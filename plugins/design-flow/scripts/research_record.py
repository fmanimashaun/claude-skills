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
            "references": [ref(category="direct", reject="their comparison table"),
                           ref(category="adjacent"), ref(category="outside")]}
    expect("a complete record passes", check(GOOD) == [])

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
