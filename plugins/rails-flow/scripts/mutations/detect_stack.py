"""Mutation guard: detect_stack. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #2163. The detector is what every flow and the toolchain audit act on, so a stack it reports
    # wrongly, or a manifest it skips in silence, sends a whole run down the wrong stack's path.
    name="detect_stack",
    subject="scripts/detect_stack.py",
    selftest="scripts/detect_stack.py",
    mutations=(
        Mutation(
            "one marker of a stack's `all` list is enough, so a Gemfile alone reads as Rails",
            "                if all(holds(m, project, deps) for m in all_of) and",
            "                if any(holds(m, project, deps) for m in all_of) and",
            "every `all` marker must hold",
        ),
        Mutation(
            "devDependencies are not read, so a Next.js app declared there is missed",
            '    for key in ("dependencies", "devDependencies"):',
            '    for key in ("dependencies",):',
            "a next devDependency is Next.js too",
        ),
        Mutation(
            "an unknown marker kind reads as absent, so a stack that cannot be judged looks missing",
            "        raise ValueError(f\"unknown marker {marker!r} (kinds: {', '.join(KINDS)})\")",
            "        return False",
            "an unknown marker kind is a problem",
        ),
        Mutation(
            "a stack with no markers is accepted, so it matches every project",
            "            if not all_of and not any_of:",
            "            if False:",
            "a stack with no markers is a problem",
        ),
        Mutation(
            "the repo root is not looked at, so rails-stack's manifest is never found in a checkout",
            "    take(grandparent)",
            "    pass",
            "discovery finds the repo root",
        ),
        Mutation(
            "two cached versions do not collapse to the higher, so an old manifest can win",
            "        if plugin not in best or best[plugin][0] < version:",
            "        if plugin not in best:",
            "collapse to the higher one",
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
    ),
)
