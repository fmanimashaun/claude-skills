#!/usr/bin/env python3
"""Selftest for toolchain_version.py.

Every check here is paired: one fixture that MUST report and one that MUST stay silent.
A gate proven only by the case it catches is a gate that might match everything; the
silence fixtures are what say it doesn't.

Four of these encode substrate facts the EPIC's design sketch got wrong. Those are the
ones to keep if this file is ever trimmed — they are the difference between a check that
reads the real files and one that reads the issue body:

  shadowed-record   two cache records, newest must win     (naive [0] reports the stale one)
  disjoint-sources  rails-stack vs the four code plugins   (either source alone misses a set)
  no-marketplace-version  known_marketplaces.json has none (the sketch said to read it there)
  unusable-not-ok   unreadable state exits 2, never 0      (a skip is not a pass)
"""

from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path

import toolchain_version as tv

RESULTS: list[tuple[bool, str]] = []


def check(name: str, got, want) -> None:
    RESULTS.append((got == want, f"{name}: got {got!r}, want {want!r}"))


def write(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def fake_home(tmp: Path, *, plugins: dict, marketplace_version="1.0.0",
              known=True, install_location=True) -> Path:
    """Build a throwaway ~/.claude/plugins tree with the real files' real shapes."""
    home = tmp / "home"
    base = home / ".claude" / "plugins"
    loc = base / "marketplaces" / "claude-skills"
    if marketplace_version is not None:
        write(loc / ".claude-plugin" / "marketplace.json",
              {"metadata": {"version": marketplace_version},
               "plugins": [{"name": n} for n in plugins]})
    if known:
        write(base / "known_marketplaces.json",
              {"claude-skills": {"source": {"source": "github", "repo": "x/y"},
                                 **({"installLocation": str(loc)} if install_location else {}),
                                 "lastUpdated": "2026-08-07T00:00:00Z"}})
    write(base / "installed_plugins.json", {"version": 2, "plugins": plugins})
    return home


def checkout(tmp: Path, name: str, *, marketplace="1.0.0", bundle=None, code=None) -> Path:
    """A marketplace checkout with the DISJOINT version layout the real repo has:
    `bundle` plugins carry a version in the manifest, `code` plugins only in plugin.json."""
    root = tmp / name
    bundle, code = bundle or {}, code or {}
    entries = [{"name": n, "version": v} for n, v in bundle.items()]
    entries += [{"name": n} for n in code]
    write(root / ".claude-plugin" / "marketplace.json",
          {"metadata": {"version": marketplace}, "plugins": entries})
    for n, v in code.items():
        write(root / "plugins" / n / ".claude-plugin" / "plugin.json", {"name": n, "version": v})
    return root


def rec(version: str, updated: str, project: str | None = None) -> dict:
    r = {"scope": "project", "version": version, "lastUpdated": updated,
         "installPath": f"/cache/{version}"}
    if project is not None:
        r["projectPath"] = project
    return r


# --------------------------------------------------------------------------------

def run() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # -- finding 2: two records for one plugin, newest by lastUpdated must win -------
        home = fake_home(tmp, plugins={
            "rails-flow@claude-skills": [rec("1.18.2", "2026-08-06T15:23:26Z"),
                                         rec("1.19.0", "2026-08-07T08:53:01Z")],
        })
        inst, _ = resolve(home)
        check("shadowed-record: newest wins", inst.plugins.get("rails-flow"), "1.19.0")
        check("shadowed-record: older is named", inst.shadowed.get("rails-flow"), ["1.18.2"])
        # SILENCE: a single record must not be reported as shadowed.
        home1 = fake_home(tmp / "a", plugins={
            "rails-flow@claude-skills": [rec("1.19.0", "2026-08-07T08:53:01Z")]})
        inst1, _ = resolve(home1)
        check("shadowed-record: silent on one record", inst1.shadowed, {})
        # The list order must not decide it — same data, reversed, same answer.
        home2 = fake_home(tmp / "b", plugins={
            "rails-flow@claude-skills": [rec("1.19.0", "2026-08-07T08:53:01Z"),
                                         rec("1.18.2", "2026-08-06T15:23:26Z")]})
        inst2, _ = resolve(home2)
        check("shadowed-record: order-independent", inst2.plugins.get("rails-flow"), "1.19.0")

        # -- finding 4: the two version sources are disjoint -----------------------------
        pub = checkout(tmp, "pub", marketplace="1.73.0",
                       bundle={"rails-stack": "1.42.1"},
                       code={"rails-flow": "1.19.0", "qa-flow": "1.24.1"})
        got, probs = tv.read_manifest_pair(pub)
        check("disjoint-sources: bundle version read", got.plugins.get("rails-stack"), "1.42.1")
        check("disjoint-sources: code version read", got.plugins.get("rails-flow"), "1.19.0")
        check("disjoint-sources: all three resolved", len(got.plugins), 3)
        check("disjoint-sources: silent when complete", probs, [])
        # A code plugin whose plugin.json is missing must be a FINDING, not a silent skip —
        # otherwise it compares equal to itself and passes as up to date.
        broken = checkout(tmp, "broken", code={"rails-flow": "1.19.0"})
        (broken / "plugins" / "rails-flow" / ".claude-plugin" / "plugin.json").unlink()
        _, probs2 = tv.read_manifest_pair(broken)
        check("disjoint-sources: missing plugin.json reported", len(probs2), 1)

        # -- finding 1: known_marketplaces.json carries no version -----------------------
        # Proven by removing installLocation: if the version were read from this file the
        # resolver would still find it. It must not.
        home3 = fake_home(tmp / "c", install_location=False,
                          plugins={"rails-flow@claude-skills": [rec("1.19.0", "2026-08-07T00:00:00Z")]})
        inst3, probs3 = resolve(home3)
        check("no-marketplace-version: unresolvable without installLocation", inst3.marketplace, None)
        check("no-marketplace-version: and it is reported", any("marketplace.json" in p for p in probs3), True)

        # -- compare: numeric, not lexical ----------------------------------------------
        a = tv.Toolchain("1.9.0", {"p": "1.9.0"})
        b = tv.Toolchain("1.10.0", {"p": "1.10.0"})
        check("compare: 1.9.0 < 1.10.0 numerically", len(tv.compare(a, b)), 2)
        check("compare: silent when equal", tv.compare(b, b), [])
        check("compare: silent when ahead", tv.compare(b, a), [])
        check("compare: uninstalled plugin is a finding",
              len(tv.compare(tv.Toolchain("1.0.0", {}), tv.Toolchain("1.0.0", {"p": "1.0.0"}))), 1)

        # -- the marker: write, fail-to-reach, reach, idempotent -------------------------
        proj = tmp / "proj"
        target = tv.Toolchain("1.73.0", {"rails-flow": "1.19.0", "rails-stack": "1.42.1"})
        tv.write_marker(proj, target, "step-3")
        check("marker: survives as a file", tv.marker_path(proj).is_file(), True)

        behind = tv.Toolchain("1.73.0", {"rails-flow": "1.18.2", "rails-stack": "1.42.1"})
        code_, lines = tv.resume(proj, behind)
        check("marker: a plugin behind target escalates", code_, tv.EXIT_FINDINGS)
        check("marker: names which plugin", any("rails-flow" in l for l in lines), True)
        check("marker: NOT cleared on failure", tv.marker_path(proj).is_file(), True)

        reached = tv.Toolchain("1.73.0", {"rails-flow": "1.19.0", "rails-stack": "1.42.1"})
        code_, _ = tv.resume(proj, reached)
        check("marker: cleared once target reached", code_, tv.EXIT_OK)
        check("marker: file gone", tv.marker_path(proj).is_file(), False)
        code_, _ = tv.resume(proj, reached)
        check("marker: second resume is a no-op", code_, tv.EXIT_OK)   # idempotence
        ahead = tv.Toolchain("1.74.0", {"rails-flow": "1.20.0", "rails-stack": "1.43.0"})
        tv.write_marker(proj, target, "step-3")
        code_, _ = tv.resume(proj, ahead)
        check("marker: landing AHEAD of target is not a failure", code_, tv.EXIT_OK)

        # -- finding: unusable input exits 2, and is never folded into 0 -----------------
        empty = fake_home(tmp / "d", plugins={})
        rc = tv.main(["--home", str(empty), "--published-from", str(pub), "--project", str(proj)])
        check("unusable-not-ok: no plugins installed -> 2", rc, tv.EXIT_UNUSABLE)
        # SILENCE: the same call against a populated home must NOT return 2.
        full = fake_home(tmp / "e", marketplace_version="1.73.0", plugins={
            "rails-stack@claude-skills": [rec("1.42.1", "2026-08-07T00:00:00Z")],
            "rails-flow@claude-skills": [rec("1.19.0", "2026-08-07T00:00:00Z")],
            "qa-flow@claude-skills": [rec("1.24.1", "2026-08-07T00:00:00Z")]})
        rc = tv.main(["--home", str(full), "--published-from", str(pub), "--project", str(proj)])
        check("unusable-not-ok: a healthy machine is 0, not 2", rc, tv.EXIT_OK)
        # #923: ONE plugin's published version unresolved (its plugin.json fetch failed) must be 2, not
        # "up to date". Same healthy home; a published checkout that names qa-flow but cannot resolve it.
        pub2 = checkout(tmp / "pub2", "pub2", marketplace="1.73.0", bundle={"rails-stack": "1.42.1"},
                        code={"rails-flow": "1.19.0", "qa-flow": "1.24.1"})
        (pub2 / "plugins" / "qa-flow" / ".claude-plugin" / "plugin.json").unlink()
        rc = tv.main(["--home", str(full), "--published-from", str(pub2), "--project", str(proj)])
        check("unresolved-published: one plugin unresolved on the published side -> 2, never 0", rc, tv.EXIT_UNUSABLE)
        # And real drift is 1 — distinct from both.
        stale = fake_home(tmp / "f", marketplace_version="1.72.0", plugins={
            "rails-stack@claude-skills": [rec("1.42.0", "2026-08-07T00:00:00Z")],
            "rails-flow@claude-skills": [rec("1.19.0", "2026-08-07T00:00:00Z")],
            "qa-flow@claude-skills": [rec("1.24.1", "2026-08-07T00:00:00Z")]})
        rc = tv.main(["--home", str(stale), "--published-from", str(pub), "--project", str(proj)])
        check("unusable-not-ok: drift is 1, distinct from 2", rc, tv.EXIT_FINDINGS)

        # -- #1407: records are per project; the newest machine-wide is not this project's -----
        # The shape measured on the maintainer's machine: one project on 1.63.0, another on
        # 1.68.0 installed later. Resolving machine-wide reported the later project's version.
        pa, pb = tmp / "proj-a", tmp / "proj-b"
        pa.mkdir(); pb.mkdir()
        two = fake_home(tmp / "g", marketplace_version="1.73.0", plugins={
            "rails-stack@claude-skills": [rec("1.41.0", "2026-08-01T00:00:00Z", str(pa)),
                                          rec("1.42.1", "2026-08-07T00:00:00Z", str(pb))],
            "rails-flow@claude-skills": [rec("1.18.2", "2026-08-01T00:00:00Z", str(pa)),
                                         rec("1.19.0", "2026-08-07T00:00:00Z", str(pb))],
            "qa-flow@claude-skills": [rec("1.24.1", "2026-08-07T00:00:00Z")]})   # user scope
        got_a, _ = tv.resolve_installed(two, project=pa)
        check("per-project: A resolves its own, older record", got_a.plugins.get("rails-stack"), "1.41.0")
        check("per-project: A's install path is A's", got_a.paths.get("rails-stack"), "/cache/1.41.0")
        check("per-project: another project's record is not A's shadow", got_a.shadowed, {})
        got_b, _ = tv.resolve_installed(two, project=pb)
        check("per-project: B resolves its own record", got_b.plugins.get("rails-stack"), "1.42.1")
        check("per-project: a user-scope record applies to every project",
              (got_a.plugins.get("qa-flow"), got_b.plugins.get("qa-flow")), ("1.24.1", "1.24.1"))
        nowhere = tmp / "proj-none"
        nowhere.mkdir()
        got_n, probs_n = tv.resolve_installed(two, project=nowhere)
        check("per-project: installed only elsewhere is not installed here",
              "rails-stack" in got_n.plugins, False)
        check("per-project: and it is reported",
              any("rails-stack" in p and "other projects" in p for p in probs_n), True)
        # The same project spelled three other ways, and run from inside it.
        sub = pa / "app" / "models"
        sub.mkdir(parents=True)
        alias = tmp / "alias-a"
        alias.symlink_to(pa)
        for label, path in (("trailing slash", Path(str(pa) + "/")), ("symlinked path", alias),
                            ("a subdirectory", sub)):
            got, _ = tv.resolve_installed(two, project=path)
            check(f"per-project: {label} is the same project", got.plugins.get("rails-stack"), "1.41.0")
        # #1427: the slash where it really arrives, in the RECORD. `Path(str(p) + "/")` above
        # cannot fail -- pathlib already dropped the slash -- so a string comparison of the
        # recorded projectPath would pass it and fail this.
        slashed = fake_home(tmp / "g2", marketplace_version="1.73.0", plugins={
            "rails-stack@claude-skills": [rec("1.41.0", "2026-08-01T00:00:00Z", str(pa) + "/")]})
        got_sl, _ = tv.resolve_installed(slashed, project=pa)
        check("per-project: a trailing slash in the recorded projectPath is the same project",
              got_sl.plugins.get("rails-stack"), "1.41.0")
        # #1427: a linked worktree lives OUTSIDE the project root; its `.git` file names the main one.
        wt = tmp / "proj-a-wt"
        (wt / "app").mkdir(parents=True)
        (wt / ".git").write_text(f"gitdir: {pa / '.git' / 'worktrees' / 'wt'}\n", encoding="utf-8")
        got_wt, _ = tv.resolve_installed(two, project=wt / "app")
        check("per-project: a linked worktree of A is A", got_wt.plugins.get("rails-stack"), "1.41.0")
        # ...and a record made from INSIDE the worktree names the worktree itself (#1474 review):
        # mapping the session to the main checkout must not stop that record matching.
        in_wt = fake_home(tmp / "g3", marketplace_version="1.73.0", plugins={
            "rails-stack@claude-skills": [rec("1.41.0", "2026-08-01T00:00:00Z", str(wt))]})
        got_iw, _ = tv.resolve_installed(in_wt, project=wt / "app")
        check("per-project: a record naming the worktree itself applies in it",
              got_iw.plugins.get("rails-stack"), "1.41.0")
        # #1427: case alone differs. `samefile` is replaced by a case-folding stand-in so this runs
        # on CI's Linux runner too, which does not fold case, rather than only on APFS.
        real_samefile = tv.os.path.samefile
        tv.os.path.samefile = lambda a, b: str(a).lower() == str(b).lower()
        try:
            got_up, _ = tv.resolve_installed(two, project=tmp / "PROJ-A")
        finally:
            tv.os.path.samefile = real_samefile
        check("per-project: a path differing only in case is the same project",
              got_up.plugins.get("rails-stack"), "1.41.0")
        # A sibling whose name merely starts with the project's is NOT inside it.
        sibling = tmp / "proj-a-other"
        sibling.mkdir()
        got_s, _ = tv.resolve_installed(two, project=sibling)
        check("per-project: a same-prefix sibling is another project", "rails-stack" in got_s.plugins, False)

        # Through main(): A is BEHIND a published set equal to B's install. Machine-wide
        # resolution read B's versions and called A up to date (exit 0); the truth is drift (1).
        rc = tv.main(["--home", str(two), "--published-from", str(pub), "--project", str(pa)])
        check("per-project: a project behind the machine's newest install is drift, not current",
              rc, tv.EXIT_FINDINGS)
        rc = tv.main(["--home", str(two), "--published-from", str(pub), "--project", str(pb)])
        check("per-project: the project that IS current still reads current", rc, tv.EXIT_OK)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = tv.main(["--home", str(two), "--project", str(pa), "--installed-path", "rails-stack"])
        check("installed-path: prints this project's tree", (rc, out.getvalue().strip()),
              (tv.EXIT_OK, "/cache/1.41.0"))
        with contextlib.redirect_stderr(io.StringIO()):
            rc = tv.main(["--home", str(two), "--project", str(nowhere),
                          "--installed-path", "rails-stack"])
        check("installed-path: no record for this project -> 2, never an empty 0", rc, tv.EXIT_UNUSABLE)

        # -- arming is scoped to real drift ---------------------------------------------
        marker = tv.marker_path(proj)
        if marker.is_file():
            marker.unlink()
        tv.main(["--home", str(full), "--published-from", str(pub), "--project", str(proj),
                 "--arm", "step-1"])
        check("arm: no marker written when already at target", marker.is_file(), False)
        tv.main(["--home", str(stale), "--published-from", str(pub), "--project", str(proj),
                 "--arm", "step-1"])
        check("arm: marker written on real drift", marker.is_file(), True)

    failed = [msg for ok, msg in RESULTS if not ok]
    for msg in failed:
        print(f"  FAIL {msg}")
    print(f"{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


def resolve(home: Path):
    return tv.resolve_installed(home)


if __name__ == "__main__":
    import sys
    sys.exit(run())
