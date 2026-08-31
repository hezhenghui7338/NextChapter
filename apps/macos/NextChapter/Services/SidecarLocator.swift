import Foundation

/// 解析 sidecar 可执行文件路径。
/// 查找优先级（由高到低）：
/// 1. AppSettings.customSidecarPath（用户在设置面板自定义）
/// 2. App Bundle Contents/Resources/nextchapter-core（build-release 嵌入）
/// 3. 项目开发 venv：packages/nextchapter-core/.venv/bin/python3
///
/// 返回 (executable, arguments, workingDirectory) 三元组：
/// - embedded: 直接执行 nextchapter-core 可执行文件
/// - venv: 用 python3 -m nextchapter_core.api.server
enum SidecarLocator {
    struct Resolution {
        let executable: String
        let arguments: [String]
        let workingDirectory: String?
        let mode: String
        let description: String
    }

    /// 把所有可能的查找路径都试一遍，返回第一个找到的。
    static func resolve(customPath: String = "") -> Resolution? {
        // 1. 自定义路径
        if !customPath.isEmpty {
            if FileManager.default.isExecutableFile(atPath: customPath) {
                return Resolution(
                    executable: customPath,
                    arguments: [],
                    workingDirectory: nil,
                    mode: "custom",
                    description: "自定义路径：\(customPath)"
                )
            }
        }

        // 2. Bundle 内嵌（build-release 产物）
        if let embedded = embeddedSidecarPath() {
            return Resolution(
                executable: embedded,
                arguments: [],
                workingDirectory: nil,
                mode: "embedded",
                description: "App bundle 内嵌：\(embedded)"
            )
        }

        // 3. 开发 venv
        if let venv = devVenvPythonPath() {
            let modulePath = devVenvModulePath() ?? ""
            return Resolution(
                executable: venv,
                arguments: ["-m", "nextchapter_core.api.server"],
                workingDirectory: modulePath.isEmpty ? nil : modulePath,
                mode: "venv",
                description: "开发 venv：\(venv)"
            )
        }

        return nil
    }

    /// App bundle 内嵌的 sidecar（build-release 后存在）。
    /// 支持两种模式：
    /// - one-folder: <App>.app/Contents/Resources/nextchapter-core/nextchapter-core
    /// - one-file:   <App>.app/Contents/Resources/nextchapter-core
    static func embeddedSidecarPath() -> String? {
        guard let resourcesURL = Bundle.main.resourceURL else { return nil }
        let candidates = [
            // one-folder：内嵌整个目录
            resourcesURL.appendingPathComponent("nextchapter-core/nextchapter-core").path,
            // one-file：单文件
            resourcesURL.appendingPathComponent("nextchapter-core").path,
            resourcesURL.appendingPathComponent("Resources/nextchapter-core").path,
            resourcesURL.appendingPathComponent("MacOS/nextchapter-core").path,
        ]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    /// 开发 venv 的 python 路径。
    /// 查找策略：从 Bundle.main.bundlePath 向上找含 packages/nextchapter-core/pyproject.toml 的目录。
    static func devVenvPythonPath() -> String? {
        guard let venvRoot = findProjectRoot() else { return nil }
        let candidates = [
            venvRoot + "/packages/nextchapter-core/.venv/bin/python3",
            venvRoot + "/packages/nextchapter-core/.venv/bin/python",
        ]
        return candidates.first { FileManager.default.fileExists(atPath: $0) }
    }

    /// 开发 venv 模块工作目录。
    static func devVenvModulePath() -> String? {
        findProjectRoot()?.appending("/packages/nextchapter-core")
    }

    /// 从 Bundle.main 或 cwd 向上找 NextChapter 项目根（含 packages/nextchapter-core/pyproject.toml）。
    static func findProjectRoot() -> String? {
        // 候选起点：bundle 父目录（开发模式：build 产物在 .build/，父目录是 apps/macos）
        //           cwd（开发模式：swift run 时）
        //           bundle 资源目录（罕见）
        var candidates: [String] = []

        if let bundlePath = Bundle.main.bundlePath.components(separatedBy: "/").dropLast().joined(separator: "/").nilIfEmpty {
            candidates.append(bundlePath)
        }
        candidates.append(FileManager.default.currentDirectoryPath)
        if let resourceURL = Bundle.main.resourceURL {
            candidates.append(resourceURL.path)
        }
        if let executableURL = Bundle.main.executableURL {
            candidates.append(executableURL.deletingLastPathComponent().path)
        }

        for start in candidates {
            if let root = walkUp(start: start, depth: 6) {
                return root
            }
        }
        return nil
    }

    private static func walkUp(start: String, depth: Int) -> String? {
        var dir = start
        for _ in 0...depth {
            if FileManager.default.fileExists(atPath: dir + "/packages/nextchapter-core/pyproject.toml") {
                return dir
            }
            let parent = (dir as NSString).deletingLastPathComponent
            if parent == dir { return nil }
            dir = parent
        }
        return nil
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
