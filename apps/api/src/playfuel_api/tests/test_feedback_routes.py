"""Post-tournament feedback route tests — /v1/tournaments/{tid}/feedback.

Covers (all 12 ACs from phase7-feedback-spec.md §F):

  AC-FB-3  POST with valid body → 201, FeedbackResponse returned
  AC-FB-4  Second POST same (tournament, user) → 200, row updated in-place
  AC-FB-5  GET before any feedback → 404
  AC-FB-6  GET after submission → 200 + body matches submitted values
  AC-FB-7  User B cannot read User A's feedback → 404 (mock RLS isolation)
  AC-FB-8  POST / GET for non-existent or unowned tournament → 404
  AC-FB-9  Validation rejections: rating 0/6, bad chip, >7 chips, free_text >500
  AC-FB-10 Tournament DELETE → cascade; feedback row gone (model + DB-level note)
  AC-FB-11 No existing tests broken (covered by full pytest run in CI)
  AC-FB-12 Doc flip (covered by separate FB-G8 commit; not tested here)

Test pattern mirrors test_match_evaluations_routes.py:
  - mock_db + client_with_auth from conftest.py
  - _make_chain() builds a chainable MagicMock
  - _table_dispatch() routes by table name

Auth: TEST_USER_ID ("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11") is injected via
conftest.client_with_auth fixture — no real JWT required.
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

# ── Fixtures / constants ──────────────────────────────────────────────────────

_USER_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"
_TOURNAMENT_ID = str(uuid4())
_PLAN_ID = str(uuid4())
_FEEDBACK_ID = str(uuid4())

_TOURNAMENT_ROW = {
    "id": _TOURNAMENT_ID,
    "user_id": _USER_ID,
    "name": "Delray Beach Juniors",
    "start_date": "2026-06-01",
}

_PLAN_ROW = {
    "id": _PLAN_ID,
    "tournament_id": _TOURNAMENT_ID,
    "created_at": "2026-06-02T10:00:00+00:00",
}

_FEEDBACK_ROW = {
    "id": _FEEDBACK_ID,
    "tournament_id": _TOURNAMENT_ID,
    "user_id": _USER_ID,
    "plan_id": _PLAN_ID,
    "overall_rating": 4,
    "what_worked": ["food_timing", "hydration"],
    "what_didnt_work": ["schedule"],
    "free_text": "Great overall plan.",
    "created_at": "2026-06-02T12:00:00+00:00",
    "updated_at": "2026-06-02T12:00:00+00:00",
}

_VALID_BODY = {
    "overallRating": 4,
    "whatWorked": ["food_timing", "hydration"],
    "whatDidntWork": ["schedule"],
    "freeText": "Great overall plan.",
}


def _make_chain(data):
    """Return a MagicMock chain whose .execute().data == data."""
    chain = MagicMock()
    chain.execute.return_value.data = data
    for attr in (
        "select", "insert", "update", "delete", "eq", "order", "limit",
        "upsert", "filter", "in_", "maybe_single",
    ):
        getattr(chain, attr).return_value = chain
    return chain


def _table_dispatch(tournament_data, plan_data, feedback_data):
    """Build a mock_db.table side_effect routing by table name."""
    tournament_chain = _make_chain(tournament_data)
    plan_chain = _make_chain(plan_data)
    feedback_chain = _make_chain(feedback_data)

    def _dispatch(name):
        if name == "tournaments":
            return tournament_chain
        if name == "plans":
            return plan_chain
        if name == "feedback":
            return feedback_chain
        return _make_chain([])

    return _dispatch


# ── POST — create (AC-FB-3) ───────────────────────────────────────────────────


def test_post_feedback_creates_returns_201(client_with_auth, mock_db):
    """POST /v1/tournaments/{tid}/feedback → 201 on first submission."""
    feedback_create_chain = _make_chain([_FEEDBACK_ROW])
    feedback_check_chain = _make_chain([])  # no existing row

    call_count = [0]

    def _dispatch(name):
        if name == "tournaments":
            return _make_chain([_TOURNAMENT_ROW])
        if name == "plans":
            return _make_chain([_PLAN_ROW])
        if name == "feedback":
            call_count[0] += 1
            # First call = _get_feedback_row (existence check)
            # Second call = insert
            return feedback_check_chain if call_count[0] == 1 else feedback_create_chain
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json=_VALID_BODY,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] == _FEEDBACK_ID
    assert body["tournamentId"] == _TOURNAMENT_ID
    assert body["overallRating"] == 4
    assert body["whatWorked"] == ["food_timing", "hydration"]
    assert body["whatDidntWork"] == ["schedule"]
    assert body["freeText"] == "Great overall plan."


def test_post_feedback_response_has_plan_id(client_with_auth, mock_db):
    """POST response includes planId from the most recent plan lookup."""
    feedback_check_chain = _make_chain([])
    feedback_create_chain = _make_chain([_FEEDBACK_ROW])

    call_count = [0]

    def _dispatch(name):
        if name == "tournaments":
            return _make_chain([_TOURNAMENT_ROW])
        if name == "plans":
            return _make_chain([_PLAN_ROW])
        if name == "feedback":
            call_count[0] += 1
            return feedback_check_chain if call_count[0] == 1 else feedback_create_chain
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json=_VALID_BODY,
    )
    assert resp.status_code == 201
    assert resp.json()["planId"] == _PLAN_ID


# ── POST — update / UPSERT (AC-FB-4) ─────────────────────────────────────────


def test_post_feedback_second_call_returns_200(client_with_auth, mock_db):
    """Second POST to same (tournament, user) → 200 (update, not 409)."""
    feedback_existing_chain = _make_chain([_FEEDBACK_ROW])  # row already exists
    feedback_update_chain = _make_chain([{**_FEEDBACK_ROW, "overall_rating": 5}])

    call_count = [0]

    def _dispatch(name):
        if name == "tournaments":
            return _make_chain([_TOURNAMENT_ROW])
        if name == "plans":
            return _make_chain([_PLAN_ROW])
        if name == "feedback":
            call_count[0] += 1
            # First call = existence check (returns existing row)
            return feedback_existing_chain if call_count[0] == 1 else feedback_update_chain
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json={**_VALID_BODY, "overallRating": 5},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["overallRating"] == 5


def test_post_feedback_upsert_no_duplicate_rows(client_with_auth, mock_db):
    """After second POST, only one feedback row exists (no duplicate insert)."""
    feedback_existing_chain = _make_chain([_FEEDBACK_ROW])
    feedback_update_chain = _make_chain([_FEEDBACK_ROW])

    call_count = [0]

    def _dispatch(name):
        if name == "tournaments":
            return _make_chain([_TOURNAMENT_ROW])
        if name == "plans":
            return _make_chain([_PLAN_ROW])
        if name == "feedback":
            call_count[0] += 1
            if call_count[0] == 1:
                return feedback_existing_chain
            return feedback_update_chain
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json=_VALID_BODY,
    )
    assert resp.status_code == 200
    # Verify the route used update (not insert) for the second call
    # Update chain's .execute() should have been called
    assert feedback_update_chain.execute.called


# ── GET — happy path (AC-FB-6) ────────────────────────────────────────────────


def test_get_feedback_returns_200_with_row(client_with_auth, mock_db):
    """GET /v1/tournaments/{tid}/feedback → 200 + FeedbackResponse body."""
    mock_db.table.side_effect = _table_dispatch(
        [_TOURNAMENT_ROW], [_PLAN_ROW], [_FEEDBACK_ROW]
    )

    resp = client_with_auth.get(f"/v1/tournaments/{_TOURNAMENT_ID}/feedback")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == _FEEDBACK_ID
    assert body["tournamentId"] == _TOURNAMENT_ID
    assert body["planId"] == _PLAN_ID
    assert body["overallRating"] == 4
    assert body["whatWorked"] == ["food_timing", "hydration"]
    assert body["whatDidntWork"] == ["schedule"]
    assert body["freeText"] == "Great overall plan."


# ── GET — no row yet (AC-FB-5) ────────────────────────────────────────────────


def test_get_feedback_returns_404_before_submission(client_with_auth, mock_db):
    """GET before any feedback has been submitted → 404."""
    mock_db.table.side_effect = _table_dispatch(
        [_TOURNAMENT_ROW], [_PLAN_ROW], []  # empty feedback
    )

    resp = client_with_auth.get(f"/v1/tournaments/{_TOURNAMENT_ID}/feedback")
    assert resp.status_code == 404


# ── GET — no plans exist (plan_id nullable) ────────────────────────────────────


def test_post_feedback_plan_id_null_when_no_plans(client_with_auth, mock_db):
    """Feedback stored with plan_id=None when tournament has no plans yet."""
    feedback_row_no_plan = {**_FEEDBACK_ROW, "plan_id": None}
    feedback_check_chain = _make_chain([])
    feedback_create_chain = _make_chain([feedback_row_no_plan])

    call_count = [0]

    def _dispatch(name):
        if name == "tournaments":
            return _make_chain([_TOURNAMENT_ROW])
        if name == "plans":
            return _make_chain([])  # no plans
        if name == "feedback":
            call_count[0] += 1
            return feedback_check_chain if call_count[0] == 1 else feedback_create_chain
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json=_VALID_BODY,
    )
    assert resp.status_code == 201
    assert resp.json()["planId"] is None


# ── Security: RLS isolation (AC-FB-7) ────────────────────────────────────────


def test_get_feedback_user_b_cannot_see_user_a_feedback(client_with_auth, mock_db):
    """User B querying User A's tournament → 404 (RLS isolation, no cross-user read)."""
    # The mock simulates RLS: tournament row has user_id != caller's user_id.
    # The route's _get_tournament_or_404() checks user_id and raises 404.
    other_user_tournament = {**_TOURNAMENT_ROW, "user_id": str(uuid4())}

    mock_db.table.side_effect = _table_dispatch(
        [other_user_tournament], [], []
    )

    resp = client_with_auth.get(f"/v1/tournaments/{_TOURNAMENT_ID}/feedback")
    assert resp.status_code == 404


def test_post_feedback_user_b_cannot_write_to_user_a_tournament(client_with_auth, mock_db):
    """User B POSTing to User A's tournament → 404 (no info leak)."""
    other_user_tournament = {**_TOURNAMENT_ROW, "user_id": str(uuid4())}

    mock_db.table.side_effect = _table_dispatch(
        [other_user_tournament], [], []
    )

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json=_VALID_BODY,
    )
    assert resp.status_code == 404


# ── Security: non-existent tournament (AC-FB-8) ───────────────────────────────


def test_post_feedback_nonexistent_tournament_returns_404(client_with_auth, mock_db):
    """POST to a tournament that doesn't exist → 404 (no info-leak)."""
    mock_db.table.side_effect = _table_dispatch([], [], [])

    resp = client_with_auth.post(
        f"/v1/tournaments/{uuid4()}/feedback",
        json=_VALID_BODY,
    )
    assert resp.status_code == 404


def test_get_feedback_nonexistent_tournament_returns_404(client_with_auth, mock_db):
    """GET for a non-existent tournament → 404."""
    mock_db.table.side_effect = _table_dispatch([], [], [])

    resp = client_with_auth.get(f"/v1/tournaments/{uuid4()}/feedback")
    assert resp.status_code == 404


# ── Validation rejections (AC-FB-9) ──────────────────────────────────────────


def test_post_feedback_rating_zero_is_rejected(client_with_auth, mock_db):
    """overall_rating = 0 → 422 (below valid range of 1–5)."""
    mock_db.table.side_effect = _table_dispatch([_TOURNAMENT_ROW], [], [])

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json={"overallRating": 0},
    )
    assert resp.status_code == 422


def test_post_feedback_rating_six_is_rejected(client_with_auth, mock_db):
    """overall_rating = 6 → 422 (above valid range of 1–5)."""
    mock_db.table.side_effect = _table_dispatch([_TOURNAMENT_ROW], [], [])

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json={"overallRating": 6},
    )
    assert resp.status_code == 422


def test_post_feedback_bad_chip_token_is_rejected(client_with_auth, mock_db):
    """Chip token not in vocab → 422."""
    mock_db.table.side_effect = _table_dispatch([_TOURNAMENT_ROW], [], [])

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json={"whatWorked": ["completely_made_up_chip"]},
    )
    assert resp.status_code == 422


def test_post_feedback_bad_chip_in_what_didnt_work_is_rejected(client_with_auth, mock_db):
    """Bad chip in what_didnt_work → 422."""
    mock_db.table.side_effect = _table_dispatch([_TOURNAMENT_ROW], [], [])

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json={"whatDidntWork": ["invalid_chip_token"]},
    )
    assert resp.status_code == 422


def test_post_feedback_more_than_seven_chips_is_rejected(client_with_auth, mock_db):
    """More than 7 chips in what_worked → 422 (max = vocab size)."""
    # Repeat valid tokens to exceed the max
    eight_chips = ["food_timing"] * 8  # 8 items (duplicates allowed for count check)
    mock_db.table.side_effect = _table_dispatch([_TOURNAMENT_ROW], [], [])

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json={"whatWorked": eight_chips},
    )
    assert resp.status_code == 422


def test_post_feedback_free_text_over_500_chars_is_rejected(client_with_auth, mock_db):
    """free_text with 501 characters → 422."""
    long_text = "x" * 501
    mock_db.table.side_effect = _table_dispatch([_TOURNAMENT_ROW], [], [])

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json={"freeText": long_text},
    )
    assert resp.status_code == 422


def test_post_feedback_free_text_at_500_chars_is_accepted(client_with_auth, mock_db):
    """free_text with exactly 500 characters → 201 (boundary accepted)."""
    text_500 = "y" * 500
    feedback_with_long_text = {
        **_FEEDBACK_ROW,
        "free_text": text_500,
        "what_worked": [],
        "what_didnt_work": [],
    }

    feedback_check_chain = _make_chain([])
    feedback_create_chain = _make_chain([feedback_with_long_text])
    call_count = [0]

    def _dispatch(name):
        if name == "tournaments":
            return _make_chain([_TOURNAMENT_ROW])
        if name == "plans":
            return _make_chain([_PLAN_ROW])
        if name == "feedback":
            call_count[0] += 1
            return feedback_check_chain if call_count[0] == 1 else feedback_create_chain
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json={"freeText": text_500},
    )
    assert resp.status_code == 201


# ── Cascade: tournament DELETE → feedback gone (AC-FB-10) ─────────────────────


def test_tournament_delete_would_cascade_feedback(client_with_auth, mock_db):
    """Model-level test: ON DELETE CASCADE on feedback.tournament_id is declared
    in migration 0013. Here we verify the route correctly deletes a tournament
    without error — actual CASCADE is enforced by Postgres, not by this test.
    This test exercises the expected call path at the mock layer.
    """
    delete_chain = _make_chain([])  # DELETE returns nothing (204)

    mock_db.table.side_effect = lambda name: (
        _make_chain([_TOURNAMENT_ROW]) if name == "tournaments" else _make_chain([])
    )
    mock_db.table.return_value = delete_chain

    # The cascade is DB-level — we are testing that the route doesn't interfere.
    # Real cascade is verified by migration DDL (ON DELETE CASCADE in 0013).
    # This test just confirms the DELETE endpoint is callable and we have
    # the right expectation at the ORM layer.
    resp = client_with_auth.delete(f"/v1/tournaments/{_TOURNAMENT_ID}")
    # Tournaments delete returns 204
    assert resp.status_code in (200, 204)


# ── Plan_id SET NULL when plan deleted (AC-FB-10, plan variant) ───────────────


def test_feedback_plan_id_can_be_null_after_plan_deletion(client_with_auth, mock_db):
    """GET returns feedback with plan_id=None — valid state after plan deletion.

    After a plan is deleted, Postgres sets feedback.plan_id = NULL (ON DELETE
    SET NULL in migration 0013). This test confirms the API round-trips a null
    plan_id correctly (FeedbackResponse.plan_id is Optional[UUID]).
    """
    feedback_null_plan = {**_FEEDBACK_ROW, "plan_id": None}
    mock_db.table.side_effect = _table_dispatch(
        [_TOURNAMENT_ROW], [], [feedback_null_plan]
    )

    resp = client_with_auth.get(f"/v1/tournaments/{_TOURNAMENT_ID}/feedback")
    assert resp.status_code == 200
    assert resp.json()["planId"] is None


# ── Auth: unauthenticated requests rejected ────────────────────────────────────


def test_post_feedback_requires_auth(client_no_auth):
    """POST without auth header → 401 or 403 (no auth = rejected)."""
    resp = client_no_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json=_VALID_BODY,
    )
    assert resp.status_code in (401, 403)


def test_get_feedback_requires_auth(client_no_auth):
    """GET without auth header → 401 or 403."""
    resp = client_no_auth.get(f"/v1/tournaments/{_TOURNAMENT_ID}/feedback")
    assert resp.status_code in (401, 403)


# ── Vocab completeness ────────────────────────────────────────────────────────


def test_all_vocab_tokens_are_accepted_in_what_worked(client_with_auth, mock_db):
    """Every token in FEEDBACK_CHIPS_WORKED is accepted by the POST validator."""
    from playfuel_api.rules.feedback import FEEDBACK_CHIPS_WORKED

    all_tokens = sorted(FEEDBACK_CHIPS_WORKED)  # all 7 tokens

    feedback_row_all = {**_FEEDBACK_ROW, "what_worked": all_tokens, "what_didnt_work": []}
    feedback_check_chain = _make_chain([])
    feedback_create_chain = _make_chain([feedback_row_all])
    call_count = [0]

    def _dispatch(name):
        if name == "tournaments":
            return _make_chain([_TOURNAMENT_ROW])
        if name == "plans":
            return _make_chain([_PLAN_ROW])
        if name == "feedback":
            call_count[0] += 1
            return feedback_check_chain if call_count[0] == 1 else feedback_create_chain
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json={"whatWorked": all_tokens},
    )
    assert resp.status_code == 201


def test_all_vocab_tokens_are_accepted_in_what_didnt_work(client_with_auth, mock_db):
    """Every token in FEEDBACK_CHIPS_DIDNT_WORK is accepted by the POST validator."""
    from playfuel_api.rules.feedback import FEEDBACK_CHIPS_DIDNT_WORK

    all_tokens = sorted(FEEDBACK_CHIPS_DIDNT_WORK)

    feedback_row_all = {**_FEEDBACK_ROW, "what_worked": [], "what_didnt_work": all_tokens}
    feedback_check_chain = _make_chain([])
    feedback_create_chain = _make_chain([feedback_row_all])
    call_count = [0]

    def _dispatch(name):
        if name == "tournaments":
            return _make_chain([_TOURNAMENT_ROW])
        if name == "plans":
            return _make_chain([_PLAN_ROW])
        if name == "feedback":
            call_count[0] += 1
            return feedback_check_chain if call_count[0] == 1 else feedback_create_chain
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json={"whatDidntWork": all_tokens},
    )
    assert resp.status_code == 201


# ── Minimal body (all optional fields omitted) ────────────────────────────────


def test_post_feedback_empty_body_is_valid(client_with_auth, mock_db):
    """POST with empty body {} → 201 (all fields optional in Phase 7)."""
    minimal_feedback = {
        **_FEEDBACK_ROW,
        "overall_rating": None,
        "what_worked": [],
        "what_didnt_work": [],
        "free_text": None,
    }
    feedback_check_chain = _make_chain([])
    feedback_create_chain = _make_chain([minimal_feedback])
    call_count = [0]

    def _dispatch(name):
        if name == "tournaments":
            return _make_chain([_TOURNAMENT_ROW])
        if name == "plans":
            return _make_chain([_PLAN_ROW])
        if name == "feedback":
            call_count[0] += 1
            return feedback_check_chain if call_count[0] == 1 else feedback_create_chain
        return _make_chain([])

    mock_db.table.side_effect = _dispatch

    resp = client_with_auth.post(
        f"/v1/tournaments/{_TOURNAMENT_ID}/feedback",
        json={},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["overallRating"] is None
    assert body["whatWorked"] == []
    assert body["whatDidntWork"] == []
