#!/usr/bin/env python3
"""Prove the SessionStart curated-doc drift signal reports THREE states, not two.

The signal is advisory -- it prints a status line and blocks nothing. That is why the bug it now
guards was invisible: the loop hashed each manifest row with a bare `sha256sum` and skipped any row
that produced no output. On a machine without a working hasher every row was skipped, `stale` stayed
0, and the hook printed nothing at all -- while the REST of the hook ran normally, so the session
looked healthy and the drift check looked clean. An advisory that silently reports a false clean is
worse than no advisory.

This drives the REAL hook script end to end in a throwaway git repo. It does not reimplement the
loop: a test that recomputed the shell's logic could not witness the shell changing, which is the
whole failure this file exists to prevent.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hooks" / "scripts" / "session-start.sh"

DRIFTED = "drifted from their project skills"
UNHASHED = "could NOT be hashed"


def run_hook(*, hashers: str, manifest_hash: str) -> str:
    """Run the real hook in a fresh git repo and return its stdout.

    hashers: "real" (inherit PATH), "broken" (both present but exit 127), "absent" (neither on
    PATH), "shasum_only" (no sha256sum, which is every macOS before Apple shipped /sbin/sha256sum).
    manifest_hash: the hash recorded for the tracked file -- a wrong one means real drift.
    """
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "proj"
        (root / ".claude" / "skills").mkdir(parents=True)
        (root / "tracked.md").write_text("ORIGINAL\n")
        (root / ".claude" / "skills" / ".manifest.tsv").write_text(f"tracked.md\t{manifest_hash}\n")
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                    ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"]):
            subprocess.run(cmd, cwd=root, check=True, capture_output=True)

        env = dict(os.environ)
        env.pop("RAILS_FLOW_LANE", None)
        if hashers == "broken":
            stub = Path(td) / "stub"
            stub.mkdir()
            for name in ("sha256sum", "shasum"):
                f = stub / name
                f.write_text("#!/bin/sh\nexit 127\n")
                f.chmod(0o755)
            env["PATH"] = f"{stub}{os.pathsep}{env['PATH']}"
        elif hashers in ("absent", "shasum_only"):
            keep = Path(td) / "bin"
            keep.mkdir()
            # A minimal PATH holding every tool the hook needs EXCEPT a hasher. Symlinking rather
            # than trimming PATH keeps the rest of the hook working, so a silent failure here is
            # the hasher's and not an unrelated missing binary's.
            for tool in ("sh", "bash", "git", "cut", "printf", "grep", "sed", "awk", "wc",
                         "tr", "cksum", "mkdir", "cat", "head", "date", "sort", "uniq", "python3"):
                src = shutil.which(tool)
                if src:
                    (keep / tool).symlink_to(src)
            if hashers == "shasum_only":
                (keep / "shasum").symlink_to(shutil.which("shasum"))
            env["PATH"] = str(keep)
        proc = subprocess.run(["bash", str(HOOK)], cwd=root, env=env,
                              capture_output=True, text=True, timeout=90)
        return proc.stdout


def selftest() -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        checks.append((label, bool(ok), detail))

    if not HOOK.is_file():
        print(f"FAIL: hook not found at {HOOK}", file=sys.stderr)
        return 1

    # A WRONG recorded hash is real drift, and a working hasher must say so. Without this the two
    # negative cases below would pass on a hook that never prints anything at all.
    out = run_hook(hashers="real", manifest_hash="deadbeefdead")
    check("a working hasher reports real drift", DRIFTED in out, f"stdout={out!r}")
    check("...and does not claim it was unhashable", UNHASHED not in out, f"stdout={out!r}")

    # The CONTROL. A correct recorded hash must stay silent, or "reports drift" above would be
    # satisfied by a hook that shouts drift unconditionally.
    real = subprocess.run(["shasum", "-a", "256", "-"], input=b"ORIGINAL\n",
                          capture_output=True).stdout.decode()[:12]
    out = run_hook(hashers="real", manifest_hash=real)
    check("a matching hash reports nothing", DRIFTED not in out and UNHASHED not in out,
          f"stdout={out!r}")

    # THE REGRESSION, both shapes. Absent and present-but-broken are different failures and the
    # old `command -v` draft of this fix caught only the first: a stub that exists and exits 127
    # satisfies the probe, then hashes nothing.
    for shape in ("absent", "broken"):
        out = run_hook(hashers=shape, manifest_hash="deadbeefdead")
        check(f"a {shape} hasher is reported, not swallowed", UNHASHED in out, f"stdout={out!r}")
        check(f"a {shape} hasher does not claim a clean tree", "drifted" not in out or UNHASHED in out,
              f"stdout={out!r}")

    # THE FALLBACK. Without this the `shasum -a 256` branch is unreachable on any machine that has
    # sha256sum -- every current macOS and most Linux -- so no fixture could witness it and deleting
    # it would pass the whole suite. A mutation confirmed exactly that before this case was added.
    out = run_hook(hashers="shasum_only", manifest_hash="deadbeefdead")
    check("shasum alone still detects drift", DRIFTED in out, f"stdout={out!r}")
    check("...and is not reported as unhashable", UNHASHED not in out, f"stdout={out!r}")

    width = max(len(c[0]) for c in checks)
    failed = 0
    for label, ok, detail in checks:
        print(f"  [{'ok' if ok else 'FAIL'}] {label.ljust(width)}" + ("" if ok else f"  {detail}"))
        failed += 0 if ok else 1
    print(f"\n{len(checks) - failed} passed, {failed} failed of {len(checks)} checks")
    return 1 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true", help="run the fixtures")
    args = ap.parse_args()
    if not args.selftest:
        ap.error("--selftest is the only mode")
    return selftest()


if __name__ == "__main__":
    sys.exit(main())
