# Sign in with Apple — Supabase Configuration Guide

This document describes the full setup chain for Sign in with Apple with Supabase Auth.
The Swift code is Engineering2's responsibility (Task #3); this file documents the
**contract** they need: callback URLs, token flow, and env vars.

---

## 1. Apple Developer Setup

### Step 1.1 — Create an App ID

1. Log in to the [Apple Developer Portal](https://developer.apple.com).
2. Go to **Certificates, Identifiers & Profiles → Identifiers → App IDs**.
3. Register an App ID for the iOS app (e.g. `com.playfuel.app`).
4. Under **Capabilities**, enable **Sign In with Apple**.

### Step 1.2 — Create a Services ID (for web/Supabase callback)

1. Go to **Identifiers → Services IDs → (+)**.
2. Create a Services ID, e.g. `com.playfuel.app.auth`.
3. Enable **Sign In with Apple**.
4. Add the Supabase **callback URL** (see §3) as an authorised **Return URL**.

### Step 1.3 — Create a Private Key

1. Go to **Keys → (+)**.
2. Enable **Sign In with Apple**.
3. Associate it with the App ID from Step 1.1.
4. Download the `.p8` file **once** — it cannot be re-downloaded.
5. Note the **Key ID** (10-character string shown in the portal).

### Step 1.4 — Note Your Team ID

Your Apple Developer Team ID is the 10-character string in the top-right corner of
the Developer Portal.

---

## 2. Env Vars Required

Set these in your Supabase project and locally in `db/supabase/.env` (never commit real values).

| Variable | Description | Example |
|---|---|---|
| `APPLE_SERVICE_ID` | Services ID from Step 1.2 | `com.playfuel.app.auth` |
| `APPLE_TEAM_ID` | Apple Developer Team ID | `AB1CD2EF3G` |
| `APPLE_KEY_ID` | Key ID from Step 1.3 | `XYZABC1234` |
| `APPLE_PRIVATE_KEY_PATH` | Path to .p8 file (local dev) | `./AuthKey_XYZABC1234.p8` |
| `APPLE_REDIRECT_URL` | Supabase callback URL (§3) | `https://<ref>.supabase.co/auth/v1/callback` |

In **Supabase Dashboard** (Authentication → Providers → Apple), enter `APPLE_SERVICE_ID`,
`APPLE_TEAM_ID`, `APPLE_KEY_ID`, and the content of the `.p8` key file directly in the UI.
Do **not** set these via SQL migrations.

---

## 3. Supabase Callback URL

The callback URL that Apple must allowlist (Step 1.2 → Return URL) is:

```
https://<project-ref>.supabase.co/auth/v1/callback
```

Replace `<project-ref>` with your Supabase project reference (visible in the project URL).

For **local development** with the Supabase CLI:
```
http://localhost:54321/auth/v1/callback
```

---

## 4. Supabase Dashboard Provider Config

1. Go to **Authentication → Providers → Apple**.
2. Toggle the provider ON.
3. Enter:
   - **Service ID** (`APPLE_SERVICE_ID`)
   - **Team ID** (`APPLE_TEAM_ID`)
   - **Key ID** (`APPLE_KEY_ID`)
   - **Private Key** (paste the contents of the `.p8` file)
4. Save.

---

## 5. iOS App Flow (Engineering2 contract)

Engineering2 implements the Swift side; this section documents the expected token
exchange so both sides are aligned.

### 5.1 High-level sequence

```
User taps "Sign in with Apple"
  → iOS presents ASAuthorizationAppleIDProvider sheet
  → User authenticates with Face ID / Touch ID
  → Apple returns: identityToken (JWT), authorizationCode, user details (first time only)
  → App calls: supabase.auth.signInWithIdToken(provider: .apple, idToken: identityToken)
  → Supabase verifies identityToken with Apple's public keys
  → Supabase creates auth.users row (or matches existing)
  → on_auth_user_created trigger fires → public.users row created
  → Supabase returns: Session {access_token (JWT), refresh_token, user}
  → App stores session; navigates to tournament list
```

### 5.2 Token the backend verifies

Every API call from the iOS app must include:

```
Authorization: Bearer <access_token>
```

Where `<access_token>` is the Supabase JWT from the session. The FastAPI backend
verifies this JWT against `SUPABASE_JWT_SECRET` (HS256) — see `backend/app/auth/jwt.py`.
The backend extracts `sub` from the JWT as `user_id`; it does **not** trust any
`user_id` field in the request body.

### 5.3 Session persistence

- Store the Supabase session in the iOS Keychain (not UserDefaults).
- Call `supabase.auth.session` on app launch; if valid, skip sign-in screen.
- Use `supabase.auth.refreshSession()` when access token is near expiry.

### 5.4 Sign-out

```swift
try await supabase.auth.signOut()
```

Clears the local session. The Supabase Auth session is invalidated server-side.

---

## 6. Public Users Row

The `on_auth_user_created` trigger (defined in `migrations/0004_auth_trigger.sql`)
automatically creates a `public.users` row on every new auth signup. Engineering2
does **not** need to call a `/users` endpoint after sign-in — the row exists as soon
as the Supabase session is established.

---

## 7. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| "Invalid client_id" from Apple | `APPLE_SERVICE_ID` mismatch | Verify it matches the Services ID in the portal |
| Auth callback returns error | Redirect URL not allowlisted | Add the exact Supabase callback URL to Apple Services ID "Return URLs" |
| `public.users` row not created | Trigger not applied | Run `0004_auth_trigger.sql` and verify with `supabase db reset` |
| JWT verification fails in FastAPI | Wrong `SUPABASE_JWT_SECRET` | Copy the JWT secret from Supabase Dashboard → Settings → API |
