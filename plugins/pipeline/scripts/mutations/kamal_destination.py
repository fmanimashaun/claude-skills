"""Mutation guard: kamal_destination. Declared here, run by scripts/mutation_check.py (#1465).

Each mutation half-applies a destination again: the secrets file is scoped and the command is not, the
overlay is forgotten, the credentials environment is guessed from a name or assumed to be production.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="kamal_destination",
    subject="scripts/kamal_destination.py",
    selftest="scripts/kamal_destination.py",
    needs=("commands/deploy-cloud.md", "agents/kamal-configurator.md"),
    mutations=(
        Mutation(
            "the destination never reaches the kamal command (the #1465 defect, restored)",
            '    return ["kamal", verb] + (["-d", destination] if destination else [])',
            '    return ["kamal", verb]',
            "a destination is passed to kamal deploy",
        ),
        Mutation(
            "-d is passed even with no destination",
            '    return ["kamal", verb] + (["-d", destination] if destination else [])',
            '    return ["kamal", verb, "-d", destination or "production"]',
            "no destination: no -d",
        ),
        Mutation(
            "the env file ignores the destination",
            '        "env_file": f".kamal/secrets.{d}" if d else ".kamal/secrets",',
            '        "env_file": ".kamal/secrets",',
            "the destination's env file is the one written",
        ),
        Mutation(
            "no overlay is named for a destination",
            '        "overlay": f"config/deploy.{d}.yml" if d else None,',
            '        "overlay": None,',
            "a destination needs its overlay",
        ),
        Mutation(
            "any string is accepted as a destination",
            "    if not DESTINATION.match(destination):",
            "    if False:",
            "an unsafe destination is refused",
        ),
        Mutation(
            "the key falls back together with the content, not on its own",
            '        "key": key if (root / key).exists() else "config/master.key",',
            '        "key": key if (root / content).exists() else "config/master.key",',
            "the content file falls back independently of the key",
        ),
        Mutation(
            "an unset RAILS_ENV is assumed to be production",
            '    if values == [""]:\n        raise',
            '    if values == [""]:\n        return "production"\n        raise',
            "an unset RAILS_ENV is unusable, not production",
        ),
        Mutation(
            "the destination is not handed to Kamal's loader",
            '        proc = run(["ruby", "-e", RAILS_ENV_RUBY, d or ""], cwd=root, capture_output=True, text=True, timeout=60)',
            '        proc = run(["ruby", "-e", RAILS_ENV_RUBY, ""], cwd=root, capture_output=True, text=True, timeout=60)',
            "the destination is handed to Kamal's loader",
        ),
        Mutation(
            "a missing overlay is not caught before asking Kamal",
            '    if d and not (root / f"config/deploy.{d}.yml").is_file():',
            "    if False:",
            "a destination with no overlay is unusable, not a guess",
        ),
        Mutation(
            "RAILS_ENV is read from the top-level env.clear again, not the env Kamal resolves (R1508-1)",
            """    'c.roles.each { |r| r.hosts.each { |h| puts [r.name, h, r.env(h).clear["RAILS_ENV"].to_s].join("\\t") } }'""",
            """    'puts ["web", "h", (c.raw_config.env || {}).dig("clear", "RAILS_ENV").to_s].join("\\t")'""",
            "a role's own env overrides the top-level RAILS_ENV",
        ),
        Mutation(
            "each role's RAILS_ENV is read from the raw clear hash, so the flat env form reads as unset",
            'r.env(h).clear["RAILS_ENV"].to_s',
            '((c.raw_config.env || {})["clear"] || {})["RAILS_ENV"].to_s',
            "the flat env form is read as clear",
        ),
        Mutation(
            "roles that disagree on RAILS_ENV are accepted, and one of them is picked",
            "    if len(values) > 1:",
            "    if False:",
            "roles with different RAILS_ENV values are unusable",
        ),
        Mutation(
            "the plan hands the agent a command that prints every resolved value (R1508-3)",
            '        "deploy": kamal_argv("deploy", d),\n',
            '        "deploy": kamal_argv("deploy", d),\n        "secrets_print": kamal_argv("secrets", d) + ["print"],\n',
            "the plan never hands out a command that prints resolved values",
        ),
    ),
)
