#!/usr/bin/env python3
"""The brain must be refreshed once per release: refuse an arm or a promotion while STATUS.md predates it (#2297).

Run:  python3 check_brain_fresh.py [--root DIR] [--when always|arm] [--base REF]
      python3 check_brain_fresh.py --selftest

WHY THIS EXISTS. The SessionStart nudge "brain-review due since 2026-10-04" printed for 18 days and nothing
acted on it; `docs/brain/STATUS.md` was last touched on 2026-09-27 while seven owner rulings lived only in one
session's private memory. A nudge is not enforcement. This is the enforcement, scoped to where it must hold:
the release. A release is the one moment a project says "this is the state of the world", so the brain that
describes the world may not be older than the last time the world was released.

THE RULE. `STATUS.md` carries `_Updated: <date> · sha <commit> (<branch>)`. That commit's date must not be
older than the newest `v*` tag's commit date (the last promotion). STATUS shas are dev commits and `main` is
never merged back into `dev`, so ancestry cannot be the test; a date can. A project with no `v*` tag has
promoted nothing, so nothing is stale.

WHEN IT FIRES. `--when always` judges every time (the release-manager's precondition and the promotion
proof). `--when arm` judges only on an arm or promotion (a branch named `chore/arm-*` or `release/*`, or a
diff that adds a `(release vX.Y.Z)` heading to CHANGELOG.md) and otherwise exits 3, "not an arm", which
project_gates reports as not applicable. That is the only exit 3 here.

CANNOT TELL IS A REFUSAL (exit 1, named), not a pass: no STATUS.md, a `_Updated:` line that does not parse,
a sha this clone does not have, or a shallow clone (its tags and history are not all there). A check that
passes when it could not read its input is the defect this repository warns about most.

Exit: 0 fresh (or nothing promoted yet) · 1 stale or cannot tell · 3 `--when arm` and this is not an arm.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

STATUS = Path("docs") / "brain" / "STATUS.md"
UPDATED = re.compile(r"_Updated:\s*(\d{4}-\d{2}-\d{2})\s*·\s*sha\s+([0-9a-f]{7,40})\b")
ARM_BRANCH = re.compile(r"^(chore/arm-|release/)")
RELEASE_HEADING = re.compile(r"^\+###\s.*\(release v\d")


def git(root: Path, *args: str) -> tuple[int, str]:
    r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def commit_time(root: Path, ref: str) -> tuple[int, str] | None:
    """`(epoch seconds, ISO date)` of a commit, or None. The EPOCH is what is compared: two ISO strings carry their own
    UTC offsets, and `10:00+05:00` sorts after `08:00+00:00` as text though it is three hours EARLIER (#2303 review)."""
    rc, out = git(root, "log", "-1", "--format=%ct %cI", ref)
    parts = out.split()
    if rc != 0 or len(parts) != 2 or not parts[0].isdigit():
        return None
    return int(parts[0]), parts[1]


def is_arm(root: Path, base: str) -> bool:
    branch = os.environ.get("GITHUB_HEAD_REF") or git(root, "rev-parse", "--abbrev-ref", "HEAD")[1]
    if ARM_BRANCH.match(branch):
        return True
    rc, diff = git(root, "diff", "--ignore-submodules=dirty", f"{base}...HEAD", "--", "CHANGELOG.md")
    return rc == 0 and any(RELEASE_HEADING.match(line) for line in diff.splitlines())


def judge(root: Path) -> tuple[int, str]:
    status = root / STATUS
    if not status.is_file():
        return 1, f"{STATUS.as_posix()} does not exist: a release with no brain status cannot be shown fresh"
    m = UPDATED.search(status.read_text(encoding="utf-8", errors="replace"))
    if not m:
        return 1, f"{STATUS.as_posix()} has no `_Updated: <date> · sha <commit>` line this check can read"
    date, sha = m.groups()
    rc, shallow = git(root, "rev-parse", "--is-shallow-repository")
    if rc == 0 and shallow == "true":
        return 1, "this is a shallow clone: its tags and history are not all here, so the last promotion cannot be told (fetch with --unshallow --tags)"
    rc, tags = git(root, "tag", "--list", "v*", "--sort=-creatordate")
    if rc != 0:
        return 1, "git could not list the tags"
    if not tags:
        return 0, "no v* tag: nothing has been promoted, so nothing is stale"
    tag = tags.splitlines()[0]
    tag_at = commit_time(root, f"{tag}^{{commit}}")
    if tag_at is None:
        return 1, f"cannot read the commit date of the newest tag {tag}"
    sha_at = commit_time(root, f"{sha}^{{commit}}")
    if sha_at is None:
        return 1, f"STATUS.md names sha {sha}, which this clone does not have: it cannot be dated, so freshness cannot be shown"
    (sha_ts, sha_date), (tag_ts, tag_date) = sha_at, tag_at
    if sha_ts < tag_ts:
        return 1, (f"STATUS.md is older than the last promotion: it was written at sha {sha} ({sha_date}, _Updated {date}) "
                   f"and the newest tag {tag} is dated {tag_date}. Refresh docs/brain/STATUS.md (and record the decisions "
                   f"made since) before arming or promoting")
    return 0, f"STATUS.md is current: sha {sha} ({sha_date}) is not older than {tag} ({tag_date})"


def selftest() -> int:
    n, bad = 0, []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            bad.append(f"{label}{(' — ' + str(detail)) if detail else ''}")

    # A FIXTURE SETS ITS OWN BRANCH SIGNALS AND NEVER READS THE RUNNER'S. In CI on an arm PR the ambient GITHUB_HEAD_REF is
    # `chore/arm-vX.Y.Z`, which made the "not an arm" fixture an arm and the selftest refuse (the v1.159.0 arm, #2313).
    # The child's environment is hermetic (no GIT_*), minus every variable the script could read a branch from.
    branch_signals = ("GITHUB_HEAD_REF", "GITHUB_REF_NAME", "GITHUB_REF", "GITHUB_BASE_REF")

    def run(root: Path, *args: str, env: dict | None = None):
        base = {k: v for k, v in fixture_git.hermetic().items() if k not in branch_signals}
        r = subprocess.run([sys.executable, __file__, "--root", str(root), *args], capture_output=True, text=True,
                           env={**base, **(env or {})})
        return r.returncode, r.stdout + r.stderr

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fixture_git  # noqa: E402  (a fixture's git touches only its own temp repo, #1588)

    def commit(root: Path, name: str, when: str) -> str:
        (root / name).write_text(name, encoding="utf-8")
        fixture_git.run(root, "add", name)
        fixture_git.run(root, "commit", "-q", "-m", name, env={"GIT_AUTHOR_DATE": when, "GIT_COMMITTER_DATE": when})
        return fixture_git.run(root, "rev-parse", "--short", "HEAD").stdout.strip()

    def repo() -> Path:
        r = fixture_git.init(Path(tempfile.mkdtemp(prefix="brain-fresh-")), "-b", "dev")
        (r / "docs/brain").mkdir(parents=True)
        return r

    def status(root: Path, sha: str, date: str = "2026-10-01") -> None:
        (root / STATUS).write_text(f"# STATUS\n\n_Updated: {date} · sha {sha} (dev) · main abc1234_\n", encoding="utf-8")

    r = repo()
    old = commit(r, "a", "2026-09-01T10:00:00+00:00")
    commit(r, "b", "2026-09-10T10:00:00+00:00")
    fixture_git.run(r, "tag", "v1.0.0")
    new = commit(r, "c", "2026-09-20T10:00:00+00:00")

    status(r, new)
    check("a STATUS written after the last promotion is fresh", run(r)[0] == 0, run(r))
    status(r, old, "2026-09-01")
    rc, out = run(r)
    check("a STATUS older than the last promotion is refused, and says so", rc == 1 and "older than the last promotion" in out, (rc, out))
    check("...naming the tag and both dates", "v1.0.0" in out and "2026-09-01" in out and "2026-09-10" in out, out)

    status(r, "deadbee")
    rc, out = run(r)
    check("a sha this clone does not have is refused, not passed", rc == 1 and "does not have" in out, (rc, out))
    (r / STATUS).write_text("# STATUS\n\nno updated line here\n", encoding="utf-8")
    rc, out = run(r)
    check("a STATUS with no readable _Updated line is refused", rc == 1 and "no `_Updated" in out, (rc, out))
    (r / STATUS).unlink()
    rc, out = run(r)
    check("a missing STATUS is refused", rc == 1 and "does not exist" in out, (rc, out))

    # MIXED UTC OFFSETS (#2303 review): compare instants, not text. 10:00+05:00 is 05:00Z, EARLIER than a tag at 08:00Z.
    mo = repo()
    commit(mo, "a", "2026-09-01T10:00:00+00:00")
    eastern_old = commit(mo, "b", "2026-09-10T10:00:00+05:00")      # 05:00Z
    commit(mo, "t", "2026-09-10T08:00:00+00:00")
    fixture_git.run(mo, "tag", "v1.0.0")                            # the tag is 08:00Z
    status(mo, eastern_old, "2026-09-10")
    rc, out = run(mo)
    check("a STATUS at 10:00+05:00 (05:00Z) is OLDER than a tag at 08:00Z, though its text sorts later", rc == 1 and "older than the last promotion" in out, (rc, out))
    mo2 = repo()
    commit(mo2, "a", "2026-09-01T10:00:00+00:00")
    commit(mo2, "t", "2026-09-10T10:00:00+05:00")
    fixture_git.run(mo2, "tag", "v1.0.0")                           # the tag is 05:00Z
    western_new = commit(mo2, "b", "2026-09-10T08:00:00+00:00")     # 08:00Z: later, though its text sorts earlier
    status(mo2, western_new, "2026-09-10")
    rc, out = run(mo2)
    check("a STATUS at 08:00Z is NEWER than a tag at 10:00+05:00 (05:00Z), though its text sorts earlier", rc == 0, (rc, out))

    nt = repo()
    first = commit(nt, "a", "2026-09-01T10:00:00+00:00")
    status(nt, first)
    rc, out = run(nt)
    check("a project with no v* tag has promoted nothing: nothing is stale", rc == 0 and "nothing has been promoted" in out, (rc, out))

    sh = Path(tempfile.mkdtemp(prefix="brain-fresh-shallow-"))
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{r}", str(sh / "c")], check=True, capture_output=True,
                   env=fixture_git.hermetic())
    (sh / "c/docs/brain").mkdir(parents=True, exist_ok=True)
    status(sh / "c", new)
    rc, out = run(sh / "c")
    check("a shallow clone cannot tell and is refused, not passed", rc == 1 and "shallow" in out, (rc, out))

    status(r, old, "2026-09-01")
    rc, out = run(r, "--when", "arm")
    check("--when arm on a branch that is not an arm is not applicable (exit 3), whatever STATUS says", rc == 3 and "not an arm" in out, (rc, out))
    # The runner's own branch must not reach the fixture: with the AMBIENT environment set to an arm (as in CI on an arm PR)
    # the same "not an arm" fixture still gets exit 3.
    saved = {k: os.environ.get(k) for k in branch_signals}
    try:
        os.environ.update({"GITHUB_HEAD_REF": "chore/arm-v9.9.9", "GITHUB_REF_NAME": "chore/arm-v9.9.9", "GITHUB_REF": "refs/heads/chore/arm-v9.9.9"})
        rc, out = run(r, "--when", "arm")
    finally:
        for k, v in saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    check("--when arm on a branch that is not an arm is still not applicable (exit 3) when the RUNNER's environment says it is an arm (CI on an arm PR)",
          rc == 3 and "not an arm" in out, (rc, out))
    rc, out = run(r, "--when", "arm", env={"GITHUB_HEAD_REF": "chore/arm-v1.1.0"})
    check("--when arm on an arm branch judges, and refuses a stale STATUS", rc == 1 and "older than the last promotion" in out, (rc, out))
    status(r, new)
    rc, out = run(r, "--when", "arm", env={"GITHUB_HEAD_REF": "chore/arm-v1.1.0"})
    check("--when arm on an arm branch passes a fresh STATUS", rc == 0, (rc, out))
    fixture_git.run(r, "checkout", "-q", "-b", "feature/x")
    cl = r / "CHANGELOG.md"
    cl.write_text("# c\n", encoding="utf-8")
    commit(r, "CHANGELOG.md", "2026-09-21T10:00:00+00:00")
    fixture_git.run(r, "checkout", "-q", "-b", "armed")
    cl.write_text("# c\n\n### 1.1.0 (release v1.1.0)\n", encoding="utf-8")
    fixture_git.run(r, "commit", "-qam", "arm")
    status(r, old, "2026-09-01")
    rc, out = run(r, "--when", "arm", "--base", "feature/x")
    check("--when arm also fires on a diff that adds a `(release vX)` heading, whatever the branch is called",
          rc == 1 and "older than the last promotion" in out, (rc, out))

    for f in bad:
        print(f"FAIL {f}")
    print(f"check_brain_fresh selftest: {n} checks, {len(bad)} failure(s)")
    return 1 if bad else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--when", choices=("always", "arm"), default="always")
    ap.add_argument("--base", default="origin/dev", help="the ref `--when arm` diffs CHANGELOG.md against")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    root = Path(a.root)
    if a.when == "arm" and not is_arm(root, a.base):
        print("not an arm or a promotion (no chore/arm-* or release/* branch, and no `(release vX)` heading added to CHANGELOG.md): "
              "brain freshness is judged at the release")
        return 3
    rc, msg = judge(root)
    print(("ok: " if rc == 0 else "REFUSED: ") + msg)
    return rc


if __name__ == "__main__":
    sys.exit(main())
