#!/usr/bin/env python3
"""Prove every work-order rule fires -- and, harder, that it stays silent on a good work order.

Run:  python3 check_handoff.py --selftest   (or execute this file directly)

The silent direction decides whether this survives. A work order is ordinary prose about files,
tests and stop conditions, and three of the rules read exactly the vocabulary that prose is made of:

  * `<...>` is a placeholder in a template AND an HTML tag in a quoted view snippet.
  * "above" is a reference to the conversation AND a reference to the table three lines up.
  * `TODO` is an unresolved decision AND part of `app/models/todo.rb`.

A rule that flags the second of each pair teaches authors to stop quoting snippets, stop
cross-referencing, and rename their models -- so the near-miss fixtures below are the point, and
each carve-out (inline code stripped, fenced blocks skipped, case-sensitive `TODO`, no bare
"above") has one pinned here. Two of them caught real bugs in the first draft: `### Interface`
collected the in-scope list because `in` was matched as a substring, and a work order quoting
`<turbo-frame>` inside a fence was rejected as an unresolved template.

The last two checks run the REAL shipped tier table against the REAL shipped agents. Everything
else here is a fixture, and a fixture cannot notice that the ten files we actually ship have
drifted from the table that documents them -- which is the defect #127 reported.

Costs nothing: no network, no Rails, no bundler.
"""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_handoff as ch  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
TICK = "`" * 3

GOAL = """## Goal
Clinic staff cannot see what an appointment will cost until after it is billed, so they quote
prices from memory and get them wrong. This unit shows the total on the appointment page before
billing, from the same calculation the invoice uses.
"""

CRITERIA = """## Acceptance criteria
Graded by `docs/acceptance/invoice-totals.md`: AC-1 (the footer total), AC-2 (the 422 path).
Nothing here supersedes that file.
"""

SCOPE = """## Scope
### In
- `app/models/invoice.rb`
- `app/views/appointments/show.html.erb`
- `spec/models/invoice_spec.rb`
### Out
- `app/models/account.rb` — tenancy lives there and a change needs its own criteria
- `db/migrate/` — no schema change in this unit
"""

GUARDRAILS = """## Guardrails
`GUARDRAILS.md` in full. The ones this unit brushes against: every query clinic-scoped, no
`Invoice.find(params[:id])` without a scope, 422 on invalid and 303 after a mutation.
"""

STOP = """## Stop conditions
- **Attempt cap: 3** per criterion. On the third failure stop and write the diagnosis.
- **No progress:** 2 consecutive runs with an identical failure signature is a stop, not a retry.
- **Blast radius: 10 files**, and never a file outside In.
- **Forbidden — these end the run:** weakening or deleting a failing spec to make it pass;
  reverting a task that already passed to unblock this one; editing a file outside the declared
  scope; disabling a guardrail or hook.
- **Budget:** stop at 2 hours or 300k tokens and report the remainder.
- On a stop, write the diagnosis and continue with unrelated criteria. Never report a partial run
  as complete.
"""

VERIFY = """## Verify
1. `bundle exec rspec spec/models/invoice_spec.rb` — 0 failures.
2. Open /appointments/1 and read the footer total.
3. `bundle exec rspec` — full suite, 0 failures.
"""

EXECUTOR = """## Executor
Tier: judgement (`model: inherit`) — the change touches tenancy-scoped queries, so a wrong call
here is a data leak rather than a failed spec.
"""

DONE = """## On completion
Note the PR number here, update `docs/brain/STATUS.md`, and record the rounding choice in
`docs/brain/DECISIONS.md` as a `D-nnn` with its trade-off.
"""

GOOD = "# Work order — invoice-totals\n\n" + "\n".join(
    (GOAL, CRITERIA, SCOPE, GUARDRAILS, STOP, VERIFY, EXECUTOR, DONE)
)


def _tick() -> None:
    global CHECKS
    CHECKS += 1


def _write(body: str, name: str = "invoice-totals.md") -> Path:
    root = Path(tempfile.mkdtemp(prefix="railsflow-handoff-"))
    path = root / name
    path.write_text(body, encoding="utf-8")
    return path


def _criteria_file(body: str | None = None) -> Path:
    root = Path(tempfile.mkdtemp(prefix="railsflow-criteria-"))
    path = root / "invoice-totals.md"
    path.write_text(
        body if body is not None else (
            "## Invoice totals\n"
            "- **AC-1** Given an invoice with two line items, when the user opens the appointment "
            "page, then the footer shows the summed amount formatted as currency\n"
            "- **AC-2** Given an invoice with no line items, when POST /invoices runs, then the "
            "response is 422 and the modal re-renders with \"must have at least one line "
            "item\" [error]\n"
        ),
        encoding="utf-8",
    )
    return path


def swap(section: str, replacement: str) -> str:
    """The good work order with one section replaced -- so every fixture differs by one thing."""
    assert section in GOOD, f"fixture drift: {section[:40]!r} is not in GOOD"
    return GOOD.replace(section, replacement)


def drop(section: str) -> str:
    return swap(section, "")


def expect_clean(label: str, body: str, *, criteria: Path | None = None) -> None:
    _tick()
    try:
        findings = ch.check(ch.parse(_write(body)), criteria)
    except ch.Unusable as exc:
        FAILURES.append(f"{label}: expected clean, got UNUSABLE ({exc})")
        return
    if findings:
        FAILURES.append(f"{label}: expected clean, got {len(findings)}: {findings}")


def expect_findings(label: str, body: str, *, contains: str, criteria: Path | None = None) -> None:
    _tick()
    try:
        findings = ch.check(ch.parse(_write(body)), criteria)
    except ch.Unusable as exc:
        FAILURES.append(f"{label}: expected findings, got UNUSABLE ({exc})")
        return
    if not findings:
        FAILURES.append(f"{label}: expected findings, got clean")
        return
    blob = " | ".join(findings)
    if contains.lower() not in blob.lower():
        FAILURES.append(f"{label}: findings omit {contains!r}: {blob}")


def expect_unusable(label: str, body: str, *, contains: str) -> None:
    _tick()
    try:
        ch.parse(_write(body))
    except ch.Unusable as exc:
        if contains.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: message omits {contains!r}: {exc}")
        return
    FAILURES.append(f"{label}: expected UNUSABLE, input was accepted")


# ---- tier-mode helpers ---------------------------------------------------------------------

TIER_HEAD = "| Agent | Tier | `model:` | What proves its output |\n|---|---|---|---|\n"


def tiers_doc(rows: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="railsflow-tiers-"))
    path = root / "model-tiers.md"
    path.write_text(
        f"# Tiers\n\nprose\n\n{ch.TIERS_BEGIN}\n{TIER_HEAD}{rows}{ch.TIERS_END}\n", encoding="utf-8"
    )
    return path


def agents_dir(agents: dict[str, str | None]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="railsflow-agents-")) / "agents"
    root.mkdir(parents=True)
    for name, model in agents.items():
        model_line = f"model: {model}\n" if model is not None else ""
        (root / f"{name}.md").write_text(
            f"---\nname: {name}\ndescription: >\n  Does a thing.\ntools: Read\n{model_line}---\n\n"
            "Body.\n",
            encoding="utf-8",
        )
    return root


def expect_tiers_clean(label: str, tiers: Path, agents: Path | None = None) -> None:
    _tick()
    try:
        rows = ch.parse_tiers(tiers)
        loaded = ch.agent_models(agents) if agents else None
        findings = ch.check_tiers(rows, loaded)
    except ch.Unusable as exc:
        FAILURES.append(f"{label}: expected clean, got UNUSABLE ({exc})")
        return
    if findings:
        FAILURES.append(f"{label}: expected clean, got {len(findings)}: {findings}")


def expect_tiers_findings(label: str, tiers: Path, agents: Path | None, *, contains: str) -> None:
    _tick()
    try:
        rows = ch.parse_tiers(tiers)
        loaded = ch.agent_models(agents) if agents else None
        findings = ch.check_tiers(rows, loaded)
    except ch.Unusable as exc:
        FAILURES.append(f"{label}: expected findings, got UNUSABLE ({exc})")
        return
    if not findings:
        FAILURES.append(f"{label}: expected findings, got clean")
        return
    blob = " | ".join(findings)
    if contains.lower() not in blob.lower():
        FAILURES.append(f"{label}: findings omit {contains!r}: {blob}")


def run() -> int:  # noqa: PLR0915 -- a flat list of fixtures reads better than nested helpers
    log = _criteria_file()

    # ---- the silence proof ---------------------------------------------------------------
    expect_clean("a well-formed work order", GOOD)
    expect_clean("...and with the criteria file present", GOOD, criteria=log)

    # ---- unusable: this is not a work order ----------------------------------------------
    expect_unusable(
        "a file with no sections at all",
        "# Work order\n\nSome prose and nothing else.\n",
        contains="carries no `## ` sections",
    )
    expect_unusable(
        "sections, but not one of the eight",
        "## Notes\n\nprose\n\n## Links\n\nmore prose\n",
        contains="this is not a work order",
    )
    _tick()
    try:
        ch.parse(Path(tempfile.mkdtemp(prefix="railsflow-handoff-")) / "absent.md")
        FAILURES.append("missing file: expected UNUSABLE")
    except ch.Unusable as exc:
        if "no such file" not in str(exc):
            FAILURES.append(f"missing file: unexpected message: {exc}")

    # ---- every required section is required ----------------------------------------------
    for label, section in (
        ("goal", GOAL), ("acceptance criteria", CRITERIA), ("scope", SCOPE),
        ("guardrails", GUARDRAILS), ("stop conditions", STOP), ("verify", VERIFY),
        ("executor", EXECUTOR), ("on completion", DONE),
    ):
        expect_findings(
            f"a work order with no {label!r} section", drop(section),
            contains=f"no `## {label}` section",
        )

    # ---- scope: in AND out, and the boundary has to be nameable --------------------------
    expect_findings(
        "scope with nothing declared out",
        swap(SCOPE, "## Scope\n### In\n- `app/models/invoice.rb`\n"),
        contains="nothing is declared OUT of scope",
    )
    expect_findings(
        "scope with nothing declared in",
        swap(SCOPE, "## Scope\n### Out\n- `app/models/account.rb` — tenancy\n"),
        contains="nothing is declared IN scope",
    )
    expect_findings(
        "an in-scope entry naming no file",
        swap(SCOPE, "## Scope\n### In\n- the invoice code\n### Out\n- everything else\n"),
        contains="no in-scope entry names a file",
    )
    expect_clean(
        "`db/migrate/` counts as a path even with no extension",
        swap(SCOPE, "## Scope\n### In\n- `db/migrate/`\n### Out\n- `app/` — no app change\n"),
    )
    expect_clean(
        "the Included/Excluded aliases are accepted",
        swap(SCOPE, "## Scope\n### Included\n- `app/models/invoice.rb`\n### Excluded\n"
                    "- `app/models/account.rb` — tenancy\n"),
    )
    expect_findings(
        "`### Interface` is not the in-scope list (`in` matched as a substring)",
        swap(SCOPE, "## Scope\n### Interface\n- `app/models/invoice.rb`\n### Out\n- `db/`\n"),
        contains="nothing is declared IN scope",
    )
    expect_clean(
        "a lowercase todo.rb is a filename, not an unresolved decision",
        swap(SCOPE, "## Scope\n### In\n- `app/models/todo.rb`\n### Out\n- `app/models/account.rb`"
                    " — tenancy\n"),
    )
    expect_clean(
        # The backticked path above passes because inline code is stripped, so it does NOT pin the
        # case-sensitivity of the unresolved-token rule. This does: the same word in bare prose.
        # Without it, making the rule case-insensitive breaks nothing any fixture watches.
        "the word todo in prose is not an unresolved decision either",
        swap(DONE, DONE.rstrip() + "\nTick the invoice item off the team's todo list.\n"),
    )

    # ---- stop conditions: a number, or it cannot be evaluated ----------------------------
    expect_findings(
        "stop conditions with no numeric attempt cap",
        swap(STOP, STOP.replace("**Attempt cap: 3** per criterion. On the third failure stop and "
                                "write the diagnosis.", "Stop when you are stuck.")),
        contains="no numeric attempt cap",
    )
    expect_findings(
        "stop conditions with no no-progress detector",
        swap(STOP, STOP.replace(
            "- **No progress:** 2 consecutive runs with an identical failure signature is a stop, "
            "not a retry.\n", "")),
        contains="no numeric no-progress detector",
    )
    expect_findings(
        "stop conditions with no blast-radius cap",
        swap(STOP, STOP.replace(
            "- **Blast radius: 10 files**, and never a file outside In.\n",
            "- Do not wander outside the declared scope.\n")),
        contains="no numeric blast-radius cap",
    )
    expect_findings(
        "stop conditions with no budget",
        swap(STOP, STOP.replace(
            "- **Budget:** stop at 2 hours or 300k tokens and report the remainder.\n", "")),
        contains="no numeric budget",
    )
    for escape, edits in (
        ("weakening or deleting a failing test",
         (("weakening or deleting a failing spec to make it pass;", "being careless;"),)),
        ("reverting a passing task to unblock this one",
         (("reverting a task that already passed to unblock this one;", "cutting corners;"),)),
        # BOTH scope mentions have to go. The blast-radius bullet ("never a file outside In")
        # genuinely forbids scope creep as well, so removing only the escape bullet left the rule
        # correctly satisfied and the fixture proved nothing -- it looked like a caught escape.
        ("expanding scope beyond the declared files",
         (("editing a file outside the declared\n  scope;", "guessing;"),
          ("- **Blast radius: 10 files**, and never a file outside In.\n",
           "- **Blast radius: 10 files** at most.\n"))),
        ("disabling a guardrail or hook", (("disabling a guardrail or hook.", "rushing."),)),
    ):
        broken = STOP
        for removed, replacement in edits:
            assert removed in broken, f"fixture drift: {removed[:40]!r} is not in STOP"
            broken = broken.replace(removed, replacement)
        expect_findings(
            f"the escapes do not forbid {escape}",
            swap(STOP, broken),
            contains=f"do not cover {escape}",
        )

    # ---- verify: every step names something runnable -------------------------------------
    expect_findings(
        "a verify section with no steps",
        swap(VERIFY, "## Verify\nRun the suite and check the page.\n"),
        contains="lists no steps",
    )
    expect_findings(
        "a verify step naming no command",
        swap(VERIFY, "## Verify\n1. Confirm the total is right and/or the footer updates.\n"),
        contains="names no command or path",
    )
    expect_clean(
        "a bare route counts as runnable",
        swap(VERIFY, "## Verify\n1. Open /appointments/1 and read the footer total.\n"),
    )

    # ---- criteria: cite, never restate; and the ids must resolve -------------------------
    expect_findings(
        "an acceptance section citing no id",
        swap(CRITERIA, "## Acceptance criteria\nThe totals must be right.\n"),
        contains="cites no `AC-n` id",
    )
    expect_findings(
        "an acceptance section restating a criterion",
        swap(CRITERIA, "## Acceptance criteria\n- **AC-1** Given two line items, when the user "
                       "opens the page, then the footer shows the total\n"),
        contains="restates a criterion",
    )
    expect_findings(
        "a cited id the criteria file does not define",
        swap(CRITERIA, "## Acceptance criteria\nGraded by `docs/acceptance/invoice-totals.md`: "
                       "AC-1, AC-7.\n"),
        contains="cites AC-7",
        criteria=log,
    )
    expect_findings(
        "the criteria file does not exist",
        GOOD,
        contains="does not exist",
        criteria=Path(tempfile.mkdtemp(prefix="railsflow-nocrit-")) / "invoice-totals.md",
    )
    expect_findings(
        "a cheap-tier executor with no criteria file has no external proof",
        swap(EXECUTOR, "## Executor\nTier: mechanical (`model: haiku`) — the suite grades it.\n"),
        contains="external",
        criteria=Path(tempfile.mkdtemp(prefix="railsflow-nocrit-")) / "invoice-totals.md",
    )
    expect_findings(
        "a criteria file with no criteria in it",
        GOOD,
        contains="cannot be read as criteria",
        criteria=_criteria_file("## Invoice totals\n\nWe will make the totals correct.\n"),
    )

    # An unreachable failure path is the one that is wrong when it finally runs, so the
    # criteria-parser-absent branch is exercised through the seam rather than left to hope. It must
    # produce a FINDING: "could not check" reported as clean is a skip masquerading as a pass.
    _tick()
    original = ch._criteria_parser
    ch._criteria_parser = lambda: None
    try:
        without = ch.check(ch.parse(_write(GOOD)), log)
    finally:
        ch._criteria_parser = original
    if not any("UNVERIFIED, not satisfied" in f for f in without):
        FAILURES.append(
            "with check_criteria.py absent the ids cannot be resolved, and that has to be a "
            f"finding rather than a clean pass; got: {without}"
        )

    # ---- self-containment: the promise that makes the file worth writing ----------------
    for phrase in (
        "Use the rounding rule as we discussed.",
        "Scope is what you mentioned at the start.",
        "Follow the plan I described in our conversation.",
        "Keep the approach from the previous message.",
        "Per our earlier decision, skip the mailer.",
    ):
        expect_findings(
            f"a work order pointing at the conversation: {phrase[:34]!r}",
            swap(GOAL, GOAL.rstrip() + f"\n{phrase}\n"),
            contains="points at the conversation",
        )
    expect_clean(
        "document-internal references must pass -- `above` is not `as we discussed`",
        swap(GOAL, GOAL.rstrip() + "\nThe scope table below is exhaustive; the goal above is the "
                                   "only paragraph anyone needs to read first.\n"),
    )
    expect_findings(
        "an unresolved placeholder",
        swap(GOAL, GOAL.rstrip() + "\nThe slug is <slug> and the owner is <name>.\n"),
        contains="unresolved placeholder",
    )
    expect_clean(
        "a backticked HTML tag is code, not a placeholder",
        swap(GOAL, GOAL.rstrip() + "\nThe footer renders inside `<turbo-frame id=\"total\">`.\n"),
    )
    expect_clean(
        "a fenced snippet holding a tag is code, not a placeholder",
        swap(GOAL, GOAL.rstrip() + f"\n\n{TICK}erb\n<turbo-frame id=\"total\">\n  <%= t %>\n"
                                   f"</turbo-frame>\n{TICK}\n"),
    )
    for token in ("TBD", "TODO", "FIXME"):
        expect_findings(
            f"{token} left in the work order",
            swap(DONE, DONE.rstrip() + f"\nRounding rule: {token}.\n"),
            contains=f"{token} left in the work order",
        )

    # ---- executor: the tier and its model are one decision ------------------------------
    expect_findings(
        "an executor section naming no tier",
        swap(EXECUTOR, "## Executor\nWhoever picks this up.\n"),
        contains="names no tier",
    )
    expect_findings(
        "an executor section naming two tiers",
        swap(EXECUTOR, "## Executor\nTier: judgement, or mechanical if the suite is green.\n"),
        contains="names 2 tiers",
    )
    expect_findings(
        "a tier named without its model",
        swap(EXECUTOR, "## Executor\nTier: judgement — it needs real judgement.\n"),
        contains="does not state `model: inherit`",
    )
    expect_findings(
        "an executor pinned above the session",
        swap(EXECUTOR, "## Executor\nTier: judgement (`model: opus`) — use the best available.\n"),
        contains="more expensive model than the session",
    )
    expect_clean(
        "the US spelling of judgement is accepted",
        swap(EXECUTOR, "## Executor\nTier: judgment (`model: inherit`) — tenancy is in play.\n"),
    )
    expect_clean(
        "a mechanical executor with its criteria file present",
        swap(EXECUTOR, "## Executor\nTier: mechanical (`model: haiku`) — graded by the suite.\n"),
        criteria=log,
    )

    # ---- tier mode: the table itself ----------------------------------------------------
    ok_rows = (
        "| `code-reviewer` | judgement | `inherit` | — |\n"
        "| `test-runner` | mechanical | `haiku` | `bundle exec rspec` exit status |\n"
    )
    ok_agents = agents_dir({"code-reviewer": "inherit", "test-runner": "haiku"})
    expect_tiers_clean("a table that agrees with its agents", tiers_doc(ok_rows), ok_agents)
    expect_tiers_clean("...and the table alone, with no agents to reconcile", tiers_doc(ok_rows))

    _tick()
    try:
        ch.parse_tiers(_write("# Tiers\n\n| a | b | c | d |\n", "model-tiers.md"))
        FAILURES.append("a table with no markers: expected UNUSABLE")
    except ch.Unusable as exc:
        if "no <!-- <plugin>:tiers:begin" not in str(exc):
            FAILURES.append(f"a table with no markers: unexpected message: {exc}")

    # #299: ANY plugin may own a tier table, so the marker carries the plugin's name and one checker
    # serves all of them. Three fixtures, because a parameterised marker that accepts anything is
    # worse than a hardcoded one: it would silently reconcile qa-flow's agents against design-flow's
    # table.
    _tick()
    rows = "| `x` | judgement | `inherit` | — |\n"
    head = "| Agent | Tier | `model:` | What proves its output |\n|---|---|---|---|\n"
    for plugin in ("qa-flow", "design-flow", "pipeline"):
        doc = _write(f"# T\n\n<!-- {plugin}:tiers:begin -->\n{head}{rows}"
                     f"<!-- {plugin}:tiers:end -->\n", f"{plugin}-tiers.md")
        try:
            got = ch.parse_tiers(doc)
            if [r.agent for r in got] != ["x"]:
                FAILURES.append(f"{plugin} marker: parsed {[r.agent for r in got]}, expected ['x']")
        except ch.Unusable as exc:
            FAILURES.append(f"{plugin} marker rejected, but any plugin may own a table: {exc}")

    # NEAR MISS: a HALF-RENAMED copy must be refused, not reconciled. This is the failure the
    # parameterisation creates and the hardcoded marker could not have: copy rails-flow's table into
    # qa-flow, rename the opening marker, forget the closing one, and without this check the rows
    # between them get reconciled against the wrong plugin's agents.
    _tick()
    spliced = _write("# T\n\n<!-- qa-flow:tiers:begin -->\n" + head + rows
                     + "<!-- rails-flow:tiers:end -->\n", "spliced-tiers.md")
    try:
        ch.parse_tiers(spliced)
        FAILURES.append("a half-renamed tiers block: expected UNUSABLE, got rows")
    except ch.Unusable as exc:
        if "half-renamed" not in str(exc):
            FAILURES.append(f"a half-renamed tiers block: unexpected message: {exc}")
    _tick()
    try:
        ch.parse_tiers(tiers_doc(""))
        FAILURES.append("an empty tiers block: expected UNUSABLE")
    except ch.Unusable as exc:
        if "no agent rows" not in str(exc):
            FAILURES.append(f"an empty tiers block: unexpected message: {exc}")
    _tick()
    try:
        empty = Path(tempfile.mkdtemp(prefix="railsflow-noagents-")) / "agents"
        empty.mkdir(parents=True)
        (empty / "readme.md").write_text("no frontmatter here\n", encoding="utf-8")
        ch.agent_models(empty)
        FAILURES.append("an agents dir with no definitions: expected UNUSABLE")
    except ch.Unusable as exc:
        if "no agent definitions" not in str(exc):
            FAILURES.append(f"an agents dir with no definitions: unexpected message: {exc}")
    _tick()
    try:
        ch.agent_models(Path(tempfile.mkdtemp(prefix="railsflow-noagents-")) / "absent")
        FAILURES.append("a missing agents dir: expected UNUSABLE")
    except ch.Unusable as exc:
        if "no such directory" not in str(exc):
            FAILURES.append(f"a missing agents dir: unexpected message: {exc}")
    _tick()
    crossed = _write(
        f"# Tiers\n\n{ch.TIERS_END}\n| `x` | judgement | `inherit` | — |\n{ch.TIERS_BEGIN}\n",
        "model-tiers.md",
    )
    try:
        ch.parse_tiers(crossed)
        FAILURES.append("crossed tier markers: expected UNUSABLE")
    except ch.Unusable as exc:
        if "precedes its begin marker" not in str(exc):
            FAILURES.append(f"crossed tier markers: unexpected message: {exc}")

    # ---- the modes have to refuse an unusable INVOCATION too, not only bad input --------
    for label, argv in (
        ("--agents with nothing to reconcile against", ["--agents", "some/dir"]),
        ("no path, no --tiers, no --selftest", []),
    ):
        _tick()
        try:
            # argparse writes its usage to stderr. Swallowed on purpose: a PASSING selftest whose
            # output contains "error:" is how people learn to skim gate logs.
            with contextlib.redirect_stderr(io.StringIO()):
                ch.main(argv)
            FAILURES.append(f"{label}: expected a usage error")
        except SystemExit as exc:
            if exc.code != 2:
                FAILURES.append(f"{label}: exited {exc.code}, expected 2")

    expect_tiers_findings(
        "a judgement agent pinned to a model (a pin is a cap)",
        tiers_doc("| `code-reviewer` | judgement | `sonnet` | — |\n"), None,
        contains="a pin is a cap",
    )
    expect_tiers_findings(
        "a row pinning a more expensive alias",
        tiers_doc("| `code-reviewer` | judgement | `opus` | — |\n"), None,
        contains="more expensive model than the user's session",
    )
    expect_tiers_findings(
        "a row pinning a full model id",
        tiers_doc("| `code-reviewer` | judgement | `claude-opus-5` | — |\n"), None,
        contains="full model id",
    )
    expect_tiers_findings(
        "a cheap-tier row naming no external proof",
        tiers_doc("| `test-runner` | mechanical | `haiku` | — |\n"), None,
        contains="names no external proof",
    )
    expect_tiers_findings(
        "a third tier invented in the table",
        tiers_doc("| `rails-developer` | mid | `sonnet` | criteria |\n"), None,
        contains="not one of",
    )
    expect_tiers_findings(
        "one agent listed twice",
        tiers_doc(ok_rows + "| `code-reviewer` | mechanical | `haiku` | a grep |\n"), None,
        contains="is listed twice",
    )

    # ---- tier mode: the table vs the agents --------------------------------------------
    expect_tiers_findings(
        "an agent whose frontmatter contradicts the table",
        tiers_doc(ok_rows), agents_dir({"code-reviewer": "sonnet", "test-runner": "haiku"}),
        contains="while the tier table",
    )
    expect_tiers_findings(
        "an agent with no `model:` at all -- silence is not a decision",
        tiers_doc(ok_rows), agents_dir({"code-reviewer": None, "test-runner": "haiku"}),
        contains="declares no `model:`",
    )
    expect_tiers_findings(
        "an agent missing from the table",
        tiers_doc("| `test-runner` | mechanical | `haiku` | the suite |\n"), ok_agents,
        contains="is not in the tier table",
    )
    expect_tiers_findings(
        "a stale row naming an agent that no longer exists",
        tiers_doc(ok_rows + "| `deleted-agent` | mechanical | `haiku` | a grep |\n"), ok_agents,
        contains="which no agent definition declares",
    )

    # ---- the two checks a fixture cannot make: the REAL table vs the REAL agents --------
    # These are the only reason this file can notice that the plugin we ship has drifted. If the
    # paths ever stop resolving, that is a FAILURE and not a skip -- a selftest reporting "all
    # passed" while silently checking nothing is the exact bug this repo's doctrine warns about.
    _tick()
    real_tiers = PLUGIN_ROOT / "reference" / "model-tiers.md"
    real_agents = PLUGIN_ROOT / "agents"
    if not real_tiers.is_file() or not real_agents.is_dir():
        FAILURES.append(
            f"the shipped tier table ({real_tiers}) or agents dir ({real_agents}) is missing -- "
            "this check cannot be skipped, it is the only one that sees the real files"
        )
    else:
        try:
            findings = ch.check_tiers(ch.parse_tiers(real_tiers), ch.agent_models(real_agents))
        except ch.Unusable as exc:
            FAILURES.append(f"the shipped tier table is unusable: {exc}")
        else:
            if findings:
                FAILURES.append(
                    "the shipped agents do not match the shipped tier table: " + " | ".join(findings)
                )
    # The template the command tells an agent to write must satisfy the checker that rejects it
    # otherwise. Its placeholders are deliberate, so this checks the CONTRACT -- the eight headings
    # -- rather than running the checker on it: a template whose headings drift from
    # REQUIRED_SECTIONS ships a work order that fails our own gate on the first run.
    _tick()
    handoff_cmd = PLUGIN_ROOT / "commands" / "handoff.md"
    if not handoff_cmd.is_file():
        FAILURES.append(f"{handoff_cmd} is missing -- the checker has no command that produces it")
    else:
        template = handoff_cmd.read_text(encoding="utf-8").lower()
        for label, aliases in ch.REQUIRED_SECTIONS:
            if not any(f"## {alias}" in template for alias in aliases):
                FAILURES.append(
                    f"{handoff_cmd} never shows a `## {label}` heading, but check_handoff.py "
                    "requires one -- the template and the checker disagree, and the template is "
                    "what an agent copies"
                )

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"check_handoff selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
