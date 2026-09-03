# Framework gap audit — official sources vs authored skills

**Date**: 2026-07-21 · **Trigger**: verify the rails-8 and hotwire skills against
the official repositories rather than secondary material.
**Sources audited**: rails/rails @ `8-1-stable` (8.1.3), hotwired/turbo (8.0.23),
hotwired/stimulus (3.2.2), hotwired/hotwire-native-ios, rails/mission_control-jobs.

## Method

Shallow clones of all five repos. Ground truth extracted mechanically: the 75
official guides as the coverage checklist, railties boot/engine internals, the
default middleware stack, the Active Support core_ext surface, Turbo's stream-action
registry and drive internals, Stimulus's src API surface, Hotwire Native's bridge
architecture. Then a 31-cluster grep matrix against our references, with manual
depth probes on every single-hit topic.

## Verified correct (the headline)

- **Version pins exact**: Rails 8.1.3, Turbo 8.0.23, Stimulus 3.2.2 — all match
  the skills' authored facts.
- **Turbo stream actions**: source registry = after, append, before, prepend,
  remove, replace, update, refresh — all eight enumerated in `turbo.md`, plus
  custom-action coverage.
- **30 of 31 topic clusters covered**, including every hotwire cluster (outlets,
  dispatch, action options, prefetch, permanent elements, view transitions,
  morphing/refresh, bridge components, path configuration, navigator).
- **Depth probes passed** on all single-hit candidates: engines
  (`isolate_namespace` + host-integration example in extending-rails), generators
  (`Rails::Generators::NamedBase` example), composite primary keys (doctrine +
  code in advanced-active-record), deployment tuning (YJIT/jemalloc/Thruster in
  deployment-kamal).

## Gaps found

**P1 — doctrine missing: the Rails executor / threading model** (guide:
threading_and_code_execution). Nothing in the skills told an agent that manual
concurrency (`Thread.new`, promises, post-response middleware work) must run
inside `Rails.application.executor.wrap`, about the dev-mode load interlock, or
about reloadable-constant caching. These bugs hide in development and surface in
production. → **Fixed in rails-stack 1.0.3**: new §7 in jobs-and-realtime.md.

**P2 — shallow: mission_control-jobs** was a one-line mention. The dashboard's
adapter-dependent feature set, mount-behind-auth pattern, and "never poll
SolidQueue tables by hand" doctrine were absent. → **Fixed in rails-stack 1.0.3**:
expanded block in jobs-and-realtime.md §2.

## Backlog (P3 — valuable, not urgent)

- Default middleware stack reference table (extracted snapshot: HostAuthorization,
  AssumeSSL/SSL, ServerTiming, Executor, ActionableExceptions, PermissionsPolicy,
  DatabaseSelector/ShardSelector among the notable) → candidate for
  extending-rails.
- Active Support core_ext quick index (the 30+ extension families) → candidate
  appendix in models.md or a new as-core-ext reference.
- Turbo drive internals worth doctrine notes: prefetch cache and limited-set
  behavior, morphing page renderer boundaries.
- Stimulus schema customization (custom data attribute prefixes) — niche.
- Devcontainer workflow expansion in project-setup.md — one mention today.

## Doctrine-change protocol (standing rule, added 2026-07-22)

Order is law, and it runs BEFORE any skill edit: **(1) verify against
authoritative sources** — maintainers' docs and writing, official guides,
framework source; **(2) check house practice** — the mature codebases
(fmworkflows, auctioneer); **(3) apply engineering reasoning** — and present
the verdict to the user before touching a file. Factual claims that sources
refute are rejected no matter who makes them (the `RSpec.describe` case).
Style-doctrine changes require source + practice alignment (the factories
case — right conclusion, but steps 2–3 ran before step 1; this rule exists
because of that inversion). No skill file changes until the verification is
on the table.

## Standing conclusion

The skills were authored right. The audit found zero incorrect doctrine, one
missing advanced topic, one shallow tool section — both remediated same-day.
Re-run this audit when Rails 8.2 / Turbo 8.1 ship: clone, re-extract, re-diff.
