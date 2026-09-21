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

CLASS = re.compile(r"^(?P<indent>\s*)class (?P<name>\w+) < ViewComponent::Base\s*$", re.M)


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
        blob = "\n".join(body)
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
