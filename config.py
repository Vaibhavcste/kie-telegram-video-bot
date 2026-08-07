import os
from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv()

# Telegram Bot Token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# KIE API Credentials
KIE_API_KEY = os.getenv("KIE_API_KEY", "")
KIE_BASE_URL = os.getenv("KIE_BASE_URL", "https://vgen.abhibots.com")

# Allowed Telegram User IDs Whitelist (empty list means unrestricted)
raw_allowed = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS = [int(i.strip()) for i in raw_allowed.split(",") if i.strip().isdigit()]

# Supported AI Video & Image Models Definition
MODELS = {
    "grok": {
        "name": "xAI Grok Video 1.5",
        "api_model": "grok-imagine-video-1-5-preview",
        "endpoint_type": "jobs",
        "durations": ["6", "10", "15"],
        "default_duration": "6",
        "aspect_ratios": ["16:9", "9:16"],
        "default_aspect_ratio": "16:9",
        "resolutions": ["720p", "1080p"],
        "default_resolution": "720p",
        "pricing": "$0.007/s (Recommended — Ultra Fast)",
        "supports_image": False
    },
    "seedance2": {
        "name": "ByteDance Seedance 2.0",
        "api_model": "bytedance/seedance-2",
        "endpoint_type": "jobs",
        "durations": ["4", "5", "8", "10", "15"],
        "default_duration": "5",
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "default_aspect_ratio": "16:9",
        "resolutions": ["480p", "720p", "1080p", "4k"],
        "default_resolution": "720p",
        "pricing": "$0.035/s",
        "supports_image": True
    },
    "seedance1.5": {
        "name": "ByteDance Seedance 1.5 Pro",
        "api_model": "bytedance/seedance-1.5-pro",
        "endpoint_type": "jobs",
        "durations": ["5", "10"],
        "default_duration": "5",
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "default_aspect_ratio": "16:9",
        "pricing": "$0.025/s",
        "supports_image": False
    },
    "veo3": {
        "name": "Google Veo 3 Flagship",
        "api_model": "veo3",
        "endpoint_type": "veo",
        "durations": ["8"],
        "default_duration": "8",
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "default_aspect_ratio": "16:9",
        "resolutions": ["720p", "1080p"],
        "default_resolution": "720p",
        "pricing": "$0.28 flat",
        "supports_image": False
    },
    "veo3_fast": {
        "name": "Google Veo 3 Fast",
        "api_model": "veo3_fast",
        "endpoint_type": "veo",
        "durations": ["8"],
        "default_duration": "8",
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "default_aspect_ratio": "16:9",
        "resolutions": ["720p", "1080p"],
        "default_resolution": "720p",
        "pricing": "$0.14 flat",
        "supports_image": False
    },
    "runway": {
        "name": "Runway Gen-4",
        "api_model": "runway-gen4",
        "endpoint_type": "runway",
        "durations": ["5", "8", "10"],
        "default_duration": "5",
        "resolutions": ["720p", "1080p"],
        "default_resolution": "720p",
        "pricing": "$0.15 flat",
        "supports_image": False
    },
    "kling": {
        "name": "Kuaishou Kling 2.6",
        "api_model": "kling-2.6/text-to-video",
        "api_model_i2v": "kling-2.6/image-to-video",
        "endpoint_type": "jobs",
        "durations": ["5", "10"],
        "default_duration": "5",
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "default_aspect_ratio": "16:9",
        "pricing": "$0.03/s",
        "supports_sound": True,
        "supports_image": True
    },
    "hailuo": {
        "name": "MiniMax Hailuo 02",
        "api_model": "hailuo/02-text-to-video-standard",
        "api_model_i2v": "hailuo/2-3-image-to-video-standard",
        "endpoint_type": "jobs",
        "durations": ["6"],
        "default_duration": "6",
        "aspect_ratios": ["16:9", "9:16"],
        "default_aspect_ratio": "16:9",
        "pricing": "$0.025/s",
        "supports_image": True
    },
    "gemini_omni": {
        "name": "Google Gemini Omni Video",
        "api_model": "gemini-omni-video",
        "endpoint_type": "jobs",
        "durations": ["4", "6", "8", "10"],
        "default_duration": "8",
        "aspect_ratios": ["16:9", "9:16"],
        "default_aspect_ratio": "16:9",
        "resolutions": ["720p", "1080p", "4k"],
        "default_resolution": "1080p",
        "pricing": "$0.035/s",
        "supports_image": True
    },
    "gpt_image": {
        "name": "OpenAI GPT Image 2",
        "api_model": "gpt-image-2",
        "endpoint_type": "openai",
        "resolutions": ["1024x1024", "1536x1024", "1024x1536"],
        "default_resolution": "1024x1024",
        "qualities": ["low", "medium", "high"],
        "default_quality": "medium",
        "pricing": "Pay-per-image (~$0.008)",
        "supports_image": True
    }
}

# Default Preset Settings (Recommended model: Grok Video 1.5)
DEFAULT_USER_SETTINGS = {
    "model": "grok",
    "duration": "6",
    "aspect_ratio": "16:9",
    "resolution": "720p",
    "sound": False,
    "quality": "medium"
}
