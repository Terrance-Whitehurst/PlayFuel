import SwiftUI

// MARK: - Glass system
// Reusable glassmorphic surfaces. Translucent material + subtle white stroke +
// soft shadow + thin top-edge highlight for the lit-from-above feel.
//
// Pattern: ButtonStyle.makeBody returns a concrete named View struct rather
// than `some View` directly. Swift 5.9 can't always infer ButtonStyle.Body from
// a complex modifier chain; a named Body type sidesteps the inference failure.
//
// OQ-GLASS-1: accessibilityReduceTransparency path deferred — not wired in this
// revision. Cards and banners always use .ultraThinMaterial. Follow-up task.

// MARK: - GlassButtonStyle

/// Lightweight glass button: ultraThinMaterial fill + optional tint overlay +
/// top-lit white stroke gradient + press-scale feedback.
struct GlassButtonStyle: ButtonStyle {
    var tint: Color? = nil
    var cornerRadius: CGFloat = 14

    func makeBody(configuration: ButtonStyleConfiguration) -> GlassButtonBody {
        GlassButtonBody(configuration: configuration, tint: tint, cornerRadius: cornerRadius)
    }
}

struct GlassButtonBody: View {
    let configuration: ButtonStyleConfiguration
    let tint: Color?
    let cornerRadius: CGFloat

    var body: some View {
        configuration.label
            .padding(.horizontal, 16)
            .padding(.vertical, 10)
            .background(background)
            .foregroundStyle(Color.primary)
            .shadow(color: Color.black.opacity(0.18), radius: 12, x: 0, y: 6)
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .opacity(configuration.isPressed ? 0.85 : 1)
            .animation(.easeOut(duration: 0.15), value: configuration.isPressed)
    }

    private var background: some View {
        ZStack {
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .fill(.ultraThinMaterial)
            if let tint = tint {
                RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                    .fill(tint.opacity(0.22))
            }
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .strokeBorder(
                    LinearGradient(
                        colors: [.white.opacity(0.45), .white.opacity(0.08)],
                        startPoint: .top,
                        endPoint: .bottom
                    ),
                    lineWidth: 1
                )
        }
    }
}

// MARK: - GlassProminentButtonStyle

/// Primary CTA glass button: regularMaterial + tint overlay (32% opacity) +
/// top-lit white stroke gradient + white label + press-scale feedback.
/// Use for the main action on each screen (e.g. "View Full Day Timeline").
struct GlassProminentButtonStyle: ButtonStyle {
    var tint: Color = Color.accentColor
    var cornerRadius: CGFloat = 16

    func makeBody(configuration: ButtonStyleConfiguration) -> GlassProminentButtonBody {
        GlassProminentButtonBody(configuration: configuration, tint: tint, cornerRadius: cornerRadius)
    }
}

struct GlassProminentButtonBody: View {
    let configuration: ButtonStyleConfiguration
    let tint: Color
    let cornerRadius: CGFloat

    var body: some View {
        configuration.label
            .font(.body.weight(.semibold))
            .padding(.horizontal, 20)
            .padding(.vertical, 12)
            .background(background)
            .foregroundStyle(Color.white)
            .shadow(color: tint.opacity(0.35), radius: 14, x: 0, y: 8)
            .scaleEffect(configuration.isPressed ? 0.97 : 1)
            .opacity(configuration.isPressed ? 0.9 : 1)
            .animation(.easeOut(duration: 0.15), value: configuration.isPressed)
    }

    private var background: some View {
        ZStack {
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .fill(.regularMaterial)
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .fill(tint.opacity(0.32))
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .strokeBorder(
                    LinearGradient(
                        colors: [.white.opacity(0.55), .white.opacity(0.10)],
                        startPoint: .top,
                        endPoint: .bottom
                    ),
                    lineWidth: 1
                )
        }
    }
}

// MARK: - GlassPillButtonStyle

/// Compact capsule button for secondary inline actions.
/// Used by: FoodOptionCard "Menu Suggestions", ScenarioCardView "See suggestions"
/// via the GlassPillButtonStyle when using .buttonStyle().
struct GlassPillButtonStyle: ButtonStyle {
    var tint: Color = Color.accentColor

    func makeBody(configuration: ButtonStyleConfiguration) -> GlassPillButtonBody {
        GlassPillButtonBody(configuration: configuration, tint: tint)
    }
}

struct GlassPillButtonBody: View {
    let configuration: ButtonStyleConfiguration
    let tint: Color

    var body: some View {
        configuration.label
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(background)
            .foregroundStyle(Color.white)
            .shadow(color: tint.opacity(0.30), radius: 8, x: 0, y: 4)
            .scaleEffect(configuration.isPressed ? 0.96 : 1)
            .opacity(configuration.isPressed ? 0.85 : 1)
            .animation(.easeOut(duration: 0.13), value: configuration.isPressed)
    }

    private var background: some View {
        ZStack {
            Capsule()
                .fill(.ultraThinMaterial)
            Capsule()
                .fill(tint.opacity(0.30))
            Capsule()
                .strokeBorder(
                    LinearGradient(
                        colors: [.white.opacity(0.50), .white.opacity(0.08)],
                        startPoint: .top,
                        endPoint: .bottom
                    ),
                    lineWidth: 1
                )
        }
    }
}

// MARK: - GlassCardModifier

/// Applies glassmorphic card surface to any view:
/// ultraThinMaterial fill + top-lit white stroke gradient + soft drop shadow.
struct GlassCardModifier: ViewModifier {
    var cornerRadius: CGFloat = 20
    var padding: CGFloat = 16

    func body(content: Content) -> some View {
        content
            .padding(padding)
            .background(cardBackground)
            .shadow(color: Color.black.opacity(0.12), radius: 14, x: 0, y: 8)
    }

    private var cardBackground: some View {
        ZStack {
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .fill(.ultraThinMaterial)
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .strokeBorder(
                    LinearGradient(
                        colors: [.white.opacity(0.40), .white.opacity(0.06)],
                        startPoint: .top,
                        endPoint: .bottom
                    ),
                    lineWidth: 1
                )
        }
    }
}

extension View {
    /// Wraps a view in the shared glassmorphic card surface.
    func glassCard(cornerRadius: CGFloat = 20, padding: CGFloat = 16) -> some View {
        modifier(GlassCardModifier(cornerRadius: cornerRadius, padding: padding))
    }
}
