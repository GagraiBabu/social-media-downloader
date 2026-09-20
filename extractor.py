"""
Media extraction engine powered by yt-dlp.
Provides real metadata inspection, format resolution, and safe file downloading
with strict resource limits, timeouts, and error handling.
"""

import os
import glob
import shutil
import tempfile
from typing import Dict, Any, List, Optional, Tuple
import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError, UnsupportedError

from config import settings
from security import sanitize_filename


class MediaExtractionError(Exception):
    """Base exception for media extraction errors with HTTP status code mappings."""
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _build_format_selector(requested_quality: Optional[str] = None) -> str:
    """
    Constructs the yt-dlp format selector string.
    Rule:
    - Default quality is 1080p when available.
    - If 1080p is unavailable, automatically select the best available quality below it.
    - Do NOT upscale lower resolution to 1080p.
    - If user requests specific quality (e.g. "720p", "480p", "360p", "audio_only", or format_id):
      adhere strictly to request.
    - Prefer already compatible formats (mp4/m4a) to avoid server-side transcoding.
    """
    if not requested_quality or requested_quality.lower() in ("default", "1080p", "1080"):
        # Select best video up to 1080p combined with best audio, or best pre-merged <= 1080p
        return (
            "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[height<=1080]+bestaudio/"
            "best[height<=1080][ext=mp4]/"
            "best[height<=1080]/"
            "best"
        )
    
    q = requested_quality.lower().strip()
    if q in ("audio_only", "audio", "mp3", "m4a"):
        return "bestaudio[ext=m4a]/bestaudio/best"

    if q in ("best", "highest", "max"):
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

    # Match numeric height like "720p" -> 720, "480p" -> 480, "360p" -> 360
    digits = "".join(filter(str.isdigit, q))
    if digits:
        height = int(digits)
        return (
            f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
            f"bestvideo[height<={height}]+bestaudio/"
            f"best[height<={height}][ext=mp4]/"
            f"best[height<={height}]/"
            f"best"
        )

    # Specific format ID passed directly
    return requested_quality


def _get_base_ydl_opts() -> Dict[str, Any]:
    """Base yt-dlp options ensuring safety, non-interactive execution, and resource limits."""
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nocheckcertificate": False,
        "user_agent": settings.CUSTOM_USER_AGENT,
        # Route yt-dlp HTTP/HTTPS traffic through Decodo when enabled.
        # The proxy URL is built from Render environment variables and is never returned to clients.
        **({"proxy": settings.DECODO_PROXY_URL} if settings.DECODO_PROXY_URL else {}),
        "socket_timeout": settings.INFO_TIMEOUT_SECONDS,
        "max_filesize": settings.MAX_FILE_SIZE_BYTES,
        "prefer_ffmpeg": True,
        # Avoid downloading entire playlists when a playlist URL is provided
        "extract_flat": False,
        # Ignore external configuration files
        "ignoreerrors": False,
        "no_color": True,
        "retries": settings.YTDLP_RETRIES,
        "fragment_retries": settings.YTDLP_FRAGMENT_RETRIES,
        "sleep_interval_requests": settings.YTDLP_SLEEP_REQUESTS,
        "concurrent_fragment_downloads": 1,
        "continuedl": True,
        "overwrites": True,
    }


def _classify_ytdlp_error(error: Exception) -> MediaExtractionError:
    """Classifies yt-dlp errors into user-friendly messages and appropriate HTTP status codes."""
    err_str = str(error).lower()

    if "private video" in err_str or "this video is private" in err_str:
        return MediaExtractionError(
            "This video is private. The content owner has restricted access.",
            status_code=403
        )

    if "login required" in err_str or "sign in" in err_str or "account required" in err_str:
        return MediaExtractionError(
            "This content requires account authentication/login, which is not supported.",
            status_code=403
        )

    if "copyright" in err_str or "blocked" in err_str or "dmca" in err_str:
        return MediaExtractionError(
            "This video is unavailable due to copyright or geographic restrictions.",
            status_code=403
        )

    if "video unavailable" in err_str or "not found" in err_str or "deleted" in err_str or "404" in err_str:
        return MediaExtractionError(
            "The requested video was not found or has been removed from the platform.",
            status_code=404
        )

    if "file is larger than" in err_str or "max_filesize" in err_str:
        return MediaExtractionError(
            f"The video exceeds the maximum file size limit of {settings.MAX_FILE_SIZE_MB}MB.",
            status_code=413
        )

    if "timed out" in err_str or "timeout" in err_str:
        return MediaExtractionError(
            "Connection timed out while connecting to the media platform.",
            status_code=504
        )

    if isinstance(error, UnsupportedError) or "unsupported url" in err_str:
        return MediaExtractionError(
            "The provided URL is not supported by the extraction engine.",
            status_code=422
        )

    # General extractor or platform restriction error
    clean_msg = str(error).split("ERROR:")[-1].strip()
    return MediaExtractionError(
        f"Extraction failed: {clean_msg}",
        status_code=422
    )


def extract_media_info(url: str, detected_platform: Optional[str] = None) -> Dict[str, Any]:
    """
    Extracts video metadata without downloading the media.
    
    Returns structured dictionary with:
    - title, thumbnail, duration, uploader, platform, available_formats
    """
    opts = _get_base_ydl_opts()
    opts["socket_timeout"] = settings.INFO_TIMEOUT_SECONDS

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as e:
        raise _classify_ytdlp_error(e)

    if not info:
        raise MediaExtractionError("Unable to extract video information.", status_code=404)

    # Handle playlist wrapper if returned
    if "entries" in info:
        entries = [e for e in info.get("entries", []) if e]
        if not entries:
            raise MediaExtractionError("No playable media found at this URL.", status_code=404)
        info = entries[0]

    # Process available formats cleanly
    formats = info.get("formats", [])
    clean_formats: List[Dict[str, Any]] = []

    seen_resolutions = set()
    for fmt in formats:
        height = fmt.get("height")
        format_id = fmt.get("format_id", "")
        ext = fmt.get("ext", "")
        vcodec = fmt.get("vcodec", "none")
        acodec = fmt.get("acodec", "none")
        filesize = fmt.get("filesize") or fmt.get("filesize_approx")

        has_video = vcodec != "none" and vcodec is not None
        has_audio = acodec != "none" and acodec is not None

        # Build clean format description
        format_note = fmt.get("format_note") or ""
        resolution = f"{height}p" if height else (fmt.get("resolution") or ("audio only" if not has_video else "unknown"))

        clean_formats.append({
            "format_id": format_id,
            "ext": ext,
            "resolution": resolution,
            "height": height,
            "format_note": format_note,
            "has_video": has_video,
            "has_audio": has_audio,
            "filesize_approx_bytes": filesize,
            "vcodec": vcodec,
            "acodec": acodec,
        })

    # Available quality options (e.g., 1080p, 720p, 480p, 360p, audio_only)
    qualities_available: List[str] = []
    has_audio_stream = any(f["has_audio"] for f in clean_formats)
    if has_audio_stream:
        qualities_available.append("audio_only")

    # Collect available video resolutions in descending order
    video_heights = sorted({f["height"] for f in clean_formats if f["height"]}, reverse=True)
    for h in video_heights:
        qualities_available.append(f"{h}p")

    # Determine default selected quality: 1080p or best below 1080p
    default_quality = "1080p"
    if 1080 not in video_heights:
        sub_1080 = [h for h in video_heights if h <= 1080]
        if sub_1080:
            default_quality = f"{sub_1080[0]}p"
        elif video_heights:
            default_quality = f"{video_heights[-1]}p"

    return {
        "title": info.get("title", "Video"),
        "thumbnail": info.get("thumbnail"),
        "duration_seconds": info.get("duration"),
        "uploader": info.get("uploader") or info.get("channel"),
        "uploader_url": info.get("uploader_url"),
        "platform": detected_platform or info.get("extractor_key", "unknown").lower(),
        "default_quality": default_quality,
        "available_qualities": qualities_available,
        "raw_formats": clean_formats,
    }


def download_media_file(
    url: str,
    requested_quality: Optional[str] = None,
    detected_platform: Optional[str] = None
) -> Tuple[str, str, str]:
    """
    Downloads media to a dedicated temporary directory with safety limits.
    
    Returns:
        (filepath: str, clean_filename: str, temp_dir: str)
    
    Caller MUST clean up `temp_dir` after streaming/sending the file.
    """
    os.makedirs(settings.TEMP_DIR, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix="dl_", dir=settings.TEMP_DIR)

    format_selector = _build_format_selector(requested_quality)

    outtmpl = os.path.join(temp_dir, "%(title).100B.%(ext)s")

    opts = _get_base_ydl_opts()
    opts.update({
        "format": format_selector,
        "outtmpl": outtmpl,
        "socket_timeout": settings.DOWNLOAD_TIMEOUT_SECONDS,
        "max_filesize": settings.MAX_FILE_SIZE_BYTES,
        # Merge to mp4 or m4a if separate audio+video streams are downloaded
        "merge_output_format": "mp4",
        "postprocessors": [
            {
                "key": "FFmpegVideoRemuxer",
                "preferedformat": "mp4",
            }
        ] if (requested_quality or "").lower() not in ("audio_only", "audio", "mp3", "m4a") else [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "192",
            }
        ],
    })

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as e:
        # If download failed, clean up the temporary directory immediately
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise _classify_ytdlp_error(e)

    # Locate downloaded file in temp_dir
    downloaded_files = [
        f for f in glob.glob(os.path.join(temp_dir, "*"))
        if os.path.isfile(f) and not f.endswith(".part") and not f.endswith(".ytdl")
    ]

    if not downloaded_files:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise MediaExtractionError(
            "Download completed but output media file was not generated.",
            status_code=500
        )

    filepath = downloaded_files[0]

    # Verify file size constraint
    filesize = os.path.getsize(filepath)
    if filesize > settings.MAX_FILE_SIZE_BYTES:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise MediaExtractionError(
            f"Downloaded file size ({filesize // (1024*1024)}MB) exceeded maximum limit of {settings.MAX_FILE_SIZE_MB}MB.",
            status_code=413
        )

    ext = os.path.splitext(filepath)[1].lstrip(".") or "mp4"
    raw_title = info.get("title", "social_media_video") if isinstance(info, dict) else "social_media_video"
    clean_filename = f"{sanitize_filename(raw_title)}.{ext}"

    return filepath, clean_filename, temp_dir
