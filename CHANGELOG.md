# Changelog

All notable changes to this repository. Components version independently:
**rails-flow** (version in `plugins/rails-flow/.claude-plugin/plugin.json`),
**rails-stack** (version in its `marketplace.json` entry), and repository-level
changes (README, packaging, infrastructure). Every version bump gets an entry here.

## Repository hygiene

### Unreleased

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
