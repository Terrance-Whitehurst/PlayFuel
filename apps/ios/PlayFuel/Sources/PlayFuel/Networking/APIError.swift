import Foundation

/// Typed errors surfaced by APIClient and Repository.
enum APIError: Error, Equatable, LocalizedError {
    case unauthorized                  // 401 — signed out / refresh failed
    case forbidden                     // 403 — RLS denial
    case notFound                      // 404 — resource missing
    case server(statusCode: Int)       // 5xx and unmapped 4xx
    case decoding(String)              // JSON decode failed (message = type name + cause)
    case transport(String)             // URLSession-level failure (message = localizedDescription)
    case invalidResponse               // Non-HTTPURLResponse came back

    var errorDescription: String? {
        switch self {
        case .unauthorized:
            return "You've been signed out. Please sign in again."
        case .forbidden:
            return "You don't have access to that."
        case .notFound:
            return "Not found."
        case .server(let code):
            return "Server error (\(code)). Try again in a moment."
        case .decoding(let what):
            return "Couldn't read response (\(what))."
        case .transport(let message):
            return "Network error: \(message)"
        case .invalidResponse:
            return "Unexpected response from server."
        }
    }

    static func == (lhs: APIError, rhs: APIError) -> Bool {
        switch (lhs, rhs) {
        case (.unauthorized, .unauthorized),
             (.forbidden, .forbidden),
             (.notFound, .notFound),
             (.invalidResponse, .invalidResponse):
            return true
        case (.server(let a), .server(let b)):
            return a == b
        case (.decoding(let a), .decoding(let b)):
            return a == b
        case (.transport(let a), .transport(let b)):
            return a == b
        default:
            return false
        }
    }
}
