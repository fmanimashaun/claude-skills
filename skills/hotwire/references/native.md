# Hotwire Native (iOS 1.2.x / Android 1.2.x) — Web-First Mobile Apps

Hotwire Native wraps your web app in a real native shell: a native navigation
stack driving a web view (WKWebView / Android WebView) that renders HTML from
your server. Screens ship once (HTML/CSS), native transitions come free, and
you upgrade *individual* controls or screens to native only where it pays.
It supersedes the old Turbo Native + Strada pair; Strada's ideas live on as
**bridge components**.

## Contents
1. Mental model and project shape
2. iOS setup
3. Android setup
4. Navigation: the routing table and server-driven stack control
5. Path configuration (JSON)
6. Bridge components — web side
7. Bridge components — native side (Swift / Kotlin)
8. Native screens
9. Web-side detection and native-aware views
10. Rules of thumb

---

## 1. Mental model and project shape

- **One web app, two thin native apps.** The native projects contain almost
  no product code: a navigator pointed at your root URL, a path-configuration
  JSON, registered bridge components, and (rarely) native screens.
- Navigation is native: each visited URL becomes a screen pushed onto a real
  `UINavigationController` / Android fragment backstack, so back-swipe,
  toolbars, and modals feel right automatically.
- Everything web still applies: Turbo Drive powers in-app visits; Frames,
  Streams, and Stimulus behave exactly as on desktop. Fix web first — a slow
  web page is a slow native screen.

## 2. iOS setup

Add the SPM package `https://github.com/hotwired/hotwire-native-ios`. Minimal
app — a `Navigator` owns the whole UI:

```swift
// SceneDelegate.swift
import HotwireNative
import UIKit

let rootURL = URL(string: "https://myapp.example")!

class SceneDelegate: UIResponder, UIWindowSceneDelegate {
  var window: UIWindow?
  private let navigator = Navigator()

  func scene(_ scene: UIScene, willConnectTo session: UISceneSession,
             options connectionOptions: UIScene.ConnectionOptions) {
    window?.rootViewController = navigator.rootViewController
    navigator.route(rootURL)
  }
}
```

App-level configuration (before the first route — e.g. in
`AppDelegate.didFinishLaunching`):

```swift
Hotwire.loadPathConfiguration(from: [
  .file(Bundle.main.url(forResource: "path-configuration", withExtension: "json")!),
  .server(rootURL.appending(path: "configurations/ios_v1.json"))
])
Hotwire.registerBridgeComponents([FormComponent.self])
// Optional knobs: Hotwire.config.applicationUserAgentPrefix,
// Hotwire.config.showDoneButtonOnModals, debug logging, etc.
```

`.file` is the bundled fallback; `.server` fetches (and caches) the live
version so you can change app behavior without an App Store release.

## 3. Android setup

Dependencies in the module `build.gradle.kts`:

```kotlin
dependencies {
  implementation("dev.hotwire:core:<latest>")
  implementation("dev.hotwire:navigation-fragments:<latest>")
}
```

`AndroidManifest.xml` needs `<uses-permission
android:name="android.permission.INTERNET"/>`. The entire layout
(`activity_main.xml`) is one navigator host:

```xml
<androidx.fragment.app.FragmentContainerView
  xmlns:android="http://schemas.android.com/apk/res/android"
  xmlns:app="http://schemas.android.com/apk/res-auto"
  android:id="@+id/main_nav_host"
  android:name="dev.hotwire.navigation.navigator.NavigatorHost"
  android:layout_width="match_parent"
  android:layout_height="match_parent"
  app:defaultNavHost="false" />
```

```kotlin
class MainActivity : HotwireActivity() {
  override fun onCreate(savedInstanceState: Bundle?) {
    enableEdgeToEdge()
    super.onCreate(savedInstanceState)
    setContentView(R.layout.activity_main)
    findViewById<View>(R.id.main_nav_host).applyDefaultImeWindowInsets()
  }

  override fun navigatorConfigurations() = listOf(
    NavigatorConfiguration(
      name = "main",
      startLocation = "https://myapp.example",
      navigatorHostId = R.id.main_nav_host
    )
  )
}
```

App-level configuration in your `Application.onCreate`:

```kotlin
Hotwire.loadPathConfiguration(
  context = this,
  location = PathConfiguration.Location(
    assetFilePath = "json/configuration.json",                       // bundled fallback
    remoteFileUrl = "https://myapp.example/configurations/android_v1.json"
  )
)
Hotwire.registerBridgeComponents(
  BridgeComponentFactory("form", ::FormComponent)
)
```

## 4. Navigation: the routing table and server-driven stack control

Every link tap consults the path configuration; the matched `context` +
`presentation` decide the stack operation. The behavior matrix (State = is a
modal currently up):

| State | Context | Presentation | Behavior |
|---|---|---|---|
| default | default | default | Push (replace if same page; pop-then-visit if previous screen is same URL) |
| default | default | replace | Replace top of main stack |
| default | modal | default/replace | Present as a modal |
| modal | default | default | Dismiss modal, then push on main stack |
| modal | default | replace | Dismiss modal, then replace on main stack |
| modal | modal | default | Push on the modal stack |
| modal | modal | replace | Replace top of modal stack |
| any | any | pop | Pop top screen (dismiss if last modal screen) |
| any | any | refresh | Pop, then refresh the newly visible screen |
| any | any | clear_all | Dismiss modal, pop to root, refresh root |
| any | any | replace_root | Dismiss modal, pop to root, replace root |
| any | any | none | Nothing |

**Server-driven stack control (Rails)** — turbo-rails ships historical
location redirects that Hotwire Native (≥1.2.0) intercepts, so one controller
serves web and native correctly:

```ruby
def create
  @task = Task.create!(task_params)
  recede_or_redirect_to tasks_path, notice: "Created"
  # native: dismiss the modal / pop the screen; web: normal redirect
end
```

- `recede_or_redirect_to(url)` — pop the visible screen (dismiss modal first).
- `refresh_or_redirect_to(url)` — reload the visible screen, invalidating cache.
- `resume_or_redirect_to(url)` — just dismiss any modal; stay put.

Pattern: forms open in a modal (path config: `/new$`, `/edit$` → `context:
modal`), submit, then `recede_or_redirect_to` — the modal closes and the
list underneath refreshes.

**Route decision handlers** decide *whether* a URL is in-app at all. Defaults:
same-domain → in-app; external http(s) → `SFSafariViewController` (iOS) /
Custom Tab (Android); other schemes (`mailto:`, `sms:`) → system. Customize by
subclassing `RouteDecisionHandler` and registering in priority order:
`Hotwire.registerRouteDecisionHandlers([AppNavigationRouteDecisionHandler(),
MyHandler()])` (same shape in Kotlin).

**Manual navigation** from native code: iOS
`navigator.route(url)` / `.pop()` / `.clearAll()` (each takes
`animated: false`); Android `delegate.currentNavigator?.route(location)` /
`pop()` / `clearAll()` inside a `HotwireActivity` (plain `navigator.` inside a
`HotwireFragment`).

## 5. Path configuration (JSON)

One JSON document per platform drives app behavior — served from your web app
so it's updatable without releases:

```json
{
  "settings": {
    "feature_flags": [{ "name": "new_onboarding", "enabled": true }]
  },
  "rules": [
    {
      "patterns": [".*"],
      "properties": { "context": "default", "pull_to_refresh_enabled": true }
    },
    {
      "patterns": ["/new$", "/edit$"],
      "properties": { "context": "modal", "pull_to_refresh_enabled": false }
    },
    {
      "patterns": ["/numbers$"],
      "properties": { "view_controller": "numbers", "uri": "hotwire://fragment/numbers" }
    }
  ]
}
```

- **`settings`** — your sandbox: feature flags, tab definitions, anything the
  app reads at launch.
- **`rules`** — evaluated **sequentially**; later rules override earlier
  ones for matching URLs. Convention: rule 1 matches `.*` and sets defaults;
  subsequent rules specialize.
- **`patterns`** — regular expressions matched against the URL path.
- **Cross-platform properties**: `context` (`default` | `modal`),
  `presentation` (`default` | `push` | `pop` | `replace` | `replace_root` |
  `clear_all` | `refresh` | `none`), `pull_to_refresh_enabled` (defaults:
  iOS `true`, Android `false`), `animated` (default `true`).
- **Android-only**: `uri` (**required** for a rule to map to a
  fragment/activity destination), `fallback_uri` (older app versions),
  `title` (toolbar title for native destinations).
- **iOS-only**: `view_controller` (identifier of a native controller),
  `modal_style` (`large` | `medium` | `full` | `page_sheet` | `form_sheet`),
  `modal_dismiss_gesture_enabled` (default `true`).
- You may add arbitrary custom properties and read them from the matched
  path properties in native code.
- **Version the remote files** (`/configurations/ios_v1.json`,
  `android_v1.json`): breaking changes → new versioned URL, old app builds
  keep the old file. Serve them from a plain Rails controller/route.

## 6. Bridge components — web side

Bridge components let web pages drive native UI (native buttons, menus,
toasts) with graceful degradation on the plain web. The web side is a
Stimulus controller subclass from `@hotwired/hotwire-native-bridge`:

```html
<form method="post" data-controller="bridge--form">
  <button type="submit"
          data-bridge--form-target="submit"
          data-bridge-title="Submit">
    Submit Form
  </button>
</form>
```

```javascript
// app/javascript/controllers/bridge/form_controller.js
import { BridgeComponent, BridgeElement } from "@hotwired/hotwire-native-bridge"

export default class extends BridgeComponent {
  static component = "form"          // MUST match the native component name
  static targets = ["submit"]

  submitTargetConnected(target) {
    const submitButton = new BridgeElement(target)
    this.send("connect", { submitTitle: submitButton.title }, () => {
      target.click()                 // native bar button tapped → submit the real form
    })
  }
}
```

`BridgeComponent` adds to a normal Stimulus controller:
`static component` (the contract name), `this.send(event, data, callback)`
(message the native side; callback runs when it replies), `this.enabled`
(is the component supported by this app build), `this.bridgeElement`, and
`this.platformOptingOut`.

`BridgeElement` wraps any element for bridge data: `.title` (from
`data-bridge-title` → `aria-label` → text/value), `.disabled`/`.enabled`
(`data-bridge-disabled="true|false|ios|android"`),
`.bridgeAttribute(name)` / `.setBridgeAttribute(name, value)` /
`.removeBridgeAttribute(name)` (the `data-bridge-*` namespace),
`.attribute(name)`, `.hasClass(name)`, `.click()`,
`.enableForComponent(component)`.

Per-instance platform opt-out: `data-controller-optout-ios` /
`data-controller-optout-android` on the controller element. Convention: keep
these controllers in a `controllers/bridge/` subdirectory
(`data-controller="bridge--form"`) so web-only Stimulus stays separate. On the
plain web the component simply never activates — the HTML button keeps
working. Design every bridge component that way.

## 7. Bridge components — native side (Swift / Kotlin)

The native counterpart shares the component name and handles messages. The
canonical shape (see the platform pages under native.hotwired.dev/ios and
/android for full projects):

```swift
// iOS — FormComponent.swift
import HotwireNative
import UIKit

final class FormComponent: BridgeComponent {
  override class var name: String { "form" }

  override func onReceive(message: Message) {
    guard message.event == "connect",
          let data: MessageData = message.data() else { return }
    configureBarButton(title: data.submitTitle)
  }

  private func configureBarButton(title: String) {
    // Add a UIBarButtonItem titled `title` to the delegate's view controller;
    // its action calls: self.reply(to: "connect")  → runs the web callback
  }

  private struct MessageData: Decodable { let submitTitle: String }
}
```

```kotlin
// Android — FormComponent.kt
class FormComponent(
  name: String,
  private val delegate: BridgeDelegate<HotwireDestination>
) : BridgeComponent<HotwireDestination>(name, delegate) {

  override fun onReceive(message: Message) {
    if (message.event != "connect") return
    val data = message.data<MessageData>() ?: return
    // Add a toolbar menu item titled data.submitTitle; on tap:
    // replyTo("connect")   → runs the web callback
  }

  @Serializable
  data class MessageData(val submitTitle: String)
}
```

Register at launch (`Hotwire.registerBridgeComponents([...])` /
`BridgeComponentFactory("form", ::FormComponent)` — see §2/§3). The flow is
always: web `send(event, data, callback)` → native `onReceive(message)` →
native UI → user interacts → native `reply/replyTo(event)` → web callback
fires. Keep messages small (titles, flags, ids) — the web page remains the
source of truth.

## 8. Native screens

For the few screens where web genuinely can't compete (maps, camera,
barcode scanners, heavy offline), map a URL to a fully native screen in path
configuration:

- **iOS** — rule sets `"view_controller": "numbers"`; your
  `UIViewController` conforms to `PathConfigurationIdentifiable` with
  `static var pathConfigurationIdentifier: String { "numbers" }`. Handle
  unknown identifiers/routes in your `Navigator` delegate if customizing.
- **Android** — rule sets `"uri": "hotwire://fragment/numbers"`; your
  `HotwireFragment` subclass is annotated
  `@HotwireDestinationDeepLink(uri = "hotwire://fragment/numbers")` and
  registered via `Hotwire.registerFragmentDestinations(...)`. `fallback_uri`
  covers app versions that lack the destination; `title` sets the toolbar.

The web app still owns the URL: `/numbers` renders HTML for browsers, while
apps intercept it natively. Keep both in sync or redirect web users
elsewhere.

## 9. Web-side detection and native-aware views

The apps append **"Hotwire Native"** to the WebView user agent (plus platform
and your `applicationUserAgentPrefix`). In Rails, turbo-rails gives you:

```ruby
class ApplicationController < ActionController::Base
  before_action { request.variant = :native if hotwire_native_app? }
end
```

- `hotwire_native_app?` — helper available in controllers and views.
- Variants render `show.html+native.erb` when present — the clean way to
  serve stripped-down native layouts.
- Hide web chrome for native: the native shell provides top bars and tabs, so
  wrap your web `<nav>`/header/footer in
  `<% unless hotwire_native_app? %>` (or use the native layout variant).
  Page `<title>` becomes the native screen title — keep titles short and
  meaningful.
- Auth: cookies flow through the web views, so session auth works unchanged;
  present sign-in as a `context: modal` rule and `recede_or_redirect_to`
  after success.

## 10. Rules of thumb

Build web-first and wrap; don't fork the product per platform. Start with
zero native screens and zero bridge components — add a bridge component only
when a specific interaction feels wrong (form submit buttons, menus, toasts
are the classic first three), and a native screen only when the web version
is genuinely inadequate. Keep the path configuration remote and versioned so
behavior changes skip app review. Test every flow on both platforms or scope
rules per platform explicitly. And when navigation misbehaves, debug in this
order: the server's redirect status → the matched path-configuration rule →
the routing table in §4.
