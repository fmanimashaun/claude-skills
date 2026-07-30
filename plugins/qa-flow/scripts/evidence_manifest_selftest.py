#!/usr/bin/env python3
"""Prove a killed run still yields usable output, and the evidence contract actually binds.

Run:  python3 evidence_manifest.py --selftest   (or execute this file directly)

The fixture that matters most is a TRUNCATED final line, because that is the artifact of the
crash this code exists to survive. A parser that dies on it has reproduced the original defect
in the tool meant to fix it -- so it is tested first, and tested as data rather than as an
error.

The second theme is the difference between "the run ended" and "the run covered everything".
#111's defect was a summary that could not tell those apart, so `unreached` is asserted
explicitly rather than inferred from a count.

Stdlib only; no network, no browser.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import evidence_manifest as em  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def _tick() -> None:
    global CHECKS
    CHECKS += 1


def check(label: str, got, want) -> None:
    _tick()
    if got != want:
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="qaflow-evidence-manifest-"))


def unit(name: str, **kw) -> dict:
    row = {
        "unit": name, "route": f"/{name}", "status": "Observed", "purpose": "interaction",
        "capture": "clipped", "image": f"screenshots/{name}--1280x800-light.png",
        "valid": True, "assertion": "heading 'X'",
    }
    row.update(kw)
    return row


def write_log(rows: list[dict], *, truncate: bool = False) -> Path:
    path = _tmp() / "results.jsonl"
    body = "".join(json.dumps(r) + "\n" for r in rows)
    if truncate:
        body += json.dumps(unit("dying"))[:37]  # a half-written final line, no newline
    path.write_text(body, encoding="utf-8")
    return path


def run() -> int:
    # ---- THE fixture: a killed run leaves usable partial output ------------------------
    log = write_log([unit("home"), unit("about")], truncate=True)
    units, truncated = em.read_results(log)
    check("killed run: complete units survive", [u["unit"] for u in units], ["home", "about"])
    check("killed run: the half-written line is counted, not fatal", truncated, 1)

    # A malformed line mid-file must cost only that line -- not the other 71 units.
    mid = _tmp() / "results.jsonl"
    mid.write_text(json.dumps(unit("a")) + "\nNOT JSON\n" + json.dumps(unit("b")) + "\n",
                   encoding="utf-8")
    got, bad = em.read_results(mid)
    check("one bad line does not cost the run", [u["unit"] for u in got], ["a", "b"])
    check("the bad line is counted", bad, 1)

    _tick()
    try:
        em.read_results(_tmp() / "absent.jsonl")
        FAILURES.append("missing log: expected Unusable, got a result")
    except em.Unusable:
        pass

    # ---- 'the run ended' is not 'the run covered everything' --------------------------
    m = em.derive([unit("home"), unit("about")], ["home", "about", "pricing", "docs"], 0)
    check("unreached units listed explicitly", m["unreached"], ["pricing", "docs"])
    check("aborted flagged when units are unreached", m["aborted"], True)
    check("counts: expected from the expectation, not from what was reached",
          (m["counts"]["expected"], m["counts"]["reached"]), (4, 2))
    m2 = em.derive([unit("home")], ["home"], 0)
    check("a complete run is not flagged aborted", m2["aborted"], False)
    # A truncated line means the process died, so the run is aborted even with nothing expected.
    m3 = em.derive([unit("home")], [], 1)
    check("a truncated line alone marks the run aborted", m3["aborted"], True)
    check("no expectation file: expected falls back to reached", m3["counts"]["expected"], 1)

    # ---- resume: completed units, and blocked ones stay retryable ---------------------
    log2 = write_log([unit("home"), unit("about", status="Blocked", reason="route_timeout 90s")])
    units2, _ = em.read_results(log2)
    done = [u["unit"] for u in units2 if str(u.get("status", "")).lower() != em.BLOCKED]
    check("resume: completed unit is skippable", done, ["home"])
    _tick()
    if "about" in done:
        FAILURES.append(
            "resume: a Blocked unit was treated as completed -- a transient hang would become a "
            "permanent hole in the evidence"
        )

    # --fresh must empty the skip list, so a clean run re-does everything. Asserted through the
    # CLI because that is the only place resume is decided -- a caller with its own fresh path
    # would be a second rule to keep in step.
    import argparse as _a
    import contextlib, io

    _tick()
    with contextlib.redirect_stdout(io.StringIO()) as fresh_out, contextlib.redirect_stderr(io.StringIO()):
        rc_fresh = em.cmd_completed(_a.Namespace(results=str(log2), fresh=True))
    if rc_fresh != 0 or fresh_out.getvalue().strip():
        FAILURES.append(f"--fresh must emit an EMPTY skip list, got {fresh_out.getvalue()!r}")
    _tick()
    with contextlib.redirect_stdout(io.StringIO()) as resume_out, contextlib.redirect_stderr(io.StringIO()):
        em.cmd_completed(_a.Namespace(results=str(log2), fresh=False))
    if resume_out.getvalue().split() != ["home"]:
        FAILURES.append(f"resume must list completed units, got {resume_out.getvalue()!r}")

    # ---- the evidence contract ------------------------------------------------------
    check("conforming unit passes", em.validate_manifest({"units": [unit("home")]}), [])

    def problems(**kw) -> str:
        return " | ".join(em.validate_manifest({"units": [unit("home", **kw)]}))

    # Purpose decides capture scope. This is the 8050px-screenshot defect.
    _tick()
    if "must be clipped" not in problems(purpose="interaction", capture="full"):
        FAILURES.append("interaction evidence captured full-page was accepted")
    _tick()
    if "must be clipped" not in problems(purpose="a11y", capture="full"):
        FAILURES.append("a11y evidence captured full-page was accepted")
    # ...but a full-page capture is CORRECT for whole-page purposes. A rule that forbade it
    # everywhere would be switched off by the first legitimate visual-regression run.
    check("full-page is right for layout", em.validate_manifest(
        {"units": [unit("home", purpose="layout", capture="full")]}), [])
    check("full-page is right for visual-regression", em.validate_manifest(
        {"units": [unit("home", purpose="visual-regression", capture="full")]}), [])
    # Clipped is never wrong for a whole-page purpose -- only the reverse is a defect.
    check("clipped is allowed for layout too", em.validate_manifest(
        {"units": [unit("home", purpose="layout", capture="clipped")]}), [])

    _tick()
    if "not one of" not in problems(purpose="vibes"):
        FAILURES.append("an unknown purpose was accepted")
    _tick()
    if "no capture scope" not in problems(capture=""):
        FAILURES.append("a missing capture scope was accepted")

    # Naming must encode the axes, or the set is not self-describing.
    for bad_name in ("home.png", "Home--1280x800-light.png", "home--1280-light.png",
                     "home--1280x800.png", "home--1280x800-light.jpg"):
        _tick()
        if "does not match" not in problems(image=f"screenshots/{bad_name}"):
            FAILURES.append(f"malformed evidence name accepted: {bad_name}")
    for good_name in ("home--1280x800-light.png", "user-list--390x844-dark--hover.png"):
        _tick()
        if em.validate_manifest({"units": [unit("home", image=f"s/{good_name}")]}):
            FAILURES.append(f"valid evidence name rejected: {good_name}")

    # Validity recorded, per #106 -- 12 captures of 404 pages sat beside real evidence.
    _tick()
    bare = unit("home")
    del bare["valid"]
    if "validity not recorded" not in " | ".join(em.validate_manifest({"units": [bare]})):
        FAILURES.append("a capture with no recorded validity was accepted")
    _tick()
    if "marked invalid without a reason" not in problems(valid=False):
        FAILURES.append("invalid-without-reason was accepted")
    check("invalid WITH a reason is honest", em.validate_manifest(
        {"units": [unit("home", valid=False, reason="404 page, not the page under test")]}), [])
    _tick()
    if "without the assertion it supports" not in problems(assertion=""):
        FAILURES.append("valid evidence with no assertion was accepted")

    # Blocked units: honest only if they say why, and exempt from capture rules (no image).
    check("Blocked with a reason is complete", em.validate_manifest(
        {"units": [{"unit": "x", "route": "/x", "status": "Blocked", "purpose": "interaction",
                    "reason": "route_timeout 90s"}]}), [])
    _tick()
    blocked_no_reason = em.validate_manifest(
        {"units": [{"unit": "x", "route": "/x", "status": "Blocked", "purpose": "interaction"}]})
    if not any("Blocked without a reason" in p for p in blocked_no_reason):
        FAILURES.append("Blocked with no reason was accepted -- it becomes a way to record nothing")

    for field in ("unit", "route", "status", "purpose"):
        _tick()
        partial = unit("home")
        del partial[field]
        if not any(f"missing {field!r}" in p for p in em.validate_manifest({"units": [partial]})):
            FAILURES.append(f"a unit missing {field!r} was accepted")

    # ---- index.html: browsable, and validity VISIBLE -------------------------------
    manifest = em.derive(
        [unit("home"), unit("bad", valid=False, reason="404 page"),
         {"unit": "slow", "route": "/slow", "status": "Blocked", "purpose": "layout",
          "reason": "route_timeout 90s"}],
        ["home", "bad", "slow", "never"], 0)
    page = em.render_index(manifest)
    for expected in ("INVALID", "class=invalid", "BLOCKED", "route_timeout 90s",
                     "did not complete", "never"):
        _tick()
        if expected not in page:
            FAILURES.append(f"index.html omits {expected!r} — invalid/blocked/unreached must be visible")
    _tick()
    if "<script" in page.lower() or "http://" in page or "https://" in page:
        FAILURES.append("index.html must be dependency-free: no scripts, no remote assets")
    # Escaping: a route or reason is untrusted text; it must not break out into markup.
    _tick()
    evil = em.render_index({"units": [unit("x", route="/<script>alert(1)</script>")],
                            "counts": {}, "unreached": []})
    if "<script>alert(1)" in evil:
        FAILURES.append("index.html does not escape route text")

    # ---- retention: newest kept, referenced runs protected, pruning always printed ---
    root = _tmp()
    for name in ("2026-07-01-a", "2026-07-02-b", "2026-07-03-c", "2026-07-04-d", "2026-07-05-e"):
        (root / name).mkdir(parents=True)
        (root / name / "manifest.json").write_text("{}", encoding="utf-8")
    runs = [p for p in root.iterdir() if p.is_dir()]
    kept, dropped = em.prune(runs, keep=3, protected=set())
    check("retention: newest 3 kept",
          sorted(p.name for p in kept), ["2026-07-03-c", "2026-07-04-d", "2026-07-05-e"])
    check("retention: the rest pruned",
          sorted(p.name for p in dropped), ["2026-07-01-a", "2026-07-02-b"])
    kept2, dropped2 = em.prune(runs, keep=3, protected={"2026-07-01-a"})
    check("retention: a run referenced by an open defect survives",
          "2026-07-01-a" in {p.name for p in kept2}, True)
    check("retention: protection does not save the others",
          sorted(p.name for p in dropped2), ["2026-07-02-b"])
    check("retention: keep=0 with protection still keeps the protected run",
          sorted(p.name for p in em.prune(runs, keep=0, protected={"2026-07-02-b"})[0]),
          ["2026-07-02-b"])
    # Ordering is by NAME, not mtime: opening an index.html changes mtime and would silently
    # reshuffle what gets deleted.
    _tick()
    (root / "2026-07-01-a").touch()
    if {p.name for p in em.prune(runs, keep=1, protected=set())[0]} != {"2026-07-05-e"}:
        FAILURES.append("retention ordered by mtime — touching an old run changed what survives")

    # ---- end to end, including --dry-run deleting nothing --------------------------
    import argparse as _a

    work = _tmp()
    (work / "2026-07-09-run").mkdir(parents=True)
    log3 = work / "2026-07-09-run" / "results.jsonl"
    log3.write_text(json.dumps(unit("home")) + "\n", encoding="utf-8")
    expect = work / "2026-07-09-run" / "expected.txt"
    expect.write_text("home\npricing\n", encoding="utf-8")
    import contextlib, io

    _tick()
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        rc = em.cmd_derive(_a.Namespace(results=str(log3), expect=str(expect), out=None))
    if rc != 0:
        FAILURES.append("derive: an incomplete run is reported, not failed -- exit must be 0")
    written = json.loads((work / "2026-07-09-run" / "manifest.json").read_text(encoding="utf-8"))
    check("derive writes the manifest beside the log", written["unreached"], ["pricing"])

    _tick()
    with contextlib.redirect_stdout(io.StringIO()) as out:
        em.cmd_prune(_a.Namespace(runs=str(work), keep=0, protect=None, dry_run=True))
    if "prune 2026-07-09-run" not in out.getvalue():
        FAILURES.append("prune --dry-run does not report what it would delete")
    _tick()
    if not (work / "2026-07-09-run").is_dir():
        FAILURES.append("prune --dry-run DELETED a run")

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"evidence_manifest selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
