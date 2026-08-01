#!/usr/bin/env python3
"""Judge a visual comparison run against committed baselines.

Run:  python3 visual_baseline.py qa/manual-tests/visual.json
      python3 visual_baseline.py qa/manual-tests/visual.json --config qa/qa.config.yml
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

DETERMINISM IS THE CALLER'S JOB, and it is not optional: without frozen animations, a stable clock
and seeded data this is a flake generator, and a flaky visual check is worse than none because it
trains people to ignore it. The collector applies those and records that it did; a run that does NOT
record them is reported as unusable rather than judged.

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

SCHEMA_EXAMPLE = {
    "schema": SCHEMA,
    "determinism": {"reducedMotion": True, "frozenClock": True, "seededData": True},
    "shots": [{
        "route": "/dashboard", "viewport": "1280x900", "theme": "light",
        "baseline": "qa/baselines/1280x900-light/dashboard.png",
        "baselinePresent": True,
        "candidate": "qa/baselines/_candidates/1280x900-light/dashboard.png",
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
    missing = [k for k in ("reducedMotion", "frozenClock", "seededData") if not d.get(k)]
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


def read_config(path: Path | None) -> dict:
    """A deliberately tiny reader for the two keys this needs.

    Not a YAML parser: PyYAML is not stdlib, and taking a dependency for `max_diff_ratio` would put
    a third-party import in a gate. It reads the `visual:` block only, and anything it cannot parse
    is reported rather than silently defaulted -- a tolerance that silently became 0.002 when someone
    wrote 0.02 is a regression waved through.
    """
    if path is None or not path.is_file():
        return {}
    out: dict = {"visual": {}}
    section, per_route = False, {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if re.match(r"^\S", raw):
            section = raw.strip().startswith("visual:")
            continue
        if not section:
            continue
        m = re.match(r"^\s+max_diff_ratio:\s*([0-9.]+)\s*$", raw)
        if m:
            out["visual"]["max_diff_ratio"] = float(m.group(1))
        m = re.match(r"^\s+([/\w.-]+):\s*([0-9.]+)\s*$", raw)
        if m and m.group(1) != "max_diff_ratio":
            per_route[m.group(1)] = float(m.group(2))
    if per_route:
        out["visual"]["per_route"] = per_route
    return out


def judge(run: dict, config: dict) -> Judged:
    result = Judged()
    for shot in run["shots"]:
        where = (f"{shot.get('route', '?')} @ {shot.get('viewport', '?')} "
                 f"{shot.get('theme', '?')}")
        if not shot.get("baselinePresent"):
            result.new.append(f"{where} — no baseline; candidate at "
                              f"{shot.get('candidate', '(not written)')}")
            continue
        ratio = shot.get("diffRatio")
        if not isinstance(ratio, (int, float)):
            result.new.append(f"{where} — baseline exists but no diff was computed")
            continue
        limit = tolerance_for(str(shot.get("route", "")), config)
        if ratio > limit:
            result.regressions.append(
                f"{where} — {ratio:.4%} of pixels changed, over the {limit:.4%} tolerance; "
                f"candidate at {shot.get('candidate', '(not written)')}")
        else:
            result.matched += 1
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Judge a visual run against committed baselines.")
    ap.add_argument("run", nargs="?", type=Path)
    ap.add_argument("--config", type=Path, default=Path("qa/qa.config.yml"))
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--schema", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.schema:
        print(json.dumps(SCHEMA_EXAMPLE, indent=2))
        return 0
    if not args.run:
        ap.error("a run file is required (or --schema / --selftest)")
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

    det = {"reducedMotion": True, "frozenClock": True, "seededData": True}

    def run(*shots):
        return {"schema": SCHEMA, "determinism": det, "shots": list(shots)}

    def shot(**kw):
        base = {"route": "/a", "viewport": "1280x900", "theme": "light",
                "baselinePresent": True, "diffRatio": 0.0, "candidate": "c.png"}
        base.update(kw)
        return base

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
        for key in ("reducedMotion", "frozenClock", "seededData"):
            check(f"the collector records {key}", re.search(rf"(?m)^\s*{key}\s*[,:]", js) is not None,
                  f"{COLLECTOR} never records {key}, so the run would always be refused")

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {n} checks:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"visual_baseline selftest: {n} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
