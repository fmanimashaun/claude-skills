# STATUS

_Updated: 2026-10-22 · sha 30cf621c (dev, `git rev-parse origin/dev`) · main e7073b5e (`git rev-parse origin/main`)_

**Phase:** arming v1.159.0. `[reported]` by the coordinator: the arm is blocked only on PR #2291. `[observed]`
`gh pr view 2291 --json state` → OPEN, base dev. No `chore/arm-v1.159.0` PR is open yet (`gh pr list --state open --limit 50`).

**Live measurements** (each number names the command that produced it, run 2026-10-22):

| what | value | command |
|---|---|---|
| open issues | 83 | `gh issue list --state open --limit 200 --json number -q 'length'` (83 is under the 200 cap, so the list is complete) |
| open `prio:P1` issues | 14 | `gh issue list --state open --limit 200 --label prio:P1 --json number -q 'length'` |
| open PRs | 5 (#2294, #2293, #2291, #2282, #2160) | `gh pr list --state open --limit 50` |
| latest release | v1.158.0, 2026-10-21 | `gh release list --limit 3` (next: v1.157.6, 2026-10-17) |
| dev vs main | 398 files, +7740 / −29824 | `git diff --stat origin/dev origin/main \| tail -1` (non-empty: dev is not promoted) |
| self-consistency lint | exit 0, no findings | `python3 scripts/lint_self_consistency.py` |

The 14 open P1 issues: #2297, #2296, #2295, #2280, #2279, #2278, #2277, #2273, #2264, #2225, #2223, #2205, #2186, #2143
(`gh issue list --state open --limit 200 --label prio:P1 --json number`).

**Shipped since the last STATUS (2026-09-27):** v1.151.0 → v1.158.0 on `main`. `[observed]` (`gh release list --limit 3`).
Merges that changed how the repo is run: #2234 (the full sweep runs on GitHub, because the repo is public) and #2290 (vendor
CLI steps handed off to the vendor plugins; `scripts/check_vendor_handoff.py` refuses a copy). `[observed]` (`gh pr view <n> --json state,mergedAt`).

**Now:** arm v1.159.0. Merge PR #2291 (toolchain audit, #2168), then open the arm PR `chore/arm-v1.159.0` → dev. `[reported]`

**Next:** the open P2 and P3 issues. Two open rulings have no enforcement yet: #2288 (toolchain-check installs and logs in autonomously, D-016)
and #2296 (worktree teardown leaves files behind, D-018).

**Blockers:** PR #2291 review and merge. `[reported]`
