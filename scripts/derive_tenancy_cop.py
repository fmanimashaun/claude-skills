#!/usr/bin/env python3
"""Derive rails-flow's shipped tenancy cop from the rails-8 doctrine that declares it (#1361).

WHY THIS IS AN ARTIFACT AND NOT A RUNTIME READ. The cop's source of truth is the fenced block in
`skills/rails-8/references/multi-tenancy.md` §7, which ships in the **rails-stack** plugin; the
checker that compares a project's installed copy against it ships in **rails-flow**. A runtime read
across that boundary is #617's class (a clone and an install differ in depth), so the cop is
COMMITTED beside the checker and this script fails on any disagreement. Same shape, and same reasons,
as `derive_mandated_gems.py`.

ANCHORED ON CONTENT. The ```ruby fence containing `class ScopedLookup < Base` -- not "the first ruby
fence" in §7, which would silently follow an edit that inserted an earlier one. The spec's fence names
the class as `RuboCop::Cop::Tenancy::ScopedLookup`, so it cannot match.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCTRINE = ROOT / "skills" / "rails-8" / "references" / "multi-tenancy.md"
ARTIFACT = ROOT / "plugins" / "rails-flow" / "scaffold" / "tenancy" / "scoped_lookup.rb"

FENCE_ANCHOR = "class ScopedLookup < Base"


class Unusable(RuntimeError):
    """The doctrine did not yield what this needs -- never a silent empty file."""


def fenced_block(text: str, anchor: str) -> str:
    """The body of the ONE ```ruby fence containing `anchor`. Refuses on zero or several."""
    blocks = re.findall(r"^```ruby\n(.*?)^```", text, re.S | re.M)
    hits = [b for b in blocks if anchor in b]
    if len(hits) != 1:
        raise Unusable(
            f"expected exactly one ```ruby fence containing {anchor!r} in {DOCTRINE.name}, "
            f"found {len(hits)} of {len(blocks)} fence(s). The doctrine moved; re-anchor this "
            f"deliberately rather than widening the search.")
    return hits[0]


def derive_from(text: str) -> str:
    cop = fenced_block(text, FENCE_ANCHOR)
    # A fence that names the class but defines no lookup list is a cop that checks nothing.
    if "RESTRICT_ON_SEND" not in cop or "def on_send" not in cop:
        raise Unusable("the cop fence has no RESTRICT_ON_SEND / on_send -- it would flag nothing, "
                       "and the installed copy would be a gate that cannot fail.")
    return cop


def derive() -> str:
    if not DOCTRINE.is_file():
        raise Unusable(f"no {DOCTRINE} -- cannot derive the cop from a doctrine that is not there")
    return derive_from(DOCTRINE.read_text(encoding="utf-8"))


def write() -> int:
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(derive(), encoding="utf-8")
    print(f"wrote {ARTIFACT.relative_to(ROOT)} from {DOCTRINE.name}")
    return 0


def check() -> int:
    want = derive()
    rel = ARTIFACT.relative_to(ROOT).as_posix()
    # The blob at HEAD, never the working copy (#833): regenerated-but-unstaged is not shipped.
    committed = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=ROOT,
                               capture_output=True, text=True, timeout=30)
    if committed.returncode != 0:
        print(f"MISSING {rel} at HEAD -- run this script and `git add` it", file=sys.stderr)
        return 1
    if committed.stdout != want:
        print(f"DRIFT: {rel} disagrees with {DOCTRINE.name} §7\n"
              f"  -> python3 scripts/derive_tenancy_cop.py && git add {rel}", file=sys.stderr)
        return 1
    print(f"{rel} matches {DOCTRINE.name} §7")
    return 0


def selftest() -> int:
    checks, failures = 0, []

    def check_(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{('  ' + detail) if detail else ''}")

    COP = ("```ruby\nmodule X\n  class ScopedLookup < Base\n    RESTRICT_ON_SEND = %i[find].freeze\n"
           "    def on_send(node); end\n  end\nend\n```\n")
    SPEC = "```ruby\nRSpec.describe RuboCop::Cop::Tenancy::ScopedLookup, :config do\nend\n```\n"

    got = derive_from(SPEC + COP)
    check_("the cop fence is chosen, not the spec fence that precedes it",
           "class ScopedLookup < Base" in got and "RSpec" not in got, got[:80])
    check_("the body is taken verbatim, without the fence lines",
           got.startswith("module X\n") and not got.rstrip().endswith("```"), repr(got[-20:]))

    for label, text in (("absent", SPEC), ("duplicated", COP + COP)):
        try:
            fenced_block(text, FENCE_ANCHOR)
            check_(f"an {label} anchor refuses", False, "no Unusable raised")
        except Unusable:
            check_(f"an {label} anchor refuses", True)

    HOLLOW = "```ruby\nclass ScopedLookup < Base\nend\n```\n"
    try:
        derive_from(HOLLOW)
        check_("a cop fence with no lookup list refuses", False, "no Unusable raised")
    except Unusable as exc:
        check_("a cop fence with no lookup list refuses", True)
        check_("...saying it would be a gate that cannot fail", "cannot fail" in str(exc), str(exc)[:90])

    # THE REAL DOCTRINE, so the fixtures cannot drift from the file actually shipped.
    if DOCTRINE.is_file():
        real = derive()
        check_("the shipped doctrine yields the cop", "module Tenancy" in real and
               "class ScopedLookup < Base" in real, real[:80])
        check_("...with Rails' querying list plus the three it adds",
               "RESTRICT_ON_SEND = (%i[" in real and "upsert_all" in real
               and "] + %i[unscoped find_by_sql count_by_sql]).freeze" in real)
        check_("...and the csend alias", "alias on_csend on_send" in real)

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} derive-tenancy-cop assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="fail if the artifact and doctrine disagree")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.selftest:
            return selftest()
        return check() if a.check else write()
    except Unusable as exc:
        print(f"CANNOT DERIVE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
