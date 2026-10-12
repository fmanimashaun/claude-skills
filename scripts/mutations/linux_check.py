"""Mutation guard: scripts/linux_check.sh (#1738). Run by scripts/mutation_check.py.

The script is the Linux check a maintainer runs before pushing a guard change. Its whole value is that it cannot be mistaken for a pass:
no docker, or a docker that is not running, is a refusal; a failing container is a failure. Each of those is broken once here.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="linux_check",
    subject="scripts/linux_check.sh",
    selftest="scripts/linux_check_selftest.py",
    mutations=(
        Mutation(
            "a missing docker is not noticed, so nothing runs and the script still goes on",
            'if ! command -v "$DOCKER" >/dev/null 2>&1; then',
            "if false; then",
            "docker absent FAILS CLOSED",
        ),
        Mutation(
            "a missing docker exits 0, so the skipped Linux check reads as a pass",
            'This is not a pass." >&2\n  exit 2\nfi\nif ! "$DOCKER" info',
            'This is not a pass." >&2\n  exit 0\nfi\nif ! "$DOCKER" info',
            "docker absent FAILS CLOSED",
        ),
        Mutation(
            "a docker that is not running is not noticed",
            'if ! "$DOCKER" info >/dev/null 2>&1; then',
            "if false; then",
            "docker installed but NOT RUNNING fails closed",
        ),
        Mutation(
            "no arguments runs nothing and passes",
            'if [ "$#" -eq 0 ]; then',
            "if false; then",
            "no arguments is a usage error",
        ),
        Mutation(
            "the image floats on latest",
            'IMAGE="${LINUX_CHECK_IMAGE:-ubuntu:24.04}"',
            'IMAGE="${LINUX_CHECK_IMAGE:-ubuntu:latest}"',
            "the image is pinned by a tag, never latest",
        ),
        Mutation(
            "the image cannot be overridden",
            'IMAGE="${LINUX_CHECK_IMAGE:-ubuntu:24.04}"',
            'IMAGE="ubuntu:24.04"',
            "LINUX_CHECK_IMAGE overrides the image",
        ),
        Mutation(
            "the repository is mounted somewhere the commands do not look",
            '-v "$PWD":/work -w /work',
            '-v "$PWD":/mnt -w /mnt',
            "the repository is mounted at /work and is the working directory",
        ),
        Mutation(
            "the container is left behind",
            'run --rm -e PYTHONDONTWRITEBYTECODE=1',
            'run -e PYTHONDONTWRITEBYTECODE=1',
            "docker is run with --rm",
        ),
        Mutation(
            "root-owned bytecode lands in the checkout",
            'run --rm -e PYTHONDONTWRITEBYTECODE=1 ',
            "run --rm ",
            "bytecode is not written into the mount",
        ),
        Mutation(
            "a guard name with a shell metacharacter is accepted",
            "        *[!A-Za-z0-9_]*) echo",
            "        *[!A-Za-z0-9_\\;]*) echo",
            "a guard name with a shell metacharacter is refused",
        ),
        Mutation(
            "--run hands a selftest path to the container as a guard",
            '      specs+=("run:$2")',
            '      specs+=("guard:$2")',
            "every guard and selftest is handed to the container, in order",
        ),
        Mutation(
            "git is not installed in the container",
            "apt-get install -y -qq python3 git bash ca-certificates",
            "apt-get install -y -qq python3 bash ca-certificates",
            "the container installs python3, git and bash",
        ),
        Mutation(
            "a failing selftest inside the container is swallowed",
            'python3 "${spec#run:}" || rc=1 ;;',
            'python3 "${spec#run:}" || true ;;',
            "a failing guard OR selftest in the container makes the container script exit non-zero",
        ),
        Mutation(
            "a failing container is reported as a pass",
            'if [ "$status" -ne 0 ]; then',
            "if false; then",
            "a container that fails makes the script fail",
        ),
        Mutation(
            "the container's exit status is flattened",
            '  exit "$status"',
            "  exit 1",
            "the container's own exit status is the script's",
        ),
    ),
)
