"""Mutation guard: prompt_library. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #625. The library that keeps the composed prompt, the model and the money. Every mutation
    # below leaves it PRODUCING A FILE THAT LOOKS RIGHT -- rows present, table rendered, totals
    # printed -- while quietly answering the one question it exists for with a fiction. That is
    # this flow's signature failure, so the fixtures have to be provably able to see it.
    name="prompt_library",
    subject="plugins/design-flow/scripts/prompt_library.py",
    selftest="plugins/design-flow/scripts/prompt_library.py",  # --selftest lives in the module
    needs=(),  # stdlib only, and every fixture builds its own tempdir project
    mutations=(
        Mutation(
            # The whole reason the model column can be trusted. `agent` names WHO did the work;
            # writing it where a model belongs answers "which model made the good one?" with a
            # role name, and nothing downstream can tell the difference.
            "a role is recorded as though it were a model, so the column starts lying",
            "    if model is None and rung and not is_role:",
            "    if model is None and rung:",
            "an agent-authored row records model=None",
        ),
        Mutation(
            # Appending per run makes one prompt look like N prompts, which is precisely the
            # shape that hides paying twice -- the failure the library was built to expose.
            "a re-run appends a duplicate row instead of accumulating onto the first",
            '        if existing.get("id") != entry["id"]:',
            "        if True:",
            "one prompt run twice is ONE row",
        ),
        Mutation(
            # An earlier run that knew its model must not be overwritten by a later one that
            # did not. Losing it is silent: the row stays, the column just empties.
            "a later unknown model erases an earlier known one",
            '        if entry.get("model") is not None:',
            "        if True:",
            "a null model does not overwrite a known one",
        ),
        Mutation(
            # Money summed wrongly still renders a total, and a wrong total is read as a right
            # one. Nothing else in the flow tallies actual spend.
            "spend stops accumulating, so paying twice reads as paying once",
            '        merged["spend_count"] = int(existing.get("spend_count", 0)) + int(entry.get("spend_count", 0))',
            '        merged["spend_count"] = int(entry.get("spend_count", 0))',
            "...with spend_count 2",
        ),
        Mutation(
            # #638. A composition has no model BY DEFINITION, so counting it as "unknown model"
            # produced the advice "pass --model to state it" -- which cannot be followed. A
            # warning nobody can act on trains people to ignore warnings.
            "a composition is counted as a missing model, advising a flag nobody can pass",
            '                             if r.get("model") is None and r.get("kind") != "surface"),',
            '                             if r.get("model") is None),',
            "...without advising a --model nobody could pass",
        ),
        Mutation(
            # A hand-editable view is a second source of truth that disagrees within a week and
            # disagrees SILENTLY, because a stale table still looks like a table.
            "drift in the generated view stops being reported",
            '    if path.read_text(encoding="utf-8") != render(rows):',
            "    if False:",
            "a hand-edited view is drift",
        ),
        Mutation(
            # A prompt quoting a token name or a code fence would break out of a 3-backtick
            # fence, and a prompt that cannot be copied is the one thing this document is for.
            "the fence stops outgrowing the prompt, so a quoted prompt breaks the page",
            '    return "`" * max(3, longest + 1)',
            '    return "`" * 3',
            "the fence outgrows the content",
        ),
    ),
)
