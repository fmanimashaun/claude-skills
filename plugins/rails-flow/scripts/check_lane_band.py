#!/usr/bin/env python3
"""Gate: the lane-band mod stays read-only, is wired as ONE module, and still behaves (#1537).

`claude plugin test` runs the mod's tests with the real test kit, but CI does not install `claude`,
so nothing in the gate sweep exercised `hooks/lane-band.js`. This is what CI can run:

  1. `hooks/hooks.json` names exactly one module and that file exists (a mod takes ONE path; a
     second silently never loads).
  2. Static: the module calls no mods API method outside a small read-only set, and runs only the
     three read-only git verbs, `status` with `--no-optional-locks` before it. A read-only band
     that can rewrite `.git/index` or write a file is not read-only.
  3. Behaviour: `tests/lane-band.host.test.mjs` runs the module against a fake host in plain Node.

Paths resolve from this file's location, so the check works in `plugins/rails-flow` and in a
mutation tempdir that mirrors it. Exit 0 clean, 1 findings, 3 when `node` is missing (a skipped
behaviour check is not a pass).

    python3 plugins/rails-flow/scripts/check_lane_band.py
    python3 plugins/rails-flow/scripts/check_lane_band.py --selftest
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Every mods API method the module may call. Anything else is a call nobody reviewed.
ALLOWED_CALLS = {"process.run", "env.get", "ui.invalidate", "ui.resolve", "clock.after"}
# `git(`-helper argument lists the module may pass: the three read-only reads, nothing else.
ALLOWED_GIT = {
    ("rev-parse", "--show-toplevel"),
    ("branch", "--show-current"),
    ("--no-optional-locks", "status", "--porcelain"),
}


def check_modules(hooks_json_text: str, exists) -> list[str]:
    """`modules` is a list of exactly one string naming a file that exists."""
    try:
        data = json.loads(hooks_json_text)
    except ValueError as e:
        return [f"hooks.json does not parse: {e}"]
    modules = data.get("modules")
    if not isinstance(modules, list) or len(modules) != 1 or not isinstance(modules[0], str):
        return [f"hooks.json `modules` must be a list of exactly one path, got {modules!r}"]
    return [] if exists(modules[0]) else [f"hooks.json names {modules[0]!r}, which does not exist"]


def check_static(js: str) -> list[str]:
    """No unreviewed mods API call, and only the read-only git calls."""
    findings = []
    called = set(re.findall(r"\$\.([a-z]+\.[a-zA-Z]+)\b", js))
    for call in sorted(called - ALLOWED_CALLS):
        findings.append(f"calls $.{call}, which is not in the reviewed read-only set {sorted(ALLOWED_CALLS)}")
    for args in re.findall(r"\bgit\(\$,\s*\[([^\]]*)\]", js):
        verbs = tuple(re.findall(r"""['"]([^'"]+)['"]""", args))
        if verbs not in ALLOWED_GIT:
            findings.append(f"runs git with {list(verbs)}, which is not one of the three reviewed read-only calls")
    if re.search(r"\bawait\s+refresh\(", js):
        findings.append("awaits refresh() inside a hook, which delays the first prompt; schedule it with $.clock.after")
    return findings


def run_host_test() -> tuple[int, str]:
    node = shutil.which("node")
    if node is None:
        return 3, "node is not on PATH, so the behaviour check did not run"
    test = ROOT / "tests" / "lane-band.host.test.mjs"
    r = subprocess.run([node, str(test)], capture_output=True, text=True, timeout=60)
    return r.returncode, (r.stdout + r.stderr).strip()


def run() -> int:
    findings = []
    hooks_json = ROOT / "hooks" / "hooks.json"
    findings += check_modules(hooks_json.read_text(encoding="utf-8"), lambda m: (hooks_json.parent / m).is_file())
    js = (ROOT / "hooks" / "lane-band.js").read_text(encoding="utf-8")
    findings += check_static(js)
    code, out = run_host_test()
    if code == 3:
        print(f"lane-band: {out}")
        return 3
    if code != 0:
        findings.append("host test failed:\n    " + out.replace("\n", "\n    "))
    if findings:
        print("lane-band findings:\n  - " + "\n  - ".join(findings))
        return 1
    print("lane-band: one module, read-only calls only, host test passes")
    return 0


def selftest() -> int:
    """Each check fires on a fixture built to break it, and stays silent on the real shape."""
    failures = []

    def expect(name, findings, needle):
        hit = any(needle in f for f in findings)
        if bool(needle) != hit:
            failures.append(f"{name}: wanted {'a finding mentioning ' + repr(needle) if needle else 'no findings'}, got {findings}")

    good = '{"modules": ["./lane-band.js"], "hooks": {}}'
    expect("one module that exists is clean", check_modules(good, lambda m: True), "")
    expect("two modules are refused", check_modules('{"modules": ["./a.js", "./b.js"]}', lambda m: True), "exactly one")
    expect("no modules key is refused", check_modules('{"hooks": {}}', lambda m: True), "exactly one")
    expect("a missing file is refused", check_modules(good, lambda m: False), "does not exist")
    expect("bad JSON is refused", check_modules("{", lambda m: True), "does not parse")

    clean_js = (
        "const a = await git($, ['rev-parse', '--show-toplevel'])\n"
        "const b = await git($, ['branch', '--show-current'])\n"
        "const c = await git($, ['--no-optional-locks', 'status', '--porcelain'])\n"
        "$.process.run($.env.get('X'))\n$.ui.invalidate('ui.render')\n$.ui.resolve(e)\n$.clock.after(0, f)\n"
    )
    expect("the reviewed shape is clean", check_static(clean_js), "")
    expect("a write call is refused", check_static(clean_js + "$.fs.write('a','b')\n"), "$.fs.write")
    expect("a network call is refused", check_static(clean_js + "$.http.fetch(u)\n"), "$.http.fetch")
    expect("a mutating git verb is refused", check_static(clean_js + "await git($, ['add', '-A'])\n"), "'add', '-A'")
    expect("status without the flag is refused",
           check_static(clean_js.replace("'--no-optional-locks', ", "")), "'status', '--porcelain'")
    expect("an awaited refresh in a hook is refused", check_static(clean_js + "await refresh($)\n"), "awaits refresh")

    if failures:
        print("selftest FAILED:\n  - " + "\n  - ".join(failures))
        return 1
    print("selftest ok: every check fires on its fixture and stays silent on the reviewed shape")
    return 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv[1:] else run())
