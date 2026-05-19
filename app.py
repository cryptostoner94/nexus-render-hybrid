import os
import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

APP = FastAPI(title="Agentflow Relay", version="11.1.0")

def has(name):
    return bool(os.getenv(name, "").strip())

@APP.get("/")
def home():
    return HTMLResponse("""
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agentflow Relay</title>
<style>
body{font-family:Arial;background:#0b0d12;color:white;padding:24px}
.card{background:#151925;border:1px solid #2b3040;border-radius:14px;padding:16px;margin:14px 0}
textarea,button{width:100%;font-size:16px;padding:12px;margin-top:8px;border-radius:10px}
button{background:#4f7cff;color:white;border:0}
pre{white-space:pre-wrap;background:#090b10;padding:12px;border-radius:10px}
</style>
</head>
<body>
<h1>Agentflow Relay</h1>
<div class="card">
<h3>Provider Status</h3>
<button onclick="providers()">Check Providers</button>
<pre id="providers"></pre>
</div>
<div class="card">
<h3>Chat</h3>
<textarea id="prompt" rows="7" placeholder="Ask anything..."></textarea>
<button onclick="chat()">Run</button>
<pre id="out"></pre>
</div>
<script>
async function providers(){
 const r=await fetch('/api/providers');
 document.getElementById('providers').textContent=JSON.stringify(await r.json(),null,2);
}
async function chat(){
 const prompt=document.getElementById('prompt').value;
 const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})});
 document.getElementById('out').textContent=JSON.stringify(await r.json(),null,2);
}
providers();
</script>
</body>
</html>
""")

@APP.get("/health")
def health():
    return {"ok": True, "service": "agentflow-relay", "version": "11.1.0"}

@APP.get("/api/health")
def api_health():
    return health()

@APP.get("/api/providers")
def providers():
    return {
        "gemini": has("GEMINI_API_KEY") or has("GOOGLE_API_KEY"),
        "groq": has("GROQ_API_KEY"),
        "openrouter": has("OPENROUTER_API_KEY"),
        "together": has("TOGETHER_API_KEY"),
        "fireworks": has("FIREWORKS_API_KEY"),
        "mac_connector": has("MAC_CONNECTOR_URL"),
        "mac_connector_secret": has("MAC_CONNECTOR_SECRET"),
        "openai_disabled": True
    }

def cloud_fallback(prompt):
    return {
        "provider": "cloud-fallback",
        "answer": "Provider route is installed. Add/verify API keys in Render and redeploy. Use /api/providers to confirm active providers."
    }

@APP.post("/api/chat")
def chat(payload: dict):
    prompt = payload.get("prompt", "").strip()
    if not prompt:
        return {"error": "Empty prompt"}

    mac_url = os.getenv("MAC_CONNECTOR_URL", "").strip().rstrip("/")
    secret = os.getenv("MAC_CONNECTOR_SECRET", "").strip()

    if mac_url:
        try:
            r = requests.post(
                mac_url + "/api/chat",
                json={"prompt": prompt},
                headers={"x-connector-secret": secret},
                timeout=240
            )
            return {"mode": "mac-connector", "result": r.json()}
        except Exception as e:
            return {"mode": "mac-failed", "error": str(e), "fallback": cloud_fallback(prompt)}

    return {"mode": "cloud", "result": cloud_fallback(prompt)}
