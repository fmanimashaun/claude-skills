---
name: feedback-run-the-canvas-to-port-it
description: Port a Claude Design canvas by executing its own JS (screen/modal builders) in Node and committing the dump as the app's data, instead of transcribing it twice.
type: feedback
---

When a Claude Design canvas ships its screens as code (`admin-core.js` with screen/detail/modal
builders), do not transcribe the JS into Ruby by hand a second time. Run the canvas's own functions in
Node with handlers swapped for descriptors (`{detail, id}`, `{modal, ctx}`, `{setState}`) and charts
swapped for their specs (`{__chart, sets: [{name, color, series: [key, base, vol]}]}`), write the result
to JSON, commit it beside the app (`app/models/admin_shell/canvas/`) and resolve it at render time.

**Why:** Retask v1 hand-ported 877 items in ~1,000 lines of Ruby; v3 had 3,294 items across three
canvases and the owner wanted every interaction. The dump made 43 screens, 23 details and 112 modals
render in a day, byte-reproducible from the canvas (`node screens_dump.mjs`), and the port report
became a script. Ruby stays for what depends on state (audit log, config, staff, role builder).

**How to apply:** make the harness reproducible (`make_core.py` → `core_dump.mjs`, a KEEP list for
the data tables, `+ '\n'` on writes) and prove `cmp` equality before claiming it; keep the harness
under `scripts/`, not `docs/` (docs-layout gate), but the imported modules must stay beside the
canvas (design-flow follows the import — fixed the contradiction in claude-skills #942). Mark copy the
JS produces only in unreached states as `deferred` with a reason, never as scaffolding. Related:
[[design-is-the-source-of-truth]], [[gate-the-commit-on-the-check]] (a `| tail -1` masked a failing
mutation guard and a broken guard was pushed — pipe through `if`, never through tail).

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, run-the-canvas-to-port-it.md._
