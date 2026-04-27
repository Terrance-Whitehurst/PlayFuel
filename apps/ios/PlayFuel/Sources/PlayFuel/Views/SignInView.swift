import SwiftUI
import AuthenticationServices

/// US-01 — Sign In screen.
///
/// Uses the real `SignInWithAppleButton` for native appearance.
/// Auth is FAKE in Phase 1: tapping the button flips `appState.isAuthenticated = true`.
/// Phase 2: wire to Supabase Auth (Apple identity token exchange).
struct SignInView: View {

    @EnvironmentObject var appState: AppState
    @State private var showingDisclaimer = false

    var body: some View {
        ZStack {
            // Background
            Color(.systemGroupedBackground)
                .ignoresSafeArea()

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

                // Sign in button
                VStack(spacing: 16) {
                    // Real SignInWithAppleButton for native appearance.
                    // Phase 1: onTapGesture overrides auth — just flips the flag.
                    // Phase 2: use .onCompletion handler to send token to Supabase.
                    SignInWithAppleButton(.signIn) { _ in
                        // Phase 2: handle ASAuthorizationAppleIDRequest here
                    } onCompletion: { _ in
                        // Phase 2: decode ASAuthorization credential, send to Supabase
                    }
                    .signInWithAppleButtonStyle(.black)
                    .frame(height: 50)
                    .padding(.horizontal, 40)
                    // Phase 1 fake auth: tap gesture intercepts before real auth flow
                    .onTapGesture {
                        appState.fakeSignIn()
                    }

                    // Disclaimer link (US requirement — SAFETY_DISCLAIMERS §A)
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
    }
}

#Preview {
    SignInView()
        .environmentObject(AppState())
}
