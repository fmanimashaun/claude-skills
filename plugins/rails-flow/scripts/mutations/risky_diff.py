"""Mutation guard: risky_diff (#1819). Declared here, run by scripts/mutation_check.py.

Each mutation lets a risky diff through without the adversarial pass, makes a stale or hand-waved record count, swallows a BLOCKED
verdict, or holds a harmless change. The named fixture in `risky_diff.py --selftest` must go red for each.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="risky_diff",
    subject="scripts/risky_diff.py",
    selftest="scripts/risky_diff.py",   # --selftest lives in the module itself
    needs=("scripts/fixture_git.py", "scripts/classify_door.py", "scripts/advisory_scope.py", "scripts/check_threat_model.py", "scripts/detect_stack.py", "checks.json"),
    # its git goes through fixture_git (#1588); it imports classify_door's diff, and advisory_scope's override line, filler test, issue check and slug (#2264)
    mutations=(
        Mutation(
            "a spec or test file counts as risky, so every spec that parses JSON holds the PR",
            '        if path.startswith(("spec/", "test/")) or "/spec/" in path or "/test/" in path:',
            "        if False:",
            "CONTROL: a file under a nested /spec/ directory is not risky even when it parses JSON",
        ),
        Mutation(
            "a policy file is not on the access surface",
            '    ("access", re.compile(r"^app/policies/|',
            '    ("access", re.compile(r"^app/NEVER/|',
            "a policy is risky",
        ),
        Mutation(
            "an initializer named author_names is read as an auth initializer (the substring, not the word)",
            "(?:[^/]*[_-])?(?:auth|authentication|devise",
            "[^/]*(?:auth|authentication|devise",
            "coauth",
        ),
        Mutation(
            "strong parameters are not a parsing surface",
            r"|\bNokogiri::|\bparams\.(?:require|permit)\b",
            r"|\bNokogiri::",
            "strong parameters are risky",
        ),
        Mutation(
            "a risky diff with no --record is not asked for the pass",
            "    if record is None or head is None:\n        return 1,",
            "    if record is None or head is None:\n        return 0,",
            "a risky diff with no --record asks for the pass",
        ),
        Mutation(
            "a record for another commit is accepted, so a pass on an old head stands in for this one",
            "    if not any(head.startswith(h) for h in heads):",
            "    if False:",
            "a record for another commit is stale",
        ),
        Mutation(
            "a record with no Head line is accepted",
            "    if not heads:\n",
            "    if False:\n",
            "a record with no Head line is refused",
        ),
        Mutation(
            "a BLOCKED verdict with no override exits 0, so the finding never reaches the human",
            "        return 1, [f\"RISKY ({len(reasons)} reason(s)), adversary pass recorded BLOCKED -- a finding",
            "        return 0, [f\"RISKY ({len(reasons)} reason(s)), adversary pass recorded BLOCKED -- a finding",
            "a BLOCKED record with no override is a finding for a human",
        ),
        Mutation(
            "a BLOCKED verdict exits 3 again, which the project gates read as not applicable (#1873)",
            "        return 1, [f\"RISKY ({len(reasons)} reason(s)), adversary pass recorded BLOCKED -- a finding",
            "        return 3, [f\"RISKY ({len(reasons)} reason(s)), adversary pass recorded BLOCKED -- a finding",
            "a BLOCKED record with no override is a finding for a human",
        ),
        Mutation(
            "an override with a short reason is accepted",
            " and len(m.group(2)) >= advisory_scope.REASON_MIN",
            "",
            "BLOCKED with an override whose reason is short is refused",
        ),
        Mutation(
            "an override with a filler reason is accepted",
            "and not advisory_scope._filler(m.group(2)) and ISSUE_CHECK(",
            "and ISSUE_CHECK(",
            "BLOCKED with an override whose reason is filler is refused",
        ),
        Mutation(
            "an override citing an issue nobody can read is accepted",
            " and ISSUE_CHECK(root, m.group(3))):",
            "):",
            "BLOCKED with an override citing an issue that cannot be read is refused",
        ),
        Mutation(
            "the record is not derived from the branch, so the registered check asks for a pass nobody can name",
            "record = a.record if a.record else (default_record(a.root) if reasons else None)",
            "record = a.record",
            "record derived from the branch",
        ),
        Mutation(
            "a detached HEAD reads as a branch named nothing, so the record path is prs//adversary.md and the answer is 1, not 2",
            "    if not slug:\n        raise Unusable(",
            "    if False:\n        raise Unusable(",
            "a detached HEAD cannot name its record",
        ),
        Mutation(
            "a base that exists only as origin/<base> is no longer tried, so a CI checkout cannot classify",
            '    for candidate in (base, f"origin/{base}"):',
            "    for candidate in (base,):",
            "a base that exists only as origin/<base> still resolves",
        ),
        Mutation(
            "the FIRST verdict decides, so a later BLOCKED is not seen",
            "    return verdicts[-1], f",
            "    return verdicts[0], f",
            "the LAST verdict decides",
        ),
        Mutation(
            "a verdict quoted inside a sentence counts as the verdict line",
            'VERDICT = re.compile(r"^VERDICT:\\s*(CLEAN|BLOCKED)\\s*$")',
            'VERDICT = re.compile(r".*VERDICT:\\s*(CLEAN|BLOCKED)\\s*$")',
            "a verdict quoted inside a sentence",
        ),
        Mutation(
            "the record is derived with the prefix dropped (feature/x is x), so the gate looks where no agent writes",
            '    return out.replace("/", "-")',
            '    return out.split("/", 1)[-1].replace("/", "-")',
            "record derived from the branch",
        ),
        Mutation(
            "a VERDICT line inside a fenced example decides the verdict",
            "    lines = unfenced(text)\n    heads",
            "    lines = text.splitlines()\n    heads",
            "a VERDICT line inside a fenced block is not the verdict",
        ),
        Mutation(
            "an Override line inside a fenced example grants the override",
            '        lines = unfenced(path.read_text(encoding="utf-8"))',
            '        lines = path.read_text(encoding="utf-8").splitlines()',
            "an override inside a fenced block grants nothing",
        ),
        Mutation(
            "an override whose who has no letters is accepted",
            "sum(c.isalpha() for c in m.group(1)) >= WHO_MIN_LETTERS and ",
            "",
            "BLOCKED with an override whose who has one letter is refused",
        ),
        Mutation(
            "a pull request number counts as the follow-up issue",
            ' and "/issues/" in proc.stdout',
            "",
            "a pull request number is no issue",
        ),
        Mutation(
            "the issue is looked up in the caller's repository, not the one at --root",
            "timeout=30, cwd=root)",
            "timeout=30)",
            "it is read in the repository at --root",
        ),
    ),
)
