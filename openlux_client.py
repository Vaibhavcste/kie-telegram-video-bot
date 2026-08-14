import logging
import os
import re
import tempfile
from typing import Any, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import MAX_VIDEO_BYTES, MODELS, OPENLUX_API_KEY, OPENLUX_BASE_URL, normalized_settings


logger = logging.getLogger(__name__)
_SECRET_PATTERN = re.compile(r"(?:sk|kie)-[A-Za-z0-9_-]+")


def _safe_error(message: object) -> str:
    return _SECRET_PATTERN.sub("[redacted]", str(message))[:1000]


class OpenLuxClient:
    def __init__(
        self,
        api_key: str = OPENLUX_API_KEY,
        base_url: str = OPENLUX_BASE_URL,
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
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _json(response: requests.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise ValueError("Provider returned an invalid response") from exc
        if not isinstance(data, dict):
            raise ValueError("Provider returned an unexpected response")
        return data

    def create_generation_task(
        self,
        model_key: str,
        prompt: str,
        duration: str = "5",
        aspect_ratio: str = "9:16",
        resolution: str = "720p",
        image_data: Optional[str] = None,
    ) -> Tuple[bool, dict[str, Any]]:
        if model_key not in MODELS:
            return False, {"error": "Unsupported generation route"}

        cfg = normalized_settings(
            {"duration": duration, "aspect_ratio": aspect_ratio, "resolution": resolution},
            route=model_key,
        )
        model = MODELS[model_key]
        duration_value = int(cfg["duration"])

        if model_key == "grok":
            url = f"{self.base_url}/v1/videos/generations"
            payload = {
                "model": model["api_model"],
                "prompt": prompt,
                "aspect_ratio": cfg["aspect_ratio"],
                "resolution": cfg["resolution"],
                "duration": duration_value,
            }
            endpoint_type = "grok"
        else:
            sub_path = "image2video" if image_data else "text2video"
            url = f"{self.base_url}/kling/v1/videos/{sub_path}"
            payload = {
                "model": model["api_model"],
                "prompt": prompt,
                "duration": duration_value,
                "aspect_ratio": cfg["aspect_ratio"],
                "resolution": cfg["resolution"],
            }
            if image_data:
                payload["image"] = image_data
            endpoint_type = "kling_i2v" if image_data else "kling_t2v"

        try:
            # POST is not automatically retried: that could create duplicate paid jobs.
            response = self.session.post(url, headers=self.headers, json=payload, timeout=(10, 45))
            if response.status_code < 200 or response.status_code >= 300:
                logger.warning("Generation submission rejected: route=%s status=%s body=%s", model_key, response.status_code, _safe_error(response.text))
                return False, {"error": "The generation service did not accept the request"}

            data = self._json(response)
            if model_key == "grok":
                task_id = data.get("request_id") or data.get("id")
            else:
                task_id = data.get("data", {}).get("task_id") if data.get("code") == 0 else None
            if not task_id:
                logger.warning("Generation response lacked a task ID: route=%s response=%s", model_key, _safe_error(data))
                return False, {"error": "The generation service returned an incomplete response"}
            return True, {"task_id": str(task_id), "endpoint_type": endpoint_type, "settings": cfg}
        except requests.RequestException as exc:
            logger.warning("Generation submission network error: %s", _safe_error(exc))
            return False, {"error": "The generation service is temporarily unreachable"}
        except (TypeError, ValueError) as exc:
            logger.warning("Generation submission response error: %s", _safe_error(exc))
            return False, {"error": str(exc)}

    def poll_task_status(self, task_id: str, endpoint_type: str) -> Tuple[str, Optional[str], Optional[str]]:
        if endpoint_type == "grok":
            url = f"{self.base_url}/v1/videos/{task_id}"
        elif endpoint_type in ("kling_t2v", "kling_i2v"):
            sub_path = "image2video" if endpoint_type == "kling_i2v" else "text2video"
            url = f"{self.base_url}/kling/v1/videos/{sub_path}/{task_id}"
        else:
            return "failed", None, "Unknown generation route"

        try:
            response = self.session.get(url, headers=self.headers, timeout=(10, 30))
            if response.status_code in (404, 410):
                return "failed", None, "Generation job was not found"
            if response.status_code < 200 or response.status_code >= 300:
                return "error", None, f"Temporary provider response ({response.status_code})"
            payload = self._json(response)

            if endpoint_type == "grok":
                status = str(payload.get("status", "")).lower()
                video = payload.get("video") if isinstance(payload.get("video"), dict) else {}
                media_url = video.get("url") or payload.get("video_url") or payload.get("url")
            else:
                data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
                status = str(data.get("task_status", "")).lower()
                videos = data.get("task_result", {}).get("videos", [])
                media_url = videos[0].get("url") if videos and isinstance(videos[0], dict) else None

            if status in ("done", "succeed", "completed", "success"):
                if isinstance(media_url, str) and media_url.startswith(("https://", "http://")):
                    return "success", media_url, None
                return "failed", None, "Completed job did not include a video"
            if status in ("failed", "rejected", "error", "cancelled", "canceled"):
                return "failed", None, "The video could not be generated"
            return "processing", None, None
        except requests.RequestException as exc:
            return "error", None, _safe_error(exc)
        except (TypeError, ValueError) as exc:
            return "error", None, _safe_error(exc)

    def download_video(self, media_url: str) -> str:
        """Download a completed result with a hard byte limit and return a temp path."""
        headers = self.headers if media_url.startswith(self.base_url) else {}
        path = ""
        try:
            with self.session.get(media_url, headers=headers, stream=True, timeout=(10, 120)) as response:
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
