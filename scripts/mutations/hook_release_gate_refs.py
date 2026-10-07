"""Mutation guard: hook_release_gate_refs (#1600). Declared here, run by scripts/mutation_check.py.

The release gate is a PreToolUse hook, so it runs before the permission prompt. A ref taken from the gated
command's text must never reach `git fetch` as an option (`--upload-pack=<program>` runs the program over a
local-path or ssh origin) or as a refspec (`a:b` writes a local ref). The `release_gate_refs` group drives each
site with a marker file over a local-path origin. Each mutation removes one guard; its fixture must go red.

NOT MUTATED, ON PURPOSE: `--end-of-options` on the three `git fetch` calls. With `plain_ref` in front of the
only fetch that takes a ref from the command's text it cannot be observed (a mutation would survive), and the
other two fetches take an object id by construction. It stays as hardening the issue asked for.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_release_gate_refs",
    subject="plugins/qa-flow/hooks/scripts/release-gate.sh",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "release_gate_refs"),
    needs=("plugins/rails-flow/hooks/hooks.json",
           "plugins/rails-flow/hooks/scripts", "plugins/qa-flow/hooks/scripts",
           "plugins/qa-flow/scripts",
           'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py',  # session-start.sh runs both (#1581: the harness drives it)
           'plugins/rails-flow/scripts/check_criteria.py',
           'plugins/rails-flow/scripts/check_handoff.py',
           'plugins/rails-flow/scripts/extract_claims.py',
           'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/session_reaper.py', 'plugins/rails-flow/scripts/process_containment.py',
           'plugins/qa-flow/scripts/read_certification.py',
           'plugins/qa-flow/scripts/push_targets.py',
           'plugins/qa-flow/scripts/release_evidence.py',
           'plugins/qa-flow/scripts/remote_evidence.py',   # the release gate runs it (#1591)
           'plugins/rails-flow/scripts/self_consistency.py'),
    mutations=(
        Mutation(
            "the fetch is the original: no name check, no end of options, so --upload-pack=<program> runs",
            '        if [ -z "$c" ] && plain_ref "$ref"; then\n          git fetch -q --end-of-options origin "$ref" 2>/dev/null',
            '        if [ -z "$c" ]; then\n          git fetch -q origin "$ref" 2>/dev/null',
            "runs no program",
        ),
        Mutation(
            "a ref is not checked for being a plain name, so a refspec is fetched and writes a local ref",
            'plain_ref() { case "$1" in ""|-*|*[!A-Za-z0-9._/-]*|*..*|/*|*//*|*/|.*|*/.*|*.lock|*.lock/*|*.) return 1 ;; esac; return 0; }',
            'plain_ref() { return 0; }',
            "a refspec) is never fetched",
        ),
        Mutation(
            "this checkout's stamp may carry a sha that is not a commit id",
            '  case "$csha" in *[!0-9a-fA-F]*) JWHY="certification sha',
            '  case "$csha" in "__never__") JWHY="certification sha',
            "a stamp whose `sha` is an option is denied",
        ),
        Mutation(
            "another repository's stamp may carry a sha that is not a commit id",
            '  case "$csha" in *[!0-9a-fA-F]*) JWHY="${repo}: certification sha',
            '  case "$csha" in "__never__") JWHY="${repo}: certification sha',
            "whose `sha` is a path is denied",
        ),
        # ---- (#1606) the same untrusted text, spliced into ANOTHER repository's API path, and the third fetch --------
        Mutation(
            "a ref that is not a plain name is put in another repository's commits path",
            '        ! plain_ref "$ref" || c="$(gh_lookup api "repos/${_R}/commits/${ref}" -q .sha || true)"',
            '        c="$(gh_lookup api "repos/${_R}/commits/${ref}" -q .sha || true)"',
            "a REST merge's head with a fragment",
        ),
        Mutation(
            "a release target that is not a plain name is put in another repository's API path",
            '    [ -z "$tgt" ] || plain_ref "$tgt" || return 1\n',
            '',
            "a release's --target that climbs",
        ),
        Mutation(
            "a release tag that is not a plain name is put in another repository's API path",
            '    [ -z "$tag" ] || plain_ref "$tag" || return 1\n    [ -z "$tgt" ] || plain_ref "$tgt" || return 1\n',
            '    [ -z "$tgt" ] || plain_ref "$tgt" || return 1\n',
            "a release's tag that climbs",
        ),
        Mutation(
            "what `git ls-remote` printed is handed to `git fetch` whatever it is",
            '        case "$t" in ""|*[!0-9a-fA-F]*) return 1 ;; esac\n',
            '',
            "an object id from `git ls-remote` that is an option",
        ),
        # ---- (#1610) hardening left by the #1609 review ----------------------------------------------------------------
        Mutation(
            "the commit id GitHub's API returned is put in a contents URL whatever it is",
            '  case "$sha" in ""|*[!0-9a-fA-F]*) JWHY="${repo}: ${what} (${sha:0:20}) is not a commit id, so its certification cannot be read."; return 1 ;; esac\n',
            '',
            "is never put in a contents URL",
        ),
        Mutation(
            "a release tag with a glob becomes a `git ls-remote` pattern",
            '    [ -z "$tag" ] || plain_ref "$tag" || return 1\n    if [ -n "$tag" ] && git remote get-url origin',
            '    if [ -n "$tag" ] && git remote get-url origin',
            "a release tag with a glob is never handed to",
        ),
        Mutation(
            "plain_ref is the old charset again, so names git refuses (a// , ./, x.lock) are asked about",
            'plain_ref() { case "$1" in ""|-*|*[!A-Za-z0-9._/-]*|*..*|/*|*//*|*/|.*|*/.*|*.lock|*.lock/*|*.) return 1 ;; esac; return 0; }',
            'plain_ref() { case "$1" in ""|-*|*[!A-Za-z0-9._/-]*|*..*) return 1 ;; esac; return 0; }',
            "which git refuses as a name",
        ),
    ),
)
