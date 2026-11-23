import os
import json
import urllib.request
import urllib.error

API_KEY = os.environ["GEMINI_API_KEY"]
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={API_KEY}"

payload = {
    "contents": [
        {
            "parts": [
                {"text": "Hello, respond with JSON: {'status': 'ok'}"}
            ]
        }
    ],
    "generationConfig": {
        "responseMimeType": "application/json",
        "temperature": 0.1,
    },
}

req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        print("Response body:")
        print(json.dumps(body, indent=2))
except Exception as e:
    print("Error:", e)
    if hasattr(e, "read"):
        print(e.read().decode("utf-8"))
