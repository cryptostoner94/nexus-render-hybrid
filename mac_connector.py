import os
import requests
from fastapi import FastAPI
from fastapi.responses import JSONResponse

APP = FastAPI(title="NEXUS Private Mac Connector")

OLLAMA = "http://localhost:11434/api/chat"
MODEL = os.environ.get("NEXUS_MODEL", "llama3.2:3b")

@APP.get("/api/health")
def health():
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        return {"ok": True, "ollama": r.ok, "model": MODEL}
    except Exception as e:
        return {"ok": False, "ollama": False, "error": str(e)}

@APP.post("/api/chat")
def chat(payload: dict):
    prompt = payload.get("prompt", "").strip()
    if not prompt:
        return JSONResponse({"error": "Empty prompt"}, status_code=400)

    r = requests.post(
        OLLAMA,
        json={
            "model": MODEL,
            "stream": False,
            "messages": [
                {
                    "role": "system",
                    "content": "You are the user's private Mac Ollama assistant. Keep private data local. Be practical and concise."
                },
                {"role": "user", "content": prompt},
            ],
        },
        timeout=240,
    )
    r.raise_for_status()
    return {
        "model": MODEL,
        "answer": r.json()["message"]["content"],
    }
