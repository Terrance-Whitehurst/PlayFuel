import SwiftUI

/// US-07 — Weather card.
///
/// Shows temperature, humidity, wind, precip, UV, active flags,
/// and the list of plan adjustments derived from those flags (§E.3).
///
/// NUTRITION_FIRST_IA_V1.md §F: Pass `compact: true` on the dashboard to render
/// a 1-line pill (temp + flags + chevron) that expands inline on tap.
/// `compact: false` (default) renders the existing full card body — unchanged.
///
/// SAFETY NOTE: Demoting the weather card's visual prominence does NOT disable
/// any safety logic. `extreme_heat_risk` still drives EmergencyBanner at position
/// #0 regardless of whether WeatherCardView is compact or expanded.
struct WeatherCardView: View {

    let weather: WeatherSnapshot
    var compact: Bool = false

    /// Expansion state for compact mode. Per-session, default collapsed.
    @State private var expanded: Bool = false

    var body: some View {
        if compact {
            compactPillView
        } else {
            fullCardBody
        }
    }

    // MARK: - Compact Pill

    private var compactPillView: some View {
        VStack(spacing: 0) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    expanded.toggle()
                }
            } label: {
                HStack(spacing: 8) {
                    Image(systemName: "thermometer.medium")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(pillSummary)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Image(systemName: expanded ? "chevron.up" : "chevron.down")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
            }
            .buttonStyle(.plain)

            if expanded {
                Divider()
                    .padding(.horizontal, 16)
                fullCardBody
            }
        }
        .background(pillBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .padding(.horizontal, 16)
    }

    /// 1-line pill summary: "°88°F · humid, hot · feels 95°F"
    private var pillSummary: String {
        var parts: [String] = ["❤️ \(Int(weather.tempF))°F"]
        if !weather.flags.isEmpty {
            let flagNames = weather.flags.map { $0.rawValue.replacingOccurrences(of: "_", with: " ") }.joined(separator: ", ")
            parts.append(flagNames)
        }
        // apparentTempF not in the model — omit "feels" segment for now (OQ-IA-W1)
        return parts.joined(separator: " · ")
    }

    private var pillBackground: some View {
        Group {
#if os(iOS)
            Color(.secondarySystemBackground)
#else
            Color.secondary.opacity(0.1)
#endif
        }
    }

    // MARK: - Full Card Body

    @ViewBuilder
    private var fullCardBody: some View {
        VStack(alignment: .leading, spacing: 16) {

            // Header
            HStack {
                Label("Weather", systemImage: "thermometer.sun.fill")
                    .font(.headline)
                Spacer()
                if weather.extremeHeatRisk {
                    Label("EXTREME HEAT", systemImage: "exclamationmark.triangle.fill")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(Color.red)
                        .clipShape(Capsule())
                }
            }

            // Big temperature display
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text("\(Int(weather.tempF))°F")
                    .font(.system(size: 48, weight: .bold, design: .rounded))
                    .foregroundStyle(tempColor)
                Spacer()
                VStack(alignment: .trailing, spacing: 4) {
                    StatBadge(icon: "humidity.fill", value: "\(Int(weather.humidity))%", label: "Humidity")
                    StatBadge(icon: "wind", value: "\(Int(weather.windMph)) mph", label: "Wind")
                    StatBadge(icon: "cloud.drizzle.fill", value: "\(Int(weather.precipProb))%", label: "Rain")
                    if let uv = weather.uvIndex {
                        StatBadge(icon: "sun.max.fill", value: "UV \(Int(uv))", label: "UV Index")
                    }
                }
            }

            // Active flags
            if !weather.flags.isEmpty {
                HStack(spacing: 8) {
                    ForEach(weather.flags, id: \.self) { flag in
                        FlagPill(flag: flag)
                    }
                    if weather.extremeHeatRisk {
                        Text("🔥 extreme heat risk")
                            .font(.caption2.weight(.bold))
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Color.red.opacity(0.15))
                            .foregroundStyle(.red)
                            .clipShape(Capsule())
                    }
                }
                .flexibleWidth()
            }

            Divider()

            // Adjustments
            if !weather.adjustments.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Plan Adjustments")
                        .font(.subheadline.weight(.semibold))

                    ForEach(weather.adjustments, id: \.self) { adjustment in
                        HStack(alignment: .top, spacing: 8) {
                            Image(systemName: "arrow.right.circle.fill")
                                .font(.caption)
                                .foregroundStyle(.orange)
                                .padding(.top, 2)
                            Text(adjustment)
                                .font(.caption)
                                .foregroundStyle(.primary)
                        }
                    }
                }
            }
        }
        .padding(16)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .padding(.horizontal, 16)
    }

    // MARK: - Helpers

    private var tempColor: Color {
        if weather.extremeHeatRisk { return .red }
        if weather.flags.contains(.hot) { return .orange }
        if weather.flags.contains(.cold) { return .blue }
        return .primary
    }
}

// MARK: - Sub-Views

private struct StatBadge: View {
    let icon: String
    let value: String
    let label: String

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.caption2)
                .foregroundStyle(.secondary)
            Text(value)
                .font(.caption.weight(.medium))
        }
    }
}

private struct FlagPill: View {
    let flag: WeatherFlag

    var body: some View {
        Text(flag.rawValue.replacingOccurrences(of: "_", with: " "))
            .font(.caption2.weight(.medium))
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(backgroundColor.opacity(0.15))
            .foregroundStyle(backgroundColor)
            .clipShape(Capsule())
    }

    private var backgroundColor: Color {
        switch flag {
        case .hot, .very_hot: return .orange
        case .humid:          return .teal
        case .cold:           return .blue
        case .windy:          return .gray
        case .rain_risk:      return .indigo
        }
    }
}

// MARK: - Layout helper

private extension View {
    func flexibleWidth() -> some View {
        self.frame(maxWidth: .infinity, alignment: .leading)
    }
}

#Preview {
    ScrollView {
        VStack(spacing: 16) {
            // Compact pill (default on dashboard)
            WeatherCardView(weather: FakeData.dallasWeather, compact: true)
            // Full card (used in standalone weather views)
            WeatherCardView(weather: FakeData.dallasWeather)
        }
        .padding(.vertical, 16)
    }
}
