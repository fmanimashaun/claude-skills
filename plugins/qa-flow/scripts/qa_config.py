#!/usr/bin/env python3
"""The ONE reader for `qa/qa.config.yml`. Stdlib only, no YAML dependency.

WHY THIS EXISTS (#792). There were two loaders -- `route_coverage.load_config` and
`blast_radius.load_config` -- structurally similar, separately written, and carrying the SAME
defect: the key pattern was anchored to end-of-line (`^\\s{2}(\\w+):\\s*(\\[\\s*\\])?\\s*$`), so any key
with a trailing comment was silently dropped. A trailing comment on every key is exactly what
`/qa-flow:setup-qa` scaffolds, so on the block the scaffolder writes **both loaders returned `{}`**
-- the whole declared configuration discarded, with no warning.

The visible symptom was never the config. `route_coverage` printed `excluded by config: 0`, which
reads as *"you declared no exclusions"* rather than *"your exclusions were discarded"*, and
`--fail-on-untested` then failed on an inflated denominator -- so it looked like a project problem.
That is the inverse of the risk `route_coverage`'s own docstring names: *"a suppression that leaves
no trace is how a coverage number quietly becomes a lie."* Declared-and-not-applied is equally
untraceable, and lands on the pessimistic side.

A SECOND DEFECT the report did not separate: the key pattern accepted an EMPTY inline list (`[]`)
and nothing else, so `exclude: ["/up", "/rails/"]` was dropped even with no comment in sight. Both
shapes are valid YAML and both are natural to write.

ONE IMPLEMENTATION, because two copies of a parser is what let one defect exist twice. Neither
loader had a fixture -- `route_coverage --selftest` passed 70 checks while `load_config` was
referenced only at its definition and its single call site.

WHAT IT HANDLES, all of which appear in the scaffold or in real project files:

    coverage:                       # a trailing comment on the section
      exclude: []                   # an EMPTY inline list, with a comment
      allow: ["/up", "/rails/"]     # a POPULATED inline list
      deny:                         # a block list
        - /admin                    # ...whose items may carry comments too
      high_risk:                    # one level of nesting
        money:
          - app/models/ledger.rb

A `#` INSIDE QUOTES IS DATA, not a comment. Stripping to the first `#` unconditionally is the
mistake this repo made in `check_ci_runs_tests` a few hours ago -- it truncated a legitimate value
and reported a conforming project as broken. A false positive is the failure that gets a tool
switched off.
"""
from __future__ import annotations

import re
from pathlib import Path

SECTION = re.compile(r"^(?P<name>[\w-]+):")
# The `$` anchor is NOT what fixes #792 -- `strip_comment` runs first, so by the time this matches
# there is no trailing comment left to defeat it. What changed is `(?P<inline>\[.*\])`, which was
# `(\[\s*\])` and therefore accepted only an EMPTY inline list. Keeping the anchor is deliberate:
# it still rejects a line with trailing junk that is not a comment.
KEY = re.compile(r"^(?P<indent>\s+)(?P<name>[\w-]+):\s*(?P<inline>\[.*\])?\s*$")
ITEM = re.compile(r"^(?P<indent>\s+)-\s*(?P<value>.*)$")


def strip_comment(line: str) -> str:
    """Everything before an UNQUOTED `#`.

    Quote-aware on purpose. `- "a#b"` is a value containing a hash, and truncating it would drop a
    legitimate entry -- the same false positive this repo shipped in a CI checker hours before this
    file was written, where stripping to the first `#` broke a command that contained one.
    """
    out, quote = [], None
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _scalar(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        return text[1:-1]
    return text


def _inline_list(text: str) -> list[str]:
    """`[]` -> [] and `["a", "b"]` -> ["a", "b"]. Split on commas OUTSIDE quotes."""
    inner = text.strip()[1:-1]
    parts, buf, quote = [], [], None
    for ch in inner:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    parts.append("".join(buf))
    return [_scalar(p) for p in parts if p.strip()]


def load_section(path: Path, section: str) -> dict[str, object]:
    """One top-level section, as `{key: [items]}` or `{key: {sub: [items]}}`.

    Returns `{}` when the file or the section is absent -- both callers already treat an absent
    config as "no configuration", and that is the one case where empty is the honest answer.
    """
    if not path.is_file():
        return {}
    block: dict[str, object] = {}
    inside = False
    key: str | None = None
    sub: str | None = None
    key_indent: int | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = strip_comment(raw)
        if not line.strip():
            continue
        top = SECTION.match(line)
        if top:
            if inside:
                # STOP at the first match rather than relying on the reassignment below. The two
                # agree for a well-formed file, so a mutation removing this survived every fixture
                # until one existed for a DUPLICATE top-level key -- which hand-edited YAML does
                # grow. Without the break the second block merges into the first, silently.
                break
            inside = top.group("name") == section
            continue
        if not inside:
            continue
        m = KEY.match(line)
        if m:
            indent = len(m.group("indent"))
            name, inline = m.group("name"), m.group("inline")
            if key_indent is None or indent <= key_indent:
                key_indent, key, sub = indent, name, None
                block[name] = _inline_list(inline) if inline else []
            else:                          # nested one level under `key`
                nested = block.get(key)
                if not isinstance(nested, dict):
                    nested = {}
                    block[key] = nested
                sub = name
                nested[name] = _inline_list(inline) if inline else []
            continue
        item = ITEM.match(line)
        if item and key is not None:
            value = _scalar(item.group("value"))
            if not value:
                continue
            target = block.get(key)
            if sub is not None and isinstance(target, dict):
                target.setdefault(sub, []).append(value)      # type: ignore[union-attr]
            elif isinstance(target, list):
                target.append(value)
    return block


def selftest() -> int:
    """Fixtures for the reader BOTH consumers depend on.

    Neither loader had one. `route_coverage --selftest` passed 70 checks while `load_config` was
    referenced only at its definition and its single call site, so the parser every coverage number
    depends on was entirely unexercised -- and a shared parser with no direct fixtures is one silent
    failure for every consumer, which is the second time that exact sentence has been written in
    this repo this week.
    """
    import tempfile
    checks, failures = 0, []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{('  ' + detail) if detail else ''}")

    def parse(text: str, section: str = "coverage") -> dict[str, object]:
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "qa.config.yml"
            f.write_text(text, encoding="utf-8")
            return load_section(f, section)

    # THE REPORTED DEFECT, verbatim from what `/qa-flow:setup-qa` scaffolds. Both loaders returned
    # `{}` on this -- the whole declared configuration discarded, silently.
    SCAFFOLD = (
        "coverage:                            # route coverage denominator (#119)\n"
        "  exclude: []                        # substrings: health endpoints\n"
        "  authenticated_prefixes: []         # e.g. /admin\n"
        "blast_radius:                        # derived regression scope (#134)\n"
        "  exclude: []                        # substrings\n"
        "  high_risk:                         # ADDS to the built-in axes\n"
        "    auth: []                         # e.g. app/models/api_key.rb\n"
        "    tenancy: []                      # e.g. app/models/account.rb\n")
    got = parse(SCAFFOLD)
    check("the scaffolded coverage block is READ, not discarded",
          set(got) == {"exclude", "authenticated_prefixes"}, f"{got}")
    got = parse(SCAFFOLD, "blast_radius")
    check("...and so is the scaffolded blast_radius block",
          set(got) == {"exclude", "high_risk"}, f"{got}")
    check("...including its nested axes",
          isinstance(got.get("high_risk"), dict)
          and set(got["high_risk"]) == {"auth", "tenancy"},   # type: ignore[index]
          f"{got.get('high_risk')}")

    # THE SECOND DEFECT the report did not separate: only an EMPTY inline list was accepted, so a
    # populated one was dropped with no comment in sight.
    got = parse('coverage:\n  exclude: ["/up", "/rails/"]\n')
    check("a POPULATED inline list is read", got.get("exclude") == ["/up", "/rails/"], f"{got}")
    got = parse("coverage:\n  exclude: []\n")
    check("an empty inline list stays empty", got.get("exclude") == [], f"{got}")

    # BLOCK LISTS, the form that always worked -- so the fixes above are not a rewrite that broke it.
    got = parse("coverage:\n  exclude:\n    - /up\n    - /rails/\n")
    check("a block list is read", got.get("exclude") == ["/up", "/rails/"], f"{got}")
    got = parse("coverage:\n  exclude:\n    - /up   # a health endpoint\n")
    check("...and its items may carry comments", got.get("exclude") == ["/up"], f"{got}")

    # A `#` INSIDE QUOTES IS DATA. Stripping to the first `#` unconditionally is the false positive
    # this repo shipped in a CI checker hours earlier; it must not be repeated here.
    got = parse('coverage:\n  exclude: ["/a#b"]\n')
    check("a quoted # is data, not a comment", got.get("exclude") == ["/a#b"], f"{got}")
    got = parse('coverage:\n  exclude:\n    - "/x#y"   # trailing\n')
    check("...in block items too", got.get("exclude") == ["/x#y"], f"{got}")

    # SECTION BOUNDARIES. Reading past the section would silently import another section's keys.
    got = parse(SCAFFOLD)
    check("the next section is not absorbed", "high_risk" not in got, f"{got}")
    check("an absent section is empty", parse(SCAFFOLD, "nonesuch") == {})
    # A DUPLICATE top-level key: the FIRST block wins, and the second does not merge into it.
    # Without this, removing the early `break` is indistinguishable from keeping it.
    dup = parse("coverage:\n  exclude:\n    - /first\ncoverage:\n  exclude:\n    - /second\n")
    check("a duplicate section does not merge into the first",
          dup.get("exclude") == ["/first"], f"{dup}")
    check("an absent file is empty", load_section(Path("/nonexistent/qa.config.yml"), "coverage") == {})

    # QUOTES are stripped from scalars, both list forms.
    got = parse("coverage:\n  exclude:\n    - '/quoted'\n")
    check("a quoted block item loses its quotes", got.get("exclude") == ["/quoted"], f"{got}")

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} qa-config assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    import sys as _sys
    if "--selftest" in _sys.argv:
        raise SystemExit(selftest())
    raise SystemExit("qa_config is a library; run --selftest to exercise it")
