import Foundation
import AuthenticationServices

/// Auth service: bridges Sign in with Apple → Supabase id_token grant → Keychain.
///
/// Owns `isSignedIn` so `RootView` can route between `SignInView` and the main
/// `NavigationStack` reactively via Combine.
///
/// Auth flow:
///   1. Apple returns `ASAuthorizationAppleIDCredential` with `identityToken`.
///   2. `signIn(with:)` POSTs the id_token to Supabase Auth v1 token endpoint.
///   3. Supabase issues a JWT access_token + refresh_token.
///   4. Tokens stored in Keychain. `isSignedIn` flips to true.
///   5. `APIClient` reads `currentAccessToken` from Keychain on every /v1/* call.
///   6. On 401: `APIClient` calls `refresh()`, retries once.
///   7. If refresh fails: `signOut()` clears Keychain + flips isSignedIn to false.
///
/// NOTE — OQ-iOS-1: Sign in with Apple requires the `Sign In with Apple`
/// capability in an Xcode project (.xcodeproj). This Swift Package cannot
/// declare entitlements. For full device testing, wrap this package in an
/// Xcode project with the capability enabled. Simulator flow works without it.
@MainActor
final class AuthService: ObservableObject {

    @Published private(set) var isSignedIn: Bool

    private let session: URLSession
    private let supabaseURL: URL
    private let anonKey: String

    init(
        session: URLSession = .shared,
        supabaseURL: URL = Configuration.supabaseURL,
        anonKey: String = Configuration.supabaseAnonKey
    ) {
        self.session = session
        self.supabaseURL = supabaseURL
        self.anonKey = anonKey
        // Re-hydrate sign-in state from Keychain (survives app restart).
        self.isSignedIn = KeychainStore.get(KeychainStore.Keys.accessToken) != nil
    }

    /// Current access token (synchronous Keychain read). nil when signed out.
    var currentAccessToken: String? {
        KeychainStore.get(KeychainStore.Keys.accessToken)
    }

    // MARK: - Sign in with Apple → Supabase id_token grant

    /// Exchange an Apple identity token for a Supabase session.
    /// Throws `APIError` if the credential is malformed, network fails, or Supabase rejects.
    func signIn(with appleCredential: ASAuthorizationAppleIDCredential) async throws {
        guard let tokenData = appleCredential.identityToken,
              let idToken = String(data: tokenData, encoding: .utf8)
        else {
            throw APIError.decoding("ASAuthorizationAppleIDCredential.identityToken missing or unreadable")
        }

        var req = URLRequest(
            url: supabaseURL.appendingPathComponent("auth/v1/token")
                .appending(queryItems: [URLQueryItem(name: "grant_type", value: "id_token")])
        )
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(anonKey, forHTTPHeaderField: "apikey")
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "provider": "apple",
            "id_token": idToken,
        ])

        try await exchange(req: req)
    }

    /// Refresh the session using the stored refresh_token.
    /// Throws `.unauthorized` if the refresh token is absent or rejected.
    func refresh() async throws {
        guard let refreshToken = KeychainStore.get(KeychainStore.Keys.refreshToken) else {
            throw APIError.unauthorized
        }
        var req = URLRequest(
            url: supabaseURL.appendingPathComponent("auth/v1/token")
                .appending(queryItems: [URLQueryItem(name: "grant_type", value: "refresh_token")])
        )
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(anonKey, forHTTPHeaderField: "apikey")
        req.httpBody = try JSONSerialization.data(withJSONObject: [
            "refresh_token": refreshToken,
        ])
        try await exchange(req: req)
    }

    #if DEBUG
    /// DEBUG hook: flip published flag after `DebugAuth` writes a session
    /// directly to Keychain. No-op in Release builds (entire branch excluded).
    func notifyDebugSignIn() {
        self.isSignedIn = true
    }
    #endif

    /// Sign out: clear Keychain tokens and flip published flag.
    func signOut() {
        KeychainStore.delete(KeychainStore.Keys.accessToken)
        KeychainStore.delete(KeychainStore.Keys.refreshToken)
        isSignedIn = false
    }

    // MARK: - Internal token exchange

    private struct SupabaseSession: Decodable {
        let access_token: String
        let refresh_token: String
    }

    private func exchange(req: URLRequest) async throws {
        let (data, resp): (Data, URLResponse)
        do {
            (data, resp) = try await session.data(for: req)
        } catch {
            throw APIError.transport(error.localizedDescription)
        }
        guard let http = resp as? HTTPURLResponse else { throw APIError.invalidResponse }
        guard (200..<300).contains(http.statusCode) else {
            // 400 / 401 from Supabase Auth = credential rejected
            if http.statusCode == 400 || http.statusCode == 401 {
                throw APIError.unauthorized
            }
            throw APIError.server(statusCode: http.statusCode)
        }
        do {
            let session = try JSONDecoder().decode(SupabaseSession.self, from: data)
            KeychainStore.set(session.access_token, for: KeychainStore.Keys.accessToken)
            KeychainStore.set(session.refresh_token, for: KeychainStore.Keys.refreshToken)
            self.isSignedIn = true
        } catch {
            throw APIError.decoding("SupabaseSession")
        }
    }
}
