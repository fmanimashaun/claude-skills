#!/usr/bin/env python3
"""Prove the mutation checker itself can fail — otherwise it is the very thing it exists to catch.

Run:  python3 scripts/mutation_check.py --selftest

A checker whose job is "prove your guards can fail" is worthless if IT cannot fail. So this pins the
three ways it could silently pass:

  1. a **survivor** — the selftest passes with its subject broken — must be reported, not shrugged off
  2. a **stale anchor** — a mutation that no longer matches — must be a hard error, because a mutation
     that did not apply produces a mutant identical to the original, which passes and looks exactly
     like a caught mutation
  3. a **coincidental catch** — the selftest fails, but for an unrelated reason — must not count, or a
     fixture going quiet is masked by its neighbour

It also asserts every guard's declared anchors still match exactly once in the real tree, so the
mutation list cannot drift away from the code it mutates and start reporting vacuous passes.

Stdlib only.
"""

from __future__ import annotations

import ast
import dataclasses
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mutation_check as mc  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def _tick() -> None:
    global CHECKS
    CHECKS += 1


# A trivial subject + selftest pair, so the three failure modes can be exercised without depending
# on any real guard's behaviour.
SUBJECT = '''
def is_even(n):
    return n % 2 == 0
'''

SELFTEST = '''
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import subject_under_test as s

failures = []
if s.is_even(4) is not True:
    failures.append("fixture-even: expected True for 4")
if s.is_even(3) is not False:
    failures.append("fixture-odd: expected False for 3")
if failures:
    print("SELFTEST FAILED", file=sys.stderr)
    for f in failures:
        print("  - " + f, file=sys.stderr)
    sys.exit(1)
print("ok")
'''


# The same selftest, noisier on failure: 20 numbered lines, one non-UTF-8 byte and one 2,000-character
# line before the verdict, so the report's tail bound, width bound and decoding are each observable.
NOISY_SELFTEST = SELFTEST.replace(
    'if failures:\n',
    'if failures:\n'
    '    for i in range(1, 21):\n'
    '        print(f"noise-{i:02d}", file=sys.stderr)\n'
    '    sys.stderr.flush(); sys.stderr.buffer.write(b"bad-byte-\\xff\\n"); sys.stderr.buffer.flush()\n'
    '    print("wide-" + "w" * 2000, file=sys.stderr)\n', 1)
assert NOISY_SELFTEST != SELFTEST


def _fixture_guard(mutations: tuple[mc.Mutation, ...], selftest: str = SELFTEST) -> tuple[mc.Guard, Path]:
    """A real Guard pointing at a throwaway subject/selftest pair inside a temp 'repo'."""
    root = Path(tempfile.mkdtemp(prefix="mutcheck-selftest-"))
    (root / "scripts").mkdir()
    (root / "scripts" / "subject_under_test.py").write_text(SUBJECT, encoding="utf-8")
    (root / "scripts" / "subject_selftest.py").write_text(selftest, encoding="utf-8")
    guard = mc.Guard(
        name="fixture",
        subject="scripts/subject_under_test.py",
        selftest="scripts/subject_selftest.py",
        mutations=mutations,
    )
    return guard, root


# ---- review of #1525: what a group kill alone could not reach --------------------------------------
# Every child script below records the pids it started in a file, so the fixture can see what
# survived; each one is SIGKILLed at the end whatever the verdict, so a failing run leaks nothing.
_SLEEPER_WITH_GRANDCHILD = (
    "import os, subprocess, sys, time\n"
    "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], start_new_session=True)\n"
    "open(sys.argv[1] + '.tmp', 'w').write(f'{os.getpid()} {g.pid}')\n"
    "os.replace(sys.argv[1] + '.tmp', sys.argv[1])\n"
    "time.sleep(120)\n"
)


def _pids(*files: Path, wait: float = 30.0) -> list[int]:
    """The pids recorded in `files`, waiting up to `wait` seconds for each to appear."""
    import time as _time
    found: list[int] = []
    for f in files:
        deadline = _time.monotonic() + wait
        while not f.exists() and _time.monotonic() < deadline:
            _time.sleep(0.05)
        if f.exists():
            found.extend(int(p) for p in f.read_text().split())
    return found


def _survivors(pids: list[int]) -> list[int]:
    """Which of `pids` are still running two seconds on (a killed process takes a moment to be reaped).
    Every survivor is SIGKILLed before returning."""
    import signal as _signal
    import time as _time
    deadline = _time.monotonic() + 2.0
    alive = list(pids)
    while alive and _time.monotonic() < deadline:
        still = []
        for pid in alive:
            try:
                os.kill(pid, 0)
                still.append(pid)
            except ProcessLookupError:
                pass
        alive = still
        if alive:
            _time.sleep(0.05)
    for pid in alive:
        try:
            os.kill(pid, _signal.SIGKILL)
        except ProcessLookupError:
            pass
    return alive


def _proc_group_fixtures() -> None:
    import signal as _signal
    import subprocess as _sp
    import time as _time
    scripts = Path(mc.__file__).resolve().parent     # the staged copy under a mutant, not the repo's
    pg = mc.proc_group
    work = Path(tempfile.mkdtemp(prefix="procgroup-selftest-"))
    try:
        # (1) TWO LEVELS. A gate whose own children go through proc_group.run, from a thread pool, and
        # one of those starts a grandchild in a session of ITS own -- mutation_check under the doctor,
        # and check_hook_gates' hooks under a mutant. Each inner session is a group the outer killpg
        # never reached: both mutants were alive after the gate's timeout.
        outer = work / "outer.py"
        outer.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(scripts)!r})\n"
            "import proc_group\n"
            "from concurrent.futures import ThreadPoolExecutor\n"
            f"inner = {_SLEEPER_WITH_GRANDCHILD!r}\n"
            "def one(i):\n"
            f"    proc_group.run([sys.executable, '-c', inner, {str(work)!r} + f'/inner{{i}}.pids'], timeout=300)\n"
            "with ThreadPoolExecutor(2) as p:\n"
            "    list(p.map(one, range(2)))\n", encoding="utf-8")
        _tick()
        timed_out = False
        try:
            pg.run([sys.executable, str(outer)], timeout=4)
        except _sp.TimeoutExpired:
            timed_out = True
        recorded = _pids(work / "inner0.pids", work / "inner1.pids", wait=0)
        left = _survivors(recorded)
        if not timed_out or len(recorded) != 4 or left:
            FAILURES.append(f"#1459: a timed-out run left a nested child running -- its inner sessions were not "
                            f"killed (timed out: {timed_out}; recorded {len(recorded)} of 4 pids; survivors {left})")

        # (2) Ctrl-C. A child in a session of its own never sees the terminal's SIGINT, so run() must
        # kill it on the way out: the review measured 2 survivors on the PR head, 0 on dev.
        pids = work / "sigint.pids"
        driver = work / "sigint_driver.py"
        driver.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(scripts)!r})\n"
            "import proc_group\n"
            f"proc_group.run([sys.executable, '-c', {_SLEEPER_WITH_GRANDCHILD!r}, {str(pids)!r}], timeout=300)\n",
            encoding="utf-8")
        _tick()
        d = _sp.Popen([sys.executable, str(driver)], start_new_session=True,
                      stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
        recorded = _pids(pids)
        os.kill(d.pid, _signal.SIGINT)
        try:
            d.wait(timeout=20)
            exited = True
        except _sp.TimeoutExpired:
            exited = False
            d.kill()
            d.wait()
        left = _survivors(recorded)
        if not exited or len(recorded) != 2 or left:
            FAILURES.append(f"#1459: Ctrl-C left a run's child running (exited: {exited}; recorded "
                            f"{len(recorded)} of 2 pids; survivors {left})")

        # (3) Ctrl-C under mutation_check's POOL. Its workers never see the interrupt: the join waited
        # for the running mutant (24 s in the review) while it, and everything it started, kept going.
        # One worker and two guards: the second must never start.
        drv = work / "pool_driver.py"
        hang = work / "hang_selftest.py"
        hang.write_text(_SLEEPER_WITH_GRANDCHILD.replace("sys.argv[1]", repr(str(work) + "/pool-") + " + str(os.getpid())"),
                        encoding="utf-8")
        drv.write_text(
            "import dataclasses, sys\n"
            f"sys.path.insert(0, {str(scripts)!r})\n"
            "import mutation_check as mc, mutation_check_selftest as st\n"
            "guard, root = st._fixture_guard((mc.Mutation('unused', 'n % 2 == 0', 'True', 'fixture-odd'),),\n"
            f"                                selftest=open({str(hang)!r}).read())\n"
            "mc.REPO = root\n"
            "mc.GUARDS = (guard, dataclasses.replace(guard, name='fixture-two'))\n"
            "mc.main(['--jobs', '1'])\n", encoding="utf-8")
        _tick()
        d = _sp.Popen([sys.executable, str(drv)], start_new_session=True,
                      stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
        deadline = _time.monotonic() + 30
        while not any(f.name.startswith("pool-") and not f.name.endswith(".tmp") for f in work.iterdir()) \
                and _time.monotonic() < deadline:
            _time.sleep(0.05)
        os.kill(d.pid, _signal.SIGINT)
        started = _time.monotonic()
        try:
            d.wait(timeout=20)
            exited = True
        except _sp.TimeoutExpired:
            exited = False
            d.kill()
            d.wait()
        took = _time.monotonic() - started
        _time.sleep(1)                  # long enough for a wrongly started second baseline to record itself
        files = [f for f in work.iterdir() if f.name.startswith("pool-") and not f.name.endswith(".tmp")]
        recorded = _pids(*files, wait=0)
        left = _survivors(recorded)
        if not exited or len(files) != 1 or left:
            FAILURES.append(f"#1459: Ctrl-C under mutation_check's pool left work running (exited: {exited} "
                            f"after {took:.0f}s; {len(files)} of 1 baselines started; survivors {left})")

        # (4) ...and once interrupted, nothing new starts: a worker between two tasks would otherwise
        # launch a fresh mutant after the kill, and the join would wait out its whole limit.
        marker = work / "started-after-interrupt"
        _tick()
        # getattr: a proc_group without the mechanism must fail the ASSERTION below, not raise here.
        getattr(pg, "kill_all", lambda: None)()   # nothing of this process is live here, so this kills nothing
        try:
            pg.run([sys.executable, "-c", f"open({str(marker)!r}, 'w')"], timeout=30)
            refused = False
        except KeyboardInterrupt:
            refused = True
        finally:
            if hasattr(pg, "_closing"):
                pg._closing.clear()
        if not refused or marker.exists():
            FAILURES.append("#1459: after an interrupt a new child still started -- the pool's join would "
                            "wait out its whole limit")

        # (5) AN ESCAPEE: a double fork leaves a process that is nobody's descendant and leads its own
        # group, still holding the pipe. The wait for it is bounded, and what the child printed before
        # the kill still comes back (the review found it reported as "printed nothing").
        escapee = work / "escapee.pid"
        child = ("import os, sys, time\n"
                 "print('child-1459 up', flush=True)\n"
                 "if os.fork() == 0:\n"
                 "    os.setsid()\n"
                 "    if os.fork() == 0:\n"
                 f"        open({str(escapee)!r} + '.tmp', 'w').write(str(os.getpid()))\n"
                 f"        os.replace({str(escapee)!r} + '.tmp', {str(escapee)!r})\n"
                 "        time.sleep(60)\n"
                 "    os._exit(0)\n"
                 "os.wait()\n"
                 "time.sleep(120)\n")
        _tick()
        started = _time.monotonic()
        output, raised = None, False
        saved_wait = getattr(pg, "ESCAPEE_WAIT", None)
        pg.ESCAPEE_WAIT = 1             # the bound is the claim, not its size: keep the selftest quick
        try:
            pg.run([sys.executable, "-c", child], timeout=2, text=True)
        except _sp.TimeoutExpired as exc:
            output, raised = exc.output, True
        finally:
            pg.ESCAPEE_WAIT = saved_wait
        took = _time.monotonic() - started
        _survivors(_pids(escapee, wait=5))
        if not raised or took > 2 + 1 + 10:
            FAILURES.append(f"#1459: an escapee holding the pipe must cost at most ESCAPEE_WAIT, not a hang "
                            f"(took {took:.0f}s, timed out: {raised})")
        _tick()
        text = output.decode(errors="replace") if isinstance(output, bytes) else (output or "")
        if "child-1459 up" not in text:
            FAILURES.append(f"#1459: an escapee's timeout dropped what the child printed before the kill; got {output!r}")

        # (6) AN ORPHAN STILL IN THE GROUP: a double fork WITHOUT setsid leaves a process whose parent
        # is gone, so no walk by parent pid finds it -- only the kill of the child's own group does,
        # and that group is the child's only because it starts a session of its own.
        orphan = work / "orphan.pid"
        child = ("import os, sys, time\n"
                 "if os.fork() == 0:\n"
                 "    if os.fork() == 0:\n"
                 "        null = os.open(os.devnull, os.O_WRONLY)\n"
                 "        os.dup2(null, 1)\n"
                 "        os.dup2(null, 2)\n"
                 f"        open({str(orphan)!r} + '.tmp', 'w').write(str(os.getpid()))\n"
                 f"        os.replace({str(orphan)!r} + '.tmp', {str(orphan)!r})\n"
                 "        time.sleep(60)\n"
                 "    os._exit(0)\n"
                 "os.wait()\n"
                 "time.sleep(120)\n")
        _tick()
        try:
            pg.run([sys.executable, "-c", child], timeout=2)
        except _sp.TimeoutExpired:
            pass
        recorded = _pids(orphan, wait=0)
        left = _survivors(recorded)
        if len(recorded) != 1 or left:
            FAILURES.append(f"#1459: a timed-out run left an orphan in its group running (recorded "
                            f"{len(recorded)} of 1 pid; survivors {left})")
        # (5) #1548: an exception MID-WALK must not leave the tree SIGSTOPped. The first `ps` pass freezes
        # the grandchild; the second raises, as a Ctrl-C or a failing `ps` would. Both must end up dead,
        # not stopped, and the exception must still reach the caller.
        midwalk = work / "midwalk.pids"
        root = _sp.Popen([sys.executable, "-c", _SLEEPER_WITH_GRANDCHILD, str(midwalk)], start_new_session=True,
                         stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
        tree = _pids(midwalk)
        real_rows, calls = pg._ps_rows, [0]

        def rows_then_raise():
            calls[0] += 1
            if calls[0] >= 2:
                raise KeyboardInterrupt("injected mid-walk (#1548)")
            return real_rows()
        pg._ps_rows = rows_then_raise
        reraised = False
        try:
            pg.kill_tree(root.pid)
        except KeyboardInterrupt:
            reraised = True
        finally:
            pg._ps_rows = real_rows
        try:
            root.wait(timeout=10)
        except _sp.TimeoutExpired:
            pass

        def stat(pid: int) -> str:
            return _sp.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
        _time.sleep(0.5)
        stopped = [p for p in tree if stat(p).startswith("T")]
        running = [p for p in tree if stat(p) and not stat(p).startswith(("T", "Z"))]
        for p in tree:                    # never leave this fixture's own processes behind
            try:
                os.kill(p, _signal.SIGKILL)
            except ProcessLookupError:
                pass
        if not reraised or stopped or running:
            FAILURES.append(f"#1548: an exception mid-walk left the tree stopped or running (re-raised: {reraised}; "
                            f"stopped {stopped}; running {running})")

        # (6) #1548: a pool started after an interrupted one starts children again. `kill_all` sets
        # `_closing` for the pool it interrupts; a later pool must not inherit it.
        _tick()
        pg.kill_all()
        second = work / "second-pool"
        try:
            with pg.pool(1) as ex:
                ex.submit(pg.run, [sys.executable, "-c", f"open({str(second)!r}, 'w')"], timeout=30).result()
            started = second.exists()
        except KeyboardInterrupt:
            started = False
        finally:
            pg._closing.clear()
        if not started:
            FAILURES.append("#1548: a pool started after an interrupted one refused every child -- _closing never resets")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def run() -> int:
    original_repo = mc.REPO

    # ---- 0. EVERY DECLARED PATH RESOLVES FROM ITS GUARD'S BASE ------------------------
    # A shipped guard's paths are plugin-relative so it can run in a project that installed only
    # that plugin; one reaching out to `skills/` or a sibling plugin cannot resolve there, and the
    # failure is a FileNotFoundError deep in staging rather than a sentence anyone can act on.
    #
    # CHECKED HERE RATHER THAN AT IMPORT, and that placement is the point. This module is also
    # loaded inside a STAGED tempdir -- `doctrine_map`'s own selftest copies the repo and re-imports
    # it -- where a file a guard legitimately needs, such as `CHANGELOG.md`, is simply not staged.
    # Raising at import broke two guards that were correct, which is the "gate red on correct code"
    # shape. The real tree is the only place the question is meaningful (#1109).
    for guard in mc.GUARDS:
        base = original_repo / guard.base
        for relative in sorted({guard.subject, guard.selftest, *guard.deps, *guard.needs}):
            _tick()
            if not (base / relative).exists():
                FAILURES.append(
                    f"{guard.name}: {relative!r} does not resolve from base {guard.base!r} — a "
                    f"shipped guard's paths are plugin-relative; if it cannot be expressed that "
                    f"way the guard belongs in scripts/mutations/")

    # ---- 1. a real break must be CAUGHT, and attributed to the right fixture ------------
    guard, root = _fixture_guard((
        mc.Mutation("odd numbers reported even", "n % 2 == 0", "True", "fixture-odd"),
    ))
    mc.REPO = root
    try:
        _tick()
        problems = mc.run_guard(guard)
        if problems:
            FAILURES.append(f"a genuine break was not accepted as caught: {problems}")
    finally:
        mc.REPO = original_repo

    # ---- 1b. a mutant's limit SCALES with its guard's baseline (#1486) -----------------
    # The same slow guard, twice. With the limit derived from the ~1 s baseline, the mutant has
    # time to fail and is caught; with the scale zeroed, the fixed floor is shorter than the run,
    # and it times out -- which is what 10 of 12 hook_guard_bash mutations did under load.
    guard, root = _fixture_guard((
        mc.Mutation("odd numbers reported even", "n % 2 == 0", "True", "fixture-odd"),
    ))
    slow = root / "scripts" / "subject_selftest.py"
    slow.write_text("import time\ntime.sleep(1.0)\n" + slow.read_text(encoding="utf-8"), encoding="utf-8")
    saved = (mc.REPO, mc.MUTATION_FLOOR, mc.MUTATION_SCALE)
    mc.REPO, mc.MUTATION_FLOOR = root, 0.4
    try:
        _tick()
        mc.MUTATION_SCALE = 3.0
        problems = mc.run_guard(guard)
        if problems:
            FAILURES.append(f"#1486: a slow guard's mutant must get a limit scaled from its baseline, got {problems}")
        _tick()
        mc.MUTATION_SCALE = 0.0
        problems = mc.run_guard(guard)
        if not any("timed out after" in p for p in problems):
            FAILURES.append(f"#1486 CONTROL: with no scaling, the fixed floor must time the mutant out, got {problems}")
    finally:
        mc.REPO, mc.MUTATION_FLOOR, mc.MUTATION_SCALE = saved
    # ...and THE PATH CI RUNS: main()'s pool, driven end to end on the same slow guard (review of
    # PR #1491: the pool's call could drop the limit with the fixture above still green).
    saved = (mc.REPO, mc.MUTATION_FLOOR, mc.MUTATION_SCALE, mc.GUARDS)
    mc.REPO, mc.MUTATION_FLOOR, mc.GUARDS = root, 0.4, [guard]
    try:
        import contextlib, io
        _tick()
        mc.MUTATION_SCALE = 3.0
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            rc = mc.main(["--jobs", "2"])
        if rc != 0:
            FAILURES.append(f"#1486: main()'s pool must give a slow guard's mutant its scaled limit, exit {rc}")
        _tick()
        mc.MUTATION_SCALE = 0.0
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            rc = mc.main(["--jobs", "2"])
        if rc == 0 or "timed out after" not in err.getvalue():
            FAILURES.append(f"#1486 CONTROL: main()'s pool with no scaling must time the mutant out, exit {rc}")
    finally:
        mc.REPO, mc.MUTATION_FLOOR, mc.MUTATION_SCALE, mc.GUARDS = saved
    _tick()
    quick = mc.Guard(name="quick", subject="s.py", selftest="t.py", mutations=())
    heavy = mc.Guard(name="heavy", subject="s.py", selftest="t.py", mutations=())
    stuck = mc.Guard(name="stuck", subject="s.py", selftest="t.py", mutations=())
    limits = mc.mutation_limits([quick, heavy, stuck], [([], 10.0), ([], 200.0), ([], 1000.0)])
    if limits != {"quick": 300.0, "heavy": 600.0, "stuck": mc.MUTATION_CAP}:
        FAILURES.append(f"#1486: main's pool must give each guard max(floor, 3x baseline), capped, got {limits}")

    # ---- 1c. selftest_args reach the baseline AND every mutant (#1497) ------------------
    # A selftest that refuses to run without its argument: with the argument declared, the guard
    # scores normally; without it, the baseline fails and the guard reads INERT.
    guard, root = _fixture_guard((
        mc.Mutation("odd numbers reported even", "n % 2 == 0", "True", "fixture-odd"),
    ))
    needy = root / "scripts" / "subject_selftest.py"
    needy.write_text("import sys\nif '--arg-1497' not in sys.argv:\n    sys.exit(3)\n"
                     + needy.read_text(encoding="utf-8"), encoding="utf-8")
    mc.REPO = root
    try:
        _tick()
        with_args = dataclasses.replace(guard, selftest_args=("--arg-1497",))
        problems = mc.run_guard(with_args)
        if problems:
            FAILURES.append(f"#1497: a guard's selftest_args must reach its baseline and mutants, got {problems}")
        _tick()
        problems = mc.run_guard(guard)
        if not any("INERT" in p for p in problems):
            FAILURES.append(f"#1497 CONTROL: without its argument the same selftest must read INERT, got {problems}")
    finally:
        mc.REPO = original_repo

    # ---- 1e. a mutant runs only the fixture its `expects` names, and only if that fixture passes alone (#1599) ----
    # A guard that sets `narrow_with` gets `<flag> <expects>` on every mutant, and on a CONTROL run of the
    # UNMUTATED code first: a fixture that cannot pass alone (it leans on state another fixture sets up)
    # would otherwise "catch" every mutant by failing for that reason. The stand-in selftest honours the
    # flag and logs each invocation, so what the baseline, the control and the mutant ran can be read.
    narrow_src = (
        "import sys\n"
        "from pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent))\n"
        "import subject_under_test as s\n"
        "match = sys.argv[sys.argv.index('--match') + 1].lower() if '--match' in sys.argv else None\n"
        "want = lambda label: match is None or match in label.lower()\n"
        "if match is not None and 'REFUSE' in Path(s.__file__).read_text():\n"
        "    print('selected no check for ' + match, file=sys.stderr); sys.exit(2)\n"
        "ran, failures = [], []\n"
        "if want('fixture-even'):\n"
        "    ran.append('even')\n"
        "    if s.is_even(4) is not True:\n"
        "        failures.append('fixture-even: expected True for 4')\n"
        "if want('fixture-odd'):\n"
        "    ran.append('odd')\n"
        "    if NEEDS_EVEN and 'even' not in ran:\n"
        "        failures.append('fixture-odd: leans on the even fixture')\n"
        "    if s.is_even(3) is not False:\n"
        "        failures.append('fixture-odd: expected False for 3')\n"
        "open(LOG, 'a').write(' '.join(sys.argv[1:]) + ' | ran ' + ','.join(ran) + '\\n')\n"
        "if match is not None and not ran:\n"
        "    print('selected no check', file=sys.stderr); sys.exit(2)\n"
        "if failures:\n"
        "    print('SELFTEST FAILED', file=sys.stderr)\n"
        "    for f in failures: print('  - ' + f, file=sys.stderr)\n"
        "    sys.exit(1)\n"
        "print('ok')\n")

    def narrow_guard(mutation: mc.Mutation, needs_even: bool = False, narrow_with: str = "--match"):
        guard, root = _fixture_guard((mutation,))
        log = root / "invocations.log"
        (root / "scripts" / "subject_selftest.py").write_text(
            narrow_src.replace("LOG", repr(str(log))).replace("NEEDS_EVEN", repr(needs_even)), encoding="utf-8")
        return dataclasses.replace(guard, narrow_with=narrow_with), root, log

    odd_break = mc.Mutation("odd numbers reported even", "n % 2 == 0", "True", "fixture-odd")
    guard, root, log = narrow_guard(odd_break)
    mc.REPO = root
    try:
        _tick()
        problems = mc.run_guard(guard)
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        narrowed = [l for l in lines if "--match fixture-odd" in l]
        if problems or len(lines) != 3 or len(narrowed) != 2 or any("ran odd" not in l for l in narrowed):
            FAILURES.append(f"#1599: a narrowing guard must run its baseline whole and its control and mutant on "
                            f"the expected fixture only, got problems={problems} log={lines}")
    finally:
        mc.REPO = original_repo
    # ...a guard that does not set it runs every mutant whole,
    guard, root, log = narrow_guard(odd_break, narrow_with="")
    mc.REPO = root
    try:
        _tick()
        mc.run_guard(guard)
        lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        if any("--match" in l for l in lines):
            FAILURES.append(f"#1599 CONTROL: a guard with no narrow_with must not be narrowed, got {lines}")
    finally:
        mc.REPO = original_repo
    # ...a mutation with no `expects`, or one that opts out, runs whole as well,
    for label, mutation in (("no expects", dataclasses.replace(odd_break, expects="")),
                            ("narrow=False", dataclasses.replace(odd_break, narrow=False))):
        guard, root, log = narrow_guard(mutation)
        mc.REPO = root
        try:
            _tick()
            mc.run_guard(guard)
            lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
            if any("--match" in l for l in lines):
                FAILURES.append(f"#1599: a mutation with {label} must run the whole selftest, got {lines}")
        finally:
            mc.REPO = original_repo
    # THE CONTROL RUN: a fixture that cannot pass alone must not count a mutant as caught.
    guard, root, log = narrow_guard(odd_break, needs_even=True)
    mc.REPO = root
    try:
        _tick()
        problems = mc.run_guard(guard)
        if not any("cannot be narrowed" in x for x in problems):
            FAILURES.append(f"#1599: a fixture that fails alone, unmutated, must be reported as unable to be "
                            f"narrowed and never counted as catching its mutant, got {problems}")
    finally:
        mc.REPO = original_repo
    # An `expects` that names no fixture selects nothing: loud, not an empty pass.
    guard, root, log = narrow_guard(dataclasses.replace(odd_break, expects="no such fixture"))
    mc.REPO = root
    try:
        _tick()
        problems = mc.run_guard(guard)
        if not any("cannot be narrowed" in x for x in problems):
            FAILURES.append(f"#1599: an `expects` that selects no fixture must be reported, got {problems}")
    finally:
        mc.REPO = original_repo
    # A mutant the SELECTED fixture does not notice still SURVIVES: narrowing cannot hide it.
    guard, root, log = narrow_guard(mc.Mutation("only 4 is wrong", "n % 2 == 0", "n % 2 == 0 and n != 4", "fixture-odd"))
    mc.REPO = root
    try:
        _tick()
        problems = mc.run_guard(guard)
        if not any("SURVIVED" in x for x in problems):
            FAILURES.append(f"#1599: a mutant the narrowed fixture cannot see must be reported SURVIVED, got {problems}")
    finally:
        mc.REPO = original_repo
    # A REFUSAL IS NOT A CATCH (review of #1603, F1). A mutant that makes the selection refuse exits 2 with a message
    # that quotes the label `expects` names, so "non-zero and the label appears" counted it as caught. Only the
    # selftest's own failure, exit 1, is a catch under narrowing.
    guard, root, log = narrow_guard(mc.Mutation("the selection is refused", "n % 2 == 0", "n % 2 == 0  # REFUSE", "fixture-odd"))
    mc.REPO = root
    try:
        _tick()
        problems = mc.run_guard(guard)
        if not any("refused or crashed" in x for x in problems):
            FAILURES.append(f"#1599: a narrowed mutant that is REFUSED (exit 2) must be a problem, never a catch, got {problems}")
    finally:
        mc.REPO = original_repo

    # ---- 1f. the cost ratchet: a new expensive guard fails until it is cheaper or the record is re-set (#1599) ----
    # `mutation coverage` reached 3490 s of its 3600 s budget and nothing said which guard had grown. A guard over
    # RATCHET_FLOOR seconds of work must be on record; one on record may not grow past RATCHET_GROWTH x its record
    # plus RATCHET_SLACK; a record naming a guard that is gone is drift. Pure functions, so every rule has a case.
    floor = mc.RATCHET_FLOOR
    record = {"guards": {"heavy": 400.0, "medium": 100.0}}

    def ratchet(cost: dict, base: dict | None) -> list[str]:
        """`ratchet_problems`, with a raise reported as a problem: a mutant that breaks it by CRASHING would
        otherwise die with a traceback that names no fixture, and read as caught by the wrong thing (#1599)."""
        try:
            return mc.ratchet_problems(cost, base)
        except Exception as exc:        # noqa: BLE001 -- the check below fails by name
            return [f"raised {exc!r}"]

    cases = [
        ("a NEW guard over the new-guard limit", {"heavy": 400.0, "medium": 100.0, "fresh": mc.RATCHET_NEW + 1},
         record, "fresh"),
        ("a recorded guard past growth and slack", {"heavy": 400.0 * mc.RATCHET_GROWTH + mc.RATCHET_SLACK + 1,
                                                     "medium": 100.0}, record, "heavy"),
        ("a record naming a guard that no longer exists", {"heavy": 400.0}, record, "medium"),
    ]
    for label, cost, base, names in cases:
        _tick()
        problems = ratchet(cost, base)
        if not any(names in x for x in problems):
            FAILURES.append(f"#1599: the ratchet must report {label} (naming {names!r}), got {problems}")
        # AND SAY WHAT TO DO: a growth or a new guard is fixed by re-recording the file IN THIS PR (the coordinator's rule, 2026-10-05).
        if names in ("fresh", "heavy") and not any("re-record docs/evidence/mutation-cost-baseline.json in this PR" in x
                                                    for x in problems if names in x):
            FAILURES.append(f"#1599: the ratchet's refusal for {label} must tell the author to re-record the baseline in this PR, got {problems}")
    for label, cost, base in (
            ("a new guard under the floor", {"heavy": 400.0, "medium": 100.0, "fresh": floor - 1}, record),
            # THE REASON RATCHET_NEW EXISTS: a guard just under the record floor is not on record, and a slow runner
            # can push it past the floor without anyone having made it more expensive.
            ("a new guard between the record floor and the new-guard limit",
             {"heavy": 400.0, "medium": 100.0, "fresh": mc.RATCHET_NEW - 1}, record),
            ("a recorded guard within growth and slack", {"heavy": 400.0 * mc.RATCHET_GROWTH + mc.RATCHET_SLACK,
                                                           "medium": 100.0}, record),
            ("a recorded guard that got cheaper, even under the floor", {"heavy": 400.0, "medium": floor - 5}, record)):
        _tick()
        problems = ratchet(cost, base)
        if problems:
            FAILURES.append(f"#1599 CONTROL: the ratchet must accept {label}, got {problems}")
    _tick()
    problems = ratchet({"heavy": 400.0}, None)
    if not (len(problems) == 1 and "no cost record" in problems[0]):
        FAILURES.append(f"#1599: with no record at all the ratchet must say so once, never pass, got {problems}")
    # The record alone, with no run (`--check-record`, the gate a pull request can afford): missing or naming a guard that
    # is gone fails; a record that holds is clean. `ratchet_problems` reads the same function, so the two cannot disagree.
    for label, base, guards, want in (
            ("a missing record", None, {"heavy"}, "no cost record"),
            ("a record naming a guard that is gone", record, {"heavy"}, "medium")):
        _tick()
        try:
            found = mc.record_problems(guards, base)
        except Exception as exc:        # noqa: BLE001 -- the check below fails by name
            found = [f"raised {exc!r}"]
        if not any(want in x for x in found):
            FAILURES.append(f"#1599: the record check must report {label}, got {found}")
    _tick()
    if mc.record_problems({"heavy", "medium", "extra"}, record):
        FAILURES.append("#1599 CONTROL: a record whose guards all exist is clean (a guard missing from it is not drift)")

    class StandInGuard:
        """The registry is replaced by one stand-in guard: the guards that run THIS selftest in a staged tempdir (hermetic_git,
        proc_group, this harness) do not stage `scripts/mutations/`, so the real `mc.GUARDS` is empty there and indexing it
        raised an IndexError that made three baselines inert (CI run 37223022427). The test needs a registry, not THE registry."""
        name = "stand_in_guard"

    def check_record_exit(loader) -> int:
        """`main(["--check-record"])` with the record replaced by `loader` and the registry by one stand-in guard; output swallowed."""
        import contextlib
        import io
        real_loader, real_guards = mc.load_cost_baseline, mc.GUARDS
        mc.load_cost_baseline, mc.GUARDS = loader, (StandInGuard,)
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return mc.main(["--check-record"])
        except Exception:               # noqa: BLE001 -- a crash is not an exit code of 0 or 1
            return -1
        finally:
            mc.load_cost_baseline, mc.GUARDS = real_loader, real_guards

    def unreadable():
        raise ValueError("not a record")

    for label, loader, want in (
            ("--check-record exits 1 for a record naming a guard that is gone", lambda: {"guards": {"ghost_guard": 99.0}}, 1),
            ("--check-record exits 1 when there is no record", lambda: None, 1),
            ("--check-record exits 1 for an unreadable record", unreadable, 1),
            ("--check-record exits 0 for a record that holds", lambda: {"guards": {StandInGuard.name: 99.0}}, 0)):
        _tick()
        got = check_record_exit(loader)
        if got != want:
            FAILURES.append(f"#1599: {label}; got exit {got}")
    # The record: only guards over the floor, deterministic bytes, and a round trip.
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "cost.json"
        mc.write_cost_baseline(path, {"heavy": 400.04, "light": floor - 1, "medium": 100.0}, jobs=4)
        first = path.read_bytes()
        mc.write_cost_baseline(path, {"medium": 100.0, "light": floor - 1, "heavy": 400.04}, jobs=4)
        loaded = mc.load_cost_baseline(path)
        _tick()
        if first != path.read_bytes() or loaded is None or set(loaded["guards"]) != {"heavy", "medium"} \
                or loaded["guards"]["heavy"] != 400.0:
            FAILURES.append(f"#1599: the record must hold only guards over the floor, rounded, in a stable order, "
                            f"got {loaded} / {first!r}")
        _tick()
        if mc.load_cost_baseline(Path(td) / "absent.json") is not None:
            FAILURES.append("#1599: an absent record must load as None, not as an empty one")
        path.write_text("{not json", encoding="utf-8")
        _tick()
        try:
            mc.load_cost_baseline(path)
        except ValueError:
            pass
        else:
            FAILURES.append("#1599: a malformed record must raise, never read as empty (which would pass everything)")

    # ---- 1d. baselines and mutants start no detached git maintenance (#1510) ----------------
    # The helper APPENDS to a caller's own pairs, never renumbers them over.
    _tick()
    mine = mc.hermetic_git.env({"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.x", "GIT_CONFIG_VALUE_0": "y"})
    if (mine.get("GIT_CONFIG_KEY_0"), mine.get("GIT_CONFIG_COUNT"), mine.get("GIT_CONFIG_KEY_1"),
            mine.get("GIT_CONFIG_KEY_2")) != ("core.x", "3", "maintenance.auto", "gc.auto"):
        FAILURES.append(f"#1510: hermetic_git.env must append after a caller's GIT_CONFIG pairs, got {mine}")
    # ...an empty count is none, and a count git rejects is left exactly as it was.
    _tick()
    if mc.hermetic_git.env({"GIT_CONFIG_COUNT": ""}).get("GIT_CONFIG_KEY_0") != "maintenance.auto":
        FAILURES.append("#1510: an empty GIT_CONFIG_COUNT is no pairs, so ours start at 0")
    for bogus in ("-1", "abc", " 2 ", "٣"):
        _tick()
        given = {"GIT_CONFIG_COUNT": bogus, "GIT_CONFIG_KEY_0": "core.x", "GIT_CONFIG_VALUE_0": "y"}
        if mc.hermetic_git.env(given) != given:
            FAILURES.append(f"#1510: a count git rejects ({bogus!r}) must be left untouched, "
                            f"got {mc.hermetic_git.env(given)}")
    # #1588: an inherited GIT_DIR (git exports it to hooks, `rebase --exec`, `bisect run`...) must not
    # survive into a fixture's environment: under it, `git -C <tmp> commit` commits into $GIT_DIR.
    _tick()
    poisoned = mc.hermetic_git.env({"GIT_DIR": "/real/.git", "GIT_WORK_TREE": "/real", "GIT_INDEX_FILE": "/real/i",
                                    "PATH": "/usr/bin"})
    if any(k in poisoned for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")) or poisoned.get("PATH") != "/usr/bin":
        FAILURES.append(f"#1588: hermetic_git.env must drop the repository-locating variables and keep the rest, "
                        f"got {sorted(poisoned)}")
    # ...end to end: the #1493 probe's own commands, under an inherited GIT_DIR naming a stand-in repo.
    import subprocess as _sp, tempfile as _tf
    with _tf.TemporaryDirectory() as _w:
        _real = Path(_w) / "real"
        _sp.run(["git", "init", "-q", str(_real)], check=True, env=mc.hermetic_git.env())
        _sp.run(["git", "-C", str(_real), "-c", "user.email=x@x", "-c", "user.name=x", "commit", "-q",
                 "--allow-empty", "-m", "real"], check=True, env=mc.hermetic_git.env())
        _env = mc.hermetic_git.env({**os.environ, "GIT_DIR": str(_real / ".git")})
        _tmp = Path(_w) / "probe"
        _sp.run(["git", "init", "-q", str(_tmp)], env=_env, capture_output=True)
        _sp.run(["git", "-C", str(_tmp), "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgSign=false",
                 "commit", "-q", "--allow-empty", "-m", "m"], env=_env, capture_output=True)
        _n = _sp.run(["git", "-C", str(_real), "rev-list", "--count", "HEAD"], capture_output=True, text=True,
                     env=mc.hermetic_git.env()).stdout.strip()
        _tick()
        if _n != "1":
            FAILURES.append(f"#1588: a fixture commit under an inherited GIT_DIR reached the repo it names "
                            f"({_n} commits, want 1) -- the t@t/m commits on dev")
    # A selftest that commits in a temp repo under GIT_TRACE and refuses to go on if git started
    # `maintenance run --auto` or `gc --auto` -- the #1493 race. Through run_guard, so it proves
    # the CALLER passes the env to both the baseline and the mutant, not only that the helper builds it.
    probe = (
        "import os, subprocess, sys, tempfile\n"
        "with tempfile.TemporaryDirectory() as d:\n"
        "    subprocess.run(['git', 'init', '-q', d], check=True)\n"
        "    t = subprocess.run(['git', '-C', d, '-c', 'user.email=t@t', '-c', 'user.name=t', '-c',\n"
        "                        'commit.gpgSign=false', 'commit', '-q', '--allow-empty', '-m', 'm'],\n"
        "                       capture_output=True, text=True, env={**os.environ, 'GIT_TRACE': '1'})\n"
        "    if 'maintenance run' in t.stderr or 'gc --auto' in t.stderr:\n"
        "        print('background git maintenance started'); sys.exit(4)\n"
    )
    guard, root = _fixture_guard((
        mc.Mutation("odd numbers reported even", "n % 2 == 0", "True", "fixture-odd"),
    ))
    traced = root / "scripts" / "subject_selftest.py"
    traced.write_text(probe + traced.read_text(encoding="utf-8"), encoding="utf-8")
    mc.REPO = root
    real_env = mc.hermetic_git.env
    # The ambient env must not already be hermetic -- under a mutation guard it is, inherited from the
    # outer runner -- or a call site that drops `env=` still passes. Only the call site may supply it.
    inherited = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("GIT_CONFIG_")}
    try:
        _tick()
        problems = mc.run_guard(guard)
        if problems:
            FAILURES.append(f"#1510: the baseline and the mutant must run with git maintenance off, got {problems}")
        _tick()
        # No env, really: drop GIT_CONFIG_* too, or a run nested inside a hermetic runner (the
        # mutation guard for this very file) inherits the settings and the control proves nothing.
        mc.hermetic_git.env = lambda base=None: {k: v for k, v in (os.environ if base is None else base).items()
                                                 if not k.startswith("GIT_CONFIG_")}
        problems = mc.run_guard(guard)
        if not any("INERT" in p for p in problems):
            FAILURES.append(f"#1510 CONTROL: without the env this git does start maintenance, so the same "
                            f"selftest must read INERT, got {problems}")
    finally:
        mc.hermetic_git.env = real_env
        os.environ.update(inherited)
        mc.REPO = original_repo

    # ---- 1e. a mutant that times out takes its whole process group, and says what it knows (#1459)
    # The mutated selftest starts a grandchild that would outlive a plain kill, prints a line, then
    # hangs. run_mutation must report a timeout naming the guard, the mutation and the elapsed time,
    # with that line as its tail, and leave nothing running. #1556: the grandchild's pid is recorded
    # atomically AFTER the line is printed, and the timeout is lengthened only while the mutant never
    # got that far -- a mutant killed before it started is no verdict on the group kill.
    import signal as _signal
    import time as _time
    guard, root = _fixture_guard((
        mc.Mutation("the mutant hangs", "n % 2 == 0", "n % 2 == 0 or __import__('time').sleep(0)", "fixture-odd"),
    ))
    pidfile = root / "grandchild.pid"
    hang = root / "scripts" / "subject_selftest.py"
    hang.write_text("import subprocess, sys, time\n"
                    "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                    "print('mutant-1459 started its grandchild', flush=True)\n"
                    f"open({str(pidfile)!r} + '.tmp', 'w').write(str(g.pid))\n"
                    f"__import__('os').replace({str(pidfile)!r} + '.tmp', {str(pidfile)!r})\n"
                    "time.sleep(120)\n", encoding="utf-8")
    mc.REPO = root
    try:
        _tick()
        for limit in (2, 4, 8):
            t0 = _time.monotonic()
            problems = mc.run_mutation(guard, guard.mutations[0], timeout=limit)
            took = _time.monotonic() - t0
            recorded = _pids(pidfile, wait=0)
            if recorded:
                break
        report = " | ".join(problems)
        if not recorded:
            FAILURES.append(f"#1459: the timed-out mutant never started its grandchild, even with {limit}s -- "
                            f"the runner is too loaded to judge the group kill; got {problems!r}")
        elif not ("fixture: the mutant hangs timed out after" in report and "mutant-1459 started its grandchild" in report
                  and f"limit {limit}s" in report and took < limit + 18):
            FAILURES.append(f"#1459: a timed-out mutant must report guard, mutation, elapsed and its tail, "
                            f"promptly; got {problems!r} after {took:.0f}s")
        _tick()
        grandchild = recorded[0] if recorded else None
        gone = grandchild is not None
        for _ in range(20):
            try:
                os.kill(grandchild, 0)
            except (ProcessLookupError, TypeError):
                break
            _time.sleep(0.1)
        else:
            gone = False
            os.kill(grandchild, _signal.SIGKILL)
        if not gone:
            FAILURES.append("#1459: a timed-out mutant left its grandchild running -- its process group was not killed")
    finally:
        mc.REPO = original_repo

    # ...and each guard's line prints the moment its last mutation finishes, once, not after the pool.
    import contextlib as _contextlib
    import io as _io
    from concurrent.futures import ThreadPoolExecutor as _Pool
    guard, root = _fixture_guard((
        mc.Mutation("odd numbers reported even", "n % 2 == 0", "True", "fixture-odd"),
        mc.Mutation("even numbers reported odd", "n % 2 == 0", "False", "fixture-even"),
    ))
    mc.REPO = root
    try:
        _tick()
        buf = _io.StringIO()
        with _contextlib.redirect_stdout(buf), _Pool(max_workers=2) as pool:
            outcomes = mc.run_live(pool, [(guard, m) for m in guard.mutations], {guard.name: 60.0})
        lines = [l for l in buf.getvalue().splitlines() if l.strip().startswith("[done] fixture:")]
        if lines != ["  [done] fixture: 2 mutation(s), 0 problem(s)"] or len(outcomes) != 2:
            FAILURES.append(f"#1459: a guard's progress line prints once when its last mutation ends, "
                            f"got {buf.getvalue()!r} / {len(outcomes)} outcome(s)")
    finally:
        mc.REPO = original_repo

    # ---- 1f. NESTED runners, Ctrl-C, and an escapee (review of #1525) ---------------------------
    _proc_group_fixtures()

    # ---- 2. a SURVIVOR must be reported ------------------------------------------------
    # This mutation changes the subject in a way neither fixture observes, so the selftest still
    # passes. That is exactly the vacuous-fixture situation, and it must not read as success.
    guard, root = _fixture_guard((
        mc.Mutation("adds an unobserved helper", "def is_even(n):",
                    "def unobserved():\n    return 1\n\n\ndef is_even(n):", "fixture-odd"),
    ))
    mc.REPO = root
    try:
        _tick()
        problems = mc.run_guard(guard)
        if not any("SURVIVED" in p for p in problems):
            FAILURES.append(
                "a survivor was not reported — the checker would pass a guard whose fixtures "
                f"observe nothing; got {problems}"
            )
    finally:
        mc.REPO = original_repo

    # ---- 3. a STALE ANCHOR must be a hard error, never a pass --------------------------
    guard, root = _fixture_guard((
        mc.Mutation("anchor that no longer exists", "this_text_is_absent", "x", "fixture-odd"),
    ))
    mc.REPO = root
    try:
        _tick()
        try:
            mc.apply_mutation(guard, guard.mutations[0], Path(tempfile.mkdtemp()))
            FAILURES.append(
                "a stale anchor did not raise — a mutation that cannot apply yields a mutant "
                "identical to the original, which passes and reads exactly like a caught mutation"
            )
        except RuntimeError as exc:
            if "anchor matches 0" not in str(exc):
                FAILURES.append(f"stale anchor raised the wrong message: {exc}")
    finally:
        mc.REPO = original_repo

    # A NON-UNIQUE anchor is equally unsafe: it would mutate more than intended, so the result
    # cannot be attributed to the change under test.
    guard, root = _fixture_guard((
        mc.Mutation("ambiguous anchor", "return", "pass", "fixture-odd"),
    ))
    mc.REPO = root
    try:
        _tick()
        (root / "scripts" / "subject_under_test.py").write_text(
            SUBJECT + "\n\ndef other():\n    return 2\n", encoding="utf-8")
        try:
            mc.apply_mutation(guard, guard.mutations[0], Path(tempfile.mkdtemp()))
            FAILURES.append("a non-unique anchor did not raise")
        except RuntimeError as exc:
            if "need exactly 1" not in str(exc):
                FAILURES.append(f"non-unique anchor raised the wrong message: {exc}")
    finally:
        mc.REPO = original_repo

    # ---- 4. a COINCIDENTAL catch must not count ----------------------------------------
    # The break is real and the selftest fails — but on the *other* fixture. Expecting the wrong
    # one must be reported, or a fixture going quiet is masked by its neighbour.
    guard, root = _fixture_guard((
        mc.Mutation("even numbers reported odd", "n % 2 == 0", "False", "fixture-odd"),
    ))
    mc.REPO = root
    try:
        _tick()
        problems = mc.run_guard(guard)
        if not any("not by the expected fixture" in p for p in problems):
            FAILURES.append(
                "a catch by the WRONG fixture was accepted — that hides the intended fixture "
                f"going quiet; got {problems}"
            )
    finally:
        mc.REPO = original_repo

    # ...and a BASELINE that fails with a non-UTF-8 byte in its output is reported INERT, never a
    # crash: #1493 decoded mutant output only, and the baseline has the same pipe.
    broken = 'import sys\nsys.stderr.flush(); sys.stderr.buffer.write(b"bad-\\xff\\n"); sys.stderr.buffer.flush()\nsys.exit(1)\n'
    guard, root = _fixture_guard((mc.Mutation("unused", "n % 2 == 0", "True", "fixture-odd"),), selftest=broken)
    mc.REPO = root
    try:
        _tick()
        try:
            problems = mc.run_guard(guard)
            if not any("INERT" in p for p in problems):
                FAILURES.append(f"a baseline failing with a non-UTF-8 byte must read INERT, got {problems}")
        except UnicodeDecodeError as exc:
            FAILURES.append(f"a non-UTF-8 byte in a BASELINE's output raised before the INERT report printed: {exc}")
    finally:
        mc.REPO = original_repo

    # ...and the report carries the mutant's own output, or a catch seen only on CI cannot be
    # diagnosed (#1493: two CI-only wrong-fixture catches, no output kept). A NOISY mutant, so each
    # bound is observable: the last 12 lines exactly, the first line gone, every line <= 300 chars,
    # and a non-UTF-8 byte decoded rather than raised.
    guard, root = _fixture_guard((
        mc.Mutation("even numbers reported odd", "n % 2 == 0", "False", "fixture-odd"),
    ), selftest=NOISY_SELFTEST)
    mc.REPO = root
    try:
        _tick()
        try:
            problems = mc.run_guard(guard)
        except UnicodeDecodeError as exc:
            problems = []
            FAILURES.append(f"a non-UTF-8 byte in a mutant's output raised before the report printed: {exc}")
        report = next((p for p in problems if "not by the expected fixture" in p), "")
        tail = [l for l in report.split("\n")[1:] if l.startswith("      ")]
        if not (report and "exit 1" in report and tail):
            FAILURES.append(f"a wrong-fixture report does not carry the mutant's exit and output; got {problems}")
        _tick()
        tail_text = "\n".join(tail)
        # The clause on the TAIL, not the report: the header names the expected fixture
        # ('no mention of fixture-odd'), so a test of the whole report for it could never fail (#1532).
        if len(tail) != 12 or "noise-01" in tail_text or "noise-20" not in tail_text:
            FAILURES.append(f"a wrong-fixture report does not carry exactly the last 12 lines of output; "
                            f"got {len(tail)} line(s), first={tail[:1]}")
        _tick()
        if any(len(l) > 306 for l in tail):
            FAILURES.append("a wrong-fixture report does not cut each output line to 300 characters; "
                            f"widest {max(len(l) for l in tail)}")
    finally:
        mc.REPO = original_repo

    # ---- #1530-#1532: the three diagnostics a CI-only failure depends on ------------------------
    # (1) the tail is ONE interleaved stream. 13 stderr lines, then a label on stdout: the old
    # `stdout + stderr` put the label first and cut it, so the line naming what fired was the one
    # missing. (2) the INERT report is as width-bound as the wrong-fixture tail. (3) a TIMEOUT keeps
    # what the child printed before the limit, for the baseline and the mutant alike.
    labelled = SELFTEST.replace(
        '    sys.exit(1)\n',
        '    for i in range(13):\n        print(f"noise-{i:02d}", file=sys.stderr, flush=True)\n'
        '    print("label-on-stdout", flush=True)\n    sys.exit(1)\n', 1)
    assert labelled != SELFTEST
    guard, root = _fixture_guard((
        mc.Mutation("even numbers reported odd", "n % 2 == 0", "False", "fixture-odd"),
    ), selftest=labelled)
    mc.REPO = root
    try:
        _tick()
        report = next((p for p in mc.run_guard(guard) if "not by the expected fixture" in p), "")
        tail = [l.strip() for l in report.split("\n")[1:] if l.startswith("      ")]
        if not tail or tail[-1] != "label-on-stdout":
            FAILURES.append("a wrong-fixture tail hides a label printed to stdout behind 12+ stderr lines "
                            f"(stdout and stderr are not one interleaved stream); tail ends {tail[-2:]}")
    finally:
        mc.REPO = original_repo

    wide = 'import sys\nprint("w" * 5000)\nsys.exit(1)\n'
    guard, root = _fixture_guard((mc.Mutation("unused", "n % 2 == 0", "True", "fixture-odd"),), selftest=wide)
    mc.REPO = root
    try:
        _tick()
        inert = next((p for p in mc.run_guard(guard) if "INERT" in p), "")
        rows = inert.split("\n")[1:]
        if not rows or any(len(r) > 306 for r in rows):
            FAILURES.append("the INERT report does not cut each output line to 300 characters; "
                            f"widest {max((len(r) for r in rows), default=0)}")
    finally:
        mc.REPO = original_repo

    sleeper = 'import time\nprint("timeout-label", flush=True)\ntime.sleep(60)\n'
    guard, root = _fixture_guard((mc.Mutation("unused", "n % 2 == 0", "True", "fixture-odd"),), selftest=sleeper)
    mc.REPO = root
    original_baseline_timeout = mc.BASELINE_TIMEOUT
    try:
        _tick()
        timed_out = mc.run_mutation(guard, guard.mutations[0], timeout=2)
        if not any("timed out" in p and "timeout-label" in p for p in timed_out):
            FAILURES.append(f"a MUTANT's timeout report drops what it printed before the limit; got {timed_out}")
        _tick()
        mc.BASELINE_TIMEOUT = 2
        timed_out = mc.run_baseline(guard)
        if not any("timed out" in p and "timeout-label" in p for p in timed_out):
            FAILURES.append(f"a BASELINE's timeout report drops what it printed before the limit; got {timed_out}")
    finally:
        mc.BASELINE_TIMEOUT = original_baseline_timeout
        mc.REPO = original_repo

    # ---- 5. every real guard's anchors still match exactly once ------------------------
    # Without this the mutation list rots silently: an anchor that drifts raises at run time, but
    # only for whoever runs the checker. Asserting it here makes drift a selftest failure.
    for real_guard in mc.GUARDS:
        # Relative to the guard's BASE: a shipped guard's paths are plugin-relative (#1109).
        source = (original_repo / real_guard.base / real_guard.subject).read_text(encoding="utf-8")
        for mutation in real_guard.mutations:
            _tick()
            hits = source.count(mutation.old)
            if hits != 1:
                FAILURES.append(
                    f"{real_guard.name} / {mutation.name}: anchor matches {hits} time(s) in "
                    f"{real_guard.subject}, need exactly 1 — the mutation list has drifted"
                )

    # ---- 6. every guard names a real subject and selftest, and declares mutations ------
    # `subject` and `selftest` are scripts, so they must be FILES. `deps` and `needs` are staged
    # by copying, and #422 deliberately declared a DIRECTORY there ("a directory, so a new
    # reference doc is picked up rather than quietly missing") -- which `is_file()` then rejected,
    # leaving the fix that removed one vacuous guard failing this selftest. Existence is the real
    # rule for those two, and it still catches the typo this check exists for.
    for real_guard in mc.GUARDS:
        _tick()
        # `subject`, `selftest` and `deps` are Python modules that get IMPORTED, so they must be
        # files. `needs` is different: it means "stage this beside the mutant", and a guard whose
        # selftest reads a whole directory of fixtures must be able to declare the directory —
        # `build_coverage` needs all of `skills/design-system/references`, and naming files would
        # silently miss the next one added, which is the rot that made five guards inert.
        #
        # `dev` fixed this concurrently and let `deps` be a directory too. Kept the stricter form:
        # no guard declares a directory dep, so the two behave identically today, and a dep that
        # resolves to a directory could never be imported — it is a typo worth catching.
        missing = [p for p in (real_guard.subject, real_guard.selftest, *real_guard.deps)
                   if not (original_repo / real_guard.base / p).is_file()]
        missing += [p for p in real_guard.needs
                    if not (original_repo / real_guard.base / p).exists()]
        if missing:
            FAILURES.append(f"{real_guard.name}: declares paths that do not exist: {missing}")
        if not real_guard.mutations:
            FAILURES.append(
                f"{real_guard.name}: declares no mutations — a guard with an empty list passes "
                "vacuously, which is the failure this checker exists to prevent"
            )

        # ---- every SIBLING MODULE a staged file imports must itself be staged --------------
        # THE THIRD OCCURRENCE IS WHY THIS IS STRUCTURAL. Adding an import to a shipped module
        # orphans every neighbouring guard that stages it without the new dependency: the mutant
        # dies on ModuleNotFoundError, which is an ENVIRONMENTAL failure, not a caught mutation.
        # #1113 (six guards), #1114 (a seventh, missed because I matched on a shared literal) and
        # #1133's `validate_evidence` -> `evidence_app_tie` were all this, and all three surfaced
        # only in the 438-second sweep. Here it is about a second.
        for problem in mc.unstaged_sibling_imports(real_guard,
                                                   original_repo / real_guard.base):
            FAILURES.append(
                f"{real_guard.name}: {problem}. The mutant dies on ModuleNotFoundError, and an "
                f"environmental death is not a caught mutation.")
        _tick()

    # ---- 7. every RULE inside a multi-rule guard is backed by a mutation ----------------
    # The gap this closes: "mutation coverage" asserts every GUARD declares mutations, and the
    # lint_self_consistency guard already declared twelve. So a SEVENTH rule bolted onto that same
    # subject sailed through green with no mutation behind it (#100's `broken-doc-pointer`, caught
    # in review, not by a gate). A guard-level count cannot see a rule-level gap.
    #
    # Checked STRUCTURALLY — which function does each mutation's anchor live in, and which rules
    # does that function emit — rather than by matching fixture labels. `expects` is matched as a
    # substring of the whole selftest output (rule names included), so a label comparison both
    # misses real coverage and invents gaps. Ask the question the anchor can actually answer.
    import re as _re

    for guard in mc.GUARDS:
        subject = original_repo / guard.base / guard.subject
        if not subject.is_file():
            continue
        body = subject.read_text(encoding="utf-8")
        # Top-level function blocks, in source order.
        defs = [(m.start(), m.group(1)) for m in _re.finditer(r"^def (\w+)\(", body, _re.M)]
        if len(defs) < 2:
            continue
        bounds = [(name, s, defs[i + 1][0] if i + 1 < len(defs) else len(body))
                  for i, (s, name) in enumerate(defs)]

        def _owner(index: int) -> str | None:
            for name, s, e in bounds:
                if s <= index < e:
                    return name
            return None

        # rule name -> the functions that can emit it
        emitters: dict[str, set[str]] = {}
        for m in _re.finditer(r'Finding\(\s*\n?\s*"([a-z][a-z-]+)"', body):
            owner = _owner(m.start())
            if owner:
                emitters.setdefault(m.group(1), set()).add(owner)
        if not emitters:
            continue

        # functions with at least one mutation anchored inside them
        mutated: set[str] = set()
        for mutation in guard.mutations:
            index = body.find(mutation.old)
            if index != -1:
                owner = _owner(index)
                if owner:
                    mutated.add(owner)

        for rule in sorted(emitters):
            _tick()
            if not (emitters[rule] & mutated):
                FAILURES.append(
                    f"{guard.name}: rule {rule!r} is emitted by {sorted(emitters[rule])} and NO "
                    "declared mutation touches that function — nothing proves its fixtures would "
                    "fail if the rule broke. A guard-level mutation count cannot see this."
                )

    # ---- main's pool schedule (#1444): an INERT baseline ends its guard, unscored ------------
    _tick()
    inert = mc.Guard(name="inert", subject="s.py", selftest="t.py",
                     mutations=(mc.Mutation("i1", "a", "b", ""),))
    alive = mc.Guard(name="alive", subject="s.py", selftest="t.py",
                     mutations=(mc.Mutation("a1", "a", "b", ""), mc.Mutation("a2", "c", "d", "")))
    scheduled = [(g.name, m.name) for g, m in mc.live_mutations([inert, alive], [["INERT"], []])]
    if scheduled != [("alive", "a1"), ("alive", "a2")]:
        FAILURES.append(f"pool schedule: an INERT baseline must end its guard, and a passing one "
                        f"must run every mutation -- scheduled {scheduled}")

    # ---- the import-completeness rule, on a FIXTURE rather than on this repo ----------------
    # The loop above reads the real repo through `original_repo`, which inside a staged tempdir is
    # the tempdir -- so it iterates zero guards and every assertion about it passes vacuously. That
    # is the very defect this rule exists to catch, one level up, and it is why the rule is proved
    # here on a tree built for the purpose.
    fixture_base = Path(tempfile.mkdtemp(prefix="import-completeness-"))
    try:
        (fixture_base / "scripts").mkdir()
        (fixture_base / "scripts/leader.py").write_text(
            "import argparse\nimport follower\n\n\ndef go():\n    import lazy_one\n    return lazy_one\n",
            encoding="utf-8")
        (fixture_base / "scripts/follower.py").write_text("X = 1\n", encoding="utf-8")
        (fixture_base / "scripts/lazy_one.py").write_text("Y = 2\n", encoding="utf-8")
        bare = mc.Guard(name="fixture", subject="scripts/leader.py",
                        selftest="scripts/leader.py", mutations=())
        problems = mc.unstaged_sibling_imports(bare, fixture_base)
        _tick()
        if not any("follower" in p for p in problems):
            FAILURES.append("import-completeness: a module-scope sibling import must be reported")
        _tick()
        # THE CARVE-OUT, on the same fixture: a `def`-scope import is optional at load time, and
        # counting it flagged six correct guards on this rule's first run.
        if any("lazy_one" in p for p in problems):
            FAILURES.append("import-completeness: a function-scope import must NOT be reported")
        _tick()
        # ...and a stdlib import must never be reported, or the rule fires on `argparse` everywhere.
        if any("argparse" in p for p in problems):
            FAILURES.append("import-completeness: a stdlib import must NOT be reported")
        _tick()
        # THE CONTROL: declaring the dependency clears it. Without this the rule could be one that
        # reports every guard, which would also "catch" the mutation above.
        declared = mc.Guard(name="fixture", subject="scripts/leader.py",
                            selftest="scripts/leader.py", deps=("scripts/follower.py",),
                            mutations=())
        if mc.unstaged_sibling_imports(declared, fixture_base):
            FAILURES.append("import-completeness: a DECLARED dependency must clear the finding")
        _tick()
        # TRANSITIVE, through a `needs` FILE (#1444): check_slices -> check_mockup_gate (a need)
        # -> classify_door went INERT in CI because a one-level scan never read the need.
        (fixture_base / "scripts/follower.py").write_text("import grandchild\n", encoding="utf-8")
        (fixture_base / "scripts/grandchild.py").write_text("Z = 3\n", encoding="utf-8")
        via_need = mc.Guard(name="fixture", subject="scripts/leader.py",
                            selftest="scripts/leader.py", needs=("scripts/follower.py",),
                            mutations=())
        if not any("grandchild" in p for p in mc.unstaged_sibling_imports(via_need, fixture_base)):
            FAILURES.append("import-completeness: an import made BY a staged need must be reported")
        _tick()
        # A need NO staged file imports (run by path, as a subprocess) is still read: only the
        # `needs` seed reaches it, since no import edge leads there.
        (fixture_base / "scripts/runner.py").write_text("import solo\n", encoding="utf-8")
        (fixture_base / "scripts/solo.py").write_text("W = 4\n", encoding="utf-8")
        by_path = mc.Guard(name="fixture", subject="scripts/leader.py", selftest="scripts/leader.py",
                           deps=("scripts/follower.py", "scripts/grandchild.py"),
                           needs=("scripts/runner.py",), mutations=())
        if not any("solo" in p for p in mc.unstaged_sibling_imports(by_path, fixture_base)):
            FAILURES.append("import-completeness: a need no staged file imports must still be scanned")
        _tick()
        # TRANSITIVE proper: nothing declared, so follower is reported -- and so is what IT
        # imports, in the same run, instead of one missing file per round of fixing.
        if not any("grandchild" in p for p in mc.unstaged_sibling_imports(bare, fixture_base)):
            FAILURES.append("import-completeness: an unstaged import's own imports must be reported too")
        _tick()
        # ...and its control: staging the grandchild too clears it.
        both = mc.Guard(name="fixture", subject="scripts/leader.py", selftest="scripts/leader.py",
                        needs=("scripts/follower.py", "scripts/grandchild.py"), mutations=())
        if mc.unstaged_sibling_imports(both, fixture_base):
            FAILURES.append("import-completeness: a staged grandchild must clear the finding")
    finally:
        shutil.rmtree(fixture_base, ignore_errors=True)

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"mutation_check selftest: {CHECKS} checks passed")
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

