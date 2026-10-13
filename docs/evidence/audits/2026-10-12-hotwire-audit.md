# Audit: the hotwire skill against official sources (2026-10-12)

Auditor: fd / claude-skills-e9, assigned by coordinator claude-skills-24 (e8 keeps rails-8). Method: one doctrine-verifier per reference; each picked the file's load-bearing claims (API names, attributes, signatures, defaults, stated behaviour, version boundaries) and checked them against source at release tags. Full tables, one row per claim with file:line, verdict, source and quote: `raw/2026-10-12-hotwire-audit-{turbo,stimulus,native,production}.md`.

| Reference | Claims | Confirmed | Refuted | Inconclusive | Verified against |
|---|---|---|---|---|---|
| `turbo.md` (+ SKILL.md Turbo parts) | 26 | 25 | 1 | 0 | `@hotwired/turbo` 8.0.23 built source; turbo-rails 2.0.23 gem source; turbo 8.0.0/8.0.13/8.0.14 packages for boundaries |
| `stimulus.md` (+ SKILL.md pin) | 23 | 23 | 0 | 0 | hotwired/stimulus v3.2.2 source and v3.0.0–v3.2.2 release notes; stimulus-rails v1.3.4 |
| `native.md` | 27 | 25 | 2 | 0 | hotwire-native-ios 1.3.1, hotwire-native-android 1.3.2, hotwire-native-bridge v1.2.2, at release tags |
| `production.md` | 22 | 22 | 0 | 0 | turbo-rails v2.0.23, `@hotwired/turbo` v8.0.23, Stimulus v3.2.2, rails/rails 8-0-stable, solid_queue README |
| **Total** | **98** | **95** | **3** | **0** | |

## Findings, each filed and fixed on this branch

- **#1960** (`turbo.md:479`, REFUTED): `turbo_stream_request?` does not exist in turbo-rails 2.0.23; only `turbo_frame_request?` does. Replaced with `request.format.turbo_stream?`, separately CONFIRMED: turbo-rails `lib/turbo/engine.rb:77` registers `:turbo_stream`, and Rails' `Mime::Type#method_missing` answers `<symbol>?` (`mime_type.rb:336-338`, 8-0-stable and 8-1-stable). Same issue, wording: the refresh `method`/`scroll` precedence is now traced (8.0.23), and the `turbo_frame_tag` signature is corrected.
- **#1961** (`native.md:271`, `:76`, REFUTED): the `push` presentation is Android-only; `hideTabBarWhenPushed` was never renamed in a release. Also notes that `matchQueryStrings` already defaults to true.
- **#1962** (`stimulus.md:118`, `:132`): click modifiers and the `page_up`/`page_down` filters arrived in **3.2.2**, not 3.2.0. The claims were true; the boundaries were off by a patch release.

## Not audited

The SKILL.md Rack status-symbol matrix (a Rack/Rails claim), the Solid Queue ordering note in `turbo.md`, `native.md`'s §4 behaviour matrix and patch-note PR numbers, and observational notes about Campfire/Fizzy (not framework claims).
