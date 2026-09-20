import base64
import requests

from .config import settings


class GitHubTools:
    def __init__(self):
        self.owner = settings.GITHUB_OWNER
        self.repo = settings.GITHUB_REPO
        self.branch = settings.GITHUB_BRANCH
        self.base_url = f"https://api.github.com/repos/{self.owner}/{self.repo}"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if settings.GITHUB_TOKEN:
            self.headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"

    def _check_repo_config(self):
        if not self.owner:
            raise RuntimeError("GITHUB_OWNER is not configured")
        if not self.repo:
            raise RuntimeError("GITHUB_REPO is not configured")
        if settings.GITHUB_BRANCH == "main":
            raise RuntimeError("AI agent is not allowed to modify main")

    def _check_read_config(self):
        self._check_repo_config()

    def _check_write_config(self):
        self._check_repo_config()
        if not settings.GITHUB_TOKEN:
            raise RuntimeError("GITHUB_TOKEN is not configured; a token with repository Contents write permission is required to apply changes")

    @staticmethod
    def _raise_github_error(response, operation):
        if response.status_code == 401:
            raise RuntimeError(
                f"GitHub authentication failed during {operation}. "
                "The GITHUB_TOKEN is invalid, expired, or revoked."
            )
        if response.status_code == 403:
            raise RuntimeError(
                f"GitHub permission denied during {operation} (HTTP 403). "
                "The Render GITHUB_TOKEN does not have access to this repository or lacks "
                "Contents: Read and write permission. Update the token permissions for "
                "GagraiBabu/social-media-downloader, then replace GITHUB_TOKEN in Render."
            )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"GitHub API error during {operation}: HTTP {response.status_code}"
            ) from exc

    def get_repository(self):
        self._check_read_config()
        response = requests.get(self.base_url, headers=self.headers, timeout=20)
        self._raise_github_error(response, "repository access")
        return response.json()

    def list_files(self, path=""):
        self._check_read_config()
        response = requests.get(
            f"{self.base_url}/contents/{path}",
            headers=self.headers,
            params={"ref": self.branch},
            timeout=20,
        )
        self._raise_github_error(response, "repository file listing")
        return response.json()

    def read_file(self, path):
        self._check_read_config()
        if not path or path.startswith("/") or ".." in path.split("/"):
            raise ValueError("Unsafe repository path")
        response = requests.get(
            f"{self.base_url}/contents/{path}",
            headers=self.headers,
            params={"ref": self.branch},
            timeout=20,
        )
        self._raise_github_error(response, f"reading {path}")
        data = response.json()
        if data.get("type") != "file":
            raise RuntimeError(f"{path} is not a file")
        content = base64.b64decode(data.get("content", "")).decode("utf-8")
        return {"path": data.get("path"), "sha": data.get("sha"), "content": content}

    def update_file(self, path, content, sha, message):
        self._check_write_config()
        if not path or path.startswith("/") or ".." in path.split("/"):
            raise ValueError("Unsafe repository path")
        response = requests.put(
            f"{self.base_url}/contents/{path}",
            headers=self.headers,
            json={
                "message": message,
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "sha": sha,
                "branch": self.branch,
            },
            timeout=30,
        )
        self._raise_github_error(response, f"updating {path}")
        data = response.json()
        commit = data.get("commit") or {}
        return {
            "commit_sha": commit.get("sha"),
            "content_sha": (data.get("content") or {}).get("sha"),
            "path": path,
        }


github = GitHubTools()
