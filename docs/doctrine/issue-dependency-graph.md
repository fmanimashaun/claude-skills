# The issue dependency graph

The tracker has always carried dependencies — `#93 → #104 → #94/#90`, `#125 → #127` — but they
lived as prose inside issue bodies. Answering *"what should I work on next?"* therefore meant
re-reading many issues and re-deriving the ordering by hand, which produced a different answer
each time as the tracker grew.

This is the machine-readable version of those edges, and `scripts/issue_graph.py` is the thing
that computes the queue from them. A queue asserted in prose is not a queue.

## Declaring an edge

One fenced block in the issue body, tagged `deps`:

```deps
depends-on: #93, #104
blocks: #94, #90
part-of: #89
```

| Key | Meaning |
|---|---|
| `depends-on: #A` | A must finish before this issue can start |
| `blocks: #B` | the same edge stated from the other end — this issue must finish before B |
| `part-of: #E` | epic membership. Carries **no** ordering |

Rules the parser enforces, all of them reported rather than assumed:

- **The `deps` tag is required.** See *Why the tag* below.
- **One key per line, `#n` references only**, comma-separated. `depends-on: the auth epic` is an
  error, not an edge.
- **No comments inside the block.** A line starting `#` is ambiguous with an issue reference, so
  prose explaining *why* goes outside the fence — where it reads better anyway.
- **The keys are exactly the three above.** `depends_on:` is a reported error, never a silently
  dropped line.
- **Both ends may declare the same edge.** `#93 blocks: #104` and `#104 depends-on: #93` are one
  edge, not two and not a cycle. Declare whichever end you are editing.
- **Repeating a reference is deduped**, not flagged.
- Edges into **closed** issues are normal — that is what a satisfied dependency looks like.

## Running it

```bash
python3 scripts/issue_graph.py                  # fetch via gh, print the queue
python3 scripts/issue_graph.py --json           # same, machine-readable
python3 scripts/issue_graph.py --ready 109 110  # gate: may this work start now?
python3 scripts/issue_graph.py --selftest       # prove the rules fire and stay silent
```

It reports five things:

- **Ready now** — open, every dependency closed. The list that matters day to day.
- **Blocked** — and by exactly what, so a blocker's priority can be reconsidered.
- **Critical path per epic** — the longest remaining chain. A P1 sitting behind three unstarted
  issues is not really the next task. Ties are broken toward the higher-priority branch: a tie
  reported as the lower-priority branch is equally true and sends the reader to the wrong place.
- **Priority vs graph**, in both directions — `P1-but-blocked`, and the costlier
  `low-priority-blocking-P1`.
- **Coverage** — how many open issues declare no edges at all.

That last one is the honest part. Edges are **declarations, not discoveries**: the tool knows what
the tracker says, and the coverage line states how much of the tracker said nothing. Without it a
short "ready now" list reads as complete knowledge when it may be three declared edges out of forty
open issues.

## Starting work — `--ready`, the gate at the point of use

Reporting an order changes nothing on its own. `/maintainer-work` said *"take the head of the
triaged queue"* while nothing checked that it had — the same prose-not-a-queue problem this file
opens with, one level up. So the queue is also a gate, asked at the moment work starts:

```bash
python3 scripts/issue_graph.py --ready 109 110
```

**Exit 1, with the refusal on stderr and stdout left empty**, when any named issue waits on open
work, is already closed, is absent from the tracker, or when the graph is too broken to answer
from. Exit 0 and a `READY` line on stdout otherwise — so a caller reading stdout alone cannot
mistake a refusal for a go-ahead. `/maintainer-work` runs it in Phase 0, before branching.
(`--ready <n> --json` is the deliberate exception: it writes the verdict object to stdout either
way, and the exit code still carries it.)

Name **every issue going on the branch**. Grouping related issues onto one branch is this
repo's default shape (CLAUDE.md, *Grouping related issues on one branch*), so an edge *between*
two issues you named is satisfied by the branch itself and only decides which of them you do
first — reported as a note. An edge *leaving* the set is not satisfied, and adding an unrelated
issue to the set cannot launder a blocker away. Concretely, with `#110 depends-on: #109`:

| Call | Verdict |
|---|---|
| `--ready 110` | **NOT READY** — waits on open `#109` |
| `--ready 109 110` | **READY**, with a note to do `#109` first on the branch |
| `--ready 110 42` | **NOT READY** — `#109` is still outside the set |

A dependency on a **closed** issue is not a refusal: that is what a satisfied prerequisite
looks like, and treating it as a block would make every finished edge permanent.

**A READY verdict says what it does not know.** On an issue that declares no edges it prints a
note: the tracker names no blocker, which is not the same as nothing blocking it. Until the epic
backfill lands that is the common case, and reporting the first as the second would be the
`unverified-negative` class from `skills/code-review/SKILL.md` — a green light nobody could
calibrate. An issue that *did* declare gets no note, because a caveat on every verdict is a
caveat nobody reads.

Going out of the computed order is allowed; doing it silently is not. Say so in the PR body.

## What fails, and what only advises

This follows the general rule: **fail closed for gates, fail open for advisories** — now recorded in
[`doctrine/harness-doctrine.md`](doctrine/harness-doctrine.md) §5, which also states the scoping this tool relies on
(fail closed for what the gate guards, exit 0 otherwise). It is still restated here as this tool's own
contract, because a reader of this file should not have to follow a link to learn what exits non-zero.
Note that CLAUDE.md's *Platform* sentence remains narrower than the general rule — it says only that
*hooks* fail open when a dependency is missing, which is true of seven hooks and false of two.

**Exit 1 — the graph is wrong.** A cycle; an edge to an issue not in the tracker; a
self-reference; a typo'd key; a malformed line; a declaration outside its fence; declarations
under the wrong fence tag. Each is a *filing* error, fixable by editing the issue.

When any of these fire, **no queue is printed at all** — only the errors. This is deliberate and it
is the property that makes the script a gate rather than a report: a ranked queue computed from a
graph we already know is broken reads exactly like a correct one, and would be trusted the same way.

**Exit 1 — `--ready` was asked and the answer is no.** Distinct from the above: the graph is
fine, the *pick* is not. Blocked work is only an advisory while you are reading the queue; it
becomes a refusal the moment you say you are about to start it. Same fail-closed rule, so an
invalid graph refuses to answer `--ready` at all rather than guessing.

**Exit 0 — everything else.** Blocked work, priority contradictions and thin coverage are all
reported, none of them fail. They are judgement calls for a maintainer, and a gate that fails on
judgement calls gets switched off.

`--limit` bounds the `gh` query, and a page that comes back **full** is an error rather than a
total: bounding a query proves nothing about whether it truncated, and a truncated tracker turns
real edges into phantom "issue not in the tracker" errors. That is #211's lesson applied to the
tool's own input.

## Why the tag is required

#133 sketched a bare fence. A bare fence cannot be distinguished from a code sample, and
`depends_on: :owner` is an ordinary Rails association that appears in this repo's own issue
bodies — it would be read as an edge.

Requiring a tag makes extraction unambiguous, but strictness that silently drops a near-miss is
the `gate-that-cannot-fail` class from `skills/code-review/SKILL.md`: nobody would ever learn
their block was invisible. So the two near-misses are **detected and reported**:

- a fence whose content is **nothing but declarations** under some other tag (or none) — "tag it
  ```deps or it declares nothing";
- a declaration line **loose in prose**, outside any fence.

Being strict about the tag is only safe because missing the tag is an error rather than a silence.
Both detectors are deliberately narrow — they require the canonical `key: #n, #n` shape and nothing
else on the line — so that prose which merely mentions an edge ("Blocks #94 and #90, but only once
the schema lands") stays silent. A checker that fires on ordinary sentences gets switched off after
the third false positive and then catches nothing at all. The selftest pins both directions.

This format is **ours**; it has no upstream to cite. Per `CLAUDE.md`'s carve-out for
design/architecture changes, the authority is the maintainer decision recorded on #133.

## Backfilling an existing issue

Append the block to the body — it can sit anywhere, but the end is conventional:

```bash
set -euo pipefail
body=$(mktemp)
trap 'rm -f "$body"' EXIT
gh issue view 104 --json body --jq .body > "$body"
if grep -q '^```deps' "$body"; then
  echo "#104 already declares a deps block — edit that block, never append a second" >&2
  exit 1
fi
printf '\n```deps\ndepends-on: #93\nblocks: #94, #90\npart-of: #89\n```\n' >> "$body"
gh issue edit 104 --body-file "$body"
```

Most of that is guard rather than step, and each guard is here because the shorter version of
this snippet was a hazard rather than a convenience:

- **`set -euo pipefail` before anything else.** `>` truncates its target *before* the command
  on the left runs, so a failed `gh issue view` — expired auth, wrong number, no network —
  leaves an empty file. Without `set -e` the next two lines still run, and `gh issue edit`
  then replaces the entire issue body with nothing but the deps block. That is a destroyed
  report on a shared tracker, from a procedure whose only visible symptom is success.
- **`mktemp`, not a fixed `/tmp/body.md`.** Two backfills in parallel would otherwise write
  each other's bodies.
- **The `grep` guard, because appending twice is silent.** The parser reads *every* `deps`
  fence in a body, so a duplicate block raises no error — and a duplicate that has since
  drifted quietly contributes edges nobody wrote on purpose. Idempotency here has to be
  checked, not hoped for.

Then re-run `python3 scripts/issue_graph.py` and confirm the edge appears and nothing broke —
and `--ready` on the issue you just edited, since that is the verdict the edit changes.
