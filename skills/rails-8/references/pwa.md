# Installable apps (PWA)

A new Rails app generates a manifest and a service worker under `app/views/pwa/`. Their routes
ship commented out (`controllers-routing.md`). Uncommenting them serves the two files, but it does
not by itself make the app installable, and it says nothing about what the service worker may
keep. This file states the results the app must reach. How you configure it is up to you.

## 1. The app installs

Chromium browsers treat a site as installable when all of these hold
([Chrome's installability criteria](https://developer.chrome.com/docs/lighthouse/pwa/installable-manifest)):

- it is served over **HTTPS**;
- the page links the manifest;
- the manifest has `name` or `short_name`, a `start_url`, and `display` set to `standalone`,
  `fullscreen` or `minimal-ui`;
- its `icons` include a **192px** and a **512px** icon;
- `prefer_related_applications` is absent or not `true`.

**A service worker is not required to install** in Chrome 108+ on mobile or Chrome 112+ on desktop
([Chrome blog](https://developer.chrome.com/blog/update-install-criteria)). Ship one for the
offline page (§3), not to unlock installation.

`screenshots` is optional ([MDN](https://developer.mozilla.org/en-US/docs/Web/Manifest/Reference/screenshots)).
Each entry takes a `form_factor` of `narrow` (mobile) or `wide` (desktop).

## 2. Every person is offered a way to install that works in their browser

The browsers install in different ways, so a single "Install" button cannot be the only path:

| Browser | How installation is offered |
|---|---|
| Chrome, Edge, Opera, Samsung Internet | They fire `beforeinstallprompt`, so the page can show its own install control ([MDN compatibility](https://developer.mozilla.org/en-US/docs/Web/API/BeforeInstallPromptEvent#browser_compatibility)) |
| Safari on iOS | No event. Share → **Add to Home Screen** |
| Safari on macOS (Sonoma 14+) | No event. File or Share → **Add to Dock** ([Apple](https://support.apple.com/en-us/104996)) |
| Firefox for Android | No event. It installs from its own menu |
| Firefox desktop | Cannot install web apps |

The outcomes:

- An in-page install control appears **only after** the browser has offered the prompt. It is never
  rendered as a dead button in a browser that will not fire it.
- Where there is no prompt, anything the app says about installing gives that browser's steps.
- Nothing prompts a person to install when they are already using the installed app.

## 3. A service worker never caches signed-in pages

This is our rule, not a browser's (maintainer decision, #1258).

> A service worker never caches responses to signed-in pages. It precaches only static,
> content-free shell files: an offline page and icons.

A cached response is a copy of the page on whatever device opened it. For a signed-in page that
copy holds the user's data. It outlives sign-out and the removal of the account, and it stays on
a shared machine for the next person. So signed-in navigations go to the network, and when the
network fails they show the static offline page. Pages anyone can read without signing in may be
cached.

**The exception needs its own design.** An app whose users must work offline, such as field staff
filling in forms with no signal, needs data stored deliberately: encrypted, scoped to the user, and
wiped at sign-out. A response cache is not that design. Record the decision in the project's
CLAUDE.md before building it.

## Proving it

- A request spec asserts that the manifest route returns JSON with each field in §1, and that the
  icon files it names exist.
- A test of the service worker's fetch handling asserts that a signed-in navigation is never
  written to a cache. It is not enough to assert that a public one is.
