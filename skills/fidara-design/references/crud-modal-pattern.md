# CRUD is modal-driven and in-page (the Fidara pattern)

In Fidara apps, **create / edit / delete never navigate to a separate `new` / `edit` / `show`
page.** They open in a **modal on the current page**; on success the modal closes and the
list updates in place via **Turbo Stream** — the user never loses their place, scroll, or
context. This is the pattern the reference apps use throughout (a persistent
`<turbo-frame id="modal">`, links carrying `data-turbo-frame="modal"`, a
`_delete_confirmation_modal`). **Modal and Card are therefore the backbone components** — the
list is Cards (or a table of `dom_id`-addressable rows), and every mutation happens through a
Modal. Treat full-page CRUD forms as a defect in a Fidara UI.

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
       <%= form_with model: @invoice, data: { turbo_frame: "_top" } do |f| %>
         <div class="stack" style="--space: var(--space-s)">
           <%= render(Ui::FieldComponent.new(form: f, name: :amount, label: "Amount")) %>
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
   `form_with` posts via Turbo. `data-turbo-frame="_top"` on the form lets the **create/update
   response drive a Turbo Stream against the whole page** (list + modal), not just the frame.
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
         turbo_stream.prepend("toasts", ToastComponent.new(intent: :success, message: "Invoice created"))
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
     turbo_stream.prepend("toasts", ToastComponent.new(intent: :success, message: "Invoice deleted"))
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
- **Destructive actions get a confirmation modal**, not just `turbo-confirm`.
- **The list is Cards or `dom_id` rows.** Rows/cards must be individually addressable so
  streams can target them. Host card lists in `grid-auto`.
- **One modal at a time** — the single shared `id="modal"` frame enforces this; the
  dismissable-layer stack handles nested popovers/dropdowns inside the modal.
- a11y is inherited from the Modal component (`role="dialog"`, `aria-modal`, labelled title,
  trap + Esc + restore) — don't re-implement it per screen.
