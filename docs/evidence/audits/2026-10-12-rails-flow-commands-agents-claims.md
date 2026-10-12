# Audit: rails-flow commands and agents, claims against enforcement (2026-10-12)

Auditor: fd / claude-skills-e9, assigned by coordinator claude-skills-24. Tree: `origin/dev` on 2026-10-12. Scope: `plugins/rails-flow/commands/*.md` (24) and `plugins/rails-flow/agents/*.md` (13).

## Method and results

| Check | How | Result |
|---|---|---|
| Every script a command or agent names exists | grep of every `*.py` reference in the 37 files, resolved under `plugins/*/scripts`, `plugins/*/hooks/scripts/lib` and `scripts/` | 27 scripts named; all exist |
| Every flag passed to a named script is one it accepts | each `script.py … --flag` pair extracted (52 pairs), then matched as a whole flag against that script's real `--help` output | 52 of 52 accepted; 0 misses |
| Guarantee sentences that name a mechanism | read the claim, then the code it names | all held (below) |
| The repository's mechanical claims linter | `python3 scripts/lint_self_consistency.py` | no findings |

## Guarantees checked and held

- `commands/setup-flow.md:913-915`: guard-bash refuses a `gh issue create` missing a declared label group. Held by `hooks/scripts/guard-bash.sh:402-446`, which calls `issue_labels.py`.
- `commands/drive.md:46`: `next_action.py` does not proceed past a stop from `breaker.py`. Held.
- `commands/slice.md:100`: `check_slices.py:230-233` refuses a slice whose blocker is not yet filed. Held.
- `agents/claude-skills-reporter.md:98`: `check_issue_mockup.py` refuses an issue with no Mock-up section. Held.
- `commands/fix.md:131,146`: the exit codes named for `check_mockup_gate.py` and `classify_door.py` match the scripts. Held.
- `agents/claim-verifier.md`: its guarantee-shaped wording is examples of claims to check, not guarantees.

## Not covered (stated, not implied clean)

- **Unanchored guarantees:** "never" and "always" sentences that name no script, hook or gate were not traced line by line. A full read is still owed before calling these 37 files clean: #1948.
- **Agent obedience:** whether each agent's tool list allows what its body says it does.

## Findings

None confirmed. The read-only pass ran in a subagent, and its 0 dropped candidates means it found none it could not confirm, not that it read every sentence. Report: `_logs/audit-railsflow-claims.md`, outside the repository.
