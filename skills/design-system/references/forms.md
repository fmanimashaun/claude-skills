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

Base: `block w-full rounded-md border bg-background text-step--1 text-foreground px-3 h-9
placeholder:text-muted-foreground focus-visible:outline-hidden focus-visible:ring-2
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

## Input group — prefix / suffix addons (#95)

**Not a component.** It is a **variant of Text input**, and the distinction is the doctrine: the
Tailwind UI `forms/input-groups` corpus directory is already claimed by the `Text input` row, and
giving addons their own component would be the *duplicate mechanism* the component catalog forbids.
One control, one contract, an optional addon on either side.

```erb
<%# currency prefix — the addon is INSIDE the bordered box, the input keeps its own focus ring %>
<div class="cluster rounded-md border border-input bg-background focus-within:ring-2
            focus-within:ring-ring/30" style="--space: 0">
  <span class="px-3 text-step--1 text-muted-foreground" aria-hidden="true">£</span>
  <%= f.input_field :amount, inputmode: "decimal",
        class: "flex-1 min-w-0 bg-transparent px-0 pe-3 h-9 min-h-touch text-step--1 " \
               "text-foreground focus-visible:outline-hidden" %>
</div>
```

Four rules, each with a reason rather than a preference:

- **The ring moves to the wrapper.** The addon and the control read as one field, so the focus
  indicator must surround both — `focus-within:ring-2` on the wrapper, and the inner control drops
  its own ring. Leaving the ring on the input draws a box around half the field.
- **A decorative addon is `aria-hidden`.** `£` or a `@` glyph is presentation; announcing it turns
  *"Amount"* into *"Amount pound"*. An addon that carries **meaning** the label does not
  (`.com`, `USD` where the currency is selectable) is content instead: leave it announced and make
  sure the label still says what the field is.
- **An interactive addon is not an addon.** A dropdown or a submit button beside a control is a
  composed cluster of two focusable things, each with its own name and its own `min-h-touch`. Do not
  put a `<button>` inside the wrapper and rely on the input's label to name it.
- **`f.input_field`, never hand-rolled anatomy.** This is the composed-cluster row of the table
  above — simple_form's control-only helper — so the mandate is satisfied while the wrapper supplies
  the border. Reaching for `f.label` plus a manual error `<p>` here is what the mandate forbids.

Sizes follow Text input (`h-9` default); the addon inherits the control's `text-step--1`, because it
is chrome.

## File upload / Dropzone (#95)

**No APG pattern** — the index lists 30 and there is none for file upload or drag-and-drop. This is a
**native `<input type="file">` plus an enhancement**, and the split matters because the enhancement is
the part that can fail.

### What the native control gives you, and the one thing it does not

- **`accept` is a hint, not validation.** MDN is explicit: *"The `accept` attribute doesn't validate the
  types of the selected files; it provides hints for browsers to guide users… It is still possible (in
  most cases) for users to toggle an option in the file chooser that makes it possible to override this
  and select any file they wish."* And therefore: *"you should make sure that the `accept` attribute is
  backed up by appropriate server-side validation."* **Server-side validation is mandatory, not
  belt-and-braces.**
- **`multiple`** allows more than one file; **`capture`** picks a camera, and only applies when `accept`
  names an image or video type.
- **You cannot set the value from script.** *"You cannot set the value of a file picker from a script."*
  That is a security boundary, and it has a design consequence: a dropzone cannot "fill in" the native
  input, so the two are **parallel paths to the same form submission**, not a wrapper around one.

Style it with the field wrapper's classes plus `file:` variants on the input — Tailwind's `file:`
modifier targets the button, so no custom pseudo-element is needed.

### The dropzone is an enhancement, and it has one non-negotiable

**`preventDefault()` on `dragover`, or the drop never fires.** This is the single most-missed detail in
the API: *"Any element can become a drop target by canceling the `dragover` event that fires on it with
`preventDefault()`."* Minimum viable target is `dragover` (cancelled) + `drop`.

```erb
<%# The native input is the PRIMARY path. The dropzone decorates it — it does not replace it, %>
<%# because a script cannot set a file input's value. %>
<div data-controller="dropzone"
     data-action="dragover->dropzone#over:prevent dragleave->dropzone#leave drop->dropzone#drop:prevent"
     class="stack rounded-lg border-2 border-dashed border-border p-6 text-center
            data-[state=over]:border-primary data-[state=over]:bg-primary/5">
  <p class="text-muted-foreground">Drag files here, or</p>

  <%# Not hidden, not sr-only: this button IS the 2.5.7 alternative (see below). %>
  <%= f.input :documents, as: :file, input_html: {
        multiple: true, accept: "application/pdf,image/*",
        data: { dropzone_target: "input" },
        class: "file:mr-3 file:rounded-md file:border-0 file:bg-secondary file:px-3 file:py-1.5" } %>

  <p role="status" class="text-step--1 text-muted-foreground" data-dropzone-target="status"></p>
</div>
```

Note `:prevent` in the Stimulus action — that is how `preventDefault()` is expressed declaratively, so
the rule above cannot be forgotten in the controller.

### WCAG 2.5.7 Dragging Movements — and the trap in it

**Level AA, and satisfied by the file button — but only because the button is clickable.**

> *"All functionality that uses a dragging movement for operation can be achieved by a single pointer
> without dragging, unless dragging is essential…"*

The trap, quoted because it is the opposite of the obvious assumption:

> *"achieving keyboard equivalence for a dragging operation does not automatically meet this success
> criterion, unless that equivalent keyboard operation also provides controls that can be clicked or
> tapped with a pointer."*

**So a keyboard-only alternative does not satisfy 2.5.7.** The visible, clickable file input is what
satisfies it — which is another reason never to hide the native input behind the dropzone. A
`sr-only`-hidden input plus a dropzone is a 2.5.7 failure even though it is keyboard-operable.

### Announcing it

Selection and progress are invisible without a live region. `role="status"` (polite **and** atomic — see
[interaction-stimulus.md](interaction-stimulus.md#loading-progress-and-busy-state-95)) reporting
**one aggregate**, not one message per file: *"3 files selected, 12 MB"*, then *"Uploading 2 of 3"*.
Per-file announcements on a ten-file drop are worse than none.

For the bar itself, use the documented **Progress bar** — `role="progressbar"`, indeterminate means
**omitting** `aria-valuenow`. Do not invent a second progress mechanism here.

## Copy to clipboard (#95)

**No APG pattern either.** A button, a Clipboard API call, and an announcement — the announcement being
the part most implementations skip, which makes the feature invisible to anyone not watching the button.

**`navigator.clipboard.writeText()` is the API.** Baseline **widely available since March 2020**,
**secure context only** (*"This feature is available only in secure contexts (HTTPS)"*). It returns a
promise and rejects with `NotAllowedError` when writing is refused — so failure is a real branch, not a
theoretical one, and `localhost`-vs-HTTPS is where you will meet it.

```js
// clipboard_controller.js — the announcement is the feature, not decoration.
export default class extends Controller {
  static targets = ["source", "status"]
  static values = { label: { type: String, default: "Copied" } }

  async copy() {
    try {
      await navigator.clipboard.writeText(this.sourceTarget.value)
      this.announce(`${this.labelValue} to clipboard`)
    } catch {
      // NotAllowedError, or no secure context. Never fail silently: the user
      // pressed a button and nothing visible happened.
      this.announce("Couldn't copy — select the text and copy manually")
      this.sourceTarget.select()
    }
  }

  announce(message) {
    this.statusTarget.textContent = message
    // Clear it so a second identical copy announces again — an unchanged
    // textContent is not a change, so the live region would stay silent.
    setTimeout(() => { this.statusTarget.textContent = "" }, 4000)
  }
}
```

```erb
<div class="cluster" data-controller="clipboard">
  <input type="text" readonly value="<%= @account.api_key %>"
         data-clipboard-target="source" class="font-mono text-step--1">
  <%= render Ui::ButtonComponent.new(variant: :secondary, size: :sm,
        data: { action: "clipboard#copy" }) do %>Copy<% end %>
  <span role="status" class="sr-only" data-clipboard-target="status"></span>
</div>
```

**Three rules, in order of how often they are missed:**

1. **Announce it.** A tick that changes colour is invisible to a screen-reader user, and **WCAG 4.1.3
   Status Messages (AA)** covers exactly this: a status message conveying success that does not receive
   focus. `role="status"`, not a bare `aria-live`.
2. **Re-announce a repeat.** Setting the same text twice is not a DOM change, so the region stays
   silent — clear it, or the second copy is silent.
3. **Handle the failure path visibly.** `NotAllowedError` and non-secure contexts are real. Falling back
   to selecting the text gives the user something to act on; a swallowed rejection gives them a button
   that does nothing.

**Do not reach for `document.execCommand('copy')` as a fallback.** It is deprecated, and the honest
fallback is the one above: select the text and let the user copy it. A deprecated API as a safety net is
a second thing to maintain that will itself be removed.

**Never put the value only in the clipboard.** The text must remain visible and selectable — the copy
button is a convenience over a value the user can already read, not the only way to get it.

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

Above the form when submit fails: **the documented `Ui::Alert` at `intent: :error`**, with a
`stack` list inside it linking each item to its field id.

**Not hand-rolled markup, and this entry used to be exactly that** (#95) — `box` +
`border-destructive bg-destructive/5` + `role="alert"`, written out here while
`page-anatomies.md` prescribes `Ui::Alert intent: :error` for the same surface on two separate
anatomies. Two recipes for one block is the duplicate mechanism the catalog forbids, and the
hand-rolled one silently re-derived what the component already does: `AlertComponent#role`
returns `alert` for `:error` (and `status` otherwise), so writing `role="alert"` by hand is
either redundant or, on a different intent, wrong. The component takes block content, so the
list of field links goes straight inside it.

## Layout

Field grids use intrinsic `grid-auto` (`--min: 16rem`) or `Layout::Switcher` for 2-up/3-up
that collapses to single column with no breakpoint — **not** hand-written `grid-cols-1
sm:grid-cols-2`. Buttons in a trailing `cluster`; primary action first (LTR) / last per
platform convention, consistently.

## a11y

Label every control; associate helper/error via `aria-describedby`; mark invalid with
`aria-invalid`; group related controls in `<fieldset><legend>`; keep focus order natural;
never rely on color alone for error state (icon + text too).
