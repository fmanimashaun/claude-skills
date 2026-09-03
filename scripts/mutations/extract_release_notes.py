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
    needs=(".claude-plugin", ".github", "CHANGELOG.md", "scripts/release_local.sh"),
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
            "            if needle in line:",
            "            if needle in line and not out:",
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
    ),
)
