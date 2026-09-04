"""Mutation guard: hook_session_start. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #838. The SessionStart drift nudge read a two-column manifest while every curator wrote three,
# so every row was skipped in silence and the nudge never fired. The harness drives the REAL hook.
GUARD = Guard(
    name="hook_session_start",
    subject="plugins/rails-flow/hooks/scripts/session-start.sh",
    selftest="plugins/rails-flow/scripts/check_drift_signal.py",
    needs=('plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts'),   # check_hook_gates drives BOTH plugins' hooks (#906)
    mutations=(
        Mutation(
            "three-column rows are read as two again, so the skill name is taken for the source",
            '    if [ -n "$f3" ]; then src="$f2"; hash="$f3"; else src="$f1"; hash="$f2"; fi',
            '    src="$f1"; hash="$f2"',
            "a 3-column manifest with a header and a 64-char digest reports real drift",
        ),
        Mutation(
            "an unparseable row is skipped in silence again",
            "      unparsed=$((unparsed+1))\n      continue",
            "      continue",
            "reported as unparseable, not skipped",
        ),
        Mutation(
            "the digest is compared at 12 chars regardless of the stored length",
            'cur="$($_rf_hash "$src" 2>/dev/null | cut -c1-${#hash})"',
            'cur="$($_rf_hash "$src" 2>/dev/null | cut -c1-12)"',
            "64-char digest MATCHES reports nothing",
        ),
    ),
)
