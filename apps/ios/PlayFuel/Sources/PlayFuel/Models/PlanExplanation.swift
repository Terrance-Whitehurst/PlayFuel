import Foundation

/// Structured LLM-generated (or TemplateProvider-generated) explanation of a Plan.
/// Mirrors the API's `PlanExplanation` Pydantic model (Phase 6 / Task #9).
///
/// Safety guarantee: every field's content must originate from the structured
/// `PlanExplanationInput` — the LLM/template never invents restaurants,
/// weather facts, or schedule logic (SAFETY_DISCLAIMERS §E / PRD §2).
///
/// `safetyNote` always contains the verbatim §A disclaimer. When `extreme_heat_risk`
/// was true at generation time, the §B emergency text is prepended verbatim.
struct PlanExplanation: Codable, Hashable, Sendable {

    /// 2–4 sentence parent-friendly intro summarising the plan.
    let summary: String

    /// Per-scenario explanations keyed by "short", "normal", "long".
    let scenarioExplanations: [String: String]

    /// 1–2 sentences on weather adjustments; nil when no weather data available.
    let weatherNote: String?

    /// 1–2 sentences on food picks; nil when bag_fallback_only.
    let foodNote: String?

    /// Always present. Contains §A disclaimer verbatim. When extreme_heat_risk,
    /// §B emergency text is prepended verbatim.
    let safetyNote: String

    /// Provider that produced this explanation: "template" | "anthropic" | "openai".
    let provider: String

    /// Model identifier (e.g. "claude-haiku-3-5"). Nil for the template provider.
    let model: String?

    /// When this explanation was generated (decoded from ISO 8601 via camelDecoder).
    let generatedAt: Date

    init(
        summary: String,
        scenarioExplanations: [String: String],
        weatherNote: String?,
        foodNote: String?,
        safetyNote: String,
        provider: String,
        model: String?,
        generatedAt: Date
    ) {
        self.summary = summary
        self.scenarioExplanations = scenarioExplanations
        self.weatherNote = weatherNote
        self.foodNote = foodNote
        self.safetyNote = safetyNote
        self.provider = provider
        self.model = model
        self.generatedAt = generatedAt
    }
}
