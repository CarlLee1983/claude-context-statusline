// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "AIUsageMonitor",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "AIUsageMonitorCore", targets: ["AIUsageMonitorCore"]),
        .executable(name: "AIUsageMonitorApp", targets: ["AIUsageMonitorApp"]),
    ],
    targets: [
        .target(name: "AIUsageMonitorCore"),
        .executableTarget(name: "AIUsageMonitorApp", dependencies: ["AIUsageMonitorCore"]),
        .testTarget(name: "AIUsageMonitorCoreTests", dependencies: ["AIUsageMonitorCore"]),
        .testTarget(name: "AIUsageMonitorAppTests", dependencies: ["AIUsageMonitorApp"]),
    ]
)
