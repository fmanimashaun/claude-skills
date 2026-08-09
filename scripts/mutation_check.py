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
                # #483. The sibling stops counting as named, so the rule fires on every paragraph
                # that describes the conditional correctly — including the fix for the very defect
                # it exists to catch, which is what it did when first written against `role="…"`
                # literals instead of words.
                "the sibling branch never counts as named, so correct paragraphs fail",
                '            named = {w for w in re.findall(r"[a-z]+", paragraph)}',
                "            named = set()",
                "...silent when the paragraph names the sibling",
            ),
            Mutation(
                # The other direction: nothing is ever missing, so a flattened role sails through
                # and a scaffolder ships errors announced politely.
                "no branch is ever considered missing, so flattening is never caught",
                "                missing = sorted(siblings.get(value, set()) - named)",
                "                missing = []",
                "one branch stated as a literal",
            ),
            Mutation(
                # No section is ever missing, so the CHANGELOG can lose eight of its nine component
                # sections and 7,950 lines and the sweep still reports green — which is exactly what
                # happened, in CI, on the commit this gate was written for.
                "no plugin's CHANGELOG section is ever missing, so a truncation passes",
                "        if not any(name in h for h in headings):",
                "        if False:",
                "a plugin whose CHANGELOG section was deleted",
            ),
            Mutation(
                # Match any heading level and the leftover `### <plugin> 1.0.0` release blocks count
                # as sections. The real truncation left those behind, so this mutation reproduces
                # the damage in the shape that would have been waved through.
                "any heading counts as a section, so leftover release blocks mask the loss",
                '    headings = [l for l in read(doc).splitlines() if l.startswith("## ")]',
                '    headings = [l for l in read(doc).splitlines() if l.startswith("#")]',
                "...a release block is not a section",
            ),
            Mutation(
                # Nothing is ever undocumented, so a skill can be authored, shipped and named
                # nowhere -- which is what happened to derived-artifacts on the night this landed.
                "no skill is ever missing from CLAUDE.md, so all of them may go unnamed",
                "            if d.name not in body:",
                "            if False:",
                "a shipped skill named nowhere in CLAUDE.md",
            ),
            Mutation(
                # The `.claude/skills` half stops being scanned only if the walk itself narrows;
                # requiring a SKILL.md is what separates a skill from a stray folder, and dropping
                # that check makes every directory a subject -- caught by the negative fixture.
                "any directory counts as a skill, so stray folders demand documentation",
                '        for d in sorted(p for p in base.iterdir() if (p / "SKILL.md").is_file()):',
                "        for d in sorted(p for p in base.iterdir() if p.is_dir()):",
                "...silent on a directory that is not a skill",
            ),
            Mutation(
                # The fence strip goes, so a fenced block DOCUMENTING `@AGENTS.md` reads as a real
                # import. That is the gate certifying the exact repo state it exists to refuse: one
                # that has written the rule down and wired nothing.
                "a fenced example counts as an import, so documenting the rule satisfies it",
                "            fenced = not fenced",
                "            fenced = False",
                "...a fenced example is not an import",
            ),
            Mutation(
                "the unimported half goes, so an AGENTS.md nothing reads passes",
                "    if neutral.is_file() and import_line is None:",
                "    if False:",
                "an authored AGENTS.md that CLAUDE.md never imports",
            ),
            Mutation(
                # The worse half: every fresh clone opens by resolving a file that is not there.
                "the dangling half goes, so an import with no target passes",
                "    elif import_line is not None and not neutral.is_file():",
                "    elif False:",
                "...a dangling import is the same defect reversed",
            ),
            Mutation(
                # #531: a true claim with nothing behind it — the discount whose condition
                # the skill gave no way to satisfy.
                "the MFA-guidance test always passes, so the discount may dangle again",
                '    teaches = re.search(r"\\bTOTP\\b|\\bWebAuthn\\b|\\bpasskey\\b|## 2b\\.", body, re.I)',
                "    teaches = True",
                "the multi-factor discount with no MFA guidance",
            ),
            Mutation(
                "the rule stops requiring an offer, demanding MFA doctrine of every auth file",
                '    if not offers:',
                "    if False:",
                "a file not offering the discount is silent",
            ),
            Mutation(
                # Third stale doc-number about our own files; second time the missed one was design-flow.
                "the total comparison goes, so a wrong hook count passes",
                '    if m.group(1) != WORDS.get(total, str(total)):',
                "    if False:",
                "a wrong total is reported",
            ),
            Mutation(
                "the advisory figure stops subtracting the gates, so it drifts freely",
                '    gates = sum(1 for s in scripts if s.name in {"guard-bash.sh", "release-gate.sh"})',
                "    gates = 0",
                "advisory is total minus the named gates",
            ),
            Mutation(
                "a missing sentence stops failing loud, so the rule silently checks nothing",
                '    if not m:',
                "    if False:",
                "a reworded sentence is reported, not ignored",
            ),
            Mutation(
                # A manual error made twice in three releases; a join should catch it, not a human.
                "the duplicate count relaxes, so two Unreleased headings pass",
                '        if len(lines) > 1:',
                "        if len(lines) > 2:",
                "two Unreleased headings in one section",
            ),
            Mutation(
                "the heading test becomes a substring match, so prose counts as a heading",
                '        elif line.strip() == "### Unreleased" and section:',
                '        elif "### Unreleased" in line and section:',
                "prose mentioning the string is not counted",
            ),
            Mutation(
                # #513. Nothing can declare this pairing in a manifest, so the check has to
                # live in the command or the doctrine is simply absent at runtime.
                "the stop-instruction check goes, so a command may read an absent skill",
                '        if STOP.search(body):',
                "        if True:",
                "a command reading a foreign skill with no stop instruction",
            ),
            Mutation(
                "the skill-reference filter goes, demanding a precondition of every command",
                '        if FOREIGN_SKILL not in body:',
                "        if False:",
                "a command not reading it is silent",
            ),
            Mutation(
                # #484. Two numbers for one rule in one file is how a relaxed example
                # outlives a table nobody re-read.
                "the floor comparison inverts, so only a MATCHING example is reported",
                '        for n in enforced if int(n) != floor',
                '        for n in enforced if int(n) == floor',
                "a worked example below the stated floor",
            ),
            Mutation(
                "a missing stated floor stops being reported, so nothing reconciles the example",
                '    if not stated:',
                '    if False:',
                "an example with no stated floor is reported",
            ),
            Mutation(
                # #483. The controller shipped orphaned in every scaffolded app, and the CRUD
                # pattern's three `turbo_stream.prepend("toasts", ...)` call sites had no target.
                "the component check goes, so a controller may ship with no component",
                '        if re.search(rf"\\b{re.escape(component)}\\b", body):',
                "        if True:",
                "a controller whose component is not scaffolded",
            ),
            Mutation(
                "pairing stops being discovered, so every controller demands a component",
                '            prescribed |= {n for n in re.findall(r"`([a-z][a-z-]*)`", line) if n in implemented}',
                '            prescribed |= {n for n in re.findall(r"`([a-z][a-z-]*)`", line)}',
                "an unpaired controller needs no component",
            ),
            Mutation(
                # #489. The file is what /maintainer-setup-intake provisions FROM, so a missing
                # entry means the label is never created on a fresh clone.
                "the shipped-vs-declared join goes, so a component with no label passes",
                "    for name in sorted(shipped - declared):",
                "    for name in []:",
                "a skill with no comp label",
            ),
            Mutation(
                "the reverse direction goes, so a label outliving its component passes",
                "    for name in sorted(declared - shipped - NON_DIRECTORY):",
                "    for name in []:",
                "a declared label with no directory is reported",
            ),
            Mutation(
                "the bundle stops being excluded, demanding a duplicate comp:rails-stack",
                "    shipped -= BUNDLE",
                "    shipped -= set()",
                "the rails-stack bundle needs no label of its own",
            ),
            Mutation(
                "the non-directory exemption goes, so packaging and marketplace report",
                'NON_DIRECTORY = {"packaging", "marketplace"}',
                "NON_DIRECTORY = set()",
                "packaging and marketplace are exempt",
            ),
            Mutation(
                # #487/#490. The rule exists because `gh issue create` errors on an unknown label,
                # so a lost defect report is the failure it prevents.
                "the created-label set is ignored, so every provisioned label reports missing",
                "                        if token not in created:",
                "                        if True:",
                "the same label created in the same plugin",
            ),
            Mutation(
                "the --repo scope test moves back to one line, mis-flagging an upstream call",
                '                if "--repo" in block:',
                '                if "--repo" in block.splitlines()[-1]:',
                "an upstream --repo call is out of scope",
            ),
            Mutation(
                "placeholders stop being templates, so `severity:sN` is demanded literally",
                "                        if placeholder.search(token):",
                "                        if False:",
                "placeholder 'severity:sN' is not judged",
            ),
            Mutation(
                "the comma list stops splitting, so a bad token hides behind a good one",
                '                    for token in (tok.strip() for tok in raw.split(",")):',
                "                    for token in [raw.strip()]:",
                # The unsplit token still looks missing, so the FIRING fixture passes anyway; the
                # silence fixture is what actually catches it.
                "every token provisioned is silent",
            ),
            Mutation(
                "the toggle rule widens past booleans and flags agent-applied keys",
                '            match = re.match(r"^\\s*([a-z_][a-z0-9_]*):\\s*(?:true|false)\\b", line)',
                '            match = re.match(r"^\\s*([a-z_][a-z0-9_]*):", line)',
                "a non-boolean key is out of scope",
            ),
            Mutation(
                "the wiring rule stops noticing a flow that never calls claim-verifier",
                '        if "claim-verifier" not in body:',
                "        if False:",
                "a flow that never names claim-verifier",
            ),
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
                # Anchor shortened by #491: the skip branch now also ticks the mention counter,
                # so the `continue` no longer sits on the next line. The stale-anchor rule caught
                # the drift rather than letting this mutation quietly stop mutating anything.
                "the topology rule demands a declaration from every single-agent command",
                "        if len(dispatched) < 2:",
                "        if False:",
                "a single agent needs no declaration",
            ),
            # #491. Every mutation below reverts one half of "a mention is not a dispatch". The
            # rule's own trap is that narrowing it produces false NEGATIVES, which are worse here
            # than the false positive being fixed -- so the silence fixtures and the firing
            # fixtures each get their own mutation, and neither direction is left assumed.
            Mutation(
                "detection reverts to a backticked name, so a MENTION is a dispatch again",
                "        dispatched = _dispatched_agents(body, named)",
                '        dispatched = {n: "backtick" for n in named}',
                "two agents merely mentioned, not dispatched",
            ),
            Mutation(
                "the signal stops being scoped to the name's own sentence",
                "    for end in _SENTENCE_END.finditer(prefix):\n        cut = max(cut, end.end())",
                "    for end in []:\n        cut = max(cut, end.end())",
                "two agents merely mentioned, not dispatched",
            ),
            Mutation(
                "subject position stops counting, losing ``qa-reporter` consolidates.`",
                '    if _STEP_LEAD.match(sentence):\n        return "subject-position"',
                '    if False:\n        return "subject-position"',
                "an agent opening its own step is a dispatch",
            ),
            Mutation(
                "the arrow handoff stops counting, losing /rails-flow:review's whole shape",
                '    if _HANDOFF_PREFIX.search(sentence):\n        return "handoff-arrow"',
                '    if False:\n        return "handoff-arrow"',
                "an arrow handoff is a dispatch",
            ),
            Mutation(
                "the imperative stops counting, losing `Dispatch all layers: ...`",
                '    if _DISPATCH_VERB.search(sentence):\n        return "dispatch-verb"',
                '    if False:\n        return "dispatch-verb"',
                "two agents dispatched with no declaration",
            ),
            Mutation(
                "fenced code is read as prose, so a name in a label description dispatches",
                '    return _FENCED.sub(lambda m: re.sub(r"[^\\n]", " ", m.group(0)), text)',
                "    return text",
                "an agent named only inside a fenced block is not dispatched",
            ),
            Mutation(
                "a Task/subagent invocation stops counting because it is inside a fence",
                '                if _TASK_INVOCATION.search(body[line_start:].split("\\n", 1)[0]):',
                "                if False:",
                "a Task invocation inside a fence is a dispatch",
            ),
            Mutation(
                "a thematic break stops ending a block, so frontmatter hides the first instruction",
                '_BLOCK_BREAK = re.compile(r"\\n[ \\t]*\\n|\\n[ \\t]*(?:-{3,}|={3,}|\\*{3,}|_{3,})'
                '[ \\t]*(?=\\n)")',
                '_BLOCK_BREAK = re.compile(r"\\n[ \\t]*\\n")',
                "an agent opening its own step is a dispatch",
            ),
            Mutation(
                # The narrowing's instrument. Without this, a `_dispatched_agents` that had gone
                # completely blind would satisfy every silence fixture above and report nothing
                # -- which is what the counter exists to make visible.
                "the mention counter stops moving, so an over-narrowed rule reads as a clean one",
                "                named_only += 1",
                "                named_only += 0",
                "must be COUNTED as such, not merely unreported",
            ),
            Mutation(
                "the coercion rule drops its backreference and flags any two identifiers",
                r'\b\1\.to_(?:i|f)\b',
                r'\b[a-z_]+\.to_(?:i|f)\b',
                "different identifiers are not a contradiction",
            ),
            Mutation(
                "the controller-inventory rule stops comparing markup against the inventory",
                "        if name not in inventory\n",
                "        if False\n",
                "markup names a controller the inventory omits",
            ),
            Mutation(
                "the ERB half is dropped, so a controller named in a literal goes unseen",
                "    for erb in _ERB_TAG.findall(value):\n"
                "        names |= {m for m in _QUOTED_LITERAL.findall(erb) if _CONTROLLER_NAME.match(m)}\n",
                "",
                "the ERB literal is still required to be listed",
            ),
            Mutation(
                "the raw attribute is tokenised, so Ruby keywords become controllers",
                '    names |= {t for t in _ERB_TAG.sub(" ", value).split() if _CONTROLLER_NAME.match(t)}',
                "    names |= {t for t in value.split() if _CONTROLLER_NAME.match(t)}",
                "ERB contributes its string literals and not its keywords",
            ),
            Mutation(
                "fences are left in, so backtick pairing walks off by one across the section",
                '    section = _FENCE.sub("", body[start: end if end > 0 else len(body)])',
                "    section = body[start: end if end > 0 else len(body)]",
                "a fenced block before the list does not blind the reader",
            ),
            # The two halves of that one line need separate mutations, because removing the call
            # trips only the off-by-one fixture: with the inventory destroyed, a rule that fires
            # too much still satisfies a fixture expecting a finding. Stripping the fence MARKERS
            # while keeping their bodies leaves pairing intact and isolates the other half.
            Mutation(
                "only the fence markers go, so a name in an EXAMPLE counts as one in the inventory",
                '_FENCE = re.compile(r"^```.*?^```", re.M | re.S)',
                '_FENCE = re.compile(r"^```[^\\n]*$", re.M)',
                "a name mentioned inside an example does not count as listed",
            ),
            Mutation(
                "a renamed inventory heading goes quiet instead of loud",
                '        return [Finding(\n'
                '            "controller-inventory-gap", _CONTROLLER_INVENTORY, 0,\n',
                "        return [], 0\n        _unreachable = [Finding(\n"
                '            "controller-inventory-gap", _CONTROLLER_INVENTORY, 0,\n',
                "a renamed inventory heading fails loud",
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
                "agent worktrees are no longer pruned, so a sweep reads other agents' copies",
                ', "design-corpora", "worktrees"}',
                ', "design-corpora"}',
                "another agent's copy",
            ),
            Mutation(
                "corpora no longer pruned from the walk",
                '"design-corpora", "worktrees"}',
                '"worktrees"}',
                "not ours to enforce",
            ),
            Mutation(
                "unbounded gh queries stop being flagged",
                "if not _GH_LIST.search(line) or not _INVOCATION.search(line):",
                "if True:",
                "unbounded",
            ),
            Mutation(
                "a shipped CI.run example with no test step stops being flagged (#391)",
                "            if _CI_SUITE_STEP.search(block):",
                "            if True:",
                "a CI.run example with no test step",
            ),
            Mutation(
                "the ci-gate rule escapes the shipped surface and reads the CHANGELOG",
                'if not (relpath.startswith("skills/") or relpath.startswith("plugins/")):',
                "if False:",
                "the CHANGELOG may quote a superseded example",
            ),
            Mutation(
                "the ci-gate rule stops reading plugins, covering only half the shipped surface",
                'if not (relpath.startswith("skills/") or relpath.startswith("plugins/")):',
                'if not relpath.startswith("skills/"):',
                "the same defect in a plugin",
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
        # The selftest's evidence guards read every doc under `references/` -- `verify_shipped_
        # evidence` and `verify_interaction_claims` both resolve it from the SUBJECT's location, so
        # a staged mutant with no `references/` made the unmutated selftest exit 1 and every
        # mutation vacuously "caught". A directory, so a new reference doc is picked up rather than
        # quietly missing. `run_baseline` is what now proves this is sufficient.
        needs=("skills/fidara-design/references",),
        mutations=(
            Mutation(
                "the totality guard stops naming unclassified corpus entries",
                "def verify_totality(",
                "def _disabled_verify_totality(",
                "",   # any failure counts: removing the entry point breaks many fixtures
            ),
            Mutation(
                "two rows may again be vouched for by one piece of doc (#95)",
                "    problems += verify_evidence_is_not_shared()\n",
                "",
                "two documented rows sharing one evidence string",
            ),
            # The substring half needs its own mutation: equality alone still catches the loud
            # case, so `"## Button"` silently satisfied by the Button-GROUP heading would go
            # unguarded on a rule that only compared for equality.
            Mutation(
                "the shared-evidence guard drops to equality and misses the prefix case",
                "            DOCUMENTED_EVIDENCE[a] in DOCUMENTED_EVIDENCE[b]\n"
                "            or DOCUMENTED_EVIDENCE[b] in DOCUMENTED_EVIDENCE[a]\n",
                "            DOCUMENTED_EVIDENCE[a] == DOCUMENTED_EVIDENCE[b]\n",
                "one row's evidence contained inside another's",
            ),
            Mutation(
                "a promoted row keeps its stale BUILD fallback unnoticed (#95)",
                "    stale = sorted(\n"
                "        {e.name for e in ENTRIES if e.is_documented and e.build.strip()}\n"
                "        | (set(BUILD) & {e.name for e in ENTRIES if e.is_documented})\n"
                "    )",
                "    stale = []",
                # The FIXTURE's label, not the guard's message. With `stale = []` the guard never
                # emits its message at all, so `expect_error` reports "expected BuildError, mapping
                # was accepted" under this label -- and the old `expects` ("still carrying a BUILD
                # fallback", one word off the label's "its") matched nothing. It only ever passed
                # because the whole selftest was failing for want of the reference docs; the
                # baseline control above is what made it visible.
                "a documented row still carrying its BUILD fallback",
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
            # `verify_interaction_claims` shipped in #399 with selftest fixtures and no mutations,
            # which is the gap this block closes: a fixture proves a guard fires TODAY, a mutation
            # proves the fixture would notice if the guard stopped firing. Both DIRECTIONS get one,
            # because the guard's whole point is that a one-way rule would have caught none of the
            # four stale rows it was written for -- and a mutation on only the `shipped` half would
            # reproduce that blind spot in the meta-check.
            Mutation(
                "the interaction guard stops flagging a `planned` row whose contract HAS landed",
                "        elif status.strip() != \"shipped\" and present:",
                "        elif False:",
                "the contract landed and the status was never flipped",
            ),
            Mutation(
                "the interaction guard stops flagging a `shipped` row with no doc behind it",
                "        if status.strip() == \"shipped\" and not present:",
                "        if False:",
                "does not appear in any reference doc",
            ),
            Mutation(
                "one document is allowed to vouch for two different interaction patterns",
                "        if probe in seen:",
                "        if False:",
                "share the probe",
            ),
            # `verify_no_undeclared_entry` (#89) is the negative direction the component half
            # never had. Both of its halves get a mutation for the same reason the interaction
            # guard's do -- and the second is the more important one here, because the way this
            # guard fails is not by going quiet but by becoming a false-positive machine that
            # someone then deletes.
            # Each `expects` is the FIXTURE's own label, never the guard's message -- with the
            # guard neutered it emits no message at all, so matching on it would match nothing
            # and every mutation would read as caught-by-something-else (#422).
            Mutation(
                "a `derivable` row is allowed to have a catalogue entry again",
                "        if entry.is_documented:\n            continue",
                "        if True:\n            continue",
                "a `derivable` row whose catalogue entry exists must be caught",
            ),
            Mutation(
                "the catalogue match widens to a substring, convicting correct rows",
                "            if title.casefold() == entry.name.casefold() or re.match(\n"
                "                re.escape(entry.name) + r\"\\s*[—–\\-(]\", title, re.I\n"
                "            ):",
                "            if entry.name.casefold() in title.casefold():",
                "must not convict a row named",
            ),
            # forms.md is the second catalogue file, and dropping it is silent: nothing else in
            # the run reads it, so without this the tuple could shrink to one file and the guard
            # would keep passing while blind to the whole forms family.
            Mutation(
                "the guard stops reading forms.md, blinding it to the forms family",
                'CATALOGUE_FILES = ("components.md", "forms.md")',
                'CATALOGUE_FILES = ("components.md",)',
                "forms.md is a catalogue file too",
            ),
            # `verify_cell_text` likewise. The interaction half is mutated rather than the ENTRIES
            # half because that is the loop the near-miss was found in: the note that nearly shipped
            # a broken table was an interaction note.
            Mutation(
                "the pipe guard stops reading interaction notes, so a `|` splits the row again",
                "    for name, status, note, _probe in INTERACTION_PATTERNS:\n"
                "        scan(f\"interaction pattern {name!r}\", name, status, note)",
                "    for name, status, note, _probe in ():\n"
                "        scan(f\"interaction pattern {name!r}\", name, status, note)",
                "a `|` inside an interaction note was not flagged",
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
        # `plugins/qa-flow`: its selftest reads profile/agent files across the plugin.
        needs=("plugins/qa-flow",),
        mutations=(
            Mutation(
                # #578: a conformant app was flagged S1 on EVERY page because the pass looked up
                # `outline` while the ring lived in `box-shadow`. Requiring the method does not
                # verify the diff was done right -- it stops an unmethodical blocking S1 being
                # filed silently, which is the part that cost a morning.
                "a blocking S1 stops needing a method, so a property lookup can cry wolf again",
                '    if counts.get("No Focus Indicator", 0) > 0:',
                "    if False:",
                "keyboard: missing-indicator count with no method recorded",
            ),
            # #424: the modal-CRUD 422 assertion, and the carve-out that lets a valid modal row
            # exist at all. Both directions, because widening the carve-out is how it goes quiet.
            Mutation(
                "the modal-CRUD 422 assertion stops firing",
                '    elif surface == "modal" and exercised:',
                "    elif False:",
                "modal CRUD that navigated instead of re-rendering",
            ),
            Mutation(
                "the 422 carve-out widens past modal rows, so any non-2xx passes",
                '    modal_422 = row.get("Surface", "").lower() == "modal" and row["HTTP"].strip() == "422"',
                "    modal_422 = True",
                "exercised a form on a 500",
            ),
            Mutation(
                "a Pass on a non-2xx/3xx page is accepted (the #106 defect)",
                # Anchor updated by #424: the `elif` became an `if` with the modal-422 carve-out
                # beside it. The stale-anchor rule caught the drift rather than letting this
                # mutation quietly stop mutating anything.
                'if row["HTTP"] and not _http_ok(row["HTTP"]) and not modal_422:',
                "if False:",
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
                # The whole reason the third state exists: folding a crawl visit into `covered`
                # would inflate the one number this tool keeps honest, on exactly the routes
                # nobody wrote a test for.
                "a crawl visit is folded into `covered`, inflating the coverage percentage",
                "    seen = visited_paths(evidence)",
                "    seen = {**visited_paths(evidence), **visit_only_paths(evidence)}",
                "a crawl visit changed the coverage arithmetic",
            ),
            Mutation(
                "the GET-only carve-out goes, so a DELETE route is claimed as crawl-visited",
                "                  if c.covered and not c.route.destructive}",
                "                  if c.covered}",
                "a destructive route was claimed as crawled",
            ),
            Mutation(
                "the third-state line is suppressed when zero, so nobody can tell it ran",
                '    print(f"  of those, {len(crawled)} visited by a crawl but never asserted, "',
                '    print("") if False else print(f"  of those, {max(len(crawled), 1)} visited by a crawl but never asserted, "',
                "the third-state line must print even when the count is zero",
            ),
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
        name="blast_radius",
        subject="plugins/qa-flow/scripts/blast_radius.py",
        selftest="plugins/qa-flow/scripts/blast_radius_selftest.py",
        mutations=(
            # -- the reverse walk itself -------------------------------------------------------
            Mutation(
                "the walk follows OUTGOING edges, reporting dependencies as dependents",
                '        target = edge.get("to")',
                '        target = edge.get("from")',
                "a dependent is included by an incoming references edge",
            ),
            Mutation(
                "the depth cap stops applying, so the radius silently becomes the whole app",
                "    for level in range(1, max(depth, 0) + 1):",
                "    for level in range(1, 99):",
                "the depth cutoff excludes",
            ),
            # Narrowing WITHOUT saying so is the failure this tool exists to prevent, so the
            # cutoff's report is a separate rule from the cutoff itself.
            Mutation(
                "the depth cutoff stops reporting what it dropped",
                "    for node in frontier:\n        for edge in incoming.get(node, []):",
                "    for node in []:\n        for edge in incoming.get(node, []):",
                "the depth cutoff is reported, not silent",
            ),
            Mutation(
                "an enrichment edge stops naming the tool that produced it",
                '                    + (f"  [via {tool}]" if tool else ""),',
                '                    + "",',
                "an enriched edge names the tool that produced it",
            ),
            Mutation(
                "--no-enrichment stops excluding machine-local edges",
                "    if use_enrichment and isinstance(block, dict):",
                "    if isinstance(block, dict):",
                "--no-enrichment reproduces a bare-runner walk",
            ),
            # -- the five non-negotiable risk axes ----------------------------------------------
            Mutation(
                "the migration axis stops firing",
                '    "migration": ("db/migrate/", "db/schema.rb", "db/structure.sql"),',
                "",
                "fires the migration axis",
            ),
            Mutation(
                "the shared-concern axis stops firing",
                '    "shared-concern": ("/concerns/", "app/views/layouts/", '
                '"app/helpers/application_helper.rb"),',
                "",
                "fires the shared-concern axis",
            ),
            Mutation(
                "the money name hints stop firing",
                '    "money": ("payment", "invoice", "billing", "charge", "subscription", '
                '"price", "pricing",\n              "order", "ledger", "refund", "wallet", '
                '"transaction", "checkout", "coupon",\n              "discount", "payout", '
                '"tax"),',
                "",
                "fires the money axis",
            ),
            # The whole point of "non-negotiable": a project's config may ADD to an axis and may
            # never empty one. Declaring `migration: []` must not switch the structural rule off.
            Mutation(
                "config becomes able to switch a structural axis off",
                "        for axis, markers in STRUCTURAL_RISK.items():",
                "        for axis, markers in {k: v for k, v in STRUCTURAL_RISK.items() "
                "if declared.get(k) != []}.items():",
                "config cannot switch a non-negotiable axis off",
            ),
            Mutation(
                "a declared high-risk path stops being printed as excluded",
                '            report.excluded.append(Exclusion(path, "declared in qa.config.yml '
                '`blast_radius.exclude`"))',
                "            pass",
                "a declared exclusion is printed with its reason",
            ),
            # -- the silence half: rules that are only useful if they stay quiet -----------------
            Mutation(
                "`authenticated` becomes an auth signal, so every controller change is wide",
                "TAG_RISK: dict[str, str] = {",
                'TAG_RISK: dict[str, str] = {\n    "authenticated": "auth",',
                "an authenticated controller is not on its own an auth hit",
            ),
            Mutation(
                "the risk classifier stops exempting test files, so every spec edit is wide",
                "    report.risk = classify_risk([p for p in considered "
                "if not p.startswith(TEST_ROOTS)],",
                "    report.risk = classify_risk(considered,",
                "a spec-only change is never wide",
            ),
            Mutation(
                "non-app files stop being excluded, so a docs edit reads as under-determined",
                "        if not (path.startswith(APP_ROOTS) or path in APP_FILES):",
                "        if False:",
                "a docs-only change is excluded with a reason, not unresolved",
            ),
            # -- accounting: an unexplained file must never read as "nothing is affected" --------
            Mutation(
                "an unaccounted-for app file stops forcing the wide selection",
                "        return bool(self.risk) or bool(self.unresolved)",
                "        return bool(self.risk)",
                "an unaccounted-for app file forces wide",
            ),
            Mutation(
                "a conventional spec path that does not exist is dropped instead of reported",
                '            present = (root / candidate).exists()\n'
                '            out[candidate] = TestTarget(candidate, f"{reason} ({why})", present)',
                '            present = (root / candidate).exists()\n'
                "            if present:\n"
                '                out[candidate] = TestTarget(candidate, f"{reason} ({why})", '
                "present)",
                "a missing spec is reported, not dropped",
            ),
            Mutation(
                "the test-framework narrowing stops reporting itself",
                "    if present_frameworks:\n"
                "        for framework in sorted(set(TEST_ROOTS) - present_frameworks):",
                "    if False:\n"
                "        for framework in sorted(set(TEST_ROOTS) - present_frameworks):",
                "and the drop is printed once, with its reason",
            ),
            Mutation(
                "the excluded section is hidden when it is empty",
                '    lines.append(f"excluded from the radius -> {len(report.excluded)}")',
                "    if report.excluded:\n"
                '        lines.append(f"excluded from the radius -> {len(report.excluded)}")',
                "the excluded section prints even when empty",
            ),
            # -- route selection reads the #119 table rather than asserting agreement -------------
            Mutation(
                "every route is claimed to be in the route table, so a disagreement is hidden",
                "                                              inclusion.unit in by_key)",
                "                                              True)",
                "a graph route absent from the route table is flagged",
            ),
            # -- exit codes: 2 is "could not run", never 0 ------------------------------------------
            Mutation(
                "an empty changed-file list becomes a clean run instead of UNUSABLE",
                '        raise Unusable("no changed files supplied -- pass --changed or '
                '--changed-from")',
                "        return []",
                "no changed files is UNUSABLE (2), not clean (0)",
            ),
            Mutation(
                "--require-graph falls back silently instead of failing",
                "    elif args.require_graph:",
                "    elif False:",
                "--require-graph with no graph is UNUSABLE (2), never a silent fallback",
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
    # #129. Two subjects, one feature: the CANONICAL contrast instrument in scripts/, and the
    # SHIPPED one inside design-flow that a user runs on their own pack. They carry the same maths
    # for a stated reason (a plugin cannot import from maintainer tooling), so the parity fixture
    # that compares them is itself mutated — a parity check that stopped comparing would let the
    # two drift in exactly the silence it exists to prevent.
    Guard(
        name="check_token_contrast",
        subject="scripts/check_token_contrast.py",
        selftest="scripts/check_token_contrast.py",
        # It reads the doctrine file and every shipped pack, and its parity fixtures import the
        # shipped module. Without these the mutant dies on a missing file and every mutation reads
        # as "caught" by a traceback rather than by the fixture named below.
        needs=("skills/fidara-design/references/foundations-tokens.md",
               "plugins/design-flow/brands/fidara/theme.css",
               "plugins/design-flow/brands/_template/theme.css",
               "plugins/design-flow/scripts/palette_candidates.py",
               "plugins/design-flow/scripts/brand_pack_lint.py"),
        mutations=(
            Mutation(
                "the gate narrows back to the doctrine file, so the packs go unmeasured (#129)",
                "    return [repo / TOKENS.relative_to(REPO), *packs]",
                "    return [repo / TOKENS.relative_to(REPO)]",
                "every shipped brand pack is measured",
            ),
            Mutation(
                "an empty pack glob becomes a clean pass instead of a hard error",
                "    if not packs:\n        raise Unparseable(",
                "    if False:\n        raise Unparseable(",
                "a tree with no brand pack enumerated sources",
            ),
            Mutation(
                "the sRGB breakpoint reverts to WCAG 2.0's 0.03928",
                "SRGB_LINEAR_BREAKPOINT = 0.04045",
                "SRGB_LINEAR_BREAKPOINT = 0.03928",
                "the sRGB linearisation breakpoint is WCAG 2.2's 0.04045",
            ),
            Mutation(
                "the parity check with the shipped implementation stops comparing",
                "    return max(abs(left(a, b) - right(a, b)) for a in probes for b in probes)",
                "    return 0.0",
                "the parity comparison can actually detect a disagreement",
            ),
            Mutation(
                "the two token parsers may disagree without anyone noticing",
                "        if ours is None or ours.upper() != value.upper():",
                "        if False:",
                "the parser comparison can actually detect a disagreement",
            ),
            Mutation(
                "the muted-text pair is dropped again (it was the missing one, at 2.71:1)",
                '    ("muted text on a muted surface", "--muted-foreground",   "--muted",      "light"),\n',
                "",
                "the muted-text pair is measured in both modes",
            ),
        ),
    ),
    # The shipped half. Roughly half of these break a fixture whose job is to stay SILENT, because
    # this tool's whole risk is false positives: a checker that rewrites a client's brand colour
    # which was already fine gets switched off, and then nothing measures the one that was not.
    Guard(
        name="palette_candidates",
        subject="plugins/design-flow/scripts/palette_candidates.py",
        selftest="plugins/design-flow/scripts/palette_candidates.py",
        # It imports its sibling for the ROLE CONTRACT -- that import is the reuse that makes
        # "the composer covers the whole contract" checkable at all.
        deps=("plugins/design-flow/scripts/brand_pack_lint.py",),
        mutations=(
            Mutation(
                "the contrast bar stops comparing, so an unreadable palette ships",
                "    return [row for row in measure(roles) if not row.passes]",
                "    return []",
                "a failing candidate is reported, not passed",
            ),
            Mutation(
                "the bar drops to the large-text allowance, grandfathering unreadable body text",
                "AA_NORMAL = 4.5",
                "AA_NORMAL = 3.0",
                "3:1 is the LARGE-text allowance",
            ),
            Mutation(
                "every palette is reported as failing (the false-positive direction)",
                "        return self.ratio >= AA_NORMAL",
                "        return False",
                "a conformant candidate is silent",
            ),
            Mutation(
                "measuring zero pairs reports clean",
                "    if not CANDIDATE_PAIRS:",
                "    if False:",
                "measuring nothing is not a pass",
            ),
            Mutation(
                "the composer may omit a role, so a pack falls back to a stock Tailwind colour",
                '    missing = [r for r in bpl.ROLES if r not in light]',
                "    missing = []",
                "a role added to the contract makes snap() fail loudly",
            ),
            Mutation(
                "a surface role may stay put on dark, so dark mode inherits the light surface",
                "    unrepointed = [r for r in bpl.DARK_REQUIRED if dark.get(r) == light.get(r)]",
                "    unrepointed = []",
                "a dark-required role that does not move makes snap() fail loudly",
            ),
            Mutation(
                "nearest_passing hands back the failing input dressed as a fix",
                "    if contrast(colour, surface) >= threshold:\n        return colour, contrast(colour, surface)",
                "    return colour, contrast(colour, surface)",
                "the nearest alternative actually passes",
            ),
            Mutation(
                "nearest_passing rewrites a brand colour that was already fine",
                "    if contrast(colour, surface) >= threshold:",
                "    if False:",
                "a brand colour that already passes is returned unchanged",
            ),
            Mutation(
                "the search drifts off the client's hue instead of only its lightness",
                "            candidate = _from_hls(hue, candidate_light, sat)",
                "            candidate = _from_hls((hue + 0.25) % 1.0, candidate_light, sat)",
                "the nearest alternative keeps the client's hue",
            ),
            Mutation(
                "a constrained search with no answer returns rather than saying so",
                '    raise Unusable(\n        f"no {direction} shade of {colour} clears',
                '    return colour, contrast(colour, surface)\n    raise Unusable(\n        f"no {direction} shade of {colour} clears',
                "a constrained search with no answer returned instead of raising",
            ),
            Mutation(
                "a pack with no .dark block is measured as though light were both modes",
                '    if not dark:\n        raise Unusable(f"{theme_css}: no `.dark` block',
                '    if False:\n        raise Unusable(f"{theme_css}: no `.dark` block',
                "a pack with no .dark block was read instead of refused",
            ),
            Mutation(
                "`.dark` stops inheriting from `:root` (the #304 mechanism, in the reader)",
                '    scopes["dark"] = {**scopes["light"], **dark}',
                '    scopes["dark"] = dict(dark)',
                "a pack read back off disk measures the same as the model that wrote it",
            ),
            Mutation(
                "an emitted manifest claims the chart validation nobody ran",
                '        "chart_palette_validated": False,',
                '        "chart_palette_validated": True,',
                "the emitted manifest never claims a validation it did not run",
            ),
            Mutation(
                "the catalogue is free to grow into the style menu this must not become",
                "CATALOGUE_BAND = (8, 12)",
                "CATALOGUE_BAND = (8, 400)",
                "the catalogue band is the declared 8-12",
            ),
            Mutation(
                "a type pairing may carry its own fluid type scale, forking a system axis",
                "    return sorted(slug for slug, pairing in pairings.items()\n"
                "                  if any(key not in PAIRING_KEYS for key in pairing))",
                "    return []",
                "a pairing that DID carry a type scale would be caught",
            ),
            Mutation(
                "an unparseable colour resolves to something arbitrary instead of raising",
                "    if not isinstance(value, str) or not HEX_RE.match(value.strip()):",
                "    if False:",
                "",   # normalise_hex is called everywhere; the module fails hard, which is honest
            ),
        ),
    ),
    Guard(
        name="maintainer_doctor",
        subject="scripts/maintainer_doctor.py",
        selftest="scripts/maintainer_doctor_selftest.py",
        needs=(
            # + `scripts`: GATES names ~55 sibling scripts; listing them by hand is the same rot that made check_handoff inert.
            ".gitignore",
            "scripts",
            # ...and `plugins`, because GATES names checkers in BOTH trees. Reaching this second
            # missing path only after fixing the first is the point of `run_baseline`: an inert
            # guard hides every downstream problem behind the first one.
            "plugins",
            "evals",
        ),
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
            # #129 added a SECOND name-keyed carve-out, so it gets the same three mutations the
            # first one has: a name that matches nothing, a set that grew, and the direction
            # nobody thinks of -- an "allowance" that is really a tightening.
            Mutation(
                "the slow-gate allowance is keyed on a gate that does not exist",
                '    "mutation coverage": 900,',
                '    "mutatoin coverage": 900,',
                "SLOW_GATES names no such gate",
            ),
            Mutation(
                "the slow-gate allowance widens to a gate that reads the tree once",
                '    "mutation coverage": 900,',
                '    "mutation coverage": 900,\n    "packaging determinism": 900,',
                "SLOW_GATES is",
            ),
            Mutation(
                "a SLOW_GATES entry silently tightens a gate instead of loosening it",
                '    "mutation coverage": 900,',
                '    "mutation coverage": 30,',
                "silently TIGHTENS a gate",
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
        needs=(
            # + `plugins`: its selftest resolves every script each checks.json names, across all three plugins.
            "plugins/rails-flow/checks.json", "plugins/qa-flow/checks.json",
               "plugins/design-flow/checks.json",
            "plugins",
        ),
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
        name="classify_boot_failure",
        subject="plugins/qa-flow/scripts/classify_boot_failure.py",
        selftest="plugins/qa-flow/scripts/classify_boot_failure.py",
        mutations=(
            Mutation(
                "category order stops mattering, so incidental noise can outvote the real cause",
                "    for name, patterns, action in CATEGORIES:",
                "    for name, patterns, action in reversed(CATEGORIES):",
                "the specific cause wins over incidental noise",
            ),
            Mutation(
                "everything classifies as an application error",
                "    for name, patterns, action in CATEGORIES:",
                "    for name, patterns, action in []:",
                "EADDRINUSE",
            ),
        ),
    ),
    Guard(
        name="crawl_report",
        subject="plugins/qa-flow/scripts/crawl_report.py",
        selftest="plugins/qa-flow/scripts/crawl_report.py",
        # `plugins/qa-flow/scripts/crawl_collector.js`: its selftest asserts the collector ships beside the judge.
        needs=("plugins/qa-flow/scripts/crawl_collector.js",),
        mutations=(
            Mutation(
                # The dangerous direction for a de-duplicator: merging defects that are not the
                # same one. Grouping on the rule alone would hide every distinct error behind
                # whichever fired first.
                "grouping drops `detail`, so two different errors merge under one rule name",
                "        routes = out.setdefault((f.rule, f.detail), [])",
                "        routes = out.setdefault((f.rule, f.rule), [])",
                "same rule, different detail stays two groups",
            ),
            Mutation(
                "a route repeating within a group is counted twice, inflating the spread claim",
                "        if f.route not in routes:",
                "        if True:",
                "one route counted once per group",
            ),
            Mutation(
                "uncaught exceptions stop being reported, so an S1 category goes unobserved again",
                '    for error in page.get("pageErrors", []) or []:',
                "    for error in []:",
                "an uncaught exception is reported",
            ),
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
                # The dangerous direction for a de-duplicator: a shorter report that hid a defect.
                "grouping drops `detail`, so two different defects merge under one rule name",
                "        refs = out.setdefault((f.rule, f.detail), [])",
                "        refs = out.setdefault((f.rule, f.rule), [])",
                "same rule, different detail stays two groups",
            ),
            Mutation(
                "a repeated ref is counted twice, inflating the occurrence claim",
                "        if f.ref not in refs:",
                "        if True:",
                "a repeated ref is counted once",
            ),
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
        # Without this the collector is absent from the mutant's directory, and every fixture that
        # cross-checks it -- including the `dismiss.*` field checks and the syntax gate's own
        # negative test -- silently does not run. `visual_baseline` below needs it for the same
        # reason.
        needs=("plugins/qa-flow/scripts/crawl_collector.js",),
        mutations=(
            Mutation(
                # The dangerous direction for a de-duplicator: a shorter report that hid a defect.
                "grouping drops `detail`, so two different defects merge under one rule name",
                "        refs = out.setdefault((f.rule, f.detail), [])",
                "        refs = out.setdefault((f.rule, f.rule), [])",
                "same rule, different detail stays two groups",
            ),
            Mutation(
                "a repeated ref is counted twice, inflating the occurrence claim",
                "        if f.ref not in refs:",
                "        if True:",
                "a repeated ref is counted once",
            ),
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
            # #105 criterion 4, second half. The first of these is the one that decides whether the
            # focus-restore rule is usable: APG's base Disclosure pattern has no Escape row, so
            # dropping the scope guard fires on every accordion on the internet.
            Mutation(
                "the APG scope guard goes, so every ordinary accordion reports a focus-restore bug",
                '    if kind not in RESTORE_REQUIRED:',
                '    if False:',
                "an ordinary disclosure that keeps focus is NOT a finding",
            ),
            Mutation(
                "the combobox discriminator goes, so combobox popups stop being judged",
                '    if trigger_role == "combobox":',
                '    if False:',
                "a combobox that keeps focus fires focus-restore-missing",
            ),
            Mutation(
                "the menu discriminator goes, so menu popups stop being judged",
                '    if haspopup == "menu" or popup_role == "menu":',
                '    if False:',
                "a menu that keeps focus fires focus-restore-missing",
            ),
            Mutation(
                "a probe that never completed is graded instead of named",
                '    if closed is None or restored is None:',
                '    if False:',
                "a probe with focusRestored=null is not judged clean",
            ),
            # Ordering, not presence: moving the calls BELOW the exclusions silently drops every
            # overlay opened by a link -- which is a large share of the real ones.
            Mutation(
                "the dismissal is judged after the exclusions, so links lose their overlays",
                '        judge_dismissal(result, ref, control)\n'
                '        judge_containment(result, ref, control)\n'
                '        if excluded_reason(control):\n'
                '            result.excluded += 1\n'
                '            continue',
                '        if excluded_reason(control):\n'
                '            result.excluded += 1\n'
                '            continue\n'
                '        judge_dismissal(result, ref, control)\n'
                '        judge_containment(result, ref, control)',
                "a link with href is still judged on focus restore",
            ),
            # #114's overlay criterion (a), the half that stayed an agent-typed number for eight
            # releases. Every mutation below except the last two makes the rule fire MORE, and the
            # scope guard is the one that decides whether it is usable: APG specifies the OPPOSITE
            # of containment for menus and comboboxes, so a rule that ignores modality files S1s
            # against behaviour the spec describes the other way.
            Mutation(
                "the modality scope guard goes, so every non-modal dialog is judged on containment",
                "    if not is_modal(containment):",
                "    if False:",
                "that leaks Tab is NOT a finding",
            ),
            Mutation(
                "modality is read by attribute PRESENCE, so aria-modal=\"false\" reads as modal",
                '    return str(containment.get("ariaModal") or "").strip().lower() == "true"',
                '    return containment.get("ariaModal") is not None',
                "is_modal reads aria-modal by VALUE, not by presence",
            ),
            Mutation(
                "the backward direction is dropped, so half of APG's mandate stops being checked",
                '    leaked = [name for name, escaped in (("Tab", forward), ("Shift+Tab", backward)) if escaped]',
                '    leaked = [name for name, escaped in (("Tab", forward),) if escaped]',
                "Shift+Tab alone leaking is still a finding",
            ),
            Mutation(
                "a walk that never completed is graded instead of named",
                "    if forward is None or backward is None:",
                "    if False:",
                "a walk with forwardEscaped=null is not judged clean",
            ),
            Mutation(
                "a layer the walk could not start in is judged anyway",
                '    if not containment.get("containerFound"):',
                "    if False:",
                "a dialog that opened without taking focus is not judged contained",
            ),
            Mutation(
                "the empty-layer guard goes, so a modal with nothing tabbable reports as leaky",
                '    if not containment.get("tabbables"):',
                "    if False:",
                "a modal with no tabbable element inside is not a containment finding",
            ),
            # The vacuous-pass mutation. Nothing about the OUTPUT changes -- the same findings are
            # printed -- but the denominator beside them goes to zero, so a sweep that walked
            # nothing becomes indistinguishable from an app with no leaky modals.
            Mutation(
                "the containment denominator stops counting, so a vacuous pass reads as a clean one",
                "    result.containment_judged += 1",
                "    pass",
                "counts toward the denominator",
            ),
            # The syntax gate's own negative test. `node --check <path>` exits 0 on a broken ESM
            # file, so this gate is one careless edit away from being unable to fail at all.
            Mutation(
                "the collector syntax gate always reports success",
                '    return proc.returncode, proc.stderr.decode("utf-8", "replace")',
                '    return 0, ""',
                "the module-mode check FAILS on a broken ES module",
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
                "    missing = [k for k in DETERMINISM_KEYS if not d.get(k)]",
                "    missing = []",
                "motion not frozen",
            ),
            Mutation(
                "the first matching prefix wins instead of the longest",
                '        if route.startswith(pattern) and len(pattern) > best:',
                '        if route.startswith(pattern) :',
                "the longest matching prefix wins",
            ),
            # The ignore-region half of #112. `ignored` shipped in the schema, emitted as a
            # hardcoded `[]` and read by nobody, so the field existed and the feature did not.
            # These three break the parts that make it real rather than declared.
            Mutation(
                "the mask a config demands is trusted instead of verified against the run",
                "        if want != got:",
                "        if False:",
                "a mask the config demands but the run never applied is refused",
            ),
            Mutation(
                "a per-route mask REPLACES the global list instead of adding to it",
                '    out = list(visual.get("ignore") or [])',
                "    out = []",
                "a per-route mask ADDS to the global list",
            ),
            Mutation(
                "an unreadable line in the visual block is skipped and silently defaulted",
                "        raise Unusable(_unreadable(path, lineno, raw))",
                "        continue",
                "an unreadable tolerance is refused, not silently defaulted",
            ),
            Mutation(
                "a regression reports its ratio without the diff image",
                '            picture = shot.get("diff") or "(none written: the collector produced '
                'no diff image)"',
                '            picture = "(none)"',
                "a regression names its diff image",
            ),
        ),
    ),
    # #360. Every mutation here makes a STALE NUMBER read as a fresh one, which is the only thing
    # this checker can fail on. Note what is deliberately absent: no mutation asks whether a copy
    # of a shape is justified, because the quality pass is advisory and a gate on taste would
    # contradict the doctrine this guards.
    Guard(
        name="check_shared_shapes",
        subject="scripts/check_shared_shapes.py",
        selftest="scripts/check_shared_shapes.py",   # --selftest lives in the module itself
        mutations=(
            Mutation(
                "the count comparison stops comparing, so a stale number passes",
                "        if want_files != len(hits):",
                "        if False:",
                "a wrong count in the table is DRIFT",
            ),
            # A `continue` rather than `if False:`: disabling the membership test would index a
            # missing key and die with a KeyError, and a mutation that crashes before a labelled
            # assertion is caught by a traceback rather than by the fixture written for it.
            Mutation(
                "a measured shape with no row in the table goes unreported",
                '        if shape.label not in rows:\n'
                '            findings.append(\n'
                '                f"{shape.label}: measured in {len(hits)} file(s) and has NO row in'
                ' the table. A "\n'
                '                f"count nobody reads is not doctrine.")\n'
                "            continue\n",
                "        if shape.label not in rows:\n            continue\n",
                "a shape with no row is reported",
            ),
            Mutation(
                "the other direction of the join goes, so prose nothing measures passes",
                "    for label in rows:",
                "    for label in []:",
                "a table row nothing measures is reported",
            ),
            Mutation(
                "a pattern that matches nothing is accepted, so a rotted regex reads as a pass",
                "        if not hits:",
                "        if False:",
                "a pattern that matches nothing is reported",
            ),
            Mutation(
                "an empty marked table parses instead of raising",
                "    if not rows:",
                "    if False:",
                "an empty marked table parsed instead of raising",
            ),
            # The corpus guard. With no roots every count is 0, every comparison is vacuous, and a
            # gate over zero files reports exactly like a gate over a clean repo.
            Mutation(
                "the measured roots go empty, so every count is taken over no files",
                'ROOTS = ("plugins", "scripts")',
                "ROOTS = ()",
                "the source walk finds the corpus files",
            ),
            # #398. `reach` is a second, independent claim per row: how many copies share one
            # install root, which is the ceiling on what extracting the shape could remove. The
            # file count can be right while it is wrong, so it needs its own mutation.
            Mutation(
                "the reach comparison stops comparing, so a stale ceiling passes",
                "        if want_reach != got_reach:",
                "        if False:",
                "a wrong reach in the table is DRIFT",
            ),
            # The grouping, not the comparison. A `unit()` that answers the same thing for every
            # path makes reach == files everywhere: each row stays internally consistent and the
            # column silently stops meaning "one install root".
            Mutation(
                "every path groups into one install root, so reach collapses into the file count",
                '    if parts[0] == "plugins" and len(parts) > 1:',
                "    if False:",
                "every declared shape is measured at its known count and reach in the corpus",
            ),
            Mutation(
                "a plugin directory the manifest never installs stops being reported",
                "    return sorted(u for u in seen if u.startswith(\"plugins/\") and u not in roots)",
                "    return []",
                "a copy under an undeclared plugin directory is reported",
            ),
            # Both directions of the manifest read. Returning an empty set instead of raising
            # would make every measured plugin undeclared -- a rule that fires on everything is a
            # rule that gets switched off, which is the same defect as one that never fires.
            Mutation(
                "an unparseable manifest yields no roots instead of refusing to guess",
                "        raise Unreadable(f\"{MANIFEST}: not readable as JSON ({exc}), so no install root is known \"\n"
                "                         \"and `reach` would be grouping by a boundary nothing confirms\") from exc",
                "        return set()",
                "an unparseable manifest returned instead of raising",
            ),
        ),
    ),
    # #92 (Phase 5). Same argument as `check_shared_shapes` above, one skill along: every mutation
    # here makes a STALE CLAIM read as a fresh one. Two are structural rather than per-rule — the
    # corpus walk going vacuous, and the measurement widening from "marketing rows" to "all of
    # them" — because a gate whose INPUT quietly changed reports clean exactly like a gate over a
    # correct repo. The last one breaks the checker the other way, so the silence direction has a
    # mutation too: a pacing gate that fires on our own shipped sequence is a gate someone deletes.
    # #91. The rule was PRACTISED in 16 of 18 sections and stated nowhere, so the mutations ask
    # the two questions that matter: can it still fire, and can prose make it fire wrongly.
    Guard(
        name="check_section_landmarks",
        subject="scripts/check_section_landmarks.py",
        selftest="scripts/check_section_landmarks.py",
        needs=("skills/fidara-design/references",),
        mutations=(
            Mutation(
                "the name test accepts any aria-* attribute, so aria-hidden passes as a name",
                'NAMED = re.compile(r"(?<![-\\w])aria-(?:label|labelledby)\\s*=", re.I)',
                'NAMED = re.compile(r"(?<![-\\w])aria-[a-z]+\\s*=", re.I)',
                "'<section aria-hidden=\"true\">' does not name the section",
            ),
            Mutation(
                # A `data-` prefixed attribute is not an ARIA attribute. `\b` matched inside
                # `data-aria-label`; this gate's own fixture caught it.
                "the token boundary relaxes, so data-aria-label counts as an accessible name",
                'NAMED = re.compile(r"(?<![-\\w])aria-(?:label|labelledby)\\s*=", re.I)',
                'NAMED = re.compile(r"\\baria-(?:label|labelledby)\\s*=", re.I)',
                "'<section data-aria-label=\"x\">' does not name the section",
            ),
            Mutation(
                "the exemption matches by prefix, so any hero-ish tag is waved through",
                "            if tag in exempt:",
                "            if any(tag.startswith(e[:20]) for e in exempt):",
                "a lookalike hero tag still fails",
            ),
            Mutation(
                "prose is scanned as markup, making the gate unpassable beside its own doctrine",
                "    for offset, raw in code_blocks(text):",
                "    for offset, raw in [(0, text)]:",
                "a bare <section> in PROSE is not a finding",
            ),
            Mutation(
                # `return [] or [...]` would be a NO-OP -- `[]` is falsy, so `or` yields the
                # comprehension. Mutate the pattern to one that cannot match instead.
                "the fence pattern matches nothing, so every file reports clean",
                'FENCE = re.compile(r"^(?P<t>`{3,})',
                'FENCE = re.compile(r"^(?P<t>`{99,})',
                # Killing the extractor makes the very FIRST fixture fail, before the one that
                # probes `code_blocks` directly. That earlier fixture is the honest expectation.
                "a bare section is a finding",
            ),
            Mutation(
                # #475. The footer rule and the section rule are the same join over the same
                # markup, deliberately in one file so they cannot drift apart.
                "a nested footer stops being reported, so a page footer loses contentinfo silently",
                "        for offset_c, tag, parent in nested_footers(body):",
                "        for offset_c, tag, parent in []:",
                "a footer inside <section> is reported",
            ),
            Mutation(
                "a CLOSED ancestor still counts, flagging every footer that follows a band",
                "            if stack and stack[-1] == tag:",
                "            if False:",
                "a footer AFTER a closed section is silent",
            ),
            Mutation(
                # The bug this gate's own doctrine triggered: `<nav>` written inside an ERB comment
                # opened an element that never closed.
                "comments are scanned as markup again, so prose in a comment opens elements",
                "        body = strip_non_markup(raw)",
                "        body = raw",
                "an ERB comment naming <nav> does not open one",
            ),
            Mutation(
                "comment blanking drops the newlines, so every later line number is wrong",
                'return NON_MARKUP.sub(lambda m: re.sub(r"[^\\n]", " ", m.group(0)), body)',
                'return NON_MARKUP.sub("", body)',
                "a line number after a comment is still correct",
            ),
            Mutation(
                "a stale exemption stops being reported, so a carve-out outlives its markup",
                "        if declared and used < declared:",
                "        if False:",
                "a declared exemption matching nothing is reported",
            ),
        ),
    ),
    Guard(
        name="check_page_pacing",
        subject="scripts/check_page_pacing.py",
        selftest="scripts/check_page_pacing.py",   # --selftest lives in the module itself
        # The LAY-017 fixture (#476) re-derives its measurement from the REAL band table, so the
        # doc has to be staged. Without it the baseline selftest fails in the tempdir and every
        # mutation below is INERT -- which run_baseline reported rather than passing silently.
        needs=("skills/fidara-design/references/page-anatomies.md",
               "skills/fidara-design/references/coverage.md",
               "skills/fidara-design/references/foundations-tokens.md"),
        mutations=(
            Mutation(
                "the measured row count stops being compared, so a stale 14 passes",
                "    if measured != pacing.identical_rows:",
                "    if False:",
                "a wrong identical-row count is reported",
            ),
            Mutation(
                "the band range stops bounding the table that prints it",
                "    if not pacing.band_min <= len(pacing.bands) <= pacing.band_max:",
                "    if False:",
                "a band count outside the stated range is reported",
            ),
            Mutation(
                "a band may compose from a row that does not exist",
                "        if band.composed not in names:",
                "        if False:",
                "a band naming no coverage row is reported",
            ),
            Mutation(
                "the tone vocabulary stops being joined to the token file",
                "        if band.tone not in roles:",
                "        if False:",
                "a tone naming no role is reported",
            ),
            Mutation(
                "tone may stop alternating, so bands lose their edges",
                "        if prev.tone == nxt.tone:",
                "        if False:",
                "two consecutive bands on one tone are reported",
            ),
            Mutation(
                "consecutive bands may share a shape — the fourteen-stacks defect itself",
                "        if prev.shape == nxt.shape:",
                "        if False:",
                "two consecutive bands of the same shape are reported",
            ),
            # The corpus guard. With headers and separators counted as components, the join is over
            # rows that are not rows, and a name could match a table heading.
            Mutation(
                "the coverage walk stops skipping headers, so the join runs over non-rows",
                '        if cells[1] in {"Kind", "---"}:',
                "        if False:",
                "the coverage walk finds both tables' component rows",
            ),
            # The measurement guard. Counting every marketing row instead of the largest identical
            # group answers a different question, and it drifts in the direction that looks right.
            Mutation(
                "the identical-string measurement widens to every marketing row",
                "    return max(counts.values())",
                "    return len(marketing)",
                "the identical-Build-from count is measured over marketing rows only",
            ),
            Mutation(
                "a marked block with no bands parses instead of raising",
                "    if not bands:",
                "    if False:",
                "a marked block with no band rows parsed instead of raising",
            ),
            # The silence direction: inverted, the rule fires on the shipped sequence.
            Mutation(
                "the tone rule inverts and demands two consecutive bands share a tone",
                "        if prev.tone == nxt.tone:",
                "        if prev.tone != nxt.tone:",
                "a correct section is silent",
            ),
        ),
    ),
    # #108 item E. Five of these seven break a rule by making it fire MORE — the direction that gets
    # a rule switched off. A link audit that reports every auth-gated page and every `mailto:` as a
    # dead link is deleted within a day, taking every genuine 404 with it.
    Guard(
        name="link_audit",
        subject="plugins/qa-flow/scripts/link_audit.py",
        selftest="plugins/qa-flow/scripts/link_audit.py",
        needs=("plugins/qa-flow/scripts/crawl_collector.js",),
        mutations=(
            Mutation(
                "the broken-link boundary moves to 500, so every 404 goes quiet",
                "                elif isinstance(status, int) and status >= 400:",
                "                elif isinstance(status, int) and status >= 500:",
                "a 404 target is a broken link",
            ),
            Mutation(
                "the unauthenticated carve-out widens past 401/403 and swallows a dead link",
                "UNAUTHENTICATED_STATUSES = frozenset({401, 403})",
                "UNAUTHENTICATED_STATUSES = frozenset({401, 403, 410})",
                "a 410 is still a broken link",
            ),
            Mutation(
                "the scheme test becomes a substring match, exempting any href containing 'mailto:'",
                "    match = SCHEME.match(href.strip())",
                '    match = re.search(r"([a-zA-Z][a-zA-Z0-9+.\\-]*):", href.strip())',
                "an href CONTAINING 'mailto:' in a query is still judged",
            ),
            Mutation(
                "the rel test becomes a substring match, so a `noopenerfoo` typo passes as safe",
                '                if not tokens & {"noopener", "noreferrer"}:',
                '                if "noopener" not in str(link.get("rel") or "").lower():',
                "a lookalike rel token does not satisfy it",
            ),
            Mutation(
                # This one fires MORE, and on the single most common spelling of the fix.
                "`split()` goes, so the whole rel is one token and `noopener noreferrer` reports a leak",
                '                tokens = {tok for tok in str(link.get("rel") or "").lower().split() if tok}',
                '                tokens = {str(link.get("rel") or "").lower()}',
                "rel='noopener noreferrer' satisfies the rule",
            ),
            Mutation(
                "`noreferrer` stops counting, so a correctly-severed link reports a leak",
                '                if not tokens & {"noopener", "noreferrer"}:',
                '                if not tokens & {"noopener"}:',
                "rel='noreferrer' satisfies the rule",
            ),
            Mutation(
                "the opener rule moves out of reach, where a real leak can never be reported",
                '            if str(link.get("target") or "").lower() == "_blank":',
                "            if False:",
                "target=_blank with no rel is an opener leak",
            ),
            Mutation(
                "the top-of-document carve-out goes, so every `#` and `#top` reports dead",
                "            if fragment.lower() in TOP_FRAGMENTS:",
                "            if False:",
                "is the top of the document, not a dead fragment",
            ),
            Mutation(
                "an un-inventoried anchor list stops being distinguished from an empty one",
                "            if anchors is None:",
                "            if anchors is None or not anchors:",
                "a page with an EMPTY anchor list is still judged",
            ),
            Mutation(
                "the document carve-out widens to every response, so no missing asset is reported",
                '            if str(response.get("resourceType", "")) == DOCUMENT_RESOURCE:',
                "            if True:",
                "a 404 sub-resource is a missing asset",
            ),
            Mutation(
                "findings group by rule alone, collapsing unrelated defects into one",
                "        key = (rule, target)",
                '        key = (rule, "")',
                "two DIFFERENT broken targets are two findings",
            ),
            Mutation(
                "an inventory with no base origin is judged instead of refused",
                '    if not origin_of(str(data.get("base") or "")):',
                "    if False:",
                "no base origin, so internal cannot be told from external",
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
    # design-flow #160. THREE of these ten are caught by a fixture whose job is to stay SILENT, and
    # those are the ones worth having: this check stands between an agent and a user's repo, and
    # every rule it carries has an obvious over-broad form. `bg-primary` is a role token AND a
    # string ending in a primitive's suffix; an ERB comment naming `--color-x:` is prose AND a
    # custom-property declaration; `# do not remove` is a comment AND a line ending in `do`. Flag
    # the wrong half of any pair and variant mode reports findings on every correct set it is
    # given, which is how a checker gets switched off wholesale.
    Guard(
        name="variant_conformance",
        subject="plugins/design-flow/scripts/variant_conformance.py",
        selftest="plugins/design-flow/scripts/variant_conformance.py",
        # It RUNS the #157 detector rather than reimplementing it, and the detector in turn imports
        # `rendered_conformance` for the shared palette-step definition. Without both, every mutant
        # dies at import and reads as "caught" by a traceback instead of by the fixture named below.
        needs=("plugins/design-flow/scripts/llm_tell_detector.py",
               "plugins/design-flow/scripts/rendered_conformance.py",
               "plugins/design-flow/scripts/conformance_collector.js"),
        mutations=(
            Mutation(
                "the role layer is read as primitives, so every conformant variant is a finding",
                "        if opening.group(1):",
                "        if False:",
                "role tokens are NOT flagged as primitives",
            ),
            Mutation(
                "an ERB comment naming a custom property becomes a styling violation",
                "        if tells.COMMENT_LINE.match(line):\n            continue\n"
                "        for pattern, what in STYLING:",
                "        if False:\n            continue\n        for pattern, what in STYLING:",
                "a comment naming a custom property is NOT a finding",
            ),
            Mutation(
                "an unresolvable pack becomes a silent skip instead of a finding",
                "    if not theme:",
                "    if False:",
                "an unresolvable pack is a finding, not a skip",
            ),
            Mutation(
                "the distinctness rule stops noticing two variants with one arrangement",
                "        twin = signatures.get(signature)",
                "        twin = None",
                "two variants differing only in copy fire",
            ),
            Mutation(
                "a set of one passes, so variant mode degenerates to the yes/no it replaces",
                "    if len(entries) < 2:",
                "    if len(entries) < 1:",
                "a set of one fires",
            ),
            Mutation(
                "the rationale requirement is dropped and the choice becomes aesthetic again",
                '        if not str(entry.get("rationale") or "").strip():',
                "        if False:",
                "a blank rationale fires",
            ),
            Mutation(
                "the undeclared-partial direction is dropped, so discard misses a leftover",
                '        if entry == MANIFEST or entry in declared or not entry.endswith(".erb"):',
                "        if True:",
                "an undeclared partial in the set fires",
            ),
            Mutation(
                "the route tracker stops popping, so a CLOSED dev block launders a later route",
                "        if _CLOSES.match(line) and stack:",
                "        if False and stack:",
                "a closed development block does not launder a later route",
            ),
            Mutation(
                "an empty scaffolding directory reads as a clean pass",
                "    if not set_dirs:",
                "    if False:",
                "an empty variants directory is fatal too",
            ),
            Mutation(
                "comments re-enter the route tracker, so `# do` unbalances the stack",
                '        if line.lstrip().startswith("#"):\n            continue',
                "        if False:\n            continue",
                "a comment does not unbalance the block tracker",
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
        #
        # The agents are named as a DIRECTORY, for the reason build_coverage's `references` is: the
        # eleven files were hand-typed, `claim-verifier.md` was added later and never appended, and
        # the staged mutant therefore reconciled a full tier table against ten agents -- reporting
        # the row for the missing one as stale. `run_baseline` (#422) surfaced it as INERT the day
        # it landed. A hand-typed list of a directory's contents goes quiet the first time the
        # directory grows, which is the coverage-gap class inside the harness built to catch it.
        needs=(
            "plugins/rails-flow/reference/model-tiers.md",
            "plugins/rails-flow/commands/handoff.md",
            # The DIRECTORY, not ten hand-listed agent files. The list omitted
            # `claim-verifier.md` when v1.52.0 added it, so the staged mutant lacked an agent the
            # tier table names -- and `check_handoff` correctly reported a stale row on its own
            # UNMUTATED baseline. Every mutation then read as "caught" by that, proving nothing.
            "plugins/rails-flow/agents",
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
    # #158. The routing regex is the mutation that matters here. Its whole job is telling a real
    # dispatch entry apart from prose that happens to name the file, and getting that wrong in the
    # LOOSE direction is silent: every reference looks routed and the gate reports clean forever.
    # That is precisely how `fidara-design/references/coverage.md` hid at depth 2 while two other
    # reference files name it in passing.
    Guard(
        name="check_skill_routing",
        subject="scripts/check_skill_routing.py",
        selftest="scripts/check_skill_routing.py",
        mutations=(
            Mutation(
                "the `references/` anchor becomes optional, so prose naming a file counts as routing",
                'REF_PATH_RE = re.compile(r"(?:\\./)?references/([A-Za-z0-9._-]+\\.md)")',
                'REF_PATH_RE = re.compile(r"(?:\\./)?(?:references/)?([A-Za-z0-9._-]+\\.md)")',
                "a bare prose mention is NOT routing",
            ),
            Mutation(
                "the unrouted rule stops reporting, so an orphaned reference is clean",
                "    for missing in sorted(present - routed):",
                "    for missing in []:",
                "an unrouted reference is a finding",
            ),
            Mutation(
                "the dead-link rule stops reporting, so a router pointing at nothing is clean",
                "    for dead in sorted(routed - present):",
                "    for dead in []:",
                "a dead reference link is a finding",
            ),
            Mutation(
                "the Level-2 budget goes off-by-one and fires on a compliant 500-line body",
                "    if line_count > MAX_SKILL_LINES:",
                "    if line_count >= MAX_SKILL_LINES:",
                "a body exactly AT the budget is silent",
            ),
            Mutation(
                "a skill directory with no SKILL.md becomes a silent skip instead of an error",
                '        raise Unreadable(f"{name}/: no SKILL.md")',
                "        return [], 0",
                "skipped instead of raising",
            ),
        ),
    ),
   # rails-flow #130. FIVE of these eleven break a fixture whose job is to stay SILENT, because the
   # centrepiece is a SIMILARITY rule and similarity rules are false-positive machines: a brief and
   # the PRD it indexes describe the same product in the same words to the same reader. A
   # blockquote is quotation, a fenced block is quoted code, a coverage-map cell quotes the
   # source's own heading BY DESIGN, and shared product nouns are not a copy. Two more guard the
   # carve-outs that keep the prose rules usable at all.
   Guard(
       name="check_brief",
       subject="plugins/rails-flow/scripts/check_brief.py",
       selftest="plugins/rails-flow/scripts/check_brief_selftest.py",
       # The self-containment rules are IMPORTED from check_handoff rather than copied -- "what
       # counts as a reference to the conversation" is one decision, and two copies of it would be
       # the second-source-of-truth failure this checker exists to police. check_criteria comes
       # along because check_handoff imports it.
       deps=(
           "plugins/rails-flow/scripts/check_handoff.py",
           "plugins/rails-flow/scripts/check_criteria.py",
       ),
       # Read, not imported. The selftest's last checks run the REAL command against this
       # checker's section contract and FAIL rather than skip when absent.
       needs=("plugins/rails-flow/commands/brief.md",),
       mutations=(
           Mutation(
               "the duplication threshold collapses and shared vocabulary reads as a copy",
               "DUP_WINDOW = 12",
               "DUP_WINDOW = 4",
               "eleven shared words is shared vocabulary",
           ),
           Mutation(
               "blockquotes stop being exempt, so quoting the user is duplication",
               '                and not stripped.startswith(">")',
               "                and True",
               "a blockquote of the same words is attributed quotation",
           ),
           Mutation(
               "table rows stop being exempt, so the citation mechanism flags itself",
               '                and not stripped.startswith("|")',
               "                and True",
               "a table row quoting the source's own heading",
           ),
           Mutation(
               "fenced blocks stop being exempt from the duplication rule",
               "                not fenced and bool(stripped)",
               "                bool(stripped)",
               "a fenced block of the same words is quoted code",
           ),
           Mutation(
               "the heading disqualifier loses its plural (the real bug a fixture found)",
               'rf"\\b{re.escape(d)}s?\\b"',
               'rf"\\b{re.escape(d)}\\b"',
               "is not the scope section",
           ),
           Mutation(
               "the mode cross-check widens back to the whole line and can never fire",
               'clause = re.split(r"[.|]", line[found.end():], maxsplit=1)[0][:60]',
               "clause = line",
               "the mode letter and the mode word disagree",
           ),
           Mutation(
               "a locator stops being resolved, so a citation only has to name a real file",
               "                if _collapse(locator) not in _collapse(body):",
               "                if False:",
               "a reference whose locator is not in the file",
           ),
           Mutation(
               "an `answered` row stops needing a source",
               '        if row.state == "answered" and not SOURCE_REF_RE.search(row.source):',
               "        if False:",
               "an `answered` row citing no source",
           ),
           Mutation(
               "an open question stops needing an owner",
               "        if not OWNER_RE.search(_strip_code(text)):",
               "        if False:",
               "an open question with no owner",
           ),
           Mutation(
               "TBD stops being carved out of Open questions (the false-positive direction)",
               "            if section is open_questions:",
               "            if False:",
               "TBD inside the open questions is that section's job",
           ),
           Mutation(
               "the `- None.` carve-out stops covering an explicitly empty open-questions section",
               "    if body and all(NONE_ONLY_RE.match(line) for line in body.splitlines()):",
               "    if False:",
               "an explicitly empty open-questions section is a real answer",
           ),
           Mutation(
               "a coverage gap stops needing to be recorded anywhere",
               "    if open_questions.bullets():",
               "    if True:",
               "a gap in the map and no open question recorded",
           ),
           Mutation(
               "a cited `D-nnn` stops being resolved against the decisions file",
               "        if num not in defined:",
               "        if False:",
               "a cited `D-nnn` the decisions file does not define",
           ),
           Mutation(
               "the non-goals hedge list stops applying, so `- None.` is a non-goal",
               '            if _collapse(_strip_code(text)).strip(".") not in HEDGES '
               "and len(_tokens(text)) >= 3]",
               "            if True]",
               "non-goals that say nothing",
           ),
       ),
   ),
    Guard(
        name="check_manifest_paths",
        subject="scripts/check_manifest_paths.py",
        selftest="scripts/check_manifest_paths.py",   # --selftest lives in the module itself
        # No `needs`: every fixture builds its own synthetic plugin in a tempdir. A fixture reaching
        # for the real `plugins/` tree would die here on a missing corpus and read as a caught
        # mutation, when a crash is not a verdict.
        mutations=(
            Mutation(
                "agreement becomes unconditional, so no manifest path is ever phantom",
                '    return named.startswith(entry + "/")   '
                "# the manifest waits on a directory written into",
                "    return True",
                "a phantom applies_when path is reported",
            ),
            Mutation(
                "prose leaks into the corpus, so a path mentioned in a sentence vouches for itself",
                '            out.append((path, [fenced(path.read_text(encoding="utf-8"))]))',
                '            out.append((path, [path.read_text(encoding="utf-8")]))',
                "a path named only in prose does not count as agreement",
            ),
            Mutation(
                "docstrings leak in, which is the exact shape that hid `qa/routes.json`",
                "            and id(n) not in docstrings]",
                "            ]",
                "a path named only in a docstring does not count as agreement",
            ),
            Mutation(
                "a bare `dir/*` writer starts vouching for every child name anyone invents",
                '                    while token.endswith("/*") or token.endswith("/**"):',
                "                    while False:",
                "a bare `dir/*` writer does not vouch for an invented child",
            ),
            # The two coverage counters. A rule reporting "no findings" over nothing examined is
            # the vacuous pass this repo keeps hitting, so each half is mutated separately —
            # one guard for both would let either go quiet behind the other.
            Mutation(
                "a manifest declaring no paths stops being reported",
                "    if not entries:",
                "    if False:",
                "a manifest declaring no paths is reported, not passed",
            ),
            Mutation(
                "an empty corpus stops being reported, so a broken scan reads as a clean manifest",
                "    if not corpus:",
                "    if False:",
                "a plugin whose surfaces name no paths is reported",
            ),
        ),
    ),
    Guard(
        name="generation_gate",
        subject="plugins/design-flow/scripts/generation_gate.py",
        selftest="plugins/design-flow/scripts/generation_gate.py",   # --selftest lives in the module
        # No `needs`: every fixture builds its own config in a tempdir. This path spends real money,
        # so each mutation removes exactly ONE refusal and names the fixture that catches it -- a
        # mutation caught by the wrong fixture would mean some other check is doing the work.
        mutations=(
            Mutation(
                # An unpriced rung treated as free makes the ceiling unreachable: every unpriced
                # model costs nothing, so the budget check cannot refuse -- a gate that cannot fail,
                # guarding the one thing here with a bill attached.
                "an unpriced rung stops refusing, so the budget compares against nothing",
                '        if rung.get("cost_usd") is None:',
                "        if False:",
                "an unpriced rung is refused",
            ),
            Mutation(
                # #161's shape with a bill attached: a ceiling documented and unenforced.
                "the budget comparison inverts, so spending past the ceiling is approved",
                "    if spent + projected > ceiling:",
                "    if False:",
                "projected cost exceeds the ceiling",
            ),
            Mutation(
                "a free-typed prompt is silently accepted instead of rejected",
                '    if "prompt" in request:',
                "    if False:",
                "a free-typed prompt",
            ),
            Mutation(
                # Climbing with no stated check is how "best output" becomes "the agent liked it".
                "the ladder climbs with no acceptance check, so a reroll needs no justification",
                '    if attempt > 0 and not config.get("acceptance", {}).get(surface):',
                "    if False:",
                "climbing with no acceptance check",
            ),
            Mutation(
                # The DEFAULT install has no aggregator. If this stops refusing, the common case
                # walks into a provider that is not there.
                "a missing aggregator stops refusing, so the default install proceeds",
                "    if not name:",
                "    if False:",
                "no aggregator configured",
            ),
            Mutation(
                # `avoid` is the field most often skipped and the one that matters most to a
                # curated SET: without it the family drifts by well-meaning reuse.
                "an empty field passes, so a manifest can be present without being usable",
                "            if value in (None, \"\", [], {}):",
                "            if value is None and False:",
                "an entry with no avoid",
            ),
            Mutation(
                # The most expensive mistake available here: re-buying an asset the project owns.
                "a library is never required to have been searched, so owned assets get re-bought",
                '    if not miss or not miss.get("searched_for") or not miss.get("why_no_fit"):',
                "    if False:",
                "a library exists but was not searched",
            ),
            Mutation(
                # The manifest contradicting the miss is the sharper case -- generating anyway
                # forks the surface's look instead of filling a gap.
                "a covered surface stops being detected, so the same surface forks in two looks",
                '        if entry.get("surface") == surface and entry.get("kind", "static") == kind:',
                "        if False:",
                "...the manifest already covers this surface",
            ),
            Mutation(
                # The gap the reference survey exposed: "calm, abstract" renders as monochrome ink
                # OR as rounded flat-vector characters, and without a named style both pass.
                "any style string is accepted, so one pack can drift across two looks",
                "    if style not in STYLES:",
                "    if False:",
                "a style outside the taxonomy",
            ),
            Mutation(
                # Both free tiers must be ruled out EXPLICITLY. Drop this and a request reaches the
                # paying path while claiming a refusal it never made.
                "a free tier stops needing an explicit refusal, so generation is reachable first",
                '        why = refusal.get(f"tier_{tier}_why_not")',
                '        why = "assumed"',
                "tier 1 not ruled out",
            ),
        ),
    ),
    Guard(
        name="next_action",
        subject="plugins/rails-flow/scripts/next_action.py",
        selftest="plugins/rails-flow/scripts/next_action.py",   # --selftest lives in the module
        # No `needs`: every fixture is a dict literal or a tempdir. The mutations target the four
        # decisions that carry real consequence — overruling the breaker, ignoring the budget,
        # letting an unclassified action through, and accepting a policy that escalates nothing.
        mutations=(
            Mutation(
                # ESCALATE-AND-CONTINUE, also found by a real run: the driver stopped to ask about a
                # scope-flagged enhancement while a QA pass needing no permission sat beside it.
                # Over-asking is the failure the matrix exists to avoid, wearing the clothes of caution.
                "the driver stops preferring autonomous work, so one escalation blocks the run",
                '        if c["rights"] == "decide":',
                "        if False:",
                "a scope-flagged issue does not block available autonomous work",
            ),
            Mutation(
                # THE SCOPE DOOR, found by a real run: an issue whose own body called it "a distinct
                # auth-hardening feature" routed to DECIDE, because every open issue becomes
                # `fix-issue` and that needs only `pick-next-backlog-item`.
                "an item's nature stops upgrading the right, so scope enters via the issue door",
                "    if labels and SCOPE_LABELS & {str(l).lower() for l in labels}:",
                "    if False:",
                "an issue labelled enhancement escalates",
            ),
            Mutation(
                # The worst one available: a driver that keeps working after the safety system said
                # stop. Two disagreeing stop systems mean the permissive one wins.
                "the breaker stop is ignored, so the driver works past its own safety system",
                '    if state.get("run_stopped"):',
                "    if False:",
                "a stopped run stops, even with issues waiting",
            ),
            Mutation(
                "the budget stop is ignored, so a spent run keeps spending",
                '    if state.get("budget_exhausted"):',
                "    if False:",
                "budget beats a full backlog",
            ),
            Mutation(
                # An unclassified action defaulting to `decide` is how a policy grows permissive by
                # omission -- every action nobody thought about becomes autonomous.
                "an unclassified action becomes decidable, so the policy grows permissive by omission",
                '    return "unknown"',
                '    return "decide"',
                "an action absent from BOTH lists must not be treated as decidable",
            ),
            Mutation(
                # A policy with no escalate list is full autonomy wearing a config file.
                "a policy that escalates nothing is accepted",
                '    if not isinstance(loaded, dict) or not loaded.get("escalate"):',
                "    if False:",
                "a policy with no `escalate` list should be refused",
            ),
        ),
    ),
    Guard(
        name="compose_state",
        subject="plugins/rails-flow/scripts/compose_state.py",
        selftest="plugins/rails-flow/scripts/compose_state.py",   # --selftest lives in the module
        # No `needs`: the fixtures are literals and a tempdir. Both mutations target a decision the
        # driver previously made by accident -- what order the backlog is in, and what it refuses to
        # start -- because "first element wins" IS a prioritisation policy, just an unstated one.
        mutations=(
            Mutation(
                "the actionability filter goes, so blocked work is picked and burns attempts",
                "        if blocked:",
                "        if False:",
                "blocked issues excluded",
            ),
            Mutation(
                # Ordering was previously whatever the caller typed. Unsorting it puts an
                # unprioritised issue first, which is how forgetting a label promotes work.
                "the stated order goes, so priority stops deciding what is next",
                '    actionable.sort(key=lambda e: (priority_rank(set(e["labels"])), e["number"]))',
                "    pass",
                "priority then age",
            ),
        ),
    ),
    Guard(
        name="generate_asset",
        subject="plugins/design-flow/scripts/generate_asset.py",
        selftest="plugins/design-flow/scripts/generate_asset.py",   # --selftest lives in the module
        # `needs` the sibling it imports. Without it the staged mutant cannot import
        # generation_gate, the selftest dies on ModuleNotFoundError, and every mutation reads as
        # "caught" while proving nothing -- a crash is not a verdict, and this guard demonstrated it.
        needs=("plugins/design-flow/scripts/generation_gate.py",),
        # Every fixture is a tempdir and NOTHING reaches the network. A test that needed
        # a provider would not be a test -- it would be a bill. Each mutation removes one thing that
        # stands between a request and someone's card.
        mutations=(
            Mutation(
                # A critic with no criterion produces an OPINION, and an opinion recorded as a
                # verdict is worse than no verdict -- it looks like the check ran.
                "a surface with no acceptance check is still critiqued, so opinion becomes verdict",
                "    if not criterion:",
                "    if False:",
                "a surface with no acceptance check should refuse to be critiqued",
            ),
            Mutation(
                # A verdict nobody can review (accept) or act on (reject) is not a verdict.
                "a verdict needs no reason, so accepts cannot be reviewed and rejects not acted on",
                "    if not why.strip():",
                "    if False:",
                "verdict with no reason should be refused",
            ),
            Mutation(
                # The agent path never calls an API. Demanding a key from it refused the one
                # zero-cost route for a credential it had no use for -- which is what shipped until
                # the adapter was resolved before the preflight.
                "the agent path demands an API key it never uses",
                '    key = "" if name in KEYLESS else preflight_key(config.get("api_key_env", ""), root)',
                '    key = preflight_key(config.get("api_key_env", ""), root)',
                "the agent path needs no API key (refused instead",
            ),
            Mutation(
                # An agent-authored asset must get NO easier route into the manifest than a bought
                # one, or "the agent wrote it" becomes the way past every refusal.
                "a raster recorded as vector is accepted, so `.svg` stops meaning vector",
                '    if kind == "vector" and ext != "svg":',
                "    if False:",
                "a raster recorded as vector is still refused",
            ),
            Mutation(
                # Two shipped messages promised `.env` worked while nothing read the file, so a
                # user who followed the instruction got "not set" and concluded the tool was broken.
                "the .env fallback goes, so a promised location silently stops working",
                "    if raw is None and root is not None:",
                "    if False:",
                "a key in .env is found",
            ),
            Mutation(
                # A shell export is the more deliberate act. If a stale file could override it,
                # someone debugging a key would be overridden by something they had forgotten.
                "the environment stops winning, so a stale .env overrides a deliberate export",
                "    if raw is None and root is not None:",
                "    if root is not None:",
                "the environment beats .env",
            ),
            Mutation(
                # The load-bearing property: the gate is RE-RUN here, never trusted from the caller.
                # Drop it and a hand-written {"approved": true} bypasses every refusal at once --
                # library, tier precondition, composed prompt, budget ceiling.
                "the gate stops being re-run, so a forged approval reaches the provider",
                "    approval = decide(root, request)  # produce(): RE-RUN, never trusted from the caller",
                '    approval = request if request.get("approved") else decide(root, request)',
                "expected a Refusal, got Unusable",
            ),
            Mutation(
                # A placeholder key calls the provider and fails there with an error that reads like
                # an outage, sending someone to debug the wrong system.
                "a placeholder key is treated as real, so the call fails at the provider",
                '    if PLACEHOLDER_RE.match((raw or "").strip()):',
                "    if False:",
                "should be rejected as a placeholder",
            ),
            Mutation(
                "an absent key stops being caught, so the default install walks into the call",
                "    if raw is None:",
                "    if False:",
                "an absent key is distinguished from a placeholder",
            ),
            Mutation(
                # #599. `pen` shells out to a local CLI carrying its own auth, so a key is
                # meaningless to it -- and demanding one refuses a zero-cost route for a credential
                # it will never use, which is exactly what happened to the agent rung before.
                "the pen rung stops being keyless, so a local CLI is refused for a missing API key",
                'KEYLESS = frozenset({"agent", "pen"})',
                'KEYLESS = frozenset({"agent"})',
                "...and is keyless, like the agent",
            ),
            Mutation(
                # Exit 0 with no artefact is not a completion -- the same rule the plan applies to
                # its own rows. Accepting it records a asset that is not on disk.
                "exit 0 with no image counts as success, so an absent asset is recorded",
                "        if not img.is_file():",
                "        if False:",
                "exit 0 with no image is refused, not recorded",
            ),
            Mutation(
                # A manifest that grows unusable rows is worse than one that refuses to grow: the
                # asset looks findable and still gets re-generated by whoever could not tell.
                "incomplete manifest rows are written, so the library grows rows nobody can act on",
                "    if missing:",
                "    if False:",
                "a row missing file should be refused",
            ),
        ),
    ),
    Guard(
        # #600/#601. Two rules carry this: an absent surface degrades SILENTLY to today's
        # behaviour, and the intent pass never blocks. Both fail open in a way that looks fine --
        # a tier that stopped the run, or an advisory that became a gate, would each be discovered
        # by a user rather than by us.
        name="pen_compose",
        subject="plugins/design-flow/scripts/pen_compose.py",
        selftest="plugins/design-flow/scripts/pen_compose.py",   # --selftest lives in the module
        mutations=(
            Mutation(
                # A tier that is off by default is a tier nobody discovers -- the maintainer
                # decision on #600, which an inverted default would quietly reverse.
                "the tier defaults to off, so nobody ever discovers it",
                '    want = str(config.get("exploration_surface") or "auto").lower()',
                '    want = str(config.get("exploration_surface") or "none").lower()',
                "an unconfigured project still gets the tier",
            ),
            Mutation(
                # `none` is a real project choice, not a fallback. Ignoring it changes how a shared
                # repo builds UI on whichever machine happens to have pen installed.
                # Note the assertion this lands on: with the branch gone, `none` matches no
                # surface name either, so it still reports unusable -- only the REASON changes. The
                # harness caught that the obvious fixture passes coincidentally, which is precisely
                # what `expects` exists to prevent.
                "an explicit `none` stops being honoured, so the reason misdescribes the project",
                '    if want == "none":',
                "    if False:",
                "...and says so rather than looking broken",
            ),
            Mutation(
                # A requested surface that is absent must NOT silently become another one: an
                # operator who asked for the headless CLI did so for a reason.
                "a requested surface silently falls through to a different one",
                '    if want in ("auto", "pencil-mcp") and mcp_available:',
                "    if mcp_available:",
                "a requested surface that is absent does not silently use another",
            ),
            Mutation(
                # THE tier rule: raw colour in a composition forks the brand silently, because it
                # looks right today and stops following the pack tomorrow.
                "raw colours in a composition stop being reported",
                '    if raw:',
                "    if False:",
                "a literal colour is reported",
            ),
        ),
    ),
    Guard(
        # #603. A generated library's whole safety is that regeneration is predictable: identical
        # bytes for an unchanged pack, and the designer's own work untouched. Each mutation below
        # breaks one of those silently -- the file still looks like a library afterwards.
        name="pen_library",
        subject="plugins/design-flow/scripts/pen_library.py",
        selftest="plugins/design-flow/scripts/pen_library.py",   # --selftest lives in the module
        # The BRAND PACK is a dependency, not incidental data: the selftest generates from the real
        # fidara theme, so without it every mutation dies on `no theme.css` -- a crash, which is not
        # a verdict. The harness caught that on the first run and refused to score any of them.
        needs=("plugins/design-flow/scripts/pen_to_svg.py",
               "plugins/design-flow/scripts/brand_pack_lint.py",
               "plugins/design-flow/brands/fidara/theme.css",
               "plugins/design-flow/brands/fidara/brand.json",
               # EVERY FILE `build()` READS. This list has now been short three times running --
               # theme.css, then components.md, then component-shapes.json -- and each time the
               # symptom was identical: every mutation died on `Unreadable`, a crash rather than a
               # verdict, and the harness refused to score any of them. The rule to carry forward is
               # that a guard's `needs` is not "the other scripts" but "everything the subject
               # opens", data included.
               "skills/fidara-design/references/components.md",
               "skills/fidara-design/references/component-shapes.json"),
        mutations=(
            Mutation(
                # THE reason this writes a file instead of driving the MCP. A random id per run
                # breaks every `ref` in every existing document, and a dangling ref is not an error.
                "ids lose their generated prefix, so nothing is recognised as ours again",
                '    return f"fm-{cleaned}"',
                "    return cleaned",
                "ids are derived from names, not random",
            ),
            Mutation(
                # The file is also the scratchpad. Dropping the non-generated children deletes the
                # designer's compositions every time the brand pack moves.
                "a rebuild stops preserving authored nodes, so it eats the designer's work",
                '    kept = [c for c in existing.get("children") or [] if not is_generated(c)]',
                "    kept = []",
                "regenerating PRESERVES the designer's composition",
            ),
            Mutation(
                # A theme-less value is what pen's own SetVariables silently drops, taking the light
                # theme with it -- after which artwork exports black rather than erroring.
                "a theme mode stops being named, so the light theme is silently droppable",
                '            {"value": resolve(role, light), "theme": {AXIS: LIGHT}},',
                '            {"value": resolve(role, light)},',
                "every role names BOTH theme modes",
            ),
            Mutation(
                # Comparing every variable makes a scratch colour read as drift -- a check that
                # fires on correct input, which is a check that gets switched off.
                "the drift check widens to every variable, so a scratch colour reads as drift",
                '    return {"variables": {k: v for k, v in (doc.get("variables") or {}).items() if k in ours},',
                '    return {"variables": {k: v for k, v in (doc.get("variables") or {}).items()},',
                "a composition alongside the library is NOT drift",
            ),
        ),
    ),
    Guard(
        # #602. The compiler's value is entirely in what it REFUSES: a degraded compile looks
        # finished, so nobody re-checks it. Every mutation below turns a refusal into an
        # approximation, which is the failure this file exists to make impossible.
        name="pen_to_svg",
        subject="plugins/design-flow/scripts/pen_to_svg.py",
        selftest="plugins/design-flow/scripts/pen_to_svg.py",   # --selftest lives in the module
        # No `needs`: the fixtures are hand-authored dicts and the compiler touches no filesystem
        # beyond the file named on the command line, which the selftest never supplies.
        mutations=(
            Mutation(
                # The whole point. A literal hex compiles into the asset, so illustration stops
                # recolouring with the brand pack and `design-auditor` refuses it downstream --
                # after someone has already shipped it into a component.
                "a literal colour is accepted, so the asset stops following the brand pack",
                '    if text.startswith("$"):\n        return f"var({text[1:]})"',
                '    if True:\n        return text',
                "a literal hex fill",
            ),
            Mutation(
                # SVG's <ellipse> has no partial sweep, so emitting one silently FILLS IN the
                # missing arc -- a change to the artwork that renders as though it were intended.
                "an arc ellipse is emitted whole, so a donut silently becomes a disc",
                '        if n.get("innerRadius") or n.get("startAngle") or n.get("sweepAngle"):',
                "        if False:",
                "an arc ellipse",
            ),
            Mutation(
                # A conic gradient approximated by a linear ramp is the same class: plausible
                # output, different design, and nothing says so.
                "a conic gradient is approximated by a linear ramp",
                '        raise Refusal(\n            f"node {node_id!r}: {prop} is an {kind!r} (conic) gradient',
                '        defs.append("")\n        _unused = (\n            f"node {node_id!r}: {prop} is an {kind!r} (conic) gradient',
                "a conic gradient",
            ),
            Mutation(
                # Rotation is CCW about the node's TOP-LEFT corner. Dropping the pivot spins the
                # shape about the canvas origin and flings it off-canvas -- which reads as "the
                # compiler lost my artwork" rather than as an axis bug.
                "rotation loses its pivot, so rotated artwork flies off the canvas",
                '        out.append(f\'  <g transform="rotate({-num(rot)} {x} {y})">\')',
                '        out.append(f\'  <g transform="rotate({-num(rot)})">\')',
                "rotation pivots on the node's own top-left",
            ),
            Mutation(
                # A dimension bound to a variable has no value at compile time. Coercing it would
                # produce a shape of the wrong size rather than an error.
                "a variable-bound dimension is coerced, so the shape compiles at the wrong size",
                '    if isinstance(v, str) and v.startswith("$"):',
                "    if False:",
                "a variable-bound dimension",
            ),
        ),
    ),
    Guard(
        name="asset_plan",
        subject="plugins/design-flow/scripts/asset_plan.py",
        selftest="plugins/design-flow/scripts/asset_plan.py",   # --selftest lives in the module
        # No `needs`: the fixtures are literals and tempdirs, and the one run_plan fixture points at
        # a NONEXISTENT executor on purpose, so no mutation can reach a provider from here.
        mutations=(
            Mutation(
                # The join that makes research MEAN something downstream. Without it a project can
                # research monochrome ink line-work and brief a 3D render, and nothing notices --
                # the record becomes a box that was ticked rather than a decision anything honours.
                "briefs stop being held to the researched style, so one set mixes families",
                '            off = [s for s, b in briefs.items() if b.get("style") and b["style"] != chosen]',
                "            off = []",
                "a brief that ignores the researched style is reported",
            ),
            Mutation(
                # Exit 0 is not "done": the agent path exits 0 with a BRIEF. Reading the code alone
                # marked rows done with no file on disk -- the exact "recorded from what was
                # attempted" failure this file's own docstring forbids.
                "exit 0 alone marks a row done, so a plan completes with no assets on disk",
                "            if produced and (root / produced).is_file():",
                "            if True:",
                "an agent brief is awaiting-agent, not done",
            ),
            Mutation(
                # Research settles the STYLE, and the style settles which assets exist at all. A
                # plan written without it looks identical to one written with it -- every row
                # complete, and nothing recording that the look came from the median.
                "research stops being required, so the plan is costed against a look nobody chose",
                "    path = root / RESEARCH_PATH",
                "    path = Path(__file__)",
                "a missing research record is reported",
            ),
            Mutation(
                # A hero still and the motion loop that animates it are one artefact in two files.
                # Row-greedy buys the loop alone, which is worse than buying neither: you pay for
                # something that cannot be used.
                "groups stop being atomic, so half a set is bought and cannot be used",
                "        if cost <= remaining:",
                "        if True:",
                "a group that does not fit whole is skipped entirely",
            ),
            Mutation(
                # A library planned against last month's brief is quietly incomplete: every row
                # done, status clean, and the new surfaces have no rows at all.
                "PRD drift stops being detected, so a stale plan reads as a finished one",
                '    if fingerprint(path) != prd.get("sha256"):',
                "    if False:",
                "an edited PRD is reported",
            ),
            Mutation(
                # Without reconciliation the plan and the library drift apart, and the gap between
                # them stops meaning "remaining work".
                "unplanned assets stop being reported, so ad-hoc work never reaches the plan",
                '            for e in owned if (e.get("surface"), e.get("kind", "static")) not in planned]',
                '            for e in owned if False]',
                "an unplanned asset is reported",
            ),
            Mutation(
                # Idempotency is what stops a re-run re-buying the library. Without it, every
                # `--run` pays again for everything already on disk.
                "a done row is re-run, so every pass re-buys the whole library",
                '        if row.get("status") == "done":',
                "        if False:",
                "a done row is skipped entirely",
            ),
            Mutation(
                # The scaffold CREATES an empty plan, so this is the state of every fresh setup.
                # Blessing it says the planning is finished before it has started.
                "an empty plan passes review, so an unplanned project reads as finished",
                # Anchored with its comment: `render_plan` grew a second `if not rows:` at the same
                # indent, and a bare anchor then matched twice. An ambiguous anchor is a mutation
                # that silently moves to a different line, so the harness refuses it outright.
                "    if not rows:\n        # An empty plan is UNPLANNED, not finished.",
                "    if False:\n        # An empty plan is UNPLANNED, not finished.",
                "an empty plan is reported as unplanned",
            ),
            Mutation(
                "two rows for one slot pass, so a surface forks into two looks",
                "        if key in seen:",
                "        if False:",
                "two rows for one surface+kind is reported",
            ),
            Mutation(
                # Moves the finding from review time back to run time, which is after the spend.
                "the brief cross-check goes, so unrunnable rows only fail once money is involved",
                '        if briefs is not None and row.get("surface") and row["surface"] not in briefs:',
                "        if False:",
                "a row with no brief for its surface is reported",
            ),
            Mutation(
                # #592, AND THE REASON IT SURVIVED 63 ASSERTIONS. `--scaffold` writes `ladders`
                # (per kind); the cost path read `ladder` (flat), which no scaffolded config has.
                # So it resolved to [], every plan cost $0.00 however many rows it held, the budget
                # refusal compared 0.0 against the ceiling and could not fire, and `--run` fell
                # through to the executor. Reverting the reader reproduces it exactly.
                "the cost path reads a key --scaffold never writes, so every plan costs $0.00",
                '    return ladders.get(kind) or config.get("ladder") or []',
                '    return config.get("ladder") or []',
                "...while the fixed reader prices it from `ladders`",
            ),
            Mutation(
                # An unpriced kind is not a free kind. Returning 0.0 for a ladder that prices
                # nothing is the same bug one level up: the row scores $0.00, fits inside every
                # budget, and reaches the executor as the cheapest thing in the plan.
                "an unpriced ladder reads as free, so the row nobody costed is the cheapest one",
                "    return min(priced) if priced else None",
                "    return min(priced) if priced else 0.0",
                "a ladder that prices nothing returns None rather than 0.0",
            ),
            Mutation(
                # The refusal is deliberately NOT a budget comparison -- a ceiling can only refuse a
                # number. Dropping it puts the unpriced plan back on the path to the executor.
                "the unpriced refusal goes, so a plan nobody has costed runs anyway",
                "        if unpriced:",
                "        if False:",
                "--run refuses an unpriced plan",
            ),
            Mutation(
                # "Buy what the budget affords" is a decision about rows whose price is KNOWN.
                # Letting an unpriced group through prices it at nothing and buys it first.
                "unpriced groups are treated as affordable, so they fit inside any budget",
                "        if any(r is None for r in rungs):",
                "        if False:",
                "an unpriced row never fits, however large the budget",
            ),
            Mutation(
                # A generated view that is allowed to rot is worse than no view: it still reads as
                # authoritative, and it is the copy a human reviews before deciding to spend.
                "the rendered table stops being drift-checked, so a stale one reads as current",
                "    if path.read_text(encoding=\"utf-8\") != render_plan(rows, config):",
                "    if False:",
                "...an edited one is reported as stale",
            ),
        ),
    ),
    Guard(
        name="toolchain_version",
        subject="plugins/rails-flow/scripts/toolchain_version.py",
        selftest="plugins/rails-flow/scripts/toolchain_version_selftest.py",
        mutations=(
            Mutation(
                # Two records for one plugin coexist in the cache, ordered ONLY by lastUpdated.
                # Picking arbitrarily reports the stale one as installed, so an out-of-date
                # toolchain reads as current -- which is the single thing pillar 1 exists to catch.
                "the newest install record stops winning, so a stale version reads as installed",
                '    return max(records, key=lambda r: (r or {}).get("lastUpdated") or "")',
                "    return records[0]",
                "shadowed-record: newest wins",
            ),
        ),
    ),
    Guard(
        name="escalation",
        subject="plugins/rails-flow/scripts/escalation.py",
        selftest="plugins/rails-flow/scripts/escalation_selftest.py",
        mutations=(
            Mutation(
                # The agent and the human share a login, so authorship cannot distinguish them --
                # only the marker can, and only anchored at the START. Matching it anywhere means a
                # QUOTED question counts as the agent's own writing, and the thread parks forever.
                "the marker matches anywhere, so a quoted question reads as agent-authored",
                r'    return body.lstrip("\ufeff").startswith(MARKER)',
                "    return MARKER in body",
                "quoted-marker: a quoted question is not agent-authored",
            ),
        ),
    ),
    # The four that pre-dated the pillars and were flagged rather than fixed. Each target and each
    # `expects` was found EMPIRICALLY -- the mutation applied, the selftest run, the failure line
    # read -- because three earlier guesses in this repo named the pass message instead of the
    # failure message, and one named a line the selftest never exercised.
    Guard(
        name="check_criteria",
        subject="plugins/rails-flow/scripts/check_criteria.py",
        selftest="plugins/rails-flow/scripts/check_criteria_selftest.py",
        mutations=(
            Mutation(
                "empty criteria stop being unusable, so a brief with nothing in it is accepted",
                "    if not out:",
                "    if False:",
                "no criteria at all: expected UNUSABLE",
            ),
        ),
    ),
    Guard(
        name="extract_claims",
        subject="plugins/rails-flow/scripts/extract_claims.py",
        selftest="plugins/rails-flow/scripts/extract_claims.py",
        mutations=(
            Mutation(
                # Hedged prose is not a claim. Without the filter, "arguably this prevents X" is
                # extracted as an assertion someone must then verify.
                "hedges stop disqualifying a sentence, so speculation is extracted as a claim",
                "    if any(re.search(h, sentence, re.I) for h in HEDGES):",
                "    if False:",
                "silent on 'Arguably this prevents confusion.'",
            ),
        ),
    ),
    Guard(
        name="findings",
        subject="plugins/rails-flow/scripts/findings.py",
        selftest="plugins/rails-flow/scripts/findings.py",
        mutations=(
            Mutation(
                # Dependency edges must outrank severity, or a fix is ordered before the thing it
                # depends on and the "ordered" list cannot actually be followed.
                "edges stop constraining order, so a fix is scheduled before its prerequisite",
                "    if after not in successors[before]:",
                "    if False:",
                "an edge outranks severity",
            ),
        ),
    ),
    Guard(
        name="self_consistency",
        subject="plugins/rails-flow/scripts/self_consistency.py",
        selftest="plugins/rails-flow/scripts/self_consistency_selftest.py",
        mutations=(
            Mutation(
                # An example that runs code and asserts nothing is a test that cannot fail -- green
                # forever, and indistinguishable in a report from one that verifies something.
                "every example looks like it asserts, so assertion-free specs pass as coverage",
                "        if _PENDING.search(blob) or _ASSERTS.search(blob):",
                "        if True:",
                "assertion-free-spec / example runs code but asserts",
            ),
            Mutation(
                # A verification command whose failure cannot fail the build is a gate that cannot
                # fail -- the class this whole repo is organised around.
                "softened verdicts stop being reported, so `|| true` on a check passes review",
                "        match = _SOFTENED.search(line)",
                "        match = None",
                "swallowed-verdict / rspec verdict softened",
            ),
            Mutation(
                # An empty sample set must not read as "nothing to check" -- that is the vacuous
                # pass this repo keeps hitting, where a rule reports clean over nothing examined.
                "an empty sample set short-circuits, so documented-but-dead keys are never found",
                "    if not samples:",
                "    if True:",
                "dead-env-var / documented key nothing reads",
            ),
            Mutation(
                "`rescue nil` stops being reported, so every failure it hides stays hidden",
                "        if _RESCUE_NIL.search(code):",
                "        if False:",
                "swallowed-exception / rescue nil",
            ),
        ),
    ),
    Guard(
        name="research_record",
        subject="plugins/design-flow/scripts/research_record.py",
        selftest="plugins/design-flow/scripts/research_record.py",   # --selftest lives in the module
        # No `needs`: every fixture is a dict literal, and nothing here touches the network -- which
        # matters more than usual, because the subject is about BROWSING other people's sites.
        mutations=(
            Mutation(
                # Emitting doctrine from an unreviewable record publishes a decision nobody made,
                # in the place agents trust most. The skill is only written from a record that
                # PASSES -- a record that gathers and does not choose must not become guidance.
                "an unreviewable record still emits a skill, publishing a decision nobody made",
                "    problems = check(record)   # emit_skill: refuse at the point of writing",
                "    problems = []", 
                "a record with no style should not emit a skill",
            ),
            Mutation(
                # "Three or more sources disagree, and the choosing IS the design." A record that
                # gathers and does not choose is a mood board.
                "a record may gather without choosing, so the research produces no decision",
                '    if record.get("references") and not record.get("style"):',
                "    if False:",
                "a record with references and no style is reported",
            ),
            Mutation(
                # Direct competitors converged on one look by copying each other. A record sampled
                # only from them inherits the convergence and produces the median.
                "an all-competitor record passes, so the output inherits their convergence",
                "    if refs and cats == {\"direct\"}:",
                "    if False:",
                "an all-direct record is reported",
            ),
            Mutation(
                # A login wall returns a PAGE, not an error -- so the capture can be the wall, filed
                # as research, and nothing downstream can tell.
                "a sign-in capture passes unmarked, so the wall is filed as a reference",
                '        if re.search(r"(login|signin|sign-in|auth)", cap, re.I) and not ref.get("gated"):',
                "        if False:",
                "a sign-in-looking capture with no `gated` is reported",
            ),
            Mutation(
                "everything-adopted stops being reported, so a shopping list passes as research",
                "    if refs and not any(r.get(\"reject\") for r in refs):",
                "    if False:",
                "a record rejecting nothing is reported",
            ),
        ),
    ),
)


def stage(guard: Guard, workdir: Path) -> Path:
    """Copy subject + selftest + deps + needs into `workdir`, UNMUTATED. Returns the entry point.

    Mirrors the repo layout rather than flattening, so `parents[1]`-relative reads still work.
    """
    for relative in {guard.subject, guard.selftest, *guard.deps}:
        target = workdir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((REPO / relative).read_text(encoding="utf-8"), encoding="utf-8")
    for relative in guard.needs:
        source, target = REPO / relative, workdir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        # A whole directory, not just a file: `build_coverage_selftest` reads EVERY doc under
        # `references/`, and naming the 19 of them here would go quiet the day a 20th is added --
        # the coverage-gap class, in the harness that exists to catch it.
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copyfile(source, target)
    return workdir / guard.selftest


def apply_mutation(guard: Guard, mutation: Mutation, workdir: Path) -> Path:
    """Stage the guard into `workdir`, with the mutation applied to the subject.

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

    entry = stage(guard, workdir)
    (workdir / guard.subject).write_text(mutated, encoding="utf-8")
    return entry


def run_baseline(guard: Guard) -> list[str]:
    """The control: the UNMUTATED selftest must PASS in the same staged tempdir.

    Without this, `run_guard`'s "returncode != 0 means caught" reads a guard that cannot pass at
    all as a guard that catches everything. That is not hypothetical -- it was true of
    `build_coverage` for as long as its selftest read the reference docs, which are not part of
    the subject: the staged mutant had no `references/`, the unmutated selftest already exited 1,
    and all of its mutations were therefore "caught" without the mutation doing anything. A
    gate-that-cannot-fail inside the meta-gate whose whole job is proving gates can fail.

    Run once per guard rather than once per mutation: staging is identical, and the cost is one
    selftest run against N.
    """
    workdir = Path(tempfile.mkdtemp(prefix=f"mutbase-{guard.name}-"))
    try:
        entry = stage(guard, workdir)
        argv = [sys.executable, str(entry)]
        if guard.selftest == guard.subject:
            argv.append("--selftest")
        result = subprocess.run(argv, cwd=workdir, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return [
                f"{guard.name}: INERT — the UNMUTATED selftest already fails in the staged "
                f"tempdir (exit {result.returncode}), so every mutation below is 'caught' whether "
                "or not it breaks anything. Add what it reads to the guard's `needs`.\n"
                + "\n".join(f"      {line}" for line in
                            (result.stdout + result.stderr).strip().splitlines()[-6:])
            ]
    except subprocess.TimeoutExpired:
        return [f"{guard.name}: the unmutated baseline timed out"]
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return []


def run_guard(guard: Guard) -> list[str]:
    """Failures for one guard. Empty list = every mutation was caught by the right fixture.

    Serial, deliberately. Wall time is one subprocess per declared mutation and the list only
    grows -- 236 of them crossed `maintainer_doctor`'s 180s per-gate budget while #129 was being
    written. The fix is `SLOW_GATES` over there, which states the cost honestly, rather than a
    thread pool here: every mutation does run in its own temp directory against its own
    subprocess, so parallelising is safe and is the obvious next step, but it measured at only
    ~7% on a machine that was running other agents' sweeps at the same time. An unmeasurable
    speedup is not worth adding concurrency to the checker every other gate is judged by.
    """
    # The baseline runs the UNMUTATED selftest first. Without it a guard whose staged copy is
    # missing a dependency fails for that reason alone, and every mutation then reads as "caught"
    # by the breakage rather than by a fixture -- which is exactly what `build_coverage` was doing.
    problems: list[str] = run_baseline(guard)
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
