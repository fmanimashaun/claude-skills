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
# guards are best run from a main checkout. The container has python3, git and bash only: a guard that shells out to node
# or ruby is proven by CI, not here.
set -u

IMAGE="${LINUX_CHECK_IMAGE:-ubuntu:24.04}"
DOCKER="${LINUX_CHECK_DOCKER:-docker}"

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
apt-get update -qq >/dev/null && apt-get install -y -qq python3 git bash ca-certificates >/dev/null || { echo "linux_check: could not install python3, git and bash in the container" >&2; exit 3; }
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

"$DOCKER" run --rm -e PYTHONDONTWRITEBYTECODE=1 -v "$PWD":/work -w /work "$IMAGE" bash -c "$inside" linux_check "${specs[@]}"
status=$?
if [ "$status" -ne 0 ]; then
  echo "linux_check: FAILED on Linux (exit $status): $IMAGE" >&2
  exit "$status"
fi
echo "linux_check: passed on Linux ($IMAGE)"
