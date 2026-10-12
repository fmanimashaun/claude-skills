#!/usr/bin/env python3
"""Selftest: pipeline-status.sh (SessionStart) finds the repository's pipeline files from any directory inside it (#1946).

The hook tested `[ -f pipeline.yml ]` and `[ -f qa/CERTIFICATION ]` against the working directory, so a session started in a subdirectory printed nothing: no post-merge QA-verify nudge, no
"dev is certified" line, exit 0. Every positive row here runs the REAL hook through a real bash in a real repository, from the root and from a subdirectory, and looks at what it printed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_git  # noqa: E402  (#1588: a fixture's git touches only its own temp repo)

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "scripts" / "pipeline-status.sh"
FAILURES: list[str] = []
CHECKS = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILURES.append(f"{label}: {detail}")


def run_hook(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", "-p", str(HOOK)], cwd=cwd, env=fixture_git.hermetic(), capture_output=True, text=True, timeout=60)


def build(base: Path, with_pipeline: bool = True) -> tuple[Path, str]:
    repo = base / "repo"
    fixture_git.init(repo, "-b", "main")
    (repo / "a.txt").write_text("one\n")
    if with_pipeline:
        (repo / "pipeline.yml").write_text("stages: []\n")
    fixture_git.run(repo, "add", "--", "a.txt", *(["pipeline.yml"] if with_pipeline else []))
    fixture_git.run(repo, "commit", "-q", "-m", "init")
    head = fixture_git.run(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "sub" / "deeper").mkdir(parents=True)
    return repo, head


def main() -> int:
    with TemporaryDirectory(prefix="pipeline-status-") as td:
        base = Path(td)
        repo, head = build(base)
        git_dir = Path(fixture_git.run(repo, "rev-parse", "--absolute-git-dir").stdout.strip())
        (git_dir / "pipeline-pending").write_text("QA verify pending after merge abc123\n")
        for where, cwd in (("the root", repo), ("a subdirectory", repo / "sub"), ("a nested subdirectory", repo / "sub" / "deeper")):
            r = run_hook(cwd)
            check(f"pipeline-status: the post-merge nudge is printed from {where}", r.returncode == 0 and "pipeline: QA verify pending after merge abc123" in r.stdout, f"rc {r.returncode}, out {r.stdout[:120]!r}")
        # The certified line reads qa/CERTIFICATION and origin/dev, also from the top level.
        (repo / "qa").mkdir()
        (repo / "qa" / "CERTIFICATION").write_text(json.dumps({"sha": head}))
        fixture_git.run(repo, "update-ref", "refs/remotes/origin/dev", head)
        for where, cwd in (("the root", repo), ("a subdirectory", repo / "sub")):
            r = run_hook(cwd)
            check(f"pipeline-status: the 'dev is certified' line is printed from {where}", f"dev ({head[:12]}) certified" in r.stdout, f"out {r.stdout[:200]!r}")
    # Controls: a repository with no pipeline.yml says nothing, from anywhere; so does a directory that is no repository.
    with TemporaryDirectory(prefix="pipeline-status-") as td:
        base = Path(td)
        repo, _ = build(base, with_pipeline=False)
        git_dir = Path(fixture_git.run(repo, "rev-parse", "--absolute-git-dir").stdout.strip())
        (git_dir / "pipeline-pending").write_text("QA verify pending after merge abc123\n")
        for where, cwd in (("the root", repo), ("a subdirectory", repo / "sub")):
            r = run_hook(cwd)
            check(f"pipeline-status: CONTROL: a repository with no pipeline.yml prints nothing from {where}", r.returncode == 0 and r.stdout == "", f"rc {r.returncode}, out {r.stdout[:120]!r}")
    with TemporaryDirectory(prefix="pipeline-status-") as td:
        r = run_hook(Path(td))
        check("pipeline-status: CONTROL: a directory that is no repository prints nothing", r.returncode == 0 and r.stdout == "", f"rc {r.returncode}, out {r.stdout[:120]!r}")
    if FAILURES:
        print(f"pipeline-status selftest FAILED -- {len(FAILURES)} of {CHECKS} checks:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"pipeline-status selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
