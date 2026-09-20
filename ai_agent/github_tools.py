import base64
import requests

from .config import settings


class GitHubTools:
    def __init__(self):
        self.owner = settings.GITHUB_OWNER
        self.repo = settings.GITHUB_REPO
        self.branch = settings.GITHUB_BRANCH

        self.base_url = (
            f"https://api.github.com/repos/"
            f"{self.owner}/{self.repo}"
        )

        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _check_config(self):
        if not settings.GITHUB_TOKEN:
            raise RuntimeError("GITHUB_TOKEN is not configured")

        if not self.owner:
            raise RuntimeError("GITHUB_OWNER is not configured")

        if not self.repo:
            raise RuntimeError("GITHUB_REPO is not configured")

    def get_repository(self):
        self._check_config()

        response = requests.get(
            self.base_url,
            headers=self.headers,
            timeout=20,
        )

        response.raise_for_status()
        return response.json()

    def list_files(self, path=""):
        self._check_config()

        url = f"{self.base_url}/contents/{path}"

        response = requests.get(
            url,
            headers=self.headers,
            params={"ref": self.branch},
            timeout=20,
        )

        response.raise_for_status()
        return response.json()

    def read_file(self, path):
        self._check_config()

        url = f"{self.base_url}/contents/{path}"

        response = requests.get(
            url,
            headers=self.headers,
            params={"ref": self.branch},
            timeout=20,
        )

        response.raise_for_status()

        data = response.json()

        if data.get("type") != "file":
            raise RuntimeError(f"{path} is not a file")

        encoded_content = data.get("content", "")
        content = base64.b64decode(
            encoded_content
        ).decode("utf-8")

        return {
            "path": data.get("path"),
            "sha": data.get("sha"),
            "content": content,
        }


github = GitHubTools()
