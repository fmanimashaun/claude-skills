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
  * the licensed corpora live in a separate private repo, cloned into one gitignored
    subfolder, and exactly ONE file reads them -- and the ignore rules that keep them out of
    this history are themselves checked, because they once could not match the layout the
    setup instructions prescribed (#197);
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
import os
import shutil
import subprocess
import sys
import tempfile
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
#
# ONE gitignored subfolder holding a nested clone — not three root-level symlinks (#197).
# `check_corpora_ignored` keeps this in step with `.gitignore`, and the selftest asserts it
# stays in step with `build_coverage.TW_ROOT`, which is the only thing that reads the kits.
CORPORA_DIR = "design-corpora"
CORPORA = ("tailwind-ui", "flowbite", "everylayout")
CORPORA_REPO = "https://github.com/fmanimashaun/design-corpora.git"

# Paths whose ignore status is asserted below. The near-misses matter as much as the positives:
# an over-broad corpora pattern that swallowed `coverage.md` would silently disable the drift
# guard. `/flowbite*` is wildcarded on purpose (flowbite-figma, the zips), so its near-miss
# tests the root ANCHOR at depth rather than the name.
MUST_IGNORE = (
    CORPORA_DIR,
    f"{CORPORA_DIR}/tailwind-ui/html/components",
    "tailwind-ui",          # the pre-#197 root layout, still ignored as insurance
    "everylayout",
    "flowbite",
    "flowbite-figma",
    "flowbite-pro-marketing-ui.zip",
)
MUST_NOT_IGNORE = (
    "scripts/build_coverage.py",                    # not everything is ignored
    f"{CORPORA_DIR}-notes/README.md",               # exact name, not a prefix
    "docs/flowbite-notes.md",                       # `/flowbite*` is root-anchored
    "skills/fidara-design/references/coverage.md",   # the drift guard needs this committed
)

GATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("markdown shell lint", ("python3", "scripts/lint_markdown_shell.py")),
    ("markdown shell coverage", ("python3", "scripts/lint_markdown_shell.py", "--audit-coverage")),
    ("markdown code lint", ("python3", "scripts/lint_markdown_code.py")),
    ("markdown code coverage", ("python3", "scripts/lint_markdown_code.py", "--audit-coverage")),
    ("markdown code selftest", ("python3", "scripts/lint_markdown_code.py", "--selftest")),
    # Only the SELFTEST is a gate. Validating the live tracker needs `gh`, and a gate that fails
    # for want of a binary teaches people to ignore gates — the reasoning CORPORA_GATES already
    # encodes. The live check runs in /maintainer-triage, where `gh` is a stated precondition.
    ("issue graph selftest", ("python3", "scripts/issue_graph.py", "--selftest")),
    ("self-consistency", ("python3", "scripts/lint_self_consistency.py")),
    ("self-consistency selftest", ("python3", "scripts/lint_self_consistency.py", "--selftest")),
    ("coverage matrix drift", ("python3", "scripts/build_coverage.py", "--check")),
    ("coverage matrix selftest", ("python3", "scripts/build_coverage.py", "--selftest")),
    # The artifact is COMMITTED (docs/coverage.html), so it can go stale exactly as coverage.md
    # can — same shape, same gate, and the same corpora dependency. An earlier version of this
    # comment claimed neither gate needed the licensed kits, because `ENTRIES` is declared
    # statically. That was wrong and was proved wrong by running it: the page also EMBEDS the
    # upstream corpus totals, so a corpora-less machine renders different bytes and the drift gate
    # returns 1 on a perfectly good checkout. Hence its place in CORPORA_GATES below.
    ("coverage artifact drift", ("python3", "scripts/build_coverage_artifact.py", "--check")),
    # The selftest is a gate too: one that exists but that `--gates` never runs makes a clean sweep a
    # claim about work nobody did — the coverage-gap class. It was registered TWICE for a while, which
    # inflates the sweep count; GATE names are asserted unique in the selftest now.
    ("coverage artifact selftest", ("python3", "scripts/build_coverage_artifact.py", "--selftest")),
    ("packaging determinism", ("python3", "scripts/package_core.py", "--selftest")),
    ("rails-flow self-consistency", ("python3", "plugins/rails-flow/scripts/self_consistency.py", "--selftest")),
    ("acceptance criteria", ("python3", "plugins/rails-flow/scripts/check_criteria.py", "--selftest")),
    ("rails-flow guide", ("python3", "plugins/rails-flow/scripts/check_guide.py", "--selftest")),
    ("qa-flow evidence", ("python3", "plugins/qa-flow/scripts/validate_evidence.py", "--selftest")),
    ("qa-flow route coverage", ("python3", "plugins/qa-flow/scripts/route_coverage.py", "--selftest")),
    ("qa-flow evidence manifest", ("python3", "plugins/qa-flow/scripts/evidence_manifest.py", "--selftest")),
    ("design-flow setup cross-check", ("python3", "plugins/design-flow/scripts/setup_doctrine_crosscheck.py", "--quiet")),
    ("design-flow setup cross-check selftest", ("python3", "plugins/design-flow/scripts/setup_doctrine_crosscheck.py", "--selftest")),
    ("evals gates", ("python3", "evals/selftest.py")),
    # The doctor's own selftest is a gate like any other. Not recursive: this runs `--selftest`,
    # which exercises fixtures and never re-enters `--gates`. Its absence was found by the
    # completeness rule in maintainer_doctor_selftest.py on that rule's first run.
    ("maintainer doctor", ("python3", "scripts/maintainer_doctor.py", "--selftest")),
    # The meta-gate: proves each selftest above actually FAILS when its subject breaks. Runs last
    # because it is the slowest (it re-runs every selftest once per declared mutation).
    ("mutation check", ("python3", "scripts/mutation_check.py", "--selftest")),
    ("mutation coverage", ("python3", "scripts/mutation_check.py")),
)

# Gates that cannot run without the licensed corpora, so their absence is a SKIP rather than a
# FAIL. Only the two DRIFT checks qualify, and for the same reason: both compare a committed
# artifact against a fresh build, and both artifacts carry the upstream corpus totals, so without
# the kits the rebuild differs and the gate reports drift on a healthy checkout. The matching
# SELFTESTS do NOT belong here — each reports its corpora-dependent checks as SKIPPED and still
# exits 0, which is the honest shape and leaves the rest of the fixtures running.
# Keyed by gate NAME, and the selftest asserts every name here exists in GATES — otherwise a
# rename would silently stop the exemption applying — and that the set is exactly these two.
CORPORA_GATES = frozenset({"coverage matrix drift", "coverage artifact drift"})


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
        root = REPO / CORPORA_DIR
        missing = [c for c in CORPORA if not (root / c).exists()]
        if not missing:
            self.add(PASS, "design corpora present", f"{CORPORA_DIR}/: " + ", ".join(CORPORA))
            return
        self.add(
            SKIP, f"design corpora missing: {', '.join(missing)}",
            "only `scripts/build_coverage.py` reads them, so everything else works — but the "
            "coverage matrix cannot be regenerated or drift-checked",
            # A nested clone, nothing to link. The old remedy was a clone plus three `ln -s`,
            # which produced paths `.gitignore` could not match at all (#197).
            f"git clone {CORPORA_REPO} {CORPORA_DIR}",
        )

    def check_corpora_ignored(self) -> None:
        """The ignore rules must actually cover the layout the setup instructions prescribe.

        #197: the patterns were `tailwind-ui/`, `everylayout/`, `flowbite*/` while CLAUDE.md
        told maintainers to symlink the kits in. A trailing slash matches a real DIRECTORY, and
        git stores a symlink as mode 120000 — so none of the three matched, and all three sat
        UNTRACKED in the guard written to hide them, directly under doctrine warning about
        656 MB of licensed blobs the rule could not actually stop. That is
        `claims-vs-enforcement` from skills/code-review/SKILL.md, so it is re-checked by script
        rather than remembered.

        Asserted in a THROWAWAY repo seeded with our `.gitignore`, against paths that DO NOT
        EXIST — both deliberate. `git check-ignore` consults the filesystem to decide whether a
        trailing-slash pattern applies, so on a machine that already has the corpora, testing
        the real path matches under BOTH the correct pattern and the buggy one and a regression
        hides. Against a path that is not there, only a slash-free pattern matches — which
        discriminates on every machine, and subsumes the symlink form, so nothing needs
        creating (a symlink would need Developer Mode on Windows).
        """
        gitignore = REPO / ".gitignore"
        if not gitignore.is_file():
            self.add(FAIL, "corpora ignore rules", "no .gitignore at the repo root",
                     "restore .gitignore — without it the licensed corpora are committable")
            return

        tmp = Path(tempfile.mkdtemp(prefix="doctor-ignore-"))
        try:
            code, out = self.run("git", "init", "-q", str(tmp), cwd=tmp)
            if code != 0:
                self.add(SKIP, "corpora ignore rules", f"could not create a probe repo: {out}")
                return
            shutil.copyfile(gitignore, tmp / ".gitignore")

            problems: list[str] = []
            for candidate in MUST_IGNORE:
                verdict = self._ignored_in(tmp, candidate)
                if verdict is None:
                    self.add(SKIP, "corpora ignore rules",
                             f"git check-ignore unusable for {candidate!r}")
                    return
                if not verdict:
                    problems.append(f"{candidate!r} is NOT ignored")
            for candidate in MUST_NOT_IGNORE:
                verdict = self._ignored_in(tmp, candidate)
                if verdict is None:
                    self.add(SKIP, "corpora ignore rules",
                             f"git check-ignore unusable for {candidate!r}")
                    return
                if verdict:
                    problems.append(f"{candidate!r} IS ignored but must not be")

            if problems:
                self.add(
                    FAIL, "corpora ignore rules", "; ".join(problems),
                    "in `.gitignore`, the corpora patterns must be root-anchored and "
                    "slash-FREE (`/design-corpora`, not `design-corpora/`): a trailing slash "
                    "matches a real directory only, never a symlink (#197)",
                )
            else:
                self.add(PASS, "corpora ignore rules",
                         f"{len(MUST_IGNORE)} ignored, {len(MUST_NOT_IGNORE)} near-misses clear")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _ignored_in(self, probe: Path, candidate: str) -> bool | None:
        """True if ignored, False if not, None if git could not answer.

        Isolated from global/system git config: a maintainer whose personal `core.excludesFile`
        happens to list `design-corpora` would otherwise make this pass no matter what our
        `.gitignore` says — a fail-open inside the check for a fail-open. Exit 0 means ignored
        and 1 means not; anything else (128 = fatal) returns None rather than reading as "not
        ignored", so a broken invocation cannot be mistaken for a verdict.
        """
        try:
            p = subprocess.run(
                ["git", "check-ignore", "--", candidate],
                cwd=probe, capture_output=True, text=True, timeout=60,
                env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull,
                     "GIT_CONFIG_SYSTEM": os.devnull},
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None
        if p.returncode == 0:
            return True
        if p.returncode == 1:
            return False
        return None

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
        corpora_absent = any(not (REPO / CORPORA_DIR / c).exists() for c in CORPORA)
        for name, cmd in GATES:
            script = REPO / cmd[1]
            if not script.exists():
                self.add(
                    SKIP, f"gate: {name}", f"{cmd[1]} does not exist",
                    "this checkout predates the gate — `git pull` on `dev`",
                )
                continue
            # A gate that CANNOT run is not a broken machine. The corpora are optional (only
            # build_coverage.py reads them), so failing this gate for their absence told a
            # contributor to "fix the failures before doing maintenance work" about a file they
            # are not required to have — the mirror image of the SKIP-as-PASS bug this script
            # exists to prevent, and it made "OPTIONAL" false for anyone running --gates.
            if name in CORPORA_GATES and corpora_absent:
                self.add(
                    SKIP, f"gate: {name}", "licensed corpora absent — nothing to drift-check",
                    f"git clone {CORPORA_REPO} {CORPORA_DIR}",
                )
                continue
            code, out = self.run(*cmd)
            if code == 0:
                self.add(PASS, f"gate: {name}")
            elif code == 3:
                # Exit 3 is a gate's own "I ran but could not check everything" — currently
                # lint_markdown_code.py with node or ruby absent, which is the normal state of a
                # cloud container. Reporting `ok` there would let 242 of 276 blocks go unchecked
                # behind a green line, so it is a SKIP and the reason comes from the gate itself.
                reason = out.strip().splitlines()[0] if out.strip() else "incomplete run"
                self.add(SKIP, f"gate: {name}", reason,
                         "install the missing interpreter, or state in the PR that the gate "
                         "could not run — a skip is not a pass")
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
        self.check_corpora_ignored()
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
