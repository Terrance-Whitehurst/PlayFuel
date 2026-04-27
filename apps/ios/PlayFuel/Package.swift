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
    targets: [
        .executableTarget(
            name: "PlayFuel",
            path: "Sources/PlayFuel"
        )
    ]
)
