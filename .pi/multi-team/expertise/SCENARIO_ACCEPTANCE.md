# PlayFuel — Plan Generation Engine: Scenario Acceptance Criteria

> **Status:** Phase 0 draft · Authority: Product Manager · Last updated: 2026-04-26
> These are the QA acceptance criteria for the plan generation engine.
> Rules source: §14 (match durations), §15 (parent pickup windows), §16 (food strategy), §17 (weather flags), §19 (pseudocode).
> Use these to validate Phase 3 backend output and Phase 6 LLM explanation output.

---

## Duration Defaults (from §14)

All scenarios use these defaults unless overridden:

| Scenario | Duration |
|---|---|
| Short | 75 minutes |
| Normal | 120 minutes |
| Long | 180 minutes |

---

## Gap → Food Strategy Rules (from §19 pseudocode)

| Gap (minutes) | Food Strategy |
|---|---|
| < 45 | "Use immediate bag food only: banana, pretzels, applesauce pouch, electrolyte drink, simple sandwich if tolerated." |
| 45–89 | "Use pre-bought portable food immediately after match. Avoid waiting in line." |
| 90–149 | "Use quick pickup food: turkey sandwich, rice bowl, grocery prepared meal." |
| ≥ 150 | "There is enough time for a light meal, but avoid heavy/greasy foods." |

---

## Parent Pickup Window Rules (from §19 pseudocode)

| Gap (minutes) | Parent Strategy |
|---|---|
| < 60 | "Parent should have portable food ready before match ends." |
| 60–119 | "If match is trending long, parent should pick up food during the final portion of the match if another trusted adult is present." |
| ≥ 120 | "Parent can likely wait until the match ends before getting food." |

---

## Weather Flag Thresholds (from §17)

| Flag | Condition |
|---|---|
| hot | temp_f ≥ 85 |
| very_hot | temp_f ≥ 90 |
| humid | humidity ≥ 65% |
| cold | temp_f ≤ 50 |
| windy | wind_mph ≥ 15 |
| rain_risk | precipitation_probability ≥ 40% |

---

## Scenario 1: Cool Weather · 9 AM / 1 PM · Many Restaurants Nearby

```
Match 1:       9:00 AM
Est. Match 2:  1:00 PM
Weather:       ~65°F, ~40% humidity, ~5 mph wind, ~10% precip
Food:          3–5 nearby restaurants (various categories)
```

### Must Include

- [ ] Three scenarios generated: Short (ends ~10:15 AM), Normal (ends ~11:00 AM), Long (ends ~12:00 PM)
- [ ] **Short scenario**: gap = 165 min → food strategy = "enough time for a light meal, avoid heavy/greasy" (≥ 150 min bucket) · parent pickup = "can wait until match ends" (≥ 120 min)
- [ ] **Normal scenario**: gap = 120 min → food strategy = "enough time for a light meal, avoid heavy/greasy" (≥ 150 min? — see Open Questions §1 below) · parent pickup = "can wait until match ends" (= 120 min boundary)
- [ ] **Long scenario**: gap = 60 min → food strategy = "pre-bought portable food immediately" (45–89 min bucket) · parent pickup = "if match is trending long, pick up food during final portion" (60–119 min boundary)
- [ ] At least 3 nearby food options displayed with: name, category, recommended order template, estimated drive time
- [ ] No weather flags set for "hot," "humid," "cold," or "rain_risk" (conditions don't meet thresholds)
- [ ] Pre-match timeline: wake-up event, breakfast window, pack bag reminder, arrive at venue, dynamic warm-up
- [ ] General hydration reminders at changeovers (present regardless of weather)

### Must Not Include

- ❌ "hot" or "humid" weather flag (temp < 85°F, humidity < 65%)
- ❌ Heat illness emergency text in the plan body (reserve for actual heat conditions)
- ❌ Instruction to skip restaurant pickup (gap is sufficient in all three scenarios)
- ❌ Medical claims about any food or hydration item
- ❌ Invented restaurant names not present in the places API response

---

## Scenario 2: Hot & Humid · 9 AM / 12 PM · Few Food Options

```
Match 1:       9:00 AM
Est. Match 2:  12:00 PM
Weather:       88°F, 72% humidity, 8 mph wind
Food:          1–2 nearby options (or none if testing fallback)
```

### Must Include

- [ ] Weather flags set: "hot" (88 ≥ 85) and "humid" (72 ≥ 65)
- [ ] Hot weather adjustments present: increased hydration emphasis, electrolyte note, shade/rest, avoid heavy meals, cool-down reminder (see §17 hot + humid adjustments)
- [ ] Three scenarios: Short (ends ~10:15 AM, gap = 105 min), Normal (ends ~11:00 AM, gap = 60 min), Long (ends ~12:00 PM, gap = 0 min or overrun warning)
- [ ] **Short scenario**: gap = 105 min → food = "quick pickup food" (90–149 min bucket) · parent pickup = "if match trending long, pick up during final portion" (60–119 min)
- [ ] **Normal scenario**: gap = 60 min → food = "pre-bought portable food immediately" (45–89 min bucket) · parent pickup = "if match trending long, pick up during final portion" (60–119 min)
- [ ] **Long scenario**: gap = 0 min (match ends at next match start) → food = "immediate bag food only" (< 45 min bucket) · parent pickup = "have portable food ready before match ends" (< 60 min)
- [ ] If only 1–2 food options returned: display available options plus bag-food fallback guidance
- [ ] If zero food options: display bag-food fallback only (banana, pretzels, applesauce pouch, electrolyte drink — see §16)
- [ ] Heat illness emergency guidance accessible from plan (hard-coded — see SAFETY_DISCLAIMERS §B)

### Must Not Include

- ❌ Recommendation for a heavy sit-down meal in Normal or Long scenarios (gap < 90 min)
- ❌ "very_hot" flag (88°F < 90°F threshold)
- ❌ Invented restaurant name when no places API data is available
- ❌ Medical claims about heat or hydration
- ❌ Guaranteed electrolyte outcomes ("electrolytes will prevent cramps")

---

## Scenario 3: Long Gap · 10 AM / 4 PM

```
Match 1:       10:00 AM
Est. Match 2:  4:00 PM
Weather:       (neutral — e.g., 72°F, 50% humidity)
Food:          Standard mix of nearby options
```

### Must Include

- [ ] Three scenarios: Short (ends ~11:15 AM, gap = 285 min), Normal (ends ~12:00 PM, gap = 240 min), Long (ends ~1:00 PM, gap = 180 min)
- [ ] All three scenarios → gap ≥ 150 min → food strategy = "enough time for a light meal, avoid heavy/greasy foods" (≥ 150 min bucket)
- [ ] All three scenarios → gap ≥ 120 min → parent pickup = "can wait until match ends"
- [ ] Re-warm-up timing specified for all three scenarios (large gap = sufficient rest before re-warm-up)
- [ ] Recovery strategy accounts for large gap: rest window identified, re-warm-up window placed ~30–45 min before estimated Match 2 start
- [ ] Pre-match timeline starts from 10:00 AM match (wake-up, breakfast, warm-up adjusted accordingly)

### Must Not Include

- ❌ Urgent food pickup instruction (all gaps are ≥ 150 min)
- ❌ "Have food ready before match ends" (gap > 120 min in all scenarios)
- ❌ Weather flag adjustments if weather is neutral (no thresholds crossed)
- ❌ Medical claims

---

## Scenario 4: Back-to-Back · 9 AM / 11 AM

```
Match 1:       9:00 AM
Est. Match 2:  11:00 AM
Weather:       (neutral)
Food:          Standard mix
```

### Must Include

- [ ] Three scenarios: Short (ends ~10:15 AM, gap = 45 min), Normal (ends ~11:00 AM, gap = 0 min / overrun warning), Long (ends ~12:00 PM, gap = -60 min / overrun warning)
- [ ] **Short scenario**: gap = 45 min → food = "pre-bought portable food immediately" (45–89 min bucket — boundary case, see Open Questions §2) · parent pickup = "have portable food ready before match ends" (< 60 min)
- [ ] **Normal scenario**: gap ≤ 0 → plan must surface an overrun warning: "Match 1 may not finish before Match 2's estimated start time. Alert tournament desk."
- [ ] **Long scenario**: gap is negative → overrun warning required. Food strategy = "immediate bag food only" (< 45 min; likely no time between matches)
- [ ] Back-to-back re-warm-up guidance: Short scenario warm-up must be described as "short and light" given the 45-minute gap
- [ ] Bag-food emphasis for all scenarios: portable, pre-bought, no restaurant pickup in Normal/Long
- [ ] Emergency food fallback included (banana, pretzels, electrolyte drink)

### Must Not Include

- ❌ Sit-down meal recommendation in any scenario
- ❌ Parent pickup advice suggesting restaurant run during a 45-minute gap
- ❌ Normal or Long scenario presented without an overrun warning
- ❌ Re-warm-up window longer than the available gap

---

## Scenario 5: Rain Delay Risk · Outdoor Courts · Uncertain Schedule

```
Match 1:       9:00 AM (scheduled)
Est. Match 2:  ~1:00 PM (uncertain)
Weather:       70°F, precipitation_probability = 55%, outdoor courts
Food:          Standard mix
```

### Must Include

- [ ] Weather flag set: "rain_risk" (precipitation_probability 55% ≥ 40% threshold — see §17)
- [ ] Rain delay plan included: flexible meal timing note, extra snacks guidance, warm/dry clothing reminder (see §17 rain risk adjustments)
- [ ] Three scenarios generated based on 9:00 AM scheduled start (plan generates from known start time even if schedule is uncertain)
- [ ] Delay plan language in plan: "If there is a rain delay, keep food flexible and have extra snacks available. Keep warm and dry."
- [ ] Estimated next match time treated as uncertain: parent pickup advice acknowledges schedule may shift
- [ ] General hydration reminders present (rain does not reduce hydration need)

### Must Not Include

- ❌ Definitive schedule (plan must not assert the match will start at 9:00 AM without acknowledging delay risk)
- ❌ "hot" or "very_hot" flag (70°F < 85°F threshold)
- ❌ Heavy meal recommendation (rain delay = uncertain timing = keep food portable)
- ❌ Real-time weather alerting or dynamic schedule updates (out of MVP scope)
- ❌ Medical claims

---

## Cross-Scenario: Universal Must-Not-Include

Applies to every generated plan, in all scenarios:

- ❌ Any phrase from SAFETY_DISCLAIMERS §C prohibited list
- ❌ LLM-invented restaurant names, addresses, or menu items not present in structured food_options input
- ❌ LLM-changed timings (LLM may only explain — not modify — the structured plan)
- ❌ Hydration quantities stated as medical prescriptions
- ❌ User data from another user's account appearing in the plan

---

## Open Questions

1. **120-minute boundary (Scenario 1 Normal)**: The `determine_food_strategy` pseudocode (§19) uses `< 150` for the "quick pickup" bucket and `else` for "light meal." A 120-minute gap falls into the "≥ 150" else bucket with current logic — but §16 text says "90–150 minutes → quick pickup food." The pseudocode and the prose description conflict. Engineering should clarify: is the boundary 150 (exclusive) or 150 (inclusive)?

2. **45-minute boundary (Scenario 4 Short)**: The pseudocode `elif gap_minutes < 90` catches gaps of exactly 45. The §15 prose says "45–90 minutes → pre-bought portable food." The §16 prose says "less than 45 minutes before next match → bag food." 45 min exactly falls in "pre-bought portable" per pseudocode. Confirm this is the intended boundary behavior.

3. **Negative gap handling (Scenario 4 Normal/Long)**: The spec does not define behavior when estimated next match time is before estimated match end (negative gap). The pseudocode does not handle this. Backend must define: show overrun warning? clamp to 0? Error state? Recommend: show overrun warning with bag-food fallback.

4. **Scenario 5 uncertain schedule**: The spec mentions "rain delay plan" and "flexible meal timing" in §17 but does not define the data model for an uncertain next match time. If `estimated_next_match_time` is null, §19 returns "No next match provided. Parent can wait until match ends" — but that's incorrect for a delay scenario. Consider a `schedule_confidence` field or a boolean `rain_delay_risk` flag on the match record to drive different logic.

5. **Very_hot flag behavior**: §17 defines "very_hot" (≥ 90°F) as a separate flag but does not describe adjustments specific to `very_hot` vs. `hot`. Adjustments listed in §17 only describe "hot." Backend agent must confirm whether `very_hot` triggers additional adjustments or is purely informational.
