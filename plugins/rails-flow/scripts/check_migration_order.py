#!/usr/bin/env python3
"""A branch must not add a migration numbered at or below the base branch's schema version (#1248).

WHY IT IS A GATE NOW. Rails records such a migration as ALREADY APPLIED and never runs it, so its
columns never arrive and the suite fails somewhere unrelated. The rule already lived in
`session_coordinator.py` -- but only `/rails-flow:coordinate` ran it, so no project gate, `bin/doctrine`
or CI ever checked it. Downstream, a branch stamped before `dev`'s newest migration merged `dev`, a
`db:schema:load` stamped schema.rb past it, and the rebuilt schema silently lacked its column while
the project's own ordering lint said "they agree".

ONE IMPLEMENTATION. This is a thin CLI over `session_coordinator.migration_findings`, which compares
every migration the branch ADDS (`git diff <base>...HEAD -- db/migrate/`) against the schema version
on `<base>` -- so it sees the case even after the base has been merged into the branch.

Run:  check_migration_order.py [--root DIR] [--base origin/dev]
      check_migration_order.py --selftest
Exit: 0 in order · 1 a migration at or below the base's schema version · 2 the base cannot be read
      (never reported as clean) · 3 not applicable (no db/schema.rb)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from session_coordinator import migration_findings


def check(root: Path, base: str) -> tuple[int, list[str]]:
    if not (root / "db" / "schema.rb").is_file():
        return 3, ["not applicable — no db/schema.rb in this project"]
    probe = subprocess.run(["git", "-C", str(root), "show", f"{base}:db/schema.rb"],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        return 2, [f"cannot read db/schema.rb on `{base}` — fetch it; this is not a clean result"]
    findings = migration_findings(root, base)
    if not findings:
        return 0, [f"every migration this branch adds is numbered above {base}'s schema version"]
    lines = [f"{len(findings)} finding(s):"]
    for f in findings:
        lines.append(f"  - {f.subject}: {f.detail}")
    return 1, lines


def selftest() -> int:
    import tempfile
    checks, fails = 0, []

    def expect(label: str, ok: bool) -> None:
        nonlocal checks
        checks += 1
        if not ok:
            fails.append(label)

    def schema(version: str) -> str:
        return f'ActiveRecord::Schema[8.1].define(version: {version}) do\nend\n'

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        g = ["git", "-C", tmp, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q", "-b", "dev", tmp], check=True)
        (root / "db" / "migrate").mkdir(parents=True)
        (root / "db" / "schema.rb").write_text(schema("2026_01_01_000000"))
        subprocess.run(g + ["add", "."], check=True)
        subprocess.run(g + ["commit", "-qm", "base"], check=True)
        expect("the base branch itself adds nothing and is in order", check(root, "dev")[0] == 0)

        subprocess.run(g + ["checkout", "-qb", "feat"], check=True)
        (root / "db/migrate/20260102000000_add_good.rb").write_text("class AddGood; end\n")
        subprocess.run(g + ["add", "."], check=True)
        subprocess.run(g + ["commit", "-qm", "good"], check=True)
        expect("a migration numbered above the base's version is in order", check(root, "dev")[0] == 0)

        # THE REPORTED CASE: dev moves past the branch's migration, then the branch merges dev.
        subprocess.run(g + ["checkout", "-q", "dev"], check=True)
        (root / "db" / "migrate").mkdir(parents=True, exist_ok=True)   # git does not track an empty dir
        (root / "db/migrate/20260105000000_on_dev.rb").write_text("class OnDev; end\n")
        (root / "db" / "schema.rb").write_text(schema("2026_01_05_000000"))
        subprocess.run(g + ["add", "."], check=True)
        subprocess.run(g + ["commit", "-qm", "dev moves on"], check=True)
        subprocess.run(g + ["checkout", "-q", "feat"], check=True)
        subprocess.run(g + ["merge", "-q", "--no-edit", "dev"], check=True)
        code, lines = check(root, "dev")
        expect("a branch migration below dev's newer schema version FAILS, even after merging dev",
               code == 1 and "20260102000000_add_good.rb" in " ".join(lines))
        expect("...and dev's own migration is not blamed", "on_dev" not in " ".join(lines))
        expect("an unreadable base is exit 2, never clean", check(root, "no-such-ref")[0] == 2)

    with tempfile.TemporaryDirectory() as tmp:
        expect("a project with no db/schema.rb is n/a", check(Path(tmp), "dev")[0] == 3)

    for label in fails:
        print(f"FAIL {label}")
    print(f"check_migration_order selftest: {checks} checks, {len(fails)} failure(s)")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Refuse a migration numbered at or below the base's schema version.")
    ap.add_argument("--root", default=".")
    ap.add_argument("--base", default="origin/dev")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    code, lines = check(Path(a.root), a.base)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
