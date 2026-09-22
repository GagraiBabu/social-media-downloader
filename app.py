"""
Social Media Video Downloader Backend API.
Built with FastAPI, yt-dlp, and Pydantic for high-performance, production-ready video extraction.
"""

import asyncio
import logging
import os
import shutil
import time
import mimetypes
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any

from starlette.concurrency import run_in_threadpool

from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field

from config import settings
from security import validate_url_security
from detector import detect_platform, normalize_url, PLATFORM_PATTERNS
from extractor import extract_media_info, download_media_file, MediaExtractionError
from hybrid_router import download_media_file_hybrid


logger = logging.getLogger(__name__)

# The AI routes are an optional extension. Missing or incompatible extension
# imports must not prevent the core downloader API or health check from starting.
try:
    from ai_agent.ai_routes import router as ai_router
except Exception as exc:
    ai_router = None
    logger.warning("AI Backend Doctor routes are unavailable: %s", exc)


# ---------------------------------------------------------------------------
# Application Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup temporary directory on startup
    os.makedirs(settings.TEMP_DIR, exist_ok=True)
    yield
    # Cleanup temporary directory on shutdown
    if os.path.exists(settings.TEMP_DIR):
        shutil.rmtree(settings.TEMP_DIR, ignore_errors=True)


DOWNLOAD_SEMAPHORE = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Production-ready backend API for extracting and downloading social media videos "
        "from YouTube, Instagram, Facebook, TikTok, X (Twitter), Reddit, Pinterest, "
        "Dailymotion, Moj, Snapchat, and LinkedIn."
    ),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# AI Backend Doctor routes, when the optional extension is available.
if ai_router is not None:
    app.include_router(ai_router)

# ---------------------------------------------------------------------------
# CORS Middleware
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic Request & Response Schemas
# ---------------------------------------------------------------------------
class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    version: str
    timestamp: float
    max_file_size_mb: int
    proxy_enabled: bool = False


class DetectRequest(BaseModel):
    url: str = Field(..., description="The social media URL to inspect", min_length=4, max_length=2048)


class DetectResponse(BaseModel):
    url: str
    detected_platform: Optional[str]
    is_valid_url: bool
    is_supported_platform: bool
    normalized_url: str


class InfoRequest(BaseModel):
    url: str = Field(..., description="The media URL to inspect", min_length=4, max_length=2048)


class FormatItem(BaseModel):
    format_id: str
    ext: str
    resolution: str
    height: Optional[int] = None
    format_note: Optional[str] = None
    has_video: bool
    has_audio: bool
    filesize_approx_bytes: Optional[int] = None


class VideoInfoResponse(BaseModel):
    title: str
    thumbnail: Optional[str] = None
    duration_seconds: Optional[float] = None
    uploader: Optional[str] = None
    uploader_url: Optional[str] = None
    platform: str
    default_quality: str
    available_qualities: List[str]
    raw_formats: List[Dict[str, Any]]


class DownloadRequest(BaseModel):
    url: str = Field(..., description="The media URL to download", min_length=4, max_length=2048)
    quality: Optional[str] = Field(
        default="1080p",
        description="Target video quality (e.g., '1080p', '720p', '480p', '360p', 'audio_only', or specific format_id)"
    )


# ---------------------------------------------------------------------------
# Global Exception Handlers
# ---------------------------------------------------------------------------
@app.exception_handler(MediaExtractionError)
async def media_extraction_exception_handler(request: Request, exc: MediaExtractionError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "error_type": "extraction_error"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    # Return safe message without exposing internal stack traces
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected server error occurred while processing the request.",
            "error_type": "internal_error",
        },
    )


# ---------------------------------------------------------------------------
# Background Cleanup Helper
# ---------------------------------------------------------------------------
def _cleanup_temp_directory(directory_path: str):
    """Safely deletes an isolated request temp folder after download transmission completes."""
    try:
        if os.path.exists(directory_path):
            shutil.rmtree(directory_path, ignore_errors=True)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------
@app.get("/", summary="Root Overview", tags=["General"])
async def root():
    """Returns quick API info and links to interactive documentation."""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
        "supported_platforms": list(PLATFORM_PATTERNS.keys()),
        "webshare_proxy_enabled": bool(settings.WEBSHARE_PROXY_URL),
    }


@app.get("/health", response_model=HealthResponse, summary="Service Health Check", tags=["General"])
async def health_check():
    """
    Health check endpoint for Render and uptime monitoring.
    Returns HTTP 200 with server status.
    """
    return HealthResponse(
        status="ok",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        timestamp=time.time(),
        max_file_size_mb=settings.MAX_FILE_SIZE_MB,
        proxy_enabled=bool(settings.WEBSHARE_PROXY_URL),
    )


@app.post("/api/detect", response_model=DetectResponse, summary="Detect Platform & Normalize URL", tags=["Detection"])
async def detect_url_endpoint(payload: DetectRequest):
    """
    Validates the URL, protects against SSRF, identifies the social media platform,
    and returns the normalized URL stripped of tracking parameters.
    """
    is_safe, error_msg = validate_url_security(payload.url)
    if not is_safe:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    platform, is_valid, norm_url = detect_platform(payload.url)

    return DetectResponse(
        url=payload.url,
        detected_platform=platform,
        is_valid_url=is_valid,
        is_supported_platform=platform is not None,
        normalized_url=norm_url,
    )


@app.post("/api/info", response_model=VideoInfoResponse, summary="Extract Video Metadata", tags=["Extractor"])
async def get_video_info_endpoint(payload: InfoRequest):
    """
    Extracts comprehensive metadata, available resolutions, and stream attributes
    for a media URL without performing a full download.
    """
    is_safe, error_msg = validate_url_security(payload.url)
    if not is_safe:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    platform, _, norm_url = detect_platform(payload.url)

    # Perform real metadata extraction
    async with DOWNLOAD_SEMAPHORE:
        info = await run_in_threadpool(extract_media_info, norm_url, platform)

    return VideoInfoResponse(
        title=info["title"],
        thumbnail=info.get("thumbnail"),
        duration_seconds=info.get("duration_seconds"),
        uploader=info.get("uploader"),
        uploader_url=info.get("uploader_url"),
        platform=info.get("platform", platform or "unknown"),
        default_quality=info.get("default_quality", "1080p"),
        available_qualities=info.get("available_qualities", []),
        raw_formats=info.get("raw_formats", []),
    )


@app.post("/api/download", summary="Download Media File", tags=["Downloader"])
async def download_video_endpoint(payload: DownloadRequest, background_tasks: BackgroundTasks):
    """
    Extracts and downloads media adhering to:
    - Default quality: 1080p when available.
    - If 1080p unavailable: best available quality below it (never upscaled).
    - Other requested quality if provided ('720p', '480p', '360p', 'audio_only', format_id).
    - Isolated temporary file storage.
    - Background task cleanup of temporary files upon response completion.
    """
    is_safe, error_msg = validate_url_security(payload.url)
    if not is_safe:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg)

    platform, _, norm_url = detect_platform(payload.url)

    async with DOWNLOAD_SEMAPHORE:
        download_fn = download_media_file_hybrid if settings.HYBRID_PROXY_ENABLED else download_media_file
        filepath, clean_filename, temp_dir = await run_in_threadpool(
            download_fn,
            norm_url,
            payload.quality or "1080p",
            platform,
        )

    # Register background cleanup task to delete temporary files once the file has been streamed
    background_tasks.add_task(_cleanup_temp_directory, temp_dir)

    # Determine media type from the actual output extension.
    ext = os.path.splitext(filepath)[1].lower()
    media_type = mimetypes.types_map.get(ext)
    if not media_type:
        media_type = "audio/mp4" if ext in (".m4a", ".aac") else ("audio/mpeg" if ext == ".mp3" else "application/octet-stream")

    # Let Starlette generate Content-Disposition. Supplying our own header with a
    # Unicode filename causes a latin-1 encoding failure in Starlette/Uvicorn.
    return FileResponse(
        path=filepath,
        filename=clean_filename,
        media_type=media_type,
        background=background_tasks,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


# ---------------------------------------------------------------------------
# Direct Execution Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips="*",
        timeout_keep_alive=5,
        limit_concurrency=settings.MAX_CONCURRENT_JOBS + 8,
        timeout_graceful_shutdown=15,
    )
