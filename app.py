#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
app.py — ULTRA SPEED Instagram Bot (Flask web UI)

Features:
- Start / Stop buttons that work
- Background animated image / neon gradient
- Input: accounts (username:password, comma separated),
         group thread IDs (comma separated),
         names (comma separated),
         delay in milliseconds (number, e.g. 500)
- Infinite auto-loop over names
- Multi-account auto-switch on repeated errors (3 errors -> switch)
- Live logs shown on page (auto-poll every 1s)
- All logic runs in a background thread; UI controls the worker
- Safe use of threads and shared logs
- NOTE: change_group_name uses Instagram endpoints (best-effort). Use responsibly.

Run:
pip install flask requests rich pyfiglet playsound
python app.py
Open http://127.0.0.1:8000
"""

import os
import time
import random
import threading
import requests
from collections import deque
from flask import Flask, render_template_string, request, jsonify, redirect, url_for
from rich.console import Console
from rich.text import Text

console = Console()
app = Flask(__name__)

# ---- Shared worker state ----
worker_thread = None
worker_stop_event = threading.Event()
worker_lock = threading.Lock()
logs = deque(maxlen=1000)
state = {"running": False, "current_account": None, "error_count": 0, "accounts": []}


# ---- Small helpers ----
def add_log(s: str):
    ts = time.strftime("%H:%M:%S")
    entry = f"[{ts}] {s}"
    with worker_lock:
        logs.append(entry)
    console.print(Text(entry))


# ---- Instagram helper functions (best-effort) ----
def insta_login(username, password):
    """Attempt login and return session object or None. Best-effort; Instagram may change endpoints."""
    try:
        session = requests.Session()
        headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10)",
            "X-IG-App-ID": "936619743392459",
        }
        session.headers.update(headers)
        login_url = "https://www.instagram.com/accounts/login/ajax/"

        # fetch page to get CSRF
        r = session.get("https://www.instagram.com/accounts/login/", timeout=10)
        csrf = r.cookies.get("csrftoken", "")
        session.headers.update({"X-CSRFToken": csrf})

        payload = {"username": username, "enc_password": f"#PWD_INSTAGRAM_BROWSER:0:{int(time.time())}:{password}"}
        res = session.post(login_url, data=payload, allow_redirects=True, timeout=10)

        # Best-effort check for "authenticated":true in response text
        if res.status_code == 200 and (('"authenticated":true' in res.text) or ('"authenticated": true' in res.text)):
            return session
        # some accounts may return different shape; still attempt parse
        if res.status_code == 200 and "userId" in res.text:
            return session
        add_log(f"❌ Login failed for {username} (status {res.status_code})")
        return None
    except Exception as e:
        add_log(f"❌ Login error for {username}: {e}")
        return None


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


def change_group_name_safe(thread_id, new_name, session):
    """
    Try to change group name using Instagram mobile API endpoint.
    Returns (ok:bool, resp:str)
    """
    url = f"https://i.instagram.com/api/v1/direct_v2/threads/{thread_id}/update_title/"
    data = {"title": new_name}
    headers = get_random_headers()
    try:
        r = session.post(url, data=data, headers=headers, timeout=10)
        if r.status_code == 200:
            return True, "✅ Success"
        else:
            return False, f"HTTP {r.status_code}"
    except Exception as e:
        return False, str(e)


def smart_sleep_ms(ms):
    # clamp minimum to 1ms sleep to avoid busy spin
    try:
        ms = float(ms)
    except:
        ms = 500.0
    if ms <= 1:
        time.sleep(0.001)
    else:
        time.sleep(ms / 1000.0)


# ---- Worker thread ----
def worker_run(accounts_list, thread_ids, names_list, delay_ms):
    """
    accounts_list: list of "username:password"
    thread_ids: list of thread id strings
    names_list: list of names
    delay_ms: float milliseconds
    """
    add_log("🚀 Worker started")
    state["running"] = True
    state["current_account"] = None
    state["error_count"] = 0

    sessions_cache = [None] * len(accounts_list)  # store session objects
    account_index = 0
    name_index = 0

    try:
        while not worker_stop_event.is_set():
            # ensure session for current account
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
                    add_log(f"⚠ Login failed for {username}; switching to next account")
                    account_index = (account_index + 1) % len(accounts_list)
                    continue

            session = sessions_cache[account_index]
            # choose next name (infinite loop over names)
            name = names_list[name_index % len(names_list)].strip()
            name_index += 1
            suffix = random.choice(["🔥", "⚡", "💀", "✨", "🚀"])
            unique_name = f"{name}_{random.randint(1000,9999)}{suffix}"

            # try update for each thread id
            for tid in thread_ids:
                if worker_stop_event.is_set():
                    break
                tid = tid.strip()
                if not tid:
                    continue
                ok, resp = change_group_name_safe(tid, unique_name, session)
                ts = time.strftime("%H:%M:%S")
                if ok:
                    add_log(f"✅ [{tid}] -> {unique_name} (acc {account_index+1})")
                    state["error_count"] = 0
                else:
                    add_log(f"❌ [{tid}] -> {unique_name} | {resp}")
                    state["error_count"] += 1
                    # if repeated errors, switch account
                    if state["error_count"] >= 3:
                        add_log("⚠️ Too many errors for this account, switching to next")
                        sessions_cache[account_index] = None  # drop cached session
                        account_index = (account_index + 1) % len(accounts_list)
                        state["error_count"] = 0
                        break

                smart_sleep_ms(delay_ms)

            # continue infinite loop (names cycle)
            continue

    except Exception as e:
        add_log(f"❌ Worker exception: {e}")
    finally:
        state["running"] = False
        state["current_account"] = None
        add_log("🛑 Worker stopped")


# ---- HTML Template with background & animation ----
INDEX_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>ULTRA SPEED Instagram Bot</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;500;700&display=swap');
    :root{
      --bg1: #02121a;
      --bg2: #08121a;
      --accent: #7ee8fa;
      --accent2: #ff6bcb;
    }
    *{box-sizing:border-box;font-family:Inter, system-ui, Arial, sans-serif}
    body{
      margin:0; min-height:100vh; background: radial-gradient(ellipse at center, rgba(12,18,25,1) 0%, rgba(3,6,12,1) 60%), linear-gradient(120deg,#01162733, #0f172a22);
      color:#e6f1ff; display:flex; align-items:center; justify-content:center; padding:24px;
      overflow:hidden;
    }

    /* Animated neon background (CSS only) */
    .bg {
      position:fixed; inset:0; z-index:0; pointer-events:none;
      background:
        radial-gradient( circle at 10% 20%, rgba(126,232,250,0.06), transparent 8%),
        radial-gradient( circle at 80% 80%, rgba(255,107,203,0.05), transparent 8%),
        linear-gradient(90deg, rgba(7,18,27,0.8), rgba(2,6,12,0.9));
      animation: bgmove 12s linear infinite;
      filter: blur(18px) saturate(120%);
      opacity:0.95;
    }
    @keyframes bgmove{
      0%{transform:translateY(0px) scale(1)}
      50%{transform:translateY(-20px) scale(1.03)}
      100%{transform:translateY(0px) scale(1)}
    }

    .card{
      position:relative; z-index:2; width:100%; max-width:1100px; border-radius:14px; padding:20px;
      background: linear-gradient(180deg, rgba(3,10,18,0.75), rgba(2,6,12,0.85));
      box-shadow: 0 10px 40px rgba(2,10,20,0.6);
      border: 1px solid rgba(126,232,250,0.06);
    }

    .row{display:flex; gap:12px; flex-wrap:wrap}
    .col{flex:1; min-width:240px}
    h1{margin:0 0 6px 0; font-size:20px; color:var(--accent)}
    p.muted{color:#9bb7d6; margin:0 0 12px 0}

    label{display:block; font-size:13px; color:#9bdcff; margin:8px 0 6px}
    input[type=text], textarea{width:100%; padding:10px 12px; border-radius:8px; border:1px solid rgba(125,170,200,0.06); background:#031018; color:#e6f1ff}
    textarea{min-height:80px; resize:vertical}
    .controls{display:flex; gap:10px; margin-top:12px}
    button{
      padding:10px 14px; border-radius:10px; border:none; cursor:pointer; font-weight:600;
      box-shadow: 0 6px 18px rgba(0,0,0,0.6);
    }
    .btn-start{background:linear-gradient(90deg,#00d4ff,#7ee8fa); color:#021018}
    .btn-stop{background:linear-gradient(90deg,#ff6b6b,#ff9aa2); color:#fff}
    .muted-small{color:#7c98b3; font-size:13px}

    .status-box{background:#02131a; padding:12px; border-radius:8px; border:1px solid rgba(255,255,255,0.02)}
    pre#logs{background:transparent; color:#bfe9ff; padding:12px; border-radius:8px; max-height:320px; overflow:auto; margin:0; font-family:monospace; font-size:13px}

    footer{margin-top:12px; text-align:center; color:#6fa8c8; font-size:13px}
    @media (max-width:800px){
      .row{flex-direction:column}
    }
  </style>
</head>
<body>
  <div class="bg" aria-hidden="true"></div>

  <div class="card">
    <h1>🚀 ULTRA SPEED Instagram Bot (Web)</h1>
    <p class="muted">Enter multiple accounts as <code>username:password</code> (comma separated). Provide group thread IDs and names. Delay in milliseconds.</p>

    <form id="frm" method="post" action="/start" onsubmit="startBot(event)">
      <div class="row">
        <div class="col">
          <label>Accounts (comma separated)</label>
          <input id="accounts" name="accounts" placeholder="e.g. nfyter:x-223344, nfyte_r:g-223344" required>
          <div class="muted-small">Example: <code>nfyter:x-223344, nfyte_r:g-223344</code></div>
        </div>

        <div class="col">
          <label>Group Thread IDs (comma separated)</label>
          <input id="threads" name="threads" placeholder="e.g. 1372945174421748, 1234567890" required>
          <div class="muted-small">Enter numeric thread IDs (comma separated)</div>
        </div>
      </div>

      <label>Group Names (comma separated)</label>
      <input id="names" name="names" placeholder="e.g. Hacker, UltraSpeed, Matrix" required>

      <div class="row" style="margin-top:8px;">
        <div class="col">
          <label>Delay (milliseconds)</label>
          <input id="delay_ms" name="delay_ms" placeholder="500" value="500" required>
        </div>
        <div class="col">
          <label>Auto-retry on error threshold</label>
          <input id="err_threshold" name="err_threshold" placeholder="3" value="3" required>
          <div class="muted-small">How many consecutive errors before switching account (default 3)</div>
        </div>
      </div>

      <div class="controls">
        <button id="btnStart" class="btn-start" type="submit">Start</button>
        <button id="btnStop" class="btn-stop" type="button" onclick="stopBot()">Stop</button>
        <div style="flex:1"></div>
        <div class="status-box">
          <div>Status: <strong id="status">Stopped</strong></div>
          <div>Current Account: <span id="current_account">-</span></div>
          <div>Errors: <span id="error_count">0</span></div>
        </div>
      </div>
    </form>

    <hr style="border-color:#122233; margin:14px 0;">

    <div>
      <h4 style="margin:6px 0 6px 0">Live Logs</h4>
      <pre id="logs">No logs yet.</pre>
    </div>

    <footer>Made for testing — use responsibly. Press Stop to halt the worker.</footer>
  </div>

<script>
let polling = null;
function updateStatus(){
  fetch('/status').then(r=>r.json()).then(j=>{
    document.getElementById('status').innerText = j.running ? "Running" : "Stopped";
    document.getElementById('current_account').innerText = j.current_account || "-";
    document.getElementById('error_count').innerText = j.error_count || 0;
    document.getElementById('btnStart').disabled = j.running;
    document.getElementById('btnStop').disabled = !j.running;
  });
  fetch('/logs').then(r=>r.json()).then(j=>{
    const logs = j.logs.join('\\n');
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


# ---- Flask endpoints ----
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
    err_threshold_raw = request.form.get("err_threshold", "3").strip()

    if not accounts_raw or not threads_raw or not names_raw:
        return "Missing fields", 400

    accounts_list = [a.strip() for a in accounts_raw.split(",") if ":" in a]
    thread_ids = [t.strip() for t in threads_raw.split(",") if t.strip()]
    names_list = [n.strip() for n in names_raw.split(",") if n.strip()]

    try:
        delay_ms = float(delay_raw)
        if delay_ms < 0:
            delay_ms = 500.0
    except:
        delay_ms = 500.0

    try:
        err_threshold = int(err_threshold_raw)
    except:
        err_threshold = 3

    # update worker state settings
    state["accounts"] = accounts_list
    state["err_threshold"] = err_threshold

    # clear logs
    with worker_lock:
        logs.clear()

    # reset stop event and start worker
    worker_stop_event.clear()
    worker_thread = threading.Thread(target=worker_run, args=(accounts_list, thread_ids, names_list, delay_ms), daemon=True)
    worker_thread.start()

    time.sleep(0.1)
    return redirect(url_for("index"))


@app.route("/stop", methods=["POST"])
def stop():
    global worker_thread, worker_stop_event
    worker_stop_event.set()
    # wait briefly for thread to stop (non-blocking)
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


# ---- Run server ----
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"
    print(f"Starting Flask app on {host}:{port} ...")
    app.run(host=host, port=port, debug=False)
