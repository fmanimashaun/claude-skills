#!/usr/bin/env python3
"""Check a reference-research record is research, not a shopping list.

`reference-research.md` is the method; this is the part of it a machine can hold. Three of its rules
are checkable, and writing them as prose alone would be the defect this repo is built around:

  1. THREE SOURCES MINIMUM, and not all from one category. One is a copy; two is a blend, and the
     seam shows; three or more DISAGREE, and the choosing between them is the design. Direct
     competitors have converged on one look by copying each other, so a record sampled only from
     them inherits the convergence and produces something on-trend and indistinguishable.

  2. A MECHANISM, NOT A BRAND NAME. "Looks like Linear" cannot be applied to a different subject; a
     mechanism survives a change of palette, typeface and subject. This is checked crudely and on
     purpose -- see `looks_like_a_brand`.

  3. SOMETHING REJECTED. A record where every reference was adopted wholesale is a shopping list.
     The `reject` field is what makes the file honest, and it is the one people skip.

WHAT IT DELIBERATELY DOES NOT DO. It cannot tell a good mechanism from a bad one, and it does not
try. Judging taste is the reviewer's job, and a gate that pretended to do it would either block real
work or wave through anything phrased confidently. It checks the shape of the research, which is the
part that is a fact.

Exit codes:  0 the record holds up · 1 findings · 2 unusable input

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# #636. IMPORTED, not re-listed. `STYLES` is the closed illustration taxonomy every brief is
# held to, and a second copy here would drift the first time one gains an entry -- after which
# a record could settle on a style the gate later refuses. `generation_gate` is stdlib-only and
# side-effect free on import.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generation_gate import STYLES  # noqa: E402

RECORD_PATH = Path("docs/design/reference-research.json")

MIN_SOURCES = 3
CATEGORIES = ("direct", "adjacent", "outside")

FIELDS = {
    "source": "where it came from, so the claim can be re-checked",
    "category": f"one of {', '.join(CATEGORIES)} — the spread is what avoids convergence",
    "mechanism": "WHY it works, in terms that survive a change of subject",
    "adopt": "what you are taking, stated as something you will build",
}

# A note that names a company instead of a mechanism. Deliberately crude: a capitalised word that is
# not a sentence opener, or an explicit comparison. It over-reports rather than under-reports, and
# that is the right direction -- a false positive costs one rewritten sentence, while a false
# negative ships "looks like Stripe" as though it were a design decision.
BRANDISH = re.compile(r"\b(like|similar to|inspired by|à la|same as)\s+[A-Z]", re.I)


def looks_like_a_brand(mechanism: str) -> bool:
    if BRANDISH.search(mechanism):
        return True
    words = mechanism.split()
    # A capitalised word mid-sentence, ignoring the first word and anything after a full stop.
    for i, w in enumerate(words):
        if i == 0 or not w[:1].isupper():
            continue
        if words[i - 1].endswith((".", "!", "?")):
            continue
        if w.strip(".,;:").isupper():         # an acronym like CSS or UI is not a brand claim
            continue
        return True
    return False


def check(record: dict) -> list[str]:
    problems: list[str] = []
    if not record.get("job"):
        problems.append(
            "no `job` stated. Research without one returns the median of everything, which is the "
            "stock look this method exists to avoid. Name the user, their state of mind, and the "
            "decision the surface has to move.")
    # THE STYLE IS THE RESEARCH'S OUTPUT, and it must be stated here. Synthesis that names no
    # style has not finished: "three or more sources disagree, and the choosing IS the design" --
    # so a record with no `style` records the gathering and omits the decision. It is also the link
    # that makes research MEAN anything downstream: without it a project can research ink line-work
    # and brief a 3D render, and nothing notices.
    if record.get("references") and not record.get("style"):
        problems.append(
            "no `style` chosen. The references disagree — that is why three are required — and "
            "choosing between them is the design. A record that gathers and does not choose is a "
            "mood board, and nothing downstream can hold a brief to it.")
    # #636. AND IT MUST BE ONE THE PIPELINE ACCEPTS. Validating presence only let a record settle on
    # a value every asset brief would later refuse: `research_record.check` passed it,
    # `asset_plan.check_research` passed it, and `generation_gate.compose_prompt` refused it three
    # steps later with "unknown illustration style" -- AFTER the plan was written and costed.
    #
    # Moving the refusal from run time to record time is the same move `asset_plan --check` already
    # makes for a surface with no brief, and for the same reason: finding out after the spend is the
    # wrong order.
    chosen = record.get("style")
    if chosen and chosen not in STYLES:
        problems.append(
            f"style {chosen!r} is not one of the taxonomy: {', '.join(STYLES)}. Every asset brief is "
            f"held to this value, so a record that settles on something else is refused later, by "
            f"the generator, after the plan has been costed. If the direction genuinely is not in "
            f"the list, that is a decision about the taxonomy — make it deliberately rather than "
            f"discovering it at the point of sale.")
    # #632. A DECLARED SIGNATURE EXCEPTION: a second style the research deliberately sanctions --
    # one rationed device (a luminous prism at the hero) beside a family of ink line marks. It is
    # validated HERE, in the record, and never accepted from a brief: an exception a brief could
    # introduce is not an exception, it is drift with better manners, and the whole value of the
    # mechanism is that the deviation was decided once, in the open, with a reason attached.
    seen_styles: set[str] = set()
    for i, exc in enumerate(record.get("signature_exceptions") or []):
        label = f"signature_exceptions[{i}]"
        if not isinstance(exc, dict):
            problems.append(f"{label}: not an object. Each exception is `{{style, why}}` with an "
                            f"optional `max`.")
            continue
        style = exc.get("style")
        if not style:
            problems.append(f"{label}: no `style`. An exception has to name the style it permits, "
                            f"or nothing downstream can tell it from an off-style brief.")
        if not str(exc.get("why") or "").strip():
            problems.append(
                f"{label}: no `why`. An exception is a deliberate break in the one-style rule, and "
                f"the reason is the only thing separating that from drift. State what the device is "
                f"for and where it is allowed to appear — the next person to read this record is "
                f"deciding whether to widen it.")
        if style and style == record.get("style"):
            problems.append(
                f"{label}: {style!r} is already the chosen style, so exempting it means nothing. An "
                f"exception naming the primary reads as though a second style were sanctioned when "
                f"none is.")
        # #636, one level down. An exception declaring a style outside the taxonomy passes here and
        # is refused by the generator later, exactly as the primary was -- the same defect, and
        # found by grepping for the pattern rather than by waiting for it to be reported.
        if style and style not in STYLES:
            problems.append(
                f"{label}: {style!r} is not one of the taxonomy: {', '.join(STYLES)}. A sanctioned "
                f"exception still has to be a style the generator will accept, or it is refused "
                f"after the plan is costed like any other off-taxonomy value.")
        if style and style in seen_styles:
            problems.append(f"{label}: {style!r} is declared twice. Two entries for one style means "
                            f"two `max` values and two reasons, and nothing says which governs.")
        if style:
            seen_styles.add(style)
        if "max" in exc:
            try:
                cap = int(exc["max"])
            except (TypeError, ValueError):
                cap = -1
            if cap < 1:
                problems.append(
                    f"{label}: `max` is {exc['max']!r}. A ration below 1 permits the style and then "
                    f"forbids every use of it, which is a refusal wearing a permission's clothes — "
                    f"drop the exception instead, and say why in the record.")
    # #637. RECOGNITION TRAITS: how you would know the result hit the chosen direction.
    #
    # The record already captures what was BORROWED -- `mechanism`, `adopt`, `reject` per reference.
    # It never captured what the result should LOOK like when it worked, so `design-critic` had the
    # references and the adopted mechanisms and no list it could walk. Its output was therefore as
    # good as the model's taste that day, which is the variance the research pass exists to remove.
    #
    # THE PATTERN IS BORROWED, and the source is worth naming: `websiteprompts.com/design` pairs each
    # of its 14 directions with exactly four numbered traits, framed as "See the style. Recognize its
    # traits. Prompt it clearly." Traits are the CHECKABLE RESIDUE of a taste decision -- not "is this
    # beautiful" but "does this have mixed spans and strong alignment, yes or no".
    #
    # COMPLETENESS ONLY, never quality. Whether a trait is a good one is judgement, and
    # `art-direction.md`'s "why none of this is gated" holds: #476 killed a monotony gate that flagged
    # our own worked example on its first real input. This checks that a record which chose a
    # direction also said how to recognise it -- the same kind of check `reject` already gets.
    traits = record.get("recognition_traits")
    if record.get("style") and not traits:
        problems.append(
            "no `recognition_traits`. The record chose a style and never said how you would know the "
            "result hit it, so a reviewer has the references and no list to walk. Three to five "
            "short, checkable phrases — 'modular tiles', 'strong alignment', 'compact summaries' — "
            "not sentences of praise.")
    elif traits is not None:
        if not isinstance(traits, list):
            problems.append("`recognition_traits` must be a list of short phrases.")
        else:
            blank = [i for i, t in enumerate(traits) if not str(t or "").strip()]
            if blank:
                problems.append(
                    f"`recognition_traits` has {len(blank)} empty entr(y/ies). An empty trait pads "
                    f"the list and checks nothing.")
            # FOUR IS THE REFERENCE SHAPE and the ceiling is the load-bearing half: a list long
            # enough to argue with is a list nobody walks, so the cap protects the mechanism rather
            # than the reader's patience.
            if len(traits) > 6:
                problems.append(
                    f"`recognition_traits` lists {len(traits)}. A reviewer walks four; a list long "
                    f"enough to argue with is one nobody walks. Cut it to the traits that would "
                    f"actually distinguish this direction from a near miss.")

    refs = record.get("references") or []
    if len(refs) < MIN_SOURCES:
        problems.append(
            f"only {len(refs)} reference(s); {MIN_SOURCES} is the minimum. One is a copy, two is a "
            f"blend and the seam shows. Three or more disagree, and choosing between them is the "
            f"design.")
    for i, ref in enumerate(refs):
        label = ref.get("source") or f"reference {i}"
        for field, why in FIELDS.items():
            if not ref.get(field):
                problems.append(f"{label}: no `{field}` — {why}")
        cat = ref.get("category")
        if cat and cat not in CATEGORIES:
            problems.append(f"{label}: category {cat!r} is not one of {', '.join(CATEGORIES)}")
        # A LOGIN WALL DOES NOT ERROR -- it returns a page, so an unattended capture succeeds and
        # files a screenshot of a sign-in form as a reference. Nothing downstream can tell that from
        # real research, because the file exists and has the right name. A gated source must
        # therefore say so, and the human authenticates once into a reusable browser profile.
        cap = str(ref.get("capture", ""))
        if re.search(r"(login|signin|sign-in|auth)", cap, re.I) and not ref.get("gated"):
            problems.append(
                f"{label}: the capture path looks like a sign-in page and `gated` is not set. A "
                f"login wall returns a page rather than an error, so the capture may be the wall "
                f"itself. Have the human sign in once into the browser profile, re-capture, and "
                f"mark the source `gated: true`.")
        mech = ref.get("mechanism") or ""
        if mech and looks_like_a_brand(mech):
            problems.append(
                f"{label}: the mechanism names a brand rather than describing one. A mechanism "
                f"survives a change of subject, palette and typeface — if yours does not, you have "
                f"described the surface, and copying a surface is what produces the tells.")
    cats = {r.get("category") for r in refs if r.get("category")}
    if refs and cats == {"direct"}:
        problems.append(
            "every reference is a DIRECT competitor. They converged on one look by copying each "
            "other, so this record inherits the convergence — the result will be on-trend and "
            "indistinguishable. Add an adjacent industry and something outside software.")
    if refs and not any(r.get("reject") for r in refs):
        problems.append(
            "nothing was rejected anywhere in this record, which makes it a shopping list rather "
            "than research. If every reference was adopted wholesale, none of them was examined.")
    return problems


SKILL_PATH = Path(".claude/skills/project-design/SKILL.md")


def emit_skill(record: dict, root: Path) -> Path:
    """Write the settled approach as a project-level SKILL, not just a JSON record.

    THE RECORD IS EVIDENCE; THE SKILL IS DOCTRINE. A JSON file is something an agent parses when it
    remembers to; a skill is something it reads because the description matches what it is doing. If
    the approach only ever lives in `reference-research.json`, every downstream agent re-derives the
    style from raw references -- and re-derivation is where a family quietly becomes a pile.

    So the research's OUTPUT is written where doctrine lives. It carries the chosen style, the
    mechanisms adopted, and -- the part people drop -- what was REJECTED and why, because a reader
    who does not know what was considered and turned down will re-propose it next quarter.

    Regenerated from the record every time, never hand-edited: the record is the source, and two
    editable copies of one decision is how they drift apart.
    """
    # REFUSE AT THE POINT OF WRITING, not at the CLI. The guard lived in main(), which no test
    # exercised, so a mutation removing it survived -- and the thing it guards is publishing a
    # decision nobody made into the place agents trust most.
    problems = check(record)   # emit_skill: refuse at the point of writing
    if problems:
        raise SystemExit("refusing to emit a skill from a record that does not hold up:\n  "
                         + "\n  ".join(problems))
    style = record.get("style") or "unstated"
    refs = record.get("references") or []
    adopted = [r for r in refs if r.get("adopt")]
    rejected = [r for r in refs if r.get("reject")]

    lines = [
        "---",
        "name: project-design",
        (f"description: The design approach settled for this project — style `{style}`, the "
         f"mechanisms adopted from reference research, and what was deliberately rejected. Use when "
         f"building any UI surface, choosing an illustration or asset, reviewing a design for brand "
         f"fit, or deciding whether a new visual belongs in this product."),
        "---", "",
        "# The design approach for this project", "",
        "**GENERATED from `docs/design/reference-research.json` — do not hand-edit.** Regenerate with",
        "`research_record.py --emit-skill`. Two editable copies of one decision drift apart.", "",
        f"## The style: `{style}`", "",
        "Every brief in this project carries this style, and the plan refuses a brief that names a",
        "different one. One family, one style — a set that mixes them is a pile, and it is invisible",
        "once shipped.", "",
    ]
    # #632. THE GENERATED SKILL MUST NOT OVERSTATE THE RULE. This file is read by the project's own
    # agent as doctrine, so a flat "every brief carries this style" is enforced against a project
    # whose research deliberately sanctioned a second one -- the same shape as writing a wrong rule
    # into a user's CLAUDE.md and then gating on it. Stated only when exceptions exist, so a project
    # without any reads exactly as strictly as before.
    # #637. THE TRAITS REACH THE PROJECT'S OWN DOCTRINE, or the record holds a checklist nobody
    # reads. This is the file `design-critic` is pointed at, so the traits belong beside the style
    # they describe -- and framed as a checklist, because a reviewer walks a list and skims a
    # paragraph.
    traits = [str(t).strip() for t in (record.get("recognition_traits") or []) if str(t).strip()]
    if traits:
        lines += [
            "### How to recognise it", "",
            "Walk these against any surface built for this project. They are **advisory** — the lens,",
            "not the gate. A near miss on one is a conversation; it is not a merge condition.", "",
        ]
        lines += [f"- [ ] {t}" for t in traits]
        lines += ["",
                  "Stated as checkable traits rather than praise, so a review can disagree with a",
                  "specific one instead of with the whole design.", ""]

    exceptions = record.get("signature_exceptions") or []
    if exceptions:
        lines += [
            "### Declared signature exception(s)", "",
            "The research deliberately sanctioned a second style, **rationed** — a signature device",
            "works by scarcity, so used everywhere it stops punctuating and becomes the family.", "",
            "| style | ration | why |",
            "|---|---|---|",
        ]
        for e in exceptions:
            if not isinstance(e, dict):
                continue
            why = " ".join(str(e.get("why") or "—").split()).replace("|", "\\|")
            lines.append(f"| `{e.get('style') or '—'}` | {e.get('max', 1)} | {why} |")
        lines += [
            "",
            "Anything outside this table is drift, and the plan still refuses it. Widening the list",
            "is a research decision — re-open the record and say why; do not add it to a brief.", "",
        ]
    lines += [
        f"## The job this design serves", "",
        f"> {record.get('job') or '(no job stated)'}", "",
        "Research a job, not a page type. A surface that does not serve this job is not covered by",
        "this approach and needs its own research rather than a guess.", "",
        "## Mechanisms adopted", "",
    ]
    lines += [f"- **{r.get('adopt')}** — from {r.get('source')} ({r.get('category')}): "
              f"{r.get('mechanism')}" for r in adopted] or ["- (none recorded)"]
    lines += ["", "## Deliberately rejected", "",
              "The half people drop, and the reason the same idea does not get re-proposed next",
              "quarter. Each of these was considered and turned down:", ""]
    lines += [f"- **{r.get('reject')}** — considered from {r.get('source')}"
              for r in rejected] or ["- (nothing rejected — which makes the record a shopping list)"]
    lines += ["", "## What this does not settle", "",
              "Tokens, spacing and type come from the brand pack, not from here. This file records",
              "the *approach*; the pack records the *values*, and a mechanism that cannot be",
              "expressed in the pack's tokens is one this project cannot ship.", ""]

    out = root / SKILL_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--record", default=str(RECORD_PATH))
    ap.add_argument("--emit-skill", action="store_true",
                    help="write the settled approach as a project-level skill agents read")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    path = Path(args.record)
    if not path.is_file():
        print(f"no research record at {path} — do the research before the design, not after.",
              file=sys.stderr)
        return 2
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"{path} is not valid JSON ({exc})", file=sys.stderr)
        return 2
    problems = check(record)
    if problems:
        print("\n".join(problems))
        return 1
    if args.emit_skill:
        print(f"wrote {emit_skill(record, Path.cwd())}")
        return 0
    print("the research record holds up.")
    return 0


def selftest() -> int:
    checks, failures = 0, []

    def expect(label, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failures.append(label)

    def ref(**kw):
        base = {"source": "https://x", "category": "adjacent",
                "mechanism": "one focal point, everything else demoted to plumbing type",
                "adopt": "demote the sub-head"}
        return {**base, **kw}

    GOOD = {"job": "a sceptical buyer deciding in one visit", "style": "minimalist-ink",
            "recognition_traits": ["monochrome line-work", "single ink weight", "no gradient",
                                   "high contrast"],
            "references": [ref(category="direct", reject="their comparison table"),
                           ref(category="adjacent"), ref(category="outside")]}
    expect("a complete record passes", check(GOOD) == [])

    # #636. THE STYLE MUST BE ONE THE PIPELINE ACCEPTS, checked at RECORD time. Presence-only let a
    # record settle on a value that `generation_gate` refused three steps later, after costing.
    expect("a style outside the taxonomy is reported",
           any("not one of the taxonomy" in p for p in check({**GOOD, "style": "bento-grid"})))
    expect("...and one inside it is not",
           not any("taxonomy" in p for p in check(GOOD)))
    # Same defect one level down: a sanctioned exception still has to be a style the generator takes.
    expect("an exception outside the taxonomy is reported",
           any("not one of the taxonomy" in p for p in check(
               {**GOOD, "signature_exceptions": [{"style": "bento-grid", "why": "a device"}]})))
    expect("...and an in-taxonomy exception is not",
           not any("taxonomy" in p for p in check(
               {**GOOD, "signature_exceptions": [{"style": "3d-render", "why": "one prism"}]})))

    # #637. RECOGNITION TRAITS -- how you would know the result hit the direction. Completeness only:
    # whether a trait is a GOOD one is judgement, and gating judgement is what #476 killed.
    expect("a record that chose a style and stated no traits is reported",
           any("recognition_traits" in p
               for p in check({k: v for k, v in GOOD.items() if k != "recognition_traits"})))
    expect("an empty trait is reported",
           any("empty entr" in p for p in check({**GOOD, "recognition_traits": ["ink", "  "]})))
    expect("a list too long to walk is reported",
           any("A reviewer walks four" in p
               for p in check({**GOOD, "recognition_traits": [f"t{i}" for i in range(7)]})))
    expect("a non-list is reported",
           any("must be a list" in p for p in check({**GOOD, "recognition_traits": "ink"})))
    # A record with NO style states no direction, so it owes no traits -- the check must not fire on
    # a record that simply has not chosen yet, or it doubles up on the "no style chosen" finding.
    expect("a record with no style is not asked for traits",
           not any("recognition_traits" in p for p in check(
               {k: v for k, v in GOOD.items() if k not in ("style", "recognition_traits")})))

    expect("a missing job is reported", any("`job`" in p for p in check({**GOOD, "job": ""})))
    expect("two references are too few",
           any("minimum" in p for p in check({**GOOD, "references": GOOD["references"][:2]})))
    for field in FIELDS:
        bad = {**GOOD, "references": [{**GOOD["references"][0], field: ""}] + GOOD["references"][1:]}
        expect(f"a reference with no {field} is reported",
               any(f"`{field}`" in p for p in check(bad)))
    expect("an unknown category is reported",
           any("not one of" in p for p in check(
               {**GOOD, "references": [ref(category="vibes", reject="x"), ref(), ref()]})))

    # CONVERGENCE. Sampling only direct competitors inherits the look they copied from each other.
    allsame = {**GOOD, "references": [ref(category="direct", reject="x"),
                                      ref(category="direct"), ref(category="direct")]}
    expect("an all-direct record is reported", any("converged" in p for p in check(allsame)))
    expect("...and a mixed one is not",
           not any("converged" in p for p in check(GOOD)))

    # THE SHOPPING-LIST CHECK. Every reference adopted wholesale means none was examined.
    nothing_rejected = {**GOOD, "references": [ref(), ref(category="direct"), ref(category="outside")]}
    expect("a record rejecting nothing is reported",
           any("shopping list" in p for p in check(nothing_rejected)))
    expect("...and ONE rejection anywhere is enough", check(GOOD) == [])

    # THE SKILL IS THE HANDOFF. A JSON record is parsed when an agent remembers to; a skill is read
    # because its description matches the work. If the approach lives only in the record, every
    # downstream agent re-derives the style from raw references -- and re-derivation is where a
    # family quietly becomes a pile.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        rec = {**GOOD, "style": "minimalist-ink"}
        out = emit_skill(rec, root)
        body = out.read_text(encoding="utf-8")
        expect("the skill lands where skills are read", str(out).endswith(".claude/skills/project-design/SKILL.md"))
        expect("...with frontmatter a matcher can use", body.startswith("---\nname: project-design"))
        expect("...naming the chosen style", "`minimalist-ink`" in body)
        expect("...and the job it serves", "sceptical buyer" in body)
        expect("...carrying what was ADOPTED", "demote the sub-head" in body)
        # The half people drop: without it the same idea is re-proposed next quarter.
        expect("...and what was REJECTED", "their comparison table" in body)
        expect("...marked generated, so nobody hand-edits a second copy",
               "do not hand-edit" in body)
        # Tokens are the pack's job. A skill that restated them would be a second source of truth.
        expect("...deferring tokens to the brand pack", "come from the brand pack" in body)
        # #632. A project with NO exceptions must read exactly as strictly as before — the section
        # is absent, not empty, or every project inherits a mechanism it never opted into.
        expect("...and saying nothing about exceptions when none are declared",
               "signature exception" not in body.lower())
        # #637. The traits reach the generated skill, as a checklist a reviewer walks.
        expect("...carrying the recognition traits", "single ink weight" in body)
        expect("...as a checklist rather than prose", "- [ ] monochrome line-work" in body)
        expect("...marked advisory, not a merge condition", "not the gate" in body)

    # #632. THE GENERATED SKILL IS DOCTRINE THE PROJECT'S OWN AGENT READS, so an absolute "every
    # brief carries this style" would be enforced against a project whose research sanctioned a
    # second one — a wrong rule written into the user's own skill and then gated on.
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        body = emit_skill({**GOOD, "style": "minimalist-ink", "signature_exceptions": [
            {"style": "3d-render", "why": "one rationed luminous prism at hero punctuation",
             "max": 1}]}, root).read_text(encoding="utf-8")
        expect("a declared exception reaches the generated skill", "3d-render" in body)
        expect("...with its ration, since scarcity is the mechanism", "| 1 |" in body)
        expect("...and its reason, which is what separates it from drift",
               "luminous prism" in body)
        expect("...saying plainly that anything else is still refused",
               "is drift, and the plan still refuses it" in body)
        expect("...and that widening it is a RESEARCH decision, not a brief edit",
               "do not add it to a brief" in body)

    # An unreviewable record must NOT become doctrine.
    with tempfile.TemporaryDirectory() as td:
        checks += 1
        try:
            emit_skill({**GOOD, "style": None}, Path(td))
            failures.append("a record with no style should not emit a skill")
        except SystemExit:
            pass

    # THE STYLE IS THE OUTPUT. A record that gathers and does not choose is a mood board.
    expect("a record with references and no style is reported",
           any("no `style` chosen" in p for p in check({**GOOD, "style": None})))
    expect("...and one that chose is fine",
           not any("no `style`" in p for p in check({**GOOD, "style": "minimalist-ink"})))

    # #632. A DECLARED SIGNATURE EXCEPTION is validated in the RECORD, never accepted from a brief:
    # an exception a brief could introduce is drift with better manners.
    def exc(**kw):
        return {**GOOD, "style": "minimalist-ink", "signature_exceptions": [kw]}

    PRISM = {"style": "3d-render", "why": "one rationed prism at hero/CTA punctuation"}
    expect("a well-formed exception is accepted",
           not any("signature_exceptions" in p for p in check(exc(**PRISM))))
    # `why` IS THE MECHANISM. It is the only thing separating a decision from drift, and the next
    # person reading the record is deciding whether to widen it.
    expect("an exception with no `why` is reported",
           any("no `why`" in p for p in check(exc(style="3d-render"))))
    expect("an exception with a blank `why` is reported too",
           any("no `why`" in p for p in check(exc(style="3d-render", why="   "))))
    expect("an exception with no `style` is reported",
           any("no `style`" in p for p in check(exc(why="because"))))
    # EXEMPTING THE PRIMARY reads as though a second style were sanctioned when none is.
    expect("an exception naming the chosen style is reported",
           any("already the chosen style" in p
               for p in check(exc(style="minimalist-ink", why="because"))))
    dup = {**GOOD, "style": "minimalist-ink", "signature_exceptions": [PRISM, {**PRISM, "max": 4}]}
    expect("the same style declared twice is reported",
           any("declared twice" in p for p in check(dup)))
    # A RATION BELOW 1 permits the style and then forbids every use of it.
    expect("`max: 0` is reported", any("`max` is 0" in p for p in check(exc(**PRISM, max=0))))
    expect("a non-numeric `max` is reported",
           any("refusal wearing a permission" in p for p in check(exc(**PRISM, max="lots"))))
    expect("a sane `max` is accepted",
           not any("signature_exceptions" in p for p in check(exc(**PRISM, max=2))))
    # A NON-OBJECT ENTRY must be named rather than crashing the checker — a crash is not a verdict.
    expect("a non-object exception is reported, not raised on",
           any("not an object" in p
               for p in check({**GOOD, "style": "minimalist-ink",
                               "signature_exceptions": ["3d-render"]})))

    # THE LOGIN WALL. It returns a page, not an error, so the capture can BE the wall.
    walled = {**GOOD, "references": [{**ref(reject="x"), "capture": "captures/mobbin-login.png"},
                                     ref(), ref(category="outside")]}
    expect("a sign-in-looking capture with no `gated` is reported",
           any("login wall" in p for p in check(walled)))
    okgated = {**GOOD, "references": [{**ref(reject="x"), "capture": "captures/mobbin-login.png",
                                       "gated": True}, ref(), ref(category="outside")]}
    expect("...and marking it `gated` clears it",
           not any("login wall" in p for p in check(okgated)))

    # BRAND-NAME MECHANISMS. Crude on purpose, and over-reporting is the right direction.
    for mech in ("looks like Linear", "similar to Stripe's pricing", "inspired by Notion",
                 "a Linear-style focal point"):
        expect(f"{mech!r} is caught as a brand claim", looks_like_a_brand(mech))
    for mech in ("one focal point, everything else demoted to plumbing type",
                 "three type steps total and generous negative space instead of dividers",
                 "the product screenshot is the hero; no illustration competes with it"):
        expect(f"{mech[:34]!r}... is accepted", not looks_like_a_brand(mech))
    # An ACRONYM is not a brand claim -- refusing "CSS" would push people to write worse notes.
    expect("an acronym is not a brand claim",
           not looks_like_a_brand("a single CSS grid carries the whole band"))
    # A sentence-opening capital is not a brand claim either.
    expect("a sentence opener is not a brand claim",
           not looks_like_a_brand("Type does the work here. No dividers at all."))

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} research-record assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
