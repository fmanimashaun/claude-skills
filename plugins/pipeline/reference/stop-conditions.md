# Stop conditions — when an unattended pipeline run must stop and escalate

**The hooks already stop a run doing damage. Nothing said when to stop *trying*.** That is the gap
[#128](https://github.com/fmanimashaun/claude-skills/issues/128) reports, and this file is the
pipeline half of it. rails-flow's half lives in the work order `/rails-flow:handoff` writes; a
pipeline has no work order, so its stop conditions live here and are enforced by
`${CLAUDE_PLUGIN_ROOT}/scripts/breaker.py` against a run ledger.

An agent that cannot make progress does not idle — it digs. In this plugin the digging is
expensive: re-pushing an image, re-running `kamal deploy` against a live host, reaching for the
audited deploy override because the gate is "obviously" wrong. Every one of those looks like
activity in a log, and two of them look like success.

## The ledger, and why it is a file

`pipeline/run-ledger.jsonl` — append-only JSONL, one record per line, **committed**. Same reasoning
as `qa/CERTIFICATION`: a run's honest ending has to survive the session that produced it, and a
reviewer of the release needs to see whether the run that built it was complete or stopped. Plain
text in git means the whole run is a `git diff`, including the deletion of a ledger someone found
inconvenient.

The breaker is a **discipline, not a sandbox**. It cannot stop an agent that never calls it or that
deletes the ledger — it makes both visible instead. That limit is stated here rather than papered
over, because a guarantee nothing makes true is the defect this toolchain writes down most often.

## The numbers, and what may be overridden

Declared **once**, at `start`. `check` reads them back from the ledger and accepts no threshold
flags at all, so a run cannot widen its own cap halfway through — and a second `start` over a run
that did not end `complete` is refused rather than silently resetting the counters.

| Flag | Default | Allowed | Why that shape |
|---|---|---|---|
| `--attempts` | **3** | `1..10` | Bounded retries per stage. The next attempt on an unchanged failure has never been the one that works. |
| `--no-progress` | **2** | `2..10` | Two identical failure signatures in a row is a stop. Repetition *without a changing error* is the signal; a changing error is progress. Below 2 it would fire before the attempt cap could ever run. |
| `--budget-minutes` | **120** | `1..480` | An unattended run with no budget is discovered by its bill. Report the remainder. |

The upper bounds are the point: **an override that can be set to infinity is not a breaker.** Work
that genuinely needs more than this is more than one run — split it, or hand back with the
diagnosis. The numbers are the same ones rails-flow's work order settled on, reused deliberately:
two halves of one issue disagreeing about what "3 attempts" means would be worse than either number
being wrong.

## The five ways `check` refuses

`check` is read-only and never writes into what it inspects, so the verdict and the record of it
are separate, deliberate acts. It prints `STOP <reason>` and exits `1`:

| `<reason>` | It means |
|---|---|
| `already-passed` | The stage already passed in this run. Re-running it replaces proven work with unproven work. |
| `out-of-order` | An earlier stage in the plan has not passed. This is gate-skipping, made mechanical. |
| `attempt-cap` | The stage has burned its attempts. |
| `no-progress` | The last N failures carry an identical signature. |
| `budget` | The wall-clock budget is spent. |

A stage that is not in the run's declared plan is **exit 2, not exit 1** — "I cannot judge this" is
a different answer from "do not proceed", and only one of them is a verdict.

## The four forbidden escapes — these end the run

Same taxonomy as #128, translated to what each looks like in a gated deployment chain. They are not
"discouraged":

| Escape | Why it ends the run rather than costing a warning |
|---|---|
| weakening, skipping or deleting a failing test to get a stage green | Destroys the only external proof the release has. A certification is worth exactly what the suite behind it is worth. |
| reverting a stage that already passed in order to unblock this one | Trades work that was proven for work that is not. |
| running a stage out of order, or past a gate that has not passed | This is how uncertified code gets an image built for it. `check` refuses it mechanically; the doctrine is here because the refusal only binds a caller that asks. |
| disabling a guardrail, hook, or gate -- including reaching for an audited override | `RAILS_FLOW_ALLOW_DEPLOY=1` exists for a human's deliberate say-so on a *working* deploy, never as a way past a failing one. The guardrails are the reason unattended deployment is allowed at all. |

Two of the four are decidable from the ledger and are enforced. The other two involve file edits
the breaker cannot see, so they stay doctrine — and `breaker.py --selftest` asserts this table
still lists all four with the strings the script declares, so the doctrine and the code cannot
drift apart.

## Escalate and continue does **not** apply here, and that is deliberate

rails-flow's stop conditions say: on a stop, write the diagnosis and continue with unrelated
criteria. Criteria are independent, so that is right there. **A pipeline is a gated chain** —
nothing downstream of a stopped stage is independent of it, and "continuing" past a stop is the
out-of-order escape wearing a friendlier name. So a stop ends the run here. What carries over is
the other half: the stop must carry a **diagnosis**, and `breaker.py stop` refuses without one.

## The final report: complete / partial / stopped

Derived from the ledger by `breaker.py report`, not from the agent's own account of the run, and
the exit code carries the verdict: **`0` only for `complete`**, `1` for `partial` or `stopped`.

- **complete** — every planned stage passed, no cap was exceeded, no breaker tripped.
- **partial** — the run ended with planned stages unattended or unfinished, and nothing tripped.
- **stopped** — a breaker tripped, or a cap was exceeded, or a stop was recorded with no diagnosis.

Exceeding a cap makes a run `stopped` **even if every stage later passed**. A run that ignored its
own breaker did not follow the protocol, and the report says so rather than crediting the outcome.

Report the word verbatim and name every stage that was not attempted. *Partial completion reported
as success is the worst available outcome*: it spends the reviewer's trust and the reviewer's time,
and it is how a green log ships a broken release.

## Running it

```bash
BREAKER="${CLAUDE_PLUGIN_ROOT}/scripts/breaker.py"

python3 "$BREAKER" start --stages verify,certify,release

python3 "$BREAKER" check certify
python3 "$BREAKER" record certify --outcome fail --signature "rspec: 3F in spec/billing_spec.rb"

python3 "$BREAKER" stop certify --breaker no-progress \
  --diagnosis "same 3 failures twice; suspect the seed, not the code — see qa/CERTIFICATION"

python3 "$BREAKER" report
```

Exit `0` proceed / recorded / complete · `1` STOP, or the run was partial or stopped · `2` unusable
input. **Never wrap any of these in `|| true` or `|| echo`** — the exit code *is* the verdict, and
consuming it produces a run that looks bounded and is not. That is not hypothetical here: a
`--check || echo` in this plugin's own release command shipped a gate that could not block (#151).

## `maxTurns` is a different bound, not this one

An agent's frontmatter may carry `maxTurns` — *"Maximum number of agentic turns before the subagent
stops"* ([Claude Code docs](https://code.claude.com/docs/en/sub-agents), fetched 2026-07-31). It
bounds **turns, not attempts**: an agent can burn three attempts inside one turn, or spend twenty
turns making real progress on one. It is a mechanical backstop that complements the attempt cap;
it does not replace it, and neither plugin sets it in place of these numbers.
