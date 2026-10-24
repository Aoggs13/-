#!/usr/bin/env bash
# Official standalone Luau toolchain. No credentials or application services needed.
set -euo pipefail
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
  echo 'The pinned Luau bundle requires Linux x86_64.' >&2
  exit 1
fi
TOOLS_DIR=/workspace/.tools/luau-0.699
ARCHIVE_SHA=4169f04aa66c8f5039d5cb2257aab9e81674ec152a8d84bda96c12cdb9fa973a
TEMP_DIR=$(mktemp -d /tmp/lava-luau.XXXXXX)
trap 'rm -rf "$TEMP_DIR"' EXIT
curl --fail --location --retry 2 --silent --show-error \
  https://github.com/luau-lang/luau/releases/download/0.699/luau-ubuntu.zip \
  --output "$TEMP_DIR/luau.zip"
printf '%s  %s\n' "$ARCHIVE_SHA" "$TEMP_DIR/luau.zip" | sha256sum --check --status
mkdir -p "$TOOLS_DIR"
unzip -oq "$TEMP_DIR/luau.zip" -d "$TOOLS_DIR"
"$TOOLS_DIR/luau" --help >/dev/null
printf 'Luau 0.699 installed in %s\n' "$TOOLS_DIR"
