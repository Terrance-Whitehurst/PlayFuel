import Foundation

// MARK: - TournamentFeedback

/// Domain model for a post-tournament feedback submission.
///
/// Mirrors the API's `FeedbackResponse` shape (phase7-feedback-spec.md §C.2).
/// One row per (parent × tournament). UPSERT on resubmission.
///
/// Phase 7 — public.feedback migration 0013.
struct TournamentFeedback: Codable, Identifiable, Hashable {
    let id: UUID
    let tournamentId: UUID
    let planId: UUID?            // nil when no plan existed or plan was deleted (ON DELETE SET NULL)
    let overallRating: Int?      // 1–5; nil when parent submitted chips/text only
    let whatWorked: [String]     // chip tokens from FEEDBACK_CHIP_TOKENS
    let whatDidntWork: [String]  // same token set, "didn't work" context
    let freeText: String?        // optional free-form comment, ≤500 chars
    let createdAt: Date
    let updatedAt: Date
}
