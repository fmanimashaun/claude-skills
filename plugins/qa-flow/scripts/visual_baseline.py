#!/usr/bin/env python3
"""Judge a visual comparison run against committed baselines.

Run:  python3 visual_baseline.py qa/manual-tests/visual.json
      python3 visual_baseline.py qa/manual-tests/visual.json --config qa/qa.config.yml
      python3 visual_baseline.py --masks --routes / /dashboard   # resolve masks for the collector
      python3 visual_baseline.py --schema
      python3 visual_baseline.py --selftest

WHY (#112). The audit produced 359 screenshots and had nothing to compare them to. Capturing
evidence is not regression testing; the comparison is the whole product.

FOUR STATES, AND THE THIRD IS THE ONE THAT MATTERS:

    match       within tolerance
    REGRESSION  over tolerance -- a finding
    new         no baseline exists: "needs approval", and it is NEITHER a pass NOR a failure
    UNUSABLE    the run cannot be judged at all

`new` is stated as an acceptance criterion on #112 for a reason. Treating a missing baseline as a
pass means a brand-new screen is "visually correct" the day it is written, which is exactly backwards
-- nothing has ever been reviewed. Treating it as a failure means every new screen breaks the build
and the tolerance gets raised until nothing fails at all. It is a third outcome and it blocks
nothing, but it is always counted and always listed.

THE AGENT NEVER PROMOTES A BASELINE. This file has no write path to `qa/baselines/` -- it cannot
promote, overwrite, or delete one, and there is a fixture asserting the module contains no such call.
A baseline is a human's assertion that a rendering is correct; an agent that can rewrite it can
launder a regression into the new truth in one run.

DETERMINISM IS THE CALLER'S JOB, and it is not optional: without frozen animations, a stable clock,
a pinned pixel ratio, loaded fonts and seeded data this is a flake generator, and a flaky visual
check is worse than none because it trains people to ignore it. The collector applies what it can
and records that it did; a run that does NOT record all five is reported as unusable, never judged.

IGNORE REGIONS ARE RESOLVED HERE AND APPLIED THERE, and the two are cross-checked. Which selectors
are dynamic on which route is a *policy* decision, so it lives in this gateable Python
(`--masks` prints the resolution for the collector to consume). Painting over them needs a browser,
so the collector does that and records what it painted. If the two disagree the run is REFUSED: a
config that says a clock is dynamic, paired with a run that never masked it, produced a ratio over
pixels nobody meant to compare — and reporting that number as either a match or a regression is a
guess. This is the whole reason the field is cross-checked rather than merely declared: `ignored`
was in the schema from the start, emitted as `[]` by the collector and read by nobody, so the
tolerance story was configurable and the ignore-region story was decoration (#112).

Exit codes:  0 no regressions (news are listed, not failed) · 1 regressions · 2 unusable

Stdlib only, no network, no image decoding: the browser computes the diff ratio, this judges it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "qa-flow/visual-run/1"
DEFAULT_MAX_DIFF = 0.002          # 0.2% of pixels
BASELINE_DIR = "qa/baselines"

# All five must be recorded true or the run is refused. Not bumped to `visual-run/2` when the last
# two were added on purpose: a stale collector already fails the check below with the exact key it
# omitted, which is more actionable than "not a visual-run/2 document" and fires on the same input.
DETERMINISM_KEYS = ("reducedMotion", "frozenClock", "pinnedScale", "fontsLoaded", "seededData")

SCHEMA_EXAMPLE = {
    "schema": SCHEMA,
    "determinism": {"reducedMotion": True, "frozenClock": True, "pinnedScale": True,
                    "fontsLoaded": True, "seededData": True},
    "shots": [{
        "route": "/dashboard", "viewport": "1280x900", "theme": "light",
        "baseline": "qa/baselines/1280x900-light/dashboard.png",
        "baselinePresent": True,
        "candidate": "qa/baselines/_candidates/1280x900-light/dashboard.png",
        "diff": "qa/baselines/_diffs/1280x900-light/dashboard.png",
        "diffRatio": 0.0004,
        "ignored": ["[data-testid=clock]"],
    }],
}
COLLECTOR = "crawl_collector.js"


class Unusable(RuntimeError):
    """The run cannot be judged -- reported, never treated as a clean comparison."""


@dataclass
class Judged:
    regressions: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)
    matched: int = 0


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Unusable(f"{path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise Unusable(f"{path}: not a {SCHEMA} document — run `--schema`")
    if not isinstance(data.get("shots"), list) or not data["shots"]:
        raise Unusable(
            f"{path}: no shots. An empty run reporting zero regressions is indistinguishable from a "
            "pixel-perfect app.")
    d = data.get("determinism") or {}
    missing = [k for k in DETERMINISM_KEYS if not d.get(k)]
    if missing:
        # Refusing beats reporting. Without these the diff ratios are noise, and a flaky visual
        # check is worse than none: it trains people to ignore the one report that needs eyes.
        raise Unusable(
            f"{path}: the run did not apply {missing}. Undeterministic renders make every ratio "
            "meaningless, so this is refused rather than judged.")
    return data


def tolerance_for(route: str, config: dict) -> float:
    """Per-route override, else the global, else the default. Longest matching prefix wins."""
    visual = (config or {}).get("visual") or {}
    overrides = visual.get("per_route") or {}
    best, value = -1, visual.get("max_diff_ratio", DEFAULT_MAX_DIFF)
    for pattern, override in overrides.items():
        if route.startswith(pattern) and len(pattern) > best:
            best, value = len(pattern), override
    return float(value)


def ignores_for(route: str, config: dict) -> list[str]:
    """Selectors masked on this route: the global list PLUS every matching per-route list.

    Union, deliberately -- not longest-prefix-wins like the tolerance. A tolerance is one number and
    a route must be able to override it in both directions. A mask is an assertion that a region is
    dynamic, and a route-specific assertion does not make a global one false: if the clock is live
    everywhere, naming a chart on /dashboard must not quietly unmask the clock there. Silently
    dropping a global mask is invisible in the output and shows up only as a flake weeks later.
    """
    visual = (config or {}).get("visual") or {}
    out = list(visual.get("ignore") or [])
    for pattern, selectors in (visual.get("ignore_per_route") or {}).items():
        if route.startswith(pattern):
            out.extend(selectors)
    return sorted(set(out))


def read_config(path: Path | None) -> dict:
    """A deliberately tiny reader for the handful of keys this needs.

    Not a YAML parser: PyYAML is not stdlib, and taking a dependency for `max_diff_ratio` would put
    a third-party import in a gate. It reads the `visual:` block only, and anything it cannot parse
    is REFUSED rather than silently defaulted -- a tolerance that silently reverts to 0.002 while the
    config says otherwise is a regression waved through.

    That last sentence was in this docstring before anything enforced it: the old reader skipped
    every line it did not recognise, so `max_diff_ratio: 1e-2` (not matched by `[0-9.]+`) fell back
    to the 0.002 default and the run was judged 5x TIGHTER than the config asked for, silently. A
    promise in a docstring that the code does not keep is the exact claims-vs-enforcement defect this
    repo keeps finding, so it is now an `Unusable` naming the file, line number and text.

    Shapes accepted inside `visual:`

        max_diff_ratio: 0.002       global tolerance
        /checkout: 0.0001           per-route tolerance (longest matching prefix wins)
        ignore:                     selectors masked on EVERY route
          - "[data-testid=clock]"
        ignore_per_route:           selectors masked on routes with this prefix, ADDED to `ignore`
          /dashboard:
            - ".live-chart"
    """
    if path is None or not path.is_file():
        return {}
    out: dict = {"visual": {}}
    per_route: dict[str, float] = {}
    ignore: list[str] = []
    ignore_per_route: dict[str, list[str]] = {}
    section = False
    mode: str | None = None          # None | "ignore" | "ignore_per_route"
    current: str | None = None       # the route whose mask list we are inside
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if re.match(r"^\S", raw):
            section = raw.strip().startswith("visual:")
            mode, current = None, None
            continue
        if not section:
            continue
        m = re.match(r"^\s+max_diff_ratio:\s*([0-9.eE+-]+)\s*$", raw)
        if m:
            mode, current = None, None
            out["visual"]["max_diff_ratio"] = _number(m.group(1), path, lineno, raw)
            continue
        if re.match(r"^\s+ignore:\s*$", raw):
            mode, current = "ignore", None
            continue
        if re.match(r"^\s+ignore_per_route:\s*$", raw):
            mode, current = "ignore_per_route", None
            continue
        m = re.match(r"^\s+-\s+(.*\S)\s*$", raw)
        if m and mode:
            selector = m.group(1).strip().strip("'\"")
            if mode == "ignore":
                ignore.append(selector)
            elif current:
                ignore_per_route.setdefault(current, []).append(selector)
            else:
                raise Unusable(f"{path}:{lineno}: {raw.strip()!r} is a mask with no route above it")
            continue
        m = re.match(r"^\s+(\S+):\s*$", raw)
        if m and mode == "ignore_per_route":
            current = m.group(1)
            ignore_per_route.setdefault(current, [])
            continue
        m = re.match(r"^\s+([/\w.-]+):\s*([0-9.eE+-]+)\s*$", raw)
        if m:
            mode, current = None, None
            per_route[m.group(1)] = _number(m.group(2), path, lineno, raw)
            continue
        raise Unusable(_unreadable(path, lineno, raw))
    if per_route:
        out["visual"]["per_route"] = per_route
    if ignore:
        out["visual"]["ignore"] = ignore
    if ignore_per_route:
        out["visual"]["ignore_per_route"] = ignore_per_route
    return out


def _unreadable(path: Path, lineno: int, raw: str) -> str:
    return (f"{path}:{lineno}: cannot read {raw.strip()!r} inside the `visual:` block. Refused "
            "rather than defaulted — a tolerance that silently reverts to the default is a "
            "regression waved through. Run `--schema` for the shapes this accepts.")


def _number(text: str, path: Path, lineno: int, raw: str) -> float:
    try:
        return float(text)
    except ValueError as exc:
        raise Unusable(f"{path}:{lineno}: {raw.strip()!r} is not a number") from exc


def judge(run: dict, config: dict) -> Judged:
    result = Judged()
    for shot in run["shots"]:
        route = str(shot.get("route", ""))
        where = (f"{shot.get('route', '?')} @ {shot.get('viewport', '?')} "
                 f"{shot.get('theme', '?')}")
        # THE MASK CLAIM IS VERIFIED, NOT TRUSTED. Compared in both directions on purpose: a mask
        # the config demanded and the run never applied leaves live pixels in the ratio, and a mask
        # the run applied that no config asked for hides pixels nobody agreed to stop watching --
        # which is a regression made invisible, the worse of the two.
        want = ignores_for(route, config)
        got = sorted({str(s) for s in (shot.get("ignored") or [])})
        if want != got:
            raise Unusable(
                f"{where}: the config masks {want or '[]'} but the run recorded {got or '[]'}. The "
                "ratio was measured over different pixels than the config describes, so it is "
                "refused rather than judged — pass the resolved masks to the collector with "
                "`visual_baseline.py --masks --routes ... > qa/manual-tests/masks.json` and "
                "`crawl_collector.js --masks qa/manual-tests/masks.json`.")
        if not shot.get("baselinePresent"):
            result.new.append(f"{where} — no baseline; candidate at "
                              f"{shot.get('candidate', '(not written)')}")
            continue
        ratio = shot.get("diffRatio")
        if not isinstance(ratio, (int, float)):
            result.new.append(f"{where} — baseline exists but no diff was computed")
            continue
        limit = tolerance_for(route, config)
        if ratio > limit:
            # A ratio without the picture is a number nobody can act on: the reviewer's next
            # question is always "changed WHERE", and answering it is the difference between a
            # report that gets triaged and one that gets a tolerance bump.
            picture = shot.get("diff") or "(none written: the collector produced no diff image)"
            result.regressions.append(
                f"{where} — {ratio:.4%} of pixels changed, over the {limit:.4%} tolerance; "
                f"candidate at {shot.get('candidate', '(not written)')}; diff image at {picture}")
        else:
            result.matched += 1
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Judge a visual run against committed baselines.")
    ap.add_argument("run", nargs="?", type=Path)
    ap.add_argument("--config", type=Path, default=Path("qa/qa.config.yml"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--schema", action="store_true")
    ap.add_argument("--masks", action="store_true",
                    help="print the resolved route→selector masks for the collector to apply")
    ap.add_argument("--routes", nargs="*", default=[])
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.schema:
        print(json.dumps(SCHEMA_EXAMPLE, indent=2))
        return 0
    if args.masks:
        # Printed, never written: the judging path holds no write call, and adding one here to
        # save a shell redirect would put a file-writing agent back inside the module whose whole
        # promise is that it cannot touch a baseline.
        try:
            config = read_config(args.config)
        except Unusable as exc:
            print(f"UNUSABLE: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({r: ignores_for(r, config) for r in args.routes}, indent=2))
        return 0
    if not args.run:
        ap.error("a run file is required (or --masks / --schema / --selftest)")
    try:
        result = judge(load(args.run), read_config(args.config))
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result.__dict__, indent=2))
    else:
        for r in result.regressions:
            print(f"  [REGRESSION] {r}")
        for n in result.new:
            print(f"  [new] {n}")
        print(f"\n{result.matched} matched, {len(result.regressions)} regression(s), "
              f"{len(result.new)} awaiting approval.")
        if result.new:
            # Never silent, and never counted either way. See the module docstring.
            print("A screen with no baseline has never been reviewed — it is not a pass. "
                  f"Promote a candidate into {BASELINE_DIR}/ yourself; nothing here writes there.")
    return 1 if result.regressions else 0


def selftest() -> int:
    failures: list[str] = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    det = {k: True for k in DETERMINISM_KEYS}

    def run(*shots):
        return {"schema": SCHEMA, "determinism": det, "shots": list(shots)}

    def shot(**kw):
        base = {"route": "/a", "viewport": "1280x900", "theme": "light",
                "baselinePresent": True, "diffRatio": 0.0, "candidate": "c.png",
                "diff": "d.png"}
        base.update(kw)
        return base

    def refused(fn) -> bool:
        try:
            fn()
        except Unusable:
            return True
        return False

    def matched(run_: dict, cfg: dict) -> int:
        """`judge().matched`, or -1 when the run was refused.

        A CRASH IS NOT A VERDICT. `judge` now raises on a mask mismatch, so a mutation that changes
        which masks resolve makes an *earlier* fixture throw and the whole selftest dies before the
        fixture written for that mutation ever reports — which `mutation_check.py` correctly refuses
        to count as a catch. Swallowing it here keeps every label reachable.
        """
        try:
            return judge(run_, cfg).matched
        except Unusable:
            return -1

    r = judge(run(shot()), {})
    check("an identical render matches", r.matched == 1 and not r.regressions and not r.new)

    r = judge(run(shot(diffRatio=0.5)), {})
    check("a large diff is a regression", len(r.regressions) == 1, f"{r}")

    # THE THIRD STATE: neither pass nor failure.
    r = judge(run(shot(baselinePresent=False)), {})
    check("a missing baseline is `new`", len(r.new) == 1, f"{r}")
    check("a missing baseline is NOT a regression", not r.regressions, f"{r}")
    check("a missing baseline is NOT counted as matched", r.matched == 0, f"{r.matched}")
    check("a baseline with no computed diff is also `new`",
          len(judge(run(shot(diffRatio=None)), {}).new) == 1)

    # TOLERANCES: global, per-route, and longest-prefix.
    cfg = {"visual": {"max_diff_ratio": 0.01}}
    check("a diff under the global tolerance matches",
          judge(run(shot(diffRatio=0.005)), cfg).matched == 1)
    cfg2 = {"visual": {"max_diff_ratio": 0.001, "per_route": {"/a": 0.01}}}
    check("a per-route override loosens", judge(run(shot(diffRatio=0.005)), cfg2).matched == 1)
    cfg3 = {"visual": {"max_diff_ratio": 0.5, "per_route": {"/a": 0.0001}}}
    check("a per-route override also TIGHTENS",
          len(judge(run(shot(diffRatio=0.005)), cfg3).regressions) == 1,
          "an override that can only loosen is a tolerance that only ever grows")
    # The LONGER prefix is declared FIRST on purpose. With it second, "last match wins" and
    # "longest match wins" give the same answer and the fixture proves nothing -- which is exactly
    # what happened: the mutation removing the length comparison SURVIVED until this was reordered.
    cfg4 = {"visual": {"per_route": {"/a/b": 0.0001, "/": 0.5}}}
    check("the longest matching prefix wins",
          len(judge(run(shot(route="/a/b/c", diffRatio=0.01)), cfg4).regressions) == 1,
          f"got {judge(run(shot(route='/a/b/c', diffRatio=0.01)), cfg4)}")

    # DIFF IMAGES. A ratio with no picture is a number nobody can triage (#112 criterion 1).
    r = judge(run(shot(diffRatio=0.5, diff="qa/baselines/_diffs/1280x900-light/a.png")), {})
    check("a regression names its diff image",
          "_diffs/1280x900-light/a.png" in r.regressions[0], f"{r.regressions}")
    r = judge(run(shot(diffRatio=0.5, diff=None)), {})
    check("a regression with no diff image says so rather than printing a bare ratio",
          "none written" in r.regressions[0], f"{r.regressions}")

    # IGNORE REGIONS. The claim is cross-checked in BOTH directions -- see judge().
    masked = {"visual": {"ignore": ["[data-testid=clock]"]}}
    check("a run that applied exactly the configured masks is judged",
          matched(run(shot(ignored=["[data-testid=clock]"])), masked) == 1)
    check("a mask the config demands but the run never applied is refused",
          refused(lambda: judge(run(shot(ignored=[])), masked)),
          "an unapplied mask leaves live pixels in a ratio judged as if they were static")
    check("a mask the run applied that no config asked for is refused",
          refused(lambda: judge(run(shot(ignored=[".surprise"])), {})),
          "masking pixels nobody agreed to stop watching hides a regression instead of reporting it")
    check("no configured masks and no applied masks is not a mismatch",
          matched(run(shot()), {}) == 1,
          "the common case must stay silent or the check gets switched off")
    # UNION, not longest-prefix-wins: a route-specific mask must not unmask the global one.
    both = {"visual": {"ignore": [".clock"], "ignore_per_route": {"/a": [".chart"]}}}
    check("a per-route mask ADDS to the global list rather than replacing it",
          ignores_for("/a", both) == [".chart", ".clock"], f"resolved {ignores_for('/a', both)}")
    check("a per-route mask does not leak onto a route that does not match",
          ignores_for("/b", both) == [".clock"], f"{ignores_for('/b', both)}")

    # DETERMINISM IS MANDATORY.
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "v.json"
        for label, body in (
            ("no determinism block", {"schema": SCHEMA, "shots": [shot()]}),
            ("motion not frozen",
             {"schema": SCHEMA, "determinism": {**det, "reducedMotion": False}, "shots": [shot()]}),
            ("no shots", {"schema": SCHEMA, "determinism": det, "shots": []}),
            ("wrong schema", {"schema": "x/1", "shots": [shot()]}),
            # A baseline shot at deviceScaleFactor 2 shares not one pixel with one shot at 1, and
            # a webfont that swaps after the screenshot changes every glyph on the page. Both are
            # 100%-diff flakes that read as catastrophic regressions.
            ("the pixel ratio was not pinned",
             {"schema": SCHEMA, "determinism": {**det, "pinnedScale": False}, "shots": [shot()]}),
            ("fonts were not awaited",
             {"schema": SCHEMA, "determinism": {**det, "fontsLoaded": False}, "shots": [shot()]}),
        ):
            p.write_text(json.dumps(body), encoding="utf-8")
            n += 1
            try:
                load(p)
                failures.append(f"{label}: expected UNUSABLE")
            except Unusable:
                pass

        # THE CONFIG READER MUST NOT SILENTLY DEFAULT.
        c = Path(tmp) / "qa.config.yml"
        c.write_text("app:\n  port: 3000\nvisual:\n  max_diff_ratio: 0.02\n  /checkout: 0.0001\n",
                     encoding="utf-8")
        cfg5 = read_config(c)
        check("the config reader finds the global tolerance",
              cfg5["visual"]["max_diff_ratio"] == 0.02, f"{cfg5}")
        check("the config reader finds a per-route tolerance",
              cfg5["visual"]["per_route"]["/checkout"] == 0.0001, f"{cfg5}")
        check("keys outside the visual block are ignored",
              "port" not in str(cfg5.get("visual")), f"{cfg5}")
        check("an absent config yields defaults, not a crash",
              read_config(Path(tmp) / "nope.yml") == {})

        # IGNORE REGIONS ARE CONFIGURABLE GLOBALLY AND PER ROUTE (#112 criterion 2).
        c2 = Path(tmp) / "masks.yml"
        c2.write_text(
            "app:\n  port: 3000\n"
            "visual:\n"
            "  # a comment inside the block must not be refused\n"
            "  max_diff_ratio: 0.01\n"
            "  ignore:\n"
            "    - \"[data-testid=clock]\"\n"
            "  ignore_per_route:\n"
            "    /dashboard:\n"
            "      - .live-chart\n"
            "      - .avatar\n", encoding="utf-8")
        cfg6 = read_config(c2)
        check("the config reader finds a GLOBAL ignore list",
              cfg6["visual"]["ignore"] == ["[data-testid=clock]"], f"{cfg6}")
        check("the config reader finds a PER-ROUTE ignore list",
              cfg6["visual"]["ignore_per_route"]["/dashboard"] == [".live-chart", ".avatar"],
              f"{cfg6}")
        check("a tolerance declared beside ignore lists still reads",
              cfg6["visual"]["max_diff_ratio"] == 0.01, f"{cfg6}")
        check("comments and blank lines inside the visual block are not refused",
              "ignore" in cfg6["visual"],
              "a reader that chokes on a comment is a reader nobody can configure")
        check("global and per-route masks resolve to the union on a matching route",
              ignores_for("/dashboard", cfg6) == [".avatar", ".live-chart", "[data-testid=clock]"],
              f"{ignores_for('/dashboard', cfg6)}")

        # THE DOCSTRING'S PROMISE, ENFORCED. `1e-2` was silently defaulted to 0.002 by the old
        # reader -- a 5x TIGHTER run than the config asked for, with nothing printed.
        c3 = Path(tmp) / "junk.yml"
        c3.write_text("visual:\n  max_diff_ratio: loose\n", encoding="utf-8")
        check("an unreadable tolerance is refused, not silently defaulted",
              refused(lambda: read_config(c3)),
              "the docstring promised this before any code did it")
        c4 = Path(tmp) / "junk2.yml"
        c4.write_text("visual:\n  wat: [1, 2]\n", encoding="utf-8")
        check("an unrecognised key inside the visual block is refused",
              refused(lambda: read_config(c4)))
        # 1e-4, and NOT 2e-3: 2e-3 IS the default, so a fixture asserting it would pass whether the
        # value was read or silently defaulted — vacuous in exactly the way this repo's mutation
        # gate exists to catch. The asserted number must be one the fallback cannot produce, which
        # is why the `!= DEFAULT_MAX_DIFF` is spelled out rather than left to the reader.
        c5 = Path(tmp) / "ok.yml"
        c5.write_text("visual:\n  max_diff_ratio: 1e-4\n", encoding="utf-8")
        check("scientific notation reads as the number it is, not as the default",
              read_config(c5)["visual"]["max_diff_ratio"] == 0.0001 != DEFAULT_MAX_DIFF,
              "refusing must not be so eager that a valid float is rejected")

    # THE AGENT MUST NOT BE ABLE TO PROMOTE A BASELINE. Asserted against this module's own source,
    # because "we would never do that" is not a guarantee -- a future edit adding a write here would
    # let one run launder a regression into the new truth.
    src = Path(__file__).read_text(encoding="utf-8")
    # Scoped to the JUDGING path -- everything before `def selftest`. The selftest itself writes
    # fixture files and must, so including it made this assertion fire on correct code. That is the
    # false positive that gets a rule deleted, so the scope is narrowed rather than the rule dropped.
    judging = src.split("def selftest(", 1)[0].split('"""', 2)[-1]
    for forbidden in ("write_text", "shutil", "rename", "unlink", "mkdir", "open("):
        check(f"the judging path never calls {forbidden} (it cannot promote a baseline)",
              forbidden not in judging, f"found {forbidden} in the judging path")

    collector = Path(__file__).with_name(COLLECTOR)
    check(f"{COLLECTOR} ships beside its judge", collector.is_file(), f"{collector} missing")
    if collector.is_file():
        js = collector.read_text(encoding="utf-8")
        missing = [f for f in SCHEMA_EXAMPLE["shots"][0]
                   if not re.search(rf"(?m)^\s*{re.escape(f)}\s*[,:]", js)]
        check("the collector emits every field the schema declares", not missing,
              f"{COLLECTOR} never emits {missing}")
        for key in DETERMINISM_KEYS:
            check(f"the collector records {key}", re.search(rf"(?m)^\s*{key}\s*[,:]", js) is not None,
                  f"{COLLECTOR} never records {key}, so the run would always be refused")
        # EMITTING THE FIELD IS NOT PRODUCING THE THING. `ignored` sat in this schema from the
        # start and the collector emitted a hardcoded `[]`, so the field check above passed for
        # three releases while ignore regions did not exist. These assert the collector reaches
        # for the APIs that make the two fields true, not merely that the keys are spelled.
        #
        # Scanned with `//` COMMENTS STRIPPED, because the first version of the deviceScaleFactor
        # check was a bare substring test and its own explanatory comment satisfied it: deleting
        # the actual option left the selftest green. A check that a comment can pass is not a check.
        code = re.sub(r"//.*$", "", js, flags=re.M)
        check("the collector applies masks with Playwright's screenshot `mask` option",
              re.search(r"\bmask:\s*\w", code) is not None,
              f"{COLLECTOR} records `ignored` but never masks anything — the field would be a claim")
        check("the collector writes the diff image it reports",
              re.search(r"writeFileSync\(\s*diff\b", code) is not None,
              f"{COLLECTOR} reports a `diff` path it never writes")
        check("the collector pins deviceScaleFactor rather than inheriting it",
              re.search(r"\bdeviceScaleFactor:\s*\w", code) is not None,
              f"{COLLECTOR} never pins deviceScaleFactor")
        check("the collector awaits document.fonts.ready",
              re.search(r"document\.fonts\.ready\b", code) is not None,
              f"{COLLECTOR} claims fontsLoaded without awaiting the fonts")
        # THE EXACT REGRESSION THAT HAPPENED, guarded by name. `ignored: []` reported no masks
        # while the screenshot masked plenty; the judge's cross-check refuses such a run at
        # runtime, but only once someone runs it against a config that declares masks. This fails
        # on the source, in CI, with no browser.
        check("the collector reports the masks it applied, not a hardcoded empty list",
              re.search(r"\bignored:\s*\[\s*\]", code) is None,
              f"{COLLECTOR} pushes a literal empty `ignored` — the field would be a claim again")

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {n} checks:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"visual_baseline selftest: {n} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
