# app.py - Fixed Flask control panel + Instagram welcome bot (Render-ready)
# Usage:
#   pip install -r requirements.txt
#   python app.py
# Then open the rendered URL (Render provides the public URL).

import os
import time
import json
import threading
from datetime import datetime
from flask import Flask, request, render_template_string, redirect, url_for, flash, jsonify, send_file
from werkzeug.utils import secure_filename

# instagrapi for Instagram automation
from instagrapi import Client

# --------------- CONFIG ---------------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
SESSION_PATH = os.path.join(UPLOAD_FOLDER, "session.json")
WELCOME_PATH = os.path.join(UPLOAD_FOLDER, "welcome_messages.txt")
WELCOME_CACHE = "welcomed_cache.json"
LOG_FILE = "bot_logs.txt"

# Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "replace-with-a-secure-random-key")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB upload limit

# Bot runtime globals
bot_thread = None
bot_thread_lock = threading.Lock()
bot_stop_event = None
bot_status = {"running": False, "task_id": None, "started_at": None, "last_ping": None}
bot_logs = []

def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    bot_logs.append(line)
    if len(bot_logs) > 2000:
        del bot_logs[:500]
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\\n")
    except Exception:
        pass
    print(line)

def load_welcomed_cache():
    if os.path.exists(WELCOME_CACHE):
        try:
            with open(WELCOME_CACHE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_welcomed_cache(cache_set):
    try:
        with open(WELCOME_CACHE, "w", encoding="utf-8") as f:
            json.dump(list(cache_set), f)
    except Exception as e:
        log(f"Error saving welcomed cache: {e}")

def instagram_bot_worker(task_id, cfg, stop_event):
    """
    Worker thread that polls group threads and sends multiple welcome messages to new users.
    cfg keys: username, password, session_file, group_ids, welcome_mode, welcome_file, single_message, delay, poll_interval
    """
    log(f"Task {task_id}: starting bot")
    bot_status["running"] = True
    bot_status["task_id"] = task_id
    bot_status["started_at"] = datetime.now().isoformat()
    cl = Client()

    # Load session if provided
    try:
        sess_path = cfg.get("session_file")
        if sess_path and os.path.exists(sess_path):
            try:
                with open(sess_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                cl.set_settings(settings)
                log("Loaded session settings from provided session file.")
                # Try to login using settings (may or may not re-authenticate)
                try:
                    cl.login(cfg.get("username") or "", cfg.get("password") or "")
                    log("Session validated via login attempt.")
                except Exception:
                    log("Login attempt after loading session settings failed (may still be authenticated).")
            except Exception as e:
                log(f"Saved session load failed: {e}. Will attempt fresh login if credentials provided.")
        elif os.path.exists(SESSION_PATH):
            try:
                with open(SESSION_PATH, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                cl.set_settings(settings)
                try:
                    cl.login(cfg.get("username") or "", cfg.get("password") or "")
                    log("Loaded local session.json and logged in.")
                except Exception:
                    log("Local session load: login after settings failed (session might still be valid).")
            except Exception as e:
                log(f"Local session load failed: {e}")
        else:
            log("No session file available on disk or provided upload.")
    except Exception as e:
        log(f"Session handling error: {e}")

    # If not logged in, try fresh login with username/password
    try:
        if not cl.authenticated:
            if cfg.get("username") and cfg.get("password"):
                log("Attempting fresh login with username & password...")
                cl.login(cfg["username"], cfg["password"])
                # save session to SESSION_PATH
                try:
                    with open(SESSION_PATH, "w", encoding="utf-8") as f:
                        json.dump(cl.get_settings(), f)
                    log("Saved new session to " + SESSION_PATH)
                except Exception as e:
                    log(f"Failed to save session: {e}")
            else:
                log("Not authenticated and no credentials supplied. Bot cannot proceed.")
                bot_status["running"] = False
                return
        else:
            log("Already authenticated with instagrapi client.")
    except Exception as e:
        log(f"Login failed: {e}")
        bot_status["running"] = False
        return

    # Prepare welcome messages
    welcome_messages = []
    try:
        mode = cfg.get("welcome_mode", "file")
        if mode == "file":
            path = cfg.get("welcome_file") or WELCOME_PATH
            if path and os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                welcome_messages = [m.strip() for m in content.split("===") if m.strip()]
                log(f"Loaded {len(welcome_messages)} messages from file.")
            else:
                log("Welcome file not found for mode 'file'.")
        elif mode == "single":
            single = cfg.get("single_message") or ""
            welcome_messages = [line.strip() for line in single.splitlines() if line.strip()]
            log(f"Using single-message input broken into {len(welcome_messages)} messages.")
        elif mode == "split_by_line":
            path = cfg.get("welcome_file") or WELCOME_PATH
            if path and os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                welcome_messages = [line.strip() for line in content.splitlines() if line.strip()]
                log(f"Loaded {len(welcome_messages)} lines as messages from file.")
            else:
                log("Welcome file not found (split_by_line).")
        else:
            log("Unknown welcome_mode; no messages loaded.")
    except Exception as e:
        log(f"Error preparing welcome messages: {e}")

    if not welcome_messages:
        log("No welcome messages to send. Stopping bot.")
        bot_status["running"] = False
        return

    # Prepare group ids
    group_ids = cfg.get("group_ids", [])
    if isinstance(group_ids, str):
        group_ids = [g.strip() for g in group_ids.split(",") if g.strip()]
    log(f"Configured group IDs: {group_ids}")

    # Load welcomed cache
    welcomed = load_welcomed_cache()

    delay = float(cfg.get("delay", 2))
    poll_interval = float(cfg.get("poll_interval", 6))
    log(f"Delay between messages: {delay}s, poll interval: {poll_interval}s")

    # Helper to send messages for a user in a thread
    def send_messages_to_thread(thread_id, target_username, target_user_pk=None):
        for m in welcome_messages:
            if stop_event.is_set():
                return
            msg = m.replace("{username}", target_username)
            try:
                cl.direct_send(msg, thread_ids=[thread_id])
                log(f"Sent to @{target_username} in thread {thread_id}: {msg[:60]}")
            except Exception as e:
                try:
                    if target_user_pk:
                        cl.direct_send(msg, user_ids=[target_user_pk])
                        log(f"Fallback: sent to @{target_username} by user id.")
                    else:
                        log(f"Send failed for @{target_username} in thread {thread_id}: {e}")
                except Exception as e2:
                    log(f"Final send error for @{target_username}: {e2}")
            time.sleep(delay)

    # MAIN LOOP: poll threads, find users, welcome new ones
    try:
        while not stop_event.is_set():
            bot_status["last_ping"] = datetime.now().isoformat()
            for thread_id in group_ids:
                if stop_event.is_set():
                    break
                try:
                    thread = cl.direct_thread(thread_id)
                    users = getattr(thread, "users", []) or []
                    for user in users:
                        if stop_event.is_set():
                            break
                        username = getattr(user, "username", None) or str(getattr(user, "pk", "unknown"))
                        user_pk = getattr(user, "pk", None)
                        # don't welcome self
                        if username == cfg.get("username"):
                            continue
                        key = f"{thread_id}::{username}"
                        if key not in welcomed:
                            log(f"New user detected: @{username} in thread {thread_id}")
                            send_messages_to_thread(thread_id, username, target_user_pk=user_pk)
                            welcomed.add(key)
                            save_welcomed_cache(welcomed)
                except Exception as e:
                    log(f"Error reading thread {thread_id}: {e}")
            for _ in range(int(max(1, poll_interval))):
                if stop_event.is_set():
                    break
                time.sleep(1)
    except Exception as e:
        log(f"Worker loop exception: {e}")
    finally:
        try:
            bot_status["running"] = False
            bot_status["task_id"] = None
            log(f"Task {task_id}: stopped.")
        except Exception:
            pass

# ----------------- Flask routes & UI ---------------
INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Insta Multi Welcome Bot</title>
  <style>
    body { margin:0; font-family: Inter, system-ui, Roboto, Arial; background: linear-gradient(120deg,#050518,#081122); color:#dff8ff; display:flex; align-items:center; justify-content:center; padding:24px; }
    .card{ width:100%; max-width:980px; background:rgba(8,10,20,0.78); padding:20px; border-radius:12px; }
    label{ display:block; font-size:13px; color:#bfeffc; margin-bottom:6px; }
    input, textarea, select { width:100%; padding:8px; border-radius:8px; border:1px solid rgba(255,255,255,0.04); background:rgba(255,255,255,0.02); color:#eafcff; margin-bottom:12px; }
    button{ padding:10px 14px; border-radius:10px; background:linear-gradient(90deg,#00f6ff,#7a4cff); border:none; color:#001218; font-weight:700; cursor:pointer; }
    pre{ white-space:pre-wrap; max-height:260px; overflow:auto; background:rgba(255,255,255,0.02); padding:8px; border-radius:8px; color:#dff8ff; }
  </style>
</head>
<body>
  <div class="card">
    <h2 style="color:#00f6ff; margin:0 0 10px 0">INSTA MULTI WELCOME BOT</h2>
    <form method="post" action="/start" enctype="multipart/form-data">
      <label>Instagram Username (optional if session.json uploaded)</label>
      <input name="username" type="text" />
      <label>Password (only for fresh login)</label>
      <input name="password" type="password" />
      <label>Upload session.json</label>
      <input name="session_file" type="file" accept=".json" />
      <label>Upload welcome_messages.txt (use === as separators)</label>
      <input name="welcome_file" type="file" accept=".txt" />
      <label>Or paste single welcome message (new lines => separate messages)</label>
      <textarea name="single_message" rows="3"></textarea>
      <label>Welcome mode</label>
      <select name="welcome_mode">
        <option value="file">File (===)</option>
        <option value="single">Single (split by newline)</option>
        <option value="split_by_line">Split by line</option>
      </select>
      <label>Group Chat IDs (comma separated)</label>
      <input name="group_ids" type="text" placeholder="e.g. 24632887389663044,123..." />
      <label>Delay between messages (sec)</label>
      <input name="delay" value="2" />
      <label>Poll interval (sec)</label>
      <input name="poll_interval" value="6" />
      <div style="margin-top:8px; display:flex; gap:8px;">
        <button type="submit">Start Bot</button>
        <button formaction="/stop" formmethod="post" style="background:linear-gradient(90deg,#ff5f6d,#ffc371);">Stop Bot</button>
        <a href="/download_sample"><button type="button" style="background:linear-gradient(90deg,#8be8a9,#7ab4ff); color:#001;">Download sample</button></a>
      </div>
    </form>
    <h4 style="margin-top:16px">Logs</h4>
    <pre id="logs">{{ logs }}</pre>
    <div style="margin-top:12px; font-size:13px; color:#bfeffc;">
      <div>Task: {{ status.task_id or '—' }}</div>
      <div>Started: {{ status.started_at or '—' }}</div>
      <div>Last ping: {{ status.last_ping or '—' }}</div>
      <div>Welcomed cache: {{ welcomed_count }}</div>
    </div>
  </div>
  <script>
    setInterval(()=>fetch('/status').then(r=>r.json()).then(d=>{ document.getElementById('logs').innerText = d.logs.join('\\n'); }),4000);
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    small_logs = bot_logs[-400:]
    welcomed = load_welcomed_cache()
    return render_template_string(INDEX_HTML, logs="\n".join(small_logs[::-1]) if small_logs else "No logs yet.", status=bot_status, welcomed_count=len(welcomed))

@app.route("/download_sample")
def download_sample():
    sample = ("Hey @{username} 👋 Welcome to the group! 🚀\n===\n🎉 @{username}, glad to have you here! 🥳\n===\nWelcome, @{username}!\n")
    path = os.path.join(UPLOAD_FOLDER, "sample_welcome.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(sample)
    return send_file(path, as_attachment=True, download_name="welcome_messages_sample.txt")

@app.route("/start", methods=["POST"])
def start_bot():
    global bot_thread, bot_stop_event
    if bot_status.get("running"):
        flash("Bot already running", "info")
        return redirect(url_for("index"))

    username = request.form.get("username") or ""
    password = request.form.get("password") or ""
    group_ids = request.form.get("group_ids") or ""
    delay = request.form.get("delay") or "2"
    poll_interval = request.form.get("poll_interval") or "6"
    welcome_mode = request.form.get("welcome_mode") or "file"
    single_message = request.form.get("single_message") or ""

    # handle file uploads
    session_file_path = None
    if "session_file" in request.files:
        f = request.files["session_file"]
        if f and f.filename:
            dest = os.path.join(app.config["UPLOAD_FOLDER"], "uploaded_session.json")
            f.save(dest)
            session_file_path = dest
            log(f"Uploaded session file saved to {dest}")

    welcome_file_path = None
    if "welcome_file" in request.files:
        f = request.files["welcome_file"]
        if f and f.filename:
            dest = os.path.join(app.config["UPLOAD_FOLDER"], "uploaded_welcome.txt")
            f.save(dest)
            welcome_file_path = dest
            log(f"Uploaded welcome file saved to {dest}")

    # if welcome file not uploaded but a server-side welcome file exists, use that
    if not welcome_file_path and os.path.exists(WELCOME_PATH):
        welcome_file_path = WELCOME_PATH

    cfg = {
        "username": username.strip() if username else None,
        "password": password.strip() if password else None,
        "session_file": session_file_path,
        "group_ids": group_ids,
        "welcome_mode": welcome_mode,
        "welcome_file": welcome_file_path,
        "single_message": single_message,
        "delay": float(delay),
        "poll_interval": float(poll_interval)
    }

    bot_stop_event = threading.Event()
    bot_task_id = f"TASK-{int(time.time())}"

    bot_thread = threading.Thread(target=instagram_bot_worker, args=(bot_task_id, cfg, bot_stop_event), daemon=True)
    bot_thread.start()
    log(f"Started bot task {bot_task_id}")
    return redirect(url_for("index"))

@app.route("/stop", methods=["POST"])
def stop_bot():
    global bot_stop_event
    if bot_stop_event:
        bot_stop_event.set()
        log("Stop signal sent to bot.")
    else:
        log("No active bot to stop.")
    return redirect(url_for("index"))

@app.route("/status")
def status_api():
    welcomed = load_welcomed_cache()
    return jsonify({
        "running": bot_status.get("running"),
        "task_id": bot_status.get("task_id"),
        "logs": bot_logs[-300:],
        "welcomed_count": len(welcomed)
    })

# -------------------- Run Flask --------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # debug=False is recommended on Render
    app.run(host="0.0.0.0", port=port, debug=False)
        
