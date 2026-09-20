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
            raise RuntimeError("RENDER_API_KEY is not configured")
        if not self.service_id:
            raise RuntimeError("RENDER_SERVICE_ID is not configured")

    def get_service(self):
        self._check_config()
        response = requests.get(
            f"{self.base_url}/services/{self.service_id}",
            headers=self.headers,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def get_service_url(self):
        service = self.get_service()

        def find_url(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key.lower() == "url" and isinstance(item, str) and ".onrender.com" in item:
                        return item.rstrip("/")
                    found = find_url(item)
                    if found:
                        return found
            elif isinstance(value, list):
                for item in value:
                    found = find_url(item)
                    if found:
                        return found
            return None

        return find_url(service)

    def get_deploys(self):
        self._check_config()
        response = requests.get(
            f"{self.base_url}/services/{self.service_id}/deploys",
            headers=self.headers,
            params={"limit": 10},
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def get_deploy(self, deploy_id):
        self._check_config()
        response = requests.get(
            f"{self.base_url}/services/{self.service_id}/deploys/{deploy_id}",
            headers=self.headers,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def trigger_deploy(self, commit_id=None):
        self._check_config()
        payload = {"commitId": commit_id} if commit_id else {}
        response = requests.post(
            f"{self.base_url}/services/{self.service_id}/deploys",
            headers=self.headers,
            json=payload,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()


render = RenderTools()
