# Vendored copies in rails-stack

The Rails agents moved here from rails-flow (#2173). A plugin can reach only its own files (`${CLAUDE_PLUGIN_ROOT}`); there is no path into a sibling plugin. So the files the agents run or cite are copied here, byte-identical to their canonical copy in rails-flow. `scripts/lint_self_consistency.py` (`findings-script-drift`, `vendored-copy-drift`) fails if a copy drifts or goes missing. Edit the canonical file, then copy it over.

Every copy is temporary. Each row names what removes it.

| copy here | canonical | used by | removed when |
|---|---|---|---|
| `scripts/findings.py` | `plugins/rails-flow/scripts/findings.py` | `code-reviewer` | the neutral references move to core-skills (#2186) |
| `reference/agent-output-contract.md` | `plugins/rails-flow/reference/agent-output-contract.md` | every agent here | the neutral references move to core-skills (#2186) |
| `scripts/triage_failures.py` | `plugins/rails-flow/scripts/triage_failures.py` | `test-runner` | the flows' triage reads the descriptor and rails-stack owns the original (#2183) |
| `scripts/dev_baseline.py` | `plugins/rails-flow/scripts/dev_baseline.py` | `triage_failures.py` (imports it) | with `triage_failures.py`'s copy (#2183) |
| `scripts/fixture_git.py` | `plugins/rails-flow/scripts/fixture_git.py` | `dev_baseline.py` (imports it) | with `dev_baseline.py`'s copy (#2183) |
