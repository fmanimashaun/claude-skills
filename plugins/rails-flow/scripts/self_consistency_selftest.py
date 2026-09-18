#!/usr/bin/env python3
"""Prove every self-consistency rule fires -- and, more importantly, stays silent.

Run:  python3 self_consistency.py --selftest      (or execute this file directly)

The silent direction is the one that matters. A rule that flags everything looks
rigorous, gets disabled after the third false positive, and then catches nothing.
This project's own criterion is: zero false positives on a conforming repo, or the
rule is cut, not softened.

Costs nothing: no network, no bundler, no Rails.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import self_consistency as sc  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0


def _tree(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="railsflow-selfconsist-"))
    for relpath, content in files.items():
        target = root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def expect(rule: str, files: dict[str, str], *, flagged: bool, label: str,
           whole_repo: bool = False) -> None:
    """Assert `rule` does (or does not) fire for the given tree."""
    global CHECKS
    CHECKS += 1
    root = _tree(files)
    try:
        if whole_repo:
            findings, _ = sc.check_all(root)
        else:
            findings = []
            for relpath in files:
                findings.extend(sc.check_file(root / relpath, root))
    except Exception as exc:  # pragma: no cover - a raising rule is a bug
        FAILURES.append(f"{rule} / {label}: raised {exc!r}")
        return
    got = [f for f in findings if f.rule == rule]
    if bool(got) != flagged:
        want = "a finding" if flagged else "silence"
        detail = "; ".join(str(f) for f in got) or "(none)"
        FAILURES.append(f"{rule} / {label}: expected {want}, got {detail}")


# ---------------------------------------------------------------------------
# swallowed-exception
# ---------------------------------------------------------------------------

expect("swallowed-exception",
       {"app/models/user.rb": "class User\n  def sync\n    Api.call\n  rescue nil\n  end\nend\n"},
       flagged=True, label="rescue nil")

expect("swallowed-exception",
       {"app/models/user.rb":
        "class User\n  def sync\n    Api.call\n  rescue Api::Error => e\n"
        "    Rails.error.report(e)\n    raise\n  end\nend\n"},
       flagged=False, label="specific rescue that reports and re-raises")

expect("swallowed-exception",
       {"app/jobs/sync_job.rb":
        "class SyncJob\n  def perform\n    Api.call\n  rescue\n  end\nend\n"},
       flagged=True, label="empty bare rescue body")

# `#` inside a string must not be mistaken for a comment and vice versa.
expect("swallowed-exception",
       {"app/models/tag.rb":
        'class Tag\n  COLOR = "#0077CC"\n  def label = "##{name}"\nend\n'},
       flagged=False, label="hash characters in strings are not comments")

# A commented-out rescue nil is discussion, not code.
expect("swallowed-exception",
       {"app/models/user.rb": "class User\n  # never write rescue nil here\nend\n"},
       flagged=False, label="rescue nil inside a comment")

# ---------------------------------------------------------------------------
# swallowed-verdict
# ---------------------------------------------------------------------------

expect("swallowed-verdict",
       {"bin/ci.sh": "#!/usr/bin/env bash\nbundle exec rspec || true\n"},
       flagged=True, label="rspec verdict softened with || true")

expect("swallowed-verdict",
       {".github/workflows/ci.yml":
        "jobs:\n  test:\n    steps:\n      - run: bundle exec rubocop || echo skipped\n"},
       flagged=True, label="rubocop verdict softened in CI")

expect("swallowed-verdict",
       {"bin/ci.sh": "#!/usr/bin/env bash\nset -e\nbundle exec rspec\nbundle exec rubocop\n"},
       flagged=False, label="verdicts left intact")

# `|| true` on a non-verification command (cleanup) is legitimate and must not fire.
expect("swallowed-verdict",
       {"bin/ci.sh": "#!/usr/bin/env bash\nrm -rf tmp/cache || true\nbundle exec rspec\n"},
       flagged=False, label="|| true on cleanup is not a softened verdict")

# ---------------------------------------------------------------------------
# assertion-free-spec
# ---------------------------------------------------------------------------

expect("assertion-free-spec",
       {"spec/models/user_spec.rb":
        'require "rails_helper"\n'
        'RSpec.describe User do\n'
        '  it "creates a user" do\n'
        '    User.create!(email: "a@b.test")\n'
        '  end\n'
        'end\n'},
       flagged=True, label="example runs code but asserts nothing")

expect("assertion-free-spec",
       {"spec/models/user_spec.rb":
        'require "rails_helper"\n'
        'RSpec.describe User do\n'
        '  it "creates a user" do\n'
        '    expect(User.create!(email: "a@b.test")).to be_persisted\n'
        '  end\n'
        'end\n'},
       flagged=False, label="example with an expectation")

expect("assertion-free-spec",
       {"spec/models/user_spec.rb":
        'RSpec.describe User do\n'
        '  it { is_expected.to validate_presence_of(:email) }\n'
        'end\n'},
       flagged=False, label="one-liner is_expected")

# Shared examples delegate the assertion; flagging them would be a false positive.
expect("assertion-free-spec",
       {"spec/models/invoice_spec.rb":
        'RSpec.describe Invoice do\n'
        '  it "behaves like a soft-deletable record" do\n'
        '    it_behaves_like SoftDeletable\n'
        '  end\n'
        'end\n'},
       flagged=False, label="delegating to shared examples counts as asserting")

# An explicit placeholder is honest about proving nothing.
expect("assertion-free-spec",
       {"spec/models/user_spec.rb":
        'RSpec.describe User do\n'
        '  it "handles SSO" do\n    pending "not built yet"\n  end\n'
        'end\n'},
       flagged=False, label="pending example is a deliberate placeholder")

expect("assertion-free-spec",
       {"spec/models/user_spec.rb":
        'RSpec.describe User do\n  it "handles SSO" do\n  end\nend\n'},
       flagged=False, label="empty example body is a placeholder, not a false claim")

# Non-spec Ruby must never be scanned by this rule.
expect("assertion-free-spec",
       {"app/models/user.rb": 'class User\n  def it(x) = x\nend\n'},
       flagged=False, label="application code is out of scope")

# #1036. THE REPORTED CASE, verbatim in shape: an example whose only call is a helper named
# `expect_*` defined elsewhere in the file. The helper asserts -- proved downstream by mutation,
# removing the patterns it checks made both examples fail with its own message -- but bare
# `expect` could not match across the `_`, so the rule called a real assertion no assertion.
expect("assertion-free-spec",
       {"spec/requests/subpage_navigation_spec.rb":
        'RSpec.describe "subpages" do\n'
        '  def expect_a_way_back(path)\n'
        '    get path\n'
        '    expect(response).to have_http_status(:ok)\n'
        '  end\n'
        '  it "offers a way back from a contract" do\n'
        '    expect_a_way_back("/contracts/1")\n'
        '  end\n'
        'end\n'},
       flagged=False, label="a helper named expect_* counts as asserting")

# The `expects_*` spelling too -- \w* has to mean any suffix, not just a leading underscore.
expect("assertion-free-spec",
       {"spec/requests/nav_spec.rb":
        'RSpec.describe "nav" do\n'
        '  it "has a way back" do\n    expects_a_way_back("/x")\n  end\n'
        'end\n'},
       flagged=False, label="a helper named expects_* counts as asserting")

# THE NEGATIVE CONTROL, and the reason the widening above is a fix and not a deletion. Same file
# shape, same rule, one word different: the call does not name an assertion at all. Without this,
# `expect\w*` would be indistinguishable from matching any identifier -- a rule that cannot fail,
# which is the exact class this rule exists to catch.
expect("assertion-free-spec",
       {"spec/requests/nav_spec.rb":
        'RSpec.describe "nav" do\n'
        '  it "has a way back" do\n    do_something("/x")\n  end\n'
        'end\n'},
       flagged=True, label="a helper that names no assertion is still a finding")

# THE SECOND NEGATIVE CONTROL, and it exists because the first one did not do the job. `\w*` after
# `expect` has to stay a SUFFIX: the word boundary in front is what keeps `expect_a_way_back`
# (asserts) apart from `unexpected_thing` (does not). Widening to `\w*expect\w*` -- the obvious
# over-correction -- passes every other case in this file including `do_something`, because none of
# them contains the substring at all. Only a name that CONTAINS "expect" without starting with it
# can tell the two regexes apart, so without this case the widening would have been unfalsifiable.
expect("assertion-free-spec",
       {"spec/requests/nav_spec.rb":
        'RSpec.describe "nav" do\n'
        '  it "has a way back" do\n    unexpected_thing("/x")\n  end\n'
        'end\n'},
       flagged=True, label="a name merely CONTAINING expect is not an assertion")

# ---------------------------------------------------------------------------
# dead-env-var  (repo-wide)
# ---------------------------------------------------------------------------

expect("dead-env-var",
       {".env.example": "STRIPE_SECRET_KEY=sk_test\nUNUSED_TOKEN=abc\n",
        "app/models/payment.rb": 'class Payment\n  KEY = ENV["STRIPE_SECRET_KEY"]\nend\n'},
       flagged=True, label="documented key nothing reads", whole_repo=True)

expect("dead-env-var",
       {".env.example": "STRIPE_SECRET_KEY=sk_test\n",
        "app/models/payment.rb": 'class Payment\n  KEY = ENV.fetch("STRIPE_SECRET_KEY")\nend\n'},
       flagged=False, label="key read via ENV.fetch", whole_repo=True)

# A key may be consumed outside Ruby entirely -- narrowing the haystack to .rb is
# how this rule would produce false positives.
expect("dead-env-var",
       {".env.example": "DATABASE_URL=postgres://x\n",
        "config/deploy.yml": "env:\n  clear:\n    DATABASE_URL: postgres://prod\n"},
       flagged=False, label="key referenced from a non-Ruby file", whole_repo=True)

expect("dead-env-var",
       {".env.example": "# OPTIONAL_THING=1\nREAL=1\n",
        "config/application.rb": 'ENV["REAL"]\n'},
       flagged=False, label="commented-out key is not a declaration", whole_repo=True)


# ---------------------------------------------------------------------------
# invariants
# ---------------------------------------------------------------------------

CHECKS += 1
_root = _tree({"app/models/a.rb": "class A\nend\n"})
_findings, _coverage = sc.check_all(_root)
if "files" not in _coverage or _coverage["files"] < 1:
    FAILURES.append("check_all: coverage must report what it examined, so a clean "
                    "result over zero inputs cannot read as a pass")

CHECKS += 1
if sc.check_file(Path(tempfile.gettempdir()) / "definitely-not-here-164.rb",
                 Path(tempfile.gettempdir())):
    FAILURES.append("check_file: a missing file produced findings")


def run_selftest() -> int:
    print(f"ran {CHECKS} self-consistency assertion(s)")
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("every rule fires on a violation and stays silent on conforming code")
    return 0


if __name__ == "__main__":
    sys.exit(run_selftest())
