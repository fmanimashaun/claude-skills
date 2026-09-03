"""Mutation guard: inventory_data. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #892. The wiki's Agents-And-Gates page renders whatever this module returns, so a reader that goes quiet
# produces a page that LOOKS complete. Each mutation silences one refusal.
GUARD = Guard(
    name="inventory_data",
    subject="scripts/inventory_data.py",
    selftest="scripts/inventory_data.py",   # --selftest lives in the module itself
    needs=(".claude-plugin", "plugins", ".claude", "scripts", "evals"),   # GATES names evals/selftest.py; verify_gate_scripts must find it
    mutations=(
        Mutation(
            "an agent file with no `name:` is skipped instead of refused, so an agent vanishes from the page with no error",
            '    if nameless:\n        raise ArtifactError(',
            '    if False:\n        raise ArtifactError(',
            "an agent file with no `name:` is REFUSED",
        ),
        Mutation(
            "a tier row naming no agent is accepted, so a stale row renders as a shipped agent",
            '            if (plugin, tier_row.agent) not in known:',
            '            if False:',
            "a tier row naming no agent is refused",
        ),
        Mutation(
            "a gate whose script does not exist is listed, stating coverage that does not exist",
            '        for gate in gates if not (REPO / gate["script"]).exists()',
            '        for gate in gates if False',
            "a gate naming a script that does not exist is refused",
        ),
        Mutation(
            "the manifest cross-check never fails, so a plugin the marketplace does not install is inventoried as shipped",
            '    if walked == declared:',
            '    if True:',
            "FAILS when a directory the manifest does not install is walked",
        ),
        Mutation(
            "a mention inside a longer token counts as naming the agent",
            '    return bool(re.search(rf"(?<![\\w-]){re.escape(agent)}(?![\\w-])", body))',
            '    return agent in body',
            "a longer token does not",
        ),
    ),
)
