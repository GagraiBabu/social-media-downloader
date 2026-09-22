"""
Media extraction engine powered by yt-dlp.
Provides real metadata inspection, format resolution, and safe file downloading
with strict resource limits, timeouts, and error handling.
"""

import os
import glob
import shutil
import tempfile
import time
from collections import OrderedDict
from urllib.parse import urlparse
import requests
from typing import Dict, Any, List, Optional, Tuple
import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError, UnsupportedError

from config import settings
from security import sanitize_filename


# Short-lived in-process metadata cache. The frontend commonly calls /api/info
# immediately before /api/download for the same URL. Reusing the extracted
# format info avoids a second residential-proxy page/API extraction request.
# Media URLs remain short-lived; download fallback can re-extract when needed.
_INFO_CACHE_TTL_SECONDS = 60
_INFO_CACHE_MAX_ITEMS = 32
_INFO_CACHE = OrderedDict()
_SHARE_URL_CACHE = {}


def _info_cache_key(url: str, detected_platform: Optional[str]) -> str:
    return f"{(detected_platform or '').lower()}::{url}"


def _get_cached_info(url: str, detected_platform: Optional[str]):
    key = _info_cache_key(url, detected_platform)
    item = _INFO_CACHE.get(key)
    if not item:
        return None
    created_at, info = item
    if time.monotonic() - created_at > _INFO_CACHE_TTL_SECONDS:
        _INFO_CACHE.pop(key, None)
        return None
    _INFO_CACHE.move_to_end(key)
    return info


def _cache_info(url: str, detected_platform: Optional[str], info):
    key = _info_cache_key(url, detected_platform)
    _INFO_CACHE[key] = (time.monotonic(), info)
    _INFO_CACHE.move_to_end(key)
    while len(_INFO_CACHE) > _INFO_CACHE_MAX_ITEMS:
        _INFO_CACHE.popitem(last=False)


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
        # Use yt-dlp's documented video-containing selector. The previous
        # ext-specific chain could end up selecting an audio-only result on
        # YouTube when the preferred MP4/M4A pair was unavailable.
        # bv* guarantees the selected first format contains video; ba supplies
        # audio when needed, with a combined video+audio fallback.
        return "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b"
    
    q = requested_quality.lower().strip()
    if q in ("audio_only", "audio", "mp3", "m4a"):
        return "bestaudio[ext=m4a]/bestaudio/best"

    if q in ("best", "highest", "max"):
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

    # Match numeric height like "720p" -> 720, "480p" -> 480, "360p" -> 360
    digits = "".join(filter(str.isdigit, q))
    if digits:
        height = int(digits)
        return f"bv*[height<={height}]+ba/b[height<={height}]/bv*+ba/b"

    # Specific format ID passed directly
    return requested_quality


def _get_base_ydl_opts(is_youtube: bool = False, platform: Optional[str] = None) -> Dict[str, Any]:
    """Base yt-dlp options ensuring safety, non-interactive execution, and resource limits."""
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nocheckcertificate": False,
        "user_agent": settings.CUSTOM_USER_AGENT,
        # Route yt-dlp HTTP/HTTPS traffic through Webshare when enabled.
        # The proxy URL is built from Render environment variables and is never returned to clients.
        **({"proxy": settings.WEBSHARE_PROXY_URL_BUILT} if settings.WEBSHARE_PROXY_URL_BUILT else {}),
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
        "concurrent_fragment_downloads": 4,
        "continuedl": True,
        "overwrites": True,
    }

    # Facebook and Instagram increasingly apply browser/TLS fingerprinting.
    # Use yt-dlp curl_cffi browser impersonation only for those platforms.
    if (platform or "").lower() in {"facebook", "instagram"}:
        opts["impersonate"] = os.getenv("YTDLP_SOCIAL_IMPERSONATE", "chrome")

    # Do not impose an artificial 0.75s delay on every YouTube request.
    # The delay is configurable through YTDLP_SLEEP_REQUESTS; default is 0
    # so normal downloads start immediately. YouTube rate-limit protection
    # should be handled by the configured retry/sleep policy rather than by
    # slowing every request unconditionally.
    if is_youtube:
        opts["sleep_interval_requests"] = settings.YTDLP_SLEEP_REQUESTS

    return opts


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

    if (
        "tunnel connection failed: 400 bad request" in err_str
        or "client_connect_invalid_params" in err_str
        or "unable to connect to proxy" in err_str
    ):
        return MediaExtractionError(
            "Webshare rejected the proxy connection parameters (HTTP 400). "
            "The backend now uses the Webshare Endpoint Generator credentials exactly as configured. "
            "Check that WEBSHARE_PROXY_URL contains the exact Endpoint Generator output, "
            "or that WEBSHARE_USERNAME/WEBSHARE_PASSWORD match it exactly.",
            status_code=502
        )

    if "429" in err_str or "too many requests" in err_str:
        return MediaExtractionError(
            "The platform is rate-limiting the current network path (HTTP 429). Webshare proxy mode is active; please retry after the temporary rate limit clears.",
            status_code=429
        )

    # General extractor or platform restriction error
    clean_msg = str(error).split("ERROR:")[-1].strip()
    return MediaExtractionError(
        f"Extraction failed: {clean_msg}",
        status_code=422
    )


def _resolve_facebook_share_url(url: str, opts: Dict[str, Any]) -> str:
    """Resolve Facebook share links while minimizing residential-proxy traffic."""
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path.lower()
        if not host.endswith("facebook.com") or not path.startswith("/share/"):
            return url

        cached = _SHARE_URL_CACHE.get(url)
        if cached and time.monotonic() - cached[0] <= _INFO_CACHE_TTL_SECONDS:
            return cached[1]

        base_kwargs = {
            "headers": {"User-Agent": settings.CUSTOM_USER_AGENT},
            "timeout": min(settings.INFO_TIMEOUT_SECONDS, 15),
            "allow_redirects": True,
        }

        # A share-link redirect is small and often works directly. Try direct
        # first so resolving the URL does not consume residential bandwidth.
        try:
            response = requests.get(url, **base_kwargs)
            final_url = response.url or url
            final = urlparse(final_url)
            final_host = final.netloc.lower()
            if final_host.endswith("facebook.com") or final_host.endswith("fb.watch"):
                _SHARE_URL_CACHE[url] = (time.monotonic(), final_url)
                return final_url
        except Exception:
            pass

        # Only use Webshare for the redirect if direct resolution failed.
        proxy = opts.get("proxy")
        if proxy:
            proxy_kwargs = dict(base_kwargs)
            proxy_kwargs["proxies"] = {"http": proxy, "https": proxy}
            response = requests.get(url, **proxy_kwargs)
            final_url = response.url or url
            final = urlparse(final_url)
            final_host = final.netloc.lower()
            if final_host.endswith("facebook.com") or final_host.endswith("fb.watch"):
                _SHARE_URL_CACHE[url] = (time.monotonic(), final_url)
                return final_url
    except Exception:
        pass
    return url


def _extract_info_with_social_fallback(url: str, detected_platform: Optional[str], opts: Dict[str, Any], download: bool = False):
    """Try browser impersonation first, then a plain HTTP path."""
    attempts = [dict(opts)]
    if (detected_platform or "").lower() in {"facebook", "instagram"} and opts.get("impersonate"):
        # If the configured target is unavailable, let yt-dlp choose any
        # installed curl_cffi target before falling back to plain HTTP.
        any_target = dict(opts)
        any_target["impersonate"] = True
        if any_target["impersonate"] != opts.get("impersonate"):
            attempts.append(any_target)

        fallback = dict(opts)
        fallback.pop("impersonate", None)
        attempts.append(fallback)

    last_error = None
    for attempt in attempts:
        try:
            with yt_dlp.YoutubeDL(attempt) as ydl:
                return ydl.extract_info(url, download=download)
        except Exception as exc:
            last_error = exc

    # Facebook's native extractor is currently prone to `Cannot parse data`
    # on public share/reel URLs even on recent yt-dlp builds. Try yt-dlp's
    # generic extractor as a fallback. The generic extractor can follow the
    # share redirect and read the public page's embedded media metadata
    # without invoking the failing Facebook parser again.
    if (detected_platform or "").lower() == "facebook":
        generic_opts = dict(opts)
        generic_opts.pop("impersonate", None)
        generic_opts["force_generic_extractor"] = True
        generic_opts["allowed_extractors"] = ["generic"]
        try:
            with yt_dlp.YoutubeDL(generic_opts) as ydl:
                generic_info = ydl.extract_info(url, download=download)
            if generic_info:
                return generic_info
        except Exception as exc:
            last_error = exc

        # yt-dlp's generic extractor still hands Facebook redirects back to
        # the broken native Facebook extractor. As a final public-content
        # fallback, parse direct MP4 URLs from Facebook's HTML instead.
        try:
            html_info = _extract_facebook_html_media(url, opts)
            if html_info:
                return html_info
        except Exception as exc:
            last_error = exc

    raise last_error



def _extract_facebook_html_media(url: str, opts: Dict[str, Any]):
    """Extract public Facebook video URLs directly from the rendered HTML."""
    parsed = urlparse(url)
    if not parsed.netloc.lower().endswith("facebook.com"):
        return None

    headers = {
        "User-Agent": settings.CUSTOM_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
    }
    request_kwargs = {
        "headers": headers,
        "timeout": min(settings.INFO_TIMEOUT_SECONDS, 15),
        "allow_redirects": True,
    }

    response = None
    try:
        response = requests.get(url, **request_kwargs)
        if response.status_code >= 400:
            response = None
    except Exception:
        response = None

    if response is None and opts.get("proxy"):
        try:
            proxy = opts["proxy"]
            request_kwargs["proxies"] = {"http": proxy, "https": proxy}
            response = requests.get(url, **request_kwargs)
        except Exception:
            response = None

    if response is None or not response.text:
        return None

    html = response.text
    from html import unescape
    import json
    import re
    from urllib.parse import unquote

    # Facebook frequently HTML/JSON-escapes its media URLs. Normalize the
    # common escaping layers before looking for direct MP4 sources.
    normalized = unescape(html)
    normalized = normalized.replace("\\/", "/")
    normalized = normalized.replace("\\u0025", "%").replace("\\u0026", "&")
    normalized = normalized.replace("\\u003D", "=").replace("\\u003d", "=")
    normalized = normalized.replace("\\u002F", "/").replace("\\u002f", "/")
    normalized = unquote(normalized)

    candidates = []

    # Known Facebook page-data fields.
    field_patterns = [
        r'"playable_url_quality_hd"\s*:\s*"([^"]+)"',
        r'"playable_url"\s*:\s*"([^"]+)"',
        r'"hd_src"\s*:\s*"([^"]+)"',
        r'"sd_src"\s*:\s*"([^"]+)"',
        r'"browser_native_hd_url"\s*:\s*"([^"]+)"',
        r'"browser_native_sd_url"\s*:\s*"([^"]+)"',
    ]
    for pattern in field_patterns:
        for match in re.findall(pattern, normalized):
            candidates.append(match)

    # OpenGraph can expose a direct video resource on public pages.
    meta_patterns = [
        r'<meta[^>]+property=["\\']og:video(?::secure_url|:url)?["\\'][^>]+content=["\\']([^"\\']+)["\\']',
        r'<meta[^>]+content=["\\']([^"\\']+)["\\'][^>]+property=["\\']og:video(?::secure_url|:url)?["\\']',
    ]
    for pattern in meta_patterns:
        candidates.extend(re.findall(pattern, normalized, flags=re.IGNORECASE))

    # Last-resort scan for direct Facebook CDN MP4 URLs in the page source.
    candidates.extend(re.findall(
        r'https?://[^"\'\s<>]+(?:fbcdn\.net|facebook\.com)[^"\'\s<>]+?\.mp4(?:\?[^"\'\s<>]*)?',
        normalized,
        flags=re.IGNORECASE,
    ))

    cleaned = []
    seen = set()
    for candidate in candidates:
        candidate = candidate.replace("\\\"", '"').strip()
        if candidate.startswith("http") and ".mp4" in candidate.lower() and candidate not in seen:
            seen.add(candidate)
            cleaned.append(candidate)

    if not cleaned:
        return None

    # Prefer HD-looking sources; keep the first few unique sources so the
    # normal quality selector can choose among them when Facebook exposes both.
    def _score(u):
        low = u.lower()
        return (
            2 if "hd" in low else 0,
            1 if "1080" in low or "720" in low else 0,
        )

    cleaned.sort(key=_score, reverse=True)

    title_match = re.search(
        r'<meta[^>]+property=["\\']og:title["\\'][^>]+content=["\\']([^"\\']+)["\\']',
        normalized,
        flags=re.IGNORECASE,
    )
    if not title_match:
        title_match = re.search(
            r'<title[^>]*>(.*?)</title>',
            normalized,
            flags=re.IGNORECASE | re.DOTALL,
        )
    title = unescape(title_match.group(1)).strip() if title_match else "Facebook Video"

    thumb_match = re.search(
        r'<meta[^>]+property=["\\']og:image["\\'][^>]+content=["\\']([^"\\']+)["\\']',
        normalized,
        flags=re.IGNORECASE,
    )
    thumbnail = thumb_match.group(1).strip() if thumb_match else None

    formats = []
    for index, media_url in enumerate(cleaned[:4], start=1):
        formats.append({
            "format_id": f"facebook-html-{index}",
            "url": media_url,
            "ext": "mp4",
            "height": None,
            "width": None,
            "vcodec": "unknown",
            "acodec": "unknown",
        })

    return {
        "id": re.search(r'(?:/videos/|/reel/|[?&]v=)(\d+)', response.url or url).group(1)
        if re.search(r'(?:/videos/|/reel/|[?&]v=)(\d+)', response.url or url) else None,
        "title": title,
        "thumbnail": thumbnail,
        "webpage_url": response.url or url,
        "extractor_key": "Facebook",
        "formats": formats,
        "url": cleaned[0],
        "_facebook_html_fallback": True,
    }


def extract_media_info(url: str, detected_platform: Optional[str] = None) -> Dict[str, Any]:
    """
    Extracts video metadata without downloading the media.
    
    Returns structured dictionary with:
    - title, thumbnail, duration, uploader, platform, available_formats
    """
    if (detected_platform or "").lower() == "facebook":
        url = _resolve_facebook_share_url(url, _get_base_ydl_opts(platform=detected_platform))
    is_youtube = (detected_platform or "").lower() == "youtube" or "youtube.com" in url.lower() or "youtu.be/" in url.lower()
    opts = _get_base_ydl_opts(is_youtube=is_youtube, platform=detected_platform)
    opts["socket_timeout"] = settings.INFO_TIMEOUT_SECONDS

    try:
        info = _get_cached_info(url, detected_platform)
        if info is None:
            info = _extract_info_with_social_fallback(url, detected_platform, opts, download=False)
            _cache_info(url, detected_platform, info)
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

    if (detected_platform or "").lower() == "facebook":
        url = _resolve_facebook_share_url(url, _get_base_ydl_opts(platform=detected_platform))
    is_youtube = (detected_platform or "").lower() == "youtube" or "youtube.com" in url.lower() or "youtu.be/" in url.lower()
    opts = _get_base_ydl_opts(is_youtube=is_youtube, platform=detected_platform)
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
        # First extract metadata/format URLs through Webshare. This keeps the
        # residential proxy on the protected platform request path without
        # forcing the large media payload through the proxy.
        info = _get_cached_info(url, detected_platform)
        if info is None:
            info = _extract_info_with_social_fallback(url, detected_platform, opts, download=False)
            _cache_info(url, detected_platform, info)

        downloaded_direct = False
        proxy_url = opts.get("proxy")
        if proxy_url and not settings.WEBSHARE_PROXY_MEDIA:
            # yt-dlp supports an empty proxy value for a direct connection.
            # Reuse the already-extracted info so we do not make a second
            # platform-page request through the residential proxy.
            direct_opts = dict(opts)
            direct_opts["proxy"] = ""
            try:
                with yt_dlp.YoutubeDL(direct_opts) as ydl:
                    ydl.process_ie_result(info, download=True)
                downloaded_direct = True
            except Exception:
                # Some signed/geo-restricted media URLs require the same proxy
                # used during extraction. Fall back to the reliable proxy path.
                downloaded_direct = False

        if not downloaded_direct:
            # Reuse the already-extracted info instead of calling extract_info()
            # again through Webshare. If the direct media URL needs the proxy,
            # this downloads the same selected media through Webshare without
            # repeating the platform-page/API extraction request.
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.process_ie_result(info, download=True)
            except Exception:
                # Cached signed URLs can expire. Only in that case re-extract
                # through Webshare and retry, preserving bandwidth savings for
                # the normal path.
                info = _extract_info_with_social_fallback(url, detected_platform, opts, download=False)
                _cache_info(url, detected_platform, info)
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.process_ie_result(info, download=True)
    except Exception as e:
        # If download failed, clean up the temporary directory immediately
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise _classify_ytdlp_error(e)

    # Locate downloaded file in temp_dir
    downloaded_files = [
        f for f in glob.glob(os.path.join(temp_dir, "*"))
        if os.path.isfile(f) and not f.endswith(".part") and not f.endswith(".ytdl")
    ]

    # A normal video request must never silently return an audio-only file.
    # yt-dlp documents bestvideo+bestaudio as the explicit video+audio merge path.
    wants_audio_only = (requested_quality or "").lower() in ("audio_only", "audio", "mp3", "m4a")
    if not wants_audio_only:
        video_files = [
            f for f in downloaded_files
            if os.path.splitext(f)[1].lower() in (".mp4", ".webm", ".mkv", ".mov", ".flv")
        ]
        if video_files:
            downloaded_files = video_files
        else:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise MediaExtractionError(
                "Video download completed without a video file. The selected format was audio-only.",
                status_code=502
            )

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
