"""Mutation guard: check_turbo_streams. Declared here, run by scripts/mutation_check.py (#2277).

Every mutation here lets a shared stream, an unchecked channel or a viewer-bound broadcast partial read as clean: the one failure an access check can have.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_turbo_streams",
    subject="scripts/check_turbo_streams.py",
    selftest="scripts/check_turbo_streams.py",
    mutations=(
        Mutation("a literal stream name is not judged", "                if value not in declared:", "                if False:",
                 "a literal string name is a finding with its file:line"),
        Mutation("an interpolated name is judged as a literal", '"([^"#]*)"', '"([^"]*)"', "an interpolated name is not judged"),
        Mutation("a declared stream no view uses is accepted", "    for name in sorted(set(declared) - used):", "    for name in []:",
                 "a declaration no view uses is a finding"),
        Mutation("a declaration with no real reason is accepted", "        elif not isinstance(reason, str) or len(reason.strip()) < MIN_REASON:", "        elif False:",
                 "a declaration with no real reason is a finding"),
        Mutation("a declaration file that cannot be read passes", "        return 2, [str(exc)]", "        return 0, [str(exc)]",
                 "a declaration file that cannot be read is exit 2"),
        Mutation("a custom channel with no file is accepted", "                if channel_text is None:", "                if False:",
                 "a custom channel with no file is a finding"),
        Mutation("a custom channel need not define subscription_allowed?", '                elif "subscription_allowed?" not in channel_text:', "                elif False:",
                 "a custom channel without subscription_allowed? is a finding"),
        Mutation("current_* is not forbidden in a broadcast partial", r'FORBIDDEN = re.compile(r"\bcurrent_[a-z_]+\b|', r'FORBIDDEN = re.compile(r"|',
                 "the default partial of broadcasts_to that uses current_user is a finding"),
        Mutation("session is not forbidden in a broadcast partial", r"|\bsession\b|", "|",
                 "an explicit partial: of a broadcast call is followed, and session is forbidden"),
        Mutation("Current. is not forbidden in a broadcast partial", r"|\bCurrent\.", "",
                 "Current. is forbidden in a broadcast partial"),
        Mutation("everything is forbidden in a broadcast partial", "            if FORBIDDEN.search(line) and (partial, number) not in seen:",
                 "            if True and (partial, number) not in seen:", "a viewer-neutral broadcast partial is clean"),
        Mutation("the partial: of a broadcast call is never followed", "            window = text[start: starts[i + 1] if i + 1 < len(starts) else start + 400][:400]",
                 '            window = ""', "an explicit partial: of a broadcast call is followed, and session is forbidden"),
        Mutation("broadcasts_to is not read", '        if src.parent.name == "models" and BROADCASTS_TO.search(text):', "        if False:",
                 "the default partial of broadcasts_to that uses current_user is a finding"),
        Mutation("a default partial that cannot be located is not reported", "                unlocated += 1", "                pass",
                 "a default partial that cannot be located is reported, not passed in silence"),
    ),
)
