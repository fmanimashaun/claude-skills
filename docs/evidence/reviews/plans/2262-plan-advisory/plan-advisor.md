Plan: https://github.com/fmanimashaun/claude-skills/issues/2262#issuecomment-6319462454
Plan-SHA256: n/a. This repository has no `docs/product/acceptance/` plan files for #2262 (finding A-3, #2269), so this record was not started by `advisory_scope.py --begin`. It is the dogfood pass, recorded by hand in the record's shape.
Categories: structure, breadth
Run: by the coordinator (claude-skills-a2) from `plugins/rails-flow/agents/plan-advisor.md` at fa05067d0cfd313b6077f747d0c6df4b7f2bcf09
Source: https://github.com/fmanimashaun/claude-skills/pull/2267#issuecomment-6320409722 and https://github.com/fmanimashaun/claude-skills/pull/2267#issuecomment-6320605170 (the rejected-alternatives and claims-to-verify sections, verbatim)

Findings:
- A-1 the gate proves the advisory was recorded before the TURN ended, not before the BUILD: `stop-gate.sh` is a Stop hook, and "before Phase 2" is prose only -- fix: a PreToolUse tripwire shaped like guard-migrate
- A-2 on Retask's 53 acceptance units the trigger fires on 31 (58%): security 27, breadth 16; security fires on nouns ("phone number", "API keys", "CSV", "html_safe") -- fix: security only on a boundary a threat model confirms; re-measure the composite on plan files
- A-3 this repo's maintainer flow (`/maintainer-work`) has no plan step, and `applies_when` makes the check n/a here, so #2220 and #2178 (the motivating cases) sit outside enforcement
- A-4 the slice advisory is prose: nothing hooks `gh issue create`; the gh shim is the natural place (#2268)
- A-5 `--begin` overwrites an existing record and snapshot, so a RETHINK can be erased with no trace -- fix: refuse unless `--again`, keeping the old record
- A-6 `applies_when` lists only `docs/product/acceptance`, so pre-layout `docs/acceptance/` projects are n/a to the sweep
Rejected alternatives:
- Bind the record to HEAD as `risky_diff` does -- worse: a plan exists before any commit; the content hash with a reviewed snapshot is the right key.
- Re-run Fable on every plan edit -- worse: the 30% rule compares every stamp to the ORIGINAL snapshot (advisory_scope.py:306), so there is no ratchet drift and the rule is safe to keep.
- RETHINK as a non-blocking exit 3 (plan section 3) -- worse: the coordinator's ruling (block until PROCEED or a named override whose issue `gh` can read) is stronger and is what the build does (judge_record:236-241).
- Per-stack `advisory.boundary_*` descriptor rows (plan section 2) -- the build dropped them and reuses `security_scope`'s rows; one home per concern, better.

Claims to verify:
- [Verified] stop-gate is a Stop hook; guard-migrate is PreToolUse Write -- `plugins/rails-flow/hooks/hooks.json`.
- [Verified] 31/53 Retask plans fire, security 27, breadth 16 -- the PR's `categories()` run read-only over `docs/product/acceptance/*.md` with Retask as `--root`; re-take at the arm.
- [Verified] the re-stamp share is measured against the reviewed snapshot, not the last stamp -- advisory_scope.py:306-307.
- [Verified] this repo runs no rails-flow hooks and has no `docs/product` -- `.claude/settings.json`; `ls docs/product`.
- [Inferred] the PR-list breadth rate (30%) and the plan-file breadth rate (16/53) agreeing is coincidence; PR file lists are still the wrong population for a trigger that reads backticked plan paths (47 of 53 Retask units have one plan file, 6 a handoff).
- [Verified] no `advisory.*` descriptor rows exist at the PR head -- `git grep advisory refs/review/2267 -- plugins/*/stacks.json`: none; the plan promised them and the PR body does not say they were dropped.
VERDICT: PROCEED

Disposition A-1: accepted | `plugins/rails-flow/hooks/scripts/guard-plan.sh` refuses a Write or Edit outside docs/ on a flow branch while the advisory is owed; four check_hook_gates fixtures and a guard
Disposition A-2: accepted | security fires only when the unit's threat model has threat rows; re-measured on Retask's 53 plans at 415ccc352, the composite fires on 16 (30%): breadth 16, dependency 1, data-model 1, structure 1, security 0
Disposition A-3: deferred | a plan step for maintainer-work is filed as #2269
Disposition A-4: deferred | the gh-shim enforcement of the slice advisory is filed as #2270, after #2268
Disposition A-5: accepted | `--begin` refuses over an existing record; `--again` keeps it as plan-advisor.<n>.md with its snapshot
Disposition A-6: accepted, adapted | applies_when is `docs`, not both criteria homes: project_gates requires EVERY listed path to exist (project_gates.py:300), so listing the two alternatives would make the check n/a almost everywhere
