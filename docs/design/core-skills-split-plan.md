# core-skills split (#2186) — plan only, nothing built

Measured 2026-10-22 on `origin/dev` 565b72d6 (after #2253). Counts are files outside the skill's own directory that name its path, excluding CHANGELOG, changelog.d, docs/wiki and dist.

## What is true today
`plugins/rails-stack/skills/` holds seven skills: `rails-8` and `hotwire` (Rails doctrine), and five stack-neutral ones: `code-review`, `quality-pass`, `derived-artifacts`, `parallel-session-lane`, `design-system`. `scripts/package_core.py` builds `dist/<skill>.skill` from that one directory (`SKILLS_DIR`). Only `flow-suite`'s `plugin.json` declares `dependencies` today.

## What changes
- **New plugin `core-skills`** (name to be confirmed by the owner) holds `code-review`, `quality-pass`, `derived-artifacts`, `parallel-session-lane`. It is also the single canonical home of `agent-output-contract.md` and `findings.py` (see Open 3).
- **`design-system` moves to `design-flow`** (owner ruling: design is neutral). 60's #2272 moves `component-shapes.json` into design-flow first.
- **Redirect**: each moved skill leaves a stub `plugins/rails-stack/skills/<skill>/SKILL.md` (same `name`, one-line description, body: "moved to `<plugin>`; load `<plugin>:<skill>`"), for two releases, the way #2173 left stub agents. A project that updated rails-stack first is told where it went instead of finding nothing. Cost: five stub listings in rails-stack's always-on line (the ratchet is edited for rails-stack only, with this reason, and drops when the stubs go).
- `dist/*.skill` stays **one per skill, same file names**; `package_core.py` reads each skill from its new plugin (a name-to-directory table, with a negative case for a skill found in two places).

## Dependencies, marketplace and flow-suite
- `marketplace.json` gets a `core-skills` entry (source `./plugins/core-skills`).
- `plugin.json` `dependencies`: `rails-stack`, `nextjs-stack` and `rails-flow` each declare `core-skills` (rails-flow's `pr-reviewer` and `coordinate` name `code-review` and `parallel-session-lane`). `rails-stack` also needs `design-flow` once `design-system` moves, because two of its agents name that skill (`code-reviewer` once, `design-auditor` twice; measured).
- `flow-suite` lists `rails-flow`, `qa-flow`, `pipeline` and gets `core-skills` only if dependencies are not transitive (Open 1).
- `lint_self_consistency` `undocumented-plugin` and the README plugin list get the new plugin; CLAUDE.md's distributed-plugins list is edited by the coordinator, not by me.

## Every reference to update (measured)
| skill | files naming `plugins/rails-stack/skills/<skill>` | by area |
|---|---|---|
| code-review | 18 | .claude/commands 3, scripts 6, docs/architecture 3, docs/brain 2, docs/doctrine 2, .github 1, CLAUDE.md 1 |
| quality-pass | 8 | scripts 3, docs/architecture 3, docs/brain 1, CLAUDE.md 1 |
| derived-artifacts | 6 | scripts 2, docs/architecture 3, docs/brain 1 |
| parallel-session-lane | 18 | .claude/skills 6 (the maintainer mirror), scripts 5, docs/architecture 3, docs/evidence 2, rails-flow/scripts 1, docs/brain 1 |
| design-system | 32 | scripts 20, docs/architecture 3, docs/brain 2, docs/design 2, evals 1, design-flow/scripts 1, rails-flow/scripts 1, .claude/skills 1, docs/evidence 1 |

Plus the keyed tables, each of which needs its path or home changed with a negative case: `scripts/check_frontmatter.py` (`OUR_SKILLS`), `scripts/build_maintainer_skills.py` (`SHIPPED`, the `parallel-session-lane` mirror), `scripts/package_core.py`, `evals/suite.json` (stages `rails-8, hotwire, design-system`), the derived-artifact builders that read a skill's reference, and the generated pages (`rebuild_generated.py`, never hand-merged). Commands and agents that name a skill by bare name (9 in design-flow for `design-system`, 2 for `code-review`, 1 for `parallel-session-lane`) are unchanged if bare names resolve across installed plugins (Open 2).

## Slicing (one issue, one PR)
1. **#2186 as filed = core-skills**: the plugin, four skills, stubs, dependencies, packaging, references. Needs no design-flow change.
2. **New issue: `design-system` to design-flow**, after #2272 lands; carries the 32-file reference update, the dist path, and the `rails-stack` to `design-flow` dependency.
3. Removing the stubs after two releases is a third, later issue.

## Verified 2026-10-22 (doctrine-verifier, then every phrase matched verbatim in the raw HTML of the docs page)
- **Confirmed:** plugin `dependencies` is a documented array of "Plugins that must be enabled for this one to work" (manifest-reference); Claude Code "also installs and enables the plugin's declared dependencies" (install); bare names resolve against the declaring plugin's own marketplace, cross-marketplace needs `allowCrossMarketplaceDependenciesOn` (dependencies); a plugin skill and a non-plugin skill "both load, because plugin skills are namespaced" (skills); a subagent can "discover and invoke project, user, and plugin skills through the Skill tool" (sub-agents).
- **Inconclusive, so the explicit path is taken:** whether dependencies are transitive (no page says; "transitiv" is absent from the dependencies page's raw HTML), and how an agent's `skills:` entry resolves a skill from another plugin. So every plugin that needs `core-skills` declares it **directly** (rails-flow, rails-stack, nextjs-stack and flow-suite), and a skill invoked across plugins is written `plugin:skill`.
- **Downstream grep (read-only, 2026-10-22):** Retask-platform and flo-it-ui contain 0 files naming `rails-stack:<skill>` for any of the five skills and 0 naming `rails-stack/skills/<skill>`. Retask enables `rails-stack@claude-skills` in `.claude/settings.json` and its CI comments mention rails-stack versions; a rails-stack that declares dependencies installs them with it, so neither needs a settings change.

## Open (each answered before it is built)
1. **Do `dependencies` install, and are they transitive?** Only `flow-suite` uses the field. A framework claim: verify against the official plugin reference with `doctrine-verifier` plus the raw-page phrase check, for the version in scope. INCONCLUSIVE means the plan lists the plugins to install explicitly in each README instead of relying on it.
2. **Do bare skill names resolve across plugins?** Same verification. If they do not, every bare name above needs the qualified `plugin:skill` form.
3. **The vendored `agent-output-contract.md` and `findings.py` copies cannot be deleted by the move**: the stack agents read them through `${CLAUDE_PLUGIN_ROOT}` and no cross-plugin root exists. core-skills becomes their canonical home and the byte-identical copies in rails-stack (and qa-flow) stay, held by the existing drift rules, unless an agent can load them through a skill. Coordinator to confirm.
4. **The name `core-skills`** is the owner's call. `design-flow` does not need `core-skills`: nothing in it loads those skills (one code comment names `code-review`).
5. **Retask and flo-it-ui** install by plugin name; the stubs cover them for two releases. Which projects pin `rails-stack:<skill>` is measured by grep of their repos before the stubs are removed.
