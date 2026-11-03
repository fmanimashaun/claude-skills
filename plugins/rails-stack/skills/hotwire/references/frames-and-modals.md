# Frames, form responses and the modal flow

Versions in scope: Turbo 8.0.23, Rails 8.0.x. Every mechanism below was verified on 2026-10-21/22 by `doctrine-verifier` against the Turbo source at tag v8.0.23, with the
quoted phrases matched to the raw files (`src/core/frames/frame_controller.js`, `frame_view.js`, `src/core/drive/form_submission.js`, `navigator.js`,
`src/observers/stream_observer.js`). Re-verify before relying on it past a major version of Turbo.

## Contents
1. A frame is matched by id
2. What a form response must be: a Drive submit and a frame submit differ
3. A stream answer, and the HTML fallback
4. The modal flow (one shared frame)
5. What the checks enforce (`check_turbo_flow.py`)

---

## 1. A frame is matched by id

A link or form inside `<turbo-frame id="x">` loads its response, and Turbo takes the **matching** `<turbo-frame id="x">` out of it and swaps that in. The response
must contain a frame with the same `id` (in Rails, `turbo_frame_tag dom_id(record)` on both pages).

- **No matching frame** → Turbo dispatches a cancelable `turbo:frame-missing` event. If nothing cancels it, the frame shows its default text, "Content missing"
  (`frame_view.js`), and Turbo raises `TurboFrameMissingError`. An app can handle the event (for example to turn the failure into a visit) instead.
- **Leaving the frame**: `data-turbo-frame="_top"` on a link or form promotes the navigation to a full page visit. A show page linked from inside a frame needs it,
  or the response has no matching frame.
- **Duplicate ids on one page** break targeting: a Turbo Stream `target` is looked up with `getElementById`, so only the first element with that id is found. Give
  every repeated element `dom_id(record)`.

## 2. What a form response must be: a Drive submit and a frame submit differ

- **A Turbo Drive (whole page) form submission must redirect.** `navigator.js` builds it with `mustRedirect` true, and a non-GET **2xx** response that is not a
  redirect raises "Form responses must redirect to another location" (`form_submission.js`): the form appears to do nothing. So a successful submit answers
  `redirect_to ..., status: :see_other`, and a failed one re-renders with `status: :unprocessable_entity` (or `:unprocessable_content`; 422 either way, see
  `turbo.md` §1 for which Rack versions accept which symbol). A 4xx or 5xx goes to the failed-submission path and is rendered, so it needs no redirect.
- **A form submission made from inside a frame is not required to redirect.** `frame_controller.js` creates its `FormSubmission` without `mustRedirect`, so a 200
  HTML response is rendered into the frame. (The old line in `turbo.md`, "forms inside frames still need 303/422 statuses", was wrong for the 303 half and is
  corrected.) The response still has to contain the matching frame (§1), or the frame shows the missing-frame error, success or failure alike.

## 3. A stream answer, and the HTML fallback

A form that Turbo submits sends `Accept: text/vnd.turbo-stream.html` first. If the response is a stream, `StreamObserver` takes it on `turbo:before-fetch-response`,
calls `preventDefault()` and applies it to the page: **the frame never loads that response**, so a stream can change the list and clear the frame from outside it
(`turbo_stream.update("modal", "")`, `turbo_stream.prepend("invoices", ...)`).

**Keep an HTML branch.** An action that answers `format.turbo_stream` also answers `format.html` (usually a redirect): a client without Turbo, or a request whose
stream answer fails, otherwise gets no usable response.

## 4. The modal flow (one shared frame)

The design choice (create, edit and delete open in one in-page modal; a purchase is the full-page exception) is the design-system skill's
`references/crud-modal-pattern.md`; this section is the Turbo mechanism under it.

1. The layout holds one empty `<turbo-frame id="modal"></turbo-frame>`.
2. A trigger link carries `data-turbo-frame="modal"`: `link_to "New", new_invoice_path, data: { turbo_frame: "modal" }`. The page does not navigate; the response
   loads into the shared frame.
3. **The template that link reaches renders inside `turbo_frame_tag "modal"`** (`new`, `edit`, a delete confirmation). Without it there is no matching frame and
   the modal shows "Content missing" and nothing opens (§1).
4. The form inside posts with `data-turbo-frame="_top"` so its answer can be a stream against the whole page (§3).
5. **Failure**: render the form again with status 422. Either re-render it into the frame (the response contains a matching `<turbo-frame id="modal">`; without
   one it is the missing-frame error, not a page replacement) or answer with a stream that updates the frame.
6. **Success**: a stream that clears the frame and changes the list, or a redirect visited with `data-turbo-frame="_top"`. A redirect that stays in the frame is followed
   inside it and needs a matching frame, so the modal would stay open or error.

## 5. What the checks enforce

`scripts/check_turbo_flow.py` (the `turbo-flow` row of `checks.json`) reads the source, never runs it:

| rule | finding |
|---|---|
| a `link_to`/`button_to` with a `modal` turbo-frame target | the template its path helper reaches (`new_invoice_path` → `app/views/invoices/new.*`, `delete_confirmation_invoice_path` → `.../delete_confirmation.*`) must render inside `turbo_frame_tag "modal"`; a helper that maps to no template is counted as "not located" |
| `render :new` / `render :edit` (or the string forms) | needs a `status:` in the same statement: `:unprocessable_entity`, `:unprocessable_content`, 422, or an explicit `:ok` for a GET |
| a `respond_to` block with `format.turbo_stream` | needs `format.html` or `format.any` in the same block |

**Limits, stated plainly:** it cannot tell whether a `render :new` is on a failed-save branch (every one without a status is reported; give a GET an explicit
`status: :ok`); a modal link built at run time is not seen; and the rendered-page half (a crawl judge for `turbo:frame-missing` and `.turbo-frame-error`) is not
here, because it needs a Turbo-specific judge seam in the neutral qa-flow.
