---
name: feedback-never-pass-backticks-through-double-quotes
description: Commit messages and PR bodies in this repo are full of backticked identifiers — always use a quoted heredoc or --body-file, never -m "..." or --body "...", or zsh executes them away.
type: feedback
---

Every commit message and PR body I write for `claude-skills` is dense with backticked identifiers
(`aria-controls`, `--limit`, `aria-expanded`). Passing those through a **double-quoted** shell
argument makes zsh treat them as command substitution and silently delete them.

It happened on `9a05d2e`: `git commit -m "…"` turned *"the behaviour table omitted `aria-controls`"*
into *"the behaviour table omitted  while forms.md included it"*, and *"the mixin claimed `Space`
activates"* into *"the mixin claimed  activates"* — losing the two nouns the message existed to
convey. The only visible symptom was `zsh: command not found: aria-controls` buried in the output,
easy to skim past, and the commit was merged before I noticed.

**How to apply:** always `git commit -F -` with a `<<'EOF'` heredoc (quoted delimiter, so nothing
expands), and always `gh pr create --body-file` / `gh issue comment --body-file` writing the file
first. Never `-m "..."`, never `--body "..."`. If a `command not found` line appears in output that
otherwise succeeded, treat it as evidence that text was eaten and check what landed.

Post-merge, a degraded commit message is not worth rewriting shared history over — record the
correct text where it stays readable (the PR body, CHANGELOG, or issue) and say plainly that the
commit message is not the authoritative copy. Related: [[name-where-a-decision-landed]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, never-pass-backticks-through-double-quotes.md._
