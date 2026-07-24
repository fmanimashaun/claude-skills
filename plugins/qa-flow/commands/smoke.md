---
description: Launch the app (stack-aware) and confirm it actually BOOTS and its key routes respond, before any deeper QA. A fast liveness/smoke gate that fails loudly if the build won't come up. Free — the app's own server + curl, no paid tooling.
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
     boot_timeout: 60           # seconds to wait for health before failing
   ```
   No `app:` block? Infer the Rails default (`bin/dev`, port 3000, `/up`) and say so.

2. **Launch in a test env, backgrounded**, capturing PID + logs; **always trap teardown** so a
   failed run never leaks a server:
   ```bash
   RAILS_ENV="${RAILS_ENV:-test}" <start> > qa/reports/smoke-boot.log 2>&1 &
   APP_PID=$!; trap 'kill "$APP_PID" 2>/dev/null' EXIT
   ```
   Use the app's own server — no paid tooling. Prefer a dedicated test/QA env; never a prod DB.

3. **Wait for health** — poll `http://localhost:<port><health>` until HTTP 200 or `boot_timeout`:
   ```bash
   up=0; for i in $(seq 1 <boot_timeout>); do
     curl -fsS -o /dev/null "http://localhost:<port><health>" && { up=1; break; }; sleep 1; done
   ```
   Never came up → **FAIL: "app did not boot within <n>s."** Print the tail of
   `qa/reports/smoke-boot.log` (the real error) and STOP — this is the "build not testable" signal.

4. **Hit the key routes** — for each in `app.routes`, capture the status; **5xx = FAIL**, 2xx/3xx
   pass, 4xx noted:
   ```bash
   curl -s -o /dev/null -w "%{http_code}" "http://localhost:<port><route>"
   ```

5. **Export the base URL** for the phases that follow: `QA_BASE_URL=http://localhost:<port>`.

6. **Report** a small table (route · status · pass/fail) + verdict, then **tear the app down**
   (the trap handles it). On FAIL, do **not** proceed to functional/e2e — report and let the
   breakage be filed as `qa,from-qa,severity:s1` (same contract as verify's smoke gate).

## Where it fits (build loop)

```
/qa-flow:smoke  →  /qa-flow:functional  or  /qa-flow:verify
(boots + liveness,     (reuse QA_BASE_URL; the full @smoke E2E + regression build on a proven-up app)
 sets QA_BASE_URL)
```

This is the concrete boot that `/qa-flow:verify` Phase 0 assumes, and the fast pre-check before
the heavier Playwright `@smoke` set. Stack-agnostic: only the `app:` config differs per stack;
the launch → health → routes → teardown procedure stays the same. Free by default.
