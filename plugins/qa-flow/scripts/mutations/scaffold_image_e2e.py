"""Mutation guard: scaffold_image_e2e. Declared here, run by scripts/mutation_check.py (#866). The runner must refuse a target off this
machine, fail (never skip) without a seed, and never retry; robot_descriptor.py --selftest drives it with stub curl/npx (#1837)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="scaffold_image_e2e",
    subject="scaffold/qa/seed/image-e2e",
    selftest="scripts/robot_descriptor.py",
    selftest_args=("--selftest",),
    needs=("scaffold/qa/seed/assert-local-target.ts", "scaffold/qa/seed/local-target.setup.ts", "scaffold/qa/e2e/support/local-target.ts"),
    mutations=(
        Mutation(
            "the base URL is not checked, so the robot can be aimed at production",
            'origin="$(node --experimental-strip-types --no-warnings seed/assert-local-target.ts "$QA_BASE_URL")" || exit 2\n',
            'origin="$QA_BASE_URL"\n',
            "runner: a non-local QA_BASE_URL must exit 2",
        ),
        Mutation(
            "a missing seed is skipped instead of failing the run",
            '  || { echo "image-e2e: no QA seed in $seed (personas.json and records.json are both needed) -- run the project\'s seed first" >&2; exit 1; }',
            '  || true',
            "runner: a missing seed must FAIL the run",
        ),
        Mutation(
            "failures are retried, so a flaky real failure can read as a pass",
            '--workers=1 --retries=0 "$@"',
            '--workers=1 --retries=2 "$@"',
            "runner: a ready stack runs playwright with QA_REQUIRE_SEED=1, --retries=0",
        ),
        Mutation(
            "a caller's --retries is passed through",
            '--retries|--retries=*) echo',
            '--no-such-flag) echo',
            "runner: a caller's --retries is refused",
        ),
        Mutation(
            "curl asks the raw text, not the guarded origin",
            'curl -sk -o /dev/null -f --max-time 5 "${origin}${up_path}"',
            'curl -sk -o /dev/null -f --max-time 5 "${QA_BASE_URL%/}${up_path}"',
            "runner: curl asks the ORIGIN the guard printed",
        ),
        Mutation(
            "a health path that changes the host is accepted",
            'if ! [[ "$up_path" =~ ^/[A-Za-z0-9/_.-]*$ ]] || [[ "$up_path" == //* ]]; then',
            'if false; then',
            "runner: a QA_UP_PATH that would change the host is refused",
        ),
        Mutation(
            "specs are not told to fail on a missing seed",
            "export QA_REQUIRE_SEED=1\n",
            "",
            "runner: a ready stack runs playwright with QA_REQUIRE_SEED=1",
        ),
    ),
)
