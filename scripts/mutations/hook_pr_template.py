"""Mutation guard: hook_pr_template. Declared here, run by scripts/mutation_check.py (#1389).

Each mutation lets a PR body through without the sections the repo's own template requires, or
refuses one that carries them, which is how a hook gets disabled.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_pr_template",
    subject="plugins/rails-flow/hooks/scripts/lib/pr_template.py",
    selftest="plugins/rails-flow/hooks/scripts/lib/pr_template.py",
    mutations=(
        Mutation(
            "a template's (optional) marker is ignored, so the section is required",
            'CONDITIONAL = re.compile(r"^\\s*(if|optional)\\b|\\((optional|if\\b[^)]*)\\)", re.I)',
            'CONDITIONAL = re.compile(r"^\\s*if\\b", re.I)',
            "CONTROL: (if applicable), (optional) and a leading Optional mark a section conditional",
        ),
        Mutation(
            "a missing section is never reported",
            "            if not CONDITIONAL.search(h) and core(h) and core(h) not in have]",
            "            if False]",
            "a body missing one section is refused, and names it",
        ),
        Mutation(
            "headings match exactly, so a template's em-dash suffix is demanded verbatim",
            "    text = re.split(r\"\\s[—–-]\\s|:|\\(\", heading, maxsplit=1)[0]",
            "    text = heading",
            "CONTROL: a heading matches on its core text (before the em dash)",
        ),
        Mutation(
            "an `If …` section is required like any other",
            "            if not CONDITIONAL.search(h) and core(h)",
            "            if core(h)",
            "CONTROL: an `If …` section is conditional and may be left out",
        ),
        Mutation(
            "headings in a template comment are required",
            "    text = re.sub(r\"<!--.*?-->\", \"\", text, flags=re.S)",
            "    pass",
            "CONTROL: a heading inside a template comment or fence is not required",
        ),
        Mutation(
            "prose naming a section counts as the section",
            "    have = {core(h) for h in headings(body_text)}",
            "    have = {core(h) for h in headings(template_text, \"##\")} if re.search(r\"how to test\", body_text, re.I) else {core(h) for h in headings(body_text)}",
            "section names in prose are not sections",
        ),
        Mutation(
            "the docs/ home is not searched",
            'DIRS = (".github", "", "docs")',
            'DIRS = (".github", "")',
            "an uppercase template under docs/ is found",
        ),
        Mutation(
            "the name is matched case-sensitively, so PULL_REQUEST_TEMPLATE.md is missed",
            "                if entry.name.lower() == NAME and entry.is_file():",
            "                if entry.name == NAME and entry.is_file():",
            "an uppercase template under docs/ is found",
        ),
    ),
)
