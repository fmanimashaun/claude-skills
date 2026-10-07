#!/usr/bin/env python3
"""Refuse a `gh issue create` whose labels miss the project's declared groups (#1311).

WHY. Issue templates apply labels only through the GitHub web form. Agents file with
`gh issue create`, which bypasses the template, so issues arrived with no labels at all: 12 of 14
open in one consumer, and `type:`/`prio:` missing from most of a maintainer repo's recent issues.
A rule in prose changed nothing; this runs on the command itself.

THE DECLARATION: `.rails-flow/issue-labels.json` at the project root.
    {"groups": [
       {"one_of": ["bug", "feature", "enhancement"]},
       {"when": "bug", "one_of": ["severity:s1", "severity:s2", "severity:s3", "severity:s4"]}
    ]}
A value ending in `*` is a prefix (`comp:*`). A group with `when` applies only if that label is set.
Undeclared, or `-R/--repo` naming another repository (whose taxonomy is not ours): at least one label.

THE DECLARATION IS THE TARGET REPOSITORY'S, not the session's (#1400). A coordinator working from one
checkout runs `cd /path/to/other-repo && gh issue create ...`; the issue lands in the other repo, so
its labels answer to the other repo's declaration. The hook used to read the session's file, refused
a correctly labelled issue, and asked for labels the other repo does not have. So a create written
`cd <literal path> && gh issue create …` is judged by that directory's git toplevel, which
supplies both the declaration and the "is this our repo" answer for `-R`. Any OTHER shape with a
`cd` in it is refused rather than guessed (see `issue_creates`), because a guess applies one repo's
rules to another's issue -- the defect itself, in a different direction.

Called by guard-bash.sh with the RAW command on stdin (the normalised form strips quotes, and a label
value is usually quoted). Prints the refusal and exits 1; exits 0 to allow. The hook fails closed on
any other exit.

Run:  issue_labels.py [--root DIR] < command.txt
      issue_labels.py --selftest
"""
from __future__ import annotations

import bisect
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

CONFIG = Path(".rails-flow/issue-labels.json")


HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*(\\?)(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\3")  # not <<< (a herestring)


def strip_heredocs(cmd: str, bodies: list | None = None) -> str:
    """Drop every heredoc BODY, keeping the line that opens it (#1336).

    Our own doctrine says to write issue bodies with a quoted heredoc and `--body-file`, never through
    double quotes. A body is prose, so it holds apostrophes and backticks, and shlex read those as an
    unterminated quote and refused a correctly labelled `gh issue create` in the same call. The body
    is data the shell never tokenises, so it is not ours to parse either.

    A heredoc whose closing tag never arrives raises ValueError -- a refusal -- when the lines it
    would swallow hold a `gh issue create`, because a create nobody sees is a create let through.
    Otherwise it is a quoted mention or arithmetic, and is left alone. `<<<` is a herestring, not a
    heredoc: it has no body to strip.

    `bodies`, when given, collects `(opener line, delimiter quoted?, body)` for every heredoc, so
    `hidden_create` can judge the two kinds that really RUN: a body fed to a shell, and an unquoted
    body's substitutions (#1462, #1467). A quoted delimiter (`<<'EOF'`, `<<"EOF"`, `<<\\EOF`) makes the
    body literal; an unquoted one substitutes `$(…)` and backticks.
    """
    lines = cmd.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        for m in HEREDOC.finditer(line):
            before = line[:m.start()]
            if before.count("'") % 2:
                continue            # inside single quotes `<<X` is text
            if before.count('"') % 2 and "$(" not in before[before.rfind('"'):]:
                continue            # inside double quotes too -- unless a `$(` opened since: `"$(cat <<'EOF'`
            tag, dash = m.group(4), m.group(1) == "-"
            quoted = bool(m.group(2) or m.group(3))
            start_of_swallow = i
            while i < len(lines) and (lines[i].lstrip("\t") if dash else lines[i]) != tag:
                i += 1
            if i >= len(lines):
                # Never closed. Usually a quoted mention (`--body 'a<<EOF'`) or arithmetic
                # (`$((1<<n))`), which is harmless -- UNLESS the lines it would swallow hold a
                # `gh issue create`, which would then go unchecked. Refuse only that.
                if re.search(r"\bgh\s+issue\s+create\b", "\n".join(lines[start_of_swallow:])):
                    raise ValueError(f"heredoc <<{tag} is never closed")
                break
            if bodies is not None:
                bodies.append((line, quoted, "\n".join(lines[start_of_swallow:i])))
            i += 1  # the closing tag line
    return "\n".join(out)


def _strip_comments(text: str) -> str:
    """Drop every shell comment, quote-aware and PER LINE, before the lines are joined (#1645 review R1).

    `issue_creates` and `hidden_create` turn each newline into ` ; ` and then run `shlex`, whose default `commenters` is `#`: the first `#` in the
    whole command commented out EVERYTHING after it, so `# note` + newline + an unlabelled create was allowed (on dev too). A `#` starts a comment
    only at the start of a word (after whitespace or a separator) and outside quotes; it runs to the end of THAT line. A `#` inside a word (`a#b`),
    inside quotes (`"see #12"`) or in a heredoc body (stripped earlier) is text."""
    out: list[str] = []
    i, n, quote = 0, len(text), ""
    while i < n:
        c = text[i]
        if quote:
            out.append(c)
            if c == "\\" and quote == '"' and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == quote:
                quote = ""
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append(c)
            out.append(text[i + 1])
            i += 2
            continue
        if c in "'\"":
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "#" and (not out or out[-1] in " \t\n;&|()"):
            while i < n and text[i] != "\n":
                i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def issue_creates(cmd: str) -> list[tuple[list[str], str | None, str | None]]:
    """(argv, the directory it runs in, a GH_REPO prefix) for every `gh issue create` in the command.

    The directory is None (the session's) or a literal `cd` operand, and a `cd` is followed in
    exactly ONE shape (#1400):

        cd <literal path> && gh issue create …

    `cd` is the command's first word, `&&` joins it DIRECTLY to the create, and the create is its
    segment's first word (a `GH_REPO=` prefix aside, which `verdict` treats as naming a repo).
    Every other shape -- no cd, or a cd anywhere else -- is None: the session's rules, exactly as
    before #1400. Why so narrow: five independent reviews of broader versions each found a shape
    where ANOTHER repo's rules were applied to a create that did not land there (a subshell `cd`,
    `cd -`, `||`, compound bodies, a `case` `)`, `time`, `export GIT_DIR=`, `env -C`). The session's
    rules are the check the same create gets with no cd at all, so falling back to them cannot let
    anything through that was refused before; `verdict` adds the remaining certainty checks.
    """
    try:
        cmd = _ansi_c(strip_heredocs(cmd))
    except ValueError:
        return _unparseable(cmd)
    cmd = _strip_comments(cmd).replace("\\\n", "").replace("\n", " ; ")   # comments go first: `# note \<nl>` ends at the newline in a shell; a backslash-newline outside one JOINS (`cre\\<nl>ate`) (#1645 R1)
    # The followed cd shape is checked on the RAW text too (#1440): shlex drops quotes, so a quoted
    # `'&&'` would otherwise read as the separator. The operand may itself be quoted.
    raw_cd_shape = bool(re.match(r"""\s*cd\s+('[^']*'|"[^"]*"|[^\s'"&;|()]+)\s*&&""", cmd))
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()")
        lexer.commenters = ""            # (#1645 R1) comments are stripped line by line by `_strip_comments`; shlex's own would eat everything after the first `#`
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return _unparseable(cmd)
    # shlex glues adjacent punctuation (`);`, `&&(`). A glued run is read as a word, which can only
    # keep the exact cd shape from matching -- and then the session's rules apply. It never hides a
    # create: `gh issue create` is found anywhere in its segment.
    split = tokens
    # A newline right after `&&` / `||` / `|` continues that chain; drop the `;` it became.
    items: list[str] = []
    for tok in split:
        if tok == ";" and items and items[-1] in ("&&", "||", "|"):
            continue
        items.append(tok)

    out: list[tuple[list[str], str | None, str | None]] = []
    seg: list[str] = []
    start = 0                    # index in `items` where `seg` began
    for k, tok in enumerate(items + [";"]):
        if tok in ("(", ")") or (tok and set(tok) <= set(";&|")):
            words = list(seg)
            env = {}
            while words and "=" in words[0] and words[0].split("=", 1)[0].isidentifier():
                name, _, value = words.pop(0).partition("=")
                env[name] = value
            for i in range(len(words)):
                # Any path to gh is gh (`/usr/bin/gh issue create`, #1423); `new` is gh's alias for
                # `create`, and gh takes global flags before the subcommand (`gh --repo o/r issue
                # create`, #1462). A repo named there is carried into the create's own arguments.
                after, lead = gh_issue_create_at(words, i)
                if after is not None:
                    cd = _cd_in_force(items[:start]) if raw_cd_shape else None
                    # After a followed cd, the create must BE the segment -- no `env -C`, no
                    # `command`, no GIT_DIR=: each sends the create somewhere the cd did not.
                    if cd is not None and (i != 0 or set(env) - {"GH_REPO"}):
                        cd = None
                    out.append((lead + words[after:], cd, env.get("GH_REPO")))
                    break
            seg, start = [], k + 1
        else:
            seg.append(tok)
    return out


def _cd_in_force(prefix: list[str]) -> str | None:
    """The cd target when everything before the create's segment is EXACTLY `cd <literal> &&`.

    Anything else is None: judged in the session's directory, which is what the hook did before
    #1400 and is the one answer that cannot leak (see `verdict`).
    """
    # That the first word IS `cd`, with an unquoted `&&` after its operand, is checked on the raw text
    # (`raw_cd_shape`), which sees quotes; here only the token shape of the prefix remains.
    if len(prefix) != 3 or prefix[2] != "&&":
        return None
    # A `-`, `$VAR` or backtick operand names no directory the text can see, so target_root finds
    # nothing there and the session's rules apply -- no special case needed.
    return prefix[1]


# `gh [global flags] issue create|new`, quote characters removed first (see `_names_create`).
# The path prefix stops at a separator (`[^\s`(;&|/]*/`, not `\S*/`): from every `(` of `$($($(` a `\S*` ran to the end of the token, so it was quadratic; a prefix that
# held a separator is matched from the LATER start point anyway.
CREATE_TEXT = re.compile(r"(?:^|[\s`(;&|])(?:[^\s`(;&|/]*/)*gh(?:\s+-\S+(?:\s+[^-\s]\S*)?)*\s+issue\s+(?:create|new)\b")


def _names_create(text: str) -> bool:
    """Does TEXT, once run, name a create? Quotes are removed first, because a shell joins
    `gh issue "create"` into the same words (#1462); a backslash-newline joins lines."""
    return bool(CREATE_TEXT.search(" " + text.replace("\\\n", "").replace('"', "").replace("'", "")))
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
# A shell reading a redirect, as guard-bash.sh's trigger spells it (#1489): `/bin/bash < f`,
# `bash --norc < f`, `sh<f`, `bash 0< f`. Coarse on purpose; the parser decides.
SHELL_REDIRECT = re.compile(r"(?:^|[\s;&|(/])(?:sh|bash|zsh|dash|ksh)(?:\s[^;&|]*)?<(?:[^<(]|$)")


def _unparseable(cmd: str) -> list:
    """An unparseable command is refused only when it could be hiding a create: it names one, or a
    shell reads a redirect. Anything else is valid bash this parser merely cannot read (#1489 review:
    `echo $'it\\'s'; bash < h.sh` was refused), and was allowed before the trigger widened."""
    if _names_create(cmd) or SHELL_REDIRECT.search(cmd):
        return [(["__unparseable__"], None, None)]
    return []


# bash's `$'…'` escapes (#1495): `$'\x62ug'` is `bug`, so a label written that way is the label.
_ANSI_SIMPLE = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r",
                "t": "\t", "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}


def _ansi_escape(text: str, j: int) -> tuple[str, int]:
    r"""The character a `$'…'` escape starting at TEXT[j] (just past the backslash) means, and the
    index after it: the simple letters, `\NNN` octal, `\xHH`, `\uHHHH`, `\UHHHHHHHH`, `\cX`."""
    c = text[j]
    if c in _ANSI_SIMPLE:
        return _ANSI_SIMPLE[c], j + 1
    for lead, digits, width, base in (("x", "0123456789abcdefABCDEF", 2, 16),
                                      ("u", "0123456789abcdefABCDEF", 4, 16),
                                      ("U", "0123456789abcdefABCDEF", 8, 16)):
        if c == lead:
            k = j + 1
            while k < len(text) and k - j - 1 < width and text[k] in digits:
                k += 1
            if k == j + 1:
                return "\\" + c, j + 1          # no digits: bash keeps it literally
            try:
                return chr(int(text[j + 1:k], base)), k
            except (ValueError, OverflowError):
                return "", k
    if c in "01234567":
        k = j
        while k < len(text) and k - j < 3 and text[k] in "01234567":
            k += 1
        return chr(int(text[j:k], 8) & 0xFF), k
    if c == "c" and j + 1 < len(text):
        return chr(ord(text[j + 1].upper()) ^ 0x40), j + 2
    return "\\" + c, j + 1                       # unknown: bash keeps the backslash


def _fold_fd_redirects(text: str) -> str:
    r"""`2>&1`, `<&0`, `>&-` and `&>log` written so shlex does not split them at `&` (#1495): split,
    `bash 2>&1 < f` became `bash 2>`, `&`, `1 < f`, and the shell lost its redirect. The `&` of a
    duplication becomes `@`; `&>` / `&>>` (stdout and stderr) become `>` / `>>`."""
    text = re.sub(r"(\d*[<>])&(\d+|-)", r"\1@\2", text)
    text = re.sub(r"(\d*>)&(?=[^\s\d-])", r"\1", text)      # `>&log` is `>log` (#1513 review)
    return re.sub(r"(?<![&|<>])&(>>?)", r"\1", text)


# A word cut at its redirect operators, so `bash>/dev/null<bad.sh` is `bash`, `>/dev/null`, `<bad.sh`.
_REDIR_PIECES = re.compile(r"\d*(?:<<<|<<|>>|<>|[<>])@?[^<>\s]*|[^<>\s]+")


def _split_redirects(words: list[str]) -> list[str]:
    return [piece for w in words for piece in (_REDIR_PIECES.findall(w) or [w])]


# Redirect words and their separate targets, which are not arguments: `cd sub &>/dev/null` is `cd sub`.
def _drop_redirects(words: list[str]) -> list[str]:
    out, k = [], 0
    while k < len(words):
        w = words[k]
        if re.fullmatch(r"\d*(?:>>|<>|[<>])@?", w):
            k += 2               # the operator alone: its target is the next word
            continue
        if re.fullmatch(r"\d*(?:>>|<>|[<>])@?\S+", w):
            k += 1
            continue
        out.append(w); k += 1
    return out


def _ansi_c(cmd: str) -> str:
    """`$'…'` (ANSI-C quoting) rewritten as the single-quoted string it means, so shlex can read it.
    Only outside quotes: inside `'…'` or `"…"` a `$'` is literal text."""
    out, q, i = [], "", 0
    while i < len(cmd):
        ch = cmd[i]
        if q == "'":
            q = "" if ch == "'" else q
        elif ch == "\\" and q != "'":
            out.append(cmd[i:i + 2]); i += 2
            continue
        elif ch == '"':
            q = "" if q == '"' else '"'
        elif ch == "'" and not q:
            q = "'"
        elif not q and cmd.startswith("$'", i):
            j, val = i + 2, []
            while j < len(cmd) and cmd[j] != "'":
                if cmd[j] == "\\" and j + 1 < len(cmd):
                    ch_, j = _ansi_escape(cmd, j + 1)
                    val.append(ch_)
                    continue
                val.append(cmd[j]); j += 1
            out.append(shlex.quote("".join(val))); i = j + 1
            continue
        out.append(ch); i += 1
    return "".join(out)
WRAPPERS = {"env", "sudo", "command", "builtin", "exec", "nohup", "timeout", "nice", "time", "xargs"}


_MAX_DEPTH = 3     # how many levels of "a shell runs text that runs text" are followed; deeper is not claimed (#1645)


def _runs(text: str, depth: int, cwd: Path | None) -> bool:
    """Would a shell that RUNS `text` (a script file, a heredoc body, a `-c` string, text piped in) file an issue?

    The words `gh issue create` anywhere in it, OR any indirect shape `hidden_create` refuses (an alias, a function wrapper, `$G`, `xargs gh`,
    another script it reads, a nested `-c`), judged by the same rules as the command line itself, to `_MAX_DEPTH` levels (#1645 R2: part B was
    applied to the command line only, so the shapes it refuses passed one level down)."""
    if _names_create(text):
        return True
    return depth < _MAX_DEPTH and hidden_create(text, depth + 1, cwd) is not None


def hidden_create(cmd: str, depth: int = 0, cwd: Path | None = None) -> str | None:
    """A `gh issue create` the parser cannot label-check, named by its shape, or None (#1423).

    Owner decision (#1423): refuse, and say "run it directly". A create inside a command STRING runs
    as a create, but its labels are one quoted token here: `sh -c '…'`, `eval '…'`, backticks and
    `$( … )`. A plain mention -- `echo "gh issue create"`, a grep for it -- is text, not a command,
    and stays allowed: only a shell, `eval`, or a substitution EXECUTES the string.
    """
    heredocs: list = []
    base_dir = cwd if cwd is not None else Path.cwd()
    try:
        body = _ansi_c(strip_heredocs(cmd, heredocs))
    except ValueError:
        return None                  # the caller already refuses an unparseable command
    # HEREDOC BODIES THAT RUN (#1462, #1467). A body fed to a shell is a script; an UNQUOTED body
    # substitutes `$(…)` and backticks. A quoted-delimiter body fed to `cat` is text.
    for opener, quoted, text in heredocs:
        mark = opener.find("<<")
        # The body goes to the command that owns the `<<`, or -- `cat <<'EOF' | bash` -- through a
        # pipe to the command after it.
        after = opener[mark:]
        feeders = [_command_word(opener[:mark])] + ([_command_word(after)] if "|" in after else [])
        for feeder in feeders:
            # A body a shell runs has its escapes decoded first: `gh i\\ssue cr\\eate` is `gh issue create` to the shell (#1515).
            if (feeder in SHELLS or feeder == "eval") and (_runs(text, depth, base_dir) or _runs(re.sub(r"\\(.)", r"\1", text, flags=re.S), depth, base_dir)):
                return f"a heredoc fed to `{feeder}`"
        if not quoted:
            # An escaped character is literal in an unquoted body too: `\\`gh issue create\\`` is text.
            found = _substituted_create(re.sub(r"\\.", "", text, flags=re.S))
            if found:
                return f"{found} in an unquoted heredoc"
    # Inside SINGLE quotes nothing is substituted, so a backtick or `$(` there is text -- a commit
    # message quoting "`gh issue create`" is not a create. Double quotes do substitute, so they stay.
    # A backslash-escaped character (`\\``) is literal outside single quotes too (#1468).
    literal, q, i = [], "", 0
    while i < len(body):
        ch = body[i]
        i += 1
        if q == "'":
            q = "" if ch == "'" else q
            continue
        if ch == "\\":
            i += 1                   # the escaped character is literal: never a substitution
            continue
        if ch == "'" and q != '"':
            q = "'"
            continue
        if ch == '"':
            q = "" if q == '"' else '"'
        literal.append(ch)
    subst = "".join(literal)
    found = _substituted_create(subst)
    if found:
        return found
    # A shell fed a file through a substitution (#1515): `bash <(cat f)`, `bash -c "$(cat f)"`, `bash <<<"$(cat f)"`.
    for kind, text in _shell_fed(body):
        if kind == "echo":      # the text a shell is fed by `echo`/`printf` IS the script (#1645 R2): `bash <(echo 'gh issue create ...')`
            if _runs(text, depth, base_dir):
                return "text fed to a shell through a substitution"
            continue
        for operand in (_cat_operands(text) if kind == "cat" else [text]):    # `cat f`, or `<f` (#1645 R2: `$(<f)`)
            fed = _read_script(operand, base_dir)
            if fed is _UNREADABLE or fed is _UNKNOWN_DIR:
                return f"a script file `{operand}` fed to a shell that this hook cannot read"
            if fed is not None and _runs(fed, depth, base_dir):
                return "a script file fed to a shell through a substitution"
    try:
        lexer = shlex.shlex(_fold_fd_redirects(_strip_comments(body)).replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
        lexer.commenters = ""            # (#1645 R1) see `_strip_comments`
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None
    seg: list[str] = []
    fn_wrappers, fn_creators = _functions(_strip_comments(body))    # functions that run gh / name a create (#1645 R2)
    gh_names: set[str] = set(fn_wrappers)   # names bound to gh in this command (`alias g=gh`, `G=gh`, a function that runs gh) (#1515, #1645)
    aliases: dict[str, list[str]] = {}      # alias name -> the words it expands to (#1645 R2: `alias g='gh issue'; g create`)
    prev_files: list[str] = []              # the contents of files a pipeline reader (`tail f`) read earlier in this pipeline (#1645 R2)
    prev_cat: list[str] = []         # the files a `cat` earlier in this pipeline reads (#1515)
    prev_text, prev_op = "", ""      # the pipeline so far (every `|`-joined segment), and the last operator
    # Where a relative `bash < script` resolves (#1489 review, #1495): the session's directory, moved by
    # each literal `cd` to a directory that EXISTS -- a cd to a missing one fails and changes nothing,
    # and `;` runs the next command anyway. `( )` is a subshell: a cd inside it holds until the `)`.
    # Any other cd (`cd -`, `cd $X`, bare, `pushd`/`popd`) makes it unknown, and an unknown file is allowed.
    here_dir: Path | None = base_dir
    dir_stack: list[Path | None] = []
    for tok in tokens + [";"]:
        if tok and set(tok) <= set(";&|()"):
            raw_seg = " ".join(seg)
            words = [w for w in seg if not ("=" in w and w.split("=", 1)[0].isidentifier())]
            words, peeled, xinfo = _peel_info(words)   # `env sh -c`, `sudo bash -c`, `timeout 5 sh -c`, `command eval`, `then . f`, `xargs -a f gh`
            # A redirect glued to the shell or to its operands (`sh<f`, `bash 2>&1<f`, `bash>/dev/null<f`,
            # #1513 review) is cut out so the shell and its stdin are seen.
            unsplit = list(words)       # `_split_redirects` splits on whitespace inside a quoted word; the `-c` string needs it whole (#1645 R2)
            if words and os.path.basename(_split_redirects(words[:1])[0]) in SHELLS:
                words = _split_redirects(words)
            head = os.path.basename(words[0]) if words else ""
            # INDIRECT CREATES (#1515, decided by the coordinator: the gate claims them). The `gh` word built at run time
            # (`$G issue create`, and `$(echo gh) issue create`, whose substitution splits the segment so a bare `issue create`
            # is left), an alias of gh, and the verb arriving through a pipe to `xargs gh` all file an unlabelled issue.
            for seg_word in raw_seg.split():
                if "=" in seg_word and seg_word.split("=", 1)[0].isidentifier() and os.path.basename(seg_word.split("=", 1)[1].strip("'\"")) == "gh":
                    gh_names.add(seg_word.split("=", 1)[0])
            if head == "alias":
                for alias_word in (seg[seg.index("alias") + 1:] if "alias" in seg else []):
                    name, _, value = alias_word.partition("=")
                    aliases[name] = value.split()
                    if value.strip("'\"").split()[:1] and os.path.basename(value.strip("'\"").split()[0]) == "gh":
                        gh_names.add(name)
            # A call of an alias or of a function that files an issue (#1645 R2): `alias mk='gh issue create'; mk -t X`, `alias g='gh issue'; g create`,
            # `g() { gh issue create "$@"; }; g -t X`. The alias is expanded, so the create it hides is read as the create it is.
            if words and not (head == "alias"):
                expanded, hops = list(words), 0
                while expanded and expanded[0] in aliases and hops < 4:
                    expanded, hops = aliases[expanded[0]] + expanded[1:], hops + 1
                if hops and gh_issue_create_at(expanded, 0)[0] is not None:
                    return "an alias that expands to a create"
                if words[0] in fn_creators:
                    return "a function whose body files an issue"
            tail = [w for w in words[1:] if not w.startswith("-")]
            names_verb = len(words) > 1 and any(a == "issue" and b in ("create", "new") for a, b in zip(words, words[1:]))
            if words and names_verb and (words[0].startswith("$") or "`" in words[0] or words[0] in gh_names):
                return "a `gh` word built at run time or aliased"
            if head == "issue" and tail[:1] and tail[0] in ("create", "new"):
                return "a `gh` word built at run time (a substitution before `issue create`)"
            # `xargs` builds gh's arguments from its input (#1645 R2): `-a FILE`, a file `cat`/`tail` pipes in, or the text `echo` pipes in; with
            # `-I{}` the input replaces `{}` in the command. The verb arriving that way, side by side, is an unlabelled create.
            if "xargs" in peeled and head == "gh":
                data: list[str] = []
                sources = [xinfo["a"]] if xinfo.get("a") else []
                for src in sources + (prev_cat if prev_op in ("|", "|&") else []):
                    fed = _read_script(src, here_dir)
                    if isinstance(fed, str) and fed not in (_UNREADABLE, _UNKNOWN_DIR):
                        data += fed.split()
                for fed in (prev_files if prev_op in ("|", "|&") else []):
                    data += fed.split()
                if prev_op in ("|", "|&") and prev_text:
                    data += prev_text.replace("'", " ").replace('"', " ").split()
                cmd_tokens = words[1:]
                if xinfo.get("I"):
                    candidates = [[w.replace(xinfo["I"], d) for w in cmd_tokens] for d in data]
                else:
                    candidates = [" ".join(cmd_tokens + data).split()]
                if any(_verb_tokens(tokens) for tokens in candidates):
                    return "the verb arriving through `xargs gh` (its input names `issue create`)"
            # A cd in the background (`cd sub &`) or in a pipeline (`cd sub | …`, `… | cd sub`) runs in a
            # subshell and never moves this shell (#1513 review), so it is not followed.
            in_subshell = tok.rstrip("()") in ("&", "|", "|&") or prev_op in ("|", "|&")
            if head in ("cd", "pushd", "popd") and not in_subshell:
                cd_words = _drop_redirects(words)
                arg = cd_words[1] if len(cd_words) == 2 else None
                if here_dir is None or head != "cd" or not arg or arg == "-" or "$" in arg or "`" in arg:
                    here_dir = None
                elif (here_dir / os.path.expanduser(arg)).is_dir():
                    here_dir = here_dir / os.path.expanduser(arg)
            rest = " ".join(words[1:])
            # `-c` may be bundled with other short flags: `bash -lc '…'`.
            runs_string = any(w.startswith("-") and not w.startswith("--") and "c" in w for w in words[1:])
            if head in SHELLS and runs_string:
                c_operand = _first_operand(unsplit[1:])[0]
                if _names_create(rest) or (c_operand and _runs(c_operand, depth, here_dir)):    # the string is a script: `sh -c '. f'`, `sh -c 'bash f'` (#1645 R2)
                    return f"`{head} -c`"
            if head == "eval" and _runs(rest, depth, here_dir):
                return "`eval`"
            # A script the shell runs from a FILE (#1515): `bash f`, `sh ./f`, `source f`, `. f`. The file is read; one that cannot be
            # read is refused (the coordinator's call: fail closed), as is a relative one after a cd this parser cannot follow.
            operand = None
            if head in SHELLS and not runs_string and not any(w.startswith("<<<") for w in words[1:]):
                operand, has_s = _first_operand(words[1:])
                operand = None if has_s else operand
            elif head in ("source", ".") and len(words) > 1:
                operand = words[1]
            if operand:
                fed = _read_script(operand, here_dir)
                if fed is _UNKNOWN_DIR:
                    return (f"a script run by `{head}` after a cd this hook cannot follow; give the script an absolute path")
                if fed is _UNREADABLE:
                    return f"a script file `{operand}` run by `{head}` that this hook cannot read"
                if fed is not None and _runs(fed, depth, here_dir):
                    return f"a script run by `{head}`"
            # A shell reading its SCRIPT from stdin (#1462): a pipe into it, or a herestring.
            if head in SHELLS and not runs_string:
                if prev_op in ("|", "|&") and _runs(prev_text, depth, here_dir):
                    return f"a pipe into `{head}`"
                # `cat f | bash` (#1515): the files `cat` read are the script.
                if prev_op in ("|", "|&") and (prev_cat or prev_files):
                    for cat_file in prev_cat:
                        fed = _read_script(cat_file, here_dir)
                        if fed is _UNREADABLE or fed is _UNKNOWN_DIR:
                            return f"a script file `{cat_file}` piped into `{head}` that this hook cannot read"
                        if fed is not None and _runs(fed, depth, here_dir):
                            return f"a script file piped into `{head}`"
                    for fed in prev_files:       # `tail -n +2 f | sh`, `sed 1d f | bash`, `grep . f | sh` (#1645 R2)
                        if _runs(fed, depth, here_dir):
                            return f"a file read by a pipeline reader and piped into `{head}`"
                here = next((k for k, w in enumerate(words) if w.startswith("<<<")), None)
                if here is not None and _runs(" ".join([words[here][3:]] + words[here + 1:]), depth, here_dir):
                    return f"a herestring fed to `{head}`"
                # `bash < script` / `bash <script` (#1489): the create lives in the FILE, so read it.
                # A file that cannot be read is allowed, as before. But a RELATIVE script after a cd this
                # parser cannot follow is refused (#1513 review, owner rule #1423): it may be anywhere.
                script = _redirected_script(words[1:], here_dir) if _stdin_is_script(words[1:]) else None
                if script is _UNREADABLE:
                    return f"a redirected script for `{head}` that this hook cannot read"
                if script is _UNKNOWN_DIR:
                    return (f"a script fed to `{head}` by redirect after a cd this hook cannot follow; "
                            "give the script an absolute path")
                if script is not None and _runs(script, depth, here_dir):
                    return f"a script fed to `{head}` by redirect"
            # A pipeline feeds its whole upstream: `echo … | cat | bash` runs what echo wrote.
            prev_files = ((prev_files if prev_op in ("|", "|&") else []) + (_reader_files(words, here_dir) if head in _READERS else []))
            prev_cat = ((prev_cat if prev_op in ("|", "|&") else []) + (_cat_operands(" ".join(words[1:])) if head == "cat" else []))
            prev_text = (prev_text + " " + raw_seg) if prev_op in ("|", "|&") else raw_seg
            prev_op = tok
            for ch in tok:
                if ch == "(":
                    dir_stack.append(here_dir)
                elif ch == ")" and dir_stack:
                    here_dir = dir_stack.pop()
            seg = []
        else:
            seg.append(tok)
    return None


def gh_issue_create_at(words: list[str], i: int) -> tuple[int | None, list[str]]:
    """If `words[i:]` is `gh [global flags] issue create|new …`: (index after `create`, the global
    `-R/--repo` flag to carry into the create's arguments). Else (None, [])."""
    if i >= len(words) or os.path.basename(words[i]) != "gh":
        return None, []
    j, lead = i + 1, []
    while j < len(words) and words[j].startswith("-"):
        flag = words[j]
        if flag in ("-R", "--repo") and j + 1 < len(words):
            lead, j = [flag, words[j + 1]], j + 2
            continue
        if flag.startswith("--repo=") or (flag.startswith("-R") and len(flag) > 2):
            lead = [flag]
        j += 1
    if j + 1 < len(words) and words[j] == "issue" and words[j + 1] in ("create", "new"):
        return j + 2, lead
    return None, []


_SUBST_OPEN = re.compile(r"\$\(")


def _substituted_create(text: str) -> str | None:
    """A create inside a backtick or `$( … )` substitution in TEXT, named, or None."""
    # Backticks PAIR: the text between the 1st and 2nd is a substitution, the 2nd and 3rd is not.
    # An unclosed one runs to the end of the command.
    ticks = text.split("`")
    if any(_names_create(span) for span in ticks[1::2]):
        return "backticks"
    # `$( … )` to its OWN closing parenthesis, counted, so a create after it is not inside it. Only the OUTERMOST substitution is read, once, and the scan
    # resumes after it: a create inside a nested one is inside the outer one, and re-reading each nested span made `$(` x 2,000 take ten seconds (cubic).
    i = 0
    while (m := _SUBST_OPEN.search(text, i)):
        depth, j = 1, m.end()
        while j < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[j], 0)
            j += 1
        if _names_create(text[m.end():j - (0 if depth else 1)]):
            return "a `$( … )` substitution"
        i = j
    return None


# Reserved words and a `!` that put a command in the position `then`/`do`/`{` introduces: `then . f` runs f (#1645 R2).
KEYWORDS = {"then", "do", "else", "elif", "if", "while", "until", "{", "}", "!"}
_XARGS_VALUED = {"-a", "--arg-file", "-I", "-n", "-L", "-P", "-d", "-s", "-E", "-l", "--max-args", "--max-lines", "--max-procs", "--delimiter",
                 "--max-chars", "--eof"}


def _peel_info(words: list[str]) -> tuple[list[str], list[str], dict]:
    """(the command words with wrappers peeled, the wrappers peeled, xargs's `-a FILE` and replace-string).

    Wrappers that run their arguments as a command -- `env`, `sudo`, `timeout 5`, `command`, `builtin`, `time`, … -- with their own flags and
    timeout's or nice's number; reserved words (`then`, `do`, `{`, `!`, #1645 R2); `xargs`'s options that take a value (`-a f`, `-I {}`, #1645 R2);
    and `find … -exec CMD … ;`, whose CMD is what runs. One peel, used everywhere."""
    words, peeled, info = list(words), [], {}
    while words:
        base = os.path.basename(words[0])
        if base in KEYWORDS:
            words.pop(0)
            peeled.append(base)
            continue
        if base in WRAPPERS:
            words.pop(0)
            peeled.append(base)
            while words and words[0].startswith("-"):
                flag = words.pop(0)
                if base == "xargs":
                    name, eq, value = flag.partition("=")
                    if flag.startswith("-I") and len(flag) > 2:
                        info["I"] = flag[2:]
                    elif flag in _XARGS_VALUED or name in _XARGS_VALUED and not eq:
                        if words:
                            value = words.pop(0)
                            if flag in ("-a", "--arg-file"):
                                info["a"] = value
                            elif flag in ("-I", "--replace"):
                                info["I"] = value
                    elif flag.startswith("-a") and len(flag) > 2:
                        info["a"] = flag[2:]
                    elif eq and name in ("--arg-file",):
                        info["a"] = value
                    elif eq and name in ("--replace",):
                        info["I"] = value
            if base in ("timeout", "nice") and words and re.fullmatch(r"[\d.]+[smhd]?", words[0]):
                words.pop(0)
            continue
        if base == "find":
            at = next((k for k, w in enumerate(words) if w in ("-exec", "-execdir", "-ok", "-okdir")), None)
            if at is None:
                break
            sub = words[at + 1:]
            cut = next((k for k, w in enumerate(sub) if w in (";", "+", "\\;")), len(sub))
            words = sub[:cut]
            peeled.append("find")
            continue
        break
    return words, peeled, info


def _peel(words: list[str]) -> list[str]:
    return _peel_info(words)[0]


_FN_DEF = re.compile(r"(?:^|[;&|({\s])(?:function\s+([A-Za-z_][\w.:+-]*)\s*(?:\(\s*\))?|([A-Za-z_][\w.:+-]*)\s*\(\s*\))\s*\{")
_GH_WORD = re.compile(r"(?:^|[\s;&|({])(?:[^\s;&|({/]*/)*gh(?=[\s;&|)}]|$)")


def _functions(text: str) -> tuple[set[str], set[str]]:
    """(functions whose body runs `gh`, functions whose body names a create) defined in TEXT (#1645 R2).

    `g() { command gh "$@"; }; g issue create -t X` files an unlabelled issue through a function: the call has a gh word the hook never sees.
    A body is read to its own closing brace (counted). A wrapper is any function whose body has `gh` as a command word."""
    wrappers: set[str] = set()
    creators: set[str] = set()
    for m in _FN_DEF.finditer(text):
        name, depth, j = m.group(1) or m.group(2), 1, m.end()
        while j < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[j], 0)
            j += 1
        body = text[m.end():j - (0 if depth else 1)]
        if _GH_WORD.search(body):
            wrappers.add(name)
        if _names_create(body):
            creators.add(name)
    return wrappers, creators


# The commands that read FILES and write them on, so `tail -n +2 f | sh` runs f's lines (#1645 R2). `cat` has its own, stricter, handling.
_READERS = {"head", "tail", "sed", "grep", "egrep", "fgrep", "awk", "tac", "nl", "cut", "sort", "uniq", "paste", "fmt", "fold", "column", "less", "more"}


def _reader_files(words: list[str], cwd: Path | None) -> list[str]:
    """The contents of the existing files a pipeline reader (`tail -n +2 f`, `sed 1d f`, `grep . f`) is given: flags, numbers and patterns that
    are not files are skipped, and a file that is not readable is not a script (`cat` is the strict one)."""
    texts: list[str] = []
    for w in words[1:]:
        if not w or w[0] in "-+" or w.isdigit() or w.startswith(("<", ">")):
            continue
        fed = _read_script(w, cwd)
        if isinstance(fed, str) and fed not in (_UNREADABLE, _UNKNOWN_DIR):
            texts.append(fed)
    return texts


def _verb_tokens(tokens: list[str]) -> bool:
    """Do these words hold `issue create|new` side by side: the verb arriving as data (#1645 R2)."""
    return any(a == "issue" and b in ("create", "new") for a, b in zip(tokens, tokens[1:]))


def _first_operand(args: list[str]) -> tuple[str | None, bool]:
    """A shell's first operand (the script file, or the `-c` string) and whether `-s` was given (#1489 review).
    Redirects, flags and the words `-o`/`-O` take are not operands."""
    k, has_s, ended = 0, False, False
    while k < len(args):
        w = args[k]
        k += 1
        if w in ("<", "0<", ">", ">>", "2>", "&>") or re.fullmatch(r"\d*[<>]&?", w):
            k += 1                   # a redirect's target is not an operand
            continue
        if re.match(r"\d*[<>]", w):
            continue                 # `<f`, `0<f`, `>log`, `2>&1`
        if w == "--" and not ended:
            ended = True             # after `--`, even `-x` is an operand
            continue
        if w[:1] in ("-", "+") and len(w) > 1 and not ended:
            if not w.startswith("--") and "s" in w[1:]:
                has_s = True
            if w in ("--rcfile", "--init-file"):
                k += 1
            elif re.fullmatch(r"[-+][A-Za-z]+", w):
                k += w.count("o") + w.count("O")   # each o/O takes a word: `-eo x`, `-ox x`, `-oO a b` (#1513)
            continue
        return w, has_s              # an operand: the script is that file, unless -s
    return None, has_s


def _stdin_is_script(args: list[str]) -> bool:
    """Does a shell run its STDIN as the script? Only with no operand, or with `-s` (#1489 review):
    `bash script.sh < notes.md` runs script.sh and hands it notes.md as data."""
    operand, has_s = _first_operand(args)
    return operand is None or has_s


_UNKNOWN_DIR = "\0unknown-dir"     # a relative script after a cd that cannot be followed
_SCRIPT_CAP = 1_000_000               # the most of a script this hook reads; a larger file is refused, not half-read (#1515)
_UNREADABLE = "\0unreadable"       # a literal script path that is not a readable file (#1515: refused, fail closed)


def _read_script(target: str | None, cwd: Path | None) -> str | None:
    """The contents of the script file TARGET names, read the way the shell would find it.

    Only a literal path: one with `$` or a backtick cannot be resolved here and is None (allowed, as before; refusing every
    `bash "$DIR/x.sh"` would block ordinary commands). A literal path that is not a readable file is `_UNREADABLE`, and
    a relative one after a cd this parser cannot follow is `_UNKNOWN_DIR`: both are REFUSED (#1515, decided by the
    coordinator: a script file that cannot be read fails closed, as #1513 did for an unfollowable cd). The first 1 MB is read;
    a relative path resolves from CWD, the directory the command has moved to; `$HOME` expands.
    """
    if target:
        target = re.sub(r"^\$(HOME|\{HOME\})(?=/|$)", lambda _: os.path.expanduser("~"), target)
    if not target or "$" in target or "`" in target:
        return None
    path = Path(os.path.expanduser(target))
    if not path.is_absolute():
        if cwd is None:
            return _UNKNOWN_DIR
        path = cwd / path
    try:
        # A file past the 1 MB read cap would be judged on its first megabyte only, and a create after it would pass: it is refused instead
        # of half-read (fail closed, as for any file this hook cannot read).
        if not path.is_file() or path.stat().st_size > _SCRIPT_CAP:
            return _UNREADABLE
        with path.open("rb") as fh:
            return fh.read(_SCRIPT_CAP).decode("utf-8", errors="replace")
    except OSError:
        return _UNREADABLE


def _redirected_script(args: list[str], cwd: Path | None) -> str | None:
    """The contents of the file a shell reads as stdin (`< path`, `<path`, `0< path`), or None.

    `<<` (heredoc) and `<<<` (herestring) are other forms, handled elsewhere; `<(` is a process substitution, not a file.
    """
    target = None
    for k, w in enumerate(args):
        if w.startswith("0<"):
            w = w[1:]
        if w == "<" and k + 1 < len(args):
            target = args[k + 1]
            break
        if w.startswith("<") and not w.startswith(("<<", "<(")) and len(w) > 1:
            target = w[1:]
            break
    return _read_script(target, cwd)


# A SHELL FED A FILE OR TEXT THROUGH A SUBSTITUTION (#1515, #1645 R2): `bash <(cat f)`, `bash -c "$(cat f)"`, `bash <<<"$(cat f)"`, the backtick form,
# `$(<f)`, and `bash <(echo '...')`. The shell word and the substitution sit in one segment (no `;`, `|`, newline or bare `&` between them).
# ONE LINEAR PASS, NOT A BACKTRACKING PATTERN (CodeQL: exponential backtracking on repeated `<&>`): the pattern this replaces let `<&>` match three
# ways, and even once unambiguous it rescanned to the end of the command from every shell word (`bash ` x 8000 took 15 s). Here each character is
# looked at once; the end of an operand comes from a precomputed list of terminators, so no marker rescans the text.
_FED_SCAN = re.compile(
    r"(?P<sep>[;|\n]|(?<![<>])&(?!>))"                          # a `&` is part of a segment only as an fd dup (`2>&1`, after `<`/`>`) or as `&>`
    r"|(?P<shell>(?<![^\s;&|(])(?:sh|bash|zsh|dash|ksh|eval)\b)"
    r"|(?P<mark><\(|\$\(|`)")
_FED_END = re.compile(r"[)`]")
_FED_CAT = re.compile(r"\s*cat\s+")
_FED_ECHO = re.compile(r"\s*(?:echo|printf)\s+")
_FED_READ = re.compile(r"\s*<\s*([^)`\s]{1,4096})")


def _shell_fed(body: str) -> list[tuple[str, str]]:
    """What a shell in BODY is fed through a substitution: ("cat", the text after `cat`), ("read", the `<f` operand), ("echo", the printed text)."""
    ends = [m.start() for m in _FED_END.finditer(body)]
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    shell = False
    resume = 0                  # a marker inside an operand already taken belongs to it: `_runs` reads it there (else n markers = n overlapping re-reads, exponential)
    for m in _FED_SCAN.finditer(body):
        if m.start() < resume:
            continue
        if m.lastgroup == "sep":
            shell = False
        elif m.lastgroup == "shell":
            shell = True
        elif shell:
            at = m.end()
            kind = ""
            if (c := _FED_CAT.match(body, at)) or (c := _FED_ECHO.match(body, at)):
                kind = "cat" if "cat" in c.group() else "echo"
                start = c.end()
                k = bisect.bisect_left(ends, start)
                text = body[start:ends[k] if k < len(ends) else len(body)]
                found = (kind, text) if text else None
                resume = start + len(text)
            elif (r := _FED_READ.match(body, at)):
                found = ("read", r.group(1))
                resume = r.end()
            else:
                found = None
            if found and found not in seen:
                seen.add(found)
                out.append(found)
    return out


def _cat_operands(text: str) -> list[str]:
    """The files `cat` is given in TEXT (a command's words after `cat`): not flags, not redirects."""
    try:
        words = shlex.split(text, posix=True)
    except ValueError:
        return []
    return [w for w in words if not w.startswith(("-", "<", ">")) and not re.fullmatch(r"\d*[<>]&?\d*", w)]


def _command_word(text: str) -> str:
    """The command word of the LAST segment of TEXT, with assignments and wrappers peeled."""
    part = re.split(r"[;&|(]", text)[-1]
    words = _peel([w for w in part.split() if not ("=" in w and w.split("=", 1)[0].isidentifier())])
    return os.path.basename(words[0]) if words else ""


def target_root(cd: str | None, root: Path) -> tuple[Path | None, str]:
    """The repository a create runs in: `root` without a `cd`, else the cd target's git toplevel."""
    if cd is None:
        return root, ""
    path = Path(os.path.expanduser(cd))
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_dir():
        return None, f"`cd {cd}` names no directory, so its label rules are unknown."
    try:
        top = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        top = ""
    return (Path(top) if top else path.resolve()), ""


def load_groups(target: Path) -> tuple[list | None, str]:
    config_path = target / CONFIG
    if not config_path.is_file():
        return None, ""
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))["groups"], ""
    except (ValueError, KeyError, TypeError) as exc:
        where = CONFIG if target == Path(".").resolve() else target / CONFIG
        return None, f"{where} is unreadable ({exc}); fix it so labels can be checked"


def parse_args(args: list[str]) -> tuple[list[str], str | None]:
    labels, repo = [], None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--label", "-l") and i + 1 < len(args):
            labels += [x.strip() for x in args[i + 1].split(",") if x.strip()]
            i += 2
            continue
        if a.startswith("--label="):
            labels += [x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()]
        elif a in ("--repo", "-R") and i + 1 < len(args):
            repo = args[i + 1]
            i += 2
            continue
        elif a.startswith("--repo="):
            repo = a.split("=", 1)[1]
        elif a.startswith("-R") and len(a) > 2:
            repo = a[2:]            # gh accepts the value glued to the short flag
        i += 1
    return labels, repo


def norm_repo(s: str | None) -> str | None:
    """`owner/name`, lowercased, from ANY spelling of a repo: `owner/name`, a URL with or without
    userinfo (`https://token@github.com/…`), an ssh port (`ssh://git@github.com:22/…`), an ssh alias
    (`git@github-work:…`), an enterprise host, `.git`. The host is dropped on purpose: two remotes
    naming the same owner/name are treated as the same repo, which only ever means MORE fallback to
    the session's rules -- the safe direction."""
    if not s:
        return None
    m = re.search(r"([^/:@\s]+)/([^/:@\s]+?)(?:\.git)?/*$", s.strip().lower())
    return f"{m.group(1)}/{m.group(2)}" if m else None

def own_repo(root: Path) -> str | None:
    """The `origin` repo, normalised, or None."""
    try:
        url = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return norm_repo(url)


def remotes(root: Path) -> set[str]:
    """EVERY remote's repo, normalised. gh picks among them (`upstream` before `origin`), so a
    checkout any of whose remotes is the session's repo may file there."""
    try:
        out = subprocess.run(["git", "-C", str(root), "remote", "-v"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {r for line in out.splitlines() if len(line.split()) >= 2
            for r in [norm_repo(line.split()[1])] if r}


def matches(label: str, pattern: str) -> bool:
    return label.startswith(pattern[:-1]) if pattern.endswith("*") else label == pattern


_ISSUES_ENDPOINT = re.compile(r"^/?repos/[^/\s]+/[^/\s]+/issues/?(?:\?.*)?$")


def api_issue_post(cmd: str) -> str | None:
    """A `gh api` request that CREATES an issue, which never uses the `issue create` verb (#1515), or None.

    `gh api -X POST repos/o/r/issues -f title=X` files an issue with no label. Decided by the coordinator: the gate claims it, and a POST to
    an issues COLLECTION is refused (a comment, `repos/o/r/issues/12/comments`, or a GET is not). A request that sends fields
    (`-f`, `-F`, `--field`, `--raw-field`, `--input`) with no `-X` is a POST too, which is how `gh api` behaves.
    """
    try:
        lexer = shlex.shlex(_fold_fd_redirects(cmd).replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None
    seg: list[str] = []
    for tok in tokens + [";"]:
        if tok and set(tok) <= set(";&|()"):
            words = _peel([w for w in seg if not ("=" in w and w.split("=", 1)[0].isidentifier())])
            seg = []
            if len(words) < 2 or os.path.basename(words[0]) != "gh":
                continue
            rest = words[1:]
            while rest and rest[0] in ("-R", "--repo") and len(rest) > 1:
                rest = rest[2:]            # gh's global repo flag before the subcommand
            if not rest or rest[0] != "api":
                continue
            method, sends, endpoint, k, args = "", False, None, 0, rest[1:]
            while k < len(args):
                w = args[k]
                k += 1
                if w in ("-X", "--method") and k < len(args):
                    method = args[k].upper(); k += 1
                elif w.startswith("--method="):
                    method = w.split("=", 1)[1].upper()
                elif w.startswith("-X") and len(w) > 2:
                    method = w[2:].upper()
                elif w in ("-f", "-F", "--field", "--raw-field", "--input", "-H", "--header", "--jq", "-q", "--template", "-t", "--cache", "--hostname"):
                    sends = sends or w in ("-f", "-F", "--field", "--raw-field", "--input")
                    k += 1
                elif w.startswith("-"):
                    continue
                elif endpoint is None:
                    endpoint = w
            posts = method == "POST" or (not method and sends)
            if posts and endpoint and _ISSUES_ENDPOINT.match(endpoint):
                return f"`gh api` POST to {endpoint}"
        else:
            seg.append(tok)
    return None


def verdict(cmd: str, root: Path) -> tuple[bool, str]:
    shape = hidden_create(cmd)
    if shape:
        if "cannot read" in shape or "cannot follow" in shape:
            return False, (f"{shape}, so a `gh issue create` in it cannot be label-checked, and the command is refused rather than let "
                           "through unlabelled. Fix the path (a readable file), or run the create directly with its --label flags (#1515).")
        return False, (f"a `gh issue create` inside {shape} cannot be label-checked (its labels are one "
                       "quoted string here). Run it directly, with its --label flags (#1423).")
    api = api_issue_post(cmd)
    if api:
        return False, (f"{api} files an issue with no label check. File it with `gh issue create` and its --label flags (a template "
                       "never applies from the shell) (#1515).")
    creates = issue_creates(cmd)
    if not creates:
        return True, ""
    for args, cd, env_repo in creates:
        if args == ["__unparseable__"]:
            return False, "the gh issue create command could not be parsed, so its labels cannot be checked"
        labels, repo = parse_args(args)
        # THE SAFE DEFAULT IS THE SESSION'S RULES -- exactly what the hook did before #1400. Another
        # repo's rules apply only when the create CERTAINLY files there: the allowlisted cd shape,
        # no repo named on the create (-R, --repo, GH_REPO), a target with remotes, and none of them
        # the session's repo (gh may pick `upstream` over `origin`). Every leak five reviews found
        # was another repo's rules applied without that certainty; this default cannot leak,
        # because it is the check the same create gets with no cd at all.
        target = root
        # GH_REPO in the hook's own environment (settings `env`) redirects gh too. One set only via
        # CLAUDE_ENV_FILE is invisible here -- a known limit, recorded in #1400.
        if cd is not None and repo is None and env_repo is None and not os.environ.get("GH_REPO"):
            found, _ = target_root(cd, root)
            if found is not None:
                theirs, ours = remotes(found), remotes(root)
                # Certain only when BOTH sides have remotes and they share none: gh may file into
                # any remote (`upstream` first), so one shared repo means the session's rules.
                if theirs and ours and ours.isdisjoint(theirs):
                    target = found
        followed = target != root
        groups, why = load_groups(target)
        if why:
            return False, why
        mine = own_repo(target)
        foreign = repo is not None and norm_repo(repo) != mine
        if not labels:
            where = f" (the declared groups are in {CONFIG})" if groups and not foreign else ""
            return False, f"`gh issue create` with no --label{where}. Label it when you file it; a template never applies here."
        if groups is None or foreign:
            continue
        for g in groups:
            if g.get("when") and not any(matches(l, g["when"]) for l in labels):
                continue
            allowed = g.get("one_of") or []
            if not any(matches(l, p) for l in labels for p in allowed):
                scope = f" (because it is `{g['when']}`)" if g.get("when") else ""
                decl = target / CONFIG if followed else CONFIG
                return False, (f"`gh issue create` needs one of {', '.join(allowed)}{scope}; it has "
                               f"{', '.join(labels)}. Declared in {decl}.")
    return True, ""


def main(argv: list[str]) -> int:
    if argv[1:] == ["--selftest"]:
        return selftest()
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else Path(".")
    ok, why = verdict(sys.stdin.read(), root.resolve())
    if not ok:
        print(why)
        return 1
    return 0


def selftest() -> int:
    import tempfile

    fails: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            fails.append(f"{label} {detail}".rstrip())

    retask = {"groups": [{"one_of": ["bug", "feature", "enhancement"]},
                         {"when": "bug", "one_of": ["severity:s1", "severity:s2", "severity:s3", "severity:s4"]}]}
    skills = {"groups": [{"one_of": ["comp:*"]}, {"one_of": ["type:*"]}, {"one_of": ["prio:*"]}]}
    with tempfile.TemporaryDirectory() as td:
        r = Path(td) / "retask"
        (r / ".rails-flow").mkdir(parents=True)
        (r / CONFIG).write_text(json.dumps(retask), encoding="utf-8")
        s = Path(td) / "skills"
        (s / ".rails-flow").mkdir(parents=True)
        (s / CONFIG).write_text(json.dumps(skills), encoding="utf-8")
        bare = Path(td) / "bare"
        bare.mkdir()

        check("not a gh issue create: allowed", verdict("gh issue list --label bug", r)[0])
        check("CONTROL: a feature is allowed", verdict('gh issue create -t X --label "feature" --body-file b.md', r)[0])
        ok, why = verdict("gh issue create -t X --body-file b.md", r)
        check("no label: refused", not ok and "no --label" in why, why)
        ok, why = verdict('gh issue create -t X --label "phase-3-recruitment"', r)
        check("labels outside the type group: refused, naming the group", not ok and "bug, feature, enhancement" in why, why)
        ok, why = verdict("gh issue create -t X --label bug", r)
        check("a bug without a severity: refused, saying why", not ok and "severity:s1" in why and "`bug`" in why, why)
        check("CONTROL: a bug with a severity is allowed",
              verdict("gh issue create -t X --label bug --label severity:s2", r)[0])
        check("comma-joined labels are split", verdict('gh issue create -t X -l "bug,severity:s3"', r)[0])
        check("--label=value is read", verdict("gh issue create -t X --label=feature", r)[0])

        check("prefix groups: comp/type/prio all present is allowed",
              verdict('gh issue create -t X --label "comp:rails-flow" --label type:bug --label prio:P2', s)[0])
        ok, why = verdict('gh issue create -t X --label "comp:rails-flow"', s)
        check("prefix groups: a missing type is refused", not ok and "type:*" in why, why)

        check("undeclared project: one label is enough", verdict("gh issue create -t X --label anything", bare)[0])
        check("undeclared project: no label is refused", not verdict("gh issue create -t X", bare)[0])
        check("another repo: one label is enough",
              verdict("gh issue create -R someone/else -t X --label bug", r)[0])
        check("another repo: no label is still refused", not verdict("gh issue create -R someone/else -t X", r)[0])

        check("a create later in a compound command is checked",
              not verdict('cd x && gh issue create -t X --body-file b.md', r)[0])
        check("a quoted mention is not a command", verdict('echo "gh issue create"', r)[0])
        # #1336: a quoted heredoc body in the same call is prose, not shell to tokenise.
        body = "cat > b.md <<'EOF'\nThe validator's warning: `x` is \"quoted\"\nEOF\n"  # ONE apostrophe: odd, so shlex cannot pair it
        check("a heredoc body with apostrophes does not break a labelled create",
              verdict(body + 'gh issue create -t X --label "feature" --body-file b.md', r)[0],
              verdict(body + 'gh issue create -t X --label "feature" --body-file b.md', r)[1])
        ok, why = verdict(body + "gh issue create -t X --body-file b.md", r)
        check("...and an unlabelled create after the heredoc is still refused", not ok and "no --label" in why, why)
        ok, why = verdict("cat <<-EOF > b.md\n\tit's\n\tEOF\ngh issue create -t X", r)
        check("a <<- heredoc (tab-indented close) is stripped too", not ok and "no --label" in why, why)
        ok, why = verdict("gh issue create -t \"X --label feature", r)
        check("CONTROL: a genuinely unparseable create still refuses", not ok and "could not be parsed" in why, why)
        # ---- #1400: the TARGET repository's declaration, in the one shape that is followed -------
        # Both sides need remotes for the cd to be certain: the session is me/skills, the target
        # a git checkout whose only remote is someone else's.
        subprocess.run(["git", "init", "-q", str(s)], check=True)
        subprocess.run(["git", "-C", str(s), "remote", "add", "origin", "https://github.com/me/skills.git"], check=True)
        subprocess.run(["git", "init", "-q", str(r)], check=True)
        subprocess.run(["git", "-C", str(r), "remote", "add", "origin", "https://github.com/other/retask.git"], check=True)
        rt = "gh issue create -t X --label enhancement --label needs-decision"
        ok, why = verdict(rt, s)
        check("CONTROL: those labels fail the session's own declaration", not ok and "comp:*" in why, why)
        ok, why = verdict(f"cd {r} && {rt}", s)
        check("cd into another repo: that repo's declaration applies, and passes", ok, why)
        ok, why = verdict(f"cd {r} && gh issue create -t X --label bug", s)
        check("...and that repo's rules still refuse, naming its file",
              not ok and "severity:s1" in why and str(r) in why, why)
        ok, why = verdict("(true);gh issue create -t X", s)
        check("a create right after a glued `);` is seen, and its missing label refused", not ok and "no --label" in why, why)
        check("a newline after && continues the chain", verdict(f"cd {r} &&\n{rt}", s)[0],
              verdict(f"cd {r} &&\n{rt}", s)[1])
        (r / "app" / "models").mkdir(parents=True)
        # Discriminating on purpose: a subdirectory with no declaration of its own would read as
        # UNDECLARED, where one label passes -- so the fixture must be one only the toplevel refuses.
        ok, why = verdict(f"cd {r}/app/models && gh issue create -t X --label bug", s)
        check("a cd into a SUBDIRECTORY finds the repo's toplevel declaration",
              not ok and "severity:s1" in why, why)
        check("...and passes what the toplevel allows", verdict(f"cd {r}/app/models && {rt}", s)[0])
        here = Path.cwd()
        try:
            os.chdir(td)
            check("a relative cd resolves from where the command runs", verdict(f"cd retask && {rt}", s)[0],
                  verdict(f"cd retask && {rt}", s)[1])
        finally:
            os.chdir(here)
        ok, why = verdict(f"cd {td}/nowhere && {rt}", s)
        check("a cd to a missing directory keeps the session's rules", not ok and "comp:*" in why, why)
        bare_target = Path(td) / "noremote"
        bare_target.mkdir()
        (bare_target / ".rails-flow").mkdir()
        (bare_target / CONFIG).write_text(json.dumps(retask), encoding="utf-8")
        ok, why = verdict(f"cd {bare_target} && {rt}", s)
        check("a target with no remote keeps the session's rules: gh's destination is unknown",
              not ok and "comp:*" in why, why)
        check("CONTROL: a create with no cd still uses the session's declaration",
              not verdict(rt, s)[0] and not verdict(f"echo hi; {rt}", s)[0])

        # ---- every OTHER shape with a cd is refused, never guessed ---------------------------------
        # Each was a real leak in an earlier draft (three independent reviews), or is its near kin.
        # The labels pass the target repo, so a guess would let them through; the session must judge.
        u = Path(td) / "undeclared"
        u.mkdir()
        one = "gh issue create -t X --label comp:x"     # one label: passes an undeclared dir, fails skills
        # "Refused" here means judged by the SESSION's rules: the labels pass the target's rules and
        # fail the session's, so a refusal proves the cd was NOT followed -- the safe default.
        def refused(name: str, cmd: str, needle: str = "comp:*") -> None:
            ok, why = verdict(cmd, s)
            check(f"refused: {name}", not ok and needle in why, why)
        for name, shape in (
                ("a cd separated by ;", f"cd {r}; {rt}"),
                ("a cd inside a subshell", f"(cd {r}); {rt}"),
                ("a subshell cd before &&", f"(cd {r}) && {rt}"),
                ("a create inside the subshell", f"(cd {r} && {rt})"),
                ("a cd that is not the first command", f"true && cd {r} && {rt}"),
                ("a cd on a later line", f"echo hi\ncd {r} && {rt}"),
                ("a cd in a pipeline", f"cd {r} | cat && {rt}"),
                ("a cd sent to the background", f"cd {r} & {rt}"),
                ("a create after cd ||", f"cd {r} || {rt}"),
                ("a second cd", f"cd {r} && cd {u} && {rt}"),
                ("cd -", f"cd {u} && cd - && {rt}"),
                ("a cd to a variable", f"cd $OTHER && {rt}"),
                ("pushd", f"pushd {r} && {rt}"),
                ("builtin cd", f"builtin cd {r} && {rt}"),
                ("a cd inside $(...)", f"x=$(cd {r} && pwd) && {rt}"),
                ("a cd inside backticks", f"x=`cd {r}` && {rt}"),
                ("a cd inside an if body", f"if false; then\n cd {r}\nfi\n{rt}"),
                ("a cd behind time", f"time if false; then cd {r}; fi; {rt}"),
                ("a cd behind a case pattern's )", f"(case x in a) ;; esac; cd {r}); {rt}"),
                ("a cd behind a quoted fi", f"if false; then 'fi'; cd {r}; fi; {rt}"),
                ("a create after cd && exit;", f"cd {r} && exit; {rt}"),
                ("a command between the cd and the create", f"cd {r} && git status && {rt}"),
                ("export GH_REPO between the cd and the create", f"cd {r} && export GH_REPO=me/skills && {rt}"),
                ("export GIT_DIR between the cd and the create", f"cd {r} && export GIT_DIR={s}/.git && {rt}"),
                ("GIT_DIR on the create itself", f"cd {r} && GIT_DIR={s}/.git {rt}"),
                ("env -C redirecting the create", f"cd {r} && env -C {s} {rt}"),
                ("a repo named with -R after the cd", f"cd {r} && {rt} -R me/skills"),
                ("GH_REPO on the create after the cd", f"cd {r} && GH_REPO=someone/else {rt}")):
            refused(name, shape)
        refused("-R naming the session's own repo keeps its rules", f"cd {u} && {one} -R me/skills", "type:*")
        refused("GH_REPO naming the session's own repo keeps its rules", f"cd {u} && GH_REPO=me/skills {one}", "type:*")
        ok, why = verdict("cat <<EOF\n" + one, s)
        check("an unterminated heredoc refuses rather than swallowing the create",
              not ok and "could not be parsed" in why, why)
        ok, why = verdict("echo '<<X'\ngh issue create -t t\nX", s)
        check("a quoted <<X is text, so the unlabelled create after it is seen", not ok and "no --label" in why, why)
        ok, why = verdict("gh issue cre\\\nate -t t", s)
        check("a backslash-newline joins, so `cre\\<nl>ate` is still a create", not ok and "no --label" in why, why)
        full = "gh issue create -t X --label comp:a --label type:b --label prio:P2"
        check("CONTROL: a quoted <<EOF on the create's own line is not a parse error",
              verdict(full + " --body 'a<<EOF'", s)[0], verdict(full + " --body 'a<<EOF'", s)[1])
        check("CONTROL: arithmetic << is not a parse error",
              verdict("echo $((1<<n)) && " + full, s)[0], verdict("echo $((1<<n)) && " + full, s)[1])
        ok, why = verdict("cat <<< hi\ngh issue create -t X\nhi", s)
        check("a <<< herestring is not a heredoc, so the unlabelled create after it is seen",
              not ok and "no --label" in why, why)
        # A cd into ANOTHER checkout of the session's own repo files into the session's repo.
        clone = Path(td) / "clone"
        clone.mkdir()
        subprocess.run(["git", "init", "-q", str(clone)], check=True)
        subprocess.run(["git", "-C", str(clone), "remote", "add", "origin", "https://github.com/me/skills.git"], check=True)
        ok, why = verdict(f"cd {clone} && {one}", s)
        check("a cd into a clone of the session's own repo keeps the session's rules", not ok and "type:*" in why, why)
        up = Path(td) / "upstream-only"
        up.mkdir()
        (up / ".rails-flow").mkdir()
        (up / CONFIG).write_text(json.dumps(retask), encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(up)], check=True)
        subprocess.run(["git", "-C", str(up), "remote", "add", "upstream", "git@github.com:Me/Skills.git"], check=True)
        ok, why = verdict(f"cd {up} && {rt}", s)
        check("a target whose UPSTREAM is the session's repo keeps the session's rules", not ok and "comp:*" in why, why)
        subprocess.run(["git", "-C", str(up), "remote", "add", "origin", "https://github.com/someone/fork.git"], check=True)
        ok, why = verdict(f"cd {up} && {rt}", s)
        check("...and so does a fork origin with the session repo as upstream", not ok and "comp:*" in why, why)
        # The session's repo in every URL spelling a clone might carry (#1406 sixth review).
        for n, (kind, url) in enumerate((("userinfo", "https://x-access-token:secret@github.com/me/skills.git"),
                                         ("an ssh port", "ssh://git@github.com:22/me/skills.git"),
                                         ("an ssh alias", "git@github-work:me/skills.git"),
                                         ("an enterprise host", "https://github.example.com/Me/Skills"))):
            c = Path(td) / f"spelling{n}"
            (c / ".rails-flow").mkdir(parents=True)
            (c / CONFIG).write_text(json.dumps(retask), encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(c)], check=True)
            subprocess.run(["git", "-C", str(c), "remote", "add", "origin", url], check=True)
            ok, why = verdict(f"cd {c} && {rt}", s)
            check(f"a clone whose origin uses {kind} is the session's repo",
                  not ok and "comp:*" in why, why)
        # GH_REPO in the hook's environment redirects gh, so the cd is not certain.
        saved = os.environ.get("GH_REPO")
        os.environ["GH_REPO"] = "me/skills"
        try:
            ok, why = verdict(f"cd {r} && {rt}", s)
            check("GH_REPO in the environment keeps the session's rules", not ok and "comp:*" in why, why)
        finally:
            if saved is None:
                os.environ.pop("GH_REPO", None)
            else:
                os.environ["GH_REPO"] = saved
        # A session whose origin is a fork and whose UPSTREAM is the real repo: gh files upstream.
        s2 = Path(td) / "session-fork"
        (s2 / ".rails-flow").mkdir(parents=True)
        (s2 / CONFIG).write_text(json.dumps(skills), encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(s2)], check=True)
        subprocess.run(["git", "-C", str(s2), "remote", "add", "origin", "https://github.com/someone/fork.git"], check=True)
        subprocess.run(["git", "-C", str(s2), "remote", "add", "upstream", "https://github.com/me/skills.git"], check=True)
        ok, why = verdict(f"cd {clone} && {rt}", s2)
        check("a session whose upstream is the target's repo keeps its own rules", not ok and "comp:*" in why, why)
        # A session with NO remote cannot be told apart from anything: never follow.
        s3 = Path(td) / "session-bare"
        (s3 / ".rails-flow").mkdir(parents=True)
        (s3 / CONFIG).write_text(json.dumps(skills), encoding="utf-8")
        ok, why = verdict(f"cd {r} && {rt}", s3)
        check("a session with no remote keeps its own rules", not ok and "comp:*" in why, why)
        # Repo names in every spelling gh accepts.
        for spelling in ("-Rme/skills", "-R Me/Skills", "-R https://github.com/me/skills", "--repo=github.com/me/skills.git"):
            ok, why = verdict(f"{one} {spelling}", s)
            check(f"-R spelled `{spelling}` is the session's repo", not ok and "type:*" in why, why)
        check("CONTROL: a glued -R naming another repo needs one label, like the spaced form",
              verdict(f"{one} -Rsomeone/else", s)[0])
        ok, why = verdict(f"GH_REPO=https://github.com/other/x {one}", s)
        check("GH_REPO with no cd changes nothing, as before #1400", not ok and "type:*" in why, why)
        # The reverse direction: a correctly labelled create with no followed cd is ALLOWED, as on dev.
        for name, shape in (("echo cd", f"echo cd; {full}"), ("a subshell cd", f"(cd {u} && true); {full}"),
                            ("popd", f"popd; {full}"), ("grep cd", f"grep -rn cd docs; {full}")):
            check(f"CONTROL: `{name}` before a fully labelled create is allowed, as on dev",
                  verdict(shape, s)[0], verdict(shape, s)[1])
        # ---- #1440: a QUOTED `&&` is an argument, not the separator ----------------------------
        ok, why = verdict(f"cd {r} '&&' {rt}", s)
        check("a quoted '&&' does not make the followed cd shape", not ok and "comp:*" in why, why)
        check("CONTROL: a quoted cd OPERAND still makes it", verdict(f"cd '{r}' && {rt}", s)[0],
              verdict(f"cd '{r}' && {rt}", s)[1])

        # ---- #1423: a create the parser cannot label-check is refused, named -----------------------
        # `bare` is undeclared, so ONE label passes a create it can see: a refusal here is the shape.
        lab = "gh issue create -t X --label anything"
        for shape, cmd in (("`sh -c`", f"sh -c '{lab}'"), ("`bash -c`", f'bash -lc "{lab}"'),
                           ("`eval`", f"eval '{lab}'"), ("backticks", f"x=`{lab}`"),
                           ("a `$( … )` substitution", f"y=$({lab})")):
            ok, why = verdict(cmd, bare)
            check(f"a create inside {shape} is refused and named", not ok and shape in why and "directly" in why, why)
        for name, cmd in (("echo of the text", 'echo "gh issue create"'), ("grep for the text", "grep -rn 'gh issue create' docs"),
                          ("a backtick BEFORE the create", f"x=`date` && {lab}"), ("$( ) BEFORE the create", f"echo $(date) && {lab}")):
            check(f"CONTROL: {name} is not a hidden create", verdict(cmd, bare)[0], verdict(cmd, bare)[1])
        # Final review of #1454: text this repo writes daily must not read as a hidden create.
        for name, cmd in (("a commit message heredoc inside $( )",
                           "git commit -m \"$(cat <<'EOF'\nrefuse `gh issue create` here\nEOF\n)\""),
                          ("a PR body heredoc inside $( )", "gh pr create --title T --body \"$(cat <<'EOF'\nsee gh issue create\nEOF\n)\""),
                          ("single-quoted backticks", "git commit -m 'refuse `gh issue create`'")):
            check(f"CONTROL: {name} is not a hidden create", verdict(cmd, bare)[0], verdict(cmd, bare)[1])
        ok, why = verdict('echo "x `gh issue create -t X`"', bare)
        check("backticks inside DOUBLE quotes still run, so they are still refused", not ok and "backticks" in why, why)
        # ...and a wrapper does not hide a string that runs as a command.
        for name, cmd in (("env", f"env sh -c '{lab}'"), ("sudo", f"sudo -E bash -c '{lab}'"),
                          ("timeout", f"timeout 5 bash -c '{lab}'"), ("command eval", f"command eval '{lab}'"),
                          ("nohup", f"nohup sh -c '{lab}'")):
            ok, why = verdict(cmd, bare)
            check(f"a create behind `{name}` is refused", not ok and "directly" in why, why)
        # ---- #1462: more forms that reach gh, each seen or refused -------------------------------
        for name, cmd in (("gh issue new (an alias)", "gh issue new -t X"),
                          ("gh --repo o/r issue create (a global flag first)", "gh --repo o/r issue create -t X"),
                          ("a create split across a backslash-newline", "gh issue \\\ncreate -t X")):
            ok, why = verdict(cmd, bare)
            check(f"{name}: its missing label is refused", not ok and "no --label" in why, why)
        check("CONTROL: a labelled gh issue new passes", verdict("gh issue new -t X --label a", bare)[0])
        for shape, cmd in (("a pipe into `bash`", "echo 'gh issue create -t X' | bash"),
                           ("a herestring fed to `bash`", "bash <<< 'gh issue create -t X'"),
                           ("a heredoc fed to `bash`", "bash <<'EOF'\ngh issue create -t X\nEOF"),
                           ("`bash -c`", "bash -c 'gh issue \"create\" -t X'")):
            ok, why = verdict(cmd, bare)
            check(f"a create in {shape} is refused and named", not ok and shape in why and "directly" in why, why)
        check("CONTROL: a pipe into something that is not a shell is not a hidden create",
              verdict("echo 'gh issue create' | grep create", bare)[0])
        check("CONTROL: a quoted heredoc fed to cat is text, even naming $(gh issue create)",
              verdict("cat <<'EOF' > b.md\nrun $(gh issue create) later\nEOF\n" + lab, bare)[0])
        # Final review of #1477: more ways a shell reads a create from stdin.
        for shape, cmd in (("a herestring fed to `bash`", "bash <<<'gh issue create -t X'"),
                           ("a heredoc fed to `bash`", "cat <<'EOF' | bash\ngh issue create -t X\nEOF"),
                           ("a heredoc fed to `bash`", "timeout 5 bash <<EOF\ngh issue create -t X\nEOF"),
                           ("a pipe into `bash`", "echo 'gh issue create -t X' | cat | bash"),
                           ("a pipe into `bash`", "echo 'gh issue create -t X' |& bash")):
            ok, why = verdict(cmd, bare)
            check(f"{cmd.splitlines()[0][:34]!r}: refused as {shape}", not ok and shape in why, why)
        # #1489: a script fed to a shell by redirect -- the create lives in the file.
        script = Path(td) / "file-an-issue.sh"
        script.write_text("#!/bin/sh\ngh issue create -t X\n", encoding="utf-8")
        for name, form in (("a spaced redirect", f"bash < {script}"), ("a glued redirect", f"bash <{script}"),
                           ("a redirect behind timeout", f"timeout 5 sh < {script}")):
            ok, why = verdict(form, bare)
            check(f"{name} feeding a script with a create to a shell is refused", not ok and "by redirect" in why, why)
        harmless = Path(td) / "no-issue.sh"
        harmless.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
        check("CONTROL: a redirected script without a create is allowed", verdict(f"bash < {harmless}", bare)[0])
        ok, why = verdict(f"bash < {td}/nope.sh", bare)
        check("a redirect to a file that cannot be read is refused, fail closed (#1515)", not ok and "cannot read" in why, why)
        check("CONTROL: cat reading the same file is not a shell running it",
              verdict(f"cat < {script}", bare)[0])
        # #1489 review: the shell spellings and redirect forms the first version missed.
        for form in (f"/bin/bash < {script}", f"bash --norc < {script}", f"bash -o errexit < {script}",
                     f"sh<{script}", f"bash 0< {script}", f"bash 0<{script}"):
            ok, why = verdict(form, bare)
            check(f"{form.split(str(td))[0]!r}: refused as a script fed by redirect", not ok and "by redirect" in why, why)
        # A relative script resolves from the directory the command has cd'd to, not the session's.
        sub = Path(td) / "sub"
        sub.mkdir()
        (sub / "only.sh").write_text("gh issue create -t X\n", encoding="utf-8")
        (sub / "c2.sh").write_text("echo hi\n", encoding="utf-8")
        (Path(td) / "c2.sh").write_text("gh issue create -t X\n", encoding="utf-8")
        # A directory literally named `$X`: following `cd $X` as if literal would find a create here.
        (sub / "$X").mkdir()
        (sub / "$X" / "only.sh").write_text("gh issue create -t X\n", encoding="utf-8")
        ok, why = verdict(f"cd {sub} && bash < only.sh", bare)
        check("a relative script is read from the cd target", not ok and "by redirect" in why, why)
        was = os.getcwd()
        try:
            os.chdir(td)
            check("CONTROL: the cd target's harmless script is judged, not the session directory's",
                  verdict("cd sub && bash < c2.sh", bare)[0])
            ok, why = verdict("cd sub && cd $X && bash < only.sh", bare)
            check("after a cd it cannot resolve, a relative script is refused as unfollowable (#1513)",
                  not ok and "cannot follow" in why, why)
            ok, why = verdict("(cd sub) && bash < only.sh", bare)
            check("a cd inside ( ) does not outlive it, so only.sh is looked for where it is not: unreadable, refused (#1515)",
                  not ok and "cannot read" in why, why)
            ok, why = verdict("bash < c2.sh", bare)
            check("with no cd, a relative script is read from the session directory", not ok and "by redirect" in why, why)
            # #1495: the five #1489 edge cases. c2.sh here has a create; sub/c2.sh is harmless.
            for cmd, why_ in (("cd nope; bash < c2.sh", "a cd to a missing directory fails and changes nothing"),
                              ("(cd sub) && bash < c2.sh", "the subshell's cd does not outlive it"),
                              ("(cd sub && bash < only.sh)", "a cd inside ( ) holds until the )"),
                              ("bash -eo pipefail < c2.sh", "a bundled -o takes a value"),
                              ("bash 2>&1 < c2.sh", "the & of a fd duplication is not a separator"),
                              ("bash &>log < c2.sh", "&> is a redirect, not a background &")):
                ok, why = verdict(cmd, bare)
                check(f"#1495 `{cmd}` is refused: {why_}", not ok and "by redirect" in why and "cannot follow" not in why, why)
            check("#1495 CONTROL: a script operand after -eo VALUE reads stdin as data",
                  verdict("bash -eo pipefail sub/c2.sh < c2.sh", bare)[0])
            # #1513 review: the same five classes, shapes the first #1495 version still let through.
            for cmd, why_ in (("cd sub &>/dev/null; bash < only.sh", "a cd's own redirect is not an argument"),
                              ("cd sub > /dev/null; bash < only.sh", "a cd's spaced redirect is not an argument"),
                              ("bash -ox pipefail < c2.sh", "an o inside a bundle takes a value"),
                              ("bash -Oe extglob < c2.sh", "an O inside a bundle takes a value"),
                              ("bash 2>&1<c2.sh", "a redirect glued to < is cut out"),
                              ("bash>/dev/null<c2.sh", "a redirect glued to the shell is cut out"),
                              ("bash >&log < c2.sh", ">&word is a redirect"),
                              ("cd sub & bash < c2.sh", "a backgrounded cd runs in a subshell"),
                              ("cd sub | bash < c2.sh", "a piped cd runs in a subshell")):
                ok, why = verdict(cmd, bare)
                # the file itself was read: not the fail-closed "cannot follow" refusal, which would also pass
                check(f"#1513 `{cmd}` is refused: {why_}", not ok and "by redirect" in why and "cannot follow" not in why, why)
            check("#1513 CONTROL: a cd's redirect does not stop it being followed to a harmless script",
                  verdict("cd sub &>/dev/null; bash < c2.sh", bare)[0])
            check("#1513 CONTROL: `bash -ox pipefail sub/c2.sh < c2.sh` runs the operand, stdin is data",
                  verdict("bash -ox pipefail sub/c2.sh < c2.sh", bare)[0])
        finally:
            os.chdir(was)
        # #1513 review (R6): every _ansi_escape branch, checked on the decoded value.
        for raw, want in (("$'\\cA'", "\x01"), ("$'\\U00000066'", "f"), ("$'\\e'", "\x1b"), ("$'\\a\\b\\f\\v\\r'", "\a\b\f\v\r"),
                          ("$'\\x6'", "\x06"), ("$'\\q'", "\\q"), ("$'\\x'", "\\x"), ("$'it\\'s'", "it's")):
            got = shlex.split(_ansi_c(raw))
            check(f"#1513 _ansi_c decodes {raw} as {want!r}", got == [want], repr(got))
        # #1495: a label spelled with bash's escapes is that label.
        for spelled in ("$'\\x66eature'", "$'\\146eature'", "$'\\u0066eature'"):
            check(f"#1495 CONTROL: `-l {spelled}` is the label `feature`",
                  verdict(f"gh issue create -t X -l {spelled} --body-file b.md", r)[0],
                  verdict(f"gh issue create -t X -l {spelled} --body-file b.md", r)[1])
        # ANSI-C quoting is valid bash: it must parse, not be refused as unparseable.
        check("CONTROL: `echo $'it\\'s'` before a harmless redirected script is allowed",
              verdict(f"echo $'it\\'s'; bash < {harmless}", bare)[0], verdict(f"echo $'it\\'s'; bash < {harmless}", bare)[1])
        ok, why = verdict(f"echo $'it\\'s'; bash < {script}", bare)
        check("`echo $'it\\'s'` before a script with a create: still refused by redirect", not ok and "by redirect" in why, why)
        check("CONTROL: an unparseable command naming no create and no redirect is allowed",
              verdict('echo "unbalanced', bare)[0])
        ok, why = verdict(f'bash < {harmless}; echo "unbalanced', bare)
        check("an unparseable command with a shell redirect is refused as unparseable", not ok and "parsed" in why, why)
        # $HOME expands, and a large script's first 1 MB is read rather than the file being skipped.
        home = os.environ.get("HOME")
        try:
            os.environ["HOME"] = td
            for form in ("bash < $HOME/file-an-issue.sh", "bash < ${HOME}/file-an-issue.sh"):
                ok, why = verdict(form, bare)
                check(f"{form!r}: $HOME expands and the script is read", not ok and "by redirect" in why, why)
        finally:
            if home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = home
        # A shell with a script OPERAND runs that file; the redirected file is only its data.
        for form in (f"bash {harmless} < {script}", f"bash < {script} {harmless}", f"sh -e {harmless} < {script}"):
            check(f"CONTROL: {form.split(str(td))[0]!r}: stdin is data for a script operand, allowed", verdict(form, bare)[0])
        for form in (f"bash -s < {script}", f"bash -s arg1 < {script}", f"bash -o errexit < {script}", f"bash -- < {script}"):
            ok, why = verdict(form, bare)
            check(f"{form.split(str(td))[0]!r}: stdin is the script, refused by redirect", not ok and "by redirect" in why, why)
        big = Path(td) / "big.sh"
        big.write_text("gh issue create -t X\n" + "#" * 1_100_000 + "\n", encoding="utf-8")
        ok, why = verdict(f"bash < {big}", bare)
        check("a script over 1 MB is refused whole, not read for its first megabyte (#1515: past the read cap it cannot be judged)",
              not ok and "cannot read" in why, why)
        check("CONTROL: a multi-stage pipe ending in grep is not a hidden create",
              verdict("echo 'gh issue create' | cat | grep create", bare)[0])
        # ---- #1467: an UNQUOTED heredoc's substitutions really run ----------------------------------
        ok, why = verdict('x="$(cat <<EOF\n$(gh issue create -t X)\nEOF\n)"', bare)
        check("a $( ) create inside an unquoted heredoc is refused", not ok and "unquoted heredoc" in why, why)
        ok, why = verdict("cat <<EOF > b.md\n`gh issue create -t X`\nEOF", bare)
        check("a backtick create inside an unquoted heredoc is refused", not ok and "unquoted heredoc" in why, why)
        check("CONTROL: prose naming the command in an unquoted heredoc is text",
              verdict("cat <<EOF > b.md\nplease run gh issue create by hand\nEOF\n" + lab, bare)[0])
        for name, cmd in (("a PR body", 'gh pr create --title T --body "$(cat <<EOF\nuse \\`gh issue create\\`\nEOF\n)"'),
                          ("a commit message", "git commit -F - <<EOF\nsee \\`gh issue new\\`\nEOF")):
            check(f"CONTROL: an escaped backtick in {name}'s unquoted heredoc is text",
                  verdict(cmd, bare)[0], verdict(cmd, bare)[1])
        check("CONTROL: a \\EOF delimiter is quoted, so its body is literal",
              verdict("cat <<\\EOF > b.md\n$(gh issue create -t X)\nEOF\n" + lab, bare)[0])
        # ---- #1468: an escaped backtick is literal ---------------------------------------------------
        check("CONTROL: an escaped backtick inside double quotes is text",
              verdict('echo "use \\`gh issue create\\`"', bare)[0], verdict('echo "use \\`gh issue create\\`"', bare)[1])
        ok, why = verdict('echo "use `gh issue create -t X`"', bare)
        check("...while an unescaped one inside double quotes still runs, and is refused", not ok and "backticks" in why, why)

        ok, why = verdict("/usr/bin/gh issue create -t X", bare)
        check("a path to gh is gh: its missing label is refused", not ok and "no --label" in why, why)
        check("CONTROL: ...and a labelled one passes", verdict("/usr/bin/gh issue create -t X --label a", bare)[0])

        (r / CONFIG).write_text("{not json", encoding="utf-8")
        check("an unreadable declaration refuses rather than allowing",
              not verdict("gh issue create -t X --label feature", r)[0])

        # #1515 (a): A SCRIPT THE SHELL RUNS THAT THE HELPER NEVER READ. Each is refused through the helper, with a control.
        bad = Path(td) / "bad.sh"
        bad.write_text("gh issue create -t X --body y\n", encoding="utf-8")
        fine = Path(td) / "fine.sh"
        fine.write_text("echo hi\n", encoding="utf-8")
        gone = Path(td) / "gone.sh"
        huge = Path(td) / "huge.sh"
        huge.write_text("echo hi\n" + "# padding\n" * 120_000 + "gh issue create -t X --body y\n", encoding="utf-8")
        for cmd, why_ in ((f"bash {bad}", "a script operand"), (f"sh {bad}", "sh with an operand"),
                          (f"source {bad}", "source"), (f". {bad}", "the dot"),
                          (f"cat {bad} | bash", "cat into a shell"), (f"bash <(cat {bad})", "a process substitution"),
                          (f'bash -c "$(cat {bad})"', "a command string built from the file"),
                          (f'bash 2>&1 <<<"$(cat {bad})"', "a herestring built from the file"),
                          (f"bash -c `cat {bad}`", "backticks around cat")):
            ok, why = verdict(cmd, bare)
            check(f"(#1515) {why_}: {cmd.replace(str(td), '')!r} is refused", not ok, why)
        ok, why = verdict("bash -s <<'EOF'\ngh i\\ssue cr\\eate -t X --body y\nEOF", bare)
        check("(#1515) a quoted heredoc fed to `bash -s` has its escapes decoded before matching", not ok and "heredoc" in why, why)
        for cmd in (f"bash {gone}", f"source {gone}", f"cat {gone} | bash", f"bash <(cat {gone})"):
            ok, why = verdict(cmd, bare)
            check(f"(#1515) a script file that cannot be read is REFUSED, fail closed: {cmd.replace(str(td), '')!r}",
                  not ok and "cannot read" in why, why)
        ok, why = verdict(f"bash {huge}", bare)
        check("(#1515) a script past the 1 MB read cap is refused, not judged on its first megabyte", not ok and "cannot read" in why, why)
        for cmd, why_ in ((f"bash {fine}", "a harmless script"), (f"source {fine}", "source of a harmless one"),
                          (f"cat {fine} | bash", "cat of a harmless one into a shell"), (f"bash <(cat {fine})", "a harmless substitution"),
                          (f'bash -c "$(cat {fine})"', "a harmless command string"),
                          (f"cat {bad} | wc -l", "cat of a create script is not run by a shell"),
                          (f'echo "$(cat {bad})"', "a substitution no shell runs"),
                          ('bash "$DIR/run.sh"', "a path the hook cannot resolve is allowed, as before"),
                          (f"bash -c 'echo hi' {bad}", "-c runs its string, the operand is data")):
            check(f"(#1515) CONTROL: {cmd.replace(str(td), '')!r} is allowed ({why_})", verdict(cmd, bare)[0])

        # #1515 (b): A CREATE INVOKED INDIRECTLY (decided: the gate claims them). Each refused, with a control.
        for cmd, why_ in (("$(echo gh) issue create -t X --body y", "a gh word from a substitution"),
                          ("G=gh; $G issue create -t X --body y", "a gh word from a variable"),
                          ("alias g=gh; g issue create -t X --body y", "an alias"),
                          ("echo issue create -t X --body y | xargs gh", "the verb through xargs"),
                          ("gh api -X POST repos/o/r/issues -f title=X", "the API, an explicit POST"),
                          ("gh api repos/o/r/issues -f title=X", "the API, fields imply a POST"),
                          ("gh api --method POST /repos/o/r/issues --field title=X", "the API, long flags"),
                          ("gh -R o/r api -X POST repos/o/r/issues -f title=X", "the API after the repo flag")):
            ok, why = verdict(cmd, bare)
            check(f"(#1515) {why_}: {cmd!r} is refused", not ok, why)
        for cmd, why_ in (("gh api repos/o/r/issues", "a GET of the collection"),
                          ("gh api -X POST repos/o/r/issues/12/comments -f body=x", "a comment, not an issue"),
                          ("gh api repos/o/r/issues/12", "one issue"),
                          ("alias g=gh; g issue list", "an alias used for something else"),
                          ('echo "alias g=gh"', "the words in an echo"),
                          ("echo issue create | cat", "the verb piped to cat, not to xargs gh"),
                          ("gh issue create -t X --body y --label feature", "a direct labelled create still passes")):
            check(f"(#1515) CONTROL: {cmd!r} is allowed ({why_})", verdict(cmd, bare)[0])

        # #1645 R1: A COMMENT LINE MUST NOT SWALLOW THE CREATE AFTER IT (also true on dev). Each refused, with controls that must stay allowed.
        for cmd, why_ in (("# note\ngh issue create -t X --body y", "a comment line, then an unlabelled create"),
                          ("echo hi # note\ngh issue create -t X --body y", "a trailing comment, then an unlabelled create"),
                          ("# note\n\ngh issue create -t X --body y", "a comment, a blank line, then an unlabelled create"),
                          ("# one\n# two\ngh issue create -t X --body y", "two comment lines, then an unlabelled create"),
                          ("# note \\\ngh issue create -t X --body y", "a comment ending in a backslash, then an unlabelled create")):
            ok, why = verdict(cmd, bare)
            check(f"(#1645 R1) {why_}: {cmd!r} is refused", not ok and "no --label" in why, why)
        ok, why = verdict("echo a#b; gh issue create -t X --body y", bare)
        check("(#1645 R1) a # inside a word is not a comment: the create after it on the same line is refused", not ok and "no --label" in why, repr((ok, why)))
        cs = Path(td) / "commented.sh"
        cs.write_text("# don't file this by hand\ngh issue create -t X --body y\n", encoding="utf-8")
        ok, why = verdict(f"sh {cs}", bare)
        check("(#1645 R1) a script body: a comment line, then an unlabelled create (the second parse) is refused", not ok, why)
        check("(#1645 R1) CONTROL: a # inside quotes does not hide a labelled create after the closing quote",
              verdict('echo "see #12 and #13"\ngh issue create -t X --body y --label feature', bare)[0],
              verdict('echo "see #12 and #13"\ngh issue create -t X --body y --label feature', bare)[1])
        for cmd, why_ in (("# note\ngh issue create -t X --body y --label feature", "a labelled create after a comment"),
                          ("# note \\\ngh issue create -t X --body y --label feature", "a labelled create after a comment ending in a backslash"),
                          ("# gh issue create is how you file one\necho hi", "the command named only inside a comment"),
                          ("echo a#b", "a # inside a word"), ('echo "see #12 and #13"', "a # inside double quotes"),
                          ("echo 'see #12'\ngh issue list", "a # inside single quotes"),
                          ("cat > b.md <<'EOF'\n# a heading\nEOF\ngh issue list", "a # in a heredoc body")):
            check(f"(#1645 R1) CONTROL: {cmd!r} is allowed ({why_})", verdict(cmd, bare)[0], verdict(cmd, bare)[1])

        # CodeQL (#1645): NO COMMAND MAY MAKE THE GUARD HANG. Each shape is decided in a CHILD process with a hard timeout, so a pattern that backtracks fails here
        # instead of hanging the selftest; the child reports its own CPU seconds (best of two), which a loaded machine does not inflate as it does the wall clock.
        timing = ("import sys, time, tempfile\nfrom pathlib import Path\nsys.path.insert(0, sys.argv[1])\nimport issue_labels as il\n"
                  "cmd = {shape!r}\nroot = Path(tempfile.mkdtemp())\nbest = 1e9\n"
                  "for _ in range(2):\n    t = time.process_time(); il.verdict(cmd, root); best = min(best, time.process_time() - t)\nprint(best)\n")
        for shape, why_ in (("bash " + "<&>" * 50000 + " ok", "50,000 x `<&>` after a shell word (CodeQL's shape)"),
                            ("bash " + "<&>" * 50000 + "$(echo hi)", "50,000 x `<&>` before an echo substitution"),
                            ("bash " * 50000, "50,000 shell words with no substitution (a rescan from each)"),
                            ("$(" * 50000, "50,000 nested `$(` (each span re-read)"),
                            ("bash <(echo " * 40, "40 x `bash <(echo ` (each marker's operand re-read by the next: exponential)")):
            try:
                done = subprocess.run([sys.executable, "-c", timing.format(shape=shape), str(Path(__file__).resolve().parent)],
                                      capture_output=True, text=True, timeout=30)
                spent = float(done.stdout.strip() or 1e9)
            except subprocess.TimeoutExpired:
                spent = float("inf")
            check(f"(#1645 CodeQL) {why_}: decided in under 1 CPU second (took {spent:.2f}s)", spent < 1.0)

        # #1645 R2: VARIANTS OF THE SHAPES THE GATE CLAIMS. Each refused through the helper, with a control. Files are absolute so the cwd does not matter.
        argsf = Path(td) / "args.txt"
        argsf.write_text("issue create -t X --body y\n", encoding="utf-8")
        okargs = Path(td) / "okargs.txt"
        okargs.write_text("issue list\n", encoding="utf-8")
        ind = Path(td) / "ind.sh"
        ind.write_text("G=gh; $G issue create -t X\n", encoding="utf-8")
        als = Path(td) / "als.sh"
        als.write_text("alias g=gh\ng issue create -t X\n", encoding="utf-8")
        fnsh = Path(td) / "fn.sh"
        fnsh.write_text('g() { command gh "$@"; }\ng issue create -t X\n', encoding="utf-8")
        chain = Path(td) / "chain.sh"
        chain.write_text(f". {bad}\n", encoding="utf-8")
        selfsrc = Path(td) / "self.sh"
        selfsrc.write_text(f". {selfsrc}\n", encoding="utf-8")
        check("(#1645 R2) a self-sourcing script is bounded: the recursion stops at its depth cap and the harmless script is allowed",
              verdict(f"bash {selfsrc}", bare)[0], verdict(f"bash {selfsrc}", bare)[1])
        for cmd, label in (
                ("alias g='gh issue'; g create -t X", "alias whose body is `gh issue`"),
                ("alias mk='gh issue create'; mk -t X", "alias whose body is the whole create"),
                ('g() { command gh "$@"; }; g issue create -t X', "function wrapper"),
                ('function g { gh "$@"; }; g issue create -t X', "`function` keyword wrapper"),
                ('g() { gh issue create "$@"; }; g -t X', "function whose body is the create"),
                (f"xargs -a {argsf} gh", "xargs -a FILE"), (f"cat {argsf} | xargs gh", "a file piped to xargs gh"),
                ("echo create | xargs -I{} gh issue {} -t X", "xargs -I{} replacing the verb"),
                (f'bash -c "$(<{bad})"', "$(<f) in a -c string"), (f'bash <<< "$(<{bad})"', "$(<f) in a herestring"),
                (f"bash <(<{bad})", "a process substitution that reads the file"), (f'eval "$(cat {bad})"', "eval of cat"),
                (f'eval "$(<{bad})"', "eval of $(<f)"), ("bash <(echo 'gh issue create -t X')", "a process substitution that echoes the script"),
                (f"tail -n +1 {bad} | sh", "tail into a shell"), (f"head -5 {bad} | sh", "head into a shell"),
                (f"sed 1d {bad} | bash", "sed into a shell"), (f"grep . {bad} | sh", "grep into a shell"),
                (f"xargs sh {bad}", "xargs sh FILE"), (f"find . -exec sh {bad} \\;", "find -exec sh FILE"),
                (f"bash {ind}", "a script that builds the gh word at run time"), (f"bash {als}", "a script that aliases gh"),
                (f"bash {fnsh}", "a script that wraps gh in a function"),
                ("sh <<'EOF'\nG=gh; $G issue create -t X\nEOF", "a heredoc fed to a shell that builds the gh word"),
                ("sh <<'EOF'\nalias g=gh\ng issue create -t X\nEOF", "a heredoc fed to a shell that aliases gh"),
                (f"sh -c '. {bad}'", "a -c string that sources the file"), (f"sh -c 'bash {bad}'", "a -c string that runs a shell on the file"),
                (f"if true; then . {bad}; fi", "`then . f`"), (f"for i in 1; do . {bad}; done", "`do . f`"),
                (f"{{ . {bad}; }}", "`{ . f; }`"), (f"builtin source {bad}", "builtin source"), (f"command . {bad}", "command ."),
                (f"time . {bad}", "time ."), (f"! . {bad}", "`! . f`"), (f"bash {chain}", "a script that sources a script")):
            ok, why = verdict(cmd, bare)
            check(f"(#1645 R2) {label}: {cmd.replace(str(td), '')!r} is refused", not ok, why)
        for cmd, label in (
                ("alias g='gh issue'; g list", "an alias of `gh issue` used for a list"), ('g() { gh "$@"; }; g issue list', "a gh wrapper used for a list"),
                ("g() { echo hi; }; g issue create-nothing", "a function that is not gh"),
                (f"xargs -a {okargs} gh", "xargs -a FILE naming a list"), (f"cat {fine} | xargs gh", "a harmless file piped to xargs gh"),
                ("echo list | xargs -I{} gh issue {}", "xargs -I{} replacing a list verb"),
                (f'bash -c "$(<{fine})"', "$(<f) of a harmless file"), (f'eval "$(cat {fine})"', "eval of a harmless file"),
                ("bash <(echo 'echo hi')", "a process substitution that echoes harmless text"),
                (f"tail -n +1 {fine} | sh", "tail of a harmless file into a shell"), (f"sed 1d {fine} | bash", "sed of a harmless file into a shell"),
                (f"tail -n +1 {bad} | wc -l", "tail of a create script that no shell runs"),
                (f"find . -exec echo {bad} \\;", "find -exec of a command that is not a shell"),
                (f"sh -c '. {fine}'", "a -c string that sources a harmless file"), (f"if true; then . {fine}; fi", "`then . f` of a harmless file"),
                (f"{{ . {fine}; }}", "`{ . f; }` of a harmless file"), (f"builtin source {fine}", "builtin source of a harmless file"),
                (f"time . {fine}", "time . of a harmless file"), (f"bash {fine}", "a harmless script"),
                ("sh <<'EOF'\necho hi\nEOF", "a harmless heredoc fed to a shell")):
            check(f"(#1645 R2) CONTROL: {cmd.replace(str(td), '')!r} is allowed ({label})", verdict(cmd, bare)[0], verdict(cmd, bare)[1])

    for f in fails:
        print(f"FAIL {f}")
    print(f"issue_labels selftest: {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
