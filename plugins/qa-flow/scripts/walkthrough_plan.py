#!/usr/bin/env python3
"""Turn `qa/qa.config.yml` -> `walkthrough:` into the plan a journey walk runs from -- or refuse.

Run:  python3 walkthrough_plan.py --config qa/qa.config.yml            # the plan, as JSON on stdout
      python3 walkthrough_plan.py --config qa/qa.config.yml --check    # validate only, print nothing
      python3 walkthrough_plan.py --selftest

WHY THIS IS A SCRIPT (#993). `/qa-flow:walkthrough` walks every persona's whole journey in a live
browser and judges each page against the spec's intent. Everything it needs is project knowledge
nobody can guess: who the personas are, how each one REALLY signs in (a fixture session, a
password plus a dev-inbox code, a password plus an authenticator, a magic link), which documents
describe the journey, and which model calls may stand in for an external system. An agent that
starts without those improvises them -- signs everyone in by cookie, reads no spec, stands in for
whatever is convenient -- and the report cannot say what it measured. So the command refuses to
run until this block exists and is whole, and this script is the refusal.

THE RULES, each a measurement over the block, never taste:

  no-block           the `walkthrough:` section is absent
  no-personas        it names no persona
  bad-recipe         a persona's sign-in recipe is not one this plugin knows how to drive
  no-journeys        it names no journey document
  missing-journey    a named journey document does not exist
  bad-viewport       a viewport is not a positive integer
  bands-uncovered    the viewports do not include one in each of the three bands -- compact
                     (below 640), medium (640-1023) and expanded (1024 and up), the Tailwind
                     `sm` / `lg` edges `responsive.md` builds its bands on. Three widths is the
                     point: every layout defect the walk exists to find was invisible at one.

`stand_ins` is optional. When present each entry is echoed into the plan verbatim so the report can
name every stand-in it used; a walk may never call a model method the block does not list.

Exit codes:  0 = a plan was produced  ·  2 = refused, with every finding on stderr

Stdlib only, no YAML dependency: it reads through `qa_config.load_section`, the one reader.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qa_config  # noqa: E402 -- sibling module, one reader for qa.config.yml (#792)

SECTION = "walkthrough"

# Every way this plugin knows how to sign a persona in. A recipe outside this set is not a
# typo to be tolerated: the walker would have to invent the steps.
RECIPES = frozenset({
    "fixture-session",   # a session id minted by the project's fixture task, written as the cookie
    "password",          # email + password, no second factor
    "password+code",     # email + password, then a one-time code read from the dev inbox
    "password+totp",     # email + password, then an authenticator code from a known secret
    "magic-link",        # a sign-in link read from the dev inbox
})

DEFAULT_VIEWPORTS = (1440, 820, 390)
COMPACT_MAX, EXPANDED_MIN = 639, 1024   # Tailwind `sm` is 640, `lg` is 1024 -- responsive.md §4


def _band(width: int) -> str:
    if width <= COMPACT_MAX:
        return "compact"
    if width >= EXPANDED_MIN:
        return "expanded"
    return "medium"


def plan(config: Path, root: Path) -> tuple[dict | None, list[str]]:
    """(plan, findings). A plan is produced only when there are no findings."""
    block = qa_config.load_section(config, SECTION)
    if not block:
        return None, [f"no-block: {config} has no `{SECTION}:` section -- declare personas, "
                      f"sign-in recipes and journey documents before walking"]
    findings: list[str] = []

    personas_raw = block.get("personas")
    personas: dict[str, str] = {}
    if not isinstance(personas_raw, dict) or not personas_raw:
        findings.append("no-personas: `walkthrough.personas` names nobody -- a walk with no persona "
                        "signs in as no one and measures the landing page")
    else:
        for name, recipe in personas_raw.items():
            values = recipe if isinstance(recipe, list) else [recipe]
            chosen = values[0] if values else ""
            if chosen not in RECIPES:
                findings.append(f"bad-recipe: persona {name!r} signs in by {chosen!r}, which this plugin "
                                f"cannot drive -- one of {', '.join(sorted(RECIPES))}")
            personas[name] = chosen

    journeys = [str(j) for j in (block.get("journeys") or [])]
    if not journeys:
        findings.append("no-journeys: `walkthrough.journeys` names no document -- a page judged against "
                        "no spec is judged against taste")
    for j in journeys:
        if not (root / j).is_file():
            findings.append(f"missing-journey: {j} does not exist under {root}")

    raw_viewports = block.get("viewports") or [str(v) for v in DEFAULT_VIEWPORTS]
    viewports: list[int] = []
    for v in raw_viewports:
        try:
            width = int(str(v))
            if width <= 0:
                raise ValueError
        except ValueError:
            findings.append(f"bad-viewport: {v!r} is not a positive integer width")
            continue
        viewports.append(width)
    bands = {_band(w) for w in viewports}
    for band in ("compact", "medium", "expanded"):
        if viewports and band not in bands:
            findings.append(f"bands-uncovered: no {band} viewport among {viewports} -- three widths is "
                            f"the point, one per band (compact <640, medium 640-1023, expanded >=1024)")

    stand_ins = [str(s) for s in (block.get("stand_ins") or [])]

    if findings:
        return None, findings
    return {
        "personas": personas,
        "journeys": journeys,
        "viewports": viewports,
        "stand_ins": stand_ins,
        "rows": [{"persona": p, "viewport": w, "band": _band(w)} for p in personas for w in viewports],
        "base_url": os.environ.get("QA_BASE_URL", ""),
    }, []


# ---------------------------------------------------------------------------------------------
# Selftest -- every rule fires on the input it exists for, and a whole block is silent.
# ---------------------------------------------------------------------------------------------

_GOOD = """\
base_url: env:QA_BASE_URL

walkthrough:                       # who walks, how they sign in, what they are judged against
  personas:
    guest:       [password+code]   # applicant: local password, code from the dev inbox
    admin:       [fixture-session]
    root:        [password+totp]
    it:          [magic-link]
  journeys:
    - docs/roles/admin.md
    - docs/routes.md
  viewports:   [1440, 820, 390]
  stand_ins:
    - "bin/rails runner 'Contract.find_by!(public_id: ARGV[0]).record_signature!'"
"""


def selftest() -> int:
    failures: list[str] = []

    def case(label: str, text: str, *, fires: str | None, journeys: tuple[str, ...] = ("docs/roles/admin.md", "docs/routes.md")):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for j in journeys:
                (root / j).parent.mkdir(parents=True, exist_ok=True)
                (root / j).write_text("# spec\n", encoding="utf-8")
            cfg = root / "qa.config.yml"
            cfg.write_text(text, encoding="utf-8")
            result, findings = plan(cfg, root)
        if fires is None:
            if findings or result is None:
                failures.append(f"{label}: expected a plan, got {findings}")
            return result
        if not any(f.startswith(fires) for f in findings):
            failures.append(f"{label}: expected `{fires}`, got {findings}")
        if result is not None:
            failures.append(f"{label}: a plan was produced despite findings")
        return result

    p = case("a whole block yields a plan", _GOOD, fires=None)
    if p:
        if p["personas"] != {"guest": "password+code", "admin": "fixture-session", "root": "password+totp", "it": "magic-link"}:
            failures.append(f"personas parsed wrongly: {p['personas']}")
        if p["viewports"] != [1440, 820, 390]:
            failures.append(f"viewports parsed wrongly: {p['viewports']}")
        if len(p["rows"]) != 12 or {r["band"] for r in p["rows"]} != {"compact", "medium", "expanded"}:
            failures.append(f"rows are not persona x viewport with bands: {p['rows'][:3]}")
        if p["stand_ins"] != ["bin/rails runner 'Contract.find_by!(public_id: ARGV[0]).record_signature!'"]:
            failures.append(f"stand-ins not echoed verbatim: {p['stand_ins']}")
    case("no block", "base_url: x\ncoverage:\n  exclude: []\n", fires="no-block")
    case("no personas", _GOOD.replace("  personas:\n    guest:       [password+code]   # applicant: local password, code from the dev inbox\n    admin:       [fixture-session]\n    root:        [password+totp]\n    it:          [magic-link]\n", "  personas: []\n"), fires="no-personas")
    case("a recipe the plugin cannot drive", _GOOD.replace("[fixture-session]", "[cookie]"), fires="bad-recipe")
    case("no journeys", _GOOD.replace("  journeys:\n    - docs/roles/admin.md\n    - docs/routes.md\n", "  journeys: []\n"), fires="no-journeys")
    case("a journey file that does not exist", _GOOD, fires="missing-journey", journeys=("docs/roles/admin.md",))
    case("a viewport that is not a width", _GOOD.replace("[1440, 820, 390]", "[1440, wide, 390]"), fires="bad-viewport")
    case("two desktop widths and no phone", _GOOD.replace("[1440, 820, 390]", "[1440, 1280, 820]"), fires="bands-uncovered")
    case("the default viewports cover all three bands", _GOOD.replace("  viewports:   [1440, 820, 390]\n", ""), fires=None)
    case("stand-ins are optional", _GOOD.split("  stand_ins:")[0], fires=None)

    if failures:
        print("walkthrough_plan selftest: FAIL")
        for f in failures:
            print(f"  {f}")
        return 1
    print("walkthrough_plan selftest: ok -- 7 rules fire on their input, 3 whole blocks yield a plan")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--config", default="qa/qa.config.yml")
    ap.add_argument("--root", default=".", help="directory journey paths are relative to (the project root)")
    ap.add_argument("--check", action="store_true", help="validate only; print nothing on success")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    result, findings = plan(Path(a.config), Path(a.root))
    if findings:
        print(f"walkthrough_plan: refused -- {len(findings)} finding(s) in {a.config}:", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        return 2
    if not a.check:
        json.dump(result, sys.stdout, indent=2)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
