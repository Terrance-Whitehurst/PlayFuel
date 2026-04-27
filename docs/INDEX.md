# PlayFuel — Documentation Index

> One page. Every document in the repo. One-line description each.

---

## Front-Door Docs

| Document | Path | Purpose |
|---|---|---|
| README | `/README.md` | Repo overview, stack, quickstart, monorepo layout, project status |
| Architecture | `/ARCHITECTURE.md` | System design, components, data flow, auth model, rules engine invariants |
| Contributing | `/CONTRIBUTING.md` | Dev setup, test commands, code conventions, OQ system, PR guide |

---

## Per-Component READMEs

| Component | Path | Purpose |
|---|---|---|
| FastAPI backend | `apps/api/README.md` | Endpoint inventory, key design decisions, deviations from spec |
| iOS app | `apps/ios/PlayFuel/README.md` | Xcode setup, Phase 3 swap path (FakeData → live API), screen tour, safety compliance checklist |
| Database | `db/supabase/README.md` | Migration order, RLS pattern, Sign in with Apple setup, seed UUIDs, env vars |

---

## Build Plan

| Document | Path | Purpose |
|---|---|---|
| Build plan | `specs/PLAN.md` | Phased roadmap (Phases 0–8+), task IDs, parallelization plan, open questions by phase |

---

## Canonical Specs

These are the authoritative product, rules, and legal documents for PlayFuel.
They currently live in `.pi/multi-team/expertise/` — see the [note below](#a-note-on-spec-location).

| Document | Path | Summary |
|---|---|---|
| PRD | `.pi/multi-team/expertise/PRD.md` | Product requirements — one-sentence pitch, target users, demo scenario, MVP goal, build phases, privacy posture |
| User Stories | `.pi/multi-team/expertise/USER_STORIES.md` | US-01 through US-09 with Given/When/Then acceptance criteria, mapped to schema columns and API endpoints |
| MVP Scope | `.pi/multi-team/expertise/MVP_SCOPE.md` | Explicit in-scope checklist (Phases 0–6), out-of-scope list (11 categories), explicit deferrals table |
| Rules Constants v1 | `.pi/multi-team/expertise/RULES_CONSTANTS_V1.md` | Frozen v1.0.0 rules engine spec — scenario durations, gap-bucket boundaries (food + pickup), hydration triggers, weather flag thresholds, hard-coded string registry, negative-gap contract (§G), OQ registry (§I), change-control rules (§J) |
| Scenario Acceptance | `.pi/multi-team/expertise/SCENARIO_ACCEPTANCE.md` | QA acceptance criteria for all 5 eval scenarios (cool weather · hot+humid · long gap · back-to-back · rain delay) with must-include / must-not-include checklists |
| Safety Disclaimers | `.pi/multi-team/expertise/SAFETY_DISCLAIMERS.md` | Verbatim disclaimer text (§A) · heat-emergency guidance (§B, draft pending OQ-11 legal review) · prohibited phrases (§C) · safer-language substitution table (§D) · LLM system prompt requirements (§E) · privacy constraints for minors (§F) |
| Privacy v1 | `.pi/multi-team/expertise/PRIVACY_V1.md` | COPPA posture and parent-owned-account model (§3) · full data inventory walked column-by-column from schema (§2, 9 tables × 67 columns) · App Store privacy questionnaire pre-answered (§8) · data deletion cascade (§7) · third-party data flows (§5) · decisions-made-beyond-source table (§10, 16 entries) · OQs for legal counsel (§11) |

---

## A Note on Spec Location

The canonical product and rules specs live in `.pi/multi-team/expertise/` — an unusual path.
This is because PlayFuel was built through a multi-agent AI collaboration framework that uses
that directory as its shared knowledge base between agents.

The specs are **first-class product documents**, not internal tooling. If you're looking for
the "why" behind a rules constant, a boundary condition, a privacy decision, or a UX
acceptance criterion, `.pi/multi-team/expertise/` is where to look.

A future cleanup pass will likely relocate these specs to `/specs/` or `/docs/specs/` for
discoverability. Until then, the canonical specs remain in `expertise/`. This index is the
bridge.
