---
description: Reuse a running server or launch the app (stack-aware), then confirm it actually BOOTS and its key routes respond, before any deeper QA. Separate boot and per-route timeouts, and boot failures are classified by category (port in use, dependency, runtime mismatch, framework policy, app error) rather than dumped as a log. A fast liveness/smoke gate that fails loudly if the build won't come up. Free — the app's own server + curl, no paid tooling.
argument-hint: "[optional base URL to liveness-check instead of launching]"
---

# /qa-flow:smoke — $ARGUMENTS

The build-verification **floor**: *does the app boot, and do its key routes respond?* Green unit
tests don't prove the app comes up — a bad initializer, missing env var, broken asset build, or a
bad migration can pass specs and still 500 on boot. Run this **first** (before
`/qa-flow:functional`, before verify's deeper phases) so "the build isn't testable" is caught in
seconds, not halfway through a suite.

Prereq: `qa/qa.config.yml` (run `/qa-flow:setup-qa` if absent). If `$ARGUMENTS` is a URL, **skip
launching** and just liveness-check that URL (an already-running or staging target).

## Procedure

1. **Read the launch config** — `qa/qa.config.yml` `app:` (stack-agnostic; Rails defaults shown):
   ```yaml
   app:
     start:        bin/dev      # boot command (may be `bin/rails server -p 3000`)
     port:         3000
     health:       /up          # 200-when-ready route (Rails 8 ships this health endpoint)
     routes:       [/, /up]     # key routes to hit
     boot_timeout:  60          # seconds for the SERVER to answer <health> at all
     route_timeout: 90          # seconds for the FIRST hit of any one route
   ```
   No `app:` block? Infer the Rails default (`bin/dev`, port 3000, `/up`) and say so.

   **The two timeouts are not interchangeable.** `boot_timeout` covers the server coming up;
   `route_timeout` covers first-hit-per-route, because dev servers compile on demand. A
   Next.js + Turbopack app reported "Ready in 10s" then spent **45–60s compiling each route on
   first visit** — with one timeout for both, the crawl clears boot and dies on route 2, which
   reads as a broken app instead of a slow compile.

2. **Probe before you launch — never start a second server.** If the port already answers,
   reuse it and say so:
   ```bash
   if curl -fsS -o /dev/null --max-time 5 "http://localhost:<port><health>"; then
     REUSED=1; echo "reusing the server already on <port> — not launching a second"
   fi
   ```
   Two dev servers against one project directory contend over the same build cache
   (`.next/`, `tmp/cache`) and can corrupt it. A reused server is also **not yours to kill**:
   skip teardown for it, and say in the report that the app was already running, since it may
   be running different code than the working tree.

3. **Otherwise launch in a test env, backgrounded**, capturing PID + logs; **always trap
   teardown** so a failed run never leaks a server:
   ```bash
   RAILS_ENV="${RAILS_ENV:-test}" <start> > qa/reports/smoke-boot.log 2>&1 &
   APP_PID=$!; trap 'kill "$APP_PID" 2>/dev/null' EXIT
   ```
   Use the app's own server — no paid tooling. Prefer a dedicated test/QA env; never a prod DB.

   **Check for prebuilt assets before running a heavy build.** If the documented start command
   chains a bundler (`npm start` = framework + webpack) and the built output is already present
   and newer than its sources, the lighter server-only command serves fully-styled pages. Say
   which path you took and why — an audited project already had `static/app.css`, so
   `hugo server` alone was enough and a naive runner would have failed on webpack and given up.
   Never silently skip a documented step: state the assumption so a stale-asset false pass is
   attributable.

4. **Wait for health** — poll `http://localhost:<port><health>` until HTTP 200 or `boot_timeout`.
   Poll; never `sleep` a fixed guess:
   ```bash
   up=0; for i in $(seq 1 <boot_timeout>); do
     curl -fsS -o /dev/null "http://localhost:<port><health>" && { up=1; break; }; sleep 1; done
   ```
   Never came up → **FAIL: "app did not boot within <n>s."** Print the tail of
   `qa/reports/smoke-boot.log` and **classify it per the triage table below** — STOP. This is the
   "build not testable" signal.

5. **Hit the key routes** — for each in `app.routes`, capture the status, allowing
   `route_timeout` for the first hit; **5xx = FAIL**, 2xx/3xx pass, 4xx noted:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" --max-time <route_timeout> "http://localhost:<port><route>"
   ```
   A route that exceeds `route_timeout` is **FAIL: "route did not respond within <n>s"** — report
   it as a route failure, distinct from a boot failure, so a slow first compile is not filed as a
   dead app.

6. **Export the base URL** for the phases that follow: `QA_BASE_URL=http://localhost:<port>`.

7. **Report** a small table (route · status · pass/fail) + verdict, then **tear the app down**
   (the trap handles it — **unless you reused an existing server**, which you must leave
   running). On FAIL, do **not** proceed to functional/e2e — report and let the breakage be
   filed as `qa,from-qa,severity:s1` (same contract as verify's smoke gate).

## Boot-error triage — report the category, not just the log

A wall of stack trace is not a diagnosis, and the categories below have genuinely different
owners. Classify the failure and give the tail; guessing a fix is worse than naming the class.

| Category | How it looks in the log | Next action |
|---|---|---|
| **Port already in use** | `EADDRINUSE`, `Address already in use` | re-run the step-2 probe — something answers on that port; reuse it or pick another |
| **Missing / incompatible dependency** | `Module not found`, `Cannot find module`, `ERR_PACKAGE_PATH_NOT_EXPORTED` | install, or the package's `exports` map does not expose that subpath — a dependency bug, not yours |
| **Runtime / engine mismatch** | `NODE_MODULE_VERSION`, unsupported engine, native ABI errors, a global the runtime injected | check the required runtime version against the installed one |
| **Framework security / config policy** | a policy or security block that never says "set this env var" | consult the gotcha table below; the framework is refusing, not crashing |
| **Application error** | anything else — bad initializer, missing env var, failed migration | the real defect; file it |

**Never report "the app did not boot" alone.** Name the category, attach the log tail, and say
what you tried. An unclassified boot failure sends a developer to read the same wall of output
you just read.

### Known gotchas (extend per stack as they are found)

These read as application breakage and are not. Seeded from a real audit; add to it rather than
re-diagnosing from scratch.

| Stack | Symptom | Cause / fix |
|---|---|---|
| **Hugo ≥ 0.158** | boot fails with a wall of security-policy output that never mentions an env var | raw `.html` content is refused by default — needs `HUGO_SECURITY_ALLOWCONTENT='.*'` |
| **Node 25** | SSR breaks on `localStorage.getItem is not a function` | Node injects a global `localStorage`; server-side code that feature-detects it now finds it and calls it |
| **npm packages with an `exports` map** | a CSS/asset subpath import is unresolvable even though the file exists on disk | the package does not export `dist/*`; import a path it does export, or copy the asset |
| **Next.js / Turbopack** | boot succeeds, then route 2 times out | per-route first-hit compilation — that is `route_timeout`, not a hang |

## Where it fits (build loop)

```
/qa-flow:smoke  →  /qa-flow:functional  or  /qa-flow:verify
(boots + liveness,     (reuse QA_BASE_URL; the full @smoke E2E + regression build on a proven-up app)
 sets QA_BASE_URL)
```

This is the concrete boot that `/qa-flow:verify` Phase 0 assumes, and the fast pre-check before
the heavier Playwright `@smoke` set. Stack-agnostic: only the `app:` config differs per stack;
the launch → health → routes → teardown procedure stays the same. Free by default.
