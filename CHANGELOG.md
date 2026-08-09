# Changelog

All notable changes to this repository. Components version independently:
**rails-flow** (version in `plugins/rails-flow/.claude-plugin/plugin.json`),
**rails-stack** (version in its `marketplace.json` entry), and repository-level
changes (README, packaging, infrastructure). Every version bump gets an entry here.

## Repository hygiene

### Unreleased

- **Nothing asserted that a promotion is a merge commit, and a squash broke the next release.**
  (#597) CLAUDE.md has said *"Release = one promotion PR `dev → main` (a merge commit)"* for eleven
  releases. v1.83.0 was squash-merged anyway, and prose does not merge anything.

  A squash keeps dev's **content** and drops its **ancestry**: `main` got a one-parent commit
  holding dev's tree without descending from it, so the merge base fell back two releases, git began
  seeing both sides as having independently changed the same files, and the **v1.84.0 promotion
  could not merge** — six conflicts on files nobody had edited twice, in a repo where
  `git diff dev main` was otherwise clean.

  `maintainer_doctor.py` now asserts it: **`main`'s tip must BE a merge and have a parent on
  `dev`.** Both halves are load-bearing, and the fixture is what proved it — a squash's single
  parent is `main`'s own previous tip, which for a repo's first promotion is itself an ancestor of
  `dev`, so "has a parent on dev" alone passes the exact trap the check exists for. The first
  formulation was weaker still and worth recording: *"is `dev` an ancestor of `main`"* is the
  **wrong question**, because mid-cycle `dev` has legitimately moved past the last release — it
  would have waved the real squash straight through.

  Two negative tests and a silent one, all against real git repositories with a real promotion
  performed both ways: the squash **fails**, the merge **passes**, and a repo that has never
  promoted is not accused of squashing one. The finding must also name `--squash` as the cause and
  `--merge` as the remedy, asserted — naming a defect without the flag that prevents it is how it
  recurs.

  It is a **diagnostic**, not a gate, so `--gates-only` (what CI runs) skips it. That is the correct
  classification — it is a question about branch topology at promotion time, not about repository
  content — but it means the full `maintainer_doctor.py` has to be run before a promotion, which
  CLAUDE.md now says.

### 2026-08-08b (v1.81.0)

- **The README was 913 lines and named version 1.3.1 while the marketplace shipped 1.80.0.** It also
  listed 5 of 42 commands and neither skill shipped that day, and **Install sat at line 732** — a
  reader had to scroll past seven hundred lines to use the thing. Re-authored to **194 lines** with
  install at line 12, every skill and command named, and zero stale versions. The two deep sections
  were **moved verbatim**, not deleted: `docs/architecture.md` (the design reasoning) and
  `docs/code-review-graph.md` (a 225-line setup for an *optional* integration that was occupying a
  quarter of the front page).

- **A wiki, in the repository rather than GitHub's.** A GitHub wiki is a separate git repo — no pull
  request, no review, and no gate can reach it, which is precisely how the README rotted. `docs/wiki/`
  is versioned with the code it describes, so a change that makes a page wrong shows up in the same
  diff. Ten pages: three **generated**, seven written.

- **The reference pages are generated and drift-gated.** `build_wiki.py` derives the command, skill
  and plugin pages from the manifest and the plugin directories, so renaming a command fails
  `--check` instead of quietly leaving the wiki wrong. A command in no group is **listed as
  ungrouped**, never dropped — silent omission is how the README came to name 5 of 42, and a reader
  cannot tell an omission from a command that does not exist.

  Its selftest caught two defects in its own author's work. One assertion was
  `"Ungrouped" in page_commands.__doc__ or True` — a **gate that cannot fail**, written into the
  selftest of a script whose entire job is refusing to go stale silently. Its replacement then
  failed for a second reason: run as a script this module is `__main__`, so `import build_wiki`
  created a **second module object** and the rebind landed on the wrong one.

- **`.github/workflows/wiki.yml` mirrors the pages on every push to `main`.** It verifies the pages
  are a clean build before mirroring, because publishing a stale reference under the repository's
  name is worse than not publishing. It replaces tracked content wholesale so a **deleted page
  disappears** rather than staying live and linkable. And it **skips loudly** when the wiki
  repository does not exist — GitHub creates it only after the first page is saved in the web UI,
  and a release must not go red because a mirror target is uninitialised.

### 2026-08-08 (v1.77.0)

- **A committed `.claude/settings.example.json`, and the three-file distinction written down.** This
  repo was telling users (via `/rails-flow:setup-flow` §2c) to keep permissions in a copied local
  file while not doing it itself — the claims-vs-enforcement shape, in its own configuration.

  The trap is that the three files look interchangeable and are not: `settings.json` is **tracked**
  and inherited by everyone who clones, `settings.local.json` is **gitignored** and holds what *you*
  trust on *your* machine, and `settings.example.json` is committed but **read by nothing** — a
  bridge so a fresh clone has something to copy. Permissions belong in the local file because they
  are not a decision to make on anyone else's behalf; the SessionStart hook belongs in the tracked
  one because it is what makes the repo work.

  Worth recording why a broad allowlist still prompts, since it cost a session: maintenance commands
  are **compound pipelines**, the whole string is evaluated, and **one** unlisted binary anywhere in
  the chain re-prompts all of it. A list holding `git`, `gh` and `python3` but not `grep` prompts on
  most real commands. `rm`, `curl`, `wget`, `kill`, `chmod` and package installers are deliberately
  absent — their blast radius outlives the run, so a prompt is correct friction even mid-run.

### 2026-08-08 (v1.75.0)

- **An `AGENTS.md` at this repo's root was read by nothing, for two whole releases.** Claude Code
  reads `CLAUDE.md`, **not** `AGENTS.md` — which is this repo's own shipped doctrine
  (`plugins/rails-flow/commands/setup-flow.md` §1b), written here and not applied here. So a file of
  rules about how to work, authored by the maintainer, sat unloaded through v1.73.0 and v1.74.0.
  Three independent confirmations: the session's project-instructions context held `CLAUDE.md` only,
  `CLAUDE.md` carried no `@AGENTS.md` import, and the file was untracked, so no parallel session or
  fresh clone saw it either. `claims-vs-enforcement` at the root of the repo that names the class.

  Fixed with the one-line `@AGENTS.md` import §1b prescribes, and the file is now tracked — both in
  one commit, because an import whose target no clone has makes every fresh clone open on a missing
  path.

  **Folding the rules into `CLAUDE.md` was tried first and reverted, on evidence.** The argument for
  folding was sound in the abstract: a harness-neutral file earns its indirection when a *second*
  harness reads it, and this repo is Claude-native by decision (#159), so there is one consumer.
  What that missed is how the file is actually used — the maintainer **edits `AGENTS.md` directly**.
  A new rule landed in it **two minutes after the fold**, unread, which is the fold's failure mode
  demonstrating itself: folding makes every future rule wait for someone to notice and copy it.
  The import has no such step.

- **New gate: `unimported-agent-instructions`**, both directions — an authored `AGENTS.md` that
  `CLAUDE.md` never imports, and an import whose target does not exist. The load-bearing detail is
  that the import must be a **line**, with fenced blocks stripped first: a fenced block *documenting*
  `@AGENTS.md` is prose about an import, and counting it would make the gate pass on precisely the
  repo state it exists to refuse — one that has written the rule down and wired nothing. That case is
  a fixture, and a mutation removing the fence strip is caught by it. It then **fired on live input
  within minutes of being written**, when the recreated `AGENTS.md` appeared unimported.

- **`derived-artifacts`, a third maintainer skill, was untracked and undocumented** — the same defect
  as the `AGENTS.md` one, found ten minutes after fixing it. Now tracked, and described in `CLAUDE.md`
  beside the other two. The sentence that named them said "**Two** maintainer skills"; it now names
  all three instead of counting them, which is that skill's own rule 3 (*generate it; never
  transcribe it*) applied to the sentence introducing it — a hand-typed "two" is a transcription, and
  it went stale the moment a third arrived.

- **The `unbounded-issue-query` gate caught the new "measure before you assert" rule undercutting
  itself.** The rule's worked example called `gh issue list` with no `--limit` — and that command
  silently defaults to `--limit 30`, so re-running that at the moment you quote it still reports one
  page as the total. Measuring the wrong thing, carefully. Bounded, and the paragraph now says the
  gate fired on it.

- **The decision-rights half was not shipped, deliberately.** The rules include when an agent should
  decide versus ask, which is genuinely user-facing — but its home is #488 pillar 2's decision-rights
  matrix, which has not shipped. `pipeline/reference/stop-conditions.md` was checked as a home and
  rejected: it governs when a *gated chain* stops, a different axis. Recorded on #488 as the
  maintainer decision pillar 2 must encode, rather than misfiled into a plugin now.

- **Two skills that lived in `.claude/skills/` now ship, because nothing in them was about this
  repo.** `derived-artifacts` (anything whose numbers come from somewhere else — read the
  generator's **structured source** rather than regex-parsing its generated prose, and assert every
  derived total against the source's own declared totals) and `parallel-session-lane` (the protocol
  when several agent sessions run against one repository at once). Both are stack-neutral, both
  answer a problem any project has, and both are now bundled in `rails-stack` beside `code-review`
  and `quality-pass` — the established precedent for shipping general agent doctrine as a skill.

  `parallel-session-lane` was **generalised, not copied**. It hardcoded this marketplace's layout —
  *"edit `plugins/<yours>/**` exclusively"*, *"do not edit `skills/**`, `dist/**`"* — which is
  meaningless in a user's repo. The rules now state the mechanism they always were: your assigned
  subtree, shared and generated paths, your repository's own review doctrine. A sixth rule was added
  from the same source as the rest — do not clean up worktrees you did not create, after an "idle"
  heuristic deleted three that were in active use.

- **`plugin-boundaries` stays maintainer-only, by its own rule 3.** Every line of it is about *this
  marketplace* — `marketplace.json`, per-stack plugins, the licensed corpora — so a user installing
  it would receive doctrine about a repo they do not have. **No copy was left behind** for the two
  that moved, either: rule 2 forbids it, and the price is that they are read as files here rather
  than being invocable, exactly as `code-review` already is.

- **New gate: `undocumented-skill`.** Every skill directory that exists — under `skills/` *or*
  `.claude/skills/` — must be **named** in `CLAUDE.md`. The sibling of `undocumented-plugin`, and it
  exists because the same failure hit skills twice in one night: `derived-artifacts` was authored,
  left untracked and named nowhere, while the sentence introducing the set said "Two maintainer
  skills" — a hand-typed count that went stale the moment a third arrived. It checks **naming, not
  counting**, because a count is itself the transcription the rule exists to catch.

- **Three existing gates caught consequences of the move that a review would have missed**, which is
  the whole argument for having them. `undeclared-component-label` required a `comp:` label per
  shipped skill, so downstream reports can route to the new ones. `skill routing` refused with
  **CANNOT CHECK** rather than passing on a `SHIPPED_SKILLS` pin it no longer recognised — four
  states, not two. And `CLAUDE.md`'s own distribution list was under-naming what `rails-stack`
  bundles: the drift its very next sentence warns is *"still on you"*.

- **A stale count inside the routing gate's own docstring.** It said *"The four SHIPPED skills"*
  while the set held five. Pinned by name now, with no count at all — the `derived-artifacts` rule
  applied to the file that enforces skill hygiene.

- **A scripted edit deleted 7,950 lines of this file, and the whole gate sweep passed.** PR #557
  removed **eight of the CHANGELOG's nine component sections** — `rails-flow`, `qa-flow`, `pipeline`,
  `design-flow` and both `rails-stack` sections, every one of their release histories — and CI
  reported **67/67 green** on the commit that did it. Restored from the last good blob, asserted
  **additions only** against it (`+88 −0`), so the 88 legitimate new lines survive and nothing else
  changed.

  The bug was a **two-anchor splice**: `t[:t.index(a)] + new + t[t.index(b):]`, written assuming `b`
  sat just after `a`. It sat seven thousand lines further down, so the slice removed everything
  between them. The general lesson is *assert what a splice removes, not just where it starts* — a
  rule for a reviewer, not a linter.

- **New gate: `changelog-section-missing`.** Every plugin declared in `marketplace.json` must still
  have a `## ` section in the CHANGELOG. The sections are **derived from the manifest**, so the check
  transcribes no list of its own and a new plugin is covered the day it is declared.

  Two properties are deliberate. It matches **`## ` only** — the truncation left `###` release blocks
  behind, so accepting any heading level would have passed on the damage, and a mutation reproduces
  exactly that. And it is **not a size or line-count check**: a threshold invites tuning it downward
  the first time a legitimate consolidation trips it, whereas a section either exists or does not.

  It was validated against the **real damaged commit**, not a fixture approximation: replayed over
  `674cdad` it names all five missing plugins, and is silent on the restored file.

### 2026-08-07 (v1.71.0)

- **`dangling-conditional-floor`** (Refs #531) — if §2a offers a lower floor conditional on multi-factor
  auth, the file must carry MFA guidance. Structural, not a judgement: it asks whether the second factor
  is discussed at all, and cannot tell adequate doctrine from a stub. A file that never offers the
  discount owes nothing, so the rule does not demand MFA doctrine of every auth file. 6 fixtures, 2
  mutations — and the fixtures had to be rebuilt once, because writing a bare `auth-security.md` tripped
  `password-floor-drift` as well and stole its mutation.

### 2026-08-06 (v1.69.0)

- **`hook-count-drift` — CLAUDE.md had two wrong numbers in one sentence.** It said *"of the ten hook
  scripts, eight are advisory"*; there are **eleven**, and nine are advisory. The eleventh is
  `design-flow`'s `design-tells.sh`. Both stale figures sat in the paragraph explaining which hooks fail
  closed — in the file that spends pages warning about claims nothing makes true.

  Third time a doc number about our own files has gone stale, and the **second time the missed component
  was design-flow** (#203, #489). So it is a join now: the total is counted from disk, and the advisory
  figure is **derived** — total minus the gates CLAUDE.md names by path — rather than read, because a
  second hardcoded number is just a second thing to go stale. A reworded sentence **fails loud** instead
  of silently checking nothing. 6 fixtures, 3 mutations.

  One fixture had to be rebuilt: the first version had *both* numbers wrong, so it could not isolate the
  total check — the advisory check fired too, and the mutation that disables the total comparison
  survived. It now uses a case where only the total is wrong.

### 2026-08-06 (v1.68.0)

- **`harness-doctrine.md` carried two stale counts about the rule it documents** (Refs #491). It said
  *"Four commands qualify today"* (five do) and *"two declared mutations"* (thirteen). Both were
  `claims-vs-enforcement` on our own doc — the exact class that file exists to warn about, in the
  paragraph describing a rule whose first version *"reported no findings over an empty scan"*. Found by
  the session fixing #491, which could not correct it from inside its own lane; both re-measured against
  the repo rather than incremented, and the §491 narrowing is now documented there too.

- **`undeclared-topology` counted a MENTION of an agent as a dispatch** (Refs #491). Detection was
  `re.search(rf"\`{name}\`", body)`, so a command explaining *who consumes* its output was charged with
  dispatching them: one sentence naming `qa-reporter` took `setup-qa.md` from 1 agent to 2 and produced a
  false finding. Both escapes were worse than the finding — declare a topology the command does not have
  (a false statement written into shipped doctrine to satisfy a gate), or stop naming the agent (the
  linter deciding what doctrine may say). A dispatch is now recognised by a signal a dispatch actually
  has: an imperative in the name's **own sentence**, an arrow/`to` handoff, the name in subject position
  at the head of its step, or a `Task`/`subagent_type` invocation — the last counting even inside a
  fenced block, while a name that appears *only* in a fence does not.

  The narrowing is biased toward **counting**, because for this rule a false negative (an undeclared
  fan-out shipping unlabelled) is worse than a false positive: the verb list includes ordinary English
  (`run`, `use`, `call`), `to`/`via` count as handoffs, and one dispatching occurrence is enough.
  Measured against the real tree rather than asserted — **5 commands examined and 0 reported, before and
  after**. Agent detections go 38 → 35 tree-wide and 29 → 28 across the five multi-agent commands; all
  three drops were read and confirmed to be mentions (`brand-guardian` inside `variants.md`'s own
  topology comment, `case-author` describing what `/qa-flow:cases` does later, `claude-skills-reporter`
  in a relative clause), and the narrowing never *adds* a detection. Reproducing #491 by restoring the
  sentence to `setup-qa.md` fires on `dev` (examined 5 → 6, one false finding) and is silent here.
  A new coverage counter, `commands_naming_2plus_agents_without_dispatching`, is what makes an
  over-narrowing visible: a silence fixture proves the rule does not *fire* on a mention, only a number
  that moves proves it can still *see* one. 6 new fixtures (both directions, one per named signal) and
  9 new mutations, each verified to be caught by the fixture its `expects` names. The finding now also
  names **which agent was counted via which signal**, because #491's reporter had to read the function
  to learn why the count was 2, and a count with no evidence behind it is what makes a maintainer
  reword doctrine to appease the gate.

- **`docs/inventory.html` — a generated, committed map of what this marketplace ships** (Refs #509).
  27 agents, 37 commands, 4 model-tier tables and 64 gates existed with no map of any of it: the one
  question people ask ("which agent owns this, what gate covers it, which command drives it") cuts
  across all three kinds, so answering it meant reading four plugin trees. One filterable table now
  does. **Change type: repo tooling** — no doctrine change, no framework claim, so no
  `doctrine-verifier` verdict was sought.

  Deliberately *not* the dashboard #509 was prompted by: same shape as `docs/coverage.html` instead —
  generated, committed, drift-gated, stdlib only, no runtime. Every source is **imported rather than
  re-parsed** (`maintainer_doctor.GATES`, `check_handoff.parse_tiers`), and the one source that could
  not be — agent frontmatter, because the page needs `description` and `tools` — is **reconciled**
  against `check_handoff.agent_models` instead, so two readers of one file cannot disagree in silence.
  All three traps that page recorded are pinned by fixture: zero git calls on the render path (counted,
  not compared), every input tracked in every clone, and `--check` comparing the blob at `HEAD`.

  Three defects were found by mutating the subject rather than by reading it, and all three are
  fixed. The `--check` fixtures stubbed `committed_blob`, so rewriting it to `Path.read_text`
  survived the whole selftest — the exact defect the gate exists to prevent, sitting inside its own
  test; it is now pinned against a throwaway git repo where the commit and the working copy
  disagree. The frontmatter fixture's folded lines all began with a capital letter, so relaxing the
  column-0 anchor also survived. And the placeholder guard tested for a placeholder *surviving*
  `str.replace`, which cannot happen — `gate-that-cannot-fail`, replaced by a count of the
  template's slots.

  The fourth was caught by writing the page's own footnote and then checking it: a first draft
  measured agent references as *"named in backticks or bold"* and printed "dispatches none" beside
  `/rails-flow:issues`, which names seven of its plugin's agents in plain prose and dispatches every
  one. Emphasis is typographic, not semantic. The match is now word-bounded and markup-blind, the
  column is called **Agents named**, and the page says outright that naming is not dispatch — a
  measurement it can make, in place of an inference it cannot.

  One guard exists for a hole nothing else in the repo can see: an agent file with no `name:` is
  **refused**, not skipped. `check_handoff.agent_models` skips it — correctly, there is nothing to
  reconcile — so both readers would skip it identically, the reconciliation would stay clean, the
  tier table would have nothing to match, and the agent would simply be absent from a page whose
  entire claim is completeness. 90 fixtures; 17 hand-run mutations, each caught by a named fixture
  (not registered in `mutation_check.py`: that harness stages a subject alone in a temp directory,
  and this subject is effectively the whole repo tree, so it cannot reach a baseline pass there).

  **The arm step now regenerates two pages, not one.** The inventory stamps the release version for
  the same reason the coverage page does, so a version bump invalidates it and `inventory artifact
  drift` fails until `python3 scripts/build_inventory.py` is re-run.

### 2026-08-06 (v1.67.0)

- **`duplicate-unreleased`** — at most one `### Unreleased` per component section. A manual error I
  made **twice in three releases**, both times identically: two changes each insert their bullet against
  the same `## <section>` anchor, so the second opens its own heading above the first. Nothing broke
  either time, because the promotion pre-flight counts headings — but it should not need catching by a
  human reading a number, and a repeated manual error a join can detect belongs in a gate rather than in
  a habit. Counts **heading lines**, not the substring, because this file's own prose discusses
  `### Unreleased` while describing the rule against a stray one, and a substring count made an earlier
  arm fail on that sentence. 5 fixtures, 2 mutations.

- **`undeclared-skill-dependency`** (Refs #513) — a command reading a skill from another plugin must
  carry a stop instruction. Verified against the pre-fix tree rather than assumed: 5 examined, **5
  reported**. Agents are deliberately out of scope, since an agent is only ever reached through a
  command. 6 fixtures, 2 mutations.

- **`invisible-character` missed every C0 control byte, and one had already shipped.** The table was
  typographic — characters that *look* like a space. A control byte is worse: inside a **regex literal**
  it silently changes what the pattern means, and `inspect.getsource` renders it invisibly, so the
  source reads correctly while the rule matches nothing. `gate-that-cannot-fail` with no symptom.

  Found the only way it can be. Writing `\b` through a shell heredoc produced a literal `0x08` in the
  new rule above, whose pattern then required a backspace after *"stop"* — it reported clean on input it
  could never match, and its own fixture caught it. Reading the line with `repr()` is what made it
  visible; `inspect.getsource` had shown it as correct. The table now covers BACKSPACE, VERTICAL TAB,
  FORM FEED, ESCAPE, BELL and NUL (TAB and line endings excluded as legitimate), and it immediately
  found **5 backspace bytes already in `CHANGELOG.md`** — a `\bverify\b` written the same way in an
  earlier session. All cleared; the repo now holds zero.

- **`plugin-boundaries` — the second maintainer skill**, in `.claude/skills/`, so it ships to nobody
  and arrives automatically on a clone. It decides *where content belongs*: one stack-neutral core with
  stack-specific plugins layered on top, exactly one home per concern, and nothing maintainer-only
  vendored into a client plugin. Every rule in it comes from a proposal rejected for breaking it, and
  it says to apply them **while shaping** a proposal rather than after.

  It earned its keep immediately. Read against #507 (asset generation), its rule 2 — *"a split whose
  two halves only work together, with nothing able to say so, is not yet a working design"* — surfaced
  a **pre-existing** defect: **all four `design-flow` agents and five of its commands reference
  `skills/fidara-design`**, which ships only inside the `rails-stack` bundle, and no `plugin.json`
  carries a `requires` field. Installing `design-flow` alone yields agents whose own text says *"read
  it first; it is the law"* about a file that is not there. Filed, not fixed here.

  Named in CLAUDE.md's `.claude/` inventory for the same reason `parallel-session-lane` was: a
  component in neither an inventory nor a gate is how `design-flow` fell out of the plugin list for as
  long as it existed (#203, #489).

### 2026-08-05 (v1.64.0)

- **`password-floor-drift`** (Refs #484) — the floor §2a *states* must equal the one its worked
  example *enforces*, because the reader copies the example. **Deliberately not a prose rule:** the
  obvious gate greps for "at least one uppercase" and would fire on the sentence that **forbids** it
  — the same mention-versus-prescription false positive as #491, which I hit two releases ago and
  filed rather than repeat. A number-to-number join has no such ambiguity. Drift **above** the floor
  is reported too: two numbers for one rule is the defect, not the direction. 7 fixtures, 2 mutations.

### 2026-08-05 (v1.63.0)

- **`parallel-session-lane` — the protocol for running several sessions against this repo at once.**
  A maintainer skill in `.claude/skills/`, so it ships to nobody through the marketplace and arrives
  automatically for anyone who clones. Five steps, each written from a session that went wrong:
  confirm your worktree (a wrong-worktree edit once put one session's uncommitted work onto
  another's release branch), read CLAUDE.md, take **one** coherent slice and say which assigned
  issues you left out, stay inside `plugins/<yours>/**` with no drive-by fixes, and review your own
  diff against `code-review` **before** opening the PR.

  Two things fixed on the way in: the "never work here" rule named an **absolute home directory**,
  which is wrong on every machine but one and directly contradicts this repo's fresh-clone
  onboarding story — it now resolves the primary checkout from `git worktree list` instead. And it is
  named in CLAUDE.md's `.claude/` inventory, because a component in neither the inventory nor a gate
  is exactly how `design-flow` fell out of the plugin list for as long as it existed (#203, #489).

- **`orphaned-controller` — a scaffold may not prescribe a controller without its component** (Refs
  #483). **The pairing is discovered, not listed:** a controller is paired iff
  `component-implementations.md` has a `## <Titlecase>` section for it, which is why `sidebar` and
  `theme` are silent with no exemption — neither drives a component. A hardcoded pair list would
  need editing whenever a component is added, and the edit nobody makes is the bug the rule exists
  to catch. Verified against the pre-fix scaffold rather than assumed: it examines 4 paired
  controllers and reports **3**. 6 fixtures, 2 mutations.

### 2026-08-05 (v1.62.0)

- **The label taxonomy's source of truth was four components behind the repo** (Refs #489).
  `.github/labels.yml` is what `/maintainer-setup-intake` provisions **from**, and it declared 7
  `comp:*` labels for 9 live ones: `comp:fidara-design` and `comp:design-flow` existed on GitHub and
  sat on four open issues while being undeclared, so a fresh clone would never create them — and
  `gh issue create --label comp:design-flow` fails outright. Writing the **join** rather than
  patching the two found two *more* absent from the file **and** from GitHub (`comp:code-review`,
  `comp:quality-pass`); both are now created. `undeclared-component-label` reconciles `skills/*/` and
  `plugins/*/` against the yaml in **both** directions, so a component with no label and a label
  whose component was deleted both fail. Deliberately a pure **file** join with no `gh` call — a gate
  needing network and auth fails on a runner for reasons unrelated to the repo, which teaches people
  to ignore a red build. `rails-stack` is excluded as the bundle that ships the skills, each of which
  carries its own label. 7 fixtures, 4 mutations.

  Same blind spot as #203, where CLAUDE.md's plugin list omitted `design-flow` for as long as the
  plugin existed: the design half of the toolchain keeps being missed by the lists that enumerate
  components. That is now two enumerations gated instead of remembered.

- **`unprovisioned-label` — the join that finds the third instance** (Refs #487, #490). Two
  identical defects in two plugins is a class, so it is now enforced rather than grepped:
  `lint_self_consistency.py` fails when a plugin files with `--label X` against the **user's own**
  repo and no `gh label create X` exists in that plugin. Scope is the difficult part and is drawn
  three ways — a call carrying `--repo` targets the upstream tracker and is exempt; a label created
  in a *different* plugin does not count, because plugins install independently; and placeholders
  (`severity:sN`, `<comp:*>`) are **counted in the coverage line rather than judged**, since
  demanding a literal `sN` would be a false positive and dropping them silently would let a family
  go unchecked. The `--repo` test reads the whole **command block**, not one line: the real upstream
  call puts `--repo` on line 1 and `--label` on line 3, and the first version of this rule flagged
  it — a defect caught because the docstring promised block scoping the code did not do. 11
  fixtures, 4 mutations.

### 2026-08-02 (v1.61.0)

- **Four "monotony" gate rules considered and rejected, each with the measurement that killed it**
  (Refs #476). An external catalogue names four repetition axes that look like they belong beside
  `check_page_pacing.py`'s existing `tone-repeat` / `shape-repeat`. None earns a gate, for three
  different reasons — recorded in the gate's own docstring so the idea is not re-proposed:
  - **`LAY-017`** (a layout family repeated more than twice) was **measured against our own table
    and rejected**: the shipped band sequence uses one shape for **3 of its 7** bands, because the
    hero, a prose band and the closing band legitimately share the shape for centred prose. Their
    threshold would flag our own correct doctrine — a gate needing a carve-out on its first real
    input is taste wearing a count.
  - **`LAY-015`** (repeated closing CTA) is a **doctrine contradiction**: `page-anatomies.md` says
    the opposite with its reason — the failure is two *competing* primary actions, not one
    repeated — so adopting it would have the gate enforce against the file it reconciles.
  - **`VIS-012`/`LAY-024`** (surface and divider monotony) are **unmeasurable here**: their own
    detection is *"remove them and see"*, and neither appears as a column in the band table.

  The rationale's own number is re-derived by a fixture rather than asserted, because an unchecked
  number in a rationale rots exactly like one in doctrine and then reads as authoritative while
  being false. Two things that fixture exposed: it must convert **any** exception into a verdict,
  since a crash makes every other fixture look like it went quiet; and reading the real doc means
  the guard must **declare** it in `needs=`, which `run_baseline` caught by reporting all ten
  mutations INERT instead of passing them.

### 1.57.2 — 2026-08-02

- **CI actions were pinned to majors running the deprecated Node 20.** `actions/checkout@v4` and
  `actions/setup-python@v5` target node20, which GitHub now force-runs on node24 and will eventually
  stop supporting — both workflows printed the deprecation on every run. Bumped to **v7** for both,
  which is what `releases/latest` actually reports; the deprecation notice implies v5/v6, so the
  versions were checked against the API rather than inferred from the warning text.
- Changed in **both** `gates.yml` and `release.yml`. Those two files are deliberate mirrors —
  `CLAUDE.md` says change one, change the other — and a bump applied to only one would have left the
  publish path on a runtime the PR path had already left behind.

### 1.56.0 — 2026-08-02

- **`scripts/check_page_pacing.py` — the pacing doctrine's numbers are measured, not asserted**
  (Refs [#92](https://github.com/fmanimashaun/claude-skills/issues/92)). *How a page is paced*
  states a count taken from `coverage.md`, a band range, and a worked sequence whose entire point is
  that consecutive bands differ. Each is a claim about the repo, and a claim in prose rots silently
  — the `claims-vs-enforcement` class. Six rules, every one a **join** rather than a taste:
  `identical-row-count` (the stated 14 re-measured against `coverage.md`), `band-count` (the table
  against the range printed above it), `unknown-composition` (a band naming no `coverage.md` row),
  `unknown-tone` (a tone naming no role in `foundations-tokens.md`'s `@theme inline`),
  `tone-repeat` and `shape-repeat`. `--selftest`: 21 checks, weighted toward **silence** — a
  checker that fires on our own shipped sequence is one somebody deletes. Registered as two gates
  (`page pacing`, `page pacing selftest`) and behind **10 declared mutations**, one of which
  inverts the tone rule so the silence direction is guarded too.
  **This is deliberately not a design gate.** Nothing in it judges whether a band sequence is any
  good; it refuses only a number or a name in shipped doctrine disagreeing with the repo — the same
  shape as `check_shared_shapes.py` and `check_handoff.py`. `unknown-tone` resolves the vocabulary
  through the token file rather than a hardcoded `{card, background}`, so the section's *"no new
  token"* promise is enforced in the file that makes it instead of being another prose guarantee.
- **DECISION — the selftest harness stays one copy per install root; it is not extracted and not
  vendored** (#398). This is an **architecture/distribution decision**, not a framework claim, so
  the authority is the maintainer decision recorded on
  [#398](https://github.com/fmanimashaun/claude-skills/issues/398) rather than a `doctrine-verifier`
  citation — and the numbers behind it are measured against the repo, not asserted. The reasoning
  now lives in `skills/quality-pass/references/worked-example.md` so the next reader inherits it
  instead of re-measuring, which was the issue's own acceptance criterion.
  - **The boundary is `${CLAUDE_PLUGIN_ROOT}`, not file absence.** The marketplace is one git repo,
    so an install may hold every plugin tree on disk; what a plugin is *given* is its own root. No
    `.py` under `plugins/` resolves a path above its own plugin (`parents[2]` and higher: zero
    occurrences), so the harness copies partition into four disjoint install roots and no module
    reaches past the largest.
  - **The arithmetic.** A shared harness must be an object (`check()` mutates closure state, the
    reporter reads it): ~16 lines, and each caller nets 10. Across all four roots that is ~44 lines
    out of 6,016 — under 1% — against 298 call sites to rewrite and 10 `mutation_check.py` guards
    gaining a `deps=` entry over 81 declared mutations. Vendoring is worse still: a build step plus
    a drift gate larger than the duplication it polices, turning twelve honest copies into four
    that *claim* to be one.
  - **What makes the copies acceptable is a shared control, not a shared module** —
    `scripts/mutation_check.py` proves these selftests can fail. It covers ten of twelve;
    `extract_claims.py` and `findings.py` ship a `--selftest` no guard mutates, named in the
    write-up as a mutation-coverage gap rather than rounded away.
- **NEW `reach` column in the gated shared-shapes table**, and it is the point of the change:
  `files` says how much duplication exists, `reach` says how much of it a module could ever remove.
  `check_shared_shapes.py` derives it as the largest single install root holding the shape, and
  cross-checks that grouping against `marketplace.json` — if `plugins/<name>` ever stops being where
  a plugin is installed from, the column would be counting a boundary nobody ships, and that now
  fails rather than rots. Four new fixtures (a wrong reach with a right file count; a copy under an
  undeclared plugin; two silence controls) and four new declared mutations, including one that
  collapses the grouping without changing any file count. The corpus gained a second plugin so that
  mutation is *distinguishable* — with one plugin, "grouped by plugin" and "all of `plugins/` as one
  lump" give the same answer and the break would have been caught by a coincidental fixture.
- **FIX — `run_baseline` was reporting five INERT guards and the sweep had been red since it
  landed; 44 mutations were passing vacuously** (found while working #398, follows #422). #422 added
  the control and fixed the one instance it was written for. The control immediately found four
  more, plus a sixth defect that made its own selftest unpassable — *"when you find one instance,
  grep for the pattern"*, from `code-review`, and nobody did.
  - `check_handoff` — its `needs` **enumerated** ten agent files, and an eleventh (`claim-verifier`)
    had shipped. Now the `agents` directory, exactly as #422 did for `references`.
  - `validate_evidence` (24 mutations) — cross-checks every evidence contract against the agent
    documenting it; `needs=("plugins/qa-flow/agents",)`.
  - `maintainer_doctor` (7) — a fixture asserts every gate in `GATES` names a real script, and
    `GATES` spans the whole toolchain, so the mutant needs it. Directories, not the ~50 paths
    `GATES` names today. `dist` too, or the packaged-skill check SKIPs, and a skip in a staged
    tempdir is indistinguishable from a pass.
  - `project_gates` (3) — the scripts its three `checks.json` manifests name.
  - `crawl_report` (3) — `crawl_collector.js`, which its three sibling qa-flow judges all declared
    and it did not.
  - `mutation_check --selftest` itself asserted every declared path `is_file()`, which **#422's own
    directory-valued `needs` made false** — a gate that could not be satisfied by the feature it was
    checking. Split: modules keep `is_file()`, `needs` gets `exists()`, and both directions are now
    fixtures (a directory is accepted; an absent path is still reported), because relaxing an
    assertion is how one stops asserting.
- **FIX — the same stale-restated-number defect the 1.55.0 entry below claims to have fixed was
  still live 70 lines further down the same file** (#398). The decision section said the harness had
  "**nine** copies spanning **two** plugins" and that a module "reaches **four** of the nine"; the
  gated table said twelve across three plugins plus tooling, with a reach of five. Three wrong
  numbers in one sentence — and it is the sentence #398 was filed from, so the question was framed
  against figures that had already moved. The 1.55.0 fix patched the instance three lines under the
  table and did not grep for the pattern, which is the failure mode `code-review` names. Digits
  gone; the sentence points at the table.
- **FIX — `mutation_check`'s own selftest rejected the declaration #422 had just added.** Rule 6 asserts
  every guard names paths that exist, and tested all four fields with `is_file()`. #422 deliberately gave
  the `build_coverage` guard a **directory** (*"a directory, so a new reference doc is picked up rather
  than quietly missing"*), so the commit that removed one vacuous guard left `dev`'s `mutation check` gate
  failing. `subject` and `selftest` are scripts and still must be files; `deps` and `needs` are staged by
  copying, so existence is the real rule for them — which still catches the typo the check exists for.
  Found running the sweep on a clean `origin/dev`, not on a change.

- **A `checks.json` path that no shipped tool produces is a build failure now, not a permanent
  skip** (#423). `scripts/check_manifest_paths.py` reconciles every `applies_when` path and every
  `{match:glob}` in every `plugins/*/checks.json` against the paths that plugin's own scripts,
  commands, agents and hooks name. Registered in `GATES` as **`checks.json paths`** (the shipped
  manifests) and **`checks.json paths selftest`** (the rules), for the reason the tell-detector's
  entry already states: fixtures prove a rule fires and stays silent, only the bare run proves the
  three manifests we actually ship are true. Its first run found **five** entries across **two**
  plugins, which is the whole justification for it existing.
  - **It closes a gap `project gates` could not see.** `project_gates.py --selftest` already asserts
    every manifest entry names a real *script* and supplies a required subcommand. Nothing asserted
    the entries name real *artefacts* — and that is the half where "not applicable" hides.
  - **Prose does not count, and that is the whole design.** `qa/routes.json` was named four times in
    qa-flow — in a docstring paragraph, in YAML frontmatter and twice in prose — while the file it
    describes is `qa/reports/routes.json`. A corpus built from "anywhere the string appears" would
    have read clean over the exact bug it exists for. So the corpus is built only from surfaces
    something *runs*: Python string constants with docstrings excluded, JS literals with `//`
    comments excluded, **fenced blocks only** in commands and agents, comment-stripped hook shell.
    `*_selftest.py` is excluded too — a fixture path is not a shipped writer, and letting one vouch
    for a phantom is how a test double validates a typo.
  - **It states what it does not do.** It cannot prove a write happens: most of these artefacts are
    written by an agent following a fenced command, and no static analysis reaches that. It proves
    *agreement* — a manifest path that appears nowhere else in the plugin is either a typo or an
    artefact nobody produces, and both are the same permanent skip. Saying so in the docstring is
    the point; a checker overclaiming its own guarantee is the class it guards against.
  - **Coverage is counted in both directions**, because "no findings" over nothing examined is the
    vacuous pass this repo keeps hitting: a manifest declaring no paths is reported, and so is a
    plugin whose surfaces name none — the second reported *instead of* failing every entry, since an
    empty corpus is a defect in the scan, not in the manifest.
  - **Six declared mutations in `mutation_check.py`**, one per rule and one per coverage counter,
    each expecting its fixture's own label. The empty-corpus mutation **survived** the first run:
    the obvious assertion looked for "no shipped script … names", wording the per-entry finding also
    carries, so the fixture passed with the branch deleted. It now asserts on wording unique to that
    branch. A coincidental catch is exactly what the `expects` field exists to refuse.
  - The worked example's shared-shape counts move 12 → 13 and 10 → 11: the new checker uses the same
    selftest harness and reporter every other script here uses, and it is not exempted from its own
    measurement. `check_shared_shapes.py` re-derives both, so the number is measured, not restated.

- **NOTE — five guards were INERT on `dev` (`check_handoff`, `validate_evidence`, `project_gates`,
  `crawl_report`, `maintainer_doctor`), so 44 mutations proved nothing.** Fixed on `dev` by #429,
  which carried no CHANGELOG entry, so the record is here. Found independently twice in one evening —
  by #429 and by #423's branch, both by running the sweep on a clean `origin/dev` rather than on a
  change — and both arrived at the same fix, so the merge simply takes #429's. Worth recording
  because the cause was identical in all five and is now on its second week: **a hand-typed list of a
  directory's contents goes quiet the first time the directory grows.** `run_baseline` (#422) is what
  made it visible at all — without that control, a guard whose staging is incomplete is
  indistinguishable from one whose fixtures all work. `needs` takes directories; use one.

### 1.55.0 — 2026-08-01

- **`mutation coverage` outgrew the doctor's flat 180s timeout** (#129). The gate spawns one
  subprocess per declared mutation, so it gets slower every time anyone makes the repo safer; at
  236 mutations it timed out, and a timeout is reported as FAIL — indistinguishable from a real
  survivor, so the sweep tells a maintainer to fix a checker that was working. **`SLOW_GATES`**
  declares the allowance next to the gate rather than raising the default for everything, because a
  gate given ten minutes is a gate that hangs for ten minutes before anyone hears about it. Keyed
  by gate NAME exactly as `CORPORA_GATES` is, and pinned in the selftest the same way, in three
  directions: a name matching no gate, a set that grew to cover a check that reads the tree once,
  and the direction nobody thinks of — an "allowance" that is really a **tightening**. Three
  declared mutations. Parallelising the checker was tried and **reverted**: it measured ~7% on a
  machine running other agents' sweeps concurrently, and an unmeasurable speedup is not worth
  concurrency in the checker every other gate is judged by. The reasoning is recorded on
  `run_guard` so the next person does not re-derive it.
- **FIX — the quality-pass worked example restated two gated counts as bare prose numbers, and both
  had gone stale** (#129). The table said 11 and 10; the sentence three lines below still said 9 and
  8. `check_shared_shapes.py` could not see it, because it reconciles the *table*. That is a second
  copy of a number with no arbiter — the exact shape the row above it is about — so the numbers are
  gone and the sentence points at the table instead. Found by the gate failing on the counts #129
  legitimately moved (a 12th `check()` harness, a 3rd luminance copy), which is the gate working.

- **FIX — `docs/harness-doctrine.md` carried three stale gap-claims, and one of them told the reader
  to trust it** (found while working #128). §8 said a grep for
  `circuit.?breaker|stop condition|max attempts|bail out` across `plugins/` and `skills/` *"still
  returns none"* — it returns **26 hits in five files**, and has since the rails-flow half shipped.
  §7 said *"#127 is open. Nothing in the repo assembles that today"* — #127 is **closed** and
  `/rails-flow:handoff` assembles exactly that. §11's table row asserted both issues unshipped.
  - **A stale gap-claim is as misleading as a stale guarantee, and it survives longer, because
    nobody re-checks good news.** The three replacement rows in §11 are re-checkable commands rather
    than sentences, which is what the rest of that table already does and what these three had
    stopped doing.
  - §8 now records what shipped and, more usefully, the two places the halves deliberately
    **differ**: which of the four escapes became mechanical in pipeline and which stayed doctrine,
    and why escalate-and-continue was not copied into a gated chain.
  - §8a's deferral of loop breakers to #128 has **expired**, so the decision is re-grounded rather
    than left resting on a reason that no longer holds: the `topology: loop` marker still owes only
    `exit:`, because a number in an HTML comment beside an enforced mechanism is a claim nothing
    makes true.
- **The gate sweep gains `pipeline stop conditions`** and `mutation_check.py` gains the `breaker`
  guard (14 mutations). A selftest the sweep never runs makes a clean sweep a claim about work
  nobody did.
- **NEW gate `shared shapes`** (`scripts/check_shared_shapes.py`, #360). The `quality-pass` worked
  example states how many files carry each duplicated shape and rests an extraction decision on
  those numbers. A count written in prose rots the first time someone adds a copy, and it rots
  **silently** — the `claims-vs-enforcement` class, one directory along from the skill that names
  it. The checker re-derives all five counts from `plugins/**/*.py` + `scripts/**/*.py` and fails
  when the table disagrees, in **both** directions (a shape with no row, and a row nothing
  measures). Same shape as `check_handoff.py` reconciling a tier table against the agents it
  describes.
  - **It is explicitly NOT a duplication gate**, and that is written into the module docstring, the
    `GATES` entry and CLAUDE.md. Nothing here refuses a copy: the quality pass is advisory by
    design, so a gate that blocked on it would contradict the doctrine it guards. The only failure
    it can produce is a stale number.
  - **10 selftest checks, 6 declared mutations**, all caught by the fixture named for them. One
    mutation is a `continue` rather than the usual `if False:` because disabling that branch would
    raise a `KeyError` before any labelled assertion ran — a crash is not a verdict.
  - **The gate found a defect in itself on its first real run.** Its synthetic corpus was written
    as literal Python, and `scripts/` is inside the measured roots — so `class Unusable(RuntimeError)`
    and the luminance coefficient existed as *strings* in the measuring file and the counts moved
    4→5 and 2→3. Fixed by placeholder-substituting the fixture at write time (the trick
    `lint_markdown_shell.py` already uses), **not** by exempting the file from its own walk: a
    self-exemption is the carve-out class, and it would hide a genuine copy landing there later.
  - Gate sweep 43 → **45**.
- **NEW `verify_interaction_claims` in `build_coverage.py` — the half of the matrix with no guard
  is the half that rotted** (#89). `verify_shipped_evidence` has checked every `documented`
  component row against the reference docs since #124. `INTERACTION_PATTERNS` had nothing, and four
  of its nine rows were wrong (see the rails-stack entry). Each row now carries a **probe** — a
  literal string present in the shipped docs iff that contract is written — and the rule is
  `shipped` ⇔ probe present.
  - **Checked in both directions on purpose.** A one-way *"`shipped` rows must cite a doc"* rule
    would have caught **none** of the four, because none of them claimed `shipped`; that is the
    `carve-out-without-negative-test` shape from the `code-review` skill. The direction that
    actually failed in production — a `planned`/`declined` row whose contract has landed — is the
    first fixture, and the near-miss beside it proves a genuinely unwritten pattern stays silent, so
    the rule is about whether the doctrine exists and not about the word `planned`.
  - Probes must be non-empty and distinct across rows, or one document vouches for two mechanisms.
    Fails **closed** when the reference docs cannot be read, like the evidence guard beside it.
  - Runs inside `verify_totality`, and is exercised by `--selftest` with a synthetic corpus, so it
    holds on a runner and on a corpora-less clone. Coverage selftest 41 → **52** checks.
- **NEW `verify_cell_text` — a `|` in any cell silently splits the row into an extra column**
  (#89). Every table here is assembled with `add(f"| {a} | {b} |")`, so a pipe inside a note grows
  the row a column while the header keeps three, and nothing complains. **Found by nearly shipping
  one**: the new `filter / typeahead` note was first written as ``aria-autocomplete=list|both``,
  which generated, committed and drift-checked perfectly happily. Scans every rendered cell —
  component rows, interaction patterns, layout primitives — with fixtures on two of the three.
- **NEW gate `skill routing` + `skill routing selftest`** (#158) — asserts every file in a shipped
  skill's `references/` is named by its own `SKILL.md`, that no `SKILL.md` routes to a reference
  that does not exist, and that no `SKILL.md` body exceeds Claude Code's documented 500-line
  Level-2 budget. `scripts/check_skill_routing.py`, registered in `GATES`, 15 selftest checks,
  5 declared mutations in `mutation_check.py`.
  - **The issue's central premise was REFUTED, and the gate is what survived it.** #158 proposed
    rebuilding `SKILL.md` as a "capability router" because *"a skill is loaded as a unit, so a task
    that only needs `jobs-and-realtime.md` still pays for `deployment-kamal.md`"*. The official docs
    say the opposite: *"Claude reads only the files each task needs. A Skill can include dozens of
    reference files, but if your task only needs the sales schema, that's the one file Claude loads.
    The rest stay on the filesystem and **cost zero tokens**"*
    ([agent-skills/overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)).
    The domain-split `references/` layout we already have is the documented recommendation
    (*"Pattern 2: Domain-specific organization"*,
    [best-practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)).
    **No router was built** — there is no Claude Code routing/sub-skill mechanism to build one on,
    and the issue's supporting citation (`npx skills add --full-depth`) is an unrelated third-party
    registry flag about git-clone freshness, not context depth.
  - What the issue got right is its last criterion — reachability *"asserted by a script rather than
    by review"* — and that rests on a claim the docs do make: *"Keep references one level deep from
    SKILL.md. All reference files should link directly from SKILL.md"*, because *"Claude may
    partially read files when they're referenced from other referenced files"* (best-practices).
  - **The precision fixture is the point.** Routing is a `references/<name>` path, not a bare
    filename: two fidara-design references name `coverage.md` in prose while routing nothing, so a
    substring test would have called the tree clean and hidden the one real defect. Link syntax is
    *not* required either — the docs never mandate `[]()`, and demanding it would fail all 19
    rails-8 dispatch rows for a rule nobody wrote.
  - Scope is pinned in `SHIPPED_SKILLS` and enforced **by the gate against the real tree**, both
    directions, so a fifth skill fails the sweep until added deliberately. It is not pinned in the
    selftest: a scope asserted only over fixtures is a claim about fixtures, and keeping
    `--selftest` hermetic is what lets the mutation harness run it against a mutated copy.
- **Agent worktrees are ignored and pruned from every linter.** Claude Code puts background-agent
  worktrees at `.claude/worktrees/` — **inside the repo**, one full copy each — and
  `git status --porcelain` collapses the whole tree to a single `?? ` line, so sixteen repo copies
  looked like nothing at all. That is the untracked-directory trap `CLAUDE.md` already warns about,
  now sitting one careless `git add` away from committing sixteen copies of the repo.
- **The linters were reading them.** `.claude` is one of `DEFAULT_ROOTS`, so a sweep went from **129
  files to 1526** — and the failure mode is worse than slowness: another agent's half-finished edit
  fails the *maintainer's* gate run, over a file that is not in the maintainer's tree. Pruned by
  exact name in all three linters, with a `worktrees-notes/` near-miss fixture so the prune cannot
  widen and go quiet.
- The ignore pattern is **root-anchored and slash-free**, per #197 — the lesson there being a
  pattern that was written, believed, and matched nothing.
- Adding to `SKIP_DIRS` broke the existing `corpora no longer pruned` mutation's anchor, and the
  mutation checker **hard-errored** rather than passing quietly. Both anchors updated; that stale-
  anchor rule is the reason the drift was visible at all.
- **`check_token_contrast.py` now reads every shipped role-token file, not one** (#129). Its input
  was a single hardcoded path, so it was a claim about `foundations-tokens.md` wearing the name of
  a claim about the design system. Both brand packs carried defects it existed to catch (logged
  under design-flow above). The pack glob is a hard error when it matches nothing — a checker that
  measured nothing would print the same clean verdict as one that measured everything, which is
  the skip-as-pass failure this repo keeps paying for. 12 pairs × 3 files = 36 measured, up from 10.
- **NEW pair: muted text on a muted surface**, in both modes. It is the commonest low-contrast
  failure in a real UI — helper text, timestamps, table meta — and it was the pair missing from the
  set. `_template`'s sat at 2.71:1 behind a green sweep.
- **`--destructive-foreground` on `--destructive` is deliberately still NOT measured**, and this is
  a decision for the maintainer rather than one a checker should make while implementing an
  unrelated issue: fidara's shipped `#FFFFFF` on `#EF4444` is **3.76:1**, under 1.4.3, so adding
  the pair would fail the build on a **brand** colour. Reported on #129 instead. Palettes this repo
  authors from scratch *are* held to the wider set — `palette_candidates.py`'s `CANDIDATE_PAIRS`
  includes it, because there is no legacy value there to grandfather.
- **FIX — the sRGB linearisation breakpoint was WCAG 2.0's `0.03928`; the current normative text
  uses `0.04045`.** *"if RsRGB <= 0.04045 then R = RsRGB/12.92 else R = ((RsRGB+0.055)/1.055) ^
  2.4"* — https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html. The correction is
  proved **immaterial** rather than claimed so: the two disagree only on inputs in
  (0.03928, 0.04045], and no 8-bit channel lands there (10/255 = 0.0392, 11/255 = 0.0431), which
  the selftest asserts over all 256 channels. So no committed ratio changed value.
- **The shipped and canonical contrast implementations are now COMPARED, not merely both present.**
  `plugins/design-flow/scripts/palette_candidates.py` must carry its own copy — a plugin has to run
  in a user's clone with nothing installed, and `scripts/` is never distributed — so the selftest
  imports it and asserts both the **maths** and the **token parser** agree, each with a positive
  control proving the comparison can detect a disagreement at all. Same discipline
  `brand_pack_lint --roles-from` applies to the role contract.
- **New guard in `mutation_check.py` for `check_token_contrast.py`**, which had none: 6 mutations.
  Two of them exist because the first versions of these fixtures were **tautologies** — "no
  disagreement" and "no comparison" are the same observation until something forces them apart, and
  mutation is what found that. Selftest 12 → **29** checks. Two new gates registered
  (`design-flow palette candidates` and its selftest); sweep 35 → 37.

### 2026-08-01 — the install block, and a rule that can see it

- **FIX — `design-flow` was missing from the README's install block** (#203, second occurrence).
  It is in `marketplace.json`, named **four times** in the README, and had **no
  `/plugin install design-flow@claude-skills` line** — so anyone following the install steps got
  four of five plugins and never learned the fifth existed. Its `/design-flow:setup` was missing
  from the setup ordering too. Found by a maintainer asking for the install commands.
- **NEW `uninstallable-plugin` rule**, because this is the second time. The existing
  `undocumented-plugin` rule stayed **green** throughout, exactly as its own docstring predicts:
  *"it proves the name appears SOMEWHERE in the file, not that it appears in the list that
  enumerates what ships"*, and four prose mentions satisfied it.
  - That docstring also explains why it was left loose — locating a prose *section* needs judgement
    about where a section begins, which is how a mechanical rule turns noisy. **An install command
    is not a section.** `/plugin install <name>@` is a fixed pattern, so "this plugin has no install
    line" is decidable with no judgement at all, and the trap the looser rule documents does not
    apply.
  - Proven to add coverage rather than duplicate: with the line deleted, the new rule fires and
    `undocumented-plugin` stays silent. Three fixtures including the near-miss that matters — **prose
    naming the plugin does not satisfy it**, or it would be the looser rule again under a new name.
    One declared mutation. Self-consistency assertions 70 → **73**.

### 2026-08-01 — the gates finally run somewhere

- **FIX — the publish was not gated, which is the branch that matters.** `gates.yml` shipped hours
  earlier watching pull requests and pushes to `dev`. It did **not** watch `main`, and `release.yml`
  had no `needs:` — so **the merge commit that publishes ran zero of the 35 gates.**
  - The reasoning was already written down and I failed to apply it where it counted: `gates.yml`
    watches `dev` on the grounds that *a merge commit is content no PR run ever tested*. That is
    truer of `main`, not less — a clean merge of two clean branches can break a gate reading across
    both, and here the blast radius is a **published release**, from the branch
    `/plugin marketplace add` resolves.
  - `release.yml` now has a `gates` job and the publish declares `needs: gates`. The sweep is
    **called**, not copied — `gates.yml` gained `workflow_call` — because two copies drift and the
    one that drifted would be the copy guarding production.
  - Raised by the maintainer asking what runs at `dev → main`, since that is where deployment
    happens. It is the second defect in this workflow found by being asked to justify it rather than
    by any check.

- **The gates run in CI now. Until today they ran nowhere automatically.** Every automated check on a
  pull request in this repo belonged to a **third party** — AccessLint and GitGuardian. Our own
  workflow was `release.yml`, which fires only on a push to `main`, *after* merge, and whose single
  check is the `dist/` drift guard. The **35** gates this repo builds, documents at length and treats
  as its safety net ran when a maintainer remembered to type the command.
  - That is the `claims-vs-enforcement` defect CLAUDE.md warns about most, **in its own
    infrastructure**: the file insists guarantees belong in the deterministic layer, and the
    deterministic layer was a command a human had to remember. Actions is free and unmetered for
    public repos, so there was never a cost reason either.
  - Found by being asked to justify *"CI has no browser"* — a claim of mine that was **wrong**
    (`ubuntu-latest` ships Chrome). Checking it turned up the real situation, which was worse than
    the thing I had said.
  - **New `--gates-only`** runs the sweep without the machine diagnostics, because those ask about a
    maintainer's *clone* — branch, stale `main` ref, `gh` auth, licensed corpora — and none is
    meaningful on a runner. Failing on them would teach people to ignore a red build, which is worse
    than having no CI. The gates are the opposite: each is a claim about repo **content**, identical
    on a runner and a laptop.
  - **CI asserts `node` and `ruby` exist rather than tolerating their absence.** Without them
    `lint_markdown_code.py` returns exit 3 → SKIP, and in CI a skip is indistinguishable from a pass
    unless something asserts the interpreters are there.
  - **`dist/` drift is checked on PRs too**, not only at release: it is a diagnostic rather than a
    gate, so `--gates-only` skips it, and `release.yml` catches it only after merge on someone else's
    clock. Same shape in both files deliberately — change one, change the other.
  - Proven to block: an injected `outline-none` regression in shipped doctrine returns **exit 1**
    with `gate: self-consistency` FAILing. Restored, exit 0.

### 2026-07-31 — a committed coverage page, and bytes that depend only on data

- **FIX — CLAUDE.md claimed all hooks fail open; two fail closed on purpose** (#132). A
  `doctrine-contradiction` in our own file, flagged by the session that wrote the harness doctrine and
  **verified here by running the hooks** with `python3` shadowed by a stub that exits 127 — not by
  reading them. Of the **ten** hook scripts, eight are advisory and degrade to silence, which is
  correct: an advisory that blocks work when a dependency is missing is an advisory people disable.
  The two gates fail **closed**: `guard-bash.sh` still exits **2** on `git add -A`, because its
  fallback passes the raw JSON payload and the command text is still in it; `release-gate.sh` exits
  **2** when `python3` is absent *and* the command targets `main`, **0** otherwise. That scoping is the
  load-bearing detail — a gate that failed closed on unrelated work would be switched off within a day.
- **`docs/harness-doctrine.md` is now referenced from the maintenance guidance** (#132), closing its
  last open acceptance criterion. It was cited only from a sibling doc, so the doctrine existed and the
  people who needed it — anyone adding a hook — had no pointer to it. The reference sits at the exact
  place the decision gets made, next to the fail-open/fail-closed split, with the guarantee-vs-advice
  test named: *"if a model ignores this, what happens?"*

- **TOOLING — the computed work queue becomes a gate at the point of use** (#133). `issue_graph.py`
  could already tell you the order; nothing checked that anyone followed it. `/maintainer-work`
  Phase 0 said *"take the head of the triaged queue"* — a claim with no enforcement, which is the
  same **prose-is-not-a-queue** defect #133 was filed about, one level up. New
  `python3 scripts/issue_graph.py --ready 109 110` answers one question — may this be started now,
  as one branch? — and **exits non-zero with the refusal on stderr and stdout left empty** when any
  named issue waits on open work, is already closed, is absent from the tracker, or when the graph
  is too broken to answer from, so a caller reading stdout alone cannot mistake a refusal for a
  go-ahead (`--json` is the stated exception). Wired into `/maintainer-work` Phase 0, where the
  standing instruction had been prose. Change type: **maintainer tooling**; no skill
  doctrine and no external framework claim, so no `doctrine-verifier` verdict applies, and the
  declaration format it reads remains the maintainer decision recorded on
  [#133](https://github.com/fmanimashaun/claude-skills/issues/133).
  - **Edges *between* the requested issues are satisfied by the branch itself**, because grouping
    related issues onto one branch is this repo's preferred shape (CLAUDE.md, *Grouping related
    issues on one branch*). `--ready 110` refuses while `--ready 109 110` clears, with a note
    saying which member goes first. That carve-out has the near-miss test that matters:
    `--ready 110 42` still refuses, so padding the set cannot launder a blocker away. A gate that
    refused the doctrine's own branch shape would be switched off inside a week, after which
    nothing checks the order at all.
  - **A dependency on a *closed* issue is not a refusal.** That is what a met prerequisite looks
    like — pinned by a silence fixture, because treating it as a block would make every finished
    edge permanent.
  - **A green light says what it does not know.** On an issue declaring no edges the verdict
    carries a note: the tracker names no blocker, which is not the same as nothing blocking it.
    Until the epic backfill lands that is the common case, and reporting the first as the second is
    the `unverified-negative` class from `skills/code-review/SKILL.md`.
  - **59 selftest checks** (was 43) and **6 new declared mutations** appended to
    `mutation_check.py`'s `issue_graph` guard — 17 total, all caught, each observed failing on
    purpose. They cover both directions of the group carve-out, the absent/closed refusals, and
    both directions of the coverage caveat. The one temp-dir helper every end-to-end fixture goes
    through is what
    the pre-existing *"writes its fixture into the repo again"* mutation anchors on, so a future
    `main()` fixture cannot quietly acquire its own unguarded write path.
  - **FIX — the documented backfill procedure could destroy an issue body, and exit 0 doing it.**
    `gh issue view … > /tmp/body.md` truncates the target *before* `gh` runs, so an expired token
    or a wrong number left an empty file; the next two lines then appended the deps block and
    handed it to `gh issue edit`, **replacing an entire downstream report with nothing but the
    edges**. Reproduced against a stubbed `gh` before and after: the old snippet loses the body and
    returns 0, the new one refuses and returns 1. It now runs under `set -euo pipefail`, uses
    `mktemp` rather than a shared filename, and greps for an existing `deps` fence first — the
    parser reads *every* `deps` block in a body, so appending a second is silent and a drifted
    duplicate contributes edges nobody wrote.
  - **Still open on #133:** the last acceptance criterion, backfilling epics #89 / #96 / #108 and
    their phases with edges. That is tracker work rather than a repo change, and every declaration
    it adds is what makes the coverage caveat above stop firing.

- **NEW `docs/harness-doctrine.md` — the rule we had been following without writing down** (#132):
  *put your guarantees in the deterministic layer*, with the guarantee-vs-advice test (*"if a model
  ignores this, what happens?"*), the three tiers (prose / output contract / deterministic), the
  fail-open-for-advisories vs fail-closed-for-gates rule, and a classification checklist for anyone
  adding a hook, agent, command or gate. Change type: **design / architecture** — our own placement
  decision with no upstream, so the authority is the maintainer decision recorded on
  [#132](https://github.com/fmanimashaun/claude-skills/issues/132), not a `doctrine-verifier` verdict
  (which would return INCONCLUSIVE for want of a source). No new tooling, as the issue required.
  - **The document's own claims are cited to files and re-checkable by command, never asserted** —
    §11 is a table mapping each factual claim to the command that re-verifies it. Where the answer is
    *nothing enforces this*, it says so: #77's no-disposition clause has no mechanical check
    (`grep -rn disposition scripts/ plugins/*/scripts/` is empty), nothing cross-checks a skill's
    non-negotiables against its own reference recipes, and #127 (handoff artefact) and #128 (stop
    conditions) are **open**, so their principles are recorded as gaps rather than as doctrine.
    Writing those as rules would have been the `claims-vs-enforcement` defect inside a document about
    catching it.
  - **Two claims in the issue body did not survive verification, and the corrections are the
    document's sharpest content.** (a) *"Every one of those three was an agent ignoring text"* is not
    true of #56: no agent defied anything at run time — a skill's stated non-negotiables and its own
    copyable recipes disagreed and nothing had ever compared them. That changes the remedy from
    *enforcement* to *a cross-check between two things we wrote*, and the general rule is **where a
    prose rule and a copyable example disagree, the example wins**. (b) *"fail closed for gates"* is
    imprecise: `release-gate.sh` fails closed **scoped to the command it guards** and exits 0
    otherwise, because a gate that fails closed on unrelated work is a gate people disable.
  - **The evidence is extended with the shape the issue did not have: determinism is necessary, not
    sufficient.** The Stop gate ran every time and still let behavioural code finish with no spec,
    because plain `--porcelain` collapses a new untracked directory (`stop-gate.sh:24`, found by
    behaviour-testing #125's gate). Four more instances from 2026-07-31 are cited as one class — a
    gate that wrote into the working tree, a selftest no gate ran, an interpreter stall reported as a
    syntax error, and mutation coverage blind to a new rule inside an existing guard. All four are
    *a check existed, ran, and reported a verdict that was not the truth*, which is why the doc
    carries the six-rung ladder (mechanical → selftest both directions → mutation per **rule** →
    reachable from `GATES` → three states with `skip ≠ pass` → does not mutate its subject).
  - **Found while verifying: `CLAUDE.md:455` states the rule too flatly.** *"Hooks fail open when a
    dependency is missing"* holds for the four status/advisory hooks and is **false** for
    `release-gate.sh`, which fails closed on a promotion with no `python3` — deliberately, per its own
    header comment. A `doctrine-contradiction` against our own code. Recorded in the new doc's §5 and
    left for the owning lane, since this branch is scoped to `docs/`; for the same reason the issue's
    other two placements — a pointer from `CLAUDE.md` and a mirror into rails-flow's scaffolded
    conventions — remain open.

**The coverage page's bytes depend only on its data** (#89). The gate above shipped, and then broke
twice in one afternoon — both times because something that is *not the data* had leaked into the
rendered bytes. The rule, arrived at the hard way: **a committed generated artifact may be a function
of tracked content and nothing else.**

- **FIX — git state, round two: the dirty caveat was a footgun, not a safeguard.** Round one removed
  the SHA, branch and released/unreleased split. The dirty flag survived, and it was worse:
  regenerating `coverage.md` *necessarily* dirties the tree, so the very next command wrote a
  `state: "dirty"` page to the **committed** path, and the gate then failed permanently until someone
  rebuilt from a clean checkout. `--check` guarded the *comparison* and left the *write* wide open.
  I did this to myself in the regeneration PR and diagnosed it by extracting both `DATA` blobs and
  diffing them field by field — only `provenance` differed — rather than theorising. With git state
  gone the dirty-tree **exit-3 skip goes too**, and that is a strict improvement: mid-edit the honest
  verdict is a real one (*"the committed page does not match your data"*), which is exactly what
  `build_coverage.py --check` reports for `coverage.md` with no exemption at all. `EXIT_INCOMPLETE`
  is deleted as the dead declaration it became. Proven by re-running `--check` from a deliberately
  dirtied tree: **exit 0**, where it used to be unpassable.
- **FIX — corpora availability was the second leak, and the carve-out I added for it was the wrong
  fix.** The page walked the licensed kits for the upstream totals, so a machine without them
  committed `tw: null, fb: null` and broke the gate for everyone who had them. A web session hit
  exactly this and flagged it. Earlier the same day I had added `coverage artifact drift` to
  `CORPORA_GATES` — which only stops the check failing on the machine that is **missing** them and
  cannot stop that machine committing a stripped page. **The exemption moved the damage rather than
  removing it.** Both counts now come from the committed `coverage.md` Totals table — which every
  clone has, and which `build_coverage.py --check` already gates by enumerating the kits — so the
  authority is unchanged and only the *reader* moved. The exemption is reverted, with the reasoning
  recorded in both directions so it is not re-added. Verified by hashing the render with the corpora
  attached and with the root pointed at nothing: **identical**.
- **Three fixtures had to be rebuilt, each because `mutation_check.py` refused a coincidental catch.**
  The corpora-independence fixture now stubs the kits **in** at two different sizes rather than
  stubbing them away — the mutation workdir has no corpora at all, so stubbing away was **vacuous**
  while the mutant merely **crashed** on the missing directory. It runs **first** and returns
  immediately, because every later fixture calls `collect()` and a traceback is not a verdict. The
  totals-parser fixture that pinned the corpus rows as *"not buckets"* was translated rather than
  deleted: they now parse under keys of their own, and the guarantee that actually mattered — corpus
  counts must never land in a fidara bucket and inflate a percentage — is asserted structurally.

**The coverage matrix is a committed deliverable now, and its gate reads git** (#89).
**Change type: repository tooling.** Nothing under `skills/` changed and no framework behaviour is
claimed, so no `doctrine-verifier` verdict is in scope. The one factual assertion — the row counts —
is measured by the generator and cross-checked against `coverage.md`'s own Totals table on every run.

- **The coverage matrix now ships as a page other machines can see.** `build_coverage_artifact.py`
  wrote to a **gitignored** path, so the deliverable existed only on the machine that built it — the
  defect the maintainer named directly (*"if the build is gitignore, then other maintainer machine
  can't see it"*). Output moved to **`docs/coverage.html`**, committed, with a `--check` drift mode
  wired into `maintainer_doctor.py` beside its selftest. All 113 rows classified, cross-checked
  against the Totals table committed in `coverage.md` on every run, so the two cannot silently
  diverge. **The per-state split is deliberately not quoted here** — it moved twice while this branch
  was open (65/44/4 → 66/44/3 → 67/44/2) as parallel sessions landed marketing-copy, visual-asset and
  Reviews+Rating doctrine. `coverage.md` is the authority on the state of the matrix; this entry is
  about the tooling. The drift gate caught the stale page both times, which is the whole point of it.
- **FIX — the drift gate was unpassable by construction.** The page embedded its own short SHA,
  branch, and released/unreleased state. Committing the page advances `HEAD`, and a promotion flips
  `unreleased` → `released`, so the committed bytes could only ever match a build made at the one
  commit that does not yet contain the file. **A file inside a commit cannot name its own commit**;
  git already knows. `stable_provenance()` now embeds only what is stable and still honest about
  freshness — the release version, read from a tracked source — plus the dirty caveat. The console
  keeps logging commit and branch, where volatility costs nothing. Two mutations pin both halves,
  and a fixture renders the page under two different fake checkouts and requires byte equality.
- **FIX — the gate trusted the working copy, so it passed a page that was never committed.** It
  tested `args.out.is_file()` and compared the file on disk. Run against an untracked, *byte-identical*
  `docs/coverage.html`, it exited **0** — the exact "invisible deliverable" failure above, waved
  through by the gate built to close it, with the message *"is not committed"* one branch away. This
  is `claims-vs-enforcement` in new code, the third instance the `code-review` skill's own class has
  caught. It now compares the blob at `HEAD` via `committed_blob()`, verified against real git rather
  than a stub. Fixtures pin both directions: an untracked clean build **is** drift; a locally
  scribbled working copy over a clean commit is **not**.
- **A dirty tree is INCOMPLETE, not clean and not drift.** The dirty caveat is part of the rendered
  bytes, so reproducibility genuinely cannot be observed from a dirty checkout. `--check` returns
  **3**, which `maintainer_doctor.py` maps to **SKIP** — never `ok`. The gate is real exactly where it
  matters: CI, a fresh clone, the moment before a promotion.
- **FIX — the new drift gate failed on every machine without the licensed corpora.** The doctor
  comment registering it asserted *"neither needs the corpora: `build_coverage` declares `ENTRIES`
  statically"*. The generator does run — but the page **embeds the upstream corpus totals**, so a
  corpora-less rebuild produces different bytes and `--check` returned **1** on a healthy checkout,
  telling a contributor to fix failures about **optional private files**. Proved by pointing the
  corpora root at a nonexistent path, which is also how the false comment was caught: CLAUDE.md
  promises *"no gate fails for their absence"*, and this one did. `coverage artifact drift` joins
  `CORPORA_GATES`; the doctor's selftest now pins that set **exactly**, so both too-narrow (a
  corpora-less machine fails) and too-broad (a gate that needs nothing gets skipped, shrinking the
  sweep behind a healthy summary) require a deliberate edit with a reason. Verified end-to-end
  through the real `check_gates()` loop: both drift gates SKIP, both selftests still PASS.
  CLAUDE.md's *"exactly one file reads them"* is corrected to distinguish one **reader** from one
  **dependency** — importing `build_coverage` inherits it.
- **FIX — one gate was registered twice.** `coverage artifact selftest` appeared in `GATES` twice, so
  `--gates` ran it twice and printed a total larger than the number of distinct checks performed. The
  only consumer of those names was a set comprehension, which collapses duplicates, so nothing could
  see it. Names are asserted unique now.
- **Six mutations guard it, and three of them lied the first time.** They reported *caught — but not
  by the expected fixture*, because the guard declared no `deps`: the selftest died at import inside
  the mutation workdir, so every mutation was "caught" by a **traceback**. A crash is not a verdict.
  The guard now declares `build_coverage.py` and `coverage.md`. Separately, a mutation anchor
  hand-transcribed as a multi-line string was mangled by `re.sub`'s backslash handling in the
  authoring step — anchors are read out of the file, never typed.

### 2026-07-31 — a stall is not a syntax error


- **FIX — an interpreter stall was reported as a syntax error** in the markdown-code gate. This is the
  unreproducible `30 passed, 1 failed` a parallel session saw and honestly flagged rather than papered
  over, saying it had truncated the output and could not name the gate. **Not papering over it is why
  it got found.**
  - **The mechanism:** `subprocess.TimeoutExpired` is a **subclass** of `SubprocessError`, so the
    single `except (OSError, subprocess.SubprocessError)` swallowed a stall into the same rc-127 path
    as *"interpreter missing"*. From there it flowed through the context ladder and came out as
    **"did not parse in any documented context"** — an environment stall presented as a **code
    defect**, non-deterministically and only under load. A full sweep here takes ~110 s against a 30 s
    per-block limit, close enough to fire occasionally. In someone's diff it would have read as a real
    finding.
  - A stall now raises `InterpreterStalled`, is reported as **skip** with the offending blocks named,
    and makes the run **incomplete** (exit 3 → SKIP) — because the honest verdict is that the block was
    never checked. Real findings still win the exit code, but the stall notice always prints, so it is
    never silently absorbed.
  - **Two of my own fixtures were wrong before this landed, both caught by mutation.** The first
    stubbed `mc._run`, which **bypasses the very except-ordering under test** — so it passed with the
    code broken. Patching `subprocess.run` one level lower fixed it. The second mutation reverted the
    `raise` to `pass`, which produces an `UnboundLocalError` rather than the original defect, so it
    tripped the fixture's catch-all branch instead of the intended one; it now reverts to the **actual
    pre-fix behaviour**. A mutation that breaks the code differently from how it was broken proves less
    than it appears to.

- **TOOLING — the coverage matrix gets a filterable HTML rendering, generated from the source rather
  than from its own output.** `scripts/build_coverage_artifact.py` renders the 113 fidara rows as one
  filterable table (guidance × kind × corpus, plus search), because the question a maintainer actually
  asks — *"what needs doctrine, of kind composition, that only Flowbite carries?"* — cuts across the
  three tables `coverage.md` splits them into, and markdown cannot express a filter. Change type:
  **maintainer tooling**, no skill doctrine touched and no external framework claim, so no
  `doctrine-verifier` verdict applies; the licensing boundary is inherited from `build_coverage.py`
  rather than re-earned (names, statuses and our own prose only — no corpus markup, so a published
  page cannot leak licensed content).
  - **It imports `build_coverage.ENTRIES`; it does not parse `coverage.md`.** The first draft parsed
    the markdown and failed its own count assertion on the first run: the Totals label `documented`
    also matches `— derivable from documented parts`, so 44 derivable rows were counted as
    documented. `coverage.md` is *generated English*, and pattern-matching it re-derives — badly —
    structure the generator already had (three tables whose column order differs, `✓`/`—` standing in
    for booleans, a tracked issue buried inside a status string). `is_documented` / `is_derivable` /
    `needs_doctrine` are predicates on a frozen dataclass, so there is no label left to mis-match.
  - **That moves one bug class rather than removing it, and the new one is guarded.** The predicates
    are `status.startswith(...)`, so a typo'd status (`"documentd"`) matches none of them and the row
    would vanish from the page with no error — 112 rendered where 113 exist. `verify_partition`
    asserts the buckets are total **and** disjoint; the disjoint half is unreachable via real status
    strings, so a stub matching all three exercises it. A completeness matrix that silently drops a
    row is worse than no matrix, because the missing row looks like a row that does not exist.
  - **The count assertion is kept, but against data rather than against our own regex.**
    `cross_check_committed` compares the counts to the Totals table in the *committed* `coverage.md`
    — an independently generated artifact of the same source — and reports **three** states, where
    `skip` (file absent or unparseable) is not a pass. A `fail` aborts the build instead of warning.
    The one surviving label match is the ordering that caused the original bug, pinned by a fixture
    whose four numbers are all distinct so a mis-mapping cannot pass by coincidence.
  - **A shared page stamps what it was built from.** An HTML snapshot outlives its commit, and a
    stale second source of truth that looks authoritative is the failure mode this repo keeps
    writing down — so the page carries the commit, the branch, the rails-stack version, and whether
    that commit is in a published release. An unreleased or dirty build says so on the page itself,
    in amber. The HTML is deliberately **not committed**: it is a rendering, not a source, and a
    committed copy would be a second thing to keep in sync — which is why there is no `--check` and
    therefore no mutation (that requirement attaches to gates).
  - **Corpora stay optional.** Only the two upstream enumeration totals need `design-corpora/`; the
    113 rows are ours. Without the corpora the page omits those two numbers and says so, rather than
    printing a zero that reads like a finding. 40 selftest checks, of which 8 are guards observed
    firing — including `</script>` inside entry prose, which `json.dumps` does **not** neutralise,
    and whose escape must stay value-preserving (the first attempt turned `<!--` into `<--`).

- **FIX — a selftest existed that no gate ran.** `maintainer_doctor.py`'s own selftest flagged
  `build_coverage_artifact_selftest.py` as having no `GATES` entry — *"`--gates` would report a clean
  sweep having never executed them"*. Wired; sweep **34 → 35**. The check that caught it exists for
  exactly this coverage-gap class, and this is the first time it has fired on a real omission rather
  than a fixture.

- **FIX — an interpreter stall was reported as a syntax error** in the markdown-code gate. This is the
  unreproducible `30 passed, 1 failed` a parallel session saw and honestly flagged rather than papered
  over, saying it had truncated the output and could not name the gate. **Not papering over it is why
  it got found.**
  - **The mechanism:** `subprocess.TimeoutExpired` is a **subclass** of `SubprocessError`, so the
    single `except (OSError, subprocess.SubprocessError)` swallowed a stall into the same rc-127 path
    as *"interpreter missing"*. From there it flowed through the context ladder and came out as
    **"did not parse in any documented context"** — an environment stall presented as a **code
    defect**, non-deterministically and only under load. A full sweep here takes ~110 s against a 30 s
    per-block limit, close enough to fire occasionally. In someone's diff it would have read as a real
    finding.
  - A stall now raises `InterpreterStalled`, is reported as **skip** with the offending blocks named,
    and makes the run **incomplete** (exit 3 → SKIP) — because the honest verdict is that the block was
    never checked. Real findings still win the exit code, but the stall notice always prints, so it is
    never silently absorbed.
  - **Two of my own fixtures were wrong before this landed, both caught by mutation.** The first
    stubbed `mc._run`, which **bypasses the very except-ordering under test** — so it passed with the
    code broken. Patching `subprocess.run` one level lower fixed it. The second mutation reverted the
    `raise` to `pass`, which produces an `UnboundLocalError` rather than the original defect, so it
    tripped the fixture's catch-all branch instead of the intended one; it now reverts to the **actual
    pre-fix behaviour**. A mutation that breaks the code differently from how it was broken proves less
    than it appears to.

- **TOOLING — the coverage matrix gets a filterable HTML rendering, generated from the source rather
  than from its own output.** `scripts/build_coverage_artifact.py` renders the 113 fidara rows as one
  filterable table (guidance × kind × corpus, plus search), because the question a maintainer actually
  asks — *"what needs doctrine, of kind composition, that only Flowbite carries?"* — cuts across the
  three tables `coverage.md` splits them into, and markdown cannot express a filter. Change type:
  **maintainer tooling**, no skill doctrine touched and no external framework claim, so no
  `doctrine-verifier` verdict applies; the licensing boundary is inherited from `build_coverage.py`
  rather than re-earned (names, statuses and our own prose only — no corpus markup, so a published
  page cannot leak licensed content).
  - **It imports `build_coverage.ENTRIES`; it does not parse `coverage.md`.** The first draft parsed
    the markdown and failed its own count assertion on the first run: the Totals label `documented`
    also matches `— derivable from documented parts`, so 44 derivable rows were counted as
    documented. `coverage.md` is *generated English*, and pattern-matching it re-derives — badly —
    structure the generator already had (three tables whose column order differs, `✓`/`—` standing in
    for booleans, a tracked issue buried inside a status string). `is_documented` / `is_derivable` /
    `needs_doctrine` are predicates on a frozen dataclass, so there is no label left to mis-match.
  - **That moves one bug class rather than removing it, and the new one is guarded.** The predicates
    are `status.startswith(...)`, so a typo'd status (`"documentd"`) matches none of them and the row
    would vanish from the page with no error — 112 rendered where 113 exist. `verify_partition`
    asserts the buckets are total **and** disjoint; the disjoint half is unreachable via real status
    strings, so a stub matching all three exercises it. A completeness matrix that silently drops a
    row is worse than no matrix, because the missing row looks like a row that does not exist.
  - **The count assertion is kept, but against data rather than against our own regex.**
    `cross_check_committed` compares the counts to the Totals table in the *committed* `coverage.md`
    — an independently generated artifact of the same source — and reports **three** states, where
    `skip` (file absent or unparseable) is not a pass. A `fail` aborts the build instead of warning.
    The one surviving label match is the ordering that caused the original bug, pinned by a fixture
    whose four numbers are all distinct so a mis-mapping cannot pass by coincidence.
  - **A shared page stamps what it was built from.** An HTML snapshot outlives its commit, and a
    stale second source of truth that looks authoritative is the failure mode this repo keeps
    writing down — so the page carries the commit, the branch, the rails-stack version, and whether
    that commit is in a published release. An unreleased or dirty build says so on the page itself,
    in amber. The HTML is deliberately **not committed**: it is a rendering, not a source, and a
    committed copy would be a second thing to keep in sync — which is why there is no `--check` and
    therefore no mutation (that requirement attaches to gates).
  - **Corpora stay optional.** Only the two upstream enumeration totals need `design-corpora/`; the
    113 rows are ours. Without the corpora the page omits those two numbers and says so, rather than
    printing a zero that reads like a finding.
  - **44 selftest checks — 6 guards observed raising, 5 silence fixtures, 33 assertions.** Three of
    them exist because they caught something during the build, not by anticipation:
    - `</script>` inside entry prose, which `json.dumps` does **not** neutralise (it is valid JSON
      and still ends the script element). The escape has to be value-preserving, and the first
      attempt turned `<!--` into `<--`.
    - **`git status --porcelain` is fixed-width, and `.strip()` corrupts it.** An unstaged change is
      `" M path"` — leading space significant — so stripping the output shifted the slice and the
      stamp reported `cripts/build_coverage_artifact.py`. Invisible for *staged* files, which is
      why the first run looked right; the fixture therefore covers ` M`, `M `, `MM` and `??`.
    - **The default output must not be `dist/`.** That directory holds the committed `.skill`
      artifacts, and the packaging check is "repackage, then confirm `git status` shows only the
      intended `dist/` change" — an untracked HTML file there sits inside the very signal that
      check reads. It writes to a new gitignored `/build` instead.

- **FIX — the call-site rule flagged a CORRECT call site** (#95). `ButtonComponent.new(…, data: { action:
  … })` is legal: its initializer ends in **`**attrs`**, which forwards arbitrary keywords — and that is
  how ViewComponent passes HTML attributes through, so the rule was set to fire on most correct call
  sites the moment one appeared. It now excludes splat-forwarding initializers from the unknown-keyword
  check (declared components 20 → 14; the six with splats keep their **slot** checking, which a splat
  does not affect).
  - **The carve-out keys on the splat, not on weakening the check** — the `ModalComponent` flag that
    preceded it was *correct*, because that one has no splat. Three fixtures pin all three edges: a
    splat silences the keyword check, a component **without** one still fires, and a splat **never**
    excuses an undeclared slot. Plus a mutation that removes the carve-out, so it cannot regress.
    `mutation_check` **64 → 65**.

### 2026-07-31 — six parallel sessions, and what they caught in each other

- **FIX — a broken plugin pointer, and the reason the new rule could not see it** (#272).
  `plugins/pipeline/commands/setup-cloud.md` pointed at
  `${CLAUDE_PLUGIN_ROOT}/../templates/env.example`. `${CLAUDE_PLUGIN_ROOT}` **is** the plugin's root,
  so the `/..` walked out of it: the path resolved to `plugins/templates/env.example`, which does not
  exist, while the real file sat at `plugins/pipeline/templates/env.example`. One spurious `/..`.
  - **The interesting half is why `broken-doc-pointer` — added days earlier for exactly this class —
    stayed silent.** Its regex required the extension to be one of `md|py|sh|json`, and this pointer
    ends in `.example`. **An extension allowlist fails open on the first type nobody added**, which is
    the failure mode CLAUDE.md already records for packaging's binary detection (*"never an extension
    allowlist"*). The rule now accepts **any** dot-extension, which still keeps globs and bare
    directories out — all the allowlist was ever doing. Pointers examined: **41 → 46**, still clean.
  - Three fixtures, both directions, including the exact `/..` shape from this issue; plus a mutation
    that **reverts the regex to the allowlist**, so the widening cannot silently regress. `mutation_check`
    **58 → 64**; its selftest **81 → 87**.
  - Building that mutation took two attempts — hand-escaping a regex-inside-a-regex drifted, and the
    checker's stale-anchor error caught it rather than letting a mutation pass vacuously. Rebuilt by
    reading the anchor line out of the file itself.

- **`issue_graph.py`: a gate that wrote into the repo, and a rewrite that could hang** — two review
  findings on #267 plus a third the fix itself exposed. All three shipped in that promotion, so this
  is the follow-up.
  - **The selftest wrote `scripts/.issue_graph_selftest.json` into the working tree** and unlinked it
    in a `finally`. `maintainer_doctor.py` runs that selftest as a gate, and a diagnostic must never
    mutate the repo — it also fails on a read-only checkout and races two concurrent runs on one
    fixed filename. `mutation_check.py`'s own docstring already records this exact lesson ("one
    interrupted process away from leaving a mutated repo"), which is what makes it worth writing
    down twice. Now a system temp dir, and the selftest **asserts** it leaves no file behind.
  - **`chain_lengths` recursed while `_cycle_in`, three functions up, deliberately did not** — the
    same module inconsistent with itself, so the deep-chain case was handled in exactly one of the
    two places it matters. Now iterative, pinned by a **1500-issue chain** that raises
    `RecursionError` on the old code.
  - **The rewrite then introduced a worse bug than the one it fixed.** Recursion got cycle-safety
    free by writing a provisional length before recursing; the iterative version dropped that, so a
    cyclic graph looped **forever**. Nothing in the review found it — `mutation_check` did, by
    disabling cycle detection and watching the run hang. A hang is a far worse failure than a wrong
    number on a graph that is already a filing error. Fixed with a `visiting` set and its own
    fixture. Selftest **40 → 43**, `mutation_check` **53 → 54**.
- **NEW `.github/pull_request_template.md`** — the maintenance rules a PR is judged against now
  arrive *in* the PR instead of having to be remembered from CLAUDE.md. It makes the change-type
  classification an explicit tick (silence is not a claim of exemption), demands the citation or
  the linked maintainer decision that the chosen type requires, and carries the checks a reviewer
  would otherwise have to ask for: gates run with every skip justified (**a skip is not a pass**),
  a new guard shipping with a selftest *and* a declared mutation, near-miss negative tests for
  carve-outs, repackaging after a `skills/**` edit, one CHANGELOG bullet per issue, and no version
  bump on `dev`. It also restates the closing-keyword rule below at the point of use. The template
  deliberately contains **no issue numbers at all** — its text becomes every future PR body, so a
  literal closing keyword beside a real number in it would reproduce that bug on every PR.
- **NEW `scripts/issue_graph.py` — the work queue is computed from declared edges, not re-reasoned**
  (#133). The tracker's dependencies (`#93 → #104 → #94/#90`, `#125 → #127`) lived as prose inside
  issue bodies, so "what should I work on next?" meant re-deriving the ordering by hand and getting a
  different answer each time. Issues now declare edges in a ```deps block (`depends-on` / `blocks` /
  `part-of`); the script reports **ready-now**, **blocked-by-what**, **critical path per epic**, and
  **priority-vs-graph contradictions in both directions** — including the costlier
  `low-priority-blocking-P1`. Wired into `/maintainer-triage` and `issue-triager`; format documented
  in `docs/issue-dependency-graph.md`. Design decision (our own format, no upstream) recorded on #133.
  - **The graph is a gate, the queue is advice.** A cycle, a dangling edge, a typo'd key or a
    declaration outside its fence exits non-zero and prints **no queue at all** — a ranked queue
    computed from a graph already known to be broken reads exactly like a correct one. Blocked work
    and priority contradictions only advise — fail closed for gates, fail open for advisories,
    stated as this tool's own contract. CLAUDE.md does **not** yet carry that rule generally (only
    "hooks fail open when a dependency is missing"), which is exactly what #132 exists to fix; the
    first draft of this entry cited it as settled doctrine, which was the `doctrine-contradiction`
    class in a PR about catching it.
  - **Requiring the `deps` tag is only safe because missing it is an error.** `depends_on: :owner` is
    a Rails association, so a bare fence cannot be told from a code sample — but silent strictness is
    the `gate-that-cannot-fail` class, so both near-misses are *reported*: a fence that is nothing but
    declarations under the wrong tag, and a declaration loose in prose. Both detectors stay narrow
    enough that "Blocks #94 and #90, but only once the schema lands" is silent; the selftest pins
    every rule in **both** directions. 40 checks, `mutation_check` **30 → 40**.
  - A full `gh` page is treated as an **error, not a total**: `--limit` bounds a query but proves
    nothing about truncation, and a truncated tracker turns real edges into phantom "not in the
    tracker" errors (#211).
- **`docs/` and `CLAUDE.md` were never linted, and CLAUDE.md is where the release commands live**
  (found while adding the doc above). Both markdown linters defaulted to `plugins skills .claude`, so
  the `release_local.sh`, `package_core.py` and `maintainer_doctor.py` invocations a maintainer copies
  verbatim had never been syntax-checked — a `coverage-gap` in the tooling whose entire purpose is
  catching them. Roots extended; **shell blocks checked 71 → 96**. `CHANGELOG.md` stays excluded on
  purpose (an append-only history, not instructions anyone runs — a gate failing on a command quoted
  in a 2026-07 entry is one nobody may act on), and that boundary is now stated in the code.
  - **A fence inside a blockquote was invisible to both linters.** The `^[ \t]*` anchor cannot see
    past `> `, which surfaced honestly as `parsed 0, present 1` on CHANGELOG.md rather than as a
    silent skip. Blockquote markers are now stripped line-by-line, so line numbers still point at the
    real file — and `iter_blocks` reads through the same helper as the coverage reconciliation, since
    counting a block as parsed while never linting it reports cleaner coverage than it delivers.
- **The `mutation coverage` gate could not see a new RULE added to an existing guard** — so a rule
  shipped with no mutation behind it, and only review caught it. The gate asserts every *guard*
  declares mutations; `lint_self_consistency` already declared twelve, so #100's new
  `broken-doc-pointer` rule sailed through green. A guard-level count is blind to a rule-level gap.
  - **Now checked structurally, per rule**: which function does each mutation's anchor live in, and
    which rules does that function emit? Any rule emitted by a function no mutation touches is a
    failure. Deliberately *not* done by matching fixture labels — `expects` is matched as a substring
    of the whole selftest output, so a label comparison both misses real coverage and invents gaps.
    The first version did exactly that and reported six false gaps.
  - **It immediately found a genuine pre-existing hole: the two ORIGINAL rules** —
    `dead-settings-key` and `unenforced-mandatory-flag` — had fixtures but **never had mutations**,
    from the day `mutation_check.py` was written. Three rules later, nothing had noticed. Both now
    have one.
  - `mutation_check` **43 → 47** mutations across 8 guards; its selftest **67 → 69** checks.

- **FIX — a skip was masquerading as a pass in the gate added hours earlier.** `lint_markdown_code.py`
  fails open when `node` or `ruby` is absent, printing a SKIP notice — but it **exited 0**, so
  `maintainer_doctor.py` printed `[ ok ] gate: markdown code lint` while **242 of 276 blocks went
  unchecked**. On a cloud container without Ruby — the normal state for a web session — the sweep
  would have read fully green over a gate that checked 12% of its input. That is precisely the
  three-state failure the doctor exists to prevent, reintroduced by the newest gate.
  - The linter now exits **3** for "ran, but could not check everything", distinct from 0 (clean) and
    1 (findings), and the doctor maps 3 to **SKIP** with the gate's own reason. Its selftest does the
    same rather than FAILing: a selftest that cannot run is not a broken selftest, and it is not a
    pass either.
  - **Found by simulating the container**, not by reading the code — a stub `ruby` on `PATH` was
    enough to show the green line over an 88%-unchecked run.

- **A commit message explaining the closing-keyword rule triggered the very bug it described.** The
  commit said, in prose and inside backticks, that a promotion had wrongly used a closing keyword on
  issue 95. GitHub parses the pattern **wherever it appears** — context, backticks and intent are
  irrelevant — so when that commit reached `main` via the v1.41.0 promotion it **closed issue 95 for
  the second time in one day**, twenty-six minutes after it was reopened. CLAUDE.md now says: never
  write a closing keyword next to a real issue number in a commit message or PR body, even when
  quoting a mistake; use a placeholder number or name the issue separately from the keyword. The
  existing prose in CLAUDE.md was reworded to stop modelling the dangerous shape.

### 1.22.0 — 2026-07-30

- **An umbrella issue was closed by a promotion that shipped one of its groups** — and the rule that
  allowed it is now written down. #95's body says *"Ship in sub-releases, one group at a time"* and
  carries a checklist; a closing keyword on it in the v1.37.0 promotion retired it with **seven rows still
  undocumented**, after which **four further slices landed against a closed issue**. CLAUDE.md's
  promotion section now says plainly: an issue that ships incrementally gets `Refs`, never `Closes`,
  until its last increment — and to check the body for unticked boxes before writing `Closes`. #95 is
  reopened with the remaining seven rows enumerated.

### 2026-07-30 — the fences are syntax-checked, and invisible characters are caught

- **NEW rule `invisible-character`** (#95) — no invisible or confusable whitespace in anything we
  ship. Two no-break spaces reached a shipped behaviour table, and the way they surfaced is the whole
  argument: an anchored edit failed with *0 matches* against a string copied from the file. A reader
  searching the doctrine for that phrase silently gets nothing.
  - **Only characters with no legitimate use are listed** — the em dash, en dash, ellipsis, arrows,
    check marks and box-drawing we use deliberately are not. That boundary is pinned by a near-miss
    fixture, and writing it taught something: my fixture put a **THIN SPACE** among the
    "punctuation we use on purpose" and the rule fired. The corpus contains none, so the **fixture** was
    wrong, not the rule — a thin space breaks grep exactly like a no-break space. Kept in the set.
  - 174 shipped files scanned; `mutation_check` **28 → 30**.
- **NEW `scripts/lint_markdown_code.py` — the JS, Ruby and ERB in our fences is now syntax-checked**
  (#248). `lint_markdown_shell.py` covered fenced *bash* only, and the other languages are the larger
  surface: **154 ruby, 85 erb, 22 js** blocks against 79 bash, all of it code an agent pastes into a
  user's project. Wired as three gates (lint, coverage, selftest); sweep **27 → 29**.
  - **Four real copy-paste hazards in shipped skills, every one of which raises on paste.** A bare
    `rescue … end` with no `begin` and no enclosing method (`observability.md`); two prose-as-code lines
    where `/` is division, not a separator — `Product.select(:id, :name) / .pluck(:name)`
    (`models.md`); and two `stimulus.md` blocks mixing a `static` class field with `this.` statements,
    which cannot share a scope. The Stimulus blocks now show the accessors **inside the method that
    uses them**, which parses and documents better.
  - **The linter's own first run was 26 findings, 22 of them its fault** — and that is the useful part
    to record. `<%= form_with … do |f| %>` and `<%==` are **invalid in stdlib ERB**: Rails compiles
    views with **erubi**. Depending on erubi would make the gate pass or fail by machine, so both are
    normalised away. A linter that fires on the most common idiom in the corpus is one that gets
    deleted rather than fixed.
  - **`js` matched the `js` in ` ```json `**, so every JSON block was being parsed as JavaScript. The
    `--audit-coverage` control caught it — that regex already had the word boundary and the strict one
    did not. Worth noting the direction: this was an **over**-matching extractor, which is as dishonest
    as an under-matching one, and the audit was written for the latter.
  - **ERB does not error on an unterminated `<%`** — it emits the remainder as a **literal string**, so
    the expression silently never runs and the view renders text where a value belongs. An explicit
    balance check now catches it; the compiler never will. `<%%` is correctly treated as an escape.
  - **False positives are the whole risk, so the selftest is mostly silence fixtures** — 27 checks, of
    which 14 assert the linter stays *quiet* on elisions, fragments and erubi idioms. Blocks are
    normalised and then tried in a short **named ladder of contexts** (bare, class body, method body,
    object literal); each run prints which context accepted each block, so a ladder that stops
    discriminating is visible rather than silent.
  - **`mutation_check` 23 → 28.** Two of the six mutations I first declared were wrong in instructive
    ways: one fixture was **vacuous** (`<%%= foo %>` still has a `%>` later in the line, so misreading
    the escape changed nothing), and one mutation was **unobservable** (`export` is a SyntaxError inside
    every wrapper, so removing that skip cannot change a verdict — it is an optimisation, not a guard,
    and the comment now says so). The checker caught both, which is why it exists.
  - **The selftest had to be made hermetic.** It reconciled the two regexes against the real tree, but
    it runs against a mutated copy in a temp directory where `skills/` does not exist — so `discover()`
    raised and every mutation was "caught" by a traceback instead of by its fixture. **A crash is not a
    verdict.** The real tree is still reconciled, on every run and by the coverage gate.

### 2026-07-30 — the icon rule flagged its own doctrine, and a promoted row kept its workaround

- **`lint_self_consistency.py`: the icon rule flagged prose that stated the icon rule** (#95). A
  paren-less `lucide_icon` scan read the words after the call as its arguments, so the comment
  *"lucide_icon takes no `size:`/`class:`"* — written to warn readers off exactly that — became a
  finding. The rule now requires the text to **look like an argument list** (a literal, or an identifier
  followed by a comma) before inspecting it. This is the second instance of the class in this file: the
  same false positive was fixed in `unbounded-issue-query`, where a CHANGELOG mention read as an
  invocation. **Near-miss fixtures pin both edges** — prose is silent, while a call whose first argument
  is a variable or a symbol is still flagged, so the carve-out cannot become a hole.
- **NEW guard — a promoted coverage row must not keep its "until the entry lands" fallback** (#95).
  `BUILD` holds the nearest safe workaround for a `needs doctrine` row. Once the row is `documented`
  that text tells readers to build the workaround instead of using the doctrine, and it is **invisible
  in the rendered table** (documented rows print `—` in that column), so nothing surfaced it. The
  Combobox entry outlived its own promotion this way, still saying *"use the documented Select until the
  entry lands"* after the Combobox entry had shipped. Deleted, and the guard keys on **status**, not on
  the name appearing — pinned by a near-miss fixture where a `needs doctrine` row legitimately carries
  one.
- **`mutation_check.py`: 19 → 23 mutations**, covering both new guards and both of their carve-outs.
  Writing them found a third defect of the same family: the new fixture's `build=` argument was accepted
  by `expect_error` and then **not passed through** to the guard, so the fixture ran against the real
  table and could not have failed. The selftest caught it, which is the harness doing its job.

### 2026-07-30 — the verification discipline becomes enforced rather than remembered (#233)

Fifteen defects surfaced in one session: eleven predated it, four were mine. **Two of my four were
caught by the maintainer, not by me**, and both had one cause — I wrote fixtures and did not revert the
code to check they failed, which is the repo's own rule and one I had cited in the same PR. Stating a
discipline and skipping it under momentum is not a knowledge gap, so three things now enforce it.

- **`CLAUDE.md`: an issue body is not an authority.** The gate was written about *editing* doctrine;
  nothing said *do not treat a spec written in an issue as verified*. #142 nearly shipped a fabricated
  APG citation because its contract read as one — four keybindings attributed to a pattern that does
  not contain them, traceable to a 2017 draft, deleted since. It also **omitted** a requirement APG
  states plainly, so the rule says to read for omissions too. And where a claim has no upstream (APG
  has no Command palette or Stepper pattern), an INCONCLUSIVE verdict means a recorded maintainer
  decision, never a citation invented to fill the gap.
- **The sibling-blind-spot sweep found the rules sound, and one boundary worth stating.** #182 fixed a
  paren-less blind spot for the icon rule and never carried it to two render siblings — six releases
  unfixed — so every regex-based rule was probed against its idiomatic alternative form. All held.
  Notably **one probe was wrong rather than the rule**: `_SOFTENED` looked broken until I checked its
  actual vocabulary, so I nearly filed a false finding against a working guard. The one real gap is now
  documented rather than accidental: the unbounded-query rule deliberately excludes `gh api` collection
  iteration, because that risk profile is ~1000 rather than 30 and firing correctly would need
  judgement about which endpoints return collections — which is how a linter becomes noisy.
- **NEW `scripts/mutation_check.py` — nothing verified that a selftest can fail.** Six selftests, 14
  gates, and no check that any of them notices its subject breaking. That is the hole both vacuous
  fixtures fell through. Each guard now declares hand-chosen mutations with the fixture expected to
  trip: **16 mutations across 6 guards**, including the exact defects from this session (`:id` matching
  greedily, duplicate signatures accepted, a truncated line crashing the parse, full-page evidence for a
  component purpose, the paren-less render regex).
  - **Deliberately not a general mutation framework.** No AST rewriting, no operator taxonomy — a
    declared list is auditable, whereas generated survivors nobody triages are indistinguishable from a
    pass.
  - **A stale anchor is a hard error, not a pass.** A mutation that does not apply produces a mutant
    identical to the original, which passes and reads exactly like a caught mutation.
  - **A coincidental catch does not count.** Each mutation names the fixture that must trip, or a
    fixture going quiet is masked by its neighbour.
  - It found **three defects in itself on its first run**: two `expects` written as the finding's
    message text, which is absent by definition once a mutation makes that finding disappear (the
    fixture *label* is the right expectation), and one malformed mutation that crashed rather than
    cleanly disabling its check. A fourth surfaced when `maintainer_doctor`'s mutant died on a missing
    `.gitignore` — the checker now mirrors repo-relative layout instead of flattening it.
  - Its own selftest (27 checks) pins that a survivor is reported, a stale or ambiguous anchor raises,
    a wrong-fixture catch is refused, and every declared anchor still matches exactly once — so the
    mutation list cannot rot into vacuous passes.
- Sweep is now **16 gates / 27 checks**, ~43s. **Stated stopping condition: this is the last layer.** A
  fourth would be guards on guards on guards, and the real backlog is 29 `needs doctrine` rows. This one
  earns its place only because it would have caught defects that actually shipped.

### 2026-07-30 — the gate-sweep completeness rule earned itself

- The rule added yesterday — *every `*_selftest.py` must be reachable from `GATES`* — **fired on the
  next script added**, catching `evidence_manifest_selftest.py` before it could be forgotten. That
  is the difference between fixing an omission and preventing the class: nobody had to remember.
  The sweep is now 14 gates.

### 2026-07-30 — a selftest the gate sweep never ran (found by #119)

- **`maintainer_doctor.py --gates` silently omitted selftests.** Adding `route_coverage.py` showed
  it: the new selftest passed locally while the doctor's sweep never executed it, so `--gates`
  would report a clean machine having skipped a whole gate. The doctor's selftest now asserts that
  **every `*_selftest.py` in the repo is reachable from `GATES`** — and on its first run it found a
  second omission nobody had noticed: the doctor was not running **its own** selftest either. Both
  are wired in; the sweep is 13 gates.
- This is the `coverage-gap` class from `skills/code-review/SKILL.md` — a check exercised against
  only part of what it covers — applied to the thing that runs the checks. Cheap to pin, and it
  cannot silently regress the next time a script is added.

### 2026-07-30 — an unbounded `gh issue list` made dedupe read a truncated tracker (#211)

- **Found because I reported a wrong number to the maintainer.** I said "30 open issues"; there were
  **42**. `gh issue list` defaults to `--limit 30`, and I had dropped the explicit limit and reported
  the page as the total — `unverified-negative` from our own `code-review` skill, *"reporting a count
  from a list you did not read to the end"*, committed while holding that rule in context. The
  maintainer caught it.
- **Grepping for the pattern found it shipped in two places**, per the rule that this class travels
  in groups:
  - `.claude/agents/issue-triager.md:44` — **duplicate detection**. It could conclude "no duplicate
    exists" having read 30 of 42 issues, then label and queue the duplicate it exists to prevent.
    This is the one with teeth.
  - `.claude/commands/maintainer-audit.md:23` — per-component clustering, where *"clustered reports
    point at systemic gaps"* was read off a truncated list. Latent today (largest component is 17)
    but it grows into a real defect silently.
  - Correctly bounded already, which is why the SessionStart count was right all along while mine was
    not: `maintainer-status.sh` (`--limit 200`), `maintainer-triage.md` (100),
    `maintainer-onboard.md` (20), and both rails-flow call sites.
- **New `unbounded-issue-query` rule in `lint_self_consistency.py`**, because both instances were
  **inline in prose** rather than in fenced blocks — so `lint_markdown_shell.py` structurally cannot
  see them, and a rule left in prose gets violated again (I am the existence proof).
  - **Known-answer calibrated:** run against `dev`'s tree it reproduces *both* shipped defects, and
    is clean on the fixed tree having examined 7 real invocations.
  - **It grades invocations, not mentions.** The first version fired on `CHANGELOG.md:674` — *"the
    command only ever saw `gh issue list` before"* — which is **history**, and a rule demanding that
    past records be rewritten gets overridden and then catches nothing. Requiring at least one flag
    fixed it without a per-file exemption to keep honest; both real defects carried one (`--search`,
    `--label`). Two near-miss fixtures pin both halves: a bare prose mention stays silent, and the
    same file still fires when it documents a real unbounded invocation, so the narrowing is about
    invocation shape rather than trusting a filename.
  - `--paginate` counts as bounded: it fetches every page, so it bounds nothing but truncates
    nothing — a correct answer to the same question.

### 2026-07-30 — related issues are worked on one branch (#206)

- **The written rule contradicted the productive practice.** `CLAUDE.md:31` said take "**ONE** issue
  end-to-end", and `maintainer-work.md` said it twice more ("One issue at a time", "One at a time").
  But some issues are one change wearing several numbers: #109 and #110 are both qa-flow, both under
  EPIC #108, and both edit the same boot/validation path — split, they are two PRs editing the same
  lines where the second cannot be reviewed without the first. Grouping related issues covers more
  ground per branch and is the only honest shape for that case.
- **Maintainer decision** recorded on [#206](https://github.com/fmanimashaun/claude-skills/issues/206),
  which is where the authority for a process change belongs — an architecture/process decision with no
  upstream to cite, so the doctrine-verifier gate does not apply (CLAUDE.md, *What the gate covers*).
  Grouping is now the **default for related work**, not an exception, with "related" carrying real
  weight: same `comp:*` label, one coherent mechanism (same files or code path), the same change type
  under the doctrine gate, and still reviewable in one sitting. No fixed cap on issue count — if the
  fixes never touch each other, grouping only widens a revert's blast radius, so split.
- **The gate condition is the one that is not a judgement call.** Grouping inherits *Split a mixed
  change* rather than weakening it: if one issue needs a CONFIRMED `doctrine-verifier` verdict and
  another does not, they do not share a branch. That is the loophole this rule could otherwise open —
  an architecture change carrying a framework claim through on its coat-tails.
- **Traceability is never pooled**, which is what makes grouping safe rather than sloppy: one
  `Refs #n` per issue in the PR body, **one CHANGELOG bullet per issue** rather than one for the
  group, and a separate `Closes #n` for each on the promotion, so each closes on its own merit. Pool
  them and you lose which fix answered which report, and the promotion cannot say what it shipped.
- Recorded in three places that previously disagreed: `CLAUDE.md`'s maintenance-flow section (with a
  new *Grouping related issues on one branch* subsection), and `maintainer-work.md`'s frontmatter and
  body. Its Phase 4 now also spells out the per-issue `Refs`/CHANGELOG requirement, since that is
  where pooling would actually happen.

### 2026-07-30 — CLAUDE.md's list of what we ship omitted a whole plugin (#203)

- **Found by following this file's own rule, and it was worse than the report.** #203 was filed for
  a stale count — `CLAUDE.md:136` said the release publishes "the two `.skill` assets" when there
  are **four**. I noticed it only because I had copied that figure into user-facing v1.30.0 release
  notes and then hashed the actual assets. CLAUDE.md says *when you find one instance of a
  contradiction, grep for the pattern — that class travels in groups*. It did:
  - `CLAUDE.md:6` — "**four** app-builder plugins", listing `rails-stack`, `rails-flow`, `qa-flow`,
    `pipeline`. There are **five**; `design-flow` was missing, and appeared **nowhere in CLAUDE.md
    at all** — zero mentions. The section is the definition of what this repo distributes, so
    anything orienting from it could not learn the plugin existed.
  - `CLAUDE.md:6` also described `rails-stack` as "the rails-8 + hotwire skills". It bundles
    **four**: rails-8, hotwire, fidara-design, code-review.
  - `CLAUDE.md:16` — "you want the four plugins".
  - `README.md:600` — "The **four** plugins above", while README's own heading twelve screens
    earlier says *five plugins, one marketplace*. The repo contradicted itself in one file.
- **Fixed with wording that cannot go stale where possible.** The release now publishes "**every**
  `dist/*.skill` asset (a glob, never a hand-typed list — that is how a release silently drops a
  newly added skill)", which is what `release.yml` and `release_local.sh` actually do. Subset
  references lost their counts rather than gaining new ones to maintain.
- **New `undocumented-plugin` rule in `lint_self_consistency.py`**: every plugin declared in
  `.claude-plugin/marketplace.json` must be named in both `CLAUDE.md` and `README.md`. A plugin
  absent from those is invisible to one of the two audiences — the maintainer (or agent) orienting
  from CLAUDE.md, or the user reading README.
  - **Known-answer calibrated**, per the #182 precedent: run against `dev`'s tree it reproduces the
    exact defect that shipped — *"plugin 'design-flow' is declared in marketplace.json but never
    named in CLAUDE.md"* — and is clean on the fixed tree having examined 5 declared plugins, so
    the green is not vacuous.
  - **Counts are deliberately NOT checked.** Prose legitimately refers to subsets ("the plugins
    above help you build apps"), so matching "four plugins" against the real total would fire on
    correct writing. By this repo's own thesis a linter that cries wolf gets switched off and then
    catches nothing, so the rule tests name presence, which needs no judgement. A near-miss fixture
    pins this: a manifest of two plugins with prose saying "the one plugin above" must stay silent.
  - A tree with no `marketplace.json` yields **no verdict** rather than findings, so the rule cannot
    fire on input it is unable to judge.
  - **Its limit is stated rather than overclaimed, because mutation-testing found it.** The rule
    proves a name appears *somewhere* in the file, not that it appears in the list enumerating what
    ships — deleting `design-flow` from CLAUDE.md's list left the linter green, since a neighbouring
    sentence still named it. Locating "the right section" needs judgement about where sections begin
    and end, which is how a mechanical rule becomes a noisy one, so the narrow guarantee is the
    honest one: it catches a plugin documented **nowhere**, which is precisely what shipped
    (design-flow had zero mentions). Verified by removing every mention and watching it block. My
    first draft of the CLAUDE.md note claimed the linter "asserts every declared plugin is named
    **here**" — the same claims-vs-enforcement defect, in the line added to fix one; corrected to
    say the list itself is still the maintainer's responsibility.

### 2026-07-29 — the corpora ignore rules now match the layout we prescribe (#197)

- **The corpora ignore rules could not match the layout our own setup instructions prescribed
  (#197).** `.gitignore` guarded the licensed kits with `everylayout/`, `tailwind-ui/`,
  `flowbite*/` — **directory-only patterns**, because a trailing slash matches a real directory
  while git stores a symlink as mode `120000`. CLAUDE.md told maintainers to attach the corpora
  "with a clone plus links", so following the documented setup left all three **untracked and
  unignored**, printed by `git status` directly beneath the warning about 656 MB of licensed blobs
  the rule could not actually stop. Reproduced before fixing: `git check-ignore` exited 1 for all
  three. `claims-vs-enforcement` — and the only thing between it and a real incident was
  CLAUDE.md's "never `git add -A` blindly", a human habit compensating for a broken mechanism.
- **One gitignored `design-corpora/` subfolder now, no symlinks.** Maintainer decision recorded on
  [#197](https://github.com/fmanimashaun/claude-skills/issues/197) — an architecture change, not an
  external claim, so the doctrine-verifier gate does not apply (CLAUDE.md, *What the gate covers*).
  It removes the failure mode rather than patching it: one ignored path instead of three, nothing
  to link, and the Windows directory-junction special case disappears from doctrine (symlinks need
  Developer Mode there). `scripts/build_coverage.py` is the only reader, so the path change is one
  line; the pre-#197 root names stay ignored as insurance for machines still on that layout.
- **The rule is re-checkable now, not remembered.** `maintainer_doctor.py` gained `corpora ignore
  rules`, asserting 7 paths are ignored and 4 near-misses are not. It probes a throwaway repo
  seeded with our real `.gitignore`, against paths that **do not exist** — deliberately, because a
  trailing-slash pattern *does* match a real directory, so probing the real path on a machine that
  has the corpora would pass under both the correct and the buggy pattern and hide the regression.
  That form also subsumes the symlink case, so nothing is created and Windows needs no privileges.
  The probe is isolated from global/system git config, or a maintainer's personal
  `core.excludesFile` could make the guard pass regardless of what we ship — a fail-open inside the
  check for a fail-open — and `git check-ignore` exiting 128 reports SKIP, never "not ignored".
- **Negative tests, because the original rule was written, believed, and matched nothing.** The
  doctor's selftest now runs the pre-#197 `.gitignore` verbatim and requires a FAIL that both names
  the unignored path and says to drop the slash; a missing `.gitignore` fails closed; and an
  over-broad pattern that would swallow `coverage.md` — silently disabling the drift guard — is
  caught from the other direction.
- **Corrected an assertion that had become too broad.** The doctor's selftest banned *any* check
  whose name contains "corpora" from reporting PASS while the kits were absent. Right when the only
  such check was presence; wrong now, since `corpora ignore rules` reads patterns rather than kits
  and must still reach a verdict on a machine that never cloned them. Banning the substring would
  have forced the new check to lie or rename itself to dodge the rule, so both halves are pinned
  separately — stronger than the blanket ban, and the exemption is not a hole.
- **`lint_self_consistency.py` prunes `design-corpora/`.** With the kits inside the tree it walked
  ~125 third-party markdown files, checking OUR claims against vendor CHANGELOGs, where a finding
  would be false and unactionable. It stayed silent only by luck — no vendor README matches the
  mandatory-flag regex. The old symlink layout got this for free, since `os.walk` does not follow
  symlinks. Pruned by exact name, with a near-miss proving a `design-corpora-notes/` of ours is
  still scanned.
- **"OPTIONAL" was false for anyone running the full sweep.** Found while checking my own wording
  against behaviour: `maintainer_doctor.py --gates` ran `build_coverage.py --check` unconditionally,
  so a corpora-less machine got `[ FAIL ] gate: coverage matrix drift` and the verdict *"fix the
  failures above before doing maintenance work"* — about a licensed 656 MB download nobody is
  required to have. A gate that **cannot** run is not a broken machine; that is the mirror image of
  the SKIP-as-PASS bug the doctor exists to prevent. The drift gate now SKIPs with the clone remedy
  when the kits are absent (`20 passed, 0 failed, 2 skipped`, exit 0) and still runs, and still
  fails on real drift, when they are present — verified by making `coverage.md` stale on purpose.
  The exemption is keyed by gate name, so the selftest pins that every name exists in `GATES` (a
  rename would silently lapse the exemption) and that no gate which *can* run is exempted.
- `.claude/commands/maintainer-onboard.md` promised the doctor prints a "clone-and-symlink remedy";
  it prints a clone-only remedy now.

### 2026-07-29 — a new maintainer machine is set up by a script, not by remembering (#199)

- Moving maintenance to a second machine needed a hand-written ~120-line briefing, and it was only
  complete because the author had just hit every trap in one session: a fresh clone lands on
  **`main`**; an idle clone's **stale local `main` ref** makes the prescribed `git diff dev main`
  check report phantom deletions (5,231 of them); the licensed corpora need attaching; and
  `git status --porcelain` **collapses a new untracked directory**, so a new file reads as nothing.
- A checklist in prose would be the same **claims-vs-enforcement** defect this file keeps warning
  about, so `scripts/maintainer_doctor.py` is a script that can fail. `/maintainer-onboard` wraps it
  with the judgement half.
- **Three outcomes, not two.** `pass`, `fail` and **`skip`** are distinct, because a check that did
  not run is not a check that passed. That conflation was a live bug: `build_coverage.py --selftest`
  printed "35 checks passed" on a corpora-less machine while two checks against the real repo
  silently did nothing — inert guards reading green. Now `33 passed, 2 SKIPPED` with the reason.
- **It earned its place on its first real run**, flagging that local `main` sat two releases behind
  `origin/main` — unnoticed, and the same defect that produced the 5,231 phantom deletions earlier
  the same day.
- **A diagnostic must not mutate the repo.** `check_dist_clean` has to rebuild to know anything, and
  `package_core.py` writes into `dist/` with no output-dir flag, so it snapshots and restores
  byte-for-byte. The first version skipped the restore and was idempotent only *because* the packer
  is byte-deterministic — true today, incidental rather than guaranteed, and it would have silently
  destroyed intentional uncommitted `dist/` edits.
- `--fix` touches exactly two things (fast-forward the local `main` ref; check out/pull `dev`) and
  never rewrites history, `reset --hard` or `clean`. Every FAIL and SKIP names a remedy — a fault
  without a fix is a complaint, and the reader is the person who does not yet know what to do.
- **Windows uses directory junctions** for the corpora, not `ln -s`, which needs developer mode.
- 29 selftest assertions against real bare-remote-plus-clone git fixtures; **7 deliberate mutations
  each caught**, including dropping the `dist/` restore and reporting corpora absence as a pass.
- Two defects the review process caught rather than the code: the doctor's own `check_branch`
  treated `dev` as a clean pass, so it would have blessed editing directly on the integration
  branch — which is exactly what the author was doing while writing it; and the first `stale_main`
  test fixture set local `main` to a commit that *was* `origin/main`, so the check looked broken
  when the fixture was.

### 2026-07-29 — doctrine call sites are checked by a linter, not by remembering (#182)
- **Seven instances of one class in two days, and zero permanent enforcement.** Skills are doctrine
  other agents follow verbatim, so a call site naming an API that does not exist is generated code
  that raises in a user's project: `--grid-min` for `--min`, `with_rail` for `with_sidebar`,
  `FieldComponent.new(form:, attribute:)`, `lucide_icon(..., class: "size-4")`, `d.with_item` for
  `items:`, plus the two that **shipped** — `FieldComponent.new(form:, name:, label:)` and
  `field_classes` for `input_classes`. Five were caught by throwaway scripts written in the moment
  and discarded; two reached users. Ad-hoc catching is not enforcement, which is the same lesson as
  #151 and #171.
- **New third rule in `lint_self_consistency.py`**: wrong initializer keywords (per component, only
  where the initializer is documented — an undocumented one is #168's coverage gap, a different
  finding), undeclared slots, and the icon call shape.
- **Known-answer calibrated:** run against `v1.24.0` it reproduces the exact defect that shipped —
  *"FieldComponent.new called with ['form', 'name'] but its initializer accepts ['error', 'for_id',
  'hint', 'label']"* — and is clean on current `dev` having examined 40 skill docs and 16 declared
  components, so the clean result is not vacuous.
- **Two false-positive classes were found and fixed by its own selftest, which is the point.**
  The first version matched every `.with_*` in the corpus and produced **six false positives against
  one real finding** — `with_lock`, `with_connection`, `with_instructions`, `with_temperature`,
  `with_tool`, `with_schema` are ActiveRecord and ruby_llm idioms, not slots — so slot checks are now
  scoped to the receiver of a `render(...) do |v|` block. The icon check then flagged the doctrine's
  **own correct example**, because `tag.span(helpers.lucide_icon("x"), class: "with-icon")` passes
  `class:` to the wrapper, not the icon; it now matches parentheses to inspect only the call's own
  arguments. A linter that cries wolf gets disabled, which is precisely the failure it exists to
  prevent.
- It also caught that the rule initially required parentheses, so it would **not** have caught the
  violation that motivated it (`lucide_icon "chevron-right", class: "size-4"` — the paren-less form
  ERB actually uses). Both call forms are covered now.
- Coverage printing was hard-coded to three counters, so the new rule's inputs were invisible on a
  clean run — every counter is printed now, because a clean result over input a rule never read
  reads as a pass.

### 2026-07-29 — the packager stops depending on your working copy (#171)
- **The prescribed check was satisfiable while producing the drift it exists to prevent.**
  `.gitattributes` is `* text=auto eol=lf` with `*.skill binary`, so git normalises sources to LF on
  commit but stores the artifact byte-for-byte. Packaging a freshly authored file on Windows (CRLF in
  the working copy) produced an archive carrying CRs its own committed sources did not have — 424
  bytes' worth in #94 — while `git status` showed only the intended `dist/` change, so CLAUDE.md's
  instruction passed. It runs *before* the normalisation that creates the mismatch. The drift then
  surfaced at release time, where `release.yml` correctly refused to publish.
- **`package_core.py` now normalises text members itself**, so the guarantee is "byte-identical on any
  machine" rather than "byte-identical from a clean checkout" — it no longer depends on remembering
  anything, which is the only kind of guarantee this repo trusts.
- **Binary detection is git's own heuristic** (a NUL byte in the first 8000 bytes), deliberately not an
  extension allowlist: an allowlist needs maintaining and **fails open**, so the first file type nobody
  added would silently revert to the original bug. A future `.png` in a brand pack is protected without
  anyone listing it. Only `CRLF` is converted, matching git's `eol=lf`; a lone `CR` is left alone.
- **Proven behaviour-preserving, not asserted.** With the change in place all four `.skill` files
  rebuild **byte-identical** to what was already committed — clean input has LF, so a correct
  implementation changes nothing there. Then the original bug was reproduced end to end: all 39 sources
  CRLF-ified (the #94 condition), and every artifact still built byte-identical to the committed
  version.
- **`--selftest` makes it mechanical** (11 assertions): CRLF and LF working copies build identical
  bytes; a NUL-bearing member with `\r\n` inside is stored unmodified (the fixture naive normalisation
  would corrupt); text members carry no CR; entries stay `ZIP_STORED` with `create_system` pinned and
  timestamps fixed. Two bugs in that selftest were caught while writing it — an incoherent assertion,
  and one scanning the whole archive for `\r` when a ZIP's CRC and size fields can legitimately contain
  `0x0D`, which would have failed spuriously.

### 2026-07-29 — doctrine effect becomes measurable (#156), and the reviewer moves in-repo (#162)
- **The asymmetry this closes.** Doctrine *content* has a hard gate: nothing is edited until
  `doctrine-verifier` confirms it against an authoritative source. Doctrine *effect* had none.
  "The rails-8 skill produces better Rails" lived entirely in prose — the one layer this repo
  otherwise refuses to trust. New `evals/` measures whether loading the skills changes what an
  agent writes. Secondary benefit, possibly the larger one: **a doctrine edit that makes agent
  output worse was undetectable**; a regression is now visible.
- **Runner is `claude -p`, not the Anthropic API.** The obvious build pastes `SKILL.md` into an
  API `system` field — clean, cheap, and measuring the wrong thing. These skills ship as Claude
  Code *plugins*, so a pasted system prompt is a proxy for how they load; a result from it would
  not be evidence about what `/plugin marketplace add` actually gives a user. Consequence worth
  having: **no Anthropic API dependency**, so the harness stays stdlib-only Python with no
  `requirements.txt` and nothing for CI to install.
- **Two gates specified in #156 were wrong, and would have manufactured false regressions.**
  (a) The issue asked for an "ids only" job gate; `jobs-and-realtime.md:28` says the opposite —
  `def perform(order)  # pass records, not ids: GlobalID (de)serializes them`. An ids-only rule
  fails the doctrine's own reference example, so the real-skill arm would have scored *worse* than
  baseline and "proven" our doctrine harmful. Only idempotence is gated (`:176`). (b) A naive
  no-hex rule flags our own `Ui::Logo`, which `brand.md:87` names as "the only component permitted
  to carry literal colors"; the carve-out is encoded. Generalised as a standing rule that
  `selftest.py` asserts: **a gate must pass against the doctrine's own reference examples — if it
  fails what `references/*.md` shows as correct, the rule is wrong, not the doctrine.**
- **A third rule needed fairness, not correction.** `form_with` is correct stock Rails, and
  `ecosystem-gems.md:29` makes simple_form conditional ("dozens of uniform CRUD forms"). So
  `scaffold.py` establishes the convention (Gemfile entry + initializer) and the gate **refuses to
  judge** when it is absent, rather than punishing an agent for writing correct Rails.
- **Gates vs measurements, kept separate.** Six named rules, each citing the doctrine file:line it
  enforces, are grep/parse pass/fail. Cost, wall-clock, output tokens, and turn count are recorded
  and never judged — "less code" is trivially gamed by emitting something broken. A run that
  errored, hit the API error path, or was blocked by a permission prompt is **INVALID** and
  excluded from scoring: scoring infrastructure trouble as a doctrine failure invents a regression.
- **Isolation is asserted, not assumed.** Runs never execute in this repo — our `CLAUDE.md` would
  load into *every* arm, contaminating all three identically and drifting the result toward "no
  difference" without looking broken. `scaffold.py` refuses to run when an ancestor holds a
  `CLAUDE.md`, when a non-home ancestor holds `.claude/`, or when `~/.claude/skills/` is non-empty
  (skills-dir plugins auto-load into every session). Tools are restricted to
  `Read,Write,Edit,Glob,Grep` — no Bash, no network.
- **Verified without spending anything on a benchmark.** `selftest.py` — 38 assertions, every rule
  proven to fire on a violation *and* stay silent on conforming code (a rule that flags everything
  looks rigorous and makes all arms fail equally). `run.py --dry-run` prints all 15 invocations and
  executes none. The staged `real` arm passes `claude plugin validate` with all three skills
  (14/3/17 references) and no maintainer `.claude/` leaked. **No results are published**, and the
  README's results table is deliberately empty pending authorisation.
- **Deliberately disposable runner.** `claude plugin eval` already does this properly
  (`--ablation with-without`, `--runs`, `--threshold`, `--json`, `--max-cost-usd`, HTML reports)
  but is in early access and unavailable here. The durable assets are `cases/*/prompt.md`,
  `gates.py`, and `selftest.py`; when early access opens, point it at `evals/` and delete `run.py`.
  Metadata is `suite.json`, not `case.yaml`, because `yaml` is not in the stdlib.
- **Out of the release path.** Nothing wired into CI. It costs money, it is opt-in, and it must
  never gate a promotion.
- **Four bugs found in review, all in the new harness** (#161). Two would have corrupted results in
  opposite directions: (a) `read_lines()` promised Ruby comment handling but only blanked ERB
  comments, so a palette note in a `.rb` component (`# cerulean is #0077CC`) was reported as a
  violation — a false regression. Stripping is now quote-state-aware (the token we hunt for *is*
  `#`, so splitting on the first one would have deleted every violation) and applied to `.rb` only,
  never `.erb`, where a bare `#` is HTML text and blanking to end-of-line would hide violations
  after it. (b) The `Ui::Logo` carve-out matched any path containing `logo`, making it a one-line
  bypass — name a partial `logo.html.erb` and hardcode anything. Now an explicit allowlist of the
  component's canonical paths. Plus: `--max-total-usd` is **enforced** rather than merely
  documented (a live run without it refuses to start), and `max_turns` is removed from `suite.json`
  because the CLI exposes no `--max-turns` — a declared condition nothing enforces is worse than an
  absent one, so turn count is measured and spend is bounded by the budget ceilings instead.
  Selftest grew 32 → 38 assertions.
- **The realisation.** A trial reviewer kept finding a class of bug our own review missed,
  and it had no proprietary advantage: **it checked the diff against rules already written in
  this codebase's markdown.** Its finding on #161 was literally "missing change-type
  classification" — verbatim from `CLAUDE.md`; others were our own README and `suite.json`
  contradicting our own code. The capability was never rented; the rules were always here,
  nothing was *asking* them of a diff.
- **The class.** Every existing review dimension asks *"is this code correct?"*. The misses all
  came from a different question: *"does this code do what its own documentation, config and
  comments claim?"* Correct-looking code passes the first and fails the second — and the author
  cannot see it, because they read the claim and the code as one thing.
- **`claims-vs-enforcement` has now bitten three times in three PRs**: `--check || echo` making a
  release gate unable to block (#151); a README mandating `--max-total-usd` while the flag stayed
  optional (#161); a docstring promising Ruby-comment handling the code lacked (#161). Writing the
  rule down does not prevent it — the thesis of `lint_markdown_shell.py`, now pointed at our claims.
- **New `scripts/lint_self_consistency.py`** (stdlib, free, no LLM) mechanises the judgement-free
  subset: `dead-settings-key` (a key in a JSON settings block no reader reads) and
  `unenforced-mandatory-flag` (a flag documented as mandatory that code leaves optional).
  **Known-answer calibrated:** run against the pre-fix commit it independently reproduces 2 of the
  5 trial-reviewer findings; against the post-fix commit it is silent with the same inputs
  examined. `--selftest` (8 assertions) proves both rules fire *and* stay silent — a rule that
  flags everything gets disabled after the third false positive and then catches nothing. Its own
  selftest caught a real limitation during authoring: the guard regex hardcoded `parser.error`, so
  it missed a guard on any parser not named `parser`.
- **Coverage is reported even when clean**, because "no findings" over input never read is worse
  than no linter — the `--audit-coverage` lesson, where a fence regex silently skipped 11 blocks.
- **The classes no machine catches became a shipped skill, not a `docs/` file.** First draft put
  them in `docs/review-rubric.md` *and* inline in two agent files — two homes for one doctrine,
  which is precisely the drift this repo exists to prevent, and `docs/` was referenced by nothing,
  so the discovery path that made the trial reviewer work (read the codebase's own markdown rules)
  never reached it. Now `skills/code-review/SKILL.md` is the single source:
  `carve-out-without-negative-test`, `coverage-gap`, `doctrine-contradiction`,
  `unverified-negative` (count first, then read), `gate-that-cannot-fail`. Every class is named and
  traceable to a real finding; a class with no instance behind it is speculation and is excluded.
- **Placing it in `skills/` is the load-bearing decision.** Rules a reviewer must find belong where
  reviewers already look, and as shipped doctrine it is the *same* rule set a user's `pr-reviewer`
  applies — so we are held to what we sell rather than keeping a private checklist.
- **Wired into `CLAUDE.md` and `/maintainer-work` Phase 3** — apply the class list to your own diff
  before asking anyone else to.


### 2026-07-29 — promotions get a two-step name and a divergence assertion
- **"Arm" vs "promote", named.** The v1.22.0 promotion used a branch called `release/v1.22.0`
  merging into **`dev`**, which reads as though `dev` publishes releases. It does not and cannot:
  the workflow triggers only on `push: branches: [main]` *and* re-checks
  `github.ref == 'refs/heads/main'` in the job — verified, zero workflow runs have ever originated
  on `dev`. But the naming made an invisible mechanism look wrong, so step 1 is now
  `chore/arm-vX.Y.Z` titled "version assignment (does not publish)", and `CLAUDE.md` states the two
  steps in a table with which one publishes.
- **A merge unions; it does not override.** Recorded as a correctness rule rather than tidiness:
  merging `dev → main` never removes content that exists only on `main`, so a direct commit there
  is permanently invisible to every future `dev`-based change. One such commit exists in this
  repo's history (`d4b35f6`, `enabledPlugins` in `.claude/settings.json`); it converged only
  because the same block later reached `dev` — luck, not a property of the merge.
  `release-manager` now asserts `git log --no-merges origin/dev..origin/main` before promoting.
- **How to read branch state.** Judge `dev` against `main` with `git diff dev main` (empty after a
  promotion), never the ahead/behind counter: `main` gains one merge commit per release that `dev`
  never receives, so `dev` reads as tens of commits "behind" while being content-identical.
  Merging `main` back into `dev` to tidy the counter is what produced 37 no-op merge commits on
  `dev` earlier in the week.

### 2026-07-29 — the shell inside markdown is now verified (root cause of #151)
- **The repo mandated `bash -n` for `.sh` files and shipped 194 unverified lines of bash inside
  markdown** — 51 fenced blocks across 30 command/skill files, the lines an agent copies and runs
  verbatim in a user's project. Three review findings in one week lived in that gap: the
  `--check || echo` that made the release gate unable to block (#151), the same file's guard
  conflating "no data" with "no tool", and design-flow's unresolvable lint path. Each was
  prose-reviewed and never executed. The #151 fix stated a rule ("a guard decides whether to run
  a check; it must never soften the verdict") — but a rule is not a guarantee, which is the one
  thing this repo's doctrine is explicit about.
- **New `scripts/lint_markdown_shell.py`** (stdlib only): extracts every fenced shell block and
  runs `bash -n` on it (template placeholders substituted first, since `<pack>` is a redirect to
  bash), then flags **swallowed verdicts** (`|| echo`/`|| true` on a verification command) and
  unquoted test operands. **Regression-proven**: run against `release.md` as shipped in v1.21.0 it
  reports the `--check || echo` at line 82 and exits 1; against the fixed file it exits 0.
- **`--audit-coverage`**, because the first version of the fence regex **silently skipped 11 blocks
  in 7 files** by anchoring ` ``` ` to column 1 — blocks nested in numbered lists are indented. A
  lint that reports clean on input it never read is worse than no lint, so coverage is now
  cross-checked against an independent looser scan and a gap is a failure. (Same column-1
  assumption `brand_pack_lint` had; second time it bit.)
- Wired into `CLAUDE.md`, `/maintainer-work` Phase 3, and `plugin-doctor`, so it runs without
  being remembered.
- **Coverage is reconciled on every run, not on request.** `--audit-coverage` was a separate
  command, so a future tweak to the fence regex could still quietly reduce coverage while the
  default run reported clean — the same defect one level up. Every run now cross-checks the strict
  parser against an independent looser scan and **refuses to report clean when they disagree**.
  Proven with a fence the strict regex cannot parse (inside a blockquote) that contains a real
  swallowed verdict: the tool exits 1 saying a clean result would be meaningless, where before it
  printed "no findings".
- Four bugs were found *in the linter itself* while proving it, all silent-failure shaped: `bash -n
  <tempfile>` broke under Git Bash (mangled Windows path → every block a false syntax error);
  `text=True` encoded stdin as cp1252 and crashed on a `✓`; a nonexistent path reported "0 files,
  no findings" instead of erroring; and `\bverify\b` matched inside `pipeline-verify`, flagging an
  idempotent `docker rm … || true`. Worth recording that three separate escaping mistakes wrote
  literal control characters (`\b`, TAB) into the source via heredoc patching — invisible in
  output, and the regex matched nothing. Author code with an editor, not with nested string layers.

### 2026-07-28 — the doctrine gate gets an explicit scope
- The verification gate said "no skill claim is edited until `doctrine-verifier` confirms it against
  an authoritative source", without stating what counts as a claim. Our own architecture decisions
  (the brand-pack model, the role contract, distribution policy) have **no upstream to cite**, so
  the verifier returns INCONCLUSIVE for want of a source — and "INCONCLUSIVE leaves doctrine
  unchanged" would then block our own decisions permanently. The exemption was therefore being
  decided per PR by whoever wrote it, which is precisely what a gate exists to prevent. Review
  flagged it on #149; the finding was correct.
- `CLAUDE.md` now scopes it: the gate covers **externally verifiable claims** (framework/gem
  behaviour at a stated version); for **design/architecture** changes the authority is the
  maintainer's explicit decision **recorded on the issue** — the durable equivalent of a citation.
  Four rules stop that becoming a loophole: declare which kind of change you are making *before*
  editing; split a mixed PR so a framework claim still needs CONFIRMED; reuse established framework
  syntax rather than inventing it (new API *is* an external claim); and measure anything measurable
  against the repo's own files with a re-checkable script.

### 2026-07-22 — README brought to four-plugin fidelity
- The README documented only rails-stack + rails-flow; qa-flow and pipeline (the
  entire test + deploy half) were absent, which made fetched/summarized views report
  "2 plugins" and confused tooling. Rewrote (513→628 lines): added a top-of-file
  four-plugin architecture overview table, full qa-flow section (verify/certify two
  moments, mechanical dev→main gate, PR Documentation Contract), full pipeline section
  (Docker-image-as-release-artifact on ghcr, /pipeline:deploy-cloud .env-routing model,
  frugal git-hook nudges, platform note), and updated the install block to all four in
  dependency order. No functional change; metadata 1.4.5.

### 2026-07-22 — remove root-level plugin file duplicates
- 14 stale plugin files (agents, commands, hook scripts, plus a stale
  marketplace.json and orphan hooks.json) had been committed to the REPO ROOT by
  an early "Add files via upload" web drag-drop, duplicating — at frozen old
  versions — the canonical files under plugins/**/ and .claude-plugin/. Removed all
  14 (each verified to have a canonical copy first). Hardened .gitignore with
  root-anchored patterns (/*.sh, /hooks.json, /marketplace.json, /plugin.json) so
  plugin files can only live under plugins/** and .claude-plugin/**, never the root.
  No canonical file touched; marketplace remains 1.4.4 with all four plugins.

## skill-maintainer (marketplace maintenance plugin)

> **Relocated to repo-local `.claude/` in v1.6.8** (the short-lived separate marketplace
> from v1.6.7 was reverted and deleted). The entries below are its history as a
> distributed plugin; it now lives in `.claude/` as this repo's own maintainer tooling —
> see `CLAUDE.md`.

### 1.0.1 — 2026-07-23
- Fix #4: separate this maintainer-only plugin from the app-builder install surface.
  Manifest descriptions (marketplace entry + plugin.json) now lead with a hard
  "⚠ MAINTAINERS ONLY — do NOT install into app projects" marker, so the `/plugin` browse
  surface itself carries the warning (not just README prose). All four commands
  (`setup-intake`, `triage`, `work`, `audit`) gained a hard repo-type precondition:
  they refuse to mutate anything unless `.claude-plugin/marketplace.json` exists at the
  repo root (reusing the SessionStart hook's test) — so a mis-install can't scaffold
  marketplace issue-templates/labels into an app repo. README made consistent: the plugin
  table row is badged maintainers-only and the plugin's own README leads with the caveat
  instead of a bare install recipe.

### 1.0.0 — 2026-07-23
- New fifth plugin: the maintenance side of the loop — downstream projects report
  issues as they hit them, and this flow ships source-verified fixes. Marketplace
  1.6.0.
- 4 commands: `/skill-maintainer:setup-intake` (scaffold GitHub issue templates + a
  label taxonomy, idempotent), `:triage` (classify open issues by component × type ×
  priority, label, dedupe, queue), `:work` (one issue end-to-end: confirm → verify →
  fix → PR `Closes #n` → bump + CHANGELOG → release), `:audit` (proactive
  source-of-truth review, files findings as issues).
- 5 agents: `issue-triager` (classify/label only), `doctrine-verifier` (BLOCKING gate —
  no skill claim is edited without an authoritative citation; verification precedes
  edits, INCONCLUSIVE leaves doctrine unchanged), `skill-doctor` (edits skill
  references on a CONFIRMED verdict, then repackages via `package_core.py`),
  `plugin-doctor` (fixes plugin agents/commands/hooks; `bash -n` + behavior repro +
  all-paths-intact before hand-off), `release-manager` (independent component
  versioning, CHANGELOG, reproducible packaging, tagged release).
- SessionStart status hook surfaces the open-issue signal (P1 / incorrect-doctrine
  counts); read-only, non-blocking, fails open when `gh` is absent.
- Repo intake (dogfood): `.github/ISSUE_TEMPLATE/` forms (incorrect-doctrine — requires
  a citation, skill-gap, plugin-bug, packaging, feature) + `config.yml` (usage
  questions → Discussions) + `.github/labels.yml` taxonomy.

## rails-flow (agentic flow plugin)

### 1.22.2 — 2026-08-08

- **The four unguarded scripts are guarded** — `check_criteria`, `extract_claims`, `findings`,
  `self_consistency`. They were flagged in the last release and not fixed, which is the half-measure
  this repo's own doctrine forbids: a gap named and left is a gap nobody is accountable for.

  Every target and every `expects` was found **empirically** — mutation applied, selftest run,
  failure line read — because guessing had already failed three times in this repo: twice naming the
  *pass* message instead of the *failure* message, and once naming a line the selftest never
  exercised. Registering a guard for `self_consistency` then triggered the meta-gate's stricter rule
  — once a guard exists, **every** rule that script emits needs a declared mutation — so
  `swallowed-verdict`, `dead-env-var` and `assertion-free-spec` were covered too. A partial guard is
  worse than none, because it looks covered.

  The harness also caught **drift**: a mutation still targeting a line the group-affordability
  rewrite had deleted. It reported the mutation list had drifted from the code it mutates, which is
  precisely what that check is for.

### 1.22.1 — 2026-08-08

- **Pillars 1 and 3 had selftests but no mutation coverage** (Refs #488). Their fixtures ran; nothing
  proved those fixtures could fail. Found while verifying #488's *"each pillar independently
  acceptance-tested"* against the repo rather than against memory — the `mutation coverage` gate
  proves every **declared** mutation is caught, and never that everything testable is declared, so
  two shipped pillars sat uncovered without anything going red.

  Each now has the mutation that matters most. `toolchain_version`: the newest install record stops
  winning, so a **stale** version reads as installed — the one thing pillar 1 exists to catch.
  `escalation`: the marker matches anywhere instead of at the start, so a **quoted** question reads
  as agent-authored and the thread parks forever.

  Registering them took three attempts, each a defect worth naming. The first target was indented by
  four spaces and I copied eight, having counted my own terminal prefix as source. The second matched
  a real line yet the harness saw nothing, because `"\ufeff"` inside a normal Python string is
  **evaluated at parse time** — the file held the right characters while the runtime value held an
  actual U+FEFF. A raw string fixes it. The same invisible-character class has now bitten twice in
  this repo, and both times the file looked correct.

  **Four more scripts remain unguarded** — `check_criteria`, `extract_claims`, `findings`,
  `self_consistency` — all pre-dating this EPIC. Named here rather than silently left, because a
  count nobody wrote down is how this went unnoticed in the first place.

### 1.22.0 — 2026-08-08

- **Reverted: `setup-flow` no longer scaffolds a permission allowlist.** It was added hours earlier
  and is being taken out again on the maintainer's call, which is the right one — a plugin has no
  business configuring a user's permissions, and the advice was self-contradicting: the same passage
  said *"for no friction at all, choose a permission mode deliberately rather than extending a list
  of binaries"* and then shipped 38 lines of list-building. If a run should be unattended, that is a
  **mode** decision the user makes once, not a list a scaffold grows on their behalf.

- **The driver stopped to ask when it had work it could do** (Refs #488). Reported from a real run: a
  scope-flagged enhancement was first in the backlog, so the driver escalated and halted — while a QA
  pass that needed no permission at all sat available beside it. The EPIC is explicit that an
  escalation must **not block the run**: park it and move to other independent work.

  It now collects every candidate the ladder offers and returns the first the policy lets it take
  **alone**, keeping the first escalation as a fallback for when nothing autonomous remains. A later
  issue it may actually do beats an earlier one it may not. Over-asking is the failure the
  decision-rights matrix exists to prevent — it just wears the clothes of caution.

- **Scope could enter through the `fix-issue` door, and a real run found it** (Refs #488). Rights
  were keyed on the ACTION alone: every open issue becomes `fix-issue`, which needs only
  `pick-next-backlog-item` — so an issue whose own body called it *"a distinct auth-hardening
  feature"* routed to **decide**. The `build-feature` escalate gate was never reached, because the
  work never called itself a feature; it called itself an issue. The required right is now the
  maximum of what the action needs and **what the item is**, matched case-insensitively across
  `enhancement` / `feature` / `roadmap` / `epic` and their `type:` forms. A bare issue number still
  decides but is flagged `nature_unverified` — its labels could not be read, and silence there would
  reopen the hole for hand-written state.

- **`compose_state.py` — the driver reads reality instead of a hand-typed file** (Refs #488). The
  same run put it plainly: *"I had to be the loop by hand."* Issues come from a **bounded** `gh`
  query, `run_stopped` from the breaker's own ledger (never re-derived — two safety systems that
  disagree resolve in favour of the permissive one), plus parked escalations and verification
  stamps. It reports; it never decides, because a composer that also decided could quietly prefer
  the state justifying the action it wanted.

- **Actionability and ordering were decisions the toolchain was making by accident.** Blocked,
  env-gated and deploy-time issues are excluded **with their reason** and still reported as
  `declined_issues` — *"the backlog is empty"* and *"everything left is blocked"* are different
  sentences and only one means you are finished. The breaker is a backstop for work that turns out
  impossible, not a substitute for reading the label that already said so. Ordering is now stated —
  priority label, then age — because *"first element wins"* **is** a prioritisation policy, and the
  toolchain had one while refusing to say what it was. Unprioritised sorts **last**, so forgetting a
  label cannot promote work.

- **`/rails-flow:setup-flow` now scaffolds a permission allowlist** (§2c). Without one an unattended
  run stops for confirmation every few commands and stops being unattended. The cause is not
  obvious: agent commands are **compound pipelines**, the whole string is evaluated, so **one**
  unlisted binary anywhere in the chain re-prompts all of it — a list with `bin/rails` and `bundle`
  but no `grep` still prompts on most real commands. It writes to the committed
  `settings.example.json` for the user to copy, **merges rather than overwrites**, and deliberately
  omits `rm`, `curl`, `wget`, `kill`, `chmod` and package installers: those are exactly the actions
  whose blast radius outlives the run, so a prompt is correct friction even mid-run.

### 1.21.0 — 2026-08-08

- **Pillars 2 and 4 of the autonomous flow driver** (Refs #488). `/rails-flow:drive` answers exactly
  two questions per tick — what is next, and may I do it alone. It chooses **one** action, never a
  menu: a driver returning three options has handed the decision back to the human it exists to
  spare. Three conditions outrank the work ladder, in order — the breaker has stopped the run, the
  budget is spent, an escalation is parked awaiting a reply.

- **It does NOT re-implement the circuit breakers, and that is the load-bearing decision.**
  `breaker.py` already owns attempt caps, the no-progress detector, the four forbidden escapes, the
  elapsed and blast-radius limits and the complete/partial/stopped verdict — all of #128's doctrine,
  already selftested and mutated. A second set here could **disagree** with the first, and when two
  safety systems disagree the more permissive one wins. Run-level stops stay the breaker's answer,
  and a mutation proves the driver cannot work past one.

- **The decision-rights matrix is configurable, and rots safe rather than permissive.** Two rules do
  that work: an **unclassified action escalates** — defaulting it to *decide* would let the policy
  grow permissive by omission, one unconsidered action at a time — and a **policy with no `escalate`
  list is refused**, because that is full autonomy wearing a config file. The test that keeps this
  checkable rather than a vibe is *"does it publish, or can it not be undone"*, which is readable
  from the action itself, unlike *"is this important"*.

- **Pillar 4: craft is autonomous, scope is not**, and the line is not size. A redesign that leaves
  every journey intact is craft; the same redesign that quietly drops a step is scope wearing a
  visual diff — the case worth being slow about precisely because it looks like the first one in
  review. Scope changes pass IA-before-code and escalate through pillar 3; every creative or scope
  call is recorded as a brain decision, because autonomy without an audit trail is an unexplained
  diff.

  The mutation harness found **two real defects** in this script that its own selftest passed over. A
  mutation **survived** because a `right is None` branch was redundant — the final `return "unknown"`
  already covered it, so removing it changed nothing and proved nothing; the branch is gone and the
  mutation now targets the load-bearing return. And a second mutation was caught **by the wrong
  fixture**: removing the policy guard raised `KeyError` instead of refusing, so the selftest crashed
  rather than failing the assertion written for it. A crash is not a verdict, so the loader degrades
  now and the fixture catches a wrong answer instead of an exception.

### 1.20.0 — 2026-08-07

- **Pillar 3 of the autonomous flow driver: the async human-in-the-loop** (Refs #488).
  `/rails-flow:escalate` posts a question as a comment on the relevant issue, labels it so GitHub
  emails the human, records the thread in `docs/brain/.escalations.json`, and **moves on**. A later
  `--poll` finds the reply and resumes from it. Nothing blocks; state survives a restart.

  **Two API facts broke the design as sketched**, both verified against the real API:

  1. **The agent and the human have the same login.** `gh` authenticates with the user's own token,
     so a comment the flow posts comes back authored by the repo owner — confirmed identical to
     `gh api user`. The EPIC's *"fetch comments since its question (by timestamp/**author**)"* can
     therefore never work: excluding the owner excludes the human too, and not excluding them makes
     the flow answer its own question. Replies are found by an **invisible marker** the flow stamps
     on its own comments. The marker must be at the *start* — a human quoting the question
     reproduces it behind a `> `, and reading that as flow-authored would strand the thread parked
     forever, the one failure this loop cannot recover from by itself.
  2. **A missing label errors; it does not degrade.** `gh issue edit --add-label` applies nothing
     when the label is absent — the same defect `unprovisioned-label` exists to catch (#487, #490).
     Here it is worst-case: the label is what sends the email, so the flow would park believing it
     had asked while nobody was ever told. `awaiting-input` and `answered` are created before
     anything is posted, and **if they cannot be created the escalation is not sent**.

  Deliberately *not* a signal: an **edited** comment. Only `createdAt` counts, because `updatedAt`
  also moves when the flow edits its own comment, and a typo fix on an old comment would resume with
  an "answer" predating the question. A thread left parked is visible and recoverable; a false
  resume is not.

  38 paired assertions and five mutations — `startswith` weakened to `in`, the marker check dropped,
  parking allowed after a failed label, the timestamp filter dropped, an unlabelled post treated as
  sent — each caught by the fixture named for it. Registered in the doctor's gate sweep.

  Recorded as a **maintainer decision**: the API shapes are observed and reproduced as fixtures; the
  policy (fail rather than park unlabelled, ignore edits, never fail a poll for want of an answer) is
  ours.

- **Pillar 1 of the autonomous flow driver: the toolchain self-update gate** (Refs #488).
  `/rails-flow:toolchain-check` resolves what is installed, compares it against what is published,
  and carries a durable marker across the restart an update requires — so the driver never begins
  unattended work on a stale toolchain. Three states, and the third is the point: **exit 2 (could not
  resolve one side) is never folded into exit 0**, because "I could not read the installed state" is
  not "you are up to date".

  **Five substrate facts corrected the issue's design sketch**, each found by reading the real files.
  All five fail in the *silent* direction — reporting a stale toolchain as current:

  1. `known_marketplaces.json` records **no version** — only `source`, `installLocation`,
     `lastUpdated`. The installed marketplace version is one level down, in
     `<installLocation>/.claude-plugin/marketplace.json`.
  2. `installed_plugins.json` maps each plugin to a **list** of install records, not one. Two versions
     coexist in the cache — the machine this was written on held rails-flow at **both 1.19.0 and
     1.18.2**, same scope, separable only by `lastUpdated`. `[0]` or `[-1]` picks arbitrarily.
  3. **Four of five** plugin entries in `marketplace.json` carry no `version` key.
  4. Because the two sources are **disjoint, not redundant**: `rails-stack` is a skills bundle with no
     plugin directory and is versioned *only* in `marketplace.json`; the four code plugins are
     versioned *only* in their own `plugin.json`. Read either alone and you miss the other set.
  5. The drift was **live while this was written** — installed 1.72.0 against a published 1.73.0.

  Recorded as a **maintainer decision**, not a framework claim: the shapes above are observed facts
  about Claude Code's on-disk state, verified on this machine and reproduced as selftest fixtures, and
  the gate's policy choices (fail-closed on a plugin behind target, tolerate landing *ahead* of it,
  clear the marker only on success) are ours.

  28 paired assertions, and **five mutations** — `newest_record` returning `records[0]`, dropping the
  `plugin.json` fallback, folding exit 2 into 0, clearing the marker unconditionally, and comparing
  versions lexically — each caught by the fixture named for it. Registered in the doctor's gate sweep,
  which is how the repo's own `mutation coverage` gate caught it running **nowhere**.

### 1.19.0 — 2026-08-06

- **`project_gates.py` now says whose tracker each finding belongs to** (Refs #485). The four
  states said *what happened*, never *where the fix goes* — and the summary added ERRORs into the
  same `N failed` total as real findings, so a manifest of ours naming a script of ours that is not
  there read to a user as a defect in their own app. Every non-pass outcome is now routed and the
  counts are separated: a **FAIL** to the project (`app`, the detector ran and found something), an
  **ERROR** or an unparseable manifest **upstream** (`doctrine`, the check produced no verdict at
  all and project content cannot cause that — handed to `/rails-flow:report`), a missing `requires`
  binary to neither (`environment`). Not-applicable is routed **nowhere**, which is
  "not applicable is not a pass" one step later. `--json` carries the destination and its reason on
  every non-pass row (`null` on a pass) so an agent acts on the routing instead of re-deriving it
  from prose. **Change type:
  architecture** — the taxonomy is ours, not an upstream framework claim; decision recorded on
  [#485](https://github.com/fmanimashaun/claude-skills/issues/485). Scope stated rather than
  implied: a FAIL routing to `app` is a **default, not a proof** — the archetype that motivated the
  issue (doctrine mandates a `#toasts` container that our own setup never emits) is a FAIL that
  belongs upstream, and telling it apart needs the per-plugin conformance detectors of #485(a),
  which this does not ship. 21 new selftest assertions, and each carve-out carries its near-miss:
  declaring `requires` must not exempt a check from its own findings. Every branch was proven to
  fail by mutation — collapsing `route_of` to always answer `app` trips five of them. Also fixes a
  stale count found in the same docstring: it claimed the plugins "ship eleven checks" while the
  three manifests declare fifteen. Replaced with no number rather than a fresh one, since a count
  restated outside the manifests is the thing that went stale.

### 1.18.2 — 2026-08-05

- **The same defect, in a second plugin** (Refs #490). `pr-comments.md:41` folds an out-of-scope
  review comment into the user's tracker with `--label "from-pr-review"`, which no setup step
  created — so the item was lost and the instruction to *"reply on the thread with the new issue
  link"* could not be followed. Found by grepping the pattern after confirming #487, per CLAUDE.md.
  `setup-flow` §8b now creates it. The labels `claude-skills-reporter` passes are **not** affected:
  they target the upstream tracker with `--repo`, where the taxonomy is somebody else's.

### 1.18.1 — 2026-08-02

- **Two of rails-flow's five gates were permanent silent skips, for the same reason as qa-flow's**
  (#423). Found by the reconciliation gate written for the qa-flow half, on its first run —
  filing them instead of fixing them would have meant registering a gate that fails.
  - **`human-guide` waited on `docs/guides/` and globbed `docs/guides/*.md`.** No such directory
    exists anywhere in the toolchain: the artefact is a single file, `docs/GUIDE.md`, written by
    `/rails-flow:explain` and named as such by `check_guide.py:4`, `doc-updater.md:42` and
    `explain.md:163`. So `check_guide.py` — the whole of #126 — has never run in a user's repo. Now
    `{match:docs/GUIDE.md}`, and it passes `--decisions docs/brain/DECISIONS.md` the way
    `product-brief` already does, so the "cite the decision log, do not restate it" rule is actually
    exercised rather than silently off.
  - **`architecture-graph-drift` waited on `docs/architecture.md`.** `architecture_graph.py` writes
    a *directory* — `docs/architecture/{graph.json,index.html,graph.md}` (`--out` default
    `docs/architecture`), and its own drift message names `docs/architecture/graph.json`. Now
    `applies_when: ["app", "docs/architecture/graph.json"]`, which is the artefact `--check`
    compares.

### 1.18.0 — 2026-08-01

- **A vague ask now becomes a buildable brief, and the brief is an index over its sources rather
  than a copy of them** (#130). New `/rails-flow:brief` writes `docs/brain/BRIEF.md`: the intake
  artefact that gates a client engagement, run **before** `/rails-flow:setup-flow`. It detects
  which of three situations it is in — documents exist, code exists, or greenfield — **ingests
  first**, reports a coverage map of what the sources already answer, and interviews only the
  genuine gaps. **Change type: design / architecture.** The brief's shape, the coverage vocabulary,
  the citation syntax and the duplication rule are our own decisions about our own toolchain; no
  upstream exists to cite, so the authority is the maintainer decision recorded on
  [#130](https://github.com/fmanimashaun/claude-skills/issues/130#issuecomment-5152551963). **No
  framework claim rides along** — nothing here asserts how Rails, Hotwire, Claude Code or any gem
  behaves.
  - **The issue's citation format does not exist and could never have resolved.** #130 specified
    `PRD S7.2`-style references *"matching the citation convention already used in `docs/brain/`"*.
    `grep -rn "PRD S"` over this repo returns **nothing**: the brain uses `D-nnn` ids and the four
    provenance tags, and `PRD S7.2` names no file, so an agent following the issue verbatim would
    have shipped a citation style the toolchain does not use and that nothing could check. The
    syntax is therefore ours — `` `docs/prd.md` § "Pricing tiers" `` — a real path plus a string
    that literally occurs in that file, **and the checker opens the file and looks**. It carries
    code unchanged (`` `app/models/booking.rb` § "class Booking" ``), which is what lets one
    mechanism serve document intake and codebase intake instead of two.
  - **A fourth coverage state, because three could not describe greenfield.** The issue gives
    answered-with-source / thin / missing; a greenfield brief has no document to cite, so every row
    would have had to lie in the `answered` cell. A `decided` row cites a `D-nnn` that must exist in
    `docs/brain/DECISIONS.md` — which is what turns the issue's *"decisions … are written to
    DECISIONS.md"* from a hope into a checkable claim, reusing the `[decided]` provenance tag the
    brain already defines rather than inventing a fifth vocabulary.
  - **"Never duplicates an existing PRD" is measured, not requested** —
    `plugins/rails-flow/scripts/check_brief.py` (61-check selftest, 11 declared mutations, **five in
    the silence direction**), registered as the `rails-flow product brief` gate and in the plugin's
    `checks.json` so a user's own `project_gates.py` runs it. A 12-word contiguous run reproduced
    from a cited source is a finding. **Its whole risk is false positives**, because a brief and its
    PRD describe the same product in the same words: blockquotes, fenced code, table rows and
    headings are exempt, each with a near-miss fixture, since attributed quotation is the one place
    the brief is *supposed* to borrow and the coverage map's Source cell quotes the source's own
    heading by design. The checker also rejects a citation that resolves to nothing, an `answered`
    row with no source, a `decided` row with no `D-nnn`, non-goals that say "none", an open question
    with no owner, and a coverage gap recorded nowhere.
  - **Two rules shipped broken and the fixtures caught both**, which is the reason for the silent
    half. `\bnon-goal\b` does **not** match "Non-goals" — the `\b` fails against the trailing `s` —
    so `## Non-goals (out of scope)` was collected as the *scope* section and a brief with no scope
    section at all reported clean. And the mode cross-check read first the whole section and then
    the whole line, both of which always contained the expected word (`"**Mode: A — documents.**
    Intake read the documents first"`), so it could not fire; it now reads only the declaration
    clause. Neither was visible by reading.
  - **What is deliberately NOT enforced, said out loud rather than implied.** One-question-at-a-
    time, every question carrying a recommendation, and stopping when the first slice is decidable
    are runtime interview behaviour that leaves no trace in the artifact — tier 1 prose per
    [`docs/harness-doctrine.md`](docs/harness-doctrine.md) §1, and labelled as tier 1 in the command
    so nobody reads enforcement that does not exist. Success criteria are **not** graded for
    falsifiability here either: that is `check_criteria.py`'s job on `docs/acceptance/<slug>.md`, and
    enforcing one property twice at two fidelities is the second-source-of-truth failure this whole
    command exists to prevent.
  - **The self-containment rules are imported from `check_handoff.py`, not copied.** "What counts as
    a reference to the conversation" is one decision, and two copies of it would be exactly the
    doc-drift the checker polices, committed inside the checker. The import is a seam: with the
    module absent the rules report **UNVERIFIED**, never clean — a skip masquerading as a pass is
    the failure this repo has shipped twice. `TBD` is carved out of `## Open questions` and only
    there, because a recorded unknown with an owner is that section's job and an unrecorded one
    anywhere else is the defect.
  - Hands document distillation to `/rails-flow:curate` rather than reimplementing it.
- **`code-reviewer` now runs the quality pass as an explicitly second, explicitly non-blocking
  section** (#360). Without a call site the new `quality-pass` skill would be doctrine nothing
  points at. The wiring states both halves of its contract: it runs **after** the correctness
  review, and every finding it produces is a **Suggestion** — it can never reach a BLOCKING
  verdict. Deliberately **not** wired into `pr-reviewer`, which is the merge gate: a quality
  finding must not be able to refuse a merge, and the surest way to guarantee that is to keep it
  out of the agent that can.

### 1.16.0 — 2026-08-01

- **`extract_claims.py` — the half of `claim-verifier` that can actually be proven** (#359). Its
  acceptance criterion asked for fixtures showing the agent fires on a false claim and stays silent
  on a true one. **An agent is a prompt and has no fixtures**, so that criterion cannot be met by the
  agent alone — stating that is better than faking it.
  - Split the way everything else here is split: **the script extracts, the agent judges.** Pulling
    the claims out is mechanical and testable; deciding whether each is *true* is judgement.
  - **The silence half is what makes it usable.** It drops hedged and unfalsifiable sentences —
    "cleaner", "more idiomatic", "should be faster", "probably fixes" — because a verifier handed
    those has nothing to run, and a list of them trains everyone to skim the output. A hedge beats a
    keyword: *"this probably fixes the leak"* is not a causation claim.
  - Fenced code and inline code are skipped: a block full of `gate`, `fails` and `blocks` is
    identifiers, not assertions.
  - **A fixture was wrong, not the code.** *"Selftest 33 checks passed"* was asserted to be a
    *measurement*; it classifies as **enforcement**, correctly, because `selftest` is an enforcement
    keyword and the documented ordering says enforcement wins. Both readings are now pinned.
  - **A limitation found by running it on a real PR body, recorded rather than hidden.** It cannot
    tell a claim the change is *making* from one it is *quoting* — run against #361 it extracted two
    sentences from a table of previously **refuted** claims. Left unhandled deliberately: every
    available heuristic for "is this quoted?" also fires on real assertions, and dropping a genuine
    claim silently is the failure this tool exists to stop. **When in doubt it extracts**, and the
    agent is told to discard the quotes itself.

- **NEW `claim-verifier` — it verifies what a change says about itself, not the code** (#359).
  Borrowed from `fable-advisor` in `fcakyon/claude-codex-settings`: *"a second opinion **without
  substituting the host tool's model**… the reviewer checks load-bearing claims itself."*
  - **The failure it exists for is measured, not hypothetical.** Three defects shipped from this
    repository in one day — the gates ran nowhere automatically, the publish had no dependency on the
    sweep, and a scaffolded CI job referenced a variable that does not exist in Actions. **Every one
    was found by a human asking whether a claim was true**, and none by the forty gates. Twice the
    correct knowledge was already in the same file. Reviewing the diff would not have caught any of
    them, because each diff was internally consistent: **the defect was in the sentence describing
    it.**
  - It extracts enforcement, exhaustiveness, causation and measurement claims, then checks each by
    **running or grepping** — reading the code is explicitly not checking, because the claims are
    about behaviour. Three verdicts, and **UNVERIFIABLE is a finding**: a claim nobody can check
    should not be in a description.
  - **The issue asked for a third tier, and building it showed that was the wrong answer.** #359
    assumed the agent must be pinned to a different model, which `check_handoff.py` rejects twice —
    no tier maps to it, and `fable` is in `EXPENSIVE_ALIASES`. That second objection is
    **substantively correct**: pinning a *shipped* agent to an expensive alias spends a stranger's
    money on our authority, and a value outside their `availableModels` is skipped anyway. A pin
    cannot buy a second opinion; it can only impose a cost.
  - So it is `inherit` like every other judgement agent, and the mechanism moves where it belongs:
    getting a genuine second opinion is the **caller's** act, and the agent must **state which model
    it ran as** and say plainly when that matches the session. The tier vocabulary needed no third
    value — the mechanism was never the frontmatter. Recorded beside the table, because the row
    otherwise looks like an oversight.

### 1.15.1 — 2026-08-01

- **FIX — the CI job we scaffold into a user's repo could never run** (#334). `setup-flow` §8
  proposed a `doctrine` job whose step was
  `python3 "$CLAUDE_PLUGIN_ROOT/scripts/project_gates.py"`. **That variable does not exist in
  GitHub Actions** — it is set only inside Claude Code's own plugin context — so the job failed on
  every run with `can't open file '/scripts/project_gates.py'`. It shipped in the release whose
  stated purpose was putting guarantees in the deterministic layer.
  - **Nothing could have caught it, and that is the interesting part.** Our own workflows never
    reference that variable, so every gate we own was silent: *the workflow we test and the workflow
    we scaffold are different files.* It surfaced when a maintainer ran the command by hand.
  - **The correct knowledge was already in the same file, twelve lines below.** The
    architecture-graph job says plainly *"the script ships inside the plugin, which CI does not
    install"* and vendors a copy. I wrote the broken job anyway.
  - Fixed by checking the toolchain out **beside** the repo at a **pinned tag** — one checkout serves
    all four plugins, because the runner discovers each `checks.json` itself. Pinning is stated as
    mandatory: an unpinned `main` means our next release silently changes what a user's CI enforces.
  - **The two patterns now coexist explicitly.** Vendoring suits one self-contained file whose
    staleness is visible; a pinned checkout suits many scripts across four plugins, where vendoring
    would be four copies drifting independently.
- **NEW `plugin-root-in-ci` rule.** Scoped to ```yaml fences, which is where our docs put CI
  scaffolding. **Prose naming the variable is correct and common** — it is how an agent resolves a
  plugin path at runtime, and the same file legitimately says *"copy from
  `${CLAUDE_PLUGIN_ROOT}/scripts/x.py`"* — so matching anywhere would fire on that sentence and the
  rule would be deleted within a day. Four fixtures, two of them silence cases including a YAML
  **comment**. Assertions 73 → **77**.

### 1.15.0 — 2026-08-01

- **One CI entry point a Rails project can actually run** (#334). The plugins shipped **eleven**
  checks that run against a *user's* repo and **no way to run them together** — a user had to know
  each script existed, know which applied, and invoke each by hand, which in practice meant an agent
  ran them when it remembered. New `project_gates.py`, plus a `checks.json` per plugin so a check
  **registers itself** and the runner hardcodes nothing.
  - **Four states, not two: pass / FAIL / not-applicable / ERROR.** A project with no `qa/` reports
    the evidence checks as **not applicable**, printed loudly every run with the reason — a repo with
    zero evidence must not go the same green as a repo with complete evidence.
  - **A missing dependency FAILS rather than skipping**, because in CI a skip is indistinguishable
    from a pass. For the same reason `rendered_conformance.py` is deliberately **not** registered:
    it needs Playwright, which is the user's dependency, and a gate that quietly skips without a
    browser is worse than no gate.
  - **`setup-flow` §8 scaffolds it into the project's own `dev → main` CI** as an approved diff, and
    insists the deploy job declares `needs: doctrine`. A parallel job is *advisory* — it can go red
    after the deploy — which is a check that reports rather than a gate that stops.
  - **§8's rationale is corrected.** It justified scoping CI down partly with *"local hooks + qa-flow
    already proved it for feature → dev"*. That was an assumption, not a guarantee: if the agent did
    not run qa-flow, nothing proved anything. The Actions-minutes argument stands alone and stays.
  - **Two defects in my own work, both caught by mutating rather than reading.** I declared
    `evidence_manifest.py` with no arguments — it requires a subcommand, so it exited on a usage
    error; the runner correctly reported FAIL, but nothing would have caught the *manifest* before a
    user's first run. The assertion I added for it was then **vacuous** (`--help` exits 0 whether or
    not a subcommand is required) and only surfaced by re-introducing the bug and watching it pass.
    Its replacement reads the usage block for a subparser group, and was narrowed after it fired a
    **false positive** on `architecture_graph.py`'s `{json,md}` — a `--format` choice list, not a
    subcommand. A rule that fires on a correct manifest gets deleted, so the pattern was narrowed
    rather than the finding excused.

### 1.14.2 — 2026-08-01

- **FIX — a bare doc pointer is invisible to the lint.** `setup-flow` cited the rails-8 skill's
  `references/style.md`. Same shape, same fix, same reason.

### 1.14.1 — 2026-08-01

- **One tier checker now serves every plugin** (#299). `check_handoff.py`'s table markers were
  hardcoded to `rails-flow:tiers:*` and now match `<!-- <plugin>:tiers:begin -->` for any plugin,
  so qa-flow, design-flow and pipeline get reconciliation without a copy of the checker — four
  sources of truth for one contract being the failure this module's own comments warn about. A
  **half-renamed** block (opens `qa-flow`, closes `rails-flow`) is refused rather than reconciled
  against the wrong plugin's agents: that failure is created by the parameterisation, so it has
  its own fixture. Selftest 78 → **80**; rails-flow's own reconciliation is unchanged.

### 1.14.0 — 2026-07-31

- **FIX — `model-tiers.md` stated the wrong `opus` version for two named providers** (#127). Caught
  auditing `dev` against source, hours after the doctrine shipped. The paragraph grouped three
  providers for the `sonnet` alias — correctly, all three resolve to **Sonnet 4.5** — and then
  attached ***`opus` = Opus 4.6*** to the same group. Per the provider table in
  [Claude Code model configuration](https://code.claude.com/docs/en/model-config) (read 2026-07-31),
  `opus` is **Opus 5** on Amazon Bedrock and Google Cloud's Agent Platform, and **Opus 4.6** only on
  **Microsoft Foundry**. The paragraph also implied `sonnet` has two values when it has **three**:
  Sonnet 5 on the Anthropic API, **Sonnet 4.6** on Claude Platform on AWS, Sonnet 4.5 on the other
  three. Read that table **by row, not by group** — a note in the file now says so.
  - **The argument was right and only the illustration was wrong**, which is the more dangerous
    shape: the conclusion — *an alias is not a tier, so a shipped plugin cannot know which model its
    own frontmatter selects* — is fully supported, so nothing about the surrounding reasoning looks
    off and a reader has no prompt to check the numbers.
  - Grepped the pattern rather than fixing the one line, per the rule that a contradiction travels in
    groups. The CHANGELOG's own summary of the same verdict was **already correct** (it says
    Sonnet 4.5 on Bedrock and Foundry and makes no `opus` claim), so this was the only instance.
  - Everything else in that verdict re-verified verbatim against the same docs and holds: `model`
    *"Defaults to `inherit`"*; the four-step resolution order with frontmatter at 3 and *"The main
    conversation's model"* at 4; an excluded value *"skipped … runs the subagent on the inherited
    model instead"*; *"As of v2.1.198, Explore inherits the main conversation's model"*; and
    `effort`'s *"available levels depend on the model"*. So the seven `inherit` pins stand.

- **A unit of work now has a work order, and the model tiers are decided rather than accidental**
  (#127). New `/rails-flow:handoff` writes `docs/handoff/<slug>.md`: the one file an executor can run
  from with **no conversation history** — goal, the `AC-n` ids that grade it, files in *and explicitly
  out of* scope, the guardrails in play, the stop conditions, how to verify, what to record. New
  `plugins/rails-flow/reference/model-tiers.md` records which agent runs on which model and why. The
  design half is the maintainer decision recorded on
  [#127](https://github.com/fmanimashaun/claude-skills/issues/127#issuecomment-5146942862) (an
  architecture change to our own doctrine, so its authority is that decision, not an upstream
  citation); every claim about Claude Code's own behaviour is cited below.
  - **All ten agents' `model:` lines are now decided; seven of them changed, and the old value was
    backwards.** Verified 2026-07-31:
    frontmatter *beats* the session model in Claude Code's resolution order, so a pin is a **cap** —
    the seven agents pinned `sonnet` were **downgrading** every user who had deliberately started an
    Opus session, which is the opposite of what the issue asked for. Judgement agents (review,
    security, migrations, implementation, curation, reporting) now say `model: inherit`; the three
    mechanical ones (`test-runner`, `design-auditor`, `doc-updater`) keep `haiku` and each **names the
    external proof** that makes a cheap tier safe. The precedent is the platform's own: *"As of
    v2.1.198, Explore inherits the main conversation's model instead of always running on Haiku"*.
  - **The issue's three-row table has no mechanism, and that is now written down.** There is no "mid"
    model to select — the middle row is `effort` (`low`..`max`), a separate field. It is deliberately
    **not set**: *"available levels depend on the model"* and Claude Code does not publish which,
    so the value would be unverifiable. Recorded as the next lever rather than left silent.
  - **`docs/handoff/<slug>.md`, committed — both against the issue body**, which proposed a root
    `HANDOFF.md` and left committed-vs-gitignored open. Concurrent branches each have a work order, so
    a root file is overwritten by whichever touched it last: the artefact whose purpose is surviving a
    context switch would be the one thing that cannot. And a file a fresh clone does not have cannot
    fix loss of context between machines. The slug rule matches `docs/acceptance/<slug>.md` exactly.
  - **"Self-contained by construction" is enforced, not asserted** —
    `plugins/rails-flow/scripts/check_handoff.py` (78-check selftest, 7 declared mutations, **four in
    the silence direction**). It rejects a work order that points at the conversation, leaves
    `<placeholders>`/`TBD`, restates criteria instead of citing ids, cites an `AC-n` the acceptance
    file does not define, or whose stop conditions carry no number. Its second mode reconciles all ten
    agents against the tier table, so #127's "no agent silently contradicting it" cannot decay back
    into folklore. The Stop gate validates a work order **when one exists** and never demands one, so
    branches already in flight are unaffected.
  - **Verified against upstream, 2026-07-31** ([sub-agents](https://code.claude.com/docs/en/sub-agents),
    [model-config](https://code.claude.com/docs/en/model-config),
    [settings](https://code.claude.com/docs/en/settings),
    [skills](https://code.claude.com/docs/en/skills)): `model:` takes *"`sonnet`, `opus`, `haiku`,
    `fable`, a full model ID … or `inherit`. Defaults to `inherit`"*; resolution runs
    `CLAUDE_CODE_SUBAGENT_MODEL` → per-invocation parameter → *"the subagent definition's `model`
    frontmatter"* → *"the main conversation's model"*; a value outside the org's `availableModels` is
    skipped and the agent *"runs … on the inherited model instead"*, so pinning up buys nothing;
    `model` **is** honoured for plugin agents (only *"`hooks`, `mcpServers`, or `permissionMode`"* are
    ignored); aliases resolve per provider (`sonnet` is Sonnet 5 on the Anthropic API, **Sonnet 4.5**
    on Bedrock and Foundry) and *"update over time"*; plugin agents are priority *"5 (lowest)"* so a
    same-named file in `.claude/agents/` overrides ours; and a command's `model` *"applies for the
    rest of the current turn"*, which is why no command is pinned.
- **Unattended runs now have stop conditions instead of only guardrails** (#128, rails-flow half —
  see the decision record on
  [#128](https://github.com/fmanimashaun/claude-skills/issues/128#issuecomment-5146943177)). The hooks
  already stopped a run doing damage; nothing said when to **stop and escalate**, and an agent that
  cannot make progress does not idle, it digs — reverting its own fixes, loosening specs until they
  pass, widening scope around a blocker, each of which looks like activity in a log. Every work order
  now carries a numeric **attempt cap** (default 3), a **no-progress detector** (2 identical failure
  signatures), a **blast-radius cap** (10 files, never outside the declared scope), a **budget** with
  the remainder reported, and all four **forbidden escapes** enumerated — each individually checked,
  and each number required to *be* a number, because "stop when you are stuck" cannot be evaluated by
  the thing that is stuck. `feature.md` (Phase 3, Phase 7) and `fix.md` (*Unattended operation*) now
  require the final report to say **complete / partial / stopped** and name what was not attempted.
  Also documents that `maxTurns` is *"Maximum number of agentic turns before the subagent stops"*
  ([docs](https://code.claude.com/docs/en/sub-agents), 2026-07-31) — a **turn** bound, so it
  complements the attempt cap rather than replacing it. **The `comp:pipeline` half is not done**: no
  file under `plugins/pipeline/**` was touched, and each plugin resolves its own
  `${CLAUDE_PLUGIN_ROOT}`, so pipeline needs its own doctrine and its own checker.

### 1.13.0 — 2026-07-31

- **The flow can now explain a system back to the human who owns it** (#126). New
  `/rails-flow:explain` writes `docs/GUIDE.md`: plain-language sections, mermaid diagrams that
  render on GitHub, and a *"check it yourself"* block per area — the human-runnable form of the
  acceptance criteria. Every other artefact this toolchain produces is written for an agent, and
  `/rails-flow:curate` runs docs → skills; nothing ran the other way. The design half is the
  maintainer decision recorded on [#126](https://github.com/fmanimashaun/claude-skills/issues/126)
  (this is an architecture change to our own doctrine, so its authority is that decision, not an
  upstream citation); the mermaid half is externally verifiable and cited below.
  - **The guide is thin by construction, and that is the whole design.** It *links* to
    `docs/architecture/graph.md` for structure and `docs/brain/DECISIONS.md` (`D-nnn`) for
    rationale rather than restating either, because those are generated/digest-guarded and
    authored-once respectively, while the guide's prose can rot. Same reasoning as the capped
    `## Architecture Overview` in setup-flow §2: 37signals cut their own `AGENTS.md` from 166
    lines to 70 by deleting four claims that had drifted into being false
    ([fizzy #2999](https://github.com/basecamp/fizzy/pull/2999), 2026-07-28).
  - **Two claims in the issue body are now enforced rather than asserted**, via the new
    `plugins/rails-flow/scripts/check_guide.py` (47-check selftest, 5 declared mutations).
    "Idempotent, section-scoped updates" holds only while the managed markers are balanced, and
    "diagrams are mermaid (GitHub-renderable)" fails *silently* — GitHub shows an error box, and
    the diff is valid markdown either way. Both were `claims-vs-enforcement` waiting to happen.
  - **Verified against upstream, 2026-07-31.** Mermaid renders in *"GitHub Issues, GitHub
    Discussions, pull requests, wikis, and Markdown files"*
    ([GitHub docs](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-diagrams)),
    gists too ([changelog](https://github.blog/changelog/2022-02-28-gists-now-support-mermaid-diagrams/));
    a bare lowercase `end` *"will break the Flowchart"* and quoting is the documented fix for
    bracket characters ([mermaid](https://mermaid.js.org/syntax/flowchart.html)); `%%{init:...}%%`
    is *"deprecated from v10.5.0"* ([mermaid](https://mermaid.js.org/config/directives.html)).
  - **Three things checking refuted, and the doctrine says so.** `graph` is **not** deprecated in
    favour of `flowchart` — *"Instead of `flowchart` one can also use `graph`"*, no deprecation
    notice — so the preference is recorded as a house convention and both spellings pass.
    GitHub **does not publish** its bundled mermaid version (its docs offer a self-check and never
    state the number), which is why the diagram-type rule is an allowlist rather than a version
    comparison. And GitHub documents **no** node/size cap: the 60-node cap in
    `architecture_graph.py` is ours, and the doctrine now says not to repeat it as an upstream
    limit.
  - **Two deliberate deviations from the issue body**, both stated so they can be overruled:
    `explain plan` writes **nothing** — a planned area written into the guide is an aspiration
    presented as fact, which `doc-updater` is already forbidden to do — and `doc-updater`
    *reports* a stale area rather than rewriting its explanation, matching the rule this repo
    already applies to curated skills and the architecture graph. The model-tier question that
    sits behind the second is #127's, not pre-empted here.
  - Resolves a dead declaration: `commands/graph.md` has listed `/explain` as a consumer of
    `graph.json` since the graph shipped, naming a command that did not exist.
  - Also fixed in passing: the README's rails-flow command row omitted `/graph` and
    `/pr-comments` — the #203 defect class, in the line this change already touched.

### 1.12.0 — 2026-07-31

- **The scaffold now knows how to brief an agent in a repo that already briefs agents** (#100,
  Phase D of #96). Compared `/rails-flow:setup-flow`'s generated scaffold against 37signals' own
  agent instructions — [fizzy](https://github.com/basecamp/fizzy)'s `AGENTS.md` / `STYLE.md` /
  `.claude/CLAUDE.md` and [writebook](https://github.com/basecamp/writebook)'s `AGENTS.md`, read
  from `main` on 2026-07-31 — and recorded every adopt / adapt / reject decision with its citation
  in the new `plugins/rails-flow/reference/agent-instruction-conventions.md`. Four scaffold changes:
  - **An existing `AGENTS.md` is imported, not duplicated** (new §1b). Claude Code reads
    `CLAUDE.md`, *not* `AGENTS.md`, and its
    [memory docs](https://code.claude.com/docs/en/memory) prescribe exactly what both 37signals
    apps do — a `CLAUDE.md` whose first line is `@AGENTS.md`, with tool-specific content below.
    The scaffold previously assumed greenfield and would create a **second** orientation file
    beside an existing one: two entry points that can contradict each other, where "Claude may
    pick one arbitrarily". We still never *generate* an `AGENTS.md` (Claude-native, #159) — the
    import is a coexistence tool, not the default layout.
  - **A constrained `## Architecture Overview`** — fizzy's most useful section (URL-based
    tenancy via middleware, the entropy system, UUIDv7 base36 PKs, account-scoped jobs) and the
    one conceptual layer neither `Patterns` (code shapes) nor `docs/architecture/graph.json`
    (structure) could carry. Capped at **non-derivable** mechanisms and domain vocabulary, because
    Claude Code's own `/doctor` trims overviews it can derive from the codebase and keeps
    "conventions that differ from tool defaults" — so an unconstrained overview is worse than none.
  - **A per-project `STYLE.md` is rejected, and the pointer replaces it.** fizzy's `AGENTS.md`
    ends with "read STYLE.md"; we already extracted that file into `skills/rails-8/references/style.md`
    in Phase A (#97). Copying it per project would duplicate shipped doctrine and drift, so the
    generated `CLAUDE.md` now points at the skill instead. Where a genuine per-project style file
    is warranted, the Claude-native home is a **path-scoped `.claude/rules/style.md`**
    (`paths: ["**/*.rb"]`), which loads only when Ruby is being read — not a root `STYLE.md` that
    costs its full weight every session.
  - **`.claude/rules/` is documented as the home for area/mode-specific instructions** (new §2b),
    which is the sanctioned mechanism for what fizzy solves with a conditional `saas/AGENTS.md`.
    Not scaffolded by default — empty machinery is worse than none — but named, so a project that
    needs it doesn't invent a bespoke conditional import.
  - **A claim in the issue was false, and that is the finding worth keeping.** Both #100 and #96
    assert fizzy's `AGENTS.md` wires "Chrome MCP for local dev", offered as the comparand to
    qa-flow's Playwright MCP. It appears in **none** of the five source files as of 2026-07-31 —
    the #142 pattern again: attributed to a specific file, absent from that file today. No MCP
    tooling was scaffolded on that basis, and qa-flow's choice is untouched.

### 1.11.0 — 2026-07-29

- **Acceptance criteria are defined BEFORE implementation, and the Stop gate enforces it** (#125).
  The gate already required "no behavioural change without a proving spec" — but it fires *after*
  code exists, so it cannot tell whether the spec asserts what was **required** or merely what the
  code happens to do. A goal written after the result is unfalsifiable: the same defect class as a
  gate that cannot fail, moved from the gate to the goal. This is the other half of qa-flow #106 —
  that made *evidence* trustworthy, this makes the *expectation* trustworthy.
  - `/rails-flow:feature` Phase 1 and `/rails-flow:fix` now write `docs/acceptance/<slug>.md`
    before any code: one `##` section per unit, each criterion in the fixed shape **Given** state,
    **when** action, **then** observable, carrying a stable id (`AC-1`, `AC-2`, …).
  - **The id is what makes "the spec proves the criteria" checkable.** The proving spec cites it
    (`it "AC-2 rejects an invoice with no line items"`), and the shipped
    `plugins/rails-flow/scripts/check_criteria.py` verifies **every criterion is cited by some
    spec** — a real 1:1 mapping rather than a claim. It also enforces the shape, rejects
    rubber-stamp observables (`works`, `handles errors`, `gracefully`, `as expected`), and
    requires **at least one error-path criterion per unit**, because every security finding this
    flow has produced downstream was an error or edge path.
  - **The Stop gate blocks** on `feature/*` and `fix/*` branches when app code changed with no
    criteria file, or when the criteria do not hold. Scoped to the flow's own branches on purpose:
    blocking every branch would break ad-hoc work that never entered the flow. Fails **open** on a
    missing `python3` (a guard decides whether to RUN a check, never softens the verdict) and
    **closed** on a real finding.
  - Bounded honestly in both the script and the doctrine: it proves each criterion is *traceable*
    to a spec, not that the spec truly asserts the observable, and it cannot know the criteria
    predate the code — that is the gate's ordering, not the parser's.
  - **qa-flow consumes them** (closing the loop): `case-author` now reads `docs/acceptance/*.md`
    as its **first** source — the only one written before the code, so the only one stating what
    was required rather than what shipped. Each `AC-n` becomes a case with `Source:
    acceptance:<slug>` and the id in `Notes`, so the trail runs criterion → case → evidence.
    `[error]` criteria become the negative cases.
  - **Fixes a pre-existing hole in the Stop gate, found by behaviour-testing this one:** plain
    `git status --porcelain` **collapses a new untracked directory** to `?? app/`, so
    `app/models/invoice.rb` in a brand-new folder was invisible and behavioural code could finish
    with no spec at all. Now `-uall`, with path parsing that survives spaces and renames.
  - Two defects in the new gate caught by self-review before commit: a bare
    `${CLAUDE_PLUGIN_ROOT}` would abort the whole gate under `set -u` when run outside the hook
    runtime, and a nested branch (`feature/team/foo`) produced `docs/acceptance/team/foo.md` — a
    nested path nobody would create. Slugs now flatten `/` to `-`.
  - 26 selftest assertions; 10 deliberate mutations each caught, including dropping the
    word-boundary anchor on the rubber-stamp list (which would flag "property" and "workspace" —
    the false-positive route to the check being switched off).

### 1.10.0 — 2026-07-29
- **The grep matched what it was meant to allow.** `grep -rn "form_with\|form_for" app/views`
  also matches **`simple_form_for`**, because that string ends with `form_for` — so the mandate
  check fired on every *correct* form. A check that flags everything is as useless as one that
  cannot fire: it gets ignored, then disabled. Fixed with a word boundary
  (`grep -rnE "\b(form_with|form_for)\b"`), verified against a fixture containing one correct
  `simple_form_for` and one offending `form_with` — only the offender is reported.
- **Added the check that actually catches violations.** The mandate covers form *elements*, not just
  the form tag, and hand-rolled anatomy was unchecked: `f.label` with a manual error `<p>`, or a
  ViewComponent emitting its own `<label>`, is a form element built without simple_form. Now flagged
  in `app/views` **and** `app/components`.
- **A stock `config/initializers/simple_form.rb` is BLOCKING.** If the wrapper carries no role-token
  classes, fields are unstyled by the design system and every view is tempted to patch classes per
  input — which is precisely the drift the mandate exists to prevent.

### 1.9.0 — 2026-07-29
- **A doctrine contradiction was live in users' hands, in three files.** `pr-reviewer.md` told the
  merge gate to check jobs for "id args", `rails-developer.md` said "pass IDs, never AR objects",
  and `setup-flow.md` wrote "job shape (ids only)" into the generated project CLAUDE.md. But
  `skills/rails-8/references/jobs-and-realtime.md:28` says the opposite — `def perform(order)
  # pass records, not ids: GlobalID (de)serializes them` — and :39 lists records (GlobalID) as
  serializable. **So the shipped merge gate would block a PR for correctly following our own
  doctrine**, the developer agent would write the wrong thing, and setup-flow would propagate the
  wrong rule into the user's own doctrine file for pr-reviewer to then enforce against them.
  Self-reinforcing, and worse than a plain bug because it blames the user.
  **No framework claim is introduced or changed here, deliberately.** `skills/rails-8` is
  untouched, and review flagged that the first draft *restated* the mechanism (GlobalID,
  `discard_on`) in three shipped plugin files — which would have been authoring an externally
  verifiable claim, and `CLAUDE.md` requires a CONFIRMED `doctrine-verifier` verdict for that even
  when the rest of a PR is an architecture decision. So the plugin text now **defers** to the
  rails-8 jobs doctrine instead of paraphrasing it: the corrected rule is "do not demand ids-only;
  follow the project's own job doctrine", and the mechanism stays in the one place that already
  carries it. Same single-source principle this branch applies to the review classes.
  Found by applying the rubric's `doctrine-contradiction` class systematically with one grep rather
  than fixing the single instance review happened to surface.
- **`code-reviewer` and `pr-reviewer` now ask claims-vs-enforcement explicitly** — the class an
  author is systematically blind to, because they read the claim and the code as one intention
  rather than two artefacts that can disagree. Both **delegate to the new `code-review` skill**
  rather than restating its classes, so there is one source of the doctrine and no drift between
  agent and skill. Both keep two habits in the verdict itself: when a claim and the code disagree
  the reviewer decides *which* is wrong (the fix is not automatically the code), and on finding one
  contradiction, grep for the pattern — that class travels in groups.

- **The mechanical half now ships too (#164).** #162 gave users the *doctrine* and kept the
  deterministic check maintainer-side — backwards, since this repo's whole thesis is that a rule
  left in prose gets violated again. New `scripts/self_consistency.py` (stdlib; a Rails repo must
  not need a pip install to review itself) plus a `PostToolUse` hook on `Edit|Write|MultiEdit`
  beside `lint-ruby.sh`.
- **Four rules, each mechanising a named `code-review` class:** `swallowed-exception`
  (`rescue nil`, empty rescue), `swallowed-verdict` (`|| true` on a verification command — the
  `--check || echo` shape that made a release gate unable to block), `assertion-free-spec` (an
  example that runs code but asserts nothing, so it passes whatever the code does), and
  `dead-env-var` (a key in `.env.example` nothing reads).
- **Two candidate rules were cut, not softened.** `unenforced-documented-step` and
  `carve-out-without-negative-test` need judgement — matching a `skip_before_action` is easy,
  proving no spec covers the near-miss is not. A rule that guesses produces false positives, gets
  disabled, and then catches nothing; both stay with the reviewer and the skill, which is the right
  layer. The standard applied was: zero false positives on a conforming repo, or cut it.
- **The hook exits 2 on findings, deliberately.** A check that can only advise is itself a
  `gate-that-cannot-fail` — one of the classes it enforces — so shipping an advisory-only version
  would have violated the doctrine it exists to uphold. It fails *open* on a missing `python3`,
  because a guard decides whether to RUN a check and must never soften the verdict.
- **Calibrated, and non-vacuously.** 22 selftest assertions prove every rule fires on a violation
  **and stays silent on conforming code** — including the cases that would otherwise be false
  positives: `#` inside a Ruby string, a commented-out `rescue nil`, `|| true` on a *cleanup*
  command, a one-liner `is_expected`, an example delegating to shared examples, a `pending`
  placeholder, and an env key referenced from a non-Ruby file (Kamal `deploy.yml`). Run against
  this repo it examines 25 files and 4 env keys and reports nothing — coverage prints on every run,
  because "no findings" over input never read reads as a pass.
- `pr-reviewer` now runs the repo-wide pass first and treats its output as BLOCKING evidence, then
  reasons about the classes no machine catches.

### 1.8.0 — 2026-07-29
- **`architecture_graph.py --if-present`** — with `--check`, a missing `graph.json` exits 0 instead
  of reporting DRIFT, because the graph is opt-in per project. Added so a caller never has to
  branch on the file's existence in shell: that guard belonged in the script, and putting it in a
  command doc's prose is how #151 shipped a release gate that could not block. Without the flag a
  missing graph is still DRIFT, which is correct for a project that opted in.

### 1.7.0 — 2026-07-27
- **Living architecture graph** (#141): `/rails-flow:graph` extracts `{nodes, edges, flows}` from
  `config/routes.rb`, `app/**` and `db/schema.rb` into three artefacts — `docs/architecture/graph.json`
  (machine-readable), `index.html` (human, interactive) and `graph.md` (mermaid, for GitHub file
  views). One extraction, three consumers: humans get a picture, agents get structural context
  without reading the whole codebase, qa-flow gets reverse dependencies for a **computed** blast
  radius (#134 becomes a consumer instead of needing its own extractor).
  - `plugins/rails-flow/scripts/architecture_graph.py` — **stdlib Python 3 only**: no gems, no graph
    tool, no network, no app boot, so it runs in any clone. Node kinds: controller · model · job ·
    mailer · service · component · Stimulus controller · route · table · channel (+ `concern`, which
    the specified `includes` edge needs somewhere to point). Edge kinds: `references` · `persists` ·
    `enqueues` · `renders` · `broadcasts` · `includes` · `belongs_to`/`has_many`/`has_one`, one
    uniform direction (subject → object).
  - **`flows`** are the part a generic code-graph tool does not give you: named, ordered request
    paths ("Create an invoice": `POST /invoices` → controller → model → job → turbo_stream), built
    from the action body plus the private helpers and `before_action` callbacks that actually apply
    to that action (`only:`/`except:` honoured — ignoring them made every action claim work it does
    not do).
  - **Drift check** (`--check`) mirrors the proven `dist/` guard by rebuilding and comparing a
    `content_digest` over `{nodes, edges, flows}`. Digesting the *extracted structure* rather than
    fingerprinting input files means a prose-only view edit cannot raise a false finding, while a
    real structural change cannot hide; `generated_at`/`commit` are excluded, so re-running on an
    unchanged tree is a no-op. Exit 1 = the code moved and the graph did not.
  - **`--delta <ref>`** prints the release-notes delta — new/removed nodes and **flows that changed
    shape** ("flow *Create an invoice* gained a step"), which is what a 40-file diff cannot tell a
    reviewer.
  - **Self-contained HTML by decision** (maintainer ruling on the issue's open question): inline CSS
    and vanilla JS, JSON embedded *and* written as a separate file, **zero external requests** — no
    CDN, no webfont, no remote image, no `fetch`. It opens from a clone, offline, years later.
    Verified mechanically (12 external-request patterns, all zero) and by executing the inlined JS
    against a DOM stub: node/flow selection, cross-link navigation, layer filtering, search, and
    keyboard nav all run clean. Fidara dark-palette values are copied literally with a comment
    saying so (a standalone file cannot read `@theme` tokens); layer is always stated as text, never
    colour alone; visible focus rings, `prefers-reduced-motion`, and a `@media print` block.
  - **Enrichment is quarantined**: `--enrich` folds in `graphify`/`code-review-graph` edges but into
    a separate `enrichment` block **excluded from the digest** — otherwise CI would report drift for
    a teammate's missing local tool. The foreign schema is probed, and a mismatch is noted, never
    guessed at.
  - **Limits are announced, never silent**: unmodelled route DSL (`mount`/`match`/dynamic), flow and
    mermaid caps, and id collisions all land in `notes`, surfaced in the console and persistently in
    the HTML sidebar.
  - Lifecycle: `doc-updater` regenerates at session end (step 5); `setup-flow` offers generation
    (§6b), adds a graph-freshness item to the `loop.md` maintenance pass, proposes the CI drift job
    as an approved diff (§8), and points agents at `graph.json` before grepping.
  - Verified against a synthetic Rails app covering nested/member/collection/namespaced/singular
    routes, `%i[]` callback options, concerns, ViewComponent, Stimulus, Turbo, and `Current.`-scoped
    queries. Fixed while building: `concerns/` mis-namespaced as `Concerns::X` (broke every
    `includes` edge), nested resources missing the parent `:invoice_id` segment, and non-ASCII
    console output mangled on Windows code pages.
  - **Post-review fixes** (Qodo findings on PR #143, folded in here because 1.7.0 had not yet been
    promoted to `main`):
    - **Flow identity is no longer the display name.** `compute_delta()` keyed flows by `name`, and
      `flow_name()` dropped namespaces — so `Admin::InvoicesController#index` and
      `InvoicesController#index` both produced "List invoices" and one **silently vanished from
      every delta** (measured: 7 of 8 flows survived the dict). Flows now carry a unique `id`, the
      delta keys on a version-stable `trigger + entry` pair, and the display name keeps its
      namespace ("List invoices (admin)"). The reviewer's suggested fix — keying on `id` — was
      implemented, tested against a simulated older `graph.json`, and **rejected**: it reported all
      8 flows as simultaneously added and removed, because a delta compares two schema versions and
      so the key must be derivable from fields both sides have and neither redefines.
    - **`/pipeline:release` no longer breaks graph-less projects**: the prose said "skip silently"
      while the commands ran `--check` unconditionally, which exits 1 on a missing `graph.json`. Now
      guarded by a file test, with the skip path stated.
    - **Accessibility**, against this repo's own design doctrine: base type is `1rem` not `15px` (a
      px base overrides the reader's browser font-size preference), and `min-h-touch` (44px) is
      applied under `@media (pointer: coarse)` — full finger-sized targets where a finger aims,
      preserving the density a 40-row graph browser needs on a mouse, which still clears the 24px AA
      floor (~27px buttons, ~31px rows).
    - **Enrichment dedupe** no longer rebuilds the base-edge set once per candidate edge
      (O(base×enriched) → O(base+enriched)), and collapses duplicates within the enriched input.

### 1.6.0 — 2026-07-25
- **File-then-fix discipline for mid-session defects** (#73). The flow intended issue-driven fix
  work but nothing steered it there when defects surfaced *interactively* (user reviewing the running
  app: "this is broken", "also this") — the result was ad-hoc hot-fixing, several unrelated fixes
  stacked on one branch, no issues filed. Now:
  - `fix.md` **Setup**: if the defect surfaced live and isn't filed, **file it before touching code**;
    if several surfaced, file them all (batched), then work them **one at a time**, own branch → PR →
    spec. Never hot-fix onto the checked-out branch.
  - `issues.md` gains **Phase 0 — Capture unfiled defects**, the route from "surfaced in conversation"
    into the tracker queue (the command only ever saw `gh issue list` before).
  - `setup-flow`'s CLAUDE.md scaffold always includes the file-first ALWAYS-rule.
  - **SessionStart advisory** (fail-open, never blocks): ≥2 fix-shaped commits on a branch with no
    issue reference → prints a nudge back to `/rails-flow:fix` · `/rails-flow:issues`. Verified: fires
    on unreferenced fix stacks, silent on `fix/issue-NN-*` branches.

### 1.5.0 — 2026-07-25
- **setup-flow scaffolds economical GitHub CI** (#76): a new step checks `.github/workflows/ci.yml`
  and, when it runs the full matrix on every PR/push (the Rails default), proposes scoping the
  triggers to the `dev → main` gate **as an approved diff — never a silent rewrite** (idempotent;
  leaves it alone if already economical or the user declines). Local gates + qa-flow stay primary
  for `feature → dev`; hosted CI is the independent check at `dev → main`; `workflow_dispatch` stays
  on-demand.

### 1.4.1 — 2026-07-25
- **Review/audit agents report ALL findings — no self-triage** (#77). `security-auditor`,
  `code-reviewer`, `design-auditor`, `pr-reviewer`, and the `/rails-flow:review` synthesis had
  output contracts that let a pass *silently drop* a real finding — downstream, `security-auditor`
  self-dismissed a token-in-URL and a login-CSRF finding as "accepted residual"/"awareness-only"
  and never surfaced them. Every contract now mandates: **report every finding** (any severity)
  with `file:line` + repro + fix option(s), **issue-ready**; **do not decide disposition** (no
  "accept / won't fix / no action / residual—ignore" — a residual is still reported as low-severity);
  the fix-flow + human decide whether/how to fix. Verdict (CLEAN/BLOCKED) stays, but the full list
  ships regardless. Synthesis now only *orders* findings, never drops them. Security findings are
  never reviewer-dismissed.

### 1.4.0 — 2026-07-24
- **Local brain-review cadence nudge** (#65) — the maintenance sweep now actually fires on time.
  `/rails-flow:brain-review` stamps an epoch into `docs/brain/.last-review`; the SessionStart
  hook reads it and nudges *"brain-review due"* when the last sweep is older than the cadence
  (default **7 days**, override `RAILS_FLOW_BRAIN_REVIEW_DAYS`), or *"no sweep on record"* if it's
  never run. Reminder-only — never auto-runs; dismiss by re-stamping. Fully **local/offline**, no
  cloud, hook fails open. (Filed under pipeline as the nudge-pattern owner; implemented in
  rails-flow, where `brain-review`, `docs/brain`, and the brain-surfacing SessionStart hook live.)
  `setup-flow` documents the cadence.

### 1.3.1 — 2026-07-23
- **Dropped NotebookLM from the brain flow.** `/rails-flow:brain-sync` no longer documents
  NotebookLM as an optional synthesis lens; the `<org>/brain` git repo is the **single source of
  truth** for cross-project state, with no external embeddings/RAG layer. Rationale: keep the
  audit trail — git gives provenance, deterministic reads, and diffs; a separate synthesis service
  drifts from git and can't be trusted for coordination. Federation (publish/consume via `gh`,
  no cloning) is unchanged.

### 1.3.0 — 2026-07-23
- **Brain, leveled up — fuller structure + maintenance + cross-repo federation.** The brain
  was `/brain` memos + MEMORY.md; it's now a full repo-side memory system, and two new commands:
  - `setup-flow` §4 now scaffolds the **fuller brain**: `STATUS.md` (where we are now, edited in
    place), append-only `PROGRESS-LOG.md`, ADR-lite `DECISIONS.md` (with reversal conditions),
    `HYPOTHESES.md` (**lifecycle** candidate→proposed→confirmed|refuted with dated evidence),
    `MEMORY.md`, and a `README.md` doctrine — plus **provenance tags** (`[observed]`/`[decided]`/
    `[assumed]`/`[reported]`) on non-obvious claims, with a "preserve contradictions" rule.
  - NEW **`/rails-flow:brain-review`** — weekly maintenance sweep: flag stale STATUS/evidence,
    surface decisions-vs-PRD drift and contradictions, check hypotheses against evidence, compress
    recurring patterns (preserving minority signals). Report + proposed diffs; applies only what's
    approved. The keystone ritual that keeps the brain from becoming a landfill.
  - NEW **`/rails-flow:brain-sync`** — a **cross-project shared brain repo** (`<org>/brain`) as the
    coordination bus: each project publishes its STATUS to `projects/<self>/` and appends to a
    shared `EVENTS.md`/`CONTRACTS.md`, and reads siblings via `gh` single-file fetches — so agentic
    flows in separate repos coordinate **without cloning each other**. Git is the store (versioned,
    provenance, deterministic). **NotebookLM** is documented as an optional read/synthesis lens on
    top (briefings, Q&A) — never the store, since its write primitive is append-sources not mutable
    state (official Enterprise API + community MCP options + auth caveats noted).
  - `session-start` hook now surfaces the top of `STATUS.md` ("where are we now") alongside MEMORY.md.

### 1.2.1 — 2026-07-23
- Reporter now covers the **design system**: `/rails-flow:report` + `claude-skills-reporter`
  scope includes the `fidara-design` skill and `design-flow` plugin. A generated
  component/UI that won't compile or render in a real Rails app is explicitly in-scope
  (`comp:fidara-design` / `comp:design-flow`) — so the least runtime-verified layer has a
  path back into the issue inflow.

### 1.2.0 — 2026-07-23
- Fix #2: NEW `claude-skills-reporter` agent + `/rails-flow:report <observation>` — closes
  the toolchain feedback loop. Turns friction hit while USING the toolchain into a
  structured, deduped, version-pinned, evidence-backed issue on the upstream marketplace
  repo. Scope-guarded (toolchain only — refuses to file the user's app bugs); pins
  marketplace + plugin version (and running-vs-latest delta); dedups against open/closed
  issues before filing; **drafts by default**, files only on explicit `MODE: FILE` via
  `gh issue create --body-file`. `setup-flow` now surfaces the report path; README gains a
  "feedback loop" section. Pairs with skill-maintainer (the receiving end).
- setup-flow: idempotent-safe re-runs + audit/repair, both by construction.
  IDEMPOTENCY — rails-flow content lives in `<!-- rails-flow:begin/end X -->` markers;
  re-runs refresh only marked blocks and never touch out-of-marker prose; a marker-less
  hand-authored CLAUDE.md is never restructured (additive blocks only, with a diff).
  REPAIR — setup-flow can now diagnose and fix a DEFECTIVE CLAUDE.md, always as
  diagnose→propose-diff→await-approval (never an autonomous rewrite). Repair scope is
  deliberately conservative: only (a) contradictions of fact (stack table vs Gemfile,
  pointers to missing paths, AGENTS.md naming absent agents) and (b) broken safety
  rules (Delegation Rules missing the anti-recursion check, gate bypasses, GUARDRAILS
  contradictions). Divergent-but-valid content (documented Project Overrides, custom
  layouts, domain prose) is left untouched — deliberate choices are never "repaired"
  into vanilla; missing sections are additions, not defects.

### 1.1.2 — 2026-07-22
- stop-gate macOS portability fix (field-reported): the hook shelled out to `timeout`,
  absent on stock macOS, so the wrapped rspec run exited 127 and the gate misread it as
  a RED suite — a false block on green specs. Added a portable `_rf_timeout` helper
  (prefers `timeout`, falls back to `gtimeout`, else runs bare — a missing timeout must
  never be misread as failing) using `type -P` so shell-function/alias shadows can't
  fool it. Same gap noted for the CRG post-checkout hook in setup-flow guidance
  (install coreutils for `gtimeout`, or it runs without the time cap). Both branches
  behaviorally verified: green passes, real failures still block. Same class of bug
  previously patched out of the CRG hook — now consistent across all hooks.

### 1.1.1 — 2026-07-22
- PR Documentation Contract: /feature and /fix now generate the full contract body
  (Summary, What was built, How to test + expected results, Out of scope, Risk notes,
  Proof); pr-reviewer BLOCKS PRs missing it when qa-flow is installed; it is QA's
  primary planning input. QA handoff documented in /feature (verify gates feature->dev).

### 1.1.0 — 2026-07-21
- NEW `skill-curator` agent + `/rails-flow:curate`: distills `docs/` (PRDs,
  branding, architecture, domain rules) into project-local skills with a
  hash-manifest sync protocol; SessionStart reports source drift; curator may
  propose project-local agents (human-approved). Docs → capabilities,
  continuously.
- Scaffolded CLAUDE.md gains Delegation Rules: coordinator/executor split with
  an anti-recursion role check (`ROLE: EXECUTOR` never spawns subagents).
- Agent-teams doctrine: /review documents optional teams mode (persistent
  teammates from these agent types, peer messaging, TaskCompleted enforcement);
  default remains one-shot subagents. Verified against official agent-teams docs.

### 1.0.8 — 2026-07-21
- Version-only bump alongside the marketplace 1.1.8 release; no plugin content
  change since 1.0.7 (keeps the plugin cache-key aligned with the release tag).

### 1.0.7 — 2026-07-20
- Version-only bump: invalidates installed 1.0.6 caches that captured the
  pre-amendment `setup-flow` (same-version content amendments don't propagate —
  lesson encoded: content changes always ride a version bump).

### 1.0.6 — 2026-07-20
- graphify integration as the complementary exploration/cross-repo graph:
  `setup-flow` detects it, scaffolds `.graphifyignore`, git-hook-only freshness,
  and the `CRG → graphify → grep` fallback chain.
- Setup/verification parity with the source field guide: ignore file before first
  build, graphify end-to-end verification, CRG post-checkout hook (branch-switch
  staleness), SessionStart graph cheatsheet, third freshness probe.

### 1.0.5 — 2026-07-20
- Repo-wide LF normalization after a CRLF incident broke all four hook scripts
  on macOS/WSL (`git add -A` from a Windows clone swept phantom-modified files).
  `.gitattributes` added (`* text=auto eol=lf`); recurrence structurally impossible.
- Content otherwise identical to 1.0.4.

### 1.0.4 — 2026-07-20
- New `/rails-flow:issues`: triages open issues (bug/feature/chore/needs-info),
  works them strictly one at a time through the matching pipeline, `Closes #n`
  PRs with auto-close verification, `/goal`-driven unattended mode.
- New `/rails-flow:pr-comments`: sweeps conversation + inline comments + CI;
  in-scope items fixed on-branch (spec-first), out-of-scope folded into
  `from-pr-review` issues; re-gates after changes.
- Close-out rule threaded through `/feature` and `/fix`: no next task while the
  current PR has unresolved feedback.
- pr-reviewer deferral rule: BLOCKING findings are never deferred to issues to
  earn a CLEAN; deferred suggestions must be folded and linked.

### 1.0.3 — 2026-07-20
- Autonomous operation: `/goal` vs `/loop` doctrine (condition-driven vs
  interval-driven), `setup-flow` scaffolds a project `loop.md` maintenance pass,
  `/feature` offers a PR-babysitter loop on default-branch stops, `/fix`
  documents unattended backlog runs.
- README: autonomy section; Windows note (hook scripts are bash — WSL/Git Bash).

### 1.0.2 — 2026-07-20
- code-review-graph v2.x era (upstream moved plugin → pip CLI): merge gate in
  `/feature`, `/fix`, and pr-reviewer detects the CLI + built graph and invokes
  the `review-pr` skill (plugin namespace removed upstream).
- `setup-flow` gains CRG coexistence: authored-file protection, three-file
  settings pattern with PID-guarded Stop hook, `CRG_TOOLS` 8-tool allow-list,
  post-commit updater, gitignore hygiene.

### 1.0.1 — 2026-07-20
- Hook loader schema fix: `hooks.json` wrapped in a top-level `"hooks"` key;
  empty `matcher` dropped from non-tool events (Stop, SessionStart).

### 1.0.0 — 2026-07-20
- Initial release. Five commands (`/feature`, `/fix`, `/review`, `/setup-flow`,
  `/brain`), eight subagents (rails-developer, migration-writer, code-reviewer,
  test-runner, security-auditor, design-auditor, doc-updater, pr-reviewer), four
  guardrail hooks (bash guard, rubocop-on-edit, spec-proof stop gate, session
  context). Synthesized from the fmworkflows/auctioneer agent systems, elevated
  to hooks-enforced, plugin-distributed, progressive-disclosure form.

## pipeline (lifecycle orchestrator)

### 1.3.0 — 2026-08-01

- **Unattended pipeline runs are bounded by a circuit breaker instead of by hope** (#128, the
  `comp:pipeline` half; the rails-flow half shipped in rails-flow 1.14.0). The gates said when a
  stage may *advance*; nothing said when to stop **retrying** one — and this plugin's most
  autonomous agent, `kamal-configurator`, was told to *"troubleshoot autonomously"* and *"re-run
  idempotently"* against a **production host** with no bound of any kind. An agent that cannot make
  progress does not idle here, it re-pushes an image and redeploys, and every attempt looks like
  activity in a log.
  - **Change type: architecture / design decision**, per CLAUDE.md's carve-out — the ledger shape,
    the numbers, and which of #128's escapes become mechanical have no upstream to cite. The one
    external claim reused (`maxTurns` bounds *turns, not attempts*,
    [docs](https://code.claude.com/docs/en/sub-agents)) was verified for the rails-flow half and is
    repeated with its citation, not re-derived. Decision recorded on
    [#128](https://github.com/fmanimashaun/claude-skills/issues/128#issuecomment-5146943177).
  - **New `scripts/breaker.py`** over `pipeline/run-ledger.jsonl` — append-only JSONL, committed, so
    a run is a `git diff` rather than a memory. `start` declares the stages and the limits **once**;
    `check` reads them back and takes **no threshold flags**, so a run cannot widen its own cap
    halfway through, and a second `start` over a run that did not end `complete` is refused rather
    than silently resetting every counter.
  - **Five refusals, all decidable from the ledger:** `already-passed`, `out-of-order` (gate-skipping
    made mechanical — `release` cannot be attempted until `certify` passed), `attempt-cap` (3),
    `no-progress` (2 identical failure signatures), `budget` (120 minutes). Overridable within
    `1..10` / `2..10` / `1..480`, because **an override that can be set to infinity is not a
    breaker**. Digits survive signature normalisation on purpose: "3 failures" becoming "1" is
    progress, and erasing it would stop a converging run.
  - **A failure cannot be recorded without a signature and a stop cannot be recorded without a
    diagnosis** — both exit 2. A no-progress detector fed unsigned failures can never fire, which is
    an unfalsifiable breaker wearing a breaker's clothes.
  - **`report` derives complete / partial / stopped from the ledger and exits `0` only for
    `complete`**, so "partial presented as success" is not available to anything that reads the exit
    code. Exceeding a cap makes a run `stopped` **even if every stage later passed**: crediting the
    outcome would make the cap advisory.
  - **Two of #128's four escapes are enforced, two are doctrine, and the file says which.** Test
    weakening and guardrail disabling involve file edits the ledger cannot see, so they live in the
    new `reference/stop-conditions.md` — and the selftest asserts that file still carries all four
    escape strings, all three defaults, and all three allowed ranges the script declares, so doctrine
    and code cannot drift apart.
  - **Escalate-and-continue was deliberately NOT copied from the rails-flow half.** Criteria are
    independent; a gated chain is not. Nothing downstream of a stopped stage is independent of it, so
    "continuing" is the out-of-order escape under a friendlier name. A stop ends a pipeline run.
  - **Wired into all four unattended surfaces** — `/pipeline`, `/pipeline:deploy-cloud`,
    `pipeline-coordinator`, `kamal-configurator` — and the selftest **fails** if a pipeline command or
    agent describes an unattended re-run without naming the breaker. That rule found its own four
    subjects on its first run, and a line-based version silently missed `pipeline.md`, where "run the
    whole pipeline" wraps across two lines; it matches whitespace-normalised text now.
  - Registered as the gate **`pipeline stop conditions`**. **59 selftest checks** (fires-and-silent
    per breaker, including the near misses that decide whether it survives: the last attempt before
    the cap, one minute short of the budget, a shrinking failure count) and **14 declared mutations**,
    all caught. One fail-open was found by writing them: a ledger with no `started` made the budget
    rule return silently instead of refusing, on exactly the hand-edited input where it matters most.
    It is `UNUSABLE` now, with its own fixture and mutation.
- **FIX — `reference/model-tiers.md` justified both tiers with a premise this release makes false.**
  It rested on *"this plugin ships no deterministic scripts at all"*; it now ships one. The
  conclusion is unchanged and the reason is now the honest one — `breaker.py` grades a **run**
  (attempts, signatures, ordering, budget), never a **judgement**, so it cannot tell that the
  coordinator picked the wrong stage or that a deploy succeeded against the wrong host. A tier table
  justified by a false premise is the `doctrine-contradiction` class whatever its conclusion.

### 1.2.0 — 2026-08-01

- **Agent model pins reconciled with the tier doctrine** (#299). Every agent moved from a
  `sonnet` pin — which is a **cap**, since frontmatter resolves above the session model — to
  `inherit`. The full argument, the per-agent table and the reasoning for this plugin's tier
  split are in its new `reference/model-tiers.md`, reconciled against the shipped agents by a
  gate in `--gates` so the table cannot drift back into folklore.

### 1.1.4 — 2026-07-29
- **Moved the decision out of the markdown entirely.** The fix above still shipped a 12-line,
  three-branch shell guard in a doc — and a doc is the one layer nothing tests. The branching only
  existed because `--check` conflated *absent* (a legitimate opt-out) with *stale* (a defect), so
  the prose compensated for a missing flag. `architecture_graph.py` now takes **`--if-present`**,
  which owns that judgement in tested Python, and the doc carries two plain invocations with no
  branching at all. If the script is not vendored the command fails on its own — which is the
  correct outcome and deletes the misleading-skip branch rather than fixing it.
  Verified: absent + `--if-present` → 0 · absent without it → 1 · stale → 1 · fresh → 0 · script
  missing → non-zero. Old snippet vs new on the same drifted repo: **0 vs 1**.
  The general rule, now stated in the doc: **bash is for commands, Python is for decisions.** Every
  finding this week came from a snippet that encoded a decision; none came from a plain
  `docker build` / `git push`.
- **The architecture-graph drift check could not block a release** (#151, shipped in v1.21.0). The
  snippet in `/pipeline:release` ran `python3 "$GRAPH" --check || echo "…"`, and `|| echo` consumes
  the non-zero exit — including under `set -e`. A stale graph printed a warning and the release
  proceeded. That is worse than having no check, because the message makes it look like the gate
  ran. Proven before/after against the same drifted repo: old snippet exit **0**, fixed snippet
  exit **1**.
- **The skip branch conflated two different causes.** `[ -f "$GRAPH" ]` was ANDed into the
  absence test, so a project that *had* `docs/architecture/graph.json` but had not vendored the
  script reported *"no architecture graph in this project — skipping"* and silently skipped
  verification. Since the graph is opt-in per project while the script is vendored manually, that
  combination is likely rather than exotic. Now three branches: no graph → skip (exit 0); graph
  but no script → **error, exit 1** (a project that opted in and cannot verify must stop, not
  skip); otherwise run `--check` and let it fail.
- Root cause worth recording: this was introduced *while fixing* an earlier review finding. The
  unguarded `--check` broke graph-less projects, so a guard was added — and making the failure
  non-fatal made it non-functional. **A guard decides whether to run a check; it must never soften
  the verdict.**
- `/pipeline:release`'s Report section now requires the graph verdict as one of three explicit
  words — `verified` / `skipped` / `FAILED` — so a skip can never be read as a pass.
- Verified `scripts/release_local.sh` and `.github/workflows/release.yml` for the same softening:
  both already hard-fail (`fail`, `exit 1`), so the defect was confined to this one snippet.
- Found by review on PR #144 and **missed** on the first read — the comment list was truncated, so
  four of five findings were addressed and reported as "four findings". Count first, then read.

### 1.1.3 — 2026-07-27
- **Release verifies the architecture graph and reports its delta** (#141): `/pipeline:release` now
  runs the graph drift check before reporting and pastes `--delta origin/main` into the release
  notes, so a release carries its structural story (new/removed nodes, flows that changed shape)
  alongside the image digest. Release is the second cadence at which the graph must be true — the
  first is session end, via rails-flow's `doc-updater`. Skips when the app has no
  `docs/architecture/graph.json` (the graph is opt-in) — the skip is a real file guard, since
  `--check` exits 1 on a missing graph and an unguarded call would report every graph-less project
  as a failed release (Qodo finding on PR #143, fixed before promotion). Guidance-only; no hook or
  script changed.

### 1.1.2 — 2026-07-25
- **setup-pipeline CI-economy alignment** (#76): notes that pipeline's own release/build workflows
  are already `main`-only, and points at `/rails-flow:setup-flow` to scope the Rails-default
  `ci.yml` to the `dev → main` gate too — so the hosted CI runs only where it's the independent
  check, consistent with the pipeline release gate. Guidance-only.

### 1.1.1 — 2026-07-23
- **/pipeline:ack git-dir guard** (#46): the marker path came from an unguarded
  `$(git rev-parse --git-dir)`; outside a repo it collapsed to `/pipeline-pending` and the
  `rm -f` could delete a root-level file. Now bails (exit 0 + message) if git-dir is
  unresolved/empty. Fixed `setup-pipeline.md` doc drift (hardcoded `.git/…` → the resolved
  git-dir, worktree-safe, with the `.git/` common case noted).

### 1.1.0 — 2026-07-23
- Fix #5: the post-merge QA-verify nudge marker now has a dismissal/clear path. New
  `/pipeline:ack` removes `.git/pipeline-pending` (worktree-safe via `git rev-parse
  --git-dir`) — nudge-only, no token spend — so a stale nudge can be cleared without
  another merge or a manual `rm`; verified the SessionStart hook stops re-surfacing it
  after. The pipeline-coordinator now CLEARS the marker when the verify stage resolves
  (a `/qa-flow:verify` PASS or an explicit N/A), making "clears when the stage completes"
  literally true. `pipeline-status.sh` reads the marker via git-dir (matching the writer)
  and its hint points to `/pipeline:ack` (e.g. docs-only merges with nothing to verify).
  Docs updated (`setup-pipeline.md`, README).

### 1.0.5 — 2026-07-22
- setup-pipeline + setup-cloud: idempotent re-run + repair contract (matching
  setup-flow). pipeline.yml keys reconciled not overwritten (missing added, wrong
  values proposed as diffs); .env.example regenerated preserving user annotations,
  never touching the real .env; generated deploy.yml uses kamal-config markers so
  re-runs refresh only the generated block. Every scaffolding command in the
  marketplace now shares one idempotent-and-repairable discipline.

### 1.0.4 — 2026-07-22
- Portability pass: pipeline-status skips cleanly when `python3` is absent; portable
  `mktemp` template in install-git-hooks (BSD+GNU). Platform assumptions now behave
  consistently across macOS/Linux/WSL.

### 1.0.3 — 2026-07-22
- install-git-hooks hardening (peer review): append-or-backup instead of clobbering
  an existing post-merge hook (critical in an ecosystem where CRG and rails-flow also
  write git hooks) — managed-block markers make re-runs idempotent, non-managed hooks
  are backed up then appended to; `dev_branch` fallback no longer defeated by
  pipefail when pipeline.yml is absent. Platform note added to the plugin README.

### 1.0.2 — 2026-07-22
- Cloud deploy reworked to the .env-briefing-sheet + routing model (Rails
  convention). `.env` is the agent's single source of truth (NOT a Rails runtime
  file — Rails 8 has no dotenv); the agent ROUTES each value to its home: `CRED__*`
  keys → Rails encrypted credentials written NON-INTERACTIVELY via
  ActiveSupport::EncryptedConfiguration with a read-back verify (never
  credentials:edit, which needs an editor and silently no-ops); deploy secrets →
  gitignored .kamal/secrets by name; facts → deploy.yml. Annotated `.env.example`
  template ships in the plugin, grouped by destination bucket, with the
  `CRED__top__sub` nesting convention. Verified vs Rails credentials + Kamal 2 docs.

### 1.0.1 — 2026-07-22
- Cloud deployment on demand: `kamal-configurator` agent + `/pipeline:setup-cloud`
  and `/pipeline:deploy-cloud`. setup-cloud writes `.env.example` (the documented
  contract of every variable the deploy expects) and a README "Cloud deployment"
  section; deploy-cloud reads the filled `.env`, generates `config/deploy.yml`
  (secret NAMES only, committed) and `.kamal/secrets` (values, gitignored +
  dockerignored, via the `<% Dotenv.load(".env") %>` bridge Kamal 2 requires since
  it no longer auto-loads .env), safety-checks that no secret value entered a
  committed file, then `kamal setup`/`deploy` with explicit approval + the deploy
  guard. Verified against Kamal 2 secrets docs. Same ghcr image as the local flow —
  cloud is just where it's pulled.

### 1.0.0 — 2026-07-22
- Fourth plugin: sequences rails-flow and qa-flow across the SDLC without replacing
  their gates. pipeline-coordinator detects stage (developing / verify-pending /
  verify-failed / certify-pending / release-ready / released) and drives the next
  flow; /pipeline advances, /pipeline:status reports read-only.
- Release artifact = a versioned Docker image on ghcr.io (source-verified: the same
  image Kamal pulls to a server later — local vs cloud is only where it's pulled).
  /pipeline:release builds, tags with the certified dev sha + latest, pushes, and in
  local mode pulls-and-runs to health-check /up (proves the artifact boots, not just
  builds). Cloud mode = kamal deploy, gated by rails-flow's deploy guard.
- Gated on qa/CERTIFICATION matching the dev sha — uncertified code is never imaged.
- Local git-hook nudges (/pipeline:install-hooks): post-merge on dev leaves a marker
  the SessionStart hook surfaces — detects transitions, NEVER invokes Claude or
  spends tokens (frugal by design; no GitHub Actions minutes used). Dormant Actions
  adapter shipped as an .example for when cloud minutes exist.
- pipeline.yml carries registry/image/mode/branches — local today, cloud by config
  flip, no rebuild.

## rails-stack (rails-8 + hotwire + fidara-design skills)

### 1.43.0 — 2026-08-08

- **Reference research — look before you design.** A designer does not open a blank canvas; they
  gather references for the *kind of problem*, work out **why** each works, and build from the
  mechanisms rather than the surface. Skipping it does not produce nothing — it produces the median
  of everything the model has seen, which is the stock-SaaS look, and a reader recognises that
  instantly without being able to say why.

  **Scoped to any interface, not just marketing**, because the method is identical for a dashboard,
  an onboarding flow or a pricing page. Marketing differs only in *weighting*: a product surface is
  bound by convention (novelty costs a returning user time), a marketing surface by attention
  (looking like everyone else is the failure, not the safe choice).

  Three rules are checkable and are enforced rather than written down: **three sources minimum and
  never all from one category** (direct competitors converged by copying each other, so sampling
  only them inherits the convergence), **a mechanism rather than a brand name** (*"looks like
  Linear"* cannot be applied to a different subject), and **something rejected** (a record where
  everything was adopted is a shopping list).

- **The operational half: where to look, and the failures that are silent.** A source directory split
  by whether a human must sign in first, plus the three capture mechanics whose failures produce a
  *file* rather than an error — lazy loading returns empty placeholders, a **login wall returns a
  sign-in form**, and a rotted CSS-in-JS selector returns nothing at all. Each is filed as research
  and nothing downstream can tell.

  On gated galleries the agent **stops and asks the human to sign in once** into a reusable browser
  profile; it never requests, types or stores credentials, and a decline is a complete answer. On a
  *deliberate* block — persistent challenge, rate limit, robots directive — it stops and says so
  rather than escalating techniques.

  Galleries are an **index, not the material**: follow the listing through to the live site, because
  a thumbnail cannot show 1440→390 behaviour, interaction, or the current state of a page that may
  be a redesign old.

### 1.42.2 — 2026-08-08

- **`dismissable?` was dead code, and the close button was gated on the wrong thing** (Refs #556).
  The predicate exists to keep a close button off a `:loading` toast; the template gated on
  `action.present?` instead and never called it. Those two differ on exactly one case, and it is the
  case the predicate exists for: a **`:loading` toast with an action** — *"Uploading… · Cancel"* —
  which is legitimate and still rendered a close button, so dismissing it hid an operation that was
  still running. The recipe's prose stated the correct rule **twice** while the code beneath it did
  the opposite. Fifth survivor of the v1.72.0 rewrite.

- **Four component templates rendered strings through a lazy `t('.key')` and never said where the
  key lives** (Refs #555). A missing key does not raise — Rails renders `translation missing:
  en.ui.toast.dismiss` **into the attribute**, so for the two `aria-label`s the failure is audible
  only to a screen-reader user and invisible to everyone reviewing the page. #555 reported **one**
  (Toast); the same defect sat in **PasswordStrength**, **Breadcrumbs** and **DescriptionList::Row**.
  All four now use absolute keys, and the locale entries ship as part of the recipe.

  Two other lazy lookups were left alone **deliberately**, and that distinction is why this needed
  measuring rather than a regex: `t(".saved")` sits in a controller and `t(".or")` in a plain view
  recipe, where a lazy lookup resolves exactly as a reader expects. The defect was never the lazy
  form — it was a *component* template depending on a resolution the recipe never stated.
  `breadcrumbs.show_more` takes a `count:`, so it ships plural sub-keys; a bare string there is right
  for `count: 1` and wrong for every other value.

### 1.42.1 — 2026-08-07

- **The toast rewrite left call sites that crash, and an accent that silently vanishes** (Refs #546).
  Two defects, both survivors of the v1.72.0 rewrite, and both bite anyone copying the section verbatim.

  **The examples called a keyword that no longer exists.** The rewrite made `title:` required and
  removed `message:` — but the flash→toast examples still passed `message:`, so the exact wiring the
  section teaches raised `ArgumentError`. #546 reported **two** such call sites; there were **five**,
  three of them in `crud-modal-pattern.md`, a file the report does not mention. One also passed
  `undo_path:`, a **third** dropped keyword, now expressed through the `action:` slot the rewrite added.

  **`border-l-<%= intent %>` was string interpolation posing as a token.** It emits `border-l-error` and
  `border-l-loading`, and a conformant theme has **neither** — it names the error colour `destructive`
  (as `Ui::Alert`'s own `INTENT` map already did) and ships no `loading` colour at all. So the accent
  disappeared on precisely the two intents that most need it, and a pack passing the brand-pack lint
  still rendered them unbranded. The accent is now a **mapped constant**, and every one of its five
  tokens was checked to exist in `foundations-tokens.md`.

  These are the third and fourth survivors of one rewrite, after the two #542 caught. The lesson is the
  one this repo keeps paying for: **renaming a keyword in a signature does not find its call sites**, and
  a regex that fixes one passage does not find the others. This time the sweep was run for every dropped
  keyword across the whole repo, not just the section being edited — and the first attempt at that sweep
  silently matched nothing because of a shell glob, which is its own reminder that a check that did not
  run is not a pass.

### 1.42.0 — 2026-08-07

- **A stale remnant of the reversed error rule survived the rewrite** (Refs #540). The toast rebuild
  replaced the prose but left an ERB snippet showing `"data-toast-timeout-value" unless intent ==
  :error`, plus a sentence claiming the dismiss button *"already has `min-h-touch`"*. Both described
  the design as it was **before** that same commit reversed it — a `doctrine-contradiction` inside the
  file that had just been corrected. Found by grepping the pattern rather than trusting the edit, which
  is the discipline this repo keeps relearning: a regex that replaces one passage does not find the
  other three places the rule was stated.

- **The toast was a card, and the persistent-error rule was wrong** (Refs #483). Reported from a real
  run: the toast renders too big. Measured, and it was arithmetic rather than taste — `box` applies
  `--space-s` (16–20px) on all four sides, `min-h-touch` forces a **44px** dismiss target inside, and
  `max-w-sm` fixes the width, so *"Saved"* rendered roughly **80px tall by 384px wide**. `box` is the
  **content-panel** primitive; a toast is transient chrome.

  Rebuilt against the reference anatomy — **container · optional icon · text · optional action ·
  optional close**. The close button now appears **only beside an action**: a toast that leaves on its
  own needs no button, and with no button there is no touch target forcing the height. That fixes the
  size at its source rather than working around it. `title` + optional `description` replace the single
  `message`, and an **action slot** exists at last — *"Task deleted · Undo"* is the canonical toast, and
  without a slot people put the verb in the text and leave the user nothing to press.

  **And a correction to yesterday's rule.** This file said errors do *not* auto-dismiss, reasoned from
  `role="alert"`. That conflated **announcement** with **persistence**: `role="alert"` governs how a
  message is announced, not how long the box stays. Every toast now auto-dismisses. A message that must
  remain visible is not a toast — it is `Ui::Alert` in the page, and one that must be answered first is
  `Ui::Modal`. The escalation table is in both files.

  **One exception, found by reading the reference implementation's source rather than its docs:**
  `:loading` persists while its operation runs, then is **replaced** by the outcome. Both references
  model it that way, and it gets no close button either — dismissing a running operation leaves the user
  with no way to learn how it ended. An error is a *result* and results auto-dismiss; a loading toast is
  not a result yet. My first pass wrote *"there is no persistent variant"*, which was too absolute.

  Worth noting the touch-target arithmetic that made the old markup expensive: `min-h-touch` is 44px,
  which is **WCAG 2.5.5 Target Size (Enhanced), level AAA**. The level-AA requirement, 2.5.8, is
  *"at least 24 by 24 CSS pixels"* — verified against the W3C understanding document. Paying 44px inside
  a transient element bought AAA by doubling the notification's height.

### 1.41.0 — 2026-08-07

- **§2b — multi-factor, and the discount §2a was offering with no way to earn it** (Refs #531). §2a's
  table drops the password floor from 15 to **8 when the password is one factor of multi-factor**. Both
  lines were correct, and together they defined a **conditional discount whose condition the skill gave
  a reader no way to satisfy** — not a false claim, a true one with nothing behind it, which sends the
  reader out of our doctrine to re-invent per app.

  **Rails 8 ships no MFA at all** — verified against the installed gem, not assumed: the authentication
  generator's two migrations are its whole persisted surface, and a sweep for
  `totp|webauthn|passkey|mfa|otp` across the generator tree returns **zero**. Checked on 8.1.1 and
  8.1.3 with the same result, and the version boundary is recorded.

  What it *does* give you: `authenticate_by` verifies multiple **stored** secrets in one timing-hardened
  call — useful, and **not** a TOTP path, since a TOTP is clock-derived with no digest to compare. The
  `Session` model is a **row**, which is the real hook.

  Three rules that are ours and are the ones most often got wrong: **replay** — *"Verifiers SHALL accept
  a given OTP only once while it is valid"*, and `rotp` reports validity, never use, so `if
  totp.verify(code)` accepts the same digits all window; **MFA is a property of the session, not the
  user**, or enrolling silently blesses every existing session including one an attacker holds; and
  **recovery codes are a set** needing their own table with `used_at`, hashed, shown once.

  **SMS is *restricted*, not deprecated** — the popular claim is wrong, and shipping it would be the
  same defect as any other unverified assertion. Restricted is a status with obligations: an
  alternative authenticator **SHALL** be available, subscribers *SHOULD* be warned, and risk signals
  (SIM change, porting) *SHOULD* be considered.

### 1.40.0 — 2026-08-07

- **The password-strength component, implemented** (Refs #484). A worked `PasswordStrengthComponent` +
  Stimulus controller on role tokens, plus its call site on the two write paths §2a names. The floor
  comes from the **model**, never a literal in the component: two numbers for one policy is how a
  relaxed validator and a stale meter end up disagreeing, and the meter is the one the user believes.
  Announcement is **debounced** — a live region speaking per keystroke is unusable with a screen reader
  — and *unknown* stays a state, because the blocklist verdict is a round-trip and silence that reads as
  approval is the failure. No `dark:` variants anywhere: `bg-muted`/`bg-primary` are role tokens, so
  dark mode and forced-colors come free, whereas a meter built from `bg-green-500` is both a drift
  finding and unreadable in forced-colors.

  Three gates caught this work while it was being written: `undeclared-component-call-site` (the
  component was documented but never called), `controller-inventory-gap` (`password-strength` named in
  markup the inventory did not admit existed), and `component-without-call-site`. Each was a real gap in
  the addition, not a false positive.
- **A raised password floor now reaches the accounts already under it** (Refs #484). `auth-security.md`
  §2a shipped telling readers to *"let existing users through until they next set a password"* — which
  grandfathers a six-character password indefinitely, so the floor bound only the users who were going to
  comply anyway. It now says the opposite: after `authenticate_by` succeeds, a user whose stored password
  misses the current policy is confined to the change-password screen. **Design decision, not a citation**
  — verification found NIST SP 800-63B-4 §3.1.1.2 does *not* authorise this (its one mandatory trigger is
  *"evidence that the authenticator has been compromised"*, and a short password is not evidence), while
  its prohibition is on **periodic** rotation, which a fires-once condition is not. The section says so in
  those words instead of borrowing authority: [maintainer decision](https://github.com/fmanimashaun/claude-skills/issues/484#issuecomment-5209651634).
  The Rails half is a separate CONFIRMED verdict against `rails/rails` `8-0-stable`, and its crux is the
  trap: `allow_unauthenticated_access` is generated as `skip_before_action :require_authentication` —
  **one callback, by name** — so it never exempts a second `before_action`, and sign-out, the emailed
  reset link and the change screen itself each need their own named skip or the user is trapped or
  looping. The design crux is that a bcrypt digest cannot be measured and a `password_length` column
  would leak, so the app stamps the **policy version in force at set-time** (`default: 0`, so rows that
  predate the column are stale by construction). Six request specs — one per exemption plus the
  near-miss proving `allow_unauthenticated_access` does not exempt the guard. The "never re-validate strength inside
  `authenticate_by`" rule is unchanged — this happens after it returns, not during it.

  Same pass, same file: all seven citations read bare *"NIST SP 800-63B"* and now read **SP
  800-63B-4**. This is a **citation-precision fix, not a correction of the guidance** — the quoted
  composition-rule prohibition, the 15/8 split, the blocklist `SHALL` and the no-periodic-rotation
  rule were all verbatim correct. But the 15-character single-factor floor exists *only* in revision
  4 (July 2025, which **supersedes** the 2020 edition; superseded, not withdrawn — CSRC carries no
  withdrawal label), so bare *"SP 800-63B"* pointed at a document that does not contain the number
  the table states, and the citation did not support its own claim. The section now says why the
  suffix is load-bearing. One consequence caught in self-review: *"Force a change only on evidence of
  compromise"* sat two paragraphs above a section that forces one on policy violation — a
  `doctrine-contradiction` in the same file, now scoped to what the standard requires versus what we
  decided.
- **We shipped a 2FA recipe that produces a replayable one-time password** (Refs #531).
  `ecosystem-gems.md` said *"Need email confirmation, lockouts, or 2FA? Add a column, a mailer, a
  `rotp` check"*. True of the plumbing, dangerous as a recipe: verified that way a TOTP **accepts the
  same code repeatedly** inside its window, and *NIST SP 800-63B-4* makes single-use a **SHALL** —
  *"the verifier SHALL NOT accept a previously used OTP"*. Replay prevention is not a detail added
  later; it is the difference between a second factor and a decoration. 2FA is removed from that
  add-a-column sentence, which stays correct for confirmation and lockouts.

  Found by a research session sent to establish what Rails 8 ships natively for MFA. The answer was
  **nothing** — 19 generator templates across three generators, zero MFA terms — but the more useful
  finding was this one, in doctrine we had already published.

### 1.39.0 — 2026-08-06

- **Password strength — the component contract, with the checklist the issue asked for removed** (Refs
  #484). #484 specified *"a live requirement checklist"*. That checklist **is** the rule NIST prohibits,
  rendered: *"Verifiers and CSPs **SHALL NOT** impose other composition rules (e.g., requiring mixtures
  of different character types)."* A meter ticking *has uppercase · has a digit · has a symbol* teaches
  the user that `Passw0rd!` beats a passphrase, which is backwards — so the component shows only what
  the policy actually enforces: **length progress**, **confirmation match**, and **the server's
  blocklist verdict**. Never a score out of five, never a colour-only bar, never character classes.

  Four rules that fall out of existing doctrine rather than being new: the meter reports *progress
  toward valid*, not *invalid* — field errors stay in the field; `role="status"` on a container present
  from first paint and announced on a **debounce**, since a region speaking per keystroke is unusable;
  **submit is not gated on the meter**, because a client that disagrees with the server either blocks a
  valid password or lies about an invalid one; and the blocklist verdict is a round-trip, so **unknown
  is a state** — silence that reads as approval is the failure. The policy in `auth-security.md` §2a now
  points at this contract, closing the cross-reference criterion.

- **Flash → toast: the half the layout promised and nothing implemented** (Refs #483). The reference
  layout carries the comment *"flash output goes to `#toasts` below, via Turbo Stream"* — and **no code
  anywhere read `flash`**. Three call sites prepend a toast directly from a controller action, so a Turbo
  Stream response showed its toast while a plain `redirect_to … notice:` showed **nothing at all**: no
  inline flash either, because the layout deliberately renders no flash partial. The message was not
  un-styled, it was **lost**. Both paths now reach the same container, with `flash` drained **inside**
  the live region rather than beside it — rendering it anywhere else recreates the second notification
  surface this doctrine exists to remove.

  Rails' `notice`/`alert` shorthands are mapped explicitly, because a map omitting them silently
  downgrades half an app's messages to `:info`. And **errors do not auto-dismiss** — that follows from
  the existing markup rather than being a new rule: `:error` already renders `role="alert"`, and a
  message important enough to interrupt a screen reader is important enough to outlive five seconds.

- **`ToastComponent` was never declared, only drawn** (Refs #483). The Toast section shipped its ERB and
  no Ruby class, so a reader got the template without the object that renders it — and a call site
  naming `ToastComponent` could not be checked against any initializer. Found by `undeclared-component-call-site`
  firing on the new `render` in the flash path: the existing call sites use `turbo_stream.prepend(...)`,
  which that rule does not match, so the gap had been invisible since the component was written.

- **`art-direction.md` names itself the "look and feel" layer** (Refs #486). #486's last acceptance
  criterion greps the skill for craft vocabulary; four of five terms were present and *"look and feel"*
  was not. Added as a **routing gloss** in the opening rather than stuffed somewhere to satisfy a grep —
  an agent asked *"why does this look mechanical"* rather than *"which token is wrong"* should land on
  this file, and the phrase it would use was the one missing.

### 1.38.0 — 2026-08-06

- **A generated asset is not usable until its fitness is reviewed** (Refs #507). Nothing makes a prompt
  produce the asset you asked for — measured, not assumed: the test in §3a asked for empty space in the
  left two-thirds and got a centred motif. So an asset arrives as a **candidate**, and **unreviewed means
  unused**: until fitness passes the surface behaves as it does with no provider at all.

  **Fitness is not taste, and that decides who may block.** Taste is judgement and stays advisory.
  Fitness is a **comparison against a brief we wrote** — the prompt was composed from surface class and
  brand pack — so "brief said left-weighted, output is centred" is falsifiable, and comparisons can gate.
  The mechanical half (dimensions, weight, contrast against its role token, `alt`, format) is gateable.
  The looked-at half needs eyes on the image, which an agent has: reading an image renders it, and that
  is how the composition failure was found rather than shipped. **No recorded brief is a fail** — an
  asset nobody can re-check is one nobody can regenerate after a brand change either.

### 1.37.0 — 2026-08-06

- **Generated assets enter the hierarchy as two cost-ordered tiers** (Refs #507). The asset ladder now
  runs: **1** product screenshot · **2** brand-geometric decoration from `brand.json` · **3** a
  *designed graphic* exported from a brand template · **4** a *generated illustration* from a metered
  model · **5** commissioned. The ordering principle becomes *specificity first, then cost*, and the
  distinction between the two new tiers is the load-bearing part: **tier 3 inherits the brand, tier 4
  is prompted toward it and may miss** — a design tool assembles from parts you gave it, a diffusion
  model invents. If the asset can be *composed*, composing it is both cheaper and more faithful, so
  tier 4 is genuinely last-resort rather than the default anyone reaches for.

  **Tested before the doctrine was written, and tier 2 won.** A hero backdrop was generated from a
  brand kit and exported end to end — the pipeline works (`generate → candidate → design → export`
  returns a real 1920×1080 PNG). But it **ignored the composition brief**, returning a centred motif
  when asked for empty space in the left two-thirds, so a layout must never depend on a region of a
  generated image being empty. There is **no SVG export**, so a backdrop arrives as a **126 KB raster**
  against a few hundred bytes for the equivalent `decor-mesh`. And what came back was abstract
  geometric decoration — exactly what **tier 2 already produces from `brand.json`**, lighter, scalable,
  and brand-*derived* rather than brand-*flavoured*. So tier 3 is scoped to **what tier 2 cannot do**:
  composed scenes, product-adjacent mockups, editorial assembly, and brand **motion** (MP4/GIF, which
  tier 2 has no answer for). Prompting it for *"abstract shapes in the brand colours"* is paying bytes
  for a worse `decor-mesh`.

  **Tier 3 is exported assets only — never a page.** A design tool that can build whole pages must not
  be used to: its page output cannot be exported as code (formats are PDF, JPG, PNG, PPTX, GIF, MP4,
  CSV — verified, no HTML), it uses none of our role tokens, and no gate we ship can see it. A page
  authored there is a fork of the design system, which this file's own *"a pack is a theme, not a
  fork"* rule already forbids. Layout stays in Rails views built from primitives.

  **Tier 4's ceiling must refuse**, checked before the call that would cross it, with an unset ceiling
  meaning *refuse* rather than unlimited — a budget defaulting to infinity is not a budget. And where a
  provider bills all-or-nothing, a failed generation is free but a **completed-but-unusable one is paid
  for**, so the prompt is composed from the surface class and the brand pack rather than improvised.

  **The drift hazard is named, not gated.** Tier 2 derives identity from `brand.json`; tier 3 inherits
  it from an external brand kit. Two sources of truth for one brand, on adjacent surfaces.
  **`brand.json` is authoritative** — it is the copy under version control and under gate — and the
  external kit is a mirror to be checked. Nothing can compare them today, because the kit lives behind
  a connector, and saying so is more honest than implying a check exists.

- **§10 reconciled rather than contradicted** (Refs #507). It said the system *"produces nothing"* —
  true when v1.66.0 shipped it, false now. Rewritten, keeping the half that survives generation and
  matters more with it: **the improvisation ban.** A provider that is present but misconfigured is a
  *new* way to end up with nothing, and the answer is unchanged — satisfy from tiers 1–2, or say so and
  stop.

### 1.36.1 — 2026-08-06

- **The asset boundary, declared** (Refs #503). `visual-assets.md` §10 listed rejected *techniques* —
  ambient motion, SVG filters, `mask-*`, vendored illustration sets — and never said that the system
  **generates nothing**. Tier 1 is captured from the running product, tier 2 is CSS/SVG derived from
  `brand.json`, tiers 3–4 are sourced by a human and recorded; nothing emits a raster image. That was
  already true, and the gap mattered because **line 7 of that same file predicts what an agent does
  with an absent boundary** — *"leave it empty, generate something inconsistent, or import stock art
  that undercuts the brand"*. A file that names a failure and does not close it off is
  `claims-vs-enforcement` in the warning itself. So the rule is now explicit: if a surface cannot be
  satisfied from tiers 1–2, **say so and stop** — name the surface and what the tiers could not carry,
  and never ship a placeholder, a stock photograph or a hand-rolled "illustration". §6 keeps the cost
  low by making tier 2 primary on exactly the surfaces with nothing to screenshot; #507 tracks the
  bounded generation path for the case where that is not enough.

### 1.36.0 — 2026-08-05

- **The craft layer — `art-direction.md`** (Refs #486). Nineteen references answered *"is this
  correct?"* and none answered *"is this considered?"*. Measured: `art direction`, `visual hierarchy`,
  `focal point`, `look and feel`, `aesthetic` all returned **zero** across the skill, and
  `design-auditor`'s own priority order is `breaks-consistency > a11y > polish` — polish last, and
  framed as consistency. Everything we shipped was *avoid-the-bad* (`llm_tell_detector`) and
  *match-the-system* (`rendered_conformance`); there was no *achieve-the-good*.

  The doctrine: **one focal point per surface** carried by scale **or** weight **or** contrast, never
  all three; a **different brief per surface class** — marketing is emotion, a dense app is clarity, a
  focused task is calm — which is the direct answer to *"marketing reads as slop and the app reads
  mechanical"*, because both were given one treatment; **taste inside the constraints**, with exactly
  one bounded escape (one element on one surface may break the grid or the scale, and **never** the
  token contract, because a bespoke hex outlives the brand it was picked for); negative space as
  grouping; motion as sequence on top of `motion.md`. Two worked before/afters — a marketing hero and
  a dense table — where the "before" passes every gate we ship.

  `SKILL.md`'s routing description said *"Consistency is enforced here, not left to taste"*, which
  reads to an agent as taste being out of scope. Reconciled rather than overwritten: consistency is
  still enforced, and craft now has a named home.

### 1.35.0 — 2026-08-05

- **A password policy, and the rule the report asked for that NIST forbids** (Refs #484). A fresh
  Rails app accepts `a` as a password: `has_secure_password` gives bcrypt, the virtuals and a
  72-**byte** ceiling, and no strength policy at all. The doctrine's only mention was a
  **commented-out** `length: { minimum: 12 }` hint. `auth-security.md` §2a is now real doctrine —
  and **half of what the issue proposed is refuted**, which is the more valuable half of the verdict.

  **Verified against NIST SP 800-63B.** The issue asked for *"EITHER character-class composition OR
  a breach check"*. They are not alternatives: composition is *"Verifiers and CSPs **SHALL NOT**
  impose other composition rules (e.g., requiring mixtures of different character types)"*, and the
  compromised-password blocklist is a **SHALL**. So the section states the prohibition first, with
  the citation, because "at least one uppercase, one digit and one symbol" is the single most common
  thing a team bolts on and it makes passwords *worse* — it pushes users to `Passw0rd!` and away from
  a passphrase. The floor is **15** for single-factor (8 under MFA), the max is already validated by
  Rails so we do not re-add it, and rotation is **SHALL NOT**. Enforced on write paths only with
  `allow_nil: true`; never on sign-in, where `authenticate_by` verifies a digest that may predate the
  policy — re-validating there is a self-inflicted outage, and a spec pins that regression.

  The blocklist section states the local-list-vs-range-API trade-off honestly, including that a
  silent `rescue` around a network check is `gate-that-cannot-fail` **in your auth**.

### 1.34.0 — 2026-08-02

- **Legal, privacy and consent surfaces — the one subject the doctrine had nothing on** (Refs
  #475). Found by auditing against an external catalogue: of its 110 named failure modes this was
  our only clean zero (`grep -ril "privacy polic|cookie consent|consent banner"` → **0 files**),
  while #91 had just shipped checkout and billing. Three parts, and the change type differs per
  part:
  - **Verified.** *ARIA in HTML* (W3C) gives `<footer>` `role=contentinfo` *"if not a descendant
    of an `article`, `aside`, `main`, `nav` or `section` element"* — **"otherwise `role=generic`"**.
    That interacts with the band rule shipped in v1.60.0, which tells authors to wrap bands in
    `<section>`: put the page footer inside one and the landmark silently disappears. The two
    rules are stated together and enforced by the **same** join in
    `scripts/check_section_landmarks.py`, so they cannot drift apart.
  - **Verified.** GDPR Recital 32: *"Silence, pre-ticked boxes or inactivity should not therefore
    constitute consent"*, which must be *"a clear affirmative act"*. The UI consequences are
    mechanical — never render the box `checked`, never treat dismissal as acceptance, one checkbox
    per thing consented to.
  - **Ours.** That a consent surface is a **modal dialog we already document** (focus trapped,
    `aria-modal` + `inert`, focus restored) rather than a bespoke banner — APG has no consent
    pattern, checked rather than assumed. And the boundary: *which* surfaces a jurisdiction
    requires is the operator's decision. A design system that shipped a compliance checklist would
    be asserting something it cannot verify.

  The gate grew a second rule and two bugs of its own, both caught by its fixtures: an ERB comment
  reading *"its link list is NOT a `<nav>`"* opened an element that never closed, so the footer
  below it reported as nested; and blanking comments had to preserve newlines, or every line
  number after one is wrong. 25 → 42 fixtures, 6 → 10 mutations.

### 1.33.0 — 2026-08-02

- **`<section>` is a landmark only when you name it — practised in 16 of 18 places, stated in
  none** (Refs #91). *ARIA in HTML* (W3C) gives `<section>` `role=region` **"if the `section`
  element has an accessible name"** and `role=generic` otherwise — `generic` being exactly what a
  `<div>` exposes, so an unnamed `<section>` is inert markup that reads as structure. The skill
  already obeyed this everywhere except two hero bands, where it is deliberate: a hero's heading
  is the page's `<h1>`, so naming the region repeats the page title and adds a navigation target
  pointing where the reader already stands. Sixteen correct instances are not evidence the
  seventeenth will be, so the rule is now written in `page-anatomies.md` and held by
  `scripts/check_section_landmarks.py`, with the two heroes declared **by exact tag** rather than
  inferred — a carve-out that recognised its own exception by pattern would exempt every future
  violation that looked similar. A declared exemption matching nothing is itself reported.

- **The ecommerce composition recipe produced a block that was not navigable** (Refs #91). Every
  promo section in the corpus is a `<section aria-labelledby>`; the `Build from` string shared by
  nine ecommerce rows said *"Card + Heading + Description list / Table inside `grid-auto`"* and
  named no landmark, so an agent following it shipped a `div`. The recipe now carries it.

### 1.32.0 — 2026-08-02

- **The page-pacing doctrine shipped a rule the corpus refutes** (Refs #92). Rule 1 required tone to
  alternate *at every boundary* and rule 3 forbade a border — so at our own token values the two
  together specified a boundary carried by a **1.053:1** step (`--background` `#F8F9FB` /
  `--card` `#FFFFFF`) with nothing else marking it. Of six marketing templates studied, one
  alternates at **none** of its four boundaries, and the smallest step where tone genuinely carries
  a boundary is **24× ours**. Rule 1 is now stated as **continuity**, with rule 2 owning the
  boundary — which is what a reader actually perceives at that contrast.
- **Rule 3 becomes conditional rather than absolute.** Its authority was the *Elevation idiom*
  measurement, which is about elevation **within** a page and was lifted to page scale without
  re-checking. A template with a numerically identical step — ΔL 0.0177 against our 0.0181 — draws a
  hairline at exactly its two such boundaries and at **none** of the four where the step is 0.775.
  Where a boundary must carry tone alone, a border is now the honest fix rather than a violation.
- **Proof moves from band 4 to band 2**, resolving a file that contradicted itself: the band table
  said 4 while its own worked ERB said *"proof immediately under the fold line"*. Four of the six
  templates put proof at position 1–2.
- **6–8 bands is scoped to the product-landing genre**, and *"more is a page nobody reaches the end
  of"* is withdrawn — a conference page runs 5 and a long-form sales page runs 12, where the length
  *is* the product.
- **The inset rounded panel is named as a second legitimate band form.** The doctrine described
  full-bleed as the only shape; it is the default, not the only one.
- **Rule 2's argument had to be repaired, not just kept.** It proved the stronger "exactly one axis"
  form wrong *by appeal to rule 1's every-boundary requirement* — so correcting rule 1 would have
  left a stale proof behind. Reworded to survive the correction; the conclusion is unchanged.
- The brand-filled punctuation band the corpus also uses is **deliberately not adopted here**: it is
  a colour decision, and brand packs own colour, so it belongs against the pack contract rather than
  smuggled into pacing doctrine.

The **audit half** of #95. Its writing half is done — `coverage.md` reports **0 `needs doctrine`**
rows — so what was left was the four acceptance criteria the issue states *per group*, none of which
anything checked. Three failed. Change type: **no `doctrine-verifier` verdict is involved.** Every
claim corrected here is a claim fidara-design makes about **itself**, refuted by fidara-design's own
shipped files, so the authority is measurement against those files and each measurement now has a
script behind it (`CLAUDE.md` → *Measure anything measurable*). No new framework API is introduced
anywhere in it: every replacement reuses a recipe already shipped elsewhere in the same skill.

- **AC4 "no duplicate mechanisms" failed on the example the issue itself names** (Refs #95).
  `components.md` → Toast / Notification says the Toast mechanism *"replaces the duplicate
  `_flash`/`_flash_messages` pair"*, and `reference-implementation.md`'s base layout went on
  rendering `shared/flash_messages` inside `<main>` — the eliminated half of the pair, shipped in
  the same skill as its own replacement, in the file whose name says it is the reference. Removed;
  flash goes to `#toasts` via Turbo Stream and nowhere else.
- **The same block dropped all three things `page-anatomies.md` says a shell may not drop**
  (Refs #95). No skip link — **WCAG 2.4.1 Bypass Blocks is Level A**, and `page-anatomies.md` and
  `components.md` both already say so — a `<main>` with neither `id="main"` nor `tabindex="-1"`, so
  the link would have had nothing focusable to land on, and `#toasts` **without `aria-live`**, which
  `interaction-stimulus.md` refuses in terms: *"do not 'simplify' this by deleting the container's
  `aria-live` on the strength of the toast having a role."* Three of the four copies of that
  container appears in the docs carried it; this one did not. Fixed against the recipes already shipped in
  `component-implementations.md`, not against new markup.
- **AC3 "no new bespoke controllers where a mixin fits" was answered by a sentence that was false**
  (Refs #95). `interaction-stimulus.md` said `carousel` was *"the only new controller the #95 rows
  need"* while the snippets around it prescribed `dropzone` and `clipboard` (forms.md) and
  `combobox`, `disclosure` and `feed` (component-implementations.md) — five more, for #95 rows
  alone. Replaced by the measured inventory: a table of the **twelve** controllers the reference
  docs name beyond the ten already in the apps, each with what it drives and which mixins it
  composes. `dropzone` is the one that mattered most to state, because the same file warns that
  **none of the four mixins is a gesture mixin**.
- **`controller-inventory-gap`, so that table cannot drift again** — a new
  `lint_self_consistency.py` rule reconciling every `data-controller=` in the fidara-design
  references (18 today) against the inventory. One-directional on purpose: markup naming an
  unlisted controller is a reader inheriting an unspecified dependency, while a listed controller
  with no snippet is ordinary (`search`, `multistep`, `countdown` live in the apps). Its ERB half
  reads string literals only — `data-controller="theme <%= 'native-bridge' if native_app? %>"`
  names two controllers, and `if` is not one of them, which tokenising the raw attribute would have
  claimed and deleting the ERB would have missed. **The rule found a bug in itself on first run:**
  a ``` fence is three backticks, so the span pattern paired off by one from there and returned an
  inventory of 38 healthy-looking entries containing not one controller name — visible only because
  the rule then fired on all 18 controllers at once. **Then `mutation_check.py` refused the first
  fix for carrying two defences that could not both be load-bearing.** Excluding newlines from a
  span and stripping fences each kill that off-by-one, so whichever ran second survived every
  mutation. Only fence-stripping also stops a name inside a fenced *example* counting as "listed",
  so that is the one that stayed, with a fixture in each direction. A guard nothing can fail is not
  a guard, and here the gate said so about our own fix.
- **AC1's evidence table stopped letting one doc vouch for two rows** (Refs #95). `Select` and
  `Textarea` both cited `### Field anatomy` — the simple_form **wrapper**, generic to every field,
  which would still be there after every trace of either control was deleted — and `Checkbox`,
  `Radio group` and `Toggle / Switch` all cited one heading. `verify_interaction_claims` has refused
  a reused probe since it was written (*"one doc cannot be evidence for two different mechanisms"*)
  and `DOCUMENTED_EVIDENCE`, which decides 79 rows rather than 9, had no such rule — while its own
  Navigation comment records this exact defect being fixed by hand for two rows. The guard is
  **substring, not equality**, because `"## Button"` also occurs inside `"## Button group"`: that
  near-miss is what the table's hand-added trailing newlines defend against, and it is now a gate
  instead of a convention someone remembers.
- **No new doctrine was written to satisfy the table.** The five rows point at the text stating each
  control's own recipe — four of them a bullet in forms.md's `## Controls` — because non-heading
  evidence is the established shape for recipe-shaped rows (`divide-y divide-border`,
  `@utility frame`) and a control-specific string is harder to satisfy by accident than a heading,
  not easier. Checkbox and radio keep one shared bullet, because radio really is a one-word delta
  (`rounded-full`) from the checkbox; splitting the doc to give the table a heading each would have
  been the tail wagging the dog.
- **Two more AC4 duplicates, found by grepping for the pattern rather than stopping at the first**
  (Refs #95) — `CLAUDE.md` says that class travels in groups, and it did.
  - `page-anatomies.md` said the mobile rail *"becomes"* a drawer and that
    `Layout::SidebarComponent` *"owns the disclosure"*. `components.md` → Drawer / off-canvas says
    **"render both, do not morph one"** and makes the overlay a `Ui::Modal`; `interaction-stimulus.md`
    records correcting this exact conflation once already (*"`sidebar` is collapse only"*); and the
    shipped `SidebarComponent` contains **no disclosure and no drawer** — it is a two-column flex
    primitive. The correction had landed in two files and missed the third.
  - `forms.md` → Error summary prescribed hand-rolled markup (`box` + `border-destructive` +
    `role="alert"`) for the block `page-anatomies.md` specifies as `Ui::Alert intent: :error` on two
    separate anatomies. Now the component, which is also the file that forbids hand-rolling — and
    `AlertComponent#role` already returns `alert` for `:error`, so the hand-written attribute was
    redundant here and wrong on any other intent.
- **`Action panel` was left `derivable`, deliberately.** Its `Build from` works (Card + Heading +
  Button group), so writing an entry to tick an unticked box would add surface nobody asked for.
- #95 stays **open**: its five groups are a checklist, and an umbrella is not closed by the
  promotion that ships one slice of it.
- **fidara-design: the commerce family's catalog and cart slice** (Refs
  [#91](https://github.com/fmanimashaun/claude-skills/issues/91)) — the browse → select → cart path,
  taken as one group because it is one mechanism: a catalog card **cannot** carry an add-to-basket
  button (the `<a>` content model forbids an interactive descendant, and the stretched-link overlay
  covers a sibling), which is *why* quick-view exists, which is what fills the cart, which is what the
  drawer shows. Four catalogue entries in `components.md` — **Product card**, **Filter panel**,
  **Quick view**, **Cart drawer and cart line** — plus a markup section in
  `component-implementations.md`. **No new ViewComponent class**: every piece composes Card, Grid list,
  Disclosure, Modal, Media object and Empty state, which is #91's "no duplicate mechanisms" criterion.
  It also closes two dangling references — `components.md` already cited *"a cart line"* and *"the cart
  total"* with no entry behind either.
  **Change type: split.** The **framework claims** are CONFIRMED against the version in scope and cited
  in place: [WAI-ARIA 1.2](https://www.w3.org/TR/wai-aria-1.2/#aria-selected) (REC 2023-06-06) for
  `aria-selected`'s supported roles and `role="status"`'s implicit `polite`+`atomic`;
  [ARIA in HTML](https://www.w3.org/TR/html-aria/#el-button) (REC 2026-04-15); the
  [APG pattern index](https://www.w3.org/WAI/ARIA/apg/patterns/) (30 patterns — the negative for
  filter, product card, gallery, drawer and cart) plus its
  [Dialog](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/),
  [Disclosure](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/) and
  [Carousel](https://www.w3.org/WAI/ARIA/apg/patterns/carousel/) patterns; WHATWG HTML (Living
  Standard, 2026-07-20) for the [`<a>` content model](https://html.spec.whatwg.org/multipage/text-level-semantics.html#the-a-element),
  [`<s>` vs `<del>`](https://html.spec.whatwg.org/multipage/text-level-semantics.html#the-s-element) and
  [`inert`](https://html.spec.whatwg.org/multipage/interaction.html#the-inert-attribute); WCAG 2.2
  1.4.1 (A), 2.4.4 (A), [2.4.11](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum.html)
  (AA, new in 2.2), 2.5.8 (AA), 3.2.2 (A), 3.3.4 (AA), 3.3.6 (AAA) and
  [4.1.3](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html) (AA); Turbo 8.0.23. The
  **design/architecture** half — one link per card, quick-view is never the product page, drawer and
  page both exist, `aria-modal`+`inert` together, our stricter `aria-controls` — has no upstream, so its
  authority is the [maintainer decision recorded on #91](https://github.com/fmanimashaun/claude-skills/issues/91#issuecomment-5156613111).
- **One verdict came back INCONCLUSIVE and doctrine says so rather than inventing a citation** (Refs
  [#91](https://github.com/fmanimashaun/claude-skills/issues/91)). **Is removing a line from an open
  cart inside 3.3.4?** No W3C text decides it: the criterion covers *"modify or delete user-controllable
  data in data storage systems"*, while its Understanding document narrows the intent to *"prevent mass
  loss of data"* and excludes *"the simple creation or editing of … records"*. Decision (recorded on the
  issue, per CLAUDE.md): **a cart line is draft data — removal is immediate and reversible.**
  `crud-modal-pattern.md` gains *A confirmation is for what cannot be undone*, which scopes the
  previously unscoped destructive-action rule to **reversibility rather than destructiveness** — the
  condition its own worked example already stated (*"This can't be undone"*) and the rule did not. The
  undo is written as a contract, not a softer option, because **no specification requires an undo
  anywhere**: 3.3.4 offers Reversible / Checked / Confirmed as alternatives and 3.3.6 is Level AAA.
- **Two defects in already-shipped doctrine, found by grepping the pattern** (Refs
  [#91](https://github.com/fmanimashaun/claude-skills/issues/91)). (1) `page-anatomies.md` told every
  agent that product-gallery *"thumbnails are buttons in a group, with the active one announced as
  selected"* — `aria-selected` is scoped by ARIA 1.2 to `gridcell`/`option`/`row`/`tab` and is not in
  `button`'s supported set, so that shipped an attribute invalid in both ARIA 1.2 and *ARIA in HTML*
  which announces nothing. Fixed **by reuse**: a thumbnail that *picks* an image is the documented
  Carousel's **Tabbed** style, where `role="tab"` makes `aria-selected` legal — and the distinction is
  now written down (a thumbnail that **opens** a viewer is a `button`; one that **selects** is a `tab`).
  (2) `Seat / quantity selector` and `Promo / discount code` both rested "never submit on change" on
  **3.2.2 On Input**, which is narrower than that: it forbids a change of *context*, and WCAG states
  *"a change of content is not always a change of context"*. A total restreamed in place without moving
  focus is permitted. **The rules stand; their authority was wrong**, and both now say the money carries
  them. The neighbouring `Stepper` citation was checked and left alone — advancing a step moves focus,
  so there 3.2.2 genuinely applies.
- **No coverage `ENTRIES` rows, and the gap is disclosed rather than left to be found** (Refs
  [#91](https://github.com/fmanimashaun/claude-skills/issues/91)). `coverage.md` and
  `docs/coverage.html` need the licensed corpora to regenerate, so committing rows here would fail the
  drift gate on the next maintainer's machine. **`verify_no_undeclared_entry` cannot see this gap**: it
  matches on row name, and the four new headings are named differently from the four `derivable` rows
  they back — the same shape as the `Command palette` row that guard was written for, in the half it
  does not cover. The exact flip (four rows, two `BUILD` deletions, four evidence strings, each checked
  against the shipped headings and found exactly once) is
  [on the issue](https://github.com/fmanimashaun/claude-skills/issues/91#issuecomment-5156613111) for a
  corpora-attached follow-up.

### 1.31.1 — 2026-08-02

- **The coverage matrix now reports #91's slice-2 work, which it had been silently under-reporting**
  (Refs #91). Four catalogue entries and two archetypes shipped in v1.55.0 with **no `ENTRIES` rows**,
  so the matrix described a smaller system than the one we ship. That was deliberate, not an
  oversight: regenerating `coverage.md` needs the licensed corpora, and committing rows without
  regenerating leaves a stale matrix that fails the drift gate on the next maintainer's machine —
  the "damage still landed elsewhere" shape `CLAUDE.md` records. Cleared here on a corpora-attached
  machine, with both artifacts regenerated. **118 rows from 93 TW + 63 FB.**
- **`Number input` was flipped, not duplicated.** Slice 2 shipped `## Seat / quantity selector`, and
  Flowbite's `Number Input` was already claimed by the existing `derivable` row — the totality guard
  allows exactly one claimant, so a second row would have failed rather than added. Its `BUILD`
  fallback is deleted too: a `documented` row carrying one is precisely what `verify_shipped_evidence`
  refuses.
- **No row invented for "Invoice / statement"** — it is the existing `Detail anatomy`, and a row for
  it would have misreported the matrix in the opposite direction.
- Every one of the six evidence strings was checked against the shipped headings **before** being
  trusted (each found exactly once). That is the trap that failed this repo twice at promotion time,
  on Checkout and on Navigation, where a slice improved the structure and falsified the row.

### 1.31.0 — 2026-08-02

- **fidara-design: `page-anatomies.md` gains *How a page is paced*** (Refs [#92](https://github.com/fmanimashaun/claude-skills/issues/92),
  the Phase-5 *template synthesis* issue — its shippable half only; see Repository hygiene for the
  gate). The defect is **measurable in our own generated data**: **14** of the 16 marketing-section
  rows in `references/coverage.md` carry a *byte-identical* `Build from` string (the two exceptions
  are *Marketing header* and *Footer*). Every row is correct alone; followed literally they compose
  fourteen identical centred stacks separated by equal whitespace — a page right in every part and
  flat as a whole. The new section ships the missing layer: a **6–8 band** default sequence with
  three axis columns (Tone · Columns · Width), and the rules that keep consecutive bands from
  reading the same — tone alternates at every boundary, consecutive bands never share both Columns
  and Width, edges come from tone rather than a `border-b`, a `card`-tone band carries no
  `Ui::Card`, one primary *action* at most once per band, decoration in at most two non-adjacent
  bands. It **composes only from rows that already exist** and introduces no new token, `@utility`,
  `brand.json` field, archetype or framework syntax.
  **Change type: design/architecture** — there is no specification for how many bands a marketing
  page has or in what order, so `doctrine-verifier` would return INCONCLUSIVE for want of a source;
  authority is the maintainer decision recorded on
  [#92](https://github.com/fmanimashaun/claude-skills/issues/92#issuecomment-5152577804). Every
  claim that *does* have a source is cited to the file carrying it (`foundations-tokens.md`
  → *Elevation idiom*, `visual-assets.md` §8, `motion.md` §14, the *Settings* nested-card rule), and
  the one number asserted about ourselves is **measured, not asserted** — see the gate below.
- **The proposal's "exactly one axis moves per boundary" was rejected, and the reason is in the
  section.** It **contradicts the tone rule outright**: if tone must change at every boundary and
  only one axis may change, tone is the axis that changes every time, so Columns and Width never
  change at all — the stricter-sounding rule *is* the flat page. The shipped rule is a floor rather
  than an equality: never share **both** Columns and Width, which is exactly what the 14 identical
  rows break, and which a script can decide.
- **`Landing` now says it is the spine of that sequence, not a second answer.** Its four sections
  are bands 1, 2, 5 and 7, so the two are one doctrine rather than two that drift.
- **`fidara-design` — plans/pricing and billing, the second slice of the commerce family** (#91).
  Two page anatomies (**Plans — compare and switch**, **Billing**) plus **Invoice / statement**, which
  is deliberately *not* a fourth anatomy: it is the shipped `Detail` anatomy with the only three
  differences named (immutable, so no edit affordance; the money/reference type split; print is the
  same template). Four catalogue entries — **Plan comparison / feature matrix**, **Seat / quantity
  selector**, **Saved payment methods**, **Subscription state and dunning** — plus worked markup for
  the matrix, the default-method radio group and the past-due notice.
  Externally verifiable claims, each cited at the version in scope:
  WCAG 2.2 [1.1.1 (A)](https://www.w3.org/TR/WCAG22/#non-text-content) with the
  [non-text-content definition](https://www.w3.org/TR/WCAG22/#dfn-non-text-content),
  [1.3.1 (A)](https://www.w3.org/TR/WCAG22/#info-and-relationships) via
  [H63](https://www.w3.org/WAI/WCAG22/Techniques/html/H63) /
  [H43](https://www.w3.org/WAI/WCAG22/Techniques/html/H43) /
  [H39](https://www.w3.org/WAI/WCAG22/Techniques/html/H39),
  [1.4.1 (A)](https://www.w3.org/TR/WCAG22/#use-of-color),
  [1.4.10 (AA)](https://www.w3.org/TR/WCAG22/#reflow),
  [3.2.2 (A)](https://www.w3.org/TR/WCAG22/#on-input),
  [3.3.4 (AA)](https://www.w3.org/TR/WCAG22/#error-prevention-legal-financial-data);
  [ARIA 1.2 `aria-sort`](https://www.w3.org/TR/wai-aria-1.2/#aria-sort);
  APG [Table](https://www.w3.org/WAI/ARIA/apg/patterns/table/),
  [Grid](https://www.w3.org/WAI/ARIA/apg/patterns/grid/) and
  [Alert](https://www.w3.org/WAI/ARIA/apg/patterns/alert/);
  [ARIA in HTML](https://www.w3.org/TR/html-aria/) for `input type=number` → `spinbutton`;
  WHATWG HTML for the [`type=number` note](https://html.spec.whatwg.org/multipage/input.html#number-state-(type=number)),
  the underflow/overflow/step-mismatch validity states, `<caption>` and
  [`download`](https://html.spec.whatwg.org/multipage/links.html#downloading-resources);
  **PCI DSS v4.0.1 (June 2024) Requirement 3.4.1** quoted from the standard itself for PAN masking,
  with the scope condition stated rather than assumed — a tokenised merchant is outside it only
  because no code path touches a raw PAN, not because the requirement exempts them.
- **A source conflict recorded instead of resolved by fiat** (#91). Whether `role="alert"` is
  announced for a banner already present at page load has **no normative answer**: ARIA 1.2 (the
  Recommendation) is silent on load timing, [ARIA 1.3](https://www.w3.org/TR/wai-aria-1.3/) is a
  *Working Draft* and says an alert is announced *"when the alert is rendered on the page"*, while
  [APG](https://www.w3.org/WAI/ARIA/apg/patterns/alert/) reports the measured opposite — *"at this
  time, screen readers do not inform users of alerts that are present on the page before page load
  completes."* Doctrine states the disagreement and then decides: a state true at load goes in the
  reading order, `role="alert"` is reserved for a change during the session. No MUST is claimed in
  either direction.
- **`type="number"` for a seat count is a decision between two live sources, and both are named**
  (#91). The HTML Standard's spinbox test leaves quantities in — its own `min`/`max` example is
  `<input name="quantity" … type="number" min="1">` — while the **GOV.UK Design System** currently
  says *"Do not use `<input type="number">` unless your user research shows that there's a need for
  it"*, with no carve-out for incrementable numbers, citing the wheel-scroll hazard. That hazard is
  real and unspecified: an [open WHATWG issue](https://github.com/whatwg/html/issues/10911), and
  **Firefox disabled the behaviour by default in 130**
  ([bug 1741469](https://bugzilla.mozilla.org/show_bug.cgi?id=1741469)). The entry picks
  `type="number"`, says why, and marks `inputmode="numeric"` a legitimate Project Override — rather
  than citing one source and omitting the other.
- **The money-typography question the checkout slice escalated is now settled, at the source** (#91).
  `brand.md` gains **Money is `tabular-nums`, not `--font-mono`**: the ruling stands, and it is now
  backed by mechanism rather than by a scope list. `tabular-nums` maps to the OpenType `tnum` feature
  ([CSS Fonts 3 §tabular-nums](https://www.w3.org/TR/css-fonts-3/#tabular-nums), W3C Recommendation
  2018-09-20; [CSS Fonts 4](https://www.w3.org/TR/css-fonts-4/#valdef-font-variant-numeric-tabular-nums)
  repeats it verbatim), and the spec **forbids synthesis** when a font lacks it — *"no attempt is made
  to synthesize the feature except where explicitly defined for specific properties"*
  ([§feature-precedence](https://www.w3.org/TR/css-fonts-3/#feature-precedence)), and
  `font-variant-numeric` is not among the exempt properties. So the rule carries a **pack-font
  condition**: measured against the font binaries, Bricolage Grotesque implements `tnum` functionally;
  Newsreader and Overpass Mono register it inertly, being tabular already. `brand_pack_lint.py` cannot
  check this — a pack declares a family *name*, not a *binary* — so overriding `fonts.sans` is the one
  override carrying a manual check, and doctrine says so rather than implying a gate exists.
  **Change type: design/architecture** for the choice itself (no W3C or WHATWG document takes a
  position on monospace versus tabular figures for currency); authority is the maintainer decision on
  [#91](https://github.com/fmanimashaun/claude-skills/issues/91).
- **`components.md` → Description list contradicted that ruling, and the shipped component could not
  obey it** (#91). The entry said *"money and identifiers in `font-mono`"* while `page-anatomies.md`
  and `component-implementations.md` already said money is `tabular-nums` — a `doctrine-contradiction`
  inside one skill, which an agent building an invoice row would have resolved the wrong way. Fixed at
  both ends: the entry now names two options, and `Ui::DescriptionListComponent::RowComponent` gains
  `numeric:` beside `mono:` (passing both raises), because the ruling was previously unimplementable in
  the component the ruling is about — `claims-vs-enforcement` on our own doctrine.
- **A plan change is a modal, and `crud-modal-pattern.md` now says so with the reasoning** (#91). The
  checkout exception's four conditions are run against a plan change as a worked negative: it fails
  three, so it is ordinary CRUD on a subscription record. The one case that flips it — a change that
  must collect a *new* payment instrument — hands off to Checkout, because a provider iframe inside a
  focus trap is the failure the exception exists to avoid. Written down because "money ⇒ full page" is
  the reasonable wrong reading of the exception, and it would produce a new full-page flow every
  release. **Change type: design/architecture**; authority is the maintainer decision on
  [#91](https://github.com/fmanimashaun/claude-skills/issues/91).
- **Five negatives recorded so they are not reinvented** (#91). (a) **1.4.10 Reflow explicitly permits
  horizontally scrolling a data table** — its Note 2 names *"data tables (not individual cells) … It is
  acceptable to provide two-dimensional scrolling for such parts of the content"* — so our card-stack
  preference is ergonomics and must never be cited as conformance. (b) **No spec requires any markup on
  a currency amount**: WCAG 2.2 does not contain the word "currency", and neither `<data>` nor `<bdi>`
  carries a currency example in the HTML Standard. (c) **Stating "(PDF, 240 KB)" on a download link is
  not a WCAG requirement at any level and not a technique for 2.4.4 either, sufficient or advisory**;
  G201, usually cited for it, is about opening new windows. (d) **A plan downgrade is not settled by
  3.3.4's text** — the Understanding document narrows the SC away from *"the simple creation or editing
  of … records"* — so our downgrade confirmation is recorded as a product decision, while cancelling
  and deleting a stored payment method remain squarely inside the criterion. (e) The `✓`-needs-a-name
  rule follows from WCAG's *definition* of non-text content — *"or where the sequence is not expressing
  something in human language"* — and is stated that way, because WCAG's note names ASCII art,
  emoticons and leetspeak, not symbol glyphs. The #142 discipline throughout: cite what the source
  says, not what it is taken to say.
- **Not done in this slice, and deliberately** (#91): no rows were added to
  `scripts/build_coverage.py`'s `ENTRIES` for the four new catalogue entries and three anatomies.
  `coverage.md` and `docs/coverage.html` can only be regenerated with the licensed corpora attached,
  and committing an `ENTRIES` change without regenerating them would leave a stale matrix that fails
  the drift gate on the next maintainer's machine — the exact "damage still landed elsewhere" shape
  CLAUDE.md records for the corpora exemption. The rows and their evidence strings are listed on
  [#91](https://github.com/fmanimashaun/claude-skills/issues/91) for a corpora-attached follow-up.

- **The generated-layout tree listed `test/` in the file that mandates `--skip-test` fifty lines
  above it** (#395). §1 of `project-setup.md` says the framework's test scaffolding "must never be
  generated"; §2's tree then listed `test/` as part of what a generated app contains, so an agent
  reading the tree as the map of a scaffolded app believed a directory §1 guarantees is absent.
  Verified: `--skip-test` skips `build(:test)` outright, so none of `test/test_helper.rb`,
  `test/fixtures/files/`, `test/controllers/`, `test/mailers/`, `test/models/`, `test/helpers/` or
  `test/integration/` is written, and `capybara`/`selenium-webdriver` leave the `Gemfile` with it
  ([`app_generator.rb`](https://github.com/rails/rails/blob/8-1-stable/railties/lib/rails/generators/rails/app/app_generator.rb)
  `create_test_files`,
  [`Gemfile.tt`](https://github.com/rails/rails/blob/8-1-stable/railties/lib/rails/generators/rails/app/templates/Gemfile.tt),
  both gated on `depends_on_system_test?`; fetched 2026-08-01). **The row was also wrong on its own
  terms, before `--skip-test` is considered**: `def test` creates no `test/jobs/`, and `test/system/`
  + `test/application_system_test_case.rb` are written only when `--devcontainer` is *also* passed
  (`build(:system_test)` is called unconditionally but its body is `if devcontainer? &&
  depends_on_system_test?`). So the row is gone rather than corrected, and the note replacing it says
  what is absent, what takes its place (`spec/`, from `rspec:install`), the two consequences already
  documented elsewhere, and — because a deletion invites a restoration — not to add it back from
  memory. Version boundary: Rails **8.1** (`8-1-stable`, = 8.1.3.1); the flag's behaviour is not new
  in 8.1, the contradiction was with our own doctrine.
- **The issue's stated consequence for mailer previews was REFUTED, and the real defect is a
  different one** (#395). The report reasoned that previews at `test/mailers/previews/` would leave
  `/rails/mailers` "silently empty" because rspec-rails does not change `preview_paths`. Both halves
  are wrong, and the corrected doctrine had to be written from the sources rather than from the
  issue. (a) Rails' railtie adds its default as a **union** — `options.preview_paths |=
  ["#{Rails.root}/test/mailers/previews"]` — so that path is in the search list whether or not the
  directory exists, and a preview hand-written there *does* render
  ([`railtie.rb`](https://github.com/rails/rails/blob/8-1-stable/actionmailer/lib/action_mailer/railtie.rb)).
  (b) rspec-rails **does** set the path: its `rspec_rails.action_mailer` initializer runs `before:
  "action_mailer.set_configs"` and appends `"#{Rails.root}/spec/mailers/previews"`, and
  `rails g mailer` writes the preview file there
  ([`rspec-rails.rb`](https://github.com/rspec/rspec-rails/blob/v8.0.4/lib/rspec-rails.rb),
  [`mailer_generator.rb`](https://github.com/rspec/rspec-rails/blob/v8.0.4/lib/generators/rspec/mailer/mailer_generator.rb)).
  So the harm was not an empty page but doctrine naming a directory the mandated scaffold does not
  create — telling an agent to hand-build the `test/` tree §1 promises will not exist, in a second
  location from where the generator on line 14 of the same file actually writes. `mail-storage-richtext.md`
  §1 now states `spec/mailers/previews/` with the mechanism behind it.
- **`config_default_preview_path` guards on `.empty?`, so *appending* a preview path also drops the
  `spec/` default** (found while verifying #395). Not in the report, and the non-obvious half: because
  rspec-rails only supplies its default *"unless `options.preview_paths.empty?`"*, any app-level touch
  of the setting — `<<` included, not just assignment — suppresses `spec/mailers/previews` silently.
  The guidance therefore names both paths in the worked example rather than showing the guides' bare
  append. Assignment is called out separately as unable to *remove* Rails' `test/` entry, since the
  railtie unions it back afterwards. Also recorded: `show_previews` defaults to
  `Rails.env.development?`, and `preview_path` **singular** is not a Rails 8 setting — deprecated in
  **7.1**, removed in **7.2**
  ([Action Mailer CHANGELOG](https://github.com/rails/rails/blob/v7.2.0/actionmailer/CHANGELOG.md)).
  Change type: framework claim, CONFIRMED verdict; sources above fetched 2026-08-01.
- **fidara-design: the list family is documented — Stacked list, Grid list, Activity feed / Timeline**
  (Refs #95, the Phase-2 umbrella's *Lists + data display* group). All three were `derivable` rows whose
  entire guidance was one **Build from** cell (*"Media object rows inside a `divide-y` container"*), while
  the group's acceptance criterion asks for variant × size × state, an a11y contract and responsive rules.
  `coverage.md` **69 → 72 `documented`**, 44 → 41 derivable. Verified against
  [APG Patterns index](https://www.w3.org/WAI/ARIA/apg/patterns/) (still **30**, re-counted),
  [Feed](https://www.w3.org/WAI/ARIA/apg/patterns/feed/), [`feed`](https://www.w3.org/TR/wai-aria-1.2/#feed),
  [Grid](https://www.w3.org/WAI/ARIA/apg/patterns/grid/), [Listbox](https://www.w3.org/WAI/ARIA/apg/patterns/listbox/),
  ARIA 1.2 [`list`](https://www.w3.org/TR/wai-aria-1.2/#list) / [`listitem`](https://www.w3.org/TR/wai-aria-1.2/#listitem),
  and WCAG 2.2 [1.3.1](https://www.w3.org/WAI/WCAG22/Understanding/info-and-relationships.html) (A) and
  [2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum.html) (AA).
- **Three ARIA patterns are near-misses for a list of records and every one of them is wrong — stated
  with the quote that rules it out.** **Listbox**: *"it does not provide an accessible way to present a
  list of interactive elements, such as links, buttons, or checkboxes"*, which is what a record row is.
  **Grid**: *"A grid is a composite widget so it: Always contains multiple focusable elements … Requires
  the author to provide code that manages focus movement inside it"* — a wall of cards has no roving
  tabindex, so `role="grid"` announces a keyboard model that does not exist. **Feed**: scoped to
  *"a dynamic list of articles that often appears to scroll infinitely"*, so a fixed-length history is
  not one. Plain `list`/`listitem` is the answer, and *"Authors **MUST** ensure elements whose role is
  listitem are contained in, or owned by, an element whose role is list"*.
- **FIX — every list this kit ships loses its list semantics in Safari, and two things we already
  ship are what cause it.** Tailwind v4's Preflight sets `ol, ul, menu { list-style: none }`
  ([Preflight](https://tailwindcss.com/docs/preflight)), and WebKit then drops the role **on purpose** —
  *"This was a purposeful change due to rampant 'list'-itis by web developers… If you want to override
  the heuristic, you can add `role=list`"* ([WebKit 170179](https://bugs.webkit.org/show_bug.cgi?id=170179),
  resolved as a duplicate of 134187, unretracted through the tracker's last activity in January 2023 and
  still reproducing in independent testing on Safari 15.6–17). Tailwind's **own** docs carry the fix
  verbatim — *"Unstyled lists are not announced as lists by VoiceOver… add a `list` role to the element"* —
  which is the citation used, because it is first-party to the framework we ship. The criterion is
  **1.3.1 Info and Relationships (Level A)**, and the markup passes its technique **H48** while the
  accessibility tree does not, so nothing in the HTML looks wrong.
  - **Nine shipped markup sites and six prose rules were emitting bare lists** and now carry
    `role="list"`: the cart lines, the checkout and order-progress `<ol>`s, the mobile card-stack
    fallback, the navbar / mobile-nav / rail / nested-section lists, the Breadcrumbs `<ol>`, and the prose
    prescribing a bare `<ul>` or `<ol>` for the rail, the Stepper, the avatar group, the Breadcrumbs row
    and the mega-menu columns (twice). Found by grepping the pattern rather than fixing the one
    instance, per CLAUDE.md.
  - **A claim I expected to make was REFUTED, and shipping it would have misdirected people.**
    `display: flex` / `display: grid` **on the list element itself** does *not* break list semantics in
    current Safari, Chrome or Firefox — so `stack`, `cluster` and `grid-auto` on a `<ul>` are all safe.
    The real hazard is `display: contents` used to flatten a `<ul>` wrapper so its `<li>`s become grid
    items, which resets the accessible role; MDN's answer is `subgrid`
    ([Grid layout and accessibility](https://developer.mozilla.org/en-US/docs/Web/CSS/Guides/Grid_layout/Accessibility)).
    The broader claim is written down as the thing *not* to believe.
- **The feed entry states which document binds, because APG and core ARIA disagree in strength.** APG
  states `aria-posinset`/`aria-setsize` flatly; ARIA 1.2 says authors **MAY**. We bind to the APG pattern
  and say so. Two negatives are recorded the #142 way: **`aria-level` is not part of the Feed pattern**
  (it is a `listitem` property, and it appears nowhere in the pattern), and **`role="feed"` takes no
  `role="list"`** — `feed` is a subclass of `list` whose required owned elements are `article`.
- **Three claims are OURS and say so, because the gate found no upstream** (design decisions under
  CLAUDE.md's *What the gate covers* carve-out, recorded on
  [#95](https://github.com/fmanimashaun/claude-skills/issues/95)): (1) applying Tailwind's `<ul>`-shaped
  callout to `<ol>` as well; (2) the one-stretched-link-per-row rule, and the corollary that a row with a
  second control must not use it, because the overlay covers its siblings; (3) `<time datetime>` with a
  relative label — **no WCAG criterion governs relative versus absolute time, and none mandates `<time>`**.
  Likewise **no success criterion requires `aria-posinset`/`aria-setsize`** outside the feed pattern, so
  the entry scopes them to virtualised lists rather than implying an obligation.
- **FIX — the Media object entry carried its `a11y` bullet twice**, with the decorative-`alt` rule stated
  in both and the responsive rule buried inside the first. Merged; the `Responsive:` bullet now holds the
  responsive rule, like every other entry in the file.
- **FIX — `coverage.md`'s derivable section said something stronger than it meant, and was already false.**
  *"No dedicated catalogue entry, and none needed"* — while Command palette, a derivable row, has had a
  `components.md` section since #229. The distinction the file actually draws is **anatomy**, not the
  existence of a section, so it now says that and names the exception instead of contradicting it.
- **FIX — `Chat bubble`'s `Build from` re-spelled the Stacked list's composition** instead of pointing at
  it, so it went stale the moment that row was promoted. Same defect the promoted-row guard exists for,
  in the half it does not cover (`derivable` rows).
- **FIX — `fidara-design/SKILL.md` advertised "~16 catalog components"; the catalog holds well over twice
  that.** Replaced with a pointer to `coverage.md`, which a script regenerates — a count restated in prose
  beside a generated one is a second copy with no arbiter, which is how it drifted.
- **`coverage.md` told agents the Command palette had no catalogue entry, and one had shipped
  since #95** (#89). The row printed under *"Derivable — No dedicated catalogue entry, and none
  needed"* while `components.md` carried `## Command palette`, so the matrix routed readers past
  a written entry and gave them a shorter Build-from line in its place — losing the rules only the
  entry states (no APG pattern covers a command palette; `aria-haspopup="grid"` is needed once the
  result rows carry icon + label + shortcut). The row is now `documented` with its own evidence
  string, taking the matrix to **73 documented / 40 derivable / 0 needs doctrine**.
  **Change type: design/architecture** for the guidance state — it is a claim about our own
  doctrine, so it is measured against the repo and made re-checkable by the guard below rather
  than asserted.
- **The guard that could not have caught it, added** (#89). `verify_shipped_evidence` only ever
  read this module's own tables: `documented` ⇒ evidence present, and not-`documented` ⇒ no
  evidence key. Neither looks at the docs for a row that claims nothing, so a row whose entry
  exists while the matrix denies it was invisible — the one-way `carve-out-without-negative-test`
  shape that `verify_interaction_claims` was given both directions to avoid in #399, still sitting
  in the older and larger half. `verify_no_undeclared_entry` closes it, over both catalogue files
  (`components.md` **and** `forms.md`, which is where half the form controls are catalogued), with
  six fixtures and three mutations. Two near-miss fixtures pin the match to exact-or-separator in
  **both** prefix directions, because the way this guard fails is by becoming a false-positive
  machine somebody then deletes.
- **A REFUTED APG attribution in `components.md`'s Command palette entry** (#89). It read *"the
  'dialog popups move DOM focus' rule applies to opening the modal, not to the filtered list
  inside it"*, merging two separate provisions into one rule APG does not state. The Combobox
  pattern's *"Unlike other combobox popups, dialogs do not support `aria-activedescendant` so DOM
  focus moves into the dialog from the combobox"* is scoped to a combobox whose **own popup** is a
  dialog (the Date-Picker-Combobox shape) and never reaches a palette, whose popup is a listbox or
  grid; the outer shell's focus-on-open is the separate Dialog (Modal) rule, *"When a dialog opens,
  focus moves to an element inside the dialog"*. Both now cited apart.
  https://www.w3.org/WAI/ARIA/apg/patterns/combobox/ ·
  https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/ (verified 2026-08-01).
  The entry's other external claims were re-verified and stand: the APG Patterns index carries
  **30** patterns and none is a command palette (https://www.w3.org/WAI/ARIA/apg/patterns/,
  counted from the page rather than read off a summary), and `grid` is a valid `aria-haspopup`
  token in ARIA 1.2 (https://www.w3.org/TR/wai-aria-1.2/#aria-haspopup).

### 1.30.0 — 2026-08-01

- **`brand.md` — how to start a pack when the client has no palette** (#129). A decision path, not
  a gallery: logo colour → does the product recede → hue family → formality, stop at the first
  answer. Plus the snap path for a client who *does* have brand colours, and the statement the
  issue asked for plainly — this is **a starting point for client onboarding, not a style menu**.
  **Change type: design/architecture** (the brand-pack model has no upstream); authority is the
  maintainer decision on [#129](https://github.com/fmanimashaun/claude-skills/issues/129).
- **The contrast bar in that section is externally verifiable and cited, not asserted.** 4.5:1 per
  WCAG 2.2 SC 1.4.3 (Level AA), with the 3:1 allowance correctly scoped to large-scale text
  (≥18pt / ≥14pt bold): https://www.w3.org/TR/WCAG22/#contrast-minimum. It also records what is
  **not** gated and why: SC 1.4.11 requires 3:1 only of information *required* to identify a
  component, and its Understanding note states that a control with visible content needs no
  boundary indication — so gating `--border`/`--input` on a flat ratio would be stricter than the
  spec, and a rule stricter than the spec is a rule people switch off.
  https://www.w3.org/TR/WCAG22/#non-text-contrast ·
  https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html


- **`bin/ci` was doctrine's "whole gate" and ran zero specs** (#391). The skill mandates
  `--skip-test`, and Rails wraps every test step in its generator template in
  `<% unless options[:skip_test] -%>`
  ([`config/ci.rb.tt` on `8-1-stable`](https://github.com/rails/rails/blob/8-1-stable/railties/lib/rails/generators/rails/app/templates/config/ci.rb.tt),
  fetched 2026-08-01) — so the mandated scaffold writes a `config/ci.rb` with no `Tests: Rails`, no
  `Tests: Seeds`, and not even the commented-out `Tests: System` line. `testing.md` §11 then told the
  agent to *"swap the test step"*: an edit to a line the mandated invocation never writes, while four
  other places went on calling `bin/ci` the full gate. A `gate-that-cannot-fail` in shipped doctrine.
  §11 now gives the **whole file** a `--skip-test` app needs — `Tests: RSpec` plus the `Tests: Seeds`
  step Rails also drops, ordered after the suite because `db:seed:replant` truncates and re-seeds —
  and the mandate moved beside `--skip-test` itself in `project-setup.md` §1, where the consequence
  originates. `SKILL.md` (golden-path step 7, the 8.1 feature list, Definition of done) and
  `deployment-kamal.md` now state plainly that a green `bin/ci` without that step proves lint and
  audits only. DSL surface re-verified rather than assumed against
  [`ActiveSupport::ContinuousIntegration`](https://github.com/rails/rails/blob/8-1-stable/activesupport/lib/active_support/continuous_integration.rb):
  `step(title, *command)`, `success?`, `failure(title, subtitle)` — nothing else, and `CI.run`
  aborts non-zero if any step failed. Version boundary: Rails **8.1.0+** (railties CHANGELOG,
  *"Introduce `bin/ci` for running your tests, style checks, and security audits…"*).
- **Verifying #391 found a second wrong claim one table row away.** `SKILL.md`'s stack table said
  `--skip-ci` omits `config/ci.rb` + `bin/ci`. It does not. `skip_ci?` guards only `create_cifiles`
  — `.github/workflows/ci.yml` and `.github/dependabot.yml` — while `config/ci.rb` is templated
  unconditionally by `config`, and `bin/ci` is never in `bin`'s exclude pattern (thruster, rubocop,
  brakeman, bundler-audit)
  ([`app_generator.rb`](https://github.com/rails/rails/blob/8-1-stable/railties/lib/rails/generators/rails/app/app_generator.rb));
  the flag's own `desc:` is *"Skip GitHub CI files"*
  ([`app_base.rb`](https://github.com/rails/rails/blob/8-1-stable/railties/lib/rails/generators/app_base.rb)).
  So a reader passing `--skip-ci` to avoid local CI still gets `bin/ci`, and one keeping it for local
  CI still gets the Actions workflow whose triggers `testing.md` §11 tells them to scope.
- **New `ci-gate-without-test-step` rule** in `lint_self_consistency.py`, closing the enforcement
  half of #391: a fenced `CI.run` block under `skills/` or `plugins/` must carry a `step` that runs
  the suite (`rspec`, or `rails test` for a Minitest project). It cannot catch the prose half —
  *"swap the test step"* is not mechanically checkable — but it pins the artifact, which is the half
  that lasts: the corrected `config/ci.rb` cannot be "simplified" back, and any future `CI.run` we
  ship must answer the same question. Narrow on purpose, and two near-miss fixtures decide that: a
  lone `step` line with no `CI.run` (how `api-documentation.md` shows the OpenAPI drift gate) and
  prose naming `CI.run` outside a fence both stay silent, as does the CHANGELOG quoting a superseded
  example. Two mutations registered, both caught.
- **SimpleCov's `add_group` → `group` rename landed in 1.0.0, not 1.0.2** (#396). `testing.md` §2
  stated the floor twice — an inline `# SimpleCov >= 1.0.2` beside the `group` call and *"renamed in
  1.0.2"* in the prose below — so a reader pins or gates two patch releases too high. The rename is
  in the **1.0.0** Deprecations section, alongside `add_filter` → `skip` and `track_files` → `cover`,
  with the legacy names kept working and each warning
  ([SimpleCov CHANGELOG](https://github.com/simplecov-ruby/simplecov/blob/main/CHANGELOG.md), fetched
  2026-08-01); 1.0.1, 1.0.2 and 1.0.3 mention none of them. The rest of the same paragraph was
  re-verified and left alone: the `StringFilter` path-segment change and the Ruby >= 3.2 minimum are
  both 1.0.0 and both stated correctly, and `SimpleCov.start`, `enable_coverage` and
  `minimum_coverage` were not renamed by the same redesign. Version boundary: `group` / `skip` /
  `cover` are **SimpleCov >= 1.0.0**.
- **`hotwire/references/stimulus.md` §3 invented function-key filters, and an unknown filter throws
  rather than no-oping** (#381). `defaultSchema.keyMappings` holds twelve named keys
  (`enter tab esc space up down left right home end page_up page_down`) plus `a`–`z` and `0`–`9`, and
  no `f*` entry at all — the doctrine's trailing `f1…` named a range that has never existed. The
  failure mode is why this was P1: `Action#shouldIgnoreKeyboardEvent` raises
  `contains unknown key filter` when the name is absent from the map, via an `error()` helper whose
  whole body is `throw new Error(message)`. Two adjacent facts verified in the
  same file and now stated: filters bind to `keydown`/`keyup`/`keypress` only (elsewhere the parser
  folds the dot back into the event name, which is how `jquery.custom.event->x#y` works), and
  `keyFilterDissatisfied` compares all four of meta/ctrl/alt/shift **exactly**, so `keydown.ctrl+k`
  stays silent while Shift is held. Verified against **Stimulus 3.2.2** — the version the skill
  targets and the latest release (published 2023-08-07; `keyMappings` is unchanged across 3.x) —
  [`src/core/schema.ts`](https://github.com/hotwired/stimulus/blob/v3.2.2/src/core/schema.ts),
  [`src/core/action.ts`](https://github.com/hotwired/stimulus/blob/v3.2.2/src/core/action.ts),
  [`src/core/action_descriptor.ts`](https://github.com/hotwired/stimulus/blob/v3.2.2/src/core/action_descriptor.ts).
  - **The report's account of where the error lands was wrong, and the correction is the sharper
    warning.** It said the error "surfaces through Stimulus' error handler". It does not:
    `shouldIgnoreKeyboardEvent` is reached from `Binding#willBeInvokedByEvent`, which sits *outside*
    the `try` in `invokeWithEvent`, and `EventListener#handleEvent` wraps nothing — so the throw
    escapes to the page as an uncaught error. Verified in
    [`src/core/binding.ts`](https://github.com/hotwired/stimulus/blob/v3.2.2/src/core/binding.ts)
    and [`src/core/event_listener.ts`](https://github.com/hotwired/stimulus/blob/v3.2.2/src/core/event_listener.ts).
    An issue body is a hypothesis, including one we wrote.
- **`hotwire/references/stimulus.md` §1 prescribed `stimulus:manifest:update`, the one command that
  destroys the auto-registration the same sentence promised** (#382) — a `doctrine-contradiction` in
  the `skills/code-review/SKILL.md` sense, not merely a stale fact. The importmap installer writes a
  four-line `index.js` calling `eagerLoadControllersFrom("controllers", application)` and appends
  `pin_all_from "app/javascript/controllers", under: "controllers"`, so a new controller needs **no
  command**; the rake task overwrites that file with explicit `application.register` lines, deleting
  the eager-load call and making the task permanently necessary. The old "if pins are stale" reason
  was wrong too — the task never touches pins. Verified against **stimulus-rails v1.3.4** (latest,
  published 2024-08-16, the version Rails 8 resolves) —
  [`index_for_importmap.js`](https://github.com/hotwired/stimulus-rails/blob/v1.3.4/lib/install/app/javascript/controllers/index_for_importmap.js),
  [`stimulus_with_importmap.rb`](https://github.com/hotwired/stimulus-rails/blob/v1.3.4/lib/install/stimulus_with_importmap.rb),
  [`stimulus_tasks.rake`](https://github.com/hotwired/stimulus-rails/blob/v1.3.4/lib/tasks/stimulus_tasks.rake).
  - **Verification found the old text wrong in a way the report missed, in the same clause.** "the
    generator `bin/rails g stimulus clipboard` handles it" inverts the truth: the generator's line is
    `rails_command "stimulus:manifest:update" unless Rails.root.join("config/importmap.rb").exist? || options[:skip_manifest]`
    — it *deliberately skips* the task on importmap and runs it only on the bundler path, where
    `index.js` genuinely is a generated manifest. The doctrine now names both paths instead of
    blurring them
    ([`stimulus_generator.rb`](https://github.com/hotwired/stimulus-rails/blob/v1.3.4/lib/generators/stimulus/stimulus_generator.rb)).
  - **Grepped for the class, per CLAUDE.md — no second instance.** The only other statement of this
    fact in the corpus, `rails-8/references/views-hotwire.md:131` ("pinned via `pin_all_from` and
    auto-registered"), is correct and corroborates the fix; the two shipped `keydown.esc` examples
    use a real filter; and every `data-action` written without `event->` in `skills/` sits on a
    `<button>`, which does have a default.
- **`hotwire/references/stimulus.md` §3's default-event map was four rules where the source has
  seven, and the omissions were the unguessable ones** (#387). `defaultEventNames` is
  `a`/`button` → `click`, `form` → `submit`, `details` → `toggle`, `input` → `input` *except*
  `input[type=submit]` → `click`, `select` → `change`, `textarea` → `input`. `details` matters most:
  §10 steers people to `<details>` as the no-JS disclosure element, and guessing `click` there yields
  a silently dead controller. Verified against **Stimulus 3.2.2** —
  [`src/core/action.ts`](https://github.com/hotwired/stimulus/blob/v3.2.2/src/core/action.ts).
  - **The report's failure mode was wrong in the safe-sounding direction.** It said an element with
    no default "turns into a thrown `missing event name`". It throws, but
    `ValueListObserver#parseToken` catches it into a `ParseResult.error` that **nothing in the
    codebase ever reads** — so the action is dropped with no binding and no console output. Written
    as reported, the doctrine would have promised a visible error where the real behaviour is
    silence, which is the harder bug. Verified in
    [`src/mutation-observers/value_list_observer.ts`](https://github.com/hotwired/stimulus/blob/v3.2.2/src/mutation-observers/value_list_observer.ts)
    (`grep -rn ParseResult src` → six hits, none reading `.error`).
- **`hotwire/references/native.md` documented a `RouteDecisionHandler` signature that 1.3.0 broke on
  both platforms** (#384). §4 told agents to implement `matches(location:…)` / `handle(location:…)`;
  since **iOS 1.3.0** and **Android 1.3.0** both functions receive the whole `VisitProposal`, so code
  written from the old paragraph does not compile. **Version boundary:** the documented shape is
  correct through **iOS ≤1.2.2 / Android ≤1.2.8** and wrong from 1.3.0 on both — §4 now states that
  inline, the way it already does for `recede_or_redirect_to` at ≥1.2.0. Verified against the release
  notes ([iOS 1.3.0](https://github.com/hotwired/hotwire-native-ios/releases/tag/1.3.0),
  [Android 1.3.0](https://github.com/hotwired/hotwire-native-android/releases/tag/1.3.0)) **and the
  tagged source**, because the notes give prose and this file ships signatures:
  `RouteDecisionHandler.swift` at `1.3.0` (`matches(proposal:configuration:)`,
  `handle(proposal:configuration:navigator: Navigating)`, read `proposal.url`) and
  `Router.kt` at `1.3.1` (`matches(proposal, configuration)`,
  `handle(proposal, configuration, activity: HotwireActivity)`, read `proposal.location`).
  Version facts bumped to **iOS 1.3.0 / Android 1.3.1** in `hotwire/SKILL.md` and `README.md`
  (releases dated 2026-07-07 and 2026-07-27; Android 1.2.6/1.2.7/1.2.8 had also shipped unrecorded).
- **Reading the same source refuted the two smaller claims in #384 and found a third error the report
  did not make.** (a) It asked to drop debug logging from "§2's Android knob list" — §2 is the *iOS*
  section, and `Hotwire.config.debugLoggingEnabled` **still exists on iOS at 1.3.0**
  (`HotwireConfig.swift:37`), so removing it would have introduced the error it meant to fix. The
  removal is Android-only, so the note went to §3 instead, where Android's config block previously
  listed no knobs at all: `Hotwire.config.logger` replaces it, with
  `logger.logLevel = HotwireLogLevel.DEBUG` for debug output. (b) The file said a custom handler is
  made by "subclassing" and that registration has "the same shape in Kotlin". Both are wrong at every
  version: it is a `protocol` (iOS) / nested `interface` (Android), and Kotlin's
  `Hotwire.registerRouteDecisionHandlers` is **`vararg`**, not the bracketed array iOS takes
  (`HotwireNavigation.kt`). Android's third `handle` parameter has also always been
  `activity: HotwireActivity`, never a navigator — the platforms were never the same shape.
- **Verifying #384 found §2's iOS setup block does not compile — and never did, at any version.**
  `private let navigator = Navigator()` calls an initializer that does not exist: `Navigator`'s only
  public initializer is `init(configuration:delegate:)`, and `Navigator.Configuration` requires both
  `name` and `startLocation` with no defaults (`Navigator.swift` / `Navigator+Configuration.swift`,
  identical at tags **1.2.2 and 1.3.0**). The block also called `navigator.route(rootURL)` where
  upstream calls `navigator.start()`. Now matches the official
  [iOS getting-started](https://native.hotwired.dev/ios/getting-started) verbatim in shape. This is
  the whole point of *"an issue body is a hypothesis"* cutting both ways: #384 reported a **1.3.0
  regression** in §4 and re-verified §2 as sound, but the first snippet an agent copies was broken
  independently of the version bump — a staleness audit is not a correctness audit.
- **§4's manual-navigation aside over-generalised `animated:`.** It said iOS `route`/`pop`/`clearAll`
  "each takes `animated: false`"; `route(_:options:parameters:)` has no `animated:` argument at
  1.2.2 or 1.3.0 — only `pop(animated: true)` and `clearAll(animated: false)` do, with the two
  differing defaults now stated.
- **Kamal's local registry is opt-in, not the default — `deployment-kamal.md` told agents to skip
  registry setup and broke the first deploy** (#389). §4 claimed Kamal 2.8 "by default … spins up a
  local registry" and that you can therefore "skip registry setup entirely"; `:72` marked the whole
  `registry:` block "optional since Kamal 2.8". All false. Kamal's default registry is Docker Hub —
  *"The default registry is Docker Hub, but you can change it using `registry/server`"* — and the
  local registry is opted into with a `server` that starts with `localhost`: *"If the registry server
  starts with `localhost`, Kamal will start a local Docker registry on that port and push the app
  image to it"*
  ([docs/configuration/docker-registry](https://kamal-deploy.org/docs/configuration/docker-registry/),
  generated from
  [`lib/kamal/configuration/docs/registry.yml`](https://github.com/basecamp/kamal/blob/main/lib/kamal/configuration/docs/registry.yml),
  fetched 2026-08-01). The opt-in test is
  [`Registry#local?`](https://github.com/basecamp/kamal/blob/v2.8.0/lib/kamal/configuration/registry.rb)
  — `server.to_s.match?("^localhost[:$]")` — and
  [`Validator::Registry`](https://github.com/basecamp/kamal/blob/v2.8.0/lib/kamal/configuration/validator/registry.rb)
  waives the mandatory `username`/`password` **only** for such a server.
  - **Reproduced, not reasoned about.** Against a real `kamal` 2.8.0 gem, the exact config the old
    §4 prescribed (no `registry:` block) fails before anything is built:
    `ERROR (Kamal::ConfigurationError): registry/username: is required`. The replacement config was
    run the same way and resolves `repository: localhost:5555/myapp`.
  - **What the issue got wrong, and it changed the fix.** #389 implied a fresh Rails 8.1 app hits
    the auth failure. It does not: Rails 8.1 *generates* `registry: server: localhost:5555`
    ([`deploy.yml.tt` at v8.1.0](https://github.com/rails/rails/blob/v8.1.0/railties/lib/rails/generators/rails/app/templates/config/deploy.yml.tt)).
    The failure path was **our own §2 annotated `deploy.yml`**, which still showed the pre-2.8
    Docker-Hub shape (`username`/`password`, no `server:`) under a comment calling it optional — an
    agent copying our example wrote a config needing credentials it was told it did not need. So the
    fix is a re-attribution (the *generator* opts in, not Kamal) plus repairing the §2-vs-§4
    contradiction, not a deletion of the section.
  - **Downstream claims resting on the same premise, all corrected**: the §2 image name
    (`your-user/myapp` is the remote-registry form; a bare name is right for the local one, and
    `repository` is `[server, image].compact.join("/")`); §3's `.kamal/secrets`, which presented
    `KAMAL_REGISTRY_PASSWORD` as the live default when 8.1 generates it commented out and a local
    registry authenticates nothing; the "Registry-free deploys (Kamal 2.8, new in 8.1)" heading and
    contents entry; and `rails-8/SKILL.md:162`, which carried the same "by default" wording.
  - Also corrected an over-claim inherited from the old text: the enumerated minimum omitted
    `builder.arch`, which is required and whose error surfaces only *after* the registry validates
    (observed in the same reproduction). §9's checklist gained a `registry:` row so the first-deploy
    gate can catch this class instead of prose promising it.
  - **Version boundary**: Kamal **2.8.0** (released 2025-10-19) added the local registry; before it
    there is no local registry at all. Rails **8.1.0** (2025-10-22) generates the opt-in. Rails does
    not pin Kamal (`gem "kamal", require: false`), and the behaviour is unchanged through the current
    2.12.0. Nothing here is Rails-version-dependent — it is a Kamal release, so the old "new in 8.1"
    framing was loose as well.
- **fidara-design: the Navigation family is documented — app header / navbar, sidebar / vertical, and
  Tabs** (Refs #95, the Phase-2 umbrella's *Navigation* group, which asks to add `vertical-navigation`
  and *"refine existing navbars/tabs/pagination/sidebar-nav"*). Three `documented` rows in
  `coverage.md` — *Navigation — header / navbar*, *Navigation — sidebar / vertical*, *Tabs* — rested
  on **eight lines** carrying no variant × size × state axis, no responsive rules, and one a11y
  attribute between them, while the matrix told agents to *"build it straight from that entry"*.
  Verified against [ARIA in HTML](https://www.w3.org/TR/html-aria/#el-nav),
  [HTML §4.3.4 `nav`](https://html.spec.whatwg.org/multipage/sections.html#the-nav-element),
  [APG Landmark Regions](https://www.w3.org/WAI/ARIA/apg/practices/landmark-regions/#aria_lh_step3),
  [ARIA 1.2 `aria-current`](https://www.w3.org/TR/wai-aria-1.2/#aria-current), and WCAG 2.2
  [2.4.5](https://www.w3.org/WAI/WCAG22/Understanding/multiple-ways) (AA),
  [2.4.11](https://www.w3.org/WAI/WCAG22/Understanding/focus-not-obscured-minimum) (AA, new in 2.2),
  [2.5.8](https://www.w3.org/WAI/WCAG22/Understanding/target-size-minimum) (AA),
  [3.2.3](https://www.w3.org/WAI/WCAG22/Understanding/consistent-navigation) (AA).
- **The landmark-naming rules are written once, not per row** — Breadcrumbs, Pagination, the rail and
  the bar all land on them. Three carry a boundary that is easy to overstate and is now stated at its
  real strength: unique labels for multiple `navigation` landmarks are an **APG "should", not a spec
  MUST**; *"If a landmark is only used once on the page it may not require a label"*; and identical
  repeated instances (pagination above and below one table) may **share** a label — which is exactly
  the shape the Pagination row already ships.
- **A Level A criterion had no mention anywhere in the design skill: WCAG 2.4.1 Bypass Blocks.** No
  skip link in `components.md`, `page-anatomies.md` or `component-implementations.md`, while
  `qa-flow`'s `a11y-auditor` already *reports* a `Skip Link` column — we audited for a thing we never
  told anyone to build. Now in the base-layout contract, with two corrections to the recipe everyone
  writes: (1) `tabindex="-1"` on `<main>` is load-bearing, because HTML's
  [scroll-to-the-fragment](https://html.spec.whatwg.org/multipage/browsing-the-web.html#scrolling-to-a-fragment)
  steps run the focusing steps *"with the Document's viewport as the fallback target"* and a plain
  `<main>` is not a focusable area, so the **viewport** takes focus — while
  [G1](https://www.w3.org/WAI/WCAG22/Techniques/general/G1) tests only the outcome and never names the
  attribute; and (2) `sr-only` + `focus-visible:not-sr-only` + `fixed`/`absolute` is a **coin flip**,
  because both set `position` and Tailwind resolves same-property collisions by generated-stylesheet
  order, not class order — *"you should just never add two conflicting classes to the same element"*
  ([Tailwind v4](https://tailwindcss.com/docs/styling-with-utility-classes#conflicting-utility-classes)).
  One `position` utility, `top` does the reveal.
- **Tabs: the shipped catalog row contradicted its own worked implementation, and the implementation
  was right.** The row prescribed `data-[state=active]:border-primary` while
  `component-implementations.md` used `aria-[selected=true]:border-primary` — and
  [APG](https://www.w3.org/WAI/ARIA/apg/patterns/tabs/) already requires `aria-selected`, so a second
  state source was never needed. Row corrected to the attribute the pattern mandates.
- **Tabs: four required wirings were missing from the worked markup** — no `id` on any tab, therefore
  no `aria-labelledby` on any panel (*"Each element with role tabpanel has the property
  aria-labelledby referring to its associated tab element"*, stated unconditionally), no accessible
  name on the `tablist`, and no `aria-orientation`. All four now emitted; the panel's
  `aria-labelledby` is called out because it is the one routinely dropped.
- **Tabs: three keyboard rows are marked `(Optional)` by APG and were being carried as required**;
  `Home`/`End` in `interaction-stimulus.md`'s contract table now say so. Two omissions filled from the
  same pattern: a **horizontal tablist must not listen for ↑/↓** (*"so those keys can provide their
  normal browser scrolling functions even when focus is inside the tab list"*), and `Shift + F10` /
  `aria-haspopup` exist only when a tab owns a popup menu. Checked for a phantom the #142 way — **no
  APG revision, current or the 2017 1.1 snapshot, contains `Ctrl+Delete`**, so it is not written down.
- **Three claims are OURS and say so, because the gate came back with no upstream** (design decisions
  under CLAUDE.md's *What the gate covers* carve-out, recorded on
  [#95](https://github.com/fmanimashaun/claude-skills/issues/95)): (1) **"tabs are not page
  navigation"** — the Tabs pattern has no "when not to use" section and APG nowhere warns against it,
  so the previous unattributed phrasing is now labelled as our position with our reasoning; (2)
  **marking only the deepest active nav item with `aria-current`** — ARIA's *"SHOULD only mark one
  element in a set"* governs peers and says nothing about an ancestor section and its child; (3)
  **manual activation when a tab panel is a lazy `<turbo-frame>`** — inferred from APG's own
  precondition (*"as long as their associated tab panels are displayed without noticeable latency.
  This typically requires tab panel content to be preloaded"*), which a lazy frame cannot meet.
- **`2.4.8 Location` is AAA and is now labelled AAA.** The "you are here" rail cue reads like an AA
  obligation and is not one; what is AA is that the active state must not be colour alone (1.4.1).
- **`rails-8/references/ecosystem-gems.md` §6 documented a pagy API that no longer exists** (#390).
  The snippet's `include Pagy::Backend` / `include Pagy::Frontend` and `pagy_nav(@pagy)` were
  removed wholesale in the version-43 redesign, with **no shims** — and since the skill wrote
  `gem "pagy"` unpinned, a downstream agent installed the current gem and got
  `NameError: uninitialized constant Pagy::Backend` on boot. On the golden path, too: line 33 marks
  pagy as the answer for *"any real list"*. Rewritten to `include Pagy::Method`,
  `pagy(:offset, collection, limit: 25)` and `@pagy.series_nav`, and the Gemfile line now pins
  `"~> 43.6"` so the doctrine says what it was checked against.
  **Version boundary is exact, not observational** — the audit left this INCONCLUSIVE because the
  43.0.0 changelog says only *"a complete redesign"*, but the gem's own git tree settles it without
  needing the prose. `gem/lib/pagy/backend.rb` and `gem/lib/pagy/frontend.rb` are **present in tag
  `9.4.0` and absent in tag `43.0.0`** (replaced by `toolbox/paginators/method.rb`), and pagy
  published **no stable release between the two**. So: **≤ 9.4.0 (2025-08-13) the old snippet is
  correct; ≥ 43.0.0 (2025-11-03) it raises.** Checked against **43.6.1** (2026-07-21). For the
  record, the removal actually landed in the prerelease `43.0.0.rc1` (2025-07-05), whose tree
  already has `method.rb` and neither of the two removed files.
  Citation: pagy's own search-and-replace table in
  [Upgrade to 43](https://ddnexus.github.io/pagy/guides/upgrade-guide/) — `include Pagy::Backend` →
  `include Pagy::Method`, `include Pagy::Frontend` → *"(remove: integrated)"*, `pagy_nav(@pagy, ...)`
  → `@pagy.series_nav(...)`; and the current API in
  [Quick Start](https://ddnexus.github.io/pagy/guides/quick-start) /
  [README](https://github.com/ddnexus/pagy/blob/master/README.md). Release dates from
  [the rubygems API](https://rubygems.org/api/v1/versions/pagy.json).
- **Two claims in #390 were wrong, and the fix does not carry them** (#142's lesson, again). The
  report said the paginator symbol is *"a required first argument"*; it is not —
  `Pagy::Method` defines `pagy` as `|paginator = :offset, collection, **options|`, so
  `pagy(collection)` still works. The skill therefore tells you to pass `:offset` **because the
  choice is worth seeing**, not because omitting it raises — a rule stated with a false reason is
  the next reader's bug. The report also dated 43.0.0 to *2025-07-05*, which is **before** the 9.4.0
  it calls the last 9.x — an ordering that cannot be true. That date belongs to the prerelease
  `43.0.0.rc1`; stable 43.0.0 is 2025-11-03. Neither error changes the verdict, which is why they
  are recorded rather than argued: the report was right that the API is gone and right about what
  replaced it.
- **Executing the new snippet caught a trap the linters structurally cannot.**
  `python3 scripts/lint_markdown_code.py` is `ruby -c` — it accepts anything syntactically valid, and
  a `NameError` is exactly the failure #390 is about. So the rewrite was **run** against a real
  install of pagy 43.6.1: the old two `include`s raise `NameError`, the new snippet paginates
  (page 2, limit 25, records 26–50 of 300), and `@pagy.limit_tag_js` — which the first draft listed
  as a plain helper — **raises `Pagy::OptionError` unless the `pagy` call passes `max_limit:`**. That
  caveat is now in the doctrine. Verified, not asserted.
- **NEW skill `quality-pass` — the review dimension `code-review` deliberately does not have**
  (#360). `code-review` hunts correctness and enforcement: `claims-vs-enforcement`,
  `gate-that-cannot-fail`, `doctrine-contradiction`. Nothing in it asks *is this duplicating
  something that already exists?* — so nothing did, through four files written in one week.
  **Change type: design/architecture decision, no upstream.** The four dimensions (reuse,
  simplification, efficiency, altitude) are borrowed from
  [`simplify` in fcakyon/claude-codex-settings](https://github.com/fcakyon/claude-codex-settings);
  the near-misses, the advisory rule and the measurement discipline are ours, and the authority is
  the decision recorded on [#360](https://github.com/fmanimashaun/claude-skills/issues/360).
  - **Every dimension carries a near-miss** — the case where the pattern is *correct* — because a
    quality pass that fires on legitimate code is a pass people stop reading. Duplication across an
    uncrossable distribution boundary; derivable state with a stated invalidation rule; a loop too
    small to hoist; a bandaid whose root cause is genuinely out of reach; *two cases is not a
    pattern*.
  - **Advisory, stated as a rule and not as a tone.** It never blocks a merge. A gate on taste gets
    switched off, and then nothing checks quality at all.
  - **Scoped away from bugs in both directions.** `code-review` gained a paragraph and a
    description clause pointing at it, so the two skills each say where the other starts and a
    quality finding that turns out to be a bug has a named way back.
  - **The worked example is the deliverable, not decoration.** `references/worked-example.md`
    records the pass's first real run against this repo's own toolchain, and the outcome was a
    decision **not to extract** — 29% of 1,189 lines matched textually, ~6% was mechanism a shared
    module could hold, and the one unit big enough to justify a module spans two independently
    installed plugins. Its counts are re-derived by `scripts/check_shared_shapes.py` rather than
    asserted.
- **`rails-8` named a vulnerable Rails as "current stable"** (#388). `SKILL.md` said **8.1.3**
  (2026-03-24); the current stable is **8.1.3.1** (2026-07-29), a **security** release fixing
  **CVE-2026-66066** / [GHSA-xr9x-r78c-5hrm](https://github.com/rails/rails/security/advisories/GHSA-xr9x-r78c-5hrm)
  — critical, CVSS v4 9.5, arbitrary file read and RCE in Active Storage variant processing. Every
  8.1 below 8.1.3.1 is affected (`>= 8.1.0.beta1, < 8.1.3.1`; backports 8.0.5.1 and 7.2.3.2), so the
  skill was pointing every new app at a known RCE while `auth-security.md:212` told the same agent to
  *"keep Rails patched … stay current"* — a rule its own version block made unsatisfiable.
  The block now carries the CVE, the pin, and **two things the report omitted that make the upgrade
  actually safe** — the fix needs **libvips >= 8.13** at runtime, and a possibly-exploited app must
  rotate `secret_key_base`. Support dates restated as absolutes (8.1 bug fixes to 2026-10-10,
  security to 2027-10-10; 8.0 bug-fix support ended 2026-05-07) and cited to the
  [end-of-support announcement](https://rubyonrails.org/2025/10/29/new-rails-releases-and-end-of-support-announcement),
  because `maintenance_policy.html` states only the *relative* rule and is where a reader would
  wrongly look. **Version boundary: Rails 8.1.3 → 8.1.3.1.** Verified against rubygems.org, the
  GitHub Security Advisory API and the [release post](https://rubyonrails.org/2026/7/29/Rails-Versions-7-2-3-2-8-0-5-1-and-8-1-3-1-have-been-released),
  2026-08-01.
- **The skill stated two different Ruby floors, and the lower one was end-of-life** (#394).
  `testing.md:87` claimed a "3.4+ floor" while `SKILL.md:64` and `controllers-routing.md:289` said
  `>= 3.2` — a `doctrine-contradiction`, and load-bearing, since §7's whole `parse.y` analysis exists
  *because* 3.2–3.3 is in scope. **External half (CONFIRMED):** `required_ruby_version = ">= 3.2.0"`
  in the `actionpack`/`activesupport`/`railties` gemspecs at tag `v8.1.3.1`; Ruby 3.2 is `eol` since
  **2026-04-01** and **Ruby 3.3 has been `security maintenance` since the same date** — the latter
  absent from the report, and it means the entire 3.2–3.3 band is out of normal maintenance
  ([ruby-lang.org/en/downloads/branches](https://www.ruby-lang.org/en/downloads/branches/)).
  **Design half — no upstream, so the authority is the maintainer decision recorded at
  [#394 (comment)](https://github.com/fmanimashaun/claude-skills/issues/394#issuecomment-5152697344)**,
  flagged there for sign-off before promotion: the skill's supported floor is **Ruby 3.4** — the
  oldest branch still in normal maintenance, so it is a re-checkable rule rather than a number that
  goes stale — while Rails' `>= 3.2.0` stays stated and is now explicitly labelled a *compatibility
  minimum, not a support statement*. All three sites now name which of the two numbers they mean, and
  §7 keeps its premise: Rails permits 3.2, so an existing app may sit below our floor, and
  `--parser=parse.y` rejects the form even on 3.4.7. **Version boundary: Rails 8.1.3.1 requires Ruby
  >= 3.2.0; this skill supports >= 3.4.**
- **The pin was stale in `README.md` too, which #388 did not mention** (#388, collateral —
  found by grepping every version site rather than only the two lines the report cited). Its
  Versioning section said "pinned to **Rails 8.1.3**" — the same claim, one directory up, where a user reads it
  before installing anything. A version fresh in the skill and stale in the README is worse than both
  being stale, so it moves with them; `SKILL.md`'s provenance line (Rails Guides `v8.1.3` → `v8.1.3.1`,
  both editions live) moves for the same reason. Also recorded in-line, in the skill, where a
  downstream agent will read it: **there is no Rails 8.2 or 9.0** — no gem, no tag, no `8-2-stable`
  branch — because a third-party post dated 2026-04-20 claims otherwise and keeps resurfacing.
- **Rails 8.1 stopped HTML-escaping `render json:`, and our security checklist never said so**
  (#393). `load_defaults 8.1` sets `config.action_controller.escape_json_responses = false`, so the
  JSON renderer no longer escapes `<`, `>`, `&`, U+2028 or U+2029. Rails' own changelog names the
  consequence — *"vulnerabilities when the resulting JSON is embedded in HTML"*
  ([actionpack/CHANGELOG.md @ 8-1-stable, under 8.1.0](https://github.com/rails/rails/blob/8-1-stable/actionpack/CHANGELOG.md);
  the flip itself is `railties/lib/rails/application/configuration.rb` `when "8.1"`, and
  [Configuring §3.1.1](https://guides.rubyonrails.org/configuring.html) lists it). Now in
  `auth-security.md` §4 **Injection & escaping** — the checklist a reader actually consults — with
  the per-response `escape: true`. **The JSONP carve-out is documented as partial, not absolute**,
  which neither the issue nor Rails' changelog sentence says: `renderers.rb:171` skips the flip when
  `:callback` is present, but `escape_js_separators_in_json = false` is global with no callback
  branch, so `json/encoding.rb:203-208` takes the `HTML_ENTITIES_REGEX` arm — `<`, `>`, `&` escaped,
  U+2028/9 **not**. **The issue's other remedy is a trap and is documented as one:** setting
  `config.action_controller.escape_json_responses = true` back is *"deprecated and will have no
  effect in Rails 8.2"* — the deprecation shipped in **v8.1.0 itself**
  (`renderers.rb:30-40`, `DeprecatedEscapeJsonResponses`), so doctrine points at `escape: true` and
  `json_escape` instead. *Version boundary:* Rails ≤ 8.0 or `load_defaults` ≤ 8.0 still escape.
- **`load_defaults 8.1` promotes path-relative redirects from `:log` to `:raise`, undocumented**
  (#392). `mattr_accessor :action_on_path_relative_redirect, default: :log`
  ([actionpack redirecting.rb:31 @ 8-1-stable](https://github.com/rails/rails/blob/8-1-stable/actionpack/lib/action_controller/metal/redirecting.rb)),
  set to `:raise` by the `when "8.1"` block. Verified the trigger against
  `_compute_redirect_to_location` rather than the issue's wording: it fires on a `String` starting
  with neither `/`, `?`, a scheme, nor `//`, and the payload is real — Rails' own docs give
  `redirect_to "@attacker.com"` → `http://yourdomain.com@attacker.com`, read by browsers as
  `userinfo@host`. Documented in `auth-security.md` §4 and `controllers-routing.md` §6 with the
  error class (`ActionController::Redirecting::PathRelativeRedirectError`) and all three modes.
  Also corrected the nit the same issue raised: 8.1 **added** `action_on_open_redirect`, it did not
  *"replace"* `raise_on_open_redirects`.
  [8-0-stable redirecting.rb](https://github.com/rails/rails/blob/8-0-stable/actionpack/lib/action_controller/metal/redirecting.rb)
  declares exactly one mattr, `raise_on_open_redirects` — so the new setting is an addition — and at
  8.1 the old one is still declared and still short-circuits (`redirecting.rb:262`,
  `return false if raise_on_open_redirects`). Verification then turned up a **second precedence rule
  nobody had reported, and it loses protection rather than adding it**: `actionpack railtie.rb:114-128`
  downgrades `action_on_open_redirect` to `:log` when an app *explicitly* carries
  `raise_on_open_redirects = false` forward, so an upgraded app can keep the old opt-out and silently
  stop raising on open redirects. Now a watch item in `project-setup.md` §7 and a sub-bullet in
  `auth-security.md` §4. *Version boundary:* `load_defaults` ≤ 8.0 keeps `:log`.
- **Both issues came from diffing `load_defaults 8.1` against our doctrine, so the diff was finished
  rather than sampled.** The `when "8.1"` block sets **seven** things; the two above were the two
  nobody had written down, but three more were undocumented and two documented claims were wrong.
  `project-setup.md` §7 now carries the complete seven-row table — old value, 8.1 value, and the
  observable change — because the 8.0 → 8.1 watch list is the one place a reader is entitled to
  assume completeness. Enumeration cross-checked two ways: the `when "8.1"` branch of
  `railties/lib/rails/application/configuration.rb` @ 8-1-stable, and the guides'
  ["Default Values for Target Version 8.1"](https://guides.rubyonrails.org/configuring.html), which
  agree exactly.
- **The three further gaps that diff found**, all now documented: `active_support.escape_js_separators_in_json`
  `true → false` (U+2028/9 unescaped **everywhere** `to_json` runs, views included — wider than the
  controller flip, and recorded with Rails' stated reasoning that ECMAScript 2019 legalised them in
  string literals); `action_view.remove_hidden_field_autocomplete` `false → true` (`autocomplete="off"`
  dropped from `form_tag`/`token_tag`/`method_tag` and the hidden params in `button_to`, `check_box`,
  `select` multiple, `file_field`, extended to the form builder's `hidden_field` in **8.1.1**);
  `action_view.render_tracker` `:regex → :ruby` (template dependencies parsed by prism/ripper instead
  of a regex, so fragment-cache digest trees can shift on upgrade — now in `performance-caching.md`
  §2, with the verified note that `<%# Template Dependency: … %>` still works, `ruby_tracker.rb`
  keeping the same `EXPLICIT_DEPENDENCY` scan).
- **And two claims we already shipped that the diff proved wrong.** `SKILL.md` and `project-setup.md`
  called order-dependent finders a **deprecation**; under `load_defaults 8.1`
  `raise_on_missing_required_finder_order_columns` is `true` and `.first`/`.last` on an unordered
  relation **raises `ActiveRecord::MissingRequiredOrderError`**
  ([activerecord/CHANGELOG.md @ 8-1-stable](https://github.com/rails/rails/blob/8-1-stable/activerecord/CHANGELOG.md)) —
  so the advice was right and the severity was understated. And `performance-caching.md` read as
  though 8.1 turned YJIT on; 7.2 did that (`config.yjit = true`), while **8.1 narrows it to
  `!Rails.env.local?`** — off in development and test. Both corrected.
- **`hotwire/references/turbo.md` §2 documented `data-turbo-disable-submitter`, an attribute Turbo
  has never had** (#380) — and it sat inside the fenced Drive cheat sheet, so an agent wrote a no-op
  onto a user's form and believed it had configured something. Grepping `src/` of the shipped tag
  returns zero matches and the official reference does not list it. The behaviour the comment
  described is real and *is* the default, but it is **global config, not markup**:
  `Turbo.config.forms.submitter` takes `"disabled"` (sets `submitter.disabled` for the submit,
  clears it after) or `"aria-disabled"` (sets the attribute and cancels clicks, so the button stays
  focusable) —
  [`src/core/config/forms.js`](https://github.com/hotwired/turbo/blob/v8.0.23/src/core/config/forms.js).
  The block line is replaced by `data-turbo-submits-with`, the per-element knob that does exist
  ([`form_submission.js` L183–215](https://github.com/hotwired/turbo/blob/v8.0.23/src/core/drive/form_submission.js),
  [attributes reference](https://turbo.hotwired.dev/reference/attributes)). **Version boundary:**
  verified against **Turbo 8.0.23**, the version `hotwire/SKILL.md` targets; the attribute exists in
  no Turbo 8 release.
- **`turbo.md` §2 described `data-turbo-track="dynamic"` as updating the element in place without a
  reload** (#383) — it *removes* the element, and both halves of the sentence were wrong: the
  mechanism (remove, not update) and the trigger (absent from the new `<head>`, not "the fingerprint
  changed"). `unusedDynamicStylesheetElements` filters the current head's stylesheets that the new
  head lacks, and `removeUnusedDynamicStylesheetElements()` deletes them
  ([`page_renderer.js` L86, L119–122, L197–205](https://github.com/hotwired/turbo/blob/v8.0.23/src/core/drive/page_renderer.js));
  the official reference says the same in one line. It exists because Turbo's head merge is additive,
  so page-specific CSS otherwise piles up forever. Two precisions the issue did not carry, both from
  source: `"dynamic"` appears **once** in the whole tree, on that stylesheet filter, so it applies to
  `<style>` / `<link rel="stylesheet">` and nothing else despite the reference's generic wording; and
  the `reload` half of the sentence was correct and is unchanged. **Version boundary:** verified
  against **Turbo 8.0.23**; behaviour unchanged across Turbo 8.
- **`turbo.md` §5 scoped stream id-de-duplication to `append`/`prepend`** (#385) — since **Turbo
  8.0.21** all four insertion actions de-duplicate, so the reference told agents an element-removal
  would not happen when it does. `before`/`after` call `removeDuplicateTargetSiblings()`
  ([`stream_actions.js`](https://github.com/hotwired/turbo/blob/v8.0.23/src/core/streams/stream_actions.js),
  [`stream_element.js` L78–93](https://github.com/hotwired/turbo/blob/v8.0.23/src/elements/stream_element.js));
  added by [hotwired/turbo#1290](https://github.com/hotwired/turbo/pull/1290), shipped in
  [v8.0.21](https://github.com/hotwired/turbo/releases/tag/v8.0.21). **Version boundary confirmed by
  reading both tags**: `removeDuplicateTargetSiblings` is absent at v8.0.20 and present at v8.0.21 —
  doctrine was correct for ≤ 8.0.20 and wrong from 8.0.21, the dangerous shape where a claim stays
  true-looking inside one major version. The section is retitled to cover all four and states the
  scope difference: `append`/`prepend` scan the target's **direct children**, `before`/`after` scan
  the target's **siblings**, which is its parent's children *including the target itself*. That last
  clause is not pedantry — a `before`/`after` whose template carries the target's own `id` removes
  the target, loses the insertion point (`e.parentElement?.insertBefore`, and `targetElements`
  re-queries by id) and **inserts nothing, silently**. Reproduced against a real DOM, not inferred.
- **`turbo.md`'s §4, §5 and §8 lookup tables omitted real Turbo 8 API** (#386) — agents read absence
  from a table as "no such thing". Added: `data-turbo-frame="_parent"`, which navigates the
  *immediate* enclosing frame via `parentElement.closest("turbo-frame")` and falls back to a full page
  visit when there is no enclosing frame or it is `disabled`
  ([`frame_controller.js` L482–511 and L585–594](https://github.com/hotwired/turbo/blob/v8.0.23/src/core/frames/frame_controller.js),
  behaviour pinned by five functional tests; **Turbo ≥ 8.0.21**,
  [hotwired/turbo#1446](https://github.com/hotwired/turbo/pull/1446));
  the `refresh` action's `method` / `scroll`, which override the page's meta tags for that one
  refresh (`page_view.js` L19, L63; **Turbo ≥ 8.0.21**,
  [hotwired/turbo#1208](https://github.com/hotwired/turbo/pull/1208));
  and `turbo:before-prefetch`, `turbo:frame-render` and `turbo:before-frame-morph`. Enumerating every
  `turbo:*` dispatch in v8.0.23 gives **24** events against §8's 21 — exactly those three, so the
  issue's list was complete. Two things it got only half right, corrected here: its enumeration
  missed `src/http/`, which is where `turbo:fetch-request-error` is dispatched (§8 already listed it,
  so nothing was wrong — but the method would not have caught it); and `turbo:before-frame-morph` is
  dispatched **without** `cancelable`, unlike the element and attribute morph hooks beside it, so the
  reference now says so. §5's `refresh` row also loses its "(morphing — §3)" gloss: the action honours
  whatever is configured, and the meta-tag default is `replace`. **Version boundary:** `_parent` and
  the refresh attributes are absent at v8.0.20 and present at v8.0.21 (both tags read); the three
  events predate 8.0.21 and had simply never been listed.
- **FIX — `coverage.md`'s Interaction-patterns table had outlived the work it tracked, in four of
  its nine rows** (#89). The component half of that matrix has been evidence-checked since #124;
  this half was hand-maintained prose, and it rotted quietly while the phases under this epic
  shipped. **Change type: a correction of factual claims about our own repo, measured against our
  own files — no framework claim, so no `doctrine-verifier` verdict is in scope.** Each status is
  now derived from a probe string that must occur in the shipped reference docs (below).
  - `disclosure (collapse / accordion)` read **`planned #142`**, with the note *"we shipped no
    controller at all"*. `interaction-stimulus.md` §*Disclosure — the full contract (#142)* has
    shipped the full two-mode contract since v1.35.0, `components.md` §*Disclosure / Accordion*
    names `Ui::Disclosure` / `Ui::Accordion`, and the matrix's **own** Accordion row already said
    `documented`. So the file contradicted itself about the pattern it calls the second most common
    on the web.
  - `drag and drop (upload)` read **`planned #95`, "keyboard path is mandatory"** — which is not
    merely stale but the **inverse** of the doctrine it summarised. `forms.md` §*File upload /
    Dropzone* quotes Understanding WCAG 2.5.7 saying *"achieving keyboard equivalence for a dragging
    operation does not automatically meet this success criterion, unless that equivalent keyboard
    operation also provides controls that can be clicked or tapped with a pointer"* — the visible,
    clickable native input is what satisfies it. An agent reading only the matrix would have built
    the 2.5.7 failure the reference doc exists to prevent.
  - `filter / typeahead` read `planned #95`. Both consumers shipped; the note now states the
    distinction #229 established — filtering is `aria-autocomplete` on an **editable** combobox,
    typeahead-jump belongs to the **select-only** one, and conflating them swallows the space bar.
  - `carousel / slide` read **`declined`** while `components.md` §*Carousel* prescribes the
    `carousel` controller by name and the `documented` Lightbox row composes it. `declined` in a
    status column reads as *the mechanism does not exist*; the doctrine position ("the default
    answer is still no") now lives in the note, where it was always meant to be.
- **FIX — `Category filters` told agents to build a workaround that had been superseded** (#89).
  Its **Build from** cell said *"`<details>`/`<summary>` groups inside a `stack`, until #142
  lands"*. #142 landed. The existing guard catches exactly this text — but only on `documented`
  rows, and this row is `derivable`, so nothing was watching. Now points at `Ui::Disclosure`, with
  `<details>` kept as the cheap option for groups that never animate, per `components.md`.
- **`fidara-design/references/coverage.md` was unreachable from its own `SKILL.md`** (#158) — 230
  lines of component doctrine (every component's guidance state, what to build it from, and which
  surface it belongs on) reachable only via `brand.md` and `marketing-copy.md`. That is depth two,
  which the official guidance names as the case that degrades: *"Keep references one level deep from
  SKILL.md. All reference files should link directly from SKILL.md to ensure Claude reads complete
  files when needed"* / *"Claude may partially read files when they're referenced from other
  referenced files ... resulting in incomplete information"*
  ([agent-skills/best-practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices),
  fetched 2026-08-01). So an agent building an uncatalogued component could consult the design system
  and never see the matrix that says what to build it from. Now routed from the **Concrete code**
  block, and held there by the new `skill routing` gate rather than by review.
- The other three shipped skills were already clean: 42 reference files across four skills, all
  routed one level deep, every `SKILL.md` well inside the 500-line Level-2 budget (largest is
  rails-8, 227 lines when this was measured and 240 after the 8.1 defaults work below).
  Verified by running the gate, not by reading.
- **The purchase flow is documented, and the checkout exception is now stated rather than implied**
  (Refs #91 — the commerce family, shipped in slices; this is the purchase/checkout slice).
  `crud-modal-pattern.md` said flatly *"treat full-page CRUD forms as a defect"* while
  `page-anatomies.md` already shipped a full-page Checkout: two shipped rules contradicting each
  other, which is the `doctrine-contradiction` class our own `code-review` skill names. The
  exception is now named, scoped to four conditions that are properties of the Modal component
  (dismiss affordances over a financial commitment, the page behind being the thing abandoned, the
  focus trap vs a provider iframe, one address for a multi-step flow), and explicitly non-general.
  **Architecture decision, not a framework claim** — the authority is the maintainer's own wording
  in [#91](https://github.com/fmanimashaun/claude-skills/issues/91) (*"checkout is the one legitimate
  multi-step, full-page flow … state it explicitly so agents don't force it into a modal"*), linked
  where a citation would go. New `Checkout — the purchase flow` anatomy, new `Payment / card entry`
  and `Promo / discount code` catalog entries, worked recipes for both.
  - **The PCI framing in scope changed on 2025-03-31, and the intuitive version is the wrong one.**
    PCI DSS v4.0.1's January 2025 SAQ A **removed** Requirements 6.4.3 and 11.6.1 (and 12.3.1) as SAQ
    A line items and replaced them with an eligibility criterion — *"the merchant has confirmed that
    their site is not susceptible to attacks from scripts that could affect the merchant's e-commerce
    system(s)"* — which per PCI SSC **FAQ 1588** applies **only** to merchants embedding the
    provider's payment form in iframe(s) and *"does not apply to … a webpage that redirects
    customers"*. Writing "your iframe checkout must satisfy 6.4.3 and 11.6.1 under SAQ A" would have
    been #142's shape exactly: traceable to a real source, wrong today. Sources: PCI SSC blog,
    [SAQ A updates](https://blog.pcisecuritystandards.org/important-updates-announced-for-merchants-validating-to-self-assessment-questionnaire-a)
    and [FAQ 1588](https://blog.pcisecuritystandards.org/faq-clarifies-new-saq-a-eligibility-criteria-for-e-commerce-merchants).
    Version boundary: PCI DSS **v4.0.1**, SAQ A January 2025 revision, effective **31 March 2025**.
  - **Cited, with the version each claim is true at.** WCAG 2.2 —
    [3.3.7 Redundant Entry (**A**)](https://www.w3.org/WAI/WCAG22/Understanding/redundant-entry.html),
    whose Understanding doc's own example is the billing/delivery address checkbox;
    [3.3.4 Error Prevention (Legal, Financial, Data) (**AA**)](https://www.w3.org/TR/WCAG22/#error-prevention-legal-financial-data),
    which the review step answers via *Confirmed*;
    [2.2.1 Timing Adjustable (**A**)](https://www.w3.org/TR/WCAG22/#timing-adjustable) for a cart
    hold, with a note not to stretch its Real-time Exception (an auction) to a reservation timer;
    [1.3.5 Identify Input Purpose (**AA**)](https://www.w3.org/WAI/WCAG22/Understanding/identify-input-purpose.html)
    plus [H98](https://www.w3.org/WAI/WCAG22/Techniques/html/H98)'s scope limit (*"only place
    requirements on input fields collecting information about the user"*).
    WHATWG HTML — the `cc-*` autofill names, the fixed token order (`section-*` → `shipping`/`billing`
    → `home`/`work`/… → field name), and the `type=number` note that names **credit card numbers and
    US postal codes** as inappropriate. Turbo **8.0.23** — the submitter is auto-disabled for the
    duration of a submission, `data-turbo-submits-with` supplies the in-flight label,
    `data-turbo="false"` opts a provider redirect out, and a submission expects **303** / **422**.
    Tailwind **v4** — `tabular-nums`.
  - **Two claims in the issue body were verified false and are not implemented** (#142's rule, again).
    It required money at *"`decimal(15,2)` per the rails-8 doctrine"*: rails-8's actual money doctrine
    is `ecosystem-gems.md` — *"store integer minor units (`price_cents`) always"* — and the string
    `decimal(15,2)` appears nowhere in this repo (`models.md` shows `decimal{10,2}` for a generic
    price). Writing it would have put a storage rule into a **design** skill that contradicts our own
    **framework** skill. It also required money in `font-mono`, which `brand.md` scopes to *reference
    numbers, SLA timers, code, timestamps*. Doctrine now says money is `tabular-nums`, an order
    reference is `font-mono`, and storage is rails-8's call — the discrepancy is flagged on the issue
    rather than decided silently.
  - **`Ui::AddressFieldsComponent` was referenced by the Checkout anatomy with no `autocomplete`
    tokens at all** — a 1.3.5 gap in shipped doctrine, multiplied by every screen that renders an
    address. It now takes `mode: :shipping | :billing | :none` and emits `billing postal-code`-shaped
    tokens in the spec's required order. Its call site is updated with it.
  - **APG has no pattern for a wizard, a checkout or a coupon field** — re-confirmed against the
    current index, so the multi-step shape reuses the existing `Stepper / wizard` contract (already
    ours, from #95) instead of a second mechanism, and the promo-code shape is decided as ours. The
    two HTML-spec rules that settle it: a `<form>`'s content model is *"Flow content, but with no
    `form` element descendants"*, and *"a form element's default button is the first submit button in
    tree order"* — so the code entry is a **sibling** form, never nested and never the checkout
    form's default button.

### 1.29.1 — 2026-08-01

- **`Ui::Logo`'s `size:` raised `NoMethodError` on every input except a SIZE key or a numeric
  string** (#352). `@px = (SIZE[size.to_sym] || size.to_i).clamp(20, 200)` contradicts itself on one
  line: the `|| size.to_i` fallback and the clamp both say a px number may arrive — and `brand.md`
  states a *"prism 20px digital"* minimum, which only means anything if one can — but
  `Integer#to_sym` does not exist, so `size: 48` raised before reaching the branch written for it.
  Now branches on the type. **Design decision, not a framework claim:** an out-of-range value keeps
  clamping silently rather than raising, consistent with the `8 → 20` / `999 → 200` behaviour already
  in the expression. Verified in Ruby across eight inputs; the pre-fix expression raises on three.
- **Measuring #352 found a second raise the report missed, in the same expression.** `Symbol#to_i`
  does not exist either, so *any* key absent from `SIZE` — `size: :xl` — raised as well. The
  fallback only ever worked for the one input nobody writes, a numeric string. Hence `to_s.to_i`.
- **New `unreachable-coercion-fallback` rule** in `lint_self_consistency.py` — `X.to_sym` guarding a
  `X.to_i`/`to_f` fallback on the same identifier, across `skills/` and `plugins/` markdown. This is
  the class `lint_markdown_code.py` **structurally cannot** catch: `ruby -c` accepts it, because it
  is valid syntax that raises at run time. Backreferenced, so different identifiers (the normal
  shape) stay silent, and comments are skipped — the doctrine explaining the bug has to quote it.
  Selftest 77 → 85 assertions; mutations 21 → 23, both new ones caught by their own fixture.
- **Two claims in #352 were false, and are recorded because the pattern repeats** (#142). It quoted
  supporting doctrine — *"`:sm`/`:md`/`:lg` from SIZE, **or an integer px**"* — that appears nowhere
  in the skill: the word "integer" is absent from `fidara-design` entirely. It also placed a mirror
  of the component in `reference-implementation.md`, which contains no Logo. The defect was real,
  but on **internal** evidence (the dead fallback, the clamp, `brand.md`'s px minimum), not on the
  authority the report claimed. An issue body is a hypothesis.

### 1.29.0 — 2026-08-01

- **`stock-phrase`: the LLM house style is now named in the copy doctrine, as an advisory count.**
  Borrowed from the `humanize` plugin in `fcakyon/claude-codex-settings`, which blocks ~53 stock
  words. Useful to us for a specific reason: **`/design-flow:component` drafts marketing copy**, so
  that vocabulary is a risk *we create*.
  - **Advisory, not a failure, unlike every other row in that table.** The others fail on a fact;
    this one fails on a *word*, and a word has legitimate uses — `unlock` is a real CTA
    (*"Unlock your first report"*), `harness` is an ordinary noun. One is a word choice; six in a
    landing page is a draft nobody edited, and §1 already says copy is the human's decision.
  - **One caution recorded about the evidence, because it is easy to over-read.** Scanning *this
    repo's own skills* finds seven hits — `harness` (the #105 capture harness), `elevate` (CSS
    elevation), `unlock` (a scroll lock) — all legitimate. That proves the list must never run over
    documentation. It says much less about a user's hero headline, which is the actual target and
    where nobody has measured the rate. The honest response to an unmeasured false-positive rate is
    to report rather than block.
- **FIX — the doctrine's scope note claimed a gap that had since been closed.** It said the checks
  were a specification and that wiring them into `design-auditor` and `/design-flow:component` was
  "not changed by the PR that adds this file". Both landed a release later. A doctrine file claiming
  enforcement it lacks is `gate-that-cannot-fail`; one still claiming a gap that has been closed is
  the same error pointing the other way.

### 1.28.1 — 2026-08-01

- **FIX — five catalog entries carried no accessibility contract, and two contradicted our own rule**
  (#95). Found doing Phase 2's audit criterion by **measuring** the catalog rather than reading it:
  every `## ` section scored for variant / size / a11y / responsive content.
  - **The over-broad reading was rejected first.** 34 of 36 sections "failed" that scan, because a
    Divider has no variants and a Breadcrumb has no sizes — requiring those axes universally would be
    the false-positive machine this repo keeps refusing to ship. **No gate was added.** a11y was the
    one dimension near-universal enough for the misses to be real, and there were exactly five.
  - **Two of the five contradicted `design-auditor`'s own checklist**, which mandates *no colour-only
    state*: Pagination's active page was `bg-primary/10 text-primary` and nothing else, and Avatar's
    status dot was a bare coloured dot. Both now carry a text equivalent — `aria-current="page"` and
    `sr-only` status text — so the colour is the visual half rather than the whole signal.
  - The other three: **Table (CRUD)** had no `<caption>`/`<th scope>` rule, so a cell could not be
    associated with its header; **Media object** had no `alt` guidance, where the right default is
    `alt=""` because a thumbnail beside a name announces it twice; **Empty state** had no rule that
    its icon is `aria-hidden`, that its title is a real heading at the implied level, and that a
    filtered-into-empty region must be `aria-live` or the user filters into silence.
  - `Forms` is a one-line pointer to `forms.md` and is deliberately left alone — its contracts live
    there and duplicating them is the mechanism the catalog forbids.

### 1.28.0 — 2026-08-01

- **A per-page motion cap, which was #136's one genuinely missing rule** (#136). `motion.md` §7
  capped a single *stagger*; nothing capped the **page** — the limit that actually gets exceeded,
  because each section is added by someone who only saw their own section. Now: one entrance pattern
  per page, at most three animated regions, never two running at once in the viewport, and never on
  content the reader scrolled to *on purpose*. The arithmetic follows §7 — three regions at the 1.6s
  ceiling is 4.8s of page assembly if they queue, which is why they may not run together rather than
  merely being capped in number. **Ours, not upstream**: no spec bounds animation count, so it is
  recorded as a decision rather than left to taste, and `design-auditor` counts it.

### 1.27.0 — 2026-08-01

- **Input group documented as a Text-input variant, not a new component** (#95, Phase 2). The last
  named Phase-2 family with no contract. **Change type: architecture decision**, recorded here
  because there is no upstream: APG has no input-group pattern.
  - **It is not a missing component.** The Tailwind UI `forms/input-groups` corpus directory was
    already claimed by the `Text input` row, and `forms.md` already mentioned prefix/suffix twice —
    what was missing was the **contract**, not the row. Giving addons their own component would have
    been the *duplicate mechanism* Phase 2's own criteria forbid. The `Text input` matrix note now
    states the claim explicitly so the next reader does not re-litigate it.
  - Four rules, each with a reason: the **focus ring moves to the wrapper** (`focus-within`), because
    a ring around half a field is worse than none; a **decorative addon is `aria-hidden`**, or
    *"Amount"* is announced as *"Amount pound"*; an **interactive addon is not an addon** but a
    cluster of two focusable things, each needing its own name and touch target; and `f.input_field`
    rather than hand-rolled anatomy, which is the composed-cluster row of the existing table.

- **FIX — two role-token pairs failed WCAG 1.4.3, and only one of them was reported** (#304).
  **Change type: incorrect doctrine.** Internally measurable, so it is settled by arithmetic against
  our own tokens; the calculator is validated against the two standard controls (`#767676`/white =
  4.54, white/black = 21.00) before any figure is trusted.
  - **Reported:** light `--primary` on `--background` was **4.42:1**, under 4.5:1. `--primary` now
    points at a new `--color-fm-cerulean-700` (`#0072C4`) → **4.74:1**. The brand hex `#0077CC` is
    **unchanged**, because the Prism mark, `chart-1` and `brand.md` all carry it and **a logo is not
    text** — 1.4.3 does not apply to it. Fixing an accessibility defect by editing a brand asset
    would have been the wrong lever.
  - **Not reported, and worse:** the `.dark` block overrode `--primary` to electric but **not**
    `--primary-foreground`, which therefore inherited `#FFFFFF` from `:root`. White on `#00A3FF` is
    **2.73:1** — that is the label on **every primary button in dark mode**, solid-background text
    rather than a near-miss link colour. Now `var(--color-fm-navy)` → **6.30:1**.
  - **The second one is the argument for the new script.** The first was found by a person reading a
    table; the second was invisible until something enumerated the pairs mechanically. A token file
    is exactly where a reader checks the pair they are thinking about and no others.
  - **NEW `scripts/check_token_contrast.py`** — parses the token file (palette, `:root`, and `.dark`
    *inheriting* from `:root`, which is the mechanism behind the second defect) and measures **ten**
    role-token text pairs. Two gates added. Both regressions proven caught with their exact ratios.
    A missing or renamed token **raises** rather than resolving to something arbitrary, so a pair
    that stops being measured can never read as a pair that passed.
  - Two defects in the checker itself, caught before it shipped: it skipped the `@theme` palette, so
    every role referencing it was unresolvable — it *reported* that rather than passing, but a parser
    reading half the file can still miss a pair; and an emptiness check ended up **after** the merge
    that made it unreachable, a gate that cannot fail.
  - `components.md`'s contrast table restated these numbers in prose and was stale the moment the
    tokens moved. Corrected, and it now points at the command that re-derives it.

### 1.26.0 — 2026-08-01

- **FIX — chrome used the content type step in eleven places, not the six reported** (#306).
  **Change type: incorrect doctrine**, and internal rather than external: two of our own files
  disagreed, so it is settled by measurement against the repo, not by a citation.
  - `foundations-tokens.md` is emphatic that app chrome is **`text-step--1`** and calls `text-step-0`
    on chrome *"the most common calibration error, and the reason this table exists"*. The
    calibration was **measured**, not chosen — 14px chrome beats 16px body ~2.7:1 in both reference
    corpora. It had then drifted inside the reference implementations, which is the file agents copy
    from, so the error was **propagating** rather than sitting still.
  - **The issue named six sites; grepping the pattern found eleven.** The five it missed are the ones
    that travel furthest: the button `BASE` in **two** files (buttons are named chrome), the
    form-input base in a **second** file, and a `<table>` in **two** files (table cells are named
    chrome). This is the `code-review` rule — when you find one instance, grep for the class — paying
    for itself again.
  - The sharpest evidence was internal: `component-implementations.md` had a `:label` at
    `text-step--1` **immediately above** its `:input` at `text-step-0`. Two lines apart.
  - **Where `text-step-0` stays is now recorded**, because the failure mode of a rule like this is
    over-correction on the next pass: alert body, card description, page lede, `<dd>` values (whose
    `<dt>` is chrome), and `AvatarComponent`'s deliberate `sm`/`md`/`lg` ramp. Audited one by one.
  - **No static lint rule shipped, deliberately.** Chrome and content are only reliably
    distinguishable in a *rendered* DOM; a grep would have to guess from class strings and its false
    positives would land on exactly the legitimate uses above — which is how a linter gets switched
    off. It belongs in design-flow's browser-driven `rendered_conformance.py`, which resolves real
    elements, and is named there as the home for a `chrome-type-step` rule.

- **FIX (P1) — the focus ring was invisible in forced-colors mode, in nine shipped recipes** (#305).
  **Change type: incorrect doctrine.** Verdict CONFIRMED against two upstreams, both quoted.
  - Every recipe read `focus-visible:outline-none focus-visible:ring-2 …`. Under **Tailwind v4**,
    which this kit mandates, that is *"`outline-style: none`"* plus a ring that is a **box-shadow** —
    and *"`box-shadow` and `text-shadow` compute to `none`"* in forced-colors mode
    ([CSS Color Adjust 1](https://www.w3.org/TR/css-color-adjust-1/)), while `outline-color` is
    merely force-adjusted to a system colour. So the outline is the half that survives and we had
    switched it off: **no visible focus indicator at all**, a WCAG **2.4.7** failure.
  - **The mechanism is a rename that kept the old spelling and inverted its meaning.** Tailwind v3's
    `outline-none` *"didn't actually set `outline-style: none`, and instead set an invisible outline
    that would still show up in forced colors mode **for accessibility reasons**"*; v4 renamed that
    safe utility to **`outline-hidden`** and gave the old name to one that really removes the outline
    ([v4 upgrade guide](https://tailwindcss.com/docs/upgrade-guide)). Our strings were **correct
    under v3** and were carried through the migration untouched — which is why nothing looked wrong
    and why no amount of reading the diff would have caught it.
  - Fixed in all nine sites across four files, with the reasoning recorded in `components.md` so the
    next migration has the *why* and not just the string.
  - **Enforced, not just written down.** New `v4-outline-none` rule in `lint_self_consistency.py`,
    because a prose rule about a string is precisely what regressed here. Five fixtures including the
    two that decide whether it survives: doctrine **prose** naming the bad utility must stay silent
    (`components.md` names it five times on purpose), and `outline-hidden` must not trip it. Proven
    to fail on purpose by reverting one site, and guarded by a declared mutation. Self-consistency
    assertions 65 → **70**; `lint_self_consistency` mutations 18 → **19**, all caught.

### 1.25.0 — 2026-07-31

- **Inline link is documented, and `coverage.md` reaches ZERO `needs doctrine` rows** (#95). **1 → 0.**
  Every row in the matrix is now `documented` or `derivable`; no component in either corpus requires an
  agent to invent an a11y contract. This row had a **real APG pattern** — rare in this file — and two
  findings that came from measuring rather than reading.
  - **The 3:1 link figure is a *technique*, not the criterion.** SC 1.4.1 Use of Color (**A**) says only
    *"Color is not used as the only visual means of conveying information…"* — **no ratio, no mention of
    links.** The 3:1 lives in **G183, a Sufficient Technique**. Doctrine says "G183 recommends", never
    "WCAG requires 3:1". And **G183's own test names hover only** (*"Check that hovering over the link
    causes a visual enhancement"*) — focus is the separate obligation 2.4.7, which G183 cites only by
    analogy.
  - **APG's Link pattern says less than it is usually quoted for.** Its keyboard table is exactly two
    rows — *"Enter: Executes the link…"* and *"Shift + F10 (Optional)"*. It says **nothing about `Space`
    and nothing about an `<a>` without `href`.* The familiar "Enter activates, Space does not" is real
    browser behaviour but is **not in the pattern**, so the entry does not cite APG for it. It does carry
    APG's actual instruction: *"Authors are strongly encouraged to use a native host language link
    element, such as an HTML `<A>` element with an `href` attribute."*
  - **Measured against our own tokens, and the numbers decided the rule** (CLAUDE.md: *measure anything
    measurable*). Light `--primary` `#0077CC` is **3.93:1** against body text — clears G183. Dark
    `--primary` `#00A3FF` is **2.59:1** — **under 3:1, so in dark mode colour cannot be the
    distinguisher at all.** An underline at rest is therefore **mandatory, not stylistic**, and since it
    is required in dark it is used in both: one link recipe, not two. The calculator was validated
    against the standard controls (`#767676`/`#FFFFFF` = 4.54:1, `#000000`/`#FFFFFF` = 21:1) before any
    figure was trusted.
  - **This retires the row's own previous guidance.** It said to use the Button `link` variant's classes
    — but that variant is `text-primary underline-offset-4 hover:underline`, **no underline at rest**,
    i.e. precisely the colour-only-plus-hover shape that dark mode's 2.59:1 cannot support. The Button
    entry gains a one-line scope note pointing at the new one; the variant is still right for a *button*
    that looks like a link.
  - **2.5.8 Target Size (Minimum) (AA) does NOT apply to a link in a sentence** — its **Inline**
    exception, with the Understanding doc's worked example being this exact case: *"Links within
    paragraphs of text do not need to meet the 24 by 24 CSS pixels requirements."* Worth stating, because
    padding an inline link to 24 px wrecks the line rhythm to satisfy a criterion that exempts it.
  - **Three level corrections carried into the entry**: 2.4.4 is **A** and 2.4.9 is **AAA** (the *"click
    here"* failure **F84** is filed under the AAA one, so it is wrong to say it "fails AA"); **2.4.13
    Focus Appearance is AAA**, not AA, so its 2 px/3:1 rule is a target and not an obligation; 2.4.11
    Focus Not Obscured (Minimum) is **AA** and new in 2.2.
  - **Filed, not fixed: [#304](https://github.com/fmanimashaun/claude-skills/issues/304).** Light-mode
    `--primary` on `--background` measures **4.42:1**, under 1.4.3's **4.5:1** for normal-size text (it
    clears on `--card` at 4.66:1). That is a **brand-token** defect, not a component rule, so it is an
    issue rather than a workaround written into this entry.

- **The empty `Needs doctrine` section stopped printing guidance for rows that do not exist.** Hitting
  zero left a table header, a column legend and *"Build them when a project needs them"* above **nothing
  at all** — a dead declaration in the one section that exists to mark honest gaps. The renderer now
  states the zero explicitly and keeps the section (the status still exists; the next unclassified
  upstream component may land there). Both directions are fixtures — empty must not emit the table,
  non-empty must not claim there are none — proven by mutating `if needs:` to `if True:`, which fails 3
  of them. **37 → 39 checks**, and a fifth `build_coverage` mutation so the gate keeps proving it.

- **Stepper / wizard is documented** (#95). `coverage.md` **2 → 1**. The gate came back **largely
  INCONCLUSIVE**, which is the correct answer for this row, not a failure — so most of the entry is a
  **maintainer decision recorded on
  [#95](https://github.com/fmanimashaun/claude-skills/issues/95#issuecomment-5147018825)**, and every
  such line in the entry says so. Only the cited lines are citable.
  - **What is citable.** `aria-current="step"` is a real ARIA token (*"Represents the current step
    within a process"*) and *"Authors **SHOULD** only mark one element in a set of elements as current"*.
    **ARIA itself separates a stepper from a tablist**: *"Authors SHOULD NOT use the `aria-current`
    attribute as a substitute for `aria-selected` … For example, in a `tablist`, `aria-selected` is used
    on a `tab`."* And a checkout wizard is inside **3.3.4 Error Prevention (Legal, Financial, Data) at
    Level AA** — Reversible, Checked or Confirmed. Levels stated because they differ: **3.2.2 is A,
    3.3.4 is AA, 3.3.6 is AAA.**
  - **Two absences recorded as absences.** There is **no APG Stepper/Wizard pattern** ("stepper",
    "wizard", "multi-step" appear nowhere on the index), and — checked deliberately — **APG contains no
    warning against reusing Tabs for wizard flows.** Our position that a gated, ordered sequence is not
    *"layered sections of content"* is ours, not APG's.
  - **The finding worth the whole entry: announce by moving focus, and then do NOT add a live region.**
    4.1.3 Status Messages (**AA**) has a two-part test — the message must concern *"the progress of a
    process"* (a step change does) **and** must *"not [be] delivered via a change in context."* Moving
    focus **is** a change of context, and the Understanding document excludes it by name: *"Changes of
    context, by their nature, interrupt the user by taking focus … and so have already met the goal to
    alert the user."* So the two designs are exclusive: move focus to the new step's heading (satisfies
    2.4.3, and 4.1.3 then does not apply), **or** announce via `role="status"` without moving focus.
    Doing both double-announces. An implementer would otherwise reach for the live region *and* the
    focus move, believing both were required.
  - **Decided as ours:** `<ol>` always but `<nav aria-label="Progress">` only when the steps are really
    links (Breadcrumb's landmark rule is real but not transferable — a breadcrumb is a trail to
    ancestors); **no widget keyboard model at all** (it is a display, not a widget — no roving tabindex,
    no arrow keys); **not a `progressbar`** either, since ARIA scopes that to *"tasks that take a long
    time"* that are *"always read-only"* and a clickable step list is not read-only; and **never
    auto-advance on input**, which sidesteps 3.2.2 rather than papering over it with an advisory.
  - **The Progress bar entry gains a scoping note** rather than a rewrite. It was not wrong — it was
    unscoped: a continuous bar showing overall completion *is* that component and `aria-valuetext="Step
    2 of 5"` is right for it; the enumerated named-step list is this one. The two are a paragraph apart
    and a reader would otherwise pick either.

- **Reviews + Rating is documented** (#91). `coverage.md` **3 → 2**. The verdict's most valuable output
  was again negative: **the intuitive citation is the wrong one.**
  - **The governing criterion is 1.1.1 Non-text Content (Level A), not 1.4.1 Use of Color.** A star row
    that encodes a value is *informational* non-text content and cannot claim the *"pure decoration"*
    exception, so it owes *"a text alternative that serves the equivalent purpose"*. **1.4.1 applies only
    where hue alone carries the filled/empty distinction** — filled-vs-empty stars differ in **shape**,
    and the Understanding document names shape as the *remedy* for 1.4.1, not something it regulates. The
    row's old "Nearest guidance" text implied the colour framing; the entry now cites 1.1.1 first and
    1.4.1 conditionally.
  - **No APG rating pattern** — index lists 30, `w3c/aria-practices` `content/patterns` has no `rating`
    directory. **`role="img"` + accessible name is the confirmed technique**: ARIA gives `img`
    **`Children Presentational: True`** and **`Accessible Name Required: True`**, with *"authors MUST
    provide the element with an accessible name."* That collapses five glyphs into one named unit, which
    is the point — five separately-announced stars is the failure it prevents.
  - **`<meter>` is a second spec-honest route for a numeric average** (*"a scalar measurement within a
    known range"*), carried with the spec's own exclusions (*"should not be used to indicate progress"*;
    needs a known maximum). We default to `role="img"` so the average and the per-review value share one
    mechanism.
  - **Two things have no upstream and are maintainer decisions**, recorded on
    [#91](https://github.com/fmanimashaun/claude-skills/issues/91#issuecomment-5146974938) where a
    citation would go: the **interactive picker is a radio group** (no APG pattern covers a 1–5 star
    picker; Radio Group's *"no more than one of the buttons can be checked at a time"* fits a discrete
    five-value choice, Slider's continuous thumb does not — and building it as real radios inherits that
    keyboard model rather than authoring one), and the **accessible-name string** (`"4 out of 5 stars"`;
    nothing upstream prescribes wording).

- **Visual asset doctrine — what fills the large visual area** (#135). New
  `fidara-design/references/visual-assets.md`. Every marketing surface has a region that is neither
  text nor control, and the system said nothing about it — so an agent left it empty, invented
  something inconsistent, or reached for stock art.
  - **Change type: MIXED, and split accordingly.** The hierarchy, the per-surface prescriptions and
    the decision to keep illustration last are **our design decisions** recorded on
    [#135](https://github.com/fmanimashaun/claude-skills/issues/135) — there is **no APG pattern** for
    a decorative background or a product screenshot, and none is invented. The Tailwind v4, image
    format, WCAG and Playwright statements are **external claims** and each carries its citation and
    version boundary in the file. Shipped separately from #131 (pure architecture) because CLAUDE.md's
    grouping condition 3 forbids one branch carrying both kinds.
  - **The gate refuted a claim that would have shipped silently broken.** `bg-gradient-to-*` is not
    deprecated in Tailwind v4, it is **removed**, with no compatibility alias — it is `bg-linear-to-*`
    ([v4 release notes](https://tailwindcss.com/blog/tailwindcss-v4)). The v3 name emits **no class at
    all**, so the failure is invisible.
  - **Three more version boundaries the verdict pinned.** `mask-*` utilities need **Tailwind ≥ 4.1.0**
    ([v4.1.0 release](https://github.com/tailwindlabs/tailwindcss/releases/tag/v4.1.0)), not merely
    "v4" — so the recipes avoid them and say why. Theme custom properties take the **parenthesis**
    form `from-(--decor-1)`; `from-[--decor-1]` emits the raw token and silently does nothing. A
    custom `@keyframes` must be **nested inside `@theme`** beside its `--animate-*` variable.
  - **AVIF is "Newly available", WebP is "Widely available"** (Baseline, checked 2026-07-31) — stated
    precisely rather than calling both widely available, with `<picture>` source order documented as
    significant (first match wins) and the LCP rule from
    [web.dev](https://web.dev/articles/lazy-loading-images): never lazy-load the hero image.
  - **A deliberate departure from the issue, on a WCAG boundary.** #135 asked for ambient
    `gradient-drift`; an infinite decorative animation satisfies all three conditions of **WCAG 2.2.2
    Pause, Stop, Hide** (automatic, over five seconds, parallel with other content), which needs a
    **pause control** — and `prefers-reduced-motion` is not that control. So we ship a **one-shot
    1.2s settle** instead and say what taking the loop would cost.
  - **Both motion patterns the issue named did not exist.** `gradient-drift` and `reveal-on-scroll`
    appear nowhere in the repo; the issue prescribed them as though shipped. They are defined here
    from `motion.md`'s existing tokens and renamed `decor-*`. `decor-reveal` applies its hidden state
    **from JavaScript**, so a page whose observer never runs renders fully visible — the obvious
    CSS-first implementation hides content permanently on any JS failure.
  - **Decoration cannot name `fm-*` primitives**, since `brand.md` makes `Ui::Logo` the only component
    permitted literal colours. It reads four optional `--decor-*` properties with **role fallbacks**,
    so a pack declaring none still renders on-brand. Verified against
    `plugins/design-flow/scripts/brand_pack_lint.py`: `ROLES`, `DARK_REQUIRED` and the `-foreground`
    pairs are fixed lists, so extra `:root` properties pass **with no plugin change** — whereas adding
    them as required roles would fail every existing pack, and a `brand.json` field would trip the
    unrecognised-key warning. No new pack field; `brand.md`'s "colours, logo, chart proof" holds.
  - **Two departures from #135's empty-state recipe, both to avoid contradicting shipped doctrine.**
    We keep `bg-muted` — the issue is right that `bg-primary/10 text-primary` is an established
    icon-chip idiom (stat/KPI chip, soft badges, avatars, active pagination), and that is precisely
    why it is wrong here: in every one of those the tint marks something **active or affirmative**,
    while an empty state is a neutral absence, and `components.md` already specifies `bg-muted`.
    We also keep the `size-16` chip, expressing "oversized" through the chip's **font size** — because `lucide_icon`
    may not take `size:`/`class:`, which the self-consistency lint enforces and the issue's wording
    would have violated.
- **Video player is documented** (#95). `coverage.md` **4 → 3**. The verdict refuted three framings
  before a line was written, and the most useful anchor was one the issue never mentioned.
  - **No APG pattern for a media player.** The index lists 30 and none is one; `w3c/aria-practices`
    `content/patterns` has no media directory either. So there is **no upstream keyboard model at
    all**, and any "video player pattern" keybinding is somebody's convention. The entry says so and
    inherits the UA's model instead of authoring one.
  - **`controls` guarantees less than it looks.** The HTML Standard says the UA *"**should** expose a
    user interface"* with *"features to begin playback, pause playback, seek…"* — a **should**, with
    **no key bindings specified anywhere in the section**. Space-to-play and arrow-to-seek are browser
    convention, so they are documented as convention and never as a contract.
  - **The autoplay rule is WCAG 2.2.2 (Level A), not reduced-motion** — and 2.2.2 is what the issue's
    framing missed. A hero video is *"moving … information that (1) starts automatically, (2) lasts
    more than five seconds, and (3) is presented in parallel with other content"* and needs *"a
    mechanism … to pause, stop, or hide it"*. Understanding 2.2.2 names the case (*"Common examples
    include motion pictures, synchronized media presentations, animations"*) and scopes it: *"'starts
    automatically' broadly refers to animations/updates that are not the direct result of a user's
    intentional activation"*. So a player the visitor presses play on is out of scope; a background
    loop is not. **1.4.2 Audio Control (A)** stacks on top if sound can start automatically past 3 s.
  - **Captions ≠ subtitles, and the levels do not merge.** 1.2.2 (**A**) requires captions;
    `<track kind="captions">` covers *"sound effects, relevant musical cues…"* while `kind="subtitles"`
    is *"for when the sound is available but not understood"* — shipping the latter where the former is
    owed fails 1.2.2. 1.2.3 (**A**) accepts *"an alternative for time-based media **or** audio
    description"*; 1.2.5 (**AA**) removes that escape hatch. Written out per level, because conflating
    A and AA here is the easy error.
  - **Two AA criteria are dormant only while the controls are native**, and both carve native chrome
    out *by name*: 1.4.11 (*"where the appearance of the component is determined by the user agent and
    not modified by the author"*) and 2.5.8 (*"User Agent Control"*). Author your own and you owe 3:1
    and 24 × 24 CSS px on every control.
  - **Three things are ours and say so**: muted-by-default (the HTML Standard offers "allow playback
    while muted" only as an example of a policy a UA *could* adopt — never a guarantee), reduced-motion
    suppressing autoplay (Media Queries 5 says nothing about video or autoplay, and the nearest
    criterion, 2.3.3, is **AAA and about interaction-triggered animation**), and requiring an accessible
    name on the player.
- **The stale-fallback guard was checking one of its two inputs** (found flipping the row above).
  `resolve_build` prefers a row's own `build=` kwarg over the `BUILD` dict, but the guard read only the
  dict — so a `documented` row whose "use the workaround until the entry lands" text sat **inline**
  passed silently. That is the exact defect the guard exists to catch, in the half nobody looked at,
  and the text is invisible in the rendered table. The guard now reads both sources, with a firing
  fixture and a near-miss (`needs doctrine` + inline `build=` must stay silent) — 35 → 37 checks.
  Turning it on found **three** rows already carrying it: Calendar / Date picker / Time picker,
  Image gallery / Lightbox and Carousel / Slider, all promoted with the workaround text still attached.

- **Marketing copy doctrine — what each section *says*** (#131). New
  `fidara-design/references/marketing-copy.md`. The kits supply layout and visual system; they supply
  no information architecture and no words, so an agent could compose a structurally perfect landing
  page and still ship lorem-grade copy.
  - **Change type: architecture/design decision, no external framework claim.** There is no upstream
    for what a hero says — no spec, no framework, and the **ARIA APG has no pattern** for a value
    proposition. Authority is the maintainer decision recorded on
    [#131](https://github.com/fmanimashaun/claude-skills/issues/131); nothing here is dressed in a
    borrowed citation. Nothing is copied from `MikeFishbeinAtherial/infinite-headcount` (the repo
    that prompted the idea) — it carries **no licence**, so it informed the question, never the text.
  - **The rule that outranks the rest: the human owns positioning, the agent drafts against a brief.**
    And the sharp corollary — **an invented fact is worse than a visible blank.** `{{customer_count}}`
    is a defect the auditor catches; "Trusted by 4,000 teams" is a false statement that ships,
    precisely because it is well-formed. Never synthesise a metric, customer, quote, logo or
    certification.
  - **One contract per shipped archetype (job / shape / failure mode).** #90's **16** marketing
    section archetypes landed as `composition` rows in `coverage.md` rather than as a separate file,
    which is easy to miss — the first draft of this work asserted they had not landed at all, and the
    self-review caught it. The table is keyed to **coverage.md's exact names** and the correspondence
    is made re-checkable by a one-line `grep` printed in the file, so an archetype added there
    without a contract row shows up as a gap instead of going unnoticed. Also covers the three
    product surfaces that fail the same way (empty state, error page, auth) and the two page-level
    blocks (About opener, Landing's how-it-works).
  - **Commerce is named as out of scope rather than left silent** — storefront/category/product/cart/
    checkout/order copy is governed by product data and legal disclosure, not positioning, so
    stretching these contracts over it would be a `coverage-gap` wearing a table.
  - **The two length caps are derived, not asserted.** `page-anatomies.md` already ships
    `max-w-[45ch]` on the landing `h1` and `max-w-[60ch]` on the sub-head; at ~5 characters per word
    and a two-line ceiling that gives **~12 words** and **~30 words**. The derivation is written out
    so changing the measure changes the cap instead of leaving a stale number behind.
  - **Voice stays pack *documentation*, not a `brand.json` field** — measured, not assumed:
    `plugins/design-flow/scripts/brand_pack_lint.py` warns on any manifest key outside the four
    documented overrides with *"a pack is colours + logo"*. Adding a field our own lint rejects is the
    claims-vs-enforcement defect, so `brand.md`'s *Voice / meta* section remains the home.
  - **Scope stated rather than over-claimed.** The seven mechanical checks (placeholder-text,
    hero-too-long, claim-without-proof, duplicate-hero-cta, numeric-only-pricing-tiers,
    stat-without-unit, greeting-in-auth) are a **specification**; wiring them into `design-auditor`
    and `/design-flow:component` is a **design-flow plugin** change and is not in this PR. The file
    says so, because doctrine claiming enforcement it does not have is `gate-that-cannot-fail`.
  - **Keyed to the archetypes that exist.** #90's finer-grained marketing *section* archetypes have
    not landed, so the contracts are keyed to the anatomies `page-anatomies.md` actually ships plus
    the recurring marketing blocks they call for — and an archetype arriving without a contract row
    is named as a gap to file rather than a licence to improvise.

### 1.24.0 — 2026-07-31

- **Mega menu / Flyout is documented** (#90). `coverage.md` **5 → 4**. **No APG pattern** — the index
  lists 30 and none is a mega menu — so it is governed by the **Disclosure** pattern's *Navigation Menu*
  examples, and the verdict changed what the row could say.
  - **APG recommends AGAINST `role="menu"` for site navigation**, in a callout on its own Menubar
    example: *"A pattern more suited for typical site navigation with expandable groups of links is the
    Disclosure Pattern… few sites need the additional keyboard functionality required to support the
    ARIA `menubar` and `menu` roles."* And on the Disclosure example: *"it does not use the WAI-ARIA
    `menu` role… Typical site navigation does not need all the keyboard interactions specified by the
    menu and menubar pattern."* There is an open upstream proposal to **delete** the Menubar navigation
    example for this reason, so it is not the endorsed route either.
  - **Therefore the row shares NO ARIA with Dropdown**, and the shipped **Dropdown / Menu row gains a
    scoping note**: `role="menu"` is right for an application/action menu and wrong for a nav bar. The
    two look similar and are structurally opposite, which is exactly why a reader would otherwise reach
    for the wrong one. Same citations; a note rather than a rewrite, because that row is not wrong — it
    was unscoped.
  - **A top-level item that must both navigate and expand is TWO elements.** APG's hybrid example:
    *"each item contains a top-level link and an associated disclosure button."* The link navigates, the
    adjacent button carries `aria-expanded`/`aria-controls`. One element doing both is neither properly.
  - **`Tab` and `Esc` are required; arrow keys are explicitly "(Optional)"** in the example's own
    keyboard table. And APG ties `Esc` to an obligation rather than taste: *"Implementing this Esc
    behavior is necessary to meet the WCAG 2.1 1.4.13: Content on Hover or Focus criterion."*
  - **Hover triggers WCAG 1.4.13 (AA) in full** — dismissible, **hoverable**, persistent. The pointer
    must be able to travel into the panel without it vanishing, so **no gap between trigger and panel**;
    a menu that closes across a 4px gap fails *hoverable*, and that is the most common way this is got
    wrong.
  - **Three things are ours and say so**: hover-intent delay (no citation exists anywhere — ~120ms in,
    ~240ms out, and hover is an *enhancement* over a button that works on click), column grouping (APG's
    examples are single-column and silent on it — a heading plus a plain `<ul>`, and **no** invented
    `role="group"`/`aria-labelledby` attributed to APG, and **no** announced item counts), and the
    small-viewport collapse (no upstream at all — it becomes the mobile drawer's nested disclosure list,
    reusing that contract rather than inventing a second mobile nav).

- **File upload/Dropzone and Copy to clipboard are documented** (#95). `coverage.md` **7 → 5**. Batched
  on one mechanism and it held: both are a **native control plus an enhancement**, and in both the
  enhancement's result is invisible without a `role="status"` announcement. **Neither has an APG
  pattern** — the index lists 30 and contains no file upload, drag-and-drop or clipboard entry — so both
  are compositions, and the doctrine says so rather than citing.
  - **`accept` is a hint, not validation**, quoted from MDN: *"It is still possible (in most cases) for
    users to toggle an option in the file chooser… and then choose incorrect file types"*, and therefore
    *"you should make sure that the `accept` attribute is backed up by appropriate server-side
    validation."* **Server-side validation is mandatory**, not good practice.
  - **A script cannot set a file input's value**, which has a design consequence rather than just being
    a security note: a dropzone cannot fill the native input, so the two are **parallel paths to one
    submission**, not a wrapper.
  - **`preventDefault()` on `dragover` or the drop never fires** — the most-missed detail in the API.
    Expressed as Stimulus's `drop->dropzone#drop:prevent` so it cannot be forgotten in the controller.
  - **The WCAG 2.5.7 trap, which is the opposite of the obvious assumption.** Dragging Movements (AA)
    is satisfied by the visible file button — but *"achieving keyboard equivalence for a dragging
    operation does not automatically meet this success criterion, unless that equivalent keyboard
    operation also provides controls that can be clicked or tapped with a pointer."* **So a
    `sr-only`-hidden input behind a dropzone is a 2.5.7 failure even though it is keyboard-operable.**
    That is why the native input stays visible.
  - **Clipboard: the announcement IS the feature.** `navigator.clipboard.writeText` is Baseline **widely
    available since March 2020** and **secure-context only**, rejecting with `NotAllowedError` — so
    failure is a real branch, met first on plain-HTTP staging. Three rules in order of how often they
    are missed: announce it (**WCAG 4.1.3 Status Messages**, AA — a success message that never receives
    focus); **clear the region so a repeat re-announces**, because setting identical text is not a DOM
    change and the second copy would be silent; and handle the failure visibly by selecting the text.
  - **`document.execCommand('copy')` is not the fallback** — it is deprecated, and a deprecated API as a
    safety net is a second thing to maintain that will itself be removed. Selecting the text is the
    honest fallback.

- **Phase B's last two patterns are written — full-text search and bulk transfers** (#98), which
  completes EPIC #96: A, C, D and E were already closed, and these were the only items left in B.
  Placed in their existing homes rather than a new file — search in `advanced-active-record.md` beside
  the other PostgreSQL power features, transfers in `jobs-and-realtime.md` beside the continuations they
  depend on.
  - **The trigger you should no longer write.** PostgreSQL's own docs retired it: *"The method described
    in this section has been obsoleted by the use of stored generated columns."* So maintain `tsvector`
    with a **stored generated column** — PG **12+**, and `t.virtual … stored: true` is Rails **7.0+**.
  - **Rails ships the schema layer and no query builder** for full text; querying is a raw fragment.
    That makes `pg_search` an ergonomics choice rather than a requirement, which is worth stating
    plainly. Its status recorded accurately: last tagged release **2.3.7 (Aug 2024)**, `activerecord >=
    6.1` with no upper bound, repo active — compatible by that floor, not by a Rails 8 certification.
  - **A name collision that could mislead a reader**: there is also a *PostgreSQL extension* called
    `pg_search` (ParadeDB/Neon) implementing BM25 via tantivy. Not the Ruby gem our doctrine means.
  - **Do NOT copy fizzy's 16-way CRC32 search sharding onto Postgres.** It is a **MySQL-forced**
    workaround — MySQL documents that partitioned tables do not support `FULLTEXT`. PostgreSQL has
    supported **indexes on partitioned tables since 11**, where a GIN index on the parent propagates to
    every partition, so declarative partitioning needs no app-level shard router. Inheriting that scheme
    would be importing a workaround for a limitation we do not have.
  - **When the database stops being enough, with the documented and the consensus halves separated.**
    Quotable from PostgreSQL: GIN *"insert or update one heap row can cause many inserts into the
    index"*, and the hard ceilings (`tsvector` < 1 MB, lexeme < 2 KB, `tsquery` < 32,768 nodes).
    Labelled as practitioner consensus, because no PostgreSQL document says it: no BM25/IDF ranking, no
    native typo tolerance (that is `pg_trgm`), no native faceting.
  - **`rubyzip` is not a streaming writer, and "stream a ZIP with rubyzip" would have been wrong.** It
    rewinds and finalises, so it wants a **seekable** destination; **`zip_kit`** exists for the
    non-seekable case and is written by a rubyzip contributor. Pick by destination: tempfile →
    `rubyzip`, straight to a client or S3 → `zip_kit`. Ruby's stdlib has no ZIP writer at all.
    `send_stream` is Rails **7.0**.
  - **Two Active Storage ceilings, not one** — conflating them is how a 500 GB export gets designed
    against the wrong limit. Server-side `create_and_upload!` switches to **multipart above 100 MB**
    (Rails 6.1+) and is bounded by S3's real limits (**48.8 TiB**, 10,000 parts); **browser direct
    upload is a single presigned PUT capped at 5 GB**, which Rails' tracker records as expected
    behaviour rather than a bug. A large transfer must use the server-side path.
  - **Resumable-transfer safety is entirely application-level**, and doctrine says so rather than
    implying framework support: continuations checkpoint *the cursor*, not the half-written archive or
    the half-completed upload. Cursor column, manifest of completed chunks, per-part checksums, explicit
    status enum.
  - **fizzy's 500+GB is their production scale, not a Rails or Active Storage limit** — not cited as a
    boundary.

### 1.23.0 — 2026-07-31

- **#275's open measurement boundary is now closed by a reading, and it found one more thing.** The
  entry below deliberately recorded that Ruby 4.0 was *not* measured. It has been now, on 4.0.6, and
  **`parse.y` itself changed**: the form it rejects on 3.4.7 it **accepts** on 4.0.6.

  | `private def a = foo k: 1` | ruby 3.4.7 | ruby 4.0.6 |
  |---|---|---|
  | `--parser=parse.y` | **syntax error** | Syntax OK |
  | `--parser=prism` | Syntax OK | Syntax OK |
  | default | Syntax OK | Syntax OK |

  So the failing combination is narrower than first written: **`parse.y` on Ruby 3.2–3.3**, where it is
  also the default. The advice (parenthesize) and the reason (our floor is 3.2) are unchanged — the
  table replaces an inference with four readings. Confirmed the flag is still honoured in 4.0.6 rather
  than silently falling back, since a bogus `--parser` value raises `unknown parser`.
  - **The whole corpus was re-checked under 4.0.6: 310 fenced blocks — 185 ruby, 89 erb — all parse,
    and the sweep is 34 passed / 0 failed / 0 skipped.** Worth stating because the markdown-code gate
    runs whichever `ruby` is on `PATH`, so a toolchain upgrade silently changes what that gate means.

- **FIX — an endless-def `SyntaxError` was asserted unconditionally when it is parser-scoped** (#275).
  `controllers-routing.md` §7 said `private def m = render x: 1` *"is a `SyntaxError`"* flat. Measured
  on one binary, ruby 3.4.7, changing only the parser: **`parse.y` errors** (`unexpected label`,
  which independently confirms the note's own explanation) and **Prism accepts it**. `parse.y` is the
  default **through 3.3**, Prism **from 3.4**.
  - **The contradiction that made this worth fixing rather than softening:** the same skill requires
    **Ruby >= 3.2** while recommending the latest stable release — so the failing form breaks on the
    floor we support and is silently fine on the version we suggest. That is precisely how a snippet
    ships broken: it parses on the author's machine and raises on the user's.
  - The advice is unchanged and now has a reason that survives checking: **parenthesize the body**, so
    the form is correct on every supported version rather than on some of them. The scope is also
    narrowed — bare `def m = render x: 1` is fine on either parser; it only breaks when the endless
    `def` is an argument to another call.
  - **Measurement boundary recorded**: 3.4.7 under both parsers; Ruby 4.0 not measured, so
    Prism-by-default there is stated as following from the 3.4 change rather than as a reading taken.
  - #269 (the code block that actually raised) was verified already fixed on `dev` by #273 and closed
    — the block was one claim, the explanation of why is another, and splitting them was right.

- **FIX — one rule, two precisions, in two skills.** Found by reviewing `dev` after six parallel
  sessions merged. `interaction-stimulus.md` said raw ActionCable is "allowed only for genuinely
  bespoke real-time… document why Streams didn't fit" — a judgement call — while the new
  `hotwire/references/production.md` derived a **testable** line from Campfire: **Action Cable when
  the payload is a *fact*, not a *fragment*.** Not a contradiction, which is why no gate saw it, but
  two statements of one rule at different sharpness is how a reader ends up citing the weaker one.
  The fidara-design entry now states the sharp rule and defers to the derivation.

- **NEW `hotwire/references/production.md` — Hotwire under production pressure** (#99, Phase C of
  #96). Extracted from two 37signals apps, **attributed**: [once-campfire][cf99] (MIT, real-time
  chat) and [fizzy][fz99] (O'Saasy, drag-and-drop Kanban). Every framework claim carries a
  version-bounded citation; every design call is labelled **OURS** with its reason. Fifteen claims
  went through `doctrine-verifier` in three batches — verdicts and the six maintainer decisions are
  recorded on [the issue][d99].
  - **The two apps disagree about real-time, and the disagreement is the doctrine.** Fizzy is the
    *bigger* app and has **zero** Action Cable channels (`broadcasts_refreshes` only); Campfire has
    six and writes its streams by hand. So app size does not pick the rung — update rate, render
    cost, and client state do. That escalation test is **ours**; `turbo.md` §3 said "prefer
    refreshes" without ever saying when not to.
  - **Optimistic UI is one line of Ruby.** `Message#to_key` returns `[client_message_id]`, so
    `dom_id` — which derives from `to_key`, verified in `ActionView::RecordIdentifier` — emits the
    same id the client already rendered its pending element with, and the arriving `append`
    collapses the pair. No reconciliation pass, no diffing library.
  - **A catch-up path is now mandatory, not a nicety**, and is added to the skill's definition of
    done. Streams are fire-and-forget, so a broadcast-only page is **silently stale after every
    network blip** — the largest gap the audit found in our own doctrine. Campfire's answer is a
    `?since=` REST resource driven by a bodiless `HeartbeatChannel`, with the high-water mark held
    in the DOM.
  - **Action Cable vs Turbo Streams, given a testable edge:** Streams when the server knows what the
    DOM should become; raw Action Cable when the server has a **fact** and each client decides what
    it means. All six Campfire channels are on the second side and none carries HTML. Our
    "Streams first" posture is confirmed by production use, not merely asserted.
  - **Two morph hazards neither handbook mentions** — morph strips the `open` attribute off a live
    `<dialog>` (cancel `turbo:before-morph-attribute`), and a broadcast refresh will morph away an
    edit in progress (set `data-turbo-permanent` from `connect()`, remove it in `disconnect()`).
  - **`Turbo.offline` is REJECTED, and this is the most valuable finding.** Fizzy pins
    `turbo-rails` to the `offline-cache` branch and calls `Turbo.offline.start(…)`. Verified: that
    API ships in **no released** Turbo or turbo-rails — the branch re-exports an **open, unmerged**
    PR ([hotwired/turbo#1427][t1427]), and the matching turbo-rails PR was closed unmerged by its
    own author. Reading the Gemfile as licence to copy would have put an unreleasable git-branch
    dependency into shipped doctrine.
  - **Verdict on our four-mixin Stimulus doctrine: neither validated nor contradicted**, stated as
    such. Neither app uses JS mixins at all; both parameterise one generic controller instead
    (Fizzy's `navigable_list_controller` carries eleven configuration values). Calling that
    validation would be a citation that does not survive being checked.
- **Three corrections to shipped hotwire doctrine, all exposed by the gate** (#99). Each was wrong
  in a way that reads as right, which is why they survived until something checked them.
  - **`append`/`prepend` de-duplication was described as replacement in place.** It is
    remove-then-append at the container's **edge**; the scope is **direct children of the target
    only**; it matches *every* top-level template child carrying an `id`. The guarantee is id
    uniqueness, **not position** — for in-place you want `replace` with `method="morph"`.
  - **"Prefer the `_later` broadcast variants" was stated flatly, and it is incomplete.**
    Verified: **nothing** in ActiveJob, Solid Queue or turbo-rails guarantees the order of two
    `_later` broadcasts to the same stream — no priority, no concurrency key, and Solid Queue's own
    README disclaims it. So `remove` never needs `_later` (it renders nothing), and when order is
    observable — a transcript, a feed — you broadcast **synchronously**. This is why Campfire calls
    `broadcast_append_to` from its controller.
  - **`turbo:morph` was paired with `turbo:before-morph-element`; they are different scopes.**
    `turbo:morph` fires once per morphed *page refresh*; the per-element pair is
    `turbo:before-morph-element` / `turbo:morph-element`. `turbo:before-morph-attribute` was missing
    from the events list entirely.
- **`turbo.md` and `stimulus.md` gain four verified APIs the references omitted** (#99):
  `<turbo-stream method="morph">` on `replace`/`update` (Turbo ≥ 8.0.5 — and **not** on
  `append`/`prepend`/`before`/`after`); the **writable** `event.detail.render` on
  `turbo:before-stream-render`; Stimulus `static get shouldLoad()` (3.0+) and `static afterLoad()`
  (3.2+); and the fact that `data-turbo-permanent` **requires an `id` for Drive persistence but not
  for morph exclusion** — the asymmetry that makes a runtime morph-guard sound. Also recorded: a
  refresh broadcast is suppressed in the tab that caused it via `X-Turbo-Request-Id`, but the
  recognition set holds only the **last 20** requests per page load.

[cf99]: https://github.com/basecamp/once-campfire
[fz99]: https://github.com/basecamp/fizzy
[t1427]: https://github.com/hotwired/turbo/pull/1427
[d99]: https://github.com/fmanimashaun/claude-skills/issues/99#issuecomment-5140601026
- **`controllers-routing.md` §7 shipped a Ruby block that raises `SyntaxError` on paste** (#269).
  `private def render_not_found = render file: …` does not parse; parenthesising the body fixes it.
  Verified against the **reference implementation** (ruby 3.3.6) rather than asserted — `ruby -c`
  gives `syntax error, unexpected label, expecting 'do' or '{' or '('`, and `Syntax OK` with parens.
  - **The rule is narrower than it looks, so the corrected block now says why.** It is *not* "endless
    defs reject bare keyword arguments" — `def a = foo k: 1` is **valid**. It breaks only when the
    endless `def` is an argument to another call: `private def a = foo` parses first, leaving `k: 1`
    with nothing to attach to. Version boundary: measured on ruby 3.3.6; the parse rule is not
    version-specific to 8.1 and the parenthesised form is valid on every Ruby with endless defs (3.0+).
  - **Present since `38c2091` (initial release, 2026-07-05)** — live on `main` for the skill's whole
    life and baked into `dist/rails-8.skill`, so it reached the claude.ai upload path too. `dist/`
    repackaged.
  - **Grepped for the class, not just the instance** — `private def … = …` occurs exactly once in
    `skills/`, so this one did not travel in a group. Caught by `lint_markdown_code.py`, which is
    precisely the copy-paste hazard it was built to find; the gate now reports `no findings`.

### 2026-07-30 — the umbrella-Closes rule

- **NEW `references/motion.md` — motion doctrine** (#136). Our entire motion doctrine was **one
  line** (*"150–200ms `ease-out`, transition colors/opacity/transform, gated on
  `prefers-reduced-motion`"*), which governs component state transitions and nothing else. Adapted
  from [interior](https://github.com/ddoemonn/interior)'s
  [`DESIGN.md`](https://github.com/ddoemonn/interior/blob/main/DESIGN.md) (MIT, © ddoemonn),
  **attributed**, with every adapted constant marked as ours rather than quoted.
  - **A departure is always shorter than an arrival** — the highest-value rule, and we had no version
    of it. One easing in both directions is why replacements *"either lag or smear together"*. Tokens
    gain a **departure curve** (`--ease-in`) beside the shipped arrival curve.
  - **Distance chooses the duration, not component type.** Three tiers — `--duration-fast` 120ms
    under 20px, `--duration` 180ms for 20–200px, `--duration-slow` 280ms over 200px — and **an exit
    takes the tier below its entrance**, which turns rule 1 into a table rather than a judgement call.
    The three figures are **ours**, derived by holding our shipped 180ms as the mid tier; their
    millisecond values come from spring settling times and do not carry over.
  - **Opacity finishes before height on disclosure** — *"opacity finishing first hides the reflow."*
    We ship a Disclosure component with a height transition and never said this.
  - **Reduced motion: change the behaviour, not just the timing.** *"The information still arrives,
    the trip is skipped."* Never remove the element or the state change — zero the duration, because
    *"the element must still end up in the right place"*. And where timing is not the problem, change
    behaviour: `scroll-behavior: auto`, a text reveal that jumps to its final state, a marquee that
    stops rather than loops faster. This is the same rule as our existing *"a state change must never
    depend on an animation event firing"* seen from the other side.
  - **The eight ways a gesture can be abandoned**, which our four Stimulus mixins said nothing about:
    `pointercancel`, `lostpointercapture`, `pointerleave`, window `blur`, `visibilitychange`, Escape,
    blur, and move tolerance. *"If a component can be mid-gesture, it registers a window `blur`
    listener"* — otherwise alt-tabbing mid-press leaves the element stuck in its pressed state, a bug
    invisible in testing because nobody alt-tabs during a click on purpose. Also: treat
    `lostpointercapture` as a **cancel, not a drop**, and pick `touch-action` by the axis you own.
  - **Cap the stagger** — `per-child delay × count ≤ 1.6s`, because *"a stagger that scales with the
    data eventually becomes a wait."* Twelve cards at 80ms is pleasant; sixty rows is five seconds of
    the page assembling itself.
  - **Physics runs linear, intention runs eased.** A ripple expands at constant speed; a spinner turns
    at one rate *"because it is reporting an unknown"*. Easing a spinner implies it knows how far along
    it is — the one thing it is admitting it does not. Consistent with the loading contract.
  - **Focus: two signals, never three** — never combine a ring, a border change and a shadow. Draw the
    focus edge after the fill, and as a sibling above anything that slides underneath.
  - **Zero layout shift**, with the *invisible twin* named as the technique: reserve the widest state
    permanently and animate opacity inside a box that never resizes.
  - **CSS primitives, verified with version boundaries rather than assumed.** **CSS has no spring
    easing** — three families only (linear, cubic-bézier, step) — which is why the springs do not port.
    `linear()` *can* pre-sample a spring curve, is Baseline **since December 2023**, and the technique
    is documented by Chrome's own developer site; we hold off on **cost** (40-plus points per curve,
    unreadable at the call site), not support. And an **entrance no longer needs JavaScript**:
    `@starting-style` + `transition-behavior: allow-discrete` make `display: none → block`
    transitionable, Baseline **"Newly available" 6 Aug 2024** — *not* yet widely available (that tier
    is Feb 2027), so it is a progressive enhancement, not a floor.
  - **A refutation worth recording.** I was going to present gating on
    `@media (prefers-reduced-motion: no-preference)` as best practice. **MDN's own canonical example
    and WebKit's own article both use the opposite direction**, and the Media Queries spec makes no
    authoring recommendation at all. We keep `no-preference` because it **fails safe** — a UA without
    the media feature never matches it, so motion never activates — but it is now recorded as **our
    reasoned default, not a citation**.
  - **Token consumption is asymmetric, and getting it wrong means a class silently does nothing.**
    `--ease-*` **is** a Tailwind v4 namespace, so `--ease-in` generates an `ease-in` utility and
    **overrides** Tailwind's default (as our shipped `--ease-out` already does). There is **no
    `--duration-*` namespace** — durations are consumed as `var(--duration-fast)` or with Tailwind's
    `duration-(--duration-fast)` custom-property syntax.
  - **Cross-page motion (Turbo 8).** v8.0.0 shipped **two separate features** commonly conflated:
    morphing page refreshes (idiomorph) and **View Transitions support for navigations**. The latter
    needs `<meta name="view-transition" content="same-origin">` on **both** pages. Correction worth
    having: the Hotwire handbook does **not** provide `view-transition-name` — that is **plain CSS**
    from the View Transitions API, working because Turbo enabled transitions for the navigation, not
    because Turbo wraps it.
  - **What we did NOT take, and why**, rather than a silent filter: the five named springs are
    `motion` solver constants with no CSS equivalent; velocity handoff needs a spring to hand off to;
    entry/exit blur is dropped as our call (cost over benefit at our durations); and the React
    machinery (`layoutId`, quantized step state) becomes "write a custom property on rAF rather than
    toggling classes" in Stimulus.

- **FIX — the `rate_limit` test-store advice shipped an hour earlier was wrong** (#98). It said to
  "stub a real store (`:memory_store`) in any example asserting either behaviour". That works for the
  single-use marker, which goes through `Rails.cache` directly — and **cannot work for `rate_limit`**,
  which counts through `config.action_controller.cache_store` and, because the signature is
  `store: cache_store`, evaluates that default **when the class body loads** and captures it in the
  `before_action` closure. By the time an example runs the store is already bound, so
  `allow(Rails).to receive(:cache)` never reaches it and the spec goes green while the limiter does
  nothing. The doctrine now gives the two cases **different** fixes: a per-example stub for the marker,
  and a real store configured in the test environment plus a per-example `clear` for the limiter (one
  instance per process, so counts otherwise accumulate and the suite turns order-dependent).
  - **Found by applying the doctrine to a real app rather than by re-reading it.** The first attempt
    used the stub the doctrine prescribed, the throttle spec failed, and the mechanism came out of
    diagnosing why — which is the same lesson as every other defect this session: executing found it,
    reading would not have.

- **Cross-plane sign-in doctrine, and four corrections to the security checklist** (#98). A unified
  sign-in front door authenticating **both** realms, holding **no session of its own**, minting a
  short-lived single-use **encrypted** grant and handing off to the plane that exchanges it for its own
  host-scoped session (fidara-ledger D-038/D-039, accepted 24 Jul 2026).
  - **Why a hand-off and not a shared cookie:** a cookie with no `Domain` is confined to the exact host
    that set it (RFC 6265), and Rails' `domain: :all` — which *would* share it — is declined on purpose,
    because a shared cookie lets an XSS on one plane reach another plane's session.
  - **Encrypt, do not sign, and the reasoning is verified rather than repeated.** `MessageVerifier`'s own
    docs: *"Signing is not encryption… The payload is merely encoded (Base64 by default) and can be
    decoded by anyone."* The grant rides in a URL, so signed-only would publish the raw record id to
    browser history, referrer headers and CDN logs.
  - **`decrypt_and_verify`'s failure modes are asymmetrical** — it **returns `nil`** on expiry and on a
    purpose mismatch, and **raises** only on tamper or corrupt format. A `rescue`-only implementation
    sails past an expired grant with a `nil` and blows up on the next call. Check the return value *and*
    rescue.
  - **`config.hosts` is EMPTY in production by default** — the checklist previously framed Host
    authorization as a development concern only. Where the list is empty the middleware returns
    immediately and does nothing, so anything deriving a redirect target from `request.host`/`.domain`
    trusts an attacker-controlled header until it is set. It rejects with **403 before the app runs**,
    which is what makes it a real defence.
  - **Rails 8.1 replaced `raise_on_open_redirects` with `action_on_open_redirect`** (`:log`/`:notify`/
    `:raise`; framework defaults still raise) and added
    **`config.action_controller.allowed_redirect_hosts`** — preferred over `allow_other_host: true`,
    which disables the check for the *entire call* while the allowlist keeps every other host blocked.
    Also recorded: **"another host" is an exact match and subdomains count**, so `app.` → `admin.` is
    cross-host.
  - **Two specs in this area pass whether or not the code works**, because the Rails test environment
    defaults to `:null_store`. `NullStore` ignores `unless_exist` and returns `true` every time, so a
    **single-use** spec never sees a rejected replay; and `rate_limit` calls `store.increment`, which
    `NullStore` answers with `nil`, making **`rate_limit` a permanent no-op in test**. Stub
    `:memory_store` or the test is vacuous. (`rate_limit` arrived in **7.2** and needs a real store.)
  - **`unless_exist` atomicity is store-specific, not an API guarantee.** On **Solid Cache** the write
    takes a `SELECT … FOR UPDATE`, which is genuinely atomic for an existing key — but a brand-new key
    has **no row to lock**, so two concurrent first-claims can both win. Narrow and bounded, and written
    down rather than implied airtight. Redis `SET NX`/memcached `ADD` have no such window, so the caveat
    is Solid Cache's, not `Rails.cache`'s.
  - **`authenticate_by` is Rails 7.1, not 7.0**, and it is required here rather than optional: it *"takes
    the same amount of time regardless of whether a user with a matching email is found"*, so a `find_by`
    + `authenticate` pair would be a timing oracle defeating the uniformity the front door works for.
  - **A residual timing channel the uniform messages do not close**, flagged rather than glossed:
    `User.authenticate_by || StaffUser.authenticate_by` runs **one** lookup on a tenant hit and **two**
    when neither matches, so latency still varies by realm. Evaluate both unconditionally if realm
    disclosure matters.
  - **Terminology pinned rather than invented:** identifier-first sign-in is **home realm discovery**,
    and the enumeration requirement is **OWASP WSTG-IDNT-04**, which asks for *"the same error message
    **and length**"* — so keep the response *shape* constant, not just the wording.
  - **`allow_unauthenticated_access` is generated code, not a framework method** — the Rails 8
    authentication generator defines it as `skip_before_action :require_authentication`.

- **FIX — a Phase B claim shipped an hour earlier was incomplete** (#98). `multi-tenancy.md` said *"each
  plane gets its own authentication stack, not a role check on a shared one."* True for the invariant it
  protects — two identity models, two session tables, two cookies — but readable as forbidding **any**
  shared component, which the unified front door above would then contradict. Now scoped: "its own stack"
  means its own session, cookie and identity model, not "no shared code may precede it", with a forward
  reference to the pattern. Found by checking the implementation rather than by review.

- **NEW `references/multi-tenancy.md`** (#98, Phase B of EPIC #96). Rails documents **no** row-level
  tenancy doctrine — the guides' only use of "multi-tenant" is horizontal *sharding* — so every choice
  here is recorded as a choice and every framework fact is cited to source.
  - **The file's first job is separating two axes people collapse into one:** *isolation* (separate
    database / schema / **row-level**) and *identification* (subdomain / URL path / **session** /
    header). Choosing "subdomain" says nothing about how queries are scoped, and that confusion is why
    this file exists.
  - **Maintainer decision recorded: session-selected tenant, never in the URL** (fidara-ledger D-009,
    accepted 19 Jul 2026). Three reasons in the order they mattered: it is the category norm (Xero,
    QuickBooks, Wave, Zoho, FreshBooks all use an org switcher); the alternative's main benefit did not
    apply, because external users hit **one-off tokenized links** rather than a standing per-tenant
    space; and it is **the most reversible** — path or subdomain tenancy can be layered on later without
    a data-model change, while backing out of either is the expensive direction.
  - **Subdomains separate *planes*, not tenants** (D-012): root for marketing, `app.` for the product,
    `admin.` for the operator console — routed with `constraints subdomain:` + `scope module:` (not
    `namespace`) so the host picks the controller and URLs stay identical. **Each plane gets its own auth
    stack**, so a tenant session grants zero admin access *structurally* rather than because a
    `before_action` remembered.
  - **The session value is still re-authorised every request.** `Current.user.organizations.find_by(id:
    session[:organization_id])` is the authorisation — written as `Organization.find_by(id: …)` the same
    line is a tenant-switching hole, and that distinction is the load-bearing detail.
  - **Five verified reasons not to use `default_scope`**, each confirmed against Rails 8.1 source or by
    running it: a wrong-tenant `find_by` returns **`nil` rather than raising**, so the block reads as
    "not found"; it leaks into `new`/`create` (and sets a null FK when `Current` is nil — the database
    `NOT NULL` constraint is the real safety net); `unscoped` bypasses it; it is evaluated **when a
    `Relation` is constructed, not when the query runs**, so a memoized or cross-boundary relation keeps
    a stale tenant; and `joins` with `default_scope` has open Rails bugs spanning 4.2→7.2. Both
    fidara-ledger and 37signals' fizzy contain **zero** `default_scope`.
  - **The job boundary is the section to read twice, and it is worse than an ordering problem.** `Current`
    never survives enqueue → perform (ActiveJob wraps every execution in the reloader, which calls
    `clear_all`), and Rails ships no built-in carrier. But **GlobalID's default locator is an
    `UnscopedLocator`** — it strips *all* scopes by design, and has since 2016 — so `default_scope`
    provides **zero** protection for a record arriving as a job argument. Not "depends on timing":
    structurally none. And `deserialize_arguments_if_needed` runs **before** `run_callbacks :perform`, so
    a tenant restored in `around_perform` is restored too late. Restore it in the job's
    **`deserialize(job_data)`**, and re-check tenancy explicitly inside `perform`.
  - **PostgreSQL RLS has one trap that makes it inert**, and it is the fact most likely to be written
    down wrong: *"table owners normally bypass row security as well."* A Rails app usually **owns** the
    tables its migrations created, so the default outcome is policies defined, RLS enabled, and RLS doing
    **nothing**, silently. `FORCE ROW LEVEL SECURITY` is the lever that matters; checking for
    `BYPASSRLS` proves nothing. Plus: `SET LOCAL` is transaction-scoped and a bare `SET` **leaks to the
    next tenant on a pooled connection**, and `SET LOCAL` outside a transaction is a silent no-op.
  - **Identifiers, since the org is not in the URL.** Ours keeps the PK and mints an opaque prefixed
    `public_id`, with the **unique index as the guarantee** plus a bounded collision retry that matches
    the violation **by index name** (not by sniffing the message) and **only retries a self-minted
    value**, so a caller-supplied duplicate still surfaces the real error. For UUID PKs, four facts
    first: `id: :uuid` is **PostgreSQL-only** in Rails; `gen_random_uuid()` is UUID**v4** (random, so
    index bloat); **no Rails version generates UUIDv7** — that is `SecureRandom.uuid_v7` on **Ruby ≥
    3.3** or PostgreSQL ≥ 18's `uuidv7()`; and 16 bytes vs 8 repeats on every FK. "base36, 25 chars" is
    fizzy's own scheme, not a standard.
  - **Gem landscape corrected:** `acts_as_tenant` is row-level, maintained, and openly `default_scope`-
    based — so it centralises the hazards rather than avoiding them, and it has an **open issue about
    Solid Queue specifically**, our default adapter, where the tenant is missing from the stored job
    payload. `apartment`/`ros-apartment` are **schema/database-per-tenant — a different axis**, not
    row-level alternatives.
  - **Enforcement, stated honestly:** no standard tool proves every tenant query is scoped. The building
    block (`sql.active_record` notifications) is real; the subscriber is a hand-roll. Until then the
    enforcement is a `NOT NULL` tenant FK, association traversal that makes an unscoped query *look*
    wrong in review, and the per-job re-check above.

- **FIX — `extending-rails.md` taught subdomain-based *tenant* resolution** (#98), which contradicted the
  decision above. Its Rack-middleware example resolved a tenant from `request.subdomain`, so anyone
  skimming for "how do I do tenants" found tacit endorsement of a model the doctrine rules out. The Rack
  mechanics are identical for any cross-cutting concern, so the example now tags the request and resolves
  the **plane**, and the "when to write middleware" list no longer leads with tenant resolution.

- **FIX — `sso.md` needed its tenancy claim scoped, not rewritten** (#98). It resolves a workspace from
  the subdomain, which is defensible for enterprise SSO (IdP redirect URIs are commonly workspace-scoped)
  but is not our general model. A scope note now says so and points at the new reference — and notes that
  its **isolation** half is already correct: `workspace.users.find_by(…)`, association traversal, no
  `default_scope`. That is what generalises.

- **NEW `references/style.md` — how Rails code should read** (#97, Phase A of EPIC #96). The skill
  prescribed architecture, testing and deployment and said **nothing** about how code reads. Sourced to
  [37signals' `STYLE.md`](https://github.com/basecamp/fizzy/blob/main/STYLE.md) in
  [basecamp/fizzy](https://github.com/basecamp/fizzy) — production Rails by the people who make Rails,
  licensed MIT-equivalent so quoting is permitted, and **attributed**. All twelve upstream claims
  verified verbatim against the source; every adopt/adapt decision and its reason recorded, because
  inheriting a convention silently is how a project ends up with two styles and an argument.
  - **Six conventions adopted:** method ordering (class → public with `initialize` first → private),
    invocation order (vertical, call-order), bang methods, visibility-modifier indentation (plus the
    private-only-module variant), and the `_later`/`_now` job-naming pair.
  - **`_later`/`_now` is the most immediately useful of them** because it settles a question every Rails
    app re-litigates: **the logic lives on the model**, and the job is a two-line adapter. `_later` names
    the enqueuing method so a call site reads as non-blocking; **`_now` is scoped to the
    callback-into-self case**, not a suffix for every synchronous method — generalising it would misread
    the source.
  - **One convention ADAPTED, not adopted wholesale.** *Expanded conditionals over guard clauses* is
    **demonstrably contrary to prevailing Ruby advice**: stock RuboCop enables `Style/GuardClause` **by
    default**, keyed to the community style guide's *"Prefer a guard clause when you can assert invalid
    data."* The pattern fizzy calls "bad" is the one the community guide calls good. We adopt the
    preference **and its two named exceptions**, and add a rule of our own: **do not "fix" an existing
    guard clause, and never reject a change solely for using one.** A style preference that generates
    review churn costs more than it earns, and an agent applying this dogmatically produces `if`/`else`
    where a guard was clearer.
  - **Two conventions turned out to be doctrine we already had** — *"a new resource, not a custom
    action"* (`controllers-routing.md` §1) and *"no service-object layer by default"* (`models.md` §7).
    That is the more interesting result: the vanilla-Rails posture this skill has prescribed all along is
    what Basecamp actually ships, not our inference. Both now carry the citation, and §7 gains the nuance
    we lacked — *"when justified, it is fine to use services or form objects, but don't treat those as
    special artifacts"*, which is what makes the rule workable rather than a prohibition.
  - **Nothing was rejected**, and the file says so rather than implying a filter was applied.
  - **A provenance error caught by the gate before it shipped.** I was going to write that
    `rubocop-rails-omakase` is *37signals'* config. It is not: the README calls it *"the idiosyncratic
    aesthetic sensibilities of Rails' creator"*, the gemspec author is DHH, and it lives under the
    **`rails`** org. Related to fizzy's house style, not the same artifact, and not interchangeable in a
    citation.
  - **The linter cannot contradict any of this, verified rather than assumed.** `rubocop-rails-omakase`
    disables whole cop **departments** and re-enables a short list; `Style/GuardClause` is never
    mentioned, so it is off. And `Layout/IndentationConsistency` is `Enabled: false` **while carrying
    `EnforcedStyle: indented_internal_methods`** — so the indentation style §5 prescribes is
    *pre-declared* in the config we already mandate, switched off precisely for the private-only-concern
    case §5 documents.

### 1.21.0 — 2026-07-30

- **Range input and Calendar/Date/Time picker are documented** (#95). `coverage.md` **9 → 7**. Both are
  native-first, and both contracts live in `forms.md` with the other controls. Verdict on
  [#95](https://github.com/fmanimashaun/claude-skills/issues/95).
  - **The batching premise was partly refuted, and the doctrine records the asymmetry.** These were
    batched as "native control that is hard to style, so people rebuild it" — the same *question*, but
    **not one evidence source**. `input type=range` has an implicit ARIA role of **`slider`**, so the
    native element already *is* the custom widget's target. `input type=date|time` has **"No
    corresponding role"** at all ([ARIA in HTML](https://w3c.github.io/html-aria/#el-input-date)), so
    "native suffices" has to be argued on different grounds. Two rows, two citation trails.
  - **Do not hand-write slider ARIA onto a native range.** ARIA in HTML: *"No `role` other than slider,
    which is NOT RECOMMENDED"*, and *"Authors SHOULD NOT use the `aria-valuemax` or `aria-valuemin`
    attributes on `input type=range`"*. Discouraged by spec, not merely redundant.
  - **For the custom slider, only `aria-valuenow` is required** — *"Authors MUST set the aria-valuenow
    attribute"* — while `aria-valuemin`/`aria-valuemax` are *MAY*, defaulting to **0** and **100**.
    **`Home`/`End` are required keys; `Page Up`/`Page Down` are labelled "(Optional)"** in the pattern,
    so their absence is not a defect.
  - **Two documented reasons to leave native, and one that is not.** *Two thumbs* needs the separate
    **Slider (Multi-Thumb)** pattern — one `role="slider"` per thumb, each with its own name and value —
    and APG warns to test on **touch** assistive tech *"before considering incorporation into production
    systems"*. *A value a number cannot convey* needs `aria-valuetext`, which ARIA 1.2 scopes exactly
    that way and which layers onto the **native** element. **A vertical slider is not a reason** — that
    is native via `writing-mode`, and rebuilding to get one is the common mistake.
  - **Native date/time is safe because of a spec guarantee, not optimism.** For `type`, *"the
    attribute's missing value default and invalid value default are both the Text state"* — an
    unrecognised `date` keyword renders a **text input**, so the field keeps working and only the picker
    is lost. The value is a *valid date string*, **`yyyy-mm-dd` always**, whatever the display locale;
    `step` is in **days** (default 1). For time, `step` is in **seconds** (default 60), and a step not
    divisible by 60 is what surfaces a **seconds** field — that is what `step` is for here.
  - **There is NO APG "Date Picker" pattern**, and *"a date picker must be a dialog"* is **refuted**.
    The index lists 30 patterns and none is a date picker; what exists are **two examples** — one under
    **Dialog (Modal)**, one under **Combobox** — and the Dialog example links the Combobox one as a
    *"Similar example"*. Two valid architectures, neither mandated. Doctrine says "APG's date-picker
    examples", never "the pattern".
  - **`aria-selected` and `aria-current` are two claims with two sources.** APG's examples use
    `aria-selected` **only**, *"set on the cell containing the currently selected date"*, and use no
    `aria-current` anywhere. `aria-current="date"` is nonetheless spec-real — ARIA 1.2 defines the token
    as *"a date token used to indicate the current date within a calendar"*. Cited separately rather
    than blended.
  - **`role="grid"` is what the worked examples do, not a stated must** — recorded that way. And the old
    **three-spinbutton** date picker is gone from APG: it survives only as an archived 2019 Working
    Draft, so it is not doctrine.
  - **The complaints about native date pickers are ours, not the spec's.** Uneven screen-reader support
    and whether the popup is keyboard-operable are **not stated by any primary source we could find** —
    not the HTML spec, not MDN. Recorded as practitioner observation, explicitly not cited.
  - **WCAG, scoped rather than sprayed.** **1.3.5 Identify Input Purpose (AA)** applies to a date field
    only when it collects information *about the user* (`autocomplete="bday"`) — not to appointment or
    filter dates. **2.5.8 Target Size (Minimum) (AA, new in 2.2)** has a **User Agent Control**
    exception covering the native thumb and native picker, so it bites the moment you hand-build a day
    cell or a thumb. And **2.5.8 is not 2.5.5** — *Target Size (Enhanced)* is a different AAA criterion
    at 44×44, from 2.1.

- **FIX — two no-break spaces in the shipped behaviour table** (#95). `interaction-stimulus.md`'s
  Carousel row contained `role=region`+NBSP+`**or**`+NBSP+`group`, shipped in v1.39.0. It renders
  identically to a space, so the row was **unsearchable**: a reader grepping the phrase gets nothing.
  Found because an anchored edit to that row failed with *0 matches* against a string copied out of the
  file, and diagnosing it needed a byte-level diff. Now guarded — see the tooling entry.

### 1.20.0 — 2026-07-30

- **Drawer, Carousel and Image gallery/Lightbox are documented** (#95). `coverage.md` **12 → 9**. The
  batching premise **held this time**: the APG index lists **Dialog (Modal)** and **Carousel**, the
  lightbox is their composition (the shape already precedented by the Command palette), so all three drew
  on one body of evidence. Verdict on
  [#95](https://github.com/fmanimashaun/claude-skills/issues/95); sources
  [Dialog (Modal)](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/),
  [Carousel](https://www.w3.org/WAI/ARIA/apg/patterns/carousel/),
  [ARIA 1.2](https://www.w3.org/TR/wai-aria-1.2/#aria-modal) (REC, 6 June 2023).
  - **The drawer is ONE row with TWO contracts, and the old guidance was harmful applied to the wrong
    one.** `coverage.md` said *"the documented Modal, positioned to an edge — keep its focus trap"* with
    no qualifier. An **overlay** drawer is a modal dialog and must trap focus; a **persistent push**
    sidebar is **not a dialog** — it is never overlaid, so it fails APG's own definition — and must NOT
    trap focus, take `aria-modal`, or steal initial focus. **"A drawer must trap focus" is false as
    stated:** ARIA 1.2 scopes focus management to *modal* dialogs specifically. Responsive shape: render
    both and let the breakpoint choose; never toggle `aria-modal` by media query.
  - **Three carousel claims we would have got wrong.** The container is `role="region"` **or**
    `role="group"` (APG sanctions both), not `group` only. A **Tabbed** slide is `role="tabpanel"` and
    **drops `aria-roledescription`** entirely. And there are **three** variants — Basic, Tabbed, Grouped
    — not two.
  - **Most carousel machinery is conditional.** Prev/Next always; play/pause, stop-on-hover and
    stop-on-focus **only if it auto-rotates**. Auto-rotation is **WCAG 2.2.2**, not 2.3.3 — the same
    distinction the skeleton contract draws. Default: do not auto-rotate.
  - **"Slides must be `aria-hidden`" is REFUTED.** APG names no `aria-hidden` requirement and its own
    reference implementation uses `display: none`. What the pattern warns against is a slide *"displayed
    off-screen"* — still in the tree. So remove it by any mechanism; do not cite `aria-hidden` as the
    technique.
  - **Two lightbox claims are ours, and are labelled as ours.** That a lightbox is a dialog rather than a
    full-page route is a **decision** (it keeps the grid's scroll position) — no pattern covers
    lightboxes either way. So is the dialog's name string. The Dialog/Carousel keyboard models compose,
    but that is **inference from reading both normative sections**, not a citable rule, and it says so.
  - **`Ui::ModalComponent` gains `placement:`** (`:center` · `:left` · `:right` · `:bottom`) so a drawer
    is the same component at an edge — one dialog implementation, one focus trap, one `Esc`. Architecture
    decision; it replaces a call site that passed raw positioning classes through an argument the
    component never accepted.

- **FIX — `aria-modal="true"` promised background inertness the shipped code never delivered** (#95).
  `interaction-stimulus.md` stated the focus-trap mixin *"mark[s] the background inert"*, and
  `reference-implementation.md`'s `focus_trap.js` never did: it bound a Tab-cycling handler and locked
  body scroll, nothing more. Tab-cycling confines *the tab sequence* — a virtual cursor, a rotor, a
  swipe, or a click all still reached the background. ARIA 1.2 is explicit that this is worse than not
  claiming modality: *"users of those technologies will experience severe negative ramifications if a
  dialog is marked modal but does not behave as a modal for other users."* `focus_trap.js` now inerts
  background siblings.
  - **`inert` alone — not paired with `aria-hidden`.** `inert` removes the subtree from tab order,
    hit-testing **and** the accessibility tree in one attribute; adding `aria-hidden` beside it is how a
    background ends up hidden from AT while still clickable. The doctrine line said `inert`/`aria-hidden`
    as if interchangeable.
  - **Nesting-safe, because the dismissable-layer is a stack.** The trap restores only what *it* changed,
    so an inner overlay closing cannot un-inert what an outer one still needs — and the same fix applies
    to `body.overflow`, which previously unlocked scroll under a still-open outer modal.

- **FIX — `components.md` advertised a Modal `body` slot that does not exist** (#95). The component
  declares `renders_one :title` and `renders_one :actions` only; the body is block content, which is what
  both real call sites in `crud-modal-pattern.md` do. `m.with_body` raises `NoMethodError` — the #168/#182
  class exactly, surviving in **prose**, where the call-site linter cannot reach it. Found because the
  linter rejected a call site written *from that prose*.

- **FIX — the controller inventory conflated the two drawer shapes** (#95). It listed `sidebar` as
  *"drawer + collapse"*, one controller for both — which is how a persistent sidebar acquires an
  `aria-modal` and a focus trap it must never have. `sidebar` is collapse only; the overlay drawer is
  `modal`. `carousel` is added as the one new controller these rows need.

- **Loading, progress and busy state are documented — Progress bar, Skeleton, Spinner** (#95).
  `coverage.md` **15 → 12**. One `role="progressbar"` contract, one skeleton recipe, one spinner recipe,
  and the rule that decides between the last two: **is the content's size known?** Known → skeleton (it
  reserves the space, so nothing shifts); unknown → spinner.
  - **Change type: framework claim under the gate for Progress bar, architecture decision for the other
    two.** APG has **no pattern for any of the three** — the Patterns index lists 30 and none is Progress
    bar, Spinner, or Skeleton — so they are not one batch of evidence. Progress bar cites the normative
    ARIA role
    ([`progressbar`](https://www.w3.org/TR/wai-aria-1.2/#progressbar)); the other two have **no upstream
    at all** and say so in the doctrine rather than implying one. Verdict recorded on
    [#95](https://github.com/fmanimashaun/claude-skills/issues/95).
  - **Every `progressbar` value attribute is optional** — no "Required States and Properties" row exists
    for the role. `aria-valuemin` defaults to `0`, `aria-valuemax` to `100`, and **indeterminate means
    OMITTING `aria-valuenow`**, never `0` (which reads as "no progress made" — a different claim from
    "unknown"). The name is required and *From: author* only, and the role is **Children Presentational**,
    so text inside the fill `<div>` is never exposed. `ProgressComponent` raises on a blank label.
  - **`meter` must not be used for progress**, and the difference is not stylistic: `meter` *requires*
    `aria-valuenow` where `progressbar` treats it as optional. Both ARIA and APG say authors SHOULD NOT
    use `meter` to indicate progress.
  - **Reduced motion for a shimmer is WCAG 2.2.2, not 2.3.3** — 2.3.3 covers motion from *interaction*
    and a skeleton starts on load. 2.2.2 is also **conditional** (over five seconds *and* parallel
    content), so a fast skeleton may not trigger it at all. Respect the preference regardless; do not
    cite the wrong SC for it.
  - **`aria-busy` is never the only mechanism.** It is advisory — assistive tech *MAY* wait — and poorly
    supported. `aria-hidden` on the placeholder shapes is what stops forty rectangles being announced.

- **FIX — a shipped `aria-live` that could announce a price without its label** (#95). v1.38.0's Cart
  anatomy said to wrap the total in `aria-live="polite"`. Bare `aria-live` leaves `aria-atomic` at
  **false**, and then only the changed node is presented — so a total going £48.00 → £52.00 announces as
  **"52.00"**. Now `role="status"`, which carries polite **and** atomic implicitly. The Category row
  shipped in the same release already said `role="status"`, so this was internally inconsistent on
  arrival. Same fix applied to the basket count.
  - **The Toast implementation and the layout snippet disagreed with each other**, and the sweep for the
    class found it: `component-implementations.md`'s toast container had **no** `aria-live` while
    `page-anatomies.md`'s had one, and the toast element carried `role` *and* a redundant `aria-live`
    computed from the same condition. The container keeps `aria-live="polite"` (persistent and empty,
    matching the pattern MDN describes) and the toast keeps only its **role**, which already implies the
    live value.
  - **A boundary is recorded rather than filled.** Bare `aria-live` IS correct on the toast *container*,
    because `aria-atomic="false"` is what insertions want — atomic would re-announce every toast on
    screen. And no source we could find states whether inserting an element that itself carries
    `role="status"` announces on its own, so doctrine does not depend on it: the container is always
    present, and the role expresses severity. Written down so the next reader does not "simplify" it on
    the strength of an unverified negative.
  - **The Toast row carried the same shape** — `role="status" aria-live="polite"` (redundant) with
    "errors `assertive`" (which invites `aria-live="assertive"` on a `status` role). Severity picks the
    **role**: confirmation → `status`, time-critical failure → `alert`.

- **FIX — a false "(WAI-ARIA APG)" attribution over the whole behaviour table** (#95).
  `interaction-stimulus.md`'s per-component contract sat under a heading claiming APG for every row,
  including Toast, which has no pattern. Rows now state their own source — a pattern page, a role
  definition, or "composed from primitives". Same defect class as citing a keybinding no spec mandates
  (#142), applied to a heading instead of a row.

- **FIX — "33 named patterns" was wrong; the APG Patterns index lists 30** (#95). Stated twice, in
  `components.md` and in a `build_coverage.py` comment, both about the Command palette. The conclusion
  drawn from it was right (no pattern for a command palette) but the figure was not; verified against
  [the index](https://www.w3.org/WAI/ARIA/apg/patterns/). The v1.19.0 note below repeats the old figure
  and is left as the historical record.

### 1.19.0 — 2026-07-30

- **The commerce family is documented — Storefront, Category, Product, Cart, Checkout, Order detail,
  Order history** (#91). `coverage.md` **22 → 15**, and with it **all twelve page archetypes are done**:
  every remaining gap is now a *widget* needing an APG verdict, which makes the rest of the backlog one
  kind of work instead of two.
- **The a11y failures these archetypes exist to prevent are commerce-specific and expensive:**
  - **Cart quantity and total changes need a live region.** Edit a quantity and the total changes
    silently — this is the single most-missed thing in commerce accessibility, and the one with a direct
    revenue cost.
  - **A remove control must name what it removes.** An icon-only `×` announces as "button", and there
    are six of them: `aria-label="Remove Blue T-shirt, medium"`, the item rather than the row number.
  - **A discount needs two prices and a word** — `<s>` on the original plus `sr-only` "was"/"now".
    Colour and a strikethrough convey nothing to a screen reader, and red-as-cheap is not universal.
  - **Variant pickers are radios in a fieldset**, not a styled `div`, and an unavailable variant is
    disabled *and says why* ("Blue — out of stock").
  - **Stock and order status are text**, never colour alone; a progress tracker is an `<ol>` whose
    current step says so in words.
- **Checkout rules that are implementation faults rather than design choices:**
  - **Never require an account to buy** — offer guest checkout and create the account afterwards from
    data you already hold.
  - **Never lose what was typed.** Re-render every field on validation failure; losing an address is the
    most common abandonment cause that is entirely ours.
  - **A double-submitted payment must not double-charge** — disable on submit *and* make the server
    action idempotent, because the client half alone loses to a slow network and an impatient user.
  - **One column**, because multi-column forms produce ambiguous tab order and unreadable error
    association.
- **Category listing:** filters are a `GET` form that works without JavaScript (state in the URL, so
  results are shareable and back-button-correct), the result count is announced via `role="status"`, and
  pagination is the default — infinite scroll breaks the back button, strands keyboard users before the
  footer, and has no addressable position.

- **Five page archetypes documented — Landing, Pricing, About, Error, Auth** (#90). `coverage.md`
  **27 → 22**. These are page *compositions* with no ARIA pattern upstream, so the authority is the
  maintainer decision rather than a verdict — which is exactly why they were sequenced separately from
  the widget rows instead of queued behind 15 verifications.
  - **Shell assignment is doctrine, not taste.** Landing/Pricing/About/Error use the **stacked** shell —
    marketing pages are the only place it is the default rather than a choice. **Auth uses no shell at
    all**: showing app navigation to someone not signed in advertises destinations they cannot reach.
  - **Correctness points that are easy to get wrong and expensive to miss:**
    - A 404 design served with **HTTP 200 is a soft 404** — search engines index it and monitoring never
      sees the failure. Mirror image of `qa-flow`'s evidence rule, where a 200 error page is
      indistinguishable from a working one to everything except a human.
    - A **500 page must not depend on the app** — no database call, no current-user lookup, no asset the
      failed boot may not have compiled. A 500 page that itself raises produces a blank browser default.
    - **`autocomplete` tokens are a security property**, not polish: without
      `username`/`current-password`/`new-password`, password managers cannot fill or save, and people
      fall back to weaker passwords they can type.
    - Auth must **never say which credential was wrong**, and a password reset must **always report
      success** — both are account-enumeration oracles otherwise.
    - Pricing's recommended plan needs a **non-colour signal** (the badge carries the meaning), and
      comparison `✓`/`—` cells need `sr-only` words — a bare glyph is announced as nothing.
  - One `h1` per page, and every section gets an `h2` even where the design shows none — `sr-only`
    rather than a skipped level, or the page has no outline for anyone navigating by headings.

### 1.18.0 — 2026-07-30

- **Every documented component now has a worked call site — 14 of 20 had none** (#238). A class
  definition shows what a component *accepts*; it never shows how to **call** it, and inferring the
  invocation is precisely how `FieldComponent.new(form:, name:)` and `field_classes` both **shipped and
  raised** in a user's project (#168, #182). It also silently disarmed the doctrine-call-site rule: a
  component with no call site has nothing to check, so it was skipped without a word.
  - A single *Call sites* section gives the invocation for all of them, rather than scattering
    snippets — which is also how a reader actually reaches for it. Each is verified mechanically
    against its own declaration, so a signature change that misses the section now fails the gate
    instead of misleading somebody.
  - **`DropdownComponent` was never declared at all** — the section shipped an ERB template and no
    class, for as long as it has existed. So its `items:` keyword and `trigger` slot had *never* been
    checkable. Declared now; both are.
  - Two of the 14 were **nested slot components** (`Option`, `Row`), reachable only through a parent's
    setter. Demanding a standalone call site for those would demand the impossible, so they are exempt
    — and a fixture pins the exemption rather than leaving it implicit.
- **Two new rules, addable only because the work came first** (#238). `component-without-call-site` and
  `undeclared-component-call-site` both fire **zero** times today. Landing either before the 14 call
  sites existed would have produced 14 findings on day one — and per this repo's own thesis a linter
  that starts red gets suppressed, so the class stops being caught at all. Written first, gated second.
  - The ghost-reference rule exists because I **introduced one while writing the call sites**: a
    `SparklineComponent` that does not exist. `data-viz.md` declares the slot as *"optional inline
    sparkline (`<svg>`)"* and ships no such component. The doctrine-call-site rule could not catch it —
    it skips classes it cannot find, by design (#168) — so my own slip is the evidence the rule was
    missing. Probing for others then found `DropdownComponent` above.
  - Five fixtures cover both directions plus the nested exemption; two declared mutations in
    `mutation_check.py` mean neither rule can go quiet. Selftest 39 → 44, mutations 17 → 19.

- **Combobox / Autocomplete is `documented`, and Command palette becomes `derivable`** (#95) — two
  rows retired, **29 → 27**. The APG contract was verified first (verdict on #229/#95); this is the
  component that contract describes.
  - The **input** carries `role="combobox" aria-expanded aria-controls` — the role never goes on a
    wrapping div, which is the superseded ARIA 1.1 model. `aria-selected` tracks the **active** option
    because selection follows focus in a combobox, not the previously chosen value — the commonly
    inverted detail. A collapsed popup carries `hidden` as well as the ARIA state.
  - `role="listbox"` is the implicit popup default and needs no `aria-haspopup`; `grid`/`tree`/`dialog`
    must declare it and use `gridcell`/`row`/`treeitem` rather than `option`. The optional Open button
    is `tabindex="-1"` and out of the tab order, since the input already reaches the popup.
  - **Reach for a combobox on APG's two scenarios** — a closed set too long to scan, or an arbitrary
    value helped by suggestions — rather than the old option-count heuristic. Neither → native
    `<select>`.
  - Announcing "5 results available" via a live region is recorded as **our convention, not APG's**;
    the pattern never prescribes it.
  - **Command palette has no APG pattern at all** (33 patterns, none for it), so it is a composition
    rather than a gap: the documented `Modal` containing the documented `Combobox` with a listbox
    popup. `aria-activedescendant` is effectively mandatory there — the input must hold focus for
    typing to filter, so moving DOM focus into the results would break it.
- **A pre-existing false-positive generator in the call-site linter, found by writing the first call
  site that exercises it.** `renders_many :options` declares the slot as `options`, but
  ViewComponent's setter is the **singular** `with_option` — so a *correct* call site was flagged as
  an undeclared slot. It had never surfaced because no shipped call site used a `renders_many` slot;
  existing components pass collections as initializer args instead. The rule now accepts the declared
  name or a naive de-pluralisation, with a near-miss fixture proving an unrelated slot
  (`with_choice`) still fires, and a declared mutation in `mutation_check.py` so the fix cannot
  silently regress. Selftest 36 → 39.
- **And a gap in my own doctrine, found the same way.** The component shipped with no worked call
  site — so there was nothing for the guard to check *and* nothing for a reader to copy. Adding the
  call site fixed both, which is why the mutation probe was worth running on a component I had just
  written.

### 1.17.1 — 2026-07-30

- **Shipped combobox doctrine omitted a REQUIRED attribute, and attributed `Space`/typeahead to an
  editable combobox** (#229). Found by a `doctrine-verifier` run intended for two *unwritten* rows —
  it turned up errors in doctrine shipped in **v1.35.0** instead, which outrank a gap in unwritten
  doctrine.
  - **`aria-controls` was missing from the behaviour table while `forms.md` had it** — two shipped
    files contradicting each other on load-bearing wiring. ARIA 1.2 lists exactly **two** required
    states for the `combobox` role and this is one: *"Authors **MUST** set `aria-controls` on a
    combobox element to a value that refers to the combobox popup element"*
    ([ARIA 1.2 §combobox](https://www.w3.org/TR/wai-aria-1.2/#combobox), read 2026-07-30). An agent
    following the table alone emitted a non-conformant combobox. Reconciled toward `forms.md`.
  - **`Space` and typeahead are not editable-combobox behaviours.** Neither appears in APG's normative
    Keyboard Interaction section for a combobox; both come from the **select-only** variant, where
    there is no text field for `Space` to type into. In an editable combobox `Space` types a space and
    typed characters drive *filtering*, not a typeahead-jump. The list-navigation mixin claimed both
    for "listbox/combobox" wholesale, which yields a control that swallows the space bar.
  - **Both focus models are sanctioned, not just ours.** ARIA 1.2 presents moving DOM focus into the
    popup as the base case with `aria-activedescendant` as an alternative *"in lieu of"* it — and for
    a **dialog** popup activedescendant is *disallowed*. We still default to activedescendant for a
    listbox popup; it is no longer stated as the only conformant way.
  - **Required and optional keyboard bindings are now separated** rather than presented as one list:
    `↓` into the popup, `↑`/`↓` within it, `Enter` and `Esc` are required; `↑` from the input,
    `Alt+↓`/`Alt+↑`, and `Home`/`End` (listbox/grid) are optional — `Home`/`End` are required only for
    a **tree** popup, and `PageUp`/`PageDown` are absent from the listbox section entirely. Also
    recorded: `→`/`←` move the **text cursor** in an editable combobox, so treating all four arrows as
    list navigation is non-conformant.
  - **Version trap recorded — three models, not two.** ARIA 1.0 used `aria-owns`; ARIA 1.1 required a
    non-focusable wrapper owning a textbox plus popup; **ARIA 1.2** puts the role on the input with
    `aria-controls`, and states that *"a combobox following the ARIA 1.1 combobox specification will no
    longer conform"*. Our doctrine is on the current model — the note exists so nobody "corrects" it
    back from an older tutorial.
  - **`forms.md`'s "native select first" is now attributed honestly.** It is our judgement, not a
    Combobox-pattern requirement; the nearest authority is the *First Rule of ARIA Use*, whose document
    is a **W3C Discontinued Draft**. Guidance kept, citation corrected.

### 1.17.0 — 2026-07-30

- **Disclosure is now first-class doctrine — and the verifier gate stopped us shipping a fabricated
  spec citation** (#142). Disclosure is the **second most common interactive pattern after plain
  links**: 732 instances across a 72-page professional corpus, outnumbering dropdowns 73:1 and tabs
  81:1. Our doctrine gave it one word — `(toggle)` — while rarer patterns had full treatments. So the
  most frequent interactive component we lacked was also the least specified.
  - **The gate's most valuable output was negative.** The issue specified
    `ArrowUp`/`ArrowDown`/`Home`/`End` accordion navigation *"per the ARIA APG"*. Those four keys are
    **absent from the current APG Accordion pattern entirely** — its whole Keyboard Interaction
    section is Enter/Space, Tab, Shift+Tab
    ([APG Accordion](https://www.w3.org/WAI/ARIA/apg/patterns/accordion/), read 2026-07-30). **Version
    boundary:** they existed in the *2017 APG 1.1* draft example
    ([archived](https://www.w3.org/TR/2017/WD-wai-aria-practices-1.1-20170628/examples/accordion/accordion.html))
    and were deleted from both the pattern and the example since. Plausible, traceable to a real
    source, and wrong today — implemented as written it would have told every downstream agent that
    four keybindings are mandated by a spec that does not contain them. They now ship, if at all, as
    **our** enhancement, explicitly not attributed to APG.
  - **Three further corrections.** `<details>`/`<summary>` is *not* APG-endorsed (the Disclosure
    pattern never mentions it) and **cannot animate open/close at all** per
    [MDN](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/details), so it is not a
    drop-in swap. `aria-controls` is APG-**optional**, though [ARIA
    1.2](https://www.w3.org/TR/wai-aria-1.2/#aria-expanded) says the author **SHOULD** use it when the
    panel is not *owned* by the trigger — which is our sibling markup, so we emit it and cite ARIA, not
    APG. And the reduced-motion rule **cannot cite WCAG 2.3.3**, whose normative text only requires
    that animation *can be disabled*; it is reframed as implementation correctness — a state change
    must never depend on an animation event firing, or suppressing the animation breaks the control.
  - **Six requirements the issue omitted**, now in the contract: the accordion header button must be
    wrapped in a heading with `aria-level`, and that heading must contain **only** the button; a
    `role="region"` panel is optional and explicitly discouraged past **~6** simultaneously-expandable
    panels; APG distinguishes **three** accordion behaviours, not two; and `aria-expanded="false"` does
    **not** remove content from the accessibility tree ([ARIA 1.2
    §7.1](https://www.w3.org/TR/wai-aria-1.2/#exclude_elements2) MUST-excludes `hidden` /
    `display:none` / `visibility:hidden`, and `aria-expanded` is not on that list) — so state and
    hiding are two separate obligations.
  - **We ship two of APG's three behaviours**, deliberately: independent collapse and single-open
    **collapsible**. Not *always-one-expanded*, which prevents the user collapsing everything and is
    the only variant needing `aria-disabled`. Maintainer decision, recorded on #142 — no spec forbids
    it, we simply do not want it.
  - `coverage.md`: **30 → 29** `needs doctrine` rows, `documented` 40 → 41. The totality guard refused
    the flip until the row cited a real heading in the shipped docs, which is the guard working.
- **The call-site linter was blind to the form ERB actually uses** — found by mutating the new call
  site and watching nothing fire. Both render rules required `render(` **with** a paren, so
  `render Cls.new(...) do |v|` escaped slot *and* initializer-keyword checking entirely. #182 records
  fixing exactly this blind spot for the **icon** rule — *"the rule initially required parentheses, so
  it would not have caught the violation that motivated it"* — but the fix was never carried to its two
  siblings. Same class, same file, unfixed for six releases.
- **Follow-up: one of those five fixtures was itself vacuous.** Asked directly whether the two linter
  defects were fixed, I re-checked by reverting each fix and confirming a fixture failed — and the
  cross-contamination fixture **did not**. The declaration parser registers one component per fenced
  block, so two classes in a single fence left the second unregistered, its render block skipped, and
  the scenario never exercised. It passed for the wrong reason. Split into two fences; reverting the
  fix now fails it. `gate-that-cannot-fail` in the fixture added to prevent one — and it only surfaced
  because the fix was reverted rather than the fixture read.
- **And fixing that exposed a false-positive generator.** Slot uses were scanned to
  *end-of-document*, so two blocks binding the same variable — `do |d|` for a Disclosure above
  `do |d|` for a Dropdown — had the second's slots attributed to the first class, flagging **correct**
  markup. The window now ends at the next render block. Five fixtures pin all three fixes, including
  that narrowing the window still catches a bad slot inside the first block. Selftest 31 → 36.

### 1.16.1 — 2026-07-30

- **`fidara-design` told users to install a private plugin that should not exist** (#123). Its
  *Distribution* section instructed `/plugin marketplace add <org>/fidara-plugins` then
  `/plugin install fidara-ui`. That is **shipped doctrine pointing at nothing** — and it contradicted
  the just-in-time model this skill already ships under, where components are generated in the project
  from doctrine plus `coverage.md` and **nothing at build time reads a licensed kit**.
  - The instruction was written under an *inventory* model: the kit as a library agents reference
    while building. #124/#190 replaced that with **guidance, not availability** — 83 of 113 rows need
    no kit reference at all, and the remaining 30 are tracked as `needs doctrine` writing gaps.
  - Rewritten to say the skill is complete on its own and that **this is the only mode.** A
    kit-present branch would make the same prompt produce **different output depending on whether a
    licensed plugin happened to be installed** — a non-determinism nobody without the licence could
    test.
  - Adds the corollary that makes the model self-correcting: **if an agent seems to need the kit to
    build a screen, that is a defect in this skill** — a `coverage.md` row marked `derivable` that is
    really `needs doctrine` — not a missing download.
  - Records why the kits are never distributed: their licences forbid re-distributing components
    *separately from an End Product*, which is exactly what a plugin payload is. The kits inform our
    doctrine at authoring time on a maintainer machine and never travel further.
  - Full reasoning, including what was proposed and rejected, is the decision record on
    [#190](https://github.com/fmanimashaun/claude-skills/pull/190#issuecomment-5127664883). It is
    linked from here because a design decision's authority is the record, not this summary.

### 1.16.0 — 2026-07-29

- **NEW `coverage.md` — what to build, and where to use it** (#124). The component work so far came
  from **sampling**, so "is the library complete?" had no answer, and sampling cannot give one: a
  component nobody thought of is indistinguishable from one deliberately skipped. Now it is a
  **diff**, generated by `scripts/build_coverage.py` from a mechanical enumeration of the reference
  corpora — **93** Tailwind UI leaf components across `application-ui` / `marketing` / `ecommerce`,
  and Flowbite's **63** catalogue entries — reconciled against our own doctrine into 113 rows.
  - **The guarantee is the totality guard, not the file.** Every corpus entry must be claimed by
    exactly one row or **the build fails and names the stragglers**. A new upstream directory cannot
    be silently ignored, and coverage cannot rot into a stale list. Double-claims are checked
    explicitly, because a dict keyed by the reference would merge two rows silently.
  - **The axis is guidance, not availability — a maintainer decision, recorded here.** Components
    are built **just-in-time in the project** when a screen needs one; the kit ships doctrine, not a
    prebuilt library. So the file is neither a build queue nor an availability list, and nothing is
    withheld: every row is buildable on demand. A row says only how much the doctrine already tells
    you — `documented` (40, an entry defines the anatomy), `derivable` (43, the row names the
    documented parts it composes from), `needs doctrine #N` (30, an a11y/interaction contract is
    unwritten, so the row gives the nearest safe approach and the issue tracks writing the real one).
    `needs doctrine` is a gap in **writing**, not in capability.
  - Two earlier drafts were wrong and were corrected in review: a single `out of scope` bucket
    collapsed "we won't build this" with "no product need yet" — the latter is a roadmap snapshot
    masquerading as a principle — and even the `deferred`/`declined` split that replaced it still
    answered *"will we offer this?"*, which is the wrong question for a JIT kit. **Every row now
    answers how to build it and where to use it, and the builder refuses to emit a row missing
    either.** Vague defaults were deleted for the same reason: "compose it from primitives" is true
    of everything and therefore guidance for nothing, and it made that guard unable to fail.
  - **`documented` is evidenced, not asserted** — each such row cites a literal string that must
    occur in the reference docs. This caught a real wrong claim while the matrix was being written:
    `Link` was marked shipped on the strength of a Button `link` **variant**, with no standalone
    inline-link token anywhere. A wrong `documented` is precisely the dangling reference v1.26.0 had
    to fix, so it is now checkable.
  - **Corrects two facts #124 asserted**: Flowbite has **no** `Separator` (theirs is `HR`, under
    Typography) and **no** cookie-consent component. Both are pinned by tests so they cannot be
    re-added from the issue text.
  - Interaction patterns and layout primitives are enumerated separately, since neither maps
    one-to-one onto a corpus directory.
  - **Licensing boundary held** (#89): the corpora stay gitignored and unredistributed. The builder
    reads only directory *names* and emits only names plus our own prose — no markup, class list or
    asset. Without the local corpora it **refuses to run** rather than emitting a hollow file, which
    is why it is maintainer tooling in `scripts/` and only its output ships.
  - 35 selftest assertions; 13 deliberate mutations of the guards each caught, including two rounds
    where a guard turned out to have **no reachable failure path** until a fixture was added for it.

## qa-flow (independent QA plugin)

### 1.25.0 — 2026-08-08

- **The a11y-auditor cried wolf on every page of a conformant app** (Refs #578). The keyboard pass
  decided *"visible focus indicator"* by looking up a property, so a design system carrying its ring
  in `box-shadow` was reported as having none — a **blocking S1** across `/login`, `/passwords/new`
  and everything else. The reported computed style shows why a property lookup cannot work:
  `outline: rgb(0,95,204) none 1px` — a non-zero *width* with style `none`, so an outline check
  passes it and an outline-style check fails it, while the real indicator (a two-layer box-shadow
  ring) is never consulted by either.

  The spec was **internally inconsistent**, which is the actual defect: line 87 already listed
  `box-shadow` as an indicator source, and the forced-colors pass below *assumed* the keyboard pass
  honoured it — but the `No Focus Indicator` column that produces the verdict gave no method at all.
  One section promised it; the column that decides never mentioned it.

  It is now a **resting-vs-focused diff**: capture the computed style, Tab to the element, capture
  again, and treat *any* rendered difference as an indicator. That is deliberately property-agnostic
  — the next design system will carry its ring in something this list does not name.

- **The skip link was judged at rest, where a correct one is invisible by design** (Refs #578). An
  `sr-only` skip link is *supposed* to be hidden until focused, so a visibility check before Tab
  reports a working one as absent. It is now judged focused, against three questions: first stop,
  visible now, and does activating it move focus into main.

- **A blocking S1 must now show its work.** `validate_evidence.py` reports a `No Focus Indicator`
  count whose row records no diff method. It does not verify the diff was done correctly — it makes
  an unmethodical S1 impossible to file **silently**, which is the part that cost a morning. The
  forced-colors `Focus Indicator Lost` class survives unchanged and its reasoning gets sharper: in
  forced colors `box-shadow` computes to `none`, so the diff finds nothing, which is exactly the
  finding.

  Fixing the comment in `validate_evidence.py` that restated the old property-lookup model was part
  of the fix, not a tidy-up: leaving it would have replaced one internal contradiction with another.

### 1.24.1 — 2026-08-05

- **The scaffold provisioned everything the flow consumes except the labels it files with** (Refs
  #487). `qa-reporter` files every defect with `--label "qa,from-qa,severity:sN"`, and
  `gh label create` appeared **nowhere** in the plugin. `gh issue create` **errors and creates
  nothing** on an unknown label — it does not fall back to an unlabelled issue — so the first real
  defect was **lost**, not mislabelled. `setup-qa` §5 now creates them idempotently (`--force`), and
  creates **all four** severities rather than the two that appear as literals: `verify.md` files
  `severity:sN` for whatever grade the defect earned and the ladder in `qa-lead.md` runs S1–S4, so
  an S3 finding would have failed at the `gh` call. Also clarified `qa-reporter.md:40`, which
  conflated two deliberately different vocabularies — the findings **record** field is `P1`/`P2`/`P3`
  (shared with rails-flow, gated by `findings.py`), the issue **label** is `severity:s1`…`s4`.

### 1.24.0 — 2026-08-02

- **Route coverage read only the CSV evidence, so a crawled route counted as never touched**
  (Refs #108). `ROUTE_SOURCES` enumerated the validated profiles and nothing else; `crawl.json`
  and `links.json` were not read, and that omission was **nowhere stated** — which is what made
  it a defect rather than a decision. The fix is deliberately *not* to fold them into `covered`:
  a crawl loads a route and grades it for HTTP status, console errors and uncaught exceptions,
  but nothing asserts the page did its job, so counting it would be SKIP-is-not-a-PASS wearing a
  percentage — inflating the one number the tool exists to keep honest, on exactly the routes
  nobody wrote a test for. They are a **third state** instead: still a gap, flagged
  `crawled, unasserted`, carried in `--json` and the trend line, and printed **even when zero**
  so the count cannot be confused with one nobody computed. Non-GET routes are excluded — a
  crawler navigates with `page.goto`, so a GET of `/users/7` is not a visit to
  `DELETE /users/:id`; that error was caught by this change's own fixture and fixed in the code
  rather than in the expectation. 9 fixtures (61 → 70 checks), 3 declared mutations.

- **Three judges reported a shared-layout defect once per page** (Refs #108, item J — *"I
  reported 773 defects that were ~18 repeated across pages"*). `crawl_report`,
  `interaction_report` and `theme_parity` each printed one line per finding, so a broken control
  in a layout was reported as many times as there are routes. They now group on the **exact
  `(rule, detail)` pair** and print the spread: `(on 6 page(s), e.g. …)`. Exact-match is the
  point — a detail carrying per-instance counts does **not** group, because a de-duplicator that
  merges two different defects to make a shorter report is worse than no grouping at all, and
  that is the failure each judge's fixtures and declared mutations pin. `--json` still carries
  **every** occurrence, so nothing machine-readable was traded for readability. The summary line
  reports both numbers — *"2 distinct finding(s) across 7 occurrence(s)"* — because the
  occurrence count is what says a defect is systemic rather than local. Verified against a real
  six-page Chromium crawl: 7 occurrences, 2 lines, all 7 still in the JSON. The helper is
  **deliberately duplicated** across the three, which are standalone by design so an agent can
  run one file; see `quality-pass/references/worked-example.md` on extracting ten lines.

- **The "don't start a second server" guard could not fire in the case that does the damage**
  (Refs #108). The reuse probe was `curl -fsS`, and `-f` exits non-zero on 4xx/5xx — so an app
  that is **up with a failing health endpoint** was indistinguishable from an empty port (exit 22
  vs exit 7; both merely "non-zero" to an `if`). Measured, not assumed. The probe now reads
  curl's `http_code`, which is `000` only when no HTTP response arrived, so anything speaking
  HTTP is reused whatever it thinks of its own health. Booting a second server into a build
  cache the first one holds is precisely the corruption the step exists to prevent.

- **A shipped S3 rule that could never fire, because neither attribute it reads was recorded**
  (Refs #108). `functional-tester.md:171` grades `target="_blank"` without `rel="noopener"` as S3,
  and the crawl collector's link inventory recorded `href` and `text` — not `target`, not `rel`. So
  the rule was doctrine every downstream agent was told to apply against data that did not exist.
  The collector now records both as **raw attributes**, and `link_audit.py` judges them: `rel` is
  **split on whitespace**, never substring-matched, so a `noopenerfoo` typo does not pass as safe,
  and `noreferrer` satisfies the rule because it severs the same handle. Judged **before** the
  external short-circuit — an external target is precisely where a `window.opener` handle is worth
  reporting — and **after** the `mailto:`/`tel:` skip the rule itself specifies. Proven against a
  real Chromium run over a five-link page, not only fixtures: one leak reported, `noopener` and
  `noreferrer` silent, `mailto` skipped. 10 fixtures, 4 declared mutations.

- **The highest severity in our own taxonomy was the one category nothing could observe** (Refs
  #108). `functional-tester.md:95` prescribes `page.on('pageerror')` and `:105` grades an uncaught
  exception **S1** — *"the page is broken even though it rendered"* — and the collector had **zero**
  such listeners. It watched `console` and `requestfailed` only.
- **Proven against a real browser, not reasoned about.** A page whose `<h1>` renders *"Looks fine"*
  while a script throws `TypeError` was previously indistinguishable from a clean one. Now:
  collector records it, `crawl_report.py` grades `uncaught-exception`, exit 1.
- **Kept distinct from `console-error` deliberately.** An uncaught exception is not a console
  message and Chromium does not reliably surface one as such — folding them together would make the
  judge infer severity from how a log line happens to be worded.
- 4 new fixtures including the one that carries the point (a page that renders correctly *and*
  throws is not clean), plus a declared mutation that stops the rule reporting and is caught by it.

### 1.23.0 — 2026-08-02

- **The destructive-form safety rule pointed at config that did not exist** (#461). `a11y-auditor.md`
  said *"never submit a form matching **the configured** destructive pattern"*, while `setup-qa.md`
  scaffolded no `forms:` block and no script read one. Every auditor invented the list — for forms
  that delete data or take payment, where an under-inclusive guess submits a destructive form and an
  over-inclusive one silently drops coverage. `forms.destructive` is now scaffolded with a
  documented default and the doctrine names the real key.
- Third instance of a shipped reference with no referent, after #445 (a toggle nothing honoured) and
  #423 (gates waiting on paths nothing writes) — but the first where the missing thing was a
  **safety** carve-out.
- **A gate for that class was written and then withdrawn, which is the more useful record.** A rule
  refusing a dotted `group.key` no scaffolded config defines produced **6 findings, all false
  positives**: `registry.username` belongs to Kamal's `config/deploy.yml` rather than ours,
  `blast_radius.py` is a *filename* whose stem happens to match a config group, and the
  `links.check_external` prose names the removed key deliberately, to explain that it is gone. By
  this repo's own standard a rule that cries wolf gets switched off, so it is not shipped. My own
  near-miss fixture was vacuous too — it used `report.py`, where `report` is not a group, so it
  passed without exercising the filename case at all.

- **Nothing measured focus containment, and the overlay probe never ran on the commonest modal**
  (#458, the last unmechanised third of the closed #114; `Refs #108`). #114's overlay criterion is
  three assertions — *"(a) Tab cycles within the layer, (b) Escape closes it, (c) focus returns to
  the trigger"*. (b) and (c) became mechanical in `286b73a`; (a) stayed a number an agent typed
  into the `Trap Failures` column, whose arithmetic `validate_evidence.py:624` checks and whose
  truth nothing did. The collector now walks `Tab` then `Shift+Tab` from inside the open layer and
  `interaction_report.py` judges `focus-not-contained`.
- **Scoped to runtime-modal layers only, and the wording of that scope is load-bearing.** APG
  mandates containment in its
  [Dialog (Modal)](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/) pattern — *"If focus is
  on the last tabbable element inside the dialog, moves focus to the first tabbable element inside
  the dialog"* — and specifies the **opposite** for the two other overlays the Escape rule covers:
  *"Tab: … move focus out of the `menu` or `menubar`, and close all menus and submenus"*
  ([Menubar](https://www.w3.org/WAI/ARIA/apg/patterns/menubar/)) and *"DOM Focus is maintained on
  the combobox"* with the popup *"excluded from the page Tab sequence"*
  ([Combobox](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/)). Modality is read from the
  runtime — `aria-modal="true"` by **value**, or the `:modal` match that `showModal()` sets and
  `show()` never does ([HTML Standard](https://html.spec.whatwg.org/multipage/semantics-other.html#pseudo-classes)).
  Verified against the live specs on 2026-08-02.
- **An out-of-scope verdict says NOT CHECKED, never "exempt"**, and a fixture pins the wording.
  The verification's most useful output was negative: APG's Dialog (Modal) About section says
  *"Like non-modal dialogs, modal dialogs contain their tab sequence"*, so "APG exempts non-modal
  dialogs" would have been a false claim about the spec shipped as doctrine. There is no APG
  pattern page for a non-modal dialog and no runtime flag marking one — nothing to check against,
  which is a statement about measurability, not permission.
- **`a11y-auditor.md` said all three overlay assertions applied to all three patterns**, so it was
  telling auditors to file S1 `Trap Failures` against menus and comboboxes for doing what APG asks.
  Corrected with the citations: `Trap Failures` is bounded by the **modal dialogs** among
  `Overlays`, not by `Overlays`.
- **Two collector defects found by running it, not by reading it** (headless Chromium, six-case
  fixture). Both would have shipped as false results on the most common correct implementations.
  - *A dialog that is present is not a dialog that is open.* Overlays were counted by
    `querySelectorAll('dialog[open],[role="dialog"]')` — presence — so a `role="dialog"` div that
    lives in the DOM and is revealed by toggling `hidden` (Flowbite, Tailwind UI, most component
    libraries) never changed the count, and **the whole Escape / focus-restore probe never ran on
    it**. Measured: presence `3 → 3 → 3` while visibility went `0 → 1 → 0`. Now counted with
    `checkVisibility()`, and `[role="alertdialog"]` joins the selector — its omission exempted every
    confirm-before-delete overlay.
  - *`document.body` is not outside the layer.* Chromium's cycle for a `showModal()` dialog with two
    buttons is `one → two → BODY → one`; the wrap point parks focus on the document. Treating that
    as an escape would have reported a containment failure on **every correct native modal**. A
    genuinely leaky overlay lands on a real element instead — the same fixture's untrapped
    `aria-modal` div went `alpha → beta → BUTTON "open non-modal"`.
- **The probe is non-destructive**: focus returns to where it started after each direction, so the
  Escape/restore probe that runs next sees the state it would have seen. Without that, our own Tab
  presses could manufacture a `focus-restore-missing` on a working overlay.
- **False-positive guards, each with its own fixture**: a modal holding no tabbable element is
  reported unjudged rather than leaky (there is no cycle to walk); a dialog that opened without
  moving focus into itself is named as unmeasured rather than graded, because that is a *different*
  defect; an unrun walk is `null`, never `false`.
- **A denominator is printed even at zero** — *"N modal layer(s) walked for focus containment"* —
  because no findings over no walked layers is a statement about the sweep, not about the app.
- 113 selftest checks (up from 68) and 17 declared mutations, all caught. Two of the new fixtures
  had to be rewritten after the mutation checker correctly refused them: they indexed `findings[0]`,
  so the mutant crashed before any labelled assertion could report.

### 1.22.1 — 2026-08-02

- **A killed crawl produced nothing at all** (#451, the collector half of the closed #111). The
  collector accumulated every route in memory and wrote once at the end, so a run killed at route 40
  of 50 left **no file** — and was silent for its whole duration. Both were #111's original
  complaints; its agent-facing half shipped (`evidence_manifest.py`) and this half did not.
- **Measured before and after, same server, same kill point**: dev's collector produced **0 files**;
  this one leaves **4 routes recorded** plus an abort record naming the 2 unreached.
- Each route is appended to `crawl-progress.jsonl` as it completes, with one unbuffered progress line
  per route on **stderr** — stdout carries the final summary a caller may parse, and interleaving
  would make that unparseable.
- **The append file is a sidecar, not a replacement.** `crawl.json`, `interactions.json` and
  `links.json` keep their exact contracts, because three judges read them; buying crash-safety by
  changing those would trade one defect for a wider one. JSONL because a partial JSONL is still
  parseable line-by-line and a partial JSON array is not.
- **SIGINT/SIGTERM only — an uncaught exception is deliberately not handled.** That means the
  collector itself is broken, and a tidy summary would make it look like an orderly stop.
- **Not done, and not implied**: resume (`--fresh` / skip-completed). The append file makes it
  possible, but its semantics are a separate decision. Criterion 4 was already met — a route that
  throws is recorded `skipped` and the loop continues.

### 1.22.0 — 2026-08-02

- **`crawl_collector.js` silently ignored unknown flags and ran a default crawl** (#447). `--help`
  was not a flag it knew, so it **crawled** and wrote two files into the caller's working tree.
  Found by installing Playwright and actually running it — the first time this repo has been able to
  exercise the collector at all.
- **The quiet-typo case is why this is a bug and not a missing `--help`.** `--visualise` instead of
  `--visual` produced a complete, clean-looking crawl with visual capture **off**, and nothing said a
  flag had been ignored — so the run read as evidence for something it never measured. Same shape as
  #112's `ignored: []` and the `links.check_external` toggle nothing honoured.
- Accepted flags are now enumerated; anything else exits **2** naming the offender, and `--help`
  prints usage and exits 0. Exit 2 rather than 1 because a bad flag is a caller error, not a
  finding — the line every other qa-flow script draws.
- **Verified behaviourally, not by inspection**: `--help` → 0, `--visualise` → 2, neither writing a
  file, and a real two-route crawl against a live server still produces `crawl.json`,
  `interactions.json` and `links.json` that `crawl_report.py` and `link_audit.py` both accept.

- **NEW `classify_boot_failure.py`** — #110's boot-error triage was a **prose table an agent was
  told to eyeball** (`smoke.md`: *"classify it per the triage table below"*), and nothing applied it.
  The table's own paragraph makes the argument for classifying — *"a wall of stack trace is not a
  diagnosis, and the categories below have genuinely different owners"* — which is an argument for
  classifying, not for doing it by hand. Five categories, each matching signatures a runtime prints
  **verbatim**.
- **Order is fixed, not most-matches-wins**, and that is the whole difference between this and a
  keyword soup. A boot log routinely carries several signatures — a missing module often also prints
  a frame naming the runtime version — so counting matches would let incidental noise outvote the
  specific cause. Categories are tried most-specific first, first hit wins, and a fixture asserts it
  with a log containing **both**.
- **`application-error` is the fallback and that is a real answer, not a shrug.** It is the common
  case, and the one that files a bug rather than sending someone to fix their toolchain; guessing a
  more specific category on weak evidence points the reader at somebody else's problem.
- What stays judgement stays judgement: the script prints the table's **next action**, it does not
  decide it. Exit is **0 on every classification** — a non-zero code would carry no information,
  because the caller already knows the app did not boot.
- 14 selftest checks across 5 categories; 2 declared mutations — one reversing the order, one
  emptying the table — each caught by its own fixture.

- **`links.check_external` was a switch nothing was wired to** (Refs #108). The scaffolded config
  shipped it as `false` and the prose told the reader to *"enable it for a deliberate link audit"* —
  but `link_audit.py` **counts** external targets and has no code path that fetches one, so setting
  it `true` changed nothing while the documentation said otherwise. Removed, and both docs now state
  what the tool does: external targets are counted, never fetched, and there is no switch. If
  fetching is built, the switch returns **with** the code.
- **A dead toggle is worse than an absent feature**, which is why this is a fix and not a tidy-up: an
  absent feature is visible, whereas a toggle makes the reader believe they opted in and stop
  looking. Same shape as #112's `ignored: []` (advertised by the schema, hardcoded empty by the
  collector) and #423's five gates waiting on paths nothing writes.
- **New `unhonoured-config-toggle` rule** — a boolean a plugin scaffolds must be read by one of that
  plugin's own scripts. Deliberately scoped to **booleans**: a string or list key is often applied by
  an agent rather than a script (`runtime.ignore` really is honoured by `functional-tester`), so
  widening it would flag a real consumer and get the rule switched off. A boolean exists to change
  behaviour, and behaviour lives in code.
- **The rule is preventive, and its coverage counter says so honestly.** Removing the only offending
  toggle leaves **0 examined** in the live tree — the vacuous-pass shape this repo keeps finding,
  caught here by the counter itself. Four fixtures carry the whole proof, plus a mutation that
  widens it past booleans and is caught by the near-miss.
- Self-consistency selftest 105 → **117**; mutations 32 → **33**.

### 1.21.2 — 2026-08-02

- **#115's sixth criterion is now asserted rather than pointed at** (#424). *"Modal-CRUD variant
  asserts 422 re-render inside the modal"* shipped as a **pointer** at `functional-tester`, which
  never specified it — that file contains zero occurrences of `422`, `modal`, `dialog`, `CRUD` or
  `re-render`. The criterion was therefore asserted nowhere for three releases, and the doctrine it
  meant lives in a different component entirely (`crud-modal-pattern.md:146`).
- **The forms profile could not express a valid modal row at all**, which is the likeliest reason
  the criterion was never implemented: an `Exercised` row was required to be 2xx/3xx, while the
  doctrine *requires* 422 — Turbo replaces a frame only on that status. The profile refused its own
  requirement. Carve-out added, deliberately narrow: **422 only, modal only**; every other non-2xx
  is still Blocked, and a 422 row that does not declare `Surface: modal` gets no exemption.
- New `Surface` column (`page`/`modal`), because a modal form and a page form fail differently and a
  row that does not say which cannot assert either. A modal row that exercised an invalid submit
  must carry HTTP 422 **and** must not have navigated — a differing Requested/Final URL means the
  modal was destroyed and the user's input with it, which renders as a "pass" to any check that only
  asks whether an error appeared.
- Selftest **247 → 253**; three fires, three silent, including the near-miss that a **page** form may
  legitimately navigate and need not be 422. Mutations 24 → **26**, both new ones covering the rule
  and the widening of its carve-out.
- Two guards caught drift while this was written: the agent-header cross-check refused the new column
  until `a11y-auditor.md` documented it, and the stale-anchor rule caught an existing mutation whose
  anchor my edit had invalidated.

### 1.21.1 — 2026-08-02

- **Gates in `checks.json` pointed at paths nothing writes, so the validators #114–#120 shipped
  never ran in a user's repo** (#423). `project_gates.py`'s `applicability()` answers an absent
  `applies_when` path — and `expand()` an empty `{match:}` glob — with a *reason string*, never a
  failure. So a gate aimed at a directory nothing produces is **indistinguishable from a gate that
  correctly found nothing to do**, permanently. That is `gate-that-cannot-fail`, sitting in the
  manifest that registers the gates.
  - **`route-coverage` could neither fire nor pass, and both halves were real.** It waited on
    `qa/routes.json` while `route_coverage.py:377,381` default to `qa/reports/routes.json` and
    `commands/verify.md:47` writes there — nothing in the plugin produces the file it waited on.
    Fixing only the path would have turned a silent skip into an **unconditional red build**: the
    command passed no `--evidence`, so `visited_paths([])` returns `{}`, every route is a gap and
    `--fail-on-untested` returns 1 regardless of how much QA a project has done. Measured on a
    one-route fixture with one validated functional CSV — without `--evidence`: `0/1 (0%)`, exit 1;
    with `--evidence qa/manual-tests --evidence qa/reports`: `1/1 (100%)`, exit 0. Both halves moved
    together, and `--fail-on-untested` is kept: it is what makes this a gate rather than a print,
    and with the evidence dirs supplied its verdict is now about the repo instead of about the flag.
  - **`qa-evidence-manifest` could never fire.** It globbed `qa/manual-tests/manifest.json`;
    `evidence_manifest.py:147` derives the manifest beside its own append-only log, at
    `qa/reports/<run>/manifest.json`. Now `{match:qa/reports/*/manifest.json}`, `applies_when`
    `qa/reports`. #120's validator is finally run by the gate named for it.
  - **`qa-evidence` was NOT broken — the report was wrong about that one, and about the numbers.**
    The functional summary and runtime CSVs genuinely land in `qa/manual-tests/`, so the glob fires.
    What it has is a **coverage gap**, not a phantom path: `validate_evidence.py` carries **eight**
    profiles and that glob reaches **two**. The other six — a11y, keyboard, forms, emulation, perf,
    findings — are written to `qa/reports/`. (The report said seven profiles and five missed.) A new
    `qa-evidence-reports` check globs `{match:qa/reports/*.csv}` so the #114 sampling denominator,
    the #115 "no verdict on a state nobody triggered" rule and the #118 dedupe guarantee are
    enforced by the gate rather than when an agent remembers its own bash block.
  - **Two directories are kept, deliberately, against the issue's suggestion to consolidate.** They
    mean different things — `qa/manual-tests/` is the browser workspace, `qa/reports/` is where
    structured report artefacts land — and `route_coverage.py:7` has documented reading both since
    it shipped. Consolidating would rewrite five agents' evidence contracts and break every existing
    QA workspace to fix a manifest. The manifest is aligned to the writers instead, which is what
    the reconciliation gate below can then hold true.
  - **The prose that misled the manifest is fixed too**, because that class travels in groups:
    `link_audit.py:13` and `commands/crawl.md:3,39,75` all named `qa/routes.json`, a file
    `route_coverage.py enumerate` has never written.

### 1.21.0 — 2026-08-01

- **Broken links and missing assets are caught now** (#108, epic item E — *"classic, cheap,
  currently absent"*). Everything the crawl added in 1.17.0–1.18.0 judges the routes **you listed**.
  Nothing looked at what those pages link **to**, so a footer link to `/pricng` was invisible by
  construction: the typo is not in `qa/routes.json`, so it is never crawled, never judged, never
  reported. `crawl_collector.js --links` inventories every `href`, every fragment target and every
  4xx/5xx sub-resource, then probes each distinct same-origin target **once** — and
  `link_audit.py` judges it.
  - **This pays for a carve-out that had no owner.** `interaction_report.py` exempts `a[href]` from
    `dead-control` because "navigation IS its effect; a crawl that stays on the page cannot observe
    it" — correct, and it left every link on the site judged by *nothing*. The exclusion is only
    safe once something else owns link targets.
  - **A 404 sub-resource is not a failed request**, which is why `crawl.json`'s `failedRequests` did
    not already cover it: Playwright fires `requestfailed` for network-level failures only — *"HTTP
    error responses, such as 404 or 503, are still successful responses from HTTP standpoint, so
    request will complete with `requestfinished`"*
    ([playwright.dev/docs/api/class-request](https://playwright.dev/docs/api/class-request)). A
    `<img>` returning a well-formed 404 passes every status check written. Responses are therefore
    recorded by status, a different mechanism rather than a duplicate one.
  - **401 and 403 are `unverified`, not broken.** The crawl is unauthenticated, so an auth-gated
    target is *unknown*; reporting every one as a dead link is how the rule gets switched off within
    a day, taking every genuine 404 with it. Same for a target no probe reached. Neither is a
    finding and neither is a pass — both are named on every run. The carve-out is pinned to exactly
    `{401, 403}` by a near-miss: a 410 is still a broken link.
  - **`#` and `#top` are silent; `#topic` is not.** Both of the first two are the top of the
    document with no matching element required, per the HTML Standard's *scroll to the fragment*
    ([html.spec.whatwg.org](https://html.spec.whatwg.org/multipage/browsing-the-web.html)) — matched
    case-insensitively and **in full**, so a carve-out on three letters cannot swallow every dead
    fragment beginning with them. `id` and `a[name]` both count as targets, also per the spec.
  - **The scheme is read from the start of the `href`, never as a substring** — so
    `/contact?to=mailto:x@y` is an ordinary internal link and is still judged. That near-miss caught
    a real case on the first live run.
  - **One broken target is one finding** (#118), with a page count and up to three example routes.
    The count is **distinct pages, not occurrences**: a real run recorded the same missing image
    eight times for one page, because the interaction sweep navigates away and back and each return
    re-requests it. "8×" for a one-page defect is #118's inflated arithmetic in miniature.
  - **An inventory with no `base` origin is refused, not judged.** Without it nothing can tell an
    internal link from a third-party one, and the failure would be *silent*: every external link
    degrades to "unverified" and the report fills with noise. Same for an inventory with no pages
    or with no link recorded at all — a collector that inventoried nothing reports zero broken links
    for the same reason a healthy site does.
  - 69 fixtures, 8 declared mutations all caught, registered in `GATES` and in `checks.json` so it
    runs at a project's `dev → main`.

- **FIX — the crawl collector could not launch a browser at all, and `--links` found it** (#356
  regressed). The fix for #356 resolved Playwright's path from the project correctly and then
  `await import()`ed it as ESM. `playwright/index.js` is CommonJS, so Node infers its named exports
  with cjs-module-lexer, and for this package that inference is wrong: the namespace it produces is
  `clientEventEmitter, default, getPlaywrightVersion, … utils` — **no `chromium`**, which lives on
  `.default`. The destructure bound `undefined`, the `try` caught nothing because the import
  *succeeded*, and the script died 60 lines later on `chromium.launch()`. It is now the synchronous
  `projectRequire('playwright')`, with an explicit exit-2 if the browser is still absent so the
  symptom is never again an unrelated `TypeError`.
  - **The documented invocation was unrunnable for the second release running**, and the reason is
    the one 1.19.1 already wrote down: the collector holds no rule, so nothing tests it, so nobody
    ran it. Found in ten seconds by pointing it at a real server, which is the only thing that ever
    finds this.
  - Also fixed while there: `responses` was attributed to the wrong routes. The listener stayed
    attached through the interaction sweep, whose force-clicks navigate away and back, so one page's
    missing image was reported against three routes — our own driving reported as the app's defect.
    It is detached before the sweep, and `responses` now means "what the page load asked for".
- **`theme_parity.compare()` walked the whole light-side element list once per dark element**
  (#360). The membership test was a set comprehension written *inside* the loop, and it does not
  depend on the loop variable — so a page's elements were re-scanned for every one of a page's
  elements, on a rule whose entire input is a page of elements. Hoisted; behaviour identical, and
  the existing `an element present only in dark fires` fixture covers the branch unchanged.
  - It survived a correctness review because it is **not incorrect**, which is precisely the
    argument for having an `efficiency` dimension at all. Found by the new `quality-pass` skill's
    detection rule for it: *read every loop body for expressions containing no loop variable.*
- **Computed blast radius** (#134): `plugins/qa-flow/scripts/blast_radius.py` derives the
  regression scope from the change instead of reasoning it out. `/qa-flow:verify` Phase 2 and
  `qa-lead` now take its output as the mechanical floor, and every inclusion prints **the edge that
  justified it** — an unexplained scope list is a different guess, not a derivation.
  - **Tier 3, deterministic** (`docs/harness-doctrine.md` §1/§10): a script with an exit code, not
    an instruction an agent may reinterpret. It is a **check, not a hook**, so the advisory-vs-gate
    question does not arise; the ladder in §4 is walked in full — both-direction selftest, a
    declared mutation per rule, registered in `GATES`, and three states where a skip is not a pass.
  - **Change type: architecture (our own design), not a framework claim.** No `doctrine-verifier`
    verdict was sought and none applies: the artefact shapes it consumes (`{nodes, edges, flows}`,
    `routes.json`) are ours, and the risk axes it enforces are quoted verbatim from
    `/qa-flow:verify`'s existing rule rather than invented. The one external claim it leans on —
    Rails' `app/…` layout and `spec/…`/`test/…` naming — is *reused*, not extended.
  - **A consumer, not a second extractor** (issue thread, maintainer decision). It reverse-walks
    the graph `/rails-flow:graph` already emits: `radius(node) = { e.from : e.to == node }`,
    transitively to `--depth`. One uniform edge direction (subject → object) is what makes an
    incoming edge mean exactly "who depends on this".
  - **Not `findings.py`'s graph, deliberately.** v1.54.0's records form a graph over *defects*
    (`caused_by`/`blocks` between findings, for fix order). Blast radius is a graph over *code*
    (files/nodes/edges, for test scope). Same idea, disjoint node types — folding one into the
    other would have meant inventing a synthetic finding per source file, which is a category
    error, not reuse.
  - **The convention fallback ships and works with no graph tool installed**, on any Rails
    project: model → its specs and its conventional controller, controller → its routes and
    request/system specs, view → its action, migration → its table. When the graph is present but
    has never heard of a changed file, conventions still cover it and the report says which
    derivation accounted for each file — a graph that never indexed a file must not make it
    invisible.
  - **Integrates with the route table (#119) rather than re-deriving routes.** Route names come
    from `qa/reports/routes.json` in both modes; a route the graph names and the table does not is
    **flagged** rather than silently accepted.
  - **The five risk axes are enforced, not advised.** auth · tenancy · money · migration ·
    shared-concern force the wide selection and exit 1 ("present for approval"), which is what
    `/qa-flow:verify` already promised in prose and nothing made true. `qa.config.yml`'s
    `blast_radius.high_risk` is **additive only** — a key that could empty an axis would make a
    non-negotiable configurable, and a fixture pins that declaring `migration: []` changes nothing.
  - **Why this guesses at risk where `route_coverage.py` refuses to guess at auth.** The direction
    of the error differs: over-crediting coverage fails unsafe (it retires the question),
    over-including a risk axis fails safe (it widens scope and asks). Every hit prints the pattern
    that fired it. The `authenticated` graph tag is deliberately *not* a signal — Rails 8's
    generated auth is opt-out, so it is the default state of every controller, and a classifier
    that always fires is one a team switches off.
  - **A floor, never a ceiling.** The extractor is regex-based, so metaprogrammed structure is
    invisible to it; the graph's own `notes` are reprinted in the report and the rule is printed on
    every run. Enrichment edges from `graphify`/`code-review-graph` are included and **labelled
    with the tool**, `--no-enrichment` reproduces a bare-runner walk, and a fixture pins that the
    **verdict is identical either way** — so a machine-local tool can never make CI and a laptop
    disagree about whether to stop.
  - **Nothing narrows silently.** Depth-cutoff drops, non-app files, declared exclusions,
    conventional spec paths that do not exist, and the Minitest-vs-RSpec narrowing (observed from
    which directory exists, not guessed) are each printed with a reason — including when the list
    is empty.
  - Exit codes 0 clean · 1 findings · 2 unusable, **72 selftest checks** across both directions and
    **20 declared mutations** in `scripts/mutation_check.py`, all caught. Registered as the
    `qa-flow blast radius` gate. Deliberately **not** in `plugins/qa-flow/checks.json`: its input is
    a per-run diff, not a committed artefact, and a project gate that goes red because a PR touched
    a migration is a gate a team turns off.
- **Focus restore is measured now, not claimed** (#105, criterion 4's second half). Criterion 4 reads
  *"flags dead controls **+ missing focus restore**"*; only the first half shipped in 1.17.0, and the
  omission was not noted anywhere. `crawl_collector.js` now presses **Escape** on a layer it just
  opened and records whether the layer closed and whether `document.activeElement` **is** the trigger
  element — identity, not a selector match. `interaction_report.py` judges it as
  `focus-restore-missing`.
  - **It is the measured half of something already reported.** `a11y-auditor` counts
    `Restore Failures` per overlay in its CSV and `validate_evidence.py`'s keyboard profile gates that
    CSV's *arithmetic* — but the number in the column is the agent's own claim and nothing compares it
    to a browser. That is the claims-vs-enforcement shape this repo warns about, sitting inside the
    a11y pass. This asks the DOM.
  - **The narrow scope is the whole design, and it contradicts the issue text.** #105 asked for a rule
    on anything whose trigger flips `aria-expanded`. Verified against the live WAI-ARIA APG
    (2026-08-01), that is wrong: focus-return-on-Escape is mandated for
    [Dialog (Modal)](https://www.w3.org/WAI/ARIA/apg/patterns/dialog-modal/) (*"When a dialog closes,
    focus returns to the element that invoked the dialog"*),
    [Menu/Menubar](https://www.w3.org/WAI/ARIA/apg/patterns/menu/) (*"Escape: Close the menu that
    contains focus and return focus to the element or context … from which the menu was opened"*) and
    [Combobox](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/) (*"Escape: Closes the popup and
    returns focus to the combobox"*) — and is **absent entirely** from the base
    [Disclosure](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/) pattern, whose Keyboard
    Interaction table has no `Escape` row, and from
    [Listbox](https://www.w3.org/WAI/ARIA/apg/patterns/listbox/), which never mentions Escape. So the
    rule as the issue described it would have flagged **every FAQ accordion and every listbox** against
    APG's own spec. Those are measured, printed *out of scope* by name, and never counted — with the
    negative fixtures and a declared mutation that removes the scope guard.
  - **The trigger's role is the discriminator, not the popup's.** A plain button controlling a listbox
    is a standalone listbox (exempt); the same popup under `role="combobox"` is in scope. Fixtured as a
    near-miss pair, because keying off the popup alone silently loses the combobox case.
  - `closedOnEscape`/`focusRestored` are **`null` when the probe did not complete**, never `false` — an
    overlay whose dismissal could not be observed is named, exactly like a control that was never
    clicked, and is not a pass.
  - The dismissal is judged **before** the `dead-control` exclusions: a link's *navigation* is
    unobservable from a sweep that stays on the page, but the dialog it opened is entirely observable.
    A declared mutation reorders the two.
- **FIX — `a11y-auditor` told agents to demand `Escape` of every "overlay", undefined** (#105). The
  same over-broad claim the rule above refuses, sitting in shipped doctrine an agent follows verbatim:
  *"per overlay, assert the three individually … `Escape` closes it, focus returns to the trigger"*
  with no definition of *overlay*, so an FAQ accordion counts, inflating the `Overlays` denominator and
  filing `S1`s against behaviour APG does not require. Found by grepping for the pattern after the
  judge's scope was settled — one instance of a contradiction travels in groups. The column is now
  scoped to the same three patterns, with the same citations, and says so.
- **FIX — the qa-flow browser collector had no syntax gate, and the obvious one cannot fail.**
  `crawl_collector.js` is a shipped `.js` file an agent runs in a user's project;
  `lint_markdown_code.py` only reads fenced blocks, so nothing checked it. Worse, **`node --check
  <file>` exits 0 on an ES module with a blatant syntax error** (verified on Node 24:
  `import x from "y"; const = ;` passes) — it is detected as ESM and the check silently does nothing,
  so a gate written the obvious way would have passed on anything. `interaction_report.py
  --check-collector` feeds the source in on **stdin with `--input-type=module`**, is registered in
  `GATES`, SKIPs loudly when `node` is absent, and carries its own negative test plus a mutation that
  makes it always-succeed.
- **Visual regression: the two acceptance criteria 1.19.0 did not actually meet** (#112). The issue
  asked for five things and shipped three. Re-verified by running each, not by reading the code.
  - **Ignore regions were decoration, not a feature.** `ignored` was in the schema from day one,
    `--schema` advertised `["[data-testid=clock]"]` to users, the collector emitted a hardcoded `[]`
    and **nothing read it** — so the tolerance story was configurable and the ignore-region story was
    a field name. Now: `visual.ignore` (global) and `visual.ignore_per_route` in `qa.config.yml`,
    resolved by `visual_baseline.py --masks` and applied by the collector through Playwright's
    `page.screenshot({ mask })` ([Array\<Locator\>, since v1.8; masked boxes are filled
    `#FF00FF`](https://playwright.dev/docs/api/class-page#page-screenshot)). `maskColor` is left
    unset on purpose — pinning it would impose a Playwright >=1.35 floor to change a constant that is
    already deterministic and lands identically on baseline and candidate.
  - **The mask claim is cross-checked, in both directions, or the run is refused.** A config that
    calls a clock dynamic paired with a run that never masked it produces a ratio measured over
    pixels nobody meant to compare — and the opposite, a run masking what no config asked for, hides
    a regression instead of reporting it. Declaring the field without verifying it is how it stayed
    decoration for three releases, so the fix is a comparison, not a second declaration.
  - **Every regression now names a diff image** (`qa/baselines/_diffs/…`): changed pixels magenta
    over a faded greyscale of the candidate, produced in the same browser pass that already has both
    images decoded. "31% changed" with nowhere to look is what gets answered with a tolerance bump
    instead of a fix.
  - **Two more determinism controls, both measured rather than asserted.** `deviceScaleFactor` is
    pinned to 1 (a baseline shot at 2 shares no pixel with one shot at 1 — a ~100% diff caused only
    by the reviewer's display) and `document.fonts.ready` is awaited (`networkidle` says the requests
    finished, not that the font is applied). If the font wait fails the collector **withdraws the
    claim** and the judge refuses the run, exactly as `seededData` already worked.
  - **A docstring promise nothing kept, now kept.** `read_config` said unparseable input "is reported
    rather than silently defaulted" while the reader skipped every line it did not recognise:
    `max_diff_ratio: 1e-2` was not matched by `[0-9.]+`, fell back to 0.002, and judged the run **5x
    tighter than the config asked for** with nothing printed. It is now an `Unusable` naming the file,
    line and text. Same claims-vs-enforcement shape as #151 and #161.
  - 53 selftest checks (was 29) and 7 declared mutations (was 3), all caught. The mutation gate
    earned its keep twice here: it rejected a stale anchor the moment `DETERMINISM_KEYS` replaced an
    inline tuple, and the new fixtures had to be made refusal-proof (`matched()` returns -1 rather
    than letting `Unusable` propagate) because a mutant that dies before its labelled assertion is
    not a caught mutant.

### 1.19.1 — 2026-08-01

Both of these came from the first run against a real Rails app, which is the run no fixture here
could substitute for. Both are defects in what shipped.

- **FIX — `[dead-control]` false-positived on every validated form** (#357). A submit inside a form
  with an unfilled `required` field fires **no request**: the browser blocked it, and doing nothing
  is *correct*. The judge saw only "clicked, nothing happened" and called a working button dead —
  reported from a real sign-in whose full flow was verified by hand.
  - **This is the exact failure the rule was designed around**, and it still shipped. The docstring
    says a false positive on a working button is what gets a rule switched off; sign-in, sign-up and
    every validated form would have triggered it, taking every genuine dead control down with it.
  - The collector now measures `form.checkValidity()` and the judge treats a blocked submit as an
    **exclusion**, like `disabled` — browser measures, Python judges, as everywhere else. The
    near-miss is pinned: a submit in a **valid** form is still judged, or the exclusion would gut
    the rule instead of narrowing it.
- **FIX — the documented invocation could not run at all** (#356). `crawl_collector.js` is ESM, so
  `import 'playwright'` walks `node_modules` from the **script's** location — the plugin cache — not
  the project. It failed with `ERR_MODULE_NOT_FOUND` with Playwright plainly installed, and
  `NODE_PATH` has no effect on ESM. The only workaround was copying the file into the project.
  - Playwright is now resolved via `createRequire` anchored at the working directory, and a failure
    **names the directory it looked in** and the command to fix it, because "cannot find package"
    when the package is right there is a bewildering thing to be told.
  - **Third defect this week of the same shape: the thing tested and the thing shipped were
    different files.** The judges were exercised against fixtures; the collector was never once run
    from its installed location.

### 1.19.0 — 2026-08-01

- **Visual regression baselines** (#112). The audit produced 359 screenshots and had nothing to
  compare them to; capturing evidence is not regression testing, and the comparison is the product.
  - **Four states, and the third is the one the issue asked for.** A screen with **no baseline** is
    `new` — *neither a pass nor a failure*. As a pass, a brand-new screen is "visually correct" the
    day it is written when nothing has been reviewed; as a failure, every new screen breaks the build
    until someone raises the tolerance to zero effect.
  - **Nothing can promote a baseline.** The judging path has no write call at all, asserted against
    the module's own source — an agent that can overwrite a baseline can launder a regression into
    the new truth in one run. The check is scoped to the judging path, because the selftest writes
    fixtures and must; including it made the assertion fire on correct code.
  - **`--seeded` is the caller's assertion, not the tool's.** The collector freezes motion and the
    clock itself, but it **cannot** seed the app's fixtures — so claiming `seededData: true`
    unconditionally would have been a lie that lets a run with live data be judged pixel-for-pixel.
    It defaults to **false** and the judge refuses, which is right for a caller who has not said the
    data is fixed.
  - Diffs are computed **in the browser**, where a canvas already exists: decoding PNGs in Python
    would put a third-party image library inside a gate. Size differences count as changed pixels
    rather than being cropped away silently.
  - **A fixture that proved nothing, caught by mutation.** The longest-prefix tolerance test declared
    the *shorter* pattern first, so "last match wins" and "longest match wins" gave the same answer —
    the mutation removing the length comparison **survived** until the fixture was reordered.

### 1.18.0 — 2026-08-01

- **The three judges shipped in 1.17.0 now have something that feeds them** (#105). They landed with
  a `--schema` and **no collector** — usable in principle and unusable in practice, which is a gap
  worth naming rather than glossing: a judge nobody can feed is a judge nobody runs.
  - **`crawl_collector.js`** produces both documents in one pass, and **measures only**: it cannot be
    unit-tested without a browser, so it holds no rule. A rule there would be a rule with no fixture
    and no mutation guard. It records facts; the Python argues about them.
  - **`/qa-flow:crawl`** wires it up, reads the project's own `app:` block rather than inventing a
    boot command, and takes routes from `qa/routes.json` — crawling a hand-typed list is how a route
    nobody remembered stays untested forever. It performs **no git operations**.
  - **A collector and its judge are separate files in separate languages, so nothing stopped them
    drifting.** Both judges now cross-check the shipped collector against their own schema, including
    every effect kind — a collector that quietly stops emitting a field would make the rule reading
    it go **silent rather than fail**. Proven by renaming `h1` to `h1x` and watching the selftest
    catch it.
  - Two false positives in that check were fixed before it shipped: object **shorthand** (`{ route }`
    is `route: route`) had to count, and the effect-kind check was stricter than the field check
    beside it for no reason.
  - **The command says what it does not do, and where each thing lives instead** — layout and tap
    targets to `rendered_conformance.py`, a11y to `a11y-auditor`, coverage to `route_coverage.py`.
    That list is the duplicate-mechanism guard written down where the next author will read it.

### 1.17.0 — 2026-08-01

- **Dead controls are caught now** (#105, criterion 4). Everything nearby judges a control by how it
  **looks** — `icon-only-unnamed` wants a name, `focus-ring-missing` wants a focus style,
  `aria-controls-no-expanded` wants the state attribute. A control can satisfy all three and **still
  do nothing when clicked**: a button whose Stimulus controller failed to register, or whose target
  selector no longer matches. Named, focusable, correctly marked up, and inert.
  - **The exclusions are the design**, because a false "dead control" on a working button is the
    finding that gets a rule switched off. A `disabled` control doing nothing is *correct*; a link
    with an `href` navigates, which a sweep staying on the page cannot observe, and flagging it would
    put every link on the site in the report. An anchor **without** an href is still judged — it
    navigates nowhere, and is exactly the dead control worth catching.
  - What counts as an effect is deliberately broad — DOM mutation, navigation, a request, a focus
    move, an ARIA state flip, a dialog opening. A declared mutation drops one of those and proves a
    working control then reports dead.
  - **A control that was never activated is not a working control** — named every run, never counted
    as passing.
  - **Three defects in my own fixtures, all caught by mutation rather than reading.** The effect-kind
    fixture looped over `EFFECT_KEYS` itself, so removing a key deleted the assertion that would have
    named it — a fixture derived from its subject cannot witness that subject shrinking; it is a
    literal list now. And an unguarded `[0]` made the mutant **crash** before any labelled assertion
    reported, which the checker correctly refused as a coincidental catch: a crash is not a verdict.

- **Theme-only failures are caught now** (#105, criterion 3). Every other rule in this toolchain
  judges **one** rendering, so a theme-only defect is invisible to all of them by construction: each
  snapshot is individually conformant, and the defect is the *difference*.
  - The failure it is really for is **text that disappears in dark mode** — a hardcoded colour, or a
    role token used for text against a surface that inverts underneath it. In light it is a
    paragraph; in dark it is the same colour as its background. Nothing reading a single snapshot can
    see that, because in each one the element is just "some colour on some colour".
  - **It consumes design-flow's snapshot and does not re-run its rules** — the decision made when
    #105 was re-scoped. Re-implementing `tap-target-small` here would be a second rule with a second
    owner, drifting from the first. The snapshot is data; the rules stay where they live.
  - **The XOR is the whole rule.** A page equally bad in *both* themes is `rendered_conformance.py`'s
    finding, not a parity failure — reporting it here would double-count, and the declared mutation
    that turns the XOR into an `or` proves the distinction is real rather than incidental.
  - `colour-frozen` fires only when a colour is identical across themes **and the surroundings
    inverted**: a brand mark is legitimately fixed, so sameness alone is not a signal. A translucent
    colour is **refused** rather than composited into an invented ratio. Two snapshots of the same
    theme are refused outright — they always agree, so they would report parity while testing nothing.

- **A route crawl is judged now — and the case it exists for is the 200** (#105, criterion 1).
  qa-flow could enumerate routes (#119) and capture console errors per page (#109); design-flow could
  judge a *rendered* page against the design system (#107). **Nothing judged which routes are
  broken.**
  - A non-2xx is caught by anything, including a curl loop. **A Rails app that rescues an exception
    and renders its 500 template with a 200 status is the failure that survives every status check
    ever written** — and it is the normal shape of an error page behind a `rescue_from`. Status is
    necessary and not sufficient: a page is a finding when it *renders* like an error, and when it
    logs one.
  - **The near-misses are what make it survivable.** A page *about* errors is not an error page, so
    markers are anchored to the shapes frameworks actually render and matched against the title and
    H1 only — "Error handling guide" and "Error budget report" stay silent, and are fixtured that
    way. Console **warnings** are excluded for the same reason: noise in every real app, and a rule
    firing on all of them is a rule nobody reads.
  - **An unreachable route is not a passing route**, and an unusable crawl file is not a clean crawl.
    Both named every run. An empty crawl reporting zero findings would be indistinguishable from a
    healthy app.
  - Registered with `project_gates.py`, so it runs at a project's `dev → main`. 23 selftest checks,
    3 mutations all caught, including the 200-but-error rule going quiet.

### 1.16.0 — 2026-08-01

- **qa-flow's checks are runnable as a gate in a user's CI** (#334). A `checks.json` registers
  evidence validation, the manifest check and route coverage with `project_gates.py`, so they run
  at the project's `dev → main` instead of when an agent remembers. `route-coverage` declares
  `--fail-on-untested`, without which it reports and exits 0 — a gate that cannot fail.
  `rendered_conformance` is deliberately **not** registered: it needs Playwright, and a gate that
  quietly skips for a missing browser is worse than no gate.

### 1.15.1 — 2026-08-01

- **FIX — a bare doc pointer is invisible to the lint.** `a11y-auditor` cited `fidara-design`'s
  `references/motion.md`; readable, but not in the form `lint_self_consistency.py` validates. Now a
  full path, so a rename of the target fails a gate instead of rotting silently.

### 1.15.0 — 2026-08-01

- **Every plugin agent's model pin is now a decision with a named proof** (#299). #127 found that
  rails-flow's agents pinned `sonnet`, which is a **cap**: frontmatter resolves above the session
  model, so a user who deliberately started an Opus session got a Sonnet reviewer. That fix stopped
  at one plugin. The same defect sat in **fifteen more agents** across qa-flow, design-flow and
  pipeline — the `code-review` skill's own rule that a contradiction travels in groups.
  - **19 `inherit`, 6 `haiku`, zero `sonnet`, zero expensive aliases** across all 25 plugin agents.
  - **One checker, four tables.** `check_handoff.py`'s markers were hardcoded to `rails-flow:tiers:*`;
    they now match `<!-- <plugin>:tiers:begin -->` for any plugin. The issue floated a per-plugin copy
    instead — that would be four sources of truth for one contract, the second-source-of-truth failure
    this module's own comments warn against. A **half-renamed** block (opens `qa-flow`, closes
    `rails-flow`) is refused rather than reconciled against the wrong plugin's agents: that failure is
    *created* by the parameterisation, so it gets its own fixture. Selftest 78 → **80**.
  - **qa-flow legitimately keeps more cheap pins**, and this is the interesting decision rather than
    an oversight. Its outputs are artefacts a script can **reject** — `validate_evidence.py` grades
    a11y and performance rows, `evidence_manifest.py` grades the report — so the model cannot mark its
    own homework. Each `haiku` row names that grader, and an empty proof cell is a hard error.
  - **design-flow keeps none, despite owning three linters** — the distinction the whole table turns
    on. Those scripts grade the **artefact**, not the agent: `rendered_conformance.py` judges a
    rendered page against 11 rules and says nothing about whether `design-auditor` weighed a
    deliberate deviation correctly. Noted there that rails-flow's table lists a *different, narrower*
    agent of the same name as mechanical — same name, different contract.
  - **pipeline keeps none**: it ships no deterministic scripts at all, and `kamal-configurator`
    performs autonomous production deploys — the last agent that should be capped below the model a
    user chose.
  - **Four reconciliation gates added to `--gates`**, because a table nothing enforces is the exact
    state #127 found. Both failure modes proven on purpose: an agent drifting off its row, and an
    agent pinning `opus`. Each exits 1.


### 1.14.0 — 2026-07-31

- **Client-side performance is captured during the crawl, and none of it can reach S1** (#117). `perf-tester` measured server capacity with k6 and nothing measured what a user
  experiences, though the harness already loads every route in a real browser. The new `perf`
  evidence profile does — one row per route, LCP / CLS / TTFB / transfer bytes / request count —
  but every load-bearing decision in it came from verification that contradicted the issue.
  - **The blind spots here do not leave a blank; they return a plausible number.** That is what
    separates this profile from the other six. An unexercised keyboard walk leaves an empty cell;
    an unexercised CLS capture writes **`0`**, and a byte total summed from an API that reports
    nothing for cross-origin assets writes a small, credible figure. Both read exactly like clean
    measurements, so the profile's rules are aimed at fabricated numbers rather than missing ones.
  - **Engine support is per metric, and the obvious blanket rule would have shipped stale.**
    Verified against MDN browser-compat-data: `largest-contentful-paint` reached **Firefox 122**
    (Jan 2024) and **Safari 26.2** ([Dec 2025](https://webkit.org/blog/17640/webkit-features-for-safari-26-2/)),
    so "LCP is Chromium-only" — true until eight months ago, and what this change assumed at the
    outset — is now wrong. `layout-shift` is still `version_added: false` in both engines
    ([bug 1651528](https://bugzilla.mozilla.org/show_bug.cgi?id=1651528) open), and
    `renderBlockingStatus` is [Chromium 107+ only](https://www.w3.org/TR/resource-timing/#dom-performanceresourcetiming-renderblockingstatus).
    So `LCP ms` is required on **every** engine while `CLS`, `CLS Budget` and `Render Blocking`
    must be **blank** off chromium — a `0` there reports a perfectly stable page from an API that
    does not exist. Same direction as #116's forced-colors ceiling: false *confidence*.
  - **The interaction probe the issue proposed would have corrupted the metrics beside it.**
    Playwright's `locator.click()` drives the real input pipeline, so `isTrusted` is true — and a
    trusted input **terminates LCP observation**
    ([LCP spec](https://w3c.github.io/largest-contentful-paint/)), while shifts within **500 ms**
    of input carry `hadRecentInput` and are excluded from CLS
    ([layout-instability](https://github.com/WICG/layout-instability#recent-input-exclusion)). The
    probe therefore gets its own visit and `same-visit` is rejected. It is also **not** called INP:
    INP is a whole-visit field metric, and Lighthouse scores **TBT at 30%** in lab precisely
    because INP cannot be measured there.
  - **`transferSize` cannot carry a byte budget.** Per
    [Resource Timing §3.5.1](https://www.w3.org/TR/resource-timing/#dfn-timing-allow-check) it is
    **0** for a cross-origin resource with no `Timing-Allow-Origin`, **0** for a cache hit, and a
    fixed constant **300** for a 304 — so a page pulling 30 CDN assets passes any budget by
    measuring almost nothing. Doctrine moves to Playwright's
    [`Request.sizes()`](https://playwright.dev/docs/api/class-request#request-sizes)
    (encoded wire size, network layer, all three engines, not TAO-gated), and `Opaque Requests` is
    the column that proves which instrument ran: a `0 Oversized Requests` verdict alongside opaque
    requests is rejected as a clean verdict over bytes nobody measured.
  - **Severity is capped at S2 — the recompute's third direction.** No WCAG criterion and no
    standard of any kind mandates a performance budget (searched for, not found; the 2.5 s / 0.1
    figures are Google guidance published as revisable), so every severity here rests on a
    [maintainer decision recorded on #117](https://github.com/fmanimashaun/claude-skills/issues/117#issuecomment-5146743363)
    rather than a citation. #114/#115 stop a row grading a defect *down*, #116 stops it grading an
    advisory *up*, and this caps the ceiling. `LCP ms` and `TTFB ms` are trended and **never**
    graded; only a CLS above the budget the row itself carries, and a request over the byte budget,
    gate at S2. The cap is deliberately narrower than "perf never blocks a release" — an S2 here
    still counts against `/qa-flow:certify` like any other, and correctly so, because the two
    things that reach S2 are properties of the *page*. What can never happen is a number from an
    unthrottled dev machine being escalated into a release-breaking S1.
  - **Two corrections that silently return nothing** were also verified and written down: a webfont
    requested by `@font-face` gets `initiatorType` **`"css"`**, not `"font"`
    ([Resource Timing](https://w3c.github.io/resource-timing/#dom-performanceresourcetiming-initiatortype)),
    so the obvious filter finds no fonts at all; and `cssRules` throws `SecurityError` on a
    cross-origin stylesheet ([CSSOM](https://drafts.csswg.org/cssom-1/#dom-cssstylesheet-cssrules)),
    so font-display must be read from `document.fonts`, which is exactly where a CDN-hosted font
    stylesheet would otherwise vanish from the count.
  - Ships with 36 fixtures — 25 that must fire and **11 that must stay silent**, including LCP on
    webkit being valid so the engine rule cannot degrade into an engine ban, and opaque requests
    alongside a real oversized finding staying clean because incomplete is not false — plus 9
    declared mutations and coverage attribution wired in `route_coverage.py`. The bounds rule the emulation profile owned is now the shared
    `_check_bounds` helper — perf was its third caller, and a third textual copy would have made
    `mutation_check.py`'s existing anchor for it match twice, which that checker treats as a hard
    error rather than a pass.

### 1.13.0 — 2026-07-31

- **Emulated media conditions are tested, and most of what they find is advisory on purpose**
  (#116). Doctrine required motion to be gated on `prefers-reduced-motion` and required meaning
  never to rest on colour alone; nothing verified either, though Playwright emulates reduced
  motion, forced colors and print offline and for free. The new `emulation` evidence profile does,
  one row per route × mode — but the shape of it comes from a verification that **contradicted the
  issue on its central point**, so the change is mostly about what must *not* gate.
  - **`prefers-reduced-motion` is a Level AAA concern, so it is advisory.** [SC 2.3.3 Animation
    from Interactions](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html)
    is **AAA**, and `prefers-reduced-motion` (techniques C39/SCR40) is literally its sufficient
    technique — there is no A or AA criterion the media query satisfies. `a11y-auditor` audits to
    AA, so "this animation ignores the preference" is counted in `Motion Not Suppressed` and left
    `Severity none`, exactly as SC 2.4.13 Focus Appearance is handled in the keyboard pass. What
    *does* gate is the narrow subset [SC 2.2.2 Pause, Stop,
    Hide](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html) (**Level A**) actually
    covers: autostarting motion running **over five seconds** in parallel with other content and
    offering no way to stop it. #116 specified no severity at all, which would have defaulted this
    pass into the same gating tier as axe — wrong for nearly everything it flags.
  - **So the recompute gained the direction the other profiles leave open.** Keyboard (#114) and
    forms (#115) stop a row grading a real defect *down*; here a row may not grade an advisory
    *up*. An audit whose findings are mostly unactionable gets switched off — the same failure the
    #106 over-correction would have caused — so the AAA and no-upstream boundaries are arithmetic,
    not prose. Print gates **nothing** and the checker enforces that.
  - **A forced-colors run on WebKit is `Blocked`, never a result.** Playwright will make the media
    query report `active` in all three engines, but WebKit implements none of the *forcing* — its
    own media-query commit records that Cocoa has no concept of forced colors, and
    `forced-color-adjust` is unimplemented in Safari — so it strips no shadow and forces no system
    colour, and the pass reports **clean on an app that breaks for a real Windows high-contrast
    user**. Note the direction: #114's WebKit caveat manufactures false *defects*, this one
    manufactures false *confidence*, so it is a hard rejection rather than a `Notes` requirement.
  - **The highest-value finding is a focus ring that only the forced-colors pass can see.** Per
    [CSS Color Adjustment Level 1](https://www.w3.org/TR/css-color-adjust-1/), forced colors mode
    computes `box-shadow` and `text-shadow` to **`none`**. The keyboard pass reads indicators from
    `outline-width`/`outline-style`/`box-shadow`, so a ring built from box-shadow with no outline
    passes there and genuinely vanishes here.
  - **The reduced-motion check reads `document.getAnimations()`, not computed style.** #116
    proposed asserting a trivial `animation-duration`/`transition-duration`; that instrument is
    wrong twice over — its initial value is `0s` and it exists whether or not `animation-name` is
    set, and it is entirely blind to the **Web Animations API**, so `element.animate()` and every
    library built on it go unseen. Recorded with its residual blind spot: `getAnimations()` reports
    only what is running at the instant it is called.
  - **`emulateMedia()` merges, so `emulateMedia({})` resets nothing.** Verified against the
    shipped implementation and its own test rather than the docs, whose usage example shows the
    opposite; state lives on the Page and survives navigation, so a missed reset leaks `reduce`
    into every later pass. Doctrine requires nulling every dimension explicitly, and says plainly
    that no column detects a leak.
  - **Print records print-stylesheet sanity and does not claim to find clipped content.**
    `emulateMedia({ media: 'print' })` is a real media-type switch, but a screenshot is one
    viewport-shaped render with no pagination; page-boundary clipping exists only in paginated
    output and `page.pdf()` is Headless-Chromium-only. #116 conflated the two; the counters are
    named for what they measure.
  - **No WCAG criterion covers forced-colors support or print output** — searched for and not
    found, so both are recorded as **maintainer decisions** on #116 rather than dressed in a
    citation. `Colour Only` is the exception and keeps a real one: [SC 1.4.1 Use of
    Color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html), **Level A**, the same
    criterion the forms pass already cites.
- **`qa-reporter`'s list of finding sources no longer contradicts the checker that enforces it**
  (found while working #116). The agent's prose named nine sources while `FINDING_SOURCES`
  accepted eleven: `keyboard` and `forms` shipped in v1.12.0 as sources the checker allowed and
  the doctrine denied, so an agent reading only the prose would never roll their findings up.
  Fixed, and the selftest now holds the two in step — a `claims-vs-enforcement` defect in the
  direction that silently drops data.
- **The shared severity recompute no longer explains one profile's defects in another's words.**
  `_check_severity` hardcoded the keyboard rationale, so a *forms* colour-only finding told the
  reader about "an element a keyboard user cannot reach". The rationale is now a required argument
  rather than a default, because a default is how the next profile inherits the wrong sentence
  silently.

### 1.12.0 — 2026-07-31

*(Two issues on one branch per CLAUDE.md's grouping rule. The shared mechanism is one sentence:
both add a per-page evidence profile whose verdict is **recomputed against a denominator**, so a
pass cannot report a result on surface it never exercised. Same files — `validate_evidence.py`'s
profile table, `route_coverage.py`'s attribution map, `a11y-auditor.md` — and neither is a
framework claim needing a doctrine verdict. A bullet each so the promotion closes them
separately.)*

- **A keyboard pass can no longer sample and look exhaustive** (#114). Doctrine mandates that
  every interactive element be keyboard-operable with a visible focus ring, and that overlays trap
  focus and restore it to the trigger; nothing verified any of it. The new `keyboard` evidence
  profile does, and the design is shaped by *why* the hand-rolled probe failed silently: it checked
  one button per page and produced focus evidence for **25 of 72 pages while reporting nothing
  missing**. Sampling is invisible in a per-page log without an inventory count, so the row carries
  one: every interactive element is either reached by Tab or reported unreachable, and
  `Tab Stops + Unreachable < Interactive` is a finding. Missing indicators cannot exceed the
  elements actually focused, and trap/Escape/restore failures cannot exceed the overlays opened.
  Severity is recomputed from the counters, so a row cannot talk its own grade down.
  - **`Engine` is part of the contract, because Playwright's WebKit would otherwise fabricate
    findings.** WebKit inherits the macOS default where Tab reaches text fields and lists only —
    not links or buttons — unless Full Keyboard Access is enabled (the setting behind Safari's
    *"Press Tab to highlight each item on a webpage"*). A keyboard pass run there reports every
    link as unreachable, so a WebKit unreachable count must confirm the setting in `Notes` or it is
    rejected as a platform default rather than an application defect.
    ([playwright#2114](https://github.com/microsoft/playwright/issues/2114),
    [Apple: Full Keyboard Access](https://support.apple.com/guide/mac-help/mchlc06d1059/mac))
  - **The indicator check gates on AA and no further.** [WCAG 2.2 SC 2.4.7 Focus
    Visible](https://www.w3.org/TR/WCAG22/#focus-visible) is **Level AA** — an indicator must
    exist — but [SC 2.4.13 Focus Appearance](https://www.w3.org/TR/WCAG22/#focus-appearance) is
    **Level AAA**, so its 2-CSS-px and 3:1 requirements are advisory under an AA-targeted audit and
    must not be counted as defects. (The W3C quickref rendered 2.4.13 as AA; the specification does
    not. Verified against the specification.)
  - **Why axe does not already cover this**, recorded because the obvious guess is wrong: axe runs
    *no* focus rule under the WCAG tags `a11y-auditor` targets. `tabindex` and `skip-link` are
    tagged **best-practice** and `focus-order-semantics` is best-practice/experimental, and none is
    pulled in by `wcag2a`/`wcag2aa`/`wcag21a`/`wcag21aa`/`wcag22aa`. Even with `best-practice`
    added, nothing in axe checks indicator *visibility* or focus *restoration*.
    ([axe-core rule descriptions](https://github.com/dequelabs/axe-core/blob/develop/doc/rule-descriptions.md))
  - Doctrine now says **never enumerate focus with `element.focus()`**: `:focus-visible`
    deliberately may not match programmatically-moved focus, so such a pass reports *every* element
    as having no indicator. Drive real `Tab` keypresses.
    ([MDN `:focus-visible`](https://developer.mozilla.org/en-US/docs/Web/CSS/:focus-visible))

- **A forms row can no longer carry a verdict on an error state nobody triggered** (#115). The
  audited corpus held 200+ form controls with no systematic validation testing. The new `forms`
  profile checks label association **and required-exposure** against a `Controls` denominator —
  neither may exceed it — and ties the five error-contract columns (`aria-invalid`, message link,
  announcement, value retention, colour-independence) to `Submit Mode` **in both directions**: they
  must be `Not run` unless the row actually submitted something invalid, and must not be `Not run`
  when it did. The destructive-form carve-out must name the pattern that matched, so a skipped form
  is never indistinguishable from a passing one.
  - **`aria-invalid` is checked by value, not by presence.** Its default is `false`, and an absent
    attribute, `aria-invalid=""` and `aria-invalid="false"` are all equivalent to not-invalid — so a
    pass that greps for the attribute name reports a clean contract on a form that marks nothing.
    ([MDN `aria-invalid`](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Attributes/aria-invalid))
  - A required control that is not *exposed* as required is **S2**, not S1: it still has an
    accessible name and is still operable, it merely does not announce that it is mandatory. And an
    over-grade is deliberately tolerated — the gate exists to stop a verdict being talked *down*,
    and the `runtime` profile that shares this recompute has always behaved that way. A severity
    with nothing at all behind it is still rejected. A fixture pins the asymmetry so it stays a
    decision rather than an oversight.
  - Severities follow the actual WCAG floor, which is mostly **Level A** and is why an unlabelled
    control or a colour-only error is S1 rather than a style note: 3.3.2 Labels or Instructions (A),
    4.1.2 Name, Role, Value (A), 3.3.1 Error Identification (A), 1.4.1 Use of Color (A), with 3.3.3
    Error Suggestion at AA. Whether `aria-errormessage` is exposed independently of
    `aria-invalid="true"` was **not** verified, so it is not asserted either way — the message link
    accepts `aria-describedby` or `aria-errormessage`.

Not covered, and deliberately: `fieldset`/`legend` grouping has no clean denominator to be checked
against, and the modal-CRUD **422 re-render** expectation is `functional-tester`'s contract and is
referenced there rather than restated, so there stays one copy of it. Both remain open on #115.

Both passes earn route-coverage attribution and file deduplicated findings under the new `keyboard`
and `forms` sources. Every new rule ships a fixture in both directions plus a declared mutation in
`scripts/mutation_check.py` (39 mutations, all caught). Also fixed in passing: a dead `csv` import
in `route_coverage.py`, and a `KeyError` in one of the new attribution fixtures that let an
unrelated assertion take credit for catching a dropped `ROUTE_SOURCES` entry — found because the
mutation check reported the catch as coming from the wrong fixture.

### 1.11.0 — 2026-07-30

*(Two issues on one branch per CLAUDE.md's grouping rule. The mechanism they share is specific:
#120's `manifest.json` **is** the aggregate #111 requires be derived from the append-only log.
Built separately, one writer would append per unit while another rebuilt the summary from memory
or the filesystem — and they would disagree exactly when a run died, the case both issues exist
for. A bullet each so the promotion closes them separately.)*

- **A killed browser run now leaves usable output** (#111). The audit's crawler wrote its manifest
  only after the final page, so a crash at page 70 of 72 lost everything — and one background run
  **was** stopped mid-flight, leaving **zero** usable output after ~30 minutes. `/qa-flow:certify`
  is the pre-`main` gate, so a lost run means re-running the whole certification.
  - One JSON line per unit is appended to `qa/reports/<run>/results.jsonl` as it completes, and
    `evidence_manifest.py derive` builds the aggregate **from that log and nothing else**.
  - **A truncated final line is treated as data, not corruption** — it is the signature of the very
    crash this exists to survive, so it is counted and skipped. A parser that died on it would have
    reproduced the original defect inside the tool meant to fix it. One malformed line mid-file
    costs that line only, never the other 71 units.
  - **"The run ended" and "the run covered everything" are different claims**, and a summary that
    could not tell them apart was the defect. `unreached` is listed explicitly against an
    `expected.txt` written before the run starts, and the manifest is written on abort.
  - **Resume is decided in exactly one place.** `completed` lists what to skip; `--fresh` returns an
    empty list rather than being handled by the caller, so there is no second resume rule to drift.
    A `Blocked` unit is **not** completed — otherwise a transient hang becomes a permanent hole.
  - Progress is emitted per unit with a running count, and the doctrine states plainly: **never pipe
    the run through `tail`**. Piping buffered everything until EOF in the audit, so the log showed
    nothing for the entire run and progress could only be seen by counting files on disk. A
    supervisor that cannot tell *slow* from *hung* either waits forever or kills useful work.
- **Evidence is reviewable rather than a folder of PNGs** (#120). The audit produced 359 images, 12
  of them captures of 404 pages indistinguishable by eye, and full-page captures **8050px tall**
  proving a focus ring.
  - **Capture scope is decided by purpose and enforced**: `component` / `interaction` / `a11y`
    evidence must be **clipped**; `layout` / `theme` / `visual-regression` may be full-page. A rule
    forbidding full-page everywhere would be switched off by the first legitimate
    visual-regression run, so both directions are fixtures.
  - Deterministic naming (`<route-slug>--<viewport>-<theme>[--<state>].png`) is checked, so the set
    is self-describing; a generated `index.html` groups by route with **validity visible**, and is
    dependency-free with escaped route text so it still opens years later from the filesystem.
  - **Validity is recorded per capture**, per #106 — an image from an unvalidated page is
    indistinguishable from real evidence, so it is marked rather than silently mixed in. Valid
    evidence must name the assertion it supports.
  - **Retention** keeps the last 3 runs plus any run referenced by an open defect, ordered by run
    **name** rather than mtime (opening an `index.html` changes mtime and would silently reshuffle
    what gets deleted), and **always prints what it pruned** — including when nothing was.
  - Referenced from `functional-tester`, `e2e-tester` and `a11y-auditor`, each pointing at the one
    canonical copy rather than restating it.

### 1.10.0 — 2026-07-30

- **Route coverage: qa-flow can finally answer "what has nothing ever tested?"** (#119). It drove
  from a case catalogue and a menu scope, so the most basic coverage question had no answer — and
  blast-radius selection in `/qa-flow:verify` was therefore *judgement over an unknown denominator*.
  You cannot select "affected untested routes" without knowing what the routes are.
  - `scripts/route_coverage.py enumerate` builds `qa/reports/routes.json` from a stack-native
    source: `bin/rails routes`, a `sitemap.xml`, or a filesystem-routed directory (`[slug]` →
    `:slug`, `[...rest]` → `*glob`).
  - **Coverage is attributed from the already-validated evidence CSVs**, using
    `validate_evidence.py`'s own profiles to know which columns carry a URL. So a route counts as
    covered only when a row that *passed validation* says a pass went there — coverage inherits the
    page-identity guarantees rather than trusting a second, unchecked record, and a new browser pass
    gets attribution for free.
  - **The over-credit direction is the one that matters, so it is where the tests aim.** A tool
    reporting 100% while nothing visited `/users/:id/edit` is worse than no tool, because it retires
    the question. `:id` therefore matches exactly **one** segment: a visit to `/users/42/edit` does
    **not** credit `/users/:id`, a different action. Mutating that to a greedy match trips seven
    assertions, including a trend line recording 100% coverage — the precise lie.
  - **A deduplicated findings rollup contributes no coverage at all.** Its `Example Routes` are up to
    three *examples* of a defect (#118), and counting them would credit routes nobody opened. That
    exclusion is deliberate and asserted: every evidence profile must be either credited or
    explicitly declared route-less, so a future pass cannot be silently forgotten and understate the
    gap. `Out of Scope` rows are not visits either.
  - **Nothing about authentication is inferred.** Whether a route needs auth is not guessable from
    its path, and a heuristic would be wrong on exactly the routes that matter, so it comes from
    `coverage.authenticated_prefixes`. Untested **non-GET** routes rank first, then authenticated
    ones: an untested route that changes state is the worst kind to leave uncovered.
  - **Exclusions are declared and the excluded set is always printed, even when empty** — the same
    visible-suppression rule as `runtime.ignore` and `Ignored`. A suppression that leaves no trace
    turns a coverage number into a lie.
  - A gap **exits 0**: it is the deliverable, not a failure. `--fail-on-untested` exists for a team
    that has reached full coverage and wants to hold it. Coverage per run is appended to
    `qa/reports/route-coverage-trend.jsonl`.
  - `/qa-flow:verify` Phase 2 now refreshes the inventory and reads the gap before selecting
    regression scope, so the selection is over a known set.

### 1.9.0 — 2026-07-30

*(Two issues on one branch per CLAUDE.md's grouping rule — same component, one reporting
mechanism, and #113 was unusable without #118. A bullet each so the promotion could close them
separately.)*

- **Findings are deduplicated by signature, so counts mean something** (#118). Raw per-instance
  counts were reported as defect counts, and the inflation was measured on a real interaction
  crawl: **773** "disclosure trigger without aria-expanded" and **445** "icon-only control without
  accessible name". Every instance was real; the **distinct** count for the first was about **18**
  — one navbar defect repeating across 72 pages. A developer told "773 a11y defects" disbelieves
  the report and stops reading; told "18 defects, one on every page", they fix the navbar. The same
  arithmetic decided whether `qa-reporter` filed 18 issues or 773, and its doctrine previously said
  only "one issue each".
  - `qa-reporter` now groups by `(issue type, component/DOM signature, offending attribute)` —
    explicitly **not** the raw selector, which varies per page and so defeats grouping by making
    every occurrence look distinct. It reports `N instances across M routes`, ranks by severity
    then reach, and keeps the full instance list in a JSON artefact so collapsing 773 rows
    *summarises* the data rather than destroying it.
  - **A fourth `validate_evidence.py` profile (`findings`) makes the guarantees arithmetic rather
    than stylistic.** A **repeated signature is rejected** — that *is* the dedupe, not a proxy for
    it. `Instances` can never be fewer than `Routes` (a defect appears at least once per route it
    affects, so a smaller number is an occurrence count mistaken for a distinct one). Example
    routes cannot outnumber affected routes. And the file must be **ordered** by severity then
    reach, so "ranked by impact" is true of the artifact instead of asserted about it.
  - That needed two honest extensions to the validator rather than a workaround: `Profile` gained
    `page_identity=False`, because a rollup row spans many routes and demanding one HTTP status
    would force the writer to pick an arbitrary route and call it the finding's location; and a
    `cross` hook, because whether a signature repeats is unknowable from a single row. The
    refactor was proved behaviour-neutral — the pre-existing 94 checks passed unchanged before any
    new fixture was added.
  - Dedupe applies to **every** source (a11y, links, runtime, visual, interaction, functional,
    api, perf, security), checked against a vocabulary rather than left free-text: #118 is
    explicit that this is not an a11y-only rule, that is only where it was measured.
- **Links and anchors are audited during the crawl** (#113). Nothing verified that links went
  anywhere. The audit found the value by accident: a sitemap listed **12 section-index URLs that
  all 404'd**, and it surfaced only because a human noticed "Page Not Found" in a screenshot
  folder.
  - Unique internal targets are requested **once** (HEAD, falling back to GET), `#fragment`
    targets are confirmed to exist on the destination page — a link to a renamed heading is dead
    in the way that matters to a reader *and* returns 200 — and `target="_blank"` without
    `rel="noopener"` is an S3.
  - **External checking is off by default** (`links.check_external`), cached when enabled, with
    timeouts informational rather than failing: a gate that fails because someone else's site was
    down teaches people to ignore it.
  - **The asset half was already shipped**, so this pass does not re-crawl for it — #109's `>= 400`
    and `requestfailed` capture already covers images, fonts and script chunks. #113's own text
    asked for exactly that reuse.
  - **Findings dedupe by target**, which is why these two issues shipped together: one dead link in
    a shared footer is **one** finding across seventy routes, not seventy. The link pass writes no
    per-route CSV at all — it emits rows into #118's rollup with the resolved target URL as the
    signature and the **referring** pages as the examples, which is what a developer needs to fix
    it. A link pass that emitted one row per occurrence is now rejected by the validator.

### 1.8.0 — 2026-07-30

*(Two issues, worked on one branch per CLAUDE.md's grouping rule — same component, same
boot/validation path — with a bullet each so the promotion could close them separately.)*

- **Console errors and failed requests are captured on every page, and the severity is enforced
  rather than trusted** (#109). qa-flow never looked at the browser console or the network log, so a
  route could return 200, render, satisfy its assertion and pass its case while throwing uncaught
  exceptions or 404-ing its own script bundle. A real audit hit both at once — `Module not found:
  svgmap/dist/svgMap.min.css` and a repeating `TypeError: localStorage.getItem is not a function`,
  on a route serving HTTP 200. Page validation (#106) proved you captured the *right* page; nothing
  asked whether that page then **worked**.
  - `functional-tester` and `e2e-tester` now attach `pageerror`, `console`, `requestfailed` and
    `>= 400` response listeners on every visit, writing one row per route to
    `qa/manual-tests/<date>-<slug>-runtime.csv`.
  - **A third `validate_evidence.py` profile (`runtime`) recomputes the severity from the row's own
    counters**, so the mapping cannot be talked down: an uncaught exception or a failed
    document/script/stylesheet is **S1** however the row grades itself; `console.error` and failed
    subresources are **S2**; `console.warning` never gates. That required splitting the counters by
    *consequence* rather than by event name — a single "failed requests" number cannot tell a
    missing analytics pixel from a missing application bundle.
  - **Suppression stays visible.** `runtime.ignore` in `qa/qa.config.yml` silences known
    third-party noise, because an always-red check gets switched off — but suppressed findings are
    still counted in a required `Ignored` column, even at 0. A suppression that leaves no trace is
    how a red check turns green with nobody deciding to.
  - The counters reject `none` / `n/a` / `-`: a capture recording no counts is indistinguishable
    from one where the listeners never attached. S1 requires an `Evidence` path a human can
    re-read, and any graded row requires `Notes` carrying the message and resource URL.
  - The selftest grew 72 → 94 checks. The shared page-identity rules are exercised against the new
    profile too, so it cannot silently reintroduce #106's hole on the newest artifact, and the
    existing "every profile must be documented by an agent" check **failed until the doctrine was
    written** — the gate working on my own change.
- **App boot is hardened: reuse before launch, per-route timeouts, and classified failures**
  (#110). Booting the two audited bundles needed several manual interventions `/qa-flow:smoke`
  would have failed on.
  - **Reuse before launch.** The port is probed first; if the app already answers it is reused and
    reported, and **never** torn down (it is not ours to kill, and it may be running different code
    than the working tree). Two dev servers against one project directory contend over the same
    build cache and can corrupt it.
  - **`route_timeout` is now separate from `boot_timeout`**, documented as distinct in the `app:`
    schema. A Next.js + Turbopack app reported "Ready in 10s" then spent **45–60s compiling each
    route on first visit**; with one timeout covering both, the crawl clears boot and dies on route
    2, which reads as a broken app rather than a slow compile. A route timeout is now reported as a
    route failure, distinct from a boot failure.
  - **Boot failures are classified** — port in use, missing/incompatible dependency, runtime/engine
    mismatch, framework security policy, or application error — each with the log tail and a next
    action. A wall of stack trace is not a diagnosis, and those categories have different owners.
  - **A known-gotcha table ships with it**, seeded from the audit: Hugo ≥ 0.158 refusing raw
    `.html` without `HUGO_SECURITY_ALLOWCONTENT`, Node 25 injecting a global `localStorage` that
    breaks SSR feature-detection, `exports`-map subpaths that are unresolvable though the file is
    on disk. All three read as application breakage and are not.
  - **Prebuilt assets are detected, not silently skipped.** Where the documented start command
    chains a bundler but built output is already present and newer than its sources, the lighter
    server-only path is used *and the assumption stated* — an audited project already had
    `static/app.css`, so `hugo server` alone sufficed and a naive runner would have died on webpack.

### 1.7.0 — 2026-07-29

- **`case-author` consumes rails-flow's acceptance criteria** (#125) — `docs/acceptance/*.md` is now
  its **first** source, ahead of the PRD, because it is the only one written *before* the code and
  therefore the only one stating what was **required** rather than what shipped. Each `AC-n` becomes
  a case with `Source: acceptance:<slug>` and the criterion id in `Notes`, so the trail runs
  criterion → case → evidence. Criteria tagged `[error]` become the **negative** cases. Closes a
  loop that was previously broken in one direction: `case-author` and `qa-lead` already claimed to
  read acceptance criteria from `docs/`, but nothing in rails-flow ever wrote them — the consumers
  existed and the producer did not.

### 1.6.0 — 2026-07-29

- **A screenshot is not evidence until the page it shows is validated** (#106) — `functional-tester`
  was told "every finding needs a screenshot" and nothing more, so a capture of a 404, an error
  page, a redirect target, or a half-rendered skeleton could be filed as evidence for a **Pass**.
  That is worse than no evidence: it manufactures false confidence, and it is invisible because the
  report looks complete and green. Found the hard way — a real audit wrote 66 captures from a
  sitemap and **12 were 404s**; a human caught it by eye, the tooling could not.
  - Every capture now passes a four-check gate before it counts: **HTTP status** off the navigation
    response (not inferred), **final URL** recorded against the requested one, an
    **expected-content assertion** drawn from the case's own expectation, and not-still-loading.
    Validation failure yields **`Blocked`** — never `Pass`, never `Fail` — with the status and URL
    recorded, because a blocked case is honest about being untested.
  - **The expected-content assertion is the load-bearing signal, and the fix deliberately does not
    text-sniff.** Status alone is insufficient (error pages return HTTP 200); error-text alone is
    insufficient *and actively harmful* — the naive version of this fix wrongly excluded four
    **valid** cases, real 404-page *designs* that return 200 and legitimately read "page not
    found". Because the expectation comes from the case rather than a keyword list, an intentional
    error-page design is correctly testable. A fixture pins this so the over-correction cannot be
    reintroduced.
  - The rule is **enforced, not just written**: the report's CSV summary gains a fixed ten-column
    contract (`Status,HTTP,Requested URL,Final URL,Assertion,…`) and a shipped checker,
    `plugins/qa-flow/scripts/validate_evidence.py`, which the agent must run clean before reporting.
    It rejects any `Pass`/`Fail` row that omits its status/URLs/assertion, any `Pass` on a
    non-2xx/3xx status or a silent redirect, and any `Blocked` row that records nothing — and it
    **refuses to bless a report it could not read** (drifted header or zero rows exit 2) rather
    than reporting clean over input it never parsed.
  - Bounded honestly in both the script and the agent doctrine: it closes the **omission** hole,
    which is the one that produced the false PASS. It cannot tell whether a recorded status is
    *truthful* and it never sees the screenshots, so "not still loading" stays agent-side.
  - **`a11y-auditor` had the same defect** and is fixed with it: an axe run against a 404 or a
    login redirect returns real violations attributed to the wrong page, then files them as
    defects. It now records status + final URL, asserts expected content, and reports **BLOCKED**
    instead of a clean or violation-bearing result.
  - Deliberately **not** gated: `perf-tester` (already mandates "status + body-shape checks" — the
    existing house precedent for this two-signal rule), `security-scanner` (reports per-URL), and
    design-flow's `design-auditor` (audits source, not rendered pages). `#105`/`#107` are unbuilt,
    so they adopt the rule at authoring time.

- **The evidence rule is now enforced on every browser pass, not just one** (#106, slice of #120) —
  the first cut left qa-flow with one machine-checked evidence path (`functional-tester`) and one
  prose-only one (`a11y-auditor`). That asymmetry *is* the `claims-vs-enforcement` class: the same
  rule, enforced in one place and merely asserted in the other, which is how the original defect
  survived in the first place.
  - `validate_evidence.py` is now **profile-driven**: one implementation of the shared rule
    (status / requested-vs-final URL / expected-content assertion / silent-redirect / Blocked must
    record what it saw) with a per-artifact contract on top. The artifact kind is **detected from
    the header**, so a caller can never pass a `--kind` that disagrees with the file, and an
    unrecognised header exits 2 instead of falling back to a guess. `--contracts` prints the known
    schemas. Adding a browser pass is adding a `Profile`, not copying a rule.
  - **`a11y-auditor` gains a real artifact**: `qa/reports/a11y-<slug>-pages.csv`, eleven fixed
    columns, one row per page/state. Statuses are `Audited` / `Blocked` / `Out of Scope` — there is
    no "Pass", because an audit reports what it found rather than rendering a verdict; a clean page
    is `Audited` with `Violations` `0`. An audited row must also carry its **violation count**,
    **keyboard verdict** (`Pass`/`Fail`/`Not run`), and an **evidence path** — so a row cannot say
    a page was audited while recording no outcome, and placeholder text (`n/a`, `TBD`, `-`) is
    rejected where a number belongs.
  - **`exploratory-tester` closes the identity gap without inheriting the gate.** Every defect it
    files must record the HTTP status and final URL the evidence came from. Deliberately *not*
    BLOCKED-on-failure: its mission is hunting for surprises, so an unexpected error page is a
    finding, not spoiled evidence. The narrower reason stands on its own — a defect whose evidence
    cannot say which URL produced it is unreproducible.
  - The selftest now cross-checks **both** agent files against the exact headers the script
    enforces, and asserts every profile is documented by some agent — so a contract cannot drift
    into mutual rejection, and a profile no agent writes shows up as a dead contract.
  - **72 selftest assertions**, and **20 deliberate mutations across both cuts, each caught** —
    including dropping any single a11y outcome requirement, accepting placeholder violation counts,
    letting the two profiles share a status vocabulary, and making header detection fall back to
    the first profile instead of failing closed.

### 1.5.1 — 2026-07-25
- **functional-tester never touches git** (#78) — it was auto-committing its run evidence
  (report + screenshots **and ~35 ephemeral `.playwright-mcp/` session dumps**) to the checked-out
  branch and pushing, landing 50 files on `origin/dev` unreviewed on a "no code changes" prompt.
  The agent's output contract now forbids all git ops: write **only** under `qa/manual-tests/`,
  leave it uncommitted in the working tree for the coordinator to commit via the normal flow, and
  **never** stage `.playwright-mcp/` (ephemeral MCP state) or push to a shared branch. `setup-qa`
  now gitignores `/.playwright-mcp/` as a backstop.

### 1.5.0 — 2026-07-24
- **NEW `/qa-flow:smoke`** (#64) — the build-verification floor: **launches the app**
  (stack-aware, from a new `app:` block in `qa/qa.config.yml` — `start`/`port`/`health`/`routes`/
  `boot_timeout`, Rails-defaulted `bin/dev` + `/up`), waits for health, hits key routes (5xx =
  fail), sets `QA_BASE_URL`, and tears the server down (trapped). Closes the gap where
  `verify` Phase 0 only *assumed* a booted app and Phase 1 ran full `@smoke` E2E against it — now
  "the build won't boot" is caught in seconds with the real boot log, before any heavier phase.
  Stack-agnostic (only the `app:` config differs), free (the app's own server + curl). `verify`
  Phase 0/1 now run `/qa-flow:smoke` first; `setup-qa` scaffolds the `app:` config block.

### 1.4.1 — 2026-07-23
- **release-gate.sh: closed fail-open bypasses** in dev→main promotion detection (from the
  PR-review backlog triage, #45). (1) Heredoc-body stripping ran before quote/comment
  stripping, so a `<<EOF` inside a quote (`echo "<<EOF"`) or comment (`# <<EOF`) was read as a
  real opener and swallowed a later `git push origin main` → gate passed. (2) Delimiter regex
  missed numeric-leading/hyphenated delimiters. (3) Detection missed prefixed promotions
  (`FOO=1 git push`, `sudo git push`, `git -C repo push`). New pipeline: un-quote delimiters →
  strip quotes → strip comments → strip heredoc bodies, then peel env/sudo/git-option prefixes.
  Verified with an 18-case battery. Local advisory gate; `QA_ALLOW_MAIN=1` override unchanged.

### 1.4.0 — 2026-07-23
- `setup-qa` now **detects the codebase and proposes a recommended stack** instead of asking
  cold: it reads deps/test tooling (`cypress`/`@playwright/test`/`selenium`+`pytest-bdd`),
  `*.feature` files, mobile targets (React Native/Flutter/`ios`+`android`), an OpenAPI spec,
  existing Allure/Testmo config — and pre-fills `qa/qa.config.yml` with a one-line rationale
  per non-default tier. **Respects existing tooling** (never proposes switching a framework
  the repo already uses); greenfield falls back to free defaults by app language. Advisory
  only — the engineer confirms or overrides any line before it's written. Still no forced
  stack.

### 1.3.0 — 2026-07-23
- Wire the free **Allure** unified report end-to-end (`reporting: allure` | `both`; default
  `markdown-csv` unchanged, zero-dependency): `setup-qa` scaffolds the framework's Allure
  adapter for the chosen `web_e2e`/`mobile` runner (allure-playwright / allure-cypress /
  allure-pytest / Appium adapter), all tiers writing into one `qa/reports/allure-results` →
  `qa/reports/allure-report` (both gitignored). `e2e-tester` emits results and **attaches
  evidence** (failure screenshot, Playwright trace, logs), then `allure generate`.
  `qa-reporter` honors the mode, generates the aggregated HTML, keeps a legible Markdown
  verdict/counts alongside, and cites the report path in the PR-native comment. Free/OSS
  (Apache-2.0); no paid or online reporting service.

### 1.2.0 — 2026-07-23
- **Stack-agnostic — no forced testing stack.** New `qa/qa.config.yml` is the override
  point the QA engineer sets; every agent honors it. `setup-qa` is now config-first: it
  asks/reads the config and scaffolds ONLY the chosen tools. Free defaults; any tier
  overridable.
  - `web_e2e`: `playwright` | `cypress-cucumber` | `selenium-pytest-bdd` | `none`;
    `mobile`: `appium`; `functional_agent`: `playwright-mcp` | `autonoma-selfhosted`;
    `api`/`perf`/`security`/`a11y`; `reporting`: `markdown-csv` | `allure`;
    `case_management`: `in-repo` (free CSV, default) | `testmo` (paid, opt-in).
  - `e2e-tester` rewritten stack-agnostic: universal doctrine (self-adapting resilient
    locators, no sleeps, auth-reuse, tag routing, failure classification, corpus growth) +
    per-framework specifics; reuses the same Gherkin `.feature` scenarios across web/mobile.
- **Autonoma-inspired patterns, kept free:** `functional-tester` now **auto-maps** the
  in-scope flows before testing and drives by the **live accessibility snapshot**
  (self-adapting, no brittle selectors) via Playwright MCP. `qa-reporter` gains **PR-native
  result posting** (`gh pr comment`, marker-updated) so results show up in the PR like a CI
  check.
- **Opt-in paid backends without lock-in:** `case_management: testmo` makes `case-author`
  mirror `qa/test-cases.csv` ↔ Testmo via its REST API (`TESTMO_URL`/`TESTMO_TOKEN`, env,
  gitignored); the in-repo CSV always stays the source of truth. Testmo is not an MCP —
  REST/CLI; `setup-qa` captures the creds. Default stays free/in-repo.

### 1.1.0 — 2026-07-23
- Automate the tedious QA loop — case authoring/management + agentic functional testing,
  **free and repo-local** (no Testmo/online case manager; Testmo is paid and stays optional
  — an export can seed the catalogue but the in-repo file is the source of truth):
  - NEW `case-author` agent + **`/qa-flow:cases`** — writes and MAINTAINS the test-case
    catalogue `qa/test-cases.csv` (columns `Test ID,Title,Area,Type,Priority,Status,Source,
    Notes`) from the PRD, app menu/routes, the qa-lead plan, and `docs/brain` defects.
    Stable `TC-###` IDs; idempotent add / update / deprecate (never renumber or hard-delete);
    Excel-openable; reviewable as a `git diff`.
  - NEW `functional-tester` agent + **`/qa-flow:functional`** — drives the running app via
    **Playwright MCP** (free) from those case titles: menu-scoped, evidence-based (screenshot
    per finding), strictly in-scope, no code changes. Writes a Markdown report + an
    Excel-openable CSV summary + screenshots to `qa/manual-tests/`. Models a proven
    Claude-Desktop + Playwright-MCP manual-testing flow, systematized into the plugin.
  - `setup-qa` scaffolds `qa/test-cases.csv` + `qa/manual-tests/` and documents enabling the
    Playwright MCP server.

### 1.0.6 — 2026-07-23
- Close the #1 residual: release-gate now strips heredoc BODIES before detection, so an
  unquoted heredoc body line beginning with `git merge` / `git push origin main` /
  `gh pr merge` no longer trips the gate (`<<EOF`, `<<-EOF` with tab-stripped terminator,
  and quoted `<<'EOF'`/`<<"EOF"` all handled; here-strings `<<<` left alone). A genuine
  promotion on a line after a heredoc, and ordinary newline-separated promotions, still
  gate. Verified on `main` via a worktree (`git merge` blocks on main; a commit message
  mentioning it does not) plus the full regression matrix. Residual (documented
  in-script): multiple heredocs opened on a single line (`cmd <<A <<B`) track only the
  first body — astronomically rare, and errs fail-closed.

### 1.0.5 — 2026-07-23
- Fix #1: the release-gate hook no longer false-positives on commands that merely
  MENTION a promotion. Detection now strips quoted spans (commit messages, `-m` /
  `--body`, `echo` bodies) and requires `git push …main|master` / `git merge` /
  `gh pr merge` at the START of a command segment (split on `;` `|` `&&` `||`) — so a
  commit whose message contains "gh pr merge", or an `echo`/PR-body referencing
  "git merge", is no longer read as an invocation. Genuine promotions (incl. chained
  `… && git push origin main`) still gate, the `gh pr merge` unresolvable-base case
  still fails closed, and `QA_ALLOW_MAIN=1` still overrides. Verified with a 10-case
  matrix. Residual (documented in-script): an unquoted heredoc body line beginning with
  `git merge` is still seen — rare, and errs fail-closed.

### 1.0.4 — 2026-07-22
- setup-qa: idempotent re-run + repair contract (matching setup-flow). Generated config
  refreshed only within `qa-flow:begin/end` markers; seeds additive (find_or_create);
  defective managed files (baseURL not reading QA_BASE_URL, personas mismatching app
  roles) diagnosed and fixed as approved diffs; deliberate customizations untouched.

### 1.0.3 — 2026-07-22
- release-gate python3-missing guard: word-boundary matching (grep -E with \b)
  instead of the `*push*main*` glob, so `git push origin maintenance` no longer
  false-matches "main". Real promotions (main/master as whole refs, gh pr merge,
  git merge) still catch; still fails closed in the safe direction. Verified.

### 1.0.2 — 2026-07-22
- Portability pass (proactive, same class as the stop-gate macOS fix): the BLOCKING
  release-gate now fails CLOSED if `python3` is absent on a promotion command (a gate
  that can't evaluate must not permit dev→main) with a clear install/override message,
  reads stdin once, and uses `type -P`. The non-blocking qa-status hook skips cleanly
  when python3 is absent. Consistent across macOS/Linux/WSL.

### 1.0.1 — 2026-07-22
- release-gate hardening (peer review): fail CLOSED when the certification sha is
  empty/garbled (the sha binding is the gate — PASS alone is insufficient); robust
  `gh pr merge` promotion detection incl. bare (current-branch) merges and
  unresolvable base treated as promotion; platform note (bash+python3 → WSL/Git Bash
  on Windows) added to the plugin README.

### 1.0.0 — 2026-07-22
- Independent QA engineering flow, sibling to rails-flow, testing the running app
  from the outside with its own toolchain — never the developer spec suite.
- 8 agents: qa-lead (risk/blast-radius planning from PR docs + project skills),
  e2e-tester (Playwright TS, smoke/regression tags, corpus growth),
  api-contract-tester (Schemathesis + authz matrix), a11y-auditor
  (axe-core WCAG 2.2 AA + keyboard), perf-tester (k6 smoke + load/soak),
  security-scanner (OWASP ZAP DAST, triaged), exploratory-tester (session-based),
  qa-reporter (report + defect filing + certification stamp + corpus promotion).
- 3 commands: /qa-flow:verify (post feature->dev: smoke gate -> sanity -> targeted
  regression by blast radius, risk-gated selection), /qa-flow:certify (pre dev->main:
  smoke -> full regression -> load/DAST/cross-browser on staging, writes the stamp),
  /qa-flow:setup-qa (scaffold qa/ workspace + PR template + tool checklist).
- Hooks: release-gate (PreToolUse — blocks dev->main promotion unless
  qa/CERTIFICATION PASSes for the exact dev sha; QA_ALLOW_MAIN=1 audited break-glass)
  and qa-status (SessionStart — certification freshness vs dev).
- Doctrine (source-verified): smoke gates but never certifies; sanity subset of
  regression; regression is the release gate; QA guards existing behavior and absorbs
  proven features into the corpus rather than re-testing the current feature.

## design-flow (UI/design plugin)

### Unreleased

- **A `pen` rung for composed raster.** (#599) An OG card or social preview is layout plus real type
  at a fixed size, and a diffusion model is the wrong instrument twice over: it cannot render
  accurate text, and it cannot render the same brand twice. `pen` joins the adapter registry, driving
  the CLI headlessly and returning the exported PNG.

  **It is keyless**, and that is now stated as data rather than an `if`: `KEYLESS = {"agent", "pen"}`.
  Both make no authenticated call this config could serve, and demanding a key refuses a zero-cost
  route for a credential it never uses — the exact defect already recorded for the agent rung, which
  a second keyless adapter would otherwise have had to remember to join.

  **An absent binary says only what a PATH miss proves.** pen.dev also ships as a user-scoped MCP
  server registered outside the repo, so a provisioned machine fails this probe — measured, on a
  machine where `claude mcp list` reported pencil connected while `which pen` found nothing. The
  refusal names the CLI, not pen.dev, because "pen.dev is not installed" would send someone to
  install what they already have. Cost is reported **unknown** rather than zero: the CLI drives its
  own agent on the operator's Claude auth, so it spends Opus-minutes, not a figure this path can read.

- **`/design-flow:setup` tells a developer the composition tier exists.** (#600) A new machine now
  learns, at setup, whether a pen surface was found, what it would add — cheap N-way exploration,
  token-native custom icons, OG cards with real type — and how to add either surface later (the
  desktop app for interactive work, `npm install -g @pen.dev/cli` for headless). It **installs
  nothing and blocks on nothing**: a developer who skips it must see no difference in any command's
  behaviour, which is the contract the tier is asserted against. Discovering an optional tier months
  later in some command's output is the same failure as not shipping it.

- **An optional composition tier, and the intent pass that judges it.** (#600, #601)
  `scripts/pen_compose.py --surface` / `--intent`.

  Divergence in `/design-flow:variants` is priced at **N × ERB** — every option costs a full
  `ui-composer` dispatch writing real view code before it can be compared. A composition surface
  makes exploration cheap and charges the ERB price only for the winner.

  **The tier is on where available**, per maintainer decision, unless a project sets
  `exploration_surface: none`. The argument for defaulting off — that one machine's tooling should
  not change how a shared repo builds UI — is weaker here than it looks: a `.pen` file is never a
  merge artefact and never a gate input, so the output contract is identical either way. A tier that
  is off by default is a tier nobody discovers.

  **`--surface` always exits 0.** "No surface" is a normal answer, and a machine without pen must not
  look like a machine with a problem — otherwise callers learn to ignore the exit code, which is how
  a real failure later goes unnoticed. Detection needs `--mcp-available` passed by the caller,
  because namespace presence is **not** readiness: a tier that offers itself and then fails on the
  first call has already spent the operator's attention.

  **The audit is a three-pass progression** — intent (the composition, advisory), source (the ERB,
  blocking), rendered (the browser, blocking, shipped since #107). Only pass 1 is new, and it
  **cannot** judge conformance: role tokens, focus rings, ARIA, tap targets and the motion count that
  doctrine calls *arithmetic* are properties of code that does not exist yet. So it reports facts
  about the document instead — raw colours instead of tokens, placeholder copy, a composition
  referencing no library component, a brief ignoring the researched style. `/design-flow:audit`
  now reports all three passes and must name any that was skipped, because a skipped pass and a
  passing one must never look alike.

  25 assertions and 4 mutation guards. One guard had to be re-aimed after the harness showed the
  obvious fixture passing **coincidentally**: disabling the `none` branch leaves the verdict
  unchanged and alters only the reason, so the assertion that catches it is the one about the
  message. That is exactly what `expects` exists to prevent.

- **Generate the pen.dev design library from the brand pack.** (#603)
  `plugins/design-flow/scripts/pen_library.py --pack fidara --out design/library.pen`.

  Without a library, a composition is built from bare rectangles and is off-brand by construction —
  so the cheap-exploration argument collapses into "sketch something that will not survive review".
  This writes all **22 role tokens** as pen variables with **both theme modes explicit**, plus the
  components a composition needs (Button ×4, Card, Input, Badge, type scale), each `reusable: true`
  so a composition instantiates a `ref` rather than copying geometry.

  **It writes a file rather than driving the MCP, and that is the decision that made this
  tractable.** Through the MCP **ids cannot be chosen** — *"Pencil will always generate unique random
  IDs and override the input"*, measured, every supplied id replaced — so an MCP-built library gets
  new ids on every regeneration and every `ref` in every existing document breaks **silently**, a dangling
  ref being no kind of error. That forced a name-matching reconciler, until the simpler observation:
  `.pen` is plain JSON, the id rule belongs to `Insert`, and a file we author carries the ids we
  write. Regeneration is byte-identical **by construction**, and needs no app, no open document and
  no human — so it can run in CI, which the MCP path never could.

  **The library file is also the scratchpad**, which is what makes it usable: compositions get built
  in the same document that holds the components. So a rebuild replaces only the generated nodes
  (`fm-*` ids) and preserves everything else in place, and `--check` compares **only that region** —
  a drift check that fired on the designer's own explorations would fire on correct input, and one of
  those gets switched off. The single thing a rebuild reclaims is a **hand-edited role token**: the
  pack owns the roles, and a stale override repaints the library against a pack it no longer matches.

  **The hex lives in exactly one place** — the document's `variables`. Every component fill is a
  `$--token`, so one pack change repaints the library and light/dark come from one document. That is
  asserted by compiling the generated library through `pen_to_svg.py`, which refuses a literal colour
  by node: **two of our own tools checking each other** rather than each trusting itself.

  26 assertions and 4 mutation guards. The guard needed the brand pack added to its `needs` — without
  it every mutation died on `no theme.css`, and the harness correctly refused to score a crash as a
  verdict. One assertion was hardened from `e["theme"][AXIS]` to `.get()` for the same reason.

  **Why derived and not authored in parallel:** pen is the scratchpad for design iteration, so the
  exercise is only meaningful if the components being composed with are **the ones the agent will
  build the real code from**. Choose a variant made of components the codebase lacks and the review
  said yes to a screen nobody can ship. That is what makes the drift check load-bearing rather than
  hygiene. The guarantee currently reaches the **tokens** (derived, so a composition cannot drift on
  colour) and not yet the **catalogue** (hand-written against `components.md`, so it can still drift
  on structure) — stated in the file itself and tracked as #607, because that gap is invisible
  otherwise.

  **Authored to the convention a real pen library uses**, after reading one (`shadcn.lib.pen`).
  Four things changed, and three are better engineering rather than cosmetics:

  - **One root frame** holds the library — themed, painted from `$--background`, named
    `<pack>: design system components`. Eight loose top-level frames is a canvas with components on
    it; one named container is a *library*, and the difference shows the moment a composition is
    built beside it.
  - **Variants are `ref`s, not copies.** One `Button/Default` defines the geometry; Secondary, Ghost
    and Destructive are instances that repaint it via a `descendants` map. A radius change now
    reaches all four instead of reaching one and drifting from three — and the map is addressable
    *only because ids are derived rather than random*.
  - **Flexbox, not absolute boxes** — `gap`, `padding`, `justifyContent`, and no width, so a
    component sizes to its label. A fixed 140×40 button is a picture of a button.
  - **`Category/Variant` naming**, matching the convention.

  `pen_to_svg.py` gained **ref resolution** to match: refusing an instance would have made exactly
  the well-authored library uncompilable while passing the copy-pasted one. It resolves before
  measuring, too — a `ref` takes its size from its base, so reading width off the instance reported
  "no size" for a variant that is perfectly well defined.

  **And it cost a cross-check that was over-reach.** The suite used to compile every component
  through `pen_to_svg` as a mutual check. A flex-laid-out component has no size until a layout engine
  runs, and it was never destined to be an `.svg` file — it becomes ERB. The compiler is for
  **artwork**; conflating the two was my error. The property that mattered is asserted directly (no
  literal colour anywhere in the library), and the compiler is now asserted to *refuse* an unsized
  node honestly.

  **Verified against pen itself** (CLI 0.3.2), headlessly:
  `pen interactive -i library.pen -o out.pen`, then `get_app_state({…})`. pen reports all 8
  components as **top-level nodes AND reusable components**, under **the ids we chose** —
  `fm-button-primary`, `fm-card`, … — which is the file-authoring premise confirmed end to end: ids
  survive because the "Pencil always generates random IDs" rule belongs to `Insert`, not to a
  document it loads.

  Exporting through pen then rendered `--primary` as **#0072C4** (fidara cerulean-700) on white, and
  the card in `--card` / `--card-foreground` / `--muted-foreground` / `--border`. So the variables
  resolve, which is the claim that mattered: one document, one pack, both themes.

  Getting there needed one correction on the way. `export_nodes` with an explicit `filePath` naming a
  file that is not open **silently resolves against the active document**, so it answered confidently
  about the wrong file and a missing node read as "the library is broken". `get_app_state` names the
  active editor; checking it costs nothing and is now doctrine. Of every pen quirk measured, this is
  the only one that produces a *confident* wrong answer rather than a blank or black one.

- **Compile a `.pen` design into token-native SVG, rather than exporting one.** (#602)
  `plugins/design-flow/scripts/pen_to_svg.py`.

  pen.dev exports `png/jpeg/webp/pdf` and **no SVG** — read off `export_nodes`' own tool schema. The
  first conclusion drawn from that was that pen could not serve illustration at all. Wrong question:
  the `.pen` format **is** SVG-shaped, since a `path` carries `geometry`, an SVG path string, beside
  a `viewBox`. Nothing has to be recovered from a render.

  **And compiling beats the export we do not have.** Every design tool's SVG export emits hardcoded
  hex — exactly what `design-auditor` refuses by name (#135, *"a `fill=`/`stroke=` hex inside a
  component"*), so an exported asset arrives as a conformance violation needing manual recolouring. A
  `.pen` fill that references a variable is written `$--token` and compiles to `var(--token)`: born
  conformant, recolouring with the brand pack, and serving **light and dark from one file**. Verified
  end to end — an illustration authored in pen against the fidara pack, compiled, and rendered in
  both themes from a single asset.

  **It reads the file, and that is forced rather than chosen.** `Get("<pathId>").geometry` returns
  `"..."` through the pencil MCP, on a direct single-node read as well as through a visitor — the one
  field this needs is the one the structured API elides. The file is plain JSON (measured on three
  real documents), so reading it works; the server's own instruction that *".pen files are encrypted:
  never use Read or Grep"* is false as a claim about bytes, and obeying it would rule out the only
  path that functions.

  **It refuses rather than approximates**, because a degraded compile looks finished and nobody
  re-checks it: shaders, mesh gradients, conic gradients, image fills, arc/donut ellipses, paths with
  no geometry, and dimensions bound to a variable. A **literal colour is an upstream problem** — it
  means someone composed against a raw hex — so it is refused by node, not guessed at. That refusal
  fired on unmodified vendor content the first time it ran.

  36 assertions and 5 mutation guards, each guard turning a refusal into an approximation. Fixtures
  are hand-authored JSON, never a captured `.pen`: a real document would drag the vendor's version
  churn into the suite and could not carry a deliberately malformed node, which every refusal needs.

- **`/design-flow:generate` documents when a design tool beats a model** — compile the vector, export
  the raster. A custom icon or spot illustration compiles to SVG; an OG/social/app-store surface
  exports to PNG, because its value is real type at a fixed size and there is nothing to compile to.
  Custom icons stay the exception to Lucide, composed *beside* real Lucide glyphs, since the way a
  custom glyph gives itself away is optical weight that only shows side by side.

  Three measured gotchas are written down because each produces a plausible wrong answer instead of
  an error: a token push that omits an explicit theme mode is **silently dropped** and the artwork
  exports **black**; a per-node screenshot rendered only the background while the export was correct;
  and ids cannot be chosen, so assets are addressed by **name**.

- **`*.pen` is gitignored.** The pen.dev app writes documents wherever it is pointed, including the
  repository root, where one was found untracked. Not slash-anchored — a stray is a stray at any
  depth, and #197's lesson was that a pattern matching only the case you happened to test is a guard
  that has never fired.

### 1.22.0 — 2026-08-09

- **The cost preflight read a config key `--scaffold` has never written, so every plan cost $0.00
  and the budget guard could not fire.** (#592) `--scaffold` writes the price table under `ladders`
  — a dict keyed by kind — while `plan_cost()` and `affordable()` read `ladder`, flat and singular.
  Against any real project that resolved to `[]`, so the estimate was `$0.00` however many rows the
  plan held, `0.0 > ceiling` was never true, and `--run` fell straight through the refusal to the
  executor. **A guard whose input is always zero is not a lenient guard; it is one that has been
  switched off, and nothing said so.**

  Reconciled onto `ladders`, priced **per kind** — which is the shape the per-kind ladders were
  introduced for. A video rung costs an order of magnitude more than a vector rung the agent
  authors, so one flat ladder had to be wrong for at least one of them. The flat key still resolves
  as a fallback, matching `generation_gate.py` exactly, so hand-written configs keep working.

  Two further holes closed on the way, both the same shape one level down:

  - **An unpriced ladder read as a free one.** `cheapest_rung` returned `0.0` when nothing on the
    ladder had a price, so the row nobody had costed was the cheapest thing in the plan and fitted
    inside every budget. It returns `None` now, and `--run` **refuses an unpriced plan outright,
    before the executor is invoked and regardless of the numeric total** — deliberately not a budget
    comparison, because a ceiling can only refuse a number. `--confirm-partial` does not bypass it:
    "buy what the budget affords" is a decision about rows whose price is known.
  - **`affordable()` computed "the cheapest rung" its own second way**, which disagreed with
    `cheapest_rung` in two directions at once — it counted an unpriced rung as free, and raised
    `TypeError` on a rung whose `cost_usd` is explicitly `null`, which is exactly what the scaffold
    writes for video. One answer now, from one function.

  **Why 63 assertions passed over it.** The cost fixtures hand-wrote `{"ladder": [...]}` — a shape
  the scaffold has never emitted — so the suite validated a contract the writer does not produce.
  Tests that *imitate* the writer's output instead of **using** it cannot see a writer/reader
  divergence; they are two transcriptions agreeing with each other. Every cost fixture is now built
  by calling `scaffold()`, and a new end-to-end fixture drives `main(["--run"])` against a real
  scaffolded project with a `subprocess.run` that fails the test if the executor is ever reached.
  Five mutation guards cover the reconciled reader, the `None` rung, both refusals and the render.

- **The asset plan renders as a markdown table beside the JSON.** (#593) `plan.json` is the right
  shape for the agent that runs the plan and the wrong shape for the human who has to **review** it,
  which is the step the plan exists for. `--render` writes `docs/assets/plan.md`: one row per asset
  with surface, kind, status, group, priority, per-row estimate, produced file and `why`. Unpriced
  rows are marked **unpriced** rather than shown as `$0.00`, so the reason a run will refuse is
  visible in the document someone reads before deciding to spend.

  Generated, never hand-maintained — a hand-kept table is a second source of truth that disagrees
  with the first within a week and disagrees *silently*, because a stale table still looks like a
  table. Two properties carried over from `docs/coverage.html`: the bytes are a function of the
  **data only** (no timestamp, no SHA, no absolute path — anything else makes the drift check
  unpassable by construction), and the totals come from `status_report()` rather than the renderer
  recounting rows. `save_plan()` re-renders at the single choke point so a mutation path added later
  cannot forget, `--check` reports staleness, and an **absent** table says nothing at all — it is
  opt-in, and a check demanding a file the scaffold never creates would fail every project that
  does not want one.

- **Three stale claims in `asset_plan.py`'s own doctrine.** The module docstring described a
  placeholder API key the scaffold stopped writing two releases ago; `--scaffold` told every new
  project its next step was to fill `$OPENROUTER_API_KEY`, a variable the scaffolded path never
  reads, as the **first instruction it sees**; and `--discover` printed `--discover needs $None set`
  on any default config. All three now describe what the code does — the agent generates by default
  and needs no key, and what makes the scaffolded state safe is that paid rungs ship unpriced and an
  unpriced row is refused before the executor runs.

### 1.21.0 — 2026-08-09

- **The research now decides the style, and the plan holds every brief to it.** The sequence —
  scaffold, read the PRD, research for inspiration, curate the set, generate — was enforced at every
  step **except the one that carries the meaning**: nothing connected the research to the style. A
  project could research monochrome ink line-work and brief a `3d-render`, and no check noticed. The
  record was a box that got ticked.

  `style` is now the research record's **output**, required once it has references: three sources
  disagree, which is why three are the minimum, and **the choosing is the design**. A record that
  gathers and does not choose is a mood board — it documents the looking and omits the decision.

  Every brief is held to that value, and a mismatch refuses **before anything is bought**. One
  family, one style: a set that mixes them is the pile this whole path exists to avoid, and it is
  invisible once shipped.

- **The settled approach is emitted as a project-level SKILL, not left as JSON.** `--emit-skill`
  writes `.claude/skills/project-design/SKILL.md` — the chosen style, the job it serves, the
  mechanisms adopted, and **what was rejected and why**.

  The record is *evidence*; the skill is *doctrine*. A JSON file is parsed when an agent remembers
  to; a skill is read because its description matches the work in hand. Left only in the record, the
  style gets **re-derived** by every downstream agent from raw references — and re-derivation is
  where a family quietly becomes a pile. The rejected half is the part people drop, and it is the
  reason the same idea is not re-proposed next quarter.

  It is **generated, never hand-edited**, and refuses to emit from a record that does not pass its
  own checks — publishing a decision nobody made, into the place agents trust most, is worse than
  publishing nothing. That guard first lived in `main()`, where no test reached it and a mutation
  survived; it now sits at the point of writing, where the danger is.

  Tokens are deferred to the brand pack rather than restated, so the skill records the *approach*
  and the pack records the *values* — one home each.

- **Retracted, not shipped: a Figma-to-tokens reader.** It was named as a gap against an external
  designer workflow, and it is not one — tokens here are **generated from the brand pack**, so a
  Figma reader would be a second source of truth for the same values, which `plugin-boundaries`
  forbids by name. The flow is agent-driven; the absence is a decision.

- **Doctrine said motion had no route. It was wrong, and the shape of the error is worth keeping.**
  The claim began as a true statement about the *image* endpoint — it returns no video — and was
  allowed to stand as a claim about the provider, so the scaffold shipped an empty motion ladder and
  every motion row refused. A true sentence about one endpoint became a false one about the whole
  system, and nothing caught it because it read as a limitation rather than as a claim. OpenRouter
  has a video endpoint; there are **21 video models**, verified against the live catalogue.

- **`motion` and `video` are now separate kinds, and that split is the real fix.** They were one
  kind, which routed a **loading spinner through footage generation**. Product motion is Lottie JSON
  or an animated SVG: a few KB, recoloured from tokens, scrubbable, diffable in review, and authored
  by the agent for nothing. Generated video is footage — megabytes, fixed palette, un-recolourable,
  expensive, and right for a marketing hero and almost nothing else. Conflated, the cheap common
  case paid the expensive rare case's price. The kind/bytes check now accepts `svg` or `json` for
  motion and refuses a video file with a sentence explaining which kind was meant.

- **The video adapter is asynchronous, and three of its shapes are load-bearing.** Submit returns
  **202 with no asset**, so a caller treating 2xx as success saves an empty file; the timeout covers
  the **whole poll** rather than each request, because a per-request timeout on a job taking minutes
  never fires and the run hangs instead of failing; and the download URL needs the **same auth**,
  because an unauthenticated fetch returns an error page, which is bytes, and bytes get written.

- **The output critic — the stage that was missing.** #507 asked for *"a per-surface acceptance
  check, so climb-the-ladder has a trigger"*, and it shipped as **a string that had to be present**:
  letter of the criterion, not spirit. Nothing read the asset, so the trigger was one nobody could
  pull, and `attempt` existed while nothing ever set it. `--critique` now assembles what a critic
  needs — the acceptance check, the brief, the pack, the prompt — and `--verdict accept|reject`
  records the judgement. **Accept** writes the manifest with its reason attached; **reject**
  increments `attempt`, which is the climb trigger, finally wired.

  A surface with **no** acceptance check yields no critique brief at all, because a critic without a
  criterion produces an opinion, and an opinion recorded as a verdict is worse than no verdict. A
  verdict with no reason is refused in both directions: an accept nobody can review is as useless as
  a reject nobody can act on.

  Four fixture defects surfaced while building it, all the same class — fixtures failing on each
  other's side effects rather than on what they name. The accept path writes a manifest row, so
  every later call in that tempdir tripped the duplicate-surface refusal, and a bare
  `except Unusable: pass` swallowed it and passed for the wrong reason. Each check now runs in its
  own tempdir and asserts *why* it refused, not merely that it did.

### 1.20.0 — 2026-08-09

- **`.env` was promised in two shipped messages and read by nothing.** The scaffold's comment and
  the key refusal both said *"put the real value in your environment (or a gitignored `.env`)"*,
  while `generate_asset.py` called `os.environ.get()` and stopped there. Follow the instruction and
  you get *"is not set"* — which reads like a broken tool rather than an unloaded file, in the one
  message a user sees when they are already stuck. It now reads `.env`, and **the real environment
  wins**: a shell export is the more deliberate act, and someone debugging a key must not be
  silently overridden by a stale file they had forgotten. A placeholder in `.env` is still a
  placeholder — the file is a source, not an exemption.

  The parser is deliberately minimal: `KEY=value`, optional `export`, matching quotes, `#` comments.
  No interpolation, no `${VAR}` expansion. A fuller parser is a dependency, and this script holds an
  API key, so *no transitive supply chain* is worth more than covering exotic syntax.

- **OpenRouter is now the default aggregator, and it makes an existing promise true.** The docstring
  already claimed cost is *"recorded from the response, not from the estimate"* — which the Gemini
  adapter cannot do, because that response carries no per-request price. OpenRouter's does
  (`usage.cost`), so the provenance row records **`actual_cost_usd`** beside the estimate, and the
  two disagreeing is a finding rather than a surprise. Everything else in this pipeline budgets
  against an estimate, and an estimate that is never reconciled is how a ceiling drifts until the
  bill arrives.

  It is also simply the right shape for a field called `aggregator`: one key reaches many models.
  Verified against the [OpenRouter image-generation docs](https://openrouter.ai/docs/guides/overview/multimodal/image-generation)
  (2026-08-08) — `POST /api/v1/images`, bearer auth, `data[].b64_json`, `input_references` for a
  style reference. `gemini` still ships for talking to Google directly; there
  `actual_cost_usd` is **null** rather than back-filled from the estimate, because copying it would
  make the two agree by construction and hide the drift the field exists to show.

  Shipping one adapter had quietly made *"any provider meeting the contract is swappable"* a claim
  with a single implementation. Two is the smallest number that tests it.

- **The provider call was verified against the live API for the first time.** Every test in this
  pipeline is offline by design — a test that dials a provider to prove a refusal is a bill — so the
  adapter's request shape and response parsing had only ever been checked against documentation. A
  real call returned **HTTP 402**, and the status is the useful part: *402, not 401*, so the key
  authenticated and the endpoint, bearer header and body shape are all correct. The account simply
  has no credits. The failure path behaved as designed: the provider's own remedy reached the caller
  verbatim, and **nothing was written** — no asset file, no manifest row, no half-state to clean up.

- **The agent authors vector assets, and that is now the default.** Claude Code writes SVG natively
  and already holds the brand pack, the token names and the surrounding components — context a
  remote model does not have — so routing a vector asset through an external call bought a worse
  result at a cost. `aggregator: "agent"` runs the **whole gate** (library search, tier refusal,
  composed prompt, budget, provenance) and skips only the HTTP request, because the discipline was
  never the request. The agent writes the file, then `--record` **re-runs the gate** before the
  manifest accepts it: an agent-authored asset gets no easier route in than a purchased one, or
  *"the agent wrote it"* becomes the way past every refusal.

  Four defects surfaced while wiring it, each in something that looked finished. The key preflight
  ran **before** the adapter was chosen, so the one path that never calls an API refused for a
  credential it had no use for. `manifest_entry` referenced a local that no longer existed after
  being factored out — a `NameError` that only fired on the new path. `--record` built a manifest
  path with `relative_to` against a caller-supplied relative path. And a filename carried the model
  ID verbatim, so `cohere/x:free` produced a colon in a path that is legal here and hostile on
  Windows and in URLs.

- **Per-kind ladders, and two bugs that only surfaced by taking them seriously.** One global ladder
  forced every kind through whatever suited the most common one. Only some models emit SVG and no
  image endpoint emits video, so `kind: vector` wrote **PNG bytes to a `.svg`** and `kind: motion`
  wrote **a still frame to a `.webm`** — files that open, look plausible in a listing, and are the
  wrong format. The extension is now **sniffed from the bytes**, never derived from the request, and
  a `vector` request whose model returned a raster **refuses** rather than saving it: a raster named
  `.svg` does not scale and cannot be recoloured from tokens, which is the entire reason that kind
  exists. The scaffold ships `motion` **empty on purpose**, so a motion row refuses with *"no ladder
  for kind 'motion'"* until a video model is configured.

- **Both scaffolded model IDs were invented from prose, and both 404'd.** `recraft-ai/recraft-v3-svg`
  and `google/gemini-2.5-flash-image` do not exist; the real ones are `recraft/recraft-v4.1-vector`
  and `google/gemini-3.1-flash-lite-image`. They were written from a documentation sentence rather
  than from the provider, which is the transcription this repo's own `derived-artifacts` skill warns
  about — in the file that spends money. All IDs are now **verified against the live model list**,
  and `--discover` refreshes them so nobody depends on a hardcoded list ageing quietly.

  `cost_usd` is **not** verified and cannot be: that endpoint does not expose pricing. Every price in
  the scaffold is a placeholder the user must replace, and `--discover` says so rather than
  back-filling a number nobody chose.

- **The agent generates by default, and the scaffold no longer writes an API key at all.** A
  connected provider MCP (OpenRouter's `generate-image`) or the agent's own SVG covers the
  interactive case entirely — no key, no `.env`, no adapter code, and one fewer credential to leak.
  The gate is unchanged: it approves, hands back a brief, and `--record` **re-runs the whole gate**
  before the manifest accepts the file, because an agent-authored asset must get no easier route in
  than a purchased one.

  Scaffolding `api_key_env` was itself the defect underneath the earlier `.env` bug: naming a
  variable the default path never reads is how a placeholder became a documented step for a route
  that could not use it. It is written only when someone chooses a non-agent aggregator.

  **The HTTP adapters stay, scoped to one case** — an unattended run with no agent in the loop,
  which cannot call an MCP and must fetch bytes itself. That path needs a key; the default does not.

  **Cost is unchanged by any of this.** An MCP `generate-image` call bills the same account as the
  HTTP one; only vector-via-agent is genuinely free. Measured, not assumed: `get-credits` reports
  **0**, which is the same wall the HTTP path hit with a 402.

- **The invented prices are gone, and an unpriced rung now REFUSES.** Removing them exposed
  something worse than the placeholders: a missing `cost_usd` defaulted to **0**, so an unpriced
  model cost nothing, the budget could never refuse it, and the ceiling was unreachable — a gate
  that cannot fail, guarding the one thing here with a bill attached. The scaffold ships prices
  **unset** because the provider does not report them and an invented number is worse than an
  absent one: it looks authoritative and the budget then approves or refuses against a figure nobody
  chose. `0.0` on the agent rung stays, because there it is a measured fact rather than a guess.

- **The rung chooses the adapter.** Per-kind ladders imply per-rung adapters, and only the global
  `aggregator` was consulted — so a `vector` ladder whose rung is `agent` was routed through the
  project's image aggregator and asked for an API key it would never use. This is also what makes an
  **MCP** path work with no new code: set the rung to `agent`, obtain the asset however you like,
  and `--record` re-runs the gate before the manifest accepts it.

- **Exit 0 stopped meaning "done".** The agent path exits 0 while handing back a *brief*, so reading
  the return code alone marked rows `done` with `file: null` and nothing on disk — the exact
  *"recorded from what was attempted"* failure this file's own docstring forbids. A row is `done`
  only when a file is named **and exists**; an approved-but-unwritten row is **`awaiting-agent`**,
  which counts as outstanding, and a run reporting success with no file is `failed`.

- **The full pipeline was proven end to end at zero cost.** No image model on OpenRouter has a
  `:free` variant — checked across both endpoints, 42 models — but text models do, and the SVG path
  needs one. A complete run (`scaffold → research → plan → check → run`) produced a **valid SVG**, a
  complete manifest row, and a plan row marked `done`. The agent path was then proven the same way,
  needing no key at all.

### 1.19.0 — 2026-08-08

- **Research is now a precondition of the asset plan**, checked rather than advised. The ordering is
  not cosmetic: research settles the **style**, and the style settles which assets exist at all — a
  `minimalist-ink` family needs line art on brand grounds while a `character-world` family needs a
  recurring cast, which is different rows, different counts and different money. The failure is
  invisible without a check, because a plan written without research looks exactly like one written
  with it: every row complete, and nothing recording that the look came from the median.

- **Affordability is group-atomic, not row-greedy.** Assets are not independent — a hero still and
  the motion loop that animates it are one artefact in two files, and buying the loop alone is worse
  than buying neither, because you pay for something unusable. Rows may declare a `group`, a group is
  bought whole or skipped entirely, and a cheaper later group may still be taken: the aim is the best
  **usable** combination, not the longest list of files. A group takes its best member's priority, so
  marking one row urgent pulls its partner along instead of orphaning it.

### 1.18.0 — 2026-08-08

- **`/design-flow:assets` — the setup and drive command for the curated library** (Refs #507).
  Scaffolds config and plan, pins the brief, checks the plan is reviewable, generates what is
  outstanding and records what happened. **Re-running resumes rather than resets** — a `done` row is
  never re-bought, and a second scaffold re-pins the brief and changes nothing else, because a setup
  command that resets a user's rows is not idempotent, it is destructive.

- **Three files, three jobs.** The config says *how to buy*; `plan.json` says *what the product
  needs*; `manifest.json` says *what the project owns*. **The gap between the last two is the
  remaining work**, which is the whole reason both exist — keep only the manifest and a library
  nobody has finished planning looks finished.

- **The plan is costed before anything is generated**, and the run refuses when the budget cannot
  finish it. That is the point: generating until the money stops leaves an **arbitrary** half of the
  set, and a half-built family of illustrations is not a cheaper library, it is an incoherent one.
  The refusal prints the shortfall and what fits by priority; `--confirm-partial` then generates
  exactly that and leaves the rest `planned` — not `failed`, because they were never attempted.

  Three caveats are printed rather than hidden: the estimate is a **floor** (every row priced at the
  cheapest rung), rows with no `priority` were split by **plan order** and the run says how many, and
  `--spent` is an **input** because nothing here can read a provider balance.

- **Two kinds of drift are now detectable, neither visible any other way.** A **PRD fingerprint**
  catches a plan written against a brief that has since moved — every row `done`, the status clean,
  and the new surfaces with no rows at all. And **reconciliation** reports any manifest entry with no
  plan row: an agent generating ad-hoc must add the row with its rationale and use cases, or the
  plan stops describing the library it tracks and the gap above stops meaning anything.

- **Two defects were caught by the checks themselves while building this.** `--check` blessed an
  **empty** plan — the exact state the scaffold creates — while a comment three lines above claimed
  that case was covered. And a plan row whose surface had no brief passed review and failed at run
  time, after the spend; the cross-check moves that finding to before it. A mutation also **survived**
  because it was written as `[] or [...]`, which evaluates to the original list — the harness
  reporting a survivor was reporting a bad mutation, and it was right to.

### 1.17.0 — 2026-08-08

- **`/design-flow:generate` produces now, not just decides** (Refs #507). `generate_asset.py`
  preflights the key, calls the provider, saves the asset and appends its manifest row. It is a
  **separate script from the gate on purpose**: a decider that also spent could prefer the decision
  that justified the spend it wanted.

- **It re-runs the gate rather than accepting an approval.** Handing the executor a hand-written
  `{"approved": true}` would bypass every refusal at once — library check, tier precondition,
  composed prompt, budget ceiling — so it takes the *request* and runs the gate in-process
  immediately before the call. An approval that cannot be forged is worth more than one that is
  convenient to pass around, and a mutation proves a forged one never reaches a provider.

- **The key preflight has three outcomes, not two.** Absent means *"you have not set this up"*;
  placeholder means *"you scaffolded it and never filled it in"* — only the second is a forgotten
  step, and collapsing them sends people to re-read instructions they already followed. The
  placeholder pattern is **anchored**, so a real key merely containing `changeme` is still accepted;
  an over-eager matcher would block a working setup, which is worse than the problem it solves. The
  key is never printed, logged, or written into provenance.

  Both key states **refuse (exit 1)** rather than erroring, which corrected an inconsistency shipped
  in the same session: a missing *aggregator* refused while a missing *key* errored, though both mean
  the same thing. A caller must be able to tell *"not generating, that is fine"* from *"something is
  broken"* by exit code alone.

### 1.16.0 — 2026-08-08

- **`/design-flow:generate` — the pay-as-you-go asset path, as machinery rather than advice**
  (Refs #507). Three of its four requirements are checkable, so writing them as prose would be the
  defect this repo is built around — the precedent is #161, where the README *mandated*
  `--max-total-usd` while the flag stayed optional. `generation_gate.py` refuses on each, before any
  call: an unsearched library, an unrecorded tier-1/2 refusal, a free-typed prompt, a missing
  aggregator, a projected cost over the ceiling, or a ladder climb with no stated acceptance check.
  **Refusal is the working state** — a run of this path that always approves has been mis-wired.

- **The library is curated once and topped up, never commissioned piece by piece.** Seeded after the
  PRD becomes skills and the product intent is settled, **before any coding**, so the set is chosen
  against what the product actually is. Generating per-surface as work arrives produces a pile rather
  than a set: each piece defensible alone and the family incoherent, which is the look the whole path
  exists to avoid. Afterwards it grows by **coverage, never duplication** — the gate refuses a
  request whose surface and kind the manifest already lists, because a second one silently forks that
  surface's look.

- **The manifest is a reference table, not an inventory.** It answers the question an agent actually
  asks — *may I put this here, and will it look right?* — so every entry carries purpose, use cases,
  **where it must not go**, visual elements, style, kind and surface. A row naming only a file gets
  the asset re-generated by whoever could not tell. `--check-library` enforces the schema per field,
  because "entry 3 is incomplete" sends someone to re-read a row while "entry 3 has no `avoid`" is
  the fix. `avoid` is the field most often skipped and the one that matters most: without it a
  curated family drifts by well-meaning reuse, one reasonable placement at a time.

- **`style` is a closed taxonomy, and that came from looking rather than reasoning.** Screenshotting
  a survey of brands that do this well made the gap obvious: Mailchimp is monochrome ink line-work on
  a saturated brand ground, Headspace is flat vector with rounded characters and faces reduced to two
  dots and a curve. **Both are on-brand — for different brands.** A brief saying only *"calm,
  abstract"* renders as either, so two runs against one pack drift and the second is a reroll nobody
  planned to pay for. Two findings worth acting on came with it: `geometric` is usually satisfiable
  at **tier 2** for nothing, and in the strongest examples the drawing is monochrome on a
  brand-coloured panel — so generate line art, let CSS carry the colour, and a pack swap costs
  nothing.

- **The aggregator contract is named; the vendors are not.** Text-to-image, a **style reference
  image**, and a readable per-request price. Model names live in project config and never in
  doctrine, because they change monthly and a list in a skill rots inside a quarter — the command
  cites Google's current image models as a worked example only, with the ladder they actually expose
  ([model IDs](https://ai.google.dev/gemini-api/docs/image-generation), checked 2026-08-08).

  9 mutations, all caught; 38 selftest assertions. Two of those fixtures were written wrong first and
  the selftest caught it: a library fixture had no brief for its surface, so it refused for a missing
  brief and the library logic it existed to test was never reached — one fixture stealing another's
  verdict.

### 1.15.3 — 2026-08-08

- **`@variant dark` should be `@custom-variant dark`** (Refs #555). The scaffold emitted the
  directive that **applies** an existing variant where it needed the one that **defines** a new one.
  Tailwind v4 is explicit about the split — `@custom-variant dark (&:where(.dark, .dark *));` is the
  form the dark-mode page itself shows, while `@variant` is for applying a variant inside a CSS rule
  ([dark mode](https://tailwindcss.com/docs/dark-mode),
  [functions and directives](https://tailwindcss.com/docs/functions-and-directives), verified
  2026-08-08 against Tailwind v4).

  Low severity by design: `tailwindcss:build` exits **0** either way, which is exactly why it
  survived — a non-canonical directive that never fails loudly is one a scaffold repeats forever.
  Corrected in both places that emit it, `foundations-tokens.md:84` and this command's step 1.

  Worth recording for whoever touches this next: of **seven** `@variant` occurrences in shipped
  content, only **two** are the CSS directive. The other five are Ruby instance variables
  (`@variant = variant.to_sym`, `VARIANT.fetch(@variant)`), so a blind replace corrupts five
  components to fix two lines.

### 1.15.2 — 2026-08-07

- **The setup step flattened the toast's conditional role, which is an accessibility regression**
  (Refs #483). Shipped doctrine renders
  `role="<%= intent == :error ? 'alert' : 'status' %>"`; step 4b told the scaffolder the toast
  *"carries `role="status"` and nothing beside it"*. That misread the doctrine's *"the ROLE carries
  the severity, and nothing beside it"* — a sentence about **not adding `aria-live`**, not about
  fixing the role's value.

  It fails silently and only for screen-reader users. `status` implies `aria-live="polite"`, `alert`
  implies `assertive`, so a toast hard-coded to `status` announces an error politely and the user
  hears it after whatever is already queued. Nothing renders wrong and no test goes red.

  Found while checking #483's remaining acceptance criterion, and **grepped for as a class** rather
  than fixed in place: of the four conditional roles in shipped doctrine, this was the only one a
  plugin restated as a literal. Stating that as a measured negative, not an assumption.

  New `flattened-conditional-role` gate in `lint_self_consistency.py` — if doctrine renders a role
  conditionally, a plugin paragraph naming one branch must name the other. **The rule's first version
  fired on the fix for the defect it was built to catch**: it required the sibling to appear as a
  second `role="…"` literal, which no correct paragraph does. It now counts the sibling as named
  anywhere in the paragraph, and a fixture pins that direction.

- **#483's own acceptance criterion 3 is stale.** It reads *"flashes route to auto-dismissing toasts
  by default (errors persist)"*. Errors **no longer persist** — v1.72.0 established that
  `role="alert"` governs announcement, not lifetime, and that a persistent message is a Banner or an
  `Ui::Alert`, with `:loading` the single persistent toast. Anyone verifying the last box against the
  issue text as written would file a false regression.

### 1.15.0 — 2026-08-06

- **The critic is wired into the review path, alongside the gate rather than inside it** (Refs #486).
  `/design-flow:audit` now says to run `/design-flow:critique` **as well**, with the division stated: the
  audit asks *is this correct* and blocks; the critique asks *is this considered* and does not. A surface
  can pass every check the auditor makes and still be flat — correct tokens, correct variants, correct
  a11y, no focal point — and that is the half the gate deliberately does not own. Their findings are kept
  **unmerged** on purpose: a `file:line` fix and a missing decision carry different authority, and
  putting them in one list means the reader cannot tell which blocks.

  `/design-flow:variants` gains the critic as its **ranking rubric** (criterion 7). That command
  produces N conformant variants and then asks a human to choose with nothing to choose *on* —
  conformance cannot rank, because every variant is conformant by construction. The critic ranks on
  brief-fit first, craft second. Note the division: the winner still goes to the consistency gate
  *after*; all N go to the lens *before*.

### 1.14.0 — 2026-08-06

- **`design-critic` gains asset fitness, kept separate from taste** (Refs #507). It could already see
  images — `Read` renders them — but its instructions only described judging markup. Now: fitness first,
  returning **pass/fail with the clause that failed**, then taste only if fitness passes. The rule that
  matters is the one against blending them — *"do not soften a fitness fail into a taste suggestion"* —
  because they carry different authority, and downgrading the first into the second is exactly how an
  unchecked asset reaches a page. `/design-flow:critique` documents the carve-out: the command is
  advisory, and that stance explicitly **does not cover** a fitness verdict.

### 1.13.1 — 2026-08-06

- **Five commands read a skill that ships in another plugin, and none checked it was there** (Refs
  #513). All four design-flow agents and five of its commands read `skills/fidara-design`, which ships
  only inside the **`rails-stack`** bundle — and no `plugin.json` carries a `requires` field, so nothing
  *can* declare the pairing. `/plugin install design-flow@claude-skills` alone therefore yields agents
  whose own text calls that doctrine *"the law"* about a file that is absent, with no warning; the
  likely outcome is the worst one, an agent improvising a catalog. Each of the five now carries a
  precondition that names what is missing (`/plugin install rails-stack@claude-skills`) and **stops** —
  the pattern this repo already uses in six commands for `gh`, Playwright and cloud credentials.

### 1.13.0 — 2026-08-05

- **`design-critic` + `/design-flow:critique` — the lens, not a gate** (Refs #486). Three agents
  existed and all three were correctness roles. The critic judges hierarchy, focal point and
  brief-fit, and returns **ranked suggestions with the missing decision named** — never a pass, a
  fail, a score threshold or a merge condition. That is not timidity: **#476** proved a taste gate
  cannot hold, because its threshold flagged our own worked band sequence, and a gate that gets
  switched off leaves nothing checking anything.

  Two boundaries are load-bearing. **Consistency findings are explicitly not the critic's** — raw
  hex, missing `aria-*`, off-catalog variant all belong to `design-auditor`, because two roles
  grading one thing disagree in front of the user and the blocking one wins. And the critic has
  **`Read, Grep, Glob` only** — no `Edit`, no `Write`, no `Bash` — since a lens that rewrites what it
  judges stops being a second opinion.

### 1.12.2 — 2026-08-05

- **Three Stimulus controllers shipped orphaned, and the CRUD success path had no target** (Refs
  #483). `/design-flow:setup` listed the `toast` controller in step 4 while step 3's component list
  omitted the component it drives — and pointed at `reference-implementation.md` as *canonical for
  steps 3–4*, which carries both. The enumeration and its own canonical source disagreed, and agents
  follow the enumeration. **Worse than dead code:** `crud-modal-pattern.md` emits every success with
  `turbo_stream.prepend("toasts", ToastComponent.new(...))` — three call sites in the doctrine — so
  with no `#toasts` container in the layout, **every CRUD success silently dropped its feedback**.
  Writing the join instead of patching the report found `dropdown` and `tabs` in the same state,
  which #483 did not mention. The scaffold now prescribes `Ui::Toast`, `Ui::Dropdown`, `Ui::Tabs` and
  the `#toasts` container, with `aria-live` on the **container** (it must be in the DOM before
  content is inserted) and `role="status"` on the toast — plus the rule that Turbo-Stream flash
  **replaces** the `_flash` partial pair rather than sitting beside it, which is how a project ends
  up with two notification surfaces and no auto-dismiss anywhere.

### 1.12.1 — 2026-08-02

- **The "don't start a second server" guard could not fire in the case that does the damage**
  (Refs #108). The reuse probe was `curl -fsS`, and `-f` exits non-zero on 4xx/5xx — so an app
  that is **up with a failing health endpoint** was indistinguishable from an empty port (exit 22
  vs exit 7; both merely "non-zero" to an `if`). Measured, not assumed. The probe now reads
  curl's `http_code`, which is `000` only when no HTTP response arrived, so anything speaking
  HTTP is reused whatever it thinks of its own health. The stale branch also printed *"nothing on
  the port"* — false, and it sent the operator to boot a server already running.

### 1.12.0 — 2026-08-01

- **NEW `/design-flow:variants <brief> [--variants N]` — N brand-conformant compositions of one
  brief plus a live comparison switcher** (#160). Borrowed in shape from
  [emilkowalski/skills](https://github.com/emilkowalski/skills). One-shot generation is right when
  there is a correct answer; for a hero or a pricing page it invites a yes/no, which tends to
  become yes. Variants make the human a **chooser** rather than an approver. Change type:
  **design/architecture** — the workflow, the scaffold layout and the composition-only contract are
  ours, and the authority is the maintainer decision recorded on
  [#160](https://github.com/fmanimashaun/claude-skills/issues/160), not a citation. The one
  externally-verifiable half is **reused, not invented**: the switcher is `turbo_frame_tag` plus
  `data-turbo-frame` links, the same mechanism `crud-modal-pattern.md:7` and
  `skills/hotwire/references/turbo.md:141` already ship, so no new framework surface enters a skill.
- **The constraint is checked, not stated** — `variant_conformance.py`, ten named rules, each
  citing what it enforces. Every variant is fully brand-conformant and they differ in **composition
  only**: same role tokens, same components, same API. That sentence in prose with nothing making it
  true is the claims-vs-enforcement defect this repo warns about most, and it is the exact sentence
  that keeps variant mode from becoming the style menu we declined with ui-ux-pro-max.
- **#160's own acceptance criterion 2 was half a category error, and implementing it as written
  would have shipped a gate that cannot run.** It asks for conformance *"asserted by running
  `brand_pack_lint` and the #157 detector against each [variant]"*. The detector takes file paths,
  so per-variant is exactly right and it is **run rather than reimplemented** — a second copy of its
  seven rules is the duplication #157 criterion 7 already forbade. `brand_pack_lint.py` takes a
  brand-pack *directory* and validates `brand.json` + `theme.css`; a variant is a set of `.html.erb`
  partials. It cannot be run against one, and it should not be — pack completeness is a property of
  the **pack**, identical for all N variants, so running it N times proves one thing N times and
  nothing about the variants. It runs once, in Phase 0, and the per-set invariants neither existing
  check covers became the new script.
- **The rule the detector could not have carried: `variant-names-pack-primitive`.** `brand.md:78-82`
  says components consume roles only and nothing outside a pack may name a primitive — but knowing
  whether `fm-navy` *is* a primitive requires reading the pack's `@theme` block, and the detector is
  context-free by design. Same split as `rendered_conformance.py` (needs a browser) versus
  `llm_tell_detector.py` (needs nothing): a real difference in what the check must be handed. The
  `@theme inline` role layer is skipped, because flagging `bg-primary` would invert the rule and
  report a finding on every correct variant — fixtured in both directions.
- **A rule that did not run is reported as a finding, never as silence.** If the manifest's brand
  cannot be resolved to a pack, the primitive check emits *"could not run — a rule that did not run
  is not a pass"*. Likewise a run that examined **zero** variant sets exits **2**, not 0: no
  findings over no input is indistinguishable from a pass, the shape this repo keeps catching in its
  own gates.
- **`variant-switcher-unguarded` is an omission from #160, not a criterion in it.** A switcher route
  renders every *rejected* variant, so leaving it reachable in production ships three landing pages
  nobody approved. The command guards it with `Rails.env.development?` and constrains the slug; the
  check tracks routes.rb block nesting so a **closed** development block cannot launder a later
  route — the failure mode of the naive backwards search, and its own fixture.
- **`variant-set-not-distinct` detects identity, never similarity.** "These two feel samey" is taste,
  and a rule that cries wolf gets switched off. The signature is the ordered structural tags plus
  render targets, so two variants whose copy differs but whose arrangement does not are still caught
  — with the near-miss (two genuinely different arrangements) fixtured as SILENCE.
- **Criterion 5 is a check, not a sentence.** `--verify-discard` asserts the views, the controller
  and the route are all gone once a variant is chosen, because an un-run discard step looks exactly
  like a completed one. `/design-flow:audit` gained leftover variant scaffolding as a drift class
  for the same reason.
- Selftest: **36 checks across 10 rules, eleven of them SILENCE fixtures**, and **three of the ten
  declared mutations are caught by a silence fixture rather than a firing one**. That is where the
  risk is: every rule here has an obvious over-broad form (`bg-primary` is a role token *and* a
  string ending in a primitive's suffix; an ERB comment naming `--color-x:` is prose *and* a
  custom-property declaration; `# do not remove` ends in a block opener), and flagging the wrong
  half makes the checker report findings on every correct set it is given.
- **FIX — design-flow's only project check had never once run, and could not have passed if it
  had.** `checks.json`'s `brand-pack` entry named `app/assets/stylesheets/brand`, a path
  `/design-flow:setup` never creates (packs live in `brands/<slug>/`), so it was permanently NOT
  APPLICABLE — and it passed `brand_pack_lint.py` no pack directory, so on the one repo where it did
  apply it would have exited 2 on a usage error. Found while registering the variant check beside
  it. `project_gates.py --selftest` validates that a shipped command names a real script and supplies
  any required subcommand; neither of those is wrong here, which is the blind spot: nothing asserts
  that a shipped check's `applies_when` names a path the plugin actually generates.
- **NEW `palette_candidates.py` — ten measured starting palettes, plus the snap path for a client's
  own brand colour** (#129). A pack cannot be finished without a palette and a new client routinely
  arrives with a logo and a vibe, so authoring one by hand was slow and its quality depended on who
  was doing it that day. **Change type: design/architecture** — the candidate set, the selection
  path and where it plugs into onboarding are our own brand-pack model, with no upstream; the
  authority is the maintainer decision recorded on
  [#129](https://github.com/fmanimashaun/claude-skills/issues/129) and its
  [coordination comment](https://github.com/fmanimashaun/claude-skills/issues/129#issuecomment-5097854818).
  The contrast half is split out below and carries citations instead.
  - **One mechanism, two entry points.** A palette is stored as a handful of anchors and composed
    through `snap()` into the whole role contract, so "snap the client's colours to our role
    structure" is not a second feature — it is the same function with anchors derived from their
    hex. The role names come from `brand_pack_lint.ROLES` rather than a local copy, so a role added
    to the contract makes the composer fail loudly instead of quietly emitting a pack with a hole.
  - **140 text pairs measured, none asserted.** 10 candidates × 7 pairs × 2 modes, all ≥ 4.5:1;
    worst is 5.15:1. `--check` is a gate. A palette that fails contrast is worse than no palette,
    because it ships in a client's colours and nobody re-checks it.
  - `--snap "#RRGGBB"` reports the **nearest passing colour of the same hue** with both numbers
    when a client's colour cannot carry a role, because *"your red is 3.1:1, this one is 4.6:1"* is
    a conversation and *"it fails"* is an argument. Their **mark keeps their exact colour** — WCAG
    1.4.3 exempts logotypes; only the `--primary` role moves.
  - `--measure <pack>` exists because `--emit` writes a pack that then gets **edited**. Without it,
    the "re-measure this" line the tool writes into every pack it generates would be a
    claims-vs-enforcement defect authored by the tool itself.
  - An emitted manifest carries `chart_palette_validated: false` and therefore **fails the pack
    lint on purpose**: this script has not run the chart validator, and claiming a result it did
    not produce is the one thing a manifest must never do.
  - **Six type pairings, offered rather than prompted**, per the maintainer's coordination note:
    omitting `fonts` inherits the system stack and inheriting is the right default.
  - **#129 asked for per-pairing fluid type steps and they are deliberately NOT shipped.**
    `--text-step-*` is a system-owned axis — brand.md's own table puts the spacing/type scale in
    the "system owns, never in a pack" column — so a scale per pairing would fork the very axis the
    pack model exists to keep central. A pairing carries three family names and nothing else, and
    `--check` fails if one ever grows more.
  - 51 selftest checks, 16 declared mutations. Roughly half break a fixture whose job is to stay
    **silent**: a tool that rewrites a brand colour which was already fine gets switched off, and
    then nothing measures the one that was not.

- **FIX — the fidara brand pack still carried both #304 contrast defects, months after #304 was
  fixed** (#129, found while measuring candidates). `check_token_contrast.py` read exactly one
  file, `foundations-tokens.md`. The pack `/design-flow:setup fidara` actually reads — the bytes a
  user's app is built from — had `--primary: #0077CC` at **4.42:1** on `--background`, and a
  `.dark` block re-pointing `--primary` **without** `--primary-foreground`, leaving white on
  `#00A3FF` at **2.73:1** on every primary button in dark mode. Those are #304's two defects,
  verbatim, in the shipped artifact, while the gate written to catch them reported clean over the
  one file that had been fixed. **Change type: externally verifiable** — WCAG 2.2 SC 1.4.3 (Level
  AA), 4.5:1 for normal text: https://www.w3.org/TR/WCAG22/#contrast-minimum. Now 4.74:1 and
  6.30:1, matching the doctrine file exactly.

- **FIX — `_template` failed three text pairs, and it is the file every client pack is copied
  from** (#129). `--primary` 4.38:1 in light; `--primary` never lifted for dark surfaces (3.94:1 on
  the page, 3.44:1 on a card, because `.dark` re-pointed it to the same light value); and
  `--muted-foreground` at **2.71:1**, which is helper text, timestamps and table meta on every
  screen. A template that ships unreadable defaults teaches the failure to every pack copied from
  it. Same citation as above; all six light/dark pairs now ≥ 5.17:1.

### 1.11.0 — 2026-08-01

- **NEW `llm_tell_detector.py` — an offline detector for LLM design tells** (#157). Stdlib only, no
  browser, no API key. Borrowed in *shape* from [impeccable](https://github.com/pbakaus/impeccable):
  every rule is **named**, so it can be argued with and disabled individually, and **a disable must
  carry a reason** — a bare one is itself a finding. That is the mechanism `brand_pack_lint.py`
  lacks, and without it the first justified exception is what teaches everyone to switch a checker
  off wholesale.
- **The rule set is seven, not the twelve #157 listed, and the arithmetic is the point.** Criterion 3
  requires each rule to cite doctrine, since *"a rule with no doctrine behind it is taste"*.
  Grounding all twelve eliminated five: **two are prescribed by our own doctrine** —
  `components.md:185` mandates `backdrop-blur-sm` for the modal backdrop and `components.md:658`
  mandates `animate-pulse` for skeletons, so "glassmorphism" and "pulsing" rules would fire on the
  reference implementations they enforce — and **three need rendered output or page structure** a
  static scan cannot see (ghost-cards is a contrast measurement, and belongs to #107).
- **Two of the seven find outright bugs rather than drift.** `bg-gradient-to-*` was *removed* in
  Tailwind v4 with no alias and `duration-fast` never existed (there is no `--duration-*` theme
  namespace), so both emit **no CSS at all** — the markup looks right, renders wrong, and nothing
  raises anywhere.
- **Criterion 6 (zero findings against our own reference implementations) earned its place
  immediately.** Its first run produced 11 findings against our own doctrine, both of them real rule
  bugs: `raw-hex-literal` flagged the token *definitions* (`--color-fm-navy: #0C1B33` — a custom
  property IS the token layer the rule protects), and `off-scale-radius` flagged a comment reading
  *"NOT an arbitrary `rounded-[12px]`"*. Now a gate, so neither can come back.
- **The two scanners had already drifted, and unifying them was the fix.** The markdown path never
  called `rule.exempt`, so the same `--color-fm-navy: #0C1B33` was exempt in a `.css` file and a
  finding in our token doc. There is now one `_scan_line`; patching the copy would only have
  deferred the next divergence.
- **Criterion 7 (the palette rule defined once, shared with #107) was nearly violated silently** —
  `PALETTE_STEP` was imported and then hand-copied into the rule. The alternation is now derived
  from the shared pattern's own source, and a shape change fails loudly at import instead of
  matching nothing.
- **Wired as a PostToolUse hook** on `Edit|Write|MultiEdit` for view and component surfaces, and as
  a second step in `/design-flow:audit`. **Advisory, therefore fail-open** per the
  guarantee-vs-advice test in `docs/harness-doctrine.md` — verified by running it with `python3`
  shadowed by a stub that exits 127 (exit 0, silent). design-flow had no `hooks/` directory before
  this; hooks load by convention, exactly as rails-flow's do.
- Detector selftest: **40 checks across 7 rules**. Five declared mutations, all caught by their own
  named fixture — **three of them are bugs that were actually in the first draft**, including an
  `ease-in-out` lookahead that excused the single most common instance of the tell it detects.
  Gate sweep 41 → **43**.

### 1.10.1 — 2026-08-01

- **`design-auditor` reports stock LLM phrasing as a count** (#131). Marketing copy using
  `leverage`, `seamless(ly)`, `elevate`, `unlock`, `empower`, `robust`, `cutting-edge` — **reported,
  never failed on**. A word has legitimate uses (*"Unlock your first report"* is a real CTA), so one
  is a word choice and six is a draft nobody edited. Marketing surfaces only: never documentation,
  where `harness` and `elevate` are ordinary technical vocabulary.

### 1.10.0 — 2026-08-01

- **design-flow's brand-pack lint is runnable as a gate in a user's CI** (#334). A `checks.json`
  registers it with `project_gates.py`, applying only where `app/assets/stylesheets/brand` exists
  — reported as **not applicable** elsewhere, never as a pass. The rendered-conformance linter is
  deliberately excluded for the browser-dependency reason above.

### 1.9.1 — 2026-08-01

- **FIX — two pointers added in v1.9.0 named a directory that does not exist.** `design-auditor`'s
  new Marketing-copy and Visual-assets checklist rows pointed at `references/marketing-copy.md` and
  `references/visual-assets.md`. There is no `plugins/design-flow/references/`; the files live under
  `skills/fidara-design/references/`. An agent following either found nothing.
  - **The same commit got this right three times and wrong twice**, which is the part worth
    recording. `/design-flow:component`'s three pointers were written as full paths *specifically*
    so the doc-pointer lint would validate them — and the auditor's two were not, so the lint could
    not see them. The rule only protects what is written in the form it recognises, so a
    half-applied convention reads as covered while leaving a real broken pointer behind.
  - Found by re-reading the shipped tag when asked whether the wiring was actually in place, rather
    than by any gate. Grepping the pattern then found two more bare pointers in other plugins
    (`a11y-auditor`, `setup-flow`) — not broken, since each names its skill, but invisible to the
    lint for the same reason. All four are full paths now: **65 → 70** pointers validated.
  - `skill-curator`'s `references/` is deliberately left alone: it names a *directory convention*,
    not a file, so there is nothing to resolve.

### 1.9.0 — 2026-08-01

- **`design-auditor` counts the per-page motion cap** (#136) — one entrance pattern per
  page, at most three animated regions, never two at once in the viewport. The rule itself is
  rails-stack doctrine (`motion.md` §14); this is the half that enforces it, and it is the one
  motion check that is arithmetic rather than judgement.
- **The marketing doctrine is wired into the flow that uses it** (#131, #135, #136). Three reference
  files shipped in earlier releases — `marketing-copy.md`, `visual-assets.md`, `motion.md` — and
  each carried the same open acceptance criterion: *`/design-flow:component` consults it, and
  `design-auditor` gains the mechanical checks*. Doctrine nothing consults is the
  `claims-vs-enforcement` class one level up: the file exists, and the agent that should read it
  never learns it is there.
  - **`/design-flow:component`** now branches on the surface. A marketing surface — landing,
    pricing, feature section, hero — makes all three references mandatory before markup, each
    answering something the component catalog does not. The copy rule is the load-bearing one:
    **draft against the contract, never invent positioning**, and if the claim is unknown say so in
    the output rather than filling the slot. A confident placeholder is worse than an obvious one.
  - **`design-auditor`** gains three grep-able checks and two checklist sections. The greps are the
    unambiguous half — placeholder copy (`lorem`, `TODO`, `Your headline here`), decorative visuals
    missing `aria-hidden`, and raw hex in illustration or geometry, with `Ui::Logo` as the one
    documented exception brand.md allows. The checklist half covers what a grep cannot read for, and
    says plainly that copy is a positioning decision the human owns.
  - **The three pointers are full paths on purpose**, so `lint_self_consistency.py`'s doc-pointer
    rule validates that each target exists: 62 → **65** pointers checked. Proven by renaming one to
    `moshun.md`, which the linter caught. A bare filename would have been prose.

### 1.8.0 — 2026-08-01

- **Agent model pins reconciled with the tier doctrine** (#299). Every agent moved from a
  `sonnet` pin — which is a **cap**, since frontmatter resolves above the session model — to
  `inherit`. The full argument, the per-agent table and the reasoning for this plugin's tier
  split are in its new `reference/model-tiers.md`, reconciled against the shipped agents by a
  gate in `--gates` so the table cannot drift back into folklore.
- **Two `NOT COVERED` notes in `rendered_conformance.py` went stale when their blockers were
  fixed** (#305, #306). A stale *"we cannot check this, our own doctrine contradicts it"* is worse
  than no note: it tells the next author a blocker still stands. `chrome-vs-content type step` is
  now **UNBLOCKED** and carries the exception list, because its failure mode inverted; the
  forced-colors focus item keeps its counted-fact status for a narrower reason and points at the
  lint rule that holds our own doctrine to it.

### 1.7.0 — 2026-07-31
- **NEW — `/design-flow:audit` gains a browser mode: conformance measured on the RENDERED page,
  not grepped from source (#107).** A source grep cannot see what the cascade resolves to — a
  colour injected by a third-party partial, a role token that never resolved, a focus rule that no
  longer matches the element it was written for. Two new files: `scripts/conformance_collector.js`
  (runs in the page via Playwright, reusing qa-flow's `app:` launch config rather than inventing a
  second boot path) and `scripts/rendered_conformance.py` (11 named rules plus two snapshot guards, over the resulting
  snapshot JSON).

  **The browser measures; Python judges.** Nothing in the collector decides anything, which is
  what makes a browser-driven check testable offline: `--selftest` carries **86 assertions** and
  `scripts/mutation_check.py` **55 declared mutations**, every one caught by the intended fixture. It
  also disposes of the hardest correctness problem for free — the collector resolves each role
  token through the same browser in the same run, so comparing a rendered colour to a token is set
  membership, never colour-space arithmetic.

  Rules: `literal-colour`, `numbered-step-binding`, `focus-ring-missing`, `tap-target-small`,
  `icon-only-unnamed`, `aria-controls-no-expanded`, `horizontal-overflow`, `off-scale-type`,
  `radius-off-scale` (zero-tolerance) plus `dark-variant-sprawl` and `breakpoint-driven-layout`
  (count-based trends, thresholds tunable). Facts print even when clean — the `dark:` count, the
  breakpoint count and the radius-language distribution are the trend #107 asks for.

  **Three of #107's acceptance items are deliberately NOT implemented, because each would fire on
  doctrine-conformant input** — and a conformance linter that cries wolf is switched off, after
  which it catches nothing. px-space-off-the-fluid-scale contradicts our own *Control density*
  table (`px-3 py-2` comes from Tailwind's numeric scale, not `--space-*`); chrome-vs-content type
  step contradicts `component-implementations.md` in 6 places (filed as #306, with the
  forced-colors focus-ring gap as #305); and alpha-modified
  colours are unjudgeable without decomposing a `color-mix`, which the doctrine blesses anyway
  (`primary/90`, `ring-ring/30`). All three are recorded in the module docstring with the
  reasoning, not silently dropped.

  Externally verified rather than assumed, each load-bearing for a rule or a carve-out: Tailwind v4
  opacity modifiers compile to `color-mix(in oklab, … N%, transparent)`
  ([docs](https://tailwindcss.com/docs/colors), `oklab` per
  [tailwindlabs/tailwindcss#15201](https://github.com/tailwindlabs/tailwindcss/pull/15201)), so an
  opacity modifier always lands with alpha < 1; the v4 default palette is authored in `oklch()`;
  ring utilities are **box-shadow**, not outline ([docs](https://tailwindcss.com/docs/box-shadow)),
  so a shadow must count as a focus indicator or every conformant `focus-visible:ring-2` would be
  reported; and `box-shadow` **computes to `none`** in forced-colors mode
  ([css-color-adjust-1](https://drafts.csswg.org/css-color-adjust-1/)), reported as a counted fact
  rather than a finding for the same reason.

  **Two defects in this work were found by running it against a real browser, not by any fixture**,
  which is the argument for having done so. An inline-link target-size exemption written as
  "display starts with `inline`" silently exempted **every** native `<button>` (Chrome computes
  them `inline-block`), hiding the whole `tap-target-small` rule; and the radius rule counted the
  four corners of one element as four elements, so a single `rounded-[7px]` button reported as "4
  element(s)" and the distribution read four times too high. Both now have a fixture and a
  mutation. The first also moved a *judgement* out of the collector into Python where a fixture can
  see it — the collector reports `display`, and `is_inline_link_in_text` decides.

  The mutation check and a self-review against `skills/code-review/SKILL.md` then found nine more,
  all in this diff. The ones worth naming: `outline: 2px solid var(--ring)` written as the shorthand
  was read as *no* focus indicator, so the rule flagged the exact fix it recommends — and the fix
  for the forced-colors gap above; the printed `--schema` contract had already gone stale against
  the snapshot it documents, and is now compared mechanically against both the fields the rules read
  and the fields the collector emits, so it cannot drift again; `unreadableSheets` was collected and
  read by nothing; a guard no real Tailwind class could reach was deleted rather than covered by a
  fixture for a class nobody writes; two carve-outs were redundant with `is_visible`; two fixtures
  passed for the wrong reason (a foreign-schema one that would have failed the empty-basis guard
  instead, an invisible-outline one silenced by a zero width before the style test ran); and a
  docstring claim about `<sub>`/`<sup>`/`<small>` was wrong in its specifics — now the measured
  83.33% rather than an asserted 75%/80%.

  A shipped `.js` file is read by no markdown linter — the fenced-code checkers only see markdown —
  so `rendered_conformance.py --check-collector` `node --check`s it, and both it and the selftest
  are registered in `maintainer_doctor.py`'s gate sweep. It **skips loudly** when node is absent
  rather than failing the sweep for want of a binary, and the selftest proves that path is a skip
  by pointing it at a binary that cannot exist.

### 1.6.0 — 2026-07-31
- **FIX — two defects in the cross-check added hours earlier, both found by an external reviewer
  on the already-merged PR rather than by us.**
  - **A mention was accepted as a generation.** `setup_provides()`'s docstring claimed a key was
    named *"precisely at the step that generates the initializer setting it"*, while the code did
    set membership over the whole of `setup.md` — nothing associated a key with an initializer.
    True today only incidentally (the key occurs once, inside the generating step). Delete that
    step while leaving a prose mention anywhere, and the check reported clean while the
    `NoMethodError` it exists to prevent shipped. This is a **claims-vs-enforcement defect inside
    the guard written to catch that class**. A key now counts as provided only when one step both
    names `Rails.configuration.x.<key>` and generates `config/initializers/<key>.rb` — the exact
    filename the error path already prescribes, so tool and message now agree.
  - **An unreadable input reported as doctrine drift.** Doctrine files were read unguarded, so a
    non-UTF-8 or unreadable `.md` escaped as a traceback and exited **1** — the code reserved for
    "a depended-on config key is not generated" — sending a maintainer hunting a defect that does
    not exist. Reads are now guarded and raise `InputError`, mapping to **2** (environment).
    It **aborts rather than skips**: with one file unread the comparison is unsound in both
    directions, and a partial scan has no honest verdict.
  - `/design-flow:audit` said *"a non-zero exit is a toolchain defect"*, which conflates the two
    and would have had agents filing their own unreadable clone as a doctrine bug. It now reads
    the code: 1 = report it, 2 = fix your input.
  - **Fenced code no longer splits a step.** A shell comment at column 0 inside a ``` block
    matches the heading pattern exactly, and setup.md's own pack-resolution snippet contains two
    — so a step showing a code example *between* its initializer and its key read would have been
    reported as unprovided: a false drift error on correct input. Step splitting is now
    fence-aware; fence content is still scanned, it just cannot start a chunk.
  - Four fixtures and four declared mutations, one per defect plus a silent-skip guard. Fixtures
    G and I are the safe direction — the real multi-line step 7 shape, and a step containing a
    fenced example, must both stay clean, so the fix cannot over-correct into crying wolf.
    Fixture I's fence sits at **column 0** deliberately: indented, `^#` cannot match and the
    fixture would pass whether or not fences were tracked at all. It was caught being vacuous by
    `mutation_check.py`, which is the failure that tool exists for.

- **NEW `scripts/setup_doctrine_crosscheck.py`** — catches doctrine that references a runtime
  artefact `/design-flow:setup` never generates. The unit of dependency is a
  `Rails.configuration.x.<key>` read: doctrine reading a key setup does not generate is an
  **error** (it raises `NoMethodError` at a user's first setup run, in no test), setup generating
  config no doctrine reads is a **warning**. Deliberately narrow — a bare `config/initializers/*.rb`
  named in doctrine is *not* flagged, because `simple_form.rb` belongs to `/design-flow:component`,
  not setup, and flagging it would be the false positive that gets the check switched off. Proven
  against real history rather than asserted: exit 1 at `ced38c4` (the #104 defect) and exit 0 at
  `5902250` (its in-branch fix). A run that scans zero doctrine files exits **2**, not 0 — "no
  findings" over input it never read is the gate-that-cannot-fail shape, not a pass. Stdlib-only,
  wired into `/design-flow:audit` and the gate sweep, with 6 fixtures and 5 declared mutations in
  `scripts/mutation_check.py` — one per fixture, including the out-of-scope-initializer near-miss
  and the zero-input guard. Refs #150.

### 1.5.0 — 2026-07-29
- `/design-flow:component` step 1 previously said a screen should be built by "composing existing
  components + layout primitives" and gave nowhere to compose *from* — no page-level doctrine
  existed. It now routes any request above component scale (a page, a dashboard, a settings area)
  through `page-anatomies.md` first: pick a shell, pick an anatomy, then fill each region.
- Also points at that file's primitive-instead-of-breakpoint substitution table and the
  chrome-vs-content type assignments, to be applied **before** writing markup rather than caught
  later by `/design-flow:audit`.

### 1.4.0 — 2026-07-29
- **`/design-flow:setup` takes a brand pack**, not a two-value brand enum: `<pack>` or
  `<pack>:<variant>` (e.g. `fidara`, `fidara:fmworkflows`, `acme`). Generating the theme layer is
  now the ONLY brand-dependent step — everything else is brand-neutral and identical for every
  pack, which is what "a pack is a theme, not a fork" means in practice. Setup lints the pack
  first and refuses to scaffold on failure.
- **New `scripts/brand_pack_lint.py`** — stdlib Python 3, the mechanical guarantee behind the
  model. A pack that omits a role does not fail at runtime; the role silently falls back to a
  stock Tailwind colour and the brand breaks in one corner of the app. So it is checked:
  - every role in the **22-role contract** is defined; surface roles carry their `-foreground`
    companion and a `.dark` re-point
  - no `var()` points at a primitive the pack never defines
  - **a variant carries no values** — the check that makes drift from a parent pack impossible
  - no `@utility` / `@apply` / component CSS leaked in (that would be a fork, not a theme)
  - `brand.json` complete, knob values within their enums, `chart_palette_validated: true`
  - two subtleties encoded from measurement, not assumption: `--background`'s companion is
    `--foreground` (not `--background-foreground`), and the feedback roles plus `--ring` are
    deliberately **not** re-pointed on dark — demanding 22 dark values would fail every correct
    pack, and a check that cries wolf gets ignored
  - `--roles-from` re-derives the contract from `foundations-tokens.md` and reports drift, so the
    duplicated role list cannot silently diverge from doctrine (verified in sync: 22 roles,
    15 dark re-points)
- **New reference packs**: `brands/fidara/` (the calibrated pack, carrying the `fidara` and
  `fmworkflows` variants) and `brands/_template/` (a client skeleton — copy, set colours, drop in
  the logo, validate). The template deliberately fails the lint until its palette is validated.
- `brand-guardian`, README and the plugin description no longer assert "two brands".
- **The first real run of a pack IS the verification step**, and it reports back. The lint proves
  a pack is internally complete; it cannot prove the *contract* matches reality. So
  `/design-flow:setup` now ends with a four-point check — Tailwind builds, roles resolve in light
  and dark, `Ui::Logo` renders the right variant's endorsement, dark mode re-points — and files an
  issue via `/rails-flow:report` on any failure. The highest-value case is called out explicitly:
  **a pack that lints clean but still renders a stock Tailwind colour means the 22-role contract is
  incomplete**, which every future pack would inherit. Also generates
  `config/initializers/brand.rb` from the manifest, so `Ui::Logo` has identity to read and no
  component ever hardcodes a brand name.
- **Review fixes** (PR #149). Docs described the API two ways: `Ui::Logo`'s usage example and
  `components.md` still documented the **removed `brand:` parameter**, and `setup.md` still asserted
  `fm-*` as *the* primitive prefix — contradicting "primitives are private to a pack" three files
  away. The pack-lint invocation also resolved the script via `${CLAUDE_PLUGIN_ROOT}` while passing
  a project-relative pack path, so it could never find the shipped reference packs; it now resolves
  both locations and offers to scaffold from `_template` when neither exists.
- **Lint hardening from review**, three of which were real holes in a lint written the same day:
  - **A missing mark file passed.** `brand.json` could point at `prism.svg` while `assets/` held
    something else, and the pack still linted clean — with the logo being *half* of what a pack
    declares. Now an error; unreferenced assets warn.
  - **Indented CSS produced a false failure.** The block regex anchored `:root` and its closing
    brace to column 1, so a formatter that indented the block made the lint report **all 22 roles
    missing** — the most alarming possible message for a pack that was fine.
  - **The documented `brands/*` glob always exited non-zero**, because the shipped `_template`
    deliberately fails until its palette is validated. `_`-prefixed dirs are now skipped (with a
    `SKIP` line) unless `--include-templates`. A check that always fails gets ignored — the same
    lesson as the drift-guard work.

### 1.3.0 — 2026-07-25
- **design-auditor + audit gain a fifth checklist category — "Composition/branding"** (#74): the
  auditor structurally could not flag a full-page focused view using bare `center` instead of the
  `cover` vertical-centering recipe, nor a marketing/auth surface with **no brand mark** (both
  happened downstream and a full audit pass reported neither). Now checked in
  `design-auditor.md` and `/design-flow:audit`, including sub-20px marks, hand-rolled text
  eyebrows, and recolored/stretched facets.
- **`/design-flow:setup` scaffolds `Ui::Logo`** (#75) — added to the base-ViewComponent list, with
  guidance to use `docs/design-system/brand-assets/01-logos/` exact SVG paths when present (else the
  canonical 3-facet prism, flagged for swap), plus the auth/focused-page pairing.

### 1.2.4 — 2026-07-24
- `/design-flow:component` now routes **chart / KPI / dashboard** screens through the
  fidara-design `data-viz` doctrine (chart tokens, form-by-job, one axis, legend + direct labels,
  re-validate on hue change). Guidance-only.

### 1.2.3 — 2026-07-23
- `/design-flow:setup` closing report now nudges reporting any component that won't
  build/render via `/rails-flow:report`. Guidance-only.

### 1.2.2 — 2026-07-23
- `/design-flow:component` now routes CRUD screens through the crud-modal-pattern (modal +
  Turbo Stream), not full-page forms. Guidance-only.

### 1.2.1 — 2026-07-23
- `/design-flow:component` now points at both reference-implementation (Button/Card + mixins)
  and the full component-implementations catalog as the concrete-code source. No behavior
  change; sharper guidance.

### 1.2.0 — 2026-07-23
- NEW **`/design-flow:tokens [android|ios|both]`** — runs the native token export (Phase 3):
  parse the Rails app's `@theme`, resolve roles, emit Android + iOS token files to `tmp/`.
  Writes only to `tmp/` for the maintainer to carry into native repos; never modifies them.

### 1.1.0 — 2026-07-23
- NEW **`/design-flow:mobile [ios|android|both]`** — scaffolds the Hotwire Native parity layer
  (Phase 2): native-app detection + body flags, JSON path configuration, bridge components
  (button/menu/tab-bar, progressive enhancement), safe-area + `min-h-touch` wiring, and
  table→card-stack. Reuses the web components; never touches the native app repos.

### 1.0.1 — 2026-07-23
- `/design-flow:setup` now points at the fidara-design `reference-implementation` as the
  canonical source for the base ViewComponents + Stimulus mixins (copy those exact shapes),
  and notes mobile (Hotwire Native parity) as Phase 2. No behavior change; sharper guidance.

### 1.0.0 — 2026-07-23
- NEW fifth plugin — the agentic UI/design flow that APPLIES the `fidara-design` skill so UI
  is consistent/modern/responsive without a designer or Figma (mirrors how rails-flow applies
  the rails-8/hotwire skills).
- 3 commands: `/design-flow:setup [brand]` (scaffold the `@theme` token architecture + layout
  `@utility` recipes + base ViewComponents + Stimulus mixins into a Rails 8 + Hotwire +
  Tailwind v4 project, brand-parameterized, idempotent), `/design-flow:component <name>`
  (author/refactor UI by composing primitives + role tokens with variant/size/state + a11y +
  responsive), `/design-flow:audit` (flag drift: raw/brand colors, hand-rolled layout,
  breakpoint misuse, missing a11y, off-catalog variants).
- 3 agents: `ui-composer` (builds by composing the system), `design-auditor` (consistency
  gate, design-system-specific — complements rails-flow's general one), `brand-guardian`
  (token/logo/icon/brand-pack enforcement).

## rails-stack (skills plugin: rails-8 + hotwire + fidara-design + code-review)

### 1.15.0 — 2026-07-29
- **First increment of Phase 2**, honouring that issue's own instruction to ship one group at a time
  rather than all ~17 components at once.
- **The slice was chosen by a gap #94 created.** `page-anatomies.md` shipped in v1.24.0 telling agents
  to "fill the regions from the catalog", then named **heading block**, **Breadcrumb** and
  **description list** — none of which had catalog entries. An agent following it either invents the
  markup (the exact failure page anatomies exists to prevent) or stalls. So this increment is "the
  patterns `page-anatomies.md` already composes", cutting across the issue's Navigation / Lists /
  Elements grouping deliberately: closing a live dangling reference beats matching the kit's taxonomy,
  and these six are what the next groups build on.
- **Six catalog entries + five worked ViewComponents:** Heading blocks (page/section/card — one
  anatomy, scale the only axis, tag and step moving together so a card heading can never be an `<h2>`
  styled small), Breadcrumbs, Description list, Button group, Media object, and Divider **as a recipe,
  not a component** (an `<hr>` is already `role="separator"`; in lists the answer is `divide-y` on the
  container, not n elements).
- **No duplicate mechanisms**, per the issue's own criterion: Card's `detail` recipe now *renders* the
  Description list at `inline` instead of re-implementing `<dl>` rows, and the button group's
  single-select kind is a `radiogroup` driven by the existing **list-navigation** mixin rather than a
  new controller. Breadcrumb collapsing reuses `Ui::DropdownComponent`.
- **Mechanical verification caught two violations in the draft before commit**, which is why it is
  done by script rather than by reading: the breadcrumb separator called
  `lucide_icon(..., class: "size-4")` when the icon doctrine is explicit that icons carry **no** size
  or class (`with-icon` sizes them to 1em in `currentColor` — SVG presentation attributes have zero
  specificity, which is the whole reason that rule exists); and it used `d.with_item`, when
  `Ui::DropdownComponent` takes `items:` as an array of `{label:, href:}`. Both would have shipped
  code that raises or silently ignores doctrine.
- Verified: every primitive, role token, type step, space step and rendered component resolves against
  the other references; zero literal colours; zero inline `dark:`; no new `@utility` defined.
  `page-anatomies.md` now names the components instead of generic patterns, and the file's "full
  catalog has worked code" claim is updated to stay true.

### 1.14.0 — 2026-07-29
- **Maintainer decision, recorded:** *"simple_form is in charge of all forms to drive consistency
  across the codebase — no form or form element should exist that does not use simple_form,"* and
  *"ViewComponents should use the same simple_form."* Three references contradicted that, and two
  called APIs that do not exist at all.
- **`forms.md` called a helper that does not exist** — `field_classes(state)` against `UiHelper`'s
  `input_classes(state:, size:)` (different name *and* keyword arguments). Copied verbatim, the
  field-anatomy example raised `NoMethodError`.
- **`crud-modal-pattern.md` used `form_with` and a `Ui::FieldComponent` signature that does not
  exist** — `(form:, name:, label:)` against an initializer of `(label:, hint:, error:, for_id:)`.
  This is the canonical create/edit example every CRUD screen is built from, so it had the widest
  blast radius of the three.
- **The root cause was deeper than the signatures.** A field-wrapper component that renders its own
  `<label>`, hint and error markup **is a form element built without simple_form** — precisely what
  the mandate rules out. So `Ui::FieldComponent` is gone from doctrine rather than corrected: field
  anatomy is now a **styled simple_form wrapper**, defined once in
  `config/initializers/simple_form.rb`, which is what `forms.md` already meant by "simple_form for
  the markup contract, styled to the design system". Authors write `f.input`; the wrapper supplies
  the `stack`, label classes, control classes, hint/error paragraphs and `aria-describedby`.
  One definition means a change lands on every field at once, which is the entire point.
- **The rule reaches inside ViewComponents.** A component that renders fields takes the form builder
  in and calls `form.input`; it does not re-implement the anatomy. `component-implementations.md`
  shows that composition shape.
- **The mandate was previously enforced more strictly than it was documented** — `setup-flow.md`
  already said "simple_form mandatory — never raw `form_with`" and `design-auditor` greps for
  `form_with` as a violation, while `rails-8/ecosystem-gems.md` still said "keep `form_with` for
  one-off forms — mixing is fine". So the shipped auditor blocked users for following our own
  doctrine, the same shape as the ids-only job contradiction fixed in v1.23.0. rails-8 now states
  simple_form as mandatory (a deliberate divergence from the Rails default, with the reason given),
  `views-hotwire.md`'s forms section is reframed as the builder-agnostic **Turbo contract** with the
  mandate stated up front, `SKILL.md`'s golden path says `simple_form_for`, and the auditor's rule
  drops its stale "if the project mandates" conditional.
- **Every remaining exception was closed rather than flagged.** There is no non-simple_form case:
  a model-less form is `simple_form_for :q, url: …` (simple_form takes a symbol), a hidden label is
  `label: false` plus an accessible name, and `f.input_field` — which *is* simple_form's control-only
  renderer, so it satisfies the mandate — is reserved for a control inside a composed cluster where
  the wrapper's markup would fight the layout. What is forbidden is hand-rolling the anatomy, not
  using simple_form's own API.
- **The wrapper config is now stated as a contract with a way to prove it**, instead of a snippet
  readers must take on trust: order (label → control → hint → error in a `stack`), role tokens only,
  `min-h-touch` + `focus-visible`, error state driven by simple_form's `error_class`/`aria-invalid`
  so `aria-describedby` is not hand-maintained, and label always rendered unless explicitly hidden.
  A short system spec asserts all of it on first install — if it fails, the wrapper is wrong, not the
  doctrine. Repeated deviation is a second named wrapper, never a repeated per-field override.

### 1.13.0 — 2026-07-29
- **The gap.** fidara-design had a strong component catalog and almost no page-level anatomy — one
  base layout and the `cover` recipe. An agent asked for "the invoices screen" had nothing to
  follow above component scale, so it invented page structure, and invented structure is where
  breakpoint chains, nested cards and inconsistent heading ramps come from.
- **New `references/page-anatomies.md`** — **3 shell archetypes** (sidebar + mobile drawer via
  `Layout::SidebarComponent`; stacked top-bar; multi-column rail/main/aside) and **3 page
  anatomies** (home-dashboard, detail, settings), each stating mobile behaviour, brand-mark
  placement, safe-area handling and which catalog components fill each region. Framing: **a screen
  is composed, not designed** — pick a shell, pick an anatomy, fill from the catalog.
- **Scroll containment is called out explicitly** because it is the failure that makes a shell feel
  broken: an independent scroll region needs `min-h-0` alongside `overflow-y-auto`, or the flex/grid
  child cannot shrink and the whole page scrolls, taking the rail with it.
- **A primitive-instead-of-breakpoint substitution table** — `grid grid-cols-1 md:… lg:…` →
  `grid-auto` + `--min`; `flex-col md:flex-row` → `Layout::Switcher`; `hidden md:block` for a rail →
  `Layout::SidebarComponent`; `space-y-*` → `stack`; `max-w-7xl mx-auto px-*` → `shell`. Intrinsic
  reflow responds to the **container**, so it stays correct inside a drawer or a split view where a
  viewport breakpoint is simply wrong.
- **Composed only from primitives that already exist**, per the epic's rule that introducing new
  framework API into a skill is an external claim. Every `@utility`, component name, role token and
  type step in the file was verified against the other references mechanically rather than by
  reading — which caught three of my own errors before commit: `--grid-min` (the real custom
  property is `--min`), `with_rail` (the slots are `renders_one :sidebar` / `:main`), and a
  `FieldComponent` call matching neither shipped signature.
- The settings anatomy deliberately **defers to `forms.md`** instead of asserting a field API,
  because two references disagree about `FieldComponent` — filed as #168 rather than resolved here.
- `SKILL.md` links it as section 3 (between Layout and Components); `/design-flow:component` now
  routes any screen-level request through it before writing markup.

### 1.12.0 — 2026-07-29
- **New `skills/code-review`**, bundled into rails-stack and packaged as `dist/code-review.skill`.
  Review doctrine for the defect class authors are structurally blind to: code that is correct on
  its own terms but does not do what its own documentation, config, comments or project rules
  claim. Names seven classes (`claims-vs-enforcement`, `dead-declaration`,
  `carve-out-without-negative-test`, `coverage-gap`, `doctrine-contradiction`,
  `unverified-negative`, `gate-that-cannot-fail`) with detection guidance for each, and is explicit
  that it *complements* correctness review rather than replacing it.
- **Every class is traceable to a defect this repo actually shipped or nearly shipped** — no
  speculative rules. It also states the project's own rules (CLAUDE.md Project Overrides, README,
  `docs/`) are the *input* to the review, since most findings are a rule in the repo disagreeing
  with code in the repo.
- Consumed by rails-flow's `code-reviewer` and `pr-reviewer`, which delegate to it instead of
  restating it. Packaging is unchanged in shape; the other three `.skill` files rebuild
  byte-identical.

### 1.11.0 — 2026-07-29
- **The design system becomes multi-brand** (#104). `brand.md` refactored from "two brands, one
  system" into the **brand-pack** model, so the system can be used for client and freelance work
  without forking.
  - **A pack is a theme, not a fork.** The framing is explicit: you use this system the way you
    use Tailwind, Bootstrap or Flowbite — you do not re-author it. A pack declares **colours, the
    logo, and the chart-palette validation result**; that is the whole surface. Layout, component
    API, spacing/type scale, a11y and interactions stay central, so every brand inherits the
    fixes. "Not in the pack" is the product, not a limitation.
  - **Two levels: pack, then variant.** A *pack* is a genuinely distinct brand (own palette,
    fonts, mark). A *variant* lives inside a pack and differs only in lockup/endorsement.
    **`fmworkflows` is a variant of the `fidara` pack, not a pack of its own** — it is a product
    *using* fidara's design system. Modelling it as a peer brand would have meant two
    byte-identical `theme.css` files and a live drift hazard (update the parent palette, the
    product silently diverges). A variant carries no values, so it cannot drift. The test:
    *does it re-theme, or only re-label?*
  - **Primitives are private to a pack; the role layer is the public API.** `fm-*` is fidara's
    own naming, not system law — a client pack may name primitives anything, because nothing
    outside a pack may reference one. That is what makes a brand swap a single `@theme` layer and
    what makes completeness mechanically checkable.
  - **Overrides are a rare escape hatch**, not what a brand does: `fonts`, the three personality
    knobs, and `chart_hues` inherit fidara's calibrated defaults when omitted, so a typical
    client manifest is four lines. Every override is a place the brand stops matching the system.
  - `chart_palette_validated: true` is required **even when hues are inherited** — changing the
    palette changes the surface the hues sit on, and hues that clear contrast on fidara's navy can
    fail on a client's light beige.
  - **Fixed a latent doctrine bug the two-value enum was hiding**: the "by Fidara" endorsement was
    attached to the *parent* (`brand: :fidara` → `endorsement? = true`), rendering
    **"Fidara by Fidara"**. An endorsement ties a *product* to its parent, so it belongs on the
    product variant. `Ui::Logo` now takes `brand_variant:` and reads the display name and
    endorsement **string** from the pack manifest — no brand names in component code, so a
    client's "an Acme company" needs no code change.
  - Swept every other assertion of the old model: `SKILL.md`, `components.md`,
    `component-implementations.md`, and design-flow's `setup`, `brand-guardian`, README and
    plugin description.
  - Records what the lint **cannot** prove: it checks a pack against the role contract, not the
    contract against reality. A clean pack that still renders a stock colour is a doctrine defect
    to report upstream, not a project problem to patch locally.
  - **Rejected one review finding with reasoning**: `Ui::Logo`'s px units. The mark has a
    *documented absolute minimum* (prism 20px digital / 6mm print, clear space 1.5×) and its
    wordmark is sized proportionally to the mark, not to body text — scaling a trademark with the
    reader's font preference would violate the brand's own minimum-size rule. Materially different
    from the `body { font-size: 15px }` finding accepted earlier, which overrode text scaling.

### 1.10.0 — 2026-07-25
- **fidara-design Phase 0 — foundations calibrated against two reference corpora** (#93). The
  fluid scale existed; *which step goes where* was undefined, which is where drift starts. All
  values below were measured across 704 + 264 component files and 72 rendered pages, not chosen
  by taste.
  - **NEW tokens**: `--width-shell` (80rem/1280px — both corpora converge, `max-w-7xl` ≡
    `max-w-screen-xl`), `--width-prose` (42rem/672px section ledes), `--space-section`
    (clamp 96→128px, generous — the fidara default) and `--space-section-compact` (64→96px).
    Plus `@utility shell / prose-measure / section-y / section-y-compact`. Verified compiling
    under Tailwind v4.3.3.
  - **NEW "Applying the scale" table — the chrome-vs-content rule.** Interface chrome is
    *smaller* than prose: both corpora are `text-sm`-centric by ~**2.7 : 1** (TW 6494 vs 1575;
    FB 1100 vs 413). So app chrome = `text-step--1`, prose = `text-step-0`, meta = `text-step--2`,
    with card/section/page/hero mapped to steps 1/2/3/4-5. Using `step-0` for chrome is the most
    common calibration error and made product UI read oversized.
  - **Heading ramp** — follow Flowbite's fuller mid-range: reach for `step-1`/`step-2` for card
    and section headings instead of jumping body → hero (Tailwind UI's thin mid-range).
  - **NEW control-density table** bound to the shared `sm/md/lg` vocabulary, reconciling padding
    with height: `md` = `px-3 py-2` / `h-9` (both corpora's default — TW 749, FB 129).
  - **Validated by measurement, now settled**: the radius language matches ours exactly
    (controls `rounded-md` 2068, cards `rounded-lg` 966, pills `rounded-full` 1379) and the
    elevation idiom is a 1px edge + minimal shadow (`ring-1` 690 + `shadow-xs` 498; FB `border`
    302 + `shadow-xs` 116). Flowbite's softer all-`rounded-lg` was **considered and rejected**.
  - **NEW hard rule — never bind markup to a numbered step.** Causal, not stylistic: a numbered
    step encodes a fixed lightness, so every dark adjustment must be inline. Measured cost in the
    corpora (which do bind that way): **20,825 `dark:` classes across 72 pages** (~289/page).
    fidara's role layer needs **zero**.
  - `brand.md` gains a **personality-knobs table** (#104): section rhythm, radius language and
    heading ramp are **per-brand** choices with fidara defaults — a client brand changes a token,
    never a component.

### 1.9.1 — 2026-07-25
- **RSpec and Tailwind are stated as deliberate choices, not corrections** (#101). Both are
  **kept** — the decision is confirmed — but the doctrine previously implied the canonical
  alternatives were defects, which is wrong: **Minitest is Rails' default test framework** and
  **hand-written CSS is what 37signals ship** in their own production apps
  ([basecamp/fizzy](https://github.com/basecamp/fizzy) `Gemfile`: `minitest-reporters` + `capybara`,
  with `test/` not `spec/`; campfire/writebook/fizzy use vanilla CSS, no Tailwind gem).
  - `rails-8 › testing.md` now explains **why** we standardize on RSpec (the rails-flow Stop-gate,
    `test-runner` agent, `bin/ci` list and qa-flow gates all assume RSpec conventions + `spec/`
    layout — one framework is what makes those gates mechanical), and states that **a project
    already on Minitest is not a defect** — record a Project Override, don't migrate it on this
    skill's authority.
  - `fidara-design › SKILL.md` does the same for Tailwind: the reason is **mechanically enforceable
    consistency** (greppable `@theme` roles + `@utility` primitives let `/design-flow:audit` verify
    conformance — impossible for bespoke stylesheets), not that vanilla CSS is inferior.
  - README: "no Minitest" → "a deliberate standardization over Rails' Minitest default".
- Also hardened `.gitignore` for licensed design references (`flowbite*/`, `flowbite*.zip` alongside
  `tailwind-ui/`, `everylayout/`) so kit sources can never be committed to this public repo.

### 1.9.0 — 2026-07-25
- fidara-design **`Ui::Logo` + the auth/focused-page recipe** (#75, #74). `brand.md` fully specified
  the Prism mark (facet hues, wordmark, clear space 1.5×, min 20px / lockup 140px) and
  `brand-guardian` existed to enforce it — but **nothing rendered it**, so downstream screens
  hand-rolled a `<p>Fidara</p>` text eyebrow. Now:
  - **`Ui::Logo`** worked in component-implementations (variants `mark`/`lockup`, sizes
    `sm 20 / md 28 / lg 40` px with the 20px floor enforced in code, `brand:` toggling the
    "by Fidara" endorsement, dark-mode automatic). Facet hues stay **fixed brand hex** — the one
    documented exception to role-tokens-only, because facets must never be recolored.
  - **Catalog entry** in components.md (required on marketing/auth/full-page single-focus surfaces).
  - **Named auth recipe**: `layout-primitives.md`'s canonical-compositions table now calls out
    "Auth / marketing splash / onboarding (single-focus, full-page): `cover > center > stack`" and
    warns not to file these under "Page" — the ambiguity (#74) that left auth screens
    top-aligned via bare `center` (which is `margin-inline` only) and mark-less.

### 1.8.0 — 2026-07-25
- rails-8 **CI trigger-economy doctrine** (#76): `testing.md`'s "mirror `bin/ci` into
  `.github/workflows/ci.yml`" line no longer implies *run everything on everything*. It now
  prescribes scoping the hosted CI to the `dev → main` gate —
  `on: { pull_request: { branches: [main] }, push: { branches: [main] }, workflow_dispatch: {} }`
  — because local `bin/ci` hooks + qa-flow already cover `feature → dev`, and full-matrix-on-every-PR
  burns Actions minutes (on a private repo it can exhaust the quota and block merges, which it did
  downstream). Doctrine-verified: `pull_request.branches` filters the PR's **base** branch (fires on
  the PR into `main` + the merge push), `branches`/`branches-ignore` are mutually exclusive — GitHub
  Actions "Events that trigger workflows."

### 1.7.0 — 2026-07-24
- fidara-design **data-visualization layer** (#63, now 14 references): NEW **data-viz** —
  charts, KPIs, and dashboards as first-class design-system doctrine. Adapts Anthropic's
  design-system-agnostic `dataviz` method (form → color-by-job → **validate** → marks →
  interaction → a11y) to fidara: an 8-slot categorical **chart palette derived from the `fm-*`
  tokens** (brand-anchored: blue=cerulean, orange=fm-orange), plus cerulean sequential and
  cerulean↔red diverging ramps, emitted as `--color-chart-*` `@theme` tokens (→ `fill-chart-1`,
  `bg-chart-2`, … re-pointing under `.dark`); a KPI/stat-tile ViewComponent + bar-mark recipe;
  and the chart non-negotiables (fixed categorical order never cycled, **one axis**, identity
  never color-alone, text wears text tokens, status colors reserved). Wired into SKILL
  non-negotiables, foundations-tokens (chart-token pointer), and `/design-flow:component`.
  - **Validated, not eyeballed** (the method's core rule): the categorical palette was run
    through `validate_palette.js`. **Light** (surface `#F8F9FB`): all hard gates PASS — worst
    adjacent CVD ΔE 9.1, normal-vision ΔE 19.6 (4 slots <3:1 → relief rule: direct labels/table).
    **Dark** (surface `fm-navy #0C1B33`): lightness/chroma/normal-vision (ΔE 19.3)/contrast (all
    ≥3:1) PASS; green↔magenta adjacency CVD ΔE 6.1 (6–8 band) → legal with the secondary encoding
    fidara already mandates. Chart `@theme`→utility generation (`bg-/text-/fill-/stroke-/border-chart-*`
    + dark re-point) verified against the Tailwind v4.3.3 compiler. Basis: WCAG 1.4.11; method
    source: Anthropic `dataviz` skill (built to be re-validated per brand).

### 1.6.2 — 2026-07-23
- **fidara-design: reference recipes now honor the skill's own non-negotiables** (#56 —
  the recipes ship verbatim via `/design-flow:setup`, so the contradiction propagated
  downstream). (1) **Radius**: Modal `panel` and the Modal prose use `rounded-lg` instead of
  arbitrary `rounded-[12px]` — with the `@theme` token `--radius-lg = calc(--radius + 4px) =
  12px`, `rounded-lg` *is* 12px, so the token and the arbitrary value are equivalent and the
  vocabulary stays intact. (2) **focus-visible**: Modal close + Alert dismiss icon-buttons now
  carry `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30` like the
  Button/Input recipes. (3) **Icons**: added an "Icons (Lucide)" note with the real
  `helpers.lucide_icon(...)` call site wrapped in `with-icon`, and wired `with-icon` onto the
  Alert icon + both dismiss buttons; guidance is stroke-width-only in the `lucide-rails`
  initializer, never hardcoded px (the Button loader-spinner is the documented fixed-size
  exception). Verified (doctrine-verifier, CONFIRMED): Tailwind v4 `rounded-lg` →
  `var(--radius-lg)` (tailwindcss.com/docs/border-radius); CSS `svg { inline-size: 1em }`
  overrides SVG presentational `width`/`height` at zero specificity, no `!important`
  (MDN SVG Attribute reference). Version boundary: Tailwind v4 (v3 had a fixed radius scale).

### 1.6.1 — 2026-07-23
- fidara-design SKILL.md: NEW **"if the code here breaks, report it"** section — states the
  verification boundary (token/CSS + Stimulus layer is compiler/Node-verified; the
  ViewComponent/Rails integration is doctrine, not runtime-verified against a live app) and
  routes downstream failures to `/rails-flow:report` (`fidara-design` / `design-flow`). Closes
  the feedback loop for the design system.

### 1.6.0 — 2026-07-23
- fidara-design **modal-driven CRUD as first-class doctrine** (now 13 references): NEW
  **crud-modal-pattern** — in Fidara, create/edit/delete never navigate to a separate
  new/edit page; they open in the shared `<turbo-frame id="modal">` and update the list via
  Turbo Stream (`prepend`/`replace dom_id`/`remove dom_id`) + a toast, with a real
  confirmation modal for deletes and a `modal_controller` (focus-trap + dismissable-layer +
  restore). Modal + Card are the backbone; full-page CRUD forms are a defect. Wired into
  SKILL.md non-negotiables, components.md (Table/CRUD), reference-implementation.md (the
  load-bearing modal frame), and `/design-flow:component`. Matches the reference apps' pattern.
- **Verified fix — Tailwind v4 `@utility`:** foundations-tokens.md now defines `min-h-touch`
  and the safe-area utilities (`pt/pb/pl/pr-safe`, `mb-safe`) with `@utility`, not raw classes
  in `@layer utilities`. In v4 (native CSS cascade layers, `@utility` introduced v4.0), only
  `@utility` registers a class with the variant engine, so `sm:pt-safe` / `hover:min-h-touch`
  now generate — raw `@layer utilities` classes emit the base form but get no variants.
  Confirmed against the Tailwind v4.3.3 CLI compiler + official docs
  (tailwindcss.com/docs/adding-custom-styles#adding-custom-utilities, functions-and-directives).
  Whole design-system CSS (role tokens, fluid type, all `@utility` recipes, `dark:` variant)
  and the four Stimulus mixins were build-verified against the real compiler / Node.

### 1.5.0 — 2026-07-23
- fidara-design **full component catalog** as worked code (now 12 references): NEW
  **component-implementations** completes the reference implementations beyond Button/Card —
  Badge, Alert, form Field + Input recipe + checkbox/radio/switch, Modal, Dropdown, Tabs,
  Toast, Tooltip, Avatar, EmptyState, and the Sidebar/Switcher layout components. Every one is
  a frozen `BASE`/`VARIANT`/`SIZE` map on role tokens + primitives, attribute-driven state,
  a11y baked in — the exact shape agents replicate. Pagination/CRUD-tables remain the
  role-tokenized `shared/*` partials.

### 1.4.0 — 2026-07-23
- fidara-design **mobile Phase 3** (now 11 references): NEW **native-tokens** — the native
  token-export doctrine: the role → Material 3 (Android) / SwiftUI (iOS) mapping so semantic
  role names translate 1:1, plus a reference `bin/export_design_tokens` Ruby script that
  resolves role → primitive → hex from the `@theme` and emits `colors.xml` + `Theme.Fidara`
  (Android) and a SwiftUI `Color` extension (iOS) into `tmp/`. Fluid `--text-step-*` export as
  fixed native sizes (documented). `@theme` stays the single source of truth; native files are
  generated, never hand-diverged. `mobile.md` marks Phase 3 code-ready.

### 1.3.0 — 2026-07-23
- fidara-design **mobile Phase 2** (now 10 references): NEW **mobile-reference-implementation**
  — the web-side Hotwire Native parity code: `native_app?` detection + `body.mobile-app` chrome
  toggles, JSON path configuration (modal vs default, per surface), bridge components
  (`button` nav-bar action, `menu` action sheet) as progressive enhancement extending
  `BridgeComponent`, safe-area + `min-h-touch` wiring, and the table→card-stack recipe.
  `mobile.md` marks Phase 2 code-ready. Native Kotlin/Swift shells stay in their own repos
  (this is the web contract they consume); Phase 3 (native token export) still to come.

### 1.2.0 — 2026-07-23
- fidara-design gains the concrete code it was missing (now 9 references): NEW
  **reference-implementation** — the canonical ViewComponent pattern (Button/Card, cva-style
  variant maps + slots) plus the four Stimulus mixins as real code (list-navigation /
  focus-trap+restore / dismissable-layer / anchored-position) and a base layout composing the
  primitives; agents replicate these exact shapes instead of freehand. NEW **mobile** — the
  web↔mobile parity plan (Hotwire Native shell renders the same web UI; safe-areas +
  min-h-touch + bridge components + path config; native token export to Android/iOS for
  fully-native screens; phased). Closes the doctrine's "spec but no code" gap, all in-repo.

### 1.1.0 — 2026-07-23
- NEW **`fidara-design`** skill bundled into rails-stack — the Fidara design system, so UI
  comes out consistent, modern, and responsive across projects without a designer or Figma.
  Distilled from the fmanimashaun/fidara real assets (brand tokens, auctioneer component
  patterns) + a landscape survey (Flowbite, shadcn/Radix/Material/Carbon/Polaris) + Utopia
  (fluid type/space) + Every Layout (composition/intrinsic layout). SKILL.md + 7 references:
  - **foundations-tokens** — Tailwind v4 `@theme` with three tiers: brand primitives (`fm-*`)
    → semantic roles (shadcn-style, `-foreground` pairs, dark mode by re-pointing) → Utopia
    fluid `clamp()` type/space scale + measure/radius/shadow/motion. Resolves the real
    slate-scale / two-type-scale / `dark:`-sprawl inconsistencies to one source of truth.
  - **layout-primitives** — Every Layout (Stack/Cluster/Center/Box/Grid/Sidebar/Switcher/
    Cover/Frame/Reel/Imposter/Icon/Container) as `@utility` recipes + ViewComponents; compose,
    don't write per-page CSS; intrinsic responsiveness (breakpoints for structural swaps only).
  - **components / forms** — ~16-component catalog with a fixed variant×size×state vocabulary,
    a11y checklists, and prescribed responsive behavior, all on semantic role tokens.
  - **interaction-stimulus** — four reusable Stimulus mixins (list-nav, focus-trap+restore,
    dismissable-layer, anchored-position) covering every overlay; state via `data-*`/`aria-*`.
  - **responsive** — fluid + intrinsic first; per-element prescribed behavior; touch/safe-area.
  - **brand** — the two-brand (one-system, `fm-*` prefix) model, Prism mark, Lucide icons.

### 1.0.5 — 2026-07-22
- rails-8 › controllers-routing §1a: new URL-design doctrine (journey-wide).
  Default posture — human, readable URLs for user-facing pages; REST resource URLs for
  interchangeable records and the JSON API. The rule: match the URL to what the reader
  addresses (a specific record → REST id path; a concept or singleton-scoped-to-me like
  /account, /dashboard, /login → human path via singular `resource` or vanity route; a
  machine → strict REST always). The reconciliation: RESTful controllers UNDER human
  URLs (`get "/login", to: "sessions#new", as: :login`) so helpers read naturally,
  controllers stay resource-honest, and password managers / `/.well-known/change-password`
  work. Auth generator's `resource :session` explained as correct-but-developer-vocabulary;
  vanity override documented as a Project Override, not a bug. Pointer added from
  auth-security.md. Source-verified (SEO/URL usability consensus, W3C change-password
  well-known URL). marketplace 1.5.0.

### 1.0.4 — 2026-07-22
- rails-8 › testing §4: factories are **sequences-first** — deterministic
  defaults (reproducible failures, uniqueness by construction, faster, readable
  output), matching fmworkflows' proven practice (16 factory files, zero Faker).
  Faker demoted to its narrow slot (seeds/demo, presentation variation), always
  fully namespaced: no Syntax::Methods-style mixin exists for Faker — the
  `Faker::` prefix is the API. Source-verified post-hoc against thoughtbot's
  own guidance (Faker for development fixtures, not testing fixtures) and the
  practitioner flaky-CI record; doctrine-change protocol added to the audit
  doc so verification precedes edits from now on.

### 1.0.3 — 2026-07-21
- rails-8 › jobs-and-realtime: new §7 "Threading & the Rails executor"
  (executor.wrap doctrine, load interlock, reloadable-constant caching,
  connection-pool rules) — the single doctrine gap found by the framework audit
  against rails/rails 8-1-stable. mission_control-jobs expanded from a one-liner
  to mount-behind-auth + adapter-feature doctrine.
- Audit record: docs/audits/2026-07-21-framework-gap-audit.md — 31-cluster
  coverage matrix vs the 75 official guides + turbo/stimulus/native sources;
  verdict: zero incorrect doctrine, versions exact, P3 backlog logged.

### 1.0.2 — 2026-07-21
- rails-8 › new `references/sso.md`: roll-your-own multi-tenant SSO doctrine —
  OIDC-first with per-workspace dynamic setup, identities keyed [provider,
  issuer, uid], workspace-scoped provisioning with domain gate, enabled-vs-
  enforced with owner break-glass, JIT role sync (per-tenant mappings, ceiling),
  tenant dashboard rules (write-only secrets, step-up, provider-tabbed guide),
  SAML hatch (signing, SP metadata, cert validation + metadata-polling rotation,
  SLO caveats), audit events, nine-spec RSpec proving set. Distilled from
  implementation review of five external guides.

### 1.0.1 — 2026-07-21
- rails-8 › testing: SimpleCov 1.0 — `add_group` renamed to `group` (1.0.2);
  migration note added (segment-boundary string filters, Ruby ≥ 3.2 floor).
  Field-reported from the first live project run. `dist/rails-8.skill` rebuilt.

### 1.0.0 — 2026-07-20
- Initial release: rails-8 (16 references — vanilla-first Rails 8.1 doctrine,
  pure RSpec, Solid stack, Kamal 2, OpenAPI via rswag, ruby_llm) and hotwire
  (Turbo, Stimulus, Hotwire Native) skills, bundled as one installable plugin.

## Repository / marketplace

### 2026-08-09b (release v1.84.0)

> ### A budget guard that could not fire, and a plan a human can read
>
> The cost preflight read a config key `--scaffold` has never written, so every plan cost $0.00 and
> `--run` walked past the refusal to the executor. Fixed, with the test discipline that would have
> caught it — plus a generated markdown table beside the plan JSON.

- **`asset_plan.py`'s cost preflight read `ladder`; `--scaffold` writes `ladders`.** (#592) The
  singular key is absent from every scaffolded config, so it resolved to `[]`, every plan cost
  `$0.00` however many rows it held, `0.0 > ceiling` was never true, and `--run` fell through to the
  executor. **A guard whose input is always zero is not a lenient guard; it is one that has been
  switched off, and nothing said so.** Reconciled onto `ladders` and priced **per kind** — a video
  rung costs an order of magnitude more than a vector rung the agent authors, so one flat ladder had
  to be wrong for at least one of them.

  Two holes of the same shape one level down: `cheapest_rung` returned `0.0` for a ladder that
  priced nothing, making the row nobody had costed the cheapest thing in the plan; and `affordable()`
  computed "the cheapest rung" its own second way, which counted an unpriced rung as free **and**
  raised `TypeError` on a rung whose `cost_usd` is explicitly `null` — exactly what the scaffold
  writes for video. `--run` now refuses an unpriced plan outright, before the executor and
  regardless of the numeric total, and `--confirm-partial` does not bypass it: a ceiling can only
  refuse a number, and the whole problem is that there is no number.

  **Why 63 assertions passed over it, which is the part worth keeping.** The cost fixtures
  hand-wrote a config shape the scaffold has never emitted, so the suite validated a contract the
  writer does not produce — two transcriptions agreeing with each other. Every cost fixture is now
  built by calling `scaffold()`, and a new end-to-end fixture drives `main(["--run"])` against a
  real scaffolded project with a `subprocess.run` that **fails the test if the executor is ever
  reached**. No unit test could have caught this: each function answered correctly in isolation, and
  the bug lived in the path between them.

- **The asset plan renders as a markdown table beside the JSON.** (#593) `plan.json` is the right
  shape for the agent that runs the plan and the wrong shape for the human who has to review it —
  which is the step the plan exists for. Unpriced rows are marked **unpriced** rather than shown as
  `$0.00`, so the reason a run will refuse is visible in the document someone reads before deciding
  to spend. Generated and drift-checked, carrying the two `docs/coverage.html` rules: the bytes are
  a function of the **data only**, and the totals come from `status_report()` rather than a second
  count.

- **Three stale claims in `asset_plan.py`'s own doctrine**, all about a placeholder API key the
  scaffold stopped writing two releases ago — including `Next: fill $OPENROUTER_API_KEY`, the
  **first instruction a new project saw**, naming a variable the scaffolded path never reads.

**Upgrade note.** `--run` now refuses a plan containing a `video` row until a real `cost_usd` is
written into `ladders.video`, because the provider's catalogue does not report pricing and the
scaffold ships that rung unset rather than inventing a figure. The three agent-authored kinds
(`static`, `vector`, `motion`) are priced at `0.0` and unaffected, so the free path a fresh project
actually uses still runs.

### 2026-08-09 (release v1.83.0)

> ### The design flow is a sequence now, and every link is enforced
>
> Scaffold → read the PRD → research → choose a style → emit it as doctrine → curate → cost →
> generate → critique. Two links were missing and three shipped claims were wrong.

- **Motion had "no route", which was false.** The claim began as a true statement about the *image*
  endpoint and was allowed to stand as one about the provider, so every motion row refused. There
  are **21 video models**. More importantly `motion` and `video` are now **separate kinds**: as one
  kind it routed a loading spinner through footage generation, so the cheap common case paid the
  expensive rare case's price. Product motion is Lottie/animated SVG — KB, recolours from tokens,
  agent-authored, free. Video is footage, and right for a marketing hero and little else.

- **The output critic — the stage that was missing.** The acceptance check shipped as *a string that
  had to be present*: letter of the criterion, not spirit. Nothing read the asset, so the
  climb-the-ladder trigger was one nobody could pull and `attempt` existed while nothing set it.
  `--critique` assembles what a critic needs; `--verdict accept|reject --why` records the judgement,
  writes provenance, or climbs.

- **The research now decides the style, and every brief is held to it.** A project could research
  monochrome ink and brief a 3D render with nothing noticing. `style` is the record's required
  **output** — three sources disagree, and the choosing *is* the design.

- **The approach is emitted as a project-level skill**, not left as JSON. The record is evidence;
  the skill is doctrine, read because its description matches the work rather than parsed when an
  agent remembers to. It carries what was **rejected**, which is what stops the same idea returning
  next quarter, and refuses to emit from a record that does not pass.

- **Retracted rather than shipped:** a Figma-to-tokens reader. Tokens are *generated* from the brand
  pack, so a reader would be a second source of truth for the same values.

The fixture defects this batch surfaced were all one class — tests failing on each other's side
effects rather than on what they name — plus one guard living in `main()` where no test reached it,
and a mutation that survived because of it.

### 2026-08-09 (release v1.82.0)

> ### The asset path generates, and it needs no API key to do it
>
> Six defects, all in code that looked finished, and every one of them found by running the thing
> rather than reading it.

- **The agent generates by default.** A connected provider MCP or the agent's own SVG covers the
  interactive case entirely — no key, no `.env`, no adapter code. The gate is unchanged: it
  approves, hands back a brief, and `--record` **re-runs the whole gate** before the manifest
  accepts the file, so an agent-authored asset gets no easier route in than a purchased one. The
  HTTP adapters remain, scoped to unattended runs where no agent can call an MCP.

- **`.env` was promised in two shipped messages and read by nothing.** Follow the instruction and
  you got *"is not set"* — which reads like a broken tool rather than an unloaded file. It reads
  `.env` now, and the real environment wins. Scaffolding `api_key_env` at all turned out to be the
  defect underneath: naming a credential the default path never reads is how a placeholder became a
  documented step for a route that could not use it.

- **Both scaffolded model IDs were invented from documentation prose**, and both 404'd on the first
  real call. Verified against the live model list now, with `--discover` to refresh them. Prices are
  **unset**, because that endpoint does not report pricing and an invented number is worse than an
  absent one — and removing them exposed that a missing `cost_usd` defaulted to **0**, so an
  unpriced model cost nothing and the ceiling was unreachable. An unpriced rung refuses now.

- **`kind: vector` wrote PNG bytes to a `.svg`, and `motion` wrote a still to a `.webm`.** Files
  that open, look plausible in a listing, and are the wrong format. Extensions are sniffed from the
  **bytes**; a vector request that gets a raster refuses.

- **Exit 0 stopped meaning "done".** The agent path exits 0 while handing back a *brief*, so reading
  the return code alone marked rows complete with nothing on disk — the exact *"recorded from what
  was attempted"* failure the file's own docstring forbids.

Verified live rather than asserted: an HTTP call returned **402, not 401** (key valid, no credits),
`get-credits` reports **0**, and a full `scaffold → research → plan → check → run` produced a valid
SVG, a complete manifest row and an honest status — at zero cost.

### 2026-08-08 (release v1.81.0)

> ### The auditor cried wolf, and the README was lying about itself
>
> One reported bug, and two documents that had drifted so far they were misinforming anyone who
> read them.

- **A conformant focus ring reported as a blocking S1 on every page** (Refs #578). The keyboard pass
  decided *"visible indicator"* by looking up a property, so a ring living in `box-shadow` read as
  absent — while `outline: rgb(0,95,204) none 1px` (a non-zero *width* with style `none`) passes one
  check and fails another, and neither consults the actual ring. The spec was internally
  inconsistent: line 87 already listed `box-shadow`, the forced-colors pass *assumed* it was
  honoured, and the column producing the verdict named no method at all. Now a **resting-vs-focused
  diff** — property-agnostic, because the next design system will use something no list names. The
  skip link is judged **focused**, where a correct `sr-only` one is visible. And a blocking S1 whose
  row records no method is now itself reported.

- **The README named version 1.3.1 while the marketplace shipped 1.80.0.** It listed 5 of 42
  commands, omitted both skills shipped that day, and put **Install at line 732**. Re-authored to
  194 lines with install at line 12; the two deep sections moved verbatim rather than deleted.

- **A wiki, sourced from the repository.** A GitHub wiki is a separate repo with no PR, no review and
  no gate — which is exactly how the README rotted. Three reference pages are **generated** from the
  manifest and drift-gated, seven are written, and a workflow mirrors them on every push to `main`.

Three defects in this batch were caught by checks rather than review, and one by a reader: a
selftest assertion reading `… or True` (a gate that cannot fail, inside a script whose job is
refusing to go stale), a rebind landing on a second module object because a script run as `__main__`
imports itself as a different module, a mutation still aimed at a line an earlier rewrite deleted —
and every wiki link pointing at a raw file, because a GitHub wiki resolves siblings by page name
rather than by filename.

### 2026-08-08 (release v1.80.0)

> ### Look before you design — and the research gates the spending
>
> A designer gathers references, works out *why* each works, and builds from the mechanisms. Skip
> that and you do not get nothing: you get the median of everything the model has seen.

- **Reference research, scoped to any interface** (not just marketing — the method is identical for
  a dashboard or an onboarding flow). Three rules are **enforced rather than written down**: three
  sources minimum and never all from one category, a mechanism rather than a brand name, and
  something rejected — because a record where everything was adopted is a shopping list.

- **Every capture failure is silent**, which is what the operational half is really about. Lazy
  loading returns empty placeholders; a **login wall returns a sign-in form**; a rotted CSS-in-JS
  selector returns nothing. None errors, all produce a file with the right name. On gated galleries
  the agent stops and asks the human to sign in **once** into a reusable profile, never handling
  credentials; on a deliberate block it stops rather than escalating technique.

- **Research gates the asset plan.** The order is not cosmetic: research settles the style, and the
  style settles which assets exist at all. Without the check the failure is invisible — a plan
  written without research looks exactly like one written with it.

- **Affordability is group-atomic.** A hero still and its motion loop are one artefact in two files;
  buying the loop alone is worse than buying neither. A group is bought whole or skipped.

- **The four scripts flagged last release are guarded**, plus three more rules the meta-gate then
  demanded — once a guard exists, every rule that script emits needs one, because a partial guard
  looks covered. Targets were found **empirically**, since guessing had already failed three times
  here. The harness also caught **drift**: a mutation still aimed at a line the group rewrite deleted.

### 2026-08-08 (release v1.79.0)

> ### The autonomous driver is done, and the last check was on the checks
>
> Verifying #488's own definition of done against the repo — rather than against memory — found
> that two shipped pillars had selftests nothing proved could fail.

- **Pillars 1 and 3 had no mutation coverage** (Refs #488). Their fixtures ran; nothing showed those
  fixtures could fail. The `mutation coverage` gate proves every **declared** mutation is caught, and
  never that everything testable is declared — so two pillars sat uncovered with nothing going red.
  Each now carries the mutation that matters: for `toolchain_version`, the newest install record
  stops winning so a **stale** version reads as installed; for `escalation`, the marker matches
  anywhere instead of at the start, so a **quoted** question reads as agent-authored and the thread
  parks forever.

  Registering them took three attempts, and the second is worth remembering: `"\ufeff"` inside a
  normal Python string is **evaluated at parse time**, so the file held the right characters while
  the runtime value held an actual U+FEFF and matched nothing. A raw string fixes it. That
  invisible-character class has now bitten twice in this repo, both times with the file looking
  correct.

  **Four scripts remain unguarded** — `check_criteria`, `extract_claims`, `findings`,
  `self_consistency`, all pre-dating this work — named rather than silently left, because a count
  nobody wrote down is how this went unnoticed.

### 2026-08-08 (release v1.78.0)

> ### The asset pipeline is complete: set up, plan, cost, generate, reconcile
>
> `/design-flow:assets` is the missing front end — it scaffolds the config with a placeholder key,
> holds the plan of what the product needs, and refuses to start a plan the budget cannot finish.

- **`/design-flow:assets`** (Refs #507). Three files, three jobs: the config says *how to buy*,
  `plan.json` says *what the product needs*, `manifest.json` says *what the project owns*. **The gap
  between the last two is the remaining work** — keep only the manifest and a library nobody has
  finished planning looks finished. Re-running **resumes rather than resets**: a `done` row is never
  re-bought, and a second scaffold re-pins the brief and changes nothing else.

- **The plan is costed before anything is generated.** Generating until the money stops leaves an
  **arbitrary** half of the set, and a half-built family of illustrations is not a cheaper library —
  it is an incoherent one, and you cannot tell by looking which half is missing. The refusal prints
  the shortfall and what fits by priority; `--confirm-partial` generates exactly that and leaves the
  rest `planned`, not `failed`, because they were never attempted. Three caveats are printed rather
  than hidden: the estimate is a **floor**, unprioritised rows were split by **plan order**, and
  `--spent` is an **input** because nothing here can read a provider balance.

- **Two kinds of drift are detectable now.** A pinned **PRD fingerprint** catches a plan written
  against a brief that has since moved — every row `done`, status clean, new surfaces with no rows.
  And **reconciliation** reports any manifest entry with no plan row, so an agent generating ad-hoc
  must record its rationale and use cases or the plan stops describing the library it tracks.

The checks caught two defects in their own author's work: `--check` blessed an **empty** plan — the
exact state the scaffold creates — while a comment three lines above claimed the case was covered;
and a row whose surface had no brief passed review and failed only after the spend. A mutation also
**survived** because it was written as `[] or [...]`, which evaluates to the original list.

### 2026-08-08 (release v1.77.0)

> ### The asset path produces, and the driver stops asking when it could work
>
> Both fixes came from running the thing rather than reasoning about it — one from a downstream
> driver run, one from the mutation harness turning on the code that had just been written.

- **`/design-flow:generate` produces now** (Refs #507). `generate_asset.py` preflights the key,
  calls the provider, saves the asset and appends its manifest row — a **separate script from the
  gate**, because a decider that also spent could prefer the decision that justified the spend it
  wanted. It **re-runs the gate** rather than accepting an approval, so a hand-written
  `{"approved": true}` cannot bypass the library check, the tier precondition, the composed prompt or
  the budget ceiling. The key preflight distinguishes **absent** from **placeholder** — only the
  second is a forgotten step — and both refuse at exit 1, correcting an inconsistency where a missing
  aggregator refused while a missing key errored.

- **The driver stopped to ask when it had work it could do** (Refs #488). A scope-flagged
  enhancement sat first in the backlog, so it escalated and halted — while a QA pass needing no
  permission waited beside it. It now takes the first candidate the policy lets it take **alone**,
  keeping the escalation as a fallback for when nothing autonomous remains. Over-asking is the
  failure the decision-rights matrix exists to prevent; it just wears the clothes of caution.

- **Reverted the same day: no permission-allowlist scaffolding in the plugin.** A plugin has no
  business configuring a user's permissions, and the passage contradicted itself — it advised
  choosing a permission *mode* rather than extending a list of binaries, then shipped 38 lines of
  list-building.

The mutation harness found **three defects in the guard written minutes earlier**: a missing `needs`
made every mutation "catch" a `ModuleNotFoundError` instead of a verdict, two `expects` named the
pass message rather than the failure message, and one fixture would have dialled a real provider once
mutated. A crash is not a verdict, and a test that reaches the network to prove a refusal is a bill.

### 2026-08-08 (release v1.76.0)

> ### The autonomous driver is complete, and the asset path refuses by default
>
> Two features, and in both the interesting work was deciding what NOT to build: the driver does
> not own its own stop conditions, and the asset path names no model.

- **All four pillars of the autonomous flow driver now have machinery** (Refs #488).
  `/rails-flow:drive` answers two questions per tick — what is next, and may I do it alone. It
  chooses **one** action, never a menu. The decision-rights matrix is configurable and **rots safe**:
  an unclassified action escalates, and a policy with no `escalate` list is refused outright, because
  that is full autonomy wearing a config file. The test that keeps it checkable is *"does it publish,
  or can it not be undone"* — readable from the action, unlike *"is this important"*.

  **It deliberately does not re-implement the circuit breakers.** `breaker.py` already owns all of
  #128's doctrine; a second set could disagree with the first, and when two safety systems disagree
  the more permissive one wins. Craft is autonomous, scope is not — and the line is not size: a
  redesign leaving every journey intact is craft, while the same redesign quietly dropping a step is
  scope wearing a visual diff.

- **`/design-flow:generate` — the pay-as-you-go asset path** (Refs #507). Refusal is the working
  state. It refuses an unsearched library, an unrecorded tier-1/2 refusal, a free-typed prompt, a
  missing aggregator, a cost over the ceiling, or a ladder climb with no stated acceptance check —
  each **before** any call, because `|| echo` around a cost check is `gate-that-cannot-fail` with a
  bill. The library is curated **once**, after the PRD becomes skills and before any coding, then
  grows by coverage rather than duplication. Its manifest is a reference table — purpose, use cases,
  **where the asset must not go**, visual elements, style, kind — because a row naming only a file
  gets the asset re-generated by whoever could not tell.

  `style` is a closed taxonomy, and that came from **looking**: screenshotting a survey of brands
  showed Mailchimp's monochrome ink and Headspace's rounded flat-vector characters are both
  *"calm, abstract"*, so a mood-only brief lets one pack drift across two looks. No model names in
  doctrine — the contract is named, the vendors live in project config.

Between them the mutation harness caught **four defects that the selftests passed over**, including
one mutation that **survived** a redundant guard and one caught **by the wrong fixture** because the
code crashed instead of refusing. A crash is not a verdict.

### 2026-08-08 (release v1.75.0)

> ### A gate sweep reported 67/67 green on a commit that deleted 7,950 lines
>
> Four fixes, and the one that matters most is mine: v1.74.0's own CHANGELOG edit destroyed
> eight of nine component sections, and every gate passed. The rest came from a user running
> the toolchain into a fresh Rails app, which found three defects our review had not.

- **The CHANGELOG lost 7,950 lines and CI stayed green.** A two-anchor splice —
  `t[:t.index(a)] + new + t[t.index(b):]` — assumed the second anchor sat just after the first. It
  sat seven thousand lines further down, so the slice removed everything between: `rails-flow`,
  `qa-flow`, `pipeline`, `design-flow` and both `rails-stack` sections, with every release history
  they held. Restored from the last good blob and asserted **additions only** against it (`+88 −0`).
  New **`changelog-section-missing`** gate: every plugin in `marketplace.json` must still have a
  `## ` section. It matches `## ` alone, because the truncation left `###` release blocks behind and
  any-heading matching would have passed on the damage — and it was validated by replaying it over
  the real damaged commit, where it names all five missing plugins.

- **`dismissable?` was dead code** (#556). The predicate exists to keep a close button off a
  `:loading` toast; the template gated on `action.present?` and never called it. Those differ on
  exactly one case, and it is the case the predicate exists for: a `:loading` toast **with** an
  action — *"Uploading… · Cancel"* — which still rendered a close button, so pressing it hid an
  operation that was still running. The prose stated the correct rule **twice** while the code did
  the opposite.

- **Four component templates rendered strings through a lazy `t('.key')` with no key defined**
  (#555). A missing key does not raise — Rails renders `translation missing: …` **into the
  attribute**, so for two `aria-label`s the failure is audible only to a screen-reader user. The
  report named one; there were four. Two other lazy lookups were left alone **deliberately**: one
  sits in a controller, one in a plain view, where the lookup resolves as a reader expects. The
  defect was never the lazy form — it was a *component* template relying on a resolution the recipe
  never stated.

- **`@variant dark` should be `@custom-variant dark`** (#555). We emitted the directive that
  *applies* an existing variant where Tailwind v4 requires the one that *defines* a new one
  ([dark mode](https://tailwindcss.com/docs/dark-mode),
  [functions and directives](https://tailwindcss.com/docs/functions-and-directives), verified
  2026-08-08). It survived because `tailwindcss:build` exits **0** either way. Of seven `@variant`
  occurrences in shipped content only **two** are the directive; the other five are Ruby instance
  variables, so a blind replace corrupts five components to fix two lines.

- **`derived-artifacts` and `parallel-session-lane` now ship**, bundled in `rails-stack`. Neither was
  ever about this marketplace. `parallel-session-lane` was **generalised**, not copied — it hardcoded
  our own directory layout. `plugin-boundaries` stays maintainer-only by its own rule 3, and no copy
  was left behind for the two that moved.

The sweep went **65 → 67**, and three existing gates caught consequences of that move that review
missed: a shipped skill needs a `comp:` label, the routing gate refused with **CANNOT CHECK** rather
than passing on a pin it no longer recognised, and `CLAUDE.md`'s distribution list was under-naming
what `rails-stack` bundles.

### 2026-08-07 (release v1.74.0)

> ### Three issues where the report was wrong, and testing the substrate found it
>
> Every slice here started by checking a claim the issue stated confidently. Seven of those
> claims were false, and each failed **silently** — a stale toolchain reading as current, a
> parked question nobody was emailed, an error announced politely.

- **Pillar 1 of the autonomous flow driver: the toolchain self-update gate** (Refs #488).
  `/rails-flow:toolchain-check` resolves what is installed, compares it against what is published,
  and carries a durable marker across the restart an update requires. **Exit 2 (cannot resolve one
  side) is never folded into exit 0** — "I could not read the installed state" is not "you are up
  to date". Five of the EPIC's substrate assumptions were wrong; the load-bearing one is that the
  two version sources are **disjoint**: `rails-stack` is versioned only in `marketplace.json`, the
  four code plugins only in their own `plugin.json`, so reading either alone misses the other set.

- **Pillar 3: the async human-in-the-loop** (Refs #488). `/rails-flow:escalate` asks on a GitHub
  issue, labels it so the human is emailed, parks the thread durably, and **moves on**. The EPIC's
  "find replies by timestamp/**author**" cannot work — `gh` posts with the user's own token, so the
  agent's comments carry the *same login as the human*. Replies are found by an invisible marker
  instead, required at the **start** of the comment so a quoted question is not mistaken for the
  agent's own writing. And a missing label **errors** rather than degrading, so both labels are
  created before anything is posted: the label is what sends the email, and a thread parked on a
  question nobody receives is the one failure this loop cannot recover from.

- **The setup step flattened the toast's conditional role** (Refs #483). Doctrine renders
  `role="<%= intent == :error ? 'alert' : 'status' %>"`; the scaffold said `role="status"`, flat.
  `status` implies `aria-live="polite"`, so an error announced after whatever is already queued —
  failing silently, and only for screen-reader users. New `flattened-conditional-role` gate, whose
  **first version fired on the fix for the defect it was built to catch**.

- **The production password-strength policy is complete** (Closes #484). All five criteria verified
  against the repo with line references, including the subtle one: sign-in still authenticates a
  digest that predates the policy. The catalog entry forbids the character-class checklist, citing
  *SP 800-63B-4*'s "SHALL NOT impose other composition rules" — a meter ticking "has uppercase · has
  a digit" **is** that rule rendered, and it teaches users that `Passw0rd!` beats a passphrase.

The gate sweep went **65 → 67**. Both new selftests were registered only because the repo's own
`mutation coverage` gate failed on a sweep that would have reported clean having never run them.
Two further defects in these diffs were caught by our gates rather than by review: a literal U+FEFF
written to strip U+FEFFs, and a docstring citing a flag that does not exist.

### 2026-08-07 (release v1.73.0)

> ### Four survivors of one rewrite, and a sweep that silently swept nothing
>
> v1.72.0 rebuilt the toast. The rewrite was right; what it left behind was not. #542 caught two
> stale remnants an hour later, #546 found two more — and the sweep meant to prove there were no
> others matched nothing at all, because of a shell glob.

- **The toast examples crashed, in more places than were reported** (#546). The rewrite made `title:`
  required and removed `message:`, but the flash→toast examples still passed `message:` — so **the exact
  wiring the section teaches raised `ArgumentError`**. The report named two call sites; there were
  **five**, three of them in `crud-modal-pattern.md`, a file it does not mention. One also passed
  `undo_path:`, a *third* dropped keyword, now expressed through the `action:` slot the rewrite added.

- **`border-l-<%= intent %>` was interpolation posing as a token** (#546). It emits `border-l-error` and
  `border-l-loading`, and a conformant theme has **neither**: it names the error colour `destructive` —
  as `Ui::Alert`'s own `INTENT` map already did — and ships no `loading` colour at all. The accent
  vanished on precisely the two intents that most need it, and a pack passing the brand-pack lint still
  rendered them unbranded. It is a **mapped constant** now, with all five tokens checked to exist.

The lesson is one this repo keeps paying for: **renaming a keyword in a signature does not find its call
sites**, and a regex that fixes one passage does not find the others. Worth recording alongside it — the
first repo-wide sweep for the dropped keywords **failed on a shell glob and printed `0 hit(s)` for every
term**. It read as a clean result. That is a gate that cannot fire, in the very check written to prove
the rewrite was complete.

### 2026-08-07 (release v1.72.0)

> ### A user report, and the references corrected me twice
>
> *"The toast card is big."* It was arithmetic, not taste — and fixing it properly meant reading the
> reference implementations, which then contradicted two rules shipped the day before.

- **The toast was a card** (#540, #483). `box` applies `--space-s` (16–20px) on all four sides,
  `min-h-touch` forces a **44px** dismiss target inside, `max-w-sm` fixes the width, and the message
  inherited `text-step-0` — so *"Saved"* rendered roughly **80px tall by 384px wide**. `box` is the
  **content-panel** primitive; a toast is transient chrome.

  Rebuilt to the reference anatomy — **container · optional icon · text · optional action · optional
  close** — with the close button appearing **only beside an action**. That fixes the size at its source
  rather than working around it: no button, no touch target, nothing forcing the height. `title` +
  optional `description` replace the single `message`, and an **action slot** finally exists, because
  *"Task deleted · Undo"* is the canonical toast and without a slot the verb lands in the text with
  nothing to press.

- **Two rules from the previous release were wrong.** Errors were made persistent, reasoned from
  `role="alert"` — which conflates **announcement** with **persistence**. A message that must remain
  visible is `Ui::Alert` in the page; one that must be answered first is `Ui::Modal`.

  **And the correction over-corrected.** *"There is no persistent variant"* is false: `:loading`
  persists while its operation runs, then is **replaced** by the outcome — found only by reading a
  reference implementation's **source**, since its published docs do not mention it. A loading toast
  gets no close button either: dismissing a running operation leaves the user unable to learn how it
  ended.

- **The touch-target arithmetic, verified.** `min-h-touch`'s 44px is **WCAG 2.5.5 Target Size
  (Enhanced), level AAA**. The level-AA requirement, **2.5.8**, is *"at least 24 by 24 CSS pixels"* —
  checked against the W3C understanding document. Paying 44px inside a transient element bought AAA by
  doubling the notification's height.

- **A stale remnant of the reversed rule survived the rewrite** — an ERB snippet still showing the error
  exception, and a sentence claiming the dismiss button *"already has `min-h-touch`"*. A
  `doctrine-contradiction` inside the file just corrected, found by grepping the pattern rather than
  trusting the edit.

**Versions:** rails-stack 1.41.0 → **1.42.0**.
**Gates:** 65/65, CI-verified. **Mutation check:** 411 mutations across 32 guards, all caught.

### 2026-08-07 (release v1.71.0)

> ### A true claim with nothing behind it
>
> §2a offered a lower password floor *"where it is one factor of multi-factor"* — correct, and
> unsatisfiable, because the skill contained no MFA guidance at all. Not a wrong claim; a right one the
> reader could not act on, which sends them out of our doctrine to re-invent per app.

- **§2b — multi-factor** (#531). **Rails 8 ships none**, verified against the installed gem rather than
  assumed: the authentication generator's two migrations are its whole persisted surface, and a sweep
  for `totp|webauthn|passkey|mfa|otp` over the generator tree returns **zero**. Checked on two versions
  with the same result, and the version boundary is recorded so it can be re-checked.

  What Rails *does* give you: `authenticate_by` verifies multiple **stored** secrets in one
  timing-hardened call — useful, and **not** a TOTP path, because a TOTP is clock-derived and has no
  digest to compare. The `Session` model being a **row** is the real hook.

  Three rules, ours, and the ones most often got wrong: **replay** — NIST's *"SHALL accept a given OTP
  only once while it is valid"*, against `rotp`, which reports validity and never use; **MFA is a
  property of the session, not the user**, or enrolling retroactively blesses every existing session
  including one an attacker holds; and **recovery codes are a set**, needing their own table with
  `used_at`, hashed, shown once.

  **SMS is *restricted*, not deprecated.** The popular claim is wrong, and shipping it would be the same
  defect as any other unverified assertion. Restricted is a status with obligations — an alternative
  **SHALL** be available, subscribers *SHOULD* be warned, risk signals *SHOULD* be weighed.

- **`dangling-conditional-floor`** — offering the discount obliges the file to carry the guidance.
  Structural rather than a judgement: it asks whether the second factor is discussed at all, and a file
  that never offers the discount owes nothing.

**Versions:** rails-stack 1.40.0 → **1.41.0**.
**Gates:** 65/65, and **CI verified** — the first green hosted run since yesterday's Actions outage.
**Mutation check:** 411 mutations across 32 guards, all caught.

### 2026-08-07 (release v1.70.0)

> ### A research session found a security defect in doctrine we had already published
>
> Sent to establish what Rails 8 ships natively for MFA. The answer was **nothing** — 19 generator
> templates, zero MFA terms. The useful finding was elsewhere: a 2FA recipe of ours that produces a
> one-time password which is not one-time.

- **We shipped a 2FA recipe producing a replayable OTP** (#531). `ecosystem-gems.md` said *"Need email
  confirmation, lockouts, or 2FA? Add a column, a mailer, a `rotp` check."* True of the plumbing,
  dangerous as a recipe: `rotp` reports whether a code is **currently valid**, not whether it has been
  **used**, so that check accepts the same code repeatedly inside its window. *NIST SP 800-63B-4* makes
  single-use a **SHALL**. 2FA is removed from the add-a-column sentence, which stays correct for
  confirmation and lockouts.

- **A raised password floor now reaches the accounts already under it** (#484). §2a shipped saying
  *"let existing users through until they next set a password"* — which grandfathers a six-character
  password indefinitely, binding only the users who were going to comply anyway. After
  `authenticate_by` succeeds, a sub-policy account is now confined to the change screen.

  **Stated as ours, not as compliance.** The verifier found NIST authorises neither reading: a password
  merely shorter than a floor raised after it was set is *not* evidence of compromise, and a later
  blocklist match as evidence is INCONCLUSIVE. It does not collide with the `SHALL NOT` on **periodic**
  rotation — but "does not collide with" is not "is required by", and the original wording was the
  position the standard actually supports. The step beyond is deliberate and recorded as a decision.

  The mechanism matters: **a bcrypt digest cannot be measured**, and a `password_length` column would
  hand anyone reading `users` a head start on every account. So the **policy version in force at
  set-time** is recorded — one integer, `default: 0`, so every pre-existing row is stale by
  construction.

- **Seven bare `SP 800-63B` citations corrected to `SP 800-63B-4`** — plus an eighth in
  `components.md` that was out of that session's lane. Rev 4 (July 2025) **supersedes** the 2020
  edition, and the 15-character floor exists **only** in rev 4, so a bare citation pointed at a document
  not containing the number it was attached to. Citation precision, not a guidance correction.

- **The password-strength component, implemented** (#484). Floor read from the model, debounced live
  region, *unknown* as a state, no submit gating. Three of our own gates caught gaps in it as it was
  written.

**Versions:** rails-stack 1.39.0 → **1.40.0**, design-flow 1.15.0 → **1.15.1**.
**Gates:** 65/65. **Mutation check:** 409 mutations across 32 guards, all caught.

### 2026-08-06 (release v1.69.0)

> ### Three issues closed out, and each one's own gate caught something on the way
>
> The design-flow trio had to serialise — they all touch the same two components — so this is the
> sequential half of the parallel batch. In all three cases a gate we already ship found a defect in the
> change being made to satisfy it.

- **The critic joins the review path** (#486, complete — all 8 criteria). `/design-flow:audit` now runs
  the critique **alongside** it, findings deliberately **unmerged**: a `file:line` fix and a missing
  decision carry different authority, and one list means the reader cannot tell which blocks.
  `/design-flow:variants` gains it as its **ranking rubric** — conformance cannot rank, because every
  variant there is conformant by construction.

- **Flash → toast, the half the layout promised and nothing implemented** (#483). The reference layout
  said *"flash output goes to `#toasts` via Turbo Stream"* and **no code anywhere read `flash`** — so a
  Turbo Stream response showed its toast while a plain `redirect_to … notice:` showed **nothing at
  all**, since the layout renders no flash partial by design. The message was not un-styled; it was
  **lost**. Errors not auto-dismissing falls out of the existing markup rather than being a new rule:
  `:error` already renders `role="alert"`.

  `undeclared-component-call-site` then fired on the new `render` and found that **`ToastComponent` had
  never been declared** — the section shipped its ERB and no Ruby class. Invisible until now because the
  existing call sites use `turbo_stream.prepend(...)`, which that rule does not match.

- **Password strength, with the checklist the issue asked for removed** (#484). #484 specified *"a live
  requirement checklist"*, which **is** the composition rule NIST prohibits, rendered — and teaches that
  `Passw0rd!` beats a passphrase. The component shows length progress, confirmation match, and the
  server's blocklist verdict; never a score, never character classes. **Submit is not gated on the
  meter**, because a client disagreeing with the server either blocks a valid password or lies about an
  invalid one.

- **`hook-count-drift`** — CLAUDE.md said *"of the ten hook scripts, eight are advisory"*; there are
  **eleven**, nine advisory, the eleventh being design-flow's. Third stale doc-number about our own
  files, second time the missed component was design-flow (#203, #489). The advisory figure is now
  **derived**, not read.

**Versions:** rails-stack 1.38.0 → **1.39.0**, design-flow 1.14.0 → **1.15.0**.
**Gates:** 65/65. **Mutation check:** 409 mutations across 32 guards, all caught.

### 2026-08-06 (release v1.68.0)

> ### Three parallel sessions, and each one found an error in the issue it was given
>
> Worked in separate git worktrees under the `parallel-session-lane` protocol. None of the three took
> its issue at face value, and all three corrections are in this release — which is the argument for
> *"an issue body is a hypothesis, not a specification"* holding up under delegation.

- **`project_gates.py` routes every finding to a tracker** (#485). App gap → the project's tracker;
  `requires` binary absent → environment, nobody's; ERROR or unparseable manifest → **doctrine**,
  upstream. Derived from the outcome rather than declared per check. It also fixes a shipped defect: the
  summary folded ERRORs into the same total as findings, so **a manifest of ours naming a missing script
  of ours read to a user as a defect in their own app.** The issue claimed `/rails-flow:review` is
  diff-scoped — it is not (*"Full parallel codebase review"*); the diff-scoped command is
  `/design-flow:audit`. The two were swapped, and that changes the gap: not *"nothing sweeps the whole
  codebase"* but *"nothing sweeps it against plugin doctrine mechanically"*. A docstring claiming eleven
  checks was also wrong — the manifests declare **fifteen**.

- **A mention of an agent is not a dispatch** (#491). `undeclared-topology` counted a backticked name,
  so a sentence explaining *which agent consumes a command's output* read as dispatching it. It now
  requires a signal a dispatch has — subject position, handoff arrow, an imperative **in the name's own
  sentence**, or a `Task(…)` invocation. The narrowing is **deliberately biased toward counting**,
  because here a false negative is worse: an undeclared parallel topology ships two agents whose
  disagreement nobody defined. Six fixtures in both directions, including the negative one the issue
  warned was missing, plus a counter — a silence fixture proves the rule does not *fire* on a mention,
  only a moving number proves it can still *see* one.

- **A generated, committed map of what this marketplace ships** (#509). 138 rows: 27 agents, 37
  commands, 64 gates, 4 tier tables joined 1:1 to the agents. The issue's *"68 gates"* was already stale
  — the page renders `len(GATES)` and a fixture pins the equality, so it cannot drift into prose again.
  Its own `--check` fixtures had stubbed the function under test, so a mutation survived the entire
  selftest — **the defect the gate exists to prevent, inside its own test** — now pinned against a
  throwaway repo where commit and working copy disagree.

- **A generated asset is unusable until its fitness is reviewed** (#507). Nothing makes a prompt produce
  the asset you asked for; the test in v1.67.0 proved it. **Fitness is not taste**: taste is judgement and
  stays advisory, fitness is a comparison against a brief we wrote and therefore **blocks**. No recorded
  brief is a fail.

- **`harness-doctrine.md` carried two stale counts about the rule it documents** (#491) — found by the
  session fixing that rule, which correctly refused to edit `docs/` from outside its lane and reported
  the correction instead.

**Versions:** rails-stack 1.37.0 → **1.38.0**, design-flow 1.13.1 → **1.14.0**, rails-flow 1.18.2 →
**1.19.0**.
**Gates:** 65/65. **Mutation check:** 406 mutations across 32 guards, all caught.

### 2026-08-06 (release v1.67.0)

> ### Generation enters the asset hierarchy — and the test contradicted the first draft
>
> The doctrine for generated assets was written, then a real generation was run against it, and the
> result narrowed the tier before it shipped. Also here: a dependency nine files relied on that nothing
> could declare, and a control byte that made a brand-new gate unable to match anything.

- **Generated assets enter the hierarchy as two cost-ordered tiers** (#507). Product screenshot ·
  brand-geometric decoration from `brand.json` · **designed graphic** · **generated illustration** ·
  commissioned, ordered by *specificity first, then cost*. The load-bearing distinction: **tier 3
  inherits the brand, tier 4 is prompted toward it and may miss** — a design tool assembles from parts
  you gave it, a diffusion model invents.

  **Tested end to end before the doctrine was allowed to stand, and tier 2 won.** The pipeline works — a
  real 1920×1080 PNG came back — but it **ignored the composition brief** (asked for empty space in the
  left two-thirds, returned a centred motif), there is **no SVG export**, so a backdrop is a **126 KB
  raster** against a few hundred bytes for the equivalent `decor-mesh`, and what it produced was abstract
  geometric decoration — precisely what tier 2 already derives from tokens. Tier 3 is therefore scoped to
  **what tier 2 cannot do**: composed scenes, product-adjacent mockups, editorial assembly, brand motion.

  **Tier 3 is exported assets only, never a page** — verified against the tool surface: exports are
  PDF/JPG/PNG/PPTX/GIF/MP4 with **no HTML**, and the design-type list has no website option at all. A page
  authored in a design tool is a fork of the system, which this file's own *"a pack is a theme, not a
  fork"* rule forbids. **§10 was reconciled, not contradicted** — it had said the system *"produces
  nothing"*, true when v1.66.0 shipped it and false now; the improvisation ban survives, because a
  provider present but misconfigured is a new way to end up with nothing. The `brand.json` ↔ external
  brand-kit drift hazard is **named and explicitly not gated**; `brand.json` is authoritative.

- **Nine files depended on a skill from another plugin, and nothing could declare it** (#513). All four
  design-flow agents and five commands read `skills/fidara-design`, which ships only inside the
  `rails-stack` bundle, and no `plugin.json` carries a `requires` field — so installing design-flow alone
  gave you agents whose own text calls that doctrine *"the law"* about an absent file. Each command now
  names what is missing and **stops**. `undeclared-skill-dependency` holds them to it: verified against
  the pre-fix tree, 5 examined and **5 reported**.

- **`invisible-character` could not see a control byte, and one had already shipped.** A `\b` written
  through a shell heredoc became a literal `0x08` inside the new rule's own regex, which then required a
  backspace after *"stop"* — the gate reported clean on input it could never match, and
  `inspect.getsource` rendered it invisibly. `repr()` on the line exposed it. The table now covers
  BACKSPACE, VERTICAL TAB, FORM FEED, ESCAPE, BELL and NUL, and immediately found **5 backspace bytes
  already in `CHANGELOG.md`** from the same mistake in an earlier session. All cleared; the repo holds zero.

- **`duplicate-unreleased`** — one `### Unreleased` per component section, after making that error twice
  in three releases. And **`plugin-boundaries`**, a maintainer skill for deciding where content belongs;
  it earned its keep on first use, since reading it against #507 is what surfaced #513.

**Versions:** rails-stack 1.36.1 → **1.37.0**, design-flow 1.13.0 → **1.13.1**.
**Gates:** 63/63. **Mutation check:** 395 mutations across 32 guards, all caught.

### 2026-08-06 (release v1.66.0)

> ### A file that named a failure and did not close it off
>
> `visual-assets.md` has warned since it was written that an agent with no boundary will *"leave it
> empty, generate something inconsistent, or import stock art that undercuts the brand"*. It never
> said the system generates nothing — so the boundary was absent, which is precisely the condition
> that sentence describes.

- **The asset boundary, declared** (#503). §10 listed rejected *techniques* — ambient motion, SVG
  filters, `mask-*`, vendored illustration sets — and never the capability. Tier 1 is captured from the
  running product, tier 2 is CSS/SVG derived from `brand.json`, tiers 3–4 are sourced by a human and
  recorded; a grep for any generation path across `skills/` and `plugins/` returns **0 files**. Now
  explicit, with the rule that matters: if a surface cannot be satisfied from tiers 1–2, **say so and
  stop** — name the surface and what the tiers could not carry, and never ship a placeholder, a stock
  photograph, a hand-rolled "illustration", or an empty box where an asset was implied. §6 keeps this
  rare by making tier 2 and expressive typography *primary rather than fallback* on exactly the
  surfaces with nothing to screenshot.

**Versions:** rails-stack 1.36.0 → **1.36.1**.
**Gates:** 63/63. **Mutation check:** 393 mutations across 32 guards, all caught.

### 2026-08-05 (release v1.65.0)

> ### Nineteen references answered "is this correct?" and none answered "is this considered?"
>
> Everything the toolchain shipped was *avoid-the-bad* or *match-the-system*. A surface could pass
> every gate and be correct, accessible, dark-mode-aware and lifeless. This release adds the missing
> half — and deliberately adds it as a **lens**, not a gate.

- **The craft layer, `art-direction.md`** (#486). Measured first: `art direction`, `visual hierarchy`,
  `focal point`, `look and feel`, `aesthetic` all returned **zero** across the skill, and
  `design-auditor`'s own priority order is `breaks-consistency > a11y > polish` — polish last, and
  framed as consistency. The doctrine: **one focal point per surface**, carried by scale **or** weight
  **or** contrast and never all three; a **different brief per surface class** — marketing is emotion,
  a dense app is clarity — which is the direct answer to *"the marketing pages look like slop and the
  app looks too mechanical"*, because both had been given one treatment; **taste inside the
  constraints** with exactly one bounded escape, which may break the grid or the scale and **never**
  the token contract, since a bespoke hex outlives the brand it was chosen for; negative space as
  grouping; motion as sequence. Two worked before/afters whose **"before" passes every gate we ship**.

- **`design-critic` + `/design-flow:critique` — advisory by construction** (#486). All three existing
  agents were correctness roles. The critic judges hierarchy, focal point and brief-fit and returns
  ranked suggestions with the missing decision named — never a pass, fail, score threshold or merge
  condition. Not timidity: **#476** proved a taste gate cannot hold, because its threshold flagged our
  own worked band sequence, and a switched-off gate leaves nothing checking anything. Consistency
  findings stay the auditor's — two roles grading one thing disagree in front of the user and the
  blocking one wins — and the critic gets **`Read, Grep, Glob` only**, because a lens that rewrites
  what it judges is not a second opinion.

`SKILL.md`'s routing description said *"Consistency is enforced here, not left to taste"* — true of
consistency, but it reads as taste being out of scope. Reconciled rather than overwritten.

**Versions:** rails-stack 1.35.0 → **1.36.0**, design-flow 1.12.2 → **1.13.0**.
**Gates:** 63/63. **Mutation check:** 393 mutations across 32 guards, all caught.

### 2026-08-05 (release v1.64.0)

> ### The most useful output of a verification is sometimes a refusal
>
> A report asked for a password policy offering *"either character-class composition or a breach
> check"*. NIST prohibits the first and mandates the second. Shipping the contract as filed would have
> made every downstream agent enforce a rule the primary authority forbids — and would have built a
> UI whose whole job was to display it.

- **A production password policy, and the rule the report asked for that NIST forbids** (#484). A
  fresh Rails app accepts `a` as a password: `has_secure_password` gives bcrypt, the virtuals and a
  72-**byte** ceiling, and no strength policy. The doctrine's only mention was a **commented-out**
  `length: { minimum: 12 }`. `auth-security.md` §2a is now real doctrine, and it leads with the
  prohibition:

  > "Verifiers and CSPs **SHALL NOT** impose other composition rules (e.g., requiring mixtures of
  > different character types) for passwords." — NIST SP 800-63B

  …because *"at least one uppercase, one digit and one symbol"* is the most common thing a team bolts
  on and it makes passwords **worse**, pushing users toward `Passw0rd!` and away from a passphrase.
  The compromised-password blocklist is the **SHALL** people skip. Floor **15** single-factor (8 under
  MFA), not 12; the maximum is already validated by Rails so we do not re-add it; rotation is
  **SHALL NOT**. Write paths only with `allow_nil: true`, and **never on sign-in**, where
  `authenticate_by` verifies a digest that may predate the policy — re-validating there is a
  self-inflicted outage, and a spec pins that regression. Another spec asserts a passphrase with no
  digit and no symbol is **valid**, because a spec claiming otherwise asserts the forbidden rule.

**`password-floor-drift`** reconciles the floor the section *states* against the one its worked example
*enforces*, since the reader copies the example. **Deliberately not a prose rule** — a grep for
"at least one uppercase" fires on the sentence that *forbids* it, which is the mention-versus-
prescription false positive filed as #491 two releases ago rather than worked around.

**Versions:** rails-stack 1.34.0 → **1.35.0**.
**Gates:** 63/63. **Mutation check:** 393 mutations across 32 guards, all caught.

### 2026-08-05 (release v1.63.0)

> ### The third variant of one class: a scaffold that provisions everything except what the flow consumes
>
> After #487 (qa-flow labels) and #490 (rails-flow labels) last release, this is the same shape in
> design-flow — and the worst of the three, because the missing piece was the target of the CRUD
> pattern's own success path.

- **Three Stimulus controllers shipped orphaned, and every CRUD success dropped its feedback**
  (#483). `/design-flow:setup` listed the `toast` controller while its component list omitted the
  component it drives — and pointed at `reference-implementation.md` as *canonical for steps 3–4*,
  which carries both. The enumeration contradicted its own declared source, and agents follow the
  enumeration. `crud-modal-pattern.md` emits every success with
  `turbo_stream.prepend("toasts", ToastComponent.new(...))` at **three** call sites, so with no
  `#toasts` container the target did not exist. Writing the **join** rather than patching the report
  found `dropdown` and `tabs` in the same state, which the report did not mention.

  Two corrections to the report worth recording: there is **no `Ui::Toast`** in `components.md` — the
  component lives in `component-implementations.md` under `## Toast`, so implementing the name as
  filed would have invented one; and `aria-live` belongs on the **container**, which must be in the
  DOM before content is inserted, with `role="status"` on the toast and nothing beside it.

- **`parallel-session-lane`**, a maintainer skill for running several sessions against this repo at
  once — confirm your worktree, one coherent slice, stay in your plugin lane, review your own diff
  first. In `.claude/skills/`, so it ships to nobody and arrives automatically on a clone. Its "never
  work here" rule named an absolute home directory, which is wrong on every machine but one; it now
  resolves the primary checkout from `git worktree list`.

**A third gate**, `orphaned-controller`, which **discovers** the pairing instead of listing it: a
controller is paired iff `component-implementations.md` has a `## <Titlecase>` section, so `sidebar`
and `theme` are silent with no exemption. Verified against the pre-fix scaffold rather than assumed —
4 examined, **3** reported.

**Versions:** design-flow 1.12.1 → **1.12.2**.
**Gates:** 63/63. **Mutation check:** 391 mutations across 32 guards, all caught.

### 2026-08-05 (release v1.62.0)

> ### Two plugins filed issues with labels no setup created — so the reports were lost, not mislabelled
>
> `gh issue create` **errors and creates nothing** on an unknown label; it does not fall back to an
> unlabelled issue. Both defects therefore dropped a report at the exact moment the flow claimed to
> capture it. Two identical instances in two plugins is a class, so both are now enforced by a join
> rather than found by grep.

- **qa-flow filed every defect with labels the scaffold never created** (#487). `qa-reporter` uses
  `--label "qa,from-qa,severity:sN"` and `gh label create` appeared **nowhere** in the plugin, so the
  first real defect of any run was lost. `setup-qa` now provisions them idempotently — and **all four**
  severities, not the two that appear as literals: `verify.md` files `severity:sN` for whatever grade
  the defect earned and the ladder in `qa-lead.md` runs S1–S4, so an S3 finding would have failed at
  the `gh` call. Also clarified a sentence that conflated two deliberately separate vocabularies: the
  findings **record** field is `P1`/`P2`/`P3` (shared with rails-flow, gated by `findings.py`), the
  issue **label** is `severity:s1`…`s4`.

- **The same defect in rails-flow** (#490). `pr-comments` folds an out-of-scope review comment into
  the user's tracker with `--label "from-pr-review"`, which no setup created — so the item vanished
  and the instruction to *"reply on the thread with the new issue link"* could not be followed. Found
  by grepping the pattern after confirming #487. `claude-skills-reporter` is unaffected: its labels
  target the upstream tracker with `--repo`, where the taxonomy is somebody else's.

- **The label taxonomy's own source of truth was four components behind** (#489).
  `.github/labels.yml` is what `/maintainer-setup-intake` provisions **from**, and it declared 7
  `comp:*` for 9 live ones — `comp:fidara-design` and `comp:design-flow` were in active use on four
  open issues while undeclared. Writing the **join** instead of patching the two found two *more*
  missing from the file **and** GitHub (`comp:code-review`, `comp:quality-pass`). Same blind spot as
  #203, where CLAUDE.md's plugin list omitted `design-flow` for as long as it existed.

**Two new gates**, both pure file joins with no `gh` call, because a gate that needs network fails on
a runner for reasons unrelated to the repo: `unprovisioned-label` (a plugin filing against the user's
own repo with a label its setup never creates) and `undeclared-component-label` (`skills/*/` and
`plugins/*/` reconciled against the yaml, in both directions). 18 fixtures, 8 mutations.

**Versions:** qa-flow 1.24.0 → **1.24.1**, rails-flow 1.18.1 → **1.18.2**.
**Gates:** 63/63. **Mutation check:** 389 mutations across 32 guards, all caught.

### 2026-08-02 (release v1.61.0)

> ### The one subject we had nothing on, and four rules we decided not to write
>
> Both halves come from auditing our design doctrine against an external catalogue of 110 named
> failure modes. Of those 110, exactly **one** was a clean zero for us. The rest of the audit's
> value was negative — including four rules that looked obviously worth adding until they were
> measured.

- **Legal, privacy and consent surfaces** (#475). `grep -ril "privacy polic|cookie consent|consent
  banner"` over `skills/` and `plugins/` returned **0 files**, while v1.60.0 had just shipped
  checkout and billing. Three parts, with the change type split:
  - **Verified** — *ARIA in HTML* (W3C) gives `<footer>` `role=contentinfo` *"if not a descendant
    of an `article`, `aside`, `main`, `nav` or `section` element"*, **"otherwise `role=generic`"**.
    That interacts with the band rule shipped in v1.60.0, which tells authors to wrap bands in
    `<section>`: put the page footer inside one and the landmark **silently disappears**. Both
    rules are enforced by the **same join in the same file** so they cannot drift apart.
  - **Verified** — GDPR Recital 32: *"Silence, pre-ticked boxes or inactivity should not therefore
    constitute consent"*, which must be *"a clear affirmative act"*. Never render the box
    `checked`, never treat dismissal as acceptance, one checkbox per thing consented to.
  - **Ours** — that a consent surface is the **modal dialog we already document** rather than a
    bespoke banner (APG has no consent pattern; checked, not assumed), and that *which* surfaces a
    jurisdiction requires is the operator's decision. A design system shipping a compliance
    checklist would assert what it cannot verify.

- **Four monotony rules considered and rejected, each with its measurement** (#476). `LAY-017`
  (a layout family repeated more than twice) was **measured against our own table and rejected**:
  the shipped band sequence uses one shape for **3 of its 7** bands, because the hero, a prose band
  and the closing band legitimately share the shape for centred prose — so their threshold flags
  our own correct doctrine. `LAY-015` (repeated closing CTA) **contradicts** shipped doctrine that
  prescribes the repeat and gives its reason. `VIS-012` and `LAY-024` have no column to join
  against. Recorded in the gate's docstring, with the number **re-derived by a fixture** rather
  than asserted.

**Versions:** rails-stack 1.33.0 → **1.34.0**.
**Gates:** 63/63. **Mutation check:** 377 mutations across 32 guards, all caught.

### 2026-08-02 (release v1.60.0)

> ### A rule followed in sixteen places and written in none
>
> Completes EPIC #89 — the whole kit transformation — and #91, its commerce phase. The slice that
> closed it went looking for four missing catalogue entries and found instead that they should not
> exist, plus one rule the skill had been obeying without ever stating.

- **`<section>` is a landmark only when you name it** (#91). **Verified** against *ARIA in HTML*
  (W3C): `<section>` takes `role=region` **"if the `section` element has an accessible name"**, and
  `role=generic` otherwise — `generic` being exactly what a `<div>` exposes. So an unnamed
  `<section>` is inert markup that reads as structure: no landmark, no rotor entry, nothing to skip
  to. `page-anatomies.md` already obeyed this in **16 of its 18** sections and said so nowhere,
  which is `claims-vs-enforcement` inverted — a practice with no claim and no gate. Now stated, and
  held by `scripts/check_section_landmarks.py` (25 fixtures, 6 mutations; 61 → 63 gates). The two
  hero bands are a **deliberate** exception — a hero's heading is the page's `<h1>`, so naming the
  region repeats the page title and points the reader where they already are — and they are
  declared **by exact opening tag**, never inferred, because a carve-out that recognised its own
  exception by pattern would exempt every future lookalike. A declared exemption matching nothing
  is itself reported.

- **The ecommerce composition recipe produced a block that was not navigable** (#91). Every promo
  section in the corpus is a `<section aria-labelledby>`; the `Build from` string shared by **nine**
  coverage rows named no landmark, so an agent following it shipped a `div`. The recipe carries it
  now.

- **Four catalogue entries deliberately not written** (#91, #89). Trust/support was the last
  commerce slice, and the honest answer was that most of it earns no entry: across the eight
  incentive files in the corpus there are **zero interactive elements** and the only ARIA is
  `aria-hidden` on decorative icons — already `Card + Heading + text` in a grid. Declining to
  restate a composition we ship is the *"no duplicate mechanisms"* criterion working, not a gap.

**Versions:** rails-stack 1.32.0 → **1.33.0**.
**Gates:** 63/63. **Mutation check:** 374 mutations across 32 guards, all caught.

### 2026-08-02 (release v1.59.0)

> ### Two shipped rules that could never fire, and a coverage number that under-reported
>
> This release completes EPIC #108. Its most useful output was negative: an audit of the QA
> harness found **two rules we ship** — one graded S1, one S3 — reading fields **no collector
> recorded**. The doctrine was written, correct, and inert. Everything here was verified against
> a real Chromium run rather than fixtures alone.

- **The highest severity in our own taxonomy was the one thing nothing could observe** (#108).
  `functional-tester.md:95` prescribes `page.on('pageerror')` and `:105` grades an uncaught
  exception **S1** — *"the page is broken even though it rendered"*. The collector never
  registered the listener, so the S1 category could not fire on any run. Now captured and judged.

- **An S3 rule read two attributes nothing recorded** (#108). `functional-tester.md:171` grades
  `target="_blank"` without `rel="noopener"` as S3; the link inventory captured `href` and `text`
  only. Both attributes are now recorded **raw** and judged in Python: `rel` is **split on
  whitespace**, so a `noopenerfoo` typo does not pass as safe, and `noreferrer` satisfies the
  rule because it severs the same handle. Judged before the external short-circuit — an external
  target is exactly where a `window.opener` handle is worth reporting.

- **The "never launch a second server" guard could not fire in the case that does the damage**
  (#108). The reuse probe used `curl -fsS`, and `-f` exits non-zero on 4xx/5xx — so a server
  **up with a failing health endpoint** was indistinguishable from an empty port (exit 22 vs 7).
  It then started a second dev server into a build cache the first one held, which is the
  corruption the step exists to prevent. Grepping the pattern found the same bug in design-flow,
  where the else-branch printed *"nothing on the port"* — false, and it sent the operator to boot
  a server already running. The two `curl -fsS` sites that are *wait-for-healthy* loops were
  correctly left alone.

- **Three judges reported a shared-layout defect once per page** (#108, item J — *"773 defects
  that were ~18 repeated"*). All four judges now group on the **exact** `(rule, detail)` pair, so
  a detail carrying per-instance counts still does not group: a de-duplicator that merges two
  distinct defects to make a shorter report is worse than none. `--json` keeps every occurrence
  and the summary prints both counts.

- **Route coverage never read the crawl** (#108). A route the crawler loaded and graded counted
  as *never touched*, and the omission was stated nowhere — which made it a defect rather than a
  decision. Fixed as a **third state**, not by widening `covered`: a crawl grades errors but
  asserts nothing, so counting it would be SKIP-is-not-a-PASS wearing a percentage. Non-GET
  routes are excluded, because a crawler navigates with `page.goto` — a GET of `/users/7` is not
  a visit to `DELETE /users/:id`. That false claim was caught by the change's own fixture.

**Versions:** qa-flow 1.23.0 → **1.24.0**, design-flow 1.12.0 → **1.12.1**.
**Gates:** 61/61. **Mutation check:** 368 mutations across 31 guards, all caught.

### 2026-08-02 (release v1.58.0)

> ### Doctrine that was measured against reality for the first time
>
> Three of these were found by *running* something rather than reading it: a browser against the
> licensed templates, Playwright against our own overlay probe, and a grep against a config key
> nobody had defined. Each contradicted doctrine we had already shipped.

- **The page-pacing rules contradicted the corpus** (#92, now complete). Rule 1 required tone to
  alternate at *every* boundary and rule 3 forbade a border — so at our own token values the pair
  specified a boundary carried by a **1.053:1** step with nothing else marking it. Of six marketing
  templates studied, one alternates at **none** of its four boundaries; the smallest step where tone
  genuinely carries a boundary is **24× ours**. Rule 1 is now continuity, rule 2 owns the boundary,
  rule 3 is conditional, Proof moves to band 2 (resolving a file that contradicted its own prose),
  6–8 bands is scoped to a genre, and the inset panel is named as a second band form.
- **The overlay probe never ran on the commonest modal there is** (#458). Overlays were counted by
  *presence*, so a `role="dialog"` revealed by toggling `hidden` — every component library — never
  registered as opened, and the shipped Escape and focus-restore rules silently skipped it.
  Presence measured `3→3→3` while visibility went `0→1→0`.
- **Shipped doctrine mandated findings against spec-correct behaviour.** `a11y-auditor.md` told
  auditors to assert Tab-containment on menus and comboboxes; **APG specifies the opposite** — Tab
  exits and closes a menu. Confirmed against the live pattern, corrected with citations.
- **A safety rule pointed at config that did not exist** (#461). *"Never submit a form matching the
  configured destructive pattern"* — and nothing configured one. Third instance of a reference with
  no referent, and the first guarding forms that delete data or take payment.
- **#95's audit half had three of four criteria failing**, including on the example the issue itself
  names, plus five controllers beyond the "only new controller" claim. `aria-selected` on a `button`
  — invalid in ARIA 1.2 — was corrected by reuse rather than invention.
- **The catalog and cart slice** (#91), including a card that cannot hold the button it wants: the
  `<a>` content model forbids an interactive descendant, which is *why* quick-view exists.
- Gate sweep **61**. A gate for the config-reference class was written and **withdrawn** — six
  findings, all false positives, and a rule that cries wolf gets switched off.

### 2026-08-02 (release v1.57.2)

- **CI actions were pinned to majors running the deprecated Node 20.** `actions/checkout@v4` and
  `actions/setup-python@v5` target node20, which GitHub force-runs on node24 and will eventually
  stop supporting; both workflows printed the deprecation on every run. Bumped to **v7**, which is
  what `releases/latest` reports — the deprecation notice itself implies v5/v6 and is behind, so the
  versions were checked against the API rather than taken from the warning.
- Applied to **both** `gates.yml` and `release.yml`. Those are deliberate mirrors, and bumping only
  the PR path would have left the **publish** path on a runtime the rest had moved off — the kind of
  gap nobody notices until a release fails. Verified on the PR's own run: **0 deprecation warnings**.

### 2026-08-02 (release v1.57.1)

- **A killed crawl produced nothing at all** (#451 — the collector half of the closed #111, filed as
  its own issue so the work has a findable trail). The collector accumulated every route in memory
  and wrote once at the end: a run killed at route 40 of 50 left **no file**, and was silent
  throughout. Both were #111's original complaints; its agent-facing half shipped and this half
  did not.
- **Measured, not argued** — same server, same routes, same kill point: `dev`'s collector produced
  **0 files**; this one leaves **4 routes recorded** plus an abort record naming the 2 unreached.
- The append file is a **sidecar**: `crawl.json`, `interactions.json` and `links.json` keep their
  exact contracts, because three judges read them and buying crash-safety by changing those would
  trade one defect for a wider one. JSONL rather than JSON because a partial JSONL still parses
  line-by-line. Progress on **stderr**, so the stdout summary a caller may parse stays parseable.
- **SIGINT/SIGTERM only.** An uncaught exception is deliberately unhandled: it means the collector
  itself is broken, and a tidy abort summary would disguise that as an orderly stop.
- **Resume is not done and not implied.** The append file makes it possible; its semantics are a
  separate decision.

### 2026-08-02 (release v1.57.0)

> ### Three settings that looked honoured and were not
>
> All three shipped, all three read as working, and none of them did anything. A gate that is merely
> absent is visible; one that appears wired is not.

- **`links.check_external` was a switch nothing was wired to.** The scaffolded config shipped it and
  the prose said *"enable it for a deliberate link audit"* — but `link_audit.py` counts external
  targets and has **no code path that fetches one**. Removed; the docs now say what the tool does. A
  new `unhonoured-config-toggle` rule refuses a scaffolded boolean no script reads, scoped to
  booleans because string keys are often agent-applied and widening it would flag a real consumer.
- **`crawl_collector.js` ignored unknown flags and ran a default crawl** (#447). `--help` crawled
  and wrote two files into the caller's tree; `--visualise` produced a clean-looking run with visual
  capture silently **off**, so the output read as evidence for something never measured. Flags are
  enumerated now, unknown ones exit 2 naming the offender.
- **Boot-error triage was a prose table an agent was told to eyeball.** `classify_boot_failure.py`
  applies it: five categories matching signatures a runtime prints verbatim, **fixed order so the
  specific cause beats incidental noise**, and `application-error` as an honest fallback rather than
  a shrug. It prints the next action; it does not decide it.
- **Playwright is now installable and the collector was run for the first time.** That settled a
  claim previously only relayed: `await import()` of Playwright really does yield
  `chromium: undefined` — it lives on `.default` — so the v1.52.1 fix was broken and shipped that
  way for two releases. The current `projectRequire()` form is verified working, and the collector
  plus `crawl_report.py` and `link_audit.py` are now proven end-to-end against a live browser.
- Gate sweep **60 → 61**; self-consistency selftest 105 → **117**.

### 2026-08-02 (release v1.56.2)

- **The coverage matrix was under-reporting what we ship** (Refs #91). Four catalogue entries and two
  archetypes shipped in v1.55.0 with no `ENTRIES` rows, so the matrix described a smaller system than
  the repo contains. Deliberate rather than careless: regenerating needs the licensed corpora, and
  committing rows without regenerating leaves a stale matrix that fails the drift gate **on someone
  else's machine**. The exact edit was written onto the issue and left for a corpora-attached
  follow-up; this is it. **118 rows from 93 TW + 63 FB**, both artifacts regenerated.
- **`Number input` was flipped, not duplicated** — Flowbite's `Number Input` was already claimed, and
  the totality guard allows exactly one claimant, so a second row would have failed rather than
  added. Its `BUILD` fallback went with it: a `documented` row carrying one is what
  `verify_shipped_evidence` refuses.
- **No row invented for "Invoice / statement"** — it is the existing `Detail anatomy`. A row there
  would have inflated the matrix, which is the direction nobody checks.
- All six evidence strings were verified against the shipped headings before being trusted, each
  found exactly once — the trap that broke two promotions earlier today.

### 2026-08-02 (release v1.56.1)

- **#115's sixth criterion was pointed at, never asserted** (#424). *"Modal-CRUD variant asserts 422
  re-render inside the modal"* shipped as a pointer at `functional-tester`, which contains **zero**
  occurrences of `422`, `modal`, `dialog`, `CRUD` or `re-render`. Asserted nowhere for three
  releases; the doctrine it meant lives in another component (`crud-modal-pattern.md:146`).
- **Why it was never implemented is the more useful half: the forms profile could not express a
  valid modal row at all.** An `Exercised` row had to be 2xx/3xx while the doctrine *requires* 422 —
  Turbo replaces a frame only on that status. Anyone recording the row #115 asks for would have been
  told it was `Blocked`. The criterion was not forgotten; it was unimplementable in the schema meant
  to carry it.
- A `modal` row that exercised an invalid submit must now carry HTTP 422 **and** must not have
  navigated — a differing Requested/Final URL means the modal was destroyed and the user's input
  with it, which renders as a **pass** to any check that only asks whether an error appeared.
- The carve-out is narrow on purpose — **422 only, modal only**, and a 422 row that does not declare
  `Surface: modal` gets no exemption, pinned by a fixture because widening is how carve-outs fail.
- Selftest 247 → **253**, mutations 24 → **26**. Two existing guards caught drift during the work:
  the agent-header cross-check refused the new column until the agent doc documented it, and the
  stale-anchor rule caught a mutation the edit had invalidated.

### 2026-08-02 (release v1.56.0)

> ### A release about gates that were green over things they could not see
>
> Three checkers here reported clean while structurally unable to read what they guard. None was
> red. That is the harder failure to notice, and each was found by a control rather than by review.

- **Five of twenty-eight mutation guards were INERT** — `validate_evidence`, `maintainer_doctor`,
  `project_gates`, `crawl_report`, `check_handoff`. Each one's **unmutated** selftest already failed
  in the staged tempdir, so every mutation beneath it read as "caught" by that breakage rather than
  by the fixture it names. `validate_evidence` alone had 24 proving nothing. That is the harness
  which validates every other gate in this repo, and it was green. Now **318 mutations, 0 inert.**
- **The cause was hand-listed files rotting.** `check_handoff` staged ten rails-flow agents by name;
  v1.52.0 added an eleventh, so the mutant lacked an agent its own tier table names. Fixed by
  declaring directories. `maintainer_doctor` took **three rounds** — `scripts`, then `plugins`, then
  `evals` — because an inert guard hides every later missing path behind the first.
- **The shared-shapes gate was green over two tables it could not read.** A merge unioned a
  3-column form with a 4-column one; `ROW` needs two adjacent digit columns, so every stale row was
  skipped **silently**. Measured: `dev`'s own gate, in a `dev` checkout, printed *"matches the
  repo"* over a block holding two tables. A multi-table block is now a hard error.
- **Five `checks.json` gates waited on paths nothing writes** (#423) — permanently "not applicable",
  never run in a user's repo. That included `human-guide`, so `check_guide.py` — the whole of #126 —
  had never executed for anyone. `check_manifest_paths.py` now reconciles every declared path
  against what each plugin's own scripts write.
- **The coverage matrix said Command palette had no catalogue entry, and one had shipped** (#95) —
  agents were routed past written doctrine to a one-line summary.
- **#398 answered "no."** The selftest harness stays one copy per install root: no module reaches
  more than 5 of 12 copies, the saving is under 1% of the file set against 298 call sites, and what
  makes the copies acceptable is a shared **control** — the mutation checker — not a shared module.
- New page-pacing doctrine (#92), the list family and plans/billing (#95, #91), money typography
  settled at its source, and the generated-layout `test/` contradiction fixed (#395).
- Gate sweep **56 → 60**.

### 2026-08-01 (release v1.55.0)

> ### The largest release here, and most of it exists because things were checked rather than assumed
>
> Twenty issues close. Two doctrine audits read ~120 externally-verifiable claims against primary
> sources and found **ten wrong and seven missing** — including a **critical CVE** our own doctrine
> was steering users into. Several features refuted the issue that asked for them. And four gates
> failed only once everything was merged together, which is the argument for merging.

- **SECURITY — our doctrine pinned users to a vulnerable Rails** (#388). `SKILL.md` named 8.1.3 as
  current stable; **8.1.3.1** fixes **CVE-2026-66066 / GHSA-xr9x-r78c-5hrm**, CVSS **9.5**, an
  arbitrary file read + RCE in Active Storage. Two things the report omitted are now in the doctrine
  because "upgrade" alone is not safe advice: the fix needs **libvips ≥ 8.13** at runtime or it is a
  no-op, and a possibly-exploited app must **rotate `secret_key_base`**. A stale version claim in
  `README.md` was found by grepping every site rather than the two the report named.
- **`load_defaults 8.1` had seven changes, not the two reported** (#392, #393). Five undocumented
  and **two we had wrong**: we called a raise a deprecation, and read `yjit` as switched on in 8.1
  when 8.1 switches it **off** in dev/test. `escape_json_responses = false` is now in the security
  checklist, not just the upgrade list. The upgrade watch list is the one place a reader is entitled
  to assume completeness.
- **Ten hotwire and rails-8 doctrine claims corrected** (#380, #383, #384, #385, #386, #389, #390,
  #394) — including `data-turbo-disable-submitter`, which **does not exist in Turbo**; Stimulus
  function-key filters, which **throw** rather than no-op; a Kamal "skip the registry" instruction
  that made the first `kamal setup` fail; and a pagy snippet that raised `NameError` on paste.
  Version boundaries were **bisected across published tags**, not inferred.
- **NEW — typed findings records** (#138 shipped previously; #134 blast radius, #108 link audit,
  #105 focus restore, #112 visual baselines, #360 quality pass, #160 variant mode, #158 skill
  routing, #130 intake interview, #128 circuit breakers, #359 claim-verifier wiring).
- **`quality-pass` is a new shipped skill** — reuse, simplification, efficiency, altitude. Advisory
  by design: a gate on taste gets switched off, and then nothing checks quality at all.
- **Four gates failed only after everything merged**, each individually green. `skill routing`
  returned **CANNOT CHECK** rather than skipping a whole unpinned new skill; `shared shapes` caught
  four counts in our own worked example going stale; `coverage matrix` caught an evidence string
  demanding an exact heading that shipped with a descriptive suffix; and a selftest asserting
  `len(SHIPPED_SKILLS) == 4` turned out to be a **second source of truth** for the set above it.
- Also lands the last three doctrine groups: Stimulus key filters, the `stimulus:manifest:update`
  contradiction and the default-event map (#381, #382, #387), plus `bin/ci` running **zero**
  specs under the `--skip-test` this skill mandates (#391) and a SimpleCov version boundary
  (#396). Verification **corrected two of our own reports**: the Stimulus key-filter error
  escapes as an uncaught page error rather than through Stimulus' handler, and a missing
  default event is dropped **silently** rather than throwing — written as reported we would
  have promised a visible error where the real behaviour is silence.
- **Palette + type-pairing candidates for brand packs** (#129), and the measuring found two live
  contrast defects: the **fidara pack itself** still carried both #304 defects — `--primary` at
  4.42:1 and white-on-electric at **2.73:1** on every dark-mode primary button — because #304
  was fixed in the doctrine file and nowhere else, and the gate read one hardcoded path, so it
  reported clean over the file that was already right while the pack users install kept the
  defect. `_template`, the file every client pack is copied from, failed three pairs. Both
  fixed, and the gate's **input** widened so an empty glob is now a hard error.
- **A citation refuted our own code**: the sRGB linearisation breakpoint is `0.04045`, and we
  carried WCAG 2.0's `0.03928`. Corrected, and the difference proved immaterial across all 256
  8-bit channels rather than asserted so.
- Gate sweep **44 → 55**. Self-consistency selftest 98 → 105 assertions.

### 1.55.0 — 2026-08-01

- **`claim-verifier` is now actually wired into the flows that claim to use it** (#359). It shipped
  in v1.52.0 and was referenced from **nowhere** — an agent built because descriptions go unchecked,
  itself described as wired and never called. `release-manager` runs `extract_claims.py` over the
  promotion body and hands the list to `claim-verifier` **before** opening the PR, because that body
  becomes the published release notes and a false sentence there outlives every other kind.
  `/maintainer-work` does the same, more cheaply, at the `dev` PR.
- **New `unwired-claim-verifier` rule** makes criterion 5 checkable rather than prose. It is
  deliberately narrow: it verifies the wiring exists, not that anyone reads the verdict — whether a
  maintainer obeys it is not mechanically knowable, and pretending otherwise would be the same
  defect one level up. It also fails a flow that names the agent **without** `extract_claims.py`,
  since gathering the claim list by judgement is the half #359 proved cannot be relied on.
- **Criterion 3 was declined, not skipped, and the reversal is already recorded.** It asked for
  `claim-verifier` to be pinned to a model different from the session. `reference/model-tiers.md`
  argues the opposite for a *shipped* agent: a pin spends a stranger's money on our authority, and a
  value outside their `availableModels` is skipped anyway. A pin cannot buy a second opinion, only a
  cost. So it stays `inherit`, the caller obtains independence via a per-invocation model or
  `CLAUDE_CODE_SUBAGENT_MODEL`, and the agent must state which model it ran as.
- **A fixture here was vacuous and a mutation caught it.** The wiring rule has two branches; asserting
  only that *something* fired could not tell them apart, so disabling the first branch left the
  `elif` to fire and the mutant survived. Fixtures now assert the message, not the boolean.
- Self-consistency selftest 98 → **103** assertions; mutations 27 → **28**.

### 2026-08-01 (release v1.54.0)

> ### Three things that were judgement are now arithmetic
>
> `/rails-flow:review` fanned out seven passes and merged seven prose blobs by judgement. Dedupe
> depended on whether a reader thought two findings looked alike; "no pass may drop a finding" was a
> contract nothing checked; and *"A is caused by B"* was recorded nowhere, so fix order was a guess.

- **NEW — typed findings records** (#138, rails-flow 1.17.0 · qa-flow 1.20.1). Each pass appends
  JSONL; synthesis reads the data. **Dedupe** groups by `signature` and reports
  `distinct (N instances)`. **Completeness** asserts every input id appears in the output as
  reported or `duplicate_of` — reorder yes, collapse yes, **drop no** (#77). **Fix order** is a
  topological sort on `caused_by`/`blocks` (#118 for the counting half).
- **An edge outranks severity, and that is the point of the graph.** A P1 symptom waits for its P3
  cause; severity only breaks ties the graph leaves free. `/fix` is told explicitly not to "correct"
  that back — the inversion looks like a mistake and is the whole value. Pinned by a fixture,
  because a severity sort that quietly overrode edges looks right in every case where they agree.
- **`/issues` files one issue per distinct signature, not per record.** A real crawl produced **773**
  occurrences of one a11y defect whose distinct count was about **18**. A developer told "773
  defects" stops reading; told "18, one on every page", they fix the navbar. Same arithmetic,
  applied where it decides how many issues exist.
- **Parity between the two plugins is gated, not claimed.** qa-flow is independent and does not
  import rails-flow, so the schema *is* the contract — and `findings-schema-drift` compares the
  field tuples in `findings.py` against the fields documented in `qa-reporter.md`. It also fails
  when its own anchor is renamed, rather than comparing nothing and passing.
- **Plain JSONL in git** — no graph database, no orchestration runtime, per `harness-doctrine.md`
  §9. A record you can `git diff` and `grep` without a running service.
- **What the script deliberately will not do:** derive `signature`. It is a stable identity for the
  *defect*, not the occurrence, and `file:line` is wrong in both directions — the same defect moves
  when a line is inserted, two different defects share a line. The agent judges, the script counts.
- Findings selftest **29 checks**; self-consistency 93 → **98**; mutations 25 → **27**; sweep
  43 → **44**. One mutation was rewritten after the first version broke syntax and every mutation
  read as "caught" by a traceback rather than by a fixture — a crash is not a verdict.

### 1.54.0 — 2026-08-01

- **NEW `findings.py` — typed findings records, so multi-agent output is queryable and dedupe is
  mechanical** (#138). Plain JSONL in git; no graph database, no orchestration runtime (criterion 8,
  and `harness-doctrine.md` §9). `/rails-flow:review`'s seven passes append records before writing
  prose, and synthesis reads the data instead of merging seven text blobs by judgement.
- **Three things that were judgement are now checked.** *Dedupe* groups by `signature` and reports
  `distinct (N instances)` — the #118 arithmetic, where 773 real occurrences were ~18 defects.
  *Completeness* asserts every input id appears in the output as reported or `duplicate_of`, so
  #77's "no pass may drop a finding" is verified rather than contracted — synthesis may reorder and
  collapse, never drop. *Fix order* is a topological sort on `caused_by`/`blocks`.
- **An edge outranks severity, and that is the whole point of the graph.** A P1 symptom waits for
  its P3 cause, because fixing the symptom first is wasted work; severity is the tiebreak only
  within what the graph leaves free. Pinned by a fixture, since a severity sort that quietly
  overrode edges would look correct in every example where the two happen to agree.
- **A cycle is reported, not raised.** Order with a cycle in it still beats no order, so the members
  fall back to severity and the caller is told — a mutual `caused_by` is usually a modelling error.
- **`signature` stays the agent's judgement and the script trusts it**, stated as a limit rather
  than hidden: deriving it from file+line is wrong in both directions, since the same defect moves
  when a line is inserted and two different defects share a line.
- **qa-flow's reporter emits the same record** (criterion 7), and the parity is **gated** rather
  than claimed. The two live in different plugins deliberately — qa-flow is independent and does not
  import rails-flow — so the schema is the contract, and `findings-schema-drift` compares the field
  tuples in `findings.py` against the fields documented in `qa-reporter.md`. Two documents agreeing
  today is not the same as two documents that must agree.
- The drift rule **fails when its own anchor goes missing**: if the `REQUIRED`/`OPTIONAL` tuples are
  renamed it reports that, rather than comparing nothing and passing. That is a `gate-that-cannot-fail`
  in waiting, and it has a fixture plus a mutation of its own.
- **`/rails-flow:fix` and `/rails-flow:issues` now consume the JSONL directly**, completing the
  second half of criterion 6. `/fix` takes its order from `findings.py order` and is told **not** to
  "correct" a P1 symptom back ahead of its P3 cause — the graph is the only place that relationship
  is recorded. `/issues` files **one issue per distinct `signature`**, not per record, and carries
  the signature into the issue body so the next review recognises the defect instead of re-filing
  it. That is the 773-vs-18 arithmetic applied at the point where it decides how many issues exist.
- Findings selftest **29 checks**; self-consistency 93 → **98** assertions; mutations 25 → **27**;
  gate sweep 43 → **44**. One mutation had to be rewritten: the first version broke syntax, so the
  mutant died at import and every mutation read as "caught" by a traceback rather than by a fixture.

### 2026-08-01 (release v1.53.0)

> ### Two checks that exist because inference was tried first and did not work
>
> Both features here started as "grep for the bad pattern", and in both cases building the check
> proved the grep could not be trusted. The detector's twelve tells collapsed to seven once each was
> grounded in doctrine. The topology gate's keyword approach would have **missed the one command
> that gets fan-out right** and passed two that did not.

- **NEW — offline detector for LLM design tells** (#157, design-flow 1.11.0). Seven named rules,
  each citing the doctrine line it enforces. Stdlib only, no browser, no API key. Runs on every edit
  as a PostToolUse hook and inside `/design-flow:audit`. A disable must carry a reason; a bare one is
  itself a finding.
- **The rule set is seven, not the twelve requested, and that is the finding.** Two of the tells are
  **prescribed by our own doctrine** — `components.md:185` mandates `backdrop-blur-sm` for the modal
  backdrop, `:658` mandates `animate-pulse` for skeletons — so rules for them would fire on the
  reference implementations they enforce. Three more need rendered contrast or page structure a
  static scan cannot see.
- **Two of the seven find outright bugs, not drift.** `bg-gradient-to-*` was removed in Tailwind v4
  and `duration-fast` never existed, so both emit **no CSS at all**: the markup looks right, renders
  wrong, and nothing raises.
- **NEW — agent topology is declared and gated** (#137, rails-flow 1.16.1 · qa-flow 1.20.0).
  `harness-doctrine.md` §8a; every command dispatching 2+ of its plugin's agents declares its
  topology, a fan-out declares `merge:`, a loop declares `exit:`. Enforced by `undeclared-topology`.
- **FIX — `/qa-flow:verify` consolidated a five-way fan-out with only a verdict rule.** Nothing said
  what happens when two layers report the same defect, or when one PASSes a surface another fails.
  Now states precedence (any S1/S2 outranks every PASS; a skipped layer is not a PASS) and dedupe
  (same route + assertion is ONE defect). Filing one issue per layer makes the fix queue lie.
- **Loop breakers remain deliberately absent**, recorded where a reader will look. They are §8's
  known gap owned by #128; requiring them before they exist would be the claims-vs-enforcement
  defect the document is named for.
- Gate sweep **41 → 43**. Self-consistency selftest 77 → **93** assertions; mutations 21 → **25**.
  Two of this release's bugs were caught by our own guards rather than by review: a coverage counter
  printing `0 commands examined` under a "no findings" verdict, and an IDE unused-import hint
  revealing a shared constant that had been imported and then hand-copied.

### 1.53.0 — 2026-08-01

- **Agent topology is now declared by each command, and gated** (#137). `docs/harness-doctrine.md`
  gains **§8a**; every command dispatching two or more of its own plugin's agents carries
  `<!-- topology: … -->`, a `parallel` one carries a `merge:` rule, a `loop` carries `exit:`.
  Enforced by the new `undeclared-topology` rule in `lint_self_consistency.py`.
- **Building the check first is what proved the labels must be explicit rather than inferred**, and
  all three measurements pushed the same way. `/rails-flow:review` is the flagship parallel fan-out
  — the README says so — yet the word "parallel" appears **nowhere** in `review.md`, so a keyword
  gate would have missed the one command that gets this right. Counting agents over-fires
  (`/rails-flow:feature` names eight, sequentially — a pipeline reconciles nothing). Searching for
  merge vocabulary under-fires (`/qa-flow:certify` states a sound precedence rule in words no
  keyword list contains).
- **FIX — `/qa-flow:verify` Phase 4 consolidated a five-way fan-out with only a verdict rule.**
  Nothing said what happens when two layers report the same defect, or when one PASSes a surface
  another fails. Now states both: precedence (any S1/S2 outranks every PASS; a skipped layer is not
  a PASS) and dedupe (same route + failing assertion is ONE defect, reported with every layer that
  saw it). Filing one issue per layer inflates the count and makes the fix queue lie.
- **Loop breakers are deliberately still absent**, and §8a says so where a reader will look. Attempt
  caps and no-progress detection are §8's recorded gap, owned by #128; requiring them before they
  exist would be the claims-vs-enforcement defect this document is named for. An `exit:` condition
  is a different thing — a command can state one today.
- **The rule's first version examined ZERO commands and reported "no findings."** An off-by-one
  resolved every plugin name to `"plugins"`, so it found no agents directory and skipped everything
  — a clean verdict over an empty scan, visible only because the coverage counter printed the zero.
  Kept in the docstring, and the reason those counters exist.
- Self-consistency selftest **85 → 93** assertions; mutations **23 → 25**, both new ones caught by
  their own fixture. `/design-flow:audit` and the design-flow README also document the new detector
  from #157.

### 2026-08-01 (release v1.52.1)

> ### Everything here came from running the toolchain against a real Rails app
>
> Three defects, none of which any of the 41 gates found — because all three are about **behaviour
> at run time**, and the gates check content. Two of them made a shipped tool report confidently
> wrong things; the third raised on code we tell users to copy. The first real app run was worth
> more than the fixture suite it can't replace.

- **`[dead-control]` false-positived on every validated form** (#357, qa-flow). A submit inside a
  form with an unfilled `required` field fires no request — the browser blocked it, and doing
  nothing is *correct*. The collector now records `constraintBlocked` via `form.checkValidity()`
  and the judge excludes it, as it already did for `disabled`. The near-miss is pinned: a submit in
  a **valid** form is still judged, so the exclusion cannot swallow the finding it was carved from.
- **The crawl could not resolve a project's own Playwright** (#356, qa-flow). ESM resolves from the
  *script's* location, not the working directory, and `NODE_PATH` does not apply to ESM — so the
  collector never saw a dependency installed in the app it was crawling. Now resolved through
  `createRequire(process.cwd())`; when it still fails it names the directory and the fix, and exits
  2 rather than reporting an empty crawl as a clean one.
- **`Ui::Logo` raised `NoMethodError` on almost every `size:`** (#352, rails-stack). The reference
  snippet contradicted itself on one line: a `|| size.to_i` fallback and a `clamp(20, 200)` that
  only mean something if a px number can arrive, behind a `size.to_sym` that raises when one does.
  Measuring it found a second raise the report missed — `Symbol#to_i` does not exist either, so any
  key outside `SIZE` raised too, and the fallback only ever worked for a numeric string.
- **New `unreachable-coercion-fallback` gate** for that class, which `ruby -c` structurally cannot
  catch: it is valid syntax that raises at run time. Selftest 77 → 85 assertions, mutations 21 → 23.
- **Two claims in #352 were false** — quoted doctrine that appears nowhere in the skill, and a
  mirrored call site that does not exist. The defect was real on internal evidence, not the
  authority the report claimed. Third time this pattern has been recorded (#142, #229, now #352):
  **an issue body is a hypothesis.**

### 2026-08-01 (release v1.52.0)

> ### Reviewing the diff would not have caught any of them
>
> Three defects shipped from this repository in one day, each found by a human asking whether a claim
> was true and none by the forty gates. Every diff was internally consistent — **the defect was in the
> sentence describing it**. `claim-verifier` exists for exactly that, borrowed from `fable-advisor`.

- **NEW `claim-verifier`** — verifies what a change says about itself. Extracts enforcement,
  exhaustiveness, causation and measurement claims, then checks each by **running or grepping**;
  reading the code is explicitly not checking, because the claims are about behaviour.
  **UNVERIFIABLE is a finding** — a claim nobody can check should not be in a description.
- **The issue asked for a third model tier, and building it proved that wrong.** Pinning a *shipped*
  agent to an expensive alias spends a stranger's money on our authority, and a value outside their
  `availableModels` is skipped anyway. **A pin cannot buy a second opinion; it can only impose a
  cost.** So the agent is `inherit` and must **state which model it ran as**, saying plainly when that
  matches the session. The vocabulary needed no third value — the mechanism was never the frontmatter.
- **NEW `extract_claims.py`** — the half that can be proven, since an agent is a prompt and has no
  fixtures. The script extracts, the agent judges. Its **silence** half is what makes it usable: it
  drops hedged and unfalsifiable sentences, because a verifier handed *"this is cleaner"* has nothing
  to run. A limitation is recorded rather than hidden — it cannot tell a claim being *made* from one
  being *quoted*, and **when in doubt it extracts**, because dropping a real claim silently is the
  failure it exists to stop.
- **Stock LLM phrasing is named in the copy doctrine, as an advisory count**, borrowed from
  `humanize`. Advisory unlike every other row in that table: those fail on a fact, this fails on a
  word, and *"Unlock your first report"* is a real CTA.

### 2026-08-01 (release v1.51.1)

> ### The CI job we scaffold for users could never run
>
> `setup-flow` proposed a `doctrine` job stepping on `$CLAUDE_PLUGIN_ROOT` — a variable that exists
> only inside Claude Code's plugin context and **not in GitHub Actions**. Every run would have failed
> with `can't open file '/scripts/project_gates.py'`.
>
> Nothing we own could have caught it: our own workflows never reference that variable, so **the
> workflow we test and the workflow we scaffold are different files**. It surfaced when a maintainer
> ran the command by hand — and the correct knowledge was already twelve lines below in the same
> file, where the graph job says *"the script ships inside the plugin, which CI does not install."*

- Fixed by checking the toolchain out **beside** the repo at a **pinned tag** — one checkout serves
  all four plugins, since the runner discovers each `checks.json` itself. Pinning is mandatory: an
  unpinned `main` means our next release silently changes what a user's CI enforces.
- **NEW `plugin-root-in-ci` rule**, scoped to ```yaml fences. Prose naming the variable is correct
  and common, so matching anywhere would fire on a correct sentence in that very file. Four
  fixtures, two of them silence cases.

### 2026-08-01 (release v1.51.0)

> ### Visual regression, and the state that is neither pass nor fail
>
> A screen with **no baseline** is `new`. As a pass, a brand-new screen is "visually correct" the day
> it is written when nothing has been reviewed. As a failure, every new screen breaks the build until
> someone raises the tolerance to zero effect. It blocks nothing and is counted every run.

- **Nothing can promote a baseline.** The judging path has no write call at all, asserted against the
  module's own source — an agent that can overwrite a baseline can launder a regression into the new
  truth in one run. Candidates land in `_candidates/`; promoting one is a human's act.
- **`--seeded` is the caller's assertion, not the tool's.** The collector freezes motion and the
  clock itself, but it cannot seed the app's fixtures — so it defaults to **false** and the judge
  **refuses the run**, which is right for a caller who has not said the data is fixed. A flaky visual
  check is worse than none: it trains people to ignore the one report that needs eyes.
- Diffs are computed **in the browser**, where a canvas already exists; decoding PNGs in Python would
  put a third-party image library inside a gate.
- **One fixture proved nothing and was caught by mutation** — the longest-prefix tolerance test
  declared the shorter pattern first, so "last match wins" and "longest match wins" agreed.

### 2026-08-01 (release v1.50.0)

> ### Two things that existed but could not be used
>
> The three crawl judges shipped last release with a `--schema` and **no collector** — usable in
> principle, unusable in practice. And `design-flow` has been in the marketplace, named four times
> in the README, with **no install line**: anyone following the install steps got four of five
> plugins and never learned the fifth existed.
>
> Both are the same shape. A thing that exists and cannot be reached is not shipped.

- **The crawl judges now have a collector.** `crawl_collector.js` produces both documents in one
  pass and **measures only** — it cannot be unit-tested without a browser, so it holds no rule; a
  rule there would be a rule with no fixture and no mutation guard.
- **`/qa-flow:crawl`** reads the project's own `app:` block rather than inventing a boot command,
  and takes routes from `qa/routes.json` — crawling a hand-typed list is how a route nobody
  remembered stays untested forever. It performs **no git operations**.
- **Both judges cross-check the shipped collector against their own schema.** They are separate
  files in separate languages, so nothing stopped them drifting — and a collector that quietly
  stops emitting a field makes the rule reading it go **silent rather than fail**. Proven by
  renaming a field and watching the selftest catch it.
- **FIX — `design-flow` had no `/plugin install` line** (#203, second occurrence), and its setup
  command was missing from the ordering. The existing `undocumented-plugin` rule stayed **green**
  exactly as its own docstring predicts: it proves a name appears *somewhere*, not that it appears
  in the list that enumerates what ships.
- **NEW `uninstallable-plugin` rule.** The looser rule was deliberately left loose because locating a
  prose *section* needs judgement — but **an install command is not a section**. `/plugin install
  <name>@` is a fixed pattern, so this is decidable with none. Proven to add coverage rather than
  duplicate: delete the line and the new rule fires while the old one stays silent.

### 2026-08-01 (release v1.49.0)

> ### Three defects nothing else in the toolchain could see
>
> Each of these is invisible to every existing rule **by construction**, which is why they needed
> their own judges rather than another threshold on an existing one:
>
> - a route returning **200** while rendering its 500 template — survives every status check ever
>   written, and is the normal shape behind a `rescue_from`;
> - a page that is **individually conformant in both themes** and unreadable in one — every other
>   rule judges a single rendering, so the defect is the *difference*;
> - a control that is **named, focusable, correctly marked up and inert** — it satisfies every rule
>   that judges appearance, and only using it reveals anything.
>
> `qa-flow` changed; every other component is byte-identical.

- **Route crawl judged** — non-2xx, redirects the crawl did not follow, console errors, failed
  requests, and the 200-but-error case the file exists for. A page *about* errors is not an error
  page, so markers match the title and H1 only and "Error handling guide" stays silent — fixtured.
- **Theme parity judged** — `contrast-regression`, `vanished`, `colour-frozen`. **The XOR is the
  whole rule**: a page equally bad in *both* themes belongs to `rendered_conformance.py`, and
  reporting it here would double-count. It consumes design-flow's snapshot and does not re-run its
  rules — one rule, one owner.
- **Dead controls judged** — the exclusions are the design, because a false positive on a working
  button is what gets a rule switched off. A `disabled` control doing nothing is correct; a link with
  an `href` navigates; an anchor *without* one navigates nowhere and is exactly the dead control
  worth catching.
- **In all three: a thing that was not verified is never counted as clean.** An unreachable route, an
  unexercised control and an unusable input file are each named on every run. An empty crawl
  reporting zero findings would be indistinguishable from a healthy app.
- **Six defects in this release's own fixtures were caught by mutation, not by reading** — including
  two fixtures derived from the very constant they were testing (removing the key deleted the
  assertion that would have named it) and an unguarded index that made a mutant **crash** before any
  labelled assertion could report. A crash is not a verdict.

### 2026-08-01 (release v1.48.0)

> ### The gates existed. Nothing ran them.
>
> This repo builds 36 gates, documents them at length, and treats them as its safety net. Until
> today **every automated check on a pull request here belonged to a third party** — our own workflow
> fired only at release time, on `main`, after merge, and checked one thing. The gates ran when a
> maintainer remembered to type the command.
>
> Then the fix had the same hole: `gates.yml` watched pull requests and `dev`, but **not the publish**
> — so the merge commit that ships a release ran none of them.
>
> Both were found by being asked to justify a claim, not by any check. The gates catch content; they
> do not catch *"the gate is not wired to the thing that matters"*.
>
> The same defect is now fixed **for users**: the eleven checks we ship for their repos had no runner.

- **`gates.yml` runs the sweep on every PR and every push to `dev`**, and `release.yml` declares
  `needs: gates`, so the publish cannot happen on unproven content. A parallel job would have been
  advisory — it can go red after the release is out. The sweep is **called, not copied**; two copies
  drift and the drifted one would be the copy guarding production.
- **`project_gates.py`** (#334) gives a Rails project **one command** for the eleven checks we ship
  it, discovered from a per-plugin `checks.json` so a check registers itself. Four states —
  **pass / FAIL / not-applicable / ERROR** — and *not applicable is printed loudly every run*,
  because a repo with zero QA evidence must not go the same green as one with complete evidence. A
  missing dependency **FAILS** rather than skipping, since in CI a skip reads as a pass.
- **`setup-flow` scaffolds it into the project's own `dev → main` CI** as an approved diff, insisting
  the deploy job declares `needs: doctrine`. Its old rationale — *"local hooks + qa-flow already
  proved it"* — was an assumption, not a guarantee, and is corrected; the Actions-minutes argument
  stands alone.
- **Five catalog entries gained the accessibility contract they never had** (#95), two of which
  contradicted our own *no colour-only state* rule: Pagination's active page and Avatar's status dot
  were colour alone. Both now carry a text equivalent.
- Three defects in this release's own work were caught by **mutating rather than reading**: a
  manifest command that could not run, an assertion for it that was vacuous, and a subparser detector
  that could not be caught at all because its only assertion lived inside the loop it guarded.

### 2026-08-01 (release v1.47.1)

> ### The same commit got it right three times and wrong twice
>
> v1.47.0 wired three references into `/design-flow:component` **as full paths, specifically so the
> doc-pointer lint would validate them** — and added two more to `design-auditor` that were not, so
> the lint could not see them. Those two named `plugins/design-flow/references/`, a directory that
> does not exist. An agent following either found nothing.
>
> A rule only protects what is written in the form it recognises, so a half-applied convention reads
> as covered while leaving a real broken pointer behind. Found by re-reading the shipped tag when
> asked whether the wiring was actually in place — not by any gate.

- **FIX — two broken pointers in `design-auditor`**, both introduced one release ago. Now full paths.
- Grepping the pattern found two more bare pointers, in `a11y-auditor` and `setup-flow`. **Not
  broken** — each names its skill, so a reader resolves them — but invisible to the lint for the
  same reason. Converted. **65 → 70** pointers validated.
- `skill-curator`'s bare `references/` is deliberately untouched: it names a *directory convention*,
  not a file, so there is nothing to resolve. The distinction is the reason this is a fix and not a
  blanket rewrite.

### 2026-08-01 (release v1.47.0)

> ### Doctrine that nothing consulted
>
> Three reference files shipped in earlier releases and all three carried the **same** open
> criterion: the command that should read them, and the auditor that should enforce them, had never
> been told they exist. That is `claims-vs-enforcement` one level up — the file is right, and the
> agent never learns it is there.
>
> Closing it also surfaced #136's one genuinely missing rule: motion had a **stagger** cap but no
> **page** cap, which is the limit that actually gets exceeded, because each section is added by
> someone who only saw their own section.
>
> `fidara-design` and the design-flow plugin changed; `rails-8`, `hotwire` and `code-review` are
> byte-identical.

- **`/design-flow:component` consults the marketing doctrine** (#131, #135, #136). A marketing
  surface now makes `marketing-copy.md`, `visual-assets.md` and `motion.md` mandatory before markup.
  The load-bearing rule is **draft against the contract, never invent positioning** — and if the
  claim is unknown, say so rather than filling the slot, because a confident placeholder is worse
  than an obvious one.
- **`design-auditor` gains the mechanical half** — placeholder copy, decorative visuals missing
  `aria-hidden`, and raw hex in illustration or geometry (with `Ui::Logo` the one documented
  exception). Plus checklist sections for what a grep cannot read for, stating plainly that copy is a
  positioning decision the human owns.
- **A per-page motion cap** (#136) — one entrance pattern per page, at most three animated regions,
  never two at once in the viewport, never on content the reader scrolled to on purpose. Three
  regions at §7's 1.6s ceiling is 4.8s of page assembly if they queue, which is why they may not run
  together rather than merely being capped in number.
- **The three new pointers are full paths**, so the doc-pointer lint validates their targets exist:
  62 → **65** checked. Proven by renaming one and watching the linter catch it. A bare filename
  would have been prose.

### 2026-08-01 (release v1.46.0)

> ### Two contrast failures, and only one of them had been reported
>
> The reported defect was a link colour at **4.42:1**, a near miss under 1.4.3. Measuring the
> *adjacent* pairs found a worse one nobody had: `.dark` overrode `--primary` but not
> `--primary-foreground`, so it inherited white — **2.73:1** on every primary button label in dark
> mode. Solid-background text, not a near miss.
>
> That asymmetry is the release. A person checks the pair they are thinking about; only a script
> enumerates the rest. There is now a script, and two gates.
>
> `fidara-design` changed; `rails-8`, `hotwire` and `code-review` are byte-identical, and no plugin
> changed at all.

- **FIX — two role-token pairs failed WCAG 1.4.3** (#304). Light `--primary` now points at a new
  `--color-fm-cerulean-700` (`#0072C4`) → **4.74:1**, and dark `--primary-foreground` is navy →
  **6.30:1**. The brand hex `#0077CC` is **unchanged**: the Prism mark, `chart-1` and `brand.md` all
  carry it, and **a logo is not text**, so fixing a text defect by editing a brand asset would have
  been the wrong lever.
- **NEW `scripts/check_token_contrast.py`** — measures ten role-token text pairs from the doctrine
  file, modelling the `.dark`-inherits-from-`:root` cascade that caused the unreported defect. A
  renamed token **raises** rather than resolving, so a pair that stops being measured cannot read as
  one that passed. Both regressions proven caught with their exact ratios.
- **Input group is a Text-input variant, not a new component** (#95). The corpus directory was
  already claimed by `Text input`; what was missing was the contract, not the row. Adding a component
  would have been the duplicate mechanism Phase 2's own criteria forbid.
- **The issue dependency graph is backfilled and valid** (#133). 25 issue bodies carry a `part-of`
  fence; **no** sequential `depends-on` between phases, because the numbering implies an order the
  history contradicts — Phase 3 closed while Phase 2 is open. The tool then rejected the issue that
  *specified* it, whose example fence parsed as four real edges.

### 2026-08-01 (release v1.45.0)

> ### A focus ring nobody could see, and a type scale our own examples contradicted
>
> Three doctrine defects that shipped **because they were correct when written**. The focus ring was
> right under Tailwind v3 and broke silently at the v4 migration; the model pins were a reasonable
> default before the resolution order was checked; the type steps drifted inside the very files
> agents copy from.
>
> Two of the three were reported as smaller than they were. Grepping the pattern — the
> `code-review` skill's own rule — turned **6 sites into 11** and **one plugin into four**.
>
> `fidara-design` changed; `rails-8`, `hotwire` and `code-review` are byte-identical.

- **FIX (P1) — the focus ring was invisible in forced-colors mode** (#305). Nine shipped recipes read
  `focus-visible:outline-none focus-visible:ring-2`. Under **Tailwind v4** that is
  `outline-style: none` plus a ring that is a **box-shadow**, and *"`box-shadow` and `text-shadow`
  compute to `none`"* in forced colors ([CSS Color Adjust 1](https://www.w3.org/TR/css-color-adjust-1/))
  — while `outline-color` is merely force-adjusted. **The outline is the half that survives, and we
  had switched it off.** WCAG 2.4.7.
  - The cause is a **rename that kept the old spelling and inverted its meaning**: v3's `outline-none`
    *"set an invisible outline that would still show up in forced colors mode for accessibility
    reasons"*; v4 renamed that to `outline-hidden` and gave the old name to one that really removes
    the outline ([upgrade guide](https://tailwindcss.com/docs/upgrade-guide)). Our strings were
    correct under v3 and rode through the migration untouched, so nothing looked wrong in any diff.
  - **Enforced, not just documented** — a new `v4-outline-none` lint rule, because a prose rule about
    a string is exactly what regressed. Its two *silent* fixtures are the ones that matter: doctrine
    prose naming the bad utility must not fire, and `outline-hidden` must not trip it.
- **FIX — chrome used the content type step in eleven places, not the six reported** (#306).
  `foundations-tokens.md` calls `text-step-0`-on-chrome *"the most common calibration error"*, and the
  calibration is **measured** — 14px chrome beats 16px body ~2.7:1 in both reference corpora. It had
  drifted inside the reference implementations, so the error was **propagating**. Grepping found five
  more than reported, including the button `BASE` in two files and a `<table>` in two. One file
  contradicted itself two lines apart. Where `text-step-0` stays correct is now recorded, because the
  failure mode of this rule is over-correction.
- **Every plugin agent's model pin is a decision with a named proof** (#299). A `model:` pin is a
  **cap** — frontmatter resolves above the session model — so fifteen agents were downgrading anyone
  on a better model. Across all 25: **19 `inherit`, 6 `haiku`, zero `sonnet`, zero expensive aliases**.
  qa-flow keeps three cheap pins because its outputs are artefacts a script can **reject**;
  design-flow keeps none despite owning three linters, because those grade the *artefact*, not the
  agent. Four reconciliation gates added, both failure modes proven on purpose.
- **The coverage page is reproducible** (#89). Its drift gate broke twice after shipping, both times
  because something that is not the data had leaked into the rendered bytes — git state, then the
  optional licensed corpora. The rule that came out of it: **a committed generated artifact may be a
  function of tracked content and nothing else.** Exempting the corpora case was the *wrong* fix and
  was reverted: it only stopped the check failing on the machine that lacked them, never that machine
  committing a stripped page.

### 2026-07-31 (release v1.44.0)

> ### `needs doctrine` reaches zero, and three gates learned that their own output was not reproducible
>
> Every one of the **113** rows in the fidara coverage matrix now carries doctrine — the last four
> (video player, reviews + rating, stepper/wizard, inline link) landed here, closing a column that
> stood at 27 a fortnight ago. Plus **`/rails-flow:handoff`** with a decided model-tier policy,
> **client-side performance capture** in qa-flow, a **rendered-page conformance linter** in
> design-flow, and marketing-copy + visual-asset doctrine for fidara.
>
> The release's most useful material is again what verification **refused**: five reported claims were
> wrong in their *direction*, not their detail — a `model:` pin turned out to be a downgrade rather
> than an upgrade, star ratings turned out to engage 1.1.1 rather than 1.4.1, and autoplay turned out
> to be 2.2.2 at Level A rather than a reduced-motion question.
>
> `fidara-design` changed; `rails-8`, `hotwire` and `code-review` are byte-identical. `pipeline` is
> untouched and stays at 1.1.5.

- **The coverage matrix is browsable, committed, and gated** — `docs/coverage.html`, generated from
  `build_coverage.py` by import rather than by parsing, cross-checked against `coverage.md`'s own
  Totals table on every build. It was first written to a **gitignored** path, so the deliverable
  existed only on the machine that built it.
  - Its drift gate then failed three times in a day, each time teaching the same lesson: **a committed
    generated artifact may be a function of tracked content and nothing else.** It embedded its own
    SHA and branch (so committing it changed the bytes it would next be built with — a file inside a
    commit cannot name its own commit); then a dirty-tree caveat (so regenerating `coverage.md`, which
    *necessarily* dirties the tree, wrote a `dirty` page to the committed path and broke the gate
    permanently); then the upstream corpus totals by walking the **optional licensed kits** (so a
    machine without them committed `tw: null` and broke the gate for everyone who had them).
  - The third one is the instructive one, because the first fix was **wrong**: exempting the gate on
    corpora-less machines only stopped the *check* failing there and could not stop that machine
    *committing* a stripped page. **Fix the input, don't widen the carve-out.** The counts now come
    from the committed Totals table and the exemption is reverted.
  - `--check` also compared the file **on disk**, so a page built and never `git add`ed passed the gate
    whose own message says *"is not committed"*. It reads the blob at `HEAD` now.
- **A unit of work has a work order, and the model tiers are decided rather than accidental**
  (rails-flow 1.14.0). `/rails-flow:handoff` writes the one file an executor can run from with no
  conversation history, enforced by `check_handoff.py`. The reported model defect was **real with its
  direction inverted**: frontmatter sits *above* the session model in the resolution order, so seven
  agents pinned `sonnet` were **downgrading** every user who deliberately started an Opus session.
  Two tiers now, not three — judgement inherits, mechanical stays on `haiku`.
- **Client-side performance capture during the crawl** (qa-flow 1.14.0) — one evidence row per route.
  The engine rule is **per column, not per row**: LCP reached Firefox 122 and Safari 26.2, so it is
  required everywhere, while `layout-shift` and `renderBlockingStatus` remain Chromium-only. Severity
  is capped at S2, and `transferSize` is explicitly **not** used for a byte budget — it is 0 for a
  cross-origin asset without `Timing-Allow-Origin`, 0 for a cache hit, and a flat 300 for a 304.
- **A rendered-page conformance linter** (design-flow 1.7.0) — the browser measures, Python judges. No
  rule, count or threshold lives in JS, which is what lets a browser-driven check be gated in a repo
  with no browser in CI.
- **Marketing-copy and visual-asset doctrine** for fidara (rails-stack 1.25.0), plus the last four
  coverage rows and a Mega-menu/Dropdown correction. Verification **removed** a Tailwind claim that
  would have failed silently: `bg-gradient-to-*` is not deprecated in v4, it is *removed* with no
  alias, so the v3 name emits no class at all.
- **Harness doctrine written down** — `docs/harness-doctrine.md`: put your guarantees in the
  deterministic layer, with the guarantee-vs-advice test and the rule that **determinism is necessary,
  not sufficient**. A gate ran every time and still let behavioural code finish with no spec.
- **The computed work queue became a gate at the point of use** — `issue_graph.py --ready` refuses,
  with the reason on stderr and stdout empty, when an issue waits on open work.

### 2026-07-31 (release v1.43.0)

> ### EPIC #96 completes, and the release note's best material is what the gate refused
>
> **Phase B's last two patterns** (full-text search, bulk transfers) close the 37signals doctrine
> review — five phases, all shipped. Plus **`/rails-flow:explain`**, the **emulated-media QA pass**,
> **file upload + clipboard**, and **Mega menu as a disclosure**. `coverage.md` **7 → 4**.
>
> `rails-8` and `fidara-design` skills changed; `hotwire` and `code-review` are byte-identical.

- **EPIC #96 is complete** — canonical-Rails doctrine from campfire, writebook and fizzy, in five
  phases: style conventions, architecture, Hotwire under load, agent-instruction conventions, and the
  two deliberate divergences. Phase B's final patterns land here: **PostgreSQL full-text search** (the
  generated `tsvector` column, which PostgreSQL's own docs say *obsoletes* the trigger approach) and
  **bulk transfers**.
- **Mega menu is a disclosure, not a menu** (#90) — and APG says so in a callout on its **own** Menubar
  example: *"A pattern more suited for typical site navigation with expandable groups of links is the
  Disclosure Pattern… few sites need the additional keyboard functionality required to support the ARIA
  `menubar` and `menu` roles."* So it shares **no ARIA** with our Dropdown row, and that row gains a
  **scoping note** — `role="menu"` is right for an action menu and wrong for a nav bar. The two look
  alike and are structurally opposite.
  - A nav item that must navigate **and** expand is **two elements** — a link plus an adjacent
    disclosure button. Arrow keys are explicitly *"(Optional)"*; `Esc` is required, and APG ties it to
    **WCAG 1.4.13** rather than to taste. Hover triggers 1.4.13 in full, and *hoverable* is the one that
    fails in practice: **no gap between trigger and panel**.
- **File upload and clipboard** (#95). `accept` is a **hint, not validation** — *"you should make sure
  that the `accept` attribute is backed up by appropriate server-side validation"* — and a script
  **cannot** set a file input's value, so a dropzone is a *parallel path*, not a wrapper.
  - **The WCAG 2.5.7 trap**, which is the opposite of the obvious assumption: *"achieving keyboard
    equivalence for a dragging operation does not automatically meet this success criterion, unless that
    equivalent keyboard operation also provides controls that can be clicked or tapped with a pointer."*
    **So a `sr-only`-hidden file input behind a dropzone FAILS 2.5.7 even though it is keyboard-operable.**
  - Clipboard: the announcement **is** the feature (WCAG 4.1.3), and a repeat needs the live region
    cleared or **the second copy is silent** — identical text is not a DOM change.
- **`/rails-flow:explain`** (#126) — a plain-language `docs/GUIDE.md` with GitHub-rendered diagrams,
  section-scoped so a re-run never rewrites your prose, and runnable on a *plan* so a wrong premise
  costs a paragraph instead of a build cycle. Its mermaid output is **enforced** by a checker with 47
  selftest checks, half of them in the silence direction.
  - Three refutations kept it honest: **`graph` is not deprecated** in favour of `flowchart`; **GitHub
    does not publish its bundled mermaid version**, so the diagram rule is an allowlist rather than a
    version check; and **GitHub documents no node cap**, so our 60-node limit is **ours** and says so.
- **The emulated-media QA pass** (#116), whose guarantee runs **opposite** to its siblings: the keyboard
  and forms passes stop a row grading a real defect *down*; this one stops a row grading an advisory
  *up*. Reduced motion is **SC 2.3.3, Level AAA**, and `prefers-reduced-motion` is its *sufficient
  technique* — so implemented as the issue asked it would have filed S1s for 300 ms transitions. What
  gates is the narrow **2.2.2 (Level A)** subset.
  - **`emulateMedia()` merges** — `emulateMedia({})` resets nothing, contrary to Playwright's own docs
    example; the source at v1.62.1 settles it. A forced-colors row on **WebKit is `Blocked`, never a
    result**, because WebKit answers the media query while implementing none of the forcing — false
    *confidence*, which is worse than false defects. And **print cannot detect clipped content** at all,
    so that acceptance criterion is recorded as refuted rather than quietly dropped.
- **FIX — a stalled interpreter was reported as a syntax error.** `subprocess.TimeoutExpired` is a
  **subclass** of `SubprocessError`, so one `except` swallowed a stall into the missing-interpreter path
  and it emerged as *"did not parse in any documented context"* — an environment stall presented as a
  **code defect**, non-deterministically and only under load. Found because a parallel session reported
  an unreproducible `30 passed, 1 failed` and **said plainly it had truncated the output and could not
  name the gate** rather than papering over it. A stall now reports **skip**.
- **FIX — the call-site rule flagged a CORRECT call site.** `ButtonComponent.new(…, data: {…})` is legal
  because that initializer ends in `**attrs`, which is how ViewComponent forwards HTML attributes — so
  the rule was primed to fire on most correct call sites. The carve-out keys on the **splat**, not on
  weakening the check, because the `ModalComponent` flag that preceded it was right.
- **Two umbrellas were closed while still carrying undocumented rows** (#91, and #95 earlier today).
  Both reopened, with the remaining rows enumerated. The rule added this cycle — *an issue with unticked
  increments gets `Refs`, never `Closes`* — was itself violated twice before it existed, which is why it
  now exists.

### 2026-07-31 (release v1.42.0)

> ### Six sessions in parallel — and the release note worth reading is what they caught in each other
>
> **`hotwire/references/production.md`** (Hotwire under real load, from campfire + fizzy),
> **rails-flow agent-instruction conventions**, a **computed work queue** from a declared dependency
> graph, **qa-flow keyboard + forms evidence contracts**, and a **design-flow setup cross-check**.
> Plus nine fixes, most of them defects one session found in another's merged work — or in its own.
>
> `rails-8`, `hotwire` and `fidara-design` skills changed; `code-review.skill` is byte-identical.

- **Hotwire in production** (#99). Doctrine from once-campfire and fizzy under real load — broadcast
  patterns, morphing, presence, and the catch-up path for when the socket drops, which our doctrine
  never had: we documented how to broadcast and never what happens when delivery fails.
  - **The gate refuted the issue's own question.** #99 asked what fizzy's `turbo-rails` offline-cache
    pin implies. It implies **you cannot use it**: `Turbo.offline` ships in no released Turbo or
    turbo-rails, the branch re-exports an unmerged PR, and the matching turbo-rails PR was closed by
    its own author. Reading that Gemfile as licence to copy would have put an unreleasable git-branch
    dependency into shipped doctrine.
  - **The two apps disagree, and that is the finding.** fizzy is the larger app with **zero** Action
    Cable channels; campfire has **six**. Size does not pick the mechanism — update rate, render cost
    and client state do. Sharpened into a testable rule: **Action Cable when the payload is a *fact*,
    not a *fragment*.** None of campfire's six channels carries HTML.
  - **Three corrections to doctrine we had already shipped**, one found by grepping for the pattern
    after fixing the first: append/prepend de-duplication **removes then appends at the container
    edge** (id uniqueness, not position); *"prefer the `_later` broadcast variants"* was stated flat
    when **nothing in ActiveJob or Solid Queue orders two `_later` broadcasts to one stream** — which
    is why campfire broadcasts synchronously — and the same wrong rule was then found in
    `rails-8/references/views-hotwire.md`; and `turbo:morph` was paired with a different-scope event
    while `turbo:before-morph-attribute` was missing entirely.
  - **On our four-mixin doctrine: neither validated nor contradicted**, recorded as such. Neither app
    uses mixins; both parameterise one generic controller. The negative first rested on an empty
    `gh search code` result — **which is not evidence** — and was re-done against repository tarballs:
    161 JS files, zero mixin compositions, 96 of 104 controllers extending the bare `Controller`.
- **Agent-instruction conventions** (#100) — how 37signals brief coding agents, against what our
  scaffold generates. An existing `AGENTS.md` is now **imported, not duplicated** (Claude Code reads
  `CLAUDE.md`, and both apps use a one-line `@AGENTS.md`); a constrained architecture overview is
  added; `.claude/rules/` is named as the home for mode-specific instruction but **not scaffolded** —
  empty machinery is worse than none. A per-project `STYLE.md` is **rejected**: Phase A already
  extracted it into the skill, and copying it per project would duplicate shipped doctrine and drift.
- **A computed work queue** (#133) — dependencies declared in a parseable block instead of prose, so
  "what next?" stops being re-derived by hand and inconsistently.
- **qa-flow: keyboard and forms evidence contracts** (#114, #115). Both recompute their verdict against
  a **denominator**, so a pass cannot report a result on surface it never exercised. The keyboard
  design is shaped by *why* the hand-rolled probe failed silently: it checked one button per page and
  produced focus evidence for **25 of 72 pages while reporting nothing missing**.
  - **`Engine` is part of the contract**, because Playwright's WebKit inherits the macOS default where
    Tab reaches text fields and lists only — so a WebKit run reports every link unreachable unless the
    platform setting is confirmed. Otherwise the harness fabricates findings.
- **design-flow: setup cross-checks its own doctrine** (#150). Doctrine referencing a runtime artefact
  the generator never produces was invisible to every check we had, and surfaced at a user's first
  `/design-flow:setup` as a `NoMethodError`. Scoped to `Rails.configuration.x.<key>` reads, which is
  what makes it self-scope to things that actually raise.
- **FIX — `config.hosts` is EMPTY in production by default** (#98). The security checklist framed Host
  authorization as a development concern. Where the list is empty the middleware returns immediately
  and does **nothing**, so anything deriving a redirect target from `request.host` trusts an
  attacker-controlled header until it is set.
- **FIX — an endless-def `SyntaxError` was asserted unconditionally when it is parser-scoped** (#275),
  measured across two Rubies and both parsers. `parse.y` rejects the form on 3.4.7 and **accepts it on
  4.0.6**; Prism accepts it on both. The failing combination is `parse.y` on **Ruby 3.2–3.3**, where it
  is also the default — and this skill's floor is 3.2 while it recommends the latest stable, which is
  exactly how a snippet ships broken: parsing on the author's machine, raising on the user's.
- **FIX — a pointer that walked out of its own plugin** (#272), and the reason the rule built days
  earlier for that class stayed silent: its regex **allowlisted extensions**, and the path ended
  `.example`. CLAUDE.md already records that failure mode for packaging — *"never an extension
  allowlist, which fails open on the first type nobody added"* — and the rule repeated it anyway.
- **FIX — a skip was masquerading as a pass.** `lint_markdown_code.py` failed open on a missing
  interpreter and **exited 0**, so the doctor printed `ok` while **242 of 276 blocks went unchecked**.
  On a container without Ruby the whole sweep read green over a gate that checked 12% of its input.
  Exit 3 now maps to **skip**.
- **FIX — a gate that wrote into the working tree**, and the framing matters more than the fix:
  `mutation_check.py`'s own docstring already recorded that exact lesson, and it was violated three
  files away. Now a temp dir, an assertion that nothing is left behind, and a mutation so the
  assertion cannot go quiet.
- **FIX — mutation coverage is checked per RULE, not per guard.** A new lint rule shipped with no
  mutation behind it and the gate reported green, because the guard already declared twelve. The
  structural check immediately found a **pre-existing** hole: the two *original* rules had fixtures
  but never had mutations, from the day the checker was written.
- **FIX — one rule at two precisions across two skills.** Not a contradiction, which is why no gate
  saw it: `fidara-design` stated the Action Cable rule as a judgement call while `hotwire` derived a
  testable one. Two statements of one rule at different sharpness is how a reader cites the weaker.
- **FIX — an umbrella closed by a promotion that shipped one of its groups**, and then a commit message
  *explaining that rule* closed the same issue a second time, because it contained the literal keyword
  beside the number. GitHub parses the pattern wherever it appears.
- **Tooling now covers `docs/`, `CLAUDE.md` and `README.md`**, and strips blockquote markers so fenced
  code inside a quote is scanned — two coverage gaps in the markdown linters. **310 blocks** checked
  (185 ruby, 89 erb), verified under **Ruby 4.0.6** as well as 3.4.7.

### 2026-07-30 (release v1.41.0)

> ### Three new rails-8/fidara-design references, and doctrine corrected twice by its own gates
>
> **`style.md`** (how Rails code should read — 37signals' `STYLE.md`), **`multi-tenancy.md`**
> (row-level isolation, session-selected tenant) and **`motion.md`** (tokenised timing, reduced
> motion, gesture abandonment). Plus a cross-plane sign-in contract and **four corrections to the
> security checklist**.
>
> `rails-8.skill` and `fidara-design.skill` changed; `hotwire.skill` and `code-review.skill` are
> byte-identical.

- **`references/style.md` — how Rails code should read** (#97). The skill prescribed architecture,
  testing and deployment and said nothing about how code reads. Six conventions adopted, one
  **adapted**, two found to be doctrine we already had — that last being the more interesting result:
  *"a new resource, not a custom action"* and *"no service-object layer by default"* are what Basecamp
  actually ships, not our inference. The adapted one is *expanded conditionals over guard clauses*,
  which is **demonstrably contrary to prevailing Ruby advice** — stock RuboCop enables
  `Style/GuardClause` by default — so we take the preference and its two exceptions and add: **do not
  "fix" an existing guard clause, and never reject a change solely for using one.**
- **`references/multi-tenancy.md` — row-level isolation, session-selected tenant** (#98). Rails
  documents **no** row-level tenancy doctrine, so every choice is recorded as a choice. It separates
  the two axes people collapse into one — **isolation** and **identification** — and records the
  decision: the tenant comes from the **session, never the URL**; subdomains separate *planes*, not
  tenants.
  - **Five verified reasons not to use `default_scope`**, including that a wrong-tenant `find_by`
    returns **`nil` rather than raising**, and that it is evaluated when a `Relation` is *constructed*,
    not when the query runs.
  - **The job boundary is worse than an ordering problem.** GlobalID's default locator is an
    `UnscopedLocator` that strips **all** scopes by design, so `default_scope` gives **zero**
    protection for a record arriving as a job argument — and `deserialize_arguments_if_needed` runs
    *before* `run_callbacks :perform`, so a tenant restored in `around_perform` is too late.
  - **PostgreSQL RLS is inert by default in a Rails app**: *"table owners normally bypass row
    security"*, and your app owns the tables its migrations created. `FORCE ROW LEVEL SECURITY` is the
    lever; checking for `BYPASSRLS` proves nothing.
- **Cross-plane sign-in, and four corrections to the security checklist** (#98). One front door
  authenticating both realms, holding **no session of its own**, minting a short-lived single-use
  **encrypted** grant. Encrypt rather than sign because the grant rides in a URL and *"the payload is
  merely encoded (Base64 by default) and can be decoded by anyone."* Corrections: **`config.hosts` is
  empty in production by default** (we framed it as a dev concern); Rails 8.1 added
  **`allowed_redirect_hosts`**, safer than `allow_other_host: true`; `authenticate_by` is **7.1**;
  `rate_limit` is **7.2** and is a **permanent no-op under `:null_store`**, the Rails test default —
  so a throttling spec passes whether or not throttling works.
- **`references/motion.md` — tokenised timing and reduced motion** (#136). Our motion doctrine was
  **one line**. Now: two curves with a **departure always shorter than an arrival**, three durations
  chosen by **travel distance**, opacity finishing before height on disclosure, and the **eight ways a
  gesture can be abandoned** — *"if a component can be mid-gesture, it registers a window `blur`
  listener"*, or alt-tabbing mid-press leaves the element stuck.
  - **Reduced motion changes behaviour, not just timing** — *"the information still arrives, the trip
    is skipped."* And gating on `no-preference` is recorded as **our reasoned default, not a
    citation**: MDN's own example and WebKit's own article both use the opposite direction.
  - **An entrance no longer needs JavaScript** — `@starting-style` + `transition-behavior:
    allow-discrete`, Baseline *newly* available Aug 2024, so a progressive enhancement rather than a
    floor.
- **Tooling: an umbrella issue gets `Refs`, never `Closes`.** A promotion retired the Phase-2 component
  umbrella while seven of its rows were undocumented, after which four further slices landed against a
  closed issue. CLAUDE.md now says to check the body for unticked boxes before writing `Closes`.

### 2026-07-30 (release v1.40.0)

> ### The code in our fences is now syntax-checked — and it was hiding four hazards
>
> 154 ruby, 85 erb and 22 js blocks (3,160 lines) had never been executed by any gate, only the 79 bash
> ones had. Four blocks raised `SyntaxError` the moment anyone pasted them. Also: **Range input** and
> **Calendar/Date/Time picker** documented, `coverage.md` **9 → 7**, both native-first.
>
> `fidara-design.skill`, `rails-8.skill` and `hotwire.skill` changed; `code-review.skill` is
> byte-identical.

- **Four copy-paste hazards fixed in shipped skills, every one of which raises on paste.** A bare
  `rescue … end` with no `begin` and no enclosing method; two lines where `/` was read as a separator
  when Ruby reads it as **division** (`Product.select(:id, :name) / .pluck(:name)`); and two Stimulus
  blocks mixing a `static` class field with bare `this.` statements, which cannot share a scope. The
  Stimulus examples now show the accessors **inside the method that uses them** — which parses, and
  documents the point the old shape obscured.
- **NEW gate: `lint_markdown_code.py`.** `node --check` and `ruby -c` per fenced block, with
  `--audit-coverage` and a 27-check selftest. Fails **open** on a missing interpreter and reports
  **skip**, never a pass.
  - **Its own first run was 26 findings, 22 of them the linter's fault** — and that is the useful part.
    `<%= form_with … do |f| %>` and `<%==` are **invalid in stdlib ERB** because Rails compiles views
    with **erubi**; both are normalised away rather than taking a gem dependency that would make the
    gate pass or fail by machine.
  - **`js` matched the `js` in ` ```json `**, so every JSON block was being parsed as JavaScript. The
    coverage control caught it — worth noting the direction: that audit was written to catch an
    **under**-matching extractor and caught an **over**-matching one.
  - **ERB does not error on an unterminated `<%`.** It emits the remainder as a **literal string**, so
    the expression silently never runs and the view renders text where a value belongs. `ruby -c` on the
    compiled output sees nothing wrong, so this needs an explicit balance check — the compiler will
    never give you one.
- **Range input: do not hand-write slider ARIA onto a native range.** ARIA in HTML says *"No `role`
  other than slider, which is NOT RECOMMENDED"* and that authors **SHOULD NOT** set
  `aria-valuemax`/`aria-valuemin` on it. For the custom widget, only **`aria-valuenow`** is required
  (min/max default to 0 and 100), **`Home`/`End` are required keys and `Page Up`/`Page Down` are
  explicitly optional**. Leave native except for **two thumbs** (a separate APG pattern, and APG says to
  test on touch AT before production) or **a value a number cannot convey** (`aria-valuetext`, which
  layers onto the native element). **A vertical slider is not a reason** — that is native via
  `writing-mode`.
- **Date/time: native-first rests on a spec guarantee, not optimism.** The `type` attribute's *"missing
  value default and invalid value default are both the Text state"*, so an unrecognised `date` keyword
  renders a **text input** — the field keeps working, only the picker is lost. The value is
  **`yyyy-mm-dd` always**, whatever the display locale. `step` is **days** for date and **seconds** for
  time, where a step not divisible by 60 is what surfaces a seconds field.
- **There is NO APG "Date Picker" pattern**, so *"a date picker must be a dialog"* is **refuted**: two
  *examples* exist, one under **Dialog** and one under **Combobox**, and the Dialog one links the other
  as a *"Similar example"*. Two valid architectures, neither mandated. Relatedly, `aria-selected` (the
  chosen date) is cited to APG's examples while `aria-current="date"` (today) is cited to **ARIA 1.2** —
  APG's examples use no `aria-current` at all, so blending the two would have mis-attributed half the
  claim.
- **WCAG scoped rather than sprayed.** **1.3.5** applies to a date field only when it collects data
  *about the user*; **2.5.8 Target Size (Minimum)** (AA, new in 2.2) has a **User Agent Control**
  exception covering the native thumb and picker, so it bites only once you hand-build one — and 2.5.8
  is **not** 2.5.5, which is a different AAA criterion at 44×44.
- **Two no-break spaces shipped in v1.39.0 made a behaviour-table row unsearchable.** U+00A0 renders
  exactly like a space, so grepping the phrase returned nothing. Found because an anchored edit failed
  with *0 matches* against a string copied out of the file. Fixed, and a new mechanical
  **`invisible-character`** rule now covers 13 such characters across 174 shipped files — with a
  near-miss fixture pinning the punctuation we *do* use, so the rule cannot go red on its own corpus.
- **`mutation_check` 23 → 30 across 7 guards**, all caught. Writing them found three more defects of the
  familiar family: a **vacuous fixture** (`<%%= foo %>` has a `%>` later in the line, so misreading the
  escape changed nothing), an **unobservable mutation** (`export` is a `SyntaxError` in every wrapper, so
  that skip is an optimisation, not a guard), and a **selftest that read the real repo tree** while
  running against a mutated copy in a temp directory — so every mutation was "caught" by a traceback
  instead of by its fixture. **A crash is not a verdict.**

### 2026-07-30 (release v1.39.0)

> ### `fidara-design` documents loading, progress and dialog state — and `aria-modal` finally tells the truth
>
> Progress bar, Skeleton, Spinner, Drawer, Carousel, Image gallery/Lightbox. `coverage.md` **15 → 9**
> `needs doctrine` rows. Two live accessibility defects fixed in doctrine users already have: a modal that
> claimed `aria-modal="true"` while its focus trap never made the background inert, and a cart total that
> could announce as bare digits without its label.
>
> `fidara-design.skill` changed; the other three archives are byte-identical.

- **`aria-modal="true"` promised background inertness the shipped code never delivered.** The doctrine
  said the focus-trap mixin *"mark[s] the background inert"*; `focus_trap.js` bound a Tab-cycling handler
  and locked body scroll, and nothing else. Tab-cycling confines *the tab sequence* — a virtual cursor, a
  rotor, a swipe, or a click all still reached the background. ARIA 1.2 is blunt that this is worse than
  not claiming modality: *"users of those technologies will experience severe negative ramifications if a
  dialog is marked modal but does not behave as a modal for other users."* Now `inert` — alone, never
  paired with `aria-hidden`, which is how a background ends up hidden from AT but still clickable — and
  nesting-safe, since the trap restores only what it changed.
- **A cart total could announce as "52.00" with no label.** Bare `aria-live="polite"` leaves
  `aria-atomic` at **false**, so only the changed node is presented. `role="status"` carries polite *and*
  atomic. The Category row shipped in v1.38.0 already said `role="status"`, so v1.38.0 contradicted
  itself on arrival.
- **The gate refuted four claims before they shipped, which is the point of having it.**
  - *"A drawer must trap focus"* — false as stated. Trapping is what **modality** requires. An overlay
    drawer is a modal dialog; a **persistent push sidebar is not a dialog at all** — never overlaid, so
    it fails APG's own definition — and must not trap focus or take `aria-modal`. The previous guidance
    said "positioned to an edge — keep its focus trap" with no qualifier.
  - *"Carousel slides must be `aria-hidden`"* — refuted. APG names no such requirement and its own
    reference implementation uses `display: none`; what it warns against is a slide *displayed
    off-screen* while still in the accessibility tree.
  - *"A lightbox must be a dialog rather than a full-page route"* — no upstream either way. Ours by
    decision, and labelled as ours.
  - *"Indeterminate progress is `aria-valuenow="0"`"* — no: **omit** the attribute. `0` reads as "no
    progress made", a different claim from "unknown". Every `progressbar` value attribute is optional.
- **Three corrections to what we would have written from memory.** A carousel container is
  `role="region"` **or** `group`, not `group` only. A **Tabbed** slide is `role="tabpanel"` and *drops*
  `aria-roledescription`. There are **three** variants (Basic, Tabbed, Grouped), not two — and play/pause,
  stop-on-hover and stop-on-focus are required **only if it auto-rotates**.
- **`meter` must never be used for progress.** Not stylistic: `meter` *requires* `aria-valuenow` where
  `progressbar` treats it as optional, and both ARIA and APG say authors SHOULD NOT use it for progress.
- **Reduced motion for a shimmer or a rotation is WCAG 2.2.2, not 2.3.3** — 2.3.3 covers motion from
  *interaction*, and 2.2.2 is conditional on over five seconds *plus* parallel content. Respect the
  preference regardless; do not cite the wrong SC for it.
- **Two false citations of our own removed.** A `(WAI-ARIA APG)` heading claimed the spec for an entire
  behaviour table including rows with no pattern, and **"33 named patterns" was wrong twice — the index
  lists 30**. The conclusions drawn from the figure were right; the figure was invented precision.
- **`components.md` advertised a Modal `body` slot that does not exist**, so `m.with_body` raised
  `NoMethodError` for three releases — the #168/#182 class surviving in prose, where the call-site linter
  cannot reach. `Ui::ModalComponent` also gains `placement:`, so an overlay drawer is the same component
  at an edge: one dialog implementation, one focus trap, one `Esc`.
- **Tooling:** the self-consistency linter's icon rule flagged **prose stating the icon rule**, fixed with
  near-miss fixtures pinning both edges; a new guard stops a promoted coverage row keeping its
  *"until the entry lands"* workaround (it was invisible in the rendered table, and the Combobox entry had
  outlived its own promotion this way); `mutation_check` **19 → 23**.

### 2026-07-30 (release v1.38.0)

> ### `fidara-design` documents all twelve page archetypes
>
> Landing, Pricing, About, Error, Auth — plus the whole commerce family: Storefront, Category, Product,
> Cart, Checkout, Order detail, Order history. `coverage.md` **27 → 15** `needs doctrine` rows, and every
> remaining gap is now a *widget* rather than a page.
>
> `fidara-design.skill` changed; the other three archives are byte-identical.

- **Twelve page archetypes documented** (#90, #91). These are compositions with no ARIA pattern
  upstream, so the authority is the maintainer decision rather than a verifier verdict — which is why
  they shipped as their own slices instead of queueing behind fifteen widget verifications.
- **Shell assignment is doctrine, not taste.** Marketing pages are the only place the *stacked* shell is
  the default; **Auth uses no shell at all**, because showing app navigation to someone who is not
  signed in advertises destinations they cannot reach.
- **The failures these prevent are specific, and several are security or revenue rather than polish:**
  - A **404 design served with HTTP 200 is a soft 404** — indexed by search engines, invisible to
    monitoring. A **500 page must not depend on the app**: no database call, no current-user lookup, no
    asset the failed boot may not have compiled.
  - **`autocomplete` tokens are a security property.** Without
    `username`/`current-password`/`new-password`, password managers cannot fill or save, and people fall
    back to weaker passwords they can type. Auth must never reveal *which* credential was wrong, and a
    reset must always report success — both are account-enumeration oracles.
  - **Cart quantity edits change the total silently.** A live region on the total is the whole fix, and
    this is the most-missed item in commerce accessibility. A **remove control must name its item** — an
    icon-only `×` announces as "button", and there are six of them.
  - **A discount needs two prices and a word** (`<s>` plus `sr-only` "was"/"now"): colour and a
    strikethrough convey nothing to a screen reader, and red-as-cheap is not universal. Stock, variant
    availability and order status are all **text**, never colour alone.
  - **Checkout:** never require an account to buy, never lose what was typed on a validation failure,
    and make a double-submitted payment **server-side idempotent** — a disabled button alone loses to a
    slow network.
  - **Category filters are a `GET` form that works without JavaScript**, so state lives in the URL and
    results are shareable and back-button-correct; the result count is announced via `role="status"`;
    and pagination is the default, because infinite scroll breaks the back button and has no addressable
    position.

### 2026-07-30 (release v1.37.0)

> ### `fidara-design` gains two component contracts and a call-site reference
>
> Combobox is documented against a verified APG contract, Command palette is derivable from it plus
> Modal, and **every documented component now has a worked invocation** — 14 of 20 previously had none.
> `fidara-design.skill` changed; the other three archives are byte-identical.

- **Combobox / Autocomplete is `documented`; Command palette is `derivable`** (#95) — `coverage.md`
  **29 → 27**. The contract was APG-verified first: `role="combobox"` on the **input** (the wrapper form
  is the superseded ARIA 1.1 model), `aria-selected` on the **active** option because selection follows
  focus, `aria-controls` required, and a collapsed popup carrying `hidden` as well as the ARIA state.
  Command palette turned out not to be a gap at all — APG has no such pattern, so it composes from the
  documented Modal plus the documented Combobox, with `aria-activedescendant` effectively mandatory
  because the input must hold focus for typing to filter.
- **A worked call site for every component** (#238). 14 of 20 had none, so a reader had to infer the
  invocation — which is how `FieldComponent.new(form:, name:)` and `field_classes` both shipped and
  raised in a user's project. It also silently disarmed the call-site linter: a component with no call
  site has nothing to check. `DropdownComponent` turned out never to have been **declared** at all — an
  ERB template with no class — so its `items:` keyword and `trigger` slot had never been checkable.
- **Three linter defects, each found by exercising something rather than reading it.** A `renders_many`
  slot's setter is **singular** (`with_option` for `renders_many :options`), so correct call sites were
  being flagged — it had never surfaced because no shipped call site used a `renders_many` slot. And two
  new rules now hold the line: `component-without-call-site` and `undeclared-component-call-site`, both
  firing **zero** times, because the call sites were written *before* the rules landed. A rule that
  starts red gets suppressed, and then the class stops being caught at all.

### 2026-07-30 (release v1.36.0)

> ### Who this affects
>
> **Nobody who installs the marketplace.** No skill or plugin changed — all four `dist/*.skill`
> archives are byte-identical to v1.29.0, `rails-stack` holds at 1.17.1, `qa-flow` at 1.11.0. This
> release is entirely **maintainer tooling** and reaches `main` because `main` is what a fresh clone
> gets.

- **Nothing verified that a selftest could fail — now something does** (#233). Six selftests, fourteen
  gates, and no check that any of them notices its subject breaking. Two fixtures written in one session
  were **vacuous and passed for the wrong reason**: a `hasattr` on a function that never existed
  (comparing `[] == []`), and a cross-contamination scenario whose two classes shared one fenced block,
  leaving the second unregistered so the scenario never ran. Both looked right; one survived until the
  maintainer asked whether the fix was real.
  - `scripts/mutation_check.py` has each guard declare hand-chosen mutations plus **the fixture expected
    to trip** — 16 mutations across 6 guards, including the session's real defects (`:id` matching
    greedily, duplicate signatures accepted, a truncated line crashing the parse, full-page evidence for
    a component purpose, the paren-less render regex).
  - **A stale anchor is a hard error, not a pass** — a mutation that cannot apply yields a mutant
    identical to the original, which passes and reads exactly like a caught mutation. **A coincidental
    catch does not count** — a fixture going quiet would otherwise be masked by its neighbour.
  - Deliberately **not** a general mutation framework: a declared list is auditable, whereas generated
    survivors nobody triages are indistinguishable from a pass.
  - It found **four defects in itself while being built**, which is the useful part — two expectations
    written as a finding's message text (absent by definition once the mutation removes that finding),
    one malformed mutation that crashed rather than cleanly disabling its check, and a flat temp layout
    that broke a selftest reading repo-relative files.
- **`CLAUDE.md`: an issue body is not an authority.** The doctrine gate covered *editing* doctrine, never
  what you edit **from**. #142 nearly shipped a fabricated APG citation because its contract read as a
  spec. The rule now also requires reading for **omissions**, and states that where no upstream exists
  an INCONCLUSIVE verdict means a recorded maintainer decision — never a citation invented to fill the
  gap.
- **A sweep of every regex-based rule against its idiomatic alternative form found the rules sound.**
  #182 had fixed a paren-less blind spot in one of three rules without checking the siblings, which took
  six releases to surface. Worth recording that **one probe was wrong rather than the rule** — I nearly
  filed a false finding against a working guard. The single genuine gap is now a documented boundary:
  the unbounded-query rule excludes `gh api` collection iteration on purpose, since that risk profile is
  ~1000 rather than 30 and firing correctly needs judgement about which endpoints return collections.
- Sweep is now **16 gates / 27 checks**, ~43s. **Stated stopping condition: this is the last
  verification layer.** A fourth would be guards on guards on guards.

### 2026-07-30 (release v1.35.1)

> ### If you use `fidara-design`, this is a correctness fix
>
> The combobox behaviour table shipped **missing `aria-controls`** — one of only two attributes ARIA
> 1.2 marks *required* for the role — while `forms.md` had it. An agent following the table emitted a
> non-conformant combobox. It also attributed `Space` and typeahead to an **editable** combobox, where
> `Space` types a space; applied as written it yields a control that swallows the space bar.
>
> `fidara-design.skill` changed; the other three archives are byte-identical.

- **Shipped combobox doctrine was wrong in two ways** (#229), found by a `doctrine-verifier` run aimed
  at two *unwritten* rows — it turned up errors in doctrine shipped an hour earlier instead. An error
  in shipped doctrine outranks a gap in unwritten doctrine, so it jumped the queue.
  - `aria-controls` restored to the behaviour table, reconciling it with `forms.md` — the two files had
    contradicted each other on load-bearing wiring
    ([ARIA 1.2 §combobox](https://www.w3.org/TR/wai-aria-1.2/#combobox), read 2026-07-30).
  - `Space` and typeahead scoped to the **select-only** variant, where there is no text field for
    `Space` to type into. Neither appears in APG's normative Keyboard Interaction section for a
    combobox.
  - Both focus models now stated as sanctioned — ARIA 1.2 presents DOM focus into the popup as the base
    case with `aria-activedescendant` *"in lieu of"* it, and for a **dialog** popup activedescendant is
    *disallowed*.
  - Required vs optional keyboard bindings separated: `Home`/`End` are required only for a **tree**
    popup, `PageUp`/`PageDown` are absent from the listbox section entirely, and `→`/`←` move the text
    cursor rather than navigating options.
  - **Version boundary recorded:** three combobox models existed — 1.0 `aria-owns`, 1.1 non-focusable
    wrapper, 1.2 role-on-input. ARIA 1.2 states a 1.1-conformant combobox *"will no longer conform"*, so
    the note exists to stop anyone reverting our doctrine from an older tutorial.
  - `forms.md`'s "native select first" attributed to the *First Rule of ARIA Use* — a **W3C Discontinued
    Draft** — rather than implied to be a pattern requirement.

### 2026-07-30 (release v1.35.0)

> ### Who this affects
>
> **`fidara-design` gains a full disclosure contract** — the second most common interactive pattern
> after plain links (732 instances in a 72-page corpus) previously had one word of doctrine.
>
> **`fidara-design.skill` changed again**; `rails-8`, `hotwire` and `code-review` are byte-identical.
> Re-upload only `fidara-design` if you use the claude.ai path.

- **rails-stack 1.17.0 — disclosure is first-class doctrine, and the verifier gate stopped a
  fabricated spec citation** (#142). Disclosure outnumbers dropdowns 73:1 and tabs 81:1 in the audit
  corpus, yet our behaviour table gave it one word — `(toggle)` — while rarer patterns had full
  treatments. It now has the complete contract: `aria-expanded` + `hidden` as **two separate
  obligations**, the APG-required heading wrapper for accordion headers, the ~6-panel `role="region"`
  threshold, and two of APG's three behaviours (independent collapse and single-open **collapsible** —
  not always-one-expanded, which we decline deliberately).
  - **The gate's most valuable output was negative.** The issue specified
    `ArrowUp`/`ArrowDown`/`Home`/`End` accordion navigation *"per the ARIA APG"*. Those four keys are
    **absent from the current APG Accordion pattern** — they lived in a 2017 APG 1.1 *example* and
    were deleted since. Plausible, traceable to a real source, wrong today. Shipped as written it
    would have told every downstream agent that four keybindings are mandated by a spec that does not
    contain them.
  - Three further corrections: `<details>`/`<summary>` is not APG-endorsed and **cannot animate at
    all**; `aria-controls` is APG-optional but ARIA-1.2-SHOULD for our sibling markup; and the
    reduced-motion rule cannot cite WCAG 2.3.3 — reframed as implementation correctness, since gating
    the state change on `animationend` breaks the control when the animation is suppressed.
  - `coverage.md`: **30 → 29** `needs doctrine` rows, `documented` 40 → 41. Citations and version
    boundaries are in the rails-stack entry above; the verdict is on
    [#142](https://github.com/fmanimashaun/claude-skills/issues/142#issuecomment-5127982320).
- **Maintainer tooling: the call-site linter was blind to the form ERB actually uses.** Both render
  rules required `render(` **with** a paren, so `render Cls.new(...) do |v|` escaped slot *and*
  initializer-keyword checking entirely — #182 fixed that same blind spot for the **icon** rule and
  the fix was never carried to its two siblings. Found by mutating a new call site and watching
  nothing fire.
  - Fixing it exposed a **false-positive generator**: slot uses were scanned to end-of-document, so
    two blocks binding the same variable cross-contaminated and flagged **correct** markup.
  - And one of the new fixtures was itself **vacuous** — two classes in one fenced block left the
    second unregistered, so the scenario passed for the wrong reason. Caught by reverting the fix and
    checking a fixture actually failed, which is the rule this repo already had and I had skipped.
    Selftest 31 → 36.

### 2026-07-30 (release v1.34.1)

> ### Read this if you use `fidara-design`
>
> **The previous release told you to install a private plugin that does not exist.** `brand.md`'s
> *Distribution* section instructed `/plugin marketplace add <org>/fidara-plugins` then
> `/plugin install fidara-ui`. Ignore it — there is nothing to install, and there never needed to be.
> The skill is complete on its own, and that is the only mode.
>
> **Unlike the last four releases, the `.skill` assets DID change:** `fidara-design.skill` is
> rebuilt. `rails-8`, `hotwire` and `code-review` remain byte-identical, so re-upload only
> `fidara-design` if you use the claude.ai path.

- **`fidara-design` no longer points at a plugin that should not exist** (#123). The instruction was
  written under an *inventory* model — the licensed kit as a library agents reference while building.
  #124/#190 replaced that with **guidance, not availability**: components are generated in the
  project just-in-time from doctrine plus `coverage.md`, and **83 of 113 rows need no kit reference at
  all**. So the section contradicted the skill's own coverage matrix: one part said the kit is not
  needed at build time while another told you to install it.
  - Rewritten to state the skill is complete on its own and that this is the **only** mode. A
    kit-present branch would make the same prompt produce **different output depending on whether a
    licensed plugin happened to be installed** — a non-determinism nobody without the licence could
    even test.
  - Records why the kits are never distributed: their licences forbid re-distributing components
    *separately from an End Product*, which is exactly what a plugin payload is. They inform our
    doctrine at authoring time on a maintainer machine and never travel further.
  - Adds the corollary that makes the model self-correcting: **if an agent seems to need the kit to
    build a screen, that is a defect in this skill** — a `coverage.md` row marked `derivable` that is
    really `needs doctrine` — not a missing download.
  - Full reasoning, including what was proposed and rejected, is the decision record on
    [#190](https://github.com/fmanimashaun/claude-skills/pull/190#issuecomment-5127664883). #123 is
    closed and #89 annotated, so the superseded decision is not left live in the epic.

### 2026-07-30 (release v1.34.0)

> ### Who this affects
>
> **Marketplace install: `qa-flow` 1.11.0 is a real upgrade** — a long browser run that gets killed
> now leaves usable results, and its evidence is browsable instead of a folder of PNGs.
>
> **`dist/*.skill` upload to claude.ai: nothing changed.** All four archives remain byte-identical
> to v1.29.0 and `rails-stack` holds at 1.16.0, because no `skills/**` file moved.

- **qa-flow 1.11.0 — a killed run leaves usable output** (#111). The audit's crawler wrote its
  manifest only after the final page, so a crash at page 70 of 72 lost everything — and one
  background run **was** stopped mid-flight, leaving **zero** usable output after ~30 minutes.
  `/qa-flow:certify` is the pre-`main` gate, so a lost run means re-running the whole certification.
  One JSON line per unit is appended as it completes and the aggregate is derived from that log.
  - **A truncated final line is data, not corruption** — it is the signature of the very crash this
    exists to survive, so it is counted and skipped rather than raised. One malformed line mid-file
    costs that line only, never the other 71 units.
  - **"The run ended" and "the run covered everything" are different claims**, and a summary that
    could not tell them apart was the defect: unreached units are listed explicitly against an
    expectation written before the run, and the manifest is written on abort.
  - Resume is decided in one place (`--fresh` returns an empty skip list rather than being handled
    by the caller); a `Blocked` unit is not "done", or a transient hang becomes a permanent hole.
  - Per-unit progress with a running count, and **never pipe the run through `tail`** — piping
    buffered everything until EOF, so progress could only be seen by counting files on disk. A
    supervisor that cannot tell *slow* from *hung* waits forever or kills useful work.
- **qa-flow 1.11.0 — evidence is reviewable, not 359 loose PNGs** (#120). Twelve of those were
  captures of 404 pages indistinguishable by eye, and some were **8050px tall** proving a focus ring.
  - **Capture scope is decided by purpose and enforced**: `component`/`interaction`/`a11y` must be
    clipped; `layout`/`theme`/`visual-regression` may be full-page — a rule forbidding full-page
    everywhere would be switched off by the first legitimate visual-regression run.
  - Deterministic naming, a generated `index.html` grouped by route with **validity visible**
    (dependency-free, escaped, so it still opens years later from disk), validity recorded on every
    capture per #106, and retention that keeps the last 3 runs plus any referenced by an open defect
    — ordered by run **name**, not mtime, and always printing what it pruned.
- **Maintainer tooling (not distributed): the completeness rule earned itself.** The rule shipped in
  v1.33.0 — *every `*_selftest.py` must be reachable from `GATES`* — **fired on the next script
  added**, catching the new selftest before it could be forgotten. That is the difference between
  fixing an omission and preventing the class: nobody had to remember. The sweep is 14 gates.

### 2026-07-30 (release v1.33.0)

> ### Who this affects
>
> **Marketplace install: `qa-flow` 1.10.0 is a real upgrade** — QA can now answer which routes
> nothing has ever tested, and `/qa-flow:verify` selects regression scope over a known set instead
> of guessing.
>
> **`dist/*.skill` upload to claude.ai: nothing changed.** All four archives remain byte-identical
> to v1.29.0 and `rails-stack` holds at 1.16.0, because no `skills/**` file moved.

- **qa-flow 1.10.0 — route coverage gives blast radius a denominator** (#119). qa-flow drove from a
  case catalogue and a menu scope, so the most basic coverage question had no answer: *which routes
  has nothing ever tested?* Selection in `/qa-flow:verify` was therefore judgement over an unknown
  set — you cannot pick "affected untested routes" without knowing what the routes are.
  - `route_coverage.py enumerate` builds `qa/reports/routes.json` from `bin/rails routes`, a
    `sitemap.xml`, or a filesystem-routed directory (`[slug]` → `:slug`, `[...rest]` → `*glob`).
    `report` attributes coverage, ranks the gap, and appends a per-run trend.
  - **Coverage is attributed from the already-validated evidence CSVs**, using
    `validate_evidence.py`'s own profiles to find URL-bearing columns — so a route counts as covered
    only when a row that *passed validation* says a pass went there. Coverage inherits the
    page-identity guarantees rather than trusting a second, unchecked record, and a new browser pass
    gets attribution for free.
  - **The over-credit direction is where the tests aim**, because a tool reporting 100% while nothing
    visited `/users/:id/edit` is worse than no tool: it retires the question. `:id` matches exactly
    **one** segment, so a visit to `/users/42/edit` does not credit `/users/:id`. Five failure modes
    were mutated and each is caught by its own named assertion — the greedy-match mutant alone trips
    seven, including a trend line recording 100% coverage.
  - **Nothing is inferred that would be guessed wrong.** Authentication comes from
    `coverage.authenticated_prefixes`, never from the path shape; a deduplicated findings rollup
    contributes **no** coverage (its `Example Routes` are three examples, not a visit log), and that
    exclusion is asserted — every evidence profile must be either credited or explicitly declared
    route-less, so a future pass cannot silently understate the gap. Untested **non-GET** routes rank
    first, then authenticated ones.
  - Exclusions are declared and the excluded set is **always printed, even when empty**. A gap
    **exits 0**: it is the deliverable, not a failure.
- **Maintainer tooling (not distributed): the gate sweep silently omitted selftests** (found while
  doing #119). The new `route_coverage` selftest passed locally while `maintainer_doctor --gates`
  never executed it, so the sweep would report a clean machine having skipped a whole gate. The
  doctor's selftest now asserts **every `*_selftest.py` is reachable from `GATES`** — and on its
  first run found a second omission nobody had noticed: the doctor was not running **its own**
  selftest either. Both wired in; the sweep is 13 gates. This is the `coverage-gap` class applied to
  the thing that runs the checks.

### 2026-07-30 (release v1.32.0)

> ### Who this affects
>
> **Marketplace install: `qa-flow` 1.9.0 is a real upgrade** — QA findings stop being reported as
> per-instance counts, and links are audited during the crawl.
>
> **`dist/*.skill` upload to claude.ai: nothing changed.** All four archives are byte-identical to
> v1.29.0 and `rails-stack` holds at 1.16.0, because no `skills/**` file moved. The two
> distribution paths version independently; this release moves only the marketplace one.

- **qa-flow 1.9.0 — findings are deduplicated by signature, so the counts mean something** (#118).
  Raw per-instance counts were reported as defect counts, and the inflation was measured on a real
  interaction crawl: **773** "disclosure trigger without aria-expanded" and **445** "icon-only
  control without accessible name". Every instance was real — the **distinct** count for the first
  was about **18**, one navbar defect repeating across 72 pages. A developer told "773 a11y defects"
  disbelieves the report and stops reading; told "18 defects, one on every page", they fix the
  navbar. The same arithmetic decided whether `qa-reporter` filed **18 issues or 773**.
  - Grouping is by `(issue type, component/DOM signature, offending attribute)` — never the raw
    selector, which varies per page and so defeats grouping by making every occurrence look
    distinct. Reported as `N instances across M routes`, ranked by severity then reach, with the
    full instance list kept in JSON so collapsing 773 rows summarises the data rather than
    destroying it.
  - **The guarantees are arithmetic, not stylistic.** A repeated signature is rejected — that *is*
    the dedupe. `Instances` can never be fewer than `Routes`. Example routes cannot outnumber
    affected routes. And the file must be **ordered** by severity then reach, so "ranked by impact"
    is true of the artifact instead of asserted about it.
  - Applies to **every** finding source (a11y, links, runtime, visual, interaction, functional, api,
    perf, security), checked against a vocabulary: this is not an a11y-only rule, that is only where
    it was measured.
- **qa-flow 1.9.0 — links and anchors are audited during the crawl** (#113). Nothing verified that
  links went anywhere. The audit found the value by accident: a sitemap listed **12 section-index
  URLs that all 404'd**, and it surfaced only because a human noticed "Page Not Found" in a
  screenshot folder.
  - Unique internal targets are requested once (HEAD → GET fallback); **`#fragment` targets are
    confirmed to exist**, since a link to a renamed heading is dead in the way that matters to a
    reader *and* returns 200; `target="_blank"` without `rel="noopener"` is an S3.
  - **External checking is off by default**, cached when enabled, timeouts informational — a gate
    that fails because someone else's site was down teaches people to ignore it.
  - **Asset failures are not re-crawled**: v1.31.0's `>= 400` / `requestfailed` capture (#109)
    already covers images, fonts and script chunks.
  - Findings dedupe **by target**, which is why these shipped together — one dead link in a shared
    footer is one finding across seventy routes, not seventy.
- **Maintainer tooling (not distributed): an unbounded `gh issue list` made dedupe read a truncated
  tracker** (#211). `gh issue list` defaults to `--limit 30`, so `issue-triager`'s **duplicate
  detection** could conclude "no duplicate exists" having read 30 of 42 issues and then file the
  duplicate it exists to prevent; `maintainer-audit`'s clustering read its "systemic gap" signal off
  a truncated list too. Both bounded, and a new `unbounded-issue-query` lint rule makes it
  re-checkable — grading invocations rather than mentions, so a historical CHANGELOG reference is not
  something the linter demands be rewritten.

### 2026-07-30 (release v1.31.0)

> ### Who this affects
>
> **If you install the marketplace: `qa-flow` 1.8.0 is a real upgrade** — two new capabilities in
> the QA loop, described below.
>
> **If you upload the `dist/*.skill` archives to claude.ai: nothing changed.** All four
> (`rails-8`, `hotwire`, `fidara-design`, `code-review`) are byte-identical to v1.29.0, verified by
> hashing them against the tag, and `rails-stack` stays at 1.16.0 because no `skills/**` file moved.
> The two distribution paths are versioned independently and this release only moves one of them.

- **qa-flow 1.8.0 — the browser's own complaints are now evidence** (#109). qa-flow never looked at
  the console or the network log, so a route could return 200, render, satisfy its assertion and
  **pass its case** while throwing uncaught exceptions or 404-ing its own script bundle. A real
  audit hit both at once on a route serving HTTP 200: `Module not found:
  svgmap/dist/svgMap.min.css`, and a repeating `TypeError: localStorage.getItem is not a function`.
  #106 made page *identity* trustworthy; nothing asked whether the identified page then **worked**.
  - Both browser-driven passes now attach `pageerror` / `console` / `requestfailed` / `>= 400`
    listeners on every visit, writing one row per route to
    `qa/manual-tests/<date>-<slug>-runtime.csv`.
  - **The severity is enforced, not documented.** `validate_evidence.py` recomputes it from the
    row's own counters, so a report cannot talk its findings down: an uncaught exception or a
    failed document/script/stylesheet is **S1** however the row grades itself; `console.error` and
    failed subresources are **S2**; `console.warning` never gates. An `S1` with nothing behind it
    is a finding too, because an unexplained S1 trains people to ignore S1.
  - **Suppression stays visible.** `runtime.ignore` silences known third-party noise — necessary,
    since an always-red check gets switched off — but suppressed findings are still counted in a
    required `Ignored` column, **even at 0**.
- **qa-flow 1.8.0 — app boot survives real projects** (#110). Booting two audited bundles needed
  several manual interventions `/qa-flow:smoke` would have failed on.
  - **A running server is reused, never duplicated.** The port is probed first; a live server is
    reused, reported, and never torn down — it is not ours to kill, and it may not be running the
    working tree's code. Two dev servers against one project contend over the same build cache.
  - **`route_timeout` is separate from `boot_timeout`.** A Turbopack app reported *"Ready in 10s"*
    then spent **45–60s compiling each route on first hit** — with one timeout covering both, the
    crawl clears boot and dies on route 2, which reads as a broken app rather than a slow compile.
  - **Boot failures are classified** (port in use / dependency / runtime mismatch / framework
    security policy / application error) with the log tail and a next action, plus a
    **known-gotcha table**: Hugo ≥ 0.158 refusing raw `.html` without `HUGO_SECURITY_ALLOWCONTENT`,
    Node 25's injected global `localStorage` breaking SSR feature-detection, and `exports`-map
    subpaths that are unresolvable though the file is on disk. All three read as application
    breakage and are not.
  - **Prebuilt assets are detected and the assumption stated**, never silently skipped.
- **Maintainer tooling (not distributed): the docs describing what we ship had drifted** (#203).
  `CLAUDE.md` said the release publishes "the two `.skill` assets" when there are four — caught only
  because that figure was copied into v1.30.0's release notes and then checked against the real
  files. Following this repo's own rule to grep for the pattern found worse: **`design-flow` was
  named nowhere in CLAUDE.md**, whose opening section defines what this repo distributes, while that
  section said "four app-builder plugins" and listed the other four. A new `undocumented-plugin`
  lint rule now requires every plugin declared in `marketplace.json` to be named in both `CLAUDE.md`
  and `README.md`; it is known-answer calibrated against the tree that shipped the defect.
- **Maintainer tooling: related issues are worked on one branch** (#206). "One issue at a time" was
  written in three places while grouping related work is plainly faster — and for issues that are
  one change wearing several numbers (#109 and #110 edit the same path) splitting produces two PRs
  where the second cannot be reviewed without the first. Grouping is now the default for related
  work, bounded so it stays safe: same component, one coherent mechanism, the same change type under
  the doctrine gate, still bisectable — and traceability is never pooled, so each issue keeps its own
  `Refs`, CHANGELOG bullet and `Closes`.

### 2026-07-29 (release v1.30.0)

> ### Nothing you install changed
>
> **No skill, plugin, or `dist/*.skill` asset differs from v1.29.0** — all four `.skill` archives
> (`rails-8`, `hotwire`, `fidara-design`, `code-review`) are byte-identical to the previous release,
> verified by hashing them against the `v1.29.0` tag, and `rails-stack` stays at 1.16.0. If you use
> the marketplace, upgrading gains you nothing and costs you nothing.
>
> This release exists because **`main` is what a fresh clone gets**, and everything below is
> maintainer tooling that was only on `dev`. Cloning the repo is how a maintainer machine acquires
> the flow, so leaving it unpromoted meant a new clone did not have it.

- **A new maintainer machine is set up by a script, not by remembering** (#199). Moving maintenance
  to a second machine had needed a hand-written ~120-line briefing, complete only because its author
  had just hit every trap personally. `scripts/maintainer_doctor.py` now diagnoses and repairs the
  setup — fresh clones landing on `main`, a stale local `main` ref (which made the prescribed
  `git diff dev main` report 5,231 phantom deletions once), the optional licensed corpora, and
  `git status --porcelain` collapsing a new untracked directory so a new file reads as nothing.
  `--fix` touches only the local `main` ref and checking out `dev`: never a history rewrite, never
  `reset --hard`, never `clean`. `/maintainer-onboard` wraps it with the judgement half.
  - **Three outcomes, not two.** `ok`, `FAIL` and **`skip`** are reported distinctly, because a
    check that did not run must never render as one that passed.
- **`build_coverage.py --selftest` stopped counting skipped checks as passed** (#198, shipped as part
  of #199). It printed `35 checks passed` on a machine without the licensed corpora while **two of
  those checks never ran** — the live totality check and the `coverage.md` drift check, both of which
  need the real kits. So the coverage guards were inert while reading green, which is the
  `gate-that-cannot-fail` class this repo ships rules about. It now reports
  `33 passed, 2 SKIPPED`, names both, and still exits 0 so a contributor without the optional
  corpora is not failed.
- **The licensed-corpora ignore rules could not match the layout our own docs prescribed** (#197).
  `.gitignore` used directory-only patterns (`tailwind-ui/`, `everylayout/`, `flowbite*/`), and a
  trailing slash matches a real *directory* while git stores a symlink as mode `120000`. The setup
  instructions said to attach the kits "with a clone plus links" — so following the documented setup
  left all three **untracked and unignored**, listed by `git status` directly beneath the warning
  about 656 MB of licensed blobs the rule could not actually stop. The corpora now attach as one
  nested clone in a gitignored `design-corpora/` subfolder: nothing is linked, so there is no
  mode-`120000` path for a pattern to miss, and the Windows directory-junction workaround leaves the
  documentation. `maintainer_doctor.py` gained a `corpora ignore rules` check that proves the
  patterns still cover it — probing paths that *do not exist*, because a trailing-slash pattern does
  match a real directory, so testing the real path on a machine that has the kits would hide the
  regression.
- **The full gate sweep no longer fails a machine for not having an optional download** (#197).
  `--gates` ran the coverage-drift check unconditionally, so a corpora-less machine got
  `[ FAIL ] gate: coverage matrix drift` and the verdict *"fix the failures above before doing
  maintenance work"* — about a licensed 656 MB clone nobody is required to have. A gate that
  **cannot** run is not a broken machine. It skips now, and still fails on real drift when the kits
  are present.
- `lint_self_consistency.py` prunes `design-corpora/`: with the kits inside the tree it was checking
  our own claims against ~125 third-party vendor markdown files, where a finding would be both false
  and unactionable (#197). The `.gitignore` comments explaining why the corpora live in a separate
  private repo were also expanded (#196).

### 2026-07-29 (release v1.29.0)

> ### ⚠️ Behaviour change — read this before upgrading mid-branch
>
> On a **`feature/*` or `fix/*` branch**, changing code under `app/` or `lib/` now **blocks the
> Stop gate once** unless `docs/acceptance/<branch-slug>.md` exists and holds. That is the point of
> #125 — acceptance criteria are defined *before* implementation — but it will surprise you if you
> upgrade in the middle of a branch.
>
> **If you are blocked:** write the file the message names, one `##` section per unit, each
> criterion as `- **AC-1** Given <state>, when <action>, then <observable>`, with at least one
> error-path criterion per unit (tag it `[error]`). The block message states this too.
> Validate any time with:
>
> ```bash
> python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_criteria.py" "docs/acceptance/<slug>.md" --specs spec
> ```
>
> The slug is the branch name after `feature/`, with any remaining `/` flattened to `-`. Other
> branches (`main`, `dev`, ad-hoc work) are **unaffected** — the requirement is scoped to the flow's
> own branches on purpose.

- **A silently-broken Stop gate is fixed, and it affected every prior release** (#125, found by
  behaviour-testing the new gate rather than reading it). Plain `git status --porcelain`
  **collapses a new untracked directory** to `?? app/`, so `app/models/invoice.rb` in a *brand-new
  folder* never matched `^(app|lib)/.*\.rb$`. Behavioural code in a new directory could therefore
  finish a session with **no spec at all** — the exact rule the gate exists to enforce — and it
  failed **silently**: the gate reported clean, which is indistinguishable from a pass. Now
  `--porcelain -uall`, with path parsing that survives spaces and takes the *new* path of a rename.
  If you have been adding models or services in new directories, this gate has not been guarding
  them.
- **rails-flow 1.11.0 — acceptance criteria before implementation** (#125). The gate already
  required "no behavioural change without a proving spec", but it fires *after* code exists, so it
  cannot tell whether the spec asserts what was **required** or merely what the code happens to do.
  A goal written after the result is unfalsifiable — the same defect class as a gate that cannot
  fail, moved from the gate to the goal. This is the other half of qa-flow #106: that made
  *evidence* trustworthy, this makes the *expectation* trustworthy.
  - `/rails-flow:feature` Phase 1 and `/rails-flow:fix` write `docs/acceptance/<slug>.md` before any
    code, each criterion carrying a stable id (`AC-1`, `AC-2`, …).
  - **The id makes "the spec proves the criteria" checkable.** The proving spec cites it
    (`it "AC-2 rejects an invoice with no line items"`) and the shipped `check_criteria.py` verifies
    **every criterion is cited by some spec** — a real 1:1 mapping rather than a claim. It also
    enforces the Given/When/Then shape, rejects rubber-stamp observables (`works`, `handles errors`,
    `gracefully`, `as expected`), and requires **at least one error-path criterion per unit**,
    because every security finding this flow has produced downstream was an error or edge path.
  - The gate **fails open** on a missing `python3` (a guard decides whether to RUN a check, never
    softens the verdict) and **closed** on a real finding.
  - Bounded honestly in script and doctrine alike: it proves a criterion is *traceable* to a spec,
    not that the spec truly asserts the observable, and it cannot know the criteria predate the code
    — that is the gate's ordering, not the parser's.
- **qa-flow 1.7.0** — `case-author` reads `docs/acceptance/*.md` as its **first** source, closing a
  loop that was broken in one direction: it and `qa-lead` already claimed to read acceptance
  criteria from `docs/`, but nothing in rails-flow ever wrote them. The consumers existed; the
  producer did not.
- 26 selftest assertions for the criteria checker; **10 deliberate mutations each caught**, including
  removing the word-boundary anchor from the rubber-stamp list — which would flag "property" and
  "workspace", the false-positive route to any check being switched off. The gate itself was
  behaviour-tested on real git repositories across six scenarios.
- Nothing distributed as a skill changed, so the **`.skill` assets are byte-identical to v1.28.0**.

### 2026-07-29 (release v1.28.0)
- **rails-stack 1.16.0 — component coverage: what to build, and where to use it** (#124). The
  component work so far came from **sampling**, so "is the library complete?" had no answer — and
  sampling cannot give one: a component nobody thought of is indistinguishable from one deliberately
  skipped. Now it is a **diff**.
- `scripts/build_coverage.py` enumerates the licensed reference corpora mechanically — **93** Tailwind
  UI leaf components across `application-ui` / `marketing` / `ecommerce`, plus Flowbite's **63**
  catalogue entries — and reconciles them against our own doctrine into **113 rows** in
  `skills/fidara-design/references/coverage.md`.
- **The guarantee is the totality guard, not the file.** Every corpus entry must be claimed by exactly
  one row or **the build fails and names the stragglers**, so a new upstream directory cannot be
  silently ignored and coverage cannot rot into a stale list. Double-claims are checked explicitly,
  because a dict keyed by the reference would merge two rows silently.
- **The axis is guidance, not availability.** Components are built **just-in-time in the project**
  when a screen needs one — the kit ships doctrine, not a prebuilt library. So this is neither a build
  queue nor an availability list, and nothing is withheld: every row is buildable on demand. A row
  says only how much doctrine already exists — `documented` (40, an entry defines the anatomy),
  `derivable` (43, the row names the documented parts it composes from), or `needs doctrine #N` (30,
  an a11y/interaction contract is unwritten, so the row gives the nearest safe approach and the issue
  tracks writing the real one). `needs doctrine` is a gap in **writing**, not in capability. Every row
  also carries **where / when to use it**, and the builder refuses to emit a row missing either half.
- **`documented` is evidenced, not asserted** — each such row cites a literal string that must occur
  in the reference docs. That caught a real wrong claim while the matrix was being written: `Link` was
  marked shipped on the strength of a Button `link` **variant**, with no standalone inline-link token
  anywhere. A wrong `documented` is exactly the dangling reference v1.26.0 had to fix, so it is now
  mechanically checkable.
- **Two upstream facts corrected**: Flowbite has **no** `Separator` (theirs is `HR`, under Typography)
  and **no** cookie-consent component. Read from their docs and pinned by tests, so they cannot be
  re-added from the issue text.
- Interaction patterns and layout primitives are enumerated separately, since neither maps
  one-to-one onto a corpus directory.
- **Licensing boundary held** (#89): the corpora stay gitignored and unredistributed. The builder
  reads only directory *names* and emits only names plus our own prose — no markup, class list or
  asset. Without the corpora it **refuses to run** rather than emitting a hollow file, which is why it
  is maintainer tooling in `scripts/` and only its output ships.
- 35 selftest assertions; **13 deliberate mutations of the guards each caught**, including two rounds
  where a guard turned out to have **no reachable failure path** until a fixture was added for it.

### 2026-07-29 (release v1.27.0)
- **qa-flow 1.6.0 — a screenshot is not evidence until the page it shows is validated** (#106,
  plugin code only — **nothing distributed changed, so the `.skill` assets are byte-identical to
  v1.26.0/v1.26.1**).
- `functional-tester` was told "every finding needs a screenshot" and nothing more, so a capture of
  a 404, an error page, a redirect target, or a half-rendered skeleton could back a **Pass**. That is
  worse than no evidence: it manufactures false confidence and is invisible, because the report reads
  complete and green. A real audit wrote 66 captures from a sitemap and **12 were 404s** — a human
  caught it by eye; the tooling could not. The `Blocked` column existed in the report template with
  **no rule that ever populated it**, so a validation failure had nowhere to go but Pass or Fail.
- Every capture now passes four checks before it counts as evidence: **HTTP status** off the
  navigation response (not inferred), **final URL** against the requested one, an
  **expected-content assertion** drawn from the case's own expectation, and not-still-loading.
  Failure yields **`Blocked`** — never Pass, never Fail — with the status and URL recorded.
- **The assertion is the load-bearing signal, and this deliberately does not text-sniff.** Status
  alone is insufficient (error pages return HTTP 200); error-text alone is insufficient *and
  actively harmful* — the naive version of this fix wrongly excluded four **valid** cases, real
  404-page *designs* that return 200 and legitimately read "page not found". Fixtures pin that, so
  the over-correction cannot be reintroduced.
- **Enforced, not merely written**, because a guarantee stated in prose that nothing makes true is
  the class this repo keeps getting bitten by — and this bug *was* an instance of it. A shipped
  checker (`plugins/qa-flow/scripts/validate_evidence.py`, stdlib only) validates a fixed CSV
  contract and must exit clean before results are reported. It rejects a row missing its
  status/URLs/assertion, a result on a non-2xx/3xx status or a **silent redirect**, and a `Blocked`
  row that records nothing — and it **exits 2 rather than blessing an artifact it could not read**.
- **The rule covers every browser pass, not just the reported one.** `a11y-auditor` had the same
  defect (axe against a 404 returns *real* violations attributed to the wrong page, then files them
  as defects) and now writes a machine-checked per-page audit log. The checker is profile-driven —
  one implementation of the rule, per-artifact contracts, kind detected from the header — so adding
  a pass is adding a `Profile`, not copying a rule. `exploratory-tester` records status + final URL
  on every filed defect but is deliberately **not** gated: its mission is hunting for surprises, so
  an unexpected error page is a finding, not spoiled evidence.
- **Bounded honestly** in both the script and the agent doctrine: it closes the **omission** hole —
  the one that produced the false PASS. It cannot tell whether a recorded status is *truthful* and
  it never opens the screenshots or axe JSON, so "not still loading" stays agent-side judgement.
- **72 selftest assertions, and 20 deliberate mutations of the implementation each caught** —
  including adding text-sniffing, letting the two artifacts share one status vocabulary, accepting
  placeholder violation counts, and making header detection fall back to a default instead of
  failing closed. The selftest also cross-checks both agent files against the exact headers the
  script enforces, so doctrine and checker cannot drift into mutual rejection.

### 2026-07-29 (release v1.26.1)
- **Doctrine call sites are now checked by a linter rather than by remembering** (#182, maintainer
  tooling — **nothing distributed changed, so the `.skill` assets are byte-identical to v1.26.0**).
  A call site in a skill naming an API that does not exist is generated code that raises in a user's
  project, and that class surfaced **seven times in two days**: `--grid-min` for `--min`, `with_rail`
  for `with_sidebar`, two wrong `FieldComponent` signatures, `lucide_icon(..., class:)`, `d.with_item`
  for `items:`, and `field_classes` for `input_classes`. Five were caught by throwaway scripts written
  in the moment and discarded; **two shipped and raised**. Ad-hoc catching is not enforcement — the
  same lesson as #151 and #171 — so it is a third rule in `lint_self_consistency.py`.
- **Known-answer calibrated:** against `v1.24.0` it reproduces the defect that actually shipped, and
  is clean on current doctrine having examined 40 skill docs and 16 declared components, so the clean
  result is not vacuous.
- **Its own selftest found three faults in it**, which is the argument for building it rather than
  trusting a careful read: the first version produced **six false positives against one real finding**
  (`with_lock`, `with_connection`, `with_instructions`, `with_tool` are ActiveRecord and ruby_llm
  idioms, not slots); the icon check then flagged **the doctrine's own correct example**, because
  `tag.span(helpers.lucide_icon("x"), class: "with-icon")` passes `class:` to the wrapper; and it
  required parentheses, so it would not have caught the paren-less form that motivated it. A linter
  that cries wolf gets disabled, which is exactly the failure it exists to prevent — so every
  sub-rule now asserts both directions.

### 2026-07-29 (release v1.26.0)
- **Closes a dangling reference that was live in v1.24.0** (#95, rails-stack → 1.15.0).
  `page-anatomies.md` shipped telling agents to "fill the regions from the catalog", then named
  **heading block**, **Breadcrumb** and **description list** — none of which had catalog entries. An
  agent following that doctrine either invents the markup, which is the exact failure page anatomies
  exists to prevent, or stalls. Fixing a live defect in released doctrine is why this promoted on its
  own rather than waiting for the next Phase 2 group.
- **First increment of Phase 2**, per that issue's own instruction to ship one group at a time rather
  than all ~17 components at once. Six catalog entries + five worked ViewComponents: **Heading blocks**
  (page/section/card — one anatomy where scale is the only axis, tag and step moving together so a card
  heading can never be an `<h2>` styled small), **Breadcrumbs** (separators as `aria-hidden` markup,
  never `::after`, so a screen reader hears "Invoices, INV-042" rather than "Invoices chevron
  INV-042"; truncates first → ellipsis → last two instead of scrolling), **Description list** (blank
  values render an em dash plus `sr-only` "not set", never an empty `<dd>`, which reads as a rendering
  bug), **Button group** (actions vs single-select are *different elements* — `role="group"` vs
  `radiogroup` — not a style variant), **Media object** (never stacks; the side-by-side relationship is
  the pattern), and **Divider as a recipe rather than a component** (an `<hr>` is already
  `role="separator"`; in lists the answer is `divide-y` on the container, not *n* elements).
- **The slice deliberately cuts across the kit's own taxonomy.** It is "the patterns
  `page-anatomies.md` already composes" rather than Navigation / Lists / Elements, because closing a
  live dangling reference beats matching the kit's grouping — and these six are what the remaining
  groups build on: a stacked list is a media object in a `divide-y` container, a page header is a
  Heading with a Button group in its actions slot.
- **No duplicate mechanisms**, per the issue's own criterion: Card's `detail` recipe now *renders* the
  Description list at `inline` instead of re-implementing `<dl>` rows; single-select button groups use
  the existing **list-navigation** mixin rather than a new controller; breadcrumb collapsing reuses
  `Ui::DropdownComponent`.
- **Mechanical verification caught two violations before commit** — the reason it is a script and not a
  read-through. The breadcrumb separator called `lucide_icon(..., class: "size-4")` when the icon
  doctrine forbids any size or class (`with-icon` sizes icons to `1em` in `currentColor` *because* SVG
  presentation attributes carry zero CSS specificity — the entire reason that rule exists), and it used
  `d.with_item` when `Ui::DropdownComponent` takes `items:` as an array of `{label:, href:}`. Both
  would have shipped doctrine whose code raises. #94 caught three the same way.
- Nothing is closed by this release: **#95 has four groups remaining** (Navigation, Lists + data
  display, Forms, Overlays) and **#89** is the epic. `component-implementations.md`'s closing "the full
  catalog has worked code" claim was updated to stay true — adding entries without implementations
  would have quietly falsified it.

### 2026-07-29 (release v1.25.0)
- **simple_form owns every form, and the doctrine finally says so consistently** (#168,
  rails-stack → 1.14.0, rails-flow → 1.10.0). Maintainer decision: *no form and no form element
  exists that does not use simple_form — including inside a ViewComponent.* Three references
  contradicted it and two called APIs that do not exist: `forms.md` invoked `field_classes(state)`
  against `UiHelper`'s `input_classes(state:, size:)` (wrong name **and** wrong argument style), and
  `crud-modal-pattern.md` — the canonical create/edit example every CRUD screen is copied from —
  used `form_with` plus a `Ui::FieldComponent` signature the component does not have.
- **The root cause was deeper than the signatures, so the component is gone rather than corrected.**
  A field wrapper that renders its own `<label>`, hint and error markup **is a form element built
  without simple_form** — the very thing the mandate forbids — and correcting its arguments would
  have preserved the contradiction. Field anatomy is now a **styled simple_form wrapper defined once**
  in `config/initializers/simple_form.rb`, which is what `forms.md` always meant by "simple_form for
  the markup contract, styled to the design system". Authors write `f.input`; one definition means a
  change lands on every field at once, which is the entire reason for the mandate. A component that
  renders fields takes the form builder in and calls `form.input` instead of re-implementing anatomy.
- **No exceptions were left open.** A model-less form is `simple_form_for :q, url: …` (simple_form
  accepts a symbol); a hidden label is `label: false` plus an accessible name; `f.input_field` is
  simple_form's own control-only renderer and so satisfies the mandate, reserved for a control inside
  a composed cluster. The wrapper is documented as a **contract** — label → control → hint → error in
  a `stack`, role tokens only, `min-h-touch` + `focus-visible`, error state driven by simple_form's
  `error_class`/`aria-invalid` so `aria-describedby` is not hand-maintained — with a system spec that
  proves it on first install. If the spec fails the wrapper is wrong, not the doctrine.
- **The mandate had been enforced more strictly than it was documented.** `setup-flow` already said
  "simple_form mandatory — never raw `form_with`" and the design-auditor treated `form_with` as a
  violation, while `rails-8/ecosystem-gems.md` still said "keep `form_with` for one-off forms —
  mixing is fine". **Our shipped auditor blocked users for following our own doctrine** — the same
  shape as the ids-only job contradiction fixed in v1.23.0. rails-8 now states simple_form as
  mandatory (a deliberate divergence from the Rails default, with the reason given),
  `views-hotwire.md`'s forms section is reframed as the builder-agnostic Turbo contract, and
  `SKILL.md`'s golden path matches.
- **And the auditor's check flagged every correct form.** `grep -rn "form_with\|form_for"` also
  matches **`simple_form_for`**, because that string ends with `form_for` — so the mandate check
  fired on exactly the code it was meant to allow. A check that flags everything is as useless as one
  that cannot fire: it gets ignored, then disabled. Fixed with a word boundary and proven against a
  fixture holding one correct form and one violation. Two checks were added that catch what was
  actually unchecked — hand-rolled anatomy in `app/views` **and** `app/components`, and a stock
  simple_form initializer (unstyled fields push every view toward per-input class patching, which is
  the drift the mandate prevents).
- Pattern worth recording across this release and the last two: every recent fix has been a **check
  that looked like it was working** — two that could not fail, one that fired constantly. Each fix
  now ships with a fixture proving the check distinguishes pass from fail, because a gate never
  observed doing both is not known to work.

### 2026-07-29 (release v1.24.0)
- **Screens got doctrine** (#94, rails-stack → 1.13.0, design-flow → 1.5.0). fidara-design had a
  strong component catalog and almost **no page-level anatomy** — one base layout and the `cover`
  recipe — so an agent asked for "the invoices screen" had nothing to follow above component scale
  and invented page structure. Invented structure is where breakpoint chains, nested cards and
  inconsistent heading ramps come from. New `references/page-anatomies.md` ships **3 shell
  archetypes** (sidebar + mobile drawer, stacked top-bar, multi-column rail/main/aside) and **3 page
  anatomies** (home-dashboard, detail, settings), each stating mobile behaviour, brand-mark
  placement, safe-area handling, scroll containment, and which catalog components fill each region.
  The framing is the deliverable: **a screen is composed, not designed** — pick a shell, pick an
  anatomy, fill from the catalog. `/design-flow:component` now routes any screen-level request
  through it before writing markup.
  It also carries a **primitive-instead-of-breakpoint substitution table** (`grid-cols-1 md:… lg:…`
  → `grid-auto` + `--min`; `flex-col md:flex-row` → `Layout::Switcher`; `space-y-*` → `stack`;
  `max-w-7xl mx-auto px-*` → `shell`), because intrinsic reflow responds to the **container** and so
  stays correct inside a drawer or split view where a viewport breakpoint is simply wrong. And it
  calls out that an independent scroll region needs `min-h-0` beside `overflow-y-auto` — the bug that
  makes a shell feel broken and is invisible until you try it. Phase 1 of the kit-transformation epic
  (#89); Phases 2–5 remain open.
- **The packager stopped depending on your working copy** (#171, maintainer tooling — not
  distributed). `.gitattributes` is `* text=auto eol=lf` with `*.skill binary`, so git normalises
  sources to LF on commit but stores the artifact byte-for-byte. Packaging a freshly authored file on
  Windows produced an archive carrying CRs its own committed sources did not have — 424 bytes' worth —
  and **the check CLAUDE.md prescribed passed anyway**, because it runs *before* the normalisation
  that creates the mismatch. The drift then surfaced at release time, where `release.yml` correctly
  refused to publish. `package_core.py` was never at fault; its guarantee was scoped to "a clean
  checkout", and nothing made the checkout clean. It now normalises text members itself, detecting
  binaries git's own way (a NUL byte in the first 8000 bytes) rather than by an extension allowlist —
  an allowlist needs maintaining and **fails open**, so the first type nobody added would silently
  restore the bug. Proven behaviour-preserving rather than asserted: all four `.skill` files rebuild
  byte-identical to the previous release, and the original failure was then reproduced end to end
  (39 sources CRLF-ified) with every artifact still byte-identical. `--selftest` carries 11
  assertions, including a NUL-bearing fixture with `\r\n` inside that naive normalisation would
  corrupt.
- Third instance this week of the same class — **a guarantee that only holds if you remember
  something** (`--check || echo`, a README-mandated flag the code left optional, and now the
  packaging check). Each has been moved into a deterministic layer, which is the class the
  `code-review` skill shipped in v1.23.0 exists to name.

### 2026-07-29 (release v1.23.0)
- **The doctrine's *effect* is now measurable, not just its content** (#156, maintainer tooling —
  not distributed). This repo has always had a hard gate on doctrine *content*: nothing is edited
  until `doctrine-verifier` confirms it against an authoritative source. It had **no** gate on
  doctrine *effect* — "the rails-8 skill produces better Rails" lived entirely in prose, the one
  layer this repo otherwise refuses to trust. New `evals/` measures whether loading the skills
  changes what an agent writes: three arms (no skill / a deliberately weak control / real
  rails-stack) × five cases × six deterministic gates that each cite the doctrine `file:line` they
  enforce. The runner drives `claude -p` rather than the Anthropic API, because these skills ship
  as **Claude Code plugins** — a pasted system prompt would measure a proxy, and a benchmark that
  measures a proxy repeats the mistake it exists to correct. Side effect worth having: no API
  dependency, so the harness stays stdlib-only with nothing for CI to install.
  Authoring the gates caught **two rules in the issue's own spec that would have manufactured
  false regressions** — an "ids-only" job gate that fails our own reference example, and a no-hex
  rule that flags our own `Ui::Logo`. Generalised into a standing rule the selftest asserts: *a
  gate must pass against the doctrine's own reference examples; if it fails what `references/*.md`
  shows as correct, the rule is wrong, not the doctrine.* No paid benchmark has been run and the
  results table is deliberately empty — a harness with proven gates and no numbers is honest.
- **The reviewer moved in-repo, and stopped being rented** (#162, rails-stack → 1.12.0,
  rails-flow → 1.9.0). A trial reviewer had been catching a class our own review missed, and it
  had no proprietary advantage: **it checked the diff against rules already written in this
  codebase's markdown.** Every existing dimension asks *"is this code correct?"*; the misses all
  came from a different question — *"does this code do what its own documentation, config, comments
  and project rules claim?"* Correct-looking code passes the first and fails the second, and the
  author cannot see it because they read the claim and the code as one intention.
  New **`code-review` skill** (bundled in rails-stack, now four skills) names the classes:
  `claims-vs-enforcement`, `dead-declaration`, `carve-out-without-negative-test`, `coverage-gap`,
  `doctrine-contradiction`, `unverified-negative`, `gate-that-cannot-fail`. It lives in `skills/`
  rather than `docs/` deliberately — rules a reviewer must find belong where reviewers look, and as
  shipped doctrine it is the same rule set a user's `pr-reviewer` applies, so we are held to what
  we sell. `code-reviewer` and `pr-reviewer` delegate to it instead of restating it.
- **A doctrine contradiction was live in users' hands, in three files** (#162). `pr-reviewer` told
  the merge gate to demand ids-only job arguments, `rails-developer` said "pass IDs, never AR
  objects", and `setup-flow` wrote that rule into the user's own generated CLAUDE.md — while
  `jobs-and-realtime.md:28` says pass records. **The shipped merge gate would have blocked a PR for
  correctly following our own doctrine**, and setup-flow propagated the wrong rule into the user's
  rules file for the gate to then enforce against them: self-reinforcing, and worse than a plain
  bug because it blames the user. Found by applying the new skill's `doctrine-contradiction` class
  with one grep — that class travels in groups, because the wrong rule gets copied. `skills/rails-8`
  is unchanged; the plugin text now defers to it rather than paraphrasing the mechanism.
- **`claims-vs-enforcement` is now enforced, in both repos** (#162 maintainer, #164
  rails-flow → 1.9.0). It had bitten three times in three PRs — `--check || echo` making a release
  gate unable to block, a README mandating a flag the code left optional, a docstring promising
  behaviour the code lacked. Writing the rule down does not prevent it, which is the whole reason
  `lint_markdown_shell.py` exists. Two linters now: maintainer-side
  `scripts/lint_self_consistency.py` (`dead-settings-key`, `unenforced-mandatory-flag`), and — the
  half users were missing — `rails-flow/scripts/self_consistency.py` with a PostToolUse hook,
  covering `swallowed-exception`, `swallowed-verdict`, `assertion-free-spec` and `dead-env-var`.
  Both are stdlib-only, print coverage even when clean (because "no findings" over input never read
  reads as a pass), and ship a selftest proving every rule fires **and stays silent** — a rule that
  flags everything gets disabled and then catches nothing. The maintainer linter is known-answer
  calibrated: it independently reproduces two of five prior review findings on the pre-fix commit
  and goes silent on the fixed one with the same inputs examined. The hook exits non-zero
  deliberately: a check that can only advise is itself a `gate-that-cannot-fail`.
  Two candidate rules were **cut rather than softened** — proving no spec covers a carve-out's
  near-miss needs judgement, and a rule that guesses gets disabled.
- Promotions are now named in two steps (`chore/arm-vX.Y.Z` → `dev`, then `dev` → `main`), with
  only the second publishing, and it is recorded that **a merge unions rather than overrides** — so
  a direct commit to `main` is permanently invisible to every future `dev`-based change (#155).

### 2026-07-29 (release v1.22.0)
- **Brand packs — the design system becomes multi-brand** (#104, rails-stack → 1.11.0,
  design-flow → 1.4.0). A pack is a **theme, not a fork**: it declares colours, the logo, and the
  chart-palette validation result, and inherits layout, components, spacing, a11y and interactions
  unchanged — so client work reuses the system instead of forking it. Two levels, pack then
  variant: `fmworkflows` is a **variant** of the `fidara` pack, not a pack of its own, because a
  product uses its parent's design system and a variant carries no values it could drift with.
  Primitives are private to a pack; the role layer is the public API, which is what makes a brand
  swap one `@theme` layer. Overrides (`fonts`, the three personality knobs, `chart_hues`) are a
  rare escape hatch, so a typical client manifest is four lines.
  New `brand_pack_lint.py` enforces the 22-role contract mechanically — a missing role does not
  error at runtime, it silently renders a stock Tailwind colour. Ships `brands/fidara` and a
  `brands/_template` client skeleton. Fixed a latent bug the old two-value enum was hiding: the
  endorsement sat on the *parent*, rendering "Fidara by Fidara"; it now belongs to the product
  variant as a string, so no brand name appears in component code.
- **The release drift check actually blocks** (#151, pipeline → 1.1.4, rails-flow → 1.8.0).
  v1.21.0 shipped `--check || echo`, which consumed the non-zero exit — a stale architecture graph
  printed a warning and released anyway. Worse than no check, because the message implied the gate
  ran. The three-branch shell guard that replaced it has since been deleted too: `--if-present`
  moves that judgement into tested Python and the doc carries two plain invocations.
  **bash is for commands, Python is for decisions.**
- **The shell inside markdown is now verified** (maintainer tooling, not distributed). `bash -n`
  covered `.sh` files while 194 lines of bash shipped inside 51 fenced blocks — the lines an agent
  runs verbatim in a user's project, and where three of this week's findings lived.
  `scripts/lint_markdown_shell.py` syntax-checks them and flags swallowed verdicts; it reconciles
  coverage on every run and **refuses to report clean when its parser cannot see a block**, after
  the first version silently skipped 11 blocks in 7 files.
- The doctrine gate gained an explicit scope (externally verifiable claims need a CONFIRMED
  verdict; our own architecture needs the maintainer's decision recorded on the issue), and
  promotions now assert no `### Unreleased` heading survives — a stray one means its notes never
  reach the published release.

### 2026-07-27 (release v1.21.0)
- **Local release fallback** (`scripts/release_local.sh`). Shipping depended on a single
  hosted runner, and the doctrine's "do NOT run `gh release` by hand" left no sanctioned path
  when one is unavailable — so the fallback would have been improvised under pressure, which is
  how a release goes out with unverified notes or a missing asset. The script is a deliberate
  mirror of `release.yml`: resolve `metadata.version` -> tag, no-op if the release exists,
  rebuild `dist/` with the canonical builder, **fail on drift**, extract the matching
  `(release vX.Y.Z)` CHANGELOG block, publish every `dist/*.skill` **by glob**.
  It re-asserts what a clean CI checkout gives for free and a laptop does not: clean working
  tree, HEAD on `main`, HEAD == `origin/main` (a tag must never point at a local-only commit).
  `--dry-run` verifies everything and publishes nothing; a real run requires typing the tag.
  Publishing uses the Releases API, which is not metered by Actions minutes, so this works when
  a runner will not start — though Actions is free on public repos, so check that the runner is
  genuinely the problem first.
  Verified: guards fire on a dirty tree / wrong branch / unpushed HEAD; no-op path confirmed
  against the published v1.20.1; drift guard fires both on a changed skill source
  (`M dist/rails-8.skill`) and on an untracked new asset (`?? dist/brand-new.skill`); notes
  extraction pulls the real 11-line v1.20.1 block, stops at the next `###`, and falls back with
  a warning when no block matches. The `gh release create` call itself is exercised only by a
  real promotion — run `--dry-run` first, every time.
  Caught while testing: a hand-typed asset list in the old doctrine named two `.skill` files
  while **three** actually ship, so a hand-cut release would have dropped `fidara-design.skill`.
- **Release notes could leak a neighbouring section** (`release.yml` **and** the new script).
  The awk that extracts release notes started grabbing on ANY line containing
  `(release vX.Y.Z)`, not specifically the `### … (release vX.Y.Z)` heading. Since a CHANGELOG
  entry can legitimately mention another release in prose, an earlier section's bullets could be
  published as this release's notes. Demonstrated, not theorised: with a prose cross-reference
  above the real heading, the old expression emitted two bullets belonging to a *different,
  unreleased* version. Both copies now anchor on `/^### /`. Verified the real v1.20.1 extraction
  is byte-identical before and after (11 lines), so the fix is a tightening, not a behaviour
  change. Found by review on PR #146 — the CHANGELOG already contains 2 non-heading
  `(release v…)` mentions out of 39, so the hazard was live.
- Two portability fixes in the script, also from that review: reject a Python 2 `python` (the
  canonical builder needs 3, and a wrong interpreter yields assets nobody can reproduce), and
  give `mktemp` a template — a bare `mktemp` aborts on BSD/macOS, which is exactly the machine
  a local fallback exists to serve.
- **Living architecture graph** (#141, rails-flow + pipeline). One generated artefact
  set — `docs/architecture/graph.json` + self-contained `index.html` + mermaid `graph.md` — extracted
  by a stdlib-only Python 3 script from routes, `app/**` and `db/schema.rb`, and serving three
  consumers at once: humans, agents (structural context without reading the codebase), and qa-flow
  (reverse-walk `edges` for a computed blast radius, so #134 becomes a consumer rather than a second
  extractor). `flows` — named, ordered request paths — are the part generic code-graph tools do not
  provide.
  Staleness is handled in the deterministic layer, per the harness doctrine: `--check` rebuilds and
  compares a `content_digest` over `{nodes, edges, flows}` (the `dist/` guard's rebuild-and-diff
  shape), regeneration runs at session end and at release, and `--delta` puts the structural change
  into the release notes. The HTML makes **zero external requests** — the maintainer ruling on the
  issue's CDN-vs-self-contained question — verified mechanically and by executing its inlined JS
  against a DOM stub. Skills unchanged, so `dist/` is untouched — `rails-stack` stays 1.10.0.
  Components bumped at this promotion: **rails-flow 1.6.0 → 1.7.0** (new capability),
  **pipeline 1.1.2 → 1.1.3** (guidance), **metadata.version 1.20.1 → 1.21.0** (the tag).
  Ships with the PR #143 review findings already folded into 1.7.0/1.1.3 (flow-identity delta bug,
  the release-command guard, and two accessibility corrections against our own design doctrine) —
  no separate version, because nothing between #143 and this promotion ever reached a user.

### 2026-07-26 (release v1.20.1)
- **README: architecture section + the three-loops diagram.** Documents the harness model and the
  one rule it follows ("put your guarantees in the deterministic layer"), a **mermaid** diagram of
  the BUILD / MEMORY / MAINTAIN loops and how they feed each other, and the agent-topology table
  (sequential / parallel / loop / agent-to-agent) naming where each is already used.
  Also records, with reasoning, the two pieces of agentic infrastructure we **deliberately do not
  adopt** -- a graph database for memory, and an external orchestration runtime -- and the
  alternative that achieves the same "graph engineering" benefits with plain files in git: typed
  findings records with dedupe signatures and `caused_by`/`blocks` edges (#138), declared issue
  edges (#133), and a code graph for derived blast radius (#134). Diagram verified by rendering
  with mermaid-cli. Docs only; `metadata.version` -> 1.20.1.

### 2026-07-25 (release v1.20.0)
- **fidara-design Phase 0 — foundations calibrated** (#93, rails-stack → 1.10.0). New
  `--width-shell` / `--width-prose` / `--space-section(-compact)` tokens + `@utility` recipes; the
  chrome-vs-content type rule (app chrome is `step--1`, prose `step-0` — both corpora are
  `text-sm`-centric ~2.7:1); heading ramp uses the middle steps; control density bound to
  `sm/md/lg` (`md` = `px-3 py-2`/`h-9`); radius + elevation confirmed by measurement and settled;
  and a new hard rule — **never bind markup to a numbered palette step** (measured cost: 20,825
  inline `dark:` classes in the corpora vs zero for our role layer). Rhythm/radius/heading are
  recorded as **per-brand knobs** in brand.md (#104). `metadata.version` → 1.20.0.

### 2026-07-25 (release v1.19.1)
- **RSpec + Tailwind reframed as deliberate choices** (#101, rails-stack → 1.9.1): both kept, but the
  doctrine no longer implies Rails' Minitest default or hand-written CSS are defects — each now states
  *why* we standardize (mechanical gates for RSpec; enforceable consistency for Tailwind) and that an
  existing Minitest/vanilla-CSS project is a Project Override, not something to migrate. Verified
  against 37signals' own apps. `.gitignore` hardened for licensed design references.
  `metadata.version` → 1.19.1.

### 2026-07-25 (release v1.19.0)
- **File-then-fix discipline** (#73, rails-flow → 1.6.0): mid-session defects are FILED as issues
  first, then worked one-at-a-time (`fix.md` Setup + `issues.md` Phase 0 + the CLAUDE.md scaffold
  rule), with a fail-open SessionStart advisory when fix-shaped commits stack on a branch with no
  issue reference. Completes the "defer to the issue-loop, don't improvise" theme (#77, #78).
  `metadata.version` → 1.19.0. Skills unchanged.

### 2026-07-25 (release v1.18.0)
- **Brand mark shipped + enforced** (#75, #74): `Ui::Logo` (Prism mark/lockup, 20px floor, brand
  endorsement toggle) + the named **auth/focused-page** recipe `cover > center > stack`
  (rails-stack → 1.9.0); design-auditor and `/design-flow:audit` gain a **Composition/branding**
  checklist category, and `/design-flow:setup` scaffolds the component (design-flow → 1.3.0). Closes
  the loop where the brand spec and its enforcer both existed but nothing rendered the mark.
  `metadata.version` → 1.18.0.

### 2026-07-25 (release v1.17.0)
- **Economical GitHub CI** (#76): run the full hosted CI only at the `dev → main` gate, not on every
  `feature → dev` PR — local gates + qa-flow already cover that, and full-matrix-on-every-PR exhausts
  Actions minutes (it blocked merges downstream). rails-8 `testing.md` doctrine gains the
  trigger-economy caveat (rails-stack → 1.8.0, doctrine-verified); `/rails-flow:setup-flow` proposes/
  repairs `ci.yml` triggers as an approved diff (rails-flow → 1.5.0); `setup-pipeline` aligns
  (pipeline → 1.1.2). `metadata.version` → 1.17.0.

### 2026-07-25 (release v1.16.2)
- rails-flow **review agents report ALL findings, defer disposition** (#77, rails-flow → 1.4.1):
  the four review/audit agents + `/rails-flow:review` can no longer self-dismiss a finding
  (the pattern that silently dropped two real security findings downstream). Every finding is
  reported, issue-ready; act/defer/accept is the fix-flow's + human's call. `metadata.version` →
  1.16.2.

### 2026-07-25 (release v1.16.1)
- qa-flow **functional-tester git-hygiene fix** (#78, qa-flow → 1.5.1): the agent no longer
  auto-commits/pushes its evidence (it polluted `dev` with 50 files incl. ephemeral
  `.playwright-mcp/`); it now leaves evidence under `qa/manual-tests/` for the coordinator, never
  touches git, and `setup-qa` gitignores `/.playwright-mcp/`. `metadata.version` → 1.16.1.

### 2026-07-24 (release v1.16.0)
- rails-flow **local brain-review cadence nudge** (#65, rails-flow → 1.4.0): SessionStart reminds
  when the maintenance sweep is overdue (7-day default, env-overridable), stamped via
  `docs/brain/.last-review`. Local/offline, reminder-only — the local-first replacement for the
  rejected cloud scheduler. `metadata.version` → 1.16.0. Skills unchanged.

### 2026-07-24 (release v1.15.0)
- qa-flow **`/qa-flow:smoke`** (#64, qa-flow → 1.5.0): a stack-aware launch-&-liveness gate that
  boots the app and confirms key routes respond before deeper QA — closing verify's hand-waved
  "boot the app" Phase 0. Adds an `app:` config block; `verify`/`setup-qa` wired to it. Free,
  stack-agnostic. `metadata.version` → 1.15.0. Skills unchanged.

### 2026-07-24 (release v1.14.0)
- fidara-design **data-visualization layer** (#63, rails-stack → 1.7.0, now 14 references):
  charts/KPIs/dashboards as doctrine — a validated `fm-*`-derived `--color-chart-*` palette
  (adapting Anthropic's `dataviz` method + validator), KPI/chart recipes, and chart a11y
  non-negotiables. design-flow → 1.2.4 (component command routes chart screens through it).
  `metadata.version` → 1.14.0. rails-8/hotwire unchanged.

### 2026-07-23 (release v1.13.1)
- rails-flow → 1.3.1: removed NotebookLM from the brain flow; the `<org>/brain` git repo is the
  single source of truth for the cross-project shared brain (no external synthesis layer).
  `metadata.version` → 1.13.1. No skill content changed.

### 2026-07-23 (release v1.13.0)
- rails-flow → 1.3.0: the brain leveled up — fuller repo-side memory (STATUS / PROGRESS-LOG /
  DECISIONS / HYPOTHESES-with-lifecycle + provenance tags), a weekly maintenance sweep
  (`/rails-flow:brain-review`), and cross-project federation (`/rails-flow:brain-sync`) via a
  shared brain git repo over `gh` — agentic flows in separate repos coordinate without cloning
  each other, with NotebookLM documented as an optional synthesis lens (not the store).
  `metadata.version` → 1.13.0. No skill content changed.

### 2026-07-23 (release v1.12.4)
- fidara-design reference recipes reconciled with the skill's own non-negotiables (#56,
  rails-stack → 1.6.2): radius (`rounded-lg` not `rounded-[12px]`), `focus-visible` rings on
  Modal-close/Alert-dismiss, and a copyable Lucide `with-icon`/1em call site. Doctrine-verified
  (Tailwind v4 radius namespace; CSS-over-SVG-attribute cascade). `metadata.version` → 1.12.4.

### 2026-07-23 (release v1.12.3)
- **Docs fixes from downstream reports (#41, #42).** #41: a rails-8 URL-design `### 1.0.5`
  CHANGELOG entry was misfiled under `## pipeline`; moved to `## rails-stack` in its
  chronological slot, and fixed a self-doubled heading — so downstream changelog readers map
  entries to the right plugin. #42: README now presents the auto-updating `rails-stack`
  **plugin as the recommended team install**, with the `degit`/vendoring path re-badged as a
  fallback for no-plugin environments (stated re-sync trade-off), and clarifies
  `.claude/skills/` is for project-specific skills — removing the "commit the framework skills"
  guidance that made a downstream team hand-sync two copies. Docs only; `metadata.version` →
  1.12.3, no skill/plugin behavior change.

### 2026-07-23 (release v1.12.2)
- **PR-review backlog triaged into fixes.** Read all 132 review comments across every PR
  (qodo / codex / accesslint); codex was rate-limited (no findings) and accesslint's were all
  ERB/placeholder parse artifacts (the worked code is a11y-correct). The credible engineering
  findings were filed (#43–#46) and fixed:
  - **CI (`release.yml`)** #43: drift guard used `git diff --quiet -- dist/` (blind to
    untracked files) — a new skill's uncommitted `dist/*.skill` passed the no-drift guard
    falsely; now `git status --porcelain -- dist/`. #44: the `release` job now gates on
    `github.ref == 'refs/heads/main'` so a `workflow_dispatch` from a non-main ref can't
    publish a release for that ref.
  - **qa-flow → 1.4.1** #45: closed fail-open bypasses in the release-gate promotion detector.
  - **pipeline → 1.1.1** #46: guarded `/pipeline:ack` git-dir resolution + fixed doc drift.
  `metadata.version` → 1.12.2. No skill content changed (skills/dist unchanged).

### 2026-07-23 (release v1.12.1)
- **Design system wired into the feedback loop.** Issue templates (incorrect-doctrine,
  skill-gap, plugin-bug, feature) now offer `fidara-design` / `design-flow`; new
  `comp:fidara-design` + `comp:design-flow` labels; the `issue-triager` taxonomy and the
  shipped reporter (`/rails-flow:report` + `claude-skills-reporter`, rails-flow → 1.2.1) now
  cover them. fidara-design SKILL.md documents the verification boundary and routes breakage
  upstream (rails-stack → 1.6.1); `/design-flow:setup` nudges the same (design-flow → 1.2.3).
  `metadata.version` → 1.12.1. Closes the gap where the least runtime-verified component had
  no path back into the issue inflow.

### 2026-07-23 (release v1.12.0)
- fidara-design: modal-driven in-page CRUD as first-class doctrine (crud-modal-pattern,
  rails-stack → 1.6.0, now 13 references) + verified Tailwind v4 `@utility` fix for custom
  utilities; whole CSS/JS layer build-verified against the real Tailwind v4.3.3 compiler +
  Node. design-flow → 1.2.2 (component command routes CRUD through the modal pattern).
  `metadata.version` → 1.12.0. rails-8/hotwire unchanged.

### 2026-07-23 (release v1.11.0)
- fidara-design full component catalog worked as reference code
  (component-implementations, rails-stack → 1.5.0); design-flow → 1.2.1 (component command
  cites it). `metadata.version` → 1.11.0. rails-8/hotwire unchanged.

### 2026-07-23 (release v1.10.0)
- Mobile Phase 3 (native token export): fidara-design native-tokens (rails-stack → 1.4.0) +
  NEW `/design-flow:tokens` (design-flow → 1.2.0) — generate Android/iOS tokens from the
  `@theme`. Outputs to `tmp/`; native app repos untouched. `metadata.version` → 1.10.0.

### 2026-07-23 (release v1.9.0)
- Mobile Phase 2 (Hotwire Native parity): fidara-design mobile-reference-implementation
  (rails-stack → 1.3.0) + NEW `/design-flow:mobile` (design-flow → 1.1.0). Web-side code only
  (native app repos untouched). `metadata.version` → 1.9.0. rails-8/hotwire unchanged.

### 2026-07-23 (release v1.8.0)
- fidara-design reference-implementation (concrete ViewComponent + Stimulus-mixin code) +
  mobile parity plan (rails-stack → 1.2.0); design-flow → 1.0.1 (setup points at the reference
  impl). Closes the design system's spec-but-no-code gap, all in the marketplace repo (no app
  refactor). `metadata.version` → 1.8.0. rails-8/hotwire unchanged.

### 2026-07-23 (release v1.7.0)
- The Fidara design system lands: NEW `fidara-design` skill (rails-stack → 1.1.0) + NEW
  `design-flow` plugin (1.0.0) — consistent, modern, responsive UI without a designer/Figma,
  grounded in the real Fidara assets + Utopia + Every Layout + a modern-library survey.
  `metadata.version` → 1.7.0. rails-8/hotwire skill content unchanged; a new
  `dist/fidara-design.skill` ships (release workflow now uploads all `dist/*.skill`).

### 2026-07-23 (release v1.6.12)
- qa-flow 1.4.0: `setup-qa` inspects the codebase and proposes a recommended testing stack
  (confirm/override; respects existing tooling) instead of asking cold. `metadata.version`
  → 1.6.12. Skills unchanged.

### 2026-07-23 (release v1.6.11)
- qa-flow 1.3.0: free Allure unified reporting wired across all runners/tiers
  (`reporting: allure|both`; `markdown-csv` remains the default). `metadata.version` →
  1.6.11. Skills unchanged.

### 2026-07-23 (release v1.6.10)
- qa-flow 1.2.0: stack-agnostic QA (qa/qa.config.yml — Playwright/Cypress-Cucumber/
  Selenium-pytest-bdd/Appium, free by default; no forced stack) + Autonoma-inspired free
  patterns (auto-mapped flows, self-adapting locators, PR-native results) + opt-in Testmo
  case-management via config. `metadata.version` → 1.6.10. Skills unchanged.

### 2026-07-23 (release v1.6.9)
- qa-flow 1.1.0: free, repo-local case authoring/management (`/qa-flow:cases`) + agentic
  functional testing via Playwright MCP (`/qa-flow:functional`) — no paid/online tool.
  `metadata.version` → 1.6.9. Skills unchanged.

### 2026-07-23 (release v1.6.8)
- Reverse the v1.6.7 approach: maintainer tooling is now **repo-local `.claude/`**, not a
  separate marketplace. `skill-maintainer`'s commands/agents/hook moved into `.claude/`
  (commands renamed `/maintainer-triage` · `-work` · `-audit` · `-setup-intake`), plus a
  detailed `CLAUDE.md` maintainer guide. This is active for anyone who clones the repo and
  is **never** part of the marketplace install surface — cleaner than a second marketplace,
  and no install step. The `fmanimashaun/claude-skills-maintainers` repo created in v1.6.7
  was **deleted**. Marketplace unchanged (still the 4 app plugins). `metadata.version` →
  1.6.8. Skills unchanged.

### 2026-07-23 (release v1.6.7)
- Full separation for #4: `skill-maintainer` **extracted to a separate marketplace**,
  [`fmanimashaun/claude-skills-maintainers`](https://github.com/fmanimashaun/claude-skills-maintainers),
  and removed from this marketplace's manifest (now 4 app plugins). App builders adding
  `fmanimashaun/claude-skills` no longer see it at all; maintainers add the separate
  marketplace explicitly. README + repository layout updated. `metadata.version` → 1.6.7.
  Skills unchanged.

### 2026-07-23 (release v1.6.6)
- Three issues shipped since v1.6.3 (one consolidated dev→main promotion, tagged v1.6.6):
  - skill-maintainer 1.0.1 — #4 maintainer-only separation (manifest marker + command
    repo-type guards + README consistency). *(Superseded by the full extraction in v1.6.7.)*
  - rails-flow 1.2.0 — #2 claude-skills-reporter agent + `/rails-flow:report` (feedback-loop
    sending end).
  - pipeline 1.1.0 — #5 `/pipeline:ack` + auto-clear for the QA-verify nudge marker.
  `metadata.version` → 1.6.6. Skills unchanged. (No v1.6.4/v1.6.5 tags exist — those interim
  bumps were folded into this single release.)

### 2026-07-23 (release v1.6.3)
- Release flow is now automated via GitHub Actions (`.github/workflows/release.yml`):
  a `dev → main` merge (push to main) reads `metadata.version`, and if that tag doesn't
  exist, builds the `.skill` assets with the canonical `package_core.py` and publishes
  the GitHub Release — no manual `gh release`. Version-unchanged pushes are no-ops (tag
  exists). Includes a dist-drift guard (fails the release if committed `dist/` isn't a
  clean build) and pulls notes from this CHANGELOG's `(release vX.Y.Z)` block. Skills
  unchanged; `metadata.version` → 1.6.3.

### 2026-07-23 (release v1.6.2)
- Adopted a proper git flow: `dev` integration branch (now default) → `fix/*` and
  `feature/*` branch off dev, PR into dev; `dev → main` PR cuts the release. Aligns the
  repo with qa-flow/pipeline's own dev→main doctrine.
- qa-flow 1.0.6 closes the #1 heredoc residual; `.env` gitignored (token safety).
  `metadata.version` → 1.6.2. Skills unchanged.

### 2026-07-23 (release v1.6.1)
- First issue shipped through skill-maintainer: qa-flow 1.0.5 fixes #1 (release-gate
  substring false-positive). `metadata.version` → 1.6.1. Skills unchanged.

### 2026-07-23 (release v1.6.0)
- Fifth plugin `skill-maintainer` added and registered in `marketplace.json`;
  `metadata.version` → 1.6.0. Issue intake scaffolded into `.github/` (templates +
  label taxonomy). Skills unchanged — `.skill` assets carry over from v1.5.0.

### 2026-07-22 — truly reproducible packaging (ZIP_STORED)
- `package_core.py` now STOREs entries (no DEFLATE): output no longer depends
  on the zlib implementation — the v1.2.2 caveat (stock zlib vs zlib-ng) is
  closed by construction, and `create_system` is pinned (its default differs
  Windows vs Unix). A clean checkout now builds byte-identical `.skill`
  artifacts on any machine, Python, or OS. Canon bytes change one final time;
  larger uncompressed assets are the accepted cost of reproducibility.

### 2026-07-22 (release v1.2.2)
- Fix `package.ps1` on Windows: the launcher test matched `python.exe` (glob
  `py*`) and passed `-3`, which non-launcher Python executables reject
  (`Unknown option: -3`). Now only the real `py`/`py.exe` launcher gets `-3`.
- Correct the determinism claim (see the entry below): `package_core.py` output
  is byte-stable per zlib/DEFLATE implementation, but compressed bytes differ
  across zlib versions (stock zlib vs zlib-ng produce different output) — the
  archive *contents* are always identical. So a clean rebuild reproduces the
  committed dist only on a matching zlib; the per-release content-normalization
  is retired, but cross-zlib byte-identity is not guaranteed.
- No skill content change; `dist/*.skill` shipped as previously committed.
- `metadata.version` → 1.2.2; released as tag `v1.2.2`.

### 2026-07-22 — deterministic skill packaging
- `scripts/package_core.py` is now the single canonical `.skill` builder:
  fixed timestamps, sorted entries, deflate 9 — byte-identical output on any
  machine. `package.sh` / `package.ps1` became thin wrappers; automated
  rebuilds use the same script. Canon bytes change ONCE with this commit;
  thereafter the committed dist binaries equal any clean rebuild and the
  per-release normalization step is retired.

### 2026-07-22 (release v1.2.1)
- `metadata.version` → 1.2.1, rails-flow → 1.1.0, rails-stack → 1.0.3; released
  as tag `v1.2.1`.
- `dist/rails-8.skill` repackaged (new `references/sso.md`, jobs-and-realtime §7);
  18 entries. Normalized to the canonical `package.*` build (84,598 vs a
  non-canonical 84,730 rebuild — content identical). `hotwire.skill` unchanged.

### 2026-07-21 (release v1.1.8)
- `metadata.version` → 1.1.8, rails-flow → 1.0.8; released as tag `v1.1.8`.
- `dist/rails-8.skill` normalized back to the canonical `package.*` build: a
  prior non-canonical rebuild had diverged in bytes only (78,809 vs 78,675),
  content identical and matching the v1.1.7 asset. Reproducibility restored
  (checkout + `package` now reproduces the committed artifact).

### 2026-07-21
- rails-stack entry now carries an explicit `version` in `marketplace.json`
  (entry-declared plugins accept manifest fields), giving skills the same
  cache-key discipline as rails-flow.
- This CHANGELOG added; supersedes `metadata.version` as the human-readable
  history (that field is not consumed by Claude Code).

### 2026-07-20
- Repository published: skills, `dist/*.skill` packages for claude.ai upload,
  bash + PowerShell installers, README.
- Plugin marketplace manifest added (`/plugin marketplace add
  fmanimashaun/claude-skills`); rails-flow joins as second plugin.
- README grew into the single source of truth: install methods, the agentic
  flow, autonomy, the phased code-review install-and-verify runbook, graphify.
- Releases: v1.0 (skills), v1.1.3, v1.1.4 (post-LF-normalization).
- `.gitattributes` (LF everywhere, binaries marked).
