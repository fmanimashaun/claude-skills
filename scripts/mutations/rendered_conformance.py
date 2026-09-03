"""Mutation guard: rendered_conformance. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="rendered_conformance",
    subject="plugins/design-flow/scripts/rendered_conformance.py",
    selftest="plugins/design-flow/scripts/rendered_conformance.py",
    # The selftest `node --check`s the shipped collector, which lives beside the subject.
    # Without this the mutant's collector is missing, every run fails on that fixture, and
    # every mutation reads as caught by the wrong one.
    needs=("plugins/design-flow/scripts/conformance_collector.js",),
    mutations=(
        # #829. The skip returned 0, which the doctor renders as PASS.
        Mutation(
            "an absent node exits 0 again, so the doctor prints ok for a check that did not run",
            "        # check everything\", which the doctor renders as SKIP with this line as the reason.\n        return 3",
            "        return 0",
            "an absent node skips instead of failing",
        ),

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
)
