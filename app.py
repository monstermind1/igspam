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

def run_bot(un, pw, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    cl = Client()
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(un, pw)
            log("Session loaded")
        else:
            cl.login(un, pw)
            cl.dump_settings(SESSION_FILE)
            log("Session saved")
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
                                cl.direct_send("Instagram Bot v3.0 - Full Featured", thread_ids=[gid])
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
                                        cl.direct_send("VIDEO: " + p[1].upper() + " | Type: " + md.get("format", "VIDEO") + " | Watch: " + md["link"], thread_ids=[gid])
                                    else:
                                        cl.direct_send("Video not found!", thread_ids=[gid])
                            elif tl.startswith("/audio "):
                                p = t.split(" ", 1)
                                if len(p) >= 2:
                                    n = p[1].lower()
                                    if n in BOT_CONFIG["media_library"] and BOT_CONFIG["media_library"][n]["type"] == "audio":
                                        md = BOT_CONFIG["media_library"][n]
                                        cl.direct_send("AUDIO: " + p[1].upper() + " | Listen: " + md["link"], thread_ids=[gid])
                                    else:
                                        cl.direct_send("Audio not found!", thread_ids=[gid])
                            elif tl in ["/library", "!library"]:
                                if BOT_CONFIG["media_library"]:
                                    vids = [k for k, v in BOT_CONFIG["media_library"].items() if v["type"] == "video"]
                                    auds = [k for k, v in BOT_CONFIG["media_library"].items() if v["type"] == "audio"]
                                    msg = "LIBRARY | Videos: " + ", ".join(vids) if vids else "" + " | Audios: " + ", ".join(auds) if auds else ""
                                    cl.direct_send(msg, thread_ids=[gid])
                                else:
                                    cl.direct_send("Library empty!", thread_ids=[gid])
                            elif tl in ["/music", "!music"]:
                                cl.direct_send("Music! " + " ".join(random.choices(MUSIC_EMOJIS, k=5)), thread_ids=[gid])
                            elif tl in ["/funny", "!funny"]:
                                cl.direct_send(random.choice(FUNNY), thread_ids=[gid])
                            elif tl in ["/masti", "!masti"]:
                                cl.direct_send(random.choice(MASTI), thread_ids=[gid])
                            elif ia and tl.startswith("/kick "):
                                p = t.split(" ", 1)
                                if len(p) >= 2:
                                    ku = p[1].replace("@", "")
                                    tg = next((u for u in g.users if u.username.lower() == ku.lower()), None)
                                    if tg:
                                        try:
                                            cl.direct_thread_remove_user(gid, tg.pk)
                                            cl.direct_send("Kicked @" + tg.username, thread_ids=[gid])
                                        except:
                                            cl.direct_send("Cannot kick", thread_ids=[gid])
                            elif tl in ["/rules", "!rules"]:
                                cl.direct_send("RULES: 1.Respect 2.No spam 3.Follow guidelines 4.Have fun!", thread_ids=[gid])
                            elif ia and tl.startswith("/spam "):
                                p = t.split(" ", 2)
                                if len(p) >= 3:
                                    BOT_CONFIG["target_spam"][gid] = {"username": p[1].replace("@", ""), "message": p[2]}
                                    BOT_CONFIG["spam_active"][gid] = True
                                    cl.direct_send("Spam started", thread_ids=[gid])
                            elif ia and tl in ["/stopspam", "!stopspam"]:
                                BOT_CONFIG["spam_active"][gid] = False
                                cl.direct_send("Spam stopped!", thread_ids=[gid])
                        if g.messages:
                            lm[gid] = g.messages[0].id
                    cm = {u.pk for u in g.users}
                    nwm = cm - km[gid]
                    if nwm:
                        for u in g.users:
                            if u.pk in nwm and u.username != un:
                                if STOP_EVENT.is_set():
                                    break
                                log("NEW: @" + u.username)
                                for ms in wm:
                                    if STOP_EVENT.is_set():
                                        break
                                    fm = ("@" + u.username + " " + ms) if ucn else ms
                                    cl.direct_send(fm, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    log("Welcomed @" + u.username)
                                    time.sleep(dly)
                                km[gid].add(u.pk)
                    km[gid] = cm
                except:
                    pass
            time.sleep(pol)
        except:
            pass
    log("Stopped")

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "Running"})
    un = request.form.get("username")
    pw = request.form.get("password")
    wl = [m.strip() for m in request.form.get("welcome", "").splitlines() if m.strip()]
    gids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    adm = [a.strip() for a in request.form.get("admin_ids", "").split(",") if a.strip()]
    if not un or not pw or not gids or not wl:
        return jsonify({"message": "Fill fields"})
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(target=run_bot, args=(un, pw, wl, gids, int(request.form.get("delay", 3)), int(request.form.get("poll", 5)), request.form.get("use_custom_name") == "yes", request.form.get("enable_commands") == "yes", adm), daemon=True)
    BOT_THREAD.start()
    return jsonify({"message": "Started!"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    STOP_EVENT.set()
    return jsonify({"message": "Stopped!"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-200:]})

PAGE_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>🌟 NEON BOT</title><style>@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&display=swap');*{margin:0;padding:0;box-sizing:border-box}body{font-family:'Orbitron',sans-serif;min-height:100vh;background:#000;position:relative;overflow-x:hidden;color:#fff;padding:20px}body::before{content:'';position:fixed;top:0;left:0;width:100%;height:100%;background-image:url('https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=1920&q=80');background-size:cover;background-position:center;background-repeat:no-repeat;opacity:.2;z-index:-2}body::after{content:'';position:fixed;top:0;left:0;width:100%;height:100%;background:radial-gradient(circle at 20% 50%,rgba(120,0,255,.5) 0%,transparent 50%),radial-gradient(circle at 80% 80%,rgba(255,0,150,.5) 0%,transparent 50%),radial-gradient(circle at 40% 20%,rgba(0,255,255,.5) 0%,transparent 50%);background-size:200% 200%;animation:gradientShift 15s ease infinite;z-index:-1}@keyframes gradientShift{0%,100%{background-position:0% 50%}50%{background-position:100% 50%}}@keyframes neonPulse{0%,100%{text-shadow:0 0 10px #0ff,0 0 20px #0ff,0 0 30px #0ff,0 0 40px #0ff,0 0 50px #0ff}50%{text-shadow:0 0 5px #0ff,0 0 10px #0ff,0 0 15px #0ff,0 0 20px #0ff,0 0 25px #0ff}}@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-15px)}}@keyframes borderGlow{0%,100%{box-shadow:0 0 20px rgba(0,255,255,.7),inset 0 0 20px rgba(0,255,255,.3)}50%{box-shadow:0 0 40px rgba(0,255,255,.9),inset 0 0 30px rgba(0,255,255,.4)}}.c{max-width:850px;margin:0 auto;background:rgba(5,5,20,.95);border-radius:30px;padding:45px;box-shadow:0 0 60px rgba(0,255,255,.6),0 0 120px rgba(255,0,255,.4);border:2px solid rgba(0,255,255,.7);backdrop-filter:blur(20px);animation:float 6s ease-in-out infinite,borderGlow 3s ease-in-out infinite;position:relative}h1{text-align:center;font-size:60px;font-weight:900;margin-bottom:45px;background:linear-gradient(90deg,#0ff,#f0f,#0ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:neonPulse 2s ease-in-out infinite;letter-spacing:5px;text-transform:uppercase;position:relative}h1::after{content:'';position:absolute;top:0;left:0;right:0;background:linear-gradient(90deg,transparent,#0ff,transparent);-webkit-background-clip:text;-webkit-text-fill-color:transparent;opacity:.5;animation:slide 3s linear infinite}@keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}label{display:block;margin:20px 0 10px;color:#0ff;font-weight:700;font-size:16px;text-transform:uppercase;letter-spacing:2px;text-shadow:0 0 15px rgba(0,255,255,.9)}.sub{font-size:12px;color:rgba(0,255,255,.7);margin-top:6px;font-weight:400;letter-spacing:1px}input,textarea,select{width:100%;padding:16px;border:2px solid rgba(0,255,255,.6);border-radius:15px;background:rgba(0,15,30,.8);color:#fff;font-size:16px;font-family:'Orbitron',sans-serif;transition:all .3s;backdrop-filter:blur(5px)}input:focus,textarea:focus,select:focus{outline:0;border-color:#0ff;box-shadow:0 0 25px rgba(0,255,255,.8),inset 0 0 15px rgba(0,255,255,.3);background:rgba(0,20,40,.9);transform:scale(1.02)}textarea{min-height:110px;resize:vertical}::placeholder{color:rgba(0,255,255,.5)}.bc{display:flex;justify-content:center;gap:30px;margin-top:40px;flex-wrap:wrap}button{padding:20px 55px;font-size:22px;font-weight:700;border:none;border-radius:50px;cursor:pointer;font-family:'Orbitron',sans-serif;text-transform:uppercase;letter-spacing:3px;transition:all .3s;position:relative;overflow:hidden}.bs{background:linear-gradient(135deg,#0ff,#0af);color:#000;box-shadow:0 0 30px rgba(0,255,255,.7);animation:buttonPulse 2s ease-in-out infinite}@keyframes buttonPulse{0%,100%{box-shadow:0 0 30px rgba(0,255,255,.7)}50%{box-shadow:0 0 50px rgba(0,255,255,1)}}.bs:hover{transform:scale(1.1) rotate(3deg);box-shadow:0 0 50px rgba(0,255,255,1)}.bp{background:linear-gradient(135deg,#f0f,#f06);color:#fff;box-shadow:0 0 30px rgba(255,0,255,.7)}.bp:hover{transform:scale(1.1) rotate(-3deg);box-shadow:0 0 50px rgba(255,0,255,1)}button:active{transform:scale(.95)}.ls{margin-top:50px}.lt{text-align:center;color:#0ff;font-size:32px;margin-bottom:30px;text-transform:uppercase;letter-spacing:5px;text-shadow:0 0 20px rgba(0,255,255,.9);animation:neonPulse 2s ease-in-out infinite}.lb{background:rgba(0,0,0,.9);border:2px solid rgba(0,255,255,.6);border-radius:20px;padding:30px;height:320px;overflow-y:auto;font-family:monospace;font-size:15px;line-height:2.2;box-shadow:inset 0 0 40px rgba(0,255,255,.3),0 0 25px rgba(0,255,255,.4);backdrop-filter:blur(10px)}.lb::-webkit-scrollbar{width:14px}.lb::-webkit-scrollbar-track{background:rgba(0,0,0,.7);border-radius:10px}.lb::-webkit-scrollbar-thumb{background:linear-gradient(180deg,#0ff,#f0f);border-radius:10px;box-shadow:0 0 15px rgba(0,255,255,.6)}.le{color:#0ff;margin-bottom:10px;animation:fadeIn .5s;text-shadow:0 0 8px rgba(0,255,255,.6)}@keyframes fadeIn{from{opacity:0;transform:translateX(-25px)}to{opacity:1;transform:translateX(0)}}@media(max-width:768px){.c{padding:30px;margin:10px}h1{font-size:40px}.bc{flex-direction:column}button{width:100%}}</style></head><body><div class="c"><h1>🌟 NEON BOT 🌟</h1><form id="f"><label>🤖 USERNAME</label><input name="username" placeholder="Instagram username"><label>🔐 PASSWORD</label><input type="password" name="password" placeholder="Password"><label>👑 ADMINS<div class="sub">Comma separated: admin1,admin2</div></label><input name="admin_ids" placeholder="admin1,admin2"><label>💬 WELCOME<div class="sub">One per line - sent to new members</div></label><textarea name="welcome" placeholder="Welcome to our group!
Glad you joined!
Introduce yourself!"></textarea><label>📝 MENTION?</label><select name="use_custom_name"><option value="yes">✅ Yes - Add @username</option><option value="no">❌ No</option></select><label>⚙️ COMMANDS?</label><select name="enable_commands"><option value="yes">✅ Yes - All active</option><option value="no">❌ No</option></select><label>👥 GROUPS<div class="sub">Comma separated IDs</div></label><input name="group_ids" placeholder="123456789,987654321"><label>⏱️ DELAY (seconds)</label><input type="number" name="delay" value="3" min="1" max="10"><label>🔄 POLL (seconds)</label><input type="number" name="poll" value="5" min="3" max="30"><div class="bc"><button type="button" class="bs" onclick="start()">▶️ START</button><button type="button" class="bp" onclick="stop()">⏹️ STOP</button></div></form><div class="ls"><div class="lt">📋 LIVE LOGS</div><div class="lb" id="l">🔌 Waiting for bot to start...</div></div></div><script>async function start(){let r=await fetch('/start',{method:'POST',body:new FormData(document.getElementById('f'))});alert((await r.json()).message)}async function stop(){let r=await fetch('/stop',{method:'POST'});alert((await r.json()).message)}setInterval(async()=>{let r=await fetch('/logs');let d=await r.json();let b=document.getElementById('l');b.innerHTML=d.logs.map(l=>'<div class="le">'+l+'</div>').join('')||'Start bot...';b.scrollTop=b.scrollHeight},2000)</script></body></html>"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
