# Forms

Forms are first-class (a sibling of components, not buried in them). Use **`simple_form`**
for the markup contract, styled to the design system; inputs consume role tokens.

## Field anatomy (every field)

`stack` (`--space: var(--space-2xs)`) of: **label** → **control** → **helper/error text**.
Optional leading/trailing icon or prefix/suffix. Label always present (visually or `sr-only`).

```erb
<div class="stack" style="--space: var(--space-2xs)">
  <%= f.label :email, class: "text-step--1 font-medium text-foreground" %>
  <%= f.input_field :email, class: field_classes(state) %>
  <p class="text-step--1 text-muted-foreground">We'll never share it.</p>  <%# helper %>
</div>
```

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
- **select** — native first, styled to match; custom combobox only when search/async is needed
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
