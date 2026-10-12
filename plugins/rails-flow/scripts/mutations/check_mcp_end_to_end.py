"""Mutation guard: check_mcp_end_to_end. Declared here, run by scripts/mutation_check.py (#1930).

The mutations that matter make the gate VACUOUS (no declaration passes, a unit spec counts, one method is enough) or turn
"nobody decided" into "nothing to check".
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_mcp_end_to_end",
    subject="scripts/check_mcp_end_to_end.py",
    selftest="scripts/check_mcp_end_to_end.py",
    mutations=(
        Mutation("the mcp gem with no declaration is n/a, so a project that never decided reads green",
                 "        return 1, [f\"the Gemfile declares the `mcp` gem and {DECLARATION} does not exist",
                 "        return 3, [f\"the Gemfile declares the `mcp` gem and {DECLARATION} does not exist",
                 "the mcp gem with no declaration is a finding, not n/a"),
        Mutation("no mcp gem is a pass, not n/a",
                 '        return 3, ["n/a: the Gemfile declares no `mcp` gem',
                 '        return 0, ["n/a: the Gemfile declares no `mcp` gem',
                 "no mcp gem must be n/a (exit 3)"),
        Mutation("a commented-out gem counts as the mcp gem",
                 'MCP_GEM = re.compile(r"""^\\s*gem\\s+["\']mcp["\']""", re.M)',
                 'MCP_GEM = re.compile(r"""gem\\s+["\']mcp["\']""", re.M)',
                 "a commented-out mcp gem is n/a"),
        Mutation("a unit spec counts as end to end",
                 "    if not (rel.startswith(REQUEST_DIRS) or REQUEST_TYPE.search(text)):",
                 "    if False:",
                 "a unit spec (spec/models, no request type) is a finding"),
        Mutation("reaching one method is enough",
                 "        findings.append(f\"{rel} never reaches `{method}`",
                 "        break\n        findings.append(f\"{rel} never reaches `{method}`",
                 "a spec that never calls a tool is a finding"),
        Mutation("support helpers are not read, so the reference shape (a tools/call helper) is refused",
                 "    for f in sorted((root / \"spec\" / \"support\").rglob(\"*.rb\"))",
                 "    for f in []",
                 "CONTROL: the reference shape (Retask's) is clean"),
        Mutation("any helper counts, whether or not it sends the method",
                 "                if method in text[start:end]:",
                 "                if True:",
                 "a helper that does not send tools/call does not count"),
        Mutation("a declared spec that does not exist passes",
                 "    if not spec.is_file():\n        return 1,",
                 "    if not spec.is_file():\n        return 0,",
                 "a declared spec that does not exist is a finding"),
    ),
)
