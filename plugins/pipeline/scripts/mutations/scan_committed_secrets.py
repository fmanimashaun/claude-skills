"""Mutation guard: scan_committed_secrets. Declared here, run by scripts/mutation_check.py (#1341).

Each mutation lets a secret sit in a file git would commit while the BLOCKING safety pass reads clean.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="scan_committed_secrets",
    subject="scripts/scan_committed_secrets.py",
    selftest="scripts/scan_committed_secrets.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "untracked files are not scanned (the plain `git diff` blind spot, restored)",
            '    proc = subprocess.run(["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],',
            '    proc = subprocess.run(["git", "-C", str(root), "ls-files", "--cached", "-z"],',
            "an UNTRACKED file holding a secret is found (plain git diff cannot see it)",
        ),
        Mutation(
            "ignored files are scanned too, so the gitignored secrets file is a false finding",
            '    proc = subprocess.run(["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],',
            '    proc = subprocess.run(["git", "-C", str(root), "ls-files", "--cached", "--others", "-z"],',
            "CONTROL: an ignored secrets file is not scanned",
        ),
        Mutation(
            "a found secret is not reported",
            "            if value in text:",
            "            if False:",
            "an UNTRACKED file holding a secret is found (plain git diff cannot see it)",
        ),
        Mutation(
            "the finding prints the secret value",
            '                findings.append(f"  [secret-in-committable-file] {key} appears in {path.relative_to(root)}")',
            '                findings.append(f"  [secret-in-committable-file] {key}={value} appears in {path.relative_to(root)}")',
            "...and the value itself is never printed",
        ),
        Mutation(
            "deploy.yml-routed facts are treated as secrets",
            "            secret = not any(dest.startswith(p) for p in PUBLIC_DESTS) or any(s in dest for s in SECRET_DESTS)",
            "            secret = True",
            "CONTROL: a deploy.yml-routed fact is not a secret",
        ),
        Mutation(
            "an untagged key is assumed public",
            "    out, secret = {}, True  # before any section tag: treat as secret",
            "    out, secret = {}, False",
            "an untagged key counts as a secret",
        ),
        Mutation(
            "no briefing reads as clean",
            '        return 2, [f"UNUSABLE: no {BRIEFING}, so there are no secret values to look for"]',
            '        return 0, ["nothing to scan"]',
            "no briefing is UNUSABLE, never clean",
        ),
    ),
)
