# core-skills

The four stack-neutral skills that `rails-flow`, `rails-stack` and `nextjs-stack` all use, installed
once instead of once per stack. Before #2186 they were bundled in `rails-stack`, which made a
project on any other stack install that stack's doctrine to get a code review.

| skill | what it is for |
|---|---|
| `code-review` | review for code that is correct on its own terms but does not do what its docs, config or project rules claim |
| `quality-pass` | an advisory second pass over a diff: reuse, simplification, efficiency, altitude; never blocks a merge |
| `derived-artifacts` | a generated file, the source it derives from, and the check that they still agree |
| `parallel-session-lane` | working in one repository beside other agent sessions without colliding |

## Install

`rails-flow`, `rails-stack`, `nextjs-stack` and `flow-suite` declare `core-skills` as a dependency, so
installing any of them installs it ("Claude Code also installs and enables the plugin's declared
dependencies", Claude Code docs, plugins/install). To install it alone:

```
/plugin install core-skills@claude-skills
```

Dependencies are declared directly by each plugin that needs them, never relied on transitively: the
docs do not say whether a dependency's dependencies install.

## Where things moved

`rails-stack` keeps a one-line redirect for each skill for two releases, so a project that pins
`rails-stack:code-review` is told where it went. Their `dist/<skill>.skill` files keep their names.
`agent-output-contract.md` and `findings.py` are stack-neutral references that this plugin is meant to own. Today
their canonical copies are still rails-flow's (`reference/agent-output-contract.md`, `scripts/findings.py`), with
byte-identical copies in qa-flow and rails-stack, because an agent reaches only its own plugin's files; moving
the canonical home here is #2283.
