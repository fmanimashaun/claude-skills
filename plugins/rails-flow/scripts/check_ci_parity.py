#!/usr/bin/env python3
"""The security steps a project runs locally exist in its CI workflow, and the pipeline fails closed (#2124, part of #2115).

Run:  check_ci_parity.py [--root DIR]
      check_ci_parity.py --selftest
Exit: 0 every rule holds (or is exempted with a reason) · 1 finding(s) · 2 unusable (a workflow or the exemption file is unreadable)
      3 not applicable (no Gemfile: not a Rails project)

WHY. Brakeman and bundler-audit ran "if installed" and nothing said the project's CI runs them: a gate that exists locally and not in CI protects
nobody. Retask measured it (R6): `config/ci.rb` runs `bin/importmap audit` and `brakeman --exit-on-warn --exit-on-error`, and its GitHub `security` job
runs neither the audit nor those flags; it had no secret scan at all (R5). Static and offline: it reads `config/ci.rb`, `bin/ci` and
`.github/workflows/*.yml` and runs nothing.

THE RULES, each a finding id:
  bundler-audit, importmap-audit, brakeman   a workflow step runs the tool (importmap only when `config/importmap.rb` exists or `bin/ci` runs it)
  brakeman-flags                             every `--exit-on-warn` / `--exit-on-error` the LOCAL brakeman command carries is on the CI one
  secret-scan                                a workflow step runs gitleaks or trufflehog
  secret-scan-history                        in a job that checks out with `fetch-depth: 0` (the whole history, not the tip)
  secret-scan-push                           in a workflow triggered on `push` (every push, not only pull requests)
  dependency-review                          `actions/dependency-review-action`, in a workflow triggered on `pull_request`
  codeql                                     `github/codeql-action/analyze`
  gates                                      some step runs `project_gates.py` (the toolchain's own checks)
  fail-closed                                no security step has `continue-on-error: true`, `|| true`, `|| exit 0` or `; true`, and no job holding one does
Parity (`config/ci.rb` or `bin/ci` has it, no workflow does) and the baseline (the template's jobs) are the same rule, reported once, with where the
local step is when there is one.

EXEMPTIONS are declared, never inferred: `.rails-flow/ci-parity.json`  {"exempt": [{"rule": "codeql", "reason": "Ruby only, unsupported here (named)"}]}
An entry without a rule or a reason, for an unknown rule, or for a rule that already holds, is itself a finding.

LIMITS. A text reading of YAML (no parser, stdlib only): a step is a `- ` list item and its deeper-indented lines, a comment line is ignored, a tool named
inside a `run: |` that never executes it (an `if: false`, an `echo`) counts. It proves the step is there and cannot fail silently, not that the job is
reached, that its runner is enabled, or that the tool finds anything. It reads GitHub Actions only.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RULES = ("bundler-audit", "importmap-audit", "brakeman", "brakeman-flags", "secret-scan", "secret-scan-history", "secret-scan-push",
         "dependency-review", "codeql", "gates", "fail-closed")
EXEMPT_FILE = Path(".rails-flow/ci-parity.json")
TOOLS = {
    "bundler-audit": re.compile(r"\bbundler-audit\b"),
    "importmap-audit": re.compile(r"\bimportmap\s+audit\b"),
    "brakeman": re.compile(r"\bbrakeman\b"),
    "secret-scan": re.compile(r"\b(?:gitleaks|trufflehog)\b"),
    "dependency-review": re.compile(r"\bactions/dependency-review-action\b"),
    "codeql": re.compile(r"\bgithub/codeql-action/analyze\b"),
    "gates": re.compile(r"\bproject_gates\.py\b"),
}
SECURITY_TOOLS = ("bundler-audit", "importmap-audit", "brakeman", "secret-scan", "dependency-review", "codeql")
WEAK = re.compile(r"continue-on-error:\s*(?:true|\$\{\{[^}]*\}\})|\|\|\s*(?:true|exit\s+0|:)\b|;\s*true\s*$", re.M)
FLAGS = ("--exit-on-warn", "--exit-on-error")
STEP = re.compile(r"^(\s*)-\s+\S")


class Unusable(RuntimeError):
    pass


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Unusable(f"{path} is unreadable: {exc}") from exc


def strip_comments(text: str) -> str:
    """Drop whole-line comments (a `#` in the middle of a line may be inside a string or a URL: it stays)."""
    return "\n".join("" if ln.lstrip().startswith("#") else ln for ln in text.splitlines())


def local_commands(root: Path) -> list[tuple[str, int, str]]:
    """(file, line, command text) for every uncommented line of `config/ci.rb` and `bin/ci` that names a security tool."""
    out = []
    for rel in ("config/ci.rb", "bin/ci"):
        p = root / rel
        if not p.is_file():
            continue
        for n, ln in enumerate(_read(p).splitlines(), 1):
            if ln.lstrip().startswith("#"):
                continue
            if any(TOOLS[t].search(ln) for t in ("bundler-audit", "importmap-audit", "brakeman", "secret-scan")):
                out.append((rel, n, ln.strip()))
    return out


def jobs(text: str) -> list[tuple[str, str, list[str]]]:
    """(job name, job text, step texts) for a workflow, by indentation. Comment lines are already stripped."""
    lines = text.splitlines()
    out: list[tuple[str, str, list[str]]] = []
    i = next((k for k, ln in enumerate(lines) if re.match(r"^jobs\s*:", ln)), None)
    if i is None:
        return out
    cur_name, cur_lines = "", []
    for ln in lines[i + 1:]:
        if ln.strip() and not ln.startswith(" "):
            break
        m = re.match(r"^  ([\w.-]+)\s*:\s*$", ln)
        if m:
            if cur_name:
                out.append((cur_name, "\n".join(cur_lines), _steps(cur_lines)))
            cur_name, cur_lines = m.group(1), []
        elif cur_name:
            cur_lines.append(ln)
    if cur_name:
        out.append((cur_name, "\n".join(cur_lines), _steps(cur_lines)))
    return out


def _steps(job_lines: list[str]) -> list[str]:
    steps: list[list[str]] = []
    indent = None
    for ln in job_lines:
        m = STEP.match(ln)
        if m and (indent is None or len(m.group(1)) == indent):
            indent = len(m.group(1)) if indent is None else indent
            steps.append([ln])
        elif steps and (not ln.strip() or len(ln) - len(ln.lstrip()) > (indent or 0)):
            steps[-1].append(ln)
    return ["\n".join(s) for s in steps]


def triggers(text: str) -> set[str]:
    """The event names in the workflow's `on:` block (map, list or inline list)."""
    out: set[str] = set()
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        m = re.match(r"^(?:on|\"on\"|'on')\s*:\s*(.*)$", ln)
        if not m:
            continue
        rest = m.group(1).strip()
        if rest:
            out |= {w for w in re.findall(r"[a-z_]+", rest) if w}
            return out
        for nxt in lines[i + 1:]:
            if nxt.strip() and not nxt.startswith(" "):
                break
            mm = re.match(r"^  ([a-z_]+)\s*:", nxt) or re.match(r"^\s*-\s*([a-z_]+)\s*$", nxt)
            if mm:
                out.add(mm.group(1))
        return out
    return out


def load_exempt(root: Path) -> tuple[dict[str, str], list[str]]:
    path = root / EXEMPT_FILE
    if not path.is_file():
        return {}, []
    try:
        entries = json.loads(_read(path)).get("exempt", [])
    except (ValueError, AttributeError) as exc:
        return {}, [f"  [bad-exemption] {EXEMPT_FILE} is unreadable: {exc}"]
    exempt: dict[str, str] = {}
    problems: list[str] = []
    for e in entries:
        rule, reason = (e or {}).get("rule"), ((e or {}).get("reason") or "").strip()
        if not rule or not reason:
            problems.append(f"  [bad-exemption] {EXEMPT_FILE}: every exemption needs a rule and a reason, got {e!r}")
        elif rule not in RULES:
            problems.append(f"  [bad-exemption] {EXEMPT_FILE}: unknown rule {rule!r} (rules: {', '.join(RULES)})")
        else:
            exempt[rule] = reason
    return exempt, problems


def check(root: Path) -> tuple[int, list[str]]:
    if not (root / "Gemfile").is_file():
        return 3, ["not applicable: no Gemfile"]
    try:
        flows = {}
        wdir = root / ".github" / "workflows"
        for p in sorted(wdir.glob("*.y*ml")) if wdir.is_dir() else []:
            flows[p.relative_to(root).as_posix()] = strip_comments(_read(p))
        local = local_commands(root)
        exempt, problems = load_exempt(root)
    except Unusable as exc:
        return 2, [f"UNUSABLE: {exc}"]

    all_jobs = [(f, name, jtext, steps) for f, text in flows.items() for name, jtext, steps in jobs(text)]
    all_steps = [(f, name, jtext, st) for f, name, jtext, steps in all_jobs for st in steps]
    ons = {f: triggers(text) for f, text in flows.items()}
    failing: dict[str, str] = {}

    def where_local(tool: str) -> str:
        for rel, n, cmd in local:
            if TOOLS[tool].search(cmd):
                return f" (`{rel}:{n}` runs it locally)"
        return ""

    def has(tool: str) -> list[tuple[str, str, str, str]]:
        return [s for s in all_steps if TOOLS[tool].search(s[3])]

    need_importmap = (root / "config/importmap.rb").is_file() or any(TOOLS["importmap-audit"].search(c) for _, _, c in local)
    for tool in ("bundler-audit", "importmap-audit", "brakeman"):
        if tool == "importmap-audit" and not need_importmap:
            continue
        if not has(tool):
            failing[tool] = f"no workflow step runs `{tool.replace('-', ' ') if tool == 'importmap-audit' else tool}`{where_local(tool)}"

    local_brakeman = next((c for _, _, c in local if TOOLS["brakeman"].search(c)), "")
    ci_brakeman = " ".join(s[3] for s in has("brakeman"))
    if local_brakeman and has("brakeman"):
        lost = [f for f in FLAGS if f in local_brakeman and f not in ci_brakeman]
        if lost:
            failing["brakeman-flags"] = f"the local brakeman command carries {', '.join(lost)} and no workflow brakeman step does: the two runs are not the same command"

    scans = has("secret-scan")
    if not scans:
        failing["secret-scan"] = "no workflow step runs a secret scanner (gitleaks or trufflehog): a committed credential is found by nobody"
    else:
        if not any("fetch-depth: 0" in s[2] for s in scans):
            failing["secret-scan-history"] = "the secret scan's job does not check out with `fetch-depth: 0`, so it reads the tip, not the history"
        if not any("push" in ons[s[0]] for s in scans):
            failing["secret-scan-push"] = "the secret scan's workflow is not triggered on `push`, so a branch is scanned only when a pull request opens"
    dr = has("dependency-review")
    if not dr or not any("pull_request" in ons[s[0]] for s in dr):
        failing["dependency-review"] = "no `actions/dependency-review-action` step in a workflow triggered on `pull_request`"
    if not has("codeql"):
        failing["codeql"] = "no `github/codeql-action/analyze` step"
    if not has("gates"):
        failing["gates"] = "no step runs `project_gates.py`: the toolchain's own checks never run in CI (`/rails-flow:setup-flow` scaffolds the job)"
    weak = [(f, name) for f, name, jtext, st in all_steps
            if any(TOOLS[t].search(st) for t in SECURITY_TOOLS) and (WEAK.search(st) or re.search(r"^\s{4}continue-on-error:\s*true", jtext, re.M))]
    if weak:
        failing["fail-closed"] = "a security step cannot fail: " + ", ".join(f"{f} job `{n}`" for f, n in sorted(set(weak)))

    findings = list(problems)
    for rule in RULES:
        if rule in failing and rule not in exempt:
            findings.append(f"  [{rule}] {failing[rule]}")
    for rule in sorted(set(exempt) - set(failing)):
        findings.append(f"  [stale-exemption] {rule} is exempted in {EXEMPT_FILE} but the rule holds")
    if findings:
        return 1, [f"{len(findings)} finding(s) in the CI security pipeline:", *findings]
    held = len(RULES) - len(failing)
    return 0, [f"CI security pipeline: {held} of {len(RULES)} rules hold" + (f", {len(failing)} exempted with a reason" if failing else "")]


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    ap = argparse.ArgumentParser(prog="check_ci_parity.py", description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", type=Path)
    a = ap.parse_args(argv)
    code, lines = check(a.root.resolve())
    print("\n".join(lines), file=sys.stderr if code == 2 else sys.stdout)
    return code


LOCAL_CI = """CI.run do
  step "Security: Gem audit", "bin/bundler-audit"
  step "Security: Importmap vulnerability audit", "bin/importmap audit"
  step "Security: Brakeman code analysis", "bin/brakeman --quiet --no-pager --exit-on-warn --exit-on-error"
end
"""
GATES_JOB = """  doctrine:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 .claude-toolchain/plugins/rails-flow/scripts/project_gates.py
"""


def selftest() -> int:
    import tempfile

    bad = 0
    template = Path(__file__).resolve().parent.parent / "templates" / "ci-security.yml"

    def project(files: dict[str, str]) -> Path:
        d = Path(tempfile.mkdtemp(prefix="railsflow-ciparity-"))
        base = {"Gemfile": "source 'https://rubygems.org'\n", "config/importmap.rb": "pin 'x'\n", "config/ci.rb": LOCAL_CI,
                ".github/workflows/security.yml": template.read_text(encoding="utf-8"), ".github/workflows/ci.yml": "name: CI\non: pull_request\njobs:\n" + GATES_JOB}
        base.update(files)
        for rel, body in base.items():
            if body is None:
                continue
            (d / rel).parent.mkdir(parents=True, exist_ok=True)
            (d / rel).write_text(body, encoding="utf-8")
        return d

    def sec(**sub: str) -> str:
        t = template.read_text(encoding="utf-8")
        for old, new in sub.values():
            assert old in t, old
            t = t.replace(old, new, 1)
        return t

    def case(label: str, files: dict[str, str], want: int, needle: str = "") -> None:
        nonlocal bad
        code, lines = check(project(files))
        text = "\n".join(lines)
        if code != want or (needle and needle not in text):
            bad += 1
            print(f"FAIL {label}: expected exit {want} naming `{needle}`, got {code}: {text[:300]}")

    ws = ".github/workflows/security.yml"
    case("the shipped template plus a gates job passes (the template and the check agree)", {}, 0, "rules hold")
    case("no Gemfile is not applicable, never a pass", {"Gemfile": None}, 3, "no Gemfile")
    case("no workflow at all fails every rule", {ws: None, ".github/workflows/ci.yml": None}, 1, "no workflow step runs `bundler-audit`")
    case("the importmap audit local but not in CI is the R6 finding",
         {ws: sec(a=("      - name: Importmap advisories\n        run: bin/importmap audit\n", "      - name: Importmap advisories\n        run: echo skipped\n"))}, 1, "importmap")
    case("brakeman without the local exit flags is a finding",
         {ws: sec(a=("bin/brakeman --quiet --no-pager --exit-on-warn --exit-on-error", "bin/brakeman --quiet --no-pager"))}, 1, "brakeman-flags")
    case("no secret scanner is a finding (R5)",
         {ws: sec(a=("docker run --rm -v \"$PWD:/repo\" -w /repo ghcr.io/gitleaks/gitleaks:v8.30.1 git", "echo scan"))}, 1, "secret-scan]")
    case("a secret scan of the tip, not the history, is a finding",
         {ws: sec(a=("          fetch-depth: 0 # the whole history: a secret removed in a later commit is still in the repository\n", ""))}, 1, "secret-scan-history")
    case("a secret scan only on pull requests is a finding",
         {ws: sec(a=("  pull_request:\n  push:\n", "  pull_request:\n"))}, 1, "secret-scan-push")
    case("no dependency review is a finding",
         {ws: sec(a=("actions/dependency-review-action", "actions/something-else"))}, 1, "dependency-review")
    case("no CodeQL is a finding", {ws: sec(a=("github/codeql-action/analyze", "github/codeql-action/other"))}, 1, "codeql")
    case("no project_gates step is a finding", {".github/workflows/ci.yml": "name: CI\non: pull_request\njobs:\n  t:\n    runs-on: x\n    steps:\n      - run: echo hi\n"}, 1, "gates")
    case("continue-on-error on a security step is a finding",
         {ws: sec(a=("      - name: Gem advisories\n        run: bin/bundler-audit\n", "      - name: Gem advisories\n        continue-on-error: true\n        run: bin/bundler-audit\n"))}, 1, "fail-closed")
    case("`|| true` on a security step is a finding",
         {ws: sec(a=("run: bin/bundler-audit", "run: bin/bundler-audit || true"))}, 1, "fail-closed")
    case("a commented-out tool is not a step",
         {ws: sec(a=("      - name: Importmap advisories\n        run: bin/importmap audit\n", "      # - run: bin/importmap audit\n      - run: echo hi\n"))}, 1, "importmap")
    case("importmap is not required when the project has none and bin/ci does not run it",
         {"config/importmap.rb": None, "config/ci.rb": LOCAL_CI.replace('  step "Security: Importmap vulnerability audit", "bin/importmap audit"\n', ""),
          ws: sec(a=("  importmap-audit:", "  importmap-audit-gone:")).replace("bin/importmap audit", "echo none")}, 0, "rules hold")
    case("an exemption with a reason lets a rule go",
         {ws: sec(a=("github/codeql-action/analyze", "github/codeql-action/other")), ".rails-flow/ci-parity.json": json.dumps({"exempt": [{"rule": "codeql", "reason": "language unsupported here"}]})}, 0, "exempted with a reason")
    case("an exemption with no reason is a finding", {ws: sec(a=("github/codeql-action/analyze", "github/codeql-action/other")), ".rails-flow/ci-parity.json": json.dumps({"exempt": [{"rule": "codeql", "reason": " "}]})}, 1, "bad-exemption")
    case("an exemption for a rule that holds is stale", {".rails-flow/ci-parity.json": json.dumps({"exempt": [{"rule": "codeql", "reason": "x"}]})}, 1, "stale-exemption")
    case("an exemption for an unknown rule is a finding", {".rails-flow/ci-parity.json": json.dumps({"exempt": [{"rule": "nope", "reason": "x"}]})}, 1, "unknown rule")
    case("an unreadable exemption file is a finding, not a pass", {".rails-flow/ci-parity.json": "{not json"}, 1, "bad-exemption")
    if bad == 0:
        print("check_ci_parity selftest: every row passes")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
