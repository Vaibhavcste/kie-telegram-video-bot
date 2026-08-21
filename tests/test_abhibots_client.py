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

    def test_veo_uses_dedicated_endpoint(self):
        session = FakeSession([FakeResponse(payload={"data": {"taskId": "veo-1"}})])
        client = AbhiBotsClient("secret", "https://vgen.example", session=session)
        ok, result = client.create_generation_task("veo3_fast", "A cinematic river")
        self.assertTrue(ok)
        self.assertEqual(result["endpoint_type"], "veo")
        self.assertTrue(session.calls[0][1].endswith("/api/v1/veo/generate"))
        self.assertEqual(session.calls[0][2]["json"]["model"], "veo3_fast")

    def test_runway_uses_dedicated_endpoint(self):
        session = FakeSession([FakeResponse(payload={"id": "runway-1"})])
        client = AbhiBotsClient("secret", "https://vgen.example", session=session)
        ok, result = client.create_generation_task("runway", "A studio product shot", resolution="1080p")
        self.assertTrue(ok)
        self.assertEqual(result["endpoint_type"], "runway")
        self.assertTrue(session.calls[0][1].endswith("/api/v1/runway/generate"))
        self.assertEqual(session.calls[0][2]["json"]["quality"], "1080p")

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
        self.assertEqual(request["model"], "kling-2.6/image-to-video")
        self.assertEqual(request["input"]["image_url"], "https://cdn.example/image.jpg")
        self.assertFalse(request["input"]["sound"])

    def test_seedance_photo_uses_image_urls(self):
        session = FakeSession(
            [
                FakeResponse(payload={"url": "https://cdn.example/image.jpg"}),
                FakeResponse(payload={"data": {"taskId": "seedance-1"}}),
            ]
        )
        client = AbhiBotsClient("secret", "https://vgen.example", session=session)
        image_data = base64.b64encode(b"jpeg-bytes").decode("ascii")
        ok, _ = client.create_generation_task("seedance2", "Animate", resolution="4k", image_data=image_data)
        self.assertTrue(ok)
        request = session.calls[1][2]["json"]
        self.assertEqual(request["input"]["image_urls"], ["https://cdn.example/image.jpg"])
        self.assertEqual(request["input"]["resolution"], "4k")

    def test_successful_poll_extracts_video(self):
        session = FakeSession(
            [FakeResponse(payload={"data": {"state": "success", "resultJson": {"resultUrls": ["https://cdn.example/video.mp4"]}}})]
        )
        client = AbhiBotsClient("secret", "https://vgen.example", session=session)
        self.assertEqual(
            client.poll_task_status("job-3", "jobs"),
            ("success", "https://cdn.example/video.mp4", None),
        )

    def test_poll_uses_endpoint_specific_path(self):
        session = FakeSession([FakeResponse(payload={"data": {"state": "waiting"}})])
        client = AbhiBotsClient("secret", "https://vgen.example", session=session)
        self.assertEqual(client.poll_task_status("veo-1", "veo"), ("processing", None, None))
        self.assertTrue(session.calls[0][1].endswith("/api/v1/veo/record-info"))


if __name__ == "__main__":
    unittest.main()
