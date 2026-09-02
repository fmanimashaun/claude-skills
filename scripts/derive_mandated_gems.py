#!/usr/bin/env python3
"""Derive rails-flow's mandated-gem list from the rails-8 doctrine that declares it.

WHY THIS IS AN ARTIFACT AND NOT A RUNTIME READ (#797). The list lives in
`skills/rails-8/references/testing.md`, which ships in the **rails-stack** plugin;
`check_mandated_gems.py` ships in **rails-flow**. A runtime read across that boundary is exactly
#617's class -- the marketplace clone and an install differ in DEPTH, not offset, so a hop count
resolves in one and not the other. It recurred twice after the shared resolver existed (#763, #777),
and `doctrine_path` is design-flow's and hardcodes `design-system`, so rails-flow cannot borrow it
without a second copy -- which is how #792's one defect came to exist in two parsers.

So the list is COMMITTED beside the checker, in the same plugin, at a fixed offset; and this script
re-derives it from the doctrine and fails on any disagreement. Same shape as `coverage.md` ->
`docs/coverage.html`: the artifact is the thing that runs, and a gate proves it still matches its
source. Nothing at runtime crosses a plugin boundary.

WHAT IS DERIVED, and the boundary is the point. Only the fenced Gemfile block in `testing.md` --
anchored on `group :development, :test do`, not "the first ruby fence", which would silently follow
an edit that inserted an earlier one. A COMMENTED line is not a declaration: the doctrine's own
`# gem "database_cleaner-active_record"` is commented precisely because `testing.md` §2 says
transactional fixtures already cover it, and requiring it would contradict the file it came from.

NOT the conditional gems. `ecosystem-gems.md` §1's decision table has rows a project chooses --
pagy, pundit, ransack, bullet, rack-mini-profiler -- and their absence is correct. A gate firing on
a conforming project is the false positive that gets it switched off (#476).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCTRINE = ROOT / "skills" / "rails-8" / "references" / "testing.md"
ARTIFACT = ROOT / "plugins" / "rails-flow" / "mandated_gems.json"

FENCE_ANCHOR = "group :development, :test do"
# No `^`: `re.match` anchors at position 0 on its own, so the two were redundant -- and BECAUSE they
# were redundant, a mutation removing either one survived every fixture. Two guards for one job means
# neither is testable. One mechanism now: `match`, whose swap to `search` a fixture can witness.
GEM = re.compile(r"""\s*gem\s+(?P<q>['"])(?P<name>[A-Za-z0-9_\-]+)(?P=q)""")


class Unusable(RuntimeError):
    """The doctrine did not yield what this needs -- never a silent empty list."""


def fenced_block(text: str, anchor: str) -> str:
    """The ```ruby fence CONTAINING `anchor`.

    Anchored on content, not position. "The first ruby fence" would follow any edit that inserted an
    earlier one, and the failure would be a silently shorter list -- the shape this repo keeps
    paying for.
    """
    blocks = re.findall(r"^```ruby\n(.*?)^```", text, re.S | re.M)
    hits = [b for b in blocks if anchor in b]
    if len(hits) != 1:
        raise Unusable(
            f"expected exactly one ```ruby fence containing {anchor!r} in {DOCTRINE.name}, "
            f"found {len(hits)} of {len(blocks)} fence(s). The doctrine moved; re-anchor this "
            f"deliberately rather than widening the search.")
    return hits[0]


def gems_in(block: str) -> list[str]:
    """Every UNCOMMENTED gem declared in the block, in declaration order.

    NO EXPLICIT COMMENT SKIP. `re.match` anchors at position 0, so `\\s*gem` cannot reach the `gem`
    in `# gem "x"` -- the `#` stops it. A skip line was dead code, and so was the `^` that used to
    sit in the pattern: all three did the same job, so a mutation removing any ONE survived every
    fixture. Two guards for one behaviour means neither is testable. One mechanism now -- `match`,
    not `search` -- and the commented-gem fixture witnesses exactly that swap.

    Second time today the same redundant guard appeared; `qa_config.declared_gems` carried it too.
    """
    return [m.group("name") for m in (GEM.match(l) for l in block.splitlines()) if m]


def derive_from(text: str) -> list[str]:
    """The list, from doctrine TEXT. Takes text so a fixture can drive the empty case.

    The guard below lived inside `derive()`, which reads the real file -- so no fixture could reach
    it, and a mutation removing it survived every one. A refusal nothing can exercise is a refusal
    nobody knows still works.
    """
    gems = gems_in(fenced_block(text, FENCE_ANCHOR))
    if not gems:
        raise Unusable(
            "the testing fence declared no gems. An empty list would make `mandated-gems` pass "
            "every project — a gate that cannot fail.")
    return gems


def derive() -> list[str]:
    if not DOCTRINE.is_file():
        raise Unusable(f"no {DOCTRINE} — cannot derive the list from a doctrine that is not there")
    return derive_from(DOCTRINE.read_text(encoding="utf-8"))


def payload(gems: list[str]) -> dict:
    return {
        "_comment": [
            "GENERATED by scripts/derive_mandated_gems.py — do not hand-edit.",
            "",
            "Source of truth: skills/rails-8/references/testing.md, the fenced Gemfile block",
            "anchored on `group :development, :test do`. Edit THAT and re-run the script;",
            "`mandated gems derived` fails if this file and the doctrine disagree.",
            "",
            "Committed rather than read at runtime because testing.md ships in rails-stack and",
            "the checker ships in rails-flow: a cross-plugin path resolves in a clone and not in",
            "an install (#617 / #763 / #777). Nothing at runtime crosses that boundary.",
            "",
            "A COMMENTED gem is not a declaration — testing.md comments out",
            "database_cleaner-active_record because transactional fixtures already cover it.",
        ],
        "testing_stack": gems,
    }


def write() -> int:
    ARTIFACT.write_text(json.dumps(payload(derive()), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {ARTIFACT.relative_to(ROOT)} — {len(derive())} gem(s)")
    return 0


def check() -> int:
    want = payload(derive())
    if not ARTIFACT.is_file():
        print(f"MISSING {ARTIFACT.relative_to(ROOT)} — run this script without --check",
              file=sys.stderr)
        return 1
    have = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    if have.get("testing_stack") != want["testing_stack"]:
        print(f"DRIFT: {ARTIFACT.relative_to(ROOT)} disagrees with {DOCTRINE.name}\n"
              f"  doctrine: {want['testing_stack']}\n"
              f"  artifact: {have.get('testing_stack')}\n"
              f"  -> python3 scripts/derive_mandated_gems.py && git add plugins/rails-flow/",
              file=sys.stderr)
        return 1
    print(f"{ARTIFACT.relative_to(ROOT)} matches {DOCTRINE.name} — "
          f"{len(want['testing_stack'])} gem(s)")
    return 0


def selftest() -> int:
    checks, failures = 0, []

    def check_(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{('  ' + detail) if detail else ''}")

    BLOCK = ("```ruby\ngroup :development, :test do\n"
             '  gem "rspec-rails"\n  gem "factory_bot_rails"\nend\n\ngroup :test do\n'
             '  gem "simplecov", require: false\n'
             '  # gem "database_cleaner-active_record"  # only if transactions cannot cover you\n'
             "end\n```\n")
    got = gems_in(fenced_block(BLOCK, FENCE_ANCHOR))
    check_("every uncommented gem is derived",
           got == ["rspec-rails", "factory_bot_rails", "simplecov"], f"{got}")
    # THE CLAUSE THAT KEEPS THIS HONEST. testing.md comments database_cleaner out on purpose;
    # requiring it would contradict the very file the list came from.
    check_("a COMMENTED gem is not derived", "database_cleaner-active_record" not in got, f"{got}")

    # ANCHORED ON CONTENT, not position: an earlier fence must not be picked up silently.
    two = "```ruby\nputs 1\n```\n" + BLOCK
    check_("an earlier unrelated fence is not chosen",
           gems_in(fenced_block(two, FENCE_ANCHOR)) == got)

    # ...and an ambiguous or absent anchor REFUSES rather than guessing.
    for label, text in (("absent", "```ruby\nputs 1\n```\n"), ("duplicated", BLOCK + BLOCK)):
        try:
            fenced_block(text, FENCE_ANCHOR)
            check_(f"an {label} anchor refuses", False, "no Unusable raised")
        except Unusable:
            check_(f"an {label} anchor refuses", True)

    # AN EMPTY DERIVATION REFUSES. A fence with only commented gems yields nothing, and returning
    # [] would make `mandated-gems` pass every project -- a gate that cannot fail. This needs
    # `derive_from` to take text: while the guard sat inside `derive()` reading the real file, no
    # fixture could reach it and a mutation removing it survived.
    EMPTY = ('```ruby\ngroup :development, :test do\n'
             '  # gem "rspec-rails"   # all commented\nend\n```\n')
    try:
        derive_from(EMPTY)
        check_("an all-commented fence refuses", False, "no Unusable raised")
    except Unusable as exc:
        check_("an all-commented fence refuses", True)
        check_("...saying an empty list is a gate that cannot fail",
               "cannot fail" in str(exc), str(exc)[:100])

    # THE REAL DOCTRINE, so the fixtures cannot drift from the file actually shipped.
    if DOCTRINE.is_file():
        real = derive()
        check_("the shipped doctrine yields a non-trivial list", len(real) >= 8, f"{len(real)}")
        check_("...including simplecov, webmock and vcr",
               {"simplecov", "webmock", "vcr"} <= set(real), f"{real}")
        check_("...and NOT the commented database_cleaner",
               not any("database_cleaner" in g for g in real), f"{real}")

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} derive-mandated-gems assertion(s)")
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
