# Next Steps — TestFlight Cutover

> **Where we are (2026-05-01):** Step 2 of [`ON_DEVICE_TESTING.md`](./ON_DEVICE_TESTING.md) complete. Hosted backend live, release branch ready.
>
> **Branch:** `release/testflight-1` — two commits, clean tree.

---

## Live state

| Component | Status |
|---|---|
| Hosted Supabase | ✅ `https://vxiunrpjvamspeecbriu.supabase.co` — 11 migrations + Dallas seed |
| Hosted FastAPI | ✅ `https://playfuel-api.fly.dev` — `/healthz` 200, `/v1/tournaments` 401 |
| iOS release config | ✅ `Configuration.swift` fallback → Fly host (release branch only) |

---

## Owner — must do yourself

Sequence matters. Do not skip ahead.

### 1. App Store Connect prep — [`appstoreconnect.apple.com`](https://appstoreconnect.apple.com)

- [ ] Add wife to **Users and Access** (role: Developer or App Manager)
- [ ] Confirm app record `com.playfuel.ios` exists under My Apps

### 2. Apple Developer portal — [`developer.apple.com/account`](https://developer.apple.com/account)

- [ ] Create / verify **Services ID** for SIWA
- [ ] Set **Return URL** to `https://vxiunrpjvamspeecbriu.supabase.co/auth/v1/callback`
- [ ] Generate **`.p8` Sign in with Apple key**, download once, note Key ID

### 3. Supabase Dashboard — Auth → Providers → Apple

- [ ] Paste **Services ID**, **Team ID** (`G89TZ927TJ`), **Key ID**, `.p8` contents
- [ ] Save. Verify provider toggle is enabled.

### 4. Xcode — archive + upload

- [ ] Confirm you're on `release/testflight-1`: `git status`
- [ ] Open `apps/ios/PlayFuel/PlayFuel.xcodeproj`
- [ ] **Signing & Capabilities** — Team `G89TZ927TJ`, "Sign In with Apple" listed
- [ ] Run destination → **Any iOS Device (arm64)**
- [ ] **Product → Archive** → Organizer → **Distribute App → App Store Connect → Upload**
- [ ] On encryption prompt: **"Yes, but uses only exempt encryption"** + check "use for future uploads"

### 5. TestFlight — internal testing

- [ ] Wait 5–30 min for build to finish processing
- [ ] App Store Connect → TestFlight → Internal Testing → add wife's Apple ID
- [ ] Wife: install TestFlight from App Store → install PlayFuel from invite email

### 6. Two-phone smoke test

Run [Step 5 checklist](./ON_DEVICE_TESTING.md#step-5--on-device-smoke-test-checklist) on both phones. Tail backend logs:

```bash
flyctl logs --app playfuel-api
```

After SIWA on device, expect: `INFO: GET /v1/tournaments — 200`.

---

## Hand off to agent team — parallel work

Branch off `main`, not `release/testflight-1`. None of this blocks TestFlight.

### Ticket A — doc + repo hygiene (1 PR)

- [ ] **Fix `docs/ON_DEVICE_TESTING.md` Step 2b-1 Dockerfile.** Current snippet copies `pyproject.toml`, runs `pip install -e .`, *then* copies `src/` — fails because editable install requires `src/` present. Reorder COPYs first, install last. Working version is at `apps/api/Dockerfile`.
- [ ] **Add a "switching back to local dev" section** to `ON_DEVICE_TESTING.md` — `git checkout main` + `supabase start` + `uv run uvicorn playfuel_api.main:app --reload --port 8000`.
- [ ] **`.gitignore` audit** — confirm `.env`, `__pycache__/`, `*.pyc`, `.DS_Store`, `.venv/`, `dist/`, `build/`, `*.egg-info/` are all covered.

### Ticket B — auth.py JWKS migration (defer until after beta)

- [ ] `apps/api/src/playfuel_api/auth.py` validates with `algorithms=["HS256"]` against shared `SUPABASE_JWT_SECRET`. Supabase has moved primary signing to asymmetric keys; the legacy HS256 secret is currently the fallback we're using.
- [ ] Replace with JWKS validation against `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json`. Cache keys with TTL, support key rotation, validate via `RS256` / `ES256`.
- [ ] Add tests for both old (HS256) and new (asymmetric) tokens to ease cutover.
- [ ] **Do not ship before TestFlight beta is stable.**

### Ticket C — backend test coverage audit

- [ ] Run `cd apps/api && uv run pytest -v` — capture current coverage.
- [ ] Identify untested paths in `/v1/tournaments`, `/v1/plans`, `/v1/players`, `/v1/match_evaluations`.
- [ ] Add integration tests using a real Supabase test DB (per CLAUDE.md rule: do not mock the DB).

---

## Rollback / disaster recovery

| Scenario | Action |
|---|---|
| Bad iOS build hits TestFlight | App Store Connect → expire the build; previous build stays installable |
| Bad Fly deploy | `flyctl releases --app playfuel-api` then `flyctl deploy --image registry.fly.io/playfuel-api:<prior-digest>` |
| Bad Supabase migration | `supabase db reset --linked` (destructive — only if no real user data) or `supabase db push` a corrective migration |
| Lost JWT secret | Dashboard → Project Settings → API → JWT Settings → reveal again. Update `flyctl secrets set SUPABASE_JWT_SECRET=...`; redeploys automatically. |

---

## Open issues / known gotchas

- **TestFlight builds expire after 90 days** — set a reminder for 2026-07-30 to re-archive if beta extends.
- **Fly free tier auto-stops idle machines.** First request after idle has ~2s cold start. Acceptable for beta; revisit if matchday latency is felt.
- **Supabase free tier pauses after 7 days of inactivity.** If you and your wife don't open the app for a week, the first request will fail until you ping the dashboard. Not an issue during active testing.
- **Local dev unaffected** — staying on `main` keeps `Configuration.swift` pointed at `localhost:8000`. The Fly URL only ships from `release/testflight-1`.
