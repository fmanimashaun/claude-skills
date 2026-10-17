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
            'r"\\b(?:uploads?|csv|',
            'r"\\b(?:uplo4ds?|csv|',
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
            '|authori[sz]ation|api (?:key|token))\\b", re.I)),',
            '|authori[sz]ation|api (?:key|token))", re.I)),',
            "a word inside another word is not a match",
        ),
        Mutation(
            "no input at all stops being exit 2, so an unknown plan reads as no boundary",
            "    if not text.strip() and not args.path:",
            "    if False:",
            "no input at all is exit 2",
        ),
        Mutation(
            "import goes back to a bare word, so a plan that imports a helper module owes a model",
            "(?:bulk |data )import|imports? (?:an? |the |their |that |this )?(?:files?|csv|spreadsheets?|data|records?|rows?))",
            "(?:bulk |data )import|imports?)",
            "importing a helper module is not a boundary",
        ),
        Mutation(
            "the auth words stop needing a change verb, so a login page tweak owes a model",
            'r"\\b(?:add|adds|adding|new|change|',
            'r"\\b(?:|add|adds|adding|new|change|',
            "a login page css tweak is not a boundary",
        ),
        Mutation(
            "secrets stop being a boundary",
            '("secrets", re.compile(r"\\b(?:secrets?|credentials|',
            '("secrets", re.compile(r"(?!)\\b(?:secrets?|credentials|',
            "a secret is a boundary",
        ),
        Mutation(
            "input parsing stops being a boundary",
            '("input-parsing", re.compile(r"\\bparse[sd]?',
            '("input-parsing", re.compile(r"\\bparsx[sd]?',
            "parsing partner xml is a boundary",
        ),
        Mutation(
            "a privacy filter stops being a boundary",
            '|\\b(?:hide|restrict|mask|redact|limit)\\b',
            '|\\b(?:hidx|restrict|mask|redact|limit)\\b',
            "hiding a field from everyone else is a boundary",
        ),
    ),
)
