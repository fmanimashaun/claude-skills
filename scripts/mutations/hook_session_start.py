"""Mutation guard: hook_session_start. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #838. The SessionStart drift nudge read a two-column manifest while every curator wrote three,
# so every row was skipped in silence and the nudge never fired. The harness drives the REAL hook.
GUARD = Guard(
    name="hook_session_start",
    subject="plugins/rails-flow/hooks/scripts/session-start.sh",
    selftest="plugins/rails-flow/scripts/check_drift_signal.py",
    needs=('plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
           # guard-claims.sh runs extract_claims.py; without it the harness's two claim
           # fixtures fail in the staged tempdir and every mutation reads as caught (#1109).
           'plugins/rails-flow/scripts/extract_claims.py'),   # check_hook_gates drives BOTH plugins' hooks (#906)
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
        Mutation(
            # #1243: the measured ref is never named, so a stale checkout's count reads as the project's.
            "a checkout behind its upstream no longer says which tree was measured",
            "    if [ \"${behind:-0}\" -gt 0 ]; then\n",
            "    if false; then\n",
            "a checkout 3 behind its upstream names the measured ref and the gap",
        ),
        Mutation(
            # ...and the fires-always direction: the line on every session start costs budget and
            # teaches readers to skip it.
            "the measured-ref line prints even when the checkout is level",
            "    if [ \"${behind:-0}\" -gt 0 ]; then\n",
            "    if true; then\n",
            "...and a checkout LEVEL with a real upstream does not print that line",
        ),
    ),
)
