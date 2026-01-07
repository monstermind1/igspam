import os
import threading
import time
import random
import json
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
from instagrapi import Client
from instagrapi.exceptions import ClientError

app = Flask(__name__)
BOT_THREAD = None
STOP_EVENT = threading.Event()
LOGS = []
SESSION_FILE = "session_token.txt"  # Token file instead of session.json
STATS = {"total_welcomed": 0, "today_welcomed": 0, "last_reset": datetime.now().date()}
BOT_CONFIG = {"auto_replies": {}, "auto_reply_active": False, "target_spam": {}, "spam_active": {}, "media_library": {}}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = f"[{ts}] {msg}"
    LOGS.append(lm)
    print(lm)

def load_token_session(token):
    """Single token को session में convert करो"""
    cl = Client()
    try:
        # UUIDs set करो
        cl.set_uuids({
            "phone_uuid": "6ee804b0-7f8e-4f2d-b3e5-6d5f8a9b0c1d",
            "device_uuid": "6ee804b0-7f8e-4f2d-b3e5-6d5f8a9b0c2e",
            "instagram_uuid": "6ee804b0-7f8e-4f2d-b3e5-6d5f8a9b0c3f"
        })
        
        # Token को settings में inject करो
        settings = {
            "experiments": {},
            "sessionid": token.split(':')[0] if ':' in token else token,
            "csrftoken": token.split(':')[-1] if ':' in token else token[:32],
            "ds_user_id": token.split('%3A')[0] if '%3A' in token else "1234567890"
        }
        
        cl.set_settings(settings)
        cl.login_by_sessionid(token.split(':')[0] if ':' in token else token)
        log("✅ Token से login successful!")
        return cl
    except Exception as e:
        log(f"❌ Token login failed: {str(e)}")
        return None

def validate_token_file():
    """Check if token.txt exists and has valid content"""
    if not os.path.exists(SESSION_FILE):
        return None
    try:
        with open(SESSION_FILE, 'r') as f:
            token = f.read().strip()
            return token if token and len(token) > 20 else None
    except:
        return None

MUSIC_EMOJIS = ["🎵", "🎶", "🎸", "🎹", "🎤", "🎧", "🎺", "🎷"]
FUNNY = ["Hahaha! 😂", "LOL! 🤣", "Mast! 😆", "Pagal! 🤪", "King! 👑😂"]
MASTI = ["Party! 🎉", "Masti! 🥳", "Dhamaal! 💃", "Full ON! 🔥", "Enjoy! 🎊"]

def run_bot(token, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    global STATS
    
    # Token से login
    cl = load_token_session(token)
    if not cl:
        log("❌ Token invalid! नया token generate करो")
        return

    log("🚀 Bot started with TOKEN login!")
    log(f"👥 Admins: {admin_ids}")
    
    km = {}
    lm = {}
    for gid in gids:
        try:
            g = cl.direct_thread(gid)
            km[gid] = {u.pk for u in g.users}
            lm[gid] = g.messages[0].id if g.messages else None
            BOT_CONFIG["spam_active"][gid] = False
            log(f"✅ Group {gid} ready")
        except Exception as e:
            log(f"❌ Group {gid}: {str(e)}")
            km[gid] = set()
            lm[gid] = None

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
                        spam_data = BOT_CONFIG["target_spam"].get(gid, {})
                        tu = spam_data.get("username")
                        sm = spam_data.get("message")
                        if tu and sm:
                            cl.direct_send(f"@{tu} {sm}", thread_ids=[gid])
                            log(f"📨 Spam: @{tu}")
                            time.sleep(2)

                    if ecmd or BOT_CONFIG["auto_reply_active"]:
                        nm = []
                        if lm.get(gid):
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
                                log("🤖 Auto-reply")

                            if not ecmd:
                                continue

                            if tl in ["/help", "!help"]:
                                cl.direct_send("🔥 TOKEN BOT COMMANDS: /help /stats /count /welcome /ping /time /about /library /music /funny /masti", thread_ids=[gid])
                            elif tl in ["/stats", "!stats"]:
                                cl.direct_send(f"📊 Total: {STATS['total_welcomed']} | Today: {STATS['today_welcomed']}", thread_ids=[gid])
                            elif tl in ["/count", "!count"]:
                                cl.direct_send(f"👥 Members: {len(g.users)}", thread_ids=[gid])
                            elif tl in ["/welcome", "!welcome"]:
                                cl.direct_send(f"@{sender.username} Welcome test!", thread_ids=[gid])
                            elif tl in ["/ping", "!ping"]:
                                cl.direct_send("🏓 Pong!", thread_ids=[gid])
                            elif tl in ["/time", "!time"]:
                                cl.direct_send(f"🕐 {datetime.now().strftime('%I:%M %p')}", thread_ids=[gid])
                            elif tl in ["/about", "!about"]:
                                cl.direct_send("🤖 TOKEN Instagram Bot - No Password Needed!", thread_ids=[gid])

                        if g.messages:
                            lm[gid] = g.messages[0].id

                    cm = {u.pk for u in g.users}
                    nwm = cm - km.get(gid, set())
                    if nwm:
                        for u in g.users:
                            if u.pk in nwm and u.username.lower() != cl.account.username.lower():
                                log(f"👋 NEW: @{u.username}")
                                for ms in wm:
                                    if STOP_EVENT.is_set():
                                        break
                                    fm = (f"@{u.username} {ms}" if ucn else ms)
                                    cl.direct_send(fm, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    log(f"✅ Welcomed @{u.username}")
                                    time.sleep(dly)
                                km[gid] = cm
                                break

                    km[gid] = cm

                except Exception as e:
                    log(f"⚠️ Group {gid}: {str(e)[:50]}")
            time.sleep(pol)
        except Exception as e:
            log(f"❌ Loop error: {str(e)}")
            time.sleep(5)

    log("🛑 Bot stopped!")

@app.route("/")
def index():
    token = validate_token_file()
    return render_template_string(PAGE_HTML.format(token_status="✅ TOKEN LOADED!" if token else "❌ NO TOKEN"))

@app.route("/set_token", methods=["POST"])
def set_token():
    token = request.form.get("token", "").strip()
    if token:
        with open(SESSION_FILE, "w") as f:
            f.write(token)
        log("💾 Token saved!")
        return jsonify({"message": "✅ Token set successfully!"})
    return jsonify({"message": "❌ Empty token!"})

@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "⚠️ Bot already running!"})
    
    token = validate_token_file()
    if not token:
        return jsonify({"message": "❌ No valid token! Set token first."})
    
    wl = [m.strip() for m in request.form.get("welcome", "").splitlines() if m.strip()]
    gids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    adm = [a.strip() for a in request.form.get("admin_ids", "").split(",") if a.strip()]
    
    if not gids or not wl:
        return jsonify({"message": "❌ Fill groups & welcome messages!"})
    
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(
        target=run_bot, 
        args=(token, wl, gids, 
              int(request.form.get("delay", 3)), 
              int(request.form.get("poll", 5)), 
              request.form.get("use_custom_name") == "yes", 
              request.form.get("enable_commands") == "yes", 
              adm), 
        daemon=True
    )
    BOT_THREAD.start()
    return jsonify({"message": "🚀 Token bot started!"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    STOP_EVENT.set()
    return jsonify({"message": "✅ Bot stopped!"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-50:]})

PAGE_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TOKEN BOT</title>
<style>*{{same CSS as before}}</style></head><body>
<div class="c">
<h1>🎟️ TOKEN BOT v5.0</h1>
<div class="note">✅ <strong>NO USERNAME/PASSWORD NEEDED!</strong> बस token paste करो</div>

<!-- Token Section -->
<div style="background:rgba(0,255,0,.2);padding:20px;border-radius:15px;margin:20px 0;border:2px solid #0f0">
<label class="f1">🔑 SESSION TOKEN</label>
<textarea id="token_input" class="i1" rows="3" placeholder="56748960230%3AF8ELTyGZTkSadW%3A2%3AAYjuwrkOJ9yhvhNZrWtC5YpeHoq_L0TDZV5oPhhngQ"></textarea>
<button class="bs" onclick="setToken()" style="margin-top:10px">💾 SET TOKEN</button>
<div id="token_status">{token_status}</div>
</div>

<form id="f" style="display:{'none' if token_status=='✅ TOKEN LOADED!' else 'block'}">
<label class="f3">👑 ADMINS</label><input class="i3" name="admin_ids" placeholder="admin1,admin2">
<label class="f4">💬 WELCOME</label><textarea class="i4" name="welcome">Welcome bro! 🎉
Glad you joined! 🔥</textarea>
<label class="f5">🆔 Mention?</label><select class="i5" name="use_custom_name"><option value="yes">Yes</option><option value="no">No</option></select>
<label class="f6">⚙️ Commands?</label><select class="i6" name="enable_commands"><option value="yes">Yes</option></select>
<label class="f7">👥 GROUP IDs</label><input class="i7" name="group_ids" placeholder="1234567890,9876543210">
<label class="f8">⏱️ Delay</label><input class="i8" type="number" name="delay" value="3">
<label class="f1">🔄 Poll</label><input class="i1" type="number" name="poll" value="5">
<div class="bc"><button class="bs" onclick="startBot()">🚀 START</button><button class="bp" onclick="stopBot()">🛑 STOP</button></div>
</form>

<div class="ls"><div class="lt">📡 LIVE LOGS</div><div class="lb" id="logs">Token set karo...</div></div>
</div>
<script>
let tokenSet = `{token_status}` == '✅ TOKEN LOADED!';
if(tokenSet) document.getElementById('f').style.display = 'block';

async function setToken() {{
    let token = document.getElementById('token_input').value.trim();
    if(!token) return alert('❌ Token empty!');
    let r = await fetch('/set_token', {{method:'POST', body: new FormData({{token, token}})}});
    let res = await r.json();
    alert(res.message);
    if(res.message.includes('✅')) {{
        location.reload();
    }}
}}
async function startBot() {{
    let r = await fetch('/start', {{method:'POST', body:new FormData(document.getElementById('f'))}});
    alert((await r.json()).message);
}}
async function stopBot() {{
    let r = await fetch('/stop', {{method:'POST'}});
    alert((await r.json()).message);
}}
setInterval(async() => {{
    let r = await fetch('/logs');
    let d = await r.json();
    document.getElementById('logs').innerHTML = d.logs.map(l=>`<div style="color:#0ff">${{l}}</div>`).join('');
}}, 2000);
</script></body></html>"""

if __name__ == "__main__":
    print("🚀 TOKEN BOT v5.0 - NO PASSWORD NEEDED!")
    app.run(host="0.0.0.0", port=5000, debug=False)
