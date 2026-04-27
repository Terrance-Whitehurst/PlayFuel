import SwiftUI
import AuthenticationServices

/// US-01 — Sign In screen.
///
/// Task #6: wired to real Sign in with Apple → Supabase id_token grant via
/// `AuthService.signIn(with:)`. The tap gesture fake-auth from Phase 1 is removed.
///
/// NOTE — OQ-iOS-1: Full SIWA flow on device requires the "Sign In with Apple"
/// capability declared in an Xcode project. This Swift Package cannot declare
/// entitlements. For device testing, wrap in an .xcodeproj with the capability.
/// Simulator previews and simulator runs work without it.
struct SignInView: View {

    @EnvironmentObject var appState: AppState
    @State private var showingDisclaimer = false
    @State private var errorMessage: String? = nil
    @State private var isExchanging = false

    var body: some View {
        ZStack {
            Color(.systemGroupedBackground).ignoresSafeArea()

            VStack(spacing: 0) {
                Spacer()

                // App identity
                VStack(spacing: 12) {
                    Image(systemName: "tennis.racket")
                        .font(.system(size: 64))
                        .foregroundStyle(.green)

                    Text("PlayFuel")
                        .font(.largeTitle.bold())

                    Text("Tournament-day planning for junior tennis parents")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 40)
                }

                Spacer()

                // Sign in controls
                VStack(spacing: 16) {
                    SignInWithAppleButton(.signIn) { request in
                        request.requestedScopes = [.fullName, .email]
                    } onCompletion: { result in
                        Task { await handle(result) }
                    }
                    .signInWithAppleButtonStyle(.black)
                    .frame(height: 50)
                    .padding(.horizontal, 40)
                    .disabled(isExchanging)

                    if isExchanging {
                        ProgressView()
                            .padding(.top, 4)
                    }

                    #if DEBUG
                    if DebugAuth.jwtSecret != nil {
                        Button {
                            _ = DebugAuth.signInAsTestUser(authService: appState.authService)
                        } label: {
                            Text("Skip Auth (DEBUG)")
                                .font(.footnote.weight(.medium))
                                .frame(maxWidth: .infinity)
                                .frame(height: 40)
                                .background(.orange.opacity(0.15))
                                .foregroundStyle(.orange)
                                .clipShape(RoundedRectangle(cornerRadius: 8))
                        }
                        .padding(.horizontal, 40)
                    }
                    #endif

                    // Disclaimer link — §A placement requirement
                    Button {
                        showingDisclaimer = true
                    } label: {
                        Text("By continuing you accept our ")
                            .foregroundStyle(.secondary)
                        + Text("usage guidelines")
                            .foregroundStyle(.blue)
                    }
                    .font(.caption)
                }
                .padding(.bottom, 48)
            }
        }
        .sheet(isPresented: $showingDisclaimer) {
            DisclaimerView()
        }
        .alert("Sign-in failed", isPresented: Binding(
            get: { errorMessage != nil },
            set: { if !$0 { errorMessage = nil } }
        )) {
            Button("OK", role: .cancel) { errorMessage = nil }
        } message: {
            Text(errorMessage ?? "")
        }
    }

    // MARK: - Apple credential handler

    private func handle(_ result: Result<ASAuthorization, Error>) async {
        switch result {
        case .failure(let err):
            // User cancelled: ASAuthorizationError.canceled — swallow silently.
            if (err as? ASAuthorizationError)?.code == .canceled { return }
            errorMessage = err.localizedDescription

        case .success(let auth):
            guard let cred = auth.credential as? ASAuthorizationAppleIDCredential else {
                errorMessage = "Unexpected credential type from Apple."
                return
            }
            isExchanging = true
            defer { isExchanging = false }
            do {
                try await appState.authService.signIn(with: cred)
                // appState.isAuthenticated flips via the Combine bridge in AppState.
            } catch {
                errorMessage = (error as? LocalizedError)?.errorDescription
                    ?? error.localizedDescription
            }
        }
    }
}

#Preview {
    // Preview uses stub AppState — no real auth round-trip needed.
    let auth = AuthService()
    let api  = APIClient(authService: auth)
    let repo = Repository(api: api)
    return SignInView()
        .environmentObject(AppState(repository: repo, authService: auth))
}
