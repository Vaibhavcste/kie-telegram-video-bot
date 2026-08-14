# Team Video Studio Telegram Bot

A private Telegram bot for creating short AI videos from text prompts and animating uploaded photos. The Telegram experience is intentionally provider-neutral: team members choose only duration, format, and output quality. Provider names, account balances, wholesale pricing, credentials, and raw API errors stay on the server.

## User experience

- Send a text prompt to create a video.
- Send a photo with a caption to animate it.
- Use `/settings` to choose duration, aspect ratio, and quality.
- Use `/history` to view recent team jobs without provider or billing details.
- Text and photo requests are routed automatically to compatible rendering backends.

## Reliability and security

- Fail-closed Telegram user allowlist.
- Separate administrator allowlist; access cannot be changed from chat.
- No credentials or fallback secrets in source control.
- Bounded global and per-user concurrency.
- Validated prompts and output parameters.
- Retry/backoff for safe status requests; paid job submissions are never blindly retried.
- Generic user-facing failures with detailed server-side logs.
- Atomic settings and history writes.
- Size-limited image intake and video delivery.
- Photos are transferred as encoded data, so Telegram bot credentials are never embedded in provider-visible URLs.

## Setup

Requires Python 3.10+.

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`, then run:

```bash
python bot.py
```

For PM2:

```bash
pm2 start ecosystem.config.cjs
pm2 logs kie-telegram-video-bot
```

## Commands

- `/start`, `/help` — usage and current output preset
- `/settings` — duration, format, and quality controls
- `/generate <prompt>` — explicit generation command, useful in groups
- `/history`, `/usage` — recent team generation activity
- `/id`, `/myid` — show the caller's Telegram user ID
- `/listusers`, `/addid` — admin-only guidance; deployment access remains environment-managed

## Deployment notes

- Rotate every credential that has ever appeared in repository history, documentation, chat, or logs.
- Keep `.env`, `user_settings.json`, and `generation_history.json` outside source control and on persistent storage.
- Configure Telegram's BotFather command list without provider, model, balance, or pricing commands if you want them absent from command suggestions.
- The current local JSON state is suitable for a small internal team. Before public resale, replace it with a transactional database and durable job queue, add tenant isolation and quotas, and deliver completed jobs from a worker process.

Run checks with:

```bash
python -m unittest discover -s tests -v
```
