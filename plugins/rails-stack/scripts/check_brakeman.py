#!/usr/bin/env python3
"""Run Brakeman against the project and fail on any warning (#2223, phase 2 item 0).

Run:  python3 check_brakeman.py [--project DIR]
      python3 check_brakeman.py --selftest

WHY THIS IS A GATE. Brakeman is the upstream tool that already catches the Rails security claims this stack states as doctrine: cross-site scripting
through unescaped output (`CheckCrossSiteScripting`, `CheckSanitizeMethods`, `CheckStripTags`), the CSRF setting (`CheckForgerySetting`), SQL injection and
the rest of its checks (measured against the Brakeman docs by `doctrine-verifier` on 2026-10-21, `docs/evidence/audits/2026-10-21-hotwire-frontend-claims.md`
section C). A scaffolded project runs `bin/brakeman` in its own CI only when its `config/ci.rb` has that step, and nothing in this toolchain asked: this
registers it, so a project that installs rails-stack gets the check without having to remember it.

HOW. It finds Brakeman the way the project runs it, in this order: the project's `bin/brakeman`; `bundle exec brakeman` when the Gemfile names brakeman;
`brakeman` on PATH. It runs `-q --no-pager -f json` from the project directory and reads the JSON: every entry of `warnings` and every entry of `errors`
is a finding, printed as `file:line (check) message`. Warnings the project has reviewed and ignored (`config/brakeman.ignore`, the `ignored_warnings` list)
are Brakeman's own mechanism and are not counted.

A MISSING TOOL IS A FAILURE, NOT A SKIP, and so is output it cannot read. In CI a skip is indistinguishable from a pass, and "Brakeman said nothing" is
not "Brakeman found nothing". Exit codes follow the consumer-gate contract: 0 clean, 1 one or more findings, 2 the check could not run (no Brakeman, a
crash, JSON that does not parse).

Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TIMEOUT = 300


def find_brakeman(project: Path) -> list[str] | None:
    """The command that runs Brakeman for this project, or None."""
    binstub = project / "bin" / "brakeman"
    if binstub.is_file() and os.access(binstub, os.X_OK):
        return [str(binstub)]
    gemfile = project / "Gemfile"
    if gemfile.is_file() and "brakeman" in gemfile.read_text(encoding="utf-8", errors="replace") and shutil.which("bundle"):
        return ["bundle", "exec", "brakeman"]
    found = shutil.which("brakeman")
    return [found] if found else None


def findings_of(report: dict) -> list[str]:
    """Every warning and every error in a Brakeman JSON report as one line each. Ignored warnings are not in `warnings`."""
    out = []
    for w in report.get("warnings", []):
        out.append(f"{w.get('file', '?')}:{w.get('line', '?')} ({w.get('check_name', w.get('warning_type', '?'))}) {w.get('message', '')}".strip())
    for e in report.get("errors", []):
        out.append(f"error: {e.get('error', e)}")
    return out


def run(project: Path) -> tuple[int, list[str]]:
    """`(exit code, lines to print)`: 0 clean, 1 findings, 2 could not run."""
    # The one place the project is judged to have a Rails app: `config/application.rb` is also this check's `applies_when`.
    cmd = find_brakeman(project)
    if cmd is None:
        return 2, ["brakeman is not installed for this project (no bin/brakeman, no brakeman in the Gemfile, none on PATH): add `gem \"brakeman\"` to the "
                   "development group; a missing tool is a failure, not a skip"]
    try:
        done = subprocess.run([*cmd, "-q", "--no-pager", "-f", "json"], cwd=project, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 2, [f"brakeman could not run ({exc}): `{' '.join(cmd)}`"]
    try:
        report = json.loads(done.stdout)
    except ValueError:
        tail = (done.stderr.strip().splitlines() or done.stdout.strip().splitlines() or ["no output"])[-1][:120]
        return 2, [f"brakeman gave no JSON report (exit {done.returncode}): {tail}"]
    if not isinstance(report, dict):
        return 2, ["brakeman's JSON report is not an object"]
    found = findings_of(report)
    if found:
        return 1, [*found, f"{len(found)} finding(s)"]
    return 0, ["brakeman: 0 warnings, 0 errors"]


def _stub(directory: Path, name: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _selftest() -> int:
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    xss = {"warnings": [{"warning_type": "Cross-Site Scripting", "check_name": "CrossSiteScripting", "file": "app/views/notes/show.html.erb", "line": 4,
                         "message": "Unescaped parameter value"}], "errors": [], "ignored_warnings": []}
    clean = {"warnings": [], "errors": [], "ignored_warnings": [{"check_name": "CrossSiteScripting", "file": "app/views/ok.html.erb"}]}
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)

        def project(name: str, *, binstub: str | None = None, gemfile: str | None = None) -> Path:
            p = base / name
            (p / "config").mkdir(parents=True)
            (p / "config" / "application.rb").write_text("module App; end\n", encoding="utf-8")
            if gemfile is not None:
                (p / "Gemfile").write_text(gemfile, encoding="utf-8")
            if binstub is not None:
                _stub(p / "bin", "brakeman", binstub)
            return p

        emit = lambda report: f"cat <<'EOF'\n{json.dumps(report)}\nEOF\n"  # noqa: E731
        saved_path = os.environ.get("PATH", "")
        os.environ["PATH"] = str(base / "empty-bin") + os.pathsep + "/usr/bin:/bin"  # no brakeman and no bundle unless a case puts one here
        (base / "empty-bin").mkdir()
        try:
            code, lines = run(project("xss", binstub=emit(xss)))
            check("a warning (cross-site scripting in a view) is a finding", code == 1 and any("CrossSiteScripting" in ln and "show.html.erb:4" in ln for ln in lines))
            check("the finding count is printed", lines[-1] == "1 finding(s)")
            code, lines = run(project("clean", binstub=emit(clean)))
            check("a clean report is clean, and an ignored warning is not counted", code == 0)
            code, lines = run(project("errs", binstub=emit({"warnings": [], "errors": [{"error": "parse failure in app/models/x.rb"}]})))
            check("a Brakeman error is a finding too", code == 1 and any("parse failure" in ln for ln in lines))
            code, lines = run(project("none"))
            check("no Brakeman anywhere is a failure to run, never a skip", code == 2 and any("not installed" in ln for ln in lines))
            code, lines = run(project("garbage", binstub="echo 'Brakeman is thinking about it'\n"))
            check("output that is not JSON is a failure to run, not a clean pass", code == 2 and any("no JSON report" in ln for ln in lines))
            code, lines = run(project("crash", binstub="echo 'boom' >&2\nexit 4\n"))
            check("a crash with no report is a failure to run", code == 2)
            code, lines = run(project("array", binstub="echo '[]'\n"))
            check("a JSON report that is not an object is a failure to run", code == 2)
            # the Gemfile route: bundle exec brakeman, through a bundle stub that records its arguments
            record = base / "bundle-args"
            _stub(base / "bin-bundle", "bundle", f"echo \"$@\" > {record}\n{emit(xss)}")
            os.environ["PATH"] = str(base / "bin-bundle") + os.pathsep + os.environ["PATH"]
            code, lines = run(project("gem", gemfile='gem "rails"\ngem "brakeman", group: :development\n'))
            check("a Gemfile that names brakeman runs `bundle exec brakeman`", code == 1 and record.is_file() and record.read_text(encoding="utf-8").startswith("exec brakeman -q --no-pager -f json"))
            code, lines = run(project("nogem", gemfile='gem "rails"\n'))
            check("a Gemfile that does not name brakeman does not run bundle", code == 2)
            code, lines = run(project("pref", binstub=emit(clean), gemfile='gem "brakeman"\n'))
            check("the project's own bin/brakeman is preferred over bundle exec", code == 0)
        finally:
            os.environ["PATH"] = saved_path
    print(f"check_brakeman selftest: {ok} checks passed, {len(bad)} failed")
    for label in bad:
        print(f"  FAIL: {label}", file=sys.stderr)
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_brakeman.py", description=__doc__.splitlines()[0])
    ap.add_argument("--project", type=Path, default=Path.cwd(), help="the Rails project (default: the current directory)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    code, lines = run(args.project.resolve())
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
