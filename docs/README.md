# docs/ — the map

A file's directory answers the question a reader would ask to find it. Code goes in `scripts/`, never here.
A script's output goes under a directory marked `.generated`. Binaries go under `design/assets/` or `evidence/`, never at a root.
Memos go under `brain/memos/<type>/`. Before creating a file, find its question below; if none fits, ask — do not invent a directory.

| directory | question | what belongs |
|---|---|---|
| `product/` | WHAT are we building? | the spec, roadmap, routes, `features/F-NN-*.md`, `roles/`, `acceptance/`. Authored. Not: how it is built, how to run it. |
| `design/` | WHAT does it look like? | briefs, prompts, UI decisions; images and brand files under `assets/`. Authored. Not: screenshots as evidence (evidence/). |
| `architecture/` | HOW is it built? | GENERATED from code by `/rails-flow:graph` (`graph.json`, `graph.md`, `index.html`). Never hand-edited; regenerate instead. |
| `runbooks/` | HOW do I operate it? | setup guides, deploy, on-call, integrations (SSO, mail, payments). Authored. Dated where a step depends on a version. |
| `evidence/` | WHAT did we measure? | spikes, screenshots, coverage reports, validation results. Dated, immutable: add a new file, never edit an old one. |
| `wiki/` | WHERE is the reference? | GENERATED reference pages from the codebase plus hand-written pages the generator leaves alone. Rebuilt at ship. |
| `doctrine/` | WHAT do our agents follow? | the maintainer's authored rules and their reasoning: `doctrine/harness-doctrine.md`, `doctrine/architecture.md`, `doctrine/code-review-graph.md`, `doctrine/issue-dependency-graph.md`. Not: the plugins' shipped skills (those live in `skills/`). |
| `brain/` | WHAT did we learn and decide? | `STATUS.md`, `DECISIONS.md`, `HYPOTHESES.md`, `PROGRESS-LOG.md`, `MEMORY.md`, memos under `memos/<type>/`, `history/`. Not: product specs (product/). |

Check: `python3 <rails-flow>/scripts/docs_layout.py --report` · rework an existing tree: `--propose`, then `--write`.

## Root files

Files this layout cannot name by kind alone, and where they belong here. The tool reads this table.

| file | home |
|---|---|
| `*-doctrine.md` | `doctrine/` |
| `architecture.md` | `doctrine/` |
| `code-review-graph.md` | `doctrine/` |
| `issue-dependency-graph.md` | `doctrine/` |
| `maintainer-history.md` | `brain/history/` |
| `coverage.html` | `evidence/` |
| `doctrine-map.html` | `architecture/` |
