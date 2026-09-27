---
name: feedback-a-first-person-record-with-no-author
description: The resumed-session handoff is keyed to the project directory, so "I shipped X" means some session here shipped X.
type: feedback
---

`~/.remember/<project-dir>/remember.md` is keyed on the **project directory**, not the session — the
siblings under that root are one per repository (`…-claude-skills`, `…-Retask-platform`,
`…-fidara-ledger`). Every session in the directory reads it at `SessionStart` **and after every
compaction**, and any of them overwrites it. In one day it was rewritten three times by different
sessions, twice under names in one session's own lineage, which made it read as continuous.

It is written in the first person, and one of its own headings read **"Corrections I made under my
own name — do not re-derive them"** — an instruction to trust the first person in a file whose author
is not recorded. A peer claimed PR #1162 from the line *"#1157 shipped as PR #1162"* and was wrong
with the file open in front of them.

**Why:** this is worse than a PR's `author` field (the shared account) because the author field does
not *claim to be you*. A handoff does, in a voice indistinguishable from memory, at the moment you
have least context — right after a compaction. I read "PR #575 is mine" at the top of this session
and took it at face value; I simply had no occasion to act on it.

**How to apply:** read "I" in a handoff as "some session in this directory", and never cite it as
provenance for a branch, PR or decision. Settle those with the worktree listing in
[[attribute-a-branch-by-its-worktree-path]], which also carries the boundary — an absent row means
*unknown*, not *unowned*. Same class in the other direction:
[[a-dirty-file-in-a-shared-checkout-has-no-author]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-first-person-record-with-no-author.md._
