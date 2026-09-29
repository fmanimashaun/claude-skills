#!/usr/bin/env python3
"""Does this shell command `git push` to `main` or `master`? Decided the way git decides it.

Run:  printf '%s' "$cmd" | python3 push_targets.py    # exit 0 = targets main/master (named on
                                                       #   stdout), 10 = no push targets them,
                                                       #   anything else = could not judge, and
                                                       #   the caller fails CLOSED
      python3 push_targets.py --selftest

WHY THIS EXISTS (#1410). `release-gate.sh` matched `\\b(main|master)\\b` anywhere in a push segment,
and `\\b` counts `-` and `/` as boundaries: `git push -u origin fix/1010-one-main` and
`feat/983-pr2-master-detail` were both refused as promotions, twice in one day, and both authors
renamed their branch to get past it. A fail-closed gate that refuses correct work teaches people
its refusals are noise.

AND THE OTHER DIRECTION, found while fixing it. The regex read the NORMALISED segment, and the
normaliser strips quoted spans -- so `git push origin "main"` and `git push origin 'HEAD:main'`
arrived as `git push origin ` and were ALLOWED. This parser reads the RAW command with `shlex`.

THE RULE THAT KEEPS IT CLOSED (the #1470 review found five pushes to main the first version allowed:
`$(echo main)`, `main>/dev/null`, a mid-word `#` read as a comment, `HEAD:heads/main`, `{main,dev}`).
A parser can only answer "no" about text it actually modelled. So:
  * anything the shell would EXPAND in a refspec (`$`, a backtick, braces, a glob) is "could not
    judge", never read literally;
  * redirections are split off before the refspec is read;
  * comments and heredoc bodies are removed by a quote-aware scanner that follows bash's rule
    (`#` starts a comment only at the start of a word), not shlex's;
  * `git` is found anywhere in a segment, so `sudo -u x`, `timeout 60`, `env A=1` cannot hide a push;
  * "no" is exit 10, not 1, so an uncaught exception (exit 1) can never read as "no".

What counts as a destination, per `git help push`:
  * a refspec `<src>:<dst>` names `<dst>` (a leading `+` only forces); `:<dst>` deletes `<dst>`;
    `<ref>` alone names `<ref>`; `HEAD` / `@` alone names the current branch; `:` alone is the
    matching branches, which may include main -- treated as targeting it;
  * `refs/heads/main` and `heads/main` are `main` (git qualifies `heads/main` to `refs/heads/main`);
  * `--all`, `--branches`, `--mirror` push every branch, main included;
  * no refspec (`git push`, `git push origin`) pushes what `@{push}` resolves to -- which honours
    `push.default` and an upstream, so a branch tracking `origin/main` IS caught -- falling back to
    the current branch's name, resolved in the directory the push runs in (`git -C`, a prior `cd`).
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from typing import Callable

PROTECTED = {"main", "master"}
SEPARATOR_CHARS = set(";&|()\n")
PUSH_OPTS_WITH_VALUE = {"-o", "--push-option", "--receive-pack", "--exec", "--repo"}
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
EVERY_BRANCH = {"--all", "--branches", "--mirror"}
EXPANDS = set("$`{}*?[")
HEREDOC = re.compile(r"<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")

TARGETS, NO, UNJUDGEABLE = 0, 10, 3


class Unjudgeable(Exception):
    """The command could not be read well enough to say no. The caller must deny."""


SUBST = "$__SUBST__"
CURRENT_BRANCH_IDIOMS = {"git branch --show-current", "git rev-parse --abbrev-ref HEAD"}


def _subst_end(cmd: str, i: int) -> int:
    """Index just past the `)` closing the substitution whose `(` is at `i`, quote-aware."""
    depth, quote, n = 0, "", len(cmd)
    while i < n:
        c = cmd[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 2; continue
            if c == quote:
                quote = ""
        elif c == "\\":
            i += 2; continue
        elif c in "'\"":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise Unjudgeable("an unterminated command substitution")


def _placeholder(body: str) -> str:
    # `"$(git branch --show-current)"` is how agents spell "this branch": read it as HEAD, which
    # resolves to the branch it names, instead of refusing every such push (#1470 round 2).
    return "HEAD" if " ".join(body.split()) in CURRENT_BRANCH_IDIOMS else SUBST


def strip_comments_and_heredocs(cmd: str) -> str:
    """Bash's rules, not shlex's: `#` opens a comment only at the start of a word, outside quotes;
    a heredoc's body runs from the next newline to its delimiter line."""
    out: list[str] = []
    i, n, quote = 0, len(cmd), ""
    pending: list[tuple[str, bool]] = []          # heredoc delimiters awaiting the next newline
    while i < n:
        c = cmd[i]
        if quote == '"' and (cmd.startswith("$(", i) or c == "`"):
            end = _subst_end(cmd, i + 1) if c == "$" else cmd.find("`", i + 1) + 1
            if end <= 0:
                raise Unjudgeable("an unterminated backtick substitution")
            out.append(_placeholder(cmd[i + 2:end - 1] if c == "$" else cmd[i + 1:end - 1]))
            i = end
            continue
        if quote:
            out.append(c)
            if c == "\\" and quote == '"' and i + 1 < n:
                out.append(cmd[i + 1]); i += 2; continue
            if c == quote:
                quote = ""
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append(c + cmd[i + 1]); i += 2; continue
        if c in "$<>" and cmd.startswith("(", i + 1) and (i == 0 or cmd[i - 1] != "<"):
            # `$(...)`, `<(...)`, `>(...)`: ONE word, or shlex splits at `(` and the refspecs after
            # it land in another "segment" nobody reads -- `git -C $(pwd) push origin main` passed.
            end = _subst_end(cmd, i + 1)
            out.append(_placeholder(cmd[i + 2:end - 1]) if c == "$" else SUBST)
            i = end
            continue
        if c == "`":
            end = cmd.find("`", i + 1) + 1
            if end <= 0:
                raise Unjudgeable("an unterminated backtick substitution")
            out.append(_placeholder(cmd[i + 1:end - 1]))
            i = end
            continue
        if c in "'\"":
            quote = c; out.append(c); i += 1; continue
        if c == "#" and (i == 0 or cmd[i - 1] in " \t\n;&|()<>"):
            while i < n and cmd[i] != "\n":
                i += 1
            continue
        if c == "<" and cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            m = HEREDOC.match(cmd, i)
            if m:
                pending.append((m.group(3), m.group(1) == "-"))
                out.append(" "); i = m.end(); continue
        if c == "\n" and pending:
            out.append("\n"); i += 1
            for delim, tabs in pending:
                while i < n:
                    end = cmd.find("\n", i)
                    line = cmd[i:] if end == -1 else cmd[i:end]
                    i = n if end == -1 else end + 1
                    if (line.lstrip("\t") if tabs else line) == delim:
                        break
            pending = []
            continue
        out.append(c)
        i += 1
    return "".join(out)               # an unterminated quote is left for shlex to refuse


def tokens(cmd: str) -> list[str]:
    lex = shlex.shlex(strip_comments_and_heredocs(cmd), posix=True, punctuation_chars=";&|()<>\n")
    lex.whitespace = " \t\r"          # a newline separates commands; it is not mere whitespace
    lex.whitespace_split = True
    lex.commenters = ""               # removed above, by bash's rule
    try:
        return list(lex)
    except ValueError as exc:
        raise Unjudgeable(str(exc)) from exc


def segments(toks: list[str]) -> list[list[str]]:
    """Split on command separators; drop each redirection operator and its target."""
    out: list[list[str]] = [[]]
    skip = False
    for t in toks:
        if skip:
            skip = False
            continue
        if set(t) <= SEPARATOR_CHARS:
            out.append([])
        elif set(t) <= set("<>&") and set(t) & set("<>"):
            skip = True               # `>`, `>>`, `2>&` ... : the next token is its target
        else:
            out[-1].append(t)
    return [s for s in out if s]


def push_args(seg: list[str]) -> tuple[list[str], str | None] | None:
    """The arguments after `push` and any `git -C <dir>`, wherever `git` appears in the segment
    (after `sudo -u x`, `timeout 60`, `env A=1` ...); None if the segment is not a git push."""
    for j, word in enumerate(seg):
        if word != "git":
            continue
        i, workdir = j + 1, None
        while i < len(seg) and seg[i].startswith("-"):
            if seg[i] in GIT_OPTS_WITH_VALUE:
                if seg[i] == "-C" and i + 1 < len(seg):
                    workdir = seg[i + 1]
                i += 2
            else:
                i += 1
        if i < len(seg) and seg[i] == "push":
            return seg[i + 1:], workdir
    return None


def branch_of(dst: str) -> str:
    for prefix in ("refs/", "heads/"):
        if dst.startswith(prefix):
            dst = dst[len(prefix):]
    return dst


def destinations(args: list[str], current: Callable[[bool], str | None]) -> list[str]:
    """Every branch this push writes. `current(push)` resolves the current branch (push=False) or
    its `@{push}` destination (push=True); None = unknown."""
    for word in args:
        if SUBST in word:
            raise Unjudgeable(f"{word!r} runs a command whose output git sees, not this text")
    positional: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            positional.extend(args[i + 1:])
            break
        if a in EVERY_BRANCH:
            return [f"every branch ({a})"]
        if a in PUSH_OPTS_WITH_VALUE:
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        positional.append(a)
        i += 1
    for word in positional:
        if EXPANDS & set(word) or word.startswith("~"):      # `~user` is tilde expansion
            raise Unjudgeable(f"{word!r} is expanded by the shell before git sees it")
    # `--repo=<r>` "is equivalent to the <repository> argument. If both are specified, the
    # command-line argument takes precedence" (git help push): the first positional is still the
    # repository, so `--repo=origin main` pushes to a remote named main, not to branch main.
    refspecs = positional[1:]
    if not refspecs:
        dst = current(True) or current(False)
        if not dst:
            raise Unjudgeable("a push with no refspec, and the current branch could not be resolved")
        return [dst]
    out = []
    for spec in refspecs:
        spec = spec.lstrip("+")
        if spec == ":":
            return ["the matching branches (:)"]
        src, sep, dst = spec.partition(":")
        target = dst if sep and dst else src
        if target in ("HEAD", "@"):
            target = current(False) or ""
            if not target:
                raise Unjudgeable("HEAD could not be resolved to a branch")
        out.append(branch_of(target))
    return out


def targets(cmd: str, current: Callable[[bool, str | None], str | None]) -> list[str]:
    hits = []
    cwd: str | None = None                    # a prior `cd <dir>` moves where a bare push resolves
    for seg in segments(tokens(cmd)):
        if seg[0] == "cd" and len(seg) == 2:
            cwd = seg[1] if cwd is None or os.path.isabs(seg[1]) else os.path.join(cwd, seg[1])
            continue
        parsed = push_args(seg)
        if parsed is None:
            continue
        args, workdir = parsed
        where = workdir if workdir and (cwd is None or os.path.isabs(workdir)) else (
            os.path.join(cwd, workdir) if workdir else cwd)
        for dst in destinations(args, lambda push, d=where: current(push, d)):
            if dst in PROTECTED or dst.startswith(("every branch", "the matching")):
                hits.append(dst)
    return hits


def git_current(push: bool, workdir: str | None) -> str | None:
    rev = "@{push}" if push else "HEAD"
    cmd = ["git"] + (["-C", workdir] if workdir else []) + ["rev-parse", "--abbrev-ref", rev]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not out or out == "HEAD":      # detached, or no such ref
        return None
    return out.split("/", 1)[1] if push and "/" in out else out


def selftest() -> int:
    failures: list[str] = []

    def fake(branch: str | None, upstream: str | None = None, by_dir: dict | None = None):
        def cur(push: bool, d: str | None = None) -> str | None:
            if by_dir is not None and d in by_dir:
                return None if push else by_dir[d]
            return upstream if push else branch
        return cur

    on_feature = fake("fix/1010-one-main")
    cases = [
        # (#1410) the false refusals: `main`/`master` INSIDE a branch name is not a destination
        ("git push -u origin fix/1010-one-main", on_feature, False),
        ("git push origin feature/main-menu", on_feature, False),
        ("git push origin main-nav", on_feature, False),
        ("git push -u origin feat/983-pr2-master-detail", on_feature, False),
        ("git push origin maintenance", on_feature, False),
        ("git push", on_feature, False),
        ("git push origin HEAD", on_feature, False),
        ('git commit -m "push origin main" && git push origin feature/x', on_feature, False),
        ("git push origin --tags", on_feature, False),
        ("git push origin feature/x > /tmp/log 2>&1", on_feature, False),
        ("git push origin feature/x # not main", on_feature, False),
        # (#1470 review) a heredoc body with an apostrophe is not an unbalanced quote
        ("cat > note.md <<'EOF'\nit's done, push main later\nEOF\ngit push -u origin fix/x", on_feature, False),
        ("cat <<-EOF\n\tdon't\n\tEOF\ngit push origin fix/x", on_feature, False),
        # the real promotions
        ("git push origin main", on_feature, True),
        ("git push origin HEAD:main", on_feature, True),
        ("git push origin dev:main", on_feature, True),
        ("git push origin main:main", on_feature, True),
        ("git push origin refs/heads/main", on_feature, True),
        ("git push origin HEAD:refs/heads/main", on_feature, True),
        ("git push origin dev:refs/heads/master", on_feature, True),
        ("git push origin +main", on_feature, True),
        ("git push origin +HEAD:main", on_feature, True),
        ("git push origin :main", on_feature, True),
        ("git push origin --delete main", on_feature, True),
        ("git push --all origin", on_feature, True),
        ("git push origin :", on_feature, True),
        ("git push --repo=origin origin main", on_feature, True),
        ("git push --repo=origin main", on_feature, False),
        ("git push -- origin main", on_feature, True),
        ("git push origin main dev", on_feature, True),
        ("git push --set-upstream origin main", on_feature, True),
        ("git push --force origin main", on_feature, True),
        ("git -C repo push -o ci.skip origin main", on_feature, True),
        ("FOO=1 sudo git push origin main", on_feature, True),
        ("sudo -u bob git push origin main", on_feature, True),
        ("timeout 60 git push origin main", on_feature, True),
        ("git status; git push origin main", on_feature, True),
        ("git status\ngit push origin main", on_feature, True),
        # the bypass the regex had: the normaliser strips quoted spans, the parser must not
        ('git push origin "main"', on_feature, True),
        ("git push origin 'HEAD:main'", on_feature, True),
        # (#1470 review) the five the first version ALLOWED
        ("git push origin $(echo main)", on_feature, True),
        ("git push origin `echo main`", on_feature, True),
        ("git push origin main>/dev/null", on_feature, True),
        ("git push origin main>log 2>&1", on_feature, True),
        ("echo done#1; git push origin main", on_feature, True),
        ("git push origin HEAD:heads/main", on_feature, True),
        ("git push origin {main,dev}", on_feature, True),
        ("git push origin ~main", on_feature, True),
        ("git push -o main origin feature/x", on_feature, False),
        ("git push origin $'main'", on_feature, True),
        ("git push origin 'refs/heads/*:refs/heads/*'", on_feature, True),
        # (#1470 round 2) `$(` inside an OPTION word split the command at `(`, hiding the refspecs
        ("git push -v$(true) origin main", on_feature, True),
        ("git -C $(pwd) push origin main", on_feature, True),
        ("git push --receive-pack=$(echo git-receive-pack) origin main", on_feature, True),
        ("git push --no-verify$(true) origin main", on_feature, True),
        # an unquoted substitution WORD-SPLITS: this expands to `-v main`, a push to main, and
        # only the substitution check sees it -- the option word is otherwise skipped
        ("git push origin -v$(echo ' main')", on_feature, True),
        ("git push origin <(echo main)", on_feature, True),
        # ...while the everyday forms stay usable: a substitution elsewhere, and the current-branch idioms
        ('git commit -m "$(cat msg)" && git push origin fix/x', on_feature, False),
        ("git -C $(pwd) push origin fix/x", on_feature, False),
        ('git push -u origin "$(git branch --show-current)"', on_feature, False),
        ("git push -u origin `git rev-parse --abbrev-ref HEAD`", on_feature, False),
        ('git push -u origin "$(git branch --show-current)"', fake("main"), True),
        # a bare push FROM main, and from a branch whose @{push} is main (push.default=upstream)
        ("git push", fake("main"), True),
        ("git push origin HEAD", fake("main"), True),
        ("git push", fake("topic", "main"), True),
        # a bare push resolves where it RUNS: `cd` into a clone that is on main
        ("cd other && git push", fake("topic", by_dir={"other": "main"}), True),
        ("cd other\ngit push", fake("topic", by_dir={"other": "main"}), True),
        ("git -C other push", fake("topic", by_dir={"other": "main"}), True),
    ]
    for cmd, cur, want in cases:
        try:
            got = bool(targets(cmd, cur))
        except Unjudgeable as exc:
            got = "unjudgeable" if want else f"unjudgeable: {exc}"
            if want:          # could-not-judge is denied by the hook: correct for a real promotion
                continue
        if got is not want:
            failures.append(f"{cmd!r}: expected {'TARGETS main' if want else 'does not target main'}, got {got}")
    # Could not judge -> Unjudgeable, which the hook turns into a denial. Never a quiet "no".
    for cmd, cur in (('git push origin "main', on_feature), ("git push", fake(None)),
                     ("git push origin $BRANCH", on_feature), ("git push origin {a,b}", on_feature)):
        try:
            targets(cmd, cur)
            failures.append(f"{cmd!r}: must be unjudgeable (the hook denies), not answered")
        except Unjudgeable:
            pass
    # "no" must not share an exit code with a crash: python's uncaught-exception exit is 1.
    if NO in (0, 1) or UNJUDGEABLE == NO:
        failures.append(f"exit codes: NO={NO} must differ from 0, 1 (a crash) and UNJUDGEABLE")
    total = len(cases) + 5
    if failures:
        print(f"push_targets selftest FAILED -- {len(failures)} of {total}:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"push_targets selftest: {total} checks passed")
    return 0


def main(argv: list[str]) -> int:
    if argv[1:] == ["--selftest"]:
        return selftest()
    try:
        hits = targets(sys.stdin.read(), git_current)
    except Unjudgeable as exc:
        print(f"could not judge the push destination: {exc}")
        return UNJUDGEABLE
    except Exception as exc:          # a crash must deny, never fall through as "no"
        print(f"push_targets crashed: {exc!r}")
        return UNJUDGEABLE
    if hits:
        print(", ".join(sorted(set(hits))))
        return TARGETS
    return NO


if __name__ == "__main__":
    sys.exit(main(sys.argv))
