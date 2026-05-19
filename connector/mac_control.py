from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
import os
import requests

APP = FastAPI()

SECRET = os.getenv(
    "MAC_CONNECTOR_SECRET",
    "change-this-secret"
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "llama3"
)

@APP.get("/health")
async def health():
    return {
        "ok": True,
        "service": "mac-connector",
        "model": OLLAMA_MODEL
    }

@APP.post("/api/chat")
async def chat(
    payload: dict,
    x_connector_secret: str = Header(default="")
):

    if x_connector_secret != SECRET:

        return JSONResponse(
            status_code=401,
            content={
                "ok": False,
                "error": "Unauthorized"
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

        return r.json()

    except Exception as e:

        return {
            "ok": False,
            "error": str(e)
        }
