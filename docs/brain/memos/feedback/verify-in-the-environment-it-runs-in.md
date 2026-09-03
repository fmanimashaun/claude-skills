---
name: feedback-verify-in-the-environment-it-runs-in
description: A test run in an interactive shell can silently exercise different binaries than the hook or script under test will get.
type: feedback
---

When verifying a fix that depends on **which binary resolves**, run the test in the environment the
code will actually run in — not the interactive shell.

Testing a `stop-gate.sh` fix that routes `bundle` through mise, I put a fake `mise` first on `PATH`
and the test "passed" while proving nothing: in an interactive shell `mise` is a **shell function**
(installed by `mise activate`), so a function always beats a `PATH` entry and the real mise ran.
Hooks run **non-interactive**, where the binary at `~/.local/bin/mise` does resolve. Re-tested with
`env -i PATH=... sh -c '...'` and only then saw the routing actually work.

**Why:** `command -v X` returning a bare name rather than a path is the tell that X is a function or
alias. The same trap covers aliases, shell builtins shadowing binaries, and anything a profile
injects — none of which the harness that runs the code will have.

**How to apply:** for hooks and scripts, verify with `env -i` and an explicit `PATH`. If
`command -v` prints something without a `/`, the interactive shell is lying to you about what the
code will find.

Related: [[fix-defects-in-the-same-work]], [[verify-counts-before-stating-them]]

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, verify-in-the-environment-it-runs-in.md._
