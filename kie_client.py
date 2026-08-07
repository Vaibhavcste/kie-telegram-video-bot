import requests
import json
import time
import base64
from typing import Dict, Any, Optional, Tuple
from config import KIE_API_KEY, KIE_BASE_URL, MODELS

class KIEApiClient:
    def __init__(self, api_key: str = KIE_API_KEY, base_url: str = KIE_BASE_URL):
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def get_balance(self) -> Tuple[bool, Dict[str, Any]]:
        """Fetch current balance from KIE API"""
        url = f"{self.base_url}/api/v1/balance"
        try:
            res = requests.get(url, headers=self.headers, timeout=10)
            if res.status_code == 200:
                return True, res.json()
            return False, {"error": f"HTTP {res.status_code}: {res.text}"}
        except Exception as e:
            return False, {"error": str(e)}

    def upload_image(self, file_bytes: bytes, filename: str = "image.png") -> Tuple[bool, str]:
        """Upload image to KIE API and return public URL"""
        url = f"{self.base_url}/upload/file-base64-upload"
        try:
            b64_str = base64.b64encode(file_bytes).decode('utf-8')
            payload = {
                "base64Data": f"data:image/png;base64,{b64_str}",
                "filename": filename
            }
            res = requests.post(url, headers=self.headers, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                if "url" in data:
                    return True, data["url"]
                elif "data" in data and "url" in data["data"]:
                    return True, data["data"]["url"]
                return True, str(data)
            return False, f"Upload failed: HTTP {res.status_code} - {res.text}"
        except Exception as e:
            return False, f"Upload exception: {str(e)}"

    def create_generation_task(
        self,
        model_key: str,
        prompt: str,
        duration: str = "6",
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        sound: bool = False,
        quality: str = "medium",
        image_url: Optional[str] = None
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Create a generation job (async for videos, sync for OpenAI images).
        Returns (success, result_data_or_error_dict).
        """
        if model_key not in MODELS:
            return False, {"error": f"Unknown model key '{model_key}'"}

        model_config = MODELS[model_key]
        endpoint_type = model_config["endpoint_type"]

        # 1. OpenAI synchronous GPT Image 2
        if endpoint_type == "openai":
            if image_url:
                url = f"{self.base_url}/api/v1/openai/edit"
                payload = {
                    "prompt": prompt,
                    "image_urls": [image_url],
                    "quality": quality,
                    "size": resolution if "x" in resolution else "1024x1024"
                }
            else:
                url = f"{self.base_url}/api/v1/openai/generate"
                payload = {
                    "prompt": prompt,
                    "quality": quality,
                    "size": resolution if "x" in resolution else "1024x1024"
                }
            try:
                res = requests.post(url, headers=self.headers, json=payload, timeout=60)
                if res.status_code == 200:
                    return True, {"is_sync": True, "data": res.json()}
                return False, {"error": f"OpenAI Error {res.status_code}: {res.text}"}
            except Exception as e:
                return False, {"error": str(e)}

        # 2. Veo 3 / Veo 3 Fast
        elif endpoint_type == "veo":
            url = f"{self.base_url}/api/v1/veo/generate"
            payload = {
                "prompt": prompt,
                "model": model_config["api_model"],
                "duration": int(duration) if duration.isdigit() else 8,
                "aspectRatio": aspect_ratio,
                "resolution": resolution
            }

        # 3. Runway Gen-4
        elif endpoint_type == "runway":
            url = f"{self.base_url}/api/v1/runway/generate"
            payload = {
                "prompt": prompt,
                "quality": resolution if resolution in ["720p", "1080p"] else "720p",
                "duration": str(duration)
            }

        # 4. Jobs API (Seedance, Hailuo, Grok, Kling, Gemini Omni)
        elif endpoint_type == "jobs":
            url = f"{self.base_url}/api/v1/jobs/createTask"
            api_model_name = model_config["api_model"]

            # Check if image to video variant applies
            if image_url and "api_model_i2v" in model_config:
                api_model_name = model_config["api_model_i2v"]

            input_params = {
                "prompt": prompt,
                "duration": str(duration)
            }

            if "aspect_ratios" in model_config:
                input_params["aspect_ratio"] = aspect_ratio
            if "resolutions" in model_config and model_key in ["seedance2", "gemini_omni"]:
                input_params["resolution"] = resolution
            if model_config.get("supports_sound"):
                input_params["sound"] = sound

            if image_url:
                if model_key in ["hailuo", "kling"]:
                    input_params["image_url"] = image_url
                else:
                    input_params["image_urls"] = [image_url]

            payload = {
                "model": api_model_name,
                "input": input_params
            }

        else:
            return False, {"error": f"Unsupported endpoint_type '{endpoint_type}'"}

        # Send request
        try:
            res = requests.post(url, headers=self.headers, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                task_id = None
                if "data" in data and isinstance(data["data"], dict) and "taskId" in data["data"]:
                    task_id = data["data"]["taskId"]
                elif "taskId" in data:
                    task_id = data["taskId"]
                elif "id" in data:
                    task_id = data["id"]
                
                if task_id:
                    return True, {
                        "is_sync": False,
                        "task_id": task_id,
                        "endpoint_type": endpoint_type,
                        "model_key": model_key
                    }
                return False, {"error": f"No taskId in response: {data}"}
            else:
                return False, {"error": f"API Error {res.status_code}: {res.text}"}
        except Exception as e:
            return False, {"error": str(e)}

    def extract_media_url(self, data: Any) -> Optional[str]:
        """Robustly extract HTTP/HTTPS video or image URL from API response payload."""
        if not data:
            return None

        # 1. Parse stringified resultJson if present
        result_json = data.get("resultJson") if isinstance(data, dict) else None
        if not result_json and isinstance(data, dict):
            result_json = data.get("result_json")

        if isinstance(result_json, str):
            try:
                result_json = json.loads(result_json)
            except Exception:
                result_json = {}

        # 2. Check result_json dictionary
        if isinstance(result_json, dict):
            urls = result_json.get("resultUrls") or result_json.get("result_urls") or []
            if isinstance(urls, list) and len(urls) > 0 and str(urls[0]).startswith("http"):
                return urls[0]
            for key in ["resultImageUrl", "resultVideoUrl", "videoUrl", "video_url", "imageUrl", "image_url", "url"]:
                val = result_json.get(key)
                if val and isinstance(val, str) and val.startswith("http"):
                    return val

        # 3. Check root dictionary fields
        if isinstance(data, dict):
            urls = data.get("resultUrls") or data.get("result_urls") or []
            if isinstance(urls, list) and len(urls) > 0 and str(urls[0]).startswith("http"):
                return urls[0]

            for key in ["resultUrl", "result_url", "resultImageUrl", "resultVideoUrl", "videoUrl", "video_url", "imageUrl", "image_url", "url"]:
                val = data.get(key)
                if val and isinstance(val, str) and val.startswith("http"):
                    return val

        # 4. Fallback: Deep search for any string starting with http in the object
        def _find_urls(obj):
            if isinstance(obj, str) and obj.startswith("http"):
                return [obj]
            elif isinstance(obj, dict):
                found = []
                for v in obj.values():
                    found.extend(_find_urls(v))
                return found
            elif isinstance(obj, list):
                found = []
                for item in obj:
                    found.extend(_find_urls(item))
                return found
            return []

        all_urls = _find_urls(data)
        if all_urls:
            return all_urls[0]

        return None

    def poll_task_status(self, task_id: str, endpoint_type: str) -> Tuple[str, Optional[str], Optional[str]]:
        """
        Poll task status.
        Returns (state, media_url, error_message).
        state can be: 'processing', 'success', 'failed', 'error'
        """
        if endpoint_type == "veo":
            url = f"{self.base_url}/api/v1/veo/record-info?taskId={task_id}"
        elif endpoint_type == "runway":
            url = f"{self.base_url}/api/v1/runway/record-detail?taskId={task_id}"
        else:
            url = f"{self.base_url}/api/v1/jobs/recordInfo?taskId={task_id}"

        try:
            res = requests.get(url, headers=self.headers, timeout=15)
            if res.status_code != 200:
                return "error", None, f"HTTP {res.status_code}: {res.text}"

            resp_json = res.json()
            data = resp_json.get("data", {}) if isinstance(resp_json.get("data"), dict) else resp_json

            # State check
            state = data.get("state") or data.get("status")

            if state in ["success", "completed", "FINISHED"]:
                media_url = self.extract_media_url(data)
                if media_url:
                    return "success", media_url, None
                return "failed", None, f"Job reported success but no result URL could be parsed from payload: {data}"

            elif state in ["failed", "FAILED", "rejected"]:
                err_msg = data.get("error") or data.get("failReason") or data.get("failMsg") or "Task failed in backend."
                return "failed", None, str(err_msg)

            else:
                # Still processing / queuing / waiting
                return "processing", None, None

        except Exception as e:
            return "error", None, str(e)
