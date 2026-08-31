#!/usr/bin/env python3
"""Refuse a spec/support directory nothing loads, and a capybara that drives nothing (#803).

WHY THIS EXISTS. `testing.md` prescribes four support files -- `system.rb`, `authentication_helpers.rb`,
`webmock.rb`, `vcr.rb` -- and no shipped command scaffolds any of them. That alone is the class this
repo keeps finding (#778, #779, #797): stated, performed by nothing, checked by nothing.

ONE LINE MAKES ALL OF THEM INERT, and that is the clause worth having. `testing.md:99` says to
UNCOMMENT the auto-loader Rails generates commented out:

    Rails.root.glob("spec/support/**/*.rb").sort_by(&:to_s).each { |f| require f }

Leave it commented and every file under `spec/support/` is dead -- including ones a developer writes
by hand -- with no error and no output. A support directory that loads nothing looks exactly like one
that works, and the specs that depended on those helpers fail for reasons that point elsewhere. It is
the same shape as the `Tests:` step Rails omits under `--skip-test` (#779): **a generated default the
doctrine says to change, and nothing verifying it was changed.**

THE SECOND CLAUSE is the inert GEM, mirroring the inert CONFIG `mandated-gems` already refuses.
`capybara` is mandated (#797 enforces it) and is the developer testing workflow -- maintainer
decision on #803: system specs are the developer's, `qa/e2e` is QA's, and neither substitutes for the
other. So a project declaring capybara must actually drive it, or the gem is protection that isn't.

THREE STATES. No `spec/` directory at all -> **not applicable**, reported by name, never a pass: a
project that has not adopted RSpec has nothing here to get wrong.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SPEC = Path("spec")
SUPPORT = SPEC / "support"
GEMFILE = Path("Gemfile")

# The auto-loader, in the shapes `rails_helper.rb` actually carries. Rails' own generated line uses
# `Dir[Rails.root.join(...)]`; `testing.md` shows the modern `Rails.root.glob`. Both count -- keying
# on one would fail a project that used the other, which is a false positive on conforming work.
AUTOLOAD = re.compile(r"""(?:Rails\.root\.glob|Dir\[?\s*Rails\.root\.join)\s*\(\s*['"]spec/support""")
GEM = re.compile(r"""^\s*gem\s+(?P<q>['"])(?P<name>[A-Za-z0-9_\-]+)(?P=q)""")
DRIVEN_BY = re.compile(r"\bdriven_by\b")


def uncommented(text: str, pattern: re.Pattern) -> bool:
    """Does `pattern` match on a line that is not commented out?

    Line by line, because the whole point is a line Rails ships commented. A whole-file search would
    match the commented one and report the exact defect as clean.
    """
    return any(pattern.search(line) for line in text.splitlines()
               if not line.lstrip().startswith("#"))


def declared_gems(gemfile: str) -> set[str]:
    return {m.group("name") for m in (GEM.match(l) for l in gemfile.splitlines()) if m}


def problems(root: Path) -> list[str]:
    found: list[str] = []
    helpers = [p for p in (root / SPEC).glob("*_helper.rb")]
    helper_text = "\n".join(p.read_text(encoding="utf-8") for p in helpers)

    support_files = sorted((root / SUPPORT).glob("**/*.rb")) if (root / SUPPORT).is_dir() else []
    if support_files and not uncommented(helper_text, AUTOLOAD):
        names = ", ".join(p.relative_to(root).as_posix() for p in support_files[:4])
        found.append(
            f"{len(support_files)} file(s) under {SUPPORT}/ ({names}) and nothing loads them — "
            f"the auto-loader in spec/rails_helper.rb is absent or still commented out.\n"
            f"    Rails generates that line COMMENTED; testing.md:99 says to uncomment it. Left as "
            f"generated, every support file is dead with no error and no output.\n"
            f"    Add:  Rails.root.glob(\"spec/support/**/*.rb\").sort_by(&:to_s).each {{ |f| require f }}")

    gemfile = root / GEMFILE
    if gemfile.is_file() and "capybara" in declared_gems(gemfile.read_text(encoding="utf-8")):
        spec_text = "\n".join(p.read_text(encoding="utf-8")
                              for p in (root / SPEC).glob("**/*.rb")) if (root / SPEC).is_dir() else ""
        if not DRIVEN_BY.search(spec_text):
            found.append(
                "`capybara` is in the Gemfile and no spec calls `driven_by`, so the gem drives "
                "nothing.\n"
                "    System specs are the DEVELOPER testing workflow (#803); qa-flow's browser "
                "passes are an independent layer, not a substitute.\n"
                "    testing.md §8 has the file:  spec/support/system.rb with "
                "`driven_by :selenium, using: :headless_chrome`")
    return found


def run(root: Path = Path(".")) -> tuple[int, str]:
    """(exit, message). 0 pass, 1 fail, 3 not-applicable."""
    if not (root / SPEC).is_dir():
        return 3, f"not applicable — no {SPEC}/ in this repo (nothing to check, NOT a pass)"
    found = problems(root)
    if not found:
        return 0, f"{SPEC}/ support is wired"
    return 1, f"{len(found)} finding(s):\n" + "\n".join(f"  - {f}" for f in found)


def selftest() -> int:
    import tempfile
    checks, failures = 0, []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{('  ' + detail) if detail else ''}")

    LOADER = 'Rails.root.glob("spec/support/**/*.rb").sort_by(&:to_s).each { |f| require f }\n'

    def verdict(*, helper: str | None = None, support: dict[str, str] | None = None,
                gemfile: str | None = None, specs: dict[str, str] | None = None) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            if helper is not None:
                (root / "spec").mkdir(exist_ok=True)
                (root / "spec" / "rails_helper.rb").write_text(helper, encoding="utf-8")
            for rel, body in (support or {}).items():
                f = root / "spec" / "support" / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(body, encoding="utf-8")
            for rel, body in (specs or {}).items():
                f = root / "spec" / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(body, encoding="utf-8")
            if gemfile is not None:
                (root / "Gemfile").write_text(gemfile, encoding="utf-8")
            return run(root)

    # ---- CLAUSE 1: a support dir nothing loads ------------------------------------------------
    code, msg = verdict(helper='require "rspec/rails"\n', support={"system.rb": "# x\n"})
    check("support files with no auto-loader FAIL", code == 1, f"exit {code}")
    check("...saying nothing loads them", "nothing loads them" in msg, msg[:120])

    # THE REPORTED SHAPE: Rails ships the line COMMENTED. A whole-file search would match it and
    # report the exact defect as clean, which is why `uncommented` goes line by line.
    code, msg = verdict(helper='require "rspec/rails"\n# ' + LOADER, support={"system.rb": "# x\n"})
    check("a COMMENTED auto-loader still fails", code == 1, f"exit {code}: {msg[:90]}")

    # THE PASS, or clause 1 could be "always fail".
    code, _ = verdict(helper='require "rspec/rails"\n' + LOADER, support={"system.rb": "# x\n"})
    check("an uncommented auto-loader passes", code == 0)

    # BOTH SPELLINGS. Rails generates `Dir[Rails.root.join(...)]`; testing.md shows `Rails.root.glob`.
    # Keying on one would fail a project that used the other -- a false positive on conforming work.
    code, _ = verdict(helper='Dir[Rails.root.join("spec/support/**/*.rb")].sort.each { |f| require f }\n',
                      support={"system.rb": "# x\n"})
    check("the Dir[Rails.root.join] spelling also counts", code == 0)

    # NO support files, no requirement -- the loader is pointless without them.
    code, _ = verdict(helper='require "rspec/rails"\n')
    check("no support files, no auto-loader needed", code == 0)

    # ---- CLAUSE 2: capybara that drives nothing -----------------------------------------------
    BASE = 'require "rspec/rails"\n' + LOADER
    code, msg = verdict(helper=BASE, gemfile='gem "capybara"\n')
    check("capybara with no driven_by FAILS", code == 1, f"exit {code}")
    check("...naming the developer-workflow decision", "DEVELOPER" in msg, msg[:140])
    check("...and pointing at the file that has it", "spec/support/system.rb" in msg, msg[:200])

    code, _ = verdict(helper=BASE, gemfile='gem "capybara"\n',
                      support={"system.rb": "driven_by :selenium\n"})
    check("...and passes once a driver is configured", code == 0)

    # A driver ANYWHERE under spec/ counts -- a project may put it in rails_helper.
    code, _ = verdict(helper=BASE + "driven_by :rack_test\n", gemfile='gem "capybara"\n')
    check("a driver in rails_helper counts too", code == 0)

    # NO capybara, no requirement. Demanding a driver from a project that never asked for the gem
    # is the false positive that gets a gate switched off (#476).
    code, _ = verdict(helper=BASE, gemfile='gem "rails"\n')
    check("no capybara, no driver demanded", code == 0)
    code, _ = verdict(helper=BASE)
    check("...and no Gemfile at all is fine", code == 0)

    # ---- NOT APPLICABLE is the third state and never a pass -----------------------------------
    with tempfile.TemporaryDirectory() as td:
        code, msg = run(Path(td))
    check("no spec/ is not-applicable, not a pass", code == 3, f"exit {code}")
    check("...and says so rather than reporting clean", "NOT a pass" in msg, msg)

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} spec-support assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="run the fixtures and exit")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    code, msg = run()
    print(msg, file=sys.stderr if code == 1 else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
