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
STATS = {"total_welcomed": 0, "today_welcomed": 0, "last_reset": datetime.now().date()}
BOT_CONFIG = {"auto_replies": {}, "auto_reply_active": False, "target_spam": {}, "spam_active": {}, "media_library": {}}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = f"[{ts}] {msg}"
    LOGS.append(lm)
    print(lm)

# Complete emoji lists
MUSIC_EMOJIS = ["🎵", "🎶", "🎤", "🎸", "🥁", "🎹", "🎺", "🎷", "🥰", "❤️"]
LOVE_EMOJIS = ["❤️", "💕", "💖", "💗", "💓", "💞", "💘", "💝"]
STAR_EMOJIS = ["⭐", "✨", "🌟", "💫", "⭐️"]

# Instagram Client
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
            log("✅ Token file login successful")
            SESSION_LOADED = True
            return True
            
        else:
            log("⚠️ No session or token found - use dashboard to set token")
            SESSION_LOADED = False
            return False
            
    except Exception as e:
        log(f"❌ Login failed: {str(e)}")
        SESSION_LOADED = False
        return False

def save_session():
    try:
        if SESSION_LOADED:
            cl.dump_settings(SESSION_FILE)
            log("💾 Session saved")
    except Exception as e:
        log(f"❌ Save session failed: {str(e)}")

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
    log("🤖 Instagram Bot started")
    
    while not STOP_EVENT.is_set():
        try:
            if not SESSION_LOADED:
                time.sleep(5)
                continue
                
            reset_daily_stats()
            if STATS["today_welcomed"] >= 50:
                log("⏳ Daily limit reached (50)")
                time.sleep(300)  # Wait 5 min
                continue
            
            threads = cl.direct_threads(amount=10)
            for thread in threads:
                messages = thread.messages
                if messages:
                    last_msg = messages[0].text.lower() if messages[0].text else ""
                    
                    replied = False
                    for trigger, reply in BOT_CONFIG["auto_replies"].items():
                        if trigger in last_msg and BOT_CONFIG["auto_reply_active"]:
                            emoji = random.choice(LOVE_EMOJIS + MUSIC_EMOJIS)
                            cl.direct_send(f"{reply} {emoji}", thread_id=thread.id)
                            STATS["total_welcomed"] += 1
                            STATS["today_welcomed"] += 1
                            save_stats()
                            log(f"📨 Auto replied to {thread.users[0].username}")
                            replied = True
                            break
                    
                    if not replied and ("hi" in last_msg or "hello" in last_msg or "hey" in last_msg):
                        welcome_msg = random.choice([
                            "Namaste! Kaise ho? ❤️",
                            "Hello! Welcome dost! 🎶", 
                            "Hi! Kya haal hai? ⭐✨"
                        ])
                        cl.direct_send(welcome_msg, thread_id=thread.id)
                        STATS["total_welcomed"] += 1
                        STATS["today_welcomed"] += 1
                        save_stats()
                        log(f"👋 Welcomed {thread.users[0].username}")
            
            time.sleep(30)
            
        except Exception as e:
            log(f"⚠️ Bot error: {str(e)}")
            time.sleep(10)

def start_bot():
    global BOT_THREAD
    if BOT_THREAD is None or not BOT_THREAD.is_alive():
        STOP_EVENT.clear()
        BOT_THREAD = threading.Thread(target=bot_loop, daemon=True)
        BOT_THREAD.start()
        log("▶️ Bot started")
    else:
        log("⚠️ Bot already running")

def stop_bot():
    global BOT_THREAD
    STOP_EVENT.set()
    if BOT_THREAD:
        BOT_THREAD.join(timeout=2)
    BOT_THREAD = None
    log("⏹️ Bot stopped")

# COMPLETE DASHBOARD HTML with TOKEN INPUT
DASHBOARD_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Instagram Bot Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family: 'Segoe UI', sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height:100vh; }
        .container { max-width:1200px; margin:0 auto; padding:20px; }
        .card { background: rgba(255,255,255,0.95); border-radius:20px; padding:25px; margin:15px 0; box-shadow: 0 20px 40px rgba(0,0,0,0.1); backdrop-filter: blur(10px); }
        .stats-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(250px,1fr)); gap:20px; margin:20px 0; }
        .stat-card { background: linear-gradient(45deg, #ff6b6b, #feca57); color:white; padding:20px; border-radius:15px; text-align:center; }
        .btn { padding:12px 24px; border:none; border-radius:50px; cursor:pointer; font-weight:bold; font-size:14px; transition:all 0.3s; margin:5px; }
        .btn-primary { background: linear-gradient(45deg, #667eea, #764ba2); color:white; }
        .btn-success { background: linear-gradient(45deg, #11998e, #38ef7d); color:white; }
        .btn-danger { background: linear-gradient(45deg, #ff6b6b, #ee5a52); color:white; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 10px 20px rgba(0,0,0,0.2); }
        .logs { max-height:400px; overflow-y:auto; background:#f8f9fa; border-radius:10px; padding:15px; font-family:monospace; font-size:12px; line-height:1.5; }
        .form-group { margin:15px 0; }
        .form-group label { display:block; margin-bottom:8px; font-weight:600; color:#333; }
        .form-group input, .form-group textarea { width:100%; padding:12px; border:2px solid #e9ecef; border-radius:10px; font-size:14px; transition:border-color 0.3s; }
        .form-group input:focus, .form-group textarea:focus { outline:none; border-color:#667eea; }
        .status { padding:10px; border-radius:10px; margin:10px 0; font-weight:bold; }
        .status.online { background:#d4edda; color:#155724; }
        .status.offline { background:#f8d7da; color:#721c24; }
        h1 { text-align:center; color:white; margin-bottom:10px; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }
        .emoji { font-size:24px; margin-right:10px; }
        .token-input { font-size:12px; font-family:monospace; letter-spacing:1px; }
    </style>
</head>
<body>
    <div class="container">
        <h1><span class="emoji">🤖</span>Instagram Bot Dashboard<span class="emoji">📱</span></h1>
        
        <div class="card">
            <div class="stats-grid">
                <div class="stat-card">
                    <div style="font-size:32px;">{{ total_welcomed }}</div>
                    <div>Total Messages</div>
                </div>
                <div class="stat-card" style="background: linear-gradient(45deg, #48dbfb, #0abde3);">
                    <div style="font-size:32px;">{{ today_welcomed }}</div>
                    <div>Today</div>
                </div>
                <div class="stat-card" style="background: linear-gradient(45deg, #ff9ff3, #f368e0);">
                    <div style="font-size:32px;">{% if bot_status %}🟢 Live{% else %}🔴 Stopped{% endif %}</div>
                    <div>Bot Status</div>
                </div>
                <div class="stat-card" style="background: linear-gradient(45deg, #54a0ff, #2e86de);">
                    <div style="font-size:32px;">{{ session_status }}</div>
                    <div>Instagram</div>
                </div>
            </div>
        </div>

        <div class="card">
            <h3>🎛️ Bot Controls</h3>
            <button class="btn btn-success" onclick="toggleBot({{ 'true' if bot_status else 'false' }})">
                {% if bot_status %}⏹️ Stop Bot{% else %}▶️ Start Bot{% endif %}
            </button>
            <div class="status {% if session_status == 'Connected' %}online{% else %}offline{% endif %}">
                {{ session_status }}
            </div>
        </div>

        <div class="card">
            <h3>🔑 Token Setup</h3>
            <div class="form-group">
                <label>Paste Instagram Token Here:</label>
                <input type="text" id="tokenInput" class="token-input" placeholder="73946433692%3A86Qq7BtIBfGquT...">
                <button class="btn btn-primary" onclick="setToken()" style="margin-top:10px;">✅ Set Token</button>
            </div>
            <div id="tokenStatus" class="status offline" style="font-size:12px;">No token set</div>
        </div>

        <div class="card">
            <h3>⚙️ Auto Reply Setup</h3>
            <div class="form-group">
                <label>Enable Auto Reply</label>
                <input type="checkbox" id="autoReplyToggle" {% if auto_reply_active %}checked{% endif %} onchange="toggleAutoReply()">
            </div>
            <div class="form-group">
                <label>Trigger Word</label>
                <input type="text" id="triggerWord" placeholder="hello">
            </div>
            <div class="form-group">
                <label>Reply Message</label>
                <textarea id="replyMsg" placeholder="Namaste! Kaise ho? ❤️">Namaste! Kaise ho? ❤️</textarea>
            </div>
            <button class="btn btn-primary" onclick="addAutoReply()">➕ Add Reply</button>
        </div>

        <div class="card">
            <h3>📋 Recent Logs</h3>
            <div class="logs" id="logsContainer">{{ logs_html|safe }}</div>
        </div>
    </div>

    <script>
        function toggleBot(currentStatus) {
            const action = currentStatus ? 'stop' : 'start';
            fetch(`/bot/${action}`)
                .then(r => r.json())
                .then(data => location.reload());
        }

        function setToken() {
            const token = document.getElementById('tokenInput').value.trim();
            if (!token) {
                alert('❌ Token enter karo!');
                return;
            }
            
            fetch('/set_token', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({token: token})
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    document.getElementById('tokenStatus').innerHTML = '✅ Token set successfully!';
                    document.getElementById('tokenStatus').className = 'status online';
                    alert('🎉 Token set ho gaya! Bot restart karo.');
                } else {
                    alert('❌ Token invalid: ' + data.error);
                }
            });
        }

        function toggleAutoReply() {
            const isActive = document.getElementById('autoReplyToggle').checked;
            fetch('/config/auto_reply', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({active: isActive})
            });
        }

        function addAutoReply() {
            const trigger = document.getElementById('triggerWord').value;
            const reply = document.getElementById('replyMsg').value;
            
            fetch('/config/add_reply', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({trigger: trigger, reply: reply})
            }).then(() => {
                alert('✅ Reply added!');
                document.getElementById('triggerWord').value = '';
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
'''

@app.route('/')
def dashboard():
    load_stats()
    logs_html = '<br>'.join(LOGS[-20:])
    session_status = "Connected" if SESSION_LOADED else "Disconnected"
    bot_status = BOT_THREAD and BOT_THREAD.is_alive() if BOT_THREAD else False
    
    return render_template_string(DASHBOARD_HTML, 
                                total_welcomed=STATS["total_welcomed"],
                                today_welcomed=STATS["today_welcomed"],
                                bot_status=bot_status,
                                session_status=session_status,
                                auto_reply_active=BOT_CONFIG["auto_reply_active"],
                                logs_html=logs_html)

@app.route('/logs')
def get_logs():
    return render_template_string('<br>'.join(LOGS[-50:]))

@app.route('/set_token', methods=['POST'])
def api_set_token():
    try:
        data = request.json
        token = data.get('token', '').strip()
        
        if not token:
            return jsonify({"success": False, "error": "No token provided"})
        
        cl.login_by_sessionid(token)
        cl.dump_settings(SESSION_FILE)
        
        with open(TOKEN_FILE, 'w') as f:
            f.write(token)
            
        global SESSION_LOADED
        SESSION_LOADED = True
        
        log(f"✅ Token set successfully: {token[:20]}...")
        return jsonify({"success": True})
    except Exception as e:
        log(f"❌ Token failed: {str(e)}")
        return jsonify({"success": False, "error": str(e)})

@app.route('/bot/start', methods=['POST'])
def api_start_bot():
    if load_session():
        start_bot()
        return jsonify({"status": "started"})
    return jsonify({"status": "error", "message": "Login first"})

@app.route('/bot/stop', methods=['POST'])
def api_stop_bot():
    stop_bot()
    return jsonify({"status": "stopped"})

@app.route('/config/auto_reply', methods=['POST'])
def api_toggle_auto_reply():
    data = request.json
    BOT_CONFIG["auto_reply_active"] = data.get('active', False)
    log(f"🔄 Auto reply {'enabled' if BOT_CONFIG['auto_reply_active'] else 'disabled'}")
    return jsonify({"status": "updated"})

@app.route('/config/add_reply', methods=['POST'])
def api_add_reply():
    data = request.json
    trigger = data.get('trigger', '').lower().strip()
    reply = data.get('reply', '').strip()
    
    if trigger and reply:
        BOT_CONFIG["auto_replies"][trigger] = reply
        log(f"➕ Added reply for '{trigger}' -> '{reply[:50]}...'")
    
    return jsonify({"status": "added"})

if __name__ == '__main__':
    load_session()
    load_stats()
    log("🚀 Instagram Bot Dashboard starting on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
