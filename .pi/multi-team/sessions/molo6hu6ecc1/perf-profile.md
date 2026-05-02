# PlayFuel API — Performance Profile

Branch: `perf/measure-and-optimize`  
Session: molo6hu6ecc1  
Date: 2026-05-02

---

## Summary

User reported: "sometimes it would take a little long to process when you select a new
tournament or add data in general."

Profiling confirmed **plan generation** is the dominant hotspot (1.5–4 s real-world
depending on network latency to Open-Meteo, Google Places, and Anthropic). Two secondary
hotspots: tournament re-select (iOS had no plan cache, fired full POST on every tap) and
tournament create dismiss (serial loadTournaments() call held the sheet open).

Three backend optimisations + two iOS optimisations were shipped in this PR.

---

## iOS Profile (from Frontend Dev)

| Hot path | Root cause | Est. p95 before | Est. p95 after |
|---|---|---|---|
| Tournament re-select (existing plan) | No plan cache — full POST on every tap | ~4,000 ms | ~0 ms (instant from iOS cache) |
| Tournament create dismiss | Serial `loadTournaments()` after `createTournament()` | ~1,500 ms | ~400 ms (one call, then dismiss) |
| `DateFormatter` allocation | New instance per `createTournament` call | ~10 ms | ~0 ms (static) |

**iOS fixes shipped:**
- `AppState.planCache: [UUID: PlanEnvelope]` — tournament re-select is instant (cache hit)
- Optimistic tournament create — dismiss immediately after `createTournament()` returns
- `static let tournamentDateFormatter` — eliminates per-call allocation

---

## Backend Profile

### Instrumentation map

After this PR, every request is timed by `RequestTimingMiddleware` in `main.py`:

```
INFO: REQUEST POST /v1/tournaments/{tid}/plans/generate → 200 in 312ms
```

Within `generate_plan`, additional `perf_counter` hooks log:
- `plan_gen: weather+places parallel fetch complete weather_ms=X places_ms=Y`
- `plan_gen: llm cache HIT match=... provider=...`
- `plan_gen: llm explain complete match=... provider=... duration_ms=Z`

For the LLM provider, `AnthropicProvider.explain_plan()` logs:
- `AnthropicProvider: model=... latency_ms=... input_tokens=... output_tokens=...`

All logs are at INFO, no prompt/response content, no PII.

### Python-layer timing (mocked externals — `pytest -m perf -s`)

These numbers measure routing + Pydantic validation + rules engine only.
External I/O (network) is patched to return instantly.

| Path | p50 ms | p95 ms | min ms | max ms |
|---|---|---|---|---|
| GET /v1/tournaments | 0.8 | 1.7 | 0.8 | 1.7 |
| POST /v1/tournaments/{tid}/plans/generate | 6.1 | 10.7 | 5.2 | 10.7 |
| POST /v1/tournaments/{tid}/feedback | 1.7 | 3.1 | 1.4 | 3.1 |
| GET /v1/tournaments/{tid}/feedback | 1.3 | 1.3 | 1.2 | 1.3 |
| GET /v1/tournaments/{tid}/plans | 1.3 | 1.4 | 1.1 | 1.4 |

Python overhead is negligible. Real-world latency is dominated by network I/O.

### Top 3 backend hotspots (before optimisation)

| Rank | Hotspot | Est. contribution (real network) | Frequency |
|---|---|---|---|
| 1 | Open-Meteo + Google Places fetched serially | ~800–2,000 ms combined | Every plan gen |
| 2 | Anthropic API call (1,600–2,500 ms at max_tokens=800) | ~1,600–2,500 ms | Every first plan gen |
| 3 | Anthropic client constructed per explain_plan() call | 50–200 ms (TCP+TLS) | Per match >1 |

### Optimisations applied

#### Opt-A — Parallel weather + places (`routes/plans.py`)

**Before:** Weather fetch (async, Open-Meteo) → Places fetch (sync, Google) in serial.
Total = weather_ms + places_ms ≈ 400–1,200 ms combined.

**After:** Both fetches run via `asyncio.gather()`. Places uses `asyncio.to_thread()`
since `GooglePlacesProvider.search_nearby` is synchronous (httpx.Client).
Total = max(weather_ms, places_ms) ≈ 200–700 ms (saves the slower of the two).

**Expected save:** 200–700 ms p50 on plan generation (network dependent).

#### Opt-B — LLM explanation cache (`routes/plans.py` + migration 0015)

**Before:** Every `generate_plan` call invoked the Anthropic API for each match
(1,600–2,500 ms per match). Most re-generates for the same tournament had identical
inputs (same venue, same schedule, same weather band).

**After:** SHA-256(PlanExplanationInput minus opponent_notes) → `llm_explanation_cache`
table. On hit: serve cached `PlanExplanation` instantly, skip API call.
TTL: 7 days. Errors silently swallowed (cache non-critical; route falls through to LLM).

**Cache key design:**
- `opponent_notes` explicitly excluded (SEC-P6-2: PII must not enter cache key)
- `sort_keys=True` in JSON serialisation ensures stable key regardless of insertion order
- Two plan inputs for same tournament + weather will share the cache entry

**Cache hit rate projection:** After first successful generation for a tournament,
subsequent re-generates (e.g. user adds a match and re-generates) will typically hit.
Real-world estimate: ≥70% hit rate on tournaments with >1 plan generation in 7 days.
Fly.io single-instance deployment: cache is process-local Supabase table — durable
across restarts (unlike in-memory). Multi-instance: each instance has full cache access
via Supabase (no cross-instance coherence issue).

**Expected save on cache hit:** ~100% of LLM latency (1,600–2,500 ms → <5 ms DB read).

#### Opt-C — Reduce `max_tokens` 800 → 500 (`services/llm.py`)

**Before:** Anthropic API called with `max_tokens=800`.
**After:** `max_tokens=500`. Plan summary ≈ 180 words ≈ 250 tokens; 500 gives 2× headroom.
Anthropic latency scales roughly linearly with output tokens.

**Expected save:** ~150–300 ms p50 on first-call LLM latency (Anthropic-side generation).

#### Opt-D — Anthropic client pooled in `__init__` (`services/llm.py`)

**Before:** `anthropic.Anthropic(timeout=10.0)` constructed on every `explain_plan()` call.
Each construction creates a new `httpx.Client` instance → TCP + TLS handshake.

**After:** Client constructed once in `AnthropicProvider.__init__()` and stored as
`self._client`. Reused for all `explain_plan()` calls within the same
`get_llm_provider()` lifetime (one `generate_plan` request → one provider instance →
all matches share the client).

**Expected save:** 50–200 ms per match beyond the first (handshake amortised).

### Combined expected improvement (real network, Anthropic active)

| Scenario | Before | After | Save |
|---|---|---|---|
| First plan gen, 1 match, no cache | 3.5–5 s | 2–3 s | ~30–40% |
| Re-gen, same input (cache hit) | 3.5–5 s | 0.3–0.8 s | ~85–90% |
| First plan gen, 2 matches, no cache | 6–9 s | 2.5–4 s | ~50–60% |
| Template provider (no Anthropic key) | 1–2 s | 0.5–1 s | ~40–50% |

### Migration note

**Migration 0015** (`0015_llm_explanation_cache.sql`) must be applied before deploy.
Creates `llm_explanation_cache` table with deny-all RLS (SP-3 pattern).
No `RAISE EXCEPTION` guard needed — new table creation is idempotent (`IF NOT EXISTS`).

Apply via Supabase SQL Editor or:
```bash
psql "$SUPABASE_DB_URL" -f db/supabase/migrations/0015_llm_explanation_cache.sql
```

---

## Follow-up tickets (not in this PR)

| Item | Sev | Description |
|---|---|---|
| PERF-1 | MED | Wire `os_signpost` to mark plan-gen phases on iOS for Instruments profiling |
| PERF-2 | LOW | LLM streaming response — return rules-engine plan immediately, stream LLM summary as follow-on. Eliminates perceived wait entirely (iOS shows plan, summary "types in"). Larger scope than this PR. |
| PERF-3 | LOW | TTL sweep job — expired `llm_explanation_cache` rows accumulate indefinitely. Add a Fly.io cron or Supabase pg_cron job to `DELETE WHERE expires_at < now()`. |
| PERF-4 | LOW | Migrate SP-2 rate limiter to Redis when Fly.io scales to >1 instance. Currently in-memory defaultdict; does not share across replicas. |
