# Doctrine-effect benchmark

Measures whether **loading the rails-stack skills changes what an agent writes**.

This repo already has a hard gate on doctrine *content* — nothing is edited until
`doctrine-verifier` confirms it against an authoritative source. It has never had
a gate on doctrine *effect*. Claims like "the rails-8 skill produces better Rails"
have lived entirely in the one layer we otherwise refuse to trust: prose. This is
the sibling gate. Secondary benefit, possibly the more valuable one: **a doctrine
edit that makes agent output worse is currently undetectable.** This makes a
regression visible.

Tracked by [#156](https://github.com/fmanimashaun/claude-skills/issues/156).

## Results

**None yet.** The harness is built and mechanically verified; no paid run has been
authorised. This section stays empty rather than carrying provisional numbers —
publishing an unverified figure is the exact failure #156 exists to correct.

When a run happens, the table records date, model, `claude` version, marketplace
version, and run count. A number without its conditions is not evidence.

| date | model | runs | case | none | weak | real |
| ---- | ----- | ---- | ---- | ---- | ---- | ---- |
| _(pending authorisation)_ | | | | | | |

## Why not the Anthropic API

The obvious build is `POST /v1/messages` with `SKILL.md` pasted into `system`.
Clean, cheap, reproducible with just an API key — and it measures the wrong thing.
**These skills ship as Claude Code plugins.** A pasted system prompt is a proxy
for how they actually load, so a result from that harness would not be evidence
about what a user who runs `/plugin marketplace add` receives.

So the runner drives `claude -p` and toggles the plugin per arm. Consequences,
accepted deliberately:

- **No Anthropic API dependency.** Stdlib Python driving the CLI as a subprocess.
  No `requirements.txt`; nothing for CI to install. Consistent with
  `scripts/package_core.py` and `scripts/lint_markdown_shell.py`.
- **Noisier than single-shot** — a real agentic loop, not one completion. That is
  the cost of measuring the real thing instead of a clean abstraction of it.
- **Reproducing it needs Claude Code**, not just an API key. Fine: the audience
  for this benchmark is people evaluating a Claude Code plugin.

### This will be deleted

`claude plugin eval` implements this properly — `--ablation with-without` for the
baseline arm, `--runs`, `--threshold`, `--json`, `--max-cost-usd`, HTML reports.
It is in **early access** and unavailable on this account, so `run.py` covers the
gap and nothing more.

The durable assets are `cases/*/prompt.md`, `gates.py`, and `selftest.py`. When
early access opens, point `claude plugin eval` at `evals/` and delete `run.py`.
Do not grow it into a framework.

(`case.yaml` is deliberately absent: this repo is stdlib-Python-only and `yaml`
is not in the stdlib, so metadata lives in `suite.json`. The prompts already sit
at the documented `evals/**/prompt.md` path.)

## Arms

| arm | loads | why it exists |
| --- | --- | --- |
| `none` | nothing | Baseline. Without it a number means nothing. |
| `weak` | `weak-skill/` | Control. Generic, content-free Rails advice. Separates *"this doctrine helps"* from *"any loaded skill helps"*. A win over `none` that is **not** also a win over `weak` means we measured the presence of instructions, not the content of ours. |
| `real` | staged rails-stack | The three bundled skills + a `plugin.json`, staged at run time. |

`rails-stack` is declared `"source": "./"` — the repo root. Pointing `--plugin-dir`
there would risk loading this repo's `.claude/` maintainer tooling, which
`CLAUDE.md` says is explicitly **not** distributed. So the real arm is staged
clean: `plugin.json` plus `skills/{rails-8,hotwire,fidara-design}`. That is a
faithful reproduction of what `/plugin marketplace add` gives a user.

## Gates vs measurements

**Gates** are the deterministic rules in `gates.py` — grep/parse, pass/fail, same
verdict on any machine forever. **Measurements** are cost, wall-clock, output
tokens, and turn count: recorded, never judged.

Keeping them separate is what stops the benchmark being gamed. "Less code" is
trivially achieved by emitting something broken, so volume only means anything
next to a gate.

A run that errored, hit the API error path, or was blocked by a permission prompt
is **INVALID** — excluded from scoring, not counted as a failure. Scoring an
infrastructure problem as a doctrine failure is how you invent a regression.

### The rules

Every rule is named and cites the doctrine file:line it enforces. A rule with no
doctrine behind it is taste, and taste belongs in a discussion.

| rule | doctrine | asserts |
| --- | --- | --- |
| `scoped-index` | `auth-security.md:121` | collection reads scope through `Current`, not the global model |
| `simple-form-convention` | `forms.md:3` | forms use `simple_form_for` where the project has adopted it |
| `no-inline-dark` | `foundations-tokens.md:247` | zero inline `dark:` utilities in components/views |
| `no-literal-color` | `brand.md:87` | no literal colours outside `Ui::Logo` |
| `job-idempotent` | `jobs-and-realtime.md:176` | jobs guard against re-running |
| `spec-accompanies-behavior` | `rails-8/SKILL.md` | a concern ships with a spec that proves it |

### Two gates in the issue spec were wrong

Authoring these caught two rules that would have **manufactured false
regressions** — making the real-skill arm score worse than baseline and
"proving" our own doctrine harmful:

1. **Jobs.** #156 specified *"ids only"* and *"job signature taking an AR object
   → fail"*. Doctrine says the opposite — `jobs-and-realtime.md:28`:
   `def perform(order)  # pass records, not ids: GlobalID (de)serializes them`.
   An ids-only gate fails the doctrine's own reference example. Only idempotence
   is gated (`:176`, *"Idempotent always"*).

2. **Literal colours.** A naive no-hex rule flags our own `Ui::Logo`, which
   `brand.md:87` names as *"the only component permitted to carry literal
   colors."* The carve-out is encoded.

The general principle, and the reason `selftest.py` asserts it: **a gate must pass
against the doctrine's own reference examples.** If a rule fails what
`references/*.md` shows as correct, the rule is wrong — not the doctrine.

A third case needed fairness work rather than correction: `form_with` is correct
stock Rails, and `ecosystem-gems.md:29` makes simple_form conditional ("dozens of
uniform CRUD forms"). So `scaffold.py` establishes the convention (Gemfile entry
plus initializer) and the gate **refuses to judge** when it is absent.

## Isolation

Runs never execute in this repo. Our `CLAUDE.md` is maintainer doctrine; the agent
would read it in *every* arm, contaminating all three identically — which does not
look like breakage, it just drifts the result toward "no difference".

`scaffold.py` asserts isolation instead of assuming it, and refuses to run when:

- any ancestor holds a `CLAUDE.md` (auto-discovered memory), or
- any ancestor **other than the home directory** holds `.claude/`, or
- `~/.claude/skills/` is non-empty — skills-dir plugins auto-load into every
  session, so a skill parked there would be present in all three arms.

`--setting-sources ""` additionally excludes user/project/local settings, so a run
does not inherit whatever plugins the operator happens to have enabled.

Tools are restricted to `Read,Write,Edit,Glob,Grep`: no Bash, no network. That
removes permission prompts (which would invalidate runs), removes a large source
of nondeterminism, and costs nothing — the gates only read files.

## Usage

Free, no `claude` binary required:

```bash
python3 evals/selftest.py                 # prove every gate fires and stays silent
python3 evals/run.py --dry-run            # print exact commands, execute nothing
python3 evals/gates.py <workspace-dir>    # run all gates over a directory
```

Paid — **costs real money**:

```bash
# calibrate on one case before committing to a sweep
python3 evals/run.py --case 01-scoped-index --runs 1 --max-total-usd 1.00

# full matrix (5 cases x 3 arms x N runs)
python3 evals/run.py --runs 3 --model sonnet --max-total-usd 25.00
```

`--max-total-usd` is **required** for a live run — the runner refuses to start
without it. It was originally a README instruction and nothing more; a rule
enforced only in prose is the failure this repo keeps relearning, so the guarantee
now sits in the deterministic layer. `--per-run-budget-usd` forwards to the CLI's
own `--max-budget-usd` for a hard per-run ceiling. `--keep-workspaces` preserves
each run's directory for inspection.

**Cost is uncalibrated.** A trivial baseline call measured $0.017; a real task with
34 reference files available and up to 30 turns will be substantially more, and
the `real` arm costs more than `none` by construction. Calibrate with one case
before running a sweep.

## Not in the release path

Nothing here is wired into CI. It costs money, it is opt-in, and it must never
gate a promotion. `results/` is committed output, not a build artifact.

## What this benchmark covers, and what it deliberately does not

Three skills are staged in the `real` arm — `rails-8`, `hotwire`, `fidara-design` — and **every one
of them now has at least one case**. That is asserted rather than remembered:
`selftest.py` fails if a skill is staged and no case is tagged with its name.

The check exists because `hotwire` was staged for the whole life of this benchmark with **zero**
cases (#646). That is worse than an untested skill. Its tokens occupied the real arm's context and
contributed no signal, so every win or loss was attributed to the other two. The `weak` arm exists
to stop us mistaking *"any instructions help"* for *"our doctrine helps"*; a staged-but-unmeasured
skill undermines the same rigour from the other direction.

**The other four shipped skills have no cases, and that is a decision rather than a gap:**

| skill | why no case |
|---|---|
| `code-review` | It reviews a **diff**. This benchmark's unit is "write the files into a fresh scaffold", which produces no diff to review — measuring it needs a different harness, not another case. |
| `quality-pass` | Advisory by design and explicitly **never a merge condition**. Scoring it pass/fail would contradict the doctrine it measures. |
| `derived-artifacts` | About how a *generator* reads its source. There is no generator in the scaffold. |
| `parallel-session-lane` | About several agent sessions sharing one repo. A single-run benchmark cannot express the condition it governs. |

None of these is staged in the `real` arm, so none of them dilutes a measurement. **Written down
because an unexplained absence reads exactly like an oversight** — and the next person to notice
four uncovered skills should find the reasoning rather than re-derive it.

## Known limitations

Stated rather than discovered later:

- **Skill *loading* is not proven.** `claude plugin validate` confirms the staged
  plugin's manifest, but that the agent actually consulted `rails-8` is only
  observable in a live run. If the `real` arm scores identically to `none` across
  every case, suspect loading before concluding the doctrine is inert.
- **Prompts are single-shot and terse.** They deliberately never name the
  technique (`Current`, `simple_form`, role tokens, idempotence) — otherwise every
  arm passes and the benchmark measures nothing. The cost is that a prompt may be
  ambiguous enough that a competent agent reasonably does something else.
- **`no-inline-dark` flags the literal text `dark:`** anywhere in a view, including
  inside a URL. Asserted as current behaviour in `selftest.py` rather than hidden.
- **No turn cap.** The `claude` CLI exposes no `--max-turns`, so turn count is
  *measured* (`num_turns`) and not bounded. Spend is capped by `--max-total-usd`,
  `--per-run-budget-usd`, and the per-run timeout instead. `suite.json` therefore
  declares no `max_turns` — a declared condition nothing enforces is worse than
  an absent one.
- **Ruby `#` comments are stripped in `.rb` files only, never `.erb`.** In a
  template a bare `#` is HTML text (`Invoice #42`, `href="#"`), so blanking to
  end-of-line there would hide real violations after it. `<%# ... %>` is handled
  in both. A Ruby comment inside `<% ... %>` in an `.erb` file is not stripped.
- **Five cases is a sample, not coverage.** Nothing here speaks to the ~30
  reference files the cases do not touch.
- **One model at a time.** Ponytail runs 3 arms x 3 models x 5 tasks x 10 runs;
  `--model` takes one value per invocation.
