import json
import logging
import os
import tempfile
from base64 import b64decode
from typing import Any, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import ABHIBOTS_API_KEY, ABHIBOTS_BASE_URL, MAX_VIDEO_BYTES


logger = logging.getLogger(__name__)


class AbhiBotsClient:
    ROUTES = {
        "grok": {
            "model": "grok-imagine-video-1-5-preview",
            "durations": ("6", "10", "15"),
            "ratios": ("16:9", "9:16"),
            "resolutions": ("720p", "1080p"),
            "defaults": {"duration": "6", "aspect_ratio": "9:16", "resolution": "720p"},
        },
        "kling": {
            "model": "kling-2.6/image-to-video",
            "durations": ("5", "10"),
            "ratios": ("16:9", "9:16"),
            "resolutions": ("720p", "1080p"),
            "defaults": {"duration": "5", "aspect_ratio": "9:16", "resolution": "720p"},
        },
    }

    def __init__(
        self,
        api_key: str = ABHIBOTS_API_KEY,
        base_url: str = ABHIBOTS_BASE_URL,
        session: Optional[requests.Session] = None,
    ):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        retry = Retry(
            total=4,
            connect=4,
            read=3,
            status=4,
            backoff_factor=0.8,
            status_forcelist=(408, 429, 500, 502, 503, 504),
            allowed_methods=frozenset(("GET",)),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.auth_headers = {"Authorization": f"Bearer {self.api_key}"}
        self.json_headers = {**self.auth_headers, "Content-Type": "application/json"}

    @classmethod
    def normalize_settings(cls, settings: dict[str, Any], route: str) -> dict[str, str]:
        model = cls.ROUTES[route]
        result = model["defaults"].copy()
        requested = {key: str(settings.get(key, "")) for key in result}
        if requested["duration"] in model["durations"]:
            result["duration"] = requested["duration"]
        if requested["aspect_ratio"] in model["ratios"]:
            result["aspect_ratio"] = requested["aspect_ratio"]
        if requested["resolution"] in model["resolutions"]:
            result["resolution"] = requested["resolution"]
        return result

    @staticmethod
    def _json(response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("Provider returned an invalid response") from exc
        if not isinstance(payload, dict):
            raise ValueError("Provider returned an unexpected response")
        return payload

    def _upload_image(self, image_data: str) -> str:
        image_bytes = b64decode(image_data, validate=True)
        response = self.session.post(
            f"{self.base_url}/api/v1/upload",
            headers=self.auth_headers,
            files={"file": ("telegram-image.jpg", image_bytes, "image/jpeg")},
            timeout=(10, 60),
        )
        response.raise_for_status()
        payload = self._json(response)
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        url = payload.get("url") or data.get("url") or data.get("fileUrl")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            raise ValueError("Image upload returned no usable URL")
        return url

    def create_generation_task(
        self,
        model_key: str,
        prompt: str,
        duration: str = "6",
        aspect_ratio: str = "9:16",
        resolution: str = "720p",
        image_data: Optional[str] = None,
    ) -> Tuple[bool, dict[str, Any]]:
        if model_key not in self.ROUTES:
            return False, {"error": "Unsupported generation route"}
        if model_key == "kling" and not image_data:
            return False, {"error": "Photo animation requires an image"}

        settings = self.normalize_settings(
            {"duration": duration, "aspect_ratio": aspect_ratio, "resolution": resolution}, model_key
        )
        model = self.ROUTES[model_key]
        try:
            input_payload: dict[str, Any] = {
                "prompt": prompt,
                "duration": settings["duration"],
                "aspect_ratio": settings["aspect_ratio"],
                "resolution": settings["resolution"],
            }
            if model_key == "kling":
                input_payload["image_url"] = self._upload_image(image_data or "")
                input_payload["sound"] = False

            response = self.session.post(
                f"{self.base_url}/api/v1/jobs/createTask",
                headers=self.json_headers,
                json={"model": model["model"], "input": input_payload},
                timeout=(10, 45),
            )
            if response.status_code < 200 or response.status_code >= 300:
                logger.warning("AbhiBots submission rejected: route=%s status=%s", model_key, response.status_code)
                return False, {"error": "The generation service did not accept the request"}
            payload = self._json(response)
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            task_id = data.get("taskId") or data.get("task_id") or payload.get("taskId")
            if not task_id:
                return False, {"error": "The generation service returned an incomplete response"}
            return True, {"task_id": str(task_id), "endpoint_type": "jobs", "settings": settings}
        except (requests.RequestException, TypeError, ValueError) as exc:
            logger.warning("AbhiBots submission error: %s", type(exc).__name__)
            return False, {"error": "The generation service is temporarily unavailable"}

    def poll_task_status(self, task_id: str, endpoint_type: str) -> Tuple[str, Optional[str], Optional[str]]:
        if endpoint_type != "jobs":
            return "failed", None, "Unknown generation route"
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/jobs/recordInfo",
                headers=self.auth_headers,
                params={"taskId": task_id},
                timeout=(10, 30),
            )
            if response.status_code in (404, 410):
                return "failed", None, "Generation job was not found"
            if response.status_code < 200 or response.status_code >= 300:
                return "error", None, f"Temporary provider response ({response.status_code})"
            payload = self._json(response)
            data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            state = str(data.get("state") or data.get("status") or "").lower()
            if state == "success":
                result = data.get("resultJson") or {}
                result = json.loads(result) if isinstance(result, str) else result
                urls = result.get("resultUrls") or [] if isinstance(result, dict) else []
                media_url = urls[0] if urls else result.get("resultUrl") if isinstance(result, dict) else None
                if isinstance(media_url, str) and media_url.startswith(("https://", "http://")):
                    return "success", media_url, None
                return "failed", None, "Completed job did not include a video"
            if state in ("failed", "error", "cancelled", "canceled"):
                return "failed", None, "The video could not be generated"
            return "processing", None, None
        except (requests.RequestException, TypeError, ValueError, json.JSONDecodeError) as exc:
            return "error", None, type(exc).__name__

    def download_video(self, media_url: str) -> str:
        path = ""
        try:
            with self.session.get(media_url, stream=True, timeout=(10, 120)) as response:
                response.raise_for_status()
                declared_size = int(response.headers.get("content-length", "0") or 0)
                if declared_size > MAX_VIDEO_BYTES:
                    raise ValueError("Generated video is too large for Telegram delivery")
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as output:
                    path = output.name
                    total = 0
                    for chunk in response.iter_content(chunk_size=128 * 1024):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > MAX_VIDEO_BYTES:
                            raise ValueError("Generated video is too large for Telegram delivery")
                        output.write(chunk)
            return path
        except Exception:
            if path and os.path.exists(path):
                os.unlink(path)
            raise
