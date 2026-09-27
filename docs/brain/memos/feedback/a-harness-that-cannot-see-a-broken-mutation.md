---
name: feedback-a-harness-that-cannot-see-a-broken-mutation
description: A mutation harness must prove the mutated code RAN — a load error and a backwards edit both read as 'survived'.
type: feedback
---

A mutation harness that decides "killed" by grepping RSpec output for `0 failures` reports a
surviving mutation in four cases where nothing was tested at all:

- **The mutated file does not load.** `"0 examples, 0 failures, 1 error occurred outside of
  examples"` *contains* `0 failures`. Deleting one line from a leading-dot method chain left a blank
  line mid-chain — a syntax error — and the harness called it a survivor.
- **The edit did not remove the behaviour.** `unless @run.card_only?` → `unless false` makes the
  guard *unconditional* rather than absent, so nothing could go red.
- **The failure list is not the failure count.** RSpec's `rspec ./file:line` rerun block DEDUPES
  by source line, so examples generated in a loop — one `it` block, seven names — collapse out of
  it entirely. A run printing **18 failures** listed **11** rerun lines, and a harness matching the
  intended example name against that block called the mutation SURVIVED while it was killing seven
  examples. Re-run the intended example BY NAME (`rspec <file> -e "<name>"`) and require that run
  to fail, rather than reading the rerun list.
- **Every test skipped is not every mutation surviving.** A Playwright suite whose fixtures had
  aged out reported `0 passed, 0 failed, 10 skipped` for every mutation in a row. Require that
  something ran before scoring anything.

The first two each cost a debugging pass hunting for a missing example that was already there.

**Why:** the harness's verdict is the only thing standing behind "every check can fail", so a
false "survived" sends you to strengthen a test that is fine, and a false "killed" would be worse.

**How to apply:** require that examples actually executed — reject any run whose output contains
`error occurred outside of examples` or `0 examples`, or whose runner reports every test skipped. Then read the mutated source before believing
a survivor: check the edit removes the behaviour, and check whether the framework or the database
already guarantees it (see [[proving-the-helper-is-not-proving-the-caller]]). Prefer replacing a
whole statement over deleting a fragment, so the result stays parseable. Related:
[[gate-the-commit-on-the-check]], [[a-diagnostic-object-is-not-a-pass]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-harness-that-cannot-see-a-broken-mutation.md._
