section: design-flow
- **design-flow's hook starts `/bin/bash -p` and sources `hooks/scripts/lib/trusted-env.sh` first — `plugins/design-flow/hooks/hooks.json`, `plugins/design-flow/hooks/scripts/lib/trusted-env.sh`** (#1850; P1 of #1843). `design-tells.sh` ran `python3` through a `PATH` a repository's settings could set. Same lib as rails-flow, byte-identical.
