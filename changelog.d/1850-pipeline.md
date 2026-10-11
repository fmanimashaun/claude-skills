section: pipeline
- **pipeline's two hooks start `/bin/bash -p` and source `hooks/scripts/lib/trusted-env.sh` first — `plugins/pipeline/hooks/hooks.json`, `plugins/pipeline/hooks/scripts/lib/trusted-env.sh`** (#1850; P1 of #1843). `pipeline-status.sh` and `board-refresh.sh` ran `git` and `python3` through a `PATH` a repository's settings could set. Same lib as rails-flow, byte-identical.
