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
import tempfile
import time
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks" / "scripts"

FAILURES: list[str] = []
CHECKS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILURES.append(f"{label}: {detail}" if detail else label)


# #1469: every hook fixture runs through here. A subprocess that outruns its timeout used to raise
# TimeoutExpired and CRASH this script, so the fixtures after it never printed. Under the mutation
# harness's parallel load that read as "caught, but not by the expected fixture" on one run in a few:
# a flake with nothing wrong in the code. Now a timeout is exit 124 with a TIMEOUT line, the fixture
# that ran it fails by name, and every later fixture still runs. HOOK_GATES_TIMEOUT overrides the
# bound (the selftest sets it tiny to prove the no-crash path).
_EXPECTING_TIMEOUT = False      # set by timeout_fixtures, which times out on purpose, and the #1504 cost check


def _run(*args, **kw):
    # The override is exact (the no-crash proof sets it tiny); otherwise a fixture's own bound is
    # raised to a 180s floor, since 60s was what a loaded machine outran. Read per call, not at import.
    override = os.environ.get("HOOK_GATES_TIMEOUT")
    limit = float(override) if override else max(float(kw.pop("timeout", 0) or 0), 180.0)
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
            note = f"TIMEOUT after {limit}s: {proc.args}"
            # A timeout is ALWAYS a recorded failure -- a setup step (`git init`, check=True) that
            # times out must not pass silently -- unless timeout_fixtures asked for one on purpose.
            if not _EXPECTING_TIMEOUT:
                check(note, False)
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
  "api graphql") case "$*" in
      *"on Ref"*) [ -z "${FAKE_REF:-}" ] || printf '%s %s' "$FAKE_REF" "${FAKE_PRREPO:-o/r}" ;;
      *) [ -z "${FAKE_NODE:-}" ] || printf '%s %s' "$FAKE_NODE" "${FAKE_PRREPO:-o/r}" ;;
    esac; exit 0 ;;
  "release view") printf '%s' "${FAKE_RELVIEW:-}"; exit 0 ;;
  "api repos"*) printf '%s' "${FAKE_RELID:-}"; exit 0 ;;
esac
exit 1
"""


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
    ref="${ep##*ref=}"
    [ -n "${FAKE_STAMP_REF:-}" ] && [ "$ref" = "$FAKE_STAMP_REF" ] && [ -f "${FAKE_STAMP_FILE:-/nonexistent}" ] && { cat "$FAKE_STAMP_FILE"; exit 0; }
    exit 1 ;;
  repos/*/compare/*) [ -n "${FAKE_COMPARE:-}" ] || exit 1; printf '%s\\n' "$FAKE_COMPARE"; exit 0 ;;
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


def release_gate_repos_fixtures() -> None:
    g = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        _git_repo(repo)
        sh = lambda *a, **kw: _run([*g, *a], cwd=repo, check=True, capture_output=True, text=True, **kw).stdout.strip()
        old = {**os.environ, "GIT_COMMITTER_DATE": "2026-09-01T00:00:00+00:00", "GIT_AUTHOR_DATE": "2026-09-01T00:00:00+00:00"}
        bare = Path(td) / "origin.git"
        _run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
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
    src = Path(__file__).read_text(encoding="utf-8")
    raw = src.count("subprocess" + ".run(")
    check("every subprocess in this suite goes through the no-crash wrapper", raw == 0,
          f"{raw} direct subprocess.run call(s); every one must go through _run")


# One fixture group per hook. `--only` runs a subset (#1497): twelve mutation guards use this file
# as their selftest, each mutating ONE hook, and every mutant re-ran all ten groups -- about 70% of
# the mutation-coverage budget. A guard now names the groups that drive its hook; the doctor's
# `hook gates` gate and the harness's own guard still run every group.
# ---- the wall-clock deadline (#1575) ---------------------------------------------------------------
# A hook that outlives its timeout blocks every Bash call, and Claude Code's timeout stops WAITING without
# killing the hook's descendants: orphaned awk processes ran 51 minutes, one 23 hours, and the load hit 348.
# `lib/deadline.sh` runs each hook's work in its own process group under a wall-clock deadline and kills the whole
# group. The stub below is the incident: an `awk` that hangs and leaves a sleeper behind, every pid recorded.
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
                ("a push whose verb or remote is disguised but whose destination is still named",
                 ("git -c alias.p=push p origin HEAD:main", "git -c url.b.insteadOf=a push origin main")),
            ):
                for cmd in cmds:
                    check(f"deadline (#1575): the coarse detector refuses {what}: `{cmd}`", coarse(cmd) == 2, "exit 0: allowed")
            # THE CONTROLS: refusing everything would pass every example above. `-f query=@x` is a LITERAL string in gh (only
            # `-F` reads a file) and the full path allows it too; `--tags` pushes no branch; a branch NAMED heads/... or
            # feature/main-menu is not main.
            for cmd in ("git push origin feature/x", "git push origin HEAD:heads/feature/x", "git push origin HEAD:heads/feature/main-menu",
                        "git push origin heads/feature/x", "git push --tags origin", "git status", "git commit -m tidy",
                        "gh workflow list", "gh workflow view release.yml", "gh run list", "gh pr view 7", "gh pr list",
                        "gh api repos/o/r/pulls", "gh api graphql -f query='{ viewer { login } }'",
                        "gh api graphql -f query=@q.graphql", "gh api graphql --raw-field query=@-", "git push -u origin fix/1010-one-main"):
                check(f"deadline (#1575): CONTROL: the coarse detector allows `{cmd}`", coarse(cmd) == 0, "exit 2: refused")
        for cmd in ("git push origin HEAD:heads/main", "git push --all"):
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
    "guard_claims": guard_claims_fixtures, "release_gate": release_gate_fixtures,
    "release_gate_effects": release_gate_effects_fixtures, "release_gate_repos": release_gate_repos_fixtures,
    "release_gate_refs": release_gate_refs_fixtures,
    "ci_verdict_hint": ci_verdict_hint_fixtures, "timeout": timeout_fixtures,
    "deadline": deadline_fixtures,
}


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


def selftest(groups: list[str] | None = None) -> int:
    # --only REFUSES what it cannot run (#1497), checked on every run whatever the selection: a
    # silently empty selection is how a mutant would "survive" with no fixture ever consulted.
    for bad in ("nope", "", ",", "release_gate,nope", "release_gate,", " release_gate", "timeout,timeout"):
        check(f"--only {bad!r} is refused (exit 2), never an empty pass", parse_only(bad) is None,
              repr(parse_only(bad)))
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
    run_groups(groups, GROUPS)
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
    args = ap.parse_args(argv)
    groups = None
    if args.only is not None:
        groups = parse_only(args.only)
        if groups is None:
            print(f"check_hook_gates: --only needs known groups, got {args.only!r}; "
                  f"known: {', '.join(GROUPS)}", file=sys.stderr)
            return 2
    # `--selftest` is accepted for symmetry with every other check here, and bare invocation does
    # the same thing: the mutation harness runs a separate selftest file with no arguments, and a
    # script that printed usage there would be INERT -- every mutation "caught" by an exit 2.
    return selftest(groups)


if __name__ == "__main__":
    sys.exit(main())
