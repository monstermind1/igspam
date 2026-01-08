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
    lm = "[%s] %s" % (ts, msg)
    LOGS.append(lm)
    print(lm)

cl = Client()
SESSION_LOADED = False

def load_session():
    global cl, SESSION_LOADED
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            log("Session loaded")
            SESSION_LOADED = True
            return True
        elif os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as f:
                session_id = f.read().strip()
            cl.login_by_sessionid(session_id)
            cl.dump_settings(SESSION_FILE)
            log("Token login success")
            SESSION_LOADED = True
            return True
        else:
            log("No session/token found")
            SESSION_LOADED = False
            return False
    except Exception as e:
        log(f"Session load error: {str(e)}")
        SESSION_LOADED = False
        return False

def save_group_config():
    try:
        with open(GROUP_CONFIG_FILE, 'w') as f:
            json.dump({
                "group_chat_id": GROUP_CHAT_ID,
                "bot_config": BOT_CONFIG,
                "stats": STATS
            }, f, indent=2)
        log("Group config saved")
    except Exception as e:
        log(f"Config save error: {str(e)}")

def load_group_config():
    global GROUP_CHAT_ID, BOT_CONFIG, STATS
    try:
        if os.path.exists(GROUP_CONFIG_FILE):
            with open(GROUP_CONFIG_FILE, 'r') as f:
                config = json.load(f)
                GROUP_CHAT_ID = config.get("group_chat_id")
                BOT_CONFIG = config.get("bot_config", {"auto_replies": {}, "auto_reply_active": False})
                STATS = config.get("stats", {"total_welcomed": 0, "today_welcomed": 0, "last_reset": datetime.now().date()})
            log("Group config loaded")
    except Exception as e:
        log(f"Config load error: {str(e)}")

def reset_daily_stats():
    global STATS
    today = datetime.now().date()
    if STATS["last_reset"] != today:
        STATS["today_welcomed"] = 0
        STATS["last_reset"] = today
        log("Daily stats reset")

def welcome_new_member(user_id, username):
    global STATS
    reset_daily_stats()
    
    #  FIXED: Single line f-strings - No multi-line issues
    welcome_msgs = [" Welcome " + username + "! Group     ! "," Hey " + username + ", welcome to the family! ", 
        "  " + username + "!     "
    ]
    welcome_msg = random.choice(welcome_msgs)
    
    try:
        cl.direct_send(welcome_msg, [user_id])
        STATS["total_welcomed"] += 1
        STATS["today_welcomed"] += 1
        log(f"Welcomed {username} ({user_id})")
        save_group_config()
    except Exception as e:
        log(f"Welcome error for {username}: {str(e)}")

def bot_loop():
    global GROUP_CHAT_ID
    log("Bot started")
    
    while not STOP_EVENT.is_set():
        try:
            if GROUP_CHAT_ID and SESSION_LOADED:
                threads = cl.direct_threads(GROUP_CHAT_ID, amount=10)
                for thread in threads:
                    if thread.is_group:
                        for message in thread.messages:
                            if "joined" in message.text.lower() or "welcome" in message.text.lower():
                                user_id = message.user_id
                                username = cl.user_info(user_id).username
                                if username:
                                    welcome_new_member(user_id, username)
            
            time.sleep(30)
        except Exception as e:
            log(f"Bot loop error: {str(e)}")
            time.sleep(60)
    
    log("Bot stopped")

def start_bot():
    global BOT_THREAD
    if SESSION_LOADED and not BOT_THREAD:
        STOP_EVENT.clear()
        BOT_THREAD = threading.Thread(target=bot_loop, daemon=True)
        BOT_THREAD.start()
        log("Bot thread started")
    else:
        log("Cannot start bot - session not loaded")

def stop_bot():
    global BOT_THREAD
    if BOT_THREAD:
        STOP_EVENT.set()
        BOT_THREAD.join(timeout=5)
        BOT_THREAD = None
        log("Bot thread stopped")

@app.route('/')
def dashboard():
    reset_daily_stats()
    logs_html = ''.join([f'<div>{log_entry}</div>' for log_entry in LOGS[-20:]])
    
    template = '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Instagram Group Welcome Bot</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; }
            .container { max-width: 1200px; margin: 0 auto; background: rgba(255,255,255,0.95); border-radius: 20px; box-shadow: 0 20px 40px rgba(0,0,0,0.1); overflow: hidden; }
            .header { background: linear-gradient(135deg, #ff6b6b, #feca57); color: white; padding: 30px; text-align: center; }
            .header h1 { font-size: 2.5em; margin-bottom: 10px; }
            .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; padding: 30px; background: #f8f9fa; }
            .stat-card { background: white; padding: 25px; border-radius: 15px; text-align: center; box-shadow: 0 10px 20px rgba(0,0,0,0.1); transition: transform 0.3s; }
            .stat-card:hover { transform: translateY(-5px); }
            .stat-number { font-size: 2.5em; font-weight: bold; color: #ff6b6b; }
            .stat-label { color: #666; font-size: 1.1em; margin-top: 5px; }
            .controls { padding: 30px; background: white; border-top: 1px solid #eee; }
            .btn { padding: 12px 30px; border: none; border-radius: 25px; font-size: 1.1em; cursor: pointer; margin: 0 10px 10px 0; transition: all 0.3s; }
            .btn-primary { background: linear-gradient(135deg, #667eea, #764ba2); color: white; }
            .btn-success { background: linear-gradient(135deg, #11998e, #38ef7d); color: white; }
            .btn-danger { background: linear-gradient(135deg, #ff6b6b, #ee5a52); color: white; }
            .btn:hover { transform: translateY(-2px); box-shadow: 0 10px 20px rgba(0,0,0,0.2); }
            .input-group { margin: 15px 0; }
            .input-group label { display: block; margin-bottom: 8px; font-weight: bold; color: #333; }
            .input-group input { width: 100%; padding: 12px; border: 2px solid #eee; border-radius: 10px; font-size: 1em; transition: border-color 0.3s; }
            .input-group input:focus { outline: none; border-color: #667eea; }
            .logs { padding: 30px; background: #f8f9fa; }
            .logs-content { background: white; border-radius: 15px; padding: 20px; max-height: 400px; overflow-y: auto; font-family: monospace; font-size: 0.9em; line-height: 1.6; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1> Instagram Group Welcome Bot</h1>
                <p>Automatic welcome messages for new group members</p>
            </div>
            
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-number">{{ total }}</div>
                    <div class="stat-label">Total Welcomed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{{ today }}</div>
                    <div class="stat-label">Today Welcomed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number">{{ status }}</div>
                    <div class="stat-label">Bot Status</div>
                </div>
            </div>
            
            <div class="controls">
                <h3> Controls</h3>
                <div class="input-group">
                    <label>Group Chat ID:</label>
                    <input type="text" id="groupId" value="{{ group_id }}" placeholder="Enter group chat ID">
                </div>
                {% if session_loaded %}
                    <button class="btn btn-primary" onclick="setGroup()">Set Group</button>
                    {% if bot_running %}
                        <button class="btn btn-danger" onclick="stopBot()">Stop Bot</button>
                    {% else %}
                        <button class="btn btn-success" onclick="startBot()">Start Bot</button>
                    {% endif %}
                {% else %}
                    <button class="btn btn-primary" onclick="loadSession()">Load Session</button>
                {% endif %}
                <button class="btn" onclick="clearLogs()">Clear Logs</button>
            </div>
            
            <div class="logs">
                <h3> Recent Logs</h3>
                <div class="logs-content" id="logs">{{ logs_html }}</div>
            </div>
        </div>

        <script>
            function updateStats() {
                fetch('/stats').then(r => r.json()).then(data => {
                    document.querySelectorAll('.stat-number')[0].innerText = data.total;
                    document.querySelectorAll('.stat-number')[1].innerText = data.today;
                    document.querySelectorAll('.stat-number')[2].innerText = data.status;
                });
            }
            
            function loadSession() {
                fetch('/load_session', {method: 'POST'}).then(r => r.json()).then(data => {
                    location.reload();
                });
            }
            
            function setGroup() {
                const groupId = document.getElementById('groupId').value;
                fetch('/set_group', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({group_id: groupId})
                }).then(r => r.json()).then(data => {
                    location.reload();
                });
            }
            
            function startBot() {
                fetch('/start_bot', {method: 'POST'}).then(() => location.reload());
            }
            
            function stopBot() {
                fetch('/stop_bot', {method: 'POST'}).then(() => location.reload());
            }
            
            function clearLogs() {
                fetch('/clear_logs', {method: 'POST'});
                document.getElementById('logs').innerHTML = '';
            }
            
            setInterval(updateStats, 5000);
            updateStats();
        </script>
    </body>
    </html>
    '''
    return render_template_string(template, 
                                total=STATS["total_welcomed"],
                                today=STATS["today_welcomed"],
                                status=" Active" if (SESSION_LOADED and BOT_THREAD and BOT_THREAD.is_alive()) else " Inactive",
                                session_loaded=SESSION_LOADED,
                                bot_running=BOT_THREAD and BOT_THREAD.is_alive(),
                                group_id=GROUP_CHAT_ID or "",
                                logs_html=logs_html)

@app.route('/stats')
def get_stats():
    reset_daily_stats()
    return jsonify({
        "total": STATS["total_welcomed"],
        "today": STATS["today_welcomed"],
        "status": " Active" if (SESSION_LOADED and BOT_THREAD and BOT_THREAD.is_alive()) else " Inactive"
    })

@app.route('/load_session', methods=['POST'])
def api_load_session():
    success = load_session()
    return jsonify({"success": success, "session_loaded": SESSION_LOADED})

@app.route('/set_group', methods=['POST'])
def api_set_group():
    global GROUP_CHAT_ID
    data = request.get_json()
    GROUP_CHAT_ID = data.get('group_id')
    save_group_config()
    log(f"Group ID set to: {GROUP_CHAT_ID}")
    return jsonify({"success": True})

@app.route('/start_bot', methods=['POST'])
def api_start_bot():
    start_bot()
    return jsonify({"success": True})

@app.route('/stop_bot', methods=['POST'])
def api_stop_bot():
    stop_bot()
    return jsonify({"success": True})

@app.route('/clear_logs', methods=['POST'])
def api_clear_logs():
    global LOGS
    LOGS = []
    return jsonify({"success": True})

@app.route('/logs')
def get_logs():
    return jsonify({"logs": LOGS[-50:]})

if __name__ == '__main__':
    log("Starting Instagram Group Welcome Bot...")
    load_group_config()
    load_session()
    app.run(host='0.0.0.0', port=5000, debug=False)
