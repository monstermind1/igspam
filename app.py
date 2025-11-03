# app.py
# Insta Multi Welcome Bot — Final (working backend + cyber-neon frontend)
# Usage:
#   pip install -r requirements.txt
#   python app.py
# For Render: ensure Procfile contains: web: python app.py

import os
import threading
import time
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, send_file
from instagrapi import Client

# ---------- CONFIG ----------
APP = Flask(__name__)
APP.secret_key = os.environ.get("FLASK_SECRET", "replace-with-a-secure-random-key")

UPLOADS_DIR = "uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True)
SESSION_PATH = os.path.join(UPLOADS_DIR, "session.json")
WELCOMED_CACHE_PATH = os.path.join(UPLOADS_DIR, "welcomed_cache.json")
LOGFILE = os.path.join(UPLOADS_DIR, "bot_logs.txt")

# runtime
BOT_THREAD = None
BOT_THREAD_LOCK = threading.Lock()
STOP_EVENT = threading.Event()
LOGS = []
BOT_STATUS = {"running": False, "task_id": None, "started_at": None, "last_ping": None}

# ---------- HELPERS ----------
def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def append_log(msg):
    line = f"[{now_str()}] {msg}"
    LOGS.append(line)
    if len(LOGS) > 2000:
        del LOGS[:600]
    try:
        with open(LOGFILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)

def load_welcomed_cache():
    try:
        if os.path.exists(WELCOMED_CACHE_PATH):
            with open(WELCOMED_CACHE_PATH, "r", encoding="utf-8") as f:
                arr = json.load(f)
                return set(arr)
    except Exception as e:
        append_log(f"Failed to load welcomed cache: {e}")
    return set()

def save_welcomed_cache(s):
    try:
        with open(WELCOMED_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(list(s), f)
    except Exception as e:
        append_log(f"Failed to save welcomed cache: {e}")

# ---------- BOT WORKER ----------
def instagram_bot_worker(task_id, cfg, stop_event):
    """
    cfg: {
      username, password,
      group_ids (list),
      welcome_messages (list),
      delay (float), poll_interval (float)
    }
    """
    append_log(f"Task {task_id}: starting bot")
    BOT_STATUS["running"] = True
    BOT_STATUS["task_id"] = task_id
    BOT_STATUS["started_at"] = now_str()

    cl = Client()

    # Try to load existing saved session settings (if present)
    try:
        if os.path.exists(SESSION_PATH):
            try:
                cl.load_settings(SESSION_PATH)
                append_log("Loaded session settings from disk (will attempt reuse).")
            except Exception as e:
                append_log(f"Saved session load failed: {e}")
    except Exception as e:
        append_log(f"Session load error: {e}")

    # Try login (use credentials; instagrapi will reuse session if valid)
    try:
        append_log("Attempting login (this may reuse saved session)...")
        cl.login(cfg.get("username"), cfg.get("password"))
        try:
            cl.dump_settings(SESSION_PATH)
            append_log(f"Saved session to {SESSION_PATH}")
        except Exception as e:
            append_log(f"Could not save session: {e}")
    except Exception as e:
        append_log(f"Login failed: {e}")
        BOT_STATUS["running"] = False
        return

    # Prepare messages and groups
    welcome_messages = cfg.get("welcome_messages", [])
    if not welcome_messages:
        append_log("No welcome messages provided — stopping bot.")
        BOT_STATUS["running"] = False
        return

    group_ids = cfg.get("group_ids", [])
    if isinstance(group_ids, str):
        group_ids = [g.strip() for g in group_ids.split(",") if g.strip()]

    if not group_ids:
        append_log("No group IDs provided — stopping bot.")
        BOT_STATUS["running"] = False
        return

    append_log(f"Configured groups: {group_ids}")

    welcomed = load_welcomed_cache()
    delay = float(cfg.get("delay", 2))
    poll_interval = float(cfg.get("poll_interval", 6))

    append_log(f"Delay between messages: {delay}s, Poll interval: {poll_interval}s")

    # main loop
    try:
        while not stop_event.is_set():
            BOT_STATUS["last_ping"] = now_str()
            for thread_id in group_ids:
                if stop_event.is_set():
                    break
                try:
                    thread = cl.direct_thread(thread_id)
                    users = getattr(thread, "users", []) or []
                    for user in users:
                        if stop_event.is_set():
                            break
                        user_pk = getattr(user, "pk", None)
                        username = getattr(user, "username", None) or str(user_pk)
                        # skip welcoming self if username matches
                        if cfg.get("username") and username == cfg.get("username"):
                            continue
                        key = f"{thread_id}::{username}"
                        if key not in welcomed:
                            append_log(f"New member detected: @{username} in thread {thread_id}")
                            for m in welcome_messages:
                                if stop_event.is_set():
                                    break
                                try:
                                    text = m.replace("{username}", username)
                                    cl.direct_send(text, thread_ids=[thread_id])
                                    append_log(f"Sent to @{username} in {thread_id}: {text[:80]}")
                                except Exception as e_send:
                                    append_log(f"Send error to @{username} in {thread_id}: {e_send}")
                                    # fallback to user id if available
                                    try:
                                        if user_pk:
                                            cl.direct_send(text, user_ids=[user_pk])
                                            append_log(f"Fallback sent to @{username} by user id.")
                                    except Exception as e2:
                                        append_log(f"Fallback failed for @{username}: {e2}")
                                time.sleep(delay)
                            welcomed.add(key)
                            save_welcomed_cache(welcomed)
                except Exception as e_thread:
                    append_log(f"Error reading thread {thread_id}: {e_thread}")

            # responsive sleep
            slept = 0.0
            while slept < poll_interval:
                if stop_event.is_set():
                    break
                time.sleep(0.5)
                slept += 0.5
    except Exception as e:
        append_log(f"Worker exception: {e}")
    finally:
        BOT_STATUS["running"] = False
        BOT_STATUS["task_id"] = None
        append_log(f"Task {task_id}: stopped.")

# ---------- UI: Cyber Neon HTML ----------
PAGE_HTML = r'''
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Insta Multi Welcome Bot — Cyber Neon</title>
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;700;900&display=swap" rel="stylesheet">
<style>
:root{
  --bg1:#0f0c1a;
  --bg2:#0b0426;
  --neon1:#ff4dff;
  --neon2:#00f6ff;
  --accent:#9b59ff;
}
*{box-sizing:border-box}
body{
  margin:0; min-height:100vh; font-family: 'Nunito', sans-serif;
  background: radial-gradient(1200px 600px at 10% 10%, rgba(155,89,255,0.06), transparent 5%),
              linear-gradient(90deg,var(--bg1),var(--bg2));
  color:#dffaff; display:flex; align-items:center; justify-content:center; padding:30px;
}
.container{
  width:100%; max-width:1100px; border-radius:16px;
  background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));
  box-shadow: 0 10px 60px rgba(2,6,23,0.8), inset 0 1px 0 rgba(255,255,255,0.02);
  padding:22px; position:relative; overflow:hidden;
  border:1px solid rgba(255,255,255,0.03);
}
.bg-stripes{
  position:absolute; inset:0; pointer-events:none; opacity:0.08; background:
  repeating-linear-gradient(90deg, rgba(255,255,255,0.01) 0 1px, transparent 1px 60px);
  transform:skewY(-3deg);
  mix-blend-mode:overlay;
}
.header{
  display:flex; gap:12px; align-items:center; justify-content:space-between; margin-bottom:8px;
}
.brand{
  display:flex; gap:12px; align-items:center;
}
.logo{
  width:72px; height:72px; border-radius:12px;
  background: linear-gradient(135deg,var(--neon1),var(--neon2));
  box-shadow: 0 6px 30px rgba(0,246,255,0.08), 0 0 40px rgba(255,77,255,0.06);
  display:flex; align-items:center; justify-content:center; color:#081018; font-weight:900; font-size:18px;
}
.title{ font-size:20px; font-weight:800; letter-spacing:0.6px; color: #eaffff; text-shadow: 0 0 10px rgba(0,246,255,0.08); }
.subtitle{ color:#9fd8e8; font-size:13px; margin-top:3px; }

.grid{ display:grid; grid-template-columns: 1fr 420px; gap:18px; margin-top:12px; align-items:start; }
.card{
  background:transparent; padding:14px; border-radius:12px; border:1px solid rgba(255,255,255,0.03);
}
label{ display:block; color:#bfeffc; font-size:13px; margin-bottom:6px; }
.input, textarea, select {
  width:100%; padding:10px 12px; border-radius:10px; border:1px solid rgba(255,255,255,0.04);
  background:linear-gradient(180deg, rgba(255,255,255,0.01), rgba(255,255,255,0.02));
  color:#eafcff; font-size:14px; outline:none;
}
textarea{ min-height:120px; resize:vertical; }
.row{ display:flex; gap:12px; align-items:center; margin-bottom:12px; }
.small{ width:130px; }
.actions{ display:flex; gap:12px; align-items:center; margin-top:8px; }
.btn{
  padding:10px 16px; border-radius:10px; border:none; cursor:pointer; font-weight:800; letter-spacing:0.6px;
  background:linear-gradient(90deg,var(--neon2),var(--neon1)); color:#021020; box-shadow: 0 8px 30px rgba(0,246,255,0.06);
}
.btn.warn{ background:linear-gradient(90deg,#ff5f6d,#ffc371); color:#111; }
.note{ font-size:13px; color:#9fd8e8; margin-top:6px; }

.log-area{ background:linear-gradient(180deg, rgba(0,0,0,0.6), rgba(0,0,0,0.5)); padding:12px; border-radius:10px; max-height:560px; overflow:auto; }
.log-line{ font-family:monospace; font-size:12px; color:#cffefc; padding:4px 0; border-bottom:1px dashed rgba(255,255,255,0.02); }

.footer{ margin-top:12px; font-size:12px; color:#9fd8e8; text-align:center; }

/* neon pulse */
.neon-pill{
  display:inline-block; padding:8px 12px; border-radius:999px; background:rgba(0,246,255,0.06); color:var(--neon2);
  box-shadow: 0 6px 30px rgba(0,246,255,0.06), inset 0 -4px 20px rgba(0,246,255,0.02);
  font-weight:700;
}

/* typing animation */
@keyframes typing {
  0% { opacity: 0; transform: translateX(-6px); }
  100% { opacity: 1; transform: translateX(0); }
}
.subtitle .typing { animation: typing 1s ease forwards; }

.sound {
  width:34px; height:34px; border-radius:8px; background:linear-gradient(90deg,#111, #222); display:flex; align-items:center; justify-content:center; cursor:pointer;
}
.sound svg { filter: drop-shadow(0 4px 8px rgba(0,0,0,0.6)); }

@media (max-width:980px){
  .grid{ grid-template-columns: 1fr; }
  .logo{ width:56px; height:56px; font-size:16px;}
}
</style>
</head>
<body>
  <div class="container">
    <div class="bg-stripes"></div>
    <div class="header">
      <div class="brand">
        <div class="logo">IN</div>
        <div>
          <div class="title">INSTA MULTI WELCOME BOT</div>
          <div class="subtitle"><span class="typing">Cyber Neon • Auto-session • Multi-group • 24/7</span></div>
        </div>
      </div>
      <div style="display:flex; gap:10px; align-items:center;">
        <div class="neon-pill" id="status-pill">Stopped</div>
        <div class="sound" id="soundBtn" title="Toggle click sound">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M5 9v6h4l5 5V4L9 9H5z" stroke="#9ff" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </div>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <form id="controlForm">
          <label>Instagram Username</label>
          <input class="input" name="username" placeholder="username (will be saved to create session)" required />
          <label>Password</label>
          <input class="input" type="password" name="password" placeholder="password (only used to login)" required />
          <label>Welcome messages (each line = 1 message)</label>
          <textarea name="welcome_messages" class="input" placeholder="Welcome @{username}!\nHello @{username}, enjoy the group!"></textarea>
          <label>Group Chat IDs (comma separated)</label>
          <input class="input" name="group_ids" placeholder="24632887389663044,123456789012345" />
          <div class="row">
            <div style="flex:1">
              <label>Delay between messages (sec)</label>
              <input class="input small" name="delay" value="2" />
            </div>
            <div style="flex:1">
              <label>Poll interval (sec)</label>
              <input class="input small" name="poll_interval" value="6" />
            </div>
          </div>
          <div class="actions">
            <button type="button" class="btn" id="startBtn">Start Bot</button>
            <button type="button" class="btn warn" id="stopBtn">Stop Bot</button>
            <button type="button" class="btn" id="downloadSample">Download Sample</button>
          </div>
          <div class="note">Use <code>{username}</code> placeholder inside messages to mention user.</div>
        </form>
      </div>

      <div class="card log-area">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <div><strong>Live Logs</strong></div>
          <div style="font-size:12px; color:#9fd8e8">Task: <span id="taskId">—</span></div>
        </div>
        <div id="logs" style="max-height:440px; overflow:auto"></div>
        <div class="footer">Tip: Keep this service private. Session file saved to <code>/uploads/session.json</code>.</div>
      </div>
    </div>
  </div>

<script>
let soundOn = true;
const soundBtn = document.getElementById('soundBtn');
const startBtn = document.getElementById('startBtn');
const stopBtn = document.getElementById('stopBtn');
const statusPill = document.getElementById('status-pill');
const logsEl = document.getElementById('logs');
const taskIdEl = document.getElementById('taskId');

soundBtn.addEventListener('click', () => { soundOn = !soundOn; soundBtn.style.opacity = soundOn ? '1' : '0.5'; });

function playClick(){
  if(!soundOn) return;
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const o = ctx.createOscillator();
    const g = ctx.createGain();
    o.type = 'sine';
    o.frequency.value = 900;
    g.gain.value = 0.02;
    o.connect(g); g.connect(ctx.destination);
    o.start(); setTimeout(()=>{ o.stop(); ctx.close(); }, 80);
  } catch(e){}
}

async function fetchLogs(){
  try {
    const r = await fetch('/_status');
    const j = await r.json();
    logsEl.innerHTML = j.logs.map(l => `<div class="log-line">${l}</div>`).join('');
    taskIdEl.innerText = j.status.task_id || '—';
    statusPill.innerText = j.status.running ? 'Running' : 'Stopped';
    statusPill.style.background = j.status.running ? 'linear-gradient(90deg,#00f6ff,#ff4dff)' : 'rgba(0,0,0,0.6)';
    logsEl.scrollTop = logsEl.scrollHeight;
  } catch(e){}
}
setInterval(fetchLogs, 1500);
fetchLogs();

document.getElementById('downloadSample').addEventListener('click', ()=> {
  const sample = "Welcome @{username} 👋\\n===\\nHello @{username}, enjoy the group!\\n===\\nThanks for joining, @{username}!";
  const blob = new Blob([sample], {type:'text/plain'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = 'welcome_messages_sample.txt'; a.click();
  URL.revokeObjectURL(url);
});

startBtn.addEventListener('click', async () => {
  const form = document.getElementById('controlForm');
  const fd = new FormData(form);
  const wm = fd.get('welcome_messages') || '';
  if(!wm.trim()){ alert('Please add welcome messages (each line = 1 message)'); return; }
  playClick();
  startBtn.disabled = true;
  startBtn.innerText = 'Starting...';
  try {
    const res = await fetch('/start', { method: 'POST', body: fd });
    const j = await res.json();
    alert(j.message || (j.ok ? 'Bot started' : 'Error'));
  } catch(e){ alert('Start failed'); }
  startBtn.disabled = false;
  startBtn.innerText = 'Start Bot';
});

stopBtn.addEventListener('click', async () => {
  playClick();
  try {
    const res = await fetch('/stop', { method: 'POST' });
    const j = await res.json();
    alert(j.message || (j.ok ? 'Stopped' : 'Error'));
  } catch(e){ alert('Stop failed'); }
});
</script>
</body>
</html>
'''

# ---------- FLASK ENDPOINTS ----------
@APP.route("/")
def index():
    return render_template_string(PAGE_HTML)

@APP.route("/start", methods=["POST"])
def start_from_ui():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"ok": False, "message": "Bot already running."})

    username = (request.form.get("username") or "").strip()
    password = (request.form.get("password") or "").strip()
    raw_msgs = request.form.get("welcome_messages") or ""
    welcome_messages = [m.strip() for m in raw_msgs.splitlines() if m.strip()]
    group_ids_raw = (request.form.get("group_ids") or "").strip()
    group_ids = [g.strip() for g in group_ids_raw.split(",") if g.strip()]
    try:
        delay = float(request.form.get("delay") or 2)
    except:
        delay = 2.0
    try:
        poll_interval = float(request.form.get("poll_interval") or 6)
    except:
        poll_interval = 6.0

    # also support upload of a welcome file
    if "welcome_file" in request.files:
        f = request.files["welcome_file"]
        if f and f.filename:
            try:
                content = f.read().decode("utf-8")
                file_msgs = [m.strip() for m in content.splitlines() if m.strip()]
                if file_msgs:
                    welcome_messages = file_msgs
            except Exception as e:
                append_log(f"Failed to read uploaded welcome file: {e}")

    if not username or not password:
        return jsonify({"ok": False, "message": "Please provide username and password."})
    if not welcome_messages:
        return jsonify({"ok": False, "message": "Please provide at least one welcome message."})
    if not group_ids:
        return jsonify({"ok": False, "message": "Please provide group chat IDs."})

    STOP_EVENT.clear()
    task_id = f"TASK-{int(time.time())}"
    cfg = {
        "username": username,
        "password": password,
        "group_ids": group_ids,
        "welcome_messages": welcome_messages,
        "delay": delay,
        "poll_interval": poll_interval
    }
    with BOT_THREAD_LOCK:
        BOT_THREAD = threading.Thread(target=instagram_bot_worker, args=(task_id, cfg, STOP_EVENT), daemon=True)
        BOT_THREAD.start()
    append_log(f"Started bot task {task_id}")
    return jsonify({"ok": True, "message": "Bot started.", "task_id": task_id})

@APP.route("/stop", methods=["POST"])
def stop_from_ui():
    STOP_EVENT.set()
    append_log("Stop requested from UI")
    return jsonify({"ok": True, "message": "Stop signal sent."})

@APP.route("/_status")
def status_endpoint():
    return jsonify({
        "status": BOT_STATUS,
        "logs": LOGS[-400:]
    })

@APP.route("/download_session")
def download_session():
    if os.path.exists(SESSION_PATH):
        return send_file(SESSION_PATH, as_attachment=True, download_name="session.json")
    return jsonify({"ok": False, "message": "No session available."})

# ---------- RUN ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    append_lo
