# CRUD is modal-driven and in-page (the Fidara pattern)

In Fidara apps, **create / edit / delete never navigate to a separate `new` / `edit` / `show`
page.** They open in a **modal on the current page**; on success the modal closes and the
list updates in place via **Turbo Stream** — the user never loses their place, scroll, or
context. This is the pattern the reference apps use throughout (a persistent
`<turbo-frame id="modal">`, links carrying `data-turbo-frame="modal"`, a
`_delete_confirmation_modal`). **Modal and Card are therefore the backbone components** — the
list is Cards (or a table of `dom_id`-addressable rows), and every mutation happens through a
Modal. Treat full-page CRUD forms as a defect in a Fidara UI — with **one** scoped exception, named
and reasoned at the end of this file. Silence there would leave two shipped rules contradicting each
other, because the checkout anatomy is a full-page form.

Modal component + `modal_controller` live in
[component-implementations.md](component-implementations.md); Card in
[reference-implementation.md](reference-implementation.md). This file is the **flow that wires
them into CRUD**.

## The five pieces

1. **One persistent modal frame** in the app layout (already in the base layout):
   ```erb
   <turbo-frame id="modal"></turbo-frame>   <%# empty until a trigger fills it %>
   ```
2. **Triggers target that frame** — links/buttons for new/edit/delete, no full nav:
   ```erb
   <%= link_to "New invoice", new_invoice_path, data: { turbo_frame: "modal" },
         class: "..." %>  <%# render Ui::ButtonComponent in real code %>
   <%# per row: %>
   <%= link_to "Edit", edit_invoice_path(invoice), data: { turbo_frame: "modal" } %>
   <%= link_to "Delete", delete_confirmation_invoice_path(invoice), data: { turbo_frame: "modal" } %>
   ```
3. **`new`/`edit` render INTO the frame** — the view's root is a matching turbo-frame wrapping
   the Modal + form, so Turbo swaps it into the layout frame and the modal appears in-page:
   ```erb
   <%# invoices/new.html.erb (and edit.html.erb, same shape) %>
   <%= turbo_frame_tag "modal" do %>
     <%= render(Ui::ModalComponent.new(size: :md)) do |m| %>
       <% m.with_title { @invoice.new_record? ? "New invoice" : "Edit invoice" } %>
       <%= simple_form_for @invoice, html: { data: { turbo_frame: "_top" } } do |f| %>
         <div class="stack" style="--space: var(--space-s)">
           <%= f.input :amount %>
           <%# ...fields... %>
         </div>
         <% m.with_actions do %>
           <%= link_to "Cancel", "#", data: { action: "modal#close" } %>
           <%= f.submit "Save" %>   <%# Ui::ButtonComponent in real code %>
         <% end %>
       <% end %>
     <% end %>
   <% end %>
   ```
   **Every form and form element goes through simple_form** — that is what keeps field markup,
   labels, hints and error styling identical across the whole codebase, so it is a hard rule, not a
   preference. `f.input` renders the entire field from the wrapper configured in
   `config/initializers/simple_form.rb`; never hand-roll label/input/error markup, and never wrap a
   control in a bespoke field component. HTML attributes ride in `html:` (simple_form follows
   `form_for` conventions, so a top-level `data:` is not forwarded).
   The form still posts via Turbo. `data-turbo-frame="_top"` lets the **create/update response
   drive a Turbo Stream against the whole page** (list + modal), not just the frame.
4. **Success responds with a Turbo Stream** that closes the modal and mutates the list — the
   only place the list changes. Nothing re-renders the whole index:
   ```ruby
   # InvoicesController#create
   def create
     @invoice = Invoice.new(invoice_params)
     if @invoice.save
       render turbo_stream: [
         turbo_stream.prepend("invoices", partial: "invoices/invoice", locals: { invoice: @invoice }),
         turbo_stream.update("modal", ""),                       # empty the frame → modal gone
         turbo_stream.prepend("toasts", ToastComponent.new(intent: :success, title: "Invoice created"))
       ]
     else
       # re-render the form INTO the modal frame with inline errors, HTTP 422
       render turbo_stream: turbo_stream.update("modal",
         partial: "invoices/form_modal", locals: { invoice: @invoice }), status: :unprocessable_entity
     end
   end
   ```
   Edit → `turbo_stream.replace(dom_id(@invoice), ...)`. The list container is
   `<div id="invoices">` (or `turbo_frame_tag "invoices"`); each row is `id="<%= dom_id(invoice) %>"`.
5. **Delete uses a confirmation modal**, not a bare `data-turbo-confirm` — destructive actions
   get a real dialog (matches the reference apps' `_delete_confirmation_modal`):
   ```erb
   <%# invoices/delete_confirmation.html.erb — GET, rendered into the modal frame %>
   <%= turbo_frame_tag "modal" do %>
     <%= render(Ui::ModalComponent.new(size: :sm)) do |m| %>
       <% m.with_title { "Delete invoice?" } %>
       <p class="text-muted-foreground">This can't be undone.</p>
       <% m.with_actions do %>
         <%= link_to "Cancel", "#", data: { action: "modal#close" } %>
         <%= button_to "Delete", invoice_path(@invoice), method: :delete,
               data: { turbo_frame: "_top" } %>   <%# destructive Button in real code %>
       <% end %>
     <% end %>
   <% end %>
   ```
   ```ruby
   # #destroy → remove the row + close + toast
   render turbo_stream: [
     turbo_stream.remove(dom_id(@invoice)),
     turbo_stream.update("modal", ""),
     turbo_stream.prepend("toasts", ToastComponent.new(intent: :success, title: "Invoice deleted"))
   ]
   ```

## `modal_controller.js` (composes the mixins)

The Modal component's `data-controller="modal"` is this — focus-trap + dismissable-layer +
restore, so the frame-swapped dialog is instantly accessible. It closes by **emptying the
frame** so the same frame is reusable:

```js
import { Controller } from "@hotwired/stimulus"
import { focusTrap } from "mixins/focus_trap"
import { dismissableLayer } from "mixins/dismissable_layer"

export default class extends Controller {
  static targets = ["panel"]
  connect() {
    this.trap = focusTrap(this.panelTarget); this.trap.activate()
    this.layer = dismissableLayer(this.panelTarget, () => this.close()); this.layer.open()
  }
  disconnect() { this.trap.deactivate(); this.layer.close() }   // fires when the frame empties
  backdrop(e) { if (e.target === e.currentTarget) this.close() }
  close() {
    this.trap.deactivate(); this.layer.close()
    const frame = this.element.closest("turbo-frame")
    if (frame) frame.innerHTML = ""; else this.element.remove()   // reset the reusable frame
  }
}
```

Because `disconnect()` tears down the trap/layer, a Turbo Stream that does
`turbo_stream.update("modal", "")` cleans everything up for free — no leaked listeners, focus
restored to the trigger.

## Rules

- **No `new`/`edit`/`show` full-page routes for CRUD** in a Fidara UI. Those actions render
  into the modal frame. (A dedicated show *page* is fine for a genuine detail view, but the
  edit/delete on it still open modals.)
- **Success mutates the list via Turbo Stream only** — prepend (create) / replace `dom_id`
  (update) / remove `dom_id` (delete) — never a full index re-render. Pair every mutation with
  a **toast**.
- **Failure re-renders the form into the modal frame at HTTP 422** with inline field errors;
  the modal stays open.
- **Destructive actions get a confirmation modal**, not just `turbo-confirm` — scoped as below.
- **The list is Cards or `dom_id` rows.** Rows/cards must be individually addressable so
  streams can target them. Host card lists in `grid-auto`.
- **One modal at a time** — the single shared `id="modal"` frame enforces this; the
  dismissable-layer stack handles nested popovers/dropdowns inside the modal.
- a11y is inherited from the Modal component (`role="dialog"`, `aria-modal`, labelled title,
  trap + Esc + restore) — don't re-implement it per screen.

### A confirmation is for what cannot be undone

The delete rule above was written unscoped, and the worked example above it says *"This can't be
undone"* — which is the actual condition, stated in the fixture and not in the rule. Left that way it
reads as *every* removal gets a dialog, and an agent building a basket then puts "Are you sure you want
to remove Blue T-shirt?" in front of a customer six times. Confirmation fatigue is not a smaller defect
than a missing confirmation; it is the one that teaches people to click through the dialog that mattered.

**The condition is reversibility, not destructiveness.**

| | Confirmation modal | Immediate + undo |
|---|---|---|
| Deleting an invoice, a member, a saved payment method | **yes** — the record is gone | no |
| Cancelling a subscription | **yes** — access ends on a date | no |
| Removing a line from an open cart, clearing a filter, dismissing a draft | no | **yes** |

**Where a specification decides this, follow it; where none does, this is the decision.** Deleting a
stored record is inside WCAG 3.3.4 Error Prevention (Legal, Financial, Data) (**Level AA**) — its
Understanding document's own example is *"deleting a record of past invoices"* — and
`components.md` → Saved payment methods already applies it. A **cart line is genuinely undecided by the
sources**: the same document narrows the intent to *"prevent mass loss of data such as deleting a file
or record"* and excludes *"the simple creation or editing of documents, records or other data"*, and no
W3C text rules on an open cart either way. That verdict was INCONCLUSIVE, so the position is **our
decision, recorded on [#91](https://github.com/fmanimashaun/claude-skills/issues/91)**: a cart line is
draft data, removal is immediate, and the undo is what pays for skipping the dialog.

**"Immediate + undo" is a contract, not a softer option.** It means the toast carries a real control
that restores the line — same position, same quantity — and that the server can honour it. A toast
reading "Removed" with no way back is worse than the dialog it replaced, because it took the
confirmation away and gave nothing in return. No specification requires an undo anywhere (3.3.4 offers
**Reversible / Checked / Confirmed** as alternatives, and 3.3.6 is Level AAA), so this is a promise we
are choosing to make and must therefore keep.

## The one exception: the purchase flow is full-page

**The checkout / purchase flow is a full-page, multi-step form, not a modal.** It is the only
exception in the kit, and it exists for reasons that are properties of the Modal component rather
than preferences:

- **A modal's dismiss affordances are wrong over a financial commitment.** Esc, a backdrop click and
  a close button are three ways to lose a part-entered order by accident. The Modal gives you all
  three and you cannot remove them without breaking the pattern for everything else.
- **The page behind is the thing being abandoned.** Keeping the shop visible and dimmed behind a
  purchase is an invitation to click back into it. Checkout strips the shell to the brand mark for
  the same reason.
- **The focus trap fights the payment provider.** Card fields are provider-owned iframes
  (`components.md` → Payment / card entry); a trap that owns focus inside the dialog and an iframe
  that owns focus inside itself are two managers of one thing.
- **Steps need addressable state.** A multi-step flow wants a URL per step so a refresh, a back
  button, or a return from a provider redirect lands somewhere real. The single shared `id="modal"`
  frame has one address.

**This is our architecture decision, recorded on
[#91](https://github.com/fmanimashaun/claude-skills/issues/91) — not an upstream rule.** No spec says
checkout may not be a dialog.

**It does not generalise.** A flow qualifies only if all four above hold; "it is long" or "it has
steps" is not enough — a long settings form is still a modal, and a multi-step import wizard inside
the app is still a modal. Edits *within* a purchase — change an address, remove a line — go back to
the modal pattern, because they are ordinary CRUD on a record the user is already looking at. The
anatomy is in
[page-anatomies.md](page-anatomies.md#checkout--the-purchase-flow).

### Worked negative: a plan change is a modal, and money is not the test

The obvious candidate for a second exception is the **plan change** — upgrade, downgrade, cancel. It
moves money, so the instinct is to reach for the full-page flow. Run it against the four conditions
and it fails three of them, which is the point of having conditions at all:

| Condition | Checkout | Plan change |
|---|---|---|
| Dismiss affordances are wrong over the commitment | yes | **yes** — this one does hold |
| The page behind is the thing being abandoned | yes | **no** — it is the billing page, which the user returns to either way |
| A focus trap fights a provider iframe | yes | **no** — an existing customer pays with the method on file; no iframe is mounted |
| Steps need addressable state | yes | **no** — it is one decision and one confirm, not a sequence with a URL per step |

So a plan change is **ordinary CRUD on a subscription record**: the plan list is the page, and the
change opens the shared modal frame with a confirmation that states the new price, the date it takes
effect, and what happens to the current period. **The financial weight is carried by the confirmation
step, not by the page shape** — that is what WCAG 3.3.4 asks for, and a modal satisfies *Confirmed*
exactly as well as a page does.

**The one case that flips it** is a plan change that must collect a **new payment instrument**,
because condition three then starts holding: mounting the provider's iframe inside a focus trap is
the failure the exception exists to avoid. Hand off to the checkout flow rather than embedding a
payment iframe in a dialog. The anatomy is in
[page-anatomies.md](page-anatomies.md#plans--compare-and-switch).

**This too is our architecture decision, recorded on
[#91](https://github.com/fmanimashaun/claude-skills/issues/91).** It is written down because the
opposite reading is reasonable, and an agent that reasons "money ⇒ full page" from the checkout
exception alone would build a second full-page flow every release.
