#!/usr/bin/env python3
"""A change a user can see is built only after the owner approved a clickable mock-up (#1376).

Run:  check_mockup_gate.py --base dev [--root DIR]            # the branch's diff, before merge
      check_mockup_gate.py --paths app/views/a.html.erb ...   # the plan's files, at Phase 1
      check_mockup_gate.py --adopt-shell SRC.html SRC.html ... --approval URL --approved-by @who --issue "#n"
                           --widths "1280, 390" --states "default, collapsed"      # record the app's shell (#2211)
      check_mockup_gate.py --selftest
      optional on either: --record docs/product/mockups/<slug>.md

Exit: 0 no user-visible change, or an approved mock-up is recorded, or the project declared the
gate off · 1 user-visible change with no approved mock-up recorded · 2 cannot classify.

WHY. On a downstream app's first production day the owner reported about 14 screens built unlike
what had been agreed in conversation: tables for cards, page forms for modals, a link for a
dropdown. Each cost a PR, specs, screenshots and a redeploy. The one screen whose clickable mock-up
was approved FIRST was right in one round, because the build had a target. So the owner's rule: a
user-visible change waits for an approved mock-up, whatever the issue's label says.

UI SCOPE IS A PATH RULE, not a judgement. A change touches what a user sees when it touches
UI_PATHS: views (not JSON/XML templates, which API clients read), components, JavaScript,
stylesheets, helpers, and locale files (visible copy). Everything else is backend. A mixed change is
UI scope.

THE RECORD is `docs/product/mockups/<slug>.md`, carrying one `Key: value` line for each of RECORD_KEYS.
It must name the mock-up (a URL, or a repo file that exists), the issue, who approved it, the
approval itself as a link to the comment where they said so, and the widths (a phone width ≤ 480
and a desktop width ≥ 1024) and states it covers. The branch must add or change the record, or name
it with --record. An approval with no link is a sentence anyone can type.

THE SHELL (#2211). A mock-up is drawn inside the app's own shell: its layout and navigation, not a free-standing
screen. The shell is a RECORDED, APPROVED thing the project owns: `docs/product/mockups/shell.md`, a record in the
format above plus `Kind: shell`, `Shell-sources:` (two or more approved HTML mock-ups of DIFFERENT screens) and
`Shell-signature:`. The signature is DERIVED, never typed: the landmark elements (header, nav, main, footer, aside)
and every element id that all the sources share, so what two screens have in common is the shell and what differs
is content. `--adopt-shell` derives and writes it (`--keep` may narrow it to some of what the sources share, to drop an id two
screens have in common by chance; it cannot add one); the gate recomputes what the sources share and fails on a token they no longer share.
Every other record carries `Shell: docs/product/mockups/shell.md`. When its mock-up is a repo HTML file it must hold
every signature token as an ELEMENT (a word in text, a comment or a script is not one); an image, PDF or link can
only be checked for the reference and the output says so. A project with no recorded shell is held on its first
UI change: that change must be the shell (rule 2 of the owner's ruling). A signature too small to tell a shell from
any page (no `main`, or fewer than SHELL_MIN_TOKENS tokens) is refused: an empty signature passes everything.
Measured on a downstream project's 52 HTML mock-ups: no class token was in even 75% of them (utility classes),
landmark tags alone were in 27 to 51, and the ids the layout owns (#main, #toasts, #modal) in 27: so tags and ids.

WHAT IT DOES NOT: prove the linked comment says "approved", or that the build matches the mock-up.
The first is the reviewer's click; the second is the screenshot comparison before merge.

OPT-OUT. A project without a design reviewer declares `mockup-gate: off` on its own line in
GUARDRAILS.md (setup-flow asks). Undeclared means ON: the owner set the default.

Stdlib only; git is read like classify_door.py reads it, through the same helper.
"""
from __future__ import annotations

import argparse
import os
import re
from html.parser import HTMLParser
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_door import Unusable, diff  # noqa: E402  -- one diff reader, never a second

UI_PATHS = (re.compile(r"^app/views/"), re.compile(r"^app/components/"), re.compile(r"^app/javascript/"),
            re.compile(r"^app/assets/(stylesheets|tailwind|images)/"), re.compile(r"^app/helpers/"),
            re.compile(r"^config/locales/"),
            # What Rails 8 generates for a user to see outside app/views: the error pages, the icon,
            # the favicon (pre-release review of #1381).
            re.compile(r"^public/[^/]+\.(html|png|svg|ico|webmanifest)$"))
# An API template is read by a client, not seen by a person -- except the PWA manifest, which holds
# the installed app's name and icons.
NOT_UI = re.compile(r"\.(json|xml)(\.[a-z]+)?$")
SEEN_ANYWAY = re.compile(r"^app/views/pwa/")
RECORD_DIR = "docs/product/mockups/"
RECORD_KEYS = ("Mock-up", "Issue", "Approved-by", "Approval", "Widths", "States")
# The shell (#2211): one record every other record points at.
SHELL_RECORD = RECORD_DIR + "shell.md"
SHELL_KEYS = ("Kind", "Shell", "Shell-sources", "Shell-signature")
LANDMARKS = frozenset(("header", "nav", "main", "footer", "aside"))
SHELL_MIN_TOKENS = 3
HTML_MOCK = re.compile(r"\.html?$", re.I)
APPROVAL_URL = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/(issues|pull)/\d+"
                          r"#(issuecomment-\d+|discussion_r\d+|pullrequestreview-\d+)$")
MOCK_FILE = re.compile(r"\.(html?|png|jpe?g|webp|pdf|svg)$", re.I)
ISSUE_REF = re.compile(r"^(#\d+|https://github\.com/[^/\s]+/[^/\s]+/issues/\d+)\b")
# Space and tab only: CommonMark counts no other character as indentation (spec 0.31.2 §2.1), so a
# line opening with a non-breaking space is paragraph text, not an indented declaration (#1490).
OPT_OUT = re.compile(r"^[ \t]*(?:[-*+][ \t]*)?`?mockup-gate:[ \t]*off`?[ \t]*$", re.M | re.I)


def ui_paths(paths: list[str]) -> list[str]:
    return sorted(p for p in paths if any(r.match(p) for r in UI_PATHS)
                  and (SEEN_ANYWAY.match(p) or not NOT_UI.search(p)))


def declared_off(root: Path) -> bool:
    g = root / "GUARDRAILS.md"
    if not g.is_file():
        return False
    # The line declares only as paragraph text: inside a fenced or indented code block, an HTML block
    # or a comment it is an example (#1381, #1430, #1490, #1501). An unterminated fence runs to the
    # end of its container, as CommonMark renders it (§4.5 Ex 128).
    return declares_off(g.read_text(encoding="utf-8"))


def declares_off(text: str) -> bool:
    """Whether `text` holds the opt-out line as text, outside every code and HTML block."""
    return any(OPT_OUT.match(line) and cls == "text"
               for line, cls in zip(text.split("\n"), block_classes(text)))



# --------------------------------------------------------------------------- block structure (#1501)
# GUARDRAILS.md lines are judged by the block they sit in. An opt-out in a fenced or indented code
# block, or in an HTML block or comment, is an example or markup, not a declaration (#1381, #1430,
# #1490). Two line-based passes here before #1501 kept failing open on containers -- a fence or quote
# inside a list item, a list closed by a column-0 block -- so this is the block algorithm itself.

# commonmark.js's own definitions (lib/blocks.js, 0.31.2), matched exactly. Python's str.strip() and
# Unicode \d / \s differ from them (#1512 review B1-B3):
#   blank       -- only spaces and tabs (the parser's findNextNonspace, and spec §4.9): NBSP, \f and
#                  \v are NOT blank -- a form-feed line opens a paragraph in commonmark.js;
#   ordered     -- ASCII digits only (JavaScript \d);
#   JS_WS       -- JavaScript \s, used by the HTML block patterns.
BLANK_CHARS = " \t"
JS_WS = "[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]"
REFDEF = re.compile(r"\[(?:[^\]\\]|\\.)+\]:[ \t]*\S")

TAG_NAMES = ("address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|"
             "dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h1|h2|h3|h4|h5|h6|"
             "head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|"
             "p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul")
HTML_START = [
    # Type 1 ends at ANY of the four closing tags; it need not match its opener (verifier, §4.6).
    (re.compile(r"<(?:pre|script|style|textarea)(?:" + JS_WS + r"|>|$)", re.I), re.compile(r"</(?:pre|script|style|textarea)>", re.I)),
    # Types 2-5 end at a LITERAL string (§4.6; commonmark.js reHtmlBlockClose), so they are matched as
    # substrings, not regexes. This is CommonMark's block grammar, not an HTML sanitiser: `--!>` does
    # not end a type-2 block in the spec or the reference, and ending there would close it early.
    (re.compile(r"<!--"), "-->"),
    (re.compile(r"<\?"), "?>"),
    (re.compile(r"<![A-Za-z]"), ">"),
    (re.compile(r"<!\[CDATA\["), "]]>"),
    (re.compile(r"</?(?:" + TAG_NAMES + r")(?:" + JS_WS + r"|/?>|$)", re.I), None),
]
ATTR = r"(?:[ \t]+[A-Za-z_:][A-Za-z0-9_.:-]*(?:[ \t]*=[ \t]*(?:[^ \t\"'=<>`]+|'[^']*'|\"[^\"]*\"))?)"
HTML7 = re.compile(r"(?:<[A-Za-z][A-Za-z0-9-]*" + ATTR + r"*[ \t]*/?>|</[A-Za-z][A-Za-z0-9-]*[ \t]*>)" + JS_WS + r"*$")
FENCE = re.compile(r"(`{3,})(?!.*`)|(~{3,})")
THEMATIC = re.compile(r"(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
ATX = re.compile(r"#{1,6}(?:[ \t]|$)")
SETEXT = re.compile(r"(?:=+|-+)[ \t]*$")
MARKER = re.compile(r"([-+*]|([0-9]{1,9})[.)])(?=[ \t]|$)")


def _indent(s, pos):
    """(spaces of indentation from pos, index of first non-space). `s` has its tabs expanded."""
    j = pos
    while j < len(s) and s[j] == " ":
        j += 1
    return j - pos, j


class Item:
    def __init__(self, width, blank_start):
        self.width, self.blank_start, self.has_content = width, blank_start, not blank_start


def block_classes(text: str) -> list[str]:
    """One class per line of `text`: "code" (fenced or indented), "html", or "text" (#1501).

    Phase 1 of CommonMark 0.31.2's block parsing (the spec's appendix "A parsing strategy", and
    commonmark.js 0.31.2, which a differential fuzz of 350,000 GUARDRAILS.md variants matched line for
    line). Open containers are block quotes and list items; each line first matches their continuation
    markers, then is a lazy paragraph continuation or opens new blocks. Rules (doctrine-verifier,
    CONFIRMED against spec.txt at tag 0.31.2): fences open and close within 3 columns of the
    container, close on the same character at least as long with only spaces after, and end with
    their container (§4.5, Ex 125-147); HTML blocks of types 1-7 and their end conditions, type 7 not
    interrupting a paragraph (§4.6); a quote marker after 0-3 spaces with one optional space (§5.1);
    list items' content columns, at most one starting blank line, and the interrupt-a-paragraph limits
    (§5.2, Ex 270-305); setext underlines are never lazy (Ex 93, 101); indented code never interrupts
    a paragraph (Ex 113); tabs count to absolute 4-column stops for structure (§2.2), and only space
    and tab indent (§2.1). Inline content is never parsed.
    """
    out = []
    stack = []            # open containers, outermost first: "quote" or Item
    leaf = None           # None | "para" | ("fence", char, length, indent) | "icode" | ("html", end_re or None)
    refs_only = False     # the open paragraph holds only link reference definitions (no setext heading)
    for raw in text.split("\n"):
        s = raw.expandtabs(4)
        pos, matched = 0, 0
        last = len(s.rstrip(BLANK_CHARS)) - 1   # the line is blank from any position past `last`
        # nxt[k]: the first non-space index at or after k. One pass per line, so each container's
        # indentation check is O(1) -- rescanning the spaces per container was cubic in nesting depth
        # (#1512 review S2: 2,000 levels took minutes).
        nxt = [len(s)] * (len(s) + 1)
        for k in range(len(s) - 1, -1, -1):
            nxt[k] = k if s[k] != " " else nxt[k + 1]

        def ind(at, nxt=nxt):
            j = nxt[at] if at <= len(s) else at
            return j - at, j
        # 1. continuation markers of the open containers
        for c in stack:
            if c == "quote":
                n, j = ind(pos)
                if n <= 3 and j < len(s) and s[j] == ">":
                    pos = j + 1
                    if pos < len(s) and s[pos] == " ":
                        pos += 1
                    matched += 1
                    continue
                break
            if pos > last:                    # blank AFTER the markers matched so far (`  >` included)
                if c.blank_start and not c.has_content:
                    break                     # an item may begin with at most one blank line
                matched += 1
                continue
            n, j = ind(pos)
            if n >= c.width:
                pos += c.width
                matched += 1
                continue
            break
        rest_blank = pos > last
        all_matched = matched == len(stack)
        # 2. an open fence or HTML block continues only inside ALL its containers
        if isinstance(leaf, tuple) and leaf[0] == "fence":
            if all_matched:
                n, j = ind(pos)
                m = re.match(r"(`{3,}|~{3,})[ \t]*$", s[j:]) if n <= 3 else None
                if m and m.group(1)[0] == leaf[1] and len(m.group(1)) >= leaf[2]:
                    leaf = None
                out.append("code")
                continue
            leaf = None                       # the container closed: the fence ends with it
        if isinstance(leaf, tuple) and leaf[0] == "html":
            if all_matched:
                end = leaf[1]
                if end is None and rest_blank:
                    leaf = None
                    out.append("text")
                    continue
                if end is not None and _ends(end, s, pos):
                    leaf = None
                out.append("html")
                continue
            leaf = None
        # 3. lazy paragraph continuation: unmatched containers stay open for paragraph text only
        if not all_matched and leaf == "para" and not rest_blank and _lazy(s, pos, stack[matched:]):
            # A lazy line is paragraph content too: unless it is itself a reference definition, the
            # paragraph is no longer only definitions and can take a setext underline (#1512 review R1).
            refs_only = refs_only and bool(REFDEF.match(s, ind(pos)[1]))
            out.append("text")
            continue
        if not all_matched:
            del stack[matched:]
            if leaf == "para" or leaf == "icode":
                leaf = None
        blank = rest_blank
        for c in stack:
            if isinstance(c, Item) and not blank:
                c.has_content = True
        if blank:
            if leaf in ("para", None):
                leaf = None
            out.append("text")
            continue
        # 4. new block starts
        cls = "text"
        while True:
            n, j = ind(pos)
            if n >= 4:
                if leaf == "para":
                    cls = "text"
                else:
                    leaf, cls = "icode", "code"
                break
            if leaf == "icode":
                leaf = None
            # Patterns match AT j, never on a slice: slicing per nested marker was quadratic in line length.
            if s.startswith(">", j):
                stack.append("quote")
                pos = j + 1
                if pos < len(s) and s[pos] == " ":
                    pos += 1
                leaf = None if leaf != "para" else leaf
                if pos > last:
                    leaf, cls = None, "text"
                    break
                if leaf == "para":
                    leaf = None
                continue
            f = FENCE.match(s, j)
            if f:
                run = f.group(1) or f.group(2)
                leaf, cls = ("fence", run[0], len(run), n), "code"
                break
            h = _html_start(s, j, leaf == "para")
            if h is not False:
                leaf, cls = ("html", h), "html"
                if h is not None and _ends(h, s, j + 1):
                    leaf = None
                break
            if leaf == "para" and SETEXT.match(s, j) and not refs_only:
                leaf, cls = None, "text"
                break
            # A break ends in its own character, so test the line's last character first: matching the
            # pattern at every nested marker of a long line scanned it to the end each time.
            if last >= 0 and s[last] in "*-_" and THEMATIC.match(s, j):
                leaf, cls = None, "text"
                break
            m = MARKER.match(s, j)
            if m:
                after = m.end()
                k = after
                while k < len(s) and s[k] == " ":
                    k += 1
                empty = k > last
                spaces = k - after
                if leaf == "para" and (empty or (m.group(2) is not None and int(m.group(2)) != 1)):
                    pass                      # cannot interrupt a paragraph: falls through to text
                else:
                    width = (after - pos) + (1 if empty or spaces >= 5 else spaces)
                    stack.append(Item(width, empty))
                    pos += width
                    leaf = None
                    if empty:
                        cls = "text"
                        break
                    continue
            if ATX.match(s, j):
                leaf, cls = None, "text"
                break
            refs_only = bool(REFDEF.match(s, j)) if leaf != "para" else refs_only and bool(REFDEF.match(s, j))
            leaf, cls = "para", "text"
            break
        out.append(cls)
    return out


def _ends(end, s, at):
    """Whether an HTML block's end condition -- a pattern (type 1) or a literal (types 2-5) -- is met
    in `s` from `at`."""
    return s.find(end, at) >= 0 if isinstance(end, str) else end.search(s, at) is not None


def _html_start(s, at, in_para):
    """The end pattern of the HTML block opening at `s[at:]` (None for blank-line-ended), or False."""
    for start, end in HTML_START:
        if start.match(s, at):
            return end
    if not in_para and HTML7.match(s, at):
        return None
    return False


def _lazy(s, pos, unmatched):
    """Whether the line lazily continues the open paragraph, as the reference algorithm decides it.

    Block starts are tried from the last MATCHED container's position (commonmark.js): four or more
    columns past it, no block can open and the line is paragraph text (spec 0.31.2 Ex 312: `    - e`
    under `   - d` is lazy); otherwise it is lazy only if it would open no block there.
    """
    n, _ = _indent(s, pos)
    if n >= 4:
        return True
    return not _starts_block(s, pos)


def _starts_block(s, pos):
    """Whether the line, from `pos` (under 4 columns of indentation: `_lazy` decides the rest),
    would open a block rather than continue a paragraph."""
    _, j = _indent(s, pos)
    if s.startswith(">", j) or FENCE.match(s, j) or ATX.match(s, j) or THEMATIC.match(s, j):
        return True
    if _html_start(s, j, True) is not False:
        return True
    return bool(MARKER.match(s, j))


# --------------------------------------------------------------------------- the shell (#2211)

class _Tokens(HTMLParser):
    """The landmark elements and the element ids of a mock-up, as a set of tokens.

    Only START TAGS count, so a word in text, an id inside a comment, or a tag inside a script string is not a token: HTMLParser reads
    script and style bodies as data and comments as comments. The contents of a <template> are real elements (a mock-up board keeps its
    screens there)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tokens: set[str] = set()

    def _see(self, tag: str, attrs: list) -> None:
        if tag in LANDMARKS:
            self.tokens.add(tag)
        for key, value in attrs:
            if key == "id" and value and value.strip():
                self.tokens.add("#" + value.strip())

    def handle_starttag(self, tag, attrs):
        self._see(tag, attrs)

    def handle_startendtag(self, tag, attrs):
        self._see(tag, attrs)


def shell_tokens(text: str) -> set[str]:
    parser = _Tokens()
    parser.feed(text)
    parser.close()
    return parser.tokens


def derive_signature(texts: list[str]) -> list[str]:
    """What every one of `texts` has in common: the shell. Content that differs between screens drops out."""
    sets = [shell_tokens(t) for t in texts]
    return sorted(set.intersection(*sets)) if sets else []


def signature_line(tokens: list[str]) -> str:
    return ", ".join(tokens)


def signature_weak(tokens: list[str]) -> str | None:
    """Why a signature cannot stand for a shell, or None. An empty signature passes every page: the gate would be unable to fail."""
    if "main" not in tokens:
        return "no `main` landmark in common"
    if len(tokens) < SHELL_MIN_TOKENS:
        return f"only {len(tokens)} token(s) in common ({signature_line(tokens)}), fewer than {SHELL_MIN_TOKENS}"
    return None


def read_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*(?:[-*]\s*)?\**([A-Za-z-]+)\**:\s*(.*?)\s*$", line)
        if m and m.group(1) in RECORD_KEYS + SHELL_KEYS:
            fields[m.group(1)] = m.group(2)
    return fields


def _html_text(root: Path, rel: str) -> str | None:
    """The text of a repo HTML file, or None when `rel` is not one, or resolves outside the repo."""
    f = root / rel
    if not HTML_MOCK.search(rel) or not f.is_file():
        return None
    try:
        f.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return f.read_text(encoding="utf-8", errors="replace")


def shell_record_problems(root: Path, rel: str, fields: dict[str, str]) -> list[str]:
    sources = list(dict.fromkeys(x.strip() for x in fields.get("Shell-sources", "").split(",") if x.strip()))
    out: list[str] = []
    if len(sources) < 2:
        out.append(f"{rel}: Shell-sources must name two or more different approved HTML mock-ups (a shell is what two screens share), got {len(sources)}")
    texts = []
    for src in sources:
        text = _html_text(root, src)
        if text is None:
            out.append(f"{rel}: Shell-source {src!r} is not an HTML file inside the repo")
        else:
            texts.append(text)
    if out:
        return out
    derived = derive_signature(texts)
    typed = [t.strip() for t in fields.get("Shell-signature", "").split(",") if t.strip()]
    if not typed:
        return [f"{rel}: no `Shell-signature:` line (`--adopt-shell` derives it)"]
    invented = [t for t in typed if t not in derived]
    if invented:
        return [f"{rel}: Shell-signature names {', '.join(invented)}, which the sources no longer share (a source changed, or the line was typed "
                f"by hand): they share `{signature_line(derived)}`; re-run --adopt-shell"]
    weak = signature_weak(typed)
    if weak:
        out.append(f"{rel}: the signature has {weak}: it cannot tell a shell from any page")
    return out


def shell_reference_problems(root: Path, rel: str, fields: dict[str, str]) -> list[str]:
    """A record that is not the shell: it names the shell, the shell is valid, and an HTML mock-up holds the shell's signature."""
    ref = fields.get("Shell", "")
    if not ref:
        return [f"{rel}: no `Shell: {SHELL_RECORD}` line: draw the mock-up inside the app's own shell (its layout and navigation), "
                f"not as a free-standing screen"]
    if ref != SHELL_RECORD:
        return [f"{rel}: Shell {ref!r} must be {SHELL_RECORD}, the project's one recorded shell"]
    shell = root / SHELL_RECORD
    if not shell.is_file():
        return [f"{rel}: {SHELL_RECORD} does not exist: this project has no recorded shell, so the first UI change is the shell itself: "
                f"mock up the layout, navigation and foundation screens, get them approved, then run --adopt-shell"]
    shell_fields = read_fields(shell)
    problems = record_problems(root, SHELL_RECORD)
    if problems:
        return problems
    text = _html_text(root, fields.get("Mock-up", ""))
    if text is not None:
        have = shell_tokens(text)
        missing = [t for t in shell_fields["Shell-signature"].split(", ") if t not in have]
        if missing:
            return [f"{rel}: the mock-up {fields['Mock-up']} is not drawn inside the app's shell: it has no element for "
                    f"{', '.join(missing)} (the shell is {SHELL_RECORD})"]
    return []


def reference_only(root: Path, rel: str) -> bool:
    """A non-shell record whose mock-up is not a repo HTML file: only its `Shell:` reference was checked."""
    f = root / rel
    if not f.is_file():
        return False
    fields = read_fields(f)
    return fields.get("Kind", "").lower() != "shell" and _html_text(root, fields.get("Mock-up", "")) is None


def adopt_shell(root: Path, sources: list[str], approval: str, approved_by: str, issue: str, widths: str, states: str,
                keep: list[str] | None = None) -> tuple[int, list[str]]:
    """Derive the shell from approved mock-ups of different screens and record it. Writes nothing unless the record then passes.

    `keep` narrows the signature to some of what the sources share, to drop an id two screens happen to have in common: it can
    only choose among derived tokens, never add one (a hand-typed token is the one thing the gate refuses)."""
    sources = list(dict.fromkeys(sources))
    rec = root / SHELL_RECORD
    lines = ["# Shell — the application's layout and navigation (#2211)",
             f"Mock-up: {sources[0] if sources else ''}", f"Issue: {issue}", f"Approved-by: {approved_by}", f"Approval: {approval}",
             f"Widths: {widths}", f"States: {states}", "Kind: shell", f"Shell-sources: {', '.join(sources)}"]
    texts = [_html_text(root, src) for src in sources]
    if not sources or any(t is None for t in texts):
        bad = [s for s, t in zip(sources, texts) if t is None]
        return 1, [f"--adopt-shell needs HTML mock-ups inside the repo (got {len(sources)}"
                   f"{'; not HTML files in the repo: ' + ', '.join(bad) if bad else ''})"]
    derived = derive_signature([t for t in texts if t is not None])
    chosen = sorted(set(keep)) if keep else derived
    invented = [t for t in chosen if t not in derived]
    if invented:
        return 1, [f"refused: --keep names {', '.join(invented)}, which the mock-ups do not all have. They share: {signature_line(derived)}"]
    weak = signature_weak(chosen)
    if weak:
        return 1, [f"refused: the signature has {weak}. An empty or tiny signature passes every page; mock up the layout and navigation "
                   f"on each screen, or name screens of the same shell. The mock-ups share: {signature_line(derived) or 'nothing'}"]
    lines.append(f"Shell-signature: {signature_line(chosen)}")
    before = rec.read_text(encoding="utf-8") if rec.is_file() else None
    rec.parent.mkdir(parents=True, exist_ok=True)
    rec.write_text("\n".join(lines) + "\n", encoding="utf-8")
    problems = record_problems(root, SHELL_RECORD)
    if problems:
        if before is None:
            rec.unlink()
        else:
            rec.write_text(before, encoding="utf-8")
        return 1, ["refused, nothing written:"] + problems
    return 0, [f"recorded {SHELL_RECORD}: signature {signature_line(chosen)}"] + (
        [f"the mock-ups also share {signature_line([t for t in derived if t not in chosen])}: dropped by --keep"] if chosen != derived else [])


def record_problems(root: Path, rel: str) -> list[str]:
    path = root / rel
    if not path.is_file():
        return [f"{rel}: no such mock-up record"]
    fields = read_fields(path)
    out = [f"{rel}: no `{k}:` line" for k in RECORD_KEYS if not fields.get(k)]
    mock = fields.get("Mock-up", "")
    if mock.startswith("https://"):
        if not re.match(r"^https://[^/\s]+\.[^/\s]+", mock):
            out.append(f"{rel}: Mock-up {mock!r} is not a link to anything")
    elif mock and ((root / mock).resolve() == path.resolve()
                   or ((root / mock).exists() and (root / mock).samefile(path))):
        # `samefile` too: a hard link is the record under another name, and resolve() keeps names (#1479).
        # A record naming itself satisfied "a file under docs/product/mockups/" (#1430).
        out.append(f"{rel}: Mock-up names this record itself; name the mock-up it records")
    elif mock and (root / mock).resolve().suffix.lower() == ".md":
        # ...and so did naming another record. A record is not a mock-up, whatever a symlink calls it
        # -- the RESOLVED target is judged. Any other committed file under the folder is still a
        # mock-up (.gif, .avif, .html.erb): an allow-list refused real ones (review of PR #1478).
        out.append(f"{rel}: Mock-up {mock!r} is a Markdown record, not a mock-up file")
    elif mock and not ((root / mock).is_file() and (mock.startswith(RECORD_DIR) or MOCK_FILE.search(mock))):
        out.append(f"{rel}: Mock-up {mock!r} is neither an https link nor a mock-up file in the repo "
                   f"(under {RECORD_DIR}, or an .html/.png/.jpg/.webp/.pdf/.svg)")
    issue = fields.get("Issue", "")
    if issue and not ISSUE_REF.match(issue):
        out.append(f"{rel}: Issue {issue!r} must name the issue this mock-up answers (#n, or its URL)")
    approval = fields.get("Approval", "")
    if approval and not APPROVAL_URL.match(approval):
        out.append(f"{rel}: Approval must link the comment where the owner approved "
                   f"(…/issues/N#issuecomment-M), got {approval!r}")
    widths = [int(w) for w in re.findall(r"\d+", fields.get("Widths", ""))]
    if fields.get("Widths") and not (any(w <= 480 for w in widths) and any(w >= 1024 for w in widths)):
        out.append(f"{rel}: Widths {fields['Widths']!r} must include a phone width (≤ 480) and a desktop width (≥ 1024)")
    is_shell = fields.get("Kind", "").lower() == "shell"
    if rel == SHELL_RECORD and not is_shell:
        out.append(f"{rel}: the recorded shell must say `Kind: shell`")
    elif is_shell and rel != SHELL_RECORD:
        out.append(f"{rel}: `Kind: shell` belongs only in {SHELL_RECORD}: a project has one shell")
    elif is_shell:
        out += shell_record_problems(root, rel, fields)
    else:
        out += shell_reference_problems(root, rel, fields)
    return out


def run(root: Path, changed: list[str], record: str | None) -> tuple[int, list[str]]:
    """The whole decision. main() and the selftest both come through here."""
    ui = ui_paths(changed)
    if not ui and SHELL_RECORD not in changed:
        return 0, ["no user-visible change: no mock-up needed"]
    if declared_off(root):
        return 0, [f"{len(ui)} user-visible file(s), and GUARDRAILS.md declares `mockup-gate: off`"]
    records = [record] if record else sorted(p for p in changed if p.startswith(RECORD_DIR) and p.endswith(".md")
                                             and Path(p).name.lower() != "readme.md")
    if not records:
        return 1, [f"{len(ui)} user-visible file(s) ({', '.join(ui[:5])}{' …' if len(ui) > 5 else ''}) and no "
                   f"approved mock-up: publish one, stop for the owner's approval, then record it in "
                   f"{RECORD_DIR}<slug>.md"]
    problems = [p for r in records for p in record_problems(root, r)]
    if problems:
        return 1, problems
    what = f"{len(ui)} user-visible file(s); approved mock-up recorded in" if ui else "the recorded shell is valid:"
    notes = [f"{r}: the mock-up is not an HTML file, so only its `Shell:` reference was checked; the reviewer confirms the layout"
             for r in records if reference_only(root, r)]
    return 0, [f"{what} {', '.join(records)}"] + notes


# --------------------------------------------------------------------------- selftest

GOOD = """# Mock-up — invoice bell
Mock-up: https://example.com/mockups/bell
Issue: #12
Approved-by: @owner
Approval: https://github.com/acme/app/issues/12#issuecomment-99
Widths: 1280, 390
States: default, empty, error
Shell: docs/product/mockups/shell.md
"""

# Two screens of one shell: they share header, nav, main#main and #toasts; #screen-a and #screen-b are content (#2211).
SHELL_A = '<html><body><header></header><nav></nav><main id="main"><div id="screen-a"></div></main><div id="toasts"></div></body></html>'
SHELL_B = '<html><body><header></header><nav></nav><main id="main"><div id="screen-b"></div></main><div id="toasts"></div></body></html>'
APPROVAL = "https://github.com/acme/app/issues/1#issuecomment-5"


def selftest() -> int:
    failures: list[str] = []

    def check_that(label: str, ok: bool, detail: object = "") -> None:
        if not ok:
            failures.append(f"{label}{(' — ' + str(detail)) if detail != '' else ''}")

    check_that("a view is UI scope", ui_paths(["app/views/invoices/index.html.erb"]) != [])
    check_that("a component is UI scope", ui_paths(["app/components/bell_component.rb"]) != [])
    check_that("a Stimulus controller is UI scope", ui_paths(["app/javascript/controllers/bell_controller.js"]) != [])
    check_that("a locale file (visible copy) is UI scope", ui_paths(["config/locales/en.yml"]) != [])
    check_that("CONTROL: a model, migration, job and spec are not UI scope",
               ui_paths(["app/models/invoice.rb", "db/migrate/1_x.rb", "app/jobs/sync_job.rb",
                         "spec/models/invoice_spec.rb"]) == [])
    check_that("CONTROL: a JSON template is read by a client, not seen",
               ui_paths(["app/views/api/invoices/show.json.jbuilder"]) == [])
    # Pre-release review of #1381: what Rails 8 generates for a user to see outside app/views.
    check_that("a public error page is UI scope", ui_paths(["public/404.html"]) == ["public/404.html"])
    check_that("the app icon is UI scope", ui_paths(["public/icon.png"]) == ["public/icon.png"])
    check_that("an image asset is UI scope", ui_paths(["app/assets/images/logo.svg"]) != [])
    check_that("the PWA manifest is UI scope although it is JSON",
               ui_paths(["app/views/pwa/manifest.json.erb"]) == ["app/views/pwa/manifest.json.erb"])
    check_that("CONTROL: robots.txt and a public subdirectory file are not UI scope",
               ui_paths(["public/robots.txt", "public/assets/app-1.css"]) == [])
    check_that("a mixed change is UI scope",
               ui_paths(["app/models/invoice.rb", "app/views/invoices/_row.html.erb"]) == ["app/views/invoices/_row.html.erb"])

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rec = root / "docs/product/mockups"
        rec.mkdir(parents=True)
        view = ["app/views/invoices/index.html.erb"]
        (rec / "shell-a.html").write_text(SHELL_A)
        (rec / "shell-b.html").write_text(SHELL_B)
        code, msg = adopt_shell(root, ["docs/product/mockups/shell-a.html", "docs/product/mockups/shell-b.html"],
                                APPROVAL, "@owner", "#1", "1280, 390", "default, collapsed")
        check_that("CONTROL: the fixture shell is adopted (the records below point at it)", code == 0, msg)

        code, _ = run(root, ["app/models/invoice.rb"], None)
        check_that("CONTROL: a backend-only change passes with no record", code == 0)
        code, msg = run(root, view, None)
        check_that("a UI change with no mock-up record is held", code == 1, msg)

        (rec / "bell.md").write_text(GOOD)
        code, msg = run(root, view + ["docs/product/mockups/bell.md"], None)
        check_that("CONTROL: a UI change with a complete, approved record passes", code == 0, msg)
        code, msg = run(root, view, "docs/product/mockups/bell.md")
        check_that("CONTROL: --record names a record the branch did not touch", code == 0, msg)

        def with_record(text: str) -> tuple[int, list[str]]:
            (rec / "r.md").write_text(text)
            return run(root, view + ["docs/product/mockups/r.md"], None)

        code, msg = with_record(GOOD.replace("Approval: https://github.com/acme/app/issues/12#issuecomment-99\n", ""))
        check_that("a record with no approval line is held", code == 1 and any("Approval" in m for m in msg), msg)
        code, msg = with_record(GOOD.replace("https://github.com/acme/app/issues/12#issuecomment-99", "approved in chat"))
        check_that("an approval that is not a comment link is held", code == 1 and any("link the comment" in m for m in msg), msg)
        code, msg = with_record(GOOD.replace("Widths: 1280, 390", "Widths: 1280"))
        check_that("a mock-up with no phone width is held", code == 1 and any("phone width" in m for m in msg), msg)
        code, msg = with_record(GOOD.replace("Widths: 1280, 390", "Widths: 390"))
        check_that("a mock-up with no desktop width is held", code == 1 and any("phone width" in m for m in msg), msg)
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/missing.html"))
        check_that("a mock-up file that does not exist is held", code == 1 and any("neither" in m for m in msg), msg)
        (root / "docs/product/mockups/bell.html").write_text(SHELL_A)    # a mock-up drawn inside the fixture shell (#2211)
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/bell.html"))
        check_that("CONTROL: a committed mock-up file passes", code == 0, msg)

        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "https://"))
        check_that("a bare https:// is not a mock-up", code == 1 and any("not a link" in m for m in msg), msg)
        (root / "GUARDRAILS.md").write_text("x\n")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "GUARDRAILS.md"))
        check_that("an arbitrary repo file is not a mock-up", code == 1 and any("mock-up file" in m for m in msg), msg)
        (root / "notes.txt").write_text("x\n")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "notes.txt"))
        check_that("an arbitrary NON-Markdown repo file outside the folder is not a mock-up",
                   code == 1 and any("neither" in m for m in msg), msg)
        (root / "GUARDRAILS.md").unlink()
        code, msg = with_record(GOOD.replace("Issue: #12", "Issue: the bell one"))
        check_that("a record that names no issue is held", code == 1 and any("Issue" in m for m in msg), msg)
        (rec / "README.md").write_text("# How mock-up records work\n")
        code, msg = run(root, view + ["docs/product/mockups/README.md", "docs/product/mockups/bell.md"], None)
        check_that("CONTROL: a README in the records folder is not a record", code == 0, msg)
        (root / "GUARDRAILS.md").write_text("# Guardrails\n\nTo opt out, add:\n\n```markdown\n- mockup-gate: off\n```\n")
        code, msg = run(root, view, None)
        check_that("a fenced example of the opt-out line is not a declaration", code == 1, msg)
        (root / "GUARDRAILS.md").write_text("# Guardrails\n\n- mockup-gate: off\n")
        code, msg = run(root, view, None)
        check_that("a project that declared the gate off is not held", code == 0, msg)
        (root / "GUARDRAILS.md").write_text("# Guardrails\n\nWe might set mockup-gate: off one day.\n")
        code, msg = run(root, view, None)
        check_that("CONTROL: prose mentioning the key is not a declaration", code == 1, msg)
        # #1430: an opt-out inside an UNTERMINATED fence is still inside a fence.
        (root / "GUARDRAILS.md").write_text("# Guardrails\n\nExample:\n\n```\n- mockup-gate: off\n")
        code, msg = run(root, view, None)
        check_that("#1430: an opt-out inside an unterminated fence is not a declaration", code == 1, msg)
        # #1490: an INDENTED code block is an example too, by CommonMark 0.31.2's rules (verified by
        # doctrine-verifier against spec.txt at tag 0.31.2). Each shape is run through run(), the
        # entry point, so a scanner the gate does not call cannot pass these. (declared, expected).
        O = "mockup-gate: off"
        for label, text, declared in (
            ("an indented code block after a blank line is an example (§4.4)", f"Example:\n\n    - {O}\n", False),
            ("a tab indents to column 4 (§2.2)", f"Example:\n\n\t- {O}\n", False),
            ("a space then a tab is 4 columns, not 5 (§2.2)", f"Example:\n\n \t- {O}\n", False),
            ("CONTROL: 4 spaces directly under a paragraph continue it (Ex 113)", f"Example:\n    {O}\n", True),
            ("CONTROL: 4 spaces under `- Gates:` is a nested item (Ex 294)", f"- Gates:\n    - {O}\n", True),
            ("CONTROL: a nested item after a continuation line stays in the list", f"- Gates:\n  more text\n    - {O}\n", True),
            ("six spaces after a blank line inside an item is code (Ex 270)", f"- Gates:\n\n      {O}\n", False),
            ("CONTROL: an ordered item's content column is 3", f"1. Gates:\n   - {O}\n", True),
            ("CONTROL: a `+` bullet declares", f"+ {O}\n", True),
            ("an indented line after a heading is code (a heading is no paragraph)", f"# Gates\n    - {O}\n", False),
            ("an indented line after a fenced block is code", f"Text\n```\nx\n```\n    - {O}\n", False),
            ("a list ends at a top-level paragraph, and code after it is code", f"- a\n\nPara\n\n    - {O}\n", False),
            ("a non-breaking space is not indentation (§2.1)", f"Example:\n\n\u00a0\u00a0\u00a0\u00a0- {O}\n", False),
            ("CONTROL: three spaces before a top-level marker is still an item (Ex 286)", f"   - {O}\n", True),
            # Discriminating shapes: each is decided by one rule, after a blank line where the paragraph
            # exemption cannot rescue a wrong column.
            ("CONTROL: two spaces then a tab inside an item reach column 4, item text (§2.2)", f"- Gates:\n\n  \t{O}\n", True),
            ("CONTROL: a nested item after a blank line sits at the item's content column", f"- Gates:\n\n    - {O}\n", True),
            ("CONTROL: a lazy line keeps the item open for a nested item below it (Ex 290)", f"- Gates\nlazy text\n\n    - {O}\n", True),
            ("CONTROL: `1.` opens an item whose content column is 3", f"1. Gates:\n\n    - {O}\n", True),
            # PR #1496's review, measured against markdown-it-py (commonmark) over 200k variants:
            ("R1: a heading under an item's text ends the list; the code after it is code",
             f"- Keep specs green\n## Opting out\n\n    - {O}\n", False),
            ("R2: a setext `===` underline makes the paragraph a heading; the line after is code",
             f"Opting out\n==========\n    - {O}\n", False),
            ("R2: a setext `-` underline is a heading, not an empty item", f"Text\n-\n    - {O}\n", False),
            ("R3: an item that starts blank and meets a blank line is empty and closes",
             f"-\n\n    - {O}\n", False),
            ("R4: a heading as an item's content is no paragraph", f"- # H\n      {O}\n", False),
            ("R5: a closing fence indented further than it opened does not close it",
             f"```\nx\n     ```\n- {O}\n", False),
            ("R6: an opt-out inside an HTML comment is hidden", f"<!--\n- {O}\n-->\n", False),
            ("R6: an opt-out inside an HTML block is markup", f"<div>\n- {O}\n</div>\n", False),
            ("R6: a lone tag line opens an HTML block to the blank line", f"</pre>\n- {O}\n", False),
            ("CONTROL: after an HTML block and a blank line the opt-out counts", f"<div>\nx\n</div>\n\n- {O}\n", True),
            ("an empty quote is no paragraph; the indented line after it is code", f">\n    - {O}\n", False),
            ("an item opening with 5+ columns opens with code, so the next line is code too",
             f"-     five\n      {O}\n", False),
            ("CONTROL: `1)` opens an item whose content column is 3", f"1) Gates:\n\n    - {O}\n", True),
            # Round 2 of #1496's review: a block at column 0 after a list closes the list.
            ("a column-0 fence after a list closes it; the indented example after is code",
             f"- Keep specs green\n\n```bash\nbin/ci\n```\n\n    - {O}\n", False),
            ("a column-0 HTML comment after a list closes it",
             f"- Keep specs green\n\n<!-- opt-out example -->\n\n    - {O}\n", False),
            ("a column-0 <details> block after a list closes it",
             f"- Keep specs green\n\n<details>\nx\n</details>\n\n    - {O}\n", False),
            # #1501: the container shapes the two line passes could not see (each checked against
            # commonmark.js 0.31.2). Indented under a `10.` item, a tab is still four columns.
            ("#1501: a fence opener indented 4+ is indented code, so the text after it is text",
             f"    ```\n    x\n\n- {O}\n", True),
            ("#1501: an unclosed fence inside an item ends with the item", f"- a\n  ```\n  x\n\n- {O}\n", True),
            ("#1501: a fence inside an item that closes at column 0 still closes it",
             f"- a\n  ```\n  x\n```\n\n    - {O}\n", False),
            ("#1501: an HTML block nested in an item hides its lines", f"- a\n\n  <div>\n  - {O}\n  </div>\n", False),
            ("#1501: a quote nested in an item: an opt-out in its paragraph is text, not code",
             f"- a\n  > - {O}\n", False),
            ("#1501 CONTROL: a lazy `    - e` under `   - d` is paragraph text (Ex 312)",
             f"   - item\n    - {O}\n", True),
            ("#1501: an empty quote line is blank inside the quote; the indented line after is code",
             f"> - item\n>\n>     - {O}\n", False),
            ("#1501: a `10.` item's content column is 4; a tab-indented line under it is item text",
             f"10. Gates:\n\n\t- {O}\n", True),
            ("#1501: a type-1 block ends at ANY of the four closing tags (§4.6)", f"<pre>\nx\n</script>\n\n- {O}\n", True),
            ("#1501: `2.` cannot interrupt a paragraph, so no item opens and the code after is code (§5.2)",
             f"Text\n2. Gates:\n\n    - {O}\n", False),
            ("#1501: a lone tag cannot interrupt a paragraph, so the item after it is text (§4.6 type 7)",
             f"Text\n<custom-el>\n- {O}\n", True),
            ("#1501: an indented line after a thematic break is code", f"***\n    - {O}\n", False),
            # Found by mutation-driven differential fuzz against commonmark.js 0.31.2 (#1501): each
            # is the shortest input where one broken rule changes the verdict.
            ("#1501: a ~~~ line does not close a backtick fence", f"```\n~~~\n- {O}\n```\n", False),
            ("#1501 CONTROL: a fence ends with its item, so a later sibling item declares",
             f"- a\n  ```\n  x\n- b\n- {O}\n", True),
            ("#1501 CONTROL: a fence in a quote ends when a blank line closes the quote",
             f"> ```\n> x\n\n- {O}\n", True),
            ("#1501: a quote holding a list, then an indented <pre>, opens an HTML block",
             f"\t <pre>\n> - item\n  <pre>\n- {O}\n", False),
            ("#1501: a quote line holding only `>` and spaces is blank in the quote",
             f"> quote\n\t >\n>\n      `{O}`\n", False),
            ("#1501: a fence indented one space still opens", f" ```\n- {O}\n", False),
            # PR #1512's review: where Python's notion of blank, digit or space is not commonmark.js's.
            ("#1512 CONTROL: a comment that closes on its own line ends there", f"<!-- note -->\n- {O}\n", True),
            ("#1512 CONTROL: a comment ends at `-->` on a later line", f"<!--\nnote\n-->\n- {O}\n", True),
            ("#1512 B1: a no-break-space line is not blank, so the HTML block runs on", f"<div>\n\u00a0\n- {O}\n", False),
            ("#1512 B1 CONTROL: a no-break-space line does not end a paragraph", f"Example:\n\u00a0\n    - {O}\n", True),
            ("#1512: a form-feed line is not blank: it opens a paragraph, so the indented line continues it",
             f"\f\n    - {O}\n", True),
            ("#1512 B2: an Arabic-Indic digit opens no list item", f"\u0661. Gates:\n\n    - {O}\n", False),
            ("#1512 B3: a lone tag followed by a no-break space opens an HTML block", f"<img src=\"x.png\">\u00a0\n- {O}\n", False),
            ("#1512 B4: quote continuation keeps the quote's paragraph open for a lazy line",
             f"> x\n>     y\n    - {O}\n", True),
            ("#1512 R1: a lazy line ends a definitions-only paragraph, so a setext underline applies",
             f">[f]:\"\nl\n>-\n    - {O}\n", False),
            ("#1512 S1: a paragraph of only reference definitions takes no setext underline",
             f"[a]: /u\n===\n    - {O}\n", True),
            ("CONTROL: a fence INSIDE the item keeps the item open for a nested item",
             f"- Gates:\n\n  ```bash\n  bin/ci\n  ```\n\n    - {O}\n", True),
        ):
            (root / "GUARDRAILS.md").write_text(f"# Guardrails\n\n{text}", encoding="utf-8")
            code, msg = run(root, view, None)
            check_that(f"#1490: {label}", (code == 0) == declared, (code, msg))
        # R8: the line `/rails-flow:setup-flow` scaffolds must still declare -- read from the shipped
        # command itself, not retyped, so a doc edit that breaks it fails here.
        setup = Path(__file__).resolve().parents[1] / "commands" / "setup-flow.md"
        if setup.is_file():
            block = re.search(r"```markdown\n(- mockup-gate: off\n)```", setup.read_text(encoding="utf-8"))
            check_that("the scaffolded opt-out block is present in setup-flow.md", bool(block), setup)
            if block:
                (root / "GUARDRAILS.md").write_text("# Guardrails\n\n" + block.group(1), encoding="utf-8")
                code, msg = run(root, view, None)
                check_that("CONTROL: the opt-out setup-flow scaffolds still declares", code == 0, (code, msg))
        (root / "GUARDRAILS.md").write_text("# Guardrails\n\n```\nexample\n```\n\n- mockup-gate: off\n")
        code, msg = run(root, view, None)
        check_that("#1430 CONTROL: an opt-out AFTER a closed fence still declares", code == 0, msg)
        (root / "GUARDRAILS.md").unlink()
        # #1430: a record may not name itself, or another record, as its mock-up.
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/r.md"))
        check_that("#1430: a record naming itself is held", code == 1 and any("itself" in m for m in msg), msg)
        # #1479: a HARD LINK is the record under another name; resolve() keeps the name, samefile
        # does not. Named .html so the Markdown-record rule cannot be what holds it. Portable to Linux.
        (rec / "r.md").write_text(GOOD)
        alias = rec / "r-alias.html"
        alias.unlink(missing_ok=True)
        os.link(rec / "r.md", alias)
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/r-alias.html"))
        check_that("#1479: a record naming itself by another name is held",
                   code == 1 and any("itself" in m for m in msg), msg)
        alias.unlink()
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/bell.md"))
        check_that("#1430: a record naming another record is held", code == 1 and any("Markdown record" in m for m in msg), msg)
        (root / "docs/product/mockups/bell.svg").write_text("<svg/>")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/bell.svg"))
        check_that("#1430 CONTROL: a committed .svg mock-up passes", code == 0, msg)
        (root / "design").mkdir(exist_ok=True)
        (root / "design/bell.svg").write_text("<svg/>")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "design/bell.svg"))
        check_that("#1430: an .svg mock-up OUTSIDE the records folder is a mock-up file", code == 0, msg)
        # Review of PR #1478: an allow-list refused real mock-ups committed under the folder.
        for name in ("bell.gif", "bell.avif", "bell.html.erb"):
            (root / "docs/product/mockups" / name).write_text("x")
            code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", f"docs/product/mockups/{name}"))
            check_that(f"PR #1478 review: a committed {name} under the folder is a mock-up", code == 0, msg)
        # ...and a symlink is judged by its TARGET: o.html -> bell.md is a record, not a mock-up.
        (root / "docs/product/mockups/o.html").symlink_to("bell.md")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/o.html"))
        check_that("PR #1478 review: a symlink onto a record is held", code == 1 and any("Markdown record" in m for m in msg), msg)
        # An example opt-out in an INDENTED fence (inside a list item) is still an example.
        (root / "GUARDRAILS.md").write_text("# G\n\n- Example:\n\n    ```\n    - mockup-gate: off\n    ```\n")
        code, msg = run(root, view, None)
        check_that("PR #1478 review: an opt-out in an indented fence is not a declaration", code == 1, msg)
        # Final review: a line OPENING with an inline code span is not a fence.
        (root / "GUARDRAILS.md").write_text("# G\n\n```x``` inline\n\n- mockup-gate: off\n")
        code, msg = run(root, view, None)
        check_that("PR #1478 final review: a code span at line start does not fence the opt-out", code == 0, msg)
        (root / "GUARDRAILS.md").write_text("# G\n\n```sh\n- mockup-gate: off\n```\n")
        code, msg = run(root, view, None)
        check_that("PR #1478 final review CONTROL: an info-string fence still fences", code == 1, msg)
        (root / "GUARDRAILS.md").unlink()

    # The shell (#2211). A FRESH root per question; every case runs through run() or adopt_shell(), the entry points.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rec = root / "docs/product/mockups"
        rec.mkdir(parents=True)
        view = ["app/views/invoices/index.html.erb"]
        SHELL = "docs/product/mockups/shell.md"
        A, B = "docs/product/mockups/shell-a.html", "docs/product/mockups/shell-b.html"

        def put(name: str, text: str) -> None:
            (rec / name).write_text(text)

        def feature(mock: str, record_text: str | None = None) -> tuple[int, list[str]]:
            (rec / "f.md").write_text(record_text or GOOD.replace("https://example.com/mockups/bell", mock))
            return run(root, view + ["docs/product/mockups/f.md"], None)

        put("shell-a.html", SHELL_A)
        put("shell-b.html", SHELL_B)
        put("on-shell.html", SHELL_A.replace("screen-a", "other"))
        # Rule 2: no recorded shell. A UI change with a feature record is held; the message says what to do.
        code, msg = feature("docs/product/mockups/on-shell.html")
        check_that("#2211: with no recorded shell a feature record is held, and the message names the way out",
                   code == 1 and any("no recorded shell" in m and "--adopt-shell" in m for m in msg), msg)
        # --adopt-shell refuses what cannot be a shell.
        code, msg = adopt_shell(root, [A], APPROVAL, "@owner", "#1", "1280, 390", "default")
        check_that("#2211: one source is refused (a shell is what two screens share)", code == 1 and not (root / SHELL).exists(), msg)
        code, msg = adopt_shell(root, [A, A], APPROVAL, "@owner", "#1", "1280, 390", "default")
        check_that("#2211: the same file twice is one source, refused", code == 1 and not (root / SHELL).exists(), msg)
        code, msg = adopt_shell(root, [A, "docs/product/mockups/nope.html"], APPROVAL, "@owner", "#1", "1280, 390", "default")
        check_that("#2211: a source that does not exist is refused", code == 1 and not (root / SHELL).exists(), msg)
        put("bare-a.html", "<html><body><div id='x'>a</div></body></html>")
        put("bare-b.html", "<html><body><div id='y'>b</div></body></html>")
        code, msg = adopt_shell(root, ["docs/product/mockups/bare-a.html", "docs/product/mockups/bare-b.html"],
                                APPROVAL, "@owner", "#1", "1280, 390", "default")
        check_that("#2211: two screens sharing nothing give an EMPTY signature, which passes every page: refused",
                   code == 1 and not (root / SHELL).exists() and any("no `main`" in m for m in msg), msg)
        put("thin-a.html", "<html><body><main>a</main></body></html>")
        put("thin-b.html", "<html><body><main>b</main></body></html>")
        code, msg = adopt_shell(root, ["docs/product/mockups/thin-a.html", "docs/product/mockups/thin-b.html"],
                                APPROVAL, "@owner", "#1", "1280, 390", "default")
        check_that("#2211: a signature of `main` alone is too small: refused",
                   code == 1 and not (root / SHELL).exists() and any("fewer than" in m for m in msg), msg)
        code, msg = adopt_shell(root, [A, B], "approved in chat", "@owner", "#1", "1280, 390", "default")
        check_that("#2211: an adoption with no approval link writes nothing", code == 1 and not (root / SHELL).exists(), msg)
        code, msg = adopt_shell(root, [A, B], APPROVAL, "@owner", "#1", "1280, 390", "default")
        check_that("#2211 CONTROL: two screens of one shell are adopted", code == 0 and (root / SHELL).is_file(), msg)
        check_that("#2211: the derived signature drops each screen's own content",
                   "Shell-signature: #main, #toasts, header, main, nav" in (root / SHELL).read_text(), (root / SHELL).read_text())

        # --keep narrows to some of what the sources share, and cannot add.
        full_record = (root / SHELL).read_text()
        code, msg = adopt_shell(root, [A, B], APPROVAL, "@owner", "#1", "1280, 390", "default", keep=["header", "main", "nav"])
        check_that("#2211: --keep records only the tokens kept", code == 0 and "Shell-signature: header, main, nav" in (root / SHELL).read_text(), msg)
        put("no-toasts.html", SHELL_A.replace('<div id="toasts"></div>', ""))
        code, msg = feature("docs/product/mockups/no-toasts.html")
        check_that("#2211: a token dropped by --keep is no longer required", code == 0, msg)
        code, msg = adopt_shell(root, [A, B], APPROVAL, "@owner", "#1", "1280, 390", "default", keep=["header", "main", "nav", "#sidebar"])
        check_that("#2211: --keep naming a token the screens do not share is refused", code == 1 and any("do not all have" in m and "#sidebar" in m for m in msg), msg)
        code, msg = adopt_shell(root, [A, B], APPROVAL, "@owner", "#1", "1280, 390", "default", keep=["main", "nav"])
        check_that("#2211: --keep down to two tokens is refused", code == 1 and any("passes every page" in m for m in msg), msg)
        (root / SHELL).write_text(full_record)
        code, msg = feature("docs/product/mockups/on-shell.html")
        check_that("#2211 CONTROL: a mock-up that holds the whole signature passes", code == 0, msg)
        put("no-toasts.html", SHELL_A.replace('<div id="toasts"></div>', ""))
        code, msg = feature("docs/product/mockups/no-toasts.html")
        check_that("#2211: a mock-up missing one shell element is held, and names it",
                   code == 1 and any("#toasts" in m for m in msg), msg)
        put("free.html", "<html><body><main><div id='screen-a'>just a card</div></main></body></html>")
        code, msg = feature("docs/product/mockups/free.html")
        check_that("#2211: a free-standing screen is held", code == 1 and any("not drawn inside" in m for m in msg), msg)
        # Near misses: the tokens appear, but not as elements.
        put("prose.html", "<html><body><main>the nav and header and #toasts and #main</main></body></html>")
        code, msg = feature("docs/product/mockups/prose.html")
        check_that("#2211 near miss: the shell's words in text are not its elements", code == 1, msg)
        put("commented.html", "<html><body><!-- <header></header><nav></nav><div id=\"toasts\"></div> --><main id=\"main\"></main></body></html>")
        code, msg = feature("docs/product/mockups/commented.html")
        check_that("#2211 near miss: elements inside a comment are not elements", code == 1, msg)
        put("scripted.html", "<html><body><script>var s='<header></header><nav></nav><div id=\"toasts\"></div>';</script><main id=\"main\"></main></body></html>")
        code, msg = feature("docs/product/mockups/scripted.html")
        check_that("#2211 near miss: markup inside a script string is not elements", code == 1, msg)
        put("boarded.html", "<html><body><main id=\"main\"><template id=\"t\"><header></header><nav></nav><div id=\"toasts\"></div></template></main></body></html>")
        code, msg = feature("docs/product/mockups/boarded.html")
        check_that("#2211 CONTROL: a mock-up board keeps its screens in <template>, and those elements count", code == 0, msg)
        # A mock-up that is not HTML: the reference is all that can be checked, and the output says so.
        (rec / "card.png").write_bytes(b"\x89PNG")
        code, msg = feature("docs/product/mockups/card.png")
        check_that("#2211: an image mock-up passes on the reference alone, and says it was not checked",
                   code == 0 and any("only its `Shell:` reference" in m for m in msg), msg)
        code, msg = feature("x", GOOD.replace("Shell: docs/product/mockups/shell.md\n", "").replace("https://example.com/mockups/bell", "docs/product/mockups/card.png"))
        check_that("#2211: a record with no Shell line is held, whatever its mock-up", code == 1 and any("no `Shell:" in m for m in msg), msg)
        code, msg = feature("x", GOOD.replace("Shell: docs/product/mockups/shell.md", "Shell: docs/product/mockups/other.md").replace("https://example.com/mockups/bell", "docs/product/mockups/card.png"))
        check_that("#2211: a record naming another file as the shell is held", code == 1 and any("must be" in m for m in msg), msg)
        # Drift: a source changed after adoption, and a hand-typed signature.
        put("shell-b.html", SHELL_B.replace("<nav></nav>", ""))
        code, msg = feature("docs/product/mockups/on-shell.html")
        check_that("#2211: a source edited after adoption is a drift, held", code == 1 and any("no longer share" in m for m in msg), msg)
        put("shell-b.html", SHELL_B)
        text = (root / SHELL).read_text()
        (root / SHELL).write_text(text.replace("Shell-signature: #main, #toasts, header, main, nav", "Shell-signature: main"))
        code, msg = feature("docs/product/mockups/on-shell.html")
        check_that("#2211: a hand-typed signature too small to be a shell is held", code == 1 and any("cannot tell" in m for m in msg), msg)
        (root / SHELL).write_text(text.replace("Shell-signature: #main, #toasts, header, main, nav", "Shell-signature: #main, #sidebar, #toasts, header, main, nav"))
        code, msg = feature("docs/product/mockups/on-shell.html")
        check_that("#2211: a hand-typed token the sources do not share is held", code == 1 and any("no longer share" in m and "#sidebar" in m for m in msg), msg)
        (root / SHELL).write_text(text.replace("Shell-sources: " + A + ", " + B, "Shell-sources: " + A))
        code, msg = feature("docs/product/mockups/on-shell.html")
        check_that("#2211: a shell record that lists one source is held", code == 1 and any("two or more" in m for m in msg), msg)
        (root / SHELL).write_text(text.replace("Kind: shell\n", ""))
        code, msg = feature("docs/product/mockups/on-shell.html")
        check_that("#2211: the shell record without `Kind: shell` is held", code == 1 and any("Kind: shell" in m for m in msg), msg)
        (root / SHELL).write_text(text)
        # Changing the shell record is judged on its own, with no UI file in the change.
        code, msg = run(root, [SHELL], None)
        check_that("#2211 CONTROL: a change that only touches a valid shell record passes", code == 0, msg)
        (root / SHELL).write_text(text.replace("Shell-signature: #main, #toasts, header, main, nav", "Shell-signature: main"))
        code, msg = run(root, [SHELL], None)
        check_that("#2211: a change that only touches a broken shell record is held, with no UI file in it", code == 1, msg)
        (root / SHELL).write_text(text)
        # Kind: shell anywhere else would be a second shell.
        code, msg = feature("x", text.replace("Mock-up: docs/product/mockups/shell-a.html", "Mock-up: docs/product/mockups/on-shell.html"))
        check_that("#2211: `Kind: shell` in another record is held", code == 1 and any("belongs only" in m for m in msg), msg)
        # A source outside the repository is not read.
        with tempfile.TemporaryDirectory() as elsewhere:     # its own directory: mutants run in parallel
            outside = Path(elsewhere) / "outside-shell.html"
            outside.write_text(SHELL_A)
            (rec / "link.html").symlink_to(outside)
            code, msg = adopt_shell(root, [A, "docs/product/mockups/link.html"], APPROVAL, "@owner", "#1", "1280, 390", "default")
            check_that("#2211: a source that resolves outside the repo is refused", code == 1, msg)
        # The opt-out still switches the whole gate off, shell included.
        (root / "GUARDRAILS.md").write_text("# G\n\n- mockup-gate: off\n")
        (root / SHELL).unlink()
        code, msg = feature("docs/product/mockups/free.html")
        check_that("#2211 CONTROL: `mockup-gate: off` holds nothing, with or without a shell", code == 0, msg)

    # The git path main() takes: a new, untracked view must count (the #1341 blind spot). A FRESH
    # directory: the one above holds untracked records, which would rightly count as on the branch.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        import sys as _sys; _sys.path.insert(0, str(Path(__file__).resolve().parent)); import fixture_git as _fg  # #1588
        def git(*a: str) -> None:
            _fg.init(root, *a[2:]) if a[:2] == ("init", "-q") else _fg.run(root, *a)   # bound to this temp repo (#1588)
        git("init", "-q", "-b", "dev")
        (root / "README.md").write_text("x\n"); git("add", "README.md"); git("commit", "-qm", "base")
        git("checkout", "-q", "-b", "feature")
        (root / "app/views/invoices").mkdir(parents=True)
        (root / "app/views/invoices/index.html.erb").write_text("<table></table>\n")   # untracked
        code, msg = run(root, list(diff(root, "dev")), None)
        check_that("an untracked new view, read through the diff, is held", code == 1, msg)
        try:
            diff(root, "no-such-base")
            check_that("an unresolvable base is unusable", False)
        except Unusable:
            pass

    for f in failures:
        print(f"selftest FAIL: {f}")
    print(f"check_mockup_gate selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_mockup_gate.py", description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="dev")
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--paths", nargs="+", help="the plan's files, instead of the branch's diff")
    ap.add_argument("--record", help=f"the mock-up record, when the branch does not touch one ({RECORD_DIR}<slug>.md)")
    ap.add_argument("--adopt-shell", nargs="+", metavar="SRC.html",
                    help=f"record the app's shell from two or more approved HTML mock-ups of different screens ({SHELL_RECORD}, #2211)")
    ap.add_argument("--keep", help="with --adopt-shell: comma-separated tokens to keep of what the mock-ups share (drops content ids two screens "
                                   "happen to have in common; it cannot add a token)")
    for flag in ("approval", "approved-by", "issue", "widths", "states"):
        ap.add_argument(f"--{flag}", help="with --adopt-shell: the value of the record's line of that name")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.adopt_shell:
        missing = [f for f in ("approval", "approved_by", "issue", "widths", "states") if not getattr(a, f)]
        if missing:
            print("--adopt-shell also needs " + ", ".join("--" + m.replace("_", "-") for m in missing), file=sys.stderr)
            return 2
        root = a.root.resolve()
        def inside(x: str) -> str:
            try:
                return Path(x).resolve().relative_to(root).as_posix()
            except ValueError:
                return x            # outside the repo: adopt_shell refuses it by name
        srcs = [inside(x) for x in a.adopt_shell]
        code, lines = adopt_shell(root, srcs, a.approval, a.approved_by, a.issue, a.widths, a.states,
                                  [t.strip() for t in a.keep.split(',') if t.strip()] if a.keep else None)
        print(("SHELL: refused -- " if code else "SHELL: ok -- ") + lines[0])
        for line in lines[1:]:
            print(f"  {line}")
        return code
    try:
        changed = a.paths if a.paths else list(diff(a.root, a.base))
    except Unusable as exc:
        print(f"UNUSABLE: {exc} -- an unclassified change is not exempt; ask the owner", file=sys.stderr)
        return 2
    code, lines = run(a.root, changed, a.record)
    print(("MOCK-UP GATE: HOLD -- " if code else "MOCK-UP GATE: ok -- ") + lines[0])
    for line in lines[1:]:
        print(f"  {line}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
