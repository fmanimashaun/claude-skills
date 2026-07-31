---
description: Audit UI against the Fidara design system — flag drift (raw/brand colors in components, brittle selectors, breakpoint misuse where an intrinsic primitive fits, missing focus ring/ARIA, non-min-h-touch targets, hand-rolled layout CSS) and propose fixes.
argument-hint: "[path or view/component to audit; default: changed files]"
---

# /design-flow:audit — $ARGUMENTS

Review `$ARGUMENTS` (or the working diff) for drift from the **fidara-design** doctrine.
Delegate to the **design-auditor** agent. Report findings; don't rewrite in place unless asked.

## First: the mechanical cross-check (run it before reading anything)

The checklist below audits a *project's* UI. This one audits the **toolchain** — it catches
doctrine that references a runtime artefact `/design-flow:setup` never generates, which is
invisible to every other check and only surfaces as a `NoMethodError` at a user's first setup
run. It reads the shipped doctrine and generator, so it is meaningful from any clone:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/setup_doctrine_crosscheck.py"
```

A non-zero exit is a **toolchain defect, not a project defect** — report it with
`/rails-flow:report` (component `design-flow`) rather than patching locally. Warnings flag
config setup generates that no doctrine reads: probably dead scaffolding, worth a look but
not a blocker.

## Checklist (cite file:line for each finding)

**Tokens/color**
- Raw brand or stock colors in component code (`bg-fm-cerulean`, `bg-blue-700`, `text-gray-*`,
  hex) → must be semantic role tokens (`bg-primary`, `text-muted-foreground`, `border-border`).
- Text color hand-picked on a colored surface instead of the `-foreground` pair.
- Hardcoded font sizes/spacing instead of the fluid `--text-step-*` / `--space-*` scale.

**Layout/responsive**
- Hand-written layout CSS or `grid-cols-1 sm:grid-cols-2`-style breakpoints where an intrinsic
  primitive (`grid-auto`, `Layout::Sidebar`/`Switcher`, `cluster`) expresses it.
- Child outer margins for spacing instead of the parent's `gap`.
- Missing `min-h-touch` on tap targets; fixed pixel widths; running text past `--measure`.

**Interaction/a11y**
- Interactive element without a visible `focus-visible` ring.
- Missing/incorrect ARIA (`aria-expanded/controls/selected`, roles), icon-only control without
  `sr-only` label, color-only state, keyboard-unreachable behavior, no `prefers-reduced-motion`.

**Consistency**
- Off-catalog variant/size names; duplicate mechanisms (two button/badge idioms); brittle
  CSS-chain/`data-testid` selectors bound to markup internals; radius not matching the system
  (btn `rounded-md`, card `rounded-lg`, badge `rounded-full`); non-Lucide icons.

**Composition/branding**
- Full-page single-focus views (auth, marketing splash, onboarding) using bare `center` (top-aligned)
  instead of the `cover > center > stack` recipe that centers **vertically**.
- Marketing/auth surfaces with **no brand mark**, or a hand-rolled text eyebrow (`<p>Fidara</p>`)
  where `Ui::Logo` belongs; mark below the 20px floor (lockup <140px); recolored/stretched/rotated
  or shadowed facets; missing clear space (1.5× prism height).

## Output

A prioritized findings list (severity: breaks-consistency > a11y > polish), each with
`file:line`, the rule it violates, and the exact token/primitive/recipe to use instead. Offer
to fix via `/design-flow:component`. Confirmed-clean areas noted too.
