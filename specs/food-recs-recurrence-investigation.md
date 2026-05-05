# Food Recommendations Recurrence — Investigation Plan

**Date:** 2026-05-04  
**Symptom:** User reports "adding the first match is not providing food recommendations" — same symptom as the prior round's bug, which supposedly shipped a fix (camelCase aliases on TournamentCreate/MatchCreate + geo-agnostic MockPlacesProvider + NULL-coords warning).  
**Status:** ACTIVE — executing top-down.

---

## Code-review findings before diagnostics

From reading the source before running a single command:

| Finding | File | Implication |
|---------|------|-------------|
| `_fetch_places_async` returns `[]` when `venue_lat is None or venue_lng is None` | `routes/plans.py:280` | If tournament has NULL coords, places always empty |
| no_next_match fallback: `if not food_buckets and raw_places: food_buckets = ["quick_pickup"]` | `routes/plans.py:435` | Fallback only fires when raw_places is non-empty — no food if coords null |
| `assemble_food_options([], [])` → `non_bag = []` → `return [], True` | `rules/food.py:500` | Bag-fallback-only when both args empty |
| `TournamentCreate.model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)` | `routes/tournaments.py:39` | Fix IS on disk — accepts both snake and camelCase from iOS |
| iOS `postEncoder.keyEncodingStrategy = .convertToSnakeCase` | `Repository.swift:36` | iOS sends snake_case → accepted by `populate_by_name=True` |
| `VenueSearchViewModel.select()` catch block silently swallows errors | `VenueSearchViewModel.swift:95` | If MKLocalSearch fails, selectedVenue stays nil, Save button disabled — user can't save without coords |
| `SelectedVenue.venueLat: Double` (non-optional) | `VenueSearchViewModel.swift:13` | Coords are never nil when selectedVenue is non-nil |
| Migration `0017_match_done_state.sql` — applied during done-toggle fix | `db/supabase/migrations/` | Migration state known for 0017 only |

**Triage based on code reading alone:**  
If venue coords are present in DB → raw_places will be non-empty (MockPlacesProvider is geo-agnostic) → no_next_match fallback fires → food options appear.  
Root cause must be one of: (A) coords null in DB (stale uvicorn / encoding bug), (D) migration not applied causing 500s, or (K) plan-gen silently 500ing for a different reason.

---

## Hypothesis catalog

**Order: cheapest-evidence first, then likelihood.**

### H-A: Stale uvicorn process
**Symptom that proves it:** Running `git log --oneline -5 routes/tournaments.py` shows recent commits the running server hasn't loaded.  
**Evidence command:** `ps aux | grep uvicorn` + `git log --oneline -3 apps/api/src/playfuel_api/routes/tournaments.py`  
**Kill criterion:** `model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)` IS on disk AND uvicorn was started before that commit.  
**Dependency:** Check disk state first; then check process start time.  
**Check-cost:** Very cheap (2 greps).

### H-B: Venue coords genuinely null in DB (prior-created tournaments)
**Symptom:** Tournaments created before the camelCase fix have NULL `venue_lat`/`venue_lng` in DB. Plan gen always warns "raw_places=0 despite valid venue coords" — except it doesn't warn because coords ARE null and it hits the "plan generated without venue coords" branch.  
**Evidence command:** Direct DB query for recent tournament rows.  
**Kill criterion:** At least one tournament has non-null `venue_lat`.  
**Dependency:** H-A must not block (stale server wouldn't store coords at all).  
**Check-cost:** Cheap but requires DB access (or checking uvicorn logs).

### H-C: Migration 0017 not applied causing 500 on plan-gen (DR-18 redux)
**Symptom:** `plan_gen` endpoint returns 500, iOS catches and shows error toast. `is_done` column missing from `matches` table.  
**Evidence command:** `supabase migration list` or direct psql column check.  
**Kill criterion:** Migration 0017 listed as applied.  
**Check-cost:** Very cheap.

### H-D: `places_provider` setting unknown / misconfigured
**Symptom:** `find_nearby_food` logs an error, returns `[]` even with valid coords.  
**Evidence:** `grep -n "PLACES_PROVIDER\|places_provider" apps/api/src/playfuel_api/settings.py`  
**Kill criterion:** Setting defaults to "auto" or "mock" with a defined fallback.  
**Check-cost:** Very cheap (1 read).

### H-E: First-match no_next_match + NULL coords double-miss
**Symptom:** The `§G.5` fallback only adds `["quick_pickup"]` when `raw_places` is non-empty. If coords null → `raw_places=[]` → fallback never fires → `assemble_food_options([], [])` → `bag_fallback_only=True, options=[]`.  
This is NOT a bug in the fallback logic — it's correct behaviour for the case where the venue has no coords. The bug is upstream: why are coords null?  
**Evidence:** If coords are null, this is the mechanism. Fix is ensuring coords are stored.  
**Kill criterion:** Not applicable — this is the result of H-B.  
**Check-cost:** Already diagnosed from code reading.

### H-F: iOS bagFallbackOnly banner misread as "no food recommendations"
**Symptom:** User sees the bag-only banner ("Bring snacks from your bag") and reads it as "no food recommendations."  
**Evidence:** Read `FoodOptionDeckView` / `FoodDeckView` to see how `bagFallbackOnly=True` + empty options is rendered.  
**Kill criterion:** Find the iOS rendering path for `bagFallbackOnly=True`.  
**Check-cost:** Very cheap (1 file read).

### H-G: Plan-gen endpoint 500 silently (a la done-toggle bug)
**Symptom:** Plan-gen returns 500 (e.g. column unknown after incomplete migration), iOS `generatePlan` throws, AppState sets `.failed`. User sees error UI, not food.  
**Evidence:** Check if ANY migration added a column to `matches` that `select('*')` now reads and might break MatchRow instantiation.  
**Kill criterion:** `MatchRow(**m)` succeeds with all columns present.  
**Check-cost:** Cheap — check MatchRow fields vs migration list.

### H-H: postEncoder encodes `venueLat` → something OTHER than `venue_lat`
**Symptom:** iOS sends a key Pydantic doesn't recognize → field is None.  
**Evidence:** Test `.convertToSnakeCase` on `venueLat` in isolation.  
**Kill criterion:** `.convertToSnakeCase` on `venueLat` → `venue_lat` as expected.  
**Check-cost:** Can be verified by reading the Swift JSONEncoder docs / writing a test.

### H-I: Test suite regression introduced by recent session changes
**Symptom:** One of the changes in the match-done-state or chain-menu sessions broke the food path.  
**Evidence:** Run the full test suite.  
**Kill criterion:** Suite shows 666+ passed, 0 failed.  
**Check-cost:** Medium (runs tests).

---

## Execution

See below — hypotheses executed top-down.

---

## Fix shapes (TBD — complete after diagnosis)

- If H-A (stale uvicorn): provide restart command + documentation of the deployment process.
- If H-B (coords null in DB): investigate whether old tournaments can be updated, or just create a new tournament to verify fix works going forward.
- If H-C (migration 0017 not applied): `supabase migration up`, verify column exists.
- If H-F (banner misread): clarify to user what "no food recommendations" looks like vs bag-fallback, potentially improve the copy.

---

## Self-verification gate (after fix)

```bash
grep -n "model_config.*to_camel" apps/api/src/playfuel_api/routes/tournaments.py
# Expected: line 39 with ConfigDict(alias_generator=to_camel, populate_by_name=True)

grep -n "plan_gen:" apps/api/src/playfuel_api/routes/plans.py | head -5
# Expected: ≥2 matches (weather+places log + raw_places warning)

cd apps/api && python3.12 -m pytest src/playfuel_api/tests/ 2>&1 | tail -5
# Expected: 666 passed, 0 failed (or higher after any new tests)

# Verify food option path works for no_next_match case:
cd apps/api && python3.12 -c "
from playfuel_api.services.places import MockPlacesProvider
from playfuel_api.rules.food import assemble_food_options
raw = list(MockPlacesProvider().search_nearby(32.78, -96.80, 3000, 5))
opts, bag = assemble_food_options(raw, ['quick_pickup'])
print(f'food_options={len(opts)} bag_fallback={bag}')
assert len(opts) > 0 and not bag, 'FAIL: no food options for quick_pickup'
print('PASS: no_next_match quick_pickup fallback produces food options')
"
# Expected: PASS
```

---

## Open questions surfaced during investigation

- **OQ-FOOD-3**: When `venue_lat`/`venue_lng` are NULL (user created tournament without coordinates in an older client build), the food section is permanently empty. There's no way to add coords to an existing tournament without deleting and recreating. Should there be a PUT /v1/tournaments/{tid} call from TournamentDashboardView with a venue edit option? Or at minimum, a "no venue location" empty state that suggests re-creating the tournament?
- **OQ-FOOD-4**: Should `_fetch_places_async` fall back to `MockPlacesProvider` when venue coords are NULL, rather than returning `[]`? This would give users food options even without GPS coordinates (using Dallas demo data). Tradeoff: the mocked data would be geographically wrong for non-Dallas users. Better UX choice: give a clear "food options require venue location" message in iOS.
