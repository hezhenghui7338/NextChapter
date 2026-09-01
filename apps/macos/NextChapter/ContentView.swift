import SwiftUI
import AppKit

enum AppTab: String, CaseIterable, Identifiable {
    case library
    case continueChapter
    case settings

    var id: String { rawValue }

    var title: String {
        switch self {
        case .library: return "书库"
        case .continueChapter: return "续章"
        case .settings: return "设置"
        }
    }

    var icon: String {
        switch self {
        case .library: return "books.vertical"
        case .continueChapter: return "pencil.and.outline"
        case .settings: return "gearshape"
        }
    }
}

struct ContentView: View {
    @EnvironmentObject private var core: CoreClient
    @EnvironmentObject private var sidecar: SidecarManager
    @EnvironmentObject private var settings: AppSettings
    @StateObject private var bookStore = BookStore()
    @StateObject private var nav = AppNav()
    @State private var importError: String?
    @State private var isImporting = false

    var body: some View {
        Group {
            if sidecar.isBootstrapping {
                bootstrappingView
            } else if let err = sidecar.launchError {
                connectionErrorView(err)
            } else {
                mainTabs
            }
        }
        .frame(minWidth: 1100, minHeight: 700)
        .environmentObject(bookStore)
        .environmentObject(nav)
    }

    private var bootstrappingView: some View {
        VStack(spacing: 20) {
            AppLogoImage(width: 280, height: 150)
            ProgressView()
            Text("正在启动 NextChapter Core…")
                .foregroundStyle(.secondary)
        }
        .padding(40)
    }

    private func connectionErrorView(_ err: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 48))
                .foregroundStyle(.orange)
            Text("无法启动 Python sidecar")
                .font(.title2.bold())
            Text(err)
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 40)
            Button("重试") {
                Task { await sidecar.ensureRunning() }
            }
            .buttonStyle(.borderedProminent)
        }
    }

    private var mainTabs: some View {
        // 桥接 nav.selectedBookId → 各子视图的 @Binding
        let bookIdBinding = Binding<String?>(
            get: { nav.selectedBookId },
            set: { nav.selectedBookId = $0 }
        )
        let importErrBinding = Binding<String?>(
            get: { importError },
            set: { importError = $0 }
        )
        let isImportingBinding = Binding<Bool>(
            get: { isImporting },
            set: { isImporting = $0 }
        )

        return TabView(selection: $nav.tab) {
            LibraryView(selectedBookId: bookIdBinding, importError: importErrBinding, isImporting: isImportingBinding)
                .tabItem { Label(AppTab.library.title, systemImage: AppTab.library.icon) }
                .tag(AppTab.library)

            ContinueView(selectedBookId: bookIdBinding)
                .tabItem { Label(AppTab.continueChapter.title, systemImage: AppTab.continueChapter.icon) }
                .tag(AppTab.continueChapter)

            SettingsView()
                .tabItem { Label(AppTab.settings.title, systemImage: AppTab.settings.icon) }
                .tag(AppTab.settings)
        }
        .onChange(of: sidecar.isBootstrapping) { _, bootstrapping in
            if !bootstrapping { applyDemoEnvironmentIfNeeded() }
        }
        .onAppear {
            if !sidecar.isBootstrapping { applyDemoEnvironmentIfNeeded() }
        }
    }

    /// 录屏 / 演示脚本可通过环境变量定位初始 Tab 与书目（见 docs/SUBMISSION.md）。
    private func applyDemoEnvironmentIfNeeded() {
        if let raw = ProcessInfo.processInfo.environment["NC_DEMO_TAB"] {
            switch raw.lowercased() {
            case "settings": nav.tab = .settings
            case "continue", "continuechapter", "续章": nav.tab = .continueChapter
            default: nav.tab = .library
            }
        }
        if let bookId = ProcessInfo.processInfo.environment["NC_DEMO_BOOK"], !bookId.isEmpty {
            nav.selectedBookId = bookId
        }
    }
}
