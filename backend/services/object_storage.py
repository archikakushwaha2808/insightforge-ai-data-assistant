"""
Persistent file storage via Supabase Storage (S3-like object storage over a
simple REST API). Replaces writing uploaded/cleaned dataset files to local
disk — Render's free-tier filesystem is ephemeral and wipes local files on
every restart/redeploy, which was silently deleting uploaded datasets.
Uses httpx directly (already a dependency via the groq package) instead of
adding the full supabase-py SDK, since we only need three simple operations.
"""
import httpx

from core.config import settings

_BASE = f"{settings.SUPABASE_URL}/storage/v1/object/{settings.SUPABASE_BUCKET}"
_HEADERS = {
    "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
    "apikey": settings.SUPABASE_SERVICE_KEY,
}


def upload_bytes(key: str, data: bytes) -> None:
    resp = httpx.post(
        f"{_BASE}/{key}",
        headers={**_HEADERS, "Content-Type": "application/octet-stream"},
        content=data,
        timeout=60,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Supabase Storage upload failed ({resp.status_code}): {resp.text}")


def download_bytes(key: str) -> bytes:
    resp = httpx.get(f"{_BASE}/{key}", headers=_HEADERS, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Supabase Storage download failed ({resp.status_code}): {resp.text}")
    return resp.content


def delete_object(key: str) -> None:
    # Best-effort: if it's already gone, that's fine — don't block dataset deletion on it.
    try:
        httpx.delete(f"{_BASE}/{key}", headers=_HEADERS, timeout=30)
    except Exception:
        pass