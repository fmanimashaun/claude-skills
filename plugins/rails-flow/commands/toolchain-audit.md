---
description: Audit an existing project's whole claude-skills setup — update the toolchain, verify the scaffolding, run every check that applies, and report in three states. The broad sibling of /rails-flow:toolchain-check, which only resolves versions.
---

# /rails-flow:toolchain-audit

**What this is for.** A project adopted this toolchain some time ago. Since then the marketplace has
moved, the scaffolding has drifted, and nobody knows which of the shipped checks actually run here.
This answers that, with evidence.

**It is not `setup-flow`.** That command scaffolds and repairs conventions, and its audit path is
scoped to `CLAUDE.md`. This one spans every installed plugin, the CI pin, and the project's own
skills — and it *invokes* `setup-flow` as one of seven steps rather than duplicating it.

**It is not `toolchain-check` either.** That resolves installed-vs-published and exits 0/1/2. It is
**step 1** here.

This command was written as a paste-in prompt first and run twice against a real project before it was
shipped. Those two runs produced **seven** of the issues fixed in v1.92.2 → v1.94.0 (#706, #707, #708,
#720, #721, #723, #724). The steps below are the ones that found them; do not skip them because they
look procedural.

## 0. Ground rules

- **Measure, never assume.** Every claim about the setup names the command run or the file read.
  "Looks fine" is not a result.
- **Three states, not two.** pass / FAIL / **did-not-run**. A check that could not run is **not** a
  pass, and you say so every time. This is the rule that found the most. (`project_gates.py` splits
  did-not-run into **not-applicable** and **ERROR**, which is why its report has four columns; the
  discipline is the same.)
- **A diagnostic never mutates the project.** Every step below *reads*. `project_gates.py` asserts
  it: a check that writes a file while being asked a question comes back as **ERROR**, routed
  upstream, naming the path — that is a defect in the check, not a finding about this project.
- **Repairs are either SAFE or they wait.** The SAFE set is small and closed, the same shape as the
  marketplace's own doctor `--fix`: fast-forwarding a local ref that is behind its remote; pulling the
  integration branch when it is 0 ahead; making an already-installed git-hook nudge executable. Each
  is applied only if the user asked for repairs, each never rewrites history, resets, or cleans, and
  each is listed under **Repaired (safe changes only)** in the report. Everything else — a scaffolded
  file, a regenerated artefact, `CLAUDE.md`, CI config, an install, any commit — is shown as a diff
  with a one-line reason and **waits**. Do not "fix" what may be a deliberate choice.

## 1. Update, restart, and confirm what you actually got

```
/plugin marketplace update claude-skills
```

Then **restart Claude Code** — plugin changes do not take effect in a running session. After the
restart:

```
/rails-flow:toolchain-check
```

Read the exit state, because the third one is the trap:

| exit | meaning |
|---|---|
| 0 | up to date — proceed |
| 1 | updates available, or a plugin did not reach target — update, restart, re-run |
| **2** | **one side could not be resolved. This is NOT "up to date". Stop and say so.** |

**Report the resolved version of each of the five** — `rails-stack`, `rails-flow`, `qa-flow`,
`pipeline`, `design-flow` — not one number for "the toolchain". Two reasons, both real: the plugin
cache holds **several versions of the same plugin** simultaneously, and `rails-stack` is versioned only
in `marketplace.json` while the code plugins are versioned only in their own `plugin.json`.

Say which plugins are installed at all. If one is missing that should not be, say so; do not install it
unasked.

## 2. Audit the rails-flow scaffolding — audit mode, not re-scaffold

```
/rails-flow:setup-flow
```

Use its **audit & repair** path against the existing `CLAUDE.md`. Report:

- Are the managed markers intact, and is anything inside them stale against current doctrine?
- **Fact contradictions** — does it assert anything about this project that is no longer true?
- **Broken safety rules** — has a guardrail been weakened or made unenforceable?
- If an `AGENTS.md` exists, does `CLAUDE.md` actually **import** it? Claude Code reads `CLAUDE.md`,
  not `AGENTS.md`; an unimported one is read by nothing.
- Is `GUARDRAILS.md` present and current? Is `docs/brain/` seeded and consistent with the repo's real
  state rather than a months-old snapshot?
- Should anything currently in `CLAUDE.md` move to `.claude/rules/`?
- **Structure**: what does `claude_md_structure.py --report CLAUDE.md` say — how much is incident
  narrative, is there a checklist near the top, is a ceiling recorded and held? Propose the relocation
  diff; never summarise.

Every proposed change as a diff with a one-line reason.

## 3. Run every shipped check that applies to THIS repo

Inventory **first** — it says what will and will not run, and why:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project_gates.py" --list
```

Show that before running anything. Then run it for real and report the four states per check:
**pass / FAIL / not-applicable / ERROR**.

**Be explicit about not-applicable.** A repo with no `qa/` reports the evidence checks as
not-applicable, and that must never read the same as a repo with complete evidence. If many checks are
not-applicable, say which capability would make them apply.

Each non-pass also says **whose tracker it belongs to**: a **FAIL** is this project's, an **ERROR** is
ours and goes upstream via `/rails-flow:report`, and a missing `requires` binary is neither — install
it.

## 4. Verify each installed plugin's own setup

Only the plugins actually in use. Run each in its idempotent mode and report drift; do not silently
re-scaffold.

- **qa-flow** — `/qa-flow:setup-qa`. Does `qa/qa.config.yml` exist, and does the declared stack still
  match the codebase's real testing signals? A config naming a tool the repo no longer uses is drift.
- **pipeline** — `/pipeline:setup-pipeline`, then `/pipeline:install-hooks`. Is `pipeline.yml` current?
  Are the git-hook nudges installed and executable? Report each Docker/Kamal prerequisite separately.
- **design-flow** — `/design-flow:setup` to confirm the token architecture, then `/design-flow:audit`
  for UI drift.

Anything not installed is reported as **not installed**, never as passing.

## 5. Are the project-local skills still current?

```
/rails-flow:curate
```

Project skills are generated from the project's own docs and go stale when those change. Report which
no longer match their sources, and which sources have no skill. Do not regenerate without showing what
changes.

## 6. Check the CI pin — this one bites quietly

If this repo runs the shipped checks in CI, it checks out `fmanimashaun/claude-skills` at a pinned
`ref`. Find it and report the tag, how far behind the current release that is, and what changed in
between that affects what CI enforces.

**A pin is correct; an unpinned `main` means CI changes whenever we ship.** But a pin left alone for
dozens of releases means CI enforces old rules while the local session enforces new ones, with nothing
saying the two disagree. Bring the information; do not bump it unasked.

This step is here because it found a defect in **our own** scaffolding template, which had shipped a
pin 41 releases stale — and a stale pin produces no error, so nobody would ever have reported it.

## 7. Report

One table: **area | state | evidence (command or file) | action needed.** Then, separately:

0. **Repaired (safe changes only)** — each SAFE repair applied, one line each, or "none". Never fold
   a repair into the table; a reader must be able to see what the audit changed without diffing.

1. Everything in the **did-not-run** column and why. **This section is not optional** — if it is empty,
   say "none" rather than omitting it.
2. The single most important thing to fix first, chosen and justified in one sentence. Not a menu.
3. Anything that looks like a defect in the toolchain rather than in this project. Say so plainly —
   those go upstream with `/rails-flow:report`.

**Do not call the setup healthy unless every applicable check actually ran and passed.**
