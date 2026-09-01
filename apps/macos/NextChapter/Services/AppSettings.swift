import Foundation
import SwiftUI

/// 全局设置。所有字段用 @AppStorage 持久化到 UserDefaults（API key 明文存，本地用）。
/// 关键点：API key 等敏感配置**只在这里**，不依赖系统环境变量。
@MainActor
final class AppSettings: ObservableObject {
    // ---- LLM 配置（云端） ----

    @AppStorage("nc.llm.provider") var llmProvider: String = "deepseek"
    @AppStorage("nc.llm.apiKey") var llmAPIKey: String = ""
    @AppStorage("nc.llm.baseURL") var llmBaseURL: String = "https://api.deepseek.com/v1"
    @AppStorage("nc.llm.model") var llmModel: String = "deepseek-chat"
    @AppStorage("nc.llm.timeout") var llmTimeout: Double = 180
    @AppStorage("nc.llm.antiAI") var antiAIPreset: String = "default"

    // ---- 上下文窗口 ----

    @AppStorage("nc.context.recent") var recentCount: Int = 5
    @AppStorage("nc.context.middle") var middleCount: Int = 10
    @AppStorage("nc.context.far") var farCount: Int = 10

    // ---- sidecar ----

    /// 是否使用外部 sidecar（true = 不自动启动，假设用户已自己跑了一个）
    @AppStorage("nc.sidecar.external") var useExternalSidecar: Bool = false

    /// 自定义 sidecar 路径（空 = 自动检测：bundle 内嵌 → 项目 .venv）
    @AppStorage("nc.sidecar.customPath") var customSidecarPath: String = ""

    /// sidecar 监听地址（一般不用改）
    @AppStorage("nc.sidecar.host") var sidecarHost: String = "127.0.0.1"
    @AppStorage("nc.sidecar.port") var sidecarPort: Int = 18432

    /// sidecar 启动方式："auto" / "embedded" / "venv" / "external"
    /// 只读，根据上面字段自动推断
    var sidecarMode: String {
        if useExternalSidecar { return "external" }
        if !customSidecarPath.isEmpty { return "custom" }
        if SidecarLocator.embeddedSidecarPath() != nil { return "embedded" }
        if SidecarLocator.devVenvPythonPath() != nil { return "venv" }
        return "auto"
    }

    /// 把当前 LLM + sidecar 配置导出为 sidecar 启动时用的环境变量集合。
    /// **这是 sidecar 拿 API key 的唯一来源**。
    /// 注意：修改这些设置后需要重启 sidecar 才能生效（点 Settings 里的「重启」）。
    func envOverrides() -> [String: String] {
        let env: [String: String] = [
            "NC_LLM_PROVIDER": llmProvider,
            "NC_LLM_API_KEY": llmAPIKey,
            "NC_LLM_BASE_URL": llmBaseURL,
            "NC_LLM_MODEL": llmModel,
            "NC_LLM_TIMEOUT": String(Int(llmTimeout)),
            "NC_ANTI_AI_PRESET": antiAIPreset,
            "NC_CONTEXT_RECENT": String(recentCount),
            "NC_CONTEXT_MIDDLE": String(middleCount),
            "NC_CONTEXT_FAR": String(farCount),
            "NC_HOST": sidecarHost,
            "NC_PORT": String(sidecarPort),
        ]
        return env
    }

    /// 校验 LLM 配置完整性。
    func validateLLM() -> String? {
        if llmAPIKey.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return "API Key 未设置。请到「设置」面板填写。"
        }
        if llmBaseURL.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return "Base URL 不能为空。"
        }
        if llmModel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return "Model 名称不能为空。"
        }
        return nil
    }
}
