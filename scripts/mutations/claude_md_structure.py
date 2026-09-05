"""Mutation guard: claude_md_structure. Declared here, run by scripts/mutation_check.py (#875)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #875. The tool relocates history VERBATIM and refuses otherwise; these keep both halves honest.
GUARD = Guard(
    name="claude_md_structure",
    subject="plugins/rails-flow/scripts/claude_md_structure.py",
    selftest="plugins/rails-flow/scripts/claude_md_structure.py",
    mutations=(
        Mutation(
            "an issue reference alone becomes history, so citations get relocated",
            "    if ref and narr:",
            "    if ref:",
            "an issue number alone is a citation, not history",
        ),
        Mutation(
            "the lossless assertion is dropped, so a relocation may lose a paragraph",
            "        if p[\"text\"] not in new_history:",
            "        if False:",
            "a history that dropped a moved paragraph is REFUSED",
        ),
        Mutation(
            "past the ceiling stops being a verdict",
            "    return 1 if r[\"lines\"] > r[\"ceiling\"] else 0",
            "    return 0",
            "past the ceiling is a verdict of 1",
        ),
        Mutation(
            "no marker reads as a pass",
            "    if r[\"ceiling\"] is None:\n        return 3",
            "    if r[\"ceiling\"] is None:\n        return 0",
            "no marker is 3",
        ),
        Mutation(
            "the history paragraph is no longer removed from CLAUDE.md",
            "            i = para[\"end\"] + 1\n            continue",
            "            i = para[\"start\"]\n            keep.append(src[i - 1]); i += 1\n            continue",
            "propose removes the history paragraph",
        ),
        Mutation(
            "the ceiling is recorded from the pre-insertion count again, so the first --set-ceiling leaves the file one line over (#917)",
            '    return r["lines"] + (0 if r["ceiling"] is not None else 1)',
            '    return r["lines"]',
            "records the size WITH the marker",
        ),
        Mutation(
            "area-scoped rule paragraphs are no longer detected, so the third lever is never suggested (#927)",
            '    return min(hits)[1] if hits else None',
            '    return None',
            "is scoped to app/mailers",
        ),
    ),
)
