"""Mutation guard: session_reset. Declared here, run by scripts/mutation_check.py (#1687, #1723, #1724)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1687/#1723/#1724. The mod clears a finished implementation session, compacts a session near a limit, and
# elects each session's role. Each break below either clears or compacts a session in the middle of work,
# or leaves a session that should have been reset carrying its context. The selftest is the Node unit
# test under a hand-built host; the election runs its REAL sh script against a throwaway HOME. The engine
# is not in the loop (`claude plugin validate` is, locally).
#
# NOT listed, because equivalent: dropping `kill -0` from the liveness test. A dead pid has no start time, so
# the start-time comparison alone already calls its claim stale; the two tests overlap on purpose.
# Also NOT listed: dropping the takeover lock. Whether two simultaneous takers both win depends on timing, so no
# mutant of it is caught every time; the test runs the real race five rounds and the lock is reasoned, not proved.
GUARD = Guard(
    name="session_reset",
    subject="hooks/session-reset.mjs",
    selftest="scripts/check_mods.py",
    selftest_args=("session-reset",),
    needs=("tests/session-reset.unit.mjs", "hooks/context-nudge.mjs", "hooks/budget-guard.mjs"),
    mutations=(
        Mutation(
            "a Bash call that errored or was denied is recorded as if it ran",
            "      if (r?.deny || r?.isError) return r\n",
            "",
            "a Bash call that errors or is denied records nothing",
        ),
        Mutation(
            "a live worktree no longer blocks the clear",
            "job.worktrees.size === 0 && ",
            "",
            "never mid-job",
        ),
        Mutation(
            "a background job no longer blocks the clear",
            "job.background === 0 && ",
            "",
            "a background job started this job blocks the clear",
        ),
        Mutation(
            "a PR merged into a branch other than dev counts as done",
            "|| v.baseRefName !== 'dev'",
            "",
            "never mid-job",
        ),
        Mutation(
            "a session that opened no PR counts as done",
            "  if (job.prs.size === 0) return false\n",
            "",
            "never mid-job",
        ),
        Mutation(
            "the session compacts instead of clearing when its job is done",
            "await $.command.run({ command: 'clear' })",
            "await $.session.compact({ instructions: 'x' })",
            "job done: the session clears exactly once",
        ),
        Mutation(
            "the clear is requested inside the awaited hook, where command.run rejects",
            "$.clock.after(0, () => void reset($, epoch))",
            "void reset($, epoch)",
            "the clear is requested from a timer",
        ),
        Mutation(
            "the coordinator and a role-less session clear too",
            "state.role === 'implementation' && jobDoneShape()",
            "jobDoneShape()",
            "only an implementation session clears",
        ),
        Mutation(
            "a claude -p run (no surface) clears",
            " && (await $.session.surfaces()).length > 0",
            "",
            "claude -p (no surface) never clears",
        ),
        Mutation(
            "a handoff is any file, not one named handoff",
            "/handoff/i.test(path.split('/').pop())",
            "/./.test(path)",
            "parsers read the worktree",
        ),
        Mutation(
            "the compaction forgets the instruction not to remove a worktree",
            " Do not remove any worktree.",
            "",
            "mid-job at the context threshold",
        ),
        Mutation(
            "the compaction fires before the warning line reached the model",
            "  const handoffAsked = role === 'coordinator' || nudged\n",
            "  const handoffAsked = true\n",
            "mid-job at the context threshold",
        ),
        Mutation(
            "a usage window compacts before its line reached the model",
            " && (role === 'coordinator' || w.announced !== null)",
            "",
            "a usage window at warn compacts mid-job",
        ),
        Mutation(
            "the context compacts below the threshold",
            "if (fill !== null && fill >= compactPct && handoffAsked)",
            "if (fill !== null && fill >= 0 && handoffAsked)",
            "below the threshold nothing compacts",
        ),
        Mutation(
            "the election never claims: every session is an implementation session",
            'claim() { mkdir "$c" 2>/dev/null || return 1;',
            "claim() { return 1;",
            "the first session is elected coordinator",
        ),
        Mutation(
            "the claim is made with mkdir -p, so every simultaneous start wins it",
            'claim() { mkdir "$c" 2>/dev/null || return 1;',
            'claim() { mkdir -p "$c" 2>/dev/null || return 1;',
            "two simultaneous starts elect exactly one coordinator",
        ),
        Mutation(
            "a live pid is the coordinator whatever process it is now (a recycled pid after a reboot)",
            ' && [ "$(start "$1")" = "$2" ]; }',
            "; }",
            "a claim whose pid is recycled",
        ),
        Mutation(
            "the override does not replace a live coordinator's claim",
            'if [ "$force" = "1" ]; then rm -rf "$c"; fi',
            ":",
            "takes the claim from a live coordinator",
        ),
        Mutation(
            "a coordinator asking again is not recognised as the holder",
            'if [ "$hp" = "$me" ] && [ "$hl" = "$(start "$me")" ]; then echo coordinator; exit 0; fi',
            ":",
            "a live coordinator is not displaced",
        ),
        Mutation(
            "RAILS_FLOW_ROLE=implementation still claims when no coordinator exists",
            "    if (forced === 'implementation') return { role: forced, coordinator: null }\n",
            "",
            "never claims",
        ),
        Mutation(
            "the elected role is never stored",
            "      state.role = r.role\n",
            "",
            "the first session is elected coordinator",
        ),
        # Fable's review of #1728: each fix is held by its own check.
        Mutation(
            "a worktree added while gh answers does not cancel the clear",
            "    if (!(await allMerged($)) || !still()) {",
            "    if (!(await allMerged($))) {",
            "P1: a tool call after the turn ended",
        ),
        Mutation(
            "a tool call does not move the epoch",
            "      job.epoch += 1\n      const cmd",
            "      const cmd",
            "P1: a tool call after the turn ended",
        ),
        Mutation(
            "the reset prompt interpolates any handoff text",
            "${safe(handoff, SAFE_PATH) ?? 'the handoff you wrote (HANDOFF.md, or your last handoff comment)'}",
            "${handoff}",
            "P3: a path, branch or session id with a newline",
        ),
        Mutation(
            "a branch with a newline is kept in the compact instructions",
            "(safe(b, SAFE_BRANCH) ? `${p} (${b})` : p)",
            "`${p} (${b})`",
            "P3: a path, branch or session id with a newline",
        ),
        Mutation(
            "a handoff comment counts without its URL",
            "? lastMatch(COMMENT_URL, text) : null",
            "? (lastMatch(COMMENT_URL, text) ?? 'a comment') : null",
            "P2: a handoff comment counts only with its URL",
        ),
        Mutation(
            "the first PR URL wins instead of the last",
            "[...String(text ?? '').matchAll(re)].map((m) => m[0]).pop() ?? null",
            "[...String(text ?? '').matchAll(re)].map((m) => m[0]).shift() ?? null",
            "P2: the last full PR URL is kept",
        ),
        Mutation(
            "any word git counts as the git command, prose included",
            "    } else if (head === 'git') yield w.slice(i + 1)",
            "    } else if (w.includes('git')) yield w.slice(w.indexOf('git') + 1)",
            "P3: commands are read as commands",
        ),
        Mutation(
            "a bash -c script is not looked into",
            "    if (SHELLS.has(head)) {",
            "    if (false) {",
            "P3: commands are read as commands",
        ),
        Mutation(
            "a finished background task never decrements the count",
            "  if (job.background > 0) job.background -= 1",
            "  if (job.background > 0) job.background -= 0",
            "a background job that ends",
        ),
    ),
)
