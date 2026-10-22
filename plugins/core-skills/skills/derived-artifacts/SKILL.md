---
name: derived-artifacts
description: How to build anything whose numbers come from somewhere else — read the generator's structured source, never regex-parse generated prose, and assert every derived total against the source's own declared totals. Use when writing or updating a script that produces a report, table, page, or summary from another file; when a doc or artifact would otherwise carry hand-transcribed counts; or when quoting figures that live in a generated file such as coverage.md.
---

# Derived artifacts

Anything that restates data from elsewhere — a generated page, a report script, a summary
table, a count in a doc — is a derived artifact. These rules make it correct by
construction rather than correct by luck. Each one comes from a run that got it wrong.

## 1. Go to the structured source, not the generated prose

- Before parsing a file, ask what **produced** it. If it is itself generated, read the
  generator's source of truth instead — parse what the builder parses, or have the builder
  emit structured data (JSON/CSV) that both it and your artifact consume.
- **Never label-match on prose.** Substring matching on rendered text is the bug class: a
  matcher for `documented` also hit `— derivable from documented…` and reported **64
  documented when the real figure was 44**.
- Prose is a rendering, not an interface. Its wording changes for editorial reasons, and
  every such change silently breaks a parser downstream.
- If no structured source exists, the fix is to **create one** — add a machine-readable
  emit to the generator — not to write a tighter regex.

## 2. Assert the parse against the source's declared totals

- Every derived number must be checked against a total the source states about itself: a
  `Totals` table, a summary row, a manifest count. Compare them, and **fail loudly** —
  raise or exit non-zero — on any mismatch. Never warn and continue.
- Print both sides in the failure message: `parsed 64 documented but Totals claims 44`. A
  bare assertion failure costs a debugging round-trip that the message could have saved.
- This is not defensive padding. The assertion caught a real mis-parse on its very first
  run, before any wrong number shipped.
- The assertion does not excuse rule 1. It catches a bad parse; it does not make parsing
  prose a correct design.

## 3. Generate it; never transcribe it

- Numbers in a committed artifact must come from a script that can be re-run, not from
  values copied by hand. Commit the generator alongside its output.
- **Say which input state the output reflects.** An artifact that matches reality only
  because the source happened to be merged mid-task is "accurate by timing rather than by
  design" — treat that as a latent defect to call out, not as a pass.
- Record provenance in the output itself (source file, generator name, commit) so the next
  reader can re-derive the numbers instead of trusting them.
- When reporting the work as done, state whether the artifact was generated or transcribed,
  and name the assertion that guards it.
