"""Mutation guard: check_i18n_setup. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #799. i18n is situational, so the check is DECLARATION-DRIVEN: setup-flow asks and the
    # answer is recorded as `config.x.locales`. Without a declaration there are only two
    # options and both are wrong — gate everyone, or gate nobody.
    name="check_i18n_setup",
    subject="plugins/rails-flow/scripts/check_i18n_setup.py",
    selftest="plugins/rails-flow/scripts/check_i18n_setup.py",
    mutations=(
        Mutation(
            # Rails' own guide: I18n.locale "can leak into subsequent requests served by the
            # same thread/process". Puma is threaded and reuses threads.
            "assigning I18n.locale in a controller stops being a finding",
            "    if uncommented(controller_text, ASSIGNS_LOCALE):",
            "    if False:",
            # The exit code alone cannot witness this: with the clause off, the NEXT clause
            # fires on the same input and the verdict is still 1. Only the message differs.
            "...naming the cross-request leak",
        ),
        Mutation(
            "a project with no locale wrapper at all passes",
            "    elif not uncommented(controller_text, WITH_LOCALE):",
            "    elif False:",
            "...saying every request renders in the default",
        ),
        Mutation(
            "rails-i18n stops being required, so Rails' own strings stay English",
            '    if gemfile is not None and "rails-i18n" not in declared_gems(gemfile):',
            "    if False:",
            "a missing rails-i18n FAILS",
        ),
        Mutation(
            # Demanding locale files from a monolingual project is the false positive that
            # gets a rule ignored.
            "a declared monolingual project gets the full multi-locale ruleset",
            "    if len(locales) < 2:",
            "    if False:",
            "a declared monolingual project is not-applicable",
        ),
        Mutation(
            # None and ["en"] are DIFFERENT answers: "nobody decided" versus "we chose one".
            # Collapsing them makes the not-applicable state a guess.
            "an undeclared project is silently treated as having chosen one locale",
            '    if locales is None:\n        return 3, ("not applicable — this project has not declared',
            '    if locales is None:\n        locales = ["en"]\n    if False:\n        return 3, ("not applicable — this project has not declared',
            "...and says a declaration is what setup-flow adds",
        ),
        Mutation(
            "the declaration is never read, so nothing is ever applicable",
            'for p in cfg.glob("**/*.rb")) if cfg.is_dir() else ""',
            'for p in cfg.glob("**/*.nope")) if cfg.is_dir() else ""',
            "a wrapped multi-locale app passes",
        ),
    ),
)
