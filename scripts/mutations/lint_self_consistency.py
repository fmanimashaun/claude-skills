"""Mutation guard: lint_self_consistency. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="lint_self_consistency",
    subject="scripts/lint_self_consistency.py",
    selftest="scripts/lint_self_consistency.py",   # --selftest lives in the module itself
    mutations=(
        # #1109. Six hook_* guards went INERT at once because a driven hook gained a script
        # dependency nothing declared -- the unmutated selftest already failed in the staged
        # tempdir, so every mutation read as caught, and dev's full sweep was red for an hour.
        Mutation(
            "an undeclared harness dependency stops being a finding",
            "        missing = [g for g in guards if script not in read(g)]",
            "        missing = []",
            "a script a driven hook runs, undeclared by a guard",
        ),
        Mutation(
            # SCOPE: a hook the harness never drives cannot blind a guard, and flagging it would
            # be noise -- a rule that reports things nobody triages gets switched off.
            "hooks the harness never drives are flagged too",
            "        if hook.name not in harness_body:",
            "        if False:",
            "a hook the harness never drives is out of scope",
        ),
        # #1106. The named gates are parsed from the CLAUDE.md sentence rather than hardcoded, so
        # classifying a hook is ONE deliberate act instead of two places to keep in step.
        Mutation(
            # A paragraph naming NO gate means the decision is not recorded anywhere. Silence
            # there would let a fail-closed hook join without ever being classified.
            "a paragraph that names no gate at all stops being a finding",
            "    if not named:",
            "    if False:",
            # The FIXTURE'S label, not the finding text -- this mutation makes that finding
            # disappear, so expecting its message fails for the wrong reason (mutation_types.py
            # says so in as many words, and I did it anyway).
            "a paragraph naming no gate by path is reported",
        ),
        # #1088. The advisor stance and the context budget are scaffolded into every downstream
        # CLAUDE.md. A copy that shipped while this repo followed neither is the plainest form of
        # the defect this whole lint exists for.
        Mutation(
            "we may ship behavioural doctrine we do not follow ourselves",
            "        if in_shipped and not in_ours:",
            "        if False:",
            "doctrine we scaffold and do not follow ourselves",
        ),
        Mutation(
            # The mirror direction: dropping it from the template while keeping it here would
            # leave every NEW project without it, silently.
            "doctrine may be dropped from the scaffold while we keep it",
            "        elif in_ours and not in_shipped:",
            "        elif False:",
            "doctrine we follow and stopped shipping",
        ),
        Mutation(
            # SCOPE. Firing when it is absent from both would make a fresh checkout red before
            # anyone had written anything, which is how a rule gets deleted.
            "the rule fires even when the doctrine exists in neither place",
            "        if in_shipped and not in_ours:",
            "        if not in_ours:",
            "doctrine absent from both is out of scope",
        ),
        # #1092. The step ran on a PR into dev four times despite its `if`. Cause unknown, every
        # hypothesis refuted -- so the step must not depend on being told the truth.
        Mutation(
            "the promotion step may trust github.base_ref alone again",
            "    if not _SELF_CHECK.search(match.group(1)):",
            "    if False:",
            "a promotion step that trusts github.base_ref alone",
        ),
        Mutation(
            # The MUST-PASS half: a step that DOES resolve the base must not be flagged, or the
            # rule is red on the very shape it is asking for.
            "any promotion step is flagged, including one that already self-checks",
            "    if not _SELF_CHECK.search(match.group(1)):",
            "    if True:",
            "a promotion step that resolves the base itself is silent",
        ),
        # The tally that lied. Seven assertions sat below the print for a whole release and the
        # stale number was quoted into a merged PR body.
        Mutation(
            "assertions may sit below the printed tally again",
            "    return sorted(line for line in raisers if line > printed)",
            "    return []",
            "the tally guard misses assertions that run after the count is printed",
        ),
        # #1077. `conclusion: failure` is the same string whether a suite ran and failed or no
        # runner ever started. Each mutation removes one half of the separation.
        Mutation(
            "the step-count discriminator stops being required",
            "        if _STEP_COUNT.search(body):",
            "        if True:",
            "reading ci status with no step-count discriminator",
        ),
        Mutation(
            # Accepting ONLY our own script would fail correct code that measured the right
            # thing with a bare `gh api` call -- a gate wrong about correct code gets removed.
            "only our own helper counts, so measuring the steps by hand is not a measurement",
            '_STEP_COUNT = re.compile(r"ci_verdict\\.py|steps\\|length|steps=0|executed no steps|zero .{0,12}steps")',
            '_STEP_COUNT = re.compile(r"ci_verdict\\.py")',
            "counting the steps inline satisfies it without our script",
        ),
        Mutation(
            # SCOPE in the flattering direction: firing on every shipped command makes the rule
            # unusable, and an unusable rule is deleted rather than fixed.
            "the trigger widens past instructions that actually read CI",
            '_READS_CI = re.compile(r"gh pr checks|gh run list|gh run view|actions/runs")',
            '_READS_CI = re.compile(r"gh |bundle")',
            "a command that never reads ci status is out of scope",
        ),
        # #1080. Three shipped commands checked that a server ANSWERED and none checked whose
        # working tree it served. Each mutation below removes one half of the answer.
        Mutation(
            # The rule's whole content: an answer is not ownership.
            "resolving the listener's working directory stops being required",
            "        if _OWNER_RESOLVED.search(body):",
            "        if True:",
            "a reuse instruction that never asks whose server it is",
        ),
        Mutation(
            # BSD-only. A rule blind to /proc reports every correctly-written command as
            # defective on Linux, which is where CI runs -- red on correct code is how a gate
            # gets switched off.
            "only the BSD spelling of the cwd lookup counts, so Linux's is not a resolution",
            '_OWNER_RESOLVED = re.compile(r"-d cwd|/proc/[^\\s\\"\']*/cwd")',
            '_OWNER_RESOLVED = re.compile(r"-d cwd")',
            "the /proc spelling of the same resolution counts",
        ),
        Mutation(
            # A POINTER BELIEVED RATHER THAN RESOLVED. This is the flattering direction: every
            # `/plugin:command` mention would excuse the file, including a pointer at a command
            # with the identical defect.
            "a slash-command reference excuses the file without reading what it points at",
            "            if target.is_file() and _OWNER_RESOLVED.search(read(target)):",
            "            if target.is_file():",
            "a pointer to a command that does NOT is the same defect one hop away",
        ),
        Mutation(
            # SCOPE, in the direction nobody audits. Firing on every shipped command makes the
            # rule unusable, and an unusable rule is removed rather than fixed.
            "the trigger widens from a PRE-EXISTING listener to any mention of a server",
            '    r"|(?:starting|launching) a second", re.I)',
            '    r"|(?:starting|launching) a second|server", re.I)',
            "a command that never contemplates a running server is out of scope",
        ),

        # Pre-release review of #1387: an unterminated block went unjudged.
        Mutation(
            "an unterminated yaml block is skipped again",
            "        if block is not None and not any(ISSUE_FORM_FIELD.match(b) for _, b in block):\n            toggles.extend(block)\n",
            "",
            "a dead toggle in an UNTERMINATED yaml block is still found",
        ),
        # #1376. The issue-form carve-out, widened: every yaml block exempt, so a real dead toggle
        # beside a GitHub form goes quiet. Its control fixture must catch it.
        Mutation(
            "every yaml block is exempt, not only GitHub issue forms",
            "                if not any(ISSUE_FORM_FIELD.match(b) for _, b in block):",
            "                if False:",
            "CONTROL: a dead toggle beside an issue form is still found",
        ),
        # #1082. The invariant, not the instance. `unhonoured-config-toggle` was computed in
        # run() and dropped from its return for months while its own fixtures passed, because
        # they call the check function directly. This mutation re-orphans it.
        Mutation(
            "a rule's findings are computed and dropped from run()'s return",
            "            + xplugin + unowned + toggles + ci_step + promo_ctx + bothways + harness_dep,",
            "            + xplugin + unowned + ci_step + promo_ctx + bothways + harness_dep,",
            "drops them from its return",
        ),
        Mutation(
            # #1017. The rule exists because a backstop reached every client except its author;
            # a mutation that drops the comparison makes it agree with any .gitignore at all.
            "a never-stage path we ship is no longer required in our own .gitignore",
            "            if pattern in ignored or pattern in seen:",
            "            if True:",
            "a never-stage path this repo does not ignore",
        ),
        Mutation(
            # The scope is what keeps it usable: `qa/reports/` is a client's layout, not ours.
            # Widening to every gitignore instruction would demand fiction in our own file.
            "the rule stops requiring the never-stage phrasing and fires on any client path",
            '    r"never (?:write or stage|stage|commit)[^.\\n]*?`(/?[A-Za-z0-9_.\\-]+/)`", re.IGNORECASE)',
            '    r"`(/?[A-Za-z0-9_.\\-]+/)`", re.IGNORECASE)',
            "client-layout path without the never-stage rule",
        ),

        # #870. The ceiling on CLAUDE.md is a gate, not a note in the history file.
        Mutation(
            "the ceiling stops being enforced, so CLAUDE.md can regrow in silence",
            "    elif count > int(m.group(1)):",
            "    elif False:",
            "CLAUDE.md one line past the ceiling",
        ),
        Mutation(
            "a missing history file stops being a finding",
            "    if not (ROOT / CLAUDE_MD_HISTORY).is_file():",
            "    if False:",
            "the history file CLAUDE.md points at is missing",
        ),
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

        # #948. Two plugins in one marketplace, one instructing a path the other's gate refuses.
        # Three clauses: the placement check must FIRE, the vocabulary must come from the module
        # rather than a copy, and a missing vocabulary must be reported rather than passed.
        Mutation(
            "the placement check goes, so an unplaceable findings path ships again",
            "            if top in dirs:\n                continue",
            "            if True:\n                continue",
            "an unplaceable findings path is reported",
        ),
        Mutation(
            # A second list of layout directories IS the drift this rule prevents, one level up.
            "the vocabulary is hardcoded instead of read from docs_layout.py",
            '        layout = getattr(module, "LAYOUT", None)\n'
            "        return set(layout) if isinstance(layout, dict) else None",
            '        return {"product", "evidence", "brain", "qa", "reviews"}',
            "an unplaceable findings path is reported",
        ),
        Mutation(
            "a missing vocabulary reads as a pass, so the rule goes quiet when it cannot check",
            "            if dirs is None:",
            "            if False:",
            "a missing docs_layout.py is reported, not passed",
        ),

        # #949. A key filter is not a type check: Stimulus consults it only inside
        # `event instanceof KeyboardEvent`, so a bare `Event("keydown")` from a browser extension
        # skips it and runs the handler. Two clauses -- the rule must FIRE on a destructive handler
        # and stay SILENT on a navigation one, because a rule that flags every roving-tabindex
        # descriptor we ship is a rule that gets switched off.
        Mutation(
            "the destructive-handler verbs go, so the modal root we shipped passes again",
            "->[A-Za-z0-9_-]+#(close|dismiss|clear|cancel|remove|reset|discard|destroy|delete|hide)\\b\")",
            "->[A-Za-z0-9_-]+#(closeXXNEVERXX)\\b\")",
            "the modal root we shipped",
        ),
        Mutation(
            "the rule widens to every key filter, so navigation descriptors are flagged too",
            "        for match in _KEY_FILTER_DESTRUCTIVE.finditer(body):",
            "        for match in _KEY_FILTER_ANY.finditer(body):",
            "a filter over a navigation handler is silent",
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
        # #1415 (and its review in #1482): one mutation per clause of broken-relative-link.
        Mutation(
            'a broken relative link in docs stops being reported',
            '            if resolved.exists() or (not resolved.suffix and resolved.with_name(resolved.name + ".md").exists()):',
            '            if True:',
            'a repo-root path inside docs/brain/history resolves to nothing',
        ),
        Mutation(
            'a link is resolved from the repo root instead of its own directory',
            '            resolved = ROOT / target.lstrip("/") if target.startswith("/") else path.parent / target',
            '            resolved = ROOT / target.lstrip("/")',
            'a repo-root path inside docs/brain/history resolves to nothing',
        ),
        Mutation(
            'a /-rooted link is resolved from its own directory',
            '            resolved = ROOT / target.lstrip("/") if target.startswith("/") else path.parent / target',
            '            resolved = path.parent / target.lstrip("/")',
            '...silent on a /-rooted link that resolves from the repo root',
        ),
        Mutation(
            'an #anchor makes a missing file pass',
            '            target = unquote(raw.split("#", 1)[0])',
            '            target = "" if "#" in raw else unquote(raw)',
            '...an #anchor does not rescue a missing file',
        ),
        Mutation(
            'a percent-encoded target is not decoded',
            '            target = unquote(raw.split("#", 1)[0])',
            '            target = raw.split("#", 1)[0]',
            '...silent on titled, angled and reference links that resolve',
        ),
        Mutation(
            'any extensionless link passes as a wiki page',
            '(not resolved.suffix and resolved.with_name(resolved.name + ".md").exists())',
            '(not resolved.suffix)',
            '...a wiki-style link to a page that does not exist',
        ),
        Mutation(
            'a titled link is never examined',
            '_MD_LINK = re.compile(r"""\\[[^\\]\\n]*\\]\\([ \\t]*(?:<([^>\\n]+)>|([^)\\s]+))(?:[ \\t]+(?:"[^"\\n]*"|\'[^\'\\n]*\'|\\([^)\\n]*\\)))?[ \\t]*\\)""")',
            '_MD_LINK = re.compile(r"""\\[[^\\]\\n]*\\]\\([ \\t]*(?:<([^>\\n]+)>|([^)\\s]+))[ \\t]*\\)""")',
            '...a titled link to a missing file',
        ),
        Mutation(
            'an angle-bracket link is never examined',
            '_MD_LINK = re.compile(r"""\\[[^\\]\\n]*\\]\\([ \\t]*(?:<([^>\\n]+)>|([^)\\s]+))(?:[ \\t]+(?:"[^"\\n]*"|\'[^\'\\n]*\'|\\([^)\\n]*\\)))?[ \\t]*\\)""")',
            '_MD_LINK = re.compile(r"""\\[[^\\]\\n]*\\]\\([ \\t]*(?:(?!)<([^>\\n]+)>|([^)\\s]+))(?:[ \\t]+(?:"[^"\\n]*"|\'[^\'\\n]*\'|\\([^)\\n]*\\)))?[ \\t]*\\)""")',
            '...an angle-bracket link to a missing file',
        ),
        Mutation(
            'a reference definition is never examined',
            'list(_MD_LINK.finditer(prose)) + list(_MD_REFDEF.finditer(prose))',
            'list(_MD_LINK.finditer(prose))',
            '...a reference definition to a missing file',
        ),
        Mutation(
            'fences are scanned as prose',
            '            if opened:\n                fence = opened.group(1)',
            '            if False:\n                fence = opened.group(1)',
            '...silent inside a fenced block',
        ),
        Mutation(
            'a fence closes at any fence line, whatever its character or length',
            '            if re.match(r"^[ \\t]*" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \\t]*$", line):',
            '            if _MD_FENCE_OPEN.match(line):',
            '...silent inside a ~~~ fence and a four-backtick fence with an inner ```',
        ),
        Mutation(
            'a fence never closes',
            '            if re.match(r"^[ \\t]*" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \\t]*$", line):',
            '            if False:',
            '...a link after a closed fence and a closed comment still fires',
        ),
        Mutation(
            'a footnote definition is read as a link',
            '_MD_REFDEF = re.compile(r"^[ ]{0,3}\\[(?!\\^)[^\\]\\n]+\\]:[ \\t]*(?:<([^>\\n]+)>|(\\S+))", re.MULTILINE)',
            '_MD_REFDEF = re.compile(r"^[ ]{0,3}\\[[^\\]\\n]+\\]:[ \\t]*(?:<([^>\\n]+)>|(\\S+))", re.MULTILINE)',
            '...silent on a footnote definition',
        ),
        Mutation(
            'a four-space indent opens a fence',
            '_MD_FENCE_OPEN = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})")',
            '_MD_FENCE_OPEN = re.compile(r"^[ \\t]*(`{3,}|~{3,})")',
            '...a four-space-indented ``` is not a fence that swallows the rest',
        ),
        Mutation(
            'inline code is scanned as prose',
            '    return re.sub(r"(`+)[^\\n]*?\\1", lambda m: " " * len(m.group(0)), prose)',
            '    return prose',
            '...silent in inline code and an HTML comment',
        ),
        Mutation(
            'an HTML comment is scanned as prose',
            '    prose = re.sub(r"<!--.*?-->", lambda m: re.sub(r"[^\\n]", " ", m.group(0)), prose, flags=re.DOTALL)',
            '    pass',
            '...silent in inline code and an HTML comment',
        ),
        # #1414 (and its review in #1482): a workflow action pinned by a tag, and a checkout that keeps its credentials.
        Mutation(
            'a workflow action pinned by a tag stops being reported',
            '            if not _SHA_PIN.match(ref):',
            '            if False:',
            'an action pinned by a TAG',
        ),
        Mutation(
            'a short sha passes as a full pin',
            '_SHA_PIN = re.compile(r"^[^@\\s]+@[0-9a-f]{40}$")',
            '_SHA_PIN = re.compile(r"^[^@\\s]+@[0-9a-f]{7,40}$")',
            '...a SHORT sha is not a full pin',
        ),
        Mutation(
            'a checkout that keeps its credentials stops being reported',
            '                if not any(re.match(r"""^[\\s-]*persist-credentials:\\s*(["\']?)false\\1\\s*(#.*)?$""", l) for l in step):',
            '                if False:',
            'a checkout that keeps its credentials',
        ),
        Mutation(
            "a quoted 'false' is not accepted",
            '                if not any(re.match(r"""^[\\s-]*persist-credentials:\\s*(["\']?)false\\1\\s*(#.*)?$""", l) for l in step):',
            '                if not any(re.match(r"""^[\\s-]*persist-credentials:\\s*false\\s*(#.*)?$""", l) for l in step):',
            "...silent on a quoted 'false'",
        ),
        Mutation(
            'mismatched quotes pass as false',
            '                if not any(re.match(r"""^[\\s-]*persist-credentials:\\s*(["\']?)false\\1\\s*(#.*)?$""", l) for l in step):',
            '                if not any(re.match(r"""^[\\s-]*persist-credentials:\\s*["\']?false["\']?\\s*(#.*)?$""", l) for l in step):',
            '...mismatched quotes are not a false',
        ),
        Mutation(
            "a later step's persist-credentials counts for this checkout",
            '                    if stripped and not stripped.startswith("#") and len(nxt) - len(stripped) <= dash:\n                        break',
            '                    if False:\n                        break',
            "...a later step's persist-credentials does not cover this checkout",
        ),
        Mutation(
            "a comment at the dash's indent ends the step",
            '                    if stripped and not stripped.startswith("#") and len(nxt) - len(stripped) <= dash:\n                        break',
            '                    if stripped and len(nxt) - len(stripped) <= dash:\n                        break',
            "...silent past a comment at the dash's indent inside the step",
        ),
        Mutation(
            'the step scan starts at uses: and misses a with: written above it',
            '                if not lines[start].lstrip(" ").startswith("-"):',
            '                if False:',
            '...silent on persist-credentials written above uses: in the same step',
        ),
        Mutation(
            'the backward scan runs into the previous step',
            '                        if above.startswith("- ") and len(lines[start]) - len(above) < indent:\n                            break',
            '                        if False:\n                            break',
            "...a previous step's persist-credentials does not cover this checkout",
        ),
        Mutation(
            "a blank line before the step is swallowed as indentation -- the review's blocker",
            '_USES = re.compile(r"^([ \\t]*)-?[ \\t]*uses:[ \\t]*([^\\s#]+)", re.M)',
            '_USES = re.compile(r"^(\\s*)-?\\s*uses:\\s*([^\\s#]+)", re.M)',
            '...nor across a blank line before this checkout',
        ),
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
            # #660 extracted the set to NAMED_GATES when guard-lane.sh joined it; #1106 replaced
            # that hardcoded set with the names parsed from CLAUDE.md, so classifying a hook is
            # one deliberate act rather than two. The anchor follows the code; the assertion it
            # guards is unchanged.
            "    gates = sum(1 for s in scripts if s.name in named)",
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
            "        if not _INSTALL_LINE(name).search(body):",
            "        if False:",
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
        # #1543: a conflict block passed a PR's gate run because nothing read for the markers.
        Mutation(
            "the opening marker stops being recognised",
            '_CONFLICT_EDGE = re.compile(r"^(?:<{7}|>{7})(?: .*)?$")',
            '_CONFLICT_EDGE = re.compile(r"^(?:>{7})(?: .*)?$")',
            "only the opening marker is left",
        ),
        Mutation(
            "the closing marker stops being recognised",
            '_CONFLICT_EDGE = re.compile(r"^(?:<{7}|>{7})(?: .*)?$")',
            '_CONFLICT_EDGE = re.compile(r"^(?:<{7})(?: .*)?$")',
            "only the closing marker is left",
        ),
        Mutation(
            "a marker is matched anywhere in a line, not as a whole line",
            "if _CONFLICT_EDGE.match(line)]",
            "if re.search(r\"<{7}|>{7}\", line)]",
            "a marker quoted mid-line",
        ),
        Mutation(
            "an indented marker counts",
            "enumerate(lines, 1) if _CONFLICT_EDGE.match(line)]",
            "enumerate(lines, 1) if _CONFLICT_EDGE.match(line.strip())]",
            "an indented marker in a code block",
        ),
        Mutation(
            "a longer run of characters counts as a marker",
            '_CONFLICT_EDGE = re.compile(r"^(?:<{7}|>{7})(?: .*)?$")',
            '_CONFLICT_EDGE = re.compile(r"^(?:<{7,}|>{7,})(?: .*)?$")',
            "an eight-character run is not a marker",
        ),
        Mutation(
            "a separator counts on its own, so a setext heading is refused",
            "_CONFLICT_SEPARATOR.match(line)] if edges else []",
            "_CONFLICT_SEPARATOR.match(line)]",
            "a setext heading underline of seven characters",
        ),
        Mutation(
            "the finding points at the first marker line, an earlier setext underline included",
            "(edges or separators)[0],",
            "min(edges + separators),",
            "a heading underline before a real block",
        ),
        Mutation(
            "only markdown is read",
            '    for path in walk(""):\n        with path.open("rb") as handle:',
            '    for path in walk(".md"):\n        with path.open("rb") as handle:',
            "a workflow file",
        ),
        Mutation(
            "binary files are read as text",
            '            if b"\\0" in handle.read(8000):\n                continue\n        examined += 1',
            '            if False:\n                continue\n        examined += 1',
            "a binary file is skipped",
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
        Mutation(
            "hook lib copies that differ stop being a finding",
            "        if len(texts) == len(pair) and len(set(texts.values())) > 1:",
            "        if False:",
            "hook lib copies that differ by one byte are a finding",
        ),
        # #1575: the second lib. Checking only the first pair would leave deadline.sh free to drift.
        Mutation(
            "only the first lib pair is compared, so deadline.sh copies can differ unnoticed",
            "    for pair in HOOK_LIB_PAIRS:\n        texts = {}",
            "    for pair in HOOK_LIB_PAIRS[:1]:\n        texts = {}",
            "deadline lib copies that differ by one byte are a finding",
        ),
        # #1041, and the two below are a matched pair. The rule has to sit between two failures,
        # so one mutation each way is the only way to prove it is still between them.
        Mutation(
            # TOO NARROW -- this IS the reported bug, restored. Slash-only could not tell a README
            # with no install line from one using the shell form, and reported both as missing.
            "only the slash spelling counts, so a shell install line reads as no install line",
            r'return re.compile(rf"(?:/|\bclaude\s+)plugin\s+install\s+{re.escape(name)}@")',
            r'return re.compile(rf"/plugin\s+install\s+{re.escape(name)}@")',
            "the shell spelling satisfies it",
        ),
        Mutation(
            # TOO WIDE -- the failure mode the fix could have become. Drop the prefix and prose
            # about installing satisfies the rule, which is `undocumented-plugin` again by another
            # name and a gate that can no longer fail.
            "any mention of `plugin install` counts, so prose satisfies the install-line rule",
            r'return re.compile(rf"(?:/|\bclaude\s+)plugin\s+install\s+{re.escape(name)}@")',
            r'return re.compile(rf"plugin\s+install\s+{re.escape(name)}@")',
            "a bare `plugin install` with no prefix does not satisfy it",
        ),
        # #1042. Both halves of the DISJOINT split, one mutation each. The rule has to say
        # "delete this copy" and "nothing versions this" about different plugins, and a rule that
        # could only ever say one of them would have driven the tree to the opposite drift.
        Mutation(
            "a version duplicated in marketplace.json and plugin.json stops being reported",
            '        if own_version and "version" in entry:',
            "        if False:",
            "a plugin versioned in both files",
        ),
        Mutation(
            # Without this half, the fix for #1042 is "delete every marketplace version key",
            # which would leave rails-stack -- the one plugin with no plugin.json -- unversioned.
            "a plugin versioned NOWHERE stops being reported",
            '        elif not own_version and "version" not in entry:',
            "        elif False:",
            "a plugin with no version in either file",
        ),
        Mutation(
            # Judging on the FILE rather than the KEY is the near-miss: a plugin.json with no
            # version leaves the marketplace copy operative, and flagging it would be a false
            # positive of exactly the kind #1041 was filed for.
            "presence of plugin.json counts as a declared version, whatever is in it",
            '                own_version = (json.loads(read(own)) or {}).get("version")',
            '                own_version = "present"',
            "a plugin.json without a version key leaves marketplace.json authoritative",
        ),
    Mutation(
        # #1131: `--author @me` reads as "mine" and is the ACCOUNT. Every session on a machine
        # shares one git user, so it returns peers' work -- measured downstream at five open PRs,
        # ONE belonging to the session that ran it. Under `gh pr merge --admin`, where no CI run is
        # left to catch the wrong pick, adopting a peer's PR is unrecoverable.
        "an `--author @me` filter offered as yours is no longer reported",
        '            if not _AUTHOR_ME.search(line):',
        '            if True:',
        "a bare `--author @me` offered as yours",
    ),
    Mutation(
        # THE CARVE-OUT, and it is load-bearing: a line NAMING `@me` as unreliable is the doctrine.
        # Without it the rule forbids warning anyone about the trap, which is how a rule gets
        # deleted along with the warning it was protecting.
        "a line that names `@me` as unreliable is reported as the defect",
        "            if _REFUSES_IT.search(window):",
        "            if False:",
        "...but naming it as unreliable is the doctrine, not the defect",
    ),
    Mutation(
        # The window must reach past a fenced block: the refusal is usually the sentence UNDER the
        # command, four lines down. A window one line short silently forbids every fenced warning.
        "the refusal window stops short of a fenced command's explanation",
        "            window = \"\\n\".join(lines[max(0, lineno - 3):lineno + 4])",
        "            window = \"\\n\".join(lines[max(0, lineno - 3):lineno + 2])",
        "...including when the refusal is the sentence UNDER the fenced command",
    ),
    Mutation(
        # #1141: requiring a directory made a ROOT-file change unreportable by construction --
        # a doctrine correction to CLAUDE.md could not produce a placeable bullet, and the only
        # way past the gate was to name a file the change did not touch. A gate whose only exit
        # is a false statement is worse than no gate.
        "a bullet naming only a root file is unplaceable again",
        r'_BULLET_PATH = re.compile(r"`(?:\./)?(\.?[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)*\.[A-Za-z0-9]+)`")',
        r'_BULLET_PATH = re.compile(r"`(?:\./)?(\.?[A-Za-z0-9_-]+(?:/[A-Za-z0-9_.-]+)+\.[A-Za-z0-9]+)`")',
        "a bullet naming only a ROOT file is placeable",
    ),
    Mutation(
        # #1173: the number-word table ended at thirteen, so the fourteenth hook script described
        # correctly in words read as drift. The table is shared now; losing an entry past the old
        # edge must be caught by the fixture written at that edge.
        "the number-word table ends at thirteen again",
        '"fourteen": 14, ',
        '',
        "a correct count past thirteen, in words, is silent",
    ),
    Mutation(
        # #1178: `\.?/?` ate the dot of `.github`, so a workflow-only change could not be placed.
        "the path prefix eats a dot-directory's dot again",
        r'`(?:\./)?(\.?[A-Za-z0-9_-]+',
        r'`\.?/?([A-Za-z0-9_-]+',
        "a bullet naming only a dot-directory path is placeable",
    ),
        Mutation(
            # #1480
            'a link climbing out of its plugin or skill is accepted again',
            '                    if resolved == root or root in resolved.parents:\n                        continue',
            '                    if True:\n                        continue',
            "a design-flow command linking into rails-stack's skills/ leaves its package",
        ),
        Mutation(
            # #1582
            'uncontained-process-fixture accepts the import alone, so an unused helper passes',
            '        if _CONTAIN_IMPORT.search(text) and _CONTAIN_WITH.search(text):',
            '        if _CONTAIN_IMPORT.search(text):',
            'uncontained-process-fixture / a selftest that imports the helper but never uses it',
        ),
        Mutation(
            # #1582
            'uncontained-process-fixture accepts any mention of contained(, so a comment passes',
            '        if _CONTAIN_IMPORT.search(text) and _CONTAIN_WITH.search(text):',
            '        if "contained(" in text:',
            'uncontained-process-fixture / a selftest that only NAMES contained() in a comment',
        ),
        Mutation(
            # #1582
            'uncontained-process-fixture is not scoped to selftests, so every process-starting script is refused',
            '        if "selftest" not in path.name:\n            continue\n        text = read(path)\n        if not _SPAWNS',
            '        text = read(path)\n        if not _SPAWNS',
            'uncontained-process-fixture / a non-selftest file that starts processes (out of scope)',
        ),
        Mutation(
            # #1577
            'non-hermetic-fixture-git accepts a hermetic fixture as a finding: the reference is never looked for',
            '        if not _HERMETIC_REF.search(text):\n            offenders[name] = line',
            '        if True:\n            offenders[name] = line',
            'non-hermetic-fixture-git / a fixture that references hermetic_git',
        ),
        Mutation(
            # #1577
            'non-hermetic-fixture-git is not scoped to scripts that make temp directories',
            '        if not _TEMP_USE.search(text):\n            continue\n        line = _spawns_git_commit(text)',
            '        line = _spawns_git_commit(text)',
            'non-hermetic-fixture-git / a script that commits but makes no temp directory',
        ),
        Mutation(
            # #1577
            'non-hermetic-fixture-git counts the word commit in a comment or docstring',
            '            if "commit" in literals:',
            '            if "commit" in literals or True:',
            'non-hermetic-fixture-git / a temp-using script that mentions commit only in a docstring and a comment',
        ),
        Mutation(
            # #1577
            'non-hermetic-fixture-git scans mutation guard files too',
            r'        if not re.match(r"^(scripts|plugins/[^/]+/scripts)/[^/]+\.py$", name):',
            r'        if not re.match(r"^(scripts|plugins/[^/]+/scripts)/.+\.py$", name):',
            'non-hermetic-fixture-git / a mutation guard file is out of scope',
        ),
        Mutation(
            # #1577
            'non-hermetic-fixture-git ignores the baseline, so every known offender is a finding',
            '        if name not in baseline:',
            '        if True:',
            'non-hermetic-fixture-git / a baseline entry that still commits without the reference is tolerated',
        ),
        Mutation(
            # #1577
            'non-hermetic-fixture-git never flags a stale baseline line, so the list cannot shrink',
            '    for name in sorted(baseline - set(offenders)):',
            '    for name in []:',
            'non-hermetic-fixture-git / a baseline entry whose file is hermetic now is a stale line',
        ),
        Mutation(
            # #1588
            "fixture-git-drift never compares the copies, so a fix in one plugin's copy alone passes",
            '        if canonical is not None and rel in texts and texts[rel] != canonical:',
            '        if False:',
            'fixture-git-drift / a fixture_git copy that differs by one byte is a finding',
        ),
        Mutation(
            # #1680
            "findings-script-drift never compares the copies, so qa-flow's findings.py can drift from rails-flow's",
            '        if canonical is not None and texts.get(rel, canonical) != canonical:',
            '        if False:',
            'findings-script-drift / a findings.py copy that differs by one byte is a finding',
        ),
        Mutation(
            # #1680
            'findings-script-drift does not notice a missing qa-flow copy',
            '            findings.append(Finding("findings-script-drift", rel, 0,\n                                    "missing',
            '            continue\n            findings.append(Finding("findings-script-drift", rel, 0,\n                                    "missing',
            'findings-script-drift / a missing qa-flow findings.py is a finding',
        ),
        Mutation(
            # #1680
            'cross-plugin-relative-path loses its same-plugin exemption, so ../scripts/ inside a plugin is refused',
            '            if match.group(1) == own:\n                continue\n',
            '',
            'cross-plugin-relative-path / a relative path inside the same plugin is silent',
        ),
        Mutation(
            # #1680
            "cross-plugin-relative-path skips rails-stack's skills/, which the marketplace ships",
            '    docs += [(p, "rails-stack") for p in sorted((ROOT / "skills").glob("**/*.md"))]\n',
            '',
            'cross-plugin-relative-path / a rails-stack skill reaching ../rails-flow/ is a finding',
        ),
        Mutation(
            # #1680
            'cross-plugin-relative-path scans tests/ fixtures, which never ship',
            '        if "/tests/" in rel:\n            continue\n        examined += 1\n        text = path.read_text(encoding="utf-8", errors="replace")',
            '        examined += 1\n        text = path.read_text(encoding="utf-8", errors="replace")',
            'cross-plugin-relative-path / a tests/ fixture is silent',
        ),
        Mutation(
            "fixture-git-bypass never reports a fixture identity outside fixture_git (#1588 part 2)",
            '            findings.append(Finding("fixture-git-bypass", str(rel), n,',
            '            None and findings.append(Finding("fixture-git-bypass", str(rel), n,',
            'fixture-git-bypass: a -c user.email=t@t argv outside fixture_git is a finding',  # fixture-git: exempt (the expected-fixture label quotes the identity it detects)
        ),
        Mutation(
            "fixture-git-bypass accepts an exemption with no reason",
            '_FIXTURE_EXEMPT = re.compile(r"#\\s*fixture-git:\\s*exempt\\s*\\([^)]+\\)")',
            '_FIXTURE_EXEMPT = re.compile(r"#\\s*fixture-git:\\s*exempt")',
            'fixture-git-bypass: an exemption without a reason is still a finding',
        ),
        Mutation(
            "fixture-git-bypass no longer sees an identity in --author (#1660 review R4)",
            '''                               r"""|--author["']?[\\s,=]+["']?[^"'<]*<[\\w.+-]+@[\\w.-]+>""")''',
            '''                               r"""|--author-never-matches""")''',
            'fixture-git-bypass: an email in --author outside fixture_git is a finding',
        ),
        Mutation(
            "fixture-git-bypass no longer sees an env-dict identity",
            '''                               r"""|GIT_(?:AUTHOR|COMMITTER)_EMAIL["']?\\s*[:=,]\\s*["'][\\w.+-]+@[\\w.-]+["']"""''',
            '''                               r"""|GIT_NEVER_MATCHES"""''',
            'fixture-git-bypass: a GIT_AUTHOR_EMAIL env entry outside fixture_git is a finding',
        ),
        # #1700. A path the plugin prescribes that its own docs-layout gate fails.
        Mutation(
            "a docs/<dir>/ outside LAYOUT stops being a finding",
            "                if directory not in allowed and directory not in OWN_REPO_DOCS:",
            "                if False:",
            "a command that writes docs/handoff/<slug>.md, a directory the layout lacks",
        ),
        Mutation(
            "reference documents are not scanned",
            '*sorted(plugin.glob("reference/*.md")),',
            "",
            "a reference document that names docs/acceptance/<slug>.md (model-tiers.md did, by hand-fix only)",
        ),
        Mutation(
            "a line that names the path as pre-layout is flagged too",
            '            if "pre-layout" in line:',
            "            if False:",
            "a line that says pre-layout is a fallback, not a prescription, and silent",
        ),
        Mutation(
            "a pointer to this repository's own doctrine docs is flagged",
            'OWN_REPO_DOCS = {"doctrine"}',
            "OWN_REPO_DOCS = set()",
            "a pointer to this repository's own docs/doctrine/ is silent",
        ),
        Mutation(
            "selftests and fixtures are scanned too",
            '                 if not p.name.endswith("_selftest.py")',
            "                 if True",
            "a selftest, docs_layout.py's own tables and another plugin's docs are out of scope, and silent",
        ),
        Mutation(
            "a LAYOUT nobody can read stops being a finding",
            "    if not allowed:",
            "    if False:",
            "a LAYOUT that is not a literal dict is itself a finding",
        ),
    ),
)
