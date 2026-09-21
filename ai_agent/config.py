import os


class Settings:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    AI_ADMIN_KEY = os.getenv("AI_ADMIN_KEY", "")
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
    GITHUB_OWNER = os.getenv("GITHUB_OWNER", "")
    GITHUB_REPO = os.getenv("GITHUB_REPO", "")
    GITHUB_BRANCH = os.getenv("GITHUB_BRANCH", "ai-agent-dev")
    RENDER_API_KEY = os.getenv("RENDER_API_KEY", "")
    RENDER_SERVICE_ID = os.getenv("RENDER_SERVICE_ID", "")
    BACKEND_URL = os.getenv("BACKEND_URL", "")
    AI_AGENT_TEST_URL = os.getenv("AI_AGENT_TEST_URL", "")
    AI_TEST_VIDEO_URL = os.getenv("AI_TEST_VIDEO_URL", "https://www.youtube.com/watch?v=BaW_jenozKc")
    AI_TEST_DOWNLOAD_QUALITY = os.getenv("AI_TEST_DOWNLOAD_QUALITY", "1080p")
    AI_AGENT_DEEP_TESTS = os.getenv("AI_AGENT_DEEP_TESTS", "true").lower() in ("true", "1", "yes")
    AI_AGENT_MAX_REPAIR_ATTEMPTS = max(1, min(5, int(os.getenv("AI_AGENT_MAX_REPAIR_ATTEMPTS", "5"))))
    AI_AGENT_HEALTH_TIMEOUT_SECONDS = max(5, int(os.getenv("AI_AGENT_HEALTH_TIMEOUT_SECONDS", "30")))
    AI_AGENT_INFO_TEST_TIMEOUT_SECONDS = max(15, int(os.getenv("AI_AGENT_INFO_TEST_TIMEOUT_SECONDS", "60")))
    AI_AGENT_DOWNLOAD_TEST_TIMEOUT_SECONDS = max(30, int(os.getenv("AI_AGENT_DOWNLOAD_TEST_TIMEOUT_SECONDS", "240")))
    AI_AGENT_DOWNLOAD_SAMPLE_BYTES = max(64 * 1024, int(os.getenv("AI_AGENT_DOWNLOAD_SAMPLE_BYTES", str(256 * 1024))))
    AI_AGENT_DEPLOY_TIMEOUT_SECONDS = max(60, int(os.getenv("AI_AGENT_DEPLOY_TIMEOUT_SECONDS", "240")))
    AI_AGENT_DEPLOY_POLL_SECONDS = max(3, int(os.getenv("AI_AGENT_DEPLOY_POLL_SECONDS", "8")))
    AI_AGENT_TRIGGER_DEPLOY = os.getenv("AI_AGENT_TRIGGER_DEPLOY", "true").lower() in ("true", "1", "yes")
    AI_MODEL = os.getenv("AI_MODEL", "gpt-5.6")


settings = Settings()
