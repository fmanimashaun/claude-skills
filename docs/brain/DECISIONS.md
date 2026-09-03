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

## D-004 — The maintainer's CLAUDE.md history stays in `docs/maintainer-history.md` (2026-09-03) `[decided]`
**Choice:** this repo's relocated incident narrative lives at `docs/maintainer-history.md`, while the
shipped tool's default for projects is `docs/brain/claude-md-history.md`. **Rationale:** the file
predates the brain here and 17 `doctrine_map` anchors and lint pointers name it; moving it buys
nothing a reader can measure. **Reversal condition:** a second history file appears, or a tool needs
one location for both.
