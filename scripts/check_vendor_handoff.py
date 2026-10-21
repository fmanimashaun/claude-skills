#!/usr/bin/env python3
"""Vercel and Supabase teach their own platforms; our shipped docs hand off, they never carry a copy. (#2289)

Run:  python3 scripts/check_vendor_handoff.py [FILE...]   # the shipped docs (every tracked .md under plugins/ and skills/), or just FILE...
      python3 scripts/check_vendor_handoff.py --selftest

WHY. The `vercel` plugin (vercel/vercel-plugin) ships skills and the `/vercel:` commands; the `supabase` plugin ships the `supabase` and
`supabase-postgres-best-practices` skills (supabase-community/supabase-plugin, also supabase/agent-skills). A command table copied into our
skill goes stale against their next release, and it gives one concern two homes (plugin-boundaries, rule 2). The owner's direction on #2289:
vendor plugins own their doctrine; our shipped skills and commands hand off.

THE RULE. A line of a shipped `.md` file that tells the reader to run a vendor CLI step (`supabase start`, `npx supabase db diff`, `vercel env
pull`, `vercel deploy`: the brand in lower case followed by one of HOWTO's subcommands) is refused unless that line IS a hand-off line: it
carries `Hand-off:` and names the vendor target it hands off to (`/vercel:<command>`, vercel/vercel-plugin, supabase-community/supabase-plugin,
supabase/agent-skills, the `supabase` skill, supabase-postgres-best-practices). The excuse is per LINE: a hand-off elsewhere in the file excuses
nothing, so a copied table cannot hide beside a pointer. A hand-off line alone is clean; so is any mention that is no step (a path such as
supabase/config.toml, a URL, `.vercel`, the install lines `npx plugins add vercel/vercel-plugin`).

WHAT IT DOES NOT: judge prose about the platforms that is no CLI step, or data files (the stacks' markers, the security cases). A how-to
written as prose instead of a command is a reviewer's catch, which is why the vendor commands are the measurable edge. Stdlib only.

Exit: 0 clean, 1 findings.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHIPPED = ("plugins/", "skills/")
HOWTO = re.compile(r"(?<![\w/.-])(?:npx\s+)?(?:supabase|vercel)\s+"
                   r"(?:start|stop|status|link|unlink|env|deploy|db|migration|gen|functions|secrets|login|logout|init|pull|push|dev|build|promote|"
                   r"rollback|domains|logs|projects|branches|inspect|whoami)\b")
MARKER = "Hand-off:"
TARGET = re.compile(r"/vercel:[a-z][a-z-]*|vercel/vercel-plugin|supabase-community/supabase-plugin|supabase/agent-skills|"
                    r"supabase-postgres-best-practices|`supabase` skill")


def is_handoff(line: str) -> bool:
    return MARKER in line and TARGET.search(line) is not None


def shipped_docs(paths: list[str]) -> list[str]:
    """The shipped prose: a `.md` file under plugins/ or skills/."""
    return [p for p in paths if p.endswith(".md") and p.startswith(SHIPPED)]


def findings_in(rel: str, text: str) -> list[str]:
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        match = HOWTO.search(line)
        if match and not is_handoff(line):
            out.append(f"{rel}:{number}: a vendor how-to (`{match.group(0)}`) with no hand-off: Vercel and Supabase own their doctrine (#2289); replace the step with "
                       f"`{MARKER}` naming the vendor skill or command (`/vercel:<command>`, the `supabase` skill, ...) on that same line")
    return out


def scan(root: Path, paths: list[str], only_shipped: bool = True) -> tuple[list[str], int]:
    """(findings, files examined) over `paths`, given relative to `root`. A file NAMED on the command line is examined whatever its place."""
    docs = shipped_docs(paths) if only_shipped else [p for p in paths if p.endswith(".md")]
    found: list[str] = []
    for rel in docs:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found += findings_in(rel, text)
    return found, len(docs)


def tracked(root: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(root), "ls-files", "--", *SHIPPED], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"git ls-files failed in {root}: {out.stderr.strip()[:200]}")
    return out.stdout.splitlines()


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        return selftest()
    root = ROOT
    try:
        paths = argv if argv else tracked(root)
    except RuntimeError as exc:
        print(f"vendor hand-off: cannot list the shipped docs ({exc}); an unread tree is not a pass", file=sys.stderr)
        return 2
    findings, examined = scan(root, paths, only_shipped=not argv)
    for line in findings:
        print(f"  {line}")
    print(f"vendor hand-off: {len(findings)} finding(s) in {examined} shipped doc(s)" if findings
          else f"vendor hand-off: {examined} shipped doc(s) examined, no vendor how-to without a hand-off")
    if not argv and examined == 0:
        print("vendor hand-off: no shipped docs were examined, which is not a pass", file=sys.stderr)
        return 2
    return 1 if findings else 0


# --------------------------------------------------------------------------- selftest

def selftest() -> int:
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: object = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{(' -- ' + str(detail)) if detail != '' else ''}")

    def bad(text: str, rel: str = "plugins/x/skills/s/SKILL.md") -> list[str]:
        return findings_in(rel, text)

    handoff = "- Hand-off: for the Supabase CLI steps use the vendor's `supabase` skill (supabase/agent-skills)."
    check("NEGATIVE FIXTURE: a hand-off line alone is clean", bad(handoff) == [], bad(handoff))
    for step in ("supabase start", "npx supabase db diff", "supabase migration new add_users", "supabase gen types --lang typescript",
                 "vercel env pull .env.local", "vercel deploy --prod", "npx vercel link", "vercel dev", "supabase functions deploy hello"):
        found = bad(f"Run `{step}` first.")
        check(f"a copied vendor step is refused: {step}", len(found) == 1 and "no hand-off" in found[0], found)
    named = (bad("x\n\nRun `vercel link`.") or ["<no finding>"])[0]
    check("the finding names the file and the line", named.startswith("plugins/x/skills/s/SKILL.md:3:"), named)
    check("a hand-off elsewhere in the file excuses nothing (a copied table cannot hide beside a pointer)",
          len(bad(handoff + "\n\n| Local | `supabase start` |\n")) == 1, bad(handoff + "\n\n| Local | `supabase start` |\n"))
    for line in ("Hand-off: run supabase start yourself.", "Hand-off: use the vendor's tool: `vercel env pull`.", "hand-off: `supabase start` via `supabase` skill"):
        check(f"a marker with no vendor target, or a lower-case marker, excuses nothing: {line}", len(bad(line)) == 1, bad(line))
    for target in ("`/vercel:env`", "vercel/vercel-plugin", "supabase-community/supabase-plugin", "supabase/agent-skills", "supabase-postgres-best-practices", "the `supabase` skill"):
        line = f"Hand-off: `vercel env pull` and `supabase db diff` are taught by {target}."
        check(f"a hand-off line may carry the command it hands off, to {target}", bad(line) == [], bad(line))
    for line in ("see `supabase/config.toml`", "the `.vercel` directory", "https://supabase.com/docs/guides/cli", "Vercel deploys on push", "Supabase starts a local stack",
                 "npx plugins add vercel/vercel-plugin", "claude plugin marketplace add supabase/agent-skills", "the supabase CLI and the vercel CLI",
                 "set `supabase_url` in .env", "mysupabase start", "https://example.com/vercel dev"):
        check(f"CONTROL: a mention that is no step is not a how-to: {line}", bad(line) == [], bad(line))
    check("only shipped .md under plugins/ and skills/ is examined",
          shipped_docs(["plugins/a/x.md", "skills/s/SKILL.md", "plugins/a/x.py", "docs/x.md", "README.md", "plugins/a/data.json", ".claude/commands/x.md"]) == ["plugins/a/x.md", "skills/s/SKILL.md"])
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for rel, text in {"plugins/a/skills/s/SKILL.md": "Run `supabase start`.\n", "plugins/a/clean.md": handoff + "\n", "plugins/a/code.py": "supabase start\n",
                          "docs/other.md": "vercel deploy\n", "skills/core/SKILL.md": "Use `vercel env pull`.\n"}.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text)
        paths = ["plugins/a/skills/s/SKILL.md", "plugins/a/clean.md", "plugins/a/code.py", "docs/other.md", "skills/core/SKILL.md"]
        found, examined = scan(root, paths)
        check("a scan finds the plugin file and the skills/ file, and skips the rest", examined == 3 and len(found) == 2 and any("plugins/a/skills" in f for f in found)
              and any("skills/core" in f for f in found), (found, examined))
        found, examined = scan(root, ["plugins/a/clean.md"])
        check("a scan of a hand-off alone is clean", found == [] and examined == 1, (found, examined))
        found, examined = scan(root, ["plugins/a/missing.md"])
        check("a path that cannot be read is skipped, not a crash", found == [] and examined == 1, (found, examined))
        # main(): the exit code and the output, through the entry point.
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main([str(root / "plugins/a/skills/s/SKILL.md")])
        check("main() on a named file that carries a copied step exits 1 and names it", code == 1 and "no hand-off" in out.getvalue(), (code, out.getvalue()))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main([str(root / "plugins/a/clean.md")])
        check("main() on a named hand-off alone exits 0", code == 0, (code, out.getvalue()))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main([str(root / "plugins/a/code.py")])
        check("main() on a named file that is not markdown examines nothing and passes", code == 0 and "0 shipped doc(s)" in out.getvalue(), (code, out.getvalue()))
    here = scan(ROOT, tracked(ROOT)) if (ROOT / ".git").exists() else None
    if here is not None:
        check("the shipped tree carries no vendor how-to without a hand-off", here[0] == [], here[0])
        check("the shipped tree scan examined docs (a scan of nothing is not a pass)", here[1] > 50, here[1])
    for f in failures:
        print(f"selftest FAIL: {f}")
    print(f"check_vendor_handoff selftest: {'FAILED' if failures else 'ok'} ({checks} check(s), {len(failures)} failure(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
