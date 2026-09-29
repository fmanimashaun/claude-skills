#!/usr/bin/env python3
"""Print the first release tag whose marketplace.json carries a given plugin version.

A downstream report pins the rails-stack version the project ran, and that version is not the
marketplace version: one machine can hold a marketplace clone at 1.148.0 (rails-stack 1.68.0)
while a project on it runs rails-stack 1.63.0, which first shipped in v1.138.0 (#1407). The
triager searches the skill tree the reporter's agent actually had, so it needs this mapping, not
the marketplace tag (#1386 review).

Usage:
  python3 scripts/skill_version_tag.py rails-stack 1.63.0     # -> v1.138.0
  python3 scripts/skill_version_tag.py --selftest

Exit: 0 printed a tag · 1 no release carries that version · 2 cannot read the repo.
A warning on stderr names any later tag carrying the same version with a different skills tree.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

MANIFEST = ".claude-plugin/marketplace.json"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def carries(manifest_text: str, plugin: str, version: str) -> bool:
    """Whether a marketplace.json text lists `plugin` at `version`. Unreadable is False."""
    try:
        data = json.loads(manifest_text)
    except ValueError:
        return False
    plugins = data.get("plugins") if isinstance(data, dict) else None
    return isinstance(plugins, list) and any(
        isinstance(p, dict) and p.get("name") == plugin and p.get("version") == version
        for p in plugins)


def tags_carrying(repo: Path, plugin: str, version: str) -> list[str]:
    """Every release tag carrying `plugin` at `version`, oldest first (version sort)."""
    tags = _git(repo, "tag", "--list", "v*", "--sort=v:refname")
    if tags.returncode != 0:
        raise OSError(tags.stderr.strip() or "git tag failed")
    found = []
    for tag in tags.stdout.split():
        shown = _git(repo, "show", f"{tag}:{MANIFEST}")
        # Early tags predate the manifest; that is "not carried", not an error.
        if shown.returncode == 0 and carries(shown.stdout, plugin, version):
            found.append(tag)
    return found


def first_tag(repo: Path, plugin: str, version: str) -> str | None:
    found = tags_carrying(repo, plugin, version)
    return found[0] if found else None


def differing_trees(repo: Path, tags: list[str], tree: str = "skills") -> list[str]:
    """The tags after the first whose `tree` differs from the first's.

    One rails-stack version is usually one skills tree, but not always: measured over every tag,
    42 of 111 rails-stack versions ship in more than one tag, and 1.42.2's four tags hold two
    different skills trees -- the skills changed without a version bump (#1427). A reporter on
    such a version may have had either tree, so the triager must search each.
    """
    def tree_id(tag: str) -> str:
        # `--verify -q`: a plain rev-parse ECHOES an argument it cannot resolve, so two tags that
        # both lack the tree would compare as different.
        got = _git(repo, "rev-parse", "--verify", "-q", f"{tag}:{tree}")
        return got.stdout.strip() if got.returncode == 0 else ""
    if len(tags) < 2:
        return []
    base = tree_id(tags[0])
    return [t for t in tags[1:] if tree_id(t) != base]


def main(argv: list[str]) -> int:
    if argv[1:] == ["--selftest"]:
        return selftest()
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        tags = tags_carrying(Path.cwd(), argv[1], argv[2])
        other = differing_trees(Path.cwd(), tags)
    except OSError as exc:
        print(f"skill_version_tag: {exc}", file=sys.stderr)
        return 2
    if not tags:
        print(f"no release tag carries {argv[1]} {argv[2]}", file=sys.stderr)
        return 1
    if other:
        print(f"warning: {argv[1]} {argv[2]} ships a different skills tree in {' '.join(other)} "
              f"than in {tags[0]}; search each", file=sys.stderr)
    print(tags[0])
    return 0


def selftest() -> int:
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: object = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    check("carries: listed version", carries('{"plugins":[{"name":"rails-stack","version":"1.63.0"}]}',
                                             "rails-stack", "1.63.0"))
    check("carries: other version", not carries('{"plugins":[{"name":"rails-stack","version":"1.68.0"}]}',
                                                "rails-stack", "1.63.0"))
    check("carries: other plugin", not carries('{"plugins":[{"name":"rails-flow","version":"1.63.0"}]}',
                                               "rails-stack", "1.63.0"))
    check("carries: unreadable is not carried", not carries("not json", "rails-stack", "1.63.0"))

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)

        def commit_tag(tag: str, manifest: dict | None) -> None:
            path = repo / MANIFEST
            if manifest is None:
                (repo / "README").write_text(tag, encoding="utf-8")
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(manifest), encoding="utf-8")
            _git(repo, "add", "README" if manifest is None else MANIFEST)
            _git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", tag)
            _git(repo, "tag", tag)

        _git(repo, "init", "-q")
        commit_tag("v1.0.0", None)                                    # predates the manifest
        stack = lambda v: {"plugins": [{"name": "rails-stack", "version": v}]}  # noqa: E731
        commit_tag("v1.2.0", stack("1.63.0"))
        commit_tag("v1.3.0", stack("1.63.0"))
        # Both carry 1.68.0. By version v1.9.0 is first; lexically "v1.10.0" < "v1.9.0". Created
        # v1.10.0 first, so creation order would pick it too.
        commit_tag("v1.10.0", stack("1.68.0"))
        commit_tag("v1.9.0", stack("1.68.0"))

        check("first tag carrying a version", first_tag(repo, "rails-stack", "1.63.0") == "v1.2.0",
              first_tag(repo, "rails-stack", "1.63.0"))
        check("version sort, not lexical", first_tag(repo, "rails-stack", "1.68.0") == "v1.9.0",
              first_tag(repo, "rails-stack", "1.68.0"))
        check("an unshipped version is None", first_tag(repo, "rails-stack", "9.9.9") is None)
        # Exact match only: a version that merely starts like a shipped one is not it.
        check("a near-miss version is not a match", first_tag(repo, "rails-stack", "1.63") is None)

        # Through main(), as the triager calls it: the tag must be on STDOUT, because the triager
        # captures stdout with $(...). A tag on stderr reads as "no release" and the search
        # silently falls back to dev.
        def run_main(*args: str) -> tuple[int, str, str]:
            out, err = io.StringIO(), io.StringIO()
            here = Path.cwd()
            try:
                os.chdir(repo)
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    rc = main(["skill_version_tag.py", *args])
            finally:
                os.chdir(here)
            return rc, out.getvalue().strip(), err.getvalue()

        rc, out, _ = run_main("rails-stack", "1.63.0")
        check("main(): the tag is printed on stdout, exit 0", (rc, out) == (0, "v1.2.0"), (rc, out))
        rc, out, err = run_main("rails-stack", "9.9.9")
        check("main(): an unshipped version exits 1 with nothing on stdout",
              (rc, out) == (1, "") and "9.9.9" in err, (rc, out, err))
        check("a tag with no manifest is skipped, not fatal",
              first_tag(repo, "rails-stack", "1.63.0") is not None)

        # One version, two skills trees (#1427: measured for rails-stack 1.42.2). v1.2.0 and
        # v1.3.0 both carry 1.63.0 with no skills tree at all, so they agree; a v1.3.1 that adds
        # one differs, and the warning names it without moving the tag off stdout.
        (repo / "skills").mkdir()
        (repo / "skills" / "rule.md").write_text("changed without a version bump", encoding="utf-8")
        _git(repo, "add", "skills")
        commit_tag("v1.3.1", stack("1.63.0"))
        rc, out, err = run_main("rails-stack", "1.63.0")
        check("main(): a later tag with a different skills tree is named on stderr",
              (rc, out) == (0, "v1.2.0") and "v1.3.1" in err and "v1.3.0" not in err, (rc, out, err))
        rc, out, err = run_main("rails-stack", "1.68.0")
        check("main(): tags that agree on the skills tree warn about nothing",
              (rc, out, err) == (0, "v1.9.0", ""), (rc, out, err))

    # Exit 2 is "cannot read the repo", never "no release": outside any repository `git tag` fails.
    with tempfile.TemporaryDirectory() as bare:
        out, err = io.StringIO(), io.StringIO()
        here = Path.cwd()
        env_before = os.environ.get("GIT_CEILING_DIRECTORIES")
        try:
            os.chdir(bare)
            os.environ["GIT_CEILING_DIRECTORIES"] = str(Path(bare).resolve().parent)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = main(["skill_version_tag.py", "rails-stack", "1.63.0"])
        finally:
            os.chdir(here)
            if env_before is None:
                os.environ.pop("GIT_CEILING_DIRECTORIES", None)
            else:
                os.environ["GIT_CEILING_DIRECTORIES"] = env_before
        check("main(): outside a repository exits 2, not 1", (rc, out.getvalue()) == (2, ""),
              (rc, out.getvalue(), err.getvalue()))

    print(f"skill_version_tag selftest: {checks} check(s)")
    if failures:
        print(f"{len(failures)} FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
