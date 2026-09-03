---
name: feedback-downstream-runs-beat-code-review
description: Defects worth fixing come from RUNNING things, not reading them — four repos read produced zero fixes; the fifth paid off only because its linter was run against our own corpus.
type: feedback
---

Weight a defect by **how it was found**. On claude-skills, running the toolchain against a real
project finds real bugs; reading other people's repositories for ideas generates issues that never
get built.

Evidence, 2026-08-16: 17 issues closed across 8 releases, and every one came from a downstream run or
from the maintainer reading published output — the four band-matching defects, compose's anatomy
blindness, the surface-relevance gap, the wiki publishing `>-`, a deploy briefing that booted local
dev in production, a Stop gate reporting RED on a green suite. The five issues filed the same morning
from reviewing `swarm-forge`, `jsm-agent-skill` and OpenKB produced **zero** fixes and were all still
open at the end.

Fourth data point, 2026-08-20: analysed `nextlevelbuilder/ui-ux-pro-max-skill` (118k★) and produced
nine accurate findings about *their* repo and **zero** items worth filing here. All three "worth
stealing" takeaways failed when measured against our own tree: the count-gate rule had no defect
behind it (`"eleven specialist subagents"` in `marketplace.json` matches the 11 files in
`plugins/rails-flow/agents/`); the put-the-rule-in-the-failure-output pattern is already implemented
and *mutation-guarded* here (`blast_radius.py`, `extract_claims.py`, `check_token_contrast.py`); and
the calibration/held-out split was reached for by analogy — it addresses a drifting human oracle, and
our drift gates' oracle *is* the generator.

**Why:** the toolchain's failures are environmental and compositional — a shell that resolves a
different binary, a manifest whose prose does not overlap a band label, a file at a path foreman
reads. None is visible in the source, and reading a comparable repo suggests features rather than
exposing faults. The specific trap is **analogy**: another repo's good pattern implies a problem we
may not have, and the proposal arrives already dressed as a fix.

**How to apply:** before proposing anything learned from another repo, **measure the defect in our
tree first** — name the file and the failing value. No defect, no proposal.

**The one external-repo read that paid off did it by RUNNING their tool on our corpus, not reading
their code.** 2026-08-20, `marcoroth/herb` (HTML-aware ERB parser). **Correction, 2026-08-21: there IS a gem** —
`herb` 0.10.3 with native precompiled builds, whose `herb analyze` exits 1 on findings. The earlier
"no gem, no compile" was how I happened to run it, not a fact about the project. The *linter* is the
npm-side half (`npx @herb-tools/linter`); the `herb-linter` gem is 0.0.1 and an empty module: pointed its linter at all 119 `erb` blocks extracted from our markdown and got 78
offenses, of which ~65 were our own documentation elisions or a Herb false positive on ViewComponent
brace-form slot writers — but 10 were a real class, conditional HTML attributes built by interpolating
raw strings into attribute position, one via `.html_safe`, in `fidara-design` component doctrine that
already uses `tag.attributes` correctly elsewhere in the same file. So: when an external repo ships an
executable checker for something we ship as prose, **run it against our tree**. Reading it would have
found nothing, exactly as the four repos before it.

When the backlog is all self-generated, recommend *stop building, keep using* rather than picking the
next item; say so plainly, since the maintainer has repeatedly wanted the call and not a survey. Be
willing to propose closing the speculative ones outright.

Related: [[maintainer-works-in-momentum]], [[fix-defects-in-the-same-work]],
[[verify-counts-before-stating-them]]

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, downstream-runs-beat-code-review.md._
