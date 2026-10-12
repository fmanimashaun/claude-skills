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

## Addendum: the remaining half (#1948), same day

**Guarantees with no named mechanism.**
- A sentence filter over the 37 files (outside code blocks) found 323 sentences with guarantee words and no named mechanism.
- Dropping instructions to the model (sentences starting "Never", "Always", "Do not", "Must") and pure explanation left 28 sentences that assert how the SYSTEM behaves.
- Each was read in context, and the mechanism its paragraph names was read in code. Where it was cheap, the mechanism's selftest or a probe was run:
  - selftests: `check_spec_review`, `session_coordinator` (16 write verbs refused), `escalation_selftest` (38), `retro`, `claude_md_structure`, `check_slices`, `check_spec`, `toolchain_version_selftest` (51), `wrap_round`, `check_handoff_selftest` (112), `check_memory_systems` (21), `check_mandated_gems` (22), `check_tenancy_cop` (47), `check_coverage_ratchet` (14);
  - probes: guard-bash in a scratch repo blocks `bin/rails db:reset` (exit 2) and an unlabelled `gh issue create` (exit 2), and passes a labelled one (exit 0).
- **Result:** 26 HELD, 2 ADVICE, 0 broken, 0 unanchored. Each claim's file:line evidence is in the working notes.
- **The two ADVICE items** are rules the model follows, with no script behind them; neither claims a mechanism:
  - `commands/report.md:15`: the reporter refuses an observation about your own app;
  - `commands/toolchain-audit.md:129`: "not installed is reported as not installed".
- **One HELD with an outside dependency:** `commands/setup-flow.md:1015`, the coverage floor that is "never red on day one, cannot slide, rises by itself". That behaviour is SimpleCov's `refuse_coverage_drop`. doctrine-verifier read SimpleCov's source at v0.22.0, v1.0.0 and v1.3.2 and CONFIRMED it:
  - with no baseline, the check passes (`coverage_violations.rb` `return [] unless baseline`);
  - any drop fails the run (`MaximumCoverageDropCheck`, maximum 0);
  - `coverage/.last_run.json` is written only after a passing run (`exit_handling.rb:131` at v1.3.2), so the floor never slides.

  The same check found one defect beside it, filed as **#1957**:
  - the prescribed `minimum_coverage_by_file line: 0` has been deprecated since SimpleCov 1.0.0 and warns on every run;
  - `refuse_coverage_drop :branch` needs `enable_coverage :branch`, which the snippet omits.

**Agent tool lists against agent bodies.** All 13 agents were compared.
- Every agent told to run a command has `Bash`.
- No agent described as read-only holds `Edit` or `Write`: the reviewers, verifiers, adversary, test-runner and security-auditor hold neither.
- The one string match ("Never edit blind", `agents/rails-developer.md:20`) is about reading before editing, not a read-only claim.

**With this addendum the 37 files are audited end to end: no claims-vs-enforcement findings.**

## Findings

None confirmed. The read-only pass ran in a subagent, and its 0 dropped candidates means it found none it could not confirm, not that it read every sentence. Report: `_logs/audit-railsflow-claims.md`, outside the repository.
