#!/usr/bin/env bash
# 从源 LOGO 生成 AppLogo、AppIcon 及 AppIcon.icns
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="${1:-$ROOT/docs/assets/logo.jpeg}"
ASSETS="$ROOT/apps/macos/NextChapter/Assets.xcassets"
DOCS_ASSETS="$ROOT/docs/assets"
ICONSET="$(mktemp -d)/AppIcon.iconset"

if [[ ! -f "$SOURCE" ]]; then
  echo "❌ 找不到源 LOGO：$SOURCE" >&2
  exit 1
fi

echo "==> 从 $SOURCE 生成应用图标资源..."

mkdir -p "$DOCS_ASSETS"
SOURCE_ABS="$(cd "$(dirname "$SOURCE")" && pwd)/$(basename "$SOURCE")"
DEST_JPEG="$DOCS_ASSETS/logo.jpeg"
DEST_JPEG_ABS="$(cd "$DOCS_ASSETS" && pwd)/$(basename "$DEST_JPEG")"
if [[ "$SOURCE_ABS" != "$DEST_JPEG_ABS" ]]; then
  cp "$SOURCE" "$DEST_JPEG"
fi

LOGO_SET="$ASSETS/AppLogo.imageset"
ICON_SET="$ASSETS/AppIcon.appiconset"
mkdir -p "$LOGO_SET" "$ICON_SET" "$ICONSET"

# AppLogo：界面内横幅（1x / 2x）
sips -s format png "$SOURCE" --out "$LOGO_SET/logo.png" >/dev/null
sips -z 1536 2816 "$LOGO_SET/logo.png" --out "$LOGO_SET/logo@2x.png" >/dev/null
cp "$LOGO_SET/logo.png" "$DOCS_ASSETS/logo.png"

# AppIcon：从 LOGO 顶部居中裁出图标区域（书 + AI），再缩成 1024×1024
# 注意：sips --cropOffset 顺序是 offsetY offsetX（不是 X Y）
SQUARE="$(mktemp).png"
sips -s format png "$SOURCE" --out "$SQUARE" >/dev/null
W=$(sips -g pixelWidth "$SQUARE" | awk '/pixelWidth/ {print $2}')
H=$(sips -g pixelHeight "$SQUARE" | awk '/pixelHeight/ {print $2}')
ICON_SIDE=$(( H * 62 / 100 ))
if (( ICON_SIDE > W )); then ICON_SIDE=$W; fi
CROP_X=$(( (W - ICON_SIDE) / 2 ))
sips -c "$ICON_SIDE" "$ICON_SIDE" --cropOffset 0 "$CROP_X" "$SQUARE" >/dev/null
sips -z 1024 1024 "$SQUARE" >/dev/null
cp "$SQUARE" "$DOCS_ASSETS/logo-square.png"

declare -a SIZES=(16 32 128 256 512)
for size in "${SIZES[@]}"; do
  sips -z "$size" "$size" "$SQUARE" --out "$ICON_SET/icon_${size}x${size}.png" >/dev/null
  s2=$((size * 2))
  sips -z "$s2" "$s2" "$SQUARE" --out "$ICON_SET/icon_${size}x${size}@2x.png" >/dev/null
  cp "$ICON_SET/icon_${size}x${size}.png" "$ICONSET/icon_${size}x${size}.png"
  cp "$ICON_SET/icon_${size}x${size}@2x.png" "$ICONSET/icon_${size}x${size}@2x.png"
done

# AppIcon.icns（Dock / Finder 图标）
ICNS_OUT="$ROOT/apps/macos/NextChapter/AppIcon.icns"
iconutil -c icns "$ICONSET" -o "$ICNS_OUT"
rm -rf "$(dirname "$ICONSET")" "$SQUARE"

echo "    ✅ AppLogo.imageset"
echo "    ✅ AppIcon.appiconset ($(ls "$ICON_SET"/*.png | wc -l | tr -d ' ') 个尺寸)"
echo "    ✅ AppIcon.icns"
