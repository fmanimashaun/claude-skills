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
            'Vercel steps are not recognised',
            '(?:npx\\s+)?(?:supabase|vercel)\\s+"',
            '(?:npx\\s+)?(?:supabase)\\s+"',
            'a copied vendor step is refused: vercel env pull .env.local',
        ),
        Mutation(
            '`supabase db` is not a vendor step',
            '|db|migration|',
            '|migration|',
            'a copied vendor step is refused: npx supabase db diff',
        ),
        Mutation(
            'the lookbehind goes: any text ending in the brand is a step',
            '(?<![\\w/.-])',
            '',
            'CONTROL: a mention that is no step is not a how-to: mysupabase start',
        ),
        Mutation(
            'a hand-off needs no marker',
            '    return MARKER in line and TARGET.search(line) is not None',
            '    return TARGET.search(line) is not None',
            'a marker with no vendor target, or a lower-case marker, excuses nothing',
        ),
        Mutation(
            'a hand-off names no vendor target',
            '    return MARKER in line and TARGET.search(line) is not None',
            '    return MARKER in line',
            'a marker with no vendor target, or a lower-case marker, excuses nothing: Hand-off: run supabase start yourself.',
        ),
        Mutation(
            'a hand-off anywhere in the file excuses every step',
            '        if match and not is_handoff(line):',
            '        if match and not is_handoff(text):',
            'a hand-off elsewhere in the file excuses nothing',
        ),
        Mutation(
            'a hand-off line excuses nothing, even the command it hands off',
            '        if match and not is_handoff(line):',
            '        if match:',
            'a hand-off line may carry the command it hands off',
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
            'the finding loses its line number',
            'out.append(f"{rel}:{number}: a vendor how-to',
            'out.append(f"{rel}:0: a vendor how-to',
            'the finding names the file and the line',
        ),
    ),
)
