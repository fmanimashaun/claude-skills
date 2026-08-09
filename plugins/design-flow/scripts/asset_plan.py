#!/usr/bin/env python3
"""Scaffold the asset pipeline, hold the plan of what the product needs, and run it honestly.

Three scripts now sit in a line, and the split is deliberate:

    asset_plan.py       what the product NEEDS      (intent — this file)
    generation_gate.py  whether we MAY make it      (decision)
    generate_asset.py   making it                   (production)

THE PLAN IS NOT THE MANIFEST, and conflating them loses the thing that makes a set look designed.
The plan is **what the product wants**, written once from the brief before any of it exists. The
manifest is **what the project owns**, appended as each asset lands. Keep only the manifest and you
cannot tell a library that is finished from one nobody has finished planning; keep only the plan and
you cannot tell what was actually made. The gap between them IS the remaining work, and `--status`
prints exactly that.

WHY A PLAN AT ALL, rather than generating per surface as the work arrives: generating one at a time
produces a pile, not a set — every piece defensible alone and the family incoherent. Planning first
is what lets one style, one palette and one level of abstraction be chosen across the whole product
while it is still cheap to change.

STATUS IS RECORDED FROM WHAT HAPPENED, never from what was attempted. A row is `done` only once the
asset is on disk; a failure keeps the reason verbatim. A planner that marks rows complete because it
tried is worse than no planner, because the gap it exists to show is the first thing it hides.

SCAFFOLDING WRITES A PLACEHOLDER KEY ON PURPOSE. `generate_asset.py` distinguishes an absent key from
a placeholder and refuses on both, so the scaffolded state is safe: the pipeline is wired, nothing
can be spent, and the message says which step is outstanding rather than reading like an outage.

Exit codes:  0 clean · 1 the plan has rows that did not complete · 2 unusable input or config

Exit 1 after `--run` is normal on the first pass: no key, no aggregator, or a budget ceiling all
leave rows outstanding, and that is the honest report rather than a failure.

Stdlib only, no network of its own.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PLAN_PATH = Path("docs/assets/plan.json")
CONFIG_PATH = Path(".design-flow/generation.json")
PLACEHOLDER_KEY_ENV = "OPENROUTER_API_KEY"

# A planned row must say enough to be GENERATED and enough to be REVIEWED. `why` is the one that
# looks optional and is not: a row nobody can justify is a row nobody should pay for, and it is the
# field that makes a planning pass reviewable by someone who was not in the room.
PLAN_FIELDS = {
    "surface": "the surface class this serves",
    "kind": "static / vector / motion — priced and reused differently",
    "why": "what this asset is FOR; a row nobody can justify should not be bought",
}

STATUSES = ("planned", "done", "failed", "skipped", "awaiting-agent")


def scaffold(root: Path, prd: str = "") -> list[str]:
    """Create what the pipeline needs, and never overwrite what is already there."""
    made = []
    cfg = root / CONFIG_PATH
    if not cfg.is_file():
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(json.dumps({
            "_comment": [
                "The AGENT generates by default. It calls a connected provider MCP (OpenRouter's",
                "`generate-image`) or authors SVG itself -- no API key, no .env, no adapter code.",
                "`--run` marks such rows `awaiting-agent` with the composed prompt; the agent",
                "fulfils each and registers it with `generate_asset.py --record`, which re-runs the",
                "whole gate before the manifest accepts anything.",
                "",
                "Raster generation still COSTS via MCP -- the tool bills the same account. Only",
                "vector-via-agent is genuinely free.",
                "",
                "Set `api_key_env` and a non-agent `aggregator` ONLY for unattended runs, where no",
                "agent is in the loop to call an MCP. That path needs a key; this one does not."
            ],
            "aggregator": "agent",
            "budget_usd": 5.00,
            # PER KIND, because the kinds want different models: only some emit SVG, and no
            # image endpoint emits video.
            #
            # IDs were VERIFIED against OpenRouter's live model list on 2026-08-09. The first draft
            # of this file was not, and shipped two IDs invented from documentation prose -- both
            # 404'd on the first real call. Refresh rather than trusting this comment's date:
            #     python3 asset_plan.py --discover
            #
            # `cost_usd` IS DELIBERATELY UNSET. The model endpoint does not report pricing, so any
            # number here would be invented -- and an invented price is worse than none, because it
            # looks authoritative and the budget then refuses or approves against a figure nobody
            # chose. The gate REFUSES an unpriced rung, so nothing can be bought until you look the
            # price up and write it in. That refusal is the feature.
            "ladders": {
                # THE AGENT IS THE DEFAULT GENERATOR FOR EVERY KIND -- it calls a provider MCP when
                # one is connected, or authors SVG itself. 0.0 is a measured fact for the SVG path
                # and a FLOOR for the MCP path: the MCP bills the account, so put a real figure here
                # before running raster work, or the budget compares against a number that is only
                # true for the free half.
                "static": [{"name": "agent", "cost_usd": 0.0}],
                "vector": [{"name": "agent", "cost_usd": 0.0}],
                # EMPTY until a video route exists: no image endpoint returns video, so a motion row
                # refuses rather than saving a still under a `.webm` name.
                "motion": [],
            },
            "style_reference": "docs/assets/reference.png",
            "briefs": {},
            "acceptance": {},
        }, indent=2) + "\n", encoding="utf-8")
        made.append(str(CONFIG_PATH))
    plan = root / PLAN_PATH
    if not plan.is_file():
        plan.parent.mkdir(parents=True, exist_ok=True)
        plan.write_text(json.dumps({"assets": []}, indent=2) + "\n", encoding="utf-8")
        made.append(str(PLAN_PATH))
    if prd:
        # Re-pinning is the ONLY thing a second scaffold changes. The rows are the user's work and
        # a setup command that resets them on re-run is not idempotent, it is destructive.
        doc = json.loads(plan.read_text(encoding="utf-8"))
        doc["prd"] = {"path": prd, "sha256": fingerprint(root / prd)}
        plan.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        made.append(f"pinned {prd}")
    return made


def fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.is_file() else ""


def discover_models(config: dict) -> dict:
    """Refresh the ladders' model IDs from the provider, because hardcoding them was already wrong.

    The first version of this scaffold shipped two model IDs invented from documentation prose. Both
    404'd on the first real run -- a transcription, exactly what this repo's `derived-artifacts`
    skill exists to warn about, in the file that spends money.

    Only IDS are refreshed. The endpoint does not expose pricing, so `cost_usd` is left ALONE rather
    than zeroed or guessed: a budget compared against a number nobody set is worse than one compared
    against a number someone chose badly, because the second is visible.
    """
    import os
    import urllib.request
    key = os.environ.get(config.get("api_key_env", "")) or ""
    if not key:
        raise SystemExit(f"--discover needs ${config.get('api_key_env')} set; it queries the "
                         f"provider for the current model list.")
    req = urllib.request.Request("https://openrouter.ai/api/v1/images/models",
                                 headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            models = json.loads(resp.read().decode("utf-8")).get("data", [])
    except Exception as exc:                       # noqa: BLE001 - any failure is the same answer
        raise SystemExit(f"could not reach the model list ({exc}); ladders left unchanged.")
    ids = {m.get("id") for m in models if m.get("id")}
    stale = {kind: [r["name"] for r in rungs if r.get("name") not in ids]
             for kind, rungs in (config.get("ladders") or {}).items()}
    return {"available": sorted(ids),
            "vector_capable": sorted(i for i in ids if "vector" in i or "svg" in i),
            "stale_in_config": {k: v for k, v in stale.items() if v}}


def load_doc(root: Path) -> dict:
    path = root / PLAN_PATH
    if not path.is_file():
        raise SystemExit(f"no plan at {PLAN_PATH} — run --scaffold first, then write the rows.")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"{PLAN_PATH} is not valid JSON ({exc})")


RESEARCH_PATH = Path("docs/design/reference-research.json")


def check_research(root: Path) -> list[str]:
    """Reference research must exist BEFORE the plan, because it decides what the plan contains.

    This is a sequencing rule with teeth, and the order is not cosmetic. Research settles the style,
    and the style settles which assets exist at all: a `minimalist-ink` family needs line art on
    brand-coloured grounds, while a `character-world` family needs a recurring cast — different
    rows, different counts, different money. Plan first and you will have costed and possibly bought
    a set the research would not have asked for.

    It is checked rather than advised because the failure is invisible: a plan written without
    research looks exactly like one written with it. Every row has a surface, a kind and a `why`,
    and nothing in the file says the style was picked from the median of what the model had seen.
    """
    path = root / RESEARCH_PATH
    if not path.is_file():
        return [f"no reference research at {RESEARCH_PATH}. Research comes BEFORE the plan: it "
                f"settles the style, and the style settles which assets exist at all. Run the "
                f"research pass first, or the plan is costed against a look nobody chose."]
    return []


def check_prd(root: Path, doc: dict) -> list[str]:
    """Has the brief moved since the plan was written?

    A plan is only as current as the document it was derived from. Products grow surfaces, and a
    library planned against last month's brief is quietly incomplete in a way nothing else reports:
    every row is `done`, the status is clean, and the new surfaces have no rows at all. Comparing a
    fingerprint is cheap and turns that silence into a sentence.
    """
    prd = doc.get("prd") or {}
    if not prd.get("path"):
        return ["no `prd` recorded on the plan, so nothing can tell you when the brief moves. "
                "Re-run --scaffold with --prd <path> to pin it."]
    path = root / prd["path"]
    if not path.is_file():
        return [f"the plan is pinned to {prd['path']}, which no longer exists — re-pin it, or the "
                f"drift check is a gate that cannot fire."]
    if fingerprint(path) != prd.get("sha256"):
        return [f"{prd['path']} has CHANGED since this plan was written. Re-read it and decide "
                f"whether the product grew surfaces the plan does not cover; then re-pin with "
                f"--scaffold --prd {prd['path']}."]
    return []


def reconcile(root: Path, rows: list[dict]) -> list[str]:
    """Every asset the project owns must have a plan row saying why it exists.

    An agent that generates ad-hoc — a surface the seeding pass did not foresee — appends to the
    MANIFEST. If it does not also add a plan row, the plan and the library drift apart and the gap
    between them stops meaning "remaining work". So an unplanned asset is reported here, and the fix
    is to add the row with its rationale and use cases, not to delete the asset.
    """
    manifest = root / "docs/assets/manifest.json"
    if not manifest.is_file():
        return []
    try:
        owned = json.loads(manifest.read_text(encoding="utf-8")).get("assets", [])
    except ValueError as exc:
        return [f"docs/assets/manifest.json is not valid JSON ({exc})"]
    planned = {(r.get("surface"), r.get("kind", "static")) for r in rows}
    return [f"{e.get('name') or e.get('file')}: in the manifest with no plan row "
            f"({e.get('surface')!r}/{e.get('kind', 'static')!r}). An asset generated ad-hoc must be "
            f"added to the plan with its `why` and use cases, or the plan stops describing the "
            f"library it is meant to track."
            for e in owned if (e.get("surface"), e.get("kind", "static")) not in planned]


def load_plan(root: Path) -> list[dict]:
    path = root / PLAN_PATH
    if not path.is_file():
        raise SystemExit(f"no plan at {PLAN_PATH} — run --scaffold first, then write the rows.")
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("assets", [])
    except ValueError as exc:
        raise SystemExit(f"{PLAN_PATH} is not valid JSON ({exc})")


def save_plan(root: Path, rows: list[dict]) -> None:
    (root / PLAN_PATH).write_text(json.dumps({"assets": rows}, indent=2) + "\n", encoding="utf-8")


def check_plan(rows: list[dict], briefs: dict | None = None) -> list[str]:
    """Per-field, per-row. `surface`+`kind` must also be unique — two rows for one slot is a fork."""
    if not rows:
        # An empty plan is UNPLANNED, not finished. Reporting it clean says the planning is done
        # when it has not started -- and the scaffold creates exactly this state, so the very first
        # `--check` after setup would have blessed it. A comment three lines up used to claim this
        # case was caught; it was not, which is the shape this repo names claims-vs-enforcement.
        return ["the plan is empty — no assets are planned yet. Read the brief and write the rows "
                "before running anything; an unplanned library is not a finished one."]
    problems, seen = [], {}
    for i, row in enumerate(rows):
        label = row.get("surface") or f"row {i}"
        for field, why in PLAN_FIELDS.items():
            if not row.get(field):
                problems.append(f"{label}: no `{field}` — {why}")
        status = row.get("status", "planned")
        if status not in STATUSES:
            problems.append(f"{label}: status {status!r} is not one of {', '.join(STATUSES)}")
        if status == "failed" and not row.get("reason"):
            problems.append(f"{label}: failed with no `reason` — a failure nobody can act on will "
                            f"be retried blindly until the budget stops it")
        key = (row.get("surface"), row.get("kind"))
        if key in seen:
            problems.append(f"{label}: a second row for {key[1]!r} on {key[0]!r} (first at row "
                            f"{seen[key]}) — one slot, one asset, or the surface forks")
        seen[key] = i
        # CROSS-CHECK against the config. A row whose surface has no brief is runnable-looking and
        # unrunnable: it reaches the gate, gets refused for a missing style/mood/subject, and burns
        # a round-trip to learn something a join could have said. Checking it here moves the finding
        # from run time to review time, which is the whole point of having a plan at all.
        if briefs is not None and row.get("surface") and row["surface"] not in briefs:
            problems.append(
                f"{label}: no brief for this surface in the config's `briefs` map, so the run will "
                f"refuse it for a missing style/mood/subject. Write the brief before running.")
    return problems


def cheapest_rung(ladder: list[dict]) -> float:
    """The cheapest PRICED rung. An unpriced one is skipped, never counted as free.

    Averaging a missing price to 0 made every unpriced model free, so a plan of them cost nothing
    and the ceiling could not refuse it -- the estimate agreed with the budget by construction.
    The gate refuses an unpriced rung outright; this keeps the ESTIMATE honest in the meantime, so
    `--run`'s preflight does not quietly under-report what a plan will cost.
    """
    priced = [float(r["cost_usd"]) for r in ladder if r.get("cost_usd") is not None]
    return min(priced) if priced else 0.0


def plan_cost(rows: list[dict], config: dict) -> float:
    """What finishing the outstanding rows would cost, at the CHEAPEST rung.

    Cheapest rung because that is where every row starts; a row only climbs when it fails a stated
    acceptance check, and budgeting for a climb nobody has needed yet would refuse plans that are
    affordable. The estimate is therefore a floor, and it is labelled as one wherever it is printed.
    """
    ladder = config.get("ladder") or []
    rung = cheapest_rung(ladder)
    return round(rung * sum(1 for r in rows if r.get("status") not in ("done", "skipped")), 4)


def affordable(rows: list[dict], config: dict, spent: float) -> tuple[list[dict], list[dict]]:
    """Split outstanding rows into (fits, does_not) by priority — GROUP-ATOMIC, not row-greedy.

    This exists because the alternative is worse in a way that is easy to miss: a run that simply
    generates until the money stops produces an ARBITRARY half-built set — whichever rows happened
    to be first — and a half-built set of illustrations is not a cheaper library, it is an
    incoherent one. Choosing which half is the entire value.

    ROW-GREEDY IS NOT ENOUGH, which is the correction here. Assets are not independent: a hero still
    and the motion loop that animates it are one artefact in two files, and buying the loop without
    the still is worse than buying neither — you pay for something that cannot be used. So rows may
    declare a `group`, and a group is ALL OR NOTHING. A group that does not fit whole is skipped
    entirely, and a cheaper later group may still be taken; that is deliberate, because the aim is
    the best usable combination, not the longest list of files.

    `priority` is optional and defaults to plan order. A group takes the BEST priority among its
    members, so marking one row urgent pulls its partner along rather than orphaning it.
    """
    ladder = config.get("ladder") or []
    rung = min((float(r.get("cost_usd", 0)) for r in ladder), default=0.0)
    remaining = float(config.get("budget_usd", 0)) - spent
    outstanding = [r for r in rows if r.get("status") not in ("done", "skipped")]

    # Ungrouped rows are their own group of one, so one code path handles both.
    groups: dict = {}
    for i, row in enumerate(outstanding):
        key = row.get("group") or f"\x00solo-{i}"
        groups.setdefault(key, []).append((i, row))

    ordered = sorted(
        groups.values(),
        key=lambda members: (min(r.get("priority", 10_000) for _, r in members),
                             min(i for i, _ in members)))

    fits, over = [], []
    for members in ordered:
        cost = rung * len(members)
        if cost <= remaining:
            remaining -= cost
            fits.extend(r for _, r in members)
        else:
            over.extend(r for _, r in members)
    return fits, over


def run_plan(root: Path, rows: list[dict], executor: Path, timeout: int) -> list[dict]:
    """Drive each outstanding row through the executor, recording WHAT HAPPENED."""
    for row in rows:
        if row.get("status") == "done":
            continue                      # idempotent: a re-run never re-buys a finished row
        request = {
            "kind": row.get("kind", "static"),
            "tier_refusal": {
                "surface": row["surface"],
                "tier_1_why_not": row.get("tier_1_why_not", ""),
                "tier_2_why_not": row.get("tier_2_why_not", ""),
            },
            "pack": row.get("pack", {}),
        }
        if row.get("library_miss"):
            request["library_miss"] = row["library_miss"]
        proc = subprocess.run(
            [sys.executable, str(executor), "--request", "-", "--timeout", str(timeout)],
            input=json.dumps(request), capture_output=True, text=True, cwd=root)
        if proc.returncode == 0:
            # EXIT 0 IS NOT "DONE". The agent path exits 0 while handing back a BRIEF -- the gate
            # approved, and authorship is still outstanding. Reading the code alone marked the row
            # done with `file: null` and no asset on disk, which is precisely the "recorded from
            # what was attempted" failure this file's own docstring warns about. A row is `done`
            # only when a file is named AND exists.
            try:
                out = json.loads(proc.stdout)
            except ValueError:
                out = {}
            produced = out.get("produced")
            if produced and (root / produced).is_file():
                row["status"] = "done"
                row["file"] = produced
                row.pop("reason", None)
            elif out.get("author") == "agent":
                row["status"] = "awaiting-agent"
                row["write_to"] = out.get("write_to")
                row["prompt"] = out.get("prompt")
                row["reason"] = ("approved — the agent authors this one. Write the file at "
                                 "`write_to` using `prompt`, then re-run with --record.")
            else:
                row["status"] = "failed"
                row["reason"] = ("the run reported success but produced no file on disk; "
                                 "nothing was recorded.")
        else:
            row["status"] = "failed"
            # Verbatim, and from the process that actually refused -- paraphrasing a refusal into
            # "generation failed" is how a fixable config problem reads like a broken provider.
            detail = proc.stdout.strip() or proc.stderr.strip()
            try:
                detail = json.loads(detail).get("refused", detail)
            except ValueError:
                pass
            row["reason"] = detail[:500]
    return rows


def status_report(rows: list[dict]) -> tuple[dict, int]:
    counts = {s: 0 for s in STATUSES}
    for row in rows:
        counts[row.get("status", "planned")] = counts.get(row.get("status", "planned"), 0) + 1
    outstanding = len(rows) - counts["done"] - counts["skipped"]   # awaiting-agent counts
    return counts, outstanding


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scaffold", action="store_true", help="create config + plan, never overwrite")
    ap.add_argument("--prd", default="", help="path to the brief; pins it so drift is detectable")
    ap.add_argument("--check", action="store_true", help="validate the plan is reviewable")
    ap.add_argument("--discover", action="store_true",
                    help="list the provider's current model IDs and flag stale ones in config")
    ap.add_argument("--run", action="store_true", help="generate every outstanding row")
    ap.add_argument("--status", action="store_true", help="plan vs manifest — the remaining work")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--spent", type=float, default=0.0,
                    help="already spent this cycle, so the ceiling is compared against what is left")
    ap.add_argument("--confirm-partial", action="store_true",
                    help="generate only what the budget affords, by priority, leaving the rest planned")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()

    root = Path.cwd()
    if args.scaffold:
        made = scaffold(root, args.prd)
        print("\n".join(f"created {m}" for m in made) or "nothing to create — already scaffolded")
        print(f"\nNext: fill ${PLACEHOLDER_KEY_ENV} in your environment, then write the plan rows.\n"
              f"Until the key is real every generate call refuses, which is the safe state.")
        return 0
    if args.discover:
        cfg = root / CONFIG_PATH
        config = json.loads(cfg.read_text(encoding="utf-8")) if cfg.is_file() else {}
        found = discover_models(config)
        print(json.dumps(found, indent=2))
        if found["stale_in_config"]:
            print("\nThe IDs above under `stale_in_config` are NOT in the provider's list — they "
                  "will 404 at generation time. Replace them, and check pricing yourself: the "
                  "model endpoint does not expose it.")
            return 1
        print("\nEvery configured model ID exists. Pricing is still yours to verify — this "
              "endpoint does not report it.")
        return 0
    if args.check:
        cfg = root / CONFIG_PATH
        briefs = None
        if cfg.is_file():
            try:
                briefs = json.loads(cfg.read_text(encoding="utf-8")).get("briefs", {})
            except ValueError as exc:
                raise SystemExit(f"{CONFIG_PATH} is not valid JSON ({exc})")
        doc = load_doc(root)
        rows = doc.get("assets", [])
        problems = (check_research(root) + check_prd(root, doc)
                    + check_plan(rows, briefs) + reconcile(root, rows))
        print("\n".join(problems) or "plan is reviewable, current with the brief, and reconciled.")
        return 1 if problems else 0
    if args.run:
        rows = load_plan(root)
        cfg = root / CONFIG_PATH
        briefs = json.loads(cfg.read_text(encoding="utf-8")).get("briefs", {}) if cfg.is_file() else None
        problems = check_research(root) + check_plan(rows, briefs)
        if problems:
            # Refuse to spend against a plan that cannot be reviewed. A row with no `why` is one
            # nobody can justify, and finding that out after the bill is the wrong order.
            print("\n".join(problems))
            print("\nrefusing to run an unreviewable plan — fix the rows above first.")
            return 2
        # COST PREFLIGHT. Refuse to start a plan the budget cannot finish, rather than generating
        # until the money stops -- that leaves an ARBITRARY half of the set, and a half-built family
        # of illustrations is not a cheaper library, it is an incoherent one.
        cfg_all = json.loads((root / CONFIG_PATH).read_text(encoding="utf-8")) if (root / CONFIG_PATH).is_file() else {}
        total = plan_cost(rows, cfg_all)
        ceiling = float(cfg_all.get("budget_usd", 0))
        spent = float(args.spent)
        if total > ceiling - spent and not args.confirm_partial:
            fits, over = affordable(rows, cfg_all, spent)
            unprioritised = [r for r in fits + over if "priority" not in r]
            print(json.dumps({
                "estimated_total_usd": total,
                "remaining_usd": round(ceiling - spent, 4),
                "shortfall_usd": round(total - (ceiling - spent), 4),
                "affordable_now": [f"{r['surface']}/{r.get('kind', 'static')}" for r in fits],
                "would_not_fit": [f"{r['surface']}/{r.get('kind', 'static')}" for r in over],
            }, indent=2))
            print("\nThe budget cannot finish this plan. The estimate is a FLOOR — it prices every "
                  "row at the cheapest rung, and a row that fails its acceptance check costs more.")
            if unprioritised:
                print(f"\n{len(unprioritised)} row(s) have no `priority`, so the split above used "
                      f"plan order for them. That is an assumption, not a decision — set `priority` "
                      f"on the rows that matter if this split is wrong.")
            print("\nDecide, then re-run: raise `budget_usd`, drop or defer rows, or pass "
                  "--confirm-partial to generate the affordable ones and leave the rest planned.")
            return 2
        if args.confirm_partial:
            fits, _ = affordable(rows, cfg_all, spent)
            allowed = {id(r) for r in fits}
            for row in rows:
                if row.get("status") not in ("done", "skipped") and id(row) not in allowed:
                    row["status"] = "planned"      # explicitly left for a later run, not attempted
            rows_to_run = [r for r in rows if id(r) in allowed or r.get("status") == "done"]
            run_plan(root, rows_to_run, Path(__file__).with_name("generate_asset.py"), args.timeout)
            save_plan(root, rows)
            counts, outstanding = status_report(rows)
            print(json.dumps(counts, indent=2))
            return 1 if outstanding else 0
        rows = run_plan(root, rows, Path(__file__).with_name("generate_asset.py"), args.timeout)
        save_plan(root, rows)
        counts, outstanding = status_report(rows)
        print(json.dumps(counts, indent=2))
        for row in rows:
            if row.get("status") == "failed":
                print(f"\n{row['surface']} ({row.get('kind')}): {row.get('reason', '')[:300]}")
        return 1 if outstanding else 0
    if args.status:
        doc = load_doc(root)
        rows = doc.get("assets", [])
        counts, outstanding = status_report(rows)
        drift = check_prd(root, doc) + reconcile(root, rows)
        print(json.dumps({"plan": counts, "outstanding": outstanding, "drift": drift}, indent=2))
        return 1 if outstanding or drift else 0

    ap.print_help()
    return 2


def selftest() -> int:
    import tempfile
    checks, failures = 0, []

    def check(label, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failures.append(label)

    # SCAFFOLDING never overwrites, and writes a config that REFUSES until a key is filled in.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        made = scaffold(root)
        check("scaffold creates both files", len(made) == 2)
        cfg = json.loads((root / CONFIG_PATH).read_text())
        check("...and a budget ceiling that the agent path still respects",
              cfg.get("budget_usd") is not None)
        check("...with an empty briefs map to fill", cfg.get("briefs") == {})
        # The AGENT is the default generator for every kind, so no key is scaffolded at all --
        # naming a variable nobody needs is how a placeholder became a documented step for a path
        # that never reads one.
        check("every kind defaults to the agent",
              all(l[0]["name"] == "agent" for l in (cfg["ladders"]["static"],
                                                   cfg["ladders"]["vector"])))
        check("...and no api_key_env is written", "api_key_env" not in cfg)
        check("...with the aggregator set to agent", cfg["aggregator"] == "agent")
        # `motion` is scaffolded EMPTY on purpose: no image endpoint returns video, so a motion row
        # must refuse rather than save a still frame under a `.webm` name.
        check("...motion is empty until a video model is configured",
              cfg["ladders"]["motion"] == [])
        check("...and vector has its own SVG-capable rung",
              len(cfg["ladders"]["vector"]) == 1)
        (root / CONFIG_PATH).write_text('{"aggregator":"mine"}', encoding="utf-8")
        check("a second scaffold overwrites nothing", scaffold(root) == [])
        check("...leaving the edited config intact",
              json.loads((root / CONFIG_PATH).read_text())["aggregator"] == "mine")

    # THE PLAN must be reviewable before it is runnable.
    ok = {"surface": "hero", "kind": "static", "why": "no product UI yet"}
    check("a complete row passes", check_plan([ok]) == [])
    # The scaffold creates an empty plan, so the FIRST check after setup must not bless it.
    check("an empty plan is reported as unplanned",
          any("empty" in p for p in check_plan([])))
    for field in PLAN_FIELDS:
        partial = {k: v for k, v in ok.items() if k != field}
        check(f"a row with no {field} is reported",
              any(f"`{field}`" in p for p in check_plan([partial])))
    check("an unknown status is reported",
          any("status" in p for p in check_plan([{**ok, "status": "maybe"}])))
    # A failure with no reason gets retried blindly until the budget stops it.
    check("a failed row with no reason is reported",
          any("reason" in p for p in check_plan([{**ok, "status": "failed"}])))
    check("...and one WITH a reason is fine",
          check_plan([{**ok, "status": "failed", "reason": "no key"}]) == [])
    # Two rows for one slot fork the surface's look -- the same defect the gate refuses at run time.
    check("two rows for one surface+kind is reported",
          any("second row" in p for p in check_plan([ok, dict(ok)])))
    check("...but a different KIND on the same surface is fine",
          check_plan([ok, {**ok, "kind": "motion"}]) == [])

    # THE CROSS-CHECK. Without it a row looks runnable and is not, and you learn that from a
    # refusal after the run rather than from a review before it.
    check("a row with no brief for its surface is reported",
          any("no brief" in p for p in check_plan([ok], briefs={})))
    check("...and one WITH a brief is fine", check_plan([ok], briefs={"hero": {}}) == [])
    check("...while briefs=None (no config yet) does not fire",
          check_plan([ok], briefs=None) == [])

    # STATUS counts what HAPPENED. `done` and `skipped` are settled; everything else is outstanding.
    counts, outstanding = status_report(
        [{"status": "done"}, {"status": "failed"}, {"status": "planned"}, {"status": "skipped"}])
    check(f"done and skipped are settled (outstanding={outstanding})", outstanding == 2)
    check("counts are per status", counts["done"] == 1 and counts["failed"] == 1)
    # An empty plan is not "finished" -- it is unplanned, and reporting 0 outstanding would say the
    # opposite. It reports 0 because there is nothing to do, which --check catches as an empty plan.
    check("an empty plan has nothing outstanding", status_report([])[1] == 0)

    # RESEARCH BEFORE PLAN. The failure is invisible without this: a plan written without research
    # looks exactly like one written with it, every row complete, and nothing recording that the
    # style came from the median of what the model had seen.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        check("a missing research record is reported",
              any("BEFORE the plan" in m for m in check_research(root)))
        (root / "docs/design").mkdir(parents=True)
        (root / RESEARCH_PATH).write_text('{"job": "x", "references": []}', encoding="utf-8")
        check("...and a present one is not", check_research(root) == [])

    # COST. The estimate prices every row at the CHEAPEST rung, so it is a floor, and settled rows
    # cost nothing -- a re-run that re-priced finished work would refuse plans that are affordable.
    CFG = {"budget_usd": 0.05, "ladder": [{"cost_usd": 0.01}, {"cost_usd": 0.40}]}
    three = [{"surface": "a", "kind": "static"}, {"surface": "b", "kind": "static"},
             {"surface": "c", "kind": "static"}]
    check("cost prices outstanding rows at the cheapest rung", plan_cost(three, CFG) == 0.03)
    check("done and skipped rows cost nothing",
          plan_cost([{**three[0], "status": "done"}, {**three[1], "status": "skipped"}], CFG) == 0.0)
    check("an empty ladder costs nothing rather than crashing", plan_cost(three, {}) == 0.0)

    # AFFORDABILITY. Generating until the money stops leaves an ARBITRARY half of the set; choosing
    # which half is the entire value, so priority decides and plan order is only the fallback.
    fits, over = affordable(three, {**CFG, "budget_usd": 0.02}, spent=0.0)
    check(f"only what fits is taken (fits={len(fits)})", len(fits) == 2 and len(over) == 1)
    check("...and it is the earliest rows by plan order",
          [r["surface"] for r in fits] == ["a", "b"])
    prioritised = [{"surface": "a", "kind": "static"},
                   {"surface": "b", "kind": "static", "priority": 1}]
    fits2, _ = affordable(prioritised, {**CFG, "budget_usd": 0.01}, spent=0.0)
    check("an explicit priority beats plan order", [r["surface"] for r in fits2] == ["b"])
    # Money ALREADY spent must shrink what fits, or the ceiling is compared against the wrong number.
    # 0.05 ceiling - 0.04 spent = 0.01 left, which covers exactly one 0.01 rung.
    fits3, over3 = affordable(three, CFG, spent=0.04)
    check(f"spend so far shrinks what fits (fits={len(fits3)})", len(fits3) == 1)
    check("...and the rest is reported as not fitting", len(over3) == 2)
    fits4, _ = affordable(three, CFG, spent=0.05)
    check("a fully spent budget affords nothing", fits4 == [])
    # A settled row must never be re-offered for spending.
    fits5, _ = affordable([{**three[0], "status": "done"}], CFG, spent=0.0)
    check("a done row is not offered for spending", fits5 == [])

    # GROUPS ARE ALL-OR-NOTHING. A hero still and the motion loop that animates it are one
    # artefact in two files; buying the loop alone is worse than buying neither, because you pay
    # for something that cannot be used.
    pair = [{"surface": "hero", "kind": "static", "group": "hero-set"},
            {"surface": "hero", "kind": "motion", "group": "hero-set"}]
    fits6, over6 = affordable(pair, {**CFG, "budget_usd": 0.01}, spent=0.0)
    check(f"a group that does not fit whole is skipped entirely (fits={len(fits6)})", fits6 == [])
    check("...and both members are reported as not fitting", len(over6) == 2)
    fits7, _ = affordable(pair, {**CFG, "budget_usd": 0.02}, spent=0.0)
    check("...and taken together once it does fit", len(fits7) == 2)
    # A cheaper LATER group may still be taken after an expensive one is skipped -- the aim is the
    # best usable combination, not the longest list of files.
    mixed = pair + [{"surface": "empty", "kind": "static"}]
    fits8, _ = affordable(mixed, {**CFG, "budget_usd": 0.01}, spent=0.0)
    check(f"a solo row is taken when the group cannot be (fits={len(fits8)})",
          [r["surface"] for r in fits8] == ["empty"])
    # The BEST priority in a group pulls its partner along, rather than orphaning it.
    urgent = [{"surface": "a", "kind": "static"},
              {"surface": "hero", "kind": "static", "group": "g", "priority": 1},
              {"surface": "hero", "kind": "motion", "group": "g"}]
    fits9, _ = affordable(urgent, {**CFG, "budget_usd": 0.02}, spent=0.0)
    check("a group takes its best member's priority",
          sorted(r["kind"] for r in fits9) == ["motion", "static"])

    # EXIT 0 IS NOT "DONE". The agent path exits 0 with a brief, and reading the code alone marked
    # the row done with no file on disk -- "recorded from what was attempted", which this file's
    # own docstring forbids.
    import subprocess as _sp
    real_run = _sp.run
    def fake(kind_out):
        return lambda *a, **k: _sp.CompletedProcess(a[0] if a else [], 0, json.dumps(kind_out), "")
    try:
        _sp.run = fake({"author": "agent", "write_to": "docs/assets/x.svg", "prompt": "p"})
        with tempfile.TemporaryDirectory() as td:
            rows = run_plan(Path(td), [{"surface": "s", "kind": "vector", "why": "w"}],
                            Path("exec.py"), 1)
        check("an agent brief is awaiting-agent, not done", rows[0]["status"] == "awaiting-agent")
        check("...and it carries where to write and what to write",
              rows[0].get("write_to") and rows[0].get("prompt"))
        # Success reported with no file on disk is a FAILURE, not a completion.
        _sp.run = fake({"produced": "docs/assets/missing.svg"})
        with tempfile.TemporaryDirectory() as td:
            rows = run_plan(Path(td), [{"surface": "s", "kind": "static", "why": "w"}],
                            Path("exec.py"), 1)
        check("success with no file on disk is failed, not done", rows[0]["status"] == "failed")
    finally:
        _sp.run = real_run
    # awaiting-agent is OUTSTANDING: the asset does not exist yet.
    check("awaiting-agent counts as outstanding",
          status_report([{"status": "awaiting-agent"}])[1] == 1)

    # PRD DRIFT. A library planned against last month's brief is quietly incomplete in a way
    # nothing else reports: every row `done`, status clean, new surfaces with no rows at all.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        prd = root / "PRD.md"
        prd.write_text("v1", encoding="utf-8")
        doc = {"prd": {"path": "PRD.md", "sha256": fingerprint(prd)}, "assets": []}
        check("a matching PRD reports no drift", check_prd(root, doc) == [])
        prd.write_text("v2 — now with a pricing page", encoding="utf-8")
        check("an edited PRD is reported", any("CHANGED" in m for m in check_prd(root, doc)))
        check("an unpinned plan says so", any("no `prd` recorded" in m
                                              for m in check_prd(root, {"assets": []})))
        # A pin at a path that no longer exists is a gate that cannot fire -- say so rather than
        # silently reporting no drift forever.
        check("a pin to a missing file is reported",
              any("no longer exists" in m
                  for m in check_prd(root, {"prd": {"path": "gone.md", "sha256": "x"}})))

    # RECONCILIATION. An ad-hoc asset lands in the MANIFEST; if it never reaches the plan, the gap
    # between them stops meaning "remaining work" and starts meaning nothing.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "docs/assets").mkdir(parents=True)
        (root / "docs/assets/manifest.json").write_text(json.dumps({"assets": [
            {"name": "Ad-hoc spot", "surface": "pricing", "kind": "static"}]}), encoding="utf-8")
        check("an unplanned asset is reported",
              any("no plan row" in m for m in reconcile(root, [])))
        check("...and is silent once planned",
              reconcile(root, [{"surface": "pricing", "kind": "static"}]) == [])
        # Same surface, DIFFERENT kind is a genuinely separate artefact, not the same one.
        check("a motion row does not cover a static asset",
              any("no plan row" in m
                  for m in reconcile(root, [{"surface": "pricing", "kind": "motion"}])))
    check("no manifest yet means nothing to reconcile", reconcile(Path("/nonexistent"), []) == [])

    # SCAFFOLD re-pins the PRD without touching the rows -- a setup command that resets a user's
    # work on re-run is not idempotent, it is destructive.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "PRD.md").write_text("brief", encoding="utf-8")
        scaffold(root, "PRD.md")
        doc = json.loads((root / PLAN_PATH).read_text())
        doc["assets"] = [{"surface": "hero", "kind": "static", "why": "x"}]
        (root / PLAN_PATH).write_text(json.dumps(doc), encoding="utf-8")
        (root / "PRD.md").write_text("brief v2", encoding="utf-8")
        scaffold(root, "PRD.md")
        after = json.loads((root / PLAN_PATH).read_text())
        check("re-pinning preserves the rows", len(after["assets"]) == 1)
        check("...and updates the fingerprint",
              after["prd"]["sha256"] == fingerprint(root / "PRD.md"))
        check("...so drift is clear again", check_prd(root, after) == [])

    # A RUN is idempotent: a done row is never re-bought. Proved without an executor, because
    # reaching one would make this a network test.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        rows = [{"surface": "hero", "kind": "static", "why": "x", "status": "done", "file": "a.png"}]
        out = run_plan(root, rows, Path("/nonexistent/executor.py"), 1)
        check("a done row is skipped entirely", out[0]["status"] == "done")
        check("...and keeps its file", out[0]["file"] == "a.png")

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} asset-plan assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
