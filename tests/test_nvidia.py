import os
import json
import urllib.request
import urllib.error

API_KEY = os.environ["NVIDIA_API_KEY"]
url = "https://integrate.api.nvidia.com/v1/chat/completions"

payload = {
    "model": "meta/llama-3.2-11b-vision-instruct",
    "messages": [
        {"role": "user", "content": "Hello, respond with JSON: {\"status\": \"ok\"}"}
    ],
    "temperature": 0.1,
    "max_tokens": 1000,
    "response_format": {"type": "json_object"}
}

req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    },
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        print("Response body:")
        print(json.dumps(body, indent=2))
except Exception as e:
    print("Error:", e)
    if hasattr(e, "read"):
        print(e.read().decode("utf-8"))
