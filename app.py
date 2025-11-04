import os
import threading
import time
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client

app = Flask(__name__)

BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
SESSION_FILE = "session.json"
WELCOME_FILE = "welcome_messages.txt"


def log(msg):
    timestamp = datetime.now().strftime("%H:%M:%S")
    LOGS.append(f"[{timestamp}] {msg}")
    print(msg)


def load_welcome_messages():
    """Read messages from welcome_messages.txt"""
    if not os.path.exists(WELCOME_FILE):
        open(WELCOME_FILE, "w").write("Welcome!\nHello there!\nGlad to have you here!")
    with open(WELCOME_FILE, "r", encoding="utf-8") as f:
        msgs = [x.strip() for x in f.readlines() if x.strip()]
    return msgs


def run_bot(username, password, group_ids, delay, poll):
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
    welcome_messages = load_welcome_messages()

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
            time.sleep(poll)
        except Exception as e:
            log(f"⚠️ Loop error: {e}")
    log("🛑 Bot stopped.")


@app.route("/")
def home():
    return render_template_string(PAGE_HTML)


@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "⚙️ Bot already running."})

    username = request.form.get("username")
    password = request.form.get("password")
    group_ids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    delay = int(request.form.get("delay", 3))
    poll = int(request.form.get("poll", 10))

    if not username or not password or not group_ids:
        return jsonify({"message": "⚠️ Please fill all fields."})

    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(target=run_bot, args=(username, password, group_ids, delay, poll))
    BOT_THREAD.start()
    log("🚀 Bot thread started.")
    return jsonify({"message": "✅ Bot started successfully!"})


@app.route("/stop", methods=["POST"])
def stop_bot():
    STOP_EVENT.set()
    log("🛑 Stop signal sent.")
    return jsonify({"message": "🛑 Bot stopped."})


@app.route("/logs")
def logs():
    return jsonify({"logs": LOGS[-150:]})


# ---------- FRONTEND ----------
PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>INSTA MULTI WELCOME BOT</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600&display=swap');
body {
  font-family: 'Poppins', sans-serif;
  background: linear-gradient(135deg, #000000 0%, #021421 100%);
  color: #00ffc8;
  height: 100vh;
  margin: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  align-items: center;
}
h1 {
  margin-top: 20px;
  font-size: 36px;
  color: #00ffc8;
  text-shadow: 0 0 20px #00ffc8;
}
.container {
  width: 90%;
  max-width: 1200px;
  background: rgba(0, 0, 0, 0.75);
  border: 2px solid #00ffc8;
  border-radius: 20px;
  padding: 30px;
  box-shadow: 0 0 40px #00ffc8;
  margin-top: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
}
input, textarea {
  width: 80%;
  max-width: 800px;
  background: rgba(255,255,255,0.05);
  border: 1px solid #00ffc8;
  border-radius: 10px;
  padding: 15px;
  color: #00ffc8;
  font-size: 16px;
  margin: 10px 0;
}
textarea {
  height: 120px;
}
button {
  background: #00ffc8;
  border: none;
  border-radius: 10px;
  padding: 15px 40px;
  margin: 10px;
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
  transition: 0.3s;
}
button:hover {
  background: #00e6b0;
}
.log-box {
  background: black;
  border: 1px solid #00ffc8;
  border-radius: 10px;
  height: 300px;
  overflow-y: auto;
  width: 90%;
  max-width: 1000px;
  padding: 15px;
  text-align: left;
  color: #00ffc8;
  font-size: 14px;
  margin-top: 15px;
}
.footer {
  color: #007760;
  margin-top: 10px;
  font-size: 13px;
}
</style>
</head>
<body>
  <h1>INSTA MULTI WELCOME BOT</h1>
  <div class="container">
    <form id="botForm">
      <input type="text" name="username" placeholder="Instagram Username" required><br>
      <input type="password" name="password" placeholder="Password" required><br>
      <input type="text" name="group_ids" placeholder="Group Chat IDs (comma separated)" required><br>
      <input type="number" name="delay" placeholder="Delay between messages (seconds)" value="3"><br>
      <input type="number" name="poll" placeholder="Poll interval (seconds)" value="10"><br>
      <button type="button" onclick="startBot()">🚀 Start Bot</button>
      <button type="button" onclick="stopBot()">🛑 Stop Bot</button>
    </form>
    <h3>Logs</h3>
    <div class="log-box" id="logs"></div>
    <div class="footer">Created by YK TRICKS INDIA</div>
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
    
