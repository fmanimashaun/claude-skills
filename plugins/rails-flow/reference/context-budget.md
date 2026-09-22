# Context budget — what gets injected, and how often you pay for it

The decision record behind `scripts/check_hook_output_budget.py` and the shape of
`hooks/scripts/session-start.sh`. Filed as [#1085](https://github.com/fmanimashaun/claude-skills/issues/1085).

Every other cost in this toolchain is measured and gated. This one was not measured at all:

```
grep -rn --include='*.md' -iE '/compact|compact the context|context window' plugins/ skills/
  -> one hit, about RubyLLM's model registry
```

## The fact that changes the arithmetic

**A `SessionStart` hook does not run once per session. It runs again after every compaction.**

That inverts the intuition. A hook feels like a fixed startup cost, so 4 KB reads as cheap. But a
compaction exists to reclaim a context window that ran out — and the hook fires into the fresh
window, spending part of what was just reclaimed, before any work happens. The longer the session,
the more times you pay, and the payments land at the worst possible moments.

Measured on this repository the first time anyone looked:

| hook | bytes per fire |
|---|---|
| `plugins/rails-flow/hooks/scripts/session-start.sh` | **4451** |
| `.claude/hooks/scripts/maintainer-status.sh` | 100 |
| `plugins/qa-flow/hooks/scripts/qa-status.sh` | 0 |
| `plugins/pipeline/hooks/scripts/pipeline-status.sh` | 0 |

One hook was 98% of the cost. Of its 4451 bytes, **3805 were `docs/brain/MEMORY.md` printed
verbatim**, and **42% of that block was `[slug](path)` markdown** — link scaffolding no model acts
on, repeated once per lesson, re-injected at every compaction.

## The rule

**Apply the harness-doctrine test to every line a hook prints: if a model ignores this line, what
happens?**

- A lesson — *"the Bash tool runs zsh; an unquoted `$var` is one word"* — changes what the model
  does. It earns its bytes.
- The path that lesson lives at does not. Nobody opens it from the banner; it is one `grep` away
  when it is wanted.
- A count plus a pointer beats a list. *"17 lessons; `/rails-flow:brain` for the rest"* preserves
  discoverability at a fixed cost, where the list grows without bound.

Stripping the scaffolding took `session-start.sh` from 4451 to about 2000 bytes with **no
actionable content removed** — the lesson text is printed in full. That is the shape to aim for:
cut the packaging, never the substance.

## Gate it as a ratchet, never a threshold

`scripts/check_hook_output_budget.py` records what each hook costs today and fails on growth.

A fixed byte limit is the wrong instrument here, for the reason this repository has hit before: set
above today's size it is inert and never fires; set below it, it is red on day one and gets
switched off. A ratchet starts honest, and the only way past it is `--update` in a commit somebody
reviews.

**It measures against a fixture project, never this repository.** Hooks print the branch, the last
commit subject, an issue count — all of which move. A baseline taken from the live tree would drift
on unrelated commits, and a gate that goes red on its own is one people learn to ignore. The
fixture pins every input, and the selftest asserts both that two runs agree *and* that a bigger
fixture measures bigger — determinism alone cannot show the fixture is what is being read, because
the live tree is stable within a run too.

## The load we do not emit is still the user's

The ratchet above governs the bytes **our** hooks print. A user's session pays for everything that
loads, and on the repository where this was measured (2026-09-22) ours was the smallest part of it:

| loaded into every session | ~tokens | whose |
|---|---|---|
| the `remember` plugin's SessionStart output | ~5,700 | a third-party plugin |
| `CLAUDE.md` | ~4,500 | the project |
| Claude Code auto-memory (`MEMORY.md` index) | ~3,800 | the harness |
| `AGENTS.md` | ~1,900 | the project |
| `rails-flow` `session-start.sh` | ~520 | us |

Three of those rows are **memory systems** — auto-memory, `remember`, and our `docs/brain` — and none
knows about the others. We cannot ratchet another plugin's output (it is not ours to run, and a number
we cannot reproduce is not one a ratchet can hold). What we can do is make the choice explicit:
`/rails-flow:setup-flow` §4a records which memory systems a project loads, and the `memory-systems`
check in `project_gates` holds the committed settings to it. **It adds nothing to any session** — it
runs on demand and in CI — so the check that guards the budget does not spend it.

## What this does not cover

Whether the content is *worth* its bytes is a review question, not a gate. The check answers only
**"did it grow without anyone deciding to let it"**.

Agent output is a separate budget with a separate failure mode — an agent's answer lands in the
parent conversation and stays there for the rest of the session, so a verbose agent is a permanent
tax rather than a one-off. That is [#1086](https://github.com/fmanimashaun/claude-skills/issues/1086).
