#!/usr/bin/env python3
"""Do the three modules agree on where design-flow's assets and prompts live?

#625/#628/#629 pinned a layout: under the assets dir, `assets-library/` holds the finished
artefacts and `prompts-library/` holds the prompt library, while the indexes (`plan.json`,
`plan.md`, `manifest.json`) stay at the root. Three modules encode that:

    asset_plan.py       LIBRARY_DIR / PROMPTS_DIR   -- creates both in scaffold()
    generate_asset.py   ASSET_LIBRARY               -- writes every produced asset there
    prompt_library.py   PROMPT_DIR                  -- writes prompts.json / prompts.md there

`asset_plan.py` holds its two as LITERALS rather than importing them, because it is deliberately
standalone -- the other two pull in `generation_gate`. That duplication is fine right up until the
day someone moves one and not the others, at which point `--scaffold` creates a folder nothing
writes to and `--run` writes into a folder the scaffold never made. Nothing else in the repo would
notice: both halves keep working, on different paths.

So this is the enforcement half of a claim `asset_plan.py`'s own comment makes. It checks two
things, and the second is the one that matters:

  1. The constants are equal.
  2. `scaffold()` ACTUALLY CREATES the folders the other two write into -- run for real in a
     tempdir, not inferred from reading the source. A constant can agree while the code that was
     supposed to use it does not.

Exit 0 clean, 1 with findings.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "plugins" / "design-flow" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import asset_plan  # noqa: E402
import generate_asset  # noqa: E402
import prompt_library  # noqa: E402


def check() -> list[str]:
    findings: list[str] = []

    if asset_plan.LIBRARY_DIR != generate_asset.ASSET_LIBRARY:
        findings.append(
            f"asset_plan.LIBRARY_DIR ({asset_plan.LIBRARY_DIR}) and generate_asset.ASSET_LIBRARY "
            f"({generate_asset.ASSET_LIBRARY}) disagree. --scaffold would create one folder and "
            f"--run would write assets into another; both would look like they worked.")
    if asset_plan.PROMPTS_DIR != prompt_library.PROMPT_DIR:
        findings.append(
            f"asset_plan.PROMPTS_DIR ({asset_plan.PROMPTS_DIR}) and prompt_library.PROMPT_DIR "
            f"({prompt_library.PROMPT_DIR}) disagree. The scaffolded prompts folder would stay "
            f"empty while the library wrote itself somewhere nobody was told to look.")

    # THE INDEXES STAY AT THE ROOT. Moving one is a decision, not a refactor: every doc and command
    # that names `docs/assets/manifest.json` would silently point at nothing.
    for name, path in (("plan", asset_plan.PLAN_PATH), ("plan view", asset_plan.RENDER_PATH)):
        if path.parent != Path("docs/assets"):
            findings.append(f"the {name} index moved to {path.parent}. The layout decision keeps "
                            f"the indexes at the assets-dir root and the CONTENTS in the two "
                            f"subfolders; moving an index breaks every doc that names its path.")

    # BEHAVIOUR, not constants. Run the real scaffold and look at what is on disk -- a constant can
    # agree perfectly while the code that should have used it does not.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        asset_plan.scaffold(root)
        for label, rel in (("assets", asset_plan.LIBRARY_DIR), ("prompts", asset_plan.PROMPTS_DIR)):
            if not (root / rel).is_dir():
                findings.append(f"--scaffold did not create the {label} folder ({rel}). #625/#628/"
                                f"#629 require both destinations to exist BEFORE the first --run.")
            elif not (root / rel / "README.md").is_file():
                findings.append(
                    f"{rel} has no README.md. Git does not track an empty directory, so without "
                    f"one the folder exists only on the machine that scaffolded it and everyone "
                    f"else clones a layout with the destinations missing.")
        # The produced-asset path must land INSIDE the scaffolded folder, not merely near it.
        target = generate_asset.agent_target(root, {"surface": "s", "kind": "static"})
        if not str(target).startswith(str(root / asset_plan.LIBRARY_DIR)):
            findings.append(f"generate_asset writes to {target}, which is not inside the "
                            f"scaffolded {asset_plan.LIBRARY_DIR}.")
        if not str(root / prompt_library.LIBRARY_PATH).startswith(
                str(root / asset_plan.PROMPTS_DIR)):
            findings.append(f"the prompt library writes to {prompt_library.LIBRARY_PATH}, which is "
                            f"not inside the scaffolded {asset_plan.PROMPTS_DIR}.")
    return findings


def selftest() -> int:
    """Prove the check FIRES as well as passes — a gate that cannot fail is not a gate."""
    failures = []

    def ok(label: str, cond: bool) -> None:
        print(f"  {'ok  ' if cond else 'FAIL'}  {label}")
        if not cond:
            failures.append(label)

    ok("the repo as it stands is clean", check() == [])

    real = asset_plan.LIBRARY_DIR
    try:
        asset_plan.LIBRARY_DIR = Path("docs/assets/somewhere-else")
        found = check()
        ok("a disagreeing constant is caught", any("disagree" in f for f in found))
        # The SAME mutation must also trip the behavioural half, which is the half that would
        # survive someone "fixing" the constants to match while the folder went uncreated.
        ok("...and the scaffold half sees it too",
           any("did not create" in f or "not inside" in f for f in found))
    finally:
        asset_plan.LIBRARY_DIR = real

    real_scaffold = asset_plan.scaffold
    try:
        asset_plan.scaffold = lambda root, prd="": []
        ok("a scaffold that creates nothing is caught",
           any("did not create" in f for f in check()))
    finally:
        asset_plan.scaffold = real_scaffold

    real_plan = asset_plan.PLAN_PATH
    try:
        asset_plan.PLAN_PATH = Path("docs/assets/assets-library/plan.json")
        ok("an index moved into a contents folder is caught",
           any("index moved" in f for f in check()))
    finally:
        asset_plan.PLAN_PATH = real_plan

    ok("and it is clean again afterwards", check() == [])
    print(f"\n{len(failures)} failed" if failures else "\nall passed")
    return 1 if failures else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    problems = check()
    for p in problems:
        print(f"LAYOUT: {p}")
    print("asset layout: the scaffold, the generator and the prompt library agree."
          if not problems else f"{len(problems)} finding(s).")
    raise SystemExit(1 if problems else 0)
