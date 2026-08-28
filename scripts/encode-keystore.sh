#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════
# encode-keystore.sh — turn a .jks into the base64 string GitHub
# Actions needs for the ANDROID_KEYSTORE_BASE64 secret.
#
# Usage:
#   ./scripts/encode-keystore.sh ~/keystores/acechasers-upload.jks
#
# The output is printed to STDOUT and (on macOS) copied to the
# clipboard automatically. On Linux, pipe it to `xclip` yourself if
# desired:
#   ./scripts/encode-keystore.sh ~/keystores/acechasers-upload.jks | xclip -selection clipboard
#
# Then in GitHub:
#   Settings → Secrets and variables → Actions → New repository secret
#   Name:  ANDROID_KEYSTORE_BASE64
#   Value: paste
# ══════════════════════════════════════════════════════════════════
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <path-to-keystore.jks>" >&2
  exit 2
fi

KEYSTORE="$1"
if [ ! -f "$KEYSTORE" ]; then
  echo "✗ Keystore not found: $KEYSTORE" >&2
  exit 1
fi

# `-w 0` on Linux prevents line-wrapping (GitHub secrets tolerate wrap
# but no-wrap keeps things clean); on macOS `base64` wraps by default
# but we strip newlines below either way.
if base64 --help 2>&1 | grep -q -- "-w"; then
  ENCODED=$(base64 -w 0 "$KEYSTORE")
else
  ENCODED=$(base64 "$KEYSTORE" | tr -d '\n')
fi

echo "$ENCODED"

# Convenience: copy to macOS clipboard if pbcopy is available.
if command -v pbcopy >/dev/null 2>&1; then
  printf "%s" "$ENCODED" | pbcopy
  echo >&2
  echo "✓ Copied to clipboard (macOS). Paste into ANDROID_KEYSTORE_BASE64 secret." >&2
fi

echo >&2
echo "Also configure these three companion secrets:" >&2
echo "  • ANDROID_KEYSTORE_PASSWORD  (storePassword)" >&2
echo "  • ANDROID_KEY_PASSWORD       (keyPassword)" >&2
echo "  • ANDROID_KEY_ALIAS          (e.g. acechasers-upload)" >&2
