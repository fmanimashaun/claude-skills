"""Mutation guard: brain_local_sync. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #877. The bridge between docs/brain and Claude Code's auto-memory has three promises a reader
# cannot see from a clean run: it never writes the repo from --propose, never overwrites a file it
# did not write, and never lets a `user` memory cross. Each mutation breaks one promise; each names
# the fixture that must notice. The selftest builds both stores in a tempdir, so no `needs`.
GUARD = Guard(
    name="brain_local_sync",
    subject="plugins/rails-flow/scripts/brain_local_sync.py",
    selftest="plugins/rails-flow/scripts/brain_local_sync.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "a user memory crosses into the brain, so a personal note becomes team doctrine",
            'NEVER_SYNCED = {"user"}',
            "NEVER_SYNCED = set()",
            "a user memory is never synced",
        ),
        Mutation(
            "pull overwrites a file the harness wrote, so a developer's own memory is replaced by a pointer",
            "        if target.exists():\n            skipped.append(target)        # NEVER overwrite a file this tool did not write\n            continue\n",
            "        if False:\n            continue\n",
            "kept, not overwritten, and reported",
        ),
        # propose has no write path; the mutation ADDS one, which is the only way to prove the
        # fixture snapshots the tree rather than trusting the function's name.
        Mutation(
            "propose writes the memo into the repo, bypassing review",
            "    return [memo_text(l) for l in p[\"outbound\"]]",
            "    items = [memo_text(l) for l in p[\"outbound\"]]\n"
            "    for rel, text, _ in items:\n        (root / rel).parent.mkdir(parents=True, exist_ok=True); (root / rel).write_text(text, encoding=\"utf-8\")\n    return items",
            "propose writes nothing",
        ),
        Mutation(
            "the pointer's description is truncated, so recall matches on a fragment",
            "    desc = memo[\"description\"].replace(\"\\\\\", \"\\\\\\\\\").replace('\"', '\\\\\"')",
            "    desc = memo[\"description\"][:12]",
            "the pointer carries the memo's own description verbatim",
        ),
        Mutation(
            "the pointer copies the memo body, so the local store becomes a second copy that drifts",
            "            f\"Repo memo: `{rel}`. The repo copy is authoritative; read it before acting on this line.\\n\")",
            "            f\"Repo memo: `{rel}`.\\n\\n{memo['body']}\\n\")",
            "a pointer, not a copy",
        ),
        Mutation(
            "the slug match stops stripping the type prefix, so a proposed memo that lands comes straight back as inbound",
            'PREFIX = re.compile(r"^(feedback|decision|project)[-_]")',
            'PREFIX = re.compile(r"^\\Z")',
            "no duplicate inbound",
        ),
        Mutation(
            "divergence is never detected, so two bodies of one lesson silently coexist",
            "        if l is not None and not l[\"pointer\"] and l[\"body\"] != m[\"body\"]:",
            "        if False:",
            "a diverged pair reports both sides",
        ),
        Mutation(
            "the index line is appended on every run, so MEMORY.md grows a duplicate per session",
            "        if f\"({target.name})\" not in idx:",
            "        if True:",
            "a re-created pointer does not duplicate its index line",
        ),
        Mutation(
            "a missing auto-memory store reads as a pass instead of n/a",
            "    if not store.is_dir():\n        print(f\"n/a: no auto-memory store at {store} — this harness keeps none for this path, or the path differs\")\n        return 3",
            "    if False:\n        return 3",
            "no auto-memory store is n/a",
        ),
    ),
)
