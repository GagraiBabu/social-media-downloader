import requests

from .config import settings


class APITester:
    def __init__(self):
        self.base_url = settings.BACKEND_URL.rstrip("/")

    def _check_config(self):
        if not self.base_url:
            raise RuntimeError(
                "BACKEND_URL is not configured"
            )

    def health_check(self):
        self._check_config()

        response = requests.get(
            f"{self.base_url}/health",
            timeout=30,
        )

        return {
            "url": f"{self.base_url}/health",
            "status_code": response.status_code,
            "ok": response.ok,
            "response": response.text[:500],
        }

    def test_endpoint(self, path):
        self._check_config()

        if not path.startswith("/"):
            path = "/" + path

        response = requests.get(
            f"{self.base_url}{path}",
            timeout=30,
        )

        return {
            "url": f"{self.base_url}{path}",
            "status_code": response.status_code,
            "ok": response.ok,
            "response": response.text[:1000],
        }


api_tester = APITester()
