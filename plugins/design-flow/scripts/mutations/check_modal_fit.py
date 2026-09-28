"""Mutation guard: check_modal_fit. Run by scripts/mutation_check.py (#1419)."""
from mutation_types import Guard, Mutation  # noqa: F401

# A fit check goes quiet in three ways: it stops asking for the inset, it stops reading the sibling
# `.rb` where a ViewComponent keeps its classes (and so reports the doctrine's own modal), or it
# mistakes the backdrop's `fixed inset-0` for a pinned panel.
GUARD = Guard(
    name="check_modal_fit",
    subject="scripts/check_modal_fit.py",
    selftest="scripts/check_modal_fit.py",
    deps=("scripts/content_floors.py", "scripts/source_text.py"),
    mutations=(
        Mutation(
            "a dialog with no inset wrapper and no max-h-full stops being a finding",
            "    if missing:\n",
            "    if False:\n",
            "a dialog capped with 100vh and no inset wrapper is caught",
        ),
        Mutation(
            "the sibling .rb is no longer read, so a component's Ruby-held classes vanish",
            '    both = source + "\\n" + sibling\n',
            "    both = source\n",
            "the doctrine's own modal is silent",
        ),
        Mutation(
            "an edge-pinned panel stops being a finding",
            "    for p in PINNED.finditer(both):\n",
            "    for p in []:\n",
            "a panel pinned to an edge is caught",
        ),
        Mutation(
            "the backdrop's inset-0 is read as a pinned panel",
            'inset-[xy]-0(?![\\w-])")',
            'inset-(?:[xy]-)?0(?![\\w-])")',
            "the backdrop's fixed inset-0 is not a pinned panel",
        ),
        Mutation(
            "a native <dialog> is no longer recognised",
            '''DIALOG = re.compile(r"""\\brole\\s*[=:]\\s*["']dialog["']|<dialog\\b""")''',
            '''DIALOG = re.compile(r"""\\brole\\s*[=:]\\s*["']dialog["']""")''',
            "a native <dialog> is recognised",
        ),
    ),
)
