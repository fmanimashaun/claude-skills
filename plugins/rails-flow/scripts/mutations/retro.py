"""Mutation guard: retro. Declared here, run by scripts/mutation_check.py (#1339)."""
from mutation_types import Guard, Mutation  # noqa: F401

# A retro fails in quiet directions: a recurrence that is really one review's many records, a severity spelling guessed instead of listed, a category
# that cannot recur because its spelling was split, a report that is clean because it read nothing, lines dropped without a word, a pattern that
# is called mechanical on thin evidence, and a "write nothing" mode that writes.
GUARD = Guard(
    name="retro",
    subject="scripts/retro.py",
    selftest="scripts/retro.py",
    mutations=(
        Mutation(
            "a known severity spelling maps to the wrong level",
            '"p1": "high", "blocker": "high", "blocking": "high",',
            '"p1": "high", "blocker": "low", "blocking": "high",',
            "high maps P1, blocker, BLOCKING",
        ),
        Mutation(
            "an unknown severity spelling is guessed instead of listed as unmapped",
            "return SEVERITY_MAP.get(raw.strip().lower()) if isinstance(raw, str) else None",
            'return SEVERITY_MAP.get(raw.strip().lower(), "low") if isinstance(raw, str) else None',
            "a state and an unknown spelling and a missing one are unmapped and listed",
        ),
        Mutation(
            "recurrence counts records, not sources",
            "recurs = category != NO_CATEGORY and len(sources) >= min_prs",
            "recurs = category != NO_CATEGORY and len(members) >= min_prs",
            "two files in one PR are one source",
        ),
        Mutation(
            "a record with no category can recur into a proposal",
            "recurs = category != NO_CATEGORY and len(sources) >= min_prs",
            "recurs = len(sources) >= min_prs",
            "no-category records never recur into a proposal",
        ),
        Mutation(
            "a file pattern is called mechanical however few records share it",
            "top_n / len(members) >= DOMINANT",
            "top_n / len(members) >= 0",
            "a low-dominance pattern is not mechanical",
        ),
        Mutation(
            "a signature in one source counts as repeated",
            "if sig_cat.get(sig) == category and len(srcs) >= 2)",
            "if sig_cat.get(sig) == category and len(srcs) >= 1)",
            "a repeated signature is a mechanical candidate",
        ),
        Mutation(
            "a severity word in the category splits it (no merge)",
            'key = " ".join(EDGE.sub("", raw).lower().split())',
            'key = " ".join(raw.lower().split())',
            "severity-word spellings merge into one recurring category",
        ),
        Mutation(
            "a line that is not JSON is dropped without a word",
            'skipped.append((number, "not JSON"))',
            "pass",
            "an unreadable line is named",
        ),
        Mutation(
            "files with no usable record produce a clean report",
            "    if not items:",
            "    if False:",
            "files with no usable record is unusable",
        ),
        Mutation(
            "--stdout also writes the file",
            "    if stdout:\n        emit(text, end=\"\")\n    else:",
            "    if False:\n        emit(text, end=\"\")\n    else:",
            "--stdout writes nothing",
        ),
        Mutation(
            "the date filter admits everything",
            "if (since and when < since) or (until and when > until):",
            "if False:",
            "a dated directory is filtered by its name",
        ),
        Mutation(
            "an undated file excluded by a date filter is not counted",
            "                excluded += 1",
            "                pass",
            "an undated file is excluded and counted",
        ),
        Mutation(
            "single-source categories are tabled as rows",
            'shown = [g for g in groups if len(g["sources"]) >= 2 or g["category"] == NO_CATEGORY]',
            "shown = groups",
            "a single-source category is summarised",
        ),
        Mutation(
            "the 'Nothing recurs' sentence is said over input that recurs",
            "    if not recurring and not recurring_sigs:",
            "    if True:",
            "a recurring category is reported",
        ),
    ),
)
