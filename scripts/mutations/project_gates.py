"""Mutation guard: project_gates. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="project_gates",
    subject="plugins/rails-flow/scripts/project_gates.py",
    selftest="plugins/rails-flow/scripts/project_gates.py",
    needs=(
        # + `plugins`: its selftest resolves every script each checks.json names, across all three plugins.
        "plugins/rails-flow/checks.json", "plugins/qa-flow/checks.json",
           "plugins/design-flow/checks.json",
        "plugins",
    ),
    mutations=(
        # #849 part 3. A diagnostic never mutates the project -- asserted, not assumed.
        Mutation(
            "a check that writes during the audit is no longer an ERROR",
            "        changed = tree_delta(before, tree_state(project))\n        if changed:",
            "        changed = []\n        if changed:",
            "a check that WRITES during the audit is ERROR",
        ),
        Mutation(
            "the mutation is reported without naming the path that moved",
            '                          f"this check MODIFIED the project during an audit — a diagnostic must never write: "\n'
            '                          f"{\', \'.join(changed[:6])}{\' …\' if len(changed) > 6 else \'\'}",',
            '                          f"this check MODIFIED the project during an audit — a diagnostic must never write",',
            "naming the path it wrote",
        ),

        # #828. Every non-zero exit was FAIL. A check's own n/a (exit 3) and cannot-run (exit 2)
        # verdicts were graded FAIL, counted, and routed to the project's tracker.
        Mutation(
            "a check's exit 3 goes back to being graded FAIL",
            "            if done.returncode == 3:",
            "            if False:",
            "a check that exits 3 is n/a, not FAIL",
        ),
        Mutation(
            "a check's exit 2 goes back to being graded FAIL and routed to the app",
            "            if done.returncode == 2:",
            "            if False:",
            "a check that exits 2 is ERROR, not FAIL",
        ),

        # #812. The aggregate everyone is told to run reported a finding COUNT and dropped the
        # findings -- `[FAIL] mandated-gems  1 finding(s):`, a trailing colon promising a list
        # and nothing after it. The individual scripts carry the finding, the reason AND the fix.
        Mutation(
            "the findings are dropped again, leaving only the count",
            "    rest = [ln for ln in lines[idx + 1:] if ln.strip()]",
            "    rest = []",
            "...and the findings are CARRIED, not dropped",
        ),
        Mutation(
            # Proving `summarise` carries them is not proving `report` prints them: emptying
            # this survived every fixture that only called the helper.
            "report() stops printing the findings",
            '        for detail_line in r.findings:\n            print(f"      {detail_line}")',
            '        for detail_line in ():\n            print(f"      {detail_line}")',
            "report() PRINTS the findings, not only the count",
        ),
        Mutation(
            "as_json() emits no findings key content",
            '                     "findings": list(r.findings),',
            '                     "findings": [],',
            "...carrying every line",
        ),
        Mutation(
            # A check printing hundreds of lines belongs in its own run. The cap is fine; a
            # SILENT cap is this same defect one step along.
            "the cap truncates silently, so a reader cannot tell what was dropped",
            '            f"… {dropped} more line(s) — run the check directly for the rest"]',
            '            ""]',
            "...and the last line names what was dropped",
        ),
        Mutation(
            "the summary is duplicated into the findings",
            "    rest = [ln for ln in lines[idx + 1:] if ln.strip()]",
            "    rest = [ln for ln in lines[idx:] if ln.strip()]",
            "...and the last line names what was dropped",
        ),
        Mutation(
            # `1 finding(s):` in a one-line routing view is the trailing colon in miniature.
            "the routing view goes back to showing the count",
            '    if r.findings and r.detail.rstrip().endswith(":"):',
            "    if False:",
            "the routing view shows the finding, not the count",
        ),
        Mutation(
            "the findings lose their indent, so which check they belong to is lost",
            '            print(f"      {detail_line}")',
            '            print(f"{detail_line}")',
            "...indented under their check, so the association is visible",
        ),
        # #715/#716. Three clauses in the detail line, three mutations -- the ANSI strip, the
        # finding-preference ranking, and the empty-output fallback are independently provable.
        Mutation(
            "ANSI and hyperlink escapes reach the summary line again",
            '    lines = [_ANSI.sub("", ln).rstrip() for ln in output.splitlines()]',
            "    lines = [ln.rstrip() for ln in output.splitlines()]",
            "ANSI escapes are stripped from the detail",
        ),
        Mutation(
            # A banner denylist was the first attempt and `No .herb.yml found` beat it, so the
            # ranking is the part that has to hold.
            "the first line wins again, so a tool's banner masks its finding",
            "    idx = next((i for i, ln in enumerate(lines) if ln.strip() and _FINDING.search(ln)), None)",
            "    idx = None",
            "a banner and a config notice lose to a line naming a severity",
        ),
        Mutation(
            "the summary line loses its length cap, so one long line wrecks the status row",
            '    return lines[idx].strip()[:160], tuple(rest)',
            "    return lines[idx].strip(), tuple(rest)",
            "the detail is capped at 160 chars",
        ),
        Mutation(
            "a failing check with no output reports an empty detail",
            '        return f"exit {returncode}", ()',
            '        return "", ()',
            "empty output falls back to the exit code",
        ),
        # #706. The old walk assumed a flat layout; the installed one nests a version dir, so
        # "siblings" were other versions of the same plugin and real sibling plugins were never
        # found at all. Three mutations, one per clause -- the lesson from the last three days.
        Mutation(
            "candidates stop collapsing by plugin identity, so every cached version runs",
            "    best: dict[str, Path] = {}",
            "    best: dict[str, Path] = {}\n    return sorted(candidates)",
            "one root per plugin, not one per cached version",
        ),
        Mutation(
            "the deeper scan is dropped, so sibling PLUGINS are never discovered",
            "        if peer.is_dir() and peer != own.parent:",
            "        if False:",
            "sibling plugins are discovered",
        ),
        Mutation(
            # The name is a version number in one layout and a plugin name in the other.
            "identity is read from the directory name instead of the manifest",
            '        data = json.loads(manifest.read_text(encoding="utf-8"))',
            "        raise OSError",
            "identity is read from plugin.json",
        ),
        Mutation(
            "the one-level scan is dropped, so a flat source checkout finds only itself",
            "    scan(own.parent)",
            "    pass",
            "a flat source-checkout layout still finds both plugins",
        ),
        Mutation(
            "a not-applicable check is counted as a pass",
            '        return Result(check, NA, why_not)',
            '        return Result(check, PASS, why_not)',
            "an empty glob is n/a, not pass",
        ),
        Mutation(
            "a missing dependency skips instead of failing",
            '            return Result(check, FAIL, f"`{binary}` is not on PATH, so this check could not run")',
            '            return Result(check, NA, f"`{binary}` is not on PATH, so this check could not run")',
            "a missing dependency FAILS rather than skipping",
        ),
        Mutation(
            "the subcommand assertion stops discriminating (the vacuous version)",
            '    found = re.search(r"\\{([a-z,]+)\\}\\s*\\.\\.\\.", usage)',
            '    found = None',
            "a subparser group is detected",
        ),
    ),
)
