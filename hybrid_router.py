"""Hybrid extraction/download routing.

Order:
1. AI-dev Render/direct media path
2. Google Cloud Run worker
3. Google Compute Engine worker
4. Existing Webshare Residential fallback

Remote workers are opt-in and disabled unless configured.
"""
import os
import re
import shutil
import tempfile
from typing import Optional

import requests

from config import settings
from extractor import download_media_file, MediaExtractionError


def _worker_enabled(url: str) -> bool:
    return bool(url and settings.HYBRID_PROXY_ENABLED and settings.HYBRID_WORKER_TOKEN)


def _safe_filename_from_headers(headers, fallback: str) -> str:
    value = headers.get("Content-Disposition", "")
    match = re.search(r'filename="?([^";]+)"?', value, re.IGNORECASE)
    return match.group(1).strip() if match else fallback


def _download_from_worker(worker_url: str, media_url: str, quality: str, platform: Optional[str]):
    temp_dir = tempfile.mkdtemp(prefix="hybrid_", dir=settings.TEMP_DIR)
    target = os.path.join(temp_dir, "worker-output.mp4")
    try:
        headers = {
            "Authorization": f"Bearer {settings.HYBRID_WORKER_TOKEN}",
            "X-Hybrid-Platform": platform or "",
        }
        response = requests.post(
            worker_url.rstrip("/") + "/internal/download",
            json={"url": media_url, "quality": quality},
            headers=headers,
            stream=True,
            timeout=(settings.HYBRID_CONNECT_TIMEOUT_SECONDS, settings.HYBRID_DOWNLOAD_TIMEOUT_SECONDS),
        )
        if response.status_code != 200:
            raise RuntimeError(f"worker returned HTTP {response.status_code}: {response.text[:500]}")
        with open(target, "wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)
        if os.path.getsize(target) <= 0:
            raise RuntimeError("worker returned an empty media file")
        filename = _safe_filename_from_headers(response.headers, "social_media_video.mp4")
        return target, filename, temp_dir
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def download_media_file_hybrid(url: str, requested_quality: Optional[str] = None, detected_platform: Optional[str] = None):
    quality = requested_quality or "1080p"
    last_error = None

    # 1. Existing downloader path, but stop before its Residential fallback.
    try:
        return download_media_file(
            url,
            quality,
            detected_platform,
            allow_residential_fallback=False,
        )
    except Exception as exc:
        last_error = exc

    # 2. Google Cloud Run worker.
    if _worker_enabled(settings.HYBRID_CLOUD_RUN_URL):
        try:
            return _download_from_worker(settings.HYBRID_CLOUD_RUN_URL, url, quality, detected_platform)
        except Exception as exc:
            last_error = exc

    # 3. Google Compute Engine worker.
    if _worker_enabled(settings.HYBRID_COMPUTE_ENGINE_URL):
        try:
            return _download_from_worker(settings.HYBRID_COMPUTE_ENGINE_URL, url, quality, detected_platform)
        except Exception as exc:
            last_error = exc

    # 4. Existing Webshare Residential fallback.
    try:
        return download_media_file(url, quality, detected_platform)
    except Exception as exc:
        last_error = exc

    if isinstance(last_error, MediaExtractionError):
        raise last_error
    raise MediaExtractionError(f"Hybrid extraction failed: {last_error}", status_code=502)
