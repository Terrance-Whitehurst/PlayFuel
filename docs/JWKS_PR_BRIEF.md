# Engineering Brief — JWKS Migration + `user_id` Injection (single PR)

> **For:** Engineering team picking up the auth-correctness fix.
> **Branch:** off `release/testflight-1` → topic branch `fix/auth-jwks` → PR back into `release/testflight-1`.
> **Do not push to `main`.** Do not push directly to `release/testflight-1` — go through PR review.
> **Blocks:** TestFlight build 6 cannot ship until this lands.
> **Companion docs:** [`AUTH_DEBUG_BRIEF.md`](./AUTH_DEBUG_BRIEF.md), [`NEXT_STEPS.md`](./NEXT_STEPS.md) (Ticket B).

---

## Scope

One PR. Three changes that must ship together because they all live on the auth path and shipping any subset leaves TestFlight broken.

1. **JWKS validation** in `apps/api/src/playfuel_api/auth.py` — accept Supabase RS256/ES256 tokens (primary) and HS256 tokens (legacy fallback) during the cutover window.
2. **`user_id` injection** in every FastAPI insert path that targets a table with a `user_id NOT NULL` column — currently inserts omit it and rely on a non-existent DB default.
3. **Doc-comment cleanup** in iOS `AuthService.swift` so the comments stop claiming "HS256" once the backend validates asymmetric tokens. (Behavior already correct — see "Out of scope" below.)

---

## 1. JWKS validation in `auth.py`

**File:** `apps/api/src/playfuel_api/auth.py`

**Current behavior** (`auth.py:55-61`):

```python
payload = jwt.decode(
    token,
    settings.supabase_jwt_secret,
    algorithms=["HS256"],
    audience="authenticated",
)
```

**Required behavior:**

- Read header `kid` and `alg` from the token first.
- If `alg` is `RS256` or `ES256`: fetch the JWKS from `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json` (use `settings.supabase_url` — already on Fly: confirmed `flyctl secrets list --app playfuel-api`). Cache by `kid` with a 1 h TTL. Decode with the matching public key.
- If `alg` is `HS256`: fall back to the existing `settings.supabase_jwt_secret` path. This branch is **temporary** — scheduled for removal on **2026-05-12**.
- All other `alg` values → 401 with `Invalid token`.
- Preserve the existing 401 contract on `ExpiredSignatureError`, `InvalidTokenError`, missing `sub`, non-UUID `sub`. Tests below pin this.

**Implementation notes:**

- Use `PyJWKClient` from `pyjwt` (already a dependency). Configure with a 1 h cache TTL — Supabase rotates keys infrequently, but the cache means a single network call per key per hour, not per request.
- Wrap JWKS fetch failures so a transient outage returns 503, not 500. (Or 401 — pick one and document. 503 is more honest.)
- Do **not** swallow `kid`-not-found into a generic 401 — log it, because that's the primary signal that key rotation has happened and we need to invalidate the cache.

---

## 2. `user_id` injection in insert paths

**Root cause:** `tournaments.user_id` is declared `uuid not null` (`db/supabase/migrations/0002_tables.sql:105`) with **no default**. The RLS policy `tournaments_insert_own` (`db/supabase/migrations/0003_rls.sql:107-108`) is `with check ((select auth.uid()) = user_id)` — it *validates*, it does not *populate*. The comment at `apps/api/src/playfuel_api/routes/tournaments.py:92` claiming "user_id set by DB trigger / RLS" is incorrect — `0004_auth_trigger.sql` is the `auth.users → public.users` shadow trigger, unrelated to tournaments.

**Required change** in `tournaments.py:create_tournament` (`tournaments.py:87-102`):

```python
payload = body.model_dump(exclude_none=True)
payload["user_id"] = str(user_id)   # ← from verify_supabase_jwt
for k in ("start_date", "end_date"):
    if k in payload:
        payload[k] = payload[k].isoformat()
```

Note that the route currently binds the dependency as `_user_id` (underscore-prefixed = unused). Rename to `user_id` and use it.

**Audit every other insert path** for the same bug. Routes to check, in order:

- `apps/api/src/playfuel_api/routes/players.py` — likely has direct `user_id`
- `apps/api/src/playfuel_api/routes/player_profiles.py` — table is direct-ownership per `0003_rls.sql:67-91`
- `apps/api/src/playfuel_api/routes/matches.py` — child of tournaments, no direct `user_id`, RLS handles ownership via tournament_id; **no change needed** unless the route tries to insert a `user_id` column
- `apps/api/src/playfuel_api/routes/plans.py` — child of tournaments, same as above
- `apps/api/src/playfuel_api/routes/match_evaluations.py` — check the schema; if it has direct `user_id`, inject; otherwise leave

The rule: **if the table has a `user_id` column declared `not null`, the API insert payload must include it from the JWT `sub` claim.**

---

## 3. iOS doc-comment cleanup

The iOS 401-retry logic in `apps/ios/PlayFuel/Sources/PlayFuel/Networking/APIClient.swift:95-119` is **correct** — one refresh + one retry, then sign out. The forced-sign-out symptom on TestFlight build 5 comes from the backend rejecting *both* the original token and the post-refresh token (because both are RS256), not from over-aggressive iOS sign-out.

Once the backend accepts asymmetric tokens, the iOS behavior is already right. **No code changes needed in iOS.** Just update doc comments that say "HS256":

- `AuthService.swift:13` — drop "(HS256)"
- Any other comment in `Networking/` that mentions HS256 specifically

---

## Tests

**Project rule (from CLAUDE.md and `AUTH_DEBUG_BRIEF.md`):** do not mock Supabase or the database. Use real tokens against a real Supabase instance (test project or local `supabase start`).

Required coverage:

- `verify_supabase_jwt` accepts a valid RS256 token, returns the correct UUID
- `verify_supabase_jwt` accepts a valid HS256 token (legacy fallback), returns the correct UUID
- `verify_supabase_jwt` rejects an expired token → 401 `Token has expired`
- `verify_supabase_jwt` rejects a token signed by an unknown `kid` → 401
- `verify_supabase_jwt` rejects an unsupported `alg` (e.g. `none`, `HS512`) → 401
- JWKS cache: second call within 1 h does not re-hit the network (mock the HTTP fetch only — not Supabase itself)
- `POST /v1/tournaments` with a valid token inserts a row with the correct `user_id`, returns 201
- `POST /v1/tournaments` end-to-end against a real Supabase test DB returns the row visible to that user via RLS, not visible to a different user

Run before requesting review:

```bash
cd apps/api && uv run pytest -v
```

---

## Done criteria

- All tests above pass.
- `curl -i -H "Authorization: Bearer <fresh RS256 token>" https://playfuel-api.fly.dev/v1/tournaments` → **200** + JSON body. *(Run after Fly deploy of the merged branch — owner will deploy.)*
- Pre-deploy local check: same `curl` against `http://127.0.0.1:8000/v1/tournaments` with a token from a hosted Supabase session → **200**.
- `flyctl logs --app playfuel-api` during a TestFlight smoke test shows `200`s on `/v1/tournaments`, no `Signature verification failed`.
- Tournament creation from the iOS app works end-to-end — the row appears in the list after POST.
- App force-quit + relaunch lands on Tournaments without re-signing in.

---

## Branch strategy

| Branch | Role |
|---|---|
| `main` | Local-sim dev — `Configuration.swift` fallbacks point at `localhost`. **Do not push.** |
| `release/testflight-1` | Live TestFlight branch — `Configuration.swift` fallbacks point at Fly + hosted Supabase. **Do not push directly.** |
| `fix/auth-jwks` (off `release/testflight-1`) | Your work. PR back into `release/testflight-1`. |

Owner reviews + merges the PR, then re-archives + uploads (CFBundleVersion → 6).

---

## Out of scope

- **Removing the HS256 fallback branch** in `auth.py`. Scheduled for **2026-05-12** under a follow-up PR (Supabase refresh-token TTL is ~1 week — by then all TestFlight sessions will have rotated to asymmetric tokens). A scheduled agent will open that cleanup PR.
- **DB-level `DEFAULT auth.uid()`** on `user_id` columns. Defense-in-depth, but mid-beta migration risk isn't worth it. Track separately.
- **Refresh-token failure UX** ("Session expired — please sign in again" toast vs. silent sign-out). Already-correct retry logic; UX polish is separate.
- **App icon / asset catalog work.** Resolved in `b5e46b4`.

---

## Deliverable

PR into `release/testflight-1` titled `fix(auth): JWKS validation + user_id injection`. Body should reference this brief and `AUTH_DEBUG_BRIEF.md`. Do not deploy — owner deploys after merge.
