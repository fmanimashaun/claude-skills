# UI adapters

design-flow's core is stack-neutral: the design doctrine, the brand packs, the art-direction lens and the
tell detector. Everything that knows how a particular stack renders UI lives in one directory here,
`ui/<implementation>/`, and a project selects it with its stack descriptor's `ui.implementation`
(`plugins/<stack>/stacks.json`). The directory name IS the implementation id, so there is no table to drift.

| file | what it is |
|---|---|
| `<implementation>/adapter.json` | `id`, `stack`, the `agents` it provides (`porter`, `composer`, plugin agent names) and the `checks` ids it owns |
| `<implementation>/scripts/` | the checks and gates that read that stack's source |
| `<implementation>/scripts/mutations/` | their mutation guards, discovered by `scripts/mutation_check.py` with design-flow as the base |

A script in an adapter reaches the neutral core beside `ui/` (`scripts/`, `brands/`, `commands/`): from
`ui/<implementation>/scripts/` that is `parents[2]`.

`lint_self_consistency.py`'s `ui-adapter-unresolved` rule refuses a descriptor whose `ui.implementation` has no
`adapter.json`, an `adapter.json` whose `id` is not its directory name, or an agent it names that does not exist.

Adding a stack's adapter: create `ui/<id>/` with those three parts, name the agents `<stack>-ui-porter` and
`<stack>-ui-composer`, and set the stack's `ui.implementation` to `<id>`.
