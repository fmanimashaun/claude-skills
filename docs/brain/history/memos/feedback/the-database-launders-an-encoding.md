---
name: feedback-the-database-launders-an-encoding
description: A value written in the wrong encoding comes back from Postgres as UTF-8, so a round-trip assertion cannot test encoding handling.
type: feedback
---

`ActionDispatch::Http::UploadedFile#read` returns **ASCII-8BIT**, so every value parsed out of an
uploaded CSV is binary. An example that wrote an accented name from a binary file and asserted
`record.reload.name == "Chiamaka Ọlámidé"` **passed with the normalisation removed** — Postgres
returns UTF-8 whatever went in, so the round trip fixes the encoding and the assertion tests the
database rather than the code.

**Why:** it reads like a strong end-to-end assertion and is a tautology. The mutation surviving was
the only signal.

**How to apply:** to test encoding handling, assert the thing a round trip cannot repair. For
Retask that was: a **latin-1** export (invalid UTF-8) must be refused cleanly rather than reaching
Postgres and dying with `PG::CharacterNotInRepertoire`. Keep a companion example proving valid
UTF-8 with diacritics still reads, so the refusal is about encoding and not about non-ASCII.

Two related byte-level traps in the same code path: Ruby's `CSV` does **not** strip a UTF-8 BOM
from a String (only from an IO opened `bom|utf-8`), and a BOM renames the first column — Excel's
default export would have silently blanked one field for every row while every other column read
correctly. And a `"\xEF\xBB\xBF"` literal in a UTF-8 source file cannot be compared against a
binary string without `.b`. Related: [[active-storage-reads-the-bytes]],
[[a-harness-that-cannot-see-a-broken-mutation]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, the-database-launders-an-encoding.md._
