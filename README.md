# Claude Skills — Rails 8 & Hotwire

Opinionated [Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
that teach Claude to build full-stack **Ruby on Rails 8.1** applications the
way I build them. Drop them into a project and Claude Code (or claude.ai)
picks them up automatically whenever the task is Rails or Hotwire.

## The skills

| Skill | What it encodes | References |
|---|---|---|
| **`rails-8`** | The full Rails 8.1.x doctrine: vanilla-first stack (built-in auth, Solid Queue/Cache/Cable, Propshaft + importmap, Kamal 2), models → controllers → views workflow, **pure RSpec** testing (no Minitest, no matcher add-ons), OpenAPI docs via rswag, AI features via ruby_llm, observability, advanced Active Record, ecosystem gems | 16 reference files |
| **`hotwire`** | The Hotwire stack from the official handbooks: Turbo 8 (Drive, morphing refreshes, Frames, Streams), Stimulus 3.2 (full controller reference), and **Hotwire Native** (iOS/Android shells, path configuration, bridge components) | 3 reference files |

They cross-reference each other — install both for Rails work.

### House rules baked in

- Rails **8.1.x**, "the Rails way": convention over configuration, server-rendered HTML, one-person-framework defaults.
- **Testing is RSpec only.** Apps are scaffolded with `rails new --skip-test`; the stack is rspec-rails + FactoryBot + Faker + Capybara + SimpleCov + WebMock/VCR, with pure RSpec matchers (no shoulda-matchers).
- **No gems from categories Rails 8 eliminated**: the built-in authentication generator (not auth engines), Solid Queue (not external job backends), Solid Cache/Cable (not Redis).
- REST APIs are documented with **OpenAPI** — rswag as the test-driven default.
- AI/LLM features use **ruby_llm** (chat, tools, structured output, embeddings, `acts_as_chat`).
- Deployment is **Kamal 2** on plain servers.

## Repository layout

```
claude-skills/
├── skills/
│   ├── rails-8/          # SKILL.md + references/  (source of truth)
│   └── hotwire/          # SKILL.md + references/
├── dist/
│   ├── rails-8.skill     # zip packages for claude.ai / Claude Desktop upload
│   └── hotwire.skill
└── scripts/
    ├── install.sh        # copy skills into a project or ~/.claude/skills
    └── package.sh        # rebuild dist/*.skill after editing skills/
```

## Install — Claude Code

Skills are plain folders; installing = putting each skill at
`<location>/skills/<name>/SKILL.md`. Two locations matter:

- **Project**: `<project>/.claude/skills/` — commit it, and everyone (and CI
  agents) working in the repo gets the skills.
- **Personal**: `~/.claude/skills/` — available in all your projects, just for
  you.

### Into a project (recommended)

```bash
git clone https://github.com/fmanimashaun/claude-skills.git
cd claude-skills
./scripts/install.sh /path/to/your/project            # both skills
./scripts/install.sh /path/to/your/project rails-8    # just one
```

No clone needed — pull the folders straight into the project instead:

```bash
cd /path/to/your/project
npx degit fmanimashaun/claude-skills/skills .claude/skills
```

Then commit:

```bash
git add .claude/skills && git commit -m "Add rails-8 and hotwire Claude skills"
```

### For all your projects (personal)

```bash
./scripts/install.sh --global          # -> ~/.claude/skills/
```

### New Rails project quickstart

```bash
mkdir myapp && cd myapp && git init
npx degit fmanimashaun/claude-skills/skills .claude/skills
claude
# then: "Create a new Rails 8 app in this directory for <what you're building>"
```

The rails-8 skill takes it from there — `rails new --skip-test`, RSpec wiring,
the golden-path workflow.

### Verify

Start (or continue) a Claude Code session in the project and ask
*"What skills are available?"* — or just give it a Rails task; skills
auto-trigger from their descriptions. Notes:

- Edits to already-installed skills are picked up live within a session; if
  the `.claude/skills/` directory itself didn't exist when the session
  started, restart Claude Code once so it can be watched.
- The most common install mistake is nesting one level too deep: the path
  must be `.claude/skills/rails-8/SKILL.md`, not
  `.claude/skills/skills/rails-8/SKILL.md`.

## Install — claude.ai and Claude Desktop

Custom skills are uploaded as zip files, individually per user:

1. Grab `dist/rails-8.skill` and `dist/hotwire.skill` from this repo (or a
   [release](../../releases)).
2. In claude.ai: **Settings → Features → Skills → upload** each file.
   Requires a paid plan (Pro/Max/Team/Enterprise) with **code execution
   enabled**; on Team/Enterprise an admin may need to enable the capability
   first.
3. Uploads are per-user — teammates upload their own copies (or use the
   project install above in Claude Code, which *is* shared via git).

Docs: [Agent Skills overview](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)
· [Claude help center](https://support.claude.com).

## Install — Claude Agent SDK / API

The Agent SDK reads the same directories: point `cwd` at a project containing
`.claude/skills/`, include `"user"`/`"project"` in `setting_sources`, and
allow the `Skill` tool. For the raw API, skills upload via the Skills API and
run in the code-execution container. See
[Agent Skills in the SDK](https://platform.claude.com/docs/en/agent-sdk/skills).

## Updating

```bash
cd claude-skills && git pull
./scripts/install.sh /path/to/your/project   # re-copy into each install target
```

On claude.ai, delete the old skill and upload the new `.skill` file. After
editing anything under `skills/`, rebuild the packages with
`./scripts/package.sh`.

## Try these prompts

- "Create a new Rails 8 app for a facilities work-order tracker."
- "Add live-updating comments to posts." (Turbo Streams + RSpec)
- "Document the JSON API with OpenAPI." (rswag)
- "Add an AI assistant that can look up work orders." (ruby_llm tools)
- "Wrap this app as an iPhone app with a native submit button." (Hotwire Native)

## Versioning

Skill content is pinned to **Rails 8.1.3**, **Turbo 8.0.23**, **Stimulus
3.2.2**, and **Hotwire Native iOS 1.2.2 / Android 1.2.5**, written July 2026.
The skills instruct Claude to verify versions when the current date is well
past that — but expect a refresh here when Rails 8.2/9 lands.

## License

[MIT](LICENSE) — use, fork, adapt.
