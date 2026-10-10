# Blocked-PR catalogue — what independent reviewers refused, and what now stops it

Decision record for [#1563](https://github.com/fmanimashaun/claude-skills/issues/1563) (the pre-review
gauntlet). Source: `gh pr view <n> --json comments` over 16 candidate hook, guard and mutation PRs,
read 2026-10-03. **Reviewers write `BLOCKED` as PR comments; none of the 9 PRs checked (1498, 1529, 1470, 1511,
1525, 1491, 1519, 1513, 1516) has a GitHub review object**, which is why `docs/evidence/reviews/prs/` has none. 14 PRs carry a real BLOCK. #1452 was CLEAN and #1479's
block is history from before its branch was reset.

`python3 scripts/check_blocked_catalogue.py` re-checks this table: every row whose state is `merged`
must name a fixture on `dev` (`path :: literal`) that still contains that literal, and every row
without one must say why in the `advisory` column. A catalogue whose fixtures have gone is a list of
sentences, not a defence.

## Classes with a fixture on `dev`

| class | PR | state | defect (the mechanism) | fixture |
|---|---|---|---|---|
| obfuscation-fail-open | 1498 | merged | A raw-text pre-check skips the lexer, but the lexer dequotes, so `e'v'al "git add -A"` passes | `plugins/rails-flow/scripts/check_hook_gates.py :: e'v'al` |
| heredoc-quoting | 1498 | merged | A heredoc inside `$( )` containing `)` ends the substitution early and hides the next command | `plugins/rails-flow/scripts/check_hook_gates.py :: Adds :) emoji then` |
| fallback-lacks-its-tools | 1529 | merged | The fail-closed fallback needed grep, awk or python3; with none on PATH it exits 0 | `plugins/rails-flow/scripts/check_hook_gates.py :: hit() failed on every rule` |
| push-parser-fail-open | 1470 | merged | The release-gate push parser allowed `$(echo main)`, `main>/dev/null`, `HEAD:heads/main`, `{main,dev}` | `plugins/qa-flow/scripts/push_targets.py :: git push origin $(echo main)` |
| control-char-laundering | 1437 | merged | A newline in an evidence path smuggled a second path past a line-split gate | `plugins/rails-flow/scripts/check_hook_gates.py :: a newline in an evidence path launders nothing` |
| fixture-background-race | 1511 | merged | A selftest control commit started a detached `git maintenance` in the fixture repo | `scripts/mutations/mutation_check_harness.py :: #1510: the baseline and the mutant must run with git maintenance off` |
| timeout-process-leak | 1525 | merged | A process-group kill missed mutants that had started their own session | `scripts/mutations/check_hook_gates_harness.py :: os.killpg(proc.pid` |
| timeout-budget | 1491 | merged | A baseline timeout equalled the gate's whole budget, so a hung guard was killed unnamed | `scripts/mutations/mutation_check_harness.py :: timeout=BASELINE_TIMEOUT` |

## Classes whose fix is on an open PR (no fixture on `dev` yet)

| class | PR | state | defect (the mechanism) | owner |
|---|---|---|---|---|
| batch-split-fail-open | 1519 | open | A `\002` line inside a command splits the raw text mid-string, so `bash -c 'x<LF><STX><LF>y'; bash -c 'git add -A'` exits 0 | PR 1519 |
| redirection-regression | 1513 | open | `cd sub &>/dev/null; bash < only.sh`: `&>` folded to `>` makes `cd` three words, so the verdict is "unknown" and allowed | PR 1513 |
| wrong-repo-verdict | 1516 | open | guard-claims judged the template of the directory it ran in, six rounds of `cd`, wrappers and `GIT_DIR` | PR 1516 |

## Advisory: reviewed by a person, no mechanical fixture

| class | PR | state | defect (the mechanism) | advisory |
|---|---|---|---|---|
| over-refusal | 1522 | open | A version rule refused a legitimate state (39 of 77 releases have no such block) | judgement; the fixing PR owns its fixture |
| over-refusal | 1478 | merged | An indented fence turned a gate off; an allow-list refused `.gif` and `.avif` | judgement, covered by that gate's own selftest |
| unverified-claim | 1502 | merged | A count in an upstream review was wrong (116 + 16 against 15) | a claim, verified by `claim-verifier`, not a fixture |
| numeric-claim | 1485 | merged | Power and Monte-Carlo figures; the reviewed head is not in the PR's commit list, so unverified | not a hook or guard class |

## Classes the issue names that no review blocked on

Nothing in the 14 blocks is a quadratic loop (#1519 fixed a dev regression, nobody blocked on it), a
mutation-check grep that misses singular output, or an ungated `gh pr ready`. They came from a
model-written usage report, not from our reviews, so they have no row here and no agent. `gh pr ready`
is now gated (#1565): `guard-pr-ready.sh` refuses it without a green sweep record for HEAD.

## Replay set

Each is a commit a reviewer tested with the defect present, and the commit that fixed it. Diff sizes
measured with `git diff --shortstat <pre-fix> <fix>`.
What the agents did on these is in `gauntlet-replay.md`: 2 of 3 caught.

| PR | pre-fix | fix | diff | reproducer |
|---|---|---|---|---|
| 1498 | `1345e5780` | `56d4d1654` | +64/-17 | `e'v'al "git add -A"` exits 0 |
| 1519 | `9c2dfcda2` | `662d833f0` | +38/-14 | `bash -c 'x<LF><STX><LF>y'; bash -c 'git add -A'` exits 0 |
| 1511 | `7c356b3f2` | `364be8829` | +21/-11 | the control commit starts a detached `git maintenance` |
