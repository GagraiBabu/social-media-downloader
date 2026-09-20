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
    # Decodo Residential Proxy
    # -----------------------------------------------------------------------
    # Enable this to route yt-dlp extraction/download traffic through Decodo.
    # Keep credentials in Render Environment Variables; never commit them.
    DECODO_PROXY_ENABLED: bool = os.getenv("DECODO_PROXY_ENABLED", "false").lower() in ("true", "1", "yes")
    DECODO_HOST: str = os.getenv("DECODO_HOST", "gate.decodo.com")
    DECODO_PORT: int = int(os.getenv("DECODO_PORT", "7000"))
    DECODO_USERNAME: str = os.getenv("DECODO_USERNAME", "")
    DECODO_PASSWORD: str = os.getenv("DECODO_PASSWORD", "")
    # Optional targeting/session suffixes supported by Decodo.
    # Example: country-in or session-my-session-id
    DECODO_COUNTRY: str = os.getenv("DECODO_COUNTRY", "").strip()
    DECODO_SESSION: str = os.getenv("DECODO_SESSION", "").strip()

    @property
    def DECODO_PROXY_URL(self) -> str:
        """Build an authenticated Decodo HTTP proxy URL for yt-dlp."""
        if not self.DECODO_PROXY_ENABLED:
            return ""
        if not self.DECODO_USERNAME or not self.DECODO_PASSWORD:
            return ""
        from urllib.parse import quote
        username = self.DECODO_USERNAME
        if self.DECODO_COUNTRY:
            username += f"-country-{self.DECODO_COUNTRY.lower()}"
        if self.DECODO_SESSION:
            username += f"-session-{self.DECODO_SESSION}"
        return (
            f"http://{quote(username, safe='')}:{quote(self.DECODO_PASSWORD, safe='')}"
            f"@{self.DECODO_HOST}:{self.DECODO_PORT}"
        )

    # HTTP User-Agent for requests
    CUSTOM_USER_AGENT: str = os.getenv(
        "CUSTOM_USER_AGENT",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )


settings = Settings()
