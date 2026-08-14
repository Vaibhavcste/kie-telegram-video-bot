# AbhiBots KIE Video API — Legacy Backup & Documentation

This document contains the complete configuration, API endpoints, payload formats, and credentials for the legacy **AbhiBots KIE API** previously used by the Telegram bot (`@csteinternalvideobot`).

---

## 🔑 Credentials & Base URLs

* **Base URL**: `https://vgen.abhibots.com` (redirects to `https://kie.abhibots.com`)
* **Legacy API Key**: `kie-e3a1c2dceb29a009a4309697122339e8`
* **Auth Header**: `Authorization: Bearer kie-e3a1c2dceb29a009a4309697122339e8`

---

## 📡 Legacy Endpoints Reference

### 1. Account & Balance
* **GET** `/api/v1/balance`
  - Response: `{"balance": 12.1231, "currency": "USD", "balance_inr": 1212}`

### 2. File Upload
* **POST** `/api/v1/upload` (`multipart/form-data` with field `"file"`)
  - Response: `{"url": "https://tempfile.redpandaai.co/kieai/.../image.png"}`

### 3. Task Creation Endpoints
* **Jobs API (Grok, Seedance, Kling, Hailuo, Gemini Omni)**:
  - **POST** `/api/v1/jobs/createTask`
  - Payload:
    ```json
    {
      "model": "grok-imagine-video-1-5-preview",
      "input": {
        "prompt": "...",
        "duration": "6",
        "aspect_ratio": "16:9"
      }
    }
    ```
* **Veo 3 / Veo 3 Fast**:
  - **POST** `/api/v1/veo/generate`
  - Payload: `{"prompt": "...", "model": "veo3"|"veo3_fast", "duration": 8, "aspectRatio": "16:9", "resolution": "720p"}`
* **Runway Gen-4**:
  - **POST** `/api/v1/runway/generate`
  - Payload: `{"prompt": "...", "quality": "720p", "duration": "5"}`
* **OpenAI GPT Image 2**:
  - **POST** `/api/v1/openai/generate` & `/edit`

### 4. Status Polling Endpoints
* **Jobs API**: **GET** `/api/v1/jobs/recordInfo?taskId=TASK_ID`
* **Veo API**: **GET** `/api/v1/veo/record-info?taskId=TASK_ID`
* **Runway API**: **GET** `/api/v1/runway/record-detail?taskId=TASK_ID`

---

## 🤖 Supported Models Dictionary (AbhiBots Legacy)

```python
MODELS = {
    "grok": {
        "name": "xAI Grok Video 1.5",
        "api_model": "grok-imagine-video-1-5-preview",
        "endpoint_type": "jobs",
        "durations": ["6", "10", "15"],
        "default_duration": "6",
        "aspect_ratios": ["16:9", "9:16"],
        "default_aspect_ratio": "16:9",
        "resolutions": ["720p", "1080p"],
        "pricing": "$0.007/s"
    },
    "seedance2": {
        "name": "ByteDance Seedance 2.0",
        "api_model": "bytedance/seedance-2",
        "endpoint_type": "jobs",
        "pricing": "$0.035/s"
    },
    "veo3": {
        "name": "Google Veo 3",
        "api_model": "veo3",
        "endpoint_type": "veo",
        "pricing": "$0.28 flat"
    },
    "kling": {
        "name": "Kuaishou Kling 2.6",
        "api_model": "kling-2.6/text-to-video",
        "api_model_i2v": "kling-2.6/image-to-video",
        "endpoint_type": "jobs",
        "pricing": "$0.03/s"
    }
}
```
