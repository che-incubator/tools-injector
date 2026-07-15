#!/bin/sh
set -eu

VERSION="${CURSOR_CLI_VERSION:?CURSOR_CLI_VERSION is required}"
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
curl -fsSL "$URL" | tar --strip-components=1 -xzf - -C "$DEST/app"
ln -sf ../app/cursor-agent "$DEST/bin/agent"
ln -sf ../app/cursor-agent "$DEST/bin/cursor-agent"
