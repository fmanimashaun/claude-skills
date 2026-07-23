---
description: Agentic functional/exploratory testing of a running app via Playwright MCP — menu-scoped, evidence-based, driven from test-case titles. Writes a Markdown report + Excel-openable CSV with screenshots into qa/manual-tests/. Free, repo-local, no online tool.
argument-hint: "[url] [menu scope] — titles from qa/test-cases.csv or pasted"
---

# /qa-flow:functional — $ARGUMENTS

Run functional tests the way a QA engineer would: drive the real app in a browser via
**Playwright MCP**, from a list of **test-case titles**, and produce an evidence-backed
report in the repo. Complements the automated suites — this is exploratory/functional
coverage, not regression.

## Delegate to `functional-tester`

Hand the request to the **functional-tester** agent. It will:

1. **Check prerequisites** — Playwright MCP available; and it has the **URL**, the **menu
   scope**, and the **test-case titles**. Titles come from an in-repo file
   (`qa/test-cases.csv` / `.md` — a Testmo export dropped there works, but the file is the
   source of truth) or pasted inline. If anything's missing, it asks and stops.
2. **Explore** the menu, confirm in-scope items.
3. **Test** each in-scope item (forms valid/invalid, CTAs, data, nav, error states),
   screenshotting every failure; strictly no out-of-scope exploration; no code changes.
4. **Report** — Markdown `qa/manual-tests/<date>-<slug>.md` + a companion **CSV summary**
   (opens in Excel) + screenshots in `qa/manual-tests/screenshots/`.

## Notes

- **Free & repo-local**: no online case management or dashboards — cases and reports are
  files in the repo (Markdown + CSV/Excel).
- Needs the Playwright MCP server: `claude mcp add playwright -- npx @playwright/mcp@latest`
  (then restart). `/qa-flow:setup-qa` scaffolds `qa/test-cases.csv` and `qa/manual-tests/`.
- Grant browser permissions when Playwright prompts (allow-always avoids repeat prompts).
