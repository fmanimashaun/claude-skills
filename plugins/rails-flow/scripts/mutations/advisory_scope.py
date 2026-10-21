"""Mutation guard: advisory_scope (#2262). Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="advisory_scope",
    subject="scripts/advisory_scope.py",
    selftest="scripts/advisory_scope.py",
    selftest_args=("--selftest",),
    # It reuses security_scope (the security category), check_threat_model (the filler test) and detect_stack; the selftest
    # builds a scratch repo through fixture_git.
    needs=("scripts/security_scope.py", "scripts/check_threat_model.py", "scripts/detect_stack.py", "scripts/fixture_git.py"),
    mutations=(
        Mutation(
            "the security category stops firing",
            "    if sec:\n        found[\"security\"] = sec[0]",
            "    if False:\n        found[\"security\"] = sec[0]",
            "a webhook is security",
        ),
        Mutation(
            "a structure path stops firing",
            "        if STRUCTURE_PATHS.search(p):",
            "        if False:",
            "a new agent path is structure",
        ),
        Mutation(
            "a migration path stops being data-model",
            "        if (migrations and p.startswith(migrations.rstrip(\"/\") + \"/\")) or (schema and p == schema):",
            "        if False:",
            "a migration path is data-model",
        ),
        Mutation(
            "a dependency manifest stops firing",
            "        if p in manifests or LOCKFILE.search(p):",
            "        if False:",
            "a lockfile is dependency",
        ),
        Mutation(
            "the breadth threshold drops to five",
            "BREADTH = 6",
            "BREADTH = 5",
            "five components is not breadth",
        ),
        Mutation(
            "bookkeeping paths count toward breadth again",
            "    components = sorted({\"/\".join(p.split(\"/\")[:2]) for p in paths if not BOOKKEEPING.match(p)})",
            "    components = sorted({\"/\".join(p.split(\"/\")[:2]) for p in paths})",
            "bookkeeping paths do not count toward breadth",
        ),
        Mutation(
            "an undisposed finding passes",
            "        if count == 0:",
            "        if False:",
            "an undisposed finding is refused",
        ),
        Mutation(
            "a finding disposed twice passes",
            "        elif count > 1:",
            "        elif False:",
            "a finding disposed twice is refused",
        ),
        Mutation(
            "a filler disposition reason passes",
            "        if _filler(reason):",
            "        if False:",
            "a filler reason is refused",
        ),
        Mutation(
            "a deferral without an issue passes",
            "        if kind == \"deferred\" and not re.search(r\"#\\d+\", reason):",
            "        if False:",
            "a deferral without an issue is refused",
        ),
        Mutation(
            "a changed plan passes without a stamp",
            "    if current_hash != reviewed and (not disposed or disposed[-1] != current_hash):",
            "    if False:",
            "a changed plan with no stamp is refused",
        ),
        Mutation(
            "a new category passes without a new review",
            "    if new := sorted(current_cats - reviewed_cats):",
            "    if new := []:",
            "a new category is refused",
        ),
        Mutation(
            "RETHINK passes with no override",
            "    if verdicts and verdicts[-1] == \"RETHINK\":",
            "    if False:",
            "RETHINK with no override is refused",
        ),
        Mutation(
            "a short override reason is accepted",
            "        good = [m for m in overrides if m and len(m.group(2)) >= REASON_MIN and not _filler(m.group(2))]",
            "        good = [m for m in overrides if m]",
            "RETHINK with a short override is refused",
        ),
        Mutation(
            "a rewrite over the threshold can be stamped",
            "        if share > RESTAMP_MAX:",
            "        if False:",
            "a rewrite over 30% cannot be stamped",
        ),
        Mutation(
            "a required advisory with no record passes",
            "    if not record.is_file():\n        print(f\"advisory REQUIRED",
            "    if False:\n        print(f\"advisory REQUIRED",
            "a required advisory with no record is exit 1",
        ),
    ),
)
