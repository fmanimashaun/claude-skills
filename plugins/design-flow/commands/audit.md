---
description: Audit UI against the Fidara design system — flag drift (raw/brand colors in components, brittle selectors, breakpoint misuse where an intrinsic primitive fits, missing focus ring/ARIA, non-min-h-touch targets, hand-rolled layout CSS) and propose fixes. Optional browser mode measures conformance on the RENDERED page (literal colours after the cascade, numbered-step bindings, `dark:` count, focus rings, tap targets, radius language) instead of only reading source.
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

Read the exit code, because two of them mean opposite things:

- **Exit 1 — a toolchain defect, not a project defect.** Doctrine reads config the generator
  never produces. Report it with `/rails-flow:report` (component `design-flow`) rather than
  patching locally.
- **Exit 2 — the check could not run** (an input missing, unreadable, or not valid UTF-8). That
  is *your clone*, not the toolchain: fix the input and re-run. Filing it as a doctrine defect
  sends a maintainer hunting something that does not exist.

Treating any non-zero exit as a defect to report conflates the two. Warnings flag config setup
generates that no doctrine reads: probably dead scaffolding, worth a look but not a blocker.

## Second: the LLM-tell detector, over the project's own views

The cross-check above audits the *toolchain*. This one audits **what was generated into this
project** — the static half of the conformance question, needing no browser and no booted app:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/llm_tell_detector.py" app/views app/components
```

Seven rules, each citing the doctrine line it enforces (`--list-rules` prints them). **Two of them
find outright bugs rather than style**: `bg-gradient-to-*` was removed in Tailwind v4 and
`duration-fast` never existed, so both produce **no CSS at all** — the markup looks right, renders
wrong, and nothing raises. The other five are literal values where a role or scale step belongs,
which is what "AI beige" and "Inter for everything" look like in markup.

This also runs automatically on every edit, as a PostToolUse hook — so the audit run should
normally be quiet. A pile of findings here means the hook is not installed, which is worth knowing
on its own.

**Exit 1 is a project defect** — fix it in the view. That is the opposite of the cross-check above,
where exit 1 means a *toolchain* defect, so do not carry the habit across. Exit 2 is still "could
not run".

Disagree with a rule on a specific line? Disable it **with a reason**:

```erb
<!-- design-flow-disable stock-palette-literal: third-party embed dictates the palette -->
```

A bare disable with no reason is itself a finding, deliberately: the first justified exception is
what teaches everyone else to switch the checker off wholesale.

## Browser mode — measure conformance on the rendered page (optional, #107)

The checklist below reads **source**, so it cannot see what the cascade resolves to: a colour
injected by a third-party partial, a role token that never resolved, a focus rule that no longer
matches the element it was written for. Browser mode measures the **rendered** page instead, and
the numbers it returns are decisive rather than suggestive.

**Needs a running app and Playwright. When either is absent, skip to the checklist and say so in
the report** — a source audit is the documented fallback, not a failure.

### 1. Boot or reuse the app through qa-flow's launch config

Never invent a second boot path: `qa/qa.config.yml` `app:` (`start`, `port`, `health`) is the one
place an app's launch is described, and `/qa-flow:smoke` already reads it. Probe before launching
— two dev servers against one project contend over the same build cache:

```bash
PORT="$(python3 -c 'import re,sys;m=re.search(r"^\s+port:\s*(\d+)",open("qa/qa.config.yml").read(),re.M);print(m.group(1) if m else 3000)' 2>/dev/null || echo 3000)"
CODE=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "http://localhost:${PORT}/up" 2>/dev/null)
case "$CODE" in
  ''|000) echo "nothing answered on ${PORT}: boot it with qa/qa.config.yml app.start, then re-run" ;;
  *) echo "reusing the server on ${PORT} (/up answered ${CODE}) — not launching a second" ;;
esac
```

Probe for **an answer**, not a healthy one. `curl -f` exits non-zero on 4xx/5xx, so an app that is
up but whose `/up` returns 500 is indistinguishable from an empty port — and the branch above would
then print *"nothing on ${PORT}"*, which is false, and send you to boot a server already running.
`%{http_code}` is `000` only when no HTTP response arrived.

No `app:` block? Infer the Rails default (`bin/dev`, port 3000, `/up`) and say so.

### 2. Collect one snapshot per route × viewport × theme

The collector this plugin ships is the **only** sanctioned way to produce a snapshot — it resolves
the app's own tokens through the same browser that rendered the page, which is what makes the
comparison downstream a set membership rather than colour arithmetic:

```js
import { chromium } from 'playwright';
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';

const collector = readFileSync(`${process.env.CLAUDE_PLUGIN_ROOT}/scripts/conformance_collector.js`, 'utf8');
const routes = ['/', '/dashboard'];                  // the routes under audit
const viewports = [{ width: 390, height: 844 }, { width: 1280, height: 900 }];

mkdirSync('tmp/conformance', { recursive: true });
const browser = await chromium.launch();
for (const route of routes) {
  for (const viewport of viewports) {
    const page = await browser.newPage({ viewport });
    await page.goto(`http://localhost:${process.env.PORT || 3000}${route}`);
    await page.waitForLoadState('networkidle');      // the token layer must have applied
    const snapshot = await page.evaluate(`(() => { ${collector}\n return collectConformanceSnapshot(); })()`);
    const slug = `${route.replace(/\W+/g, '-')}-${viewport.width}`;
    writeFileSync(`tmp/conformance/${slug}.json`, JSON.stringify(snapshot));
    await page.close();
  }
}
await browser.close();
```

**A 390px snapshot is mandatory.** `tap-target-small` only runs at a mobile viewport and is
reported as SKIPPED above 640px, so a desktop-only run reads as clean while saying nothing about
touch targets. (`horizontal-overflow` runs at every viewport — sideways scroll is a defect at any
width — but mobile is where it shows up.) For dark mode, add the app's theme class before collecting
(`page.evaluate(() => document.documentElement.classList.add('dark'))`) and keep it a separate
snapshot: the role layer is what is under test, and mixing themes in one file hides which one drifted.

### 3. Judge the snapshots

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rendered_conformance.py" tmp/conformance/*.json
```

`--schema` prints the snapshot contract; `--max-dark N` / `--max-breakpoint N` move the two trend
thresholds. Read the exit code the same way as the cross-check above:

- **Exit 1 — the project drifts.** Zero-tolerance rules (`literal-colour`, `numbered-step-binding`,
  `focus-ring-missing`, `tap-target-small`, `icon-only-unnamed`, `aria-controls-no-expanded`,
  `horizontal-overflow`, `off-scale-type`, `radius-off-scale`) plus the two count-based trends
  (`dark-variant-sprawl`, `breakpoint-driven-layout`) over threshold. Report with `file:line` where
  you can trace the selector back to a component.
- **Exit 2 — the snapshot could not be judged** (no elements, no role tokens resolved, wrong
  schema). That is the *collection*, not the app: the usual cause is collecting before the
  stylesheet applied. Fix and re-run; filing it as drift sends someone hunting nothing.

**Read `skip:` lines as a third state.** A skipped rule did not run, and is not a pass — if
`off-scale-type` skipped because no `--text-step-*` resolved, the type scale is not installed,
which is itself the finding.

Report the FACT lines (`dark:` occurrences, breakpoint occurrences, the radius-language
distribution, the shadow-only focus count) even when nothing fails: those numbers are the trend
this mode exists to produce, and a regression in them is a diff rather than an opinion.

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

**Leftover variant scaffolding**
- `app/views/design_variants/`, `app/controllers/design_variants_controller.rb`, or a
  `design_variants` route still present. A variant set is a **decision in progress**: once one is
  chosen the rest are dead screens, and an un-run discard step looks exactly like a completed one.
  Verify rather than eyeball it — `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/variant_conformance.py"
  --verify-discard .` — and if the set is still live, the audit is premature: choose first, then
  audit the winner in its real home.

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
