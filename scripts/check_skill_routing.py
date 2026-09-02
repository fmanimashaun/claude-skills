#!/usr/bin/env python3
"""Assert every shipped skill routes to all of its own reference files, one level deep.

Run:  python3 scripts/check_skill_routing.py            # check, fail on a finding
      python3 scripts/check_skill_routing.py --selftest  # prove each rule fires AND stays silent

WHY (#158). The issue proposed rebuilding `SKILL.md` as a "capability router" because — quote — "A
skill is loaded as a unit, so a task that only needs `jobs-and-realtime.md` still pays for
`deployment-kamal.md`". **That premise is refuted by the official docs.** Claude Code loads skills
by progressive disclosure, and reference files cost nothing until read:

  > "On-demand file access: Claude reads only the files each task needs. A Skill can include dozens
  >  of reference files, but if your task only needs the sales schema, that's the one file Claude
  >  loads. The rest stay on the filesystem and cost zero tokens."
  -- https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview

So there is no router to build: the dispatch tables already in our `SKILL.md` files ARE the
documented pattern ("Pattern 2: Domain-specific organization"). What the issue got right is its
last acceptance criterion — that reachability must be *asserted by a script rather than by review*.
That is this file, and it found one real defect on its first run (see `unrouted-reference`).

THE RULES, each traceable to a documented requirement rather than to taste:

  * `unrouted-reference` -- a file in `references/` that its own `SKILL.md` never names.
      > "Keep references one level deep from SKILL.md. All reference files should link directly
      >  from SKILL.md to ensure Claude reads complete files when needed."
      > "Claude may partially read files when they're referenced from other referenced files ...
      >  resulting in incomplete information."
      -- https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
      This is not hypothetical tidiness. `design-system/references/coverage.md` (230 lines of
      component doctrine) was reachable ONLY from `brand.md` and `marketing-copy.md` -- depth two,
      the exact shape the docs say yields partial reads.

  * `dead-reference-link` -- `SKILL.md` names `references/x.md` that does not exist. A router
      pointing at nothing is worse than one pointing at nothing *visibly*: the model follows the
      path, gets an error, and continues without the doctrine.

  * `oversized-skill-body` -- `SKILL.md` over 500 lines. Unlike `references/`, the SKILL.md body IS
      loaded in full on every trigger (Level 2), so this is the one size that always costs.
      > "Keep SKILL.md under 500 lines. Move detailed reference material to separate files."
      -- https://code.claude.com/docs/en/skills

WHAT COUNTS AS ROUTING, and why it is not markdown-link syntax. The docs require the file be
*referenced from* SKILL.md; they do not mandate `[]()`. Our shipped skills route via a dispatch
table of `` `references/x.md` `` code spans (rails-8, hotwire) and via markdown links whose target
is `references/x.md` (design-system). Demanding link syntax would fail all 19 rails-8 rows for a
rule the docs never state -- inventing strictness is as dishonest as missing a defect. So the test
is that the **path** `references/<name>` appears. A bare prose mention of the bare filename does
NOT count: `interaction-stimulus.md` says "`coverage.md` used to say ..." while routing nothing,
and treating that as routing would have hidden the very defect this file was written to find.

BIAS, stated deliberately (the issue's AC4, applied to the gate rather than to a router). Where the
sources differ the STRICTER reading wins: best-practices says "SKILL.md **body** under 500 lines",
the Claude Code page says "SKILL.md under 500 lines", so the whole file is measured, frontmatter
included. Likewise ambiguity in the input is an ERROR, never a skip -- a skill directory with no
`SKILL.md`, or a run that examined nothing, exits non-zero rather than reporting clean.

SCOPE. The SHIPPED skills under `skills/`, pinned by NAME in `SHIPPED_SKILLS` -- not by count.
This line said "the four" while the set held five, which is the transcription class the
`derived-artifacts` skill itself warns about, sitting in the docstring of a gate. `evals/weak-skill/` is
excluded on purpose: it is a deliberately low-quality A/B control for the eval harness, not
something a user installs, and "improving" it would destroy what it measures.

The pin is asserted by the GATE against the real tree, not by the selftest, and both directions
fail: a new skill that nobody added here, and a name in here that no longer exists. That placement
is deliberate twice over. A scope living only in a selftest is a claim about fixtures rather than
about what we ship — the claims-vs-enforcement class — and it also keeps `--selftest` hermetic, so
the mutation harness can run it against a mutated copy without needing the skills tree beside it.

Exit codes:  0 clean · 1 a finding · 2 the skills tree could not be read as expected

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO / "skills"

# Claude Code's documented Level-2 budget. See the module docstring for the two quotes and why the
# stricter (whole-file) reading is the one measured.
MAX_SKILL_LINES = 500

# The skills we DISTRIBUTE (marketplace.json's rails-stack `skills` array). Asserted exactly, in
# both directions, against the real tree — see "SCOPE" in the docstring.
SHIPPED_SKILLS: frozenset[str] = frozenset({
    "code-review", "design-system", "hotwire", "rails-8",
    # Added deliberately when #360 shipped it. `quality-pass` is bundled in the rails-stack
    # plugin like the other four, so it is installed by users and its references must be
    # reachable from its own SKILL.md on the same terms.
    "quality-pass",
    # Moved out of `.claude/skills/` and shipped: nothing in either was about this marketplace.
    # `derived-artifacts` governs anything whose numbers come from elsewhere; `parallel-session-lane`
    # is the protocol for several agent sessions against one repo. Both are stack-neutral, so they
    # are installed by users and their references must be reachable on the same terms as the rest.
    "derived-artifacts", "parallel-session-lane",
})

# A path mention of a reference file, in either the code-span form (`references/x.md`) or as a
# markdown link target ([...](references/x.md)). Deliberately anchored on `references/` -- see
# "WHAT COUNTS AS ROUTING" above for why a bare filename is not enough.
REF_PATH_RE = re.compile(r"(?:\./)?references/([A-Za-z0-9._-]+\.md)")


class Unreadable(RuntimeError):
    """The skills tree did not yield what this check needs -- never a silent pass."""


@dataclass(frozen=True)
class Finding:
    rule: str
    skill: str
    detail: str

    def __str__(self) -> str:
        return f"  [{self.rule}] {self.skill}: {self.detail}"


def routed_names(skill_md: str) -> set[str]:
    """The reference filenames `SKILL.md` actually routes to."""
    return set(REF_PATH_RE.findall(skill_md))


def check_skill(skill_dir: Path) -> tuple[list[Finding], int]:
    """Findings for one skill, plus the number of reference files examined."""
    name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        # An error, not a skip: a skill directory with no SKILL.md is not a skill, and reporting it
        # as clean is the skip-as-pass failure this repo keeps paying for.
        raise Unreadable(f"{name}/: no SKILL.md")

    body = skill_md.read_text(encoding="utf-8")
    findings: list[Finding] = []

    line_count = len(body.splitlines())
    if line_count > MAX_SKILL_LINES:
        findings.append(Finding(
            "oversized-skill-body", name,
            f"SKILL.md is {line_count} lines, over the documented {MAX_SKILL_LINES}-line Level-2 "
            f"budget -- this body loads in full on every trigger. Move detail into references/",
        ))

    refs_dir = skill_dir / "references"
    present = {p.name for p in refs_dir.glob("*.md")} if refs_dir.is_dir() else set()
    routed = routed_names(body)

    for missing in sorted(present - routed):
        findings.append(Finding(
            "unrouted-reference", name,
            f"references/{missing} is never named by SKILL.md, so it is reachable only at depth 2 "
            f"(or not at all). Add it to the dispatch table",
        ))
    for dead in sorted(routed - present):
        findings.append(Finding(
            "dead-reference-link", name,
            f"SKILL.md routes to references/{dead}, which does not exist",
        ))

    return findings, len(present)


def run() -> int:
    try:
        if not SKILLS_DIR.is_dir():
            raise Unreadable(f"{SKILLS_DIR} is not a directory")
        skill_dirs = sorted(d for d in SKILLS_DIR.iterdir() if d.is_dir())
        if not skill_dirs:
            raise Unreadable(f"{SKILLS_DIR} contains no skill directories")

        # The scope pin, both directions. A skill added to the marketplace but not here would
        # otherwise be checked by nothing while the sweep still reported clean.
        found = {d.name for d in skill_dirs}
        if found != SHIPPED_SKILLS:
            unpinned = sorted(found - SHIPPED_SKILLS)
            vanished = sorted(SHIPPED_SKILLS - found)
            raise Unreadable(
                "skills/ no longer matches SHIPPED_SKILLS — "
                + (f"unpinned: {unpinned} " if unpinned else "")
                + (f"missing: {vanished} " if vanished else "")
                + "(add or remove it deliberately, with a reason)"
            )

        findings: list[Finding] = []
        refs_seen = 0
        for d in skill_dirs:
            f, n = check_skill(d)
            findings.extend(f)
            refs_seen += n

        # A lint that reports clean on input it never read is worse than no lint. If the layout
        # ever changes shape, this fails loudly instead of congratulating us on zero findings.
        if refs_seen == 0:
            raise Unreadable(
                f"examined {len(skill_dirs)} skill(s) but found no reference files at all -- "
                f"the references/ layout changed and this check is measuring nothing"
            )
    except (OSError, Unreadable) as exc:
        print(f"CANNOT CHECK: {exc}", file=sys.stderr)
        return 2

    for finding in findings:
        print(finding, file=sys.stderr)
    if findings:
        print(f"\n{len(findings)} finding(s) across {len(skill_dirs)} skills.", file=sys.stderr)
        return 1
    print(f"skill routing: {len(skill_dirs)} skills, {refs_seen} reference files, all routed "
          f"one level deep from their SKILL.md.")
    return 0


def selftest() -> int:
    import tempfile

    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    def build(tmp: Path, skill: str, body: str, refs: tuple[str, ...] = ()) -> Path:
        d = tmp / skill
        (d / "references").mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(body, encoding="utf-8")
        for r in refs:
            (d / "references" / r).write_text("# ref\n", encoding="utf-8")
        return d

    def rules(d: Path) -> list[str]:
        found, _ = check_skill(d)
        return [f.rule for f in found]

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # ---- unrouted-reference: FIRES ---------------------------------------------------------
        d = build(tmp, "fires", "# S\n\n`references/a.md` does the thing.\n", ("a.md", "b.md"))
        check("an unrouted reference is a finding",
              rules(d) == ["unrouted-reference"], f"got {rules(d)}")

        # ---- unrouted-reference: SILENT (the half that matters more) ---------------------------
        d = build(tmp, "silent-table", "# S\n\n| `references/a.md` | x |\n| `references/b.md` | y |\n",
                  ("a.md", "b.md"))
        check("a code-span dispatch table routes (rails-8 / hotwire form)", rules(d) == [], f"got {rules(d)}")

        d = build(tmp, "silent-link", "# S\n\nSee [a](references/a.md) and [b](./references/b.md).\n",
                  ("a.md", "b.md"))
        check("markdown links route, incl. a ./ prefix (design-system form)",
              rules(d) == [], f"got {rules(d)}")

        # THE PRECISION FIXTURE. A bare filename in prose is not routing -- this is the exact shape
        # that hid `coverage.md`, and a substring test would call this clean.
        d = build(tmp, "prose-only", "# S\n\nThe `coverage.md` file used to say something else.\n",
                  ("coverage.md",))
        check("a bare prose mention is NOT routing",
              rules(d) == ["unrouted-reference"], f"got {rules(d)}")

        # ---- dead-reference-link: FIRES and stays SILENT ---------------------------------------
        d = build(tmp, "dead", "# S\n\n`references/gone.md`\n", ())
        check("a dead reference link is a finding",
              rules(d) == ["dead-reference-link"], f"got {rules(d)}")
        d = build(tmp, "alive", "# S\n\n`references/a.md`\n", ("a.md",))
        check("an existing reference link is silent", rules(d) == [], f"got {rules(d)}")

        # ---- oversized-skill-body: FIRES, and the BOUNDARY stays silent ------------------------
        d = build(tmp, "big", "\n".join(["x"] * (MAX_SKILL_LINES + 1)), ())
        check("a body over the budget is a finding",
              rules(d) == ["oversized-skill-body"], f"got {rules(d)}")
        d = build(tmp, "at-budget", "\n".join(["x"] * MAX_SKILL_LINES), ())
        check("a body exactly AT the budget is silent (off-by-one)",
              rules(d) == [], f"got {rules(d)}")

        # ---- a skill with no references/ at all is fine (the code-review case) -----------------
        d = tmp / "no-refs"
        d.mkdir()
        (d / "SKILL.md").write_text("# S\n\nNo references.\n", encoding="utf-8")
        check("a skill with no references/ directory is silent", rules(d) == [], f"got {rules(d)}")

        # ---- ambiguity is an ERROR, never a skip -----------------------------------------------
        checks += 1
        empty = tmp / "empty-skill"
        empty.mkdir()
        try:
            check_skill(empty)
            failures.append("a skill directory with no SKILL.md was skipped instead of raising")
        except Unreadable:
            pass

        # A finding must survive being MIXED with clean input. Checking one defect in isolation
        # would pass even if the rule only ever reported the first file it looked at.
        d = build(tmp, "mixed", "# S\n\n`references/a.md` and `references/c.md`\n",
                  ("a.md", "b.md", "c.md"))
        found, n_refs = check_skill(d)
        check("one unrouted file among routed ones is still found",
              [f.rule for f in found] == ["unrouted-reference"] and "b.md" in found[0].detail,
              f"got {[str(f) for f in found]}")
        check("every reference file is counted, routed or not", n_refs == 3, f"got {n_refs}")

        # Several defects at once are all reported -- a rule that returns after the first finding
        # turns a sweep into a sampling.
        d = build(tmp, "many", "# S\n\n`references/gone.md`\n", ("x.md", "y.md"))
        check("findings accumulate rather than short-circuiting",
              sorted(rules(d)) == ["dead-reference-link",
                                   "unrouted-reference", "unrouted-reference"],
              f"got {sorted(rules(d))}")

    # ---- the scope pin itself (its enforcement against the real tree is in run(), by design) ---
    # NOT an exact count. The first version asserted `== 4`, which made the number a second
    # source of truth for the frozenset ten lines above it — so shipping a fifth skill
    # (`quality-pass`, #360) failed this selftest even though the pin had been updated
    # correctly and the gate itself was green. What this fixture is actually for is catching
    # an EMPTIED scope, which would make the gate examine nothing while reporting clean; the
    # real-tree reconciliation lives in run(), by design.
    check("SHIPPED_SKILLS is populated", len(SHIPPED_SKILLS) > 0, f"got {sorted(SHIPPED_SKILLS)}")
    check("the eval control is not in scope", "rails-generic" not in SHIPPED_SKILLS)

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {checks} checks:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"check_skill_routing selftest: {checks} checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Assert every shipped skill routes to all of its reference files.")
    ap.add_argument("--selftest", action="store_true",
                    help="prove each rule fires AND stays silent")
    args = ap.parse_args(argv)
    return selftest() if args.selftest else run()


if __name__ == "__main__":
    sys.exit(main())
