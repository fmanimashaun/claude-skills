#!/usr/bin/env python3
"""Prove every selftest CAN fail — by breaking its subject and requiring it to notice.

Run:  python3 scripts/mutation_check.py            # all guards
      python3 scripts/mutation_check.py --guard lint_self_consistency
      python3 scripts/mutation_check.py --selftest  # prove this checker itself can fail

WHY THIS EXISTS (#233). The repo has six selftests and fourteen gates, and until now **nothing
checked that a selftest fails when the thing it guards breaks**. Two fixtures written in one
session were vacuous and passed for the wrong reason:

  * a `hasattr` on a function that never existed, so it compared `[] == []`
  * a cross-contamination scenario whose two classes shared one fenced block, leaving the second
    unregistered — the scenario never ran

Both looked right. One survived until a maintainer asked whether the fix was real. CLAUDE.md
already says to make every new check fail on purpose once; the failure mode is not ignorance of
that rule, it is skipping it under momentum. So it becomes a gate.

WHAT IT IS NOT. Not a general mutation framework — no AST rewriting, no operator taxonomy, no
survivor analysis. Each guard declares a short list of **named, hand-chosen mutations** to its own
subject, each with the fixture it is expected to trip. A declared list is auditable and cheap; a
generated one produces survivors nobody triages, and an untriaged mutation report is
indistinguishable from a passing one.

HOW A MUTATION IS APPLIED. The subject is copied to a temp directory with one exact string
replaced, its selftest is copied beside it, and the selftest runs against the mutant. Nothing in
the working tree is touched — earlier hand-runs of this edited real files and relied on a `finally`
to restore them, which is one interrupted process away from leaving a mutated repo.

THE ASSERTION THAT MATTERS. A mutation must be *verified applied* before its result counts. An
anchor that no longer matches produces a mutant identical to the original, the selftest passes, and
that reads exactly like a caught mutation. So a stale anchor is a hard error, never a pass.

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Mutation:
    """One hand-chosen break, and the fixture that must notice it."""

    name: str
    old: str
    new: str
    # Substring expected in the selftest's failure output. Proves the RIGHT fixture tripped, not
    # merely that something did -- a mutation caught by an unrelated assertion is a coincidence,
    # and would mask the guard it was written for going quiet.
    #
    # Use the FIXTURE'S LABEL, not the finding's message text. Most mutations here make a finding
    # DISAPPEAR, so its message is absent from the output by definition -- expecting it fails for
    # the wrong reason. (Learned on this checker's first run: three of sixteen expectations were
    # written as finding text and reported spurious "wrong fixture" results.) Empty string means
    # any failure counts, for mutations that break the module hard enough to raise.
    expects: str


@dataclass(frozen=True)
class Guard:
    name: str
    subject: str          # the module whose behaviour is guarded
    selftest: str         # the script that must notice a break
    # Extra modules the selftest imports; copied alongside so the mutant is self-contained.
    deps: tuple[str, ...] = ()
    # Repo files the selftest READS (not imports). Copied at their repo-relative path, because
    # a selftest resolving `Path(__file__).parents[1] / ".gitignore"` must still find it. Found
    # when maintainer_doctor's mutant died on a missing .gitignore -- an environmental failure the
    # `expects` check correctly refused to count as a caught mutation.
    needs: tuple[str, ...] = ()
    mutations: tuple[Mutation, ...] = field(default_factory=tuple)


GUARDS: tuple[Guard, ...] = (
    Guard(
        name="lint_self_consistency",
        subject="scripts/lint_self_consistency.py",
        selftest="scripts/lint_self_consistency.py",   # --selftest lives in the module itself
        mutations=(
            Mutation(
                "the schema-parity rule stops noticing an undocumented field",
                "        missing = sorted(f for f in fields if f not in documented)",
                "        missing = []",
                "qa-reporter missing an enforced field",
            ),
            Mutation(
                "a renamed field tuple becomes a silent pass instead of a finding",
                '            findings.append(Finding(\n                "findings-schema-drift", rel(script), 1,\n                f"cannot find the `{group}` field tuple, so the schema cannot be compared. If it "\n                f"was renamed, update this rule rather than leaving the comparison silently dead",\n            ))\n',
                "",
                "a renamed field tuple must be a finding",
            ),
            Mutation(
                "the topology rule stops requiring a merge rule on a fan-out",
                'if kind == "parallel" and not re.search(r"\\bmerge:", detail, re.I):',
                "if False:",
                "parallel without a merge rule",
            ),
            Mutation(
                "the topology rule demands a declaration from every single-agent command",
                "        if len(dispatched) < 2:\n            continue\n",
                "        if False:\n            continue\n",
                "a single agent needs no declaration",
            ),
            Mutation(
                "the coercion rule drops its backreference and flags any two identifiers",
                r'\b\1\.to_(?:i|f)\b',
                r'\b[a-z_]+\.to_(?:i|f)\b',
                "different identifiers are not a contradiction",
            ),
            Mutation(
                "the coercion rule stops skipping Ruby comments",
                '            if line.lstrip().startswith("#"):\n                continue\n',
                "            if False:\n                continue\n",
                "a Ruby comment quoting the bad expression is silent",
            ),
            Mutation(
                "render rules require a paren again (the #142 blind spot)",
                r'_RENDER_CALL = re.compile(r"render\(?\s*',
                r'_RENDER_CALL = re.compile(r"render\(\s*',
                "paren-less render",
            ),
            Mutation(
                "slot window scans to end-of-document (the false-positive generator)",
                "stop = blocks[position + 1].start() if position + 1 < len(blocks) else len(body)",
                "stop = len(body)",
                "bleed into each other",
            ),
            Mutation(
                "corpora no longer pruned from the walk",
                ', "design-corpora"}',
                "}",
                "not ours to enforce",
            ),
            Mutation(
                "unbounded gh queries stop being flagged",
                "if not _GH_LIST.search(line) or not _INVOCATION.search(line):",
                "if True:",
                "unbounded",
            ),
            Mutation(
                "the renders_many singular setter is flagged as a mismatch again",
                'if used in declared or f"{used}s" in declared:',
                "if used in declared:",
                "singular setter is correct",
            ),
            Mutation(
                "an undemonstrated component stops being flagged",
                "    for name in sorted(top - called):",
                "    for name in []:",
                "with no call site",
            ),
            Mutation(
                "a call site naming a nonexistent component stops being flagged",
                "    for name in sorted(called - top - nested):",
                "    for name in []:",
                "nothing declares",
            ),
            # The two ORIGINAL rules had fixtures but never got mutations — the per-rule coverage
            # check in mutation_check_selftest.py found that, three rules later.
            Mutation(
                "the install-line rule stops firing (#203, second occurrence)",
                '        if not re.search(rf"/plugin\\s+install\\s+{re.escape(name)}@", body):',
                '        if False:',
                "a declared plugin with no install line",
            ),
            Mutation(
                "the CI plugin-root rule stops firing",
                '                if "CLAUDE_PLUGIN_ROOT" in line and not line.lstrip().startswith("#"):',
                '                if False:',
                "a scaffolded CI job using the plugin root",
            ),
            Mutation(
                "a dead settings key stops being reported (the file's first rule)",
                "        if not keys:\n            continue",
                "        if True:\n            continue",
                "settings key no reader reads",
            ),
            Mutation(
                "an unenforced mandatory flag stops being reported (the file's second rule)",
                "                if any(flag_is_enforced(flag, src) for src in definers.values()):",
                "                if True:",
                "docs say always pass, code leaves optional",
            ),
            Mutation(
                "the v4 outline-none rule stops firing (#305)",
                '            if re.search(r"(?<!-)\\b(?:focus|focus-visible|active|group-focus)\\:outline-none\\b", line):',
                '            if False:',
                "a v4 recipe using outline-none",
            ),
            Mutation(
                "a broken pointer to one of our own files stops being reported (#100)",
                "                if (owning_plugin / match.group(1)).exists():\n                    continue",
                "                if True:\n                    continue",
                "plugin points at a reference file it does not ship",
            ),
            Mutation(
                "the **attrs carve-out is removed, so correct call sites are flagged (#95)",
                '                if not _KW_SPLAT.search(match.group(1)):',
                '                if True:',
                "a **attrs initializer accepts arbitrary keywords",
            ),
            Mutation(
                "the pointer rule goes back to an extension allowlist (#272)",
                'r"\\$\\{CLAUDE_PLUGIN_ROOT\\}/([A-Za-z0-9._/-]*[A-Za-z0-9_-]\\.[A-Za-z0-9]+)")',
                'r"\\$\\{CLAUDE_PLUGIN_ROOT\\}/([A-Za-z0-9._/-]+\\.(?:md|py|sh|json))")',
                "a non-allowlisted extension is still a pointer",
            ),
            Mutation(
                "the skill-pointer half stops being reported (#100)",
                "            if (ROOT / match.group(1)).exists():\n                continue",
                "            if True:\n                continue",
                "command points at a skill doc that was renamed away",
            ),
            Mutation(
                "invisible characters stop being reported (#95)",
                "                if index == -1:\n                    continue",
                "                if True:\n                    continue",
                "a no-break space in shipped markdown",
            ),
            Mutation(
                "the invisible set shrinks to whitespace only, letting a BOM through",
                '    "\\ufeff": "BYTE ORDER MARK",',
                "",
                "a BOM inside the body of a file",
            ),
            Mutation(
                "the prose carve-out on the icon rule is removed (#95)",
                "                continue  # prose, not a call — see _PAREN_LESS_ARGS",
                "                pass",
                "prose naming the banned args is not a call",
            ),
            Mutation(
                "the icon carve-out widens to swallow variable-named calls",
                r'_PAREN_LESS_ARGS = re.compile(r"^[ \t]*(?:[\"\':]|\w+[ \t]*,)")',
                r'_PAREN_LESS_ARGS = re.compile(r"^[ \t]*[\"\':]")',
                "paren-less call on a variable still flagged",
            ),
            Mutation(
                "a declared plugin missing from the docs stops being flagged",
                "if name in blob:\n                continue",
                "if True:\n                continue",
                "undocumented-plugin",
            ),
        ),
    ),
    Guard(
        name="build_coverage",
        subject="scripts/build_coverage.py",
        selftest="scripts/build_coverage_selftest.py",
        mutations=(
            Mutation(
                "the totality guard stops naming unclassified corpus entries",
                "def verify_totality(",
                "def _disabled_verify_totality(",
                "",   # any failure counts: removing the entry point breaks many fixtures
            ),
            Mutation(
                "a promoted row keeps its stale BUILD fallback unnoticed (#95)",
                "    stale = sorted(\n"
                "        {e.name for e in ENTRIES if e.is_documented and e.build.strip()}\n"
                "        | (set(BUILD) & {e.name for e in ENTRIES if e.is_documented})\n"
                "    )",
                "    stale = []",
                "still carrying a BUILD fallback",
            ),
            Mutation(
                "the stale-fallback guard keys on the NAME instead of the status",
                "{e.name for e in ENTRIES if e.is_documented})",
                "{e.name for e in ENTRIES})",
                "a needs-doctrine row carrying a BUILD fallback is correct",
            ),
            # The guard reads TWO sources -- `resolve_build` prefers a row's own `build=` kwarg
            # over the BUILD dict -- so each half needs its own mutation. Covering only the dict
            # half is how the inline half went unguarded in the first place (#95).
            Mutation(
                "the stale-fallback guard stops reading a row's inline `build=` kwarg",
                "{e.name for e in ENTRIES if e.is_documented and e.build.strip()}\n",
                "set()\n",
                "a documented row carrying its fallback inline rather than in BUILD",
            ),
            # The Needs-doctrine section reached ZERO rows (#95/#91), so the empty branch is now
            # the live one -- a regression to the always-table form would read as normal output.
            Mutation(
                "the empty Needs-doctrine section prints guidance for rows that do not exist",
                "    if needs:\n",
                "    if True:\n",
                "yet the Tracked table header was still emitted",
            ),
        ),
    ),
    Guard(
        name="lint_markdown_code",
        subject="scripts/lint_markdown_code.py",
        selftest="scripts/lint_markdown_code_selftest.py",
        mutations=(
            Mutation(
                "the language boundary is dropped, so ```json parses as JavaScript again (#248)",
                r'FENCE = re.compile(r"^[ \t]*```[ \t]*(" + _LANG_ALT + r")\b[^\n]*\n(.*?)^[ \t]*```",',
                r'FENCE = re.compile(r"^[ \t]*```[ \t]*(" + _LANG_ALT + r")[^\n]*\n(.*?)^[ \t]*```",',
                "```json is NOT javascript",
            ),
            Mutation(
                "a stalled interpreter is reported as a syntax error again",
                '        raise InterpreterStalled(f"{cmd[0]} did not answer within 30s") from exc',
                '        return 127, "", f"could not run {cmd[0]}: {exc}"',
                "a stalled interpreter did not raise",
            ),
            Mutation(
                "the ERB block-tag normalisation is removed (20 false positives return)",
                '    code = ERB_BLOCK_TAG.sub(r"<%\\1%>", ERB_RAW_TAG.sub("<%=", code))',
                "    code = ERB_RAW_TAG.sub(\"<%=\", code)",
                "erb: <%= … do %> block tag",
            ),
            Mutation(
                "the unterminated-tag check is removed — ERB will not catch it",
                "    line = _unterminated_erb_tag(code)",
                "    line = None",
                "erb: unterminated tag",
            ),
            Mutation(
                "`<%%` stops being treated as an escaped literal",
                '        if code[i + 2:i + 3] == "%":      # `<%%` — an escaped literal, not a tag',
                "        if False:",
                "erb: `<%%` is an escaped literal, not an unterminated tag",
            ),
            Mutation(
                "elision substitution is dropped, so documentation `...` reads as code",
                "    normalised = substitute(code, lang)",
                "    normalised = code",
                "ruby: (...) argument elision",
            ),
        ),
    ),
    Guard(
        name="validate_evidence",
        subject="plugins/qa-flow/scripts/validate_evidence.py",
        selftest="plugins/qa-flow/scripts/validate_evidence_selftest.py",
        mutations=(
            Mutation(
                "a Pass on a non-2xx/3xx page is accepted (the #106 defect)",
                "elif not _http_ok(row[\"HTTP\"]):",
                "elif False:",
                "not the page under test",
            ),
            Mutation(
                "duplicate finding signatures stop being rejected (#118's dedupe)",
                "        if sig in seen:",
                "        if False:",
                "repeated signature",
            ),
            Mutation(
                "runtime severity is trusted instead of recomputed",
                "    elif required == S1 and severity != S1:",
                "    elif False:",
                "downgraded to S2",
            ),
            # #114 -- the sampling guard is the whole profile. Without it a row that walked 3 of
            # 40 elements reads exactly like a clean page, which is the 25-of-72 defect returning.
            Mutation(
                "a keyboard walk may sample instead of covering the inventory (#114)",
                '        if accounted < counts["Interactive"]:',
                "        if False:",
                "sampled 3 of 40 interactive elements",
            ),
            Mutation(
                "a focus-indicator count may exceed the elements actually focused",
                '        counts["No Focus Indicator"] > counts["Tab Stops"]\n    ):',
                "        False\n    ):",
                "more missing indicators than elements focused",
            ),
            # The verified WebKit caveat. Removing it turns every link on a WebKit run into a
            # false S1 -- a platform default reported as an application defect.
            Mutation(
                "webkit unreachable counts stop needing Full Keyboard Access confirmed",
                "        if not any(token in note for token in FKA_TOKENS):",
                "        if False:",
                "unreachable on webkit without confirming Full Keyboard Access",
            ),
            # #115 -- both directions of the Submit Mode contract, because each alone leaves the
            # other half of the hole open.
            Mutation(
                "a forms row may claim verdicts on an error state it never triggered (#115)",
                '        elif not exercised and raw != "not run" and mode in FORM_MODES:',
                "        elif False:",
                "verdicts on an error state a dry-run never triggered",
            ),
            Mutation(
                "a submitted form may record no error-contract verdict at all",
                '        if exercised and raw == "not run":',
                "        if False:",
                "submitted an invalid form but recorded no verdict",
            ),
            # Both structural counters are bounded by the same denominator, and the loop is what
            # makes them one rule instead of two copies that can drift.
            Mutation(
                "a form may report more unlabelled controls than it has (#115)",
                '        if {"Controls", column} <= counts.keys() and counts[column] > counts["Controls"]:',
                "        if False:",
                "more unlabelled controls than the form has",
            ),
            # The shared recompute behind both new profiles: `_runtime_extra` spells its own
            # comparison out, so this mutation covers the keyboard/forms path specifically.
            Mutation(
                "keyboard/forms severity is trusted instead of recomputed",
                "    elif required == S1:",
                "    elif False:",
                "unreachable elements downgraded to S2",
            ),
            # #116 -- this profile's distinctive guarantee runs the OPPOSITE way to keyboard's and
            # forms': it stops a row grading an advisory UP into a defect. Both halves of that
            # boundary get a mutation, because each alone leaves the other criterion unguarded.
            Mutation(
                "motion ignoring the preference becomes gating (SC 2.3.3 is Level AAA) (#116)",
                '        gating=(("Autoplay No Control", S1), ("End State Committed", S1)),',
                '        gating=(("Autoplay No Control", S1), ("End State Committed", S1),'
                ' ("Motion Not Suppressed", S1)),',
                "recorded as advisory",
            ),
            Mutation(
                "a print nit becomes a release-blocking defect, with no WCAG upstream (#116)",
                "        gating=(),",
                '        gating=(("Ink Burning", S1),),',
                "print nit inflated",
            ),
            # The mode contract. Without it a row carries counts from a condition it never
            # emulated, which is the forms Submit Mode hole in a new dimension.
            Mutation(
                "an emulation row may carry counts from a mode it never emulated (#116)",
                "        if column in spec.numeric:\n            continue\n        if row[column]:",
                "        if column in spec.numeric:\n            continue\n        if False:",
                "carrying a forced-colors count",
            ),
            # The WebKit ceiling. Removing it lets a forced-colors run on an engine that applies
            # no forcing report CLEAN -- false confidence, not false defects.
            Mutation(
                "a forced-colors result on webkit stops being a platform ceiling (#116)",
                '    if mode == "forced-colors" and engine == "webkit":',
                "    if False:",
                "platform ceiling",
            ),
            Mutation(
                # Now anchored in the shared `_check_bounds` helper rather than in one profile:
                # perf (#117) was the third caller to want this rule, and a third textual copy
                # would have made this very anchor match twice -- a hard error, by design.
                "an emulation count may exceed the inventory it was drawn from (#116)",
                "        if {column, denominator} <= counts.keys() and counts[column] > "
                "counts[denominator]:",
                "        if False:",
                "more unsuppressed animations",
            ),
            # #117 -- every other profile's blind spot leaves a BLANK. This one's returns a
            # plausible number: `CLS 0` from an engine with no layout-shift observer, a byte total
            # summed from an API that reports 0 for cross-origin assets. So each mutation below
            # makes a fabricated measurement read as a real one.
            Mutation(
                "a metric may be recorded from an engine whose observer does not exist (#117)",
                "        for column in PERF_CHROMIUM_ONLY:\n            if row[column]:",
                "        for column in PERF_CHROMIUM_ONLY:\n            if False:",
                "CLS 0 on firefox",
            ),
            # The ceiling is this profile's distinctive direction -- #114/#115 stop a row grading a
            # defect down, #116 stops it grading an advisory up, and this stops it blocking a
            # release on a number no standard underwrites.
            Mutation(
                "a client-side timing may block a release (#117's severity ceiling)",
                '    if severity == S1:\n        findings.append(\n            f"{where}: '
                "Severity S1 on a perf row",
                '    if False:\n        findings.append(\n            f"{where}: '
                "Severity S1 on a perf row",
                "a client-side timing graded S1",
            ),
            Mutation(
                "LCP joins the gating counters, so a localhost timing becomes a defect (#117)",
                "PERF_GATING: tuple[tuple[str, str], ...] = (\n    (CLS_OVER_BUDGET, S2),",
                'PERF_GATING: tuple[tuple[str, str], ...] = (\n    ("LCP ms", S2),\n'
                "    (CLS_OVER_BUDGET, S2),",
                "a slow LCP graded S2",
            ),
            # The byte instrument. transferSize is 0 for a cross-origin asset with no
            # Timing-Allow-Origin and 0 for a cache hit, so without this a budget passes by
            # measuring nothing -- a gate that cannot fail, in the literal sense.
            Mutation(
                "a clean byte verdict may be reported over bytes nobody measured (#117)",
                '    if counts.get("Opaque Requests", 0) > 0 and counts.get('
                '"Oversized Requests") == 0:',
                "    if False:",
                "among the ones that reported a size",
            ),
            Mutation(
                "CLS stops being compared against the budget the row carries (#117)",
                "            cls_over = 1 if measured > budget else 0",
                "            cls_over = 0",
                "CLS over the row's own budget",
            ),
            # `float()` accepts nan and inf; both sail through the budget comparison as if they
            # were measurements, and nan compares false against everything.
            Mutation(
                "a non-finite or negative CLS is accepted as a measurement (#117)",
                "    if not math.isfinite(number) or number < 0:",
                "    if False:",
                "CLS recorded as nan",
            ),
            Mutation(
                "the interaction probe may run on the visit it is measuring (#117)",
                '    elif probe == "same-visit":',
                "    elif False:",
                "ran on the same visit as the metric read",
            ),
            # #117's own acceptance criteria, which the profile claims to ENFORCE rather than
            # describe: breaches carry an attributable cause, and metrics persist for trending.
            # A claim of "enforced" with no mutation behind it is the prose it replaced.
            Mutation(
                "an LCP time may be recorded with nothing to attribute it to (#117)",
                '    if "LCP ms" in counts and not row["LCP Element"]:',
                "    if False:",
                "nothing to attribute it to",
            ),
            Mutation(
                "a measured route may persist nothing to compare the next run against (#117)",
                '    if not row["Evidence"]:\n        findings.append(\n            f"{where}: '
                "measured without an Evidence path",
                '    if False:\n        findings.append(\n            f"{where}: '
                "measured without an Evidence path",
                "nothing persisted to compare",
            ),
        ),
    ),
    Guard(
        name="route_coverage",
        subject="plugins/qa-flow/scripts/route_coverage.py",
        selftest="plugins/qa-flow/scripts/route_coverage_selftest.py",
        deps=("plugins/qa-flow/scripts/validate_evidence.py",),
        mutations=(
            Mutation(
                ":id matches greedily, over-crediting coverage",
                'out.append(r"[^/]+")',
                'out.append(r".+")',
                "swallow a deeper path",
            ),
            Mutation(
                "a findings rollup is credited as real visits",
                "columns = ROUTE_SOURCES.get(profile.name)",
                'columns = ROUTE_SOURCES.get(profile.name) or ("Example Routes",)',
                "contributes no coverage",
            ),
            # Classifying a new pass and actually READING it are two claims. The
            # "every profile classified" check proves only the first.
            Mutation(
                "the keyboard walk stops earning route coverage (#114)",
                '    "keyboard": ("Route", "Requested URL", "Final URL"),',
                "",
                "keyboard walk was not credited",
            ),
            Mutation(
                "the forms pass stops earning route coverage (#115)",
                '    "forms": ("Route", "Requested URL", "Final URL"),',
                "",
                "forms pass was not credited",
            ),
        ),
    ),
    Guard(
        name="evidence_manifest",
        subject="plugins/qa-flow/scripts/evidence_manifest.py",
        selftest="plugins/qa-flow/scripts/evidence_manifest_selftest.py",
        mutations=(
            Mutation(
                "a truncated final line crashes the parse (#111's own defect)",
                "        except json.JSONDecodeError:\n            truncated += 1\n            continue",
                "        except json.JSONDecodeError:\n            raise",
                "",   # the killed-run fixtures raise Unusable; any failure counts
            ),
            Mutation(
                "unreached units stop being distinguished from a complete run",
                '        "unreached": unreached,\n        "aborted": bool(unreached) or truncated > 0,',
                '        "unreached": [],\n        "aborted": False,',
                "unreached",
            ),
            Mutation(
                "full-page evidence accepted for a component purpose",
                'elif purpose in CLIPPED_PURPOSES and capture != "clipped":',
                "elif False:",
                "full-page",
            ),
        ),
    ),
    Guard(
        name="setup_doctrine_crosscheck",
        subject="plugins/design-flow/scripts/setup_doctrine_crosscheck.py",
        selftest="plugins/design-flow/scripts/setup_doctrine_crosscheck.py",
        mutations=(
            Mutation(
                "the error direction is disabled — #104 instance 1 ships again",
                "        if key in provided:\n            continue",
                "        if True:\n            continue",
                "instance-1 regression fires",
            ),
            Mutation(
                "every config key is treated as ungenerated, so the fixed state fails too",
                "        if key in provided:\n            continue",
                "        if False:\n            continue",
                "fixed state is clean",
            ),
            Mutation(
                "generated-but-unreferenced is escalated from a warning to an error",
                '        report.warn(\n            f"setup.md sets',
                '        report.error(\n            f"setup.md sets',
                "unreferenced config warns without failing",
            ),
            # Guards the anti-false-positive control: without the `reads and` conjunct, a
            # doctrine that names an out-of-scope initializer (simple_form, owned by
            # /design-flow:component) and reads no config at all would error. That is the
            # exact false positive #150 would die of.
            Mutation(
                "the structural check fires with no config read at all (cries wolf)",
                "    if reads and not inits:",
                "    if not inits:",
                "out-of-scope initializer is not flagged",
            ),
            # A run that scanned nothing prints the same clean verdict as a run that scanned
            # the whole tree. Without this guard the check can be pointed anywhere and still
            # report a pass — the failure mode build_coverage.py --selftest had.
            Mutation(
                "a run that examined zero files reports clean again",
                "    if not scanned:",
                "    if False:",
                "empty doctrine tree is an error, not a pass",
            ),
            # `provided` reverts to a whole-file scan, so a key MENTIONED anywhere in setup.md
            # counts as generated. This was a real defect: the docstring claimed the key was
            # named "precisely at the step that generates the initializer" while the code did
            # set membership over the whole file — claims-vs-enforcement inside the guard
            # written to catch that class.
            Mutation(
                "a mention anywhere in setup.md counts as a generation again",
                "    for chunk in setup_steps(text):\n"
                "        provided |= set(CONFIG_KEY.findall(chunk)) & set(INITIALIZER.findall(chunk))",
                "    provided = set(mentioned)",
                "a stray key mention does not count as generated",
            ),
            # The 1/2 exit split collapses: an environment fault reports as doctrine drift and
            # sends a maintainer hunting a defect that does not exist.
            Mutation(
                "an unreadable input exits 1 (drift) instead of 2 (environment)",
                '        print(f"setup_doctrine_crosscheck: {exc}", file=sys.stderr)\n'
                "        return 2",
                '        print(f"setup_doctrine_crosscheck: {exc}", file=sys.stderr)\n'
                "        return 1",
                "an undecodable doctrine file exits 2, not 1",
            ),
            # The read guard degrades from abort to silent skip. A partial scan then produces a
            # confident verdict over doctrine it never read — the failure mode the whole
            # `scanned` counter exists to prevent, reintroduced one level down.
            Mutation(
                "an unreadable doctrine file is silently skipped instead of aborting",
                '                raise InputError(f"cannot read doctrine file {rel}: {exc}") from exc',
                "                continue",
                "an undecodable doctrine file exits 2, not 1",
            ),
            # Fence tracking is dropped, so a `# ` shell comment inside ``` becomes a step
            # boundary again — splitting a step between its initializer and its key read, and
            # reporting correct input as drift. setup.md's own snippet contains two such lines.
            Mutation(
                "fenced code splits a step again, so correct input reads as drift",
                '        if stripped[:3] in ("```", "~~~"):',
                "        if False:",
                "a fenced code example does not split a step",
            ),
        ),
    ),
    Guard(
        name="issue_graph",
        subject="scripts/issue_graph.py",
        selftest="scripts/issue_graph.py",   # --selftest lives in the module itself
        mutations=(
            Mutation(
                "a dependency cycle stops being a filing error",
                "    cycle = _cycle_in(dependency)",
                "    cycle = None",
                "dependency cycle",
            ),
            Mutation(
                "a full page of gh results is accepted as the whole tracker (#211)",
                "    if len(payload) >= limit:",
                "    if False:",
                "truncation guard",
            ),
            Mutation(
                "declarations under the wrong fence tag go silent again",
                "        if lines and all(_STRICT.match(line) for line in lines):",
                "        if False:",
                "declarations under an untagged fence",
            ),
            # The near-miss half of the same carve-out. Widening `all` to `any` makes the check
            # fire on any fence that merely CONTAINS a declaration — the false positive that
            # would get it switched off. Proves the silence fixtures are load-bearing.
            Mutation(
                "the mistag check widens to any fence containing a declaration",
                "        if lines and all(_STRICT.match(line) for line in lines):",
                "        if lines and any(_STRICT.match(line) for line in lines):",
                "a fence mixing prose with a declaration is a sample",
            ),
            Mutation(
                "a declaration loose in prose stops being reported",
                "        if _STRICT.match(line):",
                "        if False:",
                "a declaration outside any fence",
            ),
            Mutation(
                "a typo'd key silently declares nothing",
                "            if key not in KEYS:",
                "            if False:",
                "typo'd key",
            ),
            Mutation(
                "an edge to an issue that does not exist stops being reported",
                "            if target not in graph.issues:",
                "            if False:",
                "edge to an issue not in the tracker",
            ),
            Mutation(
                "a self-referencing declaration is no longer named as such",
                "                if target == number:",
                "                if False:",
                "self reference",
            ),
            Mutation(
                "the critical-path tiebreak stops preferring the higher priority",
                "    return (lengths.get(number, 1), -PRIORITIES.index(priority) "
                "if priority else -len(PRIORITIES), -number)",
                "    return (lengths.get(number, 1), 0, -number)",
                "critical-path tiebreak",
            ),
            # The doctor runs this selftest as a gate, and a diagnostic that writes into the
            # working tree is a defect however tidy its cleanup looks. Reverting to a repo-local
            # fixture must be caught, not merely tolerated because the file is unlinked after.
            # Anchored on the ONE temp-dir helper every end-to-end fixture goes through, so a
            # second `main()` call cannot quietly acquire its own unguarded write path.
            Mutation(
                "the selftest writes its fixture into the repo again",
                '        with tempfile.TemporaryDirectory(prefix="issue-graph-selftest-") as workdir:',
                "        for workdir in [str(Path(__file__).resolve().parent)]:",
                "left files in scripts/",
            ),
            # The property that makes this a gate rather than a report: a graph known to be
            # broken must print NO queue, because a wrong ordering reads exactly like a right one.
            Mutation(
                "a queue is printed for a graph already known to be invalid",
                '    if graph.problems:\n        print(f"ISSUE GRAPH INVALID',
                '    if False:\n        print(f"ISSUE GRAPH INVALID',
                "cyclic",
            ),
            # --- the gate at the point of use (`--ready`) --------------------------------
            # Both directions, because each alone leaves the other half unguarded: a gate that
            # stops refusing is useless, and a gate that refuses the doctrine's preferred branch
            # shape gets switched off, after which nothing checks the order at all.
            Mutation(
                "--ready stops noticing a blocker outside the requested set",
                "        outside = [p for p in waiting if p not in inside]",
                "        outside = []",
                "an issue waiting on open work is not ready",
            ),
            Mutation(
                "--ready treats a group's own internal dependency as a blocker",
                "    inside = set(wanted)",
                "    inside = set()",
                "a group takes its own internal dependency with it",
            ),
            Mutation(
                "--ready clears an issue that is not in the tracker at all",
                "            problems.append(\n"
                '                f"#{number} is not in the tracker, so nothing is known about what'
                ' it waits on"\n            )',
                "            notes.append(\n"
                '                f"#{number} is not in the tracker, so nothing is known about what'
                ' it waits on"\n            )',
                "an issue absent from the tracker",
            ),
            Mutation(
                "--ready clears an issue that is already closed",
                "        if not issue.is_open:",
                "        if False:",
                "an already-closed issue is not work to start",
            ),
            # The honesty half. Without the caveat a READY on an issue that declared nothing
            # reads as "nothing blocks it" rather than "the tracker names no blocker" — the
            # unverified-negative class, and with the backfill incomplete it is the common case.
            Mutation(
                "a READY verdict stops saying the issue declared no edges",
                "        if number not in graph.declared:",
                "        if False:",
                "coverage caveat",
            ),
            # The other direction: a caveat on EVERY verdict is a caveat nobody reads, which
            # destroys the signal exactly as thoroughly as having none.
            Mutation(
                "the coverage caveat fires on issues that did declare edges",
                "        if number not in graph.declared:",
                "        if True:",
                "declares edges",
            ),
        ),
    ),
    Guard(
        name="maintainer_doctor",
        subject="scripts/maintainer_doctor.py",
        selftest="scripts/maintainer_doctor_selftest.py",
        needs=(".gitignore",),
        mutations=(
            Mutation(
                "an unignored corpora path stops being reported",
                "                if not verdict:",
                "                if False:",
                "slashed ignore",
            ),
            Mutation(
                "a SKIP is allowed to render as a PASS",
                'if not missing:\n            self.add(PASS, "design corpora present"',
                'if True:\n            self.add(PASS, "design corpora present"',
                "corpora",
            ),
            # Both directions of the corpora exemption. Too NARROW was the live defect: `coverage
            # artifact drift` was missing, so a machine without the optional licensed kits was told
            # to fix failures before doing maintenance work. Too BROAD silently shrinks the sweep.
            Mutation(
                "the artifact drift gate is exempted again, hiding a stripped committed page",
                'CORPORA_GATES = frozenset({"coverage matrix drift"})',
                'CORPORA_GATES = frozenset({"coverage matrix drift", "coverage artifact drift"})',
                "CORPORA_GATES is",
            ),
            Mutation(
                "the corpora exemption goes broad and skips a gate that needs nothing",
                'CORPORA_GATES = frozenset({"coverage matrix drift"})',
                'CORPORA_GATES = frozenset({"coverage matrix drift", "packaging determinism"})',
                "CORPORA_GATES is",
            ),
        ),
    ),
    # rails-flow #126. Two of these break a POSITIVE rule; two break a fixture whose job is to
    # stay SILENT, which is the direction that decides whether a mermaid linter survives contact
    # with real diagrams. Both directions are declared on purpose: a guard proven only to fire is
    # half-proven, and the half nobody checks is the half that gets the tool switched off.
    Guard(
        name="build_coverage_artifact",
        subject="scripts/build_coverage_artifact.py",
        selftest="scripts/build_coverage_artifact_selftest.py",
        # The builder imports build_coverage rather than parsing it, and the --check fixtures build a
        # real page, so the matrix source has to exist in the workdir. Without these the selftest dies
        # at import and EVERY mutation reports as "caught" — by a traceback, not by a fixture.
        deps=("scripts/build_coverage.py",),
        needs=("skills/fidara-design/references/coverage.md",),
        mutations=(
            Mutation(
                "the drift comparison stops comparing, so a stale artifact passes",
                '        if committed.replace("\\r\\n", "\\n") != doc.replace("\\r\\n", "\\n"):',
                '        if False:',
                "--check FAILS on a stale artifact",
            ),
            # The gate must read git, not the working copy. An `is_file()` + `read_text` version
            # passed a freshly built, never-added page — the exact "invisible deliverable" this
            # whole change exists to close, waved through by the gate built to close it.
            Mutation(
                "the gate goes back to trusting the working copy instead of the commit",
                "        committed = committed_blob(rel_out)",
                '        committed = args.out.read_text(encoding="utf-8") if args.out.is_file() else None',
                "a built-but-untracked page is DRIFT, not a pass",
            ),
            Mutation(
                "an absent artifact is reported as OK instead of drift",
                '            print(f"DRIFT: {rel_out} is not committed — the artifact is a deliverable other machines "\n                  f"must be able to see, not a local build.\\n{remedy}", file=sys.stderr)\n            return 1',
                '            print(f"DRIFT: {rel_out} is not committed — the artifact is a deliverable other machines "\n                  f"must be able to see, not a local build.\\n{remedy}", file=sys.stderr)\n            return 0',
                "--check FAILS when the artifact is nowhere at all",
            ),
            Mutation(
                "git state leaks back into the embedded stamp",
                '        "label": f"Coverage as of v{release}",',
                '        "label": f"Coverage as of v{release}",\n        "state": "dirty" if prov["dirty"] else "clean",',
                "the embedded stamp carries no git state whatsoever",
            ),
            Mutation(
                "the upstream totals go back to walking the licensed corpora",
                '    tw_count, fb_count = committed_totals.get("tw"), committed_totals.get("fb")',
                '    tw_count, fb_count = len(bc.discover_tw()), len(bc.discover_fb())',
                "collect() requires the licensed corpora",
            ),
        ),
    ),
    # #334. Both mutations are ones I ACTUALLY MADE while writing it: a manifest command that cannot
    # run, and an assertion that looked like it caught that but did not. The second is the reason
    # this guard exists -- the vacuous version passed a re-introduced bug, and only mutation found it.
    Guard(
        name="project_gates",
        subject="plugins/rails-flow/scripts/project_gates.py",
        selftest="plugins/rails-flow/scripts/project_gates.py",
        needs=("plugins/rails-flow/checks.json", "plugins/qa-flow/checks.json",
               "plugins/design-flow/checks.json"),
        mutations=(
            Mutation(
                "a not-applicable check is counted as a pass",
                '        return Result(check, NA, why_not)',
                '        return Result(check, PASS, why_not)',
                "an empty glob is n/a, not pass",
            ),
            Mutation(
                "a missing dependency skips instead of failing",
                '            return Result(check, FAIL, f"`{binary}` is not on PATH, so this check could not run")',
                '            return Result(check, NA, f"`{binary}` is not on PATH, so this check could not run")',
                "a missing dependency FAILS rather than skipping",
            ),
            Mutation(
                "the subcommand assertion stops discriminating (the vacuous version)",
                '    found = re.search(r"\\{([a-z,]+)\\}\\s*\\.\\.\\.", usage)',
                '    found = None',
                "a subparser group is detected",
            ),
        ),
    ),
    # #105. The first mutation is the whole point of the file: a 200 that renders an error is the
    # page every status check calls healthy, so the rule that catches it must be proven to fire.
    Guard(
        name="crawl_report",
        subject="plugins/qa-flow/scripts/crawl_report.py",
        selftest="plugins/qa-flow/scripts/crawl_report.py",
        mutations=(
            Mutation(
                "the 200-but-error rule stops firing",
                '    for pattern in ERROR_PAGE_MARKERS:',
                '    for pattern in []:',
                "200 rendering 'Internal Server Error' fires",
            ),
            Mutation(
                "an unreachable route is judged instead of named",
                '            result.skipped.append(f"{page.get(\'route\', \'?\')}: {page.get(\'skipped\')}")',
                '            pass',
                "a skipped route is named",
            ),
            Mutation(
                "console warnings become findings, so the rule fires on every real app",
                'CONSOLE_FATAL = ("error",)',
                'CONSOLE_FATAL = ("error", "warning")',
                "a console WARNING stays silent",
            ),
        ),
    ),
    # #105 criterion 3. The XOR is the whole rule: a page equally bad in BOTH themes belongs to
    # rendered_conformance, and reporting it here would double-count. Mutating it to `or` is the
    # difference between a parity check and a second contrast checker.
    Guard(
        name="theme_parity",
        subject="plugins/qa-flow/scripts/theme_parity.py",
        selftest="plugins/qa-flow/scripts/theme_parity.py",
        mutations=(
            Mutation(
                "parity becomes a second contrast checker, firing on both-themes-bad",
                '                if (l_ratio >= AA_NORMAL) != (d_ratio >= AA_NORMAL):',
                '                if (l_ratio >= AA_NORMAL) or not (d_ratio >= AA_NORMAL):',
                "bad in BOTH themes is not a parity finding",
            ),
            Mutation(
                "a frozen colour fires even when the surface never moved",
                '            if lc == dc and lbg != dbg:',
                '            if lc == dc:',
                "a frozen colour on an unmoved surface is silent",
            ),
            Mutation(
                "a translucent colour gets a fabricated ratio instead of being refused",
                '    if a[3] < 1.0 or b[3] < 1.0:',
                '    if False:',
                "a translucent foreground yields no ratio",
            ),
        ),
    ),
    # #105 criterion 4. Two of these break the rule by making it fire MORE, which is the
    # direction that gets a rule switched off: a false 'dead control' on a working button is
    # worse than no rule at all.
    Guard(
        name="interaction_report",
        subject="plugins/qa-flow/scripts/interaction_report.py",
        selftest="plugins/qa-flow/scripts/interaction_report.py",
        mutations=(
            Mutation(
                "an effect kind is dropped, so a working control reports dead",
                'EFFECT_KEYS = ("domChanged", "navigated", "requested", "focusMoved", "ariaChanged", "dialogOpened")',
                'EFFECT_KEYS = ("navigated", "requested", "focusMoved", "ariaChanged", "dialogOpened")',
                "domChanged counts as an effect",
            ),
            Mutation(
                "the constraint-validation exclusion goes, so every validated form reports dead (#357)",
                '    if control.get("constraintBlocked"):',
                '    if False:',
                "a submit blocked by constraint validation is not dead",
            ),
            Mutation(
                "the href exclusion goes, so every link on the site reports dead",
                '        return "link with href — navigation is its effect and is not observed here"',
                '        pass',
                "a link with href is not dead",
            ),
            Mutation(
                "an unexercised control is judged instead of named",
                '        if not control.get("exercised", False):',
                '        if False:',
                "an unexercised control is not judged clean",
            ),
        ),
    ),
    # #112. The first is the acceptance criterion in one line: a missing baseline must be neither a
    # pass nor a failure. Mutating it to a pass makes a brand-new screen 'visually correct' the day
    # it is written, which is exactly backwards -- nothing has ever been reviewed.
    Guard(
        name="visual_baseline",
        subject="plugins/qa-flow/scripts/visual_baseline.py",
        selftest="plugins/qa-flow/scripts/visual_baseline.py",
        needs=("plugins/qa-flow/scripts/crawl_collector.js",),
        mutations=(
            Mutation(
                "a missing baseline is treated as a pass",
                '        if not shot.get("baselinePresent"):',
                '        if False:',
                "a missing baseline is `new`",
            ),
            Mutation(
                "an undeterministic run is judged instead of refused",
                '    missing = [k for k in ("reducedMotion", "frozenClock", "seededData") if not d.get(k)]',
                '    missing = []',
                "motion not frozen",
            ),
            Mutation(
                "the first matching prefix wins instead of the longest",
                '        if route.startswith(pattern) and len(pattern) > best:',
                '        if route.startswith(pattern) :',
                "the longest matching prefix wins",
            ),
        ),
    ),
    Guard(
        name="check_guide",
        subject="plugins/rails-flow/scripts/check_guide.py",
        selftest="plugins/rails-flow/scripts/check_guide_selftest.py",
        mutations=(
            Mutation(
                "subgraph depth stops deciding whether a bare `end` is legal",
                "            if depth == 0:",
                "            if False:",
                "a bare lowercase `end` closing no subgraph",
            ),
            Mutation(
                "a correctly quoted label is read as unquoted (the false-positive direction)",
                "            if text.startswith('\"') and text.endswith('\"') and len(text) >= 2:",
                "            if False:",
                "a quoted label containing parentheses",
            ),
            Mutation(
                "an unclosed managed section stops being unusable",
                "    if open_section is not None:\n        raise Unusable(",
                "    if False:\n        raise Unusable(",
                "an unclosed section would swallow everything after it",
            ),
            Mutation(
                "the ASCII-art rule loses its arrow carve-out and eats directory trees",
                "                if len(drawn) >= 3 and any(ARROW_RE.search(b) for b in diagram.body):",
                "                if len(drawn) >= 3:",
                "a directory tree is box-drawing WITHOUT arrows and must pass",
            ),
            Mutation(
                "the diagram-type allowlist stops rejecting unverified types",
                "                if declared not in KNOWN_DIAGRAM_TYPES:",
                "                if False:",
                "a diagram type with no evidence GitHub renders it",
            ),
            Mutation(
                "the image rule widens from diagrams to every picture, eating screenshots",
                "                if any(w in haystack for w in DIAGRAM_WORDS):",
                "                if True:",
                "a screenshot is legitimate",
            ),
        ),
    ),
    # design-flow #107. A conformance linter's whole risk is FALSE POSITIVES — one that fires on
    # correct input is switched off, and then catches nothing — so roughly half of these break a
    # CARVE-OUT rather than a rule, and are expected to be caught by a fixture whose job is to stay
    # silent. Two of them exist because running the collector against a real page found the defect
    # first: corners counted as elements, and an inline-link exemption wide enough to swallow every
    # native <button>.
    Guard(
        name="llm_tell_detector",
        subject="plugins/design-flow/scripts/llm_tell_detector.py",
        selftest="plugins/design-flow/scripts/llm_tell_detector.py",
        # It IMPORTS `rendered_conformance` for the shared palette-step definition (#157 criterion
        # 7), so without this every mutant dies at import and each mutation reads as "caught" by a
        # traceback rather than by the fixture named below.
        needs=("plugins/design-flow/scripts/rendered_conformance.py",
               "plugins/design-flow/scripts/conformance_collector.js"),
        mutations=(
            # Three of these four are bugs I actually shipped into the first draft, kept as
            # mutations because a bug that happened once is the best evidence a fixture is load-
            # bearing rather than decorative.
            Mutation(
                "the shared palette step loses its hyphen (`gray500`, matching nothing)",
                'STEP_ALTERNATION = _STEP[:-len(r"\\Z")]',
                'STEP_ALTERNATION = _STEP[1:-len(r"\\Z")]',
                "stock palette",
            ),
            Mutation(
                "the ease lookahead returns, excusing `ease-in-out` (it starts with `ease-in`)",
                're.compile(r"\\bease-(?:in-out|linear|initial)\\b")',
                're.compile(r"\\bease-(?!(?:out|in)\\b)(?:in-out|linear|initial)\\b")',
                "ease-in-out",
            ),
            Mutation(
                "the duration rule flags the documented FIX, `duration-(--duration-fast)`",
                'r"(?<![-\\w])duration-(?:"',
                'r"\\bduration-(?:"',
                "custom-property duration",
            ),
            Mutation(
                "the token-definition carve-out widens to every hex",
                'return before.endswith("--") or bool(TOKEN_DEFINITION.search(before))',
                "return True",
                "a plain declaration is NOT a token definition",
            ),
            Mutation(
                "a disable stops suppressing, so the escape hatch is decorative",
                "        if rule.name in allowed:\n            report.suppressed += 1\n            continue",
                "        if False:\n            report.suppressed += 1\n            continue",
                "a disable with a reason suppresses",
            ),
        ),
    ),
    Guard(
        name="rendered_conformance",
        subject="plugins/design-flow/scripts/rendered_conformance.py",
        selftest="plugins/design-flow/scripts/rendered_conformance.py",
        # The selftest `node --check`s the shipped collector, which lives beside the subject.
        # Without this the mutant's collector is missing, every run fails on that fixture, and
        # every mutation reads as caught by the wrong one.
        needs=("plugins/design-flow/scripts/conformance_collector.js",),
        mutations=(
            # ---- literal-colour ----
            Mutation(
                "the role-token basis stops silencing anything, so nothing is a literal colour",
                "            if key in basis:\n                continue",
                "            if True:\n                continue",
                "a stock-palette colour is reported",
            ),
            Mutation(
                "translucent colours are judged — the `/90` flood the carve-out prevents",
                "            if alpha != 1.0:\n                translucent += 1\n                continue",
                "            if False:\n                translucent += 1\n                continue",
                "a translucent colour whose base is not in the basis is still not judged",
            ),
            Mutation(
                "an unparsed colour form becomes a finding instead of a counted skip",
                "            if canon is None:\n                unparsed += 1\n                continue",
                '            if canon is None:\n                unparsed += 1\n                canon = ("unknown-form", 1.0)',
                "an unrecognised colour form is counted, not reported",
            ),
            Mutation(
                "the empty-basis guard is removed, so every colour on the page is reported",
                "    if not basis:\n        report.no_input = True",
                "    if False:\n        report.no_input = True",
                "an empty role basis refuses to run",
            ),
            Mutation(
                "a transparent value is counted as an alpha-modified colour",
                '            if key == "transparent":\n                continue',
                "            if False:\n                continue",
                "a transparent background is neither judged nor counted",
            ),
            Mutation(
                "rgba(r, g, b, 1) no longer canonicalises to rgb(r, g, b)",
                '    base = "rgb" if name == "rgba" else ("hsl" if name == "hsla" else name)',
                "    base = name",
                "rgba with alpha 1 matches the rgb basis",
            ),
            # ---- numbered-step-binding ----
            Mutation(
                "the colour-utility prefix gate is removed, so any numbered utility is a binding",
                "            if prefix not in COLOUR_UTILITIES:\n                continue",
                "            if False:\n                continue",
                "correct utility `translate-x-100` is not a numbered-step binding",
            ),
            Mutation(
                "the palette-step requirement is removed, so `text-step--1` is a binding",
                "            if not PALETTE_STEP.search(stem):\n                continue",
                "            if False:\n                continue",
                "a conformant snapshot is clean",
            ),
            Mutation(
                "variant prefixes stop being stripped, so `dark:hover:` hides the binding",
                "            base = base_utility(cls)",
                "            base = cls",
                "a variant-prefixed numbered step is reported",
            ),
            # ---- focus-ring-missing ----
            Mutation(
                "a shadow stops counting as an indicator, so the doctrine's ring idiom is flagged",
                "        if has_outline or has_shadow or has_repaint:",
                "        if has_outline or has_repaint:",
                "the doctrine's ring idiom is not reported",
            ),
            Mutation(
                "an invisible outline counts as an indicator (v4's outline-none is `none`)",
                '        style_visible = declarations.get("outline-style", "") not in INVISIBLE_OUTLINE_STYLES',
                '        style_visible = declarations.get("outline-style", "") not in ("__never__",)',
                "outline-none alone is not an indicator",
            ),
            Mutation(
                "every interactive element is treated as focus-styled",
                "        if has_outline or has_shadow or has_repaint:\n            if has_shadow and not has_outline:",
                "        if True:\n            if has_shadow and not has_outline:",
                "an unstyled focus state is reported",
            ),
            Mutation(
                "an element whose focus rules could not be read is silently passed",
                "    if unmeasured:\n        report.skip(",
                "    if False:\n        report.skip(",
                "an unmeasured focus state is skipped, not passed",
            ),
            Mutation(
                "disabled controls are required to have a focus ring",
                '                 if is_interactive(e) and is_visible(e) and not e.get("disabled")]',
                "                 if is_interactive(e) and is_visible(e)]",
                "a disabled control needs no focus ring",
            ),
            Mutation(
                "the forced-colors exposure of a shadow-only ring goes unreported",
                "    if shadow_only:",
                "    if False:",
                "a shadow-only ring is a counted fact, not a finding",
            ),
            # ---- tap-target-small ----
            Mutation(
                "the 44px touch floor stops being checked",
                "        if height >= TOUCH_MIN_PX:\n            continue",
                "        if True:\n            continue",
                "a short tap target is reported",
            ),
            Mutation(
                "a desktop snapshot is judged against the touch floor",
                "    if width > MOBILE_MAX_WIDTH:",
                "    if False:",
                "a desktop viewport skips the touch rule",
            ),
            Mutation(
                "the inline exemption widens to any inline-* display, swallowing every button",
                '    if str(element.get("display", "")).strip().lower() != "inline":',
                '    if not str(element.get("display", "")).strip().lower().startswith("inline"):',
                "a link styled as a button is NOT exempt from the touch floor",
            ),
            Mutation(
                "the inline exemption drops its surrounding-text requirement",
                "    return around > own + 1",
                "    return True",
                "an inline link with no surrounding text is still a tap target",
            ),
            # ---- icon-only-unnamed ----
            Mutation(
                "a named control is reported as unnamed",
                "        if name:\n            continue",
                "        if False:\n            continue",
                "an sr-only name silences the rule",
            ),
            Mutation(
                "the accessible-name rule stops reporting",
                '        name = str(element.get("name") or "").strip()',
                '        name = "always named"',
                "an unnamed control is reported",
            ),
            Mutation(
                "an aria-hidden subtree stops being excluded, so it is judged for a11y",
                '    return width > 0 and height > 0 and not element.get("ariaHidden")',
                "    return width > 0 and height > 0",
                "an aria-hidden control is not judged",
            ),
            Mutation(
                "a disabled control is excused from having a name",
                '        name = str(element.get("name") or "").strip()\n        if name:',
                '        name = str(element.get("name") or "").strip()\n        if name or element.get("disabled"):',
                "a disabled control still needs a name",
            ),
            # ---- aria-controls-no-expanded ----
            Mutation(
                "the disclosure rule stops reporting",
                '        if aria.get("expanded") is not None:\n            continue',
                "        if True:\n            continue",
                "a disclosure trigger without aria-expanded is reported",
            ),
            Mutation(
                "the aria-pressed/aria-selected carve-out is removed, flagging a toggle button",
                '        if aria.get("selected") is not None or aria.get("pressed") is not None:\n            continue',
                "        if False:\n            continue",
                "a toggle button using aria-pressed is exempt",
            ),
            Mutation(
                "the role carve-out is removed, flagging a role=option",
                '        if role in ("tab", "tablist", "radio", "option"):\n            continue',
                "        if False:\n            continue",
                "a role=option is exempt by role",
            ),
            Mutation(
                "the role carve-out widens to combobox, hiding a required-state defect",
                '        if role in ("tab", "tablist", "radio", "option"):',
                '        if role in ("tab", "tablist", "radio", "option", "combobox"):',
                "a combobox is not exempt",
            ),
            # ---- horizontal-overflow ----
            Mutation(
                "horizontal overflow stops being reported",
                "    if scroll - client <= 1:\n        return",
                "    if True:\n        return",
                "horizontal overflow is reported",
            ),
            Mutation(
                "the 1px sub-pixel slack is removed, so pages that do not scroll are reported",
                "    if scroll - client <= 1:\n        return\n    report.add(Finding(",
                "    if scroll - client <= 0:\n        return\n    report.add(Finding(",
                "sub-pixel width is not overflow",
            ),
            # ---- off-scale-type ----
            Mutation(
                "the type-scale check stops reporting",
                "        if size is None or size in basis:\n            continue",
                "        if size is None or True:\n            continue",
                "an off-scale font size is reported",
            ),
            Mutation(
                "the UA-scaled carve-out is removed, flagging an untouched <sup>",
                "        if tag in SKIP_TAGS or tag in UA_SCALED_TAGS:",
                "        if tag in SKIP_TAGS:",
                "a UA-scaled tag is exempt",
            ),
            Mutation(
                "a missing type basis reads as a pass instead of a named skip",
                '    if not basis:\n        report.skip("off-scale-type",',
                '    if False:\n        report.skip("off-scale-type",',
                "no type basis skips the rule by name",
            ),
            # ---- radius-off-scale ----
            Mutation(
                "the radius-scale check stops reporting",
                "            if token is None:\n                groups.setdefault(value, []).append(_ref(element))",
                "            if False:\n                groups.setdefault(value, []).append(_ref(element))",
                "an arbitrary radius is reported",
            ),
            Mutation(
                "the pill carve-out is removed, flagging every rounded-full badge",
                "            if float(value) >= FULL_RADIUS_MIN_PX:",
                "            if False:",
                "a pill radius is always legitimate",
            ),
            Mutation(
                "a square corner is judged, flagging every unrounded element on the page",
                "            if float(value) == 0.0:\n                continue",
                "            if False:\n                continue",
                "a square corner is not off-scale",
            ),
            Mutation(
                "corners are counted as elements again, multiplying every radius number by four",
                "            if value is None or value in seen:",
                "            if value is None:",
                "four equal corners are one radius decision",
            ),
            # ---- trends ----
            Mutation(
                "the dark: threshold is ignored, so any occurrence is a finding",
                '    if total <= threshold:\n        return\n    report.add(Finding(\n        "dark-variant-sprawl", "trend",',
                '    if False:\n        return\n    report.add(Finding(\n        "dark-variant-sprawl", "trend",',
                "dark: sprawl under the threshold is silent but counted",
            ),
            Mutation(
                "dark: sprawl over the threshold stops being reported",
                '    report.fact(f"`dark:` occurrences: {total} (threshold {threshold})")\n    if total <= threshold:',
                '    report.fact(f"`dark:` occurrences: {total} (threshold {threshold})")\n    if True:',
                "dark: sprawl over the threshold is a trend finding",
            ),
            Mutation(
                "the breakpoint count stops being reported",
                '    report.fact(f"breakpoint occurrences: {total} (threshold {threshold})")\n    if total <= threshold:',
                '    report.fact(f"breakpoint occurrences: {total} (threshold {threshold})")\n    if True:',
                "breakpoint sprawl over the threshold is a trend finding",
            ),
            Mutation(
                "a bare utility counts as a breakpoint occurrence",
                "            if any(p in BREAKPOINT_VARIANTS for p in variant_prefixes(cls)):",
                "            if True:",
                "an unprefixed utility is not counted as a breakpoint occurrence",
            ),
            # ---- snapshot guards: judging nothing must never read as conformant ----
            Mutation(
                "a snapshot with zero elements reports clean",
                "    if not isinstance(elements, list) or not elements:",
                "    if False:",
                "an empty element list is not a pass",
            ),
            Mutation(
                "a snapshot from a different collector version is analysed anyway",
                '    if snapshot.get("schema") != SCHEMA:',
                "    if False:",
                "a foreign schema is refused",
            ),
            Mutation(
                "an unjudgeable snapshot exits 1 (drift) instead of 2 (environment)",
                "    if environment:",
                "    if False:",
                "a snapshot with nothing to judge exits 2, not 1",
            ),
            Mutation(
                "an unreadable snapshot is reported as design drift",
                '            print(f"rendered_conformance: {exc}", file=sys.stderr)\n            return 2',
                '            print(f"rendered_conformance: {exc}", file=sys.stderr)\n            return 1',
                "unparseable JSON exits 2, not 1",
            ),
            Mutation(
                "the outline shorthand stops counting, flagging the fix this rule recommends",
                '        if shorthand:\n            style_visible = "none" not in shorthand',
                '        if False:\n            style_visible = "none" not in shorthand',
                "the outline shorthand is an indicator",
            ),
            Mutation(
                "an unparseable outline width is read as zero, hiding a visible outline",
                '        width_is_zero = width_token is not None and canon_px(width_token) == "0.0"',
                '        width_is_zero = canon_px(width_token or "") != "2.0"',
                "an unparseable outline width does not veto a visible style",
            ),
            Mutation(
                "an explicit non-interactive role stops beating the tag",
                "    if role:\n        # An explicit non-interactive role wins over the tag",
                "    if False:\n        # An explicit non-interactive role wins over the tag",
                "an explicit non-interactive role beats the tag",
            ),
            Mutation(
                "unreadable stylesheets are judged over in silence",
                "    if unreadable:\n        report.notice(",
                "    if False:\n        report.notice(",
                "unreadable stylesheets are reported as a notice",
            ),
            Mutation(
                "a non-painting tag is judged for colour",
                "        if str(element.get(\"tag\", \"\")).lower() in SKIP_TAGS:\n            continue",
                "        if False:\n            continue",
                "a non-painting tag is not judged for colour",
            ),
            Mutation(
                "hex colours stop being canonicalised, so a form we claim to handle is skipped",
                "    hexed = _HEX.match(value)",
                "    hexed = None",
                "a hex colour is canonicalised",
            ),
            Mutation(
                "the printed contract loses a field the snapshot carries (it went stale once)",
                '    "display": "inline-block",              // MEASUREMENTS',
                '    "displai": "inline-block",              // MEASUREMENTS',
                "every field the analyser reads is in the printed contract",
            ),
            Mutation(
                "a rule reads a field no real collector run emits, so it judges None forever",
                '    if str(element.get("display", "")).strip().lower() != "inline":',
                '    if str(element.get("cssDisplay", "")).strip().lower() != "inline":',
                "every field the analyser reads is emitted by the collector",
            ),
            Mutation(
                "the accessor scan stops matching, so both parity checks compare nothing",
                "        read_fields = sorted(set(accessor.findall(own_source)))",
                "        read_fields = sorted(set())",
                "the analyser reads a plausible number of snapshot fields",
            ),
            # ---- the collector's own syntax check ----
            Mutation(
                "the collector syntax check cannot fail",
                "    if result.returncode != 0:",
                "    if False:",
                "a collector that does not parse exits 1",
            ),
            Mutation(
                "an absent node fails the sweep instead of skipping loudly",
                "    if shutil.which(node_bin) is None:",
                "    if False:",
                # No expectation: with the guard gone, subprocess raises FileNotFoundError before
                # the fixture can print its label, so any failure is the honest bar here.
                "",
            ),
        ),
    ),
    # rails-flow #127 + the rails-flow half of #128. FOUR of these seven break a fixture whose job
    # is to stay SILENT, because a work order is ordinary prose about files and tests: `<...>` is a
    # placeholder AND an HTML tag, "above" is the conversation AND the table three lines up, `TODO`
    # is an unresolved decision AND part of `todo.rb`. A rule that flags the second of each pair
    # gets the tool switched off, so the carve-outs are what need guarding.
    Guard(
        name="check_handoff",
        subject="plugins/rails-flow/scripts/check_handoff.py",
        selftest="plugins/rails-flow/scripts/check_handoff_selftest.py",
        # The criteria parser: the traceability rule imports it to resolve the cited AC ids.
        deps=("plugins/rails-flow/scripts/check_criteria.py",),
        # Read, not imported. The selftest's last checks run the REAL tier table against the REAL
        # agents and FAIL rather than skip when absent -- so the mutant needs them, or every
        # mutation reports as "caught by the wrong fixture" and the real signal is buried.
        needs=(
            "plugins/rails-flow/reference/model-tiers.md",
            "plugins/rails-flow/commands/handoff.md",
            "plugins/rails-flow/agents/claude-skills-reporter.md",
            "plugins/rails-flow/agents/code-reviewer.md",
            "plugins/rails-flow/agents/design-auditor.md",
            "plugins/rails-flow/agents/doc-updater.md",
            "plugins/rails-flow/agents/migration-writer.md",
            "plugins/rails-flow/agents/pr-reviewer.md",
            "plugins/rails-flow/agents/rails-developer.md",
            "plugins/rails-flow/agents/security-auditor.md",
            "plugins/rails-flow/agents/skill-curator.md",
            "plugins/rails-flow/agents/test-runner.md",
        ),
        mutations=(
            Mutation(
                "`retry` back in the attempt-cap vocabulary (the real bug a fixture found)",
                '("attempt cap", ("attempt", "retries", "retry limit", "retry cap", "tries")),',
                '("attempt cap", ("attempt", "retry", "retries", "tries")),',
                "no numeric attempt cap",
            ),
            Mutation(
                "the stale-row rule stops noticing a table row no agent defines",
                "        if row.agent not in agents:",
                "        if False:",
                "a stale row naming an agent",
            ),
            Mutation(
                "a tier's model requirement stops being enforced",
                "        elif row.model != want:",
                "        elif False:",
                "a judgement agent pinned to a model",
            ),
            Mutation(
                "heading aliases match inside words again (the false-positive direction)",
                'return any(re.search(rf"\\b{re.escape(a)}\\b", low) for a in aliases)',
                "return any(a in low for a in aliases)",
                "is not the in-scope list",
            ),
            Mutation(
                "fenced blocks stop being skipped, so a quoted view snippet is a placeholder",
                "            if offset < len(section.fenced) and section.fenced[offset]:",
                "            if False:",
                "a fenced snippet holding a tag is code",
            ),
            Mutation(
                "inline code stops being stripped, so a backticked tag is a placeholder",
                "            line = _strip_code(raw)",
                "            line = raw",
                "a backticked HTML tag is code",
            ),
            Mutation(
                "the unresolved-token rule goes case-insensitive and eats todo.rb",
                'UNRESOLVED_RE = re.compile(r"\\b(TBD|TODO|FIXME|\\?\\?\\?)\\b")',
                'UNRESOLVED_RE = re.compile(r"\\b(TBD|TODO|FIXME|\\?\\?\\?)\\b", re.I)',
                "the word todo in prose",
            ),
        ),
    ),
    # #128, the pipeline half. Two of these break a fixture whose job is to stay SILENT -- a
    # breaker that refuses a run which was progressing does not get tuned, it gets bypassed, and
    # then nothing is bounded at all. The last one breaks neither: it drifts the CODE away from the
    # shipped DOCTRINE, which only the real-file checks can see.
    Guard(
        name="breaker",
        subject="plugins/pipeline/scripts/breaker.py",
        selftest="plugins/pipeline/scripts/breaker_selftest.py",
        # Read, not imported. The selftest's last checks run against the SHIPPED doctrine and the
        # SHIPPED surfaces, and FAIL rather than skip when absent -- so the mutant needs them, or
        # every mutation reports as "caught by the wrong fixture" and the real signal is buried.
        needs=(
            "plugins/pipeline/reference/stop-conditions.md",
            "plugins/pipeline/commands/ack.md",
            "plugins/pipeline/commands/deploy-cloud.md",
            "plugins/pipeline/commands/install-hooks.md",
            "plugins/pipeline/commands/pipeline.md",
            "plugins/pipeline/commands/release.md",
            "plugins/pipeline/commands/setup-cloud.md",
            "plugins/pipeline/commands/setup-pipeline.md",
            "plugins/pipeline/commands/status.md",
            "plugins/pipeline/agents/kamal-configurator.md",
            "plugins/pipeline/agents/pipeline-coordinator.md",
        ),
        mutations=(
            Mutation(
                "the attempt cap stops firing",
                "    if len(failures) >= cap:",
                "    if False:",
                "three failures against a cap of three",
            ),
            Mutation(
                "the no-progress detector stops firing",
                "        if len(set(recent)) == 1:",
                "        if False:",
                "two identical failure signatures",
            ),
            Mutation(
                "the signature normaliser strips digits, so a converging run reads as stuck",
                '    return _WS.sub(" ", text).strip().lower()',
                '    return _WS.sub(" ", re.sub(r"\\d+", "", text)).strip().lower()',
                "a changing failure count is progress, not a stall",
            ),
            Mutation(
                "the ordering rule stops firing, and gate-skipping returns",
                "        if not _passed(records, earlier):",
                "        if False:",
                "release reached before certify passed",
            ),
            Mutation(
                "the budget breaker stops firing",
                "    if spent >= budget:",
                "    if False:",
                "the wall-clock budget is spent",
            ),
            Mutation(
                "a passed stage may be re-attempted",
                '    if _passed(records, stage):\n        return "already-passed", (',
                '    if False:\n        return "already-passed", (',
                "a passed stage is not re-attempted",
            ),
            Mutation(
                "an override outside its bounds is accepted, so a cap becomes unbounded",
                "        if not low <= value <= high:",
                "        if False:",
                "an attempt cap of 99",
            ),
            Mutation(
                "a failure is recorded with no signature, making no-progress unfalsifiable",
                '    if args.outcome == "fail" and not (args.signature or "").strip():',
                "    if False:",
                "a fail recorded with no signature",
            ),
            Mutation(
                "`report` exits 0 on a partial run -- partial presented as complete",
                '    if state == "complete":\n        return 0',
                "    if True:\n        return 0",
                "reporting an unfinished run",
            ),
            Mutation(
                "exceeding the cap stops spoiling the verdict, so the breaker becomes advisory",
                '        if len(failures) > limits["attempts"]:',
                "        if False:",
                "a cap exceeded then passed is still stopped",
            ),
            Mutation(
                "a second `start` silently resets every attempt counter",
                '            if state != "complete":',
                "            if False:",
                "restarting over an unfinished run",
            ),
            Mutation(
                "an undiagnosed stop stops being named in the report",
                '        if not str(stop.get("diagnosis", "")).strip():',
                "        if False:",
                "a stop with no diagnosis is named in the report",
            ),
            Mutation(
                "a missing `started` disables the budget rule instead of being unusable",
                '        raise Unusable(\n            "the `run` record carries no `started` '
                "timestamp, so the budget cannot be measured. \"\n            \"That is unusable "
                'input, not an unlimited budget."\n        )',
                "        return float(0)",
                "a run record with no started timestamp",
            ),
            Mutation(
                "the bound widens in the code while the doctrine still states the old one",
                '    "attempts": (1, 10),',
                '    "attempts": (1, 99),',
                "allowed range 1..99",
            ),
        ),
    ),
)


def apply_mutation(guard: Guard, mutation: Mutation, workdir: Path) -> Path:
    """Copy subject + selftest + deps into `workdir`, with the mutation applied.

    Raises if the anchor is absent or non-unique: a mutation that did not apply produces a mutant
    identical to the original, which passes and reads exactly like a caught mutation.
    """
    subject = REPO / guard.subject
    source = subject.read_text(encoding="utf-8")
    hits = source.count(mutation.old)
    if hits != 1:
        raise RuntimeError(
            f"{guard.name} / {mutation.name}: anchor matches {hits} time(s), need exactly 1 — "
            "the mutation list has drifted from the code it mutates"
        )
    mutated = source.replace(mutation.old, mutation.new)
    if mutated == source:
        raise RuntimeError(f"{guard.name} / {mutation.name}: replacement changed nothing")

    # Mirror the repo layout rather than flattening, so `parents[1]`-relative reads still work.
    for relative in {guard.subject, guard.selftest, *guard.deps}:
        target = workdir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((REPO / relative).read_text(encoding="utf-8"), encoding="utf-8")
    for relative in guard.needs:
        target = workdir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    (workdir / guard.subject).write_text(mutated, encoding="utf-8")
    return workdir / guard.selftest


def run_guard(guard: Guard) -> list[str]:
    """Failures for one guard. Empty list = every mutation was caught by the right fixture."""
    problems: list[str] = []
    for mutation in guard.mutations:
        workdir = Path(tempfile.mkdtemp(prefix=f"mutcheck-{guard.name}-"))
        try:
            entry = apply_mutation(guard, mutation, workdir)
            argv = [sys.executable, str(entry)]
            if guard.selftest == guard.subject:
                argv.append("--selftest")   # the selftest is a flag on the module itself
            result = subprocess.run(argv, cwd=workdir, capture_output=True, text=True, timeout=300)
            output = result.stdout + result.stderr

            if result.returncode == 0:
                problems.append(
                    f"{guard.name}: SURVIVED — {mutation.name}. The selftest passed with this "
                    "broken, so nothing guards it."
                )
                continue
            if mutation.expects and mutation.expects.lower() not in output.lower():
                problems.append(
                    f"{guard.name}: caught {mutation.name!r} but not by the expected fixture "
                    f"(no mention of {mutation.expects!r}) — a coincidental catch would hide that "
                    "fixture going quiet"
                )
        except subprocess.TimeoutExpired:
            problems.append(f"{guard.name}: {mutation.name} timed out")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prove each selftest fails when the thing it guards breaks."
    )
    parser.add_argument("--guard", help="run one guard by name")
    parser.add_argument("--selftest", action="store_true",
                        help="prove this checker itself detects a survivor and a stale anchor")
    args = parser.parse_args(argv)

    if args.selftest:
        import mutation_check_selftest as st

        return st.run()

    guards = [g for g in GUARDS if not args.guard or g.name == args.guard]
    if args.guard and not guards:
        print(f"no guard named {args.guard!r}; known: {[g.name for g in GUARDS]}", file=sys.stderr)
        return 2

    problems: list[str] = []
    total = 0
    for guard in guards:
        total += len(guard.mutations)
        found = run_guard(guard)
        status = "ok" if not found else "FAIL"
        print(f"  [{status:4}] {guard.name}: {len(guard.mutations)} mutation(s)")
        problems.extend(found)

    if problems:
        print(f"\nMUTATION CHECK FAILED — {len(problems)} of {total}:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"\nmutation check: {total} mutation(s) across {len(guards)} guard(s), all caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())
