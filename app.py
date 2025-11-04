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
    timestamp = datetime.now().strftime('%H:%M:%S')
    log_msg = f"[{timestamp}] {msg}"
    LOGS.append(log_msg)
    print(log_msg)


def run_bot(username, password, welcome_messages, group_ids, delay, poll_interval, use_custom_name, enable_commands):
    cl = Client()
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(username, password)
            log("Loaded existing session.")
        else:
            log("Logging in fresh...")
            cl.login(username, password)
            cl.dump_settings(SESSION_FILE)
            log("Session saved.")
    except Exception as e:
        log(f"Login failed: {e}")
        return

    log("Bot started - Monitoring for NEW members and COMMANDS...")
    
    known_members = {}
    last_message_ids = {}
    
    for gid in group_ids:
        try:
            group = cl.direct_thread(gid)
            known_members[gid] = {user.pk for user in group.users}
            last_message_ids[gid] = group.messages[0].id if group.messages else None
            log(f"Tracking {len(known_members[gid])} existing members in group {gid}")
        except Exception as e:
            log(f"Error loading group {gid}: {e}")
            known_members[gid] = set()
            last_message_ids[gid] = None

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
                    
                    if enable_commands:
                        new_messages = []
                        if last_message_ids[gid]:
                            for msg in group.messages:
                                if msg.id == last_message_ids[gid]:
                                    break
                                new_messages.append(msg)
                        
                        for msg in reversed(new_messages):
                            if msg.user_id == cl.user_id:
                                continue
                            
                            text = msg.text.strip().lower() if msg.text else ""
                            
                            if text in ["/help", "!help"]:
                                help_text = ("BOT COMMANDS

"
                                           "/help - Show this help menu
"
                                           "/stats - Show welcome statistics
"
                                           "/count - Show total members
"
                                           "/welcome - Manual welcome test
"
                                           "/ping - Check if bot is alive
"
                                           "/time - Show current time
"
                                           "/about - About this bot

"
                                           "Type any command to use!")
                                cl.direct_send(help_text, thread_ids=[gid])
                                log(f"Sent help menu to group {gid}")
                            
                            elif text in ["/stats", "!stats"]:
                                stats_text = (f"WELCOME STATISTICS

"
                                            f"Total Welcomed: {STATS['total_welcomed']}
"
                                            f"Today Welcomed: {STATS['today_welcomed']}
"
                                            f"Bot Status: Active
"
                                            f"Monitoring Groups: {len(group_ids)}")
                                cl.direct_send(stats_text, thread_ids=[gid])
                                log(f"Sent stats to group {gid}")
                            
                            elif text in ["/count", "!count"]:
                                member_count = len(group.users)
                                count_text = f"GROUP MEMBERS

Total Members: {member_count} members"
                                cl.direct_send(count_text, thread_ids=[gid])
                                log(f"Sent member count to group {gid}")
                            
                            elif text in ["/welcome", "!welcome"]:
                                sender = next((u for u in group.users if u.pk == msg.user_id), None)
                                if sender:
                                    test_msg = f"@{sender.username} This is a test welcome message!"
                                    cl.direct_send(test_msg, thread_ids=[gid])
                                    log(f"Sent test welcome to @{sender.username}")
                            
                            elif text in ["/ping", "!ping"]:
                                cl.direct_send("Pong! Bot is alive and running!", thread_ids=[gid])
                                log(f"Responded to ping in group {gid}")
                            
                            elif text in ["/time", "!time"]:
                                current_time = datetime.now().strftime("%I:%M %p, %d %b %Y")
                                time_text = f"CURRENT TIME

{current_time}"
                                cl.direct_send(time_text, thread_ids=[gid])
                                log(f"Sent time to group {gid}")
                            
                            elif text in ["/about", "!about"]:
                                about_text = ("ABOUT THIS BOT

"
                                            "Name: Instagram Welcome Bot
"
                                            "Version: 2.0
"
                                            "Features:
"
                                            "- Auto-welcome new members
"
                                            "- Command system
"
                                            "- Statistics tracking
"
                                            "- 24/7 monitoring

"
                                            "Created with love")
                                cl.direct_send(about_text, thread_ids=[gid])
                                log(f"Sent about info to group {gid}")
                        
                        if group.messages:
                            last_message_ids[gid] = group.messages[0].id
                    
                    current_members = {user.pk for user in group.users}
                    new_members = current_members - known_members[gid]
                    
                    if new_members:
                        for user in group.users:
                            if user.pk in new_members and user.username != username:
                                if STOP_EVENT.is_set():
                                    break
                                
                                for msg in welcome_messages:
                                    if STOP_EVENT.is_set():
                                        break
                                    
                                    if use_custom_name:
                                        final_msg = f"@{user.username} {msg}"
                                    else:
                                        final_msg = msg
                                    
                                    cl.direct_send(final_msg, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    log(f"Welcomed NEW member @{user.username} in group {gid}")
                                    log(f"Sent: {final_msg}")
                                    
                                    for _ in range(delay):
                                        if STOP_EVENT.is_set():
                                            break
                                        time.sleep(1)
                                    
                                    if STOP_EVENT.is_set():
                                        break
                                
                                known_members[gid].add(user.pk)
                    
                    known_members[gid] = current_members
                    
                except Exception as e:
                    log(f"Error checking group {gid}: {e}")
            
            if STOP_EVENT.is_set():
                break
            
            for _ in range(poll_interval):
                if STOP_EVENT.is_set():
                    break
                time.sleep(1)
                
        except Exception as e:
            log(f"Loop error: {e}")

    log(f"Bot stopped. Total welcomed: {STATS['total_welcomed']}")


@app.route("/")
def index():
    return render_template_string(PAGE_HTML)


@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "Bot already running."})

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
        return jsonify({"message": "Please fill all required fields."})

    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(
        target=run_bot, 
        args=(username, password, welcome, group_ids, delay, poll, use_custom_name, enable_commands), 
        daemon=True
    )
    BOT_THREAD.start()
    log("Bot thread started.")
    return jsonify({"message": "Bot started! Monitoring for new members and commands..."})


@app.route("/stop", methods=["POST"])
def stop_bot():
    global BOT_THREAD
    STOP_EVENT.set()
    log("Stop signal sent. Stopping bot...")
    
    if BOT_THREAD:
        BOT_THREAD.join(timeout=5)
    
    log("Bot stopped completely.")
    return jsonify({"message": "Bot stopped successfully!"})


@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-200:]})


@app.route("/stats")
def get_stats():
    return jsonify(STATS)


PAGE_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>INSTA COMMAND BOT</title><style>@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap');*{box-sizing:border-box;margin:0;padding:0}body{font-family:'Poppins',sans-serif;background:radial-gradient(circle at top left,#0f2027,#203a43,#2c5364);color:#fff;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}.container{width:100%;max-width:1200px;background:rgba(255,255,255,.08);border-radius:30px;padding:60px 50px;box-shadow:0 0 50px rgba(0,0,0,.5)}h1{text-align:center;margin-bottom:50px;color:#00eaff;font-size:42px;font-weight:700}.form-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:30px;margin-bottom:40px}.input-group{display:flex;flex-direction:column}label{margin-bottom:10px;color:#00eaff;font-size:18px;font-weight:600}input,textarea,select{width:100%;padding:18px 22px;border:2px solid rgba(0,234,255,.3);border-radius:15px;background:rgba(255,255,255,.1);color:#fff;font-size:17px}textarea{min-height:140px}.full-width{grid-column:1/-1}button{border:none;padding:20px 45px;font-size:20px;font-weight:700;border-radius:15px;color:#fff;margin:12px;cursor:pointer}.start{background:linear-gradient(135deg,#00c6ff,#0072ff)}.stop{background:linear-gradient(135deg,#ff512f,#dd2476)}.buttons{display:flex;justify-content:center;flex-wrap:wrap;margin-top:40px}.log-box{background:rgba(0,0,0,.6);border-radius:20px;padding:25px;font-size:16px;height:350px;overflow-y:auto;border:2px solid rgba(0,234,255,.3);font-family:monospace}.info-box{background:rgba(67,233,123,.1);border:2px solid rgba(67,233,123,.3);border-radius:15px;padding:20px;margin-bottom:30px;color:#43e97b}</style></head><body><div class="container"><h1>INSTA COMMAND BOT</h1><div class="info-box"><strong>AUTO WELCOME + COMMAND SYSTEM</strong><br>Auto welcomes new members<br>Responds to commands in group chat<br>Real-time statistics tracking</div><form id="botForm"><div class="form-grid"><div class="input-group"><label>Instagram Username</label><input type="text" name="username" placeholder="Enter Username"></div><div class="input-group"><label>Password</label><input type="password" name="password" placeholder="Enter Password"></div><div class="input-group full-width"><label>Welcome Messages</label><textarea name="welcome" placeholder="Line 1: Welcome!
Line 2: Enjoy!"></textarea></div><div class="input-group"><label>Mention Username?</label><select name="use_custom_name"><option value="yes">Yes - Add @username</option><option value="no">No - Plain message</option></select></div><div class="input-group"><label>Enable Commands?</label><select name="enable_commands"><option value="yes">Yes - Bot responds</option><option value="no">No - Only welcome</option></select></div><div class="input-group full-width"><label>Group Chat IDs</label><input type="text" name="group_ids" placeholder="123456,789012"></div><div class="input-group"><label>Delay (seconds)</label><input type="number" name="delay" value="3" min="1"></div><div class="input-group"><label>Check Interval</label><input type="number" name="poll" value="10" min="5"></div></div><div class="buttons"><button type="button" class="start" onclick="startBot()">Start Bot</button><button type="button" class="stop" onclick="stopBot()">Stop Bot</button></div></form><h3 style="text-align:center;color:#00eaff;margin-top:50px">Live Activity Logs</h3><div class="log-box" id="logs">Start the bot...</div></div><script>async function startBot(){let form=new FormData(document.getElementById('botForm'));let res=await fetch('/start',{method:'POST',body:form});let data=await res.json();alert(data.message)}async function stopBot(){let res=await fetch('/stop',{method:'POST'});let data=await res.json();alert(data.message)}async function fetchLogs(){let res=await fetch('/logs');let data=await res.json();let box=document.getElementById('logs');box.innerHTML=data.logs.length===0?"Start the bot...":data.logs.join('<br>');box.scrollTop=box.scrollHeight}setInterval(fetchLogs,2000)</script></body></html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
