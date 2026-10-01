#!/usr/bin/env python3
"""The directory a claim-carrying `gh` command will actually run in (#1509).

Usage: command_cwd.py [START]. stdin is the raw Bash tool command. START is the directory the command
starts in: the hook payload's `cwd`, or this process's cwd when it is absent. stdout is an absolute
directory. Exit 0 when it is known; exit 3 when a `cd` before the `gh` cannot be resolved here, so the
caller says "NOT checked" instead of judging against the wrong repository.

WHY. A hook runs in the SESSION's directory, not the command's. `cd ~/projects/other && gh pr create
--body-file body.md` was checked against the session repository's PR template, and a relative body
path would be read from the session directory too. The command's own `cd`s decide where `gh` runs,
so they are followed up to the first real `gh pr create|edit` / `gh issue comment` COMMAND: a word in
command position, never a phrase inside a quoted string (`echo 'gh pr create'`).

Followed:
- a `cd` joined by `&&`, `;` or a newline;
- inside `{ …; }`, `if`, `while` or `until` (the same shell);
- behind `builtin` or `command`, or with redirections (`cd x 2>/dev/null`);
- inside a `case` branch, for a `gh` in that same branch.

A `cd` inside `( … )` does not outlive the subshell.

Unresolvable, so exit 3, never a guess:
- `cd -`; a target with `$` or a backquote; `~user`; a directory that does not exist;
- `pushd`/`popd`; a negated command (`! cd x`);
- a `cd` joined by `|`, `||` or `&` (it may not have run);
- a `gh` after a `case` whose branch moved the directory (which branch ran is unknown);
- a command the lexer cannot read.
"""
from __future__ import annotations

import os
import re
import shlex
import sys

ASSIGN = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*=")
APPLIES = {"&&", ";", ";;", ";&", ";;&"}  # a cd followed by these has run before the next command
# One operator at a time out of a punctuation run. Anything with < or > is a redirection.
OPS = re.compile(r"&&|\|\||;;&|;;|;&|<<<|&>>|&>|>>|>&|<&|<<|<>|>\||[;&|()<>]")
KEYWORDS = {"{", "}", "!", "if", "then", "elif", "else", "fi", "do", "done", "while", "until", "time"}
WRAPPERS = {"builtin", "command"}
HEREDOC = re.compile(r"(?<!<)<<(-?)\s*(['\"]?)([A-Za-z0-9_][A-Za-z0-9_-]*)\2")


class Unresolved(Exception):
    pass


class Found(Exception):
    def __init__(self, here: str):
        self.here = here


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


def _is_gh(w: list[str]) -> bool:
    return len(w) >= 3 and w[0] == "gh" and (
        (w[1] == "pr" and w[2] in ("create", "edit")) or (w[1] == "issue" and w[2] == "comment"))


def resolve(cmd: str, start: str, home: str) -> str:
    cmd = strip_heredoc_bodies(cmd)
    lex = shlex.shlex(cmd.replace("\n", " ; "), posix=True, punctuation_chars=";&|()<>")
    lex.whitespace_split = True
    try:
        tokens = list(lex)
    except ValueError as e:                 # an unbalanced quote outside any heredoc
        if re.search(r"(^|[\s;&|(])(cd|pushd|popd)(\s|$|[;&|)])", cmd):
            raise Unresolved(f"the command could not be lexed: {e}") from e
        return start                        # no directory change anywhere: the starting directory

    here, stack, words = start, [], []
    # A case: (the directory before the case, the directory at the start of this branch, mode).
    cases: list[list] = []
    after_case_unknown = False
    redirect = False

    def finish(sep: str | None) -> None:
        nonlocal here, words
        w = list(words)
        words = []
        # Assignments, a brace group's and a compound's keywords, and `builtin`/`command` all leave
        # the command running in THIS shell, so peel them. `!` inverts the status: refuse it.
        while w and (ASSIGN.match(w[0]) or w[0] in KEYWORDS
                     or (w[0] in WRAPPERS and len(w) > 1 and not w[1].startswith("-"))):
            if w[0] == "!":
                raise Unresolved("a negated command before gh")
            w.pop(0)
        if not w:
            return
        if _is_gh(w):
            if after_case_unknown:
                raise Unresolved("gh after a case whose branch changed directory")
            raise Found(here)
        if w[0] in ("pushd", "popd"):
            raise Unresolved(w[0])
        if w[0] == "cd":
            if sep is None:
                return                      # a trailing cd: no gh follows it
            if sep not in APPLIES:
                raise Unresolved(f"cd joined by {sep!r}, so it may not apply")
            here = _target(w[1:], here, home)

    def end_branch() -> None:
        nonlocal here, after_case_unknown
        c = cases[-1]
        if here != c[1]:
            after_case_unknown = True       # which branch ran is unknown after esac
        here = c[1]
        c[2] = "pattern"

    try:
        for t in tokens:
            punct = bool(t) and set(t) <= set(";&|()<>")
            if not punct:
                if redirect:                # the redirection's target, not an argument
                    redirect = False
                    continue
                if cases and cases[-1][2] == "header":
                    if t == "in":
                        cases[-1][2] = "pattern"
                    continue
                if cases and cases[-1][2] == "pattern":
                    if t == "esac":
                        cases.pop()         # end_branch already restored the directory
                    continue                # a pattern word
                if cases and cases[-1][2] == "body" and t == "esac" and not words:
                    end_branch()
                    cases.pop()
                    continue
                if not words and t == "case":
                    cases.append([here, here, "header"])
                    continue
                words.append(t)
                continue
            for op in OPS.findall(t):
                if "<" in op or ">" in op:
                    if words and words[-1].isdigit():
                        words.pop()         # `2>`: the fd number belongs to the redirection
                    redirect = True
                elif cases and cases[-1][2] == "pattern" and op == ")":
                    cases[-1][1] = here     # a pattern ends; its branch starts here
                    cases[-1][2] = "body"
                elif cases and cases[-1][2] == "pattern" and op == "(":
                    continue                # the optional leading ( of a pattern
                elif cases and cases[-1][2] == "body" and op in (";;", ";&", ";;&"):
                    finish(op)
                    end_branch()
                elif op == "(":
                    stack.append(here)
                elif op == ")":
                    finish(";")             # the subshell's last command ran inside it
                    here = stack.pop() if stack else here
                else:
                    finish(op)
        finish(None)
    except Found as f:
        return f.here
    return start                            # no real gh command: nothing moved it


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
