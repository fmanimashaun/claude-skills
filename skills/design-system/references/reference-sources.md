# Where to look, and how to capture it without lying to yourself

Companion to [`reference-research.md`](reference-research.md), which is the *method*. This is the
operational half: where the material is, and the mechanics that make a capture trustworthy.

**Every failure below is silent.** A lazy-loaded page returns a screenshot of empty placeholders; a
login wall returns a screenshot of a login form; a challenge page returns a screenshot of a
challenge. None of them errors, all of them produce a file with the right name, and nothing
downstream can tell them from research. That is the thing to design against.

## 1. Ungated sources — no session needed

| source | what it is good for |
|---|---|
| [landingfolio.com](https://landingfolio.com) | HTML skeletons — hero zones, feature grids, pricing tables |
| [land-book.com](https://land-book.com) | layout and grid positioning, modern type pairings |
| [lapa.ninja](https://lapa.ninja) | full-page vertical layouts, captured whole |
| [onepagelove.com](https://onepagelove.com) | content density and scroll hierarchy on minimal pages |
| [godly.website](https://godly.website) | interaction rules, custom animation, micro-copy |

Start here. A record built entirely from these is not a lesser one — see §2.

### 1b. Follow the gallery through to the live site

Galleries show a **thumbnail** — a cropped, re-encoded, often months-old render of someone else's
capture. Study that and you are studying a photograph of the thing.

Most listings link out; Landingfolio's **"Visit site"** is the clearest example. Take it, and capture
the **live page** yourself. That gets you what a thumbnail cannot:

- **real viewport widths**, so you can see the 1440 → 390 behaviour, which is frequently the whole
  trick you were admiring;
- **interaction** — hover, scroll-triggered motion, sticky behaviour, the loading sequence;
- **current state**, since the gallery entry may be a redesign old;
- **the real type and spacing**, not a downscaled JPEG of them.

Use the gallery as an **index**, not as the material. Its editorial judgement is the value — someone
already filtered thousands of pages down to these — but the artefact you record should be the live
site, and `source` in the record should be the live URL rather than the gallery listing, because
that is the thing a later reader needs to re-check.

If the live site is gone or has changed beyond recognition, say so in the record. A thumbnail is
still better than nothing; it is just worth knowing which one you looked at.

## 2. Gated sources — a human must sign in first

[mobbin.com](https://mobbin.com) (UI patterns, and end-to-end flows) and
[pageflows.com](https://pageflows.com) (UI behaviour over time — state changes, loaders, tooltips)
need a signed-in session, and their galleries paginate only once authenticated.

Follow `reference-research.md` §3b: **detect the wall, stop, and ask the human to sign in once** into
the persistent browser profile. Never request the credentials, never type them, never store them.
If they decline, that is a complete answer — the ungated list above covers most of what research
needs, and flow-over-time material is a nice-to-have rather than a prerequisite.

**Gating changes without notice.** Treat this split as what was true when it was written, not as a
standing fact: check for the wall each run rather than trusting the table.

## 3. The three mechanics that produce silent lies

### Lazy loading — the page is not what you first see

Most galleries render cards only as they scroll into view. Capture immediately and you get a grid of
empty placeholders, filed as a reference.

Scroll in increments with a pause between, then return to the top before capturing:

```js
await page.evaluate(async () => {
  for (let y = 0; y < document.body.scrollHeight; y += 400) {
    window.scrollTo(0, y);
    await new Promise(r => setTimeout(r, 220));
  }
  window.scrollTo(0, 0);
});
await page.waitForTimeout(1500);
```

400px steps rather than one jump: a single `scrollTo(0, bottom)` fires no intermediate intersection
observers, so the middle of the page never loads.

### Automation challenges — and the line not to cross

Some sites challenge headless browsers by default, even for a signed-in human. Presenting as a real
desktop browser avoids that false positive:

```js
const browser = await chromium.launch({
  args: ['--disable-blink-features=AutomationControlled'],
});
const page = await browser.newPage({ userAgent: '<a current desktop UA>' });
```

**Where this stops.** That is for a false challenge on a public page you are entitled to read. If a
site *deliberately* blocks you — a persistent challenge, a rate limit, a robots directive, terms
that forbid automated access — **stop and say so.** Do not rotate identities, solve challenges, or
escalate techniques. The material is not worth it and there is plenty that is freely readable; a
research record short one gallery is fine, and a blocked source is a fact to report, not an obstacle
to route around.

### Dynamic class names — selectors that rot on the next deploy

Galleries built with CSS-in-JS emit classes like `sc-bdVaJa iXWZLN`, regenerated on every build. A
hardcoded selector works today and silently matches nothing next month — which returns an empty
capture rather than an error.

Select by role, semantics or structure instead: `page.getByRole('link')`, `page.locator('article')`,
heading hierarchy. Those survive a rebuild because they describe what the element *is*.

## 4. Finding sources yourself

The list above will age. Three ways to extend it without being handed URLs:

**Search for directories, not designs.** `inurl:gallery landing page design inspiration SaaS`,
`site:github.com "awesome-design"`, `curated list of web design inspiration sites`. Take the first
~20, drop the blog posts, keep the domains that are actually galleries.

**Follow the footer.** Good pages advertise where they were featured — *"Featured on Lapa Ninja"*,
*"Site of the Day"*, *"Made in Framer"*, *"Built with Webflow"*. Each phrase leads to a showcase
platform holding hundreds more, and it comes pre-filtered by someone's editorial judgement.

**Try the feed first.** Append `/feed/`, `/rss`, `/feed.xml`. A feed gives clean XML metadata with no
images, no scripts, no lazy loading and no challenge — so when one exists, it is both the cheapest
and the most reliable way to enumerate what a gallery holds. Capture screenshots only for the few
entries you actually intend to study.

## 5. What still has to be judged

None of this decides anything. A directory of sources and a reliable capture are inputs; the work is
still §4 of `reference-research.md` — naming the **mechanism** rather than the look, and rejecting
most of what you gathered. A hundred captures and no rejections is a mood board, and a mood board is
what you make when you have not decided anything yet.
