"""Mutation guard: hook_guard_migrate. Declared here, run by scripts/mutation_check.py (#1362)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name='hook_guard_migrate',
    subject='plugins/rails-flow/hooks/scripts/guard-migrate.sh',
    selftest='plugins/rails-flow/scripts/check_hook_gates.py',
    # The harness resolves every hook from the selftest's own location, so the whole
    # directory is staged -- one hook's fixtures may exercise another's shape.
    needs=('plugins/rails-flow/hooks/scripts', 'plugins/rails-flow/hooks/hooks.json',
           'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
           # guard-claims.sh runs extract_claims.py; without it the harness's two claim
           # fixtures fail in the staged tempdir and every mutation reads as caught (#1109).
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/rails-flow/scripts/self_consistency.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported guard hook_guard_lane INERT until
           # this dependency was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py'),
    mutations=(
        Mutation(
            'the EXISTENCE check is dropped, so overwriting an existing migration is denied too',
            '    if os.path.exists(file_path):\n        print("ALLOW"); sys.exit(0)\n',
            '',
            'overwriting an EXISTING migration via Write is allowed',
        ),
        Mutation(
            'the bin/rails check is dropped, so a non-Rails project is denied too',
            '    if not os.path.isfile(os.path.join(root, "bin", "rails")):\n        print("ALLOW"); sys.exit(0)\n',
            '',
            'the identical write in a NON-RAILS project is allowed',
        ),
    ),
)
