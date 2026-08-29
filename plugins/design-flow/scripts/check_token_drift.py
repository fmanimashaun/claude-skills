#!/usr/bin/env python3
"""Compare a project's managed token block against the plugin's, and say which side owns each gap.

Run:  python3 check_token_drift.py                       # app/assets/tailwind/application.css
      python3 check_token_drift.py --css path/to.css
      python3 check_token_drift.py --selftest

WHY THIS EXISTS (#750). A live project's `@theme` had diverged from `foundations-tokens.md` in ways
nobody had noticed: a warm ground the plugin could not express, six re-tuned slate steps, and four
roles the plugin never declared. It accumulated **silently** — the scaffold runs once, the plugin
ships new tokens, and nothing ever compares them again. By the time it was found it took a hand-written
repo-vs-plugin diff to see it.

THE LINE BETWEEN OURS AND THEIRS IS THE WHOLE DESIGN. A brand pack is *supposed* to add tokens; a
project is *supposed* to extend. So a check that flagged every difference would fire on correct work
and be switched off within a week -- the failure mode this repo files most. The line is the marker
`/* design-flow:tokens:begin */ … :end`, which `setup` writes and owns:

    inside  -> the plugin's. It must match, and a difference is drift.
    outside -> the project's. Never compared, never reported.

That marker did not exist until #754; the contract said "between markers" and named none. This check
is the reason it now does.

FOUR OUTCOMES, and only one of them is "you have a problem":

  * **missing**   -- the plugin declares a token the managed block does not. The project is behind;
                     re-run setup. This is how a new role never reaches an adopter.
  * **changed**   -- both declare it, values differ. Either the project re-tuned inside the managed
                     block (it belongs outside) or it predates a plugin change.
  * **extra**     -- the managed block declares something the plugin does not. Usually a local
                     extension written on the wrong side of the marker.
  * **unmanaged** -- no marker at all. **Reported as its own state, never as a pass.** Most existing
                     projects are here, and calling that clean would be the exact lie this exists to
                     prevent.

Exit codes:  0 = managed and in step · 1 = drift, or unmanaged · 2 = no CSS to read

Stdlib only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import doctrine_path                    # noqa: E402 -- same plugin, one resolver

# THE SHARED RESOLVER, not parent-counting (#777). `parents[N]` is calibrated for the marketplace
# CLONE; from an install the cache interposes `<plugin>/<version>/`, and the two shapes differ in
# DEPTH rather than offset -- so no hop count reconciles them and this check simply never ran for
# anyone who installed. That population is the least likely to notice, and the refusal below said
# "the plugin side is missing", which reads as a broken install rather than a resolver bug.
# Third recurrence of #617's class, second after the resolver existed.
_DOCTRINE = doctrine_path.find(Path(__file__).resolve())
DOC = ((_DOCTRINE / "references" / "foundations-tokens.md") if _DOCTRINE
       else Path("foundations-tokens.md"))          # unresolvable: main() refuses, naming every root
DEFAULT_CSS = Path("app/assets/tailwind/application.css")

# The one place the marker is spelled. `setup.md` writes it; this reads it. Two spellings would
# drift, and the thing being checked here is drift.
BEGIN = "design-flow:tokens:begin"
END = "design-flow:tokens:end"

DECL = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;\n]+)")


def managed_block(css: str) -> str | None:
    """Text between the markers, or None when the file is unmanaged."""
    i = css.find(BEGIN)
    j = css.find(END, i + 1) if i != -1 else -1
    return css[i + len(BEGIN):j] if i != -1 and j != -1 else None


def plugin_tokens(doc_text: str) -> dict[str, str]:
    """Every token the doctrine declares, normalised for comparison."""
    return {m.group(1): " ".join(m.group(2).split()) for m in DECL.finditer(doc_text)}


def compare(css: str, doc_text: str) -> tuple[str, list[str]]:
    """`(state, findings)`. State is `unmanaged`, `drift` or `clean`."""
    block = managed_block(css)
    if block is None:
        return "unmanaged", [
            f"no `{BEGIN}` marker — this file was scaffolded before the marker existed, or by hand. "
            f"Nothing can tell the plugin's tokens from yours, so nothing is checked. This is NOT a "
            f"pass: re-run /design-flow:setup to establish the managed block."]
    theirs = {m.group(1): " ".join(m.group(2).split()) for m in DECL.finditer(block)}
    ours = plugin_tokens(doc_text)
    out: list[str] = []
    for tok in sorted(set(ours) - set(theirs)):
        out.append(f"missing: the plugin declares {tok} and the managed block does not — this "
                   f"project is behind; re-run /design-flow:setup")
    for tok in sorted(set(theirs) - set(ours)):
        out.append(f"extra: {tok} is inside the managed block but the plugin does not declare it — "
                   f"a local extension belongs OUTSIDE the markers, where a re-run will not eat it")
    for tok in sorted(set(ours) & set(theirs)):
        if ours[tok] != theirs[tok]:
            out.append(f"changed: {tok} is {theirs[tok]!r} here and {ours[tok]!r} in the plugin — "
                       f"re-tune it outside the markers, or take the plugin's value")
    return ("drift" if out else "clean"), out


def _selftest() -> int:
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    doc = "--background: #FFF;\n--primary: #0077CC;\n"
    wrap = lambda body: f"/* {BEGIN} */\n{body}/* {END} */\n"          # noqa: E731

    state, f = compare(wrap("--background: #FFF;\n--primary: #0077CC;\n"), doc)
    check("an in-step managed block is clean", state == "clean" and f == [])

    state, f = compare(wrap("--background: #FFF;\n"), doc)
    check("a token the plugin adds is reported missing",
          state == "drift" and any(x.startswith("missing: ") and "--primary" in x for x in f))

    state, f = compare(wrap("--background: #FFF;\n--primary: #0069B4;\n"), doc)
    check("a re-tuned value is reported changed",
          any(x.startswith("changed: ") and "--primary" in x for x in f))

    state, f = compare(wrap("--background: #FFF;\n--primary: #0077CC;\n--mine: #123;\n"), doc)
    check("a local token INSIDE the markers is reported extra",
          any(x.startswith("extra: ") and "--mine" in x for x in f))

    # THE LINE THAT MAKES THIS SAFE. A project extending OUTSIDE the markers is doing the right
    # thing and must be silent -- a check that flagged it would be switched off within a week.
    outside = wrap("--background: #FFF;\n--primary: #0077CC;\n") + "--mine: #123;\n--yours: #456;\n"
    state, f = compare(outside, doc)
    check("a local token OUTSIDE the markers is silent", state == "clean" and f == [])

    # UNMANAGED IS NOT CLEAN. Most existing projects are here.
    state, f = compare("--background: #FFF;\n--primary: #0077CC;\n", doc)
    check("no marker is 'unmanaged', not 'clean'", state == "unmanaged")
    check("...and says so in as many words", any("NOT a pass" in x for x in f))
    # An opening marker with no closing one is also unmanaged, not a block running to EOF.
    state, _ = compare(f"/* {BEGIN} */\n--background: #FFF;\n", doc)
    check("an unterminated marker is unmanaged", state == "unmanaged")

    # Whitespace is normalised, so reformatting is not drift.
    state, f = compare(wrap("--background:   #FFF ;\n--primary:\t#0077CC;\n"), doc)
    check("reformatting is not drift", state == "clean")

    if DOC.is_file():
        toks = plugin_tokens(DOC.read_text(encoding="utf-8"))
        check("the real doctrine parses to a non-trivial token set", len(toks) > 40)
        check("...and includes a role added in this cycle", "--overlay" in toks)

    print(f"\n{ok} passed, {len(bad)} failed")
    for b in bad:
        print(f"  FAIL {b}")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--css", type=Path, default=DEFAULT_CSS)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if not a.css.is_file():
        print(f"no {a.css} — nothing to compare", file=sys.stderr)
        return 2
    if not DOC.is_file():
        # Name EVERY root tried. Naming one is what made #617 read as "the doctrine is missing"
        # when the truth was "I looked in the wrong place", sending reporters to check a path that
        # was never going to hold it.
        print(f"cannot locate foundations-tokens.md. Tried:\n"
              f"{doctrine_path.describe(Path(__file__).resolve())}", file=sys.stderr)
        return 2
    state, found = compare(a.css.read_text(encoding="utf-8"), DOC.read_text(encoding="utf-8"))
    if state == "clean":
        print(f"clean — {a.css}'s managed block is in step with the plugin")
        return 0
    print(f"{state}: {len(found)} finding(s) in {a.css}", file=sys.stderr)
    for f in found:
        print(f"  - {f}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
