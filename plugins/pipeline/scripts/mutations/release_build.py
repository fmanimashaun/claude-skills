"""Mutation guard: release_build. Declared here, run by scripts/mutation_check.py (#1701)."""
from mutation_types import Guard, Mutation  # noqa: F401

# The build is a command line, and each way it goes wrong is quiet: a declared arg or label that never reaches
# `docker build` (the image lacks its version, the Kamal service label), a default command that is no longer the old
# one, an unknown `{{variable}}` that reaches an image label as text, a value evaluated by a shell, a warning that
# names Docker's own args or ignores an inherited default, a bad config that builds anyway.
GUARD = Guard(
    name="release_build",
    subject="scripts/release_build.py",
    selftest="scripts/release_build.py",
    mutations=(
        Mutation(
            "a declared label never reaches docker build",
            '        argv += ["--label", f"{key}={value}"]',
            "        pass",
            "args and labels are passed",
        ),
        Mutation(
            "a declared build arg never reaches docker build",
            '        argv += ["--build-arg", f"{name}={value}"]',
            "        pass",
            "args and labels are passed",
        ),
        Mutation(
            "the default command is no longer the old one (the latest tag is dropped)",
            'argv += ["-t", f"{image}:{sha}", "-t", f"{image}:latest", context]',
            'argv += ["-t", f"{image}:{sha}", context]',
            "no keys is the bare command",
        ),
        Mutation(
            "an unknown variable is left in the value instead of refused",
            "        if name not in variables:",
            "        if False:",
            "",
        ),
        Mutation(
            "Docker's own predefined args are named as unfed",
            "if n not in fed and n.lower() not in PREDEFINED]",
            "if n not in fed]",
            "predefined args are never named",
        ),
        Mutation(
            "a default declared in another stage no longer counts",
            "            if has:\n                with_default.add(name)",
            "            if has:\n                pass",
            "a name with a default anywhere is not unfed",
        ),
        Mutation(
            "the release name ignores $RELEASE_NAME",
            'name = release_name or os.environ.get("RELEASE_NAME") or sha',
            "name = release_name or sha",
            "RELEASE_NAME beats the sha",
        ),
        Mutation(
            "the command goes through a shell",
            "    return runner(argv).returncode",
            '    return runner(" ".join(argv), shell=True).returncode',
            "",
        ),
        Mutation(
            "a bad config exits 0 instead of 2",
            '        out(f"release build: {error}")\n        return 2',
            '        out(f"release build: {error}")\n        return 0',
            "a bad config is exit 2 and builds nothing",
        ),
    ),
)
