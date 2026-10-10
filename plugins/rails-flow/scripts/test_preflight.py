#!/usr/bin/env python3
"""Say what is wrong with the machine BEFORE a test suite is read as having failed (#1561, #1566).

Run:  python3 test_preflight.py < hook-payload.json            # what the hook does
      python3 test_preflight.py --command "bundle exec rspec spec/a_spec.rb" [--cwd DIR]
      python3 test_preflight.py --selftest

WHY THIS EXISTS. A usage-insights report on 36 sessions (2026-10-03; counts are model-estimated, used to rank
only) found the same four environment faults reading as test failures: Postgres down mid-suite, a held
`bundler.lock`, an overloaded machine, a spec path that did not exist. Each costs a diagnosis of the wrong
thing: a red suite that was never the code's fault. Nothing checked the environment first; this is the generic
layer a plugin can own. A project's own preflight (its master key, its seeded database) stays the project's, and the
project runs it itself, before the suite: this hook runs no script or command line that a repository or the environment supplies (below).

WHAT IT CHECKS, on a command that runs a test suite (rspec, `rails test`, `rake test`, Playwright, `bin/e2e`,
`bin/ci`), and on nothing else:

  1. POSTGRES, only when the project's database is detected (`config/database.yml` names a Postgres adapter, or
     `DATABASE_URL` does). `pg_isready` says no -> the fix is printed. This hook only REPORTS: it never starts Postgres.
  2. A HELD `bundler.lock`. Bundler's `ProcessLock` takes an exclusive `flock` on `<bundle_path>/bundler.lock`
     for the length of `bundle install` and `bundle pristine` (bundler/process_lock.rb, installer.rb); a Ruby LSP
     `bundle update` is the usual holder. MEASURED on this machine: a non-blocking shared `flock` from Python
     reads HELD while a Ruby process holds the exclusive lock, and `lsof` names the holder, so the probe takes
     no lock it keeps and writes nothing.
  3. LOAD. The 1-minute load average above `RAILS_FLOW_PREFLIGHT_LOAD_MAX` (default: twice the core count) ->
     run in the foreground or in smaller shards, not several background runs.
  4. SPEC PATHS. Every spec path the command names exists (`rspec` and `rails test` only: a Playwright path is
     relative to a directory this script cannot know).

WHAT IT NEVER DOES: RUN A SCRIPT OR COMMAND LINE THAT A REPOSITORY OR THE ENVIRONMENT SUPPLIES. A PreToolUse hook runs BEFORE the user
is asked about the command, so whatever it executes runs on a command the user may then refuse. Two automatic security
reviews flagged the first version of this change for exactly that (a project's `.claude/test-preflight` run from the
checkout, and a restart command read from the environment); both features were REMOVED, not hardened (#1821 keeps the
designs and the threat analysis). What it does run is three fixed system tools, `pg_isready`, `lsof` and `ps`, found only in
ABSOLUTE `PATH` entries outside the project (`trusted_which`): a `.`, an empty entry or `./bin` resolves into the checkout, and a
`pg_isready` shipped there would be repository code run before the user is asked. NOT closable here, and the same for
every plugin hook: anything that can set the environment before the hook starts beats this script (`PATH` itself, which still
chooses WHICH `pg_isready` runs and cannot be narrowed to world-writable directories only without more code, `PYTHONPATH`,
`LD_PRELOAD`, `CLAUDE_PLUGIN_ROOT`), which is a harness and workspace-trust question; and `DATABASE_URL` makes
`pg_isready` contact the host it names (a connection, not code execution).

CLASSIFIED under `docs/doctrine/harness-doctrine.md` section 10:
  * TIER 3 (deterministic) for the DETECTION: the same environment gives the same finding, whatever the model.
  * ADVISORY, so it FAILS OPEN and ALWAYS exits 0 (section 5): a missing `pg_isready`, `lsof` or `python3`, an
    unreadable payload or any error here is silence. A nudge that can stop work is a nudge people uninstall.
  * DELIVERY IS ADVICE, NOT A GUARANTEE. Claude Code documents a PreToolUse hook's `additionalContext` as
    "added to Claude's context alongside the tool result", and says plain stdout from a PreToolUse hook is NOT
    shown to the model. So this emits JSON, and the line reaches the model WITH the suite's output: it helps
    read a failure that the environment caused, and it cannot stop the run. Making it stop the run would make
    it a gate, a different classification with a fail-closed contract (and a named override) this does not claim.
"""
from __future__ import annotations

import argparse
import fcntl
import glob
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Anything that takes longer than this on one external command is skipped (silence, never an accusation), never
# waited for: the hook runs before EVERY matching command and its time is the user's. `pg_isready` waits up to 3 s
# on its own and says "no response" when it gives up, so this is its own limit plus slack. Read at CALL time, so a
# selftest on a loaded machine can raise it without a first `exec` of a fresh stub reading as a hung probe.
PROBE_SECONDS = 5.0
MAX_LINES = 6
MAX_CHARS = 1500

# Options whose NEXT token is a value, not a path (`-o "--tag ~serial"`, `--format progress`). A value that looks
# like a path (`-r spec/support/x`) must not be mistaken for a spec path.
VALUE_OPTIONS = {
    "-o", "--out", "-f", "--format", "-t", "--tag", "-r", "--require", "-e", "--example", "--seed", "-n",
    "--only-group", "--runtime-log", "--exclude-pattern", "--pattern", "--default-path", "--order",
    "--test-options", "--group-by", "-p", "--profile", "--name", "-b",
}
WRAPPERS = {"env", "time", "nice", "exec", "command", "npx", "xvfb-run"}
ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
PG_ADAPTER = re.compile(r"adapter:\s*[\"']?(?:postgres|postgresql|postgis)\b", re.I)


def segments(command: str) -> list[list[str]]:
    """The command split into simple commands on `;` `&&` `||` `|` and newlines. An unbalanced quote yields
    nothing: a command this cannot read is a command this stays silent on."""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return []
    out: list[list[str]] = []
    current: list[str] = []
    for token in tokens:
        if token and all(c in "();<>|&" for c in token):
            if current:
                out.append(current)
            current = []
        else:
            current.append(token)
    if current:
        out.append(current)
    return out


def runner(segment: list[str]) -> tuple[str, list[str]] | None:
    """(kind, arguments) when this simple command RUNS a test suite, else None. Command position only: the word
    `rspec` inside `git commit -m "fix rspec"` or `grep rspec Gemfile` is not a suite run."""
    tokens = list(segment)
    while tokens:
        head = tokens[0]
        if ENV_ASSIGNMENT.match(head) or head in WRAPPERS:
            tokens = tokens[1:]
        elif head == "bundle" and tokens[1:2] == ["exec"]:
            tokens = tokens[2:]
        elif head in ("pnpm", "yarn") and tokens[1:2] == ["exec"]:
            tokens = tokens[2:]
        else:
            break
    if not tokens:
        return None
    program, args = os.path.basename(tokens[0]), tokens[1:]
    if program in ("rspec", "parallel_rspec", "parallel-rspec"):
        return "rspec", args
    if program == "rails" and args[:1] and args[0] in ("test", "spec"):
        return "rails-test", args[1:]
    if program == "rake" and args[:1] and re.match(r"^(?:test|spec)\b", args[0]):
        return "rake", args[1:]
    if program == "playwright" and args[:1] == ["test"]:
        return "e2e", args[1:]
    if program == "cypress" and args[:1] == ["run"]:
        return "e2e", args[1:]
    if program == "e2e" and "bin/e2e" in tokens[0]:
        return "e2e", args
    if program == "ci" and "bin/ci" in tokens[0]:
        return "ci", args
    return None


def spec_paths(args: list[str]) -> list[str]:
    """The paths a rspec / rails-test command names: `file.rb:12`, `file.rb[1:2]` and a directory all count; options,
    their values and anything with a glob character do not."""
    found: list[str] = []
    skip = False
    for token in args:
        if skip:
            skip = False
            continue
        if token.startswith("-"):
            skip = token in VALUE_OPTIONS
            continue
        if any(c in token for c in "*?{}$`"):
            continue
        path = re.sub(r"\[[\d:, ]+\]$", "", re.sub(r"(?::\d+)+$", "", token))
        if path.endswith(("_spec.rb", "_test.rb")) or path.startswith(("spec/", "test/")) or path in ("spec", "test"):
            found.append(path)
    return found


def project_root(cwd: str) -> Path:
    """The nearest directory at or above `cwd` holding a Gemfile, else `cwd`."""
    here = Path(cwd)
    for candidate in (here, *list(here.parents)[:6]):
        if (candidate / "Gemfile").exists():
            return candidate
    return here


def database_detected(root: Path, env) -> bool:
    if str(env.get("DATABASE_URL", "")).startswith(("postgres://", "postgresql://", "postgis://")):
        return True
    try:
        return bool(PG_ADAPTER.search((root / "config" / "database.yml").read_text(errors="replace")))
    except OSError:
        return False


def trusted_which(name: str, env, root: Path) -> str | None:
    """`shutil.which` minus the ways a repository reaches PATH: only ABSOLUTE entries, and none at or inside the project. A `.`, an
    empty entry or `./bin` resolves into the checkout, so a `pg_isready` shipped there would be repository code run before the user is asked."""
    base = os.path.realpath(root)
    for entry in str(env.get("PATH") or "").split(os.pathsep):
        if not entry or not os.path.isabs(entry):
            continue
        real = os.path.realpath(entry)
        if real == base or real.startswith(base + os.sep):
            continue
        candidate = os.path.join(entry, name)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def run_quiet(argv: list[str], env, timeout: float | None = None) -> subprocess.CompletedProcess | None:
    """One external command with a deadline; None when it cannot run or does not finish. Never raises."""
    try:
        return subprocess.run(argv, env=dict(env), capture_output=True, text=True,
                              timeout=PROBE_SECONDS if timeout is None else timeout, check=False)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def pg_args(env) -> list[str]:
    """`-h`/`-p` from DATABASE_URL, never the URL itself: a password on a command line shows in `ps`."""
    url = str(env.get("DATABASE_URL", ""))
    if not url.startswith(("postgres://", "postgresql://", "postgis://")):
        return []
    match = re.match(r"^[a-z]+://(?:[^@/]*@)?(\[[^\]]+\]|[^:/?#]+)(?::(\d+))?", url)
    if not match:
        return []
    args = ["-h", match.group(1).strip("[]")]
    if match.group(2):
        args += ["-p", match.group(2)]
    return args


def check_postgres(root: Path, env) -> list[str]:
    if not database_detected(root, env):
        return []
    binary = trusted_which("pg_isready", env, root)
    if binary is None:
        return []
    probe = run_quiet([binary, *pg_args(env)], env)
    if probe is None or probe.returncode == 0:
        return []
    said = (probe.stdout or probe.stderr).strip().splitlines()[:1]
    head = f"Postgres is not accepting connections (`pg_isready`: {said[0] if said else 'no answer'}, exit {probe.returncode})."
    return [head + " Start it and re-run the suite (for example `brew services start postgresql@<version>` on macOS, "
            "`sudo systemctl start postgresql` on Linux); this hook only reports, it never starts it."]


def bundler_lock_candidates(root: Path, env) -> list[Path]:
    """Where Bundler's lock can be, without starting Ruby: `<bundle_path>/bundler.lock`, and bundle_path is
    BUNDLE_PATH (+ a `ruby/<abi>` scope), the project's `.bundle/config`, or the Ruby's own gem directory."""
    found: list[str] = []
    bundle_paths = [str(env.get("BUNDLE_PATH", ""))]
    try:
        for line in (root / ".bundle" / "config").read_text(errors="replace").splitlines():
            if line.startswith("BUNDLE_PATH:"):
                bundle_paths.append(line.split(":", 1)[1].strip().strip("\"'"))
    except OSError:
        pass
    bundle_paths.append(str(root / "vendor" / "bundle"))
    for base in bundle_paths:
        if base:
            base = base if os.path.isabs(base) else str(root / base)
            found += glob.glob(os.path.join(base, "bundler.lock")) + glob.glob(os.path.join(base, "ruby", "*", "bundler.lock"))
    if env.get("GEM_HOME"):
        found.append(os.path.join(str(env["GEM_HOME"]), "bundler.lock"))
    ruby = shutil.which("ruby", path=env.get("PATH"))
    if ruby:
        prefix = Path(os.path.realpath(ruby)).parent.parent
        found += glob.glob(str(prefix / "lib" / "ruby" / "gems" / "*" / "bundler.lock"))
    seen: dict[str, Path] = {}
    for path in found:
        if os.path.isfile(path):
            seen.setdefault(os.path.realpath(path), Path(path))
    return list(seen.values())


def lock_is_held(path: Path) -> bool:
    """True when another process holds an exclusive `flock` on `path`. A shared, non-blocking attempt on a read-only
    descriptor: it keeps nothing and writes nothing."""
    try:
        with open(path, "rb") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
            except (BlockingIOError, PermissionError):
                return True
            fcntl.flock(handle, fcntl.LOCK_UN)
    except OSError:
        return False
    return False


def lock_holder(path: Path, env, root: Path) -> str:
    lsof = trusted_which("lsof", env, root)
    if lsof is None:
        return "holder not identified (`lsof` is not installed)"
    listed = run_quiet([lsof, "-t", "--", str(path)], env)
    pids = [p for p in (listed.stdout.split() if listed else []) if p.isdigit() and int(p) != os.getpid()]
    if not pids:
        return "holder not identified"
    ps_binary = trusted_which("ps", env, root)
    ps = run_quiet([ps_binary, "-o", "pid=,command=", "-p", ",".join(pids)], env) if ps_binary else None
    lines = [ln.strip() for ln in (ps.stdout.splitlines() if ps else []) if ln.strip()]
    return "held by " + "; ".join(ln[:90] for ln in lines[:2]) if lines else "held by pid " + ", ".join(pids)


def check_bundler_lock(root: Path, env) -> list[str]:
    out: list[str] = []
    for path in bundler_lock_candidates(root, env):
        if lock_is_held(path):
            out.append(f"`{path}` is locked ({lock_holder(path, env, root)}): a `bundle` command that has to install will wait on it. "
                       "Let that finish, or stop it, before the suite.")
    return out[:1]


def check_load(env, loadavg=os.getloadavg, cores=os.cpu_count) -> list[str]:
    try:
        load = loadavg()[0]
        count = cores() or 1
    except (OSError, AttributeError):
        return []
    try:
        limit = float(env.get("RAILS_FLOW_PREFLIGHT_LOAD_MAX") or 2 * count)
    except ValueError:
        limit = 2.0 * count
    if load <= limit:
        return []
    return [f"The 1-minute load is {load:.1f} on {count} cores (advisory threshold {limit:g}). Run the suite in the foreground or in smaller "
            "shards rather than several background runs, and read a timeout in a browser spec as the machine until it is shown otherwise."]


def check_spec_paths(kind: str, args: list[str], cwd: str) -> list[str]:
    if kind not in ("rspec", "rails-test"):
        return []
    missing = [p for p in spec_paths(args) if not os.path.exists(p if os.path.isabs(p) else os.path.join(cwd, p))]
    if not missing:
        return []
    names = ", ".join(f"`{p}`" for p in missing[:5]) + (f" and {len(missing) - 5} more" if len(missing) > 5 else "")
    return [f"Spec path(s) that do not exist: {names}. The run will report \"no examples\" or a load error, which is the path, not the code."]


def findings_for(command: str, cwd: str, env=None, loadavg=os.getloadavg, cores=os.cpu_count) -> list[str]:
    """Every finding for one command, or [] to stay silent."""
    env = os.environ if env is None else env
    for segment in segments(command):
        found = runner(segment)
        if found is None:
            continue
        kind, args = found
        root = project_root(cwd)
        out: list[str] = []
        out += check_postgres(root, env)
        out += check_bundler_lock(root, env)
        out += check_load(env, loadavg, cores)
        out += check_spec_paths(kind, args, cwd)
        return out
    return []


def render(findings: list[str]) -> str:
    lines = findings[:MAX_LINES]
    text = "Test-run preflight (advisory; the run is not stopped):\n- " + "\n- ".join(lines)
    return text if len(text) <= MAX_CHARS else text[: MAX_CHARS - 1] + "…"


def run(raw: str, env=None, loadavg=os.getloadavg, cores=os.cpu_count) -> str:
    """Hook stdout for one payload: the JSON context object, or nothing. Any failure here is nothing."""
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("tool_name") not in (None, "Bash"):
            return ""
        tool_input = payload.get("tool_input")
        command = str(tool_input.get("command", "")) if isinstance(tool_input, dict) else ""
        cwd = str(payload.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
        findings = findings_for(command, cwd, env, loadavg, cores) if command else []
    except Exception:  # noqa: BLE001 - an advisory that raises takes the tool call down with it
        return ""
    if not findings:
        return ""
    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": render(findings)}})


def selftest() -> int:
    global PROBE_SECONDS
    saved_probe, PROBE_SECONDS = PROBE_SECONDS, 30.0   # a loaded machine must not turn the first exec of a stub into a "hung probe"
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{('  ' + detail) if detail else ''}")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        bindir = tmp / "bin"
        bindir.mkdir()
        witness = tmp / "witness"

        def stub(name: str, body: str) -> None:
            path = bindir / name
            path.write_text("#!/bin/sh\n" + body + "\n")
            path.chmod(0o755)

        def env_for(**extra: str) -> dict:
            return {"PATH": f"{bindir}:/usr/bin:/bin", "HOME": td, **extra}

        def project(name: str, database: str | None = "postgresql") -> Path:
            root = tmp / name
            (root / "config").mkdir(parents=True)
            (root / "spec").mkdir()
            (root / "Gemfile").write_text("source 'https://rubygems.org'\n")
            (root / "spec" / "a_spec.rb").write_text("")
            if database:
                (root / "config" / "database.yml").write_text(f"default: &default\n  adapter: {database}\n")
            return root

        def hook(command: str, root: Path, env: dict, load: float = 0.1) -> tuple[str, str]:
            """(additionalContext or '', raw stdout) of the real entry point for a Bash payload."""
            raw = run(json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(root)}),
                      env, loadavg=lambda: (load, load, load), cores=lambda: 4)
            try:
                return json.loads(raw)["hookSpecificOutput"]["additionalContext"], raw
            except (ValueError, KeyError):
                return "", raw

        pg_down = "echo \"$@\" > " + str(witness) + ".pgargs; echo '/tmp:5432 - no response'; exit 2"
        stub("pg_isready", pg_down)
        root = project("app")
        rspec = "bundle exec rspec spec/a_spec.rb"

        # 1. POSTGRES. The outage is simulated by a stub `pg_isready` with the exit status the real one uses.
        text, raw = hook(rspec, root, env_for())
        check("a Postgres outage before an rspec run is named, with its exit status", "Postgres is not accepting connections" in text and "exit 2" in text, repr(text[:160]))
        check("...as PreToolUse additionalContext, the channel documented as reaching the model", '"hookEventName": "PreToolUse"' in raw and "additionalContext" in raw, raw[:100])
        check("...and it never decides a permission: the advisory cannot block or allow a call", "permissionDecision" not in raw)
        check("...and says it never starts Postgres by itself", "never starts it" in text)
        stub("pg_isready", "echo '/tmp:5432 - accepting connections'; exit 0")
        check("CONTROL: Postgres up is silent", hook(rspec, root, env_for())[1] == "")
        stub("pg_isready", pg_down)
        witness.with_suffix(".pgargs").unlink(missing_ok=True)
        check("a project whose adapter is sqlite3 is not probed at all (dormant without Postgres)", hook(rspec, project("lite", "sqlite3"), env_for())[1] == "" and not witness.with_suffix(".pgargs").exists())
        check("a project with no database config is not probed at all", hook(rspec, project("nodb", None), env_for())[1] == "" and not witness.with_suffix(".pgargs").exists())
        check("DATABASE_URL naming Postgres counts as detected", "Postgres is not accepting" in hook(rspec, project("urlonly", None), env_for(DATABASE_URL="postgres://u:secret@db.internal:5544/app"))[0])
        args = witness.with_suffix(".pgargs").read_text() if witness.with_suffix(".pgargs").exists() else ""
        check("...and pg_isready got -h/-p, never the URL with its password", "-h db.internal" in args and "-p 5544" in args and "secret" not in args, args)
        (bindir / "pg_isready").unlink()
        check("no `pg_isready` on PATH fails open: silent", hook(rspec, root, env_for())[1] == "")
        stub("pg_isready", pg_down)
        # A probe that hangs is cut off at the deadline and is SILENCE: an unanswered `pg_isready` is not evidence that Postgres is down.
        stub("pg_isready", "sleep 5; exit 2")
        PROBE_SECONDS = 0.3
        started = time.monotonic()
        quiet = hook(rspec, root, env_for())[1]
        PROBE_SECONDS = 30.0
        check("a `pg_isready` that hangs is cut off at the deadline, and the hook is silent", quiet == "" and time.monotonic() - started < 3, f"{time.monotonic() - started:.1f}s {quiet[:60]!r}")
        stub("pg_isready", pg_down)

        # 1b. PROGRAMS ARE LOOKED UP ONLY WHERE A REPOSITORY CANNOT REACH: absolute PATH entries outside the project. A `pg_isready` shipped in the
        #     checkout would otherwise be repository code run before the user is asked about the command.
        repo_ran = witness.with_suffix(".reporan")
        repo_bin = root / "bin"
        repo_bin.mkdir(exist_ok=True)
        (repo_bin / "pg_isready").write_text(f"#!/bin/sh\ntouch {repo_ran}\nexit 2\n")
        (repo_bin / "pg_isready").chmod(0o755)
        stub("pg_isready", "exit 0")                                      # the TRUSTED one says Postgres is up, so a correct hook is silent
        _, raw = hook(rspec, root, env_for(PATH=f"{repo_bin}:{bindir}:/usr/bin:/bin"))
        check("a pg_isready the repository ships inside its own tree is never run, even FIRST on PATH", not repo_ran.exists() and raw == "", raw[:100])
        previous = os.getcwd()
        os.chdir(root)
        try:
            _, raw = hook(rspec, root, env_for(PATH=f"bin::.:{bindir}:/usr/bin:/bin"))
        finally:
            os.chdir(previous)
        check("a pg_isready reachable through a RELATIVE or EMPTY PATH entry is never run", not repo_ran.exists() and raw == "", raw[:100])
        elsewhere = tmp / "elsewhere"
        (elsewhere / "bin").mkdir(parents=True)
        (elsewhere / "bin" / "pg_isready").write_text(f"#!/bin/sh\ntouch {repo_ran}\nexit 2\n")
        (elsewhere / "bin" / "pg_isready").chmod(0o755)
        os.chdir(elsewhere)
        try:
            _, raw = hook(rspec, root, env_for(PATH=f"bin:{bindir}:/usr/bin:/bin"))
        finally:
            os.chdir(previous)
        check("a RELATIVE PATH entry is never searched, wherever the process happens to be (only the absolute-path rule stops this one)", not repo_ran.exists() and raw == "", raw[:100])
        stub("pg_isready", pg_down)

        # 2. A HELD bundler.lock: a real flock held by a real child, a stub `lsof` naming it.
        lock_dir = root / "vendor" / "bundle" / "ruby" / "4.0.0"
        lock_dir.mkdir(parents=True)
        lock = lock_dir / "bundler.lock"
        lock.write_text("")
        stub("pg_isready", "exit 0")
        holder = subprocess.Popen([sys.executable, "-c",
                                   "import fcntl,sys,time\nf=open(sys.argv[1],'w+')\nfcntl.flock(f,fcntl.LOCK_EX)\nprint('held',flush=True)\ntime.sleep(60)", str(lock)],
                                  stdout=subprocess.PIPE, text=True)
        try:
            ready = holder.stdout.readline().strip() if holder.stdout else ""
            stub("lsof", f"echo {holder.pid}")
            text, _ = hook(rspec, root, env_for())
            check("a bundler.lock held by another process is named, with its holder", ready == "held" and "is locked" in text and "held by" in text and str(holder.pid) in text, repr(text[:200]))
            (bindir / "lsof").unlink()
            text, _ = hook(rspec, root, env_for(PATH=f"{bindir}:/usr/bin:/bin".replace(":/usr/bin:/bin", ":/nonexistent")))
            check("...with no `lsof` it still reports the lock as held and says the holder is unknown", "is locked" in text and "not identified" in text, repr(text[:200]))
        finally:
            holder.kill()
            holder.wait()
        check("CONTROL: the same lock file, no longer held, is silent", hook(rspec, root, env_for())[1] == "")
        before = lock.stat().st_mtime_ns
        hook(rspec, root, env_for())
        check("the probe writes nothing to the lock it inspects", lock.stat().st_mtime_ns == before and lock.read_text() == "")

        # 3. LOAD.
        check("a load above the threshold advises foreground or smaller shards", "smaller shards" in hook(rspec, root, env_for(), load=40.0)[0])
        check("CONTROL: a load under the threshold is silent", hook(rspec, root, env_for(), load=3.0)[1] == "")
        check("RAILS_FLOW_PREFLIGHT_LOAD_MAX moves the threshold both ways", "load is 6.0" in hook(rspec, root, env_for(RAILS_FLOW_PREFLIGHT_LOAD_MAX="5"), load=6.0)[0] and hook(rspec, root, env_for(RAILS_FLOW_PREFLIGHT_LOAD_MAX="50"), load=40.0)[1] == "")
        check("a threshold that is not a number falls back to the default, not an error", "smaller shards" in hook(rspec, root, env_for(RAILS_FLOW_PREFLIGHT_LOAD_MAX="lots"), load=40.0)[0])

        # 4. SPEC PATHS.
        text, _ = hook("bundle exec rspec spec/missing_spec.rb spec/a_spec.rb", root, env_for())
        check("a spec path that does not exist is named, and one that does is not", "`spec/missing_spec.rb`" in text and "a_spec.rb`" not in text, repr(text[:200]))
        check("CONTROL: a path with :line and an [example id] that exists is silent", hook("rspec spec/a_spec.rb:12 spec/a_spec.rb[1:2]", root, env_for())[1] == "")
        check("an option's value that looks like a path is not a spec path", hook("rspec -r spec/support/nope.rb --format progress spec/a_spec.rb", root, env_for())[1] == "")
        check("a glob is not checked", hook("rspec 'spec/**/*_spec.rb'", root, env_for())[1] == "")
        check("`rails test` paths are checked too", "test/models/x_test.rb" in hook("bin/rails test test/models/x_test.rb", root, env_for())[0])
        # EVERY COMMAND THE DOCS NAME is read as a suite run, by kind, and a near miss of each is not (a coverage gap otherwise: only three kinds were exercised).
        for command, kind in (("bundle exec rspec spec/a_spec.rb", "rspec"), ("bin/parallel-rspec 6", "rspec"), ("parallel_rspec -n 4 spec", "rspec"),
                              ("bin/rails test", "rails-test"), ("bundle exec rake spec", "rake"), ("rake test:models", "rake"),
                              ("npx playwright test", "e2e"), ("cypress run", "e2e"), ("bin/e2e e2e/x.spec.ts", "e2e"), ("RAILS_ENV=test bin/ci", "ci")):
            found = runner(segments(command)[0])
            check(f"`{command}` is read as a {kind} suite run", found is not None and found[0] == kind, repr(found))
        for command in ("rake db:migrate", "bin/rails server", "bin/rails db:reset", "playwright install", "cypress open", "gh ci status", "bin/ci-docker"):
            check(f"`{command}` is not a suite run", runner(segments(command)[0]) is None, repr(runner(segments(command)[0])))
        check("a Playwright path is NOT checked (it is relative to a directory this cannot know)", hook("npx playwright test test/e2e/x.spec.ts", root, env_for())[1] == "")

        # 5. WHAT IT IS ABOUT: a suite run, in command position, and nothing else.
        for label, command in (("a commit message that says rspec", 'git commit -m "fix rspec spec/missing_spec.rb"'),
                               ("grep for rspec", "grep -rn rspec spec/missing_spec.rb"),
                               ("an echo of the command", "echo bundle exec rspec spec/missing_spec.rb"),
                               ("a `gh pr create` whose body mentions rspec", 'gh pr create --body "ran rspec spec/missing_spec.rb"'),
                               ("a command that merely names a spec path", "cat spec/missing_spec.rb")):
            check(f"{label} is silent", hook(command, root, env_for())[1] == "")
        check("an unbalanced quote reads as no command at all, not as an error", segments('rspec "spec/missing_spec.rb') == [])
        for label, command in (("a compound command", "cd /tmp && bundle exec rspec spec/missing_spec.rb"),
                               ("env assignments first", "RAILS_ENV=test CI=true bin/rspec spec/missing_spec.rb"),
                               ("a pipe", "rspec spec/missing_spec.rb | tail -5")):
            check(f"{label} is still read as a suite run", "do not exist" in hook(command, root, env_for())[0])

        # 6. ADVISORY: odd input is silence and the process still exits 0.
        for label, raw in (("not JSON", "not json"), ("a JSON list", "[]"), ("empty", ""), ("a non-Bash tool", json.dumps({"tool_name": "Read", "tool_input": {"command": rspec}})),
                           ("no command", json.dumps({"tool_name": "Bash", "tool_input": {}}))):
            check(f"{label} is silent", run(raw, env_for()) == "")
        # A check that really raises (a RuntimeError: unlike bad JSON, nothing narrower than the blanket guard in run() catches it).
        def a_check_fails() -> tuple[float, float, float]:
            raise RuntimeError("a check failed")

        try:
            guarded = run(json.dumps({"tool_name": "Bash", "tool_input": {"command": rspec}, "cwd": str(root)}), env_for(), loadavg=a_check_fails)
        except Exception as exc:  # noqa: BLE001 - the guard under test is gone: report it under this check's own name, not as a traceback
            guarded = f"raised {exc!r}"
        check("an exception inside a check is silence, not a crash", guarded == "", guarded[:100])
        proc = subprocess.run([sys.executable, __file__], input=b"garbage \xff\xfe not text", capture_output=True, check=False)
        check("the entry point exits 0 on garbage that is not even text, and prints nothing", proc.returncode == 0 and proc.stdout == b"", repr((proc.returncode, proc.stdout, proc.stderr[:100])))
        # The caps, asked of `render` itself: no realistic command produces enough findings to reach them, so only oversized input can fail them.
        wide, tall = render([f"finding {i}" for i in range(50)]), render(["x" * 5000])
        check("the context is capped in lines and characters", wide.count("\n- ") <= MAX_LINES and len(tall) <= MAX_CHARS and "finding 49" not in wide, f"{wide.count(chr(10))} lines, {len(tall)} chars")

    PROBE_SECONDS = saved_probe
    if failures:
        print(f"selftest FAILED: {len(failures)} of {checks}", file=sys.stderr)
        for line in failures:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"selftest ok: {checks} checks")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--command", help="run the checks for this command by hand and print them")
    parser.add_argument("--cwd", default=os.getcwd())
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.command is not None:
        findings = findings_for(args.command, args.cwd)
        print("\n".join(findings) if findings else "nothing to report")
        return 0
    # BYTES, decoded with `replace`: input that is not text cannot raise here, so the entry point needs no guard of its own and still always exits 0.
    sys.stdout.write(run(sys.stdin.buffer.read().decode("utf-8", "replace")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
