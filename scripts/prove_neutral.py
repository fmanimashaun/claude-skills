#!/usr/bin/env python3
"""Prove a neutral component is neutral by RUNNING it, not by reading its text (#2205).

Run:  python3 scripts/prove_neutral.py --record     # run every neutral executable component, write docs/architecture/neutral-proof.json
      python3 scripts/prove_neutral.py --check      # re-run what the proof file records as proven: none may fail now, and the count may not fall
      python3 scripts/prove_neutral.py --status     # run everything and print the result, change nothing
      python3 scripts/prove_neutral.py --selftest   # plant a hook that calls `bundle exec rspec` (must go red), and the clean cases

WHY. `component_classes.py` classes a component neutral when a scan of its TEXT finds no Rails or Next.js name. A component can assume Rails without
naming it: shell out to `bundle exec`, expect `config/routes.rb`, `spec/**` or `db/schema.rb`. The scan cannot see those, so "neutral" meant "nothing found",
not "proven on every stack". This runs the component against two projects that have no Rails in them:

  * a Next.js one: a `next` dependency, `app/page.tsx`, no Gemfile; and
  * an empty one: a git repository holding one README.

A TRIPWIRE directory is first on PATH, with a stub for each of `rails`, `bundle`, `rspec`, `rubocop`, `ruby`, `kamal` (and `bin/rails` inside each project)
that RECORDS the call and exits 97. A neutral component that calls any of them is a finding, as is a traceback.

WHAT RUNS HOW.
  * a gate (a `checks.json` row): `project_gates.run_check`, the way `project_gates.py` runs it, one check at a time so a stub call is attributed to it;
    pass and not-applicable are clean, anything else is a finding;
  * a hook (a script registered in `hooks.json`): `/bin/bash -p <script>` with a benign payload for its event on stdin, from the project directory;
    exit 0 is clean;
  * a script (under `scripts/`): run bare from the project directory. Exit 0 or 1 with no traceback is clean; a usage exit (it needs arguments) is
    NOT PROVEN, not a finding, so it stays "nothing found".
A component is `proven` only when it ran clean on BOTH projects. Commands and agents are instructions, not code, so they are never proven here.

WHAT IT IS HONESTLY NOT. It proves "no Rails tool was called and nothing crashed on a project with no Rails". A component that reads `config/routes.rb`, finds
nothing and exits 0 still reads as proven; that is a limit of running without tracing file reads, and the page says so. A component that exits non-zero
on a Next.js project for a legitimate reason (a gate that found something) is reported as a finding to look at, not as a proof.

THE RATCHET. `docs/architecture/neutral-proof.json` records the proven components and a `floor`. `--check` re-runs the recorded ones: a recorded component
that no longer runs clean, or a count below the floor, fails. `--record` only raises the floor, never lowers it.

Stdlib only. Exit codes: 0 clean · 1 findings · 2 not this repo.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "rails-flow" / "scripts"))
import component_classes as cc  # noqa: E402
import fixture_git  # noqa: E402
import rails_assumptions as ra  # noqa: E402

REPO = ra.REPO
PROOF = "docs/architecture/neutral-proof.json"
STUBS = ("rails", "bundle", "rspec", "rubocop", "ruby", "kamal")
TIMEOUT = 25
PAYLOADS = {
    "SessionStart": {"source": "startup"},
    "SessionEnd": {"reason": "other"},
    "Stop": {"stop_hook_active": False},
    "PreToolUse": {"tool_name": "Bash", "tool_input": {"command": "ls"}},
    "PostToolUse": {"tool_name": "Bash", "tool_input": {"command": "ls"}, "tool_response": {"stdout": "", "stderr": ""}},
    "PostToolUseFailure": {"tool_name": "Bash", "tool_input": {"command": "ls"}, "error": "x"},
}


def tripwire(directory: Path) -> Path:
    """A directory of stubs that record the call into `$PROVE_TRIPWIRE_LOG` and exit 97."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in STUBS:
        stub = directory / name
        stub.write_text('#!/bin/sh\nprintf \'%s %s\\n\' "$(basename "$0")" "$*" >> "$PROVE_TRIPWIRE_LOG"\nexit 97\n', encoding="utf-8")
        stub.chmod(0o755)
    return directory


def fixtures(base: Path) -> dict[str, Path]:
    """The two projects: a Next.js one and an empty one. Each is a git repository with a `bin/rails` tripwire inside."""
    made = {}
    for name, files in (("nextjs", {"package.json": json.dumps({"name": "x", "dependencies": {"next": "15.0.0", "react": "19.0.0"}}),
                                    "app/page.tsx": "export default function Page() { return <main /> }\n",
                                    "app/layout.tsx": "export default function L({ children }: { children: React.ReactNode }) { return <html><body>{children}</body></html> }\n",
                                    "tsconfig.json": '{"compilerOptions": {"strict": true}}\n'}),
                        ("empty", {"README.md": "empty project\n"})):
        project = base / name
        for rel, text in files.items():
            (project / rel).parent.mkdir(parents=True, exist_ok=True)
            (project / rel).write_text(text, encoding="utf-8")
        fixture_git.init(project)
        fixture_git.run(project, "add", "--", *files)
        fixture_git.run(project, "commit", "-qm", "fixture")
        stub = project / "bin" / "rails"
        stub.parent.mkdir(exist_ok=True)
        stub.write_text('#!/bin/sh\nprintf \'bin/rails %s\\n\' "$*" >> "$PROVE_TRIPWIRE_LOG"\nexit 97\n', encoding="utf-8")
        stub.chmod(0o755)
        made[name] = project
    return made


def real_git() -> str | None:
    """The `git` on PATH that is not a guard shim (`.../git-shim/git`): a component run under the harness must not depend on the invoking session's shim."""
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(entry) / "git"
        if entry and "git-shim" not in entry and candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return "/usr/bin/git" if Path("/usr/bin/git").is_file() else None


def environment(base: Path, log: Path, project: Path, plugin_root: Path | None = None) -> dict[str, str]:
    tools = [str(Path(sys.executable).parent), *(str(Path(p).parent) for p in (real_git(),) if p), "/usr/bin", "/bin"]
    env = {"PATH": os.pathsep.join([str(base / "tripwire"), *dict.fromkeys(tools)]), "HOME": str(base / "home"), "TMPDIR": str(base / "tmp"),
           "LANG": "C.UTF-8", "PROVE_TRIPWIRE_LOG": str(log), "CLAUDE_PROJECT_DIR": str(project), "GIT_CONFIG_GLOBAL": os.devnull}
    if plugin_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    (base / "home").mkdir(exist_ok=True)
    (base / "tmp").mkdir(exist_ok=True)
    return env


def verdict(rc: int, out: str, log: Path, *, usage_ok: bool = False) -> tuple[str, str]:
    """`(state, why)`: clean, a finding, or notproven. A stub call or a traceback is a finding."""
    calls = log.read_text(encoding="utf-8").strip().splitlines() if log.is_file() else []
    if calls:
        return "finding", f"called a Rails tool: {calls[0][:80]}"
    if "Traceback (most recent call last)" in out:
        return "finding", "crashed with a traceback"
    if rc in (0,) or (rc == 1 and usage_ok):
        return "clean", ""
    return ("finding" if not usage_ok else "notproven"), f"exit {rc}: {out.strip().splitlines()[-1][:80] if out.strip() else 'no output'}"


def run_group(cmd: list[str], *, cwd: Path, env: dict[str, str], stdin: str | None) -> tuple[int, str] | None:
    """Run `cmd` in its own process group and kill the whole group on a timeout (a component can spawn children that outlive it). None on timeout."""
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        out, _ = proc.communicate(stdin, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        return None
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # stragglers of a component that exited
    except ProcessLookupError:
        pass
    return proc.returncode, out


def timed_out(log: Path) -> tuple[str, str]:
    """A timeout proves nothing either way, EXCEPT that a stub called before the kill is still a finding: a Rails hook that hangs after `bundle exec` must not hide as not proven."""
    calls = log.read_text(encoding="utf-8").strip().splitlines() if log.is_file() else []
    if calls:
        return "finding", f"called a Rails tool before timing out: {calls[0][:80]}"
    return "notproven", f"timed out after {TIMEOUT}s (a slow or loaded machine proves nothing either way)"


def run_hook(path: Path, event: str, project: Path, base: Path) -> tuple[str, str]:
    log = base / f"log-{path.name}-{project.name}"
    log.unlink(missing_ok=True)
    payload = {"session_id": "prove", "transcript_path": str(base / "none.jsonl"), "cwd": str(project), "hook_event_name": event, **PAYLOADS.get(event.split()[0], {})}
    plugin_root = next(p for p in (path, *path.parents) if (p / ".claude-plugin").is_dir())
    cmd = ["/bin/bash", "-p", str(path)] if path.suffix == ".sh" else [sys.executable, str(path)]
    done = run_group(cmd, cwd=project, env=environment(base, log, project, plugin_root), stdin=json.dumps(payload))
    if done is None:
        return timed_out(log)
    return verdict(done[0], done[1], log)


def run_script(path: Path, project: Path, base: Path) -> tuple[str, str]:
    log = base / f"log-{path.name}-{project.name}"
    log.unlink(missing_ok=True)
    cmd = [sys.executable, str(path)] if path.suffix == ".py" else ["/bin/bash", str(path)]
    done = run_group(cmd, cwd=project, env=environment(base, log, project), stdin=None)
    if done is None:
        return timed_out(log)
    return verdict(done[0], done[1], log, usage_ok=True)


def run_gate(check, project: Path, base: Path) -> tuple[str, str]:
    import project_gates as pg
    log = base / f"log-{check.id}-{project.name}"
    log.unlink(missing_ok=True)
    saved = dict(os.environ)
    os.environ.clear()
    os.environ.update(environment(base, log, project))
    try:
        result = pg.run_check(check, project)
    finally:
        os.environ.clear()
        os.environ.update(saved)
    calls = log.read_text(encoding="utf-8").strip().splitlines() if log.is_file() else []
    if calls:
        return "finding", f"called a Rails tool: {calls[0][:80]}"
    if result.status in (pg.PASS, pg.NA):
        return "clean", ""
    if "is not on PATH" in result.detail:
        return "notproven", f"needs a tool this harness does not provide: {result.detail[:80]}"
    return "finding", f"{result.status}: {result.detail[:80]}"


def prove_all(root: Path, components: list[dict], only: set[str] | None = None) -> dict[str, dict]:
    """`{path: {"state": proven|finding|notproven, "why": str}}` for every neutral executable component (or just `only`)."""
    import project_gates as pg
    checks = {}
    roots = pg.plugin_roots(root / "plugins" / "rails-flow" / "scripts" / "project_gates.py")
    loaded, _ = pg.load_checks(roots)
    for check in loaded:
        checks[f"plugins/{check.plugin}/checks.json#{check.id}"] = check
    todo = [c for c in components if c["info"] and c["info"]["class"] == "neutral" and c["type"] in ("hook", "script", "gate") and (only is None or c["path"] in only)]
    results: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        base = Path(tmp)
        tripwire(base / "tripwire")
        projects = fixtures(base)

        def one(comp: dict) -> tuple[str, dict]:
            path = comp["path"]
            outcomes = []
            for project in projects.values():
                if comp["type"] == "gate":
                    check = checks.get(path)
                    outcomes.append(run_gate(check, project, base) if check else ("notproven", "not discovered by project_gates"))
                elif comp["type"] == "hook":
                    if not comp["registered"] or path.endswith((".json", ".mjs", ".js")) or "/lib/" in path:
                        outcomes.append(("notproven", "not a registered hook script"))
                    else:
                        outcomes.append(run_hook(root / path, comp["registered"][0], project, base))
                elif not path.endswith((".py", ".sh")):
                    outcomes.append(("notproven", "not a runnable script"))
                else:
                    outcomes.append(run_script(root / path, project, base))
            bad = next(((s, w) for s, w in outcomes if s == "finding"), None)
            if bad:
                return path, {"state": "finding", "why": bad[1]}
            skipped = next(((s, w) for s, w in outcomes if s == "notproven"), None)
            return path, {"state": "notproven", "why": skipped[1]} if skipped else {"state": "proven", "why": ""}

        with ThreadPoolExecutor(max_workers=6) as pool:
            for path, row in pool.map(one, todo):
                results[path] = row
    return dict(sorted(results.items()))


def load_proof(root: Path) -> dict:
    p = root / PROOF
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"floor": 0, "proven": []}


def judge(results: dict[str, dict], proof: dict) -> list[str]:
    """Findings against a re-run: a recorded-proven component that no longer runs clean, and a proven count below the floor."""
    out = []
    for path in proof.get("proven", []):
        row = results.get(path)
        if row is None:
            out.append(f"{path}: recorded as proven but is no longer a neutral executable component (reclassified, moved or removed): update {PROOF}")
        elif row["state"] != "proven":
            out.append(f"{path}: recorded as proven, now {row['state']}: {row['why']}")
    proven = sum(1 for r in results.values() if r["state"] == "proven")
    if proven < proof.get("floor", 0):
        out.append(f"{proven} component(s) proven, below the recorded floor of {proof['floor']}: the proven count may not fall")
    return out


def _selftest() -> int:
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        tripwire(base / "tripwire")
        projects = fixtures(base)
        plug = base / "plugin"
        (plug / ".claude-plugin").mkdir(parents=True)
        scripts = {"clean.sh": "#!/bin/bash\necho ok\n", "bad.sh": "#!/bin/bash\nbundle exec rspec spec/\n", "rails.sh": "#!/bin/bash\nbin/rails db:migrate\n",
                   "crash.sh": "#!/bin/bash\nexit 7\n", "slow.sh": "#!/bin/bash\nsleep 1\n"}
        for name, text in scripts.items():
            (plug / name).write_text(text, encoding="utf-8")
        nj = projects["nextjs"]
        check("a clean hook is clean on the Next.js project", run_hook(plug / "clean.sh", "Stop", nj, base)[0] == "clean")
        state, why = run_hook(plug / "bad.sh", "PreToolUse Bash", nj, base)
        check("a hook that calls `bundle exec rspec` is a finding", state == "finding" and "called a Rails tool: bundle" in why)
        check("a hook that calls bin/rails is a finding", run_hook(plug / "rails.sh", "SessionStart", nj, base)[0] == "finding")
        check("a hook that exits non-zero is a finding", run_hook(plug / "crash.sh", "Stop", nj, base)[0] == "finding")
        check("a hook that calls a stub in the empty project is a finding too", run_hook(plug / "bad.sh", "Stop", projects["empty"], base)[0] == "finding")
        (plug / "tb.py").write_text("raise SystemExit(int('x'))\n", encoding="utf-8")
        check("a script that crashes with a traceback is a finding", run_script(plug / "tb.py", nj, base)[0] == "finding")
        (plug / "hang.sh").write_text("#!/bin/bash\nbundle exec rspec\nsleep 30\n", encoding="utf-8")
        (plug / "idle.sh").write_text("#!/bin/bash\nsleep 30\n", encoding="utf-8")
        global TIMEOUT
        saved, TIMEOUT = TIMEOUT, 2
        try:
            state, why = run_hook(plug / "hang.sh", "Stop", nj, base)
            check("a hook that calls a stub and then hangs past the timeout is a finding", state == "finding" and "before timing out" in why)
            check("a hook that only hangs is not proven, not a finding", run_hook(plug / "idle.sh", "Stop", nj, base)[0] == "notproven")
            check("a script that calls a stub and then hangs is a finding", run_script(plug / "hang.sh", nj, base)[0] == "finding")
        finally:
            TIMEOUT = saved
        (plug / "usage.py").write_text("import sys\nsys.exit(2)\n", encoding="utf-8")
        check("a script that needs arguments is not proven, not a finding", run_script(plug / "usage.py", nj, base)[0] == "notproven")
        (plug / "fine.py").write_text("print('ok')\n", encoding="utf-8")
        check("a script that runs clean is proven clean", run_script(plug / "fine.py", nj, base)[0] == "clean")
        check("the harness's git is never a guard shim", "git-shim" not in (real_git() or ""))
        check("the Next.js fixture has no Gemfile and a next dependency", not (nj / "Gemfile").exists() and "next" in (nj / "package.json").read_text(encoding="utf-8"))
        check("the empty fixture holds no app code", not (projects["empty"] / "app").exists())
    proof = {"floor": 2, "proven": ["a", "b"]}
    check("a recorded component that still proves is clean", judge({"a": {"state": "proven", "why": ""}, "b": {"state": "proven", "why": ""}}, proof) == [])
    check("a recorded component that now fails is a finding", any("now finding" in f for f in judge({"a": {"state": "proven", "why": ""}, "b": {"state": "finding", "why": "x"}}, proof)))
    check("a recorded component that vanished is a finding", any("no longer a neutral" in f for f in judge({"a": {"state": "proven", "why": ""}}, proof)))
    check("a proven count below the floor is a finding", any("below the recorded floor" in f for f in judge({"a": {"state": "proven", "why": ""}}, {"floor": 5, "proven": []})))
    print(f"prove_neutral selftest: {ok} checks passed, {len(bad)} failed")
    for label in bad:
        print(f"  FAIL: {label}", file=sys.stderr)
    return 1 if bad else 0


def main(argv: list[str] | None = None, root: Path = REPO) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record", action="store_true", help="run everything and write the proof file (raises the floor, never lowers it)")
    ap.add_argument("--check", action="store_true", help="re-run the recorded components: none may fail, the count may not fall")
    ap.add_argument("--status", action="store_true", help="run everything and print the result")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not (root / ".claude-plugin" / "marketplace.json").is_file():
        print("not the claude-skills repo", file=sys.stderr)
        return 2
    comps, classify_findings = cc.classify(root, ra.load_policy(root))
    proof = load_proof(root)
    results = prove_all(root, comps, set(proof.get("proven", [])) if a.check else None)
    counts = {s: sum(1 for r in results.values() if r["state"] == s) for s in ("proven", "notproven", "finding")}
    if a.status or a.record:
        print(f"{len(results)} neutral executable component(s): {counts['proven']} proven, {counts['notproven']} not proven, {counts['finding']} finding(s)")
        for path, row in results.items():
            if row["state"] == "finding":
                print(f"  FINDING {path}: {row['why']}")
    findings = list(classify_findings)
    if a.check:
        findings += judge(results, proof)
    if a.record:
        findings += [f"{p}: {r['why']}" for p, r in results.items() if r["state"] == "finding"]
        if not findings:
            proven = sorted(p for p, r in results.items() if r["state"] == "proven")
            data = {"floor": max(proof.get("floor", 0), len(proven)), "proven": proven}
            (root / PROOF).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
            print(f"wrote {PROOF}: {len(proven)} proven, floor {data['floor']}. `git add docs/` AND COMMIT.")
    if findings:
        print(f"\n{len(findings)} finding(s):", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        return 1
    if a.check:
        print(f"clean: {counts['proven']} recorded component(s) still prove neutral, floor {proof.get('floor', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
