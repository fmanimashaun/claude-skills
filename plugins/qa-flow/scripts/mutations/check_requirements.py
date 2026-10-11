"""Mutation guard: check_requirements. Declared here, run by scripts/mutation_check.py (#1855).

Each mutation lets a requirement with no real case read as covered, or lets the list of uncovered requirements grow quietly.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_requirements",
    subject="scripts/check_requirements.py",
    selftest="scripts/check_requirements.py",   # --selftest lives in the module itself
    # the subject imports qa_config to read the `requirements:` section of qa/qa.config.yml; unstaged, the unmutated selftest dies at the import
    needs=("scripts/qa_config.py",),
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
            '        section = qa_config.load_section(config, "requirements")',
            "        section = {}",
            "paths come from the requirements section of qa.config.yml",
        ),
        Mutation(
            "an unreadable --base ref reads as an empty baseline, so the check passes without a comparison",
            "        return [] if probe.returncode == 0 else None",
            "        return []",
            "an unreadable --base ref exits 2, never a pass",
        ),
    ),
)
