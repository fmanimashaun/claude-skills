# Audit: plugins/rails-stack/skills/hotwire/references/native.md (2026-10-12, doctrine-verifier, read-only)
Sources: source at tags hotwire-native-ios 1.3.1, hotwire-native-android 1.3.2, hotwire-native-bridge v1.2.2, turbo-rails main (shallow clones of github.com/hotwired/*).

| # | Claim (native.md:line) | Verdict | Source + quote | Version boundary |
|---|---|---|---|---|
| 1 | :76 hideTabBarWhenPushed default false, "renamed from hidesTabBarWhenPushed" | REFUTED (narrow) | ios Source/HotwireConfig.swift:27 `public var hideTabBarWhenPushed = false`; commit 90d34c3 "hidesTabBarWhenPushed -> hideTabBarWhenPushed" lies inside 1.2.2..1.3.0; 1.2.2 HotwireConfig has neither name | New in 1.3.0; the old name never shipped in a release. Drop "renamed from" |
| 2 | :77 animateReplaceActions default false | CONFIRMED | HotwireConfig.swift:30 `public var animateReplaceActions = false` | 1.3.0 |
| 3 | :78 redirectResolutionTimeout default 30 | CONFIRMED | HotwireConfig.swift:33 `= 30` | |
| 4 | :75 backButtonDisplayMode exists | CONFIRMED | HotwireConfig.swift:24 | |
| 5 | :80 makeCustomErrorView(error, handler) -> ErrorPresentableView | CONFIRMED | HotwireConfig.swift:92 `(HotwireNativeError, ErrorPresenter.Handler?) -> any ErrorPresentableView` | 1.3.0 |
| 6 | :83 Hotwire.config.log; :74 debugLoggingEnabled iOS | CONFIRMED | HotwireConfig.swift:37,46 | |
| 7 | :84 matchQueryStrings (example sets true) | CONFIRMED (note) | PathConfiguration.swift:25 `public var matchQueryStrings = true` — already default; example line is a no-op | |
| 8 | :67-71 loadPathConfiguration(from:[...]) / registerBridgeComponents([...]) | CONFIRMED | Source/Hotwire.swift:11,28 | |
| 9 | :154-157 Android logger pluggable, debugLoggingEnabled removed in 1.3.0, logLevel | CONFIRMED | android core HotwireConfig.kt:41 `var logger: HotwireLogger`; HotwireLogger.kt:4 `var logLevel`; 1.2.8 HotwireConfig.kt:40 had `debugLoggingEnabled`, 1.3.2 does not | removed 1.3.0 |
| 10 | :157-159 webViewDebuggingEnabled, jsonConverter, defaultFragmentDestination | CONFIRMED | HotwireConfig.kt:28,49; HotwireNavigation.kt:23 | |
| 11 | :112,127 NavigatorHost, applyDefaultImeWindowInsets | CONFIRMED | NavigatorHost.kt:21; NavigationExtensions.kt:23 | |
| 12 | :210-211 registerRouteDecisionHandlers, Kotlin varargs | CONFIRMED | ios Hotwire.swift:16 `[any RouteDecisionHandler]`; HotwireNavigation.kt:40 `vararg decisionHandlers: Router.RouteDecisionHandler` | |
| 13 | :216-218 iOS matches(proposal:configuration:), handle(...navigator: Navigating) | CONFIRMED | RouteDecisionHandler.swift:17,26-28 `navigator: Navigating` | 1.3.0 |
| 14 | :220-223 Android matches/handle(proposal, configuration, activity); proposal.location String; customRouteDecision(proposal) | CONFIRMED | Router.kt:29-43; VisitProposal.kt:7 `val location: String`; HotwireDestination.kt:119 | 1.3.0 |
| 15 | :231-233 route(options:parameters:), pop(animated=true), clearAll(animated=false) | CONFIRMED | Navigator.swift:67,91,99 | |
| 16 | :271 presentation `push` listed as cross-platform | REFUTED | ios Navigation.swift Presentation enum: default, pop, replace, refresh, clear_all, replace_root, none — no `push`; Android enum has PUSH | push is Android-only |
| 17 | :272-273 pull_to_refresh_enabled default iOS true / Android false; animated default true | CONFIRMED | PathPropertiesExtensions.swift:30,73 `?? true`; PathConfiguration.kt:183 `?: false`, :186 `?: true` | |
| 18 | :274-276 Android uri, fallback_uri, title | CONFIRMED | PathConfiguration.kt:174-180 | |
| 19 | :278-279 modal_style values; modal_dismiss_gesture_enabled default true | CONFIRMED | Navigation.swift ModalStyle medium/large/full/page_sheet/form_sheet; PathPropertiesExtensions.swift:34 `?? true` | |
| 20 | :319-331 BridgeComponent send/enabled/bridgeElement/platformOptingOut; BridgeElement API | CONFIRMED | bridge src/bridge_component.js:48,56,63,86; bridge_element.js:8-60 (title from data-bridge-title -> aria-label; disabled === "true" or platform; click()) | bridge v1.2.2 |
| 21 | :333 data-controller-optout-ios/android | CONFIRMED | bridge_component.js:52 `data-controller-optout-${bridgePlatform}` | |
| 22 | :410 NavigatorDelegate handle(proposal:from:) -> ProposalResult | CONFIRMED | NavigatorDelegate.swift:17 | |
| 23 | :426 registerFragmentDestinations varargs | CONFIRMED | HotwireNavigation.kt:67 | |
| 24 | :436 HotwireTabBarController(lazyLoadTabs:) default false; isSearchTab | CONFIRMED | HotwireTabBarController.swift:24 `lazyLoadTabs: Bool = false`; HotwireTab.swift:17 | 1.3.0 |
| 25 | :452-455 Safari handler universalLinksOnly, only init() | CONFIRMED | SafariViewControllerRouteDecisionHandler.swift:8 `public init() {}`, :55 `options.universalLinksOnly = true` | 1.3.0 |
| 26 | :196-198,472 recede/refresh/resume_or_redirect_to, hotwire_native_app? | CONFIRMED | turbo-rails app/controllers/turbo/native/navigation.rb:15,22,27,32 | |
| 27 | :463 UA contains "Hotwire Native" | CONFIRMED | ios Bridge/UserAgent.swift:10 "Hotwire Native iOS;"; android HotwireConfig.kt:67 | |

Not verified (out of budget, left unchanged): §4 behaviour matrix rows, patch-note PR numbers (#261/#207/#205/#191/#202), ≤1.2.2/≤1.2.8 old handler shape.
