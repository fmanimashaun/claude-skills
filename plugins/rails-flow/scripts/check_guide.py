#!/usr/bin/env python3
"""Reject a human guide that cannot be re-run safely, or whose diagrams will not render.

Run:  python3 check_guide.py docs/GUIDE.md
      python3 check_guide.py docs/GUIDE.md --decisions docs/brain/DECISIONS.md
      python3 check_guide.py --selftest

WHY (rails-flow #126). `/rails-flow:explain` writes `docs/GUIDE.md` -- the one artefact in this
toolchain aimed at the human owner rather than an agent. It makes two promises a reader cannot
check by reading it:

  1. **"Idempotent, section-scoped updates; never a wholesale rewrite."** That holds only while
     the managed markers are balanced. One dropped `<!-- rails-flow:end ... -->` and the next
     re-run either rewrites the owner's own prose or refuses to run -- and the damage is silent
     until it has happened.
  2. **"Diagrams are mermaid (GitHub-renderable)."** A mermaid block with one bad token does not
     render as a broken diagram; GitHub shows an error box where the picture should be. Nobody
     notices from the diff, because the diff is valid markdown. The guide is *read* on GitHub and
     *written* here, so the failure surfaces to the owner and never to the author.

Both are the `claims-vs-enforcement` class from the bundled `code-review` skill: a guarantee
stated in prose with nothing making it true. So they become a check.

WHAT THIS GUARANTEES
    Markers are balanced, unique and unnested, so a section-scoped rewrite is safe. The guide
    covers the four things #126 requires -- what it does, how it flows, decisions with
    trade-offs, how to verify by hand -- per area, not once globally. Every mermaid block
    declares a diagram type this repo has evidence renders on GitHub, avoids the two documented
    ways to break a flowchart (a bare lowercase `end`, an unquoted label holding bracket
    characters), and carries no deprecated `%%{init}%%` directive. Diagrams are mermaid rather
    than ASCII art or a picture. Verification steps name something runnable.

WHAT IT DOES NOT
    It cannot tell whether the prose is TRUE, or whether an explanation is any good -- the whole
    reason the guide is bounded and dated instead of exhaustive. It cannot render mermaid, so it
    catches the documented syntax traps and an unverified diagram type, not every possible
    render failure: the only proof a diagram renders is looking at the file on GitHub, and the
    doctrine says so in those words rather than implying this script is that proof.

    It also does not know GitHub's mermaid version -- nobody outside GitHub does (see the
    citation below). That is exactly why the diagram-type rule is an allowlist of
    long-established types rather than a version comparison.

EXTERNAL CLAIMS THIS ENCODES, AND THEIR SOURCES (verified 2026-07-31)
    * Markdown files render mermaid: "Diagram rendering is available in GitHub Issues, GitHub
      Discussions, pull requests, wikis, and Markdown files."
      https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-diagrams
      Gists too, which that page omits:
      https://github.blog/changelog/2022-02-28-gists-now-support-mermaid-diagrams/
    * A bare lowercase `end` breaks a flowchart: "Typing 'end' in all lowercase letters will
      break the Flowchart."  https://mermaid.js.org/syntax/flowchart.html
    * Quoting is the documented fix for bracket characters: "It is possible to put text within
      quotes in order to render more troublesome characters."  (same page)
    * `%%{init: ...}%%` is deprecated: "Directives are deprecated from v10.5.0. Please use the
      `config` key in frontmatter to pass configuration."
      https://mermaid.js.org/config/directives.html
    * GitHub does NOT publish its bundled mermaid version -- its docs give a self-check
      (render a block containing `info`) and never state the number. Nor does GitHub document
      any node/size cap or the conditions behind "Unable to render rich display". So this script
      claims neither.

    NOT claimed, because checking refuted it: `graph` is **not** deprecated in favour of
    `flowchart` -- "Instead of `flowchart` one can also use `graph`" (flowchart page, no
    deprecation notice). `/rails-flow:explain` prefers `flowchart` as a house convention, which
    is a different and much weaker statement, and both spellings pass here.

Exit codes:  0 clean · 1 findings · 2 unusable input (no file / not a rails-flow guide /
             markers so broken that a section-scoped rewrite is unsafe)

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

BEGIN_RE = re.compile(r"<!--\s*rails-flow:begin\s+(?P<slug>[A-Za-z0-9:_\-./]+)\s*-->")
END_RE = re.compile(r"<!--\s*rails-flow:end\s+(?P<slug>[A-Za-z0-9:_\-./]+)\s*-->")
FENCE_RE = re.compile(r"^\s*(?P<ticks>`{3,})\s*(?P<lang>[A-Za-z0-9_+-]*)\s*$")

# The two fixed sections plus at least one area. Areas are separately marked
# (`guide:area:<slug>`) precisely so `/rails-flow:explain billing` rewrites billing and nothing
# else -- a single "how it flows" section holding every area could not be updated per area
# without a wholesale rewrite, which is the promise this file exists to keep.
OVERVIEW_SLUG = "guide:overview"
DECISIONS_SLUG = "guide:decisions"
AREA_PREFIX = "guide:area:"

# Each area answers #126's four questions. Matched on the heading text, case-insensitively, with
# a small alias set -- the command generates these headings, so this is a contract, not a guess.
REQUIRED_AREA_PARTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("what it does", ("what it does", "what this does", "what it is for")),
    ("how it flows", ("how it flows", "how it works", "the flow")),
    ("check it yourself", ("check it yourself", "how to check it", "verify it yourself")),
)

# Diagram types with evidence they render on GitHub: the classics named in GitHub's own
# announcement of mermaid support, plus `erDiagram`, which predates it. Deliberately NOT
# "everything mermaid supports": GitHub's bundled version is unpublished, so a type added
# upstream last month may render nothing. Anything outside this list is *unverified*, not
# impossible -- the finding says to look at the file on GitHub and widen the list if it renders.
KNOWN_DIAGRAM_TYPES = frozenset({
    "flowchart", "graph", "sequenceDiagram", "classDiagram", "stateDiagram",
    "stateDiagram-v2", "erDiagram", "gantt", "pie", "journey", "gitGraph",
})

# Shapes from mermaid's flowchart syntax. Ordered longest-first so `[[` is not read as `[`.
#
# Two details are load-bearing, both found by fixtures that failed the SILENT direction:
#   * the id may not contain `-`, or `A-->B[Text]` parses as id `A--` + the asymmetric `>` shape,
#     making `text` the string `B[Text` -- a false positive on the most ordinary line in any
#     flowchart.
#   * a fully-quoted label is its own alternative, tried FIRST. With only the non-greedy branch,
#     `A["Bill (monthly)"]` stops `text` at the first `)`, so the label looks unquoted and the
#     rule fires on correct mermaid. A quoting rule that flags correct quoting is worse than no
#     rule: it teaches people to delete the quotes.
NODE_DECL_RE = re.compile(
    r"""(?<![\w"'])
        (?P<id>[A-Za-z_]\w*)
        (?P<open>\[\[|\[\(|\(\(|\(\[|\{\{|\[/|\[\\|\[|\(|\{|>)
        (?P<text>"[^"\n]*"|[^\n]*?)
        (?P<close>\]\]|\)\]|\)\)|\]\)|\}\}|/\]|\\\]|\]|\)|\})
    """,
    re.X,
)
# Characters that terminate a shape and so must sit inside quotes to survive.
RISKY_LABEL_CHARS = "()[]{}<>"

ARROW_RE = re.compile(r"-{2,}>|<-{2,}|-\.->|==>|→|←")
BOX_DRAWING = "─│┌┐└┘├┤┬┴┼╭╮╰╯━┃═║"
IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)")
IMG_TAG_RE = re.compile(r"<img\b[^>]*?src\s*=\s*[\"'](?P<src>[^\"']+)", re.I)
# A picture standing in for a diagram. Screenshots are legitimate and must pass, so the match is
# on diagram vocabulary rather than on "is an image" -- an exemption needs its near-miss test.
DIAGRAM_WORDS = (
    "diagram", "flowchart", "flow chart", "architecture", "sequence", "state machine",
    "state-machine", "erd", "entity relationship", "topology", "schema diagram",
)
DECISION_ID_RE = re.compile(r"\bD-\d{3,}\b")
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
PATH_OR_URL_RE = re.compile(r"https?://\S+|(?:^|\s)/[\w./-]+|\b\w+/[\w./-]+\.\w+")
STEP_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?P<text>\S.*)$")
HEADING_RE = re.compile(r"^\s{0,3}(?P<hashes>#{2,6})\s+(?P<text>.*\S)\s*$")


class Unusable(Exception):
    """The guide cannot be checked -- never report clean for it."""


@dataclass
class Section:
    slug: str
    start: int              # line number of the begin marker
    end: int                # line number of the end marker
    lines: list[str] = field(default_factory=list)   # body, between the markers
    first_body_line: int = 0                          # line number of lines[0]

    @property
    def is_area(self) -> bool:
        return self.slug.startswith(AREA_PREFIX)


@dataclass
class Diagram:
    section: str
    line: int               # line number of the opening fence
    lang: str
    body: list[str]
    closed: bool


def parse(path: Path) -> list[Section]:
    """Split the guide into its managed sections, or refuse to bless it.

    Marker damage is UNUSABLE rather than a finding. A finding says "the guide has a problem";
    this says "a re-run of /rails-flow:explain cannot be trusted to leave your prose alone",
    which is a different and louder statement.
    """
    if not path.is_file():
        raise Unusable(f"no such file: {path}")

    raw = path.read_text(encoding="utf-8").splitlines()
    sections: list[Section] = []
    open_section: Section | None = None
    seen: dict[str, int] = {}

    for line_no, line in enumerate(raw, start=1):
        begin = BEGIN_RE.search(line)
        end = END_RE.search(line)

        if begin and end:
            raise Unusable(
                f"{path}:{line_no} opens and closes a marker on one line -- a section-scoped "
                "rewrite has no body to replace"
            )
        if begin:
            slug = begin.group("slug")
            if open_section is not None:
                raise Unusable(
                    f"{path}:{line_no} opens {slug!r} while {open_section.slug!r} (line "
                    f"{open_section.start}) is still open -- nested managed sections cannot be "
                    "rewritten independently"
                )
            if slug in seen:
                raise Unusable(
                    f"{path}:{line_no} re-opens {slug!r}, already used on line {seen[slug]} -- a "
                    "duplicate slug makes it ambiguous which block a re-run replaces"
                )
            seen[slug] = line_no
            open_section = Section(slug=slug, start=line_no, end=0, first_body_line=line_no + 1)
            continue
        if end:
            slug = end.group("slug")
            if open_section is None:
                raise Unusable(
                    f"{path}:{line_no} closes {slug!r} which was never opened -- the guide's "
                    "markers do not describe its own structure"
                )
            if slug != open_section.slug:
                raise Unusable(
                    f"{path}:{line_no} closes {slug!r} but {open_section.slug!r} (line "
                    f"{open_section.start}) is open -- crossed markers"
                )
            open_section.end = line_no
            sections.append(open_section)
            open_section = None
            continue
        if open_section is not None:
            open_section.lines.append(line)

    if open_section is not None:
        raise Unusable(
            f"{path}: section {open_section.slug!r} opened on line {open_section.start} is never "
            "closed -- everything after it would be swallowed by the next re-run"
        )
    if not sections:
        raise Unusable(
            f"{path} carries no `<!-- rails-flow:begin ... -->` markers -- refusing to report a "
            "hand-written file clean as a managed guide (a re-run would have nothing to scope to)"
        )
    return sections


def diagrams_in(section: Section) -> list[Diagram]:
    """Every fenced block in a section, mermaid or not, with its closed/unclosed state."""
    out: list[Diagram] = []
    fence: Diagram | None = None
    ticks = ""
    for offset, line in enumerate(section.lines):
        line_no = section.first_body_line + offset
        match = FENCE_RE.match(line)
        if fence is None:
            if match:
                ticks = match.group("ticks")
                fence = Diagram(
                    section=section.slug, line=line_no, lang=match.group("lang").lower(),
                    body=[], closed=False,
                )
            continue
        # Inside a fence: only a bare run of at least as many backticks closes it.
        if match and match.group("ticks").startswith(ticks) and not match.group("lang"):
            fence.closed = True
            out.append(fence)
            fence = None
            continue
        fence.body.append(line)
    if fence is not None:
        out.append(fence)
    return out


def _strip_quoted(text: str) -> str:
    """Blank out quoted spans so a rule reads only the unquoted parts of a line."""
    return re.sub(r'"[^"]*"', '""', text)


def _check_flowchart_end(diagram: Diagram, findings: list[str]) -> None:
    """A bare lowercase `end` is legal ONLY as the closer of an open `subgraph`.

    Anywhere else mermaid reads it as a node and the whole flowchart stops rendering. Tracking
    subgraph depth is what separates the two; a plain `\\bend\\b` grep would flag every nested
    subgraph in a correct diagram -- including the three in this repo's own README.
    """
    depth = 0
    for offset, raw in enumerate(diagram.body):
        line = _strip_quoted(raw.split("%%")[0])
        stripped = line.strip()
        if re.match(r"^subgraph\b", stripped):
            depth += 1
            continue
        if stripped == "end":
            if depth == 0:
                findings.append(
                    f"{diagram.section} line {diagram.line + 1 + offset}: a bare lowercase `end` "
                    "closes no open `subgraph`, so mermaid reads it as a node and the flowchart "
                    "renders nothing. Capitalize it (`End`) or quote it inside a label."
                )
            else:
                depth -= 1
            continue
        if ARROW_RE.search(line) and re.search(r"\bend\b", line):
            findings.append(
                f"{diagram.section} line {diagram.line + 1 + offset}: `end` is used as a node in "
                "an edge, which breaks the whole flowchart. Rename it (`End`, `finish`) or put "
                "the word inside a quoted label."
            )


def _check_labels(diagram: Diagram, findings: list[str]) -> None:
    for offset, raw in enumerate(diagram.body):
        line = raw.split("%%")[0]
        for match in NODE_DECL_RE.finditer(line):
            text = match.group("text").strip()
            if not text:
                continue
            if text.startswith('"') and text.endswith('"') and len(text) >= 2:
                continue
            risky = sorted({c for c in text if c in RISKY_LABEL_CHARS})
            if risky:
                findings.append(
                    f"{diagram.section} line {diagram.line + 1 + offset}: node "
                    f"{match.group('id')!r} has an unquoted label containing {''.join(risky)!r}, "
                    "which terminates the shape and stops the diagram rendering. Wrap the label "
                    'in double quotes: id["text (like this)"].'
                )


def check(sections: list[Section], decisions: Path | None = None) -> list[str]:
    findings: list[str] = []
    slugs = {s.slug for s in sections}

    # ---- coverage: the four things #126 requires the guide to answer --------------------
    for required, why in (
        (OVERVIEW_SLUG, "what the system does, in plain language"),
        (DECISIONS_SLUG, "the key decisions and their trade-offs"),
    ):
        if required not in slugs:
            findings.append(
                f"no `{required}` section -- the guide does not cover {why}, which is one of the "
                "four things it exists to carry"
            )

    areas = [s for s in sections if s.is_area]
    if not areas:
        findings.append(
            f"no `{AREA_PREFIX}<slug>` section -- a guide with no area explains nothing about how "
            "the system flows or how to check it by hand"
        )

    for area in areas:
        headings = [
            HEADING_RE.match(line).group("text").strip().lower()  # type: ignore[union-attr]
            for line in area.lines if HEADING_RE.match(line)
        ]
        for label, aliases in REQUIRED_AREA_PARTS:
            if not any(any(a in h for a in aliases) for h in headings):
                findings.append(
                    f"{area.slug} (line {area.start}) has no {label!r} heading -- every area "
                    "answers what it does, how it flows, and how the owner checks it by hand. "
                    "Two of the three is a tour, not an explanation."
                )

        # ---- verification steps must name something runnable -------------------------
        in_check = False
        for offset, line in enumerate(area.lines):
            heading = HEADING_RE.match(line)
            if heading:
                text = heading.group("text").strip().lower()
                in_check = any(a in text for a in REQUIRED_AREA_PARTS[2][1])
                continue
            if not in_check:
                continue
            step = STEP_RE.match(line)
            if not step:
                continue
            body = step.group("text")
            if INLINE_CODE_RE.search(body) or PATH_OR_URL_RE.search(body):
                continue
            findings.append(
                f"{area.slug} line {area.first_body_line + offset}: the check step names no "
                f"command, route or path ({body[:60]!r}) -- a step the owner cannot run is a "
                "reassurance, not a check. Name the command in backticks or the route to open."
            )

    # ---- decisions must point at DECISIONS.md, not restate it ---------------------------
    # Fires only when the project HAS a decisions log, and only on the section as a whole: the
    # failure being prevented is the guide quietly becoming a second source of truth, not every
    # paragraph carrying a citation.
    if decisions is not None and decisions.is_file():
        for section in sections:
            if section.slug != DECISIONS_SLUG:
                continue
            body = "\n".join(section.lines)
            if body.strip() and not DECISION_ID_RE.search(body):
                findings.append(
                    f"{DECISIONS_SLUG} (line {section.start}) cites no `D-nnn` entry while "
                    f"{decisions} exists -- restating rationale here makes the guide a second "
                    "source of truth that will drift from the log. Link the decision; explain "
                    "the trade-off."
                )

    # ---- diagrams --------------------------------------------------------------------
    for section in sections:
        for diagram in diagrams_in(section):
            if not diagram.closed:
                findings.append(
                    f"{section.slug} line {diagram.line}: fenced block is never closed -- "
                    "everything below it renders as code, including the rest of the guide"
                )
                continue

            if diagram.lang == "mermaid":
                body = [b for b in diagram.body if b.strip() and not b.strip().startswith("%%")]
                if not body:
                    findings.append(
                        f"{section.slug} line {diagram.line}: empty mermaid block -- GitHub shows "
                        "an error box where the diagram should be"
                    )
                    continue

                first = body[0].strip()
                if first == "---" or first.startswith("---"):
                    findings.append(
                        f"{section.slug} line {diagram.line}: mermaid frontmatter (`---`) -- "
                        "GitHub does not document supporting it and does not publish its mermaid "
                        "version, so this may render nothing. Use a markdown heading above the "
                        "block for a title."
                    )
                    continue
                declared = first.split()[0]
                if declared not in KNOWN_DIAGRAM_TYPES:
                    findings.append(
                        f"{section.slug} line {diagram.line}: diagram type {declared!r} is not on "
                        "the list this repo has evidence GitHub renders "
                        f"({', '.join(sorted(KNOWN_DIAGRAM_TYPES))}). GitHub does not publish its "
                        "mermaid version, so a newer type can render nothing. Check the file on "
                        "GitHub; if it renders, add the type to KNOWN_DIAGRAM_TYPES with the date."
                    )

                for offset, line in enumerate(diagram.body):
                    if "%%{" in line and "init" in line:
                        findings.append(
                            f"{section.slug} line {diagram.line + 1 + offset}: `%%{{init:...}}%%` "
                            "is deprecated from mermaid v10.5.0. The guide's diagrams must render "
                            "under default config -- drop the directive."
                        )
                if declared in ("flowchart", "graph"):
                    _check_flowchart_end(diagram, findings)
                    _check_labels(diagram, findings)
                continue

            # ---- a non-mermaid block that is really a diagram ------------------------
            if diagram.lang in ("", "text", "txt", "plain", "console"):
                drawn = [
                    b for b in diagram.body
                    if any(c in b for c in BOX_DRAWING) or re.search(r"\+-{2,}", b)
                ]
                # The arrow requirement is what keeps a directory tree (also box-drawing, no
                # arrows) out of this rule. An exemption needs its near-miss test, and that
                # near-miss is pinned in the selftest.
                if len(drawn) >= 3 and any(ARROW_RE.search(b) for b in diagram.body):
                    findings.append(
                        f"{section.slug} line {diagram.line}: ASCII-art diagram -- diagrams in the "
                        "guide are mermaid, which GitHub renders as a picture and a reader can "
                        "follow. ASCII survives no re-flow and no screen width."
                    )

    # ---- a picture standing in for a diagram ----------------------------------------
    for section in sections:
        for offset, line in enumerate(section.lines):
            for match in IMAGE_RE.finditer(line):
                haystack = f"{match.group('alt')} {match.group('src')}".lower()
                if any(w in haystack for w in DIAGRAM_WORDS):
                    findings.append(
                        f"{section.slug} line {section.first_body_line + offset}: a diagram is "
                        f"embedded as an image ({match.group('src')}) -- an image cannot be "
                        "diffed, goes stale invisibly, and is unreadable to an agent. Use a "
                        "```mermaid block. (Screenshots are fine; this is about diagrams.)"
                    )
            for match in IMG_TAG_RE.finditer(line):
                if any(w in match.group("src").lower() for w in DIAGRAM_WORDS):
                    findings.append(
                        f"{section.slug} line {section.first_body_line + offset}: a diagram is "
                        f"embedded as an <img> ({match.group('src')}) -- use a ```mermaid block"
                    )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate a rails-flow human guide: markers, coverage, and mermaid diagrams."
    )
    parser.add_argument("guide_path", nargs="?", help="docs/GUIDE.md")
    parser.add_argument(
        "--decisions", metavar="FILE",
        help="the project's decision log (usually docs/brain/DECISIONS.md); when it exists, the "
             "guide's decisions section must cite it rather than restate it",
    )
    parser.add_argument(
        "--selftest", action="store_true", help="prove the rules fire AND stay silent"
    )
    args = parser.parse_args(argv)

    if args.selftest:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import check_guide_selftest as st

        return st.run()

    if not args.guide_path:
        parser.error("guide_path is required (or pass --selftest)")

    try:
        sections = parse(Path(args.guide_path))
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2

    findings = check(sections, Path(args.decisions) if args.decisions else None)

    if findings:
        print(
            f"{len(findings)} guide finding(s) in {args.guide_path}:",
            file=sys.stderr,
        )
        for f in findings:
            print(f"  - {f}", file=sys.stderr)
        print(
            "\nFix the guide, do not soften the check. A diagram that does not render is worse "
            "than no diagram: the owner sees an error box and assumes the system is broken.",
            file=sys.stderr,
        )
        return 1

    areas = sum(1 for s in sections if s.is_area)
    diagrams = sum(
        1 for s in sections for d in diagrams_in(s) if d.lang == "mermaid"
    )
    print(
        f"{len(sections)} managed sections ({areas} area(s)), {diagrams} mermaid diagram(s) "
        f"validated: {args.guide_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
