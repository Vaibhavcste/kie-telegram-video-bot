import os
import sys
import time
import requests
import json
from typing import Dict, Any, Optional, Tuple
from config import OPENLUX_API_KEY, OPENLUX_BASE_URL, MODELS

class OpenLuxClient:
    def __init__(self, api_key: str = OPENLUX_API_KEY, base_url: str = OPENLUX_BASE_URL):
        self.api_key = api_key or os.getenv("OPENLUX_API_KEY", OPENLUX_API_KEY)
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def create_generation_task(
        self,
        model_key: str,
        prompt: str,
        duration: str = "5",
        aspect_ratio: str = "9:16",
        resolution: str = "720p",
        image_url: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Create a video generation job on OpenLux API (Grok Imagine Video or Kling 3.0 Turbo).
        Returns (success, result_dict_or_error).
        """
        if model_key not in MODELS:
            model_key = "grok"

        model_config = MODELS[model_key]
        endpoint_type = model_config["endpoint_type"]
        dur_int = int(duration) if str(duration).isdigit() else 5

        # 1. Grok Imagine Video
        if endpoint_type == "grok":
            url = f"{self.base_url}/v1/videos/generations"
            payload = {
                "model": "grok-imagine-video",
                "prompt": prompt,
                "aspect_ratio": aspect_ratio,  # "9:16", "16:9", "1:1"
                "resolution": resolution,      # "720p", "1080p", "480p"
                "duration": dur_int            # 5, 6, 10
            }
            try:
                res = requests.post(url, headers=self.headers, json=payload, timeout=30)
                if res.status_code == 200:
                    data = res.json()
                    req_id = data.get("request_id") or data.get("id")
                    if req_id:
                        return True, {
                            "task_id": req_id,
                            "endpoint_type": "grok",
                            "model_key": model_key
                        }
                    return False, {"error": f"No request_id returned: {data}"}
                return False, {"error": f"OpenLux Error {res.status_code}: {res.text}"}
            except Exception as e:
                return False, {"error": str(e)}

        # 2. Kling 3.0 Turbo Video (Text-to-Video or Image-to-Video)
        elif endpoint_type == "kling":
            if image_url:
                url = f"{self.base_url}/kling/v1/videos/image2video"
                payload = {
                    "model": "kling-3.0-turbo",
                    "prompt": prompt,
                    "image": image_url,
                    "duration": dur_int
                }
                mode_type = "kling_i2v"
            else:
                url = f"{self.base_url}/kling/v1/videos/text2video"
                payload = {
                    "model": "kling-3.0-turbo",
                    "prompt": prompt,
                    "duration": dur_int
                }
                mode_type = "kling_t2v"

            try:
                res = requests.post(url, headers=self.headers, json=payload, timeout=30)
                if res.status_code == 200:
                    data = res.json()
                    if data.get("code") == 0 and "data" in data and "task_id" in data["data"]:
                        return True, {
                            "task_id": data["data"]["task_id"],
                            "endpoint_type": mode_type,
                            "model_key": model_key
                        }
                    return False, {"error": f"Kling API error: {data}"}
                return False, {"error": f"Kling Error {res.status_code}: {res.text}"}
            except Exception as e:
                return False, {"error": str(e)}

        else:
            return False, {"error": f"Unsupported endpoint type '{endpoint_type}'"}

    def poll_task_status(self, task_id: str, endpoint_type: str) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Poll task status on OpenLux API.
        Returns (state, media_url, error_message).
        state can be: 'processing', 'success', 'failed', 'error'
        """
        try:
            # 1. Grok Video Polling
            if endpoint_type == "grok":
                url = f"{self.base_url}/v1/videos/{task_id}"
                res = requests.get(url, headers=self.headers, timeout=15)
                if res.status_code != 200:
                    return "error", None, f"HTTP {res.status_code}: {res.text}"

                data = res.json()
                status = data.get("status")

                if status in ["done", "succeed", "completed", "SUCCESS"] or "video" in data or "video_url" in data:
                    video_dict = data.get("video", {}) if isinstance(data.get("video"), dict) else {}
                    url_val = video_dict.get("url") or data.get("video_url") or data.get("url")
                    if url_val and url_val.startswith("http"):
                        return "success", url_val, None
                    return "failed", None, f"No video URL found in response: {data}"

                elif status in ["failed", "FAILED", "rejected", "error"]:
                    err_msg = data.get("error") or data.get("fail_reason") or "Grok generation failed."
                    return "failed", None, str(err_msg)

                else:
                    return "processing", None, None

            # 2. Kling Video Polling
            elif endpoint_type in ["kling_t2v", "kling_i2v"]:
                sub_path = "image2video" if endpoint_type == "kling_i2v" else "text2video"
                url = f"{self.base_url}/kling/v1/videos/{sub_path}/{task_id}"
                res = requests.get(url, headers=self.headers, timeout=15)
                if res.status_code != 200:
                    return "error", None, f"HTTP {res.status_code}: {res.text}"

                data_json = res.json()
                data = data_json.get("data", {})
                status = data.get("task_status")

                if status == "succeed":
                    videos = data.get("task_result", {}).get("videos", [])
                    if videos and isinstance(videos, list) and "url" in videos[0]:
                        return "success", videos[0]["url"], None
                    return "failed", None, f"No Kling video URL found: {data_json}"

                elif status in ["failed", "FAILED"]:
                    err_msg = data.get("task_status_msg") or "Kling video generation failed."
                    return "failed", None, str(err_msg)

                else:
                    return "processing", None, None

            else:
                return "error", None, f"Unknown polling endpoint type '{endpoint_type}'"

        except Exception as e:
            return "error", None, str(e)
