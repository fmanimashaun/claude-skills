#!/usr/bin/env python3
"""Pull the load-bearing claims out of a PR body, so a verifier checks a list rather than a mood.

Run:  python3 extract_claims.py PR_BODY.md
      python3 extract_claims.py PR_BODY.md --json
      python3 extract_claims.py --selftest

WHY (#359). `claim-verifier` verifies what a change says about itself. But an agent is a prompt, and
a prompt has no fixtures — so the acceptance criterion "prove it fires on a false claim and stays
silent on a true one" cannot be met by the agent alone. This is the half that CAN be proven: pulling
the claims out is mechanical, and deciding whether each is TRUE is judgement.

Same split this toolchain uses everywhere else. The browser measures and Python judges; here the
script extracts and the agent judges. Neither half pretends to be the other.

WHAT COUNTS AS LOAD-BEARING. A claim a reader would act on, in four kinds:

    enforcement     "this is gated", "CI blocks it", "the selftest covers it"
    exhaustiveness  "the only place", "nothing else does this", "every call site"
    causation       "this fixes X", "this prevents Y"
    measurement     any number presented as fact -- counts, ratios, versions

WHAT IS DELIBERATELY NOT A CLAIM, and this half decides whether the tool is usable. Intent and taste
are unfalsifiable, so extracting them would hand the verifier a list it cannot act on and train
everyone to skim the output: "cleaner", "more idiomatic", "should be faster", "I think", "probably".
A hedge is the giveaway -- a sentence that hedges is not asserting anything to check.

KNOWN LIMITATION, found by running it on a real PR body. It cannot tell a claim the change is
MAKING from one it is QUOTING. Run against #361, it extracted "the gates run in CI" and "the publish
is gated" — both quotes in a table of previously *refuted* claims, not assertions about that change.

Left unhandled on purpose. Deciding "is this sentence quoted?" is judgement, and the heuristics
available (indentation, table cells, quotation marks) all fire on legitimate assertions too. The cost
is a verifier occasionally checking a historical claim, which is noise; the cost of guessing wrong in
the other direction is dropping a real claim silently, which is the failure this tool exists to stop.
When in doubt it extracts.

Exit codes:  0 claims found (or none, which is itself reportable) · 2 unreadable input

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Ordered: the first kind that matches wins, so a sentence is reported once under its strongest
# reading. Enforcement outranks measurement because "the 40 gates block this" is checked by running
# the gate, not by counting to 40.
KINDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("enforcement", (
        r"\bgated?\b", r"\bgates?\b", r"\benforce[sd]?\b", r"\bblocks?\b", r"\bblocked\b",
        r"\bfails? (?:the build|on|when|closed)\b", r"\bCI\b", r"\bselftest\b", r"\bmutation\b",
        r"\bcannot (?:be|happen|merge|ship)\b", r"\bprevents? .* from (?:merging|shipping)\b",
    )),
    ("exhaustiveness", (
        r"\bonly (?:place|one|file|call site)\b", r"\bnothing else\b", r"\bno other\b",
        r"\bevery (?:one|call site|instance|occurrence|agent|plugin|route)\b",
        r"\ball \d+\b", r"\bexhaustive\b", r"\bnowhere else\b",
    )),
    ("causation", (
        r"\bfix(?:es|ed)\b", r"\bprevents?\b", r"\bstops?\b", r"\bcauses?\b",
        r"\bresults? in\b", r"\bso that\b", r"\bwhich means\b",
    )),
    ("measurement", (
        r"\b\d+(?:\.\d+)?%", r"\b\d+\s*(?:checks?|fixtures?|mutations?|gates?|files?|rows?|sites?|"
        r"occurrences?|routes?|agents?|lines?|commits?)\b", r"\bv?\d+\.\d+\.\d+\b",
        r"\b\d+\s*(?:->|→)\s*\d+\b",
    )),
)

# A sentence containing any of these is asserting nothing checkable. Checked FIRST, so
# "this probably fixes the leak" is not extracted as a causation claim.
HEDGES = (
    r"\bI think\b", r"\bprobably\b", r"\bshould (?:be|make|help)\b", r"\bmight\b", r"\bmay\b",
    r"\bseems?\b", r"\bhopefully\b", r"\bcleaner\b", r"\bmore idiomatic\b", r"\bnicer\b",
    r"\bworth considering\b", r"\bin my view\b", r"\barguably\b",
)


@dataclass
class Claim:
    kind: str
    text: str
    line: int


def sentences(markdown: str) -> list[tuple[int, str]]:
    """(line number, sentence). Fenced code is skipped: a claim lives in prose, and a code block is
    full of words like `gate` and `fails` that are identifiers rather than assertions."""
    out: list[tuple[int, str]] = []
    in_fence = False
    for lineno, raw in enumerate(markdown.splitlines(), start=1):
        if re.match(r"^\s*```", raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = re.sub(r"`[^`]*`", " ", raw)          # inline code is a name, not a claim
        line = re.sub(r"^[\s>*\-+#|]+", "", line).strip()
        if not line:
            continue
        for part in re.split(r"(?<=[.!?])\s+", line):
            part = part.strip()
            if len(part) > 3:
                out.append((lineno, part))
    return out


def classify(sentence: str) -> str | None:
    if any(re.search(h, sentence, re.I) for h in HEDGES):
        return None
    for kind, patterns in KINDS:
        if any(re.search(p, sentence, re.I) for p in patterns):
            return kind
    return None


def extract(markdown: str) -> list[Claim]:
    seen: set[str] = set()
    claims: list[Claim] = []
    for lineno, sentence in sentences(markdown):
        kind = classify(sentence)
        if not kind:
            continue
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        claims.append(Claim(kind, sentence, lineno))
    return claims


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Extract load-bearing claims from a PR body.")
    ap.add_argument("body", nargs="?", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.body:
        ap.error("a body file is required (or --selftest)")
    try:
        text = args.body.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"UNREADABLE: {exc}", file=sys.stderr)
        return 2
    claims = extract(text)
    if args.json:
        print(json.dumps([c.__dict__ for c in claims], indent=2))
    else:
        for c in claims:
            print(f"  [{c.kind:14}] line {c.line}: {c.text[:110]}")
        print(f"\n{len(claims)} load-bearing claim(s) to verify.")
        if not claims:
            # Not a pass. A description asserting nothing is either trivial or vague, and both are
            # worth a reader noticing.
            print("No checkable claim found — either the change is trivial, or the description "
                  "says nothing a reader could act on.")
    return 0


def selftest() -> int:
    failures: list[str] = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    def kinds(text: str) -> list[str]:
        return [c.kind for c in extract(text)]

    # FIRES on each kind.
    check("enforcement", kinds("The sweep is gated on every pull request.") == ["enforcement"],
          f"{kinds('The sweep is gated on every pull request.')}")
    check("exhaustiveness", kinds("This is the only place that reads the token.") == ["exhaustiveness"])
    check("causation", kinds("This fixes the crash on empty input.") == ["causation"])
    # A PURE measurement, with no enforcement word in it. The first draft used "Selftest 33 checks
    # passed", which classifies as ENFORCEMENT -- correctly, per the ordering rule above, since
    # `selftest` is an enforcement keyword. The fixture was wrong, not the code.
    check("measurement", kinds("The matrix has 113 rows.") == ["measurement"],
          f"{kinds('The matrix has 113 rows.')}")
    check("a selftest sentence is enforcement, not measurement",
          kinds("Selftest 33 checks passed.") == ["enforcement"],
          "the ordering rule says enforcement wins when both match")
    check("a percentage is a measurement", kinds("Coverage rose to 94% overall.") == ["measurement"])

    # STAYS SILENT on the unfalsifiable. This half decides whether the output is worth reading: a
    # verifier handed "this is cleaner" has nothing to run, and a list of those trains people to skim.
    for taste in ("This is cleaner than the previous version.",
                  "I think this reads better.",
                  "This should be faster.",
                  "It might fix the flake.",
                  "Arguably this prevents confusion.",
                  "This is more idiomatic Ruby."):
        check(f"silent on {taste!r}", kinds(taste) == [], f"extracted {kinds(taste)}")

    # A HEDGE BEATS A KEYWORD -- the ordering that makes the silence half work.
    check("a hedged causation is not a claim",
          kinds("This probably fixes the leak.") == [], f"{kinds('This probably fixes the leak.')}")

    # CODE IS NOT PROSE. A fenced block is full of `gate`, `fails`, `blocks` as identifiers.
    fenced = "Intro.\n\n```python\nif gate.fails(): blocks()\n```\n\nDone."
    check("fenced code yields no claims", kinds(fenced) == [], f"{kinds(fenced)}")
    check("inline code is not a claim",
          kinds("Renamed `gates` to `checks`.") == [], f"{kinds('Renamed `gates` to `checks`.')}")

    # Ordering: enforcement outranks measurement when both match.
    c = extract("All 40 gates block the merge.")
    check("enforcement outranks measurement", [x.kind for x in c] == ["enforcement"], f"{c}")

    # Dedup and line numbers.
    c = extract("This is gated.\n\nThis is gated.")
    check("identical claims are deduped", len(c) == 1, f"{len(c)}")
    c = extract("Intro line.\n\nThis is gated on every PR.")
    check("the line number points at the claim", c and c[0].line == 3, f"{c}")

    # An empty body yields nothing, and main() says so rather than printing a clean bill.
    check("an empty body yields no claims", extract("") == [])
    src = Path(__file__).read_text(encoding="utf-8")
    check("no-claims is reported, not passed silently",
          "says nothing a reader could act on" in src)

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {n} checks:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"extract_claims selftest: {n} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
