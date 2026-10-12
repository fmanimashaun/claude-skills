# Installable apps (PWA)

A new Rails app generates a manifest and a service worker under `app/views/pwa/`. Their routes
ship commented out (`controllers-routing.md`). Uncommenting them serves the two files, but it does
not by itself make the app installable, and it says nothing about what the service worker may
keep. This file states the results the app must reach. How you configure it is up to you.

## 1. The app installs

Chromium browsers treat a site as installable when all of these hold
([Chrome's install criteria](https://web.dev/articles/install-criteria), last updated 2024-09-19; the Lighthouse page that used to list them says "PWA testing in Lighthouse is deprecated"):

- it is served over **HTTPS**;
- the page links the manifest;
- the manifest has `name` or `short_name`, a `start_url`, and `display` set to `standalone`,
  `fullscreen`, `minimal-ui` or `window-controls-overlay`;
- its `icons` include a **192px** and a **512px** icon;
- `prefer_related_applications` is absent or not `true`;
- the app is not already installed, and the person has clicked or tapped the page at least once and
  has spent at least 30 seconds viewing it (the same page's engagement heuristic, as dated above).

**A fresh Rails 8.1 app does not meet the icon rule.** The generated `manifest.json.erb` lists
`/icon.png` twice at `512x512` (the second with `"purpose": "maskable"`) and no 192px entry
(`rails/rails` `8-1-stable` and v8.1.4, `railties/lib/rails/generators/rails/app/templates/app/views/pwa/manifest.json.erb.tt`).
Add a 192px icon and list it before treating the app as installable.

**A service worker is not required to install** in Chrome 108+ on mobile or Chrome 112+ on desktop
([Chrome blog](https://developer.chrome.com/blog/update-install-criteria)). Ship one for the
offline page (§3), not to unlock installation.

`screenshots` is optional ([MDN](https://developer.mozilla.org/en-US/docs/Web/Manifest/Reference/screenshots)).
Each entry takes a `form_factor` of `narrow` (mobile) or `wide` (desktop).

## 2. Every person is offered a way to install that works in their browser

The browsers install in different ways, so a single "Install" button cannot be the only path:

| Browser | How installation is offered |
|---|---|
| Chrome, Edge, Opera, Samsung Internet | They fire `beforeinstallprompt`, so the page can show its own install control ([MDN compatibility](https://developer.mozilla.org/en-US/docs/Web/API/BeforeInstallPromptEvent#browser_compatibility)). MDN marks the event experimental and non-standard (`standard_track: false` in browser-compat-data), and Firefox and Safari do not implement it, so it is never the only path |
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

## 4. An offline page, where the scaffold has one

**Unreleased: this is on Rails `main` only.** `rails/rails` `main` (`gem_version` 8.2.0 at the time of
writing) added an offline fallback to the PWA scaffold ([#57184](https://github.com/rails/rails/pull/57184)):
`app/views/pwa/offline.html.erb`, a commented `get "offline" => "rails/pwa#offline", as: :pwa_offline`
route, `Rails::PwaController#offline`, and **commented** service-worker examples that precache
`/offline` and answer a failed navigation with it. It is absent from `8-1-stable` and v8.1.4: a Rails
8.1 app has none of it and builds the offline page itself. Even on `main` nothing is active until the
developer uncomments it.

The outcome for any version is the one in section 3: a signed-in navigation that fails shows a static,
content-free offline page, and nothing signed-in is cached.

## 5. Web Push

Use a Web Push gem rather than hand-rolling the protocol: `web-push` is Pushpad's maintained fork of
`webpush` (MIT, Ruby 3.0 or later; 3.1.0 released 2025-12-18). `webpush` has had no release since
2020-11 and no commit since 2022-11; that is dates, not a notice in its README.

- **VAPID** ([RFC 8292](https://www.rfc-editor.org/rfc/rfc8292)) identifies the application server with a
  P-256 key pair. The RFC makes it voluntary; Chrome and Edge require the public key as
  `applicationServerKey` at `pushManager.subscribe`, with `userVisibleOnly: true`
  ([MDN](https://developer.mozilla.org/en-US/docs/Web/API/PushManager/subscribe)). Keep the private
  key in credentials.
- **The 8.1 scaffold ships the two handlers commented out** in `service-worker.js`: `push` reads
  `{ title, options }` from `event.data.json()` and shows the notification, and `notificationclick`
  focuses a window whose path equals `event.notification.data.path`, else opens it. A payload therefore
  carries `options.data.path`.
- **iPhone and iPad:** Web Push works from iOS and iPadOS 16.4, **only for an app added to the Home Screen**,
  and the permission request must come from a direct user action such as tapping a subscribe button
  ([WebKit](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)). Safari on macOS has
  had it since 16.1, without installing. This pass did not check whether Safari needs
  `applicationServerKey`.

Our rule, not a browser's: ask for notification permission only from a user action, on every platform, not
only where iOS forces it.

## 6. The Play Store

A PWA reaches Google Play as a **Trusted Web Activity** (TWA): an Android app that opens the site in
Chrome without browser UI ([Chrome](https://developer.chrome.com/docs/android/trusted-web-activity),
Chrome 72 and later on Android). Bubblewrap, a Chrome Labs CLI, generates and builds the Android project
([repo](https://github.com/GoogleChromeLabs/bubblewrap)); PWABuilder wraps it.

- The app and the site are tied by **Digital Asset Links**: the site serves
  `https://<domain>/.well-known/assetlinks.json`, and "statement lists in any other location, or with any
  other name, are not valid" ([Google](https://developers.google.com/digital-asset-links/v1/getting-started)).
  An entry names `"relation": ["delegate_permission/common.handle_all_urls"]` and a `target` of
  `"namespace": "android_app"` with the `package_name` and `sha256_cert_fingerprints`. It uses the key
  the APK is signed with, and Play may re-sign, so include the Play signing fingerprint too.
- Without a valid link the app falls back to a Custom Tab with browser UI.
- An Android app must be signed to upload to Play. Current Play target-API and account policy was not
  checked in this pass: read Play's own pages, not this file.
- Serving the file from Rails is ordinary static-file serving (`public/.well-known/`), subject to
  `config.public_file_server.enabled` or the proxy in front. No official Rails source says more.

## Proving it

- A request spec asserts that the manifest route returns JSON with each field in §1, and that the
  icon files it names exist.
- A test of the service worker's fetch handling asserts that a signed-in navigation is never
  written to a cache. It is not enough to assert that a public one is.
- A request spec asserts that `/.well-known/assetlinks.json`, when the app ships a TWA, is served as JSON with
  each `relation` and `target` field present.
