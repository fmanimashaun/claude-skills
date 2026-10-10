"""Mutation guard: hook_release_gate_fallback. Declared here, run by scripts/mutation_check.py (#1720).

Without its classifier the release gate fails closed BY SHAPE. Each rule has a fixture only it catches, so removing one is seen.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_release_gate_fallback",
    subject="plugins/qa-flow/hooks/scripts/release-gate.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "release_gate_fallback"),
    # The same staged tree as hook_release_gate: the harness drives the hook from its own location.
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',  # release-gate.sh runs it (#1410)
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/qa-flow/scripts/remote_evidence.py',   # the release gate runs it (#1591)
           'plugins/rails-flow/scripts/self_consistency.py'),
    mutations=(
        Mutation(
            "(a) the obfuscation markers are not checked",
            '  if LC_ALL=C grep -qE "[\\$\\`\'\\"\\\\\\\\*?{}]|\\[|\\]|${_w}(eval|xargs)${_e}" <<<"$cmd"; then',
            "  if false; then",
            "release-gate fallback (#1720): (a) a marker alone refuses: a base64-decoded push run through sh from `git log $(...)`",
        ),
        Mutation(
            "(b) `fetch` with a `:` refspec is not a ref change",
            '    || LC_ALL=C grep -qE "${_w}fetch${_e}[^;&|]*:" <<<"$_flat" \\',
            "    || false \\",
            "release-gate fallback (#1720): (b) `fetch` with a `:` refspec refuses",
        ),
        Mutation(
            "(b) `branch -f` is not a ref change",
            '    || LC_ALL=C grep -qE "${_w}branch[[:space:]][^;&|]*-(f|M|D|-force|-delete|-move)${_e}" <<<"$_flat"; then',
            "    || false; then",
            "release-gate fallback (#1720): (b) `branch -f/-D` refuses even without main (`git branch -D feature/x`)",
        ),
        Mutation(
            "(c) a git subcommand off the read-only list passes",
            '        *) _why="\\`git $_s\\` is not on the read-only list"; break ;;',
            "        *) ;;",
            "release-gate fallback (#1720): (c) a git alias, not on the read-only list, refuses",
        ),
        Mutation(
            "the refusal does not name the missing classifier",
            "release-gate classifier missing: restore plugins/qa-flow/scripts/push_targets.py (reinstall the plugin).",
            "release-gate refused.",
            "release-gate fallback (#1720): the refusal names the missing classifier and the fix",
        ),
        Mutation(
            "the read-only list is not consulted: every git call is refused",
            "        status|log|diff|show|rev-parse|rev-list|ls-files|ls-tree|ls-remote|branch|",
            "        __none__|rev-list|ls-files|ls-tree|ls-remote|branch|",
            "release-gate fallback (#1720): CONTROL: read-only `git status` passes",
        ),
        Mutation(
            "the dashed `git-<verb>` form is not checked",
            '          *) _why="\\`git-$_s\\` is not on the read-only list"; break ;;',
            "          *) ;;",
            "release-gate fallback (#1720): the dashed `git-push origin main` refuses",
        ),
        Mutation(
            "a local rewrite of main is not checked",
            '           && LC_ALL=C grep -qE "${_w}(branch[[:space:]]',
            '           && false && LC_ALL=C grep -qE "${_w}(branch[[:space:]]',
            "release-gate fallback (#1720): a local rewrite of main (`git branch -m dev main`) refuses",
        ),
        Mutation(
            "a gh subcommand off the allow-list passes",
            '          *) _why="\\`gh ${1:-} ${2:-}\\` is not on the read-only list"; break ;;',
            "          *) ;;",
            "release-gate fallback (#1720): a gh subcommand off the allow-list (`gh workflow run`) refuses",
        ),
        Mutation(
            "a gh api write passes",
            '              _why="\\`gh api\\` with a method other than GET or with fields writes"; break',
            "              :",
            "release-gate fallback (#1720): `gh api -X POST` refuses",
        ),
        Mutation(
            "a GET is read as a write: every `gh api -X GET` refuses",
            '&& ! LC_ALL=C grep -qE "[[:space:]](-X|--method)[[:space:]=]*GET([[:space:]]|$)" <<<"$_g"; }; then',
            '; }; then',
            "release-gate fallback (#1720): CONTROL: read-only `gh api -X GET repos/a/b` passes",
        ),
    ),
)
