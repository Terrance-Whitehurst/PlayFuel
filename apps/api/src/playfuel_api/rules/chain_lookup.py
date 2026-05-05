"""Chain registry lookup — Phase 5 chain-menu-items feature.

Loads ``rules/chain_menus.json`` once at module import (no per-request I/O).
Provides two public functions:

    normalize_name(raw: str) -> str
        Lowercase + strip store-number suffixes + strip punctuation.

    lookup_chain(name: str) -> dict | None
        Return the matching chain registry entry, or None.
        Stub entries (``as_of == "TBD"`` or empty ``suggestions``) are skipped —
        only fully populated entries can match (spec §I / AC#4).

§G.0 pre-check note
--------------------
A live ``flyctl logs`` spot-check of ``places.displayName.text`` for Chipotle,
Starbucks, and Chick-fil-A was deferred — no live plan-gen traffic is available
in the current environment.  Verified instead via the Dallas ``MockPlacesProvider``
fixture (``services/places.py``):
    ``"Chipotle Mexican Grill"``  → normalize → ``"chipotle mexican grill"`` → alias ✅
    ``"Starbucks"``               → normalize → ``"starbucks"``               → alias ✅
Both match their respective registry entries.  Chick-fil-A is not in the mock
fixture; its alias coverage (``"chick fil a"``, ``"chickfila"``) is validated by
``test_lookup_chain_exact_match_chick_fil_a`` and
``test_lookup_chain_store_number_stripped`` using synthetic inputs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

_REGISTRY_PATH = Path(__file__).parent / "chain_menus.json"


def _load_registry() -> dict:
    """Load chain_menus.json from disk.  Called once at module import."""
    with open(_REGISTRY_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# Module-level singleton — JSON is read once; no per-request file I/O.
_REGISTRY: dict = _load_registry()


def normalize_name(name: str) -> str:
    """Lowercase, strip store-number suffixes, strip punctuation.

    Steps (order matters — store-number regexes run BEFORE punctuation strip):

    1. Lowercase the entire string.
    2. Strip ``#<digits>`` store-number suffixes (e.g. ``#4521``).
    3. Strip `` - <digits>`` suffixes (e.g. `` - 123``).
       The word-boundary ``\\b`` prevents matching digit-free tokens like
       ``"chick-fil-a"`` (the ``a`` after ``-`` is not ``\\d``).
    4. Strip drive-thru variant text.
    5. Strip remaining punctuation (``[^\\w\\s]``).
    6. Collapse runs of whitespace to a single space.

    DEVIATION from spec §D: spec listed punctuation stripping first, then the
    ``#<digits>`` / ``-<digits>`` regexes.  That ordering causes the number-strip
    regexes to never match (the ``#`` is already removed by step 1).  The correct
    order is to strip numeric suffixes *before* punctuation.

    Args:
        name: Raw place display name as returned by the Places API or mock.

    Returns:
        Normalized string suitable for alias comparison.

    Examples:
        >>> normalize_name("Chick-fil-A #4521")
        'chickfila'
        >>> normalize_name("CHIPOTLE")
        'chipotle'
        >>> normalize_name("Chipotle Mexican Grill")
        'chipotle mexican grill'
        >>> normalize_name("Starbucks")
        'starbucks'
    """
    n = name.lower()
    # Step 2: strip #<digits> store-number suffixes (before punctuation removal)
    n = re.sub(r"\s*#\s*\d+", "", n)
    # Step 3: strip " - <digits>" suffixes (e.g. "Subway - 12345")
    n = re.sub(r"\s*-\s*\d+\b", "", n)
    # Step 4: strip drive-thru variants
    n = re.sub(r"\b(drive\s*thru|drivethru|drive\s*through)\b", "", n)
    # Step 5: strip remaining punctuation (hyphens, apostrophes, periods, etc.)
    n = re.sub(r"[^\w\s]", "", n)
    # Step 6: collapse whitespace
    return " ".join(n.split())


def lookup_chain(name: str) -> Optional[dict]:
    """Return the registry entry for ``name``, or ``None`` if not matched.

    Normalization is applied to ``name`` before comparison against each chain's
    ``match_aliases`` list (aliases are pre-normalized in the registry).

    **Stub entries are skipped.**  An entry is a stub when ``as_of == "TBD"``
    or when ``suggestions`` is empty / absent.  This guarantees that stub
    chains never silently match and return an empty suggestions dict.

    Matching algorithm: first exact match in alias list wins (no fuzzy match).

    Args:
        name: Raw display name from ``RawPlace.name``.

    Returns:
        The matching chain ``dict`` (with ``"suggestions"``, ``"as_of"``,
        ``"display_name"``, etc.) or ``None``.
    """
    normalized = normalize_name(name)
    for chain in _REGISTRY.get("chains", []):
        # Skip stubs: entries with as_of == "TBD" never match.
        if chain.get("as_of") == "TBD":
            continue
        # Skip stubs: entries with empty / missing suggestions never match.
        if not chain.get("suggestions"):
            continue
        for alias in chain.get("match_aliases", []):
            if alias == normalized:
                return chain
    return None
