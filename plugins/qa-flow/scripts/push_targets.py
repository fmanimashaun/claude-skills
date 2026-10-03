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

import fnmatch
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
HEREDOC_BACKSLASH = re.compile(r"<<(-?)[ \t]*\\([A-Za-z_][A-Za-z0-9_]*)")      # <<\EOF: quoted, like <<'EOF'


def _heredoc_at(cmd: str, i: int) -> tuple[str, bool, bool, int] | None:
    """The heredoc operator at `i`: (delimiter, tabs stripped, body EXPANDS, end index), or None.
    A body expands `$( )` and backticks only when the delimiter is UNQUOTED; `<<'EOF'`, `<<"EOF"` and
    `<<\\EOF` all make it text (#1553)."""
    m = HEREDOC.match(cmd, i)
    if m:
        return m.group(3), m.group(1) == "-", m.group(2) == "", m.end()
    m = HEREDOC_BACKSLASH.match(cmd, i)
    if m:
        return m.group(2), m.group(1) == "-", False, m.end()
    return None

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
            op = _heredoc_at(cmd, i)
            if op:
                owed.append((op[0], op[1]))
                i = op[3]; continue
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


def _heredoc_substitutions(text: str, out: list[str]) -> None:
    """Append the `$( )` and backtick bodies in the text of an UNQUOTED heredoc: the shell expands
    them there, so `cat <<EOF` / `$(git push origin main)` / `EOF` pushes (#1553). A backslash
    escapes the character after it, so `\\$(...)` is text."""
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2; continue
        if c == "$" and text.startswith("(", i + 1):
            end, _ = _subst_scan(text, i + 1)
            out.append(text[i + 2:end - 1])
            i = end; continue
        if c == "`":
            j = i + 1
            while j < n and text[j] != "`":
                j += 2 if text[j] == "\\" else 1
            if j >= n:
                raise Unjudgeable("an unterminated backtick substitution")
            out.append(text[i + 1:j])
            i = j + 1; continue
        i += 1


def _placeholder(body: str) -> str:
    # `"$(git branch --show-current)"` is how agents spell "this branch": read it as HEAD, which
    # resolves to the branch it names, instead of refusing every such push (#1470 round 2).
    return "HEAD" if " ".join(body.split()) in CURRENT_BRANCH_IDIOMS else SUBST


ANSI_SIMPLE = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
               "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}


def ansi_c_end(cmd: str, i: int) -> tuple[str, int]:
    """Decode the ANSI-C string whose `$'` is at `i`: `(text bash produces, index past the closing ')`.
    `$'gh'`, `$'\\x67h'` and `$'PUT'` are the words gh, gh and PUT to bash; shlex read each as `$gh` etc.,
    a word that is no command, so the effect was missed (#1569). A NUL, or a string never closed, cannot
    be decoded with certainty: Unjudgeable."""
    j, n, out = i + 2, len(cmd), []
    while j < n:
        c = cmd[j]
        if c == "'":
            return "".join(out), j + 1
        if c != "\\" or j + 1 >= n:
            out.append(c); j += 1; continue
        d = cmd[j + 1]
        if d in ANSI_SIMPLE:
            out.append(ANSI_SIMPLE[d]); j += 2
        elif d in "01234567":
            k = j + 1
            while k < n and k < j + 4 and cmd[k] in "01234567":
                k += 1
            code = int(cmd[j + 1:k], 8) & 0xFF
            if code == 0:
                raise Unjudgeable("a NUL in an ANSI-C string ends the word in bash")
            out.append(chr(code)); j = k
        elif d in "xuU":
            width = {"x": 2, "u": 4, "U": 8}[d]
            k = j + 2
            while k < n and k < j + 2 + width and cmd[k] in "0123456789abcdefABCDEF":
                k += 1
            if k == j + 2:
                out.append("\\" + d); j += 2; continue          # `\x` with no digits stays text
            code = int(cmd[j + 2:k], 16)
            if code == 0:
                raise Unjudgeable("a NUL in an ANSI-C string ends the word in bash")
            out.append(chr(code)); j = k
        elif d == "c" and j + 2 < n:
            out.append(chr(ord(cmd[j + 2]) & 0x1F)); j += 3
        else:
            out.append("\\" + d); j += 2
    raise Unjudgeable("an unterminated ANSI-C $'...' string")


def strip_comments_and_heredocs(cmd: str, bodies: list[str] | None = None) -> str:
    """Bash's rules, not shlex's: `#` opens a comment only at the start of a word, outside quotes;
    a heredoc's body runs from the next newline to its delimiter line.

    Each `$( )`, `<( )`, `>( )` and backtick body is replaced by a placeholder word; when `bodies` is
    given, the text of every one is appended to it, so the caller can read what the shell will run
    there (#1550). Only the placeholder reaches the tokenizer."""
    out: list[str] = []
    i, n, quote = 0, len(cmd), ""
    pending: list[tuple[str, bool, bool]] = []    # heredoc delimiters awaiting the next newline
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
        if c == "$" and cmd.startswith("'", i + 1):
            text, i = ansi_c_end(cmd, i)
            out.append("'" + text.replace("'", "'\"'\"'") + "'")       # the decoded word, single-quoted
            continue
        if c == "$" and cmd.startswith('"', i + 1):
            i += 1; continue                    # `$"..."` is a plain double-quoted string to bash here
        if c in "'\"":
            quote = c; out.append(c); i += 1; continue
        if c == "#" and (i == 0 or cmd[i - 1] in " \t\n;&|()<>"):
            while i < n and cmd[i] != "\n":
                i += 1
            continue
        if c == "<" and cmd.startswith("<<", i) and not cmd.startswith("<<<", i) and not owed:
            op = _heredoc_at(cmd, i)
            if op:
                pending.append((op[0], op[1], op[2]))
                out.append(" "); i = op[3]; continue
        if c == "\n" and owed:
            end = cmd.find("\n", i + 1)
            line = cmd[i + 1:] if end == -1 else cmd[i + 1:end]
            delim, tabs = owed[0]
            if (line.lstrip("\t") if tabs else line) == delim:
                owed.pop(0)
        if c == "\n" and pending:
            out.append("\n"); i += 1
            for delim, tabs, expands in pending:
                text: list[str] = []
                while i < n:
                    end = cmd.find("\n", i)
                    line = cmd[i:] if end == -1 else cmd[i:end]
                    i = n if end == -1 else end + 1
                    if (line.lstrip("\t") if tabs else line) == delim:
                        break
                    text.append(line)
                if expands and bodies is not None:
                    _heredoc_substitutions("\n".join(text), bodies)   # the shell runs these (#1553)
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


WRAPPERS = {"sudo", "doas", "env", "command", "exec", "nohup", "time", "timeout", "nice", "builtin", "stdbuf",
            "setsid", "ionice", "xargs", "watch", "then", "do", "else", "if", "while", "until", "!", "{", "eval"}
EXPANSION = re.compile(r"\$\{[^}]*\}|\$[A-Za-z_@*#?0-9]\w*|\$__SUBST__|\{[^{}]*(?:,|\.\.)[^{}]*\}")


def check_words(seg: list[str]) -> None:
    """Words whose value only the shell knows, where they could BE the command (#1569). `$g push`,
    `g$x push` and `{gh,x} api` run gh; shlex sees a word that is no command and the effect is missed.
    `$IFS` splits a word into several, so `gh${IFS}api` is `gh api`. Either one is Unjudgeable."""
    for w in seg:
        if re.search(r"\$\{?IFS\b", w):
            raise Unjudgeable("$IFS splits a word at run time, so the command cannot be read")
    for w in seg:
        if re.fullmatch(r"[A-Za-z_]\w*=.*", w) or w in WRAPPERS or w.startswith("-") or re.fullmatch(r"\d+[smhd]?", w):
            continue
        last = w.rsplit("/", 1)[-1]
        if EXPANSION.search(last) or SUBST in last or (set(last) & set("*?[") and not os.path.exists(w)):
            pat = EXPANSION.sub("*", last.replace(SUBST, "*"))
            if any(fnmatch.fnmatchcase(name, pat) for name in ("gh", "git", "gh.exe", "git.exe")):
                raise Unjudgeable(f"the command word {w!r} is built by the shell and could be git or gh")
        break


def all_segments(cmd: str, depth: int = 0):
    """Every command segment, INCLUDING those inside `sh -c '<string>'`, `bash -lc`, and `eval ...`,
    parsed as commands in their own right (41's delta review of #1470)."""
    if depth > MAX_DEPTH:
        raise Unjudgeable("shell strings nested too deeply to read")
    bodies: list[str] = []
    for seg in segments(tokens(cmd, bodies)):
        check_words(seg)
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


def destinations(args: list[str], current: Callable[[bool], str | None],
                 srcs: list[str | None] | None = None, remote_out: list[str] | None = None) -> list[str]:
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
    if remote_out is not None and positional:
        remote_out.append(positional[0])        # the remote the push goes to (#1569)
    # `srcs`, when given, runs parallel to the result: the SOURCE of an explicit `<src>:<dst>` (the
    # commit that will land on main, #1569), else None (`main`, a bare push: judged at dev's tip).
    if not refspecs:
        dst = current(True) or current(False)
        if not dst:
            raise Unjudgeable("a push with no refspec, and the current branch could not be resolved")
        if srcs is not None:
            srcs.append(None)
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
        if srcs is not None:
            srcs.append(src if sep and src and dst else None)
    return out


def targets(cmd: str, current: Callable[[bool, str | None], str | None]) -> list[str]:
    return [dst for dst, _ in targets_detail(cmd, current)]


def _push_hits(seg: list[str], cwd, current) -> list[tuple[str, str | None, str | None, str | None]]:
    """`(dst, src, remote, workdir)` for each protected destination of a `git push` in `seg`."""
    parsed = push_args(seg)
    if parsed is None:
        return []
    args, workdir = parsed
    if cwd is UNKNOWN_DIR and not (workdir and os.path.isabs(workdir)):
        raise Unjudgeable("a cd that could not be followed, before a git push")
    where = workdir if workdir and (cwd is None or os.path.isabs(workdir)) else (
        os.path.join(cwd, workdir) if workdir else cwd)
    srcs: list[str | None] = []
    remote: list[str] = []
    dsts = destinations(args, lambda push, d=where: current(push, d), srcs, remote)
    hits = []
    for dst, src in zip(dsts, srcs + [None] * len(dsts)):
        if dst in PROTECTED or dst.startswith(("every branch", "the matching")):
            hits.append((dst, src, remote[0] if remote else None, where))
    return hits


def targets_detail(cmd: str, current: Callable[[bool, str | None], str | None]) -> list[tuple[str, str | None]]:
    """`targets`, each hit with the explicit source ref of its refspec (None when there is none)."""
    hits: list[tuple[str, str | None]] = []
    cwd: str | None = None                    # a prior `cd <dir>` moves where a bare push resolves
    for seg in all_segments(cmd):
        if seg[0] == "cd" and len(seg) == 2:
            cwd = seg[1] if cwd is None or os.path.isabs(seg[1]) else os.path.join(cwd, seg[1])
            continue
        hits += [(d, src) for d, src, _, _ in _push_hits(seg, cwd, current)]
    return hits


GH_MERGE_OPTS_WITH_VALUE = {"-b", "--body", "-F", "--body-file", "-t", "--subject",
                            "-A", "--author-email", "--match-head-commit"}


def pr_merge_selector(rest: list[str]) -> str:
    """The PR a `gh pr merge` names (number, URL or branch), or "" for the current branch's PR. `rest`
    is what follows `gh pr merge` with -R/--repo already taken out (`gh_parts`)."""
    sel, i = "", 0
    while i < len(rest):
        a = rest[i]
        if a in GH_MERGE_OPTS_WITH_VALUE:
            i += 2; continue
        if a.startswith("-"):
            i += 1; continue
        sel = a
        break
    if SUBST in sel or EXPANDS & set(sel):
        raise Unjudgeable(f"the PR {sel!r} is expanded by the shell")
    return sel


# #1569. The gate asked "does this command say `git push`/`gh pr merge` to main?" -- a question about
# SPELLING. A merge through GitHub's REST or GraphQL API, and publishing a release, have the same
# EFFECT with different spellings, and a promotion went through all of them. So `gh api` and
# `gh release create` are classified by what they DO. As everywhere in this file: only text the parser
# actually modelled may answer "no"; a file it cannot read, a stdin it cannot see, or a variable it
# cannot expand is Unjudgeable, which the hook denies.
API_OPTS_WITH_VALUE = {"-X", "--method", "-f", "--raw-field", "-F", "--field", "-H", "--header", "--input",
                       "-q", "--jq", "-t", "--template", "--hostname", "--cache", "-p", "--preview"}
API_SHORT_ATTACHED_CHARS = "XfFHqtp"
RELEASE_OPTS_WITH_VALUE = {"-t", "--title", "-n", "--notes", "-F", "--notes-file", "--target",
                           "--discussion-category", "--notes-start-tag", "-R", "--repo"}
GRAPHQL_REF_WRITES = ("updateRef", "createRef")
MAIN_WORD = re.compile(r"(?<![\w/.\-])(?:refs/heads/)?(main|master)(?![\w/.\-])")
NODE_ID = re.compile(r"^[A-Za-z0-9_=\-]+$")
PLACEHOLDER = re.compile(r"^(\{[a-z_]+\}|:[a-z_]+)$")


def _expanded(s: str) -> bool:
    return SUBST in s or "$" in s or "`" in s


def _read_file(path: str) -> str:
    if path == "-":
        raise Unjudgeable("gh api reads its body from stdin, which cannot be seen")
    if _expanded(path):
        raise Unjudgeable(f"the body file {path!r} is named by an expansion")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeError) as exc:
        raise Unjudgeable(f"gh api reads {path!r}, which cannot be read ({exc.__class__.__name__})") from exc


class ApiCall:
    """What `gh api ...` will send: methods it may use, the endpoint, and the body fields."""

    def __init__(self, rest: list[str]):
        self.method: str | None = None
        self.endpoint: str | None = None
        self.fields: list[tuple[str, str, bool]] = []      # (key, value, may-read-a-file)
        self.input: str | None = None
        self.hostname: str | None = None
        i = 0
        while i < len(rest):
            a, val = rest[i], None
            if a.startswith("--") and "=" in a:
                a, _, val = a.partition("=")
                i += 1
            elif a in API_OPTS_WITH_VALUE:
                if i + 1 >= len(rest):
                    raise Unjudgeable(f"gh api {a} with no value")
                val = rest[i + 1]
                i += 2
            elif a.startswith("-") and not a.startswith("--") and len(a) > 2:
                # A cluster of short flags (pflag): `-iXPUT` is -i -X PUT. Walk it to the first flag that
                # takes a value; the rest of the word, or the next word, is that value. Reading `-iXPUT`
                # as one unknown bool dropped the method and the call read as a GET (#1569).
                k = 1
                while k < len(a) and a[k] not in API_SHORT_ATTACHED_CHARS:
                    k += 1
                if k >= len(a):
                    i += 1; continue
                a, val = "-" + a[k], a[k + 1:]
                if val == "":
                    if i + 1 >= len(rest):
                        raise Unjudgeable(f"gh api {a} with no value")
                    val = rest[i + 1]; i += 1
                i += 1
            elif a.startswith("-"):
                i += 1; continue
            else:
                self.endpoint = self.endpoint if self.endpoint is not None else a
                i += 1; continue
            if a in ("-X", "--method"):
                self.method = val.upper()
            elif a in ("-f", "--raw-field", "-F", "--field"):
                key, _, v = val.partition("=")
                self.fields.append((key, v, a in ("-F", "--field")))
            elif a == "--input":
                self.input = val
            elif a == "--hostname":
                self.hostname = val
        if self.endpoint is None:
            raise Unjudgeable("gh api with no endpoint that could be read")

    def methods(self) -> set[str]:
        """Every method this call may use. An explicit one wins; gh otherwise sends POST when it has a
        body and GET when it has not. A field NAMED method / _method is a method override some proxies
        honour, so it is added to the set rather than trusted to be inert."""
        if self.method is not None:
            if _expanded(self.method):
                raise Unjudgeable("the gh api method is an expansion")
            out = {self.method}
        else:
            out = {"POST" if (self.fields or self.input) else "GET"}
        for key, v, _ in self.fields:
            if key.lower() in ("method", "_method") and v:
                out.add(v.upper())
        return out

    def value(self, key: str) -> str | None:
        found = None
        for k, v, readable in self.fields:
            if k == key:
                found = _read_file(v[1:]) if readable and v.startswith("@") else v
        if found is None and self.input is not None:
            data = self.json_input()
            if isinstance(data, dict) and key in data:
                found = str(data[key])
        return found

    def json_input(self):
        import json
        try:
            return json.loads(_read_file(self.input or "-"))
        except ValueError:
            return None

    def haystack(self) -> str:
        """Everything the call sends, as one text: the query, every field (files read), the --input file."""
        parts = []
        for _, v, readable in self.fields:
            parts.append(_read_file(v[1:]) if readable and v.startswith("@") else v)
        if self.input is not None:
            raw = _read_file(self.input)
            parts.append(raw)
            data = self.json_input()
            # The JSON file escapes its quotes (`\"PR_kw1\"`); the decoded query is what GraphQL reads.
            if isinstance(data, dict) and isinstance(data.get("query"), str):
                parts.append(data["query"])
        return "\n".join(parts)

    def path(self) -> str:
        from urllib.parse import unquote, urlsplit
        ep = unquote(self.endpoint or "")
        if "://" in ep:
            ep = urlsplit(ep).path
        return ep.split("?", 1)[0].strip("/")


def _repo_arg(owner: str | None, repo: str | None) -> str:
    if not owner or PLACEHOLDER.match(owner) or not repo or PLACEHOLDER.match(repo):
        return "-"
    if _expanded(owner + repo):
        raise Unjudgeable("the repository is named by an expansion")
    return f"{owner}/{repo}"


def _graphql_id(text: str, call: ApiCall, arg: str) -> str:
    """What a mutation passes as `arg` (`pullRequestId`, `refId`, `oid`, `name`): a literal, or a variable
    the call supplies. `-` when it cannot be read, which the hook resolves or denies."""
    m = re.search(arg + r'\s*:\s*"([^"]+)"', text)
    if m:
        return m.group(1)
    m = re.search(arg + r"\s*:\s*\$(\w+)", text)
    if m:
        v = call.value(m.group(1))
        if v is None:
            data = call.json_input() if call.input else None
            if isinstance(data, dict) and isinstance(data.get("variables"), dict):
                v = data["variables"].get(m.group(1))
        if v and NODE_ID.match(str(v).replace("/", "")):
            return str(v)
    return "-"


def _token(v: str | None) -> str:
    """A value the hook can carry on a line: one word with no expansion in it, else `-` (unknown)."""
    return v if v and not _expanded(v) and not (EXPANDS & set(v)) and not re.search(r"\s", v) else "-"


def _graphql_effects(call: ApiCall) -> list[str]:
    text = call.haystack()
    # `$` is GraphQL's own variable syntax (`query($id: ID!)`), so only a real shell substitution (or a
    # backtick) means the document is built at run time. Reading it as an expansion would deny every
    # parameterised read.
    if SUBST in text or "`" in text:
        raise Unjudgeable("a GraphQL document built by the shell cannot be read")
    out = []
    if "mergePullRequest" in text:
        out.append(f"GQL_PR {_graphql_id(text, call, 'pullRequestId')}")
    if "updateRef" in text:
        out.append(f"GQL_REF {_graphql_id(text, call, 'refId')} {_token(_graphql_id(text, call, 'oid'))}")
    if "createRef" in text:
        name = _graphql_id(text, call, "name")
        if name == "-" or branch_of(name) in PROTECTED:
            out.append(f"API_REF {_token(_graphql_id(text, call, 'oid'))}")
    return out


def gh_api_effects(rest: list[str]) -> tuple[list[str], str]:
    """`(lines, repo)` for one `gh api <rest>`: API_PR_MERGE <n>, API_MERGE <head>, API_REF <sha>,
    GQL_PR <id>, GQL_REF <id> <oid>, RELEASE <tag> <target>, RELEASE_ID <id>; `repo` is the one a literal
    `repos/<o>/<r>/` path names, else `-`. `-` in a line means unknown, which the hook denies (#1569:
    a ref write or a merge is judged by the commit it WRITES -- `sha`, `head`, `oid` -- not by dev)."""
    call = ApiCall(rest)
    if call.hostname:
        raise Unjudgeable("gh api --hostname names another GitHub host")
    path = call.path()
    methods = call.methods()
    if path == "graphql":
        return (_graphql_effects(call) if methods - {"GET", "HEAD"} else []), "-"
    if methods <= {"GET", "HEAD", "OPTIONS"}:
        return [], "-"
    rm = re.match(r"repos/([^/]+)/([^/]+)/", path)
    repo = _repo_arg(rm.group(1), rm.group(2)) if rm else "-"
    m = re.fullmatch(r"(?:repos/([^/]+)/([^/]+)/)?pulls/([^/]+)/merge", path)
    if m and "PUT" in methods:
        n = m.group(3)
        return [f"API_PR_MERGE {'-' if _expanded(n) or not n.isdigit() else n}"], repo
    # A write whose route is built by the shell: unreadable if the expansion could BE the resource
    # (`repos/o/r/$X`, `$URL`), or if the readable part already names one that matters.
    if _expanded(path) and (re.search(r"merge|refs|releases", path)
                            or any(_expanded(part) for part in path.split("/")[:4])):
        raise Unjudgeable("a gh api write whose path is built by the shell")
    if re.fullmatch(r"(?:repos/[^/]+/[^/]+/)?merges", path) and "POST" in methods:
        base = call.value("base")
        if base is None or _expanded(base) or branch_of(base) in PROTECTED:
            return [f"API_MERGE {_token(call.value('head'))}"], repo
        return [], repo
    m = re.fullmatch(r"(?:repos/[^/]+/[^/]+/)?git/refs/(.+)", path)
    if m and methods & {"PATCH", "POST", "PUT"}:
        ref = m.group(1)
        if _expanded(ref) or branch_of(ref) in PROTECTED:
            return [f"API_REF {_token(call.value('sha'))}"], repo
        return [], repo
    if re.fullmatch(r"(?:repos/[^/]+/[^/]+/)?git/refs", path) and methods & {"PATCH", "POST", "PUT"}:
        ref = call.value("ref")
        if ref is None or _expanded(ref) or branch_of(ref) in PROTECTED:
            return [f"API_REF {_token(call.value('sha'))}"], repo
        return [], repo
    m = re.fullmatch(r"(?:repos/([^/]+)/([^/]+)/)?releases/([^/]+)", path)
    if m and methods & {"PATCH", "POST", "PUT"}:
        draft = call.value("draft")
        if draft is not None and _draft_off(draft):
            rid = m.group(3)
            if not rid.isdigit():
                raise Unjudgeable(f"the release id {rid!r} could not be read")
            return [f"RELEASE_ID {rid}"], repo
        return [], repo
    if re.fullmatch(r"(?:repos/[^/]+/[^/]+/)?releases", path) and "POST" in methods:
        tag, target = call.value("tag_name"), call.value("target_commitish")
        return [_release_line(tag, target)], repo
    return [], repo


def _release_line(tag: str | None, target: str | None) -> str:
    for v in (tag, target):
        if v and (_expanded(v) or EXPANDS & set(v) or " " in v):
            raise Unjudgeable(f"the release tag/target {v!r} is expanded by the shell")
    return f"RELEASE {tag or '-'} {target or '-'}"


def release_creates(rest: list[str]) -> list[str]:
    tag, target, i = None, None, 0
    while i < len(rest):
        a = rest[i]
        if a.startswith("--target="):
            target = a.partition("=")[2]; i += 1; continue
        if a == "--target":
            if i + 1 >= len(rest):
                raise Unjudgeable("--target with no value")
            target = rest[i + 1]; i += 2; continue
        if a in RELEASE_OPTS_WITH_VALUE:
            i += 2; continue
        if a.startswith("-"):
            i += 1; continue
        if tag is None:
            tag = a
        i += 1
    return [_release_line(tag, target)]


def _draft_off(v: str) -> bool:
    if _expanded(v):
        raise Unjudgeable("the release draft flag is an expansion")
    return v.lower() in ("false", "f", "0")


def release_edits(rest: list[str]) -> list[str]:
    """`gh release edit <tag> --draft=false` PUBLISHES a draft: gated like `create` (#1569). Other edits
    publish nothing. `--draft` alone, or `--draft=true`, keeps it a draft."""
    tag, target, off, i = None, None, False, 0
    while i < len(rest):
        a = rest[i]
        if a.startswith("--draft="):
            off = _draft_off(a.partition("=")[2]); i += 1; continue
        if a.startswith("--target="):
            target = a.partition("=")[2]; i += 1; continue
        if a == "--target":
            if i + 1 >= len(rest):
                raise Unjudgeable("--target with no value")
            target = rest[i + 1]; i += 2; continue
        if a in RELEASE_OPTS_WITH_VALUE or a in ("--tag", "--verify-tag"):
            i += 2 if a != "--verify-tag" else 1; continue
        if a.startswith("-"):
            i += 1; continue
        if tag is None:
            tag = a
        i += 1
    if not off:
        return []
    if tag is None:
        raise Unjudgeable("gh release edit with no tag that could be read")
    line = _release_line(tag, target)
    return ["RELEASE_EDIT" + line[len("RELEASE"):]]


REPO_NAME = re.compile(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$")


def _named_repo(v: str) -> str:
    """`OWNER/REPO` as a gh flag or GH_REPO names it. A host-qualified name, a URL or an expansion is
    a repository this gate cannot pair with a stamp: Unjudgeable."""
    if _expanded(v) or EXPANDS & set(v) or not REPO_NAME.match(v):
        raise Unjudgeable(f"the repository {v!r} could not be read as OWNER/REPO")
    return v


def gh_parts(seg: list[str], j: int) -> tuple[list[str], list[str], str | None]:
    """For the `gh` at seg[j]: `(names, rest, repo)`. `names` is the subcommand path (`pr merge`,
    `release create`, or just `api`), `rest` every other word in order, `repo` what -R/--repo names.
    cobra accepts a flag before the subcommand (`gh pr -R o/r merge 7`), so the names are the first
    non-flag words, not the words next to `gh` (#1569)."""
    args, names, rest, repo, i = seg[j + 1:], [], [], None, 0
    while i < len(args):
        a = args[i]
        if a in ("-R", "--repo"):
            if i + 1 >= len(args):
                raise Unjudgeable("gh -R with no value")
            repo = _named_repo(args[i + 1]); i += 2; continue
        if a.startswith("--repo="):
            repo = _named_repo(a.partition("=")[2]); i += 1; continue
        if a.startswith("-R") and not a.startswith("--") and len(a) > 2:
            repo = _named_repo(a[2:]); i += 1; continue
        if not a.startswith("-") and len(names) < (1 if names[:1] == ["api"] else 2):
            names.append(a); i += 1; continue
        rest.append(a); i += 1
    return names, rest, repo


UNKNOWN_DIR = object()


def ctx_segments(cmd: str):
    """Every segment with the context it runs in: `(seg, cwd, gh_repo)`. `cwd` follows a prior `cd`
    (None = where the hook runs; UNKNOWN_DIR when a `cd` could not be followed); `gh_repo` is GH_REPO as
    the segment sees it -- an assignment prefix, `env GH_REPO=`, or an earlier `export GH_REPO=` (#1569:
    each makes gh act on a repository other than the one whose stamp the hook reads)."""
    cwd, env_repo = None, None
    for seg in all_segments(cmd):
        seg_repo = env_repo
        for w in seg:
            if w.startswith("GH_REPO="):
                v = w.partition("=")[2]
                seg_repo = _named_repo(v) if v else None
                if seg[0] in ("export",) or all(re.fullmatch(r"[A-Za-z_]\w*=.*", x) for x in seg):
                    env_repo = seg_repo
        if seg[0] in ("cd", "pushd"):
            if len(seg) == 2 and seg[1] != "-" and not _expanded(seg[1]):
                cwd = seg[1] if cwd is None or cwd is UNKNOWN_DIR or os.path.isabs(seg[1]) else os.path.join(cwd, seg[1])
            else:
                cwd = UNKNOWN_DIR
            continue
        yield seg, cwd, seg_repo


def _dir_word(cwd, workdir: str | None = None) -> str:
    """The directory an effect runs in, as one word for the hook (`-` = where the hook runs)."""
    if cwd is UNKNOWN_DIR:
        raise Unjudgeable("a cd that could not be followed, before a command that merges or publishes")
    d = workdir if workdir and (cwd is None or os.path.isabs(workdir)) else (
        os.path.join(cwd, workdir) if workdir and cwd else (workdir or cwd))
    if not d:
        return "-"
    if re.search(r"\s", d) or _expanded(d) or EXPANDS & set(d):
        raise Unjudgeable(f"the directory {d!r} could not be carried to the hook")
    return d


MERGE_OPTS_WITH_VALUE = {"-m", "--message", "-F", "--file", "-s", "--strategy", "-X", "--strategy-option",
                         "--into-name", "-S", "--cleanup"}


def merge_refs(args: list[str]) -> list[str] | None:
    """The commits a `git merge` brings in, as the refs it names: `[]` = none named (it merges the
    upstream), `["MERGE_HEAD"]` for --continue, None for --abort/--quit (nothing is merged)."""
    refs, i = [], 0
    while i < len(args):
        a = args[i]
        if a in ("--abort", "--quit"):
            return None
        if a == "--continue":
            return ["MERGE_HEAD"]
        if a == "--":
            refs += args[i + 1:]
            break
        if a in MERGE_OPTS_WITH_VALUE:
            i += 2; continue
        if a.startswith("-"):
            i += 1; continue
        refs.append(a); i += 1
    for r in refs:
        if SUBST in r or EXPANDS & set(r) or r.startswith("~"):
            raise Unjudgeable(f"the merge ref {r!r} is expanded by the shell")
    return refs


def effects(cmd: str, current) -> list[tuple[str, str, str]]:
    """`(line, repo, dir)` for everything in `cmd` that merges into main or publishes. `repo` is the
    repository the command acts on when it says so (`-R`, GH_REPO, a `repos/o/r/` path, a git remote as
    `remote:<name>`), else `-`; `dir` is where it runs after a `cd` or `git -C`, else `-`."""
    out: list[tuple[str, str, str]] = []
    for seg, cwd, env_repo in ctx_segments(cmd):
        # `PUSH_REF <src>` (#1569): an explicit `<src>:main` is judged by the commit it pushes, not dev's tip.
        for dst, src, remote, where in _push_hits(seg, cwd, current):
            out.append((f"PUSH_REF {src}" if src else f"PUSH_MAIN {dst}", f"remote:{remote}" if remote else "-",
                        _dir_word(None, where)))
        parsed = git_verb(seg, "merge")
        if parsed is not None:
            refs = merge_refs(parsed[0])
            if refs is not None:
                out.append((("GIT_MERGE " + " ".join(refs)).rstrip(), "-", _dir_word(cwd, parsed[1])))
        for j, word in enumerate(seg):
            if not is_command(word, {"gh"}):
                continue
            names, rest, repo = gh_parts(seg, j)
            d = _dir_word(cwd)
            if names == ["pr", "merge"]:
                out.append((f"PR_MERGE {pr_merge_selector(rest)}".rstrip(), repo or env_repo or "-", d))
            elif names[:1] == ["api"]:
                lines, prepo = gh_api_effects(rest)
                out += [(ln, prepo if prepo != "-" else (env_repo or "-"), d) for ln in lines]
            elif names == ["release", "create"]:
                out += [(ln, repo or env_repo or "-", d) for ln in release_creates(rest)]
            elif names == ["release", "edit"]:
                out += [(ln, repo or env_repo or "-", d) for ln in release_edits(rest)]
    return out


def classify(cmd: str, current) -> list[str]:
    """The hook's one question, answered from the RAW command: one `CTX <repo> <dir>` line, then the
    effect it applies to: PUSH_MAIN <dst>, PUSH_REF <src>, GIT_MERGE [<ref>...], PR_MERGE <sel>, and
    the `gh api` / `gh release` effects (API_PR_MERGE, API_MERGE, API_REF, GQL_PR, GQL_REF, RELEASE,
    RELEASE_EDIT, RELEASE_ID)."""
    lines: list[str] = []
    seen: set[tuple[str, str, str]] = set()
    for eff in effects(cmd, current):
        if eff not in seen:
            seen.add(eff)
            lines += [f"CTX {eff[1]} {eff[2]}", eff[0]]
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

    def cls(cmd, cur):
        return [ln for ln in classify(cmd, cur) if not ln.startswith("CTX ")]

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
        # (#1553) an UNQUOTED heredoc delimiter makes the shell expand `$( )` and backticks in the body;
        # a QUOTED one (<<'EOF', <<"EOF", <<\EOF) makes the body text
        ('cat <<EOF\n$(git push origin main)\nEOF', on_feature, True),
        ('cat <<EOF\n`git push origin main`\nEOF', on_feature, True),
        ('cat <<-EOF\n\t$(git push origin main)\n\tEOF', on_feature, True),
        ('x=$(cat <<EOF\n$(git push origin main)\nEOF\n)', on_feature, True),
        ("cat <<'EOF'\n$(git push origin main)\nEOF", on_feature, False),
        ('cat <<"EOF"\n$(git push origin main)\nEOF', on_feature, False),
        ('cat <<\\EOF\n$(git push origin main)\nEOF', on_feature, False),
        ('cat <<\\EOF\ngit push origin main\nEOF', on_feature, False),
        ('cat <<EOF\n\\$(git push origin main)\nEOF', on_feature, False),
        ('cat <<EOF\n$(git rev-parse HEAD)\nEOF\ngit push origin fix/x', on_feature, False),
        ('cat <<EOF\ngit push origin main\nEOF', on_feature, False),
        ('git commit -m "$(cat <<EOF\nit\'s done, git push origin main later\nEOF\n)"', on_feature, False),
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
                      ("git merge dev", ["GIT_MERGE dev"]), ("sudo git merge dev", ["GIT_MERGE dev"]),
                      ('git commit -m "merge it" && gh pr list', []),
                      ("git push origin main", ["PUSH_MAIN main"])):
        try:
            got = cls(cmd, on_feature)
        except Unjudgeable as exc:
            got = [f"unjudgeable: {exc}"]
        if got != want:
            failures.append(f"classify {cmd!r}: expected {want}, got {got}")
    for cmd in ("gh pr merge -R $R 5", "gh pr merge $N"):
        try:
            cls(cmd, on_feature)
            failures.append(f"classify {cmd!r}: must be unjudgeable (the hook denies)")
        except Unjudgeable:
            pass
    # #1569: `gh api` and `gh release create`, classified by EFFECT.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        qfile, jfile = os.path.join(td, "q.graphql"), os.path.join(td, "q.json")
        mut = 'mutation { mergePullRequest(input:{pullRequestId:"PR_kw1"}) { clientMutationId } }'
        with open(qfile, "w", encoding="utf-8") as fh:
            fh.write(mut)
        with open(jfile, "w", encoding="utf-8") as fh:
            fh.write('{"query": ' + __import__("json").dumps(mut) + "}")
        api_cases = [
            ("gh api -X PUT repos/{owner}/{repo}/pulls/1200/merge -f merge_method=merge", ["API_PR_MERGE 1200"]),
            ("gh api --method=PUT repos/o/r/pulls/5/merge", ["API_PR_MERGE 5"]),
            ("gh api repos/o/r/pulls/5/merge --method PUT", ["API_PR_MERGE 5"]),
            ("gh api -XPUT /repos/o/r/pulls/5/merge", ["API_PR_MERGE 5"]),
            ("gh api -X PUT https://api.github.com/repos/o/r/pulls/5/merge", ["API_PR_MERGE 5"]),
            ("gh api -X PUT repos/o/r/pulls/5/merge -f method=GET", ["API_PR_MERGE 5"]),
            ("gh api repos/o/r/pulls/5/merge -f _method=PUT -f x=1", ["API_PR_MERGE 5"]),
            ("GH_TOKEN=x gh api -X PUT repos/o/r/pulls/5/merge", ["API_PR_MERGE 5"]),
            ("bash -c 'gh api -X PUT repos/o/r/pulls/5/merge'", ["API_PR_MERGE 5"]),
            ('eval "gh api -X PUT repos/o/r/pulls/5/merge"', ["API_PR_MERGE 5"]),
            ("x=$(gh api -X PUT repos/o/r/pulls/5/merge)", ["API_PR_MERGE 5"]),
            ("x=`gh api -X PUT repos/o/r/pulls/5/merge`", ["API_PR_MERGE 5"]),
            ("cat <<EOF\n$(gh api -X PUT repos/o/r/pulls/5/merge)\nEOF", ["API_PR_MERGE 5"]),
            ("cat <<'EOF'\ngh api -X PUT repos/o/r/pulls/5/merge\nEOF", []),
            ("gh api repos/o/r/merges -f base=main -f head=dev", ["API_MERGE dev"]),
            ("gh api repos/o/r/merges -f base=dev -f head=x", []),
            ("gh api -X PATCH repos/o/r/git/refs/heads/main -f sha=a", ["API_REF a"]),
            ("gh api -X PATCH repos/o/r/git/refs/heads/dev -f sha=a", []),
            ("gh api repos/o/r/git/refs -f ref=refs/heads/master -f sha=a", ["API_REF a"]),
            ("gh api repos/o/r/git/refs -f ref=refs/heads/feature/main -f sha=a", []),
            ("gh api -X PATCH repos/o/r/git/refs/heads%2Fmain -f sha=a", ["API_REF a"]),
            ("gh api -f query='mutation { mergePullRequest(input:{pullRequestId:\"PR_kw1\"}) { x } }' graphql", ["GQL_PR PR_kw1"]),
            ("gh api graphql -f query='mutation($id:ID!){ mergePullRequest(input:{pullRequestId:$id}) { x } }' -f id=PR_v", ["GQL_PR PR_v"]),
            (f"gh api graphql -F query=@{qfile}", ["GQL_PR PR_kw1"]),
            (f"gh api graphql --input {jfile}", ["GQL_PR PR_kw1"]),
            ("gh api graphql -f query='mutation { updateRef(input:{refId:\"R1\", oid:\"a\"}) { x } }'", ["GQL_REF R1 a"]),
            ("gh api graphql -f query='mutation { updateRef(input:{refId:\"R1\"}) { x } }' -f name=refs/heads/main", ["GQL_REF R1 -"]),
            ("gh api graphql -f query='mutation { createRef(input:{name:\"refs/heads/main\", oid:\"c1\"}) { x } }'", ["API_REF c1"]),
            ("gh api graphql -f query='query($o:String!){ repository(owner:$o) { id } }' -f o=x", []),
            ("gh api repos/o/r/pulls/5", []),
            ("gh api -X GET repos/o/r/pulls/5/merge", []),
            ("gh api repos/o/r/pulls/5/merge", []),
            ("gh api -X POST repos/o/r/issues/1/comments -f body=hi", []),
            ("gh api repos/o/r/releases", []),
            ("gh api repos/o/r/releases -f tag_name=v1 -f target_commitish=main", ["RELEASE v1 main"]),
            ("gh api -X POST repos/{owner}/{repo}/releases -f tag_name=v1", ["RELEASE v1 -"]),
            ("gh release create v1.0.1 --target main --notes 'a b'", ["RELEASE v1.0.1 main"]),
            ("gh release create v1.0.1 --target=abc123 -t Title dist/x.skill", ["RELEASE v1.0.1 abc123"]),
            ("gh release create v1.0.1", ["RELEASE v1.0.1 -"]),
            ("timeout 60 gh release create v1 --draft", ["RELEASE v1 -"]),
            ("gh release list", []),
            ("gh release view v1", []),
        ]
        for cmd, want in api_cases:
            try:
                got = cls(cmd.replace("\\n", "\n"), on_feature)
            except Unjudgeable as exc:
                got = [f"unjudgeable: {exc}"]
            if got != want:
                failures.append(f"classify {cmd!r}: expected {want}, got {got}")
        # Could not judge -> the hook denies. A file it cannot read is never "no merge".
        unreadable = [
            f"gh api graphql --input {td}/missing.json", f"gh api graphql -F query=@{td}/missing.graphql",
            f"gh api graphql --input={td}/missing.json", f"gh api graphql -F query=@{td}",
            "gh api graphql --input -", "gh api graphql -F query=@-",
            "gh api -X PUT repos/o/r/pulls/$N/merge -f x=1 --input", "gh api -X $M repos/o/r/pulls/5/merge",
            "gh api -X PATCH repos/o/r/git/refs/heads/$B", "gh api graphql -f query=\"$(cat q)\"",
            "gh api -X POST repos/o/r/$X -f a=b", "gh release create $TAG", "gh release create v1 --target $T",
            "gh api",
        ]
        for cmd in unreadable:
            try:
                got = cls(cmd, on_feature)
                if cmd in ("gh api -X PATCH repos/o/r/git/refs/heads/$B",) and got == ["API_MAIN"]:
                    continue                  # answered closed: an unknown ref IS treated as main
                failures.append(f"classify {cmd!r}: must be unjudgeable or main-ward, got {got}")
            except Unjudgeable:
                pass
        api_total = len(api_cases) + len(unreadable)
    # #1569: a merge or push of an explicit ref is judged by that ref's commit; publishing by EDIT is gated.
    ref_cases = [
        ("git merge dev", ["GIT_MERGE dev"]), ("git merge", ["GIT_MERGE"]), ("git merge --continue", ["GIT_MERGE MERGE_HEAD"]),
        ("git merge --abort", []), ("git merge --quit", []),
        ("git merge -m 'a b' --no-ff feat other", ["GIT_MERGE feat other"]),
        ("git merge -s ours -X theirs feat", ["GIT_MERGE feat"]),
        ("timeout 60 git merge feat", ["GIT_MERGE feat"]), ("x=$(git merge feat)", ["GIT_MERGE feat"]),
        ("bash -c 'git merge feat'", ["GIT_MERGE feat"]),
        ("git push origin dev:main", ["PUSH_REF dev"]), ("git push origin +hotfix:master", ["PUSH_REF hotfix"]),
        ("git push origin HEAD:refs/heads/main", ["PUSH_REF HEAD"]),
        ("git push origin abc123:refs/heads/main feat:feat", ["PUSH_REF abc123"]),
        ("git push origin main", ["PUSH_MAIN main"]), ("git push origin :main", ["PUSH_MAIN main"]),
        ("git push origin dev:feature/x", []),
        ("gh release edit v1 --draft=false", ["RELEASE_EDIT v1 -"]),
        ("gh release edit v1 --draft=false --target abc", ["RELEASE_EDIT v1 abc"]),
        ("gh release edit v1 --draft=f -n x", ["RELEASE_EDIT v1 -"]),
        ("gh release edit v1 --draft", []), ("gh release edit v1 --draft=true", []), ("gh release edit v1 -n x", []),
        ("bash -c 'gh release edit v1 --draft=false'", ["RELEASE_EDIT v1 -"]),
        ("gh api -X PATCH repos/o/r/releases/9 -F draft=false", ["RELEASE_ID 9"]),
        ("gh api --method=PATCH repos/{owner}/{repo}/releases/9 -f draft=false", ["RELEASE_ID 9"]),
        ("gh api -X PATCH repos/o/r/releases/9 -f name=x", []),
        ("gh api -X PATCH repos/o/r/releases/9 -F draft=true", []),
    ]
    for cmd, want in ref_cases:
        try:
            got = cls(cmd, on_feature)
        except Unjudgeable as exc:
            got = [f"unjudgeable: {exc}"]
        if got != want:
            failures.append(f"classify {cmd!r}: expected {want}, got {got}")
    for cmd in ("git merge $B", "git merge feat/{a,b}", "gh release edit --draft=false", "gh release edit v1 --draft=$D",
                "gh release edit $T --draft=false",
                "gh api -X PATCH repos/o/r/releases/$I -F draft=false", "gh api -X PATCH repos/o/r/releases/latest -F draft=false",
                "gh api -X PATCH repos/o/r/releases/9 -F draft=$D"):
        try:
            cls(cmd, on_feature)
            failures.append(f"classify {cmd!r}: must be unjudgeable (the hook denies)")
        except Unjudgeable:
            pass
    api_total += len(ref_cases) + 9
    # "no" must not share an exit code with a crash: python's uncaught-exception exit is 1.
    if NO in (0, 1) or UNJUDGEABLE == NO:
        failures.append(f"exit codes: NO={NO} must differ from 0, 1 (a crash) and UNJUDGEABLE")
    total = len(cases) + 5 + 12 + api_total
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
