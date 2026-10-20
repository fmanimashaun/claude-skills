section: Repository hygiene
- **The gates follow setup-flow's Rails repairs into rails-stack — `scripts/check_manifest_paths.py`** (#2180).
  - **The paths gate.** `checks.json paths` reads each stack's `setup_section` (rails-stack's `setup/rails.md`) as a surface of the plugin that ships `detect_stack.py`, and of no other plugin. That plugin's setup-flow is what runs those sections, so `architecture-boundaries` still finds its `Archspec.rb`. A section that escapes its plugin vouches for nothing. Selftest 18 checks; guard 9 mutations, all caught.
  - **The markdown linters.** `lint_markdown_shell.py` and `lint_markdown_code.py` add `setup` to their roots, so the moved blocks are still linted.
