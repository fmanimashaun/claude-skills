# Claude Skills — wiki

A Rails 8 toolchain for Claude Code: five plugins covering stack doctrine, the build flow,
independent QA, a design system, and the release lifecycle.

**New here?** [Getting started](Getting-Started) is the ten-minute path from install to a first
verified change. Everything else on this page is reference or reasoning.

## Reference — generated from the repository

These three are built by `scripts/build_wiki.py` and checked by a gate, so a renamed command breaks
the build rather than quietly making the wiki wrong.

- **[Command reference](Command-Reference)** — every command, grouped by what you are trying to do
- **[Skills reference](Skills-Reference)** — the seven skills and what each governs
- **[Plugin reference](Plugin-Reference)** — versions, command counts, one line each

## Guides — written, because they need judgement

- **[Getting started](Getting-Started)** — install, scaffold, first feature, first QA pass
- **[How the loops fit](Loops)** — build, verify, ship, and why they are separate agents
- **[Design system](Design-System)** — tokens, components, art direction, the asset pipeline
- **[QA and evidence](QA-And-Evidence)** — what "verified" means here, and what it refuses
- **[Troubleshooting](Troubleshooting)** — the failures that are silent, and how to spot them
- **[Contributing](Contributing)** — reporting a bug from the field, and the git flow

## Deeper reading, in the repository

- [Architecture](https://github.com/fmanimashaun/claude-skills/blob/main/docs/doctrine/architecture.md) — the design reasoning, and what was deliberately not adopted
- [Harness doctrine](https://github.com/fmanimashaun/claude-skills/blob/main/docs/doctrine/harness-doctrine.md) — when a hook fails open versus closed
- [Code-review graph](https://github.com/fmanimashaun/claude-skills/blob/main/docs/doctrine/code-review-graph.md) — the optional tool-gated review integration
- [`CLAUDE.md`](https://github.com/fmanimashaun/claude-skills/blob/main/CLAUDE.md) — the maintainer's guide to this repository

---

**Why this wiki lives in the repository.** A GitHub wiki is a separate git repo: no pull request, no
review, and no gate can reach it. These pages are versioned with the code they describe, so a change
that makes a page wrong shows up in the same diff. Publishing to the GitHub wiki is one `git push`
from here whenever it is wanted.
