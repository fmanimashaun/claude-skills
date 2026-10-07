"""Mutation guard: extract_release_notes. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# rails-flow #127 + the rails-flow half of #128. FOUR of these seven break a fixture whose job
# is to stay SILENT, because a work order is ordinary prose about files and tests: `<...>` is a
# placeholder AND an HTML tag, "above" is the conversation AND the table three lines up, `TODO`
# is an unresolved decision AND part of `todo.rb`. A rule that flags the second of each pair
# gets the tool switched off, so the carve-outs are what need guarding.
GUARD = Guard(
    # #699. The bug shipped four times, so the fixtures that matter are the ones the OLD awk
    # would have failed -- two blocks under one tag, and a gate with teeth enough to refuse it.
    name="extract_release_notes",
    subject="scripts/extract_release_notes.py",
    selftest="scripts/extract_release_notes.py",
    needs=(".claude-plugin", ".github", "CHANGELOG.md", "scripts/release_local.sh",
           # #1520: component_versions() reads each plugin's own version.
           "plugins/rails-flow/.claude-plugin/plugin.json", "plugins/qa-flow/.claude-plugin/plugin.json",
           "plugins/pipeline/.claude-plugin/plugin.json", "plugins/design-flow/.claude-plugin/plugin.json"),
    mutations=(
        Mutation(
            "the tag being armed loses its exemption, so every arm reports its own release as a ghost",
            "        elif check_tags and tag != arming and tag not in tags:",
            "        elif check_tags and tag not in tags:",
            "the tag being ARMED has no git tag yet",
        ),

        # #834. `--check` looked only at the tag being armed. A block for a tag that was never cut
        # (v1.78.0) and a heading without the word `release` (v1.91.1) both published nothing,
        # and nothing could say so after the fact. Two assertions over the WHOLE file now.
        Mutation(
            "the shape assertion is dropped, so a `(vX)` heading is treated as publishable",
            "        if not PUBLISHING_SHAPE.search(line):",
            "        if False:",
            "all-tags: a heading naming a version WITHOUT the publishing shape is a finding",
        ),
        Mutation(
            "the tag-existence assertion is dropped, so a ghost release block is fine again",
            "        elif check_tags and tag != arming and tag not in tags:",
            "        elif False:",
            "all-tags: a (release vX) heading whose tag does not exist is a finding",
        ),
        Mutation(
            "the line number is dropped from the finding",
            '                f"{CHANGELOG}:{lineno}: heading names {tag} without the `(release {tag})` shape, so the "',
            '                f"{CHANGELOG}: heading names {tag} without the `(release {tag})` shape, so the "',
            "all-tags: the finding carries the line number",
        ),
        Mutation(
            "only the first block for a tag is grabbed -- the original bug, restored",
            "            if is_heading and needle in line:",
            "            if is_heading and needle in line and not out:",
            "second component's notes present — the bug",
        ),
        Mutation(
            # Without this the gate is the parser agreeing with itself.
            "the check stops noticing a block that would not publish",
            "        if stem not in produced:",
            "        if False:",
            "the check REFUSES the old first-block-only behaviour",
        ),
        Mutation(
            # The closing paren is the whole reason v1.9.0 cannot match v1.92.0.
            "the tag needle loses its closing paren, so a tag matches any tag it prefixes",
            '    needle = f"(release {tag})"\n    lines = text.split',
            '    needle = f"(release {tag}"\n    lines = text.split',
            "a prefix tag does not match the longer one",
        ),
        Mutation(
            "a tag with no block at all stops being a finding, so a release publishes a bare "
            "pointer and the gate says nothing",
            "    if not declared:",
            "    if False:",
            "no block is a CHECK finding",
        ),

        # #990. Two releases published only the Repository bullet because a component heading named
        # a stale-but-existing tag, and one promotion carried an Unreleased block onto main.
        Mutation(
            "the heading-order rule is switched off, so a component-version heading passes again",
            "        if prev is not None and key > prev[0]:",
            "        if False:",
            "order: a heading NEWER than the one above it in its section is a finding",
        ),
        Mutation(
            "the order comparison inverts and refuses every correct newest-first section",
            "        if prev is not None and key > prev[0]:",
            "        if prev is not None and key < prev[0]:",
            "order: a clean newest-first file has no findings",
        ),
        Mutation(
            "sections stop resetting the comparison, so the top of the next section is compared to the bottom of the last",
            "        if SECTION.match(line):\n            prev = None\n            continue",
            "        if SECTION.match(line):\n            continue",
            "order: sections are independent",
        ),
        Mutation(
            "the version key becomes lexical, so v1.9.0 reads newer than v1.92.0",
            '    return tuple(int(x) for x in tag.lstrip("v").split("."))',
            '    return tuple(x for x in tag.lstrip("v").split("."))',
            "order: numeric, not lexical",
        ),
        Mutation(
            "the Unreleased rule matches nothing, so a ghost block rides the promotion",
            '        for lineno, line in enumerate(text.split("\\n"), 1) if UNRELEASED.match(line)',
            '        for lineno, line in enumerate(text.split("\\n"), 1) if False',
            "promotion: an Unreleased heading is a finding",
        ),

        # #1520. #1518 put an Unreleased block under the DEAD rails-stack section and --check stayed clean.
        Mutation("an Unreleased block under an archived section passes again (#1518)",
                 '            for lineno in sec["unreleased"]:', "            for lineno in []:",
                 "Unreleased under the ARCHIVED section is a finding"),
        Mutation("two live sections for one component pass",
                 "        if len(secs) > 1:", "        if False:",
                 "two live sections for one component are a finding"),
        Mutation("an ARCHIVED entry matching no section passes, so a release added to it goes unseen",
                 "        if entry not in matched:", "        if False:",
                 "a release added to an archived section unmatches it"),
        Mutation("Unreleased in a section that is not at the current version passes",
                 "            elif newest != current:", "            elif False:",
                 "whose newest release is not the current version"),
        Mutation("Unreleased under a component nothing versions passes",
                 "            if current is None:", "            if False and current is None:",
                 "a component nothing versions"),
        Mutation("the OLDEST release heading is taken as a section's newest, so no archive entry matches",
                 '        elif out and out[-1]["newest"] is None and HEADING.match(line)', "        elif out and HEADING.match(line)",
                 "one live section per component"),
        Mutation("--check stops running the section rule",
                 "        findings += problems + _check_sections(text, versions)\n", "",
                 "--check runs the section rule"),
        # The review of PR #1522: metadata.version bumps on every promotion, the Repository section does not.
        Mutation("a marketplace-versioned section is compared with metadata.version again",
                 "            if component in METADATA_SECTIONS:\n                continue", "            if False:\n                continue",
                 "may lag metadata.version, and is not compared"),
        Mutation("a missing plugin.json is no longer named",
                 "        if not version and not own.is_file():", "        if False:",
                 "a missing plugin.json is NAMED"),
        Mutation("a plugin.json with no version is no longer named",
                 "        else:\n            problems.append(f\"{own.relative_to(root)} has no `version`",
                 "        elif False:\n            problems.append(f\"{own.relative_to(root)} has no `version`",
                 "a plugin.json with no version is named"),
        Mutation("an unreadable file is read as empty instead of raising",
                 '        raise VersionLookupError(f"{path}: {e}") from e', "        return {}",
                 "an unreadable plugin.json raises"),
        Mutation("a manifest with no metadata.version passes",
                 "    if not isinstance(data.get(\"metadata\"), dict) or not data[\"metadata\"].get(\"version\"):",
                 "    if False:",
                 "a manifest with no metadata.version raises"),
        Mutation("a failed lookup no longer exits 3",
                 "            return 3\n        findings += problems", "            versions, problems = {}, []\n        findings += problems",
                 "--check exits 3 (could not check)"),

        # #1523. A block ends at the next `## ` section heading, not only at the next `### `.
        Mutation("a section heading stops ending a block, so it leaks into the notes above it again",
                 "        if is_heading or (sections_end_blocks and SECTION.match(line)):",
                 "        if is_heading or (False and SECTION.match(line)):",
                 "a section heading after a block's last line is not in that block's notes"),
        Mutation("the section pattern loses its space, so `##notaheading` prose ends a block",
                 'SECTION = re.compile(r"^## ")', 'SECTION = re.compile(r"^##")',
                 "stay in the block"),
        Mutation("the section pattern matches any `#`, so a comment inside a fenced block ends the block",
                 'SECTION = re.compile(r"^## ")', 'SECTION = re.compile(r"^#")',
                 "stay in the block"),

        # #1520 review, S1 remnant: the DEFAULT-tag path (the doctor gate and gates.yml run it).
        Mutation("current_tag reads metadata.version with a bare subscript again, a KeyError traceback",
                 '    return "v" + _manifest(root)["metadata"]["version"]',
                 '    return "v" + json.loads((root / MANIFEST).read_text(encoding="utf-8"))["metadata"]["version"]',
                 "current_tag: a manifest with no metadata.version raises VersionLookupError"),
        Mutation("a failed default-tag lookup exits 1 instead of 3",
                 '        print(f"could not determine the release tag: {e} (exit 3, not a pass)", file=sys.stderr)\n        return 3',
                 '        print(f"could not determine the release tag: {e} (exit 3, not a pass)", file=sys.stderr)\n        return 1',
                 "the default-tag lookup failing exits 3"),

        # #1637. A release body over 125,000 characters fails the publish AFTER the gates pass (v1.154.0).
        Mutation("the size rule never shortens, so an oversize body is published whole and GitHub refuses it",
                 '    if len(full) <= NOTES_BUDGET:\n        return full, "full"',
                 '    if True:\n        return full, "full"',
                 "notes over the budget publish headlines"),
        Mutation("the headroom is zero, so a body that fits only before the Install line is appended is published",
                 "BODY_HEADROOM = 2_000", "BODY_HEADROOM = 0",
                 "notes inside the headroom are still shortened"),
        Mutation("--check stops asking whether even the headline form fits",
                 "        findings += _check_size(text, tag, a.repo)\n", "",
                 "--check runs the size rule"),
        Mutation("a bullet's headline keeps its whole first line, prose and all",
                 "    if m:\n        return f\"- **{m.group(1)}**\"", "    if False:\n        return f\"- **{m.group(1)}**\"",
                 "the prose of a bullet is not in the headline form"),
        Mutation("a bullet inside a fenced code sample is read as a change, so the headline form invents one",
                 "        if not fenced:\n            out.append(line)", "        out.append(line)",
                 "a `- item` inside a fenced code block is not a bullet"),
        Mutation("the headline form drops the link to the full notes",
                 "Every bullet in full: {changelog_url(tag, repo)}", "Every bullet in full.",
                 "the body links to CHANGELOG.md at the tag"),
        Mutation("--full is shortened like the default, so the issue notifier loses its citations",
                 "    if a.full:\n        sys.stdout.write(render(text, tag)[0])", "    if False:\n        sys.stdout.write(render(text, tag)[0])",
                 "--full is never shortened"),
    ),
)
