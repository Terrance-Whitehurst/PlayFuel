import Foundation

/// Build-time configuration constants.
///
/// All three values must be set before running against a live backend. Reads
/// from process environment first (Xcode scheme env vars are convenient for
/// dev), then falls back to compile-time placeholders that will fail loudly
/// at the first network call. Production builds will inject via xcconfig /
/// build settings; see `apps/ios/PlayFuel/README.md` → Configuration.
enum Configuration {

    /// PlayFuel FastAPI base URL. Phase 1 default = local dev server on port 8000.
    static let apiBaseURL: URL = {
        if let raw = ProcessInfo.processInfo.environment["PLAYFUEL_API_BASE_URL"],
           let url = URL(string: raw) {
            return url
        }
        return URL(string: "https://playfuel-api.fly.dev")!
    }()

    /// Supabase project URL, e.g. https://abcdefgh.supabase.co
    static let supabaseURL: URL = {
        let raw = ProcessInfo.processInfo.environment["SUPABASE_URL"]
            ?? "https://YOUR_PROJECT.supabase.co"
        return URL(string: raw)!
    }()

    /// Supabase anon (publishable) key. Required as `apikey` header on Auth calls.
    static let supabaseAnonKey: String =
        ProcessInfo.processInfo.environment["SUPABASE_ANON_KEY"] ?? "YOUR_ANON_KEY"
}
