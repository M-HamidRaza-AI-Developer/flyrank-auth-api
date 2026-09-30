"""Reusable auth dependency (the FastAPI equivalent of middleware)."""
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .client import new_client
from .errors import ApiError

# auto_error=False -> we return our own {"error": ...} body instead of FastAPI's.
# Using HTTPBearer is also what makes the "Authorize" padlock appear in /docs.
bearer_scheme = HTTPBearer(auto_error=False, description="Paste the access_token from /auth/login")


@dataclass
class AuthedUser:
    user: Any
    token: str


def require_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthedUser:
    # Missing header, wrong scheme (not "Bearer"), or empty token -> 401
    if credentials is None or not credentials.credentials.strip():
        raise ApiError(401, "Access token required")

    token = credentials.credentials.strip()

    # Ask Supabase to verify the token (expired / tampered / revoked -> failure)
    try:
        response = new_client().auth.get_user(token)
    except Exception:
        raise ApiError(401, "Invalid or expired token")

    if response is None or getattr(response, "user", None) is None:
        raise ApiError(401, "Invalid or expired token")

    return AuthedUser(user=response.user, token=token)
