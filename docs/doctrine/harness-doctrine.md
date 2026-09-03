# Harness doctrine — put your guarantees in the deterministic layer

> **Change type:** design / architecture. This is our own decision about where guarantees live; no
> upstream exists to cite, so the authority is the maintainer decision recorded on
> [#132](https://github.com/fmanimashaun/claude-skills/issues/132). Nothing here asserts how Rails,
> Hotwire, Tailwind or any gem behaves.

A *harness* is the scaffolding around a model: the loop, the tools it may call, the context assembled
for it, how its output is verified, and when it must stop. This repo has been building one all along
and following one rule implicitly. Written down, the rule is:

> **Put your guarantees in the deterministic layer.**
>
> Hooks, scripts and gates execute identically every time. A model does not. Anything that must
> *always* happen belongs in a hook or a script; prose can only advise.

Unwritten, that rule was tribal knowledge — easy to violate the next time someone adds a plugin, and
impossible for a contributor to apply. This document is that rule, plus the corrections the repo's own
history forces on it — chiefly that moving a rule into a script is where the work *starts*, not where
it finishes (§4).

---

## 1. The test: guarantee, or advice?

Ask of every rule you are about to write:

> **If a model ignores this, what happens?**

- **Nothing happens** → it is *advice*. Prose is the right home. Label it advice, so nobody assumes
  enforcement that does not exist.
- **Something stops** → it is a *guarantee*. Name the thing that stops it, in the same breath.

The defect this prevents is not "the rule was wrong". It is someone reading a preference as a
guarantee. `skills/code-review/SKILL.md` names that class first, as
[`claims-vs-enforcement`](../skills/code-review/SKILL.md) — *a guarantee stated in prose that nothing
makes true* — and calls it the class an author is structurally blind to, because the author read the
claim and the code as one intention.

### Three tiers, weakest to strongest

| Tier | Where it lives | What it does | How it fails |
|---|---|---|---|
| **1 — Prose** | `SKILL.md`, `CLAUDE.md`, command bodies | Advises. Shapes the default behaviour of a model that reads it. | Silently. A model may read it, agree with it, and not do it. No trace. |
| **2 — Output contract** | An agent's stated deliverable — *"report every finding, `file:line`, severity, no disposition"* | Makes the omission visible: a missing field is legible in the output itself. | When nobody reads the output against the contract. It is still prose; it just fails *loudly*. |
| **3 — Deterministic** | Hook, script, gate, CI step | Executes identically every time, whatever the model decided. | Only in ways you can reproduce and test — see §4, because this is where it gets interesting. |

Tier 2 is a real improvement over tier 1 and it is not tier 3. Do not describe it as enforcement.

---

## 2. Evidence: where prose alone did not hold

Three shipped failures. Each is a real report from a downstream project, not a hypothetical.

### #77 — `security-auditor` self-dismissed two real security findings

During a security-audit pass it found a sign-in grant token travelling in the URL and an
unauthenticated state-changing GET / login-CSRF shape, and labelled them *"accepted residual (no new
action needed)"* and *"awareness-only"*. Neither was surfaced as a tracked issue. They were filed only
after the founder said, explicitly, *file anything you see no matter how small*. The same
verdict-bundling appeared in the `design-auditor` pass. **The flow needed a human to re-impose "report
everything"; it should have defaulted to it.**

The fix landed at **tier 2**: all four review agents and the `/rails-flow:review` synthesis step now
carry an output contract that mandates completeness and forbids disposition —
`plugins/rails-flow/agents/security-auditor.md:36-42`, *"You do **NOT** decide disposition … a
residual is still REPORTED, as a low-severity finding."*

**Nothing mechanical checks that clause is present, or obeyed.** Verified, not assumed:

```bash
grep -rn "disposition" scripts/ plugins/*/scripts/ evals/*.py
```

returns nothing. There is no gate that would notice if the clause were deleted from one of the four
agents, and none that can tell whether a run honoured it. That is recorded here so that nobody reads
#77 as closed-and-enforced. It is closed-and-contracted.

### #78 — `functional-tester` committed 50 files to `dev` against an explicit "no code changes"

The invoking prompt said *no code changes* and asked only for a report written into
`qa/manual-tests/`. The agent committed **50 files, 597 insertions** — about 35 of them ephemeral
`.playwright-mcp/` console logs and page-snapshot `.yml`s — to whichever branch was checked out, which
was `dev`, and it reached `origin/dev` without review. History rewrite was impossible (force-push to
`dev` is hook-blocked), so it had to be fixed forward.

The fix is **split across two tiers, and the split is the lesson**:

- **Tier 3.** `/qa-flow:setup-qa` now writes `/.playwright-mcp/` into the project's `.gitignore`
  (`plugins/qa-flow/commands/setup-qa.md:164`). That part cannot be ignored by a model. It is a
  guarantee about *that directory*.
- **Tier 1.** *"No `git add` / `commit` / `push` — ever … never push to a shared branch"* is prose in
  `plugins/qa-flow/agents/functional-tester.md:364-367`.

The prose half is the half that was violated in the first place, and it is still prose. Measured
against the only relevant guard — `plugins/rails-flow/hooks/scripts/guard-bash.sh`, a `PreToolUse`
hook that blocks `db:reset`, force-push, `git add -A` / `git add .`, `--no-verify`, `git reset --hard`
and un-approved `kamal deploy` — a plain push to a shared branch is **not** blocked. Fed
`{"tool_input":{"command":"git push origin dev"}}` on stdin, it exits `0`.

Two details of that guard are worth copying rather than relearning, both confirmed by running it:

- It degrades toward blocking. Its `python3` extraction falls back to grepping the raw hook payload
  (`… || printf '%s' "$input"`), so with `python3` unavailable a force-push and a `git add -A` are
  **still** refused with exit 2.
- It refuses commands, not intentions. Everything it blocks is a literal shape in a command line.
  "Do not pollute a shared branch" is not such a shape, which is exactly why it is still prose.

### #56 — a skill's non-negotiables contradicted by the skill's own reference recipes

`design-system/SKILL.md` stated three hard non-negotiables. The worked recipes in its own
`references/component-implementations.md` contradicted all three: `rounded-[12px]` where the radius
token vocabulary already had `rounded-lg`; two icon-only dismiss controls shipping `sr-only` labels but
no `focus-visible` ring, in the same file where the Button and Input recipes carry one; and
`1em`/`with-icon` sizing that the doctrine mandated, that the CSS utility provided, and that **no
recipe ever assembled**, so an implementer following the doctrine literally had nothing to copy and
reached for the gem's 20px pixel default instead. `/design-flow:setup` copies those recipes verbatim,
so the contradiction shipped byte-for-byte into a downstream app.

**#132 says all three failures were "an agent ignoring text". For #56 that is not the mechanism, and
the correction changes the remedy.** No agent defied a rule at run time here. Two authored artefacts
disagreed, and nothing had ever compared them. The generalisable rule is sharper than
"agents ignore text":

> **Where a prose rule and a copyable example disagree, the example wins.** The example is the thing
> that gets pasted.

So the remedy for #77 and #78 is *enforcement*, and the remedy for #56 is a *cross-check between two
things we wrote*. Those are different pieces of work, and only one of them exists.
`plugins/design-flow/scripts/setup_doctrine_crosscheck.py` is a cross-check of that family but a
different class — it catches doctrine depending on a `Rails.configuration.x.<key>` the generator never
produces (#150/#104). Nothing compares a skill's stated non-negotiables against its own reference
recipes:

```bash
grep -rn "non-negotiable" scripts/ plugins/*/scripts/
```

finds no check. **#56's class is still prose-only.** That is a gap, stated as a gap.

---

## 3. Evidence: where determinism held

Each of these executes without a model's cooperation. Named with what it blocks, so the claim is
checkable rather than atmospheric.

| Mechanism | Kind | What it actually does |
|---|---|---|
| `plugins/rails-flow/hooks/scripts/stop-gate.sh` | `Stop` hook, blocking | Exit 2 when `app/`/`lib/` Ruby changed with no `spec/**/*_spec.rb` change; when a `feature/*`/`fix/*` branch has app changes and no `docs/acceptance/<slug>.md`; or when the changed specs are red. |
| `plugins/qa-flow/hooks/scripts/release-gate.sh` | `PreToolUse[Bash]`, blocking | Exit 2 on a `dev → main` promotion unless `qa/CERTIFICATION` exists, its verdict is `PASS`, and its `sha` still matches `origin/dev`. Normalises the command first, so a promotion hidden in a heredoc or behind `git -C` is still caught. |
| `plugins/rails-flow/hooks/scripts/guard-bash.sh` | `PreToolUse[Bash]`, blocking | The literal command shapes listed in §2 above. |
| `.github/workflows/release.yml` (drift guard) | CI step, blocking | Rebuilds `dist/` with `package_core.py` and fails the release if `git status --porcelain -- dist/` is non-empty — deliberately `status`, not `diff --quiet`, so a **new** skill whose artifact was never committed also trips it. |
| SessionStart hooks (`session-start.sh`, `maintainer-status.sh`, `qa-status.sh`, `pipeline-status.sh`) | Context injection, non-blocking | Put branch, dirty count, last commit, brain STATUS, open-issue counts and cadence nudges in front of the model without it having to go looking. |

## 4. The correction that matters most: a deterministic gate is *necessary, not sufficient*

The naive reading of §1 is that moving a rule into a script makes it true. The repo's own history
refutes that — once in the gate this repo cites most, and four more times in a single day.

**The Stop gate ran every time and did not hold.** `stop-gate.sh:24` records why: plain
`git status --porcelain` **collapses a new untracked directory** to `?? app/`, so
`app/models/invoice.rb` in a brand-new folder was invisible to the gate and behavioural code could
finish with no spec at all. The fix is `-uall`. It was found by *behaviour-testing the gate* while
implementing #125 — not by reading it, and not by the gate itself. The same collapse is called out
again in `scripts/maintainer_doctor.py`, because it is a trap that generalises.

**And on 2026-07-31, four separate instances of the same shape, all inside the deterministic layer:**

| # | What happened | Why it is the same shape |
|---|---|---|
| 1 | **A gate wrote into the working tree.** `issue_graph.py`'s selftest created `scripts/.issue_graph_selftest.json` and unlinked it in a `finally`. `maintainer_doctor.py` runs that selftest *as a gate*. | A diagnostic that mutates its subject is not a diagnostic. It also fails on a read-only checkout and races two concurrent runs on one fixed filename. `mutation_check.py`'s own docstring had already recorded this lesson — *"one interrupted process away from leaving a mutated repo"* — which is what makes it worth writing twice. |
| 2 | **A selftest no gate ran.** `maintainer_doctor.py --gates` silently omitted selftests; a newly added one passed locally while the sweep never executed it. On the rule's first run it found a second omission: the doctor was not running **its own** selftest either. | A check that is not reachable from the sweep is indistinguishable from a check that does not exist — and the sweep reports a clean machine. |
| 3 | **An interpreter stall reported as a syntax error.** `subprocess.TimeoutExpired` is a *subclass* of `SubprocessError`, so one `except (OSError, subprocess.SubprocessError)` swallowed a stall into the same path as *"interpreter missing"*, and it emerged as *"did not parse in any documented context"* — an environment stall presented as a code defect, non-deterministically and only under load. | The gate ran, exited, and printed a verdict that was not the truth. In someone's diff it would have read as a real finding. |
| 4 | **Mutation coverage could not see a new rule inside an existing guard.** The gate asserted every *guard* declares mutations. `lint_self_consistency` already declared twelve, so a new rule added to it sailed through green with no mutation behind it. Checked structurally per rule, it immediately found a genuine pre-existing hole: the **two original rules** had fixtures but had never had mutations, from the day `mutation_check.py` was written. | A guard-level count is blind to a rule-level gap. The gate was green over input it had not really examined. |

One shape, four times: **a check existed, ran, and reported a verdict that was not the truth.**
Determinism buys you repeatability, not correctness. A gate you have never seen fail is not known to
work — which is what the next section is for.

### The ladder: what turns a check into a guarantee

Every rung exists because it was skipped once, and the omission shipped.

1. **The rule is mechanical, not prose.** §1.
2. **It ships with a `--selftest` that proves it fires *and* stays silent.** A rule with only positive
   fixtures is untested in the direction that produces false positives, and a linter that cries wolf
   gets switched off and then catches nothing.
3. **A declared mutation in `scripts/mutations/<guard>.py` proves the selftest can fail.** Break the
   subject on purpose; watch the selftest go red. Declared per **rule**, not per guard — instance 4
   above.
4. **It is registered in `maintainer_doctor.py`'s `GATES`**, so it runs without anyone remembering it.
   `maintainer_doctor_selftest.py` asserts that **every `*_selftest.py` in the repo is reachable from
   `GATES`** — instance 2 above is why.
5. **It reports three states.** `ok` is verified, `FAIL` blocks, and **`skip` means the check did not
   run — it is not a pass.** A gate that fails open while exiting 0 turns the whole sweep green: that
   is a live bug this repo has had twice, once when `lint_markdown_code.py` printed a SKIP notice and
   exited 0 while 242 of 276 blocks went unchecked, and once when a selftest printed "35 checks
   passed" on a machine where two checks against the real repo silently did nothing.
6. **It does not mutate what it inspects.** Instance 1 above.

Read the gate list from `GATES` in `scripts/maintainer_doctor.py` rather than from a number written
here — the file is the enumeration, and rung 4 is what keeps it complete. A count in prose is a claim
that rots; a pointer to the source is not.

---

## 5. Fail closed for gates, fail open for advisories

The one-line version is in the heading. The precise version has three distinct roles in it —
**advisory**, **gate**, and **guard** — and they are not interchangeable.

- **An advisory must never block.** `.claude/hooks/scripts/maintainer-status.sh:3` — *"Read-only,
  non-blocking; fails OPEN (exit 0) whenever a dependency or precondition is missing — a status hook
  must never block a session."* It exits 0 when there is no git repo, no `marketplace.json`, no `gh`,
  or no `gh auth`. A nudge that can stop work is a nudge people uninstall.
- **A gate must not be silently disabled by a missing dependency.**
  `plugins/qa-flow/hooks/scripts/release-gate.sh:6` — *"BLOCKING gate → fail CLOSED if it's
  missing"*. With no `python3` it cannot verify certification, so it refuses, with an explicit named
  override (`QA_ALLOW_MAIN=1`, which announces itself as audited).
- **Fail closed is *scoped to what the gate guards*, never blanket.** The same script fails closed
  only when the command looks like a main-ward promotion, and exits 0 otherwise. This is the part
  that is easy to get wrong: a gate that fails closed on unrelated work is a gate people disable, and
  a disabled gate protects nothing. Match narrowly, then be absolute inside the match.
- **A guard decides whether to *run* a check; it must never *soften the verdict*.**
  `stop-gate.sh:70` — *"a missing `python3` skips (fails open) while a real finding blocks (fails
  closed)"*. The anti-pattern is a verdict consumed by its own fallback, which
  `scripts/lint_markdown_shell.py` now detects as `swallowed-verdict` because a release gate once
  shipped a stale artifact that way.
- **Where a dependency is absent *by design*, the absence is a `skip` — not a FAIL and not a pass.**
  The licensed corpora are optional, so `CORPORA_GATES` in `maintainer_doctor.py` exempts exactly the
  gate that cannot run without them, **keyed by gate name**, and the doctor's selftest asserts every
  name in that set exists in `GATES` — otherwise a rename would silently widen the exemption.

### One discrepancy, recorded rather than papered over

`CLAUDE.md` states this flatly, in *Platform*: **"Hooks fail open when a dependency is missing."**
Measured against every hook in the repo, it holds for seven and is **false for two**:

- **Holds** — the four SessionStart hooks (`session-start.sh`, `maintainer-status.sh`,
  `qa-status.sh`, `pipeline-status.sh`); the two PostToolUse hooks, which exit 0 outright on a
  missing dependency (`lint-ruby.sh:12` on `bundle`, `self-consistency.sh:24` on `python3`); and
  `stop-gate.sh`, whose *guard* skips without `python3` while its verdict still blocks.
- **False** — `release-gate.sh`, which fails **closed** on a promotion with no `python3`,
  deliberately and per its own header comment. And `guard-bash.sh`, which is not disabled by a
  missing `python3` either: its extraction falls back to the raw payload, so the blocks still fire
  (measured in §2). That one is an emergent property of the fallback rather than a stated intent —
  the script says nothing about it — which is worth knowing before anyone "tidies" the fallback away.

The precise rule is the five bullets above; the `CLAUDE.md` sentence needs narrowing to advisory
hooks. It is stated here because `CLAUDE.md` is outside this change's lane, not because the
discrepancy is acceptable. `docs/doctrine/issue-dependency-graph.md` had already noticed the same gap from the
other side, recording the fail-closed/fail-open rule as one tool's local contract precisely because
nothing carried it generally.

---

## 6. Verification lives outside the agent's own judgement

*"The agent says it works"* is not verification. The proof has to be an artefact someone else can
check: a spec, a gate, a separate reviewing plugin, or an acceptance criterion agreed **in advance**.

The advance part is load-bearing, and it is shipped (#125). `stop-gate.sh` blocks a `feature/*` or
`fix/*` branch whose `app/`/`lib/` Ruby changed with no `docs/acceptance/<slug>.md`, then validates
that file with `plugins/rails-flow/scripts/check_criteria.py`, which is itself a gate
(`acceptance criteria` in `GATES`). The gate's own comment says why the ordering matters:

> The checks below prove "the new behaviour has a spec". They fire after code exists, so they cannot
> tell whether the spec asserts what was REQUIRED or merely what the code happens to do. A goal
> written after the result is unfalsifiable — the same defect class as a gate that cannot fail, moved
> from the gate to the goal.

That last clause is the general form. **A gate that cannot fail and a goal written after the result
are the same defect wearing different clothes**, and moving one into the other is not progress. It is
also why delegating execution to a cheaper model tier is only safe once criteria exist: the proof has
to be external to whoever is being cheap.

Note the scoping, which follows §5: the criteria requirement fires only on the flow's own branch
names. Demanding a `docs/acceptance/` file on every branch would break ad-hoc work that never entered
the flow — and "criteria before implementation" is a promise the flow made, not a rule about all Ruby
edits.

---

## 7. Context is assembled, not hoped for

State what a model is *given* for a task. Do not rely on it going to find things.

What exists: the SessionStart hooks in §3. `session-start.sh` injects branch, base, uncommitted-file
count, last commit, the top of `docs/brain/STATUS.md`, the `MEMORY.md` index, a brain-review cadence
nudge, and an issue→fix discipline advisory. `maintainer-status.sh` injects the open-issue count, the
P1 count and the `type:incorrect-doctrine` count. Both are stdout-becomes-context, both fail open.

**The self-contained work order now exists.** [#127](https://github.com/fmanimashaun/claude-skills/issues/127)
asked for a per-unit file — goal, acceptance criteria, files in and explicitly out of scope,
applicable guardrails, stop conditions, how to verify — so that execution does not depend on
conversation state. `/rails-flow:handoff` writes `docs/handoff/<slug>.md` (per unit, **not** a root
`HANDOFF.md`: concurrent branches each have one, and a single root file conflicts on every merge),
and `check_handoff.py` rejects one that points at the conversation, leaves a `<placeholder>`, or
restates a criterion instead of citing its id. This paragraph read *"#127 is open. Nothing in the
repo assembles that today"* until #128's second half was worked and someone re-read it — a stale
gap-claim is as misleading as a stale guarantee, and it survives longer because nobody re-checks
good news.

---

## 8. Stop conditions are part of the harness

An agent that cannot make progress but keeps trying digs a deeper hole — reverting its own fixes,
loosening tests to make them pass, widening scope to route around a blocker — and every one of those
looks like activity in a log.

**The oldest stop condition here is deterministic and tiny.** `stop-gate.sh` reads
`stop_hook_active` from its own payload and exits 0 if it is already true, so the gate blocks **once**
and can never loop. For a long time that was the whole of it, and
[#128](https://github.com/fmanimashaun/claude-skills/issues/128) recorded the rest as a gap: an
attempt cap, a no-progress detector keyed on an unchanging failure signature, enumerated forbidden
escapes, a blast-radius cap, budgets, escalate-and-continue, and a final report that distinguishes
complete from partial from stopped. This section used to say a grep for
`circuit.?breaker|stop condition|max attempts|bail out` across `plugins/` and `skills/` *"still
returns none"*. **Re-run it: it returns 26 hits in five files.** The claim was true when written and
went stale the day the first half shipped, which is why the row in §11 says to re-run the grep rather
than to trust the sentence.

It shipped in two halves, and they are deliberately different shapes because the two plugins fail
differently:

- **rails-flow — a checked artefact.** The stop conditions are a required section of the work order
  `/rails-flow:handoff` writes, and `check_handoff.py` rejects one that states no **number**: "stop
  when you are stuck" cannot be evaluated by the thing that is stuck. All four escapes are checked
  individually.
- **pipeline — a run ledger and a breaker.** A pipeline has no work order; it has a gated chain of
  stages, sometimes unattended, whose most autonomous agent deploys to production and was told to
  *"troubleshoot autonomously"* and *"re-run idempotently"* with no bound at all.
  `plugins/pipeline/scripts/breaker.py` opens a run against `pipeline/run-ledger.jsonl` — append-only
  JSONL, committed, so §9's *if you cannot diff it, you cannot gate it* holds — and answers one
  question per stage: may this be attempted now? The limits are recorded once at `start` and `check`
  takes no threshold flags, so a run cannot widen its own cap halfway through.

Three things about that second half are worth keeping when it is next edited:

- **Two of #128's four escapes became mechanical here, and two did not.** Gate-skipping is decidable
  from the ledger (`out-of-order`), and so is re-running work that already passed. Weakening a test
  and disabling a guardrail involve file edits the breaker cannot see, so they stay doctrine in
  `reference/stop-conditions.md` — and `breaker.py --selftest` asserts that file still enumerates all
  four with the strings the script declares, so the two cannot drift apart. Naming which half is
  enforced is the point; a table that lists four and enforces two silently is the defect this
  document is about.
- **Escalate-and-continue was NOT copied across, on purpose.** rails-flow's criteria are independent,
  so a stop there moves to unrelated work. A pipeline is a gated chain: nothing downstream of a
  stopped stage is independent of it, and "continuing" is the out-of-order escape under a friendlier
  name. Copying the bullet for symmetry would have shipped advice that contradicts the mechanism
  beside it.
- **The honest report is an exit code, not a promise.** `breaker.py report` derives
  complete / partial / stopped from the ledger and exits `0` **only** for `complete`. Exceeding a cap
  makes a run `stopped` even if every stage later passed — crediting the outcome would make the cap
  advisory.

It is a script, not a hook, and the classification is deliberate: a hook sees one tool call, and every
one of these rules is a statement about a run. It is also a **discipline, not a sandbox** — it cannot
stop an agent that never calls it or that deletes the ledger. Both show up in a diff instead, and the
module's own docstring says so rather than implying otherwise.

---

## 8a. A topology is a declaration, not something a reader infers

Multi-agent shape — sequential, parallel, loop, agent-to-agent — changes what can go wrong, so
[#137](https://github.com/fmanimashaun/claude-skills/issues/137) asked for it to be documented and
for existing usages to be labelled in place. Building the check first is what showed *why the labels
have to be explicit rather than inferred*, and the evidence is worth keeping:

- **Prose does not correlate with topology.** `/rails-flow:review` is the flagship parallel
  fan-out — seven specialist passes, and the README says so — yet the word "parallel" appears
  **nowhere** in `review.md`. A keyword-based check would have missed the one command that handles
  this correctly and passed the ones that do not.
- **Counting agents over-fires.** `/rails-flow:feature` names eight agents. It is a pipeline: each
  phase consumes the previous phase's output, so there is nothing to reconcile.
- **Searching for merge vocabulary under-fires.** `/qa-flow:certify` declares a sound precedence
  rule — *"ANY S1/S2 open, or any layer failing its bar → FAIL"* — in words no reasonable keyword
  list contains.

So the command declares and the gate checks the declaration:

```
<!-- topology: parallel
     merge: any layer reporting an S1/S2 outranks every PASS; the same defect seen by
            two layers is ONE defect, keyed on route + failing assertion. -->
```

**A fan-out owes a `merge:` rule.** Not because reconciliation is hard, but because without it the
two questions that decide a verdict are undefined exactly when they arise: *both agents reported
it* (one defect or two?) and *the agents disagree* (which wins?). Absence of a finding from one
agent is never evidence against another's — they looked at different things.

**A loop owes an `exit:` condition** — the property that ends it, not a step count. Breakers
(attempt caps, no-progress detection) are **still not required in the marker**, and now for a
different reason than when this was written. The original reason was that §8 recorded them as a gap
owned by #128 and demanding them before they existed would be the exact defect this document is named
for. #128 has since shipped, so that reason has expired; the decision stands on its replacement: a
breaker is now a **mechanism with a ledger behind it**, and a number typed into an HTML comment would
be a claim nothing enforces sitting next to one that is enforced — strictly worse than no claim. A
command that loops should call `breaker.py`; the marker still declares only what ends the loop.
(No command declares `topology: loop` today, so this branch has no subjects — it is a forward guard
with a fires-and-silent fixture pair, not a live rule.)

Enforced by `undeclared-topology` in `lint_self_consistency.py`: any command dispatching two or
more of its own plugin's agents must carry the marker, a `parallel` one must carry `merge:`, a
`loop` must carry `exit:`. **Five** commands qualify today. The rule ships with a fires-and-silent
fixture per branch and **thirteen** declared mutations, because its first version resolved every plugin
name to `"plugins"`, examined **zero** commands, and reported "no findings" — a clean verdict over an
empty scan, visible only because the coverage counter printed the zero.

**A name in backticks is not a dispatch** (#491). The first version treated it as one, so a sentence
explaining *which agent consumes a command's output* counted as dispatching it — a false positive whose
only escapes were to declare a topology that does not exist, or to stop naming agents in prose. It now
requires a signal a dispatch actually has, and the narrowing is **deliberately biased toward counting**,
because for this rule a false negative is worse than a false positive: an undeclared parallel topology
ships two agents whose disagreement nobody defined.

---

## 9. Prefer inspectable state over opaque machinery

Plain text in git beats a store you cannot diff. This is already a decided question, not a preference:
`/rails-flow:brain-sync` **dropped NotebookLM** as an optional synthesis lens in rails-flow 1.3.1, and
the `<org>/brain` git repo is the single source of truth for cross-project state with **no external
embeddings or RAG layer**. The recorded rationale: git gives provenance, deterministic reads and
diffs; a separate synthesis service drifts from git and cannot be trusted for coordination.

The harness generalisation:

> **If you cannot diff it, you cannot gate it.**

Every mechanism in this document is a text file in git for that reason — and so is every artefact they
consume: `qa/CERTIFICATION`, `docs/acceptance/<slug>.md`, the fenced `deps` blocks in issue bodies,
`docs/brain/*`. An opaque store cannot be a guarantee, because rung 3 of §4 is unavailable: you cannot
mutate it on purpose and watch the gate go red.

The same reasoning is why a **rendering is not a source**, and why the direction of generation
matters. `scripts/build_coverage_artifact.py` renders the coverage matrix from
`build_coverage.ENTRIES` — the dataclass the generator already had — rather than parsing the
generated `coverage.md`. Its first draft did parse the markdown and failed its own count assertion
immediately: the Totals label `documented` also matches *"derivable from documented parts"*, so 44
rows landed in the wrong bucket. Pattern-matching generated English re-derives, badly, structure the
generator held as predicates. And because an HTML snapshot outlives the commit it was built from, the
page stamps its commit, branch and version onto itself — a stale second source of truth that looks
authoritative is the failure mode this repo keeps writing down.

---

## 10. Classify deliberately: the checklist when you add a hook, agent, command or gate

Silence is not a claim of exemption. Answer all five.

1. **Which tier is this?** Prose, output contract, or deterministic (§1). If a rule in it must always
   hold and you are writing tier 1 or 2, say so out loud — in the CHANGELOG entry and in the PR —
   rather than letting a reader infer enforcement.
2. **If it is a hook: advisory or gate?** An advisory exits 0 always and never blocks. A gate fails
   **closed** on a missing dependency, **scoped to the command it guards**, with a named audited
   override if one is warranted (§5).
3. **If it is a check, walk the ladder** (§4): selftest proving both directions → a declared mutation
   per *rule* → registered in `GATES` → three states with `skip ≠ pass` → and it must not write into
   what it inspects.
4. **If it dispatches two or more agents, which topology, and what reconciles them?** Declare it
   in the command (§8a). A `parallel` fan-out owes a `merge:` rule; a `loop` owes an `exit:`
   condition. `undeclared-topology` fails the build if you skip it.
5. **If it is doctrine with a copyable example, who compares the two?** #56 is the case where the rule
   and the example disagreed and nothing noticed, and the example is what ships (§2). Today the answer
   is often "nobody" — say that, rather than assuming the rule protects the example.

---

## 11. What enforces *this* document

**Nothing mechanical, and that is not an oversight.** This is a placement rule — *where* guarantees
belong — so it has no single measurable subject to gate. A document about not making unenforced claims
would be a poor place to make one, so the honest accounting is:

- **The doctrine itself is advice.** Tier 1, by nature. It changes what a reviewer looks for; it cannot
  stop anyone from shipping a prose-only guarantee. `.github/pull_request_template.md` is the closest
  thing to enforcement: it makes the change-type classification an explicit tick and demands a
  selftest plus a declared mutation from any new guard. That is tier 2 — a contract, checked by a
  human reviewer.
- **The individual factual claims in it are all re-checkable, and none of them is asserted from
  memory.** Every one was verified against this repo before being written down:

| Claim | How to re-check it |
|---|---|
| The gate list, and that it is complete | `GATES` in `scripts/maintainer_doctor.py`; `python3 scripts/maintainer_doctor.py --selftest` asserts every `*_selftest.py` is reachable from it |
| Every multi-agent command declares a topology, and a fan-out declares a merge rule | `python3 scripts/lint_self_consistency.py` (rule `undeclared-topology`) |
| Every gate's selftest can actually fail | `python3 scripts/mutation_check.py --selftest` (declared mutations) and `python3 scripts/mutation_check.py` (per-rule coverage) |
| The whole sweep, with skips distinguished from passes | `python3 scripts/maintainer_doctor.py --gates` |
| Nothing mechanically enforces #77's no-disposition clause | `grep -rn "disposition" scripts/ plugins/*/scripts/ evals/*.py` — no hits |
| Nothing mechanically cross-checks a skill's non-negotiables against its own recipes | `grep -rn "non-negotiable" scripts/ plugins/*/scripts/` — no check |
| `guard-bash.sh` does not block a push to a shared branch | Feed it `{"tool_input":{"command":"git push origin dev"}}` on stdin; it exits 0 |
| §8's stop conditions exist rather than being proposed | `grep -rniE "circuit.?breaker\|stop condition\|max attempts\|bail out" plugins/ skills/` — it returned **zero** when #128 was filed and returns hits now, so re-run it rather than trusting the sentence |
| The pipeline breaker fires on every rule it claims, and stays quiet on a healthy run | `python3 plugins/pipeline/scripts/breaker.py --selftest` (59 checks) and `python3 scripts/mutation_check.py --guard breaker` (14 declared mutations) |
| The pipeline doctrine and the pipeline code still agree | The last checks of that same selftest: `reference/stop-conditions.md` must state the numbers, the bounds and all four escapes the script declares, and every pipeline surface describing an unattended re-run must name `breaker.py` |
| The shell and code in this file are valid | `python3 scripts/lint_markdown_shell.py` and `python3 scripts/lint_markdown_code.py` — `docs/` is in their default roots |

The last row is the one place this document *is* under a gate, and it is a narrow one: the fenced
commands above are syntax-checked and screened for swallowed verdicts, because `docs/` was added to
both linters' `DEFAULT_ROOTS`. That covers the shell in the document. It says nothing about whether the
doctrine is followed.

- **Two claims in #132 did not survive that check**, and both are corrected in place above rather than
  reproduced: the issue's *"every one of those three was an agent ignoring text"* is not true of #56
  (§2), and its *"fail closed for gates"* is more precisely *fail closed, scoped to the command the
  gate guards* (§5). An issue body is a hypothesis, not a specification.

## Related

- `skills/code-review/SKILL.md` — the defect classes a reviewer applies, `claims-vs-enforcement` and
  `gate-that-cannot-fail` first among them. Shipped doctrine, so we are held to it.
- `CLAUDE.md` — the maintenance flow, the doctrine gate, git flow, and the two markdown linters. Note
  §5's discrepancy about its *Platform* sentence.
- `.github/pull_request_template.md` — the tier-2 contract that carries this classification into every
  PR.
- `docs/doctrine/issue-dependency-graph.md` — the worked instance of §5's rule: the graph is a gate (a cycle or
  a dangling edge prints no queue at all), the queue is advice.
