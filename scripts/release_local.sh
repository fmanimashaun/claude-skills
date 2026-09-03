#!/usr/bin/env bash
# release_local.sh — cut the marketplace release from a local machine.
#
# This is the FALLBACK for .github/workflows/release.yml, for when a hosted runner
# is unavailable. It is a deliberate mirror: the same five steps, in the same order,
# with the same failure conditions. If you change one, change the other.
#
#   1. resolve `metadata.version` from marketplace.json -> tag vX.Y.Z
#   2. no-op if that release already exists (idempotent, like the workflow)
#   3. rebuild dist/*.skill with the canonical builder
#   4. DRIFT GUARD: fail if committed dist/ differs from that clean build
#   5. extract the matching "### … (release vX.Y.Z)" CHANGELOG block as the notes,
#      then publish with EVERY dist/*.skill
#
# A hosted run gets three things for free that a laptop does not, so this script
# asserts them explicitly — they are the difference between a reproducible release
# and "whatever happened to be in this working tree":
#
#   * a clean checkout          -> we require a clean working tree
#   * the ref is main           -> we require HEAD to be main
#   * the sha is pushed         -> we require HEAD == origin/main, so the tag never
#                                  points at a commit only this machine has
#
# Releases are published through the Releases API, which is NOT metered by Actions
# minutes — so this path works even when a runner will not start.
#
# Usage:
#   bash scripts/release_local.sh --dry-run    # verify everything, publish nothing
#   bash scripts/release_local.sh              # publish (asks for confirmation)
#   bash scripts/release_local.sh --yes        # publish without the prompt
#
# Exit: 0 published or nothing-to-do · 1 a guard failed · 2 usage/environment.

set -euo pipefail

DRY_RUN=0
ASSUME_YES=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --yes|-y)  ASSUME_YES=1 ;;
    -h|--help) sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) printf 'release_local: unknown argument %s\n' "$arg" >&2; exit 2 ;;
  esac
done

say()  { printf '%s\n' "$*"; }
step() { printf '\n==> %s\n' "$*"; }
fail() { printf '\nrelease_local: %s\n' "$*" >&2; exit 1; }

# `python` is still Python 2 on some systems. package_core.py needs 3, and a silently
# wrong interpreter would build assets nobody else can reproduce — so probe, don't assume.
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 \
     && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)' 2>/dev/null; then
    PY="$candidate"; break
  fi
done
[ -n "$PY" ] || { printf 'release_local: no Python 3 on PATH (need python3, or a python that is v3).\n' >&2; exit 2; }

# ---------------------------------------------------------------- preflight

step "Preflight"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || { printf 'release_local: not a git repository.\n' >&2; exit 2; }
cd "$(git rev-parse --show-toplevel)"

[ -f .claude-plugin/marketplace.json ] \
  || { printf 'release_local: no .claude-plugin/marketplace.json — this is not the marketplace repo.\n' >&2; exit 2; }

command -v gh >/dev/null 2>&1 || { printf 'release_local: gh CLI not on PATH.\n' >&2; exit 2; }
gh auth status >/dev/null 2>&1 || { printf 'release_local: gh is not authenticated (run: gh auth status).\n' >&2; exit 2; }

REPO="$(gh repo view --json nameWithOwner --jq .nameWithOwner)"
[ -n "$REPO" ] || { printf 'release_local: could not resolve the GitHub repo.\n' >&2; exit 2; }
say "repo:   $REPO"

# A release must be reproducible from a committed tree. Anything uncommitted would
# silently become part of the built assets while being invisible to everyone else.
DIRTY="$(git status --porcelain)"
if [ -n "$DIRTY" ]; then
  say ""
  printf '%s\n' "$DIRTY"
  fail "working tree is not clean. Commit or stash first — a release must be reproducible from committed state."
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[ "$BRANCH" = "main" ] \
  || fail "on branch '$BRANCH'. Releases only ever come from main (same rule as the workflow's ref check)."

git fetch origin main --quiet
LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse origin/main)"
if [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
  fail "HEAD ($(git rev-parse --short HEAD)) != origin/main ($(git rev-parse --short origin/main)).
      Push or pull first — a tag must point at a commit that exists on the remote."
fi
say "branch: main @ $(git rev-parse --short HEAD) (in sync with origin)"

# ------------------------------------------------------------- 1. version

step "1. Resolve version"

VERSION="$("$PY" -c "import json;print(json.load(open('.claude-plugin/marketplace.json'))['metadata']['version'])")"
[ -n "$VERSION" ] || fail "could not read metadata.version from .claude-plugin/marketplace.json."
TAG="v$VERSION"
say "tag:    $TAG"

# --------------------------------------------------- 2. already released?

step "2. Check whether $TAG already exists"

if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  say "Release $TAG already exists — nothing to do."
  say ""
  say "This is the no-op case, exactly as the workflow behaves: it means metadata.version"
  say "was not bumped. Bump it in a dev -> main promotion PR to ship a new release."
  exit 0
fi
say "not published yet — proceeding"

# ------------------------------------------------------------ 3. build

step "3. Build dist/*.skill with the canonical builder"

"$PY" scripts/package_core.py

# -------------------------------------------------------- 4. drift guard

step "4. Verify committed dist/ is canonical (drift guard)"

# --porcelain catches tracked modifications AND untracked files, so a brand-new
# skill whose dist/*.skill was never committed also trips the guard (git diff
# --quiet would miss the untracked artifact and pass falsely).
DRIFT="$(git status --porcelain -- dist/)"
if [ -n "$DRIFT" ]; then
  say ""
  printf '%s\n' "$DRIFT"
  say ""
  say "Committed dist/*.skill differs from a clean package_core.py build (or a built"
  say "artifact is untracked). A skill source changed without repackaging, or a new"
  say "skill's dist/ was never committed."
  fail "run '$PY scripts/package_core.py', commit dist/, then release."
fi
say "dist/ matches a clean build."

ASSETS=(dist/*.skill)
[ -e "${ASSETS[0]}" ] || fail "no dist/*.skill assets found to attach."
say "assets (${#ASSETS[@]}):"
for a in "${ASSETS[@]}"; do
  printf '  %s  %s bytes\n' "$a" "$(wc -c < "$a" | tr -d ' ')"
done

# --------------------------------------------------------- 5. release notes

step "4b. Run the gate sweep the hosted release runs first"

# release.yml makes its `release` job `needs: gates` -- the whole sweep, before anything publishes.
# This script ran none of it (#832), so a local release could ship what CI would have refused.
# `--gates-only` is the same set CI runs: content gates only, no clone diagnostics.
"$PY" scripts/maintainer_doctor.py --gates-only \
  || fail "the gate sweep failed — the hosted release would not have published this. Fix the failures above, then re-run."

step "5. Extract release notes from CHANGELOG"

# BSD/macOS mktemp requires a template — a bare `mktemp` aborts there, breaking exactly
# the kind of machine this fallback exists to serve.
NOTES="$(mktemp "${TMPDIR:-/tmp}/release-notes.XXXXXX")"
trap 'rm -f "$NOTES"' EXIT

# EVERY `### … (release vX.Y.Z)` block, not just the first (#699). One implementation,
# shared with .github/workflows/release.yml — this file and that one carried the same awk
# verbatim, kept in step by a comment asking nicely, which is the unenforced-claim shape
# the bug itself had. The script keeps the `/^### /` anchor (a line merely MENTIONING the
# tag must not start a grab — a verified failure, not a hypothesis) and the bare-pointer
# fallback, so a release never publishes an empty body.
"$PY" scripts/extract_release_notes.py --tag "$TAG" > "$NOTES"

# FAIL, not warn (#832). This printed "Publishing anyway" -- so the `release notes complete` gate
# that BLOCKS a hosted release could not block here, in the one path that exists for when the
# hosted runner is unavailable. A fallback that relaxes a gate is not a mirror of the workflow.
"$PY" scripts/extract_release_notes.py --check \
  || fail "the notes for $TAG are incomplete or would not publish — see the findings above. Fix the CHANGELOG heading(s), then re-run."
printf '\nInstall: /plugin marketplace add %s\n' "$REPO" >> "$NOTES"

say "--- notes ---"
cat "$NOTES"
say "-------------"

# -------------------------------------------------------------- publish

step "Publish"

if [ "$DRY_RUN" -eq 1 ]; then
  say "DRY RUN — nothing published. Would have run:"
  say ""
  say "  gh release create $TAG ${ASSETS[*]} \\"
  say "    --repo $REPO --target $LOCAL_SHA \\"
  say "    --title $TAG --notes-file <the notes above>"
  say ""
  say "Every guard passed: clean tree, on main, in sync, $TAG unpublished,"
  say "dist/ canonical, ${#ASSETS[@]} asset(s) ready."
  exit 0
fi

if [ "$ASSUME_YES" -eq 0 ]; then
  say ""
  say "About to publish $TAG to $REPO at $(git rev-parse --short HEAD) with ${#ASSETS[@]} asset(s)."
  say "A published release is visible immediately and is what users install."
  printf 'Type the tag (%s) to confirm: ' "$TAG"
  read -r reply < /dev/tty || fail "no tty for confirmation — re-run with --yes if that is intended."
  [ "$reply" = "$TAG" ] || fail "confirmation did not match; nothing published."
fi

gh release create "$TAG" \
  "${ASSETS[@]}" \
  --repo "$REPO" \
  --target "$LOCAL_SHA" \
  --title "$TAG" \
  --notes-file "$NOTES"

step "Verify what was published"

gh release view "$TAG" --repo "$REPO" --json tagName,assets \
  --jq '"tag: \(.tagName)\nassets:\n" + ([.assets[] | "  \(.name)  \(.size) bytes  \(.state)"] | join("\n"))'

say ""
say "Published $TAG."
say "If the hosted workflow later runs for this same version it will be a no-op —"
say "the tag now exists, which is exactly the idempotency the workflow relies on."
