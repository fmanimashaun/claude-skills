"""Mutation guard: board_refresh_hook. Declared here, run by scripts/mutation_check.py (#1585, part 2b).

The Stop hook is the one part of the status board that runs without being asked, so the breaks that matter are the ones
that make it run where it was not invited, run every time, run past its time box, speak, or fail a stop.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="board_refresh_hook",
    subject="hooks/scripts/board-refresh.sh",
    selftest="scripts/status_board_selftest.py",
    deps=("scripts/status_board.py",),
    needs=("scripts/status_board_verdicts.json", "hooks/hooks.json"),
    mutations=(
        Mutation(
            'the hook runs in a repository that never asked for a board',
            '[ -f "$root/.claude/board.config.json" ] || [ -f "$board" ] || exit 0\n',
            '',
            'with no board config and no earlier board, the hook writes nothing',
        ),
        Mutation(
            'every Stop re-measures the board, whatever its age',
            'if [ -f "$board" ] && [ -n "$(find "$board" -mmin "-$fresh" 2>/dev/null)" ]; then',
            'if false; then',
            'a board newer than the throttle is left alone',
        ),
        Mutation(
            'a board is never refreshed once it exists',
            '[ -n "$(find "$board" -mmin "-$fresh" 2>/dev/null)" ]',
            '[ -n "$(find "$board" 2>/dev/null)" ]',
            'a board older than the throttle is measured again',
        ),
        Mutation(
            'the time box is ignored',
            '--budget-seconds "$budget"',
            '--budget-seconds 100',
            'a stalled gh is bounded by BOARD_HOOK_BUDGET',
        ),
        Mutation(
            "the collector's output reaches the model",
            '>/dev/null 2>&1 || true\nexit 0',
            '|| true\nexit 0',
            'prints NOTHING',
        ),
        Mutation(
            "the collector's exit code fails the stop",
            '>/dev/null 2>&1 || true\nexit 0',
            '>/dev/null 2>&1\nexit $?',
            'a collector that exits 7 never fails the stop',
        ),
    ),
)
