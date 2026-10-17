"""Mutation guard: security_scope (#2117). Declared here, run by scripts/mutation_check.py."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="security_scope",
    subject="scripts/security_scope.py",
    selftest="scripts/security_scope.py",
    selftest_args=("--selftest",),
    mutations=(
        Mutation(
            "the upload spelling stops matching, so an upload plan owes no threat model",
            'r"\\b(?:uploads?|imports?|csv|',
            'r"\\b(?:uplo4ds?|imports?|csv|',
            "an upload is a boundary",
        ),
        Mutation(
            "the webhook path stops matching, so a planned webhook controller owes nothing",
            'r"^app/controllers/(?:[^/]+/)*webhooks?/',
            'r"^app/controllers/(?:[^/]+/)*webhookz?/',
            "a planned webhook path is a boundary",
        ),
        Mutation(
            "the trailing word boundary goes, so a word that merely starts with `role` fires",
            '|api key|api token)\\b", re.I)),',
            '|api key|api token)", re.I)),',
            "a word inside another word is not a match",
        ),
        Mutation(
            "no input at all stops being exit 2, so an unknown plan reads as no boundary",
            "    if not text.strip() and not args.path:",
            "    if False:",
            "no input at all is exit 2",
        ),
    ),
)
