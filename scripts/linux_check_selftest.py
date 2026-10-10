#!/usr/bin/env python3
"""Selftest for scripts/linux_check.sh (#1738): it fails closed without docker, and builds the container command it claims to.

Docker is NOT required: a stub `docker` (a shell script that records its arguments) stands in, named by LINUX_CHECK_DOCKER. What this
proves is the script's own logic: refusing when docker is absent or not running, validating names, the pinned image, the mount, the
commands handed to the container, and propagating the container's failure. That a real ubuntu:24.04 container runs the guards is
proven by running the script where docker runs.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "linux_check.sh"
FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if not ok:
        FAILURES.append(f"{label}{': ' + detail if detail else ''}")


def stub(directory: Path, *, info_rc: int = 0, run_rc: int = 0) -> Path:
    path = directory / "docker"
    path.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = info ]; then exit %d; fi\n'
        'if [ "$1" = run ]; then\n'
        '  printf "%%s\\0" "$@" > "%s/args.txt"\n'
        "  exit %d\n"
        "fi\n"
        "exit 99\n" % (info_rc, directory, run_rc), encoding="utf-8")
    path.chmod(0o755)
    return path


def run(*args: str, docker: str | Path, cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ, LINUX_CHECK_DOCKER=str(docker))
    env.pop("LINUX_CHECK_IMAGE", None)
    return subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, cwd=cwd, env=env, timeout=60)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        work = root / "work"
        work.mkdir()
        absent = root / "no-such-docker"

        r = run(docker=absent, cwd=work)
        check("no arguments is a usage error (exit 2)", r.returncode == 2 and "usage" in r.stderr, f"{r.returncode} {r.stderr}")

        r = run("some_guard", docker=absent, cwd=work)
        check("docker absent FAILS CLOSED: exit 2, says nothing ran and that it is not a pass",
              r.returncode == 2 and "FAILED CLOSED" in r.stderr and "not a pass" in r.stderr and "not installed" in r.stderr,
              f"{r.returncode} {r.stderr}")
        check("docker absent prints no pass line", "passed on Linux" not in r.stdout)

        (root / "a").mkdir()
        stub(root / "a", info_rc=1)
        r = run("some_guard", docker=root / "a" / "docker", cwd=work)
        check("docker installed but NOT RUNNING fails closed: exit 2 and says it is not running",
              r.returncode == 2 and "not running" in r.stderr and "FAILED CLOSED" in r.stderr, f"{r.returncode} {r.stderr}")
        check("docker not running never reaches `docker run`", not (root / "a" / "args.txt").exists())
        check("docker not running prints no pass line", "passed on Linux" not in r.stdout)

        for label, argv in (("a guard name with a shell metacharacter", ("good", "bad;rm")), ("an option it does not know", ("--bogus",)),
                            ("--run with no path", ("--run",)), ("a --run path with a space", ("--run", "a b.py")),
                            ("a --run path that looks like an option", ("--run", "-x"))):
            (root / "v").mkdir(exist_ok=True)
            stub(root / "v")
            r = run(*argv, docker=root / "v" / "docker", cwd=work)
            check(f"{label} is refused (exit 2) before docker is touched", r.returncode == 2 and not (root / "v" / "args.txt").exists(),
                  f"{r.returncode} {r.stderr}")

        (root / "ok").mkdir()
        stub(root / "ok")
        r = run("lint_self_consistency", "hook_guard_bash", "--run", "scripts/x_selftest.py", docker=root / "ok" / "docker", cwd=work)
        args = (root / "ok" / "args.txt").read_text(encoding="utf-8").split("\0")[:-1] if (root / "ok" / "args.txt").exists() else []
        check("a passing container exits 0 and says it passed on Linux", r.returncode == 0 and "passed on Linux" in r.stdout, f"{r.returncode} {r.stdout} {r.stderr}")
        check("docker is run with --rm", "--rm" in args, str(args))
        image = next((a for a in args if a.startswith("ubuntu:")), "")
        check("the image is pinned by a tag, never latest", image.startswith("ubuntu:") and image != "ubuntu:latest" and ":" in image and image[7:8].isdigit(), image)
        check("the repository is mounted at /work and is the working directory",
              any(a.endswith(":/work") and a.startswith(str(work.resolve())) or a.endswith(":/work") and a.startswith(str(work)) for a in args)
              and "/work" in args and "-w" in args, str(args))
        check("bytecode is not written into the mount", "PYTHONDONTWRITEBYTECODE=1" in args, str(args))
        check("every guard and selftest is handed to the container, in order",
              [a for a in args if a.startswith(("guard:", "run:"))] == ["guard:lint_self_consistency", "guard:hook_guard_bash", "run:scripts/x_selftest.py"], str(args))
        script_text = next((a for a in args if "mutation_check.py --guard" in a), "")
        check("the container installs python3, git and bash", "apt-get install" in script_text and "python3 git bash" in script_text)
        check("the container runs mutation_check.py --guard for a guard and python3 for a selftest",
              'scripts/mutation_check.py --guard "${spec#guard:}"' in script_text and 'python3 "${spec#run:}"' in script_text)
        check("a failing guard OR selftest in the container makes the container script exit non-zero",
              script_text.count("|| rc=1") == 2 and "exit $rc" in script_text)

        (root / "bad").mkdir()
        stub(root / "bad", run_rc=1)
        r = run("some_guard", docker=root / "bad" / "docker", cwd=work)
        check("a container that fails makes the script fail (exit 1) and say so, with no pass line",
              r.returncode == 1 and "FAILED on Linux" in r.stderr and "passed on Linux" not in r.stdout, f"{r.returncode} {r.stderr}")
        (root / "inst").mkdir()
        stub(root / "inst", run_rc=3)
        r = run("some_guard", docker=root / "inst" / "docker", cwd=work)
        check("the container's own exit status is the script's (3 stays 3)", r.returncode == 3, str(r.returncode))

        env = dict(os.environ, LINUX_CHECK_DOCKER=str(root / "ok" / "docker"), LINUX_CHECK_IMAGE="ubuntu:22.04")
        subprocess.run(["bash", str(SCRIPT), "g"], capture_output=True, text=True, cwd=work, env=env, timeout=60)
        overridden = (root / "ok" / "args.txt").read_text(encoding="utf-8") if (root / "ok" / "args.txt").exists() else ""
        check("LINUX_CHECK_IMAGE overrides the image", "ubuntu:22.04" in overridden)

    for failure in FAILURES:
        print(f"FAIL: {failure}")
    print(f"linux_check selftest: {'FAILED' if FAILURES else 'ok'} ({len(FAILURES)} failure(s))")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
