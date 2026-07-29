#!/usr/bin/env python3
"""Build the throwaway Rails-ish workspace each benchmark run writes into.

WHY A SCAFFOLD IS NOT OPTIONAL
------------------------------
Three separate failure modes it removes:

1. ISOLATION. A run must never execute inside this repo. Our own CLAUDE.md is
   maintainer doctrine; the agent would read it in every arm, contaminating all
   of them identically and quietly flattening the result toward "no difference".
   Every run gets a fresh directory with no CLAUDE.md and no .claude/ anywhere
   in its ancestry.

2. SOMEWHERE TO WRITE. "Add a scoped index action" is ungradeable against an
   empty directory -- the agent has to invent a whole app, and file paths become
   unpredictable, so the gates cannot find what to read.

3. FAIRNESS. Some doctrine is conditional. `form_with` is correct stock Rails;
   simple_form is right only in a project that adopted it. So the scaffold ships
   the Gemfile entry and initializer that establish that convention. Without
   them the simple-form gate would punish an agent for writing correct Rails,
   and gates.check_simple_form_convention deliberately refuses to judge.

The skeleton is deliberately thin. It is a believable project, not a real app:
enough context to make one task well-posed, not so much that it answers the task.

Stdlib only.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass


# Note what is absent as much as what is present: no CLAUDE.md, no .claude/,
# no AGENTS.md. Nothing here nudges the agent toward or away from our doctrine.
FILES: dict[str, str] = {
    "README.md": """\
# Ledger

Small internal invoicing app. Multi-tenant: every record belongs to a `User`,
and requests are scoped through `Current`.

Conventions already in force in this codebase:

- **Forms** use `simple_form` (installed, initializer configured).
- **Styling** consumes semantic role tokens from `app/assets/stylesheets/application.css`.
  Components never carry literal colours and never use inline `dark:` utilities --
  roles re-point under `.dark` instead.
- **Tests** are RSpec.
""",

    "Gemfile": """\
source "https://rubygems.org"

gem "rails", "~> 8.1"
gem "simple_form"
gem "propshaft"
gem "solid_queue"

group :development, :test do
  gem "rspec-rails"
  gem "factory_bot_rails"
end
""",

    "config/initializers/simple_form.rb": """\
# Configured wrappers -- forms in this app go through simple_form, not form_with.
SimpleForm.setup do |config|
  config.wrappers :default, class: "form-field" do |b|
    b.use :html5
    b.use :label
    b.use :input, class: "input"
    b.use :error, wrap_with: { class: "form-error" }
  end
  config.default_wrapper = :default
end
""",

    "app/models/current.rb": """\
class Current < ActiveSupport::CurrentAttributes
  attribute :user
end
""",

    "app/models/user.rb": """\
class User < ApplicationRecord
  has_many :invoices, dependent: :destroy
end
""",

    "app/models/invoice.rb": """\
class Invoice < ApplicationRecord
  belongs_to :user

  enum :status, { draft: 0, sent: 1, paid: 2 }

  validates :reference, presence: true
  validates :amount_cents, numericality: { greater_than_or_equal_to: 0 }
end
""",

    "app/models/application_record.rb": """\
class ApplicationRecord < ActiveRecord::Base
  primary_abstract_class
end
""",

    "app/controllers/application_controller.rb": """\
class ApplicationController < ActionController::Base
  before_action :set_current_user

  private

  def set_current_user
    Current.user = User.find_by(id: session[:user_id])
  end
end
""",

    "app/jobs/application_job.rb": """\
class ApplicationJob < ActiveJob::Base
  retry_on ActiveRecord::Deadlocked, attempts: 3
end
""",

    # Role tokens live here so a component task has real names to consume, and
    # so `dark:` handling is demonstrated in the token layer -- which is exactly
    # where doctrine permits it.
    "app/assets/stylesheets/application.css": """\
@import "tailwindcss";

@theme {
  --color-brand-500: oklch(0.58 0.17 245);
  --color-brand-600: oklch(0.50 0.17 245);
  --color-slate-50:  oklch(0.98 0.005 250);
  --color-slate-900: oklch(0.21 0.02 250);
}

/* Semantic role layer. Components bind to these, never to the primitives above. */
:root {
  --surface: var(--color-slate-50);
  --surface-raised: white;
  --body: var(--color-slate-900);
  --muted: oklch(0.55 0.02 250);
  --primary: var(--color-brand-500);
  --primary-hover: var(--color-brand-600);
  --on-primary: white;
  --border-subtle: oklch(0.90 0.01 250);
}

/* Dark mode is one re-point here. Components stay put -- no inline dark:. */
.dark {
  --surface: var(--color-slate-900);
  --surface-raised: oklch(0.26 0.02 250);
  --body: var(--color-slate-50);
  --border-subtle: oklch(0.32 0.02 250);
}

@utility bg-surface { background-color: var(--surface); }
@utility bg-surface-raised { background-color: var(--surface-raised); }
@utility text-body { color: var(--body); }
@utility text-muted { color: var(--muted); }
@utility bg-primary { background-color: var(--primary); }
@utility text-on-primary { color: var(--on-primary); }
@utility border-subtle { border-color: var(--border-subtle); }
""",

    "app/views/layouts/application.html.erb": """\
<!DOCTYPE html>
<html>
  <head>
    <title>Ledger</title>
    <%= stylesheet_link_tag "application" %>
  </head>
  <body class="bg-surface text-body">
    <%= yield %>
  </body>
</html>
""",

    "spec/rails_helper.rb": """\
require "spec_helper"
require "rspec/rails"

RSpec.configure do |config|
  config.use_transactional_fixtures = true
  config.infer_spec_type_from_file_location!
end
""",

    "spec/spec_helper.rb": """\
RSpec.configure do |config|
  config.expect_with(:rspec) { |c| c.syntax = :expect }
  config.disable_monkey_patching!
end
""",

    "config/routes.rb": """\
Rails.application.routes.draw do
  resources :invoices
  root "invoices#index"
end
""",
}


def build(destination: Path | None = None) -> Path:
    """Materialise the skeleton. Returns the workspace root."""
    root = destination or Path(tempfile.mkdtemp(prefix="ledger-bench-"))
    root.mkdir(parents=True, exist_ok=True)
    for relpath, content in FILES.items():
        target = root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    assert_isolated(root)
    return root


def assert_isolated(root: Path) -> None:
    """Refuse to run from a workspace that inherits outside context.

    Contamination here is insidious because it is *uniform*: every arm reads the
    same stray CLAUDE.md, so nothing looks broken -- the result just drifts toward
    "no difference" and we conclude the doctrine does nothing.

    The distinction that matters is user config vs project context:

      * `CLAUDE.md` in ANY ancestor is auto-discovered memory. Fatal.
      * `.claude/` in a *project* ancestor carries settings, commands, and agents.
        Fatal. But the home directory's own `~/.claude/` is user config, and it is
        an unavoidable ancestor of any temp dir under the user profile -- so it is
        exempt. (`--setting-sources ""` in run.py already excludes user settings,
        which is what would otherwise enable installed plugins.)
      * `~/.claude/skills/` is the exception to the exemption: skills-dir plugins
        auto-load into every session, so a skill parked there would load in all
        three arms. Fatal if non-empty.
    """
    home = Path.home().resolve()

    for ancestor in [root, *root.parents]:
        memory = ancestor / "CLAUDE.md"
        if memory.is_file():
            raise RuntimeError(
                f"workspace is not isolated: {memory} is auto-discovered as memory "
                f"and would load into every arm, flattening the result toward "
                f"'no difference'. Use a workspace outside any Claude Code project."
            )
        project_config = ancestor / ".claude"
        if project_config.is_dir() and ancestor.resolve() != home:
            raise RuntimeError(
                f"workspace is not isolated: {project_config} would supply project "
                f"settings/commands/agents to every arm. Use a workspace outside "
                f"any Claude Code project."
            )

    skills_dir = home / ".claude" / "skills"
    if skills_dir.is_dir() and any(skills_dir.iterdir()):
        raise RuntimeError(
            f"{skills_dir} is non-empty: skills-dir plugins auto-load into every "
            f"session, so those skills would be present in all three arms and the "
            f"comparison would be meaningless. Move them aside for the run."
        )


def main(argv: list[str]) -> int:
    dest = Path(argv[1]).resolve() if len(argv) > 1 else None
    if dest and dest.exists():
        shutil.rmtree(dest)
    root = build(dest)
    print(root)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
