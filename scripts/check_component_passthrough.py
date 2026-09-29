#!/usr/bin/env python3
"""Every shipped ViewComponent must accept caller attributes (#1063).

Run:  python3 scripts/check_component_passthrough.py
      python3 scripts/check_component_passthrough.py --selftest

WHY THIS EXISTS. A consumer app with a mandated button component was audited and found **18 raw
`<button>` tags**. Nine hand-wrote the class string; one identical string appeared three times and
omitted `whitespace-nowrap` -- a class the component had gained *because a table's action column
broke mid-word* -- and two of those three copies sat in admin table action cells, carrying the exact
defect the component was fixed for and unable to receive the fix.

The reported cause was "the component cannot express what I need". **For the button that was false**
-- it already took `**attrs` -- but the reporter's own follow-up measurement found the claim is true
of most of the catalogue: of the 23 ViewComponent classes this skill ships as reference code, **17
took a fixed keyword list** and would drop a `form:` or a `data:` on the floor. A consumer who needs
a Stimulus target on a Modal, a Dropdown, a Toast or a Breadcrumbs reaches for the component, finds
it cannot carry one, and writes the tag by hand. **The catalogue produced the raw HTML it forbids.**

WHAT IT ASSERTS, in two parts, because one without the other is worse than neither.
`components.md` now states passthrough as contract, and a sentence in prose that the shipped code
contradicts is the claims-vs-enforcement defect this repository is organised around -- so the
sentence gets a check. Every `class <Name>Component < ViewComponent::Base` in the shipped
references must:

  1. **accept** a `**` splat in its initializer signature, and
  2. **store** it -- bind it to an ivar somewhere in the class.

**The second half was added after the first was written, and the first alone would have shipped a
worse defect than it fixed.** Widening the 17 signatures made this check green while every one of
them still discarded the hash: Ruby binds `**attrs` and drops it on the floor with no error, so a
caller's `data-controller` would have vanished *silently* where before it raised `ArgumentError`
loudly. A loud failure sends a developer to the component; a silent one sends them to hand-written
HTML and they never learn why.

WHAT IT DELIBERATELY DOES NOT ASSERT. That the stored attributes are rendered onto the root
element. That lives in an ERB template or a `call` method and is not decidable from the class body;
a check claiming it would be a gate that cannot fail. Accept and store are exact and are where the
failure starts. The render is doctrine, stated in `components.md` beside the rule.

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The shipped reference implementations. Both are consumed as copy-me-verbatim code by
# `ui-composer` and `design-porter`, so a fixed keyword list here becomes one in a user's app.
SOURCES = (
    "skills/design-system/references/component-implementations.md",
    "skills/design-system/references/reference-implementation.md",
)

CLASS = re.compile(r"^(?P<indent>[ \t]*)class (?P<name>\w+) < ViewComponent::Base[ \t]*$", re.M)


# A nested body OPENER: `class Name`, `class << self`, `module Name`, or a block that defines a class
# (`X = Struct.new(...) do`, `Data.define do`, `Class.new do`). Not `class: "..."` (a keyword
# argument) or `class="..."` (ERB), both common in component bodies. Judged on the code before any
# trailing `#` comment, so `class Error < StandardError; end # why` is a one-liner (#1487 review).
NESTED = re.compile(r"^([ \t]*)(?:class[ \t]+(?:[A-Z]|<<)|module[ \t]+[A-Z]"
                    r"|(?:[A-Z]\w*[ \t]*=[ \t]*)?(?:Struct\.new|Data\.define|Class\.new)\b.*(?:\bdo\b|\{)[ \t]*(?:\|[^|]*\|)?[ \t]*$)")
ONE_LINER = re.compile(r"\bend\s*$")
HEREDOC = re.compile(r"<<[~-]?(['\"]?)([A-Z_][A-Z0-9_]*)\1")


def _code(line: str) -> str:
    """`line` without a trailing `#` comment. Approximate -- a `#` inside a string ends it early --
    but only ever used to find `end` and one-liners, where that cannot turn code into a match."""
    return line.split("#", 1)[0].rstrip()


def own_lines(body: list[str]) -> list[str]:
    """The class body WITHOUT its nested `class` / `module` bodies (#1434).

    A component with a nested helper class declared above its own initializer had the NESTED
    class's `def initialize(` judged, because the scan took the first one in the body. Retask's
    `Ui::DetailsCardComponent` (a nested `Section`) read as "a fixed keyword list" while its own
    initializer took `**attrs`, and the downstream workaround was to reorder a correct file. A
    nested body ends at the `end` at its own indent -- `end # Section` included -- the same rule the
    component body uses. A heredoc's lines are text: a line in one starting `class X` opens nothing.
    """
    out, skip_indent, closer, heredoc = [], None, "end", None
    for line in body:
        if heredoc is not None:
            if line.strip() == heredoc:
                heredoc = None
            if skip_indent is None:
                out.append(line)
            continue
        h = HEREDOC.search(_code(line))
        if skip_indent is not None:
            if _code(line).strip() == closer and len(line) - len(line.lstrip()) == skip_indent:
                skip_indent = None
            elif h:
                heredoc = h.group(2)
            continue
        # The OPENER is judged on code too: `Row = Struct.new(:a) # do not reorder` opens nothing.
        m = NESTED.match(_code(line))
        if m and not ONE_LINER.search(_code(line)):
            skip_indent = len(m.group(1))
            closer = "}" if _code(line).endswith("{") or re.search(r"\{[ \t]*\|[^|]*\|$", _code(line)) else "end"
            continue
        if h:
            heredoc = h.group(2)
        out.append(line)
    return out


def initializer_of(body: str) -> str | None:
    """The full `def initialize(...)` signature inside a class body, or None if it defines none.

    Signatures wrap. An earlier count of this same file used a one-line regex and reported 21
    classes where there are 23, because it missed a wrapped signature and an endless method -- so
    the parameter list is collected across lines until the parentheses balance.
    """
    m = re.search(r"def initialize\(", body)
    if not m:
        return None
    depth, out = 0, []
    for ch in body[m.start():]:
        out.append(ch)
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
    return "".join(out)


def classes_in(source: str) -> list[tuple[str, str | None, bool]]:
    """(class name, initializer signature or None, whether the splat is STORED) per component.

    THE SECOND HALF MATTERS AS MUCH AS THE FIRST. A signature that accepts `**attrs` and never
    assigns them is worse than one that refuses them: Ruby binds the hash and discards it, so the
    caller's `data-controller` vanishes with no error anywhere. Accepting an attribute you then
    drop is the silent version of the defect this check exists to find.
    """
    lines = source.split("\n")
    found = []
    for m in CLASS.finditer(source):
        start = source[: m.start()].count("\n")
        indent = len(m.group("indent"))
        body = []
        for line in lines[start + 1:]:
            if line.strip() == "end" and (len(line) - len(line.lstrip())) == indent:
                break
            body.append(line)
        blob = "\n".join(own_lines(body))
        # Stored if the splat name is bound to an ivar anywhere in the class -- `@attrs = attrs`,
        # a multiple assignment ending in `attrs`, or an endless `= @attrs = attrs`.
        stored = bool(re.search(r"@attrs\b\s*=|=\s*[^=\n]*\battrs\b", blob))
        found.append((m.group("name"), initializer_of(blob), stored))
    return found


def check(root: Path = REPO) -> tuple[list[str], int]:
    findings, examined = [], 0
    for rel in SOURCES:
        path = root / rel
        if not path.is_file():
            # NOT silence. A missing source means the check examined nothing, and "0 findings over
            # 0 components" is indistinguishable from a clean run.
            findings.append(f"{rel}: not found — this check examined none of its components")
            continue
        for name, sig, stored in classes_in(path.read_text(encoding="utf-8")):
            examined += 1
            if sig is not None and "**" in sig and not stored:
                findings.append(
                    f"{rel}: `{name}` accepts `**attrs` and never stores them — Ruby binds the "
                    f"hash and discards it, so a caller's `data-controller` vanishes with NO "
                    f"error. Accepting an attribute you drop is the silent form of the defect.")
                continue
            if sig is None:
                findings.append(
                    f"{rel}: `{name}` defines no initializer, so a caller cannot pass it anything. "
                    f"Give it `def initialize(**attrs)` and render them on the root element.")
            elif "**" not in sig:
                findings.append(
                    f"{rel}: `{name}` takes a fixed keyword list and would drop a caller's "
                    f"`data:`, `form:` or `aria:` on the floor. Add `**attrs`, store it, and splat "
                    f"it onto the root element — a component that cannot carry an attribute is one "
                    f"a consumer writes by hand instead.")
    return findings, examined


def _selftest() -> int:
    ok, bad = 0, []

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    GOOD = ("```ruby\nmodule Ui\n  class GoodComponent < ViewComponent::Base\n"
            "    def initialize(variant: :primary, **attrs)\n"
            "      @variant, @attrs = variant, attrs\n    end\n  end\nend\n```\n")
    BAD = ("```ruby\nmodule Ui\n  class BadComponent < ViewComponent::Base\n"
           "    def initialize(variant: :primary)\n      @variant = variant\n    end\n  end\nend\n```\n")
    WRAPPED = ("```ruby\nmodule Ui\n  class WrappedComponent < ViewComponent::Base\n"
               "    def initialize(id:, name:, label:, autocomplete: :list,\n"
               "                   select_only: false, **attrs)\n"
               "      @attrs = attrs\n    end\n  end\nend\n```\n")
    ENDLESS = ("```ruby\nmodule Ui\n  class EndlessComponent < ViewComponent::Base\n"
               "    def initialize(**attrs) = @attrs = attrs\n  end\nend\n```\n")
    NONE = ("```ruby\nmodule Ui\n  class BareComponent < ViewComponent::Base\n"
            "    renders_one :body\n  end\nend\n```\n")
    # THE SILENT ONE, and the reason this check has a second half. Ruby binds `**attrs` here and
    # discards it: the caller's attribute vanishes with no error, where a fixed keyword list would
    # at least have raised ArgumentError. Widening 17 signatures without this case would have made
    # the check green while making the defect quieter.
    DROPS = ("```ruby\nmodule Ui\n  class DropsComponent < ViewComponent::Base\n"
             "    def initialize(variant: :primary, **attrs)\n      @variant = variant\n"
             "    end\n  end\nend\n```\n")

    # #1434: a nested class declared above the component's own initializer is not the component.
    NESTED = ("```ruby\nmodule Ui\n  class CardComponent < ViewComponent::Base\n"
              "    class Section\n      def initialize(title:)\n        @title = title\n      end\n    end\n\n"
              "    def initialize(**attrs)\n      @attrs = attrs\n    end\n  end\nend\n```\n")
    NESTED_FIXED = ("```ruby\nmodule Ui\n  class FixedCardComponent < ViewComponent::Base\n"
                    "    class Section\n      def initialize(**attrs)\n        @attrs = attrs\n      end\n    end\n\n"
                    "    def initialize(title:)\n      @title = title\n    end\n  end\nend\n```\n")
    TAGGED = ("```ruby\nmodule Ui\n  class TaggedComponent < ViewComponent::Base\n"
              "    def call\n      tag.div(\n        class: \"row\"\n      )\n    end\n\n"
              "    def initialize(**attrs)\n      @attrs = attrs\n    end\n\n"
              "    class ItemComponent < ViewComponent::Base\n"
              "      def initialize(**attrs)\n        @attrs = attrs\n      end\n    end\n  end\nend\n```\n")
    got = dict((n, (sig, st)) for n, sig, st in classes_in(TAGGED))
    expect("a `class:` keyword line is not a nested class",
           "**" in (got.get("TaggedComponent", (None, False))[0] or "") and got.get("TaggedComponent", (None, False))[1])
    expect("a nested component after a blank line keeps its own initializer",
           "ItemComponent" in got and "**" in (got["ItemComponent"][0] or "") and got["ItemComponent"][1])
    # #1487 review: the shapes a first version of own_lines() got wrong.
    got = classes_in("```ruby\nmodule Ui\n  class OneLineCommentComponent < ViewComponent::Base\n    class Error < StandardError; end # raised on bad input\n\n    def initialize(**attrs)\n      @attrs = attrs\n    end\n  end\nend\n```\n")
    expect('a one-line nested class with a trailing comment opens no body', len(got) == 1 and "**" in (got[0][1] or "") and got[0][2])
    got = classes_in("```ruby\nmodule Ui\n  class EndCommentComponent < ViewComponent::Base\n    class Section\n      def initialize(title:)\n        @title = title\n      end\n    end # Section\n\n    def initialize(**attrs)\n      @attrs = attrs\n    end\n  end\nend\n```\n")
    expect('a nested body closed by `end # Section` ends there', len(got) == 1 and "**" in (got[0][1] or "") and got[0][2])
    got = classes_in("```ruby\nmodule Ui\n  class StructDoComponent < ViewComponent::Base\n    Section = Struct.new(:title) do\n      def initialize(title:)\n        super\n      end\n    end\n\n    def initialize(**attrs)\n      @attrs = attrs\n    end\n  end\nend\n```\n")
    expect('a Struct.new block above the initializer is not the component', len(got) == 1 and "**" in (got[0][1] or "") and got[0][2])
    got = classes_in("```ruby\nmodule Ui\n  class HeredocClassComponent < ViewComponent::Base\n    TEMPLATE = <<~RUBY\n      class Foo\n    RUBY\n\n    def initialize(**attrs)\n      @attrs = attrs\n    end\n  end\nend\n```\n")
    expect('a heredoc line starting `class` opens nothing', len(got) == 1 and "**" in (got[0][1] or "") and got[0][2])
    got = classes_in("```ruby\nmodule Ui\n  class OnlyNestedComponent < ViewComponent::Base\n    class Section\n      def initialize(**attrs)\n        @attrs = attrs\n      end\n    end\n  end\nend\n```\n")
    expect('an initializer only inside a nested class is reported as none', len(got) == 1 and got[0][1] is None)
    # The shipped design-flow check carries the same own_lines(); a fix to one copy must reach both.
    import ast as _ast
    def _src(path: Path, names: tuple[str, ...]) -> list[str]:
        tree = _ast.parse(path.read_text(encoding="utf-8"))
        text = path.read_text(encoding="utf-8")
        return [_ast.get_source_segment(text, n) for n in tree.body
                if (isinstance(n, _ast.FunctionDef) and n.name in names)
                or (isinstance(n, _ast.Assign) and any(getattr(t, "id", "") in names for t in n.targets))]
    names = ("NESTED", "ONE_LINER", "HEREDOC", "_code", "own_lines")
    shipped = REPO / "plugins/design-flow/scripts/check_component_contract.py"
    expect("own_lines() and its patterns are identical in the shipped design-flow copy",
           shipped.is_file() and _src(shipped, names) == _src(Path(__file__), names)
           and len(_src(Path(__file__), names)) == len(names))
    got = classes_in(NESTED)
    expect("a nested class's initializer declared first is not the component's (#1434)",
           len(got) == 1 and "**" in (got[0][1] or "") and got[0][2])
    got = classes_in(NESTED_FIXED)
    expect("CONTROL: the component's own fixed list is seen beside a nested splat, and its splat "
           "storage is not borrowed", len(got) == 1 and "**" not in (got[0][1] or "") and not got[0][2])

    expect("a component with **attrs is accepted",
           [n for n, _, _ in classes_in(GOOD)] == ["GoodComponent"]
           and "**" in (classes_in(GOOD)[0][1] or ""))
    # THE CONTROL on the same shape: without it, "accepts a splat" would also pass for a parser
    # that reported every signature as containing one.
    expect("a component with a fixed keyword list is refused",
           "**" not in (classes_in(BAD)[0][1] or ""))
    # A WRAPPED signature is the case a one-line regex got wrong, and getting it wrong under-counts
    # in the flattering direction -- the component reads as compliant because its splat was on the
    # second line and never seen.
    expect("a signature wrapped across lines is read whole",
           "**attrs" in (classes_in(WRAPPED)[0][1] or ""))
    expect("an endless-method initializer is read", "**" in (classes_in(ENDLESS)[0][1] or ""))
    # No initializer at all is its own finding, not a pass: the consumer still cannot pass anything.
    expect("a component with no initializer is reported, not skipped",
           classes_in(NONE)[0][1] is None)
    expect("a splat that is accepted and stored reads as stored", classes_in(GOOD)[0][2] is True)
    # THE DISCRIMINATING PAIR: same signature, one stores and one does not. A checker that read
    # only the signature would call both compliant, which is exactly what it did before this case.
    expect("a splat that is accepted and DROPPED reads as not stored",
           classes_in(DROPS)[0][2] is False and "**" in (classes_in(DROPS)[0][1] or ""))

    import tempfile
    work = Path(tempfile.mkdtemp(prefix="passthrough-selftest-"))
    try:
        for rel in SOURCES:
            p = work / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(GOOD, encoding="utf-8")
        findings, examined = check(work)
        expect("a tree of compliant components reports nothing", not findings and examined == 2)

        (work / SOURCES[0]).write_text(GOOD + DROPS, encoding="utf-8")
        findings, _ = check(work)
        expect("an accept-and-drop component is reported, and named as silent",
               len(findings) == 1 and "DropsComponent" in findings[0]
               and "never stores" in findings[0])

        (work / SOURCES[0]).write_text(GOOD + BAD, encoding="utf-8")
        findings, examined = check(work)
        expect("one non-compliant component is reported, by name",
               len(findings) == 1 and "BadComponent" in findings[0])
        expect("...and the compliant ones are still counted", examined == 3)

        # A MISSING SOURCE IS A FINDING. Reporting "clean" over a file that is not there is the
        # vacuous pass this whole repository is organised against.
        (work / SOURCES[0]).unlink()
        findings, _ = check(work)
        expect("a missing source file is a finding, not a clean run",
               any("not found" in f for f in findings))
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)

    if bad:
        print(f"ran {ok + len(bad)} assertion(s)\n\n{len(bad)} FAILED:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print(f"ran {ok} assertion(s)")
    print("every shipped ViewComponent must accept caller attributes, and the check says so")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()

    findings, examined = check()
    for f in findings:
        print(f"  {f}")
    print(f"\n{examined} shipped ViewComponent class(es) checked for attribute passthrough; "
          f"{len(findings)} finding(s).")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
