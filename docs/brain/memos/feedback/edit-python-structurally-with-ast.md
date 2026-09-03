---
name: feedback-edit-python-structurally-with-ast
description: Never remove or replace a Python definition by text offsets or paren counting — walk ast for lineno/end_lineno, then diff the symbol list.
type: feedback
---

Three times in one session I cut too wide replacing Python definitions by text slicing, and each
time took unrelated code with it: deleting `def call_pen` to the next `def` swallowed the
module-level `ADAPTERS`/`KEYLESS` between them; paren-matching a guard block swallowed the unrelated
`asset_plan` guard (23 mutations); slicing `load_config` to the next `def` lost `classify_risk`,
`graph_edges` and `record`.

**Why:** module-level statements live between functions, and a paren counter cannot see parens
inside strings. Reading the resulting diff does not reveal it — the removed code is far from the
edit and looks like context.

**How to apply:** parse with `ast`, find the node, use its `lineno`/`end_lineno` to splice. Then
**verify by diffing the symbol list against `origin/dev`**, not by reading the diff:

```python
cur = {n.name for n in ast.walk(ast.parse(open(p).read())) if isinstance(n, ast.FunctionDef)}
```

Related: [[verify-counts-before-stating-them]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, edit-python-structurally-with-ast.md._
