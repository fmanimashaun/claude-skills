# doctrine-verifier verdicts for #1741 and #1748 (rails-8), 2026-10-10

Five read-only `doctrine-verifier` runs, one per claim cluster, plus a second run on #1741 that settled four
routing claims from the framework source and a reproduction. Edits in `skills/rails-8/` follow CONFIRMED rows
only; an INCONCLUSIVE or REFUTED row left (or corrected) the doctrine as stated in the last column.

Rails 8.2 is **unreleased**. Every 8.2 row is `[On main, unreleased]`; the edge guide
(`guides/source/8_2_release_notes.md`) was last changed in commit `54cce92c9a89445ea62b4df3e4cc327888e7339c`
(2026-02-15) and shows no revision of its own, so it is not evidence of a release.

## #1741 — a model's name differs from its resource route (Rails 8.1.4)

| id | claim | verdict | authority | what the doctrine does |
|---|---|---|---|---|
| C1 | polymorphic helpers derive from `model_name` (`singular_route_key` persisted, `route_key` otherwise) | CONFIRMED | `actionpack/lib/action_dispatch/routing/polymorphic_routes.rb` v8.1.4, `handle_model` and the `singular`/`plural` builders; the routing guide (`model_name.route_key`) | stated, with the source |
| C2 | `HttpMonitor` + `resources :monitors` raises `NoMethodError` for `http_monitor_path` | CONFIRMED | reproduction on Rails 8.1.4 (a `RouteSet`, a persisted stub model) | stated, "reproduced on 8.1.4" |
| C3 | `resources :monitors, as: :http_monitors` makes it work (URL stays `/monitors`) | CONFIRMED | same reproduction | stated |
| C4 | `resolve` customises polymorphic mapping | CONFIRMED for `resolve` (documented for singular resources); REFUTED for `direct` | routing guide, "Using `resolve`", "Direct routes" | `resolve` named; `direct` stated as not a polymorphic mapping |
| C5 | overriding `model_name` fixes it, at the cost of `param_key`, `i18n_key`, `human`, route keys | CONFIRMED | `activemodel/lib/active_model/naming.rb` v8.1.4 (lines 178-196) and the reproduction | stated with the side effects |
| C6 | `form_with` for an STI subclass needs explicit `url:` and `scope:` | CONFIRMED | form helpers guide, "Relying on record identification" | stated |

Note: `ActiveModel::Name` lives in `naming.rb`, not `name.rb`. The first run's INCONCLUSIVE on C1-C3 and C5 was
because it was limited to guide and API pages; the guides do not state them. The framework source and a run are
the authority used for those four, and the doctrine says so.

## #1748 — Rails 8.1 job changes and 8.2 readiness

| id | claim | verdict | status | authority |
|---|---|---|---|---|
| J1 | `enqueue_after_transaction_commit` symbol values `:never`/`:always`/`:default` removed (and the global config) | CONFIRMED (removed, not deprecated) | Released in 8.1.0 | 8.1 release notes (Removals); `activejob/CHANGELOG.md` on `8-1-stable` |
| J2 | 8.2: boolean, default `true` for new apps and `load_defaults "8.2"` | CONFIRMED | On main, unreleased | `activejob/CHANGELOG.md` on `main`; 8.2 notes |
| J3 | built-in `sidekiq` adapter deprecated (8.1) and removed (8.2) | CONFIRMED, both halves | 8.1.0 released / 8.2 on main | same CHANGELOGs |
| J4 | 8.2 deprecates built-in queue_classic, resque, delayed_job, backburner, sneakers adapters | CONFIRMED | On main, unreleased | `activejob/CHANGELOG.md` on `main` |
| J5 | the default of `enqueue_after_transaction_commit` in an 8.1 app | INCONCLUSIVE | — | doctrine's existing sentence left unchanged; no default asserted for 8.1 beyond it |
| S1 | `protect_from_forgery using: :header_only` / `:header_or_legacy_token`, `Sec-Fetch-Site`, new-app default, bare call deprecated | CONFIRMED (whether `using:` alone silences the deprecation: not verified) | On main, unreleased | `actionpack/CHANGELOG.md` on `main`; 8.2 notes |
| S2 | 8.1: `with: :exception`, `default_protect_from_forgery` | CONFIRMED | Released in 8.1 | 8.1 API docs; `8-1-stable` `railtie.rb` |
| S3 | `has_secure_password algorithm: :argon2` (`argon2 ~> 2.3`, no length limit) | CONFIRMED | On main, unreleased | `activemodel/CHANGELOG.md` on `main` |
| S4 | `Rails.app`, `Rails.app.creds`, `Rails.app.revision` | CONFIRMED | On main, unreleased | `railties/CHANGELOG.md` on `main` |
| A1 | Active Storage `analyze:` (`:immediately` default, `:later`, `:lazily`) before validation | CONFIRMED (form is `analyze:`, on attachments, not variants) | On main, unreleased | `activestorage/CHANGELOG.md`; 8.2 notes |
| A2 | `process: :immediately` exists; `preprocessed: true` deprecated | CONFIRMED; the replacement is `process: :later`, NOT `:immediately` | On main, unreleased | same |
| A3 | Action Text `to_trix_html` deprecated | CONFIRMED | On main, unreleased | `actiontext/CHANGELOG.md`; 8.2 notes |
| A4 | `has_json`, `has_delegated_json` | CONFIRMED that both exist; they are **Active Model**, not Active Record | On main, unreleased | `activemodel/CHANGELOG.md` |
| H1 | Herb compiles HTML ERB; `erb_implementation = :herb`, `:erubi` opts out | CONFIRMED (HTML format only) | On main, unreleased | rails/rails#58721 (`9fb66ed2dc239e9f78d51c8e36b43f287f548d52`), #58552 (`60eb5cb72dbf06ef9de39c6786df2f20e838884f`) |
| H2 | `herb >= 0.10` runtime dependency of actionview | INCONCLUSIVE: a runtime dependency yes, the constraint not stated | On main, unreleased | #58552; doctrine states the dependency without a version |
| H3 | `bin/rails herb:check` and the security validator | CONFIRMED, in flux (Herb 0.11 bump under discussion 2026-10-01) | On main, unreleased | #58770 (`5f1654d584d256a5f16eb364db29de2d60913b11`), #58874 (`6122999ff4cccb706dc6d6ed1a0d3676a16cf173`) |
| H4 | structural HTML errors fail compilation; ViewComponent sidecars | CONFIRMED for the compile failure; the sidecar statement rests on ViewComponent#2717 (a report, open) | On main, unreleased | #58721; ViewComponent#2717 |
| H5 | ReActionView is a third-party gem, not Rails core | INCONCLUSIVE | — | left out of the doctrine, as the issue asked |

Where the written doctrine is, and what it was not allowed to say: `skills/rails-8/references/rails-8-2-readiness.md`
(new, every item labelled unreleased), `jobs-and-realtime.md` (8.1 J1, J3), `controllers-routing.md` (C1-C6),
with one-line pointers in `auth-security.md`, `ecosystem-gems.md`, `mail-storage-richtext.md` and `SKILL.md`.
