#!/usr/bin/env bash
# Rebuild dist/<name>.skill archives (zip of each skill folder) after editing skills/.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
mkdir -p dist

for skill in skills/*/; do
  name="$(basename "$skill")"
  out="dist/$name.skill"
  rm -f "$out"
  if command -v zip >/dev/null 2>&1; then
    (cd skills && zip -qr "../$out" "$name" -x '*.DS_Store')
  else
    python3 -c "import shutil,os; shutil.make_archive('dist/$name','zip','skills','$name'); os.replace('dist/$name.zip','dist/$name.skill')"
  fi
  echo "packaged: $out"
done
