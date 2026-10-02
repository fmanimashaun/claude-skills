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

The command is read as the shell reads it, in one left-to-right pass first: a `#` starts a comment
only at the start of a word and outside quotes (`issue#12` is one word), a `<<END` opens a heredoc only
outside quotes, and an fd number counts only when it touches its `<`/`>` (`cd 5 >x` goes to `5`).

Followed:
- a `cd` joined by `&&`, `;` or a newline;
- inside `{ …; }`, `if`, `while` or `until` (the same shell);
- behind `builtin` or `command`, or with redirections (`cd x 2>/dev/null`);
- inside a `case` branch, for a `gh` in that same branch;
- to a `gh` behind `env`, `command -p`, `exec`, `nohup`, `nice`, `timeout` or `time`, or named by path.

A `cd` inside `( … )` does not outlive the subshell.

Unresolvable, so exit 3, never a guess:
- `cd -`; a target with `$` or a backquote; `~user`; a directory that does not exist;
- `pushd`/`popd`; a negated command (`! cd x`);
- a `cd` joined by `|`, `||` or `&` (it may not have run);
- a `gh` after a `case` whose branch moved the directory (which branch ran is unknown);
- a function definition before the `gh` (whether its body ran is unknown);
- a `cd` behind a wrapper that runs it as a program (`env cd x`), or `env -C`;
- no `gh pr create|edit` / `gh issue comment` COMMAND found (`sudo gh`, `bash -c "…"`) while the text has
  a `cd` anywhere: the directory it runs in is unknown, so it is never the starting one by default;
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
# Run their operand as a PROGRAM, in this directory: the gh behind them runs here, a cd behind them is not
# the builtin. Each maps an option to the number of words it takes (its own included).
EXTERNAL = {"env": {"-i": 1, "-": 1, "--ignore-environment": 1, "-0": 1, "-v": 1, "-u": 2, "--unset": 2},
            "exec": {"-c": 1, "-l": 1, "-a": 2}, "nohup": {}, "nice": {"-n": 2},
            "timeout": {"-s": 2, "--signal": 2, "-k": 2, "--kill-after": 2, "-v": 1, "--verbose": 1,
                        "--foreground": 1, "--preserve-status": 1}}
CD_ANYWHERE = re.compile(r"(^|[\s;&|(\"'`])(cd|pushd|popd)(\s|$|[;&|)\"'`])")
META = set(" \t\n;&|()<>")


class Unresolved(Exception):
    pass


class Found(Exception):
    def __init__(self, here: str):
        self.here = here


def _delimiter(s: str, i: int) -> tuple[str, int]:
    """A heredoc delimiter word at s[i:], its quotes removed (`'EOF'`, `"EOF"`, `\\EOF`), and its end."""
    out = []
    while i < len(s) and s[i] not in META:
        if s[i] in "'\"":
            j = s.find(s[i], i + 1)
            j = len(s) if j < 0 else j
            out.append(s[i + 1:j])
            i = j + 1
        elif s[i] == "\\" and i + 1 < len(s):
            out.append(s[i + 1])
            i += 2
        else:
            out.append(s[i])
            i += 1
    return "".join(out), i


def prepare(cmd: str) -> str:
    """One left-to-right pass, as the shell reads it, outside quotes only (#1516 re-review):
    - drop a comment: `#` at the start of a word, to the end of its line. shlex's own comment handling
      ends the WHOLE command at the first `#`, mid-word too, after the newlines are joined;
    - drop heredoc BODIES, keeping the opener's line: a body is data, and an apostrophe in it (`it's`)
      is not a quote the lexer should try to close. As normalize_cmd.sh does (#906). A quoted `"<<END"`
      opens nothing;
    - drop an fd number that touches its `<`/`>` (`2>`), so `cd 5 >x` keeps 5 as its argument."""
    out: list[str] = []
    pending: list[tuple[str, bool]] = []    # heredocs opened on this line: (delimiter, strip tabs)
    q, i, n = "", 0, len(cmd)
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
        word_start = i == 0 or cmd[i - 1] in META
        if c == "\\" and i + 1 < n:
            out.append(cmd[i:i + 2])
            i += 2
        elif c in "'\"":
            q = c
            out.append(c)
            i += 1
        elif c == "#" and word_start:
            j = cmd.find("\n", i)
            i = n if j < 0 else j            # keep the newline: it still ends the command
        elif c.isdigit() and word_start and re.match(r"\d+[<>]", cmd[i:]):
            i = re.match(r"\d+", cmd[i:]).end() + i
        elif cmd.startswith("<<<", i):
            out.append("<<<")
            i += 3
        elif cmd.startswith("<<", i):
            j = i + 2
            dash = j < n and cmd[j] == "-"
            j += dash
            while j < n and cmd[j] in " \t":
                j += 1
            word, end = _delimiter(cmd, j)
            if word:
                pending.append((word, dash))
            out.append(cmd[i:end] if word else "<<")
            i = end if word else i + 2
        elif c == "\n" and pending:
            out.append(c)
            i += 1
            for delim, dash in pending:     # each body in turn, up to its own delimiter line
                while i < n:
                    j = cmd.find("\n", i)
                    line, i = (cmd[i:], n) if j < 0 else (cmd[i:j], j + 1)
                    if (line.lstrip("\t") if dash else line) == delim:
                        break
            pending = []
        else:
            out.append(c)
            i += 1
    return "".join(out)


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
    return len(w) >= 3 and os.path.basename(w[0]) == "gh" and (
        (w[1] == "pr" and w[2] in ("create", "edit")) or (w[1] == "issue" and w[2] == "comment"))


def resolve(cmd: str, start: str, home: str) -> str:
    cmd = prepare(cmd)
    lex = shlex.shlex(cmd.replace("\n", " ; "), posix=True, punctuation_chars=";&|()<>")
    lex.whitespace_split = True
    lex.commenters = ""                     # prepare() has dropped the real comments
    try:
        tokens = list(lex)
    except ValueError as e:                 # an unbalanced quote outside any heredoc
        if CD_ANYWHERE.search(cmd):
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
        # `env`, `exec`, `nohup`, `nice` and `timeout` run their operand as a program in this directory:
        # peel them too, so the gh behind them is found and the cds before it count (#1516 re-review).
        external = False
        while w:
            if ASSIGN.match(w[0]) or w[0] in KEYWORDS:
                if w[0] == "!":
                    raise Unresolved("a negated command before gh")
                if w.pop(0) == "time" and w and w[0] == "-p":
                    w.pop(0)
            elif w[0] in WRAPPERS:
                if w.pop(0) == "command":
                    while w and w[0] in ("-p", "--"):
                        w.pop(0)
                    if w and w[0].startswith("-"):
                        return              # `command -v x` describes x and runs nothing
            elif w[0] in EXTERNAL:
                opts, external = EXTERNAL[w.pop(0)], True
                while w and w[0].startswith("-") and w[0] != "--":
                    if w[0] in ("-C", "--chdir") or w[0].startswith("--chdir="):
                        raise Unresolved("env -C changes the directory")
                    take = opts.get(w[0], 1)
                    if not opts and w[0] != "-":
                        break               # nohup takes no options: this is its operand
                    del w[:take]
                if w and w[0] == "--":
                    w.pop(0)
                if opts is EXTERNAL["timeout"] and w:
                    w.pop(0)                # the duration
            else:
                break
        if not w:
            return
        if w[0] == "function":
            raise Unresolved("a function definition before gh")
        if _is_gh(w):
            if after_case_unknown:
                raise Unresolved("gh after a case whose branch changed directory")
            raise Found(here)
        if w[0] in ("pushd", "popd"):
            raise Unresolved(w[0])
        if w[0] == "cd":
            if external:
                raise Unresolved("a cd run as a program, behind a wrapper")
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
                    redirect = True         # prepare() has dropped a `2>`'s fd number
                elif cases and cases[-1][2] == "pattern" and op == ")":
                    cases[-1][1] = here     # a pattern ends; its branch starts here
                    cases[-1][2] = "body"
                elif cases and cases[-1][2] == "pattern" and op == "(":
                    continue                # the optional leading ( of a pattern
                elif cases and cases[-1][2] == "body" and op in (";;", ";&", ";;&"):
                    finish(op)
                    end_branch()
                elif op == "(":
                    # `f() …` defines a function; `$(`, `x=(` do not. Whether a body ran is unknown.
                    if words and not words[-1].endswith(("$", "=")):
                        raise Unresolved("a function definition before gh")
                    stack.append(here)
                elif op == ")":
                    finish(";")             # the subshell's last command ran inside it
                    here = stack.pop() if stack else here
                else:
                    finish(op)
        finish(None)
    except Found as f:
        return f.here
    # No gh COMMAND was found (`sudo gh`, `bash -c "cd x && gh …"`), yet the hook saw the phrase. With a cd
    # anywhere, where it runs is unknown: never the starting directory by default (#1516 re-review).
    if CD_ANYWHERE.search(cmd):
        raise Unresolved("no gh pr create|edit / issue comment command was found, and the command has a cd")
    return start


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
