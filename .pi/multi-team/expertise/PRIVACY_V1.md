# PlayFuel — Privacy, COPPA & App Store Disclosure (v1)

> **Status:** v1 draft for legal review · **Authority:** Planning Lead · **Last updated:** 2026-04-26
> **Sources of truth:**
> - Data inventory derived from `db/supabase/migrations/0001_extensions_and_enums.sql` and `0002_tables.sql` (read & walked column-by-column — no invented fields).
> - Cascade behaviour and ownership graph derived from `db/supabase/migrations/0002_tables.sql` and `0003_rls.sql`.
> - Auth surface derived from `db/supabase/auth/sign-in-with-apple.md` and `0004_auth_trigger.sql`.
> - Product posture from `PRD.md §11`, `MVP_SCOPE.md`, `SAFETY_DISCLAIMERS.md §F`.
>
> **This document will go to legal counsel before any public launch (OQ-06).**
> Format is numbered, tabular, and free of marketing prose.

---

## 0. Definitions

| Term | Definition |
|---|---|
| **Parent / User** | The natural person who creates a PlayFuel account via Sign in with Apple. The only category of authenticated user in MVP. Assumed to be ≥ 18. |
| **Player / Child** | The junior tennis player a Parent enters as a `player_profile`. **Never an authenticated user** in MVP. May be under 13. |
| **PII** | Personally Identifiable Information as defined by Apple App Store Review Guideline 5.1.1 and the FTC's COPPA rule. |
| **Personal Data of a Child** | Any data that identifies, contacts, or describes a child under 13 (COPPA §312.2). For PlayFuel: child first name (display name), birth year, age bracket, dietary/hydration/injury notes, and any tournament records that reference that child. |
| **Linked to user** | An Apple App Store privacy taxonomy term meaning the data is tied to the user's identity. |
| **Tracking** | Apple App Store taxonomy term meaning sharing data with third parties for cross-app/website advertising or data brokerage. |
| **MVP** | Phases 0–6 per `specs/PLAN.md`. Anything in Phase 7+ is out of scope for this document. |
| **Plan envelope** | The `plans.plan_json` JSONB output of the rules engine, plus `plans.llm_summary` text. |

---

## 1. Scope of This Document

| In scope | Out of scope (with rationale) |
|---|---|
| All `public.*` tables defined in `db/supabase/migrations/0002_tables.sql` | `auth.*` schema internals (managed by Supabase; we configure but do not author) |
| All MVP-phase data flows (Sign in with Apple → Supabase → FastAPI → iOS) | Phase 7+ features (feedback UI, beta analytics) — addressed in a future PRIVACY_V2 |
| App Store privacy questionnaire (App Store Connect "App Privacy" section) | GDPR DSAR tooling — no EU launch in MVP (Decision D-7) |
| COPPA posture and the parent-owned-account model | CCPA opt-out flows — no California-specific surfaces in MVP (Decision D-7) |
| Data retention and deletion contract | Advertising IDs / IDFA — none collected (Decision D-7) |
| Third-party data flows that *do* exist in MVP (Apple, Supabase, OpenAI, Google/Yelp, WeatherKit/OpenWeather) | Third-party data **sharing** for ad/marketing purposes (none — Decision D-7) |

---

## 2. Data Inventory (walked from migrations)

> Every column in every `public.*` table from `0002_tables.sql` is enumerated below.
> Audit scope: 9 tables, 67 columns. `created_at` / `updated_at` are listed once (§2.10).

### 2.1 Apple App Store Privacy Taxonomy — Legend

The "ASTC bucket" column maps to the App Store Connect "App Privacy" questionnaire categories:

| Code | Apple Category |
|---|---|
| **CI** | Contact Info (name, email, address, phone) |
| **HF** | Health & Fitness (health, fitness data) |
| **LOC-C** | Location — Coarse (location with ≤ 100 m precision) |
| **LOC-P** | Location — Precise (location with > 100 m precision) |
| **ID** | Identifiers (User ID, Device ID) |
| **UD** | Usage Data (product interaction, advertising data, other) |
| **DG** | Diagnostics (crash data, performance data, other diagnostic data) |
| **OUC** | Other User Content (e.g. customer support, free-form notes) |
| **PUR** | Purchases — **N/A in MVP** (no payment) |
| **FIN** | Financial Info — **N/A in MVP** |
| **SBH** | Sensitive — Sensitive Info (e.g. racial/sexual/religious) — **N/A in MVP** |

**Linked-to-user:** "Yes" if Supabase RLS ties the row to `auth.uid()` directly or via a one-/two-hop FK chain. Every PlayFuel row is linked to user.
**Used for tracking:** "No" everywhere — we ship **no third-party advertising or tracking SDKs in MVP** (Decision D-3).

---

### 2.2 `public.users` — account shadow row
> Source: `0002_tables.sql` lines `create table … public.users`. Inserted by `handle_new_user()` trigger (`0004_auth_trigger.sql`) on first Apple sign-in.

| Column | Type | Category | PII | COPPA-relevant | ASTC bucket | Notes |
|---|---|---|---|---|---|---|
| `id` | uuid | account / identifier | Yes | No (parent only) | **ID** (User ID) | Mirror of `auth.users.id`. Sole join key. |
| `created_at` | timestamptz | telemetry | No | No | DG | Account creation timestamp. |
| `updated_at` | timestamptz | telemetry | No | No | DG | Last modification. |

**Cross-reference (`auth.users`, managed by Supabase, not in `public.*`):**

| Column | Source | PII | ASTC bucket | Notes |
|---|---|---|---|---|
| `auth.users.email` | Apple ID token (`email` claim) | Yes (parent) | **CI** (Email) | May be Apple Private Relay (`*@privaterelay.appleid.com`) — we **never** un-relay (Decision D-1). |
| `auth.users.raw_user_meta_data.name` | Apple ID token (first sign-in only) | Yes (parent) | **CI** (Name) | Optional; Apple only sends on first sign-in. We do **not** copy into `public.users` (data minimisation — Decision D-2). |
| `auth.users.identities[…].provider_id` | Apple `sub` claim | Yes (parent) | **ID** | Stable per app; Apple-issued. |

---

### 2.3 `public.player_profiles` — child profile (COPPA-relevant)
> Source: `0002_tables.sql` lines `create table … public.player_profiles`. **All non-required columns are explicitly optional** per `SAFETY_DISCLAIMERS.md §F` and the column DDL (`text` with no `NOT NULL`).

| Column | Type | Category | PII | COPPA-relevant | ASTC bucket | Notes |
|---|---|---|---|---|---|---|
| `id` | uuid | identifier | No | No | ID | Internal PK. |
| `user_id` | uuid FK→users.id | identifier | Yes (parent) | No (parent ID, not child) | ID | RLS join key. |
| `display_name` | text NOT NULL | child profile | **Yes (child)** | **Yes** | **CI** (Name) | Free-form; we do not require last name. UX should encourage first-name-only. **Decision D-4.** |
| `birth_year` | int (range-checked 2005..current_year) | child profile | Yes (child) | **Yes** | **CI** (Other User Contact Info → "year of birth") | Year only — never `date_of_birth`. PRD §11. |
| `age_bracket` | text | child profile | Yes (child, indirect) | **Yes** | **CI** (Other) | e.g. "12U". Coarser than `birth_year`. |
| `dietary_notes` | text (optional) | health-adjacent | Yes (child) | **Yes** | **HF** (Health) | Parent-authored free-form. **Optional.** |
| `hydration_notes` | text (optional) | health-adjacent | Yes (child) | **Yes** | **HF** (Health) | Parent-authored free-form. **Optional.** |
| `injury_notes` | text (optional) | health-adjacent | Yes (child) | **Yes** | **HF** (Health) | Parent-authored free-form. **No medical advice stored.** **Optional.** |
| `created_at` / `updated_at` | timestamptz | telemetry | No | No | DG | — |

**COPPA classification:** This entire table is COPPA-relevant when the child is under 13. The parent-owned-account model (§3) is the legal basis for handling without verifiable parental consent.

---

### 2.4 `public.tournaments` — venue + dates
> Source: `0002_tables.sql` lines `create table … public.tournaments`.

| Column | Type | Category | PII | COPPA-relevant | ASTC bucket | Notes |
|---|---|---|---|---|---|---|
| `id` | uuid | identifier | No | No | ID | — |
| `user_id` | uuid FK→users.id | identifier | Yes (parent) | No | ID | RLS join key. |
| `name` | text NOT NULL | account | Low | Indirect | OUC | e.g. "Dallas Junior Open". Public-event name; not personal. |
| `venue_name` | text | account | Low | Indirect | OUC | e.g. "XYZ Tennis Center". |
| `venue_address` | text | location | Yes (low) | Indirect | **LOC-C** (Coarse) | Street address of venue, not residence. |
| `venue_city` | text | location | Low | Indirect | **LOC-C** | — |
| `venue_region` | text | location | Low | Indirect | **LOC-C** | State/province. |
| `venue_postal` | text | location | Low | Indirect | **LOC-C** | ZIP/postal. |
| `venue_lat` | numeric(9,6) | location | Yes | Indirect | **LOC-P** (Precise) | 6-decimal lat = ~11 cm theoretical, but **always a public venue**. **Never** the user/child residence. **Decision D-5.** |
| `venue_lng` | numeric(9,6) | location | Yes | Indirect | **LOC-P** | Same as lat. |
| `start_date` | date NOT NULL | account | No | No | OUC | — |
| `end_date` | date | account | No | No | OUC | — |
| `created_at` / `updated_at` | timestamptz | telemetry | No | No | DG | — |

**Privacy classification rationale (location):** Apple's privacy taxonomy treats lat/lng with > 100 m resolution as Precise Location. Our 6-decimal columns are *capable* of precise resolution, but the value space is **always a public tournament venue** (geocoded from a venue address the parent provided). We declare **LOC-P** out of an abundance of caution; UX must not allow the parent to enter a residential address as a "venue."

---

### 2.5 `public.matches` — match times
> Source: `0002_tables.sql` lines `create table … public.matches`.

| Column | Type | Category | PII | COPPA-relevant | ASTC bucket | Notes |
|---|---|---|---|---|---|---|
| `id` | uuid | identifier | No | No | ID | — |
| `tournament_id` | uuid FK→tournaments.id | identifier | No | No | ID | — |
| `scheduled_start` | timestamptz NOT NULL | account | No | Indirect | OUC | When the child is at a public venue. Combined with `tournament_id` → presence inference. |
| `estimated_duration_minutes` | int (nullable) | account | No | No | OUC | — |
| `actual_end_at` | timestamptz (nullable) | account | No | Indirect | OUC | Parent-entered post-match. |
| `surface` | text | account | No | No | OUC | "hard"/"clay"/"grass". |
| `format` | text | account | No | No | OUC | "singles"/"doubles". |
| `age_bracket` | text | child profile | Yes (child, indirect) | **Yes** | **CI** (Other) | Mirrors `player_profiles.age_bracket`. |
| `display_order` | int | account | No | No | OUC | — |
| `created_at` / `updated_at` | timestamptz | telemetry | No | No | DG | — |

---

### 2.6 `public.match_scenarios` — derived rules-engine output
> Source: `0002_tables.sql` lines `create table … public.match_scenarios`. All columns are **derived** from `matches` + `weather_snapshots` + RULES_CONSTANTS_V1. No new PII enters here.

| Column | Type | Category | PII | COPPA-relevant | ASTC bucket | Notes |
|---|---|---|---|---|---|---|
| `id` | uuid | identifier | No | No | ID | — |
| `match_id` | uuid FK→matches.id | identifier | No | No | ID | — |
| `scenario_kind` | enum | derived | No | No | OUC | short / normal / long. |
| `duration_minutes` | int | derived | No | No | OUC | — |
| `estimated_end_at` | timestamptz | derived | No | No | OUC | — |
| `gap_minutes` | int (nullable) | derived | No | No | OUC | — |
| `gap_status` | enum | derived | No | No | OUC | — |
| `food_bucket` | enum (nullable) | derived | No | No | OUC | — |
| `pickup_bucket` | enum (nullable) | derived | No | No | OUC | — |
| `rewarm_up_minutes` | int (nullable) | derived | No | No | OUC | — |
| `overrun_warning` | jsonb (nullable) | derived | No | No | OUC | Shape per RULES_CONSTANTS_V1.md §G.3. |
| `created_at` / `updated_at` | timestamptz | telemetry | No | No | DG | — |

---

### 2.7 `public.weather_snapshots` — venue weather
> Source: `0002_tables.sql` lines `create table … public.weather_snapshots`. All values are about a **venue**, not the user/child.

| Column | Type | Category | PII | COPPA-relevant | ASTC bucket | Notes |
|---|---|---|---|---|---|---|
| `id` / `tournament_id` | uuid | identifier | No | No | ID | — |
| `temp_f` | numeric(5,1) NOT NULL | derived (env) | No | No | OUC | — |
| `humidity_pct` | numeric(4,1) NOT NULL | derived (env) | No | No | OUC | — |
| `wind_mph` | numeric(5,1) | derived (env) | No | No | OUC | — |
| `precipitation_probability` | numeric(4,1) | derived (env) | No | No | OUC | — |
| `condition` | enum | derived (env) | No | No | OUC | — |
| `flag_hot` / `flag_very_hot` / `flag_humid` / `flag_cold` / `flag_windy` / `flag_rain_risk` / `flag_extreme_heat_risk` | boolean NOT NULL DEFAULT false | derived (env) | No | No | OUC | Denormalised for §E threshold-stability per `0002_tables.sql` comment. |
| `fetched_at` | timestamptz NOT NULL | telemetry | No | No | DG | — |
| `provider` | text NOT NULL | telemetry | No | No | DG | "weatherkit" / "openweather". |
| `created_at` / `updated_at` | timestamptz | telemetry | No | No | DG | — |

> **No raw geofences stored.** Lat/lng are on `tournaments`; weather is keyed by `tournament_id`. Per Decision D-5 we never store any location that is not a parent-entered tournament venue.

---

### 2.8 `public.food_options` — Places API cache
> Source: `0002_tables.sql` lines `create table … public.food_options`. All values describe **public commercial venues**, not the user/child.

| Column | Type | Category | PII | COPPA-relevant | ASTC bucket | Notes |
|---|---|---|---|---|---|---|
| `id` / `tournament_id` | uuid | identifier | No | No | ID | — |
| `place_name` | text NOT NULL | derived (3p) | No | No | OUC | Public restaurant name. |
| `place_id` | text | derived (3p) | No | No | ID | Provider-issued place ID (Google/Yelp). Not user-linked. |
| `distance_m` | int | derived | No | No | OUC | — |
| `category` | text | derived | No | No | OUC | — |
| `template_id` | text | derived | No | No | OUC | — |
| `recommended_order` | jsonb | derived | No | No | OUC | Templated text per RULES §F.3. **Never invented per `SAFETY_DISCLAIMERS.md §C`.** |
| `created_at` / `updated_at` | timestamptz | telemetry | No | No | DG | — |

---

### 2.9 `public.plans` — generated plan envelope
> Source: `0002_tables.sql` lines `create table … public.plans`.

| Column | Type | Category | PII | COPPA-relevant | ASTC bucket | Notes |
|---|---|---|---|---|---|---|
| `id` / `tournament_id` | uuid | identifier | No | No | ID | — |
| `plan_json` | jsonb NOT NULL | derived (AI-adjacent) | Indirect | **Yes (transitive)** | OUC | May contain references to child age bracket via embedded scenarios. |
| `llm_summary` | text (nullable) | derived (AI output) | Indirect | **Yes (transitive)** | OUC | Phase 6. **Subject to LLM-prompt-logging policy — §6.4.** |
| `rules_constants_version` | text NOT NULL | telemetry | No | No | DG | — |
| `warnings` | jsonb NOT NULL DEFAULT '[]' | derived | No | No | OUC | — |
| `schedule_confidence` | enum NOT NULL DEFAULT 'high' | derived | No | No | OUC | — |
| `created_at` / `updated_at` | timestamptz | telemetry | No | No | DG | — |

> **`plan_json` and `llm_summary` are not raw PII themselves**, but because they reference child-context data (age bracket, dietary/hydration notes via the rules engine inputs) they inherit the COPPA classification of their inputs.

---

### 2.10 `public.feedback` — post-tournament rating (Phase 7-bound, schema present in MVP)
> Source: `0002_tables.sql` lines `create table … public.feedback`.

| Column | Type | Category | PII | COPPA-relevant | ASTC bucket | Notes |
|---|---|---|---|---|---|---|
| `id` / `plan_id` | uuid | identifier | No | No | ID | — |
| `rating` | int (1–5) | telemetry (UD) | No | No | **UD** (Product Interaction) | — |
| `what_worked` | text | OUC (free-form) | Possibly | Possibly | **OUC** | Parent free-form text — **may inadvertently contain child PII**. UX must warn. **Decision D-6.** |
| `what_didnt` | text | OUC (free-form) | Possibly | Possibly | **OUC** | Same. |
| `created_at` / `updated_at` | timestamptz | telemetry | No | No | DG | — |

---

### 2.11 Universal `created_at` / `updated_at` columns
Every `public.*` table has these two `timestamptz` columns. They are **diagnostics-only**, never displayed to the user, never sent to a third party. ASTC bucket: **DG** (Other Diagnostic Data).

---

### 2.12 Summary roll-up — what App Store Connect needs

| Apple category | Collected? | Linked to user? | Used for tracking? | Source columns |
|---|---|---|---|---|
| **Contact Info — Name** | Yes | Yes | No | `auth.users.raw_user_meta_data.name` (parent, optional, first sign-in only); `player_profiles.display_name` (child) |
| **Contact Info — Email** | Yes | Yes | No | `auth.users.email` (parent; may be Apple Private Relay) |
| **Contact Info — Other (year of birth, age bracket)** | Yes | Yes | No | `player_profiles.birth_year`, `player_profiles.age_bracket`, `matches.age_bracket` |
| **Health & Fitness — Health** | Yes (free-form) | Yes | No | `player_profiles.dietary_notes`, `player_profiles.hydration_notes`, `player_profiles.injury_notes` |
| **Location — Precise** | Yes (venue only) | Yes | No | `tournaments.venue_lat`, `tournaments.venue_lng` |
| **Location — Coarse** | Yes (venue only) | Yes | No | `tournaments.venue_address` / `_city` / `_region` / `_postal` |
| **Identifiers — User ID** | Yes | Yes | No | `users.id` (= `auth.users.id`); Apple `sub` |
| **Identifiers — Device ID** | **No** | — | — | We do not collect IDFA/IDFV; no advertising SDKs. |
| **Usage Data — Product Interaction** | Yes (limited) | Yes | No | `feedback.rating`; first-party Supabase logs only |
| **Diagnostics — Crash / Performance / Other** | Yes (Apple-default + Supabase logs) | Yes (User ID) | No | All `created_at` / `updated_at`; iOS crash data via Apple's standard opt-in |
| **Other User Content** | Yes | Yes | No | `feedback.what_worked`, `feedback.what_didnt`, tournament/match free-form fields |
| **Purchases / Financial / Sensitive Info / Browsing History / Search History / Audio / Photos / Contacts / Other** | **No** | — | — | Not collected in MVP. |

---

## 3. COPPA Compliance Posture

> **Position:** PlayFuel does not knowingly collect personal information from a child under 13 *as a user* of the service. It collects information about a child **provided by their parent** as part of a parent-authenticated account. We rely on the COPPA "parent-provided / parent-authenticated" framework, **not** on verifiable parental consent (VPC).
>
> **OQ-06 (legacy): COPPA legal review remains a pre-launch blocker.** This document is the primer for that review; it is **not** a legal opinion.

### 3.1 The Hard Rule

| # | Rule |
|---|---|
| R1 | **No authentication for anyone under 13. Ever.** |
| R2 | The only auth method is **Sign in with Apple**. Apple's terms require account holders to be ≥ 13 (US) or the relevant local age. We rely on Apple's age-gating at account creation. |
| R3 | **Children are profiles, not users.** A `player_profiles` row is parent-owned data; the child has no login, no session, no `auth.uid()`. |
| R4 | We do not advertise to children. No ads, no marketing emails, no push notifications about products. (No notifications at all in MVP per `MVP_SCOPE.md`.) |
| R5 | We do not behaviorally profile children. The rules engine is deterministic per `RULES_CONSTANTS_V1.md`; the LLM is an explanation layer on already-derived structured output. |
| R6 | We do not share child data with third parties for *their* purposes. Third-party calls (Apple, Supabase, OpenAI, Places, Weather) are scoped to **service provision only** (§5). |
| R7 | All child data is **deletable on parent request** within the windows in §7. |

### 3.2 Why this avoids the VPC obligation (subject to legal review)

- The COPPA rule (16 CFR §312) applies to operators that knowingly collect personal information from a child under 13 **online**. PlayFuel collects personal information about a child **from the parent**, who is an adult (≥ 13) authenticated via Apple.
- The FTC's COPPA FAQ (Section H) recognises a "parent-provided" model in which a verified parent enters child information; the operator's obligations centre on (a) clear disclosure, (b) parental access, and (c) deletion on request — all of which we provide via §6 and §7.
- We do **not** collect from the child directly, do not enable child-to-child interaction, do not display ads to a child, and do not behaviourally profile a child.
- **This is a posture, not a determination.** A qualified attorney must confirm that our data model — particularly the optional `dietary_notes` / `hydration_notes` / `injury_notes` (which qualify as health data) — does not trip a more conservative interpretation that requires VPC.

### 3.3 Operational implications of the parent-owned model

| Surface | Operational rule |
|---|---|
| Sign-in | Apple ID only; no email/password; no social login. |
| Onboarding copy | Must state: "PlayFuel is for the parent or guardian of a junior tennis player. Players do not create accounts." (See §4.) |
| Profile creation UI | Field labels make clear who is being described (e.g. "Player's first name", not "Your name"). |
| Marketing | No marketing emails, no push notifications targeted at children. (No marketing emails to parents either in MVP.) |
| Analytics | No third-party analytics SDKs (`§6.1`). First-party Supabase logs only. |
| Sharing | No public player profiles; no leaderboards; no social graph. (Listed as out-of-scope in `MVP_SCOPE.md`.) |
| LLM prompts | Plan-explanation prompts include child-derived fields (age bracket, dietary notes). LLM provider is treated as a Service Provider under DPA — see §5.3. |

### 3.4 Carry-forward open questions for legal counsel

| ID | Question | Owner |
|---|---|---|
| **OQ-06** | Confirm parent-provided model is sufficient and VPC is not required. | Legal |
| **OQ-PRIV-1** | Are `dietary_notes` / `injury_notes` "health information" under HIPAA-adjacent state laws (e.g. Washington's "My Health My Data" Act)? Likely no (no covered entity), but confirm. | Legal |
| **OQ-PRIV-2** | Does the OpenAI/LLM provider's standard API DPA satisfy our obligations as an operator handling COPPA-relevant data, or do we need a separate child-data addendum? | Legal |
| **OQ-PRIV-3** | App Store Connect "Made for Kids" checkbox — **do not check** in MVP; primary user is the parent. Confirm. | Legal + PM |
| **OQ-11** | Heat-emergency wording (carried from `SAFETY_DISCLAIMERS.md §B`). | Legal |

---

## 4. Privacy Notice — Plain-English Snippets (drafts for in-app and web)

> These are **drafts for legal review**. Do not ship verbatim.

### 4.1 Onboarding screen — required disclosure block

```
Who PlayFuel is for
PlayFuel is for the parent or guardian of a junior tennis player.
Players do not create accounts. You sign in with your Apple Account; the
player is added as a profile inside your account.

What we store
• Your account: your Apple user ID and the email Apple shares with us
  (this may be Apple's Private Relay address).
• Your player(s): the first name you give us, the year of birth or age
  bracket, and any optional notes you write (dietary, hydration, injury).
• Your tournaments: name, dates, venue address, and venue location.
• Your plans: the schedule, food, weather, and recovery guidance we
  generate for each tournament.

What we never do
• We do not sell your data.
• We do not show you ads.
• We do not run third-party analytics or advertising trackers.
• We do not track your or your player's live location.
• We do not let other users see your player or your plans.

Deleting your data
You can delete a player profile, a tournament, or your entire account at
any time from Settings. Account deletion permanently removes everything
we have stored for you within 30 days. (Backups follow the same window.)
```

### 4.2 In-app footer (every plan view)

> Verbatim text already required by `SAFETY_DISCLAIMERS.md §A`. Privacy footer adds:

```
PlayFuel does not share your or your player's data with advertisers or
brokers. See Settings → Privacy for full details.
```

---

## 5. Third-Party Data Flows in MVP

> **All four are Service Providers / Sub-processors under our contract with the parent.** None receives data for *its own* purposes.

| # | Vendor | Data sent | Purpose | Region | Tracking? | Required DPA / agreement |
|---|---|---|---|---|---|---|
| 1 | **Apple** (Sign in with Apple) | Apple ID token (parent only); optional name on first sign-in | Authentication | Global | No | Apple Developer Program Agreement |
| 2 | **Supabase** (Postgres + Auth + Storage) | All `public.*` table data + `auth.users` | Hosting, auth, RLS-enforced storage | US (default region — confirm at project provisioning) | No | Supabase DPA |
| 3 | **OpenAI** (or eventual LLM provider — Phase 6) | `plan_json` (structured rules-engine output incl. age bracket and any non-empty dietary/hydration notes if surfaced); **no parent name, no parent email, no child name, no birth year, no precise lat/lng** — see §6.4 LLM data minimisation. | Generate `llm_summary` (parent-friendly explanation) | US | No (default API; **opt out of training** per provider's data-use settings) | Provider standard API DPA + child-data addendum if Legal requires (OQ-PRIV-2) |
| 4 | **WeatherKit** *or* **OpenWeather** (Phase 4) | `tournaments.venue_lat`, `tournaments.venue_lng`, request timestamp | Weather lookup for venue | US (provider-dependent) | No | Provider standard ToS |
| 5 | **Google Places** *or* **Yelp Fusion** (Phase 5) | `tournaments.venue_lat`, `tournaments.venue_lng`, search radius | Nearby food options | US (provider-dependent) | No | Provider standard ToS; **comply with no-menu-scraping rule** per `MVP_SCOPE.md` |

**No third-party analytics SDK, no crash reporter beyond Apple's built-in, no advertising SDK, no attribution SDK in MVP.** (Decision D-3.)

---

## 6. Data Minimisation Principles

### 6.1 Analytics

- **No third-party analytics SDK in MVP** (Mixpanel, Amplitude, Firebase Analytics, etc.).
- Telemetry is the union of:
  - `created_at` / `updated_at` columns on `public.*` rows (first-party).
  - Supabase platform logs (Postgres + Auth) — retained per Supabase defaults.
  - Apple's standard, opt-in iOS crash/usage diagnostics (governed by user's iOS settings, not by us).
- We do **not** send custom events to any analytics endpoint.

### 6.2 Location

- Lat/lng captured **only** when the parent enters a tournament venue.
- **No background location.** App requests no `NSLocationWhenInUseUsageDescription` for ongoing tracking; if iOS prompts at all, it is for one-off "use my current location to fill venue address" — and even that is **deferred**: MVP requires manual venue entry (`MVP_SCOPE.md` Phase 2 acceptance).
- We do not store the parent's device location, the player's device location, route history, or any geofence.

### 6.3 Sensitive fields

- `dietary_notes`, `hydration_notes`, `injury_notes` are **all optional** by DDL.
- UX must:
  - Mark fields as "Optional" inline.
  - Never block save on a missing note field.
  - Never auto-prompt re-entry.
- Field values are stored as `text` (free-form). UX should advise parents not to enter clinical detail. (We do **not** validate/parse health text.)

### 6.4 LLM prompt logging policy (Phase 6)

> Authoritative until Phase 6 ships its own privacy addendum.

| Item | Policy |
|---|---|
| **What we send to the LLM provider** | The `plan_json` (rules-engine output) **with COPPA-relevant fields stripped or coarsened**: send `age_bracket` (e.g. "12U") instead of `birth_year`; **never** send `display_name`; send dietary/hydration/injury notes **only if the parent has opted in per-plan** (a future UX setting, default off). Send no `auth.users.email`, no `users.id`, no `tournaments.venue_lat`/`venue_lng` (use city/region instead). |
| **What we store of the prompt** | We persist the LLM's response in `plans.llm_summary`. We do **not** persist the full prompt verbatim in MVP — the prompt can be reconstructed deterministically from `plan_json` + the system prompt template (versioned in code per `SAFETY_DISCLAIMERS.md §E`). |
| **What we store of the response** | `plans.llm_summary` (text). No multi-turn history; each plan is a single request. |
| **Provider data-use settings** | Use the provider's **opt-out-of-training** mode (e.g. OpenAI API default since 2023). Confirm at deployment time. |
| **Logging at our edge** | The FastAPI server may log request IDs and latency for operations; it must **not** log prompt or response bodies to plaintext logs. |

### 6.5 What we deliberately do NOT collect

| Field | Why omitted |
|---|---|
| Date of birth (full) | Year-only suffices for age-bracket logic. PRD §11. |
| Live device location | Not needed; venue entry is parent-driven. §6.2. |
| Player photo / avatar | Not in MVP. Listed as out-of-scope. |
| Parent phone number | Not used. Sign in with Apple does not provide it. |
| Payment data | No paywall in MVP (`MVP_SCOPE.md`). |
| Health metrics from HealthKit | Wearable integration explicitly out of MVP. |
| Calendar | Calendar integration explicitly out of MVP. |
| Contacts | Never requested. |

---

## 7. Data Deletion Flow

### 7.1 Apple App Store Review Guideline 5.1.1(v) — account deletion

Apple requires apps that allow account creation to also allow **in-app account deletion**, not just deactivation. Required UX:

1. **Settings → Account → Delete Account.**
2. Confirmation screen explains scope (everything goes; not recoverable).
3. Single confirmation tap → request fired.
4. User is signed out and returned to the sign-in screen.
5. Server-side deletion cascades complete within the window in §7.4.

### 7.2 Cascade behaviour (verified from migrations)

> Source: `db/supabase/migrations/0002_tables.sql` — every FK uses `ON DELETE CASCADE`. Source: `0004_auth_trigger.sql` — `public.users.id` references `auth.users(id) ON DELETE CASCADE`.

```
auth.users  (DELETE)
  └── public.users                    [CASCADE]
        ├── public.player_profiles    [CASCADE]
        └── public.tournaments        [CASCADE]
              ├── public.matches      [CASCADE]
              │     └── public.match_scenarios   [CASCADE]
              ├── public.weather_snapshots       [CASCADE]
              ├── public.food_options            [CASCADE]
              └── public.plans                   [CASCADE]
                    └── public.feedback          [CASCADE]
```

**Single `DELETE FROM auth.users WHERE id = ?` removes 100% of the user's PlayFuel data in one transaction.** No orphaned rows are possible given the FK graph. This is the deletion contract.

### 7.3 Granular deletion

| Action | Effect |
|---|---|
| Delete a single `player_profile` | Removes that row only. **Does not** cascade to `tournaments` (tournaments are owned by `users.id`, not by `player_profiles.id`). The parent must delete tournaments separately. |
| Delete a single `tournament` | Cascades to `matches`, `match_scenarios`, `weather_snapshots`, `food_options`, `plans`, `feedback`. |
| Delete a single `plan` | Cascades to `feedback` (rare — feedback is Phase 7). |
| Delete account | §7.2 — full wipe. |

### 7.4 Retention windows

| Surface | Window | Source |
|---|---|---|
| **Live database rows** | Indefinite, until user deletes (per-row or full-account). | MVP stance — no scheduled-purge job in MVP. |
| **Account-deletion fulfilment** | ≤ 30 days from request to full purge of live data and backups. | Decision D-8 (industry-standard window; revisit with Legal). |
| **Supabase point-in-time backups** | Per Supabase's project-tier default (currently 7 days for paid tiers). | Supabase platform; confirm at provisioning. |
| **FastAPI server logs (request metadata only)** | ≤ 30 days, then rotated. | Decision D-9. |
| **LLM provider-side logs** | Per provider (e.g. OpenAI 30-day default with abuse-monitoring opt-out). | Provider DPA. |

**No silent retention beyond 30 days post-deletion.** If we add anything (e.g. analytics, fraud signals) in a future phase, it must be added to this table first.

### 7.5 Deletion request from a non-user (parent of a child whose data is in the system)

Because the parent is the only authenticated user **and** the only person whose data is in the system, the standard flow handles this. No separate "child rights" intake is required in MVP — but the privacy notice (§4.1) and Settings UI must make this explicit.

---

## 8. App Store Privacy Disclosure Draft

> Pre-answered for App Store Connect → "App Privacy" questionnaire.
> Format mirrors Apple's questionnaire flow (April 2026 schema).

### 8.1 "Do you or your third-party partners collect data from this app?"

**Yes.**

### 8.2 Data Types collected (check the boxes Apple shows)

| ✅ | Apple Category | Specific Type | Linked to user | Used for tracking | Purpose |
|---|---|---|---|---|---|
| ✅ | Contact Info | **Name** | Yes | No | App Functionality |
| ✅ | Contact Info | **Email Address** | Yes | No | App Functionality |
| ✅ | Contact Info | **Other User Contact Info** (year of birth, age bracket) | Yes | No | App Functionality |
| ✅ | Health & Fitness | **Health** (parent-authored notes) | Yes | No | App Functionality |
| ✅ | Location | **Precise Location** (venue lat/lng) | Yes | No | App Functionality |
| ✅ | Location | **Coarse Location** (venue address fields) | Yes | No | App Functionality |
| ✅ | Identifiers | **User ID** | Yes | No | App Functionality |
| ✅ | Usage Data | **Product Interaction** (Phase-7 feedback ratings) | Yes | No | App Functionality, Analytics (first-party only) |
| ✅ | Diagnostics | **Crash Data** (Apple-default opt-in) | Yes | No | App Functionality |
| ✅ | Diagnostics | **Performance Data** (Apple-default opt-in) | Yes | No | App Functionality |
| ✅ | Diagnostics | **Other Diagnostic Data** (created_at/updated_at audit trail) | Yes | No | App Functionality |
| ✅ | User Content | **Other User Content** (free-form notes, feedback text, tournament/match labels) | Yes | No | App Functionality |
| ❌ | Identifiers | Device ID | — | — | Not collected. |
| ❌ | Financial Info / Purchases | — | — | — | Not collected (no payment in MVP). |
| ❌ | Browsing History / Search History / Audio / Photos / Contacts / Sensitive Info | — | — | — | Not collected. |

### 8.3 Tracking question

**"Do you or your third-party partners use data from this app for tracking?"**
**No.** No third-party advertising/attribution SDKs. No data sharing for cross-app/website behavioural advertising. (This means **no App Tracking Transparency prompt** is required.)

### 8.4 Privacy policy URL

**Required by App Store. Status: TBD.** A public-facing privacy policy URL must be hosted before submission. Pre-launch task; tracked as **OQ-PRIV-4**.

### 8.5 "Made for Kids" category

**Do NOT enroll in "Made for Kids."** The primary user is a parent (≥ 18 by app stance, ≥ 13 by Apple terms). Enrolling would trigger Apple's stricter Kids Category review and additional consent flows that conflict with the parent-owned model. (Confirm with Legal — OQ-PRIV-3.)

---

## 9. Out of Scope for This Document (with rationale)

| Area | Why deferred |
|---|---|
| **GDPR DSAR tooling** | No EU launch in MVP. When EU launch is planned, add: (a) DSAR intake endpoint, (b) data-export endpoint returning JSON of all user-owned rows, (c) Article 30 record of processing activities. |
| **CCPA "Do Not Sell" / "Do Not Share"** | We don't sell or share for cross-context advertising. The "Notice at Collection" is satisfied by §4.1 once that text is in production. Re-evaluate at California-specific launch. |
| **Advertising IDs (IDFA / IDFV)** | Not collected. No ATT prompt. Re-evaluate if monetisation enters scope. |
| **Third-party data sharing for third-party purposes** | None in MVP. All vendors in §5 are Service Providers with contractual restriction to service provision. |
| **Children's online safety (e.g. NY SAFE for Kids Act, KOSA)** | We do not target users under 13 for accounts; child data is parent-managed. Re-confirm with Legal as state laws evolve. |
| **Biometric data, voice, audio, photo** | Not collected. Sign in with Apple uses Face/Touch ID locally; no biometric template ever leaves the device. |
| **Wearables / HealthKit** | Explicitly out of MVP per `MVP_SCOPE.md`. |
| **Data Subject Access Request (DSAR) automation** | Manual fulfilment via Settings → Delete Account suffices in MVP. Automated export is a Phase 7+ concern. |

---

## 10. Decisions Made Beyond Source

> Every place this doc filled a gap not covered in the schema, PRD, or scope docs. Tag legend:
> **Worth a look** = needs lightweight stakeholder confirm.
> **Invented** = a defensible default I picked; a stakeholder may want to override.
> **Derived** = mechanically derived from `db/supabase/` migrations or a referenced source doc.

| ID | Decision | Tag | Rationale | Where to revisit |
|---|---|---|---|---|
| **D-1** | We never un-relay Apple Private Relay emails. We treat the relay address as the parent's contact email even if a real one is later available. | **Invented** | Maximises parent privacy; no business need for the real address in MVP. | Re-evaluate if marketing email ever ships (post-MVP). |
| **D-2** | We do not copy `auth.users.raw_user_meta_data.name` into `public.users` or anywhere else in `public.*`. We use Apple's name only for the optional first-sign-in greeting and discard it. | **Invented** | Strict data minimisation; the parent name is never required by any product surface. | Re-evaluate if Apple changes Sign-in scopes or if a settings-screen "your name" field is added. |
| **D-3** | No third-party analytics, crash, or advertising SDKs in MVP. First-party Supabase logs only. | **Invented** | Lowers privacy surface, kills the ATT prompt, simplifies App Store review. | Phase 7 / beta — Engineering may want crash reporting; if so, choose an Apple-default or non-tracking SDK. |
| **D-4** | UX should label `display_name` as "Player's first name" and discourage last name. We do not enforce this server-side (the column is `text`). | **Worth a look** | Reduces incidental PII without breaking schema. | UX research validation; consider a soft client-side warning. |
| **D-5** | Lat/lng columns are declared as Apple **Precise Location** in the App Store questionnaire even though the values are always public-venue coordinates. | **Invented** (conservative) | Apple's category is defined by precision (>100 m), not by what the value represents. Conservative declaration avoids review-time surprises. | If App Store reviewer pushes back or wants finer categorisation. |
| **D-6** | `feedback.what_worked` and `feedback.what_didnt` are flagged as potentially containing PII; UX must show a "Don't include personal details about your child" hint above the field. | **Worth a look** | Parent free-form text is the highest-risk PII surface. | UX implementation (Phase 7). |
| **D-7** | No GDPR / CCPA / advertising-ID / third-party-sharing scope in MVP. | **Derived** (from `MVP_SCOPE.md` out-of-scope list and stack choices). | We're US-only at launch with no ads; standard MVP scoping. | Pre-EU-launch and pre-California-marketing-push. |
| **D-8** | 30-day fulfilment window for full account-deletion purge (live + backups). | **Invented** | Industry-standard window; aligns with most consumer-app DPAs and within Supabase backup retention. | Legal confirmation; confirm Supabase backup-purge mechanics. |
| **D-9** | FastAPI server logs retain request metadata only (no bodies) for ≤ 30 days. | **Invented** | Standard observability default; aligns with deletion window. | Engineering1 must enforce in `main.py` logging config (Task #5 outstanding work). |
| **D-10** | LLM prompts strip child name and birth year; pass `age_bracket` and city/region only; opt-in gate for sending dietary/hydration/injury notes (default off). | **Invented** | Most aggressive data minimisation possible without breaking the explanation use case. | Phase 6 (Task #9) — confirm prompt template before launch. |
| **D-11** | We do not enroll in App Store "Made for Kids." Primary user is the parent. | **Worth a look** | Parent-owned model is incompatible with Made-for-Kids stricter review. | Legal confirm (OQ-PRIV-3). |
| **D-12** | We declare **Health & Fitness — Health** in the App Store questionnaire because `dietary_notes` / `hydration_notes` / `injury_notes` are health-adjacent free-form fields, even though we do not parse them as health data. | **Invented** (conservative) | Apple defines the category by collected content; conservative declaration. | If the field labels change to be obviously non-health (unlikely). |
| **D-13** | Schedule-confidence and warnings (`plans.warnings`) are derived/diagnostic — not user-disclosable PII. | **Derived** | Computed from `match_scenarios.gap_status` per `0002_tables.sql` comment block; no new collected data. | n/a |
| **D-14** | The `feedback` table is in the schema but the UI ships in Phase 7. Until the UI ships, no rows are written; the privacy disclosure still discloses it because Apple wants future intent disclosed. | **Worth a look** | Some teams disclose only what's actively collected; we're conservative. | Pre-launch — confirm with Apple's reviewer guidance. |
| **D-15** | **No notifications of any kind in MVP.** No push, no local. (Already explicit in `MVP_SCOPE.md`; restated here because it has a privacy implication: no notification permission prompt, no notification token stored.) | **Derived** | From `MVP_SCOPE.md` out-of-scope list. | Phase 7+ when notifications enter scope. |
| **D-16** | App Store privacy policy URL is required pre-submission. **Not authored in this doc** — needs a public hosting decision (marketing site? GitHub Pages? Notion?). Tracked as **OQ-PRIV-4**. | **Derived** | App Store requirement, not a discretionary decision. | Pre-submission. |

---

## 11. New Open Questions Raised by This Doc

| ID | Question | Owner | Pre-launch blocker? |
|---|---|---|---|
| **OQ-PRIV-1** | Do `dietary_notes` / `injury_notes` constitute "consumer health data" under WA's My Health My Data Act or similar state laws? | Legal | Yes (if any covered-state launch) |
| **OQ-PRIV-2** | Does the chosen LLM provider's standard API DPA cover COPPA-relevant data, or do we need a child-data addendum? | Legal | Yes |
| **OQ-PRIV-3** | Confirm we should NOT enroll in App Store "Made for Kids." | Legal + PM | Yes |
| **OQ-PRIV-4** | Where will the public privacy policy URL be hosted before App Store submission? | PM + Eng | Yes |
| **OQ-PRIV-5** | Should the iOS app gate `dietary_notes` / `hydration_notes` / `injury_notes` behind a per-field consent toggle (vs the current "all three optional" approach)? | UX + Legal | No (UX nicety; current optional-by-default is defensible) |
| **OQ-PRIV-6** | Confirm Supabase project region at provisioning (US default). Document implications if EU users sign in cross-border. | Eng | Pre-EU launch |
| **OQ-PRIV-7** | LLM provider-side log retention — confirm the chosen provider's settings match D-10's intent before Phase 6 ships. | Engineering1 | Phase 6 blocker |

---

## 12. Document Conformance Checklist

- [x] Data inventory walked from actual `db/supabase/migrations/0002_tables.sql` (9 tables, 67 columns) — **no invented columns**.
- [x] Cascade behaviour verified against `0002_tables.sql` `ON DELETE CASCADE` declarations and `0004_auth_trigger.sql`.
- [x] App Store privacy questionnaire pre-answered (§8) for direct copy into App Store Connect.
- [x] COPPA posture documented; OQ-06 carried forward.
- [x] Data-deletion flow references real cascade graph; Apple Guideline 5.1.1(v) addressed (§7.1).
- [x] Out-of-scope items deferred with rationale (§9).
- [x] Decisions-beyond-source table tagged Worth-a-look / Invented / Derived (§10, 16 entries).
- [x] New OQs surfaced for legal review (§11, 7 entries).

---

---

## 2.13 `public.players` — parent's opponent roster (PLAYER_SCOUTING_V1.md §A)
> Added: 2026-04-28 · Source: PLAYER_SCOUTING_V1.md §B verified against migration 0010_players_and_notes.sql spec.

| Column | Type | Category | PII | COPPA-relevant | ASTC bucket | Notes |
|---|---|---|---|---|---|---|
| `id` | uuid | identifier | No | No | ID | Internal PK. |
| `user_id` | uuid FK→users.id | identifier | Yes (parent) | No | ID | RLS join key. |
| `display_name` | text NOT NULL | child-adjacent | **Yes (name of child opponent)** | **Yes** | **CI** (Name) | Name of another parent's child. Data minimisation: first name strongly preferred. See §13.2. |
| `club` | text (optional) | account | Low | Indirect | OUC | e.g. "Dallas Tennis Academy". |
| `city` | text (optional) | location | Low | Indirect | **LOC-C** | City/region context only. |
| `notes_summary` | text (optional) | OUC | Possibly | Possibly | **OUC** | Parent-curated 1-line headline. Free-form — may mention playing style. |
| `created_at` / `updated_at` | timestamptz | telemetry | No | No | DG | — |

---

## 2.14 `public.player_notes` — scouting observations log (PLAYER_SCOUTING_V1.md §A)
> Added: 2026-04-28 · Source: PLAYER_SCOUTING_V1.md §B verified against migration 0010_players_and_notes.sql spec.

| Column | Type | Category | PII | COPPA-relevant | ASTC bucket | Notes |
|---|---|---|---|---|---|---|
| `id` | uuid | identifier | No | No | ID | — |
| `player_id` | uuid FK→players.id | identifier | No | No | ID | — |
| `user_id` | uuid FK→users.id | identifier | Yes (parent) | No | ID | RLS join key. |
| `source` | player_note_source enum | account | No | No | OUC | "secondhand" / "observed" / "post_match". |
| `body` | text NOT NULL ≤ 2000 chars | OUC (free-form) | **Possibly** | **Yes** | **OUC** | Parent-authored observation. May contain names or descriptions of a child opponent. UX guardrail text required (§13.3). |
| `match_id` | uuid FK→matches.id (nullable, SET NULL) | identifier | No | No | ID | Links note to a specific match when known. |
| `created_at` | timestamptz | telemetry | No | No | DG | No `updated_at` — notes immutable after creation (within 24h edit window). |

**`matches.opponent_player_id` (added in migration 0010):**

| Column | Type | Category | PII | COPPA-relevant | ASTC bucket | Notes |
|---|---|---|---|---|---|---|
| `opponent_player_id` | uuid FK→players.id (nullable, SET NULL) | identifier | No | No | ID | Links a match to a scouted opponent. Additive; no change to existing ASTC declarations for `matches`. |

---

## 13. Notes About Other Minors (Scouting Feature)

> Added: 2026-04-28. Covers `public.players` and `public.player_notes` tables (migration 0010).

### 13.1 Data nature

The Player Scouting feature (PLAYER_SCOUTING_V1.md) lets a parent store observations about their child's **opponents** — other parents' children. This is a new PII surface that extends the existing parent-provided model.

Critical distinction:
- **Not opponent-authored.** The opponent never creates an account, never consents, and never knows a note exists.
- **Parent-authored opinion data.** Analogous to a coach's clipboard of pre-match scouting notes: entirely the observer's own written observations.
- **No contact data by schema design.** `players` has no email, phone, home address, photo, or physical-description columns. Character-capped free-form notes (2,000 chars).

### 13.2 Data minimisation

| Constraint | Mechanism |
|---|---|
| No contact info columns | Schema has none: no email, no phone, no address, no photo, no physical description |
| Name only + court-observable fields | `display_name` (name), `club` (org), `city` (regional), `body` (free-form observation) |
| Body capped at 2,000 chars | DB `CHECK (char_length(body) <= 2000)` |
| UX guardrail text | Verbatim required on AddPlayerNoteSheet: *"Notes are private to your account. Don't include personal contact info, photos, or anything not directly observable on court."* |

### 13.3 LLM paraphrase-only rule

When opponent notes feed into the plan explanation:
1. Sanitization pipeline strips URLs, emails, phone numbers; truncates to 200 chars before the LLM sees the text.
2. §C prohibited-phrase check redacts any note containing a prohibited phrase (replaced with `[note redacted]`) before it reaches the LLM input.
3. `TemplateProvider` conservative acknowledgment only counts notes — never quotes body text.
4. Real-LLM prompt rule (post-MVP, `OQ-SCOUT-LLM-1`): paraphrase only, never quote verbatim, never reveal source.
5. `validate_explanation` from `services/llm_safety.py` scans all LLM output for §C phrases unconditionally — no new code needed.

### 13.4 Cascade delete

```
auth.users (DELETE)
  └── public.users                  [CASCADE]
        └── public.players          [CASCADE]   ← new
              └── public.player_notes  [CASCADE]   ← new
```

If a parent deletes their account, all their scouted players and notes are deleted in the same transaction. If a parent deletes a single player, all that player's notes cascade. `player_notes.match_id` is SET NULL on match delete (note survives; FK link is cleared).

### 13.5 Legal posture

**Ship with current guardrails.** Parent-authored opinion data about opponents is legally analogous to a coach's clipboard — the parent's own court observations. This is not a new category of collected PII beyond what already exists (parent can already type any text into `injury_notes` or `player_profiles.display_name`). The same parent-provided model from §3 applies. Legal confirmation flagged as `OQ-SCOUT-PRIV-1` (non-blocking for MVP).

**App Store questionnaire impact:** `players.display_name` for opponent children adds another instance of **CI (Name)** — already declared for `player_profiles.display_name`. No new ASTC category is introduced. `player_notes.body` adds another instance of **OUC (Other User Content)** — already declared. No questionnaire change required for the existing categories.

### 13.6 Post-Match Evaluations: `opponent_observations` (POST_MATCH_EVAL_V1.md §H)

The post-match evaluation feature (migration 0011) adds a `match_evaluations.opponent_observations` field (text, ≤500 chars). This field is **in scope of the §13 posture** — same privacy treatment as `player_notes.body`:
- Parent-authored content about a minor (opponent child).
- No PII schema columns: `match_evaluations` has no email, phone, address, or photo columns.
- Auto-synced to `player_notes` (source='post_match') via `services/post_match_sync.py` — the note itself inherits all §13 constraints.
- Sanitization applies at LLM-input time (same pipeline as `player_notes`).
- ASTC bucket: **OUC** — already declared. **No new questionnaire category introduced.**
- Form guardrail text required near the field: *"These notes will be added to your scouting log for this opponent."* (hard-coded; see POST_MATCH_EVAL_V1.md §H.2).

---

## 14. New Open Questions from Player Scouting (2026-04-28)

| ID | Question | Owner | Pre-launch blocker? |
|---|---|---|---|
| **OQ-SCOUT-PRIV-1** | Parent-authored opinion data about other minors — is this a regulated category under COPPA or state laws (WA My Health My Data, NY SHIELD Act, etc.)? Posture: it's the parent's own court observation, not PII about the opponent as a user. | Legal | Non-blocking for MVP; must confirm before App Store submission |
| **OQ-SCOUT-PRIV-2** | Retention policy for opponent notes. Current stance: no scheduled purge (running log is the feature). Should notes auto-expire after X years or X days post-tournament? | Legal + PM | Non-blocking for MVP; flag in privacy policy draft |

---

*End of PRIVACY_V1.md*
