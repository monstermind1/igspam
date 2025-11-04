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
STATS = {
    "total_welcomed": 0,
    "today_welcomed": 0,
    "last_reset": datetime.now().date()
}


def log(msg):
    LOGS.append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    print(msg)


def run_bot(username, password, welcome_messages, group_ids, delay, poll_interval, use_custom_name, enable_commands):
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

    log("🤖 Bot started — Monitoring for NEW members and COMMANDS...")
    
    # Track existing members and last message IDs
    known_members = {}
    last_message_ids = {}
    
    for gid in group_ids:
        try:
            group = cl.direct_thread(gid)
            known_members[gid] = {user.pk for user in group.users}
            last_message_ids[gid] = group.messages[0].id if group.messages else None
            log(f"📊 Tracking {len(known_members[gid])} existing members in group {gid}")
        except Exception as e:
            log(f"⚠️ Error loading group {gid}: {e}")
            known_members[gid] = set()
            last_message_ids[gid] = None

    # Reset daily stats if new day
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
                    
                    # ==================== COMMAND HANDLING ====================
                    if enable_commands:
                        new_messages = []
                        if last_message_ids[gid]:
                            for msg in group.messages:
                                if msg.id == last_message_ids[gid]:
                                    break
                                new_messages.append(msg)
                        
                        for msg in reversed(new_messages):
                            if msg.user_id == cl.user_id:  # Skip bot's own messages
                                continue
                            
                            text = msg.text.strip().lower() if msg.text else ""
                            
                            # /help command
                            if text == "/help" or text == "!help":
                                help_text = """🤖 *BOT COMMANDS*

/help - Show this help menu
/stats - Show welcome statistics
/count - Show total members
/welcome - Manual welcome test
/ping - Check if bot is alive
/time - Show current time
/about - About this bot

Type any command to use!"""
                                cl.direct_send(help_text, thread_ids=[gid])
                                log(f"📝 Sent help menu to group {gid}")
                            
                            # /stats command
                            elif text == "/stats" or text == "!stats":
                                stats_text = f"""📊 *WELCOME STATISTICS*

Total Welcomed: {STATS['total_welcomed']}
Today Welcomed: {STATS['today_welcomed']}
Bot Status: ✅ Active
Monitoring Groups: {len(group_ids)}"""
                                cl.direct_send(stats_text, thread_ids=[gid])
                                log(f"📊 Sent stats to group {gid}")
                            
                            # /count command
                            elif text == "/count" or text == "!count":
                                member_count = len(group.users)
                                count_text = f"👥 *GROUP MEMBERS*

Total Members: {member_count} members"
                                cl.direct_send(count_text, thread_ids=[gid])
                                log(f"👥 Sent member count to group {gid}")
                            
                            # /welcome command (manual test)
                            elif text == "/welcome" or text == "!welcome":
                                sender = next((u for u in group.users if u.pk == msg.user_id), None)
                                if sender:
                                    test_msg = f"@{sender.username} This is a test welcome message! 👋"
                                    cl.direct_send(test_msg, thread_ids=[gid])
                                    log(f"🧪 Sent test welcome to @{sender.username}")
                            
                            # /ping command
                            elif text == "/ping" or text == "!ping":
                                cl.direct_send("🏓 Pong! Bot is alive and running!", thread_ids=[gid])
                                log(f"🏓 Responded to ping in group {gid}")
                            
                            # /time command
                            elif text == "/time" or text == "!time":
                                current_time = datetime.now().strftime("%I:%M %p, %d %b %Y")
                                time_text = f"🕐 *CURRENT TIME*

{current_time}"
                                cl.direct_send(time_text, thread_ids=[gid])
                                log(f"🕐 Sent time to group {gid}")
                            
                            # /about command
                            elif text == "/about" or text == "!about":
                                about_text = """ℹ️ *ABOUT THIS BOT*

Name: Instagram Welcome Bot
Version: 2.0
Features:
• Auto-welcome new members
• Command system
• Statistics tracking
• 24/7 monitoring

Created with ❤️"""
                                cl.direct_send(about_text, thread_ids=[gid])
                                log(f"ℹ️ Sent about info to group {gid}")
                        
                        # Update last message ID
                        if group.messages:
                            last_message_ids[gid] = group.messages[0].id
                    
                    # ==================== NEW MEMBER DETECTION ====================
                    current_members = {user.pk for user in group.users}
                    new_members = current_members - known_members[gid]
                    
                    if new_members:
                        for user in group.users:
                            if user.pk in new_members and user.username != username:
                                if STOP_EVENT.is_set():
                                    break
                                
                                # Send welcome messages to NEW member
                                for msg in welcome_messages:
                                    if STOP_EVENT.is_set():
                                        break
                                    
                                    # Add user's name/username if enabled
                                    if use_custom_name:
                                        final_msg = f"@{user.username} {msg}"
                                    else:
                                        final_msg = msg
                                    
                                    cl.direct_send(final_msg, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    log(f"🎉 Welcomed NEW member @{user.username} in group {gid}")
                                    log(f"   📤 Sent: '{final_msg}'")
                                    
                                    # Delay between messages
                                    for _ in range(delay):
                                        if STOP_EVENT.is_set():
                                            break
                                        time.sleep(1)
                                    
                                    if STOP_EVENT.is_set():
                                        break
                                
                                # Add to known members after welcoming
                                known_members[gid].add(user.pk)
                    
                    # Update known members
                    known_members[gid] = current_members
                    
                except Exception as e:
                    log(f"⚠️ Error checking group {gid}: {e}")
            
            if STOP_EVENT.is_set():
                break
            
            # Wait before checking again
            for _ in range(poll_interval):
                if STOP_EVENT.is_set():
                    break
                time.sleep(1)
                
        except Exception as e:
            log(f"⚠️ Loop error: {e}")

    log(f"🛑 Bot stopped. Total welcomed: {STATS['total_welcomed']}")


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
    use_custom_name = request.form.get("use_custom_name") == "yes"
    enable_commands = request.form.get("enable_commands") == "yes"

    if not username or not password or not group_ids or not welcome:
        return jsonify({"message": "⚠️ Please fill all required fields."})

    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(
        target=run_bot, 
        args=(username, password, welcome, group_ids, delay, poll, use_custom_name, enable_commands), 
        daemon=True
    )
    BOT_THREAD.start()
    log("🚀 Bot thread started.")
    return jsonify({"message": "✅ Bot started! Monitoring for new members and commands..."})


@app.route("/stop", methods=["POST"])
def stop_bot():
    global BOT_THREAD
    STOP_EVENT.set()
    log("🛑 Stop signal sent. Stopping bot...")
    
    if BOT_THREAD:
        BOT_THREAD.join(timeout=5)
    
    log("✅ Bot stopped completely.")
    return jsonify({"message": "✅ Bot stopped successfully!"})


@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-200:]})


@app.route("/stats")
def get_stats():
    return jsonify(STATS)


PAGE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>INSTA COMMAND BOT</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: 'Poppins', sans-serif;
  background: radial-gradient(circle at top left, #0f2027, #203a43, #2c5364);
  color: #fff;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  padding: 20px;
  overflow-x: hidden;
}

.container {
  width: 100%;
  max-width: 1200px;
  background: rgba(255,255,255,0.08);
  border-radius: 30px;
  padding: 60px 50px;
  box-shadow: 0 0 50px rgba(0,0,0,0.5);
  backdrop-filter: blur(10px);
}

h1 {
  text-align: center;
  margin-bottom: 50px;
  color: #00eaff;
  letter-spacing: 3px;
  font-size: 42px;
  font-weight: 700;
  text-transform: uppercase;
  text-shadow: 0 0 20px rgba(0,234,255,0.5);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 30px;
  margin-bottom: 40px;
}

.input-group {
  display: flex;
  flex-direction: column;
}

label {
  margin-bottom: 10px;
  color: #00eaff;
  font-size: 18px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.label-subtitle {
  font-size: 13px;
  color: #43e97b;
  font-weight: 400;
  text-transform: none;
  margin-top: 5px;
}

input, textarea, select {
  width: 100%;
  padding: 18px 22px;
  border: 2px solid rgba(0,234,255,0.3);
  border-radius: 15px;
  background: rgba(255,255,255,0.1);
  color: #fff;
  font-size: 17px;
  outline: none;
  transition: all 0.3s ease;
  font-family: 'Poppins', sans-serif;
}

input:focus, textarea:focus, select:focus {
  border-color: #00eaff;
  background: rgba(255,255,255,0.15);
  box-shadow: 0 0 15px rgba(0,234,255,0.4);
}

textarea {
  resize: vertical;
  min-height: 140px;
}

select {
  cursor: pointer;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='%2300eaff' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 15px center;
  background-size: 20px;
  padding-right: 50px;
}

select option {
  background: #203a43;
  color: #fff;
  padding: 10px;
}

.full-width {
  grid-column: 1 / -1;
}

.file-upload-wrapper {
  position: relative;
  width: 100%;
}

.file-upload-label {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 18px 22px;
  border: 2px dashed rgba(0,234,255,0.3);
  border-radius: 15px;
  background: rgba(255,255,255,0.1);
  color: #00eaff;
  font-size: 17px;
  cursor: pointer;
  transition: all 0.3s ease;
  font-weight: 500;
}

.file-upload-label:hover {
  border-color: #00eaff;
  background: rgba(255,255,255,0.15);
  box-shadow: 0 0 15px rgba(0,234,255,0.4);
}

.file-upload-input {
  display: none;
}

.file-name {
  margin-top: 10px;
  color: #43e97b;
  font-size: 14px;
  text-align: center;
}

button {
  border: none;
  padding: 20px 45px;
  font-size: 20px;
  font-weight: 700;
  border-radius: 15px;
  color: white;
  margin: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
  text-transform: uppercase;
  letter-spacing: 2px;
  box-shadow: 0 8px 20px rgba(0,0,0,0.3);
}

.start {
  background: linear-gradient(135deg, #00c6ff, #0072ff);
}
.stop {
  background: linear-gradient(135deg, #ff512f, #dd2476);
}
.sample {
  background: linear-gradient(135deg, #43e97b, #38f9d7);
}

button:hover {
  transform: translateY(-3px) scale(1.05);
  box-shadow: 0 12px 30px rgba(0,0,0,0.4);
}

button:active {
  transform: translateY(-1px) scale(1.02);
}

.buttons {
  display: flex;
  justify-content: center;
  flex-wrap: wrap;
  margin-top: 40px;
}

.log-section {
  margin-top: 50px;
}

h3 {
  text-align: center;
  margin-bottom: 20px;
  color: #00eaff;
  font-weight: 600;
  font-size: 28px;
  text-transform: uppercase;
  letter-spacing: 2px;
}

.log-box {
  background: rgba(0,0,0,0.6);
  border-radius: 20px;
  padding: 25px;
  font-size: 16px;
  line-height: 1.8;
  height: 350px;
  overflow-y: auto;
  border: 2px solid rgba(0,234,255,0.3);
  box-shadow: inset 0 0 20px rgba(0,0,0,0.5);
  font-family: 'Courier New', monospace;
}

.log-box::-webkit-scrollbar {
  width: 10px;
}

.log-box::-webkit-scrollbar-track {
  background: rgba(0,0,0,0.3);
  border-radius: 10px;
}

.log-box::-webkit-scrollbar-thumb {
  background: #00eaff;
  border-radius: 10px;
}

.info-box {
  background: rgba(67,233,123,0.1);
  border: 2px solid rgba(67,233,123,0.3);
  border-radius: 15px;
  padding: 20px;
  margin-bottom: 30px;
  color: #43e97b;
  font-size: 15px;
  line-height: 1.6;
}

.info-box strong {
  color: #00eaff;
}

.special-box {
  background: rgba(255,0,255,0.1);
  border: 2px solid rgba(255,0,255,0.4);
  border-radius: 15px;
  padding: 20px;
  margin-bottom: 30px;
  color: #ff00ff;
  font-size: 16px;
  line-height: 1.8;
  font-weight: 500;
}

.command-box {
  background: rgba(255,165,0,0.1);
  border: 2px solid rgba(255,165,0,0.4);
  border-radius: 15px;
  padding: 20px;
  margin-bottom: 30px;
  color: #ffa500;
  font-size: 15px;
  line-height: 1.8;
}

.command-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px;
  margin-top: 15px;
}

.command-item {
  background: rgba(0,0,0,0.3);
  padding: 10px;
  border-radius: 8px;
  font-family: monospace;
}

@media (max-width: 768px) {
  .container {
    padding: 40px 25px;
  }
  h1 {
    font-size: 32px;
    margin-bottom: 35px;
  }
  .form-grid {
    grid-template-columns: 1fr;
    gap: 25px;
  }
  button {
    width: 100%;
    margin: 8px 0;
  }
  label {
    font-size: 16px;
  }
  input, textarea, select {
    font-size: 15px;
    padding: 15px 18px;
  }
}

@media (max-width: 480px) {
  .container {
    padding: 30px 20px;
  }
  h1 {
    font-size: 26px;
  }
  button {
    font-size: 18px;
    padding: 16px 35px;
  }
}
</style>
</head>
<body>
  <div class="container">
    <h1>🤖 INSTA COMMAND BOT 🤖</h1>
    
    <div class="special-box">
      <strong>⚡ AUTO WELCOME + COMMAND SYSTEM ⚡</strong><br>
      ✅ Automatically welcomes new members<br>
      ✅ Responds to commands in group chat<br>
      ✅ Real-time statistics tracking<br>
      ✅ Interactive bot features
    </div>

    <div class="command-box">
      <strong>🎮 AVAILABLE COMMANDS:</strong>
      <div class="command-list">
        <div class="command-item">/help - Help menu</div>
        <div class="command-item">/stats - Statistics</div>
        <div class="command-item">/count - Member count</div>
        <div class="command-item">/welcome - Test welcome</div>
        <div class="command-item">/ping - Check bot</div>
        <div class="command-item">/time - Current time</div>
        <div class="command-item">/about - Bot info</div>
      </div>
      <div class="label-subtitle" style="margin-top: 15px;">
        Type any command in group chat to use! Works with / or ! prefix
      </div>
    </div>

    <div class="info-box">
      <strong>✨ HOW IT WORKS:</strong><br>
      • 🔍 <strong>Auto Welcome:</strong> Detects and welcomes new members<br>
      • 💬 <strong>Command System:</strong> Responds to commands in group<br>
      • 📊 <strong>Statistics:</strong> Tracks welcomes and activity<br>
      • 🎯 <strong>Interactive:</strong> Members can interact with bot
    </div>

    <form id="botForm">
      <div class="form-grid">
        <div class="input-group">
          <label>📱 Instagram Username</label>
          <input type="text" name="username" placeholder="Enter Instagram Username">
        </div>

        <div class="input-group">
          <label>🔒 Password</label>
          <input type="password" name="password" placeholder="Enter Password">
        </div>

        <div class="input-group full-width">
          <label>💬 Welcome Messages (each line = 1 message)</label>
          <textarea id="welcomeArea" name="welcome" placeholder="Enter multiple welcome messages here&#10;Line 1: Welcome to our group!&#10;Line 2: Glad you're here!&#10;Line 3: Feel free to introduce yourself!"></textarea>
        </div>

        <div class="input-group full-width">
          <label>📁 Or Upload TXT File (Optional)</label>
          <div class="file-upload-wrapper">
            <label for="fileUpload" class="file-upload-label">
              📂 Click to Upload Welcome Messages File
            </label>
            <input type="file" id="fileUpload" class="file-upload-input" accept=".txt" onchange="handleFileUpload(event)">
            <div id="fileName" class="file-name"></div>
          </div>
    
