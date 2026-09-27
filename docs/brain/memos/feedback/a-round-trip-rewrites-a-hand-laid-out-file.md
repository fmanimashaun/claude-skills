---
name: feedback-a-round-trip-rewrites-a-hand-laid-out-file
description: json.load/dump on component-shapes.json produced a 1,032-line diff for three additions; the gate passed anyway. Insert textually into hand-formatted data files.
type: feedback
---

Adding three entries to `skills/design-system/references/component-shapes.json` via `json.load` → `json.dump(indent=2)` reformatted every entry (its native layout packs `"shape"` and `"width"` on one line and `parts` arrays across wrapped lines). `check_component_shapes.py` was green over the rewrite, so only the diff stat showed it: 1,032 insertions, 198 deletions for 23 lines of intent.

**Why:** a parser round-trip preserves semantics, not layout, and the gates here check semantics. A reviewer then cannot see the three additions inside a thousand-line reflow, which is the same class as [[edit-python-structurally-with-ast]] in the other direction: there the text edit ate code; here the structural edit ate the layout.

**How to apply:** for any hand-laid-out data file (the shapes sidecar, `marketplace.json`, CHANGELOG), insert text at an exact anchor with an asserted unique match, then `json.loads` the result to prove validity, then check `git diff --stat` shows only the lines you meant. Revert and redo if the stat is bigger than the intent.

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-round-trip-rewrites-a-hand-laid-out-file.md._
