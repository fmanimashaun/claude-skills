#!/usr/bin/env python3
"""A TypeScript e2e suite is strict, type-checked, and free of explicit `any` (#1447).

Run:  python3 check_ts_strict.py                 # this project
      python3 check_ts_strict.py --root path/to/app
      python3 check_ts_strict.py --selftest

WHY THIS EXISTS. The owner's expectation (2026-09-29): "strict typescript with no any type in our code
... where typescript is applicable". A `"strict": true` tsconfig is enforced by nothing on its own,
because **Playwright does not type-check**: "Playwright does not check the types and will run tests
even if there are non-critical TypeScript compilation errors", and its docs recommend running
`tsc -p tsconfig.json --noEmit` alongside (playwright.dev/docs/test-typescript; doctrine-verifier
CONFIRMED 2026-09-30). And `strict` cannot refuse an EXPLICIT `any`: its `noImplicitAny` member flags
only an `any` the compiler would have inferred (typescriptlang.org/tsconfig; CONFIRMED). So a suite
can say `"strict": true`, carry `as any`, and never be type-checked at all -- which is what the
downstream measurement found before its CI added a `tsc` step.

THREE RULES, on the suite under `qa/`:

  ts-not-strict     some `qa/**/tsconfig*.json` (every one, not only the nearest) is not strict as the
                    compiler sees it: its options merged through `extends` -- a relative path, a package
                    in `node_modules`, or an array whose later entries win -- do not set `"strict": true`,
                    or set a member of the strict family false (`noImplicitAny`, `strictNullChecks`, ...),
                    which switches that one back off (typescriptlang.org/tsconfig#strict; CONFIRMED; the
                    list is TypeScript 5.6+). An `extends` that cannot be followed, or that is circular, is
                    reported as exactly that; a parent shared by several paths is read once. A suite with
                    TypeScript and no tsconfig under `qa/` is a finding too.
  ts-no-typecheck   no CI STEP type-checks the suite and can fail. A step counts when it runs `tsc -p` /
                    `--project` on a path under `qa/`, or `npm|pnpm|yarn [--prefix DIR] run <name>` whose
                    script does. The path resolves from the step's `working-directory:` (wherever it sits in
                    the step), else the job's or workflow's `defaults.run.working-directory`, then any
                    `cd <dir>` before it in the step. Not a step: a tsc on the app or with no `-p`; a
                    `package.json` script nothing runs; a step or job with `continue-on-error: true` or
                    `if: false`; a call whose verdict is swallowed (`|| ...`, `; exit 0`, `; true`, or an
                    `exit 0` later in the step); a call only printed (`echo`, `printf`, `:`); and a `#`
                    comment. Surfaces: `.github/workflows/*.yml` (read per step), `config/ci.rb` (per line),
                    `bin/*` (per file).
  ts-explicit-any   the keyword `any` in code, wherever it is a type: `: any`, `as any`, `Record<string, any>`,
                    `type T = any`, `<T = any>`, `string | any`, `keyof any`, `x ? any : y`. Comments and
                    string/template/regex text are blanked first; a member (`expect.any(Number)`, `obj.any`),
                    a decorator or private name (`@any`, `#any`), and an object key (`any:` after `{ , ; (`
                    or at a line start) are not types. Files: `.ts`, `.tsx`, `.mts`, `.cts`. A line may
                    declare an exception with a reason, in a COMMENT on it or directly above it:
                    `// ts-strict: allow-any -- <why>`; one with no reason, or inside a string, is not one.

NOT APPLICABLE (exit 3) when the project has no TypeScript under `qa/` -- reported, never a pass.

KNOWN LIMITS.
- Blanking is a scanner's, not a parser's. A regex literal is recognised by the character before its `/`
  (an operator, `(`, `,`, `=`, a line start -- where a value cannot end; a postfix `++`/`--` ends a
  value). After a keyword (`return /'/`) it is read as a division, so a `//` in it starts a comment and a
  quote in it opens a string to the end of the line -- either can hide a real `any` on that line. (Without
  the rule, downstream's `path.replace(/\\//g, "-")` inside a template put the scanner out of phase.)
- JSX text in a `.tsx` is read as code, and so are `{ any }` shorthand and `let any = 1`: the word is a
  false finding there (declare it).
- The workflow reader is not a YAML parser: flow-style steps (`steps: [{...}]`), anchors and multi-line
  plain scalars are not read, and a matrix `-p ${{ matrix.p }}` is not resolved (so is not a step). A
  `set +e` before the call is not seen. A package script is followed one level: a script that calls
  another script is not traced.
- `noUncheckedIndexedAccess` is doctrine advice, not a finding, because `strict` does not include it
  (CONFIRMED) and a gate requiring it would be red on day one for a reason the owner did not state.

Stdlib only, no network. Exit 0 clean, 1 findings, 3 not applicable.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from pathlib import Path

EXTS = ("*.ts", "*.tsx", "*.mts", "*.cts")
# The keyword itself, on BLANKED text: not part of a word or a member (`expect.any(...)`, `obj.any`), and not an
# object key (`{ any: 1 }`, `{ any?: 1 }`). A token, not a list of positions -- the list missed Record<string, any>.
ANY = re.compile(r"(?<![\w$.#@])any(?![\w$])")
# `any` then `:` is an object key only where a key can start: after `{ , ; (` or at the line start. After
# anything else (`x as any : y`, `? any : never`) the `:` belongs to a ternary or conditional type.
KEY_COLON = re.compile(r"\s*\??\s*:")
KEY_BEFORE = "{,;("
ALLOW = re.compile(r"ts-strict:[ \t]*allow-any[ \t]*--[ \t]*\w")
TSC = re.compile(r"(?<![\w-])tsc(?![\w-])(?P<args>[^\n;&|]*)")
PROJECT = re.compile(r"(?:^|\s)(?:-p|--project)(?:\s+|=)['\"]?(?P<path>[^\s'\"]+)")
RUNNER = re.compile(r"(?<![\w-])(?P<tool>npm|pnpm|yarn)\s(?P<args>[^\n;&|]*)")
DIR_FLAG = re.compile(r"(?:--prefix|--cwd|--dir|-C)(?:\s+|=)['\"]?(?P<dir>[^\s'\"]+)")
CD = re.compile(r"(?:^|[;&|(]\s*)cd\s+['\"]?(?P<dir>[^\s'\";&|)]+)['\"]?\s*(?=&&|;|$)")
# What makes a step enforce nothing: its verdict swallowed after the call, or the call only printed.
SWALLOWED = re.compile(r"^\s*\|\||(?:^|[;&|]\s*)exit\s+0\b|;\s*(?:true|:)\s*(?:[;#]|$)")
PRINTED = ("echo", "printf", ":")
YAML_KEY = re.compile(r"^(?P<indent>\s*)(?P<item>-\s+)?(?P<key>[\w-]+):(?:\s+(?P<val>.*))?$")
OFF = re.compile(r"^(?:false|\$\{\{\s*false\s*\}\})$")
# A `/` after one of these (or at the start) cannot be a division, so it opens a regex literal.
REGEX_AFTER = set("(,=:[!&|?{};+-*%<>~^")
JSONC = re.compile(r'"(?:\\.|[^"\\\n])*"|//[^\n]*|/\*.*?\*/', re.S)
TRAILING = re.compile(r'"(?:\\.|[^"\\\n])*"|,(?=\s*[}\]])')
# `strict` switches on a family; a member set false switches that one back off (typescriptlang.org/tsconfig#strict,
# CONFIRMED 2026-09-30). The list is TypeScript 5.6+: `strictBuiltinIteratorReturn` joined in 5.6 ("TypeScript 5.6
# introduces a new `--strict`-mode flag called `--strictBuiltinIteratorReturn`", the 5.6 release notes).
STRICT_FAMILY = ("alwaysStrict", "noImplicitAny", "noImplicitThis", "strictBindCallApply",
                 "strictBuiltinIteratorReturn", "strictFunctionTypes", "strictNullChecks",
                 "strictPropertyInitialization", "useUnknownInCatchVariables")


def _scan(text: str) -> tuple[str, str]:
    """Comments and string/template TEXT replaced by spaces, newlines kept, so a finding's line number
    is the real one. A character scanner, not a regex: sequential quote-pairing went out of phase on
    a template literal (`${role}_session_cookie`) and blanked twenty lines of real code, `as any`
    included -- found on the first downstream run. `${...}` inside a template is scanned as CODE, and a
    '/" string ends at a newline (JavaScript forbids one there), so a stray quote cannot run away.
    Returns (code with the rest blanked, comment text alone) -- the allow marker counts only in the second."""
    out = list(text)
    com = [c if c == "\n" else " " for c in text]
    n = len(text)
    i = 0
    stack: list[str] = []            # "code" frames opened by `${` inside a template

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

    def comment(a: int, b: int) -> None:
        com[a:b] = text[a:b]
        blank(a, b)

    def scan_template(i: int) -> int:
        """At the char after an opening backtick; blank text, recurse into ${...}; return past the close."""
        start = i
        while i < n:
            c = text[i]
            if c == "\\":
                i += 2
                continue
            if c == "`":
                blank(start, i)
                return i + 1
            if c == "$" and i + 1 < n and text[i + 1] == "{":
                blank(start, i)
                i = scan_code(i + 2, closing="}")
                start = i
                continue
            i += 1
        blank(start, n)
        return n

    def scan_regex(i: int) -> int | None:
        """At a `/` that opens a regex literal: blank its body, return past the flags; None if the line
        ends first (then it was a division after all)."""
        j, in_class = i + 1, False
        while j < n and text[j] != "\n":
            c = text[j]
            if c == "\\":
                j += 2
                continue
            if c == "[":
                in_class = True
            elif c == "]":
                in_class = False
            elif c == "/" and not in_class:
                blank(i + 1, j)
                j += 1
                while j < n and (text[j].isalnum() or text[j] == "_"):
                    j += 1
                return j
            j += 1
        return None

    def scan_code(i: int, closing: str | None = None) -> int:
        depth = 0
        prev = ""                    # the last significant code character: a `/` after a value divides
        while i < n:
            c = text[i]
            if not c.isspace() and c != "/":
                prev = "x" if c in "+-" and i > 0 and text[i - 1] == c else c   # `i++ / 2` divides
            if c == "/" and i + 1 < n and text[i + 1] not in "/*" and (not prev or prev in REGEX_AFTER):
                e = scan_regex(i)
                if e is not None:
                    i, prev = e, "x"
                    continue
            if c == "/" and i + 1 < n and text[i + 1] == "/":
                e = text.find("\n", i)
                e = n if e == -1 else e
                comment(i, e)
                i = e
            elif c == "/" and i + 1 < n and text[i + 1] == "*":
                e = text.find("*/", i + 2)
                e = n if e == -1 else e + 2
                comment(i, e)
                i = e
            elif c in "\"'":
                j = i + 1
                while j < n and text[j] != c and text[j] != "\n":
                    j += 2 if text[j] == "\\" else 1
                blank(i + 1, min(j, n))
                i = j + 1
            elif c == "`":
                i = scan_template(i + 1)
            elif closing and c == "{":
                depth += 1
                i += 1
            elif closing and c == closing:
                if depth == 0:
                    return i + 1
                depth -= 1
                i += 1
            else:
                i += 1
        return n

    scan_code(0)
    return "".join(out), "".join(com)


def _blank(text: str) -> str:
    return _scan(text)[0]


def _load_json(path: Path) -> dict:
    """A tsconfig is JSONC: comments and trailing commas are legal. Both are removed by an alternation that
    matches a whole string FIRST and keeps it, so `"@fixtures/*"` or `"https://x"` is never read as a comment."""
    text = JSONC.sub(lambda m: m.group(0) if m.group(0).startswith('"') else "", path.read_text(encoding="utf-8-sig"))
    return json.loads(TRAILING.sub(lambda m: m.group(0) if m.group(0).startswith('"') else "", text))


class Unfollowed(Exception):
    """An `extends` this script cannot resolve, or a circular one, so strictness cannot be read -- a finding
    of its own kind; the message is the reason."""


def _resolve_extends(tsconfig: Path, spec: str) -> Path:
    if spec.startswith("."):
        candidates = [tsconfig.parent / spec]
    else:                             # a package: node_modules, nearest first
        candidates = [d / "node_modules" / spec for d in [tsconfig.parent, *tsconfig.parent.parents]]
    for c in candidates:
        for t in (c, c.with_name(c.name + ".json"), c / "tsconfig.json"):
            if t.is_file():
                return t.resolve()
    raise Unfollowed(f"`extends` {spec!r} could not be followed (install the suite's dependencies before this "
                     f"gate, or set `\"strict\": true` in this file), so its strictness cannot be read")


def effective_options(tsconfig: Path, seen: frozenset = frozenset(), cache: dict | None = None,
                      depth: int = 0) -> dict:
    """`compilerOptions` as the compiler sees them: each `extends` (a string, or an array whose later entries
    win) merged first, then this file's own options over the top. A file met again on its own chain is a
    cycle and is reported; a file met again on another branch is read once (`cache`), so an array listing
    one parent many times costs one load, not one per path."""
    cache = {} if cache is None else cache
    key = tsconfig.resolve()
    if key in seen:
        raise Unfollowed(f"`extends` is circular through {key.name}, so its strictness cannot be read")
    if depth > 32:
        raise Unfollowed("`extends` is more than 32 files deep, so its strictness was not read")
    if key not in cache:
        cfg = _load_json(tsconfig)
        parents = cfg.get("extends") or []
        merged: dict = {}
        for spec in [parents] if isinstance(parents, str) else parents:
            merged.update(effective_options(_resolve_extends(tsconfig, spec), seen | {key}, cache, depth + 1))
        merged.update(cfg.get("compilerOptions") or {})
        cache[key] = merged
    return dict(cache[key])


def not_strict_reason(tsconfig: Path) -> str | None:
    """Why this tsconfig is not strict, or None when it is."""
    try:
        opts = effective_options(tsconfig)
    except Unfollowed as e:
        return str(e)
    if opts.get("strict") is not True:
        return "`compilerOptions.strict` is not true"
    off = [k for k in STRICT_FAMILY if opts.get(k) is False]
    if off:
        return f"`strict` is true but {', '.join(f'`{k}`' for k in off)} is set false, which switches it back off"
    return None


def _under_qa(cwd: str, path: str) -> bool:
    rel = posixpath.normpath(posixpath.join(cwd, path))
    return rel == "qa" or rel.startswith("qa/")


def _strip_comment(line: str) -> str:
    """A shell/YAML/Ruby line up to its comment: a `#` outside quotes, at the start or after whitespace."""
    quote = ""
    for i, c in enumerate(line):
        if quote:
            quote = "" if c == quote else quote
        elif c in "'\"":
            quote = c
        elif c == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i]
    return line


def _enforces(cmd: str, start: int, end: int, later: str) -> bool:
    """The call at cmd[start:end] can fail the step: it is not printed (`echo tsc ...`), and its verdict is not
    swallowed after it (`|| true`, `|| echo`, `; exit 0`, `; true`, here or later in the step)."""
    seg = max(cmd.rfind(t, 0, start) for t in (";", "&&", "||", "|", "(", "`"))
    words = cmd[seg + 1 if seg >= 0 else 0:start].replace("&", " ").split()
    if words[:1] and words[0] in PRINTED:
        return False
    return not SWALLOWED.search(cmd[end:]) and not re.search(r"(?<![\w-])exit\s+0\b", later)


def _checks_suite(cmd: str, cwd: str, later: str = "") -> bool:
    """`cmd`, run from `cwd` (relative to the root), invokes tsc on a project under qa/ and can fail."""
    for m in TSC.finditer(cmd):
        here = posixpath.join(cwd, *[c.group("dir") for c in CD.finditer(cmd[:m.start()])])
        p = PROJECT.search(m.group("args"))
        if p and _under_qa(here, p.group("path")) and _enforces(cmd, m.start(), m.end(), later):
            return True
    return False


def _scripts(root: Path, pkg_dir: str) -> dict:
    try:
        scripts = json.loads((root / pkg_dir / "package.json").read_text(encoding="utf-8")).get("scripts", {})
    except (json.JSONDecodeError, OSError, AttributeError):
        return {}
    return scripts if isinstance(scripts, dict) else {}


def _runs_suite_script(root: Path, cmd: str, cwd: str, later: str = "") -> str | None:
    """`npm|pnpm|yarn [--prefix DIR] run NAME` in `cmd` whose package script type-checks the suite."""
    for m in RUNNER.finditer(cmd):
        here = posixpath.join(cwd, *[c.group("dir") for c in CD.finditer(cmd[:m.start()])])
        args = m.group("args")
        d = DIR_FLAG.search(args)
        pkg = posixpath.normpath(posixpath.join(here, d.group("dir")) if d else here)
        words = [w.strip("'\"") for w in DIR_FLAG.sub(" ", args).split() if not w.startswith("-")]
        if words[:1] in (["run"], ["run-script"]):
            words = words[1:]
        elif m.group("tool") == "npm":
            continue                  # npm runs a script only through `run`
        script = _scripts(root, pkg).get(words[0]) if words else None
        if isinstance(script, str) and _checks_suite(script, pkg) and _enforces(cmd, m.start(), m.end(), later):
            return f"{pkg}/package.json scripts.{words[0]}"
    return None


def workflow_steps(text: str) -> list[dict]:
    """Each step of a GitHub workflow, read without a YAML library: {"line", "keys", "run": [(line, text)],
    "wd", "off"}. A step is a `- ` item under a `steps:` key, and every key in it counts wherever it sits
    (a `working-directory:` after `run:` included). A `run: |` block is the lines indented under it. `wd` is
    the step's own `working-directory`, else the job's `defaults.run.working-directory`, else the
    workflow's; `off` is a `continue-on-error: true` or `if: false` on the step or its job."""
    steps: list[dict] = []
    jobs = job = steps_at = item_at = block = None
    cur: dict | None = None
    wf_wd = job_wd = None
    job_off = False
    for n, raw in enumerate(text.splitlines(), 1):
        indent = len(raw) - len(raw.lstrip())
        if block is not None:
            if not raw.strip() or indent > block:
                cur["run"].append((n, raw.strip()))
                continue
            block = None
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = YAML_KEY.match(_strip_comment(raw).rstrip())
        if steps_at is not None:
            is_item = raw.lstrip().startswith("- ")
            if is_item and (indent == item_at or (item_at is None and indent >= steps_at)):
                item_at = indent
                cur = {"line": n, "keys": {}, "run": [], "wd": job_wd or wf_wd, "off": job_off}
                steps.append(cur)
            elif not (cur is not None and indent > (item_at if item_at is not None else steps_at)):
                steps_at = item_at = cur = None
            if cur is not None:
                if m:
                    key, val = m.group("key"), (m.group("val") or "").strip()
                    if key == "run" and val[:1] in ("|", ">"):
                        block = indent + (len(m.group("item")) if m.group("item") else 0)
                    elif key == "run":
                        cur["run"].append((n, val))
                    else:
                        cur["keys"][key] = val.strip("'\"")
                continue
        if not m:
            continue
        key, val = m.group("key"), (m.group("val") or "").strip().strip("'\"")
        if key == "jobs":
            jobs, job = indent, None
        elif jobs is not None and indent > jobs and (job is None or indent == job) and not val:
            job, job_wd, job_off = indent, None, False
        elif key == "steps":
            steps_at, item_at, cur = indent, None, None
        elif key == "working-directory":
            if jobs is None:
                wf_wd = val
            else:
                job_wd = val
        elif key == "continue-on-error" and val == "true" and job is not None:
            job_off = True
        elif key == "if" and OFF.match(val) and job is not None:
            job_off = True
    return steps


def _script_finds(root: Path, rel: str, lines: list[tuple[int, str]], cwd: str) -> str | None:
    """The first line of one script (a step's `run`, a `bin/*` file) that type-checks the suite and can fail.
    A `cd <dir>` carries forward to the lines after it, as it does in a shell."""
    text = [(n, _strip_comment(t)) for n, t in lines]
    for k, (n, cmd) in enumerate(text):
        later = "\n".join(t for _, t in text[k + 1:])
        if _checks_suite(cmd, cwd, later):
            return f"{rel}:{n}"
        via = _runs_suite_script(root, cmd, cwd, later)
        if via:
            return f"{rel}:{n} (via {via})"
        for c in CD.finditer(cmd):
            cwd = posixpath.normpath(posixpath.join(cwd, c.group("dir")))
    return None


def typecheck_step(root: Path) -> str | None:
    """The first CI step that type-checks the SUITE -- `tsc -p <path under qa/>` directly, or a package script
    doing so that the step runs -- and can fail, as `file:line`, or None. A tsc on the app, a script nothing
    runs, a step that is switched off or swallows its verdict, and a tsc that is only printed are not one."""
    for p in sorted((root / ".github/workflows").glob("*.y*ml")):
        for step in workflow_steps(p.read_text(encoding="utf-8", errors="replace")):
            keys = step["keys"]
            if step["off"] or keys.get("continue-on-error") == "true" or OFF.match(keys.get("if", "")):
                continue
            wd = posixpath.normpath(keys.get("working-directory") or step["wd"] or ".")
            hit = _script_finds(root, str(p.relative_to(root)), step["run"], wd)
            if hit:
                return hit
    ci = root / "config/ci.rb"
    if ci.is_file():                  # one `step "name", "command"` per line, each its own process
        for n, line in enumerate(ci.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            hit = _script_finds(root, "config/ci.rb", [(n, line)], ".")
            if hit:
                return hit
    for p in sorted(q for q in (root / "bin").glob("*") if q.is_file()):
        lines = list(enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1))
        hit = _script_finds(root, str(p.relative_to(root)), lines, ".")
        if hit:
            return hit
    return None


def _is_type_any(line: str, m: re.Match) -> bool:
    if KEY_COLON.match(line, m.end()):
        before = line[:m.start()].rstrip()
        return bool(before) and before[-1] not in KEY_BEFORE
    return True


def explicit_anys(rel: str, source: str) -> list[str]:
    out = []
    raw = source.split("\n")
    code, comments = _scan(source)
    notes = comments.split("\n")
    for n, line in enumerate(code.split("\n")):
        if not any(_is_type_any(line, m) for m in ANY.finditer(line)):
            continue
        if ALLOW.search(notes[n]) or (n > 0 and ALLOW.search(notes[n - 1])):
            continue
        out.append(f"{rel}:{n + 1}: ts-explicit-any — `{raw[n].strip()[:80]}`. Use `unknown` and narrow it "
                   f"(e.g. `catch (err: unknown)`), or declare why: `// ts-strict: allow-any -- <why>`.")
    return out


def run(root: Path) -> tuple[list[str], int] | None:
    qa = root / "qa"
    ts = sorted({p for ext in EXTS for p in qa.glob(f"**/{ext}") if "node_modules" not in p.parts}) if qa.is_dir() else []
    if not ts:
        return None
    findings: list[str] = []
    configs = sorted(p for p in qa.glob("**/tsconfig*.json") if "node_modules" not in p.parts)
    if not configs:
        findings.append("qa: ts-not-strict — the suite has TypeScript but no tsconfig under qa/, so nothing makes it strict.")
    for cfg in configs:
        try:
            why = not_strict_reason(cfg)
        except (json.JSONDecodeError, OSError) as e:
            why = f"unreadable tsconfig ({e})"
        if why:
            findings.append(f"{cfg.relative_to(root)}: ts-not-strict — {why}.")
    if typecheck_step(root) is None:
        findings.append("qa: ts-no-typecheck — no CI step type-checks the suite (`tsc -p <tsconfig under qa/>`, or "
                        "`npm --prefix qa run typecheck` whose script does); Playwright does not type-check, so "
                        "`strict` is enforced by nothing.")
    for p in ts:
        findings += explicit_anys(str(p.relative_to(root)), p.read_text(encoding="utf-8", errors="replace"))
    return findings, len(ts)


# --------------------------------------------------------------------------- selftest

STRICT = '{\n  // comments are legal in a tsconfig\n  "compilerOptions": { "strict": true, },\n}\n'
CI_YML = "jobs:\n  qa:\n    steps:\n      # tsc --noEmit is explained here but run below\n      - run: npm --prefix qa run typecheck\n"
QA_PKG = '{"scripts": {"typecheck": "tsc --noEmit -p e2e/tsconfig.json"}}'


def _wf(*steps: str, job: str = "") -> str:
    """A workflow with one job; each argument is one step's lines, already indented under `- `."""
    return "jobs:\n  qa:\n" + job + "    steps:\n" + "".join("      - " + st.replace("\n", "\n        ") + "\n" for st in steps)


TSC_QA = "npx tsc --noEmit -p qa/e2e/tsconfig.json"


def _selftest() -> int:
    import tempfile
    fails: list[str] = []

    def expect(label: str, ok: bool) -> None:
        if not ok:
            fails.append(label)

    def rules(files: dict[str, str]) -> list[str] | None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for rel, body in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(body)
            got = run(root)
            if got is None:
                return None
            return [re.search(r"(ts-[a-z-]+)", f).group(1) for f in got[0]]

    def run_findings(files: dict[str, str]) -> list[str]:
        with tempfile.TemporaryDirectory() as d:
            for rel, body in files.items():
                (Path(d) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(d) / rel).write_text(body)
            got = run(Path(d))
            return got[0] if got else []

    base = {"qa/e2e/tsconfig.json": STRICT, ".github/workflows/ci.yml": CI_YML, "qa/package.json": QA_PKG,
            "qa/e2e/a.spec.ts": "const n: number = 1;\n"}
    no_ci = {k: v for k, v in base.items() if not k.startswith(".github")}
    expect("CONTROL: a strict, type-checked suite with no any is clean", rules(base) == [])
    expect("no TypeScript under qa/ is NOT APPLICABLE, not a pass", rules({"qa/e2e/a.spec.js": "x"}) is None)

    # ts-not-strict
    expect("a tsconfig without strict is caught",
           rules({**base, "qa/e2e/tsconfig.json": '{"compilerOptions": {"noEmit": true}}'}) == ["ts-not-strict"])
    expect("strict: false is caught", rules({**base, "qa/e2e/tsconfig.json": '{"compilerOptions": {"strict": false}}'}) == ["ts-not-strict"])
    expect("strict inherited through a relative extends counts",
           rules({**base, "qa/base.json": STRICT, "qa/e2e/tsconfig.json": '{"extends": "../base.json"}'}) == [])
    expect("TypeScript with no tsconfig at all is caught",
           rules({k: v for k, v in base.items() if k != "qa/e2e/tsconfig.json"}) == ["ts-not-strict"])
    expect("strict: true with noImplicitAny: false is caught",
           rules({**base, "qa/e2e/tsconfig.json": '{"compilerOptions": {"strict": true, "noImplicitAny": false}}'}) == ["ts-not-strict"])
    expect("a family member switched off in a PARENT, strict set here, is caught",
           rules({**base, "qa/base.json": '{"compilerOptions": {"strictNullChecks": false}}',
                  "qa/e2e/tsconfig.json": '{"extends": "../base.json", "compilerOptions": {"strict": true}}'}) == ["ts-not-strict"])
    expect("an array extends: the later entry wins, and it is followed",
           rules({**base, "qa/lax.json": '{"compilerOptions": {"strict": false}}', "qa/base.json": STRICT,
                  "qa/e2e/tsconfig.json": '{"extends": ["../lax.json", "../base.json"]}'}) == [])
    expect("an array extends whose LAST entry is lax is caught",
           rules({**base, "qa/lax.json": '{"compilerOptions": {"strict": false}}', "qa/base.json": STRICT,
                  "qa/e2e/tsconfig.json": '{"extends": ["../base.json", "../lax.json"]}'}) == ["ts-not-strict"])
    expect("a package extends is followed into node_modules",
           rules({**base, "qa/node_modules/@tsconfig/strictest/tsconfig.json": STRICT,
                  "qa/e2e/tsconfig.json": '{"extends": "@tsconfig/strictest/tsconfig.json"}'}) == [])
    unfollowed = run_findings({**base, "qa/e2e/tsconfig.json": '{"extends": "@tsconfig/strictest"}'})
    expect("an extends that cannot be followed says so, not 'strict is not true'",
           len(unfollowed) == 1 and "could not be followed" in unfollowed[0])
    circular = run_findings({**base, "qa/a.json": '{"extends": "./b.json"}', "qa/b.json": '{"extends": "./a.json"}',
                             "qa/e2e/tsconfig.json": '{"extends": "../a.json"}'})
    expect("a circular extends is reported as circular, not read as strict or not strict",
           len(circular) == 1 and "circular" in circular[0])
    loads = [0]
    real_load = globals()["_load_json"]

    def counting(path: Path) -> dict:
        loads[0] += 1
        return real_load(path)
    globals()["_load_json"] = counting
    try:
        chain = {**base, "qa/l0.json": STRICT}
        for k in range(1, 5):
            chain[f"qa/l{k}.json"] = json.dumps({"extends": [f"./l{k - 1}.json"] * 4})
        chain["qa/e2e/tsconfig.json"] = '{"extends": ["../l4.json", "../l4.json", "../l4.json", "../l4.json"]}'
        expect("a shared parent is loaded once, not once per path (4^5 without the cache)",
               rules(chain) == [] and loads[0] < 100)
    finally:
        globals()["_load_json"] = real_load
    expect("a tsconfig with a UTF-8 BOM is read", rules({**base, "qa/e2e/tsconfig.json": "\ufeff" + STRICT}) == [])
    expect("CONTROL: a paths alias with /* and a **/*.ts include is still read strict (JSONC is string-aware)",
           rules({**base, "qa/e2e/tsconfig.json": '{"compilerOptions": {"baseUrl": ".", "paths": {"@fixtures/*": '
                  '["./fixtures/*"]}, "strict": true}, "include": ["e2e/**/*.ts"]}'}) == [])
    expect("CONTROL: a trailing // comment after a value is still read strict",
           rules({**base, "qa/e2e/tsconfig.json": '{"compilerOptions": {"strict": true // yes\n}}'}) == [])
    expect("CONTROL: a // inside a string is kept, not stripped",
           rules({**base, "qa/e2e/tsconfig.json": '{"compilerOptions": {"strict": true}, "x": "https://a/b",}'}) == [])

    # ts-no-typecheck
    expect("no typecheck step is caught", rules(no_ci) == ["ts-no-typecheck"])
    expect("a tsc mentioned only in a CI COMMENT is not a step",
           rules({**base, ".github/workflows/ci.yml": "steps:\n  # we should run tsc --noEmit -p qa/e2e\n"}) == ["ts-no-typecheck"])
    expect("a tsc on the APP, not the suite, is not a suite typecheck",
           rules({**base, ".github/workflows/ci.yml": "steps:\n  - run: npx tsc --noEmit -p app/javascript\n"}) == ["ts-no-typecheck"])
    expect("a tsc with no -p is not a suite typecheck",
           rules({**base, ".github/workflows/ci.yml": "steps:\n  - run: npx tsc --noEmit\n"}) == ["ts-no-typecheck"])
    expect("a qa typecheck script that NO CI surface runs does not count",
           rules({**no_ci, "qa/package.json": '{"scripts": {"typecheck": "tsc --noEmit -p e2e/tsconfig.json"}}'}) == ["ts-no-typecheck"])
    scaffold = {**no_ci, "qa/package.json": '{"scripts": {"typecheck": "tsc --noEmit -p e2e/tsconfig.json"}}'}
    expect("the scaffold's script, run by CI with npm --prefix qa, counts",
           rules({**scaffold, ".github/workflows/ci.yml": "steps:\n  - run: npm --prefix qa run typecheck\n"}) == [])
    expect("a CI line running a script that type-checks the APP does not count",
           rules({**no_ci, "package.json": '{"scripts": {"types": "tsc --noEmit -p app/javascript"}}',
                  ".github/workflows/ci.yml": "steps:\n  - run: npm run types\n"}) == ["ts-no-typecheck"])
    expect("a working-directory: qa step resolves -p from qa/",
           rules({**no_ci, ".github/workflows/ci.yml": "steps:\n  - working-directory: qa\n    run: npx tsc --noEmit -p e2e/tsconfig.json\n"}) == [])
    expect("working-directory does not leak into the next step",
           rules({**no_ci, ".github/workflows/ci.yml": "steps:\n  - working-directory: qa\n    run: true\n"
                  "  - run: npx tsc --noEmit -p e2e/tsconfig.json\n"}) == ["ts-no-typecheck"])
    expect("a `cd qa &&` prefix resolves -p from qa/",
           rules({**no_ci, "bin/types": "#!/bin/sh\ncd qa && npx tsc --noEmit -p e2e/tsconfig.json\n"}) == [])
    expect("a config/ci.rb step counts",
           rules({**no_ci, "config/ci.rb": 'step "Types", "npm --prefix qa run typecheck"\n'}) == [])

    # ts-no-typecheck, per STEP (delta review of #1503: B1, B2, S1, S2)
    def ci(*steps: str, job: str = "") -> list[str] | None:
        return rules({**no_ci, ".github/workflows/ci.yml": _wf(*steps, job=job)})
    expect("CONTROL: a direct tsc -p on the suite counts", ci(f"run: {TSC_QA}") == [])
    expect("CONTROL: a tsc followed by && counts", ci(f"run: {TSC_QA} && echo typed") == [])
    expect("CONTROL: an if: on a real condition still counts", ci(f"if: github.event_name == 'push'\nrun: {TSC_QA}") == [])
    for label, step in (("|| true", f"run: {TSC_QA} || true"), ("|| echo", f"run: {TSC_QA} || echo failed"),
                        ("; exit 0", f"run: {TSC_QA}; exit 0"), ("; true", f"run: {TSC_QA}; true"),
                        ("a runner's || true", "run: npm --prefix qa run typecheck || true")):
        expect(f"a swallowed verdict is not a typecheck: {label}", ci(step) == ["ts-no-typecheck"])
    expect("an exit 0 later in the same run block swallows the verdict",
           ci(f"run: |\n  {TSC_QA}\n  exit 0") == ["ts-no-typecheck"])
    expect("a step with continue-on-error: true is not a typecheck",
           ci(f"continue-on-error: true\nrun: {TSC_QA}") == ["ts-no-typecheck"])
    expect("a step with if: false is not a typecheck", ci(f"if: false\nrun: {TSC_QA}") == ["ts-no-typecheck"])
    expect("a step with if: ${{ false }} is not a typecheck", ci(f"if: ${{{{ false }}}}\nrun: {TSC_QA}") == ["ts-no-typecheck"])
    expect("a JOB with continue-on-error: true runs no typecheck",
           ci(f"run: {TSC_QA}", job="    continue-on-error: true\n") == ["ts-no-typecheck"])
    expect("a tsc in a trailing # comment is not run", ci(f"run: make test # {TSC_QA}") == ["ts-no-typecheck"])
    expect("a tsc in a comment line of a run block is not run",
           ci(f"run: |\n  # {TSC_QA}\n  echo ok") == ["ts-no-typecheck"])
    expect("a tsc in a trailing # comment on a config/ci.rb line is not run",
           rules({**no_ci, "config/ci.rb": 'step "Tests", "bin/rspec" # npm --prefix qa run typecheck\n'}) == ["ts-no-typecheck"])
    expect("a step key with a trailing YAML comment is still read (continue-on-error: true  # flaky)",
           ci(f"continue-on-error: true  # flaky\nrun: {TSC_QA}") == ["ts-no-typecheck"])
    expect("an echoed tsc is only printed", ci(f"run: echo {TSC_QA}") == ["ts-no-typecheck"])
    expect("a package script that swallows its own verdict is not a typecheck",
           rules({**no_ci, "qa/package.json": '{"scripts": {"typecheck": "tsc --noEmit -p e2e/tsconfig.json || true"}}',
                  ".github/workflows/ci.yml": _wf("run: npm --prefix qa run typecheck")}) == ["ts-no-typecheck"])
    expect("working-directory AFTER run: still sets the step's directory",
           ci("run: npx tsc --noEmit -p e2e/tsconfig.json\nworking-directory: qa") == [])
    expect("a job's defaults.run.working-directory sets the directory",
           ci("run: npx tsc --noEmit -p e2e/tsconfig.json",
              job="    defaults:\n      run:\n        working-directory: qa\n") == [])
    expect("a cd on its own line carries to the next line of the run block",
           ci("run: |\n  cd qa\n  npx tsc --noEmit -p e2e/tsconfig.json") == [])

    # ts-explicit-any
    for form in ("const x: any = 1;", "f(key as any);", "} catch (err: any) {", "const a = <any>b;", "let xs: any[] = [];",
                 "let ys: Array<any> = [];", "const h: Record<string, any> = {};", "const m = new Map<any, string>();",
                 "type T = any;", "function f<T = any>(x: T) {}", "let u: string | any;", "type K = keyof any;"):
        expect(f"explicit any is caught: {form}", rules({**base, "qa/e2e/b.spec.ts": form + "\n"}) == ["ts-explicit-any"])
    for form in ("const v = ok ? x as any : y;", "type C<T> = T extends string ? any : never;"):
        expect(f"an any before a ternary/conditional colon is a type: {form}",
               rules({**base, "qa/e2e/b.spec.ts": form + "\n"}) == ["ts-explicit-any"])
    expect("`any` as a key at a line start is not a type", rules({**base, "qa/e2e/b.spec.ts": "const o = {\n  any: 1,\n};\n"}) == [])
    expect("a decorator or private name spelled any is not a type",
           rules({**base, "qa/e2e/b.spec.ts": "class K { @any() m() {} #any = 1; }\n"}) == [])
    expect("an allow marker inside a STRING is not a declaration",
           rules({**base, "qa/e2e/b.spec.ts": 'const s = "// ts-strict: allow-any -- x"; f(x as any);\n'}) == ["ts-explicit-any"])
    expect("a postfix ++ before / is a division, so code after it is still read",
           rules({**base, "qa/e2e/b.spec.ts": "const h = i++ / 2; f(x as any); const w = v / 3;\n"}) == ["ts-explicit-any"])
    for ext in ("tsx", "mts", "cts"):
        expect(f"a .{ext} file is scanned", rules({**base, f"qa/e2e/b.{ext}": "const x: any = 1;\n"}) == ["ts-explicit-any"])
    expect("a suite of only .mts files is applicable", rules({"qa/e2e/a.mts": "export {};\n"}) is not None)
    expect("`any` as an object key is not a type", rules({**base, "qa/e2e/b.spec.ts": "const o = { any: 1, b: { any?: 2 } };\n"}) == [])
    expect("`.any` as a member is not a type (expect.any(Number))",
           rules({**base, "qa/e2e/b.spec.ts": "expect(x).toEqual(expect.any(Number)); obj.any;\n"}) == [])
    expect("`any` in a comment is not code",
           rules({**base, "qa/e2e/b.spec.ts": "// accepts it like any other claim\n/* gives { id: any } */\n"}) == [])
    expect("`any` in a string is not code", rules({**base, "qa/e2e/b.spec.ts": 'const s = "as any";\n'}) == [])
    expect("a word containing any is not any", rules({**base, "qa/e2e/b.spec.ts": "const company: Company = c; anyway(); $any;\n"}) == [])
    expect("a declared exception with a reason is silent",
           rules({**base, "qa/e2e/b.spec.ts": "// ts-strict: allow-any -- third-party type is wrong\nf(x as any);\n"}) == [])
    expect("a declaration with no reason is not one",
           rules({**base, "qa/e2e/b.spec.ts": "// ts-strict: allow-any --\nf(x as any);\n"}) == ["ts-explicit-any"])
    # THE SHAPE THAT BLANKED REAL CODE downstream: a template literal with an expression, then code.
    expect("code after a template literal with ${...} is still read",
           rules({**base, "qa/e2e/b.spec.ts": "const key = `${role}_session_cookie`;\nrequireFixtures(key as any);\n"}) == ["ts-explicit-any"])
    expect("an `any` inside a template's ${...} expression is code",
           rules({**base, "qa/e2e/b.spec.ts": "const s = `id ${(x as any).id}`;\n"}) == ["ts-explicit-any"])
    expect("an apostrophe inside a template does not start a string",
           rules({**base, "qa/e2e/b.spec.ts": "const s = `it's ${n}`;\nf(y as any);\n"}) == ["ts-explicit-any"])
    expect("a stray quote in a '...' string cannot run past its line",
           rules({**base, "qa/e2e/b.spec.ts": "const s = 'unterminated\nf(z as any);\n"}) == ["ts-explicit-any"])
    expect("a regex literal holding // inside a template's ${...} does not unbalance it (downstream shape)",
           rules({**base, "qa/e2e/b.spec.ts": "record({ shot: `TC${path.replace(/\\//g, \"-\")}`,\n});\nconst n = `on any of them`;\n"}) == [])
    expect("a quote inside a regex literal does not open a string",
           rules({**base, "qa/e2e/b.spec.ts": "const ok = s.match(/'/); f(x as any);\n"}) == ["ts-explicit-any"])
    expect("CONTROL: a division is not a regex, so code after it is still read",
           rules({**base, "qa/e2e/b.spec.ts": "const h = w / 2; f(x as any); const q = a / b;\n"}) == ["ts-explicit-any"])
    expect("catch (err: unknown) is the fix, and clean",
           rules({**base, "qa/e2e/b.spec.ts": "try { f() } catch (err: unknown) { g(err) }\n"}) == [])

    for f in fails:
        print(f"selftest FAIL: {f}")
    print(f"check_ts_strict selftest: {'FAILED' if fails else 'ok'} ({len(fails)} failure(s))")
    return 1 if fails else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="project root (default: cwd)")
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()
    root = Path(args.root).resolve()
    got = run(root)
    if got is None:
        print(f"not applicable — no TypeScript under {root / 'qa'}; this check examined nothing.")
        return 3
    findings, examined = got
    for f in findings:
        print(f"  {f}")
    print(f"\n{examined} TypeScript file(s) under qa/ examined; {len(findings)} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
