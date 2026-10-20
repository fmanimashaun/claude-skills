section: Repository hygiene
- **Our own gate fixtures no longer fail when our rails-flow `git-shim` is on PATH — `scripts/hermetic_git.py`** (#2190). Every agent session runs with the shim first on PATH, and it rightly refuses a fixture's `git add .`, `git add -A` or `git config filter.*`. So four gates were red in every agent shell and green only with PATH stripped by hand:
  - `check_upstream_docs` selftest;
  - `vendored alone` (the wiki and generated-docs selftests);
  - the `where-stopped` helper;
  - the doctor's own selftest.

  `hermetic_git.env()`, which builds the environment of every subprocess the gate and mutation runners launch, now drops the rails-flow shim from PATH. It matches the session hook's own pattern (`rails-flow(/<version>)?/git-shim`), so another tool's `git-shim` directory stays. Measured through that environment with the shim on PATH, the four gates go from exit 1 to exit 0. `scripts/mutation_check_selftest.py` proves it with a stub shim that refuses every command, first on PATH, while a fixture's `git init` and `git add .` still run. The guard has two new mutations (the strip dropped, and the pattern widened to any `git-shim`), 7 of 7 caught.
