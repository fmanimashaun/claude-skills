---
name: feedback-a-skip-inside-a-total-is-not-a-pass
description: "\"0 failed, 2 skipped\" hid a 900 s mutation-coverage timeout; I wrote \"including mutation coverage\" into two promotion bodies. Read which gates skipped."
type: feedback
---

On 2026-09-24 the local full doctor printed "122 passed, 0 failed, 2 skipped" twice, and I quoted it in
the v1.146.0 and v1.147.0 promotion bodies as a full pass "including mutation coverage". One of the two
skips WAS mutation coverage: it timed out at 900 s and did not run. Meanwhile CI's push run on dev had
found a guard I broke (#1271 → #1283) and every dev push was red.

**Why:** a total treats `skip` as neither pass nor fail, so a count reading "0 failed" says nothing
about the gate that matters most. Only `release.yml`'s own sweep stopped a bad release.

**How to apply:** before quoting a doctor result, `grep -A1 '\[ skip \] gate'` and name each skip and
its reason. For a promotion, the evidence is the **push-event** CI run on dev's tip, or a standalone
`python3 scripts/mutation_check.py` with no timeout — never a local `--gates` total. Related:
[[filter-ci-runs-by-event]], [[a-diagnostic-object-is-not-a-pass]], [[a-watcher-that-cannot-see-a-dead-job]].

A second lesson from the same day: doctrine-verifier REFUTED "libvips is Active Storage's default"
after reading only `engine.rb`'s `|| :mini_magick` fallback; `load_defaults "7.0"` sets `:vips`
(railties `configuration.rb:255`). A verifier verdict is evidence, not an oracle — when it contradicts
a guide that says "depends on load_defaults", read the file the guide points at. See
[[a-true-result-about-the-wrong-file]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-skip-inside-a-total-is-not-a-pass.md._
