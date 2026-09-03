#!/usr/bin/env python3
"""Where `design-system` lives — resolved for BOTH layouts, in one place (#617).

WHY THIS EXISTS. design-flow's scripts read doctrine that ships in a different plugin: the
`design-system` skill, bundled in `rails-stack`. Three of them found it by counting `..` hops from
their own file, and that arithmetic is calibrated for the **marketplace clone**:

    <clone>/plugins/design-flow/scripts/x.py   ->  ../../..  ->  <clone>/skills/design-system/

From an **install** — which is what `${CLAUDE_PLUGIN_ROOT}` expands to for everyone who did not
clone — the cache interposes `<plugin>/<version>/`:

    cache/claude-skills/design-flow/1.23.1/scripts/x.py  ->  ../../..  ->  cache/claude-skills/
    actual:                                       cache/claude-skills/rails-stack/1.45.0/skills/…

**The two shapes differ in DEPTH, not in offset**, so no amount of parent-counting reconciles them.
That is substrate fact #4 from `/rails-flow:toolchain-check` wearing different clothes: `rails-stack`
is a skills bundle with **no plugin directory**, so a code plugin and the skills bundle have
genuinely disjoint cache shapes. A resolver assuming one shape covers both is the same mistake as
reading one version source and calling it the version.

WHY IT IS SHARED. One question — *where is the doctrine* — answered in three files is three chances
to answer it differently, and #617 proved they had already drifted apart in style if not in outcome.
`plugin-boundaries` allows this: all three callers are inside design-flow, so this is an intra-plugin
import like `brand_pack_lint`, not a reach across a boundary.

NEWEST VERSION WINS when several are cached, for the reason `toolchain_version.py` records: two
versions of a bundle coexist, and taking whichever the filesystem yields first reports the stale one.

Stdlib only, no network.
"""

from __future__ import annotations

import re
from pathlib import Path

SKILL_REL = Path("skills") / "design-system"


def _version_key(name: str) -> tuple:
    """Sort `1.45.0` above `1.9.0`. String order would not — and picks the stale one."""
    parts = re.findall(r"\d+", name)
    return tuple(int(p) for p in parts) if parts else (0,)


def candidates(script: Path) -> list[Path]:
    """Every place the skill can live, in the order to try. Clone first, then installs, newest down.

    `base` is the marketplace root in BOTH layouts, which is what makes one function able to serve
    them: they diverge only by the `<bundle>/<version>/` segments the cache adds.
    """
    base = Path(script).resolve().parent.parent.parent.parent
    installed = sorted(
        (p for p in base.glob(str(Path("*") / "*" / SKILL_REL)) if p.is_dir()),
        key=lambda p: _version_key(p.parent.parent.name), reverse=True)
    return [base / SKILL_REL, *installed]


def find(script: Path) -> Path | None:
    """The `design-system` directory, or None. Callers REFUSE on None rather than degrading."""
    for candidate in candidates(script):
        if candidate.is_dir():
            return candidate
    return None


def describe(script: Path) -> str:
    """Every root tried, for an error message.

    Naming ONE path made #617 read as *"the catalogue is missing"* when the truth was *"I looked in
    the wrong place"* — so a reporter checked that path, found nothing, and reasonably concluded
    their `rails-stack` install was broken. A message that lists what it tried is self-diagnosing.
    """
    return "\n".join(f"    - {c}" for c in candidates(script))


def selftest() -> int:
    import tempfile
    checks, failures = 0, []

    def check(label, cond):
        nonlocal checks
        checks += 1
        if not cond:
            failures.append(label)

    # THE INSTALLED LAYOUT — the one no fixture exercised until #617, which is why a bug that broke
    # every user could sit behind a green suite. Built as a real tree, because the defect was in how
    # a filesystem is actually shaped.
    with tempfile.TemporaryDirectory() as td:
        cache = Path(td) / "cache" / "claude-skills"
        scripts = cache / "design-flow" / "1.23.1" / "scripts"
        scripts.mkdir(parents=True)
        for ver in ("1.9.0", "1.45.0"):
            (cache / "rails-stack" / ver / SKILL_REL / "references").mkdir(parents=True)
        got = find(scripts / "x.py")
        check("the installed layout resolves", got is not None)
        check(f"...newest version wins (got {got.parent.parent.name if got else None})",
              got is not None and got.parent.parent.name == "1.45.0")
        check("...and the clone root is tried first",
              candidates(scripts / "x.py")[0] == (cache / SKILL_REL).resolve())
        check("every root is named for an error message",
              describe(scripts / "x.py").count("- ") >= 2)

    # THE CLONE LAYOUT still resolves — the regression this fix must not cause.
    with tempfile.TemporaryDirectory() as td:
        clone = Path(td) / "clone"
        (clone / "plugins" / "design-flow" / "scripts").mkdir(parents=True)
        (clone / SKILL_REL / "references").mkdir(parents=True)
        got = find(clone / "plugins" / "design-flow" / "scripts" / "x.py")
        check("the clone layout resolves", got == (clone / SKILL_REL).resolve())

    # NOTHING FOUND is None, never a guess. A caller that got a plausible-looking path would read
    # doctrine that is not there and report zero findings.
    with tempfile.TemporaryDirectory() as td:
        empty = Path(td) / "a" / "b" / "c" / "scripts"
        empty.mkdir(parents=True)
        check("an unresolvable tree returns None", find(empty / "x.py") is None)

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} doctrine-path assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys
    sys.exit(selftest() if "--selftest" in sys.argv else 0)
