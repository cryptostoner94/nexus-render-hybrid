import os
import re
import signal
import subprocess
import threading
import time
import requests
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

RENDER_URL = os.environ.get("NEXUS_RENDER_URL", "https://nexus-render-hybrid.onrender.com").rstrip("/")

APP = FastAPI(title="NEXUS Mac Control")

connector_proc = None
tunnel_proc = None
tunnel_url = None
logs = []

def log(x):
    logs.append(x)
    if len(logs) > 80:
        logs.pop(0)

@APP.get("/")
def home():
    return HTMLResponse("""
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>NEXUS Mac Connector Control</title>
<style>
body{font-family:Arial;background:#0b0d12;color:white;padding:24px}
button{font-size:18px;padding:14px;border:0;border-radius:12px;margin:8px 0;width:100%}
.on{background:#18a558;color:white}.off{background:#c0392b;color:white}
pre{background:#111827;padding:14px;border-radius:12px;white-space:pre-wrap}
</style>
</head>
<body>
<h1>NEXUS Mac Connector</h1>
<p>Turn ON/OFF from iPhone. It auto-registers with Render.</p>
<button class="on" onclick="start()">Turn ON</button>
<button class="off" onclick="stop()">Turn OFF</button>
<button onclick="status()">Refresh Status</button>
<pre id="out">Loading...</pre>
<script>
async function start(){let r=await fetch('/start',{method:'POST'});document.getElementById('out').textContent=JSON.stringify(await r.json(),null,2)}
async function stop(){let r=await fetch('/stop',{method:'POST'});document.getElementById('out').textContent=JSON.stringify(await r.json(),null,2)}
async function status(){let r=await fetch('/status');document.getElementById('out').textContent=JSON.stringify(await r.json(),null,2)}
status();
setInterval(status,5000);
</script>
</body>
</html>
""")

def read_tunnel_output():
    global tunnel_url
    for line in tunnel_proc.stdout:
        log(line.strip())
        m = re.search(r"https://[-a-zA-Z0-9.]+\\.trycloudflare\\.com", line)
        if m:
            tunnel_url = m.group(0)
            log("Tunnel URL: " + tunnel_url)
            try:
                r = requests.post(
                    RENDER_URL + "/api/connector/register",
                    json={"url": tunnel_url},
                    timeout=20,
                )
                log("Registered to Render: " + r.text)
            except Exception as e:
                log("Register failed: " + str(e))

@APP.post("/start")
def start():
    global connector_proc, tunnel_proc, tunnel_url

    if connector_proc and connector_proc.poll() is None:
        return {
            "running": True,
            "url": tunnel_url,
            "message": "Already running",
            "render": RENDER_URL,
        }

    tunnel_url = None

    connector_proc = subprocess.Popen(
        [
            "python3.11",
            "-m",
            "uvicorn",
            "mac_connector:APP",
            "--host",
            "127.0.0.1",
            "--port",
            "8799",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        preexec_fn=os.setsid,
    )

    time.sleep(3)

    tunnel_proc = subprocess.Popen(
        [
            "cloudflared",
            "tunnel",
            "--url",
            "http://localhost:8799",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        preexec_fn=os.setsid,
    )

    threading.Thread(target=read_tunnel_output, daemon=True).start()

    return {
        "running": True,
        "message": "Starting. Wait 10 seconds, then refresh. Render receives the connector URL automatically.",
        "render": RENDER_URL,
    }

@APP.post("/stop")
def stop():
    global connector_proc, tunnel_proc, tunnel_url

    for p in [tunnel_proc, connector_proc]:
        if p and p.poll() is None:
            os.killpg(os.getpgid(p.pid), signal.SIGTERM)

    try:
        requests.post(RENDER_URL + "/api/connector/clear", timeout=10)
    except Exception:
        pass

    tunnel_proc = None
    connector_proc = None
    tunnel_url = None

    return {"running": False, "message": "Stopped and cleared from Render."}

@APP.get("/status")
def status():
    running = connector_proc is not None and connector_proc.poll() is None
    return {
        "running": running,
        "url": tunnel_url,
        "render": RENDER_URL,
        "logs": logs[-20:],
    }

if __name__ == "__main__":
    uvicorn.run(APP, host="0.0.0.0", port=8800)
