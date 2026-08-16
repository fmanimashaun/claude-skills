---
description: Generate the composition brief for one surface — which owned asset fills which band, at what tone, and which bands have nothing — from the project's own research, anatomy and manifest.
---

# `/design-flow:compose`

Produce a **reviewable brief for one surface** before any markup is written.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/compose_brief.py" --surface marketing-hero --render
```

Writes `docs/design/compositions/<surface>.json` and a generated `.md` view beside it.

## The asymmetry this closes

| decision | what the project got | reviewable first? |
|---|---|---|
| **what to buy** | `plan.json` + a generated `plan.md`, one row per asset, with `why` and cost | **yes** |
| **how to compose it** | *nothing* | no |

We generated a concrete artefact for the decision that costs **money** and nothing for the decision
that determines whether the page looks professional. `/design-flow:component` is thorough and it is a
**reading list** — it says which files to open, then leaves the agent to derive, per surface and from
scratch, which assets this surface needs and where they go.

## Asset selection is a lookup, not taste

That is the whole reason this can be generated rather than being a second opinion.

`generation_gate` already **requires** every manifest row to carry `use_cases` (*"where it MAY go — a
list, because reuse is the point"*) and `avoid` (*"where it must NOT go"*). Nothing read them at
composition time. Now a band takes the manifest row whose `use_cases` match it, and the brief records
**which entry matched and why**.

**`avoid` is evaluated first and is absolute.** A stated prohibition outranks a stated permission, or
the field means nothing at the only moment it could act — and `/design-flow:generate` calls it *"the
one people skip and the one that matters most"*.

**The band matches; the surface only excludes.** Folding the surface name into the match made every
band on `marketing-hero` take the asset whose use case said *"marketing hero"* — one asset, whole
page. But `avoid` still sees the surface, because *"anywhere beside a product screenshot"* is a
statement about the page rather than about one band.

## Unfilled bands are the point, not an omission

A band with no owned asset is listed as such. That is the honest bridge back to `/design-flow:assets`:
an unfilled band is either a `plan.json` row or a deliberate blank, and it should not be neither.

## It generates a brief; it does not judge a surface

Override any of it. The only mechanical checks are **joins**: a band naming an owned asset names one
that exists, and no band uses an asset whose `avoid` matches. Neither is a judgement — because a gate
on judgement gets switched off, and then nothing checks anything. `--check` reports drift in a
committed view and those joins, nothing else.

`--intent` picks the per-surface class from `art-direction.md` §3 — `marketing`, `dense-app`,
`focused-task`, `empty-error`. The same composition is right on one surface and wrong on another.

## Degraded rather than absent

A project with no research record or no manifest still gets a brief, and the brief **says what it was
composed without**. A silently thinner document reads as a simpler page rather than as missing inputs.

## Verifying a change to this path

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/compose_brief.py" --selftest
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/compose_brief.py" --check
```
