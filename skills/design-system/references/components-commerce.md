# Commerce components

The catalogue entries for **selling things**: product card, filter panel, quick view, cart, payment,
promo codes, plan comparison, seat selection, saved payment methods, subscription state. Split out of
[components.md](components.md) (#871) because they were ~40 % of it and irrelevant to every surface
that does not sell; a commerce surface reads both files, as it always did. Same rules: each entry is a
composition of layout primitives + role tokens with a fixed variant × size × state vocabulary, an a11y
checklist and a prescribed responsive behaviour. Anything these entries build from — Grid list, Card,
Modal, Drawer, Stacked list, Stepper — is documented in [components.md](components.md) and linked from
each entry. `coverage.md` counts both files as the catalogue.

## Product card
- **No new mechanism: the grid is the documented [Grid list](components.md#grid-list) and the card is the documented
  [Card](components.md#card).** What this entry owns is the four decisions a catalog card gets wrong — how many links
  it has, where the add-to-basket control may live, how a reduced price is marked, and how stock reads
  without colour. **No APG pattern covers it**: the index lists 30 and none is a card, a product grid or
  a gallery, so every rule below is either an HTML/WCAG citation or ours, and says which.
- **The "Add to basket" button must not be inside the link — and that is invalid HTML, not a styling
  problem.** The `<a>` element's content model is *"Transparent, but there must be no interactive
  content descendant, a element descendant, or descendant with the `tabindex` attribute specified"*, and
  the **interactive content** category names `button` unconditionally. So `<a …><button>Add to
  basket</button></a>` is a content-model violation whatever it looks like. Keeping them **siblings** and
  stretching the link (the [Stacked list](components.md#stacked-list) recipe) fixes the markup and leaves the pointer
  problem that entry already states: *the stretched overlay covers every sibling*, so the button under it
  cannot be clicked. Both roads are closed, which is the finding, not a nuisance.
- **So a card in a catalog grid carries ONE link and no second control — and that is why
  [Quick view](#quick-view) exists.** A grid that needs an add-to-basket affordance gets it from the
  quick-view dialog, not from a control wedged into the card. **This is our decision** (recorded on
  [#91](https://github.com/fmanimashaun/claude-skills/issues/91)); the HTML rule above forces the shape,
  it does not name the alternative.
- **Two links to one product — the image and the title — is NOT a 2.4.4 failure, and calling it one is
  the usual overstatement.** 2.4.4 Link Purpose (In Context) (**Level A**) asks only that *"the purpose
  of each link can be determined from the link text alone or from the link text together with its
  programmatically determined link context"*, and Understanding 2.4.4 counts *"the same sentence,
  paragraph, list item, or table cell as the link"* as that context — which a card supplies. It is
  conformant and still worse: two tab stops and two link-list entries for one destination, which is why
  technique **H2** is *"Combining adjacent image and text links for the same resource"*. **Ours: one
  link, `alt=""` on the image**, because the title beside it already carries the name.
- **A reduced price is two prices and a word, and `<s>` is the element the HTML Standard names for
  exactly this case.** *"The `s` element represents contents that are no longer accurate or no longer
  relevant"* — and the spec's own worked example is a recommended retail price superseded by a sale
  price. **Not `<del>`**, which *"represents a removal from the document"*, i.e. a tracked edit; the
  spec draws that line itself (*"The `s` element is not appropriate when indicating document edits"*).
  Wrap the pair in `sr-only` "was" / "now": a strikethrough is a visual convention that announces
  nothing on its own.
- **Colour carries neither the reduction nor the stock state.** 1.4.1 Use of Color (**Level A**):
  *"Color is not used as the only visual means of conveying information, indicating an action, prompting
  a response, or distinguishing a visual element."* A sale price that differs from the old one only in
  hue, and an in-stock dot that is green rather than grey, are the two failures a product grid ships.
  Stock is a word — "In stock", "2 left", "Out of stock" — and the dot is decoration beside it.
- **Money is `tabular-nums`, never `font-mono`** ([brand.md](brand.md#money-is-tabular-nums-not---font-mono-91)).
  In a grid this is the visible half of the rule: a column of prices whose digits do not line up is the
  first thing that reads as unfinished.
- **Variants:** `plain` (card on the page background) · `bordered` (the Card's own `border-border`) ·
  `compact` (no media, for a reel). **States** live on the `<li>`: `hover:bg-accent`, the link's
  `focus-visible` ring, and `aria-disabled` plus the "Out of stock" word for an unbuyable item — never
  a `disabled` card, which removes it from the tab order and hides the reason.
- **Responsive:** none. `grid-auto` with `--min: 15rem` *is* the behaviour ([Grid list](components.md#grid-list)); a
  product grid needs no breakpoint and no second column count.

## Filter panel
- **No APG pattern, and the index is how that is checkable** — 30 patterns, none of which is a filter,
  a faceted search or a filter sidebar. The nearest shipped mechanisms are the
  [Disclosure](components.md#disclosure--accordion) (one per group) and the [Modal](components.md#modal--dialog) at an edge (the
  mobile drawer), and both are used unchanged.
- **One mechanism, two hosts.** The catalog filter sidebar and the [Table (CRUD)](components.md#table-crud) index
  filter are the same panel with different fields; they do not get two implementations. What differs is
  where the result count lands — a grid of [Product cards](#product-card) here, table rows there.
- **It is a `GET` form with a submit, and that is the baseline rather than the enhancement.** Filter
  state then lives in the URL, so a filtered view is shareable, back-button-correct, and survives a
  failed script. Enhance with Turbo afterwards; never start from a Stimulus controller that mutates a
  list and leaves the address bar behind.
- **One [Disclosure](components.md#disclosure--accordion) per filter group, and APG's mandate is smaller than people
  build.** The pattern requires exactly three things — *"The element that shows and hides the content
  has role `button`"*, `aria-expanded` *"set to true"* when open and *"false"* when closed, and for
  keys, **`Enter` and `Space` only**. `aria-controls` is *"Optionally"* in APG's own wording; **our
  contract requires it anyway** and says so, because the panel is not adjacent to its trigger on a wide
  sidebar. **There are no arrow keys on a disclosure** — a filter group is not a menu and not a listbox,
  and adding a roving tabindex here is the most common over-build.
- **Below `lg` the panel is the documented Modal at `placement: :left`, not a reflowed sidebar.** That is
  the [Drawer](components.md#drawer--off-canvas) contract in full — dialog role, name, focus trap, `Esc`, restore —
  and `component-implementations.md` already ships that exact markup with `Filters` as its title. Render
  both and let the breakpoint choose; do not toggle `aria-modal` by media query.
- **The result count is a status message; the results are not.** 4.1.3 Status Messages (**Level AA**)
  covers content *"presented to the user by assistive technologies without receiving focus"*, and
  Understanding 4.1.3 draws the line for this exact surface: *"the list of results obtained from a search
  are not considered a status update and thus are not covered by this success criterion. However, brief
  text messages displayed about the completion or status of the search, such as 'Searching…', '18 results
  returned' or 'No results returned' would be status updates."* So `role="status"` goes on the
  "24 products" line — **not** on the grid, which would announce every card on every filter change.
- **Filtering into nothing is an [Empty state](components.md#empty-state), and that entry already requires the
  announcement** — do not add a second live region beside the count for it.
- **Applied filters are dismissible [Badges](components.md#badge--tag--chip), each naming its own filter.**
  `aria-label="Remove filter: Blue"`, not "Remove" six times. A "Clear all" is a separate control and is
  not one of the chips.
- **2.5.8 Target Size (Minimum) is AA and a dense checkbox column is where it fails.** The criterion is
  *"at least 24 by 24 CSS pixels"* with five exceptions, and only two are ever reachable here:
  **Spacing** — *"Undersized targets … are positioned so that if a 24 CSS pixel diameter circle is
  centered on the bounding box of each, the circles do not intersect another target"* — and
  **Equivalent**. *Inline* does not apply (a checkbox row is a block target) and neither does *Essential*.
  Give rows `min-h-touch` and stop reasoning about circles.
- **Responsive:** the sidebar is a `grid-auto items-start` column beside the results at `lg` and up, and
  the drawer below it. The count and the sort control stay with the results in both.

## Quick view
- **The documented [Modal](components.md#modal--dialog) with product content inside it. Nothing here is new**, which
  is the point: no `Ui::QuickViewComponent`, no second dialog implementation, no second focus trap.
- **It is never a substitute for the product page.** A dialog has no address, so a quick view cannot be
  shared, linked, bookmarked, or reached by the back button, and a customer who wants the full
  description has nowhere to go. **Ours** (recorded on
  [#91](https://github.com/fmanimashaun/claude-skills/issues/91)): the dialog carries a summary and the
  buy control, and always carries a "Full details" link to the real route. A quick view that is the only
  way to see a product is a routing defect wearing a dialog.
- **This is where a grid's add-to-basket control lives**, for the content-model reason in
  [Product card](#product-card). The card opens the dialog; the dialog holds the variant fieldsets, the
  [Seat / quantity selector](#seat--quantity-selector) and the submit.
- **The dialog contract is APG's, unchanged**, and one line of it is routinely dropped: *"It is strongly
  recommended that the tab sequence of all dialogs include a visible element with role `button` that
  closes the dialog, such as a close icon or cancel button."* Focus returns *"to the element that invoked
  the dialog"* — the card's link, not the grid.
- **One modal frame means one layer.** The shared `id="modal"` frame ([crud-modal-pattern.md](crud-modal-pattern.md))
  holds a quick view exactly as it holds an edit form, so a quick view cannot open a second dialog inside
  itself; a variant that needs its own screen is the product page.
- **Name the dialog with the product**, not with "Quick view" — six identical dialog names in a session
  is the same defect as six "Remove" buttons.
- **Responsive:** below `sm` the modal is `full`; a quick view that scrolls a phone screen twice has
  become the product page and should be a link instead.

## Cart drawer and cart line
- **The drawer is the documented [Modal](components.md#modal--dialog) at `placement: :right` — one dialog
  implementation, one trap, one `Esc`** ([Drawer / off-canvas](components.md#drawer--off-canvas)). **No APG pattern
  names a drawer or a cart**; the borrowed contract is Dialog (Modal), and the 30-pattern index is how
  that negative stays checkable.
- **A cart panel that is not a real modal fails a criterion that is new in WCAG 2.2, so "just slide a
  panel over the page" is not the cheap option.** 2.4.11 Focus Not Obscured (Minimum) (**Level AA**):
  *"When a user interface component receives keyboard focus, the component is not entirely hidden due to
  author-created content."* Leave the page behind tabbable and the next `Tab` lands on a control the
  panel is covering — the criterion's exact failure. A correctly modal drawer never reaches it, because
  nothing behind the panel is focusable at all.
- **`aria-modal` is a claim; `inert` is the mechanism — ship both.** APG permits `aria-modal="true"` only
  when *"Application code prevents all users from interacting in any way with content outside of it"*,
  and the attribute itself does nothing to bring that about. The HTML Standard's `inert` does: on an
  inert subtree *"Hit-testing must act as if the 'pointer-events' CSS property were set to 'none'"*, and
  *"user agents do not expose the inert nodes to accessibility APIs or assistive technologies"*. APG's
  pattern text never mentions `inert` — it discusses `aria-modal` replacing `aria-hidden` — so pairing
  the two is **ours**, and it is what makes APG's own precondition true.
- **The total is a live region, and WCAG's Understanding document uses a shopping cart as its worked
  example — this is not an analogy we invented.** 4.1.3 (**AA**): *"An example would be a shopping cart
  which updates text from reading '0 items' to '3 items'… where only the number in this string was coded
  as an updated chunk of content, the resulting experience for screen reader users could be to only hear
  'three'… In such situations, marking the entire '3 items' string as the status text would normally be a
  better solution… it would also be a courtesy to add offscreen text such as 'in shopping cart'."* Use
  `role="status"`, which carries `aria-live="polite"` **and** `aria-atomic="true"` implicitly; a bare
  `aria-live` defaults `aria-atomic` to false, and then *"assistive technologies will only present the
  changed node to the user"* — the bare "three" the example describes. **One region for the money**: the
  total, not the badge and not each line.
- **Quantity is the [Seat / quantity selector](#seat--quantity-selector), unchanged** — same element,
  same visible label, same `+`/`−` naming, same server-side clamp. Do not restate its rules here.
- **"Never submit on change" is OUR rule here, and 3.2.2 is a narrower criterion than it is usually made
  to carry.** 3.2.2 On Input (**Level A**) forbids an automatic **change of context**, and WCAG defines
  that as a change of *"user agent; viewport; focus; content that changes the meaning of the web page"*,
  adding that *"a change of content is not always a change of context"*. A quantity edit that streams a
  new total into place without moving focus is a change of **content**, so 3.2.2 is not what forbids it —
  **the money is**, which is the same reason the [Promo / discount code](#promo--discount-code) entry
  gives. Where 3.2.2 genuinely bites is the version that re-renders the row and drops focus, and that one
  is a defect for its own reason.
- **A remove control names what it removes**, exactly as [Saved payment methods](#saved-payment-methods)
  requires: `aria-label="Remove Blue T-shirt, medium"`, never the row number and never six identical
  "Remove"s. It is also a 2.5.8 target: an icon-only `×` takes `min-h-touch` or clears the **Spacing**
  exception, and *Inline* does not apply to a block control in a list row.
- **Removing a cart line gets an undo, not a confirmation dialog — and no source decides this, so we
  do.** 3.3.4 Error Prevention (Legal, Financial, Data) (**AA**) covers pages that *"modify or delete
  user-controllable data in data storage systems"*, and its Understanding document then narrows the
  intent to *"prevent mass loss of data such as deleting a file or record"*, explicitly excluding *"the
  simple creation or editing of documents, records or other data"* — with *"deleting a record of past
  invoices"* as the in-scope example. An open cart sits between the two and **no W3C document rules on
  it**; the verdict was INCONCLUSIVE, so the position is a maintainer decision recorded on
  [#91](https://github.com/fmanimashaun/claude-skills/issues/91): **a cart line is draft data, so removal
  is immediate and reversible**, and the confirmation modal that
  [crud-modal-pattern.md](crud-modal-pattern.md#a-confirmation-is-for-what-cannot-be-undone) requires for
  destructive actions is scoped away from it there. **The price of that decision is that the undo must
  really exist** — a toast that says "Removed" with no way back is the version that fails the customer.
- **No specification requires an undo anywhere, and two criteria are miscited for it.** 3.3.4 offers
  **Reversible / Checked / Confirmed** as *alternatives* — Confirmed satisfies it without any undo — and
  3.3.6 Error Prevention (All) has the same three-way test at **Level AAA**, which is not our baseline.
  So the undo above is a design choice we are making, not a conformance obligation, and doctrine should
  not dress it as one.
- **An empty cart is the documented [Empty state](components.md#empty-state)** — in the drawer as well as on the page,
  with one route back to browsing. Not a blank panel, and not the drawer refusing to open.
- **The drawer and the [Cart page](page-anatomies.md#cart) both exist, and neither replaces the other.**
  The drawer is a preview that keeps the customer in the catalog; the page is the addressable, printable,
  full-width view a checkout starts from, and it is where a promo code belongs
  ([Promo / discount code](#promo--discount-code)). **Ours.** The drawer therefore always contains a link
  to the page as well as the checkout CTA.
- **One Turbo Stream response updates the badge, the line and the total — and it is eight actions, not
  nine.** Turbo 8's stream actions are `append`, `prepend`, `replace`, `update`, `remove`, `before`,
  `after` and `refresh`; **`morph` is a `method="morph"` modifier on `replace`/`update`/`refresh`, never
  an action name** (Turbo's own handbook prose says "nine actions" in one paragraph and "eight" two
  paragraphs later — the reference page and `stream_actions.js` agree on eight). Targets resolve
  **document-wide**, not within the submitting frame, so a header badge, a drawer line and a summary
  total are all addressable from one response by `dom_id`.
- **Responsive:** the drawer is `max-w-sm` and full-height at every width; below `sm` it is the Modal's
  `full` size. The cart *page* keeps its two-column `grid-auto` and collapses to one — the summary below
  the lines, never beside them at that width.

## Payment / card entry
- **The card fields are not yours to build.** Card number, expiry and security code are rendered by
  the payment provider — a hosted page you redirect to, or provider-owned iframe(s) you embed. What
  this entry specifies is the **container**: the label, the error region, the `md` field height
  (`h-9`, matching the input recipe) so a provider iframe lines up with the fields above and below it,
  and the ring tokens you hand the provider's stylesheet so a focused iframe field does not look
  foreign. There is no `Ui::CardNumberComponent`, and writing one is the defect.
- **Which integration you choose has a compliance consequence, and the intuitive answer is out of
  date.** PCI DSS v4.0.1's SAQ A — the January 2025 revision, in effect since **31 March 2025** —
  **removed** Requirements 6.4.3 and 11.6.1 (and 12.3.1) as SAQ A line items and replaced them with an
  eligibility criterion: *"The merchant has confirmed that their site is not susceptible to attacks
  from scripts that could affect the merchant's e-commerce system(s)."* Per PCI SSC **FAQ 1588** that
  criterion applies **only** to *"e-commerce merchants with a webpage that includes a TPSP's/payment
  processor's embedded payment page/form (for example, one or more inline frame(s) (iframes))"* and
  *"does not apply to e-commerce merchants with a webpage that redirects customers from the merchant's
  webpage to a TPSP/payment processor … or e-commerce merchants that fully outsource payment
  functions."* So **embed vs redirect is a UI decision that moves an obligation**, and an embedding
  merchant discharges it either by deploying the 6.4.3/11.6.1 techniques or by written confirmation
  from the provider. Quoting the current wording is the point: citing 6.4.3/11.6.1 *as SAQ A line
  items* has been wrong since 2025-03-31. **This is framing, not a compliance determination** — which
  SAQ you validate to is your acquirer's and QSA's call, not a design skill's.
- **Nothing card-shaped may touch your DOM, your params or your logs.** That is the whole reason the
  fields are the provider's. A "just for validation" mirror input, a Stimulus value holding the PAN,
  or an analytics listener on the payment container each undo the integration you chose.
- **`type="number"` is wrong for a card number, and the spec says why.** *"The type=number state is
  not appropriate for input that happens to only consist of numbers but isn't strictly speaking a
  number. For example, it would be inappropriate for credit card numbers or US postal codes."* Its
  test is whether a spinbox would make sense: *"Getting a credit card number wrong by 1 in the last
  digit isn't a minor mistake, it's as wrong as getting every digit incorrect."* `type="text"`, with
  `inputmode="numeric"` where the value really is all digits. The note names **postal codes** too, so
  it binds the address block you *do* own — but a postcode is alphanumeric in much of the world, so
  that one gets `type="text"` and **no** numeric `inputmode`.
- **The fields that ARE yours take autofill tokens.** Cardholder name is `cc-name`; your own billing
  block is `billing`-prefixed (`autocomplete="billing postal-code"`). The order is fixed by the HTML
  Standard and is not free-form: optionally a `section-*` token, then optionally `shipping` or
  `billing`, then optionally `home`/`work`/`mobile`/`fax`/`pager`, then the field name — in that
  order. `billing postal-code` is valid; `postal-code billing` is not.
- **1.3.5 Identify Input Purpose (AA) covers these, with two boundaries worth knowing.** The `cc-*`
  tokens (`cc-name`, `cc-number`, `cc-exp`, `cc-csc`, `cc-type`, …) *are* in WCAG's *Input Purposes
  for User Interface Components* list, so a cardholder-name field is in scope. But the SC is *"scoped
  to inputs collecting information about the user"* — H98 states it directly, and Understanding 1.3.5
  adds that *"an input field for information that is not about the user does not need to
  programmatically expose its purpose, even if that purpose is included in the Input Purposes
  list"*, naming `transaction-amount`. And **`one-time-code` is a valid HTML autofill token but is
  absent from WCAG's list** — put it on a 3-D Secure step because it makes the OS offer the SMS code,
  not because 1.3.5 asks for it.
- **The disable-on-submit half is already done, which is exactly why it is not the protection.** Turbo
  *"will set the 'submitter' element's disabled attribute when the submission begins, then remove the
  attribute after the submission ends"*; `data-turbo-submits-with` *"specifies text to display when
  submitting a form"* and is the labelled in-flight state, never a bare spinner. Both are client-side
  and both lose to a reloaded tab. **Only a server-side idempotency key makes a double-submit safe**,
  and that is the rule — the button state is feedback, not a guard.
- **A form that posts to the provider's hosted page must opt out of Turbo.** `data-turbo="false"`
  *"disables Turbo Drive on links and forms including descendants"*. Otherwise Turbo fetches the
  cross-origin payment page and cannot render it, and the user sees nothing happen.
- **a11y — you cannot label the provider's field from your page, and this is the part everyone gets
  wrong.** `<label for>` requires *"the ID of a labelable element **in the same tree** as the label
  element"*: a mount-point `<div>` is not labelable, and a control inside an `<iframe>` is a different
  tree, so neither `for` nor `aria-labelledby` reaches it. **The accessible name must be set inside
  the frame, through the provider's own label/placeholder option**; the visible caption in your page
  is then for sighted users and the `<iframe>` carries a `title`. A `<label for="card-element">`
  pointing at the mount div looks right, validates as nothing, and names no control. Errors from the
  provider go into **your** error region for the field, in text (3.3.1), never a colour change on the
  border alone.
- **Responsive:** one column, always — see the Checkout anatomy in
  [page-anatomies.md](page-anatomies.md#checkout--the-purchase-flow). A two-column payment block
  produces an ambiguous tab order across a boundary you do not control.

## Promo / discount code
- **No upstream at all.** APG has no coupon, promo or "apply code" pattern, so everything here is
  **ours** except the two HTML-spec lines, which say so.
- **It is a second submission next to one you already have, and that is the whole difficulty.** Two
  rules from the HTML Standard settle the shape. A nested `<form>` is invalid — the `form` element's
  content model is *"Flow content, but with no `form` element descendants"* — so the code field cannot
  simply get its own form inside the checkout form. And *"a form element's default button is the first
  submit button in tree order whose form owner is that form element"*, so an "Apply" button dropped
  into the checkout form **becomes its default button**: Enter in the email field then applies an
  empty code. Both failure modes are silent. **Ours: the code entry is its own `<form>`, a sibling of
  the checkout form, never a descendant** — the order summary is a separate region, so this costs
  nothing in layout and gives each form its own default button. Better still, put it on the **cart**,
  before a checkout form exists at all. What you must not do is make it a `type="button"` driven by
  Stimulus: that removes it as the default button and leaves Enter in the code field *placing the
  order*, which is the worst of the three.
- **The result must be announced, and the amount is the announcement.** A code that applies changes a
  total elsewhere on the page. Put `role="status"` on the summary total, not on the code field — the
  role carries polite **and** atomic, so the user hears "Total £42.00" rather than "42.00". Same
  mechanism as the cart total; do not add a second live region for the code field.
- **A rejected code is an input error, not a toast.** 3.3.1 Error Identification (A): *"If an input
  error is automatically detected, the item that is in error is identified and the error is described
  to the user in text."* The message belongs beside the field via the simple_form error slot. A toast
  is dismissible and unassociated, so it satisfies neither half.
- **Never clear the field on failure**, and never make the user retype a code that worked — 3.3.7
  Redundant Entry (A) is about the same information *"required to be entered again in the same
  process"*, and a code silently dropped between steps is exactly that.
- **Ours: no auto-apply on blur or on keystroke.** Applying a discount changes a financial total, so
  it is an explicit press. Be precise about what carries that rule: the **money** does, not 3.2.2 On
  Input. A total restreamed in place without moving focus is a change of *content*, and WCAG says
  *"a change of content is not always a change of context"* — the boundary is stated once, in
  [Cart drawer and cart line](#cart-drawer-and-cart-line). The [Stepper](components.md#stepper--wizard) is the case
  where 3.2.2 genuinely applies, because advancing a step moves focus.
- `cluster` of a labelled `text` input (`uppercase` styling only — never `text-transform` on the
  value you send) and a `secondary` Button. The label is visible; "Promo code" as a placeholder is the
  usual failure and disappears the moment anyone types.
- **Responsive:** the cluster wraps to two rows on a narrow viewport rather than shrinking the input
  below its `min-h-touch` height.

## Plan comparison / feature matrix
- **One mechanism for two surfaces.** The marketing [Pricing](page-anatomies.md#pricing) page and the
  signed-in [Plans](page-anatomies.md#plans--compare-and-switch) page render the same matrix; only the
  surrounding state differs. Building a second one is the duplication this catalogue exists to stop.
- **No APG pattern, and the two table-shaped ones tell you to stay native.** The index lists 30;
  "comparison", "pricing" and "matrix" are not among them. APG's **Table** is *"a static tabular
  structure … it is not an interactive widget"*, and **Grid** is *"particularly useful if the tabular
  information is editable or interactive"*. A plan matrix is neither. So: a plain `<table>` with **no**
  `role="table"`, no `role="grid"`, no ARIA row/cell roles — the native element already exposes them,
  and adding the roles by hand is how you lose the ones you forgot. Escalate to `grid` only if cells
  become editable or need arrow-key traversal.
- **`scope` is sufficient until a header spans, and then it stops being sufficient.** H63 is *"sufficient
  … for making information and relationships conveyed through presentation programmatically
  determinable"* (SC 1.3.1, **Level A**) and its own note draws the line: *"For simple tables that have
  the headers in the first row or column, it is sufficient to simply use the `th` elements without
  `scope`. For complex tables use `id`s and `headers`."* H43's trigger is exact — *"used when data cells
  are associated with more than one row and/or one column header."* A flat matrix (feature names down,
  plan names across) is `scope="row"` + `scope="col"`. Add one grouping header spanning two plan
  columns and you are in H43: `headers`/`id`, not more `scope`.
- **A `✓` cell needs a text alternative, and the reason is not "it's an icon".** It needs one even as
  the literal character U+2713, because WCAG's definition of non-text content is a two-branch test:
  *"any content that is not a sequence of characters that can be programmatically determined **or where
  the sequence is not expressing something in human language**"*. A tick meaning "included" is a
  character used pictorially, not linguistically — the same branch that catches emoticons and ASCII
  art — so **SC 1.1.1 (Level A)** applies. Pair the glyph with `sr-only` text carrying the *meaning*
  ("Included" / "Not included"), never the shape ("check mark"). Same reasoning as
  [Reviews + Rating](components.md#reviews--rating); 1.4.1 enters only if a colour, not a glyph, is what
  distinguishes the two states.
  **Boundary worth recording:** WCAG's note names ASCII art, emoticons and leetspeak — it does not
  name symbol glyphs. This follows from the definition's second clause by direct analogy, and is
  stated that way rather than as a criterion that names checkmarks.
- **1.1.1 and 1.3.1 are different failures and neither covers the other.** 1.1.1 asks whether the cell
  has an equivalent name; 1.3.1 asks whether that cell is associated with its feature row and its plan
  column. A matrix can announce "Included" perfectly and still be useless because nothing says
  *included in what, on which plan*.
- **The recommended plan needs a non-colour signal.** 1.4.1 Use of Color (**Level A**): *"Color is not
  used as the only visual means of conveying information."* A ring or tint on the recommended card,
  with no label, is the Understanding document's own failure shape (*"knowing whether an outline is
  green for valid or red for invalid"*). A `Ui::Badge` reading "Recommended" is what carries the
  meaning; the tint is then reinforcement. The identical rule governs a subscription status chip —
  the word, not the hue.
- **`aria-sort` on at most one header, and only if the matrix really sorts.** ARIA: *"Authors SHOULD
  only apply this property to table headers or grid headers"* and *"For each table or grid, authors
  SHOULD apply `aria-sort` to only one header at a time."* A plan matrix normally sorts by nothing.
- **`<caption>` is optional in HTML and sufficient for 1.3.1 (H39).** Use it — `sr-only` if the design
  has no visible title — because a table announced with no name is one of several on a billing page.
- **Responsive — and here the honest answer is that WCAG permits both.** 1.4.10 Reflow (**AA**)
  excepts *"parts of the content which require two-dimensional layout"*, and its Note 2 names them:
  *"data tables (not individual cells) … It is acceptable to provide two-dimensional scrolling for
  such parts of the content."* So **horizontal scroll of a wide matrix does not fail 1.4.10**, and any
  doctrine implying it does is wrong. Our preference for a card-stack fallback on phones
  (`mobile.md`) is **ergonomics — ours — not conformance**; say which you chose and why, and do not
  cite a criterion for it. Below the fold on a phone, prefer one column per plan stacked in full over
  a matrix scrolled sideways: the reader is comparing, and a comparison you have to scroll to make is
  not one.

## Seat / quantity selector
- **`type="number"` is defensible here, and it is the same spec note that made it wrong for a card.**
  The HTML Standard's test is whether a spinbox would make sense: it rules out input that *"happens to
  only consist of numbers but isn't strictly speaking a number"*, naming card numbers and postal codes.
  A seat count is strictly speaking a number, and the spec's own worked example for `min`/`max` is
  literally `<input name="quantity" required type="number" min="1" value="1">`. **Stated precisely: the
  spec names the exclusions, not the inclusions; this applies its stated test and leans on its own
  quantity example, rather than claiming HTML names seats.** See
  [Payment / card entry](#payment--card-entry) for the other half of the note.
- **There is a real disagreement here, and blending the two sources is the failure.** The **GOV.UK
  Design System** takes the opposite default: *"Do not use `<input type="number">` unless your user
  research shows that there's a need for it. With `<input type="number">` there's a risk of users
  accidentally incrementing a number when they're trying to do something else — for example, scroll up
  or down the page."* That hazard is real rather than theoretical: wheel-scroll-changes-the-value is
  **not in any spec** (it is an open WHATWG issue), Chrome and Safari do it, and **Firefox disabled it
  by default in 130** for exactly this reason. GOV.UK's current page gives no carve-out for
  incrementable numbers — the only exception is research-gated. **Ours: `type="number"` for a seat or
  quantity count, because the spinbox is genuinely useful there and the value is bounded and visible on
  the same screen as the total it changes — but if a project's own research says otherwise, `type=text`
  with `inputmode="numeric"` is a legitimate override, and it is a Project Override rather than a
  defect.** What is not legitimate is citing one source and pretending the other does not exist.
- **Add no ARIA.** `input type=number` already has the implicit ARIA role `spinbutton`, and *ARIA in
  HTML* allows *"No `role` other than `spinbutton`, which is NOT RECOMMENDED"*. Writing
  `role="spinbutton"` restates what the element gives you and is the first thing to go stale.
- **A visible `<label>`, always.** "Qty" as a placeholder disappears on the first keystroke, and a
  bare number beside a product name announces as nothing. Use the shipped field anatomy
  ([forms.md](forms.md)) so label, hint and error markup match every other field.
- **`+` / `−` buttons are optional and, if present, are named.** They are icon-only controls: each
  needs an accessible name that says what it changes ("Increase quantity, Blue T-shirt"), and both
  need `min-h-touch`. They never replace the input — a keyboard user typing `12` must not have to
  press a button twelve times.
- **Never submit on change — and this is ours, because 3.2.2 does not reach as far as it looks.** The
  criterion (**Level A**) reads *"Changing the setting of any user interface component does not
  automatically cause a change of context unless the user has been advised of the behavior before using
  the component"*, and **change of context** is defined narrowly: *"user agent; viewport; focus; content
  that changes the meaning of the web page"*, with *"a change of content is not always a change of
  context"* stated outright. A seat count that streams a new total into place without moving focus is a
  change of content, so 3.2.2 permits it. **We forbid it anyway because it changes what the customer
  pays** — the same rule the promo field follows, for the same reason. The
  [Stepper](components.md#stepper--wizard) is the neighbouring case where 3.2.2 *does* apply, because advancing a
  step moves focus; the boundary is stated once in
  [Cart drawer and cart line](#cart-drawer-and-cart-line).
- **`min`, `max` and `step` are submission-time gates, not input-time barriers — and the spec is
  explicit about which.** They produce the validity states *"suffering from an underflow"*,
  *"suffering from an overflow"* and *"suffering from a step mismatch"*, each defined in terms of a
  value the control **already has** — so the UA lets the out-of-range value be typed and then refuses
  the submission. (Only `type=range` clamps; the number state has no such step.) A `max` reflecting a
  licence ceiling therefore shapes the control and blocks the honest path, and defends nothing against
  a request that never touches your form. **The server clamps.** Same reasoning as the idempotency key
  in
  [component-implementations.md](component-implementations.md#payment-container-and-promo-code--recipes-not-components):
  a client-side constraint is feedback, never the guard.
- **The recalculated figure is the announcement.** Changing seats changes a total elsewhere on the
  page; `role="status"` goes on the total, not on the input — polite and atomic together, so the
  announcement carries "Total £240.00" and not a bare "240.00". One live region for the money; do not
  add a second on the field.
- **Responsive:** the input keeps `min-h-touch` and does not shrink below it to fit a `+`/`−` pair; on
  a narrow viewport the cluster wraps instead.

## Saved payment methods
- **You will not have a full card number to render, and that is the design working.** The provider
  returns a token plus a brand and last four; nothing card-shaped reaches your DOM, params or logs
  ([Payment / card entry](#payment--card-entry)). Where a system *does* hold a PAN, PCI DSS v4.0.1
  Requirement **3.4.1** is the ceiling: *"PAN is masked when displayed (the BIN and last four digits
  are the maximum number of digits to be displayed), such that only personnel with a legitimate
  business need can see more than the BIN and last four digits of the PAN."* Note what that permits —
  BIN **and** last four is the maximum, so showing last four alone is comfortably inside it.
- **"We use a processor, so 3.4.1 doesn't apply" is true only under a condition worth naming.** The
  requirement has no carve-out for tokenised merchants; what puts a saved-card list outside its reach
  is that such a system never handles a PAN at all. **If any code path — server or client — receives,
  forwards or briefly holds the raw number before tokenising it, that path is in scope and 3.4.1
  governs anywhere it might display more.** A redirect or provider-iframe integration keeps you out;
  a "collect then forward" one does not. **Framing, not a compliance determination** — scope is your
  acquirer's and QSA's call, the same boundary the payment entry draws.
- **A card brand rendered as a mark still needs its name.** An `<svg>` logo is unambiguously non-text
  content under 1.1.1 (**Level A**): give it an accessible name that is the brand ("Visa"), and let the
  visible text carry "ending 4242". "Card" is not a name when there are four of them.
- **The default method is a single-select of real radios, not a widget.** `fieldset` + `legend`
  ("Default payment method") with native `<input type="radio">` per card. This is deliberately *not*
  the `role="radiogroup"` Button group: that one is for switching a view, and this one changes which
  instrument gets charged. A control that commits money is a form control.
- **A remove control names the card it removes.** `aria-label="Remove Visa ending 4242"` — the same
  rule as a cart line, and for the same reason: four icon-only `×` buttons all announce as "button".
- **Removing a saved method is inside 3.3.4** (Error Prevention — Legal, Financial, Data, **Level
  AA**), which covers pages that *"cause legal commitments or financial transactions for the user to
  occur, that modify or delete user-controllable data in data storage systems"*. Deleting a stored
  record is the clean case — the Understanding document's own example is *"deleting a record of past
  invoices"*. Satisfy **Confirmed** with a confirmation that says what stops — "this is the card your
  Team plan is billed to" — not a generic "Are you sure?". Removing a spare card still needs the
  criterion met; what changes is how much the confirmation has to say.
- **Adding a method is the provider's surface, not a form you build.** It reuses the payment container
  contract in full, including the rule that the accessible name must be set *inside* the frame.
- **An expiring card is a text state, not a red border.** "Expires 04/26 — expiring soon" beside the
  card; colour may reinforce it and may not carry it (1.4.1).

## Subscription state and dunning
- **The state is a word. The colour is decoration.** Active, past due, cancelled, trialling — each
  renders as text inside a `Ui::Badge`, because 1.4.1 Use of Color (**Level A**) forbids colour as
  *"the only visual means of conveying information"*. Three identically-shaped chips differing only in
  hue is the failure, and it is the most common one on a billing page.
- **A past-due banner rendered with the page must not rely on `role="alert"` to be heard — and this
  one is a decision, because the sources disagree.** APG documents the behaviour: *"at this time,
  screen readers do not inform users of alerts that are present on the page before page load
  completes."* **ARIA 1.3 says close to the opposite** — *"The exception to this live region convention
  is `alert` … its content is announced by assistive technology when the alert is rendered on the page
  and when the content changes"* — but ARIA 1.3 is a **Working Draft**, ARIA 1.2 (the Recommendation)
  is silent on load timing, and APG's sentence is a report of what screen readers *do*, hedged with
  *"at this time"* precisely because it is empirical. **There is no normative MUST here in either
  direction; do not write one.** Ours: a state that is already true when the page loads belongs in the
  **reading order** — a real heading and text at the top of the page, which everyone reaches
  regardless of which document turns out to describe the future. Reserve `role="alert"` for a state
  that *changes* while the user is on the page: a retry that fails, a payment that clears. The failure
  this avoids is a banner that is loud in the design and silent in a screen reader.
- **An alert never takes focus.** APG: *"Because alerts are intended to provide important and
  potentially time-sensitive information without interfering with the user's ability to continue
  working, it is crucial they do not affect keyboard focus."* Moving focus to a dunning banner
  interrupts whatever the customer was doing to fix it.
- **Four things or it is not a dunning notice: what happened, how much, by when, and one action.** "We
  could not charge your card", the amount, the date access changes, and a single primary control that
  fixes it. A notice without the deadline is an anxiety generator; a notice with three equal buttons is
  a decision the customer cannot make.
- **The retry schedule is billing logic, not UI doctrine.** How many times a provider retries and over
  how many days belongs to the app and its processor. What this kit fixes is that the *current* state
  is always readable on the billing page — never only in an email, which is the one surface you cannot
  guarantee arrived.
- **A cancelled subscription still has a page.** It says when access ends (or ended) and offers one
  route back. An account that cancels and then sees an empty billing page cannot resubscribe.
- **Downloading an invoice needs no format-and-size announcement, and no technique asks for one.**
  Stating "(PDF, 240 KB)" is **not a WCAG requirement at any level, and not a sufficient or advisory
  technique for 2.4.4 either** — the criterion asks only that the link's purpose be determinable, which
  "Invoice INV-0142" already satisfies. (G201, often cited here, is about warning before opening a new
  window; it says nothing about file metadata.) Write it if the design wants it; do not cite a
  criterion for it, and do not let a checklist demand it.
- **`download` is same-origin in practice.** The attribute *"indicates that the author intends the
  hyperlink to be used for downloading a resource"*, and its value names the suggested filename — but
  *"in cross-origin situations, the `download` attribute has to be combined with the
  `Content-Disposition` HTTP header … with the attachment disposition type"*, or the browser navigates
  instead. An invoice served from a signed cloud-storage URL is the cross-origin case, so the header
  is the server's job, not a markup fix.
