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
- **range** and **date/time** — native, with two specific exceptions each. Full contracts below.

## Range input (#95)

**Native `<input type="range">`, in the field wrapper, and leave the ARIA alone.** ARIA in HTML gives
it an implicit role of **`slider`** and then says so explicitly: *"No `role` other than slider, which
is NOT RECOMMENDED"*, and *"Authors SHOULD NOT use the `aria-valuemax` or `aria-valuemin` attributes on
`input type=range`"* — the native `min`/`max` already supply them, and `aria-valuenow` comes from the
control's live value. Hand-adding `role="slider"` or the value attributes is **discouraged by spec**,
not merely redundant.

Reach for `role="slider"` only when building the custom widget, and then know the contract:

- **`aria-valuenow` is the only REQUIRED property.** *"Authors MUST set the aria-valuenow attribute."*
  `aria-valuemin` and `aria-valuemax` are *Supported*, i.e. optional — *"Authors MAY set"* them — and
  default to **0** and **100**. `aria-orientation` is optional with an implicit `horizontal`.
- **Accessible name required, From: author** — `aria-labelledby` to a visible label, or `aria-label`.
  Never from content.
- **Keyboard: arrows and `Home`/`End` are required. `Page Up`/`Page Down` are labelled "(Optional)"**
  in the pattern itself — do not report their absence as a defect.

**The two cases where native is genuinely not enough:**

- **Two thumbs.** There is no native two-handle range, which is exactly why APG carries a **separate
  pattern**, *Slider (Multi-Thumb)*. Each thumb is its own `role="slider"` element with **its own
  accessible name and its own `aria-valuenow`/min/max**. Ship it knowing the pattern's own warning:
  users of **touch-based** assistive tech *"may experience difficulty... the gestures their assistive
  technology provides for operating sliders may not yet generate the necessary output"*, and APG says
  to test on touch devices *before considering incorporation into production systems*. A two-thumb
  price filter is often better as two number fields.
- **A value the number does not convey** (a T-shirt size, a rating, a currency band). ARIA 1.2:
  *"Authors SHOULD only set the aria-valuetext attribute when the rendered value cannot be meaningfully
  represented as a number."* This is a **spec-level SHOULD**, and `aria-valuetext` is *not* in the
  SHOULD-NOT list for `input type=range` — so it layers onto the **native** element. Still native, not
  a rebuild.

**Vertical is not one of those cases.** A vertical range is native via CSS (`writing-mode:
vertical-rl`); rebuilding a slider to get one is the common mistake here.

## Calendar / Date picker / Time picker (#95)

**Native `input[type=date|time]` in the field wrapper, plus the Rails date helpers.** Two facts make
native-first safe rather than optimistic, and both are citable:

- **The fallback is a spec guarantee, not folklore.** For `type`, *"the attribute's missing value
  default and invalid value default are both the Text state"* — a user agent that does not know the
  `date` keyword renders a **text input**. The field keeps working; only the picker is lost.
- **The value format is locale-independent.** A *valid date string* is `yyyy-mm-dd`, always, however
  the browser chooses to display it. So the server parses one format regardless of the user's locale.
  `min`/`max` take the same format; `step` is **in days**, default `1`.

**Time inputs: `step` is in seconds, default `60`.** A step that is not a multiple of 60 is what makes
the native control surface a **seconds** field — so `step` is how you get or avoid seconds, not a
validation nicety.

**The honest caveat, labelled as ours.** `input type=date` and `type=time` have **"No corresponding
role"** in ARIA in HTML — unlike range, there is no native-to-ARIA equivalence to lean on, and the
picker is a platform affordance outside the role model. The widely-repeated complaints about native
date pickers (uneven screen-reader support, whether the popup is keyboard-operable) are **not stated by
any primary source we could find** — not the HTML spec, not MDN. They are practitioner observation and
doctrine says so; do not cite a spec for them.

**If you must build one — and the architecture is a choice, not a mandate:**

- **There is NO APG "Date Picker" pattern.** The index lists 30 patterns and none is a date picker.
  What exists are **two examples under other patterns**: a *Date Picker Dialog* under **Dialog
  (Modal)**, and a *Date Picker Combobox* under **Combobox**. The Dialog example itself links the
  Combobox one as a *"Similar example"*. So **"a date picker must be a dialog" is false** — APG
  documents two valid architectures and mandates neither. Say "APG's date-picker examples", never "the
  APG date picker pattern".
- **`role="grid"` for the calendar is what both worked examples do** — a `<table>` as a grid, where
  *"the row, columnheader, and gridcell roles do not need to be specified because they are implied by
  tr, th, and td tags"*. Follow it, but note it is demonstrated rather than stated as a normative must.
- **`aria-selected` and `aria-current` come from different sources, and only one is in the examples.**
  APG's examples use **`aria-selected` only**, *"set on the cell containing the currently selected
  date; no other cells have aria-selected specified"* — and use no `aria-current` at all.
  `aria-current="date"` is nonetheless spec-real: ARIA 1.2 defines the `date` token as *"a date token
  used to indicate the current date within a calendar"*, and notes the two *"can have different
  meanings and can both be used within the same set of elements"*. So: `aria-selected` for the chosen
  date (APG), `aria-current="date"` for today (ARIA 1.2). Two claims, two citations.
- **The month/year heading is a live region** — *"marked up as a live region so screen reader users get
  feedback from the buttons and keyboard commands that change the month and year."* Use `role="status"`
  per the live-region rule in interaction-stimulus.md.
- **Do not copy the old three-spinbutton date picker.** It was removed from APG and now exists only as
  an archived 2019 Working Draft page. An archived example is not doctrine.
- **Day-cell naming is unresolved upstream.** The examples' prose documents `abbr` on the **column
  headers** (full weekday names) and says nothing about naming an individual day cell. If you need a
  convention, decide it and record it as ours — do not attribute one to APG.

### WCAG for both, scoped precisely

- **1.3.5 Identify Input Purpose (AA)** applies to a date field **only when it collects information
  about the user** — a date of birth takes `autocomplete="bday"`. An appointment date or a report
  filter is out of scope. "Date pickers need 1.3.5" is too broad to ship.
- **2.5.8 Target Size (Minimum) (AA, new in WCAG 2.2)** — 24×24 CSS px, with a **User Agent Control**
  exception: *"the size of the target is determined by the user agent and not modified by the author."*
  That covers the **native** range thumb and the native picker. It does **not** cover **custom**
  calendar day cells or a hand-rolled thumb, which are author-rendered — so the moment you build the
  custom widget, this applies to you.
- **2.5.8 is not 2.5.5.** *Target Size (Enhanced)* is a different criterion — AAA, 44×44, from WCAG
  2.1. Cite 2.5.8.

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
