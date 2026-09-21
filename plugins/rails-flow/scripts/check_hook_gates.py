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
POSITIVES_906 = ['FOO=1 git add -A', 'sudo git add .', 'git status && git add -A', 'git -C repo add -A', 'git commit --no-verify -m x', 'bin/rails db:reset', 'git push --force origin main', 'git reset --hard HEAD~1']


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
    # FAIL CLOSED without the lib: a staged copy of the hook with lib/ removed must still block the raw text.
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / "hooks"; shutil.copytree(HOOKS, stage); shutil.rmtree(stage / "lib")
        payload = lambda c: json.dumps({"tool_input": {"command": c}})
        r1 = subprocess.run(["bash", str(stage / "guard-bash.sh")], input=payload("git add -A"), capture_output=True, text=True, cwd=td)
        r2 = subprocess.run(["bash", str(stage / "guard-bash.sh")], input=payload("git -C repo add -A"), capture_output=True, text=True, cwd=td)
        check("guard-bash (#906): with lib/ missing the hook falls back to the raw text and still blocks `git add -A`", r1.returncode == 2)
        check("guard-bash (#906): ...and the fallback is honestly the OLD behaviour (git -C slips through), which is why the lib ships in the plugin", r2.returncode == 0)


# ---- guard-claims.sh (#1106) --------------------------------------------------------------------
# `claim-verifier` exists, works, covers "any number: counts, ratios, versions, timings", and is
# named in /maintainer-work -- and it was skipped for a whole working day while two wrong numbers
# reached merged PR bodies. The capability was never the gap; remembering to use it was. So the
# check runs whether or not anyone remembers, and these fixtures drive BOTH directions, because a
# guard that blocks everything is as useless as one that blocks nothing.


def guard_claims_fixtures() -> None:
    def run(cmd: str, body: str | None = None, env_extra=None) -> int:
        with tempfile.TemporaryDirectory() as td:
            if body is not None:
                (Path(td) / "body.md").write_text(body, encoding="utf-8")
                cmd = cmd.replace("BODY", str(Path(td) / "body.md"))
            return run_hook("guard-claims.sh", cwd=Path(td),
                            stdin=json.dumps({"tool_input": {"command": cmd}}),
                            env_extra={"CLAUDE_PLUGIN_ROOT": str(HOOKS.parents[1]),
                                       **(env_extra or {})})[0]

    NUMERIC = "The selftest reports **292 assertions**, up from 285.\n"
    CHECKED = NUMERIC + "Verified against the v1.134.0 tag.\n"
    PROSE = "Tidy up the wording in the README.\n"

    # MUST BLOCK: the exact shape that shipped wrong, twice, on the day this was written.
    check("guard-claims: an unchecked numeric claim in a PR body is blocked",
          run("gh pr create --base dev --body-file BODY", NUMERIC) == 2, "exit 0")

    # MUST PASS -- and these are the half that keeps the guard alive. A hook that blocked every
    # `gh pr create` would be switched off within a day, and then nothing is checked at all.
    check("guard-claims: the same claim passes once the body shows it was verified",
          run("gh pr create --base dev --body-file BODY", CHECKED) == 0, "exit 2")
    check("guard-claims: a PR body with no load-bearing claim passes",
          run("gh pr create --base dev --body-file BODY", PROSE) == 0, "exit 2")
    # OUT OF SCOPE, AND THE BODY MUST CARRY A CLAIM. A first draft passed a claim-FREE body here,
    # so these could not reach the check at all: deleting the `gh pr create` scope test left them
    # green, and the mutation SURVIVED. A control that cannot reach the code it guards proves
    # nothing. With a numeric body, any widening of the scope fails right here.
    for cmd in ("git status", "gh pr view 42", "gh pr merge 42 --merge",
                "gh issue create --title x --body-file BODY",
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

    def run(cmd: str, marketplace: bool = False) -> int:
        with tempfile.TemporaryDirectory() as td:
            _git_repo(Path(td))
            if marketplace:
                # What MAKES a tree a marketplace. No consumer project has one.
                (Path(td) / ".claude-plugin").mkdir(parents=True, exist_ok=True)
                (Path(td) / ".claude-plugin" / "marketplace.json").write_text(
                    '{"name": "x", "plugins": []}', encoding="utf-8")
            env = dict(os.environ); env.pop("QA_ALLOW_MAIN", None); env["CLAUDE_PLUGIN_ROOT"] = str(QA_HOOK.parents[2])
            done = subprocess.run(["bash", str(QA_HOOK)], cwd=td, input=json.dumps({"tool_input": {"command": cmd}}),
                                  env=env, capture_output=True, text=True, timeout=60)
            return done.returncode

    for cmd in ("git push origin main", "FOO=1 git push origin main", "git -C repo push origin main", "git status; git push origin main"):
        check(f"release-gate: `{cmd}` targets main and is blocked without a certification", run(cmd) == 2, "exit 0")
    for cmd in ('git commit -m "push origin main"', 'echo "git push origin main"', "# git push origin main", "git push origin feature/x"):
        check(f"release-gate: `{cmd}` does not target main and passes", run(cmd) == 0, "exit 2")

    # THE DISCRIMINATING PAIR for the marketplace carve-out. The same command, the same absence of
    # a certification, and the ONLY difference is `.claude-plugin/marketplace.json`. Without the
    # first case the gate denies every promotion of its own source repo, which is a gate wrong
    # about correct code; without the second, the carve-out would be indistinguishable from
    # exempting any project that never ran `/qa-flow:setup-qa` -- which is most of them.
    check("release-gate: the marketplace's OWN repo is not a consumer, so promotion passes",
          run("git push origin main", marketplace=True) == 0, "exit 2")
    check("release-gate: an ordinary repo with no certification is STILL blocked",
          run("git push origin main") == 2, "exit 0")


def selftest() -> int:
    for fn in (stop_gate_fixtures, guard_lane_fixtures, lint_ruby_fixtures,
               self_consistency_fixtures, guard_bash_fixtures, guard_claims_fixtures,
               release_gate_fixtures):
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
