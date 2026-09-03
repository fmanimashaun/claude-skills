"""Mutation guard: asset_plan. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="asset_plan",
    subject="plugins/design-flow/scripts/asset_plan.py",
    selftest="plugins/design-flow/scripts/asset_plan.py",   # --selftest lives in the module
    # No `needs`: the fixtures are literals and tempdirs, and the one run_plan fixture points at
    # a NONEXISTENT executor on purpose, so no mutation can reach a provider from here.
    mutations=(
        Mutation(
            # #642. `subject: "x"` composed into a paid prompt. The floor needs no taxonomy
            # knowledge and applies in every register.
            "a trivially short subject is accepted, so 'x' buys a picture",
            "    if len(subject) < 12:",
            "    if False:",
            "a trivially short subject is reported whatever the style",
        ),
        Mutation(
            # A scene with no stated place has the room invented, differently every run -- which
            # is the reroll a composed prompt exists to prevent.
            "a scene subject needs no environment, so the model invents the room",
            "    if not _PLACE.search(subject):",
            "    if False:",
            "a scene subject naming no environment is reported",
        ),
        Mutation(
            # Widening the contract to abstract registers would flag "an abstract woven lattice"
            # -- our own worked brief -- which is how a check gets switched off (#476).
            "the subject contract widens to abstract styles and flags correct briefs",
            '    if brief.get("style") not in SCENE_STYLES:\n        return out',
            "    if False:\n        return out",
            "an abstract subject in an abstract style is SILENT",
        ),
        Mutation(
            # #640. Reported at REVIEW time or discovered after the charge, by looking at the
            # page. There is no third option.
            "an unstated aspect stops being reported, so the row buys a shape nobody chose",
            '                and not (briefs[row["surface"]] or {}).get("aspect")):',
            "                and False):",
            "a raster row whose brief states no aspect is reported",
        ),
        Mutation(
            # #632. Without this the declared, justified exception is refused exactly as before
            # -- and the one deliberately-paid asset in the project goes back to having nowhere
            # to live: brief it and the style check refuses, do not and reconcile calls it an
            # orphan.
            "a declared signature exception is refused like any off-style brief",
            "            allowed = {chosen} | set(exceptions)",
            "            allowed = {chosen}",
            "a declared exception lets the primary and the exception coexist",
        ),
        Mutation(
            # An exception with no ceiling is not an exception, it is a second family with
            # paperwork -- which is the mixed set the one-style rule exists to prevent.
            "the ration stops being enforced, so an exception becomes a second family",
            "                if len(claimants) > cap:",
            "                if False:",
            "an unrationed second use of the exception is refused",
        ),
        Mutation(
            # `why` is the only thing separating a sanctioned second style from drift. Honour an
            # unjustified entry and the mechanism becomes a way to write any style into the
            # research and have it waved through.
            "an exception with no `why` is honoured, so drift needs only a style key",
            '        if not style or not str(why or "").strip():',
            "        if not style:",
            "an exception with no `why` is not honoured",
        ),
        Mutation(
            # The default ration is the decision that keeps this from being a hole in the rule.
            # Loosened, an exception declared without a ceiling silently gets an unlimited one.
            "the default ration goes unlimited, so an undeclared ceiling means no ceiling",
            "DEFAULT_RATION = 1",
            "DEFAULT_RATION = 999",
            "an unrationed second use of the exception is refused",
        ),
        Mutation(
            # The join that makes research MEAN something downstream. Without it a project can
            # research monochrome ink line-work and brief a 3D render, and nothing notices --
            # the record becomes a box that was ticked rather than a decision anything honours.
            "briefs stop being held to the researched style, so one set mixes families",
            # #632 rewrote this line from `!= chosen` to `not in allowed` when the declared
            # exception was added. The anchor follows the code; the assertion it guards is
            # unchanged — an UNdeclared style must still be refused.
            '            off = [s for s, b in briefs.items() if b.get("style") and b["style"] not in allowed]',
            "            off = []",
            "a brief that ignores the researched style is reported",
        ),
        Mutation(
            # Exit 0 is not "done": the agent path exits 0 with a BRIEF. Reading the code alone
            # marked rows done with no file on disk -- the exact "recorded from what was
            # attempted" failure this file's own docstring forbids.
            "exit 0 alone marks a row done, so a plan completes with no assets on disk",
            "            if produced and (root / produced).is_file():",
            "            if True:",
            "an agent brief is awaiting-agent, not done",
        ),
        Mutation(
            # Research settles the STYLE, and the style settles which assets exist at all. A
            # plan written without it looks identical to one written with it -- every row
            # complete, and nothing recording that the look came from the median.
            "research stops being required, so the plan is costed against a look nobody chose",
            "    path = root / RESEARCH_PATH",
            "    path = Path(__file__)",
            "a missing research record is reported",
        ),
        Mutation(
            # A hero still and the motion loop that animates it are one artefact in two files.
            # Row-greedy buys the loop alone, which is worse than buying neither: you pay for
            # something that cannot be used.
            "groups stop being atomic, so half a set is bought and cannot be used",
            "        if cost <= remaining:",
            "        if True:",
            "a group that does not fit whole is skipped entirely",
        ),
        Mutation(
            # A library planned against last month's brief is quietly incomplete: every row
            # done, status clean, and the new surfaces have no rows at all.
            "PRD drift stops being detected, so a stale plan reads as a finished one",
            '    if fingerprint(path) != prd.get("sha256"):',
            "    if False:",
            "an edited PRD is reported",
        ),
        Mutation(
            # Without reconciliation the plan and the library drift apart, and the gap between
            # them stops meaning "remaining work".
            "unplanned assets stop being reported, so ad-hoc work never reaches the plan",
            '            for e in owned if (e.get("surface"), e.get("kind", "static")) not in planned]',
            '            for e in owned if False]',
            "an unplanned asset is reported",
        ),
        Mutation(
            # Idempotency is what stops a re-run re-buying the library. Without it, every
            # `--run` pays again for everything already on disk.
            "a done row is re-run, so every pass re-buys the whole library",
            '        if row.get("status") == "done":',
            "        if False:",
            "a done row is skipped entirely",
        ),
        Mutation(
            # The scaffold CREATES an empty plan, so this is the state of every fresh setup.
            # Blessing it says the planning is finished before it has started.
            "an empty plan passes review, so an unplanned project reads as finished",
            # Anchored with its comment: `render_plan` grew a second `if not rows:` at the same
            # indent, and a bare anchor then matched twice. An ambiguous anchor is a mutation
            # that silently moves to a different line, so the harness refuses it outright.
            "    if not rows:\n        # An empty plan is UNPLANNED, not finished.",
            "    if False:\n        # An empty plan is UNPLANNED, not finished.",
            "an empty plan is reported as unplanned",
        ),
        Mutation(
            "two rows for one slot pass, so a surface forks into two looks",
            "        if key in seen:",
            "        if False:",
            "two rows for one surface+kind is reported",
        ),
        Mutation(
            # Moves the finding from review time back to run time, which is after the spend.
            "the brief cross-check goes, so unrunnable rows only fail once money is involved",
            '        if briefs is not None and row.get("surface") and row["surface"] not in briefs:',
            "        if False:",
            "a row with no brief for its surface is reported",
        ),
        Mutation(
            # #592, AND THE REASON IT SURVIVED 63 ASSERTIONS. `--scaffold` writes `ladders`
            # (per kind); the cost path read `ladder` (flat), which no scaffolded config has.
            # So it resolved to [], every plan cost $0.00 however many rows it held, the budget
            # refusal compared 0.0 against the ceiling and could not fire, and `--run` fell
            # through to the executor. Reverting the reader reproduces it exactly.
            "the cost path reads a key --scaffold never writes, so every plan costs $0.00",
            '    return ladders.get(kind) or config.get("ladder") or []',
            '    return config.get("ladder") or []',
            "...while the fixed reader prices it from `ladders`",
        ),
        Mutation(
            # An unpriced kind is not a free kind. Returning 0.0 for a ladder that prices
            # nothing is the same bug one level up: the row scores $0.00, fits inside every
            # budget, and reaches the executor as the cheapest thing in the plan.
            "an unpriced ladder reads as free, so the row nobody costed is the cheapest one",
            "    return min(priced) if priced else None",
            "    return min(priced) if priced else 0.0",
            "a ladder that prices nothing returns None rather than 0.0",
        ),
        Mutation(
            # The refusal is deliberately NOT a budget comparison -- a ceiling can only refuse a
            # number. Dropping it puts the unpriced plan back on the path to the executor.
            "the unpriced refusal goes, so a plan nobody has costed runs anyway",
            "        if unpriced:",
            "        if False:",
            "--run refuses an unpriced plan",
        ),
        Mutation(
            # "Buy what the budget affords" is a decision about rows whose price is KNOWN.
            # Letting an unpriced group through prices it at nothing and buys it first.
            "unpriced groups are treated as affordable, so they fit inside any budget",
            "        if any(r is None for r in rungs):",
            "        if False:",
            "an unpriced row never fits, however large the budget",
        ),
        Mutation(
            # A generated view that is allowed to rot is worse than no view: it still reads as
            # authoritative, and it is the copy a human reviews before deciding to spend.
            "the rendered table stops being drift-checked, so a stale one reads as current",
            "    if path.read_text(encoding=\"utf-8\") != render_plan(rows, config):",
            "    if False:",
            "...an edited one is reported as stale",
        ),
    ),
)
