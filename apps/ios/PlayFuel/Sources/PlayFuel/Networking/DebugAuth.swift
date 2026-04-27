#if DEBUG
import Foundation
import CryptoKit

/// DEBUG-only auth bypass for simulator testing without configuring Apple's
/// Sign in with Apple provider on the local Supabase Auth server.
///
/// Mints an HS256-signed JWT for the seeded test user (`demo@playfuel.app`,
/// id `a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11`) using the local Supabase JWT
/// secret. The minted token is byte-compatible with what Supabase Auth would
/// have issued, so APIClient + the FastAPI backend's `verify_supabase_jwt`
/// accept it transparently.
///
/// Excluded from Release builds at the language level (`#if DEBUG`).
/// Disabled at runtime if `DEBUG_JWT_SECRET` env var is missing — fail-safe.
enum DebugAuth {

    static let testUserId    = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
    static let testUserEmail = "demo@playfuel.app"

    /// Returns the JWT secret if available; nil disables the bypass at runtime.
    static var jwtSecret: String? {
        ProcessInfo.processInfo.environment["DEBUG_JWT_SECRET"]
    }

    /// Mint and store a Supabase-compatible session for the test user.
    /// Returns false if `DEBUG_JWT_SECRET` is unset.
    @MainActor
    @discardableResult
    static func signInAsTestUser(authService: AuthService) -> Bool {
        guard let secret = jwtSecret else { return false }
        let token = mintHS256JWT(
            secret: secret,
            sub: testUserId,
            email: testUserEmail,
            ttlSeconds: 24 * 3600
        )
        KeychainStore.set(token, for: KeychainStore.Keys.accessToken)
        // No refresh token — on 401, app will sign out and user re-taps.
        KeychainStore.delete(KeychainStore.Keys.refreshToken)
        authService.notifyDebugSignIn()
        return true
    }

    private static func mintHS256JWT(
        secret: String,
        sub: String,
        email: String,
        ttlSeconds: Int
    ) -> String {
        let header: [String: Any] = ["alg": "HS256", "typ": "JWT"]
        let now = Int(Date().timeIntervalSince1970)
        let payload: [String: Any] = [
            "sub":   sub,
            "email": email,
            "role":  "authenticated",
            "aud":   "authenticated",
            "iss":   "supabase-demo",
            "iat":   now,
            "exp":   now + ttlSeconds,
        ]
        let h = try! JSONSerialization.data(withJSONObject: header, options: [.sortedKeys])
        let p = try! JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
        let input = "\(h.base64URL()).\(p.base64URL())"
        let key = SymmetricKey(data: Data(secret.utf8))
        let mac = HMAC<SHA256>.authenticationCode(for: Data(input.utf8), using: key)
        return "\(input).\(Data(mac).base64URL())"
    }
}

private extension Data {
    func base64URL() -> String {
        base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }
}
#endif
