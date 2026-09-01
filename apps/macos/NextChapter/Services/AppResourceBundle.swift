import Foundation
import SwiftUI

/// 统一解析 SwiftPM 开发态与 .app 发布态的资源 Bundle。
enum AppResourceBundle {
    /// 发布 .app：`Assets.car` 在 `Contents/Resources`（main bundle）。
    /// SwiftPM 开发：`Assets.car` 在 `NextChapter_NextChapter.bundle`（module bundle）。
    static var assets: Bundle {
        if Bundle.main.path(forResource: "Assets", ofType: "car") != nil {
            return .main
        }
        return .module
    }
}

struct AppLogoImage: View {
    var width: CGFloat = 280
    var height: CGFloat = 150
    var opacity: Double = 1

    var body: some View {
        Image("AppLogo", bundle: AppResourceBundle.assets)
            .resizable()
            .scaledToFit()
            .frame(width: width, height: height)
            .opacity(opacity)
    }
}
