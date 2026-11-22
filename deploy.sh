#!/bin/sh
# Publish the 2D game and the independent Three.js trial to the existing static site.
set -eu
SOURCE_DIR=$(cd "$(dirname "$0")" && pwd)
SITE_DEST=${DEPLOY_DIR:-"$HOME/fanren-game"}
mkdir -p "$SITE_DEST"
for file in index.html game3d.html; do
  cp "$SOURCE_DIR/$file" "$SITE_DEST/$file"
  chmod 644 "$SITE_DEST/$file"
done
for directory in web3d assets vendor; do
  mkdir -p "$SITE_DEST/$directory"
  cp -R "$SOURCE_DIR/$directory/." "$SITE_DEST/$directory/"
done
if ! ss -ltn | grep -q ':8090 '; then
  busybox httpd -p 0.0.0.0:8090 -h "$SITE_DEST"
fi
echo "deployed -> $SITE_DEST"
sha256sum "$SITE_DEST/index.html" "$SITE_DEST/game3d.html"
