# Style — how Rails code should read

The rest of this skill says what to build. This says **how it should read**, which had no doctrine at
all before #97.

**Source and attribution.** These conventions come from **[37signals' `STYLE.md`][style]** in
[basecamp/fizzy][fizzy] — a production Kanban app written by the people who make Rails. It is licensed
"O'Saasy" (MIT plus a no-competing-hosted-SaaS clause), so quoting and adapting it here is permitted;
**attribute 37signals** wherever a rule is lifted. Every rule below is quoted from that file, and every
**adopt / adapt** decision with its reason is recorded, because inheriting a convention silently is how
a project ends up with two styles and an argument.

[style]: https://github.com/basecamp/fizzy/blob/main/STYLE.md
[fizzy]: https://github.com/basecamp/fizzy

**What the linter does about all this: nothing, and that is deliberate.** We mandate
`rubocop-rails-omakase`, which *"disables all cops by default"* at the department level (`Layout`,
`Lint`, `Metrics`, `Naming`, `Style`, …) and re-enables a short selected list. So none of the rules
below is machine-enforced, and none of them is machine-*contradicted* either. They are review-time
conventions, and the sections that could have collided with a cop say so explicitly.

**One provenance correction worth making, because it is easy to get backwards.**
`rubocop-rails-omakase` is **not** 37signals' config. Its README describes it as *"the idiosyncratic
aesthetic sensibilities of Rails' creator"*, the gemspec author is David Heinemeier Hansson, and it
lives under the **`rails`** org, shipped with new Rails apps. So: DHH's personal style, adopted by the
framework — related to fizzy's house style but not the same artifact, and not interchangeable in a
citation.

---

## 1. Conditional returns — prefer expanded conditionals (ADAPTED)

> *"In general, we prefer to use expanded conditionals over guard clauses… This is because guard
> clauses can be hard to read, especially when they are nested."*

```ruby
# Their "bad"
def todos_for_new_group
  ids = params.require(:todolist)[:todo_ids]
  return [] unless ids
  @bucket.recordings.todos.find(ids.split(","))
end

# Their "good"
def todos_for_new_group
  if ids = params.require(:todolist)[:todo_ids]
    @bucket.recordings.todos.find(ids.split(","))
  else
    []
  end
end
```

**Two named exceptions, and they are first-class rather than footnotes** — a guard clause is right
*"when the return is right at the beginning of the method"* and *"when the main method body is not
trivial and involves several lines of code."* Between them those cover most of the cases where a guard
actually reads better, which is why this rule is livable.

**This is genuinely contrary to prevailing Ruby advice, and pretending otherwise would be dishonest.**
Stock RuboCop enables `Style/GuardClause` **by default** (*"Checks for conditionals that can be replaced
with guard clauses"*), keyed to the community style guide's *Nested Conditionals* rule: *"Avoid use of
nested conditionals for flow of control. Prefer a guard clause when you can assert invalid data."*
The pattern fizzy labels "bad" is the one the community guide labels good.

**ADAPTED, and here is exactly how.** We adopt the preference and its two exceptions, and we add one
rule of our own:

- **Do not "fix" an existing guard clause, and never reject a change solely for using one.** A style
  preference that generates review churn costs more than it earns, and an agent applying this
  dogmatically will produce `if`/`else` where a guard was clearer. Prefer expanded conditionals when
  *writing new code*; leave working code alone.
- **No linter conflict to manage.** `Style/GuardClause` is not mentioned anywhere in
  `rubocop-rails-omakase`, and with `Style` disabled at the department level it is **off** — so
  RuboCop will not push an author either way. A project that re-enables the `Style` department inherits
  the stock cop and *will* fight this rule; that is the moment to decide, not before.
- **Our own doctrine already contains a compliant guard clause.** `jobs-and-realtime.md` says to make
  jobs idempotent with `return if order.paid?` at the top of `perform` — which is exception #1, not a
  violation. Worth knowing before someone "corrects" it.

## 2. Method ordering (ADOPTED)

> *"1. `class` methods 2. `public` methods with `initialize` at the top. 3. `private` methods"*

Adopted unchanged — mechanical, uncontroversial, and it makes a class skimmable in one pass.

## 3. Invocation order (ADOPTED)

> *"We order methods vertically based on their invocation order. This helps us to understand the flow
> of the code."*

```ruby
class SomeClass
  def some_method
    method_1
    method_2
  end

  private
    def method_1
      method_1_1
      method_1_2
    end

    def method_1_1
    end

    def method_1_2
    end

    def method_2
    end
end
```

Adopted. It reads top-down like a call tree, and it composes with §2: ordering applies *within* the
public and private groups, it does not override them.

## 4. To bang or not to bang (ADOPTED)

> *"As a general rule, we only use `!` for methods that have a correspondent counterpart without `!`.
> In particular, we don't use `!` to flag destructive actions. There are plenty of destructive methods
> in Ruby and Rails that do not end with `!`."*

Adopted, and it is a **correction to a widespread misreading**, not merely a preference: `!` does not
mean "dangerous" or "destructive". `destroy`, `delete_all` and `update_column` are all destructive and
none carries a bang. The bang marks *"this is the surprising sibling of the method next to it"* —
`save`/`save!`, `find_by`/`find_by!`. **No counterpart, no bang.**

## 5. Visibility modifiers (ADOPTED)

> *"We don't add a newline under visibility modifiers, and we indent the content under them."*

```ruby
class SomeClass
  def some_method
  end

  private
    def some_private_method_1
    end

    def some_private_method_2
    end
end
```

> *"If a module only has private methods, we mark it `private` at the top and add an extra new line
> after but don't indent."*

```ruby
module SomeModule
  private

  def some_private_method
  end
end
```

Adopted, both halves. **The linter position is unusually well documented here**, and it corroborates
the exception rather than fighting it: `rubocop-rails-omakase` carries

```yaml
Layout/IndentationConsistency:
  Enabled: false
  EnforcedStyle: indented_internal_methods
```

with the comment *"Method definitions after `private` or `protected` isolated calls need one extra level
of indentation. We break this rule in context, though, e.g. for private-only concerns, so we leave it
disabled."* So the style matching this section is **pre-declared** in the config we already mandate, and
the reason it is switched off is precisely the private-only-module case above. A project that wants this
enforced only has to flip `Enabled: true`.

## 6. CRUD controllers — a new resource, not a custom action (ALREADY OURS, now cited)

> *"We model web endpoints as CRUD operations on resources (REST). When an action doesn't map cleanly
> to a standard CRUD verb, we introduce a new resource rather than adding custom actions."*

```ruby
# Bad — custom verbs bolted onto the resource
resources :cards do
  post :close
  post :reopen
end
```

```ruby
# Good — closure is the thing being created and destroyed
resources :cards do
  resource :closure
end
```

**`controllers-routing.md` §1 already says this** — *"Prefer another **resource over a custom action**…
never a bespoke non-REST verb sprawl"* — so this is canonical practice **confirming** existing doctrine
rather than new material. Recorded because a rule that survives contact with a production app by the
framework's own authors deserves the citation.

One difference, kept deliberately: our version allows *"or at least a `member` route"* as a fallback.
Fizzy offers no such escape hatch. We keep ours — a `member` route is a smaller sin than a fake
resource invented to satisfy a rule — but the **preference order is theirs**: new resource first.

## 7. Controller ↔ model interactions (ALREADY OURS, now cited and sharpened)

> *"we favor a [vanilla Rails] approach with thin controllers directly invoking a rich domain model. We
> don't use services or other artifacts to connect the two."*

```ruby
class Cards::CommentsController < ApplicationController
  def create
    @comment = @card.comments.create!(comment_params)   # plain AR is fine
  end
end

class Cards::GoldnessesController < ApplicationController
  def create
    @card.gild                                          # intention-revealing model API
  end
end
```

**`models.md` §7 already says "No service-object layer by default."** What it lacks is the nuance that
makes the rule workable, so adopt this half too:

> *"When justified, it is fine to use services or form objects, but don't treat those as special
> artifacts."*

That is the operative sentence. The rule is **not** "services are forbidden" — it is "a service is an
ordinary object you reach for when it earns its place, not an architectural layer every verb must pass
through." `Signup.new(email_address: …).create_identity` is fine. `app/services/` as the mandatory home
for all business logic is not.

## 8. Run async operations in jobs — `_later` and `_now` (ADOPTED)

> *"we write shallow job classes that delegate the logic itself to domain models"*
> *"We typically use the suffix `_later` to flag methods that enqueue a job."*
> *"A common scenario is having a model class that enqueues a job that, when executed, invokes some
> method in that same class. In this case, we use the suffix `_now` for the regular synchronous
> method."*

```ruby
module Event::Relaying
  extend ActiveSupport::Concern

  included do
    after_create_commit :relay_later
  end

  def relay_later
    Event::RelayJob.perform_later(self)
  end

  def relay_now
    # the actual work — on the MODEL, not in the job
  end
end

class Event::RelayJob < ApplicationJob
  def perform(event)
    event.relay_now
  end
end
```

Adopted, and this is the most immediately useful rule in the file because it settles a question every
Rails app re-litigates: **where does the logic live?** On the model. The job is a two-line adapter whose
only job is to move execution off the request.

- **`_later` names the enqueuing method**, so a call site reads `relay_later` and you know it returns
  immediately without opening the file.
- **`_now` is scoped to the callback-into-self case** — the pair `relay_later`/`relay_now` on one model.
  It is not a suffix for every synchronous method in the app, and generalising it that far would be a
  misreading of the source.
- **`jobs-and-realtime.md`'s existing rules still apply on top**: idempotent always, one job one
  responsibility, and `perform_later` inside a transaction enqueues after commit.
- Note our own `models.md` already uses `after_create_commit :send_welcome_email_later` in an example —
  incidentally consistent, but it was never stated as a rule until now.

---

## What we did NOT take

Nothing in `STYLE.md` was rejected. Two of its eight conventions (§6, §7) turned out to be doctrine we
already had, which is the more interesting result — it means the "vanilla Rails, no service layer, REST
resources over custom actions" posture this skill has prescribed all along is what Basecamp actually
ships, not our inference.

**Two divergences from 37signals live elsewhere and are deliberate, not oversights** (see EPIC #96):
they use **Minitest + Capybara** where we mandate pure **RSpec**, and they hand-write **vanilla CSS**
where we mandate **Tailwind v4 with `@theme` tokens**. Those are recorded decisions with reasons, not
accidental inconsistencies — and they are the reason this file sticks to *how code reads* rather than
claiming fizzy validates our whole stack.
