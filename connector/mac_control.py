from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
import os
import requests

APP = FastAPI()

SECRET = os.getenv(
    "MAC_CONNECTOR_SECRET",
    ""
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "llama3"
)

@APP.get("/health")
async def health():
    try:
        requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
        ollama = "online"
    except:
        ollama = "offline"
    return {
        "ok": True,
        "service": "mac-connector",
        "model": OLLAMA_MODEL,
        "ollama": ollama
    }

@APP.post("/api/chat")
async def chat(
    payload: dict,
    x_connector_secret: str = Header(default="")
):

    if SECRET and x_connector_secret != SECRET:

        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "error": "Unauthorized: x-connector-secret header invalid or missing."
            }
        )

    prompt = payload.get("prompt", "")

    try:

        r = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            },
            timeout=240
        )

        data = r.json()
        return {
            "model": OLLAMA_MODEL,
            "answer": data.get("response", "")
        }

    except Exception as e:

        return {
            "ok": False,
            "error": str(e)
        }
