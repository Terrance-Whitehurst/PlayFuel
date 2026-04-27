# PlayFuel — RLS Policy Reference

This document describes every Row Level Security policy in plain English.
For the SQL definition see `migrations/0003_rls.sql`.

---

## Security Model

- Supabase RLS is enforced at the **database layer** — not the API layer.
- Every policy checks `(select auth.uid())` (parenthesised for query-planner caching).
- Direct-ownership tables check `(select auth.uid()) = user_id` (or `= id` for `users`).
- Child tables join up to the nearest user-owned ancestor; no views are used.
- HTTP 200 ≠ access granted. A SELECT that returns 0 rows for a real object means RLS blocked it — not an error.

---

## Policy Table

| Table | SELECT | INSERT | UPDATE | DELETE | Ownership Pattern |
|---|---|---|---|---|---|
| `users` | ✅ | ✅ | ✅ | ✅ | Direct: `id = auth.uid()` |
| `player_profiles` | ✅ | ✅ | ✅ | ✅ | Direct: `user_id = auth.uid()` |
| `tournaments` | ✅ | ✅ | ✅ | ✅ | Direct: `user_id = auth.uid()` |
| `matches` | ✅ | ✅ | ✅ | ✅ | 1-hop: `tournament.user_id = auth.uid()` |
| `match_scenarios` | ✅ | ✅ | ✅ | ✅ | 2-hop: `match → tournament.user_id = auth.uid()` |
| `weather_snapshots` | ✅ | ✅ | ✅ | ✅ | 1-hop: `tournament.user_id = auth.uid()` |
| `food_options` | ✅ | ✅ | ✅ | ✅ | 1-hop: `tournament.user_id = auth.uid()` |
| `plans` | ✅ | ✅ | ✅ | ✅ | 1-hop: `tournament.user_id = auth.uid()` |
| `feedback` | ✅ | ✅ | ✅ | ✅ | 2-hop: `plan → tournament.user_id = auth.uid()` |

---

## Policy Descriptions

### `users`

| Policy | Claim |
|---|---|
| `users_select_own` | A user can only **read** their own shadow row. No user can see another user's record. |
| `users_insert_own` | A user can only **create** a `users` row for their own `auth.uid()`. In practice, this is handled exclusively by the `on_auth_user_created` trigger — the app layer should never call this directly. |
| `users_update_own` | A user can only **update** their own row. Currently there is nothing updatable on this table beyond `updated_at`. |
| `users_delete_own` | A user can only **delete** their own row. Deleting it cascades to all child tables (player_profiles, tournaments, and all descendants). This is the one-shot account deletion required by PRD §11. |

---

### `player_profiles`

| Policy | Claim |
|---|---|
| `player_profiles_select_own` | A parent can only **read** player profiles they created. Another parent's player profiles are invisible. |
| `player_profiles_insert_own` | A parent can only **create** a profile owned by their `auth.uid()`. The client cannot set `user_id` to another user's ID. |
| `player_profiles_update_own` | A parent can only **edit** their own player profiles. |
| `player_profiles_delete_own` | A parent can only **delete** their own player profiles. |

---

### `tournaments`

| Policy | Claim |
|---|---|
| `tournaments_select_own` | A parent can only **see** tournaments they created. |
| `tournaments_insert_own` | A parent can only **create** tournaments under their own account. |
| `tournaments_update_own` | A parent can only **edit** their own tournaments. |
| `tournaments_delete_own` | A parent can only **delete** their own tournaments. Cascades to matches, weather_snapshots, food_options, plans (and nested feedback). |

---

### `matches`

Ownership resolved via: `matches.tournament_id → tournaments.user_id`

| Policy | Claim |
|---|---|
| `matches_select_own` | A parent can only **see** matches inside their own tournaments. |
| `matches_insert_own` | A parent can only **add** a match to a tournament they own. Prevents inserting a match into another parent's tournament even if the `tournament_id` UUID is guessed. |
| `matches_update_own` | A parent can only **edit** matches they own. |
| `matches_delete_own` | A parent can only **delete** their own matches. Cascades to match_scenarios. |

---

### `match_scenarios`

Ownership resolved via: `match_scenarios.match_id → matches.tournament_id → tournaments.user_id`

| Policy | Claim |
|---|---|
| `match_scenarios_select_own` | A parent can only **see** scenarios for their own matches. |
| `match_scenarios_insert_own` | A parent can only **insert** scenarios for matches they own. Prevents the API from inserting scenarios under another user's matches. |
| `match_scenarios_update_own` | A parent can only **edit** their own match scenarios. |
| `match_scenarios_delete_own` | A parent can only **delete** their own match scenarios. |

---

### `weather_snapshots`

Ownership resolved via: `weather_snapshots.tournament_id → tournaments.user_id`

| Policy | Claim |
|---|---|
| `weather_snapshots_select_own` | A parent can only **see** weather data for their own tournaments. |
| `weather_snapshots_insert_own` | The backend service role inserts weather snapshots; this policy ensures the `tournament_id` references a tournament the calling user owns. (Service role bypasses RLS — this applies to user-facing API calls.) |
| `weather_snapshots_update_own` | A parent can only **update** weather data for their own tournaments. |
| `weather_snapshots_delete_own` | A parent can only **delete** weather data for their own tournaments. |

---

### `food_options`

Ownership resolved via: `food_options.tournament_id → tournaments.user_id`

| Policy | Claim |
|---|---|
| `food_options_select_own` | A parent can only **see** food options cached for their own tournaments. |
| `food_options_insert_own` | Only insertable for the calling user's own tournaments. |
| `food_options_update_own` | Only updatable for the calling user's own tournaments. |
| `food_options_delete_own` | Only deletable for the calling user's own tournaments. |

---

### `plans`

Ownership resolved via: `plans.tournament_id → tournaments.user_id`

| Policy | Claim |
|---|---|
| `plans_select_own` | A parent can only **retrieve** plans for their own tournaments. Another parent cannot access a plan by guessing its UUID. |
| `plans_insert_own` | A plan can only be **created** under the calling user's own tournament. |
| `plans_update_own` | A plan can only be **edited** by its owner. |
| `plans_delete_own` | A plan can only be **deleted** by its owner. Cascades to feedback rows. |

---

### `feedback`

Ownership resolved via: `feedback.plan_id → plans.tournament_id → tournaments.user_id`

| Policy | Claim |
|---|---|
| `feedback_select_own` | A parent can only **see** feedback they submitted (for their own plans). |
| `feedback_insert_own` | A parent can only **submit** feedback for plans under their own tournaments. |
| `feedback_update_own` | A parent can only **edit** their own feedback. |
| `feedback_delete_own` | A parent can only **delete** their own feedback. |

---

## Performance Notes

- All FK columns referenced in RLS subqueries have explicit indexes (created in `0002_tables.sql`).
- The `(select auth.uid())` pattern (parenthesised subquery) hints to the Postgres query planner to evaluate `auth.uid()` once per query rather than once per row — critical for tables with many rows.
- Two-hop policies (`match_scenarios`, `feedback`) use `JOIN` rather than nested subqueries to give the planner maximum flexibility.

---

## Service Role Bypass

The Supabase service role key bypasses RLS entirely. The FastAPI backend **must** use the service role key (`SUPABASE_SERVICE_ROLE_KEY`) only on the server side and must never expose it to clients. Client-facing Supabase calls must use the anon key with a user JWT so RLS is enforced.
