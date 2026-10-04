# qa-flow

Part of the claude-skills marketplace. Install:
```
/plugin marketplace add fmanimashaun/claude-skills
/plugin install qa-flow@claude-skills
```

See the repo root README.md and CHANGELOG.md for full documentation.

## Commands

One line each, from the command's own description; the command file is the authority.

- `/qa-flow:cases` — Author and maintain the in-repo test-case catalogue (qa/test-cases.csv) from the PRD, app surface, qa-lead plan, and past defects.
- `/qa-flow:certify` — Comprehensive release certification before dev->main — full regression plus release-only layers (load, DAST, cross-browser, a first-boot operator walkthrough, a forged-request authorization sweep); writes the stamp that unlocks the deploy gate.
- `/qa-flow:crawl` — Crawl every route in a browser and judge it — broken pages, dead controls, theme-only failures.
- `/qa-flow:functional` — Agentic functional/exploratory testing of a running app via Playwright MCP — menu-scoped, evidence-based, driven from test-case titles.
- `/qa-flow:setup-qa` — Set up the independent QA workspace — detects the codebase's testing signals and PROPOSES a stack (qa/qa.config.yml) you confirm/override, then scaffolds only the chosen tools, seed personas, and case catalogue.
- `/qa-flow:smoke` — Reuse a running server or launch the app (stack-aware), then confirm it actually BOOTS and its key routes respond, before any deeper QA.
- `/qa-flow:verify` — Independent QA verification after a feature merges to dev — smoke gate, sanity, and targeted regression to prove the change broke nothing previously certified.
- `/qa-flow:walkthrough` — Walk every persona's whole journey in a live browser — every page, every action, every hand-off to the next persona, at three widths — judged against the spec's intent, not a case title.

## The release gate

`release-gate.sh` blocks a promotion to `main` unless a PASS `qa/CERTIFICATION` certifies the commit that
would ship. It classifies by effect, not spelling: `git push`/`git merge`/`gh pr merge`, a `gh api` call
that merges a PR, creates a merge into main or writes a `main` ref (REST or GraphQL), and
`gh release create` / `gh release edit --draft=false` / `POST …/releases` / `PATCH …/releases/<id>` with draft false; `git merge <ref>` on main and `git push <remote> <src>:main` are judged by the commit they carry. A PR is judged by its own HEAD (so a hotfix needs its own stamp);
a release by the commit it publishes. A command it cannot read denies. `QA_ALLOW_MAIN=1` is the audited
override; the marketplace repo itself is exempt.

**A merge into `main` must pin the head the gate judged.** The gate reads a PR's head and GitHub merges whatever
the head is a moment later, so `gh pr merge … --match-head-commit <sha>` (or `-f sha=<sha>` on the REST merge, or
`expectedHeadOid` on the GraphQL one) is required, with `<sha>` the PR's head: at least 7 hex digits, a prefix of it.
The denial prints the exact command. A merge into any other branch needs no pin.

**One command, one branch.** The gate reads `HEAD` and the refs before the command runs, so it follows them through
the command: after `git switch main`, a later `git merge`, `git pull` or push is judged as on `main`, and a push to
`main` after a command that moves a ref or `HEAD` is refused (run them as separate commands). A branch change it
cannot follow denies.

**Another repository is held to the same standard.** A command that acts on a repository other than this checkout's (`-R`,
`GH_REPO`, a `repos/<owner>/<repo>` path, another remote) is judged by that repository's own stamp, read through the API, and by
its first-boot walkthrough and authorization sweep as committed there (`scripts/remote_evidence.py` fetches the commit into a
scratch repository and runs the same check). A stamp with no `schema` committed after 2026-09-29 is refused until re-certified.
The gate stops that work by itself inside the hook's 15 s timeout: a hook that times out lets the command through, so a command
with no time left, or a stalled network call, is denied instead.

## Platform note

This plugin's hooks are **bash + python3** scripts. On Windows, run Claude Code inside
**WSL or Git Bash** with `python3` available, or the hooks (including the blocking
release gate) can't execute. macOS/Linux need no action. The release-gate and other
guards fail safe if their interpreter is missing, but a missing interpreter means the
gate does not run — so ensure the toolchain is present where enforcement matters.
