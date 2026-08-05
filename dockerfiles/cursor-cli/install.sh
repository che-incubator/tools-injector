#!/bin/sh
set -eu

VERSION="${CURSOR_CLI_VERSION:?CURSOR_CLI_VERSION is required}"
# "lab" is the only channel with working download URLs (as of 2026-07).
# "stable" returns HTTP 400. Cursor has no documented retention policy for
# lab versions — if this URL stops resolving, check the latest version at:
#   curl -fsSL https://cursor.com/install | grep downloads.cursor.com
CHANNEL="${CURSOR_CLI_CHANNEL:-lab}"
ARCH="${TARGETARCH:?TARGETARCH is required}"
DEST="${CURSOR_CLI_DEST:-/opt/cursor-cli}"

case "$ARCH" in
  amd64) DL_ARCH=x64 ;;
  arm64) DL_ARCH=arm64 ;;
  *) echo "unsupported arch: $ARCH" >&2; exit 1 ;;
esac

URL="https://downloads.cursor.com/${CHANNEL}/${VERSION}/linux/${DL_ARCH}/agent-cli-package.tar.gz"

mkdir -p "$DEST/app" "$DEST/bin"
ARCHIVE="$(mktemp /tmp/cursor-cli-XXXXXX)"
curl -fsSL --connect-timeout 30 --max-time 300 "$URL" -o "$ARCHIVE"
tar --strip-components=1 -xzf "$ARCHIVE" -C "$DEST/app"
rm -f "$ARCHIVE"
ln -sf ../app/cursor-agent "$DEST/bin/agent"
ln -sf ../app/cursor-agent "$DEST/bin/cursor-agent"
