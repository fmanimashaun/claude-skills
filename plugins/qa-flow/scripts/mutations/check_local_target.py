"""Mutation guard: check_local_target. Run by scripts/mutation_check.py (#1954). The one mechanism behind "k6 and ZAP never run against production":
an opt-in that is looser than the host it names, a userinfo URL the opt-in can launder, or a missing target read as local must each fail."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_local_target",
    subject="scripts/check_local_target.py",
    selftest="scripts/check_local_target.py",
    needs=("scripts/robot_descriptor.py",),
    mutations=(
        Mutation(
            "any non-empty QA_ALLOW_REMOTE_TARGET allows any host (a yes, not a host)",
            "    if host and allow.strip().lower() == host.lower():",
            "    if host and allow.strip():",
            "allow='1'",
        ),
        Mutation(
            "the opt-in matches a host suffix, so naming example.com allows prod.example.com",
            "    if host and allow.strip().lower() == host.lower():",
            "    if host and host.lower().endswith(allow.strip().lower()):",
            "allow='example.com'",
        ),
        Mutation(
            "a userinfo URL can be allowed by naming the host it really dials",
            '    if not why.startswith("dials "):',
            "    if False:",
            "allow='prod.example.com'",
        ),
        Mutation(
            "an empty target is read as this machine",
            "    why = local_url(raw)\n",
            "    why = local_url(raw) if raw else None\n",
            "verdict('', allow='')",
        ),
        Mutation(
            "the command line ignores QA_BASE_URL",
            'os.environ.get("QA_BASE_URL", "")',
            '""',
            "cli env={'QA_BASE_URL': 'https://prod.example.com'}",
        ),
    ),
)
