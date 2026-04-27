# PlayFuel — TestFlight Walkthrough (Solo Day Run)

> Goal: get PlayFuel running on a TestFlight build that your wife (or any internal tester) can install on her real iPhone today.
>
> Estimated wall-clock time: **4–8 hours** including Apple papercuts. First-time submitters should plan for 8.
>
> Prerequisite mindset: Apple's portals are slow and sometimes flaky. Don't fight it — when something hangs, refresh the tab and move on to a parallel step.

---

## Stage 0 — Prerequisites checklist

Tick these before starting. Missing any will block you mid-stream.

- [ ] Mac with Xcode 26.4+ installed (you have this)
- [ ] An Apple ID you don't mind being the developer-of-record
- [ ] A credit card for the $99/yr Apple Developer membership
- [ ] A phone (yours or hers) you can use for SMS-based 2FA on the Apple portal
- [ ] ~30 min of patience for Apple Developer enrollment to activate (usually instant, occasionally hours)
- [ ] A way to host a static privacy policy page (GitHub Pages, Notion public page, your own site, etc.)
- [ ] A Fly.io account (free tier works) **or** another public host that can run Python/uvicorn

If anything above is "no," resolve it before continuing.

---

## Stage 1 — Apple Developer enrollment (~15–60 min)

1. Open https://developer.apple.com/programs/enroll/
2. Sign in with the Apple ID you'll use as the dev account.
3. Pick **Individual / Sole Proprietor** unless you have a registered business.
4. Pay $99. Wait for the confirmation email — you cannot proceed without it.
5. Once active, open https://developer.apple.com/account → confirm you see the membership.

**If Apple does identity verification, it can take 24–48h. There's nothing you can do but wait.** Use that time on Stages 2–4 below, which don't require enrollment.

---

## Stage 2 — Supabase Cloud project (~15 min)

1. Open https://supabase.com → sign in or sign up → "New Project."
2. Name: `playfuel-prod` (or anything). Pick the region closest to you.
3. Set a strong database password — save it in your password manager.
4. Wait ~2 min for provisioning.
5. Once green, go to **Project Settings → API** and copy these into a scratch note:

   ```
   SUPABASE_URL=https://xxxxxxxx.supabase.co
   SUPABASE_ANON_KEY=eyJhbGciOi...
   SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOi...
   SUPABASE_JWT_SECRET=<the JWT secret string>
   ```

   ⚠️ The `service_role` and JWT secret are **never** to be exposed to the iOS client. Server-side only.

### 2a — Run database migrations

In Supabase Dashboard → **SQL Editor → New query**, paste and run **in this order**:

1. `db/supabase/migrations/0001_extensions_and_enums.sql`
2. `db/supabase/migrations/0002_tables.sql`
3. `db/supabase/migrations/0003_rls.sql`
4. `db/supabase/migrations/0004_auth_trigger.sql`

Each should return "Success. No rows returned." Stop and ask for help if any error.

### 2b — (Optional for now) Skip the Dallas demo seed

The Dallas seed inserts rows owned by a hardcoded test UUID — **your wife won't see them**. Skip it for now. We'll seed her account directly after she signs in (Stage 9).

---

## Stage 3 — Apple Developer: App ID, Services ID, and SIWA Key (~30 min)

You only do this once per app. It's fiddly but mechanical.

### 3a — Register an App ID

1. https://developer.apple.com/account/resources/identifiers/list
2. Click **+** → **App IDs** → **App** → Continue.
3. Description: `PlayFuel iOS`
4. Bundle ID: **Explicit** → `com.playfuel.PlayFuel` (must match exactly)
5. Capabilities: scroll down, check **Sign In with Apple**.
6. Continue → Register.

### 3b — Register a Services ID (for Supabase to use)

1. Same page → **+** → **Services IDs** → Continue.
2. Description: `PlayFuel Web`
3. Identifier: `com.playfuel.PlayFuel.signin` (must be different from the App ID)
4. Continue → Register.
5. Click the new Services ID → check **Sign In with Apple** → **Configure**:
   - Primary App ID: `com.playfuel.PlayFuel` (from 3a)
   - **Domains and Subdomains**: your Supabase project domain, e.g. `xxxxxxxx.supabase.co`
   - **Return URLs**: `https://xxxxxxxx.supabase.co/auth/v1/callback`
6. Save → Continue → Save.

### 3c — Create a Sign In with Apple Key

1. https://developer.apple.com/account/resources/authkeys/list
2. **+** → Key Name: `PlayFuel SIWA Key`
3. Check **Sign In with Apple** → **Configure** → pick the App ID `com.playfuel.PlayFuel` → Save.
4. Continue → Register → **Download the .p8 file**.
5. ⚠️ **You can only download the .p8 once. Save it in your password manager.**
6. Note the **Key ID** (10 chars) shown on the screen.
7. Note your **Team ID** — top right of https://developer.apple.com/account/ membership page.

### 3d — Wire SIWA into Supabase

1. Supabase Dashboard → **Authentication → Providers → Apple → Enable**.
2. Fill in:
   - **Client IDs (for Apple)**: `com.playfuel.PlayFuel` AND `com.playfuel.PlayFuel.signin` (comma-separated)
   - **Secret Key (for OAuth)**: leave for now or auto-generate via Supabase's "Generate" button using the .p8 + Team ID + Key ID + Services ID
3. Save.

---

## Stage 4 — Deploy the FastAPI backend to Fly.io (~45 min first time)

### 4a — Install Fly CLI

```bash
brew install flyctl
fly auth signup   # or `fly auth login`
```

### 4b — Fix the pyproject build-backend issue

`apps/api/pyproject.toml` currently breaks with setuptools 82+. Edit the `[build-system]` block:

```toml
[build-system]
requires = ["setuptools>=68,<82", "wheel"]
build-backend = "setuptools.build_meta"
```

(Or whatever the current backend is — pin `setuptools<82`.)

### 4c — Add a Dockerfile for Fly

Create `apps/api/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src

RUN pip install --no-cache-dir -e .

ENV PYTHONUNBUFFERED=1
ENV API_PORT=8080

EXPOSE 8080
CMD ["uvicorn", "playfuel_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 4d — Initialize Fly app

```bash
cd apps/api
fly launch --no-deploy
```

When prompted:
- App name: `playfuel-api` (or any unique name — note what you pick)
- Region: pick the closest
- Postgres? **No** (Supabase handles DB)
- Redis? **No**
- Deploy now? **No**

### 4e — Set Fly secrets

```bash
fly secrets set \
  SUPABASE_URL='https://xxxxxxxx.supabase.co' \
  SUPABASE_ANON_KEY='eyJhbGciOi...' \
  SUPABASE_JWT_SECRET='<jwt secret>' \
  SUPABASE_SERVICE_ROLE_KEY='eyJhbGciOi...' \
  API_PORT=8080
```

### 4f — Edit `fly.toml`

Make sure the `[[services]]` (or `[http_service]`) section has `internal_port = 8080` and Fly will issue an HTTPS cert automatically for `https://playfuel-api.fly.dev`.

### 4g — Deploy

```bash
fly deploy
```

Watch for "Deployment successful." Then test:

```bash
curl https://playfuel-api.fly.dev/healthz
# Expect: {"status":"ok"} or similar
```

If healthz fails → `fly logs` to debug. Common causes: wrong port, missing env var, bad import.

**Save your public API URL.** You'll bake it into the iOS build next.

---

## Stage 5 — Privacy policy hosting (~30 min)

Apple **requires** a privacy policy URL even for TestFlight when you use SIWA. Bare-bones is fine.

Easy paths:
- **GitHub Pages**: create a public repo `playfuel-privacy`, add `index.html` with the policy text, enable Pages, copy the URL.
- **Notion**: create a Notion page, share publicly, copy the URL.
- **A subdomain you already own**: just upload an HTML file.

Minimum content: app name, what data is collected (email, Apple user ID via SIWA, tournament/match data the user creates), how it's used, no third-party sharing, contact email, last-updated date. There are free generators online.

**Save the public URL.**

---

## Stage 6 — Wire production config into the iOS app (~30 min)

The current `Configuration.swift` reads from process env vars (which only work in the simulator) and falls back to placeholders. For an archived release build, you need real values baked in.

### 6a — Edit `Configuration.swift`

Open `apps/ios/PlayFuel/Sources/PlayFuel/Configuration.swift`. Replace placeholders with real values:

```swift
static let apiBaseURL: URL = {
    if let raw = ProcessInfo.processInfo.environment["PLAYFUEL_API_BASE_URL"],
       let url = URL(string: raw) {
        return url
    }
    return URL(string: "https://playfuel-api.fly.dev")!  // <-- your Fly URL
}()

static let supabaseURL: URL = {
    let raw = ProcessInfo.processInfo.environment["SUPABASE_URL"]
        ?? "https://xxxxxxxx.supabase.co"  // <-- your Supabase URL
    return URL(string: raw)!
}()

static let supabaseAnonKey: String =
    ProcessInfo.processInfo.environment["SUPABASE_ANON_KEY"]
        ?? "eyJhbGciOi..."  // <-- your Supabase anon key
```

The anon key is fine to ship — it's the public client key. Service role and JWT secret stay server-side only.

> Cleaner long-term: split into `Debug.xcconfig` / `Release.xcconfig` and reference those in `project.yml`. Today, just hardcode and move on.

### 6b — Add SIWA capability to the Xcode project

Edit `apps/ios/PlayFuel/project.yml`:

```yaml
targets:
  PlayFuel:
    type: application
    platform: iOS
    sources:
      - path: Sources/PlayFuel
    info:
      path: Sources/PlayFuel/Info.plist
      properties:
        CFBundleDisplayName: PlayFuel
        UILaunchScreen:
          UIColorName: ""
        UISupportedInterfaceOrientations:
          - UIInterfaceOrientationPortrait
        UIApplicationSceneManifest:
          UIApplicationSupportsMultipleScenes: false
    entitlements:
      path: PlayFuel.entitlements
      properties:
        com.apple.developer.applesignin:
          - Default
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: com.playfuel.PlayFuel
        TARGETED_DEVICE_FAMILY: "1,2"
        GENERATE_INFOPLIST_FILE: NO
        ENABLE_PREVIEWS: YES
        DEVELOPMENT_TEAM: ABCDE12345        # <-- your 10-char Team ID
        CODE_SIGN_STYLE: Automatic
        MARKETING_VERSION: "1.0.0"
        CURRENT_PROJECT_VERSION: "1"
```

### 6c — Regenerate

```bash
cd apps/ios/PlayFuel
xcodegen generate
```

### 6d — Verify in Xcode

```bash
open PlayFuel.xcodeproj
```

- Select the **PlayFuel** target → **Signing & Capabilities** tab.
- "Automatically manage signing" should be checked.
- Team should show your team.
- "Sign In with Apple" capability should appear.
- No red errors.

If Xcode complains about provisioning profiles, click "Try Again" or "Register Device" as it prompts.

### 6e — Local sanity rebuild

```bash
xcodebuild -project PlayFuel.xcodeproj -scheme PlayFuel \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -configuration Debug build
```

Should still BUILD SUCCEEDED.

---

## Stage 7 — Create the App Store Connect record (~20 min)

1. https://appstoreconnect.apple.com → sign in.
2. **My Apps → +** → New App.
3. Platform: iOS. Name: `PlayFuel` (must be unique on the App Store). Primary language: English.
4. Bundle ID: `com.playfuel.PlayFuel` (should appear in dropdown if Stage 3a worked).
5. SKU: anything unique, e.g. `playfuel-ios-001`.
6. User Access: Full Access.
7. Create.

### 7a — Fill in app information

- **App Information → Privacy Policy URL**: paste the URL from Stage 5. **Required.**
- Category: pick something like Sports or Health & Fitness.
- Content Rights: yes, you have rights.

You can leave most other fields blank for internal TestFlight — Apple only enforces the rest for App Store review.

---

## Stage 8 — Archive and upload to TestFlight (~30 min, sometimes fights you)

### 8a — Archive

In Xcode:
1. Top toolbar device picker → select **Any iOS Device (arm64)** (NOT a simulator).
2. **Product → Archive**.
3. Wait. First archive can take 3–10 min and reveals signing/provisioning issues.
4. When done, the **Organizer** opens automatically.

**Common archive failures and fixes:**

| Error | Fix |
|---|---|
| "No account for team..." | Xcode → Settings → Accounts → add your Apple ID, download manual profiles |
| "Provisioning profile doesn't include Sign In with Apple capability" | Wait a minute, "Try Again." Xcode regenerates profiles. |
| "Cycle in dependencies" | Clean build folder (⇧⌘K) and re-archive |
| "Encryption export compliance" prompt | Answer based on whether you use any non-standard encryption — for this app, "No" is correct |

### 8b — Distribute

1. In Organizer → select the archive → **Distribute App**.
2. Choose **TestFlight & App Store** → Next.
3. **Upload** → Next.
4. Distribution options: leave defaults (Symbols upload yes, Manage version automatically yes) → Next.
5. Re-sign automatically → Next.
6. Review → **Upload**.
7. Wait 2–10 min for upload + Apple processing.

### 8c — Wait for processing

In App Store Connect → **TestFlight** tab, your build will appear with status "Processing." This takes anywhere from 5 min to a few hours. Check back periodically.

When it's "Ready to Submit" or "Ready to Test," continue.

### 8d — Export Compliance (one-time)

Apple may ask: "Does your app use encryption?" Click the build → answer questions. For a SIWA-only app with HTTPS API calls and no custom crypto, the standard answer is "Yes — only standard encryption (HTTPS / system TLS)" → "Exempt." Saves you from a real export form.

---

## Stage 9 — Add your wife as an internal tester (~10 min)

1. App Store Connect → **TestFlight → Internal Testing → +** (Create Group, or use existing).
2. Group name: `Family`.
3. **Testers → +** → enter her email + name. **Use the Apple ID email she'll sign into TestFlight with.**
4. **Builds → +** → select your processed build.
5. She'll get an email "You've been invited to test PlayFuel."

She:
1. Installs **TestFlight** from the App Store on her iPhone.
2. Opens the email invite from her phone → tap the link → opens TestFlight.
3. Taps **Install** for PlayFuel.
4. Opens PlayFuel → taps Sign in with Apple → uses her Apple ID.

---

## Stage 10 — Seed her account so she sees something (~10 min)

After she signs in **at least once**:

1. Supabase Dashboard → **Authentication → Users**.
2. Find her email — copy her UUID (looks like `f7c4e8a0-...`).
3. **SQL Editor → New query**, paste (replace the UUID and adjust dates):

   ```sql
   -- Replace with HER user UUID
   \set tester_uuid 'f7c4e8a0-xxxx-xxxx-xxxx-xxxxxxxxxxxx'

   -- Insert a test tournament owned by her account
   insert into public.tournaments (id, owner_id, name, venue, latitude, longitude, start_date, end_date)
   values (
     gen_random_uuid(),
     :'tester_uuid',
     'Spring Open Test',
     'Local Tennis Center',
     32.7767, -96.7970,            -- Dallas-ish coords; pick yours
     '2026-05-15', '2026-05-15'
   ) returning id;

   -- Capture the returned tournament id, then insert a match:
   -- (Use the SQL Editor's row output, then run a second query with that id.)
   ```

   You may want to write a small parameterized helper instead — fine to iterate. The schema is in `db/supabase/migrations/0002_tables.sql`.

4. Tell her to pull-to-refresh or relaunch the app.

She should now see "Spring Open Test" in her tournament list and be able to tap into the dashboard, scenarios, weather, etc.

---

## Stage 11 — Smoke test the whole flow (~15 min)

On a real device:

- [ ] Sign in with Apple completes
- [ ] Tournament list shows her seeded tournament
- [ ] Tapping a tournament opens the dashboard
- [ ] Plan generation works (calls `https://playfuel-api.fly.dev/v1/...`)
- [ ] Weather card renders real data (Open-Meteo is keyless and works from Fly)
- [ ] Scenario cards show the three durations
- [ ] Food card renders (still spliced from FakeData per the Phase 4/5 splice marker until Task #8 ships)
- [ ] Timeline view renders
- [ ] Disclaimer + emergency banner render correctly

If any step fails, `fly logs --app playfuel-api` is your friend.

---

## Troubleshooting cheatsheet

| Symptom | Likely cause | Fix |
|---|---|---|
| SIWA fails with `-7026` on the device | iCloud not signed in on phone | Settings → Apple ID on her phone |
| SIWA succeeds but "Sign-in failed" alert | Supabase Apple provider misconfigured | Recheck Stage 3d Client IDs, Services ID return URL, Team/Key/Secret |
| Empty tournament list | RLS doing its job, no data for her UUID | Run Stage 10 seed |
| API calls hang | Wrong `apiBaseURL` baked in, or Fly app sleeping | `curl https://playfuel-api.fly.dev/healthz` |
| Plan generation 401 | JWT secret mismatch between Supabase and FastAPI | Re-set Fly secret with the exact JWT secret from Supabase Settings → API |
| Plan generation 500 | Migration not run, or RLS blocking insert | Recheck Stage 2a migrations all ran |
| Build expires "Build is no longer available" | TestFlight builds expire after 90 days | Re-archive and re-upload |
| Weather shows empty/zero | Open-Meteo unreachable from Fly region | Pick a different Fly region; recheck `WEATHER_PROVIDER` env |

---

## Status snapshot

When complete:
- ✅ Apple Developer membership active
- ✅ Bundle ID + Services ID + SIWA Key registered
- ✅ Supabase Cloud project running with migrations
- ✅ Apple SIWA wired into Supabase Auth
- ✅ FastAPI deployed to `https://playfuel-api.fly.dev` with HTTPS
- ✅ iOS app archived and uploaded to TestFlight
- ✅ Privacy policy URL live
- ✅ Internal tester invited and installed
- ✅ Her account seeded with at least one tournament

---

## What this does NOT cover (deliberately deferred)

- Public/external TestFlight (requires Apple beta review, ~24h)
- App Store submission (full review, several days)
- Production privacy policy review by counsel (OQ-PRIV-1, OQ-06)
- Heat-emergency text legal review (OQ-11)
- LLM explanation layer (Phase 6 / Task #9)
- Real food/places integration (Task #8 — currently spliced)
- xcconfig-based Debug/Release URL split (today's hardcoded URL is fine for one tester)
- Crash reporting / analytics
- Push notifications

These are real and matter — but not blocking your wife seeing the app today.
