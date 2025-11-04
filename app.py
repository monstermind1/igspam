import os
import threading
import time
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client

app = Flask(__name__)

# -------------------- GLOBAL VARIABLES --------------------
BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
SESSION_FILE = "session.json"


# -------------------- LOG FUNCTION --------------------
def log(msg):
    LOGS.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    print(msg)


# -------------------- BOT CORE --------------------
def run_bot(username, password, welcome_messages, group_ids, delay, poll_interval):
    cl = Client()
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(username, password)
            log("✅ Loaded existing session.")
        else:
            log("🔑 Logging in fresh...")
            cl.login(username, password)
            cl.dump_settings(SESSION_FILE)
            log("✅ Session saved.")
    except Exception as e:
        log(f"⚠️ Login failed: {e}")
        return

    log("🤖 Bot started — watching groups for new members...")
    welcomed_users = set()

    while not STOP_EVENT.is_set():
        try:
            for gid in group_ids:
                try:
                    group = cl.direct_thread(gid)
                    for user in group.users:
                        if user.pk not in welcomed_users and user.username != username:
                            msg = welcome_messages[int(time.time()) % len(welcome_messages)]
                            cl.direct_send(msg, thread_ids=[gid])
                            log(f"👋 Sent welcome to @{user.username} in group {gid}")
                            welcomed_users.add(user.pk)
                            time.sleep(delay)
                except Exception as e:
                    log(f"⚠️ Error in group {gid}: {e}")
            time.sleep(poll_interval)
        except Exception as e:
            log(f"⚠️ Loop error: {e}")

    log("🛑 Bot stopped.")


# -------------------- FLASK ROUTES --------------------
@app.route("/")
def index():
    return render_template_string(PAGE_HTML)


@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "⚙️ Bot already running."})

    username = request.form.get("username")
    password = request.form.get("password")
    welcome = request.form.get("welcome", "").splitlines()
    welcome = [m.strip() for m in welcome if m.strip()]
    group_ids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    delay = int(request.form.get("delay", 3))
    poll = int(request.form.get("poll", 10))

    if not username or not password or not group_ids or not welcome:
        return jsonify({"message": "⚠️ Please fill all fields."})

    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(target=run_bot, args=(username, password, welcome, group_ids, delay, poll))
    BOT_THREAD.start()
    log("🚀 Bot thread started.")
    return jsonify({"message": "✅ Bot started successfully!"})


@app.route("/stop", methods=["POST"])
def stop_bot():
    STOP_EVENT.set()
    log("🛑 Stop signal sent.")
    return jsonify({"message": "🛑 Bot stopped."})


@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-200:]})


# -------------------- FRONTEND (SIMPLE, FULLSCREEN HTML) --------------------
PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>INSTA MULTI WELCOME BOT</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500&display=swap');

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  padding: 0;
  font-family: 'Roboto', sans-serif;
  background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
  color: #fff;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
}

.container {
  width: 95%;
  max-width: 1000px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 20px;
  padding: 40px;
  box-shadow: 0 0 20px rgba(0,0,0,0.3);
}

h1 {
  text-align: center;
  margin-bottom: 30px;
  font-size: 32px;
  letter-spacing: 1px;
}

form {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
}

input, textarea {
  width: 90%;
  max-width: 900px;
  padding: 15px;
  margin: 10px 0;
  border: none;
  border-radius: 10px;
  background: rgba(255,255,255,0.1);
  color: #fff;
  font-size: 16px;
  outline: none;
}

textarea {
  resize: none;
  height: 120px;
}

button {
  width: 200px;
  margin: 15px 10px;
  padding: 15px;
  font-size: 16px;
  border: none;
  border-radius: 10px;
  background-color: #00bcd4;
  color: #fff;
  font-weight: 600;
  cursor: pointer;
  transition: 0.3s;
}
button:hover {
  background-color: #0097a7;
}

.buttons {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
}

.log-box {
  margin-top: 30px;
  width: 100%;
  height: 300px;
  background: rgba(0,0,0,0.4);
  border-radius: 10px;
  overflow-y: auto;
  padding: 15px;
  font-size: 14px;
  color: #c5e1e8;
  border: 1px solid rgba(255,255,255,0.2);
}
</style>
</head>
<body>
  <div class="container">
    <h1>INSTA MULTI WELCOME BOT</h1>
    <form id="botForm">
      <input type="text" name="username" placeholder="Instagram Username" required>
      <input type="password" name="password" placeholder="Password" required>
      <textarea name="welcome" placeholder="Enter multiple welcome messages (each line = 1 message)" required></textarea>
      <input type="text" name="group_ids" placeholder="Group Chat IDs (comma separated)" required>
      <input type="number" name="delay" placeholder="Delay between messages (seconds)" value="3">
      <input type="number" name="poll" placeholder="Poll interval (seconds)" value="10">
      <div class="buttons">
        <button type="button" onclick="startBot()">Start Bot</button>
        <button type="button" onclick="stopBot()">Stop Bot</button>
      </div>
    </form>
    <h3 style="text-align:center;">Logs</h3>
    <div class="log-box" id="logs"></div>
  </div>

<script>
async function startBot(){
  let form = new FormData(document.getElementById('botForm'));
  let res = await fetch('/start', {method:'POST', body: form});
  let data = await res.json();
  alert(data.message);
}
async function stopBot(){
  let res = await fetch('/stop', {method:'POST'});
  let data = await res.json();
  alert(data.message);
}
async function fetchLogs(){
  let res = await fetch('/logs');
  let data = await res.json();
  let box = document.getElementById('logs');
  box.innerHTML = data.logs.join('<br>');
  box.scrollTop = box.scrollHeight;
}
setInterval(fetchLogs, 2000);
</script>
</body>
</html>
"""

# -------------------- MAIN --------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
