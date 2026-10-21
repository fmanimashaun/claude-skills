#!/usr/bin/env python3
"""Every shipped plugin installs only its own directory, and nothing maintainer-only (#2182).

Run:  python3 scripts/check_plugin_install_shape.py
      python3 scripts/check_plugin_install_shape.py --selftest

WHY. An install copies a plugin's `source` directory. Until #2182 `rails-stack` had `source: ./`, so
installing it copied the whole repository: 1,061 tracked files including the maintainer-only
`.claude/` (the 1.76.0 install was measured holding it), where its seven skills are 67 files.
That breaks plugin-boundaries rule 3: nothing maintainer-only ships to clients.

RULES, over `.claude-plugin/marketplace.json` and the tracked files (`git ls-files`):
  root-source      a plugin's `source` is the repository root (`./`, `.`, ``).
  maintainer-dir   a plugin's source holds a `.claude/` directory.
  too-many-files   a plugin's source holds more tracked files than CEILING (a whole-repo source
                   reads as ~1,000; the largest real plugin is a few hundred).
  missing-source   a plugin's `source` names a directory with no tracked files.
A plugin whose `source` is not a relative path (a remote source) is out of scope and reported as such.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CEILING = 600


def tracked(root: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=root, check=True, capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if line]


def findings(root: Path) -> list[str]:
    manifest = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    files = tracked(root)
    out: list[str] = []
    for entry in manifest.get("plugins") or []:
        name, source = entry.get("name", "?"), entry.get("source")
        if not isinstance(source, str):
            out.append(f"{name}: source is not a relative path ({source!r}); not checked")
            continue
        rel = source.strip().removeprefix("./").strip("/")
        if rel in ("", "."):
            out.append(f"[root-source] {name}: source {source!r} is the repository root, so an install copies the whole repo")
            continue
        inside = [f for f in files if f.startswith(rel + "/")]
        if not inside:
            out.append(f"[missing-source] {name}: source {source!r} holds no tracked files")
            continue
        claude = sorted({f.split("/")[len(rel.split("/"))] for f in inside if f[len(rel) + 1:].startswith(".claude/")})
        if claude:
            out.append(f"[maintainer-dir] {name}: source {source!r} holds .claude/, which is maintainer-only")
        if len(inside) > CEILING:
            out.append(f"[too-many-files] {name}: {len(inside)} tracked files under {source!r} (ceiling {CEILING})")
    return out


def selftest() -> int:
    failures: list[str] = []

    def case(label: str, plugins: list[dict], files: list[str], want: list[str]) -> None:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"plugins": plugins}))
            for f in files:
                (root / f).parent.mkdir(parents=True, exist_ok=True)
                (root / f).write_text("x")
            subprocess.run(["git", "add", "--", ".claude-plugin/marketplace.json", *files], cwd=root, check=True)
            got = findings(root)
            ok = len(got) == len(want) and all(w in g for w, g in zip(want, got))
            if not ok:
                failures.append(f"{label}: wanted {want}, got {got}")

    good = ["plugins/rails-stack/skills/a/SKILL.md", "plugins/rails-flow/commands/x.md"]
    case("a plugin directory per plugin is clean",
         [{"name": "rails-stack", "source": "./plugins/rails-stack"}, {"name": "rails-flow", "source": "./plugins/rails-flow"}], good, [])
    case("a root source is a finding (the pre-#2182 rails-stack)", [{"name": "rails-stack", "source": "./"}], good, ["[root-source]"])
    case("a bare dot source is a finding", [{"name": "rails-stack", "source": "."}], good, ["[root-source]"])
    case(".claude/ inside a plugin is a finding", [{"name": "rails-flow", "source": "./plugins/rails-flow"}],
         [*good, "plugins/rails-flow/.claude/commands/m.md"], ["[maintainer-dir]"])
    case("a .claude-plugin/ manifest is not .claude/", [{"name": "rails-flow", "source": "./plugins/rails-flow"}],
         [*good, "plugins/rails-flow/.claude-plugin/plugin.json"], [])
    case("too many files is a finding", [{"name": "big", "source": "./plugins/big"}],
         [f"plugins/big/f{i}.md" for i in range(CEILING + 1)], ["[too-many-files]"])
    case("a source with no tracked files is a finding", [{"name": "ghost", "source": "./plugins/ghost"}], good, ["[missing-source]"])
    case("a sibling directory sharing a prefix is not inside", [{"name": "ghost", "source": "./plugins/ghost"}],
         [*good, "plugins/ghost-extra/a.md"], ["[missing-source]"])
    if failures:
        print("check_plugin_install_shape selftest FAILED:\n  " + "\n  ".join(failures))
        return 1
    print("check_plugin_install_shape selftest: 8 cases ok")
    return 0


def main() -> int:
    if "--selftest" in sys.argv[1:]:
        return selftest()
    out = findings(ROOT)
    for line in out:
        print(line)
    bad = [line for line in out if line.startswith("[")]
    print(f"plugin install shape: {len(bad)} finding(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
