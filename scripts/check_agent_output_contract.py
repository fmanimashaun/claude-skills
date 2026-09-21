#!/usr/bin/env python3
"""Every shipped agent must state what it returns to its parent (#1086).

Run:  python3 scripts/check_agent_output_contract.py
      python3 scripts/check_agent_output_contract.py --selftest

WHY THIS EXISTS. An agent's final message lands in the PARENT conversation and stays there for the
rest of the session. That is not a one-off cost like the agent's own turns -- it is a permanent tax
on every subsequent request the parent makes. A verbose agent is paid for once and charged forever.

Measured the first time anyone looked: **29 shipped agents, and 2 declared any output contract.**
The two that did are the two this check is built from, because both already worked:

  * `rails-flow/claim-verifier` returns a BOUNDED STRUCTURED VERDICT -- a fixed shape, one line per
    finding with its evidence, ending in a tally. Every line is actionable; nothing is restated.
  * `qa-flow/functional-tester` WRITES ARTIFACTS AND RETURNS A PATH -- report, CSV and screenshots
    go to `qa/manual-tests/`, and the parent reads them only if it needs to.

NOT THE SAME QUESTION AS MODEL TIER. `reference/model-tiers.md` settles which model an agent runs
on, deliberately and with citations (#127), and this check does not reopen it. That governs what the
agent's own turns cost. This governs what its ANSWER costs the parent, which no tier affects.

WHAT IT CHECKS, AND THE BOUNDARY IS DELIBERATE. It requires a declared `## Output` section that
either names a file the agent writes or is itself short enough to be a bounded shape rather than a
wandering description. **It does not check what the agent actually emits at runtime** -- that
depends on the model and the input, and a check claiming to verify it would be a gate that cannot
fail. The declaration is exact, it is what a reader of the agent sees, and an agent that has not
been made to state its contract is one that has not thought about it.

WHY `## Output` AND NOT ANY MENTION OF THE WORD. The first draft matched a heading CONTAINING
"output" and counted `design-flow/design-critic`'s *"Ranking `/design-flow:variants` output"* as a
contract -- a heading about ranking someone else's output, not about what the agent returns. That
made the baseline read 3 when it was 2. The rule anchors on the heading being Output.

Stdlib only, no network. Exit 0 clean, 1 findings, 2 nothing examined.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The heading must BE Output, not merely contain the word -- see the docstring.
OUTPUT_HEADING = re.compile(r"^##+\s+Output\b.*$", re.M)

# An artifact path the agent writes, in backticks. This is contract 2, and it is the one that
# actually removes the cost rather than trimming it.
ARTIFACT = re.compile(r"`[^`\n]*\.(?:md|csv|json|html|png|txt)`")

# A bounded shape is short. 2000 characters is roughly a fenced example plus its rules -- long
# enough for `claim-verifier`'s verdict block, too short for a section that wanders.
BOUNDED_CHARS = 2000


def section_body(text: str) -> str | None:
    """The `## Output` section's body, or None when there is no such heading."""
    m = OUTPUT_HEADING.search(text)
    if not m:
        return None
    rest = text[m.end():]
    # Stop at the next heading of the SAME OR SHALLOWER depth; a `###` subsection belongs to it.
    depth = len(m.group(0)) - len(m.group(0).lstrip("#")) if m.group(0).startswith("#") else 2
    depth = len(re.match(r"#+", m.group(0)).group(0))
    nxt = re.search(rf"^#{{1,{depth}}}\s+", rest, re.M)
    return rest[: nxt.start()] if nxt else rest


def agents(root: Path = REPO) -> list[Path]:
    return sorted(root.glob("plugins/*/agents/*.md"))


def check(root: Path = REPO) -> tuple[list[str], int]:
    findings: list[str] = []
    examined = 0
    for path in agents(root):
        examined += 1
        rel = path.relative_to(root)
        body = section_body(path.read_text(encoding="utf-8", errors="replace"))
        if body is None:
            findings.append(
                f"{rel}: no `## Output` section — nothing states what this agent returns, so its "
                f"answer lands in the parent conversation at whatever length the model chooses and "
                f"stays there for the rest of the session. Declare a bounded shape, or name the "
                f"file it writes and return the path.")
            continue
        if ARTIFACT.search(body):
            continue                     # contract 2: it writes artifacts and returns where
        if len(body) <= BOUNDED_CHARS:
            continue                     # contract 1: a bounded shape
        findings.append(
            f"{rel}: `## Output` is {len(body)} characters and names no artifact file — it "
            f"describes rather than bounds. Either give it a fixed shape the parent can act on "
            f"line by line, or write the detail to a file and return the path.")
    return findings, examined


def _selftest() -> int:
    ok, bad = 0, []

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    import shutil
    import tempfile
    root = Path(tempfile.mkdtemp(prefix="agent-output-"))
    try:
        d = root / "plugins/x/agents"
        d.mkdir(parents=True)

        # MUST FAIL: the state 27 of 29 shipped agents were in.
        (d / "none.md").write_text("---\nname: none\n---\n\n## Role\n\nDo a thing.\n",
                                   encoding="utf-8")
        # MUST PASS, contract 1: a bounded verdict, lifted from claim-verifier's real shape.
        (d / "bounded.md").write_text(
            "---\nname: bounded\n---\n\n## Output\n\n```\nCONFIRMED  \"x\"\n            evidence\n"
            "2 of 4 claims stand.\n```\n", encoding="utf-8")
        # MUST PASS, contract 2: it writes an artifact and returns the path.
        # DELIBERATELY LONGER THAN `BOUNDED_CHARS`, so it can pass ONLY through the artifact
        # branch. A first draft made it short; it then satisfied the bounded rule too, and the
        # mutation deleting the artifact branch SURVIVED because the two contracts overlapped.
        (d / "artifact.md").write_text(
            "---\nname: artifact\n---\n\n## Output\n\nWrite the report to "
            "`qa/manual-tests/<date>.md` and return that path with the verdict.\n"
            + ("Detail on the column meanings and the triage rules. " * 60),
            encoding="utf-8")
        # MUST FAIL: an Output section that wanders. Long, and names no file.
        (d / "wandering.md").write_text(
            "---\nname: wandering\n---\n\n## Output\n\n" + ("Describe everything you found. " * 120),
            encoding="utf-8")
        # THE FALSE POSITIVE THAT MADE THE BASELINE READ 3 INSTEAD OF 2: a heading that merely
        # CONTAINS the word, about ranking another command's output.
        (d / "ranking.md").write_text(
            "---\nname: ranking\n---\n\n## Ranking `/design-flow:variants` output\n\nRank them.\n",
            encoding="utf-8")

        findings, examined = check(root)
        expect("every agent file is examined", examined == 5)
        expect("an agent with no Output section is reported",
               any("none.md" in f for f in findings))
        expect("a bounded verdict is accepted",
               not any("bounded.md" in f for f in findings))
        expect("an agent that writes an artifact and returns a path is accepted",
               not any("artifact.md" in f for f in findings))
        expect("an Output section that wanders and names no file is reported",
               any("wandering.md" in f for f in findings))
        # THE ANCHORING CASE. Without it, "has an Output section" is satisfied by any heading with
        # the word in it, which is how the first baseline was wrong.
        expect("a heading merely CONTAINING 'output' is not a contract",
               any("ranking.md" in f and "no `## Output` section" in f for f in findings))
        expect("exactly three findings — the rule is narrow, not enthusiastic", len(findings) == 3)

        empty = Path(tempfile.mkdtemp(prefix="agent-output-empty-"))
        try:
            f2, e2 = check(empty)
            expect("a tree with no agents reports nothing AND says it examined nothing",
                   not f2 and e2 == 0)
        finally:
            shutil.rmtree(empty, ignore_errors=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    if bad:
        print(f"ran {ok + len(bad)} assertion(s)\n\n{len(bad)} FAILED:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print(f"ran {ok} assertion(s)")
    print("a bounded shape and an artifact path both pass; a missing or wandering section does not")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()

    findings, examined = check()
    if examined == 0:
        # NOT a pass. Zero findings over zero agents reads exactly like a compliant tree.
        print("NOT APPLICABLE: no plugins/*/agents/*.md — this check examined nothing.")
        return 2
    for f in findings:
        print(f"  {f}")
    print(f"\n{examined} shipped agent(s) checked for an output contract; {len(findings)} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
