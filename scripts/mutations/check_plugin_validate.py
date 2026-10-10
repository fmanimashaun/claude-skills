"""Mutation guard: check_plugin_validate. Declared here, run by scripts/mutation_check.py (#1684).

Each mutation lets a validator run that did not really pass read as a pass, or drops a target, or turns a skip into a pass.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_plugin_validate",
    subject="scripts/check_plugin_validate.py",
    selftest="scripts/check_plugin_validate.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "`--strict` is no longer required in the report, so a run that did not apply it reads as a pass",
            '    if report["success"] is not True or report["strict"] is not True:',
            '    if report["success"] is not True:',
            "exit 0 but `strict` false means the flag did not apply",
        ),
        Mutation(
            "a null manifest is accepted, so a run that read nothing reads as a pass",
            '    if not isinstance(report.get("manifest"), dict):',
            "    if False:",
            "exit 0 but a null manifest means nothing was read",
        ),
        Mutation(
            "output that is not JSON is a pass",
            '        return 2, [f"  {target}: exit {done.returncode} and no JSON report',
            '        return 0, [f"  {target}: exit {done.returncode} and no JSON report',
            "output that is not JSON is exit 2",
        ),
        Mutation(
            "an older claude is accepted, so `--json` is assumed where it may not exist",
            "    if version is None or version < MIN_VERSION:",
            "    if version is None:",
            "an older claude is a skip (3)",
        ),
        Mutation(
            "no claude on PATH is a pass instead of a skip",
            "        print(\"could not check: no `claude` on PATH (exit 3, not a pass)\", file=sys.stderr)\n        return 3",
            "        print(\"could not check: no `claude` on PATH (exit 3, not a pass)\", file=sys.stderr)\n        return 0",
            "no claude on PATH is a skip (3), not a pass",
        ),
        Mutation(
            "a warning left in an exit-0 report is ignored",
            "    if findings(report):\n        return 1, findings(report)\n    return 0, []",
            "    return 0, []",
            "exit 0 with a warning still listed is a failure",
        ),
        Mutation(
            "a marketplace source with no plugin.json is skipped instead of raised, so a typo is silent",
            '                raise FileNotFoundError(f"{entry.get(\'name\')}: {source} has no .claude-plugin/plugin.json")',
            "                continue",
            "targets: a source with no plugin.json raises",
        ),
        Mutation(
            "an unexpected exit code is accepted",
            "    if done.returncode != 0:\n        return 2, [f\"  {target}: unexpected exit",
            "    if False:\n        return 2, [f\"  {target}: unexpected exit",
            "an unexpected exit code is exit 2",
        ),
        Mutation(
            "the plugin directories are never validated, only the marketplace",
            '            found.append(source.rstrip("/"))',
            "            pass",
            "targets: the marketplace first, then each local directory source",
        ),
    ),
)
