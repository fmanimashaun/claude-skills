#!/usr/bin/env python3
"""A CONFIRMED verdict may quote only what the cited page says. This fetches the page and checks, phrase by phrase. (#2233)

Run:  python3 scripts/check_verdict_quotes.py AUDIT.md [...]     # every `quotes` block in the file(s): fetch each URL, match each phrase
      python3 scripts/check_verdict_quotes.py --format-check      # offline: each CONFIRMED verdict of a new audit carries its quotes or a reasoned waiver
      python3 scripts/check_verdict_quotes.py --legacy [FILE...]  # the audits written before this gate: heuristic (url, quote) pairs, a report
      python3 scripts/check_verdict_quotes.py --selftest

WHY. `doctrine-verifier` is the gate in CLAUDE.md: no skill claim is edited without its CONFIRMED verdict. It read pages through a summarising
fetch, so it could CONFIRM a quote that was a paraphrase, or text from a page it never saw. #2220 measured it: of 49 quoted phrases, six were not
on the cited page (a GOV.UK sentence quoted from the wrong page; a Polaris claim CONFIRMED from a page that serves only a JavaScript shell). A gate
that can confirm a quote the source does not contain cannot fail. This is the check that can.

THE RECORD. Every verdict line of an audit (`Verdict: CONFIRMED`, or a table row with a cell that is exactly CONFIRMED, in any case) carries `[quotes: C1]`
and the audit holds a fenced block of that id, one quote per line, three fields split by ` | `, none empty:

    | C1 | the claim | CONFIRMED | [quotes: C1] |

    ```quotes C1
    https://design-system.service.gov.uk/patterns/validation | page read 2026-10-21 | show an error summary component at the top of the page
    ```

URL, the version or date in scope, and the exact phrase. The phrase is matched against the page's RAW text, never a summary of it. A verdict whose
evidence is source in this repository has no page to match: it says `[waived: <the reason, at least 20 characters>]` instead. One block or one waiver
covers one verdict, never a second.

THE MATCH (the procedure 4a used on the #2220 claims, written down): fetch the raw page with a plain GET; keep only what a reader sees: drop `<head>`
(its `<title>` too), `<script>` (an unclosed one runs to the end of the file), `<style>`, `<noscript>`, `<template>`, `<svg>`, comments, and any element
with `hidden`, `aria-hidden="true"` or an inline `display:none` / `visibility:hidden`, with everything inside it; strip the tags; unescape entities;
normalise (NFKC, curly quotes and dashes to ASCII, non-breaking and zero-width spaces, runs of whitespace to one space); then the phrase, normalised the
same way, must appear as a substring. Case is NOT folded: "Always show" is not "always show".

EXIT CODES
  0  every phrase is on its page.
  1  a phrase is absent from its page: the verdict is refused. The output names the phrase and the URL.
  2  it cannot judge: the page could not be fetched, it REDIRECTED (the page read is not the page cited: cite the final URL, and check the version it
     describes), or it serves no text of its own (a JavaScript shell). The verdict is INCONCLUSIVE ("rendered page; not verified"), never CONFIRMED.
  A page that is missing (exit 2) and a phrase that is missing (exit 1) are different answers; 1 wins when both occur.

LIMITS. A match proves the phrase is on the page, not that the page is the right authority, nor that the version in scope is the one the page
describes: the verifier still states both. A shell is recognised by how little text the page has (SHELL_MIN_CHARS), so a very short real page
reads as INCONCLUSIVE: that errs toward refusing. An inline tag is removed without a space, so two words a page joins only by markup (`foo<b>bar</b>`)
read as one word, where a reader may see two; and text a stylesheet hides (a class, not an inline style) is counted as visible. Both err toward
accepting a phrase the reader could not read, so a phrase that matters should be checked on the page by eye as well.
A verdict written as a CODE (`C`, `OK`, a tick) cannot slip past: `--format-check` refuses any `Verdict:` line, or cell in a column headed Verdict, of a new
audit whose value is not CONFIRMED, REFUTED or INCONCLUSIVE. A verdict written in PROSE, or in a table with no Verdict column and no cell that is exactly
CONFIRMED, is not a verdict to this check.

Stdlib only. Fetching needs a network, so this is a verifier's tool and the maintainer's, not a gate that runs in CI; the gate is `--format-check`
and `--selftest`, which are offline.
"""
from __future__ import annotations

import argparse
import re
import sys
import tempfile
import threading
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
AUDITS = "docs/evidence/audits"
SHELL_MIN_CHARS = 400          # a page whose own text is shorter than this is a shell, or too short to verify anything against
# The audits that existed before this check: they are not held to the quotes format. FROZEN: an audit not named here is new, whatever its file name says
# (a back-dated or undated name does not make it old), and the list is never extended: a new audit carries its quotes.
LEGACY_AUDITS = frozenset((
    "2026-07-21-framework-gap-audit.md",
    "2026-09-16-no-enterprise-manual.md",
    "2026-10-02-mods-api-2.1.287.md",
    "2026-10-07-mods-tool-call-ratelimits-2.1.292.md",
    "2026-10-09-mods-command-run-clear-2.1.292.md",
    "2026-10-10-haiku-55-effort-advisor-verdict.md",
    "2026-10-10-model-tiers-refresh-1681.md",
    "2026-10-10-pwa-doctrine-1750.md",
    "2026-10-10-rails-8-1-8-2-doctrine-verification.md",
    "2026-10-11-github-rulesets-free-private-403-1872.md",
    "2026-10-11-hook-environment-1843.md",
    "2026-10-11-mcp-annotations-gate-1882.md",
    "2026-10-11-mission-control-1816.md",
    "2026-10-11-observability-otel-1694.md",
    "2026-10-12-hotwire-audit.md",
    "2026-10-12-pipeline-design-flow-audit.md",
    "2026-10-12-qa-flow-audit.md",
    "2026-10-12-rails-8-2-readiness-round-2.md",
    "2026-10-12-rails-flow-commands-agents-claims.md",
    "2026-10-12-test-preflight-threat-model-1821.md",
    "2026-10-14-agent-surface-read-research.md",
    "2026-10-14-agent-surface-write-research.md",
    "2026-10-14-mcp-authorization-2035.md",
    "2026-10-14-mcp-server-tool-design-2033.md",
    "2026-10-14-observability-postgres-2037.md",
    "2026-10-14-production-monitoring-research.md",
    "2026-10-14-rails-8-fix-menu-2039.md",
    "2026-10-14-worktree-teardown-2058.md",
    "2026-10-14-write-tools-epic-review.md",
    "2026-10-16-observability-postgres-index-bloat-2045.md",
    "2026-10-16-postgres-18-baseline-2057.md",
    "2026-10-16-postgres-inconclusive-2107.md",
    "raw/2026-10-11-mission-control-1816-verifier.md",
    "raw/2026-10-11-observability-otel-1694-verifier-1.md",
    "raw/2026-10-11-observability-otel-1694-verifier-2.md",
    "raw/2026-10-11-observability-otel-1694-verifier-3.md",
    "raw/2026-10-11-observability-otel-1694-verifier-4.md",
    "raw/2026-10-12-hotwire-audit-native.md",
    "raw/2026-10-12-hotwire-audit-production.md",
    "raw/2026-10-12-hotwire-audit-stimulus.md",
    "raw/2026-10-12-hotwire-audit-turbo.md",
    "raw/2026-10-16-postgres-index-bloat-2045-runs.md",
))
USER_AGENT = "claude-skills-verdict-quote-check/1 (+https://github.com/fmanimashaun/claude-skills)"
TIMEOUT = 25

MATCH, ABSENT, SHELL, UNFETCHABLE = "match", "absent", "shell", "unfetchable"


# ---------------------------------------------------------------------------------------------
# Normalising: one function for the page and the phrase, so they can only differ by what is written
# ---------------------------------------------------------------------------------------------

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−"), "-")
_QUOTES = {ord(c): "'" for c in "‘’‚‛′"} | {ord(c): '"' for c in "“”„‟″"}
_SPACES = dict.fromkeys(map(ord, "\u00a0\u2002\u2003\u2009\u200a\u202f\u200b\u200c\u200d\u2060\ufeff"), " ")


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_QUOTES).translate(_DASHES).translate(_SPACES)
    return re.sub(r"\s+", " ", text).strip()


_BLOCK_TAGS = frozenset("p div li ul ol br hr h1 h2 h3 h4 h5 h6 tr td th table thead tbody section article aside header footer nav main pre blockquote dt dd dl "
                        "figure figcaption form details summary".split())
_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_NEVER_VISIBLE = frozenset("head script style noscript template svg title".split())
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)


class _Text(HTMLParser):
    """The text a reader of the page sees. Not visible: <head> (its <title> included), <script>, <style>, <noscript>, <template>, <svg>, an element with
    `hidden`, `aria-hidden="true"` or an inline `display:none` / `visibility:hidden`, and anything inside one. An unclosed <script> runs to the end of
    the file (the parser never leaves it). An inline tag is removed without a space (`<code>1</code>,` reads `1,`), a block tag is a break."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.stack: list[tuple[str, bool]] = []     # (tag, hides what is inside it)

    def _hidden(self) -> bool:
        return any(h for _, h in self.stack)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        a = {k: (v or "") for k, v in attrs}
        hides = (tag in _NEVER_VISIBLE or "hidden" in a or a.get("aria-hidden", "").lower() == "true" or bool(_HIDDEN_STYLE.search(a.get("style", ""))))
        if tag in _BLOCK_TAGS and not self._hidden():
            self.parts.append(" ")
        if tag not in _VOID:
            self.stack.append((tag, hides))

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        if tag in _BLOCK_TAGS and not self._hidden():
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break
        if tag in _BLOCK_TAGS and not self._hidden():
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._hidden():
            self.parts.append(data)


def visible_text(raw: str, is_html: bool) -> str:
    """The text a reader of the raw page would see, normalised. A non-HTML body (raw source, Markdown) is its own text."""
    if not is_html:
        return normalise(raw)
    parser = _Text()
    parser.feed(raw)
    parser.close()
    return normalise("".join(parser.parts))


# ---------------------------------------------------------------------------------------------
# Fetching and judging
# ---------------------------------------------------------------------------------------------

@dataclass
class Page:
    text: str          # normalised visible text
    is_shell: bool
    error: str = ""


def fetch(url: str) -> Page:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:       # noqa: S310 (a verifier reads public docs by URL)
            if r.geturl() != url:
                return Page("", False, f"redirected to {r.geturl()}: cite the final URL, and check the version it describes")
            kind = r.headers.get("Content-Type", "")
            body = r.read(8_000_000).decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return Page("", False, f"{exc}")
    is_html = "html" in kind.lower() or body.lstrip()[:15].lower().startswith(("<!doctype", "<html"))
    text = visible_text(body, is_html)
    return Page(text, is_html and len(text) < SHELL_MIN_CHARS)


def judge(url: str, phrase: str, page: Page) -> str:
    if page.error:
        return UNFETCHABLE
    if page.is_shell:
        return SHELL
    return MATCH if normalise(phrase) in page.text else ABSENT


@dataclass
class Quote:
    url: str
    scope: str
    phrase: str
    where: str          # file:line, for the report
    ident: str = ""     # the id of the ```quotes block it sits in


def parse_blocks(text: str, where: str) -> tuple[list[Quote], list[str]]:
    """The quotes in every ```quotes ID block, and the lines that are not three ` | ` fields (a malformed record, or an empty version/date field, is
    refused, not skipped)."""
    quotes: list[Quote] = []
    bad: list[str] = []
    ident: str | None = None
    for n, line in enumerate(text.splitlines(), 1):
        opener = re.match(r"^\s*```quotes(?:\s+(\S+))?\s*$", line)
        if ident is None and opener:
            ident = opener.group(1) or ""
            continue
        if ident is not None and re.match(r"^\s*```\s*$", line):
            ident = None
            continue
        if ident is None or not line.strip():
            continue
        parts = [p.strip() for p in line.split(" | ", 2)]
        if len(parts) != 3 or not parts[0].startswith(("http://", "https://")) or not parts[1] or not parts[2]:
            bad.append(f"{where}:{n}: not `url | version or date | phrase` with all three filled: {line.strip()[:90]}")
            continue
        quotes.append(Quote(parts[0], parts[1], parts[2], f"{where}:{n}", ident))
    return quotes, bad


def check_quotes(quotes: list[Quote], fetcher=fetch) -> tuple[int, list[str]]:
    """(exit code, report lines). Pages are fetched once each."""
    pages: dict[str, Page] = {}
    absent: list[str] = []
    cannot: list[str] = []
    for q in quotes:
        if q.url not in pages:
            pages[q.url] = fetcher(q.url)
        page = pages[q.url]
        result = judge(q.url, q.phrase, page)
        if result == ABSENT:
            absent.append(f"ABSENT {q.where}: \"{q.phrase[:100]}\" is not on {q.url}")
        elif result == SHELL:
            cannot.append(f"INCONCLUSIVE {q.where}: {q.url} serves no text of its own (a JavaScript shell): rendered page; not verified")
        elif result == UNFETCHABLE:
            cannot.append(f"INCONCLUSIVE {q.where}: {q.url} could not be fetched ({page.error})")
    code = 1 if absent else 2 if cannot else 0
    return code, absent + sorted(set(cannot))


# ---------------------------------------------------------------------------------------------
# The format check (offline) and the legacy report
# ---------------------------------------------------------------------------------------------

# A verdict is a STRUCTURED marker, not a word: a line `Verdict: <value>`, a cell in a table column headed "Verdict", or (in a table with no such column) a
# cell whose whole text is CONFIRMED, all in any case. Prose that merely says "the owner confirmed it" is not a verdict: matching bare prose would teach
# authors to write waivers. The VALUE is held to a vocabulary: a verdict written as a code (`OK`, a tick, `C`) would escape the quotes check, so it is a finding.
VERDICT_LINE = re.compile(r"^\s*[-*>]*\s*\**\s*verdict\s*\**\s*:\s*(.*)$", re.I)
VOCABULARY = ("confirmed", "refuted", "inconclusive")
EVIDENCE = re.compile(r"\[quotes:\s*([A-Za-z0-9._-]+)\s*\]")
WAIVED = re.compile(r"\[waived:\s*([^\]]*)\]")
MIN_REASON = 20


def verdict_token(value: str) -> str:
    """The first word of a verdict's value, lower-cased, without Markdown emphasis (`**Confirmed** with a correction` -> `confirmed`); empty if none."""
    m = re.match(r"[^\s.,;:|)\u00b7]+", re.sub(r"[*`_]", "", value).strip())
    return m.group(0).casefold() if m else ""


def verdicts(text: str) -> list[tuple[int, str, str]]:
    """(line number, line, verdict word) for every verdict outside a code fence: a `Verdict:` line, each row's cell under a column headed Verdict,
    and, in a table with no such column, a cell that is exactly CONFIRMED."""
    out: list[tuple[int, str, str]] = []
    fenced = False
    column: int | None = None
    for n, line in enumerate(text.splitlines(), 1):
        if re.match(r"^\s*```", line):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = VERDICT_LINE.match(line)
        if m:
            out.append((n, line, verdict_token(m.group(1))))
            continue
        if not line.lstrip().startswith("|"):
            column = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if column is None:
            heads = [i for i, c in enumerate(cells) if re.sub(r"[*`_]", "", c).strip().casefold().startswith("verdict")]
            if heads:
                column = heads[0]
                continue
            if "confirmed" in [c.strip("*` ").casefold() for c in cells]:
                out.append((n, line, "confirmed"))
        elif not all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells if c):
            out.append((n, line, verdict_token(cells[column]) if column < len(cells) else ""))
    return out


def verdict_lines(text: str) -> list[tuple[int, str]]:
    """The verdicts that are CONFIRMED: the ones that must carry their quotes."""
    return [(n, line) for n, line, word in verdicts(text) if word == "confirmed"]


def format_findings(root: Path) -> list[str]:
    """Every verdict line of an audit that is not in LEGACY_AUDITS carries `[quotes: ID]` pointing at a ```quotes ID block that holds a record, or
    `[waived: reason]` with a reason of at least MIN_REASON characters. One record or one waiver never covers a second verdict. The verdict's value is one
    of VOCABULARY, so that no verdict can be written in a form this check does not read."""
    findings: list[str] = []
    base = root / AUDITS
    for path in sorted(base.rglob("*.md")) if base.is_dir() else []:
        rel = path.relative_to(base).as_posix()
        if rel in LEGACY_AUDITS:
            continue
        text = path.read_text(encoding="utf-8")
        shown = path.relative_to(root).as_posix()
        quotes, bad = parse_blocks(text, shown)
        findings += bad
        have = {q.ident for q in quotes if q.ident}
        for n, line, word in verdicts(text):
            if word not in VOCABULARY:
                findings.append(f"{shown}:{n}: use the verdict vocabulary: CONFIRMED, REFUTED or INCONCLUSIVE (any case), not `{word or 'nothing'}`. "
                                "A verdict written as a code or a tick escapes the quotes check")
        for n, line in verdict_lines(text):
            ev, waived = EVIDENCE.search(line), WAIVED.search(line)
            if ev and ev.group(1) in have:
                continue
            if waived and len(waived.group(1).strip()) >= MIN_REASON:
                continue
            why = ("its `[quotes: ID]` names a block that has no record" if ev else
                   f"its waiver gives a reason shorter than {MIN_REASON} characters" if waived else "it carries neither")
            findings.append(f"{shown}:{n}: a CONFIRMED verdict needs `[quotes: ID]` with a ```quotes ID block, or `[waived: reason]`; {why}. "
                            "A verdict whose quotes were never matched against the raw page is the defect #2233 reports")
    return findings


_URL = re.compile(r"https?://[^\s)>\]\"'`|]+")
_PHRASE = re.compile(r"[“\"]([^”\"\n]{25,300})[”\"]")


def legacy_pairs(path: Path, root: Path) -> list[Quote]:
    """Heuristic pairs for an audit written before the `quotes` block: a long quoted phrase and the URLs in the same bullet, row or paragraph.
    Attribution is ambiguous when a unit cites several URLs, so a phrase matches if ANY of the unit's pages carries it."""
    text = path.read_text(encoding="utf-8")
    out: list[Quote] = []
    line_no = 1
    for unit in re.split(r"(?:\n\s*\n)|(?:\n(?=[-*]\s|\|))", text):
        urls = [u.rstrip(".,;:") for u in _URL.findall(unit)]
        for phrase in _PHRASE.findall(unit):
            if urls:
                out.append(Quote("\n".join(dict.fromkeys(urls)), "legacy", phrase, f"{path.relative_to(root).as_posix()}~{line_no}"))
        line_no += unit.count("\n") + 1
    return out


def legacy_segments(phrase: str) -> list[str]:
    """A legacy phrase as the verdict wrote it: Markdown emphasis and code ticks dropped, an elision (`...` or an ellipsis) splitting it into runs
    that must each be on the page. A run under 12 characters is too short to mean anything and is not required."""
    plain = re.sub(r"\*\*|__|`", "", phrase)
    return [seg.strip() for seg in re.split(r"\u2026|\.{3}", plain) if len(seg.strip()) >= 12] or [plain.strip()]


def judge_legacy(phrase: str, page: Page) -> str:
    if page.error:
        return UNFETCHABLE
    if page.is_shell:
        return SHELL
    return MATCH if all(normalise(seg) in page.text for seg in legacy_segments(phrase)) else ABSENT


def legacy_report(files: list[Path], root: Path, fetcher=fetch) -> tuple[dict, list[str]]:
    stats = {"files": 0, "quotes": 0, "match": 0, "absent": 0, "inconclusive": 0}
    lines: list[str] = []
    pages: dict[str, Page] = {}
    for path in files:
        if "CONFIRMED" not in path.read_text(encoding="utf-8"):
            continue
        pairs = legacy_pairs(path, root)
        if not pairs:
            continue
        stats["files"] += 1
        for q in pairs:
            stats["quotes"] += 1
            results = []
            for url in q.url.split("\n"):
                if url not in pages:
                    pages[url] = fetcher(url)
                results.append(judge_legacy(q.phrase, pages[url]))
            if MATCH in results:
                stats["match"] += 1
            elif ABSENT in results:
                stats["absent"] += 1
                lines.append(f"ABSENT {q.where}: \"{q.phrase[:110]}\"  (checked {len(results)} page(s): {q.url.split(chr(10))[0]})")
            else:
                stats["inconclusive"] += 1
                lines.append(f"INCONCLUSIVE {q.where}: {'/'.join(sorted(set(results)))}: {q.url.split(chr(10))[0]}")
    return stats, lines


# ---------------------------------------------------------------------------------------------
# Selftest: a real page, a fabricated quote, a shell, a missing page; every verdict must be able to fail
# ---------------------------------------------------------------------------------------------

REAL = """<!doctype html><html><head><title>Validation</title><style>.x{color:red}</style>
<script>var hidden = "the sentence only a script holds, not the reader";</script></head><body><main><h1>Validation</h1>
<p>When there is an error, <b>show an error summary</b> component at the top of the page, and move keyboard focus to&nbsp;it.</p>
<p>Don&rsquo;t validate when the user moves away from a field &ndash; wait for the submit.</p>
<!-- an editor note nobody sees: hidden from readers -->
<script>var more = "text a body script holds, not the reader";</script>
<p>""" + ("Plain explanatory text so the page is long enough to be a real page, not a shell. " * 8) + """</p></main></body></html>"""
SHELL_PAGE = '<!doctype html><html><head><script src="/app.js"></script></head><body><div id="root"></div><noscript>You need to enable JavaScript to run this app.</noscript></body></html>'
INLINE = "<html><body><p>keep it (the value <code>x</code>, then the next one) here</p><p>the first paragraph ends</p><p>the second begins</p><p>" + ("Plain explanatory text so the page is long enough to be a real page. " * 8) + "</p></body></html>"
HIDDEN = ("<!doctype html><html><head><title>the title only the head holds</title></head><body>"
          "<div hidden>text inside a hidden attribute</div><p style=\"display: none\">text inside an inline display none</p>"
          "<p style=\"visibility:hidden\">text inside visibility hidden</p><span aria-hidden=\"true\">text inside aria hidden</span>"
          "<div hidden><p>text nested inside a hidden element</p></div><p>the one sentence a reader can see here</p><p>"
          + ("Plain explanatory text so the page is long enough to be a real page. " * 8) + "</p><script>text after an unclosed script runs to the end of the file")
PLAIN = ("def tool(self):\n    return annotations(read_only_hint: true)\n" * 12)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        routes = {"/real": ("text/html; charset=utf-8", REAL), "/shell": ("text/html", SHELL_PAGE), "/raw.rb": ("text/plain", PLAIN), "/inline": ("text/html", INLINE), "/hidden": ("text/html", HIDDEN)}
        if self.path == "/go":                      # a redirect: the page read is not the page cited
            self.send_response(302)
            self.send_header("Location", "/real")
            self.end_headers()
            return
        if self.path not in routes:
            self.send_response(404)
            self.end_headers()
            return
        kind, body = routes[self.path]
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:  # silence the access log
        pass


def selftest() -> int:
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool) -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(label)

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        def run(phrase: str, path: str = "/real") -> int:
            return check_quotes([Quote(base + path, "fixture", phrase, "fixture:1")])[0]

        check("a phrase that is on the page matches", run("show an error summary component at the top of the page") == 0)
        check("a phrase across tags and a non-breaking space matches", run("move keyboard focus to it") == 0)
        check("an inline tag leaves no space: `<code>x</code>,` reads as `x,`", run("keep it (the value x, then the next one) here", "/inline") == 0)
        check("a block tag is a break: two paragraphs are not one run of words", run("the first paragraph endsthe second begins", "/inline") == 1)
        check("a curly apostrophe and an en dash match their ASCII forms", run("Don't validate when the user moves away from a field - wait") == 0)
        check("a FABRICATED quote is refused (exit 1)", run("Always show an error summary") == 1)
        check("a paraphrase is refused", run("show an error summary next to each answer") == 1)
        check("case is not folded: the wrong case is refused", run("Show An Error Summary component") == 1)
        check("text only a <script> holds is not on the page", run("the sentence only a script holds") == 1)
        check("text only a <script> in the body holds is not on the page", run("text a body script holds") == 1)
        check("text only an HTML comment holds is not on the page", run("an editor note nobody sees") == 1)
        check("a JavaScript shell is INCONCLUSIVE (exit 2), never CONFIRMED", run("You need to enable JavaScript", "/shell") == 2)
        check("a shell is INCONCLUSIVE even for a phrase it does contain", run("enable JavaScript", "/shell") == 2)
        check("a missing page is INCONCLUSIVE (exit 2)", run("anything", "/nope") == 2)
        check("raw source text matches as itself", run("annotations(read_only_hint: true)", "/raw.rb") == 0)
        check("a redirect is INCONCLUSIVE (exit 2): the page read is not the page cited", run("show an error summary component", "/go") == 2)
        check("a redirect names where it went, so the verifier can cite it", "redirected to" in (check_quotes([Quote(base + "/go", "f", "x", "f:1")])[1] or [""])[0])
        check("the page a redirect leads to matches when it is cited directly", run("show an error summary component", "/real") == 0)
        check("a visible sentence on a page full of hidden text matches", run("the one sentence a reader can see here", "/hidden") == 0)
        for hidden in ("the title only the head holds", "text inside a hidden attribute", "text inside an inline display none", "text inside visibility hidden",
                       "text inside aria hidden", "text nested inside a hidden element", "text after an unclosed script runs to the end"):
            check(f"hidden text is not on the page: {hidden}", run(hidden, "/hidden") == 1)
        code, report = check_quotes([Quote(base + "/real", "f", "show an error summary component", "f:1"), Quote(base + "/real", "f", "a fabricated phrase", "f:2"),
                                     Quote(base + "/shell", "f", "x", "f:3")])
        check("an absent phrase wins over an inconclusive page (exit 1), and both are reported", code == 1 and len(report) == 2)
        check("an empty record set is clean", check_quotes([])[0] == 0)
        seen: list[str] = []
        def counting(url: str) -> Page:
            seen.append(url)
            return fetch(url)
        check("the page is fetched once however many phrases cite it",
              check_quotes([Quote(base + "/real", "f", "show an error summary", f"f:{i}") for i in range(3)], fetcher=counting)[0] == 0 and len(seen) == 1)
    finally:
        server.shutdown()
        server.server_close()

    q, bad = parse_blocks("text\n```quotes C1\nhttps://a.example/x | page read 2026-10-21 | one phrase here\nnot a record\n```\n", "f.md")
    check("a quotes block yields its records, with its id", len(q) == 1 and q[0].url == "https://a.example/x" and q[0].scope.startswith("page read") and q[0].phrase == "one phrase here" and q[0].ident == "C1")
    check("a malformed record is reported, not skipped", len(bad) == 1)
    check("an empty version or date field is refused", len(parse_blocks("```quotes C1\nhttps://a.example |  | a phrase\n```\n", "f")[1]) == 1)
    check("a phrase may itself contain a pipe", parse_blocks("```quotes C1\nhttps://a.example | v | a | b\n```\n", "f")[0][0].phrase == "a | b")
    check("a record outside a quotes block is ignored", parse_blocks("https://a.example | v | not in a block\n", "f")[0] == [])

    GOOD = "```quotes C1\nhttps://a.example | page read 2026-10-21 | a phrase\n```\n"
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        audits = root / AUDITS
        audits.mkdir(parents=True)

        def findings(name: str, text: str) -> list[str]:
            for old in audits.glob("*.md"):
                old.unlink()
            (audits / name).write_text(text, encoding="utf-8")
            return format_findings(root)

        legacy_name = sorted(LEGACY_AUDITS)[0]
        check("an audit on the frozen legacy list needs no quotes", findings(legacy_name, "Verdict: CONFIRMED, no quotes\n") == [])
        check("a new audit that says CONFIRMED with no quotes is a finding", len(findings("2026-10-23-new.md", "Verdict: CONFIRMED\n")) == 1)
        check("a BACK-DATED name does not make an audit old", len(findings("2026-10-01-x.md", "Verdict: CONFIRMED\n")) == 1)
        check("an UNDATED name does not make an audit old", len(findings("foo.md", "Verdict: CONFIRMED\n")) == 1)
        check("`Verdict: Confirmed` and `verdict: confirmed` are verdicts in any case", len(findings("2026-10-23-new.md", "Verdict: Confirmed\n")) == 1 and len(findings("2026-10-23-new.md", "- **verdict:** confirmed.\n")) == 1)
        check("a table cell that is exactly CONFIRMED is a verdict, in any case", len(findings("2026-10-23-new.md", "| C1 | the claim | CONFIRMED |\n")) == 1 and len(findings("2026-10-23-new.md", "| C1 | the claim | **Confirmed** | note |\n")) == 1)
        check("`Verdict: OK` is a finding: use the verdict vocabulary", len(findings("2026-10-23-new.md", "Verdict: OK\n")) == 1)
        check("`Verdict: \u2713` is a finding: use the verdict vocabulary", len(findings("2026-10-23-new.md", "Verdict: \u2713\n")) == 1)
        check("an empty `Verdict:` is a finding", len(findings("2026-10-23-new.md", "Verdict:\n")) == 1)
        check("a cell `C` under a Verdict column is a finding",
              any("verdict vocabulary" in f for f in findings("2026-10-23-new.md", "| id | claim | Verdict |\n|---|---|---|\n| R1 | a claim | C |\n")))
        check("a `C \u00b7 source` cell under a `verdict \u00b7 source` column is a finding",
              any("verdict vocabulary" in f for f in findings("2026-10-23-new.md", "| id | claim | verdict \u00b7 source |\n|---|---|---|\n| R1 | a claim | C \u00b7 react.dev |\n")))
        check("REFUTED and INCONCLUSIVE are in the vocabulary, in any case",
              findings("2026-10-23-new.md", "Verdict: Refuted\n| id | verdict |\n|---|---|\n| R1 | inconclusive (held out) |\n") == [])
        check("a CONFIRMED cell under a Verdict column needs its quotes even with extra words after it",
              len(findings("2026-10-23-new.md", "| id | claim | Verdict |\n|---|---|---|\n| R1 | a claim | CONFIRMED with a correction |\n")) == 1)
        check("a CONFIRMED cell under a Verdict column with its tag is clean",
              findings("2026-10-23-new.md", "| id | claim | Verdict | evidence |\n|---|---|---|---|\n| C1 | a claim | **Confirmed** with a correction | [quotes: C1] |\n" + GOOD) == [])
        check("a Verdict column ends with its table: a later table's cells are not read as verdicts",
              findings("2026-10-23-new.md", "| id | verdict |\n|---|---|\n| R1 | inconclusive |\n\ntext\n\n| id | note |\n|---|---|\n| R2 | C |\n") == [])
        check("a table verdict with its tag in the row is clean", findings("2026-10-23-new.md", "| C1 | the claim | CONFIRMED | [quotes: C1] |\n" + GOOD) == [])
        check("PROSE that says confirmed is not a verdict", findings("2026-10-23-new.md", "The owner confirmed the scope. We CONFIRMED nothing here.\nthe claim is unconfirmed\n| C1 | claim | not confirmed by the page |\n") == [])
        check("a verdict with [quotes: ID] and its block is clean", findings("2026-10-23-new.md", "Verdict: CONFIRMED [quotes: C1]\n" + GOOD) == [])
        check("a verdict whose [quotes: ID] has no block is a finding", len(findings("2026-10-23-new.md", "Verdict: CONFIRMED [quotes: C9]\n" + GOOD)) == 1)
        check("a block with no verdict pointing at it does not clear another verdict", len(findings("2026-10-23-new.md", "Verdict: CONFIRMED\n" + GOOD)) == 1)
        check("ONE block does not cover a second verdict", len(findings("2026-10-23-new.md", "Verdict: CONFIRMED [quotes: C1]\nVerdict: CONFIRMED\n" + GOOD)) == 1)
        check("two verdicts with their own blocks are clean", findings("2026-10-23-new.md", "Verdict: CONFIRMED [quotes: C1]\nVerdict: CONFIRMED [quotes: C2]\n" + GOOD + GOOD.replace("C1", "C2")) == [])
        check("a reasoned waiver clears its own verdict", findings("2026-10-23-new.md", "Verdict: CONFIRMED [waived: the evidence is source in this repository]\n") == [])
        check("ONE waiver does not cover a second verdict", len(findings("2026-10-23-new.md", "Verdict: CONFIRMED [waived: the evidence is source in this repository]\nVerdict: CONFIRMED\n")) == 1)
        check("a waiver reason of `x` is a finding", len(findings("2026-10-23-new.md", "Verdict: CONFIRMED [waived: x]\n")) == 1)
        check("a waiver with no reason is a finding", len(findings("2026-10-23-new.md", "Verdict: CONFIRMED [waived: ]\n")) == 1)
        check("a REFUTED audit needs no block", findings("2026-10-23-new.md", "Verdict: REFUTED\n") == [])
        check("the word inside a code fence is not a verdict", findings("2026-10-23-new.md", "```\nCONFIRMED\n```\n") == [])
        check("a malformed record in a new audit is a finding", len(findings("2026-10-23-new.md", "Verdict: CONFIRMED [quotes: C1]\n```quotes C1\nnot a record\n```\n")) >= 1)
        legacy = audits / "2026-10-10-legacy.md"
        legacy.write_text('CONFIRMED. The docs say \u201cshow an error summary component at the top of the page\u201d (https://127.0.0.1:1/x).\n', encoding="utf-8")
        pairs = legacy_pairs(legacy, root)
        check("a legacy audit's long quote is paired with the URL in its unit", len(pairs) == 1 and pairs[0].url == "https://127.0.0.1:1/x")
    legacy_page = {"https://a.example/p": Page(normalise("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"), False)}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / AUDITS).mkdir(parents=True)
        f = root / AUDITS / "2026-10-01-x.md"
        f.write_text("CONFIRMED.\n- docs say \"alpha beta gamma delta epsilon zeta eta\" (https://a.example/p)\n- and \"a sentence the page does not hold anywhere at all\" (https://a.example/p)\n",
                     encoding="utf-8")
        stats, lines = legacy_report([f], root, fetcher=lambda u: legacy_page[u])
        check("the legacy report counts a match and an absent phrase", stats["quotes"] == 2 and stats["match"] == 1 and stats["absent"] == 1 and len(lines) == 1)

    check("legacy: Markdown emphasis and code ticks are dropped", legacy_segments("**MUST NOT** vary per `connection` or as a side effect") == ["MUST NOT vary per connection or as a side effect"])
    check("legacy: an elision splits a phrase into runs that must each be present", legacy_segments("first run of the quote ... second run of the quote") == ["first run of the quote", "second run of the quote"])
    page = Page(normalise("MUST NOT vary per connection or as a side effect of other requests"), False)
    check("legacy: a phrase with emphasis marks matches its plain page", judge_legacy("**MUST NOT** vary per `connection`", page) == MATCH)
    check("legacy: a phrase with an invented run is absent", judge_legacy("MUST NOT vary per connection ... and then something invented here", page) == ABSENT)

    if failures:
        print(f"check_verdict_quotes selftest: FAILED ({len(failures)} of {checks})")
        for f in failures:
            print(f"  FAIL: {f}")
        return 1
    print(f"check_verdict_quotes selftest: {checks} checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*")
    ap.add_argument("--format-check", action="store_true", help="offline: every CONFIRMED verdict of a new audit carries its quotes or a reasoned waiver")
    ap.add_argument("--legacy", action="store_true", help="report on audits written before the quotes block (heuristic pairs; fetches pages)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.format_check:
        findings = format_findings(REPO)
        for f in findings:
            print(f"  {f}")
        print(f"verdict quotes: {len(findings)} finding(s)" if findings else "verdict quotes: every verdict of a new audit uses CONFIRMED, REFUTED or INCONCLUSIVE, and every CONFIRMED one carries its quotes (or a reasoned waiver)")
        return 1 if findings else 0
    if a.legacy:
        files = [Path(f) for f in a.files] or sorted((REPO / AUDITS).rglob("*.md"))
        stats, lines = legacy_report(files, REPO)
        for line in lines:
            print(line)
        print(f"legacy CONFIRMED audits with quoted phrases: {stats['files']} file(s), {stats['quotes']} phrase(s): "
              f"{stats['match']} match, {stats['absent']} absent, {stats['inconclusive']} inconclusive")
        return 1 if stats["absent"] else 0
    if not a.files:
        ap.print_usage(sys.stderr)
        return 2
    quotes: list[Quote] = []
    for name in a.files:
        got, bad = parse_blocks(Path(name).read_text(encoding="utf-8"), name)
        for line in bad:
            print(f"  {line}")
        if bad:
            return 2
        quotes += got
    if not quotes:
        print("no ```quotes block in the file(s): a CONFIRMED verdict needs a ```quotes ID block and `[quotes: ID]` on its line (or `[waived: reason of 20+ chars]`)")
        return 2
    code, report = check_quotes(quotes)
    for line in report:
        print(line)
    print({0: f"{len(quotes)} phrase(s), all on their pages", 1: "REFUSED: a phrase is absent from its page", 2: "INCONCLUSIVE: a page could not be judged"}[code])
    return code


if __name__ == "__main__":
    sys.exit(main())
