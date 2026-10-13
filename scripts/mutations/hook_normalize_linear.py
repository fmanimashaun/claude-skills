"""Mutation guard: hook_normalize_linear. Declared here, run by scripts/mutation_check.py (#1980).

The shared normaliser is LINEAR in the length of a line (it was quadratic in BWK awk, macOS: ONE 300 KB line took 13 s through a gate with a 15 s timeout) and
still right at the seams of the 2 KB pieces its output is built in. Each mutation puts one quadratic habit back, or breaks one seam; the fixtures that catch them
are the `normalizer_linear` group of check_hook_gates.py. (`hook_normalize_cmd` holds the mutations of what the normaliser DECIDES.) There is no mutant that puts the per-character `substr` back: it is quadratic
only in BWK awk (macOS), and the harness runs on Linux too, where mawk makes `substr` O(1) and such a mutant would SURVIVE. The ratio fixtures still catch it on macOS.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_normalize_linear",
    subject="plugins/rails-flow/hooks/scripts/lib/normalize_cmd.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "normalizer_linear"),
    narrow_with="--match",
    needs=("plugins/rails-flow/scripts/fixture_git.py", 
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py', 'plugins/rails-flow/scripts/check_memory_index.py',  # session-start.sh runs all three (#1581, #1828: the harness drives it)
           "plugins/rails-flow/hooks/hooks.json",  # read by check_hook_gates since #1362
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts", "plugins/qa-flow/scripts",
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           # ci-verdict-hint.sh runs ci_verdict_hint.py; unstaged, its fixtures fail and every
           # mutation reads as caught -- the harness reported this guard INERT until it was added (#1173).
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/test_preflight.py', 'plugins/rails-flow/scripts/wip_commit.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',  # release-gate.sh runs it (#1410)
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/qa-flow/scripts/remote_evidence.py',   # the release gate runs it (#1591)
           'plugins/rails-flow/scripts/self_consistency.py'),
    mutations=(
        Mutation(
            'the ANSI-C decoder takes one character at a time again, quadratic in BWK awk: a 300 KB span took 5.8 s (#1980)',
            '    if (c != "\\\\") { r = substr(s, i); match(r, /^[^\\\\\\047]+/); if (!cut) v = v substr(r, 1, RLENGTH); i += RLENGTH; continue }',
            '    if (c != "\\\\") { if (!cut) v = v c; i++; continue }',
            'ONE ANSI-C span costs about 4 times',
        ),
        Mutation(
            'the output buffer never starts a new piece, so every character is appended to one growing string (#1980)',
            'if (length(OB) >= 2048)',
            'if (length(OB) >= 2000000000)',
            'ONE line of plain characters costs about 4 times',
        ),
        Mutation(
            "the join drops the buffer's last piece, so the end of a long word is lost (#1980)",
            '  if (OB != "") { NP++; PP[NP] = OB; OB = "" }\n  m = NP; NP = 0',
            '  m = NP; NP = 0',
            'one plain word of 255 characters comes out whole',
        ),
        Mutation(
            'the pairwise join puts a pair the wrong way round (#1980)',
            'PP[k] = (i < m) ? PP[i] PP[i + 1] : PP[i]',
            'PP[k] = (i < m) ? PP[i + 1] PP[i] : PP[i]',
            'one plain word of 5000 characters comes out whole',
        ),
        Mutation(
            'a span of 256 characters or more loses its last character (#1980)',
            'return substr(CS, a, b - a + 1)',
            'return substr(CS, a, b - a)',
            'a single-quoted span of 257 characters comes out whole',
        ),
        Mutation(
            "the peel joins a segment's words with a growing string again, quadratic in the number of words (#1980)",
            '    OB = ""; NP = 0\n    for (j = i; j <= n; j++) app((j > i ? " " : "") t[j])\n    print joined()',
            '    out = ""\n    for (j = i; j <= n; j++) out = out (j > i ? " " : "") t[j]\n    print out',
            'ONE line of short words costs about 4 times',
        ),
    ),
)
