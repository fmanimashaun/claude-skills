# qa-flow audit: agents, commands, hooks (2026-10-12)

`/maintainer-audit` on `plugins/qa-flow` at `origin/dev` (export, nothing run in a user project). Scope: the 11 agents, the 8 commands, `hooks/hooks.json` with `release-gate.sh`, `qa-status.sh` and their `lib/`, and the scripts they name. Method: claims against enforcement (what each "never / only / refuses" sentence is backed by) and consistency of the pieces with each other. No open `comp:qa-flow` issue existed at the start.

## Findings, filed (not fixed in place)

| # | finding | issue | prio |
|---|---|---|---|
| 1 | The release gate does not answer a ~500 KB command that contains a push to main: 390 KB takes 8.2 s, 683 KB gives no answer in 70 s, and with a 3 s deadline the 390 KB case also gives none (the deadline fallback is slower than the main path). The harness kills the hook at 15 s and the command runs. | #1952 | P2 |
| 2 | "NEVER production" for k6 load and ZAP (`perf-tester.md`, `security-scanner.md`, `certify.md`) is prose only; the robot's local-target guard exists, the load/DAST path has none. | #1954 | P2 |
| 3 | `qa-status.sh` says "cleared for main" on a weaker condition (sha and verdict) than the release gate (the release-only evidence too). | #1955 | P3 |
| 4 | `scaffold_ts_tests.py`, the runner that decides pass or fail for the robot's TypeScript helper tests and the selftest of six scaffold guards, has no mutation guard of its own (found in review of this record). | #1979 | P3 |

Outcomes (2026-10-13): finding 1 is fixed in #1965 (merged) with notes in the follow-up; finding 3 is in flight as #1977; findings 2 and 4 are open. Two more came out of the same-class timing below, both filed by reviewers: `guard-worktree.sh` with python3 missing is quadratic (#1978, P3), and `guard-worktree.sh` and `guard-pr-ready.sh` are quadratic on plain lines with python3 present (#1980, P2).

## Checked and held (the evidence the plugin is consistent)

| area | check | result |
|---|---|---|
| agents | frontmatter `name` equals the file name; a `description` on all 11; `tools` lines parse (functional-tester inherits all tools, as its description says) | held |
| commands | every `${CLAUDE_PLUGIN_ROOT}/scripts/…` and `plugins/qa-flow/scripts/…` path named in the 8 commands, 11 agents and 2 references exists | held |
| commands and agents | every `qa-flow:<name>` reference resolves to an agent or command (the three hits, `qa-flow:begin`, `qa-flow:end`, `qa-flow:tiers`, are managed-section markers, not references) | held |
| config | every `qa.config.yml` key the docs cite appears in what `setup-qa.md` writes | held |
| scripts | every `plugins/qa-flow/scripts/*.py` has a `--selftest` (measured). A mutation guard whose SUBJECT is the script exists for all but three: `findings.py` and `fixture_git.py` are lint-compared copies (`findings_script_copies`, `fixture_git_copies`) and have none of their own, and `scaffold_ts_tests.py` is the selftest runner of six scaffold guards but nothing mutates it (finding 4, #1979). The first pass of this audit counted a script as guarded when any guard named it, which is how the row first read "held". | held for the selftests; two copies and one runner without a guard of their own |
| hooks.json | PreToolUse[Bash] runs `/bin/bash -p release-gate.sh` (timeout 15) and SessionStart runs `qa-status.sh` (timeout 10); both under `/bin/bash -p` after `trusted-env.sh` (#1850) | held |
| qa-status.sh | advisory and fail-open (no repo, no python3, no stamp: exit 0), one reader for the stamp, text depends only on state (no ticking value, #1886) | held, except finding 3 |
| release-gate.sh | `git push origin main` with no stamp: exit 2 in 0.3 s; the same with 100, 1,000, 3,000, 6,000, 12,000, 20,000 and 40,000 trailing lines: exit 2 | held up to 390 KB; finding 1 beyond |
| rails-flow hooks, same class (follow-up, 2026-10-12 and 13) | the hooks that take a command, timed under bash 3.2 on an idle machine, **by the shape of the input**, because the shape decides. Plain lines with NO trigger word (`echo start`, then N lines of `echo xxxx`), python3 present, at 25 / 50 / 100 / 150 KB: `guard-bash.sh` 0.3 / 0.4 / 0.7 / 1.0 s and `guard-claims.sh` 0.1 / 0.1 / 0.2 / 0.2 s (linear); **`guard-worktree.sh` 2.7 / 9.7 / over 25 / over 25 s and `guard-pr-ready.sh` 2.4 / 9.5 / over 25 / over 25 s (quadratic)**. A reviewer measured the same two on an `origin/dev` export at 0.6-0.7 / 2.1 / 7.0-7.9 / 16.2-16.9 s; the order and the shape agree, the constants differ by machine. Past about 60 KB of plain lines both pass their 15 s timeout, and both carry `onFailure: "block"` since #1968, so such a command is now DENIED (filed by the reviewer as #1980, P2). The same two hooks with the trigger word on the first line (`git worktree add ...`, `gh pr ready 5`), or with comment lines instead of plain lines, stay under 2 s at 150 KB (the first pass of this audit timed that shape and so missed it). With python3 missing: `guard-worktree.sh` is quadratic as well (2.6 / 22.3 / 23.6 s at 50 / 100 / 150 KB, #1978); `guard-bash.sh`, `guard-claims.sh` and `guard-pr-ready.sh` stay under 0.5 s; `guard-migrate.sh` and `guard-lane.sh` take file paths, not commands, and were timed with a 50 KB `content` only. `guard-bash.sh` with a hung awk and a 1 s deadline answers in 1.1 s at every size. | NOT held: `guard-worktree.sh` and `guard-pr-ready.sh` are quadratic on plain lines (#1980), and `guard-worktree.sh` with python3 missing (#1978); the other hooks are linear on the shapes above |
| release-gate.sh | the existing fixtures for the cases the recent issues named (#1764, #1768, #1770, #1781, #1803, #1875) were not re-run here | not checked |

## Not covered

The `scaffold/` TypeScript support files, the Playwright/Cypress/Selenium adaptations, the content of each agent's testing doctrine against its upstream tools (k6, ZAP, axe), and `release-gate.sh`'s foreign-repository judgement beyond the probes above. The doctrine claims about third-party tools would need `doctrine-verifier` per claim; none was edited or verified in this audit.
