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
        # ANOTHER ROUTE TO FITTING (#1419 review): the shapes a real app ships at its current dev.
        Mutation(
            "a calc(100%-gap) width no longer counts as horizontally bounded",
            "    fits_x = inset or bool(WIDTH_GUTTER.search(both))",
            "    fits_x = inset",
            "a calc(100%-gap) width with an app utility that is calc(100svh - gap) fits",
        ),
        Mutation(
            "an app's own viewport-height utility is no longer read",
            "    return {name for name, body in UTILITY.findall(css) if VH_CALC_DECL.search(body)}",
            "    return set()",
            "an @utility is read as a viewport height only when its max-height is calc(100vh - gap)",
        ),
        Mutation(
            "max-h-full counts even with no inset wrapper",
            "    fits_y = (inset and bool(MAX_H.search(both)))",
            "    fits_y = bool(MAX_H.search(both))",
            "max-h-full with NO inset wrapper is not bounded by the viewport",
        ),
        Mutation(
            "a calc(100dvh-gap) max-h class no longer counts",
            " or bool(VH_CALC_CLASS.search(both)) or ",
            " or ",
            "a max-h-[calc(100dvh-3rem)] class fits vertically",
        ),
        Mutation(
            "a declared edge-pinned placement is reported anyway",
            "    if EDGE_PINNED.search(raw):\n        return findings\n",
            "",
            "a declared edge-pinned placement is not a finding",
        ),
        Mutation(
            "an edge-pinned declaration no longer needs a reason on its line",
            'EDGE_PINNED = re.compile(r"modal-fit:[ \\t]*edge-pinned[ \\t]*--[ \\t]*\\w")',
            'EDGE_PINNED = re.compile(r"modal-fit:\\s*edge-pinned\\s*--\\s*\\w")',
            "a declaration with no reason is not a declaration",
        ),
        Mutation(
            "a native <dialog> is no longer recognised",
            '''DIALOG = re.compile(r"""\\brole\\s*[=:]\\s*["']dialog["']|<dialog\\b""")''',
            '''DIALOG = re.compile(r"""\\brole\\s*[=:]\\s*["']dialog["']""")''',
            "a native <dialog> is recognised",
        ),
    ),
)
