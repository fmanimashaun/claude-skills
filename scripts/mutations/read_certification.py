"""Mutation guard: read_certification. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #721. The reported bug was a MISDIAGNOSIS, so the mutations are about the message being
    # right, not merely about denying. Each clause gets its own fixture.
    name="read_certification",
    subject="plugins/qa-flow/scripts/read_certification.py",
    selftest="plugins/qa-flow/scripts/read_certification.py",
    mutations=(
        Mutation(
            "a non-JSON stamp is reported as a failed verdict again, which is the wrong problem",
            "    except ValueError:\n        return NOT_JSON, \"\"",
            "    except ValueError:\n        return EMPTY, \"\"",
            "a text stamp is NOT_JSON, not a failed verdict",
        ),
        Mutation(
            # A lenient reader would grep PASS out of prose and unlock the promotion.
            "the stamp is parsed leniently, so free text containing PASS reads as PASS",
            "        data = json.loads(raw)",
            '        data = {"verdict": "PASS"} if "PASS" in raw else json.loads(raw)',
            "a text stamp containing 'PASS' does not yield PASS",
        ),
        Mutation(
            "a whitespace-only field counts as set",
            "    return (OK, text) if text else (EMPTY, \"\")",
            "    return OK, text",
            "a whitespace-only verdict is EMPTY",
        ),
        Mutation(
            "the not-JSON message stops saying that re-certifying alone will not help",
            '                f"re-certify. (Re-certifying without replacing this file will not help.)")',
            '                f"re-certify.")',
            "warns that re-certifying alone will not help",
        ),
    ),
)
