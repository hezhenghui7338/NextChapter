import SwiftUI
import AppKit

struct SettingsView: View {
    @EnvironmentObject private var settings: AppSettings
    @EnvironmentObject private var sidecar: SidecarManager
    @State private var showAPIKey = false
    @State private var testResult: String?
    @State private var isTesting = false

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Spacer()
                Image("AppLogo")
                    .resizable()
                    .scaledToFit()
                    .frame(width: 200, height: 108)
                Spacer()
            }
            .padding(.bottom, 16)

            Form {
                Section("云端 LLM") {
                Picker("Provider", selection: $settings.llmProvider) {
                    Text("DeepSeek").tag("deepseek")
                    Text("OpenAI 兼容").tag("openai")
                    Text("Anthropic").tag("anthropic")
                }
                HStack {
                    if showAPIKey {
                        TextField("API Key", text: $settings.llmAPIKey)
                    } else {
                        SecureField("API Key", text: $settings.llmAPIKey)
                    }
                    Button(showAPIKey ? "隐藏" : "显示") { showAPIKey.toggle() }
                }
                TextField("Base URL", text: $settings.llmBaseURL)
                TextField("Model", text: $settings.llmModel)
                HStack {
                    Text("超时")
                    Slider(value: $settings.llmTimeout, in: 30...600, step: 30)
                    Text("\(Int(settings.llmTimeout))s").monospacedDigit().frame(width: 50, alignment: .trailing)
                }
                Text("API key 存储于 macOS UserDefaults（仅本机）。")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("上下文窗口（25 章分级）") {
                Stepper("最近细摘要：\(settings.recentCount) 章", value: $settings.recentCount, in: 1...15)
                Stepper("中期粗摘要：\(settings.middleCount) 章", value: $settings.middleCount, in: 0...20)
                Stepper("远端极简：\(settings.farCount) 章", value: $settings.farCount, in: 0...20)
            }

            Section("反 AI 味") {
                Picker("强度", selection: $settings.antiAIPreset) {
                    Text("默认").tag("default")
                    Text("强烈").tag("strong")
                    Text("轻度").tag("mild")
                }
            }

            Section("sidecar") {
                Toggle("使用外部 sidecar（不自动启动）", isOn: $settings.useExternalSidecar)
                HStack {
                    Text("自定义路径")
                    TextField("留空则自动检测", text: $settings.customSidecarPath)
                        .textFieldStyle(.roundedBorder)
                    Button("选择…") { pickSidecarPath() }
                }
                .disabled(settings.useExternalSidecar)

                HStack {
                    Text("监听地址")
                    TextField("host", text: $settings.sidecarHost)
                        .frame(width: 140)
                    TextField("port", value: $settings.sidecarPort, format: .number)
                        .frame(width: 70)
                }
                HStack {
                    Text("当前模式：")
                    Text(sidecar.resolvedMode).font(.system(.body, design: .monospaced))
                    Spacer()
                    if let err = sidecar.launchError {
                        Text(err).foregroundStyle(.red).font(.caption)
                    }
                    Button("重启") { sidecar.restart() }
                }
            }

            Section("连通测试") {
                HStack {
                    Button {
                        Task { await testLLM() }
                    } label: {
                        if isTesting { ProgressView() } else { Text("测试 LLM") }
                    }
                    .disabled(isTesting || settings.llmAPIKey.isEmpty)
                    if let r = testResult {
                        Text(r).font(.caption).foregroundStyle(r.hasPrefix("✅") ? .green : .red)
                    }
                }
            }
            }
        }
        .padding(20)
        .frame(maxWidth: 720, alignment: .topLeading)
    }

    private func pickSidecarPath() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = false
        panel.treatsFilePackagesAsDirectories = true
        panel.message = "选择 sidecar 可执行文件（nextchapter-core 或 python3）"
        if panel.runModal() == .OK, let url = panel.url {
            settings.customSidecarPath = url.path
        }
    }

    private func testLLM() async {
        isTesting = true
        defer { isTesting = false }
        testResult = nil
        do {
            // 简单调用 /health 看 sidecar 是否在跑 + LLM 能不能用
            let url = sidecar.baseURL.appendingPathComponent("health")
            let (_, resp) = try await URLSession.shared.data(from: url)
            guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
                testResult = "❌ sidecar 未运行"
                return
            }
            testResult = "✅ sidecar 正常，配置已就绪"
        } catch {
            testResult = "❌ \(error.localizedDescription)"
        }
    }
}
