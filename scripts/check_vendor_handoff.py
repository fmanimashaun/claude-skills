#!/usr/bin/env python3
"""Vercel and Supabase teach their own platforms; our shipped docs hand off, they never carry a copy. (#2289)

Run:  python3 scripts/check_vendor_handoff.py [FILE...]   # the shipped docs (every tracked .md under plugins/ and skills/), or just FILE...
      python3 scripts/check_vendor_handoff.py --selftest

WHY. The `vercel` plugin (vercel/vercel-plugin) ships skills and the `/vercel:` commands; the `supabase` plugin ships the `supabase` and
`supabase-postgres-best-practices` skills (supabase-community/supabase-plugin, also supabase/agent-skills). A command table copied into our
skill goes stale against their next release, and it gives one concern two homes (plugin-boundaries, rule 2). The owner's direction on #2289:
vendor plugins own their doctrine; our shipped skills and commands hand off.

THE RULE. A line of a shipped `.md` file that tells the reader to run a vendor CLI step is refused: `supabase start`, `npx supabase db diff`,
`vercel env pull`, `vercel --prod`, a bare `vercel`, `vercel ls` (the brand in lower case followed by one of STEP's subcommands or a flag, or
the bare command where it is told to be run). Nothing excuses a step, not even a line that says `Hand-off:`: a pointer NAMES the vendor skill or command
(`/vercel:env`, the `supabase` skill), it does not carry the steps, so a table with `Hand-off:` on every row is still a copied table. The
marker has one job: a line that says `Hand-off:` about Vercel or Supabase must name its target (`/vercel:<command>`, vercel/vercel-plugin,
supabase-community/supabase-plugin, supabase/agent-skills, the `supabase` skill, supabase-postgres-best-practices), or it points nowhere.
A hand-off line alone is clean; so is any mention that is no step (a path such as supabase/config.toml, a URL, `.vercel`, `vercel.json`, the
install lines `npx plugins add vercel/vercel-plugin`).

A KNOWN FALSE POSITIVE: a lower-case `supabase test`, `vercel list` or the like in prose that is no command reads as a step; reword it ("Supabase's tests").

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
# A vendor CLI step, in four shapes. `STEP`: the brand in lower case and a subcommand, or `vercel` and a flag (`vercel --prod`). `BARE`: the
# bare `vercel` command where it is plainly told to be run (after run/execute/type/invoke), alone in a table cell, or alone on a line (a code
# fence); a stack id in a list ("reports `nextjs`, `supabase` or `vercel`") is no step.
STEP = re.compile(r"(?<![\w/.-])(?:npx\s+)?(?:(?:supabase|vercel)\s+(?:start|stop|status|link|unlink|env|deploy|redeploy|db|migration|gen|functions|"
                  r"secrets|login|logout|init|pull|push|dev|build|promote|rollback|domains|logs|projects|branches|inspect|whoami|ls|list|alias|rm|"
                  r"seed|test)\b|vercel\s+-{1,2}[a-z])")
BARE = (re.compile(r"(?<![\w/.-])(?i:run|execute|type|invoke)\s+`?(?:npx\s+)?vercel\b(?![\w/.:-])"),
        re.compile(r"\|\s*`?(?:npx\s+)?vercel`?\s*\|"),
        re.compile(r"^\s*(?:\$\s*)?(?:npx\s+)?vercel\s*$"))


def howto(line: str) -> str | None:
    """The vendor step a line tells the reader to run, or None."""
    for pattern in (STEP, *BARE):
        found = pattern.search(line)
        if found:
            return found.group(0).strip(" |`")
    return None


VENDOR = re.compile(r"vercel|supabase", re.I)
MARKER = "Hand-off:"
TARGET = re.compile(r"/vercel:[a-z][a-z-]*|vercel/vercel-plugin|supabase-community/supabase-plugin|supabase/agent-skills|"
                    r"supabase-postgres-best-practices|`supabase` skill")


def is_handoff(line: str) -> bool:
    """A pointer: it says `Hand-off:` and names the vendor target. It may NOT carry a step (findings_in refuses that)."""
    return MARKER in line and TARGET.search(line) is not None


def shipped_docs(paths: list[str]) -> list[str]:
    """The shipped prose: a `.md` file under plugins/ or skills/."""
    return [p for p in paths if p.endswith(".md") and p.startswith(SHIPPED)]


def findings_in(rel: str, text: str) -> list[str]:
    out = []
    for number, line in enumerate(text.splitlines(), 1):
        step = howto(line)
        if step:
            why = ("a hand-off names the vendor skill or command, not the steps" if MARKER in line
                   else "a vendor how-to with no hand-off")
            out.append(f"{rel}:{number}: {why} (`{step}`): Vercel and Supabase own their doctrine (#2289); replace the step with a `{MARKER}` line naming the "
                       f"vendor skill or command (`/vercel:<command>`, the `supabase` skill, ...), and no command of its own")
        elif MARKER in line and VENDOR.search(line) and not is_handoff(line):
            out.append(f"{rel}:{number}: a `{MARKER}` about Vercel or Supabase that names no vendor skill, command or plugin points nowhere (#2289)")
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
        found = bad(f"First, `{step}`.")
        check(f"a copied vendor step is refused: {step}", len(found) == 1 and "no hand-off" in found[0], found)
    named = (bad("x\n\nRun `vercel link`.") or ["<no finding>"])[0]
    check("the finding names the file and the line", named.startswith("plugins/x/skills/s/SKILL.md:3:"), named)
    check("a hand-off elsewhere in the file excuses nothing (a copied table cannot hide beside a pointer)",
          len(bad(handoff + "\n\n| Local | `supabase start` |\n")) == 1, bad(handoff + "\n\n| Local | `supabase start` |\n"))
    for line in ("Hand-off: run supabase start yourself.", "Hand-off: use the vendor's tool: `vercel env pull`.", "hand-off: `supabase start` via `supabase` skill"):
        check(f"a marker with no vendor target, or a lower-case marker, excuses nothing: {line}", len(bad(line)) == 1, bad(line))
    for target in ("`/vercel:env`", "vercel/vercel-plugin", "supabase-community/supabase-plugin", "supabase/agent-skills", "supabase-postgres-best-practices", "the `supabase` skill"):
        pointer = f"Hand-off: pull the environment with {target} and the schema with {target}."
        check(f"a pointer to {target} that carries no step is clean", bad(pointer) == [], bad(pointer))
        line = f"Hand-off: `vercel env pull` and `supabase db diff` are taught by {target}."
        found = bad(line)
        check(f"S2: a hand-off line that ALSO carries a command is refused: {target}", len(found) == 1 and "not the steps" in found[0], found)
    table = "| Step | Command |\n|---|---|\n| Hand-off: `/vercel:env` | `vercel env pull .env.local` |\n| Hand-off: the `supabase` skill | `supabase start` |\n"
    check("S2 NEGATIVE FIXTURE: a table with `Hand-off:` on every row is still a copied table", len(bad(table)) == 2 and all("not the steps" in f for f in bad(table)), bad(table))
    for line in ("Hand-off: see the Supabase docs.", "Hand-off: Vercel handles deploys.", "- Hand-off: for the supabase CLI, ask a teammate."):
        check(f"a hand-off about Vercel or Supabase that names no vendor target points nowhere: {line}", len(bad(line)) == 1 and "points nowhere" in bad(line)[0], bad(line))
    check("CONTROL: a `Hand-off:` line about something else is no concern of this lint", bad("Hand-off: write the work order to HANDOFF.md.") == [])
    for step in ("vercel --prod", "vercel -y --prod", "vercel redeploy dpl_123", "vercel ls", "vercel alias set a.vercel.app b.com", "supabase inspect db bloat",
                 "supabase seed buckets", "supabase test db", "Run `vercel` to deploy.", "run vercel in the project root", "To ship it, execute `npx vercel`.",
                 "| Deploy | `vercel` |", "$ vercel", "vercel", "  npx vercel  "):
        check(f"S1: a step the first detector missed is refused: {step}", len(bad(step)) == 1, bad(step))
    for line in ("The stack detector reports `nextjs`, `supabase` or `vercel`.", "the `vercel` CLI", "see `vercel.json`", "/vercel:deploy is the plugin's command",
                 "Vercel's `vercel` plugin", "a vercel project", "the .vercel directory"):
        check(f"CONTROL: not a step: {line}", bad(line) == [], bad(line))
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
