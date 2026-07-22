#!/usr/bin/env bash
# Thin wrapper — the canonical build lives in package_core.py (deterministic zip).
set -euo pipefail
cd "$(dirname "$0")"
exec python3 package_core.py "$@"
