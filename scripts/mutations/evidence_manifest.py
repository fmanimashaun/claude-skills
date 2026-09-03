"""Mutation guard: evidence_manifest. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="evidence_manifest",
    subject="plugins/qa-flow/scripts/evidence_manifest.py",
    selftest="plugins/qa-flow/scripts/evidence_manifest_selftest.py",
    mutations=(
        Mutation(
            "a truncated final line crashes the parse (#111's own defect)",
            "        except json.JSONDecodeError:\n            truncated += 1\n            continue",
            "        except json.JSONDecodeError:\n            raise",
            "",   # the killed-run fixtures raise Unusable; any failure counts
        ),
        Mutation(
            "unreached units stop being distinguished from a complete run",
            '        "unreached": unreached,\n        "aborted": bool(unreached) or truncated > 0,',
            '        "unreached": [],\n        "aborted": False,',
            "unreached",
        ),
        Mutation(
            "full-page evidence accepted for a component purpose",
            'elif purpose in CLIPPED_PURPOSES and capture != "clipped":',
            "elif False:",
            "full-page",
        ),
    ),
)
