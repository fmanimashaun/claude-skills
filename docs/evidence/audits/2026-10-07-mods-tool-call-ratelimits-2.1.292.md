# Mods API for budget-guard (#1676, #1677): Claude Code 2.1.292

Excerpts from the engine's own type declaration, `claude-code.d.ts`, written by Claude Code 2.1.292 and shipped with its plugin-authoring skill. sha256 `06d8cf21493d10bfd3c6d321d6312d8c783869b348ee4643426562b714cb4fca`. Taken 2026-10-07 by the coordinator. The website's hooks reference (https://code.claude.com/docs/en/hooks) separately documents PreToolUse denial for every tool, and documents no rate-limit field in any hook input. The status line page (https://code.claude.com/docs/en/statusline) documents `rate_limits.five_hour` and `rate_limits.seven_day` with `used_percentage` and `resets_at`, which "appears only for claude.ai Pro and Max subscribers, or behind a Claude apps gateway that sets a spend limit for you, and only after the first API response in the session."

## A tool.call hook refuses with `{ deny }`, and a guard that fails is skipped

budget-guard decides the relay refusal before any `await`, so no failure can skip it. The usage refusal reads `$.session.usage()`; if that fails, the guard is skipped and the call runs, failing open, which is the intended behaviour for an advisory budget limit.

```ts
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

## The Workflow tool input carries the script
```ts
    Workflow: {
      /** Self-contained workflow script. Must begin with `export const meta = { name, description, phases }` (pure literal, no computed values) followed by the script body using agent()/parallel()/pi
      script?: string
      /** Name of a predefined workflow (built-in or from .claude/workflows/). Resolves to a self-contained script. */
      name?: string
      /** Ignored — set the workflow description in the script's `meta` block. */
      description?: string
      /** Ignored — set the workflow title in the script's `meta` block. */
      title?: string
      /** Optional input value exposed to the script as the global `args`, verbatim. Pass arrays/objects as actual JSON values, NOT as a JSON-encoded string — a stringified list breaks `args.filter`/`
      args?: unknown
      /** Path to a workflow script file on disk. Every Workflow invocation persists its script under the session directory and returns the path in the tool result. To iterate, edit that file with Wri
      scriptPath?: string
      /** Run ID of a prior Workflow invocation to resume from. Completed agent() calls with unchanged (prompt, opts) return their cached results instantly; only edited or new calls re-run. Same-sessi
```
