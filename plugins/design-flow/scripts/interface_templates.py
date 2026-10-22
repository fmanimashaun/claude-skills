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

WHAT IS MEASURED. The browser collector records FACTS in `structure`; this decides. Fifteen rules, each only for the template that owns it:
  multi-step      (a question page: `Template: multi-step` with no sub-kind, #2310)
                  A31 a back link at the top (present, and before the page's h1)
                  A34 the forward button is labelled "Continue", not "Next" (a finding only for "Next": the other labels the rule does not name are not asserted)
  multi-step: check-answers (#2327)
                  A35 a Change link on every row of the summary list
                  A36 each Change link's accessible name says more than "Change" (the hidden text naming what it changes)
                  A40 a text block sits between the answers and the submit button (its presence, never its wording)
  multi-step: task-list (#2327)
                  A43 a list of fewer than two tasks is not a task list
                  A44 one list per group: two lists under one heading are a finding
                  A46 every task shows a status
                  A47 a task whose status is the project's "cannot start" word is not a link
                  A50 no way forward while a task is not "completed"
  search-results  A53 a results count; pagination when the count is above ten; and, with no results, a no-results message
                  A54 the count sits above the list, and names a search term when the URL carries one
                  A55 with no results the message says so plainly and offers hints
                  A56 a sort control, when there is one, sits above the results
                  A57 no more than ten results on a page
`multi-step: confirmation` has NO judge: the rules about a confirmation page (A41, A42) are statements in prose, so the page is not judged and is not
reported as unverified either; the report's Not audited section says why.

THE TASK STATUS WORDS (A47, A50) are the project's. A task-list record may carry `Statuses: not-started=To do; cannot-start=Blocked; completed=Done`
(`reference/mockup-record.md`); with no line the GOV.UK wording is used. A list whose status words match neither vocabulary has A47 and A50 left out of
the audited rules and its screen reported as unverified, never clean and never guilty; a status word the vocabulary does not name also leaves A50 out
(it could mean "done"), though a finding A47 can still make from a word it does know stands.

NOT MEASURED, and named in the report with their reasons (`audit_findings.NOT_MEASURED_TEMPLATE`): A29, A30, A33 (one question per page, a statement
heading, a heading no other page of the flow shares: they need a declared flow or a judgement), A32, A37, A39, A48, A49, A51 (they need a driven journey),
A38, A41, A42 (statements in prose: a phrase match would be a wrong check), A45 and A52 (a judgement), and A58 (a partial update needs a driver).

Exit codes are `interface_audit.py`'s. Stdlib only.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mockup_records import RECORD_DIR, SHELL_RECORD, read_fields  # noqa: E402  (vendored, byte-identical to rails-flow's: the one reader of a record)

CHECK_ANSWERS, TASK_LIST = "multi-step: check-answers", "multi-step: task-list"
TEMPLATE_RULES = {"multi-step": ("A31", "A34"), "search-results": ("A53", "A54", "A55", "A56", "A57"),
                  CHECK_ANSWERS: ("A35", "A36", "A40"), TASK_LIST: ("A43", "A44", "A46", "A47", "A50")}
# The words a task list shows for its statuses unless its record's `Statuses:` line says otherwise: the GOV.UK pattern's own (#2327).
DEFAULT_STATUSES = {"not-started": "Not started", "in-progress": "In progress", "cannot-start": "Cannot start yet", "completed": "Completed"}
RULES = ("A10", *(r for rules in TEMPLATE_RULES.values() for r in rules))
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

def parse_statuses(line: str | None, where: str) -> dict[str, str]:
    """`{role: word}` from a record's `Statuses:` line (`cannot-start=Blocked; completed=Done`), the GOV.UK wording when there is no line.

    check_mockup_gate.py refuses a malformed line when a record is added or changed; this reads records that predate it or were never
    judged, so it refuses too (a half-read mapping would judge a project's tasks by words it never used)."""
    if not line:
        return dict(DEFAULT_STATUSES)
    out: dict[str, str] = {}
    for entry in (e.strip() for e in line.split(";")):
        role, eq, word = (part.strip() for part in entry.partition("="))
        if not eq or not word or role not in DEFAULT_STATUSES or role in out:
            raise Unusable(f"{where}: Statuses entry {entry!r} must read `<role>=<word>` with a role of {', '.join(DEFAULT_STATUSES)}, once each")
        if word.lower() in {w.lower() for w in out.values()}:
            raise Unusable(f"{where}: Statuses gives {word!r} to two roles: one word stands for one state")
        out[role] = word
    missing = [r for r in ("cannot-start", "completed") if r not in out]
    if missing:
        raise Unusable(f"{where}: Statuses must name {', '.join(missing)}")
    return out


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
        # `multi-step: check-answers` stays whole: a sub-kind is a different page from the question page the multi-step rules describe (#2310)
        template = re.sub(r"\s*:\s*", ": ", fields.get("Template", "").strip()).rstrip(": ")
        records[name] = {"template": template, "fields": fields, "path": f"{RECORD_DIR}{path.name}", "statuses": parse_statuses(fields.get("Statuses"), path.name)}
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


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def judge_check_answers(url: str, s: dict, statuses: dict[str, str]) -> tuple[list[dict], list[str]]:
    """A35 a Change link on every row, A36 its accessible name says what it changes, A40 a text block between the summary and the submit button.
    Presence and structure only: what the statement SAYS is prose (A38) and is never judged."""
    ca = s["check_answers"]
    out: list[dict] = []
    rows = ca["rows"]
    bare = [r for r in rows if not r["change_links"]]
    if bare:
        out.append(finding("A35", url, f"{len(bare)} of {len(rows)} summary rows have no Change link at {url}",
                           f"{_plural(len(bare), 'row')} of the answers {'has' if len(bare) == 1 else 'have'} no Change link", None) | {"instances": len(bare)})
    links = [l for r in rows for l in r["change_links"]]
    vague = [l for l in links if (l["name"] or "").strip().lower() == (l["visible"] or "").strip().lower()]
    if vague:
        out.append(finding("A36", url, f"{len(vague)} of {len(links)} Change links are named only {vague[0]['visible']!r} at {url}",
                           f"{_plural(len(vague), 'Change link')} {'says' if len(vague) == 1 else 'say'} only what the link is, not what it changes (no hidden text)", None)
                   | {"instances": len(vague)})
    if ca["submit_present"] and not ca["text_before_submit"]:
        out.append(finding("A40", url, f"no text block between the answers and the submit button at {url}", "no statement sits above the submit button"))
    return out, ([] if ca["submit_present"] else ["A40"])


def judge_task_list(url: str, s: dict, statuses: dict[str, str]) -> tuple[list[dict], list[str]]:
    """A43 more than one task, A44 one list per group, A46 every task shows a status, A47 a task that cannot start is not a link, A50 move on only
    when every task is Completed. A47 and A50 read the status WORDS, the record's (`Statuses:`) or the GOV.UK default; a list whose words match
    neither is not judged for those two (unverified), never reported clean and never reported guilty."""
    tl = s["task_list"]
    out: list[dict] = []
    skipped: list[str] = []
    items = [i for l in tl["lists"] for i in l["items"]]
    if len(items) < 2:
        out.append(finding("A43", url, f"{len(items)} task(s) in the task list at {url}", "a task list of fewer than two tasks is not a task list"))
    by_heading: dict[object, int] = {}
    for l in tl["lists"]:
        by_heading[l["heading_index"]] = by_heading.get(l["heading_index"], 0) + 1
    shared = [h for h, n in by_heading.items() if n > 1]
    if shared:
        out.append(finding("A44", url, f"{len(shared)} heading(s) with more than one task list at {url}",
                           "a group of tasks is split across more than one task list") | {"instances": len(shared)})
    blank = [i for i in items if not (i["status"] or "").strip()]
    if blank:
        out.append(finding("A46", url, f"{len(blank)} of {len(items)} tasks show no status at {url}",
                           f"{_plural(len(blank), 'task')} {'shows' if len(blank) == 1 else 'show'} no status") | {"instances": len(blank)})
    words = {w.lower(): role for role, w in statuses.items()}
    known = [i for i in items if (i["status"] or "").strip().lower() in words]
    if items and not known and len(blank) < len(items):
        return out, ["A47", "A50"]
    stuck = [i for i in items if words.get((i["status"] or "").strip().lower()) == "cannot-start" and i["has_link"]]
    if stuck:
        out.append(finding("A47", url, f"{len(stuck)} task(s) with status {statuses['cannot-start']!r} are links at {url}",
                           f"{_plural(len(stuck), 'task')} that cannot be started {'is' if len(stuck) == 1 else 'are'} still a link") | {"instances": len(stuck)})
    # A status the vocabulary does not name could mean "done", so A50 is not judged while one is on the page.
    unnamed = [i for i in items if (i["status"] or "").strip() and (i["status"] or "").strip().lower() not in words]
    if unnamed:
        return out, ["A50"]
    open_ = [i for i in items if words.get((i["status"] or "").strip().lower()) != "completed"]
    if tl["forward_present"] and open_:
        out.append(finding("A50", url, f"{len(open_)} of {len(items)} tasks are not {statuses['completed']!r}, yet a way forward is offered at {url}",
                           "the user can move on from the task list before every task is complete"))
    return out, []


def _plain(judge):
    """Adapt a judge that returns only findings and ignores the record's statuses."""
    return lambda url, s, statuses: (judge(url, s), [])


JUDGES = {"multi-step": _plain(judge_multi_step), "search-results": _plain(judge_search_results),
          CHECK_ANSWERS: judge_check_answers, TASK_LIST: judge_task_list}


def validate_structure(url: str, s: object, template: str) -> None:
    """Refuse a structure block that cannot be judged (a missing fact is not a pass)."""
    def need(cond: bool, what: str) -> None:
        if not cond:
            raise Unusable(f"snapshot {url}: `structure` {what}")
    need(isinstance(s, dict), "is missing: the collector records it, and a template row is never judged without it")
    if template == CHECK_ANSWERS:
        ca = s.get("check_answers")
        need(isinstance(ca, dict) and isinstance(ca.get("rows"), list) and ca["rows"], "needs check_answers.rows: no summary list was found, so no row was measured")
        need(all(isinstance(r, dict) and isinstance(r.get("change_links"), list) and all(isinstance(l, dict) and "visible" in l and "name" in l for l in r["change_links"])
                 for r in ca["rows"]), "needs each row's change_links, each with its visible text and its accessible name")
        need(isinstance(ca.get("submit_present"), bool) and isinstance(ca.get("text_before_submit"), bool), "needs check_answers.submit_present and text_before_submit")
    elif template == TASK_LIST:
        tl = s.get("task_list")
        need(isinstance(tl, dict) and isinstance(tl.get("lists"), list) and tl["lists"] and isinstance(tl.get("forward_present"), bool),
             "needs task_list.lists (a task list was found) and forward_present")
        need(all(isinstance(l, dict) and "heading_index" in l and isinstance(l.get("items"), list)
                 and all(isinstance(i, dict) and "status" in i and isinstance(i.get("has_link"), bool) for i in l["items"]) for l in tl["lists"]),
             "needs each list's heading_index and items, each with a status and has_link")
    elif template == "multi-step":
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
    if r.get("count_text") is not None and (r.get("list_items") or 0) > 0:
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
        except Unusable:
            unverified.append(url)
            continue
        found, skipped = JUDGES[template](url, snap["structure"], record["statuses"])
        findings += found
        for rule in TEMPLATE_RULES[template]:
            if rule not in skipped:
                audited[rule] = audited.get(rule, 0) + 1
        if skipped:
            unverified.append(url)
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

    def CA_ROW(links=None, name="Change your answer"):
        return {"key": "Name", "change_links": [{"visible": "Change", "name": name}] if links is None else links}

    def CA(rows=None, submit=True, text=True):
        return {"rows": [CA_ROW(), CA_ROW()] if rows is None else rows, "submit_present": submit, "text_before_submit": text}

    def TLI(status, link):
        return {"name": "A task", "status": status, "has_link": link}

    def TLL(items=None, heading=0):
        return {"heading_index": heading, "items": [TLI("Completed", True), TLI("Cannot start yet", False)] if items is None else items}

    def TL(lists=None, forward=False):
        return {"lists": [TLL()] if lists is None else lists, "forward_present": forward}

    def judge_one(template: str, structure: dict) -> list[dict]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record(root, "r", "Screen One", Template=template, States="loaded", Nav="level 1 under shell")
            return judge_templates([snap(**structure)], [{"url": "/s", "screen": "Screen One"}], root)[0]

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
            try:
                f, _, u = judge_templates([snap(**structure)], [{"url": "/s", "screen": "Screen One"}], root)
            except Exception as err:  # a mutant that crashes must fail a check, not end the run before later checks print
                return [f"crash:{type(err).__name__}"]
            return [x["rule"] for x in f] + [f"unverified:{x}" for x in u]

    # multi-step
    check("a conforming question page has no findings", run("multi-step", GOOD_STEP) == [])
    check("no back link is an A31 finding", run("multi-step", {**GOOD_STEP, "back_link": {"present": False, "before_h1": False, "text": None}}) == ["A31"])
    check("a back link after the h1 is an A31 finding", run("multi-step", {**GOOD_STEP, "back_link": {"present": True, "before_h1": False, "text": "Back"}}) == ["A31"])
    check('a "Next" button is an A34 finding', run("multi-step", {**GOOD_STEP, "forward_button": {"present": True, "label": "Next"}}) == ["A34"])
    check('"NEXT" in capitals is an A34 finding too', run("multi-step", {**GOOD_STEP, "forward_button": {"present": True, "label": " NEXT "}}) == ["A34"])
    check("a label the rule does not name is not asserted", run("multi-step", {**GOOD_STEP, "forward_button": {"present": True, "label": "Save and go on"}}) == [])
    check("a missing back link is a finding whatever the position fact says", run("multi-step", {**GOOD_STEP, "back_link": {"present": False, "before_h1": True, "text": None}}) == ["A31"])
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
    # a sub-kind keeps its whole template (#2310): the question-page rules (back link, Continue) never reach it
    for sub_kind, structure in (("check-answers", {"check_answers": CA()}), ("task-list", {"task_list": TL()}), ("confirmation", {})):
        check(f"a multi-step: {sub_kind} page is not judged as a question page", run(f"multi-step: {sub_kind}", structure) == [])
    check("a trailing colon leaves no trailing space, so the template still names a judge", run("multi-step:", GOOD_STEP) == [] and run("multi-step: ", {**GOOD_STEP, "forward_button": {"present": True, "label": "Next"}}) == ["A34"])
    check("a multi-step: sub-kind written without a space is read the same", run("multi-step:confirmation", {}) == [])
    check("a confirmation page has no judge: it is not judged, and it is not reported as unverified either", run("multi-step: confirmation", GOOD_STEP) == [])

    # ---- check-answers (A35, A36, A40) ------------------------------------------------------------
    check("a conforming check-answers page has no findings", run("multi-step: check-answers", {"check_answers": CA()}) == [])
    check("a row with no Change link is an A35 finding", run("multi-step: check-answers", {"check_answers": CA(rows=[CA_ROW(), CA_ROW(links=[])])}) == ["A35"])
    check("A35 counts the rows that lack one, in one finding", [f["instances"] for f in judge_one("multi-step: check-answers", {"check_answers": CA(rows=[CA_ROW(links=[]), CA_ROW(links=[])])})] == [2])
    check("a Change link named only 'Change' is an A36 finding", run("multi-step: check-answers", {"check_answers": CA(rows=[CA_ROW(name="Change")])}) == ["A36"])
    check("A36 ignores case and padding", run("multi-step: check-answers", {"check_answers": CA(rows=[CA_ROW(name=" CHANGE ")])}) == ["A36"])
    check("a Change link whose name carries the hidden text is clean", run("multi-step: check-answers", {"check_answers": CA(rows=[CA_ROW(name="Change your address")])}) == [])
    check("no text block above the submit button is an A40 finding", run("multi-step: check-answers", {"check_answers": CA(text=False)}) == ["A40"])
    check("a check-answers page with no submit button has A40 not judged, and is unverified", run("multi-step: check-answers", {"check_answers": CA(submit=False, text=False)}) == ["unverified:/s"])
    check("a check-answers page where no summary list was found is unverified, never a pass", run("multi-step: check-answers", {"check_answers": CA(rows=[])}) == ["unverified:/s"])

    # ---- task list (A43, A44, A46, A47, A50) -------------------------------------------------------
    check("a conforming task list has no findings", run("multi-step: task-list", {"task_list": TL()}) == [])
    check("a task list of one task is an A43 finding", run("multi-step: task-list", {"task_list": TL(lists=[TLL([TLI("Completed", True)])])}) == ["A43"])
    check("two task lists under one heading are an A44 finding", run("multi-step: task-list", {"task_list": TL(lists=[TLL(heading=0), TLL(heading=0)])}) == ["A44"])
    check("two task lists under two headings are clean", run("multi-step: task-list", {"task_list": TL(lists=[TLL(heading=0), TLL(heading=1)])}) == [])
    check("a task with no status is an A46 finding", run("multi-step: task-list", {"task_list": TL(lists=[TLL([TLI("Completed", True), TLI(None, True)])])}) == ["A46"])
    check("a task whose status is only spaces is an A46 finding", run("multi-step: task-list", {"task_list": TL(lists=[TLL([TLI("Completed", True), TLI("  ", True)])])}) == ["A46"])
    check("a task that cannot start but is a link is an A47 finding", run("multi-step: task-list", {"task_list": TL(lists=[TLL([TLI("Completed", True), TLI("Cannot start yet", True)])])}) == ["A47"])
    check("A47 ignores the case of the status", run("multi-step: task-list", {"task_list": TL(lists=[TLL([TLI("Completed", True), TLI("CANNOT START YET", True)])])}) == ["A47"])
    check("a task that is a link and Completed is not an A47 finding", run("multi-step: task-list", {"task_list": TL(lists=[TLL([TLI("Completed", True), TLI("Completed", True)])])}) == [])
    check("a way forward while a task is not Completed is an A50 finding", run("multi-step: task-list", {"task_list": TL(forward=True)}) == ["A50"])
    check("a way forward when every task is Completed is clean", run("multi-step: task-list", {"task_list": TL(lists=[TLL([TLI("Completed", True), TLI("Completed", True)])], forward=True)}) == [])
    check("no way forward while a task is open is clean", run("multi-step: task-list", {"task_list": TL(forward=False)}) == [])
    check("a task list the collector could not find is unverified, never a pass", run("multi-step: task-list", {"task_list": TL(lists=[])}) == ["unverified:/s"])

    # the status vocabulary: declared (judged) against renamed and undeclared (unverified)
    renamed = {"task_list": TL(lists=[TLL([TLI("Done", True), TLI("Blocked", True)])], forward=True)}
    check("a renamed vocabulary that IS declared is judged: the link on a Blocked task and the open task are findings",
          run("multi-step: task-list", renamed, Statuses="cannot-start=Blocked; completed=Done") == ["A47", "A50"])
    check("a renamed vocabulary that is NOT declared is unverified for A47 and A50, never clean and never guilty",
          run("multi-step: task-list", renamed) == ["unverified:/s"])
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        record(root, "r", "Screen One", Template="multi-step: task-list", States="loaded", Nav="level 1 under shell")
        _, aud, _ = judge_templates([snap(**renamed)], [{"url": "/s", "screen": "Screen One"}], root)
        check("a vocabulary nothing matches leaves A47 and A50 out of the audited rules, and A46 in",
              "A47" not in aud and "A50" not in aud and aud.get("A46") == 1)
    check("...and A46 is still judged there, because it reads no word",
          run("multi-step: task-list", {"task_list": TL(lists=[TLL([TLI("Done", True), TLI(None, True)])], forward=True)}) == ["A46", "unverified:/s"])
    check("a declared vocabulary is not mixed with the default: 'Cannot start yet' means nothing once the project says Blocked",
          run("multi-step: task-list", {"task_list": TL(lists=[TLL([TLI("Done", True), TLI("Cannot start yet", True)])])}, Statuses="cannot-start=Blocked; completed=Done") == ["unverified:/s"])
    check("a status the vocabulary does not name is not guessed at: A50 is not judged, though A47 still is",
          run("multi-step: task-list", {"task_list": TL(lists=[TLL([TLI("Completed", True), TLI("Waiting", True)])], forward=True)}) == ["unverified:/s"])
    check("...and an A47 finding there is still reported, because it reads one known word",
          run("multi-step: task-list", {"task_list": TL(lists=[TLL([TLI("Cannot start yet", True), TLI("Waiting", True)])], forward=True)}) == ["A47", "unverified:/s"])
    for label, line in (("a role twice", "cannot-start=A; cannot-start=B; completed=C"), ("an unknown role", "cannot-start=A; completed=B; later=C"),
                        ("no completed", "cannot-start=A"), ("one word for two roles", "cannot-start=A; completed=a"), ("an entry that is not role=word", "cannot-start A; completed=B")):
        try:
            parse_statuses(line, "r.md")
            check(f"a Statuses line with {label} is refused", False)
        except Unusable:
            check(f"a Statuses line with {label} is refused", True)
    check("no Statuses line means the GOV.UK wording", parse_statuses(None, "r.md") == DEFAULT_STATUSES)
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
        check("every undeclared finding carries a proposed record to review", all("Screen:" in by_url.get(u, {}).get("proposal", "") for u in ("/2", "/3", "/4", "/5")))
        check("A10 is audited over every screen", aud["A10"] == 5)
        sr = snap("/6", **results())
        sr["structure"]["results"]["list_items"] = 3
        f2, _, _ = judge_templates([sr], [{"url": "/6", "screen": None}], root)
        check("the proposal names a Template from a results structure, as a proposal", "Template: search-results" in (f2 or [{}])[0].get("proposal", "") and "not a verdict" in (f2 or [{}])[0].get("proposal", ""))
        f3, _, _ = judge_templates([snap("/7")], [{"url": "/7", "screen": None}], root)
        check("with nothing to go on the proposal names no template", "<one of the nine" in (f3 or [{}])[0].get("proposal", ""))
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
          set(RULES) == {"A10", "A31", "A34", "A53", "A54", "A55", "A56", "A57", "A35", "A36", "A40", "A43", "A44", "A46", "A47", "A50"})

    bad = 0
    for label, ok in cases:
        bad += not ok
        print(f"  [{'ok' if ok else 'FAIL'}] {label}")
    print(f"interface_templates selftest: {len(cases) - bad}/{len(cases)}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv[1:] else 2)
