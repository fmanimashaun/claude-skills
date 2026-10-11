"""Mutation guard: hook_trusted_env. The environment every hook runs in (#1850). Run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_trusted_env",
    subject="plugins/rails-flow/hooks/scripts/lib/trusted-env.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Only the hostile-environment group drives this subject, and each mutant runs ONE of its checks.
    selftest_args=("--only", "hostile_env"),
    narrow_with="--match",
    needs=("plugins/rails-flow/scripts/fixture_git.py", "plugins/rails-flow/hooks/hooks.json", "plugins/qa-flow/hooks/hooks.json", "plugins/pipeline/hooks/hooks.json", "plugins/design-flow/hooks/hooks.json",
           "plugins/rails-flow/scripts/assign_lanes.py", "plugins/rails-flow/scripts/brain_local_sync.py",
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts", "plugins/pipeline/hooks/scripts", "plugins/design-flow/hooks/scripts", "plugins/qa-flow/scripts",
           # The hostile-environment group RUNS every hook, and a hook whose script is missing exits quietly: unstaged, a mutant could survive because nothing ran (#1109, #1173).
           "plugins/rails-flow/scripts/check_criteria.py", "plugins/rails-flow/scripts/check_handoff.py", "plugins/pipeline/scripts/status_board.py",
           "plugins/qa-flow/scripts/read_certification.py", "plugins/qa-flow/scripts/push_targets.py",
           "plugins/qa-flow/scripts/release_evidence.py", "plugins/rails-flow/scripts/self_consistency.py", "plugins/qa-flow/scripts/remote_evidence.py",
           "plugins/rails-flow/scripts/extract_claims.py", "plugins/rails-flow/scripts/ci_verdict_hint.py", "plugins/rails-flow/scripts/test_preflight.py",
           "plugins/rails-flow/scripts/session_reaper.py", "plugins/rails-flow/scripts/process_containment.py"),
    mutations=(
        Mutation(
            'a PATH entry inside the repository is kept',
            '    if rf_inside "$real"; then continue; fi\n    case ":$out:"',
            '    if false; then continue; fi\n    case ":$out:"',
            "PATH drops the repository's bin",
        ),
        Mutation(
            'a PATH entry is not resolved through its symlinks',
            '    real="$(rf_physical "$dir")" || continue\n    if rf_inside "$real"; then continue; fi\n    case ":$out:"',
            '    real="$dir"\n    if rf_inside "$real"; then continue; fi\n    case ":$out:"',
            'a link INTO it',
        ),
        Mutation(
            'a `*` in a PATH entry is globbed',
            '  set -f\n  for dir in ${PATH:-}; do\n    case "$dir" in /*) ;; *) continue ;; esac\n    real="$(rf_physical "$dir")" || continue\n    if rf_inside "$real"; then continue; fi\n    case ":$out:"',
            '  :\n  for dir in ${PATH:-}; do\n    case "$dir" in /*) ;; *) continue ;; esac\n    real="$(rf_physical "$dir")" || continue\n    if rf_inside "$real"; then continue; fi\n    case ":$out:"',
            'a `*` in a PATH entry is not globbed',
        ),
        Mutation(
            'the INNERMOST .git or Gemfile ancestor is the repository',
            'if [ -e "$probe/Gemfile" ] || [ -e "$probe/.git" ]; then RF_REPO_ROOT="$probe"; fi',
            'if [ -e "$probe/Gemfile" ] || [ -e "$probe/.git" ]; then RF_REPO_ROOT="$probe"; break; fi',
            'OUTERMOST .git or Gemfile ancestor',
        ),
        Mutation(
            'a PATH with nothing trusted left becomes empty, which is the current directory',
            'out="/nonexistent"',
            'out=""',
            'with NOTHING trusted left',
        ),
        Mutation(
            'PYTHON* stays in the environment',
            'PYTHON*|LD_*|DYLD_*|NODE_OPTIONS|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|CDPATH|GLOBIGNORE)',
            'LD_*|DYLD_*|NODE_OPTIONS|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|CDPATH|GLOBIGNORE)',
            'trusted-env.sh unsets PYTHONPATH',
        ),
        Mutation(
            'LD_* stays in the environment',
            'PYTHON*|LD_*|DYLD_*|NODE_OPTIONS|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|CDPATH|GLOBIGNORE)',
            'PYTHON*|DYLD_*|NODE_OPTIONS|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|CDPATH|GLOBIGNORE)',
            'trusted-env.sh unsets LD_PRELOAD',
        ),
        Mutation(
            'DYLD_* stays in the environment',
            'PYTHON*|LD_*|DYLD_*|NODE_OPTIONS|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|CDPATH|GLOBIGNORE)',
            'PYTHON*|LD_*|NODE_OPTIONS|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|CDPATH|GLOBIGNORE)',
            'trusted-env.sh unsets DYLD_INSERT_LIBRARIES',
        ),
        Mutation(
            'NODE_OPTIONS stays in the environment',
            'PYTHON*|LD_*|DYLD_*|NODE_OPTIONS|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|CDPATH|GLOBIGNORE)',
            'PYTHON*|LD_*|DYLD_*|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|CDPATH|GLOBIGNORE)',
            'trusted-env.sh unsets NODE_OPTIONS',
        ),
        Mutation(
            'BASH_ENV stays in the environment',
            'PYTHON*|LD_*|DYLD_*|NODE_OPTIONS|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|CDPATH|GLOBIGNORE)',
            'PYTHON*|LD_*|DYLD_*|NODE_OPTIONS|ENV|SHELLOPTS|BASHOPTS|CDPATH|GLOBIGNORE)',
            'trusted-env.sh unsets BASH_ENV',
        ),
        Mutation(
            'ENV stays in the environment',
            'PYTHON*|LD_*|DYLD_*|NODE_OPTIONS|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|CDPATH|GLOBIGNORE)',
            'PYTHON*|LD_*|DYLD_*|NODE_OPTIONS|BASH_ENV|SHELLOPTS|BASHOPTS|CDPATH|GLOBIGNORE)',
            'trusted-env.sh unsets ENV',
        ),
        Mutation(
            'CDPATH stays in the environment',
            'PYTHON*|LD_*|DYLD_*|NODE_OPTIONS|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|CDPATH|GLOBIGNORE)',
            'PYTHON*|LD_*|DYLD_*|NODE_OPTIONS|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|GLOBIGNORE)',
            'trusted-env.sh unsets CDPATH',
        ),
        Mutation(
            'GLOBIGNORE stays in the environment',
            'PYTHON*|LD_*|DYLD_*|NODE_OPTIONS|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|CDPATH|GLOBIGNORE)',
            'PYTHON*|LD_*|DYLD_*|NODE_OPTIONS|BASH_ENV|ENV|SHELLOPTS|BASHOPTS|CDPATH)',
            'trusted-env.sh unsets GLOBIGNORE',
        ),
        Mutation(
            'every GIT_* stays, so GIT_CONFIG_* reaches git',
            '*" $name "*) ;; *) unset "$name" 2>/dev/null ;; esac ;;',
            '*) ;; esac ;;',
            'trusted-env.sh unsets GIT_CONFIG_COUNT',
        ),
        Mutation(
            'every GIT_* goes, the allowlist is ignored',
            '*" $name "*) ;; *) unset "$name" 2>/dev/null ;; esac ;;',
            '*) unset "$name" 2>/dev/null ;; esac ;;',
            'trusted-env.sh keeps GIT_DIR',
        ),
        Mutation(
            'rf_trusted_python takes a python3 whose link target is inside the repository',
            '      if rf_inside "$target"; then continue; fi',
            '      if false; then continue; fi',
            'rf_trusted_python skips a python3 whose link target is inside the repository',
        ),
        Mutation(
            'rf_trusted_python never follows the link chain',
            '  while [ -L "$f" ]; do',
            '  while false; do',
            'rf_trusted_python skips a python3 whose link target is inside the repository',
        ),
    ),
)
