#!/usr/bin/env python3
"""Resolve the installed toolchain version, compare it against what is published, and
carry a durable marker across the restart an update requires.

This is pillar 1 of the autonomous flow driver (EPIC #488): the bootstrap gate that runs
*before* any work, so the driver never builds on a stale toolchain.

Five things the EPIC's design sketch got wrong about the substrate, each found by reading
the real files rather than the issue body. They are why this script is longer than
"compare two numbers":

  1. `known_marketplaces.json` records NO version. It carries `source`, `installLocation`
     and `lastUpdated` only. The installed marketplace version lives one level down, in
     `<installLocation>/.claude-plugin/marketplace.json`.

  2. `installed_plugins.json` maps `<plugin>@<marketplace>` to a LIST of install records,
     not to one. Two versions of the same plugin coexist in the cache — this machine has
     rails-flow at both 1.19.0 and 1.18.2, same scope, distinguished only by
     `lastUpdated`. Reading `[0]` or `[-1]` picks arbitrarily and can report the stale one
     as installed, which is the exact failure this gate exists to prevent.

  3. The manifest's per-plugin versions are NOT all present. Four of the five plugin
     entries in `marketplace.json` have no `version` key at all.

  4. ...because the two version sources are DISJOINT, not redundant. `rails-stack` is a
     skills bundle with no plugin directory, so it is versioned only in `marketplace.json`;
     the other four are code plugins versioned only in their own
     `plugins/<name>/.claude-plugin/plugin.json`. A resolver reading either source alone
     silently misses the other set — and misses it as "up to date", the worst direction.

  5. The drift is real and was live while this was written: installed 1.72.0 against a
     published 1.73.0.

Exit codes:  0 up to date (or the marker resolved cleanly) · 1 findings (update available,
             or a plugin failed to reach target) · 2 unusable input — cannot resolve one
             side at all.

Exit 2 is never folded into 0. "I could not read the installed state" is not "you are up
to date"; reporting it as clean would be the skip-is-not-a-pass defect the repo's own
doctor was built to avoid.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

EXIT_OK, EXIT_FINDINGS, EXIT_UNUSABLE = 0, 1, 2

MARKETPLACE = "claude-skills"
MARKER_NAME = ".toolchain-update"


# --------------------------------------------------------------------------- data

@dataclass
class Toolchain:
    """One side of the comparison: a marketplace version plus every plugin version."""

    marketplace: str | None = None
    plugins: dict[str, str] = field(default_factory=dict)
    # Cache entries for a plugin that are NOT the newest record. Not an error — Claude Code
    # keeps old versions on disk — but they are what a naive [0] read would return, so the
    # gate names them rather than hiding them.
    shadowed: dict[str, list[str]] = field(default_factory=dict)


def read_json(path: Path):
    """Return parsed JSON, or None. Never raises: a missing or corrupt file is a fact to
    report, not a traceback."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ----------------------------------------------------------------- resolve installed

def newest_record(records: list[dict]) -> dict | None:
    """Pick the install record a running Claude Code would actually use.

    Finding 2. `installed_plugins.json` values are lists, and this machine really does hold
    two records for rails-flow. `lastUpdated` is the only field that orders them; entries
    without one sort last rather than crashing the gate.
    """
    if not isinstance(records, list) or not records:
        return None
    return max(records, key=lambda r: (r or {}).get("lastUpdated") or "")


def resolve_installed(home: Path, marketplace: str = MARKETPLACE) -> tuple[Toolchain, list[str]]:
    """Read what is installed on this machine. Returns (toolchain, problems)."""
    problems: list[str] = []
    tc = Toolchain()
    base = home / ".claude" / "plugins"

    known = read_json(base / "known_marketplaces.json")
    if not isinstance(known, dict) or marketplace not in known:
        problems.append(f"marketplace {marketplace!r} is not installed (known_marketplaces.json)")
    else:
        # Finding 1: the version is NOT here. Only the location is.
        loc = (known[marketplace] or {}).get("installLocation")
        manifest = read_json(Path(loc) / ".claude-plugin" / "marketplace.json") if loc else None
        if not isinstance(manifest, dict):
            problems.append("installed marketplace.json is missing or unreadable")
        else:
            tc.marketplace = (manifest.get("metadata") or {}).get("version")
            if not tc.marketplace:
                problems.append("installed marketplace.json has no metadata.version")

    installed = read_json(base / "installed_plugins.json")
    if not isinstance(installed, dict) or not isinstance(installed.get("plugins"), dict):
        problems.append("installed_plugins.json is missing or unreadable")
        return tc, problems

    suffix = f"@{marketplace}"
    for key, records in installed["plugins"].items():
        if not key.endswith(suffix):
            continue
        name = key[: -len(suffix)]
        rec = newest_record(records)
        if rec is None or not rec.get("version"):
            problems.append(f"{name}: no usable install record")
            continue
        tc.plugins[name] = rec["version"]
        others = [r.get("version") for r in records if r is not rec and (r or {}).get("version")]
        if others:
            tc.shadowed[name] = others

    if not tc.plugins:
        problems.append(f"no plugins from {marketplace!r} are installed")
    return tc, problems


# ---------------------------------------------------------------- resolve published

def read_manifest_pair(root: Path) -> tuple[Toolchain, list[str]]:
    """Read a marketplace checkout — the source repo, or the installed clone.

    Finding 4, the load-bearing one. The two version sources are DISJOINT:

        rails-stack   -> marketplace.json plugins[].version   (skills bundle, no plugin dir)
        every other   -> plugins/<name>/.claude-plugin/plugin.json

    So both are read and unioned. A plugin listed in the manifest that resolves from
    neither source is a finding, not a silent omission — otherwise a plugin whose version
    became unreadable would compare equal to itself and pass.
    """
    problems: list[str] = []
    tc = Toolchain()
    manifest = read_json(root / ".claude-plugin" / "marketplace.json")
    if not isinstance(manifest, dict):
        problems.append(f"{root}: no readable .claude-plugin/marketplace.json")
        return tc, problems

    tc.marketplace = (manifest.get("metadata") or {}).get("version")
    if not tc.marketplace:
        problems.append(f"{root}: manifest has no metadata.version")

    for entry in manifest.get("plugins") or []:
        name = entry.get("name")
        if not name:
            continue
        version = entry.get("version")          # source A — rails-stack only
        if not version:                         # source B — the four code plugins
            pj = read_json(root / "plugins" / name / ".claude-plugin" / "plugin.json")
            version = (pj or {}).get("version")
        if version:
            tc.plugins[name] = version
        else:
            problems.append(f"{name}: no version in the manifest and no readable plugin.json")
    return tc, problems


def fetch_published(repo: str, ref: str = "HEAD") -> tuple[Toolchain, list[str]]:
    """Resolve the published side over `gh`.

    Only the manifest is fetched, then one plugin.json per plugin that needs one. The
    manifest is fetched first precisely because finding 4 means it does not name every
    version — it names which plugins exist, and the rest is a second lookup.
    """
    def api(path: str):
        cmd = ["gh", "api", f"repos/{repo}/contents/{path}",
               "-H", "Accept: application/vnd.github.raw"]
        if ref != "HEAD":
            cmd += ["-f", f"ref={ref}"]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        return json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else None

    problems: list[str] = []
    tc = Toolchain()
    manifest = api(".claude-plugin/marketplace.json")
    if not isinstance(manifest, dict):
        problems.append(f"could not fetch the published manifest from {repo} (gh unavailable or unauthenticated?)")
        return tc, problems

    tc.marketplace = (manifest.get("metadata") or {}).get("version")
    for entry in manifest.get("plugins") or []:
        name = entry.get("name")
        if not name:
            continue
        version = entry.get("version")
        if not version:
            pj = api(f"plugins/{name}/.claude-plugin/plugin.json")
            version = (pj or {}).get("version")
        if version:
            tc.plugins[name] = version
        else:
            problems.append(f"{name}: could not resolve a published version")
    return tc, problems


# ------------------------------------------------------------------------ compare

def parse_version(v: str) -> tuple:
    """Compare numerically, so 1.9.0 < 1.10.0. A non-numeric component sorts as 0 rather
    than raising — an unparseable version must still produce a verdict."""
    parts = []
    for chunk in str(v).lstrip("v").split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts + [0] * (3 - len(parts)))[:3]


def compare(installed: Toolchain, published: Toolchain) -> list[str]:
    """Return one line per drift. Empty means up to date."""
    findings: list[str] = []
    if installed.marketplace and published.marketplace:
        if parse_version(installed.marketplace) < parse_version(published.marketplace):
            findings.append(f"marketplace: {installed.marketplace} -> {published.marketplace}")

    for name, want in sorted(published.plugins.items()):
        have = installed.plugins.get(name)
        if have is None:
            findings.append(f"{name}: not installed (published {want})")
        elif parse_version(have) < parse_version(want):
            findings.append(f"{name}: {have} -> {want}")
    return findings


# ------------------------------------------------------------------------- marker

def marker_path(project: Path) -> Path:
    return project / "docs" / "brain" / MARKER_NAME


def write_marker(project: Path, target: Toolchain, resume_step: str) -> Path:
    """Record the pending update so a restart does not lose it.

    Sits beside `docs/brain/.last-review`, following the existing convention for machine
    state: a dot-file in the brain, not a new top-level path.
    """
    p = marker_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "status": "update-pending",
        "target": {"marketplace": target.marketplace, "plugins": target.plugins},
        "resume_step": resume_step,
    }, indent=2) + "\n", encoding="utf-8")
    return p


def resume(project: Path, installed: Toolchain) -> tuple[int, list[str]]:
    """Post-restart half of the gate: did every plugin actually reach target?

    Idempotent by construction — with no marker there is nothing to resume, which is a
    clean 0 and not a finding. That is what makes a second re-run after a good update a
    no-op, as the acceptance criteria require.

    The gate is deliberately asymmetric: a plugin BEHIND target is a finding and the driver
    must stop rather than proceed degraded, while a plugin AHEAD of target is not. Landing
    past the target still satisfies "at least the version we armed for", and failing on it
    would make the marker go stale the moment a newer release appeared mid-restart.
    """
    p = marker_path(project)
    marker = read_json(p)
    if marker is None:
        return EXIT_OK, ["no update marker — nothing to resume"]
    target = (marker.get("target") or {})
    findings = []
    for name, want in sorted((target.get("plugins") or {}).items()):
        have = installed.plugins.get(name)
        if have is None:
            findings.append(f"{name}: target {want}, NOT INSTALLED")
        elif parse_version(have) < parse_version(want):
            findings.append(f"{name}: target {want}, still at {have}")
    want_mk = target.get("marketplace")
    if want_mk and installed.marketplace and parse_version(installed.marketplace) < parse_version(want_mk):
        findings.append(f"marketplace: target {want_mk}, still at {installed.marketplace}")

    if findings:
        return EXIT_FINDINGS, findings                 # escalate; do NOT clear the marker
    p.unlink()
    return EXIT_OK, [f"confirmed at target; marker cleared ({marker.get('resume_step', 'start')})"]


# --------------------------------------------------------------------------- main

def render(installed: Toolchain, published: Toolchain, findings: list[str]) -> None:
    print(f"installed marketplace: {installed.marketplace or '?'}")
    print(f"published marketplace: {published.marketplace or '?'}")
    for name in sorted(set(installed.plugins) | set(published.plugins)):
        have, want = installed.plugins.get(name, "—"), published.plugins.get(name, "—")
        flag = "  <- update" if have != "—" and want != "—" and parse_version(have) < parse_version(want) else ""
        print(f"  {name:14} {have:10} {want:10}{flag}")
    for name, others in sorted(installed.shadowed.items()):
        print(f"  note: {name} also has {', '.join(others)} in cache (older records, not active)")
    print()
    if findings:
        print(f"{len(findings)} update(s) available:")
        for f in findings:
            print(f"  - {f}")
    else:
        print("toolchain is up to date")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--home", type=Path, default=Path.home(), help="override $HOME (testing)")
    ap.add_argument("--repo", default="fmanimashaun/claude-skills")
    ap.add_argument("--published-from", type=Path,
                    help="read the published side from a local checkout instead of gh")
    ap.add_argument("--project", type=Path, default=Path.cwd(), help="project root holding docs/brain/")
    ap.add_argument("--arm", metavar="STEP", help="write the cross-restart marker, resuming at STEP")
    ap.add_argument("--resume", action="store_true", help="post-restart: confirm target reached, clear marker")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        from toolchain_version_selftest import run
        return run()

    installed, problems = resolve_installed(args.home)
    if args.resume:
        # Resume needs only the installed side; a network failure must not strand a marker.
        if not installed.plugins:
            for p in problems:
                print(f"unusable: {p}", file=sys.stderr)
            return EXIT_UNUSABLE
        code, lines = resume(args.project, installed)
        for line in lines:
            print(line)
        return code

    if args.published_from:
        published, pub_problems = read_manifest_pair(args.published_from)
    else:
        published, pub_problems = fetch_published(args.repo)

    if not installed.plugins or not published.plugins:
        for p in problems + pub_problems:
            print(f"unusable: {p}", file=sys.stderr)
        return EXIT_UNUSABLE                    # never 0 — see the module docstring
    for p in problems + pub_problems:
        print(f"note: {p}", file=sys.stderr)

    findings = compare(installed, published)
    render(installed, published, findings)
    # #923. A plugin that is installed but whose published version did not resolve (one gh fetch
    # failed) is UNUSABLE, not current: compare() never saw it, render() shows an em-dash for it, and
    # the verdict beneath would have read "up to date". Exit 2 is never folded into 0 -- per plugin.
    unresolved = sorted(n for n in installed.plugins if n not in published.plugins)
    if unresolved:
        for n in unresolved:
            print(f"unusable: {n}: published version unresolved — cannot tell whether it is current "
                  f"(gh fetch of its plugin.json failed?); re-run, or pass --published-from a clone", file=sys.stderr)
        return EXIT_UNUSABLE

    if args.arm:
        if not findings:
            print("\nnothing to arm — already at target")
            return EXIT_OK
        p = write_marker(args.project, published, args.arm)
        print(f"\nmarker written: {p}")
        print("restart Claude Code, then re-run with --resume")
    return EXIT_FINDINGS if findings else EXIT_OK


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
