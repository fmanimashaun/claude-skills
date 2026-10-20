section: rails-flow
- **setup-flow's CLAUDE.md template names no stack — `plugins/rails-flow/commands/setup-flow.md`** (#2196, split from #2180). These now come from each active stack's setup section, under its **`## CLAUDE.md facts`**:
  - the §1 inspection list, the database marker, the stack line and the App Identity rows;
  - the Common Commands and the Project Override and verification examples;
  - the style reference and the test-run preflight's stack checks;
  - the `loop.md` suite, lint and security checks.

  For Rails that is `setup/rails.md`: `pg_isready`, the held `bundler.lock`, rspec, rubocop, brakeman, bundler-audit, simple_form and `style.md`. The audit-and-repair, §0 and §1b wording is stack-neutral too.

  `lint_self_consistency.py`'s `setup-flow-preflight` rule is re-pointed. The template must keep its neutral preflight (the stack's checks, test paths, load, no mid-sweep swaps, the advice label). Every shipped stack's setup section must carry a `### Test-run preflight` under `## CLAUDE.md facts`, and Rails' must keep `pg_isready` and `bundler.lock` there, not elsewhere in the file. Its guard has three new mutations and is 237 of 237 caught.

  The template's remaining Rails line (the structural map's graph node kinds) moves with the graph generators. Our own design (#2162, owner ruling on #2180), not a framework claim.
