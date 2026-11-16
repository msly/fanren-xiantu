#!/bin/sh
# 部署到 busybox httpd 的站点目录（http://<服务器IP>:8090/）
set -e
DEST="$HOME/fanren-game"
mkdir -p "$DEST"
cp "$(dirname "$0")/index.html" "$DEST/index.html"
chmod 644 "$DEST/index.html"
if ! ss -ltn | grep -q ':8090 '; then
  busybox httpd -p 0.0.0.0:8090 -h "$DEST"
fi
echo "deployed -> $DEST ($(md5sum "$DEST/index.html" | cut -d' ' -f1))"
