# NextChapter 开发命令
# 安装 just: brew install just
# 用法: just <recipe>

# 默认：显示帮助
default:
    @just --list

# ---------- 环境 ----------

# 安装 Python 依赖
install:
    cd packages/nextchapter-core && python3 -m venv .venv
    cd packages/nextchapter-core && .venv/bin/pip install --quiet --upgrade pip
    cd packages/nextchapter-core && .venv/bin/pip install --quiet -e ".[dev]"

# 清理 venv 和 build artifacts
clean:
    rm -rf packages/nextchapter-core/.venv
    rm -rf packages/nextchapter-core/.pytest_cache
    rm -rf packages/nextchapter-core/**/__pycache__
    rm -rf apps/macos/.build
    rm -rf apps/macos/.swiftpm

# ---------- 开发 ----------

# 启动 sidecar（前台）
core:
    cd packages/nextchapter-core && ./scripts/run_dev.sh

# 启动 sidecar（后台），输出到 /tmp/nextchapter-sidecar.log
core-bg:
    cd packages/nextchapter-core && ./scripts/run_dev_bg.sh

# 停止后台 sidecar
core-stop:
    ./scripts/stop-sidecar.sh

# 启动 macOS app（前台，含图标资源编译）
app:
    ./scripts/run-macos.sh debug

# 完整开发启动：后台 sidecar + 前台 app
dev: core-bg
    @echo "==> Sidecar started on http://127.0.0.1:18432"
    @echo "==> Launching macOS app..."
    ./scripts/run-macos.sh debug

# ---------- 测试 ----------

# 单元测试（无 LLM 调用）
test-unit:
    cd packages/nextchapter-core && .venv/bin/python3 -m pytest tests/unit -v

# 端到端测试（mock LLM，不需 API key）
test-e2e:
    cd packages/nextchapter-core && .venv/bin/python3 -m pytest tests/e2e -v

# 全部测试（unit + e2e，不含 live）
test:
    cd packages/nextchapter-core && .venv/bin/python3 -m pytest tests -v

# 真实 LLM 集成测试（需要 NC_LLM_API_KEY）
test-live:
    @if [ -z "$NC_LLM_API_KEY" ]; then echo "❌ 请先设置 NC_LLM_API_KEY"; exit 1; fi
    cd packages/nextchapter-core && .venv/bin/python3 -m pytest tests -m live -v

# 全部测试（包含 live，需要 API key）
test-all: test test-live

# 跑指定测试
test-one pattern:
    cd packages/nextchapter-core && .venv/bin/python3 -m pytest tests -k "{{pattern}}" -v

# ---------- 验证 ----------

# 端到端联通测试：sidecar 真启动 + curl 验证
smoke:
    ./scripts/smoke.sh

# 验证 .app bundle 里的 sidecar 二进制能独立启动 + env 注入正常
verify-sidecar:
    bash scripts/verify-sidecar.sh

# 一键跑完所有静态检查 + 测试
ci: test
    @echo "✅ All tests passed"

# ---------- 构建 ----------

# 编译 macOS app（debug 模式，不打包 .app）
build-app:
    ./scripts/generate-assets.sh
    cd apps/macos && swift build

# 从 logo.jpeg 生成 AppLogo / AppIcon 资源
assets:
    ./scripts/generate-assets.sh

# 打包 .app bundle（需要完整 Xcode）
build-app-bundle:
    ./scripts/build-app.sh

# 构建发布版（PyInstaller 打包 sidecar + Xcode 打包 .app）
release:
    ./scripts/build-release.sh

# ---------- 杂项 ----------

# 端到端跑一次：导入 sample + 风格抽取 + 一致性检查（用 mock LLM）
demo:
    cd packages/nextchapter-core && .venv/bin/python3 scripts/demo_flow.py

# 查看 API 端点列表
api-list:
    @echo "NextChapter Sidecar API (http://127.0.0.1:18432):"
    @echo "  GET  /health"
    @echo "  POST /ingest/path"
    @echo "  POST /ingest/paste"
    @echo "  POST /summarize"
    @echo "  POST /style"
    @echo "  POST /context/build"
    @echo "  POST /continue/plan_turn"
    @echo "  POST /continue/generate"
    @echo "  POST /consistency/check"
