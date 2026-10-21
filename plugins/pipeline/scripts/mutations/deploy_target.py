"""Mutation guard: deploy_target. Declared here, run by scripts/mutation_check.py (#2179).

Each mutation puts a default back where the descriptor should decide: an unknown project is sent to a known host, an
unreadable manifest is read as "nothing declared", a stack with no deploy agent is run anyway, the descriptor is no longer
asked. The selftest's fixtures (no stack, a broken manifest, no deploy declared, a second stack) must each turn red.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="deploy_target",
    subject="scripts/deploy_target.py",
    selftest="scripts/deploy_target.py",
    # Read, not imported: the selftest's last checks run against the SHIPPED command, and the detector it imports sits beside it.
    needs=("commands/deploy-cloud.md", "scripts/detect_stack.py"),
    mutations=(
        Mutation(
            "no stack detected still names an agent (a default target)",
            '        return 1, {"stacks": [], "problems": [f"no stack was detected',
            '        return 0, {"stacks": [], "target": "default", "artifact": "", "agent": "default:deployer", "problems": [f"no stack was detected',
            "an empty project stops with exit 1",
        ),
        Mutation(
            "a detector that cannot judge is read as no stack (exit 1, not 2)",
            '        return 2, {"stacks": stacks, "problems": report["problems"]}',
            '        return 1, {"stacks": stacks, "problems": report["problems"]}',
            "an unreadable manifest is exit 2",
        ),
        Mutation(
            "a stack that declares no deploy agent is run anyway",
            '        return 1, {"stacks": stacks, "problems": [f"the detected stack ({ids}) declares no `deploy` agent',
            '        return 0, {"stacks": stacks, "target": "", "artifact": "", "agent": "", "problems": [f"the detected stack ({ids}) declares no `deploy` agent',
            "a stack that declares no deploy target is exit 1",
        ),
        Mutation(
            "the descriptor is not asked: a fixed agent is returned for any detected stack",
            '"agent": deploy["agent"],',
            '"agent": "alpha-stack:deployer",',
            "a stack that declares its own deploy agent is chosen by the descriptor alone",
        ),
    ),
)
