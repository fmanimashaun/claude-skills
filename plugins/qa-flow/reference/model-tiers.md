# Model tiers — which qa-flow agent runs on what, and why

**The short version: a `model:` pin is a cap, so we only pin where something outside the agent grades
its output.** Everything else inherits the session model the user deliberately chose.

This mirrors `plugins/rails-flow/reference/model-tiers.md`, which carries the full argument and the
citations. The three facts that decide it, verified against
[the sub-agents docs](https://code.claude.com/docs/en/sub-agents) and
[model configuration](https://code.claude.com/docs/en/model-config):

1. `model` *"Defaults to `inherit`"* — an agent with no `model:` line already follows the session.
2. Resolution puts *"the subagent definition's `model` frontmatter"* **above** *"the main
   conversation's model"*. So pinning `sonnet` on a reviewer means a user who deliberately started an
   Opus session gets a **Sonnet** reviewer. We spent their upgrade for them, downwards.
3. Pinning *up* buys nothing: a value outside the org's `availableModels` is *"skipped"* and the
   agent *"runs … on the inherited model instead"*. And an alias is a per-provider lookup that
   *"update[s] over time"* — `sonnet` is Sonnet 5 on the Anthropic API, **Sonnet 4.5** on Amazon
   Bedrock and Google Cloud's Agent Platform, **Sonnet 4.5** on Microsoft Foundry (where `opus` is
   **Opus 4.6** while it is Opus 5 everywhere else). A shipped plugin cannot know what its own
   frontmatter selects.

## Why qa-flow keeps more cheap pins than rails-flow

This is the interesting case, and it is a **decision with a named proof**, not an accident.
rails-flow's mechanical tier is small because most of its agents produce prose a human reads.
qa-flow's outputs are largely **artefacts that a deterministic script grades and can reject** —
`validate_evidence.py`, `evidence_manifest.py`, `route_coverage.py`. That is exactly the condition
the cheap tier requires: *the model cannot mark its own homework.*

Every `haiku` row below names the thing that grades it. **A row with no proof is a bug in this
table** — `check_handoff.py` rejects an empty proof cell, so the requirement is enforced rather
than merely stated.

<!-- qa-flow:tiers:begin -->
| Agent | Tier | `model:` | What proves its output |
|---|---|---|---|
| `qa-lead` | judgement | `inherit` | — |
| `case-author` | judgement | `inherit` | — |
| `functional-tester` | judgement | `inherit` | — |
| `exploratory-tester` | judgement | `inherit` | — |
| `e2e-tester` | judgement | `inherit` | — |
| `api-contract-tester` | judgement | `inherit` | — |
| `security-scanner` | judgement | `inherit` | — |
| `a11y-auditor` | mechanical | `haiku` | `@axe-core/playwright` returns the violation list; `validate_evidence.py` rejects an a11y row without a rule id and a screenshot |
| `perf-tester` | mechanical | `haiku` | k6 threshold exit status, and `validate_evidence.py`'s per-route performance profile rejects a fabricated or incomplete row |
| `qa-reporter` | mechanical | `haiku` | `evidence_manifest.py` — a report that does not reconcile against the manifest is rejected |
<!-- qa-flow:tiers:end -->

## The judgement rows, and why each is not mechanical

The four that look borderline are worth stating, because "it runs a tool" is not the same as "a tool
grades it":

- **`security-scanner`** runs OWASP ZAP, but ships **triage**. Deciding which baseline alerts are
  real is the entire value, and nothing external grades a triage call.
- **`api-contract-tester`** runs Schemathesis, which does grade the contract half — but the agent
  also drives a **hand-built authorization matrix**, and that half is judgement. A mixed agent takes
  the higher tier; splitting it to cheapen half would be a change to the agent, not to this table.
- **`e2e-tester`** is graded by its suite's exit status *once the specs exist*. **Authoring** the
  specs is the judgement, and a suite that asserts the wrong thing passes.
- **`case-author`** derives cases from a PRD. Nothing checks that a derived case is the *right* case.

## `effort` is deliberately unset

A different field. It *"Overrides the session effort level"* and its available levels
*"depend on the model"* — which levels each model accepts is unpublished, so a shipped default would
be a guess that silently degrades on some models. Left to the session.
