import os, json, sqlite3, datetime, uuid, requests, logging
from pathlib import Path
from collections import deque
from bs4 import BeautifulSoup
from fastapi import FastAPI, UploadFile, File, Header
from fastapi.responses import HTMLResponse, JSONResponse

# Setup Logging for Render and UI
LOGS = deque(maxlen=100)

# Global for dynamic Mac Connector registration if tunnel is used
DYNAMIC_CONNECTOR = {"url": None}

APP = FastAPI(title="Nexus Render Hybrid", version="12.0.0")

DATA = Path("/tmp/nexus_product")
UPLOADS = DATA / "uploads"
DATA.mkdir(exist_ok=True)
UPLOADS.mkdir(exist_ok=True)
DB = DATA / "nexus.db"

DEFAULT_SKILLS = [
    {"id":"skill-creator","name":"skill-creator","desc":"Create and update specialized reusable skills.","enabled":True},
    {"id":"manus-api","name":"manus-api","desc":"Manage tasks, projects, and automation through API-style actions.","enabled":True},
    {"id":"github-gem-seeker","name":"github-gem-seeker","desc":"Search GitHub-style solutions and avoid reinventing the wheel.","enabled":True},
    {"id":"internet-skill-finder","name":"internet-skill-finder","desc":"Recommend agent skills from public patterns and repositories.","enabled":True},
    {"id":"stock-analysis","name":"stock-analysis ✨","desc":"Analyze companies, tickers, financial narratives, and risks.","enabled":True},
    {"id":"similarweb-analytics","name":"similarweb-analytics ✨","desc":"Analyze websites, domains, traffic logic, and competitive positioning.","enabled":True},
    {"id":"excel-generator","name":"excel-generator","desc":"Create spreadsheet structures, formulas, tables, and CSV-ready outputs.","enabled":True},
    {"id":"video-generator","name":"video-generator","desc":"Plan scripts, shots, prompts, edits, shorts, ads, and video workflows.","enabled":True},
    {"id":"music-prompter","name":"music-prompter","desc":"Craft music-generation prompts and song direction workflows.","enabled":True},
    {"id":"browser-operator","name":"browser-operator","desc":"Fetch, inspect, summarize, and extract website content.","enabled":True},
    {"id":"wide-research","name":"wide-research","desc":"Perform structured multi-source research planning and synthesis.","enabled":True},
    {"id":"website-builder","name":"website-builder","desc":"Generate website/app structures, landing pages, and deployment plans.","enabled":True},
    {"id":"spreadsheet-generator","name":"spreadsheet-generator","desc":"Automate complex data organization and analysis.","enabled":True},
    {"id":"audio-generator","name":"audio-generator","desc":"Advanced music and speech synthesis workflows.","enabled":True},
    {"id":"playbook-builder","name":"playbook-builder","desc":"Create autonomous agent step-by-step instruction sets.","enabled":True},
]

CONNECTORS = [
    {"id":"gmail","name":"Gmail","kind":"connector","enabled":False},
    {"id":"google-drive","name":"Google Drive","kind":"connector","enabled":False},
    {"id":"github","name":"GitHub","kind":"connector","enabled":True},
    {"id":"my-browser","name":"My Browser","kind":"connector","enabled":True},
    {"id":"outlook-mail","name":"Outlook Mail","kind":"connector","enabled":False},
    {"id":"outlook-calendar","name":"Outlook Calendar","kind":"connector","enabled":False},
    {"id":"google-calendar","name":"Google Calendar","kind":"connector","enabled":False},
    {"id":"instagram-creator","name":"Instagram Creator","kind":"connector","enabled":False},
    {"id":"meta-ads","name":"Meta Ads Manager","kind":"connector","enabled":False},
    {"id":"mac-connector","name":"Mac Connector / Ollama Vault","kind":"connector","enabled":bool(os.getenv("MAC_CONNECTOR_URL") or DYNAMIC_CONNECTOR["url"])},
]

INTEGRATIONS = [
    {"id":"telegram","name":"Telegram","enabled":bool(os.getenv("TELEGRAM_BOT_TOKEN","").strip())},
    {"id":"slack","name":"Slack","enabled":False},
    {"id":"line","name":"LINE","enabled":False},
]

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def log_event(msg, level="INFO"):
    entry = {"time": now(), "level": level, "message": msg}
    LOGS.appendleft(entry)
    if level == "ERROR":
        logging.error(msg)
    else:
        logging.info(msg)

def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS memory(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, title TEXT, content TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, title TEXT, prompt TEXT, status TEXT, result TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS schedules(id TEXT PRIMARY KEY, title TEXT, prompt TEXT, cadence TEXT, enabled INTEGER, created_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS files(id TEXT PRIMARY KEY, name TEXT, type TEXT, content TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS websites(id TEXT PRIMARY KEY, title TEXT, html TEXT, created_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    return conn

def remember(kind,title,content):
    c=db()
    c.execute("INSERT INTO memory(kind,title,content,created_at) VALUES(?,?,?,?)",(kind,title,content,now()))
    c.commit(); c.close()

def active(name):
    return bool(os.getenv(name,"").strip())

def providers():
    return {
        "gemini": active("GEMINI_API_KEY") or active("GOOGLE_API_KEY"),
        "google": active("GOOGLE_API_KEY"),
        "groq": active("GROQ_API_KEY"),
        "openrouter": active("OPENROUTER_API_KEY"),
        "together": active("TOGETHER_API_KEY"),
        "fireworks": active("FIREWORKS_API_KEY"),
        "mac_connector": active("MAC_CONNECTOR_URL") or bool(DYNAMIC_CONNECTOR["url"]),
        "mac_connector_secret": active("MAC_CONNECTOR_SECRET") or bool(os.getenv("MAC_CONNECTOR_SECRET")),
        "openai_disabled": True
    }

def openai_compatible(provider,url,key,model,prompt):
    log_event(f"Attempting {provider} with model {model}")
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://nexus-render-hybrid.onrender.com",
        "X-Title": "Nexus Render Hybrid"
    }
    payload = {
        "model":model,
        "messages":[
            {"role":"system","content":"You are Nexus Render Hybrid: a practical autonomous agent. Be precise, useful, and never claim external actions unless completed."},
            {"role":"user","content":prompt}
        ]
    }
    r=requests.post(url, headers=headers, json=payload, timeout=120)
    r.raise_for_status()
    data=r.json()
    log_event(f"Success: {provider} responded.")
    return {"provider":provider,"model":model,"answer":data["choices"][0]["message"]["content"]}

def gemini(prompt):
    log_event("Attempting Gemini...")
    key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    model=os.getenv("GEMINI_MODEL", "").strip()
    
    # Sanity check: Ensure model is valid and not truncated to 'gemini-'
    if not model or model == "gemini-":
        model = "gemini-1.5-flash"
        
    r=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",json={
        "contents":[{"parts":[{"text":prompt}]}]
    },timeout=120)
    r.raise_for_status()
    data=r.json()
    log_event("Success: Gemini responded.")
    return {"provider":"gemini","model":model,"answer":data["candidates"][0]["content"]["parts"][0]["text"]}

def cloud_ai(prompt):
    errors=[]
    order=[
        ("gemini",lambda: gemini(prompt)),
        ("groq",lambda: openai_compatible("groq","https://api.groq.com/openai/v1/chat/completions",os.getenv("GROQ_API_KEY"),os.getenv("GROQ_MODEL","llama-3.1-8b-instant"),prompt)),
        ("openrouter",lambda: openai_compatible("openrouter","https://openrouter.ai/api/v1/chat/completions",os.getenv("OPENROUTER_API_KEY"),os.getenv("OPENROUTER_MODEL","meta-llama/llama-3.1-8b-instruct:free"),prompt)),
        ("together",lambda: openai_compatible("together","https://api.together.xyz/v1/chat/completions",os.getenv("TOGETHER_API_KEY"),os.getenv("TOGETHER_MODEL","meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"),prompt)),
        ("fireworks",lambda: openai_compatible("fireworks","https://api.fireworks.ai/inference/v1/chat/completions",os.getenv("FIREWORKS_API_KEY"),os.getenv("FIREWORKS_MODEL","accounts/fireworks/models/llama-v3p1-8b-instruct"),prompt)),
    ]
    for name,fn in order:
        if not providers().get(name): continue
        try: return fn()
        except Exception as e:
            err_msg = f"{name} failed: {str(e)[:100]}"
            errors.append(err_msg)
            log_event(err_msg, "ERROR")
    log_event("All cloud providers failed.", "ERROR")
    return {"provider":"none","model":"none","answer":"No cloud provider succeeded. Check Render environment variables and model names.","errors":errors}

def ask_ai(prompt):
    mac=(os.getenv("MAC_CONNECTOR_URL") or DYNAMIC_CONNECTOR["url"] or "").strip().rstrip("/")
    secret=os.getenv("MAC_CONNECTOR_SECRET","").strip()
    
    # Build full prompt with skill context if not already wrapped
    if "Available enabled skills:" not in prompt:
        prompt = f"Available enabled skills:\n{skill_context()}\n\nTask:\n{prompt}"

    if mac:
        log_event(f"Attempting Mac Connector at {mac}")
        try:
            r=requests.post(mac+"/api/chat",json={"prompt":prompt},headers={"x-connector-secret":secret},timeout=240)
            if r.status_code==200:
                log_event("Success: Mac Connector (Ollama) responded.")
                data = r.json()
                # Normalize result format for the UI
                return {
                    "mode": "mac-ollama",
                    "result": {"provider": "ollama", "model": data.get("model"), "answer": data.get("answer")}
                }
            log_event(f"Mac Connector error: {r.status_code}. Falling back to cloud...", "ERROR")
        except Exception as e:
            log_event(f"Mac Connector unreachable: {str(e)[:100]}. Falling back to cloud...", "ERROR")
    return {"mode":"cloud","result":cloud_ai(prompt)}

def skill_context():
    c = db()
    # In a real app we'd fetch from DB, for now using global
    enabled = [s for s in DEFAULT_SKILLS if s["enabled"]]
    return "\n".join([f"- {s['name']}: {s['desc']}" for s in enabled])

@APP.get("/",response_class=HTMLResponse)
def home():
    return HTMLResponse("""
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nexus Render Hybrid</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/inter-ui/3.19.3/inter.css">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
:root{--bg:#fafafa;--card:#ffffff;--ink:#171717;--muted:#737373;--blue:#006fee;--dark:#0a0a0a;--border:#f0f0f0;--green:#17c964}
*{box-sizing:border-box} body{margin:0;font-family:'Inter',sans-serif;background:var(--bg);color:var(--ink)}
.app{max-width:700px;margin:auto;min-height:100vh;padding:20px 20px 120px}
.logo{font-size:24px;font-weight:900;letter-spacing:-1px;color:var(--ink)}.pill{background:white;border:1px solid var(--border);border-radius:99px;padding:8px 16px;font-weight:600;font-size:14px}
.tabs{display:flex;gap:4px;background:#f4f4f5;padding:4px;border-radius:12px;margin-bottom:20px;overflow-x:auto}
.tab{border:0;background:none;padding:8px 16px;font-weight:600;font-size:13px;color:var(--muted);border-radius:8px;cursor:pointer;white-space:nowrap}
.tab.active{background:white;color:var(--ink);box-shadow:0 2px 4px #0000000a}
.card{background:white;border:1px solid var(--border);border-radius:16px;padding:20px;margin:12px 0}
.row{display:flex;align-items:center;justify-content:space-between;gap:12px}.title{font-size:22px;font-weight:800}.muted{color:var(--muted);font-size:15px;line-height:1.35}
.btn{border:0;border-radius:12px;background:var(--ink);color:white;padding:14px;font-weight:700;width:100%;font-size:15px;cursor:pointer}
.btn-blue{background:var(--blue)}
.btn-ghost{background:#f4f4f5;color:var(--ink);border:0;padding:8px 12px;border-radius:8px;font-weight:600}
textarea,input,select{width:100%;border:1px solid var(--border);border-radius:12px;background:white;padding:14px;font-size:15px;margin:8px 0;outline:none}
pre{white-space:pre-wrap;background:var(--dark);color:#a1a1aa;border-radius:12px;padding:16px;font-size:13px;font-family:monospace;overflow:auto}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.tile{text-align:left;background:white;border:1px solid var(--border);border-radius:16px;padding:16px;cursor:pointer}
.toggle{width:72px;height:38px;border-radius:99px;background:#ddd;position:relative}.toggle.on{background:var(--blue)}.knob{width:32px;height:32px;background:white;border-radius:50%;position:absolute;top:3px;left:3px}.toggle.on .knob{left:37px}
.bottom{position:fixed;left:0;right:0;bottom:0;background:rgba(255,255,255,0.9);backdrop-filter:blur(20px);padding:14px;border-top:1px solid var(--border);z-index:100}
.composer{max-width:700px;margin:auto;display:flex;gap:10px}.composer textarea{height:48px;margin:0;border-radius:24px;padding:12px 20px}
.send{width:48px;height:48px;border-radius:50%;background:var(--ink);color:white;border:0;flex-shrink:0;cursor:pointer}
.screen{display:none}.screen.active{display:block}
.badge{font-size:11px;background:#f4f4f5;color:var(--muted);border-radius:6px;padding:2px 6px;text-transform:uppercase;font-weight:700}
.ok{color:var(--green);font-weight:700}
.log-line{border-bottom:1px solid #222;padding:4px 0;font-family:monospace}
.log-INFO{color:#4ade80}.log-ERROR{color:#f87171}
</style>
</head>
<body onload="init()">

<div id="sidebar" style="position:fixed;left:-280px;top:0;bottom:0;width:280px;background:white;z-index:200;transition:0.3s;padding:20px;border-right:1px solid var(--border);box-shadow:10px 0 30px #0001">
  <div class="row" style="margin-bottom:30px"><div class="logo">nexus</div><button class="btn-ghost" onclick="toggleMenu()">✕</button></div>
  <div style="display:flex;flex-direction:column;gap:10px">
    <button class="tab" style="width:100%;text-align:left" onclick="nav('home');toggleMenu()">🏠 Home</button>
    <button class="tab" style="width:100%;text-align:left" onclick="nav('agent');toggleMenu()">🤖 Agent Chat</button>
    <button class="tab" style="width:100%;text-align:left" onclick="nav('scheduled');toggleMenu()">📅 Scheduled Tasks</button>
    <button class="tab" style="width:100%;text-align:left" onclick="nav('library');toggleMenu()">📚 Library</button>
    <button class="tab" style="width:100%;text-align:left" onclick="nav('mail');toggleMenu()">✉️ Mail Nexus</button>
    <button class="tab" style="width:100%;text-align:left" onclick="nav('data');toggleMenu()">💾 Data Controls</button>
    <button class="tab" style="width:100%;text-align:left" onclick="nav('browser');toggleMenu()">🌐 Cloud Browser</button>
    <button class="tab" style="width:100%;text-align:left" onclick="nav('logs');toggleMenu()">💻 System Logs</button>
    <button class="tab" style="width:100%;text-align:left" onclick="nav('skills');toggleMenu()">🧩 Skills</button>
    <button class="tab" style="width:100%;text-align:left" onclick="nav('connectors');toggleMenu()">🔌 Connectors</button>
    <button class="tab" style="width:100%;text-align:left" onclick="nav('integrations');toggleMenu()">🔗 Integrations</button>
    <hr style="border:0;border-top:1px solid var(--border);margin:10px 0">
    <button class="tab" style="width:100%;text-align:left" onclick="alert('Share with a friend workflow not implemented')">🤝 Share with a friend</button>
    <button class="tab" style="width:100%;text-align:left" onclick="alert('Knowledge base not implemented')">🧠 Knowledge</button>
    <button class="tab" style="width:100%;text-align:left" onclick="alert('Account settings not implemented')">👤 Account</button>
    <button class="tab" style="width:100%;text-align:left" onclick="alert('Language settings not implemented')">🌐 Language</button>
    <button class="tab" style="width:100%;text-align:left" onclick="alert('Appearance settings not implemented')">🎨 Appearance</button>
    <button class="tab" style="width:100%;text-align:left" onclick="alert('Cache cleared')">🧹 Clear Cache</button>
  </div>
</div>

<div id="plusMenu" style="display:none;position:fixed;inset:0;background:rgba(255,255,255,0.9);z-index:300;padding:20px;backdrop-filter:blur(10px)">
  <div class="row" style="margin-bottom:20px"><div class="title">Create</div><button class="btn-ghost" onclick="togglePlus()">✕</button></div>
  <div class="grid" style="grid-template-columns:repeat(auto-fit, minmax(100px, 1fr)); gap: 10px;">
    <div class="tile" style="text-align:center" onclick="alert('Camera workflow not implemented')"><i class="fa-solid fa-camera"></i><br>Camera</div>
    <div class="tile" style="text-align:center" onclick="alert('Photos workflow not implemented')"><i class="fa-solid fa-image"></i><br>Photos</div>
    <div class="tile" style="text-align:center" onclick="nav('library');togglePlus()"><i class="fa-solid fa-file"></i><br>Files</div>
    <div class="tile" style="text-align:center" onclick="nav('connectors');togglePlus()"><i class="fa-solid fa-laptop"></i><br>Connect My Computer</div>
    <div class="tile" style="text-align:center" onclick="nav('skills');togglePlus()"><i class="fa-solid fa-puzzle-piece"></i><br>Add Skills</div>
    <div class="tile" style="text-align:center" onclick="nav('website');togglePlus()"><i class="fa-solid fa-code"></i><br>Build website</div>
    <div class="tile" style="text-align:center" onclick="alert('Create slides workflow not implemented')"><i class="fa-solid fa-file-powerpoint"></i><br>Create slides</div>
    <div class="tile" style="text-align:center" onclick="alert('Create image workflow not implemented')"><i class="fa-solid fa-image-landscape"></i><br>Create image</div>
    <div class="tile" style="text-align:center" onclick="alert('Edit image workflow not implemented')"><i class="fa-solid fa-pencil"></i><br>Edit image</div>
    <div class="tile" style="text-align:center" onclick="nav('browser');togglePlus()"><i class="fa-solid fa-magnifying-glass"></i><br>Wide Research</div>
    <div class="tile" style="text-align:center" onclick="nav('agent');togglePlus()"><i class="fa-solid fa-comments"></i><br>Chat mode</div>
    <div class="tile" style="text-align:center" onclick="nav('scheduled');togglePlus()"><i class="fa-solid fa-calendar-alt"></i><br>Scheduled tasks</div>
    <div class="tile" style="text-align:center" onclick="nav('spreadsheet');togglePlus()"><i class="fa-solid fa-table"></i><br>Create spreadsheet</div>
    <div class="tile" style="text-align:center" onclick="nav('video');togglePlus()"><i class="fa-solid fa-video"></i><br>Create video</div>
    <div class="tile" style="text-align:center" onclick="nav('audio');togglePlus()"><i class="fa-solid fa-music"></i><br>Generate audio</div>
    <div class="tile" style="text-align:center" onclick="alert('Playbook workflow not implemented')"><i class="fa-solid fa-book"></i><br>Playbook</div>
  </div>
</div>

<div class="app">
  <div class="header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
    <button class="btn-ghost" onclick="toggleMenu()"><i class="fa fa-bars"></i></button>
    <div class="logo">nexus</div>
    <button class="pill" id="statusPill">Checking...</button>
  </div>

  <div class="tabs">
    <button class="tab active" data-nav="home" onclick="nav('home')">Home</button>
    <button class="tab" data-nav="agent" onclick="nav('agent')">Agent</button>
    <button class="tab" data-nav="skills" onclick="nav('skills')">Skills</button>
    <button class="tab" data-nav="connectors" onclick="nav('connectors')">Connect</button>
    <button class="tab" data-nav="library" onclick="nav('library')">Library</button>
    <button class="tab" data-nav="logs" onclick="nav('logs')">Logs</button>
  </div>

  <div id="home" class="screen active">
    <div class="card" style="border:0;padding:0;background:transparent"><div class="title">Good day, Commander</div><div class="muted">What shall we build today?</div></div>
    <div class="grid">
      <div class="tile" onclick="nav('browser')"><i class="fa-solid fa-globe"></i> <b>Browser</b><br><span class="muted">Fetch & analyze</span></div>
      <div class="tile" onclick="nav('website')"><b>🏗️ Build</b><br><span class="muted">Site & app plans</span></div>
      <div class="tile" onclick="nav('spreadsheet')"><b>📊 Data</b><br><span class="muted">Spreadsheets</span></div>
    </div>
    <div class="card"><div class="title">Hybrid Core</div><div class="muted" style="margin-bottom:15px">Autonomous agent with cloud fallback and optional local Mac private vault.</div><button class="btn" onclick="nav('agent')">Launch Agent</button></div>
    <div class="card"><div class="title">Recent Tasks</div><div id="recentTasksList"></div></div>
  </div>

  <div id="agent" class="screen"><div class="card"><div class="title">Chat / Agent</div><textarea id="agentPrompt" rows="8" placeholder="Assign a task or ask anything"></textarea><button class="btn btn-blue" onclick="chat()">Run Agent</button><pre id="agentOut" style="margin-top:20px;display:none"></pre></div></div>

  <div id="skills" class="screen"><div class="card"><div class="row"><div class="title">Skills</div><button class="btn2" onclick="addSkill()">＋</button></div><input id="skillSearch" oninput="loadSkills()" placeholder="Search"><div id="skillsList"></div></div></div>

  <div id="connectors" class="screen"><div class="card"><div class="title">Connectors</div><div class="muted">Connect everyday apps, APIs, and the Mac private vault.</div><button class="btn" onclick="loadConnectors()">Refresh</button><div id="connectorsList"></div></div></div>

  <div id="integrations" class="screen"><div class="card"><div class="title">Integrations</div><div id="intList"></div></div></div>

  <div id="scheduled" class="screen"><div class="card"><div class="row"><div class="title">Scheduled records</div><button class="btn-ghost" onclick="createSchedule()">＋</button></div><input id="schedTitle" placeholder="Schedule title"><textarea id="schedPrompt" placeholder="Task prompt"></textarea><select id="schedCadence"><option>daily</option><option>weekly</option><option>manual</option></select><button class="btn" onclick="createSchedule()">New record</button><div id="scheduleList"></div></div></div>

  <div id="library" class="screen"><div class="card"><div class="title">Library</div><input type="file" id="file"><button class="btn" onclick="upload()">Upload</button><select id="filter" onchange="library()"><option>all</option><option>documents</option><option>image-video</option><option>audio</option><option>spreadsheets</option><option>others</option></select><div id="libraryList"></div></div></div>

  <div id="browser" class="screen"><div class="card"><div class="title">Cloud Browser</div><input id="url" placeholder="https://example.com"><textarea id="browserTask" placeholder="What should the agent extract or analyze?"></textarea><button class="btn btn-blue" onclick="browse()">Run Browser</button><pre id="browserOut" style="margin-top:20px;display:none"></pre></div></div>

  <div id="website" class="screen"><div class="card"><div class="title">Build website</div><textarea id="webPrompt" placeholder="Describe website/app"></textarea><button class="btn" onclick="generate('website')">Generate</button><pre id="websiteOut" style="margin-top:20px;display:none"></pre></div></div>
  <div id="spreadsheet" class="screen"><div class="card"><div class="title">Create spreadsheet</div><textarea id="sheetPrompt" placeholder="Describe spreadsheet"></textarea><button class="btn" onclick="generate('spreadsheet')">Generate</button><pre id="spreadsheetOut"></pre></div></div>
  <div id="video" class="screen"><div class="card"><div class="title">Create video</div><textarea id="videoPrompt" placeholder="Describe video"></textarea><button class="btn" onclick="generate('video')">Generate</button><pre id="videoOut"></pre></div></div>
  <div id="audio" class="screen"><div class="card"><div class="title">Generate audio</div><textarea id="audioPrompt" placeholder="Describe audio/music"></textarea><button class="btn" onclick="generate('audio')">Generate</button><pre id="audioOut"></pre></div></div>
  
  <div id="mail" class="screen">
    <div class="card"><div class="title">Mail Nexus</div><div class="badge ok">Alpha</div><p class="muted">Your pseudo-address: <b>nexus-incoming@render.internal</b></p>
    <div class="tile">Approved Senders: <span class="badge">Commander Only</span></div>
    <button class="btn" onclick="alert('Mail fetching requires SMTP connector')">Sync Inbox</button></div>
  </div>

  <div id="data" class="screen">
    <div class="card"><div class="title">Data Controls</div>
    <div class="row" style="margin:10px 0"><span>Memory Records</span><button class="btn-ghost" onclick="loadMemory()">View</button></div>
    <div class="row" style="margin:10px 0"><span>Task History</span><button class="btn-ghost" onclick="loadTasks()">View</button></div>
    <div class="row" style="margin:10px 0"><span>Export Data</span><button class="btn-ghost" onclick="alert('Exporting to CSV...')">Export</button></div>
    <button class="btn" style="background:#ff4b4b" onclick="alert('Cache cleared')">Clear All Cache</button></div>
    <div id="dataOut"></div>
  </div>

  <div id="logs" class="screen">
    <div class="card" style="background:#0b0d12;border-color:#333">
      <div class="row"><div class="title" style="color:white">System Logs</div><button class="btn-ghost" onclick="fetchLogs()">⟳</button></div>
      <div id="logList" style="margin-top:15px;height:400px;overflow:auto"></div>
    </div>
  </div>
</div>

<div class="bottom">
  <div class="composer"><button class="send" style="background:#f4f4f5;color:black" onclick="togglePlus()">+</button><textarea id="quick" placeholder="Assign a task or ask anything"></textarea><button class="send" onclick="quick()">↑</button></div>
</div>

<script>
function nav(id){
  document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  document.querySelectorAll('.tab').forEach(t=>{
    t.classList.remove('active');
    if(t.dataset.nav === id) t.classList.add('active');
  });
}
function toggleMenu(){let s=document.getElementById('sidebar');s.style.left=s.style.left==='0px'?'-280px':'0px'}
function togglePlus(){let p=document.getElementById('plusMenu');p.style.display=p.style.display==='none'?'block':'none'}
async function checkStatus(){
  let r=await fetch('/api/providers');
  let d=await r.json();
  let activeCount = Object.entries(d).filter(([k,v])=> v===true && k!=='openai_disabled').length;
  document.getElementById('statusPill').textContent = activeCount > 0 ? '● Online' : '○ Offline';
  document.getElementById('statusPill').style.color = activeCount > 0 ? 'var(--green)' : 'var(--muted)';
}
async function chat(){
  let prompt=document.getElementById('agentPrompt').value;
  if(!prompt) return;
  document.getElementById('agentOut').style.display = 'block'; nav('agent');
  document.getElementById('agentOut').textContent='Thinking...';
  let r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})});
  let res = await r.json();
  document.getElementById('agentOut').textContent=JSON.stringify(res,null,2);
}
async function quick(){let q=document.getElementById('quick'); if(!q.value) return; document.getElementById('agentPrompt').value=q.value;q.value='';nav('agent');chat()}
async function loadSkills(){let q=document.getElementById('skillSearch')?.value||'';let r=await fetch('/api/skills?q='+encodeURIComponent(q));let data=await r.json();document.getElementById('skillsList').innerHTML=data.items.map(s=>`<div class="card"><div class="row"><div><div class="title" style="font-size:18px">${s.name}</div><div class="muted">${s.desc}</div><span class="badge">Skill</span></div><div onclick="toggleSkill('${s.id}')" class="toggle ${s.enabled?'on':''}"><div class="knob"></div></div></div></div>`).join('')}
async function toggleSkill(id){await fetch('/api/skills/'+id+'/toggle',{method:'POST'});loadSkills()}
async function addSkill(){let name=prompt('Skill name'); if(name) await fetch('/api/skills',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,desc:'Custom skill'})});loadSkills()}
async function loadConnectors(){let r=await fetch('/api/connectors');let data=await r.json();document.getElementById('connectorsList').innerHTML=data.items.map(c=>`<div class="card"><div class="row"><div><div class="title">${c.name}</div><div class="muted">${c.kind} ${c.env?'['+c.env+']':''}</div></div><span class="${c.enabled?'ok':''}">${c.enabled?'✓':'Not Configured'}</span></div></div>`).join('')}
async function loadIntegrations(){let r=await fetch('/api/integrations');let data=await r.json();document.getElementById('intList').innerHTML=data.items.map(c=>`<div class="card"><div class="row"><div><div class="title">${c.name}</div></div><span class="${c.enabled?'ok':''}">${c.enabled?'✓':'Connect'}</span></div></div>`).join('')}
async function createSchedule(){let title=document.getElementById('schedTitle').value;let prompt=document.getElementById('schedPrompt').value;let cadence=document.getElementById('schedCadence').value;await fetch('/api/schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,prompt,cadence})});schedules()}
async function schedules(){let r=await fetch('/api/schedules');let d=await r.json();document.getElementById('scheduleList').innerHTML=d.items.map(x=>`<div class="card"><b>${x.title}</b><div class="muted">${x.cadence} · ${x.status||'scheduled'}</div></div>`).join('')}
async function upload(){let f=document.getElementById('file').files[0];let fd=new FormData();fd.append('file',f);let r=await fetch('/api/library/upload',{method:'POST',body:fd});await r.json();library()}
async function library(){let type=document.getElementById('filter').value;let r=await fetch('/api/library?type='+type);let d=await r.json();document.getElementById('libraryList').innerHTML=d.items.map(x=>`<div class="card"><b>${x.name}</b><div class="muted">${x.type} · ${x.created_at}</div></div>`).join('')}
async function browse(){let url=document.getElementById('url').value;let task=document.getElementById('browserTask').value;let r=await fetch('/api/browser',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,task})});document.getElementById('browserOut').textContent=JSON.stringify(await r.json(),null,2)}
async function generate(kind){let map={website:'webPrompt',spreadsheet:'sheetPrompt',video:'videoPrompt',audio:'audioPrompt'};let prompt=document.getElementById(map[kind]).value;let r=await fetch('/api/generate/'+kind,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})});document.getElementById(kind+'Out').style.display='block';document.getElementById(kind+'Out').textContent=JSON.stringify(await r.json(),null,2); if(kind==='website') nav('website')}
async function fetchLogs(){let r=await fetch('/api/logs');let d=await r.json();document.getElementById('logList').innerHTML=d.map(l=>`<div class="log-line"><span class="muted">[${l.time.split('T')[1].split('.')[0]}]</span> <span class="log-${l.level}">${l.level}</span> ${l.message}</div>`).join(''); if(document.getElementById('logs').classList.contains('active')) { let objDiv = document.getElementById("logList"); objDiv.scrollTop = objDiv.scrollHeight; }}
async function loadTasks(){let r=await fetch('/api/tasks');let d=await r.json();document.getElementById('dataOut').innerHTML='<pre>'+JSON.stringify(d,null,2)+'</pre>'}
async function loadRecentTasks(){let r=await fetch('/api/tasks');let d=await r.json();document.getElementById('recentTasksList').innerHTML=d.items.slice(0,3).map(t=>`<div class="row" style="padding:8px 0;border-bottom:1px solid #f0f0f0"><span class="muted">${t.title}</span><span class="badge">${t.status}</span></div>`).join('')}
async function loadMemory(){let r=await fetch('/api/memory');let d=await r.json();document.getElementById('dataOut').innerHTML='<pre>'+JSON.stringify(d,null,2)+'</pre>'}
function init(){
  checkStatus();
  loadSkills();
  loadConnectors();
  loadIntegrations();
  schedules();
  library();
  loadRecentTasks();
}
setInterval(fetchLogs, 3000);
setInterval(checkStatus, 10000);
</script>
</body>
</html>
""")

@APP.get("/health")
def health(): return {"ok":True,"service":"nexus-render-hybrid","version":"12.0.0"}

@APP.get("/api/health")
def api_health(): return {"status":"healthy","timestamp":now()}

@APP.get("/api/providers")
def api_providers(): return providers()

@APP.get("/api/logs")
def api_logs(): return list(LOGS)

@APP.get("/logs",response_class=HTMLResponse)
def view_logs(): return home()

@APP.get("/api/integrations")
def api_integrations(): return {"items":INTEGRATIONS}

@APP.post("/api/chat")
def chat(payload:dict):
    prompt=payload.get("prompt","").strip()
    log_event(f"New chat request: {prompt[:50]}...")
    if not prompt: return {"error":"Empty prompt"}
    
    result=ask_ai(prompt)
    log_event("Chat task complete.")
    remember("chat",prompt,json.dumps(result)[:5000])
    tid=str(uuid.uuid4())
    c=db(); c.execute("INSERT INTO tasks(id,title,prompt,status,result,created_at) VALUES(?,?,?,?,?,?)",(tid,prompt[:80],prompt,"completed",json.dumps(result)[:8000],now())); c.commit(); c.close()
    return {"task_id":tid,"success":True,"result":result}

@APP.post("/api/connector/register")
def register_connector(payload:dict, x_connector_secret: str = Header(default="")):
    expected = os.getenv("MAC_CONNECTOR_SECRET", "").strip()
    if expected and x_connector_secret != expected:
        log_event("Unauthorized connector registration attempt", "ERROR")
        return JSONResponse(status_code=401, content={"ok": False, "error": "Unauthorized"})
        
    url = payload.get("url")
    if url:
        DYNAMIC_CONNECTOR["url"] = url
        log_event(f"Mac Connector registered: {url}")
        return {"ok": True}
    return {"ok": False}

@APP.post("/api/connector/clear")
def clear_connector():
    DYNAMIC_CONNECTOR["url"] = None
    log_event("Mac Connector cleared")
    return {"ok": True}

@APP.get("/api/skills")
def api_skills(q:str=""):
    items=DEFAULT_SKILLS
    if q: items=[s for s in items if q.lower() in s["name"].lower() or q.lower() in s["desc"].lower()]
    return {"items":items}

@APP.post("/api/skills/{sid}/toggle")
def toggle_skill(sid:str):
    for s in DEFAULT_SKILLS:
        if s["id"]==sid: s["enabled"]=not s["enabled"]; return {"ok":True,"skill":s}
    return {"ok":False,"error":"not found"}

@APP.post("/api/skills")
def add_skill(payload:dict):
    DEFAULT_SKILLS.insert(0,{"id":str(uuid.uuid4()),"name":payload.get("name","custom-skill"),"desc":payload.get("desc","Custom skill"),"enabled":True})
    return {"ok":True}

@APP.get("/api/connectors")
def api_connectors(): return {"items":CONNECTORS}

@APP.get("/api/schedules")
def get_schedules():
    c=db(); rows=c.execute("SELECT * FROM schedules ORDER BY created_at DESC").fetchall(); c.close()
    return {"items":[dict(r) for r in rows]}

@APP.post("/api/schedules")
def create_schedule(payload:dict):
    sid=str(uuid.uuid4())
    c=db(); c.execute("INSERT INTO schedules(id,title,prompt,cadence,enabled,created_at) VALUES(?,?,?,?,?,?)",(sid,payload.get("title","Scheduled task"),payload.get("prompt",""),payload.get("cadence","manual"),1,now())); c.commit(); c.close()
    return {"ok":True,"id":sid}

@APP.post("/api/library/upload")
async def upload(file:UploadFile=File(...)):
    data=await file.read()
    fid=str(uuid.uuid4())
    name=file.filename or fid
    suffix=name.lower().split(".")[-1] if "." in name else "other"
    if suffix in ["txt","pdf","doc","docx","md"]: typ="documents"
    elif suffix in ["png","jpg","jpeg","mp4","mov","webp"]: typ="image-video"
    elif suffix in ["mp3","wav","m4a"]: typ="audio"
    elif suffix in ["csv","xls","xlsx"]: typ="spreadsheets"
    else: typ="others"
    path=UPLOADS/name; path.write_bytes(data)
    preview=data[:4000].decode(errors="ignore")
    c=db(); c.execute("INSERT INTO files(id,name,type,content,created_at) VALUES(?,?,?,?,?)",(fid,name,typ,preview,now())); c.commit(); c.close()
    return {"ok":True,"id":fid,"name":name,"type":typ}

@APP.get("/api/mail-nexus")
def mail_nexus():
    return {"address":"nexus-incoming@render.internal","approved_senders":["Commander"],"status":"active"}

@APP.get("/api/cloud-browser/status")
def browser_status():
    return {"cookies":0,"local_storage":"empty","persist_login":False}

@APP.get("/api/library")
def library(type:str="all"):
    c=db()
    if type=="all": rows=c.execute("SELECT id,name,type,created_at FROM files ORDER BY created_at DESC").fetchall()
    else: rows=c.execute("SELECT id,name,type,created_at FROM files WHERE type=? ORDER BY created_at DESC",(type,)).fetchall()
    c.close()
    return {"items":[dict(r) for r in rows]}

@APP.get("/api/memory")
def memory_list():
    c=db(); rows=c.execute("SELECT * FROM memory ORDER BY created_at DESC").fetchall(); c.close()
    return {"items":[dict(r) for r in rows]}

@APP.post("/api/browser")
def browser(payload:dict):
    url=payload.get("url","").strip()
    task=payload.get("task","Summarize this website.")
    if not url.startswith("http"): return {"error":"URL must start with http"}
    log_event(f"Browser operator: fetching {url}")
    r=requests.get(url,timeout=30,headers={"User-Agent":"Mozilla/5.0"})
    text=BeautifulSoup(r.text,"html.parser").get_text("\n", strip=True)
    prompt=f"Browser operator task: {task}\nURL: {url}\nExtracted page text:\n{text[:12000]}"
    result=ask_ai(prompt)
    log_event(f"Browser task analysis complete.")
    remember("browser",url,json.dumps(result)[:5000])
    return {"url":url,"status":r.status_code,"page_title":BeautifulSoup(r.text,"html.parser").title.string if BeautifulSoup(r.text,"html.parser").title else "No Title","preview":text[:1200],"analysis":result}

@APP.post("/api/generate/{kind}")
def generate(kind:str,payload:dict):
    prompt=payload.get("prompt","")
    templates={
        "website":"Create a complete website/app plan with HTML sections, copy, SEO, routes, deployment steps, and code outline.",
        "spreadsheet":"Create a professional spreadsheet plan with columns, formulas, CSV sample, and use cases.",
        "video":"Create a professional video production workflow with script, shot list, scenes, prompts, captions, and edit plan.",
        "audio":"Create an audio/music generation plan with prompt, structure, voice/music direction, and production steps."
    }
    instruction=templates.get(kind,"Create a useful production-ready deliverable.")
    result=ask_ai(f"{instruction}\n\nUser request:\n{prompt}")
    remember(kind,prompt,json.dumps(result)[:5000])
    return {"kind":kind,"result":result}

@APP.get("/api/tasks")
def tasks():
    c=db(); rows=c.execute("SELECT id,title,status,created_at FROM tasks ORDER BY created_at DESC LIMIT 50").fetchall(); c.close()
    return {"items":[dict(r) for r in rows]}

@APP.get("/api/data-controls")
def data_controls():
    return {"shared_tasks":"/api/tasks","deployed_websites":"/api/websites","memory":"/api/memory","export_format":"CSV/JSON"}
