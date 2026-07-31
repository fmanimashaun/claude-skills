#!/usr/bin/env python3
"""Prove every doctor check fires on a broken machine -- and stays silent on a healthy one.

Run:  python3 scripts/maintainer_doctor.py --selftest   (or execute this file directly)

A setup doctor that cannot fail is worse than no doctor: it is consulted precisely when someone
does not yet know what "correct" looks like, so a false green is believed. Every check below is
therefore exercised against a REAL git fixture -- a bare remote plus a clone, with branches and
commits -- rather than a mocked one, because the bugs in this file's subject were all in how git
actually behaves (a collapsed untracked directory, a stale ref, an unborn HEAD).

THE INVARIANT THAT MATTERS MOST: `SKIP` must never be counted or rendered as `PASS`. That
conflation is the defect the doctor exists to prevent, and it is asserted directly here rather
than left to inspection.

Costs nothing: no network, stdlib + git only.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maintainer_doctor as md  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

# Captured before any fixture patches `md.REPO`, so the ignore-rule fixtures can seed themselves
# with the `.gitignore` we ACTUALLY ship. Testing a hand-written stand-in would prove the check
# works and say nothing about whether our own patterns do.
REAL_REPO = md.REPO

# The pre-#197 patterns, verbatim: directory-only, so they match neither a symlink (git mode
# 120000) nor a path that does not exist yet.
SLASHED_IGNORE = "everylayout/\ntailwind-ui/\nflowbite*/\nflowbite*.zip\n"


def _tick() -> None:
    global CHECKS
    CHECKS += 1


def _git(cwd: Path, *args: str) -> str:
    p = subprocess.run(("git",) + args, cwd=cwd, capture_output=True, text=True)
    return (p.stdout + p.stderr).strip()


def fixture(*, on_branch: str = "dev", stale_main: bool = False, dirty: bool = False,
            marketplace: bool = True, corpora: bool = False,
            direct_to_main: bool = False, gitignore: str | None = "real") -> Path:
    """A real repo with a real remote, shaped to trigger (or not) one specific check.

    `gitignore`: "real" copies the shipped `.gitignore` (so the ignore-rule check is exercised
    against the patterns we actually use), "slashed" reproduces the #197 bug, None omits the
    file, and any other string is written verbatim as the ignore file. It is written BEFORE the
    initial commit so the fixture's tree stays clean -- an uncommitted `.gitignore` would make
    every dirty-tree assertion below lie.
    """
    root = Path(tempfile.mkdtemp(prefix="doctor-fx-"))
    remote, work = root / "remote.git", root / "work"
    _git(root, "init", "--bare", "-b", "main", str(remote))
    _git(root, "clone", str(remote), str(work))
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")

    if marketplace:
        (work / ".claude-plugin").mkdir(parents=True, exist_ok=True)
        (work / ".claude-plugin" / "marketplace.json").write_text('{"metadata":{"version":"0.0.0"}}')
    if gitignore == "real":
        shutil.copyfile(REAL_REPO / ".gitignore", work / ".gitignore")
    elif gitignore == "slashed":
        (work / ".gitignore").write_text(SLASHED_IGNORE)
    elif gitignore is not None:
        (work / ".gitignore").write_text(gitignore)
    (work / "seed.txt").write_text("seed\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "-u", "origin", "main")

    # A SECOND commit on main, so `origin/main` can be genuinely ahead of a rewound local
    # `main`. The first version of this fixture set local main to `dev^` -- which in this repo
    # shape IS origin/main, so there was no staleness to find and the check looked broken when
    # the fixture was. Two commits is what makes the trap reproducible.
    (work / "release.txt").write_text("v0\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "release: v0")
    _git(work, "push", "origin", "main")

    _git(work, "checkout", "-b", "dev")
    (work / "dev.txt").write_text("dev\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "dev work")
    _git(work, "push", "-u", "origin", "dev")

    if direct_to_main:
        # A commit that exists only on main -- invisible to every future dev-based change.
        _git(work, "checkout", "main")
        (work / "sneaky.txt").write_text("only on main\n")
        _git(work, "add", "-A")
        _git(work, "commit", "-m", "feat: added straight to main")
        _git(work, "push", "origin", "main")
        _git(work, "checkout", "dev")

    if stale_main:
        # Rewind the LOCAL main ref one commit behind origin/main, leaving the remote untouched.
        # This is the real-world trap: `main` sits where it was when you last looked, releases
        # move it on the remote, and `git diff dev main` then reports phantom deletions.
        behind = _git(work, "rev-parse", "origin/main~1")
        _git(work, "update-ref", "refs/heads/main", behind)

    if corpora:
        # One subfolder holding all three, matching the layout `check_corpora` looks for (#197).
        for c in md.CORPORA:
            (work / md.CORPORA_DIR / c).mkdir(parents=True, exist_ok=True)

    if on_branch != "dev":
        _git(work, "checkout", on_branch)
    if dirty:
        (work / "app").mkdir(exist_ok=True)
        (work / "app" / "new_file.py").write_text("# uncommitted\n")

    _git(work, "fetch", "--all")
    return work


def diagnose(work: Path, *, fix: bool = False) -> md.Doctor:
    """Run only the git/corpora checks -- prerequisites and gates hit the real environment."""
    real = md.REPO
    md.REPO = work
    try:
        d = md.Doctor(fix=fix)
        if not d.check_is_marketplace_repo():
            return d
        d.check_branch()
        d.check_stale_main_ref()
        d.check_dev_current()
        d.check_no_direct_to_main()
        d.check_unshipped()
        d.check_corpora()
        d.check_corpora_ignored()
        return d
    finally:
        md.REPO = real


def find(d: md.Doctor, needle: str) -> md.Result | None:
    return next((r for r in d.results if needle.lower() in r.name.lower()), None)


def expect(label: str, d: md.Doctor, needle: str, status: str) -> md.Result | None:
    _tick()
    r = find(d, needle)
    if r is None:
        FAILURES.append(f"{label}: no check matching {needle!r}; got {[x.name for x in d.results]}")
        return None
    if r.status != status:
        FAILURES.append(f"{label}: {needle!r} was {r.status}, expected {status} ({r.detail})")
    return r


def run() -> int:
    # ---- healthy machine: nothing may FAIL ---------------------------------------------
    d = diagnose(fixture(corpora=True))
    _tick()
    fails = [r.name for r in d.results if r.status == md.FAIL]
    if fails:
        FAILURES.append(f"healthy fixture produced failures: {fails}")
    expect("healthy", d, "on `dev`", md.PASS)
    expect("healthy", d, "local `main` matches", md.PASS)
    expect("healthy", d, "corpora present", md.PASS)
    # Exercised against the `.gitignore` we actually ship, so this PASS is a statement about
    # our real patterns rather than about a stand-in written to satisfy it.
    expect("healthy", d, "corpora ignore rules", md.PASS)

    # ---- the #197 regression: directory-only patterns cannot match the prescribed layout --
    # The pre-#197 `.gitignore` verbatim. This is the negative test the original rule never had:
    # it was written, believed, and silently matched nothing for the layout in the docs.
    d = diagnose(fixture(corpora=True, gitignore="slashed"))
    r = expect("slashed ignore", d, "corpora ignore rules", md.FAIL)
    _tick()
    if r and "design-corpora" not in r.detail:
        FAILURES.append(
            "the slashed-ignore finding must name the unignored path, or it cannot be acted on; "
            f"detail={r.detail!r}"
        )
    _tick()
    if r and "slash" not in r.remedy.lower():
        FAILURES.append(
            "the remedy must say to drop the trailing slash — naming the defect without the fix "
            f"is what made #197 survive review. remedy={r.remedy!r}"
        )

    # ---- no .gitignore at all is a FAIL, not a silent skip ----------------------------
    # Fail CLOSED: with no ignore file the licensed corpora are one `git add -A` from the
    # history, which is the outcome the whole rule exists to prevent.
    expect("no ignore file", diagnose(fixture(corpora=True, gitignore=None)),
           "corpora ignore rules", md.FAIL)

    # ---- an over-broad pattern that swallows our own generated matrix ------------------
    # The other direction: a corpora pattern wide enough to hide `coverage.md` would silently
    # disable the drift guard, so near-misses are asserted, not assumed.
    d = diagnose(fixture(corpora=True, gitignore="/design-corpora\ncoverage.md\n"))
    r = expect("over-broad ignore", d, "corpora ignore rules", md.FAIL)
    _tick()
    if r and "coverage.md" not in r.detail:
        FAILURES.append(f"over-broad finding must name the swallowed path; detail={r.detail!r}")

    # ---- on main: the branch you must never work from ----------------------------------
    d = diagnose(fixture(on_branch="main", corpora=True))
    r = expect("on main", d, "on `main`", md.FAIL)
    _tick()
    if r and "install surface" not in r.detail:
        FAILURES.append("on-main finding does not explain WHY main is forbidden")

    # ---- editing directly on dev: the case that caught me while writing this ----------
    d = diagnose(fixture(dirty=True, corpora=True))
    r = expect("dirty dev", d, "editing directly on `dev`", md.FAIL)
    _tick()
    if r and "app/new_file.py" not in r.detail:
        FAILURES.append(
            "dirty-dev finding does not name the file. A NEW file in a NEW directory is the "
            f"case plain --porcelain collapses to '?? app/'. detail={r.detail!r}"
        )

    # ---- clean dev is a PASS, not a nag ----------------------------------------------
    expect("clean dev", diagnose(fixture(corpora=True)), "on `dev`, clean", md.PASS)

    # ---- stale local main ref, and --fix repairing it --------------------------------
    fx = fixture(stale_main=True, corpora=True)
    r = expect("stale main", diagnose(fx), "stale local `main` ref", md.FAIL)
    _tick()
    if r and "phantom" not in r.detail:
        FAILURES.append("stale-main finding does not say what breaks (the dev-vs-main diff)")

    fx = fixture(stale_main=True, corpora=True)
    d = diagnose(fx, fix=True)
    expect("stale main --fix", d, "local `main` matches", md.PASS)
    _tick()
    if not any("main" in f for f in d.fixed):
        FAILURES.append(f"--fix did not report repairing the ref; fixed={d.fixed}")
    _tick()
    if _git(fx, "rev-parse", "main") != _git(fx, "rev-parse", "origin/main"):
        FAILURES.append("--fix claimed success but the ref still differs")

    # ---- --fix must NOT be destructive: uncommitted work survives it -----------------
    fx = fixture(on_branch="main", dirty=True, corpora=True)
    diagnose(fx, fix=True)
    _tick()
    if not (fx / "app" / "new_file.py").exists():
        FAILURES.append("--fix destroyed uncommitted work — it must never reset or clean")

    # ---- a commit that exists only on main ------------------------------------------
    d = diagnose(fixture(direct_to_main=True, corpora=True))
    r = expect("direct to main", d, "direct-to-`main`", md.FAIL)
    _tick()
    if r and "unions" not in r.detail:
        FAILURES.append("direct-to-main finding omits why it matters (a merge unions)")

    # ---- corpora absent is SKIP, never FAIL and never PASS --------------------------
    d = diagnose(fixture(corpora=False))
    r = expect("no corpora", d, "corpora missing", md.SKIP)
    _tick()
    if r and "build_coverage" not in r.detail:
        FAILURES.append(
            "corpora finding does not say only build_coverage.py needs them — without that it "
            "reads as 'the repo is unusable', which is false"
        )
    _tick()
    if r and not r.remedy.startswith("git clone"):
        FAILURES.append("corpora finding gives no clone remedy")

    # ---- THE INVARIANT: skip is never counted as a pass -----------------------------
    _tick()
    d = diagnose(fixture(corpora=False))
    skips = sum(1 for r in d.results if r.status == md.SKIP)
    if skips == 0:
        FAILURES.append("expected at least one SKIP on a corpora-less fixture")

    # This asserted that NO check whose name contains "corpora" may PASS while the kits are
    # absent. That was right when the only such check was the presence one, and became too broad
    # in #197: `corpora ignore rules` reads the ignore PATTERNS, not the kits, so it must keep
    # reaching a real verdict on a machine that has never cloned them. Banning the substring
    # would have forced the new check to either lie or rename itself to dodge the rule. Both
    # halves are pinned separately instead, which is stronger than the blanket ban: the
    # exemption is not a hole a broken check could hide in.
    _tick()
    presence = find(d, "corpora present") or find(d, "corpora missing")
    if presence is None:
        FAILURES.append(f"no corpora presence check ran; got {[r.name for r in d.results]}")
    elif presence.status != md.SKIP:
        FAILURES.append(
            f"corpora presence reported {presence.status} while the corpora were absent — "
            "a check that did not run must never render as one that passed"
        )
    _tick()
    rules = find(d, "corpora ignore rules")
    if rules is None or rules.status != md.PASS:
        FAILURES.append(
            "the ignore-rule check must still reach a verdict with no corpora present — it reads "
            f"patterns, not kits; got {rules.status if rules else 'no such check'}"
        )
    _tick()
    if md.PASS == md.SKIP:
        FAILURES.append("PASS and SKIP are the same token — they must be distinguishable")

    # ---- not the marketplace repo: fatal, and says so ------------------------------
    d = diagnose(fixture(marketplace=False, corpora=True))
    expect("not marketplace", d, "not the marketplace repo", md.FAIL)
    _tick()
    if len(d.results) != 1:
        FAILURES.append(
            f"non-marketplace repo ran {len(d.results)} checks; it must stop at the "
            "precondition rather than reporting on a repo it does not understand"
        )

    # ---- every FAIL and SKIP must carry a remedy ----------------------------------
    _tick()
    for fx_kwargs in ({"on_branch": "main"}, {"dirty": True}, {"stale_main": True},
                      {"corpora": False}, {"direct_to_main": True}):
        for r in diagnose(fixture(**fx_kwargs)).results:
            if r.status in (md.FAIL, md.SKIP) and not r.remedy.strip():
                FAILURES.append(
                    f"{r.name!r} is {r.status} with no remedy — a fault without a fix is a "
                    "complaint, and the reader is the person who does not yet know what to do"
                )

    # ---- unshipped work is INFO, not a fault --------------------------------------
    expect("unshipped", diagnose(fixture(corpora=True)), "unshipped", md.INFO)

    # ---- the doctor must not MUTATE the repo it is diagnosing --------------------
    # check_dist_clean has to rebuild to know anything, and package_core.py writes straight
    # into dist/ with no output-dir flag. So it snapshots and restores. Asserted against the
    # REAL dist with a deliberately dirtied file: if the restore is dropped, the rebuild
    # silently overwrites uncommitted work, and the earlier version of this check did exactly
    # that — passing only because the packer happens to be byte-deterministic.
    real_dist = Path(__file__).resolve().parents[1] / "dist"
    skills = sorted(real_dist.glob("*.skill")) if real_dist.is_dir() else []
    if not skills:
        print("note: no dist/*.skill — skipped the no-mutation check", file=sys.stderr)
    else:
        _tick()
        victim = skills[0]
        original = victim.read_bytes()
        try:
            victim.write_bytes(original + b"\n# deliberately dirtied by the selftest\n")
            dirtied = victim.read_bytes()
            md.Doctor().check_dist_clean()
            if victim.read_bytes() != dirtied:
                FAILURES.append(
                    f"check_dist_clean overwrote uncommitted changes in {victim.name} — a "
                    "diagnostic must leave the working tree exactly as it found it"
                )
        finally:
            victim.write_bytes(original)

        _tick()
        before = {p.name: p.read_bytes() for p in sorted(real_dist.glob("*.skill"))}
        md.Doctor().check_dist_clean()
        after = {p.name: p.read_bytes() for p in sorted(real_dist.glob("*.skill"))}
        if before != after:
            changed = [k for k in before if before.get(k) != after.get(k)]
            FAILURES.append(f"check_dist_clean altered dist/ on a clean tree: {changed}")

    # ---- the gate list must point at files that exist ----------------------------
    _tick()
    missing = [c[1] for _, c in md.GATES if not (Path(__file__).resolve().parents[1] / c[1]).exists()]
    if missing:
        FAILURES.append(f"GATES references scripts that do not exist: {missing}")

    # ---- no selftest may be invisible to the sweep ----------------------------------
    # A gate the doctor never runs is a gate that does not exist for anyone relying on
    # `--gates`. This bit on #119: the new route_coverage selftest passed locally while the
    # doctor's own sweep silently omitted it. Discovering that by hand once is enough.
    _tick()
    repo = Path(__file__).resolve().parents[1]
    listed = {c[1] for _, c in md.GATES}
    on_disk = {
        p.relative_to(repo).as_posix()
        for p in repo.glob("scripts/*.py")
        if p.name.endswith("_selftest.py")
    } | {
        p.relative_to(repo).as_posix()
        for p in repo.glob("plugins/*/scripts/*.py")
        if p.name.endswith("_selftest.py")
    }
    # A `*_selftest.py` is normally driven through its sibling's `--selftest` flag, so the gate
    # list names the sibling. Map each selftest to the module it tests before comparing.
    missing = sorted(
        s for s in on_disk
        if s.replace("_selftest.py", ".py") not in listed and s not in listed
    )
    if missing:
        FAILURES.append(
            f"selftests no GATES entry runs: {missing} -- `--gates` would report a clean sweep "
            "having never executed them"
        )

    # ---- the corpora-gate exemption is keyed by name, so the names must be real -------
    # A stringly-keyed carve-out that stops matching is the failure mode: rename the gate and the
    # exemption quietly lapses. Cheap to pin, so pinned.
    # ---- GATE NAMES MUST BE UNIQUE -----------------------------------------------------
    # `coverage artifact selftest` was registered twice, so `--gates` ran it twice and reported an
    # inflated total — a sweep that overstates how much it covered. It went unnoticed because the
    # only thing reading these names was the set comprehension below, which collapses duplicates.
    # The name is also the key CORPORA_GATES matches on, so a duplicate makes that carve-out
    # ambiguous as well.
    _tick()
    _all = [name for name, _ in md.GATES]
    _dupes = sorted({n for n in _all if _all.count(n) > 1})
    if _dupes:
        FAILURES.append(
            f"GATES registers these names more than once: {_dupes} — the sweep runs them twice and "
            "reports a total larger than the number of distinct checks it performed"
        )

    _tick()
    gate_names = {name for name, _ in md.GATES}
    unknown = sorted(md.CORPORA_GATES - gate_names)
    if unknown:
        FAILURES.append(
            f"CORPORA_GATES names no such gate: {unknown} — the corpora-absent SKIP would never "
            f"apply. Known gates: {sorted(gate_names)}"
        )

    # ---- and the exemption must be NARROW: only corpora-dependent gates may skip -------
    # The near-miss that matters, pinned as an EXACT set rather than a substring heuristic. Both
    # failure directions are real and neither is hypothetical:
    #   too broad — a gate that runs perfectly well without the kits gets skipped, silently
    #     shrinking the sweep while the summary still reads healthy;
    #   too narrow — `coverage artifact drift` was MISSING, and a corpora-less machine was told to
    #     "fix the failures before doing maintenance work" about optional licensed files. Proved by
    #     pointing the corpora root at a nonexistent path: the gate returned 1.
    # An exact set means either direction has to be a deliberate edit here, with a reason.
    _tick()
    expected = {"coverage matrix drift", "coverage artifact drift"}
    if set(md.CORPORA_GATES) != expected:
        FAILURES.append(
            f"CORPORA_GATES is {sorted(md.CORPORA_GATES)}, expected {sorted(expected)} — exactly "
            "the two gates that rebuild an artifact embedding the upstream corpus totals. A "
            "selftest belongs in neither: it SKIPs those checks itself and still exits 0."
        )

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for f in FAILURES:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"maintainer_doctor selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
