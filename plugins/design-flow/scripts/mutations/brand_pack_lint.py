"""Mutation guard: brand_pack_lint. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# The shipped half. Roughly half of these break a fixture whose job is to stay SILENT, because
# this tool's whole risk is false positives: a checker that rewrites a client's brand colour
# which was already fine gets switched off, and then nothing measures the one that was not.
GUARD = Guard(
    # #764. The CSS parser FIVE call sites share, and it had no suite of its own -- only
    # incidental exercise as another guard's dependency, which is how a grouped selector list
    # stayed invisible to it while `brand_pack_lint`, `palette_candidates` and `design_prompt`
    # all read its empty string as "this pack declares nothing".
    name="brand_pack_lint",
    subject="scripts/brand_pack_lint.py",
    selftest="scripts/brand_pack_lint.py",
    deps=("scripts/palette_gates.py",),   # #1235: imported when a pack overrides chart_hues
    # The shipped pack is a dependency, not incidental data: the last fixture parses the real
    # theme.css, so the hand-written fixtures cannot drift from the shape actually shipped.
    needs=("brands/fidara/theme.css", "brands/reliance"),   # #1271: the entry-point fixture lints a copy of reliance
    mutations=(
        Mutation(
            # THE REPORTED BUG. `:root, .light { ... }` is ordinary CSS and is what this design
            # system's own dark-mode guidance leads to; requiring the selector to abut its brace
            # made a real pack's 24 role tokens read as zero.
            "a selector must abut its brace again, so a grouped `:root, .light` is invisible",
            'for m in re.finditer(r"^[ \\t]*([^{}@]*?)\\{(.*?)^[ \\t]*\\}", src, re.S | re.M):',
            'for m in re.finditer(r"^[ \\t]*(" + re.escape(selector) + r")\\s*\\{(.*?)^[ \\t]*\\}", src, re.S | re.M):',
            "a grouped selector list is read",
        ),
        Mutation(
            # A compound NARROWS: `:root.theme-a` applies only with the class, so its
            # declarations are not the pack's unconditional roles. Substring matching would
            # pass every positive case and still be wrong.
            "membership becomes a substring test, so `:root.theme-a` counts as `:root`",
            '        if selector in [part.strip() for part in m.group(1).split(",")]:',
            '        if any(selector in part for part in m.group(1).split(",")):',
            "a compound is NOT a member",
        ),
        Mutation(
            # The `@` keeps a `:root` nested in an at-rule reachable: without it the regex
            # matches the at-rule's own prelude and swallows the inner block as its body. The
            # pre-#764 parser found that block, so dropping this would be a regression the fix
            # introduced. A mutation survived until the nested fixture existed.
            "the at-rule guard goes, so a `:root` inside `@media` is swallowed",
            "([^{}@]*?)",
            "([^{}]*?)",
            "a :root nested in an at-rule is still read",
        ),
        Mutation(
            # #771. A pack shipping a second published lockup carried a permanent
            # "not referenced" warning it could never clear, and a warning nobody can clear is
            # one everybody learns to ignore. Narrowing that check must not DISABLE it.
            "orphan detection is switched off, so a stale asset stops being reported",
            "    referenced = set(wanted) | ({wordmark} if isinstance(wordmark, str) else set())",
            "    referenced = set(present)",
            "an unnamed asset is STILL reported as an orphan",
        ),
        Mutation(
            "a declared wordmark stops counting as referenced, so the warning returns",
            "    referenced = set(wanted) | ({wordmark} if isinstance(wordmark, str) else set())",
            "    referenced = set(wanted)",
            "a declared wordmark is not an orphan",
        ),
        Mutation(
            # A wordmark naming a file nobody shipped renders nothing -- the same failure the
            # mark check exists to prevent, which is why this is an error and not a warning.
            "a wordmark naming a missing file stops being an error",
            "        exists = isinstance(wordmark, str) and os.path.exists(os.path.join(assets, wordmark))",
            "        exists = True",
            "a wordmark naming a missing file is an ERROR",
        ),
        Mutation(
            # Each guard holds on its OWN. Written as `named and ...`, forcing `named` True
            # defeated the short-circuit and crashed os.path.join -- a crash is not a verdict.
            "a non-string wordmark is accepted",
            '        named = isinstance(wordmark, str) and wordmark.endswith(".svg")',
            "        named = True",
            "a non-string wordmark is an ERROR",
        ),
        Mutation(
            # CSS cascade order. Returning the first match silently prefers a superseded block.
            "the FIRST matching block wins, reversing the CSS cascade",
            "    blocks = selector_blocks(src, selector)\n    return blocks[-1] if blocks else \"\"",
            "    blocks = selector_blocks(src, selector)\n    return blocks[0] if blocks else \"\"",
            "a later bare block wins",
        ),
        Mutation(
            # #1235: the gates are computed but never consulted -- the flag is a claim again.
            "the chart palette is no longer validated",
            "            elif len(hues) >= 3:\n",
            "            elif False:\n",
            "fidara's old hues FAIL on colour-blind separation, dE 4.8",
        ),
        # #1271: the full chart set per pack.
        Mutation(
            "the chart check is never called, so a pack may declare one slot or none",
            "    lint_chart(os.path.join(pack_dir, \"theme.css\"), report, manifest)\n",
            "",
            "lint_pack on a pack missing --chart-5 in :root FAILS",
        ),
        Mutation(
            "a missing slot stops being an error",
            "        missing = [slot for slot in CHART_SLOTS if slot not in decls]\n",
            "        missing = []\n",
            "a .dark missing --chart-8 is an ERROR",
        ),
        Mutation(
            "the chart_hues comparison is dropped, so theme.css and brand.json can drift",
            "        if [h.lower() for h in declared] != [h.lower() for h in resolved[\"light\"]]:\n",
            "        if False:\n",
            ":root differing from brand.json chart_hues is an ERROR",
        ),
        Mutation(
            "the dark set is judged by the light band, or not at all",
            "        for failure in palette_failures(hues, mode):\n",
            "        for failure in (palette_failures(hues, mode) if mode == \"light\" else []):\n",
            "a dark chart set that fails the data-viz gates is an ERROR",
        ),
        Mutation(
            "var() is not followed, so a slot pointing at a primitive reads as unresolved",
            "        return resolve_value(decls[m.group(1)], decls, depth + 1)\n",
            "        return value.strip()\n",
            "a full, validated chart set resolving through a primitive passes",
        ),
    ),
)
