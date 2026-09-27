---
name: feedback-read-every-comment-before-implementing
description: The issue body is the oldest text on the page; comments carry the corrections and often the design.
type: feedback
---

On #1072 I implemented from the body alone. Four comments existed. Two were a **measured fact base**
from a parallel session correcting three of the body's figures, and one was a **complete design** for
the instrument to build, with acceptance criteria. I shipped the body's stale table (`49` controllers,
not `48`; components `64`, not `61`; `app/javascript/controllers` missing entirely) into doctrine, a
CHANGELOG entry, a `.skill` bundle and a `checks.json` `why` — four copies — and built a different
gate than the one designed. The maintainer had to ask *"can you read every comment on the issue?"*

**Why:** the body is the oldest text on the page and is never re-verified by the person who filed it.
CLAUDE.md already says an issue body is a hypothesis, not an authority — but the correction to that
hypothesis is usually sitting in the comments, written by someone who went and measured. On a repo
with parallel sessions, a comment is where another agent's measurement lands.

**How to apply:** `gh issue view <n> --comments` before writing any code, not after. Read the body's
edit state too — a body may have been corrected in place after you first read it. Where a comment and
the body disagree on a number, **measure it yourself** rather than picking a side; I had
`Retask-platform` on disk the whole time and `git ls-tree -r --name-only origin/dev -- app/<layer>`
settled it in one command.

Related: [[a-count-of-a-string-is-not-a-count-of-the-thing]],
[[a-number-two-sessions-agree-on-can-still-be-wrong]], [[downstream-runs-beat-code-review]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, read-every-comment-before-implementing.md._
