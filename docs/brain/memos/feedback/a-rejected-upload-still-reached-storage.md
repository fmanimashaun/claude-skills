---
name: feedback-a-rejected-upload-still-reached-storage
description: An Active Storage validation rejects the record but the bytes are already uploaded — judge the file with Marcel before attaching.
type: feedback
---

A model validation on an attachment (`content_type`, `byte_size`) runs **after** Active Storage has
uploaded the file. So a rejected upload leaves bytes in storage with no row referencing them — an
orphan nobody will ever look for. Three attempts at Retask, each looking finished:

1. **Attach inside a transaction, purge in a rescue.** The rollback removed the blob and attachment
   rows; the purge then found nothing attached and **skipped itself**. File left on disk — measured
   by subscribing to `service_upload.active_storage` and checking the key.
2. **Attach outside the transaction, purge when invalid.** Still nothing to purge: the validation
   makes the parent's `save` fail, so the rows are never written — while the bytes have already gone.
3. **Judge the bytes before attaching.** `Marcel::MimeType.for(io)` is the same sniffer Active
   Storage uses to identify a blob, so it reaches the same verdict with no upload. Size from
   `io.size`. Then attach.

**Why the tests could not see it:** asserting `attached?` or `Blob.count` passes in all three
versions, so the mutation deleting the purge survived every time. The only signal that distinguishes
"refused before storage" from "stored then cleaned up" is the `service_upload.active_storage`
notification.

**How to apply:** for any user-supplied attachment, sniff and size-check the incoming IO first and
raise before `attach`; keep the model validation as the belt for other callers. Test it with
`ActiveSupport::Notifications.subscribed(..., "service_upload.active_storage")` and assert **no
upload fired** — and include a fixture whose declared content type LIES, since the declaration is
never what gets stored ([[active-storage-reads-the-bytes]]).

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-rejected-upload-still-reached-storage.md._
