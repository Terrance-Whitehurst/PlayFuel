"""Phase C-infrastructure — unit tests for emergency_number_for() and heat_emergency_text().

These tests enforce the per-country emergency number substitution added in
Phase C-infrastructure (INTERNATIONAL_SCOPE_V1.md §L, hard_coded_strings.py).

Tests:
    emergency_number_for():
        - None input → "your local emergency number" (generic fallback)
        - Empty string → "your local emergency number" (generic fallback)
        - Unknown country code → "your local emergency number" (graceful degradation)
        - Tier 1 markets: US→"911", MX→"911", CA→"911" (North America)
        - Tier 1 markets: GB→"999" (UK)
        - Tier 2 markets: AU→"000", ES/FR/DE/IT→"112", BR→"190"
        - Tier 3 markets: JP→"119"

    heat_emergency_text():
        - None → byte-identical to HEAT_EMERGENCY_TEXT (regression invariant)
        - Unknown country → byte-identical to HEAT_EMERGENCY_TEXT
        - US/MX/CA (911 countries) → byte-identical to HEAT_EMERGENCY_TEXT
          (existing parenthetical is already correct; avoids altering a
           legally-sensitive string without necessity)
        - GB (999) → contains "Call 999", not "Call 911"
        - AU (000) → contains "Call 000", not "Call 911"
        - EU markets (ES/FR: 112) → contains "Call 112", not "Call 911"
        - All outputs are non-empty strings

    Regression invariant (heat_emergency_text(None) == HEAT_EMERGENCY_TEXT):
        This is the critical backward-compat guarantee. Any caller that was using
        HEAT_EMERGENCY_TEXT directly continues to get identical output after
        Phase C-infrastructure when venue_country is unknown (None or not in table).
"""
from __future__ import annotations

import pytest

from playfuel_api.rules.hard_coded_strings import (
    HEAT_EMERGENCY_TEXT,
    emergency_number_for,
    heat_emergency_text,
)


# ── emergency_number_for() ────────────────────────────────────────────────────

class TestEmergencyNumberFor:
    """Tests for emergency_number_for(venue_country)."""

    def test_none_returns_generic_fallback(self):
        """None venue_country → generic fallback phrase (not a dial number)."""
        result = emergency_number_for(None)
        assert result == "your local emergency number"

    def test_empty_string_returns_generic_fallback(self):
        """Empty string → generic fallback (same as None)."""
        result = emergency_number_for("")
        assert result == "your local emergency number"

    def test_unknown_country_returns_generic_fallback(self):
        """Country code not in the lookup table → generic fallback."""
        result = emergency_number_for("XX")
        assert result == "your local emergency number"

    # Tier 1 — North America (911)
    @pytest.mark.parametrize("country", ["US", "MX", "CA"])
    def test_north_america_returns_911(self, country: str):
        """US, MX, CA all use 911 — Mexico unified to 911 in 2017."""
        assert emergency_number_for(country) == "911", (
            f"Expected '911' for {country}, got {emergency_number_for(country)!r}"
        )

    # Tier 1 — UK
    def test_gb_returns_999(self):
        """UK national emergency number is 999."""
        assert emergency_number_for("GB") == "999"

    # Tier 2 — Australia
    def test_au_returns_000(self):
        """Australia triple-zero emergency number."""
        assert emergency_number_for("AU") == "000"

    # Tier 2 — EU (112)
    @pytest.mark.parametrize("country", ["ES", "FR", "DE", "IT"])
    def test_eu_tier2_returns_112(self, country: str):
        """European pan-standard emergency number 112."""
        assert emergency_number_for(country) == "112", (
            f"Expected '112' for {country}, got {emergency_number_for(country)!r}"
        )

    # Tier 2 — Brazil
    def test_br_returns_190(self):
        """Brazil universal first-contact emergency number (police / first response)."""
        assert emergency_number_for("BR") == "190"

    # Tier 3 — Japan
    def test_jp_returns_119(self):
        """Japan fire/ambulance emergency number (police is 110; 119 is the first-contact for medical)."""
        assert emergency_number_for("JP") == "119"


# ── heat_emergency_text() ─────────────────────────────────────────────────────

class TestHeatEmergencyText:
    """Tests for heat_emergency_text(venue_country).

    Critical invariant: heat_emergency_text(None) must be byte-identical to
    HEAT_EMERGENCY_TEXT. Any deviation is a regression.
    """

    def test_none_is_byte_identical_to_constant(self):
        """heat_emergency_text(None) == HEAT_EMERGENCY_TEXT — byte-identical regression invariant."""
        result = heat_emergency_text(None)
        assert result == HEAT_EMERGENCY_TEXT, (
            "heat_emergency_text(None) must be byte-identical to HEAT_EMERGENCY_TEXT — "
            "this is the critical backward-compat regression invariant"
        )

    def test_no_args_is_byte_identical_to_constant(self):
        """heat_emergency_text() with no args (default None) == HEAT_EMERGENCY_TEXT."""
        result = heat_emergency_text()
        assert result == HEAT_EMERGENCY_TEXT

    def test_unknown_country_is_byte_identical_to_constant(self):
        """Unknown country → HEAT_EMERGENCY_TEXT unchanged (generic parenthetical covers it)."""
        result = heat_emergency_text("XX")
        assert result == HEAT_EMERGENCY_TEXT

    # 911 countries: US, MX, CA → byte-identical (no substitution needed)
    @pytest.mark.parametrize("country", ["US", "MX", "CA"])
    def test_911_countries_return_original_text_unchanged(self, country: str):
        """911-country venues return HEAT_EMERGENCY_TEXT verbatim.

        The existing parenthetical '(or your local emergency number)' is already
        correct for 911 markets. Leaving the string unchanged avoids touching a
        legally-sensitive text without necessity.
        """
        result = heat_emergency_text(country)
        assert result == HEAT_EMERGENCY_TEXT, (
            f"heat_emergency_text('{country}') must equal HEAT_EMERGENCY_TEXT unchanged "
            f"(911 country — no substitution needed)"
        )

    def test_gb_substitutes_999(self):
        """UK (GB) → 'Call 999' substituted for 'Call 911 (or your local emergency number)'."""
        result = heat_emergency_text("GB")
        assert "Call 999" in result, (
            f"Expected 'Call 999' in GB heat_emergency_text, got: {result!r}"
        )
        assert "Call 911 (or your local emergency number)" not in result, (
            "GB result must not contain the 911 parenthetical after substitution"
        )
        # Safety: still contains the critical warning text
        assert "stop play and seek medical help" in result

    def test_au_substitutes_000(self):
        """Australia (AU) → 'Call 000' substituted."""
        result = heat_emergency_text("AU")
        assert "Call 000" in result, (
            f"Expected 'Call 000' in AU heat_emergency_text, got: {result!r}"
        )
        assert "Call 911 (or your local emergency number)" not in result
        assert "stop play and seek medical help" in result

    @pytest.mark.parametrize("country,number", [("ES", "112"), ("FR", "112")])
    def test_eu_tier2_substitutes_112(self, country: str, number: str):
        """EU Tier 2 markets → 'Call 112' substituted."""
        result = heat_emergency_text(country)
        assert f"Call {number}" in result, (
            f"Expected 'Call {number}' in {country} heat_emergency_text, got: {result!r}"
        )
        assert "Call 911 (or your local emergency number)" not in result
        assert "stop play and seek medical help" in result

    def test_all_outputs_are_nonempty(self):
        """heat_emergency_text() must always return a non-empty string."""
        for country in [None, "US", "MX", "CA", "GB", "AU", "ES", "FR", "BR", "JP", "XX"]:
            result = heat_emergency_text(country)
            assert result, f"heat_emergency_text({country!r}) returned empty string"

    def test_core_warning_preserved_after_substitution(self):
        """Critical safety warning text is preserved for all countries after substitution."""
        core_warning = "stop play and seek medical help"
        for country in ["GB", "AU", "ES", "FR", "BR", "JP"]:
            result = heat_emergency_text(country)
            assert core_warning in result, (
                f"Core warning text missing from heat_emergency_text('{country}'): {result!r}"
            )
