# DECISIONS (ADR-lite)

## D-001 — Relocate, never summarise (2026-09-03) `[decided]`
**Choice:** when `CLAUDE.md` passes its ceiling, pure-history paragraphs move **verbatim** to a history
file with one pointer per section; nothing is paraphrased. **Alternatives:** summarise in place;
delete old incidents. **Rationale:** the maintainer — "blind summarising context is dangerous, it can
impact quality"; a ceiling on what *loads at session start*, not on what exists. **Enforced by:**
`plugins/rails-flow/scripts/claude_md_structure.py` (`assert_lossless`), lint `claude-md-growth`.
Refs #870, #875. **Reversal condition:** a measured case where the pointer hop costs more context
than the relocated paragraph saved.

## D-002 — `brain-sync local --propose` never writes the repo (2026-09-03) `[decided]`
**Choice:** the outbound direction renders memo files and writes nothing; `/rails-flow:brain` writes
after a human picks. **Alternatives:** auto-write memos; a hook that writes on SessionStart.
**Rationale:** the repo is reviewed truth, a local memory may be personal. **Enforced by:** the
`propose writes nothing` fixture and its mutation (`scripts/mutations/brain_local_sync.py`). Refs #877.
**Reversal condition:** a team that wants unreviewed memos and says so in a DECISIONS entry of its own.

## D-003 — A pointer memory carries the memo's own description (2026-09-03) `[decided]`
**Choice:** the local pointer's `description` is the brain memo's line verbatim, not a fixed sentence.
**Rationale:** that line is what auto-memory recall matches on; a fixed sentence would recall nothing.
**Enforced by:** fixture "the pointer carries the memo's own description verbatim" + mutation. Refs #877.
**Reversal condition:** the harness stops matching recall on `description`.

## D-004 — REVERSED 2026-09-03 by D-005: the history file moved to `docs/brain/history/maintainer-history.md` `[decided]`
**Choice:** this repo's relocated incident narrative lives at `docs/brain/history/maintainer-history.md`, while the
shipped tool's default for projects is `docs/brain/claude-md-history.md`. **Rationale:** the file
predates the brain here and 17 `doctrine_map` anchors and lint pointers name it; moving it buys
nothing a reader can measure. **Reversal condition:** a second history file appears, or a tool needs
one location for both.

## D-005 — The maintainer repo follows the shipped docs/ layout, with one declared directory (2026-09-03) `[decided]`
**Choice:** `docs/` here is laid out by `docs_layout.py` like every project's: `doctrine/` (declared in the map — the
maintainer's authored rules), `architecture/` (generated: `doctrine-map.html`; `inventory.html` until D-006), `evidence/`
(`coverage.html`, `audits/`), `brain/history/` (the relocated CLAUDE.md narrative), `wiki/` (generated). Root-file
homes are the map's `## Root files` table, which the tool reads. **Alternatives:** leave the maintainer repo as the
exception; invent a maintainer-only layout. **Rationale:** the tool's first real run on Retask-platform matched the
hand review; a repo that ships a layout and does not keep it is the claims-vs-enforcement class. Refs #886.
**Reversal condition:** a generated page that cannot live under `architecture/` or `evidence/` without a script losing
its drift gate.

## D-006 — One generated reference surface: the inventory page folds into the wiki (2026-09-03) `[decided]`
**Choice:** `docs/architecture/inventory.html`, its generator `build_inventory.py`, its selftest and its two gates are
retired; the data layer lives in `scripts/inventory_data.py` (readers imported, never re-parsed; verifications kept,
one `inventory data selftest` gate) and renders as `docs/wiki/Agents-And-Gates.md` under the wiki's existing drift
gate. `coverage.html` stays: the only browsable view of the design-system matrix. **Alternatives:** keep both and
cross-link. **Rationale:** two generated views over one input set, each with its own generator, drift gate and
selftest, is the shape this repo argues against everywhere else (`duplicated-release-extractor`); the filter chips
are the one loss. Refs #892. **Reversal condition:** a reader who needs the cross-kind filter and cannot get it from
a wiki search.
