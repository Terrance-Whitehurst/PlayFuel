"""Regression test: match timeline detail strings must not embed UTC-formatted clock times.

Root cause (plan.py — build_timeline):
    _fmt_time(dt) read dt.hour (UTC) and embedded "H:MM AM/PM" in the detail
    string of the 'match' TimelineEventOut. For a 9 AM Eastern match
    (13:00 UTC), the detail read "Scheduled start (1:00 PM)" — 4 hours wrong.

Fix:
    detail string changed to "Scheduled start" (no time parenthetical).
    The `time` field (UTC ISO 8601) carries the timestamp; iOS asClockTimeFromISO
    converts to device-local time correctly — no need for a server-side AM/PM string.

Related:
    scenarios.py _fmt_time() was independently fixed in fix/scenario-card-end-time
    to return ISO 8601 UTC. The two functions are separate; this test covers plan.py.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import uuid4

from playfuel_api.models.db import MatchRow
from playfuel_api.models.enums import TimelineEventKind
from playfuel_api.rules.plan import build_timeline
from playfuel_api.rules.scenarios import generate_match_scenarios

# A match at 13:00 UTC — represents 9 AM Eastern (UTC-4 in summer).
# The old _fmt_time bug would embed "1:00 PM" (UTC) in the detail string.
_UTC_1PM = datetime(2026, 5, 4, 13, 0, tzinfo=timezone.utc)

_AMPM_RE = re.compile(r"\b\d{1,2}:\d{2}\s*(AM|PM|am|pm)\b")


def _make_singles_match(start: datetime = _UTC_1PM, display_order: int = 1) -> MatchRow:
    """Build a minimal singles MatchRow for timeline tests."""
    return MatchRow(
        id=uuid4(),
        tournament_id=uuid4(),
        scheduled_start=start,
        format="singles",
        doubles_format=None,
        display_order=display_order,
        created_at=start,
        updated_at=start,
    )


class TestTimelineNoUtcClock:
    """build_timeline() must not embed UTC AM/PM times in any detail string."""

    def setup_method(self):
        m1 = _make_singles_match()
        scenarios = generate_match_scenarios(m1, None)
        self.timeline = build_timeline([m1], scenarios)

    def test_no_ampm_pattern_in_any_detail(self):
        """No timeline event detail should contain an H:MM AM/PM pattern.

        For a 13:00 UTC match the old code produced 'Scheduled start (1:00 PM)'.
        After the fix all detail strings are plain text — no AM/PM clock times.
        """
        for event in self.timeline:
            assert not _AMPM_RE.search(event.detail), (
                f"Event {event.kind.value!r} detail contains a UTC AM/PM time string: "
                f"{event.detail!r}. This embeds the UTC hour directly, which is wrong "
                "for non-UTC device timezones. Drop the parenthetical; the `time` field "
                "carries the UTC ISO for local-timezone rendering on iOS."
            )

    def test_match_event_detail_is_plain_scheduled_start(self):
        """The 'match' event detail must be exactly 'Scheduled start' (no parenthetical)."""
        match_events = [e for e in self.timeline if e.kind == TimelineEventKind.match]
        assert match_events, "Expected at least one 'match' TimelineEvent"
        for evt in match_events:
            assert evt.detail == "Scheduled start", (
                f"Expected detail='Scheduled start', got {evt.detail!r}. "
                "The parenthetical (e.g. '(1:00 PM)') was UTC-formatted and wrong "
                "for non-UTC users."
            )

    def test_match_event_time_field_is_utc_iso(self):
        """The `time` field on the match event must be a valid UTC ISO 8601 string.

        This is what iOS asClockTimeFromISO parses to render device-local time.
        The plain 'Scheduled start' detail is correct precisely because the time
        field carries the timestamp.
        """
        match_evt = next(e for e in self.timeline if e.kind == TimelineEventKind.match)
        # Must parse as UTC datetime without error.
        parsed = datetime.fromisoformat(match_evt.time)
        assert parsed.hour == 13, (
            f"Match event time field should represent 13:00 UTC; got {match_evt.time!r}"
        )

    def test_specific_old_bug_string_absent(self):
        """'1:00 PM' must not appear in any event detail for a 13:00 UTC match.

        This was the exact string the bug produced (dt.hour=13 → '1:00 PM').
        """
        for event in self.timeline:
            assert "1:00 PM" not in event.detail, (
                f"Found the old UTC-formatted bug string '1:00 PM' in "
                f"event {event.kind.value!r} detail: {event.detail!r}"
            )
