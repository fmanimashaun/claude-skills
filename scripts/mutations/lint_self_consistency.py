"""Mutation guard: lint_self_consistency. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="lint_self_consistency",
    subject="scripts/lint_self_consistency.py",
    selftest="scripts/lint_self_consistency.py",   # --selftest lives in the module itself
    mutations=(
        # #835. Four shipped commands were documented nowhere; this is the rule that refuses it.
        Mutation(
            "the command rule stops looking at the plugin README",
            '        docs = [(root_readme, f"`{command}`"), (ROOT / "plugins" / plugin / "README.md", f"/{plugin}:{command}")]',
            '        docs = [(root_readme, f"`{command}`")]',
            "a shipped command the PLUGIN README never names",
        ),
        Mutation(
            "the command rule matches nothing, so an undocumented command passes",
            "            if needle not in read(doc):",
            "            if False:",
            "a shipped command the root README never names",
        ),

        # #777. The rule that stops #617's class recurring a fourth time. Four clauses: it must
        # FIRE on a cross-plugin hop count, stay silent on the resolver, stay silent on prose,
        # and stay silent on the resolver's own file.
        Mutation(
            # Half this corpus explains clone-vs-install in its docstring. Matching those
            # reports the files DESCRIBING the defect alongside the ones committing it, which
            # is how the first draft of this rule flagged brand_pack_lint.py:18.
            "docstrings stop being excluded, so prose about the defect reads as the defect",
            '            if id(node) in docstrings:\n                continue',
            '            if False:\n                continue',
            "a docstring naming the path is not a finding",
        ),
        Mutation(
            # The fixture for this one must CONTAIN the literal or it proves silence for the
            # wrong reason -- the first draft omitted it entirely and this mutation survived.
            "the resolver-import exemption goes, so a correct caller is flagged",
            '        if "doctrine_path" in text:\n            continue',
            "        if False:\n            continue",
            "the shared resolver is silent, fallback literal and all",
        ),
        Mutation(
            "the resolver's own file stops being exempt, where the hops legitimately live",
            '        if path.name == "doctrine_path.py":          # the resolver itself is where the hops live',
            "        if False:",
            "doctrine_path.py itself is exempt",
        ),
        Mutation(
            "the rule matches nothing, so every clone-shaped path passes",
            '            if node.value != "design-system" and "skills/design-system" not in node.value:',
            '            if id(node) in docstrings or "zzz-never" not in node.value:',
            "__file__.parents reaching a sibling plugin's doctrine",
        ),
        # #713. Three clauses, three mutations, two slugs -- a rule with N clauses needs a
        # finding per clause or none of them is provable.
        Mutation(
            "a literal toolchain tag pinned for a user to copy stops being reported",
            "        for match in _PINNED_REF.finditer(body):",
            "        for match in ():",
            "a literal toolchain tag pinned for a user to copy",
        ),
        Mutation(
            "a tag hung off our own repo slug stops being reported",
            "        for match in _SLUG_PIN.finditer(body):",
            "        for match in ():",
            "a literal tag pinned against our own repo slug",
        ),
        Mutation(
            # Without the scope, a third party's pinned ref in one of our docs becomes our
            # finding -- a rule that fires on correct input gets switched off.
            "the scope to our own repository is dropped",
            '        if "fmanimashaun/claude-skills" not in body:',
            "        if False:",
            "silent on a pinned ref that is not our repository",
        ),
        # #701. Three clauses, three mutations -- a rule with N clauses needs a fixture that
        # trips exactly one of each, or none of them is proven. That lesson cost three
        # surviving mutants the day before this landed.
        Mutation(
            "a bullet filed under a component that owns none of its files is accepted",
            "        elif owner_of_section not in owners:",
            "        elif False:",
            "maintainer tooling under the skills section fires",
        ),
        Mutation(
            "a bullet naming no file is treated as placed, so the gate goes blind on the "
            "commonest input",
            "        if not owners:",
            "        if False:",
            "a bullet naming no file at all fires",
        ),
        Mutation(
            # A path in a code sample is not evidence of ownership.
            "a path that does not exist in the tree counts as evidence",
            "        cited = {c for c in _BULLET_PATH.findall(body) if (ROOT / c).exists()}",
            "        cited = set(_BULLET_PATH.findall(body))",
            "a path that does not exist in the tree is not evidence",
        ),
        Mutation(
            # Scope is what keeps this off 13,000 lines of published history.
            "released blocks are judged too, so the gate fails on its first real input",
            '            unreleased = line[4:].strip().lower().startswith("unreleased")',
            "            unreleased = True",
            "silent on a bullet under a RELEASED heading",
        ),
        # #699. The rule this repo needed and did not have: two publish paths carrying the same
        # extractor, kept in step by a comment. Both directions, because a partial fix is what
        # made the bug survive its own discovery.
        Mutation(
            "a publish path stops delegating and nothing notices",
            "        if script not in body:",
            "        if False:",
            # NOT the awk fixtures -- those trip the inline-shape check too, so they survived
            # this mutation. This is the one that isolates the delegation half.
            "a path that neither delegates nor shows a known extractor shape",
        ),
        Mutation(
            "an inline extractor may sit alongside the delegation, so which one wins depends "
            "on line order",
            "        for shape in inline:",
            "        for shape in ():",
            "delegating and ALSO keeping an inline parser still fires",
        ),
        Mutation(
            # #653. rails-flow said "eight" and shipped eleven. The count is the part a reader
            # remembers, and it is the text they read while deciding to install.
            "a stated subagent count stops being reconciled against what ships",
            "            if claimed is not None and claimed != len(shipped):",
            "            if False:",
            "a wrong spelled-out count",
        ),
        Mutation(
            # Naming SOME agents is the trap: it reads as the list. design-flow named three of
            # five, hiding design-critic -- the advisory lens the enforcement model rests on.
            "a description may name a subset of its agents and pass",
            "            if missing:",
            "            if False:",
            "a description naming some agents but not all",
        ),
        Mutation(
            # #651. All five plugins shipped bare -- no licence on a repo that has an MIT
            # LICENSE at its root, and no repository on a project whose whole feedback loop is
            # downstream users filing issues here. Nothing checked the entries for completeness,
            # so five bare ones looked exactly like five complete ones.
            "plugin entries stop being checked for the metadata a user installs against",
            "        missing = [f for f in required if not plugin.get(f)]",
            "        missing = []",
            "a plugin entry with no install metadata",
        ),
        Mutation(
            # Two statements of one licence that disagree is the exact defect this file exists
            # to catch, and the one users receive is the manifest's.
            "the manifest licence stops being reconciled against the root LICENSE",
            "        if spdx and declared and declared != spdx:",
            "        if False:",
            "a manifest licence contradicting the root LICENSE",
        ),
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
            # #660 extracted the set to NAMED_GATES when guard-lane.sh joined it; the anchor
            # follows the code and the assertion it guards is unchanged.
            "    gates = sum(1 for s in scripts if s.name in NAMED_GATES)",
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
)
