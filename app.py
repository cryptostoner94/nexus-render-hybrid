import os
import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

APP = FastAPI(title="NEXUS Render Hybrid")

CONNECTOR = {"url": ""}

PROVIDER_ORDER = [
    "openai",
    "gemini",
    "groq",
    "openrouter",
    "together",
    "fireworks",
]

def openai_compatible(provider, url, key, model, prompt):
    r = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are NEXUS Cloud AI. Be practical, direct, and do not claim you performed actions unless a tool actually did them."
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
        },
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    return {
        "provider": provider,
        "model": model,
        "answer": data["choices"][0]["message"]["content"],
    }

def gemini_chat(prompt):
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing")
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    r = requests.post(
        url,
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    return {
        "provider": "gemini",
        "model": model,
        "answer": data["candidates"][0]["content"]["parts"][0]["text"],
    }

def cloud_fallback(prompt):
    errors = []

    for provider in PROVIDER_ORDER:
        try:
            if provider == "openai":
                key = os.getenv("OPENAI_API_KEY", "").strip()
                if not key:
                    continue
                return openai_compatible(
                    "openai",
                    "https://api.openai.com/v1/chat/completions",
                    key,
                    os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                    prompt,
                )

            if provider == "gemini":
                if not os.getenv("GEMINI_API_KEY", "").strip():
                    continue
                return gemini_chat(prompt)

            if provider == "groq":
                key = os.getenv("GROQ_API_KEY", "").strip()
                if not key:
                    continue
                return openai_compatible(
                    "groq",
                    "https://api.groq.com/openai/v1/chat/completions",
                    key,
                    os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"),
                    prompt,
                )

            if provider == "openrouter":
                key = os.getenv("OPENROUTER_API_KEY", "").strip()
                if not key:
                    continue
                return openai_compatible(
                    "openrouter",
                    "https://openrouter.ai/api/v1/chat/completions",
                    key,
                    os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free"),
                    prompt,
                )

            if provider == "together":
                key = os.getenv("TOGETHER_API_KEY", "").strip()
                if not key:
                    continue
                return openai_compatible(
                    "together",
                    "https://api.together.xyz/v1/chat/completions",
                    key,
                    os.getenv("TOGETHER_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"),
                    prompt,
                )

            if provider == "fireworks":
                key = os.getenv("FIREWORKS_API_KEY", "").strip()
                if not key:
                    continue
                return openai_compatible(
                    "fireworks",
                    "https://api.fireworks.ai/inference/v1/chat/completions",
                    key,
                    os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/llama-v3p1-8b-instruct"),
                    prompt,
                )

        except Exception as e:
            errors.append(f"{provider}: {str(e)}")

    return {
        "provider": "none",
        "answer": "No cloud fallback provider succeeded. Add or correct API keys in Render Environment Variables.",
        "errors": errors,
    }

@APP.get("/")
def home():
    return HTMLResponse("""
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NEXUS Render Hybrid</title>
<style>
body{background:#0b0d12;color:white;font-family:Arial;padding:24px}
textarea,input,button{width:100%;padding:12px;margin:8px 0;font-size:16px;border-radius:10px}
button{background:#4f7cff;color:white;border:0}
pre{background:#111827;padding:12px;border-radius:10px;white-space:pre-wrap}
.card{background:#151925;border:1px solid #2b3040;border-radius:14px;padding:14px;margin:14px 0}
</style>
</head>
<body>
<h1>NEXUS Render Hybrid</h1>
<p>Static cloud dashboard. Mac connector auto-registers when turned ON.</p>

<div class="card">
<h3>Connector Status</h3>
<button onclick="status()">Check Connector Status</button>
<pre id="status"></pre>
</div>

<div class="card">
<h3>AI Task</h3>
<textarea id="prompt" rows="8" placeholder="Ask your task here..."></textarea>
<button onclick="ask()">Run AI</button>
<pre id="out"></pre>
</div>

<div class="card">
<h3>Provider Status</h3>
<button onclick="providers()">Check Providers</button>
<pre id="providers"></pre>
</div>

<script>
async function status(){
 const r=await fetch('/api/connector/status');
 document.getElementById('status').textContent=JSON.stringify(await r.json(),null,2);
}
async function ask(){
 const prompt=document.getElementById('prompt').value;
 const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})});
 document.getElementById('out').textContent=JSON.stringify(await r.json(),null,2);
}
async function providers(){
 const r=await fetch('/api/providers');
 document.getElementById('providers').textContent=JSON.stringify(await r.json(),null,2);
}
status();
providers();
</script>
</body>
</html>
""")

@APP.get("/health")
def health():
    return {"ok": True, "service": "nexus-render-hybrid"}

@APP.get("/api/health")
def api_health():
    return {"ok": True, "service": "nexus-render-hybrid"}

@APP.get("/api/providers")
def providers():
    return {
        "openai": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "gemini": bool(os.getenv("GEMINI_API_KEY", "").strip()),
        "groq": bool(os.getenv("GROQ_API_KEY", "").strip()),
        "openrouter": bool(os.getenv("OPENROUTER_API_KEY", "").strip()),
        "together": bool(os.getenv("TOGETHER_API_KEY", "").strip()),
        "fireworks": bool(os.getenv("FIREWORKS_API_KEY", "").strip()),
    }

@APP.post("/api/connector/register")
def register_connector(payload: dict):
    url = payload.get("url", "").strip().rstrip("/")
    if not url.startswith("https://"):
        return {"ok": False, "error": "Invalid connector URL"}
    CONNECTOR["url"] = url
    return {"ok": True, "registered_url": CONNECTOR["url"]}

@APP.post("/api/connector/clear")
def clear_connector():
    CONNECTOR["url"] = ""
    return {"ok": True, "message": "Connector cleared"}

@APP.get("/api/connector/status")
def connector_status():
    return {
        "registered": bool(CONNECTOR["url"]),
        "url": CONNECTOR["url"] if CONNECTOR["url"] else None,
    }

@APP.post("/api/chat")
def chat(payload: dict):
    prompt = payload.get("prompt", "").strip()
    if not prompt:
        return {"error": "Empty prompt"}

    if CONNECTOR["url"]:
        try:
            r = requests.post(
                CONNECTOR["url"] + "/api/chat",
                json={"prompt": prompt},
                timeout=240,
            )
            return {
                "mode": "mac-ollama",
                "connector": "auto-registered",
                "result": r.json(),
            }
        except Exception as e:
            CONNECTOR["url"] = ""
            fallback = cloud_fallback(prompt)
            return {
                "mode": "mac-connector-failed-cloud-fallback-used",
                "connector_error": str(e),
                "result": fallback,
            }

    return {
        "mode": "cloud-fallback",
        "result": cloud_fallback(prompt),
    }
