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
        if c == "<" and cmd.startswith("<<", i) and not cmd.startswith("<<<", i) and not owed and (i == 0 or cmd[i - 1] != "<"):
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


def tokens_lexer(text: str, posix: bool):
    """The one lexer: `tokens` reads words with it, and `note_home_words` reads the SAME text with `posix=False` to keep the quotes."""
    lex = shlex.shlex(text, posix=posix, punctuation_chars=";&|()<>\n")
    lex.whitespace = " \t\r"          # a newline separates commands; it is not mere whitespace
    lex.whitespace_split = True
    lex.commenters = ""               # removed above, by bash's rule
    return lex


# WHICH HOME-DIRECTORY WORDS THE SHELL WILL REALLY EXPAND (#1764 review). shlex drops quotes, so `~/x`, `'~/x'`, `"~/x"` and `\\~/x` all arrive as the word `~/x`, but only the
# unquoted one is expanded by the shell: git is handed a literal directory named `~` for the others, and a hook that expanded them anyway would judge HEAD in a checkout the push
# never touches. `note_home_words` reads the RAW text with its quotes: a word is expandable only if EVERY spelling of it is: `~` and `$HOME` unquoted, or `$HOME` inside double
# quotes (which the shell expands); a single-quoted, backslash-escaped or `"~..."` spelling makes the word unexpandable wherever else it appears.
HOME_WORD = re.compile(r"(~|\$HOME|\$\{HOME\})")
HOME_GOOD: set[str] = set()
HOME_BAD: set[str] = set()


def note_home_words(text: str) -> None:
    try:
        raw_tokens = list(tokens_lexer(text, posix=False))
    except ValueError:
        return
    for raw in raw_tokens:
        try:
            parts = shlex.split(raw)
        except ValueError:
            continue
        if len(parts) != 1 or not HOME_WORD.match(parts[0]):
            continue
        word = parts[0]
        plain = not re.search(r"""["'\\]""", raw)
        double = len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"' and not re.search(r"""["'\\]""", raw[1:-1]) and word.startswith("$")
        (HOME_GOOD if plain or double else HOME_BAD).add(word)


def tokens(cmd: str, bodies: list[str] | None = None) -> list[str]:
    stripped = strip_comments_and_heredocs(cmd, bodies)
    note_home_words(stripped)
    lex = tokens_lexer(stripped, posix=True)
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
        if t and set(t) <= SEPARATOR_CHARS:    # a NON-EMPTY run of separator characters: `set("") <= anything`, so an empty-string argument (`''`) used to END the command (#1768)
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


def home_expanded(word: str) -> str:
    """A directory word with a LEADING `~`, `$HOME` or `${HOME}` expanded, as the shell will have by the time git runs (#1764).

    The hook is handed the RAW command, which nothing has expanded yet, so `git -C ~/proj push` and `cd ~/proj && git push` name a directory
    that does not exist when read as text: HEAD could not be resolved there and the gate refused a feature-branch push. Only the home
    directory is expanded, and only at the start of the word (`~`, `~/x`, `$HOME`, `$HOME/x`, `${HOME}/x`): `~user`, any other variable, a
    substitution, and a `~` inside a word are left exactly as they were, so they stay unresolved and the caller still fails closed. With no
    HOME in the environment nothing is expanded, for the same reason."""
    home = os.environ.get("HOME")
    if not home or not os.path.isabs(home) or word not in HOME_GOOD or word in HOME_BAD:
        return word
    for prefix in ("${HOME}", "$HOME", "~"):
        if word == prefix or word.startswith(prefix + "/"):
            return home + word[len(prefix):]
    return word


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
                    workdir = home_expanded(seg[i + 1])
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
# #1770: set while `all_segments` reads a command that DEFINES a shell function. A body is judged where it is written, as if it ran there, whether or
# not (or when, or how often) the name is called; `effects` then refuses the state a call site could change under that model.
FUNCS = [False]


WRAPPERS = {"sudo", "doas", "env", "command", "exec", "nohup", "time", "timeout", "nice", "builtin", "stdbuf",
            "setsid", "ionice", "xargs", "watch", "then", "do", "else", "if", "while", "until", "!", "{", "eval"}
EXPANSION = re.compile(r"\$\{[^}]*\}|\$[A-Za-z_@*#?0-9]\w*|\$__SUBST__|\{[^{}]*(?:,|\.\.)[^{}]*\}")


def check_words(seg: list[str]) -> None:
    """Words whose value only the shell knows, where they could BE the command (#1569). `$g push`,
    `g$x push` and `{gh,x} api` run gh; shlex sees a word that is no command and the effect is missed.
    `$IFS` splits a word into several, so `gh${IFS}api` is `gh api`. Either one is Unjudgeable."""
    for w in seg:
        if re.search(r"\$\{?IFS", w):
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


def _trap_strings(seg: list[str]) -> list[str]:
    """#1781: the command string of EVERY `trap` word in `seg`, wherever it stands. `trap '<command>' SIGNAL...` runs the string later, at exit or on a
    signal. An allowlist of the prefixes that may come before `trap` (`sudo -u r`, `exec -a x`, `nice -n 5`, `timeout 5`, `builtin`, `{` ...) cannot be
    completed, so no position is assumed: a word that is `trap` is read as the builtin, and `echo trap 'git push origin main'` is over-blocked on
    purpose (a release gate fails closed). `-p`, `-l` and `--` are options; `-` and `''` carry no command."""
    out: list[str] = []
    for k, w in enumerate(seg):
        if w.rsplit("/", 1)[-1] != "trap":
            continue
        rest = [a for a in seg[k + 1:] if a not in ("--", "-p", "-l")]
        if rest and rest[0] not in ("-", ""):
            out.append(rest[0])
    return out


def all_segments(cmd: str, depth: int = 0):
    """Every command segment, INCLUDING those inside `sh -c '<string>'`, `bash -lc`, and `eval ...`,
    parsed as commands in their own right (41's delta review of #1470)."""
    if depth > MAX_DEPTH:
        raise Unjudgeable("shell strings nested too deeply to read")
    if depth == 0:
        HOME_GOOD.clear(); HOME_BAD.clear()
        FUNCS[0] = False
    bodies: list[str] = []
    toks = tokens(cmd, bodies)
    if "()" in toks:
        FUNCS[0] = True       # `name() body`: the name is its own segment and the body's commands are segments below, judged as written (#1770)
    deferred: list[str] = []
    for seg in segments(toks):
        check_words(seg)
        # `trap` is read BEFORE the function-keyword handling below, from the whole segment, so a `function f {` body and a compound body are seen
        # by the same path as a bare one. The strings run after every other segment (a trap fires last).
        deferred += _trap_strings(seg)
        if seg[0] in ("alias", "coproc"):
            raise Unjudgeable(f"`{seg[0]}` defines a name that can run any command later")
        if seg[0] == "function":
            # `function NAME { body }` / `function NAME() { body }`: drop the keyword and the name, judge the rest as written (#1770)
            if len(seg) < 2 or not re.fullmatch(r"[A-Za-z_][\w.:+@-]*", seg[1]):
                raise Unjudgeable("a function definition whose name cannot be read")
            FUNCS[0] = True
            seg = seg[2:]
            if not seg:
                continue
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
    for body in deferred:
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
    return _push_hits_args(parsed[0], parsed[1], cwd, current)


def _push_hits_args(args: list[str], workdir: str | None, cwd, current) -> list[tuple[str, str | None, str | None, str | None]]:
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
            target = home_expanded(seg[1])
            cwd = target if cwd is None or os.path.isabs(target) else os.path.join(cwd, target)
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


def pr_merge_match(rest: list[str]) -> str | None:
    """The commit a `gh pr merge` pins with `--match-head-commit`, or None when it pins nothing (#1571). A value the
    shell builds is `-` (unknown). The hook compares it with the head it resolved: GitHub merges only if the head
    still is that commit, which closes the gap between the gate's read and the merge."""
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--match-head-commit":
            return _token(rest[i + 1]) if i + 1 < len(rest) else "-"
        if a.startswith("--match-head-commit="):
            return _token(a.split("=", 1)[1])
        i += 2 if a in GH_MERGE_OPTS_WITH_VALUE else 1
    return None


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

    def __init__(self, rest: list[str], known: dict[str, str] | None = None):
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
        # #1617: a `query` that is nothing but a variable the command bound to a literal earlier is that literal; any other
        # variable is left as written, and `_graphql_effects` refuses a document it cannot read.
        if known:
            self.fields = [(k, known[m.group(1) or m.group(2)] if k == "query" and (m := re.fullmatch(r"\$(?:\{(\w+)\}|(\w+))", v))
                            and (m.group(1) or m.group(2)) in known else v, r) for k, v, r in self.fields]

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
    # #1617: a `$name` the document does not DECLARE (`query($id: ID!)`) is not GraphQL's, and GraphQL would refuse the document: it is a
    # shell variable, and the document is whatever the variable holds (`Q='mutation{...}'; gh api graphql -f query="$Q"` passed). `${`
    # is never GraphQL. A variable the command bound to a literal, once, earlier, was resolved before this point.
    # ONLY the document: the VALUE of another field (`-f owner="$OWNER"`) is a variable's value, and an ordinary one.
    doc = call.value("query") or ""
    data = call.json_input() if call.input else None
    if isinstance(data, dict) and isinstance(data.get("query"), str):
        doc += "\n" + data["query"]
    doc = doc.replace(SUBST, "")   # a command substitution is the rule above's (`$__SUBST__` would otherwise read as an undeclared variable and hide it)
    declared = set(re.findall(r"\$(\w+)\s*:", doc))
    if "${" in doc or any(n not in declared for n in re.findall(r"\$([A-Za-z_]\w*)", doc)) or re.search(r"\$[0-9@*#?!$-]", doc):
        raise Unjudgeable("a GraphQL document held in a shell variable cannot be read")
    out = []
    if "mergePullRequest" in text:
        pin = f" MATCH:{_token(_graphql_id(text, call, 'expectedHeadOid'))}" if "expectedHeadOid" in text else ""
        out.append(f"GQL_PR {_graphql_id(text, call, 'pullRequestId')}{pin}")
    if "updateRef" in text:
        out.append(f"GQL_REF {_graphql_id(text, call, 'refId')} {_token(_graphql_id(text, call, 'oid'))}")
    if "createRef" in text:
        name = _graphql_id(text, call, "name")
        if name == "-" or branch_of(name) in PROTECTED:
            out.append(f"API_REF {_token(_graphql_id(text, call, 'oid'))}")
    if re.search(r"\bmutation\b", text):
        # Every field with arguments in a mutation document must be one this file models or one known not
        # to merge or publish; `mergeBranch`, `createDeployment`, `updateBranchProtectionRule` ... are not.
        calls = set(re.findall(r"\b([A-Za-z_]\w*)\s*\(", re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)))
        unknown = calls - {"mergePullRequest", "updateRef", "createRef"} - SAFE_GQL - GQL_READ - {"mutation", "query"}
        if unknown:
            raise Unjudgeable(f"a GraphQL mutation this gate cannot place ({', '.join(sorted(unknown))})")
    return out


def gh_api_effects(rest: list[str], known: dict[str, str] | None = None) -> tuple[list[str], str]:
    """`(lines, repo)` for one `gh api <rest>`: API_PR_MERGE <n>, API_MERGE <head>, API_REF <sha>,
    GQL_PR <id>, GQL_REF <id> <oid>, RELEASE <tag> <target>, RELEASE_ID <id>; `repo` is the one a literal
    `repos/<o>/<r>/` path names, else `-`. `-` in a line means unknown, which the hook denies (#1569:
    a ref write or a merge is judged by the commit it WRITES -- `sha`, `head`, `oid` -- not by dev)."""
    call = ApiCall(rest, known)
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
    if m:                                       # any write to it: a PUT merges, and so may a verb gh adds later
        n = m.group(3)
        sha = call.value("sha")
        if sha is None and call.input:
            data = call.json_input()
            sha = data.get("sha") if isinstance(data, dict) else None
        pin = "" if sha is None else f" MATCH:{_token(str(sha))}"
        return [f"API_PR_MERGE {'-' if _expanded(n) or not n.isdigit() else n}{pin}"], repo
    # A write whose route is built by the shell: unreadable if the expansion could BE the resource
    # (`repos/o/r/$X`, `$URL`), or if the readable part already names one that matters.
    if _expanded(path):
        raise Unjudgeable("a gh api write whose path is built by the shell")
    if re.fullmatch(r"(?:repos/[^/]+/[^/]+/)?merges", path):
        base = call.value("base")
        if base is None or _expanded(base) or branch_of(base) in PROTECTED:
            return [f"API_MERGE {_token(call.value('head'))}"], repo
        return [], repo
    m = re.fullmatch(r"(?:repos/[^/]+/[^/]+/)?git/refs/(.+)", path)
    if m:
        ref = m.group(1)
        if _expanded(ref) or branch_of(ref) in PROTECTED:
            return [f"API_REF {_token(call.value('sha'))}"], repo
        return [], repo
    if re.fullmatch(r"(?:repos/[^/]+/[^/]+/)?git/refs", path):
        ref = call.value("ref")
        if ref is None or _expanded(ref) or branch_of(ref) in PROTECTED:
            return [f"API_REF {_token(call.value('sha'))}"], repo
        return [], repo
    m = re.fullmatch(r"(?:repos/([^/]+)/([^/]+)/)?releases/([^/]+)", path)
    if m:
        draft = call.value("draft")
        if draft is not None and _draft_off(draft):
            rid = m.group(3)
            if not rid.isdigit():
                raise Unjudgeable(f"the release id {rid!r} could not be read")
            return [f"RELEASE_ID {rid}"], repo
        return [], repo
    if re.fullmatch(r"(?:repos/[^/]+/[^/]+/)?releases", path):
        tag, target = call.value("tag_name"), call.value("target_commitish")
        return [_release_line(tag, target)], repo
    # A write nothing above models. Only a short list of routes is known not to merge or publish; every
    # other write is Unjudgeable (#1569): `repos/<o>/<r>/dispatches`, `deployments`, `pulls/N/update-branch`,
    # `merge-upstream`, `transfer` and whatever GitHub adds next cannot be listed in advance.
    if SAFE_API_WRITE.fullmatch(path):
        return [], repo
    raise Unjudgeable(f"a gh api {'/'.join(sorted(methods))} to {path!r}, which is not a route known not to merge or publish")


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
            target = home_expanded(seg[1]) if len(seg) == 2 else ""
            if len(seg) == 2 and seg[1] != "-" and not _expanded(target):
                cwd = target if cwd is None or cwd is UNKNOWN_DIR or os.path.isabs(target) else os.path.join(cwd, target)
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


# --- FAIL CLOSED BY CONSTRUCTION (#1569) -------------------------------------------------------------
# Enumerating the spellings of a merge is how each review found one more. So every `gh` and `git` the
# command runs gets a verdict from a POSITIVE list: either a verb that cannot merge into main or publish a
# release (listed below), or one of the effects this file models. Anything else -- an unknown verb, a git
# alias, an unknown global option, a verb or subcommand built by the shell -- is Unjudgeable, which the
# hook denies. In a repository the gate applies to, that over-blocks a safe command nobody listed. The
# alternative is letting an unlisted spelling through, and that is the one that cost a production deploy.
GIT_SAFE = {
    "status", "log", "diff", "show", "fetch", "add", "rm", "mv", "commit", "restore", "stash", "rev-parse",
    "rev-list", "ls-files", "ls-remote", "ls-tree", "describe", "blame", "grep", "shortlog", "show-ref",
    "for-each-ref", "cat-file", "branch", "tag", "checkout", "switch", "reflog", "clean", "worktree",
    "diff-tree", "diff-files", "diff-index", "apply", "format-patch", "archive", "bisect", "help", "version",
    "init", "clone", "reset", "revert", "cherry-pick", "rebase", "am", "gc", "prune", "count-objects",
    "fsck", "whatchanged", "range-diff", "name-rev", "merge-base", "check-ignore", "check-attr",
    "check-ref-format", "var", "verify-commit", "verify-tag", "sparse-checkout", "notes", "hash-object",
    "write-tree", "read-tree", "commit-tree", "mktree", "mktag", "unpack-file", "stripspace", "interpret-trailers",
    "maintenance", "remote", "config", "submodule", "bundle", "difftool", "citool", "gui", "gitk", "last-modified",
}
GIT_FLAGS = {"--no-pager", "-p", "--paginate", "-P", "--bare", "--no-replace-objects", "--literal-pathspecs",
             "--glob-pathspecs", "--noglob-pathspecs", "--icase-pathspecs", "--no-optional-locks",
             "--no-lazy-fetch", "--version", "--help", "-h", "--html-path", "--man-path", "--info-path", "--exec-path"}
BENIGN_CONFIG = re.compile(r"^(user\.|core\.(quotepath|pager|editor|autocrlf|filemode|ignorecase|precomposeunicode|"
                           r"longpaths|abbrev|whitespace|fsmonitor)$|color\.|advice\.|gc\.auto$|safe\.directory$|"
                           r"init\.defaultbranch$|commit\.gpgsign$|diff\.|log\.)", re.I)
# (#1768) what turns `git config` into a write, and the options that take a value of their own (so the value is not the key's value)
CONFIG_WRITE_FLAGS = {"--add", "--unset", "--unset-all", "--replace-all", "-e", "--edit", "--rename-section", "--remove-section"}
CONFIG_READ_ACTIONS = {"--get", "--get-all", "--get-regexp", "--list", "-l", "--get-urlmatch"}
CONFIG_VALUE_FLAGS = {"--file", "-f", "--blob", "--type", "--default"}
CONFIG_READ_FLAGS = {"--global", "--local", "--system", "--worktree", "--includes", "--no-includes", "--show-origin", "--show-scope", "-z", "--null",
                     "--name-only", "--bool", "--int", "--bool-or-int", "--path", "--expiry-date", "--fixed-value", "--no-type"}
GIT_ENV_REDIRECT = re.compile(r"^GIT_(DIR|WORK_TREE|CONFIG\w*|SSH\w*|ALTERNATE\w*|OBJECT_DIRECTORY|INDEX_FILE|NAMESPACE)=")
INERT = {"echo", "printf", "which", "type", "man", "ls", "cat", "grep", "rg", "head", "tail", "wc", "cut", "tr",
         "sort", "uniq", "test", "[", "[[", "true", "false", ":", "export", "set", "unset", "read", "mkdir", "rm",
         "cp", "mv", "touch", "chmod", "ln", "tee", "basename", "dirname", "readlink", "realpath", "date", "sleep",
         "exit", "return", "diff", "cmp", "jq", "popd", "cd", "pushd"}
GH_GROUPS_ANY = {"issue", "auth", "config", "status", "browse", "search", "label", "gist", "extension", "alias",
                 "completion", "help", "version", "cache", "variable", "secret", "ssh-key", "gpg-key", "project",
                 "attestation", "agent-task", "licenses", "preview"}
GH_GROUPS_SOME = {
    "pr": {"view", "list", "create", "checks", "diff", "status", "checkout", "comment", "edit", "review", "close",
           "reopen", "ready", "lock", "unlock"},
    "repo": {"view", "list", "clone", "fork", "gitignore", "license"},
    "run": {"list", "view", "watch", "download", "cancel", "delete"},
    "workflow": {"list", "view"},
    "release": {"list", "view", "download", "upload", "delete-asset"},
    "ruleset": {"list", "view", "check"},
    "org": {"list"},
}
SAFE_API_WRITE = re.compile(
    r"(?:repos/[^/]+/[^/]+/)?(?:issues(?:/\d+(?:/(?:comments|labels|assignees|reactions))?)?|issues/comments/\d+(?:/reactions)?|"
    r"pulls(?:/\d+(?:/(?:comments|reviews|requested_reviewers|reviews/\d+/(?:events|comments)))?)?|"
    r"pulls/comments/\d+(?:/reactions)?|statuses/[^/]+|check-runs(?:/\d+)?|git/(?:blobs|trees|commits|tags)|labels(?:/[^/]+)?)")
SAFE_GQL = {"addComment", "addPullRequestReview", "addPullRequestReviewComment", "addPullRequestReviewThread",
            "addReaction", "removeReaction", "addLabelsToLabelable", "removeLabelsFromLabelable", "createIssue",
            "updateIssue", "closeIssue", "reopenIssue", "createPullRequest", "updatePullRequest", "closePullRequest",
            "reopenPullRequest", "markPullRequestReadyForReview", "convertPullRequestToDraft", "requestReviews",
            "resolveReviewThread", "unresolveReviewThread", "minimizeComment", "updateIssueComment",
            "deleteIssueComment", "submitPullRequestReview", "addAssigneesToAssignable", "createLabel",
            "updateLabel", "addStar", "removeStar", "createDiscussion", "addDiscussionComment"}
GQL_READ = {"repository", "node", "nodes", "user", "organization", "viewer", "search", "issue", "pullRequest", "labels",
            "comments", "assignees", "reviews", "commits", "files", "timelineItems", "reviewThreads", "reactions",
            "commit", "ref", "refs", "object", "milestone", "projectV2", "discussion", "issues", "pullRequests"}


def command_indexes(seg: list[str]) -> list[tuple[str, int]]:
    """Every `(tool, index)` in `seg` that may RUN gh or git. The command word is the first word that is
    no assignment, wrapper (`sudo`, `timeout`, `env`, `command`, `xargs` ...) or option. If that word is
    gh or git, that is the invocation. If it is a command known to treat its words as data (`echo`,
    `which`, `grep`), nothing runs. If it is anything else (`find -exec`, `parallel`, `watch`, a wrapper
    this file does not know), EVERY bare gh/git word may be the command it runs (#1569)."""
    head = None
    for i, w in enumerate(seg):
        if re.fullmatch(r"[A-Za-z_]\w*=.*", w) or w in WRAPPERS or w.startswith("-") or re.fullmatch(r"\d+[smhd]?", w):
            continue
        head = i
        break
    if head is None:
        return []
    base = seg[head].rsplit("/", 1)[-1]
    if is_command(seg[head], {"git"}):
        return [("git", head)]
    if is_command(seg[head], {"gh"}):
        return [("gh", head)]
    if base in INERT:
        return []
    return [("git" if is_command(w, {"git"}) else "gh", i) for i, w in enumerate(seg)
            if is_command(w, {"git"}) or is_command(w, {"gh"})]


def git_parse(seg: list[str], j: int):
    """`(verb, args, workdir, redirected)` for the `git` at seg[j]. Only global options this file knows are
    stepped over; an unknown one, an inline alias, a `-c` that is not harmless (`url.<x>.insteadOf`
    redirects a push), or a verb built by the shell is Unjudgeable."""
    i, workdir, redirected = j + 1, None, False
    while i < len(seg) and seg[i].startswith("-"):
        a = seg[i]
        if a in ("-C", "-c"):
            if i + 1 >= len(seg):
                raise Unjudgeable(f"git {a} with no value")
            v = seg[i + 1] if a == "-c" else home_expanded(seg[i + 1])
            if a == "-c":
                if v.startswith("alias."):
                    raise Unjudgeable("a git alias defined inline can be any verb, push included")
                if not BENIGN_CONFIG.match(v.partition("=")[0]):
                    raise Unjudgeable(f"git -c {v.partition('=')[0]} can redirect or rewrite what the command does")
            else:
                workdir = v if workdir is None or os.path.isabs(v) else os.path.join(workdir, v)
            i += 2; continue
        if a.startswith(("--git-dir", "--work-tree", "--namespace", "--super-prefix")):
            redirected = True
            i += 1 if "=" in a else 2; continue
        if a.startswith(("--exec-path", "--attr-source", "--config-env")) or a in GIT_FLAGS:
            i += 1; continue
        raise Unjudgeable(f"the git option {a!r} is not one this gate reads")
    if i >= len(seg):
        return None, [], workdir, redirected
    verb = seg[i]
    if _expanded(verb) or EXPANDS & set(verb) or SUBST in verb:
        raise Unjudgeable("the git verb is built by the shell")
    return verb, seg[i + 1:], workdir, redirected


def _git_read_only(verb: str, args: list[str]) -> bool:
    """`git remote` and `git config` can repoint where a later push goes: only their read forms are safe."""
    if verb == "remote":
        sub = next((a for a in args if not a.startswith("-")), "")
        return sub in ("", "show", "get-url", "add")       # `add` cannot repoint an existing remote
    if verb == "config":
        # `--get`, `--list` and the like are read FLAGS; `get` and `list` are the read SUB-COMMANDS of newer git, and only in the FIRST position:
        # anywhere else they are a VALUE (`git config core.hooksPath get` points the hooks at ./get; #1768 review).
        if any(a in CONFIG_READ_ACTIONS for a in args):
            return True
        if any(a in CONFIG_WRITE_FLAGS for a in args):
            return False
        # (#1768) A bare `git config <key>`: ONE positional word, no write flag, is a READ of that key, whichever key it is: `core.hooksPath` is not on the benign
        # list because SETTING it redirects the hooks, but reading it is how a session asks where they are. Three ways this could be a write, each refused:
        #   - a flag this rule does not KNOW is harmless: git accepts any unambiguous prefix of a long option (`--unset-a`, `--uns`), so a list of the write flags
        #     is not enough; only the flags that select a file or a value type are allowed;
        #   - a word that is not a key: `edit`, `set`, `unset` are sub-commands of newer git, and a key always has a dot (`section.name`);
        #   - a second word (a value), or a word the shell has not expanded yet.
        words, skip, only_known = [], False, True
        for a in args:
            if skip:
                skip = False
            elif a in CONFIG_VALUE_FLAGS:
                skip = True
            elif a.startswith("-"):
                only_known = only_known and a in CONFIG_READ_FLAGS
            else:
                words.append(a)
        if only_known and words and words[0] in ("get", "list"):
            return True
        if only_known and len(words) == 1 and "." in words[0] and not _opaque(words[0]):
            return True
        keys = [a for a in args if not a.startswith("-")]
        return bool(keys) and BENIGN_CONFIG.match(keys[0]) is not None
    if verb == "submodule":
        sub = next((a for a in args if not a.startswith("-")), "")
        return sub in ("", "status", "summary", "init", "update", "absorbgitdirs")
    return True


# --- WHAT EARLIER SEGMENTS OF ONE COMMAND DID TO THE STATE THE HOOK READS (#1571) -----------------------
# The hook resolves HEAD and refs BEFORE the command runs. A command that moves them first and then merges
# or pushes is judged from a state that no longer holds: `git switch main && git merge hotfix` was read as
# "a merge off main" and allowed. So the classifier follows the branch and the refs through the segments.
HOOK_HEAD = ""            # "the branch the hook saw": what HEAD was before this command ran
UNKNOWN_BRANCH = "?"      # a branch change that could not be followed
MAIN_BRANCHES = ("main", "master")
CHECKOUT_FLAGS = {"-q", "--quiet", "-f", "--force", "-m", "--merge", "--guess", "--no-guess", "--progress",
                  "--no-progress", "--recurse-submodules", "--no-recurse-submodules", "--discard-changes",
                  "--ignore-other-worktrees", "--overwrite-ignore", "--no-overwrite-ignore", "--overlay",
                  "--no-overlay", "-t", "--track", "--no-track", "-l"}
REF_MOVING_VERBS = {"commit", "reset", "cherry-pick", "am", "revert", "update-ref", "symbolic-ref", "merge",
                    "pull", "replace"}
GH_HEAD_MOVING = (["pr", "checkout"],)       # #1781: the gh subcommands that move HEAD, as the `[group, name]` prefix of the subcommand
BISECT_READ_ONLY = {"log", "visualize", "view", "terms", "help"}      # #1781: every other `git bisect` sub-command may check a commit out
BRANCH_WRITE_FLAGS = {"-f", "--force", "-d", "-D", "--delete", "-m", "-M", "--move", "-c", "-C", "--copy",
                      "-u", "--set-upstream-to", "--unset-upstream", "--edit-description"}


def _opaque(word: str) -> bool:
    return _expanded(word) or bool(EXPANDS & set(word)) or SUBST in word


def branch_change(verb: str, args: list[str]):
    """`(branches HEAD may be on afterwards, or None if the branch is unchanged; HEAD moved; a ref moved)` for
    `git switch`, `git checkout`, `git rebase` and `git branch -m`. `HOOK_HEAD` stands for "as the hook saw
    it": `git checkout x` may switch to a branch x OR restore a path x, and cannot be told apart without the
    repository, so it keeps both possibilities. A flag or a word the model does not know is UNKNOWN."""
    unknown = ({UNKNOWN_BRANCH}, True, True)
    positional: list[str] = []
    if verb in ("switch", "checkout"):
        make = ("-c", "--create") if verb == "switch" else ("-b", "--orphan")
        reset = ("-C", "--force-create") if verb == "switch" else ("-B",)
        new, forced, detach, i = None, False, False, 0
        while i < len(args):
            a = args[i]
            if a == "--":
                # `checkout [<tree-ish>] -- <paths>` restores files and leaves HEAD alone
                return (None, False, False) if new is None and not detach else unknown
            if a in make or a in reset:
                if i + 1 >= len(args):
                    return unknown
                new, forced = args[i + 1], a in reset
                i += 2; continue
            if a in ("-d", "--detach"):
                detach = True; i += 1; continue
            if a.startswith("-"):
                if a in CHECKOUT_FLAGS:
                    i += 1; continue
                return unknown
            positional.append(a); i += 1
        if new is not None:
            return ({UNKNOWN_BRANCH} if _opaque(new) else {new}), True, forced
        if detach:
            return {"(detached)"}, True, False
        if verb == "switch":
            if len(positional) != 1 or _opaque(positional[0]):
                return unknown
            return {positional[0]}, True, False
        if len(positional) == 1:
            return ({UNKNOWN_BRANCH} if _opaque(positional[0]) else {HOOK_HEAD, positional[0]}), True, False
        return None, False, False
    if verb in ("bisect", "worktree", "stash"):
        # #1781. Verbs that may check a commit or branch out, in THIS directory (`bisect start|good|bad|skip|reset|run|replay`) or in a new one a later
        # `cd` enters (`worktree add`), so a later HEAD-relative push is judged against the wrong branch. Anything not named read-only is refused, not
        # modelled. `git stash` itself does NOT move HEAD or change the current branch (it saves and cleans the working tree, and `stash pop|apply|
        # list|show|drop|push|create|store|clear` leave the branch alone), so it stays allowed; `git stash branch <name>` creates and checks out a branch.
        sub = next((a for a in args if not a.startswith("-")), "")
        if verb == "bisect" and sub not in BISECT_READ_ONLY and not (not sub and any(a in ("--help", "-h") for a in args)):
            return unknown
        if verb == "worktree" and sub == "add":
            return unknown
        if verb == "stash" and sub == "branch":
            return unknown
        return None, False, False
    if verb == "rebase":
        positional = [a for a in args if not a.startswith("-")]
        if any(_opaque(a) for a in positional):
            return unknown
        return ({HOOK_HEAD, positional[-1]} if len(positional) >= 2 else None), True, True
    if verb == "branch":
        positional = [a for a in args if not a.startswith("-")]
        writes = bool(positional) or any(a in BRANCH_WRITE_FLAGS for a in args)
        if any(_opaque(a) for a in positional):
            return unknown if writes else (None, False, False)
        renames = any(a in ("-m", "-M", "--move", "-c", "-C", "--copy") for a in args)
        return ({HOOK_HEAD, positional[-1]} if renames and positional else None), False, writes
    return None, False, False


class _Flow:
    """The repository state as earlier segments of ONE command left it, per directory.

    Fail closed on spelling: two paths cannot be told to name the same repository (`-C .`, `-C ./x`, an
    absolute path), so a branch change in one directory is also applied to the hook's own directory and
    to every directory not yet seen. `tainted` is every branch any segment may have switched to."""

    def __init__(self) -> None:
        self.branches: dict[str, set[str]] = {}
        self.tainted: set[str] = set()
        self.unknown_dir = False
        self.refs_moved = False
        self.head_moved = False

    def possible(self, key: str | None) -> set[str]:
        return self.branches.get(key, {HOOK_HEAD} | self.tainted) if key is not None else {HOOK_HEAD} | self.tainted

    def promotion_kinds(self, key: str | None, base: str) -> list[str]:
        """The effect lines a merge or pull emits: `base` when HEAD may still be what the hook saw (the hook
        checks it), `base_MAIN` when it may be main by the command's own doing. UNKNOWN denies."""
        poss = self.possible(key)
        if UNKNOWN_BRANCH in poss or self.unknown_dir:
            raise Unjudgeable("a merge or pull after a branch change that could not be followed")
        kinds = [base] if HOOK_HEAD in poss else []
        if any(b in MAIN_BRANCHES for b in poss if b):
            kinds.append(base + "_MAIN")
        return kinds

    def check_push(self, src: str | None) -> None:
        """A push to main ships a ref the hook has already read. If an earlier segment moved a ref (or, for a
        HEAD-relative source, HEAD), what it ships is not what the hook read."""
        head_relative = bool(src) and (src in ("HEAD", "@") or src.startswith(("HEAD~", "HEAD^", "@~", "@^")))
        if self.refs_moved or (head_relative and self.head_moved):
            raise Unjudgeable("a push to main after a command that moves refs or HEAD: the commit it ships "
                              "is not the one the hook can read; run them as separate commands")

    def after_gh(self, names: list[str]) -> None:
        """#1781: `gh pr checkout` switches HEAD to the pull request's branch, which is unknown here (no `gh` call is made)."""
        if names[:2] in GH_HEAD_MOVING:
            self.head_moved = True
            self.tainted.add(UNKNOWN_BRANCH)
            self.unknown_dir = True

    def after(self, verb: str, args: list[str], key: str | None) -> None:
        """Fold one `git` segment into the state."""
        branches, head_moved, refs_moved = branch_change(verb, args)
        if verb in REF_MOVING_VERBS:
            head_moved = refs_moved = True
        elif verb == "fetch" and (any(":" in a for a in args) or "-u" in args or "--update-head-ok" in args):
            refs_moved = True
        elif verb == "tag" and (any(not a.startswith("-") for a in args) or any(a in ("-f", "-d", "--delete", "--force") for a in args)):
            refs_moved = True
        self.head_moved = self.head_moved or head_moved
        self.refs_moved = self.refs_moved or refs_moved
        if branches is not None:
            self.tainted |= branches
            if key is None:
                self.unknown_dir = True
            else:
                self.branches[key] = branches
                for other in self.branches:
                    if other != key:
                        self.branches[other] = self.branches[other] | branches


def _literal_current(branch: str):
    """A `current(push, dir)` that answers as if HEAD were on `branch`: no upstream, so a bare push falls
    back to the branch's own name."""
    return lambda push, d=None: None if push else branch


def git_effects(seg, j, cwd, current, flow=None):
    """`[(line, repo, dir)]` for one `git` invocation, or Unjudgeable when it is neither a modelled effect
    nor a verb on the safe list. `flow` carries what earlier segments of the same command did to HEAD and refs."""
    flow = flow if flow is not None else _Flow()
    verb, args, workdir, _ = git_parse(seg, j)
    try:
        key = _dir_word(cwd, workdir)
        if key != "-" and not os.path.isabs(key):
            key = os.path.normpath(key)           # `.`, `./` and `sub/..` all name the hook's own directory
            key = "-" if key == "." else key
    except Unjudgeable:
        key = None
    out = _git_effects_core(seg, j, cwd, current, flow, key)
    if verb:
        flow.after(verb, args, key)
    return out


def _git_effects_core(seg, j, cwd, current, flow, key):
    """`[(line, repo, dir)]` for one `git` invocation, or Unjudgeable when it is neither a modelled effect
    nor a verb on the safe list."""
    verb, args, workdir, redirected = git_parse(seg, j)
    if verb is None:
        if any(a not in ("--version", "--help", "-h", "--html-path", "--man-path", "--info-path", "--exec-path") for a in seg[j + 1:]):
            raise Unjudgeable("git with options and no verb")
        return []
    envs = [w for w in seg[:j] if GIT_ENV_REDIRECT.match(w)]
    if verb == "push" or verb == "merge" or verb == "pull":
        if redirected or envs:
            raise Unjudgeable("GIT_DIR, --git-dir, --work-tree or GIT_CONFIG redirects which repository this acts on")
        if any(w == "xargs" for w in seg[:j]):
            raise Unjudgeable("xargs appends its stdin to the command, so its refspecs are unknown")
    out = []
    if verb == "push":
        for possible in sorted(flow.possible(key)):
            if possible == UNKNOWN_BRANCH or flow.unknown_dir:
                raise Unjudgeable("a push after a branch change that could not be followed")
            cur = current if possible == HOOK_HEAD else _literal_current(possible)
            for dst, src, remote, where in _push_hits_args(args, workdir, cwd, cur):
                flow.check_push(src)
                row = (f"PUSH_REF {src}" if src else f"PUSH_MAIN {dst}", f"remote:{remote}" if remote else "-",
                       _dir_word(None, where))
                if row not in out:
                    out.append(row)
        return out
    if verb == "merge":
        refs = merge_refs(args)
        if refs is not None:
            for kind in flow.promotion_kinds(key, "GIT_MERGE"):
                out.append(((kind + " " + " ".join(refs)).rstrip(), "-", _dir_word(cwd, workdir)))
        return out
    if verb == "pull":
        # fetch + merge: on main it brings the upstream's commits into main, and they are not fetched yet.
        for kind in flow.promotion_kinds(key, "GIT_PULL"):
            out.append((kind, "-", _dir_word(cwd, workdir)))
        return out
    if verb in GIT_SAFE and _git_read_only(verb, args):
        return []
    raise Unjudgeable(f"git {verb!r} is not on the list of commands that cannot merge into main or publish")


def gh_effects_for(seg, j, cwd, env_repo, known=None, flow=None):
    """`[(line, repo, dir)]` for one `gh` invocation, or Unjudgeable when it is neither a modelled effect
    nor on the safe list."""
    names, rest, repo = gh_parts(seg, j)
    d = _dir_word(cwd)
    if flow is not None:
        flow.after_gh(names)
    if names and (_expanded(names[0]) or EXPANDS & set(names[0]) or (len(names) > 1 and (_expanded(names[1]) or EXPANDS & set(names[1])))):
        raise Unjudgeable("the gh subcommand is built by the shell")
    if names == ["pr", "merge"]:
        pin = pr_merge_match(rest)
        line = f"PR_MERGE {pr_merge_selector(rest)}" + ("" if pin is None else f" MATCH:{pin}")
        return [(line.rstrip(), repo or env_repo or "-", d)]
    if names[:1] == ["api"]:
        lines, prepo = gh_api_effects(rest, known)
        return [(ln, prepo if prepo != "-" else (env_repo or "-"), d) for ln in lines]
    if names == ["release", "create"]:
        return [(ln, repo or env_repo or "-", d) for ln in release_creates(rest)]
    if names == ["release", "edit"]:
        return [(ln, repo or env_repo or "-", d) for ln in release_edits(rest)]
    if not names:
        if any(a not in ("--version", "--help", "-h") for a in rest):
            raise Unjudgeable("gh with options and no subcommand")
        return []
    if names[0] in GH_GROUPS_ANY:
        return []
    if names[0] in GH_GROUPS_SOME and len(names) > 1 and names[1] in GH_GROUPS_SOME[names[0]]:
        return []
    raise Unjudgeable(f"gh {' '.join(names)!r} is not on the list of commands that cannot merge into main or publish a release")


def _flat_list(cmd: str) -> bool:
    """True when `cmd` is a plain list of simple commands joined by `;` or newlines: no pipe, `&&`, `||`, `&`, group, subshell, substitution,
    heredoc, control-flow keyword or nested shell outside a quote. Only then is an assignment on an earlier line certain to hold at a later
    one (#1617: `( Q=x )`, `true || Q=x`, `if ..; then Q=x; fi`, `Q=x | cat` bind in another scope or not at all, and the later `$Q` is whatever
    the environment holds)."""
    out, i, n = [], 0, len(cmd)
    while i < n:
        c = cmd[i]
        if c == "\\":
            out.append("x"); i += 2; continue
        if c == "'":
            j = cmd.find("'", i + 1)
            out.append("x"); i = n if j < 0 else j + 1; continue
        if c == '"':
            j = i + 1
            while j < n and cmd[j] != '"':
                j += 2 if cmd[j] == "\\" else 1
            # A double quote still EXPANDS: `"${Q:=...}"` assigns, `"$(...)"` and a backtick run a command, and none of it shows once the quote is
            # masked (#1617 review). A plain `$name` or `${name}` only reads, and stays flat.
            if re.search(r"\$\{[A-Za-z_]\w*:?[=+?-]|\$\(|`", cmd[i:j]):
                return False
            out.append("x"); i = j + 1; continue
        out.append(c); i += 1
    flat = "".join(out)
    if re.search(r"[|&(){}`]|<<|\$\(", flat):
        return False
    # `declare`, `typeset`, `local` and `readonly` bind a name in ways this does not follow (`declare -n Q=R` makes Q read R).
    return not re.search(r"(^|[\s;])(if|then|else|elif|fi|for|while|until|do|done|case|esac|function|select|eval|source|\.|bash|sh|zsh|dash|ksh|exec|"
                         r"declare|typeset|local|readonly)(?=[\s;]|$)", flat)


def literal_vars(cmd: str) -> dict[str, str]:
    """#1617: the variables a command binds ONCE, to a literal, and mentions nowhere else as a word (no `read Q`, `for Q in`, `unset Q`,
    `printf -v Q`, `export Q`, `Q+=`): only those can be read as what they hold. A name bound twice (an `if`/`else` that picks one), to
    something built by the shell, or by any other form is unknown, and a document held in it is refused. Known limit: a variable already in
    the environment that a conditional assignment may or may not replace."""
    if not _flat_list(cmd):
        return {}
    bound: dict[str, list[str | None]] = {}
    bare: set[str] = set()
    for seg in all_segments(cmd):
        for w in seg:
            m = re.match(r"([A-Za-z_]\w*)(\+?)=(.*)\Z", w, re.S)
            if m:
                v = m.group(3)
                bound.setdefault(m.group(1), []).append(None if m.group(2) or _expanded(v) else v)   # no glob or brace expansion on an assignment's right side
            elif re.fullmatch(r"[A-Za-z_]\w*", w):
                bare.add(w)
    return {n: vs[0] for n, vs in bound.items() if len(vs) == 1 and vs[0] is not None and n not in bare}


def _function_state_check(seg: list[str]) -> None:
    """#1770. A function body is judged where it is written, but it RUNS where it is called, which may be before the definition, after a `cd`, or after a
    branch change. So in a command that defines a function, anything that changes where or on what a later git runs is refused rather than modelled: a
    `cd`/`pushd`, a GIT_DIR-style environment redirect, and any git verb that moves HEAD or a ref."""
    head = next((w for w in seg if w not in WRAPPERS and not re.fullmatch(r"[A-Za-z_]\w*=.*", w)), "")
    if head in ("cd", "pushd", "popd") or any(GIT_ENV_REDIRECT.match(w) for w in seg):
        raise Unjudgeable("a command that defines a function and also changes directory or redirects git: where the body runs cannot be read")
    for tool, j in command_indexes(seg):
        if tool == "gh":
            scratch = _Flow()
            scratch.after_gh(gh_parts(seg, j)[0])
            if scratch.head_moved:
                raise Unjudgeable("a command that defines a function and also moves HEAD (gh pr checkout): when the body runs cannot be read")
        if tool == "git":
            verb, args, _, _ = git_parse(seg, j)
            if verb:
                scratch = _Flow()
                scratch.after(verb, args, None)
                if scratch.head_moved or scratch.refs_moved or scratch.tainted or scratch.unknown_dir:
                    raise Unjudgeable("a command that defines a function and also moves HEAD or a ref: when the body runs cannot be read")


def effects(cmd: str, current) -> list[tuple[str, str, str]]:
    """`(line, repo, dir)` for everything in `cmd` that merges into main or publishes. `repo` is the
    repository the command acts on when it says so (`-R`, GH_REPO, a `repos/o/r/` path, a git remote as
    `remote:<name>`), else `-`; `dir` is where it runs after a `cd` or `git -C`, else `-`."""
    out: list[tuple[str, str, str]] = []
    flow = _Flow()
    lits, known = literal_vars(cmd), {}
    every = list(all_segments(cmd))
    if FUNCS[0]:
        for seg in every:
            _function_state_check(seg)
    for seg, cwd, env_repo in ctx_segments(cmd):
        for tool, j in command_indexes(seg):
            if tool == "git":
                out += git_effects(seg, j, cwd, current, flow)
            else:
                out += gh_effects_for(seg, j, cwd, env_repo, known, flow)
        # AFTER the segment: `Q=x gh api ... "$Q"` expands $Q before the prefix assignment takes effect.
        for w in seg:
            m = re.match(r"([A-Za-z_]\w*)=", w)
            if m and m.group(1) in lits:
                known[m.group(1)] = lits[m.group(1)]
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
    os.environ["HOME"] = "/home/selftest"    # the cases below name directories through it (#1764); a real HOME would make them depend on the machine

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
        # a here-string (`<<<`) is a WORD, not a heredoc: it opens no body and hides nothing after it. Its second `<` once started
        # a heredoc whose "delimiter" was the word, and the push after it was deleted with the body.
        ("cat <<< x; git push origin main", on_feature, True),
        ("cat <<<x; git push origin main", on_feature, True),
        ("cat <<< x\ngit push origin main", on_feature, True),
        ("git push origin main <<< x", on_feature, True),
        ("cat <<< x; git push origin fix/x", on_feature, False),
        ("cat <<< x\ngit push origin fix/x", on_feature, False),
        ("cat <<< x <<EOF\nbody\nEOF\ngit push origin main", on_feature, True),     # a real heredoc after a here-string still opens
        ("cat <<< x <<EOF\ngit push origin main\nEOF", on_feature, False),             # ... and still hides its own body
        # the same inside a substitution, whose own scanner decides where it ends
        ("y=$(cat <<< x)\ngit push origin main", on_feature, True),
        ("y=$(cat <<<x\n)\ngit push origin main", on_feature, True),
        ("y=$(cat <<< x)\ngit push origin fix/x", on_feature, False),
        ("y=$(cat <<< x)\ncat <<EOF\ngit push origin main\nEOF\ngit push origin fix/x", on_feature, False),   # the here-string owes no delimiter
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
        # (#1768) an empty-string argument does not end the command: the refspecs after it are still read
        ("git push origin '' main", on_feature, True),
        # (#1764) a directory named through HOME is expanded BEFORE the push's HEAD is resolved there: the hook is handed the raw command
        ("git -C ~/proj push", fake("topic", by_dir={"/home/selftest/proj": "main"}), True),
        ("git -C ~/proj push", fake("main", by_dir={"/home/selftest/proj": "topic"}), False),
        ("cd ~/proj && git push", fake("topic", by_dir={"/home/selftest/proj": "main"}), True),
        ("cd ~/proj && git push", fake("main", by_dir={"/home/selftest/proj": "topic"}), False),
        ("git -C $HOME/proj push", fake("topic", by_dir={"/home/selftest/proj": "main"}), True),
        ("git -C ${HOME}/proj push", fake("topic", by_dir={"/home/selftest/proj": "main"}), True),
        ("cd $HOME/proj && git push", fake("topic", by_dir={"/home/selftest/proj": "main"}), True),
        ("cd ~ && git push", fake("topic", by_dir={"/home/selftest": "main"}), True),
        ('git -C "$HOME/proj" push', fake("topic", by_dir={"/home/selftest/proj": "main"}), True),
        # ...but only a spelling the shell WILL expand: quoted or escaped, `~/proj` is a literal directory name to git, and expanding it would judge HEAD in a checkout the push never touches
        ("git -C '~/proj' push", fake("topic", by_dir={"/home/selftest/proj": "main"}), False),
        ('git -C "~/proj" push', fake("topic", by_dir={"/home/selftest/proj": "main"}), False),
        ("git -C \\~/proj push", fake("topic", by_dir={"/home/selftest/proj": "main"}), False),
        ("git -C '~/proj' push; git -C ~/proj push", fake("topic", by_dir={"/home/selftest/proj": "main"}), False),
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
                      ("cat <<< x; gh pr merge 5", ["PR_MERGE 5"]), ("cat <<<x\ngh pr merge 5", ["PR_MERGE 5"]),
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
            ("cat <<< x; gh api -X PUT repos/o/r/pulls/5/merge", ["API_PR_MERGE 5"]),
            ("cat <<< x\ngh api graphql -f query='mutation { mergePullRequest(input:{pullRequestId:\"PR_kw1\"}) { x } }'", ["GQL_PR PR_kw1"]),
            ("cat <<< x; gh api repos/o/r/merges -f base=main -f head=dev", ["API_MERGE dev"]),
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
            # #1617: a document held in a variable is read when the command bound it ONCE, to a literal, earlier; its VALUE is judged like
            # a literal one. A variable passed as another field's value is ordinary.
            ("Q='mutation { mergePullRequest(input:{pullRequestId:\"PR_kw1\"}) { x } }'; gh api graphql -f query=\"$Q\"", ["GQL_PR PR_kw1"]),
            ("export Q='mutation { mergePullRequest(input:{pullRequestId:\"PR_kw1\"}) { x } }'\\ngh api graphql -f query=\"$Q\"", ["GQL_PR PR_kw1"]),
            ("Q='query{viewer{login}}'; gh api graphql -f query=\"$Q\"", []),
            ("Q='query{viewer{login}}'; gh api graphql -f query=\"$Q\" -f o=\"$OWNER\" -f p=\"${PAGE}\"", []),
            ("gh api graphql -f query='query($o:String!){repository(owner:$o){id}}' -f o=\"$OWNER\"", []),
            ("gh api graphql -f query='mutation($id:ID!){mergePullRequest(input:{pullRequestId:$id}){x}}' -f id=\"$ID\"", ["GQL_PR -"]),
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
            # #1617: a document the command did not bind once, to a literal, before it uses it
            "gh api graphql -f query=\"$Q\"", "gh api graphql -f query=$Q", "gh api graphql -f query=\"${Q}\"",
            "Q='query{a}' gh api graphql -f query=\"$Q\"", "read Q < f; gh api graphql -f query=\"$Q\"",
            "if c; then Q='query{a}'; else Q='mutation{x}'; fi; gh api graphql -f query=\"$Q\"",
            "Q='query{a}'; Q='mutation{x}'; gh api graphql -f query=\"$Q\"", "Q='query{a}'; export Q; gh api graphql -f query=\"$Q\"",
            "Q=$(cat q); gh api graphql -f query=\"$Q\"", "gh api graphql -f query=\"$Q\"; Q='query{a}'",
            "Q='query{a}'; Q+='mutation{x}'; gh api graphql -f query=\"$Q\"",
            "gh api graphql -f query=\"$1\"",
            # a binding in another scope, or one that may not run: the later $Q is whatever the environment holds
            "( Q='query{a}' ); gh api graphql -f query=\"$Q\"", "false && Q='query{a}'; gh api graphql -f query=\"$Q\"",
            "true || Q='query{a}'; gh api graphql -f query=\"$Q\"", "if c; then Q='query{a}'; fi; gh api graphql -f query=\"$Q\"",
            "for i in 1; do Q='query{a}'; done; gh api graphql -f query=\"$Q\"", "Q='query{a}' | cat; gh api graphql -f query=\"$Q\"",
            "bash -c \"Q='query{a}'\"; gh api graphql -f query=\"$Q\"", "Q='query{a}' & gh api graphql -f query=\"$Q\"",
            # #1617 review: an assignment INSIDE double quotes (`${Q:=...}`, `$(...)`), and a name that is an alias of another (`declare -n`)
            "Q=''; : \"${Q:=mutation{mergePullRequest(input:{pullRequestId:\\\"PR_x\\\"}){x}}}\"; gh api graphql -f query=\"$Q\"",
            "Q='query{a}'; : \"$(Q=x)\"; gh api graphql -f query=\"$Q\"", "Q='query{a}'; : \"`Q=x`\"; gh api graphql -f query=\"$Q\"",
            "declare -n Q=R; R='mutation{mergePullRequest(input:{pullRequestId:\"PR_x\"}){x}}'; gh api graphql -f query=\"$Q\"",
            "typeset -n Q=R; R='mutation{mergePullRequest(input:{pullRequestId:\"PR_x\"}){x}}'; gh api graphql -f query=\"$Q\"",
            "local Q='query{a}'; gh api graphql -f query=\"$Q\"", "readonly Q='query{a}'; gh api graphql -f query=\"$Q\"",
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
        # (#1571) what earlier segments of ONE command did to the branch the hook read before it ran
        # (#1571) the head a merge into main pins, in each of its three spellings
        ("gh pr merge 5 --match-head-commit abc1234", ["PR_MERGE 5 MATCH:abc1234"]),
        ("gh pr merge 5 --match-head-commit=ABC1234 --squash", ["PR_MERGE 5 MATCH:ABC1234"]),
        ("gh pr merge --match-head-commit abc1234 7", ["PR_MERGE 7 MATCH:abc1234"]),
        ("gh pr merge 5 --match-head-commit $H", ["PR_MERGE 5 MATCH:-"]),
        ("gh pr merge 5 --squash", ["PR_MERGE 5"]),
        ("gh api -X PUT repos/o/r/pulls/5/merge -f sha=abc1234 -f merge_method=merge", ["API_PR_MERGE 5 MATCH:abc1234"]),
        ("gh api -X PUT repos/o/r/pulls/5/merge -f sha=$H", ["API_PR_MERGE 5 MATCH:-"]),
        ("gh api graphql -f query='mutation{mergePullRequest(input:{pullRequestId:\"PR_kwDOA\",expectedHeadOid:\"abc1234\"}){clientMutationId}}'", ["GQL_PR PR_kwDOA MATCH:abc1234"]),
        ("gh api graphql -f query='mutation{mergePullRequest(input:{pullRequestId:\"PR_kwDOA\"}){clientMutationId}}'", ["GQL_PR PR_kwDOA"]),
        ("git switch main && git merge hotfix", ["GIT_MERGE_MAIN hotfix"]),
        ("git checkout main && git merge hotfix", ["GIT_MERGE hotfix", "GIT_MERGE_MAIN hotfix"]),   # `checkout main` may restore a PATH named main
        ("git checkout -q main; git merge hotfix", ["GIT_MERGE hotfix", "GIT_MERGE_MAIN hotfix"]),   # `checkout main` may restore a PATH named main
        ("git switch -C main && git merge hotfix", ["GIT_MERGE_MAIN hotfix"]),
        ("git -C . switch main && git merge hotfix", ["GIT_MERGE_MAIN hotfix"]),
        ("git switch main && git pull", ["GIT_PULL_MAIN"]),
        ("git switch topic && git merge hotfix", []),
        ("git checkout -b topic && git merge hotfix", []),
        ("git checkout --detach dev && git merge hotfix", []),
        ("git switch main && git switch topic && git merge hotfix", []),
        ("git checkout README.md && git merge hotfix", ["GIT_MERGE hotfix"]),
        ("git checkout main README.md && git merge hotfix", ["GIT_MERGE hotfix"]),
        ("git checkout -- README.md && git merge hotfix", ["GIT_MERGE hotfix"]),
        ("git branch -M main && git merge hotfix", ["GIT_MERGE hotfix", "GIT_MERGE_MAIN hotfix"]),
        ("git rebase dev main && git merge hotfix", ["GIT_MERGE hotfix", "GIT_MERGE_MAIN hotfix"]),
        ("git switch topic && git -C /elsewhere switch main && git merge hotfix", ["GIT_MERGE_MAIN hotfix"]),
        ("git status && git push origin dev:main", ["PUSH_REF dev"]),
        ("git fetch origin && git push origin dev:main", ["PUSH_REF dev"]),
        ("git switch topic && git push origin dev:main", ["PUSH_REF dev"]),
        ("git commit --allow-empty -m x && git push origin feature/x", []),
        # #1781 harmless controls: none of these moves HEAD, so a later push is judged as the hook saw it
        ("gh pr checkout 3", []), ("git stash; git status", []), ("git stash; git push origin HEAD", []), ("git stash pop; git push origin HEAD", []),
        ("git bisect log", []), ("git bisect log; git push origin HEAD", []), ("git worktree list; git push origin HEAD", []),
        ("git bisect --help; git push origin HEAD", []), ("git bisect -h", []),
        ("builtin trap 'git push origin main' EXIT", ["PUSH_MAIN main"]), ("command trap 'git push origin main' EXIT", ["PUSH_MAIN main"]),
        ("env trap 'git push origin main' EXIT", ["PUSH_MAIN main"]), ("f(){ trap 'git push origin main' EXIT; }; f", ["PUSH_MAIN main"]),
        ("{ trap 'git push origin main' EXIT; }", ["PUSH_MAIN main"]), ("if true; then trap 'git push origin main' EXIT; fi", ["PUSH_MAIN main"]),
        ("( trap 'git push origin main' EXIT )", ["PUSH_MAIN main"]), ("builtin trap - EXIT", []), ("f(){ trap 'echo bye' EXIT; }; f", []),
        # #1781: `trap` is found at ANY position, so no prefix list can leak; the echo case is a documented over-block (fail closed)
        ("function f { trap 'git push origin main' EXIT; }; f", ["PUSH_MAIN main"]), ("function f { { trap 'git push origin main' EXIT; }; }; f", ["PUSH_MAIN main"]),
        ("function f() { trap 'git push origin main' EXIT; }; f", ["PUSH_MAIN main"]),
        ("sudo -u r trap 'git push origin main' EXIT", ["PUSH_MAIN main"]), ("exec -a x trap 'git push origin main' EXIT", ["PUSH_MAIN main"]),
        ("nice -n 5 trap 'git push origin main' EXIT", ["PUSH_MAIN main"]), ("timeout 5 trap 'git push origin main' EXIT", ["PUSH_MAIN main"]),
        ("echo trap 'git push origin main'", ["PUSH_MAIN main"]), ("trap -- 'git push origin main' EXIT", ["PUSH_MAIN main"]),
        ("sudo trap -p", []), ("echo trap", []), ("trap -l", []),
        ("trap - EXIT", []), ("trap '' INT", []), ("trap -p", []), ("trap 'echo bye' EXIT", []),
        # a trap string is classified like `bash -c`'s
        ("trap 'git push origin main' EXIT", ["PUSH_MAIN main"]), ("trap 'git push origin main' EXIT; git status", ["PUSH_MAIN main"]),
        ("trap 'gh pr merge 7' EXIT", ["PR_MERGE 7"]),
    ]
    for cmd, want in ref_cases:
        try:
            got = cls(cmd, on_feature)
        except Unjudgeable as exc:
            got = [f"unjudgeable: {exc}"]
        if got != want:
            failures.append(f"classify {cmd!r}: expected {want}, got {got}")
    for cmd in ("gh pr checkout main; git push origin HEAD", "gh pr checkout 3; git push origin HEAD", "gh pr checkout 3 && git push origin HEAD",
                "git bisect start main; git push origin HEAD", "git bisect good; git push origin HEAD", "git bisect reset; git push origin HEAD",
                "git bisect run make; git push origin HEAD", "git worktree add -f x main; git push origin HEAD",
                "git worktree add -f x main; cd x; git push origin HEAD", "git stash branch b; git push origin HEAD",
                "trap 'git push origin $B' EXIT", "trap \"$CMD\" EXIT", "trap 'git push origin main' EXIT; echo 'unbalanced",
                "f(){ gh pr checkout 3; }; git push origin HEAD", "f(){ git bisect start main; }; f; git push origin HEAD",
                "f(){ git worktree add x main; }; f; git push origin HEAD", "f(){ git stash branch b; }; f; git push origin HEAD",
                "git switch $B && git merge hotfix", "git checkout - && git merge hotfix",
                "git switch main && git merge dev && git push origin main",
                "git commit --allow-empty -m x && git push origin main",
                "git fetch origin hotfix:main && git push origin main",
                "git switch hotfix && git push origin HEAD:main",
                "git merge $B", "git merge feat/{a,b}", "gh release edit --draft=false", "gh release edit v1 --draft=$D",
                "gh release edit $T --draft=false",
                "gh api -X PATCH repos/o/r/releases/$I -F draft=false", "gh api -X PATCH repos/o/r/releases/latest -F draft=false",
                "gh api -X PATCH repos/o/r/releases/9 -F draft=$D"):
        try:
            cls(cmd, on_feature)
            failures.append(f"classify {cmd!r}: must be unjudgeable (the hook denies)")
        except Unjudgeable:
            pass
    api_total += len(ref_cases) + 15 + 17
    # #1569 -- the parser differential. The same command, spelled the way bash reads it differently from
    # shlex: every transformation must give the SAME effects as the plain spelling, or be unjudgeable
    # (the hook denies). Never "no effect".
    fuzz_bases = [
        ("gh api -X PUT repos/o/r/pulls/7/merge", ["API_PR_MERGE 7"]),
        ("gh api repos/o/r/merges -f base=main -f head=hot", ["API_MERGE hot"]),
        ("gh api -X PATCH repos/o/r/git/refs/heads/main -f sha=abc", ["API_REF abc"]),
        ("gh api repos/o/r/releases -f tag_name=v1", ["RELEASE v1 -"]),
        ("gh release create v1 --target main", ["RELEASE v1 main"]),
        ("gh release edit v1 --draft=false", ["RELEASE_EDIT v1 -"]),
        ("gh pr merge 7 --merge", ["PR_MERGE 7"]),
        ("git merge hotfix", ["GIT_MERGE hotfix"]),
        ("git push origin hot:main", ["PUSH_REF hot"]),
    ]

    def words(c):
        return c.split(" ")

    def ansi(w, fmt):
        return "$'" + "".join(fmt(ord(ch)) for ch in w) + "'"

    transforms = {
        "single-quoted words": lambda c: " ".join("'" + w + "'" for w in words(c)),
        "double-quoted words": lambda c: " ".join('"' + w + '"' for w in words(c)),
        "empty quotes inside a word": lambda c: " ".join(w[:1] + "''" + w[1:] for w in words(c)),
        "backslash inside a word": lambda c: " ".join(w[:1] + "\\" + w[1:] if w[:1].isalpha() else w for w in words(c)),
        "ANSI-C hex words": lambda c: " ".join(ansi(w, lambda o: "\\x%02x" % o) for w in words(c)),
        "ANSI-C octal words": lambda c: " ".join(ansi(w, lambda o: "\\%03o" % o) for w in words(c)),
        "ANSI-C command word only": lambda c: ansi(words(c)[0], lambda o: "\\x%02x" % o) + " " + " ".join(words(c)[1:]),
        "ANSI-C mid-word": lambda c: " ".join(w[:1] + "$'" + w[1:] + "'" if w[:1].isalpha() else w for w in words(c)),
        "locale $\"..\"": lambda c: " ".join('$"' + w + '"' for w in words(c)),
        "line continuations": lambda c: " \\\n".join(words(c)),
        "trailing comment": lambda c: c + " # push main",
        "$IFS for spaces": lambda c: "${IFS}".join(words(c)),
        "bare $IFS": lambda c: "$IFS".join(words(c)),
        "brace-built command word": lambda c: c.replace("gh", "g{h,}", 1).replace("git", "gi{t,}", 1),
        "variable command word": lambda c: "$cmd " + " ".join(words(c)[1:]),
        "env prefix": lambda c: "A=1 " + c, "env wrapper": lambda c: "env A=1 " + c,
        "command wrapper": lambda c: "command " + c, "timeout wrapper": lambda c: "timeout 5 " + c,
        "subshell": lambda c: "( " + c + " )", "group": lambda c: "{ " + c + "; }",
        "substitution": lambda c: "x=$(" + c + ")", "backticks": lambda c: "x=`" + c + "`",
        "bash -c": lambda c: "bash -c '" + c + "'", "eval": lambda c: "eval " + c,
        "second line": lambda c: "true\n" + c, "after &&": lambda c: "true && " + c, "backgrounded": lambda c: c + " &",
    }
    must_be_unjudgeable = {"$IFS for spaces", "bare $IFS", "brace-built command word", "variable command word"}
    fuzz_total = 0
    for base, want in fuzz_bases:
        for name, tf in transforms.items():
            fuzz_total += 1
            cmd = tf(base)
            try:
                got = cls(cmd, on_feature)
            except Unjudgeable:
                continue
            if name in must_be_unjudgeable or got != want:
                failures.append(f"fuzz [{name}] {cmd!r}: expected {want} or unjudgeable, got {got}")
    # Context: which repository, which directory, which remote (#1569).
    ctx_cases = [
        ("gh pr merge 7 -R o/r", ["CTX o/r -", "PR_MERGE 7"]),
        ("gh pr merge -R=o/r 7", None), ("gh pr merge --repo o/r 7", ["CTX o/r -", "PR_MERGE 7"]),
        ("gh pr -R o/r merge 7", ["CTX o/r -", "PR_MERGE 7"]), ("gh -R o/r pr merge 7", ["CTX o/r -", "PR_MERGE 7"]),
        ("gh pr merge 7 -Ro/r", ["CTX o/r -", "PR_MERGE 7"]),
        ("GH_REPO=o/r gh pr merge 7", ["CTX o/r -", "PR_MERGE 7"]), ("env GH_REPO=o/r gh pr merge 7", ["CTX o/r -", "PR_MERGE 7"]),
        ("export GH_REPO=a/b; gh release create v1", ["CTX a/b -", "RELEASE v1 -"]),
        ("GH_REPO=a/b; gh release create v1", ["CTX a/b -", "RELEASE v1 -"]),
        ("gh release create v1 -R x/y --target main", ["CTX x/y -", "RELEASE v1 main"]),
        ("gh release edit v1 --draft=false -R x/y", ["CTX x/y -", "RELEASE_EDIT v1 -"]),
        ("gh api -X PUT repos/x/y/pulls/3/merge", ["CTX x/y -", "API_PR_MERGE 3"]),
        ("GH_REPO=a/b gh api -X PUT repos/{owner}/{repo}/pulls/3/merge", ["CTX a/b -", "API_PR_MERGE 3"]),
        ("gh api -X PUT repos/{owner}/{repo}/pulls/3/merge", ["CTX - -", "API_PR_MERGE 3"]),
        ("git push upstream hot:main", ["CTX remote:upstream -", "PUSH_REF hot"]),
        ("git push origin main", ["CTX remote:origin -", "PUSH_MAIN main"]),
        ("git push git@github.com:x/y.git hot:main", ["CTX remote:git@github.com:x/y.git -", "PUSH_REF hot"]),
        ("cd sub && git merge dev", ["CTX - sub", "GIT_MERGE dev"]),
        ("cd /a/b; cd ../c; gh pr merge 7", ["CTX - /a/b/../c", "PR_MERGE 7"]),
        ("git -C ../x merge dev", ["CTX - ../x", "GIT_MERGE dev"]),
        ("git -C /abs push origin hot:main", ["CTX remote:origin /abs", "PUSH_REF hot"]),
        # (#1764) the home directory is expanded; another user's (`~someone`) and any other variable are not, so they stay unresolved
        ("git -C ~/proj push origin hot:main", ["CTX remote:origin /home/selftest/proj", "PUSH_REF hot"]),
        ("cd $HOME/proj && git merge dev", ["CTX - /home/selftest/proj", "GIT_MERGE dev"]),
        ("git -C ~someone/proj merge dev", ["CTX - ~someone/proj", "GIT_MERGE dev"]),
        ('git -C "$HOME/proj" push origin hot:main', ["CTX remote:origin /home/selftest/proj", "PUSH_REF hot"]),
        ("git -C '~/proj' push origin hot:main", ["CTX remote:origin ~/proj", "PUSH_REF hot"]),
        ("git merge dev", ["CTX - -", "GIT_MERGE dev"]),
        ("gh api repos/o/r/merges -f base=main -f head=dev", ["CTX o/r -", "API_MERGE dev"]),
        ("gh api -iXPUT repos/o/r/pulls/7/merge", ["CTX o/r -", "API_PR_MERGE 7"]),
        ("gh api -siXPUT repos/o/r/pulls/7/merge", ["CTX o/r -", "API_PR_MERGE 7"]),
        ("gh api -i -XPUT repos/o/r/pulls/7/merge", ["CTX o/r -", "API_PR_MERGE 7"]),
        ("gh api -ifsha=abc -X PATCH repos/o/r/git/refs/heads/main", ["CTX o/r -", "API_REF abc"]),
        ("gh api repos/o/r/merges -ffbase=main", None),
    ]
    ctx_total = 0
    for cmd, want in ctx_cases:
        if want is None:
            continue
        ctx_total += 1
        try:
            got = classify(cmd, on_feature)
        except Unjudgeable as exc:
            got = [f"unjudgeable: {exc}"]
        if got != want:
            failures.append(f"classify (context) {cmd!r}: expected {want}, got {got}")
    for cmd in ("cd; gh pr merge 7", "cd - && git merge dev", "cd $D && git merge dev", "GH_REPO=$R gh pr merge 7",
                "GH_REPO=https://github.com/o/r gh pr merge 7", "gh pr merge 7 -R github.example.com/o/r",
                "gh api --hostname ghe.example.com -X PUT repos/o/r/pulls/7/merge", "gh api -X PATCH",
                "git push $REMOTE hot:main"):
        ctx_total += 1
        try:
            classify(cmd, on_feature)
            failures.append(f"classify {cmd!r}: must be unjudgeable (the hook denies)")
        except Unjudgeable:
            pass
    api_total += fuzz_total + ctx_total
    # #1569: fail closed BY CONSTRUCTION. A gh or git the gate does not recognise is not "no effect".
    safe_cases = [
        "git status", "git log --oneline -5", "git diff HEAD~1 -- app.rb", "git fetch origin", "git add -A", "git commit -m 'x y'",
        "git checkout -b feature/x", "git push -u origin feature/x", "git branch -D old", "git -c user.name=x -c user.email=y commit -m z",
        "git -C /tmp/x status", "git config --get remote.origin.url", "git config user.email a@b", "git remote -v",
        # (#1768) a bare `git config <key>` is a READ of that key, whichever key it is
        "git config get core.hooksPath", "git config list", "git config get --local remote.origin.url",
        "git config core.hooksPath", "git config --local core.hooksPath", "git config --global core.hooksPath", "git config --file .git/config core.hooksPath",
        "git config remote.origin.url", "git config --local url.x.insteadOf",
        "git remote add up https://github.com/o/r", "git stash pop", "git rebase dev", "git reset --hard HEAD~1",
        "git cherry-pick abc123", "git rev-parse HEAD", "git --no-pager log", "git --version", "git",
        "gh pr view 7", "gh pr list --state open", "gh pr create --title t --body b", "gh pr checks 7", "gh pr checkout 7",
        "gh issue create -t x", "gh issue list", "gh run list", "gh run view 5 --log", "gh workflow list", "gh release list",
        "gh release view v1", "gh repo view", "gh auth status", "gh --version", "gh",
        "gh api repos/o/r/pulls/7", "gh api -X GET repos/o/r/issues", "gh api -X POST repos/o/r/issues/1/comments -f body=hi",
        "gh api -X PATCH repos/o/r/pulls/7 -f title=x", "gh api graphql -f query='query{viewer{login}}'",
        "gh api graphql -f query='mutation{addComment(input:{subjectId:\"x\",body:\"y\"}){clientMutationId}}'",
        "echo git push origin main", "which gh", "grep -r git .", "type -a git", "ls git", "python3 x.py git", "make gh",
        "cd /tmp && git status",
    ]
    for cmd in safe_cases:
        api_total += 1
        try:
            got = cls(cmd, on_feature)
        except Unjudgeable as exc:
            got = f"unjudgeable: {exc}"
        if got != []:
            failures.append(f"safe shape {cmd!r}: must be allowed with no effect, got {got}")
    unlisted = [
        "git ci -m x", "git -c core.sshCommand=x push origin feature/x", "git -c url.x.insteadOf=y push origin feature/x",
        "git --weird-option status", "git $V push origin feature/x", "git remote set-url origin https://github.com/x/y",
        "git remote remove origin", "git config remote.origin.url https://github.com/x/y", "git config url.x.insteadOf y",
        # (#1768) ...but a value, a write flag, or a word the hook cannot read is a WRITE (or could be): still refused
        "git config core.hooksPath /tmp/x", "git config --local core.hooksPath ''", "git config --add core.hooksPath /tmp/x",
        "git config --unset core.hooksPath", "git config --unset-all remote.origin.url", "git config --replace-all remote.origin.url x",
        "git config -e", "git config --edit", "git config --rename-section remote.origin remote.up", "git config --remove-section remote.origin",
        "git config $KEY", "git config core.hooksPath $VALUE", "git config remote.$NAME.url",
        # (#1768 review) the sub-commands of newer git (`edit` opens the editor on the config), and abbreviated long options (git accepts any unambiguous prefix)
        # (#1768 review) `get` and `list` are sub-commands only in the FIRST position: as a VALUE they are a write (`git config core.hooksPath get` points the hooks at ./get)
        "git config core.hooksPath get", "git config core.hooksPath list", "git config remote.origin.url list",
        "git config edit", "git config set core.hooksPath /tmp/x", "git config unset core.hooksPath", "git config --unset-a core.hooksPath",
        "git config --edi", "git config --uns core.hooksPath", "git config --remove-s remote.origin", "git config -z -e",
        "git send-pack origin main", "git update-ref refs/heads/main abc", "git symbolic-ref HEAD refs/heads/x",
        "git filter-branch -f", "git fast-import", "git svn dcommit", "git http-push x",
        "gh workflow run release.yml", "gh pr update-branch 7", "gh repo sync", "gh repo delete x --yes", "gh release delete v1",
        "gh foo", "gh $x", "gh pr $verb 7", "gh api -X POST repos/o/r/dispatches -f event_type=x",
        "gh api -X POST repos/o/r/deployments -f ref=main", "gh api -X PUT repos/o/r/pulls/7/update-branch",
        "gh api -X POST repos/o/r/merge-upstream -f branch=main", "gh api -X POST repos/o/r/transfer",
        "gh api graphql -f query='mutation{mergeBranch(input:{}){x}}'",
        "gh api graphql -f query='mutation{createDeployment(input:{}){x}}'",
        "alias gm='git merge'",
        "git merge $((1+1))", "git push origin $((1+1))",
    ]
    for cmd in unlisted:
        api_total += 1
        try:
            got = cls(cmd, on_feature)
            failures.append(f"unlisted shape {cmd!r}: must be unjudgeable (the hook denies), got {got}")
        except Unjudgeable:
            pass
    # A bare gh or git word under an unknown command may BE the command it runs.
    for cmd, want in (("find . -name x -exec git push origin main ;", ["PUSH_MAIN main"]),
                      ("parallel git merge ::: a b", ["GIT_MERGE ::: a b"]), ("watch -n 5 gh pr merge 7", ["PR_MERGE 7"]),
                      ("sudo -u bob git merge dev", ["GIT_MERGE dev"]), ("git pull", ["GIT_PULL"]),
                      ("echo gh pr merge 7", []), ("grep git push", [])):
        api_total += 1
        try:
            got = cls(cmd, on_feature)
        except Unjudgeable as exc:
            got = [f"unjudgeable: {exc}"]
        if got != want:
            failures.append(f"classify {cmd!r}: expected {want}, got {got}")
    # (#1770) A function body is judged where it is written, as the same commands would be inline; what a call site could change under that model is refused.
    # want None = Unjudgeable (the gate refuses); a list = the effect lines.
    push_main = ["PUSH_MAIN main"]
    for cmd, want in (
            ("g(){ echo hi; }; g", []), ("g(){ git grep -n \"$1\" HEAD; }; g x", []),
            ("g() { echo hi; } && g", []), ("g(){\n  echo hi\n}\ng", []), ("function g { echo hi; }; g", []), ("function g() { echo hi; }; g", []),
            ("f(){ git push origin main; }; f", push_main), ("f(){ git push origin main; }", push_main),         # never called: judged as if called, since a call can come from anywhere
            ("f(){\n  git push origin main\n}\nf", push_main), ("function f { git push origin main; }; f", push_main),
            ("function f() { git push origin main; }; f", push_main), ("f; f(){ git push origin main; }", push_main),
            ("git(){ command git push origin main; }; git status", push_main), ("g(){ echo hi; }; g(){ git push origin main; }; g", push_main),
            ("g(){ git push origin main; }; g(){ echo hi; }; g", push_main),                                        # the first body may have run: both are judged
            ("a(){ b(){ git push origin main; }; b; }; a", push_main), ("f(){ f; git push origin main; }; f", push_main),
            ("f(){ ( git push origin main ); }; f", push_main), ("f() ( git push origin main ); f", push_main),
            ("f(){ git merge x; }; f", None), ("foo() { gh pr merge 7; }; foo", ["PR_MERGE 7"]),
            ("f(){ git push origin feat/x; }; f", []), ("function f", []),
            ("f(){ git push \"$@\"; }; f origin main", None), ("f(){ git push origin $1; }; f main", None), ("f(){ git push origin \"${1}\"; }; f main", None),
            ("f(){ git push origin \"$*\"; }; f main", None), ("f(){ shift; git push origin \"$1\"; }; f x main", None),
            ("f(){ git \"$@\"; }; f push origin main", None), ("f(){ \"$@\"; }; f git push origin main", None), ("f(){ $1 push origin main; }; f git", None),
            ("f(){ eval \"$1\"; }; f 'git push origin main'", None), ("f(){ eval git push origin main; }; f", push_main),
            ("f(){ bash -c 'git push origin main'; }; f", push_main), ("f(){ cd /tmp; }; git push", None), ("f(){ git push; }; cd /x; f", None),
            ("f(){ git checkout dev; }; f; git push", None), ("git checkout dev; f(){ git push; }; f", None), ("f(){ git push; }; GIT_DIR=/x f", None),
            ("function $x { echo; }", None), ("alias g='git push origin main'; g", None)):
        api_total += 1
        try:
            got = cls(cmd.replace("\\n", "\n"), on_feature)
        except Unjudgeable as exc:
            got = None
        if got != want:
            failures.append(f"function fixture {cmd!r}: expected {want}, got {got}")
    # #1781: the inline model and the function check read ONE definition of what moves HEAD (the function check folds each verb through `_Flow`),
    # so every verb the inline model refuses must be refused when a function is defined too.
    for names in GH_HEAD_MOVING:
        probe = f"f(){{ gh {' '.join(names)} 3; }}; f"
        try:
            cls(probe, on_feature)
            failures.append(f"function check does not refuse the HEAD-moving gh subcommand {names}")
        except Unjudgeable:
            pass
    for verb, args in (("bisect", ["start"]), ("worktree", ["add", "x"]), ("stash", ["branch", "b"])):
        flow = _Flow()
        flow.after(verb, args, None)
        if not (flow.head_moved and flow.unknown_dir):
            failures.append(f"git {verb} {' '.join(args)} must move HEAD in the flow model")
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
