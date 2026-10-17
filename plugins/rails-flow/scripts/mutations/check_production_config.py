"""Mutation guard: check_production_config. Declared here, run by scripts/mutation_check.py (#2120).

The mutations that matter make a rule VACUOUS (a comment, `= nil` or `.clear` counts as a setting, the wrong value is
accepted, a guard that does not guard is trusted) or make it fire on the wrong text (a bare `*`), or let an exemption
clear more than the one rule it names.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_production_config",
    subject="scripts/check_production_config.py",
    selftest="scripts/check_production_config.py",
    mutations=(
        Mutation(
            "a leading # is stripped before reading, so the commented-out config.hosts of the trap counts as set",
            '        code = line.split("#", 1)[0].rstrip()',
            '        code = re.sub(r"^(\\s*)#\\s?", r"\\1", line).split("#", 1)[0].rstrip()',
            "a commented-out config.hosts is a finding",
        ),
        Mutation(
            "config.hosts = nil / [] count as set",
            '        empty = value in ("nil", "[]", "%w[]", "%i[]") or (value in ("[", "%w[", "%i[") and nxt.startswith("]"))',
            "        empty = False",
            "is unset, so a finding",
        ),
        Mutation(
            "config.hosts.clear no longer unsets an earlier assignment",
            '            if re.match(r"^\\s*config\\.hosts\\.clear\\b", code):\n                hit = None',
            '            if re.match(r"^\\s*config\\.hosts\\.clear\\b", code):\n                pass',
            "after an assignment unsets it",
        ),
        Mutation(
            "force_ssl = false is accepted as long as it is set",
            '    if not ssl or ssl[1] != "true":',
            "    if not ssl:",
            "force_ssl = false is a finding",
        ),
        Mutation(
            "assume_ssl is read as force_ssl",
            '    ssl = setting(prod, "force_ssl") or setting(app, "force_ssl")',
            '    ssl = setting(prod, "assume_ssl") or setting(app, "assume_ssl")',
            "assume_ssl without force_ssl is a finding",
        ),
        Mutation(
            "consider_all_requests_local = true is never a finding",
            '    if local and local[1] == "true":',
            "    if False:",
            "consider_all_requests_local = true is a finding",
        ),
        Mutation(
            "an origins list wrapped onto the next line is read as its first line only",
            '        while (stmt.count("(") > stmt.count(")") or stmt.count("[") > stmt.count("]")\n               or stmt.rstrip().endswith(",")) and j + 1 < len(lines):',
            "        while False:",
            "a wrapped origins list is read whole",
        ),
        Mutation(
            "any * counts as a wildcard origin (the article's bare grep)",
            '''        if re.search(r"(?:^|[\\s(\\[,])[\\"']\\*[\\"']|/(?:\\\\A)?\\.\\*(?:\\\\z)?/", stmt):''',
            '        if re.search(r"\\*", stmt):',
            "CONTROL: a subdomain pattern",
        ),
        Mutation(
            "a wildcard origin is never found",
            '''        if re.search(r"(?:^|[\\s(\\[,])[\\"']\\*[\\"']|/(?:\\\\A)?\\.\\*(?:\\\\z)?/", stmt):''',
            "        if False:",
            "is a finding that names its file and line",
        ),
        Mutation(
            "a development guard is not required, so every dev-only mount passes or fails alike",
            "        if DEBUG_ROUTE.search(s) and not any(stack) and not modified:",
            "        if DEBUG_ROUTE.search(s):",
            "CONTROL: the same mount inside `if Rails.env.development?` is clean",
        ),
        Mutation(
            "the else branch of a development guard is still guarded",
            "            if stack:\n                stack[-1] = False",
            "            if stack:\n                pass",
            "the else branch of a development guard is NOT guarded",
        ),
        Mutation(
            "a closed guard stays open, so a mount after it is excused",
            "            if stack:\n                stack.pop()",
            "            if stack:\n                pass",
            "AFTER a closed development guard",
        ),
        Mutation(
            "every block counts as a development guard",
            "            stack.append(bool(GUARD_BLOCK.match(s)))",
            "            stack.append(True)",
            "inside an unrelated block is a finding",
        ),
        Mutation(
            "an exemption without a reason is accepted",
            "        if not rule or not reason:",
            "        if not rule:",
            "an exemption without a reason does not clear it",
        ),
        Mutation(
            "an unknown rule is accepted",
            "        elif rule not in RULES:",
            "        elif False:",
            "an unknown rule is a finding",
        ),
        Mutation(
            "an exemption for any rule clears every rule",
            "        if rule in failing and rule not in exempt:",
            "        if rule in failing and not exempt:",
            "an exemption for ANOTHER rule does not clear hosts",
        ),
        Mutation(
            "a stale exemption is never reported",
            "    for rule in sorted(set(exempt) - set(failing)):",
            "    for rule in []:",
            "an exemption for a rule that passes is a stale-exemption finding",
        ),
    ),
)
