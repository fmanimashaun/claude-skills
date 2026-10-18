"""Mutation guard: data_root_hooks. Declared here, run by scripts/mutation_check.py (#2141).

The Kamal hooks the pipeline plugin ships: `pre-connect` acts only for the commands that boot a container, and `post-deploy` prunes after a
redeploy or a rollback (the deploy commands that never prune by themselves, Kamal 2.12.0) without failing a live release.
"""
from mutation_types import Guard, Mutation  # noqa: F401

NEEDS = ("templates/data-root/bin/data-root", "templates/data-root/bin/data-root.sh", "templates/data-root/kamal-hooks/pre-connect",
         "templates/data-root/kamal-hooks/docker-setup", "scripts/check_deploy_volumes.py")

GUARD = Guard(
    name="data_root_hooks",
    subject="templates/data-root/kamal-hooks/post-deploy",
    selftest="scripts/data_root_selftest.py",
    needs=NEEDS,
    mutations=(
        Mutation("post-deploy never prunes", 'if ! "$ROOT/bin/kamal" "${args[@]}"; then', "if false; then", "post-deploy prunes after redeploy"),
        Mutation("post-deploy prunes after a deploy too (twice)", "  redeploy|rollback) ;;", "  redeploy|rollback|deploy) ;;",
                 "post-deploy does not prune twice after a deploy"),
        Mutation("a failed prune fails the live release", "exit 0\n", "exit 1\n", "a failed prune warns and does not fail the live release"),
        Mutation("the destination is dropped", '[ -z "${KAMAL_DESTINATION:-}" ] || args+=(-d "$KAMAL_DESTINATION")', ":",
                 "post-deploy passes the destination"),
    ),
)
