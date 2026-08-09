#!/usr/bin/env python3
"""The prompt library: what was asked for, which model answered, and what it cost.

`generation_gate.py` says, of the prompt it composes:

    "A composed prompt is also the only thing that makes the asset reproducible: without it, a
     brand change means paying again."

And then nothing kept it. The asset manifest records file, name, purpose, use_cases, avoid,
visual_elements, style, kind, surface -- every field except the three a reuse decision needs. The
provenance row carries prompt, model and cost, is printed to stdout, and is gone with the scrolled
buffer. So the one artefact the doctrine calls load-bearing did not survive its own run: that is
claims-vs-enforcement, in the path with a bill attached.

This module is the missing store. Two files, one source:

    docs/assets/prompts.json   the source -- agents read this
    docs/assets/prompts.md     a VIEW of it -- humans read this, and it is generated

The markdown is derived, never hand-kept, for the reason `docs/coverage.html` records: a
hand-maintained second copy disagrees with the first within a week and disagrees SILENTLY, because
a stale table still looks like a table. Two rules follow and both are load-bearing:

  1. The rendered bytes are a function of the DATA and nothing else. No timestamp, no git SHA, no
     absolute path. Anything else makes `--check` unpassable by construction.
  2. Totals are computed once, in `tally()`, and both the JSON summary and the markdown read that.
     A derived total computed twice can disagree with itself, and the copy a human reads is the one
     nothing else checks.

WHAT AN ENTRY IS KEYED ON. `id` is a hash of (surface, prompt), so the SAME prompt for the same
surface is the same entry however many times it runs. That is deliberate: the question the library
exists to answer is "have I bought this before, and was it any good?", and a store that appended a
fresh row per run could not answer it -- the duplicates would look like distinct prompts. Re-running
increments `spend_count` and adds to `spent_total_usd` instead, which is how paying twice for one
prompt becomes VISIBLE rather than merely possible.

WHY `model` MAY BE NULL, AND MUST BE. On the agent-authored path the rung is named `agent`, which is
a ROLE, not a model -- the real model belongs to whatever MCP the agent called, and nothing reports
it back. Recording `"agent"` in a column headed `model` would make the library answer "which model
made this?" with a fiction, and reuse decisions get made from that column. So the model is recorded
as null with a note saying why, unless the agent passes `--model` and states it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

LIBRARY_PATH = Path("docs/assets/prompts.json")
RENDER_PATH = Path("docs/assets/prompts.md")

# A rung name that is a ROLE rather than a model. `agent` authors in-process and `pen` shells out to
# a local CLI; in both cases the model that actually rendered the pixels is unreported. Kept as a
# set rather than tested inline so adding a third keyless route cannot forget this half.
ROLE_NOT_MODEL = frozenset({"agent", "pen"})

VERDICTS = ("pending", "accept", "reject")

# Present-and-non-empty is required for these. `model` is deliberately NOT here: null is a legitimate
# and honest value for it, and a completeness check that forbade null would push the agent path into
# writing "agent" to satisfy the checker -- manufacturing the exact fiction this module refuses.
REQUIRED = ("id", "prompt", "surface", "kind", "verdict")


class Unusable(Exception):
    """The store cannot be read or written without destroying something."""


def entry_id(surface: str, prompt: str) -> str:
    """Stable identity for (surface, prompt). Deterministic — no clock, no counter.

    The surface is part of the key because one prompt reused for two surfaces is two decisions with
    two verdicts, and collapsing them would let an accept on one silently vouch for the other.
    """
    digest = hashlib.sha256(f"{surface}\n{prompt}".encode("utf-8")).hexdigest()
    return digest[:12]


def build_entry(prov: dict, prompt: str, brief: dict, *, asset: str | None,
                model: str | None, verdict: str = "pending", why: str = "",
                actual_cost_usd: float | None = None) -> dict:
    """One library row, from the pieces every call site already holds.

    Built HERE rather than at each call site so the bought path and the agent path cannot drift into
    recording different fields for the same event -- which is how `manifest_entry` earned a NameError
    that only fired on the path with no test.
    """
    surface = prov["surface"]
    rung = str(prov.get("model", "") or "")
    is_role = rung.lower() in ROLE_NOT_MODEL
    # A RUNG THAT IS NOT A ROLE *IS* THE MODEL. `openai/gpt-image-1` names a model; `agent` names
    # who did the work. Resolved here rather than at each call site so the bought path and the
    # agent path cannot disagree about which rungs are models -- the distinction is the whole
    # reason this column can be trusted.
    if model is None and rung and not is_role:
        model = rung
    note = None
    if model is None and is_role:
        note = (f"unknown — the {rung!r} rung is a role, not a model. The model that rendered this "
                f"belongs to whatever the agent called and is not reported back. Pass `--model` at "
                f"record time to state it.")
    return {
        "id": entry_id(surface, prompt),
        "surface": surface,
        "kind": prov.get("kind", "static"),
        "style": brief.get("style", ""),
        "prompt": prompt,
        "model": model,
        "model_note": note,
        "rung": rung or None,
        "estimated_cost_usd": prov.get("cost_usd"),
        "spent_total_usd": float(actual_cost_usd or 0.0),
        "spend_count": 1 if actual_cost_usd is not None else 0,
        "asset": asset,
        "use_cases": brief.get("use_cases") or [surface],
        "avoid": brief.get("avoid") or [],
        "verdict": verdict,
        "why": why,
    }


def load(root: Path) -> dict:
    path = root / LIBRARY_PATH
    if not path.is_file():
        return {"prompts": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise Unusable(f"{LIBRARY_PATH} is not valid JSON ({exc}); refusing to overwrite it.")
    data.setdefault("prompts", [])
    return data


def upsert(root: Path, entry: dict) -> Path:
    """Merge one entry by `id`. A re-run ACCUMULATES spend rather than appending a duplicate row.

    The merge is field-by-field and deliberately asymmetric:

      - `spend_count` and `spent_total_usd` ACCUMULATE, because the question "did I pay for this
        twice?" is exactly the one three bugs in this flow have made expensive to answer.
      - `verdict` and `why` OVERWRITE, because the latest judgement is the operative one.
      - `model` overwrites only when the incoming one is known. A later run that could not name its
        model must not erase an earlier run that could.
      - `asset` overwrites only when non-null, for the same reason.
    """
    missing = [f for f in REQUIRED if entry.get(f) in (None, "", [], {})]
    if missing:
        raise Unusable(f"refusing to write a prompt-library row missing {', '.join(missing)} — a row "
                       f"nobody can act on is why prompts get re-bought.")
    if entry["verdict"] not in VERDICTS:
        raise Unusable(f"verdict must be one of {', '.join(VERDICTS)}; got {entry['verdict']!r}")
    data = load(root)
    rows = data["prompts"]
    for i, existing in enumerate(rows):
        if existing.get("id") != entry["id"]:
            continue
        merged = {**existing, **{k: v for k, v in entry.items()
                                 if k not in ("spend_count", "spent_total_usd", "model",
                                              "model_note", "asset")}}
        merged["spend_count"] = int(existing.get("spend_count", 0)) + int(entry.get("spend_count", 0))
        merged["spent_total_usd"] = round(
            float(existing.get("spent_total_usd", 0.0)) + float(entry.get("spent_total_usd", 0.0)), 6)
        if entry.get("model") is not None:
            merged["model"], merged["model_note"] = entry["model"], entry.get("model_note")
        if entry.get("asset") is not None:
            merged["asset"] = entry["asset"]
        rows[i] = merged
        break
    else:
        rows.append(entry)
    path = root / LIBRARY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"prompts": rows}, indent=2) + "\n", encoding="utf-8")
    # RE-RENDER AT THE CHOKE POINT, never at each call site, so a path added later cannot forget.
    # Only when the view already exists: rendering one nobody asked for would create a file the
    # scaffold does not make and `--check` would then hold the project to it.
    if (root / RENDER_PATH).is_file():
        (root / RENDER_PATH).write_text(render(rows), encoding="utf-8")
    return path


def tally(rows: list[dict]) -> dict:
    """Every derived number, computed ONCE. Both views read this rather than recounting."""
    return {
        "prompts": len(rows),
        "spent_total_usd": round(sum(float(r.get("spent_total_usd") or 0.0) for r in rows), 4),
        "accepted": sum(1 for r in rows if r.get("verdict") == "accept"),
        "rejected": sum(1 for r in rows if r.get("verdict") == "reject"),
        "pending": sum(1 for r in rows if r.get("verdict") == "pending"),
        "unknown_model": sum(1 for r in rows if r.get("model") is None),
        "re_spent": sum(1 for r in rows if int(r.get("spend_count") or 0) > 1),
    }


BANNER = ("<!-- GENERATED from docs/assets/prompts.json by prompt_library.py --render.\n"
          "     Do not hand-edit: the JSON is the source, this is a view of it.\n"
          "     Rebuild:  python3 <plugin>/scripts/prompt_library.py --render\n"
          "     Staleness is reported by --check once this file exists. -->\n")

VERDICT_MARK = {"accept": "accepted", "reject": "**rejected**", "pending": "_pending_"}


def _cell(value) -> str:
    """One table cell: pipes escaped, newlines flattened, empty rendered as an em dash."""
    text = str(value if value not in (None, "", []) else "—").replace("|", "\\|")
    return " ".join(text.split())


def _fence(body: str) -> str:
    """A fence long enough to survive backticks INSIDE the prompt.

    Prompts quote token names and file paths, so a three-backtick fence around one is a coin flip.
    The fence is therefore computed from the content: a document that renders wrong is a document
    whose prompt cannot be copied, which is the one thing it is for.
    """
    longest = 0
    run = 0
    for ch in body:
        run = run + 1 if ch == "`" else 0
        longest = max(longest, run)
    return "`" * max(3, longest + 1)


def render(rows: list[dict]) -> str:
    """The library as markdown — GENERATED, never hand-maintained.

    Two sections, because they answer different questions. The TABLE answers "what do I already
    have?" at a glance. The BODIES answer "can I reuse this one?", which needs the prompt verbatim
    and does not fit in a cell.
    """
    t = tally(rows)
    out = [BANNER, "# Prompt library\n",
           "Every prompt that reached a provider — what it asked for, which model answered, what it "
           "cost, and whether the result was kept. **This file is generated**; edit "
           "`docs/assets/prompts.json` or re-run the flow.\n",
           f"**{t['prompts']} prompt(s)** — {t['accepted']} accepted · {t['rejected']} rejected · "
           f"{t['pending']} pending. **${t['spent_total_usd']:.2f} spent in total.**\n"]

    if t["re_spent"]:
        out.append(f"> **{t['re_spent']} prompt(s) were paid for more than once.** An identical "
                   f"prompt re-run is a reroll, and a composed prompt exists to avoid rerolls — "
                   f"check the `runs` column before spending again.\n")
    if t["unknown_model"]:
        out.append(f"> **{t['unknown_model']} prompt(s) have no known model.** They were authored "
                   f"through a role (`agent`, `pen`) that does not report which model rendered the "
                   f"result. Recorded as unknown rather than guessed — pass `--model` at record "
                   f"time to state it.\n")
    if not rows:
        out.append("_No prompts recorded yet. Nothing has been generated, or the flow predates this "
                   "library._\n")
        return "\n".join(out)

    out.append("| id | surface | kind | model | est. | spent | runs | verdict |")
    out.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        est = r.get("estimated_cost_usd")
        out.append("| " + " | ".join([
            f"[`{_cell(r['id'])}`](#{_cell(r['id'])})", _cell(r.get("surface")),
            _cell(r.get("kind")),
            f"`{_cell(r['model'])}`" if r.get("model") else "**unknown**",
            f"${float(est):.2f}" if est is not None else "—",
            f"${float(r.get('spent_total_usd') or 0.0):.2f}",
            str(r.get("spend_count") or 0),
            VERDICT_MARK.get(r.get("verdict"), _cell(r.get("verdict"))),
        ]) + " |")

    out.append("\n## The prompts\n")
    for r in rows:
        out.append(f"### {r['id']}\n")
        out.append(f"**{_cell(r.get('surface'))}** · {_cell(r.get('kind'))} · "
                   f"{VERDICT_MARK.get(r.get('verdict'), '')}")
        if r.get("style"):
            out.append(f"\nStyle: {_cell(r['style'])}")
        if r.get("use_cases"):
            out.append(f"\n**Use for:** {', '.join(_cell(u) for u in r['use_cases'])}")
        if r.get("avoid"):
            out.append(f"\n**Avoid:** {', '.join(_cell(a) for a in r['avoid'])}")
        if r.get("asset"):
            out.append(f"\n**Produced:** `{_cell(r['asset'])}`")
        if r.get("model_note"):
            out.append(f"\n**Model:** {_cell(r['model_note'])}")
        if r.get("why"):
            out.append(f"\n**Verdict:** {_cell(r['why'])}")
        fence = _fence(r["prompt"])
        out.append(f"\n{fence}text\n{r['prompt']}\n{fence}\n")
    return "\n".join(out)


def check(root: Path) -> list[str]:
    """Is the committed view still the library?

    Absent, this says NOTHING -- the view is opt-in, and a check demanding a file the scaffold never
    creates would fail every project that does not want one. Once it exists it is held current,
    because a rendered view allowed to rot is worse than none: it reads as authoritative.
    """
    path = root / RENDER_PATH
    if not path.is_file():
        return []
    rows = load(root)["prompts"]
    if path.read_text(encoding="utf-8") != render(rows):
        return [f"{RENDER_PATH} no longer matches the library it was rendered from. It is generated, "
                f"so the fix is to rebuild it (--render), not to edit it."]
    return []


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--render", action="store_true", help="write the markdown view of the library")
    ap.add_argument("--check", action="store_true", help="report drift between the JSON and the view")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    root = Path.cwd()
    try:
        if args.check:
            problems = check(root)
            for p in problems:
                print(p, file=sys.stderr)
            return 1 if problems else 0
        if args.render:
            rows = load(root)["prompts"]
            path = root / RENDER_PATH
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(render(rows), encoding="utf-8")
            print(f"wrote {RENDER_PATH} ({len(rows)} prompt(s))")
            return 0
    except Unusable as why:
        print(f"cannot: {why}", file=sys.stderr)
        return 2
    print("nothing to do: pass --render, --check or --selftest", file=sys.stderr)
    return 2


def selftest() -> int:
    import tempfile

    failures: list[str] = []

    def ok(label: str, cond: bool) -> None:
        print(f"  {'ok  ' if cond else 'FAIL'}  {label}")
        if not cond:
            failures.append(label)

    prov = {"surface": "hero", "kind": "static", "model": "agent", "cost_usd": 0.02}
    brief = {"style": "line-art", "use_cases": ["the hero"], "avoid": ["stock photos"]}

    print("identity")
    a = entry_id("hero", "draw a thing")
    ok("the same (surface, prompt) hashes the same", a == entry_id("hero", "draw a thing"))
    ok("a different surface is a different entry", a != entry_id("about", "draw a thing"))
    ok("a different prompt is a different entry", a != entry_id("hero", "draw another thing"))

    print("the model is never invented")
    e = build_entry(prov, "draw a thing", brief, asset=None, model=None)
    ok("an agent-authored row records model=None", e["model"] is None)
    ok("...and says why", "role, not a model" in (e["model_note"] or ""))
    ok("the rung is kept separately", e["rung"] == "agent")
    stated = build_entry(prov, "draw a thing", brief, asset=None, model="gemini-2.5-flash-image")
    ok("a stated model is recorded", stated["model"] == "gemini-2.5-flash-image")
    ok("...with no note", stated["model_note"] is None)
    real = build_entry({**prov, "model": "openai/gpt-image-1"}, "p", brief, asset=None, model=None)
    ok("a rung that is not a role IS the model", real["model"] == "openai/gpt-image-1")
    ok("...so it gets NO excuse note", real["model_note"] is None)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        print("the store refuses what nobody can act on")
        try:
            upsert(root, {**e, "prompt": ""})
            ok("an empty prompt is refused", False)
        except Unusable as why:
            ok("an empty prompt is refused", "re-bought" in str(why))
        try:
            upsert(root, {**e, "verdict": "maybe"})
            ok("an unknown verdict is refused", False)
        except Unusable as why:
            ok("an unknown verdict is refused", "verdict must be one of" in str(why))

        print("spend accumulates instead of duplicating")
        upsert(root, build_entry(prov, "draw a thing", brief, asset=None, model=None,
                                 actual_cost_usd=0.02))
        upsert(root, build_entry(prov, "draw a thing", brief, asset=None, model=None,
                                 actual_cost_usd=0.02))
        rows = load(root)["prompts"]
        ok("one prompt run twice is ONE row", len(rows) == 1)
        ok("...with spend_count 2", rows[0]["spend_count"] == 2)
        ok("...and the spend summed", abs(rows[0]["spent_total_usd"] - 0.04) < 1e-9)
        ok("the re-spend is counted", tally(rows)["re_spent"] == 1)

        print("a later run cannot erase what an earlier one knew")
        upsert(root, build_entry(prov, "draw a thing", brief, asset="docs/assets/hero.png",
                                 model="gemini-2.5-flash-image", actual_cost_usd=0.02))
        upsert(root, build_entry(prov, "draw a thing", brief, asset=None, model=None,
                                 actual_cost_usd=0.02))
        rows = load(root)["prompts"]
        ok("a null model does not overwrite a known one",
           rows[0]["model"] == "gemini-2.5-flash-image")
        ok("a null asset does not overwrite a known one",
           rows[0]["asset"] == "docs/assets/hero.png")
        ok("the note cleared with the model", rows[0]["model_note"] is None)

        print("the verdict is the latest judgement")
        upsert(root, build_entry(prov, "draw a thing", brief, asset=None, model=None,
                                 verdict="reject", why="two hues, brief said one"))
        rows = load(root)["prompts"]
        ok("reject overwrites pending", rows[0]["verdict"] == "reject")
        ok("...carrying its reason", "two hues" in rows[0]["why"])
        ok("the rejection is counted", tally(rows)["rejected"] == 1)
        ok("a rejected prompt is still in the library", len(rows) == 1)

        print("the view is derived, and its bytes are a function of the data")
        first = render(load(root)["prompts"])
        ok("re-rendering unchanged data is byte-identical", first == render(load(root)["prompts"]))
        ok("the banner says it is generated", first.startswith("<!-- GENERATED"))
        ok("a rejected prompt is VISIBLE in the view", "**rejected**" in first)
        ok("an unknown model is never rendered as a rung name", "`agent`" not in first)
        # Four priced upserts at $0.02 above; the verdict upsert carries no cost and adds nothing.
        # Stated as a literal rather than recomputed from the rows: a total that recomputes itself
        # from the same data it is checking cannot disagree with it, which is not a test.
        ok("the total is the tally's", "$0.08 spent in total" in first)
        ok("...and the tally agrees", tally(load(root)["prompts"])["spent_total_usd"] == 0.08)

        print("drift is reported once the view exists")
        ok("no view means no complaint", check(root) == [])
        (root / RENDER_PATH).parent.mkdir(parents=True, exist_ok=True)
        (root / RENDER_PATH).write_text(first, encoding="utf-8")
        ok("a fresh view is clean", check(root) == [])
        (root / RENDER_PATH).write_text(first + "hand-edited\n", encoding="utf-8")
        ok("a hand-edited view is drift", len(check(root)) == 1)
        ok("...and the message says to rebuild, not to edit", "--render" in check(root)[0])

        print("the choke point re-renders")
        (root / RENDER_PATH).write_text(render(load(root)["prompts"]), encoding="utf-8")
        upsert(root, build_entry({**prov, "surface": "about"}, "draw another", brief,
                                 asset=None, model=None))
        ok("an upsert refreshed the committed view", check(root) == [])

    print("a prompt full of backticks still fences")
    tricky = "use ``code`` and ```blocks``` in the prompt"
    body = render([build_entry(prov, tricky, brief, asset=None, model=None)])
    ok("the fence outgrows the content", f"\n{'`' * 4}text\n" in body)
    ok("the prompt survives verbatim", tricky in body)

    print(f"\n{len(failures)} failed" if failures else "\nall passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
