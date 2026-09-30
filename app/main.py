import os
from contextlib import asynccontextmanager
from typing import Optional

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict

load_dotenv()

from .client import SUPABASE_KEY, SUPABASE_URL, new_client  # noqa: E402
from .deps import AuthedUser, require_user  # noqa: E402
from .errors import ApiError  # noqa: E402


@asynccontextmanager
async def lifespan(_: FastAPI):
    new_client()  # fails fast if .env is missing or malformed
    print("Server running and connected to Supabase")
    yield


app = FastAPI(
    title="FlyRank Auth API",
    description="Sign up, log in, log out and protected routes powered by Supabase Auth.",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------- error handling: always return {"error": "..."} ----------
@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message})


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, __: RequestValidationError):
    return JSONResponse(status_code=400, content={"error": "Invalid or malformed request body"})


# ---------- models ----------
class Credentials(BaseModel):
    # Optional so that missing fields give our own 400 instead of FastAPI's 422
    email: Optional[str] = None
    password: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={"example": {"email": "test@example.com", "password": "password123"}}
    )


def _validate(creds: Credentials) -> tuple[str, str]:
    email = (creds.email or "").strip()
    password = creds.password or ""
    if not email or not password:
        raise ApiError(400, "Email and password are required")
    return email, password


def _iso(value) -> Optional[str]:
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)


# ---------- auth ----------
@app.post("/auth/signup", status_code=201, tags=["Auth"], summary="Create a new user account")
def signup(creds: Credentials):
    email, password = _validate(creds)
    try:
        result = new_client().auth.sign_up({"email": email, "password": password})
    except Exception as exc:
        raise ApiError(400, getattr(exc, "message", None) or str(exc))
    if result is None or result.user is None:
        raise ApiError(400, "Could not create user")
    return result.user.model_dump(mode="json")


@app.post("/auth/login", tags=["Auth"], summary="Log in and receive a JWT")
def login(creds: Credentials):
    email, password = _validate(creds)
    try:
        result = new_client().auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:
        # Debug line: shows the real reason in the server terminal
        # (e.g. "Email not confirmed"). The client still gets the generic 401.
        
        raise ApiError(401, "Invalid login credentials")
    session = result.session if result else None
    if session is None:
      
        raise ApiError(401, "Invalid login credentials")
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
        "expires_in": session.expires_in,
    }


@app.post(
    "/auth/logout",
    status_code=204,
    tags=["Auth"],
    summary="Log out (protected)",
    responses={401: {"description": "Missing, invalid or expired token"}},
)
def logout(auth: AuthedUser = Depends(require_user)):
    # supabase-py's signed-in-client sign_out() has no token argument, so we call
    # Supabase's logout endpoint directly with the caller's own token (works with the anon key).
    try:
        r = httpx.post(
            f"{SUPABASE_URL}/auth/v1/logout",
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {auth.token}"},
            timeout=10,
        )
    except httpx.HTTPError:
        raise ApiError(502, "Could not reach Supabase to log out")
    if r.status_code not in (200, 204):
        raise ApiError(502, "Supabase rejected the logout request")
    return Response(status_code=204)


# ---------- public ----------
@app.get("/public/info", tags=["Public"], summary="Public info (no auth)")
def public_info():
    return {"message": "Welcome stranger! This info is public."}


# ---------- protected ----------
@app.get(
    "/protected/profile",
    tags=["Protected"],
    summary="Current user's profile",
    responses={401: {"description": "Missing, invalid or expired token"}},
)
def profile(auth: AuthedUser = Depends(require_user)):
    u = auth.user
    return {"id": str(u.id), "email": u.email, "created_at": _iso(u.created_at)}


@app.get(
    "/protected/dashboard",
    tags=["Protected"],
    summary="Example second protected route",
    responses={401: {"description": "Missing, invalid or expired token"}},
)
def dashboard(auth: AuthedUser = Depends(require_user)):
    return {"message": f"Welcome to your dashboard, {auth.user.email}!"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.getenv("PORT", 3000)), reload=True)