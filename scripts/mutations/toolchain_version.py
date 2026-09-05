"""Mutation guard: toolchain_version. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="toolchain_version",
    subject="plugins/rails-flow/scripts/toolchain_version.py",
    selftest="plugins/rails-flow/scripts/toolchain_version_selftest.py",
    mutations=(
        Mutation(
            # Two records for one plugin coexist in the cache, ordered ONLY by lastUpdated.
            # Picking arbitrarily reports the stale one as installed, so an out-of-date
            # toolchain reads as current -- which is the single thing pillar 1 exists to catch.
            "the newest install record stops winning, so a stale version reads as installed",
            '    return max(records, key=lambda r: (r or {}).get("lastUpdated") or "")',
            "    return records[0]",
            "shadowed-record: newest wins",
        ),
        Mutation(
            "a plugin whose published version did not resolve is folded into 'up to date' again (#923)",
            '    if unresolved:\n        for n in unresolved:',
            '    if False:\n        for n in unresolved:',
            "unresolved-published",
        ),
    ),
)
