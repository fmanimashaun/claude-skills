---
name: feedback-a-dirty-file-in-a-shared-checkout-has-no-author
description: A shared artifact carries no author — a dirty file, a /tmp draft, a comment on a busy issue. Measure ownership from timelines and bytes, never from what is lying around.
type: feedback
---

Two collisions in one hour on 2026-09-17, both in the shared `claude-skills` checkout, both
because **an uncommitted edit carries no author**.

1. I arrived on a branch a peer session had pushed (`feature/1004-parallel-session-protocol`),
   read PR #1005 as mine to finish, and **merged it into `dev` on green** before its author's
   message reached me. Nothing was lost, but closing out another session's work was not mine to do.
2. Minutes later the same peer read ` M scripts/build_maintainer_skills.py` in that checkout and
   announced it as **their** uncommitted work. It was mine, and this is now settled rather than
   contested: they had written nothing, in this repo or anywhere else. They conceded on evidence
   within two minutes.

**Why:** `git status` prints modifications with no author. `git log` and `git blame` answer "whose
is this" and an uncommitted edit is invisible to both — so in a shared tree the only reading
available to either session is "mine". Announcing paths first (the parallel-session protocol's §2)
does not fix it, because the announcement and the dirty file are in different media.

How I settled it, since a peer's confident claim is not evidence — each of these is worth running
before conceding or insisting: `git worktree list` (one worktree, so no second checkout existed;
the ones under other sessions' scratchpads read `gitdir: …/Retask-platform/.git/worktrees/…`);
the `git pull --ff-only` that had **succeeded** minutes earlier, which would have refused with a
local modification to a file it was updating; and my patch script's `assert src.count(anchor) == 1`
on the *unmodified* lines, which could not have passed if their edit had been in the file.

**What actually settled it was the other session's own reflog and mtimes, not my three checks** —
worth reaching for first, because it is two commands and it works from either side:
`git reflog --date=iso` gave `15:59:58 checkout: moving from dev to fix/1004-unregistered-mirror-gate`,
and `stat` gave 16:00:32 / 16:01:22 / 16:01:48 on the three files — every write after that checkout,
in a session that had run no Write or Edit at all. Ownership is a timeline question, and the
timeline is on disk.

**How to apply:** commit early in a shared tree, even a WIP, so ownership is a `git log` away —
better still, take a worktree, per [[confirm-your-branch-not-just-your-repo]]. Do not merge or
close out a PR you did not open without asking its author session first; green and mergeable says
the code is ready, not that the work is yours. When a peer claims your diff, measure before
conceding — [[verify-counts-before-stating-them]] applies to ownership too — and when you are
wrong, say so in one line and hand it back.

## It is not only git, and not only files (2026-09-22)

Two more instances in one day, same class, neither involving `git status`:

- **`/tmp` is shared across sessions.** A peer wrote a draft to `/tmp/c1154.md`, a hook read a file
  of that name already there, and they concluded it was mine and told me to use my scratchpad. I
  already was. `cmp` settled it in one command: their file was 4621 bytes beginning *"Correcting my
  own framing"*, mine was 2549 bytes in the session scratchpad beginning *"An independent
  reproduction"*. **Different files.** Their underlying advice was right and their attribution was
  wrong.
- **A comment on a busy issue.** The same peer corrected me for a fix proposed in a *different*
  session's comment on the same issue — three sessions had commented within an hour. Listing the
  comments with timestamps and first lines showed mine proposed no fix at all.

**How to apply:** when someone attributes an artifact to you, or you are about to attribute one to
them, find the bytes or the timeline before answering — `cmp`, `stat`, `ls -la`, the comment list
with timestamps. Never infer an author from what is lying around at a path. Correct the addressing
in one line and keep their technical content, which is usually still right
([[a-true-result-about-the-wrong-file]]). And write drafts to the session scratchpad, never `/tmp`,
because a name collision there is silent.

## The worst version: an artifact that claims authorship in MY voice (2026-09-22)

I told two sessions that claude-skills PR #1162 was mine and needed no rebase. Both halves were
wrong. It belongs to session `925034d0`; I am `821cdbc6`.

I did not infer it from the PR — I read it out of the handoff file:

    ~/.remember/-Users-fmanimashaun-projects-claude-skills/remember.md

which says, in the first person, *"#1157 shipped as PR #1162"*. **That path is keyed on the PROJECT
DIRECTORY, not the session.** Every session in the working directory is handed the same file at
SessionStart *and again after every compaction*, and any of them can overwrite it — it was rewritten
at least three times in one day. So a first-person sentence in it means "some session here did
this", with no field saying which, and session names rotate so the names inside do not carry it
either.

This is worse than a dirty file or a `/tmp` collision, which are merely ambiguous. A handoff
**asserts** authorship, in my own voice, arriving exactly when a compaction has removed my ability
to check it against my own memory of the turn.

**The one artifact that is per-session by construction is the lane path**, because it contains the
session id:

    MINE=<my scratchpad session uuid>
    git worktree list --porcelain | awk -v m="$MINE" '/^worktree /{w=$2} /^branch /{if (w ~ m) print w}'

A `+` prefix in `git branch -a --list '<pattern>'` says the same thing from the other side: checked
out in **another** worktree. Boundary a peer measured and I confirmed: **a branch whose worktree has
been removed keeps its commits and its PR and loses its row**, so no row does not prove no owner —
pair it with `git rev-list --count origin/dev..<branch>` over every local branch before reading
silence as absence.

**How to apply:** never claim a PR, branch or issue from the handoff file. Treat every first-person
sentence in it as "a session in this directory", and confirm with the worktree path before
asserting ownership to anyone. Same when correcting a peer — I corrected one session's attribution
error and made the identical one in the same message
([[a-value-two-causes-both-produce]]: I read a post-rebase tree and named the wrong cause for why
it was clean).

Related: [[assert-ancestry-not-merge-output]], [[fix-defects-in-the-same-work]],
[[a-true-result-about-the-wrong-file]], [[refusing-to-guess-is-a-contribution]],
[[confirm-your-branch-not-just-your-repo]], [[a-value-two-causes-both-produce]]

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-dirty-file-in-a-shared-checkout-has-no-author.md._
