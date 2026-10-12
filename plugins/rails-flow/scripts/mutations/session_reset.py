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
# Removed, because equivalent once the catch-all hook owned the epoch: a Bash-only bump (the catch-all bumps for every tool, Bash included).
# Also NOT listed: dropping `job.checked.epoch === job.epoch` in turn.complete. maybePrecheck already replaces the
# cached answer with a fresh unanswered one on any tool call, so the comparison is a second line of defence.
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
            "      .run({ command: 'clear' })\n",
            "      .run({ command: 'compact' })\n",
            "job done: the session clears exactly once",
        ),
        Mutation(
            "an await stands ahead of command.run in turn.complete, so a later prompt can be queued before the clear",
            "job.checked.epoch === job.epoch) fire($, job.epoch)\n",
            "job.checked.epoch === job.epoch) { await Promise.resolve(); fire($, job.epoch) }\n",
            "the clear is queued synchronously from turn.complete",
        ),
        Mutation(
            "the coordinator and a role-less session clear too",
            "state.role === 'implementation' && state.hasSurface && jobDoneShape(true)",
            "state.hasSurface && jobDoneShape(true)",
            "only an implementation session clears",
        ),
        Mutation(
            "a claude -p run (no surface) clears",
            "state.role === 'implementation' && state.hasSurface && jobDoneShape(true)",
            "state.role === 'implementation' && jobDoneShape(true)",
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
            "a resumed session is never recognised: the turn count is ignored",
            "return (await $.session.turns()) > 0",
            "return (await $.session.turns()) < 0",
            "every session resumed at once",
        ),
        Mutation(
            "a turn count that cannot be read counts as a fresh start",
            "  } catch {\n    return true\n  }",
            "  } catch {\n    return false\n  }",
            "cannot be read counts as a resume",
        ),
        Mutation(
            "the resumed flag never reaches the election script",
            "(await isResumed($)) ? '1' : '0'",
            "'0'",
            "every session resumed at once",
        ),
        Mutation(
            "a resumed session takes a claim that carries another session's id",
            '[ -n "$hp" ] && [ "$hs" = "$sid" ] && {',
            '[ -n "$hp" ] && {',
            "a different id does not inherit it",
        ),
        Mutation(
            "a resumed session displaces a live coordinator of its own id",
            '{ [ "$hp" = "$me" ] || ! alive "$hp" "$hl"; }',
            '{ true; }',
            "does not displace a LIVE coordinator",
        ),
        Mutation(
            "a resumed session no longer keeps the claim it owns",
            '{ [ "$hp" = "$me" ] || ! alive "$hp" "$hl"; }',
            '{ false; }',
            "stays coordinator",
        ),
        Mutation(
            "the override is ignored for a resumed session",
            'if [ "$resumed" = "1" ] && [ "$force" != "1" ]; then',
            'if [ "$resumed" = "1" ]; then',
            "still claims for a resumed session",
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
            "a turn that ends before the early merge check answers is never cleared",
            "        job.turnEnd = job.touched ? job.epoch : null\n",
            "",
            "the merge check is early",
        ),
        Mutation(
            "work after the clear was queued still gets the reset prompt over it",
            "        if (job.epoch !== epoch) {\n          job.cleared = false",
            "        if (false) {\n          job.cleared = false",
            "the clear is queued synchronously from turn.complete",
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
            ".filter((w) => re.test(w)).pop() ?? null",
            ".filter((w) => re.test(w)).shift() ?? null",
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
            "a new turn does not clear the cached turn end, so a merge answer mid-turn queues a clear",
            "    job.turnEnd = null\n    job.touched = false\n    return next(e)",
            "    job.touched = false\n    return next(e)",
            "P1 round 2: a merge answer that arrives during the NEXT turn",
        ),
        Mutation(
            "only Bash, Write and Edit move the epoch; a Read or Grep leaves the cached answer standing",
            "    job.epoch += 1\n    job.touched = true\n    return next(e)\n  })\n\n  // Cheap",
            "    job.touched = true\n    return next(e)\n  })\n\n  // Cheap",
            "a Read, Grep or Task call also voids",
        ),
        Mutation(
            "a comment word is read as a command",
            "    } else if (c === '#' && word === null) {",
            "    } else if (false) {",
            "P3: a comment word",
        ),
        Mutation(
            "if, then, braces and xargs are not skipped as wrappers",
            "'nohup', '{', 'if', 'then', 'else', 'elif', 'do', 'until', 'while', '!', 'xargs'])",
            "'nohup'])",
            "P3: a comment word",
        ),
        Mutation(
            "only a bare -c opens a shell script, not -lc",
            "/^-[a-z]*c$/.test(x)",
            "x === '-c'",
            "P3: a comment word",
        ),
        Mutation(
            "a path built by the shell is taken at face value",
            "rest[0] === undefined || /[$`{]/.test(rest[0])",
            "rest[0] === undefined",
            "P3: a comment word",
        ),
        Mutation(
            "a tool-free turn counts as the end of the finished job, so an assignment answered in text is cleared",
            "        job.turnEnd = job.touched ? job.epoch : null\n        if (job.touched && state.role",
            "        job.turnEnd = job.epoch\n        if (state.role",
            "round 3: a tool-free turn after the job ended",
        ),
        Mutation(
            "a turn start does not reset the touched flag",
            "    job.turnEnd = null\n    job.touched = false\n",
            "    job.turnEnd = null\n",
            "round 3: a tool-free turn after the job ended",
        ),
        Mutation(
            "until, elif and while are not skipped",
            "'else', 'elif', 'do', 'until', 'while', '!', 'xargs'",
            "'else', 'do', '!', 'xargs'",
            "round 3: until, elif and wrapper options",
        ),
        Mutation(
            "a wrapper's options are read as the command",
            "      while (WRAPPERS.has(wrapper) && i < w.length && w[i].startsWith('-'))",
            "      while (false && i < w.length && w[i].startsWith('-'))",
            "round 3: until, elif and wrapper options",
        ),
        Mutation(
            "a due compaction is never queued at turn.complete",
            "        if (due !== null) {\n          if (job.pending",
            "        if (false) {\n          if (job.pending",
            "a compact is never requested inside a turn",
        ),
        Mutation(
            "a rejected /compact does not re-arm the compaction",
            "    state.rearm = due.key\n",
            "",
            "tried again at the next measure",
        ),
        Mutation(
            "the debug log is written without RAILS_FLOW_DEBUG",
            "if (lines.length === 0 || (await $.env.get('RAILS_FLOW_DEBUG')) !== '1') return",
            "if (lines.length === 0) return",
            "RAILS_FLOW_DEBUG=1 writes each compact decision",
        ),
        # #1728 review: the empty-claim takeover and the handoff that does not survive its worktree.
        Mutation('an empty claim still being written is taken over, so two sessions print coordinator',
                 'young_empty() { [ -z "$hp" ] &&',
                 'young_empty() { false &&',
                 'an empty claim being written is never taken over'),
        Mutation('a handoff inside a removed worktree still counts, so the session clears onto a lost handoff',
                 "    if (r.startsWith('/') ? h === r || h.startsWith(`${r}/`) : h.includes(`/${r.split('/').pop()}/`)) return false\n",
                 '',
                 'a handoff written inside the worktree it then removes does not count'),
        Mutation('the handoff file is not asked for, so a session clears onto a handoff that is gone',
                 '    ok = (await allMerged($)) && (await handoffPresent($))',
                 '    ok = await allMerged($)',
                 'a handoff whose file is gone does not clear'),
        Mutation('a future-dated empty claim counts as young, so clock skew leaves it never taken over',
                 '&& ! future; }',
                 '; }',
                 'an empty claim dated in the FUTURE (clock skew) is stale'),
    ),
)
