#!/usr/bin/env python3
"""Diagnose a maintainer machine, and repair the safe parts.

Run:  python3 scripts/maintainer_doctor.py            # diagnose, change nothing
      python3 scripts/maintainer_doctor.py --fix       # also apply the SAFE repairs
      python3 scripts/maintainer_doctor.py --gates     # include the full gate sweep (slower)
      python3 scripts/maintainer_doctor.py --selftest   # prove the checks fire and stay silent

WHY THIS EXISTS. Moving maintenance to a second machine needed a ~120-line hand-written
briefing, and it was only complete because the author had just hit every trap personally:

  * a fresh clone lands on `main` -- the one branch this repo says never to work from;
  * an idle clone has a STALE local `main` ref, which silently breaks the `git diff dev main`
    check CLAUDE.md prescribes (it reported 5,231 phantom deletions on a real machine);
  * the licensed corpora live in a separate private repo and must be linked in, and exactly
    ONE file reads them;
  * the ahead/behind counter is meaningless here, because `main` gains one merge commit per
    release that `dev` never receives.

None of that is discoverable. A checklist in a readme would be the same defect class this repo
keeps paying for -- claims-vs-enforcement, a guarantee in prose that nothing makes true -- so
it is a script that can fail instead.

THE DESIGN RULE THAT MATTERS: three outcomes, not two. PASS, FAIL and **SKIP** are reported
distinctly, because a check that did not run must never render as a check that passed. That is
the exact bug this replaces: `build_coverage.py --selftest` printed "35 checks passed" on a
machine with no corpora while silently skipping two checks against the real repo, so the
coverage guards were inert while reading green.

WHAT IT DOES NOT DO. It never rewrites history, never `reset --hard`, never `clean`. `--fix`
touches two things only: fast-forwarding the local `main` ref to `origin/main` (safe, because
you never commit to `main`) and checking out/pulling `dev`. Anything else is reported with a
remedy for a human to run deliberately.

Exit codes:  0 = no failures (skips allowed) · 1 = at least one FAIL · 2 = not this repo

Stdlib only, no network beyond the `git`/`gh` calls the checks make.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The one historical direct-to-main commit, documented in CLAUDE.md. It converged (the same
# block later reached dev), so it is expected -- but anything ELSE on main and not on dev is a
# real finding, because a direct commit to main is invisible to every future dev-based change.
KNOWN_DIRECT_TO_MAIN = "d4b35f6"

PASS, FAIL, SKIP, INFO = "PASS", "FAIL", "SKIP", "INFO"

# Only `scripts/build_coverage.py` reads the corpora. Stated here so the corpora check can say
# what is actually lost without them, rather than implying the repo is unusable.
CORPORA = ("tailwind-ui", "flowbite", "everylayout")
CORPORA_REPO = "https://github.com/fmanimashaun/design-corpora.git"

GATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("markdown shell lint", ("python3", "scripts/lint_markdown_shell.py")),
    ("markdown shell coverage", ("python3", "scripts/lint_markdown_shell.py", "--audit-coverage")),
    ("self-consistency", ("python3", "scripts/lint_self_consistency.py")),
    ("self-consistency selftest", ("python3", "scripts/lint_self_consistency.py", "--selftest")),
    ("coverage matrix drift", ("python3", "scripts/build_coverage.py", "--check")),
    ("coverage matrix selftest", ("python3", "scripts/build_coverage.py", "--selftest")),
    ("packaging determinism", ("python3", "scripts/package_core.py", "--selftest")),
    ("rails-flow self-consistency", ("python3", "plugins/rails-flow/scripts/self_consistency.py", "--selftest")),
    ("acceptance criteria", ("python3", "plugins/rails-flow/scripts/check_criteria.py", "--selftest")),
    ("qa-flow evidence", ("python3", "plugins/qa-flow/scripts/validate_evidence.py", "--selftest")),
    ("evals gates", ("python3", "evals/selftest.py")),
)


@dataclass
class Result:
    status: str
    name: str
    detail: str = ""
    remedy: str = ""


@dataclass
class Doctor:
    fix: bool = False
    results: list[Result] = field(default_factory=list)
    fixed: list[str] = field(default_factory=list)

    # ---- helpers ----------------------------------------------------------------------
    def run(self, *args: str, cwd: Path | None = None) -> tuple[int, str]:
        try:
            p = subprocess.run(
                args, cwd=cwd or REPO, capture_output=True, text=True, timeout=180
            )
            return p.returncode, (p.stdout + p.stderr).strip()
        except FileNotFoundError:
            return 127, f"{args[0]}: not found"
        except subprocess.TimeoutExpired:
            return 124, f"{' '.join(args)}: timed out"

    def git(self, *args: str) -> tuple[int, str]:
        return self.run("git", *args)

    def add(self, status: str, name: str, detail: str = "", remedy: str = "") -> Result:
        r = Result(status, name, detail, remedy)
        self.results.append(r)
        return r

    def working_tree_changes(self) -> list[str]:
        """Changed paths, tracked or not. `-uall` matters: plain --porcelain collapses a new
        untracked directory to "?? dir/", which is how a fresh file can look like nothing at
        all (the same collapse that had rails-flow's Stop gate silently not firing)."""
        code, out = self.git("status", "--porcelain", "-uall")
        if code != 0:
            return []
        paths = []
        for line in out.splitlines():
            if len(line) > 3:
                paths.append(line[3:].split(" -> ")[-1])
        return paths

    # ---- checks -----------------------------------------------------------------------
    def check_prerequisites(self) -> None:
        for tool, why in (
            ("git", "everything"),
            ("python3", "every gate and packaging"),
            ("gh", "issues, PRs and releases"),
        ):
            code, _ = self.run(tool, "--version")
            if code == 0:
                self.add(PASS, f"`{tool}` present")
            else:
                self.add(
                    FAIL, f"`{tool}` missing", f"needed for {why}",
                    f"install {tool} and put it on PATH",
                )

        code, out = self.run("gh", "auth", "status")
        if code == 0:
            self.add(PASS, "`gh` authenticated")
        else:
            self.add(
                FAIL, "`gh` not authenticated",
                "the repo is private at times, so even `git fetch` can fail",
                "gh auth login",
            )

    def check_is_marketplace_repo(self) -> bool:
        """Same precondition as the SessionStart hook. Fatal: nothing else makes sense."""
        if (REPO / ".claude-plugin" / "marketplace.json").is_file():
            self.add(PASS, "this is the claude-skills marketplace repo")
            return True
        self.add(
            FAIL, "not the marketplace repo",
            f"no .claude-plugin/marketplace.json under {REPO}",
            "run this from inside a claude-skills checkout",
        )
        return False

    def check_branch(self) -> None:
        code, branch = self.git("symbolic-ref", "--short", "HEAD")
        if code != 0:
            self.add(
                SKIP, "current branch", "detached HEAD or unborn branch",
                "git checkout dev",
            )
            return
        if branch == "main":
            if self.fix:
                c, out = self.git("checkout", "dev")
                if c == 0:
                    self.fixed.append("checked out `dev` (was on `main`)")
                    self.add(PASS, "on `dev`", "was on `main`; --fix checked out `dev`")
                    return
                self.add(
                    FAIL, "on `main`", f"could not switch: {out}",
                    "git checkout dev — resolve the blocker first",
                )
                return
            self.add(
                FAIL, "on `main`",
                "main is the install surface; work never starts here, and a direct commit "
                "survives every future dev->main merge invisibly",
                "git checkout dev   (or re-run with --fix)",
            )
        elif branch == "dev":
            # `dev` is the integration branch, not a workbench. Sitting on it is correct
            # BETWEEN pieces of work and wrong DURING one -- work branches off it and PRs
            # back into it. Uncommitted changes here are the signal that someone (me, while
            # writing this very check) started editing without branching first.
            dirty = self.working_tree_changes()
            if dirty:
                self.add(
                    FAIL, "editing directly on `dev`",
                    f"{len(dirty)} uncommitted path(s): {', '.join(dirty[:3])}"
                    + (" …" if len(dirty) > 3 else "")
                    + " — `dev` is the integration branch; work branches off it and PRs back in",
                    "git checkout -b feature/<slug>   (untracked and unstaged changes follow you)",
                )
            else:
                self.add(PASS, "on `dev`, clean", "correct resting state between pieces of work")
        else:
            self.add(INFO, f"on `{branch}`", "a work branch — the right place to be mid-task")

    def check_stale_main_ref(self) -> None:
        """The trap that makes the documented dev-vs-main check lie."""
        code, local = self.git("rev-parse", "main")
        if code != 0:
            self.add(
                SKIP, "local `main` ref", "no local `main` branch",
                "git branch main origin/main   (optional; only needed for `git diff dev main`)",
            )
            return
        code, remote = self.git("rev-parse", "origin/main")
        if code != 0:
            self.add(SKIP, "local `main` ref", "no `origin/main` — fetch first", "git fetch --all")
            return
        if local == remote:
            self.add(PASS, "local `main` matches `origin/main`")
            return
        detail = (
            f"local {local[:9]} vs origin {remote[:9]} — this makes `git diff dev main` report "
            "phantom deletions (5,231 of them on a real machine)"
        )
        if self.fix:
            c, out = self.git("branch", "-f", "main", "origin/main")
            if c == 0:
                self.fixed.append("fast-forwarded local `main` to `origin/main`")
                self.add(PASS, "local `main` matches `origin/main`", "--fix updated the ref")
                return
            self.add(FAIL, "stale local `main` ref", f"{detail}; fix failed: {out}",
                     "git branch -f main origin/main")
            return
        self.add(
            FAIL, "stale local `main` ref", detail,
            "git branch -f main origin/main   (safe: you never commit to main)",
        )

    def check_dev_current(self) -> None:
        code, _ = self.git("rev-parse", "origin/dev")
        if code != 0:
            self.add(FAIL, "`origin/dev` unknown", "no remote dev ref", "git fetch --all --prune")
            return
        code, local = self.git("rev-parse", "dev")
        if code != 0:
            self.add(FAIL, "no local `dev`", "", "git checkout dev")
            return
        _, remote = self.git("rev-parse", "origin/dev")
        if local == remote:
            self.add(PASS, "`dev` is current with `origin/dev`")
            return
        _, behind = self.git("rev-list", "--count", "dev..origin/dev")
        _, ahead = self.git("rev-list", "--count", "origin/dev..dev")
        detail = f"{ahead} ahead, {behind} behind"
        if self.fix and ahead == "0":
            c, out = self.git("pull", "--ff-only")
            if c == 0:
                self.fixed.append("pulled `dev`")
                self.add(PASS, "`dev` is current with `origin/dev`", "--fix pulled")
                return
            self.add(FAIL, "`dev` not current", f"{detail}; pull failed: {out}", "git pull")
            return
        self.add(
            FAIL if behind != "0" else INFO, "`dev` not current with `origin/dev`", detail,
            "git pull --ff-only" + ("" if ahead == "0" else "  (you have unpushed commits)"),
        )

    def check_unshipped(self) -> None:
        """Informational: unshipped work is normal, it is not a fault."""
        code, out = self.git("diff", "--stat", "dev", "origin/main")
        if code != 0:
            self.add(SKIP, "unshipped work", "cannot diff dev against origin/main", "git fetch --all")
            return
        if not out.strip():
            self.add(INFO, "no unshipped work", "`dev` and `main` are content-identical")
            return
        _, count = self.git("rev-list", "--count", "origin/main..dev")
        self.add(
            INFO, f"{count} unshipped commit(s) on `dev`",
            "a promotion would ship them; not a fault",
            "read the CHANGELOG `### Unreleased` sections to see what",
        )

    def check_no_direct_to_main(self) -> None:
        code, out = self.git("log", "--oneline", "dev..origin/main", "--no-merges")
        if code != 0:
            self.add(SKIP, "direct-to-`main` commits", "cannot compare", "git fetch --all")
            return
        lines = [l for l in out.splitlines() if l.strip()]
        unexpected = [l for l in lines if not l.startswith(KNOWN_DIRECT_TO_MAIN)]
        if not unexpected:
            self.add(PASS, "no unmerged direct-to-`main` commits")
            return
        self.add(
            FAIL, f"{len(unexpected)} direct-to-`main` commit(s) not on `dev`",
            "; ".join(unexpected[:3]) + " — a merge unions, it never removes content that "
            "exists only on main, so these are invisible to every future dev-based change",
            "cherry-pick them onto `dev` and promote, or confirm they are intentional",
        )

    def check_corpora(self) -> None:
        missing = [c for c in CORPORA if not (REPO / c).exists()]
        if not missing:
            self.add(PASS, "design corpora present", ", ".join(CORPORA))
            return
        self.add(
            SKIP, f"design corpora missing: {', '.join(missing)}",
            "only `scripts/build_coverage.py` reads them, so everything else works — but the "
            "coverage matrix cannot be regenerated or drift-checked",
            f"git clone {CORPORA_REPO} ../design-corpora && "
            + " && ".join(f"ln -s ../design-corpora/{c} {c}" for c in missing),
        )

    def check_dist_clean(self) -> None:
        """Compare committed `dist/` against a clean build — WITHOUT leaving a trace.

        The rebuild is the only way to know, but `package_core.py` writes into `dist/` and has
        no output-dir flag, so this snapshots the bytes first and restores them afterwards. A
        diagnostic that mutates the repo is not a diagnostic. The first version of this skipped
        the restore and was idempotent only because the packer is byte-deterministic — true
        today, incidental rather than guaranteed, and it would have silently destroyed
        intentional uncommitted `dist/` edits.
        """
        dist = REPO / "dist"
        if not dist.is_dir():
            self.add(SKIP, "`dist/` drift guard", "no dist/ directory",
                     "python3 scripts/package_core.py")
            return

        snapshot = {p: p.read_bytes() for p in sorted(dist.glob("*.skill"))}
        try:
            code, out = self.run("python3", "scripts/package_core.py")
            if code != 0:
                self.add(FAIL, "`dist/` rebuild failed", out.splitlines()[-1] if out else "",
                         "python3 scripts/package_core.py")
                return
            # After the rebuild the working tree IS a clean build, so anything git reports as
            # changed is committed content that differs from it — exactly the CI drift guard.
            _, status = self.git("status", "--porcelain", "dist/")
            if not status.strip():
                self.add(PASS, "committed `dist/` is a clean build")
            else:
                self.add(
                    FAIL, "committed `dist/` does not match a clean build",
                    status.strip().replace("\n", "; "),
                    "python3 scripts/package_core.py && git add dist/ && commit — the CI drift "
                    "guard fails a release otherwise",
                )
        finally:
            # Restore byte-for-byte, including files the rebuild may have added.
            for path, data in snapshot.items():
                if path.read_bytes() != data:
                    path.write_bytes(data)
            for p in dist.glob("*.skill"):
                if p not in snapshot:
                    p.unlink()

    def check_gates(self) -> None:
        for name, cmd in GATES:
            script = REPO / cmd[1]
            if not script.exists():
                self.add(
                    SKIP, f"gate: {name}", f"{cmd[1]} does not exist",
                    "this checkout predates the gate — `git pull` on `dev`",
                )
                continue
            code, out = self.run(*cmd)
            if code == 0:
                self.add(PASS, f"gate: {name}")
            else:
                tail = out.splitlines()[-1] if out else f"exit {code}"
                self.add(FAIL, f"gate: {name}", tail, " ".join(cmd))

    # ---- driver ----------------------------------------------------------------------
    def diagnose(self, gates: bool) -> int:
        if not self.check_is_marketplace_repo():
            self.report()
            return 2
        self.check_prerequisites()
        self.git("fetch", "--all", "--tags", "--prune")
        self.check_branch()
        self.check_stale_main_ref()
        self.check_dev_current()
        self.check_no_direct_to_main()
        self.check_unshipped()
        self.check_corpora()
        self.check_dist_clean()
        if gates:
            self.check_gates()
        else:
            self.add(
                SKIP, "full gate sweep", "not requested",
                "re-run with --gates once the machine is otherwise healthy",
            )
        self.report()
        return 1 if any(r.status == FAIL for r in self.results) else 0

    def report(self) -> None:
        icon = {PASS: "  ok  ", FAIL: " FAIL ", SKIP: " skip ", INFO: " note "}
        for r in self.results:
            print(f"[{icon[r.status]}] {r.name}")
            if r.detail:
                print(f"           {r.detail}")
            if r.remedy and r.status in (FAIL, SKIP):
                print(f"           -> {r.remedy}")

        if self.fixed:
            print("\nRepaired (safe changes only):")
            for f in self.fixed:
                print(f"  - {f}")

        counts = {s: sum(1 for r in self.results if r.status == s) for s in (PASS, FAIL, SKIP, INFO)}
        print(
            f"\n{counts[PASS]} passed, {counts[FAIL]} failed, {counts[SKIP]} skipped, "
            f"{counts[INFO]} note(s)"
        )
        # Skipped is called out deliberately: a check that did not run is not a check that
        # passed, and conflating the two is the defect this tool exists to prevent.
        if counts[SKIP]:
            print("Skipped checks did NOT run — they are not passes. Read their remedies above.")
        if counts[FAIL]:
            print("Fix the failures above before doing maintenance work.")
        elif not counts[SKIP]:
            print("Machine is ready.")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Diagnose and repair a maintainer machine.")
    p.add_argument("--fix", action="store_true", help="apply the SAFE repairs (never rewrites history)")
    p.add_argument("--gates", action="store_true", help="also run the full gate sweep (slower)")
    p.add_argument("--selftest", action="store_true", help="prove the checks fire and stay silent")
    args = p.parse_args(argv)

    if args.selftest:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import maintainer_doctor_selftest as st

        return st.run()

    return Doctor(fix=args.fix).diagnose(gates=args.gates)


if __name__ == "__main__":
    sys.exit(main())
