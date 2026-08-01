// qa-flow crawl collector — MEASURES ONLY. Every verdict, threshold and marker belongs to
// crawl_report.py and interaction_report.py; nothing here decides whether anything is a finding.
//
// That split is not style. This file cannot be unit-tested without a browser, so it must not hold a
// rule: a rule here would be a rule with no fixture and no mutation guard. Everything it records is
// a fact a Python judge can then argue about — and the judges have 47 fixtures between them.
//
// Run with `node`, against an app the caller already booted. It writes two files the judges read:
//   qa/manual-tests/crawl.json          -> crawl_report.py
//   qa/manual-tests/interactions.json   -> interaction_report.py
//   qa/manual-tests/visual.json         -> visual_baseline.py   (with --visual)
//
//   node crawl_collector.js --routes / /dashboard --base http://localhost:3000 --out qa/manual-tests
//   node crawl_collector.js --visual --seeded --masks qa/manual-tests/masks.json --routes /
//
// `--masks` takes the map visual_baseline.py prints with `--masks`: route -> selectors to paint
// over. This file applies them and records what it applied; it does not decide what is dynamic.
//
// WHAT IT DOES NOT DO. It does not screenshot, judge layout, or evaluate the design system —
// design-flow's conformance collector owns that, and this one deliberately does not duplicate it.
// For theme parity, run design-flow's collector twice (light, then with the `dark` class) and pass
// both snapshots to theme_parity.py; this file does not re-implement that either.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

// PLAYWRIGHT IS RESOLVED FROM THE PROJECT, NOT FROM THIS FILE (#356).
//
// A bare `import { chromium } from 'playwright'` fails when this script runs from its installed
// location: ESM resolution walks `node_modules` upward from the SCRIPT, which lives in the plugin
// cache, and Playwright is installed in the user's project. `NODE_PATH` does not help — it has no
// effect on ESM resolution at all. The documented invocation therefore failed outright with
// ERR_MODULE_NOT_FOUND, and the only workaround was copying this file into the project.
//
// `createRequire` anchored at the working directory resolves the way the user expects: from their
// project. The failure message names both the cwd and the fix, because "cannot find package" with
// Playwright plainly installed is a bewildering thing to be told.
const projectRequire = createRequire(`${process.cwd()}/`);
let chromium;
try {
  ({ chromium } = await import(pathToFileURL(projectRequire.resolve('playwright')).href));
} catch (error) {
  console.error(
    `Cannot load Playwright from ${process.cwd()}.\n` +
    `  This script resolves it from your PROJECT, not from the plugin, so run it from the repo\n` +
    `  root where Playwright is installed:  npm i -D playwright && npx playwright install chromium\n` +
    `  Original error: ${error.message}`);
  process.exit(2);
}

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  if (i === -1) return fallback;
  const rest = process.argv.slice(i + 1);
  const stop = rest.findIndex((v) => v.startsWith('--'));
  const values = stop === -1 ? rest : rest.slice(0, stop);
  return values.length > 1 ? values : (values[0] ?? fallback);
};

const base = arg('base', `http://localhost:${process.env.PORT || 3000}`);
const outDir = arg('out', 'qa/manual-tests');
const routes = [].concat(arg('routes', '/'));
// A control we activate must not navigate away mid-sweep, or every later control reports
// "not exercised" for a reason that is our fault rather than the app's.
const MAX_CONTROLS = Number(arg('max-controls', 40));
const VISUAL = process.argv.includes('--visual');
const BASELINES = arg('baselines', 'qa/baselines');
const VIEWPORT = { width: 1280, height: 900 };
// A baseline shot at deviceScaleFactor 2 shares not one pixel with the same page shot at 1, so the
// ratio would read ~100% on a machine that merely has a different display. Playwright defaults this
// to 1, but a default is not a pin: a device descriptor sets it to 2 or 3, and inheriting a value
// that decides whether every comparison is meaningful is not something to leave implicit.
const SCALE = 1;
const THEME = arg('theme', 'light');

// WHICH SELECTORS ARE DYNAMIC IS A POLICY DECISION, AND IT IS NOT MADE HERE (#112). visual_baseline.py
// resolves the config's global + per-route ignore lists and prints the map; this file only paints
// over what it is handed and records what it painted. Same split as everywhere else: deciding is
// Python's, and a rule here would be a rule with no fixture. The judge REFUSES a run whose recorded
// masks disagree with the config, so a stale or absent map is reported, never quietly judged.
const MASKS = (() => {
  const path = arg('masks', null);
  if (!path) return {};
  try {
    return JSON.parse(readFileSync(path, 'utf8'));
  } catch (error) {
    console.error(`Cannot read --masks ${path}: ${error.message}\n` +
      '  Generate it with:  python3 visual_baseline.py --masks --routes / /dashboard \\\n' +
      '                       --config qa/qa.config.yml > qa/manual-tests/masks.json');
    process.exit(2);
  }
})();

// DETERMINISM. Without it the diff ratios are noise, and a flaky visual check is worse than none:
// it trains people to ignore the one report that needs eyes. visual_baseline.py REFUSES a run that
// does not record all five, so this object is a CLAIM and must only assert what is actually true.
//
// Four of the five this file can genuinely do, and it does them below: motion and the clock before
// the first paint, the pixel ratio at newPage, the fonts before the shot.
// `seededData` it CANNOT: seeding the app's fixtures is the caller's job, and asserting it here
// would be a lie that lets a run with live, moving data be judged pixel-for-pixel. So it comes from
// an explicit `--seeded` flag and defaults to FALSE -- the judge then refuses, which is the correct
// outcome for a caller who has not said the data is fixed.
const determinism = {
  reducedMotion: true,
  frozenClock: true,
  pinnedScale: true,
  fontsLoaded: true,
  seededData: process.argv.includes('--seeded'),
};

const pages = [];
const controls = [];

mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch();
const shots = [];

for (const route of routes) {
  const page = await browser.newPage(
    VISUAL ? { viewport: VIEWPORT, deviceScaleFactor: SCALE } : {});
  if (VISUAL) {
    // Freeze motion and the clock BEFORE the first paint, or the first frame is already wrong.
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.addInitScript(() => {
      const frozen = new Date('2026-01-01T00:00:00Z').getTime();
      Date.now = () => frozen;
      const style = document.createElement('style');
      style.textContent = '*,*::before,*::after{animation:none!important;transition:none!important;' +
                          'caret-color:transparent!important}';
      document.addEventListener('DOMContentLoaded', () => document.head.appendChild(style));
    });
    if (THEME === 'dark') {
      await page.addInitScript(() =>
        document.addEventListener('DOMContentLoaded', () =>
          document.documentElement.classList.add('dark')));
    }
  }
  const console_ = [];
  const failed = [];
  page.on('console', (m) => console_.push({ level: m.type(), text: m.text() }));
  page.on('requestfailed', (r) =>
    failed.push({ method: r.method(), url: r.url(), failure: r.failure()?.errorText || 'failed' }));

  let record;
  try {
    const response = await page.goto(`${base}${route}`, { waitUntil: 'networkidle' });
    record = {
      route,
      status: response ? response.status() : null,
      title: await page.title(),
      // The first heading, because a framework error template puts its message there while the
      // <title> may still say the app's name.
      h1: await page.evaluate(() => document.querySelector('h1')?.textContent?.trim() || ''),
      console: console_,
      failedRequests: failed,
      skipped: null,
    };
  } catch (error) {
    // A route we could not load is NOT a passing route. Recorded as skipped with the reason, which
    // crawl_report.py reports separately and never counts as clean.
    record = { route, skipped: String(error.message || error).slice(0, 200) };
  }
  pages.push(record);

  if (record.skipped) { await page.close(); continue; }

  if (VISUAL) {
    const slug = route.replace(/^\//, '').replace(/\W+/g, '-') || 'root';
    const dir = `${VIEWPORT.width}x${VIEWPORT.height}-${THEME}`;
    const baseline = `${BASELINES}/${dir}/${slug}.png`;
    const candidate = `${BASELINES}/_candidates/${dir}/${slug}.png`;
    const diff = `${BASELINES}/_diffs/${dir}/${slug}.png`;
    const baselinePresent = existsSync(baseline);
    // FONTS BEFORE PIXELS. `networkidle` says the requests finished; it does not say the font is
    // applied, and a webfont that swaps in after the shot changes every glyph on the page — a
    // whole-page diff that looks like a catastrophic regression and is nothing at all.
    // Recorded, not assumed: if the wait fails the claim is withdrawn and the judge refuses the
    // whole run. Asserting `fontsLoaded: true` unconditionally would be the same lie `seededData`
    // exists to avoid — a determinism block is only worth anything if every entry is measured.
    const fontsOk = await page.evaluate(() => document.fonts.ready.then(() => true))
      .catch(() => false);
    if (!fontsOk) determinism.fontsLoaded = false;
    const ignored = (MASKS[route] || []).map(String);
    const maskLocators = ignored.map((selector) => page.locator(selector));
    // The CANDIDATE is always written and the BASELINE is never touched. Promotion is a human's
    // act: an agent that can overwrite a baseline can launder a regression into the new truth.
    //
    // `mask` overlays each locator's bounding box with a flat #FF00FF block (Playwright's default,
    // left unset on purpose: pinning `maskColor` would impose a >=1.35 floor to change a constant
    // that is already deterministic, and the same block lands on baseline and candidate alike).
    mkdirSync(`${BASELINES}/_candidates/${dir}`, { recursive: true });
    await page.screenshot({ path: candidate, fullPage: true, mask: maskLocators });
    let diffRatio = null;
    let diffPresent = false;
    if (baselinePresent) {
      // Compared IN THE BROWSER, where a canvas already exists. Decoding PNGs in Python would mean
      // a third-party image library inside a gate, and this file measures rather than judges: it
      // emits the ratio and visual_baseline.py decides what it means. The DIFF IMAGE comes back
      // from the same pass for the same reason — the pixels are already decoded here, and a ratio
      // with no picture is a number a reviewer cannot act on.
      const measured = await page.evaluate(async ([a, b]) => {
        const load = (src) => new Promise((res, rej) => {
          const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src;
        });
        const [x, y] = await Promise.all([load(a), load(b)]);
        const w = Math.min(x.width, y.width), h = Math.min(x.height, y.height);
        const draw = (img) => {
          const c = document.createElement('canvas'); c.width = w; c.height = h;
          c.getContext('2d').drawImage(img, 0, 0);
          return c.getContext('2d').getImageData(0, 0, w, h).data;
        };
        const p1 = draw(x), p2 = draw(y);
        const out = document.createElement('canvas'); out.width = w; out.height = h;
        const ctx = out.getContext('2d');
        const image = ctx.createImageData(w, h);
        let changed = 0;
        for (let i = 0; i < p1.length; i += 4) {
          const off = Math.abs(p1[i] - p2[i]) + Math.abs(p1[i + 1] - p2[i + 1]) +
                      Math.abs(p1[i + 2] - p2[i + 2]);
          if (off > 24) {
            changed += 1;
            // Changed pixels magenta, unchanged ones a faded greyscale of the candidate, so the
            // eye lands on the change while it stays locatable on the page it came from.
            image.data[i] = 255; image.data[i + 1] = 0; image.data[i + 2] = 255;
          } else {
            const grey = 200 + (p1[i] + p1[i + 1] + p1[i + 2]) / 3 * 0.2;
            image.data[i] = grey; image.data[i + 1] = grey; image.data[i + 2] = grey;
          }
          image.data[i + 3] = 255;
        }
        ctx.putImageData(image, 0, 0);
        // Size differences count as changed pixels rather than being cropped away silently.
        const total = Math.max(x.width * x.height, y.width * y.height);
        return {
          ratio: (changed + (total - w * h)) / total,
          png: out.toDataURL('image/png').split(',')[1],
        };
      }, [pathToFileURL(candidate).href, pathToFileURL(baseline).href]).catch(() => null);
      if (measured) {
        diffRatio = measured.ratio;
        mkdirSync(`${BASELINES}/_diffs/${dir}`, { recursive: true });
        writeFileSync(diff, Buffer.from(measured.png, 'base64'));
        diffPresent = true;
      }
    }
    shots.push({
      route,
      viewport: `${VIEWPORT.width}x${VIEWPORT.height}`,
      theme: THEME,
      baseline,
      baselinePresent,
      candidate,
      // Null rather than the path when nothing was written: reporting a path to a file that does
      // not exist sends a reviewer looking for evidence that was never produced.
      diff: diffPresent ? diff : null,
      diffRatio,
      ignored,
    });
  }

  // ---- interaction sweep on this route ------------------------------------------------------
  const found = await page.evaluate((cap) => {
    const sel = 'button, a, [role="button"], [role="tab"], [role="menuitem"], summary, [onclick]';
    const refOf = (el) => {
      const parts = [];
      for (let n = el; n && n !== document.body; n = n.parentElement) {
        const tag = n.tagName.toLowerCase();
        const cls = (n.getAttribute('class') || '').trim().split(/\s+/).filter(Boolean).slice(0, 2);
        parts.unshift(cls.length ? `${tag}.${cls.join('.')}` : tag);
      }
      return parts.join(' > ');
    };
    return Array.from(document.querySelectorAll(sel)).slice(0, cap).map((el, index) => ({
      index,
      ref: refOf(el),
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || '',
      name: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 60),
      href: el.getAttribute('href'),
      disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
    }));
  }, MAX_CONTROLS);

  for (const control of found) {
    const before = await page.evaluate(() => ({
      html: document.body.innerHTML.length,
      url: location.href,
      active: document.activeElement?.outerHTML?.slice(0, 80) || '',
      aria: Array.from(document.querySelectorAll('[aria-expanded],[aria-selected],[aria-pressed]'))
        .map((e) => `${e.getAttribute('aria-expanded')}${e.getAttribute('aria-selected')}${e.getAttribute('aria-pressed')}`)
        .join('|'),
      dialogs: document.querySelectorAll('dialog[open],[role="dialog"]').length,
    }));
    // #357: did NATIVE CONSTRAINT VALIDATION block this? A submit inside a form with an unfilled
    // `required` field fires no request — correctly — and without this fact the judge sees only
    // "clicked, nothing happened" and calls a working button dead. Measured here, judged there.
    const formInvalidBefore = await page.evaluate((i) => {
      const sel = 'button, a, [role="button"], [role="tab"], [role="menuitem"], summary, [onclick]';
      const el = document.querySelectorAll(sel)[i];
      const form = el && el.closest('form');
      if (!form || typeof form.checkValidity !== 'function') return null;
      return !form.checkValidity();
    }, control.index).catch(() => null);
    const after_console = [];
    const onMsg = (m) => after_console.push({ level: m.type(), text: m.text() });
    let requested = false;
    const onReq = () => { requested = true; };
    page.on('console', onMsg);
    page.on('request', onReq);

    let exercised = true;
    let reason = null;
    try {
      const handle = (await page.$$(
        'button, a, [role="button"], [role="tab"], [role="menuitem"], summary, [onclick]'
      ))[control.index];
      if (!handle) throw new Error('element no longer in the DOM');
      // `force` is deliberate: an obscured control is still a control, and refusing to click it
      // would report "not exercised" for a layout reason rather than a behavioural one.
      await handle.click({ timeout: 2000, force: true, noWaitAfter: true });
      await page.waitForTimeout(150);
    } catch (error) {
      exercised = false;
      reason = String(error.message || error).slice(0, 120);
    }

    const after = exercised ? await page.evaluate(() => ({
      html: document.body.innerHTML.length,
      url: location.href,
      active: document.activeElement?.outerHTML?.slice(0, 80) || '',
      aria: Array.from(document.querySelectorAll('[aria-expanded],[aria-selected],[aria-pressed]'))
        .map((e) => `${e.getAttribute('aria-expanded')}${e.getAttribute('aria-selected')}${e.getAttribute('aria-pressed')}`)
        .join('|'),
      dialogs: document.querySelectorAll('dialog[open],[role="dialog"]').length,
    })).catch(() => null) : null;

    page.off('console', onMsg);
    page.off('request', onReq);

    controls.push({
      ref: `${route} ${control.ref}`,
      tag: control.tag,
      role: control.role,
      name: control.name,
      href: control.href,
      disabled: control.disabled,
      exercised,
      reason,
      constraintBlocked: formInvalidBefore === true,
      effects: after ? {
        domChanged: after.html !== before.html,
        navigated: after.url !== before.url,
        requested,
        focusMoved: after.active !== before.active,
        ariaChanged: after.aria !== before.aria,
        dialogOpened: after.dialogs > before.dialogs,
      } : {},
      consoleAfter: after_console,
    });

    if (after && after.url !== before.url) {
      // Navigated away: the rest of this route's controls are gone. Go back rather than reporting
      // them all as missing, which would be our artefact and not the app's defect.
      await page.goto(`${base}${route}`, { waitUntil: 'networkidle' }).catch(() => {});
    }
  }
  await page.close();
}

await browser.close();

writeFileSync(`${outDir}/crawl.json`,
  JSON.stringify({ schema: 'qa-flow/route-crawl/1', pages }, null, 2));
writeFileSync(`${outDir}/interactions.json`,
  JSON.stringify({ schema: 'qa-flow/interaction-sweep/1', controls }, null, 2));

if (VISUAL) {
  writeFileSync(`${outDir}/visual.json`,
    JSON.stringify({ schema: 'qa-flow/visual-run/1', determinism, shots }, null, 2));
}

console.log(`wrote ${outDir}/crawl.json (${pages.length} route(s)) and ` +
            `${outDir}/interactions.json (${controls.length} control(s))`);
