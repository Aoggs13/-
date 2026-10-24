#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
LUAU_DIR=${LAVA_LUAU_DIR:-/workspace/.tools/luau-0.699}
for spec in tests/*.spec.luau; do
  "$LUAU_DIR/luau" "$spec"
done
# Roblox services cannot run in the standalone VM, but every shipped script must compile.
while IFS= read -r source; do
  "$LUAU_DIR/luau-compile" "$source" > /dev/null
done < <(find src -type f -name '*.luau' | sort)
"$LUAU_DIR/luau-analyze" src/shared/*.luau src/server/ProfileStore.luau
python3 tools/build.py
python3 -m unittest discover -s tests -p '*_test.py' -v
