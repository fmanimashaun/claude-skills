# Marketing copy — what each section *says*, not just how it is laid out

The kits, the tokens and the page anatomies supply **layout and visual system**. None of them
supplies **information architecture or words**. So an agent can compose a structurally perfect
landing page and still ship something that reads as unfinished, because a correct layout full of
placeholder text is not a page — it is a wireframe with a stylesheet.

This file is the missing half: for each section, **the job its copy has to do**, the shape that
does it, and the way it usually fails.

**Provenance, stated up front, because the rest of this system cites sources and this cannot.**
There is no upstream here. No spec, framework or published pattern library governs what a hero
says; the ARIA APG has nothing to say about a value proposition. Everything below is **our design
decision**, recorded on [#131](https://github.com/fmanimashaun/claude-skills/issues/131), and where
a rule is a judgement call it says so. Nothing is copied from
[infinite-headcount](https://github.com/MikeFishbeinAtherial/infinite-headcount), the repo that
prompted the idea — it carries **no licence** (per #131), so it informed the *question*, never the
text.

---

## 1. The rule that outranks everything below

> **The human owns positioning. The agent drafts against a brief; it never invents one.**

Who this is for, what it replaces, why it wins, what it costs — those are business decisions with
consequences outside the page. An agent that picks them is not saving the founder time, it is
making commitments on their behalf in a medium the founder will be held to.

So the agent's input is a **brief**, and the operating rule when there isn't one is to *ask*, not to
guess. What a brief has to carry is small:

| The brief supplies | Example |
|---|---|
| **One named reader** | "operations lead at a 50–200 person field-service company", not "businesses" |
| **The outcome** they get | "close the month without chasing paper job sheets" |
| **What it replaces** | spreadsheets + WhatsApp, or a named incumbent |
| **Proof you actually hold** | a real number, a named customer, a certification — whatever exists |
| **One action** | the single thing the page asks for |

### An invented fact is worse than a visible blank

This is the sharpest point in the file and the one most likely to be got wrong, because a
well-drafted fabrication *looks* more finished than a gap.

- `{{customer_count}}` and "Feature one" are **defects the auditor catches**. They are loud, and
  loud is safe.
- "Trusted by 4,000 teams", a plausible-looking logo wall, or "reduces admin by 40%" invented to
  fill a proof slot are **false statements that ship**. Nothing catches them, because they are
  well-formed.

**Never synthesise a metric, a customer name, a quote, a logo, a certification or a review.** Where
the brief has no proof for a slot that wants one, the correct output is the slot left explicitly
empty and named in the hand-off — or the section dropped. A page with three honest sections beats
one with six where two are fiction.

---

## 2. Copy contracts, per section

**One contract per shipped archetype.** [#90](https://github.com/fmanimashaun/claude-skills/issues/90)
landed its **16 marketing section archetypes** as `composition` rows in
[coverage.md](coverage.md) — not as a separate file, which is why they are easy to miss. This table
carries **one row per archetype, using coverage.md's exact names**, so the correspondence is
re-checkable rather than asserted:

```bash
grep "a section of a marketing page" skills/fidara-design/references/coverage.md \
  | awk -F'|' '{print $2}' | sed 's/^ *//;s/ *$//'
```

Every name that command prints must appear below. **An archetype added to `coverage.md` without a
contract row here is a gap worth filing**, not a licence to improvise.

| Archetype | The job the copy does | Shape | Fails when |
|---|---|---|---|
| **Marketing header** | Get the reader to the one page that answers their question | ≤5 items, each named for a **destination**; one CTA | Nav mirrors our org chart ("Platform", "Solutions", "Resources") so no item names anywhere |
| **Hero section** | Name the **outcome the reader gets**, not the category we belong to | One claim + one clarifying line + one primary action (a quiet secondary is allowed — `page-anatomies.md`). Length caps in §3 | It describes what the software *is* — "an AI-powered operations platform" — instead of what changes for the reader |
| **Logo cloud** | Borrow credibility we have not yet earned in prose | A 3–6 word framing line + **real** names or marks, nothing else | It says "Trusted by industry leaders" with no names: a credibility claim whose own evidence is missing |
| **Feature section** | One benefit, with its mechanism **and** its evidence | benefit headline → how it works → proof | It lists capabilities instead of consequences, or the "proof" is another adjective |
| **Bento grid section** | Show breadth without becoming a spec sheet | One cell carries the claim; the rest are one-line supports, each verb-led | Every cell is weighted equally, so the grid has no reading order and the eye just bounces |
| **Stats section** | Make the scale legible at a glance | 3–4 figures, each with its **unit and its period** | A number with no denominator — "99.9%" of what, "10×" versus what |
| **Testimonial section** | Let a named person say what we cannot say about ourselves | One quote naming a specific outcome + full name, role, company | The quote is an adjective ("Great product!") — praise, not evidence |
| **Pricing section / table** | Let the reader self-select in one pass | Tier named by **who it is for**, plus the one line that disqualifies the tier above | Tiers differ only by numbers, so nobody can tell which one is theirs |
| **FAQ section** | Answer the objection that is actually blocking signup | Real objections in the reader's words; answer first, caveat second | It answers questions nobody asked ("What is <product>?") — an FAQ used as a second feature list |
| **Content / prose section** | Carry the one idea that needs more room than a card | One `h2`, ≤3 paragraphs at the measure, one link out | It becomes the page's junk drawer — everything that fit nowhere else |
| **Team section** | Make the company a set of people who can be held to this | Name, role, and one **specific** credential | Titles are aspirational ("Chief Visionary"), or the credential is a hobby |
| **Blog / article list section** | Show the thinking is ongoing | Real titles + **visible dates** | The dates are hidden — which is the tell that the last post is two years old |
| **Contact section** | Remove the doubt that a human answers | The channel + a response time we actually meet | It promises "within 24 hours" that nobody measures |
| **Newsletter section** | Say what arrives, and how often | What it contains + cadence + how to leave | "Subscribe to our newsletter" — no content promise, no frequency, so the only answer is no |
| **CTA section** | Restate the outcome and remove the last risk | One action + one risk-reducer ("no card", "cancel anytime", "10-minute setup") | It repeats the hero verbatim, so the page ends exactly where it began |
| **Footer** | Carry the legal facts and the links people leave to find | Real entity name, the required notices, a short link set | It becomes a second navigation as dense as the header's |

**Page compositions.** The three page-level anatomies (Landing, Pricing, About in
`page-anatomies.md`) sequence these sections; their copy rules live there. Two additions that belong
to a *page* rather than to any one archetype:

- **An About page opens by saying what we *do*, not who we are.** `page-anatomies.md` already
  prescribes "what we do, in one line — not 'About us'"; the copy half is keeping the founding year
  and the values list off the first screen.
- **Landing's "How it works" block** exists to remove the fear that adoption is a project. Exactly
  three ordered steps (`page-anatomies.md` makes it an `<ol>`, because the order is the meaning),
  each one verb + one object, **written from the reader's side**. It fails when the steps describe
  our internals — "we ingest, normalise and index" is our architecture, not their Tuesday.

**Out of scope, named rather than left silent:** the **commerce** archetypes (storefront, category,
product, cart, checkout, order detail, order history) are transactional surfaces whose copy is
governed by product data, legal disclosure and payment-flow clarity rather than by positioning. They
are a genuine gap in this file and want their own doctrine; do not stretch these contracts over them.

### The same contract off the marketing page

Three product surfaces fail in exactly these ways, so they are governed here rather than being left
to each screen:

| Surface | The job the copy does | Fails when |
|---|---|---|
| **Empty state** | Say what belongs here and give the one action that puts it there | It says "No data" — a *status* where an *instruction* belongs |
| **Error page** (404/500) | Say where they are and give one way out | It apologises at length, or blames the visitor (`page-anatomies.md` already forbids the blame; this is the copy half) |
| **Auth** | Name the action | It greets — "Welcome back!" — on a page whose only task is a form. `page-anatomies.md` already prescribes "Sign in", the action, not the greeting |

---

## 3. Rules that generalise

**1. Specific beats clever.** A concrete number or a named outcome outperforms wordplay, and it
survives translation, skimming and being quoted back by a sales rep. Puns are the first thing to cut
when a claim has to fit the measure.

**2. Write to one reader.** The named reader from the brief, in their words. Copy addressed to
"businesses" is addressed to nobody, and the give-away is that it would read identically on a
competitor's site.

**3. Every claim carries its mechanism or its proof, adjacently.** "Faster month-end" is noise;
"month-end closes in a day because job sheets arrive already coded" is a claim with a mechanism
attached. If neither a mechanism nor evidence is available, the claim is not ready to be on the
page.

**4. Say what it is, early.** A hero that needs a scroll before the reader can name the category has
failed, however elegant it is. Category clarity is not the same as describing the product (rule 1 of
the hero contract) — *what changes for you* first, *what kind of thing this is* immediately after.

**5. One primary action, repeated.** This one is **already doctrine** —
`page-anatomies.md` → Landing requires the same CTA in the hero, mid-page and the closing band. It
is restated here because it is as much a copy rule as a layout rule: the three instances must use
**the same verb**. "Start free" in the hero and "Get in touch" in the closing band are two different
asks wearing one design.

**6. No placeholder ships.** Lorem, "Feature one", an unfilled `{}` or a `TODO` in a rendered
surface is a **defect**, not a note-to-self — see §5.

**7. Never invent a fact.** §1, restated because it is the one failure that survives review.

### Length: two caps, and both are derived rather than asserted

The hero is the only place where a length rule earns its keep, and the numbers come from values the
system already ships rather than from taste:

- `page-anatomies.md` sets the landing `h1` to **`max-w-[45ch]`** and the sub-head to
  **`max-w-[60ch]`**.
- A hero headline should not run past **two lines** — a three-line `h1` at `text-step-5` stops
  scanning and starts reading.
- English averages ~5 characters per word plus a space, so 45ch ≈ 7–8 words per line.

**→ Hero headline: about 12 words. Sub-head: about 30 words** (two lines at 60ch). These are *ours*,
they are ceilings rather than targets, and the derivation is written out so that changing the
measure changes the cap rather than leaving a stale number behind.

Everywhere else, the shape column in §2 is the constraint. **We deliberately do not publish a
word-count per section** — see §6.

---

## 4. Voice comes from the brand pack

Voice is **per-brand**, exactly like colour, and it already has a home:
[brand.md](brand.md) → *Voice / meta*. For `fidara` that is: precise, grounded, no hype — the
tagline "Operations, engineered." is the register. A client pack carries its own note and the same
contracts produce different prose.

**Voice is pack *documentation*, not a `brand.json` field — and that is deliberate.** It would be
natural to add `"voice": "..."` to the manifest. Don't:

- `brand.md` states the pack surface is **colours, logo, and the chart-palette proof** — *"that is
  the entire surface"*. A prose field is not a value the system can consume; it is a note for
  whoever writes the copy.
- It would also **fail our own lint**: `brand_pack_lint.py` warns on any manifest key outside
  `slug` / `name` / `chart_palette_validated` / `variants` + the four documented overrides, with the
  message *"a pack is colours + logo"*. Adding a field to doctrine while the lint rejects it is the
  claims-vs-enforcement defect this repo keeps catching, so the decision is to leave the manifest
  alone.

Two things stay true regardless of pack: **product chrome carries no marketing voice** (taglines and
endorsements are marketing-surface only — `brand.md` again), and voice never overrides §1. A brand
whose voice note is "bold and disruptive" still may not invent a statistic.

---

## 5. Placeholder text is a finding — the mechanical checks

These are the checks that need **no judgement**, which is what makes them enforceable. They are
specified here and implemented by `design-auditor`:

| Check | Fires when | Why it is mechanical |
|---|---|---|
| **placeholder-text** | `lorem`/`ipsum`, `Feature one`/`Feature 1`, `Your headline here`, `TODO`, `FIXME`, `Card title`, or an unsubstituted `{{…}}` / `{…}` / `%s` in rendered copy | String match on the rendered surface |
| **hero-too-long** | Landing `h1` exceeds ~12 words, or the sub-head exceeds ~30 | Word count against §3 |
| **claim-without-proof** | A feature section has a benefit headline and no adjacent number, named source or mechanism sentence | Structural: the section has no `<cite>`, no digit and no named entity |
| **duplicate-hero-cta** | The closing-band copy is byte-identical to the hero's | String equality |
| **numeric-only-pricing-tiers** | Tier names are all of the form `Basic`/`Pro`/`Enterprise` **and** the only differences between tiers are numeric | Diff the tier feature lists |
| **stat-without-unit** | A stats-band figure has no unit and no period | Regex: a bare number with no adjacent unit token |
| **greeting-in-auth** | An auth `h1` matches a greeting ("Welcome", "Hello", "Hi there") rather than the action | String match |

**Scope note, so this file does not over-claim.** These checks are a **specification**. Wiring them
into `design-auditor` and making `/design-flow:component` consult this file are changes to the
**design-flow plugin**, which is a separate component from this skill and is not changed by the PR
that adds this file. Until that lands, this doctrine is advisory to an agent reading the skill
rather than enforced by the auditor — stated plainly because a doctrine file claiming enforcement it
does not have is precisely the defect class `code-review` calls `gate-that-cannot-fail`.

---

## 6. What we deliberately did not write

- **A tone-of-voice matrix or brand archetypes** (the "Sage / Outlaw / Creator" family). They are
  unfalsifiable: no output can be shown to violate one, so they generate discussion rather than
  decisions. The per-section *failure mode* column does the work a matrix pretends to.
- **Per-section word counts** beyond the two derived hero caps. A word count is a proxy for the
  thing we actually want, which is the shape in §2; enforcing the proxy produces copy padded or
  clipped to hit a number.
- **Fill-in-the-blank copy templates.** A template is a placeholder with better grammar — it would
  ship "Powerful <noun> for modern <industry>" everywhere and pass every check in §5. The contracts
  constrain the *job*; the words come from the brief.
- **SEO keyword doctrine.** A different discipline with a different owner, and it pulls directly
  against rule 1 — keyword-fitted copy is the most reliable way to make a hero generic.
