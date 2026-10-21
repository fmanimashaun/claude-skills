---
name: derived-artifacts
description: Moved to the core-skills plugin; load core-skills:derived-artifacts. This redirect is removed after two releases.
---

# derived-artifacts has moved

This skill now lives in the **core-skills** plugin, so a project that uses another stack does not have
to install another stack's doctrine to get it. Load **`core-skills:derived-artifacts`** instead. `rails-stack` declares
`core-skills` as a dependency, so installing or updating `rails-stack` installs it; if it is missing,
run `/plugin install core-skills@claude-skills`.

This redirect exists for two releases (#2186) so a project that pins `rails-stack:derived-artifacts` is told
where the skill went instead of finding nothing, and is then deleted.
