#!/usr/bin/env bash
# 开发模式启动：生成图标 → swift build → 编译 Asset Catalog → 运行
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MACOS="$ROOT/apps/macos"
ASSETS_DIR="$MACOS/NextChapter/Assets.xcassets"
CONFIG="${1:-debug}"

# 确保 xcassets 与 docs/assets 同步（用户更新 logo.jpeg 后生效）
SOURCE_LOGO="${NC_LOGO:-$ROOT/docs/assets/logo.jpeg}"
if [[ -f "$SOURCE_LOGO" ]]; then
  bash "$ROOT/scripts/generate-assets.sh" "$SOURCE_LOGO"
fi

cd "$MACOS"
swift build -c "$CONFIG"

BIN_DIR="$(swift build -c "$CONFIG" --show-bin-path)"
BUNDLE_DIR="$BIN_DIR/NextChapter_NextChapter.bundle"

if [[ -d "$ASSETS_DIR" ]]; then
  echo "==> 编译 Asset Catalog..."
  ASSETS_BUILD_DIR=$(mktemp -d)
  ASSETS_PLIST_OUT=$(mktemp)
  if ! xcrun actool \
      --output-format human-readable-text \
      --notices --warnings --errors \
      --platform macosx \
      --minimum-deployment-target 14.0 \
      --app-icon AppIcon \
      --output-partial-info-plist "$ASSETS_PLIST_OUT" \
      --compile "$ASSETS_BUILD_DIR" \
      "$ASSETS_DIR" >/dev/null; then
    echo "❌ actool 编译 Asset Catalog 失败" >&2
    rm -rf "$ASSETS_BUILD_DIR" "$ASSETS_PLIST_OUT"
    exit 1
  fi
  mkdir -p "$BUNDLE_DIR"
  cp "$ASSETS_BUILD_DIR/Assets.car" "$BUNDLE_DIR/Assets.car"
  if [[ -f "$ASSETS_BUILD_DIR/AppIcon.icns" ]]; then
    cp "$ASSETS_BUILD_DIR/AppIcon.icns" "$MACOS/NextChapter/AppIcon.icns"
    cp "$ASSETS_BUILD_DIR/AppIcon.icns" "$BUNDLE_DIR/AppIcon.icns"
  elif [[ -f "$MACOS/NextChapter/AppIcon.icns" ]]; then
    cp "$MACOS/NextChapter/AppIcon.icns" "$BUNDLE_DIR/AppIcon.icns"
  fi
  rm -rf "$ASSETS_BUILD_DIR" "$ASSETS_PLIST_OUT"
  echo "    ✅ Assets.car → $BUNDLE_DIR"
fi

exec "$BIN_DIR/NextChapter"
