"""Mutation guard: check_vendored_alone. Declared here, run by scripts/mutation_check.py (#1261).

The mutations that matter make the gate VACUOUS: running the script where its siblings are (the state
that hid #1261), ignoring the exit code, or discovering nothing and reporting clean.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_vendored_alone",
    subject="scripts/check_vendored_alone.py",
    selftest="scripts/check_vendored_alone.py",
    mutations=(
        # THE MUTATION THAT RECREATES THE BUG: run the script in its plugin directory, beside the
        # sibling it needs, and every needy script passes.
        Mutation(
            "the script is run beside its siblings instead of alone",
            "        shutil.copy2(script, copy)\n",
            "        shutil.copytree(script.parent, td, dirs_exist_ok=True)\n",
            "a script that needs its sibling fails when run alone",
        ),
        Mutation(
            "a failing selftest is not a finding",
            "        if rc != 0:\n",
            "        if False:\n",
            "the needy script is reported",
        ),
        Mutation(
            "scripts a doc tells projects to vendor are no longer discovered",
            "            named.update(VENDORED_PATH.findall(",
            "            set().update(VENDORED_PATH.findall(",
            "a script a doc tells projects to vendor is discovered",
        ),
        Mutation(
            "scripts promising to work vendored alone are no longer discovered",
            "        if ALONE_PROMISE in source or PROMISE_WORDING.search(source):",
            "        if False and (ALONE_PROMISE in source or PROMISE_WORDING.search(source)):",
            "a script that promises to work vendored alone is discovered",
        ),
        Mutation(
            "a vendoring instruction naming no shipped script stops being a finding",
            '            problems.append(f"a doc tells projects to vendor .claude/scripts/{name}, and no plugin ships it")',
            "            pass",
            "a vendoring instruction naming no shipped script is a finding",
        ),
        Mutation(
            'a doc paragraph that tells projects to vendor a script by its bare name is no longer read (#1767)',
            '                if VENDOR_VERB.search(paragraph):\n',
            '                if False:\n',
            'a script a doc tells projects to vendor by its bare name is discovered',
        ),
        Mutation(
            'the wording a script uses of itself is narrowed back to vendored ALONE, so `vendors this file` is not discovered (#1767)',
            '        if ALONE_PROMISE in source or PROMISE_WORDING.search(source):',
            '        if ALONE_PROMISE in source:',
            'a script whose source says a project vendors it is discovered',
        ),
        Mutation(
            'the vendoring verb is no longer required, so every script a doc names in backticks is run (#1767)',
            '                if VENDOR_VERB.search(paragraph):\n',
            '                if True:\n',
            'a script a doc names without a vendoring verb is not run',
        ),
        Mutation(
            'the vendor directory is read as a vendoring verb, so `the vendor directory` captures the script beside it (#1767)',
            '(?!\\s+(?:dir|folder))',
            '',
            'a script named only beside the vendor DIRECTORY is not run',
        ),
        Mutation(
            'a digit in a name is no longer read in a .claude/scripts path, so check2.py under .claude/scripts is never found (#1773)',
            'VENDORED_PATH = re.compile(r"\\.claude/scripts/([a-z0-9_]+\\.py)")',
            'VENDORED_PATH = re.compile(r"\\.claude/scripts/([a-z_]+\\.py)")',
            'a script under .claude/scripts with a digit in its name is discovered',
        ),
        Mutation(
            'a digit in a name is no longer read beside a vendoring verb, so a script named step2.py is never found (#1773)',
            'BACKTICKED_SCRIPT = re.compile(r"`([a-z0-9_]+\\.py)`")',
            'BACKTICKED_SCRIPT = re.compile(r"`([a-z_]+\\.py)`")',
            'a script with a digit in its name, named beside a vendoring verb, is discovered',
        ),
        Mutation(
            'the verb copy is no longer read, so Copy `x.py` into your project does not put x.py under the gate (#1773)',
            '    re.compile(r"\\b(?:copy|copies|copied|copying)\\s+" + _ARTICLE + r"`([a-z0-9_]+\\.py)`", re.I),\n',
            '',
            'a script a doc tells projects to copy, with the verb beside its name, is discovered',
        ),
        Mutation(
            'drop in is no longer read, so Drop in `x.py` does not put x.py under the gate (#1773)',
            '    re.compile(r"\\bdrop\\s+in\\s+" + _ARTICLE + r"`([a-z0-9_]+\\.py)`", re.I),\n',
            '',
            'a script a doc tells projects to drop in is discovered',
        ),
        Mutation(
            'Drop `x.py` in is no longer read, so the verb before the name and in after it does not put x.py under the gate (#1773)',
            '    re.compile(r"\\bdrop(?:s|ped|ping)?\\s+" + _ARTICLE + r"`([a-z0-9_]+\\.py)`\\s+in\\b", re.I),\n',
            '',
            'the verb before its name and in after it, is discovered',
        ),
        Mutation(
            'copy may sit anywhere before the name, so a script only near the word copy is run (#1773)',
            '    re.compile(r"\\b(?:copy|copies|copied|copying)\\s+" + _ARTICLE + r"`([a-z0-9_]+\\.py)`", re.I),\n',
            '    re.compile(r"\\b(?:copy|copies|copied|copying)\\s+(?:\\w+\\s+){0,6}" + _ARTICLE + r"`([a-z0-9_]+\\.py)`", re.I),\n',
            'a script only near the word copy, not beside it as a verb, is not run',
        ),
    ),
)
