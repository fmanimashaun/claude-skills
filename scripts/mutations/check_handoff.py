"""Mutation guard: check_handoff. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_handoff",
    subject="plugins/rails-flow/scripts/check_handoff.py",
    selftest="plugins/rails-flow/scripts/check_handoff_selftest.py",
    # The criteria parser: the traceability rule imports it to resolve the cited AC ids.
    deps=("plugins/rails-flow/scripts/check_criteria.py",),
    # Read, not imported. The selftest's last checks run the REAL tier table against the REAL
    # agents and FAIL rather than skip when absent -- so the mutant needs them, or every
    # mutation reports as "caught by the wrong fixture" and the real signal is buried.
    #
    # The agents are named as a DIRECTORY, for the reason build_coverage's `references` is: the
    # eleven files were hand-typed, `claim-verifier.md` was added later and never appended, and
    # the staged mutant therefore reconciled a full tier table against ten agents -- reporting
    # the row for the missing one as stale. `run_baseline` (#422) surfaced it as INERT the day
    # it landed. A hand-typed list of a directory's contents goes quiet the first time the
    # directory grows, which is the coverage-gap class inside the harness built to catch it.
    needs=(
        "plugins/rails-flow/reference/model-tiers.md",
        "plugins/rails-flow/commands/handoff.md",
        # The DIRECTORY, not ten hand-listed agent files. The list omitted
        # `claim-verifier.md` when v1.52.0 added it, so the staged mutant lacked an agent the
        # tier table names -- and `check_handoff` correctly reported a stale row on its own
        # UNMUTATED baseline. Every mutation then read as "caught" by that, proving nothing.
        "plugins/rails-flow/agents",
    ),
    mutations=(
        # #708. The comment said the NOTE must not fail the order; nothing inspected the prefix,
        # so the Stop gate refused every feature branch whose HEAD had moved past its base.
        Mutation(
            "a NOTE counts as a failing finding again, refusing every moved branch",
            "    real = [f for f in findings if not f.startswith(NOTE_PREFIX)]",
            "    real = list(findings)",
            "a NOTE-only result must exit 0",
        ),
        Mutation(
            # The other direction: the fix must not disarm the check it lives in.
            "a real finding stops failing once a note is present",
            "    if real:",
            "    if False:",
            "a real finding alongside a NOTE must still exit non-zero",
        ),
        Mutation(
            # #659. A plausible hex string tells an executor where to start and is worse than an
            # absent one, because it will be trusted. Present-but-unusable is not passable, the
            # rule this file already applies to a stop condition with no number.
            "an unresolvable base commit is accepted, so the executor starts from nowhere",
            "    if resolved is None:",
            "    if False:",
            "a plausible SHA this repository does not have",
        ),
        Mutation(
            # A section naming no SHA at all leaves the one question it exists to answer open.
            "a base-commit section with no SHA passes",
            "    if not shas:",
            "    if False:",
            "a base commit that names no SHA at all",
        ),
        Mutation(
            "`retry` back in the attempt-cap vocabulary (the real bug a fixture found)",
            '("attempt cap", ("attempt", "retries", "retry limit", "retry cap", "tries")),',
            '("attempt cap", ("attempt", "retry", "retries", "tries")),',
            "no numeric attempt cap",
        ),
        Mutation(
            "the stale-row rule stops noticing a table row no agent defines",
            "        if row.agent not in agents:",
            "        if False:",
            "a stale row naming an agent",
        ),
        Mutation(
            "a tier's model requirement stops being enforced",
            "        elif row.model != want:",
            "        elif False:",
            "a judgement agent pinned to a model",
        ),
        Mutation(
            "heading aliases match inside words again (the false-positive direction)",
            'return any(re.search(rf"\\b{re.escape(a)}\\b", low) for a in aliases)',
            "return any(a in low for a in aliases)",
            "is not the in-scope list",
        ),
        Mutation(
            "fenced blocks stop being skipped, so a quoted view snippet is a placeholder",
            "            if offset < len(section.fenced) and section.fenced[offset]:",
            "            if False:",
            "a fenced snippet holding a tag is code",
        ),
        Mutation(
            "inline code stops being stripped, so a backticked tag is a placeholder",
            "            line = _strip_code(raw)",
            "            line = raw",
            "a backticked HTML tag is code",
        ),
        Mutation(
            "the unresolved-token rule goes case-insensitive and eats todo.rb",
            'UNRESOLVED_RE = re.compile(r"\\b(TBD|TODO|FIXME|\\?\\?\\?)\\b")',
            'UNRESOLVED_RE = re.compile(r"\\b(TBD|TODO|FIXME|\\?\\?\\?)\\b", re.I)',
            "the word todo in prose",
        ),
    ),
)
