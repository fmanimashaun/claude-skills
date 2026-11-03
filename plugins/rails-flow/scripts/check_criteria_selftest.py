#!/usr/bin/env python3
"""Prove every acceptance-criteria rule fires -- and, harder, that it stays silent.

Run:  python3 check_criteria.py --selftest   (or execute this file directly)

The silent direction decides whether this survives. A criteria checker that flags well-written
criteria gets switched off after the third false positive, and then the flow is back to
post-hoc goals. So the rubber-stamp list has near-miss fixtures: "properly" must not fire
inside "property", and a criterion whose observable legitimately contains "not found" (a 404
page IS the observable) must pass.

Fixtures are adversarial rather than realistic -- a realistic criteria file exercises only the
happy path, which is the same blind spot the rule itself is about.

Costs nothing: no network, no Rails, no bundler.
"""

from __future__ import annotations

import sys as _rf_sys; from pathlib import Path as _RfPath; _rf_sys.path.insert(0, str(_RfPath(__file__).resolve().parent))  # rf_tmp (#2306)
import rf_tmp  # noqa: E402  -- rf- temp dirs, removed at exit and on a signal
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_criteria as cc  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

GOOD = (
    "## Sign-in\n"
    "- **AC-1** Given a registered user, when they submit the sign-in form with a correct "
    "password, then the browser lands on /dashboard and the header shows their name\n"
    "- **AC-2** Given a wrong password, when the user submits the sign-in form, then the page "
    "shows 'wrong email or password' and does NOT redirect to the dashboard [error]\n"
)


def _tick() -> None:
    global CHECKS
    CHECKS += 1


def _write(body: str) -> Path:
    root = Path(rf_tmp.mkdtemp("railsflow-criteria-"))
    p = root / "acceptance.md"
    p.write_text(body, encoding="utf-8")
    return p


def expect_clean(label: str, body: str, *, specs: Path | None = None) -> None:
    _tick()
    try:
        findings = cc.check(cc.parse(_write(body)), specs)
    except cc.Unusable as exc:
        FAILURES.append(f"{label}: expected clean, got UNUSABLE ({exc})")
        return
    if findings:
        FAILURES.append(f"{label}: expected clean, got {len(findings)}: {findings}")


def expect_findings(label: str, body: str, *, contains: str, count: int | None = None,
                    specs: Path | None = None) -> None:
    _tick()
    try:
        findings = cc.check(cc.parse(_write(body)), specs)
    except cc.Unusable as exc:
        FAILURES.append(f"{label}: expected findings, got UNUSABLE ({exc})")
        return
    if not findings:
        FAILURES.append(f"{label}: expected findings, got clean")
        return
    blob = " | ".join(findings)
    if contains.lower() not in blob.lower():
        FAILURES.append(f"{label}: findings omit {contains!r}: {blob}")
    if count is not None and len(findings) != count:
        FAILURES.append(f"{label}: expected {count}, got {len(findings)}: {blob}")


def expect_unusable(label: str, body: str, *, contains: str) -> None:
    _tick()
    try:
        cc.parse(_write(body))
    except cc.Unusable as exc:
        if contains.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: message omits {contains!r}: {exc}")
        return
    FAILURES.append(f"{label}: expected UNUSABLE, input was accepted")


def run() -> int:
    # ---- the silence proof --------------------------------------------------------------
    expect_clean("well-written criteria", GOOD)

    # ---- the shape ---------------------------------------------------------------------
    expect_findings(
        "no Given/when/then at all -- the issue's 'login works'",
        "## Sign-in\n- **AC-1** login works [error]\n",
        contains="missing Given, when, then",
    )
    expect_findings(
        "missing only the then clause",
        "## Sign-in\n- **AC-1** Given a user, when they submit the form, the page updates [error]\n",
        contains="missing then",
    )
    expect_findings(
        "trivial when clause",
        "## Sign-in\n- **AC-1** Given a user, when submitted, then the page shows an error "
        "message [error]\n",
        contains="names no real action",
    )
    expect_findings(
        "trivial then clause",
        "## Sign-in\n- **AC-1** Given a bad password, when the user submits the form, then it "
        "fails\n",
        contains="names no real observable",
    )

    # ---- rubber-stamp phrasings: the issue's own 'bad' list -----------------------------
    for phrase in ("works correctly", "handles errors", "gracefully", "as expected",
                   "no errors", "is correct"):
        expect_findings(
            f"rubber-stamp observable {phrase!r}",
            f"## Unit\n- **AC-1** Given an invalid invoice, when POST /invoices runs, then it "
            f"{phrase} and nothing breaks [error]\n",
            contains="rubber-stamp phrasing",
        )

    # ---- near misses: the rule must NOT fire on legitimate criteria --------------------
    # "property" contains "properly"? No -- but "properly" as a substring of another word is
    # exactly the kind of match that turns a useful rule into a disabled one. Pin it.
    expect_clean(
        "the word 'property' does not trip the 'properly' rule",
        "## Listings\n- **AC-1** Given a listing with no photos, when the agent opens the "
        "property page, then the gallery region shows the 'no photos yet' empty state [error]\n",
    )
    expect_clean(
        "'not found' is a legitimate observable (the 404 page IS the expected result)",
        "## Routing\n- **AC-1** Given an unknown slug, when GET /articles/nope runs, then the "
        "response is 404 and the page renders the 'not found' design [error]\n",
    )
    expect_clean(
        "'workspace' does not trip the 'works' rule",
        "## Workspaces\n- **AC-1** Given a member of two workspaces, when they switch "
        "workspace, then the sidebar lists only the new workspace's projects\n"
        "- **AC-2** Given a non-member, when they request another workspace, then the response "
        "is 403 and no project names appear [error]\n",
    )

    # ---- every unit needs an error path ------------------------------------------------
    expect_findings(
        "happy-path-only unit",
        "## Sign-in\n- **AC-1** Given a registered user, when they submit valid credentials, "
        "then the browser lands on /dashboard\n",
        contains="no error-path criterion",
        count=1,
    )
    expect_clean(
        "an explicit [error] tag satisfies it",
        "## Sign-in\n- **AC-1** Given a registered user, when they submit valid credentials, "
        "then the browser lands on /dashboard\n"
        "- **AC-2** Given a locked account, when they submit valid credentials, then the page "
        "shows 'account locked' and stays on /sign-in [error]\n",
    )
    expect_clean(
        "an untagged failure case still counts (keyword fallback)",
        "## Invoices\n- **AC-1** Given an invoice with line items, when POST /invoices runs, "
        "then the response is 201 and the invoice appears in the index\n"
        "- **AC-2** Given an invoice with no line items, when POST /invoices runs, then the "
        "response is 422 and the modal re-renders with 'must have at least one line item'\n",
    )
    # ---- #1189: Ruby expresses an error path by raising --------------------------------
    HAPPY = ("## Segments\n- **AC-1** Given two segments, when the control renders, then both "
             "appear as buttons and the first is pressed\n")
    expect_clean(
        "an untagged `raises SomeError` criterion counts as the error path",
        HAPPY + "- **AC-2** Given one segment, when the component is initialised, then it raises "
        "ArgumentError naming the minimum of two\n",
    )
    expect_clean(
        "`raises an error` and `rescues` count too",
        HAPPY + "- **AC-2** Given a pressed count of zero, when the caller initialises the component, "
        "then it raises an error, and the controller rescues it into a flash\n",
    )
    # #1209: criteria are markdown, so the class arrives quoted or in the passive.
    for label, clause in (
        ("a backtick-quoted class after `raises` counts", "then it raises `ArgumentError`"),
        ("an article before a quoted class counts", "then it raises an `ActiveRecord::RecordNotFound`"),
        ("a bold class after `raises` counts", "then it raises **ArgumentError**"),
        ("the passive `X is raised` counts", "then `ActiveRecord::RecordNotFound` is raised"),
        ("a class ending in Error counts without the verb",
         "then the builder refuses it with `Segments::TooFewError`"),
    ):
        expect_clean(
            label,
            HAPPY + "- **AC-2** Given fewer than two segments, when it is built, " + clause + "\n",
        )
    # The passive and the suffix must not turn domain prose into an error path either.
    expect_findings(
        "a lowercase 'a request is raised' is not an error path",
        "## Requests\n- **AC-1** Given a requester, when they raise a request, then a ticket is raised "
        "and shown to the facilities team\n",
        contains="no error-path criterion",
        count=1,
    )
    # THE CONTROL ON THE SAME VERB. In a domain app a requester RAISES a request; if a bare "raise"
    # counted, this happy-path-only unit would pass with no error path at all.
    expect_findings(
        "the DOMAIN verb 'raises a request' is not an error path",
        "## Requests\n- **AC-1** Given a requester, when they raise a request, then it appears in "
        "their list as raised 8 Sep\n",
        contains="no error-path criterion",
        count=1,
    )
    expect_findings(
        "a second unit without an error path is caught even when the first has one",
        GOOD + "## Invoices\n- **AC-3** Given a draft invoice, when the user clicks Send, then "
        "the status column reads 'sent'\n",
        contains="'Invoices'",
        count=1,
    )

    # ---- duplicate ids would make the spec mapping ambiguous --------------------------
    expect_findings(
        "duplicate criterion id",
        "## Sign-in\n- **AC-1** Given a user, when they submit the form, then the dashboard "
        "loads\n- **AC-1** Given a bad password, when they submit the form, then an error "
        "message appears [error]\n",
        contains="reuses an id",
    )

    # ---- unusable input: never report clean over something unparsed ------------------
    expect_unusable("no criteria at all", "## Sign-in\nSome prose, no ids.\n", contains="no `AC-n` criteria")
    expect_unusable("empty file", "", contains="no `AC-n` criteria")
    expect_unusable(
        "two ids on one line makes the mapping ambiguous",
        "## Sign-in\n- **AC-1** and **AC-2** Given a user, when they submit, then it loads\n",
        contains="one criterion per line",
    )
    # ---- #707: prose that REFERENCES criteria is not a criterion ---------------------
    # The live repro, verbatim in shape from the acceptance doc that was rejected: nine well-formed
    # criteria, and one true sentence under `## Notes` naming two ids. The old parser read the note
    # as a malformed definition and failed the whole file -- from the Stop gate, so it blocked every
    # turn-stop, with the criteria already correct and nothing honest to change.
    expect_clean(
        "a `## Notes` bullet naming two AC ids is prose, not a criterion",
        GOOD + "\n## Notes\n\n- `check_authorization` forces every `Admin::` action to call "
        "`authorize!`; a content action that forgot would raise `AuthorizationNotPerformed` -- so "
        "AC-1/AC-2 passing also proves the pipeline is wired.\n",
    )
    # A criterion may REFERENCE another in its own text. Only the bolded id defines.
    expect_clean(
        "a criterion referencing another criterion in its text",
        "## Sign-in\n"
        "- **AC-1** Given a registered user, when they submit valid credentials, then the "
        "dashboard loads\n"
        "- **AC-2** Given AC-1 has passed, when the session expires, then the page shows a "
        "sign-in prompt [error]\n",
    )
    # THE DANGEROUS DIRECTION. A line that is clearly TRYING to be a criterion must not be skipped
    # silently -- losing a real criterion is worse than the false positive this fixes.
    expect_unusable(
        "a Given/When/Then line whose id does not lead is reported, not dropped",
        "## Sign-in\n- **AC-1** Given a user, when they submit, then it loads\n"
        "- Given a locked account, when they submit, then it is refused (AC-2)\n",
        contains="does not lead the line",
    )
    # ...and the non-bold leading form keeps the strict rule, because with no marker there is
    # nothing to tell a definition from a reference.
    expect_unusable(
        "two ids on a non-bold definition line still fails",
        "## Sign-in\n- AC-1 and AC-2 Given a user, when they submit, then it loads\n",
        contains="one criterion per line",
    )

    _tick()
    try:
        cc.parse(Path(rf_tmp.mkdtemp("railsflow-criteria-")) / "absent.md")
        FAILURES.append("missing file: expected UNUSABLE")
    except cc.Unusable as exc:
        if "no such file" not in str(exc):
            FAILURES.append(f"missing file: unexpected message: {exc}")

    # ---- the 1:1 mapping check --------------------------------------------------------
    spec_root = Path(rf_tmp.mkdtemp("railsflow-spec-")) / "spec" / "requests"
    spec_root.mkdir(parents=True)
    (spec_root / "sign_in_spec.rb").write_text(
        'RSpec.describe "sign in" do\n'
        '  it "AC-1 lands on the dashboard" do\n  end\n'
        '  it "AC-2 rejects a wrong password" do\n  end\nend\n',
        encoding="utf-8",
    )
    specs = spec_root.parent.parent
    expect_clean("every criterion cited by a spec", GOOD, specs=specs)
    expect_findings(
        "a criterion no spec cites",
        GOOD + "## Invoices\n- **AC-3** Given no line items, when POST /invoices runs, then the "
        "response is 422 and an error message appears [error]\n",
        contains="no spec under",
        specs=specs,
    )
    expect_findings(
        "a missing spec root must fail closed, not pass silently",
        GOOD,
        contains="does not exist",
        specs=Path(rf_tmp.mkdtemp("railsflow-nospec-")) / "absent",
    )

    # ---- [security] criteria against the threat model (#2118) ---------------------------------
    rows = [(1, "Forged callback", "mitigate"), (2, "Replay", "accept"), (3, "Leaked body", "mitigate")]
    sec = (
        "## Webhook\n"
        "- **AC-1** Given a callback with a bad signature, when it posts to the webhook, then the response is 401 and no contract changes [error] [security] (TM-1)\n"
        "- **AC-2** Given a signed callback, when the log is written, then the body is filtered from the log line [security] covers: TM-3\n"
    )
    def sec_check(label, body, want_rows, contains):
        _tick()
        try:
            found = cc.check(cc.parse(_write(body)), None, want_rows)
        except cc.Unusable as exc:
            FAILURES.append(f"{label}: UNUSABLE ({exc})")
            return
        blob = " | ".join(found)
        if contains is None and found:
            FAILURES.append(f"{label}: expected clean, got {found}")
        if contains is not None and contains.lower() not in blob.lower():
            FAILURES.append(f"{label}: expected {contains!r}, got {found}")
    sec_check("every mitigate row cited by a [security] criterion is clean", sec, rows, None)
    sec_check("a mitigate row no [security] criterion cites is a finding", sec.replace(" covers: TM-3", ""), rows, "TM-3")
    sec_check("a model with mitigate rows and no [security] criterion is a finding", GOOD, rows, "no [security] criterion cites it")
    sec_check("a [security] criterion citing no row is a finding", sec.replace(" (TM-1)", ""), rows, "cites no threat-model row")
    sec_check("a [security] criterion citing a row that does not exist is a finding", sec.replace("(TM-1)", "(TM-9)"), rows, "not a row of the threat model")
    sec_check("a [security] criterion citing an accept row is a finding", sec.replace("(TM-1)", "(TM-2)"), rows, "not a `mitigate` row")
    def sec_refused(label, body, needle):
        _tick()
        try:
            found = cc.check(cc.parse(_write(body)), None, rows)
        except cc.Unusable as exc:
            if needle.lower() not in str(exc).lower():
                FAILURES.append(f"{label}: refused, but not naming {needle!r}: {exc}")
            return
        FAILURES.append(f"{label}: expected UNUSABLE naming {needle!r}, got {found}")
    # STRICT (#2213 adversary): a shape outside the one we read is refused, never interpreted.
    sec_refused("a tag and a citation inside an html comment are refused", sec.replace("[security] (TM-1)", "<!-- [security] (TM-1) -->"), "no HTML comments")
    sec_refused("a citation inside an html comment is refused", sec.replace("[security] (TM-1)", "[security] <!-- (TM-1) -->"), "no HTML comments")
    sec_check("a citation inside a code span does not count", sec.replace("[security] (TM-1)", "[security] `(TM-1)`"), rows, "cites no threat-model row")
    sec_check("a mention mid-sentence is not a citation", sec.replace("[security] (TM-1)", "[security] (unlike TM-1 this one is fine)"), rows, "cites no threat-model row")
    sec_check("a citation followed by more words is not in the slot", sec.replace("(TM-1)", "(TM-1) and more words follow"), rows, "cites no threat-model row")
    sec_refused("a trailing html comment is refused", sec.replace("(TM-1)", "(TM-1) <!-- reviewed -->"), "no HTML comments")
    sec_check("a list of ids in the slot cites each", sec.replace("[security] (TM-1)", "[security] (TM-1, TM-3)"), rows, None)
    # an existing model with no readable table is exit 2, never 0
    import tempfile as _t
    d = Path(rf_tmp.mkdtemp("railsflow-model-"))
    (d / "ac.md").write_text(sec, encoding="utf-8")
    (d / "bad-model.md").write_text("# not a model\n", encoding="utf-8")
    (d / "old-model.md").write_text("## Threats\n| Threat | STRIDE | Component | Decision | Reason |\n|---|---|---|---|---|\n| x | S | y | mitigate | z |\n", encoding="utf-8")
    (d / "empty-model.md").write_text("# T\n## What we are building\nA hook.\n## Trust boundaries\n- a -> b: c\n## Threats\n"
                                      "| ID | Threat | STRIDE | Component | Decision | Reason |\n|---|---|---|---|---|---|\n"
                                      "## Security requirements\n- verify the body\n", encoding="utf-8")
    for label, mf in (("a model with no table is exit 2", "bad-model.md"), ("a model without the ID column is exit 2", "old-model.md"),
                      ("a complete model whose table has no rows is exit 2", "empty-model.md")):
        _tick()
        got = cc.main([str(d / "ac.md"), "--threat-model", str(d / mf)])
        if got != 2:
            FAILURES.append(f"{label}: expected exit 2, got {got}")
    # The default model is found from the repository root, wherever the criteria file sits (#2213 review), and a miss is said.
    import contextlib, io
    repo = Path(rf_tmp.mkdtemp("railsflow-repo-"))
    (repo / ".git").mkdir()
    deep = repo / "docs" / "product" / "acceptance" / "2026"
    deep.mkdir(parents=True)
    (deep / "unit.md").write_text(GOOD, encoding="utf-8")
    (repo / "docs" / "security" / "threat-models").mkdir(parents=True)
    (repo / "docs" / "security" / "threat-models" / "unit.md").write_text(
        "# T\n## What we are building\nA webhook.\n## Trust boundaries\n- partner -> app: the body\n"
        "## Threats\n| ID | Threat | STRIDE | Component | Decision | Reason |\n|---|---|---|---|---|---|\n| TM-1 | Forged | S | hook | mitigate | sig checked |\n"
        "## Security requirements\n- verify the signature\n", encoding="utf-8")
    (deep / "other.md").write_text(GOOD, encoding="utf-8")
    for label, name, want, needle in (
            ("a criteria file deeper than docs/product/acceptance still finds its model at the repo root", "unit.md", 1, ""),
            ("no model found says the security check was skipped", "other.md", 0, "security check skipped"),
            ("a skip names the other models in the directory", "other.md", 0, "1 other model(s) there: unit.md")):
        _tick()
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            got = cc.main([str(deep / name)])
        if got != want or needle not in err.getvalue():
            FAILURES.append(f"{label}: expected exit {want} naming {needle!r}, got {got}: {err.getvalue()[:200]}")
    # A row the reader cannot parse refuses the model instead of dropping its requirement (#2213 adversary).
    head = "## Threats\n| ID | Threat | STRIDE | Component | Decision | Reason |\n|---|---|---|---|---|---|\n| TM-1 | Forged | S | hook | mitigate | sig |\n"
    for label, row in (("a bolded ID", "| **TM-3** | Leak | I | log | mitigate | filter |"),
                       ("a suffixed ID", "| TM-3a | Leak | I | log | mitigate | filter |"),
                       ("a Cyrillic ID", "| \u0422\u041c-3 | Leak | I | log | mitigate | filter |"),
                       ("a non-breaking hyphen ID", "| TM\u20113 | Leak | I | log | mitigate | filter |"),
                       ("a blank ID", "|  | Leak | I | log | mitigate | filter |"),
                       ("a bolded decision", "| TM-3 | Leak | I | log | **mitigate** | filter |"),
                       ("a past-tense decision", "| TM-3 | Leak | I | log | Mitigated | filter |"),
                       ("a qualified decision", "| TM-3 | Leak | I | log | mitigate (partial) | filter |"),
                       ("a blank decision", "| TM-3 | Leak | I | log |  | filter |")):
        _tick()
        mf = d / "malformed.md"
        mf.write_text(head + row + "\n", encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            got = cc.main([str(d / "ac.md"), "--threat-model", str(mf)])
        if got != 2 or "cannot trust" not in err.getvalue():
            FAILURES.append(f"a model row with {label} is refused, not dropped: expected exit 2, got {got}: {err.getvalue()[:200]}")
    # A criterion inside a multi-line comment or a fenced block is not live, so it cites nothing (#2213 adversary).
    ac2 = "- **AC-2** Given a signed callback, when the log is written, then the body is filtered from the log line [security] covers: TM-3\n"
    sec_refused("a criterion inside a multi-line comment is refused", sec.replace(ac2, "<!--\n" + ac2 + "-->\n"), "no HTML comments")
    sec_refused("a criterion inside an unclosed comment is refused", sec.replace(ac2, "<!-- draft\n" + ac2), "no HTML comments")
    sec_refused("`<!--` inside a code span is refused too", sec.replace("then the response", "then `<!--` the response"), "no HTML comments")
    sec_refused("a fence closed with text after its marker is refused", sec.replace(ac2, "```\nx\n``` done\n" + ac2), "only its marker")
    sec_refused("a fence that never closes is refused", sec.replace(ac2, "````\n" + ac2 + "```\n"), "never closes")
    sec_refused("a criterion indented as code is refused", sec.replace(ac2, "\n    " + ac2), "indented four spaces")
    sec_refused("a criterion tab-indented as code is refused", sec.replace(ac2, "\n\t" + ac2), "indented four spaces")
    sec_check("a criterion inside a backtick fence does not cite", sec.replace(ac2, "```\n" + ac2 + "```\n"), rows, "TM-3")
    sec_check("a criterion inside a tilde fence does not cite", sec.replace(ac2, "~~~md\n" + ac2 + "~~~\n"), rows, "TM-3")
    sec_check("a tag inside a code span is not a tag", sec.replace("[security] (TM-1)", "`[security]` (TM-1)"), rows, "TM-1")
    sec_check("a criterion after a closed fence still cites", sec.replace(ac2, "```\nx\n```\n" + ac2), rows, None)
    sec_refused("an indented fence is refused", sec.replace(ac2, "  ```\nx\n  ```\n" + ac2), "start of its line")
    # The adversary's own inputs (#2213, pass 2), replayed end to end through main(): each is refused unless its record says why it passes.
    import json as _json
    corpus = _json.loads((Path(__file__).resolve().parent / "fixtures" / "security-adversary-2213.json").read_text(encoding="utf-8"))
    for case in corpus:
        _tick()
        root = Path(rf_tmp.mkdtemp("railsflow-adv-"))
        (root / ".git").mkdir()
        (root / "docs" / "product" / "acceptance").mkdir(parents=True)
        (root / "docs" / "security" / "threat-models").mkdir(parents=True)
        (root / "docs" / "product" / "acceptance" / "x.md").write_text(case["criteria"], encoding="utf-8")
        (root / "docs" / "security" / "threat-models" / case["model_name"]).write_text(case["model"], encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            got = cc.main([str(root / "docs" / "product" / "acceptance" / "x.md")])
        if "passes" in case and got != 0:
            FAILURES.append(f"adversary input `{case['name']}` should pass ({case['passes']}), got exit {got}: {err.getvalue()[:160]}")
        elif "passes" not in case and got == 0:
            FAILURES.append(f"adversary input `{case['name']}` got through (exit 0)")
        elif "refused_with" in case and (got != 2 or case["refused_with"] not in err.getvalue()):
            FAILURES.append(f"adversary input `{case['name']}` must be refused naming {case['refused_with']!r}, got exit {got}: {err.getvalue()[:160]}")
    sec_check("a model with only accept rows asks for nothing", GOOD, [(1, "Replay", "accept")], None)
    sec_check("no model, no security rule", GOOD, [], None)

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for f in FAILURES:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"check_criteria selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
