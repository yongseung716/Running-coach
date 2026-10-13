import hashlib
import hmac
import secrets
import time
from pathlib import Path
from uuid import UUID

import httpx
import jwt
from fastapi import HTTPException, Request, Response

from .config import settings

_jwks = None


def secret():
    cfg = settings()
    if cfg.mode == "production":
        raise RuntimeError("Local auth is disabled")
    if cfg.dev_jwt_secret:
        if len(cfg.dev_jwt_secret) < 32:
            raise RuntimeError("DEV_JWT_SECRET must contain at least 32 characters")
        return cfg.dev_jwt_secret
    path: Path = cfg.data_dir / ".auth-secret"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x") as stream:
            path.chmod(0o600)
            stream.write(secrets.token_urlsafe(48))
    except FileExistsError:
        pass
    return path.read_text()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 600_000).hex()
    return f"{salt}:{digest}"


def password_matches(password, stored):
    return hmac.compare_digest(password_hash(password, stored.split(":")[0]), stored)


def issue(user_id):
    now = int(time.time())
    return jwt.encode({"sub": user_id, "aud": "authenticated", "iss": "running-coach-local",
                       "iat": now, "exp": now + 86400, "auth_time": now}, secret(), algorithm="HS256")


def decode(token):
    cfg = settings()
    try:
        if cfg.mode == "production":
            global _jwks
            if _jwks is None:
                _jwks = jwt.PyJWKClient(f"{cfg.supabase_url}/auth/v1/.well-known/jwks.json")
            # Legacy HS256 projects must migrate to asymmetric signing before deployment.
            if jwt.get_unverified_header(token).get("alg") not in {"RS256", "ES256"}:
                raise jwt.InvalidTokenError("Use asymmetric Supabase signing keys")
            key = _jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(token, key, algorithms=["RS256", "ES256"], audience="authenticated",
                                issuer=f"{cfg.supabase_url}/auth/v1", options={"require": ["exp", "sub", "iat"]})
        else:
            claims = jwt.decode(token, secret(), algorithms=["HS256"], audience="authenticated",
                                issuer="running-coach-local", options={"require": ["exp", "sub", "iat"]})
        UUID(claims["sub"])
        return claims
    except (jwt.PyJWTError, ValueError) as exc:
        raise HTTPException(401, "로그인이 필요하거나 세션이 만료되었습니다.") from exc


def current_claims(request: Request):
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.startswith("Bearer ") else request.cookies.get("rc_access")
    if not token:
        raise HTTPException(401, "로그인이 필요합니다.")
    return decode(token)


def current_user(request: Request):
    return current_claims(request)["sub"]


def set_session(response: Response, access, refresh=None, expires=3600):
    cfg = settings()
    response.set_cookie("rc_access", access, httponly=True, secure=cfg.mode == "production", samesite="lax",
                        max_age=expires, path="/")
    if refresh:
        response.set_cookie("rc_refresh", refresh, httponly=True, secure=cfg.mode == "production",
                            samesite="lax", max_age=30 * 86400, path="/")


def gotrue(path, payload=None, token=None, method="POST", admin=False):
    cfg = settings()
    key = cfg.supabase_service_role_key if admin else cfg.supabase_anon_key
    try:
        result = httpx.request(method, f"{cfg.supabase_url}/auth/v1/{path}", json=payload,
                               headers={"apikey": key, "Authorization": f"Bearer {token or key}"}, timeout=20)
        if result.is_error:
            raise HTTPException(400 if result.status_code < 500 else 503, "인증 요청이 실패했습니다. 이메일 확인과 입력을 확인하세요.")
        return result.json() if result.content else {}
    except httpx.HTTPError as exc:
        raise HTTPException(503, "인증 서버에 연결할 수 없습니다.") from exc
