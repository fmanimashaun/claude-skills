#!/usr/bin/env python3
"""Judge a screen against the template its mock-up record declares, and refuse a screen that declares none. (#2251, slice 3 of #2221)

Run:  python3 interface_templates.py --selftest        (the judge is called by `interface_audit.py --screens screens.json`)

WHY. The framework's template rules (A29-A58, from the GOV.UK patterns) apply to a PAGE KIND: a back link belongs on a question page, a results count on a
search-results page. Applying them to every page would report a dashboard for lacking a "Continue" button. So a rule is judged only for a screen whose
mock-up record (`docs/product/mockups/<slug>.md`, #2226) declares that `Template:`, and a screen with no record, or a record with no `Template:`, `States:`
or `Nav:` line, is itself a finding (A10: a screen is one of the nine templates), with a record PROPOSED for a person to review.

THE SCREEN-TO-RECORD LINK IS DATA THE CALLER SUPPLIES. A record has no route (its `Story:` is a file), so `screens.json` is a list of
`{"url": "/orders", "screen": "Order list"}`, where `screen` names a record's `Screen:` line (null for none). This reads the records itself, refuses a
`screen` no record has, and refuses two records with one `Screen:`. A URL in no entry is undeclared, never assumed.

WHAT IS MEASURED. The browser collector records FACTS in `structure`; this decides. Seven rules, each only for the template that owns it:
  multi-step      A31 a back link at the top (present, and before the page's h1)
                  A34 the forward button is labelled "Continue", not "Next" (a finding only for "Next": the other labels the rule does not name are not asserted)
  search-results  A53 a results count; pagination when the count is above ten; and, with no results, a no-results message
                  A54 the count sits above the list, and names a search term when the URL carries one
                  A55 with no results the message says so plainly and offers hints
                  A56 a sort control, when there is one, sits above the results
                  A57 no more than ten results on a page
NOT MEASURED, and named in the report with their reasons (`audit_findings.NOT_MEASURED_TEMPLATE`): A29, A30, A33 (one question per page, a statement heading, a
heading no other page of the flow shares: they need a declared flow or a judgement), A32 (the back link's state: it needs a driven journey), A35-A42
(check-answers and confirmation pages) and A43-A52 (task lists): the record's vocabulary has no page kind for either, and A58 (a partial update needs a driver).

Exit codes are `interface_audit.py`'s. Stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mockup_records import RECORD_DIR, SHELL_RECORD, read_fields  # noqa: E402  (vendored, byte-identical to rails-flow's: the one reader of a record)

TEMPLATE_RULES = {"multi-step": ("A31", "A34"), "search-results": ("A53", "A54", "A55", "A56", "A57")}
RULES = ("A10", *TEMPLATE_RULES["multi-step"], *TEMPLATE_RULES["search-results"])
DESIGN_LINES = ("Template", "States", "Nav")
PAGE_SIZE = 10


class Unusable(Exception):
    pass


def finding(rule: str, url: str, ref: str, message: str, proposal: str | None = None) -> dict:
    out = {"rule": rule, "screen": url, "instances": 1, "evidence": {"kind": "measured", "ref": ref}, "message": message}
    if proposal:
        out["proposal"] = proposal
    return out


# ---------------------------------------------------------------------------------------------
# The records
# ---------------------------------------------------------------------------------------------

def load_records(root: Path) -> dict[str, dict]:
    """`{Screen: {template, fields, path}}` for every record under docs/product/mockups/ that names a `Screen:` (the shell record is not a screen)."""
    base = root / RECORD_DIR
    records: dict[str, dict] = {}
    for path in sorted(base.glob("*.md")) if base.is_dir() else []:
        if path.as_posix().endswith(SHELL_RECORD):
            continue
        fields = read_fields(path)
        name = fields.get("Screen")
        if not name:
            continue
        if name in records:
            raise Unusable(f"two mock-up records name the screen `{name}` ({records[name]['path']} and {path.name}): a screen name is unique")
        template = re.split(r"[:\s]", fields.get("Template", "").strip(), maxsplit=1)[0] if fields.get("Template") else ""
        records[name] = {"template": template, "fields": fields, "path": f"{RECORD_DIR}{path.name}"}
    return records


def load_screens(doc: object, snapshots: list[dict], records: dict[str, dict]) -> dict[str, str | None]:
    """`{url: screen name or None}` from screens.json, refusing a document that cannot be trusted."""
    if not isinstance(doc, list):
        raise Unusable("the screens file must be a list of {url, screen}")
    out: dict[str, str | None] = {}
    for i, entry in enumerate(doc, 1):
        if not isinstance(entry, dict) or not isinstance(entry.get("url"), str) or not entry["url"]:
            raise Unusable(f"screens entry {i}: needs a `url`")
        screen = entry.get("screen")
        if screen is not None and (not isinstance(screen, str) or not screen.strip()):
            raise Unusable(f"screens entry {i} ({entry['url']}): `screen` is a record's `Screen:` name, or null")
        if entry["url"] in out:
            raise Unusable(f"screens entry {i}: the url {entry['url']} appears twice")
        if screen is not None and screen not in records:
            raise Unusable(f"screens entry {i} ({entry['url']}): no mock-up record has `Screen: {screen}`: a screen is mapped to a record that exists, or to null")
        out[entry["url"]] = screen
    return out


# ---------------------------------------------------------------------------------------------
# The structure rules
# ---------------------------------------------------------------------------------------------

def _terms(structure: dict) -> list[str]:
    return [t.lower() for t in (structure.get("query", {}).get("terms") or []) if isinstance(t, str) and t.strip()]


def judge_multi_step(url: str, s: dict) -> list[dict]:
    out = []
    back = s["back_link"]
    if not back["present"]:
        out.append(finding("A31", url, f"no back link on {url}", "a question page has no back link"))
    elif not back["before_h1"]:
        out.append(finding("A31", url, f"back link {back['text']!r} after the h1 at {url}", "the back link is not at the top of the page: it comes after the heading"))
    fwd = s["forward_button"]
    if fwd["present"] and (fwd["label"] or "").strip().lower() == "next":
        out.append(finding("A34", url, f"forward button labelled {fwd['label']!r} at {url}", 'the forward button is labelled "Next", not "Continue"'))
    return out


def judge_search_results(url: str, s: dict) -> list[dict]:
    out = []
    r = s["results"]
    items, value = r["list_items"], r["count_value"]
    if r["count_text"] is None:
        out.append(finding("A53", url, f"no results count on {url}", "a search-results page shows no results count"))
    elif r["count_before_list"] is False:
        out.append(finding("A54", url, f"count {r['count_text']!r} below the list at {url}", "the results count is not above the list"))
    terms = _terms(s)
    if r["count_text"] is not None and terms and not any(t in r["count_text"].lower() for t in terms):
        out.append(finding("A54", url, f"count {r['count_text']!r}, search terms {terms} at {url}", "the results count does not name the search terms"))
    if isinstance(value, int) and value > PAGE_SIZE and not r["pagination"]:
        out.append(finding("A53", url, f"{value} results, no pagination at {url}", f"{value} results and no pagination"))
    if items > PAGE_SIZE:
        out.append(finding("A57", url, f"{items} results on one page at {url}", f"{items} results on one page: results paginate ten to a page"))
    if items == 0:
        if r["no_results_text"] is None:
            out.append(finding("A53", url, f"no results and no message at {url}", "no results, and no no-results message"))
        elif not r["no_results_hints"]:
            out.append(finding("A55", url, f"no-results text {r['no_results_text']!r} with no hints at {url}", "the no-results message offers no hints"))
    sort = r["sort_control"]
    if sort["present"] and sort["before_list"] is False:
        out.append(finding("A56", url, f"sort control below the list at {url}", "the sort control is not above the results"))
    return out


JUDGES = {"multi-step": judge_multi_step, "search-results": judge_search_results}


def validate_structure(url: str, s: object, template: str) -> None:
    """Refuse a structure block that cannot be judged (a missing fact is not a pass)."""
    def need(cond: bool, what: str) -> None:
        if not cond:
            raise Unusable(f"snapshot {url}: `structure` {what}")
    need(isinstance(s, dict), "is missing: the collector records it, and a template row is never judged without it")
    if template == "multi-step":
        b, f = s.get("back_link"), s.get("forward_button")
        need(isinstance(b, dict) and isinstance(b.get("present"), bool) and isinstance(b.get("before_h1"), bool), "needs back_link {present, before_h1}")
        need(isinstance(f, dict) and isinstance(f.get("present"), bool), "needs forward_button {present, label}")
    else:
        r = s.get("results")
        need(isinstance(r, dict) and isinstance(r.get("list_items"), int) and not isinstance(r["list_items"], bool) and r["list_items"] >= 0,
             "needs results.list_items (a whole number)")
        need("count_text" in r and "count_value" in r and "count_before_list" in r and "pagination" in r and "no_results_text" in r
             and "no_results_hints" in r and isinstance(r.get("sort_control"), dict) and "present" in r["sort_control"] and "before_list" in r["sort_control"],
             "needs the results facts (count_text, count_value, count_before_list, pagination, no_results_text, no_results_hints, sort_control)")


# ---------------------------------------------------------------------------------------------
# The undeclared screen
# ---------------------------------------------------------------------------------------------

def propose(snap: dict) -> tuple[str, str]:
    """A Template proposed from structure, and why. A proposal for a person to review, never a verdict on which template the screen should be."""
    s = snap.get("structure") or {}
    r = s.get("results") or {}
    if r.get("count_text") is not None and (r.get("list_items") or 0) >= 0 and r.get("list_items", 0) > 0:
        return "search-results", "it shows a results count above a list of results"
    if (s.get("back_link") or {}).get("present") and (s.get("forward_button") or {}).get("present"):
        return "multi-step", "it has a back link and a forward button"
    return "", "nothing in its structure says which of the nine templates it is"


def undeclared(snap: dict, screen: str | None, record: dict | None) -> dict | None:
    url = snap["url"]
    if record is None:
        why = "no mock-up record is named for this screen" + (f" (`{screen}` has none)" if screen else "")
        missing = list(DESIGN_LINES)
    else:
        missing = [k for k in DESIGN_LINES if not record["fields"].get(k)]
        if not missing:
            return None
        why = f"its mock-up record {record['path']} has no " + ", ".join(f"`{m}:`" for m in missing) + (" line" if len(missing) == 1 else " lines")
    template, reason = propose(snap)
    title = (snap.get("title") or url).strip()
    proposed = (f"propose a record `{RECORD_DIR}<slug>.md` for this screen, for a person to review (a proposal, not a verdict): "
                f"`Screen: {title}`; `Template: {template or '<one of the nine; ' + reason + '>'}`"
                + (f" ({reason})" if template else "") + "; `Nav: <level N under <parent>>`; `States: <each state designed, or n/a with a reason>`")
    return finding("A10", url, f"{url}: {why}", f"the screen is undeclared: {why}", proposed)


# ---------------------------------------------------------------------------------------------
# The entry point `interface_audit.judge` calls
# ---------------------------------------------------------------------------------------------

def judge_templates(snapshots: list[dict], screens_doc: object, root: Path) -> tuple[list[dict], dict[str, int], list[str]]:
    """`(findings, audited, unverified)` for the 2xx snapshots. A rule is audited over the screens that declare the template that owns it."""
    records = load_records(root)
    screens = load_screens(screens_doc, snapshots, records)
    findings: list[dict] = []
    audited: dict[str, int] = {}
    unverified: list[str] = []
    for snap in snapshots:
        url = snap["url"]
        screen = screens.get(url)
        record = records.get(screen) if screen else None
        audited["A10"] = audited.get("A10", 0) + 1
        gap = undeclared(snap, screen, record)
        if gap:
            findings.append(gap)
        template = record["template"] if record else ""
        if template not in JUDGES:
            continue
        try:
            validate_structure(url, snap.get("structure"), template)
        except Unusable as err:
            unverified.append(f"{url}: {err}")
            continue
        findings += JUDGES[template](url, snap["structure"])
        for rule in TEMPLATE_RULES[template]:
            audited[rule] = audited.get(rule, 0) + 1
    return findings, audited, unverified


# ---------------------------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------------------------

def selftest() -> int:
    import copy
    import tempfile

    cases: list[tuple[str, bool]] = []

    def check(label: str, ok: bool) -> None:
        cases.append((label, bool(ok)))

    def record(root: Path, slug: str, screen: str, **lines: str) -> None:
        d = root / RECORD_DIR
        d.mkdir(parents=True, exist_ok=True)
        body = [f"Screen: {screen}"] + [f"{k}: {v}" for k, v in lines.items()]
        (d / f"{slug}.md").write_text("\n".join(body) + "\n", encoding="utf-8")

    def snap(url="/s", **structure) -> dict:
        return {"url": url, "title": "A screen", "status": 200, "structure": structure}

    GOOD_STEP = {"back_link": {"present": True, "before_h1": True, "text": "Back"}, "forward_button": {"present": True, "label": "Continue"}}

    def results(**over) -> dict:
        r = {"count_text": "12 results for \"cats\"", "count_value": 12, "count_before_list": True, "list_items": 10, "pagination": True, "no_results_text": None,
             "no_results_hints": False, "sort_control": {"present": True, "before_list": True}}
        r.update(over)
        return {"results": r, "query": {"terms": ["cats"]}}

    def run(template: str, structure: dict, **lines: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record(root, "r", "Screen One", Template=template, States="loaded", Nav="level 1 under shell", **lines)
            f, _, u = judge_templates([snap(**structure)], [{"url": "/s", "screen": "Screen One"}], root)
            return [x["rule"] for x in f] + [f"unverified:{x}" for x in u]

    # multi-step
    check("a conforming question page has no findings", run("multi-step", GOOD_STEP) == [])
    check("no back link is an A31 finding", run("multi-step", {**GOOD_STEP, "back_link": {"present": False, "before_h1": False, "text": None}}) == ["A31"])
    check("a back link after the h1 is an A31 finding", run("multi-step", {**GOOD_STEP, "back_link": {"present": True, "before_h1": False, "text": "Back"}}) == ["A31"])
    check('a "Next" button is an A34 finding', run("multi-step", {**GOOD_STEP, "forward_button": {"present": True, "label": "Next"}}) == ["A34"])
    check('"NEXT" in capitals is an A34 finding too', run("multi-step", {**GOOD_STEP, "forward_button": {"present": True, "label": " NEXT "}}) == ["A34"])
    check("a label the rule does not name is not asserted", run("multi-step", {**GOOD_STEP, "forward_button": {"present": True, "label": "Save and go on"}}) == [])
    check("a page with no forward button has no A34 finding", run("multi-step", {**GOOD_STEP, "forward_button": {"present": False, "label": None}}) == [])
    # search-results
    check("a conforming results page has no findings", run("search-results", results()) == [])
    check("no results count is an A53 finding", run("search-results", results(count_text=None, count_value=None, count_before_list=None)) == ["A53"])
    check("a count below the list is an A54 finding", run("search-results", results(count_before_list=False)) == ["A54"])
    check("a count that does not name the search terms is an A54 finding", run("search-results", results(count_text="12 results")) == ["A54"])
    check("a count is not required to name terms when the URL carries none", run("search-results", {**results(count_text="12 results"), "query": {"terms": []}}) == [])
    check("more than ten results with no pagination is an A53 finding", run("search-results", results(pagination=False)) == ["A53"])
    check("exactly ten results need no pagination", run("search-results", results(count_text='10 results for "cats"', count_value=10, pagination=False)) == [])
    check("eleven results on one page is an A57 finding", run("search-results", results(list_items=11)) == ["A57"])
    check("no results and no message is an A53 finding", run("search-results", results(count_text='0 results for "cats"', count_value=0, list_items=0, pagination=False)) == ["A53"])
    check("a no-results message with no hints is an A55 finding", run("search-results", results(count_text='0 results for "cats"', count_value=0, list_items=0, pagination=False,
                                                                                            no_results_text="There are no results", no_results_hints=False)) == ["A55"])
    check("a no-results message with hints is clean", run("search-results", results(count_text='0 results for "cats"', count_value=0, list_items=0, pagination=False,
                                                                                  no_results_text="There are no results", no_results_hints=True)) == [])
    check("a sort control below the list is an A56 finding", run("search-results", results(sort_control={"present": True, "before_list": False})) == ["A56"])
    check("no sort control is not a finding (a sort is optional)", run("search-results", results(sort_control={"present": False, "before_list": None})) == [])
    # applicability: a rule is judged only for its template
    check("a list screen is not judged for a back link", run("list", {}) == [])
    check("a multi-step screen is not judged for a results count", run("multi-step", {**GOOD_STEP, **results(count_text=None)}) == [])
    # a missing structure is unverified, never clean
    check("a template screen with no structure is unverified, never a pass", [x for x in run("multi-step", {}) if x.startswith("unverified")])
    # undeclared
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record(root, "ok", "Screen One", Template="list", States="loaded", Nav="level 1 under shell")
        record(root, "no-nav", "Screen Two", Template="list", States="loaded")
        record(root, "no-template", "Screen Three", Nav="level 1 under shell", States="loaded")
        s = lambda url, **kw: snap(url, **kw)  # noqa: E731
        f, aud, unv = judge_templates([s("/1"), s("/2"), s("/3"), s("/4"), s("/5")],
                                      [{"url": "/1", "screen": "Screen One"}, {"url": "/2", "screen": "Screen Two"}, {"url": "/3", "screen": "Screen Three"},
                                       {"url": "/4", "screen": None}], root)
        by_url = {x["screen"]: x for x in f}
        check("a screen with a complete record is not undeclared", "/1" not in by_url)
        check("a record with no Nav line is an A10 finding naming the missing line", "/2" in by_url and "`Nav:` line" in by_url["/2"]["message"])
        check("a record with no Template line is an A10 finding", "/3" in by_url and "`Template:` line" in by_url["/3"]["message"])
        check("a url mapped to null is an A10 finding", "/4" in by_url and by_url["/4"]["rule"] == "A10")
        check("a url in no entry is an A10 finding, never assumed declared", "/5" in by_url)
        check("every undeclared finding carries a proposed record to review", all("proposal" in by_url[u] and "Screen:" in by_url[u]["proposal"] for u in ("/2", "/3", "/4", "/5")))
        check("A10 is audited over every screen", aud["A10"] == 5)
        sr = snap("/6", **results())
        sr["structure"]["results"]["list_items"] = 3
        f2, _, _ = judge_templates([sr], [{"url": "/6", "screen": None}], root)
        check("the proposal names a Template from a results structure, as a proposal", "Template: search-results" in f2[0]["proposal"] and "not a verdict" in f2[0]["proposal"])
        f3, _, _ = judge_templates([snap("/7")], [{"url": "/7", "screen": None}], root)
        check("with nothing to go on the proposal names no template", "<one of the nine" in f3[0]["proposal"])
        # the refusals
        def refuses(screens_doc, needle: str, setup=None) -> bool:
            try:
                judge_templates([s("/1")], screens_doc, root)
                return False
            except Unusable as err:
                return needle in str(err)
        check("a screen no record names is refused", refuses([{"url": "/1", "screen": "Nowhere"}], "no mock-up record has"))
        check("a screens file that is not a list is refused", refuses({"url": "/1"}, "must be a list"))
        check("an entry with no url is refused", refuses([{"screen": "Screen One"}], "needs a `url`"))
        check("a url listed twice is refused", refuses([{"url": "/1", "screen": None}, {"url": "/1", "screen": None}], "appears twice"))
        check("a non-string screen is refused", refuses([{"url": "/1", "screen": 5}], "a record's `Screen:` name"))
        record(root, "dup", "Screen One", Template="list", States="loaded", Nav="level 1 under shell")
        check("two records with one Screen: are refused", refuses([{"url": "/1", "screen": "Screen One"}], "unique"))
        (root / RECORD_DIR / "dup.md").unlink()
    # the shell record is not a screen
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        d = root / RECORD_DIR
        d.mkdir(parents=True)
        (d / "shell.md").write_text("Kind: shell\nScreen: Shell\nTemplate: list\n", encoding="utf-8")
        check("the shell record is not a screen", "Shell" not in load_records(root))
    check("the rules the module claims are the rules it judges",
          set(RULES) == {"A10", "A31", "A34", "A53", "A54", "A55", "A56", "A57"})

    bad = 0
    for label, ok in cases:
        bad += not ok
        print(f"  [{'ok' if ok else 'FAIL'}] {label}")
    print(f"interface_templates selftest: {len(cases) - bad}/{len(cases)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if sys.argv[1:] == ["--selftest"] else 2)
