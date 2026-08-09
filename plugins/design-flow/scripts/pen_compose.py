#!/usr/bin/env python3
"""Decide whether a composition surface is usable, and judge a composition's INTENT (#600, #601).

Two modes, one concern — composing in pen before writing view code:

    --surface   is a composition surface usable here, and which one?   (#600)
    --intent    does this composition honour the brief it came from?   (#601)

WHY THE SURFACE DECISION IS A SCRIPT AND NOT A PARAGRAPH. The rule has three branches and one of
them is a silent skip, which is exactly the shape that rots into "it always offers" or "it never
does". Written down it is prose nothing enforces; written here it has fixtures, including the one
that matters most — that an unavailable surface degrades to today's behaviour rather than stopping.

THE TIER IS NEVER A PREREQUISITE. No design-flow command may stop for want of pen. That is the one
place the qa-flow precedent must NOT be copied: there the MCP is *required* by the one command that
uses it, which stops without it. Here the tier is strictly additive, and a machine without pen must
behave byte-identically to one before this existed.

WHY PASS 1 IS INTENT AND NOT CONFORMANCE. `design-auditor`'s checklist is overwhelmingly mechanical
and reads the ERB — role tokens, `focus-visible`, ARIA, `min-h-touch`, and a motion rule doctrine
itself calls arithmetic. **None of that is answerable from a design**, however readable, because they
are properties of the implementation. So conformance cannot move earlier; that is not a tooling limit
but what conformance means. What CAN be judged before code is whether the composition honours the
brief and the researched style — and this checks that, mechanically, on the document.

IT NEVER BLOCKS. Every finding here is advisory, and the exit code says so. A gate on judgement gets
switched off, and then nothing checks judgement at all; `design-auditor` keeps its authority by only
ever asserting facts.

Exit codes:  0 usable / no findings · 1 findings (advisory) · 2 unusable input

Stdlib only, no network, no MCP.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

# #632. IMPORTED, not re-implemented. What counts as a declared signature exception is one
# rule, and two copies of it would drift into a project that passes `asset_plan --check` and
# is then flagged here for the very device the research sanctioned. `asset_plan` is stdlib
# only and side-effect free on import (its `main` is under `__main__`).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from asset_plan import signature_exceptions  # noqa: E402

CONFIG_PATH = Path(".design-flow/generation.json")
RESEARCH_PATH = Path("docs/design/reference-research.json")

# What a project may ask for. `none` is a real choice, not a fallback -- a shared repo may want its
# UI built one way regardless of what any one machine happens to have installed.
SURFACES = ("auto", "pencil-mcp", "pencil-cli", "none")

# Copy that means nobody has written the copy yet. Visible in a composition, and the cheapest thing
# to catch before it becomes a screenshot in a review.
PLACEHOLDER = re.compile(r"\b(lorem|ipsum|dolor sit|todo|tbd|placeholder|xxx+)\b", re.I)


def load_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"{path} is not valid JSON ({exc})")


def choose_surface(config: dict, mcp_available: bool, cli_present: bool) -> dict:
    """Which surface to use, and WHY — the why is half the value when the answer is 'none'.

    DEFAULT IS ON WHERE AVAILABLE (maintainer decision on #600), not off. The argument for defaulting
    off was that a machine which merely happens to have pen installed should not silently change how
    a shared repo builds UI. That worry is weaker than it looks *here*, because a `.pen` file is
    never a merge artefact and never a gate input: the output contract is identical either way, and
    two developers exploring differently still converge on ERB judged by the same verdicts. A tier
    that is off by default is a tier nobody discovers.
    """
    want = str(config.get("exploration_surface") or "auto").lower()
    if want not in SURFACES:
        return {"surface": "none", "usable": False,
                "why": f"`exploration_surface` is {want!r}, which is not one of "
                       f"{', '.join(SURFACES)}. Falling back to composing in code."}
    if want == "none":
        return {"surface": "none", "usable": False,
                "why": "this project sets `exploration_surface: none`. Composing in code."}
    if want in ("auto", "pencil-mcp") and mcp_available:
        return {"surface": "pencil-mcp", "usable": True,
                "why": "the pencil MCP is available and a document is open."}
    if want in ("auto", "pencil-cli") and cli_present:
        return {"surface": "pencil-cli", "usable": True,
                "why": "the `pen` CLI is on PATH — headless, so this works unattended."}
    # NOT AN ERROR. The whole contract is that an absent surface is a silent skip, so the caller
    # gets a reason it can print in one line and then carries on exactly as before.
    asked = "" if want == "auto" else f" ({want} was requested)"
    return {"surface": "none", "usable": False,
            "why": f"no composition surface is reachable here{asked}: the pencil MCP is not "
                   f"available to this session and the `pen` CLI is not on PATH. Composing in code, "
                   f"which is what happens without this tier at all."}


def walk(nodes: list) -> list:
    out = []
    for n in nodes:
        out.append(n)
        out.extend(walk(n.get("children") or []))
    return out


def check_intent(doc: dict, style: str | None, briefs: dict, surface: str | None,
                 exceptions: dict | None = None) -> list[str]:
    """Does this composition honour the brief it came from? ADVISORY, and mechanical.

    Deliberately not taste. Every finding below is a fact about the document — a raw colour, a
    missing library reference, placeholder copy — because a pre-code step that argued about
    hierarchy would be arguing, and the reviewer already has `/design-flow:critique` for that.
    """
    findings: list[str] = []
    nodes = walk(doc.get("children") or [])
    if not nodes:
        findings.append("this composition is empty — there is nothing to judge yet.")
        return findings

    # RAW COLOUR is the one that matters most, because it silently forks the brand: a composition
    # painted in literal hex looks right today and does not follow the pack tomorrow.
    raw = [n for n in nodes
           for prop in ("fill", "stroke")
           if isinstance(n.get(prop), str) and n[prop].startswith("#")]
    if raw:
        named = ", ".join(sorted({str(n.get("name") or n.get("id")) for n in raw})[:6])
        findings.append(
            f"{len(raw)} node(s) are painted with a literal colour rather than a role token "
            f"({named}). A composition in raw hex does not follow the brand pack and cannot compile "
            f"to a token-native asset — paint from `$--token` variables instead.")

    # THE LIBRARY EXISTS TO BE USED. A composition that hand-draws a button has not explored the
    # design system; it has explored a drawing of one.
    refs = [n for n in nodes if n.get("type") == "ref"]
    generated = [n for n in nodes if str(n.get("id", "")).startswith("fm-")]
    if not refs and not generated:
        findings.append(
            "nothing in this composition references the generated library (no `ref` nodes, no "
            "`fm-*` components). Compose from the library so what you are choosing between is real "
            "components rather than drawings of them — `pen_library.py` scaffolds it.")

    for n in nodes:
        content = n.get("content")
        if isinstance(content, str) and PLACEHOLDER.search(content):
            findings.append(
                f"{n.get('name') or n.get('id')}: the copy is still placeholder text "
                f"({content[:40]!r}). Copy is a positioning decision — a composition reviewed with "
                f"lorem in it gets reviewed on its layout alone.")

    # THE RESEARCH DECIDED THE STYLE, and a brief that ignores it is the defect the plan already
    # refuses for assets. The same join, one step earlier.
    # #632. The SAME carve-out the plan makes, and it has to be made here too: a project with a
    # declared signature exception would otherwise pass `asset_plan --check` and then be flagged
    # composing that very device, by a rule the research already sanctioned. One cause, two tools.
    allowed = {style} | set(exceptions or {})
    if style and surface and (briefs.get(surface) or {}).get("style") not in ({None} | allowed):
        extra = (f" Declared signature exception(s): {', '.join(sorted(exceptions))}."
                 if exceptions else
                 " A deliberate second style is expressible — declare it in the research as a "
                 "`signature_exceptions` entry with its own `why`.")
        findings.append(
            f"the research chose {style!r}, but the brief for {surface!r} names "
            f"{briefs[surface]['style']!r}. One family, one style — a set that mixes them is the "
            f"pile this whole path exists to avoid.{extra}")
    return findings


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="composition surface + intent checks for design-flow")
    ap.add_argument("--surface", action="store_true", help="report which surface is usable here")
    ap.add_argument("--mcp-available", action="store_true",
                    help="the caller can see the mcp__pencil__* tools AND a document is open")
    ap.add_argument("--intent", default=None, metavar="PEN", help="judge a composition's intent")
    ap.add_argument("--for-surface", default=None,
                    help="the surface class this composition serves, for the brief join")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    root = Path.cwd()

    if args.surface:
        verdict = choose_surface(load_json(root / CONFIG_PATH), args.mcp_available,
                                 shutil.which("pen") is not None)
        print(json.dumps(verdict, indent=2))
        # ALWAYS 0. "No surface" is a normal, expected answer -- returning non-zero would make a
        # machine without pen look like a machine with a problem, and callers would learn to ignore
        # the exit code, which is how a real failure later goes unnoticed.
        return 0

    if args.intent:
        doc = load_json(Path(args.intent))
        if not doc:
            print(f"cannot read a composition at {args.intent}", file=sys.stderr)
            return 2
        research = load_json(root / RESEARCH_PATH)
        config = load_json(root / CONFIG_PATH)
        findings = check_intent(doc, research.get("style"), config.get("briefs") or {},
                                args.for_surface, signature_exceptions(research))
        print("\n".join(f"- {f}" for f in findings)
              or "this composition honours the brief it came from.")
        # ADVISORY. Exit 1 says "read these", never "you may not proceed": conformance is judged on
        # the ERB by `design-auditor`, and this pass must not be able to block a merge.
        print("\nAdvisory — conformance is judged on the implementation, not on the design. "
              "`/design-flow:audit` remains the gate.")
        return 1 if findings else 0

    ap.print_help()
    return 2


def selftest() -> int:
    checks, failures = 0, []

    def check(label, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failures.append(label)

    # THE SURFACE DECISION. The branch that matters most is the last one: absent is a silent skip.
    check("auto + MCP available picks the MCP",
          choose_surface({}, True, False)["surface"] == "pencil-mcp")
    check("auto + only the CLI picks the CLI",
          choose_surface({}, False, True)["surface"] == "pencil-cli")
    check("the MCP wins when both are present",
          choose_surface({}, True, True)["surface"] == "pencil-mcp")
    # DEFAULT IS ON WHERE AVAILABLE -- the maintainer decision on #600. An empty config must offer.
    check("an unconfigured project still gets the tier",
          choose_surface({}, True, False)["usable"] is True)
    check("`none` is honoured even when a surface exists",
          choose_surface({"exploration_surface": "none"}, True, True)["usable"] is False)
    check("...and says so rather than looking broken",
          "exploration_surface: none" in choose_surface({"exploration_surface": "none"}, True, True)["why"])
    # A REQUESTED surface that is not there falls through rather than failing.
    v = choose_surface({"exploration_surface": "pencil-cli"}, True, False)
    check("a requested surface that is absent does not silently use another",
          v["surface"] == "none")
    check("...and names what was asked for", "pencil-cli was requested" in v["why"])
    v = choose_surface({"exploration_surface": "banana"}, True, True)
    check("an unknown setting falls back rather than crashing", v["usable"] is False)
    check("...and lists the valid values", "pencil-mcp" in v["why"])
    # THE SILENT SKIP. Nothing reachable is a normal answer, phrased so a caller can print one line.
    v = choose_surface({}, False, False)
    check("nothing reachable is not an error", v["usable"] is False)
    check("...and the reason says work continues as before", "Composing in code" in v["why"])

    # INTENT. Every finding is a FACT about the document, never a judgement about hierarchy.
    good = {"children": [{"type": "ref", "id": "i1", "ref": "fm-button-primary"},
                         {"type": "rectangle", "id": "r1", "name": "Panel", "fill": "$--card"},
                         {"type": "text", "id": "t1", "content": "Reconcile this month"}]}
    check("a clean composition has no findings", check_intent(good, None, {}, None) == [])

    raw = {"children": [{"type": "ref", "id": "i", "ref": "fm-x"},
                        {"type": "rectangle", "id": "bad", "name": "Hero", "fill": "#FF0000"}]}
    f = check_intent(raw, None, {}, None)
    check("a literal colour is reported", any("literal colour" in x for x in f))
    check("...naming the node", any("Hero" in x for x in f))

    lonely = {"children": [{"type": "rectangle", "id": "x", "fill": "$--card"}]}
    check("a composition using no library component is reported",
          any("references the generated library" in x for x in check_intent(lonely, None, {}, None)))
    check("...and an `fm-` component counts as using it",
          not any("references the generated library" in x
                  for x in check_intent({"children": [{"type": "frame", "id": "fm-card",
                                                       "fill": "$--card"}]}, None, {}, None)))

    lorem = {"children": [{"type": "ref", "id": "i", "ref": "fm-x"},
                          {"type": "text", "id": "t", "name": "Body", "content": "Lorem ipsum dolor"}]}
    check("placeholder copy is reported",
          any("placeholder text" in x for x in check_intent(lorem, None, {}, None)))
    check("...while real copy is not",
          not any("placeholder" in x for x in check_intent(good, None, {}, None)))

    # THE RESEARCH DECIDED THE STYLE — the same join the asset plan enforces, one step earlier.
    briefs = {"marketing-hero": {"style": "3d-render"}}
    # #632. A DECLARED EXCEPTION IS HONOURED HERE TOO. Without this the project would pass
    # `asset_plan --check` and then be flagged composing the very device its research sanctioned —
    # one cause, two tools, and the second one contradicting the first.
    check("a declared signature exception is not flagged here",
          check_intent(good, "minimalist-ink", {"marketing-hero": {"style": "3d-render"}},
                       "marketing-hero", {"3d-render": {"why": "one prism", "max": 1}}) == [])
    check("...while an undeclared style still is",
          any("One family, one style" in x
              for x in check_intent(good, "minimalist-ink",
                                    {"marketing-hero": {"style": "cartoon"}}, "marketing-hero",
                                    {"3d-render": {"why": "one prism", "max": 1}})))
    check("...and the refusal names what IS declared",
          any("Declared signature exception(s): 3d-render" in x
              for x in check_intent(good, "minimalist-ink",
                                    {"marketing-hero": {"style": "cartoon"}}, "marketing-hero",
                                    {"3d-render": {"why": "one prism", "max": 1}})))
    check("a brief that ignores the researched style is reported",
          any("One family, one style" in x
              for x in check_intent(good, "minimalist-ink", briefs, "marketing-hero")))
    check("...and one that honours it is silent",
          not any("One family" in x for x in
                  check_intent(good, "minimalist-ink", {"marketing-hero": {"style": "minimalist-ink"}},
                               "marketing-hero")))
    check("an empty composition says so rather than passing",
          any("nothing to judge" in x for x in check_intent({"children": []}, None, {}, None)))

    # THE TIER NEVER BLOCKS. `--surface` always exits 0, whatever it found -- a machine without pen
    # must not look like a machine with a problem.
    import io
    import contextlib
    for available in (True, False):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = main(["--surface"] + (["--mcp-available"] if available else []))
        check(f"--surface exits 0 when available={available}", code == 0)
    checks += 1

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} pen-compose assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
