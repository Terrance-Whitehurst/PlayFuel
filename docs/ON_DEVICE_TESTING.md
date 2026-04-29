# On-Device Testing — Getting PlayFuel on Two iPhones

> **Goal:** You and your wife both have PlayFuel installed on real iPhones and can run the full Dallas demo at an actual tournament, across multiple weekends, without touching a laptop.
>
> **Audience:** Project owner. Technically capable. Wants a sequenced checklist, not a research dump.
>
> **Related docs:** [`apps/api/README.md`](../apps/api/README.md) · [`db/supabase/README.md`](../db/supabase/README.md) · [`apps/ios/PlayFuel/README.md`](../apps/ios/PlayFuel/README.md)

---

> ✅ **Apple Developer Program enrollment confirmed** (team `G89TZ927TJ`). No sign-up needed — the $99 account is already active and the team ID is already wired into `project.yml`.

---

## Table of Contents

1. [Step 0 — Sanity check the local dev loop](#step-0--sanity-check-the-local-dev-loop)
2. [Step 1 — Distribution: TestFlight](#step-1--distribution-testflight)
3. [Step 2 — Backend hosting](#step-2--backend-hosting)
4. [Step 3 — iOS signing and build](#step-3--ios-signing-and-build)
5. [Step 4 — Sign in with Apple on real device](#step-4--sign-in-with-apple-on-real-device)
6. [Step 5 — On-device smoke-test checklist](#step-5--on-device-smoke-test-checklist)
7. [Cutover summary](#cutover-summary)

---

## Step 0 — Sanity check the local dev loop

> **Do not skip this.** If Step 0 fails, nothing downstream matters. The entire deployment path assumes the local loop works.

### 0a. Supabase stack

```bash
supabase status
```

Expected output includes `API URL: http://127.0.0.1:54321` and a `JWT secret`. If not running:

```bash
supabase start
supabase db reset   # applies all migrations + Dallas demo seed
```

See [`db/supabase/README.md`](../db/supabase/README.md) for full local Supabase setup.

### 0b. FastAPI backend

```bash
grep -E 'SUPABASE_URL|SUPABASE_ANON_KEY|SUPABASE_JWT_SECRET' apps/api/.env

cd apps/api
uvicorn playfuel_api.main:app --reload --port 8000
```

Expected: `Uvicorn running on http://127.0.0.1:8000`

### 0c. Verify from terminal

```bash
curl -i http://localhost:8000/healthz
# Expected: HTTP/1.1 200  {"status":"ok","rules_version":"..."}

curl -i http://localhost:8000/v1/tournaments
# Expected: HTTP/1.1 401  (server up, auth required — correct)
```

### 0d. Simulator smoke test

1. Open `apps/ios/PlayFuel/` in Xcode. If `PlayFuel.xcodeproj` is absent: `cd apps/ios/PlayFuel && xcodegen`.
2. Select the iPhone simulator, hit ▶.
3. Sign in → My Tournaments should load without a network error (empty list is fine).
4. **If "Could not connect" persists after starting uvicorn:** confirm the scheme sets `PLAYFUEL_API_BASE_URL=http://127.0.0.1:8000` in `project.yml`.

✅ **Step 0 done when:** `curl /healthz` returns 200 and the simulator reaches the Tournaments screen.

---

## Step 1 — Distribution: TestFlight

TestFlight is the distribution path. Builds last 90 days, your wife installs from an email link with no cable, and Sign in with Apple works cleanly against a stable paid-team bundle ID.

### 1a. Verify your team in the portals

- **Apple Developer portal:** [developer.apple.com/account](https://developer.apple.com/account) → confirm team `G89TZ927TJ` is active.
- **App Store Connect:** [appstoreconnect.apple.com](https://appstoreconnect.apple.com) → this is where you manage builds and testers.

### 1b. Register the bundle ID (one-time)

1. [developer.apple.com](https://developer.apple.com) → Certificates, IDs & Profiles → Identifiers → **+**.
2. App IDs → App → Continue.
3. Bundle ID: `com.playfuel.ios` (Explicit). Description: `PlayFuel`.
4. Capabilities: check **Sign In with Apple**. Register.

### 1c. Create the App Store Connect app record (one-time)

1. [appstoreconnect.apple.com](https://appstoreconnect.apple.com) → My Apps → **+** → New App.
2. Platform: iOS. Bundle ID: `com.playfuel.ios`. SKU: `playfuel-ios` (arbitrary).
3. Save. You do **not** need to fill in store metadata to run a TestFlight test — the record just needs to exist for Xcode to upload to.

### 1d. Add your wife as an internal tester

1. App Store Connect → **Users and Access** → **+** → invite by email, role: Developer (or App Manager).
2. She accepts the invite email.
3. After uploading a build (Step 3d): TestFlight → Internal Testing → add her Apple ID to the test group.

> **Internal vs External:** Two people = internal testing. Internal testers see builds immediately after processing — no Beta App Review required. External testing requires a 24–48 hr Apple review. Use internal.

---

## Step 2 — Backend hosting

> `localhost` is unreachable once the phone leaves your home WiFi. You need a public backend.

### 2a. Hosted Supabase project

1. [supabase.com](https://supabase.com) → New Project (free tier is fine for beta).
2. Note your **Reference ID** (`abcdefghijkl`-style).
3. Push all migrations:

```bash
supabase link --project-ref <your-ref-id>
supabase db push
```

4. Apply the Dallas demo seed (auto-seed is local-only):

```bash
supabase db execute --file db/supabase/seed/dallas_demo.sql
```

5. From Supabase Dashboard → Project Settings → API, copy:
   - **Project URL** → `https://<ref>.supabase.co`
   - **Anon Key**
   - **JWT Secret** (Dashboard → API → JWT Settings)

These replace the three local values in `apps/api/.env`.

> 🚨 **SIWA redirect URL — must update in two places simultaneously:**
> Local callback: `http://127.0.0.1:54321/auth/v1/callback`
> Hosted callback: `https://<ref>.supabase.co/auth/v1/callback`
>
> When you migrate Supabase, update **both**:
> - **Apple Developer portal** → Identifiers → your Services ID → Sign in with Apple → Return URLs → replace the local URL with the hosted one.
> - **Supabase Dashboard** → Auth → Providers → Apple → the same hosted callback URL.
>
> These must match exactly. A mismatch causes SIWA to fail silently with a redirect error. See [`db/supabase/auth/sign-in-with-apple.md`](../db/supabase/auth/sign-in-with-apple.md) for full Apple provider setup.

### 2b. FastAPI on Fly.io

**Why Fly.io:** One-command deploy, free 256 MB VM (ample for the rules engine), automatic `*.fly.dev` HTTPS — satisfies ATS on real devices with zero cert config.

#### 2b-1. Add a Dockerfile

`apps/api/` has no Dockerfile. Create one:

```bash
cat > apps/api/Dockerfile << 'EOF'
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir -e .

COPY src/ src/

EXPOSE 8080

CMD ["uvicorn", "playfuel_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
EOF
```

> **Port 8080:** Fly.io's default. Local dev stays on `--port 8000`.

#### 2b-2. Deploy

```bash
brew install flyctl
fly auth login

cd apps/api
fly launch --name playfuel-api --region dfw --no-deploy
# No Postgres, no Redis — Supabase handles the DB

fly secrets set \
  SUPABASE_URL="https://<ref>.supabase.co" \
  SUPABASE_ANON_KEY="<anon-key>" \
  SUPABASE_JWT_SECRET="<jwt-secret>"

fly deploy
```

Expected: `==> Release v1 created … --> v1 deployed successfully`

#### 2b-3. Verify

```bash
curl -i https://playfuel-api.fly.dev/healthz
# Expected: HTTP/1.1 200  {"status":"ok","rules_version":"..."}

curl -i https://playfuel-api.fly.dev/v1/tournaments
# Expected: HTTP/1.1 401
```

### 2c. Point iOS at the hosted backend

TestFlight archives don't honor Xcode scheme env vars — `Configuration.swift`'s hardcoded fallback (`http://localhost:8000`) ships as-is. Change it before archiving:

```swift
// apps/ios/PlayFuel/Sources/PlayFuel/Configuration.swift — line 14
// Change:
return URL(string: "http://localhost:8000")!
// To:
return URL(string: "https://playfuel-api.fly.dev")!
```

> **Recommended:** make this change on a `release` branch. Stash or revert before your next local dev run — otherwise the simulator hits the production backend with a dev JWT, which will fail. A `git stash` habit keeps local and release clean without extra xcconfig ceremony.

---

## Step 3 — iOS signing and build

### 3a. Bundle ID and team

`project.yml` already has:
- `PRODUCT_BUNDLE_IDENTIFIER: com.playfuel.ios`
- `DEVELOPMENT_TEAM: G89TZ927TJ`
- `Resources/PlayFuel.entitlements` includes `com.apple.developer.applesignin: [Default]` ✅

No signing changes needed.

### 3b. Regenerate the Xcode project

After any `project.yml` or `Configuration.swift` edit:

```bash
cd apps/ios/PlayFuel
xcodegen   # brew install xcodegen if absent
```

### 3c. Confirm signing in Xcode

```
File → Open → apps/ios/PlayFuel/PlayFuel.xcodeproj
```

Select **PlayFuel** target → **Signing & Capabilities**:
- Team: your paid account
- Bundle ID: `com.playfuel.ios`
- "Sign In with Apple" capability listed

If "No profiles found": Xcode Preferences → Accounts → sign in with the Apple ID tied to team `G89TZ927TJ`.

### 3d. Archive and upload to TestFlight

1. Update `Configuration.swift` fallback URL (Step 2c). Run `xcodegen`.
2. Set run destination to **Any iOS Device (arm64)** — not a simulator.
3. **Product → Archive** → Organizer opens.
4. **Distribute App → App Store Connect → Upload**.

> **TestFlight gotchas — read before uploading:**
>
> - **Build processing:** First upload takes 5–30 minutes to appear in App Store Connect. Subsequent uploads are faster. Don't panic if the build isn't immediately visible.
> - **Export compliance:** On first upload, Xcode asks "Does your app use encryption?" PlayFuel uses HTTPS only — no custom crypto. Answer: **"Yes, but uses only exempt encryption"** (or the equivalent "Standard encryption" option). Check "Use this setting for future uploads" to avoid the prompt on every build.
> - **Build expiration:** TestFlight builds expire after **90 days**. Plan a re-upload if testing extends past 3 months.
> - **Internal testers:** Add your wife to the Internal Testing group in App Store Connect → TestFlight after the build finishes processing. She gets an email → installs TestFlight → installs PlayFuel. No cable needed.

---

## Step 4 — Sign in with Apple on real device

### What's different from the simulator

On a real device, `AuthenticationServices` runs the full Apple ID flow. The round-trip:

1. iOS presents the native "Sign in with Apple" sheet (Face ID / Apple ID password).
2. Apple returns an `identityToken` JWT (signed by Apple's keys).
3. App sends it to Supabase Auth (`POST /auth/v1/token?grant_type=id_token`).
4. Supabase validates against Apple's public keys, creates/retrieves the user, returns a Supabase HS256 JWT.
5. App stores Supabase JWT in Keychain; attaches as `Authorization: Bearer` on every API call.
6. FastAPI validates HS256 locally, enforces RLS via `authed_client`.

### Verify the round-trip

```bash
fly logs --app playfuel-api
```

After tapping "Sign in with Apple" on device, watch for:
```
INFO: GET /v1/tournaments — 200
```

**401:** JWT not sent or not accepted — check that `SUPABASE_JWT_SECRET` in `fly secrets` matches Dashboard → API → JWT Settings exactly.

**SIWA hangs or errors on device:** Almost always the redirect URL mismatch. See the 🚨 callout in Step 2a.

**New user not appearing in Dashboard → Auth → Users:** The Supabase Apple provider config is incomplete — re-check Services ID, Team ID, Key ID, and the `.p8` key in Dashboard.

---

## Step 5 — On-device smoke-test checklist

Run on **each phone** after install. Tied to the Dallas demo (88°F, 9:00 AM match, 1:00 PM next match).

- [ ] **Cold launch:** Shows Sign in with Apple screen with "usage guidelines" link.
- [ ] **SIWA flow:** Face ID → lands on My Tournaments (list loads, no network error).
- [ ] **EmergencyBanner:** Dallas Junior Open → Dashboard shows red emergency strip (88°F + 72% humidity). Tap strip → Heat Guidance sheet opens with §B verbatim text.
- [ ] **Scenario cards:** Three cards render — Short (165 min / `light_meal`), Normal (120 min / `quick_pickup`), Long (60 min / `portable`). Gap pills color-coded.
- [ ] **Weather sheet:** Tap Weather bubble → 88°F, 72% humidity, `hot` + `humid` flags, §E.3 adjustment bullets.
- [ ] **Session persistence:** Kill app → relaunch → goes straight to Tournaments (Keychain token persists — no re-sign-in required).
- [ ] **RLS check (wife's phone):** Wife signs in → sees only her tournaments (empty list — correct). Yours don't appear.
- [ ] **Airplane mode:** Enable → Retry → error shown. Disable → Retry → loads normally.
- [ ] **Sign out:** Sign Out → back to Sign In. Fresh credentials required on next launch.
- [ ] **Create tournament:** Tap "+" → fill in name/venue/date → save → appears in list → Dashboard loads.

---

## Cutover Summary

| Setting | Local dev (simulator) | Hosted (on-device / TestFlight) |
|---|---|---|
| **API base URL** | `http://127.0.0.1:8000` (scheme env var in `project.yml`) | `https://playfuel-api.fly.dev` (`Configuration.swift` fallback for archive) |
| **Supabase project** | Local Docker (`http://127.0.0.1:54321`) | Hosted (`https://<ref>.supabase.co`) |
| **JWT secret source** | `supabase status` output | Dashboard → API → JWT Settings |
| **Supabase anon key** | Local key (scheme env var) | Dashboard → API → anon/public key |
| **Signing config** | Team `G89TZ927TJ`, debug profile | Team `G89TZ927TJ`, distribution profile |
| **ATS posture** | `NSAllowsLocalNetworking: true` in `Info.plist` (allows `http://localhost`) | `https://` satisfies ATS natively; exception harmless to keep |
| **Apple SIWA redirect URL** | `http://127.0.0.1:54321/auth/v1/callback` | `https://<ref>.supabase.co/auth/v1/callback` |
| **TestFlight build expiry** | N/A | 90 days — re-upload if testing extends past 3 months |

> `NSAllowsLocalNetworking` only relaxes ATS for `localhost`/`127.0.0.1`/`.local`. It doesn't weaken ATS for public internet traffic. Safe to keep in the archive build.

---

*Last updated: 2026-04-28 — Single-path TestFlight doc for two-person beta (Phase 8 build).*
