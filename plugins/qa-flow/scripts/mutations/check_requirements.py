"""Mutation guard: check_requirements. Declared here, run by scripts/mutation_check.py (#1855).

Each mutation lets a requirement with no real case read as covered, or lets the list of uncovered requirements grow quietly.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_requirements",
    subject="scripts/check_requirements.py",
    selftest="scripts/check_requirements.py",   # --selftest lives in the module itself
    # the subject imports qa_config to read the `requirements:` section of qa/qa.config.yml, and its selftest builds real refs with fixture_git;
    # unstaged, the unmutated selftest dies at the import
    needs=("scripts/qa_config.py", "scripts/fixture_git.py"),
    mutations=(
        Mutation(
            "a deprecated or draft case counts as coverage",
            '            if (row.get("Status") or "").strip().lower() != "active":',
            "            if False:",
            "a DEPRECATED case covers nothing",
        ),
        Mutation(
            "a requirement id is matched as a substring of a Source token, so REQ-001 is covered by REQ-0011",
            '        if entry.get("status") == "owner-decision" or rid in named or rid in listed:',
            '        if entry.get("status") == "owner-decision" or any(rid in token for token in named) or rid in listed:',
            "an id inside a longer token does not count",
        ),
        Mutation(
            "an owner-decision is no longer exempt, so a decision awaiting the owner fails the gate",
            '        if entry.get("status") == "owner-decision" or rid in named or rid in listed:',
            "        if rid in named or rid in listed:",
            "an owner-decision needs no case",
        ),
        Mutation(
            "the baseline no longer exempts a requirement, so grandfathered rows fail on day one",
            '        if entry.get("status") == "owner-decision" or rid in named or rid in listed:',
            '        if entry.get("status") == "owner-decision" or rid in named:',
            "a baselined uncased requirement is clean",
        ),
        Mutation(
            "a baseline line that is now cased is not reported, so the list never shrinks",
            "        elif line in named:",
            "        elif False:",
            "a baseline line that is now cased is a finding",
        ),
        Mutation(
            "the baseline's size header is not compared, so a line can be added unseen",
            "        if size != len(listed):",
            "        if False:",
            "a baseline whose size header is wrong is a finding",
        ),
        Mutation(
            "--base is ignored, so the baseline can grow against the branch it merges into",
            "            if line not in base:",
            "            if False:",
            "a baseline line not in the base branch's baseline is refused",
        ),
        Mutation(
            "a case naming a mistyped requirement id is not reported, so it covers nothing silently",
            '        if token not in by_id and ID.match(token) and token.split("-")[0].split(".")[0] in prefixes:',
            "        if False:",
            "a case naming a mistyped requirement id",
        ),
        Mutation(
            "a missing catalogue is a pass instead of exit 2",
            "        return 2, problems + case_problems",
            "        return 0, []",
            "a missing catalogue is exit 2, never a pass",
        ),
        Mutation(
            "a repeated requirement id is accepted",
            "        if rid in by_id:",
            "        if False:",
            "a repeated id is a finding",
        ),
        Mutation(
            "an unknown status is accepted",
            '        if entry.get("status") not in STATUSES:',
            "        if False:",
            "an unknown status is a finding",
        ),
        Mutation(
            "the requirements section of qa.config.yml is ignored, so declared paths are discarded",
            '    section = qa_config.load_section(config, "requirements")',
            "    section = {}",
            "paths come from the requirements section of qa.config.yml",
        ),
        Mutation(
            "a base ref that cannot be read reads as a first adoption, so the check passes without a comparison",
            '            return "unreadable", []',
            '            return "none", []',
            "a ref that does not exist is unreadable",
        ),
        Mutation(
            "a base with a registry and no baseline reads as a first adoption, so a baseline moved to a path the base lacks can grow (the ratchet bypass)",
            "    if not baselines and not registries:",
            "    if not baselines:",
            "a base with a registry and no baseline is an empty baseline",
        ),
        Mutation(
            "an unreadable configured or flagged base is a skip instead of exit 2",
            "            if explicit:",
            "            if False:",
            "a configured base that cannot be read is exit 2, not a skip",
        ),
        Mutation(
            "main no longer skips the growth check, with a note, when the base holds no registry or baseline",
            '        elif state == "none":',
            "        elif False:",
            "a base with no registry or baseline skips the growth check with a printed note",
        ),
        Mutation(
            "a clean tree whose DEFAULT base is missing passes instead of being a skip",
            "    if code == 0 and unchecked:",
            "    if False:",
            "a clean tree whose default base is missing is a skip (3) with a note",
        ),
        Mutation(
            "findings are hidden behind the skip when the default base is missing",
            "    if code == 0 and unchecked:",
            "    if unchecked:",
            "findings are reported, not hidden, when the default base is missing",
        ),
        Mutation(
            "the base's baseline is read at the configured path only, so moving the file reads as growth",
            "dict.fromkeys((baseline, BASELINE))",
            "dict.fromkeys((baseline,))",
            "moving the baseline file with the same lines is clean",
        ),
        Mutation(
            "a base ref that starts with `-` is passed to git, which reads it as an option",
            '    if ref and (not REF.match(ref) or any(part.startswith("-") for part in ref.split("/"))):',
            "    if False:",
            "a base ref that starts with `-` is refused",
        ),
        Mutation(
            "a base ref whose later component starts with `-` is accepted, so `origin/--upload-pack=...` reaches git fetch as an option",
            '    if ref and (not REF.match(ref) or any(part.startswith("-") for part in ref.split("/"))):',
            "    if ref and not REF.match(ref):",
            "a base ref with a component starting with `-` is refused",
        ),
        Mutation(
            "the base set in qa.config.yml is ignored, so a project on main cannot choose its base",
            '    ref = flag or (str(section["base"]) if section.get("base") else "")',
            '    ref = flag or ""',
            "a base set in qa.config.yml is used",
        ),
        Mutation(
            "a registry with no `# rows: N` header is accepted, so a requirement can be deleted with its baseline line unseen",
            "        if rows is None:",
            "        if False:",
            "a registry with no rows header is a finding",
        ),
        Mutation(
            "the rows header is not compared with the entry count",
            "        elif rows != len(entries):",
            "        elif False:",
            "a registry whose rows header is not its entry count is a finding",
        ),
        Mutation(
            "the catalogue is read without tolerating a BOM, so an Excel save reads as a missing column",
            '    with path.open(newline="", encoding="utf-8-sig") as handle:',
            '    with path.open(newline="", encoding="utf-8") as handle:',
            "a catalogue saved with a BOM is read",
        ),
        Mutation(
            "a requirements path outside the project is accepted",
            "        if not (root / value).resolve().is_relative_to(root.resolve()):",
            "        if False:",
            "a requirements path outside the project is exit 2 (..)",
        ),
    ),
)
