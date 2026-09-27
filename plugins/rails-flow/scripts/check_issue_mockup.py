#!/usr/bin/env python3
"""Every issue says whether it changes what a user sees, and if it does, links its mock-up (#1376).

Run:  check_issue_mockup.py --body-file BODY.md       # one issue body, before or after filing
      check_issue_mockup.py --issue 42                # read it with `gh issue view`
      check_issue_mockup.py --open                    # every open issue (`gh`, bounded)
      check_issue_mockup.py --selftest

Exit: 0 declared (a mock-up link, or "no visible change") · 1 missing or empty · 2 cannot read.

WHY. The owner's rule: an issue whose resolution changes what a user sees (a feature, an
enhancement, or a bug whose fix alters a screen) carries a clickable mock-up when it is FILED, and
every other issue says so explicitly. The trigger is UI impact, not the label.

A TEMPLATE ALONE CANNOT CARRY THIS. GitHub forms apply only in the web UI; an agent files with
`gh issue create`, which skips the template (the same reason setup-flow declares labels, #1311).
So the section is checked in the BODY, whichever way it was written:
  * a form renders it as `### Mock-up` followed by the answer, and `_No response_` when left blank;
  * an agent writes `## Mock-up` (any heading level) or a `Mock-up:` line.
The answer is DECLARED when it holds an https link or a repo path to a mock-up, or says
"no visible change". Anything else, including a blank, a "TBD" or a bare "yes", is missing: an
undecided issue is not ready.

WHAT IT DOES NOT: decide whether "no visible change" is true. That is triage's judgement, and
check_mockup_gate.py re-checks the real diff before merge, so a wrong "no visible change" is caught
at the latest there.

Stdlib only. `--issue` and `--open` need `gh`.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

HEADING = re.compile(r"^\s{0,3}#{1,6}\s*mock-?up\b[^\n]*$", re.I | re.M)
INLINE = re.compile(r"^\s*(?:[-*]\s*)?\**mock-?up\**\s*:\s*(.+)$", re.I | re.M)
NEXT_HEADING = re.compile(r"^\s{0,3}#{1,6}\s", re.M)
LINK = re.compile(r"https://\S+|(?:^|\s)[\w./-]+\.(?:html?|png|jpe?g|webp|pdf|md)\b", re.I)
NO_CHANGE = re.compile(r"\bno visible change\b", re.I)


def answer(body: str) -> str | None:
    """The text under the Mock-up heading, or on the `Mock-up:` line. None when there is no section."""
    m = HEADING.search(body)
    if m:
        rest = body[m.end():]
        nxt = NEXT_HEADING.search(rest)
        return (rest[: nxt.start()] if nxt else rest).strip()
    m = INLINE.search(body)
    return m.group(1).strip() if m else None


def verdict(body: str) -> tuple[bool, str]:
    text = answer(body)
    if text is None:
        return False, "no Mock-up section: add one with a mock-up link, or say \"no visible change\""
    if not text or text == "_No response_":
        return False, "the Mock-up section is empty"
    if NO_CHANGE.search(text):
        return True, "declared: no visible change"
    if LINK.search(text):
        return True, "declared: mock-up linked"
    return False, f"the Mock-up section neither links a mock-up nor says \"no visible change\": {text[:60]!r}"


def gh_json(*args: str) -> object:
    out = subprocess.run(("gh",) + args, capture_output=True, text=True)
    if out.returncode != 0:
        raise OSError(out.stderr.strip() or "gh failed")
    return json.loads(out.stdout)


# --------------------------------------------------------------------------- selftest

def selftest() -> int:
    failures: list[str] = []

    def check_that(label: str, ok: bool, detail: object = "") -> None:
        if not ok:
            failures.append(f"{label}{(' — ' + str(detail)) if detail != '' else ''}")

    form = "### What\n\nA bell.\n\n### Mock-up\n\n{}\n\n### Acceptance\n\n- AC-1 …\n"
    cases_ok = {
        "a form answer with an https link": form.format("https://example.com/mock/bell"),
        "a form answer saying no visible change": form.format("No visible change: the job only retries."),
        "an agent-written section with a committed mock-up file": "## Mock-up\ndocs/product/mockups/bell.html\n",
        "a `Mock-up:` line with a link": "Summary.\n\nMock-up: https://example.com/m\n",
        "a `Mockup` heading, spelled without the hyphen": "## Mockup\n\nhttps://example.com/m\n",
    }
    for label, body in cases_ok.items():
        ok, why = verdict(body)
        check_that(f"CONTROL: {label} is declared", ok, why)

    ok, why = verdict("### What\n\nA bell.\n")
    check_that("an issue with no Mock-up section is missing", not ok and "no Mock-up section" in why, why)
    ok, why = verdict(form.format("_No response_"))
    check_that("a form left blank (_No response_) is missing", not ok and "empty" in why, why)
    ok, why = verdict(form.format("TBD"))
    check_that("\"TBD\" is not a declaration", not ok and "neither" in why, why)
    ok, why = verdict(form.format("yes"))
    check_that("a bare \"yes\" is not a declaration", not ok and "neither" in why, why)
    # The section ends at the next heading, so a link further down the issue does not count.
    ok, why = verdict("### Mock-up\n\nTBD\n\n### Notes\n\nsee https://example.com/other\n")
    check_that("a link under a LATER heading does not satisfy the Mock-up section", not ok, why)
    # And prose that mentions mock-ups is not the section.
    ok, why = verdict("We should make a mock-up for this someday.\n")
    check_that("prose that mentions a mock-up is not a section", not ok and "no Mock-up section" in why, why)

    for f in failures:
        print(f"selftest FAIL: {f}")
    print(f"check_issue_mockup selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_issue_mockup.py", description=__doc__.splitlines()[0])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--body-file")
    src.add_argument("--issue", type=int)
    src.add_argument("--open", action="store_true", help="every open issue, bounded to 200")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        if a.body_file:
            items = [("body", open(a.body_file, encoding="utf-8").read())]
        elif a.issue:
            items = [(f"#{a.issue}", gh_json("issue", "view", str(a.issue), "--json", "body")["body"])]
        elif a.open:
            rows = gh_json("issue", "list", "--state", "open", "--limit", "200", "--json", "number,body")
            items = [(f"#{r['number']}", r["body"] or "") for r in rows]
        else:
            ap.error("one of --body-file, --issue, --open is required")
    except (OSError, ValueError, KeyError) as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2
    missing = 0
    for name, body in items:
        ok, why = verdict(body)
        missing += not ok
        print(f"{'ok     ' if ok else 'MISSING'} {name}: {why}")
    print(f"{len(items) - missing}/{len(items)} issue(s) declare their mock-up or no visible change")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
