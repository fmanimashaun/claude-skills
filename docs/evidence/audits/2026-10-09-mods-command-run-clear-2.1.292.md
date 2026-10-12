# Mods API for session-reset (#1687, #1723, #1724): Claude Code 2.1.292 declaration, 2.1.293 measured

Excerpts from the engine's own type declaration, `claude-code.d.ts` (`index.d.ts` in a dev-mods copy), written by
Claude Code **2.1.292**. sha256 `98acac69b7fdffc40a1c66fd23b4c75917d79ffb7c6ac06b78e6f00f32750d54`, 15776 lines. Taken 2026-10-09
from `~/.claude/dev-mods/*/budget-guard/.claude-plugin/types/claude-code/index.d.ts`. Each block names the lines it comes from.

**Version boundary.** The scope is Claude Code 2.1.295, where the coordinator checked that there is no `clear` API
other than the one below. **No 2.1.295 declaration was read**: the newest on this machine is 2.1.292's, and the CLI
that ran the checks (`claude plugin validate`, `claude plugin test`, `claude -p --plugin-dir`) is 2.1.293. Re-check
these lines when a newer declaration is available.

**Measured, not quoted** (2.1.293, `claude -p --plugin-dir <probe plugin>` with a `turn.complete` mod):
- the shell `$.process.run(['sh','-c',...])` starts has the `claude` process as `$PPID` (`ps` named it `claude`), so `$PPID` is the session's pid;
- `$.session.surfaces()` was `[]` under `-p`, and `$.session.id()` returned a UUID;
- the module loader refuses `$.session.id` used as a value: `$` is "always spelled `$.noun.event(...)` at the call site";
- `claude plugin validate plugins/rails-flow` lists `session.start{isInteractive=true}` beside lane-band's unmatched `session.start`, and passes.

## `$.command.run` queues a slash command, and rejects inside a hook the turn is waiting on
Supports: the clear is requested from a timer, as `command: "clear"`; `list` covers built-in commands.
```ts
// claude-code.d.ts lines 3025-3050
      /**
       * The slash commands the person can run in this session, and running one.
       */
      command: {
          /**
           * Returns the slash commands the person can run now, built-in, plugin
           * and MCP alike, in the order the typeahead lists them.
           *
           * @example
           * const names = (await $.command.list()).map(c => c.name)
           */
          list: () => Promise<CommandInfo[]>;
          /**
           * Runs a slash command as if the person typed `/command args`: the
           * event `command.run`, queued and run once the session is idle.
           *
           * It runs through every hook but the calling one with `e.origin`
           * `{ kind: 'plugin', name }`, its lines in the transcript. Rejects an
           * unknown name, and inside a hook the turn is waiting on.
           *
           * @example
           * const { text } = await $.command.run({ command: "status" })
           */
          run: EventCalls['command']['run'];
          /**
           * Declares the slash command `/<name>` for this session, listed in the
```

## `$.prompt.submit` runs once the session is idle
Supports: the one prompt after the clear.
```ts
// claude-code.d.ts lines 2905-2920
      /**
       * Submitting a prompt the model reads as a user turn, and the person's
       * prompt box: read as it stands, written, or proposed into.
       */
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
```

## `$.session.compact` between turns, rejects while a turn runs
Supports: the mid-job and coordinator compaction, retried at the next measure.
```ts
// claude-code.d.ts lines 2837-2847
           * Compacts the conversation: the event `session.compact` with `trigger`
           * `plugin`, the same call `/compact` makes, between turns.
           *
           * It runs through every hook but the calling one, then core: a summary
           * and the kept messages in the transcript's place. Resolves `{ skip }`
           * when a hook vetoed it; rejects while a turn runs.
           *
           * @example
           * const { skip } = await $.session.compact({ instructions: "the plan" })
           */
          compact: EventCalls['session']['compact'];
```

## `$.session.surfaces()` is empty in a `-p` run
Supports: a `claude -p` run is never reset.
```ts
// claude-code.d.ts lines 2777-2788
          /**
           * Returns every surface the session draws on, each once: `terminal` under
           * the REPL first, then the remote ones in the order they attached.
           *
           * A session may draw on several at once (a terminal and two phones):
           * clients attach (`session.attach`) and detach, and a render hook still
           * reads `e.surface` per ask. Empty in a plain -p run; never rejects.
           *
           * @example
           * const inApp = (await $.session.surfaces()).some(s => s !== "terminal")
           */
          surfaces: () => Promise<readonly RenderSurface[]>;
```

## `session.start` does not fire for `/clear`
Supports: module variables, and so the role, survive a clear.
```ts
// claude-code.d.ts lines 4294-4306
      /**
       * Fires once per process for each loaded plugin, before the first prompt,
       * then once per fresh load of one (never `/clear`); `next(e)` is `{ cwd }`.
       *
       * Observe. The first is awaited: a `$.tool.register` is listed by turn one.
       * A later one runs its hooks alone: an enable, a worker respawn, or a reload
       * (changed modules only; all if one hooks `engine.create`/`plugin.register`).
       *
       * @example
       * on("session.start", ($, e, next) => $.tool.register(t).then(() => next(e)))
       */
      'session.start': SessionStartInput;
      /**
```

## `session.end` reason `clear`: the process goes on under a new session id
Supports: the same, from the other side.
```ts
// claude-code.d.ts lines 10973-10981
  export type SessionEndInput = {
      /**
       * Why it ends (SessionEndReason), the word the classic SessionEnd hook
       * receives as its `reason`.
       *
       * `clear` is how a hook sees a `/clear`: the conversation ends, the process
       * goes on under a new session id, and no `session.start` fires for it.
       */
      reason: SessionEndReason;
```

## `$.clock.after`
Supports: the timer the clear and the compaction are requested from.
```ts
// claude-code.d.ts lines 3420-3426
          /**
           * Calls `fn` once after `ms` milliseconds; `cancel()` before then stops it.
           *
           * One `clock.after` dispatch: `fn` runs when it resolves, and never when
           * a hook refuses it.
           */
          after: TimerCall;
```
