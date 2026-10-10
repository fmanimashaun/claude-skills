"""Mutation guard: changelog_fragments. Declared here, run by scripts/mutation_check.py (#1825).

The fold is what a hand-resolved CHANGELOG conflict used to be: if it drops, duplicates or misplaces a bullet, the release notes are wrong and nothing
else notices. Each mutant breaks one property of the fold or of the check that holds a fragment to the CHANGELOG's own rule.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="changelog_fragments",
    subject="scripts/changelog_fragments.py",
    selftest="scripts/changelog_fragments.py",
    needs=("scripts/lint_self_consistency.py", "plugins/rails-flow/scripts/fixture_git.py"),
    mutations=(
        Mutation(
            "a fragment goes BELOW the section's existing bullets, so the newest note is last",
            "            lines[first:first] = group\n",
            "            lines[first + 1:first + 1] = group\n",
            "a fragment goes ABOVE the section's existing bullets",
        ),
        Mutation(
            "fragments fold in name order, so issue 10 comes before issue 9",
            "key=lambda p: (int(m.group(1)) if (m := re.match(r\"(\\d+)-\", p.name)) else 10 ** 9, p.name))",
            "key=lambda p: p.name)",
            "numeric issue order",
        ),
        Mutation(
            "the bullet-count assertion is never made",
            "    if count_bullets(after) != want:\n",
            "    if False:\n",
            "the bullet-count assertion refuses a dropped bullet",
        ),
        Mutation(
            "an ambiguous section prefix is resolved to the first heading",
            "    if len(hits) > 1:\n        live",
            "    if False:\n        live",
            "an ambiguous prefix is an error",
        ),
        Mutation(
            "a section with no `### Unreleased` gets none, so its fragment is lost",
            "            lines[at:at] = [UNRELEASED, \"\", RELEASE_NOTE, \"\"] + group + [\"\"]\n",
            "            lines[at:at] = []\n",
            "a section with no Unreleased gets one",
        ),
        Mutation(
            "a fold into an armed block falls back to `### Unreleased` when the block is missing",
            "            if into is not None:\n                raise FragmentError(f\"the section",
            "            if False:\n                raise FragmentError(f\"the section",
            "--into a block that does not exist is an error",
        ),
        Mutation(
            "a fragment with two bullets is accepted",
            "        if l.startswith(\"- \"):\n            raise FragmentError(f\"{name}: two bullets",
            "        if False:\n            raise FragmentError(f\"{name}: two bullets",
            "two bullets is refused",
        ),
        Mutation(
            "a fragment's name is not checked",
            "    if not NAME.match(name):\n",
            "    if False:\n",
            "a bad name is refused",
        ),
        Mutation(
            "a fragment that names no path is accepted",
            "        if not cited:\n",
            "        if False:\n",
            "a fragment naming no path is unplaceable",
        ),
        Mutation(
            "a fragment under another component's section is accepted",
            "        elif L._changelog_section_owner(heading, plugins) not in owners:\n",
            "        elif False:\n",
            "a fragment naming only another component's path is misfiled",
        ),
        Mutation(
            "a name that disagrees with the bullet's issue is accepted",
            "        elif not p.name.startswith(f\"{issue}-\"):\n",
            "        elif False:\n",
            "a name and a bullet that cite different issues are refused",
        ),
        Mutation(
            "the fold writes over a CHANGELOG with uncommitted changes",
            "    if require_clean and not dry_run and _dirty(root):\n",
            "    if False:\n",
            "a fold refuses a CHANGELOG with uncommitted changes",
        ),
        Mutation(
            "a failed fold deletes its fragments anyway",
            "    new = fold_text(cl.read_text(encoding=\"utf-8\"), frags, into)\n",
            "    try:\n        new = fold_text(cl.read_text(encoding=\"utf-8\"), frags, into)\n    except FragmentError:\n        new = cl.read_text(encoding=\"utf-8\")\n",
            "a fold with one unplaceable fragment is refused",
        ),
    ),
)
