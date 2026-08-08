# Getting started

Ten minutes from nothing to a change that has been built, reviewed and independently verified.

## 1. Install

```bash
/plugin marketplace add fmanimashaun/claude-skills
/plugin install rails-stack@claude-skills
/plugin install rails-flow@claude-skills
```

`rails-stack` ships **no commands** — it is doctrine. Installing it changes what Claude writes
without adding anything to type, which is why it goes first.

Add `design-flow`, `qa-flow` and `pipeline` as you need them.

## 2. Scaffold the project

```bash
/rails-flow:setup-flow
```

Writes `CLAUDE.md`, guardrails, and `docs/brain/` — a durable memory that survives a session ending.
It is **idempotent**: re-run it after an upgrade and it merges rather than overwrites.

If you are doing UI work, also:

```bash
/design-flow:setup
```

## 3. Build something

```bash
/rails-flow:feature
```

Describe what you want in plain language. It plans first, gets the information architecture settled
before writing code, implements, and reviews its own diff before handing it to you.

## 4. Verify it — with something that does not trust step 3

```bash
/qa-flow:verify
```

A separate agent that treats the build's claims as unverified and produces **evidence** rather than
assurances. This is the step people skip and the one that catches what review missed.

## 5. Ship

```bash
/pipeline:pipeline
```

Build → verify → certify → release, with circuit breakers so an unattended run stops rather than
digging.

---

## What to read next

- Working out which command you want: [command reference](Command-Reference.md)
- Why the loops are separate agents: [how the loops fit](Loops.md)
- Something behaving oddly: [troubleshooting](Troubleshooting.md)
