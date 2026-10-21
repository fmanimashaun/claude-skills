"""Mutation guard: hook_normalize_linear. Declared here, run by scripts/mutation_check.py (#1980).

The shared normaliser is LINEAR in the length of a line (it was quadratic in BWK awk, macOS: ONE 300 KB line took 13 s through a gate with a 15 s timeout) and
still right at the seams of the 2 KB pieces its output is built in. Each mutation breaks one seam of it; the fixtures that catch them
are the `normalizer_linear` group of check_hook_gates.py. (`hook_normalize_cmd` holds the mutations of what the normaliser DECIDES.) The three TIMING mutants (the buffer that never starts a new piece, the peel joining with a growing string, the ANSI-C decoder one character at a time) are NOT here
either, and they were, until the v1.157.1 release run: they survived on the hosted runner. A string copy that grows with every concatenation is a cost of BWK awk (macOS) and of
mawk (a bare ubuntu image, where they were caught 6/6), but the hosted runner's awk is gawk, where concatenation is amortised and `substr` is O(1): there those mutants are
no slower and cannot be caught. What a mutant can prove on every awk is that the pieces are joined RIGHT (the three below); the ratio fixtures of the `normalizer_linear` group
catch a quadratic habit where the awk makes it quadratic (the doctor's gates on macOS). There is no mutant that puts the per-character `substr` back: it is quadratic
only in BWK awk (macOS), and the harness runs on Linux too, where mawk makes `substr` O(1) and such a mutant would SURVIVE. The ratio fixtures still catch it on macOS.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_normalize_linear",
    subject="plugins/rails-flow/hooks/scripts/lib/normalize_cmd.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "normalizer_linear"),
    narrow_with="--match",
    needs=("plugins/rails-flow/scripts/advisory_scope.py", "plugins/rails-flow/scripts/security_scope.py", "plugins/rails-flow/scripts/check_threat_model.py", "plugins/rails-flow/scripts/detect_stack.py",  # stop-gate.sh runs advisory_scope.py (#2262)
           "plugins/rails-flow/scripts/fixture_git.py", 
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
    ),
)
