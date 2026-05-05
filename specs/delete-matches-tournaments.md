# Delete Matches & Tournaments

> **Feature spec** · single-pass · hard delete · MVP
> **Author:** PM · **Date:** 2026-05-04
> **Branch target:** `feat/delete-matches-tournaments`

---

## §A Summary

PlayFuel parents can delete a tournament (and everything under it) or a single match from
within the iOS app. Deletion is hard (data is gone immediately, no recovery), consistent with
`PRIVACY_V1.md §7.3`'s "data is actually gone" contract and Apple's in-app deletion
guideline (App Store Review 5.1.1(v)). All cascades are enforced by existing Postgres FK
rules — **no new DB migration is required**. The two API DELETE endpoints already exist in
the codebase but return `204` unconditionally; they must be patched to return `404` on
not-found/not-owned rows. iOS needs swipe actions on the tournament list and an overflow
menu on the tournament and match detail screens.

---

## §B Cascade & Schema

### B.1 FK Audit — verified from migrations 0002–0016

| Child table | FK column | Parent | `ON DELETE` | Source migration | Survives tournament delete? | Survives match delete? |
|---|---|---|---|---|---|---|
| `matches` | `tournament_id` | `tournaments(id)` | **CASCADE** | 0002 | ❌ deleted | — |
| `match_scenarios` | `match_id` | `matches(id)` | **CASCADE** | 0002 | ❌ deleted | ❌ deleted |
| `plans` | `tournament_id` | `tournaments(id)` | **CASCADE** | 0002 | ❌ deleted | — |
| `plans` | `match_id` | `matches(id)` | **CASCADE** | 0008 | ❌ deleted (via both FKs) | ❌ deleted |
| `match_evaluations` | `match_id` | `matches(id)` | **CASCADE** | 0011 | ❌ deleted | ❌ deleted |
| `weather_snapshots` | `tournament_id` | `tournaments(id)` | **CASCADE** | 0002 | ❌ deleted | — |
| `food_options` | `tournament_id` | `tournaments(id)` | **CASCADE** | 0002 | ❌ deleted | — |
| `feedback` | `tournament_id` | `tournaments(id)` | **CASCADE** | 0013 | ❌ deleted | — |
| `feedback` | `plan_id` | `plans(id)` | **SET NULL** | 0013 | ❌ deleted (via `tournament_id` CASCADE first) | ✅ survives (plan_id → null) |
| `player_notes` | `match_id` | `matches(id)` | **SET NULL** | 0010 | ✅ survives (match_id → null) | ✅ survives (match_id → null) |

### B.2 Effective cascade result

**Tournament delete** removes: `tournaments`, `matches`, `match_scenarios`, `plans`,
`match_evaluations`, `weather_snapshots`, `food_options`, `feedback`. Surviving rows:
`player_notes` (match_id set to null — the note body is retained, the match link is
severed). No orphaned rows possible given the FK graph.

**Match delete** removes: `match_scenarios`, `plans` (match-scoped), `match_evaluations`.
Surviving rows: `feedback` (plan_id set to null, tournament link kept), `player_notes`
(match_id set to null).

### B.3 Migration decision

**No new migration required.** All FKs already carry the correct `ON DELETE` behaviour.
Next free migration number for reference: **0017**.

---

## §C API Contract

Both DELETE endpoints already exist in the codebase. They are **partially correct** (correct
status code, correct RLS-via-JWT pattern, correct cascade) but have a behaviour defect:
they return `204` unconditionally, even when no row was deleted. Engineering must patch both
to return `404` when `result.data` is empty (RLS blocked or row absent) — the same pattern
used by `update_tournament` / `update_match`.

### C.1 Endpoint shapes (locked)

```
DELETE /v1/tournaments/{id}
  Auth:    Bearer JWT (verify_supabase_jwt)
  Body:    none
  Success: 204 No Content
  Error:   404 Not Found   — row absent or owned by another user (RLS returns empty)
                              body: {"detail": "Tournament not found"}
  Never:   403 — prevents existence enumeration

DELETE /v1/tournaments/{tid}/matches/{mid}
  Auth:    Bearer JWT
  Body:    none
  Success: 204 No Content
  Error:   404 Not Found
              body: {"detail": "Match not found"}
  Never:   403
```

### C.2 404-fix patch (both routes)

Replace the unconditional `return Response(status_code=204)` with:

```python
# tournaments.py — delete_tournament
result = client.table(_TABLE).delete().eq("id", str(tid)).execute()
if not result.data:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail="Tournament not found")
return Response(status_code=status.HTTP_204_NO_CONTENT)

# matches.py — delete_match
result = (
    client.table(_TABLE)
    .delete()
    .eq("id", str(mid))
    .eq("tournament_id", str(tid))
    .execute()
)
if not result.data:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                        detail="Match not found")
return Response(status_code=status.HTTP_204_NO_CONTENT)
```

### C.3 Idempotency

Deleting an already-deleted ID returns `404` — **not** `204`. We do not fake success.
Re-calling DELETE on a valid (existing) ID returns `204` and removes the row.

### C.4 No new schemas

No request body, no new Pydantic model, no new router registration (both routers are
already mounted in `routes/__init__.py`).

---

## §D iOS UX

### D.1 Entry points

| Surface | Trigger | Component change needed |
|---|---|---|
| Tournament list row (`TournamentListView`) | Left-swipe → red **Delete** button | Add `.swipeActions(edge: .trailing)` to `NavigationLink` row in `list()` helper |
| Tournament detail screen (`TournamentDashboardView`) | Toolbar `•••` (`Menu`) → **Delete tournament** (`.destructive` role) | Add `Menu` button to toolbar alongside existing `+` and profile buttons |
| Match detail screen (`MatchDetailView`) | Toolbar `•••` (`Menu`) → **Delete match** (`.destructive` role) | Add `Menu` button to toolbar (currently only has "Done") |

> 🔴 **OQ-DEL-1 — Match list swipe not feasible on current architecture.** The pre-baked
> spec listed "Match list (within tournament detail): left-swipe" as an entry point. Disk
> verification shows the match list is `ScheduleStripView` — a horizontal `LazyHStack`, not
> a `List`. SwiftUI `.swipeActions` requires a `List` row; it cannot be applied to a
> `LazyHStack` chip. **Ruling:** scope match delete to `•••` menu on `MatchDetailView` only
> for MVP. If Engineering wants swipe-to-delete on matches, they must first introduce a
> separate vertical match list screen — defer to follow-up.

### D.2 Confirmation sheet — `.confirmationDialog` (native iOS)

**Tournament delete:**

```
Title:   "Delete tournament?"

Message (dynamic):
  • Has matches:   "This will also delete {N} match{es}, {N} plan{s}, and any
                    feedback. This can't be undone."
  • No matches:    "This can't be undone."
  • Tournament is today (start_date == today, either case):
                   prepend "This tournament is today. "

Buttons:
  [Delete]   — .destructive role
  [Cancel]   — default
```

**Match delete:**

```
Title:   "Delete match?"

Message: "This will also delete the plan and any feedback for this match.
          This can't be undone."

Buttons:
  [Delete]   — .destructive role
  [Cancel]   — default
```

### D.3 Post-delete navigation

- **Deleted from tournament list (swipe):** remove row from list; no navigation needed.
- **Deleted from tournament detail (`•••` menu):** pop back to `TournamentListView` after
  confirmation. AppState's tournament list updates (optimistic removal or re-fetch).
- **Deleted from match detail (`•••` menu):** dismiss `MatchDetailView` sheet, then
  re-generate plan for the tournament (same flow as adding a match).

### D.4 Optimistic UI + error recovery

1. On user confirmation tap: remove the item from local state immediately (optimistic).
2. Fire `DELETE` API call.
3. **On success (204):** done — no further action.
4. **On failure (any error):** restore the item to local state; show an inline error toast
   (`"Couldn't delete — please try again."`) for 3 seconds. No retry sheet.

---

## §E Telemetry

Fire-and-forget analytics events (no PII; no blocking call):

```
tournament_deleted
  tournament_id:   <uuid>          (internal; not sent to 3rd-party analytics in MVP)
  match_count:     Int             (number of matches cascaded)
  plan_count:      Int
  had_feedback:    Bool

match_deleted
  match_id:        <uuid>
  tournament_id:   <uuid>
  had_plan:        Bool
  had_evaluation:  Bool
```

In MVP: log to the iOS `Logger` (Unified Logging / Console.app) only. No third-party
analytics endpoint (consistent with `PRIVACY_V1.md §6.1`).

---

## §F Edge Cases

| Edge case | Handling |
|---|---|
| **Tournament is today** (`start_date == today`) | Confirmation sheet prepends `"This tournament is today. "` — no block, parent decides |
| **Deleting the last tournament** | Allowed; `TournamentListView` renders its existing empty state after removal |
| **Network failure mid-delete** | Optimistic state restored; error toast shown; row re-appears in list |
| **Deleted from detail screen (tournament or match)** | Pop/dismiss back to parent list; list re-fetches or removes row optimistically |
| **Already-deleted ID (double-tap race)** | API returns `404`; iOS treats it as silent success (item is already gone from local state) |
| **Concurrent plan generation during delete** | Not guarded in MVP; plan generation for the deleted tournament will return `404` on next poll — handled by existing error state |

---

## §G Deferred / Out of Scope

| Item | Rationale |
|---|---|
| Soft delete / trash bin / 30-day recovery | No demand signal; hard delete aligns with PRIVACY_V1 |
| Bulk delete / multi-select | Not needed for single-parent MVP; adds complexity |
| Undo snackbar | Confirmation sheet is the undo mechanism in MVP |
| Export before delete | Covered by separate account-export flow (PRIVACY_V1 §7) |
| Active-match lock ("tournament locked while in progress") | Parent owns data; trust + confirm pattern chosen |
| Audit log of deletions | No compliance requirement in MVP |
| Match delete via swipe on `ScheduleStripView` | Requires vertical match list screen; deferred — see OQ-DEL-1 |

---

## §H Acceptance Criteria

1. **Tournament delete — full cascade:** Parent can delete a tournament from the tournament
   list via left-swipe; confirmation sheet shows accurate match count; on confirm, the
   tournament and all FK-cascaded rows (`matches`, `match_scenarios`, `plans`,
   `match_evaluations`, `feedback`, `weather_snapshots`, `food_options`) are removed from
   the database and the list updates within 1 s. `player_notes` linked to the tournament's
   matches survive with `match_id = null`.

2. **Match delete:** Parent can delete a single match from the match detail screen via the
   overflow menu; confirmation sheet shows; on confirm, the match and its
   `match_scenarios`, `plans`, and `match_evaluation` are removed. `feedback` rows survive
   with `plan_id = null`. `player_notes` survive with `match_id = null`.

3. **Hard delete verifiable:** Post-delete, no rows remain in the DB referencing the
   deleted `tournament_id` or `match_id` across all FK tables (assertable via
   `SELECT count(*) = 0` across all cascaded tables by tournament/match ID).

4. **RLS enforced:** Parent A's `DELETE /v1/tournaments/{B_owned_id}` returns `404` (not
   `403`, not `204`); B's data is untouched. Same for `DELETE /v1/tournaments/{tid}/matches/{mid}`.

5. **Detail-screen navigation:** If the deleted entity was the active detail screen (tournament
   detail or match detail), the app pops/dismisses back to the parent list without crashing
   or showing a stale row.

---

## §I PM Verification Findings

> Pre-scribe disk verification. All findings are sourced from actual file reads.
> 🔴 = real contradiction with a pre-baked decision. OQ = open question raised.

| # | Finding | File : line | Status |
|---|---|---|---|
| I-1 | Migrations 0001–0016 exist; next free number = **0017** | `db/supabase/migrations/` (ls) | ✅ |
| I-2 | `matches.tournament_id` → `ON DELETE CASCADE` | `0002_tables.sql:~L120` | ✅ |
| I-3 | `match_scenarios.match_id` → `ON DELETE CASCADE` | `0002_tables.sql:~L152` | ✅ |
| I-4 | `weather_snapshots.tournament_id` → `ON DELETE CASCADE` | `0002_tables.sql:~L168` | ✅ |
| I-5 | `food_options.tournament_id` → `ON DELETE CASCADE` | `0002_tables.sql:~L188` | ✅ |
| I-6 | `plans.tournament_id` → `ON DELETE CASCADE` | `0002_tables.sql:~L210` | ✅ |
| I-7 | `feedback.plan_id` was changed from CASCADE → **SET NULL** by migration 0013 | `0013_feedback_schema_v2.sql:~L54` | ✅ (feedback survives match delete) |
| I-8 | `feedback.tournament_id` → `ON DELETE CASCADE` (new FK added by 0013) | `0013_feedback_schema_v2.sql:~L79` | ✅ (feedback fully removed on tournament delete) |
| I-9 | `plans.match_id` → `ON DELETE CASCADE` (0008 `ADD COLUMN`) | `0008_per_match_plans.sql:~L29` | ✅ |
| I-10 | `match_evaluations.match_id` → `ON DELETE CASCADE` (0011) | `0011_match_evaluations.sql:~L78` | ✅ |
| I-11 | `player_notes.match_id` → `ON DELETE SET NULL` (0010) | `0010_players_and_notes.sql:~L108` | ✅ (notes survive with match_id nulled) |
| I-12 | **`DELETE /v1/tournaments/{tid}` ALREADY EXISTS** in `routes/tournaments.py` | `routes/tournaments.py:~L131` | 🔴 returns `204` unconditionally — must add `if not result.data: raise 404` |
| I-13 | **`DELETE /v1/tournaments/{tid}/matches/{mid}` ALREADY EXISTS** in `routes/matches.py` | `routes/matches.py:~L201` | 🔴 returns `204` unconditionally — same 404-fix required |
| I-14 | Both routers already registered in `routes/__init__.py` | `routes/__init__.py:L16-L22` | ✅ no new registration needed |
| I-15 | `TournamentListView` uses `List` + `NavigationLink` rows — swipeActions **feasible** | `TournamentListView.swift:~L57` | ✅ |
| I-16 | `TournamentDashboardView` toolbar has only `+` and profile — no `•••` Menu exists | `TournamentDashboardView.swift:~L50` | ✅ must add `Menu` button |
| I-17 | **`ScheduleStripView` is a horizontal `LazyHStack`, NOT a `List`** — `.swipeActions` cannot be applied | `ScheduleStripView.swift:~L48` | 🔴 OQ-DEL-1 |
| I-18 | `MatchDetailView` toolbar has only "Done" — no `•••` Menu exists | `MatchDetailView.swift:~L50` | ✅ must add `Menu` button |
| I-19 | `PRIVACY_V1.md §7.2` cascade graph predates migrations 0011 + 0013; does not show `match_evaluations`, updated `feedback` FK, or `player_notes` SET NULL | `PRIVACY_V1.md:§7.2` | Minor — not blocking; PRIVACY_V1 should be updated post-feature |

### Open Questions

| ID | Question | Owner | Blocking? |
|---|---|---|---|
| **OQ-DEL-1** | `ScheduleStripView` is a horizontal chip strip, not a `List` — `.swipeActions` can't be attached. Should Engineering (a) accept menu-only match delete for MVP (recommended), or (b) add a separate vertical match list screen to enable swipe? | Engineering Lead | Yes (scoping decision before iOS work starts) |
