import base64
import json
import logging
import os
import re
import sys
import tempfile
import threading
import time
from typing import Any, Optional

import telebot
from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from abhibots_client import AbhiBotsClient
from config import (
    ABHIBOTS_API_KEY,
    ABHIBOTS_BASE_URL,
    ADMIN_USER_IDS,
    ALLOWED_USER_IDS,
    DEFAULT_USER_SETTINGS,
    GENERATION_TIMEOUT_SECONDS,
    MAX_CONCURRENT_JOBS,
    MAX_IMAGE_BYTES,
    MAX_JOBS_PER_USER,
    MAX_PROMPT_LENGTH,
    OPENLUX_API_KEY,
    OPENLUX_BASE_URL,
    POLL_INTERVAL_SECONDS,
    SETTING_OPTIONS,
    TELEGRAM_BOT_TOKEN,
    VIDEO_PROVIDER,
    normalized_settings,
    validate_runtime_config,
)
from openlux_client import OpenLuxClient


logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger("video_bot")

DATA_DIR = os.getenv("BOT_DATA_DIR", ".")
USER_SETTINGS_FILE = os.path.join(DATA_DIR, "user_settings.json")
HISTORY_FILE = os.path.join(DATA_DIR, "generation_history.json")

settings_lock = threading.RLock()
history_lock = threading.RLock()
job_lock = threading.Lock()
user_settings: dict[int, dict[str, str]] = {}
generation_history: list[dict[str, Any]] = []
active_jobs: dict[int, int] = {}

generation_client = (
    AbhiBotsClient(api_key=ABHIBOTS_API_KEY, base_url=ABHIBOTS_BASE_URL)
    if VIDEO_PROVIDER == "abhibots"
    else OpenLuxClient(api_key=OPENLUX_API_KEY, base_url=OPENLUX_BASE_URL)
)
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="Markdown") if TELEGRAM_BOT_TOKEN else None
bot_username = ""


def _load_json(path: str, fallback: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as source:
            return json.load(source)
    except FileNotFoundError:
        return fallback
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("Could not load %s: %s", path, exc)
        return fallback


def _write_json_atomic(path: str, data: Any) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, delete=False) as output:
            temp_path = output.name
            json.dump(data, output, indent=2, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def load_user_settings() -> None:
    global user_settings
    with settings_lock:
        data = _load_json(USER_SETTINGS_FILE, {})
        if not isinstance(data, dict):
            data = {}
        user_settings = {
            int(user_id): normalized_settings(value if isinstance(value, dict) else {})
            for user_id, value in data.items()
            if str(user_id).isdigit()
        }


def save_user_settings() -> None:
    with settings_lock:
        _write_json_atomic(USER_SETTINGS_FILE, user_settings)


def get_user_config(user_id: int) -> dict[str, str]:
    with settings_lock:
        current = normalized_settings(user_settings.get(user_id, {}))
        user_settings[user_id] = current
        return current.copy()


def update_user_setting(user_id: int, key: str, value: str) -> bool:
    if key not in SETTING_OPTIONS or value not in SETTING_OPTIONS[key]:
        return False
    with settings_lock:
        current = normalized_settings(user_settings.get(user_id, {}))
        current[key] = value
        user_settings[user_id] = current
        _write_json_atomic(USER_SETTINGS_FILE, user_settings)
    return True


def load_history() -> None:
    global generation_history
    with history_lock:
        data = _load_json(HISTORY_FILE, [])
        generation_history = data if isinstance(data, list) else []


def log_generation_event(user_id: int, prompt: str, operation: str, settings: dict, status: str) -> None:
    event = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "user_id": user_id,
        "operation": operation,
        "prompt": prompt[:MAX_PROMPT_LENGTH],
        "duration": settings["duration"],
        "aspect_ratio": settings["aspect_ratio"],
        "resolution": settings["resolution"],
        "status": status,
    }
    with history_lock:
        generation_history.append(event)
        del generation_history[:-100]
        _write_json_atomic(HISTORY_FILE, generation_history)


def escape_markdown(text: object) -> str:
    value = str(text or "")
    for char in ("_", "*", "`", "[", "]"):
        value = value.replace(char, f"\\{char}")
    return value


def format_settings(settings: dict[str, str]) -> str:
    return f"{settings['duration']}s | {settings['aspect_ratio']} | {settings['resolution']}"


def format_caption(prompt: str, settings: dict[str, str]) -> str:
    clean_prompt = escape_markdown(prompt[:700] + ("…" if len(prompt) > 700 else ""))
    return f"🎬 *Prompt:* {clean_prompt}\n⚙️ *Output:* `{format_settings(settings)}`"


def is_user_allowed(user_id: int) -> bool:
    return bool(ALLOWED_USER_IDS) and user_id in ALLOWED_USER_IDS


def is_admin(user_id: int) -> bool:
    return bool(ADMIN_USER_IDS) and user_id in ADMIN_USER_IDS and is_user_allowed(user_id)


def check_access(message: Message) -> bool:
    if is_user_allowed(message.from_user.id):
        return True
    bot.send_message(
        message.chat.id,
        "⛔ *Access Restricted*\n\n"
        f"Your Telegram User ID is `{message.from_user.id}`. Contact an administrator for access.",
    )
    return False


def _claim_job(user_id: int) -> bool:
    with job_lock:
        if sum(active_jobs.values()) >= MAX_CONCURRENT_JOBS:
            return False
        if active_jobs.get(user_id, 0) >= MAX_JOBS_PER_USER:
            return False
        active_jobs[user_id] = active_jobs.get(user_id, 0) + 1
        return True


def _release_job(user_id: int) -> None:
    with job_lock:
        remaining = active_jobs.get(user_id, 0) - 1
        if remaining > 0:
            active_jobs[user_id] = remaining
        else:
            active_jobs.pop(user_id, None)


def safe_edit_message_text(text: str, chat_id: int, message_id: int, reply_markup=None) -> None:
    if not bot:
        return
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup)
    except telebot.apihelper.ApiTelegramException as exc:
        if "message is not modified" not in str(exc).lower():
            logger.warning("Could not edit Telegram status message: %s", exc)
    except Exception as exc:
        logger.warning("Could not edit Telegram status message: %s", exc)


def get_main_keyboard() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings"),
        InlineKeyboardButton("📊 History", callback_data="menu_history"),
    )
    markup.add(InlineKeyboardButton("ℹ️ Help", callback_data="menu_info"))
    return markup


def get_settings_keyboard(user_id: int) -> InlineKeyboardMarkup:
    settings = get_user_config(user_id)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"⏱️ Duration: {settings['duration']}s", callback_data="menu_durations"))
    markup.add(InlineKeyboardButton(f"📐 Format: {settings['aspect_ratio']}", callback_data="menu_ratios"))
    markup.add(InlineKeyboardButton(f"🖥️ Quality: {settings['resolution']}", callback_data="menu_resolutions"))
    markup.add(InlineKeyboardButton("⬅️ Back", callback_data="menu_main"))
    return markup


def _options_keyboard(kind: str, current: str) -> InlineKeyboardMarkup:
    labels = {"duration": " sec", "aspect_ratio": "", "resolution": ""}
    callback_names = {"duration": "set_duration", "aspect_ratio": "set_ratio", "resolution": "set_resolution"}
    markup = InlineKeyboardMarkup()
    buttons = [
        InlineKeyboardButton(
            f"{'✅ ' if value == current else ''}{value}{labels[kind]}",
            callback_data=f"{callback_names[kind]}:{value}",
        )
        for value in SETTING_OPTIONS[kind]
    ]
    markup.row(*buttons)
    markup.add(InlineKeyboardButton("⬅️ Back", callback_data="menu_settings"))
    return markup


def settings_text(settings: dict[str, str]) -> str:
    return (
        "⚙️ *Video Settings*\n\n"
        f"• *Duration:* `{settings['duration']} seconds`\n"
        f"• *Format:* `{settings['aspect_ratio']}`\n"
        f"• *Quality:* `{settings['resolution']}`\n\n"
        "Photo animation automatically uses the best compatible rendering route. "
        "If a chosen option is unavailable for a photo, the bot safely uses the nearest compatible preset."
    )


def history_text() -> str:
    load_history()
    with history_lock:
        if not generation_history:
            return "📊 *No generation history yet.*"
        recent = generation_history[-8:]
        text = f"📊 *Team Generation Log ({len(generation_history)} jobs)*\n\n"
        for item in reversed(recent):
            icon = "✅" if item.get("status") == "success" else "❌"
            operation = "Photo animation" if item.get("operation") == "photo" else "Text video"
            prompt = escape_markdown(item.get("prompt", ""))[:45]
            text += f"{icon} *{operation}* ({item.get('duration', '?')}s)\n  └ `{prompt}…` [{item.get('timestamp', '')}]\n"
        return text


if bot:
    @bot.message_handler(commands=["id", "myid"])
    def cmd_myid(message: Message):
        bot.send_message(message.chat.id, f"🆔 *Your Telegram User ID:* `{message.from_user.id}`")

    @bot.message_handler(commands=["start", "help"])
    def cmd_start(message: Message):
        if not check_access(message):
            return
        settings = get_user_config(message.from_user.id)
        text = (
            "🎥 *Team Video Studio*\n\n"
            "Create a video by sending a detailed text prompt, or animate a photo by sending it with a caption.\n\n"
            f"⚙️ *Current output:* `{format_settings(settings)}`\n\n"
            "Use /settings to change duration, format, or quality."
        )
        bot.send_message(message.chat.id, text, reply_markup=get_main_keyboard())

    @bot.message_handler(commands=["settings"])
    def cmd_settings(message: Message):
        if check_access(message):
            settings = get_user_config(message.from_user.id)
            bot.send_message(message.chat.id, settings_text(settings), reply_markup=get_settings_keyboard(message.from_user.id))

    @bot.message_handler(commands=["generate"])
    def cmd_generate(message: Message):
        if not check_access(message):
            return
        prompt = re.sub(r"^/generate(?:@\w+)?", "", message.text or "", flags=re.IGNORECASE).strip()
        if len(prompt) < 3:
            bot.send_message(message.chat.id, "⚠️ Add a clear prompt after /generate.")
            return
        handle_generation_request(message.chat.id, message.from_user.id, prompt)

    @bot.message_handler(commands=["usage", "history"])
    def cmd_usage(message: Message):
        if check_access(message):
            bot.send_message(message.chat.id, history_text())

    @bot.message_handler(commands=["addid", "listusers"])
    def cmd_admin(message: Message):
        if not check_access(message):
            return
        if not is_admin(message.from_user.id):
            bot.send_message(message.chat.id, "⛔ This command is restricted to bot administrators.")
            return
        if (message.text or "").split()[0].lower().startswith("/listusers"):
            users = "\n".join(f"• `{user_id}`" for user_id in ALLOWED_USER_IDS)
            bot.send_message(message.chat.id, f"🔒 *Authorized Team Members*\n\n{users}")
            return
        bot.send_message(message.chat.id, "ℹ️ Update `ALLOWED_USER_IDS` in the deployment environment and restart the bot. Runtime secret files are not modified from Telegram.")

    @bot.message_handler(content_types=["photo"])
    def handle_photo(message: Message):
        caption = (message.caption or "").strip()
        if message.chat.type in ("group", "supergroup"):
            mention = f"@{bot_username}" if bot_username else ""
            if not mention or mention.lower() not in caption.lower():
                return
            caption = re.sub(re.escape(mention), "", caption, flags=re.IGNORECASE).strip()
        if not check_access(message):
            return
        prompt = caption or "Animate this photo with natural, realistic motion"
        if len(prompt) > MAX_PROMPT_LENGTH:
            bot.send_message(message.chat.id, f"⚠️ Caption is too long. Keep it under {MAX_PROMPT_LENGTH} characters.")
            return
        status = bot.send_message(message.chat.id, "📤 *Preparing your photo…*")
        try:
            file_info = bot.get_file(message.photo[-1].file_id)
            image_bytes = bot.download_file(file_info.file_path)
            if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
                raise ValueError("Photo is too large")
            # Kling-compatible APIs expect raw Base64 in the image field (no data-URI prefix).
            image_data = base64.b64encode(image_bytes).decode("ascii")
            handle_generation_request(
                message.chat.id,
                message.from_user.id,
                prompt,
                image_data=image_data,
                status_msg_id=status.message_id,
            )
        except Exception as exc:
            logger.warning("Photo preparation failed for user %s: %s", message.from_user.id, exc)
            safe_edit_message_text("❌ *Could not prepare that photo.* Please try a smaller JPG or PNG.", message.chat.id, status.message_id)

    @bot.message_handler(content_types=["text"])
    def handle_text(message: Message):
        text = (message.text or "").strip()
        if text.startswith("/"):
            return
        if message.chat.type in ("group", "supergroup"):
            mention = f"@{bot_username}" if bot_username else ""
            if not mention or mention.lower() not in text.lower():
                return
            text = re.sub(re.escape(mention), "", text, flags=re.IGNORECASE).strip()
        if not check_access(message):
            return
        if text.lower() in {"hi", "hello", "hey", "ok", "okay", "thanks", "thank you", "help"} or len(text) < 3:
            bot.send_message(message.chat.id, "👋 Send a detailed video prompt, or use /help.")
            return
        handle_generation_request(message.chat.id, message.from_user.id, text)

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callbacks(call: CallbackQuery):
        if not is_user_allowed(call.from_user.id):
            bot.answer_callback_query(call.id, "Access restricted", show_alert=True)
            return
        settings = get_user_config(call.from_user.id)
        data = call.data or ""
        markup = None
        text = ""
        if data == "menu_main":
            text = f"🎥 *Team Video Studio*\n\n⚙️ *Current output:* `{format_settings(settings)}`"
            markup = get_main_keyboard()
        elif data == "menu_settings":
            text, markup = settings_text(settings), get_settings_keyboard(call.from_user.id)
        elif data == "menu_history":
            text = history_text()
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⬅️ Back", callback_data="menu_main"))
        elif data == "menu_info":
            text = "ℹ️ *How it works*\n\nSend text to create a new video. Send a photo with a caption to animate it. Rendering routes are selected automatically."
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⬅️ Back", callback_data="menu_main"))
        elif data == "menu_durations":
            text, markup = "⏱️ *Select duration:*", _options_keyboard("duration", settings["duration"])
        elif data == "menu_ratios":
            text, markup = "📐 *Select format:*", _options_keyboard("aspect_ratio", settings["aspect_ratio"])
        elif data == "menu_resolutions":
            text, markup = "🖥️ *Select quality:*", _options_keyboard("resolution", settings["resolution"])
        else:
            callback_map = {"set_duration": "duration", "set_ratio": "aspect_ratio", "set_resolution": "resolution"}
            prefix, separator, value = data.partition(":")
            key = callback_map.get(prefix) if separator else None
            if not key or not update_user_setting(call.from_user.id, key, value):
                bot.answer_callback_query(call.id, "Invalid setting", show_alert=True)
                return
            settings = get_user_config(call.from_user.id)
            text, markup = "✅ *Settings updated*\n\n" + settings_text(settings), get_settings_keyboard(call.from_user.id)
        bot.answer_callback_query(call.id)
        safe_edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)


def handle_generation_request(
    chat_id: int,
    user_id: int,
    prompt: str,
    image_data: Optional[str] = None,
    status_msg_id: Optional[int] = None,
) -> None:
    prompt = prompt.strip()
    if len(prompt) < 3 or len(prompt) > MAX_PROMPT_LENGTH:
        bot.send_message(chat_id, f"⚠️ Prompts must be between 3 and {MAX_PROMPT_LENGTH} characters.")
        return
    if not _claim_job(user_id):
        text = "⏳ The studio is at capacity, or you already have a video rendering. Please try again shortly."
        if status_msg_id:
            safe_edit_message_text(text, chat_id, status_msg_id)
        else:
            bot.send_message(chat_id, text)
        return

    route = "kling" if image_data else "grok"
    settings = generation_client.normalize_settings(get_user_config(user_id), route)
    status_text = (
        "🎬 *Video request accepted*\n\n"
        f"• *Prompt:* `{escape_markdown(prompt[:500])}`\n"
        f"• *Output:* `{format_settings(settings)}`\n"
        f"• *Source:* `{'Attached photo' if image_data else 'Text prompt'}`\n\n"
        "⏳ Rendering has started."
    )
    try:
        if status_msg_id:
            safe_edit_message_text(status_text, chat_id, status_msg_id)
            message_id = status_msg_id
        else:
            message_id = bot.send_message(chat_id, status_text).message_id
        worker = threading.Thread(
            target=_worker_generation_task,
            args=(chat_id, user_id, prompt, route, settings, image_data, message_id),
            daemon=True,
            name=f"video-job-{user_id}",
        )
        worker.start()
    except Exception:
        _release_job(user_id)
        raise


def _worker_generation_task(
    chat_id: int,
    user_id: int,
    prompt: str,
    route: str,
    settings: dict[str, str],
    image_data: Optional[str],
    message_id: int,
) -> None:
    operation = "photo" if image_data else "text"
    try:
        ok, result = generation_client.create_generation_task(
            model_key=route,
            prompt=prompt,
            duration=settings["duration"],
            aspect_ratio=settings["aspect_ratio"],
            resolution=settings["resolution"],
            image_data=image_data,
        )
        image_data = None
        if not ok:
            logger.warning("Submission failed for user %s: %s", user_id, result.get("error"))
            log_generation_event(user_id, prompt, operation, settings, "failed")
            safe_edit_message_text("❌ *Could not start this video.* Please try again in a few minutes.", chat_id, message_id)
            return

        task_id = result["task_id"]
        endpoint_type = result["endpoint_type"]
        settings = result.get("settings", settings)
        started_at = time.monotonic()
        next_status_update = 20
        consecutive_poll_errors = 0

        while time.monotonic() - started_at <= GENERATION_TIMEOUT_SECONDS:
            state, media_url, error = generation_client.poll_task_status(task_id, endpoint_type)
            elapsed = int(time.monotonic() - started_at)
            if state == "success" and media_url:
                safe_edit_message_text("✅ *Video ready.* Preparing delivery…", chat_id, message_id)
                temp_path = ""
                try:
                    temp_path = generation_client.download_video(media_url)
                    with open(temp_path, "rb") as video_file:
                        bot.send_video(chat_id, video_file, caption=format_caption(prompt, settings), supports_streaming=True, timeout=120)
                    log_generation_event(user_id, prompt, operation, settings, "success")
                    safe_edit_message_text("🎉 *Video delivered successfully.*", chat_id, message_id)
                finally:
                    if temp_path and os.path.exists(temp_path):
                        os.unlink(temp_path)
                return
            if state == "failed":
                logger.warning("Provider generation failed: task=%s error=%s", task_id, error)
                log_generation_event(user_id, prompt, operation, settings, "failed")
                safe_edit_message_text("❌ *This video could not be generated.* Try adjusting the prompt or settings.", chat_id, message_id)
                return
            if state == "error":
                consecutive_poll_errors += 1
                logger.warning("Polling error: task=%s attempt=%s error=%s", task_id, consecutive_poll_errors, error)
                if consecutive_poll_errors >= 8:
                    log_generation_event(user_id, prompt, operation, settings, "failed")
                    safe_edit_message_text("⚠️ *Rendering status is temporarily unavailable.* Please try again later.", chat_id, message_id)
                    return
            else:
                consecutive_poll_errors = 0
            if elapsed >= next_status_update:
                safe_edit_message_text(f"⏳ *Rendering your video…* `{elapsed}s elapsed`\n\nYou can continue using Telegram while this finishes.", chat_id, message_id)
                next_status_update += 30
            time.sleep(POLL_INTERVAL_SECONDS)

        log_generation_event(user_id, prompt, operation, settings, "failed")
        safe_edit_message_text("⏱️ *Rendering took longer than expected.* Please try again later.", chat_id, message_id)
    except Exception as exc:
        logger.exception("Unhandled generation worker error for user %s: %s", user_id, exc)
        log_generation_event(user_id, prompt, operation, settings, "failed")
        safe_edit_message_text("❌ *Delivery failed unexpectedly.* Please try again in a few minutes.", chat_id, message_id)
    finally:
        _release_job(user_id)


def main() -> None:
    global bot_username
    missing = validate_runtime_config()
    if missing:
        logger.critical("Refusing to start; missing required configuration: %s", ", ".join(missing))
        sys.exit(1)
    load_user_settings()
    load_history()
    try:
        bot_username = bot.get_me().username or ""
    except Exception as exc:
        logger.warning("Telegram authentication check failed; polling will retry: %s", exc)
    logger.info("Starting Team Video Studio for %d allowed users using %s", len(ALLOWED_USER_IDS), VIDEO_PROVIDER)
    bot.infinity_polling(timeout=60, long_polling_timeout=60, skip_pending=True)


if __name__ == "__main__":
    main()
