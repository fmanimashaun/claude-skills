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
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
RUBY_LINE_COMMENT = re.compile(r"^([ \t]*)#.*$", re.M)


def _blank(match: re.Match[str]) -> str:
    """Same newlines, no text -- so `file:line` in every caller's finding stays true."""
    return "\n" * match.group(0).count("\n")


def strip_comments(source: str) -> str:
    """Blank every comment in place. Safe on both `.rb` and `.erb`; the patterns do not overlap."""
    source = ERB_COMMENT.sub(_blank, source)
    source = HTML_COMMENT.sub(_blank, source)
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
