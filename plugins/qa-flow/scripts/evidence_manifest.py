#!/usr/bin/env python3
"""Make a long browser run survivable, and its evidence reviewable.

Run:  python3 evidence_manifest.py completed --results qa/reports/<run>/results.jsonl
      python3 evidence_manifest.py derive    --results qa/reports/<run>/results.jsonl \
                                             --expect  qa/reports/<run>/expected.txt
      python3 evidence_manifest.py index     --manifest qa/reports/<run>/manifest.json
      python3 evidence_manifest.py validate  --manifest qa/reports/<run>/manifest.json
      python3 evidence_manifest.py prune     --runs qa/reports --keep 3
      python3 evidence_manifest.py --selftest

TWO DEFECTS, ONE ARTEFACT (#111 + #120).

#111: the audit's crawler wrote its manifest only after the final page, so a crash at page 70
of 72 lost the whole run -- and one background run WAS stopped mid-flight, losing ~30 minutes
of work for zero usable output. `/qa-flow:certify` is the pre-`main` gate, so a lost run means
re-running the entire certification. The fix is append-only: one JSON line per unit as it
completes, and the aggregate DERIVED from that line log rather than held in memory.

#120: 359 PNGs in a flat folder, 12 of them 404 pages indistinguishable by eye, and full-page
captures 8050px tall proving a focus ring. Evidence needs naming that encodes its axes, a
manifest, a browsable index, recorded validity, and a retention policy.

WHY THESE ARE ONE THING. #120's `manifest.json` IS the aggregate #111 says must be derived from
the append-only log. Built separately, one writer would append per unit and another would
rebuild the summary from memory or from the filesystem, and the two would disagree exactly when
a run died -- the case both issues exist for. So `derive` is the only thing that writes a
manifest, and it reads nothing but the line log.

WHAT A KILLED RUN LEAVES. A truncated final line is expected, not corruption: the process died
mid-write. It is skipped with a count, never a crash, because a parser that dies on the
artifact of the crash it exists to survive has missed the point.

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from pathlib import Path

# `<route-slug>--<viewport>-<theme>[--<state>].png`: deterministic, sortable, self-describing.
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*--\d+x\d+-[a-z][a-z0-9-]*(--[a-z0-9][a-z0-9-]*)?\.png$")

# Capture scope is decided by PURPOSE, not by taste. An 8050px full-page capture proving "this
# button shows a focus ring" is unreadable, so evidence about a component must be clipped;
# evidence about the whole page's layout or theme legitimately is the whole page.
CLIPPED_PURPOSES = {"component", "interaction", "a11y"}
FULL_PURPOSES = {"layout", "theme", "visual-regression"}
PURPOSES = CLIPPED_PURPOSES | FULL_PURPOSES

REQUIRED_FIELDS = ("unit", "route", "status", "purpose")
BLOCKED = "blocked"


class Unusable(Exception):
    """The input cannot be processed -- never report success for it."""


def read_results(path: Path) -> tuple[list[dict], int]:
    """Parse the append-only log. Returns (units, skipped_truncated).

    A trailing partial line is the SIGNATURE of a killed run, so it is counted and skipped
    rather than raised. Anything malformed mid-file is also skipped -- one bad line must not
    cost the other 71 units, which is the whole reason the log is line-oriented.
    """
    if not path.is_file():
        raise Unusable(f"no results log at {path}")
    units: list[dict] = []
    truncated = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            truncated += 1
            continue
        if isinstance(row, dict) and row.get("unit"):
            units.append(row)
        else:
            truncated += 1
    return units, truncated


def cmd_completed(args: argparse.Namespace) -> int:
    """Units already done, so a resumed run can skip them (#111).

    Blocked units are NOT completed: a unit that timed out should be retried on the next run,
    or a transient hang becomes a permanent hole in the evidence.

    `--fresh` returns an EMPTY skip list rather than being handled by the caller, so resume is
    decided in exactly one place. A runner that asks this every time, and a `--fresh` that
    answers "nothing is done", cannot drift apart -- whereas a caller that implements its own
    fresh path has a second resume rule to keep in step.
    """
    if args.fresh:
        print("# --fresh: skip list is empty, every unit will run", file=sys.stderr)
        return 0
    units, truncated = read_results(Path(args.results))
    done = [u["unit"] for u in units if str(u.get("status", "")).lower() != BLOCKED]
    for unit in done:
        print(unit)
    print(f"# {len(done)} completed, {len(units) - len(done)} blocked (retryable), "
          f"{truncated} truncated line(s) skipped", file=sys.stderr)
    return 0


def derive(units: list[dict], expected: list[str], truncated: int) -> dict:
    """The manifest, derived from the line log and nothing else."""
    by_unit = {u["unit"]: u for u in units}
    reached = list(by_unit)
    unreached = [u for u in expected if u not in by_unit] if expected else []
    blocked = [u for u in units if str(u.get("status", "")).lower() == BLOCKED]
    invalid = [u for u in units if u.get("valid") is False]
    return {
        "units": list(by_unit.values()),
        "counts": {
            "expected": len(expected) if expected else len(reached),
            "reached": len(reached),
            "blocked": len(blocked),
            "invalid": len(invalid),
            "unreached": len(unreached),
            "truncated_lines": truncated,
        },
        # Listed explicitly, because "the run ended" and "the run covered everything" are
        # different claims and a summary that cannot tell them apart is the #111 defect.
        "unreached": unreached,
        "aborted": bool(unreached) or truncated > 0,
    }


def cmd_derive(args: argparse.Namespace) -> int:
    units, truncated = read_results(Path(args.results))
    expected: list[str] = []
    if args.expect:
        p = Path(args.expect)
        if p.is_file():
            expected = [x.strip() for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    manifest = derive(units, expected, truncated)
    out = Path(args.out) if args.out else Path(args.results).parent / "manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    c = manifest["counts"]
    print(f"manifest: {c['reached']}/{c['expected']} reached · {c['blocked']} blocked · "
          f"{c['invalid']} invalid · {c['unreached']} unreached -> {out}")
    if manifest["aborted"]:
        # Always written, and it says what it did not reach.
        print("run did NOT complete — unreached units are listed in the manifest", file=sys.stderr)
        for unit in manifest["unreached"]:
            print(f"  unreached: {unit}", file=sys.stderr)
    return 0


def validate_manifest(manifest: dict) -> list[str]:
    """The evidence contract, checked. Empty list = conforming."""
    problems: list[str] = []
    for index, unit in enumerate(manifest.get("units", [])):
        name = unit.get("unit") or f"<row {index}>"
        for field in REQUIRED_FIELDS:
            if not unit.get(field):
                problems.append(f"{name}: missing {field!r}")

        status = str(unit.get("status", "")).lower()
        if status == BLOCKED:
            # A timed-out unit is honest only if it says why; otherwise "blocked" becomes a way
            # to record nothing and still look complete.
            if not unit.get("reason"):
                problems.append(f"{name}: Blocked without a reason")
            continue

        purpose = str(unit.get("purpose", "")).lower()
        if purpose and purpose not in PURPOSES:
            problems.append(
                f"{name}: purpose {purpose!r} is not one of {'/'.join(sorted(PURPOSES))}"
            )

        capture = str(unit.get("capture", "")).lower()
        if not capture:
            problems.append(f"{name}: no capture scope recorded (clipped/full)")
        elif capture not in {"clipped", "full"}:
            problems.append(f"{name}: capture {capture!r} is not clipped or full")
        elif purpose in CLIPPED_PURPOSES and capture != "clipped":
            problems.append(
                f"{name}: {purpose} evidence captured full-page — an 8050px image proving a "
                "component detail is unreadable, so this purpose must be clipped"
            )

        image = str(unit.get("image", ""))
        if not image:
            problems.append(f"{name}: no image path")
        elif not NAME_RE.match(Path(image).name):
            problems.append(
                f"{name}: image {Path(image).name!r} does not match "
                "<route-slug>--<viewport>-<theme>[--<state>].png"
            )

        # Validity must be RECORDED, not assumed. #106: 12 captures of 404 pages sat beside
        # valid ones, indistinguishable until inspected by eye.
        if "valid" not in unit:
            problems.append(
                f"{name}: validity not recorded — an image from an unvalidated page is "
                "indistinguishable from real evidence (#106)"
            )
        elif unit["valid"] is False and not unit.get("reason"):
            problems.append(f"{name}: marked invalid without a reason")

        if unit.get("valid") is True and not unit.get("assertion"):
            problems.append(
                f"{name}: valid evidence without the assertion it supports — the only signal "
                "separating the page under test from an error page that also returned 200"
            )
    return problems


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.manifest)
    if not path.is_file():
        raise Unusable(f"no manifest at {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not manifest.get("units"):
        raise Unusable(f"{path} has no units — refusing to bless an empty evidence set")
    problems = validate_manifest(manifest)
    for problem in problems:
        print(f"  - {problem}")
    print(f"{len(manifest['units'])} unit(s) checked, {len(problems)} problem(s)")
    return 1 if problems else 0


def render_index(manifest: dict) -> str:
    """A browsable index, grouped by route, with validity visible.

    A flat folder of 359 PNGs is not reviewable; this is what turned it into something a human
    could actually browse. Deliberately dependency-free and inlined -- evidence must open from
    the filesystem years later, with no build step and no CDN.
    """
    by_route: dict[str, list[dict]] = {}
    for unit in manifest.get("units", []):
        by_route.setdefault(str(unit.get("route", "?")), []).append(unit)

    c = manifest.get("counts", {})
    parts = [
        "<!doctype html><meta charset=utf-8><title>QA evidence</title>",
        "<style>body{font:14px system-ui;margin:2rem;max-width:70rem}"
        "h2{margin-top:2rem;border-bottom:1px solid #ccc}"
        "figure{display:inline-block;margin:0 1rem 1rem 0;vertical-align:top}"
        "img{max-width:22rem;border:1px solid #ddd}"
        "figcaption{font-size:12px;max-width:22rem}"
        ".invalid{outline:3px solid #c00}.blocked{color:#c00}</style>",
        "<h1>QA evidence</h1>",
        f"<p>{c.get('reached', 0)}/{c.get('expected', 0)} reached · "
        f"{c.get('blocked', 0)} blocked · <strong>{c.get('invalid', 0)} invalid</strong> · "
        f"{c.get('unreached', 0)} unreached</p>",
    ]
    if manifest.get("aborted"):
        parts.append("<p class=blocked><strong>This run did not complete.</strong> "
                     "Unreached units: " + html.escape(", ".join(manifest.get("unreached", [])))
                     + "</p>")
    for route in sorted(by_route):
        parts.append(f"<h2>{html.escape(route)}</h2>")
        for unit in sorted(by_route[route], key=lambda u: str(u.get("image", ""))):
            if str(unit.get("status", "")).lower() == BLOCKED:
                parts.append(
                    f"<p class=blocked>BLOCKED {html.escape(str(unit.get('unit')))} — "
                    f"{html.escape(str(unit.get('reason', '')))}</p>"
                )
                continue
            image = html.escape(str(unit.get("image", "")))
            invalid = unit.get("valid") is False
            cls = " class=invalid" if invalid else ""
            label = "INVALID — " if invalid else ""
            caption = (f"{label}{html.escape(str(unit.get('purpose', '')))} · "
                       f"{html.escape(str(unit.get('capture', '')))} · "
                       f"{html.escape(str(unit.get('assertion', unit.get('reason', ''))))}")
            parts.append(f"<figure><img{cls} src='{image}' alt='{image}'>"
                         f"<figcaption>{caption}</figcaption></figure>")
    return "\n".join(parts) + "\n"


def cmd_index(args: argparse.Namespace) -> int:
    path = Path(args.manifest)
    if not path.is_file():
        raise Unusable(f"no manifest at {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    out = Path(args.out) if args.out else path.parent / "index.html"
    out.write_text(render_index(manifest), encoding="utf-8")
    print(f"index -> {out}")
    return 0


def prune(run_dirs: list[Path], keep: int, protected: set[str]) -> tuple[list[Path], list[Path]]:
    """Newest `keep` runs survive, as does any run a defect still references.

    Sorted by NAME, not mtime: run directories are date-stamped, and mtime changes when someone
    opens an index.html, which would silently reshuffle what gets deleted.
    """
    ordered = sorted(run_dirs, key=lambda p: p.name, reverse=True)
    kept, dropped = [], []
    for index, path in enumerate(ordered):
        if index < keep or path.name in protected:
            kept.append(path)
        else:
            dropped.append(path)
    return kept, dropped


def cmd_prune(args: argparse.Namespace) -> int:
    root = Path(args.runs)
    if not root.is_dir():
        raise Unusable(f"no runs directory at {root}")
    runs = [p for p in root.iterdir() if p.is_dir() and (p / "manifest.json").is_file()]
    protected = set(args.protect or [])
    kept, dropped = prune(runs, args.keep, protected)

    # Always printed, including when nothing was pruned: deletion nobody can see is how
    # evidence referenced by an open defect disappears without a trace.
    print(f"retention: keeping {len(kept)} run(s), pruning {len(dropped)}")
    for path in kept:
        why = " (protected: referenced by an open defect)" if path.name in protected else ""
        print(f"  keep  {path.name}{why}")
    for path in dropped:
        print(f"  prune {path.name}")
        if not args.dry_run:
            shutil.rmtree(path, ignore_errors=True)
    if args.dry_run and dropped:
        print("  (--dry-run: nothing deleted)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QA evidence durability and standards.")
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="command")

    c = sub.add_parser("completed", help="units already done, for a resumed run")
    c.add_argument("--results", required=True)
    c.add_argument("--fresh", action="store_true",
                   help="force a clean run: emit an empty skip list")
    c.set_defaults(func=cmd_completed)

    d = sub.add_parser("derive", help="build manifest.json from the append-only log")
    d.add_argument("--results", required=True)
    d.add_argument("--expect", help="file of expected unit ids, one per line")
    d.add_argument("--out")
    d.set_defaults(func=cmd_derive)

    v = sub.add_parser("validate", help="check the manifest against the evidence contract")
    v.add_argument("--manifest", required=True)
    v.set_defaults(func=cmd_validate)

    i = sub.add_parser("index", help="generate a browsable index.html")
    i.add_argument("--manifest", required=True)
    i.add_argument("--out")
    i.set_defaults(func=cmd_index)

    p = sub.add_parser("prune", help="apply the retention policy")
    p.add_argument("--runs", required=True)
    p.add_argument("--keep", type=int, default=3)
    p.add_argument("--protect", action="append", help="run name to keep (repeatable)")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_prune)

    args = parser.parse_args(argv)
    if args.selftest:
        import evidence_manifest_selftest as st

        return st.run()
    if not getattr(args, "func", None):
        parser.print_help()
        return 2
    try:
        return int(args.func(args))
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
