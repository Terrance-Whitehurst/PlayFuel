import Foundation
import Security

/// Minimal Keychain wrapper for credential strings (access + refresh tokens).
/// Uses kSecClassGenericPassword. Service identifier = bundle ID; account = key name.
///
/// Tokens are security-sensitive credentials. NEVER use UserDefaults for tokens.
enum KeychainStore {

    private static let service: String =
        Bundle.main.bundleIdentifier ?? "com.playfuel.app"

    // MARK: - CRUD

    /// Persist a string under `key`. Overwrites any existing value.
    @discardableResult
    static func set(_ value: String, for key: String) -> Bool {
        guard let data = value.data(using: .utf8) else { return false }
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(query as CFDictionary)  // idempotent delete before insert
        var attrs = query
        attrs[kSecValueData as String] = data
        // Available after first device unlock; survives backgrounding but not device wipe.
        attrs[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        return SecItemAdd(attrs as CFDictionary, nil) == errSecSuccess
    }

    /// Read the stored string for `key`, or nil if absent or malformed.
    static func get(_ key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String:  true,
            kSecMatchLimit as String:  kSecMatchLimitOne,
        ]
        var item: AnyObject?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data,
              let str = String(data: data, encoding: .utf8)
        else { return nil }
        return str
    }

    /// Remove the stored value for `key`. No-op if absent.
    static func delete(_ key: String) {
        let query: [String: Any] = [
            kSecClass as String:       kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(query as CFDictionary)
    }

    // MARK: - Key Constants

    enum Keys {
        static let accessToken  = "com.playfuel.access_token"
        static let refreshToken = "com.playfuel.refresh_token"
    }
}
