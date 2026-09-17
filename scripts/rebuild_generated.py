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

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Order matters only for readability; none depends on another's output.
#
# THE THIRD FIELD IS WHAT TO `git add`, and it is declared rather than described because the
# closing line used to print a hardcoded `git add docs/ dist/` that stopped being true the moment a
# builder wrote anywhere else — which two of them now do.
BUILDERS = (
    ("coverage page", "build_coverage_artifact.py", ("docs/evidence/coverage.html",)),
    ("wiki reference", "build_wiki.py", ("docs/wiki/",)),
    ("doctrine map", "doctrine_map.py", ("docs/architecture/doctrine-map.html",)),
    ("dist/*.skill", "package_core.py", ("dist/",)),
    ("maintainer skill mirrors", "build_maintainer_skills.py", (".claude/skills/",)),
    ("mandated gems", "derive_mandated_gems.py", ("plugins/rails-flow/mandated_gems.json",)),
)

# A `scripts/*.py --check` gate that this script deliberately does NOT run, and why. Every entry is
# a decision somebody made; `--selftest` refuses a gate that is in neither table, so a new generator
# cannot arrive without one.
NOT_REBUILT = {
    # Reads the licensed corpora (a gitignored nested clone) and its gate SKIPs without them, so
    # running it here would fail on every machine that has not cloned them — including CI. When you
    # DO have the corpora and regenerate `docs/evidence/coverage.md`, rebuild the page too: that is
    # `build_coverage_artifact.py` above, and CLAUDE.md states the pairing.
    "build_coverage.py": "needs the licensed corpora; its own gate skips without them",
    # Validates the CHANGELOG's release headings. Writes nothing — `grep -c write_text` is 0.
    "extract_release_notes.py": "a validator, not a generator — it writes no file",
}


def main() -> int:
    failures: list[str] = []
    for label, script, _outputs in BUILDERS:
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
    paths = sorted({out for _label, _script, outs in BUILDERS for out in outs})
    print(f"all {len(BUILDERS)} rebuilt — `git add {' '.join(paths)}` and the drift gates will "
          f"pass once committed (they compare the blob at HEAD, not the working copy).")
    return 0


def _checked_scripts() -> set[str]:
    """Every `scripts/*.py` the doctor runs with `--check`, read from its gate table.

    THE DOCTOR IS THE REGISTRY, so this cannot be answered from memory and cannot go stale the way
    a second hand-written list would. Only `scripts/` — a plugin's own gates are the plugin's, and
    `rebuild_generated.py` is about this repository's committed surfaces.
    """
    text = (ROOT / "scripts" / "maintainer_doctor.py").read_text(encoding="utf-8")
    return set(re.findall(r'"python3",\s*"scripts/([A-Za-z0-9_]+\.py)",\s*"--check"', text))


def selftest() -> int:
    """Every `--check` generator is classified, and every classification names a real script.

    THE LIST FELL BEHIND TWICE BEFORE ANYTHING WATCHED IT. `build_maintainer_skills.py` (#1004) and
    `derive_mandated_gems.py` were both gated by the doctor and absent here, so `rebuild_generated`
    — the one command that exists so nobody rebuilds four things from memory — rebuilt four of six.
    The failure was invisible because this script had no selftest and no gate of its own.

    Both directions, per #866: an unclassified gate fails, and a classification naming a script that
    no longer exists fails too.
    """
    failures: list[str] = []
    built = {script for _label, script, _outs in BUILDERS}

    overlap = built & NOT_REBUILT.keys()
    if overlap:
        failures.append(f"classified twice, as builder and as excluded: {', '.join(sorted(overlap))}")

    checked = _checked_scripts()
    if not checked:
        failures.append("read no --check gates out of maintainer_doctor.py — the pattern has moved")
    for script in sorted(checked - built - NOT_REBUILT.keys()):
        failures.append(
            f"scripts/{script} has a --check gate but is in neither BUILDERS nor NOT_REBUILT — "
            f"add it as a builder, or exclude it with the reason")

    for script in sorted(built | NOT_REBUILT.keys()):
        if not (ROOT / "scripts" / script).is_file():
            failures.append(f"scripts/{script} is registered here and does not exist")

    for _label, _script, outs in BUILDERS:
        for out in outs:
            if not (ROOT / out).exists():
                failures.append(f"declared output {out} does not exist")

    for f in failures:
        print(f"SELFTEST FAILED: {f}")
    if failures:
        return 1
    print(f"selftest: ok — {len(built)} builder(s), {len(NOT_REBUILT)} excluded with a reason, "
          f"and all {len(checked)} --check gate(s) under scripts/ are classified")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        raise SystemExit(selftest())
    raise SystemExit(main())
