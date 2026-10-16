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
            "an ambiguous section name is resolved to the first heading instead of refused",
            "    if len(headings) > 1:\n        raise FragmentError(",
            "    if False:\n        raise FragmentError(",
            "an ambiguous name is an error naming both headings",
        ),
        Mutation(
            "a section is matched by PREFIX again, so a prefix of an old heading's title is filed under a stale `### Unreleased`",
            "    hits = [s for s in secs if s[1] == want] or [s for s in secs if heading_name(s[1]) == want]\n",
            "    hits = [s for s in secs if s[1].startswith(want)]\n",
            "a PREFIX of an older heading's title is refused",
        ),
        Mutation(
            "a typo lists only the headings that start with the same word",
            "f\"The sections a fragment can name: {listing(secs)}\")",
            "f\"The sections a fragment can name: {listing(secs, [h for h in {x[1] for x in secs} if h.split(' ', 1)[0] == want.split(' ', 1)[0]])}\")",
            "a typo lists EVERY valid section",
        ),
        Mutation(
            "every heading is marked live, so the stale one cannot be told from the live one",
            "        mark = \"[live]\" if newest[h] == top else (",
            "        mark = \"[live]\" if True else (",
            "every listing marks the LIVE heading and the older one",
        ),
        Mutation(
            "an `### Unreleased` breaks a tie between different headings again",
            "    headings = list(dict.fromkeys(s[1] for s in hits))\n",
            "    headings = list(dict.fromkeys(s[1] for s in (hits if len({s[1] for s in hits}) < 2 else ([h for h in hits if h[2]] or hits))))\n",
            "does NOT break the tie",
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
        Mutation(
            'identical headings are no longer treated as one, so `## Repository hygiene` twice is ambiguous again',
            '    headings = list(dict.fromkeys(s[1] for s in hits))\n',
            '    headings = [s[1] for s in hits]\n',
            'two IDENTICAL headings with no Unreleased resolve',
        ),
        Mutation(
            '--into does not look for the heading that holds the armed block',
            '        pool = [s for s in pool if into in s[3]] or pool\n',
            '        pass\n',
            '--into on identical headings goes to the one holding the release block',
        ),
        Mutation(
            'a fragment saved with CRLF endings is read with a stray carriage return',
            '    lines = text.replace("\\r\\n", "\\n").replace("\\r", "\\n").rstrip("\\n").split("\\n")',
            '    lines = text.rstrip("\\n").split("\\n")',
            'a fragment with CRLF endings parses',
        ),
        Mutation(
            'a git failure is read as a clean CHANGELOG',
            '    return r.returncode != 0 or bool(r.stdout.strip())',
            '    return r.returncode == 0 and bool(r.stdout.strip())',
            'a git failure is treated as a dirty CHANGELOG',
        ),
        # #1841: a bullet added directly under `### Unreleased` is refused; each path of the rule has a mutant.
        Mutation(
            'no bullet is ever a direct bullet',
            '        if seen[(heading, name)] <= have[(heading, name)]:\n            continue',
            '        if True:\n            continue',
            'a bullet added directly under `### Unreleased` is a finding',
        ),
        Mutation(
            'an edit of a bullet base already has is refused',
            '        if seen[(heading, name)] <= have[(heading, name)]:',
            '        if False:',
            'an EDIT of a bullet base already has',
        ),
        Mutation(
            'the folded copy of a deleted fragment is refused',
            '        if moved[name] > 0:',
            '        if False:',
            'the folded copy of a fragment this change deletes',
        ),
        Mutation(
            'any deleted fragment excuses any bullet',
            '        if moved[name] > 0:',
            '        if moved:',
            'a deleted fragment for a DIFFERENT bullet does not excuse it',
        ),
        Mutation(
            'a bullet under a release block counts as direct',
            '            inside, cur = line.strip() == UNRELEASED, None',
            '            inside, cur = True, None',
            'added under a RELEASE block',
        ),
        Mutation(
            'the finding no longer names the fragment path',
            'add changelog.d/{issue}-{slug}.md, whose first line is',
            'add a fragment, whose first line is',
            'that names the fragment path to use',
        ),
        Mutation(
            'an unreadable base is reported clean',
            '        return (1 if in_ci else 3), [f"cannot read',
            '        return 0, [f"cannot read',
            'a base that does not exist is a SKIP (3)',
        ),
        Mutation(
            'deleted fragments are not read, so a fold is refused',
            '"--diff-filter=D"',
            '"--diff-filter=A"',
            'with the fragment it came from deleted',
        ),
        Mutation(
            'an unreadable base is a skip even in CI',
            '    if base is None or not cl.is_file():\n        return (1 if in_ci else 3), [',
            '    if base is None or not cl.is_file():\n        return 3, [',
            'in CI an unreadable base is a FAILURE (1)',
        ),
        Mutation(
            "the branch is compared with the base's tip, not the commit it was cut from",
            '    base = _git_out(root, "show", f"{mb}:CHANGELOG.md") if mb else None',
            '    base = _git_out(root, "show", f"{base_ref}:CHANGELOG.md") if mb else None',
            'a branch cut before the base armed is compared with the commit it was cut from',
        ),
        Mutation(
            'headlines are looked up, not counted',
            '        if seen[(heading, name)] <= have[(heading, name)]:',
            '        if have[(heading, name)]:',
            'a SECOND bullet with a headline the section already has is a finding',
        ),
        Mutation(
            'one deleted fragment excuses every bullet with its headline',
            '            moved[name] -= 1                           # one deleted fragment excuses ONE bullet',
            '            pass',
            'one deleted fragment excuses ONE of two bullets',
        ),
    ),
)
