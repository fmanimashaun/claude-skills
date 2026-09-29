"""Mutation guard: hook_guard_migrate_matcher. Declared here, run by scripts/mutation_check.py (#1362).

`guard-migrate.sh` only refuses the moment a file is CREATED; `Edit`/`MultiEdit` cannot create a
file, so the whole scope guarantee lives in one line of `hooks.json` -- the matcher. Nothing inside
the script itself checks which tool invoked it, so a widened matcher is invisible to every fixture
in `hook_guard_migrate.py`. This is the one place that catches it.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name='hook_guard_migrate_matcher',
    subject='plugins/rails-flow/hooks/hooks.json',
    selftest='plugins/rails-flow/scripts/check_hook_gates.py',
    needs=('plugins/rails-flow/hooks/scripts',
           'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',  # release-gate.sh runs it (#1410)
           'plugins/rails-flow/scripts/self_consistency.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           'plugins/rails-flow/scripts/ci_verdict_hint.py'),
    mutations=(
        Mutation(
            'the matcher is widened to also route Edit and MultiEdit into the creation-only guard',
            '      {\n        "matcher": "Write",\n        "hooks": [\n          {\n            "type": "command",\n            "command": "bash \\"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/guard-migrate.sh\\"",',
            '      {\n        "matcher": "Edit|Write|MultiEdit",\n        "hooks": [\n          {\n            "type": "command",\n            "command": "bash \\"${CLAUDE_PLUGIN_ROOT}/hooks/scripts/guard-migrate.sh\\"",',
            "hooks.json wires it to exactly one PreToolUse entry, matcher `Write`",
        ),
    ),
)
