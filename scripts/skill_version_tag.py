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
"""
from __future__ import annotations

import json
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


def first_tag(repo: Path, plugin: str, version: str) -> str | None:
    tags = _git(repo, "tag", "--list", "v*", "--sort=v:refname")
    if tags.returncode != 0:
        raise OSError(tags.stderr.strip() or "git tag failed")
    for tag in tags.stdout.split():
        shown = _git(repo, "show", f"{tag}:{MANIFEST}")
        # Early tags predate the manifest; that is "not carried", not an error.
        if shown.returncode == 0 and carries(shown.stdout, plugin, version):
            return tag
    return None


def main(argv: list[str]) -> int:
    if argv[1:] == ["--selftest"]:
        return selftest()
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        tag = first_tag(Path.cwd(), argv[1], argv[2])
    except OSError as exc:
        print(f"skill_version_tag: {exc}", file=sys.stderr)
        return 2
    if tag is None:
        print(f"no release tag carries {argv[1]} {argv[2]}", file=sys.stderr)
        return 1
    print(tag)
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
        check("a tag with no manifest is skipped, not fatal",
              first_tag(repo, "rails-stack", "1.63.0") is not None)

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
