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

# Supported OpenLux AI Video & Image Models Definition
MODELS = {
    "grok": {
        "name": "xAI Grok Imagine Video",
        "api_model": "grok-imagine-video",
        "endpoint_type": "grok",
        "durations": ["5", "6", "10"],
        "default_duration": "5",
        "aspect_ratios": ["9:16", "16:9", "1:1"],
        "default_aspect_ratio": "9:16",
        "resolutions": ["480p", "720p", "1080p"],
        "default_resolution": "480p",
        "pricing": "480p ~₹3.4 RS | 720p ~₹10.8 RS (5s)",
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
        "pricing": "1080p ~₹7.6 RS (Text & Image-to-Video)",
        "supports_image": True
    },
    "midjourney": {
        "name": "Midjourney V7 Photo",
        "api_model": "midjourney-v7",
        "endpoint_type": "midjourney",
        "durations": ["1"],
        "default_duration": "1",
        "aspect_ratios": ["1:1", "16:9", "9:16"],
        "default_aspect_ratio": "1:1",
        "resolutions": ["1024x1024"],
        "default_resolution": "1024x1024",
        "pricing": "High-Res 4-Grid Image Generation",
        "supports_image": False
    }
}

# Default User Settings Preset
DEFAULT_USER_SETTINGS = {
    "model": "grok",
    "duration": "5",
    "aspect_ratio": "9:16",
    "resolution": "480p",
    "quality": "medium",
    "sound": False
}
