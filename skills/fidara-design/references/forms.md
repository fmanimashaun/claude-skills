# Forms

Forms are first-class (a sibling of components, not buried in them). Use **`simple_form`**
for the markup contract, styled to the design system; inputs consume role tokens.

## Field anatomy (every field)

`stack` (`--space: var(--space-2xs)`) of: **label** → **control** → **helper/error text**.
Optional leading/trailing icon or prefix/suffix. Label always present (visually or `sr-only`).

```erb
<%= f.input :email, hint: "We'll never share it." %>
```

That one call renders the whole anatomy, because **the anatomy is defined once** in
`config/initializers/simple_form.rb` as a styled wrapper — the `stack`, the label
classes, the control classes and the hint/error paragraphs all live there. See
[component-implementations.md](component-implementations.md) → Field anatomy for the
wrapper configuration itself.

**Never hand-roll a field.** No `f.label` + `f.input_field` + a hand-written `<p>`, and
no bespoke field-wrapper component — a component that renders its own `<label>` and error
markup *is* a form element built without simple_form, which is what the mandate rules out.
Hand-rolled anatomy drifts from every other field the moment someone edits it; one wrapper
definition is what makes a change land everywhere at once.

**This applies inside ViewComponents too.** A component that renders fields takes the form
builder in and calls `form.input`, rather than re-implementing label/input/error markup:

```erb
<%# inside a ViewComponent template — composition, not re-implementation %>
<div class="stack">
  <%= form.input :line1 %>
  <%= form.input :city %>
</div>
```

### There is no non-simple_form case

Every shape a form can take is covered, so the rule has no exceptions:

| case | how |
|---|---|
| Model-backed form | `simple_form_for @invoice do \|f\|` |
| **No model** (search, filters, a non-AR object) | `simple_form_for :q, url: search_path, method: :get do \|f\|` — simple_form takes a symbol + `url:`, so a model-less form is still a simple_form form |
| **Label must be hidden** (icon-only search) | `f.input :q, label: false, input_html: { "aria-label": "Search" }` — the accessible name is required, the visible label is not |
| Control inside a composed cluster (search in a button group, prefix/suffix) | `f.input_field :q` — simple_form's **control-only** renderer, used when the wrapper's own markup would fight the composition |

`f.input_field` is *simple_form*, so it satisfies the mandate. What the mandate forbids is
**hand-rolling the anatomy** — `f.label` plus a manual `<p>` for the error, or a component that
emits its own `<label>`. Reach for `input_field` because the surrounding layout demands it, never
to avoid configuring a wrapper.

When a control genuinely needs a one-off class, it comes from `input_classes(state:, size:)` in
`UiHelper` (keyword arguments; there is no `field_classes`). A **repeated** deviation is a second
named wrapper, not a repeated override — see below.

## Control recipe + states

Base: `block w-full rounded-md border bg-background text-step-0 text-foreground px-3 h-9
placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2
focus-visible:ring-ring/30 focus-visible:border-ring disabled:opacity-50 min-h-touch`.

- **default** → `border-input`
- **error** (`aria-invalid="true"`) → `border-destructive focus-visible:ring-destructive/30` +
  helper text `text-destructive`; set `aria-describedby` to the error id.
- **success** → `border-success`
- **disabled/readonly** → `disabled:opacity-50` / `readonly:bg-muted`.
- **sizes** `sm h-8 · md h-9 · lg h-10` (match Button).

## Controls

- **text/email/number/search/textarea** — the recipe above (textarea `min-h-[…]`, no fixed height).
- **select** — native first, styled to match; custom combobox only when search/async is needed.
  This is **our judgement**, not a Combobox-pattern requirement — the pattern never says it. The
  nearest authority is the *First Rule of ARIA Use* ("if you can use a native HTML element…then
  do so"), whose document is now a **W3C Discontinued Draft**, so treat it as longstanding WAI
  philosophy rather than a live citation
  (build on the list-navigation mixin, `role="combobox" aria-expanded aria-controls`,
  `aria-activedescendant`; lazy-load results via a Turbo Frame).
- **checkbox / radio** — `size-4 rounded text-primary focus-visible:ring-ring/30` (radio `rounded-full`);
  wrap label in a `cluster` so control + text align.
- **switch/toggle** — `Ui::Switch` (`role="switch" aria-checked`), track uses `--primary` when on.
- **password** — reuse the `password_with_toggle` input (visibility toggle + strength meter).
- **multi-step** — the `multistep` Stimulus controller; numbered step indicator chips
  (`size-8 rounded-full border-2`, active `border-primary text-primary`).

## Error summary

Above the form when submit fails: `box` + `border-destructive bg-destructive/5` + a `stack`
list; link each item to its field id. `role="alert"`.

## Layout

Field grids use intrinsic `grid-auto` (`--min: 16rem`) or `Layout::Switcher` for 2-up/3-up
that collapses to single column with no breakpoint — **not** hand-written `grid-cols-1
sm:grid-cols-2`. Buttons in a trailing `cluster`; primary action first (LTR) / last per
platform convention, consistently.

## a11y

Label every control; associate helper/error via `aria-describedby`; mark invalid with
`aria-invalid`; group related controls in `<fieldset><legend>`; keep focus order natural;
never rely on color alone for error state (icon + text too).
