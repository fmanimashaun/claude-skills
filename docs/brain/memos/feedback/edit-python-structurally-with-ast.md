---
name: feedback-edit-python-structurally-with-ast
description: Never remove or replace a Python definition — or a config key — by text replacement; splice by ast lineno, and re-parse the file to check the shape you meant.
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

**The same failure in YAML is worse, because it still parses.** Editing `qa/qa.config.yml`, my
`old` string included the `responsive_exclude:` key line and the replacement did not — so the key
vanished and its six entries stayed indented under the `exclude:` list above, where YAML read them
as six more members of it. Six routes silently left the coverage denominator and the percentage went
*up*: the same defect the issue I was fixing was about, arriving through the config. Nothing errored,
and the diff looked like a comment rewrite.

So for structured text of any kind, the check is not "does it still load" but **"does it still have
the shape I meant"** — re-parse and assert the keys:

```python
cv = yaml.safe_load(open("qa/qa.config.yml"))["coverage"]
assert set(cv) >= {"exclude", "responsive_exclude"}
```

And where the shape is load-bearing, make it a test rather than a habit —
`spec/models/qa_config_spec.rb` now refuses any `exclude` entry naming a route the app's own
controllers serve. Related: [[verify-counts-before-stating-them]],
[[chase-an-off-by-a-constant-tally]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, edit-python-structurally-with-ast.md._
