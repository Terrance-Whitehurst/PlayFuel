import SwiftUI

/// Reusable bubble button component for the dashboard header row.
///
/// A 44×44pt circle icon button that opens a sheet or triggers an action on tap.
/// Supports an optional badge overlay for contextual values (e.g. temperature).
///
/// Used by `HeaderBubbleRow` to surface Plan Summary and Weather as compact,
/// non-intrusive buttons above the schedule strip.
///
/// HEADER_BUBBLES_V1.md §F.1
struct HeaderBubble: View {

    let systemImage: String
    let label: String
    var badge: String? = nil
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            ZStack(alignment: .topTrailing) {
                Image(systemName: systemImage)
                    .font(.system(size: 18, weight: .medium))
                    .frame(width: 44, height: 44)
                    .foregroundStyle(Color.accentColor)
                    .background(
                        Circle().fill(Color(.systemGray5))
                    )

                if let badge {
                    Text(badge)
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(Color.red, in: Capsule())
                        .offset(x: 12, y: -12)
                }
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityAddTraits(.isButton)
    }
}

#Preview {
    HStack(spacing: 20) {
        HeaderBubble(
            systemImage: "text.bubble.fill",
            label: "Today's Plan",
            action: {}
        )
        HeaderBubble(
            systemImage: "cloud.sun.fill",
            label: "Current Conditions",
            badge: "88°",
            action: {}
        )
    }
    .padding()
}

#Preview("Dark") {
    HStack(spacing: 20) {
        HeaderBubble(
            systemImage: "text.bubble.fill",
            label: "Today's Plan",
            action: {}
        )
        HeaderBubble(
            systemImage: "cloud.sun.fill",
            label: "Current Conditions",
            badge: "88°",
            action: {}
        )
        HeaderBubble(
            systemImage: "map.fill",
            label: "Venue map",
            action: {}
        )
    }
    .padding()
    .preferredColorScheme(.dark)
}
