// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "NextChapter",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "NextChapter", targets: ["NextChapter"]),
    ],
    targets: [
        .executableTarget(
            name: "NextChapter",
            path: "NextChapter",
            exclude: ["README.md", "Resources"],
            resources: [
                .process("Assets.xcassets"),
                .copy("AppIcon.icns"),
            ],
            linkerSettings: [
                .linkedFramework("AppKit"),
            ]
        ),
    ]
)
