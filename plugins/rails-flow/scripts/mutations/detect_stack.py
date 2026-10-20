"""Mutation guard: detect_stack. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #2163. The detector is what every flow and the toolchain audit act on, so a stack it reports
    # wrongly, or a manifest it cannot judge read as "no stack", sends a whole run down the wrong path.
    name="detect_stack",
    subject="scripts/detect_stack.py",
    selftest="scripts/detect_stack.py",
    mutations=(
        Mutation(
            "one marker of a stack's `all` list is enough, so a Gemfile alone reads as Rails",
            "            if all(every) and (not any_of or any(some)):",
            "            if any(every) and (not any_of or any(some)):",
            "every `all` marker must hold",
        ),
        Mutation(
            "an `any` list is not read, so a stack none of whose alternatives holds still matches",
            "            if all(every) and (not any_of or any(some)):",
            "            if all(every):",
            "a stack whose `any` list holds nothing is not matched",
        ),
        Mutation(
            "a `dir` marker never holds, so a project known by a directory is missed",
            '    return (project / value).is_file() if kind == "file" else (project / value).is_dir()',
            '    return (project / value).is_file() if kind == "file" else False',
            "a `dir` marker",
        ),
        Mutation(
            "devDependencies are not read, so a Next.js app declared there is missed",
            '    for key in ("dependencies", "devDependencies"):',
            '    for key in ("dependencies",):',
            "a next devDependency is Next.js too",
        ),
        Mutation(
            "a package.json that does not parse reads as no dependency, so 'cannot judge' becomes 'no stack'",
            '            raise ValueError("package.json exists but does not parse, so its dependencies cannot be read")',
            "            return False",
            "a package.json that does not parse is a problem",
        ),
        Mutation(
            "an unknown marker kind reads as absent, so a stack that cannot be judged looks missing",
            "        raise ValueError(f\"unknown marker {marker!r} (kinds: {', '.join(KINDS)})\")",
            "        return False",
            "an unknown marker kind is a problem",
        ),
        Mutation(
            "a marker path is not contained, so `/etc/hosts` is judged on the host",
            '    if parts.is_absolute() or ".." in parts.parts or value.startswith("\\\\") or (parts.parts and ":" in parts.parts[0]):',
            "    if False:",
            "an absolute marker path is a problem",
        ),
        Mutation(
            "a stack with no markers is accepted, so it matches every project",
            "            if not all_of and not any_of:",
            "            if False:",
            "a stack with no markers is a problem",
        ),
        Mutation(
            "an unreadable manifest is skipped in silence",
            '            problems.append(f"{path}: unreadable manifest ({exc})")',
            "            pass",
            "an unreadable manifest is a problem",
        ),
        Mutation(
            "a manifest naming no plugin is skipped in silence",
            '            problems.append(f"{path}: names no `plugin`")',
            "            pass",
            "a manifest that names no plugin is a problem",
        ),
        Mutation(
            "two manifests for one plugin at one version: the first wins in silence",
            "        if plugin in best and best[plugin][0] == version:",
            "        if False:",
            "at the same version are a problem",
        ),
        Mutation(
            "two cached versions do not collapse to the higher, so an old manifest can win",
            "        if plugin not in best or best[plugin][0] < version:",
            "        if plugin not in best:",
            "collapse to the higher one",
        ),
        Mutation(
            "a problem no longer forces exit 2, so 'cannot judge' exits as a detection or as 'none'",
            "    if problems:\n        return 2, report",
            "    if False:\n        return 2, report",
            "(exit 2)",
        ),
        Mutation(
            "no stack detected exits 0, so a caller cannot tell 'none' from a detection",
            "    return (0 if matched else 1), report",
            "    return 0, report",
            "an empty project matches nothing and says so (exit 1)",
        ),
        Mutation(
            "a stack's declared name is dropped for its id",
            '                matched.append({"id": stack.get("id"), "name": stack.get("name", stack.get("id")), "plugin": manifest["plugin"]})',
            '                matched.append({"id": stack.get("id"), "name": stack.get("id"), "plugin": manifest["plugin"]})',
            "carries its declared name",
        ),
        Mutation(
            "--json prints the text summary, so a caller parsing JSON breaks",
            "    print(json.dumps(report, indent=2) if args.json else render(code, report))",
            "    print(render(code, report))",
            "--json prints the report",
        ),
        Mutation(
            "any directory's stacks.json is read, so a stray docs/notes/stacks.json becomes a plugin",
            "        if (directory / MANIFEST).is_file() and is_plugin_root(directory):",
            "        if (directory / MANIFEST).is_file():",
            "discovery reads plugin roots only",
        ),
        Mutation(
            "the repo root is not looked at, so rails-stack's manifest is never found in a checkout",
            "    take(grandparent)",
            "    pass",
            "discovery reads plugin roots only",
        ),
        Mutation(
            "the installed cache is not scanned, so no stack plugin is found where the toolchain runs",
            "            scan(peer)                        # every plugin's every version in the cache",
            "            pass",
            "discovery finds a stack plugin in the installed cache",
        ),
        Mutation(
            "a descriptor key two plugins declare is merged silently, so one stack's test command overwrites another's",
            '            if key in owner and owner[key] != found["plugin"]:',
            "            if False:",
            "declared by two plugins is a conflict",
        ),
        Mutation(
            "one plugin giving a leaf two values keeps the first in silence",
            "            elif key in into and into[key] != item:",
            "            elif False:",
            "one plugin giving a leaf two values is a conflict",
        ),
        Mutation(
            "three stacks of one plugin do not merge, so Supabase's migrations replace Next.js' source",
            "                merge(into[key], item, label, here)",
            "                into[key] = item",
            "three stacks from one plugin merge",
        ),
        Mutation(
            "an undeclared descriptor key is accepted, so a flow can read a key nobody declared",
            '            found.append(f"{where}.{key} is not a declared descriptor key (descriptor-key-undeclared)")',
            "            pass",
            "an undeclared descriptor key is a problem",
        ),
        Mutation(
            "a port given as text passes, so a flow boots on a string",
            '        return [] if isinstance(value, int) and not isinstance(value, bool) else [f"{where} must be a whole number"]',
            "        return []",
            "a descriptor value of the wrong type is a problem",
        ),
        Mutation(
            "descriptors are never validated on a detection run",
            "        problems += descriptor_problems(manifest)\n    matched, more = detect(project, manifests)",
            "        pass\n    matched, more = detect(project, manifests)",
            "an undeclared key inside a block is a problem",
        ),
        Mutation(
            "a marker naming the project root is accepted, so a stack keyed on `.` matches every project",
            '    if value.strip().rstrip("/") in ("", "."):',
            "    if False:",
            "naming the project root (.) is a problem",
        ),
        Mutation(
            "a stack with no usable id is reported as None",
            '            if not isinstance(stack.get("id"), str) or not stack.get("id"):',
            "            if False:",
            "a stack with no id is a problem",
        ),
        Mutation(
            "a package.json that is valid JSON but not an object reads as no dependency",
            "    if not isinstance(data, dict):\n        return CORRUPT",
            "    if False:\n        return CORRUPT",
            "valid JSON but not an object is a problem",
        ),
    ),
)
