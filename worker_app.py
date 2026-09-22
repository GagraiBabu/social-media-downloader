"""Private worker API for Google Cloud Run / Compute Engine."""
import os
import shutil
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from config import settings
from detector import detect_platform
from extractor import download_media_file
from security import validate_url_security


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.TEMP_DIR, exist_ok=True)
    yield


app = FastAPI(
    title="Social Media Downloader Hybrid Worker",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)


class WorkerDownloadRequest(BaseModel):
    url: str = Field(..., min_length=4, max_length=2048)
    quality: str = Field(default="1080p", min_length=1, max_length=64)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "hybrid-worker", "timestamp": time.time()}


@app.post("/internal/download")
async def internal_download(
    payload: WorkerDownloadRequest,
    authorization: str | None = Header(default=None),
):
    expected = settings.HYBRID_WORKER_TOKEN
    if not expected or authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    is_safe, error_msg = validate_url_security(payload.url)
    if not is_safe:
        raise HTTPException(status_code=400, detail=error_msg)

    platform, _, normalized_url = detect_platform(payload.url)

    filepath, filename, _temp_dir = await run_in_threadpool(
        download_media_file,
        normalized_url,
        payload.quality,
        platform,
        False,
    )

    # The extractor creates a dedicated temp directory for each worker job.
    # FileResponse streams the file after this handler returns, so cleanup must
    # run as a response background task rather than in a finally block here.
    cleanup = BackgroundTask(shutil.rmtree, _temp_dir, ignore_errors=True)
    return FileResponse(
        filepath,
        filename=filename,
        media_type="video/mp4",
        background=cleanup,
    )
