import XCTest
import SnapshotTesting
import SwiftUI
@testable import PlayFuel

// MARK: - WeatherCardView Snapshot Tests (Phase B)
//
// Purpose: regression net for the °F→°C locale-aware display change.
// These snapshots are recorded AFTER the Phase B metric flip, capturing the
// correct post-flip state. Any future regression (e.g. accidentally reverting
// to hardcoded °F strings) will fail these tests.
//
// Running snapshots:
//   swift test (macOS host): uses NSHostingView rendering — captures correct
//     text content (temperature strings) in macOS-style renders.
//   xcodebuild test -destination "platform=iOS Simulator,name=iPhone 17 Pro":
//     uses UIHostingController — produces pixel-perfect iPhone-style renders.
//     Run this path before Phase C to establish iOS-faithful baselines.
//
// Recording new baselines:
//   Set isRecording = true, run tests once, then revert to false.
//   Or run: swift test with SNAPSHOT_TESTING_RECORD=true env var (v1.17+).
//
// Snapshot files land at:
//   PlayFuelTests/__Snapshots__/WeatherCardViewSnapshotTests/<testName>.png
//
// Phase B note: WeatherSnapshot.adjustments strings remain English-only (Phase C).
// The snapshot shows English adjustment text — this is intentional and will
// change in Phase C when i18n wraps those strings.

final class WeatherCardViewSnapshotTests: XCTestCase {

    // MARK: - Test Fixtures

    /// Hot CDMX summer day: 32°C / 90°F, 65% humidity → extremeHeatRisk = true.
    /// Matches the QA Mexico City scenario spec (QA-INTL-2 corrected to UTC-6 year-round).
    private static let hotDayWeather = WeatherSnapshot(
        tempF: 90,
        tempC: 32.2,
        humidity: 65,
        windMph: 8,
        windKph: 12.9,
        precipProb: 15,
        uvIndex: 10,
        flags: [.very_hot, .humid]
    )

    /// Mild day: 20°C / 68°F, no flags fired. Baseline for default rendering.
    private static let mildDayWeather = WeatherSnapshot(
        tempF: 68,
        tempC: 20.0,
        humidity: 50,
        windMph: 5,
        windKph: 8.0,
        precipProb: 5,
        uvIndex: 4,
        flags: []
    )

    // MARK: - Snapshot Tests

    // -------------------------------------------------------------------------
    // Snapshot 1: Hot day, en-US locale
    // Expected display: "90 °F" temperature (US measurementSystem), "8 mph" wind.
    // EmergencyBanner context fires (very_hot + humid → extremeHeatRisk).
    // -------------------------------------------------------------------------
    func testWeatherCard_hotDay_enUS() {
        let view = WeatherCardView(weather: Self.hotDayWeather)
            .environment(\.locale, Locale(identifier: "en_US"))
            .frame(width: 375)

        #if canImport(AppKit)
        // macOS path (swift test): render via NSHostingView
        let hostingView = NSHostingView(rootView: view)
        hostingView.frame = NSRect(x: 0, y: 0, width: 375, height: 560)
        assertSnapshot(
            of: hostingView,
            as: .image,
            named: "hotDay_enUS"
        )
        #elseif canImport(UIKit)
        // iOS path (xcodebuild test with simulator)
        assertSnapshot(
            of: view,
            as: .image(layout: .fixed(width: 375, height: 560)),
            named: "hotDay_enUS"
        )
        #endif
    }

    // -------------------------------------------------------------------------
    // Snapshot 2: Mild day, en-US locale
    // Expected display: "68 °F" temperature, "5 mph" wind, no flag pills.
    // No EmergencyBanner context — tests the default/normal rendering path.
    // -------------------------------------------------------------------------
    func testWeatherCard_mildDay_enUS() {
        let view = WeatherCardView(weather: Self.mildDayWeather)
            .environment(\.locale, Locale(identifier: "en_US"))
            .frame(width: 375)

        #if canImport(AppKit)
        let hostingView = NSHostingView(rootView: view)
        hostingView.frame = NSRect(x: 0, y: 0, width: 375, height: 380)
        assertSnapshot(
            of: hostingView,
            as: .image,
            named: "mildDay_enUS"
        )
        #elseif canImport(UIKit)
        assertSnapshot(
            of: view,
            as: .image(layout: .fixed(width: 375, height: 380)),
            named: "mildDay_enUS"
        )
        #endif
    }

    // -------------------------------------------------------------------------
    // Snapshot 3: Hot day, es-MX locale  ← KEY Phase B + Phase C prep snapshot
    // Expected display: "32 °C" temperature (metric measurementSystem), "13 km/h" wind.
    // This snapshot proves:
    //   (a) metric-locale devices see °C + km/h (Phase B correctness)
    //   (b) the layout handles metric strings without wrapping/clipping (Phase C prep)
    // When Phase C lands Spanish translations, this snapshot WILL change (adjustment
    // text and labels will appear in Spanish). That diff confirms i18n is working.
    // -------------------------------------------------------------------------
    func testWeatherCard_hotDay_esMX() {
        let view = WeatherCardView(weather: Self.hotDayWeather)
            .environment(\.locale, Locale(identifier: "es_MX"))
            .frame(width: 375)

        #if canImport(AppKit)
        let hostingView = NSHostingView(rootView: view)
        hostingView.frame = NSRect(x: 0, y: 0, width: 375, height: 560)
        assertSnapshot(
            of: hostingView,
            as: .image,
            named: "hotDay_esMX"
        )
        #elseif canImport(UIKit)
        assertSnapshot(
            of: view,
            as: .image(layout: .fixed(width: 375, height: 560)),
            named: "hotDay_esMX"
        )
        #endif
    }

    // -------------------------------------------------------------------------
    // Snapshot 4: Hot day, en-GB locale (UK hybrid Phase B treatment)
    // Expected display: "32 °C" (metric) + "13 km/h" (metric).
    // Phase B treats .uk same as .metric (locale.measurementSystem != .us → metric).
    // Phase C will add a three-toggle Settings override for UK hybrid (°C + mph).
    // When that toggle ships, this snapshot will be updated intentionally.
    // -------------------------------------------------------------------------
    func testWeatherCard_hotDay_enGB() {
        let view = WeatherCardView(weather: Self.hotDayWeather)
            .environment(\.locale, Locale(identifier: "en_GB"))
            .frame(width: 375)

        #if canImport(AppKit)
        let hostingView = NSHostingView(rootView: view)
        hostingView.frame = NSRect(x: 0, y: 0, width: 375, height: 560)
        assertSnapshot(
            of: hostingView,
            as: .image,
            named: "hotDay_enGB"
        )
        #elseif canImport(UIKit)
        assertSnapshot(
            of: view,
            as: .image(layout: .fixed(width: 375, height: 560)),
            named: "hotDay_enGB"
        )
        #endif
    }
}
