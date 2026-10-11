#!/usr/bin/env python3
"""Every feature has an end-to-end path that a runner actually SELECTS (#1856, slice 2 of #1853).

WHY. The owner's rule (#1853): "every feature must have a way to test it end to end". Downstream, a `@real-signin` Playwright spec existed and passed on the
dev runner, but the image runner ran `--grep "@qa-image"`, which never selected it, so nothing flagged that the feature had no end-to-end path where it
mattered. A spec that no runner picks up is not a path: it counts as missing. Slice 1 (check_requirements.py) links a requirement to a manual case; this
links a requirement marked as a feature to a spec that is selected.

    python3 check_e2e_paths.py                    # the gate
    python3 check_e2e_paths.py --base origin/dev  # the base to compare the baseline with (default as in check_requirements.py)
    python3 check_e2e_paths.py --selftest         # the plumbing, against canned listings and stub executables
    python3 check_e2e_paths.py --selftest --real DIR   # also run the attack battery against a REAL Playwright (DIR holds its node_modules)

THE AUTHORITY IS PLAYWRIGHT ITSELF. The first version of this check re-implemented Playwright's argument parsing (`--grep`, `--grep-invert`, positional filters,
`--config`, `testDir`) and an independent review found six ways it disagreed with the real thing (attached `-g@tag` values, a case-insensitive CLI grep, a config
that is not at the default path, a `testDir` elsewhere, positional filters that are OR'd, `--list`). Patching each one is a loop that never ends, so this version
asks Playwright: for each runner command it runs the same command with `--list --reporter=json` and reads which tests Playwright says it would run. A feature
passes only if a listed, non-skipped test names it. The text of a runner file is read for ONE thing: to FIND the `playwright test` commands, and to refuse the
ones it cannot execute safely.

THIS IS A PROJECT GATE, run in the project's own CI or on its developer's machine, never a PreToolUse hook: running the project's own `npx --no-install playwright`
(which loads the project's playwright config and spec files, as its own test run does) is in scope. It never installs anything. The arguments are passed as an
argument list (no shell), and only `playwright test` is ever run.

WHAT IT READS (Playwright only; any other `web_e2e` is exit 2, never a pass):
  qa/requirements.yml        the registry of slice 1; an entry with `feature: true` (a JSON boolean) needs an end-to-end path (an owner-decision is exempt)
  the runners                the files listed under `e2e_paths: runners:` in qa/qa.config.yml (a shell script, a package.json)
  the listings               `playwright test --list --reporter=json`, once with no filter (every test Playwright finds) and once per runner command
A requirement NAMES a test when its id is a whole token of a describe title, a test title or a tag (Playwright reports tags without the `@`). A test Playwright
marks skipped (`test.skip`, `test.fixme`) names nothing. Paths and the runner list come from the `e2e_paths:` section of qa/qa.config.yml (`config`, `baseline`,
`cwd`, `runners`); defaults qa/playwright.config.ts and qa/e2e-unselected-baseline.txt. The listings run from the directory of the playwright config (`qa/`), or
from `cwd` when it is set; a runner file that `cd`s somewhere else needs `cwd` to say so.

THE RUNNER'S ENVIRONMENT is part of its selection (a config can read it: `grep: process.env.QA_TARGET === "image" ? ... : undefined`), so literal assignments are
applied to the listing's environment: `NAME=value` before the command, `env NAME=value`, `cross-env NAME=value`, an earlier top-level `export NAME=value`, and
`export NAME` of an earlier literal `NAME=value`. A value that is not a plain literal (a `$`, a backtick, a glob), an `export` inside control flow, an `unset`,
`set -a`, a `source` or `.` line (an env file can export anything the config reads) and an `export NAME` with no literal value are refused (exit 2), because the environment the run sees is then not knowable here. Redirections (`2>&1`,
`> file`, `>> file`, `&> file`, `< file`) are shell, not Playwright, and are stripped. `--only-changed` and `--last-failed` narrow the run by git or last-run state a
listing cannot see, so a command that uses them is refused, never listed wider than it runs.

THE STATEMENTS BEFORE THE COMMAND are an ALLOWLIST, because the shell has too many builtins to deny one by one (the first denylist missed `eval "export ..."`, `declare -x`,
`typeset -x`, `command export` and a function that sources a file). Before the runner command a script may have only: the shebang, comments and blank lines; `set -e`,
`set -u`, `set -o pipefail` (and combinations); a literal `NAME=value` or `export NAME=value` (applied to the listing, above); a literal `cd DIR` when `cwd` is set;
and CHILD PROCESSES, a simple command whose first word is not a shell builtin or keyword (docker, curl, ./setup.sh, another `npx playwright test`): a child process
cannot change the runner's environment. Everything else runs in the runner's own shell and is refused (exit 2): any other builtin or keyword (eval, declare, typeset,
command, builtin, source, `.`, read, printf, echo, local, alias, unset, `set` with any other option), a function definition or call, a group `{ }` or subshell `( )`,
a chain or pipeline with such a part, and a `$( )` or backtick anywhere. The builtin and keyword set is PINNED in this file (bash 3.2 and 5, dash, zsh) and the selftest
asserts it covers `bash -c 'compgen -b; compgen -k'` of the bash it runs on, so a newer shell's builtin fails the selftest here instead of slipping through.

WHAT ELSE IT REFUSES TO EXECUTE (exit 2, with the reason, never a pass): a command whose arguments are built from a shell variable or a substitution; one that sits in
shell control flow (`if`, `for`, `while`, `case`, a function body); one with anything else on its line before it (`[ ... ] && cmd`, `a || cmd`, `x | cmd`); one after
a heredoc, an `exit` or a `return`; one after a `cd` unless `cwd` is set; a package.json script that pipes or uses `||`. A runner command that is only a listing
(`--list`) runs nothing and is not a runner. If Playwright cannot be run (not installed, a config error, a timeout, no JSON on stdout) the verdict is "could not check" (exit 2).
A `--project` filter is passed through, so Playwright applies it.

THE GATE FAILS WHEN
  1. a feature requirement is named by no active test in the unfiltered listing, or is named only by tests that every runner command leaves out, and is not on the
     baseline (`qa/e2e-unselected-baseline.txt`, a ratchet that may only shrink, with a `# size: N` header and `--base` as in slice 1);
  2. a baseline line names a requirement that is now selected, is not a feature, is an owner-decision, or is not in the registry, or the size header is wrong.

EXIT CODES. 0 clean; 1 findings; 2 COULD NOT CHECK (a registry or path that cannot be read, no runner declared, a non-Playwright runner, a Playwright that cannot be run,
a command refused as unsafe to execute): the project gate runner (project_gates.py) grades 2 as ERROR and 3 as "not applicable", which never fails a run, so a check that
could not look must not say 3; 3 only when the DEFAULT base ref is missing (a project on `main`) and nothing else is wrong, the #1029 precedent where the project chooses.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_requirements as cr  # noqa: E402

E2E_BASELINE = "qa/e2e-unselected-baseline.txt"
DEFAULTS = {"config": "qa/playwright.config.ts", "baseline": E2E_BASELINE}
TIMEOUT = 180
DROP_FLAGS = {"--list", "--ui", "--debug", "--headed"}
NARROWING = ("--only-changed", "--last-failed")     # narrow by git or last-run state a listing cannot see: the command is unreadable, never dropped
DROP_WITH_VALUE = {"--reporter"}


# ---- Playwright's own answer -------------------------------------------------------------------------------------------------------------------------


def flatten(data: dict) -> list[dict]:
    """The specs of a `--list --reporter=json` document: {titles: [describe titles..., test title], tags: [...], file, active}. `active` is False for a test
    Playwright marks skipped."""
    found: list[dict] = []

    def walk(suite: dict, chain: list[str], top: bool) -> None:
        title = suite.get("title") or ""
        # the file's own suite is titled with the file name; it is not a describe
        inner = chain if (top and title == os.path.basename(suite.get("file") or title)) else [*chain, title] if title else chain
        for spec in suite.get("specs", []):
            tests = spec.get("tests", [])
            found.append({"titles": [*inner, spec.get("title", "")], "tags": [str(t) for t in spec.get("tags", [])], "file": spec.get("file") or suite.get("file") or "",
                          "active": any(t.get("expectedStatus") != "skipped" for t in tests)})
        for child in suite.get("suites", []):
            walk(child, inner, False)

    for suite in data.get("suites", []):
        walk(suite, [], True)
    return found


class Lister:
    """Runs `npx --no-install playwright test <args> --list --reporter=json` and returns its specs. Subclassed by the selftest, never mocked at the subprocess."""

    def list(self, cwd: Path, args: list[str], env: dict[str, str] | None = None) -> tuple[list[dict] | None, str | None]:
        """`env` is the runner's own literal assignments (`QA_TARGET=image npx playwright test`, an earlier `export`), layered on this process's environment."""
        argv = ["npx", "--no-install", "playwright", "test", *args, "--list", "--reporter=json"]
        try:
            done = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL, env={**os.environ, **(env or {})})
        except FileNotFoundError:
            return None, "`npx` is not installed, so Playwright could not be run"
        except subprocess.TimeoutExpired:
            return None, f"Playwright did not finish listing in {TIMEOUT}s"
        try:
            data = json.loads(done.stdout)
        except ValueError:
            return None, f"Playwright printed no JSON listing (exit {done.returncode}): {(done.stderr or done.stdout).strip()[:160]!r}"
        if not isinstance(data, dict):
            return None, f"Playwright printed JSON that is not a listing: {str(data)[:120]!r}"
        # a filter that matches nothing is reported as the error "No tests found" (exit 1) with an empty suite list: that is an empty listing, not a failure
        errors = [e for e in data.get("errors") or [] if "No tests found" not in str(e.get("message", "") if isinstance(e, dict) else e)]
        if errors:
            return None, f"Playwright reported errors: {json.dumps(errors)[:160]}"
        return flatten(data), None


# ---- finding the runner commands ---------------------------------------------------------------------------------------------------------------------


def strip_shell_comments(text: str) -> str:
    """`text` without shell comments: a `#` at the start of a word, outside quotes, ends the line. A comment that says `playwright test` is not a runner."""
    lines = []
    for line in text.split("\n"):
        quote, cut = "", len(line)
        for i, ch in enumerate(line):
            if quote:
                if ch == quote:
                    quote = ""
            elif ch in "\"'":
                quote = ch
            elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
                cut = i
                break
        lines.append(line[:cut])
    return "\n".join(lines)


def command_text(source: str, start: int) -> str:
    """The rest of a shell command from `start`: up to a newline, `;`, `&&`, `||` or `|` that is NOT inside a quote (a grep pattern holds `|`)."""
    quote, i, n = "", start, len(source)
    while i < n:
        ch = source[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch in "\n;|" or source.startswith("&&", i):
            break
        i += 1
    return source[start:i]


CLEAN_PREFIX = re.compile(r"^\s*(?:(?:exec|env|cross-env|npx(?:\s+(?:--no-install|-y|--yes))*|pnpm(?:\s+exec)?|yarn(?:\s+run)?|bunx|npm\s+exec(?:\s+--)?|[A-Za-z_][A-Za-z0-9_]*=\S*)\s+)*$")
ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
NOT_LITERAL = re.compile(r"[$`*?\[~()\\]")
ODD_ASSIGNMENT = re.compile(r"^[A-Za-z_][\w.+\[\]-]*\+?=")      # `NAME+=x`, `a[0]=x`, `a=(x)`: an assignment form other than the exact NAME=literal
# A PINNED COPY of the words a shell treats as its own (bash 3.2 and 5, dash, zsh): builtins and keywords. A statement whose first word is one of these runs IN the
# runner's shell and can change what the runner sees (`eval`, `declare -x`, `source`, `command export`, `alias`, a function); any other first word is a child process,
# which cannot. The selftest asserts the pinned set covers `bash -c 'compgen -b; compgen -k'` of the bash it runs on, so a newer shell's builtin fails the selftest here.
SHELL_WORDS = frozenset("""
! . : [ [[ ]] { } - alias autoload bg bind bindkey break builtin bye caller case cd chdir command compadd compcall compctl compdescribe compgen complete compopt compset continue
coproc declare dirs disable disown do done echo elif else emulate enable esac eval exec exit export false fc fg fi float for function functions getln getopts hash help history
if in integer jobs kill let limit local log logout mapfile noglob popd print printf private pushd pushln pwd read readarray readonly rehash return sched select set setopt shift
shopt source suspend test then time times trap true ttyctl type typeset ulimit umask unalias unfunction unhash unlimit unset unsetopt until vared wait whence where which while
zcompile zformat zle zmodload zparseopts zstyle
""".split())
SET_OPTIONS = re.compile(r"^-[eu]+$")
SOURCED = re.compile(r"(?:^|[;&|(])[ \t]*(?:source|\.)[ \t]+\S", re.M)           # `source f` and `. f`; `./script` is a path, not the dot command
OPENERS = re.compile(r"(?:^|[;&|(]|\bthen\b|\bdo\b|\belse\b|\bin\b)\s*(if|for|while|until|case|select)\b", re.M)
CLOSERS = re.compile(r"\b(fi|done|esac)\b")


def top_level_split(text: str) -> list[str]:
    """The statements of a shell fragment: split at a newline, `;`, `&&`, `||`, a single `|` (each pipeline stage is judged alone) and a background `&`, outside quotes.
    A `&` that is part of a redirection (`2>&1`, `&>file`) does not split."""
    parts: list[str] = []
    cur: list[str] = []
    quote = ""
    i, n = 0, len(text)

    def flush() -> None:
        parts.append("".join(cur))
        cur.clear()

    while i < n:
        ch = text[i]
        if quote:
            cur.append(ch)
            if ch == quote and text[i - 1] != "\\":
                quote = ""
        elif ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch in "\n;|":
            flush()
        elif text.startswith("&&", i):
            flush()
            i += 1
        elif ch == "&" and not (i > 0 and text[i - 1] in "<>") and not (i + 1 < n and text[i + 1] == ">"):
            flush()
        else:
            cur.append(ch)
        i += 1
    flush()
    return parts


def statement_refusal(statement: str, allow_cd: bool) -> str | None:
    """Why one statement before the runner command cannot be accounted for, or None. UNDERSTOOD: `set -e -u -o pipefail`, a literal `NAME=value`, `export` (its values are
    judged by `exported`), `cd <literal>` when `cwd` is set. A CHILD PROCESS (a first word that is not a shell word: docker, curl, ./setup.sh) cannot change the runner's
    environment. Everything else, a builtin or a keyword, a function or a group, runs in the runner's shell and is refused."""
    stmt = statement.strip()
    if not stmt:
        return None
    if stmt[0] in "({":
        return "a group or a function body"
    try:
        words = shlex.split(stmt)
    except ValueError as exc:
        return f"it cannot be split ({exc})"
    i = 0
    while i < len(words) and ASSIGNMENT.match(words[i]):
        if NOT_LITERAL.search(words[i].partition("=")[2]):
            return f"the value of {words[i].partition('=')[0]} is not a plain literal"
        i += 1
    if i == len(words):
        return None
    command, args = words[i], words[i + 1:]
    if ODD_ASSIGNMENT.match(command):
        return f"an assignment form other than the exact NAME=literal ({command[:30]!r}): `+=`, an array or an indexed name"
    if re.match(r"^[A-Za-z_][\w-]*\s*\(\)", stmt):
        return "a function definition"
    if command == "set":
        k = 0
        while k < len(args):
            if SET_OPTIONS.match(args[k]):
                k += 1
            elif re.match(r"^-[eu]*o$", args[k]) and k + 1 < len(args) and args[k + 1] == "pipefail":
                k += 2
            else:
                return f"`set {args[k]}` is not one of -e, -u, -o pipefail"
        return None
    if command == "export":
        return None
    if command == "cd":
        if allow_cd and len(args) == 1 and not NOT_LITERAL.search(args[0]):
            return None
        return "a `cd` that is not to a literal directory with `cwd` set"
    if command in SHELL_WORDS:
        return f"`{command}` is a shell builtin or keyword, which runs in the runner's own shell"
    return None


def unaccounted(prior: str, allow_cd: bool) -> str | None:
    """Why the text before a runner command (a shell script's earlier statements) cannot be fully accounted for, or None."""
    if "$(" in prior or "`" in prior:
        return "a command substitution comes before it, so what runs is not knowable here"
    for statement in top_level_split(prior):
        why = statement_refusal(statement, allow_cd)
        if why:
            return f"a statement before it cannot be accounted for ({statement.strip()[:40]!r}): {why}. Only `set -e/-u/-o pipefail`, literal assignments and exports, `cd <literal>` (with `cwd` set) and child processes may come before it"
    return None


def shell_refusal(prior: str, prefix: str, allow_cd: bool) -> str | None:
    """Why a command found in a shell script cannot be executed safely, or None. `prior` is the text before its line, `prefix` the text before it on its line."""
    if not CLEAN_PREFIX.match(prefix):
        return f"something else runs on the same line before it ({prefix.strip()[:40]!r}): a condition, a pipe or another command"
    if re.search(r"<<-?\s*['\"]?\w", prior):
        return "a heredoc comes before it"
    if re.search(r"(?:^|[;&|(\s])(?:exit|return)\b", prior):
        return "an `exit` or `return` comes before it"
    if len(OPENERS.findall(prior)) - len(CLOSERS.findall(prior)) > 0 or prior.count("{") - prior.count("}") > 0:
        return "it sits inside shell control flow (an `if`, `for`, `while`, `case` or a function body)"
    if SOURCED.search(prior):
        return "a `source` or `.` comes before it, and an env file can export anything the config reads, so the environment it runs in is not knowable here"
    if not allow_cd and re.search(r"(?:^|[;&|(\s])cd\s", prior):
        return "a `cd` comes before it, so the directory it runs in is unknown (set `cwd` under `e2e_paths:` to say which)"
    return unaccounted(prior, allow_cd)


def script_refusal(prefix: str, allow_cd: bool) -> str | None:
    """The same for a package.json script string: `a && playwright test` and `a; playwright test` are fine, `||` and a pipe are not."""
    if "||" in prefix or re.search(r"(?<!\|)\|(?!\|)", prefix):
        return "a `||` or a pipe comes before it"
    if re.search(r"(?:^|[;&|(\s])(?:exit|return)\b", prefix):
        return "an `exit` comes before it"
    if SOURCED.search(prefix):
        return "a `source` or `.` comes before it, and an env file can export anything the config reads, so the environment it runs in is not knowable here"
    if not allow_cd and re.search(r"(?:^|[;&|(\s])cd\s", prefix):
        return "a `cd` comes before it, so the directory it runs in is unknown (set `cwd` under `e2e_paths:` to say which)"
    parts = re.split(r"&&|;", prefix)
    return unaccounted("\n".join(parts[:-1]), allow_cd)


def assignments(words: str) -> tuple[dict[str, str], str | None]:
    """The literal `NAME=value` words of a command prefix, and the reason one of them cannot be applied (a `$`, a backtick or a glob in the value)."""
    found: dict[str, str] = {}
    try:
        raw_words = shlex.split(words, posix=False)
    except ValueError as exc:
        return found, f"an assignment cannot be split ({exc})"
    for raw in raw_words:
        m = ASSIGNMENT.match(raw)
        if not m:
            continue
        if NOT_LITERAL.search(m.group(2)):
            return found, f"the value of {m.group(1)} is not a plain literal ({m.group(2)[:30]!r}): a variable, a substitution or a glob"
        found[m.group(1)] = (shlex.split(raw)[0].partition("=")[2]) if raw else ""
    return found, None


def exported(prior: str) -> tuple[dict[str, str], str | None]:
    """The environment an earlier part of a shell script exports: literal `export NAME=value` lines at the top level. A conditional export, an `unset`, `set -a`,
    and an `export NAME` with no literal value are refused, because the value the runner sees is then not knowable here."""
    env: dict[str, str] = {}
    shell_vars: dict[str, str] = {}
    depth = 0
    for line in prior.split("\n"):
        stripped = line.strip()
        if re.match(r"(?:unset|set\s+-\w*a)\b", stripped):
            return env, f"an `{stripped.split()[0]}` comes before it, so the environment it runs in is not knowable here"
        if re.match(r"export\b", stripped):
            if depth > 0:
                return env, "an `export` sits inside shell control flow"
            for word in stripped.split(None, 1)[1].split() if len(stripped.split(None, 1)) > 1 else []:
                if "=" in word:
                    if not ASSIGNMENT.match(word):
                        return env, f"an assignment form other than the exact NAME=literal ({word[:30]!r}): `+=`, an array or an indexed name"
                    got, why = assignments(word)
                    if why:
                        return env, why
                    env.update(got)
                elif word in shell_vars:
                    env[word] = shell_vars[word]
                else:
                    return env, f"`export {word}` has no literal value here"
        elif depth == 0 and ASSIGNMENT.match(stripped.split()[0] if stripped.split() else "") and len(stripped.split()) == 1:
            got, why = assignments(stripped)
            if why:
                return env, why
            shell_vars.update(got)
        depth += len(OPENERS.findall(stripped)) - len(CLOSERS.findall(stripped)) + stripped.count("{") - stripped.count("}")
    return env, None


def runner_commands(relpath: str, text: str, allow_cd: bool = False) -> list[dict]:
    """Every `playwright test ...` command in a runner file: {file, args, listing_only, unsafe}. `args` are what to hand Playwright to list the same selection."""
    found = []
    if relpath.endswith(".json"):
        try:
            scripts = [v for v in (json.loads(text).get("scripts") or {}).values() if isinstance(v, str)]
        except ValueError:
            return [{"file": relpath, "args": [], "listing_only": False, "unsafe": "the file is not JSON"}]
        for source in scripts:
            for m in re.finditer(r"\bplaywright\s+test\b", source):
                prefix = source[:m.start()]
                env: dict[str, str] = {}
                why = None
                parts = re.split(r"&&|;", prefix)
                for part in parts[:-1]:
                    if part.strip().startswith("export "):
                        got, why = assignments(part.strip()[len("export "):])
                        env.update(got)
                        if why:
                            break
                if not why:
                    got, why = assignments(parts[-1])
                    env.update(got)
                found.append(_command(relpath, command_text(source, m.end()), script_refusal(prefix, allow_cd) or why, env))
        return found
    source = strip_shell_comments(text).replace("\\\n", " ")
    for m in re.finditer(r"\bplaywright\s+test\b", source):
        line_start = source.rfind("\n", 0, m.start()) + 1
        prior, prefix = source[:line_start], source[line_start:m.start()]
        refusal = shell_refusal(prior, prefix, allow_cd)
        env, why = exported(prior)
        if not why:
            got, why = assignments(prefix)
            env.update(got)
        found.append(_command(relpath, command_text(source, m.end()), why or refusal, env))
    return found


REDIRECT = re.compile(r"^(?:\d*|&)(?:>>?|<)(?:&\d+|&-|[^\s<>]\S*)$")          # 2>&1  >file  >>file  &>file  <file  2>/dev/null
REDIRECT_OPERATOR = re.compile(r"^(?:\d*|&)(?:>>?|<)$")                  # > file  (the file is the next word)


def _command(relpath: str, argument_text: str, refusal: str | None, env: dict[str, str] | None = None) -> dict:
    command = {"file": relpath, "args": [], "listing_only": False, "unsafe": refusal, "env": dict(env or {})}
    try:
        tokens = shlex.split(argument_text.rstrip(") "), posix=True)
    except ValueError as exc:
        command["unsafe"] = command["unsafe"] or f"the command cannot be split ({exc})"
        return command
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in ("$@", "$*"):
            pass                                   # the runner's own extra arguments: not part of its default selection
        elif REDIRECT.match(token):
            pass                                   # shell, not Playwright
        elif REDIRECT_OPERATOR.match(token):
            i += 1                                 # `> file`: the next word is the target
        elif token in NARROWING or token.startswith("--only-changed="):
            command["unsafe"] = command["unsafe"] or f"{token.split('=')[0]} narrows the run by git or last-run state that a listing cannot see"
        elif "$" in token or "`" in token:
            command["unsafe"] = command["unsafe"] or f"an argument is built from a shell variable or substitution ({token!r})"
        elif token == "--list":
            command["listing_only"] = True
        elif token in DROP_FLAGS:
            pass
        elif token in DROP_WITH_VALUE:
            i += 1
        elif token.startswith("--reporter="):
            pass
        else:
            command["args"].append(token)
        i += 1
    return command


# ---- the gate ----------------------------------------------------------------------------------------------------------------------------------------


def names(spec: dict, rid: str) -> bool:
    """The requirement id is a whole token of a describe title, the test title or a tag (never of the file path)."""
    pattern = re.compile(r"(?<![A-Za-z0-9._-])" + re.escape(rid) + r"(?![A-Za-z0-9._-])")
    return any(pattern.search(piece) for piece in [*spec["titles"], *spec["tags"]])


def settings(root: Path) -> dict:
    config = root / "qa" / "qa.config.yml"
    values: dict = {}
    if config.is_file():
        import qa_config
        values = qa_config.load_section(config, "e2e_paths")
    chosen: dict = {}
    for key, default in DEFAULTS.items():
        value = str(values[key]) if values.get(key) else default
        if not (root / value).resolve().is_relative_to(root.resolve()):
            raise ValueError(f"e2e_paths.{key} {value!r} must be a path inside the project")
        chosen[key] = value
    cwd = str(values["cwd"]) if values.get("cwd") else ""
    chosen["cwd_set"] = bool(cwd)
    chosen["cwd"] = cwd or str(Path(chosen["config"]).parent)
    if not (root / chosen["cwd"]).resolve().is_relative_to(root.resolve()):
        raise ValueError(f"e2e_paths.cwd {chosen['cwd']!r} must be a path inside the project")
    runners = values.get("runners") or []
    runners = [runners] if isinstance(runners, str) else list(runners)
    for value in runners:
        if not (root / str(value)).resolve().is_relative_to(root.resolve()):
            raise ValueError(f"e2e_paths.runners {value!r} must be a path inside the project")
    chosen["runners"] = [str(v) for v in runners]
    return chosen


def check(root: Path, base: list[str] | None = None, lister: Lister | None = None) -> tuple[int, list[str], list[str]]:
    """(exit code, findings, notes). Notes are the reasons a verdict could not be reached."""
    lister = lister or Lister()
    try:
        conf = settings(root)
        registry, _, _ = cr.paths(root)
    except ValueError as exc:
        return 2, [str(exc)], []
    entries, problems = cr.load(root, registry)
    if problems:
        return 2, problems, []
    by_id = {e["id"]: e for e in entries if isinstance(e.get("id"), str)}
    features = [rid for rid, e in by_id.items() if e.get("feature") is True and e.get("status") != "owner-decision"]
    findings: list[str] = []
    notes: list[str] = []
    baseline_path = root / conf["baseline"]
    base_text = baseline_path.read_text(encoding="utf-8-sig") if baseline_path.is_file() else ""
    listed = cr.baseline_lines(base_text)
    size = cr.header_number(base_text, "size")
    if (listed or size is not None) and size != len(listed):
        findings.append(f"{conf['baseline']}: the header says `# size: {size}` but it holds {len(listed)} line(s); edit the number on purpose, where a reviewer sees it")
    if not features and not listed:
        return (1 if findings else 0), findings, notes
    if features and not conf["runners"]:
        return 2, findings, ["no runner files are declared: list them under `e2e_paths: runners:` in qa/qa.config.yml (a shell script or a package.json that runs `playwright test`)"]
    config_yml = root / "qa" / "qa.config.yml"
    declared = re.search(r"^web_e2e:\s*([A-Za-z][A-Za-z0-9-]*)", config_yml.read_text(encoding="utf-8-sig"), re.M) if config_yml.is_file() else None
    if features and declared and declared.group(1) not in ("playwright", "none"):
        return 2, findings, [f"web_e2e is {declared.group(1)}: only Playwright is read (could not check, never a pass)"]
    commands: list[dict] = []
    for runner in (conf["runners"] if features else []):
        path = root / runner
        if not path.is_file():
            return 2, findings + [f"{runner}: listed under e2e_paths: runners but missing"], notes
        found = runner_commands(runner, path.read_text(encoding="utf-8-sig"), allow_cd=conf["cwd_set"])
        if not found:
            notes.append(f"{runner}: no `playwright test` command found in it")
        commands += found
    cwd = root / conf["cwd"]
    everything, why = lister.list(cwd, []) if features else ([], None)      # no feature, nothing to list
    if everything is None:
        return 2, findings, notes + [f"could not list the tests Playwright finds: {why}"]
    selections: list[list[dict]] = []
    uncertain: list[str] = []
    for command in commands:
        if command["listing_only"]:
            notes.append(f"{command['file']}: a `--list` command only lists tests and runs none, so it is not a runner")
        elif command["unsafe"]:
            uncertain.append(f"{command['file']}: not executed, {command['unsafe']}")
        else:
            specs, why = lister.list(cwd, command["args"], command["env"])
            if specs is None:
                uncertain.append(f"{command['file']}: could not list `{' '.join(command['args'])}`: {why}")
            else:
                selections.append(specs)
    selected_ids: set[str] = set()
    undecided: dict[str, str] = {}
    for rid in features:
        # named by ANY listing: a runner's environment can change which tests Playwright finds (a config that reads it), so the unfiltered listing alone is not the whole set
        named = [s for s in [*everything, *[x for specs in selections for x in specs]] if s["active"] and names(s, rid)]
        if not named:
            if rid not in listed:
                findings.append(f"{rid}: a feature, but no active test names it (an id in a test title, a describe title or a tag): add an end-to-end spec")
            continue
        if any(s["active"] and names(s, rid) for specs in selections for s in specs):
            selected_ids.add(rid)
        elif uncertain:
            undecided[rid] = "; ".join(uncertain)
        elif rid not in listed:
            where = ", ".join(sorted({s["file"] for s in named}))
            findings.append(f"{rid}: named by {len(named)} test(s) in {where}, but no runner selects any of them (Playwright lists none of them for any runner command)")
    for rid in listed:
        entry = by_id.get(rid)
        if entry is None:
            findings.append(f"{conf['baseline']}: {rid} is not in the registry (the list only shrinks: drop it)")
        elif entry.get("feature") is not True or entry.get("status") == "owner-decision":
            findings.append(f"{conf['baseline']}: {rid} is not a feature that needs an end-to-end path (drop it)")
        elif rid in selected_ids:
            findings.append(f"{conf['baseline']}: {rid} is now selected by a runner; drop it from the baseline (the list only shrinks)")
    if base is not None:
        for rid in listed:
            if rid not in base:
                findings.append(f"{conf['baseline']}: {rid} is not in the base branch's baseline; a feature without an end-to-end path cannot be added to it (add the spec)")
    more = [f"{rid}: could not decide ({why})" for rid, why in sorted(undecided.items())]
    if findings:
        return 1, findings, notes + more
    if undecided:
        return 2, findings, notes + more
    return 0, findings, notes


# ---- selftest ---------------------------------------------------------------------------------------------------------------------------------------


def spec(*titles: str, tags: tuple[str, ...] = (), active: bool = True, file: str = "e2e/auth.spec.ts") -> dict:
    return {"titles": list(titles), "tags": list(tags), "file": file, "active": active}


class FakeLister(Lister):
    """Answers a listing from a table keyed by the argument list, and records every call: the plumbing is tested, Playwright's selection is not re-implemented."""

    def __init__(self, table: dict[tuple, list[dict] | str]):
        self.table, self.calls = table, []

    def list(self, cwd: Path, args: list[str], env: dict[str, str] | None = None):
        """The table is keyed by the argument list, or by (arguments, sorted environment items) for a listing that depends on the runner's environment."""
        self.calls.append((cwd.name, tuple(args), tuple(sorted((env or {}).items()))))
        key = (tuple(args), tuple(sorted((env or {}).items())))
        answer = self.table[key] if key in self.table else self.table.get(tuple(args), f"no canned listing for {tuple(args)} {sorted((env or {}).items())}")
        return (None, answer) if isinstance(answer, str) else (answer, None)


def stub_npx(directory: Path, body: str) -> None:
    (directory / "npx").write_text("#!/bin/sh\n" + body + "\n")
    (directory / "npx").chmod(0o755)


def selftest(match: str | None = None, real: str | None = None) -> int:
    """`match` runs only the rows whose label contains it (the mutation harness runs each mutant on the one row it names)."""
    failures: list[str] = []

    def entry(rid: str, extra: str = "  feature: true\n", status: str = "done") -> str:
        return f'- id: "{rid}"\n  area: "A"\n  requirement: "text of {rid}"\n  status: "{status}"\n{extra}'

    def project(*entries: str) -> str:
        return f"# rows: {len(entries)}\n" + "".join(entries)

    CONFIG = "e2e_paths:\n  runners:\n    - bin/e2e\n"
    RUN = '#!/bin/sh\nexec npx playwright test --project=chromium --grep "@REQ-001|@smoke" --workers=1 "$@"\n'
    ARGS = ("--project=chromium", "--grep", "@REQ-001|@smoke", "--workers=1")
    NAMED = spec("@REQ-001 signs in", tags=("REQ-001",))
    OTHER = spec("something else")

    def row(label: str, files: dict, table: dict, want_code: int, want: str | None, base: list[str] | None = None) -> FakeLister | None:
        if match and match not in label:
            return None
        files = {"qa/requirements.yml": project(entry("REQ-001")), "qa/test-cases.csv": "Test ID,Status,Source\n", "qa/qa.config.yml": CONFIG, "bin/e2e": RUN,
                 "qa/playwright.config.ts": "export default {};\n", **files}
        lister = FakeLister(table)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, text in files.items():
                if text is None:
                    continue
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(text, encoding="utf-8")
            code, found, notes = check(root, base, lister)
        joined = "\n".join([*found, *notes])
        if code != want_code or (want is None and found) or (want is not None and want not in joined):
            failures.append(f"{label}: wanted exit {want_code} {want!r}, got exit {code}: {joined[:260]!r}")
        return lister

    ALL = {(): [NAMED, OTHER]}
    selected = {**ALL, ARGS: [NAMED]}
    row("a feature that a runner's listing selects is clean", {}, selected, 0, None)
    row("the @real-signin shape: named in the unfiltered listing, left out of every runner's", {}, {**ALL, ARGS: [OTHER]}, 1, "no runner selects")
    row("a feature that no test names is a finding", {}, {(): [OTHER], ARGS: [OTHER]}, 1, "no active test names it")
    row("a test Playwright marks skipped names nothing", {}, {(): [spec("@REQ-001 signs in", active=False)], ARGS: [OTHER]}, 1, "no active test names it")
    row("a skipped test in a runner's listing does not select the feature", {}, {(): [NAMED], ARGS: [spec("@REQ-001 signs in", active=False)]}, 1, "no runner selects")
    row("a tag names the requirement", {}, {(): [spec("signs in", tags=("REQ-001",))], ARGS: [spec("signs in", tags=("REQ-001",))]}, 0, None)
    row("a describe title names the requirement", {}, {(): [spec("@REQ-001 sign in", "works")], ARGS: [spec("@REQ-001 sign in", "works")]}, 0, None)
    row("an id inside a longer token is not named (REQ-0011 is not REQ-001)", {}, {(): [spec("@REQ-0011 other")], ARGS: [spec("@REQ-0011 other")]}, 1, "no active test names it")
    row("an id only in the file path is not named", {}, {(): [spec("works", file="e2e/REQ-001/login.spec.ts")], ARGS: [OTHER]}, 1, "no active test names it")
    row("the listing arguments are the runner's own, minus --list, --reporter and the runner's extra arguments",
        {"bin/e2e": '#!/bin/sh\nnpx playwright test --reporter=list --grep "@REQ-001" --list-x "$@" --reporter html\n'},
        {(): [NAMED], ("--grep", "@REQ-001", "--list-x"): [NAMED]}, 0, None)
    row("an attached short value is forwarded as written, never re-parsed", {"bin/e2e": "#!/bin/sh\nnpx playwright test -g@qa-image\n"}, {(): [NAMED], ("-g@qa-image",): [OTHER]}, 1,
        "no runner selects")
    row("a --config argument is forwarded for Playwright to read", {"bin/e2e": "#!/bin/sh\nnpx playwright test --config=qa/ci.config.ts\n"}, {(): [NAMED], ("--config=qa/ci.config.ts",): [OTHER]}, 1,
        "no runner selects")
    row("two positional filters are forwarded as written", {"bin/e2e": "#!/bin/sh\nnpx playwright test auth.spec.ts other.spec.ts\n"}, {(): [NAMED], ("auth.spec.ts", "other.spec.ts"): [NAMED]}, 0, None)
    row("a runner that only lists is not a runner", {"bin/e2e": '#!/bin/sh\nnpx playwright test --list --grep "@REQ-001"\n'}, {(): [NAMED]}, 1, "no runner selects")
    row("a comment that says playwright test is not a runner", {"bin/e2e": '#!/bin/sh\n# npx playwright test\nnpx playwright test --grep "@qa-image"   # not @REQ-001\n'},
        {(): [NAMED], ("--grep", "@qa-image"): [OTHER]}, 1, "no runner selects")
    row("a package.json script is a runner", {"qa/package.json": json.dumps({"scripts": {"smoke": "playwright test --grep @qa-image"}}), "qa/qa.config.yml": "e2e_paths:\n  runners:\n    - qa/package.json\n"},
        {(): [NAMED], ("--grep", "@qa-image"): [OTHER]}, 1, "no runner selects")
    row("a package.json script after && is fine", {"qa/package.json": json.dumps({"scripts": {"e2e": "npm run build && playwright test --grep @REQ-001"}}), "qa/qa.config.yml": "e2e_paths:\n  runners:\n    - qa/package.json\n"},
        {(): [NAMED], ("--grep", "@REQ-001"): [NAMED]}, 0, None)
    row("a second runner that selects the feature is enough", {"bin/e2e": '#!/bin/sh\nnpx playwright test --grep "@qa-image"\nnpx playwright test --grep @REQ-001\n'},
        {(): [NAMED], ("--grep", "@qa-image"): [OTHER], ("--grep", "@REQ-001"): [NAMED]}, 0, None)
    # what is refused, with the reason, and never executed
    for label, script, reason in (
        ("a grep built from a shell variable is not executed", '#!/bin/sh\nnpx playwright test --grep "$TAGS"\n', "built from a shell variable"),
        ("a command substitution in an argument is not executed", '#!/bin/sh\nnpx playwright test --grep "$(cat tags)"\n', "built from a shell variable or substitution"),
        ("a command inside an if is not executed", '#!/bin/sh\nif false; then\n  npx playwright test --grep @REQ-001\nfi\n', "shell control flow"),
        ("a command in a function body is not executed", '#!/bin/sh\nrun() {\n  npx playwright test --grep @REQ-001\n}\n', "shell control flow"),
        ("a command after a heredoc is not executed", '#!/bin/sh\ncat <<EOF\nx\nEOF\nnpx playwright test --grep @REQ-001\n', "a heredoc comes before it"),
        ("a command after an exit is not executed", '#!/bin/sh\nexit 0\nnpx playwright test --grep @REQ-001\n', "an `exit` or `return` comes before it"),
        ("a command guarded by && on its line is not executed", '#!/bin/sh\n[ -n "$CI" ] && npx playwright test --grep @REQ-001\n', "something else runs on the same line"),
        ("a command after || on its line is not executed", '#!/bin/sh\ntrue || npx playwright test --grep @REQ-001\n', "something else runs on the same line"),
        ("a command piped into is not executed", '#!/bin/sh\necho x | npx playwright test --grep @REQ-001\n', "something else runs on the same line"),
        ("a `. file` before the command is refused (an env file can export what the config reads)", '#!/bin/sh\n. qa/image.env\nnpx playwright test --grep @REQ-001\n', "a `source` or `.` comes before it"),
        ("a `source file` before the command is refused", '#!/bin/sh\nsource qa/image.env\nnpx playwright test --grep @REQ-001\n', "a `source` or `.` comes before it"),
        ("a source inside a function before the command is refused", '#!/bin/sh\nload() {\n  source qa/image.env\n}\nnpx playwright test --grep @REQ-001\n', "a `source` or `.` comes before it"),
        ("a command after a cd is not executed unless cwd is set", '#!/bin/sh\ncd somewhere\nnpx playwright test --grep @REQ-001\n', "a `cd` comes before it"),
    ):
        lister = row(label, {"bin/e2e": script}, {(): [NAMED]}, 2, reason)
        if lister is not None and any(call[1] for call in lister.calls):
            failures.append(f"{label}: Playwright was run for a command that must not be executed: {lister.calls}")
    row("a command after a cd is executed when cwd is set", {"bin/e2e": "#!/bin/sh\ncd somewhere\nnpx playwright test --grep @REQ-001\n", "qa/qa.config.yml": "e2e_paths:\n  cwd: qa/e2e\n  runners:\n    - bin/e2e\n"},
        {(): [NAMED], ("--grep", "@REQ-001"): [NAMED]}, 0, None)
    row("a package.json script that sources an env file before the command is refused", {"qa/package.json": json.dumps({"scripts": {"e2e": ". qa/image.env && playwright test --grep @REQ-001"}}),
        "qa/qa.config.yml": "e2e_paths:\n  runners:\n    - qa/package.json\n"}, {(): [NAMED]}, 2, "a `source` or `.` comes before it")
    row("a ./script before the command is not a source and does not refuse", {"bin/e2e": "#!/bin/sh\n./setup.sh\nnpx playwright test --grep @REQ-001\n"}, {(): [NAMED], ("--grep", "@REQ-001"): [NAMED]}, 0, None)
    row("a package.json script with || before it is not executed", {"qa/package.json": json.dumps({"scripts": {"e2e": "a || playwright test --grep @REQ-001"}}), "qa/qa.config.yml": "e2e_paths:\n  runners:\n    - qa/package.json\n"},
        {(): [NAMED]}, 2, "a `||` or a pipe comes before it")
    row("a refused command does not hide a runner that selects the feature", {"bin/e2e": '#!/bin/sh\nnpx playwright test --grep "$X"\nnpx playwright test --grep @REQ-001\n'},
        {(): [NAMED], ("--grep", "@REQ-001"): [NAMED]}, 0, None)
    row("a finding is still reported when another feature cannot be decided", {"qa/requirements.yml": project(entry("REQ-001"), entry("REQ-002")), "bin/e2e": '#!/bin/sh\nnpx playwright test --grep "$X"\n'},
        {(): [NAMED]}, 1, "REQ-002: a feature, but no active test names it")
    row("a listing that fails for a runner is exit 2, never a pass", {}, {(): [NAMED], ARGS: "boom"}, 2, "could not list")
    row("the unfiltered listing failing is exit 2, never a pass", {}, {(): "no JSON"}, 2, "could not list the tests Playwright finds")
    lister = row("the cwd of a listing is the config's directory", {}, selected, 0, None)
    if lister is not None and {call[0] for call in lister.calls} != {"qa"}:
        failures.append(f"the cwd of a listing is the config's directory: {lister.calls}")
    row("no runner files declared is exit 2, not a pass", {"qa/qa.config.yml": ""}, {}, 2, "no runner files are declared")
    row("a web_e2e other than playwright is exit 2, not a pass", {"qa/qa.config.yml": "web_e2e: cypress-cucumber\ne2e_paths:\n  runners:\n    - bin/e2e\n"}, {}, 2, "only Playwright is read")
    row("a runner file that is missing is exit 2", {"qa/qa.config.yml": "e2e_paths:\n  runners:\n    - bin/gone\n"}, {}, 2, "listed under e2e_paths: runners but missing")
    row("a runner path outside the project is exit 2", {"qa/qa.config.yml": "e2e_paths:\n  runners:\n    - ../outside\n"}, {}, 2, "inside the project")
    row("a registry with no features lists nothing and needs no runners", {"qa/requirements.yml": project(entry("REQ-001", extra="")), "qa/qa.config.yml": ""}, {}, 0, None)
    row("a runner file with no playwright command says so", {"bin/e2e": "#!/bin/sh\necho hi\n"}, {(): [NAMED]}, 1, "no `playwright test` command found")
    # the runner's environment: a config can read it, so a literal assignment must reach the listing (and a value that is not literal must be refused)
    ENV = (("QA_TARGET", "image"),)
    GREP = ("--grep", "@REQ-001")
    env_table = {(): [NAMED], (GREP, ENV): [NAMED], GREP: [OTHER]}      # without the environment the listing leaves the feature out: only an applied environment selects it
    for label, script, files in (
        ("a NAME=value prefix reaches the listing's environment", '#!/bin/sh\nQA_TARGET=image npx playwright test --grep @REQ-001\n', {}),
        ("an earlier export reaches the listing's environment", '#!/bin/sh\nexport QA_TARGET=image\nnpx playwright test --grep @REQ-001\n', {}),
        ("an env NAME=value prefix reaches the listing's environment", '#!/bin/sh\nenv QA_TARGET=image npx playwright test --grep @REQ-001\n', {}),
        ("an exported shell variable reaches the listing's environment", '#!/bin/sh\nQA_TARGET=image\nexport QA_TARGET\nnpx playwright test --grep @REQ-001\n', {}),
        ("a quoted literal value reaches the listing's environment", '#!/bin/sh\nQA_TARGET="image" npx playwright test --grep @REQ-001\n', {}),
        ("a cross-env prefix in a package.json script reaches the listing's environment", None,
         {"qa/package.json": json.dumps({"scripts": {"e2e": "cross-env QA_TARGET=image playwright test --grep @REQ-001"}}), "qa/qa.config.yml": "e2e_paths:\n  runners:\n    - qa/package.json\n"}),
        ("an export before && in a package.json script reaches the listing's environment", None,
         {"qa/package.json": json.dumps({"scripts": {"e2e": "export QA_TARGET=image && playwright test --grep @REQ-001"}}), "qa/qa.config.yml": "e2e_paths:\n  runners:\n    - qa/package.json\n"}),
    ):
        lister = row(label, {"bin/e2e": script, **files} if script else files, env_table, 0, None)
        if lister is not None and not any(call[2] == ENV for call in lister.calls):
            failures.append(f"{label}: no listing carried the environment: {lister.calls}")
    for label, script, reason in (
        ("an assignment whose value is a variable is refused", '#!/bin/sh\nQA_TARGET=$X npx playwright test --grep @REQ-001\n', "not a plain literal"),
        ("an assignment whose value is a substitution is refused", '#!/bin/sh\nexport QA_TARGET=$(cat target)\nnpx playwright test --grep @REQ-001\n', "not a plain literal"),
        ("an assignment whose value is a glob is refused", '#!/bin/sh\nQA_TARGET=im* npx playwright test --grep @REQ-001\n', "not a plain literal"),
        ("an assignment whose value is a backtick substitution is refused", '#!/bin/sh\nexport QA_TARGET=`cat target`\nnpx playwright test --grep @REQ-001\n', "not a plain literal"),
        ("an export inside an if is refused", '#!/bin/sh\nif [ -n "$CI" ]; then\n  export QA_TARGET=image\nfi\nnpx playwright test --grep @REQ-001\n', "inside shell control flow"),
        ("an unset before the command is refused", '#!/bin/sh\nunset QA_TARGET\nnpx playwright test --grep @REQ-001\n', "comes before it, so the environment"),
        ("set -a before the command is refused", '#!/bin/sh\nset -a\nnpx playwright test --grep @REQ-001\n', "comes before it, so the environment"),
        ("an export of a variable with no literal value is refused", '#!/bin/sh\nexport QA_TARGET\nnpx playwright test --grep @REQ-001\n', "has no literal value"),
        ("--only-changed narrows by state a listing cannot see and is refused", '#!/bin/sh\nnpx playwright test --only-changed --grep @REQ-001\n', "narrows the run by git or last-run state"),
        ("--only-changed=REF is refused too", '#!/bin/sh\nnpx playwright test --only-changed=origin/main --grep @REQ-001\n', "narrows the run by git or last-run state"),
        ("--last-failed narrows by state a listing cannot see and is refused", '#!/bin/sh\nnpx playwright test --last-failed --grep @REQ-001\n', "narrows the run by git or last-run state"),
    ):
        lister = row(label, {"bin/e2e": script}, {(): [NAMED]}, 2, reason)
        if lister is not None and any(call[1] for call in lister.calls):
            failures.append(f"{label}: Playwright was run for a command that must not be executed: {lister.calls}")
    for label, tail in (("2>&1", "2>&1"), ("> out.log", "> out.log"), (">> out.log", ">> out.log"), ("&>log", "&>log"), ("< in.txt", "< in.txt"), ("2>/dev/null", "2>/dev/null")):
        lister = row(f"a redirection ({label}) is shell, not a Playwright argument", {"bin/e2e": f"#!/bin/sh\nnpx playwright test --grep @REQ-001 {tail}\n"}, {(): [NAMED], GREP: [NAMED]}, 0, None)
        if lister is not None and not any(call[1] == GREP for call in lister.calls):
            failures.append(f"a redirection ({label}) is shell, not a Playwright argument: the listing arguments were {[c[1] for c in lister.calls]}")
    row("a feature named only by a runner's own listing (its environment changes what Playwright finds) is named, not missing",
        {"bin/e2e": "#!/bin/sh\nQA_TARGET=image npx playwright test --grep @REQ-001\n"}, {(): [OTHER], (GREP, ENV): [NAMED]}, 0, None)
    # the statements before the command: an allowlist (understood, or a child process); every other builtin or keyword runs in the runner's own shell and is refused
    for label, script, reason in (
        ('an `eval "export ..."` before the command is refused', '#!/bin/sh\neval "export QA_TARGET=image"\nnpx playwright test --grep @REQ-001\n', "`eval` is a shell builtin or keyword"),
        ("a `declare -x` before the command is refused", "#!/bin/bash\ndeclare -x QA_TARGET=image\nnpx playwright test --grep @REQ-001\n", "`declare` is a shell builtin or keyword"),
        ("a `typeset -x` before the command is refused", "#!/bin/bash\ntypeset -x QA_TARGET=image\nnpx playwright test --grep @REQ-001\n", "`typeset` is a shell builtin or keyword"),
        ("a `command export` before the command is refused", "#!/bin/sh\ncommand export QA_TARGET=image\nnpx playwright test --grep @REQ-001\n", "`command` is a shell builtin or keyword"),
        ("a `builtin export` before the command is refused", "#!/bin/bash\nbuiltin export QA_TARGET=image\nnpx playwright test --grep @REQ-001\n", "`builtin` is a shell builtin or keyword"),
        ("a function that sources an env file, then called, is refused", "#!/bin/sh\nsetup() { . qa/image.env; }\nsetup\nnpx playwright test --grep @REQ-001\n", "a statement before it cannot be accounted for"),
        ("a `printf` before the command is refused", "#!/bin/sh\nprintf x\nnpx playwright test --grep @REQ-001\n", "`printf` is a shell builtin or keyword"),
        ("an `echo` before the command is refused (a builtin)", "#!/bin/sh\necho hi\nnpx playwright test --grep @REQ-001\n", "`echo` is a shell builtin or keyword"),
        ("a `read` before the command is refused", "#!/bin/sh\nread x\nnpx playwright test --grep @REQ-001\n", "`read` is a shell builtin or keyword"),
        ("a `local` before the command is refused", "#!/bin/sh\nlocal x=1\nnpx playwright test --grep @REQ-001\n", "`local` is a shell builtin or keyword"),
        ("an `alias` before the command is refused", "#!/bin/sh\nalias npx=true\nnpx playwright test --grep @REQ-001\n", "`alias` is a shell builtin or keyword"),
        ("an exported `NAME+=value` before the command is refused", "#!/bin/bash\nexport QA_TARGET+=image\nnpx playwright test --grep @REQ-001\n", "an assignment form other than the exact NAME=literal"),
        ("a bare `NAME+=value` before the command is refused", "#!/bin/bash\nQA_TARGET+=image\nnpx playwright test --grep @REQ-001\n", "an assignment form other than the exact NAME=literal"),
        ("an array assignment before the command is refused", "#!/bin/bash\nTARGETS=(image dev)\nnpx playwright test --grep @REQ-001\n", "is not a plain literal"),
        ("an indexed assignment before the command is refused", "#!/bin/bash\nTARGETS[0]=image\nnpx playwright test --grep @REQ-001\n", "an assignment form other than the exact NAME=literal"),
        ("an exported array element before the command is refused", "#!/bin/bash\nexport TARGETS[0]=image\nnpx playwright test --grep @REQ-001\n", "an assignment form other than the exact NAME=literal"),
        ("a tilde in an assignment value is not a literal (it expands)", "#!/bin/sh\nQA_HOME=~/qa\nnpx playwright test --grep @REQ-001\n", "is not a plain literal"),
        ("a function defined with a subshell body is refused", "#!/bin/sh\nsetup() ( docker compose up -d )\nsetup\nnpx playwright test --grep @REQ-001\n", "a function definition"),
        ("a builtin after a NAME=value prefix is refused", "#!/bin/sh\nFOO=bar eval x\nnpx playwright test --grep @REQ-001\n", "`eval` is a shell builtin or keyword"),
        ("a non-literal NAME=value prefix before a child process is refused", "#!/bin/sh\nFOO=$X docker run app\nnpx playwright test --grep @REQ-001\n", "is not a plain literal"),
        ("a group `{ ...; }` before the command is refused", "#!/bin/sh\n{ true; }\nnpx playwright test --grep @REQ-001\n", "a group or a function body"),
        ("a subshell `( ... )` before the command is refused", "#!/bin/sh\n(true)\nnpx playwright test --grep @REQ-001\n", "a group or a function body"),
        ("a chain with a builtin part before the command is refused", "#!/bin/sh\ndocker compose up -d && eval x\nnpx playwright test --grep @REQ-001\n", "`eval` is a shell builtin or keyword"),
        ("a pipe into a builtin before the command is refused", "#!/bin/sh\ncat tags | read first\nnpx playwright test --grep @REQ-001\n", "`read` is a shell builtin or keyword"),
        ("a command substitution anywhere before the command is refused", "#!/bin/sh\ndocker run $(cat image)\nnpx playwright test --grep @REQ-001\n", "a command substitution comes before it"),
        ("a backtick substitution before the command is refused", "#!/bin/sh\ndocker run `cat image`\nnpx playwright test --grep @REQ-001\n", "a command substitution comes before it"),
        ("`set +e` before the command is refused", "#!/bin/sh\nset +e\nnpx playwright test --grep @REQ-001\n", "is not one of -e, -u, -o pipefail"),
        ("`set -x` before the command is refused", "#!/bin/sh\nset -x\nnpx playwright test --grep @REQ-001\n", "is not one of -e, -u, -o pipefail"),
        ("`set -o noglob` before the command is refused", "#!/bin/sh\nset -o noglob\nnpx playwright test --grep @REQ-001\n", "is not one of -e, -u, -o pipefail"),
        ("a `cd` to a variable is refused even when cwd is set", "#!/bin/sh\ncd $DIR\nnpx playwright test --grep @REQ-001\n", "a `cd` that is not to a literal directory"),
    ):
        lister = row(label, {"bin/e2e": script, "qa/qa.config.yml": "e2e_paths:\n  cwd: qa\n  runners:\n    - bin/e2e\n" if "$DIR" in script else CONFIG}, {(): [NAMED]}, 2, reason)
        if lister is not None and any(call[1] for call in lister.calls):
            failures.append(f"{label}: Playwright was run for a command that must not be executed: {lister.calls}")
    row("a package.json script with an eval before the command is refused", {"qa/package.json": json.dumps({"scripts": {"e2e": "eval x && playwright test --grep @REQ-001"}}),
        "qa/qa.config.yml": "e2e_paths:\n  runners:\n    - qa/package.json\n"}, {(): [NAMED]}, 2, "`eval` is a shell builtin or keyword")
    for label, script in (
        ("child processes before the command are allowed (docker, curl, ./setup.sh)", "#!/bin/sh\ndocker compose up -d\ncurl -sf http://localhost:3000/up\n./setup.sh\nnpx playwright test --grep @REQ-001\n"),
        ("`set -euo pipefail` and literal assignments and exports before the command are understood", "#!/bin/sh\nset -euo pipefail\nset -e\nPORT=3000\nexport PORT\nQA_TARGET=image\nexport QA_TARGET\ndocker compose up -d\nnpx playwright test --grep @REQ-001\n"),
        ("a child process with its own NAME=value prefix and redirections is allowed", "#!/bin/sh\nFOO=bar docker run --rm app 2>&1\nnpx playwright test --grep @REQ-001\n"),
        ("a child process in a pipeline is allowed", "#!/bin/sh\ndocker logs app | tail -n 5\nnpx playwright test --grep @REQ-001\n"),
        ("a chain of child processes is allowed", "#!/bin/sh\ndocker compose up -d && curl -sf http://localhost:3000/up; ./setup.sh\nnpx playwright test --grep @REQ-001\n"),
    ):
        lister = row(label, {"bin/e2e": script}, {(): [NAMED], (GREP, ENV): [NAMED], GREP: [NAMED]}, 0, None)
    row("a literal cd is allowed when cwd is set", {"bin/e2e": "#!/bin/sh\ncd qa\nnpx playwright test --grep @REQ-001\n", "qa/qa.config.yml": "e2e_paths:\n  cwd: qa\n  runners:\n    - bin/e2e\n"},
        {(): [NAMED], GREP: [NAMED]}, 0, None)
    row("a child process before a NAME=value prefix: the environment is still applied", {"bin/e2e": "#!/bin/sh\ndocker compose up -d\nQA_TARGET=image npx playwright test --grep @REQ-001\n"},
        {(): [NAMED], (GREP, ENV): [NAMED], GREP: [OTHER]}, 0, None)
    if not match or "the pinned shell words cover the live shell" in match:
        try:
            live = subprocess.run(["bash", "-c", "compgen -b; compgen -k"], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL).stdout.split()
        except (OSError, subprocess.SubprocessError):
            live = []
        missing = sorted(set(live) - SHELL_WORDS)
        if missing:
            failures.append(f"the pinned shell words cover the live shell: this bash has builtins or keywords the check does not know: {missing}")
    # the baseline ratchet
    base_files = {"qa/e2e-unselected-baseline.txt": "# size: 1\nREQ-001\n"}
    row("a baselined feature that is named nowhere is clean", base_files, {(): [OTHER], ARGS: [OTHER]}, 0, None)
    row("a baseline line for a feature that is now selected is a finding", base_files, selected, 1, "now selected by a runner")
    row("a baseline line for a non-feature is a finding", {"qa/requirements.yml": project(entry("REQ-001", extra="")), **base_files}, {}, 1, "not a feature that needs an end-to-end path")
    row("a baseline line for an unknown requirement is a finding", {"qa/e2e-unselected-baseline.txt": "# size: 1\nREQ-404\n"}, selected, 1, "not in the registry")
    row("a baseline whose size header is wrong is a finding", {"qa/e2e-unselected-baseline.txt": "# size: 4\nREQ-001\n"}, {(): [OTHER], ARGS: [OTHER]}, 1, "header says `# size: 4`")
    row("--base: a baseline line not in the base's baseline is refused", base_files, {(): [OTHER], ARGS: [OTHER]}, 1, "not in the base branch's baseline", base=[])
    row("a requirement that is not a feature needs no spec", {"qa/requirements.yml": project(entry("REQ-001", extra=""))}, {(): [OTHER]}, 0, None)
    row("an owner-decision feature needs no spec", {"qa/requirements.yml": project(entry("REQ-001", status="owner-decision"))}, {(): [OTHER]}, 0, None)

    # the real Lister, against stub executables: what Playwright's output and failures turn into
    def real_lister(label: str, body: str, want_specs: bool, want: str | None) -> None:
        if match and match not in label:
            return
        with tempfile.TemporaryDirectory() as td:
            stub_npx(Path(td), body)
            old = os.environ["PATH"]
            os.environ["PATH"] = td + os.pathsep + old
            try:
                specs, why = Lister().list(Path(td), ["--grep", "x"])
            finally:
                os.environ["PATH"] = old
        if (specs is not None) != want_specs or (want is not None and want not in (why or "")):
            failures.append(f"{label}: wanted specs={want_specs} {want!r}, got {specs!r} {why!r}")

    if not match or "the Lister applies the runner's environment" in match:
        body = ("if [ \"$QA_TARGET\" = image ]; then echo '{\"errors\":[],\"suites\":[{\"title\":\"a.spec.ts\",\"file\":\"a.spec.ts\",\"specs\":[{\"title\":\"t\",\"tags\":[],"
                "\"file\":\"a.spec.ts\",\"tests\":[{\"expectedStatus\":\"passed\"}]}]}]}'; else echo '{\"errors\":[],\"suites\":[]}'; fi")
        with tempfile.TemporaryDirectory() as td:
            stub_npx(Path(td), body)
            old = os.environ["PATH"]
            os.environ["PATH"] = td + os.pathsep + old
            os.environ.pop("QA_TARGET", None)
            try:
                with_env, _ = Lister().list(Path(td), [], {"QA_TARGET": "image"})
                without, _ = Lister().list(Path(td), [], None)
            finally:
                os.environ["PATH"] = old
        if not with_env or without:
            failures.append(f"the Lister applies the runner's environment to the subprocess: with {with_env!r}, without {without!r}")
    if not match or "no npx on PATH" in match:
        with tempfile.TemporaryDirectory() as td:
            old = os.environ["PATH"]
            os.environ["PATH"] = td
            try:
                specs, why = Lister().list(Path(td), [])
            finally:
                os.environ["PATH"] = old
        if specs is not None or "`npx` is not installed" not in (why or ""):
            failures.append(f"no npx on PATH is a reason, not a pass: got {specs!r} {why!r}")
    DOC = {"config": {}, "suites": [{"title": "auth.spec.ts", "file": "auth.spec.ts", "specs": [{"title": "@REQ-1 a", "tags": ["REQ-1"], "file": "auth.spec.ts",
           "tests": [{"projectName": "c", "expectedStatus": "passed"}]}], "suites": [{"title": "grp", "specs": [{"title": "b", "tags": [], "file": "auth.spec.ts",
           "tests": [{"projectName": "c", "expectedStatus": "skipped"}]}]}]}], "errors": []}
    real_lister("a real listing is flattened: the file suite is not a describe, a nested describe is, a skipped test is inactive", f"cat <<'JSON'\n{json.dumps(DOC)}\nJSON", True, None)
    real_lister("npx missing is a reason, not a pass", "exit 127", False, "printed no JSON listing")
    real_lister("output that is not JSON is a reason, not a pass", "echo not json; exit 1", False, "printed no JSON listing")
    real_lister("a JSON document with errors is a reason, not a pass", "echo '{\"errors\":[{\"message\":\"bad config\"}],\"suites\":[]}'; exit 1", False, "reported errors")
    real_lister("a listing that matches nothing (error No tests found, exit 1) is an empty listing, not a failure",
                "echo '{\"errors\":[{\"message\":\"Error: No tests found\"}],\"suites\":[]}'; exit 1", True, None)
    real_lister("No tests found next to a real error is still an error", "echo '{\"errors\":[{\"message\":\"Error: No tests found\"},{\"message\":\"bad config\"}],\"suites\":[]}'; exit 1", False,
                "reported errors")
    if not match or "a real listing is flattened" in match:
        got = flatten(DOC)
        want = [{"titles": ["@REQ-1 a"], "tags": ["REQ-1"], "file": "auth.spec.ts", "active": True}, {"titles": ["grp", "b"], "tags": [], "file": "auth.spec.ts", "active": False}]
        if got != want:
            failures.append(f"a real listing is flattened: got {got!r}")
    if real:
        failures += real_battery(Path(real))
    if failures:
        print("check_e2e_paths selftest FAILED --\n" + "\n".join(f"  - {f}" for f in failures))
        return 1
    print("check_e2e_paths selftest: ok (0 failure(s))" + (f"; the real-Playwright battery ran against {real}" if real else ""))
    return 0


def real_battery(modules: Path) -> list[str]:
    """0d's attack battery (#1864 review) against a REAL Playwright: `modules` is a directory that holds node_modules with `playwright` (and `@playwright/test`)."""
    failures: list[str] = []
    entry = lambda rid: f'- id: "{rid}"\n  area: "A"\n  requirement: "t"\n  status: "done"\n  feature: true\n'  # noqa: E731
    SPEC = 'import { test } from "@playwright/test";\ntest("@REQ-001 signs in", async ({ page }) => {});\n'
    BASE = {"qa/requirements.yml": "# rows: 1\n" + entry("REQ-001"), "qa/test-cases.csv": "Test ID,Status,Source\n", "qa/qa.config.yml": "e2e_paths:\n  runners:\n    - bin/e2e\n",
            "bin/e2e": '#!/bin/sh\nnpx playwright test --grep "@REQ-001"\n', "qa/e2e/auth.spec.ts": SPEC, "qa/playwright.config.ts": "export default { testDir: './e2e' };\n"}
    sh = lambda c: "#!/bin/sh\n" + c + "\n"  # noqa: E731
    ENVCONFIG = "export default { testDir: './e2e', grep: process.env.QA_TARGET === 'image' ? /@qa-image/ : undefined };\n"
    battery = [
        ("CLI --grep-invert is case-insensitive: @req-001 excludes the @REQ-001 test", 1, {"bin/e2e": sh('npx playwright test --grep-invert "@req-001"')}),
        ("CLI --grep is case-insensitive: @req-001 selects the @REQ-001 test", 0, {"bin/e2e": sh('npx playwright test --grep "@req-001"')}),
        ("two positional files are OR'd", 0, {"bin/e2e": sh("npx playwright test auth.spec.ts other.spec.ts")}),
        ("-g@qa-image (attached value)", 1, {"bin/e2e": sh("npx playwright test -g@qa-image")}),
        ("--config with a grepInvert", 1, {"bin/e2e": sh("npx playwright test --config=ci.config.ts"), "qa/ci.config.ts": "export default { testDir: './e2e', grepInvert: /@REQ-001/ };\n"}),
        ("the only config is playwright.config.js with a grepInvert", 1, {"qa/playwright.config.ts": None, "qa/playwright.config.js": "module.exports = { testDir: './e2e', grepInvert: /@REQ-001/ };\n"}),
        ("config testDir points elsewhere: the spec is never loaded", 1, {"qa/playwright.config.ts": "export default { testDir: './elsewhere' };\n"}),
        ("--list only runs nothing", 1, {"bin/e2e": sh('npx playwright test --list --grep "@REQ-001"')}),
        ("a command after an unconditional exit is refused, not executed: exit 2", 2, {"bin/e2e": sh('npx playwright test --grep "@qa-image"\nexit 0\nnpx playwright test --grep "@REQ-001"')}),
        ("a command in a branch that is never taken is refused, not executed: exit 2", 2, {"bin/e2e": sh('npx playwright test --grep "@qa-image"\nif false; then\n  npx playwright test --grep "@REQ-001"\nfi')}),
        ("a command inside a heredoc is refused, not executed: exit 2", 2, {"bin/e2e": sh('npx playwright test --grep "@qa-image"\ncat <<EOF\nnpx playwright test --grep "@REQ-001"\nEOF')}),
        ("control: a grep that leaves it out", 1, {"bin/e2e": sh('npx playwright test --grep "@qa-image"')}),
        ("control: a grep from a shell variable is exit 2", 2, {"bin/e2e": sh('npx playwright test --grep "$TAGS"')}),
        ("control: a skipped test names nothing", 1, {"qa/e2e/auth.spec.ts": 'import { test } from "@playwright/test";\ntest.skip("@REQ-001 signs in", async () => {});\n'}),
        ("env-dependent config, runner QA_TARGET=image prefix: the real run greps @qa-image, so the spec is NOT selected", 1,
         {"bin/e2e": sh("QA_TARGET=image npx playwright test"), "qa/playwright.config.ts": ENVCONFIG}),
        ("env-dependent config, an earlier export QA_TARGET=image", 1, {"bin/e2e": sh("export QA_TARGET=image\nnpx playwright test"), "qa/playwright.config.ts": ENVCONFIG}),
        ("env-dependent config, no environment set: the spec IS selected", 0, {"bin/e2e": sh("npx playwright test"), "qa/playwright.config.ts": ENVCONFIG}),
        ("env-dependent config, env set to another target: the spec IS selected", 0, {"bin/e2e": sh("QA_TARGET=dev npx playwright test"), "qa/playwright.config.ts": ENVCONFIG}),
        ("an env file sourced with `. file` before the command is refused (the config reads QA_TARGET)", 2,
         {"bin/e2e": sh("echo 'export QA_TARGET=image' > qa/image.env\n. qa/image.env\nnpx playwright test"), "qa/playwright.config.ts": ENVCONFIG}),
        ("an env file sourced with `source file` before the command is refused", 2,
         {"bin/e2e": sh("source qa/image.env\nnpx playwright test"), "qa/image.env": "export QA_TARGET=image\n", "qa/playwright.config.ts": ENVCONFIG}),
        ("an exported NAME+=value before the command is refused", 2, {"bin/e2e": sh("export QA_TARGET+=image\nnpx playwright test"), "qa/playwright.config.ts": ENVCONFIG}),
        ("an `eval export` before the command is refused", 2, {"bin/e2e": sh('eval "export QA_TARGET=image"\nnpx playwright test'), "qa/playwright.config.ts": ENVCONFIG}),
        ("a `declare -x` before the command is refused", 2, {"bin/e2e": sh("declare -x QA_TARGET=image\nnpx playwright test"), "qa/playwright.config.ts": ENVCONFIG}),
        ("a `typeset -x` before the command is refused", 2, {"bin/e2e": sh("typeset -x QA_TARGET=image\nnpx playwright test"), "qa/playwright.config.ts": ENVCONFIG}),
        ("a `command export` before the command is refused", 2, {"bin/e2e": sh("command export QA_TARGET=image\nnpx playwright test"), "qa/playwright.config.ts": ENVCONFIG}),
        ("a function that sources an env file, then called, is refused", 2,
         {"bin/e2e": sh("setup() { . qa/image.env; }\nsetup\nnpx playwright test"), "qa/image.env": "export QA_TARGET=image\n", "qa/playwright.config.ts": ENVCONFIG}),
        ("docker and ./setup.sh before the command are allowed; the env prefix still decides: not selected under image", 1,
         {"bin/e2e": sh("docker compose up -d\n./setup.sh\nQA_TARGET=image npx playwright test"), "qa/playwright.config.ts": ENVCONFIG}),
        ("docker before the command with no environment set: the spec is selected", 0,
         {"bin/e2e": sh("docker compose up -d\nnpx playwright test"), "qa/playwright.config.ts": ENVCONFIG}),
        ("--only-changed is refused", 2, {"bin/e2e": sh('npx playwright test --only-changed --grep "@REQ-001"')}),
        ("--last-failed is refused", 2, {"bin/e2e": sh("npx playwright test --last-failed")}),
        ("a 2>&1 redirect is shell, not a file filter", 0, {"bin/e2e": sh('npx playwright test --grep "@REQ-001" 2>&1')}),
        ("control: a lookbehind grep is Playwright's to read", 1, {"bin/e2e": sh('npx playwright test --grep "(?<=@)qa-image"')}),
    ]
    for label, want, over in battery:
        files = {**BASE, **over}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, text in files.items():
                if text is None:
                    continue
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(text)
            (root / "node_modules").symlink_to((modules / "node_modules").resolve())
            code, found, notes = check(root)
        if code != want:
            failures.append(f"real Playwright, {label}: wanted exit {want}, got {code}: {(found + notes)[:2]!r}")
        else:
            print(f"  real ok: {label}")
    return failures


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Every feature requirement has a test that a runner selects, by Playwright's own listing (#1856).")
    parser.add_argument("--root", default=".", help="the project root (default: the current directory)")
    parser.add_argument("--base", metavar="REF", help="refuse a baseline line not in REF's baseline (default: `requirements: base:` in qa/qa.config.yml, else origin/dev)")
    parser.add_argument("--selftest", action="store_true", help="prove each rule fires on a violation and stays silent on conforming input")
    parser.add_argument("--match", metavar="TEXT", help="with --selftest: run only the rows whose label contains TEXT (the mutation harness)")
    parser.add_argument("--real", metavar="DIR", help="with --selftest: also run the attack battery against a real Playwright (DIR holds node_modules)")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest(args.match, args.real)
    root = Path(args.root).resolve()
    base, unchecked = None, False
    try:
        conf = settings(root)
        ref, explicit = cr.base_ref(root, args.base)
        state, lines = cr.base_baseline(ref, root, baseline=conf["baseline"], default_baseline=E2E_BASELINE)
        if state == "unreadable":
            if explicit:
                print(f"check_e2e_paths: cannot read {ref} (exit 2, not a pass)", file=sys.stderr)
                return 2
            print(f"check_e2e_paths: note: the default base {ref} cannot be read, so growth was not checked; set `base:` under `requirements:` in qa/qa.config.yml")
            unchecked = True
        elif state == "none":
            print(f"check_e2e_paths: note: {ref} holds no registry or baseline, so growth against it was not checked (first adoption)")
        else:
            base = lines
    except ValueError as exc:
        print(f"check_e2e_paths: {exc} (exit 2, not a pass)", file=sys.stderr)
        return 2
    code, found, notes = check(root, base)
    for line in found:
        print(line)
    for note in notes:
        print(f"note: {note}")
    if code == 0 and unchecked:
        print("check_e2e_paths: nothing found, but growth was not checked: exit 3 (a skip, not a pass)")
        return 3
    print(f"check_e2e_paths: {'ok' if code == 0 else 'could not check (exit 2, not a pass)' if code == 2 else str(len(found)) + ' finding(s)'}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
