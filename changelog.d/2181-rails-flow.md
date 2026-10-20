section: rails-flow
- **A stack says how it tests, boots, reviews and deploys: the `descriptor` in `stacks.json`, read by `detect_stack.py --descriptor` — `plugins/rails-flow/scripts/detect_stack.py`** (#2181, plan step 2 of #2162). A stack's `descriptor` declares:
  - `runner_prefix`;
  - `tests` (command, glob, preflight) and `lint`;
  - `layout` (source, migrations, schema, views, components);
  - `boot` (command, port, health, routes);
  - `agents` (role to agent), `deploy` (target, artifact, agent) and `ui` (implementation, porter, composer);
  - `dangerous_commands`, `setup_section`, `scripts` and `review_checklist`.

  `--descriptor` prints the detected stacks' merged descriptor. Stacks of one plugin merge (Next.js + Supabase + Vercel). A key declared by two plugins, or one leaf given two values, is exit 2 naming both sources. Every key and its shape is declared once, in `DESCRIPTOR_SCHEMA`; an unknown key or a wrong type is a problem (`descriptor-key-undeclared`). `--check` validates every discovered manifest whatever the project.
  `rails-stack`'s `stacks.json` declares the Rails values the flows hard-code today, with no new values: `bundle exec rspec --fail-fast --no-color` over `spec/**/*_spec.rb` with `pg_isready` first; `bin/dev` on 3000 with `/up`; `db/migrate/` and `db/schema.rb`; the six `rails-flow` agents; Kamal through `pipeline:kamal-configurator`; ViewComponent/ERB through `design-flow`'s porter and composer; and `db:reset` allowed only as `RAILS_ENV=test bin/rails db:reset`.
  Nothing reads the descriptor yet; step 3 (#2173, #2174) moves the flows onto it. The selftest grows to 23 cases (a `go` stack no Rails value fits, a three-stack merge, both conflicts, an undeclared key and a wrong type), and the mutation guard to 13 mutations, all caught. Our own design (maintainer, #2162, 2026-10-20), not a framework claim.
