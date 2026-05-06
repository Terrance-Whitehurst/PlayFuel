"""Regression tests for the estimated_duration_minutes removal.

DR_42: estimated_duration_minutes removed from MatchCreate, MatchUpdate, and MatchRow.
The DB column is kept (nullable, unused). Older iOS clients that still send
estimatedDurationMinutes are not broken — Pydantic v2 default extra='ignore' drops
unknown fields silently.

Two invariants pinned here:
  MDR-1  MatchCreate accepts payloads WITHOUT estimated_duration_minutes (field gone)
  MDR-2  MatchCreate ignores unknown extra field 'estimatedDurationMinutes' (old-iOS compat)
  MDR-3  MatchUpdate accepts payloads WITHOUT estimated_duration_minutes
  MDR-4  MatchUpdate ignores estimatedDurationMinutes sent by older clients
  MDR-5  MatchRow parses without estimated_duration_minutes (field removed from model)
  MDR-6  estimated_duration_minutes no longer in MatchCreate model fields
  MDR-7  estimated_duration_minutes no longer in MatchUpdate model fields
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from playfuel_api.models.db import MatchRow
from playfuel_api.routes.matches import MatchCreate, MatchUpdate


# ── MDR-1: MatchCreate parses without estimated_duration_minutes ─────────────

def test_mdr1_match_create_parses_without_estimated_duration():
    """MatchCreate should validate cleanly when estimated_duration_minutes is absent."""
    obj = MatchCreate(
        scheduled_start=datetime(2026, 5, 15, 14, 0, tzinfo=timezone.utc),
        round=32,
        format="singles",
    )
    assert obj.round == 32
    # The field must not appear in the model's field set
    assert "estimated_duration_minutes" not in obj.model_fields_set


# ── MDR-2: MatchCreate silently ignores extra field from old iOS clients ──────

def test_mdr2_match_create_ignores_estimated_duration_extra_field():
    """Older iOS clients that still send estimatedDurationMinutes get it ignored (not 422)."""
    obj = MatchCreate(
        scheduled_start=datetime(2026, 5, 15, 14, 0, tzinfo=timezone.utc),
        round=64,
        format="singles",
        estimatedDurationMinutes=90,   # camelCase — old iOS payload key
    )
    assert obj.round == 64
    dumped = obj.model_dump(exclude_none=True)
    assert "estimated_duration_minutes" not in dumped
    assert "estimatedDurationMinutes" not in dumped


# ── MDR-3: MatchUpdate parses without estimated_duration_minutes ─────────────

def test_mdr3_match_update_parses_without_estimated_duration():
    """MatchUpdate should validate cleanly when only allowed fields are supplied."""
    obj = MatchUpdate(round=16)
    assert obj.round == 16
    assert "estimated_duration_minutes" not in obj.model_fields_set


# ── MDR-4: MatchUpdate silently ignores extra field from old iOS clients ──────

def test_mdr4_match_update_ignores_estimated_duration_extra_field():
    """Older iOS clients that still send estimatedDurationMinutes get it ignored."""
    obj = MatchUpdate(
        round=8,
        estimatedDurationMinutes=120,  # camelCase — old iOS payload key
    )
    assert obj.round == 8
    dumped = obj.model_dump(exclude_none=True)
    assert "estimated_duration_minutes" not in dumped
    assert "estimatedDurationMinutes" not in dumped


# ── MDR-5: MatchRow parses without estimated_duration_minutes ────────────────

def test_mdr5_match_row_parses_without_estimated_duration():
    """MatchRow should parse a DB row dict that omits estimated_duration_minutes."""
    row = MatchRow(
        id="c0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        tournament_id="b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
        scheduled_start=datetime(2026, 5, 15, 14, 0, tzinfo=timezone.utc),
        format="singles",
        display_order=1,
        round_label="R32",
        created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )
    assert row.format == "singles"
    assert not hasattr(row, "estimated_duration_minutes")


# ── MDR-6: estimated_duration_minutes absent from MatchCreate field list ──────

def test_mdr6_estimated_duration_not_in_match_create_fields():
    """estimated_duration_minutes must not be a declared field on MatchCreate."""
    assert "estimated_duration_minutes" not in MatchCreate.model_fields


# ── MDR-7: estimated_duration_minutes absent from MatchUpdate field list ──────

def test_mdr7_estimated_duration_not_in_match_update_fields():
    """estimated_duration_minutes must not be a declared field on MatchUpdate."""
    assert "estimated_duration_minutes" not in MatchUpdate.model_fields
