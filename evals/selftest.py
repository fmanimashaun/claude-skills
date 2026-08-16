#!/usr/bin/env python3
"""Prove every gate in gates.py actually fires -- and actually stays silent.

A gate library nobody tested is a claim, not a measurement. #156 exists because
this repo asserted effects it had never measured; shipping unverified gates would
repeat that mistake one level down.

Each rule gets at least two assertions:
  * a VIOLATING workspace that the rule must flag, and
  * a CONFORMING workspace that the rule must leave alone.

The second half is the one that matters most. A rule that flags everything looks
rigorous and is worthless -- it makes every arm fail equally, so the benchmark
reports "no difference" no matter how good the doctrine is.

Run:  python3 evals/selftest.py        (exit 0 = all gates behave)
Costs nothing. No API calls, no `claude` binary, no network.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import gates  # noqa: E402
import run  # noqa: E402  -- for RAILS_STACK_SKILLS, the staged-vs-measured check

# A Gemfile + initializer are what make the simple_form gate fair; most fixtures
# inherit them so the rule under test is the only variable.
CONVENTION = {
    "Gemfile": 'source "https://rubygems.org"\ngem "rails"\ngem "simple_form"\n',
    "config/initializers/simple_form.rb": "SimpleForm.setup { |c| c.wrappers }\n",
}

FAILURES: list[str] = []
CHECKS = 0


def workspace(files: dict[str, str]) -> Path:
    """Materialise a throwaway workspace from {relative path: contents}."""
    root = Path(tempfile.mkdtemp(prefix="gate-fixture-"))
    for relpath, content in files.items():
        target = root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def expect(rule: str, files: dict[str, str], *, flagged: bool, label: str) -> None:
    """Assert `rule` does (or does not) produce findings for `files`."""
    global CHECKS
    CHECKS += 1
    root = workspace(files)
    try:
        findings = gates.RULES[rule].check(root)  # type: ignore[operator]
    except Exception as exc:  # pragma: no cover - a raising gate is a bug
        FAILURES.append(f"{rule} / {label}: raised {exc!r}")
        return
    got = bool(findings)
    if got != flagged:
        want = "findings" if flagged else "silence"
        detail = "; ".join(str(f) for f in findings) or "(none)"
        FAILURES.append(f"{rule} / {label}: expected {want}, got: {detail}")


def report() -> int:
    print(f"ran {CHECKS} gate assertion(s)")
    if FAILURES:
        print(f"\n{len(FAILURES)} FAILED:")
        for failure in FAILURES:
            print(f"  - {failure}")
        return 1
    print("all gates behave as specified")
    return 0


# ---------------------------------------------------------------------------
# scoped-index
# ---------------------------------------------------------------------------

expect(
    "scoped-index",
    {"app/controllers/invoices_controller.rb":
        "class InvoicesController < ApplicationController\n"
        "  def index\n"
        "    @invoices = Invoice.all\n"
        "  end\n"
        "end\n"},
    flagged=True, label="Model.all with no Current scope",
)

expect(
    "scoped-index",
    {"app/controllers/invoices_controller.rb":
        "class InvoicesController < ApplicationController\n"
        "  def index\n"
        "    @invoices = Current.user.invoices.order(created_at: :desc)\n"
        "  end\n"
        "end\n"},
    flagged=False, label="scoped through Current.user (doctrine form)",
)

# The doctrine's own example, verbatim in shape, from auth-security.md:122.
expect(
    "scoped-index",
    {"app/controllers/projects_controller.rb":
        "class ProjectsController < ApplicationController\n"
        "  def index = @projects = Current.user.projects\n"
        "  private def set_project = @project = Current.user.projects.find(params[:id])\n"
        "end\n"},
    flagged=False, label="doctrine reference example (auth-security.md:122)",
)

# Non-model constants must not trip the rule. `Rails.application` / `Time.now`
# are not authorization holes, and flagging them would make the gate noise.
expect(
    "scoped-index",
    {"app/controllers/reports_controller.rb":
        "class ReportsController < ApplicationController\n"
        "  def index\n"
        "    @cutoff = Time.zone.now\n"
        "    @reports = Current.account.reports.where(created_at: ..@cutoff)\n"
        "  end\n"
        "end\n"},
    flagged=False, label="stdlib constants are not unscoped models",
)

expect(
    "scoped-index", {"README.md": "nothing here\n"},
    flagged=True, label="no controller written at all",
)

# ---------------------------------------------------------------------------
# simple-form-convention
# ---------------------------------------------------------------------------

expect(
    "simple-form-convention",
    {**CONVENTION,
     "app/views/invoices/_form.html.erb":
        "<%= form_with model: @invoice do |f| %>\n"
        "  <%= f.text_field :title %>\n"
        "<% end %>\n"},
    flagged=True, label="raw form_with despite project convention",
)

expect(
    "simple-form-convention",
    {**CONVENTION,
     "app/views/invoices/_form.html.erb":
        "<%= simple_form_for @invoice do |f| %>\n"
        "  <%= f.input :title %>\n"
        "<% end %>\n"},
    flagged=False, label="simple_form_for as mandated",
)

# Fairness precondition: with no Gemfile/initializer, form_with is correct stock
# Rails. The gate must refuse to judge rather than punish the agent.
expect(
    "simple-form-convention",
    {"app/views/invoices/_form.html.erb":
        "<%= form_with model: @invoice do |f| %>\n<% end %>\n"},
    flagged=True, label="refuses to judge when convention unestablished",
)

# ---------------------------------------------------------------------------
# no-inline-dark
# ---------------------------------------------------------------------------

expect(
    "no-inline-dark",
    {"app/components/ui/card.html.erb":
        '<div class="bg-surface dark:bg-slate-800 text-body">\n</div>\n'},
    flagged=True, label="inline dark: utility in a component",
)

expect(
    "no-inline-dark",
    {"app/components/ui/card.html.erb":
        '<div class="bg-surface text-body border-subtle">\n</div>\n'},
    flagged=False, label="role tokens only",
)

# The token layer legitimately re-points roles under .dark. That file is not in
# VIEW_GLOBS, so a stylesheet using `dark:` must not be flagged.
expect(
    "no-inline-dark",
    {"app/assets/stylesheets/application.css":
        '@layer base { .dark { --primary: oklch(0.7 0.1 250); } }\n'
        '.dark\\:x { color: red; }\n'},
    flagged=False, label="token layer may re-point under .dark",
)

# `dark:` must not match inside an unrelated word or a URL-ish fragment.
expect(
    "no-inline-dark",
    {"app/views/pages/home.html.erb":
        '<p>See the <a href="https://x.test/dark:mode">note</a></p>\n'
        '<p>Colours: darkgreen is a CSS keyword.</p>\n'},
    flagged=True, label="known limitation: literal dark: text is still flagged",
)

# ---------------------------------------------------------------------------
# no-literal-color
# ---------------------------------------------------------------------------

expect(
    "no-literal-color",
    {"app/components/ui/button.html.erb":
        '<button style="background:#0077CC">Go</button>\n'},
    flagged=True, label="literal hex in a component",
)

expect(
    "no-literal-color",
    {"app/components/ui/button.html.erb":
        '<button class="bg-primary text-on-primary">Go</button>\n'},
    flagged=False, label="role tokens only",
)

# brand.md:87 -- Ui::Logo is the ONLY component permitted literal colours. This
# is the assertion that caught the naive version of this rule: without the
# carve-out the gate flags our own reference implementation.
expect(
    "no-literal-color",
    {"app/components/ui/logo.html.erb":
        '<svg><path fill="#0077CC"/><path fill="#00A3FF"/><path fill="#00D4FF"/></svg>\n'},
    flagged=False, label="Ui::Logo exception (brand.md:87)",
)

# An ERB comment is discussion, not rendered output.
expect(
    "no-literal-color",
    {"app/components/ui/card.html.erb":
        '<%# palette reference: #0077CC cerulean %>\n'
        '<div class="bg-surface"></div>\n'},
    flagged=False, label="hex inside an ERB comment is not a literal colour",
)

# A `#` comment in a RUBY component file is discussion too. Caught in review:
# read_lines() promised Ruby comment handling and only blanked ERB comments, so
# a palette note in a .rb file was reported as a violation -- a false regression.
expect(
    "no-literal-color",
    {"app/components/ui/card.rb":
        "class Ui::Card < ViewComponent::Base\n"
        "  # brand cerulean is #0077CC -- do not inline it, use --primary\n"
        "  def classes = \"bg-surface text-body\"\n"
        "end\n"},
    flagged=False, label="hex inside a Ruby comment is not a literal colour",
)

# ...but a hex inside a STRING is real. This is why the comment stripper tracks
# quote state instead of splitting on the first '#' -- the token we hunt for IS
# a '#', so a naive split would delete every violation it was meant to find.
expect(
    "no-literal-color",
    {"app/components/ui/card.rb":
        "class Ui::Card < ViewComponent::Base\n"
        '  def style = "background:#0077CC"\n'
        "end\n"},
    flagged=True, label="hex inside a Ruby string is still a violation",
)

# Ruby comment stripping must NOT apply to .erb: there a bare '#' is HTML text,
# and blanking to end-of-line would hide the violation that follows it.
expect(
    "no-literal-color",
    {"app/components/ui/card.html.erb":
        '<p>Invoice #42</p>\n'
        '<div style="color:#0077CC"></div>\n'},
    flagged=True, label="'#' as ERB text must not mask a later violation",
)

# The exemption is for the COMPONENT Ui::Logo, not for any file named logo.
# Matching the path loosely made this a one-line bypass.
expect(
    "no-literal-color",
    {"app/views/shared/logo.html.erb":
        '<svg><path fill="#0077CC"/></svg>\n'},
    flagged=True, label="a stray file named logo/ is NOT exempt",
)

expect(
    "no-literal-color",
    {"app/components/ui/logo_component.html.erb":
        '<svg><path fill="#0077CC"/></svg>\n'},
    flagged=False, label="canonical Ui::Logo component path is exempt",
)

# Same Ruby-comment reasoning for the dark: rule.
expect(
    "no-inline-dark",
    {"app/components/ui/card.rb":
        "class Ui::Card < ViewComponent::Base\n"
        "  # never write dark:bg-slate-800 here; roles re-point under .dark\n"
        "  def classes = \"bg-surface\"\n"
        "end\n"},
    flagged=False, label="dark: inside a Ruby comment is not a violation",
)

# ---------------------------------------------------------------------------
# job-idempotent
# ---------------------------------------------------------------------------

expect(
    "job-idempotent",
    {"app/jobs/charge_job.rb":
        "class ChargeJob < ApplicationJob\n"
        "  def perform(order)\n"
        "    Payment.create!(order: order, amount: order.total)\n"
        "  end\n"
        "end\n"},
    flagged=True, label="unguarded create on every retry",
)

# The doctrine's own signature (jobs-and-realtime.md:28) passes a RECORD, not an
# id. Issue #156 asked for an ids-only gate; this assertion is what proves that
# spec wrong -- an ids-only rule would flag this conforming job.
expect(
    "job-idempotent",
    {"app/jobs/charge_job.rb":
        "class ChargeJob < ApplicationJob\n"
        "  def perform(order)  # pass records, not ids: GlobalID (de)serializes\n"
        "    return if order.paid?\n"
        "    Payment.find_or_create_by!(order: order) { |p| p.amount = order.total }\n"
        "  end\n"
        "end\n"},
    flagged=False, label="record argument + idempotence guard (doctrine form)",
)

expect(
    "job-idempotent",
    {"app/jobs/charge_job.rb": "class ChargeJob < ApplicationJob\nend\n"},
    flagged=True, label="no perform method",
)

expect(
    "job-idempotent", {"README.md": "nothing\n"},
    flagged=True, label="no job written at all",
)

# ---------------------------------------------------------------------------
# spec-accompanies-behavior
# ---------------------------------------------------------------------------

expect(
    "spec-accompanies-behavior",
    {"app/models/concerns/auditable.rb":
        "module Auditable\n  extend ActiveSupport::Concern\nend\n"},
    flagged=True, label="concern with no spec",
)

expect(
    "spec-accompanies-behavior",
    {"app/models/concerns/auditable.rb":
        "module Auditable\n  extend ActiveSupport::Concern\nend\n",
     "spec/models/concerns/auditable_spec.rb":
        'require "rails_helper"\nRSpec.describe Auditable do\nend\n'},
    flagged=False, label="matching spec by filename",
)

# A spec that exercises the concern through its including model is still proof.
expect(
    "spec-accompanies-behavior",
    {"app/models/concerns/soft_deletable.rb":
        "module SoftDeletable\n  extend ActiveSupport::Concern\nend\n",
     "spec/models/invoice_spec.rb":
        'require "rails_helper"\n'
        'RSpec.describe Invoice do\n'
        '  it_behaves_like SoftDeletable\n'
        'end\n'},
    flagged=False, label="covered by a spec that references the module",
)

# ---------------------------------------------------------------------------
# Library invariants
# ---------------------------------------------------------------------------

CHECKS += 1
try:
    gates.run_rules(workspace({}), ["no-such-rule"])
    FAILURES.append("run_rules: a typo'd rule name scored a silent pass")
except KeyError:
    pass

CHECKS += 1
try:
    gates.iter_files(Path(tempfile.gettempdir()) / "definitely-not-here-156", ("**/*",))
    FAILURES.append("iter_files: a nonexistent workspace reported 0 files instead of raising")
except NotADirectoryError:
    pass

# Every rule must cite doctrine. An uncited rule is taste.
for name, rule in gates.RULES.items():
    CHECKS += 1
    if not rule.doctrine or "skills/" not in rule.doctrine:
        FAILURES.append(f"{name}: cites no doctrine file under skills/")


# --------------------------------------------------------------------------
# stimulus-discipline (#646) -- the case that finally measures the hotwire skill the real arm
# has been staging all along.

_GOOD_STIMULUS = (
    'import { Controller } from "@hotwired/stimulus"\\nexport default class extends Controller {\\n  static targets = ["button"]\\n  static values = { text: String }\\n  copy() {\\n    navigator.clipboard.writeText(this.textValue)\\n    this.buttonTarget.textContent = "Copied"\\n  }\\n}\\n'
)

expect(
    "stimulus-discipline",
    {'app/javascript/controllers/copy_controller.js': _GOOD_STIMULUS},
    flagged=False, label="targets declared, no document query, no markup in JS (doctrine form)",
)

expect(
    "stimulus-discipline",
    {'app/javascript/controllers/copy_controller.js':
        'import { Controller } from "@hotwired/stimulus"\n'
        'export default class extends Controller {\n'
        '  static targets = ["button"]\n'
        '  copy() { document.querySelector("#invoice-number").textContent }\n'
        '}\n'},
    flagged=True, label="document.querySelector instead of a target (stimulus.md:321)",
)

expect(
    "stimulus-discipline",
    {'app/javascript/controllers/copy_controller.js':
        'import { Controller } from "@hotwired/stimulus"\n'
        'export default class extends Controller {\n'
        '  static targets = ["button"]\n'
        '  copy() { this.buttonTarget.innerHTML = "<em>Copied</em>" }\n'
        '}\n'},
    flagged=True, label="builds markup in the controller (stimulus.md:319)",
)

expect(
    "stimulus-discipline",
    {'app/javascript/controllers/copy_controller.js':
        'import { Controller } from "@hotwired/stimulus"\n'
        'export default class extends Controller {\n'
        '  static targets = ["button"]\n'
        '  connect() { document.addEventListener("turbo:load", () => this.reset()) }\n'
        '}\n'},
    flagged=True, label="global turbo:load listener (stimulus.md:322)",
)

expect(
    "stimulus-discipline",
    {'app/javascript/controllers/copy_controller.js':
        'import { Controller } from "@hotwired/stimulus"\n'
        'export default class extends Controller {\n'
        '  copy() { navigator.clipboard.writeText("x") }\n'
        '}\n'},
    flagged=True, label="no static targets, so the HTML is not the API (stimulus.md:314)",
)

# THE SCAFFOLD'S OWN CONTROLLER MUST PASS. A gate that fails what we ship as the correct example
# is a wrong gate, and it would manufacture a false regression against the real arm -- the rule
# this file's header states, and which #156 caught twice while it was being authored.
expect(
    "stimulus-discipline",
    {"app/javascript/controllers/pager_controller.js":
        'import { Controller } from "@hotwired/stimulus"\n'
        'export default class extends Controller {\n'
        '  static targets = ["panel"]\n'
        '  static values = { open: Boolean }\n'
        '  toggle() { this.openValue = !this.openValue }\n'
        '  openValueChanged() { this.panelTarget.hidden = !this.openValue }\n'
        '}\n'},
    flagged=False, label="the shipped disclosure controller's own shape",
)

# The scaffold's files are NOT the agent's work and must never be graded as it.
expect(
    "stimulus-discipline",
    {"app/javascript/controllers/index.js": 'application.register("disclosure", X)\n',
      "app/javascript/controllers/disclosure_controller.js": _GOOD_STIMULUS},
    flagged=True, label="only scaffold files present -- the task was not attempted",
)

# --------------------------------------------------------------------------
# EVERY STAGED SKILL IS MEASURED (#646)
#
# `hotwire` sat in RAILS_STACK_SKILLS for the whole life of this benchmark with no case exercising
# it. That is worse than an untested skill: its tokens occupied the real arm's context and
# contributed no signal, so a win or a loss was attributed to the other two. The `weak` arm exists
# to stop us mistaking "any instructions help" for "our doctrine helps"; a staged-but-unmeasured
# skill undermines the same rigour from the other side.
#
# Prose would not have caught it -- the rule was never written down at all. This is the enforcement.
CHECKS += 1
_suite = json.loads((HERE / "suite.json").read_text(encoding="utf-8"))
_tagged = {t for case in _suite["cases"] for t in case.get("tags", [])}
_unmeasured = [skill for skill in run.RAILS_STACK_SKILLS if skill not in _tagged]
if _unmeasured:
    FAILURES.append(
        f"staged in the `real` arm but exercised by no case: {sorted(_unmeasured)} -- their tokens "
        f"dilute the arm and their doctrine is unmeasured. Add a case tagged with the skill name, "
        f"or stop staging it.")

# Every rule must be exercised above, in both directions.
_ASSERTED = {
    "scoped-index", "simple-form-convention", "no-inline-dark",
    "no-literal-color", "job-idempotent", "spec-accompanies-behavior",
    "stimulus-discipline",
}
CHECKS += 1
_missing = set(gates.RULES) - _ASSERTED
if _missing:
    FAILURES.append(f"rules with no selftest coverage: {sorted(_missing)}")


if __name__ == "__main__":
    sys.exit(report())
