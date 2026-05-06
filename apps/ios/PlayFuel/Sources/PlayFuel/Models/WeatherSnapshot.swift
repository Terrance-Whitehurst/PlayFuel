import Foundation

// MARK: - Weather Flag

/// Primary weather flags per RULES_CONSTANTS_V1 §E.1.
/// `extreme_heat_risk` is a *derived* flag computed from these primaries (§E.2).
///
/// Phase B note: flag thresholds remain imperial in the rules engine constants;
/// flags are portable booleans and carry no unit dependency into the iOS model layer.
enum WeatherFlag: String, Codable, CaseIterable {
    case hot           // temp_f >= 85  (29.4°C)
    case very_hot      // temp_f >= 90  (32.2°C)
    case humid         // humidity >= 65%
    case cold          // temp_f <= 50  (10.0°C)
    case windy         // wind_mph >= 15 (24.1 km/h)
    case rain_risk     // precipitation_probability >= 40%
}

// MARK: - WeatherSnapshot

/// Weather conditions at tournament time.
/// Phase 3: decoded from `GET /weather?lat=&lon=` (WeatherKit or OpenWeather).
///
/// Phase B: model now carries both imperial and metric units.
/// `WeatherCardView` uses `@Environment(\.locale)` to select the appropriate unit
/// for display — no branching in the model itself.
struct WeatherSnapshot: Codable, Hashable {

    // MARK: Temperature — both units (Phase B)
    let tempF: Double          // °F — kept for US display and backward compat
    let tempC: Double          // °C — canonical metric; new in Phase B

    let humidity: Double       // percentage, e.g. 72.0

    // MARK: Wind — both units (Phase B)
    let windMph: Double        // mph — kept for US display
    let windKph: Double        // km/h — canonical metric; new in Phase B

    let precipProb: Double     // percentage, e.g. 10.0
    let uvIndex: Double?

    /// Primary flags from classify_weather() — Phase 4 implements this server-side.
    /// In the prototype, FakeData.swift sets these directly.
    let flags: [WeatherFlag]

    // MARK: - Derived Flags (§E.2)

    /// `very_hot OR (hot AND humid)` per RULES_CONSTANTS_V1 §E.2.
    /// When true, `EmergencyBanner` must render on the dashboard.
    var extremeHeatRisk: Bool {
        flags.contains(.very_hot) || (flags.contains(.hot) && flags.contains(.humid))
    }

    // MARK: - Plan Adjustments (§E.3)

    /// Human-readable adjustment lines shown in WeatherCardView.
    /// Phase C: these will be extracted to Localizable.xcstrings and localized.
    /// Phase B scope: still English-only (intentional).
    var adjustments: [String] {
        var lines: [String] = []

        if flags.contains(.hot) || extremeHeatRisk {
            lines.append("Increase hydration frequency during changeovers.")
            lines.append("Electrolyte drink recommended between games.")
            lines.append("Seek shade during all breaks — avoid standing in direct sun.")
            lines.append("Avoid heavy or greasy meals between matches.")
            lines.append("Cool-down routine after match: shade, cool water, rest.")
        }
        if flags.contains(.humid) {
            lines.append("High humidity increases sweat rate — extra electrolytes advised.")
        }
        if flags.contains(.cold) {
            lines.append("Warm fluids acceptable. Maintain hydration schedule.")
        }
        if flags.contains(.windy) {
            // Windy adjustments are deferred per MVP_SCOPE deferrals table; placeholder only.
            lines.append("Windy conditions — mental focus note (tactical guidance deferred).")
        }
        if flags.contains(.rain_risk) {
            lines.append("Rain delay possible — flexible meal timing; pack extra snacks.")
            lines.append("Keep warm, dry clothing at the venue.")
        }
        return lines
    }
}
