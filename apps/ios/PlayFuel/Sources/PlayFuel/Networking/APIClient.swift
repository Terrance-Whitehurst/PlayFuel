import Foundation

/// HTTP client for the PlayFuel FastAPI backend.
///
/// Responsibilities:
///   - Injects `Authorization: Bearer <token>` from AuthService on every /v1/* call.
///   - On 401: calls `AuthService.refresh()` and retries the original request ONCE.
///   - If the retry also 401s (or refresh throws): calls `AuthService.signOut()` and
///     throws `.unauthorized` so the RootView routes back to SignInView.
///   - Decodes JSON using either snake_case or camelCase strategy (caller chooses).
///
/// Key contract — ONE refresh retry maximum. There is NO infinite retry loop.
@MainActor
final class APIClient {

    let baseURL: URL
    private let session: URLSession
    private weak var authService: AuthService?

    // Two decoders — caller picks based on the endpoint's key convention.
    private let snakeDecoder: JSONDecoder  // .convertFromSnakeCase — DB-shaped endpoints
    private let camelDecoder: JSONDecoder  // no conversion — Pydantic aliased endpoints

    init(
        baseURL: URL = Configuration.apiBaseURL,
        session: URLSession = .shared,
        authService: AuthService
    ) {
        self.baseURL = baseURL
        self.session = session
        self.authService = authService

        let snake = JSONDecoder()
        snake.keyDecodingStrategy = .convertFromSnakeCase
        snake.dateDecodingStrategy = .iso8601
        self.snakeDecoder = snake

        let camel = JSONDecoder()
        camel.dateDecodingStrategy = .iso8601
        self.camelDecoder = camel
    }

    // MARK: - Key Strategy

    /// Determines which JSONDecoder the client uses for a given request.
    enum KeyStrategy {
        /// DB-shaped endpoints (/v1/me, /v1/tournaments CRUD, /v1/matches CRUD).
        /// API returns snake_case from raw Postgres rows.
        case snake
        /// Pydantic-aliased endpoints (/v1/tournaments/{tid}/plans/generate).
        /// API returns camelCase via `alias_generator=to_camel`.
        case camel
    }

    // MARK: - Send

    /// Send a request and decode the response body as `T`.
    func send<T: Decodable>(
        _ request: URLRequest,
        as keyStrategy: KeyStrategy,
        expecting: T.Type,
        requiresAuth: Bool = true
    ) async throws -> T {
        let data = try await sendData(request, requiresAuth: requiresAuth)
        let decoder = (keyStrategy == .snake) ? snakeDecoder : camelDecoder
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decoding("\(T.self): \(error.localizedDescription)")
        }
    }

    /// Send a request expecting an empty/ignored body (e.g. DELETE → 204).
    func sendNoContent(_ request: URLRequest, requiresAuth: Bool = true) async throws {
        _ = try await sendData(request, requiresAuth: requiresAuth)
    }

    // MARK: - Private

    private func sendData(_ request: URLRequest, requiresAuth: Bool) async throws -> Data {
        var req = request
        if requiresAuth, let token = authService?.currentAccessToken {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let (data, resp) = try await executeRequest(req)

        guard let status = (resp as? HTTPURLResponse)?.statusCode else {
            throw APIError.invalidResponse
        }

        switch status {
        case 200..<300:
            return data
        case 401:
            guard requiresAuth, let auth = authService else {
                throw APIError.unauthorized
            }
            // ONE refresh + ONE retry. No loops.
            do {
                try await auth.refresh()
                var retry = request
                if let token = auth.currentAccessToken {
                    retry.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
                }
                let (data2, resp2) = try await executeRequest(retry)
                if let http2 = resp2 as? HTTPURLResponse, (200..<300).contains(http2.statusCode) {
                    return data2
                }
                // Second attempt failed — sign out and propagate.
                auth.signOut()
                throw APIError.unauthorized
            } catch let apiErr as APIError {
                auth.signOut()
                throw apiErr
            } catch {
                auth.signOut()
                throw APIError.unauthorized
            }
        case 403:
            throw APIError.forbidden
        case 404:
            throw APIError.notFound
        default:
            throw APIError.server(statusCode: status)
        }
    }

    private func executeRequest(_ request: URLRequest) async throws -> (Data, URLResponse) {
        do {
            return try await session.data(for: request)
        } catch {
            throw APIError.transport(error.localizedDescription)
        }
    }
}
