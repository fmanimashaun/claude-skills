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
        # #1964. A container that lacks a tool the runner has makes a guard read green here and fail there (release run 38297902322: pg_isready).
        Mutation(
            "postgresql-client is not installed, so pg_isready is the host's absence again",
            'HOST_PACKAGES="postgresql-client lsof procps"',
            'HOST_PACKAGES="lsof procps"',
            "the container installs the host tools a selftest probes",
        ),
        Mutation(
            "the canary no longer asks for pg_isready",
            'CANARY_TOOLS="pg_isready lsof ps"',
            'CANARY_TOOLS="lsof ps"',
            "the container asserts pg_isready, lsof and ps are present",
        ),
        Mutation(
            "the canary is never run before a guard",
            'bash scripts/linux_check.sh --check-tools $LINUX_CHECK_CANARY_TOOLS || exit 3\n',
            "",
            "the host-tool canary runs after the install and before any guard",
        ),
        Mutation(
            "a failing canary is ignored and the guards run anyway",
            "--check-tools $LINUX_CHECK_CANARY_TOOLS || exit 3",
            "--check-tools $LINUX_CHECK_CANARY_TOOLS || true",
            "a failing canary aborts the container",
        ),
        Mutation(
            "a missing tool exits 0, so the absent tool reads as present",
            'Add its package to HOST_PACKAGES in scripts/linux_check.sh." >&2\n    exit 3',
            'Add its package to HOST_PACKAGES in scripts/linux_check.sh." >&2\n    exit 0',
            "a missing tool FAILS CLOSED",
        ),
        Mutation(
            "no tool names passes, so an empty canary checks nothing and says ok",
            'if [ "$#" -lt 1 ]; then echo "linux_check: --check-tools needs',
            'if [ "$#" -lt 0 ]; then echo "linux_check: --check-tools needs',
            "--check-tools with no names is a usage error",
        ),
    ),
)
