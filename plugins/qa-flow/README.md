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
- `/qa-flow:certify` — Comprehensive release certification before dev->main — full regression plus release-only layers (load, DAST, cross-browser); writes the stamp that unlocks the deploy gate.
- `/qa-flow:crawl` — Crawl every route in a browser and judge it — broken pages, dead controls, theme-only failures.
- `/qa-flow:functional` — Agentic functional/exploratory testing of a running app via Playwright MCP — menu-scoped, evidence-based, driven from test-case titles.
- `/qa-flow:setup-qa` — Set up the independent QA workspace — detects the codebase's testing signals and PROPOSES a stack (qa/qa.config.yml) you confirm/override, then scaffolds only the chosen tools, seed personas, and case catalogue.
- `/qa-flow:smoke` — Reuse a running server or launch the app (stack-aware), then confirm it actually BOOTS and its key routes respond, before any deeper QA.
- `/qa-flow:verify` — Independent QA verification after a feature merges to dev — smoke gate, sanity, and targeted regression to prove the change broke nothing previously certified.

## Platform note

This plugin's hooks are **bash + python3** scripts. On Windows, run Claude Code inside
**WSL or Git Bash** with `python3` available, or the hooks (including the blocking
release gate) can't execute. macOS/Linux need no action. The release-gate and other
guards fail safe if their interpreter is missing, but a missing interpreter means the
gate does not run — so ensure the toolchain is present where enforcement matters.
