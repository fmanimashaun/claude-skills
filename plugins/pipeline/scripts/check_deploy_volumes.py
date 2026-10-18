#!/usr/bin/env python3
"""Every persistent volume a Kamal deploy mounts is a bind mount under ONE data root (#2141).

Run:  python3 check_deploy_volumes.py [--root /srv/<service>] [config/deploy.yml ...]
      python3 check_deploy_volumes.py --selftest
Exit: 0 every persistent mount is under the root
      1 a finding per line: a named Docker volume, a bind mount outside the root, a relative accessory directory, a path with `..`
      2 unusable: no config, a file that is not YAML, no `service:` to name the default root

WHY (the owner, 17 Oct 2026: "this storage approach should be a shippable skill for all rails deployment"; proven first on a production
Retask host, Retask #2094). A named Docker volume keeps its data wherever Docker keeps volumes, so moving the data to a new disk misses
it, and an accessory's relative `directories:` entry lands under the SSH user's home. With every persistent mount under one root, a
move is one copy and one mount (`reference/data-root.md`). This is the check that keeps a mount added later from landing elsewhere.

WHAT IT READS: `config/deploy.yml` and every `config/deploy.<destination>.yml` overlay beside it (Kamal deep-merges an overlay over the
base), unless files are named. The app's `volumes:`, and each accessory's `volumes:` and `directories:`. `files:` are configuration the
deploy uploads, not data, and are not judged. ERB is not run: each `<%= ... %>` reads as a placeholder, so a value built in ERB is judged
by the text around it, and a mount written wholly in ERB is a finding (it cannot be shown to be under the root).

The root is `--root`, else `DATA_ROOT` (the environment, then `.kamal/deploy.env`), else `/srv/<service>` (the config's `service:`): the
same order `bin/data-root` uses, so the check and the host agree on one root.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - PyYAML ships with every python3 this repo supports
    yaml = None

PLACEHOLDER = "__erb__"


def load(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"<%=.*?%>", PLACEHOLDER, text, flags=re.S)   # an expression reads as a placeholder
    text = re.sub(r"<%.*?%>", "", text, flags=re.S)               # control flow and comments drop out
    data = yaml.safe_load(text)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a YAML mapping")
    return data


def judge(where: str, entry, root: str, findings: list[str]) -> None:
    text = str(entry)
    source = text.split(":", 1)[0]
    if PLACEHOLDER in source:
        findings.append(f"{where}: {text!r} builds its host path in ERB, so it cannot be shown to be under {root}; write the path out")
    elif not source.startswith("/"):
        kind = ("a relative directory (Kamal puts it under the SSH user's home)" if where.endswith("directories")
                else "a named Docker volume")
        findings.append(f"{where}: {text!r} is {kind}; use {root}/<name>:<container path>")
    elif os.path.normpath(source) != source.rstrip("/") or "/../" in f"{source}/" or "/./" in f"{source}/":
        findings.append(f"{where}: {text!r} is not a plain path (no `..` or `.`)")
    elif source != root and not source.startswith(root + "/"):
        findings.append(f"{where}: {text!r} is a bind mount outside {root}")


def check(configs: list[dict], root: str) -> list[str]:
    findings: list[str] = []
    for name, config in configs:
        prefix = "" if name == "config/deploy.yml" else f"{name}: "
        for v in config.get("volumes") or []:
            judge(f"{prefix}volumes", v, root, findings)
        for acc_name, acc in (config.get("accessories") or {}).items():
            if not isinstance(acc, dict):
                continue
            for v in acc.get("volumes") or []:
                judge(f"{prefix}accessories.{acc_name}.volumes", v, root, findings)
            for v in acc.get("directories") or []:
                judge(f"{prefix}accessories.{acc_name}.directories", v, root, findings)
    return findings


def run(paths: list[Path], root: str | None) -> tuple[int, list[str]]:
    if yaml is None:
        return 2, ["PyYAML is not importable: nothing was checked"]
    if not paths:
        return 2, ["no config/deploy.yml: nothing was checked"]
    try:
        configs = [(p.as_posix() if p.parent.name != "config" else f"config/{p.name}", load(p)) for p in paths]
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return 2, [f"unreadable: {exc}"]
    if root is None:
        root = deploy_env_root(paths[0])
    if root is None:
        service = next((c.get("service") for _, c in configs if c.get("service")), None)
        if not service or PLACEHOLDER in str(service):
            return 2, ["no `service:` to name the default root: give --root"]
        root = f"/srv/{service}"
    root = root.rstrip("/") or "/"
    if root == "/" or not root.startswith("/"):
        return 2, [f"the data root {root!r} must be an absolute directory below /"]
    findings = check(configs, root)
    if findings:
        return 1, [f"{len(findings)} persistent mount(s) outside {root} (#2141):", *[f"  - {f}" for f in findings]]
    return 0, [f"every persistent mount is under {root}"]


def deploy_env_root(config_path: Path) -> str | None:
    """DATA_ROOT from the environment, else from .kamal/deploy.env beside the config's project (read, never sourced)."""
    if os.environ.get("DATA_ROOT"):
        return os.environ["DATA_ROOT"]
    env_file = config_path.resolve().parent.parent / ".kamal" / "deploy.env"
    if not env_file.is_file():
        return None
    value = None
    for line in env_file.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*DATA_ROOT=(.*)$", line)
        if m:
            value = re.sub(r"\s+#.*$", "", m.group(1)).strip().strip("'\"") or None
    return value


def default_paths(cwd: Path) -> list[Path]:
    base = cwd / "config" / "deploy.yml"
    if not base.is_file():
        return []
    return [base, *sorted(p for p in (cwd / "config").glob("deploy.*.yml") if p.name != "deploy.yml")]


def selftest() -> int:
    good = """service: shop
image: me/shop
volumes:
  - "/srv/shop/storage:/rails/storage"
servers:
  web:
    - <%= ENV.fetch("WEB_HOST") %>
accessories:
  db:
    image: postgres:18
    host: <%= ENV.fetch("WEB_HOST") %>
    directories:
      - /srv/shop/postgres:/var/lib/postgresql
    files:
      - config/init.sql:/docker-entrypoint-initdb.d/setup.sql
"""
    cases = [
        ("the good config passes, ERB host lines and `files:` included", good, None, 0, "every persistent mount is under /srv/shop"),
        ("a named volume on the app", good.replace('"/srv/shop/storage:/rails/storage"', '"shop_storage:/rails/storage"'), None, 1, "a named Docker volume"),
        ("a bind mount outside the root", good.replace("/srv/shop/storage:", "/var/data:"), None, 1, "outside /srv/shop"),
        ("a relative accessory directory", good.replace("- /srv/shop/postgres:", "- data:"), None, 1, "a relative directory"),
        ("an escape with ..", good.replace("- /srv/shop/postgres:", "- /srv/shop/../root/pg:"), None, 1, "not a plain path"),
        ("a sibling that only shares the prefix", good.replace("/srv/shop/storage:", "/srv/shop-old/storage:"), None, 1, "outside /srv/shop"),
        ("a named volume on an accessory added later",
         good + "  cache:\n    image: valkey/valkey:8\n    volumes:\n      - valkey:/data\n", None, 1, "accessories.cache.volumes"),
        ("a mount built in ERB", good.replace('"/srv/shop/storage:/rails/storage"', '"<%= ENV["DATA"] %>:/rails/storage"'), None, 1, "builds its host path in ERB"),
        ("--root names another root", good, "/mnt/storage", 1, "outside /mnt/storage"),
        ("no service and no --root is unusable", good.replace("service: shop\n", ""), None, 2, "give --root"),
        ("a root of / is refused", good, "/", 2, "absolute directory below /"),
        ("not YAML is unusable", "volumes: [unclosed\n", "/srv/x", 2, "unreadable"),
    ]
    bad = 0
    with tempfile.TemporaryDirectory() as tmp:
        for name, text, root, want_code, want_text in cases:
            path = Path(tmp) / "deploy.yml"
            path.write_text(text, encoding="utf-8")
            code, lines = run([path], root)
            blob = "\n".join(lines)
            if code != want_code or want_text not in blob:
                bad += 1
                print(f"FAIL {name}: exit {code} (wanted {want_code}), output {blob!r}")
        # An overlay is judged as well: a named volume in config/deploy.staging.yml is a finding, named by its file.
        cfg = Path(tmp) / "proj" / "config"
        cfg.mkdir(parents=True)
        (cfg / "deploy.yml").write_text(good, encoding="utf-8")
        (cfg / "deploy.staging.yml").write_text('volumes:\n  - "staging_storage:/rails/storage"\n', encoding="utf-8")
        code, lines = run(default_paths(cfg.parent), None)
        if code != 1 or "config/deploy.staging.yml: volumes" not in "\n".join(lines):
            bad += 1
            print(f"FAIL an overlay's named volume is a finding: exit {code}, {lines}")
        # DATA_ROOT in .kamal/deploy.env names the root, as bin/data-root reads it.
        (cfg.parent / ".kamal").mkdir()
        (cfg.parent / ".kamal" / "deploy.env").write_text("DATA_ROOT=/mnt/data   # the volume\n", encoding="utf-8")
        (cfg / "deploy.staging.yml").unlink()
        saved = os.environ.pop("DATA_ROOT", None)
        code, lines = run(default_paths(cfg.parent), None)
        if saved is not None:
            os.environ["DATA_ROOT"] = saved
        if code != 1 or "outside /mnt/data" not in "\n".join(lines):
            bad += 1
            print(f"FAIL DATA_ROOT from .kamal/deploy.env names the root: exit {code}, {lines}")
        if run(default_paths(Path(tmp) / "nowhere"), None)[0] != 2:
            bad += 1
            print("FAIL no config/deploy.yml is unusable (exit 2), never clean")
    if bad == 0:
        print(f"check_deploy_volumes selftest: {len(cases) + 3} cases pass")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--root")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    code, lines = run(args.files or default_paths(Path.cwd()), args.root)
    print("\n".join(lines), file=sys.stderr if code else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
