#!/usr/bin/env python3
"""Reject a work order an executor cannot run from -- and an agent whose model contradicts doctrine.

Run:  python3 check_handoff.py docs/handoff/<slug>.md
      python3 check_handoff.py docs/handoff/<slug>.md --criteria docs/acceptance/<slug>.md
      python3 check_handoff.py --agents <plugin>/agents --tiers <plugin>/reference/model-tiers.md
      python3 check_handoff.py --selftest

WHY (rails-flow #127, and the rails-flow half of #128). `/rails-flow:handoff` writes
`docs/handoff/<slug>.md`: the one file an executor reads instead of the conversation. It makes three
promises a reader cannot check by reading it, and each has a way of failing that looks fine:

  1. **"Self-contained by construction."** A work order saying "the scope we discussed" reads as
     complete to whoever was in the discussion, and is unusable to the fresh session, the second
     machine, and the subagent that never saw it. The author is the one person who cannot see it.
  2. **"Stop conditions."** "Stop when you are stuck" cannot be evaluated *by the thing that is
     stuck*. Without a number, a stop condition is a sentiment -- the same unfalsifiable shape
     `check_criteria.py` rejects in "login works", moved from the goal to the guardrail.
  3. **"Agent frontmatter reconciled with the tier table."** A table in a markdown file and ten
     `model:` lines in ten other files agree only on the day someone checks. #127 exists *because*
     they had already drifted into folklore.

All three are the `claims-vs-enforcement` class from the bundled `code-review` skill: a guarantee
stated in prose with nothing making it true. So they become a check.

WHAT THIS GUARANTEES
    A work order carries all eight sections; declares scope in AND out; states a numeric attempt
    cap, no-progress detector, blast-radius cap and budget; forbids all four escapes (test
    weakening, revert-to-unblock, scope creep, guardrail disabling); every verification step names
    something runnable; every cited `AC-n` exists in the acceptance file; the criteria are cited and
    not restated; and nothing points at a conversation or is left as `<placeholder>`/`TBD`.
    In tier mode: every agent's `model:` matches the tier table, every agent appears in it, no row
    is stale, no row pins a model above the session, and every cheap pin names its external proof.

WHAT IT DOES NOT
    It cannot tell whether the goal is the RIGHT goal, whether the scope is big enough, or whether
    3 attempts is the wise number -- only that a falsifiable number is there. It cannot tell that
    an in-scope path exists or that the verify commands pass. It does not require every criterion in
    the acceptance file to be cited: a work order legitimately covers one unit of a larger plan.
    Without `--criteria` the cheap-tier dependency (external proof) is UNVERIFIED rather than
    satisfied, which is why `/rails-flow:handoff` always passes the flag.
    The tier vocabulary is deliberately two values wide (`judgement`/`inherit`,
    `mechanical`/`haiku`), because those are the two the mechanism can defend -- see EXTERNAL CLAIMS.
    A project wanting a third forks the table and points `--tiers` at its own copy.

EXTERNAL CLAIMS THIS ENCODES, AND THEIR SOURCES (verified 2026-07-31)
    * The subagent `model` field takes "`sonnet`, `opus`, `haiku`, `fable`, a full model ID (for
      example, `claude-opus-5`), or `inherit`. Defaults to `inherit`", and frontmatter beats the
      session model: resolution is `CLAUDE_CODE_SUBAGENT_MODEL`, then the per-invocation parameter,
      then "the subagent definition's `model` frontmatter", then "the main conversation's model".
      So a pin is a CAP -- which is why judgement agents must say `inherit`.
      https://code.claude.com/docs/en/sub-agents
    * Pinning UP mostly buys nothing: Claude Code "skips a value that resolves to an excluded model
      and runs the subagent on the inherited model instead" when it is outside the organization's
      `availableModels` allowlist.  (same page)
    * `model` IS honoured for plugin agents -- only "`hooks`, `mcpServers`, or `permissionMode`" are
      ignored there.  (same page)
    * An alias is a per-provider lookup that moves: `sonnet` is Sonnet 5 on the Anthropic API but
      Sonnet 4.5 on Amazon Bedrock and Microsoft Foundry, and "Aliases point to the recommended
      version for your provider and update over time".  https://code.claude.com/docs/en/model-config
    * `maxTurns` is "Maximum number of agentic turns before the subagent stops" -- a turn bound, not
      an attempt bound, so it complements the attempt cap.  (sub-agents page)

    NOT claimed, because checking said otherwise: there is no "mid" model tier to select. #127's
    three-row table (strongest/mid/cheapest) has no mechanism -- the middle row is `effort`
    (`low`..`max`), a separate field. And no effort level is asserted for any model, because
    "available levels depend on the model" and Claude Code does not publish which.

Exit codes:  0 clean · 1 findings · 2 unusable input (no file / not a work order / no tier table)

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SECTION_RE = re.compile(r"^\s{0,3}##\s+(?P<text>.*\S)\s*$")
SUBSECTION_RE = re.compile(r"^\s{0,3}###\s+(?P<text>.*\S)\s*$")
FENCE_RE = re.compile(r"^\s*(?P<ticks>`{3,})")
STEP_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?P<text>\S.*)$")
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
# A command, a path, a route or a URL -- the same "is this runnable" test check_guide.py applies to
# the guide's "Check it yourself" steps, for the same reason: a step nobody can run is a sentiment.
# It requires an EXTENSION on a relative path, so "and/or" in a sentence is not read as a file.
RUNNABLE_RE = re.compile(r"https?://\S+|(?:^|\s)/[\w./-]+|\b[\w.-]+/[\w./-]+\.\w+")
# Looser, for scope entries: `db/migrate/` and `app/**/*.rb` are boundaries with no extension. The
# looseness only ever ACCEPTS a weak scope line; the rule it serves exists to catch "the invoice
# code", which names no separator at all.
PATH_LIKE_RE = re.compile(r"https?://\S+|(?:^|\s)/[\w./-]+|\b[\w.-]+/[\w./*-]*")
AC_ID_RE = re.compile(r"\bAC-(\d+)\b")
DIGIT_RE = re.compile(r"\d")

# The eight sections. Aliases are generous because the command generates these headings and a human
# editing afterwards should not be tripped by a synonym -- but the SET is fixed, because each one
# missing is a specific observed failure, not a stylistic preference.
REQUIRED_SECTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("goal", ("goal", "what and why", "objective")),
    ("acceptance criteria", ("acceptance criteria", "criteria", "how it is graded", "graded by")),
    ("scope", ("scope", "files")),
    ("guardrails", ("guardrails", "guard rails", "invariants")),
    ("stop conditions", ("stop conditions", "stop condition", "circuit breakers")),
    ("verify", ("verify", "verification", "how to check")),
    ("executor", ("executor", "who runs this", "tier")),
    ("on completion", ("on completion", "what to record", "record on completion", "when done")),
)

IN_ALIASES = ("in scope", "in-scope", "in", "included")
OUT_ALIASES = ("out of scope", "out-of-scope", "not in scope", "out", "excluded")

# Each stop condition needs a NUMBER, because the executor evaluating it is the one that is stuck.
# Matched per line so the digit has to sit with the condition, not merely somewhere in the section.
NUMERIC_CONDITIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # "retry" is deliberately absent while "retries" is present: the no-progress bullet ends
    # "...is a stop, not a retry", which carried a digit from its own threshold and satisfied this
    # rule for the wrong reason. A work order could then state no attempt cap at all and pass.
    # Found by the fixture, not by reading.
    ("attempt cap", ("attempt", "retries", "retry limit", "retry cap", "tries")),
    ("no-progress detector", ("no progress", "no-progress", "failure signature", "same failure",
                             "identical failure", "unchanged failure")),
    ("blast-radius cap", ("blast radius", "blast-radius", "files", "file cap")),
    ("budget", ("budget", "token", "hour", "minute", "wall clock", "wall-clock")),
)

# The four escapes #128 enumerates. Each is a way of "making progress" that destroys the thing that
# made unattended work safe, and each looks like activity in a log.
ESCAPES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("weakening or deleting a failing test",
     re.compile(r"(weaken|loosen|soften|delet|remov|skip|disabl|comment out|xit|pend)[a-z]*"
                r"(?:\W+\w+){0,3}\W+(test|spec|assertion|suite)", re.I)),
    ("reverting a passing task to unblock this one",
     re.compile(r"revert", re.I)),
    ("expanding scope beyond the declared files",
     re.compile(r"outside\s+(?:the\s+)?(?:declared\s+|in\b|scope|work order)|"
                r"expand\w*\s+(?:the\s+)?scope|scope\s+creep|widen\w*\s+(?:the\s+)?scope", re.I)),
    ("disabling a guardrail or hook",
     re.compile(r"(disabl|bypass|turn\w*\s+off|remov|skip)[a-z]*\s+(?:a\s+|the\s+|any\s+)?"
                r"(guardrail|guard rail|hook|gate)", re.I)),
)

# A reference to the conversation. The whole promise of the file is that it survives without one.
#
# Deliberately NOT matching bare "above"/"below"/"earlier": those are ordinary DOCUMENT-internal
# references ("the table above"), and flagging them would teach authors to delete cross-references
# that make the work order easier to follow. The near-miss is pinned in the selftest.
CHAT_REFS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bas (?:we )?(?:discussed|agreed|decided|said)\b", re.I),
    re.compile(r"\bwe (?:discussed|agreed|decided) (?:that |this |it )?\b", re.I),
    re.compile(r"\b(?:in|from) (?:our|the|this) (?:conversation|chat|discussion|thread)\b", re.I),
    re.compile(r"\byou (?:mentioned|said|asked|wanted|described)\b", re.I),
    re.compile(r"\b(?:per|see) (?:my|our) (?:earlier|previous|last)\b", re.I),
    re.compile(r"\bthe (?:plan|approach|scope|design) (?:i|we) (?:described|outlined|gave)\b", re.I),
    re.compile(r"\b(?:earlier|previous|last) (?:message|turn|prompt|reply)\b", re.I),
)

# An unresolved template. `<[a-z]…>` is the placeholder shape the command's template ships; HTML in
# prose (`<turbo-frame>`) is written in backticks in this toolchain, and inline code is stripped
# before this runs -- the near-miss for that carve-out is pinned in the selftest.
PLACEHOLDER_RE = re.compile(r"<[a-z][^>\n]{1,60}>")
UNRESOLVED_RE = re.compile(r"\b(TBD|TODO|FIXME|\?\?\?)\b")
# Restating a criterion instead of citing it. Two prose copies of one criterion will disagree, and
# nothing says which grades the work -- the same second-source-of-truth failure docs/GUIDE.md avoids.
GWT_RE = re.compile(r"\bgiven\b.*\bwhen\b.*\bthen\b", re.I)

TIERS_BEGIN = "<!-- rails-flow:tiers:begin -->"
TIERS_END = "<!-- rails-flow:tiers:end -->"
TIER_MODELS: dict[str, str] = {"judgement": "inherit", "mechanical": "haiku"}
# Aliases that select a MORE expensive model than the session already chose. Shipping one spends a
# stranger's money on our authority -- or is silently dropped by their availableModels allowlist.
EXPENSIVE_ALIASES = frozenset({"opus", "fable", "best", "opusplan", "opus[1m]", "sonnet[1m]"})
EMPTY_PROOF = frozenset({"", "-", "--", "—", "–", "n/a", "na", "none", "tbd", "todo"})
FRONTMATTER_FIELD_RE = re.compile(r"^(?P<key>[a-z][\w-]*)\s*:\s*(?P<value>.*?)\s*$")


class Unusable(Exception):
    """The input cannot be checked -- never report clean for it."""


def _heading_says(title: str, aliases: tuple[str, ...]) -> bool:
    """Alias match on whole words. `\\b` matters: without it the `in`/`out` scope aliases match
    inside "Invariants" and "Outcome", and the wrong subheading collects the scope list."""
    low = title.lower()
    return any(re.search(rf"\b{re.escape(a)}\b", low) for a in aliases)


@dataclass
class Section:
    title: str
    start: int
    lines: list[str] = field(default_factory=list)
    # Parallel to `lines`: True where the line sits inside a fenced block. Prose rules skip those,
    # because a quoted view snippet (`<turbo-frame id="x">`) is code, not an unresolved placeholder.
    fenced: list[bool] = field(default_factory=list)
    first_body_line: int = 0

    def matches(self, aliases: tuple[str, ...]) -> bool:
        return _heading_says(self.title, aliases)

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


@dataclass(frozen=True)
class TierRow:
    agent: str
    tier: str
    model: str
    proof: str
    line: int


def _strip_code(line: str) -> str:
    """Blank out inline code so a prose rule never reads a command or an HTML tag as prose."""
    return INLINE_CODE_RE.sub("``", line)


def _criteria_parser():  # -> module | None
    """`check_criteria`, or None when it is not beside this script.

    A seam, not indirection: the caller turns None into a FINDING rather than a silent skip, and a
    selftest can make it return None without hiding a file. An untestable failure path is the one
    that is wrong when it finally runs.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import check_criteria  # noqa: PLC0415 -- used by the traceability rule only
    except ImportError:
        return None
    return check_criteria


def _normalise_tier(text: str) -> str:
    """Accept the US spelling. Rejecting a work order over `judgment` would be pedantry wearing a
    gate's clothes, and the author would delete the tier line rather than respell it."""
    return text.replace("judgment", "judgement")


def parse(path: Path) -> list[Section]:
    """Split a work order into its `##` sections, or refuse to bless the file."""
    if not path.is_file():
        raise Unusable(f"no such file: {path}")

    sections: list[Section] = []
    current: Section | None = None
    in_fence = False
    ticks = ""
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        fence = FENCE_RE.match(line)
        if fence:
            # Headings inside a fenced block are sample content, not structure -- the command's own
            # template lives in one. Only a run of at least as many backticks closes the fence.
            if not in_fence:
                in_fence, ticks = True, fence.group("ticks")
            elif fence.group("ticks").startswith(ticks):
                in_fence, ticks = False, ""
            if current is not None:
                current.lines.append(line)
                current.fenced.append(True)
            continue
        heading = SECTION_RE.match(line) if not in_fence else None
        if heading:
            current = Section(
                title=heading.group("text"), start=line_no, first_body_line=line_no + 1
            )
            sections.append(current)
            continue
        if current is not None:
            current.lines.append(line)
            current.fenced.append(in_fence)

    if not sections:
        raise Unusable(
            f"{path} carries no `## ` sections -- refusing to report a file clean as a work order "
            "when none of its eight required sections can even be located"
        )
    if not any(s.matches(a) for s in sections for _, a in REQUIRED_SECTIONS):
        raise Unusable(
            f"{path} has `## ` sections but not one of the eight a work order requires "
            f"({', '.join(label for label, _ in REQUIRED_SECTIONS)}) -- this is not a work order"
        )
    return sections


def _numeric_near(section: Section, words: tuple[str, ...]) -> bool:
    """True when some line mentions the condition AND carries a digit on that same line."""
    for line in section.lines:
        low = line.lower()
        if any(w in low for w in words) and DIGIT_RE.search(line):
            return True
    return False


def _steps(section: Section) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for offset, line in enumerate(section.lines):
        step = STEP_RE.match(line)
        if step:
            out.append((section.first_body_line + offset, step.group("text")))
    return out


def _check_scope(section: Section, findings: list[str]) -> None:
    """In AND out, both populated, and at least one in-scope entry naming a file or directory."""
    buckets: dict[str, list[str]] = {"in": [], "out": []}
    which: str | None = None
    for line in section.lines:
        sub = SUBSECTION_RE.match(line)
        if sub:
            title = sub.group("text")
            # OUT first: "out of scope" also contains a bare "scope", and several in-aliases are
            # substrings of out-phrasings, so testing IN first would file exclusions as inclusions.
            if _heading_says(title, OUT_ALIASES):
                which = "out"
            elif _heading_says(title, IN_ALIASES):
                which = "in"
            else:
                which = None
            continue
        step = STEP_RE.match(line)
        if step and which:
            buckets[which].append(step.group("text"))

    if not buckets["in"]:
        findings.append(
            f"scope (line {section.start}): nothing is declared IN scope -- an executor with no "
            "declared files cannot tell a legitimate edit from scope creep, and the blast-radius "
            "stop condition has nothing to measure against. List the files under `### In`."
        )
    elif not any(PATH_LIKE_RE.search(item) for item in buckets["in"]):
        findings.append(
            f"scope (line {section.start}): no in-scope entry names a file or directory "
            f"({buckets['in'][0][:60]!r}) -- \"the invoice code\" is not a boundary anyone can "
            "check a diff against."
        )
    if not buckets["out"]:
        findings.append(
            f"scope (line {section.start}): nothing is declared OUT of scope -- the explicit "
            "exclusions are what stop \"fix the invoice total\" becoming a tenancy refactor. Name "
            "the neighbours under `### Out`, each with why."
        )


def _check_stop_conditions(section: Section, findings: list[str]) -> None:
    for label, words in NUMERIC_CONDITIONS:
        if not _numeric_near(section, words):
            findings.append(
                f"stop conditions (line {section.start}): no numeric {label} -- a stop condition "
                "without a number cannot be evaluated by the executor that is stuck, which is the "
                "only reader that matters. State the number."
            )
    body = section.text
    for label, pattern in ESCAPES:
        if not pattern.search(body):
            findings.append(
                f"stop conditions (line {section.start}): the forbidden escapes do not cover "
                f"{label} -- it is not an unlikely edge case, it is what an agent that cannot "
                "make progress does next, and it looks like activity in the log."
            )


def _check_verify(section: Section, findings: list[str]) -> None:
    steps = _steps(section)
    if not steps:
        findings.append(
            f"verify (line {section.start}): lists no steps -- \"how to verify\" with nothing in "
            "it is how a work order gets reported complete on the author's word."
        )
        return
    for line_no, text in steps:
        if INLINE_CODE_RE.search(text) or RUNNABLE_RE.search(text):
            continue
        findings.append(
            f"verify line {line_no}: the step names no command or path ({text[:60]!r}) -- a step "
            "the executor cannot run is a reassurance. Name the command in backticks."
        )


def _check_criteria(section: Section, criteria: Path | None, tier: str | None,
                    findings: list[str]) -> None:
    cited = sorted({int(n) for n in AC_ID_RE.findall(section.text)})
    if not cited:
        findings.append(
            f"acceptance criteria (line {section.start}): cites no `AC-n` id -- the work order is "
            "not attached to the contract that grades it, so \"done\" is whatever the executor "
            "decides it is."
        )
    for offset, line in enumerate(section.lines):
        if GWT_RE.search(_strip_code(line)):
            findings.append(
                f"acceptance criteria line {section.first_body_line + offset}: restates a "
                "criterion (given/when/then) instead of citing its id -- two prose copies of one "
                "criterion will disagree and nothing says which grades the work. Cite `AC-n`."
            )
            break

    if criteria is None:
        return
    if not criteria.is_file():
        findings.append(
            f"acceptance criteria (line {section.start}): {criteria} does not exist -- the work "
            "order is graded by a file that is not there."
            + (" A `mechanical` executor is only safe while the proof is EXTERNAL to it; with no "
               "criteria file there is no external proof, only a cheaper judgement."
               if tier == "mechanical" else "")
        )
        return

    cc = _criteria_parser()
    if cc is None:
        # A finding, never a silent skip: this mode's whole job is proving the ids resolve, and
        # "could not check" reported as clean is the failure the repo's doctrine calls a skip
        # masquerading as a pass.
        findings.append(
            f"acceptance criteria (line {section.start}): check_criteria.py is not beside this "
            "script, so the cited ids could not be resolved against "
            f"{criteria}. Traceability is UNVERIFIED, not satisfied."
        )
        return

    try:
        defined = {c.num for c in cc.parse(criteria)}
    except cc.Unusable as exc:
        findings.append(
            f"acceptance criteria (line {section.start}): {criteria} cannot be read as criteria "
            f"({exc}) -- run check_criteria.py on it before relying on it here."
        )
        return
    for num in cited:
        if num not in defined:
            findings.append(
                f"acceptance criteria (line {section.start}): cites AC-{num}, which {criteria} "
                "does not define -- an id that resolves to nothing is worse than no citation, "
                "because it reads as traceable."
            )


def _executor_tier(section: Section, findings: list[str]) -> str | None:
    """The declared tier, plus the model it must carry. Returns the tier for downstream rules."""
    body = section.text
    low = _normalise_tier(body.lower())
    named = [t for t in TIER_MODELS if t in low]
    if not named:
        findings.append(
            f"executor (line {section.start}): names no tier -- say `judgement` or `mechanical` "
            "and the `model:` that goes with it (see the plugin's reference/model-tiers.md). "
            "Silence is not a claim of exemption."
        )
        return None
    if len(named) > 1:
        findings.append(
            f"executor (line {section.start}): names {len(named)} tiers ({', '.join(named)}) -- "
            "one work order, one executor tier."
        )
        return None
    tier = named[0]
    want = TIER_MODELS[tier]
    models = {m.strip("`") for m in INLINE_CODE_RE.findall(body)}
    models = {m.split("model:")[-1].strip() for m in models}
    if want not in models:
        findings.append(
            f"executor (line {section.start}): tier `{tier}` but the section does not state "
            f"`model: {want}` -- the tier and the frontmatter value are one decision, and a tier "
            "named without its model cannot be reconciled with the table."
        )
    for bad in EXPENSIVE_ALIASES & models:
        findings.append(
            f"executor (line {section.start}): `{bad}` selects a more expensive model than the "
            "session already chose. Claude Code skips a value outside the org's availableModels "
            "and runs on the inherited model anyway, so the pin either spends someone else's "
            "money on our authority or does nothing. Use `inherit`."
        )
    return tier


def check(sections: list[Section], criteria: Path | None = None) -> list[str]:
    findings: list[str] = []
    found: dict[str, Section] = {}
    for label, aliases in REQUIRED_SECTIONS:
        for section in sections:
            if section.matches(aliases):
                found[label] = section
                break
        else:
            findings.append(
                f"no `## {label}` section -- a work order missing it is not self-contained, and "
                "the gap is invisible to whoever wrote it."
            )

    tier = _executor_tier(found["executor"], findings) if "executor" in found else None
    if "scope" in found:
        _check_scope(found["scope"], findings)
    if "stop conditions" in found:
        _check_stop_conditions(found["stop conditions"], findings)
    if "verify" in found:
        _check_verify(found["verify"], findings)
    if "acceptance criteria" in found:
        _check_criteria(found["acceptance criteria"], criteria, tier, findings)

    # ---- self-containment: the promise that makes the file worth writing --------------------
    for section in sections:
        for offset, raw in enumerate(section.lines):
            if offset < len(section.fenced) and section.fenced[offset]:
                continue
            line = _strip_code(raw)
            line_no = section.first_body_line + offset
            for pattern in CHAT_REFS:
                hit = pattern.search(line)
                if hit:
                    findings.append(
                        f"line {line_no}: points at the conversation ({hit.group(0)!r}) -- the "
                        "work order exists because the conversation does not survive a fresh "
                        "session, a resume, or a subagent. Write what it referred to."
                    )
                    break
            placeholder = PLACEHOLDER_RE.search(line)
            if placeholder:
                findings.append(
                    f"line {line_no}: unresolved placeholder {placeholder.group(0)!r} -- an "
                    "executor cannot resolve it and will guess, which is the failure this file "
                    "exists to prevent."
                )
            unresolved = UNRESOLVED_RE.search(line)
            if unresolved:
                findings.append(
                    f"line {line_no}: {unresolved.group(0)} left in the work order -- decide it "
                    "now, or move it to the acceptance criteria as an open question with an owner."
                )
    return findings


# ------------------------------------------------------------------------------------------------
# Tier reconciliation: the table in reference/model-tiers.md vs the agents' own frontmatter.
# ------------------------------------------------------------------------------------------------

def parse_tiers(path: Path) -> list[TierRow]:
    if not path.is_file():
        raise Unusable(f"no such file: {path}")
    raw = path.read_text(encoding="utf-8").splitlines()
    try:
        start = next(i for i, line in enumerate(raw) if TIERS_BEGIN in line)
        stop = next(i for i, line in enumerate(raw) if TIERS_END in line)
    except StopIteration as exc:
        raise Unusable(
            f"{path} has no {TIERS_BEGIN} / {TIERS_END} block -- the markers are what makes the "
            "table machine-checkable instead of folklore, which is the defect #127 reported"
        ) from exc
    if stop < start:
        raise Unusable(f"{path}: the tiers end marker precedes its begin marker")

    rows: list[TierRow] = []
    for offset, line in enumerate(raw[start + 1: stop], start=start + 2):
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        agent = cells[0].strip("`")
        if not agent or agent.lower() in ("agent", "---") or set(agent) <= {"-", ":"}:
            continue
        rows.append(TierRow(
            agent=agent, tier=_normalise_tier(cells[1].strip("`").lower()),
            model=cells[2].strip("`").lower(), proof=cells[3].strip().lower(), line=offset,
        ))
    if not rows:
        raise Unusable(
            f"{path}: the tiers block holds no agent rows -- an empty table would report every "
            "agent reconciled while checking nothing"
        )
    return rows


def agent_models(directory: Path) -> dict[str, tuple[Path, str | None]]:
    """Every agent's declared `name` -> (file, model). Identity is the frontmatter name, not the
    filename: Claude Code's docs are explicit that "identity comes only from the `name` frontmatter
    field" and "The filename doesn't have to match"."""
    if not directory.is_dir():
        raise Unusable(f"no such directory: {directory}")
    out: dict[str, tuple[Path, str | None]] = {}
    for path in sorted(directory.rglob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0].strip() != "---":
            continue
        name: str | None = None
        model: str | None = None
        for line in lines[1:]:
            if line.strip() == "---":
                break
            match = FRONTMATTER_FIELD_RE.match(line)
            if not match:
                continue
            if match.group("key") == "name":
                name = match.group("value").strip("\"'")
            elif match.group("key") == "model":
                model = match.group("value").strip("\"'").lower()
        if name:
            out[name] = (path, model)
    if not out:
        raise Unusable(
            f"{directory} holds no agent definitions with a `name:` frontmatter field -- "
            "reporting a reconciliation clean against nothing is the failure mode this avoids"
        )
    return out


def check_tiers(rows: list[TierRow], agents: dict[str, tuple[Path, str | None]] | None) -> list[str]:
    findings: list[str] = []
    seen: dict[str, int] = {}
    for row in rows:
        if row.agent in seen:
            findings.append(
                f"tier table line {row.line}: `{row.agent}` is listed twice (first on line "
                f"{seen[row.agent]}) -- two rows for one agent means the reconciliation below "
                "silently checks whichever it reaches first."
            )
        seen[row.agent] = row.line

        if row.tier not in TIER_MODELS:
            findings.append(
                f"tier table line {row.line}: `{row.agent}` has tier {row.tier!r}, not one of "
                f"{', '.join(sorted(TIER_MODELS))} -- the two values are the two the mechanism can "
                "defend; a third tier needs its own doctrine, not a new word."
            )
            continue
        want = TIER_MODELS[row.tier]
        if row.model in EXPENSIVE_ALIASES:
            findings.append(
                f"tier table line {row.line}: `{row.agent}` pins `{row.model}`, which selects a "
                "more expensive model than the user's session chose. Claude Code runs the agent on "
                "the inherited model anyway when the alias is outside their availableModels, so it "
                "either spends their money on our authority or does nothing."
            )
        elif row.model.startswith("claude-"):
            findings.append(
                f"tier table line {row.line}: `{row.agent}` pins the full model id "
                f"`{row.model}` -- it ages, and provider deployments use their own ids rather than "
                "Anthropic model ids, so it does not resolve everywhere the plugin runs."
            )
        elif row.model != want:
            findings.append(
                f"tier table line {row.line}: `{row.agent}` is `{row.tier}` but pins "
                f"`{row.model}` instead of `{want}` -- a pin is a cap: frontmatter beats the "
                "session model, so this overrides the ceiling the user chose."
            )
        if row.tier == "mechanical" and row.proof.strip("*_ ") in EMPTY_PROOF:
            findings.append(
                f"tier table line {row.line}: `{row.agent}` is cheap-tier but names no external "
                "proof -- cheap execution is delegation only while the proof sits outside the "
                "executor. Name the suite, the grep, or the digest that grades it."
            )

    if agents is None:
        return findings

    for name, (path, model) in agents.items():
        row = next((r for r in rows if r.agent == name), None)
        if row is None:
            findings.append(
                f"{path}: agent `{name}` is not in the tier table -- an agent whose model nobody "
                "decided is exactly what #127 reported. Add a row, or delete the agent."
            )
            continue
        if model is None:
            findings.append(
                f"{path}: agent `{name}` declares no `model:` -- it resolves to `inherit` by "
                f"default, and the table says `{row.model}`. State it explicitly: silence is not a "
                "decision, and it is indistinguishable from an unreviewed field."
            )
        elif model != row.model:
            findings.append(
                f"{path}: agent `{name}` pins `model: {model}` while the tier table (line "
                f"{row.line}) says `{row.model}` -- doctrine and frontmatter disagree, so one of "
                "them is lying to whoever reads it next."
            )
    for row in rows:
        if row.agent not in agents:
            findings.append(
                f"tier table line {row.line}: names `{row.agent}`, which no agent definition "
                "declares -- a stale row reads as coverage and checks nothing."
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a rails-flow work order, and reconcile agents with the tier table."
    )
    parser.add_argument("handoff_path", nargs="?", help="docs/handoff/<slug>.md")
    parser.add_argument(
        "--criteria", metavar="FILE",
        help="the acceptance criteria this work order is graded by (docs/acceptance/<slug>.md); "
             "every cited AC-n must exist there",
    )
    parser.add_argument(
        "--tiers", metavar="FILE", help="reference/model-tiers.md — the machine-readable tier table"
    )
    parser.add_argument(
        "--agents", metavar="DIR", help="an agents/ directory to reconcile against --tiers"
    )
    parser.add_argument(
        "--selftest", action="store_true", help="prove the rules fire AND stay silent"
    )
    args = parser.parse_args(argv)

    if args.selftest:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import check_handoff_selftest as st

        return st.run()

    if args.agents and not args.tiers:
        parser.error("--agents needs --tiers: there is nothing to reconcile against")
    if not args.handoff_path and not args.tiers:
        parser.error("give a work order path, or --tiers (optionally with --agents), or --selftest")

    findings: list[str] = []
    checked: list[str] = []
    try:
        if args.handoff_path:
            sections = parse(Path(args.handoff_path))
            findings += check(sections, Path(args.criteria) if args.criteria else None)
            checked.append(f"{len(sections)} sections in {args.handoff_path}")
        if args.tiers:
            rows = parse_tiers(Path(args.tiers))
            agents = agent_models(Path(args.agents)) if args.agents else None
            findings += check_tiers(rows, agents)
            checked.append(
                f"{len(rows)} tier rows"
                + (f" vs {len(agents)} agents in {args.agents}" if agents else "")
            )
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2

    if findings:
        print(f"{len(findings)} work-order finding(s):", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        print(
            "\nFix the work order, do not soften the check. An under-specified work order does not "
            "fail loudly: it produces confident work on the wrong thing.",
            file=sys.stderr,
        )
        return 1

    print(f"validated: {'; '.join(checked)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
