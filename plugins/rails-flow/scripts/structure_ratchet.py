#!/usr/bin/env python3
"""The flat root may not get flatter: a per-layer ratchet with no opinion about names (#1072).

Run:  python3 structure_ratchet.py                 # check against the committed floors
      python3 structure_ratchet.py --set-floor     # re-cut, in its own commit
      python3 structure_ratchet.py --root path
      python3 structure_ratchet.py --selftest

WHY A RATCHET AND NOT A RULE. The right grouping for one app is its domains; another's is different.
A gate that dictates folder names is wrong everywhere it was not written for, and the first team it
is wrong for switches it off -- after which it reports nothing while still looking present. This
repo's own `check_coverage_ratchet.py` settled the same argument in its own words: a fixed threshold
"one set above where a repo sits turns every run red and gets switched off in a week", and
**THE RATCHET IS THE INSTRUMENT**. `setup-flow.md` settles the other half: a custom `app/services`
layout is a **Project Override** -- "Leave it untouched. Never 'repair' a deliberate choice into
vanilla." So a gate naming folders would contradict the command that onboards projects.

WHAT IS MEASURED. Files at the ROOT of each `app/` layer, non-recursive. Layers come from
`check_layer_structure.discover_layers`, so this has no list of its own to go stale -- a hard-coded
list is exactly what hid `app/javascript/controllers` from the first version of that check (#1124).

THE TWO ARMS.

  RISE   -- a root count above its floor. A new flat file in a directory already too flat.
  STALE  -- a root count BELOW its floor. The work was done and the floor was not re-cut, so the
            ratchet has quietly stopped ratcheting. It fails and says to lower it. Without this arm
            a floor left high after one slice silently permits the next slice to undo it.

IT DOES NOT JUDGE THE FLAT CASES. Twelve jobs at the root is fine. The ratchet says "this got worse",
never "this is wrong". A layer with no floor recorded is REPORTED, never failed: a project that adds
`app/queries` has not regressed, it has grown, and failing that is the false positive that gets a
gate switched off. `--set-floor` is how a new layer joins.

IT REPORTS WHAT IT WILL NOT GATE. The flat/namespaced split per layer is printed every run. That
asymmetry is the finding `check_layer_structure` exists to surface, and it needs judgement -- which
gating destroys.

WHAT IT CANNOT DO. It cannot tell you where a file belongs. Deciding that a `Uploads::` namespace in
models deserves a matching one in controllers requires knowing the domain, and no gate knows that.
The ratchet stops the root growing; the doctrine (`directory-structure.md`) says what good looks
like; a person still does the grouping. Saying so here is what should stop someone "strengthening"
this into a taxonomy check later -- which is the version that gets switched off.

NOT APPLICABLE with no floors file: a project is green on day one, told to run `--set-floor`.

Stdlib only, no network. Exit 0 clean or not applicable, 1 findings.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from check_layer_structure import CODE_SUFFIXES, discover_layers

FLOORS = Path(".rails-flow") / "structure-floors.json"


def root_counts(root: Path) -> dict[str, int]:
    """{layer: files directly at the layer's root}, for every layer discovered in the tree."""
    out: dict[str, int] = {}
    for name, base in discover_layers(root):
        files = [p for p in base.rglob("*") if p.is_file() and p.suffix in CODE_SUFFIXES]
        if not files:
            continue
        out[name] = sum(1 for p in files if p.parent == base)
    return out


def split_table(root: Path) -> dict[str, tuple[int, int]]:
    """{layer: (root files, nested files)} -- reported, never gated."""
    out: dict[str, tuple[int, int]] = {}
    for name, base in discover_layers(root):
        files = [p for p in base.rglob("*") if p.is_file() and p.suffix in CODE_SUFFIXES]
        if not files:
            continue
        flat = sum(1 for p in files if p.parent == base)
        out[name] = (flat, len(files) - flat)
    return out


def load_floors(root: Path) -> dict[str, int] | None:
    path = root / FLOORS
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{FLOORS} is not valid JSON: {exc}")
    floors = data.get("floors")
    if not isinstance(floors, dict):
        raise SystemExit(f"{FLOORS} has no `floors` object — re-cut it with --set-floor")
    return {str(k): int(v) for k, v in floors.items()}


def _head(root: Path) -> str:
    try:
        out = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def set_floor(root: Path) -> int:
    counts = root_counts(root)
    if not counts:
        print(f"NOT APPLICABLE: no app/ layers under {root} — nothing to record.")
        return 0
    path = root / FLOORS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "measured_by": "structure_ratchet.py --set-floor",
        "measured_at": _head(root),
        "floors": dict(sorted(counts.items())),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {FLOORS} — {len(counts)} layer(s). Commit this on its own, and say in the message "
          f"whether a drop is a correction or the result of real grouping work.")
    return 0


def findings(counts: dict[str, int], floors: dict[str, int]) -> list[str]:
    out = []
    # Iterate what EXISTS, not what was recorded: a floor for a layer that has gone away is simply
    # skipped, and `--set-floor` drops the row. `.get` with no default so an UNRECORDED layer is
    # `None` rather than an implicit 0 -- growth is not regression.
    for layer in sorted(counts):
        floor = floors.get(layer)
        if floor is None:
            continue
        now = counts[layer]
        if now > floor:
            out.append(
                f"app/{layer}: {now} files at the root, floor is {floor}. A directory already this "
                f"flat got flatter. Group the new file under its domain, or if the root genuinely "
                f"is the right home, re-cut the floor in its own commit and say why.")
        elif now < floor:
            out.append(
                f"app/{layer}: {now} files at the root but the floor is still {floor} — STALE. The "
                f"grouping work was done and the floor was not lowered, so this layer is currently "
                f"free to drift back {floor - now} file(s) without failing. Run --set-floor.")
    return out


def _selftest() -> int:
    ok, bad = 0, []

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    import contextlib
    import io
    import shutil
    import tempfile

    def quiet_set_floor(at: Path) -> None:
        """--set-floor prints guidance meant for a person; in here it would bury a real failure."""
        with contextlib.redirect_stdout(io.StringIO()):
            set_floor(at)

    root = Path(tempfile.mkdtemp(prefix="structure-ratchet-"))
    try:
        (root / "app/models").mkdir(parents=True)
        (root / "app/jobs").mkdir(parents=True)
        for n in ("user", "invoice", "account"):
            (root / f"app/models/{n}.rb").write_text("x\n", encoding="utf-8")
        (root / "app/jobs/sweep_job.rb").write_text("x\n", encoding="utf-8")

        expect("with no floors file the project is not applicable, not failed",
               load_floors(root) is None)
        quiet_set_floor(root)
        floors = load_floors(root)
        expect("--set-floor records what is there, so day one is green",
               floors == {"models": 3, "jobs": 1})
        expect("...and the recorded baseline produces no findings",
               not findings(root_counts(root), floors))

        # MUST FAIL: the RISE arm. A new flat file in a directory already this flat.
        (root / "app/models/payment.rb").write_text("x\n", encoding="utf-8")
        f = findings(root_counts(root), floors)
        expect("a file added at the root of a layer at its floor is a finding",
               len(f) == 1 and "app/models" in f[0])
        expect("...and the finding names both numbers, not just a verdict",
               bool(f) and "4 files at the root" in f[0] and "floor is 3" in f[0])
        # The CONTROL on the same tree: the layer that did not change must stay silent, or a finding
        # would mean only "something somewhere moved".
        expect("...and the untouched layer is not swept up", not any("app/jobs" in x for x in f))

        # MUST PASS: a legitimately flat project. Four models and one job at the root is FINE once
        # recorded -- the ratchet says "this got worse", never "this is wrong".
        quiet_set_floor(root)
        expect("a legitimately flat project passes once its shape is recorded",
               not findings(root_counts(root), load_floors(root)))

        # MUST FAIL: the STALE arm. Real grouping work happened and the floor was not re-cut, so the
        # layer is silently free to drift back. Without this, a ratchet stops ratcheting unnoticed.
        (root / "app/models/billing").mkdir()
        (root / "app/models/payment.rb").rename(root / "app/models/billing/payment.rb")
        (root / "app/models/invoice.rb").rename(root / "app/models/billing/invoice.rb")
        f = findings(root_counts(root), load_floors(root))
        expect("a floor left above the real count fails as STALE",
               len(f) == 1 and "STALE" in f[0])
        expect("...and it says how much drift the stale floor currently permits",
               bool(f) and "back 2 file(s)" in f[0])

        # A layer with no floor recorded is REPORTED, never failed: adding `app/queries` is growth,
        # not regression, and failing it is the false positive that gets a gate switched off.
        quiet_set_floor(root)
        (root / "app/queries").mkdir()
        (root / "app/queries/overdue.rb").write_text("x\n", encoding="utf-8")
        counts = root_counts(root)
        expect("a brand-new layer is discovered", "queries" in counts)
        expect("...but a layer with no floor is not a finding",
               not findings(counts, load_floors(root)))
        # ...and the control: once recorded, it ratchets like any other.
        quiet_set_floor(root)
        (root / "app/queries/stale.rb").write_text("x\n", encoding="utf-8")
        expect("...and once --set-floor records it, it ratchets like any other layer",
               any("app/queries" in x for x in findings(root_counts(root), load_floors(root))))

        expect("the split table reports nested files too, which the gate never judges",
               split_table(root)["models"][1] == 2)

        empty = Path(tempfile.mkdtemp(prefix="structure-ratchet-empty-"))
        try:
            expect("a tree with no app/ measures nothing", not root_counts(empty))
        finally:
            shutil.rmtree(empty, ignore_errors=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    if bad:
        print(f"ran {ok + len(bad)} assertion(s)\n\n{len(bad)} FAILED:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print(f"ran {ok} assertion(s)")
    print("a risen root fails; a stale floor fails; a legitimately flat project and an unrecorded "
          "layer do not")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".", help="project root (default: cwd)")
    ap.add_argument("--set-floor", action="store_true", help="re-cut the floors to what is there now")
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()

    root = Path(args.root).resolve()
    if args.set_floor:
        return set_floor(root)

    counts = root_counts(root)
    if not counts:
        # NOT a pass. Zero findings over zero layers reads exactly like a tidy app.
        print(f"NOT APPLICABLE: no app/ layers under {root} — this check examined nothing.")
        return 0

    table = split_table(root)
    print("  layer                          root  nested")
    for layer, (flat, nested) in table.items():
        print(f"  {layer:<28} {flat:>5} {nested:>7}")
    print("\nThe root column is the ratchet's; the nested column is ADVISORY and is never gated.")

    floors = load_floors(root)
    if floors is None:
        print(f"\nNOT APPLICABLE: no {FLOORS}. This project has no baseline yet, which is not a "
              f"fault — run `--set-floor` and commit it, and you are green on day one.")
        return 0

    unrecorded = sorted(set(counts) - set(floors))
    if unrecorded:
        print(f"\n  note: no floor recorded for {', '.join(unrecorded)} — growth, not regression. "
              f"`--set-floor` adds them.")

    f = findings(counts, floors)
    for item in f:
        print(f"\n  {item}")
    print(f"\n{len(counts)} layer(s) measured against {len(floors)} floor(s); {len(f)} finding(s).")
    return 1 if f else 0


if __name__ == "__main__":
    raise SystemExit(main())
