#!/usr/bin/env python3
"""The directory a claim-carrying `gh` command will actually run in (#1509).

stdin: the raw Bash tool command. stdout: an absolute directory. Exit 0 when it is known, exit 3 when
a `cd` before the `gh` cannot be resolved here, so the caller says "NOT checked" instead of judging
against the wrong repository.

WHY. A hook runs in the SESSION's directory, not the command's. `cd ~/projects/other && gh pr create
--body-file body.md` was checked against the session repository's PR template, and a relative body
path would be read from the session directory too. The command's own `cd` decides where `gh` runs, so
follow it: each `cd` joined by `&&`, `;` or a newline moves the directory; one inside a subshell
`( … )` does not outlive it.

Unresolvable, so exit 3, never a guess: `cd -`, a target with `$` or a backquote, `~user`, a
directory that does not exist, `pushd`/`popd`, a `cd` piped or joined by `||` or `&` (it may not
apply), and a command the shell lexer cannot read. No `cd` at all is the starting directory.
"""
from __future__ import annotations

import os
import re
import shlex
import sys

GH = re.compile(r"\bgh\s+(pr\s+(create|edit)|issue\s+comment)\b")
ASSIGN = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*=")
APPLIES = {"&&", ";"}            # a cd followed by these has run before the next command
OPS = re.compile(r"&&|\|\||;;|[;&|()]")


class Unresolved(Exception):
    pass


def _target(args: list[str], here: str, home: str) -> str:
    args = [a for a in args if a not in ("-L", "-P", "--")]
    if not args:
        return home
    if len(args) > 1:
        raise Unresolved("cd with more than one argument")
    a = args[0]
    if a == "-" or "$" in a or "`" in a:
        raise Unresolved(f"cd {a}")
    if a == "~" or a.startswith("~/"):
        a = home + a[1:]
    elif a.startswith("~"):
        raise Unresolved(f"cd {a}")
    path = os.path.normpath(os.path.join(here, a))
    if not os.path.isdir(path):
        raise Unresolved(f"cd {a}: no such directory")
    return path


HEREDOC = re.compile(r"(?<!<)<<(-?)\s*(['\"]?)([A-Za-z0-9_][A-Za-z0-9_-]*)\2")


def strip_heredoc_bodies(cmd: str) -> str:
    """Drop heredoc BODIES, keeping the opener's line: a body is data, and an apostrophe in it
    (`it's`) is not a quote the lexer should try to close. As normalize_cmd.sh does (#906)."""
    out, delim, dash = [], None, False
    for line in cmd.split("\n"):
        if delim is not None:
            if (line.lstrip("\t") if dash else line) == delim:
                delim = None
            continue
        out.append(line)
        m = HEREDOC.search(line)
        if m:
            dash, delim = m.group(1) == "-", m.group(3)
    return "\n".join(out)


def resolve(cmd: str, start: str, home: str) -> str:
    cmd = strip_heredoc_bodies(cmd)
    m = GH.search(cmd)
    prefix = cmd[: m.start()] if m else cmd
    if not re.search(r"(^|[\s;&|(])(cd|pushd|popd)(\s|$|[;&|)])", prefix):
        return start                        # no directory change before the gh: the hook's own cwd
    lex = shlex.shlex(prefix.replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
    lex.whitespace_split = True
    try:
        tokens = list(lex)
    except ValueError as e:                 # an unbalanced quote, e.g. inside a heredoc body
        raise Unresolved(f"the command could not be lexed: {e}") from e

    here, stack, words = start, [], []

    def finish(sep: str | None) -> None:
        nonlocal here, words
        w = list(words)
        words = []
        while w and ASSIGN.match(w[0]):
            w.pop(0)
        if not w:
            return
        if w[0] in ("pushd", "popd"):
            raise Unresolved(w[0])
        if w[0] == "cd":
            if sep not in APPLIES:
                raise Unresolved(f"cd joined by {sep!r}, so it may not apply")
            here = _target(w[1:], here, home)

    for t in tokens:
        if not (t and set(t) <= set(";&|()")):
            words.append(t)
            continue
        # The lexer groups a run of punctuation (`)&&`, `;(`), so read it one operator at a time.
        for op in OPS.findall(t):
            if op == "(":
                stack.append(here)
            elif op == ")":
                finish(";")                 # the subshell's last command ran inside it
                here = stack.pop() if stack else here
            else:
                finish(op)
    # The words before the gh, on the same segment: `cd x gh …` is not a cd that ran first.
    if words and words[0] == "cd":
        raise Unresolved("cd with no separator before gh")
    return here


def main() -> int:
    try:
        print(resolve(sys.stdin.read(), os.getcwd(), os.environ.get("HOME", "")))
    except Unresolved as e:
        print(f"could not resolve the command's directory: {e}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
