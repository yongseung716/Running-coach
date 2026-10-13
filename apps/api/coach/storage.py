from pathlib import Path

import httpx

from .config import settings


def checked_key(key):
    parts = key.split("/")
    if len(parts) != 2 or any(not p or p in {".", ".."} for p in parts) or "\\" in key:
        raise ValueError("Invalid storage key")
    return key


def remote(method, key, data=None):
    cfg = settings()
    checked_key(key)
    path = cfg.storage_bucket if method == "DELETE" else f"{cfg.storage_bucket}/{key}"
    response = httpx.request(method, f"{cfg.supabase_url}/storage/v1/object/{path}",
                             headers={"Authorization": f"Bearer {cfg.supabase_service_role_key}",
                                      "apikey": cfg.supabase_service_role_key,
                                      "Content-Type": "application/json" if method == "DELETE" else "application/gpx+xml"},
                             content=data, json={"prefixes": [key]} if method == "DELETE" else None, timeout=30)
    if method == "DELETE" and response.status_code == 404:
        return response
    response.raise_for_status()
    return response


def location(key) -> Path:
    return settings().data_dir / "files" / checked_key(key)


def put(key, data):
    if settings().mode == "production":
        remote("POST", key, data)
    else:
        path = location(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


def get(key):
    return remote("GET", key).content if settings().mode == "production" else location(key).read_bytes()


def delete(key):
    if settings().mode == "production":
        remote("DELETE", key)
    else:
        location(key).unlink(missing_ok=True)
