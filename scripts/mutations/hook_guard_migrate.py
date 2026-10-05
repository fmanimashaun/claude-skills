"""Mutation guard: hook_guard_migrate. Declared here, run by scripts/mutation_check.py (#1362)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name='hook_guard_migrate',
    subject='plugins/rails-flow/hooks/scripts/guard-migrate.sh',
    selftest='plugins/rails-flow/scripts/check_hook_gates.py',
    # Only the fixture groups that drive this subject (#1497): the whole harness per
    # mutant was ~70% of the mutation-coverage budget.
    selftest_args=("--only", "guard_migrate"),
    # The harness resolves every hook from the selftest's own location, so the whole
    # directory is staged -- one hook's fixtures may exercise another's shape.
    needs=(
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
           'plugins/rails-flow/hooks/scripts', 'plugins/rails-flow/hooks/hooks.json',
           'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
           # guard-claims.sh runs extract_claims.py; without it the harness's two claim
           # fixtures fail in the staged tempdir and every mutation reads as caught (#1109).
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',  # release-gate.sh runs it (#1410)
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/qa-flow/scripts/remote_evidence.py',   # the release gate runs it (#1591)
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
        Mutation(
            '#1416: the directory is compared case-sensitively again, so DB/Migrate/ slips through on macOS',
            '    parent = parent.lower()                  # #1416: a case-insensitive filesystem lands DB/Migrate here',
            '    parent = parent',
            'guard-migrate (#1416): a mixed-case DB/Migrate/ path is blocked',
        ),
        Mutation(
            '#1416: the extension is compared case-sensitively again, so `.RB` slips through',
            '    if not file_path.lower().endswith(".rb"):',
            '    if not file_path.endswith(".rb"):',
            'guard-migrate (#1416): a `.RB` extension is blocked',
        ),
        Mutation(
            '#1416: the bare-PATH fallback stops folding case',
            '  shopt -s nocasematch                     # bash 3.2 has no ${var,,}; this is its case-folding match',
            '  :',
            'guard-migrate (#1416): the bare-PATH fallback folds case too (nocasematch)',
        ),
        Mutation(
            '#1416: the deny message drops the boot line, leaving no way through when the app cannot boot',
            'If the app does not boot, the generator fails too: fix the boot first, then generate.',
            '',
            '...and says a broken boot comes first, since the generator needs the app to boot (#1416)',
        ),
        Mutation(
            '#1416: the parent is no longer resolved, so a symlink into db/migrate/ slips through',
            '    if not (is_migrate_dir(parent) or is_migrate_dir(os.path.realpath(parent))):',
            '    if not is_migrate_dir(parent):',
            'guard-migrate (#1416): a Write through a symlink into db/migrate/ is blocked',
        ),
        Mutation(
            '#1416: the fallback accepts only `/` again, so a Windows backslash path slips through',
            '_raw_migrate_path=\'db[/\\\\]+migrate[/\\\\]+[^/\\\\"]*\\.rb\'',
            '_raw_migrate_path=\'db/migrate/[^/"]*\\.rb\'',
            'guard-migrate (#1416): the bare-PATH fallback accepts a Windows backslash separator',
        ),
    ),
)
