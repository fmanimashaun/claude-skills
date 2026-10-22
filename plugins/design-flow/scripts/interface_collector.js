// design-flow interface-audit collector — pass to page.evaluate(). MEASURES ONLY: every verdict,
// count and rule belongs to interface_audit.py, so nothing here decides what is a defect.
const collectInterfaceSnapshot = () => {
  const SCHEMA = 'design-flow/interface-snapshot/1';
  const visible = (el) => {
    if (el.closest('[hidden], [aria-hidden="true"]')) return false;
    const cs = window.getComputedStyle(el);
    return cs.display !== 'none' && cs.visibility !== 'hidden';
  };
  const FOCUSABLE = 'a[href], button, input, select, textarea, summary, [tabindex]:not([tabindex="-1"])';
  const here = new URL(window.location.href);
  const samePage = (href) => {
    try {
      const u = new URL(href, here);
      return u.origin === here.origin && u.pathname === here.pathname && !u.hash;
    } catch (_) { return false; }
  };

  // The `main` landmarks a user can reach: <main> and role="main", not hidden.
  const mains = Array.from(document.querySelectorAll('main, [role="main"]')).filter(visible);

  // The first focusable element on the page, and whether it is a skip link to a real target.
  const first = Array.from(document.querySelectorAll(FOCUSABLE)).find((el) => !el.closest('[inert]'));
  let skip = { present: false, first_focusable: first ? first.tagName.toLowerCase() : null, target_exists: false, href: null };
  if (first && first.tagName === 'A' && (first.getAttribute('href') || '').startsWith('#') && first.getAttribute('href').length > 1) {
    const id = first.getAttribute('href').slice(1);
    skip = { present: true, first_focusable: 'a', href: first.getAttribute('href'), target_exists: !!document.getElementById(id) };
  }

  // A live region a toast can render into: aria-live or role=status/alert, outside <main>.
  const liveRegions = Array.from(document.querySelectorAll('[aria-live], [role="status"], [role="alert"]'))
    .filter((el) => !el.closest('main, [role="main"]'));

  // The primary navigation is the first nav landmark in document order; report its links and
  // which one says it is the current page.
  const nav = document.querySelector('nav, [role="navigation"]');
  const navLinks = nav ? Array.from(nav.querySelectorAll('a[href]')).filter(visible).map((a) => ({
    text: (a.textContent || '').trim().slice(0, 80),
    href: a.getAttribute('href'),
    to_this_page: samePage(a.getAttribute('href')),
    current: a.getAttribute('aria-current') === 'page',
  })) : [];

  // STRUCTURE FACTS for the template rows (interface_templates.py decides). Each is found by the
  // most conventional hook (a class, a data attribute, an ARIA label); a page with none reports
  // the fact as absent, and the judge reads that as a finding only for the template that owns it.
  const main = mains[0] || document.body;
  const before = (a, b) => !!(a && b && (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING));
  const h1 = Array.from(document.querySelectorAll('h1')).find(visible) || null;
  const backEl = Array.from(document.querySelectorAll('a[href], button')).filter(visible)
    .find((el) => el.matches('[class*="back-link"], [data-back-link]') || /^\s*back\s*$/i.test(el.textContent || '')) || null;
  const fwdEl = Array.from(main.querySelectorAll('button[type="submit"], input[type="submit"], button:not([type])')).filter(visible).pop() || null;
  const listEl = main.querySelector('[data-results], .results, #results, ol.results, ul.results');
  const countEl = main.querySelector('[data-results-count], .results-count, #results-count');
  const noneEl = main.querySelector('[data-no-results], .no-results, #no-results');
  const sortEl = main.querySelector('select[name*="sort"], [data-sort], .sort-control');
  const countText = countEl ? (countEl.textContent || '').trim().slice(0, 120) : null;
  const countMatch = countText && countText.match(/\d[\d,]*/);
  const terms = [];
  ['q', 'query', 'search', 'term', 'keywords'].forEach((k) => {
    const v = here.searchParams.get(k);
    if (v && v.trim()) terms.push(...v.trim().split(/\s+/));
  });
  // Check-answers and task-list facts (#2327). The same rule: record what is on the page by the conventional hooks,
  // never decide. A fact that is not found is reported empty, and the judge reads that as unverified, not as a pass.
  const hiddenSel = '.govuk-visually-hidden, .visually-hidden, .sr-only, [data-visually-hidden]';
  const squash = (t) => (t || '').replace(/\s+/g, ' ').trim();
  const textOf = (el, withHidden) => {
    const c = el.cloneNode(true);
    if (!withHidden) c.querySelectorAll(hiddenSel).forEach((n) => n.remove());
    return squash(c.textContent);
  };
  const accName = (a) => squash(a.getAttribute('aria-label')) || textOf(a, true);
  const summary = main.querySelector('.govuk-summary-list, [data-check-answers], dl.summary-list, dl');
  const changeLinks = (scope) => Array.from(scope.querySelectorAll('a[href]'))
    .filter((a) => a.closest('[class*="actions"]') || /^change\b/i.test(textOf(a, false)))
    .map((a) => ({ visible: textOf(a, false), name: accName(a) }));
  let rows = [];
  if (summary) {
    const wrapped = Array.from(summary.children).filter((c) => c.tagName === 'DIV' || c.matches('.govuk-summary-list__row'));
    rows = wrapped.length
      ? wrapped.map((r) => ({ key: textOf(r.querySelector('dt') || r.firstElementChild || r, false).slice(0, 80), change_links: changeLinks(r) }))
      : Array.from(summary.querySelectorAll(':scope > dt')).map((dt) => {
        const holder = document.createElement('div');
        for (let n = dt.nextElementSibling; n && n.tagName !== 'DT'; n = n.nextElementSibling) holder.appendChild(n.cloneNode(true));
        return { key: textOf(dt, false).slice(0, 80), change_links: changeLinks(holder) };
      });
  }
  const textBlocks = summary && fwdEl ? Array.from(main.querySelectorAll('p, h2, h3, h4, [role="note"]'))
    .filter((el) => !summary.contains(el) && before(summary, el) && before(el, fwdEl) && squash(el.textContent)).length : 0;
  const check_answers = { rows, submit_present: !!fwdEl, text_before_submit: textBlocks > 0 };
  const taskHeadings = Array.from(main.querySelectorAll('h2, h3'));
  const taskLists = Array.from(main.querySelectorAll('.govuk-task-list, ul.task-list, [data-task-list]')).map((list) => {
    const preceding = taskHeadings.filter((h) => before(h, list));
    return {
      heading_index: preceding.length - 1,
      items: Array.from(list.querySelectorAll(':scope > li, :scope > .govuk-task-list__item')).map((item) => {
        const st = item.querySelector('.govuk-task-list__status, [data-status], .task-list__status, .govuk-tag, strong.tag');
        const nm = item.querySelector('.govuk-task-list__name-and-hint, [data-task-name], a');
        return { name: nm ? textOf(nm, false).slice(0, 80) : '', status: st ? textOf(st, false) : null, has_link: !!item.querySelector('a[href]') };
      }),
    };
  });
  const forwardEl = fwdEl || main.querySelector('a.govuk-button, [data-continue]');
  const task_list = { lists: taskLists, forward_present: !!forwardEl };

  const structure = {
    back_link: { present: !!backEl, before_h1: before(backEl, h1), text: backEl ? (backEl.textContent || '').trim().slice(0, 40) : null },
    forward_button: { present: !!fwdEl, label: fwdEl ? ((fwdEl.value || fwdEl.textContent || '').trim().slice(0, 40)) : null },
    results: {
      list_items: listEl ? listEl.querySelectorAll(':scope > li, :scope > [data-result]').length : 0,
      count_text: countText,
      count_value: countMatch ? parseInt(countMatch[0].replace(/,/g, ''), 10) : null,
      count_before_list: countEl && listEl ? before(countEl, listEl) : null,
      pagination: !!main.querySelector('nav[aria-label*="agination" i], .pagination, [data-pagination]'),
      no_results_text: noneEl ? (noneEl.textContent || '').trim().slice(0, 160) : null,
      no_results_hints: !!(noneEl && (noneEl.querySelector('li, a[href]') || /\b(try|check|hint|suggest)/i.test(noneEl.textContent || ''))),
      sort_control: { present: !!sortEl, before_list: sortEl && listEl ? before(sortEl, listEl) : null },
    },
    query: { terms },
    check_answers,
    task_list,
  };

  return {
    schema: SCHEMA,
    url: window.location.pathname + window.location.search,
    title: document.title,
    status: null, // the caller sets the HTTP status from the response
    mains: { visible: mains.length },
    skip_link: skip,
    live_regions: liveRegions.length,
    primary_nav: { present: !!nav, links: navLinks },
    h1_count: Array.from(document.querySelectorAll('h1')).filter(visible).length,
    structure,
  };
};
