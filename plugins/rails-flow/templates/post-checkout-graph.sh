#!/bin/sh
# post-checkout: keep the code-review-graph current across a BRANCH SWITCH (#2022).
#
# A branch change rewrites the tree with no edit hook firing, which is the staleness the Stop hook cannot
# see. git passes three arguments: the previous HEAD, the new HEAD, and 1 for a branch switch (0 for a file
# checkout). THIS FILE IS COPIED, NOT PRINTED INLINE by /rails-flow:setup-flow, because a command's markdown
# body has `$1`, `$2` and `$3` replaced by the arguments the command was invoked with (Claude Code's skill
# string substitution), which turned this hook into `[ "Audit" = "1" ]` in a real session.
[ "$3" = "1" ] || exit 0   # branch switches only, not file checkouts
command -v code-review-graph >/dev/null 2>&1 && [ -d .code-review-graph ] || exit 0
pgrep -f 'code-review-graph (update|build)' >/dev/null 2>&1 && exit 0
N=$(git diff --name-only "$1" "$2" 2>/dev/null | wc -l | tr -d ' ')
if [ "${N:-0}" -gt 5 ]; then CMD='code-review-graph build'
else CMD='code-review-graph update --skip-flows && code-review-graph embed'; fi
nohup timeout 300 sh -c "$CMD" > "$HOME/.cache/crg-checkout.log" 2>&1 < /dev/null &
