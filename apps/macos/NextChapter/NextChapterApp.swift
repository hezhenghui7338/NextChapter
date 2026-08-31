import SwiftUI
import AppKit

@main
struct NextChapterApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    @StateObject private var settings = AppSettings()
    @StateObject private var sidecar: SidecarManager
    @StateObject private var core: CoreClient

    init() {
        let s = AppSettings()
        _settings = StateObject(wrappedValue: s)
        _sidecar = StateObject(wrappedValue: SidecarManager(settings: s))
        let url = URL(string: "http://127.0.0.1:18432")!
        _core = StateObject(wrappedValue: CoreClient(baseURL: url))
    }

    var body: some Scene {
        Window("NextChapter", id: "main") {
            ContentView()
                .environmentObject(sidecar)
                .environmentObject(core)
                .environmentObject(settings)
                .onAppear {
                    appDelegate.sidecar = sidecar
                }
        }
        .defaultSize(width: 1200, height: 800)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    weak var sidecar: SidecarManager?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // SwiftPM 编译的 app 不会自动加载 Dock 图标，主动设置
        if NSApp.applicationIconImage == nil || NSApp.applicationIconImage?.size == .zero {
            if let named = NSImage(named: "AppIcon"), named.size != .zero {
                NSApp.applicationIconImage = named
            } else if let url = Bundle.main.url(forResource: "AppIcon", withExtension: "icns"),
                      let icon = NSImage(contentsOf: url), icon.size != .zero {
                NSApp.applicationIconImage = icon
            }
        }
        Task { @MainActor in
            await sidecar?.ensureRunning()
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        sidecar?.stop()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        true
    }
}
