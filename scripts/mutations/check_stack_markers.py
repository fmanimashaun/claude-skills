"""Mutation guard: check_stack_markers. Declared here, run by scripts/mutation_check.py.

The SUBJECT is the shipped manifest, not the script: the defect this guard exists for is a well-formed typo in
`plugins/nextjs-stack/stacks.json` (e6 changed `next` to `nxt` on #2198 and every other check stayed green), so each
mutant is a plausible drift of that file and names the hand-written fixture that must notice it.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_stack_markers",
    subject="plugins/nextjs-stack/stacks.json",
    selftest="scripts/check_stack_markers.py",
    # The detector reads a directory as a plugin only beside its `.claude-plugin/plugin.json`, so both manifests are staged
    # (without them the unmutated selftest fails in the tempdir and every mutant reads as caught: INERT).
    needs=("plugins/rails-flow/scripts/detect_stack.py", "plugins/rails-flow/.claude-plugin/plugin.json",
           "plugins/nextjs-stack/.claude-plugin/plugin.json",
           # the descriptor names its security checklists and cases (#2210); --check refuses a missing one, so stage them too (#2168)
           "plugins/nextjs-stack/security/nextjs.md", "plugins/nextjs-stack/security/nextjs-cases.json",
           "plugins/nextjs-stack/security/supabase.md", "plugins/nextjs-stack/security/supabase-cases.json"),
    deps=(),
    mutations=(
        Mutation(
            # The reviewer's own mutant: still a valid marker, matches no Next.js project.
            "the Next.js dependency is misspelled",
            '{"package_dependency": "next"}',
            '{"package_dependency": "nxt"}',
            "a Next.js app (next in dependencies) is Next.js",
        ),
        Mutation(
            # A path drift: the file Supabase's CLI writes is supabase/config.toml.
            "the Supabase marker names the wrong file",
            '{"file": "supabase/config.toml"}',
            '{"file": "supabase/config.json"}',
            "a linked Supabase project (supabase/config.toml) is Supabase",
        ),
        Mutation(
            # Widening: a bare `supabase/` directory would claim every repo with migrations in it.
            "the Supabase marker is widened to any supabase/ directory",
            '{"file": "supabase/config.toml"}',
            '{"dir": "supabase"}',
            "NEAR MISS: a supabase/ directory with no config.toml is not Supabase",
        ),
        Mutation(
            # Dropping one of Vercel's two markers: a project linked with `vercel link` has only `.vercel/`.
            "Vercel loses its .vercel/ marker",
            '"any": [{"file": "vercel.json"}, {"dir": ".vercel"}]',
            '"any": [{"file": "vercel.json"}]',
            "a .vercel/ directory (vercel link) is Vercel",
        ),
    ),
)
