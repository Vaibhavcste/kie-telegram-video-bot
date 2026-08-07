module.exports = {
  apps: [
    {
      name: "kie-telegram-video-bot",
      script: "./venv/bin/python",
      args: "bot.py",
      cwd: "./",
      interpreter: "none",
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      env: {
        PYTHONUNBUFFERED: "1"
      }
    }
  ]
};
