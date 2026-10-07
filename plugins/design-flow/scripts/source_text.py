#!/usr/bin/env python3
"""Comments are prose, not code: blank them before any gate matches an idiom (#1128).

Run:  python3 source_text.py --selftest

WHY THIS EXISTS. Three design-flow gates scan source for a literal idiom -- a layout recipe in a
`class` attribute, a raw `<button>`, a breakpoint that changes the layout axis. All three matched
those idioms INSIDE COMMENTS, so a file that only DESCRIBES the anti-pattern was reported as
committing it. The worst case is the remediated file: you remove the wrapper, write a comment saying
why, and the comment re-trips the gate the fix satisfies. The natural response is to delete the
explanation to satisfy the detector, which is the opposite of what the gate is for.

This is the same class as the `content` false positives that shaped `check_surface_layout` at birth
-- match the CONSTRUCT, never the word -- caught then for one token and missed for the others.

LINE NUMBERS ARE PRESERVED. Two of the three callers report `file:line`, so a comment is blanked in
place rather than removed: every newline survives, and only the text between them goes. A helper
that silently shifted line numbers would trade a false positive for a wrong citation.

WHAT IS BLANKED, and nothing else:

  <%# ... %>      ERB comments, which may span lines
  <!-- ... -->    HTML comments, which may span lines
  ^\\s*# ...       Ruby WHOLE-LINE comments

A TRAILING `#` is deliberately left alone. `#` is legal inside a Ruby string and begins `#{}`
interpolation, so stripping from the first `#` on a line would eat real code -- including, in this
very corpus, `class: "..."` values. A whole-line comment has no such ambiguity. The cost is that a
gate can still be fooled by `foo = 1  # class: "stack"`, which is rare and is a true negative's
price rather than a false positive's.

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import re
import sys

ERB_COMMENT = re.compile(r"<%#.*?%>", re.S)
# AS THE HTML SPEC PARSES IT (CodeQL py/bad-tag-filter on #1451): a comment starts at `<!--` and ends at the
# first `-->` OR `--!>`; `<!-->` and `<!--->` are complete (abrupt) empty comments; one never closed runs to
# the end of input. `-->`-only missed `--!>`, so a browser-closed comment stayed "live" to a gate and text
# after it was over-stripped up to some later `-->`.
HTML_COMMENT = re.compile(r"<!--(?:-?>|[\s\S]*?(?:--!?>|\Z))")
RUBY_LINE_COMMENT = re.compile(r"^([ \t]*)#.*$", re.M)


def _blank(match: re.Match[str]) -> str:
    """Same newlines, no text -- so `file:line` in every caller's finding stays true."""
    return "\n" * match.group(0).count("\n")


# ELEMENTS WHOSE BODY THE TOKENIZER NEVER READS AS MARKUP (#1466): RAWTEXT and RCDATA, and script data. Inside them
# `<!--` starts no comment, so blanking from it would hide the real markup after the element.
RAW_TEXT = ("script", "style", "textarea", "title", "xmp", "iframe", "noembed", "noframes")
TAG_NAME = re.compile(r"[A-Za-z][^\s/>]*")


def _ascii_alpha(ch: str) -> bool:
    """The tokenizer's ASCII ALPHA. `str.isalpha()` is Unicode-aware, so `<é` was taken for a tag and crashed on the
    ASCII-only TAG_NAME (#1651 review R1); `</é` is a bogus comment in the standard, not an end tag."""
    return ch.isascii() and ch.isalpha()


def _skip_erb(source: str, i: int) -> int:
    """Past an ERB tag starting at `i` (`<%` ... `%>`); one never closed runs to the end."""
    end = source.find("%>", i + 2)
    return len(source) if end < 0 else end + 2


def _skip_tag(source: str, i: int) -> int:
    """Past a start tag at `i`, to just after its `>`. Quoted attribute values and ERB inside the tag are opaque: a `>`
    or `<!--` there is not markup. An ERB tag inside a quoted value may itself contain quotes (`class="<%= a ? "x" : "y" %>"`),
    so ERB is skipped first inside a value too."""
    n, j = len(source), i + 1
    while j < n:
        if source.startswith("<%", j):
            j = _skip_erb(source, j)
        elif source[j] in "\"'" and source[i:j].rstrip().endswith("="):
            # ONLY AFTER `=` (#1653 N3): a quote anywhere else in a tag is part of an attribute NAME, and opens nothing.
            q, j = source[j], j + 1
            while j < n and source[j] != q:
                j = _skip_erb(source, j) if source.startswith("<%", j) else j + 1
            j += 1
        elif source[j] == ">":
            return j + 1
        else:
            j += 1
    return n


def _section_end(source: str, i: int, closer: str) -> int:
    """Past a CDATA section or a processing instruction: to its own closer, or to the first `>` when it has none."""
    end = source.find(closer, i)
    return end + len(closer) if end >= 0 else _bogus_end(source, i)


# `-->` ONLY, never `--!>`: in WHATWG §13.2.5.28 (script data escaped dash dash state) only `>` after `--` returns to
# script data; `--!>` closes an HTML COMMENT (comment end bang state), not an escaped script run (#1654, CodeQL).
SCRIPT_ESCAPE_ENDS = ("-->",)
SCRIPT_TOKEN = re.compile(r"<!--|" + "|".join(map(re.escape, SCRIPT_ESCAPE_ENDS)) + r"|</?script[\s/>]", re.I)


def _script_end(source: str, i: int) -> int:
    """Where a script body that starts at `i` ends: the start of its real `</script>` (#1653 N1). As the tokenizer's script
    data states: `<!--` enters ESCAPED, a `<script` there enters DOUBLE-ESCAPED, where `</script` only steps back to
    escaped; `-->` returns to plain script data. Only `</script` in plain or escaped data ends the body."""
    state = "data"
    for m in SCRIPT_TOKEN.finditer(source, i):
        tok = m.group(0).lower()
        if tok == "<!--":
            state = "escaped" if state == "data" else state
        elif tok in SCRIPT_ESCAPE_ENDS:
            state = "data"
        elif tok.startswith("</"):
            if state == "double":
                state = "escaped"
            else:
                return m.start()
        elif state == "escaped":                               # `<script` inside an escaped run
            state = "double"
    return len(source)


def _bogus_end(source: str, i: int) -> int:
    """A bogus comment ends at the first `>`, or at the end of input."""
    end = source.find(">", i)
    return len(source) if end < 0 else end + 1


def is_html(name: str) -> bool:
    """Whether a file is HTML or an ERB template, so the BOGUS-comment rule applies to it (see `blank_html_comments`)."""
    return name.endswith((".erb", ".html", ".htm"))


def blank_html_comments(source: str, *, html: bool = False) -> str:
    """Only the HTML comments blanked, newlines kept -- for a caller that reads ERB or Ruby comments itself.

    AS THE TOKENIZER SEES THEM (#1466; WHATWG HTML, tokenization): a comment starts only in the DATA state, so `<!--`
    inside a quoted attribute value, inside a `<script>`/`<style>`/RCDATA body, or inside ERB is text, not a comment.
    And two openers are BOGUS comments that end at the first `>` (§13.2.5.42, 13.2.5.7, 13.2.5.41): `<!` not followed by
    `--`, `DOCTYPE` or `[CDATA[`; and `</` followed by something that is not a letter and not `>`. `<!DOCTYPE` is a
    doctype and `</>` emits nothing, so both stay as they are.

    NOT `<?` (doctrine-verifier, 2026-10-07): the living standard's tag open state now enters a PROCESSING INSTRUCTION
    state, so `<?name ...>` is a processing-instruction token, not a comment; it is left live.

    CDATA IS READ AS IN FOREIGN CONTENT (#1654 review N2): to `]]>`, which is right for inline SVG. In HTML content the
    standard makes `<![CDATA[` a bogus comment ending at the first `>`; reading it to `]]>` there leaves a later `<!--`
    live -- the safe direction, since it only ever leaves MORE text visible to a gate.

    A DYNAMIC CLOSER IS LOST, HARMLESSLY (02's review of #1651): `</<%= tag %>>` is `</` before a non-letter, so in a
    template it is a bogus comment that ends at the `>` of `%>`. Only a closing tag is blanked, never an element start. So is `<![CDATA[`: a
    bogus comment in HTML content but real CDATA in foreign content (SVG), and leaving it hides nothing.

    BOGUS COMMENTS ONLY WITH `html=True` (the downstream diff of #1466): a Ruby file has no HTML data state, and Ruby's
    regex lookbehind `(?<![...` is exactly `<!` not followed by `--`, so blanking it hid real code in a model. A caller
    passes `html=is_html(path)`; the default keeps the bogus rule off, so a caller that forgets it hides nothing new.
    The rest -- `<!--` only in the data state -- only ever leaves MORE text live, so it applies to every file."""
    out, n, i, last = [], len(source), 0, 0

    def blank(start: int, end: int) -> None:
        nonlocal last
        out.append(source[last:start])
        out.append("\n" * source.count("\n", start, end))
        last = end

    while True:
        c = source.find("<", i)
        if c < 0:
            break
        nxt = source[c + 1:c + 2]
        if source.startswith("<%", c):
            i = _skip_erb(source, c)
        elif source.startswith("<!--", c):
            m = HTML_COMMENT.match(source, c)
            if m is None:                                  # cannot happen while the pattern ends in `\Z`; never crash
                i = c + 4
                continue
            blank(c, m.end())
            i = m.end()
        elif nxt == "!":
            if source.startswith("<![CDATA[", c):
                i = _section_end(source, c, "]]>")                 # CDATA runs to `]]>` (#1653 N2), left live
            elif source[c + 2:c + 9].upper() == "DOCTYPE":
                i = _bogus_end(source, c)                          # a doctype: markup, left live
            else:
                i = _bogus_end(source, c)
                if html:
                    blank(c, i)
        elif nxt == "/":
            after = source[c + 2:c + 3]
            if _ascii_alpha(after) or after == ">" or after == "":
                i = _bogus_end(source, c) if _ascii_alpha(after) else c + 2   # an end tag, `</>`, or a lone `</` at the end
            else:
                i = _bogus_end(source, c)
                if html:
                    blank(c, i)
        elif _ascii_alpha(nxt):
            end = _skip_tag(source, c)
            name = TAG_NAME.match(source, c + 1).group(0).lower()
            i = end
            # A trailing `/` does NOT close a non-void element in HTML (the self-closing flag is ignored outside foreign
            # content), so `<script/>` still opens raw text (#1651 review N4).
            if name == "script":
                i = _script_end(source, end)
            elif name in RAW_TEXT:
                close = re.compile(rf"</{name}[\s/>]", re.I).search(source, end)
                i = close.start() if close else n
        elif nxt == "?":
            i = _section_end(source, c, "?>")                     # a processing instruction runs to `?>` (#1653 N2), live
        else:
            i = c + 1
    out.append(source[last:])
    return "".join(out)


def strip_comments(source: str, *, html: bool = False) -> str:
    """Blank every comment in place. Safe on both `.rb` and `.erb`; the patterns do not overlap."""
    source = ERB_COMMENT.sub(_blank, source)
    source = blank_html_comments(source, html=html)
    return RUBY_LINE_COMMENT.sub(lambda m: m.group(1), source)


def _selftest() -> int:
    ok, bad = 0, []

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    # The three forms, each carrying an idiom a sibling gate matches on.
    out = strip_comments('<%# it was <div class="stack"> once %>\n<div class="box"></div>\n')
    expect("an ERB comment's text is gone", "stack" not in out)
    expect("...and the code beside it survives", 'class="box"' in out)

    out = strip_comments('<!-- never a raw <button> here -->\n<p>hi</p>\n')
    expect("an HTML comment's text is gone", "button" not in out)
    # THE SPEC'S OTHER ENDINGS (CodeQL py/bad-tag-filter).
    out = strip_comments('<!-- a <button> --!><p class="live">x</p> <!-- b -->')
    expect("`--!>` ends a comment", "button" not in out)
    expect("...and the markup after it is live, not swallowed up to a later `-->`", 'class="live"' in out)
    out = strip_comments('<p>a</p><!-- never closed <button>\n<select>')
    expect("an unterminated comment runs to the end of input", "button" not in out and "select" not in out)
    expect("...and the markup before it survives", "<p>a</p>" in out)
    out = strip_comments('<!--><p class="after">x</p><!---><i class="also"></i>')
    expect("`<!-->` and `<!--->` are complete empty comments", 'class="after"' in out and 'class="also"' in out)

    # A COMMENT STARTS ONLY IN THE DATA STATE (#1466). Blanking from a `<!--` that is not one hid the markup after it.
    # A `>` inside the value too: without the value being opaque the tag would end there, and `<!--` would be read as data.
    out = strip_comments('<input value="a > <!-- b"><button class="real">x</button>')
    expect("`<!--` inside a quoted attribute value starts no comment", 'class="real"' in out)
    out = strip_comments('<script>var s = "<!--";</script><div class="live"></div>')
    expect("`<!--` inside a <script> body starts no comment", 'class="live"' in out)
    out = strip_comments('<style>/* <!-- */</style><p class="after"></p>')
    expect("`<!--` inside a <style> body starts no comment", 'class="after"' in out)
    out = strip_comments('<%= "<!--" %><div class="erb-live"></div>')
    expect("`<!--` inside ERB starts no comment", 'class="erb-live"' in out)
    # An ODD number of quote characters inside the ERB: skipped as ERB, the value runs to its real close; read as text, the
    # ERB's `"` closes the value, the `>` after it ends the tag, and `<!--` is read as a comment that hides the next element.
    out = strip_comments('<div title="<%= a.delete(%q(")) %> > <!-- y"><p class="kept"></p>')
    expect("ERB with quotes inside a quoted value does not end the value early", 'class="kept"' in out)
    # BOGUS COMMENTS end at the first `>` (WHATWG 13.2.5.42 `<!x`, 13.2.5.7 `</ x`).
    out = strip_comments('<! a hidden <button\n> <p class="live1"></p>', html=True)
    expect("`<!` not followed by `--` is a bogus comment, blanked to `>`", "button" not in out and 'class="live1"' in out)
    expect("...and its newline is kept", out.count("\n") == 1)
    out = strip_comments('</ a hidden button> <p class="live2"></p>', html=True)
    expect("`</` followed by a non-letter is a bogus comment", "button" not in out and 'class="live2"' in out)
    # NOT COMMENTS, so left exactly as they are.
    for src in ('<!DOCTYPE html><p class="d"></p>', '<?xml version="1.0"?><p class="d"></p>', '<p></></p>'):
        expect(f"{src[:12]!r} is not a comment and is left as it is", strip_comments(src, html=True) == src)
    # #1651 REVIEW: each of these broke with nothing failing.
    for odd in ("a <é b", "x <ß>", "</é z>"):
        try:
            strip_comments(odd, html=True)
            ok_ = True
        except Exception:  # noqa: BLE001
            ok_ = False
        expect(f"a non-ASCII letter after `<` does not crash ({odd!r})", ok_)
    expect("`</é` is a bogus comment (ASCII alpha only starts an end tag)", "é" not in strip_comments("</é z> <p>", html=True))
    out = strip_comments('<div <%= "x" if a > b %> title="<!-- t"><p class="k-erb"></p>')
    expect("ERB in a tag OUTSIDE any quote is opaque: its `>` does not end the tag", 'class="k-erb"' in out)
    # A LITERAL list, not RAW_TEXT itself: a loop over the tuple under test loses an element's check with the element.
    for name in ("script", "style", "textarea", "title", "xmp", "iframe", "noembed", "noframes"):
        out = strip_comments(f'<{name}><!--</{name}><p class="k-{name}"></p>')
        expect(f"`<!--` inside a <{name}> body starts no comment", f'class="k-{name}"' in out)
    out = strip_comments('<script>x</scripts><!--</script><p class="k-close"></p>')
    expect("`</scripts>` does not close a <script>: the close tag needs a terminator", 'class="k-close"' in out)
    out = strip_comments("<input value='a > <!-- b'><button class=\"k-single\">x</button>")
    expect("a single-quoted attribute value is opaque too", 'class="k-single"' in out)
    expect("`<!doctype` is a doctype in any case", strip_comments("<!doctype html><p>", html=True) == "<!doctype html><p>")
    out = strip_comments('<script/><!--</script><p class="k-sc"></p>')
    expect("`<script/>` still opens a raw-text body (a trailing `/` closes no HTML element)", 'class="k-sc"' in out)

    # 02's review of #1651: CDATA, a close tag with a space, a lone `</`, and blank_html_comments's own default.
    expect("`<![CDATA[` is left live, even in a template",
           strip_comments("<![CDATA[ x ]]><p>", html=True) == "<![CDATA[ x ]]><p>")
    out = strip_comments('<script>s</script ><!-- c <button> --><p class="k-sp"></p>')
    expect("`</script >` (a space before `>`) closes the script, so the comment after it is blanked",
           "button" not in out and 'class="k-sp"' in out)
    expect("a lone `</` at the end of input is left as it is", strip_comments("<p>a</", html=True) == "<p>a</")
    expect("blank_html_comments keeps the bogus rule off by default",
           blank_html_comments("<! x> <p>") == "<! x> <p>" and blank_html_comments("<! x> <p>", html=True) == " <p>")

    # The generic raw-text close, now that <script> has its own scanner (#1653): <style> carries the same two checks.
    out = strip_comments('<style>x</styles><!--</style><p class="k-close2"></p>')
    expect("`</styles>` does not close a <style>: the close tag needs a terminator", 'class="k-close2"' in out)
    out = strip_comments('<style>s</style ><!-- c <button> --><p class="k-sp2"></p>')
    expect("`</style >` (a space before `>`) closes the style", "button" not in out and 'class="k-sp2"' in out)

    # #1653 (13's review of #1651, N1 to N3).
    out = strip_comments("<script><!-- <script> </script> --> var x='<!--'; </script><i class=after></i>")
    expect("N1: a script double-escaped by `<!-- <script>` ends only at its real `</script>`", "class=after" in out)
    out = strip_comments("<script>a</script><!-- gone <b> --><i class=n1-control></i>")
    expect("N1 control: a plain script still ends at `</script>`, and a comment after it is blanked",
           "<b>" not in out and "class=n1-control" in out)
    out = strip_comments("<svg><![CDATA[ a > <!-- b ]]></svg><p class=n2-cdata></p>", html=True)
    expect("N2: CDATA runs to `]]>`, so a `<!--` inside it starts no comment", "class=n2-cdata" in out)
    out = strip_comments("<?x > <!-- hid ?><p class=n2-pi></p>", html=True)
    expect("N2: a processing instruction runs to `?>`, so a `<!--` inside it starts no comment", "class=n2-pi" in out)
    out = strip_comments('<a b"c>\n<!-- hid <button> -->\n<p class=n3></p>')
    expect("N3: a quote outside a value (not after `=`) opens nothing, so the comment after the tag is blanked",
           "button" not in out and "class=n3" in out)

    # 13's review of #1654: six behaviours the first fixtures did not hold.
    out = strip_comments('<a b = "x > <!-- y"><p class=k-ws></p>')
    expect("whitespace between `=` and a quote still opens a value", "class=k-ws" in out)
    out = strip_comments("<script><!-- <script> <!-- </script> '<!--' <i class=x> </script><b class=after2></b>")
    expect("a `<!--` while double-escaped does not reset to escaped", "class=after2" in out)
    out = strip_comments("<script><!-- <script> </script> <script> </script> '<!--' </script><b class=after3></b>")
    expect("`</script` while double-escaped steps back to escaped, not to data", "class=after3" in out)
    out = strip_comments("<script><!-- --> <script> </script><i class=x></i> <!-- c <button> -->")
    expect("`-->` returns an escaped script to plain data", "button" not in out)
    out = strip_comments("<SCRIPT>x</SCRIPT><!-- c <button> -->")
    expect("an uppercase </SCRIPT> ends the script (case-insensitive)", "button" not in out)
    out = strip_comments("<![CDATA[ a > <!-- b --><p class=k-cd></p>", html=True)
    expect("an unterminated CDATA falls back to the first `>`, not the end of input", "<!-- b" not in out and "class=k-cd" in out)

    # #1654 (CodeQL): `--!>` ends an HTML comment but NOT an escaped script run -- both sides pinned.
    out = strip_comments("<script><!-- --!> <script> </script> '<!--' </script><b class=k-bang></b>")
    expect("`--!>` inside a script does not return it to data (only `-->` does)", "class=k-bang" in out)
    out = strip_comments("<!-- c --!> <b class=k-bang2></b>")
    expect("`--!>` still ends an HTML comment", "class=k-bang2" in out)

    # RUBY HAS NO HTML DATA STATE: a regex lookbehind is `<!` not followed by `--`, and blanking it hid a model's code.
    rb = '    Regexp.new("(?<![[:word:]])#{x}(?![[:word:]])", options)\n  end\n  def stack = "stack"\n'
    expect("by default (a Ruby file) a `(?<!` lookbehind is not a bogus comment", strip_comments(rb) == rb)
    expect("is_html: templates are HTML, Ruby is not",
           is_html("a/b.html.erb") and is_html("x.html") and not is_html("a/b.rb"))

    out = strip_comments('  # use `class: "stack"` on the caller\n  attr_reader :x\n')
    expect("a Ruby whole-line comment's text is gone", "stack" not in out)
    expect("...and the next line survives", "attr_reader" in out)

    # LINE NUMBERS. Two callers report file:line, so a multi-line comment must not shift them.
    src = '<%# one\n   two\n   three %>\n<div class="stack"></div>\n'
    out = strip_comments(src)
    expect("a multi-line comment keeps its newlines", out.count("\n") == src.count("\n"))
    # `len(...) > 3 and` so a mutation that DELETES the comment fails this assertion by name
    # instead of raising IndexError: the harness reads a traceback as "something went wrong",
    # which hides which fixture was meant to notice.
    lines = out.splitlines()
    expect("...so the code lands on the same line it started on",
           len(lines) > 3 and lines[3] == '<div class="stack"></div>')

    # THE CONTROL, and the reason this helper is narrow: a `#` that is NOT a whole-line comment must
    # survive, because it is legal in a string and it begins interpolation.
    out = strip_comments('  url = "/tags/#anchor"\n  name = "#{first} #{last}"\n')
    expect("a `#` inside a string is not a comment", "#anchor" in out)
    expect("...and `#{}` interpolation survives", "#{first}" in out)

    # A frozen_string_literal magic comment is a whole-line comment and blanking it is harmless --
    # nothing here executes Ruby. Asserted so the behaviour is chosen rather than incidental.
    expect("a magic comment is blanked like any other",
           strip_comments("# frozen_string_literal: true\nclass X\nend\n").startswith("\nclass X"))

    # An empty source, and a source with no comments at all, come back unchanged.
    expect("a source with no comments is returned unchanged",
           strip_comments('<div class="stack"></div>\n') == '<div class="stack"></div>\n')
    expect("an empty source is empty", strip_comments("") == "")

    if bad:
        print(f"ran {ok + len(bad)} assertion(s)\n\n{len(bad)} FAILED:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print(f"ran {ok} assertion(s)")
    print("comments are blanked in place; line numbers and in-string `#` survive")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true", help="prove this helper can fail")
    ap.parse_args()
    return _selftest()


if __name__ == "__main__":
    raise SystemExit(main())
