#!/usr/bin/env python3
"""Resolve what a Kamal destination changes, so a deploy never half-applies one (#1465).

Run:  python3 kamal_destination.py plan [DESTINATION]        # the files and commands, as JSON
      python3 kamal_destination.py rails-env [DESTINATION]   # RAILS_ENV of the MERGED config
      python3 kamal_destination.py --selftest

WHY. `/pipeline:deploy-cloud staging` wrote `.kamal/secrets.staging` and then ran `kamal deploy` with no
`-d`, so Kamal read `.kamal/secrets` and the base `config/deploy.yml` and the staging file sat unused.
A destination is ONE decision with several consequences; this names all of them in one place, so the
command and the agent carry the destination through instead of each remembering part of it.

VERIFIED against Kamal 2.12.0 and Rails 8.1.4 (doctrine-verifier, #1465; the sources are in the
pipeline CHANGELOG entry):
- `-d <dest>` deep-merges `config/deploy.<dest>.yml` over `config/deploy.yml` (the destination wins;
  hashes merge, arrays are replaced), and raises when that file is missing.
- Secrets: `.kamal/secrets-common`, then `.kamal/secrets` with no destination or
  `.kamal/secrets.<dest>` with one; later files win. With `-d`, `.kamal/secrets` is NOT read.
- `-d` does not set RAILS_ENV. That is whatever the merged `env.clear` says, so the credentials
  environment is read from the merged config, never assumed from the destination's name, and never
  hard-coded to "production".
- Rails picks `config/credentials/<RAILS_ENV>.yml.enc` if it exists, else `config/credentials.yml.enc`;
  the key falls back separately (`config/credentials/<RAILS_ENV>.key`, else `config/master.key`).

`rails-env` asks Kamal's own loader for the merged config rather than re-implementing the merge: two
implementations of one merge are two answers. It exits 2 when it cannot ask (no Ruby, no kamal gem, no
config) or the merged config names no RAILS_ENV. A guessed environment encrypts credentials the app
will never read, so "could not tell" must never read as "production".
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# A destination becomes a file name and a shell word: nothing that could leave the directory or split.
DESTINATION = re.compile(r"\A[a-z0-9][a-z0-9_-]{0,31}\Z")

SECRETS_COMMON = ".kamal/secrets-common"
BASE_CONFIG = "config/deploy.yml"

# Kamal's own loader, asked for the merged env. `create_from` is what the CLI itself calls.
RAILS_ENV_RUBY = (
    'require "kamal"; '
    'c = Kamal::Configuration.create_from(config_file: Pathname.new("config/deploy.yml"), '
    'destination: (ARGV[0].to_s.empty? ? nil : ARGV[0]), version: "resolve"); '
    'print((c.raw_config.env || {}).dig("clear", "RAILS_ENV").to_s)'
)


class Unusable(Exception):
    """The answer could not be determined; exit 2, never a guess."""


def check_destination(destination: str | None) -> str | None:
    if destination in (None, ""):
        return None
    if not DESTINATION.match(destination):
        raise Unusable(f"{destination!r} is not a destination name: lowercase letters, digits, '-' and '_' only")
    return destination


def kamal_argv(verb: str, destination: str | None) -> list[str]:
    """The command, with `-d` whenever there is a destination. Without it Kamal reads neither file."""
    return ["kamal", verb] + (["-d", destination] if destination else [])


def plan(destination: str | None) -> dict:
    d = check_destination(destination)
    secrets_file = f".kamal/secrets.{d}" if d else ".kamal/secrets"
    return {
        "destination": d,
        "setup": kamal_argv("setup", d),
        "deploy": kamal_argv("deploy", d),
        "config": kamal_argv("config", d),
        "secrets_print": kamal_argv("secrets", d)[:2] + ["print"] + (["-d", d] if d else []),
        # Written by the configurator, in the order Kamal reads them.
        "secrets_read": [SECRETS_COMMON, secrets_file],
        "secrets_write": secrets_file,
        "secrets_unread": ".kamal/secrets" if d else None,
        "deploy_config": [BASE_CONFIG] + ([f"config/deploy.{d}.yml"] if d else []),
        "overlay": f"config/deploy.{d}.yml" if d else None,
    }


def credentials_paths(rails_env: str, root: Path) -> dict:
    """What Rails will read for this RAILS_ENV, each half falling back on its own, as Rails does."""
    content = f"config/credentials/{rails_env}.yml.enc"
    key = f"config/credentials/{rails_env}.key"
    return {
        "rails_env": rails_env,
        "content": content if (root / content).exists() else "config/credentials.yml.enc",
        "key": key if (root / key).exists() else "config/master.key",
        # Where a NEW per-environment file is written, as a matched pair.
        "write_content": content,
        "write_key": key,
    }


def rails_env(destination: str | None, root: Path, run=subprocess.run) -> str:
    d = check_destination(destination)
    if not (root / BASE_CONFIG).is_file():
        raise Unusable(f"no {BASE_CONFIG} under {root}")
    if d and not (root / f"config/deploy.{d}.yml").is_file():
        raise Unusable(f"no config/deploy.{d}.yml: Kamal refuses -d {d} without it, so generate it first")
    try:
        proc = run(["ruby", "-e", RAILS_ENV_RUBY, d or ""], cwd=root, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Unusable(f"could not run Kamal's config loader: {e}") from e
    if proc.returncode != 0:
        first = (proc.stderr or proc.stdout).strip().splitlines()[:1]
        raise Unusable(f"Kamal's config loader failed: {first[0] if first else 'no output'}")
    env = proc.stdout.strip()
    if not env:
        where = f"config/deploy.{d}.yml" if d else BASE_CONFIG
        raise Unusable(f"the merged config sets no env.clear.RAILS_ENV; set it (in {where}) rather than guess")
    return env


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("plan", "rails-env") or len(argv) > 2:
        print(__doc__.split("\n\n")[0])
        print("usage: kamal_destination.py plan|rails-env [DESTINATION]")
        return 2
    destination = argv[1] if len(argv) == 2 else None
    try:
        if argv[0] == "plan":
            print(json.dumps(plan(destination), indent=2))
        else:
            env = rails_env(destination, Path.cwd())
            print(json.dumps(credentials_paths(env, Path.cwd()), indent=2))
    except Unusable as e:
        print(f"UNUSABLE: {e}", file=sys.stderr)
        return 2
    return 0


def selftest() -> int:
    import tempfile
    from types import SimpleNamespace

    failures: list[str] = []

    def check_that(label: str, ok: bool) -> None:
        if not ok:
            failures.append(label)

    # THE DEFECT: a destination that reaches the secrets file but not the command.
    staging = plan("staging")
    check_that("a destination is passed to kamal deploy", staging["deploy"] == ["kamal", "deploy", "-d", "staging"])
    check_that("a destination is passed to kamal setup", staging["setup"] == ["kamal", "setup", "-d", "staging"])
    check_that("a destination is passed to kamal config and secrets print",
               staging["config"][-2:] == ["-d", "staging"] and staging["secrets_print"] == ["kamal", "secrets", "print", "-d", "staging"])
    check_that("the destination's secrets file is the one written", staging["secrets_write"] == ".kamal/secrets.staging")
    check_that("secrets are read common first, then the destination's",
               staging["secrets_read"] == [".kamal/secrets-common", ".kamal/secrets.staging"])
    check_that("the plain secrets file is named as unread under a destination", staging["secrets_unread"] == ".kamal/secrets")
    check_that("a destination needs its overlay", staging["overlay"] == "config/deploy.staging.yml"
               and staging["deploy_config"] == ["config/deploy.yml", "config/deploy.staging.yml"])
    # ITS CONTROL: no destination changes nothing, so the fix cannot be "always pass -d".
    none = plan(None)
    check_that("no destination: no -d", none["deploy"] == ["kamal", "deploy"] and none["setup"] == ["kamal", "setup"])
    check_that("no destination: .kamal/secrets, no overlay",
               none["secrets_write"] == ".kamal/secrets" and none["overlay"] is None and none["secrets_unread"] is None)
    check_that("an empty destination is no destination", plan("") == none)

    # A destination is a file name and a shell word.
    for bad in ("../prod", "staging; rm -rf /", "Staging", "-d", "a" * 40, "prod/../x"):
        try:
            plan(bad)
            failures.append(f"an unsafe destination is refused: {bad!r}")
        except Unusable:
            pass

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        # CREDENTIALS FOLLOW RAILS_ENV, and each half falls back on its own.
        check_that("no per-environment files: the shared credentials and master.key",
                   credentials_paths("staging", root) | {} == {
                       "rails_env": "staging", "content": "config/credentials.yml.enc", "key": "config/master.key",
                       "write_content": "config/credentials/staging.yml.enc", "write_key": "config/credentials/staging.key"})
        (root / "config/credentials").mkdir(parents=True)
        (root / "config/credentials/staging.yml.enc").write_text("x")
        paths = credentials_paths("staging", root)
        check_that("the content file falls back independently of the key",
                   paths["content"] == "config/credentials/staging.yml.enc" and paths["key"] == "config/master.key")
        (root / "config/credentials/staging.key").write_text("k")
        check_that("both per-environment files present: both used",
                   credentials_paths("staging", root)["key"] == "config/credentials/staging.key")

        # RAILS_ENV IS ASKED OF KAMAL'S MERGED CONFIG, never guessed.
        (root / "config/deploy.yml").write_text("service: x\n")
        seen: list[list[str]] = []

        def runner(out: str, rc: int = 0):
            def run(argv, **_kw):
                seen.append(argv)
                return SimpleNamespace(returncode=rc, stdout=out, stderr="boom" if rc else "")
            return run

        check_that("the merged RAILS_ENV is returned", rails_env(None, root, runner("production")) == "production")
        check_that("the loader is asked with no destination as an empty argument", seen[-1][-1] == "")
        for label, dest, run, needle in (
            ("a destination with no overlay is unusable, not a guess", "staging", runner("production"), "config/deploy.staging.yml"),
            ("an unset RAILS_ENV is unusable, not production", None, runner(""), "sets no env.clear.RAILS_ENV"),
            ("a failing loader is unusable", None, runner("", rc=1), "loader failed"),
        ):
            try:
                rails_env(dest, root, run)
                failures.append(label)
            except Unusable as e:
                check_that(label, needle in str(e))
        (root / "config/deploy.staging.yml").write_text("env:\n  clear:\n    RAILS_ENV: staging\n")
        check_that("the destination is handed to Kamal's loader", rails_env("staging", root, runner("staging")) == "staging"
                   and seen[-1][-1] == "staging")

    # THE REAL LOADER, when Kamal is installed: the merge is Kamal's, so ask it for real. The third
    # case is the one a name-based guess gets wrong: a destination that sets no RAILS_ENV inherits.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "config").mkdir()
        (root / "config/deploy.yml").write_text(
            "service: probe\nimage: acme/probe\nservers:\n  web: [10.0.0.1]\nregistry:\n  username: acme\n"
            # A NAME, not a value: the loader validates the shape and resolves no secret.
            "  password: [KAMAL_REGISTRY_PASSWORD]\n"
            "builder:\n  arch: amd64\n"
            "env:\n  clear:\n    RAILS_ENV: production\n")
        (root / "config/deploy.staging.yml").write_text("env:\n  clear:\n    RAILS_ENV: staging\n")
        (root / "config/deploy.qa.yml").write_text("servers:\n  web: [10.9.9.9]\n")
        try:
            real = [rails_env("staging", root), rails_env(None, root), rails_env("qa", root)]
        except Unusable as e:
            real = None
            print(f"note: the real Kamal loader was not exercised here ({e}); the fixtures above still ran")
        if real is not None:
            check_that("Kamal's own loader reads the destination's RAILS_ENV", real[0] == "staging")
            check_that("...the base config's without -d", real[1] == "production")
            check_that("...and a destination that sets none inherits the base's, not its own name", real[2] == "production")

    # THE SHIPPED CALL SITES. The helper is not the fix unless the command and the agent use it,
    # and the hard-coded environment is gone from both.
    here = Path(__file__).resolve().parents[1]
    for rel in ("commands/deploy-cloud.md", "agents/kamal-configurator.md"):
        p = here / rel
        text = p.read_text(encoding="utf-8") if p.is_file() else ""
        check_that(f"{rel} runs kamal_destination.py", "scripts/kamal_destination.py" in text)
        check_that(f"{rel} hard-codes no credentials environment", 'env = "production"' not in text)

    for f in failures:
        print(f"selftest FAIL: {f}")
    print(f"kamal_destination selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    sys.exit(main(sys.argv[1:]))
