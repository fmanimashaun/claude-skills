section: rails-flow
- **`/rails-flow:setup-flow` detects the stack of an existing project and asks for a new one — `plugins/rails-flow/commands/setup-flow.md`** (#2180, owner ruling of 2026-10-20 on #2180 and #2162). A new §0 runs `detect_stack.py`:
  - **an existing project** (a stack detected): setup-flow asks nothing. It activates that stack's descriptor and its setup sections;
  - **a new project** (nothing detected): it asks which stack, offering exactly what `detect_stack.py --available` lists from the installed stack plugins' manifests (no list is written into the command), then takes the choice with `--stack <id>`;
  - **cannot judge** (exit 2): it asks, quoting the problems, and never falls back to Rails.

  The working rules it writes are the same in all three paths. The Rails-only repairs (the `Tests:` steps, locales, the launch baseline, the tenancy cop, the coverage ratchet, spec/support wiring, simple_form, `Archspec.rb`) move out of the command into rails-stack's `setup/rails.md`, which `stacks.json` names as Rails' `setup_section`. The command is 1353 → 1024 lines.

  `detect_stack.py` gains `--available` and `--stack`. A setup section is per stack and never merged, so a two-plugin project runs both. A section that leaves its plugin, or names no file, is a problem (exit 2), which `--check` catches. Selftest 52 cases, guard 36 mutations, all caught. The template's Rails fact lines move in #2196. Our own design (owner ruling), not a framework claim.
