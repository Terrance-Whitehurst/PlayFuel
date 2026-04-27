import Foundation

/// Authenticated user record. Populated from GET /v1/me.
/// Phase 3: wired to real Supabase `public.users` row via Repository.fetchMe().
struct User: Codable, Identifiable {

    /// Supabase `auth.users.id` — stable UUID for the authenticated user.
    let id: UUID
}
