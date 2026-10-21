# The mock-up record and the app's shell (#1376, #2211)

A change a user can see is built after an approved mock-up. A mock-up is drawn **inside the app's own shell**: its layout and navigation, not a free-standing screen. `scripts/check_mockup_gate.py` checks both. This file is the format it reads; read the script's docstring for why.

## A record

One file per mock-up, `docs/product/mockups/<slug>.md`, with one `Key: value` line for each key below.

| Line | Holds |
|---|---|
| `Mock-up:` | an https link, or a repo file that exists (`.html`, `.png`, `.pdf`, `.svg`, ...) |
| `Issue:` | `#n` or the issue URL |
| `Approved-by:` | who approved |
| `Approval:` | the link to the comment where they said so (`…/issues/N#issuecomment-M`) |
| `Widths:` | at least a phone width (480 or less) and a desktop width (1024 or more) |
| `States:` | the screen's designed states. Free text to the gate today; the allowed values are defined by the frontend architecture framework (#2220), not here, so there is one list. The QA case catalogue and that framework's state check read it |
| `Shell:` | `docs/product/mockups/shell.md`, always that path |

## The shell record

`docs/product/mockups/shell.md` is a record with three more lines:

| Line | Holds |
|---|---|
| `Kind:` | `shell` |
| `Shell-sources:` | two or more approved HTML mock-ups of **different** screens, comma-separated |
| `Shell-signature:` | the landmark elements (`header`, `nav`, `main`, `footer`, `aside`) and element ids (`#main`) those screens have in common |

The signature is derived, never typed. What two screens share is the shell; what differs is content.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_mockup_gate.py" --adopt-shell \
  docs/product/mockups/<screen-a>.html docs/product/mockups/<screen-b>.html \
  --approval <link to the approval comment> --approved-by @<owner> --issue "#<n>" \
  --widths "1280, 390" --states "default, collapsed"
```

The command writes the record only if it then passes. It refuses a signature with no `main` or fewer than three tokens, because a signature that every page satisfies cannot fail. If two screens share an id by chance (a form field, a card), narrow it with `--keep "header, nav, main, #main, #toasts"`: `--keep` chooses among the shared tokens and cannot add one.

## What the gate does with it

- A record without `Shell: docs/product/mockups/shell.md` is held.
- A project with no shell record is held on its first user-visible change: **the first change is the shell**. Mock up the layout, the navigation and the foundation screens, following the design system; get them approved; run `--adopt-shell`. Every later mock-up is drawn inside it.
- A mock-up that is a repo HTML file must hold every signature token as an **element**. The word "nav" in text, an element in a comment and markup in a script string are not elements. The contents of a `<template>` are, so a board that keeps its screens there passes.
- An image, a PDF or a link cannot be read, so only its `Shell:` line is checked. The gate says so, and the reviewer confirms the layout against the shell.
- The gate recomputes what the sources share on every run. A token the sources no longer share, or a token typed by hand, fails it.
- A change to `shell.md` is judged on its own, even when it touches no user-visible file.

A flow diagram is attached to the record of the screen it belongs to (linked from that record's mock-up or kept beside it). It is not recorded on its own, and there is no `Shell: n/a`: a record that names no shell is held.

`mockup-gate: off` on its own line in GUARDRAILS.md turns the whole gate off, shell included.
