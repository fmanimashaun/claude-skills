"""Mutation guard: build_component_axes. Declared here, run by scripts/mutation_check.py (#2272).

Each mutation lets the generated `Catalog axes` line drift from the catalog or from its place under the heading: it is appended elsewhere, never replaced, written for a rule that is not a component, or never written.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="build_component_axes",
    subject="scripts/build_component_axes.py",
    selftest="scripts/build_component_axes.py",
    selftest_args=("--selftest",),
    needs=("scripts/check_component_shapes.py", "scripts/rails_assumptions.py", "scripts/hermetic_git.py", "plugins/rails-flow/scripts/fixture_git.py"),
    mutations=(
        Mutation(
            'the generated line is appended at the end of its section instead of under the heading',
            '                lines.insert(1, want)',
            '                lines.append(want)',
            'a section with a stated list gets its line right under the heading',
        ),
        Mutation(
            'an old generated line is kept when the list changes, so a rebuild adds a second',
            '            lines = [lines[0]] + [ln for ln in lines[1:] if not ln.rstrip().endswith(ccs.AXES_MARK)]',
            '            lines = lines',
            'a changed list replaces its line, never adds a second',
        ),
        Mutation(
            'a non-drawable entry (a rule, not a component) gets a line too',
            '        if isinstance(entry, dict) and entry.get("drawable") is not False:',
            '        if isinstance(entry, dict):',
            'a non-drawable entry is left alone, even one that carries a list',
        ),
        Mutation(
            'a section whose entry states no list still carries its old line',
            '            want = ccs.axes_line(entry)\n            if want:',
            '            want = ccs.axes_line(entry)\n            if False:',
            'a section with a stated list gets its line right under the heading',
        ),
    ),
)
