import os, json, sqlite3, datetime, uuid, requests
from pathlib import Path
from bs4 import BeautifulSoup
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse

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
    {"id":"excel-generator","name":"excel-generator","desc":"Create spreadsheet structures, formulas, tables, and CSV-ready outputs.","enabled":False},
    {"id":"video-generator","name":"video-generator","desc":"Plan scripts, shots, prompts, edits, shorts, ads, and video workflows.","enabled":True},
    {"id":"music-prompter","name":"music-prompter","desc":"Craft music-generation prompts and song direction workflows.","enabled":True},
    {"id":"browser-operator","name":"browser-operator","desc":"Fetch, inspect, summarize, and extract website content.","enabled":True},
    {"id":"wide-research","name":"wide-research","desc":"Perform structured multi-source research planning and synthesis.","enabled":True},
    {"id":"website-builder","name":"website-builder","desc":"Generate website/app structures, landing pages, and deployment plans.","enabled":True},
]

CONNECTORS = [
    {"id":"gmail","name":"Gmail","kind":"connector","enabled":False},
    {"id":"google-drive","name":"Google Drive","kind":"connector","enabled":False},
    {"id":"github","name":"GitHub","kind":"connector","enabled":True},
    {"id":"my-browser","name":"My Browser","kind":"connector","enabled":True},
    {"id":"outlook-mail","name":"Outlook Mail","kind":"connector","enabled":False},
    {"id":"outlook-calendar","name":"Outlook Calendar","kind":"connector","enabled":False},
    {"id":"google-calendar","name":"Google Calendar","kind":"connector","enabled":False},
    {"id":"telegram","name":"Telegram","kind":"integration","enabled":bool(os.getenv("TELEGRAM_BOT_TOKEN","").strip())},
    {"id":"slack","name":"Slack","kind":"integration","enabled":False},
    {"id":"line","name":"LINE","kind":"integration","enabled":False},
    {"id":"mac-connector","name":"Mac Connector / Ollama Vault","kind":"connector","enabled":bool(os.getenv("MAC_CONNECTOR_URL","").strip())},
]

def now():
    return datetime.datetime.utcnow().isoformat()

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
        "groq": active("GROQ_API_KEY"),
        "openrouter": active("OPENROUTER_API_KEY"),
        "together": active("TOGETHER_API_KEY"),
        "fireworks": active("FIREWORKS_API_KEY"),
        "mac_connector": active("MAC_CONNECTOR_URL"),
        "mac_connector_secret": active("MAC_CONNECTOR_SECRET"),
        "openai_disabled": True
    }

def openai_compatible(provider,url,key,model,prompt):
    r=requests.post(url,headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json={
        "model":model,
        "messages":[
            {"role":"system","content":"You are Nexus Render Hybrid: a practical autonomous agent. Be precise, useful, and never claim external actions unless completed."},
            {"role":"user","content":prompt}
        ],
        "temperature":0.3
    },timeout=120)
    r.raise_for_status()
    data=r.json()
    return {"provider":provider,"model":model,"answer":data["choices"][0]["message"]["content"]}

def gemini(prompt):
    key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    model=os.getenv("GEMINI_MODEL","gemini-1.5-flash")
    r=requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",json={
        "contents":[{"parts":[{"text":prompt}]}]
    },timeout=120)
    r.raise_for_status()
    data=r.json()
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
        except Exception as e: errors.append(f"{name}: {str(e)[:250]}")
    return {"provider":"none","model":"none","answer":"No cloud provider succeeded. Check Render environment variables and model names.","errors":errors}

def ask_ai(prompt):
    mac=os.getenv("MAC_CONNECTOR_URL","").strip().rstrip("/")
    secret=os.getenv("MAC_CONNECTOR_SECRET","").strip()
    if mac:
        try:
            r=requests.post(mac+"/api/chat",json={"prompt":prompt},headers={"x-connector-secret":secret},timeout=240)
            if r.status_code==200:
                return {"mode":"mac-ollama","result":r.json()}
            return {"mode":"mac-error","status":r.status_code,"body":r.text[:500],"fallback":cloud_ai(prompt)}
        except Exception as e:
            return {"mode":"mac-unreachable","error":str(e),"fallback":cloud_ai(prompt)}
    return {"mode":"cloud","result":cloud_ai(prompt)}

def skill_context():
    enabled=[s for s in DEFAULT_SKILLS if s["enabled"]]
    return "\n".join([f"- {s['name']}: {s['desc']}" for s in enabled])

@APP.get("/",response_class=HTMLResponse)
def home():
    return HTMLResponse("""
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nexus Render Hybrid</title>
<style>
:root{--bg:#f6f6f4;--card:#ffffff;--ink:#2a2a2a;--muted:#7b7b7b;--blue:#2878ff;--dark:#0b0d12;--relay:#00ff7f}
*{box-sizing:border-box} body{margin:0;font-family:-apple-system,BlinkMacSystemFont,Arial;background:var(--bg);color:var(--ink)}
.app{max-width:980px;margin:auto;min-height:100vh;padding:18px 18px 110px}
.header{display:flex;align-items:center;justify-content:space-between;margin:16px 0 22px}
.logo{font-family:Georgia,serif;font-size:38px;font-weight:700}.pill{background:white;border-radius:999px;padding:12px 18px;box-shadow:0 8px 28px #0001}
.tabs{display:flex;gap:10px;margin:14px 0}.tab{border:1px solid #ddd;background:white;border-radius:999px;padding:12px 22px;font-weight:700}.tab.active{background:#111;color:white}
.card{background:white;border-radius:24px;padding:18px;margin:14px 0;box-shadow:0 1px 0 #ddd}.dark .card{background:#151925;border:1px solid #263044}
.row{display:flex;align-items:center;justify-content:space-between;gap:12px}.title{font-size:22px;font-weight:800}.muted{color:var(--muted);font-size:15px;line-height:1.35}
.btn{border:0;border-radius:14px;background:var(--blue);color:white;padding:13px 16px;font-weight:800;width:100%;font-size:16px}
.btn2{border:0;border-radius:14px;background:#e9e9e9;color:#222;padding:12px 14px;font-weight:800}
textarea,input,select{width:100%;border:0;border-radius:18px;background:#eee;padding:15px;font-size:16px;margin:8px 0}
pre{white-space:pre-wrap;background:#090b10;color:#d7ffd7;border-radius:16px;padding:14px;overflow:auto}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.tile{text-align:center;background:white;border-radius:22px;padding:18px;font-weight:800}
.toggle{width:72px;height:38px;border-radius:99px;background:#ddd;position:relative}.toggle.on{background:var(--blue)}.knob{width:32px;height:32px;background:white;border-radius:50%;position:absolute;top:3px;left:3px}.toggle.on .knob{left:37px}
.bottom{position:fixed;left:0;right:0;bottom:0;background:#fff;padding:14px;box-shadow:0 -10px 30px #0001}.composer{max-width:980px;margin:auto;display:flex;gap:10px}.composer textarea{height:64px;margin:0}.send{width:64px;border-radius:50%;background:#222;color:white}
.screen{display:none}.screen.active{display:block}.link{cursor:pointer}.dark{background:#0b0d12;color:white}.dark .app{background:#0b0d12}.dark input,.dark textarea,.dark select{background:#111827;color:white}.dark .tab{background:#151925;color:white;border-color:#333}
.smallnav{display:flex;gap:8px;flex-wrap:wrap}.smallnav button{flex:1;min-width:120px}
.badge{font-size:12px;background:#eaf2ff;color:#2878ff;border-radius:8px;padding:3px 7px}.ok{color:#188a42}
</style>
</head>
<body>
<div class="app">
  <div class="header"><button class="pill" onclick="nav('home')">☰</button><div class="logo">nexus</div><button class="pill" onclick="theme()">◐</button></div>
  <div class="tabs"><button class="tab active" onclick="nav('home')">All</button><button class="tab" onclick="nav('agent')">Agent</button><button class="tab" onclick="nav('scheduled')">Scheduled</button><button class="tab" onclick="nav('library')">Library</button></div>

  <div id="home" class="screen active">
    <div class="grid">
      <div class="tile" onclick="nav('browser')">🌐<br>Cloud Browser</div>
      <div class="tile" onclick="nav('skills')">🧩<br>Skills</div>
      <div class="tile" onclick="nav('connectors')">🔌<br>Connectors</div>
    </div>
    <div class="card"><div class="title">Agent</div><div class="muted">Cloud APIs plus optional private Mac Ollama connector.</div><button class="btn" onclick="nav('agent')">Open Agent</button></div>
    <div class="card"><div class="title">Provider Status</div><button class="btn" onclick="providers()">Check Providers</button><pre id="providers"></pre></div>
    <div class="card"><div class="title">Quick Actions</div><div class="smallnav">
      <button class="btn2" onclick="nav('website')">Build website</button><button class="btn2" onclick="nav('spreadsheet')">Create spreadsheet</button><button class="btn2" onclick="nav('video')">Create video</button><button class="btn2" onclick="nav('audio')">Generate audio</button>
    </div></div>
  </div>

  <div id="agent" class="screen"><div class="card"><div class="title">Chat / Agent</div><textarea id="agentPrompt" rows="8" placeholder="Assign a task or ask anything"></textarea><button class="btn" onclick="chat()">Run Agent</button><pre id="agentOut"></pre></div></div>

  <div id="skills" class="screen"><div class="card"><div class="row"><div class="title">Skills</div><button class="btn2" onclick="addSkill()">＋</button></div><input id="skillSearch" oninput="loadSkills()" placeholder="Search"><div id="skillsList"></div></div></div>

  <div id="connectors" class="screen"><div class="card"><div class="title">Connectors</div><div class="muted">Connect everyday apps, APIs, and the Mac private vault.</div><button class="btn" onclick="loadConnectors()">Refresh</button><div id="connectorsList"></div></div></div>

  <div id="scheduled" class="screen"><div class="card"><div class="row"><div class="title">Scheduled tasks</div><button class="btn2" onclick="createSchedule()">＋</button></div><input id="schedTitle" placeholder="Schedule title"><textarea id="schedPrompt" placeholder="Task prompt"></textarea><select id="schedCadence"><option>daily</option><option>weekly</option><option>manual</option></select><button class="btn" onclick="createSchedule()">New schedule</button><div id="scheduleList"></div></div></div>

  <div id="library" class="screen"><div class="card"><div class="title">Library</div><input type="file" id="file"><button class="btn" onclick="upload()">Upload</button><select id="filter" onchange="library()"><option>all</option><option>documents</option><option>image-video</option><option>audio</option><option>spreadsheets</option><option>others</option></select><div id="libraryList"></div></div></div>

  <div id="browser" class="screen"><div class="card"><div class="title">Cloud Browser</div><input id="url" placeholder="https://example.com"><textarea id="browserTask" placeholder="What should the agent extract or analyze?"></textarea><button class="btn" onclick="browse()">Run Browser</button><pre id="browserOut"></pre></div></div>

  <div id="website" class="screen"><div class="card"><div class="title">Build website</div><textarea id="webPrompt" placeholder="Describe website/app"></textarea><button class="btn" onclick="generate('website')">Generate</button><pre id="websiteOut"></pre></div></div>
  <div id="spreadsheet" class="screen"><div class="card"><div class="title">Create spreadsheet</div><textarea id="sheetPrompt" placeholder="Describe spreadsheet"></textarea><button class="btn" onclick="generate('spreadsheet')">Generate</button><pre id="spreadsheetOut"></pre></div></div>
  <div id="video" class="screen"><div class="card"><div class="title">Create video</div><textarea id="videoPrompt" placeholder="Describe video"></textarea><button class="btn" onclick="generate('video')">Generate</button><pre id="videoOut"></pre></div></div>
  <div id="audio" class="screen"><div class="card"><div class="title">Generate audio</div><textarea id="audioPrompt" placeholder="Describe audio/music"></textarea><button class="btn" onclick="generate('audio')">Generate</button><pre id="audioOut"></pre></div></div>
</div>

<div class="bottom"><div class="composer"><textarea id="quick" placeholder="Assign a task or ask anything"></textarea><button class="send" onclick="quick()">↑</button></div></div>

<script>
function nav(id){document.querySelectorAll('.screen').forEach(s=>s.classList.remove('active'));document.getElementById(id).classList.add('active');document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'))}
function theme(){document.body.classList.toggle('dark')}
async function providers(){let r=await fetch('/api/providers');document.getElementById('providers').textContent=JSON.stringify(await r.json(),null,2)}
async function chat(){let prompt=document.getElementById('agentPrompt').value;let r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})});document.getElementById('agentOut').textContent=JSON.stringify(await r.json(),null,2)}
async function quick(){document.getElementById('agentPrompt').value=document.getElementById('quick').value;nav('agent');chat()}
async function loadSkills(){let q=document.getElementById('skillSearch')?.value||'';let r=await fetch('/api/skills?q='+encodeURIComponent(q));let data=await r.json();document.getElementById('skillsList').innerHTML=data.items.map(s=>`<div class="card"><div class="row"><div><div class="title">${s.name}</div><div class="muted">${s.desc}</div><span class="badge">Official</span></div><div onclick="toggleSkill('${s.id}')" class="toggle ${s.enabled?'on':''}"><div class="knob"></div></div></div></div>`).join('')}
async function toggleSkill(id){await fetch('/api/skills/'+id+'/toggle',{method:'POST'});loadSkills()}
async function addSkill(){let name=prompt('Skill name'); if(name) await fetch('/api/skills',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,desc:'Custom skill'})});loadSkills()}
async function loadConnectors(){let r=await fetch('/api/connectors');let data=await r.json();document.getElementById('connectorsList').innerHTML=data.items.map(c=>`<div class="card"><div class="row"><div><div class="title">${c.name}</div><div class="muted">${c.kind}</div></div><span class="${c.enabled?'ok':''}">${c.enabled?'✓':'Connect'}</span></div></div>`).join('')}
async function createSchedule(){let title=document.getElementById('schedTitle').value;let prompt=document.getElementById('schedPrompt').value;let cadence=document.getElementById('schedCadence').value;await fetch('/api/schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,prompt,cadence})});schedules()}
async function schedules(){let r=await fetch('/api/schedules');let d=await r.json();document.getElementById('scheduleList').innerHTML=d.items.map(x=>`<div class="card"><b>${x.title}</b><div class="muted">${x.cadence} · ${x.status||'scheduled'}</div></div>`).join('')}
async function upload(){let f=document.getElementById('file').files[0];let fd=new FormData();fd.append('file',f);let r=await fetch('/api/library/upload',{method:'POST',body:fd});await r.json();library()}
async function library(){let type=document.getElementById('filter').value;let r=await fetch('/api/library?type='+type);let d=await r.json();document.getElementById('libraryList').innerHTML=d.items.map(x=>`<div class="card"><b>${x.name}</b><div class="muted">${x.type} · ${x.created_at}</div></div>`).join('')}
async function browse(){let url=document.getElementById('url').value;let task=document.getElementById('browserTask').value;let r=await fetch('/api/browser',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,task})});document.getElementById('browserOut').textContent=JSON.stringify(await r.json(),null,2)}
async function generate(kind){let map={website:'webPrompt',spreadsheet:'sheetPrompt',video:'videoPrompt',audio:'audioPrompt'};let prompt=document.getElementById(map[kind]).value;let r=await fetch('/api/generate/'+kind,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt})});document.getElementById(kind+'Out').textContent=JSON.stringify(await r.json(),null,2)}
providers();loadSkills();loadConnectors();schedules();library();
</script>
</body>
</html>
""")

@APP.get("/health")
def health(): return {"ok":True,"service":"nexus-render-hybrid","version":"12.0.0"}

@APP.get("/api/providers")
def api_providers(): return providers()

@APP.post("/api/chat")
def chat(payload:dict):
    prompt=payload.get("prompt","").strip()
    if not prompt: return {"error":"Empty prompt"}
    full=f"""Available enabled skills:
{skill_context()}

User task:
{prompt}
"""
    result=ask_ai(full)
    remember("chat",prompt,json.dumps(result)[:5000])
    tid=str(uuid.uuid4())
    c=db(); c.execute("INSERT INTO tasks(id,title,prompt,status,result,created_at) VALUES(?,?,?,?,?,?)",(tid,prompt[:80],prompt,"completed",json.dumps(result)[:8000],now())); c.commit(); c.close()
    return {"task_id":tid,"success":True,"result":result}

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

@APP.get("/api/library")
def library(type:str="all"):
    c=db()
    if type=="all": rows=c.execute("SELECT id,name,type,created_at FROM files ORDER BY created_at DESC").fetchall()
    else: rows=c.execute("SELECT id,name,type,created_at FROM files WHERE type=? ORDER BY created_at DESC",(type,)).fetchall()
    c.close()
    return {"items":[dict(r) for r in rows]}

@APP.post("/api/browser")
def browser(payload:dict):
    url=payload.get("url","").strip()
    task=payload.get("task","Summarize this website.")
    if not url.startswith("http"): return {"error":"URL must start with http"}
    r=requests.get(url,timeout=30,headers={"User-Agent":"Mozilla/5.0"})
    text=BeautifulSoup(r.text,"html.parser").get_text("\\n")
    prompt=f"Browser operator task: {task}\\nURL: {url}\\nExtracted page text:\\n{text[:12000]}"
    result=ask_ai(prompt)
    remember("browser",url,json.dumps(result)[:5000])
    return {"url":url,"status":r.status_code,"preview":text[:1200],"analysis":result}

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
    result=ask_ai(f"{instruction}\\n\\nUser request:\\n{prompt}")
    remember(kind,prompt,json.dumps(result)[:5000])
    return {"kind":kind,"result":result}

@APP.get("/api/tasks")
def tasks():
    c=db(); rows=c.execute("SELECT id,title,status,created_at FROM tasks ORDER BY created_at DESC LIMIT 50").fetchall(); c.close()
    return {"items":[dict(r) for r in rows]}

@APP.get("/api/data-controls")
def data_controls():
    return {"shared_tasks":"/api/tasks","deployed_websites":"/api/websites","memory":"/api/memory"}

@APP.get("/api/memory")
def memory():
    c=db(); rows=c.execute("SELECT kind,title,content,created_at FROM memory ORDER BY id DESC LIMIT 50").fetchall(); c.close()
    return {"items":[dict(r) for r in rows]}
