# 🎬 Team AI Video & Image Generator Telegram Bot

A production-ready Telegram Bot designed for teams to generate flagship AI videos and images directly inside Telegram using the **KIE API** (`https://vgen.abhibots.com/`).

---

## ⚡ Default Recommended Model: xAI Grok Video 1.5
The bot defaults to **xAI Grok Video 1.5** (`grok-imagine-video-1-5-preview`), providing ultra-fast video generation at **$0.007/sec** (~$0.042 for a 6s video).

---

## ✨ Features & Capabilities

1. **8+ Flagship AI Video & Image Models**:
   - **xAI Grok Video 1.5** (`grok-imagine-video-1-5-preview`) — Recommended Default
   - **ByteDance Seedance 2.0 & 1.5** (`bytedance/seedance-2`, `seedance-1.5-pro`) — Supports up to 4K resolution
   - **Google Veo 3 & Veo 3 Fast** (`veo3`, `veo3_fast`) — Flat per-request pricing
   - **Runway Gen-4** (`runway-gen4`)
   - **Kuaishou Kling 2.6** (`kling-2.6/text-to-video`) — Audio generation toggle
   - **MiniMax Hailuo 02** (`hailuo/02-text-to-video-standard`)
   - **Google Gemini Omni** (`gemini-omni-video`) — T2V, I2V, V2V
   - **OpenAI GPT Image 2** (`gpt-image-2`) — Synchronous photo creation

2. **Group Chat Support**:
   - In private chats: Type any prompt directly to generate.
   - In group chats: Mention `@csteinternalvideobot <prompt>` or send `/generate <prompt>`.

3. **Smart Image-to-Video Auto-Switching**:
   - When a user uploads a photo with a caption, if their active model is text-only (e.g. Grok), the bot automatically switches to an Image-to-Video model (Seedance 2.0) and notifies the user.

4. **Thread-Safe & Secure**:
   - Uses `.env` for token security (never commits secrets to GitHub).
   - Thread-safe user configuration persistence (`user_settings.json`).
   - Markdown parsing safety to prevent crashes from special characters.
   - Large file (>50MB) Telegram upload fallback to direct download links.

---

## 🚀 Quick Start Guide

### 1. Clone & Setup
```bash
git clone https://github.com/Vaibhavcste/kie-telegram-video-bot.git
cd kie-telegram-video-bot

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)
Create a `.env` file in the root directory:
```env
TELEGRAM_BOT_TOKEN="8689450266:AAFbMLbDnPduiLc0m37r6fwJlhP9OzvC59c"
KIE_API_KEY="kie-e3a1c2dceb29a009a4309697122339e8"
KIE_BASE_URL="https://vgen.abhibots.com"
```

### 3. Run the Bot

**Development Mode**:
```bash
python bot.py
```

**Production 24/7 Mode (via PM2)**:
```bash
pm2 start ecosystem.config.cjs
```

---

## ⚙️ Bot Commands

- `/start` or `/help` — Welcome menu & active settings overview
- `/settings` — Interactive inline button menu for Provider, Duration, Aspect Ratio, Resolution & Sound
- `/balance` — Live API wallet balance ($ USD & ₹ INR)
- `/models` — List of all supported video/image AI providers & pricing
- Direct Text Message — Immediately generates video with active settings!
- Send Photo — Converts photo to video (Image-to-Video mode)
