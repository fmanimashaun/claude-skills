# Claude Skills — a Rails 8 toolchain for Claude Code

Five plugins that teach Claude to build, review, test and ship Rails 8 applications: the stack
doctrine it should follow, the flow it should work in, an independent QA pass that does not trust
the developer, a design system, and a release lifecycle.

**Install it, then talk to Claude normally.** The plugins add commands and specialist agents; you do
not need to learn the internals to get value on day one.

---

## Install

```bash
/plugin marketplace add fmanimashaun/claude-skills
/plugin install rails-stack@claude-skills     # the doctrine — start here
```

Then add the flows you want:

```bash
/plugin install rails-flow@claude-skills      # build/fix/review loop
/plugin install design-flow@claude-skills     # UI, design system, assets
/plugin install qa-flow@claude-skills         # independent QA
/plugin install pipeline@claude-skills        # release lifecycle
```

Verify:

```bash
/plugin                    # lists what is installed
/rails-flow:setup-flow     # scaffolds CLAUDE.md, guardrails and the brain into your project
```

<details>
<summary><b>Other environments</b> — claude.ai, Claude Desktop, no-plugin setups, updating</summary>

**claude.ai / Claude Desktop.** Download the `.skill` files from the
[latest release](https://github.com/fmanimashaun/claude-skills/releases/latest) and upload them in
Settings → Capabilities → Skills. Each is self-contained.

**No plugin support** (Agent SDK, older clients). Copy the skill directories into your project's
`.claude/skills/`:

```bash
git clone https://github.com/fmanimashaun/claude-skills.git /tmp/cs
mkdir -p .claude/skills && cp -R /tmp/cs/skills/* .claude/skills/
```

**For every project.** Same copy, into `~/.claude/skills/` instead.

**Updating.** `/plugin marketplace update claude-skills`, then restart Claude Code. To confirm what
you actually got — installed versions drift from what you think you installed — run
`/rails-flow:toolchain-check`.

</details>

---

## What you get

| plugin | what it does |
|---|---|
| **rails-stack** | The doctrine: Rails 8.1, Hotwire, pure RSpec, Tailwind v4, a design system, and the review rules. Bundles seven skills — no commands, it just makes Claude write the right code. |
| **rails-flow** | The build loop — `/feature`, `/fix`, `/review`, plus a durable project memory and an autonomous driver. |
| **design-flow** | UI and design system work — components, tokens, audits, a curated asset library, and an optional pen.dev tier for exploring screens visually before any code is written. |
| **qa-flow** | An **independent** QA engineer that treats the developer's claims as unverified and produces evidence. |
| **pipeline** | Build → verify → certify → release, with circuit breakers for unattended runs. |

### The seven skills in `rails-stack`

| skill | covers |
|---|---|
| `rails-8` | the stack — models, jobs, auth, APIs, deployment |
| `hotwire` | Turbo, Stimulus, Hotwire Native |
| `fidara-design` | the design system: tokens, components, art direction, reference research |
| `code-review` | correctness review classes — the bugs a reviewer must find |
| `quality-pass` | reuse, simplification, efficiency, altitude — advisory, never blocking |
| `derived-artifacts` | anything whose numbers come from somewhere else |
| `parallel-session-lane` | working as one of several agent sessions in one repo |

---

## A first run

The shortest path from empty directory to something real:

```bash
/rails-flow:setup-flow          # 1. scaffold doctrine + memory into the project
/design-flow:setup              # 2. tokens, brand pack, design system
/rails-flow:feature             # 3. describe what you want; it plans, builds, reviews
/qa-flow:verify                 # 4. an independent pass that does not trust step 3
```

Steps 1–2 are once per project. Steps 3–4 are the loop.

---

## Commands

<details>
<summary><b>rails-flow</b> — build, fix, review, remember</summary>

`feature` `fix` `review` `issues` `brief` `curate` `explain` `graph` `handoff` `pr-comments`
`report` `setup-flow` · **memory:** `brain` `brain-review` `brain-sync` · **autonomous:** `drive`
`escalate` `toolchain-check`

</details>

<details>
<summary><b>design-flow</b> — UI and the design system</summary>

`setup` `component` `tokens` `variants` `mobile` `audit` `critique` · **assets:** `assets`
`generate`

</details>

<details>
<summary><b>qa-flow</b> — independent verification</summary>

`setup-qa` `cases` `verify` `certify` `functional` `smoke` `crawl`

</details>

<details>
<summary><b>pipeline</b> — lifecycle and release</summary>

`setup-pipeline` `pipeline` `status` `ack` `release` `install-hooks` · **cloud:** `setup-cloud`
`deploy-cloud`

</details>

---

## How it fits together

Three loops, each with a different job:

1. **Build** (`rails-flow`) — plan, implement, review, remember. Spec-first, IA before code.
2. **Verify** (`qa-flow`) — a separate agent that assumes nothing from the build loop and produces
   evidence rather than assurances.
3. **Ship** (`pipeline`) — gates the two above into a release, and **stops** rather than digging
   when an unattended run goes wrong.

The separation is the point: a build agent that also signs off its own work is a build agent that
signs off its own work.

**Read next:** [architecture](docs/architecture.md) for the design reasoning and what we
deliberately did *not* adopt · [harness doctrine](docs/harness-doctrine.md) for when a hook should
fail open versus closed · [code-review graph](docs/code-review-graph.md) for the optional
tool-gated review integration.

---

## Reporting problems

The toolchain reports its own bugs. From any project using it:

```bash
/rails-flow:report
```

That files a structured, version-pinned, deduplicated issue on this repo. Every issue in the tracker
arrived that way, and it is the fastest route to a fix — the report carries the versions and paths a
maintainer would otherwise have to ask for.

---

## Repository layout

```
skills/              the seven skills — the doctrine that ships
plugins/             rails-flow · qa-flow · pipeline · design-flow
dist/                packaged .skill files for claude.ai
docs/                architecture, coverage and inventory pages
scripts/             the gates that keep all of the above honest
.claude/             maintainer tooling — not distributed
```

`CLAUDE.md` is the maintainer's guide to this repo. If you are here to build a Rails app, you want
the plugins above, not that file.

---

## Versioning

Components version independently; the marketplace tag is the release label. Every change lands in
[`CHANGELOG.md`](CHANGELOG.md) under its component, and a release publishes one block. Versions are
assigned at promotion, never before — a version number on unshipped work is a claim about something
you cannot install.

## License

MIT — see [LICENSE](LICENSE).
