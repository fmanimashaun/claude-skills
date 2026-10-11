"""Mutation guard: report_third_party_hooks. Declared here, run by scripts/mutation_check.py (#866). A report that shows a failed hook
as 0 bytes, runs an old version, or measures our own plugins under "third-party" tells the maintainer something false (#1887)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="report_third_party_hooks",
    subject="scripts/report_third_party_hooks.py",
    selftest="scripts/report_third_party_hooks.py",
    mutations=(
        Mutation(
            "a failing hook is reported as its (empty) output size",
            '"bytes": len(r.stdout) if r.returncode == 0 else None}',
            '"bytes": len(r.stdout)}',
            "report: a failing hook is reported with its status, never as 0 bytes",
        ),
        Mutation(
            "versions sort as text, so 0.9.0 beats 0.10.0",
            "    pick = sorted(numbered or versions, key=lambda d: (_version_key(d.name), d.stat().st_mtime))",
            "    pick = sorted(numbered or versions, key=lambda d: d.name)",
            "report: the NEWEST version is run",
        ),
        Mutation(
            "this marketplace's own plugins are counted as third-party",
            "            if market != OURS:\n",
            "            if True:\n",
            "report: a disabled plugin, our own marketplace and a plugin not installed are left out",
        ),
        Mutation(
            "a disabled plugin is run",
            "        if on is True and \"@\" in key:",
            "        if \"@\" in key:",
            "report: a disabled plugin, our own marketplace and a plugin not installed are left out",
        ),
    ),
)
