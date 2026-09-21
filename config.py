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
    YTDLP_RETRIES: int = max(0, int(os.getenv("YTDLP_RETRIES", "3")))
    YTDLP_FRAGMENT_RETRIES: int = max(0, int(os.getenv("YTDLP_FRAGMENT_RETRIES", "3")))
    YTDLP_SLEEP_REQUESTS: float = max(0.0, float(os.getenv("YTDLP_SLEEP_REQUESTS", "0")))

    # Temporary directory for file downloads
    TEMP_DIR: str = os.getenv("TEMP_DIR", "/tmp/social_media_downloader")

    # Webshare Residential Proxy
    # Webshare is the active proxy provider. Keep credentials in Render env vars only.
    WEBSHARE_PROXY_ENABLED: bool = os.getenv("WEBSHARE_PROXY_ENABLED", "true").lower() in ("true", "1", "yes")
    WEBSHARE_PROXY_URL: str = os.getenv("WEBSHARE_PROXY_URL", "").strip()
    WEBSHARE_PROXY_HOST: str = os.getenv("WEBSHARE_PROXY_HOST", "p.webshare.io").strip()
    WEBSHARE_PROXY_PORT: int = int(os.getenv("WEBSHARE_PROXY_PORT", "80"))
    WEBSHARE_PROXY_USERNAME: str = os.getenv("WEBSHARE_PROXY_USERNAME", "").strip()
    WEBSHARE_PROXY_PASSWORD: str = os.getenv("WEBSHARE_PROXY_PASSWORD", "")
    WEBSHARE_COUNTRY: str = os.getenv("WEBSHARE_COUNTRY", "").strip().lower()
    WEBSHARE_SESSION: str = os.getenv("WEBSHARE_SESSION", "").strip()
    WEBSHARE_ROTATE: bool = os.getenv("WEBSHARE_ROTATE", "true").lower() in ("true", "1", "yes")

    @property
    def WEBSHARE_PROXY_URL_BUILT(self) -> str:
        """Build a Webshare HTTP proxy URL for yt-dlp without exposing credentials."""
        if not self.WEBSHARE_PROXY_ENABLED:
            return ""
        if self.WEBSHARE_PROXY_URL:
            return self.WEBSHARE_PROXY_URL
        if not self.WEBSHARE_PROXY_USERNAME or not self.WEBSHARE_PROXY_PASSWORD:
            return ""

        from urllib.parse import quote
        username = self.WEBSHARE_PROXY_USERNAME
        if self.WEBSHARE_COUNTRY and f"-{self.WEBSHARE_COUNTRY}" not in username.lower():
            username += f"-{self.WEBSHARE_COUNTRY}"
        if self.WEBSHARE_SESSION:
            username += f"-{self.WEBSHARE_SESSION}"
        elif self.WEBSHARE_ROTATE and "-rotate" not in username.lower():
            username += "-rotate"

        return (
            f"http://{quote(username, safe='')}:{quote(self.WEBSHARE_PROXY_PASSWORD, safe='')}"
            f"@{self.WEBSHARE_PROXY_HOST}:{self.WEBSHARE_PROXY_PORT}"
        )

    CUSTOM_USER_AGENT: str = os.getenv(
        "CUSTOM_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )


settings = Settings()
