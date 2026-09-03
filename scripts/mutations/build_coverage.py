"""Mutation guard: build_coverage. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="build_coverage",
    subject="scripts/build_coverage.py",
    selftest="scripts/build_coverage_selftest.py",
    # The selftest's evidence guards read every doc under `references/` -- `verify_shipped_
    # evidence` and `verify_interaction_claims` both resolve it from the SUBJECT's location, so
    # a staged mutant with no `references/` made the unmutated selftest exit 1 and every
    # mutation vacuously "caught". A directory, so a new reference doc is picked up rather than
    # quietly missing. `run_baseline` is what now proves this is sufficient.
    needs=("skills/design-system/references",),
    mutations=(
        Mutation(
            "the totality guard stops naming unclassified corpus entries",
            "def verify_totality(",
            "def _disabled_verify_totality(",
            "",   # any failure counts: removing the entry point breaks many fixtures
        ),
        Mutation(
            "two rows may again be vouched for by one piece of doc (#95)",
            "    problems += verify_evidence_is_not_shared()\n",
            "",
            "two documented rows sharing one evidence string",
        ),
        # The substring half needs its own mutation: equality alone still catches the loud
        # case, so `"## Button"` silently satisfied by the Button-GROUP heading would go
        # unguarded on a rule that only compared for equality.
        Mutation(
            "the shared-evidence guard drops to equality and misses the prefix case",
            "            DOCUMENTED_EVIDENCE[a] in DOCUMENTED_EVIDENCE[b]\n"
            "            or DOCUMENTED_EVIDENCE[b] in DOCUMENTED_EVIDENCE[a]\n",
            "            DOCUMENTED_EVIDENCE[a] == DOCUMENTED_EVIDENCE[b]\n",
            "one row's evidence contained inside another's",
        ),
        Mutation(
            "a promoted row keeps its stale BUILD fallback unnoticed (#95)",
            "    stale = sorted(\n"
            "        {e.name for e in ENTRIES if e.is_documented and e.build.strip()}\n"
            "        | (set(BUILD) & {e.name for e in ENTRIES if e.is_documented})\n"
            "    )",
            "    stale = []",
            # The FIXTURE's label, not the guard's message. With `stale = []` the guard never
            # emits its message at all, so `expect_error` reports "expected BuildError, mapping
            # was accepted" under this label -- and the old `expects` ("still carrying a BUILD
            # fallback", one word off the label's "its") matched nothing. It only ever passed
            # because the whole selftest was failing for want of the reference docs; the
            # baseline control above is what made it visible.
            "a documented row still carrying its BUILD fallback",
        ),
        Mutation(
            "the stale-fallback guard keys on the NAME instead of the status",
            "{e.name for e in ENTRIES if e.is_documented})",
            "{e.name for e in ENTRIES})",
            "a needs-doctrine row carrying a BUILD fallback is correct",
        ),
        # The guard reads TWO sources -- `resolve_build` prefers a row's own `build=` kwarg
        # over the BUILD dict -- so each half needs its own mutation. Covering only the dict
        # half is how the inline half went unguarded in the first place (#95).
        Mutation(
            "the stale-fallback guard stops reading a row's inline `build=` kwarg",
            "{e.name for e in ENTRIES if e.is_documented and e.build.strip()}\n",
            "set()\n",
            "a documented row carrying its fallback inline rather than in BUILD",
        ),
        # The Needs-doctrine section reached ZERO rows (#95/#91), so the empty branch is now
        # the live one -- a regression to the always-table form would read as normal output.
        Mutation(
            "the empty Needs-doctrine section prints guidance for rows that do not exist",
            "    if needs:\n",
            "    if True:\n",
            "yet the Tracked table header was still emitted",
        ),
        # `verify_interaction_claims` shipped in #399 with selftest fixtures and no mutations,
        # which is the gap this block closes: a fixture proves a guard fires TODAY, a mutation
        # proves the fixture would notice if the guard stopped firing. Both DIRECTIONS get one,
        # because the guard's whole point is that a one-way rule would have caught none of the
        # four stale rows it was written for -- and a mutation on only the `shipped` half would
        # reproduce that blind spot in the meta-check.
        Mutation(
            "the interaction guard stops flagging a `planned` row whose contract HAS landed",
            "        elif status.strip() != \"shipped\" and present:",
            "        elif False:",
            "the contract landed and the status was never flipped",
        ),
        Mutation(
            "the interaction guard stops flagging a `shipped` row with no doc behind it",
            "        if status.strip() == \"shipped\" and not present:",
            "        if False:",
            "does not appear in any reference doc",
        ),
        Mutation(
            "one document is allowed to vouch for two different interaction patterns",
            "        if probe in seen:",
            "        if False:",
            "share the probe",
        ),
        # `verify_no_undeclared_entry` (#89) is the negative direction the component half
        # never had. Both of its halves get a mutation for the same reason the interaction
        # guard's do -- and the second is the more important one here, because the way this
        # guard fails is not by going quiet but by becoming a false-positive machine that
        # someone then deletes.
        # Each `expects` is the FIXTURE's own label, never the guard's message -- with the
        # guard neutered it emits no message at all, so matching on it would match nothing
        # and every mutation would read as caught-by-something-else (#422).
        Mutation(
            "a `derivable` row is allowed to have a catalogue entry again",
            "        if entry.is_documented:\n            continue",
            "        if True:\n            continue",
            "a `derivable` row whose catalogue entry exists must be caught",
        ),
        Mutation(
            "the catalogue match widens to a substring, convicting correct rows",
            "            if title.casefold() == entry.name.casefold() or re.match(\n"
            "                re.escape(entry.name) + r\"\\s*[—–\\-(]\", title, re.I\n"
            "            ):",
            "            if entry.name.casefold() in title.casefold():",
            "must not convict a row named",
        ),
        # forms.md is the second catalogue file, and dropping it is silent: nothing else in
        # the run reads it, so without this the tuple could shrink to one file and the guard
        # would keep passing while blind to the whole forms family.
        Mutation(
            "the guard stops reading forms.md, blinding it to the forms family",
            'CATALOGUE_FILES = ("components.md", "components-commerce.md", "forms.md")',
            'CATALOGUE_FILES = ("components.md", "components-commerce.md")',
            "forms.md is a catalogue file too",
        ),
        # `verify_cell_text` likewise. The interaction half is mutated rather than the ENTRIES
        # half because that is the loop the near-miss was found in: the note that nearly shipped
        # a broken table was an interaction note.
        Mutation(
            "the pipe guard stops reading interaction notes, so a `|` splits the row again",
            "    for name, status, note, _probe in INTERACTION_PATTERNS:\n"
            "        scan(f\"interaction pattern {name!r}\", name, status, note)",
            "    for name, status, note, _probe in ():\n"
            "        scan(f\"interaction pattern {name!r}\", name, status, note)",
            "a `|` inside an interaction note was not flagged",
        ),
    ),
)
