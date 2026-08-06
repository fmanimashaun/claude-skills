---
description: Generate N brand-conformant compositions of one brief plus a dev-only switcher route — so an aesthetic decision is made by comparing real screens, not by approving a single output.
argument-hint: "<brief>  [--variants N]   [e.g. pricing page --variants 3]"
---

<!-- topology: parallel
     merge: The N compositions are NEVER reconciled into one — divergence is the deliverable, and
            a fan-out that merges its outputs here would produce the averaged, tell-ridden screen
            variant mode exists to avoid. What merges is the VERDICT. A variant that fails
            `variant_conformance.py` or that `brand-guardian` rejects is regenerated or dropped
            from the set; it is never presented with a caveat, because a caveated option is one a
            human still has to evaluate. If fewer than two variants survive, the run FAILED —
            report that and stop. Offering a choice of one is the yes/no this command replaces. -->

# /design-flow:variants — $ARGUMENTS

Generate **N genuinely different compositions of one brief** (default 3) and a switcher to
compare them live in the real app. Delegate composition to the **ui-composer** agent, one
dispatch per variant; delegate the brand verdict to **brand-guardian**.

## Why this exists, and when NOT to use it

One-shot generation is the right shape when there is a correct answer — a catalog component, a
CRUD screen, a form. Use `/design-flow:component` for those.

It is the wrong shape when the brief has **many defensible solutions**: a marketing hero, a
pricing page, a landing section, a dashboard's first screen. There the useful question is not
*"is this acceptable?"* — which tends to become yes — but *"which of these three is best, and
why?"*. Variants make the human a **chooser** rather than an approver.

`/design-flow:setup` is deliberately **not** a variant command. It scaffolds the token
architecture and the base components: exactly one of those may exist, and N of them would be N
brands. Variants vary **within** a pack, never across.

## The constraint that makes this work

**Every variant is fully brand-conformant. They differ in composition only** — layout structure,
section order, emphasis, density, motion presence. Same role tokens, same components, same
component API.

This is **not** a style menu (`minimalist` / `brutalist` / `high-end`). We declined that
deliberately and the reasoning holds: one system with per-brand knobs, not a buffet. A variant
that reaches for its own colours, its own CSS, or a bespoke component has stopped being a
variant and become a fork of the design system — the same failure `brand.md` describes for a
pack that rewrites spacing.

The constraint is **asserted, not trusted** — see Phase 3.

## Phase 0 — brief, count, pack

Parse `$ARGUMENTS`: everything before `--variants` is the brief; `--variants N` sets the count,
default **3**. Refuse `N < 2` (a set of one is an approval) and push back above 5 — *three is a
decision, ten is a chore*, and the switcher stops being comparable.

Resolve and lint the brand pack exactly as `/design-flow:setup` does — a pack missing a role
renders a stock Tailwind colour rather than failing, and it would do so in all N variants at
once:

```bash
if [ -d "brands/<pack>" ]; then PACK="brands/<pack>"
else PACK="${CLAUDE_PLUGIN_ROOT}/brands/<pack>"; fi
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/brand_pack_lint.py" "$PACK"
```

Non-zero exit: stop and report the missing roles. Do not generate against a broken pack.

## Phase 1 — one brief, N compositions

**Read the doctrine once, compose N times.** Follow `/design-flow:component`'s order of
operations in full for each variant — the catalog, `page-anatomies.md` for anything at screen
scale, and for a marketing surface the three mandatory references (`marketing-copy.md`,
`visual-assets.md`, `motion.md`). Variant mode changes *how many* outputs there are, not *what
the doctrine is*.

Dispatch `ui-composer` **once per variant, in parallel**, each with the same brief and the same
pack, plus an explicit **composition axis** to move along so the set does not collapse into
three renderings of one idea:

- **structure** — sidebar vs stacked vs multi-column shell; which region carries the primary job.
- **order** — what the reader meets first (claim, proof, price, demo).
- **density** — `section_rhythm` within the pack's knob; how much per screenful.
- **emphasis** — which single element is allowed to be the loudest.
- **motion presence** — a named pattern from `motion.md`, or none at all.

Each variant gets a **one-line rationale** written at generation time — *"denser, prioritises the
pricing table"* — not reverse-engineered afterwards. Criterion: a rationale a human can choose
**against**. "Modern and clean" is not one.

## Phase 2 — the switcher, scaffolded to be thrown away

Three artefacts, and all three are temporary. Write them where the discard step can find them.

```
app/views/design_variants/<slug>/
  variants.json      the manifest — brief, brand, one entry per variant
  _a.html.erb        the variants themselves, partials so the winner can be moved unchanged
  _b.html.erb
  _c.html.erb
app/views/design_variants/show.html.erb          the switcher
app/controllers/design_variants_controller.rb    dev-only
config/routes.rb                                 one guarded block
```

`variants.json`:

```json
{
  "slug": "pricing",
  "brief": "pricing page for the fmworkflows marketing site",
  "brand": "fidara:fmworkflows",
  "variants": [
    { "id": "a", "file": "_a.html.erb", "rationale": "denser; leads with the comparison table" },
    { "id": "b", "file": "_b.html.erb", "rationale": "airier; leads with the claim, price below" },
    { "id": "c", "file": "_c.html.erb", "rationale": "single-column; one plan recommended by default" }
  ]
}
```

**The route is development-only.** A switcher route renders every *rejected* variant, so leaving
it reachable in production ships three landing pages nobody approved. Guard it, and constrain the
slug so a path segment cannot walk out of the directory:

```ruby
# config/routes.rb — REMOVE this block when a variant is chosen.
if Rails.env.development?
  get "design_variants/:slug", to: "design_variants#show", as: :design_variant,
      constraints: { slug: /[a-z0-9-]+/ }
end
```

```ruby
# app/controllers/design_variants_controller.rb — DELETE when a variant is chosen.
class DesignVariantsController < ApplicationController
  def show
    root = Rails.root.join("app/views/design_variants", params[:slug])
    @set = JSON.parse(root.join("variants.json").read)
    @chosen = @set["variants"].find { |v| v["id"] == params[:v] } || @set["variants"].first
    @partial = "design_variants/#{params[:slug]}/" \
               "#{@chosen['file'].delete_prefix('_').delete_suffix('.html.erb')}"
  end
end
```

The toggle is a `turbo-frame` and its links — the same mechanism as the shared CRUD modal
(`crud-modal-pattern.md`), so no new Stimulus controller and no new framework surface. Swapping a
frame leaves the page, the scroll position and the viewport alone, which is the whole point: the
comparison happens **at real viewports in the actual app**, not in a description of three options.

```erb
<%# app/views/design_variants/show.html.erb — DELETE when a variant is chosen. %>
<div class="stack">
  <nav class="cluster" aria-label="Variants">
    <% @set["variants"].each do |v| %>
      <%= link_to v["id"].upcase, design_variant_path(@set["slug"], v: v["id"]),
                  class: "min-h-touch",
                  data: { turbo_frame: "variant" },
                  aria: { current: (v["id"] == @chosen["id"] ? "true" : nil) } %>
    <% end %>
  </nav>
  <p class="text-muted-foreground"><%= @chosen["rationale"] %></p>
  <%= turbo_frame_tag "variant" do %>
    <%= render @partial %>
  <% end %>
</div>
```

Style the switcher chrome with role tokens like anything else, and keep it minimal — it is a
comparison harness, not a screen. `min-h-touch` still applies; you will be tapping it on a phone.

## Phase 3 — assert conformance, do not eyeball it

Run it. **"They look consistent" is not a verdict** — the whole reason the constraint is
mechanical is that three plausible screens are exactly the input a human review waves through.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/variant_conformance.py" .
```

Exit 0 clean · 1 findings · 2 unusable. It runs the **#157 LLM-tell detector against every
variant file** and adds the invariants that detector cannot have — a variant that brings its own
CSS or custom properties, a variant naming a **pack-private primitive** instead of a role token,
two variants with an identical composition signature (a set that offers fewer real options than
it claims), a missing rationale, and an unguarded switcher route. `--list-rules` prints all ten
with what each enforces.

`brand_pack_lint.py` is **not** run per variant, and asking for that was the one thing #160 got
wrong: it validates a brand *pack*, which is one object shared by every variant. Running it N
times proves one thing N times and nothing at all about the variants. It runs once, in Phase 0.

Then hand the set to **brand-guardian** for the judgement half — lockup, endorsement, mark usage,
and whether a variant has drifted from the pack's personality knobs rather than merely composed
differently.

Findings: regenerate the offending variant or drop it. Never present a caveated option.

## Phase 4 — choose, then leave nothing behind

Present the set as a **choice**: the switcher URL, the N rationales, and the one question worth
asking — *which, and why?* Do not recommend one unless asked; a recommendation converts the
chooser back into an approver.

Once chosen:

1. Move the winning partial to its real home (`app/views/...`), unchanged.
2. Delete `app/views/design_variants/` entirely, the controller, and the routes block.
3. Prove it, rather than believing it — an un-run discard looks exactly like a completed one:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/variant_conformance.py" --verify-discard .
```

4. **The chosen variant still goes through `/design-flow:audit`.** Variants are a way of making a
   choice, not a substitute for the consistency gate — comparing three screens tells you which is
   best, never whether the best one is correct. `design-auditor` runs on the winner in its real
   home, after the scaffolding is gone.

5. **`/design-flow:critique` is the rubric for *which* is best.** This command produces N conformant
   variants and then asks a human to choose — with nothing to choose *on* beyond preference. The critic
   supplies that: it names each variant's surface class and focal point, ranks them on **brief-fit
   first, craft second**, and says which single change would most improve the winner. *"They are all
   fine"* is not a ranking.

   Note the division. Point 4 sends the **winner** to the consistency gate; this sends **all N** to the
   taste lens, and it happens *before* the choice rather than after. Conformance cannot rank — every
   variant here is conformant by construction, which is exactly why a second question is needed.

## Output

The switcher URL, one line per variant (id · rationale · the axis it moved along), the
`variant_conformance.py` verdict, and the choice question. After a choice: the winner's new path
and the discard verification.
