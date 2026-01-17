import os
import threading
import time
import random
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client

app = Flask(__name__)

BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
START_TIME = None

STATS = {
    "total_welcomed": 0,
    "today_welcomed": 0,
    "last_reset": datetime.now().date()
}

BOT_CONFIG = {
    "auto_replies": {},
    "auto_reply_active": False,
    "target_spam": {},
    "spam_active": {},
    "media_library": {}
}

def uptime():
    if not START_TIME:
        return "Bot inactive"
    delta = datetime.now() - START_TIME
    hours, rem = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = f"[{ts}] {msg}"
    LOGS.append(lm)
    print(lm)

MUSIC_EMOJIS = ["🎵","🎶","🎸","🎹","🎤","🎧"]
FUNNY = ["Hahaha 🤣","LOL 🤣","Mast 😆","Pagal 🤪","King 👑😂"]
MASTI = ["Party 🎉","Masti 🥳","Dhamaal 💃","Full ON 🔥","Enjoy 🎊"]

# ================= BOT =================
def run_bot(session_token, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    global START_TIME
    START_TIME = datetime.now()
    cl = Client()
    try:
        cl.login_by_sessionid(session_token)
        me = cl.account_info().username
        log(f"Session login success: @{me}")
    except Exception as e:
        log("Session login failed: " + str(e))
        return

    km = {}
    lm = {}

    for gid in gids:
        try:
            g = cl.direct_thread(gid)
            km[gid] = {u.pk for u in g.users}
            lm[gid] = g.messages[0].id if g.messages else None
            BOT_CONFIG["spam_active"][gid] = False
            log("Group ready: " + gid)
        except:
            km[gid] = set()
            lm[gid] = None

    while not STOP_EVENT.is_set():
        for gid in gids:
            if STOP_EVENT.is_set():
                break
            try:
                g = cl.direct_thread(gid)

                # -------- SPAM --------
                if BOT_CONFIG["spam_active"].get(gid):
                    t = BOT_CONFIG["target_spam"].get(gid)
                    if t:
                        cl.direct_send(
                            "@" + t["username"] + " " + t["message"],
                            thread_ids=[gid]
                        )
                        log("Spam sent")
                        time.sleep(2)

                # -------- COMMANDS --------
                if ecmd or BOT_CONFIG["auto_reply_active"]:
                    new_msgs = []
                    if lm[gid]:
                        for m in g.messages:
                            if m.id == lm[gid]:
                                break
                            new_msgs.append(m)

                    for m in reversed(new_msgs):
                        if m.user_id == cl.user_id:
                            continue

                        sender = next((u for u in g.users if u.pk == m.user_id), None)
                        if not sender:
                            continue

                        su = sender.username.lower()
                        ia = su in [a.lower() for a in admin_ids] if admin_ids else True
                        t = (m.text or "").strip()
                        tl = t.lower()

                        if BOT_CONFIG["auto_reply_active"] and tl in BOT_CONFIG["auto_replies"]:
                            cl.direct_send(BOT_CONFIG["auto_replies"][tl], thread_ids=[gid])

                        if not ecmd:
                            continue

                        if tl in ["/help","!help"]:
                            cl.direct_send(
                                "COMMANDS:"
                                "/help /ping /time /about /uptime"
                                "/stats /count /welcome"
                                "/autoreply key msg/stopreply"
                                "/music /funny /masti"
                                "/spam @user msg/stopspam",
                                thread_ids=[gid]
                            )

                        elif tl in ["/ping","!ping"]:
                            cl.direct_send("Pong! ✅", thread_ids=[gid])

                        elif tl in ["/time","!time"]:
                            cl.direct_send(datetime.now().strftime("%I:%M %p"), thread_ids=[gid])

                        elif tl in ["/uptime","!uptime"]:
                            cl.direct_send(f"Uptime: {uptime()}", thread_ids=[gid])

                        elif tl in ["/about","!about"]:
                            cl.direct_send(f"Instagram Premium Bot v4.0Uptime: {uptime()}", thread_ids=[gid])

                        elif tl.startswith("/autoreply "):
                            p = t.split(" ",2)
                            if len(p)==3:
                                BOT_CONFIG["auto_replies"][p[1].lower()] = p[2]
                                BOT_CONFIG["auto_reply_active"] = True

                        elif tl in ["/stopreply","!stopreply"]:
                            BOT_CONFIG["auto_reply_active"] = False
                            BOT_CONFIG["auto_replies"] = {}

                        elif tl in ["/music","!music"]:
                            cl.direct_send(" ".join(random.choices(MUSIC_EMOJIS,k=5)), thread_ids=[gid])

                        elif tl in ["/funny","!funny"]:
                            cl.direct_send(random.choice(FUNNY), thread_ids=[gid])

                        elif tl in ["/masti","!masti"]:
                            cl.direct_send(random.choice(MASTI), thread_ids=[gid])

                        elif ia and tl.startswith("/spam "):
                            p = t.split(" ",2)
                            if len(p)==3:
                                BOT_CONFIG["target_spam"][gid] = {
                                    "username": p[1].replace("@",""),
                                    "message": p[[2]
                                }
                                BOT_CONFIG["spam_active"][gid] = True

                        elif ia and tl in ["/stopspam","!stopspam"]:
                            BOT_CONFIG["spam_active"][gid] = False

                    if g.messages:
                        lm[gid] = g.messages[0].id

                # -------- WELCOME --------
                cm = {u.pk for u in g.users}
                new_users = cm - km[gid]

                for u in g.users:
                    if u.pk in new_users:
                        for msg in wm:
                            final = f"@{u.username} {msg}" if ucn else msg
                            cl.direct_send(final, thread_ids=[gid])
                            STATS["total_welcomed"] += 1
                            STATS["today_welcomed"] += 1
                            time.sleep(dly)

                km[gid] = cm

            except:
                pass

        time.sleep(pol)

    log("BOT STOPPED")

# ================= FLASK =================
@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start():
    global BOT_THREAD
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message":"Already running"})

    token = request.form.get("session")
    welcome = [x.strip() for x in request.form.get("welcome","").splitlines() if x.strip()]
    gids = [x.strip() for x in request.form.get("group_ids","").split(",") if x.strip()]
    admins = [x.strip() for x in request.form.get("admin_ids","").split(",") if x.strip()]

    if not token or not welcome or not gids:
        return jsonify({"message":"Fill all fields"})

    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(
        target=run_bot,
        args=(
            token,
            welcome,
            gids,
            int(request.form.get("delay",3)),
            int(request.form.get("poll",5)),
            request.form.get("use_custom_name")=="yes",
            request.form.get("enable_commands")=="yes",
            admins
        ),
        daemon=True
    )
    BOT_THREAD.start()
    return jsonify({"message":"Started!"})

@app.route("/stop", methods=["POST"])
def stop():
    STOP_EVENT.set()
    return jsonify({"message":"Stopped!"})

@app.route("/logs")
def logs():
    return jsonify({"logs": LOGS[-200:], "uptime": uptime(), "status": "running" if BOT_THREAD and BOT_THREAD.is_alive() else "stopped"})

@app.route("/stats")
def stats():
    return jsonify({
        "uptime": uptime(),
        "status": "running" if BOT_THREAD and BOT_THREAD.is_alive() else "stopped",
        "total_welcomed": STATS["total_welcomed"],
        "today_welcomed": STATS["today_welcomed"]
    })

# ================= PREMIUM PRO UI =================
PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Premium Instagram Bot</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            color: #2d3748;
        }

        .container {
            max-width: 800px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(20px);
            border-radius: 24px;
            box-shadow: 0 25px 50px rgba(0,0,0,0.15);
            overflow: hidden;
            border: 1px solid rgba(255,255,255,0.2);
        }

        .header {
            background: linear-gradient(135deg, #4f46e5, #7c3aed);
            color: white;
            padding: 30px;
            text-align: center;
            position: relative;
            overflow: hidden;
        }

        .header::before {
            content: '';
            position: absolute;
            top: -50%;
            right: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, rgba(255,255,255,0.1) 0%, transparent 70%);
            animation: float 6s ease-in-out infinite;
        }

        @keyframes float {
            0%, 100% { transform: translateY(0px) rotate(0deg); }
            50% { transform: translateY(-20px) rotate(180deg); }
        }

        .header h1 {
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 10px;
            position: relative;
            z-index: 2;
        }

        .header p {
            opacity: 0.9;
            font-weight: 400;
            position: relative;
            z-index: 2;
        }

        .status-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 30px;
            background: linear-gradient(90deg, #f8fafc, #e2e8f0);
            border-bottom: 1px solid #e2e8f0;
        }

        .status-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 500;
        }

        .status-running { color: #10b981; }
        .status-stopped { color: #ef4444; }

        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #10b981;
            animation: pulse 2s infinite;
        }

        .status-stopped .status-dot { background: #ef4444; }

        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }

        .content {
            padding: 30px;
        }

        .form-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 30px;
        }

        .form-group {
            position: relative;
        }

        .form-group.full { grid-column: 1 / -1; }

        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: #374151;
            font-size: 0.95rem;
        }

        input, textarea, select {
            width: 100%;
            padding: 14px 16px;
            border: 2px solid #e5e7eb;
            border-radius: 12px;
            font-size: 1rem;
            background: white;
            transition: all 0.3s ease;
            font-family: inherit;
        }

        input:focus, textarea:focus, select:focus {
            outline: none;
            border-color: #4f46e5;
            box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
            transform: translateY(-1px);
        }

        textarea {
            resize: vertical;
            min-height: 120px;
        }

        .checkbox-group {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 16px;
            background: #f8fafc;
            border-radius: 12px;
            border: 2px solid #e5e7eb;
            transition: all 0.3s ease;
            cursor: pointer;
        }

        .checkbox-group:hover {
            border-color: #4f46e5;
            background: #eff6ff;
        }

        .checkbox-group input[type="checkbox"] {
            width: auto;
            transform: scale(1.2);
        }

        .controls {
            display: flex;
            gap: 16px;
            justify-content: center;
            margin: 40px 0;
        }

        .btn {
            padding: 16px 40px;
            border: none;
            border-radius: 16px;
            font-size: 1.1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            display: flex;
            align-items: center;
            gap: 10px;
            text-decoration: none;
            font-family: inherit;
        }

        .btn-start {
            background: linear-gradient(135deg, #10b981, #059669);
            color: white;
            box-shadow: 0 10px 25px rgba(16, 185, 129, 0.4);
        }

        .btn-start:hover {
            transform: translateY(-2px);
            box-shadow: 0 15px 35px rgba(16, 185, 129, 0.6);
        }

        .btn-stop {
            background: linear-gradient(135deg, #ef4444, #dc2626);
            color: white;
            box-shadow: 0 10px 25px rgba(239, 68, 68, 0.4);
        }

        .btn-stop:hover {
            transform: translateY(-2px);
            box-shadow: 0 15px 35px rgba(239, 68, 68, 0.6);
        }

        .logs-container {
            background: #1e293b;
            border-radius: 16px;
            padding: 24px;
            margin-top: 30px;
            position: relative;
            overflow: hidden;
        }

        .logs-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            color: white;
            margin-bottom: 20px;
            font-weight: 600;
        }

        #logs {
            background: #0f172a;
            color: #e2e8f0;
            border-radius: 12px;
            padding: 20px;
            height: 300px;
            overflow-y: auto;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 0.9rem;
            line-height: 1.5;
            white-space: pre-wrap;
            border: 1px solid #334155;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .stat-card {
            background: white;
            padding: 24px;
            border-radius: 16px;
            text-align: center;
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            border: 1px solid #e5e7eb;
            transition: all 0.3s ease;
        }

        .stat-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 20px 40px rgba(0,0,0,0.15);
        }

        .stat-number {
            font-size: 2.5rem;
            font-weight: 700;
            color: #4f46e5;
            margin-bottom: 8px;
        }

        .stat-label {
            color: #6b7280;
            font-weight: 500;
        }

        @media (max-width: 768px) {
            .form-grid {
                grid-template-columns: 1fr;
            }
            
            .header h1 {
                font-size: 2rem;
            }
            
            .controls {
                flex-direction: column;
            }
        }

        .fade-in {
            animation: fadeIn 0.6s ease-out;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
    </style>
</head>
<body>
    <div class="container fade-in">
        <div class="header">
            <h1><i class="fas fa-robot"></i> Premium Bot</h1>
            <p>Professional Instagram Automation Dashboard</p>
        </div>

        <div class="status-bar" id="statusBar">
            <div class="status-item status-stopped">
                <div class="status-dot"></div>
                <span>Status: Stopped</span>
            </div>
            <div class="status-item">
                <span id="uptime">00:00:00</span>
            </div>
        </div>

        <div class="content">
            <div class="stats-grid" id="statsGrid" style="display: none;">
                <div class="stat-card">
                    <div class="stat-number" id="totalWelcomed">0</div>
                    <div class="stat-label">Total Welcomed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-number" id="todayWelcomed">0</div>
                    <div class="stat-label">Today Welcomed</div>
                </div>
            </div>

            <form id="botForm">
                <div class="form-grid">
                    <div class="form-group">
                        <label for="session"><i class="fas fa-key"></i> Session Token</label>
                        <input type="password" id="session" name="session" placeholder="Enter your session token" required>
                    </div>
                    <div class="form-group">
                        <label for="admin_ids"><i class="fas fa-users"></i> Admin Usernames</label>
                        <input type="text" id="admin_ids" name="admin_ids" placeholder="username1,username2">
                    </div>
                    <div class="form-group full">
                        <label for="welcome"><i class="fas fa-comment-dots"></i> Welcome Messages</label>
                        <textarea id="welcome" name="welcome" placeholder="Welcome to group!&#10;Enjoy your stay 😊&#10;Have fun! 🎉">Welcome bro! 🔥
Have fun in group! 🎉
Enjoy your stay! 😊
Rules: No spam</textarea>
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-hashtag"></i> Group IDs</label>
                        <input type="text" name="group_ids" placeholder="1234567890,0987654321">
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-clock"></i> Delay (seconds)</label>
                        <input type="number" name="delay" value="3" min="1" max="10">
                    </div>
                    <div class="form-group">
                        <label><i class="fas fa-sync"></i> Poll Interval (seconds)</label>
                        <input type="number" name="poll" value="5" min="2" max="30">
                    </div>
                </div>

                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px;">
                    <div class="checkbox-group" onclick="toggleCheckbox('use_custom_name')">
                        <input type="checkbox" id="use_custom_name" name="use_custom_name" value="yes" checked>
                        <label for="use_custom_name" style="cursor: pointer; flex: 1; margin: 0;">
                            <i class="fas fa-user-tag"></i> Mention @username
                        </label>
                    </div>
                    <div class="checkbox-group" onclick="toggleCheckbox('enable_commands')">
                        <input type="checkbox" id="enable_commands" name="enable_commands" value="yes" checked>
                        <label for="enable_commands" style="cursor: pointer; flex: 1; margin: 0;">
                            <i class="fas fa-terminal"></i> Enable Commands
                        </label>
                    </div>
                </div>

                <div class="controls">
                    <button type="button" class="btn btn-start" onclick="startBot()">
                        <i class="fas fa-play"></i> Start Bot
                    </button>
                    <button type="button" class="btn btn-stop" onclick="stopBot()">
                        <i class="fas fa-stop"></i> Stop Bot
                    </button>
                </div>
            </form>

            <div class="logs-container">
                <div class="logs-header">
                    <div><i class="fas fa-list"></i> Live Logs</div>
                    <button onclick="clearLogs()" style="background: none; border: 1px solid #94a3b8; color: white; padding: 8px 16px; border-radius: 8px; cursor: pointer;">Clear</button>
                </div>
                <div id="logs">🚀 Premium Bot ready! Fill form and click START</div>
            </div>
        </div>
    </div>

    <script>
        let statusInterval;

        function toggleCheckbox(id) {
            document.getElementById(id).click();
        }

        async function startBot() {
            try {
                const formData = new FormData(document.getElementById('botForm'));
                const response = await fetch('/start', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                alert('✅ ' + result.message);
                updateStatus();
            } catch (error) {
                alert('❌ Error: ' + error.message);
            }
        }

        async function stopBot() {
            try {
                const response = await fetch('/stop', { method: 'POST' });
                const result = await response.json();
                alert('✅ ' + result.message);
                updateStatus();
            } catch (error) {
                alert('❌ Error: ' + error.message);
            }
        }

        async function updateStatus() {
            try {
                const response = await fetch('/stats');
                const data = await response.json();
                
                document.getElementById('uptime').textContent = data.uptime;
                
                const statusBar = document.getElementById('statusBar');
                const statusDot = statusBar.querySelector('.status-dot');
                const statusText = statusBar.querySelector('span');
                
                if (data.status === 'running') {
                    statusBar.classList.remove('status-stopped');
                    statusBar.classList.add('status-running');
                    statusDot.style.background = '#10b981';
                    statusText.textContent = 'Status: Running';
                    document.getElementById('statsGrid').style.display = 'grid';
                    document.getElementById('totalWelcomed').textContent = data.total_welcomed;
                    document.getElementById('todayWelcomed').textContent = data.today_welcomed;
                } else {
                    statusBar.classList.add('status-stopped');
                    statusBar.classList.remove('status-running');
                    statusDot.style.background = '#ef4444';
                    statusText.textContent = 'Status: Stopped';
                    document.getElementById('statsGrid').style.display = 'none';
                }
            } catch (error) {
                console.error('Status update failed:', error);
            }
        }

        async function updateLogs() {
            try {
                const response = await fetch('/logs');
                const data = await response.json();
                const logsDiv = document.getElementById('logs');
                logsDiv.textContent = data.logs.join('\
');
                logsDiv.scrollTop = logsDiv.scrollHeight;
            } catch (error) {
                console.error('Logs update failed:', error);
            }
        }

        function clearLogs() {
            document.getElementById('logs').textContent = '🧹 Logs cleared!';
        }

        // Auto update every 2 seconds
        statusInterval = setInterval(() => {
            updateStatus();
            updateLogs();
        }, 2000);

        // Initial update
        updateStatus();
        updateLogs();
    </script>
</body>
</html>"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
