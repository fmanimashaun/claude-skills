#!/usr/bin/env python3
"""Re-read the Claude Code docs our doctrine quotes, and list the CHANGELOG entries we have not reviewed.

Run:  python3 scripts/check_upstream_docs.py              # fetch: quotes still present? new entries?
      python3 scripts/check_upstream_docs.py --coverage   # local: every cited docs page has a row
      python3 scripts/check_upstream_docs.py --selftest   # prove the rules fire AND stay silent

WHY (#1328). Claude Code ships most weeks, and our doctrine quotes its docs verbatim. A quote is true
on the day it was fetched and nothing re-read it after. #1326 found `model-tiers.md` quoting a subagent
model-resolution order that changed in v2.1.251: its "session-wide" recipe had silently stopped working
for every shipped agent. Replayed against the live pages, a presence check flags that quote at once.

THE REGISTRY IS THE JOIN (`docs/evidence/upstream/claude-code.json`). Each row is one Claude Code
behaviour we rely on: the docs page, the verbatim quote, and the files built on it. A quote that is
gone names those files, which is where the fix goes. Scraping quotes out of prose was tried first and
flagged true quotes as missing, so the registry is explicit, like `doctrine_map.py`'s CLAIMS.

TWO MODES, BECAUSE ONE OF THEM MUST NOT GATE. The fetch mode depends on the network and on upstream
edits, so as a PR gate it would fail a change for something Anthropic did; that teaches people to
ignore red. It runs weekly (`.github/workflows/upstream.yml`) and files one issue. `--coverage` is
local and deterministic, so it IS a gate: a new `code.claude.com/docs` citation with no registry row
would be a quote nothing re-reads, which is the gap this closes.

THE CHANGELOG CURSOR. `changelog_reviewed` is the last Claude Code version a maintainer reviewed.
Newer entries that name a surface we build on are listed; `/maintainer-upstream` triages them and
advances the cursor. The cursor moves only by a commit, so the review is on the record.

Exit codes:  0 clean · 1 drift (a quote gone, an unreviewed entry, or a coverage finding)
             · 2 unusable (registry unreadable, or a page could not be fetched: never reported clean)
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = Path("docs/evidence/upstream/claude-code.json")
CHANGELOG_URL = "https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md"
DOCS_URL = re.compile(r"https://code\.claude\.com/docs/en/[a-z0-9][a-z0-9/_-]*[a-z0-9]")
# Where a citation is a historical record, not live doctrine: re-reading it would rewrite history.
NOT_DOCTRINE = ("CHANGELOG.md", "docs/brain/history/", str(REGISTRY), "scripts/check_upstream_docs.py")
# The surfaces our plugins build on. An entry naming none of them is not ours to review.
SURFACES = re.compile(
    r"\b(hooks?|PreToolUse|PostToolUse|SessionStart|Stop hook|subagents?|agents?|frontmatter|plugins?|"
    r"marketplaces?|skills?|settings|CLAUDE\.md|AGENTS\.md|slash commands?|effort|advisor|MCP|"
    r"permissions?|CLAUDE_[A-Z_]+|worktrees?)\b", re.I)

Fetch = Callable[[str], str]


class Unusable(RuntimeError):
    pass


def normalise(text: str) -> str:
    """Markdown down to comparable prose: links to their text, emphasis and code marks dropped."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*`]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def http_fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "claude-skills-upstream-check"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def load(root: Path) -> dict:
    try:
        data = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
        data["changelog_reviewed"], data["quotes"]  # noqa: B018 -- the two fields everything reads
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Unusable(f"{REGISTRY} is unreadable: {exc}") from exc
    return data


def check_quotes(data: dict, fetch: Fetch) -> list[str]:
    pages: dict[str, str] = {}
    findings = []
    for row in data["quotes"]:
        url = row["url"]
        if url not in pages:
            try:
                pages[url] = normalise(fetch(url + ".md"))
            except Exception as exc:  # noqa: BLE001 -- any fetch failure is the same verdict
                raise Unusable(f"could not fetch {url}.md: {exc}") from exc
        if normalise(row["quote"]) not in pages[url]:
            findings.append(f"  [quote-gone] {row['id']} -- {url} no longer says: \"{row['quote']}\"\n"
                            f"      built on it: {', '.join(row['used_by'])}")
    return findings


def _version(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


def unreviewed(changelog: str, cursor: str) -> list[tuple[str, str]]:
    """(version, entry) for every entry newer than the cursor that names a surface we build on."""
    out = []
    version = None
    for line in changelog.splitlines():
        heading = re.match(r"^## (\d+(?:\.\d+)+)\s*$", line)
        if heading:
            version = heading.group(1)
            continue
        if version and _version(version) > _version(cursor) and line.startswith("- ") and SURFACES.search(line):
            out.append((version, line[2:].strip()))
    return out


def check_coverage(root: Path, data: dict) -> list[str]:
    findings = []
    ids = [row.get("id") for row in data["quotes"]]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        findings.append(f"  [duplicate-id] {dup} is used by more than one row")
    rows_by_url = {row.get("url") for row in data["quotes"]}
    for row in data["quotes"]:
        if not row.get("quote") or not row.get("url") or not row.get("used_by"):
            findings.append(f"  [incomplete-row] {row.get('id')} needs a url, a quote and used_by")
        for path in row.get("used_by", []):
            if not (root / path).exists():
                findings.append(f"  [stale-used-by] {row.get('id')} names {path}, which does not exist")
    tracked = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True).stdout.split()
    if not tracked:
        raise Unusable("git ls-files listed nothing -- coverage over no files is not coverage")
    cited: dict[str, list[str]] = {}
    for path in tracked:
        if path.startswith(NOT_DOCTRINE):
            continue
        try:
            text = (root / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for url in set(DOCS_URL.findall(text)):
            cited.setdefault(url.split("#")[0], []).append(path)
    for url in sorted(set(cited) - rows_by_url):
        findings.append(f"  [uncovered-citation] {url} is cited by {', '.join(sorted(cited[url]))} "
                        f"and no row in {REGISTRY} re-reads it")
    return findings


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_upstream_docs.py", description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        data = load(a.root)
        if a.coverage:
            findings = check_coverage(a.root, data)
            head = f"{len(data['quotes'])} registry rows cover every cited Claude Code docs page"
        else:
            findings = check_quotes(data, http_fetch)
            try:
                entries = unreviewed(http_fetch(CHANGELOG_URL), data["changelog_reviewed"])
            except Exception as exc:  # noqa: BLE001
                raise Unusable(f"could not fetch {CHANGELOG_URL}: {exc}") from exc
            findings += [f"  [unreviewed] {v}: {e}" for v, e in entries]
            head = (f"{len(data['quotes'])} quotes still present; no entry after "
                    f"{data['changelog_reviewed']} names a surface we build on")
    except Unusable as exc:
        print(f"UNUSABLE: {exc}", file=sys.stderr)
        return 2
    if findings:
        print(f"{len(findings)} finding(s):")
        print("\n".join(findings))
        return 1
    print(head)
    return 0


def selftest() -> int:
    import tempfile

    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label} {detail}".rstrip())

    page = ("# Subagents\n\nClaude Code resolves the model in this order:\n\n"
            "1. The per-invocation `model` parameter\n2. The **frontmatter**, see [docs](/x)\n")
    row = {"id": "order", "url": "https://code.claude.com/docs/en/sub-agents",
           "quote": "1. The per-invocation `model` parameter 2. The frontmatter, see docs", "used_by": ["a.md"]}
    data = {"changelog_reviewed": "2.1.250", "quotes": [row]}
    check("CONTROL: a quote across lines, emphasis and a link is found", check_quotes(data, lambda u: page) == [],
          str(check_quotes(data, lambda u: page)))
    moved = page.replace("1. The per-invocation `model` parameter", "1. The `CLAUDE_CODE_SUBAGENT_MODEL` variable")
    gone = check_quotes(data, lambda u: moved)
    check("a quote the page no longer says is a finding naming what is built on it",
          len(gone) == 1 and "[quote-gone] order" in gone[0] and "a.md" in gone[0], str(gone))
    asked: list[str] = []
    check_quotes(data, lambda u: asked.append(u) or page)
    check("the page is fetched as markdown", asked == ["https://code.claude.com/docs/en/sub-agents.md"], str(asked))

    def down(url: str) -> str:
        raise OSError("offline")
    try:
        check_quotes(data, down)
        check("a fetch failure is UNUSABLE, never clean", False)
    except Unusable:
        pass

    log = ("# Changelog\n\n## 2.1.252\n\n- Fixed a hook payload field\n- Improved terminal colours\n\n"
           "## 2.1.251\n\n- Subagent model order changed\n\n## 2.1.250\n\n- Added a plugins flag\n")
    got = unreviewed(log, "2.1.250")
    check("entries after the cursor that name our surfaces are listed",
          got == [("2.1.252", "Fixed a hook payload field"), ("2.1.251", "Subagent model order changed")], str(got))
    check("CONTROL: nothing after the newest version is listed", unreviewed(log, "2.1.252") == [])
    check("versions compare numerically, not as text", unreviewed("## 2.1.100\n\n- hooks\n", "2.1.99") != [])

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        (root / REGISTRY).parent.mkdir(parents=True)
        (root / "a.md").write_text("see https://code.claude.com/docs/en/sub-agents#model\n", encoding="utf-8")
        (root / "CHANGELOG.md").write_text("https://code.claude.com/docs/en/old-page\n", encoding="utf-8")
        (root / REGISTRY).write_text(json.dumps(data), encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        check("CONTROL: a cited page with a row is covered, and CHANGELOG citations are history",
              check_coverage(root, load(root)) == [], str(check_coverage(root, load(root))))
        (root / "b.md").write_text("https://code.claude.com/docs/en/hooks\n", encoding="utf-8")
        subprocess.run(["git", "add", "b.md"], cwd=root, check=True)
        found = check_coverage(root, load(root))
        check("a cited page with no row is a finding naming the citer",
              any("[uncovered-citation] https://code.claude.com/docs/en/hooks" in f and "b.md" in f for f in found),
              str(found))
        stale = dict(data, quotes=[dict(row, used_by=["gone.md"])])
        (root / REGISTRY).write_text(json.dumps(stale), encoding="utf-8")
        check("a used_by path that does not exist is a finding",
              any("[stale-used-by] order names gone.md" in f for f in check_coverage(root, load(root))))
        (root / REGISTRY).write_text("{", encoding="utf-8")
        try:
            load(root)
            check("an unreadable registry is UNUSABLE", False)
        except Unusable:
            pass

    for f in failures:
        print(f"FAIL: {f}")
    print(f"check_upstream_docs selftest: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
