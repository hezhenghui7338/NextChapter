#!/usr/bin/env bash
# 开发模式启动：swift build + 编译 Asset Catalog + 运行
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MACOS="$ROOT/apps/macos"
ASSETS_DIR="$MACOS/NextChapter/Assets.xcassets"
CONFIG="${1:-debug}"

cd "$MACOS"
swift build -c "$CONFIG"

BUNDLE_DIR="$MACOS/.build/arm64-apple-macosx/$CONFIG/NextChapter_NextChapter.bundle"
if [[ -d "$BUNDLE_DIR/Assets.xcassets" ]]; then
  echo "==> 编译 Asset Catalog..."
  ASSETS_BUILD_DIR=$(mktemp -d)
  ASSETS_PLIST_OUT=$(mktemp)
  xcrun actool \
    --output-format human-readable-text \
    --notices --warnings --errors \
    --platform macosx \
    --minimum-deployment-target 14.0 \
    --app-icon AppIcon \
    --output-partial-info-plist "$ASSETS_PLIST_OUT" \
    --compile "$ASSETS_BUILD_DIR" \
    "$ASSETS_DIR" >/dev/null
  cp "$ASSETS_BUILD_DIR/Assets.car" "$BUNDLE_DIR/Assets.car"
  rm -rf "$ASSETS_BUILD_DIR" "$ASSETS_PLIST_OUT"
  echo "    ✅ Assets.car → $BUNDLE_DIR"
fi

exec "$MACOS/.build/$CONFIG/NextChapter"
