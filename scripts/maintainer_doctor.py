#!/usr/bin/env python3
"""Diagnose a maintainer machine, and repair the safe parts.

Run:  python3 scripts/maintainer_doctor.py            # diagnose, change nothing
      python3 scripts/maintainer_doctor.py --fix       # also apply the SAFE repairs
      python3 scripts/maintainer_doctor.py --gates     # include the full gate sweep (slower)
      python3 scripts/maintainer_doctor.py --selftest   # prove the checks fire and stay silent

WHY THIS EXISTS. Moving maintenance to a second machine needed a ~120-line hand-written
briefing, and it was only complete because the author had just hit every trap personally:

  * a fresh clone lands on `main` -- the one branch this repo says never to work from;
  * an idle clone has a STALE local `main` ref, which silently breaks the `git diff dev main`
    check CLAUDE.md prescribes (it reported 5,231 phantom deletions on a real machine);
  * the licensed corpora live in a separate private repo, cloned into one gitignored
    subfolder, and exactly ONE file reads them -- and the ignore rules that keep them out of
    this history are themselves checked, because they once could not match the layout the
    setup instructions prescribed (#197);
  * the ahead/behind counter is meaningless here, because `main` gains one merge commit per
    release that `dev` never receives.

None of that is discoverable. A checklist in a readme would be the same defect class this repo
keeps paying for -- claims-vs-enforcement, a guarantee in prose that nothing makes true -- so
it is a script that can fail instead.

THE DESIGN RULE THAT MATTERS: three outcomes, not two. PASS, FAIL and **SKIP** are reported
distinctly, because a check that did not run must never render as a check that passed. That is
the exact bug this replaces: `build_coverage.py --selftest` printed "35 checks passed" on a
machine with no corpora while silently skipping two checks against the real repo, so the
coverage guards were inert while reading green.

WHAT IT DOES NOT DO. It never rewrites history, never `reset --hard`, never `clean`. `--fix`
touches two things only: fast-forwarding the local `main` ref to `origin/main` (safe, because
you never commit to `main`) and checking out/pulling `dev`. Anything else is reported with a
remedy for a human to run deliberately.

Exit codes:  0 = no failures (skips allowed) · 1 = at least one FAIL · 2 = not this repo

Stdlib only, no network beyond the `git`/`gh` calls the checks make.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The one historical direct-to-main commit, documented in CLAUDE.md. It converged (the same
# block later reached dev), so it is expected -- but anything ELSE on main and not on dev is a
# real finding, because a direct commit to main is invisible to every future dev-based change.
KNOWN_DIRECT_TO_MAIN = "d4b35f6"

PASS, FAIL, SKIP, INFO = "PASS", "FAIL", "SKIP", "INFO"

# Only `scripts/build_coverage.py` reads the corpora. Stated here so the corpora check can say
# what is actually lost without them, rather than implying the repo is unusable.
#
# ONE gitignored subfolder holding a nested clone — not three root-level symlinks (#197).
# `check_corpora_ignored` keeps this in step with `.gitignore`, and the selftest asserts it
# stays in step with `build_coverage.TW_ROOT`, which is the only thing that reads the kits.
CORPORA_DIR = "design-corpora"
CORPORA = ("tailwind-ui", "flowbite", "everylayout")
CORPORA_REPO = "https://github.com/fmanimashaun/design-corpora.git"

# Paths whose ignore status is asserted below. The near-misses matter as much as the positives:
# an over-broad corpora pattern that swallowed `coverage.md` would silently disable the drift
# guard. `/flowbite*` is wildcarded on purpose (flowbite-figma, the zips), so its near-miss
# tests the root ANCHOR at depth rather than the name.
MUST_IGNORE = (
    CORPORA_DIR,
    f"{CORPORA_DIR}/tailwind-ui/html/components",
    "tailwind-ui",          # the pre-#197 root layout, still ignored as insurance
    "everylayout",
    "flowbite",
    "flowbite-figma",
    "flowbite-pro-marketing-ui.zip",
)
MUST_NOT_IGNORE = (
    "scripts/build_coverage.py",                    # not everything is ignored
    f"{CORPORA_DIR}-notes/README.md",               # exact name, not a prefix
    "docs/flowbite-notes.md",                       # `/flowbite*` is root-anchored
    "skills/fidara-design/references/coverage.md",   # the drift guard needs this committed
)

GATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("markdown shell lint", ("python3", "scripts/lint_markdown_shell.py")),
    ("markdown shell coverage", ("python3", "scripts/lint_markdown_shell.py", "--audit-coverage")),
    ("markdown code lint", ("python3", "scripts/lint_markdown_code.py")),
    ("markdown code coverage", ("python3", "scripts/lint_markdown_code.py", "--audit-coverage")),
    ("markdown code selftest", ("python3", "scripts/lint_markdown_code.py", "--selftest")),
    # Only the SELFTEST is a gate. Validating the live tracker needs `gh`, and a gate that fails
    # for want of a binary teaches people to ignore gates — the reasoning CORPORA_GATES already
    # encodes. The live check runs in /maintainer-triage, where `gh` is a stated precondition.
    ("issue graph selftest", ("python3", "scripts/issue_graph.py", "--selftest")),
    ("self-consistency", ("python3", "scripts/lint_self_consistency.py")),
    ("self-consistency selftest", ("python3", "scripts/lint_self_consistency.py", "--selftest")),
    ("coverage matrix drift", ("python3", "scripts/build_coverage.py", "--check")),
    ("coverage matrix selftest", ("python3", "scripts/build_coverage.py", "--selftest")),
    # The artifact is COMMITTED (docs/coverage.html), so it can go stale exactly as coverage.md
    # can — same shape, same gate, and the same corpora dependency. An earlier version of this
    # comment claimed neither gate needed the licensed kits, because `ENTRIES` is declared
    # statically. That was wrong and was proved wrong by running it: the page also EMBEDS the
    # upstream corpus totals, so a corpora-less machine renders different bytes and the drift gate
    # returns 1 on a perfectly good checkout. Hence its place in CORPORA_GATES below.
    ("coverage artifact drift", ("python3", "scripts/build_coverage_artifact.py", "--check")),
    # The selftest is a gate too: one that exists but that `--gates` never runs makes a clean sweep a
    # claim about work nobody did — the coverage-gap class. It was registered TWICE for a while, which
    # inflates the sweep count; GATE names are asserted unique in the selftest now.
    ("coverage artifact selftest", ("python3", "scripts/build_coverage_artifact.py", "--selftest")),
    # #509, and the same shape a second time: `docs/inventory.html` is COMMITTED, so it goes stale
    # the moment an agent, a command, a gate or a version moves — which is most PRs. Registered as
    # both halves for the reason stated above: the selftest proves the guards fire and stay silent
    # on fixtures, the drift check asserts the page we actually ship is a clean build.
    #
    # NOT in CORPORA_GATES, and it never should be: every input is a tracked file in every clone
    # (`plugins/**`, `.claude/**`, this file, `marketplace.json`). That is the fixed version of the
    # mistake the block above records, not a carve-out anyone got away without.
    ("inventory artifact drift", ("python3", "scripts/build_inventory.py", "--check")),
    ("inventory artifact selftest", ("python3", "scripts/build_inventory.py", "--selftest")),
    # The wiki's REFERENCE pages only. Its narrative pages are hand-written and this never touches
    # them -- but a renamed command or a new skill must not be able to leave the reference wrong,
    # which is exactly how the README came to name version 1.3.1 while the marketplace shipped 1.80.
    ("wiki reference drift", ("python3", "scripts/build_wiki.py", "--check")),
    ("wiki reference selftest", ("python3", "scripts/build_wiki.py", "--selftest")),
    # #304: contrast is the most measurable claim in the design system and was asserted in prose.
    # #129 widened its INPUT from the doctrine file to every shipped brand pack, because the #304
    # fix had been applied to the doctrine file and to neither pack — so the gate read clean over
    # the one file that was already right while the artifact users install kept the defect.
    ("token contrast", ("python3", "scripts/check_token_contrast.py")),
    ("token contrast selftest", ("python3", "scripts/check_token_contrast.py", "--selftest")),
    # #129. A candidate palette ships in a client's colours, so "measured, not asserted" is the
    # whole feature: --check measures every candidate against 1.4.3 in both modes.
    ("design-flow palette candidates",
     ("python3", "plugins/design-flow/scripts/palette_candidates.py", "--check")),
    ("design-flow palette candidates selftest",
     ("python3", "plugins/design-flow/scripts/palette_candidates.py", "--selftest")),
    # #602. A compiler whose whole value is "no literal colour survives" needs the assertion that
    # says so to run somewhere other than a maintainer's memory.
    ("design-flow pen-to-svg selftest",
     ("python3", "plugins/design-flow/scripts/pen_to_svg.py", "--selftest")),
    # #603. The library is a PROJECTION of the brand pack, so the assertions that matter are that
    # regeneration is byte-identical and that it never eats the designer's own compositions.
    # #617. The resolver that finds `fidara-design` from BOTH the clone and the installed cache —
    # the layout no fixture exercised until a user hit it.
    ("design-flow doctrine path selftest",
     ("python3", "plugins/design-flow/scripts/doctrine_path.py", "--selftest")),
    ("design-flow pen library selftest",
     ("python3", "plugins/design-flow/scripts/pen_library.py", "--selftest")),
    # #625. The library that keeps the composed prompt, the model and the money. Two of its rules
    # are the ones a checker cannot infer and only a fixture can hold: the markdown view's bytes
    # are a function of the JSON alone, and a rung named `agent` is a ROLE recorded as an unknown
    # model rather than as a model called "agent".
    # #661. The launcher refuses overlapping lanes, and overlap is its whole safety property: two
    # sessions editing one tree while the guard believes each is alone review clean on both sides.
    # #655. Both halves: the drift check asserts the page we ship is a clean build, and the selftest
    # proves each validator fires AND stays silent -- including that an `advice` row with nothing
    # behind it is correct, without which the unenforced-guarantee rule is a blanket ban on advisory
    # doctrine, which `quality-pass` exists to argue against.
    # #699. Asserts what PUBLISHES, not what exists: it runs the real extractor for
    # marketplace.json's version and refuses any block written for the tag that would not appear.
    ("release notes complete", ("python3", "scripts/extract_release_notes.py", "--check")),
    ("release notes selftest", ("python3", "scripts/extract_release_notes.py", "--selftest")),
    ("doctrine map drift", ("python3", "scripts/doctrine_map.py", "--check")),
    ("doctrine map coverage", ("python3", "scripts/doctrine_map.py", "--audit-coverage")),
    ("doctrine map selftest", ("python3", "scripts/doctrine_map.py", "--selftest")),
    ("rails-flow lane assigner selftest",
     ("python3", "plugins/rails-flow/scripts/assign_lanes.py", "--selftest")),
    ("design-flow prompt library selftest",
     ("python3", "plugins/design-flow/scripts/prompt_library.py", "--selftest")),
    # #625/#628/#629. Three modules encode one layout decision and `asset_plan.py` holds its half as
    # literals (it is deliberately standalone). Move one and not the others and `--scaffold` creates
    # a folder nothing writes to while `--run` writes into one the scaffold never made — both halves
    # still "work", on different paths, and nothing else in the repo would notice.
    # #639. The composition brief — which owned asset fills which band, and why that one. Its two
    # load-bearing properties are the ones only a fixture can hold: `avoid` outranks `use_cases`, and
    # the band matches while the SURFACE only excludes (folding the surface into the match made every
    # band on one page take the same asset).
    ("design-flow composition brief selftest",
     ("python3", "plugins/design-flow/scripts/compose_brief.py", "--selftest")),
    ("design-flow asset layout",
     ("python3", "scripts/check_asset_layout.py")),
    ("design-flow asset layout selftest",
     ("python3", "scripts/check_asset_layout.py", "--selftest")),
    # #600/#601. The branch that matters is the silent skip: an absent surface must degrade to
    # today's behaviour rather than stopping, and only a fixture can hold that true.
    ("design-flow pen compose selftest",
     ("python3", "plugins/design-flow/scripts/pen_compose.py", "--selftest")),
    # #609. "pen mirrors the whole catalogue" is a claim; without this it is a claim nothing makes
    # true, and the drift is silent in the worst direction — a component simply not appearing.
    ("component shapes reconciled",
     ("python3", "scripts/check_component_shapes.py")),
    ("component shapes selftest",
     ("python3", "scripts/check_component_shapes.py", "--selftest")),
    # #360, and the same argument one skill along: the quality-pass worked example states how many
    # files carry each duplicated shape, and an extraction decision rests on those numbers. NOT a
    # duplication gate — nothing here refuses a copy. It refuses a number in shipped doctrine
    # disagreeing with the repo, exactly as the tier gates below reconcile a table against agents.
    ("shared shapes", ("python3", "scripts/check_shared_shapes.py")),
    ("shared shapes selftest", ("python3", "scripts/check_shared_shapes.py", "--selftest")),
    # #92 (Phase 5), and the same shape a third time: `page-anatomies.md` -> How a page is paced
    # states a count measured from `coverage.md`, a band range, and a worked sequence whose whole
    # point is that consecutive bands differ. NOT a design gate — nothing here judges a sequence.
    # It refuses a number or a name in shipped doctrine disagreeing with the repo, and it resolves
    # the band tones through `foundations-tokens.md` so the section's "no new token" promise is
    # enforced rather than asserted.
    ("page pacing", ("python3", "scripts/check_page_pacing.py")),
    ("page pacing selftest", ("python3", "scripts/check_page_pacing.py", "--selftest")),
    ("section landmarks", ("python3", "scripts/check_section_landmarks.py")),
    ("section landmarks selftest",
     ("python3", "scripts/check_section_landmarks.py", "--selftest")),
    ("packaging determinism", ("python3", "scripts/package_core.py", "--selftest")),
    ("rails-flow self-consistency", ("python3", "plugins/rails-flow/scripts/self_consistency.py", "--selftest")),
    ("acceptance criteria", ("python3", "plugins/rails-flow/scripts/check_criteria.py", "--selftest")),
    ("rails-flow guide", ("python3", "plugins/rails-flow/scripts/check_guide.py", "--selftest")),
    # Its last two checks reconcile the SHIPPED tier table against the SHIPPED agents, so this gate
    # also catches an agent's `model:` drifting from the doctrine that documents it (#127).
    ("rails-flow work order", ("python3", "plugins/rails-flow/scripts/check_handoff.py", "--selftest")),
    # #130. Its riskiest rule is a SIMILARITY rule (no long run of a cited source reproduced in the
    # brief), so most of its selftest is the silence direction — a blockquote, a fence, a table
    # cell and a run one word under the threshold are all shapes that look like duplication.
    ("rails-flow product brief", ("python3", "plugins/rails-flow/scripts/check_brief.py", "--selftest")),
    ("rails-flow claim extraction", ("python3", "plugins/rails-flow/scripts/extract_claims.py", "--selftest")),
    # #488 pillar 1. Four of its fixtures encode SUBSTRATE facts rather than logic — that
    # `installed_plugins.json` holds a LIST per plugin (two rails-flow versions really do coexist
    # in the cache), that `known_marketplaces.json` carries no version at all, and that the two
    # version sources are DISJOINT (rails-stack only in marketplace.json, the four code plugins
    # only in their own plugin.json). Each fails in the silent direction: reading one source, or
    # the wrong record, reports a stale toolchain as current.
    ("rails-flow toolchain version", ("python3", "plugins/rails-flow/scripts/toolchain_version.py", "--selftest")),
    # #488 pillar 3. Its four load-bearing fixtures encode API facts, not logic: the agent and the
    # human share a LOGIN (gh authenticates with the user's own token), so replies are found by a
    # marker; a quoted marker must still read as human; a missing label ERRORS rather than degrading,
    # and parking on a question nobody is emailed about is the one unrecoverable failure here.
    ("rails-flow escalation loop", ("python3", "plugins/rails-flow/scripts/escalation.py", "--selftest")),
    # #334. Its selftest also validates every SHIPPED checks.json -- that each names a real
    # script and supplies a required subcommand -- so a manifest defect fails here rather
    # than on a user's first run.
    ("project gates", ("python3", "plugins/rails-flow/scripts/project_gates.py", "--selftest")),
    # #423, and the gap the line above could not see. `project_gates.py --selftest` asserts each
    # manifest entry names a real SCRIPT; nothing asserted its `applies_when` paths and `{match:}`
    # globs name real ARTEFACTS. An absent path is reported as not-applicable, never as a failure,
    # so five checks across two plugins were permanent silent skips — a gate that cannot fail,
    # inside the manifest that registers the gates. Registered as both halves for the reason the
    # tell-detector above states: the selftest proves the rules fire and stay silent on fixtures,
    # the bare run asserts the SHIPPED manifests agree with the plugins that ship them.
    ("checks.json paths", ("python3", "scripts/check_manifest_paths.py")),
    ("checks.json paths selftest", ("python3", "scripts/check_manifest_paths.py", "--selftest")),
    # #299: every plugin's tier table reconciled against its OWN shipped agents. The selftest above
    # proves the checker works; these prove the four SHIPPED tables are true. Without them a table is
    # doctrine nothing enforces — which is the exact state #127 found rails-flow's pins in, and the
    # reason this issue exists. One checker, four tables: the marker carries the plugin's name.
    ("rails-flow tiers", ("python3", "plugins/rails-flow/scripts/check_handoff.py",
                          "--agents", "plugins/rails-flow/agents",
                          "--tiers", "plugins/rails-flow/reference/model-tiers.md")),
    ("qa-flow tiers", ("python3", "plugins/rails-flow/scripts/check_handoff.py",
                       "--agents", "plugins/qa-flow/agents",
                       "--tiers", "plugins/qa-flow/reference/model-tiers.md")),
    ("design-flow tiers", ("python3", "plugins/rails-flow/scripts/check_handoff.py",
                           "--agents", "plugins/design-flow/agents",
                           "--tiers", "plugins/design-flow/reference/model-tiers.md")),
    ("pipeline tiers", ("python3", "plugins/rails-flow/scripts/check_handoff.py",
                        "--agents", "plugins/pipeline/agents",
                        "--tiers", "plugins/pipeline/reference/model-tiers.md")),
    # #128, the pipeline half. Its last checks run against the SHIPPED doctrine and the SHIPPED
    # commands: that reference/stop-conditions.md still states the numbers and the four escapes the
    # script declares, and that every pipeline surface describing an unattended re-run names the
    # breaker. Fixtures prove the breakers fire; only those can see the doctrine drifting away from
    # the code, which is the same defect one level up.
    ("pipeline stop conditions", ("python3", "plugins/pipeline/scripts/breaker.py", "--selftest")),
    ("qa-flow evidence", ("python3", "plugins/qa-flow/scripts/validate_evidence.py", "--selftest")),
    ("qa-flow route coverage", ("python3", "plugins/qa-flow/scripts/route_coverage.py", "--selftest")),
    ("qa-flow blast radius", ("python3", "plugins/qa-flow/scripts/blast_radius.py", "--selftest")),
    ("qa-flow evidence manifest", ("python3", "plugins/qa-flow/scripts/evidence_manifest.py", "--selftest")),
    ("qa-flow route crawl", ("python3", "plugins/qa-flow/scripts/crawl_report.py", "--selftest")),
    ("qa-flow theme parity", ("python3", "plugins/qa-flow/scripts/theme_parity.py", "--selftest")),
    ("qa-flow boot classifier", ("python3", "plugins/qa-flow/scripts/classify_boot_failure.py", "--selftest")),
    ("qa-flow interaction sweep", ("python3", "plugins/qa-flow/scripts/interaction_report.py", "--selftest")),
    ("qa-flow visual baselines", ("python3", "plugins/qa-flow/scripts/visual_baseline.py", "--selftest")),
    ("qa-flow link audit", ("python3", "plugins/qa-flow/scripts/link_audit.py", "--selftest")),
    ("design-flow setup cross-check", ("python3", "plugins/design-flow/scripts/setup_doctrine_crosscheck.py", "--quiet")),
    ("design-flow setup cross-check selftest", ("python3", "plugins/design-flow/scripts/setup_doctrine_crosscheck.py", "--selftest")),
    ("design-flow rendered conformance", ("python3", "plugins/design-flow/scripts/rendered_conformance.py", "--selftest")),
    ("rails-flow findings records", ("python3", "plugins/rails-flow/scripts/findings.py", "--selftest")),
    ("design-flow LLM-tell detector", ("python3", "plugins/design-flow/scripts/llm_tell_detector.py", "--selftest")),
    # #157 criterion 6, and NOT redundant with the selftest above: the selftest proves each rule
    # fires and stays silent on synthetic fixtures, while this runs the whole rule set against the
    # doctrine we actually ship. It has already earned it — the first run flagged our own token
    # definitions as raw-hex violations and a comment saying "NOT an arbitrary `rounded-[12px]`".
    ("design-flow tells vs our own doctrine", ("python3", "plugins/design-flow/scripts/llm_tell_detector.py", "--doctrine-selfcheck")),
    # #160. Only the SELFTEST is a gate: the subject is a USER's variant set, and this repo is a
    # marketplace, not a Rails app — a gate pointed at `app/views/design_variants` here would SKIP
    # forever, and a permanent skip reads as a pass. The live check runs in a user's project via
    # design-flow's `checks.json`, where `applies_when` decides applicability honestly.
    ("design-flow variant conformance", ("python3", "plugins/design-flow/scripts/variant_conformance.py", "--selftest")),
    # The browser collector is a shipped `.js` FILE, so no markdown linter reads it — the fenced-code
    # checkers only see markdown. Its syntax check therefore lives with it, and SKIPS loudly when
    # node is absent instead of failing the sweep for want of a binary (CORPORA_GATES' reasoning).
    ("design-flow conformance collector", ("python3", "plugins/design-flow/scripts/rendered_conformance.py", "--check-collector")),
    # Same argument, second collector — and it had no gate at all until #105's focus-restore work
    # touched it. Note it needs MODULE mode: `crawl_collector.js` is ESM, and plain
    # `node --check <file>` exits 0 on a broken ES module, so the obvious gate could not fail.
    ("qa-flow crawl collector", ("python3", "plugins/qa-flow/scripts/interaction_report.py", "--check-collector")),
    # #158. Both halves registered, for the reason spelled out on the tell-detector above: the
    # selftest proves each rule fires and stays silent on fixtures, the bare run asserts the four
    # SHIPPED skills actually route to every one of their 42 reference files. Only the second could
    # have caught `fidara-design/references/coverage.md` sitting at depth 2, which it did.
    ("skill routing", ("python3", "scripts/check_skill_routing.py")),
    ("skill routing selftest", ("python3", "scripts/check_skill_routing.py", "--selftest")),
    ("evals gates", ("python3", "evals/selftest.py")),
    # The doctor's own selftest is a gate like any other. Not recursive: this runs `--selftest`,
    # which exercises fixtures and never re-enters `--gates`. Its absence was found by the
    # completeness rule in maintainer_doctor_selftest.py on that rule's first run.
    ("maintainer doctor", ("python3", "scripts/maintainer_doctor.py", "--selftest")),
    # The meta-gate: proves each selftest above actually FAILS when its subject breaks. Runs last
    # because it is the slowest (it re-runs every selftest once per declared mutation).
    ("mutation check", ("python3", "scripts/mutation_check.py", "--selftest")),
    ("mutation coverage", ("python3", "scripts/mutation_check.py")),
)

# Gates that cannot run without the licensed corpora, so their absence is a SKIP rather than a
# FAIL. Exactly ONE qualifies. `build_coverage.py --check` genuinely enumerates the kits, so without
# them it cannot rebuild `coverage.md` to compare against.
#
# `coverage artifact drift` was briefly in here and has been REMOVED, which is the more instructive
# half. It was added because the HTML page embedded the upstream corpus totals by walking the kits,
# so a corpora-less rebuild produced different bytes. But exempting it only stopped the CHECK failing
# on the machine that lacked them — it could not stop that machine committing a page with
# `tw: null, fb: null`, which then failed the gate for everyone who HAD them. The exemption moved the
# damage rather than removing it, and a web session hit exactly that. The page now reads both counts
# from the committed `coverage.md` Totals table, so its bytes are corpora-independent and the gate
# runs everywhere. Fix the input; do not widen the carve-out.
#
# Keyed by gate NAME, and the selftest asserts the name exists in GATES — otherwise a rename would
# silently stop the exemption applying — and that the set is exactly this one.
CORPORA_GATES = frozenset({"coverage matrix drift"})

# Seconds a subprocess gets before the doctor calls it hung. Right for a check that reads the tree
# once, which is nearly all of them.
DEFAULT_TIMEOUT = 180

# Gates whose cost grows with the repo's own thoroughness, and the seconds they get.
#
# The default 180s is right for a check that reads the tree once. It is the WRONG SHAPE for
# `mutation coverage`, which spawns one subprocess per declared mutation and therefore gets slower
# every time anyone makes the repo safer. It crossed the budget at 236 mutations (#129), and a
# timeout reported as FAIL is indistinguishable from a real survivor — the sweep says "fix the
# failures before doing maintenance work" about a checker that was working fine.
#
# Declared here rather than raised globally, because a slow gate is a property of THAT gate: giving
# every gate ten minutes would mean a genuinely hung check sits there for ten minutes.
#
# Keyed by gate NAME, exactly as CORPORA_GATES is, and the selftest asserts the names are real —
# a rename would otherwise silently drop the allowance and the gate would start failing on time.
SLOW_GATES: dict[str, int] = {
    "mutation coverage": 900,
}


@dataclass
class Result:
    status: str
    name: str
    detail: str = ""
    remedy: str = ""


@dataclass
class Doctor:
    fix: bool = False
    results: list[Result] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)

    # ---- helpers ----------------------------------------------------------------------
    def run(self, *args: str, cwd: Path | None = None,
            timeout: int = DEFAULT_TIMEOUT) -> tuple[int, str]:
        try:
            p = subprocess.run(
                args, cwd=cwd or REPO, capture_output=True, text=True, timeout=timeout
            )
            return p.returncode, (p.stdout + p.stderr).strip()
        except FileNotFoundError:
            return 127, f"{args[0]}: not found"
        except subprocess.TimeoutExpired:
            return 124, f"{' '.join(args)}: timed out"

    def git(self, *args: str) -> tuple[int, str]:
        return self.run("git", *args)

    def gate_results(self) -> list[Result]:
        """Only the GATES, never a precondition or a diagnostic.

        A method rather than a comprehension inside the summary print, because the selftest has to
        be able to CALL it. The first version was inline, the selftest recomputed the same filter
        by hand, and the mutation that widened it survived -- a fixture proving an adjacent claim
        instead of the code under test.
        """
        return [r for r in self.results if r.name.startswith("gate: ")]

    def add(self, status: str, name: str, detail: str = "", remedy: str = "") -> Result:
        r = Result(status, name, detail, remedy)
        self.results.append(r)
        return r

    def working_tree_changes(self) -> list[str]:
        """Changed paths, tracked or not. `-uall` matters: plain --porcelain collapses a new
        untracked directory to "?? dir/", which is how a fresh file can look like nothing at
        all (the same collapse that had rails-flow's Stop gate silently not firing)."""
        code, out = self.git("status", "--porcelain", "-uall")
        if code != 0:
            return []
        paths = []
        for line in out.splitlines():
            if len(line) > 3:
                paths.append(line[3:].split(" -> ")[-1])
        return paths

    # ---- checks -----------------------------------------------------------------------
    def check_prerequisites(self) -> None:
        for tool, why in (
            ("git", "everything"),
            ("python3", "every gate and packaging"),
            ("gh", "issues, PRs and releases"),
        ):
            code, _ = self.run(tool, "--version")
            if code == 0:
                self.add(PASS, f"`{tool}` present")
            else:
                self.add(
                    FAIL, f"`{tool}` missing", f"needed for {why}",
                    f"install {tool} and put it on PATH",
                )

        code, out = self.run("gh", "auth", "status")
        if code == 0:
            self.add(PASS, "`gh` authenticated")
        else:
            self.add(
                FAIL, "`gh` not authenticated",
                "the repo is private at times, so even `git fetch` can fail",
                "gh auth login",
            )

    def check_is_marketplace_repo(self) -> bool:
        """Same precondition as the SessionStart hook. Fatal: nothing else makes sense."""
        if (REPO / ".claude-plugin" / "marketplace.json").is_file():
            self.add(PASS, "this is the claude-skills marketplace repo")
            return True
        self.add(
            FAIL, "not the marketplace repo",
            f"no .claude-plugin/marketplace.json under {REPO}",
            "run this from inside a claude-skills checkout",
        )
        return False

    def check_branch(self) -> None:
        code, branch = self.git("symbolic-ref", "--short", "HEAD")
        if code != 0:
            self.add(
                SKIP, "current branch", "detached HEAD or unborn branch",
                "git checkout dev",
            )
            return
        if branch == "main":
            if self.fix:
                c, out = self.git("checkout", "dev")
                if c == 0:
                    self.fixed.append("checked out `dev` (was on `main`)")
                    self.add(PASS, "on `dev`", "was on `main`; --fix checked out `dev`")
                    return
                self.add(
                    FAIL, "on `main`", f"could not switch: {out}",
                    "git checkout dev — resolve the blocker first",
                )
                return
            self.add(
                FAIL, "on `main`",
                "main is the install surface; work never starts here, and a direct commit "
                "survives every future dev->main merge invisibly",
                "git checkout dev   (or re-run with --fix)",
            )
        elif branch == "dev":
            # `dev` is the integration branch, not a workbench. Sitting on it is correct
            # BETWEEN pieces of work and wrong DURING one -- work branches off it and PRs
            # back into it. Uncommitted changes here are the signal that someone (me, while
            # writing this very check) started editing without branching first.
            dirty = self.working_tree_changes()
            if dirty:
                self.add(
                    FAIL, "editing directly on `dev`",
                    f"{len(dirty)} uncommitted path(s): {', '.join(dirty[:3])}"
                    + (" …" if len(dirty) > 3 else "")
                    + " — `dev` is the integration branch; work branches off it and PRs back in",
                    "git checkout -b feature/<slug>   (untracked and unstaged changes follow you)",
                )
            else:
                self.add(PASS, "on `dev`, clean", "correct resting state between pieces of work")
        else:
            self.add(INFO, f"on `{branch}`", "a work branch — the right place to be mid-task")

    def check_stale_main_ref(self) -> None:
        """The trap that makes the documented dev-vs-main check lie."""
        code, local = self.git("rev-parse", "main")
        if code != 0:
            self.add(
                SKIP, "local `main` ref", "no local `main` branch",
                "git branch main origin/main   (optional; only needed for `git diff dev main`)",
            )
            return
        code, remote = self.git("rev-parse", "origin/main")
        if code != 0:
            self.add(SKIP, "local `main` ref", "no `origin/main` — fetch first", "git fetch --all")
            return
        if local == remote:
            self.add(PASS, "local `main` matches `origin/main`")
            return
        detail = (
            f"local {local[:9]} vs origin {remote[:9]} — this makes `git diff dev main` report "
            "phantom deletions (5,231 of them on a real machine)"
        )
        if self.fix:
            c, out = self.git("branch", "-f", "main", "origin/main")
            if c == 0:
                self.fixed.append("fast-forwarded local `main` to `origin/main`")
                self.add(PASS, "local `main` matches `origin/main`", "--fix updated the ref")
                return
            self.add(FAIL, "stale local `main` ref", f"{detail}; fix failed: {out}",
                     "git branch -f main origin/main")
            return
        self.add(
            FAIL, "stale local `main` ref", detail,
            "git branch -f main origin/main   (safe: you never commit to main)",
        )

    def check_dev_current(self) -> None:
        code, _ = self.git("rev-parse", "origin/dev")
        if code != 0:
            self.add(FAIL, "`origin/dev` unknown", "no remote dev ref", "git fetch --all --prune")
            return
        code, local = self.git("rev-parse", "dev")
        if code != 0:
            self.add(FAIL, "no local `dev`", "", "git checkout dev")
            return
        _, remote = self.git("rev-parse", "origin/dev")
        if local == remote:
            self.add(PASS, "`dev` is current with `origin/dev`")
            return
        _, behind = self.git("rev-list", "--count", "dev..origin/dev")
        _, ahead = self.git("rev-list", "--count", "origin/dev..dev")
        detail = f"{ahead} ahead, {behind} behind"
        if self.fix and ahead == "0":
            c, out = self.git("pull", "--ff-only")
            if c == 0:
                self.fixed.append("pulled `dev`")
                self.add(PASS, "`dev` is current with `origin/dev`", "--fix pulled")
                return
            self.add(FAIL, "`dev` not current", f"{detail}; pull failed: {out}", "git pull")
            return
        self.add(
            FAIL if behind != "0" else INFO, "`dev` not current with `origin/dev`", detail,
            "git pull --ff-only" + ("" if ahead == "0" else "  (you have unpushed commits)"),
        )

    def check_unshipped(self) -> None:
        """Informational: unshipped work is normal, it is not a fault."""
        code, out = self.git("diff", "--stat", "dev", "origin/main")
        if code != 0:
            self.add(SKIP, "unshipped work", "cannot diff dev against origin/main", "git fetch --all")
            return
        if not out.strip():
            self.add(INFO, "no unshipped work", "`dev` and `main` are content-identical")
            return
        _, count = self.git("rev-list", "--count", "origin/main..dev")
        self.add(
            INFO, f"{count} unshipped commit(s) on `dev`",
            "a promotion would ship them; not a fault",
            "read the CHANGELOG `### Unreleased` sections to see what",
        )

    def check_promotion_was_a_merge(self) -> None:
        """Is `dev` an ANCESTOR of `origin/main`? If not, the last promotion was squashed.

        A promotion is a merge commit with `dev` as a parent. Squash it instead and `main` gets a
        one-parent commit holding dev's CONTENT with none of its ANCESTRY -- so the merge base falls
        back to whatever came before, git starts seeing both sides as having independently changed
        the same files, and **the next promotion cannot merge at all**. That is not a style
        preference; v1.83.0 was squashed and v1.84.0 hit six conflicts on files nobody had touched
        twice.

        WHY THIS AND NOT `check_no_direct_to_main`. That one catches the same event by its symptom
        -- a commit on `main` that is not on `dev` -- and it did fire here. But it fires for several
        unrelated causes, its remedy ("cherry-pick them onto dev") is the WRONG advice for a squash,
        and one squash poisons it permanently: after the repair the squash IS reachable from dev, so
        the symptom clears while the habit that produced it does not. This asks the direct question
        instead, and its remedy is the actual fix.

        Checked against `origin/main` rather than the local ref, because a stale local `main` would
        answer for whenever you last fetched.
        """
        code, tip = self.git("rev-parse", "origin/main")
        if code != 0:
            self.add(SKIP, "last promotion was a merge", "no `origin/main`", "git fetch --all")
            return
        # "Is `dev` an ancestor of main" is the WRONG question, and getting it wrong first is worth
        # recording: mid-cycle `dev` has moved past the last release, so it is legitimately not an
        # ancestor, and a check asking that would have waved the real squash straight through.
        #
        # The question that separates the two cases is whether main's tip has a PARENT on `dev`.
        # A merge promotion does; a squash has one parent, which is main's own previous tip.
        if self.git("merge-base", "--is-ancestor", "origin/main", "dev")[0] == 0:
            # Nothing has diverged them: either no promotion yet, or one just repaired.
            self.add(PASS, "the last promotion carried `dev`'s ancestry", "`main` is on `dev`")
            return
        # BOTH conditions, and the second is not redundant. A squash's single parent is main's own
        # previous tip -- which, for a repo whose first promotion this is, IS an ancestor of `dev`.
        # So "has a parent on dev" alone passes the very trap this exists for; the fixture caught
        # that. A promotion must BE a merge (two parents) AND one of them must be on `dev`.
        code, parents = self.git("rev-list", "--parents", "-n", "1", tip.strip())
        kin = parents.split()[1:] if code == 0 else []
        if len(kin) >= 2:
            for p in kin:
                if self.git("merge-base", "--is-ancestor", p, "dev")[0] == 0:
                    self.add(PASS, "the last promotion carried `dev`'s ancestry",
                             f"`main`'s tip merges {p[:9]}, which is on `dev`")
                    return
        self.add(
            FAIL, "the last promotion did NOT carry `dev`'s ancestry",
            f"`origin/main`'s tip ({tip.strip()[:9]}) has {len(kin)} parent(s) and none of them is "
            "on `dev` — the promotion was squashed or rebased, so `main` holds dev's content with "
            "none of its history and the NEXT promotion will conflict on files nobody edited twice",
            "merge `origin/main` into `dev`, resolve every conflict to dev's side, and assert the "
            "merge changes no content (`git diff --cached <dev before> --stat` must be empty); "
            "then always merge a promotion with `gh pr merge --merge`, never --squash",
        )

    def check_no_direct_to_main(self) -> None:
        code, out = self.git("log", "--oneline", "dev..origin/main", "--no-merges")
        if code != 0:
            self.add(SKIP, "direct-to-`main` commits", "cannot compare", "git fetch --all")
            return
        lines = [l for l in out.splitlines() if l.strip()]
        unexpected = [l for l in lines if not l.startswith(KNOWN_DIRECT_TO_MAIN)]
        if not unexpected:
            self.add(PASS, "no unmerged direct-to-`main` commits")
            return
        self.add(
            FAIL, f"{len(unexpected)} direct-to-`main` commit(s) not on `dev`",
            "; ".join(unexpected[:3]) + " — a merge unions, it never removes content that "
            "exists only on main, so these are invisible to every future dev-based change",
            "cherry-pick them onto `dev` and promote, or confirm they are intentional",
        )

    def check_corpora(self) -> None:
        root = REPO / CORPORA_DIR
        missing = [c for c in CORPORA if not (root / c).exists()]
        if not missing:
            self.add(PASS, "design corpora present", f"{CORPORA_DIR}/: " + ", ".join(CORPORA))
            return
        self.add(
            SKIP, f"design corpora missing: {', '.join(missing)}",
            "only `scripts/build_coverage.py` reads them, so everything else works — but the "
            "coverage matrix cannot be regenerated or drift-checked",
            # A nested clone, nothing to link. The old remedy was a clone plus three `ln -s`,
            # which produced paths `.gitignore` could not match at all (#197).
            f"git clone {CORPORA_REPO} {CORPORA_DIR}",
        )

    def check_corpora_ignored(self) -> None:
        """The ignore rules must actually cover the layout the setup instructions prescribe.

        #197: the patterns were `tailwind-ui/`, `everylayout/`, `flowbite*/` while CLAUDE.md
        told maintainers to symlink the kits in. A trailing slash matches a real DIRECTORY, and
        git stores a symlink as mode 120000 — so none of the three matched, and all three sat
        UNTRACKED in the guard written to hide them, directly under doctrine warning about
        656 MB of licensed blobs the rule could not actually stop. That is
        `claims-vs-enforcement` from skills/code-review/SKILL.md, so it is re-checked by script
        rather than remembered.

        Asserted in a THROWAWAY repo seeded with our `.gitignore`, against paths that DO NOT
        EXIST — both deliberate. `git check-ignore` consults the filesystem to decide whether a
        trailing-slash pattern applies, so on a machine that already has the corpora, testing
        the real path matches under BOTH the correct pattern and the buggy one and a regression
        hides. Against a path that is not there, only a slash-free pattern matches — which
        discriminates on every machine, and subsumes the symlink form, so nothing needs
        creating (a symlink would need Developer Mode on Windows).
        """
        gitignore = REPO / ".gitignore"
        if not gitignore.is_file():
            self.add(FAIL, "corpora ignore rules", "no .gitignore at the repo root",
                     "restore .gitignore — without it the licensed corpora are committable")
            return

        tmp = Path(tempfile.mkdtemp(prefix="doctor-ignore-"))
        try:
            code, out = self.run("git", "init", "-q", str(tmp), cwd=tmp)
            if code != 0:
                self.add(SKIP, "corpora ignore rules", f"could not create a probe repo: {out}")
                return
            shutil.copyfile(gitignore, tmp / ".gitignore")

            problems: list[str] = []
            for candidate in MUST_IGNORE:
                verdict = self._ignored_in(tmp, candidate)
                if verdict is None:
                    self.add(SKIP, "corpora ignore rules",
                             f"git check-ignore unusable for {candidate!r}")
                    return
                if not verdict:
                    problems.append(f"{candidate!r} is NOT ignored")
            for candidate in MUST_NOT_IGNORE:
                verdict = self._ignored_in(tmp, candidate)
                if verdict is None:
                    self.add(SKIP, "corpora ignore rules",
                             f"git check-ignore unusable for {candidate!r}")
                    return
                if verdict:
                    problems.append(f"{candidate!r} IS ignored but must not be")

            if problems:
                self.add(
                    FAIL, "corpora ignore rules", "; ".join(problems),
                    "in `.gitignore`, the corpora patterns must be root-anchored and "
                    "slash-FREE (`/design-corpora`, not `design-corpora/`): a trailing slash "
                    "matches a real directory only, never a symlink (#197)",
                )
            else:
                self.add(PASS, "corpora ignore rules",
                         f"{len(MUST_IGNORE)} ignored, {len(MUST_NOT_IGNORE)} near-misses clear")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _ignored_in(self, probe: Path, candidate: str) -> bool | None:
        """True if ignored, False if not, None if git could not answer.

        Isolated from global/system git config: a maintainer whose personal `core.excludesFile`
        happens to list `design-corpora` would otherwise make this pass no matter what our
        `.gitignore` says — a fail-open inside the check for a fail-open. Exit 0 means ignored
        and 1 means not; anything else (128 = fatal) returns None rather than reading as "not
        ignored", so a broken invocation cannot be mistaken for a verdict.
        """
        try:
            p = subprocess.run(
                ["git", "check-ignore", "--", candidate],
                cwd=probe, capture_output=True, text=True, timeout=60,
                env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull,
                     "GIT_CONFIG_SYSTEM": os.devnull},
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        if p.returncode == 0:
            return True
        if p.returncode == 1:
            return False
        return None

    def check_dist_clean(self) -> None:
        """Compare committed `dist/` against a clean build — WITHOUT leaving a trace.

        The rebuild is the only way to know, but `package_core.py` writes into `dist/` and has
        no output-dir flag, so this snapshots the bytes first and restores them afterwards. A
        diagnostic that mutates the repo is not a diagnostic. The first version of this skipped
        the restore and was idempotent only because the packer is byte-deterministic — true
        today, incidental rather than guaranteed, and it would have silently destroyed
        intentional uncommitted `dist/` edits.
        """
        dist = REPO / "dist"
        if not dist.is_dir():
            self.add(SKIP, "`dist/` drift guard", "no dist/ directory",
                     "python3 scripts/package_core.py")
            return

        snapshot = {p: p.read_bytes() for p in sorted(dist.glob("*.skill"))}
        try:
            code, out = self.run("python3", "scripts/package_core.py")
            if code != 0:
                self.add(FAIL, "`dist/` rebuild failed", out.splitlines()[-1] if out else "",
                         "python3 scripts/package_core.py")
                return
            # After the rebuild the working tree IS a clean build, so anything git reports as
            # changed is committed content that differs from it — exactly the CI drift guard.
            _, status = self.git("status", "--porcelain", "dist/")
            if not status.strip():
                self.add(PASS, "committed `dist/` is a clean build")
            else:
                self.add(
                    FAIL, "committed `dist/` does not match a clean build",
                    status.strip().replace("\n", "; "),
                    "python3 scripts/package_core.py && git add dist/ && commit — the CI drift "
                    "guard fails a release otherwise",
                )
        finally:
            # Restore byte-for-byte, including files the rebuild may have added.
            for path, data in snapshot.items():
                if path.read_bytes() != data:
                    path.write_bytes(data)
            for p in dist.glob("*.skill"):
                if p not in snapshot:
                    p.unlink()

    def check_gates(self) -> None:
        corpora_absent = any(not (REPO / CORPORA_DIR / c).exists() for c in CORPORA)
        for name, cmd in GATES:
            script = REPO / cmd[1]
            if not script.exists():
                self.add(
                    SKIP, f"gate: {name}", f"{cmd[1]} does not exist",
                    "this checkout predates the gate — `git pull` on `dev`",
                )
                continue
            # A gate that CANNOT run is not a broken machine. The corpora are optional (only
            # build_coverage.py reads them), so failing this gate for their absence told a
            # contributor to "fix the failures before doing maintenance work" about a file they
            # are not required to have — the mirror image of the SKIP-as-PASS bug this script
            # exists to prevent, and it made "OPTIONAL" false for anyone running --gates.
            if name in CORPORA_GATES and corpora_absent:
                self.add(
                    SKIP, f"gate: {name}", "licensed corpora absent — nothing to drift-check",
                    f"git clone {CORPORA_REPO} {CORPORA_DIR}",
                )
                continue
            code, out = self.run(*cmd, timeout=SLOW_GATES.get(name, DEFAULT_TIMEOUT))
            if code == 0:
                self.add(PASS, f"gate: {name}")
            elif code == 3:
                # Exit 3 is a gate's own "I ran but could not check everything" — currently
                # lint_markdown_code.py with node or ruby absent, which is the normal state of a
                # cloud container. Reporting `ok` there would let 242 of 276 blocks go unchecked
                # behind a green line, so it is a SKIP and the reason comes from the gate itself.
                reason = out.strip().splitlines()[0] if out.strip() else "incomplete run"
                self.add(SKIP, f"gate: {name}", reason,
                         "install the missing interpreter, or state in the PR that the gate "
                         "could not run — a skip is not a pass")
            else:
                tail = out.splitlines()[-1] if out else f"exit {code}"
                self.add(FAIL, f"gate: {name}", tail, " ".join(cmd))

    # ---- driver ----------------------------------------------------------------------
    def diagnose(self, gates: bool, gates_only: bool = False) -> int:
        if not self.check_is_marketplace_repo():
            self.report()
            return 2
        # GATES-ONLY is for CI, and skipping the machine diagnostics there is the point rather than a
        # shortcut. Every one of them asks a question about a MAINTAINER'S CLONE: which branch you are
        # on, whether your local `main` ref is stale, whether `gh` is authenticated, whether the
        # licensed corpora are attached. A runner is not a clone anyone works in -- it is detached, it
        # has no `gh` login, and it will never have the private corpora. Running them there produces
        # failures that mean nothing, which teaches people to ignore a red build: the one outcome
        # worse than having no CI at all.
        #
        # The GATES are the opposite. Every one is a claim about the CONTENT of the repo, so it holds
        # identically on a runner and on a laptop. That is what makes them the right half to automate,
        # and the only half.
        if gates_only:
            self.check_gates()
            self.report()
            return 1 if any(r.status == FAIL for r in self.results) else 0
        self.check_prerequisites()
        self.git("fetch", "--all", "--tags", "--prune")
        self.check_branch()
        self.check_stale_main_ref()
        self.check_dev_current()
        self.check_promotion_was_a_merge()
        self.check_no_direct_to_main()
        self.check_unshipped()
        self.check_corpora()
        self.check_corpora_ignored()
        self.check_dist_clean()
        if gates:
            self.check_gates()
        else:
            self.add(
                SKIP, "full gate sweep", "not requested",
                "re-run with --gates once the machine is otherwise healthy",
            )
        self.report()
        return 1 if any(r.status == FAIL for r in self.results) else 0

    def report(self) -> None:
        icon = {PASS: "  ok  ", FAIL: " FAIL ", SKIP: " skip ", INFO: " note "}
        for r in self.results:
            print(f"[{icon[r.status]}] {r.name}")
            if r.detail:
                print(f"           {r.detail}")
            if r.remedy and r.status in (FAIL, SKIP):
                print(f"           -> {r.remedy}")

        if self.fixed:
            print("\nRepaired (safe changes only):")
            for f in self.fixed:
                print(f"  - {f}")

        counts = {s: sum(1 for r in self.results if r.status == s) for s in (PASS, FAIL, SKIP, INFO)}
        print(
            f"\n{counts[PASS]} passed, {counts[FAIL]} failed, {counts[SKIP]} skipped, "
            f"{counts[INFO]} note(s)"
        )
        # THE GATE TALLY, SEPARATELY. The line above counts every result, and `--gates-only` also
        # runs `check_is_marketplace_repo` -- a PRECONDITION, not a gate. So the total has always
        # been gates + 1, and anyone reading it as "how many gates are there" is off by one. Three
        # wrong counts reached shipped text that way in one afternoon: a CHANGELOG bullet claiming
        # "83 (was 80)" against 82 and 79, a PR body claiming 85 against 84, and the same 85 stated
        # to the maintainer. Two sessions then reconciled 84 against 85 as a units disagreement, and
        # it was not one -- it was this. A number nobody can read correctly is a defect in the
        # reporting, not in the reader, which is the same argument as SKIP never rendering as PASS.
        gates = self.gate_results()
        if gates:
            g = {s: sum(1 for r in gates if r.status == s) for s in (PASS, FAIL, SKIP)}
            print(
                f"of those, {len(gates)} are gates: {g[PASS]} passed, {g[FAIL]} failed, "
                f"{g[SKIP]} skipped — quote THIS number as the gate count"
            )
        # Skipped is called out deliberately: a check that did not run is not a check that
        # passed, and conflating the two is the defect this tool exists to prevent.
        if counts[SKIP]:
            print("Skipped checks did NOT run — they are not passes. Read their remedies above.")
        if counts[FAIL]:
            print("Fix the failures above before doing maintenance work.")
        elif not counts[SKIP]:
            print("Machine is ready.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Diagnose and repair a maintainer machine.")
    p.add_argument("--fix", action="store_true", help="apply the SAFE repairs (never rewrites history)")
    p.add_argument("--gates", action="store_true", help="also run the full gate sweep (slower)")
    p.add_argument("--gates-only", action="store_true",
                   help="run ONLY the gate sweep, skipping machine diagnostics (for CI)")
    p.add_argument("--selftest", action="store_true", help="prove the checks fire and stay silent")
    args = p.parse_args(argv)

    if args.selftest:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import maintainer_doctor_selftest as st

        return st.run()

    return Doctor(fix=args.fix).diagnose(gates=args.gates or args.gates_only,
                                         gates_only=args.gates_only)


if __name__ == "__main__":
    sys.exit(main())
