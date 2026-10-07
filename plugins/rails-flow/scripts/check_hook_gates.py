#!/usr/bin/env python3
"""Drive the rails-flow hook scripts end to end, under the environments that broke them.

The hooks are shell, and shell has no unit tests here: `bash -n` proves a script parses and nothing
proved what it DOES. That gap held five defects at once (#822-#826), found in one review, none of them
visible on the maintainer's machine:

  * `stop-gate.sh` handed a shell FUNCTION to the external `timeout` binary. Stock macOS ships no
    `timeout`, so the bare-function fallback ran and the gate looked fine; on every Linux box, CI
    runner and WSL it printed `exec: _rf_bundle: not found` and called that a RED suite.
  * `guard-lane.sh` normalised `/./` and not `..`, so a fail-closed guard had a one-segment hole.
  * `lint-ruby.sh` parsed RuboCop's summary for ` 0 offenses`, a string RuboCop never prints after
    correcting anything; and it used PATH's `bundle`, so under mise it silently never ran.
  * `self-consistency.sh` expanded `${CLAUDE_PLUGIN_ROOT}` bare under `set -u`.
  * `guard-bash.sh` anchored `-A` and `.` to the first argument of `git add`.

Every fixture below runs the REAL script -- never a reimplementation of its logic, which could not
witness the shell changing -- inside a throwaway directory, with stub binaries on PATH standing in
for `timeout`, `bundle` and friends. The stubs are the environments: a GNU-shaped `timeout` that
execs its argument, a `bundle` that passes, one that fails with RSpec's summary line, one that
aborts before RSpec starts. "Verify in the environment it runs in" is the whole lesson here.

Exit 0: every fixture holds.  Exit 1: a fixture failed (a hook regressed).  Exit 2: bad usage.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import uuid
import tempfile
import types
import time
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks" / "scripts"

FAILURES: list[str] = []
CHECKS = 0

# `--match SUBSTR` runs only the fixtures whose check label contains SUBSTR (#1599). The mutation harness runs
# every mutant of a guard through this file, and each mutant is meant to be caught by ONE fixture, named by the
# mutation's `expects`; re-running all 199 checks of a group (about 116 s) to see one of them fail was most of
# the mutation-coverage budget. Fixtures do not name themselves before they run, so it is two passes over a
# group: a SURVEY with every subprocess stubbed (it only records the check labels), then a RUN in which the
# code before a wanted check executes for real and the code before every other check is stubbed. A fixture
# whose result steers which checks follow it would make the two passes disagree; that raises, it never guesses.
_MATCH_MODE: str | None = None      # None, "survey" or "run"
_SURVEYED: list[str] = []           # the labels, in the order the survey saw them
_WANTED: set[int] = set()           # positions in `_SURVEYED` whose label matched
_INDEX = 0                          # the position the next check() call has in the run pass
_SKIP = False                       # True while the code before an unwanted check runs


class MatchSequenceError(Exception):
    """The run pass reached a different check than the survey did, so `--match` cannot be trusted here."""


# A label that carries a temp path differs between the survey and the run, because each pass makes its own directory, so
# `--match` would refuse the group. The path is MASKED for the comparison, including a name a label cut short (`cmd[:40]` in
# a label ends mid-name when the directory is short, as `/tmp` is on a Linux runner and `/private/var/folders/...` is not on
# a Mac: a group that surveyed clean on a laptop was refused in CI, #1596). Failures still print the label as written.
_TEMP_PATH = re.compile(r"/\S*?/tmp\w+")


def _stable(label: str) -> str:
    return _TEMP_PATH.sub("<tmp>", label)


def skipping() -> bool:
    return _MATCH_MODE == "survey" or (_MATCH_MODE == "run" and _SKIP)


# A group whose fixtures build shared state as they go (repositories, commits, stamps) cannot have that setup stubbed with the
# rest: the one wanted check would then run against nothing. `@real_setup` keeps every subprocess REAL under `--match`
# except the hook itself, which is the cost the narrowing exists to avoid (#1592).
_REAL_SETUP = False


def real_setup(fn):
    def wrapper(*a, **k):
        global _REAL_SETUP
        _REAL_SETUP = True
        try:
            return fn(*a, **k)
        finally:
            _REAL_SETUP = False
    wrapper.__name__ = fn.__name__
    return wrapper


def check(label: str, ok: bool, detail: str = "") -> None:
    global CHECKS, _INDEX, _SKIP
    if _MATCH_MODE == "survey":
        _SURVEYED.append(_stable(label))
        return
    if _MATCH_MODE == "run":
        if _INDEX >= len(_SURVEYED) or _SURVEYED[_INDEX] != _stable(label):
            raise MatchSequenceError(
                f"check #{_INDEX} is {label!r} in the run pass but "
                f"{_SURVEYED[_INDEX] if _INDEX < len(_SURVEYED) else 'absent'!r} in the survey")
        live = _INDEX in _WANTED
        _INDEX += 1
        _SKIP = _INDEX not in _WANTED        # the code before the NEXT check runs for real only if it is wanted
        if not live:
            return
    CHECKS += 1
    if not ok:
        FAILURES.append(f"{label}: {detail}" if detail else label)


def record_failure(note: str) -> None:
    """A failure that is not one of a group's numbered checks (a timeout), so it never shifts `--match`'s count."""
    global CHECKS
    CHECKS += 1
    FAILURES.append(note)


# #1469: every hook fixture runs through here. A subprocess that outruns its timeout used to raise
# TimeoutExpired and CRASH this script, so the fixtures after it never printed. Under the mutation
# harness's parallel load that read as "caught, but not by the expected fixture" on one run in a few:
# a flake with nothing wrong in the code. Now a timeout is exit 124 with a TIMEOUT line, the fixture
# that ran it fails by name, and every later fixture still runs. HOOK_GATES_TIMEOUT overrides the
# bound (the selftest sets it tiny to prove the no-crash path).
_EXPECTING_TIMEOUT = False      # set by timeout_fixtures, which times out on purpose, and the #1504 cost check


# A HOOK'S WALL BUDGET SCALES WITH THE MACHINE (#1638). Every subprocess a fixture starts gets a wall-clock bound, 180 s at least. Measured on an
# idle machine the longest single subprocess of the `deadline` group takes under 8 s (the whole group 22 s), so 180 s is twenty times the need;
# yet on a shared machine at load 12 to 80 a mutation baseline of `hook_guard_bash_deadline` hit it ("TIMEOUT after 180.0s: release-gate.sh") and the
# guard read as INERT: a correct tree reported as broken. The bound cannot be CPU time: a hung hook sleeps and uses none, so a CPU bound would never
# fire, which is the 30-minute hang #1469 closed. It is the same wall bound, scaled by how much slower than idle THIS machine is right now: a fixed
# calibration workload (a `git init` and an empty commit in a throwaway repository, the work every fixture starts with) is timed against its idle
# figure, as the mutation harness times a baseline and scales each mutant's limit from it (`mutation_check.mutation_timeout`).
HOOK_BUDGET_FLOOR = 180.0       # seconds, on an idle machine
HOOK_BUDGET_CAP = 600.0         # never more than ten minutes: the doctor's per-gate budgets (400 to 900 s) decide beyond that, so a larger bound would be a dead number
CALIBRATION_IDLE = 0.06         # seconds the calibration workload takes on an idle machine (measured 0.056, median of nine)
CALIBRATION_REFRESH = 30.0      # re-measured at most this often: load moves, and a measurement per subprocess would be the load
_CALIBRATION = {"at": None, "slowdown": 1.0}


def hook_limit(requested: float, slowdown: float) -> float:
    """The wall bound for one subprocess: a fixture's own bound, raised to the floor, then scaled by the machine's slowdown up to the cap.

    Never below the floor or the fixture's own bound, and never raised past the cap unless the fixture asked for more itself."""
    base = max(float(requested or 0), HOOK_BUDGET_FLOOR)
    return max(base, min(HOOK_BUDGET_CAP, base * max(1.0, slowdown)))


CALIBRATION_SAMPLES = 3         # the median of three, so one stall (a lock, an exec held up) does not set the budget for a whole refresh window
CALIBRATION_TIMEOUT = 60        # each calibration command is itself bounded: a calibration that hangs would be the hang it guards against (#1469)


def _sample() -> float:
    """Seconds ONE run of the calibration workload took here; the cap's worth of slowdown if it would not finish."""
    with tempfile.TemporaryDirectory() as td:
        began = time.monotonic()
        try:
            for cmd in (["git", "init", "-q"], ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "i"],
                        ["bash", "-c", "true"]):
                subprocess.call(cmd, cwd=td, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=CALIBRATION_TIMEOUT)
        except (OSError, subprocess.SubprocessError):
            return CALIBRATION_IDLE * (HOOK_BUDGET_CAP / HOOK_BUDGET_FLOOR)
        return time.monotonic() - began


def _calibrate(sample=_sample) -> float:
    """The median of CALIBRATION_SAMPLES runs of the calibration workload: one outlier among calm samples is ignored."""
    runs = sorted(sample() for _ in range(CALIBRATION_SAMPLES))
    return runs[len(runs) // 2]


def machine_slowdown(measure=_calibrate, now=time.monotonic) -> float:
    """How many times slower than idle this machine is, at least 1, measured at most once per CALIBRATION_REFRESH."""
    t = now()
    if _CALIBRATION["at"] is None or t - _CALIBRATION["at"] >= CALIBRATION_REFRESH:
        _CALIBRATION["slowdown"] = max(1.0, measure() / CALIBRATION_IDLE)
        _CALIBRATION["at"] = t
    return _CALIBRATION["slowdown"]


def _is_hook_run(args) -> bool:
    """The hook itself, as opposed to the git and gh the fixtures set up around it."""
    argv = args[0] if args else []
    return isinstance(argv, (list, tuple)) and any("release-gate.sh" in str(a) for a in argv)


def gate_exit(returncode: int, stderr: bytes) -> int:
    """A release gate's exit code as a FIXTURE should read it. The gate's own deadline also exits 2 ("the gate took longer than 13s"), which on a loaded
    machine reads as the refusal a fixture is looking for and lets a mutant survive for the wrong reason: it is 124 here, equal to neither 0 nor 2."""
    return 124 if b"took longer than" in stderr else returncode


def _run(*args, **kw):
    if skipping() and not (_REAL_SETUP and not _is_hook_run(args)):     # `--match`: the code before an unwanted check, or the survey (#1599)
        text = kw.get("text") or kw.get("universal_newlines")
        empty = "" if text else b""
        return subprocess.CompletedProcess(args[0] if args else kw.get("args"), 0, stdout=empty, stderr=empty)
    # The override is exact (the no-crash proof sets it tiny); otherwise a fixture's own bound is raised to the floor and scaled by how much slower than
    # idle this machine is (`hook_limit`, #1638): 60 s was what a loaded machine outran, and a fixed 180 s is outrun at load 12 to 80 too. Read per call.
    override = os.environ.get("HOOK_GATES_TIMEOUT")
    requested = kw.pop("timeout", 0)
    limit = float(override) if override else hook_limit(requested, machine_slowdown())
    kw.pop("timeout", None)
    # Its OWN process group, so a timeout kills the hook AND the stubs it started. subprocess.run
    # kills only the direct child; measured 2026-09-29, 43 stub processes were left orphaned and
    # stuck (macOS held their exec at _dyld_start), piling up across runs.
    want_check = kw.pop("check", False)
    data = kw.pop("input", None)
    if kw.pop("capture_output", False):
        kw["stdout"], kw["stderr"] = subprocess.PIPE, subprocess.PIPE
    if data is not None:
        kw["stdin"] = subprocess.PIPE
    with subprocess.Popen(*args, start_new_session=True, **kw) as proc:
        try:
            out, err = proc.communicate(data, timeout=limit)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            # Bounded: a process that LEFT the group (its own setsid) would otherwise hold the pipe
            # and bring the hang back. After a short wait, stop reading.
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                for pipe in (proc.stdin, proc.stdout, proc.stderr):
                    if pipe:
                        pipe.close()
            note = f"TIMEOUT after {limit}s (floor {HOOK_BUDGET_FLOOR:g}s, machine {_CALIBRATION['slowdown']:.1f}x slower than idle): {proc.args}"
            # A timeout is ALWAYS a recorded failure -- a setup step (`git init`, check=True) that
            # times out must not pass silently -- unless timeout_fixtures asked for one on purpose.
            if not _EXPECTING_TIMEOUT:
                record_failure(note)
            empty = "" if kw.get("text") else b""
            return subprocess.CompletedProcess(proc.args, 124, stdout=empty,
                                               stderr=note if kw.get("text") else note.encode())
        done = subprocess.CompletedProcess(proc.args, proc.returncode, stdout=out, stderr=err)
        if want_check:
            done.check_returncode()
        return done


def _stub(dirpath: Path, name: str, body: str) -> None:
    f = dirpath / name
    f.write_text("#!/bin/sh\n" + body.rstrip("\n") + "\n")
    f.chmod(0o755)


# A GNU-coreutils-shaped `timeout`: `timeout SECS CMD ARGS…` execs CMD. Faithful in the one respect
# that matters -- it can only exec a real executable, never a shell function -- and it also mimics
# GNU's wording when the command does not exist, since that wording is what the old denylist missed.
GNU_TIMEOUT = '''secs="$1"; shift
if ! command -v "$1" >/dev/null 2>&1; then
  echo "timeout: failed to run command '$1': No such file or directory" >&2; exit 127
fi
exec "$@"'''


def _git_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for cmd in (["git", "init", "-q"],
                ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q",
                 "--allow-empty", "-m", "init"]):
        _run(cmd, cwd=root, check=True, capture_output=True)


def run_hook(name: str, *, cwd: Path, stdin: str, path_prefix: list[Path] = (),
             env_extra: dict[str, str] | None = None, unset: tuple[str, ...] = (),
             shell: str = "bash") -> tuple[int, str]:
    env = dict(os.environ)
    for k in unset:
        env.pop(k, None)
    env.pop("RAILS_FLOW_LANE", None)
    for k in [k for k in env if k.startswith(("GIT_", "GH_"))]:
        env.pop(k, None)                    # a git hook's GIT_DIR, a CI's GH_*: each would route every fixture
    if path_prefix:
        env["PATH"] = os.pathsep.join(str(p) for p in path_prefix) + os.pathsep + env["PATH"]
    if env_extra:
        env.update(env_extra)
    done = _run([shell, str(HOOKS / name)], cwd=cwd, input=stdin, env=env,
                          capture_output=True, text=True, timeout=60)
    return done.returncode, done.stdout + done.stderr


# ---- stop-gate.sh (#822) ------------------------------------------------------------------------
def stop_gate_fixtures() -> None:
    def scenario(*, timeout_present: bool, bundle_body: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td) / "repo"
            _git_repo(repo)
            (repo / "spec").mkdir()
            (repo / "spec" / "x_spec.rb").write_text("describe 'x' do; end\n")  # uncommitted
            stubs = Path(td) / "bin"
            stubs.mkdir()
            _stub(stubs, "bundle", bundle_body)
            if timeout_present:
                _stub(stubs, "timeout", GNU_TIMEOUT)
            return run_hook("stop-gate.sh", cwd=repo, stdin="{}", path_prefix=[stubs])

    passing = 'echo "1 example, 0 failures"; exit 0'
    failing = 'echo "Failures:"; echo "  1) x"; echo "2 examples, 1 failure"; exit 1'
    aborting = 'echo "Could not locate Gemfile"; exit 10'

    # THE #822 SHAPE: a timeout binary on PATH, a passing suite. This exited 2 with "RED".
    code, out = scenario(timeout_present=True, bundle_body=passing)
    check("stop-gate: a PASSING suite under a real `timeout` binary lets the stop proceed",
          code == 0, f"exit {code}: {out.strip()[:160]!r}")
    check("...and does not mention a missing function",
          "_rf_bundle" not in out and "not found" not in out, f"{out.strip()[:160]!r}")

    code, out = scenario(timeout_present=True, bundle_body=failing)
    check("stop-gate: a FAILING suite under `timeout` blocks", code == 2, f"exit {code}")
    check("...and is called RED, because RSpec's summary line is present",
          "RED" in out, f"{out.strip()[:160]!r}")

    code, out = scenario(timeout_present=True, bundle_body=aborting)
    check("stop-gate: a suite that never STARTED still blocks", code == 2, f"exit {code}")
    check("...and is called an environment problem, not a red suite -- no summary line, no verdict",
          "could not RUN" in out and "RED" not in out, f"{out.strip()[:200]!r}")

    code, out = scenario(timeout_present=False, bundle_body=passing)
    check("stop-gate: the no-timeout (stock macOS) path still passes a green suite",
          code == 0, f"exit {code}: {out.strip()[:160]!r}")


# ---- guard-lane.sh (#823) -----------------------------------------------------------------------
def guard_lane_fixtures() -> None:
    def write(path: str, lane: str | None) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            payload = json.dumps({"tool_input": {"file_path": path}})
            extra = {"RAILS_FLOW_LANE": lane} if lane else None
            return run_hook("guard-lane.sh", cwd=Path(td), stdin=payload, env_extra=extra)

    code, _ = write("app/models/user.rb", "app/models")
    check("guard-lane: a write INSIDE the lane passes", code == 0, f"exit {code}")
    code, _ = write("config/routes.rb", "app/models")
    check("guard-lane: a write OUTSIDE the lane is blocked", code == 2, f"exit {code}")
    # THE #823 SHAPE.
    code, out = write("app/models/../../config/routes.rb", "app/models")
    check("guard-lane: a `..` escape is blocked", code == 2, f"exit {code}: {out.strip()[:120]!r}")
    check("...and the message names `..`, so the reader knows why a lane-prefixed path was refused",
          "'..'" in out, f"{out.strip()[:160]!r}")
    code, _ = write("app/models/../../config/routes.rb", None)
    check("guard-lane: with NO lane assigned nothing is policed, `..` included -- dormant means dormant",
          code == 0, f"exit {code}")


# ---- guard-migrate.sh (#1362) --------------------------------------------------------------------
def guard_migrate_fixtures() -> None:
    def write(file_path_fn, *, rails: bool = True, existing: str | None = None) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            (proj / "db" / "migrate").mkdir(parents=True)
            if rails:
                (proj / "bin").mkdir()
                (proj / "bin" / "rails").write_text("#!/usr/bin/env ruby\n")
            if existing:
                target = proj / existing
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("class Existing < ActiveRecord::Migration[7.1]; end\n")
            file_path = file_path_fn(proj)
            payload = json.dumps({"tool_input": {"file_path": file_path}, "cwd": str(proj)})
            return run_hook("guard-migrate.sh", cwd=proj, stdin=payload,
                            unset=("CLAUDE_PROJECT_DIR",))

    # THE BLOCKED SHAPE, both ways a path arrives: relative and absolute.
    code, out = write(lambda p: "db/migrate/20260927120000_add_thing.rb")
    check("guard-migrate: creating a NEW migration by a RELATIVE path is blocked",
          code == 2, f"exit {code}: {out.strip()[:160]!r}")
    check("...and the message steers to the generator", "bin/rails generate migration" in out, out.strip()[:200])
    check("...and says a broken boot comes first, since the generator needs the app to boot (#1416)",
          "does not boot" in out, out.strip()[-200:])
    code, _ = write(lambda p: str(p / "db" / "migrate" / "20260927120000_add_thing.rb"))
    check("guard-migrate: creating a NEW migration by an ABSOLUTE path is blocked", code == 2, f"exit {code}")
    # #1416. On a case-insensitive filesystem (macOS, Windows) this path LANDS in db/migrate/.
    code, _ = write(lambda p: "DB/Migrate/20260927120000_add_thing.rb")
    check("guard-migrate (#1416): a mixed-case DB/Migrate/ path is blocked", code == 2, f"exit {code}")
    code, _ = write(lambda p: "db/migrate/20260927120000_add_thing.RB")
    check("guard-migrate (#1416): a `.RB` extension is blocked", code == 2, f"exit {code}")
    # The existence check uses the path AS GIVEN, so a mixed-case OVERWRITE is allowed on any
    # filesystem when the file exists at that literal path (a later `exists(path.lower())` would deny
    # this on case-sensitive CI).
    code, _ = write(lambda p: "DB/Migrate/20260101000000_existing.rb",
                    existing="DB/Migrate/20260101000000_existing.rb")
    check("guard-migrate (#1416): CONTROL: overwriting a file that exists at the mixed-case path is allowed",
          code == 0, f"exit {code}")

    def via_symlink() -> int:
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            (proj / "db" / "migrate").mkdir(parents=True)
            (proj / "bin").mkdir()
            (proj / "bin" / "rails").write_text("#!/usr/bin/env ruby\n")
            (proj / "db" / "mig").symlink_to("migrate")
            payload = json.dumps({"tool_input": {"file_path": "db/mig/20260927120000_add_thing.rb"}, "cwd": str(proj)})
            return run_hook("guard-migrate.sh", cwd=proj, stdin=payload, unset=("CLAUDE_PROJECT_DIR",))[0]
    code = via_symlink()
    check("guard-migrate (#1416): a Write through a symlink into db/migrate/ is blocked", code == 2, f"exit {code}")

    # CONTROL, existence: the identical path, but the file already exists -- Write is an overwrite,
    # not a creation, and stays allowed.
    code, _ = write(lambda p: "db/migrate/20260101000000_existing.rb",
                    existing="db/migrate/20260101000000_existing.rb")
    check("guard-migrate: CONTROL: overwriting an EXISTING migration via Write is allowed",
          code == 0, f"exit {code}")
    code, _ = write(lambda p: str(p / "db" / "migrate" / "20260101000000_existing.rb"),
                    existing="db/migrate/20260101000000_existing.rb")
    check("guard-migrate: CONTROL: ...the same holds for the absolute-path form", code == 0, f"exit {code}")

    # CONTROL, directory: an ordinary write elsewhere is untouched.
    code, _ = write(lambda p: "app/models/x.rb")
    check("guard-migrate: CONTROL: a write elsewhere (app/models/x.rb) is allowed", code == 0, f"exit {code}")

    # CONTROL, extension: a non-`.rb` file in db/migrate/ (a fixture, a README) is not a migration.
    code, _ = write(lambda p: "db/migrate/notes.txt")
    check("guard-migrate: CONTROL: a non-`.rb` file in db/migrate/ is allowed", code == 0, f"exit {code}")

    # CONTROL, project kind: the identical new-migration path, in a project with no bin/rails.
    code, _ = write(lambda p: "db/migrate/20260927120000_add_thing.rb", rails=False)
    check("guard-migrate: CONTROL: the identical write in a NON-RAILS project is allowed",
          code == 0, f"exit {code}")

    # THE DOCUMENTED LIMIT (verified 2026-09-27): a custom `migrations_paths` in database.yml
    # (Rails multi-database support) is not read here, so a non-existent file under a directory
    # that is NOT the literal `db/migrate/` -- even one that looks purpose-built, like
    # `db/animals_migrate/` -- is allowed. Reading database.yml was judged out of scope.
    code, _ = write(lambda p: "db/animals_migrate/20260101000000_x.rb")
    check("guard-migrate: KNOWN LIMIT: a custom migrations_paths directory (db/animals_migrate/) "
          "is not covered and is allowed", code == 0, f"exit {code}")

    # FAIL CLOSED, SCOPED: an unparsable payload. Judged on the raw text alone, paired on the one
    # thing that differs -- whether a db/migrate/*.rb path appears in it at all.
    def raw(stdin: str) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            (proj / "db" / "migrate").mkdir(parents=True)
            (proj / "bin").mkdir()
            (proj / "bin" / "rails").write_text("#!/usr/bin/env ruby\n")
            return run_hook("guard-migrate.sh", cwd=proj, stdin=stdin, unset=("CLAUDE_PROJECT_DIR",))

    code, _ = raw("not json, but it mentions db/migrate/20260927120000_add_thing.rb in passing")
    check("guard-migrate: an UNPARSABLE payload naming a db/migrate/*.rb path is blocked",
          code == 2, f"exit {code}")
    code, _ = raw("not json, and names no migration path at all")
    check("guard-migrate: CONTROL: an unparsable payload naming NO db/migrate path is allowed",
          code == 0, f"exit {code}")

    # THE DEGRADED ENVIRONMENT ITSELF: PATH holds only bash and cat -- no python3, and no grep. The
    # fallback once piped to grep, and "grep: command not found" is a non-match, so this exact shape
    # ALLOWED a new migration while claiming to fail closed. PATH is replaced, not prefixed, or the
    # host's python3 would answer and the fallback would never run.
    def bare(file_path: str, bash: str | None = None) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            (proj / "db" / "migrate").mkdir(parents=True)
            (proj / "bin").mkdir()
            (proj / "bin" / "rails").write_text("#!/usr/bin/env ruby\n")
            only = Path(td) / "only"
            only.mkdir()
            for tool in ("bash", "cat"):
                (only / tool).symlink_to(bash if (tool == "bash" and bash) else shutil.which(tool))
            done = _run([str(only / "bash"), str(HOOKS / "guard-migrate.sh")], cwd=proj,
                                  input=json.dumps({"tool_input": {"file_path": file_path}}),
                                  env={"PATH": str(only)}, capture_output=True, text=True, timeout=60)
            return done.returncode, done.stdout + done.stderr

    code, out = bare("db/migrate/20260927120000_add_thing.rb")
    check("guard-migrate: with NEITHER python3 NOR grep on PATH, a new migration is still blocked",
          code == 2, f"exit {code}: {out.strip()[:160]!r}")
    code, out = bare("DB/Migrate/20260927120000_add_thing.rb")
    check("guard-migrate (#1416): the bare-PATH fallback folds case too (nocasematch)",
          code == 2, f"exit {code}: {out.strip()[:160]!r}")
    code, out = bare("db\\migrate\\20260927120000_add_thing.rb")
    check("guard-migrate (#1416): the bare-PATH fallback accepts a Windows backslash separator",
          code == 2, f"exit {code}: {out.strip()[:160]!r}")
    # bash 3.2 (macOS /bin/bash) is the shell with no ${var,,}; prove the fold THERE when it is present.
    legacy = Path("/bin/bash")
    if legacy.is_file() and _run([str(legacy), "-c", "echo ${BASH_VERSINFO[0]}"],
                                           capture_output=True, text=True).stdout.strip() == "3":
        code, out = bare("DB/Migrate/20260927120000_add_thing.rb", bash=str(legacy))
        check("guard-migrate (#1416): ...and under bash 3.2 itself (/bin/bash)", code == 2,
              f"exit {code}: {out.strip()[:160]!r}")
    code, _ = bare("app/models/x.rb")
    check("guard-migrate: CONTROL: ...and the same bare PATH still allows a write elsewhere",
          code == 0, f"exit {code}")

    # WIRED SCOPE: hooks.json must route this hook from `Write` alone. `Edit`/`MultiEdit` cannot
    # create a file, so there is no creation moment for either of them to carry into this hook.
    manifest = json.loads((HOOKS.parent / "hooks.json").read_text(encoding="utf-8"))
    matchers = [entry.get("matcher") for entry in manifest.get("hooks", {}).get("PreToolUse", [])
                for hook in entry.get("hooks", []) if "guard-migrate.sh" in hook.get("command", "")]
    check("guard-migrate: hooks.json wires it to exactly one PreToolUse entry, matcher `Write`",
          matchers == ["Write"], f"found matcher(s) {matchers!r}")


# ---- lint-ruby.sh (#824) ------------------------------------------------------------------------
def lint_ruby_fixtures() -> None:
    def edit(rubocop_body: str, *, with_mise: bool = False) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "proj"
            proj.mkdir()
            (proj / "a.rb").write_text("puts 1\n")
            stubs = Path(td) / "bin"
            stubs.mkdir()
            working = 'case "$*" in *--version*) echo "1.80.0"; exit 0;; esac\n' + rubocop_body
            if not with_mise:
                # `bundle exec rubocop --version` must succeed; `bundle exec rubocop -a …` prints the body.
                _stub(stubs, "bundle", working)
            else:
                # The mise shape: PATH's `bundle` is the wrong Ruby's and FAILS; the working one lives
                # off PATH and is reachable only through `mise exec -- bundle`. A hook that ignores
                # mise therefore exits 0 without running, which is exactly the #824 symptom.
                (proj / ".ruby-version").write_text("3.4.1\n")
                rubybin = Path(td) / "rubybin"
                rubybin.mkdir()
                _stub(rubybin, "bundle", working)
                _stub(stubs, "bundle", 'echo "bundle: command not found" >&2; exit 127')
                _stub(stubs, "mise", 'case "$1" in current) exit 0;; exec) shift; shift; '
                                     f'[ "$1" = bundle ] && shift && exec "{rubybin}/bundle" "$@";; esac; exit 1')
            payload = json.dumps({"tool_input": {"file_path": str(proj / "a.rb")}})
            return run_hook("lint-ruby.sh", cwd=proj, stdin=payload, path_prefix=[stubs])

    # THE #824 SHAPE: everything corrected; the summary counts the corrected offenses as detected.
    corrected = ('echo "== a.rb =="; echo "C:  1:  1: [Corrected] Style/FrozenStringLiteralComment: Missing."; '
                 'echo ""; echo "1 file inspected, 1 offense detected, 1 offense autocorrected"; exit 1')
    code, out = edit(corrected)
    check("lint-ruby: a file whose only offense was CORRECTED passes",
          code == 0, f"exit {code}: {out.strip()[:160]!r}")

    remaining = ('echo "== a.rb =="; echo "C:  1:  1: [Corrected] Style/FrozenStringLiteralComment: Missing."; '
                 'echo "W:  2:  3: [Correctable] Lint/UselessAssignment: Useless assignment to x."; '
                 'echo ""; echo "1 file inspected, 2 offenses detected, 1 offense autocorrected"; exit 1')
    code, out = edit(remaining)
    check("lint-ruby: an offense that REMAINS after -a blocks", code == 2, f"exit {code}")
    check("...naming how many remain, not how many were detected",
          "1 offense(s)" in out, f"{out.strip()[:160]!r}")
    check("...and listing the remaining one, not the corrected one",
          "UselessAssignment" in out and "FrozenStringLiteral" not in out, f"{out.strip()[:200]!r}")

    clean = 'echo ""; echo "1 file inspected, no offenses detected"; exit 0'
    code, _ = edit(clean)
    check("lint-ruby: a clean file passes", code == 0, f"exit {code}")

    code, out = edit(remaining, with_mise=True)
    check("lint-ruby: under mise with a pinned Ruby the hook RUNS (it used to exit 0 unconditionally)",
          code == 2 and "UselessAssignment" in out, f"exit {code}: {out.strip()[:160]!r}")


# ---- self-consistency.sh (#825) -----------------------------------------------------------------
def self_consistency_fixtures() -> None:
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td)
        (proj / "a.rb").write_text("puts 1\n")
        payload = json.dumps({"tool_input": {"file_path": str(proj / "a.rb")}})
        code, out = run_hook("self-consistency.sh", cwd=proj, stdin=payload, unset=("CLAUDE_PLUGIN_ROOT",))
    check("self-consistency: with CLAUDE_PLUGIN_ROOT unset the hook exits 0, not `unbound variable`",
          code == 0 and "unbound" not in out, f"exit {code}: {out.strip()[:120]!r}")


# ---- guard-bash.sh (#826, #906) -----------------------------------------------------------------
NEGATIVES_906 = ['grep -ciE "git add -A" GUARDRAILS.md', 'echo "never git add -A"', 'git commit -m "docs: state the no \'git add -A\' rule"', '# git add -A', 'gh issue list --search "git add -A" --state all', 'for k in "force-push" "git add -A" "no-verify"; do printf "  %-24s %s\\n" "$k" "$(grep -ciE "$k" GUARDRAILS.md)"; done', 'echo "--no-verify"', 'grep db:reset lib/tasks/x.rake', 'echo "git reset --hard is bad"', 'git commit -m "wip; git add -A comes later"']
POSITIVES_906 = ['FOO=1 git add -A', 'sudo git add .', 'git status && git add -A', 'git -C repo add -A', 'git commit --no-verify -m x', 'bin/rails db:reset', 'git push --force origin main', 'git reset --hard HEAD~1',
                 # #1342: the other ways git discards work with no undo
                 'git clean -fd', 'git checkout .', 'git checkout -- app/x.rb', 'git checkout main -- app/x.rb',
                 'git restore .', 'git branch -D feature/x', 'git stash drop', 'git stash clear']
# #1342 safe twins: each must stay allowed, or the new rules block the recovery they point to.
NEGATIVES_1342 = ['git clean -n', 'git clean -fdn', 'git checkout feature/x', 'git checkout -b new',
                  'git restore -- app/x.rb', 'git restore --staged .', 'git restore --source origin/dev --staged --worktree -- docs/a.md',
                  'git branch -d feature/x', 'git stash push -m wip', 'git stash list', "grep 'git stash drop' notes.md"]
# #1472: a command the shell RUNS from inside a string, a wrapper or a group, or git spelled another
# way. The normaliser never classified any of these, so every guard-bash rule was blind to them.
POSITIVES_1472 = ["bash -c 'git add -A'", 'sh -c "git push --force origin main"', "bash -lc 'git reset --hard'",
                  "bash -o pipefail -c 'git add -A'", "zsh -c -- 'git add -A'", 'eval "git add -A"', "eval 'git add' '-A'",
                  "bash -c \"eval 'git add -A'\"", 'echo "$(git add -A)"', 'echo `git add -A`', 'diff <(git add -A) x',
                  'command git add -A', 'exec git add -A', 'time git add -A', 'nice -n 5 git add -A', 'env -i git add -A',
                  'sudo -u deploy git add -A', 'timeout 60 git add -A', 'echo x | xargs git add -A', '{ git add -A; }',
                  '( git add -A )', '(git add -A)', 'if true; then git add -A; fi', '\\git add -A', '/usr/bin/git add -A',
                  'git.exe add -A', 'git --no-pager add -A', 'git --attr-source HEAD add -A',
                  'git -c alias.p=push p --force origin main', "bash >log -c 'git add -A'",
                  "echo x; bash -c 'git add -A'", 'true && eval "git add -A"',
                  # #1498 review: a trigger spelled with quotes or a backslash is still eval / bash.
                  "e'v'al \"git add -A\"", "e''val 'git add -A'", 'ev\\al "git add -A"',
                  "ba's'h -c 'git add -A'", "bas\\h -c 'git add -A'", '"ba""s"h -c \'git add -A\'',
                  # ...and a heredoc inside $( ) that never closes cannot hide the command after it.
                  "echo \"$(cat <<EOF\n1) x\n)\"\nbash -c 'git add -A'"]
# ...and each one's twin: the same shape doing something allowed, or a string that only MENTIONS it.
NEGATIVES_1472 = ["bash -c 'git add app/x.rb'", "bash -c 'git push origin feature/x'", 'eval "git status"',
                  'echo "$(git branch --show-current)"', 'command -v git', 'time git status', 'git --no-pager log -1',
                  'git --attr-source HEAD status', 'git -c alias.p=push p origin feature/x', 'sudo -u deploy git status',
                  'echo "bash -c \'git add -A\'"', 'git commit -m "never bash -c \'git add -A\'"',
                  "echo 'eval \"git add -A\"'", "bash script.sh -c 'git add -A'",
                  "cat <<'X' > s.sh\nbash -c 'git add -A'\nX\ngit status",
                  "git commit -m \"$(cat <<'EOF'\nwhy: never git add -A\nEOF\n)\"",
                  # #1472 review: a `)` inside a heredoc inside $( ) must not end the substitution early.
                  "gh pr create --title t --body \"$(cat <<'EOF'\n1) don't run `git add -A`\nEOF\n)\"",
                  "git commit -m \"$(cat <<'EOF'\na) first\nb) never `git push --force`\nEOF\n)\"",
                  "echo \"$(cat <<'EOF'\nAdds :) emoji then `git add -A`\nEOF\n)\""]

# #1613: ANSI-C quoting, `$'...'`, spells the verb, the subcommand or the flag; the shell decodes it and runs the command, and the normaliser
# printed the quotes' CONTENT as it was written, so no rule matched. Each decodes (here, in bash) to a command that stages everything.
POSITIVES_1613 = ["$'\\x67\\x69\\x74' add -A", "git $'\\x61dd' -A", "git add $'\\x2dA'", "git add $'\\055A'", "git add $'\\u002dA'",
                  "git $'a\\x64d' -A", "git $'\\x70ush' --force origin main", "git add -$'\\x41'"]
# #1568: the other spellings of the same words that the sed-based quote strip read as a MENTION, plus the continuation and heredoc shapes
# the shell reads differently from the normaliser (each measured against bash with git stubbed: bash ran the command, the hook said nothing).
POSITIVES_1568 = ['git add "-A"', "git add '.'", "git 'add' -A", '"git" add -A', 'git push "--force" origin main', "git 'reset' --hard",
                  'git add\\\n -A', 'g\\\nit add -A', 'g\\it add -A', 'gi\\t add -A', 'git a\\dd -A', 'git add \\-A', 'git add -\\A',
                  'echo $((1<<2))\ngit add -A', 'echo $(( 1 << 2 ))\ngit add -A',
                  'cat <<EOF\r\nx\r\nEOF\r\ngit add -A', "cat <<'EOF'\nfoo\\\nEOF\ngit add -A",
                  'echo "a\'b"; git add -A; echo "c\'d"']
# ...and the twins that must stay allowed: the same words only MENTIONED, quoted spans holding spaces, and the shapes bash reads as text.
NEGATIVES_1568 = ['git add "app/x.rb" "spec/y.rb"', "git add 'x y' app/z.rb", 'git commit -m "git add -A"', "echo $'git add -A'",
                  "git add $'a\\x20b' app/z.rb", 'echo "$((1<<2))"', 'echo $((1<<2))\ngit status',
                  'cat <<EOF\nfoo\\\nEOF\ngit add -A\nEOF', 'cat <<-EOF\n\tfoo\\\n\tEOF\ngit add -A\nEOF',
                  'echo "a\\"; git add -A; echo \\"b"', 'echo "a\'b"; git status; echo "c\'d"', "git commit -m 'it'\"'\"'s'",
                  'git add "app/models/user.rb"', "git add 'a.rb' 'b.rb'", 'git commit -m "fix"', 'git status "-s"']
# ANSI-C bodies whose decoding must equal bash's own, byte for byte (compared when the result is one plain word, the only kind kept).
ANSIC_BODIES_1613 = ["\\x61bc", "a\\x62c", "\\141bc", "\\1411", "a\\x6", "\\x", "a\\u0062c", "a\\U00000062c", "ab\\0cd", "a\\x00b",
                     "\\x41\\x42", "x\\u00e9y", "x\\xc3\\xa9y", "\\e", "\\q", "\\cA", "a\\\\b", "a\\'b", "a\\?b", "a\\\"b", "\\a\\b\\t"]


def normaliser_pipelines(cmd: str) -> int | str:
    """#1504: how many `_normalize_one` pipelines `normalize_segments` runs for `cmd`. The lib is sourced
    and `_normalize_one` wrapped to append one byte to a file per call: a file, because each depth's
    pipeline (and, per string, each recursion) runs in a subshell a shell variable would not survive."""
    with tempfile.TemporaryDirectory() as td:
        count = Path(td) / "count"; count.write_text("")
        script = ('. "$1"\n'
                  'eval "_nc_counted_$(declare -f _normalize_one)"\n'
                  '_normalize_one() { printf x >> "$NC_COUNT"; _nc_counted__normalize_one; }\n'
                  'printf \'%s\' "$CMD" | normalize_segments >/dev/null\n')
        r = _run(["bash", "-c", script, "count", str(HOOKS / "lib" / "normalize_cmd.sh")], capture_output=True,
                 text=True, env={**os.environ, "NC_COUNT": str(count), "CMD": cmd})
        if r.returncode != 0:
            return f"exit {r.returncode}: {r.stderr.strip()[:200]}"
        return len(count.read_text())


def pattern_expansion_sites() -> list[str] | str:
    """#1504: every bash pattern-substitution expansion (`${name//…}`, `${name/…}`, `${name%…}`, `${name#…}`)
    in the functions `lib/normalize_cmd.sh` defines, read from `declare -f` so comments do not count."""
    script = ('before=$(declare -F); . "$1" || exit 3\n'
              'for f in $(declare -F | while read -r _ _ n; do case "$before" in (*" $n"*) ;; (*) echo "$n" ;; esac; done); do\n'
              '  declare -f "$f"\ndone\n')
    r = _run(["bash", "-c", script, "scan", str(HOOKS / "lib" / "normalize_cmd.sh")], capture_output=True, text=True)
    if r.returncode != 0 or "normalize_segments" not in r.stdout:
        return f"scan failed: exit {r.returncode}, {r.stderr.strip()[:200]}"
    return re.findall(r"\$\{[A-Za-z_][A-Za-z0-9_]*(?:/|%|#)[^}]*\}", r.stdout)


def guard_bash_fixtures() -> None:
    def run(cmd: str, shell: str = "bash") -> int:
        with tempfile.TemporaryDirectory() as td:
            return run_hook("guard-bash.sh", cwd=Path(td), shell=shell,
                            stdin=json.dumps({"tool_input": {"command": cmd}}))[0]

    for cmd in ("git add -A", "git add .", "git add --all",
                # THE #826 SHAPES.
                "git add -v -A", "git add -vA", "git add ./", "git add :/", "git add -v ."):
        check(f"guard-bash: `{cmd}` is blocked", run(cmd) == 2, "exit 0")
    for cmd in ("git add app/models/user.rb", "git add -p app/models/user.rb", "git add ./app/x.rb",
                "git add spec/models/user_spec.rb spec/support/x.rb", "git status", "git add -v lib/a.rb"):
        check(f"guard-bash: `{cmd}` passes", run(cmd) == 0, "exit 2")

    # #906: MATCH THE INVOKED COMMAND, NOT ANY SUBSTRING. Every negative here merely MENTIONS the rule;
    # every positive stages everything behind a prefix the old adjacency match could not see.
    for cmd in NEGATIVES_906:
        check(f"guard-bash (#906): `{cmd[:50]}` only mentions the rule and passes", run(cmd) == 0, "exit 2")
    for cmd in POSITIVES_906:
        check(f"guard-bash (#906): `{cmd}` is blocked", run(cmd) == 2, "exit 0")
    for cmd in NEGATIVES_1342:
        check(f"guard-bash (#1342): safe twin `{cmd[:60]}` stays allowed", run(cmd) == 0, "exit 2")
    for cmd in POSITIVES_1472:
        check(f"guard-bash (#1472): `{cmd!r}` runs the command and is blocked", run(cmd) == 2, "exit 0")
    for cmd in NEGATIVES_1472:
        check(f"guard-bash (#1472): CONTROL: `{cmd[:60]!r}` passes", run(cmd) == 0, "exit 2")
    for cmd in POSITIVES_1613:
        check(f"guard-bash (#1613): ANSI-C `{cmd!r}` is the command it decodes to, and is blocked", run(cmd) == 2, "exit 0")
    for cmd in POSITIVES_1568:
        check(f"guard-bash (#1568): `{cmd!r}` is read as the shell reads it, and is blocked", run(cmd) == 2, "exit 0")
    for cmd in NEGATIVES_1568:
        check(f"guard-bash (#1568): CONTROL: `{cmd[:60]!r}` passes", run(cmd) == 0, "exit 2")
    # #1613: the decoder against bash ITSELF. `git $'BODY'` goes through normalize_segments; `printf %s $'BODY'` is what bash makes of it.
    # Compared only when bash's word is plain (no space or shell character), because only a plain word is kept; any other is deleted.
    lib = HOOKS / "lib" / "normalize_cmd.sh"
    # bash 3.2 (macOS /bin/bash) does not decode \\u and \\U at all, so its answer is no reference for them; a newer bash is.
    unicode_ok = _run(["bash", "-c", "printf '%s' $'\\u0061'"], capture_output=True, text=True).stdout == "a"
    for body in ANSIC_BODIES_1613:
        if not unicode_ok and ("\\u" in body or "\\U" in body):
            continue
        word = _run(["bash", "-c", "printf '%s' $'" + body + "'"], capture_output=True, text=True).stdout
        plain = bool(word) and all(ch > " " and ch not in ";|&()<>$`\"\\#'" for ch in word)
        # Under a UTF-8 locale ON PURPOSE: gawk there turns sprintf("%c", 233) into the two bytes of U+00E9, which the lib's own LC_ALL=C pin must
        # prevent (release-gate.sh does not pin one). BSD awk (macOS) and mawk are byte-oriented either way, so this can only be red on gawk, i.e. on Linux CI.
        got = _run(["bash", "-c", f"source {lib}; printf '%s' \"$1\" | normalize_segments", "x", "git $'" + body + "'"],
                   capture_output=True, text=True, env={**os.environ, "LC_ALL": "C.UTF-8"}).stdout.strip()
        want = f"git {word}" if plain else "git"
        check(f"guard-bash (#1613): ANSI-C decoder agrees with bash on `$'{body}'`", got == want, f"bash made {word!r}; normaliser said {got!r}")
    # #1504: a depth's strings are normalised as ONE batch, so each must still be judged on its own.
    for cmd, why in (("bash -c 'cat <<EOF'; bash -c 'git add -A'", "an unclosed heredoc in one string does not swallow the next"),
                     ("bash -c \"echo it's\"; bash -c \"eval 'git add -A'\"", "an unbalanced quote in one string does not stop the next being lexed"),
                     (" ".join(["echo $(date)"] * 30) + "; bash -c 'git add -A'", "the 31st string of a batch is still seen"),
                     # #1519 review: a \002 line is a batch boundary only in a batch, never in the raw command...
                     ("bash -c 'x\n\x02\ny'; bash -c 'git add -A'", "a raw \\002 line does not split the command"),
                     # ...and a string carrying one cannot fake a boundary inside the next depth's batch.
                     ("bash -c \"bash -c 'x\n\x02\ny'; bash -c 'git add -A'\"", "a \\002 line inside a string does not split the batch")):
        check(f"guard-bash (#1504): {why}", run(cmd) == 2, "exit 0")
    # #1504: COST. The #1498 pre-check used bash's `${var//[set]/}`, superlinear on bash 3.2: an 8 KB PR body
    # took 32-96 s in guard-bash on dev. The bound is the hook's OWN declared timeout, read from hooks.json,
    # not a number of ours: past it Claude Code kills the hook. Measured after the fix: 0.16 s.
    hook_timeout = next(h["timeout"] for e in json.loads((HOOKS.parent / "hooks.json").read_text())["hooks"]["PreToolUse"]
                        for h in e["hooks"] if "guard-bash.sh" in h["command"])
    body = "\n".join(f"{i}) line with `code` and (parens)" for i in range(240))
    pr = f"gh pr create --title t --body \"$(cat <<'EOF'\n{body}\nEOF\n)\""
    # KILLED at that timeout, as Claude Code kills it: unbounded, the superlinear mutant ran for minutes
    # under the mutation harness's load and outran the harness's own limit instead of failing here.
    global _EXPECTING_TIMEOUT
    saved = os.environ.get("HOOK_GATES_TIMEOUT")
    os.environ["HOOK_GATES_TIMEOUT"] = str(hook_timeout)
    _EXPECTING_TIMEOUT = True
    t0 = time.monotonic()
    # PINNED to /bin/bash when it exists, as the guard-migrate check above does: that is bash 3.2 on a Mac,
    # the shell where the cost was measured. `bash` first on PATH may be Homebrew's bash 5, where this
    # timed check would pass without ever exercising the shell that matters (#1519 review, S-suggestion).
    timed_shell = "/bin/bash" if Path("/bin/bash").is_file() else "bash"
    try:
        rc = run(pr, shell=timed_shell)
    finally:
        _EXPECTING_TIMEOUT = False
        if saved is None:
            os.environ.pop("HOOK_GATES_TIMEOUT", None)
        else:
            os.environ["HOOK_GATES_TIMEOUT"] = saved
    took = time.monotonic() - t0
    check(f"guard-bash (#1504): an {len(pr) // 1024} KB PR body is judged inside the hook's {hook_timeout} s timeout, and passes",
          rc == 0 and took < hook_timeout, "killed at the timeout (exit 124)" if rc == 124 else f"exit {rc}, {took:.1f}s")
    # #1504: THE SLOW PATH, counted, not timed. bash 3.2's pattern substitution (`${v//[set]/}`, and its `/`,
    # `%`, `#` kin) is superlinear: on an 8 KB body it cost 32-96 s here. On bash 5 (Linux CI) the same
    # expansion is fast, so the timed check above cannot see it come back there; only the construct can.
    # Counted in the functions as BASH PARSED them (`declare -f`: comments gone, so prose cannot trip it).
    # A RATCHET at the measured 0: the normaliser does its text work in awk and sed, never in bash.
    sites = pattern_expansion_sites()
    check("guard-bash (#1504): the normaliser's functions run 0 bash pattern substitutions over the command (ratchet)",
          sites == [], f"{len(sites)} site(s): {sites[:3]}")
    # #1504: THE BATCHING, counted, not timed, so load cannot make it flaky. Each depth's strings go through
    # ONE `_normalize_one` pipeline; per string, as before, 30 strings cost 31 pipelines. A RATCHET at the
    # measured counts: a rise is the regression; a drop means the code got cheaper, so lower the number here.
    for cmd, want, what in ((" ".join(["echo $(date)"] * 30), 2, "30 `$(…)` strings at one depth"),
                            ("; ".join(["bash -c \"bash -c 'eval x'\""] * 10), 4, "10 strings nested 3 deep"),
                            ("git status", 1, "CONTROL: a command with no strings")):
        got = normaliser_pipelines(cmd)
        check(f"guard-bash (#1504): {what} cost {want} normaliser pipeline(s), one per depth (ratchet)",
              got == want, f"{got} pipelines" + (": lower the ratchet" if isinstance(got, int) and got < want else ""))
    # FAIL CLOSED without the lib: a staged copy of the hook with lib/ removed must still block the raw text.
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / "hooks"; shutil.copytree(HOOKS, stage); shutil.rmtree(stage / "lib")
        payload = lambda c: json.dumps({"tool_input": {"command": c}})
        r1 = _run(["bash", str(stage / "guard-bash.sh")], input=payload("git add -A"), capture_output=True, text=True, cwd=td)
        r2 = _run(["bash", str(stage / "guard-bash.sh")], input=payload("git -C repo add -A"), capture_output=True, text=True, cwd=td)
        check("guard-bash (#906): with lib/ missing the hook falls back to the raw text and still blocks `git add -A`", r1.returncode == 2)
        check("guard-bash (#906): ...and the fallback is honestly the OLD behaviour (git -C slips through), which is why the lib ships in the plugin", r2.returncode == 0)

    # #1311: an issue filed from the shell is labelled against the project's declared groups, or refused.
    groups = {"groups": [{"one_of": ["bug", "feature", "enhancement"]},
                         {"when": "bug", "one_of": ["severity:s1", "severity:s2"]}]}
    def labelled(cmd: str, *, declare: bool = True, drop_helper: bool = False,
                 files: dict[str, str] | None = None) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            for rel, text in (files or {}).items():     # relative scripts the command reads (#1495)
                (Path(td) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(td) / rel).write_text(text, encoding="utf-8")
            if declare:
                (Path(td) / ".rails-flow").mkdir()
                (Path(td) / ".rails-flow" / "issue-labels.json").write_text(json.dumps(groups), encoding="utf-8")
            hook = HOOKS / "guard-bash.sh"
            if drop_helper:
                stage = Path(td) / "hooks"; shutil.copytree(HOOKS, stage); (stage / "lib" / "issue_labels.py").unlink()
                hook = stage / "guard-bash.sh"
            r = _run(["bash", str(hook)], input=json.dumps({"tool_input": {"command": cmd}}),
                               capture_output=True, text=True, cwd=td)
            return r.returncode, r.stderr
    rc, err = labelled("gh issue create -t X --body-file b.md")
    check("guard-bash (#1311): an unlabelled gh issue create is blocked", rc == 2 and "no --label" in err, err)
    rc, err = labelled("gh issue create -t X --label bug")
    check("guard-bash (#1311): a bug without its declared severity is blocked, and says why",
          rc == 2 and "severity:s1" in err, err)
    check("guard-bash (#1311): CONTROL: a bug with a severity passes",
          labelled('gh issue create -t X --label bug --label "severity:s2"')[0] == 0)
    check("guard-bash (#1311): an undeclared project still needs one label",
          labelled("gh issue create -t X", declare=False)[0] == 2
          and labelled("gh issue create -t X --label x", declare=False)[0] == 0)
    # #1336: the doctrine's own shape -- a quoted heredoc body, then a labelled create, one call.
    heredoc = "cat > b.md <<'EOF'\nthe validator's `warning` is quoted\nEOF\n"  # one apostrophe: unpairable
    rc, err = labelled(heredoc + "gh issue create -t X --label bug --label severity:s2 --body-file b.md")
    check("guard-bash (#1336): a heredoc body before a labelled create is allowed", rc == 0, err)
    rc, err = labelled(heredoc + "gh issue create -t X --body-file b.md")
    check("guard-bash (#1336): ...and an unlabelled create after it is still blocked",
          rc == 2 and "no --label" in err, err)
    # #1400: the TARGET repository's declaration, through the real hook. The session stands in a repo
    # that wants comp/type/prio; the command cds into one that wants a type and, for a bug, a severity.
    with tempfile.TemporaryDirectory() as td:
        session, other = Path(td) / "session", Path(td) / "other"
        for repo, decl in ((session, {"groups": [{"one_of": ["comp:*"]}, {"one_of": ["type:*"]}]}), (other, groups)):
            (repo / ".rails-flow").mkdir(parents=True)
            (repo / ".rails-flow" / "issue-labels.json").write_text(json.dumps(decl), encoding="utf-8")
        # The target is CERTAINLY another repo only when both sides have remotes and share none.
        _run(["git", "init", "-q", str(session)], check=True)
        _run(["git", "-C", str(session), "remote", "add", "origin", "https://github.com/me/session.git"], check=True)
        _run(["git", "init", "-q", str(other)], check=True)
        _run(["git", "-C", str(other), "remote", "add", "origin", "https://github.com/other/repo.git"], check=True)
        def cross(cmd: str) -> tuple[int, str]:
            r = _run(["bash", str(HOOKS / "guard-bash.sh")], input=json.dumps({"tool_input": {"command": cmd}}),
                               capture_output=True, text=True, cwd=session)
            return r.returncode, r.stderr
        rc, err = cross(f"cd {other} && gh issue create -t X --label enhancement --body-file b.md")
        check("guard-bash (#1400): a create after `cd <other repo>` answers to THAT repo's labels", rc == 0, err)
        rc, err = cross(f"cd {other} && gh issue create -t X --label bug --body-file b.md")
        check("guard-bash (#1400): ...and that repo's rules still refuse", rc == 2 and "severity:s1" in err, err)
        rc, err = cross("gh issue create -t X --label enhancement --body-file b.md")
        check("guard-bash (#1400): CONTROL: without the cd, the session's own rules apply", rc == 2 and "comp:*" in err, err)
    # #1423: the hook must CALL the helper for a create that never starts a segment.
    rc, err = labelled("sh -c 'gh issue create -t X --label feature'")
    check("guard-bash (#1423): a create inside `sh -c` is refused through the real hook",
          rc == 2 and "sh -c" in err and "directly" in err, err)
    rc, err = labelled("/usr/bin/gh issue create -t X --body-file b.md")
    check("guard-bash (#1423): `/usr/bin/gh issue create` with no label is refused through the real hook",
          rc == 2 and "no --label" in err, err)
    # #1462: the trigger must reach the helper for forms a plain `gh issue create` grep misses.
    for form in ('gh issue "create" -t X --body-file b.md', "gh --repo o/r issue create -t X --body-file b.md",
                 "gh issue new -t X --body-file b.md"):
        rc, err = labelled(form)
        check(f"guard-bash (#1462): `{form[:30]}` with no label is refused through the real hook",
              rc == 2 and "no --label" in err, err)
    # #1489: `bash < file` names no create in its text; the trigger must still reach the helper.
    with tempfile.TemporaryDirectory() as sd:
        script = Path(sd) / "file.sh"
        script.write_text("#!/bin/sh\ngh issue create -t X\n", encoding="utf-8")
        rc, err = labelled(f"bash < {script}")
        check("guard-bash (#1489): a script with a create fed to bash by redirect is refused through the real hook",
              rc == 2 and "by redirect" in err, err)
        plain = Path(sd) / "plain.sh"
        plain.write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
        check("guard-bash (#1489): CONTROL: a harmless redirected script is allowed through the real hook",
              labelled(f"bash < {plain}")[0] == 0)
        # #1489 review: the spellings the first trigger missed, each through the real hook.
        for form in (f"/bin/bash < {script}", f"bash --norc < {script}", f"bash -o errexit < {script}",
                     f"sh<{script}", f"bash 0< {script}"):
            rc, err = labelled(form)
            check(f"guard-bash (#1489 review): `{form.split(sd)[0]}` with a create is refused through the real hook",
                  rc == 2 and "by redirect" in err, err)
        check("guard-bash (#1489 review): CONTROL: `bash other.sh < file` hands the file to a script as data, allowed",
              labelled(f"bash other.sh < {script}")[0] == 0)
        check("guard-bash (#1489 review): CONTROL: `$'…'` before a harmless redirected script is allowed",
              labelled(f"echo $'it\\'s'; bash < {plain}")[0] == 0)
    # A relative script is read from the cd target (#1489 review, through the real hook).
    with tempfile.TemporaryDirectory() as sd:
        (Path(sd) / "only.sh").write_text("gh issue create -t X\n", encoding="utf-8")
        rc, err = labelled(f"cd {sd} && bash < only.sh")
        check("guard-bash (#1489 review): `cd <dir> && bash < only.sh` reads the cd target's script and is refused",
              rc == 2 and "by redirect" in err, err)
    # #1495: the five #1489 edge cases, each through the real hook, with a control.
    create, harmless = "gh issue create -t X --body y\n", "echo hi\n"
    tree = {"bad.sh": create, "sub/only.sh": create, "ok.sh": harmless}
    for cmd, why in (("cd nope; bash < bad.sh", "a cd to a missing directory fails and changes nothing"),
                     ("(cd sub && bash < only.sh)", "a cd inside ( ) holds until the )"),
                     ("cd sub; bash < only.sh", "a cd joined by ; that succeeds is followed"),
                     ("bash -eo pipefail < bad.sh", "a bundled -o takes a value"),
                     ("bash -euxo pipefail < bad.sh", "a longer bundle ending in o takes a value"),
                     ("bash 2>&1 < bad.sh", "the & of a fd duplication is not a separator"),
                     ("bash &>log < bad.sh", "&> is a redirect, not a background &")):
        rc, err = labelled(cmd, files=tree)
        check(f"guard-bash (#1495): `{cmd}` is refused ({why})", rc == 2 and "by redirect" in err and "cannot follow" not in err, err)
    for cmd, why in (("(cd sub) && bash < only.sh", "the subshell's cd does not outlive it; only.sh is not here"),
                     ("bash -eo pipefail ok.sh < bad.sh", "a script operand after -eo VALUE reads stdin as data"),
                     ("bash 2>&1 < ok.sh", "a harmless script behind 2>&1")):
        check(f"guard-bash (#1495): CONTROL: `{cmd}` is allowed ({why})", labelled(cmd, files=tree)[0] == 0)
    # #1513 review: shapes the first #1495 version still let through, each through the real hook.
    tree2 = {**tree, "sub/ok.sh": harmless}
    for cmd, why in (("cd sub &>/dev/null; bash < only.sh", "a cd's own redirect is not an argument"),
                     ("bash -ox pipefail < bad.sh", "an o inside a bundle takes a value"),
                     ("bash 2>&1<bad.sh", "a redirect glued to < is cut out"),
                     ("bash>/dev/null<bad.sh", "a redirect glued to the shell is cut out"),
                     ("bash&>log<bad.sh", "the trigger sees a redirect glued to the shell"),
                     ("bash >&log < bad.sh", ">&word is a redirect"),
                     ("cd sub & bash < bad.sh", "a backgrounded cd runs in a subshell"),
                     ("cd sub | bash < bad.sh", "a piped cd runs in a subshell")):
        rc, err = labelled(cmd, files=tree2)
        check(f"guard-bash (#1513): `{cmd}` is refused ({why})", rc == 2 and "by redirect" in err and "cannot follow" not in err, err)
    rc, err = labelled("cd $X && bash < ok.sh", files=tree2)
    check("guard-bash (#1513): a relative script after a cd the hook cannot follow is refused, not guessed",
          rc == 2 and "cannot follow" in err, err)
    for spelled in ("gh issue $'\\x63reate'", "gh issue $'\\143reate'", "gh $'\\x69ssue' create", "$'\\x67h' issue create"):
        rc, err = labelled(f"{spelled} -t X --body y")
        check(f"guard-bash (#1513): `{spelled}` reaches the helper and an unlabelled create is refused",
              rc == 2 and "no --label" in err, err)
    for cmd in ("cd sub &>/dev/null; bash < ok.sh", "bash>/dev/null<ok.sh", "cd sub & bash < ok.sh", "echo $'a\\tb'"):
        check(f"guard-bash (#1513): CONTROL: `{cmd}` is allowed", labelled(cmd, files=tree2)[0] == 0)
    rc, err = labelled("gh issue $'create' -t X --body y")
    check("guard-bash (#1495): `gh issue $'create'` reaches the helper and an unlabelled create is refused",
          rc == 2 and "no --label" in err, err)
    for spelled in ("$'\\x66eature'", "$'\\146eature'", "$'\\u0066eature'"):
        check(f"guard-bash (#1495): CONTROL: `-l {spelled}` is the label `feature`, and is allowed",
              labelled(f"gh issue create -t X --body y -l {spelled}")[0] == 0)
    check("guard-bash (#1423): CONTROL: an echo of the text is allowed through the real hook",
          labelled('echo "gh issue create"')[0] == 0)
    rc, err = labelled("gh issue create -t X --label feature", drop_helper=True)
    check("guard-bash (#1311): FAIL CLOSED: with the helper missing, a labelled create is refused, not let through",
          rc == 2 and "could not run" in err, err)

    # #1526 -- THREE WAYS THE NORMALISED TEXT CAME OUT EMPTY, AND EVERY RULE PASSED. Each is driven
    # through the real hook, with a control on the same input that must still pass.
    def raw(stdin: bytes, path: str | None = None, lang: str = "C") -> int:
        env = {"HOME": os.environ.get("HOME", "/tmp"), "LANG": lang, "LC_ALL": lang,
               "PATH": path if path is not None else os.environ["PATH"]}
        with tempfile.TemporaryDirectory() as td:
            return _run(["/bin/bash", str(HOOKS / "guard-bash.sh")], cwd=td, input=stdin, env=env,
                        capture_output=True, timeout=60).returncode

    def payload(cmd: str) -> bytes:
        return json.dumps({"tool_input": {"command": cmd}}).encode()

    # 1. NO awk ON PATH: the normaliser printed nothing. Absolute binaries, so an alias or a shell
    # function for one of them cannot stand in (zsh here aliases grep).
    with tempfile.TemporaryDirectory() as bd:
        for tool in ("bash", "git", "sed", "tr", "grep", "dirname", "cat", "env", "head"):
            real = next((f"{d}/{tool}" for d in ("/usr/bin", "/bin") if os.path.exists(f"{d}/{tool}")), None)
            if real:
                os.symlink(real, Path(bd) / tool)
        os.symlink(sys.executable, Path(bd) / "python3")
        check("guard-bash (#1526): with no awk on PATH, `git add -A` is still blocked",
              raw(payload("git add -A"), bd) == 2, "exit 0: the normaliser printed nothing and every rule passed")
        check("guard-bash (#1526): with no awk on PATH, a force-push to dev is still blocked",
              raw(payload("git push --force origin dev"), bd) == 2, "exit 0")
        check("guard-bash (#1526): CONTROL: with no awk on PATH, `git status` still passes",
              raw(payload("git status"), bd) == 0, "exit 2")
    # 1b. A LONG COMMAND: `grep -q` quits at the first match, `printf` takes SIGPIPE once the text outgrows
    # the pipe buffer, and `set -o pipefail` read that 141 as "no match". `git add -A` plus 10k lines of echo
    # was allowed (attacker corpus b2/b3/b4/b14). 10k lines of `echo line N` is ~130KB, past a 64KB pipe.
    long_tail = "".join(f"echo line {i}\n" for i in range(10000))
    check("guard-bash: `git add -A` followed by 10k lines is still blocked (pipefail + SIGPIPE)",
          raw(payload("git add -A\n" + long_tail)) == 2, "exit 0: grep -q's early exit was read as no match")
    check("guard-bash: a force-push to dev followed by 10k lines is still blocked",
          raw(payload("git push --force origin dev\n" + long_tail)) == 2, "exit 0")
    check("guard-bash: CONTROL: `git status` followed by 10k lines still passes",
          raw(payload("git status\n" + long_tail)) == 0, "exit 2")
    # 2. AN UNCLOSED HEREDOC INSIDE `$( )`: bash ends it at the line closing the `$( )`.
    check("guard-bash (#1526): a heredoc left open inside $( ) does not hide the `git add -A` after it",
          run("x=$(cat <<EOF\nfoo\n)\ngit add -A") == 2, "exit 0")
    check("guard-bash (#1526): CONTROL: the same shape followed by `git status` passes",
          run("x=$(cat <<EOF\nfoo\n)\ngit status") == 0, "exit 2")
    check("guard-bash (#1526): CONTROL: `git add -A` INSIDE a closed heredoc in $( ) is a mention and passes",
          run("x=$(cat <<EOF\ngit add -A\nEOF\n)") == 0, "exit 2")
    # 3. AN INVALID UTF-8 BYTE: the parse failed, and the raw JSON's quotes hid the command.
    check("guard-bash (#1526): an invalid UTF-8 byte does not hide `git add -A`",
          raw(b'{"tool_input":{"command":"git add -A \xff"}}', lang="en_US.UTF-8") == 2, "exit 0")
    check("guard-bash (#1526): CONTROL: an invalid UTF-8 byte after `git status` passes",
          raw(b'{"tool_input":{"command":"git status \xff"}}', lang="en_US.UTF-8") == 0, "exit 2")
    check("guard-bash (#1529 review): CONTROL: an invalid byte beside a QUOTED mention still parses and passes",
          raw(b'{"tool_input":{"command":"echo \\"never git add -A\\" \xff"}}', lang="en_US.UTF-8") == 0,
          "exit 2: the payload was not decoded, so the hook fell to degraded mode")

    # #1529 review: the fallback was the RAW text, and every rule is anchored `^git` -- so a compound
    # command, a missing python3 (the raw JSON) or a lone surrogate still passed. Degraded mode now
    # matches unanchored; with no grep, bash's `=~` matches.
    def bindir(tools: tuple[str, ...], python: bool) -> str:
        bd = tempfile.mkdtemp()
        for tool in tools:
            real = next((f"{d}/{tool}" for d in ("/usr/bin", "/bin") if os.path.exists(f"{d}/{tool}")), None)
            if real:
                os.symlink(real, Path(bd) / tool)
        if python:
            os.symlink(sys.executable, Path(bd) / "python3")
        return bd
    base = ("bash", "git", "dirname", "cat", "env", "head")
    no_awk = bindir(base + ("grep",), python=True)
    no_python = bindir(base + ("grep", "sed", "tr", "awk"), python=False)
    no_grep = bindir(base + ("sed", "tr", "awk"), python=True)
    try:
        check("guard-bash (#1529 review): with no awk, a COMPOUND `cd x && git add -A` is blocked",
              raw(payload("cd x && git add -A"), no_awk) == 2, "exit 0: the anchored rules missed the raw text")
        check("guard-bash (#1529 review): CONTROL: with no awk, `cd x && git status` passes",
              raw(payload("cd x && git status"), no_awk) == 0, "exit 2")
        check("guard-bash (#1529 review): with no python3, `git add -A` is blocked (the raw JSON is matched)",
              raw(payload("git add -A"), no_python) == 2, "exit 0")
        check("guard-bash (#1529 review): CONTROL: with no python3, `git status` passes",
              raw(payload("git status"), no_python) == 0, "exit 2")
        check("guard-bash (#1529 review): with no grep, `git add -A` is blocked",
              raw(payload("git add -A"), no_grep) == 2, "exit 0: hit() failed on every rule")
        check("guard-bash (#1529 review): with no grep, a force-push to dev is blocked",
              raw(payload("git push --force origin dev"), no_grep) == 2, "exit 0")
        check("guard-bash (#1529 review): CONTROL: with no grep, `git status` passes",
              raw(payload("git status"), no_grep) == 0, "exit 2")
        # #1529 round 3: with no grep the lib still normalises, so the hook is NOT degraded -- and one
        # `=~` over the multi-line text let `^` see only the first segment.
        for cmd in ("cd x && git add -A", "echo hi; git add -A", "x=$(git add -A)",
                    "cd x; git push --force origin main", "cd x && git clean -fd"):
            check(f"guard-bash (#1529 r3): with no grep, a LATER segment `{cmd}` is blocked",
                  raw(payload(cmd), no_grep) == 2, "exit 0: `^` matched only the first line")
        check("guard-bash (#1529 r3): CONTROL: with no grep, `cd x && git status` passes",
              raw(payload("cd x && git status"), no_grep) == 0, "exit 2")
        check("guard-bash (#1529 r3): CONTROL: with no grep, a dry-run `cd x && git clean -n -fd` passes",
              raw(payload("cd x && git clean -n -fd"), no_grep) == 0, "exit 2")
    finally:
        for bd in (no_awk, no_python, no_grep):
            shutil.rmtree(bd, ignore_errors=True)
    check("guard-bash (#1529 review): a lone surrogate does not hide `git add -A`",
          raw(b'{"tool_input":{"command":"git add -A \\ud800"}}') == 2, "exit 0")
    check("guard-bash (#1529 review): a heredoc left open inside BACKTICKS does not hide what follows",
          run("x=`cat <<EOF\nfoo\n`\ngit add -A") == 2, "exit 0")
    check("guard-bash (#1529 review): CONTROL: the backtick shape followed by `git status` passes",
          run("x=`cat <<EOF\nfoo\n`\ngit status") == 0, "exit 2")

    # #1529 round-2 review. B1: after a heredoc ended early at the `)`, a body line naming `cat <<END`
    # opened a heredoc that never closed and hid what bash runs next -- a regression on dev's exit 2.
    check("guard-bash (#1529 r2): a PR body naming `cat <<END` after an early heredoc end hides nothing",
          run("gh pr view 1 --json body -q \"$(cat <<'EOF'\n) note\nuse `cat <<END` here\nEOF\n)\"\ngit add -A") == 2,
          "exit 0: a phantom heredoc swallowed the command")
    check("guard-bash (#1529 r2): the minimal phantom-heredoc shape is blocked",
          run("x=$(cat <<EOF\n)\ncat <<END\nEOF\n)\ngit add -A") == 2, "exit 0")
    # B2: an awk that FAILS (not a missing one) read as a clean empty result.
    fake = tempfile.mkdtemp()
    for tool in ("bash", "git", "dirname", "cat", "env", "head", "sed", "tr", "grep"):
        real = next((f"{d}/{tool}" for d in ("/usr/bin", "/bin") if os.path.exists(f"{d}/{tool}")), None)
        if real:
            os.symlink(real, Path(fake) / tool)
    os.symlink(sys.executable, Path(fake) / "python3")
    (Path(fake) / "awk").write_text("#!/bin/sh\nexit 2\n", encoding="utf-8")
    (Path(fake) / "awk").chmod(0o755)
    no_cat = bindir(base + ("grep", "sed", "tr", "awk"), python=True)
    os.unlink(Path(no_cat) / "cat")
    no_awk = bindir(base + ("grep",), python=True)
    # No sed: the FIRST stage fails while the last (awk) succeeds on empty input, so only `pipefail`
    # carries the failure (#1529 round 3).
    no_sed = bindir(base + ("grep", "tr", "awk"), python=True)
    try:
        check("guard-bash (#1529 r3): with no sed, `git add -A` is blocked",
              raw(payload("git add -A"), no_sed) == 2, "exit 0: an early stage failed and the last one's 0 won")
        check("guard-bash (#1529 r3): CONTROL: with no sed, `git status` passes",
              raw(payload("git status"), no_sed) == 0, "exit 2")
        check("guard-bash (#1529 r2): with an awk that exits 2, `git add -A` is blocked",
              raw(payload("git add -A"), fake) == 2, "exit 0: the normaliser's status was discarded")
        check("guard-bash (#1529 r2): CONTROL: with an awk that exits 2, `git status` passes",
              raw(payload("git status"), fake) == 0, "exit 2")
        # B3: unanchored, an exemption's `.*` reached another segment.
        for cmd in ("git clean -fd && echo -n done", "git push --force origin feat; echo --force-with-lease",
                    "git restore . && echo --staged"):
            check(f"guard-bash (#1529 r2): with no awk, `{cmd}` is not exempted by another segment",
                  raw(payload(cmd), no_awk) == 2, "exit 0")
        # Suggestion 1: `$(cat)` read nothing without cat.
        check("guard-bash (#1529 r2): with no cat, `git add -A` is blocked",
              raw(payload("git add -A"), no_cat) == 2, "exit 0: stdin was never read")
        check("guard-bash (#1529 r2): CONTROL: with no cat, `git status` passes",
              raw(payload("git status"), no_cat) == 0, "exit 2")
    finally:
        for bd in (fake, no_cat, no_awk, no_sed):
            shutil.rmtree(bd, ignore_errors=True)
    check("guard-bash (#1529 r2): CONTROL: with the full PATH, `git clean -n -fd` is still a dry run",
          run("git clean -n -fd") == 0, "exit 2")


# ---- guard-claims.sh (#1106) --------------------------------------------------------------------
# `claim-verifier` exists, works, covers "any number: counts, ratios, versions, timings", and is
# named in /maintainer-work -- and it was skipped for a whole working day while two wrong numbers
# reached merged PR bodies. The capability was never the gap; remembering to use it was. So the
# check runs whether or not anyone remembers, and these fixtures drive BOTH directions, because a
# guard that blocks everything is as useless as one that blocks nothing.


# ---- guard-claims.sh under pipefail with a long command (#1579) --------------------------------------------------------
def guard_claims_pipe_fixtures() -> None:
    """A `gh pr create` FIRST and a long tail after it: `grep -q` quits at the early match, `printf` takes SIGPIPE once the
    text outgrows the pipe buffer, and `pipefail` turned that 141 into "no match", so the guard exited 0 having checked
    nothing (#1579; the class of #1570 in guard-bash.sh). The tail is 10,000 lines, well past any pipe buffer."""
    TAIL = "\n" + "echo line\n" * 10000
    NUMERIC = "The selftest reports **292 assertions**, up from 285.\n"
    TPL = "## What changed\n\n## How to test\n"

    def run(cmd: str, body: str | None = None, template: str | None = None) -> int:
        with tempfile.TemporaryDirectory() as td:
            if template is not None:
                (Path(td) / ".github").mkdir()
                (Path(td) / ".github" / "pull_request_template.md").write_text(template, encoding="utf-8")
            if body is not None:
                (Path(td) / "body.md").write_text(body, encoding="utf-8")
                cmd = cmd.replace("BODY", str(Path(td) / "body.md"))
            return run_hook("guard-claims.sh", cwd=Path(td), stdin=json.dumps({"tool_input": {"command": cmd}}),
                            env_extra={"CLAUDE_PLUGIN_ROOT": str(HOOKS.parents[1])})[0]

    check("guard-claims (#1579): an unchecked claim is blocked when a 10,000-line tail FOLLOWS the gh pr create",
          run("gh pr create --base dev --body-file BODY" + TAIL, NUMERIC) == 2, "exit 0: checked nothing")
    check("guard-claims (#1579): ...and the same in an issue comment",
          run("gh issue comment 1579 --body-file BODY" + TAIL, NUMERIC) == 2, "exit 0: checked nothing")
    check("guard-claims (#1579): a missing template section is blocked with the long tail after it",
          run("gh pr create --base dev --body-file BODY" + TAIL, "## What changed\nTidy the README.\n", TPL) == 2,
          "exit 0: template not checked")
    check("guard-claims (#1579) control: the 10,000-line tail alone is not a claim-carrying command, and passes",
          run(TAIL.strip()) == 0, "blocked a benign command")


def guard_claims_fixtures() -> None:
    def run(cmd: str, body: str | None = None, env_extra=None, template: str | None = None,
            with_output: bool = False):
        with tempfile.TemporaryDirectory() as td:
            if template is not None:
                (Path(td) / ".github").mkdir()
                (Path(td) / ".github" / "pull_request_template.md").write_text(template, encoding="utf-8")
            if body is not None:
                (Path(td) / "body.md").write_text(body, encoding="utf-8")
                cmd = cmd.replace("BODY", str(Path(td) / "body.md"))
            cmd = cmd.replace("BODYDIR", td)
            done = run_hook("guard-claims.sh", cwd=Path(td),
                            stdin=json.dumps({"tool_input": {"command": cmd}}),
                            env_extra={"CLAUDE_PLUGIN_ROOT": str(HOOKS.parents[1]),
                                       **(env_extra or {})})
            return done if with_output else done[0]

    NUMERIC = "The selftest reports **292 assertions**, up from 285.\n"
    CHECKED = NUMERIC + "Verified against the v1.134.0 tag.\n"
    PROSE = "Tidy up the wording in the README.\n"

    # MUST BLOCK: the exact shape that shipped wrong, twice, on the day this was written.
    check("guard-claims: an unchecked numeric claim in a PR body is blocked",
          run("gh pr create --base dev --body-file BODY", NUMERIC) == 2, "exit 0")

    # `gh issue comment` IS THE SAME ARTIFACT (#1141). This guard is the only thing that has ever
    # actually stopped a wrong number here, and it watched PRs alone -- so on the day it fired on a
    # PR body carrying eight unverified claims, four issue comments carrying counts went out
    # unchecked. An issue comment is durable, read by someone else and quoted onward.
    check("guard-claims: an unchecked numeric claim in an ISSUE COMMENT is blocked",
          run("gh issue comment 1141 --body-file BODY", NUMERIC) == 2, "exit 0")
    check("guard-claims: ...and the same comment passes once it shows it was verified",
          run("gh issue comment 1141 --body-file BODY", CHECKED) == 0, "exit 2")

    # MUST PASS -- and these are the half that keeps the guard alive. A hook that blocked every
    # `gh pr create` would be switched off within a day, and then nothing is checked at all.
    check("guard-claims: the same claim passes once the body shows it was verified",
          run("gh pr create --base dev --body-file BODY", CHECKED) == 0, "exit 2")
    check("guard-claims: a PR body with no load-bearing claim passes",
          run("gh pr create --base dev --body-file BODY", PROSE) == 0, "exit 2")

    # THE REPO'S PR TEMPLATE (#1389), driven through the real hook: 5 of 5 downstream PRs were
    # BLOCKED by a reviewer for missing template sections that a rule in prose never stopped.
    TPL = "## What changed\n\n## How to test\n\n## If this touches skills\n"
    FULL = "## What changed\nTidy the README.\n## How to test\nN/A — copy only.\n"
    check("guard-claims: a PR body missing a template section is blocked",
          run("gh pr create --base dev --body-file BODY", "## What changed\nTidy the README.\n",
              template=TPL) == 2, "exit 0")
    check("guard-claims: ...and `gh pr edit` with the same body is blocked too",
          run("gh pr edit 12 --body-file BODY", "## What changed\nTidy the README.\n", template=TPL) == 2,
          "exit 0")
    check("guard-claims: a PR body carrying every template section passes (an If-section may be left out)",
          run("gh pr create --base dev --body-file BODY", FULL, template=TPL) == 0, "exit 2")
    check("guard-claims: a repo with no PR template is not held to one",
          run("gh pr create --base dev --body-file BODY", "## What changed\nTidy the README.\n") == 0,
          "exit 2")
    # Pre-release review of #1398: a crash or a foreign repository must be said out loud, never pass silently.
    check("guard-claims: a template-optional section ('(optional)') may be left out",
          run("gh pr create --base dev --body-file BODY", "## What changed\nx\n## How to test\nN/A.\n",
              template=TPL + "## Screenshots (optional)\n") == 0, "exit 2")
    check("guard-claims: -R targets another repo, so its template is not judged here",
          run("gh pr create -R other/repo --base dev --body-file BODY", "## What changed\nx\n",
              template=TPL) == 0, "exit 2")
    check("guard-claims: ...and without -R the same body is blocked (control)",
          run("gh pr create --base dev --body-file BODY", "## What changed\nx\n", template=TPL) == 2, "exit 0")
    # Second pre-release review: a crash is said out loud, and -R is read from the gh segment only.
    rc, out = run("gh pr create --base dev --body-file BODYDIR", None, template=TPL, with_output=True)
    # FAIL CLOSED (owner decision on #1435): a checker that cannot judge has not checked anything.
    check("guard-claims: a body the helper cannot judge (a directory) is BLOCKED, never let through",
          rc == 2 and "crashed" in out, f"exit {rc}: {out[-120:]}")
    check("guard-claims: an unrelated `grep -R` earlier in the chain does not switch the check off",
          run("grep -R TODO . >/dev/null; gh pr create --base dev --body-file BODY", "## What changed\nx\n",
              template=TPL) == 2, "exit 0")
    check("guard-claims: the attached form -Rother/repo is another repository too",
          run("gh pr create -Rother/repo --base dev --body-file BODY", "## What changed\nx\n",
              template=TPL) == 0, "exit 2")
    # Third pre-release review: a helper that dies AT IMPORT exits 1 with nothing listed. Run a COPY of
    # the hook whose helper cannot import, so the branch that says so is proven reachable.
    with tempfile.TemporaryDirectory() as hd:
        copy = Path(hd) / "scripts"
        shutil.copytree(HOOKS, copy)
        (copy / "lib" / "pr_template.py").write_text("import nonexistent_module_for_the_fixture\n", encoding="utf-8")
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / ".github").mkdir()
            (Path(td) / ".github" / "pull_request_template.md").write_text(TPL, encoding="utf-8")
            (Path(td) / "body.md").write_text("## What changed\nx\n", encoding="utf-8")
            env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(HOOKS.parents[1])}
            for k in [k for k in env if k.startswith(("GIT_", "GH_"))]:
                env.pop(k, None)
            broke = _run(["bash", str(copy / "guard-claims.sh")], cwd=td, env=env, text=True,
                                   capture_output=True, timeout=60,
                                   input=json.dumps({"tool_input": {"command": f"gh pr create --base dev --body-file {td}/body.md"}}))
    check("guard-claims: a helper that fails at import is BLOCKED, never let through",
          broke.returncode == 2 and "died before judging" in broke.stdout + broke.stderr,
          f"exit {broke.returncode}: {(broke.stdout + broke.stderr)[-120:]}")
    # #1509: the directory resolver is a checker too. Missing or crashing, it has resolved nothing,
    # and the session directory is not a safe default: FAIL CLOSED, as #1435 ruled for pr_template.
    # The review's shape (#1516): a cd plus a RELATIVE body that exists only in the cd target. An absolute
    # body with no cd reached the template branch's own block; this one used to fail OPEN at "could not
    # read a --body-file" before any block ran.
    for label, mangle in (
            ("missing", lambda f: f.rename(f.with_name("command_cwd_renamed.py"))),
            ("crashing", lambda f: f.write_text("import sys\nsys.exit(1)\n", encoding="utf-8"))):
        with tempfile.TemporaryDirectory() as hd:
            copy = Path(hd) / "scripts"
            shutil.copytree(HOOKS, copy)
            mangle(copy / "lib" / "command_cwd.py")
            with tempfile.TemporaryDirectory() as td:
                a, b = Path(td) / "a", Path(td) / "b"
                for d in (a, b):
                    (d / ".github").mkdir(parents=True)
                    (d / ".github" / "pull_request_template.md").write_text(TPL, encoding="utf-8")
                (b / "onlyb.md").write_text(FULL, encoding="utf-8")
                env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(HOOKS.parents[1])}
                for k in [k for k in env if k.startswith(("GIT_", "GH_"))]:
                    env.pop(k, None)
                broke = _run(["bash", str(copy / "guard-claims.sh")], cwd=a, env=env, text=True,
                             capture_output=True, timeout=60,
                             input=json.dumps({"tool_input": {"command": f"cd {b} && gh pr create --base dev --body-file onlyb.md"}}))
        needle = "could not be resolved"
        check(f"guard-claims: a {label} command_cwd.py is BLOCKED, never the session's template (#1509)",
              broke.returncode == 2 and needle in broke.stdout + broke.stderr,
              f"exit {broke.returncode}: {(broke.stdout + broke.stderr)[-120:]}")
    check("guard-claims: `-R` in a double-quoted title with an apostrophe is still text (#1435)",
          run("gh pr create --title \"it's the -R fix\" --base dev --body-file BODY", "## What changed\nx\n",
              template=TPL) == 2, "exit 0")
    check("guard-claims: ...and an escaped quote inside the title does not end it early",
          run("gh pr create --title \"say \\\"hi -R\\\" now\" --base dev --body-file BODY", "## What changed\nx\n",
              template=TPL) == 2, "exit 0")
    check("guard-claims: `-R` inside a quoted --title is text, so the body is still judged",
          run("gh pr create --title 'fix grep -R bug' --base dev --body-file BODY", "## What changed\nx\n",
              template=TPL) == 2, "exit 0")
    check("guard-claims: GH_REPO=other/repo targets another repository",
          run("GH_REPO=o/r gh pr create --base dev --body-file BODY", "## What changed\nx\n", template=TPL) == 0,
          "exit 2")
    check("guard-claims: a | inside a quoted title does not hide a later -R",
          run("gh pr create --title 'a|b' -R o/r --body-file BODY", "## What changed\nx\n", template=TPL) == 0,
          "exit 2")

    # ---- the COMMAND's directory, not the session's (#1509) ----
    # A hook runs in the session's directory. A session rooted in repo A ran `cd <repo B> && gh pr
    # create` and was BLOCKED for missing A's sections, while B's template went unchecked. Each body
    # below satisfies exactly one of the two templates, so a verdict names the template it read.
    TPL_B = "## Summary\n\n## Risk\n"
    FITS_B = "## Summary\nTidy the README.\n## Risk\nNone, copy only.\n"

    def run_in(cmd: str, body: str, *, body_in: str = "a", with_output: bool = False, payload_cwd: str = "",
               env_extra: dict[str, str] | None = None):
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td) / "a", Path(td) / "b"
            # `a/5` carries B's template, so `cd 5 >/dev/null` read as a bare `cd` (HOME, set to A) is visible.
            for d, tpl in ((a, TPL), (b, TPL_B), (a / "5", TPL_B)):
                (d / ".github").mkdir(parents=True)
                (d / ".github" / "pull_request_template.md").write_text(tpl, encoding="utf-8")
            # A directory literally named `$NOWHERE`: a `cd $NOWHERE` read literally would find it, so
            # only the refusal of `$` keeps that fixture red, not the missing-directory check.
            (a / "$NOWHERE").mkdir()
            (a / "sub").mkdir()             # `cd sub` resolves here, so only CDPATH can make it unknown
            (a / "~nobody").mkdir()         # likewise, only the refusal of `~user` keeps that fixture red
            # #1605: directories whose names the shell would EXPAND if unquoted (`cd [b]` runs in `b`, `cd {b1,b2}` in `b1`, never in
            # these). Each carries B's template, so reading the name literally is visible: exit 2 and B's "## Risk".
            for glob_dir in ("[b]", "{b1,b2}", "x*", "y?", "?", "*"):
                (a / glob_dir / ".github").mkdir(parents=True)
                (a / glob_dir / ".github" / "pull_request_template.md").write_text(TPL_B, encoding="utf-8")
            (b / "sub").mkdir()             # A/linkSub -> B/sub: `cd -P linkSub/..` is B, a logical one A
            (a / "linkSub").symlink_to(b / "sub")
            for odd in ("x#y", "x #y"):     # a `#` that is not a comment: B's template one level down
                (b / odd / ".github").mkdir(parents=True)
                (b / odd / ".github" / "pull_request_template.md").write_text(TPL_B, encoding="utf-8")
            where = a if body_in == "a" else b
            (where / "body.md").write_text(body, encoding="utf-8")
            cmd = cmd.replace("B_DIR", str(b)).replace("BODY", str(where / "body.md"))
            payload = {"tool_input": {"command": cmd}}
            extra = {k: v.replace("B_DIR", str(b)) for k, v in (env_extra or {}).items()}
            if payload_cwd:
                payload["cwd"] = str({"a": a, "b": b}[payload_cwd])
            done = run_hook("guard-claims.sh", cwd=a, stdin=json.dumps(payload),
                            env_extra={"CLAUDE_PLUGIN_ROOT": str(HOOKS.parents[1]), "HOME": str(a), **extra})
            return done if with_output else done[0]

    check("guard-claims: a `cd <other repo>` is judged against that repo's template (#1509)",
          run_in("cd B_DIR && gh pr create --base dev --body-file BODY", FULL) == 2, "exit 0")
    check("guard-claims: ...and a body fitting the cd target's template passes there",
          run_in("cd B_DIR && gh pr create --base dev --body-file BODY", FITS_B) == 0, "exit 2")
    check("guard-claims: no cd is the session repo's template (control)",
          run_in("gh pr create --base dev --body-file BODY", FITS_B) == 2, "exit 0")
    rc, out = run_in("cd B_DIR && gh pr create -R o/r --base dev --body-file BODY", FULL, with_output=True)
    check("guard-claims: -R after a cd is still another repository, NOT checked (control)",
          rc == 0 and "NOT checked (-R" in out, f"exit {rc}: {out[-120:]}")
    check("guard-claims: a relative --body-file is read from the cd target",
          run_in("cd B_DIR && gh pr create --base dev --body-file body.md", FITS_B, body_in="b") == 0
          and run_in("cd B_DIR && gh pr create --base dev --body-file body.md", FULL, body_in="b") == 2,
          "the relative body was not read from B")
    check("guard-claims: an issue comment's relative body is read from the cd target too, and its claims checked",
          run_in("cd B_DIR && gh issue comment 5 --body-file body.md", NUMERIC, body_in="b") == 2, "exit 0")
    check("guard-claims: `--body-file b.md; echo done` reads b.md, not `b.md;` (#1516)",
          run_in("cd B_DIR && gh pr create --body-file body.md; echo done", FULL, body_in="b") == 2
          and run_in("cd B_DIR && gh pr create --body-file body.md; echo done", FITS_B, body_in="b") == 0,
          "the body was not read")
    check("guard-claims: the command starts in the payload's cwd, not the hook's own directory",
          run_in("gh pr create --body-file BODY", FULL, payload_cwd="b") == 2
          and run_in("gh pr create --body-file BODY", FITS_B, payload_cwd="b") == 0, "judged against A")
    # THE ALLOWLIST (#1516, round 3). A cd is followed only in the simple grammar: top-level segments joined
    # by `&&`, `;` or a newline, before the gh segment, each `cd [-P|-L] <one path>` with an optional `>`/`2>`
    # redirect; the gh segment may carry a known wrapper. FULL fits A and not B, so exit 2 means B was read.
    for label, cmd in (
            ("`cd B;`", "cd B_DIR; gh pr create --body-file BODY"),
            ("a newline after the cd", "cd B_DIR\ngh pr create --body-file BODY"),
            ("a quoted path", 'cd "B_DIR" && gh pr create --body-file BODY'),
            ("a double-quoted glob path, which the shell takes literally (#1605)", 'cd "[b]" && gh pr create --body-file BODY'),
            ("a single-quoted brace path, which the shell takes literally (#1605)", "cd '{b1,b2}' && gh pr create --body-file BODY"),
            ("a single-quoted `?`, which the shell takes literally (#1605)", "cd '?' && gh pr create --body-file BODY"),
            ("a single-quoted `*`, which the shell takes literally (#1605)", "cd '*' && gh pr create --body-file BODY"),
            ("a backslash-escaped bracket path, which the shell takes literally (#1605)", "cd \\[b\\] && gh pr create --body-file BODY"),
            ("two cds in a row", "cd B_DIR/.. && cd b && gh pr create --body-file BODY"),
            ("a cd with its stderr redirected", "cd B_DIR 2>/dev/null && gh pr create --body-file BODY"),
            ("a cd with its stdout redirected", "cd B_DIR >/dev/null && gh pr create --body-file BODY"),
            ("`cd 5 >/dev/null` (5 is the directory, not an fd)", "cd 5 >/dev/null && gh pr create --body-file BODY"),
            ("a leading comment line", "# open the PR\ncd B_DIR && gh pr create --body-file BODY"),
            ("a leading comment with an apostrophe", "# don't open this from A\ncd B_DIR && gh pr create --body-file BODY"),
            ("a comment after the cd", "cd B_DIR # go to B\ngh pr create --body-file BODY"),
            ("a `#` inside a word", "cd B_DIR/x#y && gh pr create --body-file BODY"),
            ("a `#` inside a quoted path", 'cd "B_DIR/x #y" && gh pr create --body-file BODY'),
            ("an escaped space before `#` (S-b)", "cd B_DIR/x\\ #y && gh pr create --body-file BODY"),
            ("a `~/` path", "cd ~/../b && gh pr create --body-file BODY"),
            ("a redirect before the cd", ">/dev/null cd B_DIR && gh pr create --body-file BODY"),
            ("`env gh`", "cd B_DIR && env gh pr create --body-file BODY"),
            ("`env VAR=1 gh`", "cd B_DIR && env PAGER=cat gh pr create --body-file BODY"),
            ("`VAR=1 gh`", "cd B_DIR && PAGER=cat gh pr create --body-file BODY"),
            ("`command -p gh`", "cd B_DIR && command -p gh pr create --body-file BODY"),
            ("an absolute path to gh", "cd B_DIR && /opt/homebrew/bin/gh pr create --body-file BODY"),
            ("`timeout 60 gh`", "cd B_DIR && timeout 60 gh pr create --body-file BODY"),
            ("`timeout -k 5 60 gh`", "cd B_DIR && timeout -k 5 60 gh pr create --body-file BODY"),
            ("`nohup gh`", "cd B_DIR && nohup gh pr create --body-file BODY"),
            ("`nice -n 5 gh`", "cd B_DIR && nice -n 5 gh pr create --body-file BODY"),
            ("`exec gh`", "cd B_DIR && exec gh pr create --body-file BODY"),
            ("`time -p gh`", "cd B_DIR && time -p gh pr create --body-file BODY")):
        rc, out = run_in(cmd, FULL, with_output=True)
        # B's own missing section, not just exit 2: a crashing resolver also exits 2, by blocking.
        check(f"guard-claims: {label} is followed to the cd target's template (#1516 allowlist)",
              rc == 2 and "## Risk" in out, f"exit {rc}: {out[-140:]}")
    check("guard-claims: `cd B && env gh` with a body fitting B passes there (control)",
          run_in("cd B_DIR && env gh pr create --body-file BODY", FITS_B) == 0, "exit 2")
    check("guard-claims: with no cd, a command before gh leaves it in the starting repo (control)",
          run_in("git push -u origin x && gh pr create --body-file BODY", FITS_B) == 2, "exit 0")
    for label, cmd in (("known-safe commands and an assignment before gh", "X=1 git status && echo ok | head -1; gh pr create --body-file BODY"),
                       ("a `[ ... ]` test before gh: a lone `[` is not a glob (#1605)", "[ -d . ] && gh pr create --body-file BODY"),
                       ("a logical `cd link/..`, as bash resolves it", "cd linkSub/.. && gh pr create --body-file BODY")):
        rc, out = run_in(cmd, "Tidy the README.\n", with_output=True)
        check(f"guard-claims: {label} is judged in the starting repo (control, #1516 round 4)",
              rc == 2 and "## What changed" in out, f"exit {rc}: {out[-140:]}")
    # CANNOT TELL: anything else, so ALLOW WITH A LOUD NOTICE (the maintainer's decision on #1509). NEITHER
    # fits no template, so a judgement against either repository exits 2; only the notice path exits 0.
    NEITHER = "Tidy the README.\n"
    NOTICE = "NOT checked (the directory gh runs in could not be resolved"
    for label, cmd in (
            # round 3: N1-N5, each judged against the wrong repository at 600614d
            # round 4: B1, `-P` resolves physically, so it is out of the grammar; B2, the no-cd shortcut is an
            # allowlist of command words too, so a builtin it does not know (zsh `chdir`) cannot slip past
            ("B1 `cd -P`", "cd -P B_DIR && gh pr create --body-file BODY"),
            ("B1 `cd -P link/..`", "cd -P linkSub/.. && gh pr create --body-file BODY"),
            ("B1 `cd -P link && cd ..`", "cd -P linkSub && cd .. && gh pr create --body-file BODY"),
            ("B1 `cd -L`", "cd -L B_DIR && gh pr create --body-file BODY"),
            ("B2 zsh `chdir`", "chdir B_DIR; gh pr create --body-file BODY"),
            ("B2 `builtin source`", "builtin source /dev/null && gh pr create --body-file BODY"),
            ("B2 `command .`", "command . /dev/null && gh pr create --body-file BODY"),
            ("B2 a command word from a variable", "x=cd; $x B_DIR; gh pr create --body-file BODY"),
            ("B2 an ANSI-quoted `$'cd'`", "$'cd' B_DIR; gh pr create --body-file BODY"),
            ("B2 an unknown command (an alias or function may cd)", "proj && gh pr create --body-file BODY"),
            # round 5: GIT_DIR / GIT_WORK_TREE pick gh's repository whatever the directory
            ("R5 `GIT_DIR=B/.git gh`", "GIT_DIR=B_DIR/.git gh pr create --body-file BODY"),
            ("R5 `cd B && GIT_DIR=A/.git gh`", "cd B_DIR && GIT_DIR=../a/.git gh pr create --body-file BODY"),
            ("R5 `GIT_WORK_TREE=B gh`", "GIT_WORK_TREE=B_DIR gh pr create --body-file BODY"),
            ("R5 `env GIT_DIR=… gh`", "env GIT_DIR=B_DIR/.git gh pr create --body-file BODY"),
            ("R5 `GIT_DIR=…;` before gh", "GIT_DIR=B_DIR/.git; gh pr create --body-file BODY"),
            ("R5 `export GIT_DIR=…;` before gh", "export GIT_DIR=B_DIR/.git; gh pr create --body-file BODY"),
            ("R5 `export GIT_WORK_TREE=…;` before gh", "export GIT_WORK_TREE=B_DIR; gh pr create --body-file BODY"),
            # round 6: any GIT_* / GH_* is the class, not a list; the reviewer's four, then two of the class
            ("R6 `GIT_COMMON_DIR`", "GIT_COMMON_DIR=B_DIR/.git gh pr create --body-file BODY"),
            ("R6 `GIT_CONFIG_GLOBAL`", "GIT_CONFIG_GLOBAL=B_DIR/gitconfig gh pr create --body-file BODY"),
            ("R6 `GIT_CONFIG_COUNT/KEY_0/VALUE_0`",
             "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=url.x.insteadOf GIT_CONFIG_VALUE_0=y gh pr create --body-file BODY"),
            ("R6 `GIT_CONFIG_PARAMETERS`", "GIT_CONFIG_PARAMETERS=\"'remote.origin.url'='x'\" gh pr create --body-file BODY"),
            ("R6 an arbitrary `GIT_FOO=1` (the class)", "GIT_FOO=1 gh pr create --body-file BODY"),
            ("R6 `GH_HOST` (the class)", "GH_HOST=example.com gh pr create --body-file BODY"),
            ("R6 `GH_REPO`, folded into the class", "cd B_DIR && GH_REPO=o/r gh pr create --body-file BODY"),
            ("R6 `export GH_HOST=…;` before gh", "export GH_HOST=example.com; gh pr create --body-file BODY"),
            ("R6 `GH_HOST=…;` before gh", "GH_HOST=example.com; gh pr create --body-file BODY"),
            # round 7: HOME / XDG_CONFIG_HOME set by the command move git's global config (insteadOf); the rest of
            # the config-redirecting family, each shown with real gh 2.97.0 (`gh browse -n`)
            ("R7 `HOME=… gh`", "HOME=B_DIR/h gh pr create --body-file BODY"),
            ("R7 `XDG_CONFIG_HOME=… gh`", "XDG_CONFIG_HOME=B_DIR/x gh pr create --body-file BODY"),
            ("R7 `env HOME=… gh`", "env HOME=B_DIR/h gh pr create --body-file BODY"),
            ("R7 `HOME=…;` before gh", "HOME=B_DIR/h; gh pr create --body-file BODY"),
            ("R7 `export HOME=…;` before gh", "export HOME=B_DIR/h; gh pr create --body-file BODY"),
            ("R7 `export XDG_CONFIG_HOME=…;` before gh", "export XDG_CONFIG_HOME=B_DIR/x; gh pr create --body-file BODY"),
            ("R7 `GIT_CONFIG_SYSTEM`", "GIT_CONFIG_SYSTEM=B_DIR/c gh pr create --body-file BODY"),
            ("R7 `GIT_CONFIG_NOSYSTEM`", "GIT_CONFIG_NOSYSTEM=1 gh pr create --body-file BODY"),
            ("R7 `GH_CONFIG_DIR`", "GH_CONFIG_DIR=B_DIR/g gh pr create --body-file BODY"),
            ("R7 `git config --global …insteadOf` before gh", "git config --global url.b.insteadOf a && gh pr create --body-file BODY"),
            ("R7 `git config …insteadOf` before gh", "git config url.b.insteadOf a; gh pr create --body-file BODY"),
            ("R7 `git remote set-url` before gh", "git remote set-url origin b; gh pr create --body-file BODY"),
            ("R7 `gh repo set-default` before gh", "gh repo set-default o/b && gh pr create --body-file BODY"),
            ("R7 an unknown git option before gh", "git --exec-path=x status && gh pr create --body-file BODY"),
            ("R7 a write into .git/config before gh", "echo x >> .git/config; gh pr create --body-file BODY"),
            ("R7 `sed -i` on .git/config before gh", "sed -i.bak s/a/b/ .git/config; gh pr create --body-file BODY"),
            ("N1 `env -C/dir`", "env -CB_DIR gh pr create --body-file BODY"),
            ("N1 `env -iC dir`", "env -iC B_DIR gh pr create --body-file BODY"),
            ("N1 `env -C dir`", "env -C B_DIR gh pr create --body-file BODY"),
            ("N1 `env --chdir=dir`", "env --chdir=B_DIR gh pr create --body-file BODY"),
            ("N1 `env -i` (any env option)", "cd B_DIR && env -i gh pr create --body-file BODY"),
            ("N2 `eval \"cd B\"`", 'eval "cd B_DIR" && gh pr create --body-file BODY'),
            ("N2 `eval cd B;`", "eval cd B_DIR; gh pr create --body-file BODY"),
            ("N2 `eval \"$VAR\"`, with no cd in sight", 'eval "$GO" && gh pr create --body-file BODY'),
            ("N3 a cd in an if/else", "if true; then cd B_DIR; else cd .; fi; gh pr create --body-file BODY"),
            ("N3 a cd in an if that did not run", "if false; then cd B_DIR; fi; gh pr create --body-file BODY"),
            ("N3 a cd in a while body", "while false; do cd B_DIR; done; gh pr create --body-file BODY"),
            ("N3 a cd in a while condition", "while cd B_DIR; do gh pr create --body-file BODY ; break; done"),
            ("N3 a cd in an until condition", "until cd B_DIR; do :; done; gh pr create --body-file BODY"),
            ("N3 a cd in a for body", "for x in 1; do cd B_DIR; done; gh pr create --body-file BODY"),
            ("N4 `false && cd B; gh`", "false && cd B_DIR; gh pr create --body-file BODY"),
            ("N4 `true || cd B; gh`", "true || cd B_DIR; gh pr create --body-file BODY"),
            ("N5 `$((1<<2))` before the cd", "echo $((1<<2))\ncd B_DIR && gh pr create --body-file BODY"),
            ("N5 `(( n = 1 << 2 ))` before the cd", "(( n = 1 << 2 ))\ncd B_DIR && gh pr create --body-file BODY"),
            # everything else outside the grammar
            ("a cd inside a subshell", "(cd B_DIR) && gh pr create --body-file BODY"),
            ("a cd inside a brace group", "{ cd B_DIR; } && gh pr create --body-file BODY"),
            ("a cd in a case branch", "case x in x) cd B_DIR && gh pr create --body-file BODY;; esac"),
            ("a gh after a case", "case x in x) cd B_DIR;; esac; gh pr create --body-file BODY"),
            ("`builtin cd`", "builtin cd B_DIR && gh pr create --body-file BODY"),
            ("`command cd`", "command cd B_DIR && gh pr create --body-file BODY"),
            ("an assignment before the cd", "X=1 cd B_DIR && gh pr create --body-file BODY"),
            ("another command between the cd and gh", "cd B_DIR && git log --oneline -1 # sanity\ngh pr create --body-file BODY"),
            ("an echo before the cd", "echo 'gh pr create' && cd B_DIR && gh pr create --body-file BODY"),
            ("a heredoc before the cd", "cat > /dev/null <<'EOF'\nit's a body\nEOF\ncd B_DIR && gh pr create --body-file BODY"),
            ("a function body's cd", "f() { cd B_DIR; }; gh pr create --body-file BODY"),
            ("a `function` keyword body's cd", "function f { cd B_DIR; }; gh pr create --body-file BODY"),
            ("gh inside `bash -c`", 'bash -c "cd B_DIR && gh pr create --body-file BODY"'),
            ("gh behind `sudo` after a cd", "cd B_DIR && sudo gh pr create --body-file BODY"),
            ("gh behind `sudo` with no cd", "sudo gh pr create --body-file BODY"),
            ("gh in an if with no cd", "if true; then gh pr create --body-file BODY; fi"),
            ("a cd run as a program (`env cd`)", "env cd B_DIR && gh pr create --body-file BODY"),
            ("`source` before gh", "source /dev/null && gh pr create --body-file BODY"),
            ("`. file` in an if", "if true; then . /dev/null; fi; gh pr create --body-file BODY"),
            ("`X=1 . file`", "X=1 . /dev/null && gh pr create --body-file BODY"),
            ("a cd with an input redirect", "cd B_DIR </dev/null && gh pr create --body-file BODY"),
            ("a cd to ~user", "cd ~nobody && gh pr create --body-file BODY"),
            ("an unquoted `[b]` glob in a cd path (#1605)", "cd [b] && gh pr create --body-file BODY"),
            ("an unquoted `{b1,b2}` brace list in a cd path (#1605)", "cd {b1,b2} && gh pr create --body-file BODY"),
            ("an unquoted `x*` glob in a cd path (#1605)", "cd x* && gh pr create --body-file BODY"),
            ("an unquoted `y?` glob in a cd path (#1605)", "cd y? && gh pr create --body-file BODY"),
            ("a bare unquoted `?` as a cd path (#1605)", "cd ? && gh pr create --body-file BODY"),
            ("a bare unquoted `*` as a cd path (#1605)", "cd * && gh pr create --body-file BODY"),
            ("an unquoted `[b]` glob followed by `/..` (#1605: normpath would collapse it back to the start)", "cd [b]/.. && gh pr create --body-file BODY"),
            ("an unquoted `x*` glob followed by `/..` (#1605)", "cd x*/.. && gh pr create --body-file BODY"),
            ("`pushd`", "pushd B_DIR && gh pr create --body-file BODY"),
            ("a bare `cd`", "cd && gh pr create --body-file BODY"),
            ("`cd -`", "cd - && gh pr create --body-file BODY"),
            ("a cd with two arguments", "cd B_DIR x && gh pr create --body-file BODY"),
            ("a cd to a variable", "cd $NOWHERE && gh pr create --body-file BODY"),
            ("a negated cd", "! cd B_DIR && gh pr create --body-file BODY"),
            ("a cd to a missing directory", "cd B_DIR/missing && gh pr create --body-file BODY"),
            ("a cd joined by ||", "cd B_DIR || gh pr create --body-file BODY"),
            ("a cd joined by |", "cd B_DIR | gh pr create --body-file BODY"),
            ("a cd joined by &", "cd B_DIR & gh pr create --body-file BODY"),
            ("an unbalanced quote before the cd", "echo it's\ncd B_DIR && gh pr create --body-file BODY")):
        rc, out = run_in(cmd, NEITHER, with_output=True)
        check(f"guard-claims: {label} is NOT checked, with the notice, never a guessed template (#1516 allowlist)",
              rc == 0 and NOTICE in out, f"exit {rc}: {out[-140:]}")
    rc, out = run_in("gh pr create --body-file BODY", NEITHER, with_output=True,
                     env_extra={"GIT_DIR": "B_DIR/.git"})
    check("guard-claims: GIT_DIR inherited by the hook is NOT checked, with the notice (#1516 round 5)",
          rc == 0 and NOTICE in out, f"exit {rc}: {out[-140:]}")
    rc, out = run_in("GIT_PAGER=cat git status && X=1; gh pr create --body-file BODY", NEITHER, with_output=True)
    check("guard-claims: other assignments before gh keep the starting repo (control, #1516 round 5)",
          rc == 2 and "## What changed" in out, f"exit {rc}: {out[-140:]}")
    # round 6: a GIT_* on an earlier SAFE command is that command's own environment, so gh is judged normally;
    # GH_HOST inherited is the class too; GIT_EDITOR, which the harness sets, is not.
    rc, out = run_in("GIT_DIR=B_DIR/.git git status && gh pr create --body-file BODY", NEITHER, with_output=True)
    check("guard-claims: a GIT_* on an earlier SAFE command does not reach gh (control, #1516 round 6)",
          rc == 2 and "## What changed" in out, f"exit {rc}: {out[-140:]}")
    rc, out = run_in("gh pr create --body-file BODY", NEITHER, with_output=True, env_extra={"GH_HOST": "example.com"})
    check("guard-claims: GH_HOST inherited by the hook is NOT checked, with the notice (#1516 round 6)",
          rc == 0 and NOTICE in out, f"exit {rc}: {out[-140:]}")
    # round 7: each of these is that process's own, so gh is judged normally (shown with real gh)
    for label, cmd in (("an inherited HOME", "gh pr create --body-file BODY"),
                       ("`git -c url…insteadOf=… status` before gh", "git -c url.b.insteadOf=a status && gh pr create --body-file BODY"),
                       ("`git --config-env=…` before gh", "V=a git --config-env=url.b.insteadOf=V status && gh pr create --body-file BODY"),
                       ("`HOME=… git status` before gh", "HOME=B_DIR/h git status && gh pr create --body-file BODY"),
                       ("a redirect to /dev/null and an fd before gh", "git status >/dev/null 2>&1 && gh pr create --body-file BODY"),
                       ("`gh pr view` before gh", "gh pr view 1 && gh pr create --body-file BODY")):
        rc, out = run_in(cmd, NEITHER, with_output=True)
        check(f"guard-claims: {label} is judged in the starting repo (control, #1516 round 7)",
              rc == 2 and "## What changed" in out, f"exit {rc}: {out[-140:]}")
    rc, out = run_in("gh pr create --body-file BODY", NEITHER, with_output=True, env_extra={"GIT_EDITOR": "true"})
    check("guard-claims: an inherited GIT_EDITOR (the harness sets it) is still judged (control, #1516 round 6)",
          rc == 2 and "## What changed" in out, f"exit {rc}: {out[-140:]}")
    rc, out = run_in("cd sub && gh pr create --body-file BODY", NEITHER, with_output=True,
                     env_extra={"CDPATH": "B_DIR"})
    check("guard-claims: a relative cd with CDPATH set is NOT checked, with the notice (#1516 allowlist)",
          rc == 0 and NOTICE in out, f"exit {rc}: {out[-140:]}")
    # S-a: a RELATIVE body with an unresolved directory cannot be located. The message still says the template
    # and the change type were NOT checked, and why.
    rc, out = run_in("if true; then cd B_DIR; fi; gh pr create --body-file body.md", NEITHER, body_in="b", with_output=True)
    check("guard-claims: an unlocatable relative body still says NOT checked, and why (#1516 S-a)",
          rc == 0 and NOTICE in out and "template" in out, f"exit {rc}: {out[-140:]}")
    check("guard-claims: an issue comment is not held to the PR template",
          run("gh issue comment 5 --body-file BODY", "Tidy the README.\n", template=TPL) == 0, "exit 2")
    # OUT OF SCOPE, AND THE BODY MUST CARRY A CLAIM. A first draft passed a claim-FREE body here,
    # so these could not reach the check at all: deleting the `gh pr create` scope test left them
    # green, and the mutation SURVIVED. A control that cannot reach the code it guards proves
    # nothing. With a numeric body, any widening of the scope fails right here.
    for cmd in ("git status", "gh pr view 42", "gh pr merge 42 --merge",
                # STILL out of scope, deliberately: widening is one verb at a time, and a new
                # issue goes through /rails-flow:report which has its own shape.
                "gh issue create --title x --body-file BODY",
                "gh issue list --limit 5",
                "gh release create v1.0.0 --notes-file BODY"):
        check(f"guard-claims: `{cmd[:34]}` is out of scope even with a numeric body",
              run(cmd, NUMERIC) == 0, "exit 2")

    # The audited escape. A fail-closed guard with no visible way past it gets disabled the first
    # time it is wrong, and then it protects nothing.
    check("guard-claims: RAILS_FLOW_CLAIMS_OK=1 overrides, and says so",
          run("gh pr create --base dev --body-file BODY", NUMERIC,
              env_extra={"RAILS_FLOW_CLAIMS_OK": "1"}) == 0, "exit 2")

    # ---- the change-type declaration (doctrine-map's one tracked gap, #1106) ----
    # The map carried this as a GAP whose recorded reason was "it would live in CI against the PR
    # body, which no gate in this repo reads". This hook reads the PR body, so it is mechanisable
    # now. Driven in a real git repo, because the rule is scoped by `git diff --name-only`.
    def run_in_repo(cmd: str, body: str, touch: str) -> int:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "body.md").write_text(body, encoding="utf-8")
            target = root / touch
            target.parent.mkdir(parents=True, exist_ok=True)
            for args in (["init", "-q", "-b", "main"],):
                _run(["git", *args], cwd=root, capture_output=True)
            target.write_text("x\n", encoding="utf-8")
            _run(["git", "add", "-A"], cwd=root, capture_output=True)
            _run(["git", "-c", "user.email=f@e", "-c", "user.name=f",
                            "commit", "-qm", "base"], cwd=root, capture_output=True)
            target.write_text("changed\n", encoding="utf-8")
            return run_hook("guard-claims.sh", cwd=root,
                            stdin=json.dumps({"tool_input": {
                                "command": cmd.replace("BODY", str(root / "body.md"))}}),
                            env_extra={"CLAUDE_PLUGIN_ROOT": str(HOOKS.parents[1])})[0]

    CREATE = "gh pr create --base dev --body-file BODY"
    check("guard-claims: a skills/** PR naming no change type is blocked",
          run_in_repo(CREATE, "Tidy the wording.\n", "skills/rails-8/references/x.md") == 2, "exit 0")
    # MUST PASS, both declarations. A rule that accepted neither would block every skill PR.
    check("guard-claims: ...unless it says framework claim",
          run_in_repo(CREATE, "Change type: a framework claim, verified against the docs.\n",
                      "skills/rails-8/references/x.md") == 0, "exit 2")
    check("guard-claims: ...or architecture decision",
          run_in_repo(CREATE, "Our own design — an architecture decision.\n",
                      "skills/rails-8/references/x.md") == 0, "exit 2")
    # SCOPE: a PR touching no skill is not subject to the rule, whatever its body says.
    check("guard-claims: a PR touching no skill needs no change type",
          run_in_repo(CREATE, "Tidy the wording.\n", "scripts/x.py") == 0, "exit 2")
    # #1516 review: the change-type check ran `git diff` in the SESSION's repo. A session with a modified
    # skills/ file blocked `cd <other repo> && gh pr create` for a PR that touches nothing there.
    def run_skills_cd(cmd: str) -> int:
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td) / "a", Path(td) / "b"
            for d in (a, b):
                d.mkdir()
                _run(["git", "init", "-q", "-b", "main"], cwd=d, capture_output=True)
                (d / "README.md").write_text("x\n", encoding="utf-8")
            (a / "skills").mkdir()
            (a / "skills" / "x.md").write_text("x\n", encoding="utf-8")
            for d in (a, b):
                _run(["git", "add", "-A"], cwd=d, capture_output=True)
                _run(["git", "-c", "user.email=f@e", "-c", "user.name=f", "commit", "-qm", "base"],
                     cwd=d, capture_output=True)
            (a / "skills" / "x.md").write_text("changed\n", encoding="utf-8")
            # STAGED, because another repository is read through its staged diff only (no code from the target,
            # #1516): an unstaged change would let a hook that read the wrong repository look right.
            _run(["git", "add", "skills/x.md"], cwd=a, capture_output=True)
            (b / "body.md").write_text("Tidy the wording.\n", encoding="utf-8")
            return run_hook("guard-claims.sh", cwd=a, stdin=json.dumps({"tool_input": {
                "command": cmd.replace("B_DIR", str(b))}}),
                env_extra={"CLAUDE_PLUGIN_ROOT": str(HOOKS.parents[1])})[0]

    check("guard-claims: the skills/** change-type check reads the cd target's diff, not the session's (#1516)",
          run_skills_cd("cd B_DIR && gh pr create --base dev --body-file body.md") == 0, "exit 2")
    check("guard-claims: ...and without the cd the session's skills/ change is still held to it (control)",
          run_skills_cd("gh pr create --base dev --body-file B_DIR/body.md") == 2, "exit 0")

    # NO CODE RUNS BEFORE PERMISSION (#1516, push security reviews). The hook reads `git diff` in the directory
    # the command `cd`s into, and a hook runs BEFORE the person is asked about the command. A repository's own
    # config can name a program that `git diff` executes: `core.fsmonitor` on any diff, and a `filter.<name>.clean`
    # on a diff that hashes a changed working-tree file. Disabling one key was not enough (the first fix left the
    # clean filter running), so the hook reads a repository other than the session's with only the staged diff, which
    # hashes nothing. The marker file is what the program writes; it must not exist afterwards.
    def run_exec_cd(cmd: str, vector: str, stage_skills: bool = False) -> tuple[int, bool]:
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td) / "a", Path(td) / "b"
            marker, script = Path(td) / "PROGRAM_RAN", Path(td) / "program.sh"
            script.write_text(f"#!/bin/sh\necho ran >> '{marker}'\n" + ("cat\n" if vector == "filter" else ""),
                              encoding="utf-8")
            script.chmod(0o755)
            for d in (a, b):
                d.mkdir()
                _run(["git", "init", "-q", "-b", "main"], cwd=d, capture_output=True)
                (d / "README.md").write_text("x\n", encoding="utf-8")
            (b / ".gitattributes").write_text("*.md filter=evil\n", encoding="utf-8")
            (b / "skills").mkdir()
            (b / "skills" / "x.md").write_text("x\n", encoding="utf-8")
            for d in (a, b):
                _run(["git", "add", "-A"], cwd=d, capture_output=True)
                _run(["git", "-c", "user.email=f@e", "-c", "user.name=f", "commit", "-qm", "base"],
                     cwd=d, capture_output=True)
            (b / "README.md").write_text("changed\n", encoding="utf-8")        # a working-tree change to hash
            if stage_skills:
                (b / "skills" / "x.md").write_text("changed\n", encoding="utf-8")
                _run(["git", "add", "skills/x.md"], cwd=b, capture_output=True)
            (b / "body.md").write_text("Tidy the wording.\n", encoding="utf-8")
            key = "core.fsmonitor" if vector == "fsmonitor" else "filter.evil.clean"
            _run(["git", "config", key, str(script)], cwd=b, capture_output=True)
            rc = run_hook("guard-claims.sh", cwd=a, stdin=json.dumps({"tool_input": {
                "command": cmd.replace("B_DIR", str(b))}}),
                env_extra={"CLAUDE_PLUGIN_ROOT": str(HOOKS.parents[1])})[0]
            return rc, marker.exists()

    CD_B = "cd B_DIR && gh pr create --base dev --body-file body.md"
    rc, ran = run_exec_cd(CD_B, "fsmonitor")
    check("guard-claims: a cd into a repository whose core.fsmonitor names a program does not run it "
          "(no code before permission, #1516)", not ran, f"exit {rc}: the repository's own program ran in the hook")
    rc, ran = run_exec_cd(CD_B, "filter")
    check("guard-claims: a cd into a repository whose filter.<name>.clean names a program does not run it "
          "(no code before permission, #1516)", not ran, f"exit {rc}: the repository's own program ran in the hook")
    rc, ran = run_exec_cd(CD_B, "filter", stage_skills=True)
    check("guard-claims: ...and the cd target's STAGED skills/ change is still read without running anything (control)",
          rc == 2 and not ran, f"exit {rc}, program ran: {ran}")

    # A LARGE DIFF MUST NOT FAIL OPEN (#1516, push security review; the SIGPIPE class of #1579). `git diff --name-only |
    # grep -q` under `set -o pipefail` loses the match when the name list outgrows the pipe buffer: `grep -q` leaves at
    # the first hit, `git` dies of SIGPIPE, the pipeline reports failure and the gate reads "no skills/ change". 2500
    # staged files with long names are about 170 KiB, well past the 64 KiB buffer.
    def run_big_skills_diff(cmd: str, big_repo: str) -> int:
        with tempfile.TemporaryDirectory() as td:
            a, b = Path(td) / "a", Path(td) / "b"
            for d in (a, b):
                d.mkdir()
                _run(["git", "init", "-q", "-b", "main"], cwd=d, capture_output=True)
                (d / "README.md").write_text("x\n", encoding="utf-8")
                _run(["git", "add", "-A"], cwd=d, capture_output=True)
                _run(["git", "-c", "user.email=f@e", "-c", "user.name=f", "commit", "-qm", "base"],
                     cwd=d, capture_output=True)
            big = a if big_repo == "session" else b
            (big / "skills").mkdir()
            for i in range(2500):
                (big / "skills" / f"s{i:04d}-a-fairly-long-file-name-so-the-name-list-outgrows-a-pipe-buffer.md").write_text(
                    "x\n", encoding="utf-8")
            _run(["git", "add", "-A"], cwd=big, capture_output=True)
            (b / "body.md").write_text("Tidy the wording.\n", encoding="utf-8")
            return run_hook("guard-claims.sh", cwd=a, stdin=json.dumps({"tool_input": {
                "command": cmd.replace("B_DIR", str(b))}}),
                env_extra={"CLAUDE_PLUGIN_ROOT": str(HOOKS.parents[1])})[0]

    check("guard-claims: a large staged skills/ list in the session's repository is still held to the change-type rule "
          "(no SIGPIPE fail-open, #1516)",
          run_big_skills_diff("gh pr create --base dev --body-file B_DIR/body.md", "session") == 2, "exit 0")
    check("guard-claims: a large staged skills/ list in the cd target is still held to the change-type rule "
          "(no SIGPIPE fail-open, #1516)",
          run_big_skills_diff("cd B_DIR && gh pr create --base dev --body-file body.md", "target") == 2, "exit 0")

    # FAILS OPEN when it cannot read the body. This guard's job is to make the check happen where
    # it can, never to block opening a PR because a path could not be resolved.
    check("guard-claims: an unreadable body file fails OPEN rather than blocking",
          run("gh pr create --base dev --body-file /nonexistent/body.md") == 0, "exit 2")
    check("guard-claims: an inline --body fails open too",
          run('gh pr create --base dev --body "292 assertions, up from 285"') == 0, "exit 2")


# ---- release-gate.sh (qa-flow) shares the normaliser: drive it too, or the "one normaliser" claim is prose (#906) ----
QA_HOOK = HOOKS.parents[2] / "qa-flow" / "hooks" / "scripts" / "release-gate.sh"


def _pin(cmd: str, head: str) -> str:
    """`cmd` with the head a PR merge into main acts on pinned (#1571). A merge that does not pin it is denied before it
    is judged, so a fixture that is about WHICH repository, or WHETHER the head is certified, must carry the pin.
    Commands that are not a PR merge come back unchanged."""
    if re.search(r"\bgh\s+pr\b.*\bmerge\b", cmd):         # flags may sit between `pr` and `merge`
        return f"{cmd} --match-head-commit {head}"
    if re.search(r"pulls/\d+/merge", cmd):
        return re.sub(r"(pulls/\d+/merge)", rf"\1 -f sha={head}", cmd, count=1)
    return cmd


def release_gate_fixtures() -> None:
    if not QA_HOOK.is_file():
        check("release-gate.sh present beside rails-flow", False, str(QA_HOOK))
        return

    def run(cmd: str, marketplace: bool = False, plugin_root: Path | None = None,
            origin: str | None = "https://github.com/fmanimashaun/claude-skills.git",
            git_config: tuple[tuple[str, ...], ...] = (), extra_env: dict[str, str] | None = None) -> int:
        with tempfile.TemporaryDirectory() as td:
            _git_repo(Path(td))
            # ON A FEATURE BRANCH (#1410). `git init` leaves HEAD on main, where a bare `git push`
            # really IS a push to main -- so a parser handed the quote-stripped `git push origin `
            # was still blocked, and the fixture could not tell it from one reading the real argument.
            _run(["git", "checkout", "-q", "-b", "feature/work"], cwd=td, check=True,
                           capture_output=True)
            if marketplace:
                # What MAKES a tree a marketplace. No consumer project has one.
                (Path(td) / ".claude-plugin").mkdir(parents=True, exist_ok=True)
                (Path(td) / ".claude-plugin" / "marketplace.json").write_text(
                    '{"name": "x", "plugins": []}', encoding="utf-8")
                if origin:
                    # The exemption is keyed on the repository's identity, not on the file alone (#1569).
                    _run(["git", "remote", "add", "origin", origin], cwd=td, check=True, capture_output=True)
            for args in git_config:
                _run(["git", *args], cwd=td, check=True, capture_output=True)
            env = dict(os.environ); env.pop("QA_ALLOW_MAIN", None); env.pop("GH_REPO", None)
            env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root or QA_HOOK.parents[2]); env.update(extra_env or {})
            done = _run(["bash", str(QA_HOOK)], cwd=td, input=json.dumps({"tool_input": {"command": cmd}}),
                                  env=env, capture_output=True, text=True, timeout=60)
            return done.returncode

    for cmd in ("git push origin main", "FOO=1 git push origin main", "git -C repo push origin main", "git status; git push origin main"):
        check(f"release-gate: `{cmd}` targets main and is blocked without a certification", run(cmd) == 2, "exit 0")
    for cmd in ('git commit -m "push origin main"', 'echo "git push origin main"', "# git push origin main", "git push origin feature/x"):
        check(f"release-gate: `{cmd}` does not target main and passes", run(cmd) == 0, "exit 2")
    # #1410: `main`/`master` INSIDE a branch name is not a destination. Both were refused
    # downstream on one day, and both authors renamed the branch to get past the gate.
    for cmd in ("git push -u origin fix/1010-one-main", "git push origin feature/main-menu",
                "git push origin main-nav", "git push -u origin feat/983-pr2-master-detail"):
        check(f"release-gate (#1410): `{cmd}` names main only inside a branch name, and passes",
              run(cmd) == 0, "exit 2")
    # ...and every real destination form is still a promotion -- including the QUOTED ones, which
    # the old regex allowed because the normaliser strips quoted spans before it looked.
    for cmd in ("git push origin HEAD:main", "git push origin dev:main", "git push origin refs/heads/main",
                "git push --all origin", 'git push origin "main"', "git push origin 'HEAD:main'"):
        check(f"release-gate (#1410): `{cmd}` targets main and is blocked without a certification",
              run(cmd) == 2, "exit 0")
    check("release-gate (#1410): a bare `git push` from a feature branch passes", run("git push") == 0, "exit 2")
    # A here-string (`<<<`) is a word. Its second `<` once opened a heredoc whose "delimiter" was the next word, and the
    # command after it was deleted with the body: each of these was ALLOWED end to end.
    for cmd in ("cat <<< x; git push origin main", "cat <<<x\ngit push origin main", "git push origin main <<< x",
                "cat <<< x; gh pr merge 5", "cat <<< x\ngh api -X PUT repos/o/r/pulls/5/merge"):
        check(f"release-gate: a here-string before it hides nothing: `{cmd!r}` is blocked", run(cmd) == 2, "exit 0")
    check("release-gate: a here-string before a push to a branch still passes", run("cat <<< x; git push origin feature/x") == 0, "exit 2")
    # #1470 review: the five pushes to main the first parser ALLOWED. Each is blocked end to end.
    for cmd in ("git push origin $(echo main)", "git push origin main>/dev/null",
                "echo done#1; git push origin main", "git push origin HEAD:heads/main",
                "git push origin {main,dev}", "git -C $(pwd) push origin main",
                "git push -v$(true) origin main", "git push --receive-pack=$(echo x) origin main"):
        check(f"release-gate (#1470): `{cmd}` reaches main and is blocked", run(cmd) == 2, "exit 0")
    # 41's delta review of #1470: the hook only handed the parser segments that STARTED with
    # `git push`, so a wrapper, a group, a continuation or a shell string hid the push entirely.
    for cmd in ("timeout 60 git push origin main", "sudo -u bob git push origin main",
                "command git push origin main", "git --no-pager push origin main",
                "( git push origin main )", "{ git push origin main; }", "/usr/bin/git push origin main",
                "git push origin \\\nmain", "bash -c 'git push origin main'", 'eval "git push origin main"',
                "git -c alias.p=push p origin main", "echo main | xargs git push origin",
                "timeout 60 gh pr merge 5", "bash -o pipefail -c 'git push origin main'",
                "g''it push origin main", "gi\\t push origin main", '"g"it push origin main'):
        check(f"release-gate (#1470): `{cmd!r}` reaches main (or cannot be judged) and is blocked",
              run(cmd) == 2, "exit 0")
    for cmd in ("bash -c 'git push origin fix/x'", "timeout 60 git push origin fix/x", "gh pr list"):
        check(f"release-gate (#1470): CONTROL: `{cmd}` passes", run(cmd) == 0, "exit 2")
    check("release-gate (#1470): the current-branch idiom on a feature branch passes",
          run('git push -u origin "$(git branch --show-current)"') == 0, "exit 2")
    # ...and the false refusal that review found: an apostrophe in a heredoc body is not a quote.
    check("release-gate (#1470): a heredoc body with an apostrophe does not block a feature push",
          run("cat > n.md <<'EOF'\nit's done\nEOF\ngit push -u origin fix/x") == 0, "exit 2")
    # An unbalanced quote cannot be tokenised; "could not judge" must deny, never read as "no".
    check("release-gate (#1410): an unparseable push is treated as a promotion",
          run('git push origin "feature/x') == 2, "exit 0")
    # FAIL CLOSED without the parser: the whole-word match over the RAW command still sees a quoted
    # main (the pair's control is the feature push beside it, which must still pass).
    with tempfile.TemporaryDirectory() as bare_root:
        check("release-gate (#1410): parser missing -> a quoted `main` push is still blocked",
              run('git push origin "main"', plugin_root=Path(bare_root)) == 2, "exit 0")
        check("release-gate (#1410): parser missing -> CONTROL: a feature push still passes",
              run("git push origin feature/x", plugin_root=Path(bare_root)) == 0, "exit 2")
        # #1472: without the parser the shared normaliser decides, and it now sees inside a shell string.
        for cmd in ("bash -c 'git push origin main'", 'eval "git push origin main"', "command git push origin main"):
            check(f"release-gate (#1472): parser missing -> `{cmd}` is blocked",
                  run(cmd, plugin_root=Path(bare_root)) == 2, "exit 0")
        check("release-gate (#1472): parser missing -> CONTROL: `bash -c 'git push origin feature/x'` passes",
              run("bash -c 'git push origin feature/x'", plugin_root=Path(bare_root)) == 0, "exit 2")

    # THE DISCRIMINATING PAIR for the marketplace carve-out. The same command, the same absence of
    # a certification, and the ONLY difference is `.claude-plugin/marketplace.json`. Without the
    # first case the gate denies every promotion of its own source repo, which is a gate wrong
    # about correct code; without the second, the carve-out would be indistinguishable from
    # exempting any project that never ran `/qa-flow:setup-qa` -- which is most of them.
    check("release-gate: the marketplace's OWN repo is not a consumer, so promotion passes",
          run("git push origin main", marketplace=True) == 0, "exit 2")
    check("release-gate: an ordinary repo with no certification is STILL blocked",
          run("git push origin main") == 2, "exit 0")
    # #1569: the file alone proves nothing -- any repo can add one. The exemption needs the marketplace's identity.
    for label, origin in (("no origin at all", None), ("another repository's origin", "https://github.com/acme/app.git"),
                          ("a look-alike name", "https://github.com/acme/claude-skills.git"),
                          ("a look-alike owner", "https://github.com/fmanimashaun-evil/claude-skills.git"),
                          ("a path that merely contains the name", "/home/x/fmanimashaun/claude-skills")):
        check(f"release-gate (#1569): a marketplace.json in a repo with {label} is NOT the marketplace, and stays blocked",
              run("git push origin main", marketplace=True, origin=origin) == 2, "exit 0")
    # #1571 review: the exemption described the CONFIGURED origin url, but a push, merge or release goes to the
    # EFFECTIVE target. Each of these leaves `remote.origin.url` naming the marketplace while the command acts on
    # the consumer's repository (acme/app here), and each was exempt.
    mk = "https://github.com/fmanimashaun/"
    acme = "https://github.com/acme/"
    for label, cfg, env in (
            ("a pushurl that points elsewhere", (("config", "remote.origin.pushurl", acme + "app.git"),), None),
            ("a second pushurl that points elsewhere",
             (("config", "remote.origin.pushurl", mk + "claude-skills.git"),
              ("config", "--add", "remote.origin.pushurl", acme + "app.git")), None),
            ("a pushInsteadOf that rewrites the push target",
             (("config", f"url.{acme}.pushInsteadOf", mk),), None),
            ("an insteadOf that rewrites the remote",
             (("config", f"url.{acme}.insteadOf", mk),), None),
            ("a second remote that is another repository",
             (("remote", "add", "fork", acme + "app.git"),), None),
            ("gh's default repo resolved to another remote",
             (("remote", "add", "fork", acme + "app.git"), ("config", "remote.fork.gh-resolved", "base")), None),
            ("gh's default repo named as another repository",
             (("config", "remote.origin.gh-resolved", "acme/app"),), None),
            ("a GH_REPO that names another repository", (), {"GH_REPO": "acme/app"})):
        for cmd in ("git push origin main", "gh release create v9 --target main"):
            check(f"release-gate (#1571 review): a marketplace tree with {label} is NOT exempt for `{cmd}`",
                  run(cmd, marketplace=True, git_config=cfg, extra_env=env) == 2, "exit 0")
    # The pairs: the same configuration shapes that name the marketplace itself, or only change the transport,
    # keep the exemption, so a broken-open and a broken-shut resolver are told apart.
    for label, cfg, env in (
            ("a pushurl that names the marketplace", (("config", "remote.origin.pushurl", mk + "claude-skills.git"),), None),
            ("a pushInsteadOf that only changes the transport",
             (("config", "url.git@github.com:fmanimashaun/.pushInsteadOf", mk),), None),
            ("a second remote that is the marketplace too", (("remote", "add", "fork", mk + "claude-skills.git"),), None),
            ("a gh default that names the marketplace",
             (("config", "remote.origin.gh-resolved", "fmanimashaun/claude-skills"),), None),
            ("GH_REPO naming the marketplace", (), {"GH_REPO": "fmanimashaun/claude-skills"})):
        check(f"release-gate (#1571 review): CONTROL: a marketplace tree with {label} stays exempt",
              run("git push origin main", marketplace=True, git_config=cfg, extra_env=env) == 0, "exit 2")

    # #1337. The stamp is bound to the tested dev sha; committing it to dev by PR moves dev. The gate
    # accepts an ANCESTOR of dev only when the delta since is the stamp itself.
    g = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        _git_repo(repo)
        sh = lambda *a: _run([*g, *a], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
        (repo / "app.rb").write_text("v1\n", encoding="utf-8")
        sh("add", "app.rb"); sh("commit", "-q", "-m", "app")
        tested = sh("rev-parse", "HEAD")
        (repo / "qa").mkdir()
        stamp = {"sha": tested, "date": "2026-09-26", "verdict": "PASS", "report": "qa/reports/r.md"}
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps(stamp), encoding="utf-8")
        env = dict(os.environ); env.pop("QA_ALLOW_MAIN", None); env["CLAUDE_PLUGIN_ROOT"] = str(QA_HOOK.parents[2])
        # These are OLD-shape stamps (no schema), grandfathered only when their commit predates the
        # #1428 cutoff -- so they are committed with an old committer date.
        old_env = {**os.environ, "GIT_COMMITTER_DATE": "2026-09-01T00:00:00+00:00",
                   "GIT_AUTHOR_DATE": "2026-09-01T00:00:00+00:00"}
        sh_old = lambda *a: _run([*g, *a], cwd=repo, check=True, capture_output=True, text=True,
                                           env=old_env).stdout.strip()

        def gate() -> tuple[int, str]:
            sh("branch", "-f", "dev", "HEAD")
            # `git push origin main` ships the LOCAL main (#1569), so the fixture promotes dev by making main it.
            sh("update-ref", "refs/heads/main", "HEAD")
            # The last PUBLISHED release is origin/main (release_evidence reads it before main): the root commit.
            sh("update-ref", "refs/remotes/origin/main", sh("rev-list", "--max-parents=0", "HEAD").split()[0])
            done = _run(["bash", str(QA_HOOK)], cwd=repo, env=env, capture_output=True, text=True, timeout=60,
                                  input=json.dumps({"tool_input": {"command": "git push origin main"}}))
            return done.returncode, done.stderr

        rc, err = gate()
        # #1437 review round 3: the stamp is read as COMMITTED at dev. An uncommitted one is not what
        # main would receive, so it no longer permits -- the old "uncommitted control" inverts.
        # The FIRST stage's own words, which no later stage repeats: the evidence step that follows also denies an
        # uncommitted stamp ("unusable: no qa/CERTIFICATION is committed at ... -- commit the stamp to dev first"),
        # so a hook that read the stamp from the working tree was still denied here and the old assertion could not
        # tell it from the real one (#1571, measured on both). Only stage 1 says to run /qa-flow:certify.
        check("release-gate (#1428): an UNCOMMITTED stamp is denied -- main would not receive it",
              rc == 2 and "no qa/CERTIFICATION is committed at" in err and "Run /qa-flow:certify against staging" in err, err)
        # #1657 review: the gate's own text tools are not byte-safe in a UTF-8 locale. macOS `tr` (the git/gh pre-check) and BSD `grep` stop at an invalid
        # byte and drop the REST of the command, and macOS `sed` (inside the normaliser) aborts: `echo \xff` + a newline + a push read as no git at all and
        # was allowed. The hook pins `LC_ALL=C` itself, whatever the caller's locale; a normaliser that yields nothing for a command that is not empty is
        # "could not read", which refuses in the degraded (no classifier) path. Run under en_US.UTF-8 ON PURPOSE; on a host without that locale the tools
        # are byte-safe and these pass either way, so they can only be red on macOS (the maintainer's own machine).
        import shutil

        def gate_bytes(payload: bytes, root: Path | None = None, path_prefix: Path | None = None) -> int:
            e = {**env, "LC_ALL": "en_US.UTF-8"}
            if root is not None:
                e["CLAUDE_PLUGIN_ROOT"] = str(root)
            if path_prefix is not None:
                e["PATH"] = f"{path_prefix}{os.pathsep}{e['PATH']}"
            done = _run(["bash", str(QA_HOOK)], cwd=repo, env=e, capture_output=True, timeout=60, input=payload)
            return gate_exit(done.returncode, done.stderr)

        with tempfile.TemporaryDirectory() as ubtd:
            ub_root = Path(ubtd) / "qa-flow"
            shutil.copytree(QA_HOOK.parents[2], ub_root, ignore=shutil.ignore_patterns("push_targets.py", "__pycache__"))
            check("release-gate (#1657): an invalid byte on an EARLIER line does not hide a push to main under a UTF-8 locale",
                  gate_bytes(b"echo \xff\ngit push origin main\n") == 2, "exit != 2")
            check("release-gate (#1657): CONTROL: the same push without the invalid byte is refused",
                  gate_bytes(b"echo ok\ngit push origin main\n") == 2, "exit != 2")
            check("release-gate (#1657): CONTROL: without the classifier, an invalid byte with no push in the command is not itself a refusal",
                  gate_bytes(b"echo \xff\ngit status\n", ub_root) == 0, "exit != 0")
            check("release-gate (#1657): without the classifier, an invalid byte on an earlier line does not hide a push to main",
                  gate_bytes(b"echo \xff\ngit push origin main\n", ub_root) == 2, "exit != 2")
            check("release-gate (#1657): without the classifier, a command the normaliser reads as NOTHING (only comments) is refused, not passed",
                  gate_bytes(b"# git push origin main", ub_root) == 2, "exit != 2")
            # BSD grep stops matching at an invalid byte EARLIER ON THE SAME LINE under a UTF-8 locale (an earlier LINE is fine), so the fallback's `main|master` match
            # read `echo \xff; git push origin main` as no main: the greps run under LC_ALL=C. Two spellings of the invalid byte (\xff, and \xe9 which is a valid
            # Latin-1 letter but not valid UTF-8).
            check("release-gate (#1657): without the classifier, an invalid byte EARLIER ON THE SAME LINE does not hide a push to main",
                  gate_bytes(b"echo \xff; git push origin main", ub_root) == 2, "exit != 2")
            check("release-gate (#1657): without the classifier, a Latin-1 byte before `&& git push origin main` does not hide it",
                  gate_bytes(b"echo \xe9 && git push origin main", ub_root) == 2, "exit != 2")
            # The gh api / release promotion check reads the RAW command (unanchored: `merge|refs|releases|...`), and BSD grep stops at an invalid byte earlier on the
            # same line: `echo \xff; gh api -X PUT repos/o/r/merges -f base=main` merged into main with no classifier (the pin on that grep is what refuses it).
            check("release-gate (#1657): without the classifier, an invalid byte before a `gh api` merge does not hide it",
                  gate_bytes(b"echo \xff; gh api -X PUT repos/o/r/merges -f base=main", ub_root) == 2, "exit != 2")
            # A normaliser that FAILS (an awk that passes its input through and exits 2) is "could not read": refused. The pass-through keeps the output non-empty, so
            # the empty-output refusal cannot be what refuses; and `FOO=1 git push …` is not anchored without the peel, so the raw text cannot be what refuses either.
            with tempfile.TemporaryDirectory() as sbtd:
                stub = Path(sbtd) / "awk"
                stub.write_text("#!/bin/sh\ncat\nexit 2\n", encoding="utf-8"); stub.chmod(0o755)
                check("release-gate (#1657): without the classifier, a normaliser that fails (awk exits 2) is refused, not read as nothing to judge",
                      gate_bytes(b"FOO=1 git push origin main\n", ub_root, stub.parent) == 2, "exit != 2")
            check("release-gate (#1657): CONTROL: the same command is judged and refused by the real normaliser too",
                  gate_bytes(b"FOO=1 git push origin main\n", ub_root) == 2, "exit != 2")
            check("release-gate (#1657): CONTROL: without the classifier, a git command that is not a push passes with the real normaliser",
                  gate_bytes(b"FOO=1 git status\n", ub_root) == 0, "exit != 0")
            # The classifier decodes strictly in a UTF-8 locale; an invalid byte made it fail and the gate refused even a `git status`, naming nothing. Under C it judges the command.
            check("release-gate (#1657): with the classifier, an invalid byte in a command that is not a push does not refuse it",
                  gate_bytes(b"echo \xff\ngit status\n") == 0, "exit != 0")
            # `grep -q` closes its pipe at the first match; under `set -o pipefail` a producer still writing (a segment over the pipe buffer, 64 KB) dies of
            # SIGPIPE and the pipeline reads 141, which skipped the `&&` branch: a push on the FIRST line of a long command was not seen (a fail-open).
            check("release-gate (#1657): without the classifier, a push on the first line of a 120 KB command is refused (grep -q must not read 141)",
                  gate_bytes(b"git push origin main\n" + b"x\n" * 60000, ub_root) == 2, "exit != 2")
        sh("add", "qa/CERTIFICATION"); sh_old("commit", "-q", "-m", "stamp")
        rc, err = gate()
        check("release-gate (#1337): the stamp committed on top of the tested sha still permits", rc == 0, err)
        # #1571: dev's tip is read only when the classifier is unavailable (it names every commit itself), so that
        # path needs its own fixture. A plugin copy WITHOUT push_targets.py forces the fallback, and this repo has
        # no origin/dev: plain `git rev-parse origin/dev` echoes the literal ref and poisons the value (#1337).
        import shutil
        with tempfile.TemporaryDirectory() as fbtd:
            fb_root = Path(fbtd) / "qa-flow"
            shutil.copytree(QA_HOOK.parents[2], fb_root, ignore=shutil.ignore_patterns("push_targets.py", "__pycache__"))
            done = _run(["bash", str(QA_HOOK)], cwd=repo, env={**env, "CLAUDE_PLUGIN_ROOT": str(fb_root)},
                        capture_output=True, text=True, timeout=60,
                        input=json.dumps({"tool_input": {"command": "git push origin main"}}))
        check("release-gate (#1337): without the classifier, dev's tip is read and a missing origin/dev does not poison it",
              done.returncode == 0, done.stderr)
        (repo / "app.rb").write_text("v2\n", encoding="utf-8")
        sh("commit", "-q", "-am", "untested change")
        rc, err = gate()
        check("release-gate (#1337): a code change after the tested sha is denied, naming the path",
              rc == 2 and "app.rb" in err, err)
        sh("checkout", "-q", "-b", "side", tested + "~1")
        (repo / "other.rb").write_text("x\n", encoding="utf-8")
        sh("add", "other.rb"); sh("commit", "-q", "-m", "side")
        stamp["sha"] = sh("rev-parse", "HEAD"); sh("checkout", "-q", "-")
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps(stamp), encoding="utf-8")
        sh("add", "qa/CERTIFICATION"); sh_old("commit", "-q", "-m", "a stamp for another branch")
        rc, err = gate()
        check("release-gate (#1337): a stamp for a sha that is not an ancestor of dev is denied",
              rc == 2 and " moved" in err, err)

    # #1428. A schema-2 stamp must name a passing first-boot walkthrough and authorization sweep; its
    # own commit may carry that evidence and nothing else. An old stamp passes, loudly, for one release.
    fb_rows = ("Step,Width,Actor,URL,Action,Expected,Actual,Status,Notes,Screenshot,Also,Issue,Env\n"
               "1.1,1280,root,/login,Sign in,In,In,Pass,,,,,empty db\n"
               "1.2,390,root,/login,Sign in,In,In,Pass,,,,,empty db\n")
    az_head = "action,location,actor_role,target_role,guard,verdict,evidence,issue\n"
    az_good = az_head + "demote,app/models/user.rb:40,it,root,root? refusal,GUARDED,,\n"
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        _git_repo(repo)
        sh = lambda *a: _run([*g, *a], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
        (repo / "app.rb").write_text("v1\n", encoding="utf-8")
        sh("add", "app.rb"); sh("commit", "-q", "-m", "app")
        # Work on a branch that is not `main`: main is the last PUBLISHED release, and evidence
        # already there is last release's (#1437 round 3). main stays at the commit before any.
        sh("checkout", "-q", "-b", "work")
        tested = sh("rev-parse", "HEAD")
        fb_dir, az_file = repo / "qa/manual-tests/first-boot-v1", repo / "qa/manual-tests/authz-v1/sweep.csv"
        fb_dir.mkdir(parents=True); az_file.parent.mkdir(parents=True)
        (fb_dir / "pages.csv").write_text(fb_rows, encoding="utf-8")
        az_file.write_text(az_good, encoding="utf-8")
        new_stamp = {"sha": tested, "date": "2026-09-28", "verdict": "PASS", "report": "qa/reports/r.md",
                     "schema": 2, "version": "v1", "first_boot": "qa/manual-tests/first-boot-v1",
                     "authz": "qa/manual-tests/authz-v1/sweep.csv"}
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps(new_stamp), encoding="utf-8")
        env = dict(os.environ); env.pop("QA_ALLOW_MAIN", None); env["CLAUDE_PLUGIN_ROOT"] = str(QA_HOOK.parents[2])

        def gate2() -> tuple[int, str]:
            sh("branch", "-f", "dev", "HEAD")
            # `git push origin main` ships the LOCAL main (#1569), so the fixture promotes dev by making main it.
            sh("update-ref", "refs/heads/main", "HEAD")
            # The last PUBLISHED release is origin/main (release_evidence reads it before main): the root commit.
            sh("update-ref", "refs/remotes/origin/main", sh("rev-list", "--max-parents=0", "HEAD").split()[0])
            done = _run(["bash", str(QA_HOOK)], cwd=repo, env=env, capture_output=True, text=True, timeout=60,
                                  input=json.dumps({"tool_input": {"command": "git push origin main"}}))
            return done.returncode, done.stderr

        sh("add", "qa"); sh("commit", "-q", "-m", "stamp + evidence")
        rc, err = gate2()
        check("release-gate (#1428): a schema-2 stamp whose commit carries its passing evidence permits",
              rc == 0, err)
        az_file.write_text(az_good + "demote,app/controllers/staff.rb:88,it,root,,HOLE,forged PATCH,#1\n",
                           encoding="utf-8")
        sh("commit", "-q", "-am", "sweep found a hole")
        rc, err = gate2()
        check("release-gate (#1428): a HOLE in the sweep denies, naming the layer",
              rc == 2 and "#1428" in err and "HOLE" in err, err)
        az_file.write_text(az_good, encoding="utf-8")
        (fb_dir / "pages.csv").write_text(fb_rows + "2.1,1280,root,/users/new,Create,Created,,Blocked,,,,,x\n",
                                          encoding="utf-8")
        sh("commit", "-q", "-am", "blocked row")
        rc, err = gate2()
        check("release-gate (#1428): a Blocked row with no reason denies", rc == 2 and "Blocked" in err, err)
        (fb_dir / "pages.csv").write_text(fb_rows, encoding="utf-8")
        (repo / "app.rb").write_text("v2\n", encoding="utf-8")
        sh("commit", "-q", "-am", "evidence fixed, and an untested code change")
        rc, err = gate2()
        check("release-gate (#1428): a code change riding with the evidence is still denied, naming it",
              rc == 2 and "app.rb" in err, err)
        (repo / "app.rb").write_text("v1\n", encoding="utf-8")
        evil = repo / "qa/manual-tests/first-boot-v1-other/x.rb"
        evil.parent.mkdir(parents=True); evil.write_text("x\n", encoding="utf-8")
        sh("add", "qa"); sh("commit", "-q", "-am", "a path that only starts like the evidence dir")
        rc, err = gate2()
        check("release-gate (#1428): a look-alike of the evidence path is not evidence",
              rc == 2 and "first-boot-v1-other" in err, err)
        sh("rm", "-q", "-r", "qa/manual-tests/first-boot-v1-other"); sh("commit", "-q", "-m", "drop it")
        # The allowance is a PREFIX match: the evidence path appearing inside another path is not it.
        inner = repo / "vendor/qa/manual-tests/first-boot-v1/x.rb"
        inner.parent.mkdir(parents=True); inner.write_text("x\n", encoding="utf-8")
        sh("add", "vendor"); sh("commit", "-q", "-m", "evidence path embedded in another path")
        rc, err = gate2()
        check("release-gate (#1428): a path merely containing the evidence path is not evidence",
              rc == 2 and "vendor/" in err, err)
        sh("rm", "-q", "-r", "vendor"); sh("commit", "-q", "-m", "drop vendor")
        # CONFINEMENT (#1437 review blocker): a stamp naming evidence outside qa/manual-tests/ would
        # let the stamp's commit carry code. It is refused before any allowance is computed.
        tip = sh("rev-parse", "HEAD")
        (repo / "app").mkdir(exist_ok=True)
        (repo / "app" / "pages.csv").write_text(fb_rows, encoding="utf-8")
        (repo / "app" / "evil.rb").write_text("x\n", encoding="utf-8")
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps({**new_stamp, "sha": tip, "first_boot": "app"}),
                                                   encoding="utf-8")
        sh("add", "app", "qa"); sh("commit", "-q", "-m", "a stamp naming app/ as its evidence")
        rc, err = gate2()
        check("release-gate (#1428): a stamp naming evidence outside qa/manual-tests/ is denied",
              rc == 2 and "evidence must be" in err, err)
        sh("rm", "-q", "-r", "app")
        # A non-ASCII evidence file name arrives unquoted and is recognised as evidence.
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps({**new_stamp, "sha": sh("rev-parse", "HEAD")}),
                                                   encoding="utf-8")
        sh("add", "qa"); sh("commit", "-q", "-m", "restore the stamp")
        tip = sh("rev-parse", "HEAD")
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps({**new_stamp, "sha": tip}), encoding="utf-8")
        (fb_dir / "écran-1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        sh("add", "qa"); sh("commit", "-q", "-m", "a non-ASCII screenshot name in the evidence")
        rc, err = gate2()
        check("release-gate (#1428): a non-ASCII evidence file name is recognised as evidence", rc == 0, err)
        # #1437 review round 2. RENAME LAUNDERING: moving code into the evidence folder in the stamp's
        # commit listed only the new path, so the code's removal from app/ was never judged.
        (repo / "app.rb").write_text("v1\n", encoding="utf-8")
        tip = sh("rev-parse", "HEAD")
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps({**new_stamp, "sha": tip}), encoding="utf-8")
        sh("mv", "app.rb", "qa/manual-tests/first-boot-v1/app.rb")
        sh("add", "qa"); sh("commit", "-q", "-m", "stamp commit that moves code into the evidence folder")
        rc, err = gate2()
        check("release-gate (#1428): code renamed into the evidence folder is denied, naming its old path",
              rc == 2 and "app.rb" in err, err)
        sh("mv", "qa/manual-tests/first-boot-v1/app.rb", "app.rb"); sh("commit", "-q", "-m", "move it back")
        # The sweep is ONE file: a sibling that merely starts with its name is not evidence.
        tip = sh("rev-parse", "HEAD")
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps({**new_stamp, "sha": tip}), encoding="utf-8")
        (repo / "qa/manual-tests/authz-v1/sweep.csv.rb").write_text("x\n", encoding="utf-8")
        sh("add", "qa"); sh("commit", "-q", "-m", "a file named after the sweep")
        rc, err = gate2()
        check("release-gate (#1428): a file that only starts with the sweep's name is not evidence",
              rc == 2 and "sweep.csv.rb" in err, err)
        sh("rm", "-q", "qa/manual-tests/authz-v1/sweep.csv.rb"); sh("commit", "-q", "-m", "drop it")
        # The gate judges what dev COMMITTED: a HOLE committed on dev, fixed only in the index here.
        tip = sh("rev-parse", "HEAD")
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps({**new_stamp, "sha": tip}), encoding="utf-8")
        az_file.write_text(az_good + "demote,app/controllers/staff.rb:88,it,root,,HOLE,forged PATCH,#1\n",
                           encoding="utf-8")
        sh("add", "qa"); sh("commit", "-q", "-m", "the sweep, committed with a HOLE")
        az_file.write_text(az_good, encoding="utf-8"); sh("add", "qa")
        rc, err = gate2()
        check("release-gate (#1428): a committed HOLE denies though the fix is only staged",
              rc == 2 and "HOLE" in err, err)
        sh("commit", "-q", "-m", "fix it for real")
        # An old stamp names no evidence, so it gets no evidence allowance: certify the current tip.
        old_stamp = {k: v for k, v in new_stamp.items() if k in ("date", "verdict", "report")}
        old_stamp["sha"] = sh("rev-parse", "HEAD")
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps(old_stamp), encoding="utf-8")
        _run([*g, "commit", "-q", "-am", "an old-style stamp"], cwd=repo, check=True, capture_output=True,
                       env={**os.environ, "GIT_COMMITTER_DATE": "2026-09-01T00:00:00+00:00"})
        rc, err = gate2()
        check("release-gate (#1428): an old stamp is grandfathered -- it permits, and says re-certify",
              rc == 0 and "re-run /qa-flow:certify" in err.lower(), err)
        # ...and gets NO evidence allowance: evidence files changed after an OLD stamp's sha are just
        # changes, because an old stamp names no evidence.
        (fb_dir / "pages.csv").write_text(fb_rows + "9,1280,a,/,x,y,z,Pass,,,,,\n", encoding="utf-8")
        sh("commit", "-q", "-am", "evidence edited after an old stamp")
        rc, err = gate2()
        check("release-gate (#1428): an old stamp gets no evidence allowance", rc == 2 and "pages.csv" in err, err)
        # Round 3: a NEW stamp that merely omits `schema` (committed now) is not grandfathered.
        (fb_dir / "pages.csv").write_text(fb_rows, encoding="utf-8")
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps({**old_stamp, "sha": sh("rev-parse", "HEAD"),
                                                                "date": "now"}), encoding="utf-8")
        sh("commit", "-q", "-am", "a new stamp without schema")
        rc, err = gate2()
        check("release-gate (#1428): a NEW stamp that omits schema is denied, not grandfathered",
              rc == 2 and "schema" in err, err)
        # Round 3 BLOCKER: a newline in an evidence path smuggled `app` into the line-by-line allowance.
        tip = sh("rev-parse", "HEAD")
        (repo / "app").mkdir(exist_ok=True)
        (repo / "app" / "policy.rb").write_text("x\n", encoding="utf-8")
        sh("add", "app"); sh("commit", "-q", "-m", "policy"); tip = sh("rev-parse", "HEAD")
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps(
            {**new_stamp, "sha": tip, "first_boot": "qa/manual-tests/first-boot-v1\napp"}), encoding="utf-8")
        sh("rm", "-q", "app/policy.rb"); sh("add", "qa"); sh("commit", "-q", "-m", "stamp + delete app/policy.rb")
        rc, err = gate2()
        check("release-gate (#1428): a newline in an evidence path launders nothing", rc == 2, err)

    # Round 3: a DEGRADED PATH -- only bash. grep, sed, awk, tr, head, python3 and git are all gone;
    # the builtins-only fallback must still deny a promotion. PATH replaced, not prefixed.
    def bare_gate(cmd: str, tools: tuple[str, ...] = ("bash",)) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            only = Path(td) / "only"
            only.mkdir()
            for tool in tools:
                (only / tool).symlink_to(shutil.which(tool))
            done = _run([str(only / "bash"), str(QA_HOOK)], cwd=td,
                                  input=json.dumps({"tool_input": {"command": cmd}}),
                                  env={"PATH": str(only)}, capture_output=True, text=True, timeout=60)
            return done.returncode, done.stdout + done.stderr

    code, out = bare_gate("git push origin main")
    check("release-gate: with ONLY bash on PATH, a push to main is still blocked", code == 2, f"exit {code}: {out[:160]!r}")
    code, out = bare_gate("gh pr merge 12")
    check("release-gate: with ONLY bash on PATH, gh pr merge is still blocked", code == 2, f"exit {code}: {out[:160]!r}")
    # python3 and git PRESENT, the text tools missing: the fallback must still fire, because the
    # normaliser and the detection run on sed, awk, tr and grep, and without them nothing matches.
    code, out = bare_gate("git push origin main", tools=("bash", "python3", "git"))
    check("release-gate: with python3 and git but NO grep or sed, a push to main is still blocked",
          code == 2, f"exit {code}: {out[:160]!r}")
    # Round 3 fold-in: the fallback matched raw JSON, so git's global options and a JSON-escaped tab
    # slipped past it. Each is a real way to write a push to main.
    for cmd in ("git -C . push origin main", "git -c k=v push origin main", "git\tpush origin main",
                # #1617: EVERY separator a JSON-escaped tab. The alias rule reads `git\tpush origin main` as an unknown verb beside `main`, so the
                # first spelling is refused without the whitespace normalisation; this one is refused only because of it.
                "git\tpush\torigin\tmain", "git\tpush\torigin\tHEAD:main",
                "git --git-dir=.git push origin HEAD:main", "git push origin refs/heads/main",
                "git push origin HEAD:refs/heads/master"):
        code, out = bare_gate(cmd)
        check(f"release-gate: with ONLY bash on PATH, {cmd!r} is still blocked", code == 2,
              f"exit {code}: {out[:160]!r}")
    for cmd in ("git status", "git push origin maintenance", "git push origin feature/x",
                "git push origin feature/main"):
        code, out = bare_gate(cmd)
        check(f"release-gate: CONTROL: with ONLY bash on PATH, `{cmd}` is allowed", code == 0, f"exit {code}: {out[:160]!r}")

    # #1542: a heredoc a `$( )` ended early still owes its delimiter, and no new heredoc opens until it
    # is seen. Otherwise a body line naming `cat <<END` opened a heredoc that never closed, and
    # `git push origin main` after the `)` read as heredoc text: the gate allowed a push it must refuse.
    early = "x=$(cat <<EOF\n)\ncat <<END\nEOF\n)\n"
    check("release-gate (#1542): a push to main after an early-ended heredoc and a `cat <<END` is blocked",
          run(early + "git push origin main") == 2, "exit 0: the gate read the push as heredoc text")
    check("release-gate (#1542): CONTROL: without the `cat <<END` line the same push is blocked",
          run("x=$(cat <<EOF\n)\nEOF\n)\ngit push origin main") == 2, "exit 0")
    check("release-gate (#1542): CONTROL: the same shape pushing a feature branch is allowed",
          run(early + "git push origin feature/w") == 0, "exit 2")

    # #1550: the shell RUNS a substitution, so a push inside one is a push. `--classify` never read the
    # body, and the hook's own comment ("a substitution ... is treated as a promotion") was not true of it.
    for cmd in ("x=$(git push origin main)", 'echo "$(git push origin main)"', "x=`git push origin main`"):
        check(f"release-gate (#1550): {cmd!r} is blocked", run(cmd) == 2, "exit 0: the body was never read")
    check("release-gate (#1550): CONTROL: a harmless substitution beside a feature-branch push is allowed",
          run("x=$(git rev-parse HEAD)\ngit push origin feature/w") == 0, "exit 2")
    check("release-gate (#1550): CONTROL: a commit message heredoc in $( ) naming a push is allowed",
          run("git commit -m \"$(cat <<'EOF'\nnever git push origin main\nEOF\n)\"") == 0, "exit 2")

    # #1553: an UNQUOTED heredoc delimiter makes the shell expand `$( )` in the body, so the push runs;
    # a QUOTED one makes the body text.
    check("release-gate (#1553): a push in a substitution in an UNQUOTED heredoc body is blocked",
          run("cat <<EOF\n$(git push origin main)\nEOF") == 2, "exit 0: the heredoc body was stripped unread")
    check("release-gate (#1553): CONTROL: the same body under a QUOTED delimiter is text and allowed",
          run("cat <<'EOF'\n$(git push origin main)\nEOF") == 0, "exit 2")
    check("release-gate (#1553): CONTROL: a harmless substitution in an unquoted body, then a feature push, is allowed",
          run("cat <<EOF\n$(git rev-parse HEAD)\nEOF\ngit push origin feature/w") == 0, "exit 2")



# ---- #1569: classify by EFFECT. A REST/GraphQL merge, a hotfix PR and a release publish all reached main
# past a gate that only read `git push` / `gh pr merge`. Driven through the real hook with a fake `gh`.
FAKE_GH = """#!/bin/sh
case "$1 $2" in
  "pr view") [ -z "${FAKE_PRVIEW:-}" ] || printf '%s https://github.com/%s/pull/7' "$FAKE_PRVIEW" "${FAKE_PRREPO:-o/r}"; exit 0 ;;
  "api graphql") if [ -n "${FAKE_LOOKUP_BODY:-}" ]; then printf '%s' "$FAKE_LOOKUP_BODY"; exit "${FAKE_LOOKUP_EXIT:-0}"; fi
    case "$*" in
      *"on Ref"*) [ -z "${FAKE_REF:-}" ] || printf '%s %s' "$FAKE_REF" "${FAKE_PRREPO:-o/r}" ;;
      *) [ -z "${FAKE_NODE:-}" ] || printf '%s %s' "$FAKE_NODE" "${FAKE_PRREPO:-o/r}" ;;
    esac; exit "${FAKE_LOOKUP_EXIT:-0}" ;;
  "release view") printf '%s' "${FAKE_RELVIEW:-}"; exit 0 ;;
  "api repos"*) if [ -n "${FAKE_LOOKUP_BODY:-}" ]; then printf '%s' "$FAKE_LOOKUP_BODY"; else printf '%s' "${FAKE_RELID:-}"; fi; exit "${FAKE_LOOKUP_EXIT:-0}" ;;
esac
exit 1
"""
# #1626: REAL `gh` on a lookup that errors exits 1 and prints the raw error BODY to STDOUT (not stderr, and not nothing). The stub's FAKE_LOOKUP_EXIT is
# the exit status and FAKE_LOOKUP_BODY the stdout of `gh api graphql` and `gh api repos/...`; the old "a node GitHub cannot name" row modelled
# the failure as empty stdout with exit 0, a shape `gh` never produces.
GH_ERROR_BODY = ('{"data":{"node":null},"errors":[{"type":"NOT_FOUND","path":["node"],'
                 '"message":"Could not resolve to a node with the global id of \'PR_kw1\'"}]}')


def release_gate_effects_fixtures() -> None:
    g = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _git_repo(repo)
        sh = lambda *a, **kw: _run([*g, *a], cwd=repo, check=True, capture_output=True, text=True, **kw).stdout.strip()
        old = {**os.environ, "GIT_COMMITTER_DATE": "2026-09-01T00:00:00+00:00", "GIT_AUTHOR_DATE": "2026-09-01T00:00:00+00:00"}
        # THIS checkout is github.com/o/r (so `repos/o/r/...` and `-R o/r` name it, and nothing else does),
        # and the remote's refs live in a local bare repo behind insteadOf, so `git ls-remote origin`
        # (the tag check) answers without a network.
        bare = Path(td) / "origin.git"
        _run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
        sh("remote", "add", "origin", "https://github.com/o/r.git")
        sh("config", f"url.{bare}.insteadOf", "https://github.com/o/r.git")
        (repo / "app.rb").write_text("v1\n", encoding="utf-8")
        sh("add", "app.rb"); sh("commit", "-q", "-m", "app")
        tested = sh("rev-parse", "HEAD")
        (repo / "qa").mkdir()
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps(
            {"sha": tested, "date": "2026-09-26", "verdict": "PASS", "report": "qa/reports/r.md"}), encoding="utf-8")
        sh("add", "qa/CERTIFICATION"); sh("commit", "-q", "-m", "stamp", env=old)
        stamped = sh("rev-parse", "HEAD")                 # the certified tip of dev
        sh("branch", "-f", "dev", stamped)
        sh("checkout", "-q", "-b", "hotfix")
        (repo / "app.rb").write_text("hotfix\n", encoding="utf-8")
        sh("commit", "-q", "-am", "hotfix, never certified")
        hot = sh("rev-parse", "HEAD")
        sh("checkout", "-q", "-b", "feature/work", stamped)
        sh("branch", "-f", "main", hot)                   # main is at an UNcertified commit
        (Path(td) / "bin").mkdir()
        (Path(td) / "bin" / "gh").write_text(FAKE_GH, encoding="utf-8")
        (Path(td) / "bin" / "gh").chmod(0o755)
        (Path(td) / "q.graphql").write_text('mutation { mergePullRequest(input:{pullRequestId:"PR_kw1", expectedHeadOid:"%s"}) { clientMutationId } }' % hot, encoding="utf-8")
        (Path(td) / "q.json").write_text(json.dumps({"query": 'mutation { mergePullRequest(input:{pullRequestId:"PR_kw1", expectedHeadOid:"%s"}) { clientMutationId } }' % hot}), encoding="utf-8")

        (Path(td) / "draft.json").write_text('{"draft": false}', encoding="utf-8")

        def run(cmd: str, **extra) -> tuple[int, str]:
            env = dict(os.environ); env.pop("QA_ALLOW_MAIN", None)
            env["CLAUDE_PLUGIN_ROOT"] = str(QA_HOOK.parents[2])
            env["PATH"] = str(Path(td) / "bin") + os.pathsep + env["PATH"]
            env.update(extra)
            done = _run(["bash", str(QA_HOOK)], cwd=repo, input=json.dumps({"tool_input": {"command": cmd}}),
                        env=env, capture_output=True, text=True, timeout=60)
            return done.returncode, done.stderr

        hotfix_pr = {"FAKE_PRVIEW": f"main {hot}"}
        promo_pr = {"FAKE_PRVIEW": f"main {stamped}"}

        def pinned(cmd: str, head: str) -> str:
            """The same command with the head it merges PINNED (#1571). A merge into main that does not pin it is denied
            before it is judged, so the fixtures that prove the CERTIFICATION decision must carry the pin."""
            if "graphql" in cmd:
                return cmd.replace('pullRequestId:"PR_kw1"}', f'pullRequestId:"PR_kw1", expectedHeadOid:"{head}"}}')
            if "/merge" in cmd:
                return cmd.replace("/merge", f"/merge -f sha={head}", 1)
            return f"{cmd} --match-head-commit {head}"
        # (1) A merge through the API, by every spelling, of a PR into main whose head is NOT certified.
        for label, cmd in (
            ("REST PUT, placeholders", "gh api -X PUT repos/{owner}/{repo}/pulls/7/merge -f merge_method=merge"),
            ("REST PUT, literal repo", "gh api -X PUT repos/o/r/pulls/7/merge"),
            ("--method=PUT", "gh api --method=PUT repos/o/r/pulls/7/merge"),
            ("--method PUT after the path", "gh api repos/o/r/pulls/7/merge --method PUT"),
            ("-XPUT attached", "gh api -XPUT repos/o/r/pulls/7/merge"),
            ("sh -c", "bash -c 'gh api -X PUT repos/o/r/pulls/7/merge'"),
            ("eval", 'eval "gh api -X PUT repos/o/r/pulls/7/merge"'),
            ("env prefix", "GH_TOKEN=x gh api -X PUT repos/o/r/pulls/7/merge"),
            ("$( )", "x=$(gh api -X PUT repos/o/r/pulls/7/merge)"),
            ("backticks", "x=`gh api -X PUT repos/o/r/pulls/7/merge`"),
            ("unquoted heredoc body", "cat <<EOF\n$(gh api -X PUT repos/o/r/pulls/7/merge)\nEOF"),
            ("gh pr merge of a hotfix", "gh pr merge 7 --merge"),
            ("GraphQL -f query", "gh api graphql -f query='mutation { mergePullRequest(input:{pullRequestId:\"PR_kw1\"}) { clientMutationId } }'"),
            ("GraphQL -F query=@file", f"gh api graphql -F query=@{td}/q.graphql"),
            ("GraphQL --input file", f"gh api graphql --input {td}/q.json"),
        ):
            rc, err = run(pinned(cmd, hot), **hotfix_pr, FAKE_NODE=f"main {hot}")
            check(f"release-gate (#1569): {label} merging an uncertified PR head into main is blocked, naming the PR head",
                  rc == 2 and "PR head" in err, f"rc={rc} {err[:200]!r}")
        # The hotfix model: the SAME merge is permitted when the PR head IS the certified commit.
        for cmd in ("gh api -X PUT repos/o/r/pulls/7/merge", "gh pr merge 7"):
            rc, err = run(pinned(cmd, stamped), **promo_pr)
            check(f"release-gate (#1569): `{cmd}` of a PR whose head carries a PASS stamp is permitted", rc == 0, f"rc={rc} {err[:200]!r}")
        rc, err = run(pinned("gh api -X PUT repos/o/r/pulls/7/merge", hot), FAKE_PRVIEW=f"main {hot}")
        check("release-gate (#1569): a hotfix head is judged by ITS stamp, not dev's (dev is certified, the head is not)",
              rc == 2 and hot[:12] in err, f"rc={rc} {err[:200]!r}")
        # (#1617) A GRAPHQL MERGE HELD IN A VARIABLE. The literal form was judged and `Q='mutation{mergePullRequest...}'; gh api graphql -f query="$Q"`
        # was allowed (found reviewing #1615, with a gh stub that targets main). A variable the command bound ONCE to a literal, earlier, is read as
        # that literal and judged like one; any other variable is a document the gate cannot read, which it refuses.
        held = 'mutation { mergePullRequest(input:{pullRequestId:"PR_kw1", expectedHeadOid:"%s"}) { clientMutationId } }' % hot
        for label, cmd in (("a variable", f"Q='{held}'; gh api graphql -f query=\"$Q\""),
                           ("an exported variable, set on an earlier line", f"export Q='{held}'\ngh api graphql -f query=\"$Q\"")):
            rc, err = run(cmd, **hotfix_pr, FAKE_NODE=f"main {hot}")
            check(f"release-gate (#1617): a GraphQL merge held in {label} is judged like a literal one, and blocked naming the PR head",
                  rc == 2 and "PR head" in err, f"rc={rc} {err[:200]!r}")
        for label, cmd in (("a variable the command never set", 'gh api graphql -f query="$Q"'),
                           ("an unquoted variable", "gh api graphql -f query=$Q"),
                           ("a variable read from a file", 'read Q < q.txt; gh api graphql -f query="$Q"'),
                           ("a variable set in the command's own prefix", f"Q='{held}' gh api graphql -f query=\"$Q\""),
                           ("a variable set twice", f"Q='query{{a}}'; Q='{held}'; gh api graphql -f query=\"$Q\"")):
            rc, err = run(cmd, **hotfix_pr, FAKE_NODE=f"main {hot}")
            check(f"release-gate (#1617): a GraphQL document held in {label} cannot be read, and the command is blocked",
                  rc == 2 and "cannot tell which" in err, f"rc={rc} {err[:200]!r}")
        for cmd in ("Q='query{viewer{login}}'; gh api graphql -f query=\"$Q\"",
                    "gh api graphql -f query='query($o:String!){repository(owner:$o){id}}' -f o=\"$OWNER\""):
            rc, err = run(cmd, **hotfix_pr, FAKE_NODE=f"main {hot}")
            check(f"release-gate (#1617): CONTROL: a read-only query, or a variable that is only another field's value, is allowed: `{cmd[:60]}`",
                  rc == 0, f"rc={rc} {err[:200]!r}")
        # (#1571) THE HEAD IS PINNED. The gate reads the PR's head, then GitHub merges whatever the head is a moment
        # later; a commit pushed in between would ride on the certification. So a merge into main must pin the head
        # the gate judged (`--match-head-commit`, `sha=`, `expectedHeadOid`), and the denial prints the command to run.
        rest = "gh api -X PUT repos/o/r/pulls/7/merge"
        gql = "gh api graphql -f query='mutation { mergePullRequest(input:{pullRequestId:\"PR_kw1\"}) { clientMutationId } }'"
        for label, cmd, want in (
            ("`gh pr merge`", "gh pr merge 7", f"gh pr merge 7 --match-head-commit {stamped}"),
            ("`gh pr merge` with other flags", "gh pr merge 7 --squash --delete-branch", f"--match-head-commit {stamped}"),
            ("a REST merge", rest, f"-f sha={stamped}"),
            ("a GraphQL merge", gql, f'expectedHeadOid: "{stamped}"'),
        ):
            rc, err = run(cmd, **promo_pr, FAKE_NODE=f"main {stamped}")
            check(f"release-gate (#1571): {label} into main without a pin is blocked",
                  rc == 2 and "without pinning the head" in err, f"rc={rc} {err[:200]!r}")
            check(f"release-gate (#1571): {label} without a pin: the denial prints the exact command, with the full head",
                  want in err, err[:300])
        for label, cmd in (
            ("a full pin", f"gh pr merge 7 --match-head-commit {stamped}"),
            ("the `=` spelling", f"gh pr merge 7 --match-head-commit={stamped}"),
            ("an unambiguous prefix of 12 digits", f"gh pr merge 7 --match-head-commit {stamped[:12]}"),
            ("a prefix of exactly 7 digits", f"gh pr merge 7 --match-head-commit {stamped[:7]}"),
            ("an uppercase pin", f"gh pr merge 7 --match-head-commit {stamped.upper()}"),
            ("a pin among other flags", f"gh pr merge 7 --squash --match-head-commit {stamped} --delete-branch"),
            ("a REST `sha=`", f"{rest} -f sha={stamped}"),
            ("a GraphQL expectedHeadOid", gql.replace('"PR_kw1"}', f'"PR_kw1", expectedHeadOid:"{stamped}"}}')),
        ):
            rc, err = run(cmd, **promo_pr, FAKE_NODE=f"main {stamped}")
            check(f"release-gate (#1571): CONTROL: {label} pins the judged head and is permitted", rc == 0, f"rc={rc} {err[:200]!r}")
        other = hot if hot != stamped else "0" * 40
        for label, cmd in (
            ("a pin for a DIFFERENT commit", f"gh pr merge 7 --match-head-commit {other}"),
            ("a pin shorter than 7 digits", f"gh pr merge 7 --match-head-commit {stamped[:6]}"),
            ("a pin that is not hexadecimal", f"gh pr merge 7 --match-head-commit {stamped[:8].replace(stamped[0], 'z')}"),
            ("a pin built by the shell", "gh pr merge 7 --match-head-commit $HEAD_SHA"),
            ("an empty pin", "gh pr merge 7 --match-head-commit ''"),
            ("a REST `sha=` for a different commit", f"{rest} -f sha={other}"),
            ("a REST `sha=` built by the shell", f"{rest} -f sha=$S"),
            ("a GraphQL expectedHeadOid for a different commit", gql.replace('"PR_kw1"}', f'"PR_kw1", expectedHeadOid:"{other}"}}')),
        ):
            rc, err = run(cmd, **promo_pr, FAKE_NODE=f"main {stamped}")
            check(f"release-gate (#1571): {label} does not pin the judged head, so it is blocked",
                  rc == 2 and "without pinning the head" in err, f"rc={rc} {err[:200]!r}")
        rc, err = run("gh pr merge 7", FAKE_PRVIEW=f"dev {stamped}")
        check("release-gate (#1571): CONTROL: a PR into dev is not a promotion, so it needs no pin", rc == 0, f"rc={rc} {err[:200]!r}")
        rc, err = run("gh pr merge 7", **hotfix_pr, QA_ALLOW_MAIN="1")
        check("release-gate (#1571): CONTROL: the audited QA_ALLOW_MAIN override still lets an unpinned, uncertified merge through",
              rc == 0 and "QA_ALLOW_MAIN=1 override" in err, f"rc={rc} {err[:200]!r}")
        # Unresolved or unreadable is "could not judge", and that denies.
        for label, cmd, env in (
            ("an unresolvable PR", "gh api -X PUT repos/o/r/pulls/7/merge", {"FAKE_PRVIEW": ""}),
            ("a PR number from a variable", "gh api -X PUT repos/o/r/pulls/$N/merge", {}),
            ("a missing --input file", f"gh api graphql --input {td}/nope.json", {}),
            ("a missing -F query file", f"gh api graphql -F query=@{td}/nope.graphql", {}),
            ("--input from stdin", "gh api graphql --input -", {}),
            ("-F query=@- from stdin", "gh api graphql -F query=@-", {}),
            ("a GraphQL node GitHub cannot name", "gh api graphql -f query='mutation { mergePullRequest(input:{pullRequestId:\"PR_zz\"}) { clientMutationId } }'", {"FAKE_NODE": ""}),
        ):
            rc, err = run(cmd, **env)
            check(f"release-gate (#1569): {label} could not be judged, so it is blocked", rc == 2, f"rc={rc} {err[:200]!r}")
        # (#1626) CONTROL: a base GitHub names that `plain_ref` (the rule for a ref typed into a command) would not accept is still a branch, and a PR
        # into it is not a promotion. Treating every unusual name as "unresolved" would refuse merges into branches `dev` let through.
        for odd in ("release+2026", "feature#7", "user@team/topic", "v1.0.x_hotfix"):
            rc, err = run("gh pr merge 7", FAKE_PRVIEW=f"{odd} {hot}")
            check(f"release-gate (#1626): CONTROL: a PR into the branch `{odd}` is not a promotion and is permitted", rc == 0, f"rc={rc} {err[:160]!r}")
            rc, err = run(merge_pinned_odd := gql, FAKE_NODE=f"{odd} {hot}")
            check(f"release-gate (#1626): CONTROL: a GraphQL merge into the branch `{odd}` is not a promotion and is permitted", rc == 0, f"rc={rc} {err[:160]!r}")
        # (#1628) A base or ref name GitHub returns qualified (`refs/heads/main`, `heads/main`) is still main: the coarse detector reads it as main,
        # so the full path must too. Each form is refused on the `gh pr merge`, GraphQL merge and updateRef paths, with an UNCERTIFIED head.
        ref_to_hot = f"gh api graphql -f query='mutation {{ updateRef(input:{{refId:\"R1\", oid:\"{hot}\"}}) {{ clientMutationId }} }}'"
        for qualified in ("refs/heads/main", "heads/main", "refs/heads/master"):
            rc, err = run("gh pr merge 7", FAKE_PRVIEW=f"{qualified} {hot}")
            check(f"release-gate (#1628): a `gh pr merge` whose base is looked up as `{qualified}` is judged as main and blocked", rc == 2, f"rc={rc} {err[:160]!r}")
            rc, err = run(gql, FAKE_NODE=f"{qualified} {hot}")
            check(f"release-gate (#1628): a GraphQL merge whose base is looked up as `{qualified}` is judged as main and blocked", rc == 2, f"rc={rc} {err[:160]!r}")
            rc, err = run(ref_to_hot, FAKE_REF=qualified)
            check(f"release-gate (#1628): an updateRef whose ref is looked up as `{qualified}` is judged as main and blocked", rc == 2, f"rc={rc} {err[:160]!r}")
        # CONTROL: only ONE prefix is stripped, and only a leading one: `refs/heads/dev` and `refs/heads/refs/heads/main` are not main.
        for other_ref in ("refs/heads/dev", "heads/release+2026"):
            rc, err = run("gh pr merge 7", FAKE_PRVIEW=f"{other_ref} {hot}")
            check(f"release-gate (#1628): CONTROL: a PR into `{other_ref}` is not a promotion and is permitted", rc == 0, f"rc={rc} {err[:160]!r}")
        # (#1626) A LOOKUP THAT ERRORS IS UNRESOLVED, NOT AN ANSWER. Real `gh` exits 1 and prints the raw error body to STDOUT; the lookups kept
        # whatever was printed (`|| true`), so `base` held the JSON, was neither `main` nor empty, and a GraphQL merge into main was allowed.
        merge_pinned = gql.replace('"PR_kw1"}', f'"PR_kw1", expectedHeadOid:"{stamped}"}}')
        ref_to_certified = f"gh api graphql -f query='mutation {{ updateRef(input:{{refId:\"R1\", oid:\"{stamped}\"}}) {{ clientMutationId }} }}'"
        patch_release = "gh api -X PATCH repos/o/r/releases/9 -F draft=false"
        rc, err = run(merge_pinned, **promo_pr, FAKE_NODE=f"main {stamped}")
        check("release-gate (#1626): CONTROL: a pinned GraphQL merge of the certified head resolves and is permitted", rc == 0, f"rc={rc} {err[:200]!r}")
        rc, err = run(ref_to_certified, FAKE_REF="main")
        check("release-gate (#1626): CONTROL: an updateRef of main to the certified commit resolves and is permitted", rc == 0, f"rc={rc} {err[:200]!r}")
        for label, cmd in (("a GraphQL mergePullRequest", merge_pinned), ("a GraphQL updateRef", ref_to_certified), ("a release published by id", patch_release)):
            rc, err = run(cmd, **promo_pr, FAKE_LOOKUP_BODY=GH_ERROR_BODY, FAKE_LOOKUP_EXIT="1")
            check(f"release-gate (#1626): {label} whose lookup errors the way gh does (the JSON body on stdout, exit 1) is blocked",
                  rc == 2, f"rc={rc} {err[:200]!r}")
        # The exit status alone, with a plausible answer: a lookup that failed is not trusted for what it printed.
        for label, cmd, env in (("a GraphQL mergePullRequest", merge_pinned, {"FAKE_NODE": f"main {stamped}"}),
                                ("a GraphQL updateRef", ref_to_certified, {"FAKE_REF": "main"}),
                                ("a release published by id", patch_release, {"FAKE_RELID": f"v2 {stamped}"})):
            rc, err = run(cmd, **promo_pr, **env, FAKE_LOOKUP_EXIT="1")
            check(f"release-gate (#1626): {label} whose lookup exits non-zero is blocked even though it printed an answer",
                  rc == 2, f"rc={rc} {err[:200]!r}")
        # The shape alone, with exit 0: what is printed must be a ref name, or it is not an answer.
        for label, cmd in (("a GraphQL mergePullRequest", merge_pinned), ("a GraphQL updateRef", ref_to_certified)):
            rc, err = run(cmd, **promo_pr, FAKE_LOOKUP_BODY=GH_ERROR_BODY, FAKE_LOOKUP_EXIT="0")
            check(f"release-gate (#1626): {label} whose lookup prints something that is not a ref name (exit 0) is blocked",
                  rc == 2, f"rc={rc} {err[:200]!r}")
        rc, err = run("gh release edit v1.0.1 --draft=false", FAKE_RELVIEW=GH_ERROR_BODY)
        check("release-gate (#1626): a draft release whose target lookup prints something that is not a ref name is blocked, not read as a target",
              rc == 2, f"rc={rc} {err[:200]!r}")
        # Writes to main that are not a PR merge name no PR head, so they are judged at dev's tip: with dev
        # certified they are the ordinary promotion (permitted), with dev uncertified they are blocked.
        rc, err = run("gh api repos/o/r/merges -f base=main -f head=dev", FAKE_REF="main")
        check("release-gate (#1569): CONTROL: a merge into main of a CERTIFIED dev is the ordinary promotion and passes",
              rc == 0, f"rc={rc} {err[:200]!r}")
        sh("branch", "-f", "dev", hot)
        for label, cmd in (
            ("POST merges, base main", "gh api repos/o/r/merges -f base=main -f head=dev"),
            ("POST merges, base via -F", "gh api -X POST repos/o/r/merges -F base=master -F head=dev"),
            ("PATCH git/refs/heads/main", "gh api -X PATCH repos/o/r/git/refs/heads/main -f sha=abc"),
            ("POST git/refs of refs/heads/main", "gh api repos/o/r/git/refs -f ref=refs/heads/main -f sha=abc"),
            ("method given by --method=PATCH", "gh api --method=PATCH repos/{owner}/{repo}/git/refs/heads/master -f sha=abc -F force=true"),
            ("GraphQL updateRef naming main", "gh api graphql -f query='mutation { updateRef(input:{refId:\"R1\", oid:\"abc\"}) { clientMutationId } }'"),
        ):
            rc, err = run(cmd, FAKE_REF="main")
            check(f"release-gate (#1569): {label} writes main and is blocked", rc == 2, f"rc={rc} {err[:200]!r}")
        sh("branch", "-f", "dev", stamped)
        # Controls: none of these may be over-blocked.
        for cmd, env in (
            ("gh api repos/o/r/pulls/7", {}),
            ("gh api -X GET repos/o/r/pulls/7/merge", {}),
            ("gh api repos/o/r/merges -f base=dev -f head=x", {}),
            ("gh api -X PATCH repos/o/r/git/refs/heads/dev -f sha=abc", {}),
            ("gh api repos/o/r/git/refs -f ref=refs/heads/feature/main-menu -f sha=abc", {}),
            ("gh api -X POST repos/o/r/issues/1/comments -f body=hello", {}),
            ("gh api graphql -f query='query($o:String!){repository(owner:$o,name:\"r\"){id}}' -f o=x", {}),
            ("gh api -X PUT repos/o/r/pulls/7/merge", {"FAKE_PRVIEW": f"dev {hot}"}),
            ("gh pr merge 7", {"FAKE_PRVIEW": f"dev {hot}"}),
            ("gh api graphql -f query='mutation { updateRef(input:{refId:\"R1\", oid:\"abc\"}) { clientMutationId } }'", {"FAKE_REF": "dev"}),
            ("gh release list", {}),
        ):
            rc, err = run(cmd, **env)
            check(f"release-gate (#1569): CONTROL: `{cmd[:70]}` is not a promotion and passes", rc == 0, f"rc={rc} {err[:200]!r}")
        # (2) Publishing a release needs a PASS stamp for the commit it publishes.
        for label, cmd in (
            ("gh release create --target main", "gh release create v1.0.1 --target main --notes x"),
            ("--target=main", "gh release create v1.0.1 --target=main"),
            ("no target: the default branch's tip", "gh release create v1.0.1 --generate-notes"),
            ("a draft", "gh release create v1.0.1 --draft"),
            ("--target a sha", f"gh release create v1.0.1 --target {hot}"),
            ("gh api POST releases", "gh api repos/o/r/releases -f tag_name=v1.0.1 -f target_commitish=main"),
            ("gh api -X POST releases, no target", "gh api -X POST repos/{owner}/{repo}/releases -f tag_name=v1.0.1"),
            ("inside bash -c", "bash -c 'gh release create v1.0.1'"),
        ):
            rc, err = run(cmd)
            check(f"release-gate (#1569): {label} publishing an uncertified commit is blocked, naming the stamp",
                  rc == 2 and "qa/CERTIFICATION" in err, f"rc={rc} {err[:200]!r}")
        rc, err = run("gh release create v1.0.1 --target dev")
        check("release-gate (#1569): --target dev publishes the certified tip and is permitted", rc == 0, f"rc={rc} {err[:200]!r}")
        sh("tag", "v0.9", stamped)
        sh("push", "-q", "origin", "v0.9")                # the tag exists ON THE REMOTE: GitHub ignores --target for it
        rc, err = run("gh release create v0.9")
        check("release-gate (#1569): an existing tag is judged by ITS commit, not main's tip", rc == 0, f"rc={rc} {err[:200]!r}")
        sh("branch", "-f", "main", stamped)
        rc, err = run("gh release create v1.0.1")
        check("release-gate (#1569): a new tag publishes the default branch tip, which is now certified", rc == 0, f"rc={rc} {err[:200]!r}")
        sh("branch", "-f", "main", hot)
        rc, err = run("gh release create v1.0.1 --target main", QA_ALLOW_MAIN="1")
        check("release-gate (#1569): QA_ALLOW_MAIN=1 is still the audited override for a release", rc == 0, f"rc={rc} {err[:200]!r}")
        # (#1571) The override is the HOOK's environment, never the command's text: an inline assignment, `env`, an
        # `export`, or a comment all run AFTER the hook (or never), so none can authorise the command that carries it.
        for label, cmd in (
            ("an inline assignment", "QA_ALLOW_MAIN=1 gh release create v1.0.1 --target main"),
            ("`env`", "env QA_ALLOW_MAIN=1 gh release create v1.0.1 --target main"),
            ("an `export`", "export QA_ALLOW_MAIN=1; gh release create v1.0.1 --target main"),
            ("a trailing comment", "gh release create v1.0.1 --target main # QA_ALLOW_MAIN=1"),
            ("a quoted string", "gh release create v1.0.1 --target main --notes 'QA_ALLOW_MAIN=1'"),
        ):
            rc, err = run(cmd)
            check(f"release-gate (#1571): QA_ALLOW_MAIN typed into the command as {label} does not authorise it",
                  rc == 2, f"rc={rc} {err[:200]!r}")
        (repo / ".claude-plugin").mkdir()
        (repo / ".claude-plugin" / "marketplace.json").write_text('{"name":"x","plugins":[]}', encoding="utf-8")
        # The file alone exempts nothing (any repo can add one): origin here is o/r, not the marketplace.
        rc, err = run("gh release create v1.0.1 --target main")
        check("release-gate (#1569): a marketplace.json in a repo that is NOT the marketplace does not exempt a release", rc == 2, f"rc={rc} {err[:200]!r}")
        sh("remote", "set-url", "origin", "https://github.com/fmanimashaun/claude-skills.git")
        rc, err = run("gh release create v1.0.1 --target main")
        check("release-gate (#1569): the marketplace's own repo (by its origin) is exempt from the release gate too", rc == 0, f"rc={rc} {err[:200]!r}")
        rc, err = run("gh api -X PUT repos/fmanimashaun/claude-skills/pulls/7/merge", **hotfix_pr, FAKE_PRREPO="fmanimashaun/claude-skills")
        check("release-gate (#1569): ... and from the API merge gate", rc == 0, f"rc={rc} {err[:200]!r}")
        rc, err = run("gh pr merge 7 -R other/fork", **hotfix_pr, FAKE_PRREPO="other/fork")
        check("release-gate (#1569): ... but never for a command that acts on ANOTHER repository", rc == 2, f"rc={rc} {err[:200]!r}")
        sh("remote", "set-url", "origin", "https://github.com/o/r.git")

        # The fallback with no python3 cannot read `gh api`, so it must stay coarse and closed.
        (repo / ".claude-plugin" / "marketplace.json").unlink(); (repo / ".claude-plugin").rmdir()
        # #1569 (2): publishing by EDIT, and a merge or push judged by the commit it carries, not dev's tip.
        sh("branch", "-f", "dev", stamped)
        for label, cmd, env in (
            ("gh release edit --draft=false, a draft targeting main", "gh release edit v1.0.1 --draft=false", {"FAKE_RELVIEW": "main"}),
            ("gh release edit --draft=false --target main", "gh release edit v1.0.1 --draft=false --target main", {}),
            ("gh release edit with GitHub unable to name the target", "gh release edit v1.0.1 --draft=false", {"FAKE_RELVIEW": ""}),
            ("gh api PATCH releases/<id> draft=false", "gh api -X PATCH repos/o/r/releases/9 -F draft=false", {"FAKE_RELID": "v2 main"}),
            ("gh api PATCH releases/<id> via --input", f"gh api --method=PATCH repos/{{owner}}/{{repo}}/releases/9 --input {td}/draft.json", {"FAKE_RELID": "v2 main"}),
            ("gh api PATCH releases/<id> GitHub cannot name", "gh api -X PATCH repos/o/r/releases/9 -f draft=false", {"FAKE_RELID": ""}),
            ("gh release edit inside bash -c", "bash -c 'gh release edit v1.0.1 --draft=false'", {"FAKE_RELVIEW": "main"}),
        ):
            rc, err = run(cmd, **env)
            check(f"release-gate (#1569): {label} publishes an uncertified commit and is blocked", rc == 2, f"rc={rc} {err[:200]!r}")
        for label, cmd, env in (
            ("a draft whose target is the certified dev", "gh release edit v1.0.1 --draft=false", {"FAKE_RELVIEW": "dev"}),
            ("an existing remote tag at the certified commit (the draft's recorded target is ignored)", "gh release edit v0.9 --draft=false", {"FAKE_RELVIEW": "main"}),
            ("--draft alone (stays a draft)", "gh release edit v1.0.1 --draft", {}),
            ("--draft=true", "gh release edit v1.0.1 --draft=true", {}),
            ("editing the notes", "gh release edit v1.0.1 --notes x", {}),
            ("an API PATCH that does not touch draft", "gh api -X PATCH repos/o/r/releases/9 -f name=x", {}),
            ("an API PATCH of a certified release", "gh api -X PATCH repos/o/r/releases/9 -F draft=false", {"FAKE_RELID": "v0.9 dev"}),
        ):
            rc, err = run(cmd, **env)
            check(f"release-gate (#1569): CONTROL: {label} passes", rc == 0, f"rc={rc} {err[:200]!r}")
        # `git merge <ref>` on main: judged by <ref>'s commit.
        sh("checkout", "-q", "main")
        for label, cmd in (
            ("an uncertified hotfix branch", "git merge hotfix"),
            ("an uncertified sha", f"git merge --no-ff -m 'ship it' {hot}"),
            ("a ref that does not resolve", "git merge no-such-branch"),
            ("a bare merge with no upstream", "git merge"),
            ("a wrapped merge", "timeout 60 git merge hotfix"),
            ("a merge in $( )", "x=$(git merge hotfix)"),
            ("an octopus with one uncertified ref", "git merge dev hotfix"),
        ):
            rc, err = run(cmd)
            check(f"release-gate (#1569): `git merge` on main of {label} is blocked", rc == 2, f"rc={rc} {err[:200]!r}")
        rc, err = run("git merge hotfix")
        check("release-gate (#1569): the denial names the commit being merged, not dev", "commit being merged" in err and hot[:12] in err, err[:200])
        for label, cmd in (("a certified dev", "git merge dev"), ("--abort", "git merge --abort")):
            rc, err = run(cmd)
            check(f"release-gate (#1569): CONTROL: `git merge` on main of {label} passes", rc == 0, f"rc={rc} {err[:200]!r}")
        sh("checkout", "-q", "feature/work")
        rc, err = run("git merge hotfix")
        check("release-gate (#1569): CONTROL: `git merge hotfix` off main is not a promotion", rc == 0, f"rc={rc} {err[:200]!r}")
        # (#1571) The hook reads HEAD and the refs BEFORE the command runs, so a command that moves them first and
        # merges, pulls or pushes after was judged from a state that no longer held. From feature/work:
        for label, cmd in (
            ("a switch to main, then a merge", "git switch main && git merge hotfix"),
            ("a checkout of main, then a merge", "git checkout main && git merge hotfix"),
            ("a quiet checkout of main and a `;`", "git checkout -q main; git merge hotfix"),
            ("a switch -C main, then a merge", "git switch -C main && git merge hotfix"),
            ("a checkout -B main, then a merge", "git checkout -B main && git merge hotfix"),
            ("a switch spelled `git -C .`, then a merge", "git -C . switch main && git merge hotfix"),
            ("a switch spelled `git -C ./`, then a merge", "git -C ./ switch main && git merge hotfix"),
            ("a switch in a directory that may be this one, then a merge", "git -C /nonexistent switch main && git merge hotfix"),
            ("a switch to main, then a pull", "git switch main && git pull"),
            ("a switch to a branch named by a variable", 'git switch "$B" && git merge hotfix'),
            ("`checkout -`, which names no branch", "git checkout - && git merge hotfix"),
            ("a branch rename onto main, then a merge", "git branch -M main && git merge hotfix"),
            ("a rebase onto main's branch, then a merge", "git rebase dev main && git merge hotfix"),
            ("a switch to main, a merge of CERTIFIED dev, then a push of main", "git switch main && git merge dev && git push origin main"),
            ("a commit, then a push of main", "git commit --allow-empty -m x && git push origin main"),
            ("a switch to hotfix, then a push of HEAD to main", "git switch hotfix && git push origin HEAD:main"),
            ("a fetch of a refspec onto main, then a push of main", "git fetch origin hotfix:main && git push origin main"),
        ):
            rc, err = run(cmd)
            check(f"release-gate (#1571): {label} is blocked", rc == 2, f"rc={rc} {err[:200]!r}")
        for label, cmd in (
            ("a switch to another branch, then a merge", "git switch topic && git merge hotfix"),
            ("a new branch, then a merge", "git checkout -b topic2 && git merge hotfix"),
            ("a detached checkout, then a merge", "git checkout --detach dev && git merge hotfix"),
            ("a checkout that may be a path, from a branch that is not main", "git checkout README.md && git merge hotfix"),
            ("`checkout -- path`, which leaves HEAD alone", "git checkout -- README.md && git merge hotfix"),
            ("a switch to main and a merge of CERTIFIED dev", "git switch main && git merge dev"),
            ("a commit on a feature branch, then a push of a feature branch", "git commit --allow-empty -m x && git push origin feature/x"),
            ("a branch listing, then a merge off main", "git branch --list && git merge hotfix"),
            ("a status, then a push of a feature branch", "git status && git push origin feature/work"),
        ):
            rc, err = run(cmd)
            check(f"release-gate (#1571): CONTROL: {label} passes", rc == 0, f"rc={rc} {err[:200]!r}")
        # `git push <remote> <src>:main`: judged by <src>'s commit.
        for label, cmd in (
            ("a branch", "git push origin hotfix:main"),
            ("a sha to refs/heads/main", f"git push origin {hot}:refs/heads/main"),
            ("a forced refspec", "git push origin +hotfix:master"),
            ("a ref that does not resolve", "git push origin no-such:main"),
            ("a wrapped push", "timeout 60 git push origin hotfix:main"),
        ):
            rc, err = run(cmd)
            check(f"release-gate (#1569): push of {label} to main is blocked", rc == 2, f"rc={rc} {err[:200]!r}")
        rc, err = run("git push origin hotfix:main")
        check("release-gate (#1569): the denial names the commit being pushed, not dev", "commit being merged or pushed" in err and hot[:12] in err, err[:200])
        for label, cmd in (("a certified dev", "git push origin dev:main"), ("a certified HEAD", "git push origin HEAD:refs/heads/main"),
                           ("a certified sha", f"git push origin {stamped}:main"), ("a feature branch", "git push origin hotfix:feature/x")):
            rc, err = run(cmd)
            check(f"release-gate (#1569): CONTROL: push of {label} passes", rc == 0, f"rc={rc} {err[:200]!r}")
        only = Path(td) / "only"; only.mkdir()
        (only / "bash").symlink_to(shutil.which("bash"))
        for cmd in ("gh api -X PUT repos/o/r/pulls/7/merge", "gh release create v1", "gh release edit v1 --draft=false", "gh api graphql -f query=x -f u=mergePullRequest"):
            done = _run([str(only / "bash"), str(QA_HOOK)], cwd=repo, input=json.dumps({"tool_input": {"command": cmd}}),
                        env={"PATH": str(only)}, capture_output=True, text=True, timeout=60)
            check(f"release-gate (#1569): with ONLY bash on PATH, `{cmd}` is still blocked", done.returncode == 2, f"rc={done.returncode}")



# ---- #1569, second half: the command and the gate must agree on WHAT is acted on and WHERE. A different
# repository (-R, GH_REPO, a repos/<o>/<r> path, another remote), a different directory (cd, git -C), a
# different argument (the PR number, the ref a merge or ref write carries, the tag a release resolves to),
# and a command spelled so that shlex and bash read it differently.
FAKE_GH2 = """#!/bin/sh
[ -z "${FAKE_LOG:-}" ] || printf '%s\\n' "$*" >> "$FAKE_LOG"
ep=""; for a in "$@"; do case "$a" in repos/*) ep="$a"; break ;; esac; done
case "$1 $2" in
  "pr view")
    sel="$3"; case "$sel" in -*) sel="" ;; esac
    v=""
    if [ -n "$sel" ]; then
      key="$(printf '%s' "$sel" | tr -c 'A-Za-z0-9' _)"
      eval "v=\\${FAKE_PRVIEW_$key:-}"
    fi
    [ -n "$v" ] || v="${FAKE_PRVIEW:-}"
    [ -z "$v" ] || printf '%s https://github.com/%s/pull/7' "$v" "${FAKE_PRREPO:-o/r}"
    exit 0 ;;
  "api graphql")
    case "$*" in
      *"on Ref"*) [ -z "${FAKE_REF:-}" ] || printf '%s %s' "$FAKE_REF" "${FAKE_PRREPO:-o/r}" ;;
      *) [ -z "${FAKE_NODE:-}" ] || printf '%s %s' "$FAKE_NODE" "${FAKE_PRREPO:-o/r}" ;;
    esac; exit 0 ;;
  "release view") printf '%s' "${FAKE_RELVIEW:-}"; exit 0 ;;
esac
case "$ep" in
  repos/*/contents/*)
    [ -z "${FAKE_SLEEP:-}" ] || sleep "$FAKE_SLEEP"
    ref="${ep##*ref=}"
    [ -n "${FAKE_STAMP_REF:-}" ] && [ "$ref" = "$FAKE_STAMP_REF" ] && [ -f "${FAKE_STAMP_FILE:-/nonexistent}" ] && { cat "$FAKE_STAMP_FILE"; exit 0; }
    exit 1 ;;
  repos/*/compare/*) [ -z "${FAKE_SLEEP_COMPARE:-${FAKE_SLEEP:-}}" ] || sleep "${FAKE_SLEEP_COMPARE:-$FAKE_SLEEP}"; [ -n "${FAKE_COMPARE:-}" ] || exit 1; printf '%s\\n' "$FAKE_COMPARE"; exit 0 ;;
  repos/*/commits/*) [ -n "${FAKE_COMMIT:-}" ] || exit 1; printf '%s' "$FAKE_COMMIT"; exit 0 ;;
  repos/*/git/matching-refs/*) printf '%s' "${FAKE_TAGS:-}"; exit 0 ;;
  repos/*/releases/*) printf '%s' "${FAKE_RELID:-}"; exit 0 ;;
  repos/*) printf 'main'; exit 0 ;;
esac
exit 1
"""


def release_gate_refs_fixtures() -> None:
    """#1600: a ref taken from the GATED COMMAND'S TEXT must never reach git as an option. The release gate is a
    PreToolUse hook, so it runs before the permission prompt: `git fetch origin --upload-pack=<program>` RUNS the
    program when origin is a local path or ssh. Each site that hands such a value to git or gh is driven with a
    marker file, over a local-path origin: no marker may appear, and the command is denied."""
    if not QA_HOOK.is_file():
        check("release-gate (#1600): release-gate.sh present beside rails-flow", False, str(QA_HOOK))
        return
    g = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _git_repo(repo)
        sh = lambda *a, **kw: _run([*g, *a], cwd=repo, check=True, capture_output=True, text=True, **kw).stdout.strip()
        old = {**os.environ, "GIT_COMMITTER_DATE": "2026-09-01T00:00:00+00:00", "GIT_AUTHOR_DATE": "2026-09-01T00:00:00+00:00"}
        bare = Path(td) / "origin.git"
        _run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
        # The bare repository also stands in for other/fork, whose evidence the hook fetches (#1591): it holds `stamped` as dev.
        for k, v in (("uploadpack.allowFilter", "true"), ("uploadpack.allowAnySHA1InWant", "true")):
            _run(["git", "config", k, v], cwd=bare, check=True, capture_output=True)
        # origin names o/r, and is a LOCAL PATH underneath: the transport that runs --upload-pack.
        sh("remote", "add", "origin", "https://github.com/o/r.git")
        sh("config", f"url.{bare}.insteadOf", "https://github.com/o/r.git")
        (repo / "app.rb").write_text("v1\n", encoding="utf-8")
        sh("add", "app.rb"); sh("commit", "-q", "-m", "app")
        tested = sh("rev-parse", "HEAD")
        (repo / "qa").mkdir()
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps(
            {"sha": tested, "date": "2026-09-26", "verdict": "PASS", "report": "qa/reports/r.md"}), encoding="utf-8")
        sh("add", "qa/CERTIFICATION"); sh("commit", "-q", "-m", "stamp", env=old)
        stamped = sh("rev-parse", "HEAD")
        sh("branch", "-f", "dev", stamped)
        sh("branch", "fix/x-y", stamped)
        sh("checkout", "-q", "-b", "feature/work")
        sh("push", "-q", "origin", "dev:dev")
        (Path(td) / "bin").mkdir()
        (Path(td) / "bin" / "gh").write_text(FAKE_GH2, encoding="utf-8")
        (Path(td) / "bin" / "gh").chmod(0o755)
        marker = Path(td) / "MARKER"
        # --upload-pack=<program>: git runs the program through the shell with the remote's path. No space in the value,
        # so the classifier reads it as one token and the hook reaches the git call (a payload with spaces is refused earlier).
        prog = Path(td) / "prog.sh"
        prog.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
        prog.chmod(0o755)
        evil = f"--upload-pack={prog}"

        def run(cmd: str, **extra) -> tuple[int, str]:
            marker.unlink(missing_ok=True)
            env = dict(os.environ); env.pop("QA_ALLOW_MAIN", None); env.pop("GH_REPO", None)
            env["CLAUDE_PLUGIN_ROOT"] = str(QA_HOOK.parents[2])
            env["PATH"] = str(Path(td) / "bin") + os.pathsep + env["PATH"]
            # No test reaches github.com: every https://github.com/ url is a path that does not exist, except other/fork, which is
            # the local bare repository (#1591).
            env.update({"GIT_CONFIG_COUNT": "2",
                        "GIT_CONFIG_KEY_0": "url./nonexistent-qa-flow-remote/.insteadOf", "GIT_CONFIG_VALUE_0": "https://github.com/",
                        "GIT_CONFIG_KEY_1": f"url.{bare}.insteadOf", "GIT_CONFIG_VALUE_1": "https://github.com/other/fork.git"})
            env.update(extra)
            done = _run(["bash", str(QA_HOOK)], cwd=repo, input=json.dumps({"tool_input": {"command": cmd}}),
                        env=env, capture_output=True, text=True, timeout=60)
            return done.returncode, done.stderr

        # The proof that the marker is observable: the same program, handed to git the way the hook would have.
        marker.unlink(missing_ok=True)
        _run(["git", "fetch", "-q", "origin", evil], cwd=repo, capture_output=True)
        check("release-gate (#1600): the probe works -- an unguarded `git fetch origin <--upload-pack=...>` DOES run the program",
              marker.exists(), "no marker: this fixture could not tell a fix from a hole")
        # Every site where a ref from the command's own text reaches git or gh.
        for label, cmd, extra in (
            ("a REST merge's `head`", f"gh api repos/o/r/merges -f base=main -f head='{evil}'", {}),
            ("a ref write's `sha`", f"gh api -X PATCH repos/o/r/git/refs/heads/main -f sha='{evil}'", {}),
            ("a new ref's `sha`", f"gh api repos/o/r/git/refs -f ref=refs/heads/main -f sha='{evil}'", {}),
            ("a release's --target", f"gh release create v9 --target '{evil}'", {}),
            ("a commit the PR view reports", "gh pr merge 7", {"FAKE_PRVIEW": f"main {evil}"}),
        ):
            rc, err = run(cmd, **extra)
            check(f"release-gate (#1600): {label} that starts with `--` runs no program, and is denied",
                  not marker.exists() and rc == 2, f"marker={marker.exists()} rc={rc} {err[:200]!r}")
        # The same, with the value an ordinary option rather than a program: gh must never read it as a selector.
        log = Path(td) / "gh.log"
        for label, cmd in (("a PR selector", "gh pr merge --web"),
                           ("a PR selector after the end of options", "gh pr merge --admin -- --web")):
            log.unlink(missing_ok=True)
            rc, err = run(cmd, FAKE_PRVIEW=f"main {stamped}", FAKE_LOG=str(log))
            asked = log.read_text().splitlines() if log.exists() else []
            check(f"release-gate (#1600): {label} that starts with  is never handed to gh, and the command is denied",
                  not any("--web" in line for line in asked) and rc == 2, f"rc={rc} gh calls={asked} {err[:160]!r}")
        # A stamp is data from the repository being promoted: its `sha` is a commit id, never an option.
        bad = Path(td) / "badstamp"
        _git_repo(bad)
        bsh = lambda *a, **kw: _run([*g, *a], cwd=bad, check=True, capture_output=True, text=True, **kw).stdout.strip()
        _run(["git", "checkout", "-q", "-B", "main"], cwd=bad, check=True, capture_output=True)
        (bad / "qa").mkdir()
        (bad / "qa" / "CERTIFICATION").write_text(json.dumps(
            {"sha": evil, "date": "2026-09-26", "verdict": "PASS", "report": "r.md"}), encoding="utf-8")
        bsh("add", "qa"); bsh("commit", "-q", "-m", "stamp")
        bsh("branch", "dev")
        marker.unlink(missing_ok=True)
        env = dict(os.environ); env.pop("QA_ALLOW_MAIN", None)
        env["CLAUDE_PLUGIN_ROOT"] = str(QA_HOOK.parents[2])
        done = _run(["bash", str(QA_HOOK)], cwd=bad, input=json.dumps({"tool_input": {"command": "git push origin main"}}),
                    env=env, capture_output=True, text=True, timeout=60)
        check("release-gate (#1600): a stamp whose `sha` is an option is denied as not a commit id",
              done.returncode == 2 and "not a commit id" in done.stderr and not marker.exists(), f"rc={done.returncode} {done.stderr[:240]!r}")
        # ANOTHER repository's stamp is the same kind of data: its `sha` is a commit id, never a path of the API.
        evil_stamp = Path(td) / "evil-stamp.json"
        evil_stamp.write_text(json.dumps({"sha": "../../x?y", "date": "2026-10-01", "verdict": "PASS", "report": "r.md"}), encoding="utf-8")
        rc, err = run(_pin("gh pr merge 7 -R other/fork", stamped), FAKE_PRVIEW=f"main {stamped}", FAKE_PRREPO="other/fork",
                      FAKE_STAMP_REF=stamped, FAKE_STAMP_FILE=str(evil_stamp), FAKE_COMPARE="ahead")
        check("release-gate (#1600): ANOTHER repository's stamp whose `sha` is a path is denied as not a commit id",
              rc == 2 and "not a commit id" in err, f"rc={rc} {err[:240]!r}")
        # A ref with a `:` is a REFSPEC: `git fetch origin dev:refs/heads/injected` writes a local branch, before the prompt.
        rc, err = run("gh api repos/o/r/merges -f base=main -f head=dev:refs/heads/injected")
        made = _run(["git", "rev-parse", "--verify", "-q", "refs/heads/injected"], cwd=repo, capture_output=True).returncode == 0
        check("release-gate (#1600): a ref with a `:` (a refspec) is never fetched, so no local ref is written, and it is denied",
              not made and rc == 2, f"ref written={made} rc={rc} {err[:200]!r}")
        # CONTROLS: a dash INSIDE a name is a name, and a certified branch still promotes.
        rc, err = run("gh api repos/o/r/merges -f base=main -f head=fix/x-y")
        check("release-gate (#1600): CONTROL: a branch whose name has a dash inside is still read and judged (certified: passes)",
              rc == 0, f"rc={rc} {err[:240]!r}")
        rc, err = run("gh api repos/o/r/merges -f base=main -f head=dev")
        check("release-gate (#1600): CONTROL: the certified dev still promotes", rc == 0, f"rc={rc} {err[:240]!r}")
        # ANOTHER repository (`other/fork`) whose own PASS stamp certifies `stamped`, read through the API (the fake gh).
        foreign_stamp = Path(td) / "foreign-stamp.json"
        foreign_stamp.write_text(json.dumps({"sha": stamped, "date": "2026-10-01", "verdict": "PASS", "report": "r.md"}), encoding="utf-8")
        ok_api = {"FAKE_STAMP_REF": stamped, "FAKE_STAMP_FILE": str(foreign_stamp), "FAKE_COMMIT": stamped, "FAKE_PRREPO": "other/fork"}
        # (#1606) A ref, tag or target from the command's text becomes part of ANOTHER repository's API path
        # (`repos/<r>/commits/<ref>`). The fake gh answers any commits/<anything> with the certified commit, as an endpoint
        # reached through a fragment or a climb would answer something, so a value that is not a plain name must be refused
        # BEFORE the call. `#` is a legal character in a ref name and starts a fragment in a URL: the gate would ask about
        # `abc` while the command acts on `abc#frag`.
        for label, cmd in (
            ("a REST merge's head with a fragment", "gh api repos/other/fork/merges -f base=main -f head='abc#frag'"),
            ("a REST merge's head that climbs", "gh api repos/other/fork/merges -f base=main -f head='x/../../../issues/1'"),
            ("a REST merge's head with an escaped slash", "gh api repos/other/fork/merges -f base=main -f head=a%2fb"),
            ("a ref write's sha that climbs", "gh api -X PATCH repos/other/fork/git/refs/heads/main -f sha='../../x'"),
            ("a ref write's sha with a fragment", "gh api -X PATCH repos/other/fork/git/refs/heads/main -f sha='abc#frag'"),
            ("a release's --target that climbs", "gh release create v1 -R other/fork --target ../../x"),
            ("a release's --target with an escaped slash", "gh release create v1 -R other/fork --target a%2fb"),
            ("a release's tag that climbs", "gh release create ../../x -R other/fork --target main"),
            ("a release's tag with an escaped slash", "gh release create a%2fb -R other/fork --target main"),
        ):
            rc, err = run(cmd, **ok_api)
            check(f"release-gate (#1606): {label} is not a plain name, is never put in another repository's API path, and is DENIED",
                  rc == 2, f"rc={rc} {err[:240]!r}")
        for label, cmd in (
            ("a REST merge's head", "gh api repos/other/fork/merges -f base=main -f head=feature/x-y"),
            ("a ref write's sha", f"gh api -X PATCH repos/other/fork/git/refs/heads/main -f sha={stamped}"),
            ("a release's tag and target", "gh release create v1.2.3 -R other/fork --target release/2026-10"),
        ):
            rc, err = run(cmd, **ok_api)
            check(f"release-gate (#1606): CONTROL: {label} that is a plain name is read and judged (certified: permitted)",
                  rc == 0 and "other/fork" in err, f"rc={rc} {err[:240]!r}")
        # (#1606) The third fetch takes the object id `git ls-remote origin refs/tags/<tag>` printed. It is an object id by
        # construction of a well-behaved origin; an origin that prints anything else must not be handed to `git fetch`. A
        # `git` that answers ls-remote with an option and logs every call stands in for that origin.
        gitbin = Path(td) / "gitbin"
        gitbin.mkdir(exist_ok=True)
        gitlog = Path(td) / "git.log"
        real_git = shutil.which("git")
        (gitbin / "git").write_text(
            f'#!/bin/sh\nprintf \'%s\\n\' "$*" >> "{gitlog}"\ncase "$1" in\n'
            f'  ls-remote) printf \'%s\\trefs/tags/v9\\n\' "{evil}"; exit 0 ;;\nesac\nexec {real_git} "$@"\n', encoding="utf-8")
        (gitbin / "git").chmod(0o755)
        gitlog.unlink(missing_ok=True)
        rc, err = run("gh release create v9 --target dev", PATH=f"{gitbin}{os.pathsep}{Path(td) / 'bin'}{os.pathsep}{os.environ['PATH']}")
        calls = gitlog.read_text().splitlines() if gitlog.exists() else []
        check("release-gate (#1606): an object id from `git ls-remote` that is an option is never handed to `git fetch`, and the release is DENIED",
              not any(c.startswith("fetch") and "--upload-pack" in c for c in calls) and not marker.exists() and rc == 2,
              f"rc={rc} marker={marker.exists()} fetch calls={[c for c in calls if c.startswith('fetch')]}")

        # (#1610, hardening left by the #1609 review.) 1. The commit id GitHub's API returned is joined into
        # `contents/qa/CERTIFICATION?ref=<sha>`: it is a commit id or the command is refused. The fake gh serves the stamp for
        # whatever ref the id names, as an endpoint reached through a fragment, a climb or an escaped slash would.
        # (The evidence helper refuses a short id too, but only AFTER the stamp was read through that URL, so the proof is the
        # fake gh's own log: no contents call may carry the id.)
        for bad in ("abc#frag", "../x", "a%2fb"):
            calls = Path(td) / "gh-calls.log"
            calls.unlink(missing_ok=True)
            rc, err = run("gh api repos/other/fork/merges -f base=main -f head=dev",
                          **{**ok_api, "FAKE_COMMIT": bad, "FAKE_STAMP_REF": bad, "FAKE_COMPARE": "ahead", "FAKE_LOG": str(calls)})
            asked = [l for l in (calls.read_text().splitlines() if calls.exists() else []) if "contents/qa/CERTIFICATION" in l]
            check(f"release-gate (#1610): a commit id from the API that reads `{bad}` is never put in a contents URL, and is DENIED",
                  rc == 2 and "not a commit id" in err and not asked, f"rc={rc} contents calls={asked} {err[:200]!r}")
        # 2. A release tag on the local path goes to `git ls-remote refs/tags/<tag>`, whose pattern takes a glob: `v*` lists every
        # v tag. The command's own text cannot carry one (the classifier refuses it), so the way in is the tag GitHub's
        # `releases/<id>` answer names (FAKE_RELID). A tag that is not a plain name is refused; a plain tag the remote holds is
        # still resolved and judged.
        sh("tag", "v1.0", stamped)
        sh("push", "-q", "origin", "v1.0")
        rc, err = run("gh api -X PATCH repos/o/r/releases/12 -f draft=false", FAKE_RELID="v* dev")
        check("release-gate (#1610): a release tag with a glob is never handed to `git ls-remote` as a pattern, and is DENIED",
              rc == 2, f"rc={rc} {err[:240]!r}")
        rc, err = run("gh api -X PATCH repos/o/r/releases/12 -f draft=false", FAKE_RELID="v1.0 dev")
        check("release-gate (#1610): CONTROL: a plain release tag the remote holds is still resolved and judged (certified: permitted)",
              rc == 0, f"rc={rc} {err[:240]!r}")
        # 3. `plain_ref` names what git itself would refuse: a leading or doubled or trailing slash, a component that starts with a
        # dot, a `.lock` ending, a trailing dot. Through ANOTHER repository's API path each would otherwise be asked about.
        for shape in ("/x", "./x", "a//b", "x/", "a/./b", "x.lock", "x."):
            rc, err = run(f"gh api repos/other/fork/merges -f base=main -f head={shape}", **ok_api)
            check(f"release-gate (#1610): the ref `{shape}`, which git refuses as a name, is never put in another repository's API path, and is DENIED",
                  rc == 2, f"rc={rc} {err[:240]!r}")
        for ok in ("feature/x-y", "release/2026-10", "v1.2.3", "a.b/c_d"):
            rc, err = run(f"gh api repos/other/fork/merges -f base=main -f head={ok}", **ok_api)
            check(f"release-gate (#1610): CONTROL: the plain name `{ok}` is still read and judged (certified: permitted)",
                  rc == 0, f"rc={rc} {err[:240]!r}")


@real_setup
def release_gate_repos_fixtures() -> None:
    g = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _git_repo(repo)
        sh = lambda *a, **kw: _run([*g, *a], cwd=repo, check=True, capture_output=True, text=True, **kw).stdout.strip()
        old = {**os.environ, "GIT_COMMITTER_DATE": "2026-09-01T00:00:00+00:00", "GIT_AUTHOR_DATE": "2026-09-01T00:00:00+00:00"}
        bare = Path(td) / "origin.git"
        _run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
        # other/fork, as the hook fetches it (#1591): a local bare repository standing in for github.com.
        forkbare = Path(td) / "fork.git"
        _run(["git", "init", "-q", "--bare", str(forkbare)], check=True, capture_output=True)
        for k, v in (("uploadpack.allowFilter", "true"), ("uploadpack.allowAnySHA1InWant", "true")):
            _run(["git", "config", k, v], cwd=forkbare, check=True, capture_output=True)
        sh("remote", "add", "origin", "https://github.com/o/r.git")
        sh("config", f"url.{bare}.insteadOf", "https://github.com/o/r.git")
        sh("remote", "add", "upstream", "https://github.com/other/fork.git")
        (repo / "app.rb").write_text("v1\n", encoding="utf-8")
        sh("add", "app.rb"); sh("commit", "-q", "-m", "app")
        tested = sh("rev-parse", "HEAD")
        (repo / "qa").mkdir()
        stamp = {"sha": tested, "date": "2026-09-26", "verdict": "PASS", "report": "qa/reports/r.md"}
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps(stamp), encoding="utf-8")
        sh("add", "qa/CERTIFICATION"); sh("commit", "-q", "-m", "stamp", env=old)
        stamped = sh("rev-parse", "HEAD")
        sh("branch", "-f", "dev", stamped)
        sh("checkout", "-q", "-b", "hotfix")
        (repo / "app.rb").write_text("hotfix\n", encoding="utf-8")
        sh("commit", "-q", "-am", "hotfix, never certified")
        hot = sh("rev-parse", "HEAD")
        sh("checkout", "-q", "-b", "feature/work", stamped)
        sh("branch", "-f", "main", hot)
        sh("tag", "v0.9", stamped); sh("tag", "v0.8", hot)
        sh("push", "-q", "origin", "v0.9", "v0.8")
        sh("push", "-q", str(forkbare), f"{stamped}:refs/heads/dev", f"{hot}:refs/heads/hot")
        # another checkout, on main, whose dev has no stamp at all
        sub = Path(td) / "sub"
        _git_repo(sub)
        _run([*g, "checkout", "-q", "-B", "main"], cwd=sub, check=True, capture_output=True)
        _run([*g, "branch", "dev"], cwd=sub, check=True, capture_output=True)
        (Path(td) / "bin").mkdir()
        (Path(td) / "bin" / "gh").write_text(FAKE_GH2, encoding="utf-8")
        (Path(td) / "bin" / "gh").chmod(0o755)
        foreign_stamp = Path(td) / "foreign-stamp.json"
        foreign_stamp.write_text(json.dumps({"sha": stamped, "date": "2026-10-01", "verdict": "PASS", "report": "r.md"}), encoding="utf-8")

        def run(cmd: str, **extra) -> tuple[int, str]:
            env = dict(os.environ); env.pop("QA_ALLOW_MAIN", None); env.pop("GH_REPO", None)
            env["CLAUDE_PLUGIN_ROOT"] = str(QA_HOOK.parents[2])
            env["PATH"] = str(Path(td) / "bin") + os.pathsep + env["PATH"]
            # No test reaches github.com: every https://github.com/ url is a path that does not exist, except
            # other/fork, which is the local bare repository the hook may fetch evidence from (#1591).
            env.update({"GIT_CONFIG_COUNT": "2",
                        "GIT_CONFIG_KEY_0": "url./nonexistent-qa-flow-remote/.insteadOf", "GIT_CONFIG_VALUE_0": "https://github.com/",
                        "GIT_CONFIG_KEY_1": f"url.{forkbare}.insteadOf", "GIT_CONFIG_VALUE_1": "https://github.com/other/fork.git"})
            env.update(extra)
            done = _run(["bash", str(QA_HOOK)], cwd=repo, input=json.dumps({"tool_input": {"command": cmd}}),
                        env=env, capture_output=True, text=True, timeout=60)
            return done.returncode, done.stderr

        ok_pr = {"FAKE_PRVIEW": f"main {stamped}"}
        # (1) THE SAME COMMAND, a different repository. This checkout is o/r and holds a PASS stamp at the PR's
        # head, so judging it here would permit; the command acts on other/fork, whose stamp must be read there.
        for label, cmd, env in (
            ("gh pr merge -R", "gh pr merge 7 -R other/fork", {**ok_pr, "FAKE_PRREPO": "other/fork"}),
            ("gh pr merge --repo=", "gh pr merge 7 --repo=other/fork", {**ok_pr, "FAKE_PRREPO": "other/fork"}),
            ("gh pr -R before the subcommand", "gh pr -R other/fork merge 7", {**ok_pr, "FAKE_PRREPO": "other/fork"}),
            ("GH_REPO in the command", "GH_REPO=other/fork gh pr merge 7", {**ok_pr, "FAKE_PRREPO": "other/fork"}),
            ("GH_REPO exported earlier", "export GH_REPO=other/fork; gh pr merge 7", {**ok_pr, "FAKE_PRREPO": "other/fork"}),
            ("GH_REPO in the hook's environment", "gh pr merge 7", {**ok_pr, "GH_REPO": "other/fork", "FAKE_PRREPO": "other/fork"}),
            ("a PR whose URL is another repository", "gh pr merge 7", {**ok_pr, "FAKE_PRREPO": "other/fork"}),
            ("a repos/<owner>/<repo> path", "gh api -X PUT repos/other/fork/pulls/7/merge", {**ok_pr, "FAKE_PRREPO": "other/fork"}),
            ("a REST merge into another repository", "gh api repos/other/fork/merges -f base=main -f head=dev", {"FAKE_COMMIT": stamped}),
            ("a ref write in another repository", f"gh api -X PATCH repos/other/fork/git/refs/heads/main -f sha={stamped}", {"FAKE_COMMIT": stamped}),
            ("gh release create -R", "gh release create v1 -R other/fork --target main", {"FAKE_COMMIT": stamped}),
            ("a draft published with -R", "gh release edit v1 --draft=false -R other/fork", {"FAKE_RELVIEW": "main", "FAKE_COMMIT": stamped}),
            ("another git remote", "git push upstream dev:main", {}),
            ("a remote given as a URL", "git push git@github.com:other/fork.git dev:main", {}),
        ):
            rc, err = run(_pin(cmd, stamped), **env)
            check(f"release-gate (#1569): {label} acts on ANOTHER repository, whose stamp cannot be read, and is blocked",
                  rc == 2 and "other/fork" in err, f"rc={rc} {err[:240]!r}")
        # ... and permitted when that repository's own stamp is read through the API and certifies the commit.
        ok_api = {"FAKE_STAMP_REF": stamped, "FAKE_STAMP_FILE": str(foreign_stamp), "FAKE_COMMIT": stamped, "FAKE_PRREPO": "other/fork"}
        for label, cmd, env in (
            ("gh pr merge -R", "gh pr merge 7 -R other/fork", ok_pr),
            ("GH_REPO", "GH_REPO=other/fork gh pr merge 7", ok_pr),
            ("a repos/<owner>/<repo> merge path", "gh api -X PUT repos/other/fork/pulls/7/merge", ok_pr),
            ("a release into another repository", "gh release create v1 -R other/fork --target main", {}),
            ("another git remote", "git push upstream dev:main", {}),
        ):
            rc, err = run(_pin(cmd, stamped), **{**ok_api, **env})
            check(f"release-gate (#1569): {label} is permitted by the OTHER repository's own PASS stamp, read through the API",
                  rc == 0 and "other/fork" in err, f"rc={rc} {err[:240]!r}")
        # Each of these has ONE signal that the command acts on another repository, so ignoring that signal is visible.
        # GH_REPO alone: no -R, no path, no PR URL. Judged here, `--target main` (the uncertified local main) is denied.
        rc, err = run("gh release create v1 --target main", GH_REPO="other/fork", **ok_api)
        check("release-gate (#1591): GH_REPO ALONE sends a release to the OTHER repository's stamp, which permits it",
              rc == 0 and "other/fork" in err, f"rc={rc} {err[:240]!r}")
        # A host-qualified repository is not owner/repo: refused as unresolved, even where the API would answer for any repository.
        # (Not `-R` or a path in the command: the classifier refuses a host-qualified repository there before the hook sees it. The
        # hook's own check is the one on GH_REPO in ITS environment, which the classifier never reads. The fake gh serves a stamp
        # for ANY repository, so a repository accepted by mistake would be judged and permitted.)
        rc, err = run("gh release create v1 --target main", GH_REPO="ghe.example.com/o/r", **ok_api)
        check("release-gate (#1591): a host-qualified GH_REPO is refused as unresolved, though the API would serve it a stamp",
              rc == 2 and "cannot tell" in err, f"rc={rc} {err[:240]!r}")
        rc, err = run(_pin("gh pr merge 7 -R other/fork", stamped), **{**ok_api, **ok_pr, "FAKE_COMPARE": "ahead\napp.rb", "FAKE_STAMP_REF": hot}, )
        check("release-gate (#1569): another repository's stamp for an OLDER commit must cover only the stamp itself",
              rc == 2, f"rc={rc} {err[:240]!r}")
        # (2) NOT over-blocked: -R / GH_REPO / a path naming THIS checkout's own repository is judged here.
        for cmd in ("gh pr merge 7 -R o/r", "gh pr merge 7 -R O/R", "GH_REPO=o/r gh pr merge 7", "gh api -X PUT repos/o/r/pulls/7/merge",
                    "git push origin dev:main", "git push origin HEAD:main"):
            rc, err = run(_pin(cmd, stamped), **ok_pr)
            check(f"release-gate (#1569): CONTROL: `{cmd}` names this checkout's own repository and is judged here (certified: passes)",
                  rc == 0, f"rc={rc} {err[:240]!r}")
        rc, err = run(_pin("gh pr merge 7 -R o/r", hot), FAKE_PRVIEW=f"main {hot}")
        check("release-gate (#1569): CONTROL: ... and an uncertified head is still blocked", rc == 2 and "PR head" in err, f"rc={rc} {err[:240]!r}")
        # Unreadable repositories and remotes deny.
        for label, cmd in (
            ("a host-qualified repository", "gh pr merge 7 -R ghe.example.com/o/r"),
            ("a repository from a variable", "gh pr merge 7 -R $R"),
            ("GH_REPO from a variable", "GH_REPO=$R gh pr merge 7"),
            ("GH_REPO as a URL", "GH_REPO=https://github.com/o/r gh pr merge 7"),
            ("--hostname", "gh api --hostname ghe.example.com -X PUT repos/o/r/pulls/7/merge"),
            ("a remote that does not exist", "git push nowhere dev:main"),
            ("a remote that is a path", "git push ../elsewhere dev:main"),
            ("a remote from a variable", "git push $REMOTE dev:main"),
        ):
            rc, err = run(cmd, **ok_pr)
            check(f"release-gate (#1569): {label} cannot be paired with a stamp and is blocked", rc == 2, f"rc={rc} {err[:240]!r}")
        # (3) A different DIRECTORY: the stamp is read where the command runs.
        for label, cmd in (
            ("cd into another checkout", f"cd {sub} && git merge dev"),
            ("git -C into another checkout", f"git -C {sub} merge dev"),
            ("a cd that cannot be followed", "cd $SOMEWHERE && git merge dev"),
            ("two different directories", f"cd {sub} && git merge dev; cd .. && git merge dev"),
        ):
            rc, err = run(cmd)
            check(f"release-gate (#1569): {label} is judged in THAT directory (no stamp there) and blocked", rc == 2, f"rc={rc} {err[:240]!r}")
        rc, err = run(f"cd {sub} && git status")
        check("release-gate (#1569): CONTROL: a cd with no merge or push passes", rc == 0, f"rc={rc} {err[:240]!r}")
        rc, err = run("git merge dev")
        check("release-gate (#1569): CONTROL: `git merge dev` off main in this checkout is not a promotion", rc == 0, f"rc={rc} {err[:240]!r}")
        # (4) The ARGUMENT the command acts on, not another one in the command line.
        rc, err = run("gh pr merge -b 8 7", FAKE_PRVIEW_7=f"main {hot}", FAKE_PRVIEW_8=f"dev {stamped}")
        check("release-gate (#1569): `gh pr merge -b 8 7` merges PR 7 (not the 8 that is the body) and is judged on PR 7's head",
              rc == 2 and hot[:12] in err, f"rc={rc} {err[:240]!r}")
        rc, err = run("gh pr merge 7 --match-head-commit 8", FAKE_PRVIEW_7=f"main {hot}", FAKE_PRVIEW_8=f"dev {stamped}")
        check("release-gate (#1569): `--match-head-commit 8` is not the PR: PR 7 is judged", rc == 2 and hot[:12] in err, f"rc={rc} {err[:240]!r}")
        for label, cmd, ok in (
            ("a REST merge's `head` (dev is certified, the head is not)", "gh api repos/o/r/merges -f base=main -f head=hotfix", False),
            ("a REST merge of the certified dev", "gh api repos/o/r/merges -f base=main -f head=dev", True),
            ("a ref write's `sha` (dev is certified, the sha is not)", f"gh api -X PATCH repos/o/r/git/refs/heads/main -f sha={hot}", False),
            ("a ref write of the certified sha", f"gh api -X PATCH repos/o/r/git/refs/heads/main -f sha={stamped}", True),
            ("a new main ref at an uncertified sha", f"gh api repos/o/r/git/refs -f ref=refs/heads/main -f sha={hot}", False),
            ("a REST merge with no head at all", "gh api repos/o/r/merges -f base=main", False),
            ("a ref write with no sha at all", "gh api -X PATCH repos/o/r/git/refs/heads/main", False),
            ("a GraphQL updateRef's oid", "gh api graphql -f query='mutation { updateRef(input:{refId:\"R1\", oid:\"%s\"}) { clientMutationId } }'" % hot, False),
            ("a GraphQL updateRef of the certified oid", "gh api graphql -f query='mutation { updateRef(input:{refId:\"R1\", oid:\"%s\"}) { clientMutationId } }'" % stamped, True),
            ("a GraphQL createRef's oid", "gh api graphql -f query='mutation { createRef(input:{name:\"refs/heads/main\", oid:\"%s\"}) { clientMutationId } }'" % hot, False),
        ):
            rc, err = run(cmd, FAKE_REF="main")
            check(f"release-gate (#1569): {label} is judged by the commit it writes", (rc == 0) == ok and (ok or rc == 2), f"rc={rc} {err[:240]!r}")
        # (5) A release is resolved the way GitHub resolves it: a tag that exists on the REMOTE wins over --target.
        for label, cmd, ok in (
            ("an existing remote tag at the certified commit, --target the uncertified main", "gh release create v0.9 --target main", True),
            ("an existing remote tag at an UNcertified commit, --target the certified dev", "gh release create v0.8 --target dev", False),
            ("an existing remote tag, no target", "gh release create v0.8", False),
            ("a new tag with --target main (uncertified)", "gh release create v2.0 --target main", False),
            ("a new tag with --target dev (certified)", "gh release create v2.0 --target dev", True),
        ):
            rc, err = run(cmd)
            check(f"release-gate (#1569): {label} is judged by the commit GitHub will use", (rc == 0) == ok and (ok or rc == 2), f"rc={rc} {err[:240]!r}")
        rc, err = run("gh release edit v0.8 --draft=false", FAKE_RELVIEW="dev")
        check("release-gate (#1569): a draft whose tag already exists remotely is judged by the TAG, not its recorded target",
              rc == 2 and hot[:12] in err, f"rc={rc} {err[:240]!r}")
        # (6) The command the SHELL runs is the command that was classified.
        for label, cmd in (
            ("ANSI-C command word", "$'gh' api -X PUT repos/o/r/pulls/7/merge"),
            ("ANSI-C hex command word", "$'\\x67\\x68' pr merge 7"),
            ("ANSI-C method", "gh api -X $'PUT' repos/o/r/pulls/7/merge"),
            ("ANSI-C in the middle of a word (no `gh` left in the text)", "g$'h' release create v2.0 --target main"),
            ("locale string", 'gh $"api" -X PUT repos/o/r/pulls/7/merge'),
            ("a variable command word", "$g release create v2.0 --target main"),
            ("a brace-built command word", "g{h,} release create v2.0 --target main"),
            ("$IFS for the spaces", "gh${IFS}release${IFS}create${IFS}v2.0${IFS}--target${IFS}main"),
            ("a short-flag cluster hiding the method", "gh api -iXPUT repos/o/r/pulls/7/merge"),
            ("a line continuation", "gh api -X PUT \\\n repos/o/r/pulls/7/merge"),
        ):
            rc, err = run(cmd, FAKE_PRVIEW=f"main {hot}")
            check(f"release-gate (#1569): {label} is read the way the shell reads it (blocked)", rc == 2, f"rc={rc} {err[:240]!r}")
        for cmd in ("echo $HOME", "git commit -m $'a\\nb'", "ls $(pwd)", "x=1; echo $x", "echo {a,b}"):
            rc, err = run(cmd)
            check(f"release-gate (#1569): CONTROL: `{cmd}` has an expansion but no effect, and passes", rc == 0, f"rc={rc} {err[:240]!r}")

        # (7) FAIL CLOSED BY CONSTRUCTION: a gh or git nobody listed is not "no effect". Over-blocking a safe
        # command in a gated repository is the price; letting an unlisted spelling merge is what it prevents.
        for label, cmd in (
            ("an unknown git verb (an alias)", "git ci -m x"),
            ("a git -c that can redirect a push", "git -c url.https://x/.insteadOf=https://github.com/o/ push origin feature/x"),
            ("an unknown git global option", "git --weird status"),
            ("a git verb from a variable", "git $V push origin feature/x"),
            ("git remote set-url", "git remote set-url origin https://github.com/x/y"),
            ("a plumbing push", "git send-pack origin main"),
            ("gh workflow run", "gh workflow run release.yml"),
            ("gh pr update-branch", "gh pr update-branch 7"),
            ("an unknown gh subcommand", "gh foo bar"),
            ("a gh subcommand from a variable", "gh $x pr merge 7"),
            ("a gh api write to dispatches", "gh api -X POST repos/o/r/dispatches -f event_type=release"),
            ("a gh api update-branch", "gh api -X PUT repos/o/r/pulls/7/update-branch"),
            ("a GraphQL mutation nobody listed", "gh api graphql -f query='mutation { mergeBranch(input:{}) { x } }'"),
            ("a function defined before use", "foo() { gh pr merge 7; }; foo"),
            ("an alias defined before use", "alias gm='git merge'; gm hotfix"),
            ("find -exec", "find . -name x -exec gh pr update-branch 7 ;"),
            ("git pull on main", "git pull"),
        ):
            sh("checkout", "-q", "main") if label == "git pull on main" else None
            rc, err = run(cmd, FAKE_PRVIEW=f"main {stamped}")
            if label == "git pull on main":
                sh("checkout", "-q", "feature/work")
            check(f"release-gate (#1569): {label} cannot be shown to be harmless, and is blocked", rc == 2, f"rc={rc} {err[:240]!r}")
        for cmd in ("git status", "git log --oneline -3", "git fetch origin", "git add -A", "git commit -m 'x y'", "git push -u origin feature/x",
                    "git checkout -b feature/y", "git -c user.name=x -c user.email=y commit -m z", "git config --get remote.origin.url",
                    "git remote -v", "gh pr view 7", "gh pr list", "gh pr create -t x -b y", "gh pr checks 7", "gh issue create -t x",
                    "gh run list", "gh release list", "gh api repos/o/r/pulls/7", "gh api -X POST repos/o/r/issues/1/comments -f body=hi",
                    "echo gh pr merge 7", "which gh", "grep -r git .", "python3 x.py git"):
            rc, err = run(cmd)
            check(f"release-gate (#1569): CONTROL: the listed-safe `{cmd}` passes", rc == 0, f"rc={rc} {err[:240]!r}")
        rc, err = run("gh workflow run release.yml", QA_ALLOW_MAIN="1")
        check("release-gate (#1569): ... and the audited override (the HOOK's environment) still allows an unlisted command", rc == 0, f"rc={rc} {err[:240]!r}")
        # (8) AUTHORIZATION: the override comes from the hook's own environment, never from the command text.
        for cmd in ("QA_ALLOW_MAIN=1 gh release create v2.0 --target main", "env QA_ALLOW_MAIN=1 gh pr merge 7",
                    "export QA_ALLOW_MAIN=1; git push origin hotfix:main", "QA_ALLOW_MAIN=1 git push origin hotfix:main",
                    "bash -c 'QA_ALLOW_MAIN=1 gh pr merge 7'", "QA_ALLOW_MAIN=1; gh pr merge 7"):
            rc, err = run(cmd, FAKE_PRVIEW=f"main {hot}")
            check(f"release-gate (#1569): `{cmd}` does not set the override (it is not the hook's environment): blocked", rc == 2, f"rc={rc} {err[:240]!r}")
        for cmd in ("gh release create v2.0 --target main", "git push origin hotfix:main"):
            rc, err = run(cmd, QA_ALLOW_MAIN="1")
            check(f"release-gate (#1569): `{cmd}` with QA_ALLOW_MAIN=1 in the HOOK's environment is allowed (audited)", rc == 0, f"rc={rc} {err[:240]!r}")
        # The marketplace exemption needs the marketplace's identity, even after a cd into a directory that has the file.
        spoof = Path(td) / "spoof"
        _git_repo(spoof)
        _run([*g, "checkout", "-q", "-B", "main"], cwd=spoof, check=True, capture_output=True)
        (spoof / ".claude-plugin").mkdir()
        (spoof / ".claude-plugin" / "marketplace.json").write_text('{"name":"x","plugins":[]}', encoding="utf-8")
        _run([*g, "remote", "add", "origin", "https://github.com/acme/app.git"], cwd=spoof, check=True, capture_output=True)
        _run([*g, "branch", "dev"], cwd=spoof, check=True, capture_output=True)
        rc, err = run(f"cd {spoof} && git merge dev")
        check("release-gate (#1569): a directory with a marketplace.json but another repository's origin is not exempt", rc == 2, f"rc={rc} {err[:240]!r}")
        # (9) `git push origin main` ships the LOCAL main: dev's stamp must not stand in for it.
        rc, err = run("git push origin main")
        check("release-gate (#1569): `git push origin main` is judged by the LOCAL main (uncertified), though dev is certified",
              rc == 2 and hot[:12] in err, f"rc={rc} {err[:240]!r}")
        rc, err = run("git push --all origin")
        check("release-gate (#1569): `git push --all` judges main too", rc == 2 and hot[:12] in err, f"rc={rc} {err[:240]!r}")
        sh("branch", "-f", "main", stamped)
        rc, err = run("git push origin main")
        check("release-gate (#1569): CONTROL: ... and permitted once local main IS the certified commit", rc == 0, f"rc={rc} {err[:240]!r}")
        sh("branch", "-f", "main", hot)

# ---- ci-verdict-hint.sh (#1173) -----------------------------------------------------------------
# An ADVISORY, so every fixture asserts exit 0 -- a hint that could fail the tool call would be a gate
# nobody asked for. What varies is whether it SPEAKS, and on which event.

        # (10) #1591: a repository other than this checkout's is held to the SAME standard as this one. The
        # stamp is not enough: a schema-2 stamp must name a passing first-boot walkthrough and authorization
        # sweep (#1428), judged from the evidence AS COMMITTED in that repository, and the commit may carry
        # that evidence beyond the stamp itself. The foreign repository's objects are fetched from a local
        # bare repository, so nothing here touches the network.
        fw = Path(td) / "fw"
        _git_repo(fw)
        fsh = lambda *a, **kw: _run([*g, *a], cwd=fw, check=True, capture_output=True, text=True, **kw).stdout.strip()
        fb_rows = ("Step,Width,Actor,URL,Action,Expected,Actual,Status,Notes,Screenshot,Also,Issue,Env\n"
                   "1.1,1280,root,/login,Sign in,In,In,Pass,,,,,empty db\n"
                   "1.2,390,root,/login,Sign in,In,In,Pass,,,,,empty db\n")
        az_head = "action,location,actor_role,target_role,guard,verdict,evidence,issue\n"
        az_good = az_head + "demote,app/models/user.rb:40,it,root,root? refusal,GUARDED,,\n"
        az_hole = az_good + "demote,app/controllers/staff.rb:88,it,root,,HOLE,forged PATCH,#1\n"
        (fw / "app.rb").write_text("v1\n", encoding="utf-8")
        fsh("add", "app.rb"); fsh("commit", "-q", "-m", "app", env=old)
        tested_f = fsh("rev-parse", "HEAD")
        fsh("push", "-q", str(forkbare), f"{tested_f}:refs/heads/main")      # the last PUBLISHED release
        ev_files = ["qa/manual-tests/first-boot-v1/pages.csv", "qa/manual-tests/authz-v1/sweep.csv"]

        def scenario(name: str, stamp: dict, authz: str, versions: tuple = ("v1",)) -> tuple:
            fsh("checkout", "-q", "-B", name, tested_f)
            for v in versions:
                (fw / f"qa/manual-tests/first-boot-{v}").mkdir(parents=True, exist_ok=True)
                (fw / f"qa/manual-tests/authz-{v}").mkdir(parents=True, exist_ok=True)
                (fw / f"qa/manual-tests/first-boot-{v}/pages.csv").write_text(fb_rows, encoding="utf-8")
                (fw / f"qa/manual-tests/authz-{v}/sweep.csv").write_text(authz, encoding="utf-8")
            (fw / "qa").mkdir(exist_ok=True)
            (fw / "qa" / "CERTIFICATION").write_text(json.dumps(stamp), encoding="utf-8")
            fsh("add", "qa"); fsh("commit", "-q", "-m", name)
            fsh("push", "-q", "-f", str(forkbare), f"HEAD:refs/heads/{name}")
            return fsh("rev-parse", "HEAD"), stamp

        base_stamp = {"sha": tested_f, "date": "2026-10-01", "verdict": "PASS", "report": "r.md"}
        s2 = {**base_stamp, "schema": 2, "version": "v1", "first_boot": "qa/manual-tests/first-boot-v1",
              "authz": "qa/manual-tests/authz-v1/sweep.csv"}

        def foreign(sha: str, stamp: dict, delta: list, cmd: str = "gh pr merge 7 -R other/fork",
                    repo_name: str = "other/fork", status: str = "ahead", **more) -> tuple:
            f = Path(td) / f"stamp-{sha[:10]}.json"
            f.write_text(json.dumps(stamp), encoding="utf-8")
            return run(_pin(cmd, sha), FAKE_PRVIEW=f"main {sha}", FAKE_PRREPO=repo_name, FAKE_COMMIT=sha, FAKE_STAMP_REF=sha,
                       FAKE_STAMP_FILE=str(f), FAKE_COMPARE=status + "\n" + "\n".join(["qa/CERTIFICATION", *delta]), **more)

        sha_bare, st = scenario("bare", base_stamp, az_good, ())
        rc, err = foreign(sha_bare, st, [])
        check("release-gate (#1591): ANOTHER repository's bare PASS stamp, committed after the #1428 cutoff, is denied (no schema)",
              rc == 2 and "schema" in err, f"rc={rc} {err[:300]!r}")
        sha_good, st = scenario("good", s2, az_good)
        rc, err = foreign(sha_good, st, ev_files)
        check("release-gate (#1591): ANOTHER repository's schema-2 stamp, whose commit carries its passing evidence, is permitted",
              rc == 0 and "other/fork" in err, f"rc={rc} {err[:300]!r}")
        rc, err = foreign(sha_good, st, [*ev_files, "app.rb"])
        check("release-gate (#1591): ... and a code change riding with that evidence is denied, naming it",
              rc == 2 and "app.rb" in err, f"rc={rc} {err[:300]!r}")
        rc, err = foreign(sha_good, st, [], cmd="gh release create v1 -R other/fork --target main")
        check("release-gate (#1591): ... and a release of that commit is permitted too", rc == 0, f"rc={rc} {err[:300]!r}")
        sha_hole, st = scenario("hole", s2, az_hole)
        rc, err = foreign(sha_hole, st, ev_files)
        check("release-gate (#1591): ANOTHER repository's committed HOLE in the sweep is denied, naming the layer",
              rc == 2 and "#1428" in err and "HOLE" in err, f"rc={rc} {err[:300]!r}")
        rc, err = foreign(sha_hole, st, ev_files, cmd="gh release create v1 -R other/fork --target main")
        check("release-gate (#1591): ... and a release of that commit is denied too", rc == 2 and "HOLE" in err, f"rc={rc} {err[:300]!r}")
        sha_twin, st = scenario("twin", s2, az_good, ("v0", "v1"))
        rc, err = foreign(sha_twin, st, ev_files + ["qa/manual-tests/first-boot-v0/pages.csv", "qa/manual-tests/authz-v0/sweep.csv"])
        check("release-gate (#1591): ANOTHER repository's evidence copied from another release is denied (byte-identical)",
              rc == 2 and "byte-identical" in err, f"rc={rc} {err[:300]!r}")
        sha_out, st = scenario("outside", {**s2, "first_boot": "app"}, az_good)
        rc, err = foreign(sha_out, st, ev_files)
        check("release-gate (#1591): ANOTHER repository's stamp naming evidence outside qa/manual-tests/ is denied",
              rc == 2 and "qa/manual-tests/" in err, f"rc={rc} {err[:300]!r}")
        rc, err = foreign(sha_good, {**s2, "verdict": "FAIL"}, ev_files)
        check("release-gate (#1591): ANOTHER repository's stamp whose verdict is not PASS is denied", rc == 2 and "not PASS" in err,
              f"rc={rc} {err[:300]!r}")
        for status in ("diverged", "behind"):
            rc, err = foreign(sha_good, s2, ev_files, status=status)
            check(f"release-gate (#1591): ANOTHER repository's certified commit that is {status} of the judged one is denied (not an ancestor)",
                  rc == 2 and "not an ancestor" in err, f"rc={rc} {err[:300]!r}")
        # THE HOOK'S OWN TIME. A PreToolUse hook that outlives its timeout (15 s) does not deny: the command goes through.
        # A fetch that stalls past that must be stopped by the helper's budget, and a hook that has spent its time on the
        # API must not start one. A `git` that sleeps on `fetch` (20 s, longer than the hook may take) stands in for a slow remote.
        gitbin = Path(td) / "gitbin"
        gitbin.mkdir()
        real_git = shutil.which("git")
        (gitbin / "git").write_text(f'#!/bin/sh\ncase " $* " in *" fetch "*) sleep 20 ;; esac\nexec {real_git} "$@"\n', encoding="utf-8")
        (gitbin / "git").chmod(0o755)
        started = time.monotonic()
        # (RAILS_FLOW_HOOK_DEADLINE=13, the gate's own largest deadline, so it is the helper's budget that speaks first, not #1602's.)
        rc, err = foreign(sha_good, s2, ev_files, RAILS_FLOW_HOOK_DEADLINE="13",
                          PATH=f"{gitbin}{os.pathsep}{Path(td) / 'bin'}{os.pathsep}{os.environ['PATH']}")
        took = time.monotonic() - started
        check("release-gate (#1591): a fetch that stalls past the hook's own 15 s is stopped by the budget and DENIED, inside the timeout",
              rc == 2 and "time budget" in err and took < 15, f"rc={rc} took={took:.1f}s {err[:240]!r}")
        # A `gh api` that stalls is cut short by `bounded` (4 s) and read as a failure: denied, well inside the 15 s.
        started = time.monotonic()
        rc, err = foreign(sha_good, s2, ev_files, FAKE_SLEEP="30")
        took = time.monotonic() - started
        # By ITS OWN message: with the stall left unbounded, #1602's deadline would cut it short too and the denial inside 15 s
        # would still hold, so only "could not be read" tells this bound from the deadline's.
        check("release-gate (#1591): a gh that stalls is cut short and the command DENIED, inside the hook's timeout",
              rc == 2 and took < 15 and "could not be read" in err, f"rc={rc} took={took:.1f}s {err[:240]!r}")
        # The compare call stalls alone (the stamp read is fast), so only ITS bound can stop it.
        started = time.monotonic()
        rc, err = foreign(sha_good, s2, ev_files, FAKE_SLEEP_COMPARE="30")
        took = time.monotonic() - started
        check("release-gate (#1591): a compare call that stalls on its own is cut short and the command DENIED, inside the hook's timeout",
              rc == 2 and took < 15 and "could not be compared" in err, f"rc={rc} took={took:.1f}s {err[:240]!r}")
        # Too little time left for the evidence judge: a gate whose deadline leaves under 3 s after the 2 s margin does not START
        # the judge. A deadline of 4 s makes that deterministic (the API calls are instant here), where sleeping through earlier
        # calls made it depend on how fast the machine was (it passed locally and was permitted on CI).
        rc, err = foreign(sha_good, s2, ev_files, RAILS_FLOW_HOOK_DEADLINE="4")
        check("release-gate (#1591): a hook with too little time left for the evidence judge does not start it, and DENIES",
              rc == 2 and "no time left" in err, f"rc={rc} {err[:240]!r}")
        rc, err = foreign(sha_good, s2, ev_files, cmd="gh pr merge 7 -R gone/repo", repo_name="gone/repo")
        check("release-gate (#1591): a repository whose objects cannot be fetched is denied, naming the layer and the repository",
              rc == 2 and "#1428" in err and "gone/repo" in err, f"rc={rc} {err[:300]!r}")


def ci_verdict_hint_fixtures() -> None:
    # The PLUGIN root, two levels above hooks/scripts -- `HOOKS.parent` is hooks/, and pointing there
    # made every fixture silent for the wrong reason until the positive one said so.
    root = str(HOOKS.parents[1])
    fail_rows = "test\tfail\t8s\thttps://x/runs/1/job/1\t\nlint\tfail\t9s\thttps://x/runs/1/job/2\t\n"
    pass_rows = "test\tpass\t8s\thttps://x/runs/2/job/1\t\n"
    # THE CASE IT EXISTS FOR: plain `gh pr checks` exits 1 on a failing check, so the harness sends
    # PostToolUseFailure with the text in `error`, not PostToolUse with `tool_response`.
    failed = json.dumps({"hook_event_name": "PostToolUseFailure", "tool_name": "Bash",
                         "tool_input": {"command": "gh pr checks 580"},
                         "error": "Exit code 1\n" + fail_rows, "is_interrupt": False})
    passed = json.dumps({"hook_event_name": "PostToolUse", "tool_name": "Bash",
                         "tool_input": {"command": "gh pr checks 1172"},
                         "tool_response": {"stdout": pass_rows, "stderr": "", "exit_code": 0}})
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td)
        code, out = run_hook("ci-verdict-hint.sh", cwd=proj, stdin=failed,
                             env_extra={"CLAUDE_PLUGIN_ROOT": root})
        check("ci-verdict-hint: a failing `gh pr checks` (PostToolUseFailure) emits additionalContext",
              code == 0 and '"additionalContext"' in out and "ci_verdict.py" in out,
              f"exit {code}: {out.strip()[:140]!r}")
        check("ci-verdict-hint: ...under the PostToolUseFailure event name",
              '"hookEventName": "PostToolUseFailure"' in out, out.strip()[:140])
        code, out = run_hook("ci-verdict-hint.sh", cwd=proj, stdin=passed,
                             env_extra={"CLAUDE_PLUGIN_ROOT": root})
        check("ci-verdict-hint: an all-passing `gh pr checks` is silent and exits 0",
              code == 0 and out.strip() == "", f"exit {code}: {out.strip()[:120]!r}")
        # #825's environment: the harness sets the variable; a person driving the script does not.
        code, out = run_hook("ci-verdict-hint.sh", cwd=proj, stdin=failed, unset=("CLAUDE_PLUGIN_ROOT",))
        check("ci-verdict-hint: with CLAUDE_PLUGIN_ROOT unset it exits 0 silently, not `unbound variable`",
              code == 0 and "unbound" not in out and out.strip() == "", f"exit {code}: {out.strip()[:120]!r}")
        # No python3 on PATH: only a `bash` survives, so `command -v python3` must miss and it must
        # fail OPEN. Proved by a PATH that genuinely lacks it, not by assuming the guard works.
        bare = proj / "bare-bin"
        bare.mkdir()
        (bare / "bash").symlink_to(shutil.which("bash"))
        done = _run([str(bare / "bash"), str(HOOKS / "ci-verdict-hint.sh")], cwd=proj,
                              input=failed, capture_output=True, text=True, timeout=60,
                              env={"PATH": str(bare), "CLAUDE_PLUGIN_ROOT": root, "HOME": td})
        check("ci-verdict-hint: with no python3 on PATH it exits 0 and says nothing",
              done.returncode == 0 and (done.stdout + done.stderr).strip() == "",
              f"exit {done.returncode}: {(done.stdout + done.stderr).strip()[:120]!r}")
        # Garbage in must be silence out -- an advisory that errors takes the tool call down with it.
        code, out = run_hook("ci-verdict-hint.sh", cwd=proj, stdin="not json",
                             env_extra={"CLAUDE_PLUGIN_ROOT": root})
        check("ci-verdict-hint: an unreadable payload exits 0 silently",
              code == 0 and out.strip() == "", f"exit {code}: {out.strip()[:120]!r}")


def session_end_fixtures() -> None:
    """#1582 slice C: session-end.sh reaps the session's own stopped orphans, fails open, and never blocks.

    The reaper's own fixtures (the decoy, the other session, the running orphan, the child with a parent) live in
    `session_reaper.py --selftest`; this proves the HOOK reaches it with the payload and stays silent and exit 0 when
    it cannot."""
    root = str(HOOKS.parents[1])
    sid = str(uuid.uuid4())      # unique per run: guards run in parallel (#1646 R2)
    leaf = ("import os, signal, sys, time\nopen(sys.argv[1], 'w').write(str(os.getpid()))\n"
            "os.kill(os.getpid(), signal.SIGSTOP)\ntime.sleep(120)\n")
    parent = ("import subprocess, sys\nN = subprocess.DEVNULL\n"
              f"subprocess.Popen([sys.executable, '-c', {leaf!r}, sys.argv[1]], start_new_session=True, stdin=N, stdout=N, stderr=N)\n")
    with tempfile.TemporaryDirectory() as td:
        proj, pidfile = Path(td), Path(td) / "leaf.pid"
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"}
        env["CLAUDE_CODE_SESSION_ID"] = sid
        _run([sys.executable, "-c", parent, str(pidfile)], cwd=proj, env=env, timeout=30)
        pid = 0
        for _ in range(100):
            if pidfile.exists() and pidfile.read_text().strip():
                pid = int(pidfile.read_text())
                if _run(["ps", "-o", "stat=", "-p", str(pid)], cwd=proj, capture_output=True, text=True,
                        timeout=10).stdout.strip().startswith("T"):
                    break
            time.sleep(0.05)

        def alive() -> bool:
            out = _run(["ps", "-o", "stat=", "-p", str(pid)], cwd=proj, capture_output=True, text=True,
                       timeout=10).stdout.strip()
            return bool(out) and not out.startswith("Z")

        try:
            check("session-end: the fixture is a stopped orphan before the hook runs", pid > 0 and alive(), f"pid {pid}")
            code, out = run_hook("session-end.sh", cwd=proj, stdin=json.dumps({"session_id": "ffffffff-0000-0000-0000-000000000000"}),
                                 env_extra={"CLAUDE_PLUGIN_ROOT": root})
            check("session-end: another session's id reaps nothing and says nothing",
                  code == 0 and out.strip() == "" and alive(), f"exit {code}: {out.strip()[:120]!r}, alive {alive()}")
            code, out = run_hook("session-end.sh", cwd=proj, stdin=json.dumps({"session_id": sid, "hook_event_name": "SessionEnd"}),
                                 env_extra={"CLAUDE_PLUGIN_ROOT": root})
            time.sleep(0.3)
            check("session-end: this session's stopped orphan is reaped and the hook exits 0",
                  code == 0 and not alive(), f"exit {code}: {out.strip()[:120]!r}, alive {alive()}")
        finally:
            if pid > 0:
                for sig in (signal.SIGCONT, signal.SIGKILL):
                    try:
                        os.kill(pid, sig)
                    except (ProcessLookupError, PermissionError):
                        pass
        # `unset` and `env_extra` must not meet: run_hook unsets first and then adds env_extra back.
        for label, kwargs in (("an unreadable payload", {"stdin": "not json", "env_extra": {"CLAUDE_PLUGIN_ROOT": root}}),
                              ("CLAUDE_PLUGIN_ROOT unset", {"stdin": json.dumps({"session_id": sid}), "unset": ("CLAUDE_PLUGIN_ROOT",)})):
            code, out = run_hook("session-end.sh", cwd=proj, **kwargs)
            check(f"session-end: {label} exits 0 silently", code == 0 and out.strip() == "", f"exit {code}: {out.strip()[:120]!r}")


def timeout_fixtures() -> None:
    """#1469: a subprocess that times out fails ITS fixture by name; the suite never crashes.

    Cheap on purpose -- this file is the selftest of every hook guard, so a costly proof would make
    the very flake it fixes worse. The wrapper is driven directly on a sleep that outruns a 0.2s
    bound, and the file is checked to route every subprocess call through it.
    """
    global _EXPECTING_TIMEOUT
    saved = os.environ.get("HOOK_GATES_TIMEOUT")
    os.environ["HOOK_GATES_TIMEOUT"] = "0.2"
    _EXPECTING_TIMEOUT = True
    marker = f"sleep 29.{os.getpid() % 1000:03d}"   # unique, so no other process can be counted
    import time
    began = time.monotonic()
    try:
        r = _run(["bash", "-c", f"{marker} & {marker}; wait"], capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        r = None
    finally:
        _EXPECTING_TIMEOUT = False
        if saved is None:
            os.environ.pop("HOOK_GATES_TIMEOUT", None)
        else:
            os.environ["HOOK_GATES_TIMEOUT"] = saved
    took = time.monotonic() - began
    check("a timed-out hook fixture fails by name and the suite still finishes (no crash)",
          r is not None and r.returncode == 124 and "TIMEOUT after" in r.stderr, f"{r}")
    # THE MECHANISM OF THE 30-MINUTE HANG: a stub the timeout did not kill keeps the output pipe open,
    # so reading the hook's output waits for the stub to exit on its own. Killing the whole group
    # returns at once; anything less waits out the 29s sleep.
    # 3s, not 10: the group kill returns in ~0.2s, while anything that leaves a stub alive waits out
    # the 5s bound on the read after the kill -- so this still tells the two apart.
    check("...and returns promptly, because nothing it started still holds the output pipe",
          took < 3, f"took {took:.1f}s")
    left = _run(["pgrep", "-f", marker], capture_output=True, text=True).stdout.split()
    check("...and the timeout kills the hook's whole process group, leaving no orphaned stub",
          left == [], f"{len(left)} process(es) left: {left}")
    for pid in left:
        try:
            os.kill(int(pid), 9)
        except (ProcessLookupError, ValueError):
            pass
    # #1657: the release gate's OWN deadline also exits 2, so a release-gate fixture reads it through `gate_exit`: a refusal under test is 2, a deadline is 124.
    check("a gate_exit of the gate's deadline message is 124, a real refusal stays 2, an allow stays 0",
          gate_exit(2, b"BLOCKED by qa-flow release gate: the gate took longer than 13s, and this command looks like a promotion") == 124
          and gate_exit(2, b"BLOCKED by qa-flow release gate: no qa/CERTIFICATION is committed") == 2 and gate_exit(0, b"") == 0, "mapping wrong")
    with tempfile.TemporaryDirectory() as dltd:
        slow = Path(dltd) / "awk"
        slow.write_text("#!/bin/sh\nsleep 6\n", encoding="utf-8"); slow.chmod(0o755)
        denv = {k: v for k, v in os.environ.items() if k not in ("QA_ALLOW_MAIN", "RAILS_FLOW_LANE")}
        denv.update(PATH=f"{slow.parent}{os.pathsep}{denv['PATH']}", RAILS_FLOW_HOOK_DEADLINE="2", CLAUDE_PLUGIN_ROOT=str(QA_HOOK.parents[2]))
        began = time.monotonic()
        done = _run(["bash", str(QA_HOOK)], cwd=dltd, env=denv, capture_output=True, timeout=60, input=json.dumps({"tool_input": {"command": "git push origin main"}}).encode())
        check("release-gate (#1657): a gate that hits its own deadline reads as 124 to the fixtures, not as the refusal under test",
              done.returncode == 2 and b"took longer than" in done.stderr and gate_exit(done.returncode, done.stderr) == 124 and time.monotonic() - began < 30,
              f"exit {done.returncode}, {done.stderr[:120]!r}")
    # An UNEXPECTED timeout is a recorded failure (a setup step that times out must not pass).
    before = len(FAILURES)
    os.environ["HOOK_GATES_TIMEOUT"] = "0.2"
    try:
        _run([sys.executable, "-c", "import time; time.sleep(3)"], capture_output=True, text=True)
    except subprocess.TimeoutExpired:
        pass                         # a crash here is the defect the check below names
    finally:
        if saved is None:
            os.environ.pop("HOOK_GATES_TIMEOUT", None)
        else:
            os.environ["HOOK_GATES_TIMEOUT"] = saved
    recorded = FAILURES[before:]
    del FAILURES[before:]
    check("an UNEXPECTED timeout is recorded as a failure, never passed silently",
          len(recorded) == 1 and "TIMEOUT after" in recorded[0], f"{recorded}")
    # THE BUDGET SCALES WITH THE MACHINE (#1638): pure arithmetic first, then the wiring.
    check("an idle machine gets the floor, and a fixture's own larger bound is kept",
          hook_limit(0, 1.0) == 180.0 and hook_limit(600, 1.0) == 600.0 and hook_limit(60, 1.0) == 180.0)
    check("a slower machine gets proportionally more, so a loaded machine is not read as a hung hook",
          hook_limit(0, 3.0) == 540.0 and hook_limit(100, 2.5) == 450.0)
    check("a machine measured faster than idle never shrinks the budget", hook_limit(0, 0.3) == 180.0)
    check("the budget stops at the cap, so a real hang under load still ends", hook_limit(0, 1000.0) == HOOK_BUDGET_CAP)
    check("a fixture that asked for more than the cap keeps what it asked for", hook_limit(3600, 5.0) == 3600.0)
    probe = {"slowdown": 1.0, "at": None}
    saved_cal = dict(_CALIBRATION)
    try:
        ticks = iter([0.0, 5.0, 31.0])
        measured = []
        _CALIBRATION.update(probe)
        s1 = machine_slowdown(measure=lambda: (measured.append(1), 0.6)[1], now=lambda: next(ticks))
        s2 = machine_slowdown(measure=lambda: (measured.append(1), 0.06)[1], now=lambda: next(ticks))
        s3 = machine_slowdown(measure=lambda: (measured.append(1), 0.06)[1], now=lambda: next(ticks))
    finally:
        _CALIBRATION.update(saved_cal)
    check("the machine's slowdown is the calibration over its idle figure", abs(s1 - 10.0) < 1e-9, f"{s1}")
    check("...measured once per refresh window, not once per subprocess", s2 == s1 and len(measured) == 2, f"{s2} {measured}")
    check("...and again after the window, so a machine that calmed down gets its floor back", abs(s3 - 1.0) < 1e-9, f"{s3}")
    real_call = subprocess.call
    seen_timeouts: list = []

    def _stalled(*a, **k):
        seen_timeouts.append(k.get("timeout"))
        raise subprocess.TimeoutExpired("calibration", 60)
    subprocess.call = _stalled
    try:
        stalled = _calibrate()
    finally:
        subprocess.call = real_call
    check("a calibration that cannot finish reads as the heaviest load, not as idle",
          abs(stalled / CALIBRATION_IDLE - HOOK_BUDGET_CAP / HOOK_BUDGET_FLOOR) < 1e-9, f"{stalled}")
    check("the calibration is itself bounded: every command it starts has a timeout",
          seen_timeouts and all(isinstance(t, (int, float)) and 0 < t <= CALIBRATION_TIMEOUT for t in seen_timeouts), f"{seen_timeouts}")
    check("one outlier among calm samples does not set the budget (the median of three)",
          _calibrate(sample=iter([0.06, 0.5, 0.06]).__next__) == 0.06 and _calibrate(sample=iter([0.5, 0.06, 0.06]).__next__) == 0.06)
    check("...but a machine that is slow in most samples is read as slow",
          _calibrate(sample=iter([0.5, 0.06, 0.5]).__next__) == 0.5)
    check("a calibration that runs reports a plausible, positive time", 0 < _calibrate() < 60)
    src = Path(__file__).read_text(encoding="utf-8")
    check("every subprocess's bound goes through hook_limit, never a bare number",
          src.count("else hook_limit(requested, " + "machine_slowdown())") == 1)
    raw = src.count("subprocess" + ".run(")
    check("every subprocess in this suite goes through the no-crash wrapper", raw == 0,
          f"{raw} direct subprocess.run call(s); every one must go through _run")


# One fixture group per hook. `--only` runs a subset (#1497): twelve mutation guards use this file
# as their selftest, each mutating ONE hook, and every mutant re-ran all ten groups -- about 70% of
# the mutation-coverage budget. A guard now names the groups that drive its hook; the doctor's
# `hook gates` gate and the harness's own guard still run every group.
# ---- guard-worktree.sh (#1581) -------------------------------------------------------------------
def _worktree_kit() -> types.SimpleNamespace:
    """The helpers every worktree fixture group shares (#1581): a throwaway repository with a `dev` integration branch,
    worktrees, the coordinator recording a lane, and the hook run on a PreToolUse payload."""
    coord = HOOKS / "lib" / "coordination.py"

    def git(cwd, *a):
        return _run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=cwd, check=True,
                    capture_output=True, text=True)

    def new_repo(td) -> Path:
        repo = Path(td) / "repo"
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        git(repo, "commit", "-q", "--allow-empty", "-m", "init")
        git(repo, "branch", "dev")          # the integration branch
        return repo

    def add_wt(repo: Path, name: str, branch: str, *, unmerged: bool = True) -> Path:
        path = repo.parent / name
        git(repo, "worktree", "add", "-q", "-b", branch, str(path), "dev")
        if unmerged:
            git(path, "commit", "-q", "--allow-empty", "-m", "wip")
        return path.resolve()

    def lane(repo: Path, owner: str, path: Path, branch: str) -> None:
        """The COORDINATOR records the lane: hooks only read the record."""
        for args in (["claim"], ["assign", "--path", str(path), "--branch", branch, "--owner", owner]):
            _run([sys.executable, str(coord), args[0], "--session-id", "COORD", *args[1:], "--cwd", str(repo)],
                 capture_output=True)

    def payload(repo: Path, cmd: str, sid: str | None) -> str:
        d = {"tool_name": "Bash", "hook_event_name": "PreToolUse", "tool_input": {"command": cmd}, "cwd": str(repo)}
        if sid is not None:
            d["session_id"] = sid
        return json.dumps(d)

    def guard(repo: Path, cmd: str, sid: str | None = "SESS-A", **kw) -> tuple[int, str]:
        return run_hook("guard-worktree.sh", cwd=repo, stdin=payload(repo, cmd, sid), unset=("CLAUDE_PROJECT_DIR",), **kw)

    def denied(label: str, res: tuple[int, str], *needles: str) -> None:
        code, out = res
        check(label, code == 2 and "BLOCKED by rails-flow worktree guard" in out, f"exit {code}: {out.strip()[:200]!r}")
        for n in needles:
            # The temp directory differs per run, and `--match` compares the survey's labels with the run's.
            # Hoisted: a backslash inside an f-string expression is a SyntaxError before Python 3.12 (#1597).
            shown = re.sub(r'/\S*?/tmp\w{8}(?=/|$)', '<tmp>', n)
            check(f"...and the message names {shown!r}", n in out, out.strip()[:300])

    def allowed(label: str, res: tuple[int, str]) -> None:
        check(label, res[0] == 0, f"exit {res[0]}: {res[1].strip()[:200]!r}")

    return types.SimpleNamespace(coord=coord, git=git, new_repo=new_repo, add_wt=add_wt, lane=lane, payload=payload, guard=guard, denied=denied, allowed=allowed)


def guard_worktree_fixtures() -> None:
    """The RULES: one issue at a time, and no duplicate worktree for a branch or an issue (#1581)."""
    k = _worktree_kit()
    coord, git, new_repo, add_wt, lane, payload, guard, denied, allowed = (k.coord, k.git, k.new_repo, k.add_wt, k.lane, k.payload, k.guard, k.denied, k.allowed)
    _ = (coord, git, new_repo, add_wt, lane, payload, guard, denied, allowed)     # a group uses some, not all
    # 4. A fresh session that owns nothing, in a repository with no coordination record.
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(td)
        allowed("guard-worktree: a session that owns nothing may add a worktree", guard(repo, "git worktree add ../fresh -b feature/fresh dev"))

    # 1. This session owns an unmerged worktree: a second one is DENIED.
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(td)
        wt = add_wt(repo, "a", "feature/a")
        lane(repo, "SESS-A", wt, "feature/a")
        denied("guard-worktree: a session that owns an UNMERGED worktree may not add another",
               guard(repo, "git worktree add ../b -b feature/b dev"), str(wt), "feature/a", "hand the new task back")
        denied("guard-worktree: ...also through `cd x && git worktree add`", guard(repo, f"cd {td} && git worktree add ../b -b feature/b dev"))
        denied("guard-worktree: ...also through `git -C repo worktree add`", guard(repo, f"git -C {repo} worktree add ../b -b feature/b dev"))
        denied("guard-worktree: ...also after an env prefix", guard(repo, "FOO=1 git worktree add ../b -b feature/b dev"))
        denied("guard-worktree: a worktree add INSIDE `bash -c '...'` is judged, and names the lane it collides with",
               guard(repo, "bash -c 'git worktree add ../b -b feature/b dev'"), str(wt))
        denied("guard-worktree: ...inside `eval \"...\"`", guard(repo, 'eval "git worktree add ../b -b feature/b dev"'), str(wt))
        allowed("guard-worktree: ...and a session owning nothing may still run it inside `bash -c`",
                guard(repo, "bash -c 'git worktree add ../b -b feature/b dev'", "SESS-B"))
        allowed("guard-worktree: ANOTHER session, owning nothing, is not held back by it", guard(repo, "git worktree add ../b -b feature/b dev", "SESS-B"))
        allowed("guard-worktree: a payload with no session_id cannot be matched to an owner, so rule 1 does not fire",
                guard(repo, "git worktree add ../b -b feature/b dev", None))
        # Scope: only `git worktree add` is judged.
        for cmd in ("git status", "git worktree list", f"git worktree remove {wt}", 'echo "git worktree add ../x"',
                    "grep -c 'worktree add' notes.md"):
            allowed(f"guard-worktree: NOT a worktree add, left alone: {cmd[:40]}", guard(repo, cmd))
        # 3 (the other half). The lane's branch merges: the session may add one again.
        git(repo, "branch", "-f", "dev", "feature/a")
        allowed("guard-worktree: after the owned worktree's branch MERGES, a new worktree is allowed",
                guard(repo, "git worktree add ../b -b feature/b dev"))

    # A lane whose worktree has been removed is finished, not in progress.
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(td)
        wt = add_wt(repo, "a", "feature/a")
        lane(repo, "SESS-A", wt, "feature/a")
        git(repo, "worktree", "remove", "--force", str(wt))
        allowed("guard-worktree: a lane whose worktree no longer exists does not block", guard(repo, "git worktree add ../b -b feature/b dev"))

    # 3. A DUPLICATE worktree for the same branch, or the same issue, is denied -- no record needed.
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(td)
        wt = add_wt(repo, "issue-77", "feature/issue-77-x")
        denied("guard-worktree: a second worktree for the SAME branch is denied (a resume creating a duplicate)",
               guard(repo, "git worktree add ../dup feature/issue-77-x"), str(wt), "feature/issue-77-x")
        denied("guard-worktree: ...even with --force", guard(repo, "git worktree add -f ../dup feature/issue-77-x"))
        denied("guard-worktree: a second worktree for the same ISSUE under another branch name is denied",
               guard(repo, "git worktree add ../again -b fix/77-again dev"), str(wt))
        denied("guard-worktree: an attached -b<branch> for the same ISSUE is read (fix/77-again)",
               guard(repo, "git worktree add -bfix/77-again ../again"), str(wt))
        denied("guard-worktree: ...and by the new worktree's DIRECTORY name", guard(repo, "git worktree add ../issue-77-redo -b scratch dev"))
        allowed("guard-worktree: a DIFFERENT issue is allowed beside it (two live worktrees for different work stay silent)",
                guard(repo, "git worktree add ../other -b fix/78-other dev"))
        add_wt(repo, "issue-2026", "feature/issue-2026-y")
        allowed("guard-worktree: a DATE in a branch name is not issue 2026 (its year must not match a real issue 2026)",
                guard(repo, "git worktree add ../d -b chore/2026-10-02-x dev"))
        denied("guard-worktree: ...but a year-sized number written as an issue IS one (this repository will pass #1900)",
               guard(repo, "git worktree add ../e -b fix/2026-again dev"))
        git(repo, "branch", "-f", "dev", "feature/issue-77-x")
        allowed("guard-worktree: once the same-issue worktree is MERGED, a new one for it is allowed (finished)",
                guard(repo, "git worktree add ../again -b fix/77-again dev"))

    # The exact-branch rule on its own: a branch with NO issue number, so the same-issue rule cannot be what refuses.
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(td)
        wt = add_wt(repo, "lane-band", "feature/lane-band")
        denied("guard-worktree: a second worktree for a branch with no issue number is denied by the branch alone",
               guard(repo, "git worktree add ../dup feature/lane-band"), str(wt), "feature/lane-band")
        denied("guard-worktree: ...also with --force", guard(repo, "git worktree add -f ../dup feature/lane-band"))
        allowed("guard-worktree: a different branch with no issue number is allowed beside it",
                guard(repo, "git worktree add ../other -b feature/other dev"))
        # S1 (ae's review of 526470f): a backslash-newline is a continuation, and the shell joins the lines.
        denied("guard-worktree: a backslash-newline continuation is joined: the operands on the next line are read",
               guard(repo, "git worktree add \\\n../dup feature/lane-band"), "feature/lane-band")
        denied("guard-worktree: ...also between an option and its value", guard(repo, "git worktree add -f -B \\\nfeature/lane-band ../dup"))
        # PARSER DIFFERENTIAL (the push security review): the hook must read the command the way git does. These
        # shapes made the helper see no branch at all, so the duplicate rule never fired.
        denied("guard-worktree: an ATTACHED -B<branch> (git accepts it) is read: a forced duplicate of a checked-out branch",
               guard(repo, "git worktree add -f -Bfeature/lane-band ../dup"), "feature/lane-band")
        denied("guard-worktree: an attached -b<branch> bundled with a flag (-fb) is read too",
               guard(repo, "git worktree add -fbfeature/lane-band ../dup"))
        denied("guard-worktree: a redirect BEFORE the commit-ish does not hide the branch",
               guard(repo, "git worktree add ../dup >/dev/null feature/lane-band"), "feature/lane-band")
        denied("guard-worktree: ...nor a redirect with a separate target", guard(repo, "git worktree add ../dup > log feature/lane-band"))
        denied("guard-worktree: ...nor a stderr redirect", guard(repo, "git worktree add ../dup 2>&1 feature/lane-band"))
        denied("guard-worktree: a `--` before the operands is read", guard(repo, "git worktree add -- ../dup feature/lane-band"))
        denied("guard-worktree: --reason <text> as two words does not swallow the branch",
               guard(repo, "git worktree add --lock --reason wip ../dup feature/lane-band"))
        denied("guard-worktree: --reason=<text> does not swallow the branch",
               guard(repo, "git worktree add --lock --reason=wip ../dup feature/lane-band"))
        allowed("guard-worktree: CONTROL: a redirect on a different, new branch is still allowed",
                guard(repo, "git worktree add ../other -b feature/other dev >/dev/null 2>&1"))

    # F1 (ae's review of #1596): an issue number is read only from the documented forms. `slug-20` is not issue 20.
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(td)
        add_wt(repo, "node-20", "chore/node-20")
        allowed("guard-worktree: `-b chore/ubuntu-20` is NOT issue 20 beside `chore/node-20`",
                guard(repo, "git worktree add ../u -b chore/ubuntu-20 dev"))
        allowed("guard-worktree: a directory `pr-20-review` is NOT issue 20", guard(repo, "git worktree add ../pr-20-review -b scratch dev"))
        wt20 = add_wt(repo, "issue-21", "feature/issue-21-x")
        denied("guard-worktree: CONTROL: `issue-21` as a branch segment IS issue 21", guard(repo, "git worktree add ../a -b feature/issue-21-again dev"))
        denied("guard-worktree: CONTROL: `N-slug` (21-again) IS issue 21", guard(repo, "git worktree add ../b -b fix/21-again dev"))

    # A record that cannot be read fails CLOSED, with the way out.
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(td)
        bad = repo / ".git" / "coordination.json"
        bad.parent.mkdir(parents=True, exist_ok=True)   # a `--match` survey stubs `git init`, so .git is not there yet
        bad.write_text("{not json")
        denied("guard-worktree: an unreadable coordination record fails closed", guard(repo, "git worktree add ../b -b feature/b dev"),
               "unreadable")

    # DORMANT outside a git repository: there are no worktrees to protect.
    with tempfile.TemporaryDirectory() as td:
        allowed("guard-worktree: outside a git repository the guard is dormant", guard(Path(td), "git worktree add ../x -b y"))



def guard_worktree_parse_fixtures() -> None:
    """What the hook READS: quoted words, mentions that are not commands, heredoc bodies (#1581)."""
    k = _worktree_kit()
    coord, git, new_repo, add_wt, lane, payload, guard, denied, allowed = (k.coord, k.git, k.new_repo, k.add_wt, k.lane, k.payload, k.guard, k.denied, k.allowed)
    _ = (coord, git, new_repo, add_wt, lane, payload, guard, denied, allowed)     # a group uses some, not all
    # Quoted words (ae's review): the shell's normaliser strips quoted spans, so these never reached the helper.
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(td)
        wt = add_wt(repo, "lane-band", "feature/lane-band")
        for cmd in ("'git' worktree add ../dup feature/lane-band", "git 'worktree' add ../dup feature/lane-band",
                    'git worktree "add" ../dup feature/lane-band', "\\git worktree add ../dup feature/lane-band"):
            denied(f"guard-worktree: a quoted or escaped word does not hide the command: {cmd}", guard(repo, cmd), "feature/lane-band")
        for cmd in ('echo "git worktree add ../x"', "echo 'git worktree add ../x -b y'", "printf '%s' \"git worktree add\" > notes.txt"):
            allowed(f"guard-worktree: ...and a plain MENTION is still left alone: {cmd[:44]}", guard(repo, cmd))

    # A MENTION must pass even when this session HOLDS a lane: were it read as a command, rule 1 would refuse it.
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(td)
        wt = add_wt(repo, "a", "feature/a")
        lane(repo, "SESS-A", wt, "feature/a")
        for cmd in ('echo "git worktree add ../x -b y"', "echo 'git worktree add ../x'", "grep -n 'worktree add' README.md",
                    "printf '%s\\n' \"git worktree add ../x\" > notes.txt"):
            allowed(f"guard-worktree: a mention is not a command, even while a lane is held: {cmd[:44]}", guard(repo, cmd))
        # S2: a heredoc BODY that mentions the command is data for the command it feeds, unless that command is a shell.
        for cmd in ("cat <<'EOF' > notes.txt\ngit worktree add ../x -b y dev\nEOF", "cat > f <<EOF\ngit worktree add ../x\nEOF"):
            allowed(f"guard-worktree: a heredoc body that merely mentions it is not a command: {cmd[:30]!r}", guard(repo, cmd))
        for cmd in ("bash <<'EOF'\ngit worktree add ../x -b y dev\nEOF", "sh <<EOF\ngit worktree add ../x -b y dev\nEOF"):
            denied(f"guard-worktree: CONTROL: a heredoc fed to a SHELL is still read as commands: {cmd[:14]!r}", guard(repo, cmd), str(wt))
        denied("guard-worktree: CONTROL: the same words as a real command ARE refused while a lane is held",
               guard(repo, "'git' worktree add ../x -b y dev"), str(wt))



def guard_worktree_failopen_fixtures() -> None:
    """Every way the hook or git can misbehave must be a refusal, never a pass (#1581)."""
    k = _worktree_kit()
    coord, git, new_repo, add_wt, lane, payload, guard, denied, allowed = (k.coord, k.git, k.new_repo, k.add_wt, k.lane, k.payload, k.guard, k.denied, k.allowed)
    _ = (coord, git, new_repo, add_wt, lane, payload, guard, denied, allowed)     # a group uses some, not all
    # The fail-open (the push's security review): a payload cwd outside any repository made the guard dormant even
    # when the command itself changes directory into one.
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(td)
        add_wt(repo, "lane-band", "feature/lane-band")
        outside = Path(td) / "elsewhere"
        outside.mkdir()
        denied("guard-worktree: `cd <repo> && git worktree add` from a cwd outside any repository cannot be judged, so it is refused",
               guard(outside, f"cd {repo} && git worktree add ../dup feature/lane-band"), "cannot be judged")
        denied("guard-worktree: ...and `git -C <repo> worktree add` likewise", guard(outside, f"git -C {repo} worktree add ../dup feature/lane-band"))
        allowed("guard-worktree: CONTROL: a plain worktree add from outside any repository is still dormant",
                guard(outside, "git worktree add ../x -b y"))

    # FAIL-OPEN PATHS (the push's security review): every way git itself can misbehave must be a refusal, never a pass.
    # A git that is missing, hangs, or cannot list worktrees used to read as "not a repository" or "no worktrees".
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(td)
        add_wt(repo, "lane-band", "feature/lane-band")
        real_git = shutil.which("git")

        def stage_bin(name: str, git_body: str | None) -> dict[str, str]:
            b = Path(td) / name
            b.mkdir()
            for tool in ("bash", "python3"):
                (b / tool).symlink_to(shutil.which(tool))
            if git_body is not None:
                _stub(b, "git", git_body.replace("REAL_GIT", real_git).replace("REAL_SLEEP", shutil.which("sleep")))
            return {"PATH": str(b)}

        no_git = stage_bin("no-git", None)
        denied("guard-worktree: with git missing a worktree add cannot be judged, so it is refused (not read as 'no repository')",
               guard(repo, "git worktree add ../dup feature/lane-band", env_extra=no_git), "cannot be judged")
        allowed("guard-worktree: ...and with git missing an ordinary command is untouched", guard(repo, "ls", env_extra=no_git))
        # The ABSOLUTE sleep: this PATH holds only bash and python3, so a bare `sleep` is "not found" and fails at once, which made
        # this fixture pass for the wrong reason (found when a mutation giving git a 60 s timeout survived it).
        slow = stage_bin("slow-git", "exec REAL_SLEEP 20")
        slow_env = dict(slow, WORKTREE_GUARD_BUDGET="1")
        denied("guard-worktree: a git that hangs is cut off and the command is refused (the hook's own timeout would let it run)",
               guard(repo, "git worktree add ../dup feature/lane-band", env_extra=slow_env), "timed out")
        # TIMED IN ITS OWN CALL, so `--match` can run it alone: a clock started before the check above would be read after
        # that check's code had been stubbed, and the check would pass on an elapsed time of zero (#1599, #1581).
        t0 = time.monotonic()
        guard(repo, "git worktree add ../dup feature/lane-band", env_extra=slow_env)
        check("guard-worktree: ...and a slow git is cut off within the budget, not after it", time.monotonic() - t0 < 8,
              f"{time.monotonic() - t0:.1f}s")
        no_list = stage_bin("no-list", 'case "$*" in *"worktree list"*) echo "fatal: simulated" >&2; exit 1;; esac\nexec REAL_GIT "$@"')
        no_common = stage_bin("no-common", 'case "$*" in *"git-common-dir"*) echo "fatal: simulated" >&2; exit 1;; esac\nexec REAL_GIT "$@"')
        denied("guard-worktree: a record location git cannot give is refused, not read as 'this session holds no lane'",
               guard(repo, "git worktree add ../x -b y dev", env_extra=no_common), "could not locate the coordination record")
        denied("guard-worktree: a `git worktree list` that fails is refused, not read as 'no worktrees'",
               guard(repo, "git worktree add ../dup feature/lane-band", env_extra=no_list), "could not list the worktrees")

    # DEGRADED. No python3: the hook cannot judge, so it refuses a worktree add and leaves everything else alone.
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(td)
        bindir = Path(td) / "bin"
        bindir.mkdir()
        for tool in ("bash", "git"):
            (bindir / tool).symlink_to(shutil.which(tool))
        bare = {"PATH": str(bindir)}
        denied("guard-worktree: with no python3 a worktree add is refused, not waved through",
               guard(repo, "git worktree add ../b -b feature/b dev", env_extra=bare), "python3")
        allowed("guard-worktree: ...and with no python3 an ordinary command is untouched", guard(repo, "git status", env_extra=bare))

    # A helper that crashes must fail CLOSED: any exit but 0 or 2 would let the command run.
    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(td)
        stage = Path(td) / "stage"
        shutil.copytree(HOOKS, stage)
        (stage / "lib" / "worktree_guard.py").write_text("import sys\nsys.exit(7)\n")
        env = dict(os.environ)
        env.pop("CLAUDE_PROJECT_DIR", None)
        done = _run(["bash", str(stage / "guard-worktree.sh")], cwd=repo, input=payload(repo, "git worktree add ../b -b b dev", "S"),
                    env=env, capture_output=True, text=True, timeout=60)
        check("guard-worktree: a crashing helper fails CLOSED (exit 2, says so)",
              done.returncode == 2 and "failed" in done.stderr, f"exit {done.returncode}: {done.stderr.strip()[:200]!r}")



def guard_worktree_pointer_fixtures() -> None:
    """The SessionStart resume pointer: advisory, fail open, silent when there is nothing to say (#1581)."""
    k = _worktree_kit()
    coord, git, new_repo, add_wt, lane, payload, guard, denied, allowed = (k.coord, k.git, k.new_repo, k.add_wt, k.lane, k.payload, k.guard, k.denied, k.allowed)
    _ = (coord, git, new_repo, add_wt, lane, payload, guard, denied, allowed)     # a group uses some, not all
    # ---- the SessionStart resume pointer: advisory, fail open, SILENT when there is nothing to say ----
    def start(repo: Path, sid: str | None = "SESS-A", **env) -> tuple[int, str]:
        stdin = json.dumps({"session_id": sid, "hook_event_name": "SessionStart"}) if sid is not None else "not json"
        return run_hook("session-start.sh", cwd=repo, stdin=stdin, unset=("CLAUDE_PROJECT_DIR",),
                        env_extra=dict({"RAILS_FLOW_ZOMBIE_WARN": "100000", "RAILS_FLOW_STOPPED_ORPHAN_WARN": "100000"}, **env))

    with tempfile.TemporaryDirectory() as td:
        repo = new_repo(td)
        code, base = start(repo)
        check("resume pointer: with nothing recorded the hook says nothing about worktrees",
              code == 0 and "resume in place" not in base and "finished worktree" not in base and "zombie" not in base, base[:200])
        wt = add_wt(repo, "a", "feature/a")
        lane(repo, "SESS-A", wt, "feature/a")
        code, out = start(repo)
        check("resume pointer: the session that holds a lane is told where to resume",
              code == 0 and "resume in place" in out and str(wt) in out and "feature/a" in out
              and "finished worktree" not in out, out[-300:])
        check("resume pointer: ANOTHER session is not pointed at it", "resume in place" not in start(repo, "SESS-B")[1])
        # A stub `ps` that reports NO zombies, so the count is 0 whatever this machine is running: against the real `ps` an
        # unclamped setting prints "3 zombie processes" when three happen to exist, and the fixture could not fail.
        no_zombies = Path(td) / "no-zombies"
        no_zombies.mkdir()
        _stub(no_zombies, "ps", "exit 0")
        for bad in ("0", "-5"):
            out = run_hook("session-start.sh", cwd=repo, stdin=json.dumps({"session_id": "SESS-A"}), path_prefix=[no_zombies],
                           env_extra={"RAILS_FLOW_ZOMBIE_WARN": bad}, unset=("CLAUDE_PROJECT_DIR",))[1]
            check(f"resume pointer: RAILS_FLOW_ZOMBIE_WARN={bad} is clamped, so zero zombies prints no '0 zombie processes' line",
                  "zombie" not in out and "resume in place" in out, out[-200:])
        # #1582 slice C: the stopped-orphan advisory. A stub `ps` lists stopped orphans for `-U`: two REAL processes (one
        # whose environment names a session, one whose ARGUMENT only spells the entry, #1646 S1) and three made-up pids,
        # plus a running one and a stopped one with a parent that must not count.
        orphans = Path(td) / "orphans"
        orphans.mkdir()
        owner_id = str(uuid.uuid4())
        env_owned = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     env={**os.environ, "CLAUDE_CODE_SESSION_ID": owner_id, "AWS_SECRET": "hunter2"})
        spoofed_id = str(uuid.uuid4())
        argv_spoof = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", f"CLAUDE_CODE_SESSION_ID={spoofed_id}"],
                                      stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                      env={k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_SESSION_ID"})
        _stub(orphans, "ps", 'case "$*" in\n'
              f'  *-U*) printf "{env_owned.pid} T 1\\n{argv_spoof.pid} Ts 1\\n13 T 1\\n14 T 1\\n15 S 1\\n16 T 99\\n" ;;\n'
              'esac\nexit 0')
        try:
            out = run_hook("session-start.sh", cwd=repo, stdin=json.dumps({"session_id": "SESS-A"}), path_prefix=[orphans],
                           env_extra={"RAILS_FLOW_ZOMBIE_WARN": "100000", "RAILS_FLOW_STOPPED_ORPHAN_WARN": "3"},
                           unset=("CLAUDE_PROJECT_DIR",))[1]
            check("stopped orphans: four stopped orphans (ppid 1) are counted, a running one and a stopped one with a parent are not",
                  "4 stopped orphan processes" in out, out[-300:])
            check("stopped orphans: the owning session is named from the environment", owner_id in out, out[-300:])
            check("stopped orphans: a session id that only an ARGUMENT spells is not shown as an owner", spoofed_id not in out, out[-300:])
            check("stopped orphans: nothing else from the environment is printed", "hunter2" not in out and "AWS_SECRET" not in out, out[-300:])
            out = run_hook("session-start.sh", cwd=repo, stdin=json.dumps({"session_id": "SESS-A"}), path_prefix=[orphans],
                           env_extra={"RAILS_FLOW_ZOMBIE_WARN": "100000", "RAILS_FLOW_STOPPED_ORPHAN_WARN": "5"},
                           unset=("CLAUDE_PROJECT_DIR",))[1]
            check("stopped orphans: below the threshold the advisory is silent", "stopped orphan" not in out, out[-300:])
        finally:
            for proc in (env_owned, argv_spoof):
                proc.kill()
                proc.wait()
        # S4: the zombie scan must finish inside session-start's own 10 s hook timeout, even when `ps` hangs.
        slow_ps = Path(td) / "slow-ps"
        slow_ps.mkdir()
        _stub(slow_ps, "ps", f"exec {shutil.which('sleep')} 20")
        t0 = time.monotonic()
        res = run_hook("session-start.sh", cwd=repo, stdin=json.dumps({"session_id": "SESS-A"}), path_prefix=[slow_ps],
                       unset=("CLAUDE_PROJECT_DIR",))
        check("resume pointer: a hanging `ps` is cut off well inside the hook's 10 s timeout", time.monotonic() - t0 < 8,
              f"{time.monotonic() - t0:.1f}s")
        check("resume pointer: ...and the lane pointer still prints when `ps` hangs", "resume in place" in res[1], res[1][-200:])
        check("resume pointer: a junk RAILS_FLOW_ZOMBIE_WARN falls back to the default and the pointer still prints",
              "resume in place" in start(repo, RAILS_FLOW_ZOMBIE_WARN="abc")[1], start(repo, RAILS_FLOW_ZOMBIE_WARN="abc")[1][-200:])
        check("resume pointer: a payload with no usable session_id is not pointed at anything (fails open, exit 0)",
              start(repo, None)[0] == 0 and "resume in place" not in start(repo, None)[1])
        done_wt = add_wt(repo, "done", "feature/done", unmerged=False)
        out = start(repo)[1]
        check("resume pointer: a merged, clean worktree is listed as finished, with how to remove it",
              "finished worktree" in out and str(done_wt) in out and "git worktree remove" in out, out[-300:])
        done_wt.mkdir(parents=True, exist_ok=True)   # a `--match` survey stubs `git worktree add`
        (done_wt / "scratch.txt").write_text("uncommitted\n")
        check("resume pointer: a merged worktree with uncommitted work is NOT listed as finished",
              str(done_wt) not in start(repo)[1])
        # Zombies: a real one, parented to this process, then reaped.
        child = subprocess.Popen(["sh", "-c", "exit 0"])
        time.sleep(0.5)
        try:
            out = start(repo, RAILS_FLOW_ZOMBIE_WARN="1")[1]
            check("resume pointer: a zombie count at the threshold is reported, naming a parent",
                  "zombie process" in out and "pid" in out, out[-300:])
            check("resume pointer: below the threshold the zombie warning is silent", "zombie" not in start(repo)[1])
        finally:
            child.wait()
        # A parent's command line can hold a credential: the advisory names the executable, never its arguments.
        # A short command line on purpose: `ps` shows argv, and the advisory used to cut it at 60 characters, so a
        # long interpreter path (Python re-executes through Python.app on macOS) would hide the secret and make
        # this fixture pass whatever the code does. perl forks a child that exits unreaped: a real zombie.
        check("resume pointer: the zombie fixture's parent can be started (perl)", shutil.which("perl") is not None, "perl not found")
        parent = subprocess.Popen(["perl", "-e", "sleep 8 if fork;", "SECRET-TOKEN-xyz"])
        time.sleep(1.0)
        try:
            out = start(repo, RAILS_FLOW_ZOMBIE_WARN="1", RAILS_FLOW_ZOMBIE_TOP="100")[1]
            check("resume pointer: the zombie advisory lists a busy parent by pid", f"pid {parent.pid}" in out, out[-300:])
            check("resume pointer: ...and never prints a parent's command-line arguments (they can hold a credential)",
                  "SECRET-TOKEN" not in out, out[-300:])
        finally:
            parent.kill()
            parent.wait()




# ---- the wall-clock deadline (#1575) ---------------------------------------------------------------
# A hook that outlives its timeout blocks every Bash call, and Claude Code's timeout stops WAITING without
# killing the hook's descendants: orphaned awk processes ran 51 minutes, one 23 hours, and the load hit 348.
# `lib/deadline.sh` runs each hook's work in its own process group under a wall-clock deadline and kills the whole
# group. The stub below is the incident: an `awk` that hangs and leaves a sleeper behind, every pid recorded.
# ---- stop-where.sh + session-start.sh's where-stopped lines (#1639) -----------------------------------------------------
def where_stopped_fixtures() -> None:
    """Where this worktree stopped: the Stop hook writes the facts file and warns ONCE about unsaved work; SessionStart
    points at it. Advisory, so every fixture also proves it fails open (exit 0, silent) rather than stopping a turn."""
    def g(cwd: Path, *args: str) -> None:
        _run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=cwd, check=True, capture_output=True)

    def stop(repo: Path, **kw) -> tuple[int, str]:
        return run_hook("stop-where.sh", cwd=repo, stdin=json.dumps({"hook_event_name": "Stop"}), **kw)

    def start(repo: Path) -> str:
        return run_hook("session-start.sh", cwd=repo, stdin=json.dumps({"session_id": "S", "hook_event_name": "SessionStart"}),
                        unset=("CLAUDE_PROJECT_DIR",), env_extra={"RAILS_FLOW_ZOMBIE_WARN": "100000"})[1]

    hooks = json.loads((HOOKS.parent / "hooks.json").read_text())["hooks"]
    check("where-stopped: stop-where.sh is registered on Stop",
          any("stop-where.sh" in h["command"] for e in hooks["Stop"] for h in e["hooks"]))
    with tempfile.TemporaryDirectory() as td:
        root = Path(td).resolve()
        remote, repo = root / "remote.git", root / "repo"
        g(root, "init", "-q", "--bare", str(remote))
        g(root, "init", "-q", "-b", "dev", str(repo))
        (repo / "a").write_text("a\n")
        g(repo, "add", "a")
        g(repo, "commit", "-q", "-m", "one")
        g(repo, "remote", "add", "origin", str(remote))
        g(repo, "push", "-q", "origin", "dev")
        handoff = Path(_run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=repo,
                            capture_output=True, text=True).stdout.strip()) / "handoff"

        code, out = stop(repo)
        check("where-stopped: clean and pushed, the Stop hook exits 0 and says nothing", code == 0 and out.strip() == "", out)
        files = list(handoff.glob("*.md")) if handoff.is_dir() else []
        check("where-stopped: the facts file is written under <git-common-dir>/handoff, one per worktree",
              len(files) == 1 and files[0].name.startswith("repo-"), str(files))
        out = start(repo)
        check("where-stopped: clean and pushed, SessionStart prints neither line though the file exists (#1643 D1)",
              "unsaved work" not in out and "where this worktree stopped" not in out, out[-300:])

        (repo / "b").write_text("b\n")
        g(repo, "add", "b")
        g(repo, "commit", "-q", "-m", "two")
        (repo / "c").write_text("c\n")
        code, out = stop(repo)
        msg = json.loads(out).get("systemMessage", "") if out.strip().startswith("{") else ""
        check("where-stopped: unpushed and uncommitted work is named once, as a systemMessage, exit 0",
              code == 0 and "1 commit not on any remote" in msg and "1 uncommitted file" in msg, out)
        check("where-stopped: the same counts on the next turn are not repeated", stop(repo)[1].strip() == "")
        text = files[0].read_text() if files else ""
        check("where-stopped: the file holds the branch, both counts and the dirty path",
              "- branch: dev" in text and "- commits not on any remote: 1" in text and "  - c" in text, text[:300])

        out = start(repo)
        check("where-stopped: SessionStart states the unsaved work and points at the file",
              "- unsaved work: 1 commit not on any remote, 1 uncommitted file" in out
              and f"where this worktree stopped (last turn, " in out and str(files[0] if files else "?") in out, out[-400:])

        # FAIL OPEN: a python3 that fails never stops the turn (a hung git is bounded by the lib's own deadline, which
        # where_stopped.py --selftest proves; the harness does not hang a real git here).
        bad = root / "bad-python"
        bad.mkdir()
        _stub(bad, "python3", "exit 7")
        code, out = stop(repo, path_prefix=[bad])
        check("where-stopped: a failing interpreter is silent and exits 0", code == 0 and out.strip() == "", out)
        outside = root / "plain"
        outside.mkdir()
        code, out = stop(outside)
        check("where-stopped: outside a git repository, silent and exit 0", code == 0 and out.strip() == "", out)


def deadline_fixtures() -> None:
    guard = HOOKS / "guard-bash.sh"
    base_env = {k: v for k, v in os.environ.items() if k not in ("QA_ALLOW_MAIN", "RAILS_FLOW_LANE", "RAILS_FLOW_HOOK_DEADLINE")}

    def alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True

    def survivors(pidfile: Path, within: float = 5.0) -> list[int]:
        """Every sleeper the stub recorded that is STILL running after `within` seconds (killed, so none leaks)."""
        pids = [int(x) for x in pidfile.read_text().split()] if pidfile.exists() else []
        end = time.monotonic() + within
        while time.monotonic() < end and any(alive(p) for p in pids):
            time.sleep(0.1)
        left = [p for p in pids if alive(p)]
        for p in left:
            try:
                os.kill(p, signal.SIGKILL)
            except ProcessLookupError:
                pass
        return left

    def stubs(td: str) -> tuple[str, Path]:
        d = Path(td) / "stubs"
        d.mkdir()
        pidfile = Path(td) / "sleepers"
        (d / "awk").write_text(f"#!/bin/bash\nsleep 300 &\necho $! >> {pidfile}\nwait\n")
        (d / "awk").chmod(0o755)
        return str(d), pidfile

    def hung(hook: Path, cmd: str, extra: dict[str, str] | None = None, deadline: str = "1"):
        """The hook with a HANGING awk: (exit, seconds, stderr, sleepers still alive afterwards)."""
        with tempfile.TemporaryDirectory() as td:
            d, pidfile = stubs(td)
            env = dict(base_env, PATH=d + os.pathsep + base_env["PATH"], RAILS_FLOW_HOOK_DEADLINE=deadline, **(extra or {}))
            t0 = time.monotonic()
            r = _run(["/bin/bash", str(hook)], cwd=td, input=json.dumps({"tool_input": {"command": cmd}}), env=env,
                     capture_output=True, text=True, timeout=60)
            took = time.monotonic() - t0
            return r.returncode, took, r.stderr, survivors(pidfile)

    # 1. guard-bash: past the deadline the command is DENIED, in about the deadline, with the whole group dead.
    rc, took, err, left = hung(guard, "git status")
    check("deadline (#1575): guard-bash refuses a command its normaliser cannot read in time (fails CLOSED)",
          rc == 2, f"exit {rc}: a hung awk was ALLOWED")
    check("deadline (#1575): ...at the deadline, not at the stub's 300 s", took < 6, f"{took:.1f}s")
    check("deadline (#1575): ...and no process the hook started outlives it (the whole group is killed)",
          not left, f"still running: {left} -- a kill of the parent alone orphans them")
    lines = [x for x in err.strip().splitlines() if x.strip()]
    check("deadline (#1575): ...with ONE line on stderr, the verdict, and no job-control notice (Claude reads stderr)",
          len(lines) == 1 and lines[0].startswith("BLOCKED by rails-flow guardrails: this command took longer than 1s"),
          repr(err[:200]))
    # 2. CONTROLS: the deadline must not be what denies an ordinary command, and a real rule still says its own reason.
    with tempfile.TemporaryDirectory() as td:
        t0 = time.monotonic()
        ok = _run(["/bin/bash", str(guard)], cwd=td, input=json.dumps({"tool_input": {"command": "git status"}}), env=base_env,
                  capture_output=True, text=True, timeout=60)
        quick = time.monotonic() - t0
        bad = _run(["/bin/bash", str(guard)], cwd=td, input=json.dumps({"tool_input": {"command": "git add -A"}}), env=base_env,
                   capture_output=True, text=True, timeout=60)
    check("deadline (#1575): CONTROL: an ordinary command still passes, silently, well inside the deadline",
          ok.returncode == 0 and not ok.stderr.strip() and quick < 5, f"exit {ok.returncode} {quick:.1f}s {ok.stderr[:100]!r}")
    check("deadline (#1575): CONTROL: a refused command still gives ITS reason, not the deadline's",
          bad.returncode == 2 and "git add -A" in bad.stderr and "took longer" not in bad.stderr, bad.stderr[:160])
    # 3. THE ORPHAN: Claude Code SIGKILLs the hook at its own timeout. The group must not run on for the deadline.
    with tempfile.TemporaryDirectory() as td:
        d, pidfile = stubs(td)
        env = dict(base_env, PATH=d + os.pathsep + base_env["PATH"], RAILS_FLOW_HOOK_DEADLINE="8")
        proc = subprocess.Popen(["/bin/bash", str(guard)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, cwd=td, env=env, start_new_session=True)
        try:
            proc.stdin.write(json.dumps({"tool_input": {"command": "git status"}}).encode())
            proc.stdin.close()
            for _ in range(100):                                  # until the stub has really started
                if pidfile.exists() and pidfile.read_text().strip():
                    break
                time.sleep(0.1)
            time.sleep(0.3)
            proc.kill()
            proc.wait()
            t0 = time.monotonic()
            left = survivors(pidfile, within=4.0)
            gone = time.monotonic() - t0
        finally:
            if proc.poll() is None:
                proc.kill()
    check("deadline (#1575): the group dies within a poll of its PARENT being SIGKILLed, not at the 8 s deadline",
          not left and gone < 4, f"still running after {gone:.1f}s: {left}")
    # 4. NO `sleep` ON PATH: a watchdog that cannot wait would reach the deadline at once and deny EVERYTHING.
    with tempfile.TemporaryDirectory() as bd:
        for tool in ("bash", "git", "sed", "tr", "grep", "dirname", "cat", "env", "head", "awk"):
            real = next((f"{x}/{tool}" for x in ("/usr/bin", "/bin") if os.path.exists(f"{x}/{tool}")), None)
            if real:
                os.symlink(real, Path(bd) / tool)
        os.symlink(sys.executable, Path(bd) / "python3")
        def nosleep(cmd: str) -> int:
            with tempfile.TemporaryDirectory() as td:
                return _run(["/bin/bash", str(guard)], cwd=td, input=json.dumps({"tool_input": {"command": cmd}}),
                            env=dict(base_env, PATH=bd, RAILS_FLOW_HOOK_DEADLINE="1"), capture_output=True, text=True,
                            timeout=60).returncode
        check("deadline (#1575): with no `sleep` on PATH an ordinary command still passes (no instant deadline)",
              nosleep("git status") == 0, "denied: the watchdog could not sleep and fired at once")
        check("deadline (#1575): ...and a refused command is still refused (the rules run, only the backstop is gone)",
              nosleep("git add -A") == 2, "exit 0")
    # 5. THE KNOB: RAILS_FLOW_HOOK_DEADLINE is an integer >= 1, never above the hook's timeout minus margin.
    def knob(value: str | None, default: int, top: int) -> str:
        env = dict(base_env)
        if value is not None:
            env["RAILS_FLOW_HOOK_DEADLINE"] = value
        script = f'. "{HOOKS / "lib" / "deadline.sh"}"; deadline_seconds {default} {top}; printf %s "$_deadline_s"'
        return _run(["/bin/bash", "-c", script], env=env, capture_output=True, text=True, timeout=30).stdout
    # F2 (#1602 review): 19+ digits overflow bash's integer comparison, the clamp never ran, and the watchdog fired at once,
    # so guard-bash denied EVERY command. Longer than 4 digits is above any ceiling; zero would fire at once too.
    for value, default, top, want in ((None, 6, 8, "6"), ("3", 6, 8, "3"), ("abc", 6, 8, "6"), ("0", 6, 8, "6"),
                                      ("", 6, 8, "6"), ("99", 6, 8, "8"), ("-4", 6, 8, "6"), ("2.5", 6, 8, "6"),
                                      ("99999999999999999999", 6, 8, "8"), ("9223372036854775808", 6, 8, "8"),
                                      ("12345", 6, 8, "8"), ("000000000000000000003", 6, 8, "8"),
                                      ("00", 6, 8, "6"), ("0008", 6, 8, "8"), ("007", 6, 8, "7")):
        check(f"deadline (#1575): the knob {value!r} with default {default} and ceiling {top} gives {want}",
              knob(value, default, top) == want, f"got {knob(value, default, top)!r}")
    # 5b. THE DEFAULT SITS UNDER THE HOOK'S OWN TIMEOUT. Past that, Claude Code stops waiting and the deadline never
    # gets to deny; the numbers are read from the hook and from its hooks.json, not repeated here.
    for hook, manifest, name in ((guard, HOOKS.parent / "hooks.json", "guard-bash.sh"),
                                 (QA_HOOK, QA_HOOK.parents[1] / "hooks.json", "release-gate.sh")):
        if not hook.is_file() or not manifest.is_file():
            continue
        m = re.search(r"deadline_seconds\s+(\d+)\s+(\d+)", hook.read_text())
        timeout = next((h["timeout"] for e in json.loads(manifest.read_text())["hooks"]["PreToolUse"]
                        for h in e["hooks"] if name in h["command"]), None)
        check(f"deadline (#1575): {name}'s default and ceiling sit below the hook's configured timeout ({timeout} s)",
              bool(m) and timeout is not None and int(m.group(1)) <= int(m.group(2)) < int(timeout),
              f"deadline_seconds {m.groups() if m else None} against a timeout of {timeout}")
    # 5c. END TO END: an overflowing or zero knob must not make the hook deny an ordinary command.
    for value in ("99999999999999999999", "00"):
        with tempfile.TemporaryDirectory() as td:
            r = _run(["/bin/bash", str(guard)], cwd=td, input=json.dumps({"tool_input": {"command": "git status"}}),
                     env=dict(base_env, RAILS_FLOW_HOOK_DEADLINE=value), capture_output=True, text=True, timeout=60)
        check(f"deadline (#1575): RAILS_FLOW_HOOK_DEADLINE={value} does not make guard-bash deny an ordinary command",
              r.returncode == 0 and not r.stderr.strip(), f"exit {r.returncode}: {r.stderr[:120]!r}")
    # 6. qa-flow's release gate shares the normaliser and the lib; a timeout refuses a PROMOTION and nothing else.
    if QA_HOOK.is_file():
        for cmd in ("git push origin main", "gh pr merge 12 --merge"):
            rc, took, err, left = hung(QA_HOOK, cmd)
            check(f"deadline (#1575): release-gate refuses `{cmd}` when it cannot finish reading it (fails CLOSED)",
                  rc == 2 and "looks like a promotion" in err, f"exit {rc}: {err[:160]!r}")
            check(f"deadline (#1575): ...in about the deadline, with no process left running",
                  took < 6 and not left, f"{took:.1f}s, still running: {left}")
        # F1 (#1602 review): the normal path denies ANY GraphQL mutation by shape, so the timeout path denies by the word,
        # whatever the mutation is called or how the flag is spelled. A list of names let three promotions through.
        gql = "gh api graphql %s query='mutation { %s(input:{}) { clientMutationId } }'"
        for flag, name in (("-f", "enablePullRequestAutoMerge"), ("-F", "enablePullRequestAutoMerge"),
                           ("--raw-field", "enablePullRequestAutoMerge"), ("-F", "createCommitOnBranch"),
                           ("--raw-field", "updatePullRequestBranch")):
            rc, took, err, left = hung(QA_HOOK, gql % (flag, name))
            check(f"deadline (#1575): release-gate refuses `gh api graphql {flag}` {name} when it cannot finish reading it",
                  rc == 2 and "looks like a promotion" in err and not left, f"exit {rc}: {err[:120]!r}")
        for what, cmd in (("a GraphQL query with no mutation", "gh api graphql -f query='{ viewer { login } }'"),
                          ("a REST read", "gh api repos/o/r/issues")):
            rc, took, err, left = hung(QA_HOOK, cmd)
            check(f"deadline (#1575): CONTROL: release-gate ALLOWS {what} on a timeout", rc == 0 and not left,
                  f"exit {rc}: {err[:120]!r}")
        # THE DIFFERENTIAL (#1602 review of the timeout path). The coarse detector decides on a timeout, and for the
        # missing-tool path too: it is ONE function. 486 promotion-shaped commands from this file's own fixtures were run
        # through the full path and through a timeout; every shape below was DENIED by the full path and ALLOWED by the
        # coarse one. It is driven through the missing-tool path (PATH holds only bash), which reaches the same function
        # and answers at once, with two end-to-end timeout checks to show the timeout path really calls it.
        with tempfile.TemporaryDirectory() as bd:
            os.symlink("/bin/bash", Path(bd) / "bash")

            def coarse(cmd: str) -> int:
                return _run(["/bin/bash", str(QA_HOOK)], cwd=bd, input=json.dumps({"tool_input": {"command": cmd}}),
                            env={"PATH": bd, "HOME": os.environ.get("HOME", "/tmp")}, capture_output=True, text=True,
                            timeout=60).returncode
            for what, cmds in (
                ("the `heads/` shorthand for refs/heads/main", ("git push origin HEAD:heads/main", "git push origin HEAD:heads/master",
                                                                "git push -f origin HEAD:heads/main", "git push origin heads/main:heads/main",
                                                                "git push origin :heads/main", "git push origin 'HEAD:heads/main'",
                                                                'git push origin "HEAD:heads/main"', "git push origin feature/work:heads/main")),
                ("a push of every branch (--all, --mirror)", ("git push --all", "git push origin --all", "git push --mirror", "git push --mirror origin")),
                ("a wildcard refspec, which pushes every branch", ("git push origin refs/heads/*:refs/heads/*",
                                                                   "git push origin +refs/heads/*:refs/heads/*", "git push origin '*:*'")),
                ("update-branch", ("gh pr update-branch", "gh pr update-branch 7 --rebase", "gh api -X PUT repos/o/r/pulls/7/update-branch")),
                ("a workflow run", ("gh workflow run release.yml", "gh workflow run gates.yml --ref x")),
                ("a repository dispatch", ("gh api -X POST repos/o/r/dispatches -f event_type=release",
                                           "gh api repos/o/r/actions/workflows/r.yml/dispatches -X POST -f ref=main")),
                ("a GraphQL body it cannot read (--input, -F query=@file)", ("gh api graphql --input q.json", "gh api graphql --input -",
                                                                              "gh api graphql -F query=@q.graphql", "gh api graphql --field query=@-",
                                                                              "gh api graphql -Fquery=@q")),
                # #1606 / #1609: the explicit-repository shapes whose ref or tag climbs, carries a fragment or a %2f. The full path now
                # refuses them as "not a plain name"; the TIMEOUT path has no ref to inspect, so it must refuse them by the words
                # (a REST merge, a ref write, a release publish). Pinned here so a later edit to those rules cannot reopen them.
                ("a REST merge or ref write whose head or sha is not a plain name (#1606)",
                 ("gh api -X POST repos/o/r/merges -f base=main -f head='abc#frag'",
                  "gh api -X POST repos/o/r/merges -f base=main -f head=x/../../../issues/1",
                  "gh api -X POST repos/o/r/merges -f base=main -f head='a%2f..%2fb'",
                  "gh api -X PATCH repos/o/r/git/refs/heads/main -f sha=../../x",
                  "gh api -X PATCH repos/o/r/git/refs/heads/main -f sha='abc#frag'")),
                ("a release publish whose tag or target is not a plain name (#1606)",
                 ("gh release create v1.0.0 --repo o/r --target ../x", "gh release create v1.0.0 --repo o/r --target 'a#b'",
                  "gh release create ../v1 --repo o/r --target main", "gh release create 'v%2f..%2f1' --repo o/r --target main")),
                # #1607 (the #1602 delta review's residuals S1-S4). The coarse detector is an allow-by-default WORD LIST while the full
                # path denies an unlisted `gh` write by default, so each word narrowed the gap and none closed it. These are RULES: any
                # `gh api` that writes, a few CLI verbs that write, a main spelled so no word shows, and a GraphQL body built by substitution.
                ("a `gh api` that WRITES, by method or by fields (S1, S2); the cost, accepted for a fallback that runs only when the gate overran its "
                 "deadline, is that an ordinary `gh api ... -f body=x` is refused too",
                 ("gh api repos/o/r/contents/f.txt -X PUT -f branch=main -f message=m -f content=Zg==", "gh api -X DELETE repos/o/r/contents/f.txt -f branch=main",
                  "gh api repos/o/r/contents/f.txt -XPUT -f branch=main", "gh api repos/o/r/branches/main/rename -f new_name=x",
                  "gh api --method POST repos/o/r/issues -f title=x", "gh api repos/o/r/contents/f.txt --input body.json",
                  "gh api -X POST repos/o/r/actions/runs/1/rerun", "gh api repos/o/r/actions/runs/1/rerun-failed-jobs -X POST",
                  "gh api repos/o/r/issues/1/comments -f body=x", "gh api repos/o/r/issues/1/comments -fbody=x", "gh api repos/o/r/issues -F title=x",
                  "gh api -X PUT repos/o/r/subscription", "gh api --method PATCH repos/o/r", "gh api -X 'DELETE' repos/o/r/subscription")),
                ("a bare `gh api` on a merge, ref, release or dispatch endpoint: the word rules (#1602, #1606) still refuse what no method or field "
                 "marks as a write, an over-block the full path does not share (it allows the read), accepted for the fallback",
                 ("gh api repos/o/r/dispatches", "gh api repos/o/r/merges", "gh api repos/o/r/git/refs/heads/main", "gh api repos/o/r/releases")),
                ("a `gh` verb that changes a repository or re-runs a workflow (S1, S2)",
                 ("gh repo sync o/r --branch main", "gh repo edit --default-branch main", "gh repo edit o/r --description x",
                  "gh run rerun 123", "gh run rerun 123 --failed", "gh workflow enable release.yml")),
                ("a `git push` whose destination is spelled so no word shows (S3): a variable, a glob, a brace expansion, or a name split by a quote, a backslash or a backtick",
                 ("git push origin HEAD:$B", "git push origin HEAD:${B}", "git push origin HEAD:refs/heads/mai?", "git push origin HEAD:ma[i]n",
                  "git push origin HEAD:ma{in,}", "git push origin 'HEAD:ma''in'", 'git push origin "HEAD:ma""in"', "git push origin $(git rev-parse --abbrev-ref HEAD)",
                  "git $V push origin feature/x", "git  $V push origin feature/x",
                  # the #1607 review's 19 of 31: every quote, backslash and backtick spelling of main, not just the empty pair
                  'git push origin HEAD:"ma"in', 'git push origin HEAD:m"ain"', "git push origin HEAD:ma'in'", "git push origin HEAD:'m'ain",
                  "git push origin HEAD:m'a'in", "git push origin HEAD:ma\\in", "git push origin HEAD:m\\ain", "git push origin HEAD:mai\\n",
                  "git push origin ma\\in", "git push origin 'HEAD:m'ain", "git push origin HEAD:ma`:`in", 'git push origin HEAD:refs/heads/"ma"in',
                  "git push origin HEAD:heads/ma'in'", 'git push origin "ma"in', 'git push origin "HEAD":ma\\in')),
                ("an ORDINARY quoted ref, a multi-line command or a backticked commit message that says `git push` (the accepted cost of one character class "
                 "instead of a list of spellings: a fallback that runs only after the gate overran its deadline, 'retry it')",
                 ("git push origin 'feat/x'", 'git push origin "feat/x"', "git push origin feature/x\ngit commit -m 'it works'", "git commit -m 'push the fix'",
                  "git commit -m \"$(cat <<'EOF'\nnever `git push --force`\nEOF\n)\"")),
                ("a GraphQL body built by substitution (S4)",
                 ('gh api graphql -f query="$(cat q.graphql)"', "gh api graphql -f query=`cat q.graphql`", "gh api graphql -f query=<(cat q.graphql)")),
                ("a push whose verb or remote is disguised but whose destination is still named",
                 ("git -c alias.p=push p origin HEAD:main", "git -c url.b.insteadOf=a push origin main")),
                # #1617 (the #1615 review, N1): a `gh` verb that is not on the READ-ONLY list is refused. 13 of these 23 slipped through the word list.
                ("a `gh` verb that is not on the FULL path's safe list (#1617): the 13 the word list let through, and a spelling the walker must see through",
                 ("gh repo rename x", "gh repo archive o/r", "gh repo unarchive o/r", "gh repo delete o/r --yes", "gh repo set-default o/r", "gh repo create o/x",
                  "gh repo deploy-key add k.pub", "gh workflow disable ci.yml", "gh release delete v1", "gh ruleset create", "gh codespace create",
                  "gh pm 1", "gh co 1", "gh -R o/r pr merge 7", "gh pr merge 7 --repo o/r", "gh pr update-branch 7", "gh workflow run r.yml", "gh release create v1",
                  "gh release edit v1", "bash -c 'gh release create v1.0.1'")),
                # #1617 (N4): a git alias hides `push`: the verb is not one git has, and main is among its arguments.
                ("a git ALIAS that hides `push` (#1617, N4)",
                 ("git p origin main", "git -C . p origin HEAD:main", "git -c user.name=x ph origin master", "git p origin HEAD:refs/heads/main")),
                # #1617 (N5): `?` is a glob unless it opens a URL query (`?key=`); `ma?n` is main.
                # #1617 review: shell quote removal makes a QUOTED or ESCAPED verb a push; the word-boundary change had let 20 of these through.
                ("a QUOTED or ESCAPED `push` (#1617 review): the verb is a push once the shell removes the quotes",
                 ('git "push" origin HEAD:ma?n', "git 'push' origin HEAD:ma?n", 'git "push" origin HEAD:"ma"in', "git 'push' origin 'ma''in'",
                  'git "push" origin HEAD:ma[i]n', 'git "push" origin HEAD:ma{in,}', 'git "push" origin HEAD:$B', "git \\push origin HEAD:ma\\in",
                  'true; git "push" origin HEAD:ma?n', "(git 'push' origin HEAD:ma?n)", 'env FOO=1 git "push" origin HEAD:ma?n',
                  "command git 'push' origin HEAD:ma?n", 'git -c x=y "push" origin HEAD:ma?n', '/usr/bin/git "push" origin HEAD:ma?n')),
                ("a `?` glob in the destination that is not a URL query (#1617, N5)",
                 ("git push origin HEAD:ma?n", "git push origin HEAD:m?in", "git push origin HEAD:refs/heads/ma?n")),
            ):
                for cmd in cmds:
                    check(f"deadline (#1575): the coarse detector refuses {what}: `{cmd}`", coarse(cmd) == 2, "exit 0: allowed")
            # THE CONTROLS: refusing everything would pass every example above. `-f query=@x` is a LITERAL string in gh (only
            # `-F` reads a file) and the full path allows it too; `--tags` pushes no branch; a branch NAMED heads/... or
            # feature/main-menu is not main.
            # #1607 controls: a RULE over-blocks more than a word does, so each rule has the ordinary command it must leave alone. A
            # `-X GET` (or no method and no fields) is a read; `?` inside a URL query is not a glob; a plain quoted ref is not an empty pair.
            for cmd in ("gh api repos/o/r/pulls", "gh api repos/o/r/issues/1/comments", "gh api -X GET repos/o/r/pulls -f per_page=100",
                        "gh api --method GET repos/o/r/pulls -F per_page=100", "gh api repos/o/r/issues --jq '.[].number'", "gh run list",
                        "gh run view 123", "gh repo view o/r", "gh repo clone o/r", "gh workflow view release.yml",
                        # #1617: the read-only verbs stay allowed with a repo flag before or after, and a git ALIAS that does not name main is not a promotion
                        "gh pr view 7", "gh pr list", "gh pr checks 7", "gh release list", "gh release view v1", "gh -R o/r pr view 7", "gh pr view 7 --repo o/r",
                        "gh auth status", "gh search issues x", "gh pr create --fill", "gh issue comment 5 -b x", "gh run cancel 1", "gh release upload v1 f.zip", "gh secret delete X", "git p origin feature/x", "git checkout main", "git log main", "git diff main", "git fetch origin main",
                        "git branch main", 'git checkout -b "feature/push-fix"', 'git checkout -b "feature/push fix"', "git checkout -b feature/push-fix",
                        'git log --grep pushed "x y"', 'git push origin feature/x; git log --grep pushed "x y"',
                        "git push https://x.test/r.git?z=1 feature/x", "git push origin feature/x:feature/y",
                        "gh api graphql -f query='{ repository(owner:\"o\", name:\"r\") { id } }'"):
                check(f"deadline (#1575): CONTROL (#1607): the coarse detector allows `{cmd}`", coarse(cmd) == 0, "exit 2: refused")
            # #1607: the destination is what FOLLOWS `push` in the same simple command. A `$` in an earlier line, an env prefix, a commit
            # message, or a loop that merely says "push" is not a destination (first version: 5 of 8 new refusals were this).
            for cmd in ("cat <<EOF\n$(git rev-parse HEAD)\nEOF\ngit push origin feature/w", "x=$(git rev-parse HEAD) git push origin feature/w",
                        "for k in \"force-push\" \"no-verify\"; do grep -c \"$k\" GUARDRAILS.md; done", "git status && git push origin feature/x"):
                check(f"deadline (#1575): CONTROL (#1607): a `$` that does not follow `push` is not refused: `{cmd[:60]!r}`", coarse(cmd) == 0, "exit 2: refused")
            # THE JSON WRAPPER IS NOT THE COMMAND: the payload holds braces, brackets, commas and quotes of its own, and a rule that looked at
            # `{` or `[` anywhere would refuse every command. A payload with extra keys and an array must still pass.
            wrapped = json.dumps({"tool_input": {"command": "git push origin feature/x", "description": "push the branch, then [wait]"},
                                  "session_id": "s", "args": ["a", "b"],
                                  "meta": {"a": 1, "b": 2}})
            ok = _run(["/bin/bash", str(QA_HOOK)], cwd=bd, input=wrapped, env={"PATH": bd, "HOME": os.environ.get("HOME", "/tmp")},
                      capture_output=True, text=True, timeout=60).returncode
            check("deadline (#1575): CONTROL (#1607): a payload with extra keys, an array and braces of its own is not refused", ok == 0, f"exit {ok}")
            # #1617: THE COARSE `gh` LIST IS THE FULL PATH'S. Every verb push_targets.py allows (`GH_GROUPS_ANY`, `GH_GROUPS_SOME`) is allowed on a timeout,
            # and a sample of the verbs it does NOT list is refused, so the two cannot drift apart. Imported, not copied.
            import importlib.util as _ilu
            _sp = _ilu.spec_from_file_location("push_targets_for_drift", str(QA_HOOK.parents[2] / "scripts" / "push_targets.py"))
            _pt = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_pt)
            _safe = [f"gh {g} x" for g in sorted(_pt.GH_GROUPS_ANY)] + [f"gh {g} {v} x" for g, vs in sorted(_pt.GH_GROUPS_SOME.items()) for v in sorted(vs)]
            _bad = [c for c in _safe if coarse(c) != 0]
            check("deadline (#1617): every `gh` verb the full path allows is allowed on a timeout, so the two lists agree", not _bad and len(_safe) > 40,
                  f"{len(_safe)} verbs; refused on a timeout: {_bad[:6]}")
            _unlisted = [f"gh {g} {v} x" for g, v in (("repo", "rename"), ("repo", "delete"), ("workflow", "disable"), ("workflow", "enable"), ("release", "delete"),
                                                     ("release", "create"), ("ruleset", "create"), ("codespace", "create"), ("pr", "merge"), ("pr", "update-branch"))]
            _bad = [c for c in _unlisted if coarse(c) != 2 or c.split()[2] in _pt.GH_GROUPS_SOME.get(c.split()[1], ())]
            check("deadline (#1617): the `gh` verbs the full path does not list are refused on a timeout", not _bad, f"allowed or listed: {_bad}")
            # The quote/backslash/backtick rule stops at the first RAW double quote, which ends the command in the payload; an apostrophe in a LATER key
            # (a `description` that says "don't wait") is not part of the destination.
            apos = json.dumps({"tool_input": {"command": "git push origin feature/x", "description": "send the branch, don't wait"}, "session_id": "s"})
            ok = _run(["/bin/bash", str(QA_HOOK)], cwd=bd, input=apos, env={"PATH": bd, "HOME": os.environ.get("HOME", "/tmp")},
                      capture_output=True, text=True, timeout=60).returncode
            check("deadline (#1575): CONTROL (#1607): an apostrophe in a later payload key is not read as part of the push destination", ok == 0, f"exit {ok}")
            for cmd in ("git push origin feature/x", "git push origin HEAD:heads/feature/x", "git push origin HEAD:heads/feature/main-menu",
                        "git push origin heads/feature/x", "git push --tags origin", "git status", "git commit -m tidy",
                        "gh workflow list", "gh workflow view release.yml", "gh run list", "gh pr view 7", "gh pr list",
                        "gh api repos/o/r/pulls", "gh api graphql -f query='{ viewer { login } }'",
                        "gh api graphql -f query=@q.graphql", "gh api graphql --raw-field query=@-", "git push -u origin fix/1010-one-main"):
                check(f"deadline (#1575): CONTROL: the coarse detector allows `{cmd}`", coarse(cmd) == 0, "exit 2: refused")
        for cmd in ("git push origin HEAD:heads/main", "git push --all", "gh run rerun 123", "git push origin HEAD:$B"):
            rc, took, err, left = hung(QA_HOOK, cmd)
            check(f"deadline (#1575): a TIMEOUT refuses `{cmd}` through that same detector",
                  rc == 2 and "looks like a promotion" in err and not left, f"exit {rc}: {err[:120]!r}")
        rc, took, err, left = hung(QA_HOOK, "ls -la")
        check("deadline (#1575): release-gate ALLOWS a command that does not look like a promotion when it times out "
              "(blocking every slow command would be the failure)", rc == 0 and not left, f"exit {rc}: {err[:120]!r}")
        rc, took, err, left = hung(QA_HOOK, "git push origin main", {"QA_ALLOW_MAIN": "1"})
        check("deadline (#1575): QA_ALLOW_MAIN=1 is honoured and audited on a timeout, as in the missing-tool path",
              rc == 0 and "audited" in err, f"exit {rc}: {err[:160]!r}")


GROUPS = {
    "stop_gate": stop_gate_fixtures, "guard_lane": guard_lane_fixtures,
    "guard_migrate": guard_migrate_fixtures, "lint_ruby": lint_ruby_fixtures,
    "self_consistency": self_consistency_fixtures, "guard_bash": guard_bash_fixtures,
    "guard_claims": guard_claims_fixtures, "guard_claims_pipe": guard_claims_pipe_fixtures, "release_gate": release_gate_fixtures,
    "release_gate_effects": release_gate_effects_fixtures, "release_gate_repos": release_gate_repos_fixtures,
    "release_gate_refs": release_gate_refs_fixtures,
    "ci_verdict_hint": ci_verdict_hint_fixtures, "session_end": session_end_fixtures, "timeout": timeout_fixtures,
    "guard_worktree": guard_worktree_fixtures, "guard_worktree_parse": guard_worktree_parse_fixtures,
    "guard_worktree_failopen": guard_worktree_failopen_fixtures, "guard_worktree_pointer": guard_worktree_pointer_fixtures,
    "deadline": deadline_fixtures, "where_stopped": where_stopped_fixtures,
}


# The doctor runs this harness as THREE gates (`--part a`, `--part b`, `--part c`), because the whole run takes far longer than
# the doctor's 180 s limit for a gate, and a gate that cannot finish is a SKIP on every sweep (#1581). It was two gates until
# a measurement showed part a alone at 164 CPU-seconds and 244 s wall under load: dev's `guard_claims` had grown from 4.9 s to
# 55.6 s since the first split, and the worktree groups came on top, so a skip would have been the normal result.
# MEASURED per group (CPU seconds, user+sys, which a busy machine does not inflate the way wall time is): release_gate_effects
# 60.7, guard_claims 55.6, release_gate 49.7, guard_bash 36.9, release_gate_repos 33.6, guard_worktree 11.1, guard_worktree_pointer
# 6.1, release_gate_refs 4.1, guard_worktree_parse 3.4, guard_worktree_failopen 2.0, deadline 2.1 (but 19 s of wall, it waits on
# hung processes), the rest under 1 each. So part a is
# guard_claims + guard_bash + the small ones (about 96), part b the two release_gate groups (about 110), and part c the
# repos, refs and deadline groups and the four worktree groups (about 60 CPU-s, about 80 s of wall). EVERY group must be in exactly one part: a group in none
# would never run in the doctor, which is the vacuous gate this repository keeps finding; the selftest checks it below.
PARTS = {
    "a": ["stop_gate", "guard_lane", "guard_migrate", "lint_ruby", "self_consistency", "guard_bash", "guard_claims", "guard_claims_pipe",
          "ci_verdict_hint", "session_end", "timeout"],
    "b": ["release_gate", "release_gate_effects"],
    "c": ["release_gate_repos", "release_gate_refs", "guard_worktree", "guard_worktree_parse",
          "guard_worktree_failopen", "guard_worktree_pointer", "deadline", "where_stopped"],
}


def parse_part(value: str) -> list[str] | None:
    """The groups `--part` names, or None when it must be REFUSED: an unknown part would run nothing and pass."""
    return list(PARTS[value]) if value in PARTS else None


def parse_only(value: str) -> list[str] | None:
    """The groups `--only` names, or None when it must be REFUSED: an unknown or empty group would
    run nothing and pass -- a mutant "surviving" because its fixtures were never selected."""
    groups = value.split(",")
    # Every name known, none empty (so no trailing comma), none repeated: a selection runs exactly
    # what it names, once (review of PR #1506).
    if any(g not in GROUPS for g in groups) or len(set(groups)) != len(groups):
        return None
    return groups


_NESTED = False


def run_groups(groups: list[str] | None, table: dict) -> None:
    for name in (groups or list(table)):
        table[name]()


def groups_should_run(fail_fast: bool, failures: list[str], nested: bool = False) -> bool:
    """Whether `selftest` runs the real hook groups after its meta-checks (#1599).

    Not under `--fail-fast` once a meta-check has failed: the groups have nothing to add and cost minutes. A mutant of
    the group machinery (`--only` ignored) used to run every group, over 300 s here, after its meta-check had already
    caught it, and that read as a timeout. And never in a NESTED selftest, which exists only to prove that a bad
    `--only` or `--match` is refused: were the refusal broken, the nested call fell through and ran the whole suite."""
    return not nested and not (fail_fast and bool(failures))


def run_matching(groups: list[str] | None, table: dict, match: str) -> int:
    """`--match`: run only the checks whose label contains `match` (#1599); how many ran.

    Two passes per group (see the note at `_MATCH_MODE`). Raises `MatchSequenceError` when the passes
    disagree or a group cannot be surveyed under stubs, so a selection is never silently wrong."""
    global _MATCH_MODE, _SURVEYED, _WANTED, _INDEX, _SKIP
    ran = 0
    try:
        for name in (groups or list(table)):
            _MATCH_MODE, _SURVEYED = "survey", []
            try:
                table[name]()
            except Exception as exc:        # noqa: BLE001 -- any crash under stubs means "cannot survey"
                raise MatchSequenceError(f"group {name!r} cannot be surveyed under stubs: {exc!r}") from exc
            _WANTED = {i for i, label in enumerate(_SURVEYED) if match.lower() in label.lower()}
            if not _WANTED:
                continue
            _MATCH_MODE, _INDEX, _SKIP = "run", 0, 0 not in _WANTED
            table[name]()
            if _INDEX != len(_SURVEYED):
                raise MatchSequenceError(f"group {name!r} made {_INDEX} checks in the run pass and "
                                         f"{len(_SURVEYED)} in the survey")
            ran += len(_WANTED)
    finally:
        _MATCH_MODE, _SKIP = None, False
    return ran


def meta_checks() -> None:
    """The checks about `--only` and `--match` themselves. Cheap, but not free (about 2.5 s), so a `--match` run
    skips them: the baseline run of the same file has already shown them pass (#1599)."""
    # --only REFUSES what it cannot run (#1497), checked on every run whatever the selection: a
    # silently empty selection is how a mutant would "survive" with no fixture ever consulted.
    for bad in ("nope", "", ",", "release_gate,nope", "release_gate,", " release_gate", "timeout,timeout"):
        check(f"--only {bad!r} is refused (exit 2), never an empty pass", parse_only(bad) is None,
              repr(parse_only(bad)))
    # The partition behind the doctor's two gates: complete, disjoint, and a bad name refused.
    flat = [g for part in PARTS.values() for g in part]
    check("every fixture group is in exactly one PART, so the doctor's three gates together run all of them",
          sorted(flat) == sorted(GROUPS), f"in a part but not a group, or the reverse: {sorted(set(flat) ^ set(GROUPS))}; "
          f"repeated: {sorted({g for g in flat if flat.count(g) > 1})}")
    check("a label's temp path is masked, including a name cut short, so --match compares the survey with the run (#1596)",
          _stable("x: git worktree remove /tmp/tmpAbCd1234/a") == _stable("x: git worktree remove /tmp/tmpZyXw9876/a")
          and _stable("x: git worktree remove /private/tmp/tmpp47g") == _stable("x: git worktree remove /private/tmp/tmp_1_y")
          and _stable("no path in this label") == "no path in this label"
          and _stable("a /tmp/tmpAbCd1234/x") != _stable("b /tmp/tmpAbCd1234/x"),
          repr([_stable("x: git worktree remove /tmp/tmpAbCd1234/a"), _stable("x /private/tmp/tmpp47g")]))
    check("--part a, --part b and --part c name groups; any other part is refused, never an empty pass",
          all(parse_part(k) == PARTS[k] for k in ("a", "b", "c")) and all(parse_part(x) is None for x in ("", "d", "ab", "A")),
          repr([parse_part(x) for x in ("a", "b", "c", "", "d")]))
    check("CONTROL: --only release_gate,guard_bash is accepted",
          parse_only("release_gate,guard_bash") == ["release_gate", "guard_bash"], repr(parse_only("release_gate,guard_bash")))
    # ...and a selection runs exactly what it names, proved on stand-ins so the proof costs nothing.
    ran: list[str] = []
    fakes = {name: (lambda n=name: ran.append(n)) for name in GROUPS}
    run_groups(["timeout", "stop_gate"], fakes)
    check("--only runs exactly the groups it names, in order", ran == ["timeout", "stop_gate"], repr(ran))
    # ...and a BARE run -- the doctor's `hook gates` gate -- runs every group. A break here would let
    # that gate pass having run no hook fixture at all (review of PR #1506).
    ran.clear()
    run_groups(None, fakes)
    check("a bare run (no --only) runs every group", ran == list(GROUPS), repr(ran))
    # `--match` (#1599), proved on stand-in groups: a few process starts, no hook fixture.
    global CHECKS
    with tempfile.TemporaryDirectory() as td:
        spawned = Path(td) / "spawned"

        def mark(name: str) -> None:
            _run(["sh", "-c", f"echo {name} >> '{spawned}'"])

        def fake_group() -> None:
            mark("A"); check("fixture A passes", True)
            mark("B"); check("fixture B passes", True)
            mark("C"); check("fixture C fails on purpose", False, "on purpose")

        def steered_group() -> None:
            answered = _run(["sh", "-c", "echo x"], capture_output=True, text=True).stdout
            if answered:                      # '' in the survey, 'x' in a real run: the passes would disagree...
                check("answered by the subprocess", True)
            else:                             # ...on WHICH check comes first, with the same number of checks in both
                check("silent subprocess", True)
            check("last", True)

        saved_checks, saved_failures = CHECKS, list(FAILURES)
        got = run_matching(None, {"fake": fake_group}, "fixture B")
        only_b = spawned.read_text().split() if spawned.exists() else []
        counted, failed = CHECKS - saved_checks, len(FAILURES) - len(saved_failures)
        check("--match runs only the fixture whose label matches, and none of the others' work",
              got == 1 and only_b == ["B"] and counted == 1 and failed == 0, f"ran {got}, spawned {only_b}, counted {counted}")
        spawned.unlink(missing_ok=True)
        before_c, checks_before_c = len(FAILURES), CHECKS
        run_matching(None, {"fake": fake_group}, "fails on purpose")
        failed_c = len(FAILURES) - before_c
        del FAILURES[before_c:]                 # the deliberate failure was the proof, not a finding; the first check's own verdict stays
        CHECKS = checks_before_c
        check("--match still FAILS when the check it selected fails", failed_c == 1, f"{failed_c} failure(s) recorded")
        check("--match that selects nothing runs nothing and says so (0), never an empty pass",
              run_matching(None, {"fake": fake_group}, "no label has this") == 0)
        try:
            run_matching(None, {"steered": steered_group}, "silent subprocess")
            raised = False
        except MatchSequenceError:
            raised = True
        check("--match raises when a fixture's result steers which checks follow, never guesses",
              raised and _MATCH_MODE is None and not _SKIP, f"raised={raised}, mode={_MATCH_MODE}, skip={_SKIP}")
    check("a nested selftest, which only proves a refusal, never runs the real groups",
          groups_should_run(False, [], nested=True) is False)
    check("--fail-fast skips the real groups once a meta-check has failed",
          groups_should_run(True, ["a meta-check failed"]) is False)
    check("CONTROL: --fail-fast runs the groups when nothing has failed", groups_should_run(True, []) is True)
    check("CONTROL: with no --fail-fast the groups run even after a failure",
          groups_should_run(False, ["a meta-check failed"]) is True)
    # The REAL exit code, not only the parser's verdict: main() must return 2 for a bad selection.
    # Only at the outermost level: were the refusal broken, main() would call selftest() again,
    # and this check would recurse instead of failing by name.
    global _NESTED
    if not _NESTED:
        import contextlib, io
        _NESTED = True
        try:
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                try:
                    rc = main(["--only", "nope"])
                except Exception as exc:          # noqa: BLE001 -- a crash fails THIS check, by name
                    rc = f"raised {exc!r}"
        finally:
            _NESTED = False
        check("main() exits 2 for --only nope", rc == 2, f"exit {rc}")
        # `--match` the same way (#1599): a selection that names no check, or a blank one, is refused, not passed.
        _NESTED = True
        try:
            with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
                try:
                    rc_none = main(["--only", "guard_lane", "--match", "no check has this label fragment"])
                    rc_blank = main(["--only", "guard_lane", "--match", "   "])
                except Exception as exc:          # noqa: BLE001 -- a crash fails THIS check, by name
                    rc_none = rc_blank = f"raised {exc!r}"
        finally:
            _NESTED = False
        check("main() exits 2 for --match that selects nothing", rc_none == 2, f"exit {rc_none}")
        check("main() exits 2 for a blank --match", rc_blank == 2, f"exit {rc_blank}")


def selftest(groups: list[str] | None = None, match: str | None = None, fail_fast: bool = False) -> int:
    if match is None:
        meta_checks()
    if match is None:
        if groups_should_run(fail_fast, FAILURES, nested=_NESTED):
            run_groups(groups, GROUPS)
    else:
        try:
            ran_matching = run_matching(groups, GROUPS, match)
        except MatchSequenceError as exc:
            print(f"check_hook_gates: --match {match!r} cannot be used here: {exc}", file=sys.stderr)
            return 2
        if ran_matching == 0:
            print(f"check_hook_gates: --match {match!r} selected no check, which would be an empty pass",
                  file=sys.stderr)
            return 2
    if FAILURES:
        print(f"check_hook_gates selftest: {len(FAILURES)} of {CHECKS} checks FAILED", file=sys.stderr)
        for f in FAILURES:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"check_hook_gates selftest: {CHECKS} checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="drive every hook under its stub environments")
    ap.add_argument("--only", metavar="GROUP[,GROUP]",
                    help=f"run only these fixture groups: {', '.join(GROUPS)} (#1497)")
    ap.add_argument("--part", metavar="a|b", help="run one half of the groups: the doctor runs both as two gates (#1581)")
    ap.add_argument("--match", metavar="SUBSTR",
                    help="run only the checks whose label contains SUBSTR, case-insensitively (#1599)")
    ap.add_argument("--fail-fast", action="store_true",
                    help="skip the real hook groups when the suite's own meta-checks have already failed (#1599)")
    args = ap.parse_args(argv)
    if args.match is not None and not args.match.strip():
        print("check_hook_gates: --match needs a non-empty label fragment", file=sys.stderr)
        return 2
    if args.part is not None and args.only is not None:
        print("check_hook_gates: --part and --only are alternatives, not both", file=sys.stderr)
        return 2
    groups = None
    if args.part is not None:
        groups = parse_part(args.part)
        if groups is None:
            print(f"check_hook_gates: --part needs one of {', '.join(PARTS)}, got {args.part!r}", file=sys.stderr)
            return 2
    if args.only is not None:
        groups = parse_only(args.only)
        if groups is None:
            print(f"check_hook_gates: --only needs known groups, got {args.only!r}; "
                  f"known: {', '.join(GROUPS)}", file=sys.stderr)
            return 2
    # `--selftest` is accepted for symmetry with every other check here, and bare invocation does
    # the same thing: the mutation harness runs a separate selftest file with no arguments, and a
    # script that printed usage there would be INERT -- every mutation "caught" by an exit 2.
    return selftest(groups, args.match, args.fail_fast)


if __name__ == "__main__":
    sys.exit(main())
