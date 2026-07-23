---
description: Report toolchain friction (a rails-flow/qa-flow/pipeline/rails-stack bug, wrong guidance, or feature idea) upstream as a structured, deduped, version-pinned issue. Drafts by default; add "MODE: FILE" to actually file.
argument-hint: "<observation>  [MODE: FILE]"
---

# /rails-flow:report — $ARGUMENTS

Turn friction you hit while USING the toolchain into a high-signal upstream issue. Delegate
to the **claude-skills-reporter** agent — one delegated step, no context switch.

## Run

Hand `$ARGUMENTS` to the `claude-skills-reporter` agent. It will:

1. **Scope-check** — toolchain-only. If the observation is about your own app, it refuses
   and points you to your own tracker.
2. **Pin versions** — marketplace + plugin version (and running-vs-latest delta) from the
   local marketplace clone / plugin state.
3. **Gather evidence** — `file:line` + minimal repro for a bug; motivation + acceptance
   criteria for a feature; classify with `type:*` / `comp:*` labels.
4. **Dedup** — search open + closed issues; if it already exists, propose a comment
   (open) or flag a regression (closed) instead of filing.
5. **Draft or file** — by default it returns the draft and stops. Include **`MODE: FILE`**
   in the arguments to actually open the issue (needs `gh` authenticated); it uses
   `gh issue create --body-file` and returns the URL.

## Examples

- `/rails-flow:report the qa-flow release-gate blocked a plain commit whose message mentioned "gh pr merge"`
- `/rails-flow:report setup-flow should scaffold a CODEOWNERS file    MODE: FILE`

Default is a draft you review; nothing is filed without `MODE: FILE`.
