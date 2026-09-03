#!/usr/bin/env python3
"""Rebuild every generated artefact whose bytes are committed. #680.

WHY THIS EXISTS. Three committed files carry the marketplace version — `docs/evidence/coverage.html`,
`docs/wiki/Plugin-Reference.md` and `docs/wiki/Agents-And-Gates.md` — and `dist/*.skill` is a deterministic
build of the skills. Each has its own drift gate, so bumping a version invalidates all of them and
the gates fail until each is rebuilt.

`docs/architecture/doctrine-map.html` (#655) stamps NO version, deliberately: it is read in-tree beside the
sources it describes, where the drift gate is the freshness signal, so it has one fewer non-content
input to be unpassable by. It is rebuilt here anyway, because its registry moves whenever a gate,
guard or rule does — and one command beating four-from-memory is this script's whole reason.

Until now the arm ran four commands, in order, from memory. **The v1.88.0 arm forgot the wiki and the
gate caught it**, which is the gate working and the sequence being memory — the claims-vs-enforcement
shape this repo files bugs about, and one that bites a second maintainer on their first release.

IT RUNS THEM ALL EVEN IF ONE FAILS, and reports every outcome. Stopping at the first failure would
leave the tree half-rebuilt, which is worse than not starting: some gates then pass and some do not,
and the reason is invisible.

    python3 scripts/rebuild_generated.py

Exit 0 when every builder succeeded, 1 otherwise.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Order matters only for readability; none depends on another's output.
BUILDERS = (
    ("coverage page", "build_coverage_artifact.py"),
    ("wiki reference", "build_wiki.py"),
    ("doctrine map", "doctrine_map.py"),
    ("dist/*.skill", "package_core.py"),
)


def main() -> int:
    failures: list[str] = []
    for label, script in BUILDERS:
        path = ROOT / "scripts" / script
        if not path.is_file():
            print(f"[FAIL] {label}: {script} is missing")
            failures.append(label)
            continue
        proc = subprocess.run([sys.executable, str(path)], cwd=ROOT,
                              capture_output=True, text=True, timeout=600)
        if proc.returncode == 0:
            print(f"[ ok ] {label}")
        else:
            # The builder's OWN stderr, verbatim. Paraphrasing it into "rebuild failed" is how a
            # fixable problem reads like a broken toolchain.
            print(f"[FAIL] {label} (exit {proc.returncode})")
            for line in (proc.stderr or proc.stdout).strip().splitlines()[-4:]:
                print(f"         {line}")
            failures.append(label)

    print()
    if failures:
        print(f"{len(failures)} of {len(BUILDERS)} failed: {', '.join(failures)}")
        return 1
    print(f"all {len(BUILDERS)} rebuilt — `git add docs/ dist/` and the drift gates will pass "
          f"once committed (they compare the blob at HEAD, not the working copy).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
