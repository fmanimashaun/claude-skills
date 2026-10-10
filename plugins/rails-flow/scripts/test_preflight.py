#!/usr/bin/env python3
"""Say what is wrong with the machine BEFORE a test suite is read as having failed (#1561, #1566).

Run:  python3 test_preflight.py < hook-payload.json            # what the hook does
      python3 test_preflight.py --command "bundle exec rspec spec/a_spec.rb" [--cwd DIR]
      python3 test_preflight.py --selftest

WHY THIS EXISTS. A usage-insights report on 36 sessions (2026-10-03; counts are model-estimated, used to rank
only) found the same four environment faults reading as test failures: Postgres down mid-suite, a held
`bundler.lock`, an overloaded machine, a spec path that did not exist. Each costs a diagnosis of the wrong
thing: a red suite that was never the code's fault. Nothing checked the environment first; this is the generic
layer a plugin can own. A project's own preflight (its master key, its seeded database) stays the project's and
runs AFTER this one, through one hook point, so there is one entry and one wording.

WHAT IT CHECKS, on a command that runs a test suite (rspec, `rails test`, `rake test`, Playwright, `bin/e2e`,
`bin/ci`), and on nothing else:

  1. POSTGRES, only when the project's database is detected (`config/database.yml` names a Postgres adapter, or
     `DATABASE_URL` does). `pg_isready` says no -> the fix is printed. It is NEVER restarted unless
     `RAILS_FLOW_PREFLIGHT_RESTART=1` AND `pg_start` in YOUR `~/.claude/rails-flow-preflight.json` names the
     command to run: this script cannot know how Postgres is installed on a machine, so it will not guess a
     command and run it.
  2. A HELD `bundler.lock`. Bundler's `ProcessLock` takes an exclusive `flock` on `<bundle_path>/bundler.lock`
     for the length of `bundle install` and `bundle pristine` (bundler/process_lock.rb, installer.rb); a Ruby LSP
     `bundle update` is the usual holder. MEASURED on this machine: a non-blocking shared `flock` from Python
     reads HELD while a Ruby process holds the exclusive lock, and `lsof` names the holder, so the probe takes
     no lock it keeps and writes nothing.
  3. LOAD. The 1-minute load average above `RAILS_FLOW_PREFLIGHT_LOAD_MAX` (default: twice the core count) ->
     run in the foreground or in smaller shards, not several background runs.
  4. SPEC PATHS. Every spec path the command names exists (`rspec` and `rails test` only: a Playwright path is
     relative to a directory this script cannot know).
  5. THE PROJECT'S HOOK POINT: an executable `.claude/test-preflight` in the project is run after the generic
     checks and its output is added, but ONLY once you have pinned it (see below). Its exit status is ignored (this
     is advisory) and it is cut off at `RAILS_FLOW_PREFLIGHT_PROJECT_TIMEOUT` seconds (default 10).

NOTHING A REPOSITORY CONTROLS IS EVER EXECUTED BY DEFAULT. A PreToolUse hook runs BEFORE the user is asked about
the command, so a script the hook ran from the checkout would run on a command the user may then refuse: clone a
repository, ask for its tests, and its `.claude/test-preflight` has already run. A security review of this very
change found that. So a project's script runs only if its SHA-256 is pinned in the user's own
`~/.claude/rails-flow-preflight.json` (written by `test_preflight.py --trust`, after reading the file); editing the
script un-pins it; an unpinned one is NAMED in the output and not run. The restart command lives in the same
user-level file for the same reason: the environment can be set by a project's settings, a file under HOME cannot.

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
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
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


CONFIG_RELATIVE = Path(".claude") / "rails-flow-preflight.json"


def config_path(env) -> Path:
    """The USER's file. Under HOME, never under the project: a repository must not be able to supply a command or a pin."""
    return Path(str(env.get("HOME") or os.path.expanduser("~"))) / CONFIG_RELATIVE


def load_config(env) -> dict:
    try:
        data = json.loads(config_path(env).read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def sha256_of(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def pin_trust(root: Path, env) -> str:
    """Pin the project's `.claude/test-preflight` by its SHA-256 in the user's file. The only way a project script becomes runnable."""
    hook = root / ".claude" / "test-preflight"
    digest = sha256_of(hook) if hook.is_file() else None
    if digest is None:
        return f"nothing to trust: {hook} is not a readable file"
    config = load_config(env)
    trusted = config.get("trusted") if isinstance(config.get("trusted"), dict) else {}
    trusted[os.path.realpath(hook)] = digest
    config["trusted"] = trusted
    target = config_path(env)
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = target.with_suffix(".tmp")
    scratch.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    os.chmod(scratch, 0o600)
    os.replace(scratch, target)
    return f"trusted {os.path.realpath(hook)} (sha256 {digest}) in {target}"


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
    binary = shutil.which("pg_isready", path=env.get("PATH"))
    if binary is None:
        return []
    probe = run_quiet([binary, *pg_args(env)], env)
    if probe is None or probe.returncode == 0:
        return []
    said = (probe.stdout or probe.stderr).strip().splitlines()[:1]
    head = f"Postgres is not accepting connections (`pg_isready`: {said[0] if said else 'no answer'}, exit {probe.returncode})."
    if str(env.get("RAILS_FLOW_PREFLIGHT_RESTART", "")) == "1":
        command = str(load_config(env).get("pg_start", "")).strip()
        if not command:
            return [head + f" RAILS_FLOW_PREFLIGHT_RESTART=1 is set but `pg_start` in {config_path(env)} names no command, so nothing was started."]
        run_quiet(["bash", "-c", command], env, timeout=20)
        again = run_quiet([binary, *pg_args(env)], env)
        if again is not None and again.returncode == 0:
            return [head + " Ran your `pg_start` and `pg_isready` now answers."]
        return [head + " Ran your `pg_start` and it still does not answer."]
    return [head + " Start it and re-run the suite (for example `brew services start postgresql@<version>` on macOS, "
            "`sudo systemctl start postgresql` on Linux); this hook never starts it unless RAILS_FLOW_PREFLIGHT_RESTART=1 "
            "and `pg_start` in ~/.claude/rails-flow-preflight.json name how."]


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


def lock_holder(path: Path, env) -> str:
    lsof = shutil.which("lsof", path=env.get("PATH"))
    if lsof is None:
        return "holder not identified (`lsof` is not installed)"
    listed = run_quiet([lsof, "-t", "--", str(path)], env)
    pids = [p for p in (listed.stdout.split() if listed else []) if p.isdigit() and int(p) != os.getpid()]
    if not pids:
        return "holder not identified"
    ps = run_quiet(["ps", "-o", "pid=,command=", "-p", ",".join(pids)], env)
    lines = [ln.strip() for ln in (ps.stdout.splitlines() if ps else []) if ln.strip()]
    return "held by " + "; ".join(ln[:90] for ln in lines[:2]) if lines else "held by pid " + ", ".join(pids)


def check_bundler_lock(root: Path, env) -> list[str]:
    out: list[str] = []
    for path in bundler_lock_candidates(root, env):
        if lock_is_held(path):
            out.append(f"`{path}` is locked ({lock_holder(path, env)}): a `bundle` command that has to install will wait on it. "
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


def check_project_hook(root: Path, env) -> list[str]:
    hook = root / ".claude" / "test-preflight"
    try:
        if not (hook.is_file() and hook.stat().st_mode & stat.S_IXUSR):
            return []
        seconds = float(env.get("RAILS_FLOW_PREFLIGHT_PROJECT_TIMEOUT") or 10)
    except (OSError, ValueError):
        return []
    trusted = load_config(env).get("trusted")
    if not isinstance(trusted, dict) or trusted.get(os.path.realpath(hook)) != sha256_of(hook):
        return ["`.claude/test-preflight` exists but is NOT pinned, so it was not run: a repository's own script must not run before you have read it. "
                f"Read it, then pin it with `python3 {Path(__file__).resolve()} --trust --cwd {root}` (any later edit un-pins it)."]
    try:
        done = subprocess.run([str(hook)], cwd=str(root), env=dict(env), capture_output=True, text=True, timeout=seconds, check=False)
    except subprocess.TimeoutExpired:
        return [f"The project's preflight (`.claude/test-preflight`) did not finish in {seconds:g}s and was skipped."]
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    text = (done.stdout or "").strip()
    return [f"Project preflight: {line.strip()}" for line in text.splitlines() if line.strip()][:3]


def findings_for(command: str, cwd: str, env=None, loadavg=os.getloadavg, cores=os.cpu_count) -> list[str]:
    """Every finding for one command, or [] to stay silent. The generic checks come first, the project's after."""
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
        out += check_project_hook(root, env)
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
        stub("pg_isready", "sleep 5")
        PROBE_SECONDS = 0.3
        started = time.monotonic()
        quiet = hook(rspec, root, env_for())[1]
        PROBE_SECONDS = 30.0
        check("a `pg_isready` that hangs is cut off at the deadline, and the hook is silent", quiet == "" and time.monotonic() - started < 10, f"{time.monotonic() - started:.1f}s {quiet[:60]!r}")
        stub("pg_isready", pg_down)

        # 1b. RESTART only behind the explicit flag, and only with the command the USER wrote in their own file under HOME.
        def write_config(**data) -> None:
            (tmp / ".claude").mkdir(exist_ok=True)
            (tmp / ".claude" / "rails-flow-preflight.json").write_text(json.dumps(data))

        witness.with_suffix(".started").unlink(missing_ok=True)
        stub("pg_isready", f"if [ -e {witness}.started ]; then echo ok; exit 0; fi; echo 'no response'; exit 2")
        write_config(pg_start=f"touch {witness}.started")
        hook(rspec, root, env_for())
        check("an outage with a start command configured but the flag OFF does not start anything", not witness.with_suffix(".started").exists())
        write_config()
        text, _ = hook(rspec, root, env_for(RAILS_FLOW_PREFLIGHT_RESTART="1"))
        check("the flag ON with no command says nothing was started, and starts nothing", "names no command" in text and not witness.with_suffix(".started").exists(), text[:160])
        hook(rspec, root, env_for(RAILS_FLOW_PREFLIGHT_RESTART="1", RAILS_FLOW_PREFLIGHT_PG_START=f"touch {witness}.started"))
        check("a start command supplied through the ENVIRONMENT is never run (a project's settings can set the environment)", not witness.with_suffix(".started").exists())
        write_config(pg_start=f"touch {witness}.started")
        text, _ = hook(rspec, root, env_for(RAILS_FLOW_PREFLIGHT_RESTART="1"))
        check("the flag ON with a command in the user's file runs exactly that command and re-checks", witness.with_suffix(".started").exists() and "now answers" in text, text[:160])
        (tmp / ".claude" / "rails-flow-preflight.json").unlink()
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
        check("a Playwright path is NOT checked (it is relative to a directory this cannot know)", hook("npx playwright test e2e/x.spec.ts", root, env_for())[1] == "")

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

        # 6. THE PROJECT'S HOOK POINT, after the generic checks, advisory in its own right, and run ONLY once the user has pinned it. A PreToolUse hook
        #    runs before the user is asked about the command, so a script it ran from a checkout would run on a command the user may refuse.
        stub("pg_isready", pg_down)
        (root / ".claude").mkdir()
        mine = root / ".claude" / "test-preflight"
        ran = witness.with_suffix(".ranproject")

        def project_script(body: str = "echo 'master key missing'") -> None:
            mine.write_text(f"#!/bin/sh\ntouch {ran}\n{body}\nexit 3\n")
            mine.chmod(0o755)

        project_script()
        text, _ = hook(rspec, root, env_for())
        check("a project's .claude/test-preflight that nobody pinned is NOT run: the hook names it and says how to pin it",
              not ran.exists() and "NOT pinned" in text and "--trust" in text, repr(text[:240]))
        check("...and its output never reaches the context", "master key missing" not in text)
        pinned = pin_trust(root, env_for())
        check("pinning records the file's SHA-256 in the user's own file, readable by the user alone", "sha256" in pinned and (tmp / ".claude" / "rails-flow-preflight.json").stat().st_mode & 0o077 == 0, pinned[:120])
        text, _ = hook(rspec, root, env_for())
        check("a PINNED .claude/test-preflight is run and its output added", ran.exists() and "Project preflight: master key missing" in text, repr(text[:200]))
        check("...AFTER the generic checks, so one entry and one order", text.find("Postgres") < text.find("Project preflight"), repr(text[:200]))
        ran.unlink()
        project_script("echo 'changed after it was read'")
        text, _ = hook(rspec, root, env_for())
        check("a pinned script that is edited afterwards is un-pinned: not run, and named again", not ran.exists() and "NOT pinned" in text, repr(text[:200]))
        check("--trust, the command a person runs after reading it, pins the current file end to end",
              subprocess.run([sys.executable, __file__, "--trust", "--cwd", str(root)], capture_output=True, text=True, env=env_for(), check=False).returncode == 0
              and "changed after it was read" in hook(rspec, root, env_for())[0])
        # THE ATTACK: a repository ships its own pin for its own script. The pin is read from the user's HOME only, so it is worth nothing.
        (tmp / "empty-home").mkdir(exist_ok=True)
        (root / ".claude" / "rails-flow-preflight.json").write_text(json.dumps({"trusted": {os.path.realpath(mine): sha256_of(mine)}}))
        ran.unlink(missing_ok=True)
        check("a pin that the REPOSITORY ships is not honoured: only the user's file under HOME pins a script",
              not ran.exists() and "NOT pinned" in hook(rspec, root, env_for(HOME=str(tmp / "empty-home")))[0] and not ran.exists())
        project_script("echo 'edited again, so it is unpinned'")     # unpinned AND not executable: only the executable check keeps it from being named
        mine.chmod(0o644)
        check("a non-executable one is ignored (neither run nor named)", "Project preflight" not in hook(rspec, root, env_for())[0] and "NOT pinned" not in hook(rspec, root, env_for())[0])
        project_script("sleep 5")
        pin_trust(root, env_for())
        text, _ = hook(rspec, root, env_for(RAILS_FLOW_PREFLIGHT_PROJECT_TIMEOUT="0.3"))
        check("one that hangs is cut off, said so, and does not hold the run", "did not finish in 0.3s" in text, repr(text[:200]))
        mine.write_text("#!/nonexistent/interpreter\n")
        mine.chmod(0o755)
        pin_trust(root, env_for())
        check("one that cannot run fails open (the generic findings still arrive)", "Postgres" in hook(rspec, root, env_for())[0])
        mine.unlink()
        check("nothing to pin is said plainly, not an error", "nothing to trust" in pin_trust(root, env_for()))

        # 7. ADVISORY: odd input is silence and the process still exits 0.
        for label, raw in (("not JSON", "not json"), ("a JSON list", "[]"), ("empty", ""), ("a non-Bash tool", json.dumps({"tool_name": "Read", "tool_input": {"command": rspec}})),
                           ("no command", json.dumps({"tool_name": "Bash", "tool_input": {}}))):
            check(f"{label} is silent", run(raw, env_for()) == "")
        check("an exception inside a check is silence, not a crash", run(json.dumps({"tool_name": "Bash", "tool_input": {"command": rspec}, "cwd": str(root)}), {"PATH": None}) == "")
        proc = subprocess.run([sys.executable, __file__], input=b"garbage \xff\xfe not text", capture_output=True, check=False)
        check("the entry point exits 0 on garbage that is not even text, and prints nothing", proc.returncode == 0 and proc.stdout == b"", repr((proc.returncode, proc.stdout, proc.stderr[:100])))
        # The caps, asked of `render` itself: no realistic command produces enough findings to reach them, so only oversized input can fail them.
        wide, tall = render([f"finding {i}" for i in range(50)]), render(["x" * 5000])
        check("the context is capped in lines and characters", wide.count("\n- ") + 1 <= MAX_LINES and len(tall) <= MAX_CHARS and "finding 49" not in wide, f"{wide.count(chr(10))} lines, {len(tall)} chars")

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
    parser.add_argument("--trust", action="store_true", help="pin the project's .claude/test-preflight (by SHA-256) so the hook may run it; read it first")
    parser.add_argument("--cwd", default=os.getcwd())
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.trust:
        print(pin_trust(project_root(args.cwd), os.environ))
        return 0
    if args.command is not None:
        findings = findings_for(args.command, args.cwd)
        print("\n".join(findings) if findings else "nothing to report")
        return 0
    try:
        sys.stdout.write(run(sys.stdin.read()))
    except Exception:  # noqa: BLE001 - advisory: always exit 0
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
