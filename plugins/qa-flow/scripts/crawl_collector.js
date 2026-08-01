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
//
//   node crawl_collector.js --routes / /dashboard --base http://localhost:3000 --out qa/manual-tests
//
// WHAT IT DOES NOT DO. It does not screenshot, judge layout, or evaluate the design system —
// design-flow's conformance collector owns that, and this one deliberately does not duplicate it.
// For theme parity, run design-flow's collector twice (light, then with the `dark` class) and pass
// both snapshots to theme_parity.py; this file does not re-implement that either.

import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';

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

const pages = [];
const controls = [];

mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch();

for (const route of routes) {
  const page = await browser.newPage();
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

console.log(`wrote ${outDir}/crawl.json (${pages.length} route(s)) and ` +
            `${outDir}/interactions.json (${controls.length} control(s))`);
