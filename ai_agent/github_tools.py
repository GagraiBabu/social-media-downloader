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

    def update_files_atomic(self, changes, message):
        """Commit multiple file changes as one Git commit."""
        self._check_write_config()
        if not isinstance(changes, list) or not changes:
            raise ValueError("At least one change is required")
        for change in changes:
            path = change.get("path")
            content = change.get("content")
            if not path or path.startswith("/") or ".." in path.split("/") or not isinstance(content, str):
                raise ValueError(f"Unsafe repository change: {path!r}")

        ref_response = requests.get(
            f"{self.base_url}/git/ref/heads/{self.branch}",
            headers=self.headers,
            timeout=20,
        )
        self._raise_github_error(ref_response, "reading branch ref")
        parent_sha = (ref_response.json().get("object") or {}).get("sha")
        if not parent_sha:
            raise RuntimeError("GitHub did not return the current branch SHA")

        commit_response = requests.get(
            f"{self.base_url}/git/commits/{parent_sha}",
            headers=self.headers,
            timeout=20,
        )
        self._raise_github_error(commit_response, "reading branch commit")
        base_tree_sha = (commit_response.json().get("tree") or {}).get("sha")
        if not base_tree_sha:
            raise RuntimeError("GitHub did not return the current tree SHA")

        tree_entries = []
        for change in changes:
            blob_response = requests.post(
                f"{self.base_url}/git/blobs",
                headers=self.headers,
                json={"content": change["content"], "encoding": "utf-8"},
                timeout=30,
            )
            self._raise_github_error(blob_response, f"creating blob for {change['path']}")
            blob_sha = (blob_response.json() or {}).get("sha")
            if not blob_sha:
                raise RuntimeError(f"GitHub did not return a blob SHA for {change['path']}")
            tree_entries.append({
                "path": change["path"],
                "mode": "100644",
                "type": "blob",
                "sha": blob_sha,
            })

        tree_response = requests.post(
            f"{self.base_url}/git/trees",
            headers=self.headers,
            json={"base_tree": base_tree_sha, "tree": tree_entries},
            timeout=30,
        )
        self._raise_github_error(tree_response, "creating atomic change tree")
        tree_sha = (tree_response.json() or {}).get("sha")
        if not tree_sha:
            raise RuntimeError("GitHub did not return the new tree SHA")

        new_commit_response = requests.post(
            f"{self.base_url}/git/commits",
            headers=self.headers,
            json={"message": message, "tree": tree_sha, "parents": [parent_sha]},
            timeout=30,
        )
        self._raise_github_error(new_commit_response, "creating atomic commit")
        new_commit_sha = (new_commit_response.json() or {}).get("sha")
        if not new_commit_sha:
            raise RuntimeError("GitHub did not return the new commit SHA")

        ref_response = requests.patch(
            f"{self.base_url}/git/refs/heads/{self.branch}",
            headers=self.headers,
            json={"sha": new_commit_sha, "force": False},
            timeout=30,
        )
        self._raise_github_error(ref_response, "updating branch ref")
        return {
            "commit_sha": new_commit_sha,
            "paths": [change["path"] for change in changes],
        }

    def find_job_commit(self, job_id):
        self._check_read_config()
        response = requests.get(
            f"{self.base_url}/commits",
            headers=self.headers,
            params={"sha": self.branch, "per_page": 30},
            timeout=20,
        )
        self._raise_github_error(response, "searching job commits")
        marker = f"[AI-JOB:{job_id}]"
        for item in response.json():
            message = ((item.get("commit") or {}).get("message") or "")
            if marker in message:
                return {
                    "commit_sha": item.get("sha"),
                    "message": message,
                    "html_url": item.get("html_url"),
                }
        return None


github = GitHubTools()
