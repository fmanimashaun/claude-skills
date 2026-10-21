# viewcomponent-erb — the Rails UI adapter

Selected by a stack descriptor whose `ui.implementation` is `viewcomponent-erb` (rails-stack's). It renders the design system as
Rails 8 + Hotwire + Tailwind v4: the `@theme` token architecture in `app/assets/tailwind/application.css`, ViewComponents, ERB,
simple_form, Turbo and Stimulus, and the brand pack recorded in `config/initializers/brand.rb` as `config.x.brand.pack = "<slug>"`.

- `adapter.json` — id, agents (`rails-ui-porter`, `rails-ui-composer`) and the gate ids it owns.
- `setup.md`, `component.md`, `port.md`, `audit.md`, `mobile.md`, `tokens.md`, `variants.md` — what each `/design-flow:<command>` does
  here; the command resolves this directory with `scripts/ui_adapter.py` and reads the matching file.
- `scripts/` — the ERB/ViewComponent checks and the canvas port gate; `scripts/mutations/` — their guards.
