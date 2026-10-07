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

ANY `GIT_*` or `GH_*` variable is "cannot tell" (#1516, rounds 5 and 6): GIT_DIR, GIT_WORK_TREE,
GIT_COMMON_DIR, GIT_CONFIG_GLOBAL, GIT_CONFIG_COUNT/KEY_n/VALUE_n, GIT_CONFIG_PARAMETERS and GH_REPO each
pick gh's repository whatever the directory. That holds on the gh segment, behind `env`, in an
assignment-only segment before it, by `export`, and in this process's environment, except GIT_EDITOR,
which the harness sets and which cannot change gh's target. A `GIT_X=… git push` on an earlier SAFE
command is that command's own environment: it does not persist to gh, so it is judged normally.
HOME and XDG_CONFIG_HOME set BY THE COMMAND (gh segment, `env`, standalone, `export`) are the same: they
move git's global config, whose `insteadOf` rewrites the remote (round 7). Inherited, they are judged.

`git` and `gh` before the gh segment are SAFE only for listed subcommands: `git config`, `git remote
set-url` and `gh repo set-default` rewrite what gh reads. A `git -c K=V` or `--config-env` is that git
process's own and does not reach gh. A segment redirecting into a file (`echo … >> .git/config`) is not
SAFE either; `/dev/null` and fds are.

Everything else is exit 3 ("cannot tell"):
- before the gh segment, once any segment is not SAFE: every segment that is not a plain `cd PATH` joined
  by `&&` or `;` (so `if`/`while`/`until`/`for`/`case`, subshells, brace groups, functions, `eval`,
  `source`, `.`, `pushd`/`popd`, `chdir`, `builtin`, `export`, `!`, `$x`, and any word not in SAFE), and a
  cd joined by `||`, `|` or `&`;
- a cd target with `$`, a backquote or `~user`, or an UNQUOTED glob or brace character (`* ? [ ] { }`, #1605: the shell
  expands them, so `cd [a]` runs in `a` and `cd {a,ab}` in `a` (bash) or nowhere (zsh), never in a directory named
  `[a]`; a quoted or backslash-escaped one is literal and is followed); `-` or any option (`-P`, `-L`); a missing directory; a
  relative path while CDPATH is set; a bare `cd` or one with two arguments; a redirect on a cd other than
  `>`, `>>`, `>&`;
- a gh that is no command word of the grammar (`sudo gh`, `bash -c "…"`, `env -C dir gh`, any `env`
  option);
- any GIT_* / GH_* variable, as above;
- an unbalanced quote before the gh.
"""
from __future__ import annotations

import os
import re
import shlex
import sys

ASSIGN = re.compile(r"\A[A-Za-z_][A-Za-z0-9_]*=")
# A CLASS, not a list (#1516, round 6): GIT_DIR, GIT_WORK_TREE, GIT_COMMON_DIR, GIT_CONFIG_GLOBAL (insteadOf),
# GIT_CONFIG_COUNT/KEY_n/VALUE_n, GIT_CONFIG_PARAMETERS and GH_REPO each send gh to another repository, and
# naming them one at a time left the next one open. Any GIT_* or GH_* variable is "cannot tell".
# HOME and XDG_CONFIG_HOME SET BY THE COMMAND move git's global config, whose `insteadOf` can rewrite the remote
# (#1516, round 7: `HOME=h gh …` reached B with real gh). Inherited, they are every session's own: not refused.
REPO_ENV = re.compile(r"\A((GIT|GH)_[A-Za-z0-9_]*|HOME|XDG_CONFIG_HOME)=")
# Proven not to change gh's target, with real gh (`gh browse -n` names the same repository with and without it),
# and set by the Claude Code harness itself: without the exemption every PR would go unchecked.
INHERITED_EXEMPT = {"GIT_EDITOR"}
OPS = re.compile(r"&&|\|\||;;&|;;|;&|<<<|&>>|&>|>>|>&|<&|<<|<>|>\||[;&|()<>]")
SEPS = {"&&", ";"}
CD_REDIRECTS = {">", ">>", ">&"}
# External programs, which cannot change this shell's directory, and builtins that do not. Chosen for
# what precedes a `gh pr create` in practice; a word not here before gh means "cannot tell".
SAFE = {"git", "gh", "echo", "printf", "test", "[", "true", "false", ":", "cat", "ls", "grep", "head",
        "tail", "wc", "sleep", "date", "pwd", "mkdir", "touch", "jq"}
# git and gh can REWRITE what gh reads (#1516, round 7, each shown with real gh): `git config [--global]
# url.X.insteadOf Y`, `git remote set-url`, `gh repo set-default`. So only these subcommands are SAFE. A
# `git -c K=V` / `--config-env=K=V` lives in that one git process and does not reach a later gh.
GIT_SAFE_SUB = {"status", "log", "diff", "show", "add", "commit", "push", "fetch", "pull", "rev-parse",
                "ls-files", "grep", "branch", "checkout", "switch", "stash", "tag", "restore", "describe"}
GIT_OPTS = {"-c": 2, "-C": 2, "--no-pager": 1, "-P": 1}  # plus --config-env=… / --git-dir=… / --work-tree=…
GH_SAFE_SUB = {"pr", "issue", "run", "auth", "api", "status", "search", "workflow"}
META = set(" \t\n;&|()<>")
# An UNQUOTED glob or brace character is expanded by the shell (#1605), but shlex strips the quotes, so by the time a cd target is read
# `[a]` and `"[a]"` look alike. `prepare()` therefore marks the unquoted ones with a private-use character that survives lexing, and
# `_target` refuses a path carrying it. A lone `[` or `]` is the `test` command and its closing word, not a glob: left as they are.
GLOB_CHARS = "*?[]{}"
GLOB_MARK = "\ue000"


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
            lone = word_start and (i + 1 >= n or cmd[i + 1] in META)     # `[` or `]` as a word of its own: `test`
            out.append(GLOB_MARK if c in GLOB_CHARS and not lone else c)
            i += 1
    return "".join(out)


def _target(args: list[str], here: str, home: str) -> str:
    if len(args) != 1:
        raise Unresolved("cd takes exactly one path here")
    a = args[0]
    # The `isdir` check below would refuse the mark too (no directory is named with it), so this line only NAMES the reason: it is why
    # no mutation is declared for it (#1605), and the marks `prepare()` leaves are what the fixtures and the mutations hold.
    if GLOB_MARK in a:
        raise Unresolved("cd to a path with an unquoted glob or brace character: the shell expands it")
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
    found = len(w) >= 3 and os.path.basename(w[0]) == "gh" and (
        (w[1] == "pr" and w[2] in ("create", "edit")) or (w[1] == "issue" and w[2] == "comment"))
    if found and any(REPO_ENV.match(x) for x in words[:len(words) - len(w)]):
        raise Unresolved("a GIT_* / GH_* / HOME / XDG_CONFIG_HOME set on the gh command can pick another repository")
    return found


def _safe(seg: list[str]) -> bool:
    """A segment that cannot move this shell's directory: empty, assignments only, or a SAFE command."""
    w = list(seg)
    while w and ASSIGN.match(w[0]):
        w.pop(0)
    if not w:                               # assignments alone persist in this shell, and so reach gh
        return not any(REPO_ENV.match(x) for x in seg)
    if w[0] == "git":
        a = w[1:]
        while a and a[0].startswith("-"):
            if a[0] in GIT_OPTS:
                del a[:GIT_OPTS[a[0]]]
            elif a[0].startswith(("--config-env=", "--git-dir=", "--work-tree=")):
                a.pop(0)
            else:
                return False
        return bool(a) and a[0] in GIT_SAFE_SUB
    if w[0] == "gh":
        return len(w) > 1 and w[1] in GH_SAFE_SUB
    return w[0] in SAFE


def _judge(done: list[tuple[list[str], bool, str, bool]], start: str, home: str) -> str:
    # A segment that writes a file (`echo … >> .git/config`) can rewrite what gh reads: not SAFE.
    if all(_safe(seg) and not writes for seg, _, _, writes in done):
        return start                        # nothing before gh can move the directory
    here = start
    for seg, clean, sep, _ in done:
        if sep not in SEPS or not clean:
            raise Unresolved(f"a segment joined by {sep!r}, or redirected, before gh")
        if not seg:
            continue                        # a blank line, a leading `;`
        if seg[0] != "cd":
            raise Unresolved(f"`{seg[0]}` before gh is neither a plain cd nor a SAFE command")
        here = _target(seg[1:], here, home)
    return here


def resolve(cmd: str, start: str, home: str) -> str:
    if any(k.startswith(("GIT_", "GH_")) and k not in INHERITED_EXEMPT for k in os.environ):
        raise Unresolved("a GIT_* / GH_* variable in the environment can pick gh's repository")
    lex = shlex.shlex(prepare(cmd).replace("\n", " ; "), posix=True, punctuation_chars=";&|()<>")
    lex.whitespace_split = True
    lex.commenters = ""                     # prepare() has dropped the real comments
    # The segments before gh: (words, only allowed cd redirects inside it, the separator after it, and
    # whether it redirects into a file other than /dev/null or an fd).
    done: list[tuple[list[str], bool, str, bool]] = []
    words: list[str] = []
    clean, redirect, writes = True, False, False
    try:
        for t in lex:                       # lazily: a quote left open AFTER the gh segment is never read
            if t and set(t) <= set(";&|()<>"):
                for op in OPS.findall(t):
                    if "<" in op or ">" in op:
                        clean = clean and op in CD_REDIRECTS
                        redirect = True
                    else:
                        done.append((words, clean, op, writes))
                        words, clean, redirect, writes = [], True, False, False
                continue
            if redirect:                    # the redirection's target, not an argument
                redirect = False
                writes = writes or not (t == "/dev/null" or t.isdigit() or t == "-")
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
