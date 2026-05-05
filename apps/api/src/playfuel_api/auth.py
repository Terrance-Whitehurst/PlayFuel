"""Auth dependency — verify Supabase JWT and extract user_id.

Supports two signing modes during the HS256 → asymmetric cutover:

  RS256   Asymmetric path — validate via JWKS endpoint cached by kid.
  ES256   Supabase emits these by default once asymmetric keys are enabled.
          kid identifies which key to use; keys cached for 1 h (JWKS_LIFESPAN).

  HS256   Legacy path — validate with SUPABASE_JWT_SECRET env var.
          Supabase emitted these for sessions created before asymmetric keys
          were enabled. Kept here until all TestFlight sessions have cycled
          out (~1 week post-fix). See legacy removal comment below.

Algorithm is determined from the unverified JWT header — safe because
we only use alg/kid to select the right key, then do full verification.

Token contract (Supabase JWTs):
  aud:  "authenticated"
  sub:  Supabase user UUID (string)
  The sub claim is extracted and returned as a UUID.

Raises:
  HTTP 401  — no Authorization header (auto_error=False, raised by guard)
  HTTP 401  — expired or otherwise invalid token
  HTTP 401  — alg not in {HS256, RS256, ES256}
  HTTP 503  — JWKS endpoint unreachable (transient backend issue, not a token
              problem; returning 401 would trigger unnecessary iOS sign-out)
"""
from __future__ import annotations

import logging
from uuid import UUID

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientConnectionError, PyJWKClientError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from playfuel_api.settings import Settings, get_settings

logger = logging.getLogger(__name__)

# Module-level singleton — shared with db.py so FastAPI caches it once per request.
# auto_error=False so we can return 401 (not FastAPI's default 403) when the header
# is missing.
bearer_scheme = HTTPBearer(auto_error=False)

# JWKS cache TTL — 1 h matches Supabase's recommended key-rotation window.
_JWKS_LIFESPAN_SECS = 3600

# Module-level JWKS client cache keyed by supabase_url.
# PyJWKClient is thread-safe; one instance per project URL is sufficient.
# Evicted on kid-miss (key rotation signal) and rebuilt fresh.
_jwks_clients: dict[str, PyJWKClient] = {}


def _get_jwks_client(supabase_url: str) -> PyJWKClient:
    """Return (or create) a cached PyJWKClient for the given Supabase project URL.

    PyJWKClient fetches keys lazily on first use and re-fetches after
    ``lifespan`` seconds or on a kid miss. The module-level dict avoids
    creating a new HTTP connection on every request.

    Args:
        supabase_url: Base URL of the Supabase project
                      (e.g. ``https://vxiunrpjvamspeecbriu.supabase.co``).

    Returns:
        PyJWKClient configured to fetch from /auth/v1/.well-known/jwks.json.
    """
    if supabase_url not in _jwks_clients:
        jwks_uri = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
        _jwks_clients[supabase_url] = PyJWKClient(
            jwks_uri,
            cache_keys=True,
            lifespan=_JWKS_LIFESPAN_SECS,
        )
    return _jwks_clients[supabase_url]


def verify_supabase_jwt(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> UUID:
    """Verify the Supabase JWT and return the caller's user_id (sub claim).

    Algorithm dispatch (determined from unverified header):
      RS256 / ES256  → asymmetric path: verify via kid-keyed JWKS cache.
      HS256          → legacy path: verify with SUPABASE_JWT_SECRET env var.
      anything else  → 401 "Unsupported token algorithm".

    Args:
        creds:    Injected by FastAPI from the Authorization header.
        settings: App settings (provides supabase_url + supabase_jwt_secret).

    Returns:
        UUID — the Supabase user id extracted from the ``sub`` claim.

    Raises:
        HTTPException(401) if the token is expired or otherwise invalid.
        HTTPException(401) if no Bearer token is present (raised by guard).
        HTTPException(401) if alg is not in {HS256, RS256, ES256}.
        HTTPException(503) if the JWKS endpoint is unreachable (transient).
    """
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = creds.credentials

    # ── Step 1: peek at the header (signature NOT verified here) ─────────────
    # Used only to select the correct validation key. Full verification follows.
    try:
        unverified_header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    alg = unverified_header.get("alg", "")

    # ── Step 2: verify using the algorithm-appropriate key ───────────────────
    try:
        if alg in ("RS256", "ES256"):
            # Asymmetric path — key fetched from JWKS endpoint and cached by kid.
            # This is the primary path for all new Supabase sessions.
            payload = _verify_asymmetric(token, alg, settings)

        elif alg == "HS256":
            # LEGACY HS256 PATH — scheduled for removal on 2026-05-12.
            # After all TestFlight sessions have rotated to asymmetric tokens
            # (Supabase refresh-token TTL ~1 week post-fix), this branch and the
            # SUPABASE_JWT_SECRET env var can be deleted. See docs/JWKS_PR_BRIEF.md.
            payload = _verify_hs256(token, settings)

        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Unsupported token algorithm: {alg!r}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ── Step 3: extract and validate the sub claim ───────────────────────────
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing sub claim",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return UUID(sub)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token sub is not a valid UUID",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _verify_asymmetric(token: str, alg: str, settings: Settings) -> dict:
    """Verify an RS256 or ES256 token via the Supabase JWKS endpoint.

    Implements a single evict-and-retry on kid-miss so that a key rotation
    event is handled transparently on the next request.

    Args:
        token:    Raw JWT string.
        alg:      Algorithm string from the unverified header (RS256 or ES256).
        settings: App settings providing ``supabase_url``.

    Returns:
        Verified JWT payload dict.

    Raises:
        HTTPException(503) if the JWKS endpoint is unreachable.
        HTTPException(401) if the kid is not found after evict-and-retry.
        jwt.ExpiredSignatureError / jwt.InvalidTokenError propagated to caller.
    """
    kid = jwt.get_unverified_header(token).get("kid", "<unknown>")
    jwks_client = _get_jwks_client(settings.supabase_url)

    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
    except PyJWKClientConnectionError as exc:
        # JWKS endpoint unreachable — transient server-side problem.
        # Return 503, NOT 401: a 401 would trigger an unnecessary iOS sign-out.
        logger.error(
            "JWKS fetch failed for %s: %s",
            settings.supabase_url,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service temporarily unavailable",
        ) from exc
    except PyJWKClientError:
        # kid not found in cached JWKS — likely key rotation.
        # Evict the stale client and retry once with a fresh JWKS fetch.
        logger.warning(
            "JWKS kid not found for token (kid=%s) — likely key rotation, "
            "evicting cache and retrying",
            kid,
        )
        _jwks_clients.pop(settings.supabase_url, None)
        jwks_client = _get_jwks_client(settings.supabase_url)
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)
        except PyJWKClientError as exc:
            # Still not found after fresh fetch — genuine unknown key.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token signing key not recognised",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    return jwt.decode(
        token,
        signing_key.key,
        algorithms=[alg],
        audience="authenticated",
    )


def _verify_hs256(token: str, settings: Settings) -> dict:
    """Verify a legacy HS256 token using SUPABASE_JWT_SECRET.

    LEGACY HS256 PATH — scheduled for removal on 2026-05-12.
    After all TestFlight sessions have rotated to asymmetric tokens
    (Supabase refresh-token TTL ~1 week post-fix), this function and the
    SUPABASE_JWT_SECRET env var can be deleted. See docs/JWKS_PR_BRIEF.md.

    Args:
        token:    Raw JWT string.
        settings: App settings providing ``supabase_jwt_secret``.

    Returns:
        Verified JWT payload dict.

    Raises:
        HTTPException(401) if SUPABASE_JWT_SECRET is not configured.
        jwt.ExpiredSignatureError / jwt.InvalidTokenError propagated to caller.
    """
    if not settings.supabase_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="HS256 token received but SUPABASE_JWT_SECRET is not configured",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return jwt.decode(
        token,
        settings.supabase_jwt_secret,
        algorithms=["HS256"],
        audience="authenticated",
    )
