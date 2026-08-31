import Foundation
import Darwin
import AppKit

/// 负责启动 / 停止 / 监控 Python sidecar 子进程。
/// 关键依赖：
/// - AppSettings：env 变量来源（API key、provider、model、port）
/// - SidecarLocator：可执行文件路径解析
@MainActor
final class SidecarManager: ObservableObject {
    @Published var isRunning = false
    @Published var isBootstrapping = false
    @Published var userStopped = false
    @Published var launchError: String?
    @Published var resolvedMode: String = "—"

    private var process: Process?
    private let settings: AppSettings
    private let maxLaunchAttempts = 3
    private let healthPollAttempts = 60
    private let healthPollDelayNs: UInt64 = 500_000_000  // 0.5s
    /// 与 Python sidecar `API_FEATURES` 对齐；缺任一即视为旧版
    private let requiredSidecarFeatures = ["plan_draft", "plan_revise", "critique"]

    private struct HealthResponse: Decodable {
        let status: String
        let features: [String]?
        let llm_configured: Bool?
    }

    init(settings: AppSettings) {
        self.settings = settings
    }

    deinit {
        process?.terminate()
    }

    // MARK: - 公共 API

    var baseURL: URL {
        URL(string: "http://\(settings.sidecarHost):\(settings.sidecarPort)")!
    }

    /// 异步确保 sidecar 在跑。
    func ensureRunning() async {
        if isBootstrapping { return }
        if isRunning { return }
        isBootstrapping = true
        defer { isBootstrapping = false }

        // 1) 探测端口（health 正常且 API 能力齐全才复用）
        if await probeCompatibleSidecar() {
            isRunning = true
            resolvedMode = "external (already running)"
            return
        }

        // 1b) 端口上有不兼容 sidecar（旧版 / 未注入 API Key）→ 非「外部模式」时自动重启
        if !settings.useExternalSidecar, await probeHealth() != nil {
            print("[NextChapter] 检测到不兼容 sidecar（旧版或缺少 API Key），正在重启…")
            terminateProcessOnPort(settings.sidecarPort)
            try? await Task.sleep(nanoseconds: 500_000_000)
        }

        // 2) 如果用户明确选了「外部 sidecar」，不自动启动
        if settings.useExternalSidecar {
            if await probeHealth() != nil {
                launchError = """
                外部 sidecar 版本过旧，缺少 AI 规划续写所需接口（plan_draft / plan_revise）。
                请在 packages/nextchapter-core 目录重启 sidecar：
                  source .venv/bin/activate && python -m nextchapter_core.api.server
                """
            } else {
                launchError = "已启用「外部 sidecar」模式但 \(settings.sidecarHost):\(settings.sidecarPort) 无响应。请先手动启动 sidecar。"
            }
            return
        }

        // 3) 解析可执行文件路径
        guard let resolution = SidecarLocator.resolve(customPath: settings.customSidecarPath) else {
            launchError = """
            找不到 sidecar 可执行文件。请检查以下任一来源：
            1. App Bundle 内嵌（build-release 后自动）：<App>.app/Contents/Resources/nextchapter-core
            2. 项目开发 venv：packages/nextchapter-core/.venv/bin/python3
            3. 设置面板中「自定义 sidecar 路径」
            """
            return
        }
        resolvedMode = resolution.mode
        print("[NextChapter] sidecar mode: \(resolution.mode) — \(resolution.description)")

        // 4) 启动
        for attempt in 1...maxLaunchAttempts {
            do {
                try launchProcess(resolution: resolution)
                if await waitForHealth() {
                    isRunning = true
                    launchError = nil
                    return
                }
                process?.terminate()
                process = nil
            } catch {
                launchError = "启动失败 (attempt \(attempt))：\(error.localizedDescription)"
                print("[NextChapter] launch error: \(error)")
            }
        }
        if launchError == nil {
            launchError = "sidecar 启动后无响应（30 秒内 /health 未返回 200）。请检查 LLM 配置（API key 等）。"
        }
    }

    func stop() {
        process?.terminate()
        process = nil
        isRunning = false
        userStopped = true
    }

    func restart() {
        stop()
        if !settings.useExternalSidecar {
            terminateProcessOnPort(settings.sidecarPort)
        }
        isRunning = false
        userStopped = false
        Task { await ensureRunning() }
    }

    // MARK: - internals

    private func probeCompatibleSidecar() async -> Bool {
        guard let health = await probeHealth(), health.status == "ok" else { return false }
        let features = Set(health.features ?? [])
        guard requiredSidecarFeatures.allSatisfy({ features.contains($0) }) else { return false }
        // 不复用未注入 API Key 的 sidecar（常见于手动 run_dev 启动的 dev 进程）
        return health.llm_configured == true
    }

    private func probeHealth() async -> HealthResponse? {
        let url = baseURL.appendingPathComponent("health")
        var req = URLRequest(url: url)
        req.timeoutInterval = 1.0
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard (resp as? HTTPURLResponse)?.statusCode == 200 else { return nil }
            return try JSONDecoder().decode(HealthResponse.self, from: data)
        } catch {
            return nil
        }
    }

    private func probe() async -> Bool {
        await probeCompatibleSidecar()
    }

    private func waitForHealth() async -> Bool {
        for _ in 0..<healthPollAttempts {
            if await probeCompatibleSidecar() { return true }
            try? await Task.sleep(nanoseconds: healthPollDelayNs)
        }
        return false
    }

    /// 释放 sidecar 占用的端口（仅用于自动重启旧进程）。
    private func terminateProcessOnPort(_ port: Int) {
        let task = Process()
        task.executableURL = URL(fileURLWithPath: "/bin/sh")
        task.arguments = ["-c", "lsof -ti :\(port) | xargs kill 2>/dev/null || true"]
        try? task.run()
        task.waitUntilExit()
    }

    private func launchProcess(resolution: SidecarLocator.Resolution) throws {
        // 先校验 LLM 配置
        if let err = settings.validateLLM() {
            throw NSError(
                domain: "NextChapter", code: 10,
                userInfo: [NSLocalizedDescriptionKey: err]
            )
        }

        let p = Process()
        p.executableURL = URL(fileURLWithPath: resolution.executable)
        p.arguments = resolution.arguments
        if let cwd = resolution.workingDirectory {
            p.currentDirectoryURL = URL(fileURLWithPath: cwd)
        }

        // env 合并：系统环境 + AppSettings 注入（覆盖 NC_*）
        var env = ProcessInfo.processInfo.environment
        for (k, v) in settings.envOverrides() {
            env[k] = v
        }
        // 确保 PATH 里有 python（venv 模式需要）
        if resolution.mode == "venv" {
            env["PATH"] = (env["PATH"] ?? "") + ":\(resolution.executable.components(separatedBy: "/").dropLast().joined(separator: "/"))"
        }
        p.environment = env

        let outPipe = Pipe()
        let errPipe = Pipe()
        p.standardOutput = outPipe
        p.standardError = errPipe

        // 实时打印 sidecar 日志到 NSLog
        outPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if let s = String(data: data, encoding: .utf8), !s.isEmpty {
                print("[sidecar:out] \(s.trimmingCharacters(in: .whitespacesAndNewlines))")
            }
        }
        errPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if let s = String(data: data, encoding: .utf8), !s.isEmpty {
                print("[sidecar:err] \(s.trimmingCharacters(in: .whitespacesAndNewlines))")
            }
        }

        p.terminationHandler = { proc in
            print("[NextChapter] sidecar terminated: exit=\(proc.terminationStatus)")
        }

        do {
            try p.run()
            process = p
        } catch {
            throw NSError(
                domain: "NextChapter", code: 2,
                userInfo: [NSLocalizedDescriptionKey: "无法启动进程 \(resolution.executable)：\(error.localizedDescription)"]
            )
        }
    }
}
