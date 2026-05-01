# Auth Debug Brief — TestFlight 401 / Forced Sign-Out Loop

> **For:** Agent team / engineer picking up the auth debug ticket.
> **Branch to work on:** `release/testflight-1` (do not push to `main`).
> **Build affected:** TestFlight build 5, `com.playfuel.ios` 0.1.0 (5).
> **Status:** Blocking the on-device beta. Step 5 smoke-test cannot proceed until this is resolved.

---

## Symptoms

Reproduced on a real iPhone, fresh TestFlight install:

- Sign in with Apple completes; the app lands on **My Tournaments** OK.
- Creating a tournament returns an error; the row never appears in the list.
- Re-launching the app — or sometimes just tapping an existing tournament — shows an error and signs the user back out.
- Behavior is identical for singles and doubles tournament creation.
- Consistent across cold launch, warm launch, and after airplane-mode toggles.

---

## Stack snapshot

| Layer | What it is |
|---|---|
| **iOS app** | `apps/ios/PlayFuel` — Swift. Native SIWA via `ASAuthorizationAppleIDProvider`. Calls Supabase Auth directly with `signInWithIdToken`. After sign-in, calls FastAPI at `https://playfuel-api.fly.dev/v1/*` with `Authorization: Bearer <JWT>`. |
| **Backend** | `apps/api` — FastAPI on Fly.io. Validates Supabase JWTs in `apps/api/src/playfuel_api/auth.py` with `algorithms=["HS256"]` against env `SUPABASE_JWT_SECRET`, currently set on Fly to the **legacy** Supabase HS256 secret (Project Settings → JWT Keys → Legacy). |
| **Supabase** | Hosted project ref `vxiunrpjvamspeecbriu`. Has both the new asymmetric (RS256/ES256) keys **and** the legacy HS256 secret enabled. Apple provider: native flow only, `com.playfuel.ios` in Client IDs, no Services ID. |
| **iOS auth flow** | `apps/ios/PlayFuel/Sources/PlayFuel/Networking/AuthService.swift` + `SignInView.swift`. Token storage in `Sources/PlayFuel/Networking/` (Keychain wrapper). |
| **iOS config** | `Configuration.swift` fallbacks now point at the hosted Supabase URL + publishable anon key. Sign-in completes, so the iOS layer is reaching Supabase Auth correctly. |

---

## Hypotheses (in order of likelihood)

1. **Backend rejects every JWT.** Supabase issues RS256/ES256 tokens from the asymmetric keys, but `auth.py` validates HS256 only — every authenticated call returns 401 → iOS interprets as session expired → clears Keychain → kicks back to Sign In.
2. **iOS sign-out path is too aggressive.** `AuthService` / `APIClient` may unconditionally clear Keychain on any 401, even ones that aren't auth-related — that turns a single failed POST into a forced sign-out.
3. **No refresh-token path on iOS.** Supabase access tokens default to 1 h. No refresh path means everything works for ~1 hour after sign-in, then dies. Probably not the *primary* issue here (failures are immediate), but worth confirming for the follow-up.
4. **RLS rejecting writes.** If the JWT is accepted but `user_id` doesn't match `auth.uid()`, the row silently doesn't appear. Less likely given the forced-sign-out symptom, but possible if some endpoints succeed and others 401.

---

## Diagnostic steps, in order

### 1. Decode a fresh issued JWT

Have a tester sign in. Capture the access token from one of:

- Supabase Studio → Authentication → Users → tester → "Edit user" / view session
- `supabase auth admin list-users` from a CLI session linked to the project
- Or: stick a `print()` in `AuthService.swift` after `decode(SessionEnvelope.self)` and re-archive a debug build

Decode the token at [jwt.io](https://jwt.io) (or `jwt decode <token>` from `pyjwt`).

**Inspect the header.** Specifically `alg` and `kid`:

| `alg` value | Meaning |
|---|---|
| `HS256` | Backend's current validation works — issue is elsewhere. |
| `RS256` / `ES256` | **Confirmed Hypothesis 1.** Backend can't validate. Move to JWKS migration. |

### 2. Reproduce the 401 server-side

```bash
curl -i -H "Authorization: Bearer <token>" https://playfuel-api.fly.dev/v1/tournaments
flyctl logs --app playfuel-api   # in a second terminal
```

Capture the server-side rejection reason. Typical messages:

- `Signature verification failed` → wrong secret or wrong algorithm.
- `Token has expired` → access token TTL exceeded; refresh-token issue.
- `Invalid audience` / `Invalid issuer` → claim mismatch; check `aud` and `iss` in the decoded payload vs. what `auth.py` enforces.

### 3. Audit the iOS sign-out trigger

Find where the iOS layer reacts to 401 responses. Look in:

- `AuthService.swift`
- `APIClient.swift` (or whichever class wraps `URLSession.shared.data`)
- Any interceptor / middleware that watches HTTP status codes

Check: does **any** 401 clear the Keychain and route to Sign In? It probably should distinguish:

- `401` from `/auth/v1/token` (Supabase auth endpoint) → genuine auth failure, sign out.
- `401` from `/v1/*` (FastAPI) → could be expired token; try refresh first, only sign out if refresh also fails.

### 4. Confirm refresh-token handling

Does the app store the `refresh_token` from the Supabase session envelope? Does it ever call `POST /auth/v1/token?grant_type=refresh_token`? If neither, document the gap and plan to add it — but it's not the *immediate* fix.

---

## Done criteria

- A `curl` with a fresh JWT against `https://playfuel-api.fly.dev/v1/tournaments` returns **200** and a JSON body.
- POSTing a tournament via the app — it appears in the list.
- Force-quit + relaunch — lands on Tournaments **without** re-signing in. Keychain token persists.
- Waiting past the access-token expiry (~70 min) either continues to work (refresh path implemented) or fails gracefully with a "session expired" message — not a forced sign-out.

---

## Branch strategy

Branch **off** `release/testflight-1`, not directly on it. Do your work on a topic branch (e.g. `fix/auth-jwks`), open a PR back into `release/testflight-1`, and let the owner review + merge before re-archiving for TestFlight.

**Mental model for this repo:**

| Branch | Role | What lives here |
|---|---|---|
| `main` | Local-sim development | `Configuration.swift` fallbacks point at `localhost` / `127.0.0.1`. Local Supabase + local FastAPI. |
| `release/testflight-1` | Live TestFlight beta | `Configuration.swift` fallbacks point at `https://playfuel-api.fly.dev` and the hosted Supabase project. Every TestFlight build is a commit here. Long-lived until the beta wraps. |
| `fix/*`, `feat/*` (off `release/testflight-1`) | In-progress work | Topic branches for substantive changes. Merge back via PR. |

Do **not** push to `main`. Do **not** push directly to `release/testflight-1` — go through a PR so the diff is reviewable before it ships to testers.

## Other constraints

- **Don't mock Supabase or the database in tests.** Project rule from a prior incident — mocked tests passed while a real prod migration broke.
- **If the fix is JWKS validation in `auth.py`** (likely): treat it as **Ticket B** from [`NEXT_STEPS.md`](./NEXT_STEPS.md). Specifically:
  - Fetch keys from `https://vxiunrpjvamspeecbriu.supabase.co/auth/v1/.well-known/jwks.json`
  - Cache by `kid` with TTL (1 h is fine)
  - Support both `HS256` (legacy fallback) and `RS256` / `ES256` during the cutover window
  - Tests cover both algorithms against real tokens, not mocked
- **Re-archiving:** bump `CFBundleVersion` in `apps/ios/PlayFuel/project.yml` for every TestFlight upload. Run `xcodegen` after any `project.yml` edit.

---

## Out of scope

- App icon work — resolved in commit `b5e46b4`.
- Backend hosting setup — resolved earlier on `release/testflight-1`.
- The `.env` files tracked in git history — separate ticket; rotate keys + untrack.
- Step 5 smoke-test execution — gated on this fix.

---

## Deliverable

Report root cause + a short diff. **Do not deploy without owner approval.**
