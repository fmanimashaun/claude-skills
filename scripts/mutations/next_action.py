"""Mutation guard: next_action. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="next_action",
    subject="plugins/rails-flow/scripts/next_action.py",
    selftest="plugins/rails-flow/scripts/next_action.py",   # --selftest lives in the module
    # No `needs`: every fixture is a dict literal or a tempdir. The mutations target the four
    # decisions that carry real consequence — overruling the breaker, ignoring the budget,
    # letting an unclassified action through, and accepting a policy that escalates nothing.
    mutations=(
        Mutation(
            # ESCALATE-AND-CONTINUE, also found by a real run: the driver stopped to ask about a
            # scope-flagged enhancement while a QA pass needing no permission sat beside it.
            # Over-asking is the failure the matrix exists to avoid, wearing the clothes of caution.
            "the driver stops preferring autonomous work, so one escalation blocks the run",
            '        if c["rights"] == "decide":',
            "        if False:",
            "a scope-flagged issue does not block available autonomous work",
        ),
        Mutation(
            # THE SCOPE DOOR, found by a real run: an issue whose own body called it "a distinct
            # auth-hardening feature" routed to DECIDE, because every open issue becomes
            # `fix-issue` and that needs only `pick-next-backlog-item`.
            "an item's nature stops upgrading the right, so scope enters via the issue door",
            "    if labels and SCOPE_LABELS & {str(l).lower() for l in labels}:",
            "    if False:",
            "an issue labelled enhancement escalates",
        ),
        Mutation(
            # The worst one available: a driver that keeps working after the safety system said
            # stop. Two disagreeing stop systems mean the permissive one wins.
            "the breaker stop is ignored, so the driver works past its own safety system",
            '    if state.get("run_stopped"):',
            "    if False:",
            "a stopped run stops, even with issues waiting",
        ),
        Mutation(
            "the budget stop is ignored, so a spent run keeps spending",
            '    if state.get("budget_exhausted"):',
            "    if False:",
            "budget beats a full backlog",
        ),
        Mutation(
            # An unclassified action defaulting to `decide` is how a policy grows permissive by
            # omission -- every action nobody thought about becomes autonomous.
            "an unclassified action becomes decidable, so the policy grows permissive by omission",
            '    return "unknown"',
            '    return "decide"',
            "an action absent from BOTH lists must not be treated as decidable",
        ),
        Mutation(
            # A policy with no escalate list is full autonomy wearing a config file.
            "a policy that escalates nothing is accepted",
            '    if not isinstance(loaded, dict) or not loaded.get("escalate"):',
            "    if False:",
            "a policy with no `escalate` list should be refused",
        ),
    ),
)
