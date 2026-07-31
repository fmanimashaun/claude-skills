// design-flow rendered-conformance collector — pass to page.evaluate(). MEASURES ONLY: every
// verdict, count and threshold belongs to rendered_conformance.py, so nothing here decides.
const collectConformanceSnapshot = () => {
  const SCHEMA = 'design-flow/rendered-conformance/1';
  const ROLES = ['background', 'foreground', 'card', 'card-foreground', 'popover',
    'popover-foreground', 'primary', 'primary-foreground', 'secondary', 'secondary-foreground',
    'muted', 'muted-foreground', 'accent', 'accent-foreground', 'destructive',
    'destructive-foreground', 'success', 'warning', 'info', 'border', 'input', 'ring'];
  const TYPE_STEPS = ['--text-step--2', '--text-step--1', '--text-step-0', '--text-step-1',
    '--text-step-2', '--text-step-3', '--text-step-4', '--text-step-5'];
  const RADII = ['--radius', '--radius-sm', '--radius-md', '--radius-lg', '--radius-xl',
    '--radius-2xl', '--radius-3xl'];
  const COLOUR_SENTINELS = ['rgb(1, 2, 3)', 'rgb(4, 5, 6)'];
  const LENGTH_SENTINELS = ['3px', '7px'];
  const MAX_ELEMENTS = 2500;
  const SKIP = new Set(['SCRIPT', 'STYLE', 'TEMPLATE', 'NOSCRIPT', 'BR', 'HEAD', 'META', 'LINK',
    'TITLE', 'SVG', 'PATH', 'G', 'CIRCLE', 'RECT', 'LINE', 'POLYLINE', 'POLYGON', 'USE', 'DEFS',
    'SYMBOL', 'CLIPPATH', 'MASK']);
  const FOCUS_PROPS = ['outline', 'outline-style', 'outline-width', 'outline-color',
    'outline-offset', 'box-shadow', '--tw-ring-shadow', '--tw-ring-color',
    '--tw-inset-ring-shadow', '--tw-shadow', 'background-color', 'border-color',
    'border-top-color', 'border-bottom-color', 'border-left-color', 'border-right-color',
    'color', 'border-width', 'border-style', 'text-decoration-line', 'text-decoration'];
  const FOCUS_PSEUDO = /:focus(-visible|-within)?/g;

  // ---- token basis: resolved by THIS browser, so no colour maths happens downstream ----
  const probe = document.createElement('div');
  probe.style.cssText = 'position:absolute;left:-9999px;top:0;width:1px;height:1px;';
  document.body.appendChild(probe);

  const computedOf = (prop, value) => {
    probe.style.setProperty(prop, value);
    const out = window.getComputedStyle(probe).getPropertyValue(prop).trim();
    probe.style.removeProperty(prop);
    return out;
  };

  // Two sentinels, not one: a single fallback could coincide with the token's real value, and a
  // token that is merely UNDECLARED would then be recorded as part of the basis.
  const resolve = (prop, token, sentinels) => {
    const viaVar = sentinels.map((s) => computedOf(prop, `var(${token}, ${s})`));
    const bare = sentinels.map((s) => computedOf(prop, s));
    if (viaVar[0] === bare[0] && viaVar[1] === bare[1]) return null;
    return viaVar[0];
  };

  const canMix = window.CSS && window.CSS.supports
    && window.CSS.supports('color', 'color-mix(in oklab, red 100%, transparent)');
  const colour = {};
  for (const role of ROLES) {
    const values = [];
    for (const token of [`--color-${role}`, `--${role}`]) {
      const direct = resolve('color', token, COLOUR_SENTINELS);
      if (direct === null) continue;
      values.push(direct);
      // The oklab spelling of the same role. Tailwind v4 compiles `bg-primary/100` to a
      // color-mix, which serializes in oklab — without this probe an opacity modifier of 100%
      // would trace to no role and be reported.
      if (canMix) {
        const mixed = computedOf('color', `color-mix(in oklab, var(${token}) 100%, transparent)`);
        if (mixed) values.push(mixed);
      }
    }
    if (values.length) colour[`--${role}`] = Array.from(new Set(values));
  }

  const fontSize = {};
  for (const token of TYPE_STEPS) {
    const value = resolve('font-size', token, LENGTH_SENTINELS);
    if (value) fontSize[token] = value;
  }
  const radius = {};
  for (const token of RADII) {
    const value = resolve('border-top-left-radius', token, LENGTH_SENTINELS);
    if (value) radius[token] = value;
  }
  probe.remove();

  // ---- focus rules, read from the cascade instead of by focusing anything ----
  // Focusing to measure would depend on :focus-visible heuristics that differ by browser and by
  // how focus arrived; a programmatic focus() may not match :focus-visible at all, and every
  // correctly styled control would then look unstyled.
  const focusRules = [];
  let unreadableSheets = 0;
  const collectRules = (rules) => {
    for (const rule of rules) {
      if (rule.selectorText && /:focus/.test(rule.selectorText)) {
        const decls = {};
        for (const prop of FOCUS_PROPS) {
          const value = rule.style ? rule.style.getPropertyValue(prop) : '';
          if (value) decls[prop] = value;
        }
        if (Object.keys(decls).length) {
          const selectors = rule.selectorText.split(',')
            .map((part) => part.replace(FOCUS_PSEUDO, '').trim())
            .filter(Boolean);
          focusRules.push({ selectors, decls });
        }
      }
      if (rule.cssRules) collectRules(Array.from(rule.cssRules));
    }
  };
  for (const sheet of Array.from(document.styleSheets)) {
    try {
      collectRules(Array.from(sheet.cssRules));
    } catch (err) {
      unreadableSheets += 1;   // cross-origin: .cssRules throws. Counted, never guessed at.
    }
  }
  const focusMeasurable = focusRules.length > 0 || unreadableSheets === 0;

  const focusFor = (el) => {
    if (!focusMeasurable) return null;
    const declarations = {};
    for (const rule of focusRules) {
      let hit = false;
      for (const selector of rule.selectors) {
        try {
          if (el.matches(selector)) { hit = true; break; }
        } catch (err) {
          // A selector this browser cannot parse contributes nothing.
        }
      }
      if (hit) Object.assign(declarations, rule.decls);
    }
    return { declarations };
  };

  // ---- per-element measurement ----
  const ownText = (el) => Array.from(el.childNodes)
    .some((node) => node.nodeType === 3 && node.textContent.trim() !== '');

  const refOf = (el) => {
    const parts = [];
    let node = el;
    for (let depth = 0; node && node.nodeType === 1 && depth < 3; depth += 1) {
      let part = node.tagName.toLowerCase();
      if (node.id) { parts.unshift(`${part}#${node.id}`); break; }
      const classes = (node.getAttribute('class') || '').split(/\s+/).filter(Boolean).slice(0, 2);
      if (classes.length) part += `.${classes.join('.')}`;
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(' > ');
  };

  const accessibleName = (el) => {
    const label = el.getAttribute('aria-label');
    if (label && label.trim()) return label.trim();
    for (const id of (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean)) {
      const target = document.getElementById(id);
      if (target && target.textContent.trim()) return target.textContent.trim();
    }
    const text = (el.textContent || '').trim();   // includes sr-only, which is the point
    if (text) return text;
    const title = el.getAttribute('title');
    if (title && title.trim()) return title.trim();
    const img = el.querySelector('img[alt]');
    if (img && (img.getAttribute('alt') || '').trim()) return img.getAttribute('alt').trim();
    const svgTitle = el.querySelector('svg title');
    if (svgTitle && svgTitle.textContent.trim()) return svgTitle.textContent.trim();
    const placeholder = el.getAttribute('placeholder');
    if (placeholder && placeholder.trim()) return placeholder.trim();
    if (el.labels && el.labels.length) {
      const joined = Array.from(el.labels).map((l) => l.textContent.trim()).join(' ').trim();
      if (joined) return joined;
    }
    return '';
  };

  const paintedColours = (el, style) => {
    const out = {};
    if (ownText(el)) out.color = style.color;
    const background = style.backgroundColor;
    if (background && background !== 'rgba(0, 0, 0, 0)' && background !== 'transparent') {
      out['background-color'] = background;
    }
    // A border colour is only ever painted where a border is actually drawn. Judging the rest
    // would flood: an unpainted border-color inherits currentcolor or the UA's black almost
    // everywhere in a document.
    const sides = {};
    for (const side of ['top', 'right', 'bottom', 'left']) {
      const width = parseFloat(style.getPropertyValue(`border-${side}-width`)) || 0;
      const kind = style.getPropertyValue(`border-${side}-style`);
      if (width > 0 && kind !== 'none' && kind !== 'hidden') {
        sides[side] = style.getPropertyValue(`border-${side}-color`);
      }
    }
    const distinct = Array.from(new Set(Object.values(sides)));
    if (distinct.length === 1) {
      out['border-color'] = distinct[0];
    } else {
      for (const side of Object.keys(sides)) out[`border-${side}-color`] = sides[side];
    }
    return out;
  };

  const candidates = Array.from(document.body.querySelectorAll('*'))
    .filter((el) => !SKIP.has(el.tagName)
      && !el.closest('[data-conformance-ignore]')
      && !el.closest('svg'));
  const elements = [];
  for (const el of candidates.slice(0, MAX_ELEMENTS)) {
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    const rect = el.getBoundingClientRect();
    const corners = ['border-top-left-radius', 'border-top-right-radius',
      'border-bottom-right-radius', 'border-bottom-left-radius']
      .map((prop) => style.getPropertyValue(prop));
    const parent = el.parentElement;
    const own = (el.textContent || '').trim();
    const record = {
      ref: refOf(el),
      tag: el.tagName.toLowerCase(),
      role: el.getAttribute('role') || '',
      type: el.getAttribute('type'),
      href: el.getAttribute('href'),
      tabindex: el.getAttribute('tabindex'),
      classes: el.getAttribute('class') || '',
      colours: paintedColours(el, style),
      rect: { w: Math.round(rect.width * 10) / 10, h: Math.round(rect.height * 10) / 10 },
      radius: corners.some((value) => parseFloat(value) > 0) ? corners : [],
      name: accessibleName(el),
      aria: {
        controls: el.getAttribute('aria-controls'),
        expanded: el.getAttribute('aria-expanded'),
        selected: el.getAttribute('aria-selected'),
        pressed: el.getAttribute('aria-pressed'),
      },
      ariaHidden: el.closest('[aria-hidden="true"]') !== null,
      disabled: el.disabled === true || el.getAttribute('aria-disabled') === 'true',
      // MEASUREMENTS, not the exemption itself. Deciding "is this an inline link in running
      // text?" here cost a whole rule: `display.startsWith('inline')` matches every native
      // <button> (UA display `inline-block`, measured in Chrome), so every button on the page was
      // exempted from the touch floor — and no Python fixture could see it, because the verdict
      // had already been made in JS. The judgement lives in rendered_conformance.py, where it has
      // a fixture and a declared mutation.
      display: style.display,
      textLength: own.length,
      parentTextLength: parent ? (parent.textContent || '').trim().length : 0,
      focus: focusFor(el),
    };
    if (ownText(el)) record.fontSize = style.fontSize;
    elements.push(record);
  }

  return {
    schema: SCHEMA,
    url: window.location.href,
    viewport: { width: window.innerWidth, height: window.innerHeight },
    theme: document.documentElement.classList.contains('dark') ? 'dark' : 'light',
    truncated: candidates.length > MAX_ELEMENTS,
    unreadableSheets,
    focusRuleCount: focusRules.length,
    overflow: {
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    },
    basis: { color: colour, fontSize, radius },
    elements,
  };
};
