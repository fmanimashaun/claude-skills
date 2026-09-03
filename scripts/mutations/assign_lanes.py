"""Mutation guard: assign_lanes. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #661. Overlap is the whole safety property, and the budget note is the only place spend is
    # ever mentioned across concurrent sessions -- silence there reads as "bounded".
    name="assign_lanes",
    subject="plugins/rails-flow/scripts/assign_lanes.py",
    selftest="plugins/rails-flow/scripts/assign_lanes.py",
    needs=("plugins/rails-flow/hooks/scripts/guard-lane.sh",),
    mutations=(
        Mutation(
            "overlapping lanes are accepted, so two sessions edit one tree",
            '            if a == b or a.startswith(b + "/") or b.startswith(a + "/"):',
            "            if False:",
            "'app' vs 'app/models' refused",
        ),
        Mutation(
            # #660 must precede #661: an advisory protocol is survivable while nobody can enter
            # the mode, and is not once a launcher can put four sessions in it.
            "lanes are assigned without the guard that makes the protocol real",
            "    if not GUARD.is_file():",
            "    if False:",
            "a missing lane guard refuses assignment",
        ),
        Mutation(
            "spend stops being reported, so N sessions read as bounded",
            '        return (f"**Spend is unbounded across {n} sessions and nothing here meters it.** Pass "',
            '        return (f"across {n} sessions. Pass "',
            "no budget says so plainly",
        ),
    ),
)
