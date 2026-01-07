import os
import threading
import time
import random
import json
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client

app = Flask(__name__)
BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
SESSION_FILE = "session.json"
TOKEN_FILE = "token.txt"
GROUP_CONFIG_FILE = "group_config.json"
STATS = {"total_welcomed": 0, "today_welcomed": 0, "last_reset": datetime.now().date()}
BOT_CONFIG = {"auto_replies": {}, "auto_reply_active": False}

GROUP_CHAT_ID = None

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = f"[{ts}] {msg}"
    LOGS.append(lm)
    print(lm)

MUSIC_EMOJIS = ["🎵", "🎶", "🎤", "🎸", "🥁", "🎹", "🎺", "🎷", "🥰", "❤️"]
LOVE_EMOJIS = ["❤️", "💕", "💖", "💗", "💓", "💞", "💘", "💝"]

cl = Client()
SESSION_LOADED = False

def load_session():
    global cl, SESSION_LOADED
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            log("✅ Session file loaded")
            SESSION_LOADED = True
            return True
        elif os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as f:
                session_id = f.read().strip()
            cl.login_by_sessionid(session_id)
            cl.dump_settings(SESSION_FILE)
            log("✅ Token login successful")
            SESSION_LOADED = True
            return True
        else:
            log("⚠️ No session/token - use dashboard")
            SESSION_LOADED = False
            return False
    except Exception as e:
        log(f"❌ Login failed: {str(e)}")
        SESSION_LOADED = False
        return False

def load_group_config():
    global GROUP_CHAT_ID
    try:
        if os.path.exists(GROUP_CONFIG_FILE):
            with open(GROUP_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                GROUP_CHAT_ID = config.get('group_chat_id')
                log(f"✅ Group config: {GROUP_CHAT_ID}")
    except:
        pass

def save_group_config():
    try:
        config = {'group_chat_id': GROUP_CHAT_ID}
        with open(GROUP_CONFIG_FILE, 'w') as f:
            json.dump(config, f)
    except:
        pass

def reset_daily_stats():
    global STATS
    today = datetime.now().date()
    if STATS["last_reset"] != today:
        STATS["today_welcomed"] = 0
        STATS["last_reset"] = today
        save_stats()

def save_stats():
    try:
        with open("stats.json", "w") as f:
            json.dump(STATS, f)
    except:
        pass

def load_stats():
    global STATS
    try:
        if os.path.exists("stats.json"):
            with open("stats.json", "r") as f:
                STATS.update(json.load(f))
    except:
        pass

def bot_loop():
    global BOT_THREAD, STOP_EVENT
    log("🤖 Instagram Group Bot Started")
    
    while not STOP_EVENT.is_set():
        try:
            if not SESSION_LOADED or not GROUP_CHAT_ID:
                time.sleep(5)
                continue
                
            reset_daily_stats()
            if STATS["today_welcomed"] >= 50:
                log("⏳ Daily limit reached (50)")
                time.sleep(300)
                continue
            
            threads = cl.direct_threads(amount=5)
            for thread in threads:
                if str(thread.id) == GROUP_CHAT_ID:
                    messages = thread.messages
                    if messages:
                        last_msg = messages[0]
                        msg_text = last_msg.text.lower() if last_msg.text else ""
                        
                        # ALL COMMANDS WORK FOR ANYONE
                        if msg_text.startswith('/'):
                            if "/start" in msg_text or "/help" in msg_text:
                                help_msg = "🤖 Bot Active!

👑 COMMANDS:
/start /help - Show this help
/stats - Statistics
/reply hello Namaste - Add auto reply
/stop - Pause bot

💬 Auto replies: " + str(len(BOT_CONFIG["auto_replies"])) + " triggers
📊 Today: " + str(STATS['today_welcomed']) + "/50"
                                cl.direct_send(help_msg, thread_id=GROUP_CHAT_ID)
                                log("✅ Help command executed")
                                
                            elif "/stats" in msg_text:
                                stats_msg = "📊 Stats:
Total: " + str(STATS['total_welcomed']) + "
Today: " + str(STATS['today_welcomed']) + "/50"
                                cl.direct_send(stats_msg, thread_id=GROUP_CHAT_ID)
                                log("✅ Stats command")
                                
                            elif "/stop" in msg_text:
                                STOP_EVENT.set()
                                cl.direct_send("⏹️ Bot paused by command", thread_id=GROUP_CHAT_ID)
                                log("✅ Stop command from group")
                                
                            elif msg_text.startswith("/reply "):
                                try:
                                    parts = msg_text.split(" ", 2)
                                    if len(parts) == 3:
                                        trigger, reply_msg = parts[1], parts[2]
                                        BOT_CONFIG["auto_replies"][trigger.lower()] = reply_msg
                                        BOT_CONFIG["auto_reply_active"] = True
                                        cl.direct_send(f"✅ Added: '{trigger}' → '{reply_msg[:30]}...'", thread_id=GROUP_CHAT_ID)
                                        log(f"➕ Reply added: {trigger}")
                                    else:
                                        cl.direct_send("❌ Format: /reply hello Namaste bhai", thread_id=GROUP_CHAT_ID)
                                except:
                                    cl.direct_send("❌ Error adding reply", thread_id=GROUP_CHAT_ID)
                        
                        # Auto replies for NON-COMMAND messages
                        elif BOT_CONFIG["auto_reply_active"] and not msg_text.startswith('/'):
                            for trigger, reply in BOT_CONFIG["auto_replies"].items():
                                if trigger in msg_text:
                                    emoji = random.choice(LOVE_EMOJIS + MUSIC_EMOJIS)
                                    cl.direct_send(reply + " " + emoji, thread_id=GROUP_CHAT_ID)
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    save_stats()
                                    log(f"📨 Auto reply triggered: {trigger}")
                                    break
            
            time.sleep(15)
            
        except Exception as e:
            log(f"⚠️ Bot error: {str(e)}")
            time.sleep(10)

def start_bot():
    global BOT_THREAD
    if BOT_THREAD is None or not BOT_THREAD.is_alive():
        STOP_EVENT.clear()
        BOT_THREAD = threading.Thread(target=bot_loop, daemon=True)
        BOT_THREAD.start()
        log("▶️ Bot started successfully")
    else:
        log("⚠️ Bot already running")

def stop_bot():
    global BOT_THREAD
    STOP_EVENT.set()
    if BOT_THREAD:
        BOT_THREAD.join(timeout=3)
        BOT_THREAD = None
    log("⏹️ Bot stopped successfully")

def disconnect_instagram():
    global SESSION_LOADED
    try:
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        SESSION_LOADED = False
        log("🔌 Disconnected: session & token deleted")
    except:
        pass

# DASHBOARD HTML
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>🤖 Instagram Group Bot Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: 'Poppins', sans-serif; background: linear-gradient(135deg, #0f0f23 0%, #2a2a4a 50%, #1a1a3a 100%); min-height:100vh; color: #e0e0e0; }
        .container { max-width:1400px; margin:0 auto; padding:20px; }
        .header { text-align:center; background: linear-gradient(45deg, #667eea, #764ba2); padding:30px; border-radius:25px; margin-bottom:30px; box-shadow: 0 25px 50px rgba(102, 126, 234, 0.3); }
        .header h1 { font-size:2.5em; font-weight:700; background: linear-gradient(45deg, #fff, #f0f0ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom:10px; }
        .header p { font-size:1.2em; opacity:0.9; }
        .glass-card { background: rgba(255,255,255,0.1); backdrop-filter: blur(20px); border-radius:25px; padding:30px; margin:20px 0; border: 1px solid rgba(255,255,255,0.2); box-shadow: 0 25px 50px rgba(0,0,0,0.2); transition: all 0.4s ease; }
        .glass-card:hover { transform: translateY(-10px); box-shadow: 0 35px 70px rgba(0,0,0,0.3); }
        .stats-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(280px,1fr)); gap:25px; margin:25px 0; }
        .stat-card { background: linear-gradient(145deg, rgba(255,255,255,0.15), rgba(255,255,255,0.05)); padding:30px; border-radius:20px; text-align:center; border: 1px solid rgba(255,255,255,0.1); }
        .stat-number { font-size:3.5em; font-weight:700; background: linear-gradient(45deg, #fff, #e0e0ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom:10px; }
        .stat-label { font-size:1.1em; opacity:0.9; font-weight:500; }
        .btn { padding:15px 35px; border:none; border-radius:50px; cursor:pointer; font-weight:600; font-size:16px; transition:all 0.3s; margin:8px; text-transform: uppercase; letter-spacing:1px; }
        .btn-primary { background: linear-gradient(45deg, #667eea, #764ba2); color:white; box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4); }
        .btn-success { background: linear-gradient(45deg, #00d4aa, #00b894); color:white; box-shadow: 0 10px 30px rgba(0, 212, 170, 0.4); }
        .btn-danger { background: linear-gradient(45deg, #ff6b6b, #ee5a52); color:white; box-shadow: 0 10px 30px rgba(255, 107, 107, 0.4); }
        .btn:hover { transform: translateY(-5px) scale(1.05); box-shadow: 0 20px 40px rgba(0,0,0,0.3); }
        .logs { max-height:450px; overflow-y:auto; background:rgba(0,0,0,0.3); border-radius:20px; padding:25px; font-family: monospace; font-size:13px; line-height:1.6; border: 1px solid rgba(255,255,255,0.1); }
        .form-group { margin:25px 0; }
        .form-group label { display:block; margin-bottom:12px; font-weight:600; color:#fff; font-size:1.1em; }
        .form-group input { width:100%; padding:18px; border:2px solid rgba(255,255,255,0.2); border-radius:15px; font-size:15px; background:rgba(255,255,255,0.1); color:#fff; }
        .status { padding:15px; border-radius:15px; margin:15px 0; font-weight:600; text-align:center; }
        .status.online { background: rgba(0, 255, 127, 0.2); color:#00ff7f; border: 1px solid rgba(0, 255, 127, 0.3); }
        .status.offline { background: rgba(255, 107, 107, 0.2); color:#ff6b6b; border: 1px solid rgba(255, 107, 107, 0.3); }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-robot"></i> Instagram Group Bot</h1>
            <p>Premium Automation Dashboard</p>
        </div>
        
        <div class="glass-card">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-number">{{ total_welcomed }}</div>
                    <div class="stat-label">Total Messages</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="color:#00d4aa;">{{ today_welcomed }}</div>
                    <div class="stat-label">Today (50 Max)</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="{% if bot_status %}color:#00ff7f;{% else %}color:#ff6b6b;{% endif %}">
                        {% if bot_status %}🟢 LIVE{% else %}🔴 STOPPED{% endif %}
                    </div>
                    <div class="stat-label">Bot Status</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" style="{% if session_status == 'Connected' %}color:#00d4aa;{% else %}color:#ff6b6b;{% endif %}">{{ session_status }}</div>
                    <div class="stat-label">Instagram</div>
                </div>
            </div>
        </div>

        <div class="glass-card">
            <h3 style="color:#fff; margin-bottom:25px; font-size:1.5em;">Bot Controls</h3>
            <button class="btn btn-success" onclick="toggleBot({{ 'true' if bot_status else 'false' }})">
                {% if bot_status %}STOP BOT{% else %}START BOT{% endif %}
            </button>
            <button class="btn btn-danger" onclick="disconnect()">DISCONNECT</button>
        </div>

        <div class="glass-card">
            <h3 style="color:#fff; margin-bottom:25px; font-size:1.5em;">Token Setup</h3>
            <div class="form-group">
                <label>Paste Instagram Session Token:</label>
                <input type="text" id="tokenInput" placeholder="73946433692%3A86Qq7BtIBfGquT...">
                <button class="btn btn-primary" onclick="setToken()" style="margin-top:15px;">Set Token</button>
            </div>
            <div id="tokenStatus" class="status offline">No token configured</div>
        </div>

        <div class="glass-card">
            <h3 style="color:#fff; margin-bottom:25px; font-size:1.5em;">Group Setup</h3>
            <div class="form-group">
                <label>Group Chat ID:</label>
                <input type="text" id="groupChatId" value="{{ group_chat_id or '' }}" placeholder="2032530394271295">
            </div>
            <button class="btn btn-success" onclick="setGroup()" style="margin-top:15px;">Save Group ID</button>
            <div id="groupStatus" class="status {% if group_chat_id %}online{% else %}offline{% endif %}">
                {% if group_chat_id %}Group Configured{% else %}No group configured{% endif %}
            </div>
        </div>

        <div class="glass-card">
            <h3 style="color:#fff; margin-bottom:25px; font-size:1.5em;">Live Logs</h3>
            <div class="logs" id="logsContainer">{{ logs_html|safe }}</div>
        </div>
    </div>

    <script>
        function toggleBot(currentStatus) {
            const action = currentStatus ? 'stop' : 'start';
            fetch(`/bot/${action}`).then(r => r.json()).then(() => location.reload());
        }

        function disconnect() {
            if(confirm('Disconnect?')) {
                fetch('/disconnect', {method: 'POST'}).then(() => location.reload());
            }
        }

        function setToken() {
            const token = document.getElementById('tokenInput').value.trim();
            if (!token) return alert('Enter token!');
            fetch('/set_token', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({token: token})
            }).then(r => r.json()).then(data => {
                if (data.success) {
                    document.getElementById('tokenStatus').innerHTML = 'Token Active';
                    document.getElementById('tokenStatus').className = 'status online';
                    alert('Token set!');
                } else alert('Error: ' + data.error);
            });
        }

        function setGroup() {
            const groupId = document.getElementById('groupChatId').value.trim();
            if (!groupId) return alert('Enter Group ID!');
            fetch('/config/group', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({group_id: groupId})
            }).then(r => r.json()).then(() => {
                document.getElementById('groupStatus').innerHTML = 'Group Configured';
                document.getElementById('groupStatus').className = 'status online';
                alert('Group ID saved!');
            });
        }

        setInterval(() => {
            fetch('/logs').then(r => r.text()).then(html => {
                document.getElementById('logsContainer').innerHTML = html;
                document.getElementById('logsContainer').scrollTop = document.getElementById('logsContainer').scrollHeight;
            });
        }, 3000);
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard():
    load_stats()
    load_group_config()
    logs_html = '<br>'.join(LOGS[-20:])
    session_status = "Connected" if SESSION_LOADED else "Disconnected"
    bot_status = BOT_THREAD and BOT_THREAD.is_alive() if BOT_THREAD else False
    
    return render_template_string(DASHBOARD_HTML, 
                                total_welcomed=STATS["total_welcomed"],
                                today_welcomed=STATS["today_welcomed"],
                                bot_status=bot_status,
                                session_status=session_status,
                                logs_html=logs_html,
                                group_chat_id=GROUP_CHAT_ID)

@app.route('/logs')
def get_logs():
    return '<br>'.join(LOGS[-50:])

@app.route('/set_token', methods=['POST'])
def api_set_token():
    try:
        data = request.json
        token = data.get('token', '').strip()
        cl.login_by_sessionid(token)
        cl.dump_settings(SESSION_FILE)
        with open(TOKEN_FILE, 'w') as f:
            f.write(token)
        global SESSION_LOADED
        SESSION_LOADED = True
        log(f"✅ Token set: {token[:20]}...")
        return jsonify({"success": True})
    except Exception as e:
        log(f"❌ Token error: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/config/group', methods=['POST'])
def api_set_group():
    global GROUP_CHAT_ID
    data = request.json
    GROUP_CHAT_ID = data.get('group_id')
    save_group_config()
    log(f"👥 Group set: {GROUP_CHAT_ID}")
    return jsonify({"success": True})

@app.route('/disconnect', methods=['POST'])
def api_disconnect():
    disconnect_instagram()
    stop_bot()
    return jsonify({"status": "disconnected"})

@app.route('/bot/start', methods=['POST'])
def api_start_bot():
    if load_session() and GROUP_CHAT_ID:
        start_bot()
        return jsonify({"status": "started"})
    return jsonify({"status": "error", "message": "Set token & group first"})

@app.route('/bot/stop', methods=['POST'])
def api_stop_bot():
    stop_bot()
    return jsonify({"status": "stopped"})

if __name__ == '__main__':
    load_session()
    load_stats()
    load_group_config()
    log("🚀 Instagram Group Bot Dashboard - http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
