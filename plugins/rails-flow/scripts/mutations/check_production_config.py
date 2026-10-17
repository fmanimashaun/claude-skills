"""Mutation guard: check_production_config. Declared here, run by scripts/mutation_check.py (#2120).

The mutations that matter make a rule VACUOUS (a comment, `= nil`, `.clear`, a conditional or a non-literal counts as a
setting; the wrong value or the wrong file order is accepted; a guard that does not guard is trusted), make it fire on the
wrong text (a bare `*`), make the scanner read a string, heredoc or `=begin` block as code (or the reverse), or let an
exemption clear more than the one rule it names.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_production_config",
    subject="scripts/check_production_config.py",
    selftest="scripts/check_production_config.py",
    mutations=(
        Mutation(
            'a quote does not open a string, so a # inside one starts a comment',
            '            if ch in "\\"\'`":\n                stack.append(["str", ch, None, ch != "\'", 0, False])',
            '            if False:\n                stack.append(["str", ch, None, ch != "\'", 0, False])',
            'scan: a # inside a string does not start a comment',
        ),
        Mutation(
            'a regexp literal is not recognised, so a # in one starts a comment',
            '            if top is None and ch == "/" and prev_allows_literal():',
            '            if False:',
            'scan: a regexp holding a # keeps it',
        ),
        Mutation(
            'a %w[] literal is not recognised, so a # in one starts a comment',
            '            if top is None and ch == "%" and prev_allows_literal():',
            '            if False:',
            'scan: %w[] holding a # keeps it',
        ),
        Mutation(
            '=begin/=end blocks are read as code',
            '            if ch == "=" and not cur_c and src.startswith("=begin", i):',
            '            if False:',
            'scan: =begin/=end is removed',
        ),
        Mutation(
            'a heredoc body is read as code',
            '                if hm and prev_allows_literal() or (hm and "".join(cur_m).rstrip()[-1:] in ("=", "(", ",")):',
            '                if False:',
            'scan: a heredoc body is blanked',
        ),
        Mutation(
            'text after __END__ is read as code',
            '            if ch == "_" and not cur_c and src.startswith("__END__", i) and src[i + 7:i + 8] in ("", "\\n", "\\r"):',
            '            if False:',
            'scan: nothing after a line that is exactly __END__ is code',
        ),
        Mutation(
            'an interpolation is not entered, so a nested string ends the outer one early',
            '        if ch == "#" and interp and i + 1 < n and src[i + 1] == "{":',
            '        if False:',
            'scan: a #{} interpolation',
        ),
        Mutation(
            'a logical statement is not continued onto the next line',
            '    return opens > closes or bool(re.search(r"(?:,|\\\\|&&|\\|\\||=)\\s*$", m))',
            '    return False',
            'origins a wrapped list is a finding',
        ),
        Mutation(
            '`;` does not split a line into statements',
            '            if ch == ";":',
            '            if False:',
            '`config.hosts = [] ; x = "#"`',
        ),
        Mutation(
            'a conditional is never conditional',
            '                out.append((n, pc, pm, any(stack) or modifier))',
            '                out.append((n, pc, pm, False))',
            'set only by an `if ENV` block',
        ),
        Mutation(
            'a trailing modifier does not make a statement conditional',
            '                out.append((n, pc, pm, any(stack) or modifier))',
            '                out.append((n, pc, pm, any(stack)))',
            'set only by a trailing `if` modifier',
        ),
        Mutation(
            'an if block does not make its body conditional',
            '            elif re.match(r"(?:if|unless|case|while|until)\\b", pm):\n                stack.append(True)',
            '            elif re.match(r"(?:if|unless|case|while|until)\\b", pm):\n                stack.append(False)',
            'set only by an `if ENV` block',
        ),
        Mutation(
            'a trailing modifier stays in the value, so `= nil if X` is not an emptying',
            '        if cut:',
            '        if False:',
            'a conditional EMPTYING fails closed',
        ),
        Mutation(
            '`.push`, `.concat` and the other append methods are not recognised',
            'APPEND_METHODS = r"(?:push|concat|append|prepend|unshift|insert)"',
            'APPEND_METHODS = r"(?:zzz)"',
            'config.hosts .push( a host is set',
        ),
        Mutation(
            '`+=` is not recognised as an append',
            'r"|\\s*(?P<op><<|\\+=|\\|=|=(?![=~]))\\s*(?P<val>.*))$")',
            'r"|\\s*(?P<op><<|\\|=|=(?![=~]))\\s*(?P<val>.*))$")',
            'config.hosts += a host is set',
        ),
        Mutation(
            'a clear no longer empties hosts',
            '            state, why = False, f"emptied by `.clear` at {at}"',
            '            state, why = state, f"emptied by `.clear` at {at}"',
            'production.rb `.clear` empties them',
        ),
        Mutation(
            'an empty assignment no longer empties hosts',
            '            state, why = False, f"emptied at {at}"',
            '            state, why = state, f"emptied at {at}"',
            'production.rb `= nil` empties them',
        ),
        Mutation(
            'a non-literal value counts as a host',
            '        elif ev["cond"] or cls == "dynamic":',
            '        elif ev["cond"]:',
            'set only by a ternary',
        ),
        Mutation(
            'the files are read in the wrong order, so application.rb overrides production.rb',
            '        sources: list[tuple[Path, str]] = [(APPLICATION, read(root, APPLICATION) or ""), (PRODUCTION, prod)]',
            '        sources: list[tuple[Path, str]] = [(PRODUCTION, prod), (APPLICATION, read(root, APPLICATION) or "")]',
            'production.rb `= nil` empties them',
        ),
        Mutation(
            'a conditional boolean setting counts as made',
            '        if ev["op"] == "assign" and not ev["cond"] and v in ("true", "false"):',
            '        if ev["op"] == "assign" and v in ("true", "false"):',
            'force_ssl = true only under a modifier is a finding',
        ),
        Mutation(
            'a non-literal boolean is read as its own text',
            '            state = "unjudgeable"',
            '            state = v',
            'consider_all_requests_local = (true) is unjudgeable',
        ),
        Mutation(
            'an unjudgeable consider_all_requests_local is not a finding',
            '    if local in ("true", "unjudgeable"):',
            '    if local == "true":',
            'consider_all_requests_local = (true) is unjudgeable',
        ),
        Mutation(
            'force_ssl = false is accepted as long as it is set',
            '    if ssl != "true":',
            '    if ssl is None:',
            'force_ssl = false is a finding',
        ),
        Mutation(
            'a quoted * is not a wildcard',
            '    if re.search(r"[\\"\']\\*[\\"\']", code):\n        return True',
            '    if re.search(r"[\\"\']\\*[\\"\']", code):\n        return False',
            'origins "*" is a finding',
        ),
        Mutation(
            "any * counts as a wildcard origin (the article's bare grep)",
            '    if re.search(r"[\\"\']\\*[\\"\']", code):\n        return True',
            '    if "*" in code:\n        return True',
            'CONTROL: a subdomain pattern',
        ),
        Mutation(
            '%w[*] is not a wildcard',
            '        if "*" in lm.group(1).split():',
            '        if False:',
            'origins %w[*] is a finding',
        ),
        Mutation(
            '/.+/ is not a wildcard',
            '    return bool(re.search(r"/(?:\\\\A)?\\.[*+](?:\\\\z)?/|%r[{(\\[]\\.[*+][})\\]]", code))',
            '    return bool(re.search(r"/(?:\\\\A)?\\.[*](?:\\\\z)?/", code))',
            'origins /.+/ is a finding',
        ),
        Mutation(
            'a constant bound to * is not followed',
            '            if am and has_wildcard(c[am.start(2):am.end(2)]):',
            '            if False:',
            'a constant bound to',
        ),
        Mutation(
            'an origins block returning true is not a wildcard',
            '            elif re.match(r"^origins\\s*(?:\\(\\s*\\))?\\s*\\{\\s*(?:\\|[^|]*\\|)?\\s*true\\s*\\}\\s*$", m):',
            '            elif False:',
            'an origins block returning true is a finding',
        ),
        Mutation(
            'a multi-line origins block returning true is not a wildcard',
            '            if [b for b in body if not re.fullmatch(r"\\|[^|]*\\|", b)] == ["true"]:',
            '            if False:',
            'a multi-line origins block',
        ),
        Mutation(
            'application.rb is not read for CORS',
            '    cors = [loc for rel, src in sources for loc in wildcard_origins(rel, src, names)]',
            '    cors = [loc for rel, src in sources[1:] for loc in wildcard_origins(rel, src, names)]',
            'a wildcard in application.rb',
        ),
        Mutation(
            'an admin dashboard is never flagged',
            '        elif ADMIN_MOUNT.search(code) and not dev and not access:',
            '        elif False:',
            'an unguarded `mount Sidekiq::Web` is a finding',
        ),
        Mutation(
            'an access constraint is not recognised',
            '        access = any(f[1] for f in stack) or bool(re.search(r"\\bconstraints\\s*:|\\bconstraints\\s*=>", s))',
            '        access = False',
            'CONTROL: a dashboard inside `constraints',
        ),
        Mutation(
            'a constraint excuses a dev-only engine too',
            '        if DEBUG_ROUTE.search(code) and not dev:',
            '        if DEBUG_ROUTE.search(code) and not dev and not access:',
            'a constraint is not a development guard',
        ),
        Mutation(
            'a closed guard stays open, so a mount after it is excused',
            '        if re.match(r"^end\\b", s):\n            if stack:\n                stack.pop()',
            '        if re.match(r"^end\\b", s):\n            if stack:\n                pass',
            'AFTER a closed development guard',
        ),
        Mutation(
            'the else branch of a development guard is still guarded',
            '            if stack:\n                stack[-1][0] = False',
            '            if stack:\n                pass',
            'the else branch of a development guard is NOT guarded',
        ),
        Mutation(
            'every block counts as a development guard',
            '            stack.append([bool(GUARD_BLOCK.match(s)), bool(ACCESS_BLOCK.match(s))])',
            '            stack.append([True, False])',
            'inside an unrelated block is a finding',
        ),
        Mutation(
            'an exemption without a reason is accepted',
            '        if not rule or not reason:',
            '        if not rule:',
            'an exemption without a reason does not clear it',
        ),
        Mutation(
            'an unknown rule is accepted',
            '        elif rule not in RULES:',
            '        elif False:',
            'an unknown rule is a finding',
        ),
        Mutation(
            'an exemption for any rule clears every rule',
            '        if rule in failing and rule not in exempt:',
            '        if rule in failing and not exempt:',
            'an exemption for ANOTHER rule does not clear hosts',
        ),
        Mutation(
            'a stale exemption is never reported',
            '    for rule in sorted(set(exempt) - set(failing)):',
            '    for rule in []:',
            'an exemption for a rule that passes is a stale-exemption finding',
        ),
    ),
)
