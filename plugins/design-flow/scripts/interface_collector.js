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
  };
};
