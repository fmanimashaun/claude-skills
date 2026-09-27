---
name: feedback-a-run-owns-its-worktree
description: A suite or mutation run owns its worktree for its duration, like its database; editing files mid-run makes the result meaningless and it still looks fine.
type: feedback
---

Twice in one evening I edited files in a worktree while a full suite was executing in it — once
mutating an app file during a background run, once editing a spec file and running a targeted rspec
against the same tree. **Both results were meaningless, and both looked fine.** I killed and re-ran
each rather than quoting them.

**Why:** RSpec loads spec files at startup and reads app files as it goes, so an edit mid-run lands
in an undefined place — some examples see the old tree, some the new, and nothing reports a
discrepancy. It is the same class as
[[a-harness-that-cannot-see-a-broken-mutation]]: the run produces a number, and the number is not
about the code you think it is about.

**How to apply:** a run owns its worktree for its duration, exactly as it owns its database
([[a-ratchet-inherits-the-last-runs-state]]).

- Before **starting** a long run: `git status --porcelain` empty, and every edit final.
- Before **editing**: check nothing is running in that tree — `pgrep -fl rspec` is one command and
  it also shows peers' runs, which is how I found another session's suite on its own database.
- A run that was touched is **not a weak result, it is no result**. Kill it and re-run; do not
  report it with a caveat.

Resolve is not the mechanism — the mechanism is treating the tree as owned, and taking the
one-command look before typing. Related: [[an-unpushed-branch-in-a-scratch-worktree]],
[[a-dirty-file-in-a-shared-checkout-has-no-author]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-run-owns-its-worktree.md._
