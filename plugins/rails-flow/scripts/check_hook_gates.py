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
import shutil
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
            done = subprocess.run([str(only / "bash"), str(HOOKS / "guard-migrate.sh")], cwd=proj,
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
    if legacy.is_file() and subprocess.run([str(legacy), "-c", "echo ${BASH_VERSINFO[0]}"],
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

    # #906: MATCH THE INVOKED COMMAND, NOT ANY SUBSTRING. Every negative here merely MENTIONS the rule;
    # every positive stages everything behind a prefix the old adjacency match could not see.
    for cmd in NEGATIVES_906:
        check(f"guard-bash (#906): `{cmd[:50]}` only mentions the rule and passes", run(cmd) == 0, "exit 2")
    for cmd in POSITIVES_906:
        check(f"guard-bash (#906): `{cmd}` is blocked", run(cmd) == 2, "exit 0")
    for cmd in NEGATIVES_1342:
        check(f"guard-bash (#1342): safe twin `{cmd[:60]}` stays allowed", run(cmd) == 0, "exit 2")
    # FAIL CLOSED without the lib: a staged copy of the hook with lib/ removed must still block the raw text.
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / "hooks"; shutil.copytree(HOOKS, stage); shutil.rmtree(stage / "lib")
        payload = lambda c: json.dumps({"tool_input": {"command": c}})
        r1 = subprocess.run(["bash", str(stage / "guard-bash.sh")], input=payload("git add -A"), capture_output=True, text=True, cwd=td)
        r2 = subprocess.run(["bash", str(stage / "guard-bash.sh")], input=payload("git -C repo add -A"), capture_output=True, text=True, cwd=td)
        check("guard-bash (#906): with lib/ missing the hook falls back to the raw text and still blocks `git add -A`", r1.returncode == 2)
        check("guard-bash (#906): ...and the fallback is honestly the OLD behaviour (git -C slips through), which is why the lib ships in the plugin", r2.returncode == 0)

    # #1311: an issue filed from the shell is labelled against the project's declared groups, or refused.
    groups = {"groups": [{"one_of": ["bug", "feature", "enhancement"]},
                         {"when": "bug", "one_of": ["severity:s1", "severity:s2"]}]}
    def labelled(cmd: str, *, declare: bool = True, drop_helper: bool = False) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            if declare:
                (Path(td) / ".rails-flow").mkdir()
                (Path(td) / ".rails-flow" / "issue-labels.json").write_text(json.dumps(groups), encoding="utf-8")
            hook = HOOKS / "guard-bash.sh"
            if drop_helper:
                stage = Path(td) / "hooks"; shutil.copytree(HOOKS, stage); (stage / "lib" / "issue_labels.py").unlink()
                hook = stage / "guard-bash.sh"
            r = subprocess.run(["bash", str(hook)], input=json.dumps({"tool_input": {"command": cmd}}),
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
        subprocess.run(["git", "init", "-q", str(session)], check=True)
        subprocess.run(["git", "-C", str(session), "remote", "add", "origin", "https://github.com/me/session.git"], check=True)
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        subprocess.run(["git", "-C", str(other), "remote", "add", "origin", "https://github.com/other/repo.git"], check=True)
        def cross(cmd: str) -> tuple[int, str]:
            r = subprocess.run(["bash", str(HOOKS / "guard-bash.sh")], input=json.dumps({"tool_input": {"command": cmd}}),
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
    check("guard-bash (#1423): CONTROL: an echo of the text is allowed through the real hook",
          labelled('echo "gh issue create"')[0] == 0)
    rc, err = labelled("gh issue create -t X --label feature", drop_helper=True)
    check("guard-bash (#1311): FAIL CLOSED: with the helper missing, a labelled create is refused, not let through",
          rc == 2 and "could not run" in err, err)


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
            env.pop("GH_REPO", None)
            broke = subprocess.run(["bash", str(copy / "guard-claims.sh")], cwd=td, env=env, text=True,
                                   capture_output=True, timeout=60,
                                   input=json.dumps({"tool_input": {"command": f"gh pr create --base dev --body-file {td}/body.md"}}))
    check("guard-claims: a helper that fails at import is BLOCKED, never let through",
          broke.returncode == 2 and "died before judging" in broke.stdout + broke.stderr,
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
                subprocess.run(["git", *args], cwd=root, capture_output=True)
            target.write_text("x\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=root, capture_output=True)
            subprocess.run(["git", "-c", "user.email=f@e", "-c", "user.name=f",
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

    # FAILS OPEN when it cannot read the body. This guard's job is to make the check happen where
    # it can, never to block opening a PR because a path could not be resolved.
    check("guard-claims: an unreadable body file fails OPEN rather than blocking",
          run("gh pr create --base dev --body-file /nonexistent/body.md") == 0, "exit 2")
    check("guard-claims: an inline --body fails open too",
          run('gh pr create --base dev --body "292 assertions, up from 285"') == 0, "exit 2")


# ---- release-gate.sh (qa-flow) shares the normaliser: drive it too, or the "one normaliser" claim is prose (#906) ----
QA_HOOK = HOOKS.parents[2] / "qa-flow" / "hooks" / "scripts" / "release-gate.sh"


def release_gate_fixtures() -> None:
    if not QA_HOOK.is_file():
        check("release-gate.sh present beside rails-flow", False, str(QA_HOOK))
        return

    def run(cmd: str, marketplace: bool = False, plugin_root: Path | None = None) -> int:
        with tempfile.TemporaryDirectory() as td:
            _git_repo(Path(td))
            # ON A FEATURE BRANCH (#1410). `git init` leaves HEAD on main, where a bare `git push`
            # really IS a push to main -- so a parser handed the quote-stripped `git push origin `
            # was still blocked, and the fixture could not tell it from one reading the real argument.
            subprocess.run(["git", "checkout", "-q", "-b", "feature/work"], cwd=td, check=True,
                           capture_output=True)
            if marketplace:
                # What MAKES a tree a marketplace. No consumer project has one.
                (Path(td) / ".claude-plugin").mkdir(parents=True, exist_ok=True)
                (Path(td) / ".claude-plugin" / "marketplace.json").write_text(
                    '{"name": "x", "plugins": []}', encoding="utf-8")
            env = dict(os.environ); env.pop("QA_ALLOW_MAIN", None); env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root or QA_HOOK.parents[2])
            done = subprocess.run(["bash", str(QA_HOOK)], cwd=td, input=json.dumps({"tool_input": {"command": cmd}}),
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

    # THE DISCRIMINATING PAIR for the marketplace carve-out. The same command, the same absence of
    # a certification, and the ONLY difference is `.claude-plugin/marketplace.json`. Without the
    # first case the gate denies every promotion of its own source repo, which is a gate wrong
    # about correct code; without the second, the carve-out would be indistinguishable from
    # exempting any project that never ran `/qa-flow:setup-qa` -- which is most of them.
    check("release-gate: the marketplace's OWN repo is not a consumer, so promotion passes",
          run("git push origin main", marketplace=True) == 0, "exit 2")
    check("release-gate: an ordinary repo with no certification is STILL blocked",
          run("git push origin main") == 2, "exit 0")

    # #1337. The stamp is bound to the tested dev sha; committing it to dev by PR moves dev. The gate
    # accepts an ANCESTOR of dev only when the delta since is the stamp itself.
    g = ["git", "-c", "user.email=t@t", "-c", "user.name=t"]
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        _git_repo(repo)
        sh = lambda *a: subprocess.run([*g, *a], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
        (repo / "app.rb").write_text("v1\n", encoding="utf-8")
        sh("add", "app.rb"); sh("commit", "-q", "-m", "app")
        tested = sh("rev-parse", "HEAD")
        (repo / "qa").mkdir()
        stamp = {"sha": tested, "date": "2026-09-26", "verdict": "PASS", "report": "qa/reports/r.md"}
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps(stamp), encoding="utf-8")
        env = dict(os.environ); env.pop("QA_ALLOW_MAIN", None); env["CLAUDE_PLUGIN_ROOT"] = str(QA_HOOK.parents[2])

        def gate() -> tuple[int, str]:
            sh("branch", "-f", "dev", "HEAD")
            done = subprocess.run(["bash", str(QA_HOOK)], cwd=repo, env=env, capture_output=True, text=True, timeout=60,
                                  input=json.dumps({"tool_input": {"command": "git push origin main"}}))
            return done.returncode, done.stderr

        rc, err = gate()
        check("release-gate (#1337): CONTROL: an uncommitted stamp for dev's tip permits", rc == 0, err)
        sh("add", "qa/CERTIFICATION"); sh("commit", "-q", "-m", "stamp")
        rc, err = gate()
        check("release-gate (#1337): the stamp committed on top of the tested sha still permits", rc == 0, err)
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
        rc, err = gate()
        check("release-gate (#1337): a stamp for a sha that is not an ancestor of dev is denied",
              rc == 2 and "dev moved" in err, err)


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
        done = subprocess.run([str(bare / "bash"), str(HOOKS / "ci-verdict-hint.sh")], cwd=proj,
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


def selftest() -> int:
    for fn in (stop_gate_fixtures, guard_lane_fixtures, guard_migrate_fixtures, lint_ruby_fixtures,
               self_consistency_fixtures, guard_bash_fixtures, guard_claims_fixtures,
               release_gate_fixtures, ci_verdict_hint_fixtures):
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
