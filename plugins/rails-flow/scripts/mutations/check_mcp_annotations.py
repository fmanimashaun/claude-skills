"""Mutation guard: check_mcp_annotations. Declared here, run by scripts/mutation_check.py (#1882).

The mutations that matter make the gate VACUOUS: a tool with no annotations passed, one hint accepted for both, a
base class judged (or an inherited class skipped), or a non-literal `annotations(CONST)` read as clean.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_mcp_annotations",
    subject="scripts/check_mcp_annotations.py",
    selftest="scripts/check_mcp_annotations.py",
    mutations=(
        Mutation(
            "a tool with no annotations passes",
            '        return "declares no annotations, so a client reads it as destructive and open-world"',
            '        return ""',
            "no annotations at all is a finding",
        ),
        Mutation(
            "one hint stands for both",
            "    missing = [k for k in REQUIRED if k not in _keys(args)]",
            "    missing = [k for k in REQUIRED if not _keys(args)]",
            "only read_only_hint set misses open_world_hint",
        ),
        Mutation(
            "a non-literal annotations argument reads as clean",
            "    if not re.search(r\"\\w+\\s*:|=>\", args):\n        return f\"annotations are not a literal hash",
            "    if False:\n        return f\"annotations are not a literal hash",
            "a constant argument cannot be read and fails",
        ),
        Mutation(
            "a subclass of an application base is never judged",
            "            if n not in tools and any(b.split(\"::\")[-1] in tools for b in bs):",
            "            if n not in tools and False:",
            "a subclass of an application base is judged, the base is not",
        ),
        Mutation(
            "an abstract base is judged as a tool",
            "m[\"name\"].split(\"::\")[-1] not in bases:",
            "True:",
            "a subclass that states its own is clean",
        ),
        Mutation(
            "Sub.define on a tool subclass is never scanned",
            '            if m["recv"] and not _is_tool(m["recv"], tools):\n                continue',
            '            if m["recv"]:\n                continue',
            "Sub.define on a tool subclass without annotations is a finding",
        ),
        Mutation(
            "Class.new(MCP::Tool) is not scanned",
            "        for m in CLASS_NEW.finditer(text):",
            "        for m in ():",
            "Class.new(MCP::Tool) block without annotations is a finding",
        ),
        Mutation(
            "a non-literal tools: list reads as clean",
            '            if t and t[1] != "[":',
            "            if False:",
            "tools: with a constant could not be checked",
        ),
        Mutation(
            "server.tools = / << is never noticed",
            "        for m in TOOLS_MUTATED.finditer(text):",
            "        for m in ():",
            "server.tools = could not be checked",
        ),
        Mutation(
            "a place that could not be checked still exits 0",
            '    if unchecked:\n        print(f"mcp-annotations: {found} tool(s) read clean',
            '    if False:\n        print(f"mcp-annotations: {found} tool(s) read clean',
            "an unchecked tool list exits 2, not 0",
        ),
        Mutation(
            "unchecked with no tool found is reported not applicable",
            "    if unchecked:\n",
            "    if unchecked and found:\n",
            "an unchecked tool list with no tool found exits 2, not 3",
        ),
        Mutation(  # #1873: the n/a row reaches its site
            "a project with no MCP tool is a pass instead of not applicable",
            '(no MCP tool in app/ or lib/)")\n        return 3',
            '(no MCP tool in app/ or lib/)")\n        return 0',
            "no MCP tool in app/ or lib/ is not applicable (exit 3, n/a)",
        ),
        Mutation(
            "whole-line comments are scanned as code",
            '        lines = ["" if ln.lstrip().startswith("#") else ln for ln in text.split("\\n")]',
            '        lines = text.split("\\n")',
            "a commented-out server.tools = is not a mutation",
        ),
        Mutation(
            "a base that defines call is exempted as abstract",
            "for b in classes[n]} - served",
            "for b in classes[n]}",
            "a base that defines call is a served tool, and judged",
        ),
        Mutation(
            "a later declaration of a name overwrites an earlier one",
            "                classes.setdefault(name, set()).add(m[\"base\"])",
            "                classes[name] = {m[\"base\"]}",
            "a name declared in two places still passes its tool-ness to a subclass",
        ),
        Mutation(
            "a declaration is judged by its name, not its own base",
            '        if m and _is_tool(m["base"], tools) and m["name"].split("::")[-1] not in bases:',
            '        if m and m["name"].split("::")[-1] in tools and m["name"].split("::")[-1] not in bases:',
            "a name declared in two places is judged per declaration",
        ),
        Mutation(
            "server.tools[name] = is never noticed",
            "|\\[[^\\]]*\\]\\s*(?:\\|\\||&&)?=(?![=~>])",
            "",
            "server.tools[name] = could not be checked",
        ),
        Mutation(
            "server.tools.merge! is never noticed",
            "\\.(?:merge!|(?:store|update|replace)\\b))",
            "\\.(?:(?:store|update|replace)\\b))",
            "server.tools.merge! could not be checked",
        ),
        Mutation(
            "server.tools.store is never noticed",
            "(?:store|update|replace)\\b",
            "(?:update|replace)\\b",
            "server.tools.store could not be checked",
        ),
        Mutation(
            "server.tools.update is never noticed",
            "(?:store|update|replace)\\b",
            "(?:store|replace)\\b",
            "server.tools.update could not be checked",
        ),
        Mutation(
            "server.tools.replace is never noticed",
            "(?:store|update|replace)\\b",
            "(?:store|update)\\b",
            "server.tools.replace could not be checked",
        ),
        Mutation(
            "server.tools[name] ||= is never noticed",
            "(?:\\|\\||&&)?=(?![=~>])",
            "(?:&&)?=(?![=~>])",
            "server.tools[name] ||= could not be checked",
        ),
        Mutation(
            "server.tools[name] &&= is never noticed",
            "(?:\\|\\||&&)?=(?![=~>])",
            "(?:\\|\\|)?=(?![=~>])",
            "server.tools[name] &&= could not be checked",
        ),
        Mutation(
            "a .rake file is not read",
            'name.endswith((".rake", ".ru"))',
            'name.endswith((".ru",))',
            "a .rake task naming MCP could not be checked",
        ),
        Mutation(
            "a .ru file is not read",
            'name.endswith((".rake", ".ru"))',
            'name.endswith((".rake",))',
            "config.ru naming MCP could not be checked",
        ),
        Mutation(
            "a ruby shebang is not looked for",
            'return line.startswith(b"#!") and b"ruby" in line',
            "return False",
            "an entry script in bin/ could not be checked",
        ),
        Mutation(
            "any shebang is read as Ruby",
            'return line.startswith(b"#!") and b"ruby" in line',
            'return line.startswith(b"#!")',
            "an extensionless file that is not Ruby is not read",
        ),
        Mutation(
            ".rb files under app/ and lib/ are scanned a second time as outside",
            "                if top in SCAN_DIRS:\n                    continue",
            "                if False:\n                    continue",
            "explicit class macro is clean",
        ),
        Mutation(
            "MCP code outside app/ and lib/ is never looked for",
            "    unchecked.extend(_outside(root))",
            "    pass",
            "MCP code in config/ could not be checked",
        ),
        Mutation(
            "spec/ is read as application code",
            '"log", "spec", "test",',
            '"log", "test",',
            "MCP code in spec/ is not read",
        ),
        Mutation(
            "a comment naming MCP outside app/ counts",
            '            code = "\\n".join("" if ln.lstrip().startswith("#") else ln for ln in text.split("\\n"))',
            "            code = text",
            "a comment naming MCP outside app/ is not MCP code",
        ),
        Mutation(
            "a hint named inside a string counts",
            "    scope = _blank_strings(scope)",
            "    scope = scope",
            "a hint named inside a string is not a hint",
        ),
        Mutation(
            "annotations anywhere in a body counts, not only a statement",
            'BODY_DECL = re.compile(r"(?m)(?:^|[{;])[ \\t]*annotations',
            'BODY_DECL = re.compile(r"(?m)annotations',
            "annotations on another receiver is not this tool's declaration",
        ),
        Mutation(
            "a one-line class is not recognised as one line",
            '    if re.search(r";\\s*end\\s*$", lines[i]):',
            "    if False:",
            "a one-line class does not borrow the next class's annotations",
        ),
        Mutation(
            "a class body ends only at a bare end",
            'stop = re.compile(rf"^{indent}end\\b")',
            'stop = re.compile(rf"^{indent}end$")',
            "an end with a trailing comment closes the class",
        ),
        Mutation(
            "paren-less annotations are not read",
            "(?:\\s*(?P<open>\\()|(?=[ \\t]+\\w+[ \\t]*:)(?P<bare>))",
            "(?:\\s*(?P<open>\\())",
            "paren-less annotations are read",
        ),
        Mutation(
            "a paren-less statement stops at its first line",
            '        n = next((k for k, r in enumerate(rows) if not r.rstrip().endswith(",")), len(rows) - 1)',
            "        n = 0",
            "paren-less annotations continue over lines ending in a comma",
        ),
        Mutation(
            "Tool.define is not scanned",
            "        for m in CALL.finditer(text):",
            "        for m in ():",
            "Tool.define without annotations is a finding",
        ),
    ),
)
