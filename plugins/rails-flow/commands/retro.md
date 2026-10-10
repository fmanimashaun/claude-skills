---
description: Count the review findings that recur across PRs and propose a check or a doctrine line for each — a report in docs/brain/retro/, nothing else changed
argument-hint: "[--since YYYY-MM-DD] [--until YYYY-MM-DD] [--min-prs N]"
---

# /rails-flow:retro — $ARGUMENTS

A review comment you write twice should have been a check. This reads the findings records the review agents already write and
says which ones recur, in how many PRs, and which kind of fix each deserves. It changes **nothing** except one report file.

## What it reads

`docs/evidence/reviews/**/*findings.jsonl`: the per-PR reviewers (`code-reviewer`, `pr-reviewer`, `spec-reviewer`) write
`docs/evidence/reviews/prs/<branch-slug>/<agent>-findings.jsonl`, and `/rails-flow:review` writes a dated
`docs/evidence/reviews/<date>/findings.jsonl`. A **source** is a PR directory or a dated review: a group recurs when its records come from
`--min-prs` (default 3) or more sources, not when it has many records, because five findings in one review are one review's thoroughness,
not a habit.

**Not read in this version:** PR review comments (`gh`) and session transcripts. If a project's reviews are not written as findings records,
the report has nothing to count and says so.

## Run it

Pass through only the flags the user gave (`--since`, `--until`, `--min-prs`). First look, nothing written:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/retro.py" --stdout
```

Then write the report (`docs/brain/retro/<today>.md`; `--out` picks another path):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/retro.py"
```

With `--since` or `--until` it runs `git log -1 --format=%cs` (read-only) on each PR file to date it. `--out` is refused when it is under the
findings directory, ends in `findings.jsonl`, or names an existing file that is not a previous retro report: it never overwrites a finding.

Exit 2 means there was **nothing to read** (no findings files, or none with a usable record): say so. It is not "nothing recurs", and you
must not report it as clean.

## Read the report, do not just forward it

- **Severity** is mapped to high, medium and low, and every raw spelling it mapped is listed (real records use P1 to P3, blocker/major/minor,
  BLOCKING/SUGGESTION and more). A spelling it does not know, or a state like `resolved`, is `unmapped`: it is listed, never guessed.
- **Categories** are grouped by their spelling with a severity word stripped from the edge (`blocking`, `blocker`, `suggestion`, `advisory`,
  `p1` to `p3`, with or without parentheses) and the case folded, so `claims-vs-enforcement (BLOCKING)` joins `claims-vs-enforcement`. Ordinary
  words such as `info` or `minor` are not stripped. **Every** category whose key differs from the spelling it was written in is listed, merged
  or alone, so nothing is renamed out of sight. Records without a category are counted and never proposed on.
- A **signature** counts per category: the same label in two categories is two defects, not a repeat.
- **mechanical candidate**: a signature that recurs in 2 or more sources, or a file pattern (two directories and a suffix) that 60% of the
  group's records share across the threshold's sources. This is a **heuristic for a person to judge**, not a verdict: a signature is the
  reviewer's own label and can coincide (a numbered criterion in different PRs), which is why the report prints the issue text beside it.
  The proposal is a deterministic check, in order of preference: a rubocop cop, a repo lint, a spec helper, a hook.
- **judgement**: no shared pattern. The proposal is a line in the project's review doctrine, not a check.
- "**Nothing recurs**" and "**Nothing mechanical recurs**" are results, said plainly. Do not invent a proposal to fill the page.

## Then

Show the user the recurring groups and each proposal with the findings behind it. For each proposal the user **accepts**, file one issue
(the project's issue flow, with its labels) citing the report and the findings; do not build the check in this command. Commit the report
only if the user asks. Change nothing else.
