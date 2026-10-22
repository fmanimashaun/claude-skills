#!/usr/bin/env python3
"""Judge one `gh pr ready` against the sweep record for HEAD (#1565). Called by guard-pr-ready.sh only.

Usage: pr_ready_guard.py ARGS. stdin is the PreToolUse JSON payload; ARGS is what followed `gh pr ready` in
the command, echoed back in the refusal. Exit 0 allows; exit 2 refuses, with the reason on stderr.

The record is written by `scripts/project_gates.py` to `<git dir>/rails-flow/sweep/<HEAD sha>.json`. It is
read, never written, here, and nothing in the command's other segments is interpreted (the coordinator's
decision on #1565, in line with epic #1793): a sweep chained before `gh pr ready` in ONE command has not run
when this judges, so it does not count.
"""
from __future__ import annotations

import json
import os
import pwd
import re
import subprocess
import sys
import time
from pathlib import Path

SWEEP_DIR = "rails-flow/sweep"
MARKER = "<!-- rails-flow:begin"
EXPLICIT = ("an explicit repository target (-R/--repo/GH_REPO/URL) cannot be matched to a local sweep record; "
            "run `gh pr ready` from the PR's own checkout, after its sweep")
SWEEP_CMD = 'python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project_gates.py"'


def _knob(name: str, default: float) -> float:
    """A positive number from the environment, else `default`. The fixtures shrink these; nothing else needs to."""
    try:
        value = float(os.environ.get(name, default))
    except ValueError:
        return default
    return value if value > 0 else default


GIT_TIMEOUT = _knob("RAILS_FLOW_GIT_TIMEOUT", 10.0)            # one git call; well under the hook's 15 s deadline (a deadline is a DENY since #1968)
HINT_MAX_WORKTREES = int(_knob("RAILS_FLOW_HINT_MAX_WORKTREES", 20))   # the worktrees the "green elsewhere" hint reads (#2143)
HINT_BUDGET = _knob("RAILS_FLOW_HINT_BUDGET", 4.0)             # seconds for the whole hint, so it can never be what runs the hook out of time


class GitTimeout(Exception):
    """git did not answer in time. NOT the same as "not a repository": the latter is an answer, this is the lack of one (#2295)."""


def git(where: str, *args: str, timeout: float | None = None) -> str | None:
    """git's stdout when it succeeds, None when it fails or cannot run. A TIMEOUT raises GitTimeout: under load it used to read as `not a repository`, which is allowed (#2295)."""
    limit = GIT_TIMEOUT if timeout is None else timeout
    try:
        done = subprocess.run(["git", "-C", where, *args], capture_output=True, text=True, timeout=limit)
    except subprocess.TimeoutExpired as exc:
        raise GitTimeout(f"`git {' '.join(args[:3])}` in {where} did not answer within {limit:g} s") from exc
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def sweep_dir(root: str, timeout: float | None = None) -> Path | None:
    where = git(root, "rev-parse", "--git-path", SWEEP_DIR, timeout=timeout)
    if not where:
        return None
    return Path(where) if os.path.isabs(where) else Path(root) / where


def in_force(root: str) -> bool:
    """The repository runs project_gates: a workflow names it, CLAUDE.md carries the rails-flow managed
    marker, or a sweep record directory already exists. Otherwise the hook does not apply (point 4)."""
    wf = Path(root) / ".github" / "workflows"
    for f in sorted(wf.glob("*.yml")) + sorted(wf.glob("*.yaml")) if wf.is_dir() else []:
        try:
            if "project_gates.py" in f.read_text(encoding="utf-8", errors="replace"):
                return True
        except OSError:
            continue
    try:
        if MARKER in (Path(root) / "CLAUDE.md").read_text(encoding="utf-8", errors="replace"):
            return True
    except OSError:
        pass
    d = sweep_dir(root)
    return bool(d and d.is_dir())


def refuse(reason: str, args: str) -> int:
    print(f"BLOCKED by rails-flow pr-ready guard: {reason}", file=sys.stderr)
    print("`gh pr ready` needs a GREEN sweep record with zero skips for the current HEAD (#1565). Run these as "
          "TWO separate commands (a sweep chained before it in one command has not run when this is judged):",
          file=sys.stderr)
    print(f"  1. {SWEEP_CMD}", file=sys.stderr)
    print(f"  2. gh pr ready{(' ' + args.strip()) if args.strip() else ''}", file=sys.stderr)
    return 2


def resolve_dir(payload: dict, start: str) -> tuple[str | None, str]:
    """(directory, why-not). The command's own `cd`s are followed by lib/command_cwd.py, as guard-claims does."""
    cmd = str(payload.get("tool_input", {}).get("command", ""))
    helper = Path(__file__).with_name("command_cwd.py")
    try:
        done = subprocess.run([sys.executable, str(helper), "--pr-ready", start], input=cmd,
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"lib/command_cwd.py could not run ({exc})"
    if done.returncode == 0 and done.stdout.strip():
        return done.stdout.strip(), ""
    return None, (done.stderr.strip() or f"lib/command_cwd.py exited {done.returncode}")[:200]


PLAIN_NUMBER = re.compile(r"\A[0-9]+\Z")
PLAIN_BRANCH = re.compile(r"\A[A-Za-z0-9._/-]+\Z")
REDIRECT = re.compile(r"\A[0-9]*(?:>>?|<&?|&>|>&)(.*)\Z", re.S)


def plain_word(w: str) -> bool:
    """A plain PR number, or a branch name that cannot name another repository or be a flag."""
    if PLAIN_NUMBER.match(w):
        return True
    return bool(PLAIN_BRANCH.match(w)) and "/pull/" not in w and not w.startswith("-")


def bad_word(segment: str) -> str | None:
    """THE ALLOWLIST (#1565, third security review): the first word of the `gh ... pr ... ready ...` segment that is not a
    plain PR number or branch, or None. Every flag before `pr`, before `ready` or after it is refused: a denylist of
    the spellings that pick another repository lost one spelling per review round. A redirection and its target
    (`> /dev/null`) are the shell's, not gh's, and are skipped."""
    words = segment.split()
    i = next((k for k, w in enumerate(words) if w == "gh" or w.endswith("/gh")), None)
    if i is None:
        return segment.strip() or "(empty)"
    rest = words[i + 1:]
    seen_pr = seen_ready = cut = False
    skip = False
    for w in rest:
        if skip:
            skip = False
            continue
        r = REDIRECT.match(w)
        if r and not r.group(1):            # a bare operator: it and its target are the shell's
            skip = True
            continue
        if r and not r.group(1).startswith("-"):
            continue                        # an attached target (`2>/dev/null`); `>-R` is not one, and is judged
        if not seen_pr and w == "pr":
            seen_pr = True
            continue
        if seen_pr and not seen_ready and w == "ready":
            seen_ready = True
            continue
        if seen_ready and w == "--" and not cut:
            cut = True
            continue
        if seen_ready and w == "--undo" and not cut:
            continue
        if not seen_ready or not plain_word(w):
            return w
    return None


def explicit_target(segment: str, raw: str) -> bool:
    """The PR is named by repository, not by this checkout: its HEAD says nothing about that PR (#1565 review)."""
    words = segment.split()
    if any(w in ("-R", "--repo") or w.startswith(("--repo=", "-R")) for w in words):
        return True
    if re.search(r"(^|[^A-Za-z0-9_])GH_REPO=", raw):
        return True
    return any("/pull/" in w for w in words)    # a PR URL, with or without a scheme


DYNAMIC = ("the PR argument cannot be judged without running it (a variable or command substitution); "
           "pass the PR number or URL literally")
GH_READY = re.compile(r"(?:^|[\s;&|(])(?:\S*/)?gh\b([^;&|\n]*?)\bready\b([^;&|\n]*)")


def dynamic_target(raw: str) -> bool:
    """A `$` or backtick in the flags before `ready` or the arguments after it, read from the RAW command (the
    normaliser deletes a quoted `"$(...)"`, so the segment alone cannot show it)."""
    return any("$" in m.group(1) + m.group(2) or "`" in m.group(1) + m.group(2) for m in GH_READY.finditer(raw))


def main() -> int:
    """The hook's judgement. A git that does not answer in time is a NAMED REFUSAL, not an allow (#2295)."""
    try:
        return _main()
    except GitTimeout as exc:
        return refuse(f"{exc}, so whether this repository runs the sweep guard, and which HEAD it is on, cannot be told; a gate that cannot tell does not allow. "
                      "Run the same command again (the machine is probably under load).", sys.argv[1] if len(sys.argv) > 1 else "")


def _main() -> int:
    args = sys.argv[1] if len(sys.argv) > 1 else ""
    segment = sys.argv[2] if len(sys.argv) > 2 else ""
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", "surrogateescape"))
        if not isinstance(payload, dict):
            raise ValueError("payload is not an object")
    except ValueError as exc:
        return refuse(f"the hook payload could not be read ({exc}).", args)
    start = str(payload.get("cwd") or os.getcwd())
    if not os.path.isdir(start):
        start = os.getcwd()
    where, why = resolve_dir(payload, start)
    raw = str(payload.get("tool_input", {}).get("command", ""))
    if dynamic_target(raw):
        roots = {git(d, "rev-parse", "--show-toplevel") for d in (where, start) if d}
        if any(r and in_force(r) for r in roots):
            return refuse(DYNAMIC + ".", args)
        return 0
    if explicit_target(segment, str(payload.get("tool_input", {}).get("command", ""))):
        roots = {git(d, "rev-parse", "--show-toplevel") for d in (where, start) if d}
        if any(r and in_force(r) for r in roots):
            return refuse(EXPLICIT + ".", args)
        return 0
    word = bad_word(segment)
    if word is not None:
        roots = {git(d, "rev-parse", "--show-toplevel") for d in (where, start) if d}
        if any(r and in_force(r) for r in roots):
            return refuse(f"argument {word} is not a plain PR number or branch; run `gh pr ready <number>` from the PR's "
                          "own checkout, after its sweep.", args)
        return 0
    if where is None:
        # Which repository and HEAD this `gh pr ready` targets cannot be told (lib/command_cwd.py: any word outside its SAFE list
        # before gh, a `cd` it cannot follow). A guarantee FAILS CLOSED: no guessing the session's directory, because an earlier
        # segment (`gh repo set-default`, `git remote set-url`, a url.insteadOf) can retarget gh (#1565, the coordinator's call
        # after the review of 7315b31e). Refused where the session's repository is in force; left alone where it is not.
        root = git(start, "rev-parse", "--show-toplevel")
        if root and in_force(root):
            return refuse(f"which repository this `gh pr ready` targets cannot be told ({why}). Run `gh pr ready <number>` "
                          "as its own command, from the PR's checkout, after its sweep.", args)
        return 0
    root = git(where, "rev-parse", "--show-toplevel")
    if not root or not in_force(root):
        return 0
    return judge_record(root, args)


# The word shape guard-pr-ready.sh's `cd <dir> && gh pr ready <n>` exception accepts (#2132): a plain literal path.
CD_WORD = re.compile(r"\A[A-Za-z0-9_./~+-]+\Z")


def worktrees(root: str, timeout: float) -> list[dict[str, str]]:
    """Every worktree of `root`'s repository as {worktree, HEAD, ...}, from `git worktree list --porcelain -z`: a NUL ends every field and an empty field ends a
    worktree, so a path holding a newline is one path, not two lines (#2293 review)."""
    try:
        done = subprocess.run(["git", "-C", root, "worktree", "list", "--porcelain", "-z"], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise GitTimeout(f"`git worktree list` in {root} did not answer within {timeout:g} s") from exc
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0:
        return []
    found: list[dict[str, str]] = []
    block: dict[str, str] = {}
    for field in done.stdout.split("\0"):
        if field == "":
            if block:
                found.append(block)
            block = {}
            continue
        key, _, value = field.partition(" ")
        block[key] = value
    if block:
        found.append(block)
    return found


def green_elsewhere(root: str) -> tuple[list[tuple[str, str]], str]:
    """((path, HEAD) of every OTHER worktree of `root`'s repository whose own HEAD has a green, zero-skip record, why the search stopped early or "") (#2143).

    Only a hint for a refusal: nothing here allows anything. A session whose Bash tool resets its directory to the main checkout is judged on that
    checkout's HEAD, and the released way out (`cd <worktree> && gh pr ready <n>`) was invisible in the refusal. BOUNDED (#2293 review): at most
    HINT_MAX_WORKTREES worktrees and HINT_BUDGET seconds in all, each git call inside what is left, and a refusal that is already certain never waits on this."""
    deadline = time.monotonic() + HINT_BUDGET
    try:
        listed = worktrees(root, min(GIT_TIMEOUT, HINT_BUDGET))
    except GitTimeout:
        return [], f"the search for other worktrees did not finish in {HINT_BUDGET:g} s"
    here = os.path.realpath(root)
    found: list[tuple[str, str]] = []
    scanned = 0
    for entry in listed:
        path, head = entry.get("worktree", ""), entry.get("HEAD", "")
        if not path or not head or os.path.realpath(path) == here:
            continue
        if scanned >= HINT_MAX_WORKTREES:
            return sorted(found)[:3], f"the search stopped after {HINT_MAX_WORKTREES} worktrees"
        left = deadline - time.monotonic()
        if left <= 0:
            return sorted(found)[:3], f"the search stopped after {HINT_BUDGET:g} s"
        scanned += 1
        try:
            d = sweep_dir(path, timeout=max(0.05, min(GIT_TIMEOUT, left)))
        except GitTimeout:
            return sorted(found)[:3], f"the search stopped after {HINT_BUDGET:g} s"
        try:
            data = json.loads((d / f"{head}.json").read_text(encoding="utf-8")) if d else None
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("head") == head and data.get("verdict") == "green" and type(data.get("skips")) is int and data["skips"] == 0:
            found.append((path, head))
    return sorted(found)[:3], ""


def elsewhere_hint(root: str, args: str) -> str:
    """The sentence a refusal appends when another worktree of the repository holds a green record for its own HEAD, or ''."""
    ready = f"gh pr ready{(' ' + args.strip()) if args.strip() else ''}"
    found, stopped = green_elsewhere(root)
    parts = []
    for path, head in found:
        plain = CD_WORD.match(path) is not None
        shown = path if plain else repr(path)         # a path with a newline or a quote is shown escaped, never as raw text in the message
        how = (f"run `cd {path} && {ready}` as ONE command (the Bash tool does not carry a bare `cd` to the next call)" if plain
               else f"run `{ready}` from a session started in {shown}")
        parts.append(f"a green record with zero skips exists for HEAD {head[:12]} in the worktree {shown}: {how}")
    text = "; ".join(parts) + "." if parts else ""
    if stopped:
        text = (text + " " if text else "") + f"({stopped}, so another worktree may hold one.)"
    return (" " + text) if text else ""


def judge_record(root: str, args: str) -> int:
    """The sweep record for the HEAD of `root`: 0 when it is green with zero skips, else a refusal. One judgement for the hook and for the `gh` shim (#1839)."""
    head = git(root, "rev-parse", "HEAD")
    if not head:
        return refuse(f"HEAD of {root} could not be read.", args)
    d = sweep_dir(root)
    if d is None:
        return refuse(f"the git directory of {root} could not be read.", args)
    record = d / f"{head}.json"
    if not record.is_file():
        return refuse(f"no sweep record for HEAD {head[:12]} (looked for {record}).{elsewhere_hint(root, args)}", args)
    try:
        data = json.loads(record.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("not a JSON object")
        verdict, skips = data["verdict"], data["skips"]
        failed, errored = data.get("failed", "?"), data.get("errored", "?")
        if data["head"] != head:
            return refuse(f"the record {record} names HEAD {str(data['head'])[:12]}, not {head[:12]}.", args)
        if verdict not in ("green", "red") or type(skips) is not int:
            raise ValueError(f"verdict {verdict!r}, skips {skips!r}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return refuse(f"the sweep record {record} is unreadable or malformed ({type(exc).__name__}: {exc}).", args)
    summary = f"record {record}: verdict {verdict}, failed {failed}, errored {errored}, skips {skips}"
    if verdict != "green":
        return refuse(f"the sweep for HEAD {head[:12]} was RED ({summary}).", args)
    if skips != 0:
        return refuse(f"the sweep for HEAD {head[:12]} skipped checks that applied ({summary}).", args)
    return 0


SHIM_FLAGS = ("-R", "--repo")


def _next_word(args: list[str]) -> str | None:
    """The first word of `args` that is not a flag, where `-R`/`--repo` also take the word after them: the one command-line shape that puts a value between `pr` and `ready`."""
    skip = False
    for w in args:
        if skip:
            skip = False
            continue
        if w in SHIM_FLAGS:
            skip = True
            continue
        if not w.startswith("-"):
            return w
    return None


# Variables that make `gh` (or the `git` under it) act on a repository or host other than the checkout this shim stands in: the local sweep record cannot stand for one. AN ALLOWLIST OF
# THE HARMLESS, NOT A LIST OF THE DANGEROUS (the commit's security review): every other GIT_* and GH_* variable (GIT_DIR, GIT_WORK_TREE, GIT_CONFIG_*, GH_HOST, GH_ENTERPRISE_*, GH_CONFIG_DIR,
# GH_REPO, and the ones nobody has thought of) can redirect, so each is refused where in force. These point nowhere: the editor, prompts, a credential, notifier switches.
HARMLESS_ENV = frozenset({"GIT_EDITOR", "GIT_TERMINAL_PROMPT", "GIT_PAGER", "GIT_SSH_COMMAND", "GIT_SSH", "GIT_ASKPASS", "GH_TOKEN", "GH_PAGER", "GH_DEBUG", "GH_BROWSER", "GH_EDITOR",
                          "GH_PROMPT_DISABLED", "GH_NO_UPDATE_NOTIFIER", "GH_NO_EXTENSION_UPDATE_NOTIFIER", "GH_SPINNER_DISABLED", "GH_FORCE_TTY"})


def _redirecting_env() -> list[str]:
    """Names (each once) of the variables that can point gh or git at another repository, host or config: every GIT_*/GH_* outside HARMLESS_ENV (GIT_TRACE* and the author/committer identity
    are inert too), HOME when it is not the account's own home, and XDG_CONFIG_HOME when it is set and not `<home>/.config` (git and gh read their config from them; a `url.insteadOf`
    there retargets a push or a PR)."""
    names = {k for k in os.environ if k.startswith(("GIT_", "GH_")) and k not in HARMLESS_ENV and not k.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_", "GIT_TRACE"))}
    try:
        account = os.path.realpath(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, OSError):
        account = ""
    home = os.environ.get("HOME")
    if home is not None and account and os.path.realpath(home) != account:
        names.add("HOME")
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and account and os.path.realpath(xdg) != os.path.join(account, ".config"):
        names.add("XDG_CONFIG_HOME")
    return sorted(names)


def _toplevel(cwd: str) -> tuple[str | None, str]:
    """(top level, status): "ok", "none" (git answered: not a repository) or "error" (git could not answer). git is asked WITHOUT the variables that locate a repository, so
    `GIT_DIR=/nonexistent` cannot make a repository read as no repository (#1839, the review of the first head): they are judged as what they are, below."""
    if not os.path.isdir(cwd):
        return None, "none"
    clean = {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k in HARMLESS_ENV or k.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_"))}
    try:
        done = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=GIT_TIMEOUT, env=clean)
    except (OSError, subprocess.SubprocessError):
        return None, "error"
    if done.returncode == 0 and done.stdout.strip():
        return done.stdout.strip(), "ok"
    return None, "none" if "not a git repository" in done.stderr else "error"


def shim_judge(argv: list[str], cwd: str, gh_repo: str = "") -> int:
    """Judge one `gh pr ready` (or a `gh api` that marks a PR ready) from its FINAL argv, which is what `git-shim/gh` receives after the shell has expanded the command (#1839, the
    guarantee behind #1565's tripwire).

    `argv` is everything after `gh`. The directory is where gh will run (the shim's own cwd), so no `cd` has to be followed and nothing is parsed from shell text. In force only where
    project_gates runs: a directory outside any repository, or in one that does not run it, is not checked, a named repository included (stated in the shim's header and in CLAUDE.md).
    Where it is in force: a variable that redirects gh or git (GIT_DIR, GIT_WORK_TREE, GIT_CONFIG_*, GH_HOST, GH_REPO), a repository named by flag or URL, and any word that is not a plain PR
    number or branch are refused; `--undo` passes after every other argument is judged; then the record for HEAD must be green with zero skips. When git cannot say whether the directory is a
    repository the answer is a refusal, not a pass. Returns 0 to allow, 2 to refuse (the reason is on stderr)."""
    root, status = _toplevel(cwd)
    shown = " ".join(argv)
    if status == "error":
        return refuse(f"git could not say whether {cwd} is a repository, so this `gh pr ready` cannot be judged.", shown)
    if not (root and in_force(root)):
        return 0
    first = _next_word(argv)
    i = next((k for k, w in enumerate(argv) if w == "pr" and _next_word(argv[k + 1:]) == "ready"), None)
    if i is not None:
        rest = argv[i + 1:]
        j = next(k for k, w in enumerate(rest) if w == "ready")
        after = rest[j + 1:]
        cut_at = after.index("--") if "--" in after else len(after)
        if "--undo" in after[:cut_at] and all(plain_word(w) for w in after if w not in ("--undo", "--")):
            return 0          # marking a PR draft again needs no sweep, and harms no repository: judged before the redirecting-variable and explicit-target refusals (the review of b09e947f, N6)
    redirect = _redirecting_env()
    if redirect or gh_repo:
        return refuse(f"{', '.join(redirect + (['GH_REPO'] if gh_repo else []))} is set, and it can point gh or git at another repository, host or config than this checkout: its local sweep "
                      "record cannot stand for that. Unset it and run `gh pr ready` from the PR's own checkout, after its sweep.", shown)
    if first == "api":
        if any(w in SHIM_FLAGS or w.startswith(("--repo=", "-R", "--hostname")) or w == "--hostname" for w in argv):
            return refuse(EXPLICIT + " (a `gh api` naming a repository or host).", shown)
        text = " ".join(argv)
        if "markPullRequestReadyForReview" in text:
            return judge_record(root, "gh api (marks a PR ready)")
        if any(w == "--input" or w.startswith("--input=") or "=@" in w for w in argv):
            return refuse("a `gh api` whose body is read from a file or stdin cannot be judged here (it may mark a PR ready).", shown)
        return 0
    if i is None:
        return refuse("a `gh pr ready` this shim could not place in its arguments.", shown)
    before, rest = argv[:i], argv[i + 1:]
    j = next(k for k, w in enumerate(rest) if w == "ready")
    between, after = rest[:j], rest[j + 1:]
    shown = " ".join(after)
    words = before + between + after
    if any(w in SHIM_FLAGS or w.startswith(("--repo=", "-R")) or "/pull/" in w for w in words):
        return refuse(EXPLICIT + ".", shown)
    cut = False
    for w in between + after:
        if w == "--" and not cut and w in after:
            cut = True
            continue
        if w == "--undo" and not cut:
            continue
        if not plain_word(w):
            return refuse(f"argument {w} is not a plain PR number or branch; run `gh pr ready <number>` from the PR's own checkout, after its sweep.", shown)
    return judge_record(root, shown)


def shim_unreadable_alias(expansion: str, cwd: str) -> int:
    """A gh alias whose expansion is not plain words (a quote, a backslash, a substitution, a glob...) cannot be classified from its text, and is NOT un-quoted here: a second split that can
    differ from gh's is how a quoted `pr "rea"dy` hid (the review of b09e947f, N1; the coordinator's design change: an allowlist shape, not a parser). Where in force it is refused; where it
    is not, it runs. The audited escape is RAILS_FLOW_GH_OK=1."""
    root, status = _toplevel(cwd)
    if status == "error":
        return refuse(f"git could not say whether {cwd} is a repository, so this gh alias cannot be judged.", expansion)
    if not (root and in_force(root)):
        return 0
    return refuse("this gh alias expands to something that is not plain words, so it cannot be classified and is refused rather than guessed at (a repository that runs project_gates; "
                  "write the alias with plain words, or run the command directly).", expansion)


if __name__ == "__main__":
    def _timed_out(exc: GitTimeout, shown: str) -> int:
        return refuse(f"{exc}, so this `gh pr ready` cannot be judged; a gate that cannot tell does not allow. Run the same command again (the machine is probably under load).", shown)

    if len(sys.argv) > 2 and sys.argv[1] == "--shim-unreadable":
        try:
            sys.exit(shim_unreadable_alias(sys.argv[2], os.getcwd()))
        except GitTimeout as exc:
            sys.exit(_timed_out(exc, sys.argv[2]))
    if len(sys.argv) > 1 and sys.argv[1] == "--shim":
        try:
            sys.exit(shim_judge(sys.argv[2:], os.getcwd(), os.environ.get("RF_INHERITED_GH_REPO") or os.environ.get("GH_REPO", "")))
        except GitTimeout as exc:
            sys.exit(_timed_out(exc, " ".join(sys.argv[2:])))
    sys.exit(main())
