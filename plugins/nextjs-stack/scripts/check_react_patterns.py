#!/usr/bin/env python3
"""React / Next.js App Router patterns that the official lint does not catch (#2222).

nextjs-stack's React frontend architecture (`skills/react`) states patterns that hold and anti-patterns that bite. Most of
the mechanical ones are caught upstream: `eslint-config-next` turns on eslint-plugin-react-hooks' recommended rules
(components defined inside components, setState in an Effect, impure keys), `react/jsx-key` and `@next/next/no-img-element`,
and checks.json turns on three more that are off by default. This script covers only what a REAL run of that config was
measured to miss (docs/evidence/audits/2026-10-21-react-frontend-claims.md, "Measured lint run"):

  use-client-route-file   `"use client"` on an App Router layout, page, template or default file: the whole route becomes
                          a client subtree, where the skill's rule is the smallest interactive leaf (R8). A client route
                          can be a deliberate trade-off, so the file may DECLARE it -- a comment
                          `react-architecture: client-route -- <reason>` with a non-empty reason -- and the declaration is
                          the enforcement (#2222, the owner's "everything enforced": a required declaration, verified here).
  fetch-in-effect         `fetch(` inside a `useEffect` callback in a client module: in the App Router the data belongs
                          in a Server Component (R16). Reported with "and no cleanup" when the callback returns nothing,
                          so a stale response is not ignored.
  internal-anchor         `<a href="/...">` to an internal route in an App Router file: a full page load instead of
                          `<Link>` (R6). `@next/next/no-html-link-for-pages` only reads a `pages/` directory.

A GATE (#2222, owner ruling: "everything must be enforced"). Any finding is exit 1. The rule that has legitimate
exceptions (a client route) is satisfied by declaring the exception with a reason, never by a silent pass. A source tree it
could not read is exit 2. Measured on 27 Next.js apps (docs/evidence/audits/2026-10-21-react-frontend-claims.md): a rule
that fired on correct code there ("use client" with no visible client need -- a third-party import can be the reason) was
dropped from this script and moved to the recorded-review set.

WHERE IT LOOKS. Route files are judged under `app/` / `src/app/`. The other rules read every source file of the project
(components usually live outside `app/`), skipping build output and `node_modules`.

Usage:  python3 check_react_patterns.py [project-dir] [--json]
        python3 check_react_patterns.py --selftest
Exit 0 nothing found · 1 findings · 2 cannot judge (an unreadable file) · 3 not applicable (no app/ or src/app/).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

SOURCE_SUFFIXES = (".tsx", ".jsx", ".ts", ".js")
ROUTE_FILES = {"layout", "page", "template", "default"}
SKIP_DIRS = {"node_modules", ".next", "dist", "build", "out", ".git"}

DIRECTIVE = re.compile(r"""\A(?:\s|//[^\n]*\n|/\*.*?\*/)*(['"])use client\1""", re.S)
CLIENT_ROUTE_DECLARED = re.compile(r"react-architecture:[ \t]*client-route[ \t]*(?:--|—|:)[ \t]*\S")   # the reason on the SAME line
EFFECT_CALL = re.compile(r"\buseEffect\s*\(")
INTERNAL_ANCHOR = re.compile(r"""<a\b[^>]*\bhref\s*=\s*\{?\s*(['"`])/(?!/)""")


class Unjudgeable(Exception):
    """The project cannot be judged -- never report clean for it (exit 2)."""


class NotApplicable(Exception):
    """Not an App Router project: the check does not apply (exit 3, which project_gates grades n/a, never pass or fail)."""


def strip_comments(text: str) -> str:
    """Blank out // and /* */ comments, NOT the same characters inside a string or template literal: a regex alone
    erased `href="//cdn..."` and every `https://` as if they were comments (found by the mutation guard)."""
    out, i, quote, n = [], 0, None, len(text)
    while i < n:
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
        elif ch in "'\"`":
            quote = ch
            out.append(ch)
            i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j]))
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def call_body(text: str, open_paren: int) -> str:
    """The text between `(` at `open_paren` and its matching `)` (strings and template literals skipped)."""
    depth, i, quote = 0, open_paren, None
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren + 1:i]
        i += 1
    return text[open_paren + 1:]


def app_dirs(project: Path) -> list[Path]:
    found = [d for d in (project / "app", project / "src" / "app") if d.is_dir()]
    if not found:
        raise NotApplicable(f"{project}: no app/ or src/app/ directory -- not an App Router project")
    return found


def source_files(root: Path) -> list[Path]:
    out = []
    for path in sorted(root.rglob("*")):
        if path.suffix in SOURCE_SUFFIXES and path.is_file() and not (SKIP_DIRS & set(path.parts)):
            out.append(path)
    return out


def judge_file(path: Path, rel: str, in_app: bool) -> list[dict]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Unjudgeable(f"{rel}: unreadable ({exc})") from exc
    findings: list[dict] = []
    code = strip_comments(raw)
    client = bool(DIRECTIVE.match(raw))
    stem = path.name.split(".")[0]
    if in_app and client and stem in ROUTE_FILES and not CLIENT_ROUTE_DECLARED.search(raw):
        findings.append({"rule": "use-client-route-file", "file": rel,
                         "message": f"`\"use client\"` on a route {stem} file makes the whole route a client subtree: move the "
                                    "directive to the smallest interactive leaf (R8), or declare the trade-off with a comment "
                                    "`react-architecture: client-route -- <reason>`"})
    if client:
        for m in EFFECT_CALL.finditer(code):
            body = call_body(code, m.end() - 1)
            if re.search(r"\bfetch\s*\(", body):
                no_cleanup = not re.search(r"\breturn\b", body)
                findings.append({"rule": "fetch-in-effect", "file": rel,
                                 "message": "`fetch` inside `useEffect` in a client module: fetch in a Server Component instead (R16)"
                                            + ("; and the Effect has no cleanup, so a stale response is not ignored" if no_cleanup else "")})
    if INTERNAL_ANCHOR.search(code):
        findings.append({"rule": "internal-anchor", "file": rel,
                         "message": "`<a href=\"/...\">` to an internal route: a full page load; use `<Link>` from next/link (R6)"})
    return findings


def judge(project: Path) -> list[dict]:
    apps = app_dirs(project)   # an App Router project, or unjudgeable
    findings: list[dict] = []
    for path in source_files(project):
        in_app = any(app in path.parents for app in apps)
        findings.extend(judge_file(path, str(path.relative_to(project)), in_app))
    return findings


def selftest() -> int:
    cases = [
        ("a client layout is reported", {"app/layout.tsx": '"use client";\nexport default function L({children}){return children}'}, {"use-client-route-file"}),
        ("a server layout is not", {"app/layout.tsx": "export default function L({children}){return children}"}, set()),
        ("a client page DECLARING its trade-off passes", {"app/page.tsx": '"use client";\n// react-architecture: client-route -- a form-heavy page\nexport default function P(){return null}'}, set()),
        ("NEAR MISS: a declaration with no reason does not pass", {"app/page.tsx": '"use client";\n// react-architecture: client-route --\nexport default function P(){return null}'}, {"use-client-route-file"}),
        ("NEAR MISS: a client page.tsx OUTSIDE app/ is not a route file", {"app/x.tsx": "export const a = 1", "components/page.tsx": '"use client";\nexport default function P(){return null}'}, set()),
        ("a fetch in an effect OUTSIDE app/ (components/) is reported", {"app/x.tsx": "export const a = 1", "components/p.tsx": "'use client'\nimport {useEffect} from 'react'\nexport function P(){useEffect(()=>{fetch('/a')},[]);return null}"}, {"fetch-in-effect"}),
        ("NEAR MISS: the directive inside a comment is not a directive", {"app/layout.tsx": "// 'use client'\nexport default function L({children}){return children}"}, set()),
        ("a fetch in an effect with no cleanup is reported", {"app/p.tsx": "'use client'\nimport {useEffect} from 'react'\nexport function P(){useEffect(()=>{fetch('/a').then(r=>r)},[]);return null}"}, {"fetch-in-effect"}),
        ("a fetch in an effect WITH cleanup is still reported, without the cleanup note", {"app/p.tsx": "'use client'\nimport {useEffect} from 'react'\nexport function P(){useEffect(()=>{let x=false;fetch('/a');return ()=>{x=true}},[]);return null}"}, {"fetch-in-effect"}),
        ("NEAR MISS: an effect with no fetch is not", {"app/p.tsx": "'use client'\nimport {useEffect} from 'react'\nexport function P(){useEffect(()=>{document.title='x'},[]);return null}"}, set()),
        ("NEAR MISS: fetch in a server component is not fetch-in-effect", {"app/page.tsx": "export default async function P(){const r=await fetch('https://x');return null}"}, set()),
        ("an internal anchor is reported", {"app/n.tsx": 'export function N(){return <a href="/dashboard">d</a>}'}, {"internal-anchor"}),
        ("NEAR MISS: an external anchor is not", {"app/n.tsx": 'export function N(){return <a href="https://x.com">d</a>}'}, set()),
        ("NEAR MISS: a protocol-relative anchor is not internal", {"app/n.tsx": 'export function N(){return <a href="//cdn.x.com/f">d</a>}'}, set()),
        ("NEAR MISS: a Link to an internal route is not", {"app/n.tsx": "import Link from 'next/link'\nexport function N(){return <Link href='/dashboard'>d</Link>}"}, set()),
    ]
    failures = []
    for label, files, expected in cases:
        with tempfile.TemporaryDirectory() as tmp:
            for rel, text in files.items():
                p = Path(tmp) / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text)
            got = {f["rule"] for f in judge(Path(tmp))}
        if got != expected:
            failures.append(f"{label}: expected {sorted(expected)}, got {sorted(got)}")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            judge(Path(tmp))
            failures.append("a project with no app/ directory must be NOT APPLICABLE, not clean")
        except NotApplicable:
            pass
    for failure in failures:
        print(f"FAIL  {failure}")
    total = len(cases) + 1
    print(f"check_react_patterns selftest: {total - len(failures)} of {total} passed")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        findings = judge(Path(args.project))
    except NotApplicable as exc:
        print(f"check_react_patterns: not applicable -- {exc}")
        return 3
    except Unjudgeable as exc:
        print(f"check_react_patterns: cannot judge -- {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"findings": findings}, indent=2))
    else:
        for f in findings:
            print(f"[{f['rule']}] {f['file']}: {f['message']}")
        print(f"check_react_patterns: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
