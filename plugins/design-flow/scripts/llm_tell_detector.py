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
DOCTRINE_DIR = os.path.join(REPO, "skills", "fidara-design", "references")

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
            "literal-font-family",
            "brand.md:263",
            "a literal font family bypasses the font-role layer (`--font-sans` / `--font-display`), "
            "so a brand pack cannot change it. This is the 'Inter for everything' tell",
            re.compile(r"font-\[[\"']?[A-Za-z]|font-family\s*:"),
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


def _scan_line(line: str, previous: str, path: str, index: int, report: Report,
               *, bare_is_a_finding: bool = True) -> None:
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
        report.findings.append(
            Finding(rule.name, path, index, line, rule.message, rule.doctrine))


def scan_text(text: str, path: str, report: Report) -> None:
    lines = text.splitlines()
    report.files += 1
    report.lines += len(lines)
    for index, line in enumerate(lines, 1):
        _scan_line(line, lines[index - 2] if index >= 2 else "", path, index, report)


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
        _scan_line(line, lines[index - 2] if index >= 2 else "", path, index, report,
                   bare_is_a_finding=False)


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

    def case(label: str, source: str, *, rule: str, expect: bool) -> None:
        nonlocal checks
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
