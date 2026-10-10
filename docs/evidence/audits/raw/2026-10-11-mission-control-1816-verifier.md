<!-- Verbatim hand-back of a read-only verifier subagent for claude-skills #1816 (whole files of mission_control-jobs 1.3.1). Model output, unedited; the audit record one level up draws its verdicts from it. -->

Doctrine-verifier report, claude-skills #1816, mission_control-jobs 1.3.1. Nothing in any repo was edited.

Version note: two versions are installed, 1.1.0 and 1.3.1. I read only 1.3.1. Retask pins it exactly (Gemfile:48 `gem "mission_control-jobs", "1.3.1"`, Gemfile.lock:272). All paths below are relative to `/Users/fmanimashaun/.local/share/mise/installs/ruby/4.0.6/lib/ruby/gems/4.0.0/gems/mission_control-jobs-1.3.1/`.

Two file-name corrections to the brief:
- There is no `lib/mission_control/jobs/solid_queue_ext.rb`. The file is `lib/active_job/queue_adapters/solid_queue_ext.rb`.
- The README has no heading "Filtering sensitive arguments". It has "### Authentication" (README:57-121) and "### Other configuration settings" (README:123-135). The filtering text is a single bullet at README:135.

| Row | Verdict | Authority |
|---|---|---|
| M1 | CONFIRMED (every sub-claim holds) | see below |
| M2 | CONFIRMED | see below |
| M3 | CONFIRMED, with a correction to what breaks | see below |
| X1 | "mount it behind admin auth like any ops surface" is misleading for the default setup | see below |
| X2 | Mount path example is fine | see below |
| X3 | The route-constraint alternative is missing | see below |
| X4 | "Back to main app" and engine route helpers are missing | see below |
| X5 | Credentials and the generator are not mentioned | see below |

**M1: CONFIRMED**

- **Defaults.** `lib/mission_control/jobs.rb:34` sets `http_basic_auth_enabled, default: true` and `:18` sets `base_controller_class, default: "::ApplicationController"`. User and password have no default (`:32-33`).
- **The concern.** `basic_authentication.rb:5-7` registers `before_action :authenticate_by_http_basic`. Lines 9-17 read: `if http_basic_authentication_enabled?` then, `if http_basic_authentication_configured?`, call `http_basic_authenticate_or_request_with(**credentials)`, `else head :unauthorized`. Lines 27-31 treat blank credentials as absent via `.transform_values(&:presence)`.
- **Credentials source.** `engine.rb:43-46` fills user and password with `||=` from `app.credentials.dig(:mission_control, ...)`.
- **The concern is always included.** `application_controller.rb:1` is `class ... < MissionControl::Jobs.base_controller_class.constantize`. Line 13 is `include MissionControl::Jobs::BasicAuthentication` and is unconditional. Setting `base_controller_class` alone therefore does not remove the check. With no credentials every request gets 401. With credentials, an admin who passes the host controller is still prompted for basic auth.
- **Callback order.** The host controller (AdminController) is the superclass, so its `before_action`s are registered first. The engine's callbacks are appended after, in `application_controller.rb` include order:
  1. `authenticate_by_http_basic` (line 13)
  2. `set_application` (line 14, ApplicationScoped)
  3. adapter and job-filter callbacks (lines 15-16)
  4. `around_action :set_current_locale` (line 18)
  The host's authentication therefore runs first. If it redirects or renders, the chain halts and basic auth never runs. The superclass's own `before_action`s are not reordered by the include.
- **Fix.** Add `config.mission_control.jobs.http_basic_auth_enabled = false`. README:101-104 says exactly this ("If you do this, you can disable the default HTTP Basic Authentication using the following option") and README:121 repeats it for the route-constraint case.
- **"Ships with HTTP basic auth enabled and closed".** This is accurate and is the README's own wording (README:59: "**HTTP basic authentication enabled and closed** by default"). README:66 adds "If no credentials are configured, Mission Control won't be accessible."
- **Does the README say `base_controller_class` alone suffices?** No. README:88-94 shows only `base_controller_class`, but README:101-104 says "If you do this, you can disable the default HTTP Basic Authentication". That sentence says "can", not "must", which is soft and misleading. The README never states that `base_controller_class` alone admits admins. Doctrine that cites the README for "set base_controller_class to admit admins" overstates it.
- **Retask configures both.** `config/initializers/mission_control_jobs.rb:23` sets `base_controller_class = "SystemHealth::JobsBaseController"` and `:24` sets `http_basic_auth_enabled = false`. Both are inside `Rails.application.config.to_prepare`. `JobsBaseController < BaseController` (`app/controllers/system_health/jobs_base_controller.rb:7`).
- **Statement exactly true for 1.3.1:** In mission_control-jobs 1.3.1 every engine request returns 401 until `http_basic_auth_user` and `http_basic_auth_password` are set. `ApplicationController` always includes `BasicAuthentication`, whose `before_action` runs after the host base controller's callbacks. Admitting your own admins therefore needs both `base_controller_class` set to an authenticating controller and `http_basic_auth_enabled = false`.

**M2: CONFIRMED**

- **Matching rule.** `lib/mission_control/jobs/arguments_filter.rb:9-20` is the whole filter. An Array maps recursively over its elements. A Hash is rebuilt as `[k, filter.include?(k.to_s) ? FILTERED : v]`, so a non-matching value `v` is returned as-is with no recursion. Anything else is returned unchanged. `FILTERED = "[FILTERED]"` (line 3).
- **Resulting behaviour.** The filter matches hash keys only, by string equality of `k.to_s`. It never recurses into the value under an unmatched key. A matched key's value becomes `"[FILTERED]"`. A scalar in a positional or array slot is never filtered, because only Hash keys are compared. Hashes sitting directly in an array are filtered, because the Array branch maps `apply_to` over them.
- **Raw-data view.** `app/views/mission_control/jobs/jobs/_raw_data.html.erb:3` renders `JSON.pretty_generate(job.filtered_raw_data.without("backtrace"))`. `solid_queue_ext.rb:104,116-118` builds it by deep-duping the raw data and applying the filter to `["arguments"]["arguments"]` only. The result is `"key": "[FILTERED]"` for matching root-level keys. Under Solid Queue the `arguments` array is the Active Job argument list. A kwargs hash therefore appears as one array element, a hash with `_aj_ruby2_keywords` and `_aj_symbol_keys` markers, and its own keys are matched by the Array-then-Hash path. Resque does the same at `resque_ext.rb:208-214`.
- **Do other places use the same filter?** Yes, for the pages below, but through a different code path (the helper, not `filtered_raw_data`). `jobs_helper.rb:6-8` defines `job_arguments(job)`. `as_renderable_hash` at line 74 calls `MissionControl::Jobs.job_arguments_filter.apply_to(argument)` and then `.transform_values { |v| as_renderable_argument(v) }`, which recurses into the unmatched values. The helper path is therefore deeper than the raw-data path for plain hashes. The helper is used by these views, all through `job_arguments(job)`:
  - `shared/_job.html.erb:11`
  - `queues/_job.html.erb:11`
  - `workers/_worker.html.erb:14`
  - `jobs/_job.html.erb:6`
  - `jobs/_general_information.html.erb:7` (the job detail view)
  - Rendering: arguments become `{key: value, key2: [FILTERED]}` joined with ", " (`jobs_helper.rb:74-79`), and lists render as `[a, b]` (line 84). List views truncate to 300 characters. The detail view's General information does not.
  - Exception: hashes with `_aj_globalid`, a `_aj_serialized` marker, or ModuleSerializer values (`jobs_helper.rb:66-73`) are rendered as the GlobalID string or deserialized value and never filtered. A GlobalID or serialized object is thus unfiltered.
- **Places the filter does not apply.**
  - `recurring_tasks/_general_information.html.erb:11` and `_recurring_task.html.erb:10` print `recurring_task.arguments.join(",")` with no filter.
  - `workers/_raw_data.html.erb:5` prints `worker.raw_data` unfiltered.
  - Whether a worker's raw data contains job arguments was not checked.
- **Retask's change.** Retask prepends `DeepArgumentsFilter` (`config/initializers/mission_control_jobs.rb:11-19`) to make the match recurse at any depth. The comment at `:7-9` confirms upstream does not recurse. Its filter list is at `:31`.
- **Statement exactly true for 1.3.1:** `filter_arguments` replaces the value of any hash key whose string form matches with `"[FILTERED]"` at the root of the argument structure, and never recurses into an unmatched key's value. The raw-data view uses `filtered_raw_data`, which applies the filter only at the top level of the arguments array. The list, queue, worker and job-detail views render through `job_arguments`, which re-applies the filter at each plain hash nesting level while leaving GlobalID and serialized objects unfiltered. The recurring-task pages and worker raw data are not filtered. README:135 correctly says "Currently, only root-level hash keys are supported."

**M3: CONFIRMED, with a correction to what breaks**

- **Default adapter list.** `engine.rb:32-34`: `if MissionControl::Jobs.adapters.empty?` then `adapters << (config.active_job.queue_adapter || :async)`. `jobs.rb:16` defaults `adapters` to `Set.new`, inside `before_initialize` (`engine.rb:24`). This matches the README:129 description, "By default this will be the adapter you have set for `active_job.queue_adapter`."
- **SolidQueueExt.** `engine.rb:57-66`: in a second `before_initialize` block, `if MissionControl::Jobs.adapters.include?(:solid_queue)` then `ActiveJob::QueueAdapters::SolidQueueAdapter.prepend ActiveJob::QueueAdapters::SolidQueueExt`.
- **Registration.** `engine.rb:72-80`, in `after_initialize`, builds one server per listed adapter with `ActiveJob::QueueAdapters.lookup(adapter).new`.
- **:async case.** `engine.rb:68` runs `ActiveJob::QueueAdapters::AsyncAdapter.include ActiveJob::QueueAdapters::AsyncExt` unconditionally. The dashboard therefore does not crash. `async_ext.rb` stubs everything to empty:
  - `queues` returns `[]`
  - `jobs_count` returns 0
  - `fetch_jobs` returns `[]`
  - `supports_queue_pausing?` returns false
  Solid Queue's tables are never read, so the dashboard shows nothing, even though the database holds jobs.
- **:test case.** The gem has no handling for `:test` (grep for "TestAdapter" returned nothing in `lib` and `app`). If the adapter list is `[:test]`, `lookup(:test).new` is an `ActiveJob::QueueAdapters::TestAdapter` instance that does not include `MissionControl::Jobs::Adapter`. `MissionControl::Jobs::Server#activating` (`server.rb:16-20`) calls `queue_adapter.activating(&block)`, which TestAdapter does not define. I did not confirm that TestAdapter lacks `activating` in activejob 8.1.4: my grep of `activejob-8.1.4/lib/active_job/queue_adapters/*.rb` for `def activating` and `def queues` returned no lines. The expected failure is `NoMethodError` on the first request, but treat that as inferred from the code, not executed.
- **Fix.** Set `config.mission_control.jobs.adapters = [ :solid_queue ]`. Retask does exactly this at `config/application.rb:75`. Its comment at `:71-74` states that the dashboard reads Solid Queue in every environment, with `:test` in specs and `:async` in development. That setting passes the first condition of `adapters.empty?`, so the default is not applied, and it prepends `SolidQueueExt` so Solid Queue's tables are read. `config/environments/production.rb:68` has `config.active_job.queue_adapter = :solid_queue`.
- **Statement exactly true for 1.3.1:** `adapters` defaults to `[config.active_job.queue_adapter || :async]` (`engine.rb:33`). SolidQueueExt is prepended only when `:solid_queue` is listed (`engine.rb:64`). With an app adapter of `:async` and a list that does not name `:solid_queue`, the dashboard renders but is permanently empty (`async_ext.rb`). Setting `config.mission_control.jobs.adapters = [:solid_queue]` makes it read Solid Queue's tables whatever adapter runs the jobs.

**X1: "mount it behind admin auth like any ops surface" is misleading for the default setup.** The default engine does not sit behind the app's admin auth. It demands its own HTTP basic credentials and returns 401 without them (`basic_authentication.rb:9-17`). Doctrine should say "set credentials via `bin/rails mission_control:jobs:authentication:configure` (README:66-75), or set `base_controller_class` AND `http_basic_auth_enabled = false`". The "like any ops surface" sentence also misses that the `base_controller_class` approach puts host-controller code inside the engine (README:106), with the route helper precedence caveat noted under X4.

**X2: The mount example `mount MissionControl::Jobs::Engine, at: "/jobs"` is correct.** It matches README:19-24 exactly. Retask mounts at `/system-health/jobs` with `as: :system_health_jobs` (`config/routes.rb:602`). The engine's own routes live at `/applications/:id/...` and `/:status/jobs` (`config/routes.rb`).

**X3: The route-constraint alternative is missing.** README:108-121 documents a second authentication approach: wrap `mount` in a `constraints` lambda (README:115-117), with "disable HTTP Basic Authentication if you don't want both" (README:121). The doctrine's current §8 text names only `base_controller_class`.

**X4: Route-helper precedence and "Back to main app".**
- README:106 says the base controller's code runs inside the engine, whose route helpers take precedence. Helpers that both apps define (for example `root_path`) resolve to the engine's, so a host `before_action` that redirects needs `main_app.root_path`. Helpers only the host defines (for example `new_session_path` from the Rails 8 authentication generator) still work.
- README:133 documents `back_to_main_app_path` as optional.
- Retask works around this with `MissionControl::Jobs::HostRouteHelpers` (`jobs_base_controller.rb:33`).
- This is relevant to the doctrine's claim that the Rails 8 authentication generator has no `authenticate` route helper (`jobs-and-realtime.md:115-116`), which I did not verify.

**X5: Credentials and the generator are not mentioned.** The doctrine's "ships ... closed" sentence omits that the default is closed until credentials exist. The ways to set them are the `bin/rails mission_control:jobs:authentication:configure` generator, the `mission_control.http_basic_auth_user` and `http_basic_auth_password` keys in Rails credentials (README:59-64), or `MissionControl::Jobs.http_basic_auth_user =` and `http_basic_auth_password =` (README:77-84). The credentials keys are read at boot with `||=` (`engine.rb:43-46`).

**Other points on §8 (`ecosystem-gems.md` lines 268-292):**
- Line 285 says "(1.3.1)" and "ships with HTTP basic auth **enabled and closed**". This matches README:59 for the installed version. The same sentence appears at `jobs-and-realtime.md:112-113`, "unreachable until you set credentials".
- The sentence "To admit your admins instead, set `config.mission_control.jobs.base_controller_class = "AdminController"`" at lines 286-288 is incomplete (see M1).
- The `jobs-and-realtime.md:114-116` variant ("point `base_controller_class` at your authenticated admin controller") has the same gap.
