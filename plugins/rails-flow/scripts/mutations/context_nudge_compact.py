"""Mutation guard: context_nudge_compact. Declared here, run by scripts/mutation_check.py (#1723, #1724)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1723/#1724. context-nudge.mjs carries the mid-job compaction and the one role line, because it owns
# session.measure and prompt.submit (a plugin registers each event once). The selftest is
# tests/session-reset.unit.mjs, which drives both modules under a hand-built host.
GUARD = Guard(
    name="context_nudge_compact",
    subject="hooks/context-nudge.mjs",
    selftest="scripts/check_mods.py",
    selftest_args=("session-reset",),
    needs=("tests/session-reset.unit.mjs", "hooks/budget-guard.mjs", "hooks/session-reset.mjs"),
    mutations=(
        Mutation(
            "a source compacts on every measure past the threshold, not once per climb",
            "      compacted[key] = true\n",
            "",
            "mid-job at the context threshold",
        ),
        Mutation(
            "a compaction that was rejected is never retried",
            "            compacted[key] = false\n          }\n        })()",
            "            // never retried\n          }\n        })()",
            "a compaction that is rejected",
        ),
        Mutation(
            "a session whose job is done is compacted instead of cleared",
            "if (role === null || (role === 'implementation' && (jobDoneShape() || job.pending))) return",
            "if (role === null) return",
            "a session whose job is done is not compacted",
        ),
        Mutation(
            "a claude -p run (no surface) compacts",
            "      if ((await $.session.surfaces()).length === 0) return\n",
            "",
            "claude -p (no surface) and a role-less",
        ),
        Mutation(
            "the climb flag is never reset, so the next climb is never compacted",
            "      if (!live) compacted[key] = false\n",
            "",
            "the next climb compacts again",
        ),
        Mutation(
            "the role line is added on every person prompt",
            "      askedRole = true\n",
            "",
            "told once",
        ),
        Mutation(
            "the elected role is not what the line says",
            "lines.push(state.line ?? ROLE_LINE)",
            "lines.push(ROLE_LINE)",
            "the first session is elected coordinator",
        ),
        Mutation(
            "RAILS_FLOW_COMPACT_PCT is ignored",
            "wholePct(await $.env.get('RAILS_FLOW_COMPACT_PCT'), DEFAULT_COMPACT_PCT)",
            "DEFAULT_COMPACT_PCT",
            "RAILS_FLOW_COMPACT_PCT moves the compact threshold",
        ),
    ),
)
