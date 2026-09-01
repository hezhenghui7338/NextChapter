#!/usr/bin/env bash
# 发布版打包：PyInstaller 打包 sidecar + SwiftPM 构建 macOS app，
# 并把 sidecar 嵌入到 .app/Contents/Resources/，让 App 启动时能找到。
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CORE_PKG="$ROOT/packages/nextchapter-core"
MACOS="$ROOT/apps/macos"
DIST="$ROOT/dist"
mkdir -p "$DIST"

VERSION="${NC_VERSION:-0.1.2}"
echo "==> NextChapter release build v${VERSION}"

# ---- 0. 从 LOGO 生成图标资源 ----
echo "==> 0. 生成图标资源..."
SOURCE_LOGO="${NC_LOGO:-$ROOT/docs/assets/logo.jpeg}"
bash "$ROOT/scripts/generate-assets.sh" "$SOURCE_LOGO"

# ---- 1. 跑全部测试 ----
echo "==> 1. 跑测试..."
cd "$CORE_PKG"
.venv/bin/python3 -m pytest tests -q

# ---- 2. 打包 sidecar (PyInstaller) ----
echo "==> 2. 打包 sidecar (PyInstaller)..."
.venv/bin/pip install --quiet pyinstaller 2>/dev/null || true
.venv/bin/pyinstaller \
  --noconfirm \
  --clean \
  --distpath "$DIST" \
  --workpath "$DIST/build" \
  "$CORE_PKG/nextchapter-core.spec" 2>&1 | tail -5

# one-folder 模式：产物是 $DIST/nextchapter-core/nextchapter-core（可执行）+ 同目录一堆 .so/.pyc
SIDECAR_DIR="$DIST/nextchapter-core"
SIDECAR_BIN="$SIDECAR_DIR/nextchapter-core"
if [[ ! -x "$SIDECAR_BIN" ]]; then
  echo "❌ PyInstaller 产物缺失：$SIDECAR_BIN" >&2
  exit 1
fi
echo "    ✅ $SIDECAR_BIN ($(du -sh "$SIDECAR_DIR" | cut -f1) total)"

# ---- 3. 构建 macOS app (swift build release) ----
echo "==> 3. 构建 macOS app (swift build -c release)..."
cd "$MACOS"
swift build -c release 2>&1 | tail -3

APP_BINARY="$MACOS/.build/release/NextChapter"
if [[ ! -x "$APP_BINARY" ]]; then
  echo "❌ Swift build 产物缺失：$APP_BINARY" >&2
  exit 1
fi

# ---- 4. 组装 .app bundle ----
echo "==> 4. 组装 .app bundle..."
APP_BUNDLE="$DIST/NextChapter.app"
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# 主二进制
cp "$APP_BINARY" "$APP_BUNDLE/Contents/MacOS/NextChapter"
chmod +x "$APP_BUNDLE/Contents/MacOS/NextChapter"

# sidecar 内嵌到 Resources（one-folder 模式：整个目录复制）
rm -rf "$APP_BUNDLE/Contents/Resources/nextchapter-core"
cp -R "$SIDECAR_DIR" "$APP_BUNDLE/Contents/Resources/nextchapter-core"
chmod +x "$APP_BUNDLE/Contents/Resources/nextchapter-core/nextchapter-core"

# Assets（AppIcon + AppLogo）编译成 Assets.car 放到 Resources
# macOS 不会识别源码格式的 .xcassets，必须用 actool 编译
ASSETS_DIR="$MACOS/NextChapter/Assets.xcassets"
ASSETS_OUT="$APP_BUNDLE/Contents/Resources"
if [ -d "$ASSETS_DIR" ]; then
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
      "$ASSETS_DIR" 2>&1; then
    echo "❌ actool 编译 Asset Catalog 失败" >&2
    rm -rf "$ASSETS_BUILD_DIR" "$ASSETS_PLIST_OUT"
    exit 1
  fi
  if [ ! -f "$ASSETS_BUILD_DIR/Assets.car" ]; then
    echo "❌ actool 没生成 Assets.car" >&2
    rm -rf "$ASSETS_BUILD_DIR" "$ASSETS_PLIST_OUT"
    exit 1
  fi
  cp "$ASSETS_BUILD_DIR/Assets.car" "$ASSETS_OUT/Assets.car"
  if [[ -f "$ASSETS_BUILD_DIR/AppIcon.icns" ]]; then
    cp "$ASSETS_BUILD_DIR/AppIcon.icns" "$ASSETS_OUT/AppIcon.icns"
    echo "    ✅ AppIcon.icns"
  fi
  rm -rf "$ASSETS_BUILD_DIR" "$ASSETS_PLIST_OUT"
  echo "    ✅ Assets.car ($(du -h "$ASSETS_OUT/Assets.car" | cut -f1))"
fi

# SwiftPM 资源包（开发态 Bundle.module 与发布态双保险）
RESOURCE_BUNDLE="$(find "$MACOS/.build" -path "*/release/NextChapter_NextChapter.bundle" -type d 2>/dev/null | head -1)"
if [[ -n "$RESOURCE_BUNDLE" && -d "$RESOURCE_BUNDLE" ]]; then
  rm -rf "$ASSETS_OUT/NextChapter_NextChapter.bundle"
  cp -R "$RESOURCE_BUNDLE" "$ASSETS_OUT/NextChapter_NextChapter.bundle"
  if [[ -f "$ASSETS_OUT/Assets.car" ]]; then
    cp "$ASSETS_OUT/Assets.car" "$ASSETS_OUT/NextChapter_NextChapter.bundle/Assets.car"
  fi
  echo "    ✅ NextChapter_NextChapter.bundle"
fi

# 兜底：generate-assets 预生成的 icns（actool 已生成时跳过）
ICNS_SRC="$MACOS/NextChapter/AppIcon.icns"
if [[ -f "$ICNS_SRC" && ! -f "$ASSETS_OUT/AppIcon.icns" ]]; then
  cp "$ICNS_SRC" "$ASSETS_OUT/AppIcon.icns"
  echo "    ✅ AppIcon.icns (from generate-assets)"
fi

# Info.plist
cat > "$APP_BUNDLE/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>NextChapter</string>
    <key>CFBundleDisplayName</key>
    <string>NextChapter</string>
    <key>CFBundleIdentifier</key>
    <string>com.nextchapter.app</string>
    <key>CFBundleVersion</key>
    <string>__VERSION__</string>
    <key>CFBundleShortVersionString</key>
    <string>__VERSION__</string>
    <key>CFBundleExecutable</key>
    <string>NextChapter</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>CFBundleIconName</key>
    <string>AppIcon</string>
    <key>NSAppTransportSecurity</key>
    <dict>
        <key>NSAllowsLocalNetworking</key>
        <true/>
        <key>NSExceptionDomains</key>
        <dict>
            <key>127.0.0.1</key>
            <dict>
                <key>NSExceptionAllowsInsecureHTTPLoads</key>
                <true/>
                <key>NSIncludesSubdomains</key>
                <true/>
            </dict>
        </dict>
    </dict>
</dict>
</plist>
PLIST
sed -i '' "s/__VERSION__/$VERSION/g" "$APP_BUNDLE/Contents/Info.plist"

# ---- 5. 自检：sidecar 能否从 bundle 内启动 ----
echo "==> 5. 自检 sidecar 二进制..."
if "$APP_BUNDLE/Contents/Resources/nextchapter-core" --help >/dev/null 2>&1 || true; then
  echo "    ✅ sidecar 可执行"
else
  echo "    ⚠️  sidecar 自检失败（首次运行可能正常）"
fi

echo ""
echo "✅ 发布版构建完成！"
echo ""
echo "产物："
echo "  App:        $APP_BUNDLE"
echo "  Sidecar:    $APP_BUNDLE/Contents/Resources/nextchapter-core"
echo ""
echo "启动："
echo "  open $APP_BUNDLE"
echo ""
echo "或直接："
echo "  $APP_BUNDLE/Contents/MacOS/NextChapter"
echo ""
echo "App 启动后会自动检测 sidecar 位置，优先使用 bundle 内嵌版本。"
echo "如果未自动启动，到「设置」面板检查 API Key 是否已填写。"
