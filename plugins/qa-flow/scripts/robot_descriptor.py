#!/usr/bin/env python3
"""Validate a project's QA robot descriptor, `qa/robot.json` (#1837), and prove the image runner fails closed.

    robot_descriptor.py --check qa/robot.json
    robot_descriptor.py --selftest

The descriptor is the per-app half of the release-image QA robot (#1693): which roles exist, the screen that creates each, how each
signs in, the journeys that create records, and the DOCUMENTED BOUNDARY -- what real flows cannot reach. Everything else (the guard,
TOTP, the mail reader, the manifests, the teardown, the runner) is the plugin's.

    {
      "stack": "myapp-certify",                       compose project name; teardown's proveNothingLeft() reads it back
      "base_url": "http://127.0.0.1:3000",            must dial this machine (parsed host, no userinfo)
      "mailpit_url": "http://127.0.0.1:8025",         optional; same rule
      "roles": [{"handle": "admin", "role": "admin", "created_on": "/people/new", "sign_in": "password+totp"}],
      "journeys": [{"name": "open a request", "as": "requester", "screens": ["/requests/new"], "creates": ["request"]}],
      "boundary": [{"what": "the payment provider's webhook", "why": "an outside party sends it; we never forge it"}]
    }

`sign_in` is one of password+totp, password+email-code, email-link. An empty `boundary` needs `boundary_none_reason`: "nothing is out
of reach" is a claim, so it is written down rather than implied by an empty list. Exit 0 valid, 1 findings, 2 unreadable.
"""
from __future__ import annotations

import json
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

SIGN_IN = {"password+totp", "password+email-code", "email-link"}
SLUG = re.compile(r"[a-z0-9][a-z0-9_-]*")   # used with fullmatch: `$` alone also matches before a trailing newline
LOCAL = {"127.0.0.1", "localhost", "::1"}
RUNNER = Path(__file__).resolve().parents[1] / "scaffold" / "qa" / "seed" / "image-e2e"


def local_url(raw: object) -> str | None:
    """None when `raw` is plain http(s) to this machine; else why not. The same rule as the TypeScript guard."""
    if not isinstance(raw, str) or not raw.strip():
        return "is missing"
    try:
        parts = urlsplit(raw)
        host = parts.hostname or ""
        parts.port   # raises ValueError for a port outside 0-65535 or not a number
    except ValueError as exc:
        return f"is not a valid URL ({exc})"
    if parts.scheme not in ("http", "https"):
        return "must be http or https"
    if parts.username is not None or parts.password is not None:
        return "has userinfo (user:password@), which hides the host it dials"
    if host not in LOCAL:
        return f"dials {host or '(no host)'}, not this machine"
    return None


def check(doc: object) -> list[str]:
    f: list[str] = []
    if not isinstance(doc, dict):
        return ["the descriptor is not a JSON object"]
    if not isinstance(doc.get("stack"), str) or not SLUG.fullmatch(doc["stack"]):
        f.append("stack: a compose project name (lower-case letters, digits, - and _) is required")
    for key in ("base_url", "mailpit_url"):
        if key == "mailpit_url" and key not in doc:
            continue
        why = local_url(doc.get(key))
        if why:
            f.append(f"{key} {why}")
    roles = doc.get("roles")
    handles: set[str] = set()
    if not isinstance(roles, list) or not roles:
        f.append("roles: at least one role is required")
        roles = []
    for i, r in enumerate(roles):
        if not isinstance(r, dict):
            f.append(f"roles[{i}] is not an object"); continue
        h = r.get("handle")
        if not isinstance(h, str) or not SLUG.fullmatch(h):
            f.append(f"roles[{i}].handle must be a slug (it becomes qa+<handle>@...)")
        elif h in handles:
            f.append(f"roles[{i}].handle {h!r} appears twice")
        else:
            handles.add(h)
        if not isinstance(r.get("role"), str) or not r["role"].strip():
            f.append(f"roles[{i}].role is required")
        if not isinstance(r.get("created_on"), str) or not r["created_on"].startswith("/"):
            f.append(f"roles[{i}].created_on must be the path of the screen that creates it (a real flow, not a backdoor)")
        if r.get("sign_in") not in SIGN_IN:
            f.append(f"roles[{i}].sign_in must be one of {', '.join(sorted(SIGN_IN))}")
    journeys = doc.get("journeys")
    if not isinstance(journeys, list):
        f.append("journeys: a list is required (it may be empty)")
        journeys = []
    for i, j in enumerate(journeys):
        if not isinstance(j, dict):
            f.append(f"journeys[{i}] is not an object"); continue
        if not isinstance(j.get("name"), str) or not j["name"].strip():
            f.append(f"journeys[{i}].name is required")
        if j.get("as") not in handles:
            f.append(f"journeys[{i}].as must name a declared role handle")
        if not isinstance(j.get("screens"), list) or not j["screens"] or not all(isinstance(s, str) and s.startswith("/") for s in j["screens"]):
            f.append(f"journeys[{i}].screens must list the screen paths it goes through")
        if not isinstance(j.get("creates"), list) or not all(isinstance(c, str) and c.strip() for c in j["creates"]):
            f.append(f"journeys[{i}].creates must list the record kinds it makes (teardown's records manifest)")
    boundary = doc.get("boundary")
    if not isinstance(boundary, list):
        f.append("boundary: a list is required")
    elif not boundary:
        if not isinstance(doc.get("boundary_none_reason"), str) or not doc["boundary_none_reason"].strip():
            f.append("boundary is empty: say why nothing is out of reach in boundary_none_reason")
    else:
        for i, b in enumerate(boundary):
            if not isinstance(b, dict) or not str(b.get("what", "")).strip() or not str(b.get("why", "")).strip():
                f.append(f"boundary[{i}] needs what and why")
    return f


def run_runner(env_extra: dict[str, str], seed: bool, args: tuple[str, ...] = ()) -> tuple[int, str, list[str], list[str]]:
    """Run the real image-e2e from a temp project root, stub curl and npx on PATH.
    Returns (exit, stderr, npx argv + QA_REQUIRE_SEED, curl argv)."""
    with tempfile.TemporaryDirectory() as td:
        qa = Path(td) / "qa"
        shutil.copytree(RUNNER.parents[1], qa)
        if seed:
            (qa / ".qa-seed").mkdir()
            for name in ("personas.json", "records.json"):
                (qa / ".qa-seed" / name).write_text("{}\n")
        bindir = Path(td) / "bin"
        bindir.mkdir()
        log = Path(td) / "npx.log"
        clog = Path(td) / "curl.log"
        for name, body in (("curl", f'printf "%s\\n" "$@" > "{clog}"\nexit 0\n'),
                           ("npx", f'printf "%s\\n" "QA_REQUIRE_SEED=$QA_REQUIRE_SEED" "$@" > "{log}"\n')):
            p = bindir / name
            p.write_text("#!/usr/bin/env bash\n" + body)
            p.chmod(p.stat().st_mode | stat.S_IXUSR)
        node = shutil.which("node")
        env = {"PATH": f"{bindir}:{Path(node).parent if node else ''}:/usr/bin:/bin", "HOME": td, **env_extra}
        r = subprocess.run(["bash", str(qa / "seed" / "image-e2e"), *args], env=env, cwd=td, capture_output=True, text=True, timeout=60)
        return (r.returncode, r.stderr, log.read_text().splitlines() if log.exists() else [],
                clog.read_text().splitlines() if clog.exists() else [])


def selftest() -> int:
    bad: list[str] = []
    good = {"stack": "myapp-certify", "base_url": "http://127.0.0.1:3000", "mailpit_url": "http://localhost:8025",
            "roles": [{"handle": "admin", "role": "admin", "created_on": "/people/new", "sign_in": "password+totp"},
                      {"handle": "requester", "role": "requester", "created_on": "/people/new", "sign_in": "email-link"}],
            "journeys": [{"name": "open a request", "as": "requester", "screens": ["/requests/new"], "creates": ["request"]}],
            "boundary": [{"what": "the payment webhook", "why": "an outside party sends it"}]}

    def expect(label: str, doc: dict, needle: str | None) -> None:
        got = check(doc)
        if needle is None and got:
            bad.append(f"{label}: expected valid, got {got}")
        elif needle is not None and not any(needle in g for g in got):
            bad.append(f"{label}: expected a finding containing {needle!r}, got {got}")

    expect("descriptor: a complete descriptor is valid", good, None)
    expect("descriptor: a base_url with userinfo hiding a real host is refused", {**good, "base_url": "https://127.0.0.1:x@prod.example.com"}, "userinfo")
    expect("descriptor: a base_url that only starts like this machine is refused", {**good, "base_url": "http://127.0.0.1.prod.example.com"}, "not this machine")
    expect("descriptor: a remote mail catcher is refused", {**good, "mailpit_url": "https://mail.example.com"}, "mailpit_url dials")
    expect("descriptor: a stack name that is a pattern is refused", {**good, "stack": "*"}, "stack:")
    expect("descriptor: a duplicate role handle is refused", {**good, "roles": good["roles"] + [good["roles"][0]]}, "appears twice")
    expect("descriptor: an unknown sign-in method is refused", {**good, "roles": [{**good["roles"][0], "sign_in": "magic-cookie"}]}, "sign_in must be")
    expect("descriptor: a role created by something other than a screen is refused", {**good, "roles": [{**good["roles"][0], "created_on": "rails runner"}]}, "created_on")
    expect("descriptor: a journey as an undeclared role is refused", {**good, "journeys": [{**good["journeys"][0], "as": "ghost"}]}, "must name a declared role")
    expect("descriptor: an empty boundary needs a stated reason", {**good, "boundary": []}, "boundary_none_reason")
    expect("descriptor: an empty boundary with a reason is valid", {**good, "boundary": [], "boundary_none_reason": "every flow is in-app"}, None)
    expect("descriptor: a stack name with a trailing newline is refused (fullmatch)", {**good, "stack": "myapp\n"}, "stack:")
    expect("descriptor: a port over 65535 is refused", {**good, "base_url": "http://127.0.0.1:70000"}, "not a valid URL")
    expect("descriptor: a boundary entry needs what and why", {**good, "boundary": [{"what": "x"}]}, "needs what and why")

    if not shutil.which("node"):
        bad.append("runner: node is not on PATH, so the image-e2e fixtures did not run")
    else:
        code, err, _, _ = run_runner({}, seed=True)
        if code == 0 or "QA_BASE_URL is required" not in err:
            bad.append(f"runner: no QA_BASE_URL must fail naming it (exit {code}: {err[-200:]})")
        code, err, npx, curl = run_runner({"QA_BASE_URL": "https://127.0.0.1:x@prod.example.com"}, seed=True)
        if code != 2 or npx:
            bad.append(f"runner: a non-local QA_BASE_URL must exit 2 before anything runs (exit {code}, npx {npx})")
        code, err, npx, curl = run_runner({"QA_BASE_URL": "http://127.0.0.1:3000", "QA_MAILPIT_URL": "https://mail.example.com"}, seed=True)
        if code != 2 or npx:
            bad.append(f"runner: a remote QA_MAILPIT_URL must exit 2 (exit {code}, npx {npx})")
        code, err, npx, curl = run_runner({"QA_BASE_URL": "http://127.0.0.1:3000"}, seed=False)
        if code != 1 or npx or "no QA seed" not in err:
            bad.append(f"runner: a missing seed must FAIL the run, not skip it (exit {code}, npx {npx})")
        code, err, npx, curl = run_runner({"QA_BASE_URL": "http://127.0.0.1:3000"}, seed=True)
        if code != 0 or "QA_REQUIRE_SEED=1" not in npx or "--retries=0" not in npx or "@qa-image" not in npx:
            bad.append(f"runner: a ready stack runs playwright with QA_REQUIRE_SEED=1, --retries=0 and the @qa-image grep (exit {code}, npx {npx})")
        code, err, npx, curl = run_runner({"QA_BASE_URL": "http://localhost:3000/some/page?x=1"}, seed=True)
        if code != 0 or "http://localhost:3000/up" not in curl:
            bad.append(f"runner: curl asks the ORIGIN the guard printed plus the health path, never the raw text (exit {code}, curl {curl})")
        code, err, npx, curl = run_runner({"QA_BASE_URL": "http://127.0.0.1:3000", "QA_UP_PATH": "@evil.example.com"}, seed=True)
        if code != 2 or curl or npx:
            bad.append(f"runner: a QA_UP_PATH that would change the host is refused (exit {code}, curl {curl})")
        code, err, npx, curl = run_runner({"QA_BASE_URL": "http://127.0.0.1:3000"}, seed=True, args=("--retries=3",))
        if code != 2 or npx:
            bad.append(f"runner: a caller's --retries is refused, so --retries=0 holds (exit {code}, npx {npx})")
        code, err, npx, curl = run_runner({"QA_BASE_URL": "http://127.0.0.1:3000", "QA_SEED_DIR": "elsewhere"}, seed=True)
        if code != 1 or "no QA seed" not in err:
            bad.append(f"runner: a relative QA_SEED_DIR is read from where the runner is run, not from qa/ (exit {code})")
    for b in bad:
        print(f"FAIL {b}")
    print(f"robot_descriptor selftest: {'FAILED ' + str(len(bad)) if bad else 'ok'}")
    return 1 if bad else 0


def main() -> int:
    args = sys.argv[1:]
    if args == ["--selftest"]:
        return selftest()
    if len(args) != 2 or args[0] != "--check":
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    try:
        doc = json.loads(Path(args[1]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"robot_descriptor: cannot read {args[1]}: {exc}", file=sys.stderr)
        return 2
    findings = check(doc)
    for x in findings:
        print(f"{args[1]}: {x}")
    if not findings:
        print(f"{args[1]}: valid")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
