---
name: feedback-fix-defects-in-the-same-work
description: When a defect surfaces mid-work in claude-skills, fix it in the same branch — filing it as an issue instead is only acceptable when it is structurally unrelated to the work in hand.
type: feedback
---

When I find a defect while working on something else in `claude-skills`, **fix it in the same branch**.
Filing an issue is the exception, reserved for a defect that is *structurally* unrelated to the work in
hand — not merely one that would widen the branch.

**Why:** I had been reaching for "file it, don't widen the branch" as the disciplined choice, citing
release-cadence and bisectability. The maintainer's correction: filing defers real work and grows a
backlog, and the branch being bigger is cheaper than the defect staying shipped. It also fits the
grouping doctrine already in CLAUDE.md — related work belongs on one branch, and a defect the work
*surfaced* is related by construction.

Concretely, I filed #248 (nothing syntax-checks the JS/Ruby in our markdown fences) after hitting a real
ASI hazard in `focus_trap.js` that only a hand-run `node --check` caught, and argued for filing because
the new linter would first need its existing findings fixed. That reasoning was wrong about *what* to
do — build it, fix what it finds, then wire the gate, all in the same work.

**How to apply:** ask whether the defect touches the same files, mechanism, or guarantee as the work in
hand. If yes — fix it now, with its own commit, its own CHANGELOG bullet, and `Refs #n` for each issue.
Only a genuinely separate subsystem gets filed. Related: [[name-where-a-decision-landed]],
[[verify-counts-before-stating-them]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, fix-defects-in-the-same-work.md._
