import requests

from .config import settings


class RenderTools:
    def __init__(self):
        self.api_key = settings.RENDER_API_KEY
        self.service_id = settings.RENDER_SERVICE_ID

        self.base_url = "https://api.render.com/v1"

        self.headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _check_config(self):
        if not self.api_key:
            raise RuntimeError(
                "RENDER_API_KEY is not configured"
            )

        if not self.service_id:
            raise RuntimeError(
                "RENDER_SERVICE_ID is not configured"
            )

    def get_service(self):
        self._check_config()

        response = requests.get(
            f"{self.base_url}/services/{self.service_id}",
            headers=self.headers,
            timeout=20,
        )

        response.raise_for_status()
        return response.json()

    def get_deploys(self):
        self._check_config()

        response = requests.get(
            f"{self.base_url}/services/"
            f"{self.service_id}/deploys",
            headers=self.headers,
            params={"limit": 10},
            timeout=20,
        )

        response.raise_for_status()
        return response.json()

    def trigger_deploy(self):
        self._check_config()

        response = requests.post(
            f"{self.base_url}/services/"
            f"{self.service_id}/deploys",
            headers=self.headers,
            timeout=20,
        )

        response.raise_for_status()
        return response.json()


render = RenderTools()
