import base64
import unittest

from abhibots_client import AbhiBotsClient


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def mount(self, *_args, **_kwargs):
        pass

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self.responses.pop(0)

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self.responses.pop(0)


class AbhiBotsClientTests(unittest.TestCase):
    def test_text_job_submission(self):
        session = FakeSession([FakeResponse(payload={"data": {"taskId": "job-1"}})])
        client = AbhiBotsClient("secret", "https://vgen.example", session=session)
        ok, result = client.create_generation_task("grok", "A cinematic sunrise", duration="6")
        self.assertTrue(ok)
        self.assertEqual(result["task_id"], "job-1")
        request = session.calls[0][2]["json"]
        self.assertEqual(request["model"], "grok-imagine-video-1-5-preview")
        self.assertNotIn("image_url", request["input"])

    def test_photo_is_uploaded_before_job_submission(self):
        session = FakeSession(
            [
                FakeResponse(payload={"data": {"url": "https://cdn.example/image.jpg"}}),
                FakeResponse(payload={"data": {"taskId": "job-2"}}),
            ]
        )
        client = AbhiBotsClient("secret", "https://vgen.example", session=session)
        image_data = base64.b64encode(b"jpeg-bytes").decode("ascii")
        ok, result = client.create_generation_task("kling", "Animate naturally", image_data=image_data)
        self.assertTrue(ok)
        self.assertEqual(result["task_id"], "job-2")
        self.assertTrue(session.calls[0][1].endswith("/api/v1/upload"))
        request = session.calls[1][2]["json"]
        self.assertEqual(request["input"]["image_url"], "https://cdn.example/image.jpg")
        self.assertFalse(request["input"]["sound"])

    def test_successful_poll_extracts_video(self):
        session = FakeSession(
            [FakeResponse(payload={"data": {"state": "success", "resultJson": {"resultUrls": ["https://cdn.example/video.mp4"]}}})]
        )
        client = AbhiBotsClient("secret", "https://vgen.example", session=session)
        self.assertEqual(
            client.poll_task_status("job-3", "jobs"),
            ("success", "https://cdn.example/video.mp4", None),
        )


if __name__ == "__main__":
    unittest.main()
