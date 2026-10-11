"""Mutation guard: hook_guard_claims. Declared here, run by scripts/mutation_check.py (#1141).

THE FAIL-CLOSED HOOK THAT HAD NO GUARD. `guard-claims.sh` is the only thing in this toolchain that
has actually stopped a wrong number reaching a person -- it blocks a PR body or an issue comment
carrying load-bearing claims with no evidence any were checked -- and nothing proved it could still
fail. Its siblings (`guard-bash`, `guard-lane`, `release-gate`, `stop-gate`) all had one.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_guard_claims",
    subject="plugins/rails-flow/hooks/scripts/guard-claims.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    # Only the fixture groups that drive this subject (#1497): the whole harness per
    # mutant was ~70% of the mutation-coverage budget.
    selftest_args=("--only", "guard_claims"),
    # Each mutant runs only the fixture its `expects` names (#1599), not the 199-check group (about 116 s a mutant).
    narrow_with="--match",
    # The harness resolves every hook from the selftest's own location, so the whole directory is
    # staged; `extract_claims.py` is what this hook shells out to, and without it every mutation
    # reads as caught against an unrun check (#1109).
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           "plugins/rails-flow/scripts/check_criteria.py",
           "plugins/rails-flow/scripts/check_handoff.py",
           "plugins/qa-flow/scripts/read_certification.py",
           "plugins/qa-flow/scripts/push_targets.py",  # release-gate.sh runs it (#1410)
           "plugins/qa-flow/scripts/release_evidence.py",
           "plugins/qa-flow/scripts/remote_evidence.py",   # the release gate runs it (#1591)
           "plugins/rails-flow/scripts/self_consistency.py",
           "plugins/rails-flow/scripts/extract_claims.py",
           # ci-verdict-hint.sh runs it; unstaged, every mutation here read as caught (#1173).
           "plugins/rails-flow/scripts/ci_verdict_hint.py", "plugins/rails-flow/scripts/test_preflight.py", "plugins/rails-flow/scripts/session_reaper.py", "plugins/rails-flow/scripts/process_containment.py"),
    mutations=(
        # #1516, push security reviews: NO CODE RUNS BEFORE PERMISSION. The hook reads a diff in the directory the
        # command `cd`s into, before the person is asked, and a repository's own config can name a program that
        # `git diff` executes (`core.fsmonitor` on any diff, a `filter.<name>.clean` on a diff that hashes a
        # changed working-tree file). Another repository is read through its staged diff only; each mutation
        # undoes one half of that.
        Mutation(
            "a repository other than the session's is read through the working-tree diff again, hashing its files",
            'GIT_OPTIONAL_LOCKS=0 git -c core.fsmonitor=false -C "$root" diff --no-ext-diff --name-only --cached HEAD 2>/dev/null',
            'GIT_OPTIONAL_LOCKS=0 git -c core.fsmonitor=false -C "$root" diff --no-ext-diff --name-only HEAD 2>/dev/null',
            "filter.<name>.clean names a program does not run it",
        ),
        Mutation(
            "the cd target's staged diff runs that repository's fsmonitor program again",
            'GIT_OPTIONAL_LOCKS=0 git -c core.fsmonitor=false -C "$root" diff --no-ext-diff --name-only --cached HEAD 2>/dev/null',
            'GIT_OPTIONAL_LOCKS=0 git -C "$root" diff --no-ext-diff --name-only --cached HEAD 2>/dev/null',
            "core.fsmonitor names a program does not run it",
        ),
        Mutation(
            "every repository is trusted like the session's own, so the target's working tree is hashed",
            'if [ "$root" = "$session_root" ]; then',
            'if true; then',
            "filter.<name>.clean names a program does not run it",
        ),
        # #1516, push security review (the class of #1579): `git diff --name-only | grep -q` under `set -o pipefail` reads
        # "no skills/ change" once the name list outgrows the pipe buffer, because `grep -q` leaves at the first hit and
        # the writer dies of SIGPIPE. The names are matched with a shell pattern instead; this puts the pipe back.
        Mutation(
            "the diff's name list is matched through a pipe again, so a large diff reads as no skills/ change",
            """  case $'\\n'"$names" in *$'\\n'skills/*) return 0 ;; esac""",
            """  printf '%s\\n' "$names" | grep -q '^skills/' && return 0""",
            "no SIGPIPE fail-open",
        ),
        # #1435: the checker failing is a BLOCK, not a warning (owner decision).
        Mutation(
            "a crashed PR-template helper warns and lets the command through again",
            '      echo "Fix it, or ship deliberately unchecked: RAILS_FLOW_CLAIMS_OK=1 (audited)." >&2\n      exit 2\n    elif [ "$tpl_rc" -eq 1 ] && [ -z "$gaps" ]; then',
            '      echo "Fix it, or ship deliberately unchecked: RAILS_FLOW_CLAIMS_OK=1 (audited)." >&2\n    elif [ "$tpl_rc" -eq 1 ] && [ -z "$gaps" ]; then',
            "a body the helper cannot judge (a directory) is BLOCKED",
        ),
        Mutation(
            "a helper that died at import warns and lets the command through again",
            '      echo "BLOCKED by rails-flow claim guard: the PR-template check died before judging (exit 1, no sections listed)." >&2\n      echo "Fix it, or ship deliberately unchecked: RAILS_FLOW_CLAIMS_OK=1 (audited)." >&2\n      exit 2',
            '      echo "BLOCKED by rails-flow claim guard: the PR-template check died before judging (exit 1, no sections listed)." >&2\n      echo "Fix it, or ship deliberately unchecked: RAILS_FLOW_CLAIMS_OK=1 (audited)." >&2',
            "a helper that fails at import is BLOCKED",
        ),
        Mutation(
            "the quote scanner stops honouring an escaped quote inside a double-quoted string",
            '    elif q == "\\"" and c == "\\\\":\n        i += 1',
            '    elif False:\n        i += 1',
            "an escaped quote inside the title does not end it early",
        ),
        Mutation(
            "an empty exit 1 (the helper died at import) reads as a pass again",
            "    elif [ \"$tpl_rc\" -eq 1 ] && [ -z \"$gaps\" ]; then",
            "    elif false; then",
            "a helper that fails at import is BLOCKED",
        ),
        Mutation(
            "quoted strings are kept, so -R in a title switches the check off",
            "  unquoted=\"$(printf '%s' \"$cmd\" | python3 -c '",
            "  unquoted=\"$(printf '%s' \"$cmd\"; true || python3 -c '",
            "`-R` inside a quoted --title is text, so the body is still judged",
        ),
        Mutation(
            "-R is read from the whole compound command again, so an unrelated grep -R skips the check",
            "  pr_seg=\"$(printf '%s' \"$unquoted\" | grep -oE 'gh[[:space:]]+pr[[:space:]]+(create|edit)[^;&|]*' | head -1)\"",
            "  pr_seg=\"$unquoted\"",
            "an unrelated `grep -R` earlier in the chain does not switch the check off",
        ),
        # #1389: the template check, removed from the hook -- the prose rule it replaced was
        # followed 0 times in 5 downstream PRs.
        Mutation(
            "the PR-template check never runs",
            "    elif [ \"$tpl_rc\" -eq 1 ]; then\n      echo \"BLOCKED by rails-flow claim guard: this PR body is missing",
            "    elif false; then\n      echo \"BLOCKED by rails-flow claim guard: this PR body is missing",
            "a PR body missing a template section is blocked",
        ),
        Mutation(
            "-R/--repo is no longer recognised, so another repository's PR is judged by this template",
            '  if has "$pr_seg" \'(^|[[:space:]])(-R|--repo)\'; then',
            '  if false; then',
            "-R targets another repo, so its template is not judged here",
        ),
        Mutation(
            "the template check is scoped to create only, so `gh pr edit` slips past it",
            "if has \"$cmd\" '\\bgh[[:space:]]+pr[[:space:]]+(create|edit)\\b'; then\n  tpl_lib",
            "if has \"$cmd\" '\\bgh[[:space:]]+pr[[:space:]]+(create)\\b'; then\n  tpl_lib",
            "`gh pr edit` with the same body is blocked too",
        ),
        Mutation(
            # #1141: the scope was `gh pr create|edit` alone. On the day this hook fired on a PR
            # body carrying eight unverified claims, four ISSUE COMMENTS carrying counts went out
            # unchecked -- the same artifact, durable and read by someone else, through a hole.
            "an issue comment is out of scope again, so its claims go unchecked",
            'has "$cmd" \'\\bgh[[:space:]]+(pr[[:space:]]+(create|edit)|issue[[:space:]]+comment)\\b\' || exit 0',
            'has "$cmd" \'\\bgh[[:space:]]+pr[[:space:]]+(create|edit)\\b\' || exit 0',
            "guard-claims: an unchecked numeric claim in an ISSUE COMMENT is blocked",
        ),
        Mutation(
            # THE OTHER HALF, and the one that keeps the guard alive: a hook that blocked every
            # `gh pr create` would be switched off within a day, and then nothing is checked at all.
            "every body is blocked, verified or not",
            'if [ "${RAILS_FLOW_CLAIMS_OK:-0}" = "1" ]; then',
            'if [ "${RAILS_FLOW_CLAIMS_OK:-0}" = "unreachable" ]; then',
            "guard-claims: RAILS_FLOW_CLAIMS_OK=1 overrides, and says so",
        ),
        # #1509: the template is the one where the COMMAND runs, not where the hook runs.
        Mutation(
            "the template root ignores the command's cd again (the #1509 defect, restored)",
            '''  root="$(git -C "$cmd_cwd" rev-parse --show-toplevel 2>/dev/null || printf '%s' "$cmd_cwd")"''',
            '''  root="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"''',
            "a `cd <other repo>` is judged against that repo's template",
        ),
        Mutation(
            "an unresolvable cd falls through to the session repo's template",
            '  elif [ "$cwd_rc" -eq 3 ]; then\n    # The directory gh runs in is unknown',
            '  elif false; then\n    # The directory gh runs in is unknown',
            'a cd to a variable is NOT checked, with the notice',
        ),
        Mutation(
            "a relative --body-file is read from the session directory, not the cd target",
            '    body="$cmd_cwd/$body"\n',
            '    :\n',
            "a relative --body-file is read from the cd target",
        ),
        Mutation(
            "a missing or crashed resolver no longer blocks, so a relative body fails open (R1516-3)",
            'if [ "$cwd_rc" -ne 0 ] && [ "$cwd_rc" -ne 3 ] && command -v python3 >/dev/null 2>&1; then',
            'if false; then',
            "a missing command_cwd.py is BLOCKED",
        ),
        Mutation(
            "a crashed resolver warns and lets the command through",
            '''  echo "BLOCKED by rails-flow claim guard: the command's directory could not be resolved (lib/command_cwd.py missing or exited $cwd_rc), so the body was not judged." >&2
  echo "Fix it, or ship deliberately unchecked: RAILS_FLOW_CLAIMS_OK=1 (audited)." >&2
  exit 2''',
            '''  echo "BLOCKED by rails-flow claim guard: the command's directory could not be resolved (lib/command_cwd.py missing or exited $cwd_rc), so the body was not judged." >&2''',
            "a crashing command_cwd.py is BLOCKED",
        ),
        Mutation(
            "the skills/** change-type check reads the session repo's diff again (R1516-4)",
            '''GIT_OPTIONAL_LOCKS=0 git -c core.fsmonitor=false -C "$root" diff --no-ext-diff --name-only --cached HEAD 2>/dev/null''',
            '''GIT_OPTIONAL_LOCKS=0 git -c core.fsmonitor=false diff --no-ext-diff --name-only --cached HEAD 2>/dev/null''',
            "the skills/** change-type check reads the cd target's diff",
        ),
        Mutation(
            "the --body-file path keeps a trailing `;` again (R1516-6)",
            '''[^";&|)[:space:]]+''',
            '''[^"[:space:]]+''',
            '`--body-file b.md; echo done` reads b.md',
        ),
        Mutation(
            "the payload's cwd is not handed to the resolver (R1516-7)",
            '''python3 "$cwd_lib" "$start" 2>/dev/null''',
            '''python3 "$cwd_lib" 2>/dev/null''',
            "the command starts in the payload's cwd",
        ),
        Mutation(
            # Round 3, S-a.
            'a relative body whose directory is unknown fails open without saying NOT checked (#1516 S-a)',
            '    echo "rails-flow: the body, the PR template and the change type NOT checked (the directory gh runs in could not be resolved, so the relative --body-file cannot be located)." >&2\n',
            '',
            'an unlocatable relative body still says NOT checked, and why',
        ),
    ),
)
