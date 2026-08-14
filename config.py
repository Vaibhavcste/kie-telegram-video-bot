import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# OpenLux API Credentials
OPENLUX_API_KEY = os.getenv("OPENLUX_API_KEY", "sk-XBdmFc2RhurcxMlV2O4QMNfA1FqReyWEzsraP1ZDDAHh8HOj")
OPENLUX_BASE_URL = os.getenv("OPENLUX_BASE_URL", "https://api.openlux.ai")

# Allowed Telegram User IDs Whitelist
raw_allowed = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS = [int(i.strip()) for i in raw_allowed.split(",") if i.strip().isdigit()]

# Supported OpenLux AI Video Models Definition (Grok & Kling Only)
MODELS = {
    "grok": {
        "name": "xAI Grok Imagine Video",
        "api_model": "grok-imagine-video",
        "endpoint_type": "grok",
        "durations": ["5", "6", "10"],
        "default_duration": "5",
        "aspect_ratios": ["9:16", "16:9", "1:1"],
        "default_aspect_ratio": "9:16",
        "resolutions": ["720p", "1080p", "480p"],
        "default_resolution": "720p",
        "pricing": "$0.11 USD (~₹10.80 INR per 5s clip)",
        "supports_image": False
    },
    "kling": {
        "name": "Kuaishou Kling 3.0 Turbo",
        "api_model": "kling-3.0-turbo",
        "endpoint_type": "kling",
        "durations": ["5", "10"],
        "default_duration": "5",
        "aspect_ratios": ["16:9", "9:16"],
        "default_aspect_ratio": "16:9",
        "resolutions": ["1080p"],
        "default_resolution": "1080p",
        "pricing": "0.595 RMB (~₹7.67 INR / Text & Photo-to-Video)",
        "supports_image": True
    }
}

# Default User Settings Preset
DEFAULT_USER_SETTINGS = {
    "model": "grok",
    "duration": "5",
    "aspect_ratio": "9:16",
    "resolution": "720p",
    "quality": "medium",
    "sound": False
}
