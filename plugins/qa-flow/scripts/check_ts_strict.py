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

THREE RULES, each on the suite under `qa/` (the tsconfig nearest its `.ts` files):

  ts-not-strict     the suite's tsconfig -- followed through relative `extends` -- does not set
                    `"compilerOptions": {"strict": true}`.
  ts-no-typecheck   no CI surface runs the type checker: no line invoking `tsc` with `--noEmit`,
                    `-p` or `--project`, in `.github/workflows/*.yml`, `config/ci.rb`, `bin/*`, or a
                    `package.json` script. Whole-line comments are skipped, because a CI file that
                    EXPLAINS why it runs tsc is not one that runs it.
  ts-explicit-any   an explicit `any` in code: `: any`, `as any`, `<any>`, `any[]`, `Array<any>`.
                    Comments and string literals are blanked first. A line may declare an
                    exception with a reason: `// ts-strict: allow-any -- <why>` on it or directly
                    above it; a declaration with no reason is not one.

NOT APPLICABLE (exit 3) when the project has no `.ts` under `qa/` -- reported, never a pass.

KNOWN LIMITS: comment/string blanking is a scanner's, not a parser's (a `//` inside a regex literal is
read as a comment start); `noUncheckedIndexedAccess` is doctrine advice, not a finding here, because
`strict` does not include it (CONFIRMED) and a gate requiring it would be red on day one for a reason
the owner did not state.

Stdlib only, no network. Exit 0 clean, 1 findings, 3 not applicable.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ANY = re.compile(r"(?::\s*any\b|\bas\s+any\b|<any>|\bany\s*\[\s*\]|Array<\s*any\s*>)")
ALLOW = re.compile(r"ts-strict:[ \t]*allow-any[ \t]*--[ \t]*\w")
TSC = re.compile(r"(?<![\w-])tsc\b[^\n]*?(?:--noEmit\b|\s-p\b|--project\b)")
COMMENT_LINE = re.compile(r"^\s*(?:#|//)")


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

    def scan_code(i: int, closing: str | None = None) -> int:
        depth = 0
        while i < n:
            c = text[i]
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
    """A tsconfig is JSON with comments and trailing commas allowed; strip both before parsing."""
    text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
    text = re.sub(r"(?m)^\s*//[^\n]*", "", text)
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return json.loads(text)


def is_strict(tsconfig: Path, depth: int = 0) -> bool:
    """`compilerOptions.strict` true here, or inherited through a relative `extends`."""
    cfg = _load_json(tsconfig)
    opts = cfg.get("compilerOptions", {})
    if "strict" in opts:
        return opts["strict"] is True
    parent = cfg.get("extends")
    if isinstance(parent, str) and parent.startswith(".") and depth < 8:
        target = (tsconfig.parent / parent).resolve()
        if target.suffix != ".json":
            target = target.with_suffix(".json")
        if target.is_file():
            return is_strict(target, depth + 1)
    return False


def typecheck_step(root: Path) -> str | None:
    """The first CI line that runs tsc as a type check, as `file:line`, or None."""
    surfaces = sorted((root / ".github/workflows").glob("*.y*ml")) + [root / "config/ci.rb"] + \
        sorted(p for p in (root / "bin").glob("*") if p.is_file())
    for p in surfaces:
        if not p.is_file():
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if not COMMENT_LINE.match(line) and TSC.search(line):
                return f"{p.relative_to(root)}:{n}"
    for p in sorted(root.glob("**/package.json")):
        if "node_modules" in p.parts:
            continue
        try:
            scripts = json.loads(p.read_text(encoding="utf-8")).get("scripts", {})
        except (json.JSONDecodeError, OSError):
            continue
        for name, cmd in scripts.items():
            if isinstance(cmd, str) and TSC.search(cmd):
                return f"{p.relative_to(root)} scripts.{name}"
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
    ts = sorted(p for p in (root / "qa").glob("**/*.ts") if "node_modules" not in p.parts) if (root / "qa").is_dir() else []
    if not ts:
        return None
    findings: list[str] = []
    configs = sorted(p for p in (root / "qa").glob("**/tsconfig*.json") if "node_modules" not in p.parts)
    if not configs:
        findings.append("qa: ts-not-strict — the suite has TypeScript but no tsconfig, so nothing makes it strict.")
    for cfg in configs:
        try:
            strict = is_strict(cfg)
        except (json.JSONDecodeError, OSError) as e:
            findings.append(f"{cfg.relative_to(root)}: ts-not-strict — unreadable tsconfig ({e}).")
            continue
        if not strict:
            findings.append(f"{cfg.relative_to(root)}: ts-not-strict — `compilerOptions.strict` is not true.")
    if typecheck_step(root) is None:
        findings.append("qa: ts-no-typecheck — no CI step runs `tsc --noEmit -p <suite>`; Playwright does not "
                        "type-check, so `strict` is enforced by nothing.")
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

    base = {"qa/e2e/tsconfig.json": STRICT, ".github/workflows/ci.yml": CI_YML,
            "qa/e2e/a.spec.ts": "const n: number = 1;\n"}
    expect("CONTROL: a strict, type-checked suite with no any is clean", rules(base) == [])
    expect("no TypeScript under qa/ is NOT APPLICABLE, not a pass", rules({"qa/e2e/a.spec.js": "x"}) is None)

    expect("a tsconfig without strict is caught",
           rules({**base, "qa/e2e/tsconfig.json": '{"compilerOptions": {"noEmit": true}}'}) == ["ts-not-strict"])
    expect("strict: false is caught", rules({**base, "qa/e2e/tsconfig.json": '{"compilerOptions": {"strict": false}}'}) == ["ts-not-strict"])
    expect("strict inherited through a relative extends counts",
           rules({**base, "qa/base.json": STRICT, "qa/e2e/tsconfig.json": '{"extends": "../base.json"}'}) == [])
    expect("TypeScript with no tsconfig at all is caught",
           rules({k: v for k, v in base.items() if k != "qa/e2e/tsconfig.json"}) == ["ts-not-strict"])

    expect("no typecheck step is caught", rules({k: v for k, v in base.items() if not k.startswith(".github")}) == ["ts-no-typecheck"])
    expect("a tsc mentioned only in a CI COMMENT is not a step",
           rules({**base, ".github/workflows/ci.yml": "steps:\n  # we should run tsc --noEmit -p qa/e2e\n"}) == ["ts-no-typecheck"])
    expect("a package.json typecheck script counts",
           rules({**{k: v for k, v in base.items() if not k.startswith(".github")},
                  "qa/package.json": '{"scripts": {"typecheck": "tsc --noEmit -p e2e"}}'}) == [])
    expect("a config/ci.rb step counts",
           rules({**{k: v for k, v in base.items() if not k.startswith(".github")},
                  "config/ci.rb": 'step "Types", "npx --prefix qa tsc --noEmit -p qa/e2e/tsconfig.json"\n'}) == [])

    for form in ("const x: any = 1;", "f(key as any);", "} catch (err: any) {", "const a = <any>b;", "let xs: any[] = [];",
                 "let ys: Array<any> = [];"):
        expect(f"explicit any is caught: {form}", rules({**base, "qa/e2e/b.spec.ts": form + "\n"}) == ["ts-explicit-any"])
    expect("`any` in a comment is not code",
           rules({**base, "qa/e2e/b.spec.ts": "// accepts it like any other claim\n/* gives { id: any } */\n"}) == [])
    expect("`any` in a string is not code", rules({**base, "qa/e2e/b.spec.ts": 'const s = "as any";\n'}) == [])
    expect("a word containing any is not any", rules({**base, "qa/e2e/b.spec.ts": "const company: Company = c;\n"}) == [])
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
