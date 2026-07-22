#!/usr/bin/env bash
# Invoked by /pipeline:install-hooks. Writes LOCAL git hooks that NUDGE, never spend.
set -euo pipefail
gitdir="$(git rev-parse --git-dir)"
dev_branch="$(grep -E '^dev_branch:' pipeline.yml 2>/dev/null | awk '{print $2}')"; dev_branch="${dev_branch:-dev}"

cat > "$gitdir/hooks/post-merge" << HOOK
#!/usr/bin/env bash
# pipeline nudge: a merge landed. If we're on the dev branch, QA verify is pending.
branch="\$(git branch --show-current 2>/dev/null)"
if [ "\$branch" = "$dev_branch" ]; then
  echo "QA verify pending on $dev_branch (\$(git rev-parse --short HEAD)) — run /qa-flow:verify or /pipeline" > "\$(git rev-parse --git-dir)/pipeline-pending"
  echo "[pipeline] $dev_branch updated — QA verify pending. Open Claude Code and run /pipeline."
fi
HOOK
chmod +x "$gitdir/hooks/post-merge"
echo "installed: $gitdir/hooks/post-merge (nudge-only, no token spend)"
