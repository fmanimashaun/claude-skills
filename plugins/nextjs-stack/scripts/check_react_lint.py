#!/usr/bin/env python3
"""Three official React lint rules that `eslint-config-next` ships OFF, run on their own (#2222).

A real run of the Next preset (eslint-config-next 16.4.2, eslint-plugin-react 7.37.5) missed three anti-patterns the React
skill names, and the plugin already has a rule for each. Turned on, each caught its fixture, including React 19's
`<Ctx value>` provider form (docs/evidence/audits/2026-10-21-react-frontend-claims.md, "Measured lint run"):

  react/no-array-index-key                 an array index as `key` (R4)
  react/jsx-no-constructed-context-values  an object or function built inline as a context provider's value (R15)
  react/no-danger                          `dangerouslySetInnerHTML` (R21): sanitise, or render as text

ONLY THESE THREE. The project's own lint step owns every other rule, so this runs the project's ESLint with a temporary
config: the project's Next preset for parsing (TypeScript, JSX), every preset rule switched off, these three on. The config is
written OUTSIDE the project and imports by absolute path, because a check must never write into the project it audits.

Usage:  python3 check_react_lint.py [project-dir] [--json]
        python3 check_react_lint.py --selftest
Exit 0 none · 1 findings · 2 ESLint ran but could not judge (crash, unparsable output) · 3 not applicable (no
package.json, or no eslint-config-next / eslint-plugin-react installed in the project's node_modules).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

RULES = ("react/no-array-index-key", "react/jsx-no-constructed-context-values", "react/no-danger")
REQUIRED = ("eslint", "eslint-config-next", "eslint-plugin-react")


class NotApplicable(Exception):
    pass


class Unjudgeable(Exception):
    pass


def flat_config(project: Path) -> str:
    """A flat config that parses like the project's Next preset and runs only RULES."""
    preset = project / "node_modules" / "eslint-config-next" / "dist" / "core-web-vitals.js"
    if not preset.is_file():
        preset = project / "node_modules" / "eslint-config-next" / "core-web-vitals.js"
    react = project / "node_modules" / "eslint-plugin-react" / "index.js"
    rules = ", ".join(f'"{r}": "error"' for r in RULES)
    return (f'import preset from {json.dumps(preset.as_uri())};\n'
            f'import react from {json.dumps(react.as_uri())};\n'
            "const quiet = (entry) => (entry && entry.rules ? { ...entry, rules: Object.fromEntries(Object.keys(entry.rules).map((k) => [k, \"off\"])) } : entry);\n"
            f"export default [...preset.map(quiet), {{ plugins: {{ react }}, rules: {{ {rules} }} }}];\n")


def findings_from(report: list[dict], project: Path) -> list[dict]:
    """Our three rules' messages, by file; anything else (a parse error included) is the project's lint step's business."""
    out = []
    for f in report:
        for m in f.get("messages", []):
            if m.get("ruleId") in RULES:
                rel = str(Path(f["filePath"]).resolve().relative_to(project.resolve())) if f.get("filePath") else "?"
                out.append({"rule": m["ruleId"], "file": rel, "line": m.get("line", 0), "message": m.get("message", "")})
    return out


def run(project: Path) -> list[dict]:
    if not (project / "package.json").is_file():
        raise NotApplicable(f"{project}: no package.json -- not a JavaScript project")
    missing = [p for p in REQUIRED if not (project / "node_modules" / p).is_dir()]
    if missing:
        raise NotApplicable(f"{project}: {', '.join(missing)} not installed in node_modules -- not a linted Next.js project")
    eslint = project / "node_modules" / ".bin" / "eslint"
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "eslint.react-architecture.config.mjs"
        cfg.write_text(flat_config(project))
        done = subprocess.run([str(eslint), "--config", str(cfg), "--format", "json", "--no-warn-ignored", "."],
                              cwd=project, capture_output=True, text=True, timeout=600)
    if done.returncode not in (0, 1):
        raise Unjudgeable(f"eslint exited {done.returncode}: {(done.stderr or done.stdout).strip()[:400]}")
    try:
        report = json.loads(done.stdout)
    except json.JSONDecodeError as exc:
        raise Unjudgeable(f"eslint printed no JSON report: {done.stdout.strip()[:200]}") from exc
    return findings_from(report, project)


def selftest() -> int:
    """The parts that need no installed ESLint: what the report becomes, and the config's shape. The real run is recorded in
    the evidence file; the checks.json row's own run proves it on a project that has ESLint installed."""
    failures = []
    root = Path("/p")
    report = [
        {"filePath": "/p/app/a.jsx", "messages": [{"ruleId": "react/no-array-index-key", "line": 2, "message": "index key"}]},
        {"filePath": "/p/app/b.jsx", "messages": [{"ruleId": "react-hooks/rules-of-hooks", "line": 1, "message": "other"}]},
        {"filePath": "/p/app/c.jsx", "messages": [{"ruleId": None, "line": 1, "message": "Parsing error"}]},
        {"filePath": "/p/app/d.jsx", "messages": [{"ruleId": "react/no-danger", "line": 3, "message": "danger"},
                                                  {"ruleId": "react/jsx-no-constructed-context-values", "line": 4, "message": "ctx"}]},
    ]
    got = sorted((f["file"], f["rule"]) for f in findings_from(report, root))
    want = [("app/a.jsx", "react/no-array-index-key"), ("app/d.jsx", "react/jsx-no-constructed-context-values"), ("app/d.jsx", "react/no-danger")]
    if got != want:
        failures.append(f"only our three rules become findings: expected {want}, got {got}")
    if findings_from([{"filePath": "/p/app/e.jsx", "messages": []}], root):
        failures.append("a clean file must give no finding")
    cfg = flat_config(Path("/proj"))
    for rule in RULES:
        if f'"{rule}": "error"' not in cfg:
            failures.append(f"the config must turn {rule} on")
    if '"off"' not in cfg:
        failures.append("the config must switch the preset's own rules off (the project's lint step owns them)")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            run(Path(tmp))
            failures.append("a project with no ESLint installed must be NOT APPLICABLE, not clean")
        except NotApplicable:
            pass
    with tempfile.TemporaryDirectory() as tmp:   # the exit-3 site in main(): an empty folder is not applicable (#1873)
        if main([tmp]) != 3:
            failures.append("a project with no package.json must exit 3, not applicable")
    for failure in failures:
        print(f"FAIL  {failure}")
    total = 3 + len(RULES) + 1 + 1
    print(f"check_react_lint selftest: {total - len(failures)} of {total} passed")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    project = Path(args.project)
    try:
        findings = run(project)
    except NotApplicable as exc:
        print(f"check_react_lint: not applicable -- {exc}")
        return 3
    except Unjudgeable as exc:
        print(f"check_react_lint: cannot judge -- {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"findings": findings}, indent=2))
    else:
        for f in findings:
            print(f"[{f['rule']}] {f['file']}:{f['line']}: {f['message']}")
        print(f"check_react_lint: {len(findings)} finding(s)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
