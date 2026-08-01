# Changelog

All notable changes to this repository. Components version independently:
**rails-flow** (version in `plugins/rails-flow/.claude-plugin/plugin.json`),
**rails-stack** (version in its `marketplace.json` entry), and repository-level
changes (README, packaging, infrastructure). Every version bump gets an entry here.

## Repository hygiene

### Unreleased

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
  no findings" instead of erroring; and `verify` matched inside `pipeline-verify`, flagging an
  idempotent `docker rm … || true`. Worth recording that three separate escaping mistakes wrote
  literal control characters (``, TAB) into the source via heredoc patching — invisible in
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
  (`grep -rnE "(form_with|form_for)"`), verified against a fixture containing one correct
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

### Unreleased

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
  rails-8 at 227). Verified by running the gate, not by reading.

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

### Unreleased

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

### Unreleased

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
