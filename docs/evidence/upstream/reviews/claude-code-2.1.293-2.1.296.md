# Claude Code upstream review: 2.1.293 to 2.1.296

_Reviewed 2026-10-12 for #1938 · CLI 2.1.296 · no `[quote-gone]` rows._

**Scope, stated exactly.** `scripts/check_upstream_docs.py` listed **150** unreviewed entries past 2.1.292 (the cursor). All 150 were read against the surfaces we ship: the 21 command hooks in `plugins/*/hooks/hooks.json` (only `type` and `timeout`), the four mods in `plugins/rails-flow/hooks/` (`lane-band.js`, `budget-guard.mjs`, `context-nudge.mjs`, `session-reset.mjs`), 31 agents (frontmatter keys `name`, `model`, `description`, `tools`), the `CLAUDE_ENV_FILE` write in `session-start.sh`, and no `prompt`, `agent` or `http` hooks. The per-item verdicts are on #1938 (comment 6127513461).

**Result.** 1 issue filed, no doctrine edited by this review:

| issue | finding |
|---|---|
| #1939 | 2.1.295 `onFailure: "block"` on a command hook: a gate that cannot start, crashes or times out was a non-blocking error. doctrine-verifier CONFIRMED the field, values, effect and the v2.1.295 floor; plugin-file support and older-version behaviour were measured (2.1.296 accepts it in a plugin's `hooks/hooks.json` and refuses the call; 2.1.292 ignores it). Built on its own branch. |

**Checked, no effect on what we ship or say:** the `CLAUDE_ENV_FILE` fixes (our git-shim PATH line only benefits), the `prompt.submit` and nested-input mod fixes (our mods add one context line and read shallow input), the `$.agent.register` and served-`$` fixes (not called), `claude plugin validate` and `test` changes (our install-line lint already holds), the 32-skill preload cap and `autoCompactWindow` (no `skills:` field and no non-standard key in our agents; `check_frontmatter.py` holds no agent field allowlist), the MCP description limits (we state no such number), and the Bash permission fixes (`guard-bash.sh` claims no parity with Claude Code's own checks). The rest (Claude Tag, VS Code, Windows, gateway and managed settings, cloud and self-hosted runners, telemetry and retry settings) are surfaces we do not use.

**Not adopted, by decision:** `$.ui.notify` and `CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL` are capabilities; adopting either is a design or spend decision with no demand on record, so no issue was filed.

**Open points.** The bucket counts on #1938 and the "no effect" verdicts come from greps of our own files and reading the entries, not from running every changed behaviour; only `onFailure` was driven end to end.
