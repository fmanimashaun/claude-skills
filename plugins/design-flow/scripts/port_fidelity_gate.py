#!/usr/bin/env python3
"""port_fidelity_gate.py -- the `port-fidelity` check: every canvas manifest under docs/design has a port report,
and every pair is clean under `canvas_manifest.py check` (#908). n/a (exit 3) when no manifest exists yet."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", default="docs/design", help="where the canvas manifests and port reports live")
    a = ap.parse_args(argv)                      # project_gates asserts every check's script answers --help
    root = Path(a.root)
    manifests = sorted(root.rglob("*.manifest.json")) if root.is_dir() else []
    if not manifests:
        print(f"n/a: no *.manifest.json under {root} -- `canvas_manifest.py extract` writes one per canvas")
        return 3
    bad = 0
    for m in manifests:
        report = m.with_name(m.name.replace(".manifest.json", ".port-report.json"))
        if not report.is_file():
            print(f"- {m}: no port report beside it ({report.name}) -- the port is not accounted for at all")
            bad += 1
            continue
        r = subprocess.run([sys.executable, str(HERE / "canvas_manifest.py"), "check", str(m), "--report", str(report), "--root", "."],
                           capture_output=True, text=True)
        if r.returncode != 0:
            print(f"- {m}: {r.stdout.strip().splitlines()[-1] if r.stdout.strip() else 'check failed'}")
            for line in r.stdout.splitlines()[:8]:
                if line.startswith("- "):
                    print("  " + line)
            bad += 1
    print(f"{len(manifests)} manifest(s), {bad} with gaps" if bad else f"{len(manifests)} manifest(s), every port accounted for")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
