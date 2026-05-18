from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from pathlib import Path
import datetime, sqlite3, requests

APP = FastAPI(title="NEXUS Render Hybrid")

DATA = Path("/tmp/nexus_data")
UPLOADS = DATA / "uploads"
DATA.mkdir(exist_ok=True)
UPLOADS.mkdir(exist_ok=True)
DB = DATA / "memory.sqlite"

def db():
    c = sqlite3.connect(DB)
    c.execute("CREATE TABLE IF NOT EXISTS memory(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, title TEXT, content TEXT, created_at TEXT)")
    c.commit()
    return c

def remember(kind, title, content):
    c = db()
    c.execute("INSERT INTO memory(kind,title,content,created_at) VALUES(?,?,?,?)", (kind, title, content, datetime.datetime.utcnow().isoformat()))
    c.commit()
    c.close()

@APP.get("/")
def home():
    return HTMLResponse("""
    <html>
    <head><meta name="viewport" content="width=device-width,initial-scale=1"></head>
    <body style="background:#0b0d12;color:white;font-family:Arial;padding:30px;">
    <h1>NEXUS Render Hybrid</h1>
    <p>Status: Cloud runtime active.</p>
    <p>Use Mac connector only when private Ollama/iCloud storage is needed.</p>

    <h3>Mac Connector URL</h3>
    <input id="mac" style="width:100%;padding:12px;" placeholder="https://xxxx.trycloudflare.com">

    <h3>Ask Private Mac Ollama</h3>
    <textarea id="prompt" style="width:100%;height:120px;padding:12px;"></textarea>
    <button onclick="ask()">Ask Mac</button>
    <pre id="out"></pre>

    <script>
    async function ask(){
      const mac_url=document.getElementById('mac').value;
      const prompt=document.getElementById('prompt').value;
      const r=await fetch('/api/mac/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mac_url,prompt})});
      document.getElementById('out').textContent=JSON.stringify(await r.json(),null,2);
    }
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

@APP.post("/api/mac/chat")
def mac_chat(payload: dict):
    mac_url = payload.get("mac_url", "").rstrip("/")
    prompt = payload.get("prompt", "")
    if not mac_url:
        return {"error": "Mac connector is OFF. Start it only when needed."}
    r = requests.post(mac_url + "/api/chat", json={"prompt": prompt}, timeout=240)
    remember("mac-chat", prompt[:80], r.text[:4000])
    return r.json()

@APP.get("/api/memory")
def memory():
    c = db()
    rows = c.execute("SELECT kind,title,content,created_at FROM memory ORDER BY id DESC LIMIT 50").fetchall()
    c.close()
    return {"items":[{"kind":k,"title":t,"content":ct,"created_at":d} for k,t,ct,d in rows]}
