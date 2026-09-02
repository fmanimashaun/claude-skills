# Porting a Claude Design artboard into Rails 8 + Hotwire

Claude Design produces the **look**. This file is the fixed mapping that turns it into a shipped
surface. It is a bridge: it composes `rails-8` (Ruby/ERB/specs), `hotwire` (Turbo/Stimulus) and this
skill's own `components.md`, `crud-modal-pattern.md` and `interaction-stimulus.md`. It does not restate
them.

Porting by eye — reading the CSS and hand-writing ERB — is how a design system gets defeated on its
first use: raw hex in the view, a bespoke `.field`, a hand-rolled card, a CDN font. **The port is a
translation with a fixed mapping, not a rebuild by taste.**

## 1. Identify the source format first

Claude Design emits one of two shapes, and they are read differently.

**(a) React / JSX / TSX.** A component tree: `className`, props, `useState`/`useEffect`/`useRef`,
handlers, conditional render, `.map()`. Read it as **structure + state + behaviour** — the JSX is the
DOM, the hooks are the interactivity to re-express, the props are the locals.

**(b) Canvas export (`.dc.html`).** An `<x-dc>` element wrapping artboards, a `<helmet>` head, a
`:root{…}` block of literal tokens, **inline `style="…"` on nearly every element**, a Google-Fonts
`<link>`, and `@keyframes` motion. Measured on two real artboards: **500+ inline styles and zero
classes**, with one carrying **755 `var(--…)` references over 50 declared tokens**.

Both carry the same design. They differ only in how styling is expressed.

## 2. The canvas is a translation INPUT, not output

Four things in an export are preview scaffolding and **must not survive into the commit**:

| in the export | why it exists | what happens to it |
|---|---|---|
| the `:root{…}` token block | the canvas restating the design system's values | **dropped** — the app's `@theme` already supplies them |
| inline `style="…"` | how the canvas composes | **dropped** — utilities and layout primitives; the only surviving inline style is a token knob, `style="--space: var(--space-s)"` |
| `fonts.googleapis.com` `<link>` | a preview convenience | **dropped** — fonts are self-hosted |
| `support.js`, `_ds/` bundle | the browser runtime that renders `<x-dc>` | **never ported**, at all |

That last row is the one to be deliberate about. `support.js` opens with *"GENERATED from
dc-runtime/src/*.ts — do not edit"* — it is ~70KB of React that exists to preview the artboard.
Claude Design's own import instruction says *"read these files the selection imports: `support.js`"*,
which an agent can read as *port them*. It is a viewer. Porting it would introduce a client-side
framework the stack does not use, to solve a problem that does not exist.

## 3. Classify the artboard before emitting anything

The Hotwire mechanisms available depend on what the surface **is**. Say which class you chose and why.

- **Mailer.** Table markup, single column, no script. **Turbo and Stimulus are forbidden here** — mail
  clients run no JavaScript, and custom properties are unreliable, so inline literals are correct (§5).
  This is a Rails mailer view, not a page.
- **Static page.** No state, no round-trip. Partials and components; no Stimulus for its own sake.
- **Interactive page.** State or server round-trips. Now §4 applies in full.

Getting this wrong is the expensive mistake: reaching for a Stimulus controller on a mailer produces
markup that renders in the preview and does nothing in an inbox.

## 4. The mapping

| source construct | port to |
|---|---|
| JSX tree / `<x-dc>` artboard structure | **ERB partials + ViewComponents** — a repeated unit is a component, a one-off section is a partial |
| `className`, inline `style`, CSS-in-JS, the `:root` block | **role-token utilities**, and `var(--token)` where a raw custom property is genuinely needed. Never a raw hex, never a palette-name utility, never a per-element dark variant — dark mode is one re-point of the roles |
| `useState` / props / context | **Stimulus values and targets**; props a partial needs become `locals:` |
| `useEffect(setup, [])` / cleanup | Stimulus `connect()` / `disconnect()` |
| `onClick` / `onChange` / `onSubmit` | `data-action="event->controller#method"` |
| conditional render | ERB `if`/`unless`/`case` — or a **Turbo Frame** when the branch is a server round-trip |
| `.map(item => …)` | `<% collection.each %>`, each row `id="<%= dom_id(item) %>"` so a Turbo Stream can target it |
| controlled input + `<form onSubmit>` | **`simple_form_for` + `f.input`** — this stack mandates simple_form (`rails-8` `ecosystem-gems.md` §2). Validation is server-side; no bespoke field markup |
| modal / dialog / drawer | the **Turbo-Frame modal flow** — `crud-modal-pattern.md` owns it; a full-page CRUD form is a defect |
| SVG hex fills, `@keyframes` | role-token paint; motion through the existing reduced-motion-safe controllers — `interaction-stimulus.md` |
| `<a href>` / router link | **path helpers** + Turbo Drive |
| icon components | the project's icon helper, `aria-hidden` on decorative marks |
| cards / badges / alerts / empty states | catalog components, on-catalogue variants only — `components.md` |
| grid/flex, breakpoint utilities, ad-hoc gaps | **layout primitives** — spacing through the primitive's own knob, not child margins |

## 5. Where a literal is correct

A few places genuinely cannot resolve `var()`. These are the **only** ones, each annotated with its
reason, and each value must match the token it stands for — a drifted literal is a bug, not an
exception:

- **Email inline styles** — mail clients do not honour custom properties.
- **Static pages served without the asset pipeline** — offline and error pages.
- **`@font-face` family names** — a family name is a string, not a colour.
- **`data:` URI favicons and manifest colours** — a manifest cannot reference `var()`.

Reaching for a literal outside this list is the divergence, not an exception to it.

## 6. Porting more than one artboard: one fact, one owner

A canvas repeats itself on purpose. Each artboard has to stand alone as a picture, so the value
proposition, the spec block and the headline figure get restated on the landing, the pricing page and
the partner page — three artboards, one fact, three copies.

**Pages are not pictures.** Port that repetition and you have created three places to update and no
arbiter between them; the first edit that lands in one of them makes the other two wrong, silently,
because nothing compares them. This is the same defect as a second source of truth anywhere else — it
is just wearing a design.

So when a port spans several surfaces: **pick the page that owns each fact, and have the others link
to it.** The owner is usually the page a reader arrives at to answer that question. Cross-link from the
rest rather than restating.

Two things this is not. It is **not** a rule against repeating a *component* — a card used on three
pages is reuse, and reuse is the point. And it is **not** licence to drop content the design needs; if
a page genuinely reads wrong without the fact, that is a signal the fact belongs there and the *other*
page should link to **it**. What is forbidden is the same sentence, maintained in three files, because
a canvas needed each frame to be self-contained.

Say which page you made the owner, and where you linked from. A reviewer cannot see that decision in
the diff.

## 7. Preserve the design exactly; align the implementation

Visual parity is non-negotiable — same layout, rhythm, type scale, colour, motion, states. The
alignment is *visual-preserving*: where the app's role tokens already equal the canvas literals,
tokenising `#0077CC` to `var(--primary)` is pixel-identical rather than an approximation. Confirm that
equality rather than assuming it; where the design needs a value the tokens cannot express, that is a
**token gap to raise**, never a literal smuggled in.

## 8. The port is not done until

- Specs are green, including one proving any new behaviour.
- `/design-flow:audit` reports no drift: no raw hex, no bespoke field or layout CSS, on-catalogue
  variants, no CDN font.
- Every state the design shows is implemented — empty, loading, validation-error, success — not just
  the happy one the artboard illustrates.
- Accessibility holds: one `h1`, a visible focus ring, AA contrast, touch targets.
