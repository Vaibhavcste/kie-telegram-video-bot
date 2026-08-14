import os
import sys
import time
import json
import logging
import threading
import tempfile
import re
import requests
from typing import Dict, Any, Optional

import telebot
from telebot.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    Message,
    CallbackQuery
)

from config import TELEGRAM_BOT_TOKEN, OPENLUX_API_KEY, OPENLUX_BASE_URL, MODELS, DEFAULT_USER_SETTINGS, ALLOWED_USER_IDS
from openlux_client import OpenLuxClient

# Force unbuffered output for live logging
sys.stdout.reconfigure(line_buffering=True)

# Configure Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("OpenLuxBot")

# Initialize OpenLux API Client
openlux_client = OpenLuxClient(api_key=OPENLUX_API_KEY, base_url=OPENLUX_BASE_URL)

# Thread Lock for User Settings File
settings_lock = threading.Lock()
USER_SETTINGS_FILE = "user_settings.json"
user_settings: Dict[int, Dict[str, Any]] = {}

def load_user_settings():
    global user_settings
    with settings_lock:
        if os.path.exists(USER_SETTINGS_FILE):
            try:
                with open(USER_SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    user_settings = {int(k): v for k, v in data.items()}
            except Exception as e:
                logger.error(f"Failed to load user settings: {e}")

def save_user_settings():
    with settings_lock:
        try:
            with open(USER_SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(user_settings, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save user settings: {e}")

# Generation History Tracking
history_lock = threading.Lock()
HISTORY_FILE = "generation_history.json"
generation_history = []

def load_history():
    global generation_history
    with history_lock:
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    generation_history = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load generation history: {e}")

def log_generation_event(user_id: int, user_name: str, model_key: str, model_name: str, prompt: str, duration: str, status: str, media_url: str = None):
    with history_lock:
        event = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "user_id": user_id,
            "user_name": user_name,
            "model_key": model_key,
            "model_name": model_name,
            "prompt": prompt,
            "duration": duration,
            "status": status,
            "media_url": media_url
        }
        generation_history.append(event)
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(generation_history[-100:], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save generation history: {e}")

def get_user_config(user_id: int) -> Dict[str, Any]:
    with settings_lock:
        if user_id not in user_settings:
            user_settings[user_id] = DEFAULT_USER_SETTINGS.copy()
        else:
            if user_settings[user_id].get("model") not in MODELS:
                user_settings[user_id]["model"] = "grok"
            ar = str(user_settings[user_id].get("aspect_ratio", ""))
            if ":" not in ar or ar not in ["9:16", "16:9", "1:1"]:
                user_settings[user_id]["aspect_ratio"] = "9:16"
    return user_settings[user_id]

# Safe Markdown Escaper for Telegram V1 Markdown
def escape_markdown(text: str) -> str:
    """Escapes Telegram Markdown special characters in dynamic text to prevent parse errors."""
    if not text:
        return ""
    for char in ["_", "*", "`", "[", "]"]:
        text = text.replace(char, f"\\{char}")
    return text

def format_caption(prompt: str, model_name: str, duration: str, aspect_ratio: str, task_id: str) -> str:
    """Format Telegram video caption under 1000 chars to avoid API limit errors."""
    clean_p = escape_markdown(prompt)
    if len(clean_p) > 700:
        clean_p = clean_p[:700] + "..."
    clean_m = escape_markdown(model_name)
    return f"🎬 *Prompt:* {clean_p}\n🤖 *Model:* {clean_m} ({duration}s | {aspect_ratio})\n🆔 `{task_id}`"

# Validate Token before startup
if not TELEGRAM_BOT_TOKEN:
    print("\n⚠️ ERROR: TELEGRAM_BOT_TOKEN is not set.")
    print("Please set TELEGRAM_BOT_TOKEN in .env or environment variable!\n")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN, parse_mode="Markdown") if TELEGRAM_BOT_TOKEN else None
bot_username = ""

# Access Control Helpers
def is_user_allowed(user_id: int) -> bool:
    if not ALLOWED_USER_IDS:
        return True
    return user_id in ALLOWED_USER_IDS

def check_access(msg: Message) -> bool:
    user_id = msg.from_user.id
    if not is_user_allowed(user_id):
        deny_text = (
            f"⛔ *Access Restricted*\n\n"
            f"Your Telegram User ID is `{user_id}`.\n"
            f"You are not authorized to use this bot.\n\n"
            f"Please request an administrator to add your User ID to `ALLOWED_USER_IDS`."
        )
        bot.send_message(msg.chat.id, deny_text)
        return False
    return True

def safe_edit_message_text(text: str, chat_id: int, message_id: int, reply_markup=None):
    """Safely edit Telegram message text ignoring 'message is not modified' error."""
    if not bot:
        return
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup)
    except telebot.apihelper.ApiTelegramException as e:
        if "message is not modified" in str(e):
            pass
        else:
            logger.warning(f"edit_message_text exception: {e}")
    except Exception as ex:
        logger.warning(f"edit_message_text exception: {ex}")

# Helper UI Keyboards
def get_main_keyboard() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings"),
        InlineKeyboardButton("🤖 Select Model", callback_data="menu_models")
    )
    markup.row(
        InlineKeyboardButton("📊 History & Usage", callback_data="menu_history"),
        InlineKeyboardButton("ℹ️ Help & Info", callback_data="menu_info")
    )
    return markup

def get_settings_keyboard(user_id: int) -> InlineKeyboardMarkup:
    cfg = get_user_config(user_id)
    model_key = cfg["model"]
    model_info = MODELS.get(model_key, MODELS["grok"])

    markup = InlineKeyboardMarkup()
    
    # Provider Row
    markup.add(InlineKeyboardButton(f"🤖 Model: {model_info['name']}", callback_data="menu_models"))

    # Duration Row
    dur_btn_text = f"⏱️ Duration: {cfg['duration']}s"
    markup.add(InlineKeyboardButton(dur_btn_text, callback_data="menu_durations"))

    # Aspect Ratio Row
    ar_btn_text = f"📐 Aspect Ratio: {cfg['aspect_ratio']}"
    markup.add(InlineKeyboardButton(ar_btn_text, callback_data="menu_ratios"))

    # Resolution Row
    res_btn_text = f"🖥️ Resolution: {cfg['resolution']}"
    markup.add(InlineKeyboardButton(res_btn_text, callback_data="menu_resolutions"))

    markup.add(InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="menu_main"))
    return markup

def get_models_keyboard(current_model: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    for m_key, m_info in MODELS.items():
        prefix = "✅ " if m_key == current_model else ""
        markup.add(InlineKeyboardButton(f"{prefix}{m_info['name']}", callback_data=f"set_model:{m_key}"))
    markup.add(InlineKeyboardButton("⬅️ Back to Settings", callback_data="menu_settings"))
    return markup

def get_durations_keyboard(model_key: str, current_duration: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    model_info = MODELS.get(model_key, MODELS["grok"])
    durations = model_info.get("durations", ["5", "6", "10"])
    
    buttons = []
    for d in durations:
        prefix = "✅ " if d == current_duration else ""
        buttons.append(InlineKeyboardButton(f"{prefix}{d} sec", callback_data=f"set_duration:{d}"))
    
    markup.row(*buttons)
    markup.add(InlineKeyboardButton("⬅️ Back to Settings", callback_data="menu_settings"))
    return markup

def get_ratios_keyboard(model_key: str, current_ratio: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    model_info = MODELS.get(model_key, MODELS["grok"])
    ratios = model_info.get("aspect_ratios", ["9:16", "16:9", "1:1"])
    
    buttons = []
    for r in ratios:
        prefix = "✅ " if r == current_ratio else ""
        buttons.append(InlineKeyboardButton(f"{prefix}{r}", callback_data=f"set_ratio:{r}"))
    
    markup.row(*buttons)
    markup.add(InlineKeyboardButton("⬅️ Back to Settings", callback_data="menu_settings"))
    return markup

def get_resolutions_keyboard(model_key: str, current_res: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup()
    model_info = MODELS.get(model_key, MODELS["grok"])
    res_list = model_info.get("resolutions", ["480p", "720p", "1080p"])
    
    buttons = []
    for res in res_list:
        prefix = "✅ " if res == current_res else ""
        buttons.append(InlineKeyboardButton(f"{prefix}{res}", callback_data=f"set_resolution:{res}"))
    
    markup.row(*buttons)
    markup.add(InlineKeyboardButton("⬅️ Back to Settings", callback_data="menu_settings"))
    return markup


# BOT COMMAND HANDLERS
if bot:
    # Public ID check command (Always accessible)
    @bot.message_handler(commands=["id", "myid"])
    def cmd_myid(msg: Message):
        bot.send_message(msg.chat.id, f"🆔 *Your Telegram User ID:* `{msg.from_user.id}`")

    @bot.message_handler(commands=["start", "help"])
    def cmd_start(msg: Message):
        if not check_access(msg): return
        load_user_settings()
        cfg = get_user_config(msg.from_user.id)
        m_name = MODELS.get(cfg["model"], {}).get("name", "xAI Grok Imagine Video")
        
        welcome_text = (
            "🎥 *Welcome to Team AI Video Generator!*\n\n"
            "Generate flagship AI videos directly in Telegram:\n"
            "• *xAI Grok Imagine Video*\n"
            "• *Kuaishou Kling 3.0 Turbo* (Text & Photo-to-Video)\n\n"
            f"⚙️ *Active Preset:* `{escape_markdown(m_name)}` ({cfg['duration']}s | {cfg['aspect_ratio']} | {cfg['resolution']})\n\n"
            "💡 *How to use:*\n"
            "1. Simply *type any video prompt* (e.g. `A drone shot over mountain peaks at sunset`) and hit send!\n"
            "2. Or *send a photo with a caption* to animate it into a video using Kling 3.0!\n"
            "3. Use `/settings` to adjust model, duration (seconds), resolution & aspect ratio."
        )
        bot.send_message(msg.chat.id, welcome_text, reply_markup=get_main_keyboard())

    @bot.message_handler(commands=["settings"])
    def cmd_settings(msg: Message):
        if not check_access(msg): return
        user_id = msg.from_user.id
        cfg = get_user_config(user_id)
        m_info = MODELS.get(cfg["model"], MODELS["grok"])
        text = (
            "⚙️ *Video Generation Settings*\n\n"
            f"• *Model:* `{escape_markdown(m_info['name'])}`\n"
            f"• *Duration:* `{cfg['duration']} seconds`\n"
            f"• *Aspect Ratio:* `{cfg['aspect_ratio']}`\n"
            f"• *Resolution:* `{cfg['resolution']}`\n\n"
            "Tap any button below to adjust your parameters:"
        )
        bot.send_message(msg.chat.id, text, reply_markup=get_settings_keyboard(user_id))

    @bot.message_handler(commands=["models"])
    def cmd_models(msg: Message):
        if not check_access(msg): return
        text = "🤖 *Available AI Video Models:*\n\n"
        for k, info in MODELS.items():
            text += f"• *{escape_markdown(info['name'])}*\n"
        text += "\nUse `/settings` to switch your active model."
        bot.send_message(msg.chat.id, text)

    @bot.message_handler(commands=["generate"])
    def cmd_generate(msg: Message):
        if not check_access(msg): return
        prompt = msg.text.replace("/generate", "").strip()
        if not prompt or len(prompt) < 3:
            bot.send_message(msg.chat.id, "⚠️ *Please provide a clear prompt after /generate.*\nExample: `/generate A drone shot over snowy mountain peaks`")
            return
        handle_generation_request(msg.chat.id, msg.from_user.id, prompt, image_url=None)

    # Admin Team User Whitelist Commands
    @bot.message_handler(commands=["addid"])
    def cmd_addid(msg: Message):
        if not check_access(msg): return
        args = msg.text.replace("/addid", "").strip()
        if not args or not args.isdigit():
            bot.send_message(msg.chat.id, "⚠️ *Usage:* `/addid <telegram_user_id>`\nExample: `/addid 123456789`")
            return
        new_id = int(args)
        if new_id not in ALLOWED_USER_IDS:
            ALLOWED_USER_IDS.append(new_id)
            env_str = ",".join(map(str, ALLOWED_USER_IDS))
            try:
                env_path = ".env"
                if os.path.exists(env_path):
                    with open(env_path, "r") as f:
                        lines = f.readlines()
                    with open(env_path, "w") as f:
                        for line in lines:
                            if line.startswith("ALLOWED_USER_IDS="):
                                f.write(f'ALLOWED_USER_IDS="{env_str}"\n')
                            else:
                                f.write(line)
            except Exception as e:
                logger.error(f"Failed to update .env: {e}")
            bot.send_message(msg.chat.id, f"✅ User ID `{new_id}` added to authorized team whitelist!")
        else:
            bot.send_message(msg.chat.id, f"ℹ️ User ID `{new_id}` is already in the whitelist.")

    @bot.message_handler(commands=["usage", "history"])
    def cmd_usage(msg: Message):
        if not check_access(msg): return
        load_history()
        with history_lock:
            if not generation_history:
                bot.send_message(msg.chat.id, "📊 *No generation history recorded yet.*\nStart generating videos to log usage!")
                return
            
            total_jobs = len(generation_history)
            recent = generation_history[-8:]
            
            history_text = f"📊 *Team Generation Log ({total_jobs} Total Jobs)*\n\n*Recent Generations:*\n"
            for item in reversed(recent):
                status_icon = "✅" if item.get("status") == "success" else "❌"
                clean_p = escape_markdown(item.get("prompt", ""))[:40]
                clean_m = escape_markdown(item.get("model_name", ""))
                clean_u = escape_markdown(item.get("user_name", str(item.get("user_id"))))
                history_text += f"{status_icon} *{clean_m}* ({item.get('duration')}s) — ID: `{clean_u}`\n  └ `\"{clean_p}...\"` [{item.get('timestamp')}]\n"
            
            bot.send_message(msg.chat.id, history_text)

    @bot.message_handler(commands=["listusers"])
    def cmd_listusers(msg: Message):
        if not check_access(msg): return
        if not ALLOWED_USER_IDS:
            bot.send_message(msg.chat.id, "🔓 *Access Mode:* Unrestricted (Any user can access).")
        else:
            users_str = "\n".join([f"• `{uid}`" for uid in ALLOWED_USER_IDS])
            bot.send_message(msg.chat.id, f"🔒 *Authorized Team User IDs:*\n\n{users_str}")

    # Photo Message Handler (Image to Video)
    @bot.message_handler(content_types=['photo'])
    def handle_photo(msg: Message):
        if not check_access(msg): return
        caption = msg.caption or "Animate this photo with natural dynamic motion"
        chat_id = msg.chat.id
        user_id = msg.from_user.id

        cfg = get_user_config(user_id)
        current_model = cfg["model"]
        model_info = MODELS.get(current_model, MODELS["grok"])

        # Determine target model for Image-to-Video without overwriting user's default setting
        target_model = current_model
        notice_prefix = ""
        if not model_info.get("supports_image"):
            target_model = "kling"
            notice_prefix = "ℹ️ *Notice:* Photos require an Image-to-Video model. Animating photo using *Kuaishou Kling 3.0 Turbo* (your default active model remains unchanged).\n\n"

        status_msg = bot.send_message(chat_id, f"{notice_prefix}📤 *Processing photo for API...*")
        try:
            file_info = bot.get_file(msg.photo[-1].file_id)
            img_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_info.file_path}"
            
            safe_edit_message_text("✅ *Photo ready! Launching Image-to-Video generation...*", chat_id, status_msg.message_id)
            handle_generation_request(chat_id, user_id, caption, image_url=img_url, status_msg_id=status_msg.message_id, override_model=target_model)
        except Exception as e:
            bot.send_message(chat_id, f"❌ Error handling photo: {escape_markdown(str(e))}")

    # Text Message Handler (Direct Prompts with Group Chat Intelligence)
    @bot.message_handler(func=lambda msg: True)
    def handle_text(msg: Message):
        if msg.text.startswith("/"):
            return
        if not check_access(msg): return

        chat_type = msg.chat.type
        text = msg.text.strip()

        # Filtering conversational short greetings or non-prompts in private chats
        conversational_words = ["hi", "hello", "hey", "hola", "ok", "okay", "thanks", "thank you", "cool", "help"]
        if text.lower() in conversational_words or len(text) < 3:
            bot.send_message(
                msg.chat.id,
                "👋 *Hello!* Enter any video prompt below to generate an AI video.\n"
                "Example: `A futuristic cyberpunk cat running in rain`"
            )
            return

        # In Group or Supergroup chats, only trigger if bot is mentioned or prompt starts with /generate
        if chat_type in ["group", "supergroup"]:
            if bot_username and f"@{bot_username.lower()}" in text.lower():
                prompt = re.sub(f"@{bot_username}", "", text, flags=re.IGNORECASE).strip()
                if prompt:
                    handle_generation_request(msg.chat.id, msg.from_user.id, prompt, image_url=None)
            return

        # Private Chat: Direct prompt execution
        handle_generation_request(msg.chat.id, msg.from_user.id, text, image_url=None)


# CALLBACK QUERY HANDLER (Interactive Menu Buttons)
if bot:
    @bot.callback_query_handler(func=lambda call: True)
    def handle_callbacks(call: CallbackQuery):
        user_id = call.from_user.id
        if not is_user_allowed(user_id):
            bot.answer_callback_query(call.id, "Access restricted for your Telegram User ID", show_alert=True)
            return

        cfg = get_user_config(user_id)
        data = call.data

        if data == "menu_main":
            m_name = MODELS.get(cfg["model"], {}).get("name", "xAI Grok Imagine Video")
            text = (
                "🎥 *Team AI Video Generator*\n\n"
                f"⚙️ *Active Model:* `{escape_markdown(m_name)}`\n"
                f"⏱️ `{cfg['duration']}s` | 📐 `{cfg['aspect_ratio']}` | 🖥️ `{cfg['resolution']}`"
            )
            safe_edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=get_main_keyboard())

        elif data == "menu_settings":
            m_info = MODELS.get(cfg["model"], MODELS["grok"])
            text = (
                "⚙️ *Video Generation Settings*\n\n"
                f"• *Model:* `{escape_markdown(m_info['name'])}`\n"
                f"• *Duration:* `{cfg['duration']} seconds`\n"
                f"• *Aspect Ratio:* `{cfg['aspect_ratio']}`\n"
                f"• *Resolution:* `{cfg['resolution']}`\n\n"
                "Tap any button below to adjust your settings:"
            )
            safe_edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=get_settings_keyboard(user_id))

        elif data == "menu_history":
            load_history()
            with history_lock:
                if not generation_history:
                    text = "📊 *No generation history recorded yet.*"
                else:
                    total_jobs = len(generation_history)
                    recent = generation_history[-8:]
                    text = f"📊 *Team Generation Log ({total_jobs} Total Jobs)*\n\n*Recent Generations:*\n"
                    for item in reversed(recent):
                        status_icon = "✅" if item.get("status") == "success" else "❌"
                        clean_p = escape_markdown(item.get("prompt", ""))[:40]
                        clean_m = escape_markdown(item.get("model_name", ""))
                        clean_u = escape_markdown(item.get("user_name", str(item.get("user_id"))))
                        text += f"{status_icon} *{clean_m}* ({item.get('duration')}s) — ID: `{clean_u}`\n  └ `\"{clean_p}...\"` [{item.get('timestamp')}]\n"
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⬅️ Back", callback_data="menu_main"))
            safe_edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

        elif data == "menu_models":
            safe_edit_message_text("🤖 *Select AI Video Model:*", call.message.chat.id, call.message.message_id, reply_markup=get_models_keyboard(cfg["model"]))

        elif data.startswith("set_model:"):
            m_key = data.split(":", 1)[1]
            if m_key in MODELS:
                cfg["model"] = m_key
                m_info = MODELS[m_key]
                if "durations" in m_info and cfg["duration"] not in m_info["durations"]:
                    cfg["duration"] = m_info.get("default_duration", m_info["durations"][0])
                if "aspect_ratios" in m_info and cfg["aspect_ratio"] not in m_info["aspect_ratios"]:
                    cfg["aspect_ratio"] = m_info.get("default_aspect_ratio", "9:16")
                if "resolutions" in m_info and cfg["resolution"] not in m_info["resolutions"]:
                    cfg["resolution"] = m_info.get("default_resolution", m_info["resolutions"][0])
                save_user_settings()
                bot.answer_callback_query(call.id, f"Model set to {m_info['name']}")
                safe_edit_message_text(f"✅ Provider set to *{escape_markdown(m_info['name'])}*", call.message.chat.id, call.message.message_id, reply_markup=get_settings_keyboard(user_id))

        elif data == "menu_durations":
            safe_edit_message_text("⏱️ *Select Video Duration:*", call.message.chat.id, call.message.message_id, reply_markup=get_durations_keyboard(cfg["model"], cfg["duration"]))

        elif data.startswith("set_duration:"):
            dur = data.split(":", 1)[1]
            cfg["duration"] = dur
            save_user_settings()
            bot.answer_callback_query(call.id, f"Duration set to {dur}s")
            safe_edit_message_text(f"✅ Duration set to *{dur}s*", call.message.chat.id, call.message.message_id, reply_markup=get_settings_keyboard(user_id))

        elif data == "menu_ratios":
            safe_edit_message_text("📐 *Select Aspect Ratio:*", call.message.chat.id, call.message.message_id, reply_markup=get_ratios_keyboard(cfg["model"], cfg["aspect_ratio"]))

        elif data.startswith("set_ratio:"):
            ratio = data.split(":", 1)[1]
            cfg["aspect_ratio"] = ratio
            save_user_settings()
            bot.answer_callback_query(call.id, f"Aspect Ratio set to {ratio}")
            safe_edit_message_text(f"✅ Aspect Ratio set to *{ratio}*", call.message.chat.id, call.message.message_id, reply_markup=get_settings_keyboard(user_id))

        elif data == "menu_resolutions":
            safe_edit_message_text("🖥️ *Select Video Resolution:*", call.message.chat.id, call.message.message_id, reply_markup=get_resolutions_keyboard(cfg["model"], cfg["resolution"]))

        elif data.startswith("set_resolution:"):
            res = data.split(":", 1)[1]
            cfg["resolution"] = res
            save_user_settings()
            bot.answer_callback_query(call.id, f"Resolution set to {res}")
            safe_edit_message_text(f"✅ Resolution set to *{res}*", call.message.chat.id, call.message.message_id, reply_markup=get_settings_keyboard(user_id))

        elif data == "menu_info":
            info_text = (
                "ℹ️ *Video Model Capabilities*\n\n"
                "• *xAI Grok Imagine Video:* Fastest & highly cinematic text-to-video generation.\n"
                "• *Kuaishou Kling 3.0 Turbo:* High HD realism. Supports Text & Photo-to-Video."
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⬅️ Back", callback_data="menu_main"))
            safe_edit_message_text(info_text, call.message.chat.id, call.message.message_id, reply_markup=markup)


# ASYNCHRONOUS GENERATION & POLLING ENGINE
def handle_generation_request(chat_id: int, user_id: int, prompt: str, image_url: str = None, status_msg_id: int = None, override_model: Optional[str] = None):
    cfg = get_user_config(user_id)
    model_key = override_model if override_model else cfg["model"]
    model_info = MODELS.get(model_key, MODELS["grok"])

    clean_prompt = escape_markdown(prompt)
    clean_model_name = escape_markdown(model_info['name'])

    # Initial status message
    status_text = (
        f"🎬 *Submitting Video Task...*\n\n"
        f"• *Prompt:* `{clean_prompt}`\n"
        f"• *Model:* `{clean_model_name}`\n"
        f"• *Params:* `{cfg['duration']}s` | `{cfg['aspect_ratio']}` | `{cfg['resolution']}`\n"
        f"{"• *Image Source:* Attached Photo\n" if image_url else ""}"
        f"⏳ Please wait..."
    )

    if status_msg_id:
        try:
            bot.edit_message_text(status_text, chat_id, status_msg_id)
            msg_id = status_msg_id
        except Exception:
            msg = bot.send_message(chat_id, status_text)
            msg_id = msg.message_id
    else:
        msg = bot.send_message(chat_id, status_text)
        msg_id = msg.message_id

    # Launch generation in background thread
    t = threading.Thread(
        target=_worker_generation_task,
        args=(chat_id, user_id, prompt, model_key, cfg, image_url, msg_id)
    )
    t.daemon = True
    t.start()


def _worker_generation_task(chat_id: int, user_id: int, prompt: str, model_key: str, cfg: dict, image_url: str, msg_id: int):
    model_info = MODELS[model_key]
    clean_prompt = escape_markdown(prompt)
    clean_model_name = escape_markdown(model_info['name'])

    ok, result = openlux_client.create_generation_task(
        model_key=model_key,
        prompt=prompt,
        duration=cfg["duration"],
        aspect_ratio=cfg["aspect_ratio"],
        resolution=cfg["resolution"],
        image_url=image_url
    )

    if not ok:
        raw_err = str(result.get("error", "Unknown error"))
        safe_edit_message_text(
            f"❌ *Task Submission Failed*\n\n`{escape_markdown(raw_err)}`",
            chat_id, msg_id
        )
        return

    task_id = result["task_id"]
    endpoint_type = result["endpoint_type"]

    start_time = time.time()
    poll_count = 0

    while True:
        poll_count += 1
        elapsed = int(time.time() - start_time)

        # Update Telegram status message every 10 seconds
        if poll_count % 2 == 0:
            safe_edit_message_text(
                f"⏳ *Generating Video...* [{elapsed}s elapsed]\n\n"
                f"• *Model:* `{clean_model_name}`\n"
                f"• *Task ID:* `{task_id}`\n"
                f"• *Prompt:* `{clean_prompt}`\n\n"
                f"_Polling GPU status..._",
                chat_id, msg_id
            )

        state, media_url, err = openlux_client.poll_task_status(task_id, endpoint_type)

        if state == "success" and media_url:
            log_generation_event(user_id, str(user_id), model_key, model_info['name'], prompt, cfg['duration'], "success", media_url)
            safe_edit_message_text(f"🎉 *Video Generation Complete!* [{elapsed}s]\nDownloading & sending MP4 video...", chat_id, msg_id)
            
            # Send video directly into Telegram chat with size handling
            video_sent = False
            video_caption = format_caption(prompt, model_info['name'], cfg['duration'], cfg['aspect_ratio'], task_id)
            
            try:
                bot.send_video(
                    chat_id,
                    media_url,
                    caption=video_caption,
                    supports_streaming=True
                )
                video_sent = True
            except Exception as e:
                logger.warning(f"Direct video send failed ({e}), downloading stream...")
                try:
                    headers = {}
                    if "api.openlux.ai" in media_url:
                        headers["Authorization"] = f"Bearer {OPENLUX_API_KEY}"
                    r = requests.get(media_url, headers=headers, stream=True, timeout=60)
                    file_size = int(r.headers.get("content-length", 0))
                    
                    if file_size > 50 * 1024 * 1024:
                        raise ValueError(f"File size {file_size / (1024*1024):.1f}MB exceeds Telegram limit (50MB).")

                    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                        for chunk in r.iter_content(chunk_size=8192):
                            tmp.write(chunk)
                        tmp_path = tmp.name
                    
                    with open(tmp_path, "rb") as video_file:
                        bot.send_video(
                            chat_id,
                            video_file,
                            caption=video_caption,
                            supports_streaming=True
                        )
                    os.remove(tmp_path)
                    video_sent = True
                except Exception as ex:
                    logger.warning(f"Local stream send failed: {ex}")

            if not video_sent:
                bot.send_message(
                    chat_id,
                    f"✅ *Video Generation Complete!*\n\n🎬 *Prompt:* {clean_prompt}\n🔗 [Click Here to View Video]({media_url})"
                )
            break

        elif state == "failed":
            log_generation_event(user_id, str(user_id), model_key, model_info['name'], prompt, cfg['duration'], "failed")
            clean_err = escape_markdown(str(err or 'Task was rejected or encountered GPU rendering error.'))
            safe_edit_message_text(
                f"❌ *Video Generation Failed*\n\n`{clean_err}`",
                chat_id, msg_id
            )
            break

        elif state == "error":
            logger.warning(f"Poll error for {task_id}: {err}")

        # Timeout safety (5 minutes)
        if elapsed > 300:
            safe_edit_message_text(
                f"⏱️ *Generation Timed Out (5 mins)*\nTask ID: `{task_id}`.",
                chat_id, msg_id
            )
            break

        time.sleep(5)


def main():
    global bot_username
    load_user_settings()
    if not TELEGRAM_BOT_TOKEN:
        print("\n❌ Error: TELEGRAM_BOT_TOKEN is required to run the bot.")
        print("Set TELEGRAM_BOT_TOKEN in .env file or environment variable!\n")
        sys.exit(1)

    try:
        me = bot.get_me()
        bot_username = me.username
        print(f"🤖 Telegram Bot Authenticated: @{bot_username}")
    except Exception as e:
        print(f"⚠️ Telegram bot auth warning: {e}")

    print("🚀 Starting Team AI Video Generator Telegram Bot...")
    print(f"🔑 Using OpenLux API Key: {OPENLUX_API_KEY[:8]}...{OPENLUX_API_KEY[-4:] if len(OPENLUX_API_KEY) > 12 else ''}")
    
    if ALLOWED_USER_IDS:
        print(f"🔒 Access Restricted to Telegram User IDs: {ALLOWED_USER_IDS}")
    else:
        print("🔓 Access Mode: Unrestricted (Open to any user)")

    print("🤖 Telegram Bot Polling Active! Listening for user commands...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)

if __name__ == "__main__":
    main()
