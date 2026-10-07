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
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import maintainer_doctor as md  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "rails-flow" / "scripts"))
import fixture_git  # noqa: E402  (#1588: a fixture's git touches only its own temp repo)

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
    """Fixture git (#1588): in a repo through fixture_git, bound to it and refused if its init failed; anything else
    (`init --bare` and `clone` from the temp root) runs plain and commits nothing."""
    if (cwd / ".git").is_dir():
        p = fixture_git.run(cwd, *args, check=False)
    else:
        p = subprocess.run(("git",) + args, cwd=cwd, capture_output=True, text=True)
    return (p.stdout + p.stderr).strip()


def fixture(*, on_branch: str = "dev", stale_main: bool = False, dirty: bool = False,
            marketplace: bool = True, corpora: bool = False,
            direct_to_main: bool = False, gitignore: str | None = "real",
            promotion: str | None = None) -> Path:
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
    # The doctor reads the clone's CONFIGURED user to tell its own commits from a foreign one, so this is the code
    # under test's input, not a fixture identity; `_git` binds it to `work` through fixture_git (#1588).
    _git(work, "config", "user.email", "t@t")  # fixture-git: exempt (the configured user is what the doctor under test reads)
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

    if promotion:
        # A REAL promotion, done both ways, because the difference is invisible in the tree and
        # decisive in the history. Both leave `main` byte-identical to `dev`; only the merge leaves
        # a commit on `main` with a parent on `dev`, and only that makes the NEXT promotion mergeable.
        _git(work, "checkout", "main")
        if promotion == "squash":
            _git(work, "merge", "--squash", "dev")
            _git(work, "commit", "-m", "release: v1 (squashed — this is the trap)")
        else:
            _git(work, "merge", "--no-ff", "dev", "-m", "release: v1")
        _git(work, "push", "origin", "main")
        _git(work, "checkout", "dev")
        # dev moves on afterwards, which is the ordinary mid-cycle state and the one that made the
        # first version of this check useless: `dev` is not an ancestor of `main` in EITHER case, so
        # asking that question passes the squash. The fixture keeps this here on purpose.
        (work / "after.txt").write_text("more dev work\n")
        _git(work, "add", "-A")
        _git(work, "commit", "-m", "dev work after the release")
        _git(work, "push", "origin", "dev")

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
        d.check_promotion_was_a_merge()
        d.check_promotion_ruleset()
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


def ruleset_fixtures() -> None:
    """The doctor maps the shipped checker's exit code and nothing else; the fixtures drive all three."""
    import json, tempfile
    work = fixture()
    d = diagnose(work)
    expect("with a local origin the ruleset check is SKIP (n/a), never a pass", d, "merges only", md.SKIP)
    with tempfile.TemporaryDirectory() as td:
        good = Path(td) / "good.json"
        good.write_text(json.dumps([{"id": 1, "name": "main: promotions merge, never squash", "target": "branch", "enforcement": "active",
                                     "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
                                     "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
                                               {"type": "pull_request", "parameters": {"allowed_merge_methods": ["merge"]}}]}]), encoding="utf-8")
        empty = Path(td) / "none.json"; empty.write_text("[]", encoding="utf-8")
        saved = md.RULESET_ARGS
        try:
            md.RULESET_ARGS = ("--from", str(good))
            expect("a conforming ruleset is PASS", diagnose(work), "merges only", md.PASS)
            md.RULESET_ARGS = ("--from", str(empty))
            r = expect("no ruleset is FAIL with the finding and the --apply remedy", diagnose(work), "no merge-only ruleset", md.FAIL)
            if r is not None and ("--apply" not in r.remedy or "covers refs/heads/main" not in r.detail):
                FAILURES.append(f"ruleset FAIL lacks the finding or the remedy: {r.detail!r} / {r.remedy!r}")
        finally:
            md.RULESET_ARGS = saved


def repo_untouched_fixtures() -> None:
    """#1588: a gate that commits into the real repository turns the sweep red, by name.

    The fixture repo's configured user is `t@t`, so here `t@t` plays the maintainer (whose own sessions
    may commit during a sweep) and `fx@fixture` plays a fixture that escaped its temp repo."""
    work = fixture()
    saved_gates, real = md.GATES, md.REPO
    try:
        md.REPO = work
        scripts = work / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        plant = ("import subprocess, sys\n"
                 "subprocess.run(['git', '-c', f'user.email={sys.argv[1]}', '-c', 'user.name=x', 'commit', '-q',"
                 " '--allow-empty', '-m', 'm'], check=True)\n")
        (scripts / "_plant.py").write_text(plant, encoding="utf-8")
        (scripts / "_quiet.py").write_text("print('ok')\n", encoding="utf-8")
        cases = (("a gate that plants a FOREIGN commit mid-sweep turns the sweep red", "fx@fixture", md.FAIL),
                 ("CONTROL: a commit by the configured user (another session's work) is not flagged", "t@t", md.PASS))
        for label, author, want in cases:
            md.GATES = (("selftest plants", ("python3", "scripts/_plant.py", author)),)
            d = md.Doctor()
            d.check_gates()
            r = expect(label, d, "the sweep committed nothing into the real repository", want)
            _tick()
            if want == md.FAIL and r is not None and "fx@fixture" not in r.detail:
                FAILURES.append(f"#1588: the finding must name the escaped commit's author: {r.detail!r}")
        # #1594 review D1: a FETCH (and a pull into a local branch) during the sweep brings commits by other
        # authors from the remote. They are not a fixture escaping, so the detector must not flag them.
        other = work.parent / "other"
        # The planted commits above are local only; unpushed, they make `dev` diverge and `--ff-only` refuse.
        _git(work, "push", "-q", "origin", "dev")
        _git(work.parent, "clone", "-q", str(work.parent / "remote.git"), str(other))
        # On `dev`, the branch `work` tracks: a push from the clone's default branch (`main`) left the
        # pull a no-op, and the control passed without ever seeing a foreign commit (#1594 review). The
        # log assertion below keeps it from going vacuous again.
        _git(other, "checkout", "-q", "dev")
        _git(other, "-c", "user.email=someone@else", "-c", "user.name=s", "commit", "-q", "--allow-empty", "-m", "theirs")
        _git(other, "push", "-q", "origin", "dev")
        (scripts / "_fetch.py").write_text(
            "import subprocess\n"
            "subprocess.run(['git', 'fetch', '-q', 'origin'], check=True)\n"
            "subprocess.run(['git', 'merge', '-q', '--ff-only', '@{u}'], check=True)\n", encoding="utf-8")
        md.GATES = (("selftest fetches", ("python3", "scripts/_fetch.py")),)
        d = md.Doctor()
        d.check_gates()
        expect("CONTROL: a fetch and pull of other authors' commits during the sweep is not flagged (#1594 D1)", d,
               "the sweep committed nothing into the real repository", md.PASS)
        _tick()
        pulled = _git(work, "log", "--format=%ae %s", "-1", "dev")
        if pulled != "someone@else theirs":
            FAILURES.append(f"#1594 D1 control is vacuous: the pull did not bring the foreign commit onto dev ({pulled!r})")
        md.GATES = (("selftest quiet", ("python3", "scripts/_quiet.py")),)
        d = md.Doctor()
        d.check_gates()
        expect("CONTROL: a sweep that commits nothing passes the detector", d,
               "the sweep committed nothing into the real repository", md.PASS)
    finally:
        md.GATES, md.REPO = saved_gates, real


def timeout_fixtures() -> None:
    """A gate that is KILLED did not run -- so it is a skip, and a real failure is still a FAIL.

    #1097. `mutation coverage` spawns one subprocess per declared mutation, so it gets slower every
    time anyone makes this repository safer. It crossed 180s at 236 mutations (#129); the fix then
    was to raise its allowance to 900s. On 2026-09-21 it crossed 900s too -- 1000 mutations across
    93 guards on a laptop running several sessions -- and the sweep reported `FAIL`, which on that
    gate means "a guard stopped guarding". Run alone on the same commit it passed completely. An
    hour went into deciding which run to believe, and the doctor's own output had said `timed out`
    in plain words the whole time.

    An allowance can always be exceeded; the VERDICT is the thing that can be correct. Both
    directions are driven below, because "a timeout is a skip" is satisfied by a doctor that never
    fails anything at all.

    `check_gates()` is called directly rather than through `diagnose()`, which deliberately runs
    only the git and corpora checks -- the gates hit the real environment, and these two must not.
    """
    work = fixture()
    saved_gates, saved_slow, real = md.GATES, md.SLOW_GATES, md.REPO
    try:
        md.REPO = work
        scripts = work / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        (scripts / "_slow.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        (scripts / "_hangs.py").write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        (scripts / "_fails.py").write_text(
            "import sys\nprint('a guard survived')\nsys.exit(1)\n", encoding="utf-8")
        # mutation_check's two closing lines: the measurement, then the heaviest guards (#1497).
        (scripts / "_slow_ok.py").write_text(
            "print('mutation check: 9 mutation(s) across 2 guard(s), all caught (jobs=3, 7s)')\n"
            "print('heaviest guards (seconds of work, all jobs): a 5s, b 2s')\n", encoding="utf-8")
        md.GATES = (("selftest slow", ("python3", "scripts/_slow.py")),
                    ("selftest fails", ("python3", "scripts/_fails.py")),
                    ("selftest slow ok", ("python3", "scripts/_slow_ok.py")))
        md.SLOW_GATES = {"selftest slow": 1, "selftest slow ok": 60}

        d = md.Doctor()
        d.check_gates()

        r = expect("a gate that times out is SKIP, never FAIL", d, "selftest slow", md.SKIP)
        _tick()
        if r is not None and "did NOT run" not in r.detail:
            FAILURES.append(
                f"the timeout skip must say the check did not run, or a reader takes it for a "
                f"pass: {r.detail!r}")
        _tick()
        if r is not None and "timed out after 1s" not in r.detail:
            FAILURES.append(
                f"the timeout skip must name the allowance it exceeded, or nobody can tell "
                f"whether to raise it or fix the gate: {r.detail!r}")
        # THE NEGATIVE CONTROL, on the same code path. Without it, "timeouts are skips" is
        # satisfied by a doctor that reports everything as a skip -- which would hide the one
        # verdict that matters most on this gate.
        expect("a gate that RUNS and fails is still FAIL", d, "selftest fails", md.FAIL)
        # Review of #1525: SLOW_GATES' note says to re-set the budget from `jobs=N, Xs` on this ok
        # line, and the doctor kept the LAST line -- which became `heaviest guards`, without it.
        ok = expect("a slow gate that passes is ok", d, "selftest slow ok", md.PASS)
        _tick()
        if ok is not None and "(jobs=3, 7s)" not in ok.detail:
            FAILURES.append(f"a slow gate's ok line must carry its `(jobs=N, Xs)` measurement, which "
                            f"SLOW_GATES is re-set from; got {ok.detail!r}")
        # ...and the summary must not tell anyone to fix a check that never ran.
        _tick()
        if any(x.status == md.FAIL and "slow" in x.name for x in d.results):
            FAILURES.append("a timed-out gate still counts as a failure in the summary")
        # #1444: the SAME timeout under --require-slow is FAIL. A push run that could not run the
        # slow gate must not read green. Its control is the default doctor above, which still skips.
        strict = md.Doctor(require_slow=True)
        strict.check_gates()
        expect("under --require-slow, a slow gate that times out is FAIL", strict, "selftest slow", md.FAIL)
        expect("...and a real failure is still FAIL there", strict, "selftest fails", md.FAIL)
        # #1635: an ORDINARY gate that hangs is FAIL, named, under either flag. The pin from #1457's review said
        # SKIP here, so a hung gate went green; its direction is now reversed, and the two controls are: a SLOW
        # gate still skips off CI (above), and a gate that merely FAILS keeps its own verdict.
        saved_timeout = md.DEFAULT_TIMEOUT
        (scripts / "_hang_kids.py").write_text(
            "import os, subprocess, sys, time\n"
            "a = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
            "b = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], start_new_session=True)\n"
            "open(sys.argv[1], 'w').write(f'{a.pid} {b.pid}')\n"
            "print('gate hung-with-children started', flush=True)\n"
            "time.sleep(120)\n", encoding="utf-8")
        import signal as _sig
        import time as _tm
        kids_file = work / "kids.pids"
        md.GATES = (("selftest hangs", ("python3", "scripts/_hang_kids.py", str(kids_file))),)
        md.SLOW_GATES = {}
        try:
            for label, flags in (("default", {}), ("--require-slow", {"require_slow": True})):
                for budget in (2, 5, 10):          # longer only while the gate never wrote its pids: no verdict yet
                    md.DEFAULT_TIMEOUT = budget
                    if kids_file.exists():
                        kids_file.unlink()
                    began = _tm.monotonic()
                    hang = md.Doctor(**flags)
                    hang.check_gates()
                    took = _tm.monotonic() - began
                    if kids_file.exists() and kids_file.read_text().strip():
                        break
                hr = expect(f"{label}: an ordinary gate that times out is FAIL, named", hang, "selftest hangs", md.FAIL)
                _tick()
                if hr is not None and ("HUNG" not in hr.detail or "process group was killed" not in hr.detail):
                    FAILURES.append(f"{label}: the hung-gate FAIL must say HUNG and that its group was killed: {hr.detail!r}")
                _tick()
                if took > budget + 19:
                    FAILURES.append(f"{label}: a hung gate must end its step at its budget ({budget}s), took {took:.0f}s")
                pids = [int(x) for x in kids_file.read_text().split()] if kids_file.exists() and kids_file.read_text().strip() else []
                _tick()
                if len(pids) != 2:
                    FAILURES.append(f"{label}: the hung gate never started its two children (runner too loaded?): {pids}")
                for pid in pids:
                    _tm.sleep(0.2)
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        continue
                    os.kill(pid, _sig.SIGKILL)
                    FAILURES.append(f"{label}: a child of a hung gate (pid {pid}) outlived the doctor's kill")
        finally:
            md.DEFAULT_TIMEOUT = saved_timeout
        md.GATES = (("selftest hangs", ("python3", "scripts/_hangs.py")),)
        md.SLOW_GATES = {"selftest hangs": 1}
        md.DEFAULT_TIMEOUT = 1
        try:
            slow_hang = md.Doctor()
            slow_hang.check_gates()
        finally:
            md.DEFAULT_TIMEOUT = saved_timeout
        expect("CONTROL: a SLOW gate that times out off CI is still SKIP", slow_hang, "selftest hangs", md.SKIP)
        # #1599: `--ratchet` reaches `mutation coverage` ONLY under --require-slow, and no other gate. A stub fails when it
        # is passed the flag, so each direction is read off a verdict: a ratchet on every local run reads a busy laptop as
        # growth; one on no run enforces nothing; one on every gate hands an unknown flag to scripts that refuse it.
        (scripts / "_ratchet_probe.py").write_text(
            "import sys\nprint('ratcheted' if '--ratchet' in sys.argv else 'plain')\n"
            "sys.exit(1 if '--ratchet' in sys.argv else 0)\n", encoding="utf-8")
        md.GATES = (("mutation coverage", ("python3", "scripts/_ratchet_probe.py")),
                    ("selftest other", ("python3", "scripts/_ratchet_probe.py")))
        md.SLOW_GATES = {"mutation coverage": 60}
        on, off = md.Doctor(require_slow=True), md.Doctor()
        on.check_gates()
        off.check_gates()
        expect("under --require-slow, `mutation coverage` is run with --ratchet (the probe fails on it)", on,
               "mutation coverage", md.FAIL)
        expect("without --require-slow, `mutation coverage` is run without --ratchet", off, "mutation coverage", md.PASS)
        expect("under --require-slow, no OTHER gate is handed --ratchet", on, "selftest other", md.PASS)
    finally:
        md.GATES, md.SLOW_GATES, md.REPO = saved_gates, saved_slow, real


def run() -> int:
    md.restore_sigint()   # #1635: a backgrounded run inherits SIGINT ignored; the Ctrl-C fixtures below need it
    timeout_fixtures()
    repo_untouched_fixtures()
    ruleset_fixtures()
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

    # ---- a SQUASHED promotion, which is what broke v1.84.0 ------------------------------
    # v1.83.0 was squash-merged into `main`. A squash keeps the CONTENT and drops the ANCESTRY, so
    # main's tip had one parent, the merge base fell back two releases, and the next promotion hit
    # six conflicts on files nobody had edited twice. Nothing asserted it, because CLAUDE.md's
    # "a promotion is a merge commit" was prose.
    d = diagnose(fixture(promotion="squash"))
    r = expect("squashed promotion", d, "last promotion", md.FAIL)
    _tick()
    if r and "squash" not in (r.detail + r.remedy).lower():
        FAILURES.append(
            "the squashed-promotion finding must name the cause, or the remedy reads as generic "
            f"merge advice; detail={r.detail!r}"
        )
    _tick()
    if r and "--merge" not in r.remedy:
        FAILURES.append(
            "the remedy must name `--merge` explicitly. `gh pr merge` defaults are the whole trap: "
            f"naming the defect without the flag is how it recurs. remedy={r.remedy!r}"
        )

    # ---- ...and the SAME fixture merged properly must stay SILENT ------------------------
    # The negative half. Both shapes leave `main` byte-identical to `dev` and both leave `dev` a
    # non-ancestor of `main` once dev moves on, so a check that cannot tell them apart would either
    # pass both (useless) or fail both (switched off within a week).
    expect("merged promotion", diagnose(fixture(promotion="merge")), "last promotion", md.PASS)
    # A repo that has never promoted must not be accused of squashing one.
    expect("never promoted", diagnose(fixture()), "last promotion", md.PASS)

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

    # ---- every PART of a split harness is a gate (#1581, review of #1596) ----------------------------
    # check_hook_gates.py runs as PARTS (`--part a|b`) because one run was past a gate's 180 s. Its own selftest proves
    # every fixture group is in exactly one part; THIS proves every part is a gate. A part with no GATES entry never
    # runs in the doctor: the reviewer deleted the `hook gates (release)` entry from an export, and this selftest and
    # lint_self_consistency both stayed green.
    _tick()
    import importlib.util
    _root = Path(__file__).resolve().parents[1]
    _spec = importlib.util.spec_from_file_location("check_hook_gates", _root / "plugins/rails-flow/scripts/check_hook_gates.py")
    _chg = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_chg)
    _declared = {c[c.index("--part") + 1] for _, c in md.GATES
                 if any(a.endswith("check_hook_gates.py") for a in c) and "--part" in c and c.index("--part") + 1 < len(c)}
    if _declared != set(_chg.PARTS):
        FAILURES.append(f"a PART of check_hook_gates.py has no gate in GATES (or a gate names a part that does not exist): "
                        f"parts {sorted(_chg.PARTS)}, gates run {sorted(_declared)}")

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
    # PR_SKIPPED_GATES (#866): exactly the one gate that costs 92 % of the sweep. Every member must be a
    # real gate, and the set must not grow without an edit here -- a "fast" mode that quietly absorbs
    # gates is how it becomes the only mode.
    _tick()
    if set(md.PR_SKIPPED_GATES) != {"mutation coverage"}:
        FAILURES.append(f"PR_SKIPPED_GATES is {sorted(md.PR_SKIPPED_GATES)}, expected ['mutation coverage'] -- "
                        "widening it needs a reason recorded here")
    _tick()
    if md.PR_SKIPPED_GATES - gate_names:
        FAILURES.append(f"PR_SKIPPED_GATES names no such gate: {sorted(md.PR_SKIPPED_GATES - gate_names)}")
    _tick()
    if md.RATCHETED_GATES != {"mutation coverage"} or not (md.RATCHETED_GATES <= gate_names):
        FAILURES.append(f"RATCHETED_GATES is {sorted(md.RATCHETED_GATES)}; expected exactly ['mutation coverage'], a real gate")
    _tick()
    if "mutation cost record" not in gate_names or "mutation cost record" in md.PR_SKIPPED_GATES:
        FAILURES.append("the cheap `--check-record` gate must be a gate AND must run on pull requests (not in PR_SKIPPED_GATES)")
    _tick()
    d_fast = md.Doctor()
    d_fast.check_gates(fast=True) if False else None  # the full sweep is minutes; assert the SKIP shape on the record instead
    r = md.Result(md.SKIP, "gate: mutation coverage", "not run in --fast mode — it runs on every push to dev and at promotion, not per PR")
    if r.status != md.SKIP or "--fast" not in r.detail:
        FAILURES.append("a --fast skip must render as SKIP naming the mode, never as a pass or an omission")

    _tick()
    expected = {"coverage matrix drift"}
    if set(md.CORPORA_GATES) != expected:
        FAILURES.append(
            f"CORPORA_GATES is {sorted(md.CORPORA_GATES)}, expected {sorted(expected)} — only "
            "`build_coverage.py --check` genuinely enumerates the kits. `coverage artifact drift` "
            "was in here and was removed: exempting it stopped the check failing on the machine "
            "missing the corpora but not that machine committing a stripped page, which then broke "
            "the gate for everyone who had them. The page reads its upstream counts from the "
            "committed coverage.md Totals now. Fix the input, do not widen the carve-out. A "
            "selftest never belongs here: it SKIPs its own corpora fixtures and still exits 0."
        )

    # ---- the slow-gate allowance is name-keyed too, so the names must be real -----------
    # Same failure mode as CORPORA_GATES: rename the gate and the allowance quietly lapses, after
    # which `mutation coverage` starts reporting a TIMEOUT as a failure and the sweep tells a
    # maintainer to fix a checker that was working.
    _tick()
    # #1486 / review of PR #1491: a hung guard must be reported by the harness, naming it, before
    # the doctor's gate-wide timeout kills the run with a message that names no guard.
    sys.path.insert(0, str(md.REPO / "scripts"))
    import mutation_check as mc
    _tick()
    # `.get`, never `[...]`: a mutation renames this key to prove the no-such-gate check below
    # fires, and a KeyError here crashed the selftest before that check ran (dispatch 36629992150).
    total = md.SLOW_GATES.get("mutation coverage")
    if total is not None and not (mc.BASELINE_TIMEOUT + mc.MUTATION_CAP < total):
        FAILURES.append(f"mutation_check's baseline cap ({mc.BASELINE_TIMEOUT}s) plus its per-mutation cap "
                        f"({mc.MUTATION_CAP:.0f}s) must stay under the gate's total ({total}s), or a hung "
                        f"guard is killed by the doctor unnamed")
    unknown = sorted(set(md.SLOW_GATES) - {name for name, _ in md.GATES})
    if unknown:
        FAILURES.append(
            f"SLOW_GATES names no such gate: {unknown} — the longer timeout would never apply. "
            f"Known gates: {sorted(name for name, _ in md.GATES)}"
        )

    # And it must stay NARROW, pinned exactly, for the reason the default exists at all: a gate
    # given ten minutes is a gate that hangs for ten minutes before anyone hears about it. Only a
    # check whose cost grows with the number of checks belongs here.
    _tick()
    # #1635: the two hook-gate parts that run whole hook fixture groups took 190 to 203 s at the maintainer's machine load, past the
    # 180 s default, and are measured in SLOW_GATES' comment. Exactly these four; a fourth needs its own measurement.
    expected_slow = {"mutation coverage", "hook gates", "hook gates (release)", "hook gates (worktree)"}
    if set(md.SLOW_GATES) != expected_slow:
        FAILURES.append(
            f"SLOW_GATES is {sorted(md.SLOW_GATES)}, expected {sorted(expected_slow)} — only "
            "`mutation_check.py` spawns one subprocess per declared mutation (and two hook-gate parts run whole fixture groups: #1635) and therefore gets "
            "slower every time the repo gets safer. Everything else reads the tree once; if one "
            "of those is near the limit, that is a defect in the check, not a budget to raise."
        )

    # THE GATE TALLY MUST EXCLUDE PRECONDITIONS. `check_is_marketplace_repo` is a PASS in the same
    # results list as every gate, so the headline total has always been gates + 1 -- and three wrong
    # gate counts reached shipped text before anyone noticed. Assert the split directly: the
    # precondition is present, it is a PASS, and it is NOT counted as a gate.
    _tick()
    d = md.Doctor()
    d.add(md.PASS, "this is the claude-skills marketplace repo")
    d.add(md.PASS, "gate: one")
    d.add(md.SKIP, "gate: two")
    d.add(md.INFO, "some diagnostic")
    gates = d.gate_results()
    if len(gates) != 2:
        FAILURES.append(
            f"the gate tally counted {len(gates)} of 2 gates -- a precondition or a diagnostic is "
            f"being counted as a gate, which is how '83 (was 80)' shipped against 82 and 79")
    _tick()
    if any(r.name == "this is the claude-skills marketplace repo" for r in d.gate_results()):
        FAILURES.append("the repo-identity precondition is counted as a gate")
    _tick()
    if len(d.results) != 4 or sum(1 for r in d.results if r.status == md.PASS) != 2:
        FAILURES.append(
            "the headline total no longer counts every result -- it must stay a count of ALL "
            "checks, with the gate count reported separately, or a reader loses the distinction "
            "between a gate and a precondition entirely")

    # A shorter-than-default "allowance" would be a tightening wearing the name of an exemption.
    _tick()
    stingy = sorted(n for n, secs in md.SLOW_GATES.items() if secs <= md.DEFAULT_TIMEOUT)
    if stingy:
        FAILURES.append(
            f"SLOW_GATES entries at or under the {md.DEFAULT_TIMEOUT}s default: {stingy} — that "
            "silently TIGHTENS a gate through a table whose whole purpose is to loosen one"
        )

    # ---- A FAILING GATE'S FINDINGS, not just their count (#820) -------------------------------
    # The doctor kept `out.splitlines()[-1]`, and most of our gates end with a `N finding(s)` --
    # so what survived was reliably the count. On a runner the doctor is the ONLY thing that runs
    # the gate, so the findings were then printed nowhere at all.
    real = (
        "scanned 95 python module(s); 1 json settings file(s); 16 declared component(s)\n"
        "\n"
        "[changelog-bullet-unplaceable] CHANGELOG.md:2373 -- names no file that exists.\n"
        "\n"
        "1 finding(s)."
    )
    summary, findings = md.gate_output(real, 1)
    _tick()
    if summary != "1 finding(s).":
        FAILURES.append(f"the summary line is no longer the gate's last line: {summary!r}")
    _tick()
    if not any("changelog-bullet-unplaceable" in f for f in findings):
        FAILURES.append(
            f"a failing gate's FINDING is dropped, leaving only its count: {findings!r}")

    # Anchored at the BOTTOM, opposite to project_gates.summarise: our gates put their preamble
    # first and their report last, so the last lines are the ones worth keeping.
    long_out = "\n".join(f"noise {i}" for i in range(30))
    long_out += "\n" + "\n".join(f"[rule] finding {i}" for i in range(30)) + "\n30 finding(s)."
    summary, findings = md.gate_output(long_out, 1)
    _tick()
    if not findings or "noise 0" in "\n".join(findings):
        FAILURES.append(
            "the cap keeps the EARLIEST lines, which for our gates is the stats preamble -- the "
            f"findings sit just above the footer and are what must survive: {findings[:2]!r}")
    _tick()
    if not findings or "[rule] finding 29" not in findings[-1]:
        FAILURES.append(f"the last finding before the footer is dropped: {findings[-1:]!r}")
    _tick()
    if not findings or "dropped" not in findings[0]:
        FAILURES.append(
            "the cap truncates SILENTLY -- a reader cannot tell the report was cut, which is this "
            f"same defect one step along: {findings[:1]!r}")
    _tick()
    if len(findings) > md.MAX_GATE_FINDING_LINES + 1:
        FAILURES.append(f"the cap does not bound the output: {len(findings)} line(s)")
    _tick()
    if md.gate_output("", 2) != ("exit 2", ()):
        FAILURES.append(
            f"a gate that failed with NO output reports nothing at all: {md.gate_output('', 2)!r}")

    # THE CONSUMER, driven directly. Everything above proves `gate_output` carries the lines; none
    # of it proves `report` PRINTS them, and emptying that loop survives every fixture that only
    # calls the helper. Proving the helper is not proving the caller (#812, and again here).
    import contextlib
    import io
    d = md.Doctor()
    d.add(md.FAIL, "gate: whatever", "1 finding(s).", "python3 scripts/x.py",
          ("[rule] the actual problem",))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        d.report()
    out = buf.getvalue()
    _tick()
    if "the actual problem" not in out:
        FAILURES.append(f"report() prints the count but not the findings: {out!r}")
    _tick()
    if "the actual problem" in out and "python3 scripts/x.py" in out and \
            out.index("the actual problem") > out.index("python3 scripts/x.py"):
        FAILURES.append(
            "the findings print AFTER the remedy -- what is wrong comes before how to re-run it")

    # #1510: every gate subprocess -- and every selftest a gate runs -- starts no detached git
    # maintenance. Through Doctor.run, which launches the gates, not the helper alone.
    _tick()
    # Strip an inherited hermetic env first (a mutation guard's runner sets it), so only run() can supply it.
    inherited = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("GIT_CONFIG_")}
    try:
        rc, out = md.Doctor().run(sys.executable, "-c",
                              "import os, subprocess\n"
                              "print(subprocess.run(['git', 'config', '--get', 'maintenance.auto'],\n"
                              "                     capture_output=True, text=True).stdout.strip(),\n"
                              "      subprocess.run(['git', 'config', '--get', 'gc.auto'],\n"
                              "                     capture_output=True, text=True).stdout.strip())")
    finally:
        os.environ.update(inherited)
    if rc != 0 or out.split()[-2:] != ["false", "0"]:
        FAILURES.append(f"#1510: a gate's git must see maintenance.auto=false and gc.auto=0, got rc={rc} {out!r}")

    # #1635: --record-proof records only a COMPLETE sweep, so it is refused without --require-slow, with --fast, or
    # without --gates-only (a fast or partial run vouching for a release is exactly the failure it exists to stop).
    import contextlib
    import io
    for args in (["--record-proof"], ["--gates-only", "--record-proof"],
                 ["--gates-only", "--require-slow", "--fast", "--record-proof"]):
        _tick()
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                md.main(args)
            FAILURES.append(f"#1635: --record-proof must refuse {args}")
        except SystemExit as e:
            if e.code != 2:
                FAILURES.append(f"#1635: --record-proof with {args} must exit 2 (usage), got {e.code}")
        except Exception as e:          # past the refusal it goes on to run things: that is the failure, not a crash of the selftest
            FAILURES.append(f"#1635: --record-proof must refuse {args}, but it went on and raised {type(e).__name__}")

    # #1635: a doctor started in the BACKGROUND inherits SIGINT as ignored and never sees the Ctrl-C its own selftests send.
    # restore_sigint() resets it, only when it was ignored. Control: without the call the child still ignores it.
    import signal as _sg
    probe = ("import sys, signal; sys.path.insert(0, %r); import maintainer_doctor as md\n"
             "before = signal.getsignal(signal.SIGINT) == signal.SIG_IGN\n"
             "did = md.restore_sigint()\n"
             "print(before, did, signal.getsignal(signal.SIGINT) is signal.default_int_handler)\n" % str(Path(md.__file__).resolve().parent))

    def child(env_ignore: bool) -> str:
        return subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, timeout=60,
                              preexec_fn=(lambda: _sg.signal(_sg.SIGINT, _sg.SIG_IGN)) if env_ignore else None).stdout.strip()

    _tick()
    if child(True) != "True True True":
        FAILURES.append(f"#1635: restore_sigint must reset an inherited-ignored SIGINT to the default handler, got {child(True)!r}")
    _tick()
    via_main = ("import sys, signal; sys.path.insert(0, %r); import maintainer_doctor as md\n"
                "try:\n    md.main(['--record-proof'])\nexcept SystemExit:\n    pass\n"
                "print(signal.getsignal(signal.SIGINT) is signal.default_int_handler)\n" % str(Path(md.__file__).resolve().parent))
    got = subprocess.run([sys.executable, "-c", via_main], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=60,
                         preexec_fn=lambda: _sg.signal(_sg.SIGINT, _sg.SIG_IGN)).stdout.strip()
    if got != "True":
        FAILURES.append(f"#1635: main() must call restore_sigint() first (a backgrounded doctor's Ctrl-C selftests need it), got {got!r}")
    _tick()
    if child(False) != "False False True":
        FAILURES.append(f"#1635: restore_sigint must leave a normal SIGINT alone and report False, got {child(False)!r}")

    # #1459: a gate that times out takes its WHOLE process group with it. The gate starts a grandchild
    # that would outlive a plain kill, prints a line, then hangs; Doctor.run must come back as a
    # timeout (124, read as SKIP -- never a pass) carrying that line, and the grandchild must be gone.
    # CONTROL: a plain kill of the direct child -- what subprocess.run does on a timeout -- leaves it running.
    #
    # #1556: the gate learns nothing by being killed before it has started, and on a loaded runner a
    # one-second timeout can land before the gate has written its record -- or halfway through
    # writing it, which read as `int('')` and turned a full mutation-coverage run red. So the record
    # is written atomically (pid_record.write) AFTER the line is printed, the timed-out run is
    # retried with a longer timeout only while the gate never got that far, and the control waits
    # for the record before it kills, instead of racing a timeout.
    import signal as _signal
    import time as _time
    import pid_record
    with tempfile.TemporaryDirectory() as td:
        def gate(record: Path) -> str:
            return (pid_record.import_line(pid_record.HERE) +
                    "import subprocess, sys, time\n"
                    "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                    "print('gate-1459 started its grandchild', flush=True)\n"
                    f"pid_record.write({str(record)!r}, g.pid)\n"
                    "time.sleep(120)\n")

        def alive(pid: int) -> bool:
            for _ in range(20):           # a killed process can take a moment to be reaped
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    return False
                _time.sleep(0.1)
            return True

        _tick()
        pidfile = Path(td) / "grandchild.pid"
        for timeout in (1, 2, 4, 8):      # longer only while the gate never started: that is no verdict
            started = _time.monotonic()
            rc, out = md.Doctor().run(sys.executable, "-c", gate(pidfile), timeout=timeout)
            took = _time.monotonic() - started
            recorded_pids = pid_record.wait(pidfile, timeout=0)
            if recorded_pids:
                break
        if not recorded_pids:
            FAILURES.append(f"#1459: the timed-out gate never started its grandchild, even with {timeout}s "
                            f"(rc={rc}) -- the runner is too loaded to judge the group kill: {out!r}")
        elif rc != 124 or "gate-1459 started its grandchild" not in out or took > timeout + 19:
            FAILURES.append(f"#1459: a timed-out gate must return 124 promptly with what it printed, "
                            f"got rc={rc} after {took:.0f}s: {out!r}")
        _tick()
        if recorded_pids and alive(recorded_pids[0]):
            os.kill(recorded_pids[0], _signal.SIGKILL)
            FAILURES.append("#1459: a timed-out gate left its grandchild running -- the process group was not killed")
        _tick()
        # No pipes: the control only needs to show the grandchild survives a kill of its parent.
        control_file = Path(td) / "control.pid"
        plain = subprocess.Popen([sys.executable, "-c", gate(control_file)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        control_pids = pid_record.wait(control_file, timeout=60)
        plain.kill()                      # exactly what subprocess.run(timeout=...) does on expiry
        plain.wait()
        control_alive = False
        if control_pids:
            try:                  # one look: alive is the expected answer, so there is nothing to wait for
                os.kill(control_pids[0], 0)
                control_alive = True
                os.kill(control_pids[0], _signal.SIGKILL)
            except ProcessLookupError:
                pass
        if not control_pids:
            FAILURES.append("#1459 CONTROL: the control gate wrote no record within 60s -- it never started")
        elif not control_alive:
            FAILURES.append("#1459 CONTROL: a plain kill of the gate should leave the grandchild "
                            "running, or the check above proves nothing")

    # Review of #1525, end to end through the doctor. (1) A gate whose OWN children go through
    # proc_group.run -- mutation coverage's pool -- each in a session the gate's group kill never
    # reached; one also starts a grandchild in a session of its own, as check_hook_gates' hooks do.
    # (2) Ctrl-C while a gate runs: the gate is in a session of its own and never sees the
    # terminal's SIGINT, so the doctor must kill it on the way out (review: 2 survivors, 0 on dev).
    scripts_dir = str(Path(md.__file__).resolve().parent)
    inner = (pid_record.import_line(pid_record.HERE) +
             "import os, subprocess, sys, time\n"
             "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], start_new_session=True)\n"
             "pid_record.write(sys.argv[1], os.getpid(), g.pid)\n"
             "time.sleep(120)\n")

    def recorded(*files: Path) -> list[int]:
        return [pid for f in files for pid in pid_record.wait(f)]

    def survivors(pids: list[int]) -> list[int]:
        left = [p for p in pids if alive(p)]
        for p in left:
            try:
                os.kill(p, _signal.SIGKILL)
            except ProcessLookupError:
                pass
        return left

    with tempfile.TemporaryDirectory() as td:
        nested = ("import sys\n"
                  f"sys.path.insert(0, {scripts_dir!r})\n"
                  "import proc_group\n"
                  "from concurrent.futures import ThreadPoolExecutor\n"
                  f"inner = {inner!r}\n"
                  "def one(i):\n"
                  f"    proc_group.run([sys.executable, '-c', inner, {td!r} + f'/m{{i}}.pids'], timeout=300)\n"
                  "with ThreadPoolExecutor(2) as p:\n"
                  "    list(p.map(one, range(2)))\n")
        _tick()
        rc, out = md.Doctor().run(sys.executable, "-c", nested, timeout=6)
        pids = recorded(Path(td) / "m0.pids", Path(td) / "m1.pids")
        left = survivors(pids)
        if rc != 124 or len(pids) != 4 or left:
            FAILURES.append(f"#1459: a timed-out gate left a nested child running (rc={rc}; recorded "
                            f"{len(pids)} of 4 pids; survivors {left})")

        pidfile = Path(td) / "sigint.pids"
        driver = Path(td) / "driver.py"
        driver.write_text("import sys\n"
                          f"sys.path.insert(0, {scripts_dir!r})\n"
                          "import maintainer_doctor as md\n"
                          f"md.Doctor().run(sys.executable, '-c', {inner!r}, {str(pidfile)!r}, timeout=300)\n",
                          encoding="utf-8")
        _tick()
        d = subprocess.Popen([sys.executable, str(driver)], start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pids = recorded(pidfile)
        os.kill(d.pid, _signal.SIGINT)
        try:
            d.wait(timeout=20)
            exited = True
        except subprocess.TimeoutExpired:
            exited = False
            d.kill()
            d.wait()
        left = survivors(pids)
        if not exited or len(pids) != 2 or left:
            FAILURES.append(f"#1459: Ctrl-C during a gate left it running (doctor exited: {exited}; recorded "
                            f"{len(pids)} of 2 pids; survivors {left})")

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for f in FAILURES:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"maintainer_doctor selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    # CONTAINED (#1582): this selftest starts process trees on purpose, some built to leak, under
    # every mutant too. Nothing it starts may outlive it -- the 2026-10-03 leak exhausted the
    # user's process limit. Not optional: a missing helper must fail here, not run uncontained.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "rails-flow" / "scripts"))
    from process_containment import contained
    with contained():
        _rc = run()
    sys.exit(_rc)
