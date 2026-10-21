"""Mutation guard: check_vendor_handoff (#2289). Declared here, run by scripts/mutation_check.py.

Each mutation lets a copied Vercel or Supabase step through, or refuses a hand-off line or a mention that is no step.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_vendor_handoff",
    subject="scripts/check_vendor_handoff.py",
    selftest="scripts/check_vendor_handoff.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            '`supabase db` is not a vendor step',
            '|db|migration|',
            '|migration|',
            'a copied vendor step is refused: npx supabase db diff',
        ),
        Mutation(
            'a hand-off names no vendor target',
            '    return MARKER in line and TARGET.search(line) is not None',
            '    return MARKER in line',
            'names no vendor target points nowhere: Hand-off: see the Supabase docs.',
        ),
        Mutation(
            'only skills/ is shipped',
            'SHIPPED = ("plugins/", "skills/")',
            'SHIPPED = ("skills/",)',
            'a scan finds the plugin file and the skills/ file',
        ),
        Mutation(
            'any file under plugins/ or skills/ is a doc',
            '    return [p for p in paths if p.endswith(".md") and p.startswith(SHIPPED)]',
            '    return [p for p in paths if p.startswith(SHIPPED)]',
            'only shipped .md under plugins/ and skills/ is examined',
        ),
        Mutation(
            'a named file must also be shipped',
            'only_shipped=not argv)',
            'only_shipped=True)',
            'main() on a named file that carries a copied step exits 1 and names it',
        ),
        Mutation(
            'a finding does not fail the run',
            '    return 1 if findings else 0\n\n\n# ---',
            '    return 0\n\n\n# ---',
            'main() on a named file that carries a copied step exits 1 and names it',
        ),
        Mutation(
            'Vercel steps are not recognised',
            '(?:(?:supabase|vercel)\\s+(?:start|',
            '(?:(?:supabase)\\s+(?:start|',
            'a copied vendor step is refused: vercel env pull .env.local',
        ),
        Mutation(
            'the lookbehind goes: any text ending in the brand is a step',
            'STEP = re.compile(r"(?<![\\w/.-])(?:npx',
            'STEP = re.compile(r"(?:npx',
            'CONTROL: a mention that is no step is not a how-to: mysupabase start',
        ),
        Mutation(
            '`redeploy` is not a step',
            'deploy|redeploy|db|',
            'deploy|db|',
            'S1: a step the first detector missed is refused: vercel redeploy dpl_123',
        ),
        Mutation(
            '`vercel ls` is not a step',
            'whoami|ls|list|alias|rm|"',
            'whoami|list|alias|rm|"',
            'S1: a step the first detector missed is refused: vercel ls',
        ),
        Mutation(
            '`vercel alias` is not a step',
            'whoami|ls|list|alias|rm|"',
            'whoami|ls|list|rm|"',
            'S1: a step the first detector missed is refused: vercel alias set a.vercel.app b.com',
        ),
        Mutation(
            '`supabase inspect` is not a step',
            'branches|inspect|whoami',
            'branches|whoami',
            'S1: a step the first detector missed is refused: supabase inspect db bloat',
        ),
        Mutation(
            '`supabase seed` is not a step',
            'r"seed|test)\\b|vercel',
            'r"test)\\b|vercel',
            'S1: a step the first detector missed is refused: supabase seed buckets',
        ),
        Mutation(
            '`supabase test` is not a step',
            'r"seed|test)\\b|vercel',
            'r"seed)\\b|vercel',
            'S1: a step the first detector missed is refused: supabase test db',
        ),
        Mutation(
            'a flag after vercel is not a step',
            '\\b|vercel\\s+-{1,2}[a-z])")',
            '\\b)")',
            'S1: a step the first detector missed is refused: vercel --prod',
        ),
        Mutation(
            'only `run` makes a bare vercel a step',
            '(?i:run|execute|type|invoke)',
            '(?i:run)',
            'S1: a step the first detector missed is refused: To ship it, execute `npx vercel`.',
        ),
        Mutation(
            'a bare vercel in a table cell is no step',
            're.compile(r"\\|\\s*`?(?:npx\\s+)?vercel`?\\s*\\|"),',
            're.compile(r"\\|\\s*NEVER\\s*\\|"),',
            'S1: a step the first detector missed is refused: | Deploy | `vercel` |',
        ),
        Mutation(
            'a bare vercel alone on a line is no step',
            're.compile(r"^\\s*(?:\\$\\s*)?(?:npx\\s+)?vercel\\s*$"))',
            're.compile(r"^NEVER$"))',
            'S1: a step the first detector missed is refused: $ vercel',
        ),
        Mutation(
            'a hand-off line may carry a command',
            '        if step:\n',
            '        if step and not is_handoff(line):\n',
            'S2: a hand-off line that ALSO carries a command is refused',
        ),
        Mutation(
            'a hand-off anywhere in the file excuses every step',
            '        if step:\n',
            '        if step and not is_handoff(text):\n',
            'a hand-off elsewhere in the file excuses nothing',
        ),
        Mutation(
            'a hand-off marker about Vercel or Supabase needs no target',
            '        elif MARKER in line and VENDOR.search(line) and not is_handoff(line):',
            '        elif False:',
            'names no vendor target points nowhere',
        ),
        Mutation(
            'the finding loses its line number',
            'out.append(f"{rel}:{number}: {why}',
            'out.append(f"{rel}:0: {why}',
            'the finding names the file and the line',
        ),
    ),
)
