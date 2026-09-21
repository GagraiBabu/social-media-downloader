import os
import re
import requests

from .config import settings


VIDEO_EXTENSIONS = (".mp4", ".webm", ".mkv", ".mov", ".flv", ".m4v")
AUDIO_EXTENSIONS = (".m4a", ".aac", ".mp3", ".opus", ".wav")


class APITester:
    def __init__(self):
        self.base_url = (settings.AI_AGENT_TEST_URL or settings.BACKEND_URL).rstrip("/")

    def _check_config(self):
        if not self.base_url:
            raise RuntimeError("AI_AGENT_TEST_URL or BACKEND_URL is not configured")

    def _result(self, response, url, extra=None):
        result = {
            "url": url,
            "status_code": response.status_code,
            "ok": response.ok,
            "response": response.text[:1000],
        }
        if extra:
            result.update(extra)
        return result

    def health_check(self):
        self._check_config()
        url = f"{self.base_url}/health"
        try:
            response = requests.get(url, timeout=settings.AI_AGENT_HEALTH_TIMEOUT_SECONDS)
            return self._result(response, url)
        except requests.RequestException as exc:
            return {"url": url, "ok": False, "error": str(exc), "error_type": type(exc).__name__}

    def info_test(self, url=None):
        self._check_config()
        test_url = url or settings.AI_TEST_VIDEO_URL
        if not test_url:
            return {"ok": False, "skipped": True, "reason": "AI_TEST_VIDEO_URL is not configured"}

        endpoint = f"{self.base_url}/api/info"
        try:
            response = requests.post(
                endpoint,
                json={"url": test_url},
                timeout=settings.AI_AGENT_INFO_TEST_TIMEOUT_SECONDS,
            )
            result = self._result(response, endpoint)
            result["test_video_url"] = test_url
            if response.ok:
                try:
                    data = response.json()
                    result["title"] = data.get("title")
                    result["platform"] = data.get("platform")
                    result["default_quality"] = data.get("default_quality")
                    result["available_qualities"] = data.get("available_qualities", [])
                except ValueError:
                    result["ok"] = False
                    result["error"] = "Metadata endpoint returned non-JSON response"
            return result
        except requests.RequestException as exc:
            return {"url": endpoint, "ok": False, "error": str(exc), "error_type": type(exc).__name__, "test_video_url": test_url}

    def download_test(self, url=None, quality=None):
        self._check_config()
        test_url = url or settings.AI_TEST_VIDEO_URL
        if not test_url:
            return {"ok": False, "skipped": True, "reason": "AI_TEST_VIDEO_URL is not configured"}

        endpoint = f"{self.base_url}/api/download"
        requested_quality = quality or settings.AI_TEST_DOWNLOAD_QUALITY
        payload = {"url": test_url}
        if requested_quality:
            payload["quality"] = requested_quality

        try:
            with requests.post(
                endpoint,
                json=payload,
                stream=True,
                timeout=(20, settings.AI_AGENT_DOWNLOAD_TEST_TIMEOUT_SECONDS),
            ) as response:
                content_type = (response.headers.get("content-type") or "").lower()
                disposition = response.headers.get("content-disposition") or ""
                filename = self._filename_from_disposition(disposition)
                ext = os.path.splitext(filename)[1].lower() if filename else ""
                sample = b""
                total_read = 0
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    if len(sample) < 256 * 1024:
                        sample += chunk[: 256 * 1024 - len(sample)]
                    total_read += len(chunk)
                    if total_read >= settings.AI_AGENT_DOWNLOAD_SAMPLE_BYTES:
                        break

                video_header = content_type.startswith("video/") or ext in VIDEO_EXTENSIONS
                audio_header = content_type.startswith("audio/") or ext in AUDIO_EXTENSIONS
                looks_like_video = self._looks_like_video(sample, ext)
                looks_like_audio = self._looks_like_audio(sample, ext)

                ok = response.ok and video_header and not audio_header and not looks_like_audio
                if response.ok and not video_header:
                    ok = False

                result = {
                    "url": endpoint,
                    "status_code": response.status_code,
                    "ok": ok,
                    "test_video_url": test_url,
                    "requested_quality": requested_quality,
                    "content_type": content_type,
                    "content_disposition": disposition[:500],
                    "filename": filename,
                    "sampled_bytes": total_read,
                    "content_length": response.headers.get("content-length"),
                    "looks_like_video": looks_like_video,
                    "looks_like_audio": looks_like_audio,
                }
                if not ok:
                    result["failure_reason"] = self._download_failure_reason(response.status_code, content_type, filename, looks_like_audio)
                return result
        except requests.RequestException as exc:
            return {
                "url": endpoint,
                "ok": False,
                "test_video_url": test_url,
                "requested_quality": requested_quality,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }

    @staticmethod
    def _filename_from_disposition(disposition):
        match = re.search(r'filename="([^"]+)"', disposition, re.I)
        if match:
            return match.group(1)
        match = re.search(r"filename=([^;]+)", disposition, re.I)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _looks_like_video(sample, ext):
        if ext in VIDEO_EXTENSIONS:
            return True
        if sample.startswith(b"Eß£"):
            return True
        if len(sample) >= 12 and sample[4:8] == b"ftyp":
            return True
        return False

    @staticmethod
    def _looks_like_audio(sample, ext):
        if ext in AUDIO_EXTENSIONS:
            return True
        if sample.startswith(b"ID3") or sample.startswith(b"OggS"):
            return True
        return False

    @staticmethod
    def _download_failure_reason(status_code, content_type, filename, looks_like_audio):
        if looks_like_audio:
            return "Downloader returned an audio-only response for a video test."
        if status_code >= 500:
            return "Downloader returned a server-side error."
        if status_code >= 400:
            return "Downloader endpoint returned a client/extraction error."
        if not content_type.startswith("video/"):
            return "Downloader response did not identify a video media type."
        if filename and os.path.splitext(filename)[1].lower() not in VIDEO_EXTENSIONS:
            return "Downloader returned a non-video filename extension."
        return "Downloader response did not pass video validation."

    def test_endpoint(self, path):
        self._check_config()
        if not path.startswith("/"):
            path = "/" + path
        url = f"{self.base_url}{path}"
        try:
            response = requests.get(url, timeout=30)
            return self._result(response, url)
        except requests.RequestException as exc:
            return {"url": url, "ok": False, "error": str(exc), "error_type": type(exc).__name__}


api_tester = APITester()
