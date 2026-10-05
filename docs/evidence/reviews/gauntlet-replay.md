# Gauntlet replay — did the agents catch what reviewers caught? (#1563)

Measured 2026-10-03. Each replay checks out the commit a reviewer tested with the defect present, gives
an agent the diff against its base, and withholds the fix. **Result: 2 of 3 caught, one only after a
change to the agent made after seeing the first miss.** The issue asked for 3 of 3; this is what was
measured.

## Method

- **Blind.** Each agent worked in a detached worktree at the pre-fix commit and was forbidden `gh`, any
  other ref, and the main checkout (which contains the fixes).
- **Leave-one-out catalogue.** The agent read `blocked-catalogue.md` with the rows and the replay entry
  for the PR under test removed. Other PRs' rows stayed, so a later PR in the same class is informed by
  the earlier ones, as it would be in practice. (#1519's number still appears once, in a prose line that
  says it fixed a dev regression and carries no defect.)
- **Deterministic check first.** The reproducer was fed to that commit's real `guard-bash.sh`:

| PR | reproducer | pre-fix exit | fix exit | control `git add -A` |
|---|---|---|---|---|
| 1498 | `e'v'al "git add -A"` | 0 | 2 | 2 on both |
| 1519 | `bash -c 'x<LF><STX><LF>y'; bash -c 'git add -A'` | 0 | 2 | 2 on both |

  Exit 2 means refused. A reproducer that passes before and is refused after, with a control refused on
  both, shows the defect is real and the harness is not simply refusing everything. For #1498 the base
  `f6fa24108` also refuses it, so the diff introduced the regression.

## Result

| PR | agent | verdict | caught the reviewer's defect? |
|---|---|---|---|
| 1498 | `shell-adversary` | BLOCKED, 5 inputs through | **Yes.** It named the raw-text pre-filter that runs before dequoting (`normalize_cmd.sh:294`), found four more spellings of the same cause, and showed the filter was the cause by removing it in a copy. It also noted that no mutation guard covers that pre-filter. |
| 1519, run 1 | `shell-adversary` | BLOCKED, 2 findings | **No.** Both findings exit 0 at the base too (a fallback with only bash and cat on PATH; a depth cap of 3). It tried "a `\002` byte in input" but not the byte inside a quoted string between two commands, which is the defect. |
| 1519, run 2 | `shell-adversary` | BLOCKED, 2 findings | **Yes, after a change.** Run 2 followed new Method step 5 (attack every delimiter the diff introduces, inside quotes, inside heredocs and between commands), which was written after run 1 missed. It found five regressions that exit 0 at HEAD and 2 at base. This is tuning on the test case, so treat 1519 as one catch in two tries, not a clean pass. |
| 1511 | `mutation-verifier` | CLEAN | **No, and an agent cannot.** It ran the guard (41 mutations caught) and the selftest (89 checks) and saw no leftover process. The defect is a fixture that starts a detached `git maintenance`; the race is intermittent and no mutation run sees it. Filed as [#1577](https://github.com/fmanimashaun/claude-skills/issues/1577), a lint, which is the deterministic tool for this class. |

## What this means for how the gauntlet is used

- `shell-adversary` is worth running on any diff that parses a shell command: it caught both parser
  regressions, and found pre-existing holes on the way (reported separately, not blamed on the diff).
- `mutation-verifier` answers "can the checks fail", not "is the fixture hermetic". Do not read its
  CLEAN as covering a fixture race.
- A model-run replay is one sample. It does not prove the next defect of the class is found. The
  permanent protection is the fixture each merged class already has (`check_blocked_catalogue.py`
  refuses one that disappears); the agents are a cheaper way to find the next one earlier.

## Model, and what changed since (review of #1578, S2)

- **Model: not recorded when the replay ran.** [Inferred] The agents pin `sonnet` (`shell-adversary`) and `haiku`
  (`mutation-verifier`) in their frontmatter, which is what a run of the agent as written uses. `haiku` for
  `mutation-verifier` is inside `model-tiers.md`'s mechanical tier (a deterministic harness result).
- **`mutation-verifier`'s guard lookup was wrong when the 1511 replay ran.** It found a guard by file name, which
  finds none for a hook script (review B2). Step 2 is now `python3 scripts/gauntlet_core.py guards`, which reads
  the harness's registry, and the replay was not re-run: its one run was on a Python script, where the old lookup
  worked.
