#!/usr/bin/env python3
"""Resolve what a Kamal destination changes, so a deploy never half-applies one (#1465).

Run:  python3 kamal_destination.py plan [DESTINATION]        # the files and commands, as JSON
      python3 kamal_destination.py rails-env [DESTINATION]   # the RAILS_ENV Kamal resolves for every role
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
- `-d` does not set RAILS_ENV. Each role's container gets the env Kamal resolves for it: the top-level
  `env` (its `clear` hash, or, with no `clear`/`secret`/`tags` key, the whole hash), then the role's own `env`, then the
  host's env tags (`Role#env(host)`). The credentials environment is that resolved value, never assumed
  from the destination's name, and never hard-coded to "production".
- Rails picks `config/credentials/<RAILS_ENV>.yml.enc` if it exists, else `config/credentials.yml.enc`;
  the key falls back separately (`config/credentials/<RAILS_ENV>.key`, else `config/master.key`).

`rails-env` asks Kamal's own loader for every role's resolved env on every host rather than
re-implementing the merge or the resolution: two implementations are two answers. It exits 2 when it
cannot ask (no Ruby, no kamal gem, no config), when no role sets RAILS_ENV, and when the roles do not
agree (two values, or some roles setting it and others not). One deploy writes one credentials
environment; a guessed one encrypts credentials the app will never read, so "could not tell" must never
read as "production".

`plan` names file paths and commands only. It never emits a command that prints resolved values
(`kamal secrets print` does), because an agent runs what the plan gives it.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# A destination becomes a file name and a shell word: nothing that could leave the directory or split.
DESTINATION = re.compile(r"\A[a-z0-9][a-z0-9_-]{0,31}\Z")

BASE_CONFIG = "config/deploy.yml"

# Kamal's own loader, asked for each role's RESOLVED env on each host: `Role#env(host)` merges the
# top-level env, the role's env and the host's env tags, exactly as the container receives it.
# `create_from` is what the CLI itself calls. One line per role and host: role, host, value ("" = unset).
RAILS_ENV_RUBY = (
    'require "kamal"; '
    'c = Kamal::Configuration.create_from(config_file: Pathname.new("config/deploy.yml"), '
    'destination: (ARGV[0].to_s.empty? ? nil : ARGV[0]), version: "resolve"); '
    'c.roles.each { |r| r.hosts.each { |h| puts [r.name, h, r.env(h).clear["RAILS_ENV"].to_s].join("\t") } }'
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
    """File paths and commands only: nothing here resolves, or prints, a value."""
    d = check_destination(destination)
    return {
        "destination": d,
        "setup": kamal_argv("setup", d),
        "deploy": kamal_argv("deploy", d),
        # The dotenv file Kamal reads for this destination, after .kamal/secrets-common.
        "env_file": f".kamal/secrets.{d}" if d else ".kamal/secrets",
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
    rows = [line.split("\t") for line in proc.stdout.splitlines() if line.strip()]
    rows = [r + [""] * (3 - len(r)) for r in rows]
    where = f"config/deploy.{d}.yml" if d else BASE_CONFIG
    if not rows:
        raise Unusable("the merged config has no role with a host, so no container env to read")
    values = sorted({value for _role, _host, value in rows})
    if values == [""]:
        raise Unusable(f"no role sets RAILS_ENV in the merged config; set it (in {where}'s env.clear) rather than guess")
    if len(values) > 1:
        seen = ", ".join(f"{role}@{host}={value or '(unset)'}" for role, host, value in rows)
        raise Unusable(f"the roles do not agree on RAILS_ENV ({seen}); one deploy writes one credentials environment")
    return values[0]


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

    # THE DEFECT: a destination that reaches the env file but not the command.
    staging = plan("staging")
    check_that("a destination is passed to kamal deploy", staging["deploy"] == ["kamal", "deploy", "-d", "staging"])
    check_that("a destination is passed to kamal setup", staging["setup"] == ["kamal", "setup", "-d", "staging"])
    check_that("the destination's env file is the one written", staging["env_file"] == ".kamal/secrets.staging")
    check_that("a destination needs its overlay", staging["overlay"] == "config/deploy.staging.yml")
    # The plan is run by an agent, so it carries only what the prose uses, and no command that prints
    # resolved values (`kamal secrets print` puts every KEY=value, kamal 2.12.0 cli/secrets.rb L32-36).
    check_that("the plan carries only the fields the prose uses",
               set(staging) == {"destination", "setup", "deploy", "env_file", "overlay"})
    check_that("the plan never hands out a command that prints resolved values",
               not any(isinstance(v, list) and "print" in v for v in staging.values()))
    # ITS CONTROL: no destination changes nothing, so the fix cannot be "always pass -d".
    none = plan(None)
    check_that("no destination: no -d", none["deploy"] == ["kamal", "deploy"] and none["setup"] == ["kamal", "setup"])
    check_that("no destination: .kamal/secrets, no overlay", none["env_file"] == ".kamal/secrets" and none["overlay"] is None)
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

        # RAILS_ENV IS ASKED OF KAMAL, per role and host, never guessed. The loader prints one
        # `role<TAB>host<TAB>value` line per role and host; these fixtures stand in for it.
        (root / "config/deploy.yml").write_text("service: x\n")
        seen: list[list[str]] = []

        def runner(out: str, rc: int = 0):
            def run(argv, **_kw):
                seen.append(argv)
                return SimpleNamespace(returncode=rc, stdout=out, stderr="boom" if rc else "")
            return run

        check_that("the resolved RAILS_ENV is returned", rails_env(None, root, runner("web\t10.0.0.1\tproduction\n")) == "production")
        check_that("the loader is asked with no destination as an empty argument", seen[-1][-1] == "")
        check_that("roles that agree give their one value",
                   rails_env(None, root, runner("web\ta\tstaging\njob\tb\tstaging\n")) == "staging")
        for label, dest, run, needle in (
            ("a destination with no overlay is unusable, not a guess", "staging", runner("web\ta\tproduction"), "config/deploy.staging.yml"),
            ("an unset RAILS_ENV is unusable, not production", None, runner("web\ta\t\n"), "no role sets RAILS_ENV"),
            ("roles with different RAILS_ENV values are unusable", None,
             runner("web\ta\tproduction\njob\tb\tstaging\n"), "roles do not agree"),
            ("a role with no RAILS_ENV beside one with it is unusable", None,
             runner("web\ta\tproduction\njob\tb\t\n"), "job@b=(unset)"),
            ("a config with no role on a host is unusable", None, runner(""), "no role with a host"),
            ("a failing loader is unusable", None, runner("", rc=1), "loader failed"),
        ):
            try:
                rails_env(dest, root, run)
                failures.append(label)
            except Unusable as e:
                check_that(label, needle in str(e))
        (root / "config/deploy.staging.yml").write_text("env:\n  clear:\n    RAILS_ENV: staging\n")
        check_that("the destination is handed to Kamal's loader",
                   rails_env("staging", root, runner("web\ta\tstaging")) == "staging" and seen[-1][-1] == "staging")

    # THE REAL LOADER. The merge and the per-role resolution are Kamal's, so they are asked of Kamal
    # itself; the mocks above cannot tell a right resolution from a wrong one. CI installs kamal 2.12.0
    # (gates.yml) so these run there. With no kamal gem this is a SKIP (exit 3, which the doctor
    # reports as skip): it did not run, and it is not a pass. With kamal present, a loader error FAILS.
    skipped = ""
    probe = subprocess.run(["ruby", "-e", 'require "kamal"'], capture_output=True, text=True) \
        if shutil.which("ruby") else None
    if probe is None or probe.returncode != 0:
        skipped = ("the real Kamal loader fixtures did NOT run: "
                   + ("no ruby on PATH" if probe is None else "the kamal gem is not installed")
                   + " (gem install kamal -v 2.12.0); the mocked fixtures ran")
    else:
        base = ("service: probe\nimage: acme/probe\nservers:\n  web: [10.0.0.1]\nregistry:\n  username: acme\n"
                # A NAME, not a value: the loader validates the shape and resolves nothing.
                "  password: [KAMAL_REGISTRY_PASSWORD]\n"
                "builder:\n  arch: amd64\n")
        overlays = {
            "staging": "env:\n  clear:\n    RAILS_ENV: staging\n",
            "qa": "servers:\n  web: [10.9.9.9]\n",
            # A ROLE's own env overrides the top level: what the container gets, not what env.clear says.
            "roleover": "servers:\n  web:\n    hosts: [10.0.0.1]\n    env:\n      clear:\n        RAILS_ENV: staging\n",
            "split": ("servers:\n  web: [10.0.0.1]\n  job:\n    hosts: [10.0.0.2]\n    cmd: bin/jobs\n"
                      "    env:\n      clear:\n        RAILS_ENV: staging\n"),
        }
        expected = {
            "staging": ("Kamal's own loader reads the destination's RAILS_ENV", "staging"),
            None: ("...the base config's without -d", "production"),
            "qa": ("...and a destination that sets none inherits the base's, not its own name", "production"),
            "roleover": ("a role's own env overrides the top-level RAILS_ENV", "staging"),
        }
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "config").mkdir()
            (root / "config/deploy.yml").write_text(base + "env:\n  clear:\n    RAILS_ENV: production\n")
            for name, text in overlays.items():
                (root / f"config/deploy.{name}.yml").write_text(text)
            for dest, (label, want) in expected.items():
                try:
                    check_that(label, rails_env(dest, root) == want)
                except Unusable as e:
                    failures.append(f"{label}: {e}")
            try:
                rails_env("split", root)
                failures.append("roles that resolve different RAILS_ENV values are refused by the real loader")
            except Unusable as e:
                check_that("roles that resolve different RAILS_ENV values are refused by the real loader",
                           "roles do not agree" in str(e))
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "config").mkdir()
            # The FLAT form: `env:` with no `clear:` is all clear (kamal 2.12.0 configuration/env.rb L8).
            (root / "config/deploy.yml").write_text(base + "env:\n  RAILS_ENV: production\n")
            try:
                check_that("the flat env form is read as clear", rails_env(None, root) == "production")
            except Unusable as e:
                failures.append(f"the flat env form is read as clear: {e}")

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
    if failures:
        print(f"kamal_destination selftest: FAILED ({len(failures)} failure(s))")
        return 1
    if skipped:
        # The first line is the doctor's skip reason (exit 3 = ran but could not check everything).
        print(f"INCOMPLETE: {skipped}")
        print("kamal_destination selftest: incomplete (0 failure(s), real-loader fixtures skipped)")
        return 3
    print("kamal_destination selftest: ok (0 failure(s))")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(selftest())
    sys.exit(main(sys.argv[1:]))
