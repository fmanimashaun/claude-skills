section: rails-flow
- **The coverage ratchet `/rails-flow:setup-flow` proposes no longer carries a deprecated line, and turns on branch coverage — `plugins/rails-flow/commands/setup-flow.md`, `plugins/rails-flow/scripts/check_coverage_ratchet.py`** (#1957, found closing the #1948 audit).
  - `minimum_coverage_by_file line: 0` was prescribed as inert, but it has been deprecated since SimpleCov 1.0.0 and prints a deprecation warning on every run. It is dropped from the snippet and from the check's advice.
  - `refuse_coverage_drop :line, :branch` raises unless `enable_coverage :branch` is set, so the snippet now sets it. The rails-8 skill's `testing.md` already did.
  - doctrine-verifier CONFIRMED both against SimpleCov's source: `lib/simplecov/configuration/thresholds.rb` (the deprecation at :79 in v1.0.0 and :55 in v1.3.2; `raise_if_criterion_disabled` at :22-23 in v1.0.0).
  - Version boundary: the deprecation starts at 1.0.0; the branch requirement holds in 0.22.x and 1.x. The ratchet itself (passes with no baseline, fails on any drop, baseline written only after a passing run) was CONFIRMED unchanged.
