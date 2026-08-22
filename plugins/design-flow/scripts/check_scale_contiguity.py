#!/usr/bin/env python3
"""Refuse a fluid scale with a hole in it, or a step the prose promises and the file never declares.

Run:  python3 check_scale_contiguity.py
      python3 check_scale_contiguity.py --selftest

WHY THIS EXISTS (#750). `foundations-tokens.md` said, in a comment:

    /* fluid space — --space-3xs … --space-3xl + one-off pairs (--space-s-l) */

and declared `2xs, xs, s, m, l`. Five promised tokens did not exist, including the `--space-s-l` the
comment names outright. The type block did the same: it announced `--text-step--2 … --text-step-5`,
declared `-1 … 3`, and closed with "… up to step-5 for heroes".

A live project reached for `xl`, `2xl`, `3xl` and `text-step-4`, found nothing, and carried local
values — which then read as the project diverging from the system when the system had simply not
declared what it advertised.

**A hole is worse than a short scale.** A component stepping up from `3` lands on `5`: a 1.44x jump
where the scale's own ratio is 1.20. Nothing errors; the type is just wrong, on one surface, and the
next person reads it as a design choice.

WHAT IT CHECKS, and both halves are mechanical:

  * **Contiguity** — the declared steps of a scale form a run with no gap. `-1, 0, 1, 2, 3, 5` fails
    and names `4`.
  * **The prose does not overpromise** — a range written as `--x-a … --x-b` in a comment must have
    every step between `a` and `b` declared. That is what makes the ellipsis honest.

WHAT IT DOES NOT DO. It has no opinion on where a scale should START or STOP. A project needing only
`s`…`l` is entitled to that, and a rule demanding `3xl` would fire on correct work. It only refuses a
gap, and a promise the file does not keep.

Exit codes:  0 = clean · 1 = a hole or an unkept promise · 2 = the reference is missing

Stdlib only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DOC = REPO / "skills" / "fidara-design" / "references" / "foundations-tokens.md"

# The two scales, and how their step names order. `3xs < 2xs < xs < s < m < l < xl < 2xl < 3xl`.
SPACE_ORDER = ["3xs", "2xs", "xs", "s", "m", "l", "xl", "2xl", "3xl"]
# Named pairs and one-offs (`section`, `s-l`) are not steps on the ladder. They need no exemption
# list: `SPACE_ORDER` IS the ladder, and the filter below drops anything not on it. An explicit
# SPACE_EXEMPT was written first and deleted -- the mutation emptying it survived, because nothing
# could distinguish its presence from its absence. A line no fixture can tell apart does nothing.


def declared_space(text: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"--space-([a-z0-9-]+)\s*:", text)]


def declared_type(text: str) -> list[int]:
    return [int(m.group(1)) for m in re.finditer(r"--text-step-(-?\d+)\s*:", text)]


def promised(text: str, prefix: str) -> list[str]:
    """Step names a comment advertises as a range, e.g. `--space-3xs … --space-3xl`."""
    out = []
    for m in re.finditer(re.escape(prefix) + r"([a-z0-9-]+)\s*…\s*" + re.escape(prefix)
                         + r"([a-z0-9-]+)", text):
        out.append((m.group(1), m.group(2)))
    return out


def findings(text: str) -> list[str]:
    out: list[str] = []

    idx = sorted({SPACE_ORDER.index(s) for s in declared_space(text)
                  if s in SPACE_ORDER})
    if idx:
        gaps = [SPACE_ORDER[i] for i in range(idx[0], idx[-1] + 1)
                if i not in idx]
        if gaps:
            out.append(f"space scale has a hole: {', '.join('--space-' + g for g in gaps)} "
                       f"sit inside the declared run and are not declared")

    nums = sorted(set(declared_type(text)))
    if nums:
        holes = [n for n in range(nums[0], nums[-1] + 1) if n not in nums]
        if holes:
            out.append(f"type scale has a hole: {', '.join('--text-step-' + str(h) for h in holes)} "
                       f"— a component stepping up lands past it")

    for prefix, present in (("--space-", set(declared_space(text))),
                            ("--text-step-", {str(n) for n in declared_type(text)})):
        for lo, hi in promised(text, prefix):
            for end in (lo, hi):
                if end not in present:
                    out.append(f"the comment promises {prefix}{lo} … {prefix}{hi}, but "
                               f"{prefix}{end} is never declared — an ellipsis is not a token")
    return out


def _selftest() -> int:
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    # THE REPORTED SHAPE: a run with the middle missing.
    holed = "--space-2xs: a;\n--space-xs: a;\n--space-s: a;\n--space-3xl: a;\n"
    f = findings(holed)
    check("a hole in the space run is a finding", any("space scale has a hole" in x for x in f))
    check("...and it names every missing step",
          any("--space-m" in x and "--space-l" in x and "--space-xl" in x for x in f))

    check("a contiguous space run is silent",
          not any("space scale" in x for x in
                  findings("--space-s: a;\n--space-m: a;\n--space-l: a;\n")))
    # A SHORT scale is not a hole. Demanding 3xl would fire on correct work.
    check("a short scale is not a hole",
          findings("--space-xs: a;\n--space-s: a;\n") == [])
    # Named pairs are not ladder steps.
    check("a one-off pair is not read as a hole",
          findings("--space-s: a;\n--space-m: a;\n--space-s-l: a;\n--space-section: a;\n") == [])

    holed_t = "--text-step-1: a;\n--text-step-2: a;\n--text-step-3: a;\n--text-step-5: a;\n"
    f = findings(holed_t)
    check("a skipped type step is a finding", any("type scale has a hole" in x for x in f))
    check("...and names it", any("--text-step-4" in x for x in f))
    check("negative steps are ordered correctly",
          findings("--text-step--2: a;\n--text-step--1: a;\n--text-step-0: a;\n") == [])

    # THE PROSE HALF: the exact defect this was written for.
    over = ("/* fluid space — --space-3xs … --space-3xl */\n"
            "--space-s: a;\n--space-m: a;\n--space-l: a;\n")
    f = findings(over)
    check("a comment promising an undeclared end is a finding",
          any("an ellipsis is not a token" in x for x in f))
    kept = ("/* fluid space — --space-s … --space-l */\n"
            "--space-s: a;\n--space-m: a;\n--space-l: a;\n")
    check("...and silent when the promise is kept",
          not any("ellipsis" in x for x in findings(kept)))

    # Against the REAL file, because a selftest that only sees fixtures is the bug
    # maintainer_doctor was written about.
    if DOC.is_file():
        check("the shipped scales are contiguous and keep their promises",
              findings(DOC.read_text(encoding="utf-8")) == [])

    print(f"\n{ok} passed, {len(bad)} failed")
    for b in bad:
        print(f"  FAIL {b}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not DOC.is_file():
        print(f"no {DOC}", file=sys.stderr)
        return 2
    found = findings(DOC.read_text(encoding="utf-8"))
    if found:
        print(f"{len(found)} scale finding(s):", file=sys.stderr)
        for f in found:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("clean — every declared scale is contiguous and every promised range is declared")
    return 0


if __name__ == "__main__":
    sys.exit(main())
