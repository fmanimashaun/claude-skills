# qa-flow audit: agents, commands, hooks (2026-10-12)

`/maintainer-audit` on `plugins/qa-flow` at `origin/dev` (export, nothing run in a user project). Scope: the 11 agents, the 8 commands, `hooks/hooks.json` with `release-gate.sh`, `qa-status.sh` and their `lib/`, and the scripts they name. Method: claims against enforcement (what each "never / only / refuses" sentence is backed by) and consistency of the pieces with each other. No open `comp:qa-flow` issue existed at the start.

## Findings, filed (not fixed in place)

| # | finding | issue | prio |
|---|---|---|---|
| 1 | The release gate does not answer a ~500 KB command that contains a push to main: 390 KB takes 8.2 s, 683 KB gives no answer in 70 s, and with a 3 s deadline the 390 KB case also gives none (the deadline fallback is slower than the main path). The harness kills the hook at 15 s and the command runs. | #1952 | P2 |
| 2 | "NEVER production" for k6 load and ZAP (`perf-tester.md`, `security-scanner.md`, `certify.md`) is prose only; the robot's local-target guard exists, the load/DAST path has none. | #1954 | P2 |
| 3 | `qa-status.sh` says "cleared for main" on a weaker condition (sha and verdict) than the release gate (the release-only evidence too). | #1955 | P3 |
| 4 | `scaffold_ts_tests.py`, the runner that decides pass or fail for the robot's TypeScript helper tests and the selftest of six scaffold guards, has no mutation guard of its own (found in review of this record). | #1979 | P3 |

Outcomes (2026-10-13): finding 1 is fixed in #1965 (merged) with notes in the follow-up; finding 3 is in flight as #1977; findings 2 and 4 are open. A fifth item came out of the same-class timing below: `guard-worktree.sh` with python3 missing is quadratic (#1978, filed by a reviewer, P3).

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
| rails-flow hooks, same class (follow-up, 2026-10-12 and 13) | the degraded fallback of the hooks that take a command, timed under bash 3.2, normal and with python3 missing: `guard-bash.sh`, `guard-claims.sh`, `guard-pr-ready.sh`, `guard-migrate.sh` and `guard-lane.sh` stay under 1 s up to 150 KB (`guard-claims.sh` and `guard-pr-ready.sh` re-timed at 100 and 150 KB), and `guard-bash.sh` with a hung awk and a 1 s deadline answers in 1.1 s at every size. **`guard-worktree.sh` with python3 missing is quadratic**: 2.2 s at 50 KB, 8.8 s at 100 KB and 20.4 s at 150 KB, past its 15 s timeout at about 130 KB (found by a reviewer; #1978, P3). | held to 50 KB; guard-worktree.sh no-python3 is quadratic, #1978 |
| release-gate.sh | the existing fixtures for the cases the recent issues named (#1764, #1768, #1770, #1781, #1803, #1875) were not re-run here | not checked |

## Not covered

The `scaffold/` TypeScript support files, the Playwright/Cypress/Selenium adaptations, the content of each agent's testing doctrine against its upstream tools (k6, ZAP, axe), and `release-gate.sh`'s foreign-repository judgement beyond the probes above. The doctrine claims about third-party tools would need `doctrine-verifier` per claim; none was edited or verified in this audit.
