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
    # Render Free tier gives 512MB RAM; 100MB video max prevents Out-Of-Memory crashes
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

    # -----------------------------------------------------------------------
    # Webshare Residential Proxy
    # -----------------------------------------------------------------------
    # Keep proxy credentials only in Render Environment Variables.
    WEBSHARE_PROXY_ENABLED: bool = os.getenv("WEBSHARE_PROXY_ENABLED", "false").lower() in ("true", "1", "yes")
    WEBSHARE_HOST: str = os.getenv("WEBSHARE_HOST", "p.webshare.io")
    WEBSHARE_PORT: int = int(os.getenv("WEBSHARE_PORT", "80"))
    WEBSHARE_USERNAME: str = os.getenv("WEBSHARE_USERNAME", "")
    WEBSHARE_PASSWORD: str = os.getenv("WEBSHARE_PASSWORD", "")
    WEBSHARE_COUNTRY: str = os.getenv("WEBSHARE_COUNTRY", "").strip().lower()
    WEBSHARE_SESSION: str = os.getenv("WEBSHARE_SESSION", "").strip()
    WEBSHARE_ROTATE: bool = os.getenv("WEBSHARE_ROTATE", "true").lower() in ("true", "1", "yes")

    @property
    def WEBSHARE_PROXY_URL(self) -> str:
        """Build an authenticated Webshare HTTP proxy URL for yt-dlp."""
        if not self.WEBSHARE_PROXY_ENABLED:
            return ""
        if not self.WEBSHARE_USERNAME or not self.WEBSHARE_PASSWORD:
            return ""

        from urllib.parse import quote

        # Webshare supports username parameters for country targeting,
        # sticky sessions, and rotating residential IPs.
        username = self.WEBSHARE_USERNAME
        if self.WEBSHARE_COUNTRY:
            username += f"-{self.WEBSHARE_COUNTRY}"
        if self.WEBSHARE_SESSION:
            username += f"-{self.WEBSHARE_SESSION}"
        elif self.WEBSHARE_ROTATE:
            username += "-rotate"

        return (
            f"http://{quote(username, safe='')}:{quote(self.WEBSHARE_PASSWORD, safe='')}"
            f"@{self.WEBSHARE_HOST}:{self.WEBSHARE_PORT}"
        )

    # HTTP User-Agent for requests
    CUSTOM_USER_AGENT: str = os.getenv(
        "CUSTOM_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )


settings = Settings()
