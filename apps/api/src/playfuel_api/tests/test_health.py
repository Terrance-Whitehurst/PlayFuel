"""Smoke tests for health + version endpoints.

Both endpoints require no authentication and no Supabase connection.
"""


def test_healthz_returns_200_and_rules_version(client_no_auth):
    """/healthz returns 200 with status=ok and a non-empty rules_version."""
    resp = client_no_auth.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "rules_version" in body
    assert body["rules_version"]  # non-empty string


def test_version_returns_200_with_rules_version_key(client_no_auth):
    """/v1/version returns 200 with rules_version, git_sha, and build_time keys.

    The exact values of git_sha and build_time are environment-dependent
    (env vars or live git), so we only assert key presence and non-emptiness.
    """
    resp = client_no_auth.get("/v1/version")
    assert resp.status_code == 200
    body = resp.json()
    assert "rules_version" in body, "rules_version key must be present"
    assert body["rules_version"], "rules_version must be non-empty"
    assert "git_sha" in body, "git_sha key must be present"
    assert "build_time" in body, "build_time key must be present"
