import os
import threading
import time
import random
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
import json

app = Flask(__name__)
BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
SESSION_FILE = "session.json"
SESSION_TOKEN = ""
STATS = {"total_welcomed": 0, "today_welcomed": 0, "last_reset": datetime.now().date()}
BOT_CONFIG = {}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = f"[{ts}] {msg}"
    LOGS.append(lm)
    print(lm)

def load_session():
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, 'r') as f:
                data = json.load(f)
                log("📁 Session loaded successfully")
                return data
    except Exception as e:
        log(f"⚠️ Session load error: {str(e)}")
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
    return None

def login_client():
    global SESSION_TOKEN
    cl = Client()
    
    # Try session first
    session_data = load_session()
    if session_data:
        try:
            cl.load_settings(SESSION_FILE)
            cl.account_info()
            log("✅ Session login OK!")
            return cl
        except Exception as e:
            log(f"⚠️ Session invalid: {str(e)}")
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
    
    # Try token login
    if SESSION_TOKEN:
        try:
            cl.login_by_sessionid(SESSION_TOKEN)
            cl.dump_settings(SESSION_FILE)
            log("✅ Token login OK!")
            return cl
        except Exception as e:
            log(f"⚠️ Token fail: {str(e)[:50]}")
    
    log("🛑 No valid login method!")
    return None

MUSIC_EMOJIS = ["🎵", "🎶", "🎸", "🎹", "🎤", "🎧", "🎺", "🎷"]
FUNNY = ["Hahaha! 😂", "LOL! 🤣", "Mast! 😆", "Pagal! 🤪", "King! 👑😂"]
MASTI = ["Party! 🎉", "Masti! 🥳", "Dhamaal! 💃", "Full ON! 🔥", "Enjoy! 🎊"]

def run_bot():
    cl = login_client()
    if not cl:
        log("🛑 Login failed! Check token/session")
        return

    welcome_raw = BOT_CONFIG.get('welcome', 'Welcome!')
    welcome_messages = [m.strip() for m in welcome_raw.split('
') if m.strip()]
    group_ids = [g.strip() for g in BOT_CONFIG.get('group_ids', '').split(',') if g.strip()]
    admin_ids = [a.strip().lower() for a in BOT_CONFIG.get('admin_ids', '').split(',') if a.strip()]
    
    log("🚀 Bot started with token!")
    log(f"Groups: {len(group_ids)} | Admins: {len(admin_ids)}")
    
    known_members = {}
    last_messages = {}
    
    # Initialize groups
    for gid in group_ids:
        try:
            group = cl.direct_thread(gid)
            known_members[gid] = {user.pk for user in group.users}
            last_messages[gid] = group.messages[0].id if group.messages else None
            log(f"📊 Group {gid[:10]}... ready ({len(known_members[gid])} members)")
        except Exception as e:
            log(f"⚠️ Group {gid[:10]}... error: {str(e)[:30]}")
            known_members[gid] = set()
            last_messages[gid] = None

    global STATS
    if STATS["last_reset"] != datetime.now().date():
        STATS["today_welcomed"] = 0
        STATS["last_reset"] = datetime.now().date()

    while not STOP_EVENT.is_set():
        try:
            for gid in group_ids:
                if STOP_EVENT.is_set():
                    break
                    
                try:
                    group = cl.direct_thread(gid)
                    current_members = {user.pk for user in group.users}
                    
                    # Welcome new members
                    new_members = current_members - known_members[gid]
                    if new_members:
                        for user in group.users:
                            if user.pk in new_members and user.username:
                                if STOP_EVENT.is_set():
                                    break
                                log(f"🎉 NEW: @{user.username}")
                                for msg in welcome_messages:
                                    if STOP_EVENT.is_set():
                                        break
                                    final_msg = f"@{user.username} {msg}" if BOT_CONFIG.get('mention', 'yes') == 'yes' else msg
                                    cl.direct_send(final_msg, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    log(f"✅ Welcomed @{user.username}")
                                    time.sleep(int(BOT_CONFIG.get('delay', 3)))
                                known_members[gid].add(user.pk)
                    
                    known_members[gid] = current_members
                    
                except Exception as e:
                    log(f"⚠️ Group error: {str(e)[:50]}")
            
            time.sleep(int(BOT_CONFIG.get('poll', 10)))
            
        except Exception as e:
            log(f"⚠️ Bot loop error: {str(e)[:50]}")
            time.sleep(10)

    log("🛑 Bot stopped completely!")

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/set_token", methods=["POST"])
def set_token():
    global SESSION_TOKEN, BOT_CONFIG
    token = request.form.get("token", "").strip()
    if token:
        SESSION_TOKEN = token
        BOT_CONFIG.update({
            'token': token,
            'welcome': request.form.get("welcome", "Welcome brother! 🔥
Glad you joined! 👋"),
            'group_ids': request.form.get("group_ids", ""),
            'admin_ids': request.form.get("admin_ids", ""),
            'delay': request.form.get("delay", "3"),
            'poll': request.form.get("poll", "10"),
            'mention': request.form.get("mention", "yes")
        })
        log("🔑 Token set successfully!")
        return jsonify({"status": "success", "message": "Token saved!"})
    return jsonify({"status": "error", "message": "Token required!"})

@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"status": "running", "message": "Already running!"})
    
    if not SESSION_TOKEN:
        return jsonify({"status": "error", "message": "Set token first!"})
    
    if not BOT_CONFIG.get('group_ids') or not BOT_CONFIG.get('welcome'):
        return jsonify({"status": "error", "message": "Fill groups & welcome message!"})
    
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(target=run_bot, daemon=True)
    BOT_THREAD.start()
    log("🚀 24x7 Bot thread started!")
    return jsonify({"status": "started", "message": "Bot started!"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    global BOT_THREAD
    STOP_EVENT.set()
    log("🛑 Stop signal received!")
    return jsonify({"status": "stopping", "message": "Stopping..."})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-50:], "stats": STATS})

PAGE_HTML = '''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TOKEN BOT v4</title>
<style>
* {margin:0;padding:0;box-sizing:border-box;font-family:Arial,sans-serif;}
body {background:#000;color:#fff;padding:20px;min-height:100vh;}
.card {max-width:500px;margin:0 auto;background:rgba(10,10,30,0.9);border-radius:20px;padding:30px;border:2px solid #00ff88;box-shadow:0 0 30px rgba(0,255,136,0.3);}
h1 {text-align:center;color:#00ff88;font-size:2.5rem;margin-bottom:30px;text-shadow:0 0 20px #00ff88;}
.input-group {margin-bottom:20px;}
label {display:block;margin-bottom:8px;color:#00eaff;font-weight:bold;}
input,textarea,select {width:100%;padding:15px;border:2px solid #00eaff;border-radius:10px;background:rgba(0,0,0,0.5);color:#fff;font-size:16px;}
input:focus,textarea:focus,select:focus {outline:none;border-color:#00ff88;box-shadow:0 0 15px #00ff88;}
textarea {min-height:100px;}
.btn {width:100%;padding:18px;font-size:18px;font-weight:bold;border:none;border-radius:12px;cursor:pointer;margin:10px 0;transition:all 0.3s;}
.btn-token {background:linear-gradient(45deg,#00ff88,#00cc66);color:#000;box-shadow:0 5px 20px rgba(0,255,136,0.4);}
.btn-start {background:linear-gradient(45deg,#00eaff,#0072ff);color:#fff;box-shadow:0 5px 20px rgba(0,198,255,0.4);}
.btn-stop {background:linear-gradient(45deg,#ff4757,#ff3838);color:#fff;box-shadow:0 5px 20px rgba(255,71,87,0.4);}
.btn:hover {transform:translateY(-2px);box-shadow:0 8px 25px;}
.logs {background:rgba(0,0,0,0.7);border:2px solid #00eaff;border-radius:15px;padding:20px;height:250px;overflow-y:auto;font-family:monospace;font-size:14px;line-height:1.5;color:#00ff88;margin-top:20px;}
.status {text-align:center;padding:15px;border-radius:10px;margin:20px 0;font-weight:bold;}
.success {background:rgba(0,255,136,0.2);border:2px solid #00ff88;color:#00ff88;}
.error {background:rgba(255,71,87,0.2);border:2px solid #ff4757;color:#ff4757;}
.stats {display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:15px;margin:20px 0;}
.stat-card {background:rgba(0,255,136,0.1);border:2px solid #00ff88;border-radius:10px;padding:15px;text-align:center;}
</style>
</head>
<body>
<div class="card">
<h1>🔑 TOKEN BOT v4</h1>

<div id="status" class="status" style="display:none;"></div>

<div class="input-group">
<label>🔑 Session Token <span style="color:#ff4757;">*</span></label>
<input type="text" id="token" placeholder="56748960230%3AF8ELTyGZTkSadW...">
<button class="btn btn-token" onclick="setToken()">✅ SET TOKEN</button>
</div>

<div class="input-group">
<label>💬 Welcome Messages</label>
<textarea id="welcome">Welcome brother! 🔥
Glad you joined our group! 👋
Stay active 24x7! ⚡</textarea>
</div>

<div class="input-group">
<label>👥 Group IDs <span style="color:#ff4757;">*</span></label>
<input type="text" id="group_ids" placeholder="24632887389663044,12345678901234567">
</div>

<div class="input-group">
<label>👑 Admin IDs (optional)</label>
<input type="text" id="admin_ids" placeholder="username1,username2">
</div>

<div class="input-group">
<label>⏱️ Delay (seconds)</label>
<input type="number" id="delay" value="3" min="1" max="10">
</div>

<div class="input-group">
<label>🔄 Poll (seconds)</label>
<input type="number" id="poll" value="10" min="5" max="30">
</div>

<div class="input-group">
<label>@mention?</label>
<select id="mention">
<option value="yes">✅ Yes</option>
<option value="no">❌ No</option>
</select>
</div>

<button class="btn btn-start" onclick="startBot()" id="startBtn" style="display:none;">▶️ START BOT</button>
<button class="btn btn-stop" onclick="stopBot()" id="stopBtn" style="display:none;">🛑 STOP BOT</button>

<div class="stats" id="stats" style="display:none;">
<div class="stat-card"><strong>Total</strong><div id="totalCount">0</div></div>
<div class="stat-card"><strong>Today</strong><div id="todayCount">0</div></div>
</div>

<div class="logs" id="logs">Ready to start bot... 📱</div>
</div>

<script>
let botRunning = false;
function showStatus(msg, type) {
    const status = document.getElementById('status');
    status.textContent = msg;
    status.className = 'status ' + type;
    status.style.display = 'block';
    setTimeout(()=>status.style.display='none', 4000);
}

async function setToken() {
    const token = document.getElementById('token').value.trim();
    if(!token) {
        showStatus('❌ Token required!', 'error');
        return;
    }
    
    try {
        const form = new FormData();
        form.append('token', token);
        form.append('welcome', document.getElementById('welcome').value);
        form.append('group_ids', document.getElementById('group_ids').value);
        form.append('admin_ids', document.getElementById('admin_ids').value);
        form.append('delay', document.getElementById('delay').value);
        form.append('poll', document.getElementById('poll').value);
        form.append('mention', document.getElementById('mention').value);
        
        const res = await fetch('/set_token', {method:'POST', body:form});
        const data = await res.json();
        
        if(data.status === 'success') {
            showStatus('✅ Token set! Ready to start', 'success');
            document.getElementById('startBtn').style.display = 'block';
        } else {
            showStatus(data.message, 'error');
        }
    } catch(e) {
        showStatus('❌ Network error!', 'error');
    }
}

async function startBot() {
    try {
        const res = await fetch('/start', {method:'POST'});
        const data = await res.json();
        if(data.status === 'started') {
            showStatus('🚀 Bot started successfully!', 'success');
            botRunning = true;
            document.getElementById('startBtn').style.display = 'none';
            document.getElementById('stopBtn').style.display = 'block';
            document.getElementById('stats').style.display = 'grid';
        } else {
            showStatus(data.message, 'error');
        }
    } catch(e) {
        showStatus('❌ Start failed!', 'error');
    }
}

async function stopBot() {
    try {
        const res = await fetch('/stop', {method:'POST'});
        const data = await res.json();
        showStatus('🛑 Bot stopping...', 'error');
        botRunning = false;
        document.getElementById('stopBtn').style.display = 'none';
        document.getElementById('startBtn').style.display = 'block';
    } catch(e) {
        showStatus('❌ Stop failed!', 'error');
    }
}

setInterval(async()=>{
    try {
        const res = await fetch('/logs');
        const data = await res.json();
        document.getElementById('logs').innerHTML = data.logs.slice(-15).map(l=>'<div>'+l+'</div>').join('') || 'No logs...';
        document.getElementById('logs').scrollTop = 9999;
        document.getElementById('totalCount').textContent = data.stats.total_welcomed || 0;
        document.getElementById('todayCount').textContent = data.stats.today_welcomed || 0;
    } catch(e) {}
}, 2000);
</script>
</body>
</html>'''

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("🚀 TOKEN Instagram Welcome Bot v4.0")
    app.run(host="0.0.0.0", port=port, debug=False)
