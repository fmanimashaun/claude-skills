# `/design-flow:component` for the Rails UI adapter (`viewcomponent-erb`)

Read by `/design-flow:component` after `ui_adapter.py` resolves this adapter. The command owns the order of operations; this file is
what "the adapter" means in it when the project renders ERB and ViewComponents.

## Step 4 — express variants server-side

A Ruby base+variants+sizes+defaults map on the ViewComponent (the cva pattern, no JS dep). Reuse the shared size vocabulary
(`sm/md/lg`).

## Step 5 — interaction

Wire the right Stimulus controller/mixins (rails-stack's `skills/design-system/references/interaction-stimulus.md`). Concrete code to mirror:
`reference-implementation.md` (Button/Card + Stimulus mixins) and `component-implementations.md` (the full worked catalog).

## CRUD screens

Mutations open in the shared `turbo-frame` modal and update the list via Turbo Stream — never build a full-page new/edit form.

## Primitives

`Layout::Sidebar`/`Switcher` are this adapter's layout components.

## Output

The ViewComponent (`.rb` + `.html.erb`) and/or refactored partial.
