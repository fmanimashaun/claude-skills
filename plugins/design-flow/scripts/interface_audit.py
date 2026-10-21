#!/usr/bin/env python3
"""Judge interface snapshots against the framework's rules, as findings (#2221).

Run:  python3 interface_audit.py snapshots.json [--out findings.json]
      python3 interface_audit.py --selftest

The browser collector (`interface_collector.js`, evaluated per page) MEASURES; this decides. It
emits a findings document in the `audit_findings.py` contract, so a finding's authority comes from
the rule's basis and is never written here. Rules judged in this first slice, by id in
`design-system/references/architecture.md`:

  A1  a page has at most one non-hidden `main` landmark.
  A2  a skip link is first in the body (to a target that exists) and the shell keeps a live region
      for toasts outside `main`.
  A4  the link to the current page in the primary navigation has `aria-current="page"`.

A page with a non-2xx status is not judged and is counted under `skipped`, never as clean; an
empty snapshot list is refused, because a report over no pages says nothing. A4 is judged only on
a page that the primary navigation links to: a page absent from the nav has nothing to mark.

Exit: 0 no findings · 1 findings · 2 the snapshots are unusable.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCHEMA = "design-flow/interface-snapshot/1"


class Unusable(Exception):
    pass


def _finding(rule: str, url: str, count: int, ref: str, message: str) -> dict:
    return {"rule": rule, "screen": url, "instances": count, "evidence": {"kind": "measured", "ref": ref}, "message": message}


def judge_page(snap: dict) -> list[dict]:
    url = snap["url"]
    out: list[dict] = []
    mains = snap["mains"]["visible"]
    if mains > 1:
        out.append(_finding("A1", url, mains, f"{mains} visible main landmarks at {url}", f"{mains} visible `main` landmarks"))
    skip = snap["skip_link"]
    if not skip["present"]:
        out.append(_finding("A2", url, 1, f"first focusable element is {skip['first_focusable']!r} at {url}",
                            "the first focusable element is not a skip link"))
    elif not skip["target_exists"]:
        out.append(_finding("A2", url, 1, f"skip link {skip['href']} has no target at {url}", "the skip link points at nothing"))
    if snap["live_regions"] < 1:
        out.append(_finding("A2", url, 1, f"no live region outside main at {url}", "the shell has no live region for toasts"))
    links = [l for l in snap["primary_nav"]["links"] if l["to_this_page"]]
    if links and not any(l["current"] for l in links):
        out.append(_finding("A4", url, 1, f"nav link to this page without aria-current at {url}",
                            "the primary navigation link to this page is not marked as current"))
    return out


def judge(doc: object) -> dict:
    if not isinstance(doc, list) or not doc:
        raise Unusable("the snapshots file must be a non-empty list: a report over no pages says nothing")
    findings: list[dict] = []
    judged = skipped = 0
    for i, snap in enumerate(doc, 1):
        if not isinstance(snap, dict) or snap.get("schema") != SCHEMA:
            raise Unusable(f"snapshot {i}: not a {SCHEMA} document")
        status = snap.get("status")
        if not isinstance(status, int) or not 200 <= status < 300:
            skipped += 1
            continue
        judged += 1
        findings += judge_page(snap)
    if not judged:
        raise Unusable(f"no snapshot had a 2xx status ({skipped} skipped): nothing was judged")
    return {"audit": "interface audit: landmarks, skip link, current navigation", "screens_examined": judged,
            "skipped_non_2xx": skipped, "findings": findings}


def selftest() -> int:
    def snap(**over):
        s = {"schema": SCHEMA, "url": "/orders", "status": 200, "mains": {"visible": 1},
             "skip_link": {"present": True, "first_focusable": "a", "href": "#main", "target_exists": True},
             "live_regions": 1, "primary_nav": {"present": True, "links": [
                 {"text": "Orders", "href": "/orders", "to_this_page": True, "current": True},
                 {"text": "Home", "href": "/", "to_this_page": False, "current": False}]}, "h1_count": 1}
        s.update(over)
        return s

    def rules(doc):
        return [f["rule"] for f in judge([doc])["findings"]]

    cases = [
        ("a conforming page has no findings", rules(snap()) == []),
        ("two visible mains is an A1 finding with the count", judge([snap(mains={"visible": 2})])["findings"][0]["instances"] == 2),
        ("zero mains is not an A1 finding (the rule says at most one)", rules(snap(mains={"visible": 0})) == []),
        ("no skip link is an A2 finding", [f["message"] for f in judge([snap(skip_link={"present": False, "first_focusable": "button", "href": None, "target_exists": False})])["findings"]]
         == ["the first focusable element is not a skip link"]),
        ("a skip link to a missing target is an A2 finding", rules(snap(skip_link={"present": True, "first_focusable": "a", "href": "#x", "target_exists": False})) == ["A2"]),
        ("no live region is an A2 finding", rules(snap(live_regions=0)) == ["A2"]),
        ("a nav link to this page without aria-current is an A4 finding", rules(snap(primary_nav={"present": True, "links": [
            {"text": "Orders", "href": "/orders", "to_this_page": True, "current": False}]})) == ["A4"]),
        ("a page the nav does not link to has no A4 finding", rules(snap(primary_nav={"present": True, "links": [
            {"text": "Home", "href": "/", "to_this_page": False, "current": False}]})) == []),
        ("a page with no nav has no A4 finding", rules(snap(primary_nav={"present": False, "links": []})) == []),
        ("a non-2xx page is skipped and counted, not judged",
         judge([snap(), snap(status=404, mains={"visible": 3})])["skipped_non_2xx"] == 1
         and judge([snap(), snap(status=404, mains={"visible": 3})])["findings"] == []),
    ]
    for label, doc, why in (
        ("an empty list is unusable", [], "non-empty"),
        ("a wrong schema is unusable", [{"schema": "x"}], "not a"),
        ("a list with no 2xx page is unusable", [snap(status=500)], "nothing was judged"),
        ("a missing status is not 2xx", [snap(status=None)], "nothing was judged"),
    ):
        try:
            judge(doc)
            cases.append((label, False))
        except Unusable as exc:
            cases.append((label, why in str(exc)))
    # The judge's output satisfies the findings contract.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import audit_findings as af
    out = judge([snap(mains={"visible": 2}), snap(url="/b", skip_link={"present": False, "first_focusable": "a", "href": None, "target_exists": False})])
    cases.append(("the judge's output passes the findings contract", af.validate(out, af.load_registry(), Path(".")) == []))
    bad = 0
    for label, ok in cases:
        bad += not ok
        print(f"  [{'ok' if ok else 'FAIL'}] {label}")
    print(f"interface_audit selftest: {len(cases) - bad}/{len(cases)}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("snapshots", nargs="?")
    ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.snapshots:
        ap.print_help()
        return 2
    try:
        result = judge(json.loads(Path(a.snapshots).read_text(encoding="utf-8")))
    except (Unusable, OSError, ValueError) as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(result, indent=1)
    Path(a.out).write_text(text + "\n", encoding="utf-8") if a.out else print(text)
    print(f"{result['screens_examined']} screen(s) judged, {result['skipped_non_2xx']} skipped, {len(result['findings'])} finding(s)", file=sys.stderr)
    return 1 if result["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
