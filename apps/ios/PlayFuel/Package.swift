// swift-tools-version: 5.9
// PlayFuel — Phase 1 Static Prototype
// iOS 17+, SwiftUI, zero external dependencies, zero networking.
// All data comes from Sources/PlayFuel/Data/FakeData.swift.
//
// PATH DEVIATION NOTE:
//   spec/PLAN.md targets `ios/PlayFuel/`. This package lives at
//   `apps/ios/PlayFuel/` because the Frontend Dev write domain is
//   restricted to `apps/`. Semantics are identical; Phase 3 wiring
//   remains a single-file swap (FakeData.swift → real API client).

import PackageDescription

let package = Package(
    name: "PlayFuel",
    platforms: [
        .iOS(.v17)
    ],
    dependencies: [
        // Phase B — snapshot test infrastructure.
        // Test-only: linked to PlayFuelTests only, not the main app target.
        // Version 1.x is the stable API; pinned to >=1.17.4 for Swift 5.9 compatibility.
        // Run snapshots via: swift test (macOS NSHostingView renders)
        // For pixel-perfect iPhone renders: xcodebuild test -destination "platform=iOS Simulator,name=iPhone 17 Pro"
        .package(
            url: "https://github.com/pointfreeco/swift-snapshot-testing.git",
            from: "1.17.4"
        ),
    ],
    targets: [
        // Main library target — all Views, Models, Helpers, Data.
        // Changed from executableTarget → target (library) so the test
        // target can @testable import PlayFuel.
        // iOS app entry point is managed by PlayFuel.xcodeproj (xcodegen),
        // not by `swift run`, so this change has no impact on the app build.
        // SCENARIO_CARD_POPOUT_V1.md §G.1 — test target support.
        .target(
            name: "PlayFuel",
            path: "Sources/PlayFuel"
        ),
        // Unit tests — pure Swift helpers (no SwiftUI rendering).
        // Run via: swift test (from apps/ios/PlayFuel/)
        //
        // Phase B adds SwiftUI snapshot tests via SnapshotTesting:
        //   - On macOS (swift test): snapshots use NSHostingView rendering.
        //   - On iOS simulator (xcodebuild test): snapshots use UIHostingController rendering.
        // See PlayFuelTests/WeatherCardViewSnapshotTests.swift for baseline snapshots.
        .testTarget(
            name: "PlayFuelTests",
            dependencies: [
                "PlayFuel",
                .product(name: "SnapshotTesting", package: "swift-snapshot-testing"),
            ],
            path: "PlayFuelTests"
        )
    ]
)
