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
SESSION_FILE = "session.json"
SESSION_TOKEN = None
STATS = {"total_welcomed": 0, "today_welcomed": 0, "last_reset": datetime.now().date()}
BOT_CONFIG = {"auto_replies": {}, "auto_reply_active": False, "target_spam": {}, "spam_active": {}, "media_library": {}}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = "[" + ts + "] " + msg
    LOGS.append(lm)
    print(lm)

MUSIC_EMOJIS = ["🎵", "🎶", "🎸", "🎹", "🎤", "🎧", "🎺", "🎷"]
FUNNY = ["Hahaha! 😂", "LOL! 🤣", "Mast! 😆", "Pagal! 🤪", "King! 👑😂"]
MASTI = ["Party! 🎉", "Masti! 🥳", "Dhamaal! 💃", "Full ON! 🔥", "Enjoy! 🎊"]

def run_bot(username, password, gids, dly, pol, ucn, ecmd, admin_ids):
    cl = Client()
    try:
        # Username Password Login - Jaise pehle karte the!
        cl.login(username, password)
        cl.dump_settings(SESSION_FILE)
        log("✅ Username Password Login successful!")
    except Exception as e:
        log("Login failed: " + str(e))
        return
    
    log("Bot started!")
    log("Admins: " + str(admin_ids))
    km = {}
    lm = {}
    for gid in gids:
        try:
            g = cl.direct_thread(gid)
            km[gid] = {u.pk for u in g.users}
            lm[gid] = g.messages[0].id if g.messages else None
            BOT_CONFIG["spam_active"][gid] = False
            log("Group " + gid + " ready")
        except Exception as e:
            log("Error: " + str(e))
            km[gid] = set()
            lm[gid] = None
    
    global STATS
    if STATS["last_reset"] != datetime.now().date():
        STATS["today_welcomed"] = 0
        STATS["last_reset"] = datetime.now().date()
    
    while not STOP_EVENT.is_set():
        try:
            for gid in gids:
                if STOP_EVENT.is_set():
                    break
                try:
                    g = cl.direct_thread(gid)
                    if BOT_CONFIG["spam_active"].get(gid, False):
                        tu = BOT_CONFIG["target_spam"].get(gid, {}).get("username")
                        sm = BOT_CONFIG["target_spam"].get(gid, {}).get("message")
                        if tu and sm:
                            cl.direct_send("@" + tu + " " + sm, thread_ids=[gid])
                            log("Spam to @" + tu)
                            time.sleep(2)
                    
                    if ecmd or BOT_CONFIG["auto_reply_active"]:
                        nm = []
                        if lm[gid]:
                            for m in g.messages:
                                if m.id == lm[gid]:
                                    break
                                nm.append(m)
                        for m in reversed(nm):
                            if m.user_id == cl.user_id:
                                continue
                            sender = next((u for u in g.users if u.pk == m.user_id), None)
                            if not sender:
                                continue
                            su = sender.username.lower()
                            ia = su in [a.lower() for a in admin_ids] if admin_ids else True
                            t = m.text.strip() if m.text else ""
                            tl = t.lower()
                            
                            if BOT_CONFIG["auto_reply_active"] and tl in BOT_CONFIG["auto_replies"]:
                                cl.direct_send(BOT_CONFIG["auto_replies"][tl], thread_ids=[gid])
                                log("Auto-reply sent")
                            if not ecmd:
                                continue
                            if tl in ["/help", "!help"]:
                                cl.direct_send("COMMANDS: /autoreply /stopreply /addvideo /addaudio /video /audio /library /music /funny /masti /kick /spam /stopspam /rules /stats /count /ping /time /about /welcome", thread_ids=[gid])
                                log("Help sent")
                            elif tl in ["/stats", "!stats"]:
                                cl.direct_send("STATS - Total: " + str(STATS['total_welcomed']) + " Today: " + str(STATS['today_welcomed']), thread_ids=[gid])
                            elif tl in ["/count", "!count"]:
                                cl.direct_send("MEMBERS: " + str(len(g.users)), thread_ids=[gid])
                            elif tl in ["/welcome", "!welcome"]:
                                cl.direct_send("@" + sender.username + " Test!", thread_ids=[gid])
                            elif tl in ["/ping", "!ping"]:
                                cl.direct_send("Pong! Alive!", thread_ids=[gid])
                            elif tl in ["/time", "!time"]:
                                cl.direct_send("TIME: " + datetime.now().strftime("%I:%M %p"), thread_ids=[gid])
                            elif tl in ["/about", "!about"]:
                                cl.direct_send("Instagram Bot v4.0 - Username Password Login", thread_ids=[gid])
                            elif tl.startswith("/autoreply "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    BOT_CONFIG["auto_replies"][p[1].lower()] = p[2]
                                    BOT_CONFIG["auto_reply_active"] = True
                                    cl.direct_send("Auto-reply set: " + p[1] + " -> " + p[2], thread_ids=[gid])
                            elif tl in ["/stopreply", "!stopreply"]:
                                BOT_CONFIG["auto_reply_active"] = False
                                BOT_CONFIG["auto_replies"] = {}
                                cl.direct_send("Auto-reply stopped!", thread_ids=[gid])
                            elif ia and tl.startswith("/addvideo "):
                                p = t.split(" ", 3)
                                if len(p) >= 4:
                                    BOT_CONFIG["media_library"][p[1].lower()] = {"type": "video", "format": p[2].upper(), "link": p[3]}
                                    cl.direct_send("Video saved: " + p[1], thread_ids=[gid])
                            elif ia and tl.startswith("/addaudio "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    BOT_CONFIG["media_library"][p[1].lower()] = {"type": "audio", "link": p[2]}
                                    cl.direct_send("Audio saved: " + p[1], thread_ids=[gid])
                            elif tl.startswith("/video "):
                                p = t.split(" ", 1)
                                if len(p) >= 2:
                                    n = p[1].lower()
                                    if n in BOT_CONFIG["media_library"] and BOT_CONFIG["media_library"][n]["type"] == "video":
                                        md = BOT_CONFIG["media_library"][n]
                                        cl.clip_upload(md["link"], caption="🎥 " + n.upper())
                                        cl.direct_send("Sent video: " + n, thread_ids=[gid])
                                        log("Video sent: " + n)
                            elif tl.startswith("/audio "):
                                p = t.split(" ", 1)
                                if len(p) >= 2:
                                    n = p[1].lower()
                                    if n in BOT_CONFIG["media_library"] and BOT_CONFIG["media_library"][n]["type"] == "audio":
                                        cl.direct_send(BOT_CONFIG["media_library"][n]["link"], thread_ids=[gid])
                                        log("Audio sent: " + n)
                            elif tl in ["/library", "!library"]:
                                libs = [k for k in BOT_CONFIG["media_library"].keys()]
                                cl.direct_send("📚 Library: " + ", ".join(libs) if libs else "Empty", thread_ids=[gid])
                            elif tl.startswith("/music"):
                                cl.direct_send(random.choice(MUSIC_EMOJIS) + " " + random.choice(["Shor macha!", "Gaana bajao! 🎶", "Music ON! 🔥"]), thread_ids=[gid])
                            elif tl.startswith("/funny"):
                                cl.direct_send(random.choice(FUNNY), thread_ids=[gid])
                            elif tl.startswith("/masti"):
                                cl.direct_send(random.choice(MASTI), thread_ids=[gid])
                            elif ia and tl.startswith("/spam "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    tu = p[1].lstrip("@")
                                    BOT_CONFIG["target_spam"][gid] = {"username": tu, "message": p[2]}
                                    BOT_CONFIG["spam_active"][gid] = True
                                    cl.direct_send("Spam started on @" + tu, thread_ids=[gid])
                            elif ia and tl in ["/stopspam", "!stopspam"]:
                                BOT_CONFIG["spam_active"][gid] = False
                                BOT_CONFIG["target_spam"].pop(gid, None)
                                cl.direct_send("Spam stopped!", thread_ids=[gid])
                            lm[gid] = g.messages[0].id if g.messages else None
                except Exception as e:
                    log("Group loop error " + gid + ": " + str(e))
            time.sleep(dly)
        except Exception as e:
            log("Main bot error: " + str(e))
            time.sleep(5)

## Flask Web Interface - USERNAME PASSWORD वाला
@app.route('/')
def index():
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <title>Instagram Bot Panel</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial; margin: 20px; background: #1a1a1a; color: #fff; }
        .container { max-width: 800px; margin: 0 auto; }
        input, button, textarea { padding: 10px; margin: 5px; border: none; border-radius: 5px; }
        input, textarea { background: #333; color: #fff; width: 300px; }
        button { background: #4CAF50; color: white; cursor: pointer; }
        button:hover { background: #45a049; }
        .stop-btn { background: #f44336 !important; }
        .stop-btn:hover { background: #da190b !important; }
        .logs { background: #222; height: 300px; overflow-y: scroll; padding: 10px; border-radius: 5px; font-family: monospace; font-size: 12px; }
        .stats { background: #333; padding: 15px; border-radius: 5px; margin: 10px 0; }
        .form-group { margin: 15px 0; }
        label { display: block; margin-bottom: 5px; color: #ccc; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 Instagram Bot Control Panel</h1>
        
        <div class="stats">
            <strong>Status:</strong> {{ '🟢 Running' if BOT_THREAD and BOT_THREAD.is_alive() else '🔴 Stopped' }}<br>
            <strong>Total Messages:</strong> {{ STATS.total_welcomed }}<br>
            <strong>Today:</strong> {{ STATS.today_welcomed }}
        </div>

        {% if not SESSION_TOKEN %}
        <div class="form-group">
            <label>Instagram Username:</label>
            <input type="text" id="username" placeholder="your_username">
        </div>
        <div class="form-group">
            <label>Instagram Password:</label>
            <input type="password" id="password" placeholder="your_password">
            <button onclick="startBot()">🚀 Start Bot</button>
        </div>
        {% endif %}

        <div class="form-group">
            <button class="stop-btn" onclick="stopBot()">⏹️ Stop Bot</button>
            <button onclick="refreshLogs()">🔄 Refresh Logs</button>
            <button onclick="clearLogs()">🗑️ Clear Logs</button>
        </div>

        <div class="form-group">
            <label>Delay (seconds):</label>
            <input type="number" id="delay" value="3" min="1" max="30">
        </div>

        <h3>📝 Recent Logs:</h3>
        <div class="logs" id="logs">{{ logs_html }}</div>
    </div>

    <script>
        function startBot() {
            const username = document.getElementById('username').value;
            const password = document.getElementById('password').value;
            if (!username || !password) { alert('Username और Password दोनों भरें!'); return; }
            fetch('/start', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username: username, password: password})
            }).then(r => r.json()).then(data => {
                alert(data.message);
                location.reload();
            });
        }

        function stopBot() {
            fetch('/stop', {method: 'POST'}).then(r => r.json()).then(data => {
                alert(data.message);
                location.reload();
            });
        }

        function refreshLogs() {
            fetch('/logs').then(r => r.json()).then(data => {
                document.getElementById('logs').innerHTML = data.logs_html;
                document.getElementById('logs').scrollTop = document.getElementById('logs').scrollHeight;
            });
        }

        function clearLogs() {
            fetch('/clear_logs', {method: 'POST'}).then(() => refreshLogs());
        }

        setInterval(refreshLogs, 3000);
        refreshLogs();
    </script>
</body>
</html>
    ''', logs_html='<br>'.join(LOGS[-20:]), STATS=STATS)

@app.route('/logs')
def get_logs():
    return jsonify({'logs_html': '<br>'.join(LOGS[-50:])})

@app.route('/start', methods=['POST'])
def start_bot():
    global BOT_THREAD, SESSION_TOKEN
    data = request.json
    username = data['username']
    password = data['password']
    
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({'message': 'Bot already running!'})
    
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(target=run_bot, args=(username, password, ['YOUR_GROUP_ID_1', 'YOUR_GROUP_ID_2'], 
                         3, True, True, True, ['admin1', 'admin2']))
    BOT_THREAD.daemon = True
    BOT_THREAD.start()
    SESSION_TOKEN = f"{username}:{password}"  # Just for UI status
    return jsonify({'message': 'Bot started with Username Password!'})

@app.route('/stop', methods=['POST'])
def stop_bot():
    STOP_EVENT.set()
    if BOT_THREAD:
        BOT_THREAD.join(timeout=2)
    return jsonify({'message': 'Bot stopped!'})

@app.route('/clear_logs', methods=['POST'])
def clear_logs():
    global LOGS
    LOGS = []
    return jsonify({'message': 'Logs cleared!'})

if __name__ == '__main__':
    log("🚀 Instagram Bot Flask Server Starting...")
    log("📱 Open: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
