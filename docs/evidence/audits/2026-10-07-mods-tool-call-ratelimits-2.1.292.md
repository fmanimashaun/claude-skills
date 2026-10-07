# Mods API for budget-guard (#1676, #1677): Claude Code 2.1.292

Excerpts from the engine's own type declaration, `claude-code.d.ts`, written by Claude Code 2.1.292 and shipped with its plugin-authoring skill. sha256 `06d8cf21493d10bfd3c6d321d6312d8c783869b348ee4643426562b714cb4fca`. Taken 2026-10-07 by the coordinator. Each block notes the line range it comes from, and `// ...` marks a gap between non-adjacent ranges.

Other sources:
- https://code.claude.com/docs/en/hooks: PreToolUse fires "on every tool call inside the agentic loop", and can deny. No hook input carries rate limits.
- https://code.claude.com/docs/en/statusline: `rate_limits` "appears only for claude.ai Pro and Max subscribers, or behind a Claude apps gateway that sets a spend limit for you, and only after the first API response in the session." There, `resets_at` is epoch seconds; in a mod, `resetsAt` is ISO 8601.
- Claude Code CHANGELOG 2.1.287: "Added Claude Mods: plugins may now modify deeper behavior". That is the floor. Whether `tool.call` existed at 2.1.287 is not stated (it is first named at 2.1.290), so this was developed and verified against 2.1.292.

## A tool.call hook refuses with `{ deny }`, and a guard that fails is skipped
```ts
// ... claude-code.d.ts lines 3905-3927
   * The events the engine raises at its call sites, and `engine.create`; the
   * classic settings hooks' events are ClassicEventOf.
   *
   * At every one, a hook that fails (throws, overruns its budget: HookBudget,
   * answers a wrong shape) is skipped: the hooks beneath and core run in its
   * place, or its last `next` result stands; the failure is reported by name.
   *
   * @remarks So a guard fails open unless its registration carries a `.catch`
   *   (Registration) that refuses in its place, at any event an answer refuses.
   */
  export type EngineEventOf = {
      /**
       * Fires when the engine is about to run a tool. Each `next(e)` runs the
       * hooks beneath, then core (the permission prompt, the tool itself).
       *
       * `{ deny: reason }` refuses and `{ result }` answers in place of `next`: a
       * deny after `next(e)` resolved undoes nothing it ran; returning with `next`
       * pending aborts what runs beneath. Managed-settings hooks' deny comes first.
       *
       * @remarks A guard that fails is skipped and the tool runs, so give it
       *   `.catch(($, e, next) => next.called ? next(e) : { deny: "no" })`.
       */
      'tool.call': ToolCallInput;
// ... claude-code.d.ts lines 12597-12650
   * of which the tool sees (the engine strips them before the tool runs).
   *
   * `consent` is the person's own words for the press that raised the call
   * (`The user pressed "1: Yes" on ...`): the run's context carries it as a human
   * turn, which the permission path reads as the user's request.
   */
  export type ToolCallReserved<T> = {
      tool: T;
      tool_use_id?: string;
      consent?: string;
  };

  /**
   * What a `tool.call` hook returns and what `next(e)` and `$.tool.call(input)`
   * resolve to: the tool's result (`{ result, context? }`) or `{ deny }`.
   *
   * From core the result is `{ ref, result, text }` or, when the tool reported
   * an error, `{ ref, result, text, isError }`, either with `isReadOnly` when
   * the tool held the input it ran read-only; `ref` names core's messages.
   *
   * @template Name the tool the call went to, typing `result` per built-in
   *   tool (BuiltinToolResults) once `e.tool` is narrowed; else `unknown`
   */
  export type ToolCallResult<Name extends string = string> = {
      /**
       * Refuses the call: the model receives the text as an error result.
       * Absent when the call was answered.
       *
       * Returned after `next(e)` was answered it undoes nothing: a tool that
       * ran has run, the deny is still the call's answer, and the debug log
       * names the plugin that denied.
       */
      deny: string;
      result?: undefined;
      context?: undefined;
      ref?: undefined;
      text?: undefined;
      isError?: undefined;
      isReadOnly?: undefined;
  } | {
      /**
       * The tool's output: from core the tool's record, typed per built-in
       * tool once `e.tool` and `isError` are narrowed; from a hook, its own.
       *
       * Core validates a hook's answer against the tool's output schema when
       * it has one, maps it for the model with the tool's own mapper, and
       * records it in the transcript as the tool's result. Absent on a deny.
       */
      result: ToolResultOf<Name>;
      /**
       * What the model reads after the tool's result and the user never
       * sees. From core, none.
       *
       * One reminder, as a PostToolUse hook's is, after the managed tier's
```

## `$.session.usage()` returns the rate-limit windows
```ts
// ... claude-code.d.ts lines 2797-2809
          /**
           * Returns when the session began, and the context window's fill, the
           * rate-limit windows and the cost as the status line has them, itemized.
           *
           * The plain call costs nothing; `"full"` counts each category with the
           * token-count API as /context does, `"summary"` estimates locally, and
           * `context.breakdown` comes back in the SDK's `get_context_usage` shape.
           *
           * @param args `{ breakdown, columns }`: how the breakdown is counted and
           *   the width its grid is drawn in; nothing for the status line's figures
           * @returns `{ startedAt, context, rateLimits, cost }` as the status line
           *   has them
           * @example
```

## `session.measure` pushes them
```ts
// ... claude-code.d.ts lines 4374-4384
      /**
       * Fires when the engine measures the session and a unit moved: after each
       * main-thread turn, and when a rate-limit window moves a whole point.
       *
       * Observe; `next(e)` echoes `{ changed }`. `$.session.usage()`'s figures,
       * pushed, not polled: compare them with your own threshold here, call the
       * op for the breakdown. One at a time, a burst folding into one more.
       *
       * @example
       * on("session.measure", ($, e, next) => (toastPast90(e.rateLimits), next(e)))
       */
// ... claude-code.d.ts lines 11028-11045
       * The rate-limit windows the last response reported, each with its
       * `percentUsed`; empty off a subscription or before the first reading.
       */
      rateLimits: SessionRateLimit[];
      /**
       * What the session has cost so far; absent where the host keeps no ledger.
       */
      cost?: SessionCost;
      /**
       * Which units differ from the last measurement raised (UsageUnit), never
       * empty; the first measurement names every unit it has a figure for.
       *
       * `context`: the fill moved; `rateLimits`: a window moved a whole point,
       * appeared or left, or the account's limit status changed; `cost`: the
       * total grew.
       */
      changed: UsageUnit[];
  };
```

## One window
```ts
// ... claude-code.d.ts lines 11203-11222
  /**
   * One rate-limit window as the rate-limit notices read it.
   */
  export type SessionRateLimit = {
      /**
       * Which window: `five_hour`, `seven_day`, or a Claude gateway's
       * `spend_limit`.
       */
      kind: string;
      /**
       * How much of the window is used, 0 to 100 with at most one decimal:
       * 23.5, or 7, never 7.000000000000001; past 100 on an exceeded spend limit.
       */
      percentUsed: number;
      /**
       * When the window resets, as an ISO 8601 timestamp.
       */
      resetsAt?: string;
  };

```

## The Workflow tool input carries the script (optional)
```ts
    Workflow: {
      /** Self-contained workflow script. Must begin with `export const meta = { name, description, phases }` (pure literal, no computed values) followed by the script body using agent()/parallel()/pipeline()/phase(). */
      script?: string
      /** Name of a predefined workflow (built-in or from .claude/workflows/). Resolves to a self-contained script. */
      name?: string
      /** Ignored — set the workflow description in the script's `meta` block. */
      description?: string
      /** Ignored — set the workflow title in the script's `meta` block. */
      title?: string
      /** Optional input value exposed to the script as the global `args`, verbatim. Pass arrays/objects as actual JSON values, NOT as a JSON-encoded string — a stringified list breaks `args.filter`/`args.map` in the scr
      args?: unknown
      /** Path to a workflow script file on disk. Every Workflow invocation persists its script under the session directory and returns the path in the tool result. To iterate, edit that file with Write/Edit and re-invok
      scriptPath?: string
      /** Run ID of a prior Workflow invocation to resume from. Completed agent() calls with unchanged (prompt, opts) return their cached results instantly; only edited or new calls re-run. Same-session only. Stop the pr
```

## Timers (`$.clock`) and a prompt from a mod (`$.prompt.submit`), for the 5-hour resume
```ts
// ... claude-code.d.ts lines 3391-3440
       * The time and timers, each an event through the host: `clock.now` reads
       * the time; `clock.sleep`, `after` and `every` wait until it has passed.
       *
       * A timer's callback is the plugin's own function, kept in its environment
       * and run there when the wait resolves; a hot reload of the plugin cancels
       * its pending waits with the old environment.
       */
      clock: {
          /**
           * Resolves milliseconds since the epoch, now.
           *
           * @example
           * const startedAt = await $.clock.now()
           */
          now: () => Promise<number>;
          /**
           * Resolves after `ms` milliseconds; rejects at once when `signal` aborts.
           *
           * The wait is the hook's own time and its budget runs on through it, as
           * through no other `$` call: a `turn.step` generator that polls with it
           * pays every sleep out of its one budget (`next.budget.remainingMs`).
           *
           * @param ms how long, in milliseconds
           * @param options `signal`: ends the wait early with a rejection (pass
           *   `next.signal` so a hook's wait ends with its dispatch)
           * @example
           * await $.clock.sleep(500, { signal: next.signal })
           */
          sleep: (ms: number, options?: SleepOptions) => Promise<void>;
          /**
           * Calls `fn` once after `ms` milliseconds; `cancel()` before then stops it.
           *
           * One `clock.after` dispatch: `fn` runs when it resolves, and never when
           * a hook refuses it.
           */
          after: TimerCall;
          /**
           * Calls `fn` every `ms` milliseconds (at least 1) until `cancel()`.
           *
           * One `clock.every` dispatch per period: `fn` runs when it resolves and
           * the next period is asked; a refused period ends the interval.
           *
           * @example
           * const tick = $.clock.every(1000, () => $.ui.status("polling"))
           */
          every: TimerCall;
      };
      /**
       * The network, through the host.
       */
// ... claude-code.d.ts lines 12546-12546
  export type TimerCall = (ms: number, fn: () => void) => Timer;
// ... claude-code.d.ts lines 2909-2921
      prompt: {
          /**
           * Submits a prompt: the event `prompt.submit`, the same call the engine
           * makes for a typed prompt; a turn of its own, once the session is idle.
           *
           * It goes through every hook but the calling one (the plugin's others
           * see it) with `e.origin` `{ kind: 'plugin', name }`, the name the
           * model reads it under unless a hook leaves it out of its answer.
           *
           * @example
           * void $.prompt.submit({ text: "List the TODOs you just mentioned." })
           */
          submit: EventCalls['prompt']['submit'];
```

## `$.env.get` takes a literal name
```ts
// ... claude-code.d.ts lines 3555-3570
       *
       * `get` and `set` take the variable's name as a string literal, so what a
       * module reads and writes is read off its source: `claude plugin validate`
       * lists the names, and a name the module does not spell is refused.
       */
      env: {
          /**
           * Resolves with the variable's value, or `undefined` when it is unset.
           *
           * `name` must be a string literal; `claude plugin validate` lists the
           * names your module reads and writes.
           *
           * @example
           * const home = await $.env.get("HOME")
           */
          get: (name: string) => Promise<string | undefined>;
```
