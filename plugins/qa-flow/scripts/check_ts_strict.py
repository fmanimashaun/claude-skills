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
                    which switches that one back off (typescriptlang.org/tsconfig#strict; CONFIRMED). An
                    `extends` that cannot be followed is reported as exactly that. A suite with TypeScript
                    and no tsconfig under `qa/` is a finding too.
  ts-no-typecheck   no CI line type-checks the SUITE. A line counts when it runs `tsc -p`/`--project` on a
                    path under `qa/` -- resolved from the root, a `cd <dir> &&`, or the step's
                    `working-directory:` -- or runs `npm|pnpm|yarn [--prefix DIR] run <name>` whose script
                    does. Surfaces: `.github/workflows/*.yml`, `config/ci.rb`, `bin/*`. A tsc on the app, a
                    tsc with no `-p`, a `package.json` script nothing runs, and a whole-line comment
                    EXPLAINING a tsc are not steps.
  ts-explicit-any   the keyword `any` in code, wherever it is a type: `: any`, `as any`, `Record<string, any>`,
                    `type T = any`, `<T = any>`, `string | any`, `keyof any`. Comments and string/template
                    text are blanked first; a member (`expect.any(Number)`, `obj.any`) and an object key
                    (`{ any: 1 }`) are not types. Files: `.ts`, `.tsx`, `.mts`, `.cts`. A line may declare
                    an exception with a reason: `// ts-strict: allow-any -- <why>` on it or directly above
                    it; a declaration with no reason is not one.

NOT APPLICABLE (exit 3) when the project has no TypeScript under `qa/` -- reported, never a pass.

KNOWN LIMITS. Blanking is a scanner's, not a parser's. A regex literal is recognised by the character
before its `/` (an operator, `(`, `,`, `=`, a line start -- where a value cannot end); after a keyword
(`return /'/`) it is read as a division, so a `//` in it starts a comment and a quote in it opens a string
to the end of the line -- either can hide a real `any` on that line. (Without the rule, downstream's
`path.replace(/\\//g, "-")` inside a template put the scanner out of phase and read prose as code.) JSX text in a `.tsx` is read as code, so the word "any" there is a false
finding (declare it). `any` directly before a `:` is taken for an object key, so a conditional type's
`? any : never` is missed. A package script is followed one level: a script that calls another script is
not traced. `noUncheckedIndexedAccess` is doctrine advice, not a finding, because `strict` does not
include it (CONFIRMED) and a gate requiring it would be red on day one for a reason the owner did not state.

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
ANY = re.compile(r"(?<![\w$.])any(?![\w$])(?!\s*\??\s*:)")
ALLOW = re.compile(r"ts-strict:[ \t]*allow-any[ \t]*--[ \t]*\w")
TSC = re.compile(r"(?<![\w-])tsc(?![\w-])(?P<args>[^\n;&|]*)")
PROJECT = re.compile(r"(?:^|\s)(?:-p|--project)(?:\s+|=)['\"]?(?P<path>[^\s'\"]+)")
RUNNER = re.compile(r"(?<![\w-])(?P<tool>npm|pnpm|yarn)\s(?P<args>[^\n;&|]*)")
DIR_FLAG = re.compile(r"(?:--prefix|--cwd|--dir|-C)(?:\s+|=)['\"]?(?P<dir>[^\s'\"]+)")
CD = re.compile(r"(?<![\w-])cd\s+['\"]?(?P<dir>[^\s'\";&]+)['\"]?\s*&&")
WORKDIR = re.compile(r"^\s*working-directory:\s*['\"]?(?P<dir>[^\s'\"#]+)")
NEW_STEP = re.compile(r"^\s*-\s")
# A `/` after one of these (or at the start) cannot be a division, so it opens a regex literal.
REGEX_AFTER = set("(,=:[!&|?{};+-*%<>~^")
COMMENT_LINE = re.compile(r"^\s*(?:#|//)")
JSONC = re.compile(r'"(?:\\.|[^"\\\n])*"|//[^\n]*|/\*.*?\*/', re.S)
TRAILING = re.compile(r'"(?:\\.|[^"\\\n])*"|,(?=\s*[}\]])')
# `strict` switches on a family; a member set false switches that one back off (typescriptlang.org/tsconfig#strict).
STRICT_FAMILY = ("alwaysStrict", "noImplicitAny", "noImplicitThis", "strictBindCallApply",
                 "strictBuiltinIteratorReturn", "strictFunctionTypes", "strictNullChecks",
                 "strictPropertyInitialization", "useUnknownInCatchVariables")


def _blank(text: str) -> str:
    """Comments and string/template TEXT replaced by spaces, newlines kept, so a finding's line number
    is the real one. A character scanner, not a regex: sequential quote-pairing went out of phase on
    a template literal (`${role}_session_cookie`) and blanked twenty lines of real code, `as any`
    included -- found on the first downstream run. `${...}` inside a template is scanned as CODE, and a
    '/" string ends at a newline (JavaScript forbids one there), so a stray quote cannot run away."""
    out = list(text)
    n = len(text)
    i = 0
    stack: list[str] = []            # "code" frames opened by `${` inside a template

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            if out[k] != "\n":
                out[k] = " "

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
                prev = c
            if c == "/" and i + 1 < n and text[i + 1] not in "/*" and (not prev or prev in REGEX_AFTER):
                e = scan_regex(i)
                if e is not None:
                    i, prev = e, "x"
                    continue
            if c == "/" and i + 1 < n and text[i + 1] == "/":
                e = text.find("\n", i)
                e = n if e == -1 else e
                blank(i, e)
                i = e
            elif c == "/" and i + 1 < n and text[i + 1] == "*":
                e = text.find("*/", i + 2)
                e = n if e == -1 else e + 2
                blank(i, e)
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
    return "".join(out)


def _load_json(path: Path) -> dict:
    """A tsconfig is JSONC: comments and trailing commas are legal. Both are removed by an alternation that
    matches a whole string FIRST and keeps it, so `"@fixtures/*"` or `"https://x"` is never read as a comment."""
    text = JSONC.sub(lambda m: m.group(0) if m.group(0).startswith('"') else "", path.read_text(encoding="utf-8"))
    return json.loads(TRAILING.sub(lambda m: m.group(0) if m.group(0).startswith('"') else "", text))


class Unfollowed(Exception):
    """An `extends` this script cannot resolve, so strictness cannot be read -- a finding of its own kind."""


def _resolve_extends(tsconfig: Path, spec: str) -> Path:
    if spec.startswith("."):
        candidates = [tsconfig.parent / spec]
    else:                             # a package: node_modules, nearest first
        candidates = [d / "node_modules" / spec for d in [tsconfig.parent, *tsconfig.parent.parents]]
    for c in candidates:
        for t in (c, c.with_name(c.name + ".json"), c / "tsconfig.json"):
            if t.is_file():
                return t.resolve()
    raise Unfollowed(spec)


def effective_options(tsconfig: Path, depth: int = 0) -> dict:
    """`compilerOptions` as the compiler sees them: each `extends` (a string, or an array whose later entries
    win) merged first, then this file's own options over the top."""
    cfg = _load_json(tsconfig)
    parents = cfg.get("extends") or []
    merged: dict = {}
    if depth < 8:
        for spec in [parents] if isinstance(parents, str) else parents:
            merged.update(effective_options(_resolve_extends(tsconfig, spec), depth + 1))
    merged.update(cfg.get("compilerOptions") or {})
    return merged


def not_strict_reason(tsconfig: Path) -> str | None:
    """Why this tsconfig is not strict, or None when it is."""
    try:
        opts = effective_options(tsconfig)
    except Unfollowed as e:
        return (f"`extends` {str(e)!r} could not be followed (install the suite's dependencies before this gate, "
                f"or set `\"strict\": true` in this file), so its strictness cannot be read")
    if opts.get("strict") is not True:
        return "`compilerOptions.strict` is not true"
    off = [k for k in STRICT_FAMILY if opts.get(k) is False]
    if off:
        return f"`strict` is true but {', '.join(f'`{k}`' for k in off)} is set false, which switches it back off"
    return None


def _under_qa(cwd: str, path: str) -> bool:
    rel = posixpath.normpath(posixpath.join(cwd, path))
    return rel == "qa" or rel.startswith("qa/")


def _checks_suite(cmd: str, cwd: str) -> bool:
    """`cmd`, run from `cwd` (relative to the root), invokes tsc on a project under qa/."""
    for m in TSC.finditer(cmd):
        pre = cmd[:m.start()]
        here = posixpath.join(cwd, *[c.group("dir") for c in CD.finditer(pre)])
        p = PROJECT.search(m.group("args"))
        if p and _under_qa(here, p.group("path")):
            return True
    return False


def _scripts(root: Path, pkg_dir: str) -> dict:
    try:
        scripts = json.loads((root / pkg_dir / "package.json").read_text(encoding="utf-8")).get("scripts", {})
    except (json.JSONDecodeError, OSError, AttributeError):
        return {}
    return scripts if isinstance(scripts, dict) else {}


def _runs_suite_script(root: Path, cmd: str, cwd: str) -> str | None:
    """`npm|pnpm|yarn [--prefix DIR] run NAME` in `cmd` whose package script type-checks the suite."""
    for m in RUNNER.finditer(cmd):
        here = posixpath.join(cwd, *[c.group("dir") for c in CD.finditer(cmd[:m.start()])])
        args = m.group("args")
        d = DIR_FLAG.search(args)
        pkg = posixpath.normpath(posixpath.join(here, d.group("dir")) if d else here)
        words = [w for w in DIR_FLAG.sub(" ", args).split() if not w.startswith("-")]
        if words[:1] in (["run"], ["run-script"]):
            words = words[1:]
        elif m.group("tool") == "npm":
            continue                  # npm runs a script only through `run`
        script = _scripts(root, pkg).get(words[0]) if words else None
        if isinstance(script, str) and _checks_suite(script, pkg):
            return f"{pkg}/package.json scripts.{words[0]}"
    return None


def typecheck_step(root: Path) -> str | None:
    """The first CI line that type-checks the SUITE -- `tsc -p <path under qa/>` directly, or a package script
    doing so that the line runs -- as `file:line`, or None. A tsc on the app, or a script nothing runs, is not one."""
    surfaces = sorted((root / ".github/workflows").glob("*.y*ml")) + [root / "config/ci.rb"] + \
        sorted(p for p in (root / "bin").glob("*") if p.is_file())
    for p in surfaces:
        if not p.is_file():
            continue
        workdir = "."
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if NEW_STEP.match(line):
                workdir = "."
            w = WORKDIR.match(line.lstrip("- ")) if p.suffix in (".yml", ".yaml") else None
            if w:
                workdir = w.group("dir")
            if COMMENT_LINE.match(line):
                continue
            if _checks_suite(line, workdir):
                return f"{p.relative_to(root)}:{n}"
            via = _runs_suite_script(root, line, workdir)
            if via:
                return f"{p.relative_to(root)}:{n} (via {via})"
    return None


def explicit_anys(rel: str, source: str) -> list[str]:
    out = []
    raw = source.split("\n")
    for n, line in enumerate(_blank(source).split("\n")):
        if not ANY.search(line):
            continue
        if ALLOW.search(raw[n]) or (n > 0 and ALLOW.search(raw[n - 1])):
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
CI_YML = "jobs:\n  qa:\n    steps:\n      # tsc --noEmit is explained here but run below\n      - run: npx --prefix qa tsc --noEmit -p qa/e2e/tsconfig.json\n"


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

    base = {"qa/e2e/tsconfig.json": STRICT, ".github/workflows/ci.yml": CI_YML,
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
           rules({**no_ci, "config/ci.rb": 'step "Types", "npx --prefix qa tsc --noEmit -p qa/e2e/tsconfig.json"\n'}) == [])

    # ts-explicit-any
    for form in ("const x: any = 1;", "f(key as any);", "} catch (err: any) {", "const a = <any>b;", "let xs: any[] = [];",
                 "let ys: Array<any> = [];", "const h: Record<string, any> = {};", "const m = new Map<any, string>();",
                 "type T = any;", "function f<T = any>(x: T) {}", "let u: string | any;", "type K = keyof any;"):
        expect(f"explicit any is caught: {form}", rules({**base, "qa/e2e/b.spec.ts": form + "\n"}) == ["ts-explicit-any"])
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
