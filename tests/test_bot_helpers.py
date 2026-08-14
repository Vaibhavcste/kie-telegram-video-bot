import unittest
from unittest.mock import patch

import bot


class BotHelperTests(unittest.TestCase):
    def setUp(self):
        with bot.job_lock:
            bot.active_jobs.clear()

    def test_access_is_fail_closed(self):
        with patch.object(bot, "ALLOWED_USER_IDS", []):
            self.assertFalse(bot.is_user_allowed(123))

    def test_job_gate_limits_one_job_per_user(self):
        with patch.object(bot, "MAX_CONCURRENT_JOBS", 3), patch.object(bot, "MAX_JOBS_PER_USER", 1):
            self.assertTrue(bot._claim_job(1))
            self.assertFalse(bot._claim_job(1))
            self.assertTrue(bot._claim_job(2))
            bot._release_job(1)
            self.assertTrue(bot._claim_job(1))

    def test_caption_contains_no_provider_or_task_details(self):
        caption = bot.format_caption("A cinematic sunrise", {"duration": "5", "aspect_ratio": "9:16", "resolution": "720p"})
        self.assertNotIn("Model", caption)
        self.assertNotIn("Task", caption)
        self.assertIn("Output", caption)


if __name__ == "__main__":
    unittest.main()
