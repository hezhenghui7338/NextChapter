#!/usr/bin/env bash
# 打包 macOS .app bundle（debug 模式）。
# 需要：swift + xcrun（macOS 自带）
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/apps/macos"

# 用 xcodebuild 替代 swift build 以生成 .app
# 注意：当前 NextChapter 用 SPM 风格 Package.swift，没有 .xcodeproj
# 这部分在 P2（Xcode 工程化）阶段完善

echo "==> 当前 Swift app 通过 SPM 构建（swift run / swift build）"
echo "==> .app bundle 打包需要先转 Xcode 工程（参考 docs/build.md）"
echo ""
echo "=== 临时方案：直接 build 验证 ==="
swift build
echo ""
echo "✅ Build OK。可执行文件在 .build/debug/NextChapter"
echo "   启动: ./.build/debug/NextChapter"
