# Model tiers: rails-stack's agents

Which model each rails-stack agent runs on. The policy, and why each agent sits in its tier, is in rails-flow's `reference/model-tiers.md` (the agents moved here from rails-flow in #2173, with the tiers unchanged).

<!-- rails-flow:tiers:begin -->
| Agent | Tier | `model:` | What proves its output |
|---|---|---|---|
| `code-reviewer` | judgement | `inherit` | — |
| `security-auditor` | judgement | `inherit` | — |
| `migration-writer` | judgement | `inherit` | — |
| `rails-developer` | judgement | `inherit` | — |
| `test-runner` | mechanical | `haiku` | `bundle exec rspec` exit status — 0 failures or the gate blocks |
| `design-auditor` | mechanical | `haiku` | the mandated greps must come back empty (`form_with`, `f.label`) |
| `kamal-configurator` | judgement | `inherit` | — |
<!-- rails-flow:tiers:end -->

`kamal-configurator` arrived from `pipeline` in #2179. It performs an **autonomous cloud deployment** from a briefing sheet: the blast radius is a production environment, and a deploy that succeeds against the wrong configuration reports success. Nothing outside the agent grades that judgement (the attempt ledger grades the run, never whether the host was the right one), so an empty proof cell is exactly right and it stays uncapped.
