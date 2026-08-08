# Claude Skills — wiki

A Rails 8 toolchain for Claude Code: five plugins covering stack doctrine, the build flow,
independent QA, a design system, and the release lifecycle.

**New here?** [Getting started](Getting-Started.md) is the ten-minute path from install to a first
verified change. Everything else on this page is reference or reasoning.

## Reference — generated from the repository

These three are built by `scripts/build_wiki.py` and checked by a gate, so a renamed command breaks
the build rather than quietly making the wiki wrong.

- **[Command reference](Command-Reference.md)** — every command, grouped by what you are trying to do
- **[Skills reference](Skills-Reference.md)** — the seven skills and what each governs
- **[Plugin reference](Plugin-Reference.md)** — versions, command counts, one line each

## Guides — written, because they need judgement

- **[Getting started](Getting-Started.md)** — install, scaffold, first feature, first QA pass
- **[How the loops fit](Loops.md)** — build, verify, ship, and why they are separate agents
- **[Design system](Design-System.md)** — tokens, components, art direction, the asset pipeline
- **[QA and evidence](QA-And-Evidence.md)** — what "verified" means here, and what it refuses
- **[Troubleshooting](Troubleshooting.md)** — the failures that are silent, and how to spot them
- **[Contributing](Contributing.md)** — reporting a bug from the field, and the git flow

## Deeper reading, in the repository

- [Architecture](../architecture.md) — the design reasoning, and what was deliberately not adopted
- [Harness doctrine](../harness-doctrine.md) — when a hook fails open versus closed
- [Code-review graph](../code-review-graph.md) — the optional tool-gated review integration
- [`CLAUDE.md`](../../CLAUDE.md) — the maintainer's guide to this repository

---

**Why this wiki lives in the repository.** A GitHub wiki is a separate git repo: no pull request, no
review, and no gate can reach it. These pages are versioned with the code they describe, so a change
that makes a page wrong shows up in the same diff. Publishing to the GitHub wiki is one `git push`
from here whenever it is wanted.
