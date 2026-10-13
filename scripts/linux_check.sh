#!/usr/bin/env bash
# Run mutation guards (or a named selftest) on Linux, in a container, before pushing a change to a guard (#1738).
#
#   scripts/linux_check.sh <guard> [more guards]        python3 scripts/mutation_check.py --guard <guard>, each
#   scripts/linux_check.sh --run scripts/x_selftest.py  python3 scripts/x_selftest.py (repeatable; mixes with guards)
#
# WHY. Ten guard findings appeared only on Linux (#1729) because the guards were only ever run on macOS first:
# GNU against BSD text tools, MAX_ARG_STRLEN, locale and scheduling. The release found them, five times. This runs the
# same command in ubuntu:24.04, the runner's OS, so the finding arrives before the push.
#
# FAILS CLOSED. No docker, or a docker that is not running, is exit 2 with a sentence: never a silent skip, because a
# skipped Linux check reads exactly like a passing one. A guard that fails in the container is exit 1.
#
# The repository is mounted at /work; the image is pinned by tag (LINUX_CHECK_IMAGE to override). PYTHONDONTWRITEBYTECODE
# keeps root-owned __pycache__ out of your checkout. A git worktree's .git file points outside the mount, so git-dependent
# guards are best run from a main checkout. The container has python3, git and bash, plus the host tools a selftest probes (HOST_PACKAGES below, asserted by a
# canary, #1964): a guard that shells out to node or ruby is proven by CI, not here.
set -u

IMAGE="${LINUX_CHECK_IMAGE:-ubuntu:24.04}"
DOCKER="${LINUX_CHECK_DOCKER:-docker}"

# THE HOST TOOLS A SELFTEST PROBES (#1964). A selftest that resolves a tool on PATH sees a different machine in a container that lacks it than on the
# runner that has it: `test_preflight`'s "no pg_isready on PATH" row found the runner's own `/usr/bin/pg_isready` and failed there, while this script
# reported it green because the container had no Postgres client (release run 38297902322). So the container installs them, and CANARY_TOOLS are asserted
# present before any guard runs: an image that loses one is a refusal with a sentence, never a green that means nothing. The tools are `trusted_which`
# lookups in `plugins/rails-flow/scripts/test_preflight.py` (`pg_isready`, `lsof`, `ps`). node, ruby and zsh are not here: a guard that needs them is proven by CI (see above).
HOST_PACKAGES="postgresql-client lsof procps"
CANARY_TOOLS="pg_isready lsof ps"

# --check-tools <name>...: assert each is on PATH, and nothing else (it never touches docker). The container runs it on itself before a guard, so the
# canary's refusal can be exercised without a container. No names is a usage error: zero inputs checked is not a pass.
if [ "${1:-}" = "--check-tools" ]; then
  shift
  if [ "$#" -lt 1 ]; then echo "linux_check: --check-tools needs at least one tool name" >&2; exit 2; fi
  missing=""
  for tool in "$@"; do command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"; done
  if [ -n "$missing" ]; then
    echo "linux_check: FAILED CLOSED: the container has no${missing}, a tool the runner has and a selftest probes (#1964). A guard that depends on it would read green here and fail on the runner. Add its package to HOST_PACKAGES in scripts/linux_check.sh." >&2
    exit 3
  fi
  exit 0
fi

usage() {
  echo "usage: scripts/linux_check.sh <guard> [more guards] [--run <selftest.py>]..." >&2
}

if [ "$#" -eq 0 ]; then
  usage
  exit 2
fi

specs=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --run)
      if [ "$#" -lt 2 ]; then usage; exit 2; fi
      case "$2" in
        *[!A-Za-z0-9_./-]*|-*) echo "linux_check: not a script path: $2" >&2; exit 2 ;;
      esac
      specs+=("run:$2")
      shift 2
      ;;
    -*)
      echo "linux_check: unknown option $1" >&2
      usage
      exit 2
      ;;
    *)
      case "$1" in
        *[!A-Za-z0-9_]*) echo "linux_check: not a guard name: $1" >&2; exit 2 ;;
      esac
      specs+=("guard:$1")
      shift
      ;;
  esac
done

if ! command -v "$DOCKER" >/dev/null 2>&1; then
  echo "linux_check: FAILED CLOSED: '$DOCKER' is not installed or not on PATH, so nothing ran on Linux. This is not a pass." >&2
  exit 2
fi
if ! "$DOCKER" info >/dev/null 2>&1; then
  echo "linux_check: FAILED CLOSED: docker is not running ('$DOCKER info' failed), so nothing ran on Linux. Start it and run this again. This is not a pass." >&2
  exit 2
fi

inside='
set -u
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null && apt-get install -y -qq python3 git bash ca-certificates $LINUX_CHECK_HOST_PACKAGES >/dev/null || { echo "linux_check: could not install python3, git, bash and the host tools in the container" >&2; exit 3; }
bash scripts/linux_check.sh --check-tools $LINUX_CHECK_CANARY_TOOLS || exit 3
git config --global --add safe.directory /work >/dev/null 2>&1
rc=0
for spec in "$@"; do
  case "$spec" in
    run:*)   echo "== python3 ${spec#run:}"; python3 "${spec#run:}" || rc=1 ;;
    guard:*) echo "== mutation_check --guard ${spec#guard:}"; python3 scripts/mutation_check.py --guard "${spec#guard:}" || rc=1 ;;
  esac
done
exit $rc
'

"$DOCKER" run --rm -e PYTHONDONTWRITEBYTECODE=1 -e LINUX_CHECK_HOST_PACKAGES="$HOST_PACKAGES" -e LINUX_CHECK_CANARY_TOOLS="$CANARY_TOOLS" -v "$PWD":/work -w /work "$IMAGE" bash -c "$inside" linux_check "${specs[@]}"
status=$?
if [ "$status" -ne 0 ]; then
  echo "linux_check: FAILED on Linux (exit $status): $IMAGE" >&2
  exit "$status"
fi
echo "linux_check: passed on Linux ($IMAGE)"
