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

    BACKEND_URL = os.getenv(
        "BACKEND_URL",
        ""
    )

    AI_MODEL = os.getenv(
        "AI_MODEL",
        "gpt-5.6"
    )


settings = Settings()
