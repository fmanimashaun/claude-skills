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
import re
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
# The catalogue proper: the two files that hold per-component entries. `verify_no_undeclared_
# entry` reads THESE and not the whole blob, because the sentence it enforces is the Derivable
# table's own "No dedicated CATALOGUE entry".
#
# forms.md is in the list because half the form controls are catalogued there and nowhere else
# -- `## Range input (#95)`, `## Copy to clipboard (#95)`, `## Calendar / Date picker / Time
# picker (#95)` -- so a components.md-only guard would have a hole exactly the size of the
# forms family. (Checking components.md alone also made a near-miss fixture VACUOUS: it named
# `## Range input (#95)` as the prefix hazard, and that heading is in forms.md, so the fixture
# passed by finding nothing. The mutation harness caught it.)
#
# page-anatomies.md is deliberately NOT here. It catalogues page archetypes, not components,
# and its `## Order history` belongs to the `Order history page archetype` row -- including it
# would convict the separate `Order history` composition row, which is correct as it stands.
CATALOGUE_FILES = ("components.md", "forms.md")

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
    # #91 shipped the anatomy as "## Checkout — the purchase flow"; the evidence is the
    # heading PREFIX so a descriptive suffix does not falsify a row that is genuinely there.
    "Checkout page archetype": "## Checkout",
    "Order detail page archetype": "## Order detail\n",
    "Order history page archetype": "## Order history\n",
    # catalogue components (components.md)
    "Button": "## Button\n",
    "Button group": "## Button group\n",
    # Trailing newline anchors the exact heading: "## Disclosure" alone would also match a longer
    # heading, which is how a missing entry could pass (see the Button/Button-group note above).
    "Accordion / Disclosure": "## Disclosure / Accordion\n",
    "Combobox / Autocomplete": "## Combobox / Autocomplete\n",
    # `derivable` said "no dedicated catalogue entry, and none needed" while components.md had
    # carried `## Command palette` since #95 -- see `verify_no_undeclared_entry` for why nothing
    # could catch that, and #89 for the promotion.
    "Command palette": "## Command palette\n",
    "Progress bar": "## Progress bar\n",
    "Stepper / wizard": "## Stepper / wizard\n",
    "Mega menu / Flyout": "## Mega menu / Flyout\n",
    "File upload / Dropzone": "## File upload / Dropzone (#95)\n",
    "Copy to clipboard": "## Copy to clipboard (#95)\n",
    "Range input": "## Range input (#95)\n",
    "Calendar / Date picker / Time picker": "## Calendar / Date picker / Time picker (#95)\n",
    "Drawer / off-canvas": "## Drawer / off-canvas\n",
    "Carousel / Slider": "## Carousel\n",
    "Image gallery / Lightbox": "## Image gallery / Lightbox\n",
    "Video player": "## Video player\n",
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
    # #95's Lists group shipped these three as their own sections rather than as compositions
    # named only in the `Build from` column. Trailing newline for the same reason as Disclosure
    # below: "## Stacked list" alone would also match a longer heading.
    "Stacked list": "## Stacked list\n",
    "Grid list": "## Grid list\n",
    "Activity feed / Timeline": "## Activity feed / Timeline\n",
    "Description list": "## Description list\n",
    "Media object": "## Media object\n",
    "Reviews + Rating": "## Reviews + Rating\n",
    "Pagination": "## Pagination\n",
    "Empty state": "## Empty state\n",
    "Breadcrumbs": "## Breadcrumbs\n",
    # #95 shipped these as two SEPARATE sections rather than the one combined heading this
    # table assumed, so each row now points at its own real heading. Sharing one evidence
    # string across two rows also meant either row could be credited by the other's doc.
    "Navigation — header / navbar": "## Navigation — app header / navbar",
    "Navigation — sidebar / vertical": "## Navigation — sidebar / vertical",
    "Tabs": "## Tabs",
    "Logo / Brand mark": "## Logo / Brand mark",
    "Divider": "## Divider\n",
    "Inline link": "## Inline link\n",
    # primitives + compositions
    "List container (divide-y)": "divide-y divide-border",
    "Stat tile": "stat cards",
    "Prose / long-form type": "--text-step",
    "Frame (aspect-ratio media)": "@utility frame",
    "Center / container": "@utility center",
    # form controls.
    #
    # These five used to point at two shared headings -- Select+Textarea at `### Field anatomy`,
    # and Checkbox+Radio+Switch at `### Checkbox / Radio / Switch` -- which is the defect the
    # Navigation note above records, unfixed in the larger half of the table (#95). Two things
    # were wrong with it. Either row could be credited by the other's doc, so deleting the switch
    # recipe left `Toggle / Switch` passing on the checkbox's markup; and worse, `### Field
    # anatomy` is the simple_form WRAPPER, which is generic to every field and says nothing about
    # a select or a textarea at all -- both rows were `documented` on the strength of a section
    # that would still be there after every trace of either control was deleted.
    #
    # So each now points at the text that states THAT control's own recipe, which for four of the
    # five is a bullet in forms.md's `## Controls` -- the catalogue of form controls, one bullet
    # per control. Non-heading evidence is the established shape for rows whose doctrine is a
    # recipe rather than a section (see `divide-y divide-border`, `@utility frame` above), not a
    # weakening of it: a shorter, control-specific string is harder to satisfy by accident than a
    # heading, not easier. `verify_shipped_evidence` now refuses a reused string outright.
    "Form layout": "## Forms",
    "Text input": "### Input recipe (helper)",
    "Select": "**select** — native first, styled to match",
    "Textarea": "textarea `min-h-[…]`, no fixed height",
    # Checkbox and radio genuinely share one bullet and one ERB block, because radio is written as
    # a one-word delta from the checkbox (`rounded-full`). Splitting the DOC to give the table a
    # heading each would be the tail wagging the dog, so the two rows point at the checkbox-only
    # and radio-only fragments of the shared text instead.
    "Checkbox": "check_box_tag",
    "Radio group": "(radio `rounded-full`)",
    "Toggle / Switch": "**switch/toggle** — `Ui::Switch`",
    # #91 slice 2. Trailing newline where a shorter heading would otherwise prefix-match.
    "Plan comparison / feature matrix": "## Plan comparison / feature matrix\n",
    "Number input":                     "## Seat / quantity selector\n",
    "Saved payment methods":            "## Saved payment methods\n",
    "Subscription state and dunning":   "## Subscription state and dunning\n",
    "Plans page archetype":             "## Plans — compare and switch\n",
    "Billing page archetype":           "## Billing\n",
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
    E("Inline link", PRIMITIVE, "documented", "—", [], ["Links"],
      "the Button `link` variant is NOT this — it has no underline at rest, and dark-mode "
      "`--primary` is 2.59:1 against body text, under G183's 3:1, so colour cannot carry it. The "
      "3:1 figure is technique G183, not SC 1.4.1 itself; 2.5.8 exempts links inside a sentence"),
    E("Frame (aspect-ratio media)", PRIMITIVE, "documented", "—", [], ["Images"]),
    E("Center / container", PRIMITIVE, "documented", "—", ["application-ui/layout/containers"], []),

    # ---- shipped form controls ---------------------------------------------------------
    E("Form layout", COMPONENT, "documented", "—", ["application-ui/forms/form-layouts"], [],
      "simple_form owns every form; the wrapper anatomy is defined once in an initializer"),
    E("Text input", COMPONENT, "documented", "—", ["application-ui/forms/input-groups"],
      ["Input Field", "Floating Label"],
      "floating label AND prefix/suffix addons are variants, not components — the input-groups "
      "corpus directory is claimed here on purpose (#95)"),
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
    E("Stacked list", COMPONENT, "documented", "—",
      ["application-ui/lists/stacked-lists"], ["List Group"],
      "role=list is not optional decoration: Preflight unstyles every list and WebKit then drops "
      "the role. One stretched link per row, or none"),
    E("Grid list", COMPOSITION, "documented", "—", ["application-ui/lists/grid-lists"], [],
      "`grid-auto` on the <ul> is safe; role=grid is NOT — APG's Grid is a composite widget with "
      "roving tabindex, which a wall of cards does not have"),
    E("Activity feed / Timeline", COMPONENT, "documented", "—",
      ["application-ui/lists/feeds"], ["Timeline"],
      "TWO shapes: a static history is an ordinary <ol>, and only scroll-loading content earns "
      "APG's feed pattern — which is a structure, not a widget"),
    E("Progress bar", COMPONENT, "documented", "—",
      ["application-ui/navigation/progress-bars"], ["Progress"],
      "the Flowbite audit surfaced LABELLED progress bars specifically"),
    E("Command palette", COMPONENT, "documented", "new controller (filter + list-navigation)",
      ["application-ui/navigation/command-palettes"], [],
      "a composition WITH its own catalogue entry — Modal shell + editable Combobox, results as a "
      "listbox or grid popup. No APG pattern covers it (the index lists 30 and none is a command "
      "palette), so the shape is ours; `aria-haspopup=\"grid\"` is required only if the rows carry "
      "icon + label + shortcut"),
    E("Combobox / Autocomplete", COMPONENT, "documented", "new controller (filter + list-navigation)",
      ["application-ui/forms/comboboxes"], []),
    E("Action panel", COMPONENT, "derivable", "—", ["application-ui/forms/action-panels"], []),
    E("File upload / Dropzone", COMPONENT, "documented", "new controller (drag + drop)", [],
      ["File Input"], "the native input stays VISIBLE — hiding it behind the dropzone fails WCAG 2.5.7"),
    E("Search input", COMPONENT, "derivable", "—", [], ["Search Input"]),
    # #91 slice 2 shipped `## Seat / quantity selector`, so this FLIPS to documented rather than
    # gaining a competing row: Flowbite's `Number Input` is already claimed here and the totality
    # guard allows exactly one claimant.
    E("Number input", COMPONENT, "documented", "—", [], ["Number Input"]),
    # #91 slice 2 — plans/pricing and billing. No corpus directory maps to any of these, so the
    # upstream columns stay empty; they are ours, not a classification of someone else's kit.
    E("Plan comparison / feature matrix", COMPONENT, "documented", "—", [], []),
    E("Saved payment methods", COMPOSITION, "documented", "—", [], []),
    E("Subscription state and dunning", COMPOSITION, "documented", "—", [], []),
    E("Plans page archetype", ARCHETYPE, "documented", "—", [], []),
    E("Billing page archetype", ARCHETYPE, "documented", "—", [], []),
    E("Range input", COMPONENT, "documented", "—", [], ["Range"],
      "native `input type=range` already IS role=slider; custom only for two thumbs"),
    E("Status indicator / dot", COMPONENT, "derivable", "—", [], ["Indicators"],
      "surfaced by the audit as nav count badge + status badge inside table rows"),
    E("Skeleton / loading placeholder", COMPONENT, "documented", "—", [], ["Skeleton"],
      "Turbo frame loading states need this; without it agents invent spinners"),
    E("Spinner / busy indicator", COMPONENT, "documented", "—", [], ["Spinner"]),
    E("Stepper / wizard", COMPONENT, "documented", "—", [], ["Stepper"],
      "a display, not a widget: no tablist, no progressbar, no arrow keys. Move focus on advance and "
      "then do NOT add a live region — 4.1.3 excludes what a change of context already announced. "
      "Also feeds #91's checkout flow, which is inside 3.3.4 (AA)"),
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
    E("Mega menu / Flyout", COMPONENT, "documented", "disclosure + dismissable",
      ["marketing/elements/flyout-menus"], ["Mega Menu"],
      "a DISCLOSURE, not a menu — APG advises against role=menu for site nav, so it shares no ARIA "
      "with the Dropdown row"),
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
    E("Reviews + Rating", COMPONENT, "documented", "—", ["ecommerce/components/reviews"], ["Rating"],
      "the governing criterion is 1.1.1 (A), NOT 1.4.1 — filled-vs-empty stars differ in shape, so "
      "1.4.1 bites only where hue alone carries the distinction; read-only average and interactive "
      "picker are different contracts"),
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

    # ---- once deferred, now documented --------------------------------------------------
    E("Calendar / Date picker / Time picker", COMPONENT, "documented", "—",
      ["application-ui/data-display/calendars"], ["Datepicker", "Timepicker"],
      note="native first: the `type` fallback to a TEXT input is a spec guarantee, and there is "
           "NO APG date-picker pattern — two examples, two valid architectures"),
    E("Image gallery / Lightbox", COMPONENT, "documented", "modal + carousel", [], ["Gallery"],
      note="focus trapping, keyboard paging and zoom are a large surface, and no current family "
           "has a media-heavy surface"),
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

    # ---- a design principle, not a threshold. Documented so it can be built correctly ----
    E("Carousel / Slider", COMPONENT, "documented", "carousel", [], ["Carousel"],
      note="content behind a timed or manual slide is content most users never see, and the "
           "pattern is a persistent a11y liability. This is a doctrine position, not a backlog "
           "item — if a client insists, build it in the app against the a11y contract rather than "
           "blessing it as a kit primitive"),
    E("Bottom navigation", COMPONENT, "derivable", "—", [], ["Bottom Navigation"],
      note="not a gap: on native the platform tab bar IS our answer (mobile.md), and a web "
           "imitation would diverge from the OS behaviour users expect",
      build="the native tab bar on Hotwire Native; the shipped sidebar/stacked shells on web"),
    E("QR code", COMPONENT, "derivable", "—", [], ["QR Code"],
      note="generated server-side and rendered as an image — there is no visual contract to "
           "standardise beyond sizing, which the `frame` primitive already covers",
      build="generate in the app and render an `<img>` inside a `frame`"),
    E("Video player", COMPONENT, "documented", "—", [], ["Video"],
      note="no APG pattern, so the keyboard model is the UA's and not ours; `kind=captions` is not "
           "`kind=subtitles`; and an autoplaying video is governed by WCAG 2.2.2 (A), not by "
           "reduced-motion"),
    E("Phone input", COMPONENT, "derivable", "—", [], ["Phone Input"],
      note="international formatting and validation depend on locale data and the app's own rules; "
           "a kit-level widget would encode assumptions the app has to override",
      build="a text input with `inputmode=tel` and app-side normalisation, using the shipped "
              "field anatomy"),
)

# Interaction patterns and layout primitives are enumerated separately: they have no
# one-to-one corpus directory, so a component matrix cannot express them.
#
# The fourth element is a PROBE: a literal string that occurs in the shipped reference docs if
# and only if this pattern's contract has been written. `verify_interaction_claims` enforces
# `shipped` <=> probe present, in BOTH directions, which is the same principle
# `verify_shipped_evidence` already applies to component rows.
#
# It is here because the half without the guard rotted, silently, while the guarded half stayed
# honest: four of these nine rows were still `planned #142` / `planned #95` / `declined` after the
# contracts had shipped, and one of them ("keyboard path is mandatory" for the dropzone) had
# become the OPPOSITE of the doctrine it summarised -- forms.md quotes 2.5.7's Understanding
# document saying a keyboard equivalent does NOT satisfy the criterion on its own. A status
# column readers act on must be checkable, not asserted.
INTERACTION_PATTERNS: tuple[tuple[str, str, str, str], ...] = (
    ("disclosure (collapse / accordion)", "shipped",
     "the largest gap the corpus audit found — 732 `data-collapse-toggle` instances — and now the "
     "most fully specified pattern we ship: two modes, and the APG-required rules stated apart "
     "from the ones that are ours (#142)",
     "### Disclosure — the full contract (#142)"),
    ("dialog (modal / drawer)", "shipped", "focus trap, Escape, restore focus on close",
     "**focus-trap + restore**"),
    ("menu (dropdown)", "shipped", "roving tabindex, Escape, click-outside",
     "## Dropdown / Menu"),
    ("list-navigation (tabs / single-select groups)", "shipped", "arrow keys + Home/End",
     "**list-navigation** (roving tabindex)"),
    ("dismissible (alert / toast)", "shipped", "removes the node, announces politely",
     "## Toast / Notification"),
    ("theme toggle (light / dark)", "shipped", "13 corpus pages carry one; ours is a role-token flip",
     "`theme` (dark toggle + localStorage)"),
    ("filter / typeahead", "shipped",
     "TWO mechanisms, not one: filtering is `aria-autocomplete` (`list` or `both`) on an editable "
     "combobox, and typeahead-jump belongs to the SELECT-ONLY combobox and the menu. Applying the "
     "typeahead half to an editable combobox swallows the space bar (#229)",
     "**`aria-autocomplete`** is required"),
    ("drag and drop (upload)", "shipped",
     "`preventDefault()` on `dragover` or the drop never fires; and the clickable native input — "
     "not a keyboard path — is what satisfies WCAG 2.5.7, so it stays visible",
     "## File upload / Dropzone (#95)"),
    ("carousel / slide", "shipped",
     "the contract is written and the Lightbox composes it, but the default answer is still no — "
     "see the Carousel row for why. `declined` was the wrong word for that: it read as though the "
     "mechanism did not exist",
     "Behavior: the `carousel` controller."),
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
    "Stacked list": "any index of records that is not tabular, and the Table's mobile fallback",
    "Grid list": "an index whose items carry media or several attributes worth scanning at once",
    "Activity feed / Timeline": "a record's history, or a stream that loads more as you scroll",
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
    #
    # Stacked list, Grid list and Activity feed used to live here. #95's Lists group gave each one
    # its own `components.md` entry, so they are `documented` now and MUST NOT keep a fallback:
    # the BUILD-fallback guard below refuses one, because a promoted row that still says "compose
    # it yourself" sends readers past the doctrine that just landed.
    "Action panel": "Card + Heading (card scale) + Button group",
    "Search input": "the documented Text input, `type=search`, with a leading Lucide icon",
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
    # Was "Media object rows in a `divide-y` container" — the Stacked list's composition, spelled
    # out again, and it went stale the moment that row was promoted. Point at the doctrine.
    "Chat bubble": "the documented Stacked list, without inventing message semantics",
    "Device mockup": "a `frame` at the screenshot's own ratio",
    "Product quickview": "the documented Modal with the product overview blocks inside",
    # Was "`<details>`/`<summary>` groups inside a `stack`, until #142 lands" — a workaround
    # pointer that outlived its workaround. #142 shipped `Ui::Disclosure` and the full contract,
    # so this cell was telling agents to go build the cheap substitute instead of using the
    # doctrine. Same defect as the BUILD-fallback guard catches on `documented` rows; this row is
    # `derivable`, so nothing was watching it.
    "Category filters": "the documented `Ui::Disclosure`, one per filter group, inside a `stack` — "
        "`<details>`/`<summary>` only where the group never animates",
    "Store navigation": "the documented navbar / sidebar navigation",
    # The `Command palette` fallback lived here, with a comment arguing it was "a composition of
    # two documented parts rather than a gap". True, and beside the point: components.md had
    # carried `## Command palette` since #95, so the row was `documented` and this fallback was
    # the stale-BUILD text the guard above exists to refuse — invisible, because that guard only
    # inspects rows already marked `documented` (#89).
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


def verify_evidence_is_not_shared() -> list[str]:
    """No two `documented` rows may be vouched for by the same piece of doc.

    `verify_interaction_claims` has refused a reused probe since it was written -- *"one doc cannot
    be evidence for two different mechanisms"* -- and the same rule was never applied to
    DOCUMENTED_EVIDENCE, which is the table that decides 79 rows rather than 9. It was not
    theoretical there either: the Navigation note in DOCUMENTED_EVIDENCE records this exact defect
    being fixed by hand for two rows in #95, while five form-control rows went on sharing two
    strings. Either row of a sharing pair can be credited by the other's doc, so deleting one
    control's doctrine entirely leaves its row green.

    The check is **substring, not equality**, because the equality case is only the loud half.
    `"## Button"` also occurs inside `"## Button group"`, so a Button row whose entry had been
    deleted would still find its evidence in the Button-group heading. That hazard is real enough
    that the table already carries hand-added trailing newlines against it, in two separate
    comments -- which is a convention someone has to remember. This makes it a gate instead.
    """
    problems: list[str] = []
    documented = {e.name for e in ENTRIES if e.is_documented}
    pairs = sorted(
        (a, b)
        for a in documented
        for b in documented
        if a < b
        and DOCUMENTED_EVIDENCE.get(a, "").strip()
        and DOCUMENTED_EVIDENCE.get(b, "").strip()
        and (
            DOCUMENTED_EVIDENCE[a] in DOCUMENTED_EVIDENCE[b]
            or DOCUMENTED_EVIDENCE[b] in DOCUMENTED_EVIDENCE[a]
        )
    )
    for a, b in pairs:
        relation = "share the evidence" if DOCUMENTED_EVIDENCE[a] == DOCUMENTED_EVIDENCE[b] else (
            "have evidence where one contains the other:"
        )
        problems.append(
            f"{a!r} and {b!r} {relation} {DOCUMENTED_EVIDENCE[a]!r} / "
            f"{DOCUMENTED_EVIDENCE[b]!r} — one doc cannot be evidence for two rows, so deleting "
            "either row's doctrine would leave the other one vouching for it. Point each at text "
            "unique to that row, or anchor the shorter string with a trailing newline"
        )
    return problems


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

    problems += verify_evidence_is_not_shared()

    # A `documented` row must not still carry a BUILD fallback. BUILD is "the nearest safe thing
    # to do until the entry lands"; once it HAS landed, that text tells readers to go build the
    # workaround instead of using the doctrine. It is invisible in the rendered table (documented
    # rows print `—` in that column), so nothing surfaces it — the Combobox entry survived its own
    # row's promotion this way, still saying "use the documented Select until the entry lands"
    # after the Combobox entry had shipped (#95).
    #
    # BOTH sources of that text are checked. `resolve_build` prefers a row's own `build=` kwarg over
    # the BUILD dict, so a guard that read only the dict passed a row whose fallback lived inline --
    # the exact defect it exists to catch, in the half nobody looked at. Found flipping Video player
    # (#95), which carried its fallback inline.
    stale = sorted(
        {e.name for e in ENTRIES if e.is_documented and e.build.strip()}
        | (set(BUILD) & {e.name for e in ENTRIES if e.is_documented})
    )
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


def catalogue_headings() -> list[tuple[str, str]] | None:
    """Every `## ` section title in the catalogue files, as (filename, title).

    None if ANY of them cannot be read: a partial answer here is the `skip != pass` failure --
    the guard would go quiet about exactly the file that went missing.
    """
    found: list[tuple[str, str]] = []
    for name in CATALOGUE_FILES:
        path = OUT.parent / name
        if not path.is_file():
            return None
        found += [(name, t) for t in re.findall(r"^## (.+)$", path.read_text(encoding="utf-8"), re.M)]
    return found


def verify_no_undeclared_entry() -> list[str]:
    """A row that is NOT `documented` must not have a catalogue entry of its own.

    This is the negative direction, and `verify_shipped_evidence` never had it. That guard
    checks `documented` => evidence present, and `not documented` => no DOCUMENTED_EVIDENCE
    KEY -- both of which read only this file. Neither notices a row whose entry exists in the
    docs while the matrix says it does not, because the only way to see that is to look at the
    docs for a row that claims nothing.

    It is the same one-way `carve-out-without-negative-test` shape `verify_interaction_claims`
    was given both directions to avoid (#399), in the older and larger half. And it had already
    let one through: `Command palette` printed under "Derivable -- No dedicated catalogue entry,
    and none needed" while components.md had shipped `## Command palette` since #95, so the
    matrix sent agents to compose from Modal + Combobox past a written entry carrying rules the
    Build-from column does not (no APG pattern; `aria-haspopup="grid"` for icon+label+shortcut
    rows). A `derivable` row is a promise that reading the entry is unnecessary; when the entry
    exists, that promise is false.
    """
    headings = catalogue_headings()
    if headings is None:
        return [
            "cannot read the catalogue ("
            + ", ".join(CATALOGUE_FILES)
            + f") under {OUT.parent} to verify non-`documented` claims"
        ]

    problems: list[str] = []
    for entry in ENTRIES:
        if entry.is_documented:
            continue
        for filename, heading in headings:
            # Exact title, or the title followed by a separator. Both prefix directions are
            # wrong and each has a fixture: "## Carousel" must not be credited to a
            # "Carousel / Slider" row, and "## Video player" must not convict a row merely
            # called "Video". This is the hazard DOCUMENTED_EVIDENCE anchors with a trailing
            # newline ("## Button" also matches "## Button group"), from the other side --
            # so it must never be relaxed to a substring test.
            title = heading.strip()
            if title.casefold() == entry.name.casefold() or re.match(
                re.escape(entry.name) + r"\s*[—–\-(]", title, re.I
            ):
                problems.append(
                    f"{entry.name!r} is {entry.status!r}, but {filename} ships "
                    f"'## {title}' — the Derivable table tells readers no dedicated "
                    "catalogue entry exists, so they never open the one that does. "
                    "Promote the row to `documented` with its evidence, or delete the entry"
                )
    return problems


def verify_interaction_claims() -> list[str]:
    """`shipped` in the interaction table must mean the contract is written -- and the other
    statuses must mean it is NOT.

    The component half of this file has had an evidence guard since #124; this half had none, and
    it is the half that rotted. Four of nine rows outlived the work they tracked: `planned #142`
    survived the disclosure contract shipping, both `planned #95` rows survived their own doctrine,
    and `carousel / slide` said `declined` while components.md prescribes the controller by name.

    So the check runs in BOTH directions. A one-way "shipped rows cite a doc" rule is the
    `carve-out-without-negative-test` shape: every one of those four stale rows would have passed
    it, because none of them claimed `shipped`.
    """
    problems: list[str] = []
    blob = reference_blob()
    if not blob:
        return [f"cannot read the reference docs at {OUT.parent} to verify interaction claims"]

    seen: dict[str, str] = {}
    for name, status, _note, probe in INTERACTION_PATTERNS:
        if not probe.strip():
            problems.append(
                f"interaction pattern {name!r} has no probe — its status is then an assertion, "
                "which is what let four rows outlive the work they tracked"
            )
            continue
        # A probe reused across rows would make one document vouch for two patterns.
        if probe in seen:
            problems.append(
                f"interaction patterns {seen[probe]!r} and {name!r} share the probe {probe!r} — "
                "one doc cannot be evidence for two different mechanisms"
            )
        seen[probe] = name

        present = probe in blob
        if status.strip() == "shipped" and not present:
            problems.append(
                f"interaction pattern {name!r} claims `shipped`, but its probe {probe!r} does not "
                "appear in any reference doc — either it is not shipped, or the doc moved"
            )
        elif status.strip() != "shipped" and present:
            problems.append(
                f"interaction pattern {name!r} is {status!r}, but its probe {probe!r} IS in the "
                "reference docs — the contract landed and the status was never flipped"
            )

    return problems


def verify_cell_text() -> list[str]:
    """No cell may contain a `|`: markdown reads it as a column break.

    Every table in this file is assembled by `add(f"| {a} | {b} |")`, so one pipe inside a note
    silently splits the row into an extra column — the header still says three columns, the row
    now has four, and the renderer never complains. Caught while writing the `filter / typeahead`
    note as ``aria-autocomplete=list|both``, which produced a broken table that generated,
    committed and drift-checked perfectly happily.
    """
    problems: list[str] = []

    def scan(where: str, *values: str) -> None:
        for value in values:
            if "|" in value:
                problems.append(
                    f"{where} contains a `|` ({value!r}) — markdown reads it as a column break, "
                    "so the row silently grows a column. Rephrase it or write `\\|`"
                )

    for entry in ENTRIES:
        scan(f"row {entry.name!r}", entry.name, entry.kind, entry.status, entry.note,
             resolve_build(entry), resolve_use(entry))
    for name, status, note, _probe in INTERACTION_PATTERNS:
        scan(f"interaction pattern {name!r}", name, status, note)
    for name, status in LAYOUT_PRIMITIVES:
        scan(f"layout primitive {name!r}", name, status)

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
    problems.extend(verify_no_undeclared_entry())
    problems.extend(verify_interaction_claims())
    problems.extend(verify_cell_text())

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
    add("**No anatomy of their own, and none needed: these are compositions.** Build from what the")
    add("**Build from** column names rather than inventing markup — that is what keeps a JIT-built")
    add("screen consistent with everything already in the app.")
    add("")
    add("A few rows here still carry a `components.md` section (Command palette is the one to know")
    add("about). That is not a contradiction: the section records the ARIA subtleties of *composing*")
    add("them, and the row stays `derivable` because there is no anatomy to build straight from. The")
    add("earlier wording — *\"no dedicated catalogue entry\"* — said something stronger than the file")
    add("meant, and was already false when it was written.")
    add("")
    add("| Component | Kind | In TW | In FB | Build from | Where / when to use it |")
    add("|---|---|---|---|---|---|")
    for e in sorted(derivable, key=lambda x: (x.kind, x.name)):
        add(
            f"| {e.name} | {e.kind} | {_mark(bool(e.tw))} | {_mark(bool(e.fb))} | "
            f"{resolve_build(e)} | {resolve_use(e)} |"
        )
    add("")

    # The empty case is rendered DIFFERENTLY, not as a table with no rows. Emitting the header
    # plus "Build them when a project needs them" above zero rows tells the reader how to handle
    # rows that do not exist -- a dead declaration, and the section that is supposed to be the
    # file's one honest gap-marker becomes noise. Reaching zero is also the single most
    # informative thing this file can say, so it says it.
    add("## Needs doctrine — buildable today, but you are carrying the risk")
    add("")
    if needs:
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
    else:
        add("**None — every row above is `documented` or `derivable`.** No component in either corpus")
        add("now requires an agent to invent an a11y or interaction contract.")
        add("")
        add("This section is not deleted, because the status still exists and the next unclassified")
        add("upstream component may well land here. An empty table would have been worse than this")
        add("sentence: it would print guidance for rows that are not there.")
    add("")

    add("## Interaction patterns")
    add("")
    add("Enumerated separately because they do not map one-to-one onto a corpus directory —")
    add("Flowbite's `data-*` trigger attributes are the better source, and they cut across components.")
    add("")
    add("| Pattern | Status | Note |")
    add("|---|---|---|")
    for name, status, note, _probe in INTERACTION_PATTERNS:
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
    # `docs/coverage.html` is generated from the SAME data and is committed, so regenerating this
    # file without it leaves the page stale and fails `coverage artifact drift` for whoever runs the
    # gates next. Four PRs did exactly that in one afternoon. CLAUDE.md documents the pair, but a
    # note at the point of use is worth more than a paragraph nobody is reading right now.
    print("  NEXT: python3 scripts/build_coverage_artifact.py && git add docs/  "
          "— the committed page is built from this data and goes stale with it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
