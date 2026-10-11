"""Mutation guard: robot_descriptor. Declared here, run by scripts/mutation_check.py (#866). The descriptor and the image runner are where the
robot is aimed; a target off this machine, a skipped seed or a retry must each fail (#1837)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="robot_descriptor",
    subject="scripts/robot_descriptor.py",
    selftest="scripts/robot_descriptor.py",
    needs=("scaffold/qa/seed/image-e2e", "scaffold/qa/seed/assert-local-target.ts", "scaffold/qa/seed/local-target.setup.ts",
           "scaffold/qa/e2e/support/local-target.ts"),
    mutations=(
        Mutation(
            "userinfo in a descriptor URL is accepted",
            "    if parts.username is not None or parts.password is not None:",
            "    if False:",
            "descriptor: a base_url with userinfo hiding a real host is refused",
        ),
        Mutation(
            "a host that only starts like this machine is accepted (prefix match)",
            "    if host not in LOCAL:",
            "    if not any(host.startswith(h) for h in LOCAL):",
            "descriptor: a base_url that only starts like this machine is refused",
        ),
        Mutation(
            "an empty boundary passes with no stated reason",
            "        if not isinstance(doc.get(\"boundary_none_reason\"), str) or not doc[\"boundary_none_reason\"].strip():",
            "        if False:",
            "descriptor: an empty boundary needs a stated reason",
        ),
        Mutation(
            "a role created by something other than a screen passes",
            "        if not isinstance(r.get(\"created_on\"), str) or not r[\"created_on\"].startswith(\"/\"):",
            "        if False:",
            "descriptor: a role created by something other than a screen is refused",
        ),
    ),
)
