#!/usr/bin/env python3
"""Prove every guide rule fires -- and, harder, that it stays silent on correct mermaid.

Run:  python3 check_guide.py --selftest   (or execute this file directly)

The silent direction decides whether this survives, and more sharply than usual. Two of these
rules read mermaid, a syntax whose ordinary lines are dense in exactly the characters the rules
look for: every flowchart is full of brackets, and `end` appears in every correct diagram that
uses a subgraph -- including the three in this repo's own README. A rule that flags
`A["Bill (monthly)"]` teaches the author to DELETE the quotes that make it render, which is
worse than having no rule at all.

So the near-miss fixtures are the point, and two of them caught real bugs in the first draft:

  * `A-->B[Text]` was read as node id `A--` plus mermaid's asymmetric `>` shape, making the
    label `B[Text` -- a false positive on the most ordinary line in any flowchart.
  * `A["Bill (monthly)"]` stopped the non-greedy label match at the first `)`, so a correctly
    quoted label looked unquoted.

Fixtures are adversarial rather than realistic: a realistic guide exercises only the happy
path, which is the blind spot the rules are about.

Costs nothing: no network, no Rails, no bundler, no mermaid.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_guide as cg  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

TICK = "`" * 3


def sec(slug: str, body: str) -> str:
    return f"<!-- rails-flow:begin {slug} -->\n{body}\n<!-- rails-flow:end {slug} -->\n"


def mermaid(body: str) -> str:
    return f"{TICK}mermaid\n{body}\n{TICK}\n"


def fenced(lang: str, body: str) -> str:
    return f"{TICK}{lang}\n{body}\n{TICK}\n"


OVERVIEW = sec(
    "guide:overview",
    "## What this app is\n\n"
    "Clinics book appointments and get paid for them. Two things carry the whole system: an\n"
    "appointment can only be billed once it is finished, and every query is clinic-scoped.\n",
)

FLOW_OK = mermaid(
    "flowchart LR\n"
    '  subgraph web["Web"]\n'
    '    n1["POST /invoices"] --> n2["InvoicesController#create"]\n'
    "  end\n"
    '  n2 --> n3["Invoice (draft)"]\n'
    '  n3 --> n4["BillingJob"]\n'
)

AREA = sec(
    "guide:area:billing",
    "### Billing\n\n"
    "#### What it does\n\n"
    "Turns a finished appointment into an invoice the clinic can send.\n\n"
    "#### How it flows\n\n"
    + FLOW_OK
    + "\n#### Check it yourself\n\n"
    "1. Run `bin/rails runner 'puts Invoice.draft.count'` and note the number.\n"
    "2. Open /appointments and mark one finished; the number goes up by one.\n",
)

DECISIONS = sec(
    "guide:decisions",
    "## Why it is built this way\n\n"
    "We bill on completion rather than at booking (D-004). That costs us upfront cash flow and\n"
    "buys us never having to refund a no-show.\n",
)

GOOD = OVERVIEW + AREA + DECISIONS


def _tick() -> None:
    global CHECKS
    CHECKS += 1


def _write(body: str) -> Path:
    root = Path(tempfile.mkdtemp(prefix="railsflow-guide-"))
    path = root / "GUIDE.md"
    path.write_text(body, encoding="utf-8")
    return path


def _decisions_log() -> Path:
    root = Path(tempfile.mkdtemp(prefix="railsflow-decisions-"))
    path = root / "DECISIONS.md"
    path.write_text("# Decisions\n\n## D-004 — bill on completion\n", encoding="utf-8")
    return path


def expect_clean(label: str, body: str, *, decisions: Path | None = None) -> None:
    _tick()
    try:
        findings = cg.check(cg.parse(_write(body)), decisions)
    except cg.Unusable as exc:
        FAILURES.append(f"{label}: expected clean, got UNUSABLE ({exc})")
        return
    if findings:
        FAILURES.append(f"{label}: expected clean, got {len(findings)}: {findings}")


def expect_findings(label: str, body: str, *, contains: str, count: int | None = None,
                    decisions: Path | None = None) -> None:
    _tick()
    try:
        findings = cg.check(cg.parse(_write(body)), decisions)
    except cg.Unusable as exc:
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
        cg.parse(_write(body))
    except cg.Unusable as exc:
        if contains.lower() not in str(exc).lower():
            FAILURES.append(f"{label}: message omits {contains!r}: {exc}")
        return
    FAILURES.append(f"{label}: expected UNUSABLE, input was accepted")


def run() -> int:
    log = _decisions_log()

    # ---- the silence proof -------------------------------------------------------------
    expect_clean("a well-formed guide", GOOD)
    expect_clean("...and with the decisions log present", GOOD, decisions=log)

    # ---- markers: the idempotency promise ----------------------------------------------
    expect_unusable(
        "an unclosed section would swallow everything after it",
        "<!-- rails-flow:begin guide:overview -->\n## What this is\n",
        contains="never closed",
    )
    expect_unusable(
        "nested sections cannot be rewritten independently",
        "<!-- rails-flow:begin guide:overview -->\n"
        "<!-- rails-flow:begin guide:area:x -->\n## x\n"
        "<!-- rails-flow:end guide:area:x -->\n"
        "<!-- rails-flow:end guide:overview -->\n",
        contains="nested managed sections",
    )
    expect_unusable(
        "a duplicate slug makes the rewrite target ambiguous",
        OVERVIEW + OVERVIEW,
        contains="re-opens",
    )
    expect_unusable(
        "crossed markers",
        "<!-- rails-flow:begin guide:overview -->\n## x\n"
        "<!-- rails-flow:end guide:area:y -->\n",
        contains="crossed markers",
    )
    expect_unusable(
        "an end with no begin",
        "## Hand-written\n<!-- rails-flow:end guide:overview -->\n",
        contains="never opened",
    )
    expect_unusable(
        "begin and end on one line leaves no body to replace",
        "<!-- rails-flow:begin guide:overview --><!-- rails-flow:end guide:overview -->\n",
        contains="one line",
    )
    expect_unusable(
        "a hand-written file is not a managed guide",
        "# My guide\n\nSome prose with no markers at all.\n",
        contains="no `<!-- rails-flow:begin",
    )
    expect_unusable("an empty file", "", contains="no `<!-- rails-flow:begin")
    _tick()
    try:
        cg.parse(Path(tempfile.mkdtemp(prefix="railsflow-guide-")) / "absent.md")
        FAILURES.append("missing file: expected UNUSABLE")
    except cg.Unusable as exc:
        if "no such file" not in str(exc):
            FAILURES.append(f"missing file: unexpected message: {exc}")

    # ---- coverage: the four things the guide must answer -------------------------------
    expect_findings(
        "no overview section",
        AREA + DECISIONS,
        contains="no `guide:overview` section",
    )
    expect_findings(
        "no decisions section",
        OVERVIEW + AREA,
        contains="no `guide:decisions` section",
    )
    expect_findings(
        "no area at all",
        OVERVIEW + DECISIONS,
        contains="no `guide:area:",
    )
    expect_findings(
        "an area missing 'what it does'",
        OVERVIEW + DECISIONS + sec(
            "guide:area:billing",
            "### Billing\n\n#### How it flows\n\n" + FLOW_OK
            + "\n#### Check it yourself\n\n1. Run `bin/rails c`.\n",
        ),
        contains="'what it does' heading",
    )
    expect_findings(
        "an area missing 'how it flows'",
        OVERVIEW + DECISIONS + sec(
            "guide:area:billing",
            "### Billing\n\n#### What it does\n\nBills things.\n\n"
            "#### Check it yourself\n\n1. Run `bin/rails c`.\n",
        ),
        contains="'how it flows' heading",
    )
    expect_findings(
        "an area missing 'check it yourself' -- a tour, not an explanation",
        OVERVIEW + DECISIONS + sec(
            "guide:area:billing",
            "### Billing\n\n#### What it does\n\nBills things.\n\n#### How it flows\n\n" + FLOW_OK,
        ),
        contains="'check it yourself' heading",
    )
    expect_clean(
        "the heading aliases are accepted",
        OVERVIEW + DECISIONS + sec(
            "guide:area:billing",
            "### Billing\n\n#### What this does\n\nBills things.\n\n#### How it works\n\n"
            + FLOW_OK
            + "\n#### How to check it\n\n1. Run `bin/rails c`.\n",
        ),
    )

    # ---- a check step must name something runnable ------------------------------------
    expect_findings(
        "a check step naming no command",
        OVERVIEW + DECISIONS + sec(
            "guide:area:billing",
            "### Billing\n\n#### What it does\n\nBills things.\n\n#### How it flows\n\n"
            + FLOW_OK
            + "\n#### Check it yourself\n\n1. Confirm that billing works as expected.\n",
        ),
        contains="names no command, route or path",
    )
    expect_clean(
        "a bare route counts as runnable (no backticks needed)",
        OVERVIEW + DECISIONS + sec(
            "guide:area:billing",
            "### Billing\n\n#### What it does\n\nBills things.\n\n#### How it flows\n\n"
            + FLOW_OK
            + "\n#### Check it yourself\n\n1. Open /invoices and read the footer total.\n",
        ),
    )

    # ---- the guide must not become a second source of truth ---------------------------
    NO_CITE = OVERVIEW + AREA + sec(
        "guide:decisions",
        "## Why it is built this way\n\nWe bill on completion because refunds are expensive.\n",
    )
    expect_findings(
        "a decisions section citing no D-nnn while the log exists",
        NO_CITE, contains="cites no `D-nnn`", decisions=log,
    )
    expect_clean(
        "...and stays silent when the project has no decisions log",
        NO_CITE,
        decisions=Path(tempfile.mkdtemp(prefix="railsflow-nolog-")) / "DECISIONS.md",
    )

    # ---- mermaid: the ways a diagram silently fails to render -------------------------
    def with_diagram(block: str) -> str:
        return OVERVIEW + DECISIONS + sec(
            "guide:area:billing",
            "### Billing\n\n#### What it does\n\nBills things.\n\n#### How it flows\n\n"
            + block
            + "\n#### Check it yourself\n\n1. Run `bin/rails c`.\n",
        )

    expect_findings(
        "an unclosed fence renders the rest of the guide as code",
        with_diagram(f"{TICK}mermaid\nflowchart LR\n  a --> b"),
        contains="never closed",
    )
    expect_findings(
        "an empty mermaid block",
        with_diagram(mermaid("")),
        contains="empty mermaid block",
    )
    expect_findings(
        "a bare lowercase `end` closing no subgraph",
        with_diagram(mermaid('flowchart LR\n  n1["Start"] --> n2["Stop"]\n  end\n')),
        contains="closes no open `subgraph`",
    )
    expect_findings(
        "`end` used as a node in an edge",
        with_diagram(mermaid('flowchart LR\n  n1["Start"] --> end\n')),
        contains="`end` is used as a node",
    )
    expect_findings(
        "an unquoted label holding brackets",
        with_diagram(mermaid("flowchart LR\n  n1[Invoice (draft)] --> n2[Sent]\n")),
        contains="unquoted label containing",
    )
    expect_findings(
        "a deprecated init directive",
        with_diagram(mermaid(
            "%%{init: {'theme':'dark'}}%%\nflowchart LR\n  n1[\"a\"] --> n2[\"b\"]\n"
        )),
        contains="deprecated from mermaid v10.5.0",
    )
    expect_findings(
        "mermaid frontmatter, whose support GitHub does not document",
        with_diagram(mermaid('---\ntitle: Billing\n---\nflowchart LR\n  n1["a"] --> n2["b"]\n')),
        contains="frontmatter",
    )
    expect_findings(
        "a diagram type with no evidence GitHub renders it",
        with_diagram(mermaid("architecture-beta\n  group api(cloud)[API]\n")),
        contains="is not on the list",
    )

    # ---- mermaid near misses: correct diagrams MUST pass -------------------------------
    expect_clean(
        "nested subgraphs -- every `end` closes one (this repo's own README shape)",
        with_diagram(mermaid(
            "flowchart TB\n"
            '  subgraph outer["Outer"]\n'
            "    direction LR\n"
            '    subgraph inner["Inner"]\n'
            '      a1["a"] --> a2["b"]\n'
            "    end\n"
            '    a2 --> a3["c"]\n'
            "  end\n"
            '  a3 --> z1["done"]\n'
        )),
    )
    expect_clean(
        "`endpoint` is not `end`",
        with_diagram(mermaid('flowchart LR\n  endpoint["GET /health"] --> ok["200"]\n')),
    )
    expect_clean(
        "a capitalized End is the documented workaround",
        with_diagram(mermaid('flowchart LR\n  n1["Start"] --> End\n  End --> DONE\n')),
    )
    expect_clean(
        "a quoted label containing parentheses -- the whole point of quoting",
        with_diagram(mermaid('flowchart LR\n  n1["Invoice (draft)"] --> n2["Sent [final]"]\n')),
    )
    expect_clean(
        "an ordinary unquoted label with no risky characters",
        with_diagram(mermaid("flowchart LR\n  n1[Draft] --> n2[Sent]\n")),
    )
    expect_clean(
        "`A-->B[Text]` with no spaces does not parse as id `A--` plus the `>` shape",
        with_diagram(mermaid("flowchart LR\n  A-->B[Text]\n  B==>C{Choice}\n")),
    )
    expect_clean(
        "edge labels are not node labels",
        with_diagram(mermaid(
            'flowchart LR\n  n1["Account"] -->|has many| n2["Invoice"]\n'
            '  n2 -.->|notifies| n3["Mailer"]\n'
        )),
    )
    expect_clean(
        "`graph` is an accepted alias, not a deprecation -- both spellings pass",
        with_diagram(mermaid('graph TD\n  n1["a"] --> n2["b"]\n')),
    )
    for kind, body in (
        ("erDiagram", "erDiagram\n  ACCOUNT ||--o{ INVOICE : has\n"),
        ("sequenceDiagram", "sequenceDiagram\n  Controller->>Job: enqueue\n  Job-->>Mailer: send\n"),
        ("stateDiagram-v2", "stateDiagram-v2\n  [*] --> Draft\n  Draft --> Sent: submit\n"),
    ):
        expect_clean(f"{kind} renders and is allowed", with_diagram(mermaid(body)))

    # ---- diagrams must be mermaid, not ASCII and not a picture -----------------------
    expect_findings(
        "an ASCII-art diagram",
        with_diagram(FLOW_OK + "\n" + fenced("text",
            "  +---------+      +---------+\n"
            "  | Request | ---> | Invoice |\n"
            "  +---------+      +---------+\n"
            "        |                |\n"
            "        +--------------> +\n"
        )),
        contains="ASCII-art diagram",
    )
    expect_clean(
        "a directory tree is box-drawing WITHOUT arrows and must pass",
        with_diagram(FLOW_OK + "\n" + fenced("text",
            "app/\n"
            "├── models/\n"
            "│   └── invoice.rb\n"
            "├── jobs/\n"
            "│   └── billing_job.rb\n"
            "└── views/\n"
        )),
    )
    expect_clean(
        "a real code sample is not a diagram",
        with_diagram(FLOW_OK + "\n" + fenced("ruby",
            "class Invoice < ApplicationRecord\n"
            "  belongs_to :appointment\n"
            "end\n"
        )),
    )
    expect_findings(
        "a diagram embedded as an image",
        with_diagram(FLOW_OK + "\n![Billing architecture diagram](docs/img/arch.png)\n"),
        contains="embedded as an image",
    )
    expect_findings(
        "a diagram embedded as an <img> tag",
        with_diagram(FLOW_OK + '\n<img src="docs/img/sequence-diagram.svg" alt="x">\n'),
        contains="embedded as an <img>",
    )
    expect_clean(
        "a screenshot is legitimate -- the rule is about diagrams, not images",
        with_diagram(FLOW_OK + "\n![The invoice page](docs/img/invoice-page.png)\n"),
    )

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for f in FAILURES:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"check_guide selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
