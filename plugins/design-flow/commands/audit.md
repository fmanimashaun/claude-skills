---
description: Audit UI against the Fidara design system — flag drift (raw/brand colors in components, brittle selectors, breakpoint misuse where an intrinsic primitive fits, missing focus ring/ARIA, non-min-h-touch targets, hand-rolled layout CSS) and propose fixes.
argument-hint: "[path or view/component to audit; default: changed files]"
---

# /design-flow:audit — $ARGUMENTS

Review `$ARGUMENTS` (or the working diff) for drift from the **fidara-design** doctrine.
Delegate to the **design-auditor** agent. Report findings; don't rewrite in place unless asked.

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

## Output

A prioritized findings list (severity: breaks-consistency > a11y > polish), each with
`file:line`, the rule it violates, and the exact token/primitive/recipe to use instead. Offer
to fix via `/design-flow:component`. Confirmed-clean areas noted too.
