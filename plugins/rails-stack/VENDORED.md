# Vendored copies in rails-stack

The Rails agents (#2173) and the Rails project gates (#2175) moved here from rails-flow. A plugin can reach only its own files (`${CLAUDE_PLUGIN_ROOT}`); there is no path into a sibling plugin. So the files the agents and the gates run, import or cite are copied here, byte-identical to their canonical copy in rails-flow. `scripts/lint_self_consistency.py` (`findings-script-drift`, `vendored-copy-drift`, `fixture-git-drift`) fails if a copy drifts or goes missing. Edit the canonical file, then copy it over.

Every copy but `fixture_git.py` is temporary. Each row names what removes it, or why nothing does.

| copy here | canonical | used by | removed when |
|---|---|---|---|
| `scripts/findings.py` | `plugins/rails-flow/scripts/findings.py` | `code-reviewer` | the neutral references move to core-skills (#2186) |
| `reference/agent-output-contract.md` | `plugins/rails-flow/reference/agent-output-contract.md` | every agent here | the neutral references move to core-skills (#2186) |
| `scripts/build_project_wiki.py` | `plugins/rails-flow/scripts/build_project_wiki.py` | `check_privacy_inventory.py` (imports its schema reader) | the Rails documentation generators move here (#2177) and this becomes the original |
| `scripts/session_coordinator.py` | `plugins/rails-flow/scripts/session_coordinator.py` | `check_migration_order.py` (imports `migration_findings`) | the coordinator asks the descriptor for the stack's migration rule (#2183) |
| `scripts/fixture_git.py` | `plugins/rails-flow/scripts/fixture_git.py` | `check_migration_order.py`'s selftest | never: one fixture-git lock ships once per plugin that runs fixture git (#1588, `fixture-git-drift`) |
| `scripts/triage_failures.py` | `plugins/rails-flow/scripts/triage_failures.py` | `test-runner` | the flows' triage reads the descriptor and rails-stack owns the original (#2183) |
