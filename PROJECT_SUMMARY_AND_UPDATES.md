# Team AI Video Generator Bot — Project Summary & Architecture Guide

## 📌 Executive Overview

This repository contains the full production codebase for **Team AI Video Generator Telegram Bot** (`@csteinternalvideobot`), powered by the **OpenLux Video API** (`api.openlux.ai`).

The bot allows authorized team members to generate cinematic AI videos via text prompts or animate photos using top-tier generative video models directly inside Telegram.

---

## 📁 Repository & Folder Location

* **Local Workspace Directory**: `/Users/vaibhavthakur/Desktop/python2026/agent-gravity/kie-telegram-video-bot`
* **GitHub Repository**: [https://github.com/Vaibhavcste/kie-telegram-video-bot](https://github.com/Vaibhavcste/kie-telegram-video-bot)
* **Active Telegram Bot**: `@csteinternalvideobot`

---

## 🔑 Active System Credentials & Configuration

* **API Provider**: OpenLux AI (`https://api.openlux.ai`)
* **API Key**: Set via `.env` (`OPENLUX_API_KEY`)
* **Telegram Bot Token**: Set via `.env` (`TELEGRAM_BOT_TOKEN`)
* **Access Control Whitelist**: `ALLOWED_USER_IDS="1113489467,8558803643"` (Whitelisted for CSTE team members)

---

## 🎥 Supported Flagship Video Models

1. **xAI Grok Imagine Video (`grok`)**:
   - **Type**: Text-to-Video
   - **Supported Resolutions**: `480p`, `720p`, `1080p` (Dynamic selection)
   - **Supported Aspect Ratios**: `9:16` (Vertical Reels/Shorts), `16:9` (Widescreen), `1:1` (Square)
   - **Supported Durations**: `5s`, `6s`, `10s`

2. **Kuaishou Kling 3.0 Turbo (`kling`)**:
   - **Type**: Text-to-Video & Photo-to-Video Animation
   - **Supported Resolutions**: `1080p`, `720p`
   - **Supported Aspect Ratios**: `16:9`, `9:16`
   - **Supported Durations**: `5s`, `10s`

---

## ✨ Latest Features & Customizations Implemented

1. **Clean Team Interface (No Pricing or Balance Clutter)**:
   - Stripped out all raw account balance views and per-video pricing text. Team members enjoy a clean, professional, distraction-free menu.
2. **Fully Dynamic Parameters**:
   - Resolutions (`480p`, `720p`, `1080p`), Durations (`5s`, `6s`, `10s`), and Aspect Ratios are completely dynamic and adjustable per user via `/settings`.
3. **Smart Photo Animation Routing**:
   - Uploading any photo with a caption automatically triggers Kling 3.0 Turbo for Image-to-Video rendering without changing the user's permanent model preference in settings.
4. **Local Audit & Usage History Logging**:
   - Tracks all generations in `generation_history.json` and displays them via `/usage` and `/history` commands.
5. **Security & Git Protection**:
   - `.env` and sensitive credentials remain 100% gitignored and isolated from repository commits.

---

## 📂 Project File Directory Structure

| File Path | Description |
| :--- | :--- |
| `/Users/vaibhavthakur/Desktop/python2026/agent-gravity/kie-telegram-video-bot/PROJECT_SUMMARY_AND_UPDATES.md` | **Main Documentation & Setup Guide** (This file) |
| `/Users/vaibhavthakur/Desktop/python2026/agent-gravity/kie-telegram-video-bot/bot.py` | Main Telegram Bot Application Engine & UI Handlers |
| `/Users/vaibhavthakur/Desktop/python2026/agent-gravity/kie-telegram-video-bot/openlux_client.py` | OpenLux API Client (Grok & Kling Task Creation & Polling) |
| `/Users/vaibhavthakur/Desktop/python2026/agent-gravity/kie-telegram-video-bot/config.py` | Bot Models & Settings Configuration |
| `/Users/vaibhavthakur/Desktop/python2026/agent-gravity/kie-telegram-video-bot/ABHIBOTS_API_BACKUP.md` | Archive of Legacy AbhiBots API Endpoints & Settings |
| `/Users/vaibhavthakur/Desktop/python2026/agent-gravity/kie-telegram-video-bot/generation_history.json` | Local Usage & Job History Log File |
| `/Users/vaibhavthakur/Desktop/python2026/agent-gravity/kie-telegram-video-bot/.env` | Environment Variables (Bot Token & OpenLux Key — Untracked) |

---

## 🚀 How to Run locally / Deploy

```bash
# 1. Navigate to directory
cd /Users/vaibhavthakur/Desktop/python2026/agent-gravity/kie-telegram-video-bot

# 2. Activate virtual environment
source venv/bin/activate

# 3. Run Telegram Bot Daemon
python bot.py
```
