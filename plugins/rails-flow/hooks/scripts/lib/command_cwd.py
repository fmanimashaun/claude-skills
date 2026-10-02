#!/usr/bin/env python3
"""The directory a claim-carrying `gh` command will actually run in (#1509).

Usage: command_cwd.py [START]. stdin is the raw Bash tool command. START is the directory the command
starts in: the hook payload's `cwd`, or this process's cwd when it is absent. stdout is an absolute
directory. Exit 0 when it is known; exit 3 when it cannot be told, so the caller says "NOT checked"
instead of judging against the wrong repository (the maintainer's decision on #1509: allow, loudly).

WHY. A hook runs in the SESSION's directory, not the command's. `cd ~/projects/other && gh pr create
--body-file body.md` was checked against the session repository's PR template, and a relative body
path would be read from the session directory too.

AN ALLOWLIST, NOT A SHELL (#1516, round 3). Three review rounds each found new shell shapes that a
partial interpreter followed wrongly (an `if` body, `false && cd`, `eval`, `env -C`, an arithmetic `<<`).
So exactly one grammar is followed, and anything else is "cannot tell":

    [cd-segment SEP]... gh-segment           SEP is `&&`, `;` or a newline
    cd-segment = cd PATH [REDIR]...          PATH is one plain or quoted word; REDIR is `>`, `>>` or `>&`
                                             (an fd number touching it, `2>`, included) and its target
    gh-segment = [VAR=x]... [WRAPPER]... gh (pr create | pr edit | issue comment) ...

WRAPPER is `env` (assignments only, no option), `command [-p]`, `exec`, `nohup`, `nice [-n N]`,
`timeout [OPTS] DURATION` or `time [-p]`; `gh` may be named by its path. Comments are dropped first:
a `#` that starts a word outside quotes, to the end of its line.

`cd -P` / `cd -L` are out: `-P` resolves symlinks physically (`cd -P link/..` is the link target's parent),
and a logical `..` is all this resolver does.

When EVERY segment before the gh segment starts (after `VAR=x` assignments) with a literal command word
from SAFE, the gh segment may follow them joined by anything (`git push && gh …`), and the answer is
START, as it was before #1509. SAFE is an allowlist too (#1516, round 4): a denylist of the words that
move a directory missed zsh's `chdir`, `builtin source`, `command .`, `$x` and `$'cd'`.

KNOWN LIMITS, invisible in the command text: a shell function or alias from the user's rc that cds
(zoxide's `z`, autojump's `j`) or that shadows a SAFE word, and CDPATH or zsh's CHASE_LINKS / AUTO_CD set
in the command's shell but not in this hook's environment (CDPATH is read from this process's).

Everything else is exit 3: a cd target with `$`, a backquote or `~user`, `-` or any option, a missing
directory, a relative path while CDPATH is set; a bare `cd` or one with two arguments; `if`/`while`/`until`/`for`/
`case`, subshells, brace groups, functions, `eval`, `source`, `pushd`/`popd`, `!`, `||`, `|`, `&`, any
other command before gh once a directory change is in sight; a redirect on a cd other than `>`, `>>`,
`>&`; a gh not found as a command word of the grammar (`sudo gh`, `bash -c "…"`, `env -C dir gh`, any
`env` option); and an unbalanced quote before the gh.
"""
from __future__ import annotations

import os
import re
import shlex
import sys

ASSIGN = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*=")
OPS = re.compile(r"&&|\|\||;;&|;;|;&|<<<|&>>|&>|>>|>&|<&|<<|<>|>\||[;&|()<>]")
SEPS = {"&&", ";"}
CD_REDIRECTS = {">", ">>", ">&"}
# External programs, which cannot change this shell's directory, and builtins that do not. Chosen for
# what precedes a `gh pr create` in practice; a word not here before gh means "cannot tell".
SAFE = {"git", "gh", "echo", "printf", "test", "[", "true", "false", ":", "cat", "ls", "grep", "head",
        "tail", "wc", "sleep", "date", "pwd", "mkdir", "touch", "jq", "sed"}
META = set(" \t\n;&|()<>")


class Unresolved(Exception):
    pass


def prepare(cmd: str) -> str:
    """One left-to-right pass, as the shell reads it, outside quotes only: drop a comment (`#` at the
    start of a word, to the end of its line), and an fd number that touches its `<`/`>` (`2>`), so
    `cd 5 >x` keeps 5 as its argument. A backslash-escaped character never ends a word (`B\\ #x`)."""
    out: list[str] = []
    q, i, n = "", 0, len(cmd)
    escaped = False                         # the previous character was escaped by a backslash
    while i < n:
        c = cmd[i]
        if q:                               # inside quotes: copy; only `"` honours a backslash
            out.append(c)
            if q == '"' and c == "\\" and i + 1 < n:
                out.append(cmd[i + 1])
                i += 1
            elif c == q:
                q = ""
            i += 1
            continue
        word_start = i == 0 or (cmd[i - 1] in META and not escaped)
        escaped = False
        if c == "\\" and i + 1 < n:
            out.append(cmd[i:i + 2])
            i += 2
            escaped = True
        elif c in "'\"":
            q = c
            out.append(c)
            i += 1
        elif c == "#" and word_start:
            j = cmd.find("\n", i)
            i = n if j < 0 else j            # keep the newline: it still ends the command
        elif c.isdigit() and word_start and re.match(r"\d+[<>]", cmd[i:]):
            i += re.match(r"\d+", cmd[i:]).end()
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _target(args: list[str], here: str, home: str) -> str:
    if len(args) != 1:
        raise Unresolved("cd takes exactly one path here")
    a = args[0]
    if a.startswith("-") or "$" in a or "`" in a:
        raise Unresolved(f"cd {a}")
    if a == "~" or a.startswith("~/"):
        a = home + a[1:]
    elif a.startswith("~"):
        raise Unresolved(f"cd {a}")
    if os.environ.get("CDPATH") and not a.startswith(("/", "./", "../")) and a not in (".", ".."):
        raise Unresolved(f"cd {a} with CDPATH set")
    path = os.path.normpath(os.path.join(here, a))
    if not os.path.isdir(path):
        raise Unresolved(f"cd {a}: no such directory")
    return path


def _gh_segment(words: list[str]) -> bool:
    """True when `words` is a gh segment of the grammar. An `env` option (`-C dir`, `-iC`) is not peeled,
    so the gh behind it is no command word of the grammar, and the command is "cannot tell"."""
    w = list(words)
    while w and ASSIGN.match(w[0]):
        w.pop(0)
    while w:
        h = w[0]
        if h == "env":
            w.pop(0)
            while w and ASSIGN.match(w[0]):
                w.pop(0)
        elif h == "command":
            w.pop(0)
            if w and w[0] == "-p":
                w.pop(0)
        elif h in ("exec", "nohup"):
            w.pop(0)
        elif h == "nice":
            w.pop(0)
            if w and w[0] == "-n":
                del w[:2]
        elif h == "timeout":
            w.pop(0)
            while w and w[0].startswith("-"):
                del w[:2 if w[0] in ("-s", "-k", "--signal", "--kill-after") else 1]
            w = w[1:]                       # the duration
        elif h == "time":
            w.pop(0)
            if w and w[0] == "-p":
                w.pop(0)
        else:
            break
    return len(w) >= 3 and os.path.basename(w[0]) == "gh" and (
        (w[1] == "pr" and w[2] in ("create", "edit")) or (w[1] == "issue" and w[2] == "comment"))


def _safe(seg: list[str]) -> bool:
    """A segment that cannot move this shell's directory: empty, assignments only, or a SAFE command."""
    w = list(seg)
    while w and ASSIGN.match(w[0]):
        w.pop(0)
    return not w or w[0] in SAFE


def _judge(done: list[tuple[list[str], bool, str]], start: str, home: str) -> str:
    if all(_safe(seg) for seg, _, _ in done):
        return start                        # nothing before gh can move the directory
    here = start
    for seg, clean, sep in done:
        if sep not in SEPS or not clean:
            raise Unresolved(f"a segment joined by {sep!r}, or redirected, before gh")
        if not seg:
            continue                        # a blank line, a leading `;`
        if seg[0] != "cd":
            raise Unresolved(f"`{seg[0]}` before gh, with a directory change in sight")
        here = _target(seg[1:], here, home)
    return here


def resolve(cmd: str, start: str, home: str) -> str:
    lex = shlex.shlex(prepare(cmd).replace("\n", " ; "), posix=True, punctuation_chars=";&|()<>")
    lex.whitespace_split = True
    lex.commenters = ""                     # prepare() has dropped the real comments
    # The segments before gh: (words, only allowed cd redirects inside it, the separator after it).
    done: list[tuple[list[str], bool, str]] = []
    words: list[str] = []
    clean, redirect = True, False
    try:
        for t in lex:                       # lazily: a quote left open AFTER the gh segment is never read
            if t and set(t) <= set(";&|()<>"):
                for op in OPS.findall(t):
                    if "<" in op or ">" in op:
                        clean = clean and op in CD_REDIRECTS
                        redirect = True
                    else:
                        done.append((words, clean, op))
                        words, clean, redirect = [], True, False
                continue
            if redirect:                    # the redirection's target, not an argument
                redirect = False
                continue
            words.append(t)
            if _gh_segment(words):
                return _judge(done, start, home)
    except ValueError as e:                 # an unbalanced quote before any gh segment
        raise Unresolved(f"the command could not be lexed: {e}") from e
    raise Unresolved("no gh pr create|edit / issue comment command word was found")


def main() -> int:
    start = sys.argv[1] if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]) else os.getcwd()
    try:
        print(resolve(sys.stdin.read(), os.path.abspath(start), os.environ.get("HOME", "")))
    except Unresolved as e:
        print(f"could not resolve the command's directory: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
