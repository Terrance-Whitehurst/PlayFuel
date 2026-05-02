import Foundation

// MARK: - FeedbackChipVocab
//
// Swift mirror of `apps/api/src/playfuel_api/rules/feedback.py`.
// MUST stay in sync with FEEDBACK_CHIPS_WORKED in that file.
//
// Tokens are SYMMETRIC: the same 7 tokens are valid in both "What Worked"
// and "What Didn't Work" chip groups. The meaning (helped vs. didn't help)
// is conveyed by which array the token is stored in, NOT by the token itself.
//
// Token set locked at v1; add new tokens to both this file and feedback.py
// simultaneously. See phase7-feedback-spec.md §D.2.

/// Ordered chip token list for both `what_worked` and `what_didnt_work` fields.
/// Order is deterministic for consistent chip grid rendering.
///
/// MUST stay in sync with apps/api/src/playfuel_api/rules/feedback.py FEEDBACK_CHIPS_WORKED.
let FEEDBACK_CHIP_TOKENS: [String] = [
    "food_timing",
    "hydration",
    "warmup_timing",
    "scenario_planning",
    "food_recs",
    "weather_forecast",
    "schedule",
]

/// Human-readable display labels for feedback chip tokens.
/// Rendered in TournamentFeedbackView chip groups.
///
/// MUST stay in sync with the token list above.
let FEEDBACK_CHIP_LABELS: [String: String] = [
    "food_timing":       "Food Timing",
    "hydration":         "Hydration Advice",
    "warmup_timing":     "Warm-Up Timing",
    "scenario_planning": "Scenario Planning",
    "food_recs":         "Food Recommendations",
    "weather_forecast":  "Weather Forecast",
    "schedule":          "Schedule",
]
