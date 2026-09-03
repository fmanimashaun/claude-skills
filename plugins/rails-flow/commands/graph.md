---
description: Regenerate the living architecture graph — docs/architecture/{graph.json,index.html,graph.md} — from routes, app/** and db/schema.rb. Also runs the drift check and the release-notes delta.
argument-hint: "[blank to regenerate | check | delta <ref>]"
---

# /rails-flow:graph — $ARGUMENTS

Extract the architecture **once** and serve all three consumers: humans (`index.html` —
the drawn diagram, one column per layer, plus an index and detail view — and the mermaid
views), agents (structural context without reading the whole codebase — the single
biggest token cost in any large-repo task), and qa-flow (reverse-walk `edges` for a
computed blast radius instead of a guessed one).

Hand-drawn architecture docs go stale within days because they are updated by intention.
This one is generated, digest-checked, and regenerated on a cadence — so it stays true or
it fails loudly.

## Run

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/architecture_graph.py            # regenerate
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/architecture_graph.py --check    # drift check
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/architecture_graph.py --delta origin/main
```

Stdlib Python 3 only — no gems, no graph tool, no network, no app boot. Pass `--enrich`
to fold in `graphify` / `code-review-graph` edges when either is installed; those land in
a separate `enrichment` block that is **deliberately excluded from the digest**, so a
teammate without the tool never sees phantom drift.

Argument routing: blank → regenerate; `check` → `--check`; `delta [ref]` → `--delta`.

## What it emits (all three, always together)

| File | For | Note |
|---|---|---|
| `docs/architecture/graph.json` | agents, qa-flow, `/explain` | `{nodes, edges, flows}` + `commit`, `generated_at`, `content_digest` |
| `docs/architecture/index.html` | humans | self-contained: inline CSS/JS, embedded JSON, **zero external requests** — opens from disk, offline, years later |
| `docs/architecture/graph.md` | repo browsers | mermaid, because `.html` does not render in a GitHub file view |

**`flows` is the part a generic code-graph tool does not give you** — a named, ordered path
through the system for a real user action ("Create an invoice": `POST /invoices` →
controller → model → job → turbo_stream). That is what makes the artefact useful for
onboarding *and* for an agent asking "what does creating an invoice actually touch?".

## Doctrine

- **Never hand-edit the three files.** They are generated; an edit is overwritten and, worse,
  makes the digest lie. Fix the extractor instead.
- **Commit all three together.** A `graph.json` newer than its `index.html` is the staleness
  the artefact exists to prevent.
- **Drift is a finding, not a chore.** `--check` regenerates and compares the
  `content_digest` over `{nodes, edges, flows}` — the same rebuild-and-diff shape as the
  `dist/` guard. `generated_at`/`commit` are excluded, so re-running on an unchanged tree is
  a no-op, while a real structural change cannot hide. Exit 1 = the code moved and the graph
  did not.
- **Structure lives here; meaning lives in `docs/GUIDE.md`.** `/rails-flow:explain` reads this
  artefact's `flows` rather than re-deriving them, and links to `graph.md` instead of copying any
  of it. The split is the point: these three files are generated and digest-guarded, so they
  cannot rot, while the guide's plain-language prose can — which is why the guide stays thin and
  points here for the exhaustive view.
- **Read the extraction notes.** The parser is regex over Ruby/ERB, not an AST: routes built
  by `mount`/`match`/dynamic DSL, and structure created by metaprogramming, are invisible to
  it and are reported in `notes` rather than silently dropped. Treat a growing notes list as
  a signal the extractor needs work, not as noise.

## Report

Node/edge/flow counts with the by-layer split, which files changed, every extraction note,
and — when regenerating on top of an existing graph — the delta in release-notes form
(new/removed nodes, new/removed flows, **flows that changed shape**). "Flow *Create an
invoice* gained a step" tells a reviewer something a 40-file diff does not.

If `--check` failed, say so plainly, show the delta, and regenerate — do not paper over it.
