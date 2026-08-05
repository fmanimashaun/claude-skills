#!/usr/bin/env python3
"""Hold `<section>` to the landmark rule the skill now states (#91, trust/support slice).

Run:  python3 scripts/check_section_landmarks.py            # measure, fail on a bare section
      python3 scripts/check_section_landmarks.py --selftest  # prove the rule fires AND stays silent

WHY. *ARIA in HTML* (W3C) gives `<section>` `role=region` **"if the `section` element has an
accessible name"** and `role=generic` otherwise -- `generic` being exactly what a `<div>` exposes.
So an unnamed `<section>` is inert markup that reads as structure: no landmark, no rotor entry,
nothing to skip to.

`page-anatomies.md` already obeyed this in 16 of its 18 `<section>` elements before the rule was
written down anywhere. That is the `claims-vs-enforcement` class inverted -- a practice with no
claim and no gate. Sixteen correct instances are not evidence the seventeenth will be, and an agent
copying our markup could not tell which case it was looking at.

THE RULE, and its one exception:

  bare-section   a `<section>` in shipped doctrine carries neither `aria-label` nor `aria-labelledby`

  HERO EXEMPTION. A hero band is deliberately unnamed: its heading is the page's `<h1>`, so naming
  the region repeats the page title and adds a navigation target pointing where the reader already
  stands. Exemptions are declared BY LOCATION below -- never inferred from the markup -- because a
  rule that recognises its own exception by pattern would exempt every future violation that
  happens to look similar. Adding one takes a deliberate edit and a reason.

WHAT IT DOES NOT DO. It never judges whether a name is *good*, and it never asks for a landmark
where there is no `<section>`. It answers one question: does a `<section>` we ship expose the role
its author evidently intended? That is a join against the markup, not taste.

Exit codes:  0 every section is named or declared * 1 a bare section * 2 a file could not be read

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "fidara-design" / "references"

# `<section` up to its closing `>`, tolerating newlines inside the tag.
SECTION = re.compile(r"<section\b[^>]*>", re.S)

# `<footer>` gets `role=contentinfo` only when it is NOT inside sectioning content -- otherwise
# `role=generic` (ARIA in HTML). Our own band rule tells authors to wrap bands in `<section>`, so
# a page footer placed inside one silently loses its landmark. The two rules interact, so one file
# holds both: they cannot drift apart if they are the same join over the same markup.
SECTIONING = ("section", "article", "aside", "main", "nav")
TAG = re.compile(rf"<(/?)({'|'.join(SECTIONING)}|footer)\b", re.I)

# A footer legitimately nested inside an <article> is an article's footer, and generic is correct
# for it. Declared by exact opening tag, like the heroes -- never inferred.
NESTED_FOOTER_EXEMPTIONS: dict[str, tuple[str, ...]] = {}
# `\b` is NOT enough: it matches between the `-` and the `a` of `data-aria-label`, so a
# `data-` prefixed attribute counted as an accessible name. Caught by this gate's own
# fixture. Require the attribute to START a token.
NAMED = re.compile(r"(?<![-\w])aria-(?:label|labelledby)\s*=", re.I)

# ONLY FENCED CODE IS MARKUP WE SHIP. Prose says `<section>` while *discussing* the rule -- the
# doctrine this gate was written beside does it six times -- and grading a sentence as markup is
# how a linter earns a reputation for noise. The fence is closed by a line of >= its own backtick
# count so a nested fence inside a block cannot end it early.
FENCE = re.compile(r"^(?P<t>`{3,})[a-z]*[ \t]*\n(?P<body>.*?)^(?P=t)`*[ \t]*$", re.M | re.S)


def code_blocks(text: str) -> list[tuple[int, str]]:
    """[(line offset of the body, body)] for every fenced block."""
    return [(text.count("\n", 0, m.start("body")), m.group("body")) for m in FENCE.finditer(text)]

# Declared exemptions: (file stem, the exact opening tag). Matching the WHOLE TAG, not a line
# number, so the exemption survives edits above it and does NOT survive a change to the tag
# itself -- adding a class is fine, quietly turning it into a different element is not.
HERO_EXEMPTIONS: dict[str, tuple[str, ...]] = {
    # Both worked examples in `art-direction.md` are marketing HERO bands carrying the page's
    # `<h1>` — the identical case the exemption was written for, in a second file. Declared rather
    # than the rule widened: a per-file list is what keeps a new bare `<section>` elsewhere failing.
    "art-direction": (
        '<section class="bg-card section-y">',
    ),
    "page-anatomies": (
        '<section class="bg-card section-y">',
        '<section class="stack text-center" style="--space: var(--space-s)">',
    ),
}

EXEMPTION_REASON = (
    "hero band -- its heading is the page's <h1>, so a region named from it repeats the page "
    "title and adds a navigation target pointing where the reader already is"
)


# ERB and HTML COMMENTS ARE NOT MARKUP. The doctrine beside this gate writes "its link list is NOT
# a `<nav>`" inside an ERB comment, and the tag walk counted that as an open <nav> that never
# closed -- so the footer beneath it reported as nested. Blanked rather than deleted, preserving
# length and newlines, so every reported line number stays true.
NON_MARKUP = re.compile(r"<%.*?%>|<!--.*?-->", re.S)


def strip_non_markup(body: str) -> str:
    return NON_MARKUP.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), body)


def nested_footers(body: str) -> list[tuple[int, str, str]]:
    """[(char offset, the footer's opening tag, the sectioning ancestor it sits in)]."""
    out: list[tuple[int, str, str]] = []
    stack: list[str] = []
    for m in TAG.finditer(body):
        closing, tag = bool(m.group(1)), m.group(2).lower()
        if tag == "footer":
            if not closing and stack:
                end = body.find(">", m.start())
                out.append((m.start(), body[m.start():end + 1] if end != -1 else "<footer>",
                            stack[-1]))
            continue
        if closing:
            if stack and stack[-1] == tag:
                stack.pop()
        else:
            stack.append(tag)
    return out


def scan(text: str, stem: str) -> tuple[list[str], int, int]:
    """(findings, total sections, exemptions actually used). Fenced code only."""
    findings: list[str] = []
    exempt = HERO_EXEMPTIONS.get(stem, ())
    total = used = 0
    for offset, raw in code_blocks(text):
        body = strip_non_markup(raw)
        for match in SECTION.finditer(body):
            total += 1
            tag = match.group(0)
            if NAMED.search(tag):
                continue
            if tag in exempt:
                used += 1
                continue
            line = offset + body.count("\n", 0, match.start()) + 1
            findings.append(
                f"{stem}.md:{line}: bare <section> exposes role=generic, not region -- name it "
                f"with aria-labelledby, or use <div>. {tag[:72]}"
            )
        for offset_c, tag, parent in nested_footers(body):
            if tag in NESTED_FOOTER_EXEMPTIONS.get(stem, ()):
                continue
            line = offset + body.count("\n", 0, offset_c) + 1
            findings.append(
                f"{stem}.md:{line}: <footer> inside <{parent}> exposes role=generic, not "
                f"contentinfo -- a page footer is a sibling of <main>, never a child of a band. "
                f"{tag[:56]}"
            )
    return findings, total, used


def run(paths: list[Path]) -> tuple[list[str], int]:
    findings: list[str] = []
    total = 0
    for path in sorted(paths):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"UNUSABLE: {path}: {exc}", file=sys.stderr)
            raise SystemExit(2)
        found, count, used = scan(text, path.stem)
        findings += found
        total += count
        # A DECLARED EXEMPTION THAT MATCHES NOTHING is a dead carve-out: the markup moved on and
        # the exemption now silently protects nothing while reading as though it does. Report it,
        # for the same reason `--audit-coverage` exists on the shell linter.
        declared = len(HERO_EXEMPTIONS.get(path.stem, ()))
        if declared and used < declared:
            findings.append(
                f"{path.stem}.md: {declared - used} declared hero exemption(s) matched no "
                f"<section> -- the markup changed, so remove the stale entry rather than leaving "
                f"a carve-out that protects nothing"
            )
    return findings, total


def selftest() -> int:
    failures: list[str] = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}{f' -- {detail}' if detail else ''}")

    def fenced(markup: str) -> str:
        return f"```erb\n{markup}\n```\n"

    # FIRES.
    bare = fenced('<section class="promo">\n<h2>Offers</h2>\n</section>')
    found, total, _ = scan(bare, "x")
    check("a bare section is a finding", len(found) == 1, f"{found}")
    check("it counts the section", total == 1, f"{total}")
    # `found[0]` guarded: a mutation that empties the list must produce a FAILED CHECK, not an
    # IndexError. A crash is not a verdict -- the harness cannot tell it from a broken selftest.
    first = found[0] if found else ""
    check("the finding names the role it actually exposes", "role=generic" in first, first)
    check("the reported line is inside the block, not the fence",
          first.split(":")[1:2] == ["2"], first)

    # STAYS SILENT -- both spellings of a name, and attribute order must not matter.
    for markup in ('<section aria-labelledby="h">',
                   '<section aria-label="Offers">',
                   '<section class="a" aria-labelledby="h" id="b">',
                   '<section\n  class="a"\n  aria-labelledby="h">',
                   '<section ARIA-LABEL="Offers">'):
        check(f"named section is silent: {markup[:34]!r}", not scan(fenced(markup), "x")[0], markup)

    # ONLY `aria-label`/`aria-labelledby` NAME AN ELEMENT. `aria-hidden`, `aria-describedby` and
    # friends are aria attributes that name nothing, and a section carrying one is still generic.
    for not_a_name in ('<section aria-hidden="true">',
                       '<section aria-describedby="d">',
                       '<section data-aria-label="x">'):
        check(f"{not_a_name[:32]!r} does not name the section",
              len(scan(fenced(not_a_name), "x")[0]) == 1, not_a_name)

    # A div is not our business, and neither is a section-less file.
    check("a div is ignored", not scan(fenced('<div class="promo">'), "x")[0])
    check("no sections at all is silent", scan("# just prose", "x") == ([], 0, 0))

    # PROSE IS NOT MARKUP. The doctrine beside this gate says `<section>` six times while
    # explaining the rule; grading a sentence would make the gate unpassable by its own author.
    check("a bare <section> in PROSE is not a finding",
          scan("A `<section>` is a landmark only when named.\n", "x") == ([], 0, 0))
    check("prose next to real markup does not hide the markup",
          len(scan("`<section>` in prose.\n\n" + fenced('<section class="p">'), "x")[0]) == 1)
    # AND THE OPPOSITE DISHONESTY: an extractor that reads nothing reports clean. Prove it reads.
    check("the extractor actually finds blocks", len(code_blocks(fenced("<p>x</p>"))) == 1)
    check("it finds every block, not just the first",
          len(code_blocks(fenced("<p>a</p>") + "\ntext\n\n" + fenced("<p>b</p>"))) == 2)

    # THE EXEMPTION IS BY EXACT TAG, NOT BY SHAPE. A lookalike must still fail, or the carve-out
    # is a hole rather than an exception.
    hero = HERO_EXEMPTIONS["page-anatomies"][0]
    check("the declared hero tag is exempt", not scan(fenced(hero), "page-anatomies")[0], hero)
    check("the same tag in ANOTHER file is not exempt",
          len(scan(fenced(hero), "components")[0]) == 1)
    # Differs only in its LAST characters, so a prefix-match carve-out would wave it through.
    lookalike = hero.replace("section-y", "section-x")
    check("the lookalike really is near-identical", lookalike[:20] == hero[:20], lookalike)
    check("a lookalike hero tag still fails", len(scan(fenced(lookalike), "page-anatomies")[0]) == 1,
          lookalike)

    # A STALE EXEMPTION IS REPORTED. Otherwise a carve-out outlives the markup it was written for.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "page-anatomies.md"
        f.write_text('```erb\n<section aria-labelledby="h">named</section>\n```\n',
                     encoding="utf-8")
        stale, _ = run([f])
        check("a declared exemption matching nothing is reported",
              any("matched no" in s for s in stale), f"{stale}")

    # ---- nested <footer> loses contentinfo (#475) ----------------------------------------
    check("a top-level footer is silent",
          not scan(fenced("<main>x</main>\n<footer>y</footer>"), "x")[0])
    for parent in ("section", "article", "aside", "main", "nav"):
        # The section case is NAMED, so only the footer rule is under test here -- a bare one
        # would fire both and the count assertion would stop meaning anything.
        opener = '<section aria-label="a">' if parent == "section" else f"<{parent}>"
        d = scan(fenced(f"{opener}<footer>y</footer></{parent}>"), "x")[0]
        check(f"a footer inside <{parent}> is reported", len(d) == 1, f"{d}")
        check(f"the finding names <{parent}> as the ancestor", d and parent in d[0], f"{d}")
    # A CLOSED ancestor is not an ancestor. Getting this wrong would flag every page footer that
    # follows a band, which is the shape our own doctrine prescribes.
    check("a footer AFTER a closed section is silent",
          not scan(fenced("<section aria-label=a>x</section>\n<footer>y</footer>"), "x")[0])
    check("nesting two deep still resolves to the innermost",
          "section" in (scan(fenced("<main><section aria-label=a><footer>y</footer>"
                                    "</section></main>"), "x")[0] or [""])[0])

    # COMMENTS ARE NOT MARKUP -- the bug this gate's own doctrine triggered.
    erb = fenced('<%# its link list is NOT a <nav> %>\n<footer>y</footer>')
    check("an ERB comment naming <nav> does not open one", not scan(erb, "x")[0], f"{scan(erb,'x')[0]}")
    html = fenced('<!-- <section> in a comment -->\n<footer>y</footer>')
    check("an HTML comment naming <section> does not open one", not scan(html, "x")[0])
    check("a bare <section> INSIDE a comment is not a finding",
          not scan(fenced('<%# <section class="x"> %>'), "x")[0])
    # Blanking must preserve line numbers, or every finding after a comment points at the wrong line.
    # MULTI-LINE on purpose: deleting a single-line comment removes no newline, so a one-line
    # fixture cannot tell blanking from deletion and the mutation would survive it.
    numbered = fenced('<%# a comment\n    spanning two lines %>\n<section class="p">')
    check("a line number after a comment is still correct",
          (scan(numbered, "x")[0] or [""])[0].split(":")[1:2] == ["4"],
          f"{scan(numbered, 'x')[0]}")

    # THE REAL FILES must pass, or the doctrine this gate was written beside is already false.
    real, count = run(sorted(SKILL.glob("*.md")))
    check("the shipped skill obeys its own rule", not real, "; ".join(real[:3]))
    check("and the gate actually read some sections", count >= 15, f"{count}")

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {n} checks:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"check_section_landmarks selftest: {n} checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()

    findings, total = run(sorted(SKILL.glob("*.md")))
    if findings:
        print(f"{len(findings)} finding(s):", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    exempt = sum(len(v) for v in HERO_EXEMPTIONS.values())
    print(f"section landmarks: {total} <section> element(s), all named or declared "
          f"({exempt} hero exemption(s): {EXEMPTION_REASON})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
