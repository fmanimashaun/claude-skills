<!--
  Branch off `dev`, PR into `dev`. No version bump. For each issue this PR completes, a line
  `Fixes #n` (alone on the line): on merge, close-on-dev-merge.yml closes it with label
  `fixed-on-dev` ("ships in the next release"). Partial work writes `Refs #n` and stays open.

  Keep every section. One that genuinely does not apply says "N/A" and why; only an `## If …`
  section may be deleted. rails-flow's guard-claims hook refuses a body missing any other (#1389),
  because a deleted section cannot be told apart from a forgotten one.
-->

## What this changes

<!-- One `Refs #<n>` line per issue. Traceability is never pooled: one line each, even when
     several issues share this branch. -->

Refs #<n>

## Change type — required, before the first edit

Silence is not a claim of exemption. Tick exactly one.

- [ ] **Framework / external claim** — asserts how Rails, Hotwire, Tailwind, a browser, or a gem
      behaves. **Blocked until `doctrine-verifier` returns CONFIRMED.** REFUTED closes the issue
      with the citation; INCONCLUSIVE leaves doctrine unchanged.
- [ ] **Design / architecture** — our own decision (brand-pack model, role-token contract,
      distribution policy). No upstream exists, so the authority is **the maintainer's explicit
      decision recorded on the issue** — the durable equivalent of a citation.
- [ ] **Plugin code / maintainer tooling** — no doctrine claim at all.
- [ ] **Mixed — then split it.** An architecture change must never carry a framework claim
      through on its coat-tails. The framework half still needs its own CONFIRMED verdict.

**Authority for the above** (citation + the version it applies to, or the link to the maintainer
decision — whichever this change type requires):

>

Reusing established framework syntax? Introducing **new** framework API into a skill is itself an
external claim, whatever else this PR is about.

## The issue body was verified, not just implemented

An issue's stated contract is a **hypothesis, not a specification**, however confident it reads.

- [ ] Every externally verifiable claim in the issue was checked against source before implementing.
- [ ] Read for **omissions** as well as errors — a spec can be silent about a real requirement.
- [ ] Where a claim has no upstream, I said so and recorded a maintainer decision rather than
      inventing a citation to fill the gap.

<!-- Recorded after an issue cited four keybindings "per the ARIA APG" that the current pattern
     does not contain (they were deleted from a 2017 example), while omitting one it states
     plainly. Traceable to a real source, wrong today. -->

## Gates

```bash
python3 scripts/maintainer_doctor.py --gates
python3 scripts/mutation_check.py
```

- [ ] 0 failed required.
- [ ] Every `skip` is listed below with why. **A skip did not run — it is not a pass.**
- [ ] Any failure that is pre-existing is named, with the evidence that it reproduces without my
      changes (and whose lane it belongs to).

<details><summary>Gate output</summary>

```
paste here
```

</details>

## If this adds or changes a check

A new guard without these is a **gate that cannot fail**.

- [ ] Ships with a `--selftest`.
- [ ] Declares a named mutation in `scripts/mutation_check.py` — I made it fail on purpose once,
      and the `expects` string names the fixture that caught it.
- [ ] Registered in `maintainer_doctor.py` `GATES`, so it runs without being remembered.
- [ ] Every carve-out has a **near-miss negative test** — an exemption tested only in the positive
      direction is untested in the direction that matters.
- [ ] The check cannot report clean over input it never read (zero inputs is not a pass).

## If this touches `skills/**`

- [ ] `python3 scripts/package_core.py` was re-run, and `git status` shows only the intended
      `dist/` change.

## If this touches markdown containing code

The fenced blocks are what an agent pastes verbatim into a user's project.

- [ ] `python3 scripts/lint_markdown_shell.py`
- [ ] `python3 scripts/lint_markdown_code.py`

## CHANGELOG

- [ ] **One bullet per issue** under the component's `### Unreleased` — never one bullet for a
      group.
- [ ] No version assigned. Versions are assigned at the promotion; a number on `dev` is a claim a
      user can install it, and that claim is false.
- [ ] The citation or maintainer-decision link is in the entry, exactly where a citation would go.

## Self-review

- [ ] I read **`skills/code-review/SKILL.md`** against this diff before requesting review, and
      recorded anything it found — including findings I did not act on. We are held to the rules
      we ship.
- [ ] Only files I authored are staged (`git status` first — never `git add -A`).

## Landing on `dev`

- [ ] No version bump.
- [ ] One `Fixes #n` line per issue this PR completes (it closes at the merge); `Refs #n` for
      partial work. Only a line that is exactly `Fixes #n` closes anything.
- [ ] No closing keyword in a COMMIT message: commits reach `main` at the promotion, and GitHub
      parses closing keywords there wherever they appear.
