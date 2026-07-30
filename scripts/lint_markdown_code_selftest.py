#!/usr/bin/env python3
"""Prove `lint_markdown_code.py` fires on real errors AND stays silent on the shapes our docs use.

Run:  python3 scripts/lint_markdown_code.py --selftest

The silence half is the load-bearing half here. This linter's whole risk is false positives: reference
docs are full of deliberate elision and of fragments that are correct but not standalone, plus two
erubi idioms stdlib ERB cannot parse. A first version reported **26 blocks**, of which **22 were the
linter's own fault** — 20 from `<%= … do %>`, one from `<%==`, and a whole class of JSON blocks
silently parsed as JavaScript because `js` matched the `js` in ```json.

So every fixture below is one of those, pinned. If a future tweak re-breaks one, this fails.

Stdlib only.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lint_markdown_code as mc  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def _tick() -> None:
    global CHECKS
    CHECKS += 1


def expect(label: str, lang: str, code: str, *, parses: bool) -> None:
    """Assert whether a block is accepted, and say which context accepted it when it is."""
    _tick()
    problem, _context = mc.check_block(code, lang)
    if parses and problem:
        FAILURES.append(f"{label}: expected to PARSE, got:\n      {problem.splitlines()[0][:160]}")
    elif not parses and not problem:
        FAILURES.append(f"{label}: expected a FINDING, but the block was accepted")


def expect_extracted(label: str, markdown: str, want: list[tuple[str, str]]) -> None:
    """Assert exactly which (lang, first-line) pairs the fence regex pulls out of a document."""
    _tick()
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "doc.md")
        Path(path).write_text(markdown, encoding="utf-8")
        got = [(lang, next((l.strip() for l in code.splitlines() if l.strip()), ""))
               for _start, lang, code in mc.iter_blocks(path)]
    if got != want:
        FAILURES.append(f"{label}: extracted {got!r}, expected {want!r}")


def run() -> int:
    # ---- 1. it FIRES on real syntax errors ---------------------------------------------
    expect("js: unclosed brace", "js", "function f() {\n  return 1\n", parses=False)
    expect("js: stray keyword", "javascript", "const x = = 1", parses=False)
    expect("ruby: missing end", "ruby", "class Foo\n  def bar\n    1\n  end", parses=False)
    # The exact defect this linter found in shipped doctrine: a bare `rescue … end` with no `begin`
    # and no enclosing `def`. It raises SyntaxError the moment anyone pastes it.
    expect("ruby: bare rescue with no begin", "ruby",
           "do_a_thing\nrescue Foo => e\n  report(e)\nend", parses=False)
    # ERB does NOT error on this — it emits the remainder as a literal string, so the expression
    # silently never runs. Caught by an explicit balance check, not by the compiler.
    expect("erb: unterminated tag", "erb", "<%= foo\n<div>x</div>", parses=False)
    # NOTE the shape: there must be NO `%>` anywhere after the escape, or the scan finds one and the
    # fixture passes whether or not `<%%` is understood. (First version of this was vacuous — the
    # mutation checker caught it, which is the entire reason that tool exists.)
    expect("erb: `<%%` is an escaped literal, not an unterminated tag", "erb",
           "<p>to show a tag, write <%% in the template</p>", parses=True)
    expect("erb: block opened and never closed", "erb",
           "<%= form_with model: @p do |f| %>\n  <%= f.submit %>", parses=False)

    # ---- 2. it stays SILENT on documentation elision ----------------------------------
    # `...` and `…` are prose inside code, the same class as `<pack>` in a shell template.
    expect("ruby: (...) argument elision", "ruby",
           "Order.create!(...)   # lands in shard_one", parses=True)
    expect("ruby: ... as a body elision", "ruby",
           "class J\n  def perform(account) ... end\nend", parses=True)
    expect("ruby: unicode ellipsis", "ruby", "def call\n  …\nend", parses=True)
    expect("js: unicode ellipsis as a body", "js",
           "class C {\n  upvote({ params: { id, url } }) { … }\n}", parses=True)

    # ---- 3. it stays SILENT on correct-but-not-standalone fragments --------------------
    # A method with no class, a class field with no class: both are how reference docs show an API.
    expect("js: class-body fragment", "javascript",
           'static targets = [ "input" ]\n\nconnect() {\n  this.inputTarget\n}', parses=True)
    expect("ruby: method-body fragment", "ruby",
           "@order = Order.find(params[:id])\n@order.save!", parses=True)
    expect("js: module with export stays bare", "js",
           "export function focusTrap(el) {\n  return { activate() {} }\n}", parses=True)
    # A module's `export` is illegal inside any wrapper, so `bare` must be the accepting context —
    # if a wrapper ever claimed it, the ladder would be masking a real error.
    _tick()
    problem, context = mc.check_block("export const x = 1\n", "js")
    if problem or context != "bare":
        FAILURES.append(f"a module must be accepted BARE, not wrapped; got {context!r} / {problem!r}")

    # ---- 4. it stays SILENT on the two erubi idioms stdlib ERB cannot parse ------------
    # Both of these are valid in a Rails view and were the linter's own false positives: 20 blocks
    # from the block tag, one from the raw tag. This is the pair most likely to regress.
    expect("erb: <%= … do %> block tag", "erb",
           "<%= form_with model: @product do |form| %>\n  <%= form.submit %>\n<% end %>", parses=True)
    expect("erb: <%= … do %> with no block args", "erb",
           '<%= turbo_frame_tag "modal" do %>\n  <p>x</p>\n<% end %>', parses=True)
    expect("erb: <%== raw output tag", "erb",
           "<%= render @products %>\n<%== pagy_nav(@pagy) %>", parses=True)
    expect("erb: nested block tags", "erb",
           "<%= form_with model: @p do |f| %>\n"
           "  <% @p.errors.each do |e| %><li><%= e.full_message %></li><% end %>\n"
           "<% end %>", parses=True)
    # NEAR MISS: the normalisation must not swallow a genuinely broken block just because it
    # contains `do`. Dropping the `=` cannot invent a missing `end`.
    expect("erb: block tag with a MISSING end still fires", "erb",
           "<%= form_with model: @p do |f| %>\n  <%= f.submit %>\n", parses=False)

    # ---- 5. extraction: the right languages, and ONLY those ---------------------------
    # `js` matched the `js` in ```json and `[^\n]*` ate the `on`, so every JSON block in the repo
    # was being handed to `node --check`. The coverage audit caught it; this pins it.
    expect_extracted(
        "```json is NOT javascript",
        '```json\n{"a": 1}\n```\n\n```js\nlet a = 1\n```\n',
        [("js", "let a = 1")])
    expect_extracted(
        "```rb is ruby, and `ruby` is not truncated to `rb`",
        "```rb\nx = 1\n```\n\n```ruby\ny = 2\n```\n",
        [("rb", "x = 1"), ("ruby", "y = 2")])
    # Indented fences are real — nested lists in crud-modal-pattern.md — and a column-1 anchor made
    # 11 blocks invisible to the shell linter. Same assumption, pinned here before it can bite twice.
    expect_extracted(
        "an INDENTED fence is still extracted",
        "1. step\n\n   ```ruby\n   x = 1\n   ```\n",
        [("ruby", "x = 1")])
    expect_extracted(
        "unsupported languages are left alone",
        "```python\nx = 1\n```\n\n```yaml\na: 1\n```\n\n```jsonc\n{}\n```\n",
        [])

    # ---- 6. the extractor and its coverage control must agree ------------------------
    # Deliberately checked on a SYNTHETIC document rather than on the real tree. This selftest is
    # run against a mutated copy of the subject inside a temp directory (mutation_check.py), where
    # `skills/` does not exist — reading the real repo here made `discover()` raise, so every
    # mutation was "caught" by a traceback instead of by the fixture that should have caught it.
    # A crash is not a verdict. The real tree IS reconciled, on every run of the linter and by the
    # `markdown code coverage` gate; this assertion is about the two regexes agreeing at all.
    _tick()
    doc = ('```json\n{}\n```\n\n```js\nlet a = 1\n```\n\n   ```ruby\n   x = 1\n   ```\n'
           '\n```erb\n<p>x</p>\n```\n\n```rb\ny = 2\n```\n')
    strict, loose = len(list(mc.FENCE.finditer(doc))), len(mc.LOOSE.findall(doc))
    if strict != loose:
        FAILURES.append(f"extractor sees {strict} block(s) but its coverage control sees {loose} — "
                        "they must agree, or a clean report covers input nobody read")

    # ---- 7. a missing interpreter is a SKIP, never a pass ----------------------------
    _tick()
    available, missing = mc.interpreters()
    if not isinstance(available, list) or not isinstance(missing, list):
        FAILURES.append("interpreters() must return (available, missing) lists")
    if sorted(available + missing) != ["node", "ruby"]:
        FAILURES.append(f"interpreters() must account for exactly node and ruby; got "
                        f"{available!r} / {missing!r}")
    # And the reporting contract: the module must SAY skip rather than printing a clean result.
    _tick()
    source = Path(mc.__file__).read_text(encoding="utf-8")
    if "SKIP" not in source or "NOT a pass" not in source:
        FAILURES.append("the missing-interpreter path must report SKIP and say it is not a pass — "
                        "a check that did not run must never read as a passing one")

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"lint_markdown_code selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
