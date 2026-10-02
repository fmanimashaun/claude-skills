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
  * `git` (by basename: `/usr/bin/git`, `git.exe`, `\\git`) is found anywhere in a segment, so
    `sudo -u x`, `timeout 60`, `command`, `( )`, `{ }`, `if ... then` cannot hide a push -- and the
    HOOK hands over any command that mentions git or gh at all, not only one starting `git push`;
  * `sh|bash|zsh [options] -c '<string>'` and `eval ...` are parsed as commands in their own right;
  * a backslash-newline is a line continuation; an inline `git -c alias.x=...` and `xargs ... git
    push` are could-not-judge;
  * "no" is exit 10, not 1, so an uncaught exception (exit 1) can never read as "no".

KNOWN LIMITS -- the threat model is an agent's HONEST mistake, not deliberate obfuscation (the
coordinator's ruling on #1470). These are not read, and pass: `bash -c $'...'` (ANSI-C quoting of
the whole string), `eval "$(...)"`, a verb or command produced at run time (`$(echo git) push`,
`$g push`), here-strings and anything piped into a shell (`... | bash`), shells outside
sh/bash/zsh/dash/ksh (`fish -c`), and aliases defined in git CONFIG rather than inline with `-c`.

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
    return _subst_scan(cmd, i)[0]


def _subst_scan(cmd: str, i: int) -> tuple[int, list[tuple[str, bool]]]:
    """`_subst_end`, plus the heredoc delimiters opened inside the substitution and not yet seen when
    its `)` was reached. The substitution ends at the first `)` even inside a heredoc body, the way
    bash 3.2 and zsh end it; bash 4+ would read the body as text and close at a later `)`. The real
    delimiter is still owed after an early end, and `strip_comments_and_heredocs` must keep it pending
    so that a body line naming `cat <<END` opens nothing (#1542, mirroring `_strip_heredocs`, #1529).

    Inside a heredoc body a quote character is text, so `it's` does not open a quote that never closes
    (#1551); parentheses still count, because the substitution ends at the first `)` there."""
    depth, quote, n = 0, "", len(cmd)
    owed: list[tuple[str, bool]] = []
    in_body = False                              # past the operator's own line, before the delimiter's
    while i < n:
        c = cmd[i]
        if not quote and c == "<" and cmd.startswith("<<", i) and not cmd.startswith("<<<", i) \
                and (i == 0 or cmd[i - 1] != "<"):
            m = HEREDOC.match(cmd, i)
            if m:
                owed.append((m.group(3), m.group(1) == "-"))
                i = m.end(); continue
        if not quote and c == "\n" and owed:
            end = cmd.find("\n", i + 1)
            line = cmd[i + 1:] if end == -1 else cmd[i + 1:end]
            delim, tabs = owed[0]
            if (line.lstrip("\t") if tabs else line) == delim:
                owed.pop(0)                      # the body closed inside the substitution, as bash 4+ reads it
            in_body = bool(owed)
        if quote:
            if c == "\\" and quote == '"':
                i += 2; continue
            if c == quote:
                quote = ""
        elif c == "\\":
            i += 2; continue
        elif c in "'\"" and not in_body:
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1, owed
        i += 1
    raise Unjudgeable("an unterminated command substitution")


def _placeholder(body: str) -> str:
    # `"$(git branch --show-current)"` is how agents spell "this branch": read it as HEAD, which
    # resolves to the branch it names, instead of refusing every such push (#1470 round 2).
    return "HEAD" if " ".join(body.split()) in CURRENT_BRANCH_IDIOMS else SUBST


def strip_comments_and_heredocs(cmd: str, bodies: list[str] | None = None) -> str:
    """Bash's rules, not shlex's: `#` opens a comment only at the start of a word, outside quotes;
    a heredoc's body runs from the next newline to its delimiter line.

    Each `$( )`, `<( )`, `>( )` and backtick body is replaced by a placeholder word; when `bodies` is
    given, the text of every one is appended to it, so the caller can read what the shell will run
    there (#1550). Only the placeholder reaches the tokenizer."""
    out: list[str] = []
    i, n, quote = 0, len(cmd), ""
    pending: list[tuple[str, bool]] = []          # heredoc delimiters awaiting the next newline
    # Delimiters owed by a heredoc that a `$( )` ended early (#1542). The lines stay VISIBLE, since bash
    # 3.2 and zsh run them, and no new heredoc opens until the delimiter has been seen.
    owed: list[tuple[str, bool]] = []
    while i < n:
        c = cmd[i]
        if quote == '"' and (cmd.startswith("$(", i) or c == "`"):
            if c == "$":
                end, carried = _subst_scan(cmd, i + 1)
                owed.extend(carried)
            else:
                end = cmd.find("`", i + 1) + 1
            if end <= 0:
                raise Unjudgeable("an unterminated backtick substitution")
            body = cmd[i + 2:end - 1] if c == "$" else cmd[i + 1:end - 1]
            if bodies is not None:
                bodies.append(body)
            out.append(_placeholder(body))
            i = end
            continue
        if quote:
            out.append(c)
            if c == "\\" and quote == '"' and i + 1 < n:
                if cmd[i + 1] == "\n":           # a line continuation: both characters vanish
                    out.pop(); i += 2; continue
                out.append(cmd[i + 1]); i += 2; continue
            if c == quote:
                quote = ""
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            # `git push origin \<newline>main` is ONE command (41's delta review of #1470)
            if cmd[i + 1] != "\n":
                out.append(c + cmd[i + 1])
            i += 2; continue
        if c in "$<>" and cmd.startswith("(", i + 1) and (i == 0 or cmd[i - 1] != "<"):
            # `$(...)`, `<(...)`, `>(...)`: ONE word, or shlex splits at `(` and the refspecs after
            # it land in another "segment" nobody reads -- `git -C $(pwd) push origin main` passed.
            end, carried = _subst_scan(cmd, i + 1)
            owed.extend(carried)
            if bodies is not None:
                bodies.append(cmd[i + 2:end - 1])
            out.append(_placeholder(cmd[i + 2:end - 1]) if c == "$" else SUBST)
            i = end
            continue
        if c == "`":
            end = cmd.find("`", i + 1) + 1
            if end <= 0:
                raise Unjudgeable("an unterminated backtick substitution")
            if bodies is not None:
                bodies.append(cmd[i + 1:end - 1])
            out.append(_placeholder(cmd[i + 1:end - 1]))
            i = end
            continue
        if c in "'\"":
            quote = c; out.append(c); i += 1; continue
        if c == "#" and (i == 0 or cmd[i - 1] in " \t\n;&|()<>"):
            while i < n and cmd[i] != "\n":
                i += 1
            continue
        if c == "<" and cmd.startswith("<<", i) and not cmd.startswith("<<<", i) and not owed:
            m = HEREDOC.match(cmd, i)
            if m:
                pending.append((m.group(3), m.group(1) == "-"))
                out.append(" "); i = m.end(); continue
        if c == "\n" and owed:
            end = cmd.find("\n", i + 1)
            line = cmd[i + 1:] if end == -1 else cmd[i + 1:end]
            delim, tabs = owed[0]
            if (line.lstrip("\t") if tabs else line) == delim:
                owed.pop(0)
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


def tokens(cmd: str, bodies: list[str] | None = None) -> list[str]:
    lex = shlex.shlex(strip_comments_and_heredocs(cmd, bodies), posix=True, punctuation_chars=";&|()<>\n")
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


def is_command(word: str, names: set[str]) -> bool:
    """`git`, `/usr/bin/git`, `git.exe` (shlex has already turned `\\git` into `git`)."""
    base = word.rsplit("/", 1)[-1]
    return base in names or (base.endswith(".exe") and base[:-4] in names)


def git_verb(seg: list[str], verb: str) -> tuple[list[str], str | None] | None:
    """The arguments after `git <verb>` and any `git -C <dir>`, wherever git appears in the segment
    (after `sudo -u x`, `timeout 60`, `command`, `{`, a substitution ...); None if there is none."""
    for j, word in enumerate(seg):
        if not is_command(word, {"git"}):
            continue
        i, workdir = j + 1, None
        while i < len(seg) and seg[i].startswith("-"):
            if seg[i] in GIT_OPTS_WITH_VALUE:
                if seg[i] == "-c" and i + 1 < len(seg) and seg[i + 1].startswith("alias."):
                    raise Unjudgeable("a git alias defined inline can be any verb, push included")
                if seg[i] == "-C" and i + 1 < len(seg):
                    workdir = seg[i + 1]
                i += 2
            else:
                i += 1
        if i < len(seg) and seg[i] == verb:
            if verb == "push" and any(w == "xargs" for w in seg[:j]):
                raise Unjudgeable("xargs appends its stdin to the push, so its refspecs are unknown")
            return seg[i + 1:], workdir
    return None


def push_args(seg: list[str]) -> tuple[list[str], str | None] | None:
    return git_verb(seg, "push")


SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
# Shell options that take a VALUE, so the `-c` scan must step over both words (41's delta review:
# `bash -o pipefail -c 'git push origin main'` stopped at `-o` and passed).
SHELL_OPTS_WITH_VALUE = {"-o", "+o", "-O", "+O", "--rcfile", "--init-file"}
MAX_DEPTH = 4


def all_segments(cmd: str, depth: int = 0):
    """Every command segment, INCLUDING those inside `sh -c '<string>'`, `bash -lc`, and `eval ...`,
    parsed as commands in their own right (41's delta review of #1470)."""
    if depth > MAX_DEPTH:
        raise Unjudgeable("shell strings nested too deeply to read")
    bodies: list[str] = []
    for seg in segments(tokens(cmd, bodies)):
        yield seg
        for k, word in enumerate(seg):
            if is_command(word, SHELLS):
                i = k + 1
                while i < len(seg) and seg[i][:1] in ("-", "+"):
                    if seg[i] in SHELL_OPTS_WITH_VALUE:
                        i += 2
                        continue
                    if seg[i][:1] == "-" and not seg[i].startswith("--") and "c" in seg[i][1:]:
                        if i + 1 >= len(seg):
                            raise Unjudgeable("`-c` with no command string")
                        yield from all_segments(seg[i + 1], depth + 1)
                        break
                    i += 1
            elif word == "eval":
                yield from all_segments(" ".join(seg[k + 1:]), depth + 1)
                break
    # What a substitution runs is a command in its own right (#1550): `x=$(git push origin main)` pushes.
    # After the outer segments, so a `cd` inside a substitution (a subshell) cannot move where the
    # outer command's bare `git push` resolves.
    for body in bodies:
        yield from all_segments(body, depth + 1)


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
    for seg in all_segments(cmd):
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


GH_MERGE_OPTS_WITH_VALUE = {"-b", "--body", "-F", "--body-file", "-t", "--subject",
                            "-A", "--author-email", "--match-head-commit"}


def pr_merge_selectors(cmd: str) -> list[str]:
    """For every `gh pr merge`, the PR it names (number, URL or branch), or "" for the current
    branch's PR. `-R/--repo` names another repository, whose base this repo cannot judge."""
    out = []
    for seg in all_segments(cmd):
        for j, word in enumerate(seg):
            if not (is_command(word, {"gh"}) and seg[j + 1:j + 3] == ["pr", "merge"]):
                continue
            rest, sel, i = seg[j + 3:], "", 0
            while i < len(rest):
                a = rest[i]
                if a in ("-R", "--repo") or a.startswith("--repo="):
                    raise Unjudgeable("gh pr merge --repo names another repository")
                if a in GH_MERGE_OPTS_WITH_VALUE:
                    i += 2; continue
                if a.startswith("-"):
                    i += 1; continue
                sel = a
                break
            if SUBST in sel or EXPANDS & set(sel):
                raise Unjudgeable(f"the PR {sel!r} is expanded by the shell")
            out.append(sel)
            break
    return out


def classify(cmd: str, current) -> list[str]:
    """The hook's one question, answered from the RAW command: PUSH_MAIN, GIT_MERGE, PR_MERGE <sel>."""
    lines = [f"PUSH_MAIN {d}" for d in sorted(set(targets(cmd, current)))]
    if any(git_verb(seg, "merge") is not None for seg in all_segments(cmd)):
        lines.append("GIT_MERGE")
    lines += [f"PR_MERGE {s}".rstrip() for s in pr_merge_selectors(cmd)]
    return lines


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
        # (#1542) a heredoc that a `$( )` ended early still owes its delimiter, and no new heredoc opens
        # until it is seen: a body line naming `cat <<END` must not swallow the push after the `)`.
        ("x=$(cat <<EOF\n)\ncat <<END\nEOF\n)\ngit push origin main", on_feature, True),
        ("x=$(cat <<EOF\n)\nEOF\n)\ngit push origin main", on_feature, True),          # the control: no `cat <<END`
        ("x=$(cat <<EOF\n)\ncat <<END\nEOF\n)\ngit push origin fix/x", on_feature, False),
        ("x=$(cat <<-EOF\n)\ncat <<END\n\tEOF\n)\ngit push origin main", on_feature, True),
        # ...and once the delimiter is seen, a REAL heredoc opens again and its body is a mention
        ("x=$(cat <<EOF\n)\nEOF\n)\ncat <<END\ngit push origin main\nEND\ngit push origin fix/x", on_feature, False),
        ("x=$(cat <<-EOF\n)\n\tEOF\n)\ncat <<END\ngit push origin main\nEND\ngit push origin fix/x", on_feature, False),
        # ...and a heredoc that CLOSED inside the substitution owes nothing
        ("x=$(cat <<EOF\nhi\nEOF\n)\ncat <<END\ngit push origin main\nEND\ngit push origin fix/x", on_feature, False),
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
        # (41's delta review of #1470) a push the hook never handed over, because the segment did
        # not START with `git push`, and a push hidden by a continuation or a shell string
        ("timeout 60 git push origin main", on_feature, True),
        ("command git push origin main", on_feature, True),
        ("git --no-pager push origin main", on_feature, True),
        ("$(true) git push origin main", on_feature, True),
        ("`true` git push origin main", on_feature, True),
        ("( git push origin main )", on_feature, True),
        ("{ git push origin main; }", on_feature, True),
        ("if true; then git push origin main; fi", on_feature, True),
        ("/usr/bin/git push origin main", on_feature, True),
        ("\\git push origin main", on_feature, True),
        ("git.exe push origin main", on_feature, True),
        ("git push origin \\\nmain", on_feature, True),
        ('git push origin "ma\\\nin"', on_feature, True),
        ("bash -c 'git push origin main'", on_feature, True),
        ('sh -lc "cd x && git push origin main"', on_feature, True),
        ('eval "git push origin main"', on_feature, True),
        ("bash -c 'git push origin fix/x'", on_feature, False),
        ("bash -o pipefail -c 'git push origin main'", on_feature, True),
        ("bash -e -x -o errexit +O extglob --login -c 'git push origin main'", on_feature, True),
        ("bash --rcfile x.rc -lc 'git push origin main'", on_feature, True),
        ("bash -o pipefail -c 'git push origin fix/x'", on_feature, False),
        ("git -c alias.p=push p origin main", on_feature, True),
        ("echo main | xargs git push origin", on_feature, True),
        ("git push origin fix/x \\\n  --force-with-lease", on_feature, False),
        # a bare push FROM main, and from a branch whose @{push} is main (push.default=upstream)
        ("git push", fake("main"), True),
        ("git push origin HEAD", fake("main"), True),
        ("git push", fake("topic", "main"), True),
        # a bare push resolves where it RUNS: `cd` into a clone that is on main
        # (#1550) what a substitution runs is a command: a push inside one is a push
        ("x=$(git push origin main)", on_feature, True),
        ('echo "$(git push origin main)"', on_feature, True),
        ("x=`git push origin main`", on_feature, True),
        ("diff <(git push origin main) /dev/null", on_feature, True),
        ("x=$(echo $(git push origin main))", on_feature, True),
        ("x=$(git push origin fix/x)", on_feature, False),
        ("x=$(git rev-parse HEAD); git push origin fix/x", on_feature, False),
        ("git push origin $(git branch --show-current)", on_feature, False),
        ("x=$(echo 'git push origin main')", on_feature, False),                 # a string that names a push is not one
        ("git commit -m \"$(cat <<'EOF'\nit's done, git push origin main later\nEOF\n)\"", on_feature, False),
        # (#1551) a quote character in a heredoc body inside `$( )` is text, even an odd one
        ("git commit -m \"$(cat <<'EOF'\nit's done\nEOF\n)\"\ngit push origin fix/x", on_feature, False),
        ("git commit -m \"$(cat <<'EOF'\nit's done\nEOF\n)\"\ngit push origin main", on_feature, True),
        ("x=$(cat <<EOF\nsay \"hi\nEOF\n)\ngit push origin fix/x", on_feature, False),   # an odd double quote
        ("x=$(cat <<EOF\nsay \"hi\nEOF\n)\ngit push origin main", on_feature, True),
        # ...and a `cd` inside a substitution is a subshell: it must not move the outer bare push
        ("x=$(cd other); git push", fake("topic", by_dir={"other": "main"}), False),
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
    # --classify: the hook's other two questions, answered from the same raw parse
    for cmd, want in (("gh pr merge 12", ["PR_MERGE 12"]), ("gh pr merge --squash", ["PR_MERGE"]),
                      ('gh pr merge -b "a b" feat/x', ["PR_MERGE feat/x"]),
                      ("gh pr merge --merge https://github.com/o/r/pull/3", ["PR_MERGE https://github.com/o/r/pull/3"]),
                      ("timeout 60 gh pr merge 5", ["PR_MERGE 5"]),
                      ("bash -c 'gh pr merge 7 --merge'", ["PR_MERGE 7"]),
                      ("git merge dev", ["GIT_MERGE"]), ("sudo git merge dev", ["GIT_MERGE"]),
                      ('git commit -m "merge it" && gh pr list', []),
                      ("git push origin main", ["PUSH_MAIN main"])):
        try:
            got = classify(cmd, on_feature)
        except Unjudgeable as exc:
            got = [f"unjudgeable: {exc}"]
        if got != want:
            failures.append(f"classify {cmd!r}: expected {want}, got {got}")
    for cmd in ("gh pr merge -R o/r 5", "gh pr merge $N"):
        try:
            classify(cmd, on_feature)
            failures.append(f"classify {cmd!r}: must be unjudgeable (the hook denies)")
        except Unjudgeable:
            pass
    # "no" must not share an exit code with a crash: python's uncaught-exception exit is 1.
    if NO in (0, 1) or UNJUDGEABLE == NO:
        failures.append(f"exit codes: NO={NO} must differ from 0, 1 (a crash) and UNJUDGEABLE")
    total = len(cases) + 5 + 12
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
    if argv[1:] == ["--classify"]:
        try:
            print("\n".join(classify(sys.stdin.read(), git_current)))
            return 0
        except Exception as exc:      # Unjudgeable or a crash: the hook denies
            print(f"could not judge: {exc}")
            return UNJUDGEABLE
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
