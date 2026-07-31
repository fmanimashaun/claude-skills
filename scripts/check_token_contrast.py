#!/usr/bin/env python3
"""Measure the fidara role tokens against WCAG 1.4.3, from the doctrine file itself.

Run:  python3 scripts/check_token_contrast.py            # measure, fail on a violation
      python3 scripts/check_token_contrast.py --selftest  # prove the maths and the rules

WHY (#304). A contrast ratio is the most measurable claim in the whole design system, and it was
being asserted in prose. `--primary` on `--background` sat at **4.42:1** in light mode — under
1.4.3's 4.5:1 — and a doctrine table stated the number without anything re-deriving it, so it stayed
wrong. Measuring adjacent pairings then found a second, worse one the report had missed: the `.dark`
block overrode `--primary` to electric but NOT `--primary-foreground`, which therefore inherited
`#FFFFFF` from `:root` — white on `#00A3FF` is **2.73:1**, and that is the label on every primary
button in dark mode.

That second defect is the argument for this script. The first was found by a human reading a table;
the second was invisible until something enumerated the pairs mechanically. A token file is exactly
the kind of input where a person checks the pair they are thinking about and no others.

WHAT IT CHECKS. The pairs where a role token's value lands on another role token's surface as TEXT.
Only text pairs, because 1.4.3 is about text — a logo, a chart hue and a decorative fill are out of
scope and are deliberately not enumerated here. `--ring` is excluded too: it is used at `/30` over an
offset, so a flat pair would be a fiction.

WHAT IT DOES NOT CHECK. Alpha-modified colours (`primary/90`), gradients, and anything requiring a
rendered page — those need the browser, and `rendered_conformance.py` is where they belong. Large
text's 3:1 allowance is not modelled: every pair here is body-sized in at least one documented use,
so the stricter threshold is the honest one.

Exit codes:  0 clean · 1 a pair is under threshold · 2 the token file could not be parsed

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOKENS = REPO / "skills" / "fidara-design" / "references" / "foundations-tokens.md"

AA_NORMAL = 4.5

# (label, foreground token, background token, mode). Names are resolved through the file, so a
# renamed token is a parse error rather than a silently skipped pair.
PAIRS: tuple[tuple[str, str, str, str], ...] = (
    ("text-primary on the page",      "--primary",            "--background", "light"),
    ("text-primary on a card",        "--primary",            "--card",       "light"),
    ("primary button label",          "--primary-foreground", "--primary",    "light"),
    ("body text on the page",         "--foreground",         "--background", "light"),
    ("body text on a card",           "--card-foreground",    "--card",       "light"),
    ("text-primary on the page",      "--primary",            "--background", "dark"),
    ("text-primary on a card",        "--primary",            "--card",       "dark"),
    ("primary button label",          "--primary-foreground", "--primary",    "dark"),
    ("body text on the page",         "--foreground",         "--background", "dark"),
    ("body text on a card",           "--card-foreground",    "--card",       "dark"),
)

HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
DECL_RE = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")


class Unparseable(RuntimeError):
    """The token file did not yield what this check needs -- never a silent pass."""


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    channels = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def parse_tokens(text: str) -> dict[str, dict[str, str]]:
    """{mode: {token: raw value}} for the `:root` and `.dark` blocks.

    `.dark` INHERITS from `:root` -- which is the whole mechanism behind the second #304 defect, so
    modelling it is the point rather than a convenience.
    """
    # `@theme` holds the raw brand PALETTE (`--color-fm-*`); `:root` and `.dark` hold the ROLE
    # tokens that point into it. A role is therefore only resolvable with the palette in scope, so
    # the palette is parsed as a base layer both modes inherit. Skipping it made every role that
    # referenced a palette entry unresolvable -- which the checker reported rather than passing,
    # but a parser that reads half the file is still a parser that can miss a pair.
    # `@theme inline` is excluded: it re-exports roles as `--color-*` aliases for Tailwind, so
    # folding it in would let an alias shadow the role it aliases.
    palette: dict[str, str] = {}
    scopes: dict[str, dict[str, str]] = {"light": {}, "dark": {}}
    current: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("@theme inline"):
            current = None
        elif stripped.startswith("@theme"):
            current = "palette"
        elif stripped.startswith(":root"):
            current = "light"
        elif stripped.startswith(".dark"):
            current = "dark"
        elif stripped == "}":
            current = None
        if current:
            target = palette if current == "palette" else scopes[current]
            for name, value in DECL_RE.findall(line):
                target[name] = value.strip()
    if not palette:
        raise Unparseable(f"{TOKENS.name}: no `@theme` palette declarations found")
    # Assert the two ROLE blocks were seen BEFORE folding the palette in. Merging first would make
    # `not scopes["light"]` unreachable -- a gate that cannot fail, which is the class this repo
    # lints for. Caught by reading back my own edit.
    if not scopes["light"]:
        raise Unparseable(f"{TOKENS.name}: no `:root` declarations found")
    if not scopes["dark"]:
        raise Unparseable(f"{TOKENS.name}: no `.dark` declarations found")
    scopes["light"] = {**palette, **scopes["light"]}
    scopes["dark"] = {**scopes["light"], **scopes["dark"]}   # cascade, deliberately
    return scopes


def resolve(token: str, scope: dict[str, str], _seen: frozenset[str] = frozenset()) -> str:
    """A token's literal hex, following `var(--x)` chains."""
    if token in _seen:
        raise Unparseable(f"`{token}` resolves in a cycle")
    raw = scope.get(token)
    if raw is None:
        raise Unparseable(f"`{token}` is not declared -- renamed, or the parser missed its block")
    if HEX_RE.match(raw):
        return raw
    ref = re.fullmatch(r"var\((--[a-z0-9-]+)\)", raw)
    if not ref:
        raise Unparseable(f"`{token}` is `{raw}`, which is neither a hex nor a single var()")
    return resolve(ref.group(1), scope, _seen | {token})


def run() -> int:
    try:
        scopes = parse_tokens(TOKENS.read_text(encoding="utf-8"))
        rows = []
        for label, fg, bg, mode in PAIRS:
            f, b = resolve(fg, scopes[mode]), resolve(bg, scopes[mode])
            rows.append((mode, label, fg, bg, f, b, contrast(f, b)))
    except (OSError, Unparseable) as exc:
        print(f"CANNOT MEASURE: {exc}", file=sys.stderr)
        return 2

    failures = [r for r in rows if r[6] < AA_NORMAL]
    for mode, label, fg, bg, f, b, ratio in rows:
        mark = "ok  " if ratio >= AA_NORMAL else "FAIL"
        print(f"  [{mark}] {mode:5} {label:24} {fg} {f} on {bg} {b} = {ratio:.2f}:1")
    if failures:
        print(f"\n{len(failures)} pair(s) under WCAG 1.4.3's {AA_NORMAL}:1 for normal text.",
              file=sys.stderr)
        return 1
    print(f"\n{len(rows)} text pairs, all at or above {AA_NORMAL}:1.")
    return 0


def selftest() -> int:
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    # The maths, against the two standard controls. Without these the whole file is unfalsifiable.
    check("control: #767676 on white is 4.54", round(contrast("#767676", "#FFFFFF"), 2) == 4.54,
          f"got {contrast('#767676', '#FFFFFF'):.2f}")
    check("control: white on black is 21.00", round(contrast("#FFFFFF", "#000000"), 2) == 21.00,
          f"got {contrast('#FFFFFF', '#000000'):.2f}")
    check("contrast is symmetric",
          abs(contrast("#0072C4", "#FFFFFF") - contrast("#FFFFFF", "#0072C4")) < 1e-9)
    check("3-digit hex expands", abs(contrast("#FFF", "#000") - contrast("#FFFFFF", "#000000")) < 1e-9)

    # THE CASCADE, which is the defect this file exists for: `.dark` overrode `--primary` and not
    # `--primary-foreground`, so the latter inherited white from `:root` and nobody saw it.
    doc = ("@theme {\n  --color-x: #123456;\n}\n"
           ":root {\n  --a: #FFFFFF;\n  --b: #0077CC;\n}\n"
           ".dark {\n  --b: #00A3FF;\n}\n")
    scopes = parse_tokens(doc)
    check("dark inherits an un-overridden :root token", scopes["dark"].get("--a") == "#FFFFFF",
          f"got {scopes['dark'].get('--a')!r}")
    check("dark's own value wins", scopes["dark"].get("--b") == "#00A3FF",
          f"got {scopes['dark'].get('--b')!r}")

    # A missing or renamed token must RAISE, never resolve to something arbitrary -- a pair that
    # silently stops being measured is the skip-as-pass failure this repo keeps paying for.
    checks += 1
    try:
        resolve("--nope", scopes["light"])
        failures.append("a missing token resolved instead of raising")
    except Unparseable:
        pass
    checks += 1
    try:
        parse_tokens("nothing here")
        failures.append("a file with no :root block parsed instead of raising")
    except Unparseable:
        pass

    # var() chains resolve; a cycle raises rather than recursing forever.
    chain = parse_tokens("@theme {\n  --color-x: #123456;\n}\n:root {\n  --x: #0072C4;\n"
                         "  --y: var(--x);\n  --z: var(--y);\n}\n.dark {\n  --x: #00A3FF;\n}\n")
    check("a var() chain resolves", resolve("--z", chain["light"]) == "#0072C4",
          f"got {resolve('--z', chain['light'])}")
    checks += 1
    cyc = parse_tokens("@theme {\n  --color-x: #123456;\n}\n:root {\n  --p: var(--q);\n"
                       "  --q: var(--p);\n}\n.dark {\n  --p: #000000;\n}\n")
    try:
        resolve("--p", cyc["light"])
        failures.append("a var() cycle did not raise")
    except Unparseable:
        pass

    # NEAR MISS: the checker must not pass by measuring nothing. Every declared pair has to resolve
    # against the REAL file -- that is what catches a rename.
    checks += 1
    real = parse_tokens(TOKENS.read_text(encoding="utf-8"))
    try:
        for _label, fg, bg, mode in PAIRS:
            resolve(fg, real[mode]); resolve(bg, real[mode])
    except Unparseable as exc:
        failures.append(f"a declared pair no longer resolves against the real tokens: {exc}")
    check("PAIRS is not empty", len(PAIRS) >= 8, f"only {len(PAIRS)}")

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {checks} checks:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"check_token_contrast selftest: {checks} checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Measure fidara role tokens against WCAG 1.4.3.")
    ap.add_argument("--selftest", action="store_true", help="prove the maths and the rules")
    args = ap.parse_args(argv)
    return selftest() if args.selftest else run()


if __name__ == "__main__":
    sys.exit(main())
