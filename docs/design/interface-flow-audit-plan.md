# Interface and flow audit — plan (#2221). PLAN ONLY: nothing is built

Measured 2026-10-21 on `origin/dev` 9ca5c443. The framework it audits against is `plugins/rails-stack/skills/design-system/references/architecture.md` (60 rules, each with a basis: `check:`, `claim:` or `decision:`).

## The one idea that carries both halves

A finding is a row a script can refuse. Every finding names a rule id (A#) from the framework's rules table, and the script **derives** the authority from that row's basis: `claim:` makes it a **standard** finding, `decision:` makes it a **house rule**, `check:` names the existing check. The agent cannot label a house rule as a standard, because the label is computed, not written. That is the owner's "everything must be enforced" applied to the audit itself (kind 2: a required declaration verified by a script).

## What exists today (so nothing is duplicated)

| piece | does | does not |
|---|---|---|
| `design-flow` `design-auditor` + `/design-flow:audit` | source conformance: tokens, primitives, raw colour; `rendered_conformance.py` for the rendered cascade | audit against an architecture; nothing about shell, template, states, navigation |
| `design-flow` `design-critic` + `/design-flow:critique` | advisory look-and-feel, never blocks | enforce anything |
| `qa-flow` `journey-walker` + `/qa-flow:walkthrough` | walks personas' journeys; records pages, hand-offs, notifications (`pages.csv`, `handoffs.csv`, `notifications.csv`, validated by `validate_evidence.py`) | measure steps, waits, dead ends, back-tracks, re-entry, late permission walls |
| `qa-flow` judges `layout_fit.py`, `text_resize.py`, `theme_parity.py`, `link_audit.py`, `crawl_report.py` | collector JSON in, findings out (the pattern to copy) | know the framework's rule ids |
| `rails-flow` `check_mockup_gate.py` | refuses a UI change without an approved mock-up record | any `Template:`, `States:`, `Nav:` value (#2226) |

## Who owns which half

**Interface audit: design-flow.** New agent `interface-auditor` and command `/design-flow:interface-audit`; it does not extend `design-auditor` (that one reads Rails source; this one reads rendered pages and is stack-neutral). It drives a browser with a new collector, hands the JSON to a new judge, and writes the report plus **proposed mock-up records** (the #2211 record format, `Approved by:` left empty, so the gate still refuses it until the owner approves). Mock-up first: an improvement is proposed as a record, not as code.

**Flow audit: qa-flow.** `journey-walker` is extended to emit one more artefact, `flow.json` (one row per action: journey, step, url, action kind, time to settled, spinner seen, form values submitted), and a new judge `flow_report.py` reads it. `/qa-flow:walkthrough` gains the bottleneck section in its report. The interface audit reads the flow report if it exists (it is the user's evidence file, not a plugin file), so the ranked list can merge both.

**Where the rule list comes from.** A plugin reaches only its own files, and the rules table lives in rails-stack's design-system skill. So the rule registry design-flow's judge reads is a **generated** `plugins/design-flow/reference/architecture-rules.json`, built from the page by a builder in `scripts/rebuild_generated.py` (the repo's one list of generated surfaces), with `--check` failing on drift. One source; no vendored copy to forget.

## What is mechanical, what is a declaration, what is a verdict

| audit row | kind | rests on |
|---|---|---|
| landmarks, skip link, one `h1`, toast region (A1, A2) | 1 mechanical | new collector: DOM facts; judge refuses a finding with no evidence |
| `aria-current` on the current primary-nav item (A4) | 1 | collector |
| hidden-in-viewport, text resize, theme parity, links (A23–A26) | 1, **reuse** | read the existing qa-flow judge `--json` output and map each finding to its rule id; no new measurement. **Correction after building slice 1:** contrast, target size and reflow (A19, A20, A22) come from axe in the `a11y-auditor` agent, not from a qa-flow judge with JSON output, so they are not reused in slice 1 and join when an axe-result judge exists |
| focus visible (A21) | 1 | **#2228** (axe has no focus rule); until it ships the row is absent, not advisory |
| no card in a card | 1 | **#2227** |
| each declared state renders distinct (A59, state rows) | 1 | **#2229** and the `States:` line of #2226 |
| Core Web Vitals within budget (A27) | 1 | **#2230** |
| multi-step and search-results structure (A29–A58): back link first, "Continue", Change links, count above results, no-results text, pagination at >10 | 1 | collector, **only for a screen whose record declares that `Template:`** |
| a screen declares `Template:`, `States:`, `Nav:` | 2 declaration | **#2226**; for an existing screen the audit writes the proposed record; an undeclared screen is itself a finding |
| density matches the surface, content hierarchy, interaction feedback, "this is the right template" | 3 verdict | **#2225**: the auditor records pass/fail with evidence per rule; until #2225 exists these rows are listed as "not audited: no verdict channel", never as advice |
| a finding's rule id exists and its authority matches the basis | 2 | the new `audit_findings.py` refuses a finding that names an unknown rule, has no evidence, or carries a hand-written authority |
| ranking | 1 | deterministic: standard failures by WCAG level and reach (screens affected), then house-rule failures, then verdict-backed; the script computes it, the agent does not |

**Flow measurements (all mechanical, from `flow.json`):** steps to complete a journey; context switches (a change of top-level navigation section or a new modal or tab); waits (time from action to settled, and spinner seen); dead ends (a page that is not a declared terminal and offers no forward action); back-tracks (a return to an earlier URL within the journey); forms re-entered (the same field names submitted again after the form came back); permission walls hit late (a 403 or an access-denied page at step k when the journey's first step already needed the permission). Each is a row in the judge with a negative fixture and a mutant.

**Thresholds are declarations, not defaults.** A journey document declares its own `Budget:` (steps, longest wait); `flow_report.py` refuses a journey with no budget (kind 2) and fails one over it. The one default I would add is the wait limit, and only with a verified source: NN/g's response-time limits (0.1 s, 1 s, 10 s) go to `doctrine-verifier` and the raw-HTML phrase check before they are written (C24 already cites the 0.1 s limit; the 1 s and 10 s limits are not verified yet). Otherwise a project sets it.

## Dependencies

| needs | for | state |
|---|---|---|
| #2226 | `Template:`, `States:`, `Nav:` records; proposed records are valid output | open, 32 builds |
| #2225 | verdict rows (density, hierarchy, feedback, template choice) | open |
| #2227, #2228, #2229, #2230 | their rule rows | open; each row joins when its check lands, never as advice |
| #2211 | the record format and gate the proposals feed | open; the gate script is on dev |
| #2185 | stack specifics through the UI adapters | open, e6 |
| #2223, #2222 | the stack architectures' own rules (Hotwire, React) | open; the registry picks up their rows when they exist |

## Honest limits

- The collector needs a browser (the user's Playwright), so it cannot be a `checks.json` gate; the judges and the findings validator are deterministic scripts with fixtures and run anywhere, as `rendered_conformance.py` already does.
- Nav depth (A5) is a declaration (`Nav:`), not measured: a rendered nav does not reveal its levels reliably. The audit checks the declaration against click distance only where the crawl has it.
- State in the URL (A8) needs a per-list control to drive; it joins when #2229's forced-state work gives it a way to do so.
- "Which template should this screen be" is a judgement. The audit proposes one from structure (a table with filters reads as list; a form as create-edit) and records it as a **verdict** (#2225), not as a measurement.

## Proposed slicing (one issue, one PR)

#2221 is too big for one reviewable PR. I propose splitting it into three issues, each a PR:

1. **Findings contract + interface audit, mechanical rows** (design-flow): the generated registry and its builder, `audit_findings.py` (refuses unknown rule, no evidence, hand-written authority), the collector and judge for A1, A2, A4, the reuse mapping of existing qa-flow evidence (A19, A20, A22–A26), the ranking, the agent and command, and the proposed-record writer.
2. **Flow measurement** (qa-flow): `flow.json` from `journey-walker`, `flow_report.py` with the seven measurements, the `Budget:` declaration and its refusal, the report section.
3. **Verdict rows and template rows**: after #2225 and #2226 land (the verdict-backed rows, the multi-step and search-results structure rows).

Rows for #2227–#2230 are added by their own PRs, as the framework's table was.

## Decisions I need from the coordinator

1. Approve the three-way slicing (and file the two new issues, or tell me to).
2. Names: `interface-auditor` and `/design-flow:interface-audit`.
3. The generated-registry mechanism (a BUILDERS entry), over a vendored copy.
4. Verify NN/g's 1 s and 10 s limits through `doctrine-verifier` before any default wait is written.
