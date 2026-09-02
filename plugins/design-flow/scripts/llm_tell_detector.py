#!/usr/bin/env python3
"""Offline detector for LLM design tells — design-flow (#157).

Borrowed in shape from [impeccable](https://github.com/pbakaus/impeccable), which ships ~58
rule-based detectors for "does this look like an LLM made it?". What is borrowed is the two
mechanisms that make such a tool survive contact: **every rule has a name**, so it can be argued
with and disabled individually, and **a disable must carry a reason**, so the first justified
exception does not teach everyone to switch the checker off.

WHY THIS AND NOT #107. `rendered_conformance.py` answers "does this match our token system?" and
needs Playwright plus a booted app, so it runs on demand and drift accumulates between runs. This
reads files, needs nothing, and runs on **every edit** as a PostToolUse hook. Different cadence,
different question.

THE RULE SET IS SEVEN, NOT TWELVE, AND THAT IS THE INTERESTING PART.

#157 lists twelve anti-patterns. Grounding each one against our own doctrine — which the issue's
own acceptance criteria demand, since *"a rule with no doctrine behind it is taste"* — eliminated
five of them, in two distinct ways:

  * TWO ARE PRESCRIBED BY OUR DOCTRINE. "Glassmorphism" and "pulsing" read as LLM tells in general,
    but `components.md:185` mandates `bg-fm-navy/50 backdrop-blur-sm` for the modal backdrop and
    `components.md:658` mandates `animate-pulse rounded-md bg-muted` for skeletons. A naive rule for
    either fires on our own reference implementations — which acceptance criterion 6 forbids
    outright, and rightly: a checker whose first run flags the doctrine it enforces is not a
    checker. Detecting them properly needs the *context* (is this a backdrop? a skeleton?), which a
    static scan does not have. Dropped, deliberately, and recorded here rather than silently.

  * THREE NEED RENDERED OUTPUT OR STRUCTURE WE CANNOT SEE. "Ghost-cards" is a contrast measurement,
    "status-chip soup" and "cards nested in cards" are structural judgements about a whole page, and
    "italic serif decoration" has no doctrine to cite. Contrast belongs to #107, which can measure
    it; the rest are taste until someone writes doctrine for them.

What is left is seven rules that each cite a line of doctrine, and **two of them find outright
bugs** rather than stylistic drift — classes that silently produce no CSS at all, so the markup
looks right, renders wrong, and no error is raised anywhere.

Exit codes:  0 clean · 1 findings · 2 unusable (bad input, unreadable file)

Stdlib only, no browser, no API key, no network — it must run in any clone with nothing installed,
exactly like `brand_pack_lint.py`.

Usage:
    python3 llm_tell_detector.py FILE [FILE ...]
    python3 llm_tell_detector.py --doctrine-selfcheck   # criterion 6, as a gate
    python3 llm_tell_detector.py --list-rules
    python3 llm_tell_detector.py --selftest
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
import doctrine_path                                    # noqa: E402 — same plugin, one resolver
_DOCTRINE = doctrine_path.find(os.path.join(HERE, "x.py"))
# Only `--check-doctrine` reads this; the consumer path scans the paths it is given, so an install
# that cannot resolve it is unaffected. The fallback keeps the "UNUSABLE" message pointing at the
# clone path a maintainer would recognise.
DOCTRINE_DIR = (os.path.join(str(_DOCTRINE), "references") if _DOCTRINE
                else os.path.join(REPO, "skills", "design-system", "references"))

# Criterion 7: the palette-step vocabulary is defined ONCE, in the rendered checker, whose doctrine
# constants were made module-level for exactly this import. If that import fails we do not quietly
# fall back to a private copy -- two definitions drifting apart is the defect the criterion exists
# to prevent, and a silent fallback is how it would happen.
sys.path.insert(0, HERE)
try:
    from rendered_conformance import COLOUR_UTILITIES, PALETTE_STEP
except ImportError as exc:  # pragma: no cover - environment, not logic
    print(f"UNUSABLE: cannot import shared doctrine constants from rendered_conformance: {exc}",
          file=sys.stderr)
    raise SystemExit(2)

# Tailwind's own palette families. Ours are `fm-`-prefixed (`--color-fm-slate-50` -> `fm-slate-50`),
# so `text-slate-500` is a stock literal and `text-fm-slate-500` is a token. The regex anchors the
# family directly after the utility prefix, which distinguishes them without a lookbehind.
# Criterion 7 again, and the IDE caught me breaking it: importing `PALETTE_STEP` and then
# hand-copying `(?:50|950|[1-9]00)` into the rule below IS the duplication the criterion forbids --
# two definitions that agree today and drift the first time #107 adds a step. So the alternation is
# derived from the shared pattern's own source. `PALETTE_STEP` is anchored (`-…\Z`) for matching a
# whole utility; here it is spliced mid-regex, so the anchors come off -- and if its shape ever
# changes, this fails loudly at import rather than silently matching nothing.
_STEP = PALETTE_STEP.pattern
if not (_STEP.startswith("-(?:") and _STEP.endswith(r"\Z")):
    raise SystemExit(f"UNUSABLE: PALETTE_STEP shape changed ({_STEP!r}); update the derivation")
STEP_ALTERNATION = _STEP[:-len(r"\Z")]   # keep the leading hyphen: `gray` + `-500`, not `gray500`

STOCK_FAMILIES = (
    "slate", "gray", "zinc", "neutral", "stone", "red", "orange", "amber", "yellow", "lime",
    "green", "emerald", "teal", "cyan", "sky", "blue", "indigo", "violet", "purple", "fuchsia",
    "pink", "rose",
)

# `--ease-*` IS a Tailwind v4 theme namespace, so `ease-out`/`ease-in` resolve to OUR curves
# (motion.md:53-55). Only these two are in `@theme`; anything else silently takes Tailwind's stock
# default and leaves the motion doctrine unapplied.
TOKEN_EASINGS = ("out", "in")

# There is no `--duration-*` namespace (motion.md:56-59), so a named duration class does not exist.
# Numeric (`duration-150`) and custom-property (`duration-(--duration-fast)`) forms are correct.
DURATION_NAMES = ("fast", "base", "slow", "slower", "instant", "moderate")

DISABLE = re.compile(
    r"(?:<!--|//|#|/\*)\s*design-flow-disable\s+([a-z0-9-]+)\s*(?::\s*(?P<reason>[^\n>*/]*))?")


# A comment is prose that happens to live in a code block, and doctrine forbidding a pattern has to
# NAME it -- `component-implementations.md:353` literally reads "NOT an arbitrary `rounded-[12px]`".
# `#` only counts followed by whitespace, so a CSS hex (`#0C1B33`) or id selector is not a comment.
COMMENT_LINE = re.compile(r"^\s*(?:#\s|//|\*|/\*|<%#|<!--(?!\s*design-flow-disable))")

# `--color-fm-navy: #0C1B33` is not a raw-hex violation: a custom-property declaration IS the token
# layer the rule protects. Anchored to the end of the text BEFORE the match, so a line declaring
# several tokens exempts each one rather than only the first.
TOKEN_DEFINITION = re.compile(r"--[A-Za-z0-9-]+\s*:\s*\Z")


def _defines_a_token(line: str, match: re.Match) -> bool:
    """True when the hex is the VALUE of a custom property.

    The subtlety that made the first version a no-op: the rule's pattern starts at the property
    NAME (`color…`), so in `--color-fm-navy: #0C1B33` the text before the match is just `--`, not
    `--color-fm-navy:`. Both shapes are checked, so a declaration reached either way is exempt,
    while `style="color: #fff"` — where nothing precedes but the attribute — still fires.
    """
    before = line[:match.start()].rstrip()
    return before.endswith("--") or bool(TOKEN_DEFINITION.search(before))


@dataclass(frozen=True)
class Rule:
    name: str
    doctrine: str          # the file:line this enforces -- criterion 3
    message: str
    pattern: re.Pattern
    # A rule may need to reject one of its own matches. Kept as a predicate rather than a fatter
    # regex because the reason is usually a doctrine carve-out that deserves a sentence.
    exempt: object = None


def _rules() -> tuple[Rule, ...]:
    return (
        # ---- silently-produces-nothing: outright bugs, not style -----------------------------
        Rule(
            "v3-gradient-utility",
            "visual-assets.md:32",
            "`bg-gradient-to-*` was REMOVED in Tailwind v4 with no compatibility alias, so this "
            "produces no class at all -- silently. Use `bg-linear-to-*`",
            re.compile(r"\bbg-gradient-to-(?:t|b|l|r|tl|tr|bl|br)\b"),
        ),
        Rule(
            "nonexistent-duration-utility",
            "motion.md:56-59",
            "there is no `--duration-*` theme namespace, so this class does not exist and emits "
            "nothing. Use `duration-(--duration-fast)` or a number",
            # `(?<![-\w])` so the CORRECT form does not flag itself: `duration-(--duration-fast)`
            # contains `duration-fast` as a substring, and matching it would make the documented fix
            # a finding -- the surest way to get a rule switched off.
            re.compile(r"(?<![-\w])duration-(?:" + "|".join(DURATION_NAMES) + r")\b"),
        ),
        # ---- roles and scale steps, never literal values (brand.md:165) ----------------------
        Rule(
            "stock-palette-literal",
            "brand.md:165",
            "a stock Tailwind palette step instead of a role token -- this is what 'AI beige' and "
            "'gray text on a coloured background' look like in markup. Use a role "
            "(`text-foreground`, `bg-muted`) or an `fm-` token",
            re.compile(r"\b(?:" + "|".join(COLOUR_UTILITIES) + r")-(?:"
                       + "|".join(STOCK_FAMILIES) + r")" + STEP_ALTERNATION + r"\b"),
        ),
        Rule(
            "raw-hex-literal",
            "brand.md:165",
            "a raw hex colour bypasses the token layer entirely, so it cannot theme and cannot go "
            "dark. Bind a role or an `fm-` token",
            # Only arbitrary values and inline styles. A bare `#` elsewhere is an anchor or an id.
            re.compile(r"\[#[0-9a-fA-F]{3,8}\]|(?:color|background|border|fill|stroke)"
                       r"[^;\"']*:\s*#[0-9a-fA-F]{3,8}"),
            exempt=_defines_a_token,
        ),
        Rule(
            # #758. A stock step (`text-gray-500`) was caught and a BRAND PRIMITIVE used the same way
            # was silent -- and the silent one is worse. `text-gray-500` announces itself as foreign;
            # `text-fm-slate-400` looks correct, because it IS a brand token, spelled the brand's way.
            # It is simply one layer too low: `.dark` re-points ROLES, so a primitive stays light-mode
            # in dark mode; `check_token_contrast`'s PAIRS enumerate role-on-role, so nothing ever
            # measures it; and a second brand cannot re-tune it.
            #
            # Live evidence: two artboards of one project disagreed on `--slate-400` (#8F96A3 vs
            # #5E6775) because two call sites used the 400 as TEXT, found it illegible on warm paper
            # (2.78:1, fails AA) and darkened the TOKEN rather than moving to `--slate-500`. No value
            # of "400" fixes that -- a light neutral is not a text colour, and making it one makes it
            # a 500. The disagreement was the symptom; this is the cause.
            #
            # `exempt=_defines_a_token` is the load-bearing part: a pack BINDING a primitive to a role
            # (`--primary: var(--color-fm-cerulean)`) is the role layer doing its job, and a rule that
            # fired on that would be switched off within a week.
            "primitive-as-role",
            "brand.md:165",
            "a brand PRIMITIVE used as a component colour bypasses the role layer, so it cannot go "
            "dark, cannot be re-tuned per brand, and appears in no contrast pair. Bind the role "
            "(`text-muted-foreground`, `bg-card`) instead",
            # NOT `-fm-[a-z]+-\d+`: that requires a numeric step and so missed `bg-fm-navy`, which
            # is the exact usage #750 reported (a modal reaching for `bg-fm-navy/50` because
            # `--overlay` did not exist). Unstepped primitives are the commoner misuse, not the
            # rarer one. `-fm-` is unambiguous: no role carries that prefix.
            re.compile(r"\b(?:" + "|".join(COLOUR_UTILITIES) + r")-fm-[a-z0-9-]+\b"
                       r"|var\(\s*--color-fm-[a-z0-9-]+\s*\)"),
            exempt=_defines_a_token,
        ),
        Rule(
            # #738. Measured absent: `grep -rn googleapis plugins/design-flow skills/design-system`
            # found only an unrelated API URL, while BOTH Claude Design artboards read from a real
            # project carry a `fonts.googleapis.com` link. A canvas export ships one as a preview
            # convenience; carried into a commit it costs a render-blocking third-party request, a
            # FOUT the self-hosted stack does not have, and a privacy hop nobody chose.
            #
            # Matched on the HOST, not on `<link>`, because the same import arrives as `@import`, as
            # a `preconnect`, and inside an inline `<style>` -- and one shape missed is the one that
            # ships. `gstatic` is the font-file host the stylesheet then pulls from, so a page can
            # carry it without ever naming googleapis.
            "cdn-font-link",
            "design-handoff.md:2",
            "a CDN font link is preview scaffolding from a design export, not something that ships. "
            "Fonts are self-hosted; drop the link and let the font roles resolve",
            re.compile(r"fonts\.googleapis\.com|fonts\.gstatic\.com"),
        ),
        Rule(
            "literal-font-family",
            "brand.md:263",
            "a literal font family bypasses the font-role layer (`--font-sans` / `--font-display`), "
            "so a brand pack cannot change it. This is the 'Inter for everything' tell",
            # #782. The second alternation was a bare `font-family\s*:`, unanchored to any VALUE,
            # so it fired on the exact role-token form the message tells you to use -- every
            # conformant stylesheet, once per declaration, on every save via the PostToolUse hook.
            # A checker that flags the correct form is the false positive this file's own docstring
            # says gets it switched off.
            #
            # The obvious narrowing does NOT work and the report measured it: `font-family\s*:\s*
            # (?!var\()` still matches, because `\s*` backtracks to zero width and the lookahead is
            # then evaluated at the space before `var(`. Scan the VALUE instead --
            # `(?![^;}]*var\()` looks ahead to the end of the declaration -- which also lets the
            # `font:` shorthand share the branch, closing a path where a genuine literal was silent.
            re.compile(r"font-\[[\"']?[A-Za-z]|font(?:-family)?\s*:(?![^;}]*var\()"),
        ),
        Rule(
            "off-scale-radius",
            "brand.md:162",
            "an arbitrary radius sits outside the pack's declared radius language "
            "(`md-controls-lg-cards` or `soft`), which is a per-brand knob. Use the scale step",
            re.compile(r"\brounded(?:-[a-z]+)?-\[[^\]]+\]"),
        ),
        # ---- motion doctrine ------------------------------------------------------------------
        Rule(
            "non-token-easing",
            "motion.md:43-49",
            "only `--ease-out` and `--ease-in` are in `@theme`, so any other easing silently takes "
            "Tailwind's stock curve. `ease-in-out` also violates 'never use one curve for both'",
            # No negative lookahead for the token easings: `ease-in-out` starts with `ease-in`, and
            # `\b` matches before the hyphen, so a `(?!ease-in)` guard silently excused the single
            # most common instance of this tell. The explicit alternation cannot match `ease-out`
            # or `ease-in` on their own, which is the property that was actually wanted.
            re.compile(r"\bease-(?:in-out|linear|initial)\b"),
        ),
    )


RULES: tuple[Rule, ...] = _rules()


def unfixtured_rules(exercised: set[str], names: "list[str] | None" = None) -> list[str]:
    """Rules the selftest never exercised. A callable, deliberately (#738).

    Written inline first, and the mutation that removed it SURVIVED: with every rule fixtured, the
    assertion never fires in a healthy tree, so nothing could distinguish it being there from it
    being gone. The fixture has to call it with a synthetic set. Same shape as
    `maintainer_doctor.gate_results` — logic a test can only re-derive is logic no test proves.
    """
    return sorted(set(names if names is not None else BY_NAME) - exercised)
BY_NAME = {r.name: r for r in RULES}


@dataclass
class Finding:
    rule: str
    path: str
    line: int
    text: str
    message: str
    doctrine: str

    def __str__(self) -> str:
        return (f"  {self.path}:{self.line}  [{self.rule}]\n"
                f"      {self.text.strip()[:96]}\n"
                f"      {self.message} ({self.doctrine})")


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    bare_disables: list[Finding] = field(default_factory=list)
    files: int = 0
    lines: int = 0
    suppressed: int = 0


def _disables(line: str, previous: str) -> tuple[set[str], set[str]]:
    """(rules disabled WITH a reason, rules disabled with NO reason).

    A bare disable is itself a finding -- borrowed from impeccable, and the mechanism
    `brand_pack_lint.py` lacks. Without it the first justified exception gets written as a blanket
    switch-off, and every later one copies it.
    """
    ok: set[str] = set()
    bare: set[str] = set()
    for source in (line, previous):
        for match in DISABLE.finditer(source):
            reason = (match.group("reason") or "").strip().rstrip("-->").strip()
            (ok if len(reason) >= 3 else bare).add(match.group(1))
    return ok, bare


def _font_face_state(line: str, was_inside: bool) -> tuple[bool, bool]:
    """(state for the NEXT line, whether THIS line sits in an @font-face block).

    ONE implementation, called by both scanners. The markdown scanner having its own copy of a
    judgement is the exact divergence this module already paid for once -- it did not call
    `rule.exempt`, so our own token file reported raw-hex violations the `.css` path exempted.
    Adding the block tracking to `scan_text` alone would have rebuilt that: `--doctrine-selfcheck`
    flagged the `@font-face` example in `brand.md` while the same block in a `.css` file was fine.

    Depth is not tracked because `@font-face` bodies do not nest -- they hold declarations, not
    rules -- so a `}` closes, which also handles the one-line form.
    """
    if "@font-face" in line:
        return "}" not in line.split("@font-face", 1)[1], True
    if was_inside:
        return "}" not in line, True
    return False, False


# Rules a self-hosted `@font-face` block legitimately violates. Naming a literal family is the
# WHOLE POINT of such a block -- `cdn-font-link`'s message says "Fonts are self-hosted", so the two
# rules would otherwise demand opposite things. Kept as an explicit set rather than a general
# block-context mechanism because exactly one rule needs it, and a general mechanism with one user
# is harder to reason about than a named exception (#782).
FONT_FACE_RULES = frozenset({"literal-font-family"})


def _scan_line(line: str, previous: str, path: str, index: int, report: Report,
               *, bare_is_a_finding: bool = True, in_font_face: bool = False) -> None:
    """The ONE place a line is judged.

    This was two near-identical loops, and they had already drifted: the markdown scanner never
    called `rule.exempt`, so every `--color-fm-navy: #0C1B33` in our own token file came back as a
    raw-hex violation while the same line in a `.css` file was correctly exempt. Fixing the copy
    would have left the next divergence to find later, so there is no copy now.
    """
    if COMMENT_LINE.match(line):
        return
    allowed, bare = _disables(line, previous)
    if bare_is_a_finding:
        for name in sorted(bare):
            if name in BY_NAME:
                report.bare_disables.append(Finding(
                    "bare-disable", path, index, line,
                    f"`design-flow-disable {name}` carries no reason. A disable without one is a "
                    f"finding: write `design-flow-disable {name}: why`", "#157"))
    for rule in RULES:
        if rule.name in allowed:
            report.suppressed += 1
            continue
        match = rule.pattern.search(line)
        if not match:
            continue
        if rule.exempt and rule.exempt(line, match):
            continue
        # The ONE-LINE form is handled by the rule's own exempt; this covers the multi-line block,
        # which is how every project that follows the self-hosting doctrine actually writes it. A
        # `previous`-only check would not do: the declaration need not be the block's first line.
        if in_font_face and rule.name in FONT_FACE_RULES:
            continue
        report.findings.append(
            Finding(rule.name, path, index, line, rule.message, rule.doctrine))


def scan_text(text: str, path: str, report: Report) -> None:
    lines = text.splitlines()
    report.files += 1
    report.lines += len(lines)
    in_font_face = False
    for index, line in enumerate(lines, 1):
        in_font_face, here = _font_face_state(line, in_font_face)
        _scan_line(line, lines[index - 2] if index >= 2 else "", path, index, report,
                   in_font_face=here)


# `js` must not match the `js` in ```json -- the boundary bug this repo already fixed once in
# lint_markdown_code.py. Same shape, so the same `\b`.
FENCE = re.compile(r"^\s*```\s*(erb|html|html\+erb|ruby|rb|css|jsx?|tsx?)\b", re.I)
FENCE_END = re.compile(r"^\s*```\s*$")


def scan_markdown_blocks(text: str, path: str, report: Report) -> None:
    """Only fenced code, never prose.

    Doctrine that FORBIDS a pattern necessarily names it -- `visual-assets.md` spells out
    `bg-gradient-to-*` in the very sentence explaining that it was removed. Scanning prose would
    make our own doctrine the checker's biggest source of findings.
    """
    lines = text.splitlines()
    report.files += 1
    inside = False
    in_font_face = False
    for index, line in enumerate(lines, 1):
        if not inside and FENCE.match(line):
            inside = True
            continue
        if inside and FENCE_END.match(line):
            inside = False
            continue
        if not inside:
            continue
        report.lines += 1
        in_font_face, here = _font_face_state(line, in_font_face)
        _scan_line(line, lines[index - 2] if index >= 2 else "", path, index, report,
                   bare_is_a_finding=False, in_font_face=here)


SCANNABLE = (".erb", ".html", ".rb", ".css", ".js", ".jsx", ".ts", ".tsx", ".vue", ".slim", ".haml")


def scan_path(path: str, report: Report) -> None:
    try:
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise SystemExit(f"UNUSABLE: cannot read {path}: {exc}")
    if path.endswith(".md"):
        scan_markdown_blocks(text, path, report)
    else:
        scan_text(text, path, report)


def doctrine_selfcheck() -> int:
    """Criterion 6: zero findings against our own reference implementations.

    Gateable, and the honest direction of the test -- if `component-implementations.md` trips a
    rule, either the rule is wrong or the doctrine is, and both are worth knowing before this runs
    in anyone's project.
    """
    if not os.path.isdir(DOCTRINE_DIR):
        print(f"UNUSABLE: doctrine directory not found: {DOCTRINE_DIR}", file=sys.stderr)
        return 2
    report = Report()
    for name in sorted(os.listdir(DOCTRINE_DIR)):
        if name.endswith(".md"):
            scan_path(os.path.join(DOCTRINE_DIR, name), report)
    rel = os.path.relpath(DOCTRINE_DIR, REPO)
    if report.findings:
        print(f"{len(report.findings)} finding(s) against our own doctrine in {rel} —\n"
              f"either a rule is wrong or the doctrine is. Both matter; neither is 'tune the rule'.")
        for finding in report.findings:
            print(finding)
        return 1
    print(f"doctrine self-check: {report.files} reference file(s), {report.lines} fenced code "
          f"line(s), 0 findings across {len(RULES)} rule(s).")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline detector for LLM design tells.")
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--doctrine-selfcheck", action="store_true")
    parser.add_argument("--list-rules", action="store_true")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--quiet", action="store_true", help="findings only, no summary")
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()
    if args.list_rules:
        for rule in RULES:
            print(f"  {rule.name:30} {rule.doctrine:22} {rule.message[:60]}")
        return 0
    if args.doctrine_selfcheck:
        return doctrine_selfcheck()
    if not args.paths:
        parser.error("give at least one path, or --doctrine-selfcheck / --list-rules / --selftest")

    report = Report()
    for path in args.paths:
        if os.path.isdir(path):
            for root, _dirs, names in os.walk(path):
                for name in sorted(names):
                    if name.endswith(SCANNABLE):
                        scan_path(os.path.join(root, name), report)
        else:
            scan_path(path, report)

    for finding in report.findings + report.bare_disables:
        print(finding)
    total = len(report.findings) + len(report.bare_disables)
    if not args.quiet:
        note = f", {report.suppressed} suppressed with a reason" if report.suppressed else ""
        print(f"\n{total} finding(s) across {report.files} file(s), {report.lines} line(s){note}.")
    return 1 if total else 0


def selftest() -> int:
    failures: list[str] = []
    checks = 0

    # Which rules a fixture actually exercised. #738: a new rule landed with NO fixture and the
    # selftest still reported green, because nothing asserted the set was complete -- a suite that
    # reports clean over a rule it never ran is the coverage-gap class this repo files most.
    exercised: set[str] = set()

    def case(label: str, source: str, *, rule: str, expect: bool) -> None:
        nonlocal checks
        exercised.add(rule)
        checks += 1
        report = Report()
        scan_text(source, "t.erb", report)
        hit = any(f.rule == rule for f in report.findings + report.bare_disables)
        if hit != expect:
            failures.append(f"{label}: expected {'a finding' if expect else 'silence'} for {rule}")

    # ---- each rule FIRES -------------------------------------------------------------------
    case("v3 gradient", '<div class="bg-gradient-to-r from-fm-navy">',
         rule="v3-gradient-utility", expect=True)
    case("named duration", '<div class="transition duration-fast">',
         rule="nonexistent-duration-utility", expect=True)
    case("stock palette", '<p class="text-gray-500">hi</p>', rule="stock-palette-literal", expect=True)
    case("stock palette behind a variant", '<p class="hover:bg-slate-900">',
         rule="stock-palette-literal", expect=True)
    case("arbitrary hex", '<p class="text-[#ff0000]">', rule="raw-hex-literal", expect=True)
    case("inline style hex", '<p style="color: #abc">', rule="raw-hex-literal", expect=True)
    case("literal font", "<p class=\"font-['Inter']\">", rule="literal-font-family", expect=True)
    case("arbitrary radius", '<div class="rounded-[13px]">', rule="off-scale-radius", expect=True)
    case("ease-in-out", '<div class="transition ease-in-out">', rule="non-token-easing", expect=True)
    case("ease-linear", '<div class="ease-linear">', rule="non-token-easing", expect=True)

    # ---- the SILENT half, which decides whether anyone leaves this switched on ----------------
    # Our own tokens must never trip the palette rule. `fm-slate-500` shares the family NAME with
    # Tailwind's `slate`, so this is the near-miss that a lazier regex fails.
    case("our own fm- token", '<p class="text-fm-slate-500">', rule="stock-palette-literal", expect=False)
    case("a role token", '<p class="text-foreground bg-muted">', rule="stock-palette-literal", expect=False)
    case("the v4 gradient name", '<div class="bg-linear-to-r">', rule="v3-gradient-utility", expect=False)
    case("numeric duration", '<div class="duration-150">',
         rule="nonexistent-duration-utility", expect=False)
    case("custom-property duration", '<div class="duration-(--duration-fast)">',
         rule="nonexistent-duration-utility", expect=False)
    # `ease-out` and `ease-in` ARE our tokens -- Tailwind v4's `--ease-*` namespace means our
    # @theme definitions override the stock curves. Flagging them would be exactly backwards.
    case("ease-out is our token", '<div class="ease-out">', rule="non-token-easing", expect=False)
    case("ease-in is our token", '<div class="ease-in">', rule="non-token-easing", expect=False)
    case("radius scale step", '<div class="rounded-lg">', rule="off-scale-radius", expect=False)
    case("an anchor is not a colour", '<a href="#main">skip</a>', rule="raw-hex-literal", expect=False)
    # The token-definition carve-out, in both directions. A custom property IS the token layer the
    # rule protects, so hex belongs there and nowhere else. Without the negative case the exemption
    # could widen to "any line with a colon" and nothing would notice.
    case("a token definition is where hex belongs", "  --color-fm-navy: #0C1B33;",
         rule="raw-hex-literal", expect=False)
    case("several definitions on one line are all exempt",
         "  --color-fm-navy: #0C1B33;  --color-fm-ink: #1A2B45;", rule="raw-hex-literal", expect=False)
    case("a plain declaration is NOT a token definition", "  background: #6366f1;",
         rule="raw-hex-literal", expect=True)
    case("a font role utility", '<p class="font-sans">', rule="literal-font-family", expect=False)

    # ---- #782. The SILENT half this rule never had -------------------------------------------
    # It matched a bare `font-family\s*:` with no regard for the value, so it fired on the exact
    # form its own message tells you to use. Both gates were quiet: no fixture covered the CSS
    # declaration, and `--doctrine-selfcheck` cannot help because not one reference file contains a
    # `font-family` declaration -- a criterion-6 gate is only as good as the doctrine's examples.
    case("a sans role token is NOT a literal", "h1 { font-family: var(--font-display); }",
         rule="literal-font-family", expect=False)
    case("a mono role token is NOT a literal", "code { font-family: var(--font-mono); }",
         rule="literal-font-family", expect=False)
    case("the shorthand with a role token is NOT a literal",
         "p { font: 400 15px/1.6 var(--font-sans); }",
         rule="literal-font-family", expect=False)
    # A self-hosted @font-face MUST name a literal family -- that is what `cdn-font-link`'s
    # "Fonts are self-hosted" message asks for, so without this the two rules demand opposites.
    case("a one-line @font-face names a real family",
         '@font-face{font-family:Newsreader;src:url("/f.woff2") format("woff2")}',
         rule="literal-font-family", expect=False)
    case("...and so does the multi-line form, declaration not first",
         '@font-face {\n  src: url("/f.woff2") format("woff2");\n  font-family: "NotoSans";\n}',
         rule="literal-font-family", expect=False)
    # THE POSITIVES, so none of the above is satisfied by a rule that stopped firing.
    case("a real literal still trips", 'h1 { font-family: "Inter", sans-serif; }',
         rule="literal-font-family", expect=True)
    case("the shorthand hides a literal too", 'p { font: 400 15px/1.6 "Inter", sans-serif; }',
         rule="literal-font-family", expect=True)
    # ...and the block must CLOSE, or everything after a @font-face would be exempt for the rest
    # of the file -- the widest possible false negative, and the risk this fix introduces.
    case("a literal AFTER a closed @font-face still trips",
         '@font-face {\n  font-family: "NotoSans";\n}\nh1 { font-family: "Inter", sans-serif; }',
         rule="literal-font-family", expect=True)
    # BOTH closing shapes, because they are different branches. The multi-line block above closes on
    # its own `}` line; a ONE-LINE @font-face closes on the same line it opens, and a mutation
    # forcing the flag to stay on survived the multi-line fixture alone -- it would have exempted
    # every literal in the rest of the file.
    case("...and after a ONE-LINE @font-face too",
         '@font-face{font-family:Newsreader;src:url("/f.woff2")}\n'
         'h1 { font-family: "Inter", sans-serif; }',
         rule="literal-font-family", expect=True)
    # The two tells our doctrine PRESCRIBES. If a future rule starts flagging these, the run goes
    # red here rather than in someone's project.
    case("prescribed modal backdrop", '<div class="bg-fm-navy/50 backdrop-blur-sm">',
         rule="stock-palette-literal", expect=False)
    case("prescribed skeleton", '<div class="animate-pulse rounded-md bg-muted">',
         rule="off-scale-radius", expect=False)

    # ---- the escape hatch ---------------------------------------------------------------------
    case("a disable with a reason suppresses",
         '<!-- design-flow-disable stock-palette-literal: third-party embed dictates it -->\n'
         '<p class="text-gray-500">',
         rule="stock-palette-literal", expect=False)
    case("a BARE disable is itself a finding",
         '<!-- design-flow-disable stock-palette-literal -->\n<p class="text-gray-500">',
         rule="bare-disable", expect=True)
    # ...and it must not ALSO suppress. A bare disable that silenced the rule would be strictly
    # better for the writer than a justified one, which inverts the incentive the hatch exists for.
    case("a bare disable does not suppress the rule it names",
         '<!-- design-flow-disable stock-palette-literal -->\n<p class="text-gray-500">',
         rule="stock-palette-literal", expect=True)
    case("a disable for a DIFFERENT rule does not suppress this one",
         '<!-- design-flow-disable off-scale-radius: cropped asset -->\n<p class="text-gray-500">',
         rule="stock-palette-literal", expect=True)

    # ---- primitive-as-role (#758) -------------------------------------------------------
    # The shape that was silent while the stock-palette equivalent was caught.
    case("a brand primitive as a text utility", '<p class="text-fm-slate-400">hi</p>',
         rule="primitive-as-role", expect=True)
    case("...and as a background utility", '<div class="bg-fm-navy">',
         rule="primitive-as-role", expect=True)
    case("...and through var() in an inline style",
         '<p style="color: var(--color-fm-slate-400)">hi</p>',
         rule="primitive-as-role", expect=True)
    # THE CARVE-OUT, and the reason the rule survives contact with a real pack: BINDING a primitive
    # to a role is the role layer working. A rule firing here gets switched off within a week.
    case("...silent when a role BINDS the primitive",
         "  --primary: var(--color-fm-cerulean);", rule="primitive-as-role", expect=False)
    case("...silent on the primitive's own declaration",
         "  --color-fm-navy: #0C1B33;", rule="primitive-as-role", expect=False)
    case("...silent on a role utility, which is the correct form",
         '<p class="text-muted-foreground">hi</p>', rule="primitive-as-role", expect=False)

    # ---- cdn-font-link (#738) ---------------------------------------------------------------
    # Both Claude Design artboards read from a real project carry one of these. A canvas export
    # ships it as a preview convenience; carried into a commit it is a render-blocking third-party
    # request the self-hosted stack does not have.
    case("a Google Fonts stylesheet link",
         '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Newsreader">',
         rule="cdn-font-link", expect=True)
    # The same import arrives in three other shapes, and one shape missed is the one that ships.
    case("...a preconnect to the font FILE host",
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
         rule="cdn-font-link", expect=True)
    case("...an @import inside a style block",
         "@import url('https://fonts.googleapis.com/css2?family=Inter');",
         rule="cdn-font-link", expect=True)
    # SILENCE ON CORRECT WORK. Self-hosting is the sanctioned shape and must never fire, or the rule
    # gets switched off by the people who did it right.
    case("...silent on a self-hosted @font-face",
         "@font-face{font-family:Newsreader;src:url('/fonts/newsreader.woff2') format('woff2')}",
         rule="cdn-font-link", expect=False)
    case("...silent on an unrelated googleapis API host",
         'const url = "https://generativelanguage.googleapis.com/v1beta/models";',
         rule="cdn-font-link", expect=False)

    # ---- markdown scans code, never prose ------------------------------------------------------
    checks += 1
    report = Report()
    scan_markdown_blocks(
        "Never write `bg-gradient-to-r`, it was removed in v4.\n", "d.md", report)
    if report.findings:
        failures.append("prose naming a forbidden utility must not be a finding")
    checks += 1
    report = Report()
    scan_markdown_blocks('```erb\n<div class="bg-gradient-to-r">\n```\n', "d.md", report)
    if not report.findings:
        failures.append("a fenced erb block must be scanned")
    # The `js`-inside-`json` boundary bug, fixed once already in lint_markdown_code.py.
    checks += 1
    report = Report()
    scan_markdown_blocks('```json\n{"a": "bg-gradient-to-r"}\n```\n', "d.md", report)
    if report.findings:
        failures.append("a json fence must not be scanned as js")

    # ---- every rule cites doctrine (criterion 3), and names are unique (criterion 2) ----------
    checks += 1
    # EVERY RULE NEEDS A FIXTURE IN BOTH DIRECTIONS -- firing is half a rule. A rule nobody proved
    # silent on correct input is one that gets switched off the first time it is wrong.
    # Called with a synthetic set, so the check is proven rather than merely present.
    checks += 1
    if unfixtured_rules({"a"}, ["a", "b"]) != ["b"]:
        failures.append("unfixtured_rules must name a rule with no fixture")
    checks += 1
    if unfixtured_rules({"a", "b"}, ["a", "b"]) != []:
        failures.append("unfixtured_rules must stay silent when every rule is fixtured")

    checks += 1
    unexercised = unfixtured_rules(exercised)
    if unexercised:
        failures.append(f"rule(s) with no selftest fixture: {unexercised} — a rule the suite never "
                        f"runs is reported green without being checked")

    if len(BY_NAME) != len(RULES):
        failures.append("rule names are not unique")
    for rule in RULES:
        checks += 1
        if not re.match(r"\A[a-z0-9-]+\.md:\d", rule.doctrine):
            failures.append(f"{rule.name}: doctrine citation {rule.doctrine!r} is not file:line")

    if failures:
        print(f"SELFTEST FAILED — {len(failures)} of {checks} checks:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"llm_tell_detector selftest: {checks} checks passed across {len(RULES)} rules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
