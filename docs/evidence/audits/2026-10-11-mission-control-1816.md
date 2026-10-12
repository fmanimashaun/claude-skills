# doctrine-verifier verdicts for #1816 (Mission Control recipe), 2026-10-11

One read-only verifier run that read WHOLE files of `mission_control-jobs` 1.3.1 (the installed gem; 1.1.0 also
installed, not read), after a first run in #1694 (`2026-10-11-observability-otel-1694.md`, M1-M3) that read single methods.
Raw output: `raw/2026-10-11-mission-control-1816-verifier.md`. Paths below are relative to the gem. Edits follow
CONFIRMED rows; the last column says what the doctrine does.

| id | claim | verdict | authority | what the doctrine does |
|---|---|---|---|---|
| M1 | with the defaults every request answers 401; `base_controller_class` alone does not admit admins, because the engine controller always includes `BasicAuthentication` whose `before_action` runs while `http_basic_auth_enabled` (default true) | CONFIRMED | `jobs.rb:18,32-34`; `basic_authentication.rb:5-17,27-31`; `application_controller.rb:1,13`; `engine.rb:43-46`; README:59,66,101-104,121 | both settings stated; "enabled and closed" kept (README:59's own words) |
| M1b | the host controller's `before_action`s run before the engine's, so a redirect there halts before basic auth | CONFIRMED (from the callback order in `application_controller.rb:13-18`; no request was run) | same | stated |
| M1c | the README says `base_controller_class` alone suffices | REFUTED: README:101-104 says "you can disable" (soft), it never says the first alone admits admins | README:88-104 | the doctrine says the README is softer than the code |
| M2 | `filter_arguments` matches root-level hash keys only | CONFIRMED | `arguments_filter.rb:3,9-20`; `solid_queue_ext.rb:104,116-118`; `jobs_helper.rb:6-8,66-84`; README:135 | stated, with which views apply it (raw-data top level; list/queue/worker/detail per plain-hash level; GlobalIDs and serialised objects and recurring-task pages and worker raw data unfiltered) |
| M3 | `adapters` defaults to `[queue_adapter \|\| :async]`; `SolidQueueExt` is prepended only when `:solid_queue` is listed | CONFIRMED, with a correction: `:async` renders an empty dashboard (`async_ext.rb`), it does not break; `:test` is unhandled and "expected NoMethodError" is inferred, not run | `engine.rb:32-34,57-68,72-80`; `server.rb:16-20` | stated with the inference labelled |
| X1 | "mount it behind admin auth like any ops surface" is misleading by default | CONFIRMED | `basic_authentication.rb:9-17` | sentence removed |
| X2 | the mount example is right | CONFIRMED | README:19-24 | kept |
| X3 | the README's route-constraint alternative is missing | CONFIRMED | README:108-121 | named, with the same `http_basic_auth_enabled = false` need |
| X4 | route-helper precedence and `back_to_main_app_path` | CONFIRMED (README) | README:106,133 | NOT written: the `jobs-and-realtime.md` claim about the authentication generator's helper was not verified |
| X5 | the ways to set credentials | CONFIRMED | README:59-84; `engine.rb:43-46` | stated |

## Added after review of #1820 (6d at 57589f0e)

| id | claim | verdict | authority | what the doctrine does |
|---|---|---|---|---|
| I1 | `config.mission_control.jobs.*` is copied into `MissionControl::Jobs` in a `before_initialize` hook, which runs before `config/initializers` load, so "(or an initializer)" for the `config.` form was wrong and the setting has no effect there | CONFIRMED for the copy and the hook (`engine.rb:24-30`) and for `adapters` being read in `before_initialize` (`engine.rb:32-34,57-66`); the load order (`before_initialize` before `config/initializers`) is the Rails initialization order, read here by the author directly and not by a verifier subagent (usage limit); the README names "environment config or `application.rb`" (README:94-97) and the direct module form (README:88-91) | `engine.rb`; README:88-97; Retask `config/initializers/mission_control_jobs.rb` (module setters inside `to_prepare`) | "(or an initializer)" removed; the direct form named for initializers; `adapters` only in application.rb / environment config |
| I2 | the filter's "root-level keys only" headline is about the filter itself; the views re-apply it per level; keys match as strings | CONFIRMED (M2, `arguments_filter.rb:9-20`, `jobs_helper.rb:74`) | as M2 | headline narrowed; `k.to_s` stated |

`jobs-and-realtime.md` carried the same one-setting recipe; it is corrected in the same PR (same defect, same row).
