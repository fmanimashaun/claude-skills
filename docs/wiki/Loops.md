# How the loops fit

Three loops, three agents, three different jobs. The separation is the design, not an accident of
packaging.

| loop | plugin | its job | what it must not do |
|---|---|---|---|
| **Build** | `rails-flow` | plan, implement, review, remember | sign off its own work |
| **Verify** | `qa-flow` | reproduce the claim, produce evidence | read the diff for hints |
| **Ship** | `pipeline` | gate the two above into a release | continue past a stop |

## Why verify is a separate agent

A build agent that also certifies its own work is a build agent that certifies its own work. It has
seen the diff, it knows which paths it touched, and it will test those — which is exactly the set of
paths least likely to be broken.

So `qa-flow` derives its cases from the **brief**, not the diff, and treats the developer's account
as unverified. It produces artefacts a human can re-check rather than a summary that has to be
believed. `/qa-flow:certify` is the only command in the toolchain that can say a change is ready.

## Why ship stops instead of retrying

An unattended run that hits a failure has two options: stop, or dig. Digging is how a loop spends an
afternoon and a budget converging on nothing.

`pipeline` carries circuit breakers — an attempt cap, a no-progress detector, and four **forbidden
escapes** it will not take to get green:

1. weakening, skipping or deleting a failing test
2. reverting a stage that already passed, to unblock this one
3. running a stage out of order, or past a gate that has not passed
4. disabling a guardrail, hook or gate

The final report distinguishes **complete**, **partial** and **stopped**, derived from the ledger
rather than from the agent's own account of the run. *Partial completion reported as success is the
worst available outcome* — it spends the reviewer's trust and their time.

## Where the autonomous driver sits

`/rails-flow:drive` is a conductor **over** these loops, never a fast path around them. Each tick it
answers two questions: what is next, and may I do it alone.

It chooses **one** action, never a menu — a driver returning three options has handed the decision
back to the human it exists to spare. When something needs a human it asks **asynchronously** via
`/rails-flow:escalate`, which comments on the issue, labels it so you get an email, and moves on to
other independent work rather than blocking.

The decision-rights policy is configurable and **rots safe**: an unclassified action escalates, and
a policy that escalates nothing is refused outright. The test that keeps it checkable is *"does it
publish, or can it not be undone"* — readable from the action itself, unlike *"is this important"*.
