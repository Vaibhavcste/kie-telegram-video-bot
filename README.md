# Team Video Studio Telegram Bot

A private Telegram bot for creating short AI videos from text prompts and animating uploaded photos. AbhiBots deployments expose a capability-aware video-model selector; OpenLux deployments route internally. Account balances, wholesale pricing, credentials, and raw API errors stay on the server.

## User experience

- Send a text prompt to create a video.
- Send a photo with a caption to animate it.
- On AbhiBots deployments, use `/models` to choose among nine supported video engines.
- Use `/settings` to choose duration, aspect ratio, and quality.
- Use `/history` to view recent team jobs without provider or billing details.
- Text and photo requests are validated and routed only to compatible rendering endpoints.

The AbhiBots selector includes xAI Grok Video 1.5, ByteDance Seedance 1.5 Pro,
ByteDance Seedance 2.0, Google Veo 3, Google Veo 3 Fast, Runway Gen-4,
Kuaishou Kling 2.6, MiniMax Hailuo 02, and Google Gemini Omni Video. Account
and billing details are never shown in Telegram.

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

For an isolated AbhiBots-backed instance, set `VIDEO_PROVIDER=abhibots` and
provide `ABHIBOTS_API_KEY` instead of `OPENLUX_API_KEY`. Keep each Telegram bot
in a separate service with its own `TELEGRAM_BOT_TOKEN` and persistent data
directory.

## Commands

- `/start`, `/help` — usage and current output preset
- `/models` — choose a video model on AbhiBots deployments
- `/settings` — duration, format, and quality controls
- `/generate <prompt>` — explicit generation command, useful in groups
- `/history`, `/usage` — recent team generation activity
- `/id`, `/myid` — show the caller's Telegram user ID
- `/listusers`, `/addid` — admin-only guidance; deployment access remains environment-managed

## Deployment notes

- Rotate every credential that has ever appeared in repository history, documentation, chat, or logs.
- Keep `.env`, `user_settings.json`, and `generation_history.json` outside source control and on persistent storage.
- The bot registers its safe command list with Telegram at startup; balance and pricing commands are never registered.
- The current local JSON state is suitable for a small internal team. Before public resale, replace it with a transactional database and durable job queue, add tenant isolation and quotas, and deliver completed jobs from a worker process.

Run checks with:

```bash
python -m unittest discover -s tests -v
```
