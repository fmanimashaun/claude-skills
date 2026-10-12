"""Mutation guard: hook_guard_claims_scope. Declared here, run by scripts/mutation_check.py (#1877).

guard-claims.sh decides WHERE the `gh` is (a command, not prose in a title or a comment) and which evidence phrases end its
refusal, including the 'measured 2026-..-..' the refusal itself asks for. Each mutant undoes one of those, and one fixture
must name it. Its own guard, so a mutant runs only the guard_claims fixture group.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_guard_claims_scope",
    subject="plugins/rails-flow/hooks/scripts/guard-claims.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "guard_claims"),
    needs=("plugins/rails-flow/scripts/fixture_git.py", "plugins/rails-flow/scripts/wip_commit.py",  # wip-commit.sh runs it (#1915 x #1901)
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py', 'plugins/rails-flow/scripts/check_memory_index.py',  # session-start.sh runs all three (#1581, #1828: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           'plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
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
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/test_preflight.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py'),   # check_hook_gates drives BOTH plugins' hooks (#906)
    mutations=(
        Mutation(
            "the date form of the evidence is gone, so the 'measured 2026-..-..' the refusal asks for keeps the PR blocked",
            r"""|measured[[:space:]]+[0-9]{4}-[0-9]{2}-[0-9]{2}|verified""",
            r"""|verified""",
            "the evidence phrase 'measured 2026-10-11' is accepted",
        ),
        Mutation(
            "the date form of 'verified' is gone, so 'Verified 2026-..-.. against ...' alone keeps the PR blocked (#1936)",
            r"""|verified[[:space:]]+(on[[:space:]]+)?[0-9]{4}-[0-9]{2}-[0-9]{2}|CONFIRMED""",
            r"""|CONFIRMED""",
            "the evidence phrase 'Verified 2026-10-12 against Retask dev' is accepted",
        ),
        Mutation(
            "the optional word between 'measured' and on/against is gone, so 'measured live on dev' is not evidence",
            r"""measured[[:space:]]+([a-z]+[[:space:]]+)?(on|against)""",
            r"""measured[[:space:]]+(on|against)""",
            "the evidence phrase 'measured live on dev' is accepted",
        ),
        Mutation(
            "the match is a substring of the whole command again, so a title that names `gh pr create` blocks an issue create",
            r"""has "$cmd" "${GH_AT_COMMAND}(pr[[:space:]]+(create|edit)|issue[[:space:]]+comment)\\b" || exit 0""",
            r"""has "$cmd" '\bgh[[:space:]]+(pr[[:space:]]+(create|edit)|issue[[:space:]]+comment)\b' || exit 0""",
            "...even when the title names `gh pr create`",
        ),
        Mutation(
            "a quote no longer ends the plain words before gh, so a title that names `gh pr create` is a command again",
            r"""([^;&|()`"'"'"'#]|"[^"]*"|'"'"'""",
            r"""([^;&|()`#]|"[^"]*"|'"'"'""",
            "...even when the title names `gh pr create`",
        ),
        Mutation(
            "a `#` no longer ends the plain words before gh, so a trailing shell comment naming `gh pr edit` is a command again",
            r"""([^;&|()`"'"'"'#]|"[^"]*"|'"'"'""",
            r"""([^;&|()`"'"'"']|"[^"]*"|'"'"'""",
            "...and when a trailing shell comment names `gh pr edit`",
        ),
        Mutation(
            "the quote of a -c string is not a command start, so `bash -c \"gh pr create ...\"` is not seen",
            r"""|[[:space:]]-[a-z]*c[[:space:]]+["'"'"']|eval""",
            r"""|eval""",
            "is still blocked inside bash -c",
        ),
        Mutation(
            "the start of a line is not a command start, so a bare `gh pr create` is not seen",
            r"""GH_AT_COMMAND='(^|[;&|(""",
            r"""GH_AT_COMMAND='([;&|(""",
            "an unchecked numeric claim in a PR body is blocked",
        ),
        Mutation(
            "a whole double-quoted string is not a word before gh, so `env -C \"$d\" gh pr create` is not seen",
            r"""|"[^"]*"|'"'"'[^'"'"']*'"'"'|\$\(""",
            r"""|'"'"'[^'"'"']*'"'"'|\$\(""",
            "is still blocked behind a double-quoted word",
        ),
        Mutation(
            "a whole single-quoted string is not a word before gh, so `timeout '60' gh pr edit` is not seen",
            r"""|"[^"]*"|'"'"'[^'"'"']*'"'"'|\$\(""",
            r"""|"[^"]*"|\$\(""",
            "is still blocked behind a single-quoted word",
        ),
        Mutation(
            "a $(...) substitution is not a word before gh, so `FOO=$(date) gh pr create` is not seen",
            r"""|\$\([^()]*\))*\bgh""",
            r""")*\bgh""",
            "is still blocked behind a $(...) assignment",
        ),
        Mutation(
            "the refusal says 'PR body' for an issue comment again",
            r"""this body makes ${n}""",
            r"""this PR body makes ${n}""",
            "says 'body', not 'PR body'",
        ),
    ),
)
