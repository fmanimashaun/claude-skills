---
description: Install local git-hook nudges that detect lifecycle transitions without spending tokens
---

# /pipeline:install-hooks

Run the installer that writes local git hooks (nudge-only — they print a reminder and
leave a marker the SessionStart hook surfaces; they NEVER invoke Claude or spend
tokens):

```bash
bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/install-git-hooks.sh
```

Requires `pipeline.yml` (run `/pipeline:setup-pipeline` first). Report what was
installed and confirm the no-token-spend behavior. Mention the dormant GitHub Actions
adapter (`plugins/pipeline/pipeline.actions.yml.example`) for when cloud minutes exist.
