import SwiftUI
import Combine

/// 全局导航状态：当前 tab + 跨视图选中的 bookId。
///
/// 为什么需要：ContinueView 里要提示用户「回书库去给新章节做摘要」，
/// 点提示要能直接跳到 Library 并选中当前这本书。ContentView 的 tab 和
/// selectedBookId 原来都是私有 @State，跨视图只能通过环境对象改。
@MainActor
final class AppNav: ObservableObject {
    @Published var tab: AppTab = .library
    @Published var selectedBookId: String?

    /// 跳到指定 tab，并可选地把对应书选中。
    func go(_ target: AppTab, selectBookId: String? = nil) {
        if let id = selectBookId {
            self.selectedBookId = id
        }
        self.tab = target
    }
}
