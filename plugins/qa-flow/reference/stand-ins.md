# Stand-ins — how a journey walk gets past a system it cannot drive

A persona's journey usually crosses a system the walk cannot operate: an e-signature provider, a
payment approver, an identity provider, a card printer. The walk still has to reach the page on the
far side — *what does the applicant see once the contract is signed?* — so it **stands in** for the
external step, and it does so under three rules that keep a stood-in step from being mistaken for a
tested one.

## The three rules (stack-neutral)

1. **A stand-in is a model call the project's own fixtures already make.** Never a new method, never
   a direct database write, never an HTTP call to the external system's sandbox. If the fixtures do
   not already perform the transition, the walk records the step as **Blocked** with the reason and
   moves on; inventing a transition is editing the app from the outside.
2. **Only the stand-ins declared in `qa/qa.config.yml` → `walkthrough.stand_ins` may be run.** The
   list is the project's declaration of what it is willing to fake; `walkthrough_plan.py` echoes it
   into the plan, and the report names every stand-in it used, verbatim, beside the step it replaced.
3. **A stand-in never produces evidence for the step it replaces.** The e-signature *itself* is not
   tested by calling `record_signature!`; only what the app shows *after* it is. The hand-off row for
   the replaced step is `Out of Scope` with `Notes` naming the stand-in, and the rows that follow are
   real observations.

Everything above is doctrine for any stack. The recipe below is one stack's, kept here as an
**example** because `qa-flow` scaffolds Rails defaults elsewhere (`app.start: bin/dev`) and labels
them the same way — not because the plugin knows Rails.

## Example: Rails

Declare the calls, with the argument the walk will supply as `ARGV[0]`:

```yaml
# qa/qa.config.yml
walkthrough:
  stand_ins:
    - "bin/rails runner 'Contract.find_by!(public_id: ARGV[0]).record_signature!'"   # e-signature
    - "bin/rails runner 'Provisioning.find_by!(public_id: ARGV[0]).activate!'"        # the IdP
```

Run one exactly as declared, then re-read the page as the persona who should see the consequence:

```bash
bin/rails runner 'Contract.find_by!(public_id: ARGV[0]).record_signature!' -- ctr_8kQ2mP
```

**Two traps measured on a real project (16 Sep 2026):**

- **Mail enqueued from `bin/rails runner` dies with the process** under the async Active Job adapter,
  so the dev inbox will show nothing for a notification the stand-in should have triggered. Read the
  inbox only for steps performed **through the server**; a stand-in's notification row is `Blocked`
  with that reason, never `missing`.
- **A QA server does not reload.** A server booted before the current schema or `Gemfile.lock` keeps
  answering and silently drops new columns from every write. Run the project's freshness check (for
  example `bin/assert-fresh-server`) before trusting any page, and again after any migration.
