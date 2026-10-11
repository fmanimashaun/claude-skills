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
        Mutation(
            "a commented-out annotations call counts as a declaration",
            '        lines = ["" if ln.lstrip().startswith("#") else ln for ln in text.split("\\n")]',
            '        lines = text.split("\\n")',
            "a commented-out annotations call is not a declaration",
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
            '            if m and _is_tool(m["base"], tools) and m["name"].split("::")[-1] not in bases:',
            '            if m and m["name"].split("::")[-1] in tools and m["name"].split("::")[-1] not in bases:',
            "a name declared in two places is judged per declaration",
        ),
        Mutation(
            "Tool.define is not scanned",
            "        for m in CALL.finditer(text):",
            "        for m in ():",
            "Tool.define without annotations is a finding",
        ),
    ),
)
