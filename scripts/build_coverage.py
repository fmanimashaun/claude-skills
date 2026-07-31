#!/usr/bin/env python3
"""Generate the fidara component coverage matrix from a mechanical corpus enumeration.

Run:  python3 scripts/build_coverage.py            # regenerate coverage.md
      python3 scripts/build_coverage.py --check    # fail if the committed file is stale
      python3 scripts/build_coverage.py --audit    # list unclassified corpus entries
      python3 scripts/build_coverage.py --selftest  # prove the guards fire and stay silent

WHY THIS IS A SCRIPT (#124). The component work so far came from *sampling*, so
"is the library complete?" had no answer. Sampling cannot answer it: a component nobody
thought of is indistinguishable from one deliberately skipped. Enumeration can, but only
if it is re-runnable -- a list built by hand is stale the day a corpus updates.

THE LOAD-BEARING GUARANTEE is the totality guard: every entry mechanically discovered in a
corpus must be claimed by exactly one row of ENTRIES, or the build FAILS and names the
stragglers. So a new Tailwind UI directory cannot be silently ignored -- it breaks the build
until someone classifies it. An unexplained omission is indistinguishable from an oversight,
which is the failure this exists to fix.

THE AXIS IS GUIDANCE, NOT AVAILABILITY. Components are built just-in-time in the project when
a screen needs one; the kit ships doctrine, not a prebuilt library. So nothing here is
"withheld" and there is no build queue: every row is buildable on demand, and the status says
only how much the doctrine already tells you -- `documented` (an entry defines it),
`derivable` (compose it from documented parts), or `needs doctrine #N` (an a11y/interaction
contract is unwritten, so building it today carries risk; the issue tracks writing it).

An earlier revision had `deferred` and `declined` statuses. Both were wrong for a JIT model:
they answered "will we offer this?" when the only useful question is "what does an agent need
to know to build it correctly right now?" -- and "no current product need" is a snapshot of
the roadmap masquerading as a principle. Every row now answers HOW to build it and WHERE to
use it, and the guard enforces both.

Corollary worth stating plainly: the *union* is mechanical, the *alignment* is curated. Which
Tailwind directory corresponds to which Flowbite component and to which of our catalog entries
is judgement, recorded in ENTRIES and reviewable in the diff. This script does not pretend the
judgement is automatic; it guarantees the judgement is COMPLETE.

LICENSING BOUNDARY (see #89, #123). The corpora are licensed references, gitignored, never
redistributed. This reads only DIRECTORY NAMES and emits only names, statuses and our own
prose. No markup, class list, or asset from either kit is copied into the generated file. That
is also why this lives in scripts/ (maintainer tooling) rather than shipping in the plugin:
without the local corpora it cannot regenerate, and it says so instead of emitting a hollow
file.

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# The licensed corpora live in ONE gitignored subfolder — a nested clone of the private
# design-corpora repo (setup in CLAUDE.md, "Design corpora"). One ignored path instead of
# three root-level entries, and no symlinks: a symlink is git mode 120000, which a
# trailing-slash ignore pattern cannot match (#197), and creating one needs Developer Mode on
# Windows — a platform this repo's tooling supports (CLAUDE.md, "Platform").
CORPORA_ROOT = REPO / "design-corpora"
TW_ROOT = CORPORA_ROOT / "tailwind-ui" / "html" / "components"
TW_FAMILIES = ("application-ui", "marketing", "ecommerce")
OUT = REPO / "skills" / "fidara-design" / "references" / "coverage.md"

# ---------------------------------------------------------------------------------------
# Flowbite's published catalogue.
#
# SOURCE: https://flowbite.com/docs/ navigation sidebar, sections "Components", "Forms" and
# "Typography", read 2026-07-29. Recorded as data rather than fetched at runtime: a build
# that needs the network is a build that breaks when the network does, and this is the kind
# of list that changes on Flowbite's release cadence, not ours.
#
# Re-verify by opening any component page and reading the sidebar. Two names commonly
# attributed to Flowbite are NOT in its catalogue and must not be added here: "Separator"
# (their name is `HR`, under Typography) and a cookie-consent component (none exists). #124
# asserted both; checked and corrected.
# ---------------------------------------------------------------------------------------
FLOWBITE_CATALOG: dict[str, tuple[str, ...]] = {
    "Components": (
        "Accordion", "Alerts", "Avatar", "Badge", "Banner", "Bottom Navigation",
        "Breadcrumb", "Buttons", "Button Group", "Card", "Carousel", "Chat Bubble",
        "Clipboard", "Datepicker", "Device Mockups", "Drawer", "Dropdowns", "Footer",
        "Gallery", "Indicators", "Jumbotron", "KBD", "List Group", "Mega Menu", "Modal",
        "Navbar", "Pagination", "Popover", "Progress", "Rating", "Sidebar", "Skeleton",
        "Speed Dial", "Spinner", "Stepper", "Tables", "Tabs", "Timeline", "Toast",
        "Tooltips", "QR Code", "Video",
    ),
    "Forms": (
        "Input Field", "File Input", "Search Input", "Number Input", "Phone Input",
        "Select", "Textarea", "Timepicker", "Checkbox", "Radio", "Toggle", "Range",
        "Floating Label",
    ),
    "Typography": (
        "Headings", "Paragraphs", "Blockquote", "Images", "Lists", "Links", "Text", "HR",
    ),
}

PRIMITIVE, COMPONENT, COMPOSITION, ARCHETYPE = "primitive", "component", "composition", "page archetype"


@dataclass(frozen=True)
class Entry:
    name: str
    kind: str
    status: str
    interaction: str = "—"
    tw: tuple[str, ...] = ()
    fb: tuple[str, ...] = ()
    # Caveats: when this is the WRONG choice, and the a11y trap to avoid. Optional.
    note: str = ""
    # HOW to build it -- the documented parts it composes from. Required unless
    # `documented`, which points at its own reference entry instead.
    build: str = ""

    @property
    def is_documented(self) -> bool:
        return self.status.startswith("documented")

    @property
    def is_derivable(self) -> bool:
        return self.status.startswith("derivable")

    @property
    def needs_doctrine(self) -> bool:
        return self.status.startswith("needs doctrine")


def E(name, kind, status, interaction="—", tw=(), fb=(), note="", build="") -> Entry:
    return Entry(name, kind, status, interaction, tuple(tw), tuple(fb), note, build)


# ---------------------------------------------------------------------------------------
# Evidence for every `documented` claim: a literal string that must occur in the shipped
# reference docs.
#
# `documented` is the one status a reader acts on directly, and a wrong one is worse than a
# wrong `derivable` -- it tells an agent to use a catalogue entry that does not exist, which is
# exactly the dangling reference v1.26.0 had to fix (page-anatomies named "heading block",
# "Breadcrumb" and "description list" before any of them had catalogue entries). So the claim
# is checked against the docs, not asserted here.
#
# Strings carry a trailing newline where a shorter heading is a PREFIX of a longer one --
# "## Button" also matches "## Button group", which would let a missing Button row pass.
# ---------------------------------------------------------------------------------------
DOCUMENTED_EVIDENCE: dict[str, str] = {
    # shells + anatomies (page-anatomies.md)
    "Sidebar shell": "## 1. Sidebar shell",
    "Stacked shell": "## 2. Stacked shell",
    "Multi-column shell": "## 3. Multi-column shell",
    "Home / dashboard anatomy": "## Home / dashboard",
    "Detail anatomy": "## Detail\n",
    "Settings anatomy": "## Settings\n",
    "Landing page archetype": "## Landing\n",
    "Pricing page archetype": "## Pricing\n",
    "About page archetype": "## About\n",
    "Error page archetype (404/500)": "## Error (404 / 500)\n",
    "Auth page archetype (sign-in / sign-up / reset)": "## Auth (sign-in / sign-up / reset)\n",
    "Storefront page archetype": "## Storefront\n",
    "Category page archetype": "## Category\n",
    "Product page archetype": "## Product\n",
    "Cart page archetype": "## Cart\n",
    "Checkout page archetype": "## Checkout\n",
    "Order detail page archetype": "## Order detail\n",
    "Order history page archetype": "## Order history\n",
    # catalogue components (components.md)
    "Button": "## Button\n",
    "Button group": "## Button group\n",
    # Trailing newline anchors the exact heading: "## Disclosure" alone would also match a longer
    # heading, which is how a missing entry could pass (see the Button/Button-group note above).
    "Accordion / Disclosure": "## Disclosure / Accordion\n",
    "Combobox / Autocomplete": "## Combobox / Autocomplete\n",
    "Progress bar": "## Progress bar\n",
    "File upload / Dropzone": "## File upload / Dropzone (#95)\n",
    "Copy to clipboard": "## Copy to clipboard (#95)\n",
    "Range input": "## Range input (#95)\n",
    "Calendar / Date picker / Time picker": "## Calendar / Date picker / Time picker (#95)\n",
    "Drawer / off-canvas": "## Drawer / off-canvas\n",
    "Carousel / Slider": "## Carousel\n",
    "Image gallery / Lightbox": "## Image gallery / Lightbox\n",
    "Skeleton / loading placeholder": "## Skeleton / loading placeholder\n",
    "Spinner / busy indicator": "## Spinner / busy indicator\n",
    "Badge / Tag / Chip": "## Badge / Tag / Chip",
    "Avatar": "## Avatar\n",
    "Dropdown / Menu": "## Dropdown / Menu",
    "Card": "## Card\n",
    "Heading blocks (page / section / card)": "## Heading blocks (page / section / card)",
    "Alert / Banner": "## Alert / Banner",
    "Modal / Dialog": "## Modal / Dialog",
    "Toast / Notification": "## Toast / Notification",
    "Tooltip / Popover": "## Tooltip / Popover",
    "Table (CRUD)": "## Table (CRUD)",
    "Description list": "## Description list\n",
    "Media object": "## Media object\n",
    "Pagination": "## Pagination\n",
    "Empty state": "## Empty state\n",
    "Breadcrumbs": "## Breadcrumbs\n",
    "Navigation — header / navbar": "## Navigation (header + sidebar + tabs)",
    "Navigation — sidebar / vertical": "## Navigation (header + sidebar + tabs)",
    "Tabs": "## Tabs",
    "Logo / Brand mark": "## Logo / Brand mark",
    "Divider": "## Divider\n",
    # primitives + compositions
    "List container (divide-y)": "divide-y divide-border",
    "Stat tile": "stat cards",
    "Prose / long-form type": "--text-step",
    "Frame (aspect-ratio media)": "@utility frame",
    "Center / container": "@utility center",
    # form controls
    "Form layout": "## Forms",
    "Text input": "### Input recipe (helper)",
    "Select": "### Field anatomy",
    "Textarea": "### Field anatomy",
    "Checkbox": "### Checkbox / Radio / Switch",
    "Radio group": "### Checkbox / Radio / Switch",
    "Toggle / Switch": "### Checkbox / Radio / Switch",
}


# ---------------------------------------------------------------------------------------
# The curated alignment. `shipped` means an entry exists in components.md /
# component-implementations.md / page-anatomies.md / layout-primitives.md TODAY -- not that
# it is planned or partially done.
# ---------------------------------------------------------------------------------------
ENTRIES: tuple[Entry, ...] = (
    # ---- shells and page anatomies (shipped in v1.24.0 / v1.26.0) ----------------------
    E("Sidebar shell", ARCHETYPE, "documented", "disclosure (mobile drawer)",
      ["application-ui/application-shells/sidebar"]),
    E("Stacked shell", ARCHETYPE, "documented", "disclosure (mobile menu)",
      ["application-ui/application-shells/stacked"]),
    E("Multi-column shell", ARCHETYPE, "documented", "disclosure (mobile drawer)",
      ["application-ui/application-shells/multi-column"]),
    E("Home / dashboard anatomy", ARCHETYPE, "documented", "—",
      ["application-ui/page-examples/home-screens"]),
    E("Detail anatomy", ARCHETYPE, "documented", "—",
      ["application-ui/page-examples/detail-screens"]),
    E("Settings anatomy", ARCHETYPE, "documented", "—",
      ["application-ui/page-examples/settings-screens"]),

    # ---- shipped catalogue components --------------------------------------------------
    E("Button", COMPONENT, "documented", "—", ["application-ui/elements/buttons"], ["Buttons"]),
    E("Button group", COMPONENT, "documented", "list-navigation (single-select only)",
      ["application-ui/elements/button-groups"], ["Button Group"],
      "actions = role=group; single-select = role=radiogroup — different elements, not variants"),
    E("Badge / Tag / Chip", COMPONENT, "documented", "—",
      ["application-ui/elements/badges"], ["Badge"]),
    E("Avatar", COMPONENT, "documented", "—", ["application-ui/elements/avatars"], ["Avatar"]),
    E("Dropdown / Menu", COMPONENT, "documented", "menu",
      ["application-ui/elements/dropdowns"], ["Dropdowns"]),
    E("Card", COMPONENT, "documented", "—", ["application-ui/layout/cards"], ["Card"]),
    E("Heading blocks (page / section / card)", COMPONENT, "documented", "—",
      ["application-ui/headings/page-headings", "application-ui/headings/section-headings",
       "application-ui/headings/card-headings"], ["Headings"],
      "one anatomy; scale is the only axis, so a card heading can never be an h2 styled small"),
    E("Alert / Banner", COMPONENT, "documented", "dismissible (optional)",
      ["application-ui/feedback/alerts", "marketing/elements/banners"], ["Alerts", "Banner"]),
    E("Modal / Dialog", COMPONENT, "documented", "dialog",
      ["application-ui/overlays/modal-dialogs"], ["Modal"]),
    E("Toast / Notification", COMPONENT, "documented", "dismissible",
      ["application-ui/overlays/notifications"], ["Toast"]),
    E("Tooltip / Popover", COMPONENT, "documented", "hover/focus popover", [], ["Tooltips", "Popover"]),
    E("Table (CRUD)", COMPONENT, "documented", "—", ["application-ui/lists/tables"], ["Tables"]),
    E("Description list", COMPONENT, "documented", "—",
      ["application-ui/data-display/description-lists"], [],
      "blank values render an em dash + sr-only 'not set', never an empty <dd>"),
    E("Media object", COMPONENT, "documented", "—", ["application-ui/layout/media-objects"], [],
      "never stacks — the side-by-side relationship IS the pattern"),
    E("Pagination", COMPONENT, "documented", "—", ["application-ui/navigation/pagination"], ["Pagination"]),
    E("Empty state", COMPONENT, "documented", "—", ["application-ui/feedback/empty-states"], []),
    E("Breadcrumbs", COMPONENT, "documented", "—",
      ["application-ui/navigation/breadcrumbs"], ["Breadcrumb"],
      "separators are aria-hidden markup, never ::after; truncates first → … → last two"),
    E("Navigation — header / navbar", COMPONENT, "documented", "disclosure",
      ["application-ui/navigation/navbars"], ["Navbar"]),
    E("Navigation — sidebar / vertical", COMPONENT, "documented", "disclosure (collapsible groups)",
      ["application-ui/navigation/sidebar-navigation", "application-ui/navigation/vertical-navigation"],
      ["Sidebar"]),
    E("Tabs", COMPONENT, "documented", "list-navigation", ["application-ui/navigation/tabs"], ["Tabs"]),
    E("Logo / Brand mark", COMPONENT, "documented", "—", [], [],
      "ours, not from either corpus: clear-space 1.5×, min 20px / lockup 140px (brand.md)"),
    E("Divider", PRIMITIVE, "documented", "—",
      ["application-ui/layout/dividers"], ["HR"],
      "an <hr> is already role=separator; in lists the answer is divide-y on the container"),
    E("List container (divide-y)", PRIMITIVE, "documented", "—",
      ["application-ui/layout/list-containers"], []),
    E("Stat tile", COMPOSITION, "documented", "—",
      ["application-ui/data-display/stats"], [],
      "page-anatomies composes these from Card, one metric each — deliberately not a new component"),
    E("Prose / long-form type", PRIMITIVE, "documented", "—", [],
      ["Paragraphs", "Blockquote", "Lists", "Text"],
      "fluid --text-step-* scale + measure in foundations-tokens.md"),
    E("Inline link", PRIMITIVE, "needs doctrine #95", "—", [], ["Links"],
      "surfaced by this matrix: we ship a Button `link` VARIANT (components.md) and links inside "
      "prose, but no standalone inline-link token — so an agent styling a body link has nothing to "
      "cite. Small, and a real gap"),
    E("Frame (aspect-ratio media)", PRIMITIVE, "documented", "—", [], ["Images"]),
    E("Center / container", PRIMITIVE, "documented", "—", ["application-ui/layout/containers"], []),

    # ---- shipped form controls ---------------------------------------------------------
    E("Form layout", COMPONENT, "documented", "—", ["application-ui/forms/form-layouts"], [],
      "simple_form owns every form; the wrapper anatomy is defined once in an initializer"),
    E("Text input", COMPONENT, "documented", "—", ["application-ui/forms/input-groups"],
      ["Input Field", "Floating Label"], "floating label is a variant, not a component"),
    E("Select", COMPONENT, "documented", "—", ["application-ui/forms/select-menus"], ["Select"]),
    E("Textarea", COMPONENT, "documented", "—", ["application-ui/forms/textareas"], ["Textarea"]),
    E("Checkbox", COMPONENT, "documented", "—", ["application-ui/forms/checkboxes"], ["Checkbox"]),
    E("Radio group", COMPONENT, "documented", "—", ["application-ui/forms/radio-groups"], ["Radio"]),
    E("Toggle / Switch", COMPONENT, "documented", "—", ["application-ui/forms/toggles"], ["Toggle"]),

    # ---- planned: #95 application-ui expansion -----------------------------------------
    E("Drawer / off-canvas", COMPONENT, "documented", "modal (overlay) / sidebar (persistent)",
      ["application-ui/overlays/drawers"], ["Drawer"],
      "ONE ROW, TWO CONTRACTS: the overlay drawer is a modal dialog and traps focus; the "
      "persistent push drawer is not a dialog and must not"),
    E("Stacked list", COMPONENT, "derivable", "—",
      ["application-ui/lists/stacked-lists"], ["List Group"],
      "a media object in a divide-y container — build on shipped parts, do not re-implement"),
    E("Grid list", COMPOSITION, "derivable", "—", ["application-ui/lists/grid-lists"], [],
      "grid-auto + Card; a composition, so likely a recipe rather than a component"),
    E("Activity feed / Timeline", COMPONENT, "derivable", "—",
      ["application-ui/lists/feeds"], ["Timeline"]),
    E("Progress bar", COMPONENT, "documented", "—",
      ["application-ui/navigation/progress-bars"], ["Progress"],
      "the Flowbite audit surfaced LABELLED progress bars specifically"),
    E("Command palette", COMPONENT, "derivable", "new controller (filter + list-navigation)",
      ["application-ui/navigation/command-palettes"], []),
    E("Combobox / Autocomplete", COMPONENT, "documented", "new controller (filter + list-navigation)",
      ["application-ui/forms/comboboxes"], []),
    E("Action panel", COMPONENT, "derivable", "—", ["application-ui/forms/action-panels"], []),
    E("File upload / Dropzone", COMPONENT, "documented", "new controller (drag + drop)", [],
      ["File Input"], "the native input stays VISIBLE — hiding it behind the dropzone fails WCAG 2.5.7"),
    E("Search input", COMPONENT, "derivable", "—", [], ["Search Input"]),
    E("Number input", COMPONENT, "derivable", "—", [], ["Number Input"]),
    E("Range input", COMPONENT, "documented", "—", [], ["Range"],
      "native `input type=range` already IS role=slider; custom only for two thumbs"),
    E("Status indicator / dot", COMPONENT, "derivable", "—", [], ["Indicators"],
      "surfaced by the audit as nav count badge + status badge inside table rows"),
    E("Skeleton / loading placeholder", COMPONENT, "documented", "—", [], ["Skeleton"],
      "Turbo frame loading states need this; without it agents invent spinners"),
    E("Spinner / busy indicator", COMPONENT, "documented", "—", [], ["Spinner"]),
    E("Stepper / wizard", COMPONENT, "needs doctrine #95", "—", [], ["Stepper"],
      "also feeds #91's checkout flow"),
    E("Copy to clipboard", COMPONENT, "documented", "new controller", [], ["Clipboard"],
      "the announcement IS the feature; a repeat needs the region cleared or it stays silent"),
    E("Keyboard key (KBD)", PRIMITIVE, "derivable", "—", [], ["KBD"],
      "trivial, but the command palette needs it"),
    E("Accordion / Disclosure", COMPONENT, "documented", "disclosure (collapse + accordion)",
      [], ["Accordion"],
      "732 instances in the audit corpus — the second most common interactive pattern after links. "
      "APG-verified contract (#142): what is required, and what is ours, is stated separately"),

    # ---- planned: #90 marketing sections + page compositions ---------------------------
    E("Hero section", COMPOSITION, "derivable", "—", ["marketing/sections/heroes"], ["Jumbotron"]),
    E("Feature section", COMPOSITION, "derivable", "—", ["marketing/sections/feature-sections"], []),
    E("Bento grid section", COMPOSITION, "derivable", "—", ["marketing/sections/bento-grids"], []),
    E("CTA section", COMPOSITION, "derivable", "—", ["marketing/sections/cta-sections"], []),
    E("Pricing section / table", COMPOSITION, "derivable", "—", ["marketing/sections/pricing"], []),
    E("Testimonial section", COMPOSITION, "derivable", "—", ["marketing/sections/testimonials"], []),
    E("Logo cloud", COMPOSITION, "derivable", "—", ["marketing/sections/logo-clouds"], []),
    E("Stats section", COMPOSITION, "derivable", "—", ["marketing/sections/stats-sections"], []),
    E("Team section", COMPOSITION, "derivable", "—", ["marketing/sections/team-sections"], []),
    E("Blog / article list section", COMPOSITION, "derivable", "—", ["marketing/sections/blog-sections"], []),
    E("Content / prose section", COMPOSITION, "derivable", "—", ["marketing/sections/content-sections"], []),
    E("Contact section", COMPOSITION, "derivable", "—", ["marketing/sections/contact-sections"], []),
    E("FAQ section", COMPOSITION, "derivable", "disclosure (depends on #142)",
      ["marketing/sections/faq-sections"], []),
    E("Newsletter section", COMPOSITION, "derivable", "—", ["marketing/sections/newsletter-sections"], []),
    E("Footer", COMPOSITION, "derivable", "—", ["marketing/sections/footers"], ["Footer"]),
    E("Marketing header", COMPOSITION, "derivable", "disclosure",
      ["marketing/elements/headers", "marketing/sections/header"], []),
    E("Mega menu / Flyout", COMPONENT, "needs doctrine #90", "disclosure + menu",
      ["marketing/elements/flyout-menus"], ["Mega Menu"]),
    E("Landing page archetype", ARCHETYPE, "documented", "—", ["marketing/page-examples/landing-pages"], []),
    E("Pricing page archetype", ARCHETYPE, "documented", "—", ["marketing/page-examples/pricing-pages"], []),
    E("About page archetype", ARCHETYPE, "documented", "—", ["marketing/page-examples/about-pages"], []),
    E("Error page archetype (404/500)", ARCHETYPE, "documented", "—", ["marketing/feedback/404-pages"], [],
      "an intentional error-page DESIGN — it returns 200 and is a legitimate page under test (qa-flow #106)"),
    E("Auth page archetype (sign-in / sign-up / reset)", ARCHETYPE, "documented", "—",
      ["application-ui/forms/sign-in-forms"], [],
      "uses the cover > center > stack recipe for true vertical centering, not bare center"),

    # ---- planned: #91 commerce family --------------------------------------------------
    E("Product list / grid", COMPONENT, "derivable", "—", ["ecommerce/components/product-lists"], []),
    E("Product overview", COMPOSITION, "derivable", "—", ["ecommerce/components/product-overviews"], []),
    E("Product features block", COMPOSITION, "derivable", "—", ["ecommerce/components/product-features"], []),
    E("Product quickview", COMPONENT, "derivable", "dialog", ["ecommerce/components/product-quickviews"], []),
    E("Category preview", COMPOSITION, "derivable", "—", ["ecommerce/components/category-previews"], []),
    E("Category filters", COMPONENT, "derivable", "disclosure (filter groups)",
      ["ecommerce/components/category-filters"], []),
    E("Store navigation", COMPONENT, "derivable", "disclosure", ["ecommerce/components/store-navigation"], []),
    E("Shopping cart", COMPOSITION, "derivable", "—", ["ecommerce/components/shopping-carts"], []),
    E("Checkout form", COMPOSITION, "derivable", "—", ["ecommerce/components/checkout-forms"], []),
    E("Order summary", COMPOSITION, "derivable", "—", ["ecommerce/components/order-summaries"], []),
    E("Order history", COMPOSITION, "derivable", "—", ["ecommerce/components/order-history"], []),
    E("Reviews + Rating", COMPONENT, "needs doctrine #91", "—", ["ecommerce/components/reviews"], ["Rating"],
      "Rating is only needed by commerce, which is why it sits here rather than in #95"),
    E("Incentives block", COMPOSITION, "derivable", "—", ["ecommerce/components/incentives"], []),
    E("Promo section", COMPOSITION, "derivable", "—", ["ecommerce/components/promo-sections"], []),
    E("Storefront page archetype", ARCHETYPE, "documented", "—", ["ecommerce/page-examples/storefront-pages"], []),
    E("Category page archetype", ARCHETYPE, "documented", "—", ["ecommerce/page-examples/category-pages"], []),
    E("Product page archetype", ARCHETYPE, "documented", "—", ["ecommerce/page-examples/product-pages"], []),
    E("Cart page archetype", ARCHETYPE, "documented", "—", ["ecommerce/page-examples/shopping-cart-pages"], []),
    E("Checkout page archetype", ARCHETYPE, "documented", "—", ["ecommerce/page-examples/checkout-pages"], []),
    E("Order detail page archetype", ARCHETYPE, "documented", "—",
      ["ecommerce/page-examples/order-detail-pages"], []),
    E("Order history page archetype", ARCHETYPE, "documented", "—",
      ["ecommerce/page-examples/order-history-pages"], []),

    # ---- deferred: revisitable, and each names WHAT WOULD FLIP IT -----------------------
    E("Calendar / Date picker / Time picker", COMPONENT, "documented", "—",
      ["application-ui/data-display/calendars"], ["Datepicker", "Timepicker"],
      note="native first: the `type` fallback to a TEXT input is a spec guarantee, and there is "
           "NO APG date-picker pattern — two examples, two valid architectures",
      build="`input[type=date|time]` via simple_form, plus Rails date helpers — styled with the "
              "shipped field anatomy so it matches everything else"),
    E("Image gallery / Lightbox", COMPONENT, "documented", "modal + carousel", [], ["Gallery"],
      note="focus trapping, keyboard paging and zoom are a large surface, and no current family "
           "has a media-heavy surface",
      build="`grid-auto` of `frame` thumbnails linking to the full image"),
    E("Speed dial / FAB cluster", COMPONENT, "derivable", "—", [], ["Speed Dial"],
      note="a floating action cluster competes with the shipped page-header actions slot, so "
           "adding it now would create two mechanisms for the same job",
      build="the page-header actions slot (Heading + Button group), or a Dropdown for overflow"),
    E("Device mockup", COMPONENT, "derivable", "—", [], ["Device Mockups"],
      note="decoration rather than structure, and #135 deliberately owns the visual-asset question",
      build="a `frame` at the screenshot's own ratio"),
    E("Chat bubble", COMPONENT, "derivable", "—", [], ["Chat Bubble"],
      note="a messaging thread is an application feature; the kit would be guessing at its "
           "semantics (grouping, read state, authorship) with no product to check against",
      build="Media object rows in a `divide-y` container — the same shape, without inventing "
              "message semantics"),

    # ---- declined: a design principle, not a threshold. No revisit trigger by design ----
    E("Carousel / Slider", COMPONENT, "documented", "carousel", [], ["Carousel"],
      note="content behind a timed or manual slide is content most users never see, and the "
           "pattern is a persistent a11y liability. This is a doctrine position, not a backlog "
           "item — if a client insists, build it in the app against the a11y contract rather than "
           "blessing it as a kit primitive",
      build="`grid-auto`, or a horizontal scroller with visible affordances and real focus order"),
    E("Bottom navigation", COMPONENT, "derivable", "—", [], ["Bottom Navigation"],
      note="not a gap: on native the platform tab bar IS our answer (mobile.md), and a web "
           "imitation would diverge from the OS behaviour users expect",
      build="the native tab bar on Hotwire Native; the shipped sidebar/stacked shells on web"),
    E("QR code", COMPONENT, "derivable", "—", [], ["QR Code"],
      note="generated server-side and rendered as an image — there is no visual contract to "
           "standardise beyond sizing, which the `frame` primitive already covers",
      build="generate in the app and render an `<img>` inside a `frame`"),
    E("Video player", COMPONENT, "needs doctrine #95", "—", [], ["Video"],
      note="a custom player is a large surface (captions, keyboard, fullscreen) that duplicates "
           "what the browser already ships and maintains",
      build="native `<video controls>` inside a `frame` for ratio"),
    E("Phone input", COMPONENT, "derivable", "—", [], ["Phone Input"],
      note="international formatting and validation depend on locale data and the app's own rules; "
           "a kit-level widget would encode assumptions the app has to override",
      build="a text input with `inputmode=tel` and app-side normalisation, using the shipped "
              "field anatomy"),
)

# Interaction patterns and layout primitives are enumerated separately: they have no
# one-to-one corpus directory, so a component matrix cannot express them.
INTERACTION_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("disclosure (collapse / accordion)", "planned #142",
     "the single largest gap found: 732 `data-collapse-toggle` instances across the Flowbite "
     "corpus and we shipped no controller at all"),
    ("dialog (modal / drawer)", "shipped", "focus trap, Escape, restore focus on close"),
    ("menu (dropdown)", "shipped", "roving tabindex, Escape, click-outside"),
    ("list-navigation (tabs / single-select groups)", "shipped", "arrow keys + Home/End"),
    ("dismissible (alert / toast)", "shipped", "removes the node, announces politely"),
    ("theme toggle (light / dark)", "shipped", "13 corpus pages carry one; ours is a role-token flip"),
    ("filter / typeahead", "planned #95", "needed by both command palette and combobox"),
    ("drag and drop (upload)", "planned #95", "needed by the file dropzone; keyboard path is mandatory"),
    ("carousel / slide", "declined", "see Carousel — a doctrine position, not a backlog item"),
)

LAYOUT_PRIMITIVES: tuple[tuple[str, str], ...] = (
    ("stack", "shipped"), ("cluster", "shipped"), ("center", "shipped"), ("box", "shipped"),
    ("grid-auto", "shipped"), ("frame", "shipped"), ("cover", "shipped"),
    ("Layout::Sidebar", "shipped"), ("Layout::Switcher", "shipped"),
    ("cover > center > stack (single-focus recipe)", "shipped"),
)


class BuildError(Exception):
    """The matrix cannot be generated correctly -- never emit a partial file."""


def discover_tw() -> set[str]:
    """Every leaf component directory in the Tailwind UI corpus, as family/group/component."""
    if not TW_ROOT.is_dir():
        raise BuildError(
            f"Tailwind UI corpus not found at {TW_ROOT}. This is maintainer tooling and the "
            "corpora are licensed, gitignored references (#89) — it cannot regenerate without "
            "them, and will not emit a hollow file instead."
        )
    found = set()
    for family in TW_FAMILIES:
        base = TW_ROOT / family
        if not base.is_dir():
            raise BuildError(f"expected corpus family missing: {base}")
        for group in sorted(p for p in base.iterdir() if p.is_dir()):
            for component in sorted(p for p in group.iterdir() if p.is_dir()):
                found.add(f"{family}/{group.name}/{component.name}")
    return found


def discover_fb() -> set[str]:
    return {name for names in FLOWBITE_CATALOG.values() for name in names}


# ---------------------------------------------------------------------------------------
# WHERE / WHEN to use each row. The kit is consulted on demand, so "how to build it" is only
# half an answer -- an agent that knows the anatomy but not the surface assembles screens out
# of the wrong parts. Every row must resolve to non-empty guidance; the guard enforces it.
#
# Defaults by (kind, corpus family) carry the rows whose answer really is the family answer,
# and USE overrides anything with a more specific home. This is deliberately not 113 bespoke
# strings: a default that is true is better than a unique string that is padding.
# ---------------------------------------------------------------------------------------
USE: dict[str, str] = {
    "Button": "any action; `primary` once per view, `destructive` only behind a confirm",
    "Button group": "2–5 related actions, or a single-select filter — `role=group` vs `radiogroup`",
    "Badge / Tag / Chip": "status and category labels inside table rows, list items and headings",
    "Avatar": "wherever a person is named; pair with the name, never alone as identification",
    "Dropdown / Menu": "overflow actions and scope pickers; not for navigation between pages",
    "Card": "a bounded surface in a dashboard grid, or a detail panel; also the stat-tile base",
    "Heading blocks (page / section / card)": "the top of every page, section and card — the "
        "scale prop picks the level, so never style a heading down",
    "Alert / Banner": "in-page state (Alert) vs page-wide announcement (Banner)",
    "Modal / Dialog": "a focused create/edit/confirm step; never for content a page can hold",
    "Toast / Notification": "transient confirmation of a completed action; never for errors "
        "requiring a decision",
    "Tooltip / Popover": "a supplementary label (Tooltip) or a small rich panel (Popover); never "
        "the only place information appears",
    "Table (CRUD)": "the index of a resource — sortable headers, row actions, select-all",
    "Description list": "read-only attribute/value pairs on a detail or settings screen",
    "Media object": "any avatar/icon + text row: list items, feeds, comments, notifications",
    "Pagination": "any index over ~25 rows; pair with the Table",
    "Empty state": "the zero-row branch of every index — required, not optional",
    "Breadcrumbs": "detail screens more than one level deep, inside the page heading block",
    "Navigation — header / navbar": "the app's top bar in the stacked shell",
    "Navigation — sidebar / vertical": "the app's primary rail in the sidebar/multi-column shells",
    "Tabs": "switching views of the SAME resource; never as page navigation",
    "Logo / Brand mark": "shell headers, auth screens and marketing surfaces",
    "Divider": "between unrelated blocks; inside a list use `divide-y` on the container instead",
    "List container (divide-y)": "any stacked list of rows — the container owns the separators",
    "Stat tile": "the metric row at the top of a dashboard, one metric per Card",
    "Prose / long-form type": "any body copy; the measure cap is what keeps it readable",
    "Frame (aspect-ratio media)": "every image or video, so layout never shifts on load",
    "Center / container": "the outer wrapper of page content, capping it at the measure",
    "Form layout": "every form — simple_form owns the field anatomy app-wide",
    "Text input": "single-line entry; the shipped wrapper supplies label, hint and error",
    "Select": "a closed set of ~2–10 options; above that reach for the combobox",
    "Textarea": "multi-line entry; set rows, never a fixed pixel height",
    "Checkbox": "independent booleans; multiples need a fieldset with a legend",
    "Radio group": "one choice from 2–5 visible options, in a fieldset",
    "Toggle / Switch": "a setting that applies immediately; if it needs Save, use a Checkbox",
    # Flowbite-only rows: no TW path, so the family default would guess "application-ui" and
    # tell an agent the wrong surface. Named explicitly instead.
    "Device mockup": "marketing surfaces only, to frame a product screenshot",
    "Chat bubble": "a messaging, comment or activity thread — not general app screens",
    "Bottom navigation": "native mobile shells (Hotwire Native); never as a web nav",
    "QR code": "wherever a code must be scanned — checkout, tickets, device pairing",
    "Video player": "marketing and docs surfaces; inside a `frame` so layout never shifts",
    "Carousel / Slider": "prefer not to — if a client insists, a marketing surface only",
    "Image gallery / Lightbox": "media-heavy surfaces: portfolio, product media, docs",
    "Speed dial / FAB cluster": "a mobile-first surface where the primary action must stay "
        "reachable while scrolling",
    "Phone input": "any form collecting a telephone number",
    "Keyboard key (KBD)": "docs and shortcut hints; the command palette needs it",
    "Spinner / busy indicator": "a region whose content is loading and has no known size",
    "Skeleton / loading placeholder": "a Turbo frame whose content size IS known — preferred "
        "over a spinner because it does not shift layout",
    "Stepper / wizard": "a multi-step flow: checkout, onboarding, long forms",
    "Copy to clipboard": "next to an API key, invite link or ID",
    "Inline link": "body copy and prose; for actions use the Button `link` variant",
    "Sidebar shell": "authenticated app screens with a persistent rail",
    "Stacked shell": "authenticated screens with few top-level areas, or marketing-adjacent app pages",
    "Multi-column shell": "screens needing a contextual aside beside the main region",
    "Home / dashboard anatomy": "the landing screen after sign-in",
    "Detail anatomy": "a single record with attributes and actions",
    "Settings anatomy": "grouped preference forms",
}

USE_DEFAULTS: dict[tuple[str, str], str] = {
    (COMPONENT, "marketing"): "a marketing surface (landing, pricing, about) — not app screens, "
        "which use the shell navigation",
    (COMPOSITION, "marketing"): "a section of a marketing page, stacked inside the landing / "
        "pricing / about anatomy",
    (ARCHETYPE, "marketing"): "a whole marketing or auth page; compose sections inside it",
    (COMPOSITION, "ecommerce"): "a block within a storefront, product, cart or checkout page",
    (ARCHETYPE, "ecommerce"): "a whole commerce page; compose the blocks inside it",
    (COMPONENT, "ecommerce"): "a commerce surface (catalog, product, cart, checkout)",
    (COMPONENT, "application-ui"): "an authenticated app screen, inside one of the three shells",
    (COMPOSITION, "application-ui"): "a region of an app screen, inside one of the three shells",
    (PRIMITIVE, "application-ui"): "anywhere; primitives are the layer everything else composes from",
    (ARCHETYPE, "application-ui"): "a whole app screen",
}


# ---------------------------------------------------------------------------------------
# HOW to build each row that has no reference entry of its own. For `derivable` rows this is
# the composition; for `needs doctrine` rows it is the nearest SAFE approach to use today,
# because "wait for the issue" is not an answer to a project that needs the thing now.
#
# A row's own `build=` kwarg wins; then BUILD; then a family default. The guard requires the
# result to be non-empty, so a row can never reach the file saying only "compose it yourself".
# ---------------------------------------------------------------------------------------
BUILD: dict[str, str] = {
    # derivable — the composition IS the guidance
    "Stacked list": "Media object rows inside a `divide-y` container",
    "Grid list": "`grid-auto` of Cards",
    "Activity feed / Timeline": "Media object rows in a `divide-y` container; the rail is a "
        "border on the container, not a pseudo-element per row",
    "Action panel": "Card + Heading (card scale) + Button group",
    "Search input": "the documented Text input, `type=search`, with a leading Lucide icon",
    "Number input": "the documented Text input with `inputmode=numeric`",
    "Status indicator / dot": "Badge, or a `size-2 rounded-full` span plus `sr-only` text — "
        "never colour alone",
    "Keyboard key (KBD)": "`<kbd>` with muted role tokens at `--text-step--1`",
    "Footer": "`center` > `cluster` of link lists + Logo",
    "Marketing header": "the documented navbar + Logo; mobile reuses the shell's disclosure",
    "Bottom navigation": "the native tab bar on Hotwire Native (mobile.md); on web, the shell nav",
    "QR code": "generate server-side, render an `<img>` inside a `frame`",
    "Phone input": "the documented Text input with `inputmode=tel`; normalise app-side",
    "Speed dial / FAB cluster": "the page-header actions slot (Heading + Button group), or a "
        "Dropdown for overflow",
    "Chat bubble": "Media object rows in a `divide-y` container",
    "Device mockup": "a `frame` at the screenshot's own ratio",
    "Product quickview": "the documented Modal with the product overview blocks inside",
    "Category filters": "`<details>`/`<summary>` groups inside a `stack`, until #142 lands",
    "Store navigation": "the documented navbar / sidebar navigation",
    # needs doctrine — the nearest safe thing to do TODAY
    "Inline link": "the Button `link` variant's classes on an `<a>`, until a token exists",
    # APG has no command-palette pattern (the Patterns index lists 30, none for it), so this is
    # a composition
    # of two documented parts rather than a gap. Keep aria-activedescendant: the input must
    # hold focus for typing to filter, so moving DOM focus into the results breaks it.
    "Command palette": "the documented Modal containing the documented Combobox with a "
        "listbox popup; keep `aria-activedescendant` so typing keeps filtering",
    "Stepper / wizard": "a `cluster` of Badges with `aria-current=step`",
    "Mega menu / Flyout": "the documented Dropdown for now; hover-intent is what #90 must specify",
    "Reviews + Rating": "Media object rows; the rating needs an accessible name (\"4 out of 5\"), "
        "not stars alone",
    "Video player": "native `<video controls>` inside a `frame`",
}

BUILD_DEFAULTS: dict[tuple[str, str], str] = {
    (COMPOSITION, "marketing"): "`center` > `stack` of Heading + prose + `grid-auto`/`Switcher`, "
        "Buttons for CTAs — no bespoke section CSS",
    (ARCHETYPE, "marketing"): "the marketing header + stacked sections inside `center`; "
        "`cover > center > stack` for a single-focus page",
    (COMPOSITION, "ecommerce"): "Card + Heading + Description list / Table inside `grid-auto` "
        "or `Switcher`",
    (ARCHETYPE, "ecommerce"): "a stacked-shell page: Heading block, then the commerce blocks in "
        "`grid-auto`",
    (COMPONENT, "ecommerce"): "Card + Badge + Button group; prices on the fluid type scale",
    (ARCHETYPE, "application-ui"): "one of the three shells plus the documented anatomy regions",
}


def _family(entry: Entry) -> str:
    """Which corpus family a row belongs to -- used only to pick a default `use`."""
    for ref in entry.tw:
        return ref.split("/", 1)[0]
    return "application-ui"


def resolve_use(entry: Entry) -> str:
    if entry.name in USE:
        return USE[entry.name]
    return USE_DEFAULTS.get((entry.kind, _family(entry)), "")


def resolve_build(entry: Entry) -> str:
    if entry.build.strip():
        return entry.build
    if entry.name in BUILD:
        return BUILD[entry.name]
    return BUILD_DEFAULTS.get((entry.kind, _family(entry)), "")


def reference_blob() -> str:
    """Every shipped fidara-design reference doc, concatenated — the evidence corpus."""
    refs = OUT.parent
    if not refs.is_dir():
        return ""
    return "\n".join(
        p.read_text(encoding="utf-8") for p in sorted(refs.glob("*.md")) if p.name != OUT.name
    )


def verify_shipped_evidence() -> list[str]:
    """A `shipped` row must cite a string that really occurs in the shipped docs."""
    problems: list[str] = []
    blob = reference_blob()
    if not blob:
        return [f"cannot read the reference docs at {OUT.parent} to verify `shipped` claims"]

    for entry in ENTRIES:
        evidence = DOCUMENTED_EVIDENCE.get(entry.name, "")
        if entry.is_documented:
            if not evidence.strip():
                problems.append(
                    f"{entry.name!r} claims `documented` with no entry in DOCUMENTED_EVIDENCE — the one "
                    "column readers act on must be checkable, not asserted"
                )
            elif evidence not in blob:
                problems.append(
                    f"{entry.name!r} claims `documented`, but its evidence {evidence!r} does not "
                    "appear in any reference doc — either it is not shipped, or the doc moved"
                )
        elif evidence:
            problems.append(
                f"{entry.name!r} is {entry.status!r} but has a DOCUMENTED_EVIDENCE entry — only "
                "shipped rows cite doc evidence"
            )

    # A `documented` row must not still carry a BUILD fallback. BUILD is "the nearest safe thing
    # to do until the entry lands"; once it HAS landed, that text tells readers to go build the
    # workaround instead of using the doctrine. It is invisible in the rendered table (documented
    # rows print `—` in that column), so nothing surfaces it — the Combobox entry survived its own
    # row's promotion this way, still saying "use the documented Select until the entry lands"
    # after the Combobox entry had shipped (#95).
    stale = sorted(set(BUILD) & {e.name for e in ENTRIES if e.is_documented})
    if stale:
        problems.append(
            f"`documented` rows still carrying a BUILD fallback: {stale} — that text says 'use the "
            "workaround until the entry lands' about an entry that HAS landed, and it is invisible "
            "in the rendered table, so delete it with the promotion"
        )

    orphans = sorted(set(DOCUMENTED_EVIDENCE) - {e.name for e in ENTRIES})
    if orphans:
        problems.append(f"DOCUMENTED_EVIDENCE keys matching no row (renamed?): {orphans}")

    return problems


def verify_totality(tw_found: set[str], fb_found: set[str]) -> None:
    """Every discovered corpus entry is claimed exactly once; nothing claims a ghost.

    This is the guarantee that makes the matrix a completeness check rather than a list.
    Duplicate claims are checked explicitly because a dict/set would merge them silently.
    """
    problems: list[str] = []

    for label, found, picker in (("Tailwind UI", tw_found, lambda e: e.tw), ("Flowbite", fb_found, lambda e: e.fb)):
        claims: dict[str, list[str]] = {}
        for entry in ENTRIES:
            for ref in picker(entry):
                claims.setdefault(ref, []).append(entry.name)

        for ref, owners in sorted(claims.items()):
            if len(owners) > 1:
                problems.append(f"{label} {ref!r} is claimed by {len(owners)} rows: {owners}")

        unclaimed = sorted(found - set(claims))
        if unclaimed:
            problems.append(
                f"{len(unclaimed)} {label} entr{'y' if len(unclaimed) == 1 else 'ies'} not "
                f"classified in ENTRIES — classify each, including as explicit out-of-scope "
                f"WITH A REASON: {unclaimed}"
            )

        ghosts = sorted(set(claims) - found)
        if ghosts:
            problems.append(
                f"{len(ghosts)} {label} reference(s) in ENTRIES do not exist in the corpus "
                f"(renamed or removed upstream?): {ghosts}"
            )

    for entry in ENTRIES:
        # .strip() throughout: whitespace is not guidance. Without it, `build="  "` satisfies
        # the rule and the row reads as actionable while saying nothing.
        if not entry.status.strip():
            problems.append(f"{entry.name!r} has no guidance level")
        elif not any(
            entry.status.startswith(p) for p in ("documented", "derivable", "needs doctrine")
        ):
            problems.append(
                f"{entry.name!r} has guidance {entry.status!r}, which is not one of documented / "
                "derivable / needs doctrine #N. (`deferred` and `declined` were retired: the kit "
                "documents how to build things on demand, it does not withhold them.)"
            )

        if entry.is_derivable and not resolve_build(entry).strip():
            problems.append(
                f"{entry.name!r} is derivable but does not say what to build it FROM — 'compose it "
                "yourself' is not guidance, it is where invented markup comes from"
            )
        if entry.needs_doctrine:
            if not any(ch.isdigit() for ch in entry.status):
                problems.append(
                    f"{entry.name!r} needs doctrine but names no issue — an untracked gap is a gap "
                    "nobody is going to close"
                )
            if not resolve_build(entry).strip():
                problems.append(
                    f"{entry.name!r} needs doctrine but offers no nearest-guidance fallback — an "
                    "agent asked for this today must still be told the closest safe thing to do"
                )
        if not resolve_use(entry).strip():
            problems.append(
                f"{entry.name!r} has no WHERE/WHEN guidance — knowing how to build a component "
                "without knowing where it belongs is how screens get assembled from the wrong parts"
            )

    names = [e.name for e in ENTRIES]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        problems.append(f"duplicate canonical names in ENTRIES: {dupes}")

    problems.extend(verify_shipped_evidence())

    if problems:
        raise BuildError("\n".join(f"  - {p}" for p in problems))


def _mark(value: bool) -> str:
    return "✓" if value else "—"


def render(tw_found: set[str], fb_found: set[str]) -> str:
    documented = [e for e in ENTRIES if e.is_documented]
    derivable = [e for e in ENTRIES if e.is_derivable]
    needs = [e for e in ENTRIES if e.needs_doctrine]

    lines: list[str] = []
    add = lines.append

    add("# Component coverage — what to build, and where to use it")
    add("")
    add("**Generated — do not hand-edit.** `python3 scripts/build_coverage.py` rebuilds this from a")
    add("mechanical enumeration of the reference corpora; `--check` fails if it is stale.")
    add("")
    add("Components are built **just-in-time, in the project**, when a screen needs one — they are")
    add("never batch-built here. So this file is not a build queue and not an availability list.")
    add("Nothing is withheld: **every row below is buildable on demand.** What differs is how much")
    add("the doctrine already tells you, and that is the only axis here.")
    add("")
    add("## How to read a row")
    add("")
    add("| Guidance | Means | What you get |")
    add("|---|---|---|")
    add("| `documented` | a reference doc defines its anatomy | build it straight from that entry |")
    add("| `derivable` | no dedicated entry needed | the **Build from** column names the documented parts it composes from |")
    add("| `needs doctrine #N` | an agent would have to invent an a11y or interaction contract | **Build from** still gives the nearest safe approach; `#N` tracks writing the real entry |")
    add("")
    add("`needs doctrine` is the only one that marks a genuine gap, and it is a gap in *writing*, not")
    add("in *capability* — you can still build the thing today, you just carry more risk of getting")
    add("the keyboard or ARIA contract wrong, which is exactly why it is tracked.")
    add("")
    add("Every row also carries **Where / when to use it**. Knowing how to build a component without")
    add("knowing which surface it belongs on is how screens get assembled from the wrong parts, so the")
    add("builder refuses to emit a row that lacks it.")
    add("")
    add("## Totals")
    add("")
    add("| | count |")
    add("|---|---|")
    add(f"| Tailwind UI leaf components enumerated | {len(tw_found)} |")
    add(f"| Flowbite catalogue entries enumerated | {len(fb_found)} |")
    add(f"| fidara rows | {len(ENTRIES)} |")
    add(f"| — `documented` | {len(documented)} |")
    add(f"| — `derivable` from documented parts | {len(derivable)} |")
    add(f"| — `needs doctrine` (tracked writing gap) | {len(needs)} |")
    add("")
    add("`Kind` is `primitive` · `component` · `composition` · `page archetype`. `In TW` / `In FB`")
    add("show which corpus carries the pattern — useful because the two are good at different things:")
    add("Tailwind UI wins on visual polish, Flowbite on interaction breadth.")
    add("")

    add("## Documented — build straight from the reference entry")
    add("")
    add("| Component | Kind | In TW | In FB | Where / when to use it | Watch out for |")
    add("|---|---|---|---|---|---|")
    for e in sorted(documented, key=lambda x: (x.kind, x.name)):
        add(
            f"| {e.name} | {e.kind} | {_mark(bool(e.tw))} | {_mark(bool(e.fb))} | "
            f"{resolve_use(e)} | {e.note or '—'} |"
        )
    add("")

    add("## Derivable — compose it from documented parts")
    add("")
    add("No dedicated catalogue entry, and none needed: these are compositions. Build from what the")
    add("**Build from** column names rather than inventing markup — that is what keeps a JIT-built")
    add("screen consistent with everything already in the app.")
    add("")
    add("| Component | Kind | In TW | In FB | Build from | Where / when to use it |")
    add("|---|---|---|---|---|---|")
    for e in sorted(derivable, key=lambda x: (x.kind, x.name)):
        add(
            f"| {e.name} | {e.kind} | {_mark(bool(e.tw))} | {_mark(bool(e.fb))} | "
            f"{resolve_build(e)} | {resolve_use(e)} |"
        )
    add("")

    add("## Needs doctrine — buildable today, but you are carrying the risk")
    add("")
    add("These need an a11y or interaction contract the docs do not yet state (a keyboard model, an")
    add("ARIA pattern, a reduced-motion rule). **Build them when a project needs them** — the")
    add("**Nearest guidance** column is the safest current approach — and expect the tracked issue to")
    add("replace that approach with a proper entry.")
    add("")
    add("| Component | Kind | In TW | In FB | Tracked | Nearest guidance | Where / when to use it |")
    add("|---|---|---|---|---|---|---|")
    for e in sorted(needs, key=lambda x: (x.kind, x.name)):
        issue = e.status.replace("needs doctrine", "").strip() or "—"
        add(
            f"| {e.name} | {e.kind} | {_mark(bool(e.tw))} | {_mark(bool(e.fb))} | {issue} | "
            f"{resolve_build(e)} | {resolve_use(e)} |"
        )
    add("")

    add("## Interaction patterns")
    add("")
    add("Enumerated separately because they do not map one-to-one onto a corpus directory —")
    add("Flowbite's `data-*` trigger attributes are the better source, and they cut across components.")
    add("")
    add("| Pattern | Status | Note |")
    add("|---|---|---|")
    for name, status, note in INTERACTION_PATTERNS:
        add(f"| {name} | {status} | {note} |")
    add("")

    add("## Layout primitives")
    add("")
    add("| Primitive | Status |")
    add("|---|---|")
    for name, status in LAYOUT_PRIMITIVES:
        add(f"| `{name}` | {status} |")
    add("")

    add("## How to re-run this")
    add("")
    add("```bash")
    add("python3 scripts/build_coverage.py           # regenerate")
    add("python3 scripts/build_coverage.py --check   # CI-style staleness check")
    add("python3 scripts/build_coverage.py --audit   # what is unclassified right now")
    add("```")
    add("")
    add("The corpora are **licensed references** (#89): gitignored, studied locally, never")
    add("redistributed. Only names, statuses and our own prose reach this file — no markup, class")
    add("list or asset is copied. Without the local corpora the builder **refuses to run** rather")
    add("than emitting a file that looks complete.")
    add("")
    add("When a corpus is updated, re-run it. A new upstream directory that nobody has classified")
    add("**fails the build** and names itself, so coverage cannot silently rot. That failure is the")
    add("feature: it is the only reason this file can be trusted as a completeness claim.")
    add("")
    add("Sources: Tailwind UI corpus directories; Flowbite catalogue read from")
    add("<https://flowbite.com/docs/> (Components, Forms, Typography) on 2026-07-29. Two names often")
    add("attributed to Flowbite are **not** in its catalogue and are deliberately absent here:")
    add("`Separator` (theirs is `HR`) and a cookie-consent component (none exists).")
    return "\n".join(lines) + "\n"


def build() -> str:
    tw, fb = discover_tw(), discover_fb()
    verify_totality(tw, fb)
    return render(tw, fb)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the fidara component coverage matrix.")
    parser.add_argument("--check", action="store_true", help="fail if the committed file is stale")
    parser.add_argument("--audit", action="store_true", help="list unclassified corpus entries and exit")
    parser.add_argument("--selftest", action="store_true", help="prove the guards fire and stay silent")
    args = parser.parse_args(argv)

    if args.selftest:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import build_coverage_selftest as st

        return st.run()

    if args.audit:
        try:
            tw, fb = discover_tw(), discover_fb()
            verify_totality(tw, fb)
        except BuildError as exc:
            print(f"UNCLASSIFIED / INCONSISTENT:\n{exc}", file=sys.stderr)
            return 1
        print(f"all {len(tw)} Tailwind UI and {len(fb)} Flowbite entries are classified")
        return 0

    try:
        rendered = build()
    except BuildError as exc:
        print(f"BUILD FAILED:\n{exc}", file=sys.stderr)
        return 2

    if args.check:
        if not OUT.is_file():
            print(f"{OUT} does not exist — run without --check to generate it", file=sys.stderr)
            return 1
        current = OUT.read_text(encoding="utf-8")
        if current != rendered:
            print(
                f"{OUT.relative_to(REPO)} is STALE — regenerate with "
                "`python3 scripts/build_coverage.py`",
                file=sys.stderr,
            )
            diff = subprocess.run(
                ["git", "--no-pager", "diff", "--no-index", "--stat", "-", str(OUT)],
                input=rendered, text=True, capture_output=True, cwd=REPO,
            )
            if diff.stdout.strip():
                print(diff.stdout.strip(), file=sys.stderr)
            return 1
        print(f"{OUT.relative_to(REPO)} is current")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} — {len(ENTRIES)} rows from {len(discover_tw())} TW + {len(discover_fb())} FB entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
