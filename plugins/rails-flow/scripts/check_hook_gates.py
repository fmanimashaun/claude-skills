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
import subprocess
import sys
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks" / "scripts"

FAILURES: list[str] = []
CHECKS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILURES.append(f"{label}: {detail}" if detail else label)


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
        subprocess.run(cmd, cwd=root, check=True, capture_output=True)


def run_hook(name: str, *, cwd: Path, stdin: str, path_prefix: list[Path] = (),
             env_extra: dict[str, str] | None = None, unset: tuple[str, ...] = ()) -> tuple[int, str]:
    env = dict(os.environ)
    for k in unset:
        env.pop(k, None)
    env.pop("RAILS_FLOW_LANE", None)
    if path_prefix:
        env["PATH"] = os.pathsep.join(str(p) for p in path_prefix) + os.pathsep + env["PATH"]
    if env_extra:
        env.update(env_extra)
    done = subprocess.run(["bash", str(HOOKS / name)], cwd=cwd, input=stdin, env=env,
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


# ---- guard-bash.sh (#826) -----------------------------------------------------------------------
def guard_bash_fixtures() -> None:
    def run(cmd: str) -> int:
        with tempfile.TemporaryDirectory() as td:
            return run_hook("guard-bash.sh", cwd=Path(td),
                            stdin=json.dumps({"tool_input": {"command": cmd}}))[0]

    for cmd in ("git add -A", "git add .", "git add --all",
                # THE #826 SHAPES.
                "git add -v -A", "git add -vA", "git add ./", "git add :/", "git add -v ."):
        check(f"guard-bash: `{cmd}` is blocked", run(cmd) == 2, "exit 0")
    for cmd in ("git add app/models/user.rb", "git add -p app/models/user.rb", "git add ./app/x.rb",
                "git add spec/models/user_spec.rb spec/support/x.rb", "git status", "git add -v lib/a.rb"):
        check(f"guard-bash: `{cmd}` passes", run(cmd) == 0, "exit 2")


def selftest() -> int:
    for fn in (stop_gate_fixtures, guard_lane_fixtures, lint_ruby_fixtures,
               self_consistency_fixtures, guard_bash_fixtures):
        fn()
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
    ap.parse_args(argv)
    # `--selftest` is accepted for symmetry with every other check here, and bare invocation does
    # the same thing: the mutation harness runs a separate selftest file with no arguments, and a
    # script that printed usage there would be INERT -- every mutation "caught" by an exit 2.
    return selftest()


if __name__ == "__main__":
    sys.exit(main())
