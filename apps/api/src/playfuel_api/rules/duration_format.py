"""Human-readable duration formatting — HEADER_BUBBLES_V1 / user request 2026-04-28.

friendly_duration() converts a raw minute count to a compact, human-readable
string using hr/min abbreviations (no plurals, no spelled-out words).

Format rules (locked per Engineering brief):
    0              → "0 min"
    1–59           → "X min"          e.g. "30 min", "45 min"
    60             → "1 hr"
    61–119         → "1 hr Y min"     e.g. "1 hr 15 min"
    120 (exact hr) → "2 hr"
    120+           → "X hr" or "X hr Y min"
    negative       → "-" + friendly_duration(abs(value))  e.g. "-45 min", "-1 hr 30 min"

Abbreviations are always "hr" and "min" (compact, avoids singular/plural branching).
Used across all narrative strings that display match or gap durations.
"""


def friendly_duration(minutes: int) -> str:
    """Format *minutes* as a human-readable duration string.

    Examples::

        >>> friendly_duration(0)
        '0 min'
        >>> friendly_duration(30)
        '30 min'
        >>> friendly_duration(60)
        '1 hr'
        >>> friendly_duration(75)
        '1 hr 15 min'
        >>> friendly_duration(90)
        '1 hr 30 min'
        >>> friendly_duration(120)
        '2 hr'
        >>> friendly_duration(135)
        '2 hr 15 min'
        >>> friendly_duration(180)
        '3 hr'
        >>> friendly_duration(225)
        '3 hr 45 min'
        >>> friendly_duration(-45)
        '-45 min'
        >>> friendly_duration(-90)
        '-1 hr 30 min'

    Args:
        minutes: Duration in whole minutes. May be negative (overrun case).

    Returns:
        Compact string using "hr" / "min" abbreviations.
    """
    if minutes < 0:
        return "-" + friendly_duration(-minutes)
    if minutes < 60:
        return f"{minutes} min"
    hr, min_ = divmod(minutes, 60)
    if min_ == 0:
        return f"{hr} hr"
    return f"{hr} hr {min_} min"
