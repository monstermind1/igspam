#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py - ULTRA SPEED Instagram Group Name Changer (Flask UI)
Use responsibly. This script attempts to log in and call Instagram mobile endpoints.
"""

import os
import time
import random
import threading
import requests
from collections import deque
from flask import Flask, render_template_string, request, jsonify, redirect, url_for

app = Flask(__name__)

# Shared state
worker_thread = None
worker_stop_event = threading.Event()
worker_lock = threading.Lock()
logs = deque(maxlen=2000)
state = {"running": False, "current_account": None, "error_count": 0, "accounts": []}


# ---------- Helpers ----------
def add_log(s: str):
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {s}"
    with worker_lock:
        logs.append(entry)
    print(entry, flush=True)


def smart_sleep_ms(ms):
    try:
        ms = float(ms)
    except:
        ms = 500.0
    if ms <= 1:
        time.sleep(0.001)
    else:
        time.sleep(ms / 1000.0)


def get_random_headers():
    user_agents = [
        "Instagram 155.0.0.37.107 Android",
        "Instagram 156.0.0.41.119 Android",
        "Instagram 157.0.0.32.118 Android",
        "Instagram 158.0.0.34.123 Android",
        "Instagram 159.0.0.12.116 Android",
    ]
    return {
        "User-Agent": random.choice(user_agents),
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-IG-App-ID": "936619743392459"
    }


# ---------- Instagram actions (best-effort) ----------
def insta_login(username, password):
    """
    Try to login and return a requests.Session or None.
    This is best-effort; Instagram changes often.
    """
    try:
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10)",
            "X-IG-App-ID": "936619743392459",
        }
        session.headers.update(headers)
        login_url = "https://www.instagram.com/accounts/login/ajax/"

        # GET to gather cookies & csrftoken
        r = session.get("https://www.instagram.com/accounts/login/", timeout=10)
        csrf = r.cookies.get("csrftoken", "")
        if csrf:
            session.headers.update({"X-CSRFToken": csrf})

        payload = {"username": username, "enc_password": f"#PWD_INSTAGRAM_BROWSER:0:{int(time.time())}:{password}"}
        res = session.post(login_url, data=payload, allow_redirects=True, timeout=10)

        # Heuristics for successful login
        text = res.text or ""
        if res.status_code == 200 and ('"authenticated":true' in text or '"authenticated": true' in text):
            return session
        if res.status_code == 200 and ("userId" in text or "status" in text):
            return session

        add_log(f"❌ Login failed for {username} (status {res.status_code})")
        return None
    except Exception as e:
        add_log(f"❌ Login error for {username}: {e}")
        return None


def change_group_name_safe(thread_id, new_name, session):
    """
    Attempt to change group title via i.instagram API (mobile).
    Returns (ok: bool, message: str)
    """
    url = f"https://i.instagram.com/api/v1/direct_v2/threads/{thread_id}/update_title/"
    headers = get_random_headers()
    data = {"title": new_name}
    try:
        r = session.post(url, headers=headers, data=data, timeout=12)
        if r.status_code == 200:
            return True, "OK"
        return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


# ---------- Worker ----------
def worker_run(accounts_list, thread_ids, names_list, delay_ms, err_threshold):
    """
    accounts_list: list of "username:password"
    thread_ids: list of thread ids
    names_list: list of names
    delay_ms: milliseconds pause between each group name change
    err_threshold: consecutive errors before switching account
    """
    add_log("🚀 Worker started")
    state["running"] = True
    state["current_account"] = None
    state["error_count"] = 0

    sessions_cache = [None] * len(accounts_list)
    account_index = 0
    name_index = 0

    try:
        while not worker_stop_event.is_set():
            # Ensure we have a session for current account
            if sessions_cache[account_index] is None:
                username, password = accounts_list[account_index].split(":", 1)
                add_log(f"🔑 Trying login: {username}")
                sess = insta_login(username, password)
                sessions_cache[account_index] = sess
                if sess:
                    add_log(f"✅ Logged in as {username}")
                    state["current_account"] = username
                    state["error_count"] = 0
                else:
                    add_log(f"⚠ Login failed for {username}, switching to next account")
                    account_index = (account_index + 1) % len(accounts_list)
                    continue

            session = sessions_cache[account_index]
            # pick next name
            if not names_list:
                add_log("⚠ No names provided, stopping worker")
                break
            name = names_list[name_index % len(names_list)].strip()
            name_index += 1
            suffix = random.choice(["🔥", "⚡", "💀", "✨", "🚀"])
            unique_name = f"{name}_{random.randint(1000,9999)}{suffix}"

            # apply to each thread id
            for tid in thread_ids:
                if worker_stop_event.is_set():
                    break
                tid = tid.strip()
                if not tid:
                    continue
                ok, resp = change_group_name_safe(tid, unique_name, session)
                if ok:
                    add_log(f"✅ [{tid}] -> {unique_name} (acc {account_index+1})")
                    state["error_count"] = 0
                else:
                    add_log(f"❌ [{tid}] -> {unique_name} | {resp}")
                    state["error_count"] += 1
                    if state["error_count"] >= err_threshold:
                        add_log("⚠️ Too many errors for this account, switching to next")
                        sessions_cache[account_index] = None
                        account_index = (account_index + 1) % len(accounts_list)
                        state["error_count"] = 0
                        break

                smart_sleep_ms(delay_ms)

            # continue infinite loop (names rotate)
            continue

    except Exception as e:
        add_log(f"❌ Worker exception: {e}")
    finally:
        state["running"] = False
        state["current_account"] = None
        add_log("🛑 Worker stopped")


# ---------- HTML (with neon design) ----------
INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>INSTA NC OFFLINE</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    
    body {
      font-family: 'Orbitron', 'Arial', sans-serif;
      background: #000;
      color: #fff;
      min-height: 100vh;
      overflow-x: hidden;
      position: relative;
    }
    
    /* Animated Background */
    .bg-container {
      position: fixed;
      inset: 0;
      z-index: 0;
      overflow: hidden;
    }
    
    .bg-image {
      position: absolute;
      inset: -10%;
      background: 
        linear-gradient(45deg, rgba(255,0,255,0.15), rgba(0,255,255,0.15)),
        url('https://images.unsplash.com/photo-1534796636912-3b95b3ab5986?w=1920&q=80');
      background-size: cover;
      background-position: center;
      filter: brightness(0.6) saturate(1.5);
      animation: zoomBg 20s ease-in-out infinite;
    }
    
    @keyframes zoomBg {
      0%, 100% { transform: scale(1.1) rotate(0deg); }
      50% { transform: scale(1.2) rotate(2deg); }
    }
    
    /* Floating Particles */
    .particle {
      position: absolute;
      background: radial-gradient(circle, rgba(255,255,255,0.8), transparent);
      border-radius: 50%;
      pointer-events: none;
      animation: float linear infinite;
    }
    
    @keyframes float {
      0% { transform: translateY(100vh) translateX(0) scale(0); opacity: 0; }
      10% { opacity: 1; }
      90% { opacity: 1; }
      100% { transform: translateY(-100vh) translateX(100px) scale(1); opacity: 0; }
    }
    
    /* Main Container */
    .container {
      position: relative;
      z-index: 10;
      max-width: 1400px;
      margin: 0 auto;
      padding: 40px 20px;
    }
    
    /* Header */
    .header {
      text-align: center;
      margin-bottom: 40px;
    }
    
    .header h1 {
      font-size: 3.5rem;
      font-weight: 900;
      background: linear-gradient(90deg, #ff00ff, #00ffff, #ffff00, #ff00ff);
      background-size: 200% auto;
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      animation: gradientText 3s linear infinite;
      text-shadow: 0 0 30px rgba(255,0,255,0.5);
      letter-spacing: 4px;
    }
    
    @keyframes gradientText {
      0% { background-position: 0% center; }
      100% { background-position: 200% center; }
    }
    
    .header p {
      color: #00ffff;
      font-size: 1.1rem;
      margin-top: 10px;
      text-shadow: 0 0 10px rgba(0,255,255,0.7);
    }
    
    /* Form Grid */
    .form-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 20px;
      margin-bottom: 30px;
    }
    
    .form-box {
      background: rgba(0,0,0,0.7);
      border: 2px solid;
      border-radius: 15px;
      padding: 25px;
      backdrop-filter: blur(10px);
      transition: all 0.3s ease;
      position: relative;
      overflow: hidden;
    }
    
    .form-box::before {
      content: '';
      position: absolute;
      inset: -2px;
      border-radius: 15px;
      padding: 2px;
      background: linear-gradient(45deg, currentColor, transparent);
      -webkit-mask: linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0);
      -webkit-mask-composite: xor;
      mask-composite: exclude;
      opacity: 0;
      transition: opacity 0.3s ease;
    }
    
    .form-box:hover::before {
      opacity: 1;
    }
    
    .form-box:hover {
      transform: translateY(-5px);
      box-shadow: 0 10px 30px currentColor;
    }
    
    .box-yellow { border-color: #ffff00; color: #ffff00; }
    .box-cyan { border-color: #00ffff; color: #00ffff; }
    .box-pink { border-color: #ff00ff; color: #ff00ff; }
    .box-green { border-color: #00ff00; color: #00ff00; }
    .box-orange { border-color: #ff8800; color: #ff8800; }
    .box-blue { border-color: #0088ff; color: #0088ff; }
    
    .form-box label {
      display: block;
      font-weight: 700;
      margin-bottom: 10px;
      font-size: 1.1rem;
      text-transform: uppercase;
      letter-spacing: 2px;
    }
    
    .form-box input,
    .form-box textarea {
      width: 100%;
      background: rgba(0,0,0,0.8);
      border: 2px solid currentColor;
      border-radius: 10px;
      padding: 15px;
      color: #fff;
      font-family: 'Orbitron', monospace;
      font-size: 1rem;
      transition: all 0.3s ease;
    }
    
    .form-box input:focus,
    .form-box textarea:focus {
      outline: none;
      box-shadow: 0 0 20px currentColor;
      background: rgba(0,0,0,0.95);
    }
    
    /* Two Column Layout */
    .row-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 20px;
    }
    
    /* Control Panel */
    .controls {
      display: flex;
      gap: 15px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 30px;
    }
    
    .btn {
      padding: 15px 35px;
      border: none;
      border-radius: 10px;
      font-family: 'Orbitron', sans-serif;
      font-weight: 700;
      font-size: 1.1rem;
      cursor: pointer;
      transition: all 0.3s ease;
      text-transform: uppercase;
      letter-spacing: 2px;
      position: relative;
      overflow: hidden;
    }
    
    .btn::before {
      content: '';
      position: absolute;
      top: 50%;
      left: 50%;
      width: 0;
      height: 0;
      border-radius: 50%;
      background: rgba(255,255,255,0.3);
      transform: translate(-50%, -50%);
      transition: width 0.6s, height 0.6s;
    }
    
    .btn:hover::before {
      width: 300px;
      height: 300px;
    }
    
    .btn span {
      position: relative;
      z-index: 1;
    }
    
    .btn-start {
      background: linear-gradient(135deg, #00ff00, #00ffff);
      color: #000;
      box-shadow: 0 5px 20px rgba(0,255,0,0.5);
    }
    
    .btn-start:hover {
      box-shadow: 0 8px 30px rgba(0,255,0,0.8);
      transform: translateY(-3px);
    }
    
    .btn-stop {
      background: linear-gradient(135deg, #ff0000, #ff00ff);
      color: #fff;
      box-shadow: 0 5px 20px rgba(255,0,0,0.5);
    }
    
    .btn-stop:hover {
      box-shadow: 0 8px 30px rgba(255,0,0,0.8);
      transform: translateY(-3px);
    }
    
    .btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
      transform: none !important;
    }
    
    /* Status Panel */
    .status-panel {
      background: linear-gradient(135deg, rgba(255,0,255,0.2), rgba(0,255,255,0.2));
      border: 2px solid #ff00ff;
      border-radius: 15px;
      padding: 20px;
      flex: 1;
      min-width: 300px;
    }
    
    .status-panel h3 {
      color: #ffff00;
      margin-bottom: 15px;
      font-size: 1.3rem;
      text-shadow: 0 0 10px rgba(255,255,0,0.7);
    }
    
    .status-item {
      display: flex;
      justify-content: space-between;
      margin-bottom: 10px;
      font-size: 1rem;
    }
    
    .status-item .label {
      color: #00ffff;
    }
    
    .status-item .value {
      color: #ff00ff;
      font-weight: 700;
    }
    
    /* Logs Section */
    .logs-section {
      background: rgba(0,0,0,0.8);
      border: 2px solid #00ff00;
      border-radius: 15px;
      padding: 25px;
      margin-top: 30px;
    }
    
    .logs-section h3 {
      color: #00ff00;
      margin-bottom: 15px;
      font-size: 1.5rem;
      text-shadow: 0 0 10px rgba(0,255,0,0.7);
    }
    
    #logs {
      background: #000;
      border: 2px solid #00ff00;
      border-radius: 10px;
      padding: 20px;
      color: #00ff00;
      font-family: 'Courier New', monospace;
      font-size: 0.95rem;
      max-height: 400px;
      overflow-y: auto;
      white-space: pre-wrap;
      word-wrap: break-word;
      box-shadow: inset 0 0 20px rgba(0,255,0,0.3);
    }
    
    #logs::-webkit-scrollbar {
      width: 10px;
    }
    
    #logs::-webkit-scrollbar-track {
      background: #000;
      border-radius: 10px;
    }
    
    #logs::-webkit-scrollbar-thumb {
      background: #00ff00;
      border-radius: 10px;
    }
    
    /* Footer */
    .footer {
      text-align: center;
      margin-top: 40px;
      color: #00ffff;
      font-size: 0.9rem;
      text-shadow: 0 0 10px rgba(0,255,255,0.5);
    }
    
    /* Responsive */
    @media(max-width: 768px) {
      .header h1 { font-size: 2rem; }
      .row-2 { grid-template-columns: 1fr; }
      .controls { flex-direction: column; }
      .status-panel { min-width: 100%; }
    }
  </style>
</head>
<body>
  <div class="bg-container">
    <div class="bg-image"></div>
  </div>
  
  <div class="container">
    <div class="header">
      <h1>✴️ INSTA NC OFFLINE SERVER</h1>
      <p>Multiple accounts, auto-switch, infinite loop, millisecond delay. Use responsibly.</p>
    </div>
    
    <form id="frm" onsubmit="startBot(event)">
      <div class="form-grid">
        <div class="form-box box-yellow">
          <label>🔑 ACCOUNTS (username:password, comma separated)</label>
          <input id="accounts" name="accounts" placeholder="username:password, username:password" required>
        </div>
        
        <div class="row-2">
          <div class="form-box box-cyan">
            <label>🎯 GROUP THREAD IDs</label>
            <input id="threads" name="threads" placeholder="1372945174421748, 1234567890" required>
          </div>
          
          <div class="form-box box-pink">
            <label>📝 GROUP NAMES</label>
            <input id="names" name="names" placeholder="instaKing, instaFire, instaFighter" required>
          </div>
        </div>
        
        <div class="row-2">
          <div class="form-box box-green">
            <label>⏱️ DELAY (milliseconds)</label>
            <input id="delay_ms" name="delay_ms" placeholder="500" value="500" required>
          </div>
          
          <div class="form-box box-orange">
            <label>⚠️ ERROR THRESHOLD</label>
            <input id="err_th" name="err_th" placeholder="3" value="3" required>
          </div>
        </div>
      </div>
      
      <div class="controls">
        <button id="btnStart" class="btn btn-start" type="submit">
          <span>🚀 START</span>
        </button>
        <button id="btnStop" class="btn btn-stop" type="button" onclick="stopBot()">
          <span>🛑 STOP</span>
        </button>
        
        <div class="status-panel">
          <h3>📊 STATUS MONITOR</h3>
          <div class="status-item">
            <span class="label">Status:</span>
            <span class="value" id="status">Stopped</span>
          </div>
          <div class="status-item">
            <span class="label">Current Account:</span>
            <span class="value" id="current_account">-</span>
          </div>
          <div class="status-item">
            <span class="label">Errors:</span>
            <span class="value" id="error_count">0</span>
          </div>
        </div>
      </div>
    </form>
    
    <div class="logs-section">
      <h3>📡 LIVE LOGS</h3>
      <pre id="logs">No logs yet.</pre>
    </div>
    
    <div class="footer">
      Made for testing — do not run at scale. Stop to halt the worker.
    </div>
  </div>

<script>
// Create floating particles
function createParticles() {
  const container = document.querySelector('.bg-container');
  for(let i = 0; i < 30; i++) {
    const particle = document.createElement('div');
    particle.className = 'particle';
    particle.style.left = Math.random() * 100 + '%';
    particle.style.width = (Math.random() * 4 + 2) + 'px';
    particle.style.height = particle.style.width;
    particle.style.animationDuration = (Math.random() * 10 + 10) + 's';
    particle.style.animationDelay = Math.random() * 5 + 's';
    container.appendChild(particle);
  }
}
createParticles();

function updateStatus(){
  fetch('/status').then(r=>r.json()).then(j=>{
    document.getElementById('status').innerText = j.running ? "🟢 Running" : "🔴 Stopped";
    document.getElementById('current_account').innerText = j.current_account || "-";
    document.getElementById('error_count').innerText = j.error_count || 0;
    document.getElementById('btnStart').disabled = j.running;
    document.getElementById('btnStop').disabled = !j.running;
  });
  fetch('/logs').then(r=>r.json()).then(j=>{
    const logs = j.logs.join('\
');
    const pre = document.getElementById('logs');
    pre.innerText = logs || "No logs yet.";
    pre.scrollTop = pre.scrollHeight;
  });
}
setInterval(updateStatus, 1000);
updateStatus();

function startBot(e){
  e.preventDefault();
  const form = document.getElementById('frm');
  const formData = new FormData(form);
  fetch('/start', {method:'POST', body: formData}).then(resp=>{
    if(resp.redirected){
      window.location = resp.url;
    } else {
      updateStatus();
    }
  });
}

function stopBot(){
  fetch('/stop', {method:'POST'}).then(()=>updateStatus());
}
</script>
</body>
</html>
"""

# ---------- Flask endpoints ----------
@app.route("/", methods=["GET"])
def index():
    return render_template_string(INDEX_HTML)


@app.route("/start", methods=["POST"])
def start():
    global worker_thread, worker_stop_event, logs, state

    if state.get("running"):
        return redirect(url_for("index"))

    accounts_raw = request.form.get("accounts", "").strip()
    threads_raw = request.form.get("threads", "").strip()
    names_raw = request.form.get("names", "").strip()
    delay_raw = request.form.get("delay_ms", "500").strip()
    err_th_raw = request.form.get("err_th", "3").strip()

    if not accounts_raw or not threads_raw or not names_raw:
        return "Missing fields", 400

    accounts_list = [a.strip() for a in accounts_raw.split(",") if ":" in a]
    thread_ids = [t.strip() for t in threads_raw.split(",") if t.strip()]
    names_list = [n.strip() for n in names_raw.split(",") if n.strip()]

    try:
        delay_ms = float(delay_raw)
        if delay_ms < 0: delay_ms = 500.0
    except:
        delay_ms = 500.0

    try:
        err_threshold = int(err_th_raw)
    except:
        err_threshold = 3

    state["accounts"] = accounts_list

    # clear logs
    with worker_lock:
        logs.clear()

    # reset stop event and start worker
    worker_stop_event.clear()
    worker_thread = threading.Thread(target=worker_run, args=(accounts_list, thread_ids, names_list, delay_ms, err_threshold), daemon=True)
    worker_thread.start()

    time.sleep(0.12)
    return redirect(url_for("index"))


@app.route("/stop", methods=["POST"])
def stop():
    global worker_stop_event
    worker_stop_event.set()
    return ("", 204)


@app.route("/logs", methods=["GET"])
def get_logs():
    with worker_lock:
        data = list(logs)
    return jsonify({"logs": data})


@app.route("/status", methods=["GET"])
def get_status():
    return jsonify({
        "running": state.get("running", False),
        "current_account": state.get("current_account", None),
        "error_count": state.get("error_count", 0)
    })


# ---------- Run ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"
    print(f"Starting Flask app on {host}:{port} ...")
    app.run(host=host, port=port, debug=False)
