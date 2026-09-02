#!/usr/bin/env python3
"""Map every doctrinal claim in this repo to the thing that makes it true -- or to nothing.

Run:  python3 scripts/doctrine_map.py                    # rebuild docs/doctrine-map.html
      python3 scripts/doctrine_map.py --check             # drift gate (compares the blob at HEAD)
      python3 scripts/doctrine_map.py --audit-coverage    # which doctrine sources have no rows
      python3 scripts/doctrine_map.py --selftest          # prove each validator fires AND stays silent

WHY THIS EXISTS (#655). One question got asked by grep more than once a session: *which claim in
our markdown is made true by which gate, and which claims are made true by nothing?* That last set
is this repo's most frequently filed defect class -- claims-vs-enforcement -- and we were finding
them one accident at a time: nothing read the manifest's `use_cases` (#639), nothing gated
`marketplace.json` completeness (#651), `--check || echo` made a release gate unable to block (#151).

WHY THERE IS NO EXTRACTOR, WHICH IS THE WHOLE DESIGN. The issue named its own biggest risk: pulling
"a claim" out of prose is the hard part, and **a bad extractor is worse than none, because a map that
misses claims reads as coverage.** So nothing here parses prose for claims. `CLAIMS` below is an
explicit registry, in the same file as the validators that check it -- the shape
`maintainer_doctor.GATES` and `mutation_check.GUARDS` already use, so a registry and its checker
cannot drift apart into two files.

WHAT THIS IS HONESTLY NOT. The map is a **floor, not a ceiling.** `--audit-coverage` can tell you a
declared doctrine source has *no* rows; nothing here can tell you a source with four rows was not
owed nine. Treat a row count as evidence that someone looked, never as proof the file is covered.
Saying so in the tool is the point: the failure mode this replaces is a green artifact standing in
for work nobody did.

WHY NOT OpenKB, which prompted the issue. It compiles documents into a wiki **with an LLM**, so the
output bytes are not a function of the inputs and no drift gate could hold them -- and
`derived-artifacts` is the rule we enforce on `coverage.html`, `inventory.html` and the wiki. Take
the idea, not the tool: generated deterministically, drift-checked like everything else.

WHAT THE VALIDATORS ACTUALLY CATCH. Each is mechanical -- no judgement, so none of them is taste
wearing a count (#476):

  * `anchor missing`        -- the claim was reworded or deleted in the markdown and the map still
                              advertises it. This is the row going stale in the visible direction.
  * `unresolved enforcement` -- the row cites a gate/guard/rule/script that no longer exists. The map
                              claiming enforcement that is gone is the exact defect class the map is
                              for, committed inside the map.
  * `unenforced guarantee`  -- kind is `guarantee` and nothing is cited. A guarantee with nothing
                              behind it is either a `gap` (say so, with an issue) or advice.
  * `untracked gap`         -- kind is `gap` with no issue number. A gap nobody filed is a shrug.
  * `resolved gap`          -- kind is `gap` and enforcement now resolves. The row got fixed and
                              never reclassified: the map going stale in the direction nobody looks.
  * `undeclared source`     -- a row points at a file `DOCTRINE_SOURCES` does not list, which means
                              the declared surface is wrong rather than the row.

WHAT IS DELIBERATELY NOT A FAILURE. An `advice` row with no enforcement is correct and common --
`art-direction.md` argues at length that gating judgement is worse than not gating it, and
`quality-pass` never blocks a merge on purpose. The classification, `guarantee` vs `advice`, is
`docs/harness-doctrine.md`'s existing test ("if a model ignores this, what happens?"), so this file
introduces no new vocabulary for it.

THE PAGE STAMPS NO VERSION, unlike `coverage.html`. That page is copied between machines, so the
release version is its only freshness signal; this one is read in-tree beside the sources it
describes, where the drift gate *is* the freshness signal. Fewer non-content inputs, fewer ways to
be unpassable by construction -- which both committed pages here have been, once each.

Exit codes:  0 = clean · 1 = at least one finding · 2 = not this repo

Stdlib only.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PAGE = "docs/doctrine-map.html"

GUARANTEE, ADVICE, GAP = "guarantee", "advice", "gap"
KINDS = (GUARANTEE, ADVICE, GAP)


@dataclass(frozen=True)
class Claim:
    """One doctrinal claim, where it is stated, and what makes it true.

    `anchor` is a short distinctive fragment that must appear verbatim in `stated_in`. It is not the
    whole sentence on purpose: a fragment survives ordinary copy-editing, and when it does break, the
    break is the signal -- someone reworded a claim and should re-check what enforces it. That is the
    same accepted friction as a `mutation_check` anchor, which is house style here rather than a new
    idea.
    """

    claim: str
    stated_in: str
    anchor: str
    kind: str
    enforced_by: tuple[str, ...] = ()
    refs: tuple[int, ...] = ()
    note: str = ""


# Every file whose prose this map considers doctrinal. Declared rather than globbed, because the
# audit's only honest question is "does a source we call doctrine have zero rows" -- and a glob would
# answer it about files nobody decided were doctrine.
# ---------------------------------------------------------------------------------------------
# THE SHIPPED SURFACE (#798) — the doctrine other people's agents follow, as opposed to the
# repo-process doctrine below.
#
# WHY THIS IS A SECOND LIST. `DOCTRINE_SOURCES` requires every entry to carry at least one row, and
# rightly: those eleven files were mapped deliberately. The shipped skills are ~46 files nobody has
# mapped yet, and declaring them there would fail the `doctrine map coverage` gate with 46 findings
# on the first run -- red on day one, switched off in a week, which is the failure #800 spent a whole
# issue removing. Bulk back-filling rows to make it green is worse still: this file already says
# "a green artifact standing in for work nobody did is the failure this replaces".
#
# SO IT RATCHETS, the same instrument as #800. The mapped count may not fall below `SHIPPED_FLOOR`.
# Never red on day one -- the floor is what is mapped today. Never slides -- deleting a row fails.
# Rises deliberately: map a source, raise the floor in the same commit.
#
# The gap is now TRACKED rather than invisible. Before this, "which shipped claim is enforced by
# nothing?" could not be asked at all: a source never declared reports nothing, forever, and #779
# said so in its own text -- "its 32 rows are repo-process claims, so this shipped-setup claim has
# no row and no enforcement column". Three claims (#778/#797, #779, #792) were each found by a
# downstream project one at a time because of it.
SHIPPED_SOURCES: tuple[str, ...] = tuple(sorted(
    p.as_posix()
    for skill in ("rails-8", "hotwire", "design-system")
    for p in (REPO / "skills" / skill).glob("**/*.md")
    if p.is_file()
    for p in [p.relative_to(REPO)]
))

# FILES mapped, not rows. Five rows in one file is not broader coverage of the surface, and the
# question this tracks is "how much of the shipped doctrine has anyone looked at". Raise it in the
# same commit that maps a new FILE. It is a floor, never a target: mapping all 49 is not the goal,
# and a row count is evidence someone looked, never proof a file is covered.
SHIPPED_FLOOR = 2

DOCTRINE_SOURCES = (
    "CLAUDE.md",
    "AGENTS.md",
    "docs/harness-doctrine.md",
    "skills/code-review/SKILL.md",
    "skills/quality-pass/SKILL.md",
    "skills/derived-artifacts/SKILL.md",
    "skills/parallel-session-lane/SKILL.md",
    "plugins/rails-flow/commands/feature.md",
    "plugins/rails-flow/commands/handoff.md",
    "plugins/rails-flow/commands/fix.md",
    "plugins/design-flow/commands/generate.md",
)

CLAIMS: tuple[Claim, ...] = (
    # ---- the SHIPPED doctrine (#798) ------------------------------------------------------
    # Five claims that already have gates to cite. Deliberately not more: a row nobody derived is
    # the green artifact this file exists to replace, and `SHIPPED_FLOOR` tracks the rest as
    # unmapped rather than pretending they are covered.
    Claim(
        claim="The prescribed testing stack is not a menu — a project missing simplecov, webmock "
              "or vcr is incomplete, not merely different.",
        stated_in="skills/rails-8/references/testing.md",
        anchor="group :development, :test do",
        kind=GUARANTEE,
        enforced_by=("script:plugins/rails-flow/scripts/check_mandated_gems.py",
                     "script:scripts/derive_mandated_gems.py",
                     "mutation:check_mandated_gems", "mutation:derive_mandated_gems"),
        refs=(778, 797),
        note="The list is DERIVED from this fence and committed beside the checker; a runtime read "
             "would cross from rails-flow into rails-stack, which is #617's class. 15 gems were "
             "written as literal `gem` lines while 4 were installed and 2 were checked.",
    ),
    Claim(
        claim="`--skip-test` leaves `config/ci.rb` with no test step, so `bin/ci` reports green "
              "having run zero specs unless the step is added back.",
        stated_in="skills/rails-8/references/testing.md",
        anchor="There is nothing to",
        kind=GUARANTEE,
        enforced_by=("script:plugins/rails-flow/scripts/check_ci_runs_tests.py",
                     "mutation:check_ci_runs_tests"),
        refs=(391, 779),
        note="#391 fixed the doctrine and said the enforcement half was still open. The gate keys "
             "on the step's COMMAND, never its label: a step named `Tests` that runs rubocop is the "
             "exact false confidence it refuses.",
    ),
    Claim(
        claim="`spec/support/**` is dead until the auto-loader Rails generates COMMENTED is "
              "uncommented — every support file, with no error and no output.",
        stated_in="skills/rails-8/references/testing.md",
        anchor="Auto-load spec/support/**",
        kind=GUARANTEE,
        enforced_by=("script:plugins/rails-flow/scripts/check_spec_support.py",
                     "mutation:check_spec_support"),
        refs=(803,),
        note="Same shape as the `Tests:` step Rails omits under --skip-test: a generated default "
             "the doctrine says to change, with nothing verifying it was changed. The gate also "
             "refuses a capybara no spec drives.",
    ),
    Claim(
        claim="Coverage gates on the DROP, never an absolute number — a fixed `minimum_coverage` "
              "is inert below the repo and red above it.",
        stated_in="skills/rails-8/references/testing.md",
        anchor="refuse_coverage_drop",
        kind=GUARANTEE,
        enforced_by=("script:plugins/rails-flow/scripts/check_coverage_ratchet.py",
                     "mutation:check_coverage_ratchet"),
        refs=(800,),
        note="Maintainer decision: \"gate is the key, advise can be ignored\". Consistent with "
             "quality-pass rather than an exception to it — that refuses to gate JUDGEMENT, and a "
             "drop is a measured regression against a recorded baseline.",
    ),
    Claim(
        claim="simple_form is mandatory in this stack — no form, and no form element, is built any "
              "other way.",
        stated_in="skills/rails-8/references/ecosystem-gems.md",
        anchor="simple_form is mandatory in this stack",
        kind=GUARANTEE,
        enforced_by=("script:plugins/rails-flow/scripts/check_mandated_gems.py",
                     "mutation:check_mandated_gems"),
        refs=(778,),
        note="Two of the three `Always` gems already had gates (archspec, herb, each applies_when "
             "its config exists). This one had neither an installer nor a check, and was missing "
             "on both affected scaffolds.",
    ),

    # ---- the release flow -------------------------------------------------------------------
    Claim(
        claim="A promotion merges with `--merge`; a squash drops dev's ancestry and the NEXT "
              "promotion cannot merge at all.",
        stated_in="CLAUDE.md",
        anchor="Merge a promotion with `--merge`. A squash breaks the NEXT one.",
        kind=GUARANTEE,
        enforced_by=("script:scripts/maintainer_doctor.py", "mutation:maintainer_doctor"),
        note="Asserted by the doctor's `the last promotion carried dev's ancestry` check, which asks "
             "both halves -- is main's tip a merge, AND does it have a parent on dev. It is a "
             "DIAGNOSTIC, so --gates-only skips it; run the full doctor before a promotion.",
    ),
    Claim(
        claim="A version number is never assigned on a merge into `dev`, because on `dev` the claim "
              "that a user can install it is false.",
        stated_in="CLAUDE.md",
        anchor="Versions are assigned at the promotion, never on a merge into `dev`",
        kind=ADVICE,
        note="A stray bump on dev is a loaded gun -- the next promotion publishes whether or not "
             "anyone decided to ship. Nothing detects it: the workflow cannot tell an intended bump "
             "from an accidental one, and a gate that refused a bump on dev would refuse the arm "
             "commit, which is the one place it belongs.",
    ),
    Claim(
        claim="Every component bump gets a CHANGELOG entry under that component's section.",
        stated_in="CLAUDE.md",
        anchor="**Every bump gets a CHANGELOG entry**",
        kind=GUARANTEE,
        enforced_by=("rule:changelog-section-missing", "gate:self-consistency"),
    ),
    Claim(
        claim="One `### … (release vX.Y.Z)` block per actual promotion -- headings for versions that "
              "never get tagged make their notes vanish from the published release.",
        stated_in="CLAUDE.md",
        anchor="One `### … (release vX.Y.Z)` block per COMPONENT that this promotion bumps",
        kind=GUARANTEE,
        enforced_by=("rule:duplicate-unreleased", "rule:duplicated-release-extractor",
                     "gate:self-consistency", "gate:release notes complete",
                     "mutation:extract_release_notes"),
        note="#699 rewrote both the claim and its enforcement. `duplicate-unreleased` catches two "
             "`### Unreleased` headings in one section; `release notes complete` runs the real "
             "extractor and refuses any block written for the tag that would not publish, which is "
             "the half that was missing while four releases dropped a component's notes.",
    ),
    Claim(
        claim="`dist/` must be a clean build of `skills/**` before a release publishes.",
        stated_in="CLAUDE.md",
        anchor="The CI drift guard fails",
        kind=GUARANTEE,
        enforced_by=("script:scripts/package_core.py", "hook:.github/workflows/release.yml",
                     "hook:.github/workflows/gates.yml"),
        note="Checked in BOTH workflows on purpose: a diagnostic is not a gate, and `--gates-only` "
             "(what CI runs) skips the doctor's drift diagnostic.",
    ),

    # ---- claims-vs-enforcement, the class this map is about ---------------------------------
    Claim(
        claim="A guarantee stated in prose that nothing makes true is a defect, not a style issue.",
        stated_in="skills/code-review/SKILL.md",
        anchor="gate-that-cannot-fail",
        kind=GUARANTEE,
        enforced_by=("script:scripts/lint_self_consistency.py", "gate:self-consistency",
                     "mutation:lint_self_consistency"),
    ),
    Claim(
        claim="A verification command whose verdict is swallowed by `|| echo` or `|| true` cannot "
              "block anything.",
        stated_in="CLAUDE.md",
        anchor="**swallowed verdicts**",
        kind=GUARANTEE,
        enforced_by=("script:scripts/lint_markdown_shell.py", "gate:markdown shell lint"),
    ),
    Claim(
        claim="A lint that reports clean on input it never read is worse than no lint, so every "
              "fenced block must be provably reached.",
        stated_in="CLAUDE.md",
        anchor="a lint that reports clean on input it never read is worse than no lint",
        kind=GUARANTEE,
        enforced_by=("gate:markdown shell coverage", "gate:markdown code coverage"),
    ),
    Claim(
        claim="A count or environment fact is re-measured against the live source at the moment it "
              "is stated, never carried forward from earlier in the session.",
        stated_in="AGENTS.md",
        anchor="## Measure before you assert",
        kind=ADVICE,
        enforced_by=("rule:unbounded-issue-query",),
        note="Only the mechanical half is enforceable: an unbounded `gh issue list` measures one page "
             "carefully and calls it the total. Whether a stated number was actually re-run cannot be "
             "observed from the tree, so the rest is advice -- and it has already been got wrong.",
    ),
    Claim(
        claim="A carve-out that silences a check needs a negative test proving the check still fires "
              "outside it.",
        stated_in="skills/code-review/SKILL.md",
        anchor="carve-out-without-negative-test",
        kind=GUARANTEE,
        enforced_by=("script:scripts/maintainer_doctor_selftest.py", "mutation:maintainer_doctor"),
        note="`CORPORA_GATES` is pinned EXACTLY, in both directions, so re-adding a member takes a "
             "deliberate edit with a reason. That is the worked instance of this claim.",
    ),

    # ---- generated artifacts ----------------------------------------------------------------
    Claim(
        claim="A generated artifact's bytes must be a function of its DATA only -- no SHA, no branch, "
              "no timestamp -- or its drift gate is unpassable by construction.",
        stated_in="CLAUDE.md",
        anchor="**The rendered bytes must be a function of the DATA and nothing else.**",
        kind=GUARANTEE,
        enforced_by=("gate:coverage artifact drift", "gate:inventory artifact drift",
                     "gate:wiki reference drift", "mutation:build_coverage_artifact"),
        note="A file inside a commit cannot name its own commit. Both committed pages here shipped "
             "that bug once each.",
    ),
    Claim(
        claim="A drift gate compares the blob at `HEAD`, never the file on disk -- otherwise a page "
              "built and never committed passes the gate whose own message says it is not committed.",
        stated_in="CLAUDE.md",
        anchor="`--check` compares the blob at `HEAD`, never the file on disk",
        kind=GUARANTEE,
        enforced_by=("gate:coverage artifact selftest", "gate:inventory artifact selftest",
                     "mutation:build_coverage_artifact"),
    ),
    Claim(
        claim="Derived numbers are read from the generator's structured source, never regex-parsed "
              "out of its generated prose, and are asserted against the source's declared totals.",
        stated_in="skills/derived-artifacts/SKILL.md",
        anchor="Go to the structured source, not the generated prose",
        kind=GUARANTEE,
        enforced_by=("script:scripts/build_coverage_artifact.py", "gate:coverage artifact selftest"),
    ),
    Claim(
        claim="Regenerating `coverage.md` means regenerating `docs/coverage.html` too; they are built "
              "from the same data and both are committed.",
        stated_in="CLAUDE.md",
        anchor="Regenerating `coverage.md` means regenerating the page too.",
        kind=GUARANTEE,
        enforced_by=("gate:coverage artifact drift", "script:scripts/rebuild_generated.py"),
    ),

    # ---- hooks ------------------------------------------------------------------------------
    Claim(
        claim="An advisory hook fails OPEN; a hook carrying a guarantee fails CLOSED, scoped to the "
              "command it guards.",
        stated_in="docs/harness-doctrine.md",
        anchor="If a model ignores this, what happens?",
        kind=GUARANTEE,
        enforced_by=("rule:hook-count-drift", "gate:self-consistency",
                     "hook:plugins/rails-flow/hooks/scripts/guard-bash.sh",
                     "hook:plugins/qa-flow/hooks/scripts/release-gate.sh",
                     "hook:plugins/rails-flow/hooks/scripts/guard-lane.sh"),
        note="The rule pins the advisory/gate split by count, so adding a hook without classifying it "
             "fails. A gate that failed closed on UNRELATED work would get switched off, which is why "
             "scoping is part of the claim rather than a refinement of it.",
    ),
    Claim(
        claim="`git add -A` is refused, even when the payload cannot be parsed.",
        stated_in="CLAUDE.md",
        anchor="`git add -A` is blocked either way.",
        kind=GUARANTEE,
        enforced_by=("hook:plugins/rails-flow/hooks/scripts/guard-bash.sh",),
        note="Verified by running it with python3 shadowed by a stub that exits 127: line 7 falls back "
             "to the raw JSON payload, which still contains the command text, so every pattern still "
             "matches and it still exits 2.",
    ),
    Claim(
        claim="Working in the wrong worktree during a parallel session is refused, not merely advised "
              "against.",
        stated_in="skills/parallel-session-lane/SKILL.md",
        anchor="## 1. Confirm your worktree before any edit",
        kind=GUARANTEE,
        enforced_by=("hook:plugins/rails-flow/hooks/scripts/guard-lane.sh",),
        refs=(660,),
        note="Dormant without `RAILS_FLOW_LANE`, so it costs a normal session nothing; writes only, "
             "since a read outside your lane is how you learn what the other lanes did.",
    ),
    Claim(
        claim="Two concurrent sessions are never assigned overlapping lanes.",
        stated_in="skills/parallel-session-lane/SKILL.md",
        anchor="refuses** overlapping lanes",
        kind=GUARANTEE,
        enforced_by=("script:plugins/rails-flow/scripts/assign_lanes.py", "mutation:assign_lanes",
                     "gate:rails-flow lane assigner selftest"),
        refs=(661,),
        note="The whole safety property: overlapping lanes mean two sessions editing one tree while "
             "the guard believes each is alone, so both diffs review clean and the collision surfaces "
             "at merge.",
    ),

    # ---- what the marketplace ships ---------------------------------------------------------
    Claim(
        claim="Every plugin in `marketplace.json` is documented, and every entry carries more than a "
              "bare name.",
        stated_in="CLAUDE.md",
        anchor="undocumented-plugin",
        kind=GUARANTEE,
        enforced_by=("rule:undocumented-plugin", "rule:bare-plugin-entry", "gate:self-consistency",
                     "mutation:lint_self_consistency"),
        note="The rule cannot tell that a mention sits in CLAUDE.md's DISTRIBUTED list rather than in "
             "prose elsewhere, so the list itself is still on a human. Stated in CLAUDE.md, and true.",
    ),
    Claim(
        claim="Nothing maintainer-only ships to clients, and every concern has exactly one home.",
        stated_in="CLAUDE.md",
        anchor="exactly one home per concern",
        kind=GUARANTEE,
        enforced_by=("rule:undocumented-skill", "rule:uninstallable-plugin", "gate:self-consistency"),
        note="`plugin-boundaries` rule 2 forbids keeping a second copy behind to dodge the trade, "
             "which is why `derived-artifacts` and `parallel-session-lane` are read as files here.",
    ),
    Claim(
        claim="A release attaches EVERY `dist/*.skill` via glob, never a hand-typed list.",
        stated_in="CLAUDE.md",
        anchor="a glob, never a hand-typed list",
        kind=GUARANTEE,
        enforced_by=("hook:.github/workflows/release.yml", "script:scripts/release_local.sh"),
        note="A hand-typed list is how a release silently drops a newly added skill. Both paths glob, "
             "and CLAUDE.md says change one when you change the other.",
    ),

    # ---- the doctrine gate ------------------------------------------------------------------
    Claim(
        claim="No skill claim is edited until `doctrine-verifier` confirms it against an authoritative "
              "source; INCONCLUSIVE leaves doctrine unchanged.",
        stated_in="CLAUDE.md",
        anchor="**INCONCLUSIVE leaves doctrine unchanged.**",
        kind=ADVICE,
        note="Deliberately unenforced, and the reason is the interesting part: a gate here would have "
             "to read a verdict nothing records in the tree. The classification is 'advice' about the "
             "MECHANISM, not about the rule -- the rule is non-negotiable and enforced by review.",
    ),
    Claim(
        claim="An issue body is a hypothesis, not a specification: every externally verifiable claim "
              "in it is checked before implementation, including for omissions.",
        stated_in="CLAUDE.md",
        anchor="### An issue body is not an authority",
        kind=ADVICE,
        note="#142 cited four accordion keybindings 'per the ARIA APG' that live only in a deleted "
             "2017 example, and omitted a requirement APG states plainly. Not mechanisable: no gate "
             "can know what an upstream spec says today.",
    ),
    Claim(
        claim="A change to a skill states its type -- framework claim or architecture decision -- in "
              "the PR, before editing. Silence is not a claim of exemption.",
        stated_in="CLAUDE.md",
        anchor="**State which kind of change you are making, in the PR, before editing.**",
        kind=GAP,
        refs=(655,),
        note="A trial reviewer's single most-cited finding here was literally 'missing change-type "
             "classification', verbatim from CLAUDE.md. Mechanisable in principle -- a PR touching "
             "`skills/**` whose body names neither type -- but it would live in CI against the PR "
             "body, which no gate in this repo reads. Filed rather than hand-waved.",
    ),

    # ---- what the plugins promise downstream ------------------------------------------------
    Claim(
        claim="An acceptance criterion that no spec cites is unproven, and the work order says so.",
        stated_in="plugins/rails-flow/commands/feature.md",
        anchor="### Acceptance criteria — write them BEFORE any code",
        kind=GUARANTEE,
        enforced_by=("gate:acceptance criteria", "mutation:check_criteria",
                     "script:plugins/rails-flow/scripts/check_criteria.py"),
    ),
    Claim(
        claim="A work order names the commit it was written against, so a stale one is visible rather "
              "than plausible.",
        stated_in="plugins/rails-flow/commands/handoff.md",
        anchor="**The base commit is the section an executor reads first.**",
        kind=GUARANTEE,
        enforced_by=("gate:rails-flow work order", "mutation:check_handoff",
                     "script:plugins/rails-flow/scripts/check_handoff.py"),
        refs=(659,),
    ),
    Claim(
        claim="A failing test is classified before it is debugged: defect, environment, wrong "
              "expectation, upstream, or flake -- and two of those say stop.",
        stated_in="plugins/rails-flow/commands/fix.md",
        anchor="classify the failure before you debug it",
        kind=ADVICE,
        refs=(647,),
        note="Judgement by construction: which row a red test belongs to is the diagnosis. A gate "
             "would have to make that call to check it was made.",
    ),
    Claim(
        claim="A generated asset's prompt is recorded, so the asset is reproducible rather than "
              "merely present.",
        stated_in="plugins/design-flow/commands/generate.md",
        anchor="prompt",
        kind=GUARANTEE,
        enforced_by=("gate:design-flow prompt library selftest", "mutation:prompt_library",
                     "script:plugins/design-flow/scripts/prompt_library.py"),
    ),
    Claim(
        claim="A style reference image is the biggest lever on cross-asset consistency, so a brief "
              "that omits one is flagged.",
        stated_in="plugins/design-flow/commands/generate.md",
        anchor="reference",
        kind=GUARANTEE,
        enforced_by=("mutation:generation_gate", "script:plugins/design-flow/scripts/generation_gate.py"),
    ),
    Claim(
        claim="Composition SHORTLISTS assets and never assigns them; explicit `bands` and `surfaces` "
              "outrank prose.",
        stated_in="plugins/design-flow/commands/generate.md",
        anchor="compose",
        kind=GUARANTEE,
        enforced_by=("gate:design-flow composition brief selftest", "mutation:compose_brief",
                     "script:plugins/design-flow/scripts/compose_brief.py"),
        refs=(672, 676),
    ),

    # ---- the quality half, advisory on purpose ----------------------------------------------
    Claim(
        claim="The quality pass never blocks a merge -- a gate on taste gets switched off, and then "
              "nothing checks quality at all.",
        stated_in="skills/quality-pass/SKILL.md",
        anchor="It is ADVISORY and never a merge",
        kind=ADVICE,
        enforced_by=("gate:shared shapes", "script:scripts/check_shared_shapes.py"),
        note="The one gate here refuses only a NUMBER in the worked example disagreeing with the repo "
             "-- claims-vs-enforcement on our own prose. Strengthening it into refusing copies would "
             "contradict the doctrine it guards.",
    ),
    Claim(
        claim="A gate that needs a carve-out on its first real input is taste wearing a count.",
        stated_in="skills/quality-pass/SKILL.md",
        anchor="**Advisory. Always.**",
        kind=ADVICE,
        refs=(476,),
        note="#476: a monotony gate flagged our own worked example on first real input. Cited to keep "
             "later gates advisory; unenforceable by construction, since it is the rule for deciding "
             "whether to build a gate at all.",
    ),
)


# ---------------------------------------------------------------------------------------------
# Enforcement references. Each prefix resolves against something real, so a row cannot claim
# enforcement that has been deleted.
# ---------------------------------------------------------------------------------------------

def _gate_names() -> set[str]:
    sys.path.insert(0, str(REPO / "scripts"))
    import maintainer_doctor as md
    return {name for name, _ in md.GATES}


def _guard_names() -> set[str]:
    sys.path.insert(0, str(REPO / "scripts"))
    import mutation_check as mc
    return {g.name for g in mc.GUARDS}


def _rule_slugs() -> set[str]:
    """Rule names as `lint_self_consistency.py` actually emits them.

    Read as literal strings in the source rather than from a declared registry, because the slug is
    what a FINDING carries -- so this resolves against the text a maintainer would grep for.
    """
    text = (REPO / "scripts" / "lint_self_consistency.py").read_text(encoding="utf-8")
    return set(re.findall(r'["\']([a-z0-9]+(?:-[a-z0-9]+){1,5})["\']', text))


def _wired_hooks() -> set[str]:
    """Hook scripts and workflows that something actually invokes.

    A hook script sitting on disk unwired is exactly the shape of defect this map exists to surface,
    so `hook:` resolves against the JSON/YAML that runs it, not against the filesystem.
    """
    wired: set[str] = set()
    for cfg in list(REPO.glob("plugins/*/hooks/hooks.json")) + list(REPO.glob(".claude/settings.json")):
        try:
            body = cfg.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in re.finditer(r"[\w./${}-]*hooks/scripts/([\w.-]+)", body):
            wired.add(m.group(1))
    for wf in REPO.glob(".github/workflows/*.yml"):
        wired.add(f".github/workflows/{wf.name}")
    return wired


@dataclass
class Resolver:
    gates: set[str] = field(default_factory=_gate_names)
    guards: set[str] = field(default_factory=_guard_names)
    rules: set[str] = field(default_factory=_rule_slugs)
    hooks: set[str] = field(default_factory=_wired_hooks)
    root: Path = REPO

    def resolve(self, ref: str) -> tuple[bool, str]:
        """(resolved, reason-if-not). An unknown PREFIX is a finding, never a silent pass."""
        kind, _, value = ref.partition(":")
        if not value:
            return False, f"malformed reference {ref!r} — expected `kind:value`"
        if kind == "gate":
            return (value in self.gates), f"no gate named {value!r} in maintainer_doctor.GATES"
        if kind == "mutation":
            return (value in self.guards), f"no mutation guard named {value!r} in mutation_check.GUARDS"
        if kind == "rule":
            return (value in self.rules), f"no rule slug {value!r} in lint_self_consistency.py"
        if kind == "script":
            return (self.root / value).is_file(), f"no such script: {value}"
        if kind == "hook":
            if value.startswith(".github/"):
                return (value in self.hooks), f"no such workflow: {value}"
            name = Path(value).name
            if not (self.root / value).is_file():
                return False, f"no such hook script: {value}"
            return (name in self.hooks), f"hook script {name} exists but nothing wires it"
        return False, f"unknown reference kind {kind!r} in {ref!r}"


# ---------------------------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------------------------

def validate(claims: tuple[Claim, ...] = CLAIMS,
             sources: tuple[str, ...] = DOCTRINE_SOURCES,
             resolver: Resolver | None = None,
             root: Path = REPO) -> list[str]:
    resolver = resolver or Resolver(root=root)
    findings: list[str] = []
    seen: set[tuple[str, str]] = set()
    cache: dict[str, str | None] = {}

    for c in claims:
        where = f"{c.stated_in} :: {c.anchor!r}"

        if c.kind not in KINDS:
            findings.append(f"unknown kind {c.kind!r} — {where}")
            continue

        if (c.stated_in, c.anchor) in seen:
            findings.append(f"duplicate claim — {where}")
        seen.add((c.stated_in, c.anchor))

        # Both surfaces count (#798). The shipped skills are declared in SHIPPED_SOURCES, which
        # ratchets rather than requiring a row per file -- see the note above that tuple.
        if c.stated_in not in sources and c.stated_in not in SHIPPED_SOURCES:
            findings.append(
                f"undeclared source — {c.stated_in} is in neither DOCTRINE_SOURCES nor SHIPPED_SOURCES, so the declared "
                f"doctrine surface is wrong rather than the row")

        if c.stated_in not in cache:
            p = root / c.stated_in
            cache[c.stated_in] = p.read_text(encoding="utf-8") if p.is_file() else None
        body = cache[c.stated_in]
        if body is None:
            findings.append(f"anchor missing — no such file {c.stated_in}")
        elif c.anchor not in body:
            findings.append(
                f"anchor missing — {c.anchor!r} is not in {c.stated_in}; the claim was reworded or "
                f"deleted and this map still advertises it")

        resolved: list[str] = []
        for ref in c.enforced_by:
            ok, why = resolver.resolve(ref)
            if ok:
                resolved.append(ref)
            else:
                findings.append(f"unresolved enforcement — {why} — {where}")

        if c.kind == GUARANTEE and not c.enforced_by:
            findings.append(
                f"unenforced guarantee — nothing is cited; make it `advice`, or a `gap` with an "
                f"issue number — {where}")
        if c.kind == GAP:
            if not c.refs:
                findings.append(f"untracked gap — a gap nobody filed is a shrug — {where}")
            if resolved:
                findings.append(
                    f"resolved gap — {', '.join(resolved)} resolves, so this row was fixed and never "
                    f"reclassified — {where}")
    return findings


def audit_coverage(claims: tuple[Claim, ...] = CLAIMS,
                   sources: tuple[str, ...] = DOCTRINE_SOURCES,
                   root: Path = REPO) -> tuple[list[str], list[str]]:
    """(findings, report-lines). A declared source with zero rows is a finding, not silence."""
    counts = {s: 0 for s in sources}
    for c in claims:
        if c.stated_in in counts:
            counts[c.stated_in] += 1
    findings = []
    lines = []
    for s in sources:
        missing = "" if (root / s).is_file() else "  (file not found)"
        lines.append(f"  {counts[s]:>3}  {s}{missing}")
        if not (root / s).is_file():
            findings.append(f"declared doctrine source does not exist: {s}")
        elif counts[s] == 0:
            findings.append(
                f"declared doctrine source with no rows: {s} — a source nobody mapped reads as "
                f"covered")

    # ---- THE SHIPPED SURFACE, ratcheted (#798) ------------------------------------------------
    # Reported, not required row-for-row. 49 files nobody has mapped would fail this gate on the
    # first run, and bulk back-filling to make it green is the exact "green artifact standing in
    # for work nobody did" this file exists to prevent. So the MAPPED COUNT ratchets: never red on
    # day one, never sliding, and rising only when someone actually maps a source.
    shipped_counts = {s: 0 for s in SHIPPED_SOURCES}
    for c in claims:
        if c.stated_in in shipped_counts:
            shipped_counts[c.stated_in] += 1
    mapped = sorted(s for s, n in shipped_counts.items() if n)
    lines.append("")
    lines.append(f"  shipped doctrine surface: {len(mapped)} of {len(SHIPPED_SOURCES)} file(s) "
                 f"mapped (floor {SHIPPED_FLOOR})")
    for s in mapped:
        lines.append(f"  {shipped_counts[s]:>3}  {s}")
    lines.append("  the rest are UNMAPPED — not clean, and not claimed to be. A row count is "
                 "evidence someone looked, never proof a file is covered.")
    if len(mapped) < SHIPPED_FLOOR:
        findings.append(
            f"shipped doctrine coverage dropped: {len(mapped)} file(s) mapped, floor is "
            f"{SHIPPED_FLOOR}. A row was deleted or its source renamed — restore it, or lower the "
            f"floor deliberately and say why.")
    return findings, lines


# ---------------------------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------------------------

def collect(claims: tuple[Claim, ...] = CLAIMS, root: Path = REPO) -> dict:
    resolver = Resolver(root=root)
    rows = []
    for c in claims:
        rows.append({
            "claim": c.claim,
            "stated_in": c.stated_in,
            "anchor": c.anchor,
            "kind": c.kind,
            "enforced_by": list(c.enforced_by),
            "refs": list(c.refs),
            "note": c.note,
            "resolved": all(resolver.resolve(r)[0] for r in c.enforced_by),
        })
    tally = {k: sum(1 for r in rows if r["kind"] == k) for k in KINDS}
    return {"rows": rows, "tally": tally, "sources": list(DOCTRINE_SOURCES)}


CSS = """
:root{--bg:#fbfbfa;--fg:#1a1a19;--mut:#6b6b66;--line:#e3e3e0;--card:#fff;
--g:#0f7b3f;--a:#8a5a00;--x:#b3261e;--code:#f3f3f1}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161614;--fg:#ecebe7;
--mut:#a3a099;--line:#2f2d29;--card:#1d1c1a;--g:#5fd08a;--a:#e0b25c;--x:#f2857c;--code:#232220}}
:root[data-theme="dark"]{--bg:#161614;--fg:#ecebe7;--mut:#a3a099;--line:#2f2d29;--card:#1d1c1a;
--g:#5fd08a;--a:#e0b25c;--x:#f2857c;--code:#232220}
body{background:var(--bg);color:var(--fg);font:15px/1.55 -apple-system,BlinkMacSystemFont,
"Segoe UI",Roboto,sans-serif;margin:0;padding:2rem 1.25rem 4rem}
main{max-width:70rem;margin:0 auto}
h1{font-size:1.5rem;margin:0 0 .4rem}
p.lede{color:var(--mut);margin:0 0 1.5rem;max-width:52rem}
.tally{display:flex;gap:.6rem;flex-wrap:wrap;margin:0 0 1.25rem}
.tally b{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:.35rem .7rem;
font-weight:600;font-size:.85rem}
.controls{display:flex;gap:.5rem;flex-wrap:wrap;margin:0 0 1rem}
button{font:inherit;font-size:.85rem;padding:.35rem .75rem;border:1px solid var(--line);
border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer}
button[aria-pressed=true]{border-color:var(--fg);font-weight:600}
.row{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:.9rem 1rem;
margin:0 0 .6rem}
.row h2{font-size:1rem;font-weight:600;margin:0 0 .45rem;line-height:1.4}
.meta{font-size:.8rem;color:var(--mut);display:flex;gap:.5rem;flex-wrap:wrap;align-items:center}
.k{font-weight:700;text-transform:uppercase;letter-spacing:.04em;font-size:.72rem}
.k-guarantee{color:var(--g)}.k-advice{color:var(--a)}.k-gap{color:var(--x)}
code{background:var(--code);padding:.1em .35em;border-radius:4px;font-size:.85em}
ul.enf{margin:.5rem 0 0;padding-left:1.1rem;font-size:.85rem}
ul.enf li{margin:.15rem 0}
.none{color:var(--x);font-size:.85rem;margin:.5rem 0 0}
.note{font-size:.85rem;color:var(--mut);margin:.5rem 0 0;border-left:2px solid var(--line);
padding-left:.7rem}
.floor{border:1px dashed var(--line);border-radius:8px;padding:.75rem 1rem;color:var(--mut);
font-size:.85rem;margin:1.5rem 0 0}
""".strip()

JS = """
var btns=document.querySelectorAll('button[data-k]');
function apply(k){
  document.querySelectorAll('.row').forEach(function(r){
    r.hidden = (k!=='all' && r.getAttribute('data-k')!==k);
  });
  btns.forEach(function(b){b.setAttribute('aria-pressed', String(b.dataset.k===k));});
}
btns.forEach(function(b){b.addEventListener('click',function(){apply(b.dataset.k);});});
apply('all');
""".strip()


def render(data: dict) -> str:
    e = html.escape
    t = data["tally"]
    out = [
        "<title>Doctrine Map</title>",
        f"<style>{CSS}</style>",
        "<main>",
        "<h1>Doctrine &rarr; enforcement</h1>",
        '<p class="lede">One row per doctrinal claim in this repo: where it is stated, and what makes '
        "it true. <strong>The unenforced rows are the deliverable.</strong> A claim with no "
        "enforcement is not automatically a defect &mdash; plenty are judgement, and gating judgement "
        "is worse than not gating it. The value is making the distinction visible instead of "
        "discovering it by accident.</p>",
        '<div class="tally">'
        f'<b>{len(data["rows"])} claims</b>'
        f'<b>{t["guarantee"]} enforced guarantees</b>'
        f'<b>{t["advice"]} advisory</b>'
        f'<b>{t["gap"]} tracked gaps</b>'
        "</div>",
        '<div class="controls">'
        '<button data-k="all">all</button>'
        '<button data-k="guarantee">guarantees</button>'
        '<button data-k="advice">advisory</button>'
        '<button data-k="gap">gaps</button>'
        "</div>",
    ]
    order = {GAP: 0, GUARANTEE: 1, ADVICE: 2}
    for r in sorted(data["rows"], key=lambda r: (order[r["kind"]], r["stated_in"])):
        out.append(f'<div class="row" data-k="{r["kind"]}">')
        out.append(f'<h2>{e(r["claim"])}</h2>')
        refs = "".join(f" &middot; #{n}" for n in r["refs"])
        out.append(
            f'<div class="meta"><span class="k k-{r["kind"]}">{r["kind"]}</span>'
            f'<span>stated in <code>{e(r["stated_in"])}</code>{refs}</span></div>')
        if r["enforced_by"]:
            out.append('<ul class="enf">')
            for ref in r["enforced_by"]:
                out.append(f"<li><code>{e(ref)}</code></li>")
            out.append("</ul>")
        else:
            out.append('<p class="none">Nothing enforces this.</p>')
        if r["note"]:
            out.append(f'<p class="note">{e(r["note"])}</p>')
        out.append("</div>")
    out.append(
        '<div class="floor"><strong>This map is a floor, not a ceiling.</strong> The audit can tell '
        "you a declared doctrine source has <em>no</em> rows; nothing here can tell you a source with "
        "four rows was not owed nine. A row count is evidence that someone looked, never proof the "
        "file is covered. Sources declared: "
        + ", ".join(f"<code>{e(s)}</code>" for s in data["sources"]) + ".</div>")
    out.append("</main>")
    out.append(f"<script>{JS}</script>")
    return "\n".join(out) + "\n"


def committed_blob(rel: str) -> str | None:
    try:
        r = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=REPO,
                           capture_output=True, text=True, check=False)
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


# ---------------------------------------------------------------------------------------------
# Selftest — every validator must FIRE on a broken fixture and stay SILENT on a good one.
# ---------------------------------------------------------------------------------------------

def _selftest() -> int:
    import tempfile
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "doc.md").write_text("the claim is stated here\n", encoding="utf-8")
        (root / "real.py").write_text("x = 1\n", encoding="utf-8")
        srcs = ("doc.md",)

        class Fake(Resolver):
            def __init__(self):
                super().__init__(gates={"g"}, guards={"m"}, rules={"a-rule"},
                                 hooks={"h.sh", ".github/workflows/w.yml"}, root=root)

        fake = Fake()
        good = Claim("c", "doc.md", "the claim", GUARANTEE, ("gate:g",))

        check("silent on a good row", validate((good,), srcs, fake, root) == [])

        def fires(label: str, c: Claim, needle: str) -> None:
            f = validate((c,), srcs, fake, root)
            check(f"{label} fires", any(needle in x for x in f))
            check(f"{label} silent on the good row", not any(needle in x
                                                            for x in validate((good,), srcs, fake, root)))

        fires("anchor missing", Claim("c", "doc.md", "not present", GUARANTEE, ("gate:g",)),
              "anchor missing")
        fires("missing file", Claim("c", "doc.md", "the claim", GUARANTEE, ("gate:g",))
              if False else Claim("c", "gone.md", "the claim", GUARANTEE, ("gate:g",)),
              "no such file")
        fires("unenforced guarantee", Claim("c", "doc.md", "the claim", GUARANTEE),
              "unenforced guarantee")
        fires("untracked gap", Claim("c", "doc.md", "the claim", GAP), "untracked gap")
        fires("resolved gap", Claim("c", "doc.md", "the claim", GAP, ("gate:g",), refs=(1,)),
              "resolved gap")
        fires("unknown kind", Claim("c", "doc.md", "the claim", "maybe"), "unknown kind")
        fires("bad gate", Claim("c", "doc.md", "the claim", GUARANTEE, ("gate:nope",)),
              "no gate named")
        fires("bad guard", Claim("c", "doc.md", "the claim", GUARANTEE, ("mutation:nope",)),
              "no mutation guard")
        fires("bad rule", Claim("c", "doc.md", "the claim", GUARANTEE, ("rule:nope",)), "no rule slug")
        fires("bad script", Claim("c", "doc.md", "the claim", GUARANTEE, ("script:nope.py",)),
              "no such script")
        fires("unknown prefix", Claim("c", "doc.md", "the claim", GUARANTEE, ("wat:x",)),
              "unknown reference kind")
        fires("malformed ref", Claim("c", "doc.md", "the claim", GUARANTEE, ("bare",)), "malformed")

        # A hook script that exists but nothing wires is the shape this map is FOR, so it must not
        # resolve merely by existing.
        (root / "hooks").mkdir()
        (root / "hooks" / "scripts").mkdir()
        (root / "hooks" / "scripts" / "unwired.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        rok, why = fake.resolve("hook:hooks/scripts/unwired.sh")
        check("an existing but unwired hook does not resolve", not rok and "nothing wires it" in why)
        (root / "hooks" / "scripts" / "h.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        check("a wired hook resolves", fake.resolve("hook:hooks/scripts/h.sh")[0])
        check("a script resolves by existing", fake.resolve("script:real.py")[0])
        check("a workflow resolves from the wired set",
              fake.resolve("hook:.github/workflows/w.yml")[0])

        dup = (good, Claim("other wording", "doc.md", "the claim", GUARANTEE, ("gate:g",)))
        check("duplicate fires", any("duplicate claim" in x for x in validate(dup, srcs, fake, root)))

        check("undeclared source fires",
              any("undeclared source" in x
                  for x in validate((Claim("c", "elsewhere.md", "x", ADVICE),), srcs, fake, root)))

        # advice with nothing behind it is CORRECT and must stay silent -- the negative test for the
        # unenforced-guarantee rule, without which that rule would be a blanket ban on advisory rows.
        check("advice with no enforcement stays silent",
              validate((Claim("c", "doc.md", "the claim", ADVICE),), srcs, fake, root) == [])

        af, _ = audit_coverage((good,), ("doc.md", "unmapped.md"), root)
        check("audit reports a nonexistent declared source",
              any("does not exist" in x and "unmapped.md" in x for x in af))
        (root / "unmapped.md").write_text("x\n", encoding="utf-8")
        af, _ = audit_coverage((good,), ("doc.md", "unmapped.md"), root)
        check("audit reports a source with no rows",
              any("no rows" in x and "unmapped.md" in x for x in af))
        check("audit silent on a mapped source", not any("doc.md" in x for x in af))

    # Against the REAL repo, not a fixture: a selftest that only ever sees fixtures is the bug
    # `maintainer_doctor` was written about.
    check("the real registry validates clean", validate() == [])
    rf, _ = audit_coverage()
    check("the real declared sources all have rows", rf == [])
    check("render is a pure function of the data", render(collect()) == render(collect()))
    check("no git state reaches the page",
          not re.search(r"\b[0-9a-f]{7,40}\b", render(collect())))

    # ---- THE SHIPPED SURFACE RATCHET (#798) ---------------------------------------------------
    # 49 shipped files nobody has mapped would fail `doctrine map coverage` on the first run -- red
    # on day one, which #800 spent a whole issue removing. So the MAPPED FILE COUNT ratchets.
    shipped = SHIPPED_SOURCES[:3]
    ok_claim = Claim(claim="c", stated_in=shipped[0], anchor="x", kind=GUARANTEE,
                     enforced_by=("script:scripts/doctrine_map.py",))
    f, lines = audit_coverage(claims=(ok_claim,), sources=(), root=REPO)
    check("a shipped source with a row is reported as mapped",
          any("1 of " in l or f"  1  {shipped[0]}" in l for l in lines))
    check("...and the unmapped rest are named as NOT clean",
          any("UNMAPPED" in l and "not clean" in l for l in lines))

    # THE RATCHET ITSELF: below the floor is a finding. Without this the count would be reported
    # and never enforced -- a number on a page, which is the shape this map exists to replace.
    import unittest.mock as _m
    with _m.patch.object(sys.modules[__name__], "SHIPPED_FLOOR", 2):
        f, _ = audit_coverage(claims=(ok_claim,), sources=(), root=REPO)
        check("one mapped file below a floor of 2 is a finding",
              any("shipped doctrine coverage dropped" in x for x in f))
        f, _ = audit_coverage(claims=(ok_claim, Claim(
            claim="c2", stated_in=shipped[1], anchor="y", kind=GUARANTEE,
            enforced_by=("script:scripts/doctrine_map.py",))), sources=(), root=REPO)
        check("...and two mapped files meets it", not any(
            "shipped doctrine coverage dropped" in x for x in f))

    # FILES, NOT ROWS. Two rows in ONE file is not broader coverage of the surface -- and a floor
    # counting rows would be met by adding a second row to a file already mapped.
    with _m.patch.object(sys.modules[__name__], "SHIPPED_FLOOR", 2):
        two_rows_one_file = (ok_claim, Claim(claim="c3", stated_in=shipped[0], anchor="z",
                                             kind=GUARANTEE,
                                             enforced_by=("script:scripts/doctrine_map.py",)))
        f, _ = audit_coverage(claims=two_rows_one_file, sources=(), root=REPO)
        check("two rows in ONE file does not meet a floor of 2 files",
              any("shipped doctrine coverage dropped" in x for x in f))

        print(f"\n{ok} passed, {len(bad)} failed")
    for b in bad:
        print(f"  FAIL {b}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="verify the COMMITTED page matches a clean build, and the registry validates")
    ap.add_argument("--audit-coverage", action="store_true",
                    help="row count per declared doctrine source; zero rows is a finding")
    ap.add_argument("--json", action="store_true", help="emit the structured source")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if not (REPO / ".claude-plugin" / "marketplace.json").is_file():
        print("not the claude-skills repo", file=sys.stderr)
        return 2
    if a.selftest:
        return _selftest()

    findings = validate()
    if a.audit_coverage:
        cf, lines = audit_coverage()
        print("rows per declared doctrine source:")
        print("\n".join(lines))
        findings += cf

    if a.json:
        print(json.dumps(collect(), indent=2, sort_keys=True))

    built = render(collect())
    if a.check:
        blob = committed_blob(PAGE)
        if blob is None:
            findings.append(f"{PAGE} is not committed — build it and `git add docs/`")
        elif blob != built:
            findings.append(f"{PAGE} does not match a clean build — rebuild it and `git add docs/`")
    elif not a.json and not a.audit_coverage:
        (REPO / PAGE).write_text(built, encoding="utf-8")
        print(f"wrote {PAGE} — {len(CLAIMS)} claims. `git add docs/`; the drift gate compares the "
              f"blob at HEAD, so it stays red until you commit.")

    if findings:
        print(f"\n{len(findings)} finding(s):", file=sys.stderr)
        for f in findings:
            print(f"  {f}", file=sys.stderr)
        return 1
    if a.check or a.audit_coverage:
        print(f"\nclean — {len(CLAIMS)} claims, {sum(1 for c in CLAIMS if c.kind == GAP)} tracked gap(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
