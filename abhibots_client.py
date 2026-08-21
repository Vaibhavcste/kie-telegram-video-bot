import json
import logging
import os
import tempfile
from base64 import b64decode
from typing import Any, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import ABHIBOTS_API_KEY, ABHIBOTS_BASE_URL, ABHIBOTS_MODELS, MAX_VIDEO_BYTES


logger = logging.getLogger(__name__)


class AbhiBotsClient:
    ROUTES = ABHIBOTS_MODELS

    def __init__(self, api_key: str = ABHIBOTS_API_KEY, base_url: str = ABHIBOTS_BASE_URL, session: Optional[requests.Session] = None):
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        retry = Retry(total=4, connect=4, read=3, status=4, backoff_factor=0.8,
                      status_forcelist=(408, 429, 500, 502, 503, 504),
                      allowed_methods=frozenset(("GET",)), respect_retry_after_header=True)
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.auth_headers = {"Authorization": f"Bearer {self.api_key}"}
        self.json_headers = {**self.auth_headers, "Content-Type": "application/json"}

    @classmethod
    def normalize_settings(cls, settings: dict[str, Any], route: str) -> dict[str, Any]:
        if route not in cls.ROUTES:
            route = "grok"
        model = cls.ROUTES[route]
        result: dict[str, Any] = {"model": route, **model["defaults"], "sound": False}
        requested = {key: str(settings.get(key, "")) for key in ("duration", "aspect_ratio", "resolution")}
        if requested["duration"] in model["durations"]:
            result["duration"] = requested["duration"]
        if requested["aspect_ratio"] in model["aspect_ratios"]:
            result["aspect_ratio"] = requested["aspect_ratio"]
        if requested["resolution"] in model["resolutions"]:
            result["resolution"] = requested["resolution"]
        result["sound"] = bool(settings.get("sound", False)) if model.get("supports_sound") else False
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

    @staticmethod
    def _extract_media_url(payload: Any) -> Optional[str]:
        if isinstance(payload, str):
            if payload.startswith(("https://", "http://")):
                return payload
            try:
                return AbhiBotsClient._extract_media_url(json.loads(payload))
            except (TypeError, ValueError):
                return None
        if isinstance(payload, list):
            for item in payload:
                found = AbhiBotsClient._extract_media_url(item)
                if found:
                    return found
        if isinstance(payload, dict):
            prioritized = ("resultUrls", "result_urls", "resultUrl", "result_url", "resultVideoUrl", "videoUrl", "video_url", "url")
            for key in prioritized:
                if key in payload:
                    found = AbhiBotsClient._extract_media_url(payload[key])
                    if found:
                        return found
            for value in payload.values():
                found = AbhiBotsClient._extract_media_url(value)
                if found:
                    return found
        return None

    def _upload_image(self, image_data: str) -> str:
        image_bytes = b64decode(image_data, validate=True)
        response = self.session.post(f"{self.base_url}/api/v1/upload", headers=self.auth_headers,
                                     files={"file": ("telegram-image.jpg", image_bytes, "image/jpeg")}, timeout=(10, 60))
        response.raise_for_status()
        payload = self._json(response)
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        url = payload.get("url") or data.get("url") or data.get("fileUrl")
        if not isinstance(url, str) or not url.startswith(("https://", "http://")):
            raise ValueError("Image upload returned no usable URL")
        return url

    def create_generation_task(self, model_key: str, prompt: str, duration: str = "6", aspect_ratio: str = "16:9",
                               resolution: str = "720p", image_data: Optional[str] = None,
                               sound: bool = False) -> Tuple[bool, dict[str, Any]]:
        if model_key not in self.ROUTES:
            return False, {"error": "Unsupported generation route"}
        model = self.ROUTES[model_key]
        if image_data and not model.get("supports_image"):
            return False, {"error": "Selected route does not support photo animation"}
        settings = self.normalize_settings({"duration": duration, "aspect_ratio": aspect_ratio,
                                            "resolution": resolution, "sound": sound}, model_key)
        try:
            image_url = self._upload_image(image_data) if image_data else None
            endpoint_type = model["endpoint_type"]
            if endpoint_type == "veo":
                url = f"{self.base_url}/api/v1/veo/generate"
                payload = {"prompt": prompt, "model": model["api_model"], "duration": int(settings["duration"]),
                           "aspectRatio": settings["aspect_ratio"], "resolution": settings["resolution"]}
            elif endpoint_type == "runway":
                url = f"{self.base_url}/api/v1/runway/generate"
                payload = {"prompt": prompt, "quality": settings["resolution"], "duration": settings["duration"]}
            else:
                url = f"{self.base_url}/api/v1/jobs/createTask"
                api_model = model.get("api_model_i2v") if image_url and model.get("api_model_i2v") else model["api_model"]
                input_payload: dict[str, Any] = {"prompt": prompt, "duration": settings["duration"],
                                                 "aspect_ratio": settings["aspect_ratio"]}
                if model_key in ("seedance2", "gemini_omni"):
                    input_payload["resolution"] = settings["resolution"]
                if model.get("supports_sound"):
                    input_payload["sound"] = settings["sound"]
                if image_url:
                    if model_key in ("kling", "hailuo"):
                        input_payload["image_url"] = image_url
                    else:
                        input_payload["image_urls"] = [image_url]
                payload = {"model": api_model, "input": input_payload}

            # POST is never retried automatically; an ambiguous retry could create a duplicate paid job.
            response = self.session.post(url, headers=self.json_headers, json=payload, timeout=(10, 45))
            if response.status_code < 200 or response.status_code >= 300:
                logger.warning("AbhiBots submission rejected: route=%s status=%s", model_key, response.status_code)
                return False, {"error": "The generation service did not accept the request"}
            response_payload = self._json(response)
            data = response_payload.get("data") if isinstance(response_payload.get("data"), dict) else {}
            task_id = data.get("taskId") or data.get("task_id") or response_payload.get("taskId") or response_payload.get("id")
            if not task_id:
                return False, {"error": "The generation service returned an incomplete response"}
            return True, {"task_id": str(task_id), "endpoint_type": endpoint_type, "settings": settings}
        except (requests.RequestException, TypeError, ValueError) as exc:
            logger.warning("AbhiBots submission error: route=%s type=%s", model_key, type(exc).__name__)
            return False, {"error": "The generation service is temporarily unavailable"}

    def poll_task_status(self, task_id: str, endpoint_type: str) -> Tuple[str, Optional[str], Optional[str]]:
        paths = {"jobs": "/api/v1/jobs/recordInfo", "veo": "/api/v1/veo/record-info",
                 "runway": "/api/v1/runway/record-detail"}
        if endpoint_type not in paths:
            return "failed", None, "Unknown generation route"
        try:
            response = self.session.get(f"{self.base_url}{paths[endpoint_type]}", headers=self.auth_headers,
                                        params={"taskId": task_id}, timeout=(10, 30))
            if response.status_code in (404, 410):
                return "failed", None, "Generation job was not found"
            if response.status_code < 200 or response.status_code >= 300:
                return "error", None, f"Temporary provider response ({response.status_code})"
            payload = self._json(response)
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            state = str(data.get("state") or data.get("status") or "").lower()
            if state in ("success", "completed", "finished"):
                media_url = self._extract_media_url(data)
                return ("success", media_url, None) if media_url else ("failed", None, "Completed job did not include a video")
            if state in ("failed", "error", "rejected", "cancelled", "canceled"):
                return "failed", None, "The video could not be generated"
            return "processing", None, None
        except (requests.RequestException, TypeError, ValueError) as exc:
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
