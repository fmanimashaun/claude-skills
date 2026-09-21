#!/usr/bin/env python3
"""Prove the toolchain's gates can still FAIL, in this project (#1109).

Run:  python3 check_toolchain_mutations.py            # every shipped guard
      python3 check_toolchain_mutations.py --guard x
      python3 check_toolchain_mutations.py --selftest

WHY THIS IS SEPARATE FROM `check_toolchain_selftests.py`. That one proves a gate still
DISCRIMINATES here -- it runs the checker's own fixtures. This proves the FIXTURES still notice a
break: it edits the checker, runs the selftest, and requires it to fail. A selftest that passes
against a deliberately broken checker is a selftest that has stopped guarding, and it looks
identical to a healthy one from the outside.

Measured upstream when this shipped: four gates written in a single day were partly vacuous, every
one of them passing its own fixtures. Only mutation testing found it.

WHY IT IS NOT IN THE PER-RUN GATE SWEEP, and this is the design rather than an omission. A mutation
catches nothing while you work: it proves a property of the CHECKER, which changes when the
toolchain is upgraded or the environment moves, not when you edit your app. Upstream the full sweep
is 438 of 475 seconds, and spending that on every merge of someone else's CI to re-check our code
would be the cost without the case. Run it at `/rails-flow:setup-flow` and after a toolchain
upgrade -- the two moments the answer can actually change.

WHAT IT CAN SEE. Only guards shipped INSIDE a plugin, whose subject and every dependency live in
that plugin. A guard that spans plugins -- `project_gates` reading three manifests,
`hook_normalize_cmd` proving two plugins share one normaliser -- stays in the marketplace, because
a project that installed one plugin could not verify the claim anyway. That is a real limit and it
is reported, not hidden.

Exit 0 every mutation caught, 1 one or more survived, 3 nothing to run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve()


def plugin_roots(start: Path | None = None) -> list[Path]:
    own = (start or HERE).resolve().parents[1]
    return sorted(p.parent.parent for p in own.parent.glob("*/scripts/mutations"))


def runner(start: Path | None = None) -> Path | None:
    """The marketplace's `mutation_check.py`, when this is a source checkout.

    A consumer project installs the PLUGIN, not the marketplace, so the runner may be absent --
    that is reported as "cannot run", never as a pass.
    """
    own = (start or HERE).resolve().parents[1]
    for candidate in (own.parent.parent / "scripts" / "mutation_check.py",):
        if candidate.is_file():
            return candidate
    return None


def guards(roots: list[Path]) -> list[tuple[str, str]]:
    """(plugin, guard name) for every guard shipped inside a plugin."""
    out = []
    for root in roots:
        for path in sorted((root / "scripts" / "mutations").glob("*.py")):
            if not path.name.startswith("_"):
                out.append((root.name, path.stem))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--guard", default=None, help="run one guard by name")
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    args = ap.parse_args()

    roots = plugin_roots()
    found = guards(roots)

    if args.selftest:
        ok = []
        # DRIVEN BY A SYNTHETIC TREE, not the live one. A first version asserted against the real
        # `plugins/` directory and failed inside the mutation harness for an environmental reason:
        # a staged mutant has no sibling plugins, so discovery legitimately found nothing and the
        # assertion failed without the mutation being the cause. Inject the state; assert values.
        import shutil
        import tempfile
        work = Path(tempfile.mkdtemp(prefix="toolchain-mutations-"))
        try:
            for name, count in (("alpha", 2), ("beta", 1)):
                d = work / name / "scripts" / "mutations"
                d.mkdir(parents=True)
                for i in range(count):
                    (d / f"g{i}.py").write_text("GUARD = None\n", encoding="utf-8")
                (d / "_private.py").write_text("x = 1\n", encoding="utf-8")
            # A plugin with scripts/ but no mutations/ ships no guards and must not be listed.
            (work / "gamma" / "scripts").mkdir(parents=True)
            fake = work / "alpha" / "scripts" / "check_x.py"

            found_roots = plugin_roots(fake)
            ok.append(("plugins carrying shipped guards are found",
                       sorted(r.name for r in found_roots) == ["alpha", "beta"]))
            ok.append(("...a plugin shipping no mutations/ is NOT listed",
                       "gamma" not in [r.name for r in found_roots]))
            g = guards(found_roots)
            ok.append(("...and each yields its guards, by plugin",
                       sorted(g) == [("alpha", "g0"), ("alpha", "g1"), ("beta", "g0")]))
            # `_`-prefixed files are package plumbing, never guards.
            ok.append(("a leading-underscore file is not a guard",
                       not any(n.startswith("_") for _, n in g)))
            ok.append(("a tree with no plugins finds nothing AND reports nothing", not guards([])))
        finally:
            shutil.rmtree(work, ignore_errors=True)
        bad = [label for label, cond in ok if not cond]
        if bad:
            print(f"ran {len(ok)} assertion(s)\n\n{len(bad)} FAILED:", file=sys.stderr)
            for b in bad:
                print(f"  - {b}", file=sys.stderr)
            return 1
        print(f"ran {len(ok)} assertion(s)")
        print(f"{len(found)} shipped guard(s) discovered across {len(roots)} plugin(s)")
        return 0

    if not found:
        # NOT a pass. Zero guards run reads exactly like a healthy toolchain.
        print("NOT APPLICABLE: no plugin ships a scripts/mutations/ directory — this proved "
              "nothing about whether the gates can still fail.")
        return 3

    run = runner()
    if run is None:
        print(f"CANNOT RUN: {len(found)} shipped guard(s) are installed, and the marketplace's "
              f"mutation_check.py is not — so nothing here proved the gates can fail. This is a "
              f"limitation of an installed plugin, not a finding about your repo.")
        return 3

    cmd = [sys.executable, str(run)]
    if args.guard:
        cmd += ["--guard", args.guard]
    done = subprocess.run(cmd, capture_output=True, text=True)
    print(done.stdout.strip() or done.stderr.strip())
    print(f"\n{len(found)} shipped guard(s) across {len(roots)} plugin(s).")
    print("Guards that span plugins stay in the marketplace and are NOT covered here — a project "
          "that installed one plugin could not verify a cross-plugin claim.")
    return 0 if done.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
