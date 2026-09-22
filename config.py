""" 
Configuration settings for Social Media Video Downloader backend.
Uses environment variables with safe production defaults for Render deployment.
"""

import os
from typing import List


class Settings:
    # Project Identity
    APP_NAME: str = "Social Media Video Downloader API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1")

    # Networking & Port (Render supplies $PORT dynamically)
    PORT: int = int(os.getenv("PORT", "10000"))
    HOST: str = os.getenv("HOST", "0.0.0.0")

    # CORS origins
    ALLOWED_ORIGINS_RAW: str = os.getenv("ALLOWED_ORIGINS", "*")
    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        if self.ALLOWED_ORIGINS_RAW == "*":
            return ["*"]
        return [origin.strip() for origin in self.ALLOWED_ORIGINS_RAW.split(",") if origin.strip()]

    # Resource Limits
    MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "100"))
    MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024

    # Timeouts in seconds
    INFO_TIMEOUT_SECONDS: int = int(os.getenv("INFO_TIMEOUT_SECONDS", "30"))
    DOWNLOAD_TIMEOUT_SECONDS: int = int(os.getenv("DOWNLOAD_TIMEOUT_SECONDS", "180"))
    MAX_CONCURRENT_JOBS: int = max(1, int(os.getenv("MAX_CONCURRENT_JOBS", "1")))
    # Keep proxy retries conservative because every retry can consume residential bandwidth.
    YTDLP_RETRIES: int = max(0, int(os.getenv("YTDLP_RETRIES", "2")))
    YTDLP_FRAGMENT_RETRIES: int = max(0, int(os.getenv("YTDLP_FRAGMENT_RETRIES", "1")))
    YTDLP_SLEEP_REQUESTS: float = max(0.0, float(os.getenv("YTDLP_SLEEP_REQUESTS", "0")))

    # Temporary directory for file downloads
    TEMP_DIR: str = os.getenv("TEMP_DIR", "/tmp/social_media_downloader")

    # Webshare Residential Proxy
    # Credentials stay in Render Environment Variables and are never returned to clients.
    WEBSHARE_PROXY_ENABLED: bool = os.getenv("WEBSHARE_PROXY_ENABLED", "true").lower() in ("true", "1", "yes")
    WEBSHARE_PROXY_URL_RAW: str = os.getenv("WEBSHARE_PROXY_URL", "").strip()
    WEBSHARE_HOST: str = os.getenv("WEBSHARE_HOST", os.getenv("WEBSHARE_PROXY_HOST", "p.webshare.io")).strip()
    WEBSHARE_PORT: int = int(os.getenv("WEBSHARE_PORT", os.getenv("WEBSHARE_PROXY_PORT", "80")))
    WEBSHARE_USERNAME: str = os.getenv("WEBSHARE_USERNAME", os.getenv("WEBSHARE_PROXY_USERNAME", "")).strip()
    WEBSHARE_PASSWORD: str = os.getenv("WEBSHARE_PASSWORD", os.getenv("WEBSHARE_PROXY_PASSWORD", ""))
    WEBSHARE_COUNTRY: str = os.getenv("WEBSHARE_COUNTRY", "").strip().lower()
    WEBSHARE_SESSION: str = os.getenv("WEBSHARE_SESSION", "").strip()
    WEBSHARE_ROTATE: bool = os.getenv("WEBSHARE_ROTATE", "true").lower() in ("true", "1", "yes")
    # When false, use Webshare for page/metadata extraction but attempt the actual
    # media transfer directly first. If direct media access fails, the downloader
    # automatically falls back to Webshare so reliability is preserved.
    WEBSHARE_PROXY_MEDIA: bool = os.getenv("WEBSHARE_PROXY_MEDIA", "false").lower() in ("true", "1", "yes")

    @property
    def WEBSHARE_PROXY_URL(self) -> str:
        """Return the exact Webshare endpoint configured by the deployment."""
        if not self.WEBSHARE_PROXY_ENABLED:
            return ""

        # If the user supplied Webshare's complete Endpoint Generator URL,
        # use it exactly as provided. This preserves provider-generated
        # routing/session parameters.
        if self.WEBSHARE_PROXY_URL_RAW:
            return self.WEBSHARE_PROXY_URL_RAW

        # Otherwise build the standard authenticated endpoint from credentials.
        if self.WEBSHARE_USERNAME and self.WEBSHARE_PASSWORD:
            from urllib.parse import quote

            username = quote(self.WEBSHARE_USERNAME, safe="")
            password = quote(self.WEBSHARE_PASSWORD, safe="")
            host = self.WEBSHARE_HOST or "p.webshare.io"
            port = self.WEBSHARE_PORT or 80
            return f"http://{username}:{password}@{host}:{port}"

        return ""

    @property
    def WEBSHARE_PROXY_URL_BUILT(self) -> str:
        """Backward-compatible alias for the Webshare proxy URL."""
        return self.WEBSHARE_PROXY_URL

    CUSTOM_USER_AGENT: str = os.getenv(
        "CUSTOM_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )


settings = Settings()
