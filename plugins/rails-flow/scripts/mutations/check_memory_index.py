"""Mutation guard: check_memory_index. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1828. The auto-memory index limit check. Each mutation breaks ONE boundary, rule or exit code, and the check's own selftest must notice it.
GUARD = Guard(
    name='check_memory_index',
    subject='scripts/check_memory_index.py',
    selftest='scripts/check_memory_index.py',
    mutations=(
        Mutation('the line limit is 201', 'MAX_LINES = 200', 'MAX_LINES = 201', '201 lines is over'),
        Mutation('the byte limit is 25,000', 'MAX_BYTES = 25 * 1024', 'MAX_BYTES = 25_000', '25,600 bytes is still loaded whole'),
        Mutation('the line warning is at 161', 'WARN_LINES = 160', 'WARN_LINES = 161', '160 lines is a warning'),
        Mutation('the byte warning is at 20,481', 'WARN_BYTES = 20_480', 'WARN_BYTES = 20_481', '20,480 bytes is a warning'),
        Mutation('a file of exactly 200 lines is over', 'if m["lines"] > MAX_LINES or m["bytes"] > MAX_BYTES:', 'if m["lines"] >= MAX_LINES or m["bytes"] > MAX_BYTES:', '200 lines is still loaded whole'),
        Mutation('a file of exactly 25,600 bytes is over', 'if m["lines"] > MAX_LINES or m["bytes"] > MAX_BYTES:', 'if m["lines"] > MAX_LINES or m["bytes"] >= MAX_BYTES:', '25,600 bytes is still loaded whole'),
        Mutation('the other reading of 25KB is not mentioned', '    if STRICT_BYTES < m["bytes"] <= MAX_BYTES:', '    if False:', 'between the two readings'),
        Mutation('the byte cut is not counted', '        if kept >= MAX_LINES or used + len(line) > MAX_BYTES:', '        if kept >= MAX_LINES:', 'a byte-bound index counts'),
        Mutation('growth past the baseline is not detected', '    if m["lines"] > bl or m["bytes"] > bb:', '    if False:', 'grown past the baseline is exit 1'),
        Mutation('over the limit with no baseline passes', '        return 1, status, f"over the limit: {msg}"', '        return 0, status, f"over the limit: {msg}"', 'over the limit with no baseline is exit 1'),
        Mutation('the hook line prints on every start', '        if status in ("warn", "over"):', '        if True:', '--hook-line is silent'),
        Mutation('the hook line can fail a session start', '        if args.hook_line:\n            return 0\n        print(f"unusable', '        if False:\n            return 0\n        print(f"unusable', '--hook-line never fails'),
        Mutation('--record writes nothing', '        baseline.write_text(json.dumps({"lines": m["lines"], "bytes": m["bytes"]}) + "\\n", encoding="utf-8")', '        pass', '--record writes the measured size'),
        Mutation('a missing index is an error', '        return 0, "none", f"no index at {index} (nothing to measure)"', '        raise Unusable(f"no index at {index}")', 'no index is not an error'),
        Mutation('autoMemoryDirectory is not read', '        d = _setting(f, "autoMemoryDirectory")', '        d = None', 'autoMemoryDirectory in user settings is honoured'),
        Mutation('the slug keeps its non-alphanumerics', 're.sub(r"[^A-Za-z0-9]", "-", str(path))', 're.sub(r"[^A-Za-z0-9/]", "-", str(path))', 'the slug matches a real one'),
        Mutation('user settings win over project settings', '(project / ".claude" / "settings.local.json", project / ".claude" / "settings.json", home / ".claude" / "settings.json")', '(home / ".claude" / "settings.json", project / ".claude" / "settings.local.json", project / ".claude" / "settings.json")', 'a project setting wins'),
        Mutation('--record without a baseline is accepted', '            raise Unusable("--record needs --baseline FILE")', '            return 0, status, msg', '--record without --baseline is refused'),
    ),
)
