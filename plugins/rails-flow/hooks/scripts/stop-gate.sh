#!/usr/bin/env bash
# Stop gate — mechanical form of "prove the NEW behavior":
#  1. Uncommitted app code without an accompanying spec change → block once.
#  2. Uncommitted spec changes → run just those specs; red suite → block.
set -uo pipefail
input="$(cat)"

# Never loop: if we already blocked once, let the stop proceed.
printf '%s' "$input" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true' && exit 0

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
[ -d spec ] || exit 0

changed="$(git status --porcelain 2>/dev/null | awk '{print $2}')"
app_changed="$(printf '%s\n' "$changed" | grep -E '^(app|lib)/.*\.rb$' || true)"
spec_changed="$(printf '%s\n' "$changed" | grep -E '^spec/.*_spec\.rb$' || true)"

if [ -n "$app_changed" ] && [ -z "$spec_changed" ]; then
  {
    echo "rails-flow stop gate: behavioral code changed with no new/updated spec."
    echo "Changed: $(printf '%s\n' "$app_changed" | head -5 | tr '\n' ' ')"
    echo "Write the spec that PROVES the new behavior (wrong-role rejection, concern behavior, etc.),"
    echo "or explain to the user why none is needed, then finish."
  } >&2
  exit 2
fi

if [ -n "$spec_changed" ] && command -v bundle >/dev/null 2>&1; then
  files="$(printf '%s\n' "$spec_changed" | tr '\n' ' ')"
  if ! out="$(timeout 120 bundle exec rspec $files --fail-fast --no-color 2>&1 | tail -15)"; then
    {
      echo "rails-flow stop gate: changed specs are RED — fix before finishing."
      printf '%s\n' "$out"
    } >&2
    exit 2
  fi
fi
exit 0
