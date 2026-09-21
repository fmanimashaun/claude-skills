# Directory structure — the same folder name in every layer

`rails-flow` gates what is *in* a file. Nothing said where a file should live, so nothing drifted —
**a flat `app/controllers` root is not a violation, it is an absence.** That is why this is doctrine
first and a gate second.

## The principle

> Open any layer — `app/models`, `app/controllers`, `app/views`, `app/jobs` — descend into the
> folder named for the flow you are working on, and find that layer's part of it. **The same folder
> name in every layer.**

## What happens without it, measured

A mature Rails 8 app built with this toolchain (#1072), domain names generalised:

| layer | flat at root | namespaced dirs | total |
|---|---|---|---|
| models | 58 | 18 | 144 |
| controllers | **48** | 6 | 64 |
| views | 0 | 51 | 132 |
| components | 0 | **1** | 61 |
| jobs | **12** | 0 | 12 |
| `javascript/controllers` | **22** | 0 | 22 |
| helpers | **6** | 0 | 6 |
| mailers | **4** | 0 | 4 |

Counted on one commit with `git ls-tree -r --name-only <ref> -- app/<layer>`: *flat at root* is the
paths with no `/` left after the layer prefix, *namespaced dirs* the distinct first segments of the
rest. Re-measure before quoting these anywhere — they are one app on one day, and the first version
of this table was quoted from a stale draft and was wrong in three cells.

**Read across the rows, not down: no two layers agree with each other.**

Models grew 18 domain namespaces because a model's path binds only to its class name — it is free,
so it drifted toward the domain naturally. Controllers stayed flat because a controller's path binds
to its URL and grouping *looks* like it rewrites every route. Views have 51 directories, but one per
**controller**, not per domain — Rails forces that, and it is not organisation. Components have
exactly one directory holding all 61 files: the same flatness, one level down. And Stimulus —
`app/javascript/controllers`, 22 files, all flat — is the **largest flat layer after models and
controllers**, and the easiest to overlook, because a per-layer audit that lists only `app/*/` never
descends into `app/javascript`.

The cost is the thing worth fixing: **for any single flow, its job, its controller, its views and
its models sit in four unrelated places, and no layer tells you where the others are.**

## Which layers are free, and which are constrained

- **models, jobs, mailers, services, components** — **free.** The path binds to the class name only.
  Group by domain directly: `app/models/billing/invoice.rb` → `Billing::Invoice`.
- **controllers** — **constrained by URL**, and this is the one people get wrong.
- **views** — they follow their controller by Rails' own lookup. They move as a *consequence*, never
  independently.
- **specs** — mirror whichever layer they test.

## Controllers: `scope module:` is the lever, and we already document it

The belief that grouping controllers rewrites URLs is true of `namespace` and false of
`scope module:`. [controllers-routing.md](controllers-routing.md) states the mechanism:

```ruby
namespace :billing do
  resources :invoices        # /billing/invoices, billing_invoices_path   URLs CHANGE
end

scope module: :billing do
  resources :invoices        # /invoices, invoices_path                   URLs IDENTICAL
end                          # both -> Billing::InvoicesController
```

**What was missing is not the API but the instruction to reach for it**: `scope module:` decouples
file location from URL, which is exactly what a project with a settled URL design needs in order to
group controllers by domain.

## The safety argument, because it is what makes the move tractable

**Request specs drive URLs. URLs are invariant under `scope module:`. So an existing request-spec
suite is the regression harness for the restructure.**

On the app above that is **100 files in `spec/requests/`** that must pass **unchanged** — and a diff
touching that directory is itself the signal that something went wrong. It turns a frightening
**180-file** change — the 48 controllers plus the 132 views that move with them — into a verifiable
one, and it is the step teams do not reach on their own.

## Choose the taxonomy once

**The taxonomy is chosen once and reused in every layer.** Where a project already has namespaces in
its freest layer — usually models — **that is the taxonomy**: it was arrived at by use rather than
by design. Inventing a second one for controllers is how the layers end up disagreeing in a *new*
way, which is worse than the flat root you started with.

## A worked example, because the rule alone is not actionable

One domain, taken from the measured app. `cards` **already has a namespace in models** — it was
arrived at by use — and four other layers ignore it.

**Before.** The same domain in seven places, and no layer tells you about the others:

```
app/models/cards/           export_row  geometry  intake  open  photograph  render
app/models/card.rb                      # same domain, flat
app/models/card_production.rb           # same domain, flat
app/controllers/card_requests_controller.rb
app/controllers/card_runs_controller.rb # flat
app/views/card_requests/  app/views/card_runs/    # one dir per CONTROLLER, not per domain
app/jobs/generate_card_batch_job.rb     # flat
```

**After.** The taxonomy is `cards`, because models already said so:

```
app/models/cards/          card.rb  production.rb  export_row.rb  geometry.rb
                           intake.rb  open.rb  photograph.rb  render.rb
app/controllers/cards/     card_requests_controller.rb  card_runs_controller.rb
app/views/cards/card_requests/   new.html.erb
app/views/cards/card_runs/       index.html.erb  show.html.erb  validation.html.erb
app/jobs/cards/            generate_batch_job.rb
spec/models/cards/   spec/controllers/cards/   spec/jobs/cards/
```

**The whole routing change, and it alters no URL:**

```ruby
scope module: :cards do
  resources :card_requests, only: %i[new create]
  resources :card_runs
end
```

`/card_requests/new` and `card_runs_path` are byte-identical before and after. The class becomes
`Cards::CardRequestsController`, and **the views move as a consequence, not as a decision** — Rails'
own lookup follows the controller path to `app/views/cards/card_requests/`.

### Two things that deliberately do NOT move

- **A UI primitive that shares the word.** `app/components/ui/card_component.rb` is *"a padded
  surface"* — a widget, not the business object. `ui/` is a catalogue whose taxonomy is *kind of
  widget*, not *domain*. **A name collision is not domain membership**; the test is whether the file
  would change when the business rule changes. If it would not, it stays.
- **Small flat layers.** Twelve jobs, four mailers and six helpers at the root are **fine**. The rule
  says *if this domain has work in this layer, use the domain's name* — it never says every layer
  must have directories, and reading it that way produces ceremony rather than navigation.

## What is checked

`check_layer_structure.py` reports the table above as an **advisory** — projects legitimately
differ, and the table is what makes the disagreement *between* layers visible at all. It **fails**
on one thing only: a controller whose file path contradicts the module it is actually routed as,
which is derivable from `config/routes.rb` and the file tree with no configuration.
