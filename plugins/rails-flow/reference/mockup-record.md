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
| `States:` | `;`-separated entries; every state of the vocabulary exactly once, each `<state>` (designed) or `<state>: n/a: <reason>`. Example: `loaded; loading: n/a: static page; error; empty-filtered: n/a: no filter; partial: n/a: one source; permission-denied: n/a: public; success: n/a: read only; first-run: n/a: seeded`. At least one state is designed; `loaded` need not be (a system page marks most states n/a) |
| `Shell:` | `docs/product/mockups/shell.md`, always that path |
| `Template:` | the page template: `list`, `detail`, `create-edit`, `multi-step`, `dashboard`, `settings`, `search-results`, `sign-in`, `system: <not-found\|no-permission\|error\|maintenance>`, or `multi-step`, which may carry a sub-kind for the pages that are not a question: `multi-step: <check-answers\|confirmation\|task-list>` (no sub-kind is a question page). A sub-kind is not a template of its own: there are nine templates |
| `Statuses:` | **optional, and only on a `multi-step: task-list` record**: the words the page shows for its task statuses, `;`-separated `<role>=<word>` entries, roles `not-started`, `in-progress`, `cannot-start` and `completed`; `cannot-start` and `completed` are required once the line exists, and one word names one role. Example: `Statuses: not-started=To do; cannot-start=Blocked; completed=Done`. No line means the GOV.UK wording (`Not started`, `In progress`, `Cannot start yet`, `Completed`) (#2327) |
| `Screen:` | this screen's name; unique across records |
| `Nav:` | `level N under <parent>`, N from 1 to 3. Level 1 sits under the literal `shell`; level N of 2 or 3 sits under the `Screen:` of an existing record at level N-1 |
| `Story:` | **once the screen is built**: a repo path to the story file (`*.stories.*`) or the user-visible file that implements this mock-up. Required by the gate on the real diff (`--base`), not at plan time (`--paths`) |

The allowed values (templates, system and multi-step sub-kinds, states, the nav depth cap) are one list, `plugins/rails-flow/reference/mockup-vocabulary.json`, which the gate reads and the frontend architecture framework (#2220) cites. A missing or unreadable list refuses every record. `n/a: <reason>` demands a non-empty reason, not a true one: the reviewer reads the truth. A record whose `Template:`, `States:`, `Screen:` or `Nav:` is missing or outside the vocabulary is refused when it is **added or changed**; existing records are never re-judged.

## The shell record

`docs/product/mockups/shell.md` is a record with three more lines:

| Line | Holds |
|---|---|
| `Kind:` | `shell` |
| `Shell-sources:` | two or more approved HTML mock-ups of **different** screens, comma-separated |
| `Shell-keep:` | optional: the tokens chosen with `--keep`, written by `--adopt-shell` |
| `Shell-signature:` | the landmark elements (`header`, `nav`, `main`, `footer`, `aside`) and element ids (`#main`) those screens have in common, narrowed to `Shell-keep:` when there is one |

The signature is derived, never typed. What two screens share is the shell; what differs is content.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_mockup_gate.py" --adopt-shell \
  docs/product/mockups/<screen-a>.html docs/product/mockups/<screen-b>.html \
  --approval <link to the approval comment> --approved-by @<owner> --issue "#<n>" \
  --widths "1280, 390" --states "default, collapsed"
```

The command writes the record only if it then passes. It refuses a signature with no `main` or fewer than three tokens, because a signature that every page satisfies cannot fail. If two screens share an id by chance (a form field, a card), narrow it with `--keep "header, nav, main, #main, #toasts"`: `--keep` chooses among the shared tokens and cannot add one, and the choice is written to the record as `Shell-keep:`.

## What the gate does with it

- A record without `Shell: docs/product/mockups/shell.md` is held.
- A project with no shell record is held on its first user-visible change: **the first change is the shell**. Mock up the layout, the navigation and the foundation screens, following the design system; get them approved; run `--adopt-shell`. Every later mock-up is drawn inside it.
- A mock-up that is a repo HTML file must hold every signature token as an **element**. The word "nav" in text, an element in a comment and markup in a script string are not elements. The contents of a `<template>` are, so a board that keeps its screens there passes. An element that is never drawn is not the shell either: anything inside `<noscript>`, an element with `hidden`, `aria-hidden="true"` or an inline `display:none`, and everything inside one of those.
- An image or a PDF in the repo, or a link, cannot be read, so only its `Shell:` line is checked. The gate says so ("not an HTML file", or "a link, not a repo file"), and the reviewer confirms the layout against the shell.
- The gate recomputes the signature from the sources (and `Shell-keep:`) on every run. A token deleted from the line by hand, a token added by hand, and a source that changed all fail it. Narrowing is done by `--keep`, which records itself; deleting a token from both lines by hand is an edit of the approved record, visible in review, and the signature still has to keep `main` and three tokens.
- Once the shell is committed on the base, a change that touches only `shell.md` covers none of its user-visible files: each screen needs a record of its own with `Shell:`. A change that adds the first shell is the whole change.
- A change to `shell.md` is judged on its own, even when it touches no user-visible file.

A flow diagram is attached to the record of the screen it belongs to (linked from that record's mock-up or kept beside it). It is not recorded on its own, and there is no `Shell: n/a`: a record that names no shell is held.

`mockup-gate: off` on its own line in GUARDRAILS.md turns the whole gate off, shell included.

## Linking the design to the build (`Story:`)

`Story:` joins the two stores: `docs/product/mockups/` holds the proposed design, and the story file (or the view) holds the built one. Reviewers compare the two.

- **On the real diff** (`check_mockup_gate.py --base <base>`, Phase 6 and the PR reviewer) a record without a valid `Story:` is held. A route cannot be checked here: the stack's route list comes with the stack descriptor (#2219).
- **What counts as a user-visible file comes from the stack** (#2219): each detected stack declares its `ui_scope` (`paths`, `not_paths`, `seen_anyway`) in its `stacks.json` descriptor, proven by its own `ui-scope-cases.json`. A JavaScript front-end project with nextjs-stack installed can name a component or page path as its `Story:`, and its UI changes are classified by the same list. When no installed stack declares `ui_scope`, the gate falls back to a built-in Rails-shaped list and prints "no installed stack declares ui_scope: used the built-in Rails-shaped list; install rails-stack or nextjs-stack" on every run; the fallback goes when rails-stack is in the install path (#2274). A story file (`*.stories.*`) is accepted either way.
- **Certification** (qa-flow's `release_evidence.py stamp`) refuses the stamp when a record with a `Template:` line and a **closed** `Issue:` names no `Story:`, and when an issue cannot be read (an unjudged audit is not a pass). It reads the records as committed at the stamp's revision. A legacy record (no `Template:`) is never failed for this.
- **By hand or in CI**: `check_mockup_gate.py --audit` prints the same finding list online, plus the legacy records that name no `Story:`. It exits 1 on a finding and 2 when an issue could not be read.
