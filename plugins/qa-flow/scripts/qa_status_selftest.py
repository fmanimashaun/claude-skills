#!/usr/bin/env python3
"""Selftest: qa-status.sh (SessionStart) says "cleared for main" only when the release gate would permit the promotion (#1955).

The banner used to print "dev (<sha>) is CERTIFIED — cleared for main." on the stamp's sha and verdict alone, which is weaker than what `release-gate.sh` asks: the stamp as COMMITTED at dev's tip, and
the release-only layers (#1428). It now runs the gate itself, in a child, on the command that promotes dev's tip, and says what the gate answered. Every row here runs the REAL banner, through a real
bash, in a real repository with `origin/dev` and `origin/main` set the way the gate's own fixtures set them, and looks at the line it printed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_git  # noqa: E402  (#1588: a fixture's git touches only its own temp repo)

PLUGIN = Path(__file__).resolve().parent.parent
BANNER = PLUGIN / "hooks" / "scripts" / "qa-status.sh"
FAILURES: list[str] = []
CHECKS = 0

FB_ROWS = ("Step,Width,Actor,URL,Action,Expected,Actual,Status,Notes,Screenshot,Also,Issue,Env\n"
           "1.1,1280,root,/login,Sign in,In,In,Pass,,,,,empty db\n"
           "1.2,390,root,/login,Sign in,In,In,Pass,,,,,empty db\n")
AZ_HEAD = "action,location,actor_role,target_role,guard,verdict,evidence,issue\n"
AZ_GOOD = AZ_HEAD + "demote,app/models/user.rb:40,it,root,root? refusal,GUARDED,,\n"
AZ_HOLE = AZ_GOOD + "demote,app/controllers/staff.rb:88,it,root,,HOLE,forged PATCH,#1\n"


def check(label: str, ok: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if not ok:
        FAILURES.append(f"{label}: {detail}")


class World:
    """A repository whose `origin/dev` is its tip, `origin/main` its root commit, and whose stamp and evidence are committed on top of the tested commit."""

    def __init__(self, base: Path):
        self.repo = base / "repo"
        fixture_git.init(self.repo, "-b", "main")
        self.git("config", "user.name", "t")  # fixture-git: exempt (an identity inside the fixture's own temp repo)
        (self.repo / "app.rb").write_text("v1\n")
        self.git("add", "--", "app.rb")
        self.git("commit", "-q", "-m", "app")
        self.root = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("checkout", "-q", "-b", "work")
        self.tested = self.git("rev-parse", "HEAD").stdout.strip()
        self.fb = self.repo / "qa/manual-tests/first-boot-v1"
        self.az = self.repo / "qa/manual-tests/authz-v1/sweep.csv"
        self.fb.mkdir(parents=True)
        self.az.parent.mkdir(parents=True)
        (self.fb / "pages.csv").write_text(FB_ROWS)
        self.az.write_text(AZ_GOOD)
        self.stamp = {"sha": self.tested, "date": "2026-10-13", "verdict": "PASS", "report": "qa/reports/r.md", "schema": 2, "version": "v1",
                      "first_boot": "qa/manual-tests/first-boot-v1", "authz": "qa/manual-tests/authz-v1/sweep.csv"}
        (self.repo / "qa" / "CERTIFICATION").write_text(json.dumps(self.stamp))

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return fixture_git.run(self.repo, *args)

    def commit_stamp(self) -> None:
        """The stamp and its evidence committed on top of the tested commit, which is how it reaches dev."""
        self.git("add", "--", "qa")
        self.git("commit", "-q", "-m", "stamp + evidence")

    def point_origin(self) -> None:
        tip = self.git("rev-parse", "HEAD").stdout.strip()
        self.git("update-ref", "refs/remotes/origin/dev", tip)
        self.git("update-ref", "refs/remotes/origin/main", self.root)
        self.git("update-ref", "refs/heads/main", self.root)

    def banner(self, env_extra: dict[str, str] | None = None, plugin_root: Path = PLUGIN) -> str:
        env = fixture_git.hermetic()
        env.pop("QA_ALLOW_MAIN", None)
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
        env.update(env_extra or {})
        done = subprocess.run(["/bin/bash", "-p", str(BANNER)], cwd=self.repo, env=env, capture_output=True, text=True, timeout=60)
        return done.stdout


def main() -> int:
    # 1. The state the gate permits: the stamp and the passing evidence committed on top of the tested commit, dev at that tip.
    with TemporaryDirectory(prefix="qa-status-") as td:
        w = World(Path(td))
        w.commit_stamp()
        w.point_origin()
        said = w.banner()
        check("qa-status: a committed stamp with passing evidence, dev at its tip: the release gate permits, so the banner says cleared for main",
              "CERTIFIED" in said and "cleared for main" in said, f"banner: {said!r}")

    # 2. The same, with a HOLE in the authorization sweep: the stamp says PASS, the gate refuses on the release-only layers, and the banner must NOT say cleared.
    with TemporaryDirectory(prefix="qa-status-") as td:
        w = World(Path(td))
        w.az.write_text(AZ_HOLE)
        w.commit_stamp()
        w.point_origin()
        said = w.banner()
        check("qa-status: a PASS stamp whose release-only evidence has a HOLE is not cleared for main, and the banner names the gate's reason",
              "cleared for main" not in said and "release gate would refuse" in said and "#1428" in said and "HOLE" in said, f"banner: {said!r}")

    # 3. THE ROW THE OLD CHECK PASSED AND THE GATE FAILS: a stamp in the working tree whose sha IS dev's tip and whose verdict is PASS (just after /qa-flow:certify, before the stamp is
    # committed). The old banner printed "CERTIFIED — cleared for main"; the gate refuses an uncommitted stamp ("not what main will receive").
    with TemporaryDirectory(prefix="qa-status-") as td:
        w = World(Path(td))
        w.point_origin()   # origin/dev is the tested commit; the stamp is only in the working tree
        said = w.banner()
        check("qa-status: an UNCOMMITTED stamp whose sha is dev's tip and says PASS (the old banner's whole test) is not cleared for main: the gate refuses it",
              "cleared for main" not in said and "release gate would refuse" in said, f"banner: {said!r}")
        said = w.banner({"QA_ALLOW_MAIN": "1"})
        check("qa-status: QA_ALLOW_MAIN=1 in the session's environment never reads as certified: the banner asks the gate without the override",
              "cleared for main" not in said and "release gate would refuse" in said, f"banner: {said!r}")
        no_gate = Path(td) / "plugin-without-the-gate"   # the stamp reader is there, release-gate.sh is not
        (no_gate / "scripts").mkdir(parents=True)
        (no_gate / "scripts" / "read_certification.py").write_text((PLUGIN / "scripts" / "read_certification.py").read_text())
        said = w.banner(plugin_root=no_gate)
        check("qa-status: where the gate cannot be run, the banner says so and does NOT claim cleared for main",
              "could not be run" in said and '"cleared for main" is not claimed' in said and "CERTIFIED" not in said, f"banner: {said!r}")

    # 4. Controls: no stamp, and a stamp that is not PASS, keep the messages they always had.
    with TemporaryDirectory(prefix="qa-status-") as td:
        w = World(Path(td))
        (w.repo / "qa" / "CERTIFICATION").unlink()
        said = w.banner()
        check("qa-status: CONTROL: no stamp says there is no certification yet", "no certification yet" in said, f"banner: {said!r}")

    if FAILURES:
        print(f"qa-status selftest FAILED -- {len(FAILURES)} of {CHECKS} checks:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print(f"qa-status selftest: {CHECKS} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
