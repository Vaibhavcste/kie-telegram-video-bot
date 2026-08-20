import os

from dotenv import load_dotenv


load_dotenv()


def _csv_user_ids(name: str) -> list[int]:
    values = []
    for raw_value in os.getenv(name, "").split(","):
        value = raw_value.strip()
        if value:
            if not value.isdigit():
                raise ValueError(f"{name} must contain only comma-separated Telegram user IDs")
            values.append(int(value))
    return values


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
VIDEO_PROVIDER = os.getenv("VIDEO_PROVIDER", "openlux").strip().lower()
OPENLUX_API_KEY = os.getenv("OPENLUX_API_KEY", "").strip()
OPENLUX_BASE_URL = os.getenv("OPENLUX_BASE_URL", "https://api.openlux.ai").strip()
ABHIBOTS_API_KEY = os.getenv("ABHIBOTS_API_KEY", "").strip()
ABHIBOTS_BASE_URL = os.getenv("ABHIBOTS_BASE_URL", "https://vgen.abhibots.com").strip()

if VIDEO_PROVIDER not in {"openlux", "abhibots"}:
    raise ValueError("VIDEO_PROVIDER must be either 'openlux' or 'abhibots'")

# Access is deliberately fail-closed. A missing allowlist never makes the bot public.
ALLOWED_USER_IDS = _csv_user_ids("ALLOWED_USER_IDS")
ADMIN_USER_IDS = _csv_user_ids("ADMIN_USER_IDS")

MAX_CONCURRENT_JOBS = max(1, int(os.getenv("MAX_CONCURRENT_JOBS", "3")))
MAX_JOBS_PER_USER = max(1, int(os.getenv("MAX_JOBS_PER_USER", "1")))
GENERATION_TIMEOUT_SECONDS = max(60, int(os.getenv("GENERATION_TIMEOUT_SECONDS", "600")))
POLL_INTERVAL_SECONDS = max(3, int(os.getenv("POLL_INTERVAL_SECONDS", "8")))
MAX_PROMPT_LENGTH = max(100, int(os.getenv("MAX_PROMPT_LENGTH", "2000")))
MAX_IMAGE_BYTES = max(1_000_000, int(os.getenv("MAX_IMAGE_BYTES", str(10 * 1024 * 1024))))
MAX_VIDEO_BYTES = max(1_000_000, int(os.getenv("MAX_VIDEO_BYTES", str(49 * 1024 * 1024))))

# Provider routing is internal. Telegram users only choose output parameters.
MODELS = {
    "grok": {
        "api_model": "grok-imagine-video",
        "endpoint_type": "grok",
        "durations": ["5", "6", "10"],
        "aspect_ratios": ["9:16", "16:9", "1:1"],
        "resolutions": ["480p", "720p", "1080p"],
        "defaults": {"duration": "5", "aspect_ratio": "9:16", "resolution": "480p"},
    },
    "kling": {
        "api_model": "kling-3.0-turbo",
        "endpoint_type": "kling",
        "durations": ["5", "10"],
        "aspect_ratios": ["16:9", "9:16"],
        "resolutions": ["1080p", "720p"],
        "defaults": {"duration": "5", "aspect_ratio": "9:16", "resolution": "720p"},
    },
}

SETTING_OPTIONS = {
    "duration": ["5", "6", "10", "15"] if VIDEO_PROVIDER == "abhibots" else ["5", "6", "10"],
    "aspect_ratio": ["9:16", "16:9", "1:1"],
    "resolution": ["480p", "720p", "1080p"],
}

DEFAULT_USER_SETTINGS = {
    "duration": "6" if VIDEO_PROVIDER == "abhibots" else "5",
    "aspect_ratio": "9:16",
    "resolution": "480p",
}


def normalized_settings(settings: dict, route: str | None = None) -> dict:
    """Return validated settings, optionally adapted to a provider route."""
    result = DEFAULT_USER_SETTINGS.copy()
    for key, allowed in SETTING_OPTIONS.items():
        value = str(settings.get(key, result[key]))
        if value in allowed:
            result[key] = value

    if route:
        model = MODELS[route]
        for key in ("duration", "aspect_ratio", "resolution"):
            if result[key] not in model[f"{key}s" if key != "resolution" else "resolutions"]:
                result[key] = model["defaults"][key]
    return result


def validate_runtime_config() -> list[str]:
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if VIDEO_PROVIDER == "openlux" and not OPENLUX_API_KEY:
        missing.append("OPENLUX_API_KEY")
    if VIDEO_PROVIDER == "abhibots" and not ABHIBOTS_API_KEY:
        missing.append("ABHIBOTS_API_KEY")
    if not ALLOWED_USER_IDS:
        missing.append("ALLOWED_USER_IDS")
    return missing
