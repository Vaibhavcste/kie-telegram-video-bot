import unittest

from openlux_client import OpenLuxClient, _safe_error


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, post_response=None, get_response=None):
        self.post_response = post_response
        self.get_response = get_response
        self.last_post = None

    def mount(self, *_args, **_kwargs):
        pass

    def post(self, url, **kwargs):
        self.last_post = (url, kwargs)
        return self.post_response

    def get(self, _url, **_kwargs):
        return self.get_response


class OpenLuxClientTests(unittest.TestCase):
    def test_photo_submission_uses_encoded_image_and_compatible_settings(self):
        session = FakeSession(
            post_response=FakeResponse(payload={"code": 0, "data": {"task_id": "photo-task"}})
        )
        client = OpenLuxClient("secret", "https://provider.example", session=session)

        ok, result = client.create_generation_task(
            "kling",
            "animate",
            duration="6",
            aspect_ratio="1:1",
            resolution="480p",
            image_data="YWJj",
        )

        self.assertTrue(ok)
        self.assertEqual(result["task_id"], "photo-task")
        url, request = session.last_post
        self.assertTrue(url.endswith("/image2video"))
        self.assertEqual(request["json"]["image"], "YWJj")
        self.assertEqual(request["json"]["duration"], 5)
        self.assertEqual(request["json"]["aspect_ratio"], "9:16")
        self.assertEqual(request["json"]["resolution"], "720p")

    def test_poll_completed_text_video(self):
        session = FakeSession(
            get_response=FakeResponse(payload={"status": "done", "video": {"url": "https://cdn.example/video.mp4"}})
        )
        client = OpenLuxClient("secret", "https://provider.example", session=session)
        self.assertEqual(
            client.poll_task_status("task", "grok"),
            ("success", "https://cdn.example/video.mp4", None),
        )

    def test_provider_error_does_not_reach_caller(self):
        leaked_key = "sk-" + "super-secret"
        session = FakeSession(post_response=FakeResponse(status_code=401, text=f"bad {leaked_key}"))
        client = OpenLuxClient("secret", "https://provider.example", session=session)
        ok, result = client.create_generation_task("grok", "prompt")
        self.assertFalse(ok)
        self.assertNotIn(leaked_key, result["error"])
        self.assertNotIn("401", result["error"])

    def test_log_error_redacts_known_key_prefixes(self):
        message = "token " + "sk-" + "abcdef and " + "kie-" + "12345"
        self.assertEqual(_safe_error(message), "token [redacted] and [redacted]")


if __name__ == "__main__":
    unittest.main()
