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

THE SCAFFOLDED STATE IS SAFE, and no longer by holding a placeholder API key. It writes
`aggregator: "agent"` and no key at all, because the default generator is the agent itself — it
calls a connected provider MCP or authors SVG directly. What makes the state safe now is that the
paid rungs ship UNPRICED and an unpriced row is refused before the executor runs, so nothing can be
bought until someone looks a price up and writes it in. (This paragraph described the placeholder
key for two releases after the scaffold stopped writing one, which is the shape of defect this
file's own gates exist to catch: doctrine outliving the code it describes.)

Exit codes:  0 clean · 1 the plan has rows that did not complete · 2 unusable input or config

Exit 1 after `--run` is normal on the first pass: no key, no aggregator, or a budget ceiling all
leave rows outstanding, and that is the honest report rather than a failure.

Stdlib only, no network of its own.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

PLAN_PATH = Path("docs/assets/plan.json")
CONFIG_PATH = Path(".design-flow/generation.json")
RENDER_PATH = Path("docs/assets/plan.md")
# #625/#628/#629. The two destinations the scaffold creates up front. Kept as literals rather than
# imported from `generate_asset`/`prompt_library`, because those import `generation_gate` and this
# module is deliberately standalone -- but `check_asset_layout.py` asserts all three agree, so the
# duplication cannot rot into a disagreement.
LIBRARY_DIR = Path("docs/assets/assets-library")
PROMPTS_DIR = Path("docs/assets/prompts-library")

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
                # MOTION GOES VIA THE VIDEO ENDPOINT, which is asynchronous: submit, poll,
                # download. Doctrine here previously said motion had no route -- a true statement
                # about the IMAGE endpoint that was allowed to stand as a claim about the provider,
                # so every motion row refused. IDs verified against the live catalogue 2026-08-09
                # (21 video models); refresh with `--discover`. Price is UNSET because the catalogue
                # does not report it and video is the most expensive thing here by an order of
                # magnitude -- the gate refuses an unpriced rung, which is the right default.
                # MOTION IS UI MOTION: Lottie JSON or animated SVG, authored by the agent for
                # nothing, recoloured from tokens, diffable in review. This was pointed at a video
                # model for one release, which routed a loading spinner through footage generation
                # -- the cheap common case paying the expensive rare case's price.
                "motion": [{"name": "agent", "cost_usd": 0.0}],
                # VIDEO IS FOOTAGE, and a different endpoint: asynchronous submit/poll/download.
                # Right for a marketing hero and almost nothing else. ID verified against the live
                # catalogue 2026-08-09 (21 video models); UNPRICED because it is the most expensive
                # rung here by an order of magnitude and the gate should refuse until you choose.
                "video": [{"name": "minimax/hailuo-3", "cost_usd": None}],
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

    # #625/#628/#629 — MAINTAINER DECISION on those issues: both destinations exist BEFORE the first
    # `--run`, so nothing has to invent a folder mid-generation. The indexes stay at the assets-dir
    # root (`plan.json`, `plan.md`, `manifest.json` describe the contents); these two folders hold
    # the contents themselves.
    #
    # EACH GETS A README RATHER THAN A `.gitkeep`. Git does not track an empty directory, so a bare
    # mkdir gives the scaffolding machine a layout that nobody else who clones the project ever
    # sees -- the invisible-deliverable failure this repo has hit before. A README makes the folder
    # tracked AND says what belongs in it, which a zero-byte sentinel does not.
    for rel, blurb in (
        (LIBRARY_DIR, "# Assets library\n\nFinished, persisted visual assets — the PNG/SVG/MP4 "
                      "files themselves.\n\nWritten here by `generate_asset.py`. The index that "
                      "says what each one is FOR, and where it may be used, is\n"
                      "`../manifest.json`; the plan of what is still outstanding is `../plan.md`.\n"),
        (PROMPTS_DIR, "# Prompts library\n\nOne entry per prompt that reached a provider: the "
                      "prompt verbatim, the model, the estimated and\nactual cost, the use cases, "
                      "and the verdict.\n\n`prompts.json` is the source. `prompts.md` is a "
                      "**generated** view of it — do not hand-edit that one;\nrebuild it with "
                      "`prompt_library.py --render` and check it with `--check`.\n\nIt exists so a "
                      "brand change does not mean paying again for work already done.\n"),
    ):
        (root / rel).mkdir(parents=True, exist_ok=True)
        readme = root / rel / "README.md"
        if not readme.is_file():
            readme.write_text(blurb, encoding="utf-8")
            made.append(str(rel) + "/")
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
    # `api_key_env` is deliberately ABSENT from a scaffolded config -- the agent path needs no key.
    # So name a real variable here rather than interpolating the missing setting, which printed
    # "--discover needs $None set" on every default install: a message that reads like a bug in the
    # tool when the actual answer is "this one command needs a key the rest of the flow does not".
    named = config.get("api_key_env") or "OPENROUTER_API_KEY"
    key = os.environ.get(named) or ""
    if not key:
        raise SystemExit(
            f"--discover needs ${named} set: it is the one command here that talks to the provider "
            f"directly, to list the current model IDs. The generation path itself does not need a "
            f"key — the agent calls a connected MCP or authors the asset — so this is not a missing "
            f"setup step, just a prerequisite for this command.")
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

# #632. How many surfaces a declared signature exception may claim before it stops being one.
#
# DEFAULTING TO 1 RATHER THAN TO UNLIMITED is the decision that keeps this mechanism from becoming
# the hole in the rule it carves. A "signature device" works by SCARCITY -- one luminous prism at
# the hero, and the ink line-work everywhere else. Used on six surfaces it is no longer punctuation,
# it is a second family, which is precisely the mixed set the one-style rule exists to prevent. So
# an exception declared without a ceiling gets the tightest one, and the refusal states the number
# so the default is never a surprise. Raising it stays possible and stays deliberate.
DEFAULT_RATION = 1


def signature_exceptions(record: dict) -> dict[str, dict]:
    """The research's declared, justified exceptions to its own chosen style, keyed by style.

    #632. The one-style rule conflated "the project's authored family style" with "the style of
    every generated asset", and a real two-part system has no way to say otherwise: a family of
    `minimalist-ink` line marks authored as SVG (needing no generation at all) plus ONE rationed
    `3d-render` signature device. Briefing the exception tripped the style refusal; not briefing it
    tripped the orphan-manifest check -- so the single asset in the project that actually cost money
    was forced to live outside the plan, losing exactly the reproducibility and spend tracking the
    plan exists to provide.

    TOLERANT ON PURPOSE. An entry with no `style` or no `why` is skipped here rather than raised on,
    because this function reads a record whose SHAPE is `research_record.check`'s job. Two checkers
    reporting one defect is the "one cause, N findings" failure; the record's own checker says it
    once, clearly, and this one simply does not honour an exception nobody justified -- which is the
    strict default, so a malformed record can never loosen the rule.
    """
    out: dict[str, dict] = {}
    for entry in record.get("signature_exceptions") or []:
        if not isinstance(entry, dict):
            continue
        style, why = entry.get("style"), entry.get("why")
        if not style or not str(why or "").strip():
            continue
        try:
            cap = int(entry.get("max", DEFAULT_RATION))
        except (TypeError, ValueError):
            cap = DEFAULT_RATION
        out[str(style)] = {"why": str(why), "max": max(0, cap)}
    return out


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
    if path.is_file():
        # THE RESEARCH DECIDES THE STYLE, and this is the join that makes that true rather than
        # hoped. Without it a project can research monochrome ink line-work and brief a 3D render,
        # and nothing notices -- the research record becomes a box that was ticked rather than a
        # decision anything downstream honours. Every brief must carry the style the research chose.
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            record = {}
        chosen = record.get("style")
        exceptions = signature_exceptions(record)
        cfg = root / CONFIG_PATH
        if chosen and cfg.is_file():
            try:
                briefs = json.loads(cfg.read_text(encoding="utf-8")).get("briefs") or {}
            except ValueError:
                briefs = {}
            allowed = {chosen} | set(exceptions)
            off = [s for s, b in briefs.items() if b.get("style") and b["style"] not in allowed]
            if off:
                # NAME THE DECLARED EXCEPTIONS in the refusal. Without them the message reads as
                # "one style, ever" and the reader's only visible move is to change the brief --
                # which is what forced a deliberately-paid signature asset out of the plan entirely
                # (#632). The mechanism has to be discoverable from the refusal that blocks you.
                extra = (f" Declared signature exception(s): {', '.join(sorted(exceptions))}."
                         if exceptions else
                         " A deliberate second style is expressible — declare it in the research as "
                         "a `signature_exceptions` entry with its own `why`, and it becomes a "
                         "tracked, rationed part of the system rather than drift.")
                # QUOTED. Unquoted, a surface called `empty` or `pending` reads as an adjective
                # -- "but empty brief(s) name a different style" -- and the reader hunts for a
                # problem with emptiness rather than for the surface named `empty`.
                named = ', '.join(repr(s) for s in sorted(off))
                return [f"the research chose {chosen!r}, but {named} brief(s) name "
                        f"a different style. One family, one style -- a set that mixes them is the "
                        f"pile this whole path exists to avoid, and it is invisible once shipped. "
                        f"Change the briefs, or re-open the research and choose again.{extra}"]
            # THE RATION IS THE WHOLE POINT. An exception with no ceiling is not an exception, it is
            # a second family with paperwork -- and a second family is exactly what the one-style
            # rule exists to prevent. So `max` defaults to 1 rather than to unlimited, and the
            # refusal says so, because a default that surprises is worse than one that is stated.
            over = []
            for style in sorted(exceptions):
                cap = exceptions[style]["max"]
                claimants = sorted(s for s, b in briefs.items() if b.get("style") == style)
                if len(claimants) > cap:
                    over.append(
                        f"{style!r} is a RATIONED signature exception capped at {cap}, but "
                        f"{len(claimants)} brief(s) claim it ({', '.join(claimants)}). A signature "
                        f"device works by scarcity: used everywhere it stops punctuating and "
                        f"becomes the family, which is the mixed set the one-style rule prevents. "
                        f"Raise `max` in the research deliberately, or move the surplus surfaces "
                        f"back to {chosen!r}.")
            if over:
                return over
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


def load_config(root: Path) -> dict:
    """The generation config, or {} when there is none yet.

    One reader, because three call sites each opening the file their own way is how one of them ends
    up reading a key the writer does not emit — which is exactly the defect `ladder_for` documents.
    """
    path = root / CONFIG_PATH
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"{CONFIG_PATH} is not valid JSON ({exc})")


def save_plan(root: Path, rows: list[dict]) -> None:
    (root / PLAN_PATH).write_text(json.dumps({"assets": rows}, indent=2) + "\n", encoding="utf-8")
    # RE-RENDER HERE rather than at each call site, so a mutation path added later cannot forget.
    # Only when the table already exists: rendering one nobody asked for would create a file the
    # scaffold does not make and `--check` would then hold the project to it.
    if (root / RENDER_PATH).is_file():
        (root / RENDER_PATH).write_text(render_plan(rows, load_config(root)), encoding="utf-8")


RENDER_BANNER = ("<!-- GENERATED from docs/assets/plan.json by asset_plan.py --render.\n"
                 "     Do not hand-edit: the plan is the source, this is a view of it.\n"
                 "     Rebuild:  python3 <plugin>/scripts/asset_plan.py --render\n"
                 "     Staleness is reported by --check once this file exists. -->\n")


def _cell(value) -> str:
    """One table cell: pipes escaped, newlines flattened, empty rendered as an em dash."""
    text = str(value if value not in (None, "") else "—").replace("|", "\\|")
    return " ".join(text.split())


def render_plan(rows: list[dict], config: dict) -> str:
    """The plan as a markdown table — GENERATED, never hand-maintained.

    JSON is the right shape for the agent that runs the plan and the wrong shape for the human who
    has to review it, which is the step the plan exists for. So both, from one source.

    THE TABLE IS DERIVED, and that is the load-bearing property. A hand-maintained copy is a second
    source of truth that disagrees with the first within a week and disagrees SILENTLY, because a
    stale table still looks like a table. Two rules follow, both learned from `docs/coverage.html`:

      1. The bytes are a function of the DATA and nothing else -- no timestamp, no git SHA, no
         absolute path. Anything else makes the staleness check unpassable by construction, because
         re-rendering an unchanged plan would produce different bytes.
      2. The totals come from `status_report()`, the same tally `--status` prints, rather than from
         this function recounting the rows. A derived total computed twice can disagree with itself,
         and the version a human reads is the one nothing else checks.

    Cost is shown per row so the unpriced ones are VISIBLE rather than implied: an unpriced row is
    the one that refuses the run, and reading "—" in a cost column is how a reviewer sees why.
    """
    counts, outstanding = status_report(rows)
    total, unpriced = plan_pricing(rows, config)
    unpriced_ids = {id(r) for r in unpriced}

    # Only the statuses that HAPPENED. "0 failed · 0 skipped" is noise in a document whose whole
    # purpose is being read quickly, and a zero says nothing the absence of a row does not.
    tally = " · ".join(f"{n} {status}" for status, n in sorted(counts.items()) if n)
    head = [RENDER_BANNER, "# Asset plan\n",
            f"**{len(rows)} row(s)** — {tally or 'nothing planned yet'}.",
            f"**{outstanding} outstanding**, estimated floor **${total:.2f}** to finish.\n"]
    if unpriced:
        head.append(
            f"> **{len(unpriced)} row(s) have no price.** `--run` refuses the plan until a "
            f"`cost_usd` is written into `ladders.<kind>` — an unpriced row costs $0.00 to the "
            f"budget and whatever the provider charges in reality.\n")
    if not rows:
        head.append("_No rows yet. An empty plan is unplanned, not finished._\n")
        return "\n".join(head)

    head.append("| # | surface | kind | aspect | status | group | priority | est. | file | why |")
    head.append("|---|---|---|---|---|---|---|---|---|---|")
    for i, row in enumerate(rows, 1):
        if row.get("status") in ("done", "skipped"):
            est = "—"                       # settled rows cost nothing; a re-run never re-buys them
        elif id(row) in unpriced_ids:
            est = "**unpriced**"
        else:
            est = f"${cheapest_rung(ladder_for(config, row.get('kind', 'static'))):.2f}"
        # #640. An UNSTATED aspect renders bold, not as an em dash: a blank cell reads as "nothing
        # to say here", and the whole point is that it is the row about to buy an unknown shape.
        brief = (config.get("briefs") or {}).get(row.get("surface")) or {}
        aspect = (_cell(brief.get("aspect")) if brief.get("aspect")
                  else ("**unstated**" if row.get("kind", "static") in ("static", "vector")
                        else "—"))
        head.append("| " + " | ".join([
            str(i), _cell(row.get("surface")), _cell(row.get("kind", "static")), aspect,
            _cell(row.get("status", "planned")), _cell(row.get("group")),
            _cell(row.get("priority")), est,
            f"`{_cell(row['file'])}`" if row.get("file") else "—",
            _cell(row.get("why")),
        ]) + " |")
    head.append("\n_Estimates are a **floor**: every row is priced at its kind's cheapest rung, and "
                "a row that fails its acceptance check climbs and costs more._\n")
    return "\n".join(head)


def render_drift(root: Path, rows: list[dict], config: dict) -> list[str]:
    """Is the committed table still the plan?

    Absent, this says NOTHING -- the table is opt-in, and a check that demanded a file the scaffold
    never creates would fail every project that does not want one. Once it exists it is held current,
    because a rendered view that is allowed to rot is worse than no view: it reads as authoritative.
    """
    path = root / RENDER_PATH
    if not path.is_file():
        return []
    if path.read_text(encoding="utf-8") != render_plan(rows, config):
        return [f"{RENDER_PATH} no longer matches the plan it was rendered from. It is generated, "
                f"so the fix is to rebuild it (--render), not to edit it."]
    return []


# #642. Styles whose subject is a SCENE -- people or characters doing something somewhere. For these
# the subject has to name an action and an environment, because a model given "a person working"
# invents the tool, the room and the wardrobe, differently every run. The abstract registers are
# excluded deliberately: "an abstract woven lattice" is a CORRECT subject for `geometric` or
# `minimalist-ink`, and a check demanding an action there would flag our own worked fidara brief on
# its first run -- #476's lesson exactly.
SCENE_STYLES = ("character-world", "cartoon", "mixed-media")

# Verbs that describe a person doing something. Crude and stated rather than clever: the alternative
# is a parts-of-speech dependency, and this file is stdlib-only by design.
_ACTION = re.compile(r"\b\w+(ing|s)\b")
# "in a kitchen", "at a desk", "on a park bench" -- a preposition introducing a place.
_PLACE = re.compile(r"\b(in|at|on|inside|outside|beside|among|through|across)\s+(a|an|the|their|his|her|its)\b",
                    re.I)


def subject_problems(surface: str, brief: dict) -> list[str]:
    """What a `subject` is missing, for a style whose subject is a scene. Empty for abstract work.

    The contract is `illustrationsai.com`'s, which publishes it for exactly this job: be specific,
    include key objects and environment, describe the action clearly -- and do not write "a person
    working", do not assume context, do not leave the action unclear. Their own samples are all the
    same shape: [who] + [doing what] + [with which objects] + [where].

    Every one of those anti-patterns passed our gate and was billed: `subject: "x"` composed into a
    paid prompt, because `compose_prompt` validated presence only.

    WHAT IT CANNOT CATCH, stated because the boundary is easy to overclaim. It detects an ABSENT
    action or environment, never a VAGUE one. "a person working" satisfies the action check --
    "working" is a verb -- and is caught only because it names no environment. A subject that is
    specific-looking and empty ("a professional doing their job in an office") passes entirely.
    Vagueness is judgement, and a rule that tried to score it would fire on correct briefs; the
    contract in `visual-assets.md` is what a human reviews against.
    """
    subject = str(brief.get("subject") or "").strip()
    if not subject:
        return []                       # the missing-subject case is already reported elsewhere
    out: list[str] = []
    # A FLOOR IN EVERY REGISTER. "x" is not a subject for geometric work either, and this needs no
    # taxonomy knowledge.
    if len(subject) < 12:
        out.append(f"{surface}: subject {subject!r} is too short to be one. It is what the picture "
                   f"is OF, and it is the field with no contract until now — 'x' composed into a "
                   f"paid prompt.")
        return out
    if brief.get("style") not in SCENE_STYLES:
        return out
    if not _ACTION.search(subject):
        out.append(f"{surface}: subject {subject!r} names no action, and {brief.get('style')!r} is a "
                   f"scene style. 'Teaching? Reading? Writing?' — a model given no verb picks one.")
    if not _PLACE.search(subject):
        out.append(f"{surface}: subject {subject!r} names no environment, and {brief.get('style')!r} "
                   f"is a scene style. Without one the model invents the room, differently each run. "
                   f"Say where: 'at a modern desk', 'in a restaurant kitchen'.")
    return out


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
        # #640. AN UNSTATED SHAPE IS BOUGHT BLIND. The prompt used to carry style, subject, mood,
        # palette, ground and an avoid-list -- and never said whether it wanted a 21:9 band or a
        # square card. Reported HERE, at review time, because the alternative is finding out after
        # the charge, by looking at the page.
        #
        # NOT reported for `motion` or `video`: a Lottie recolours and scales, and footage is framed
        # by its own row. Firing on those would flag correct input, which is how a check gets
        # switched off.
        if (briefs is not None and row.get("surface") in (briefs or {})
                and row.get("kind", "static") in ("static", "vector")
                and not (briefs[row["surface"]] or {}).get("aspect")):
            problems.append(
                f"{label}: the brief states no `aspect`, so this row buys an unspecified shape. A "
                f"square delivered for a wide band is cropped at composition time, which throws "
                f"away the part of the picture you paid for. State it as e.g. \"16:9\", \"1:1\" or "
                f"\"21:9\".")
        # #642. The subject is the field that decides what the picture is OF, and it was the only
        # one in the brief with no contract at all.
        if briefs is not None and row.get("surface") in (briefs or {}):
            problems.extend(subject_problems(row["surface"], briefs[row["surface"]] or {}))
    return problems


def ladder_for(config: dict, kind: str) -> list[dict]:
    """The rungs that price ONE kind.

    Per-kind first, with the flat `ladder` as the fallback, matching `generation_gate.py` exactly --
    and reading the same key the scaffold WRITES, which is the defect this replaces. `--scaffold`
    emits `ladders` (per kind); the cost path read `ladder` (flat), which is absent from every
    scaffolded config, so it resolved to `[]` and every plan cost $0.00 no matter how many rows it
    held. The refusal below then compared 0.0 against the ceiling, could not fire, and `--run` fell
    through to the executor. A guard whose input is always zero is not a lenient guard; it is a
    guard that has been switched off, and nothing said so.

    The kinds are priced separately because they are not close: a video rung is expensive by an
    order of magnitude and a vector rung the agent authors is free. One flat ladder had to be wrong
    for at least one of them.
    """
    ladders = config.get("ladders") or {}
    return ladders.get(kind) or config.get("ladder") or []


def cheapest_rung(ladder: list[dict]) -> float | None:
    """The cheapest PRICED rung, or None when the ladder prices nothing.

    None rather than 0.0, and that is the whole point. Averaging a missing price to 0 made every
    unpriced model free, so a plan of them cost nothing and the ceiling could not refuse it -- the
    estimate agreed with the budget by construction. Returning 0.0 for a ladder with no priced rung
    at all was the same bug one level up, surviving the fix that named it: an unpriced kind is not
    a free kind, it is a kind nobody has costed, and the caller has to be able to tell those apart.
    """
    priced = [float(r["cost_usd"]) for r in ladder if r.get("cost_usd") is not None]
    return min(priced) if priced else None


def plan_pricing(rows: list[dict], config: dict) -> tuple[float, list[dict]]:
    """(floor cost of the outstanding rows, the rows whose kind prices nothing).

    Cheapest rung because that is where every row starts; a row only climbs when it fails a stated
    acceptance check, and budgeting for a climb nobody has needed yet would refuse plans that are
    affordable. The estimate is therefore a floor, and it is labelled as one wherever it is printed.

    The unpriced list is returned SEPARATELY rather than folded into the total, because those two
    answers want opposite handling: an expensive plan is refused against the ceiling and can be made
    affordable by dropping rows, while an unpriced plan cannot be reasoned about at all and no
    ceiling refuses it. Summing them would let a plan nobody has costed read as a cheap one.
    """
    total, unpriced = 0.0, []
    for row in rows:
        if row.get("status") in ("done", "skipped"):
            continue
        rung = cheapest_rung(ladder_for(config, row.get("kind", "static")))
        if rung is None:
            unpriced.append(row)
        else:
            total += rung
    return round(total, 4), unpriced


def plan_cost(rows: list[dict], config: dict) -> float:
    """The floor cost alone. Unpriced rows contribute nothing HERE and are refused by the caller."""
    return plan_pricing(rows, config)[0]


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

    ROWS ARE PRICED PER KIND, by the same two functions `plan_pricing` uses. This used to compute
    "the cheapest rung" its own second way -- `min(float(r.get("cost_usd", 0)) ...)` over a flat
    ladder -- which disagreed with `cheapest_rung` in two ways at once: it counted an unpriced rung
    as free, and it raised `TypeError` on a rung whose `cost_usd` is explicitly `null`, which is
    what the scaffold writes for video. Two functions answering one question is how a split like
    that survives; there is now one answer.
    """
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
        rungs = [cheapest_rung(ladder_for(config, r.get("kind", "static"))) for _, r in members]
        if any(r is None for r in rungs):
            # A group holding a row nobody has costed cannot be called affordable. Treating it as
            # free is how an unpriced plan reads as one that fits inside any budget.
            over.extend(r for _, r in members)
            continue
        # Summed with the Nones already filtered rather than relying on the guard above to have
        # removed them. Not defensiveness for its own sake: `sum([0.01, None])` raises, and a
        # TypeError is not a verdict -- it makes the line above impossible to test, because
        # disabling it crashes the suite instead of failing the assertion that names the bug.
        cost = sum(r for r in rungs if r is not None)
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
                # #628 CORRECTED THIS STRING'S PREDECESSOR, which said "the bytes are the asset,
                # save them to write_to". That is an instruction the agent CANNOT follow for an
                # inline-only image MCP: it receives a rendered picture, not base64 it can retype.
                # Telling it to save bytes it cannot reach turned a dead-end into a dead-end with
                # blame attached. So the reason now routes by RESPONSE SHAPE, and says which shape
                # to check for before spending rather than what to do after.
                row["reason"] = (
                    "approved — the agent authors this one. CHECK YOUR PROVIDER'S RESPONSE SHAPE "
                    "BEFORE CALLING IT, because after the call you have been billed either way. "
                    "Returns a file path → `--record <path>`. Returns a URL → `--from-url <url>` "
                    "and the script downloads it. Returns the image INLINE ONLY → do not call it: "
                    "you cannot save an image you only saw rendered, so it bills and leaves "
                    "nothing to record — configure a keyed REST rung instead and let the script "
                    "make the call. Authoring SVG yourself → write it to `write_to`, then "
                    "`--record`.")
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
    ap.add_argument("--render", action="store_true",
                    help=f"write {RENDER_PATH} — the plan as a readable table, generated")
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
        # This used to say "fill $OPENROUTER_API_KEY, then write the plan rows" -- naming a variable
        # the scaffolded path never reads, as the FIRST instruction a new project sees. The agent is
        # the default generator and needs no key; what a new project actually owes is the research.
        print("\nNext: run the reference research, then write the plan rows. The agent generates by\n"
              "default — no API key — and paid rungs ship unpriced, so `--run` refuses them until\n"
              "you look the price up and write `cost_usd` into `ladders.<kind>`. That is the safe\n"
              "state, and it is enforced before anything is bought rather than described here.")
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
    if args.render:
        rows = load_plan(root)
        path = root / RENDER_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_plan(rows, load_config(root)), encoding="utf-8")
        print(f"wrote {RENDER_PATH} ({len(rows)} row(s))")
        return 0
    if args.check:
        config = load_config(root)
        briefs = config.get("briefs", {}) if (root / CONFIG_PATH).is_file() else None
        doc = load_doc(root)
        rows = doc.get("assets", [])
        problems = (check_research(root) + check_prd(root, doc)
                    + check_plan(rows, briefs) + reconcile(root, rows)
                    + render_drift(root, rows, config))
        print("\n".join(problems) or "plan is reviewable, current with the brief, and reconciled.")
        return 1 if problems else 0
    if args.run:
        rows = load_plan(root)
        cfg_all = load_config(root)
        briefs = cfg_all.get("briefs", {}) if (root / CONFIG_PATH).is_file() else None
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
        total, unpriced = plan_pricing(rows, cfg_all)
        ceiling = float(cfg_all.get("budget_usd", 0))
        spent = float(args.spent)
        # AN UNPRICED PLAN IS REFUSED OUTRIGHT, before the executor is invoked and regardless of the
        # numeric total. This is deliberately NOT a budget comparison: a ceiling can only refuse a
        # number, and the whole problem with an unpriced row is that there is no number -- it scores
        # 0.0, fits inside every budget, and reaches the executor as the cheapest thing in the plan.
        #
        # --confirm-partial does NOT bypass it either. That flag says "buy what the budget affords",
        # which is a decision about rows whose price is known; there is no partial answer to a row
        # whose price is not. `generation_gate.py` also refuses an unpriced rung, but that runs
        # INSIDE the executor -- per row, after `--run` has committed to spending -- so leaning on
        # it would make the preflight advisory about the one thing it exists to decide.
        if unpriced:
            kinds = sorted({r.get("kind", "static") for r in unpriced})
            print(json.dumps({
                "unpriced_rows": [f"{r['surface']}/{r.get('kind', 'static')}" for r in unpriced],
                "unpriced_kinds": kinds,
                "priced_rows_total_usd": total,
            }, indent=2))
            print(f"\nrefusing to run: {len(unpriced)} row(s) have no price. The ladder for "
                  f"{', '.join(kinds)} has no rung with a `cost_usd`, so the budget has nothing to "
                  f"compare against and would approve this plan at $0.00 whatever it actually "
                  f"costs.")
            print(f"\nThe provider's model list does not report pricing, which is why the scaffold "
                  f"leaves it unset rather than inventing a number. Look up the price for each "
                  f"model above and write `cost_usd` into `ladders.<kind>` in {CONFIG_PATH}, or "
                  f"drop those rows.")
            return 2
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
        drift = check_prd(root, doc) + reconcile(root, rows) + render_drift(root, rows,
                                                                           load_config(root))
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

    # THE CONFIG EVERY COST FIXTURE USES IS THE ONE `--scaffold` ACTUALLY WRITES.
    #
    # This is the structural half of the fix, and it matters more than any single assertion below.
    # The cost fixtures used to hand-write `{"budget_usd": ..., "ladder": [...]}` -- a flat, singular
    # shape the scaffold has never emitted. So 63 assertions passed against a config no project
    # could have, while `plan_cost` returned $0.00 for every real one and the budget refusal could
    # not fire. Tests that imitate the writer's output instead of USING it cannot see a writer/reader
    # divergence; they are two transcriptions agreeing with each other.
    def scaffolded_config() -> dict:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            scaffold(root)
            return json.loads((root / CONFIG_PATH).read_text())

    # SCAFFOLDING never overwrites, and ships the paid rungs UNPRICED so nothing can be bought.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        made = scaffold(root)
        # NAMES, not a count. This was `len(made) == 2` and broke the moment #625 added the two
        # library folders -- a bare count says nothing about WHAT was created, so it fails on a
        # correct addition and would pass if the config were swapped for something else entirely.
        check("scaffold creates the config", (root / CONFIG_PATH).is_file())
        check("...and the plan", (root / PLAN_PATH).is_file())
        # #625/#628/#629. Both destinations exist BEFORE the first --run, each with a README so git
        # tracks the folder and the next person is told what belongs in it.
        check("...and the assets library folder", (root / LIBRARY_DIR / "README.md").is_file())
        check("...and the prompts library folder", (root / PROMPTS_DIR / "README.md").is_file())
        check("...and reports each one it made", len(made) == 4)
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
        # Motion HAS a route -- the video endpoint, which is asynchronous. Doctrine said otherwise
        # for one release: a true claim about the IMAGE endpoint that stood as a false one about the
        # provider, so every motion row refused.
        # Motion is UI motion -- Lottie/animated SVG, agent-authored and free. Video is footage,
        # a different endpoint and the most expensive rung here. Pointing motion at a video model
        # for one release routed a loading spinner through footage generation.
        check("motion is agent-authored and free",
              cfg["ladders"]["motion"][0] == {"name": "agent", "cost_usd": 0.0})
        check("video is a real model, shipped unpriced",
              cfg["ladders"]["video"][0]["name"] and cfg["ladders"]["video"][0]["cost_usd"] is None)
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
    # The brief must now carry an `aspect` for a raster/vector row (#640) — an unstated shape is
    # bought blind — so this fixture states one. Its subject is the CROSS-CHECK, not the aspect.
    check("...and one WITH a brief is fine",
          check_plan([ok], briefs={"hero": {"aspect": "16:9"}}) == [])
    # #640 ITSELF: a brief with no aspect is reported at review time, before the charge.
    check("a raster row whose brief states no aspect is reported",
          any("no `aspect`" in p for p in check_plan([ok], briefs={"hero": {}})))
    # ...and NOT for motion/video: a Lottie recolours and scales, footage is framed by its own row.
    # A check that fired on those would flag correct input, which is how a check gets switched off.
    check("...but a motion row is not",
          check_plan([{**ok, "kind": "motion"}], briefs={"hero": {}}) == [])

    # #642. THE SUBJECT CONTRACT. Conditional on the style, because "an abstract woven lattice" is a
    # CORRECT subject for the abstract registers, and a check demanding an action there would flag
    # our own worked fidara brief on its first run.
    SCENE = {"style": "character-world"}
    check("a scene subject naming no environment is reported",
          any("no environment" in m
              for m in subject_problems("hero", {**SCENE, "subject": "a person working"})))
    check("...and one naming both action and place is clean",
          subject_problems("hero", {**SCENE, "subject":
              "a young female designer sketching on a tablet at a modern desk"}) == [])
    check("an abstract subject in an abstract style is SILENT",
          subject_problems("hero", {"style": "minimalist-ink",
                                    "subject": "an abstract woven lattice"}) == [])
    # A FLOOR IN EVERY REGISTER: "x" is not a subject for geometric work either.
    check("a trivially short subject is reported whatever the style",
          any("too short" in m
              for m in subject_problems("hero", {"style": "geometric", "subject": "x"})))
    check("...and an absent subject is left to the field-presence check",
          subject_problems("hero", {"style": "character-world"}) == [])
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

    # THE RESEARCH DECIDES THE STYLE. Without this join the record is a box that was ticked.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "docs/design").mkdir(parents=True)
        (root / ".design-flow").mkdir()
        (root / RESEARCH_PATH).write_text(
            json.dumps({"job": "x", "style": "minimalist-ink", "references": []}), encoding="utf-8")
        def _cfg(style):
            (root / CONFIG_PATH).write_text(
                json.dumps({"briefs": {"hero": {"style": style}}}), encoding="utf-8")
        _cfg("3d-render")
        check("a brief that ignores the researched style is reported",
              any("chose 'minimalist-ink'" in m for m in check_research(root)))
        _cfg("minimalist-ink")
        check("...and one that honours it is silent", check_research(root) == [])
        # THE REFUSAL MUST TEACH THE WAY OUT. With no exception declared, a reader's only visible
        # move was "change the brief" -- which is what forced a deliberately-paid signature asset
        # out of the plan entirely (#632). The mechanism has to be discoverable from the refusal.
        _cfg("3d-render")
        check("...and the refusal names the mechanism when none is declared",
              any("signature_exceptions" in m for m in check_research(root)))

    # #632. A DECLARED SIGNATURE EXCEPTION: a primary family plus one rationed off-style device.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "docs/design").mkdir(parents=True)
        (root / ".design-flow").mkdir()

        def _research(exceptions):
            (root / RESEARCH_PATH).write_text(json.dumps(
                {"job": "x", "style": "minimalist-ink", "references": [],
                 "signature_exceptions": exceptions}), encoding="utf-8")

        def _briefs(styles):
            (root / CONFIG_PATH).write_text(json.dumps(
                {"briefs": {s: {"style": st} for s, st in styles.items()}}), encoding="utf-8")

        PRISM = {"style": "3d-render", "why": "one rationed luminous prism at hero/CTA punctuation"}
        _research([PRISM])
        _briefs({"accent": "minimalist-ink", "hero": "3d-render"})
        check("a declared exception lets the primary and the exception coexist",
              check_research(root) == [])
        # UNDECLARED DRIFT STAYS BLOCKED. If declaring one exception waved through every other
        # style, the mechanism would be a hole in the rule rather than a carve-out of it.
        _briefs({"accent": "minimalist-ink", "hero": "3d-render", "empty": "cartoon"})
        problems = check_research(root)
        check("...while an UNdeclared style is still refused",
              any("'empty'" in m for m in problems))
        check("...and the refusal lists what IS declared",
              any("3d-render" in m and "Declared signature exception" in m for m in problems))

        # THE RATION. A device used everywhere stops punctuating and becomes the family, which is
        # the mixed set the one-style rule prevents -- so `max` defaults to 1, stated in the message.
        _briefs({"hero": "3d-render", "cta": "3d-render"})
        problems = check_research(root)
        check("an unrationed second use of the exception is refused",
              any("RATIONED" in m and "capped at 1" in m for m in problems))
        check("...naming the surfaces that claim it",
              any("cta, hero" in m for m in problems))
        _research([{**PRISM, "max": 2}])
        check("...and raising `max` deliberately permits it", check_research(root) == [])

        # AN UNJUSTIFIED EXCEPTION IS NOT ONE. `why` is what separates a decision from drift, so an
        # entry without it is not honoured -- the strict default, never the loose one.
        _research([{"style": "3d-render"}])
        _briefs({"hero": "3d-render"})
        check("an exception with no `why` is not honoured",
              any("chose 'minimalist-ink'" in m for m in check_research(root)))

        # DEFAULT STAYS STRICT: a record with no exceptions behaves exactly as before.
        _research([])
        check("no declared exceptions means the old rule, unchanged",
              any("chose 'minimalist-ink'" in m for m in check_research(root)))

        # AND THE ORPHAN TRAP CLOSES. The compounding half of #632: briefing the exception tripped
        # the style refusal, and NOT briefing it tripped reconcile's "in the manifest with no plan
        # row" -- so the one asset that actually cost money had nowhere to live. Asserted together,
        # because either check passing alone still leaves the asset untrackable.
        _research([PRISM])
        _briefs({"hero": "3d-render"})
        (root / "docs/assets").mkdir(parents=True)
        (root / "docs/assets/manifest.json").write_text(json.dumps({"assets": [
            {"name": "Luminous prism", "surface": "hero", "kind": "static"}]}), encoding="utf-8")
        rows = [{"surface": "hero", "kind": "static", "why": "the signature device"}]
        check("the exception asset passes the style check", check_research(root) == [])
        check("...AND is no longer an orphan in the manifest", reconcile(root, rows) == [])

    # COST. The estimate prices every row at the CHEAPEST rung, so it is a floor, and settled rows
    # cost nothing -- a re-run that re-priced finished work would refuse plans that are affordable.
    CFG = {"budget_usd": 0.05,
           "ladders": {"static": [{"cost_usd": 0.01}, {"cost_usd": 0.40}],
                       "motion": [{"cost_usd": 0.01}],
                       "video": [{"cost_usd": 0.60}]}}
    three = [{"surface": "a", "kind": "static"}, {"surface": "b", "kind": "static"},
             {"surface": "c", "kind": "static"}]
    check("cost prices outstanding rows at the cheapest rung", plan_cost(three, CFG) == 0.03)
    check("done and skipped rows cost nothing",
          plan_cost([{**three[0], "status": "done"}, {**three[1], "status": "skipped"}], CFG) == 0.0)
    # THE KINDS ARE NOT CLOSE. A flat ladder priced a video row at the static rung, which is wrong by
    # an order of magnitude in the direction that spends money.
    check("each kind is priced at ITS OWN ladder",
          plan_cost([three[0], {"surface": "d", "kind": "video"}], CFG) == 0.61)
    # The flat `ladder` key still resolves, because a project may have written one by hand.
    check("a flat `ladder` is still honoured as the fallback",
          plan_cost(three, {"ladder": [{"cost_usd": 0.01}]}) == 0.03)

    # THE REGRESSION. Against the config `--scaffold` REALLY writes, not an imitation of it.
    SC = scaffolded_config()
    check("the scaffolded config has no flat `ladder` key at all", "ladder" not in SC)
    check("...so a reader of `ladder` would price the whole plan at zero",
          plan_cost(three, {k: v for k, v in SC.items() if k != "ladders"}) == 0.0)
    check("...while the fixed reader prices it from `ladders`",
          plan_cost(three, SC) == 0.0 and cheapest_rung(ladder_for(SC, "static")) == 0.0)
    # An UNPRICED kind is not a free kind. The scaffold ships video unpriced on purpose, so this is
    # the state of every fresh project that plans a video row.
    _total, _unpriced = plan_pricing([three[0], {"surface": "promo", "kind": "video"}], SC)
    check(f"an unpriced row is reported, not costed at 0 (unpriced={len(_unpriced)})",
          len(_unpriced) == 1 and _unpriced[0]["surface"] == "promo" and _total == 0.0)
    check("a ladder that prices nothing returns None rather than 0.0",
          cheapest_rung([{"name": "m", "cost_usd": None}]) is None and cheapest_rung([]) is None)
    check("an absent ladder leaves the row unpriced rather than free",
          plan_pricing(three, {})[1] == three)

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
    # AN UNPRICED ROW IS NOT AN AFFORDABLE ONE. Costing it at 0 made it fit inside every budget --
    # the cheapest thing in the plan was the one nobody had priced.
    unpriced_row = [{"surface": "promo", "kind": "video"}]
    fitsU, overU = affordable(unpriced_row, {**SC, "budget_usd": 100.0}, spent=0.0)
    check("an unpriced row never fits, however large the budget", fitsU == [] and len(overU) == 1)
    # ...and pricing it must not raise, either. `float(r.get("cost_usd", 0))` over a rung whose
    # `cost_usd` is explicitly null is a TypeError, and the scaffold writes exactly that for video.
    check("a null-priced rung does not crash the split",
          affordable(unpriced_row, SC, spent=0.0)[1] == unpriced_row)

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

    # --run END TO END, against a project built by `--scaffold` and driven through `main`.
    #
    # Every fixture above tests a function; this one tests the PATH, and the difference is the whole
    # bug. `plan_cost` was wrong, `--run`'s refusal therefore never fired, and control fell through
    # to the executor -- and no unit test could see it, because each function was asked a question
    # it answered correctly in isolation. So: a real scaffold, a real plan file, `main(["--run"])`,
    # and a subprocess.run that FAILS the test if it is ever called.
    made_dirs: list[str] = []

    def project(rows: list[dict], **cfg_overrides) -> Path:
        # mkdtemp rather than the context manager, because these outlive one `with` block; they are
        # removed at the end of the run so a suite that passes does not leave a trail in /tmp.
        root = Path(tempfile.mkdtemp())
        made_dirs.append(str(root))
        (root / "PRD.md").write_text("brief", encoding="utf-8")
        scaffold(root, "PRD.md")
        (root / "docs/design").mkdir(parents=True, exist_ok=True)
        (root / RESEARCH_PATH).write_text(
            json.dumps({"job": "j", "style": "minimalist-ink", "references": []}), encoding="utf-8")
        config = json.loads((root / CONFIG_PATH).read_text())
        # `aspect` because #640 reports a raster brief without one at --check time, and these
        # fixtures are about COST, not about shape.
        config["briefs"] = {r["surface"]: {"style": "minimalist-ink", "aspect": "16:9"}
                            for r in rows}
        config.update(cfg_overrides)
        (root / CONFIG_PATH).write_text(json.dumps(config), encoding="utf-8")
        doc = json.loads((root / PLAN_PATH).read_text())
        doc["assets"] = rows
        (root / PLAN_PATH).write_text(json.dumps(doc), encoding="utf-8")
        return root

    def run_in(root: Path, argv: list[str]) -> tuple[int, bool]:
        """(exit code, was the executor invoked). cwd is restored whatever happens."""
        import os
        reached = []
        here = os.getcwd()
        real = _sp.run
        _sp.run = lambda *a, **k: reached.append(a) or _sp.CompletedProcess([], 0, "{}", "")
        try:
            os.chdir(root)
            return main(argv), bool(reached)
        finally:
            _sp.run = real
            os.chdir(here)

    VIDEO = {"surface": "promo", "kind": "video", "why": "launch film"}
    STATIC = {"surface": "hero", "kind": "static", "why": "no product UI yet"}

    root = project([VIDEO])
    before = (root / PLAN_PATH).read_text()
    code, reached = run_in(root, ["--run"])
    check(f"--run refuses an unpriced plan (exit {code})", code == 2)
    check("...without invoking the executor", not reached)
    check("...and without mutating the plan", (root / PLAN_PATH).read_text() == before)

    # --confirm-partial must NOT be a way round it. "Buy what the budget affords" is a decision
    # about rows whose price is known, and there is no partial answer for a row with no price.
    root = project([VIDEO])
    code, reached = run_in(root, ["--run", "--confirm-partial"])
    check(f"--confirm-partial does not bypass the unpriced refusal (exit {code})", code == 2)
    check("...and still reaches no executor", not reached)

    # THE PRICED PATH STILL RUNS. A refusal that fired on everything would be worse than the bug:
    # the agent path is free and is what a fresh project uses for all three non-video kinds.
    root = project([STATIC])
    code, reached = run_in(root, ["--run"])
    check(f"a fully priced plan is not refused (exit {code})", reached)
    # ...and the ceiling still refuses a plan it cannot finish, now that the total is real.
    root = project([STATIC, {"surface": "empty", "kind": "static", "why": "x"}],
                   budget_usd=0.01, ladders={"static": [{"name": "m", "cost_usd": 0.02}]})
    code, reached = run_in(root, ["--run"])
    check(f"an over-budget plan is refused (exit {code})", code == 2)
    check("...before the executor is invoked", not reached)

    # THE RENDERED TABLE. JSON for the agent, a table for the human who has to review it -- one
    # source, so they cannot disagree.
    root = project([STATIC, VIDEO])
    code, _ = run_in(root, ["--render"])
    table = (root / RENDER_PATH).read_text()
    check(f"--render writes the table (exit {code})", code == 0 and table.startswith("<!-- GENERATED"))
    body = [l for l in table.splitlines() if l.startswith("| ") and l[2:3].isdigit()]
    check(f"...with a row per asset (rows={len(body)})", len(body) == 2)
    check("...naming each surface and why", "hero" in table and "launch film" in table)
    # An unpriced row is VISIBLE as unpriced. Rendering it as $0.00 would put the bug in the
    # document a human reads to decide whether to spend.
    check("...and marking the unpriced row rather than pricing it at zero", "**unpriced**" in table)
    check("the render is a function of the DATA only, so it is reproducible",
          render_plan(load_plan(root), load_config(root)) == table)
    # Staleness is reported once the file exists, and says nothing before that.
    check("a fresh render is not stale", render_drift(root, load_plan(root), load_config(root)) == [])
    (root / RENDER_PATH).write_text("hand-edited\n", encoding="utf-8")
    check("...an edited one is reported as stale",
          any("no longer matches" in m
              for m in render_drift(root, load_plan(root), load_config(root))))
    with tempfile.TemporaryDirectory() as td:
        check("...and an absent one says nothing at all",
              render_drift(Path(td), [STATIC], SC) == [])
    # save_plan REFRESHES it, so a mutation path added later cannot leave it stale.
    main_rows = load_plan(root)
    main_rows[0]["status"] = "done"
    save_plan(root, main_rows)
    check("saving the plan re-renders the table",
          render_drift(root, load_plan(root), load_config(root)) == [])
    check("an empty plan renders as unplanned rather than finished",
          "unplanned, not finished" in render_plan([], SC))

    import shutil
    for d in made_dirs:
        shutil.rmtree(d, ignore_errors=True)

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} asset-plan assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
