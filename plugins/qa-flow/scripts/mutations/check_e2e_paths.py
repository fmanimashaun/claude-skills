"""Mutation guard: check_e2e_paths. Declared here, run by scripts/mutation_check.py (#1856).

Each mutation lets a feature with no runnable end-to-end path read as covered, or makes a runner the check cannot read read as a pass.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_e2e_paths",
    subject="scripts/check_e2e_paths.py",
    selftest="scripts/check_e2e_paths.py",   # --selftest lives in the module itself
    narrow_with="--match",                   # each mutant runs only the scenario row its `expects` names (#1599)
    # the subject imports check_requirements (the registry reader and the baseline ratchet), which imports qa_config
    needs=("scripts/check_requirements.py", "scripts/qa_config.py"),
    mutations=(
        Mutation(
            'a skipped test still names a requirement',
            'skipped = any(x in ("skip", "fixme") for x in mods)',
            'skipped = False',
            'a skipped test names nothing',
        ),
        Mutation(
            'a skipped describe no longer skips the tests inside it',
            'if call["skipped"] or any(c["skipped"] for c in chain):',
            'if call["skipped"]:',
            'a skipped describe skips every test inside it',
        ),
        Mutation(
            'comments are not blanked, so an id in a comment names a test',
            '    text = blank_comments(text)\n    calls = []',
            '    calls = []',
            'a commented-out test names nothing',
        ),
        Mutation(
            'an id is matched as a substring, so REQ-001 is named by REQ-0011',
            '    pattern = re.compile(r"(?<![A-Za-z0-9._-])" + re.escape(rid) + r"(?![A-Za-z0-9._-])")',
            '    pattern = re.compile(re.escape(rid))',
            'an id inside a longer token is not named',
        ),
        Mutation(
            'the file path counts as a title, so a spec named after the id names it',
            '    return any(pattern.search(piece) for piece in [*test["titles"], *test["tags"]])',
            '    return any(pattern.search(piece) for piece in [test["composite"]])',
            'an id only in the file path is not named',
        ),
        Mutation(
            'grep and grep-invert never exclude a test',
            '        if bool(compiled.search(test["composite"])) == invert:',
            '        if False:',
            'a --grep-invert that excludes the tag leaves the spec out',
        ),
        Mutation(
            'a grep selects what it does not match (inverted)',
            '        if bool(compiled.search(test["composite"])) == invert:',
            '        if bool(compiled.search(test["composite"])) != invert:',
            'the @real-signin shape',
        ),
        Mutation(
            'a positional file filter is not applied',
            '        if not compiled.search(absolute):',
            '        if False:',
            'a positional file filter that does not match the spec leaves it out',
        ),
        Mutation(
            'a grep built from a shell variable reads as a literal',
            '            if "$" in raw:',
            '            if False:',
            'a grep built from a shell variable cannot be read',
        ),
        Mutation(
            'a repeated --grep is accepted although its combination is undocumented',
            '    if len(command["grep"]) > 1 or len(command["invert"]) > 1:',
            '    if False:',
            'a repeated --grep cannot be read',
        ),
        Mutation(
            'a command-line grep and a config grep are combined although that is undocumented',
            '    if command["grep"] and config["grep"]:',
            '    if False:',
            'a config grep with a command-line grep cannot be combined',
        ),
        Mutation(
            'a config grep is ignored when the command has none',
            '        source = (raw[0], "") if raw else config_value',
            '        source = (raw[0], "") if raw else None',
            'a config grep alone is applied',
        ),
        Mutation(
            'a project-level filter in the config is not flagged as unreadable',
            '    if re.search(r"\\b(grep|grepInvert|testMatch|testIgnore)\\s*:", inside):',
            '    if False:',
            'a project-level grep in the config cannot be read',
        ),
        Mutation(
            'an undecidable requirement passes instead of being a skip',
            '    if uncertain:\n        return 3, findings, notes + [',
            '    if False:\n        return 3, findings, notes + [',
            'a repeated --grep cannot be read',
        ),
        Mutation(
            'a definite finding is hidden behind an undecidable one',
            '    if findings:\n        return 1, findings, notes',
            '    if findings and not uncertain:\n        return 1, findings, notes',
            'a finding is still reported when another feature cannot be decided',
        ),
        Mutation(
            'the baseline no longer exempts a feature with no spec',
            '            if rid not in listed:\n                findings.append(f"{rid}: a feature, but no',
            '            if True:\n                findings.append(f"{rid}: a feature, but no',
            'a baselined feature with no spec is clean',
        ),
        Mutation(
            'a baseline line for a now-selected feature is not reported',
            '        elif rid in selected_ids:',
            '        elif False:',
            'a baseline line for a feature that is now selected is a finding',
        ),
        Mutation(
            'the baseline size header is not compared',
            '    if (listed or size is not None) and size != len(listed):',
            '    if False:',
            'a baseline whose size header is wrong is a finding',
        ),
        Mutation(
            '--base growth is not checked',
            '            if rid not in base:',
            '            if False:',
            "a baseline line not in the base's baseline is refused",
        ),
        Mutation(
            'no declared runner is a pass instead of a skip',
            '    if not conf["runners"]:\n        return 3, findings,',
            '    if not conf["runners"]:\n        return 0, findings,',
            'no runner files declared is exit 3',
        ),
        Mutation(
            'a web_e2e other than playwright is read as playwright',
            '    if declared and declared.group(1) not in ("playwright", "none"):',
            '    if False:',
            'a web_e2e other than playwright is exit 3',
        ),
        Mutation(
            'shell comments are not stripped, so a comment becomes a runner',
            '        sources = [strip_shell_comments(text).replace(',
            '        sources = [text.replace(',
            'a comment that says playwright test is not a runner',
        ),
        Mutation(
            'a # inside a quoted pattern is cut as a comment',
            '            elif ch == "#" and (i == 0 or line[i - 1] in " \\t"):',
            '            elif ch == "#":',
            'a # in the middle of a word is not a comment',
        ),
    ),
)
