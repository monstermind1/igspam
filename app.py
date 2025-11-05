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

PAGE_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NEON BOT</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:Arial,sans-serif;min-height:100vh;background:#000;position:relative;color:#fff;padding:15px}body::before{content:'';position:fixed;top:0;left:0;width:100%;height:100%;background-image:url('https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=1920&q=80');background-size:cover;background-position:center;opacity:.35;z-index:-2}body::after{content:'';position:fixed;top:0;left:0;width:100%;height:100%;background:radial-gradient(circle at 20% 50%,rgba(0,200,255,.25),transparent 60%),radial-gradient(circle at 80% 80%,rgba(255,0,150,.25),transparent 60%);z-index:-1}.c{max-width:700px;margin:0 auto;background:rgba(10,10,30,.75);border-radius:20px;padding:25px;border:2px solid rgba(0,255,255,.5);box-shadow:0 0 30px rgba(0,255,255,.3)}h1{text-align:center;font-size:42px;font-weight:900;margin-bottom:25px;color:#0ff;text-shadow:0 0 5px #0ff,0 0 10px #0ff,0 0 15px #0ff;letter-spacing:3px}label{display:block;margin:12px 0 5px;font-weight:600;font-size:13px}.f1{color:#0ff}.f2{color:#ff00ff}.f3{color:#00ff88}.f4{color:#ffaa00}.f5{color:#ff0066}.f6{color:#00ddff}.f7{color:#88ff00}.f8{color:#ff6600}input,textarea,select{width:100%;padding:10px;border-radius:10px;background:rgba(0,20,40,.7);color:#fff;font-size:14px;transition:all .3s}input:focus,textarea:focus,select:focus{outline:0;transform:scale(1.02)}.i1{border:2px solid rgba(0,255,255,.5)}.i1:focus{border-color:#0ff;box-shadow:0 0 15px rgba(0,255,255,.5)}.i2{border:2px solid rgba(255,0,255,.5)}.i2:focus{border-color:#f0f;box-shadow:0 0 15px rgba(255,0,255,.5)}.i3{border:2px solid rgba(0,255,136,.5)}.i3:focus{border-color:#0f8;box-shadow:0 0 15px rgba(0,255,136,.5)}.i4{border:2px solid rgba(255,170,0,.5)}.i4:focus{border-color:#fa0;box-shadow:0 0 15px rgba(255,170,0,.5)}.i5{border:2px solid rgba(255,0,102,.5)}.i5:focus{border-color:#f06;box-shadow:0 0 15px rgba(255,0,102,.5)}.i6{border:2px solid rgba(0,221,255,.5)}.i6:focus{border-color:#0df;box-shadow:0 0 15px rgba(0,221,255,.5)}.i7{border:2px solid rgba(136,255,0,.5)}.i7:focus{border-color:#8f0;box-shadow:0 0 15px rgba(136,255,0,.5)}.i8{border:2px solid rgba(255,102,0,.5)}.i8:focus{border-color:#f60;box-shadow:0 0 15px rgba(255,102,0,.5)}textarea{min-height:70px;resize:vertical}::placeholder{color:rgba(255,255,255,.4)}.bc{display:flex;justify-content:center;gap:15px;margin-top:25px}button{padding:12px 35px;font-size:16px;font-weight:700;border:none;border-radius:25px;cursor:pointer;text-transform:uppercase;transition:all .3s}.bs{background:linear-gradient(135deg,#0ff,#00a8cc);color:#000;box-shadow:0 0 20px rgba(0,255,255,.5)}.bp{background:linear-gradient(135deg,#f0f,#c00);color:#fff;box-shadow:0 0 20px rgba(255,0,255,.5)}.bs:hover,.bp:hover{transform:scale(1.08)}.ls{margin-top:30px}.lt{text-align:center;color:#0ff;font-size:20px;margin-bottom:15px;font-weight:700;text-shadow:0 0 10px rgba(0,255,255,.8)}.lb{background:rgba(0,0,0,.8);border:2px solid rgba(0,255,255,.4);border-radius:15px;padding:20px;height:200px;overflow-y:auto;font-family:monospace;font-size:13px;line-height:1.8;box-shadow:inset 0 0 20px rgba(0,255,255,.2)}.lb::-webkit-scrollbar{width:8px}.lb::-webkit-scrollbar-track{background:rgba(0,0,0,.5)}.lb::-webkit-scrollbar-thumb{background:linear-gradient(180deg,#0ff,#f0f);border-radius:5px}.le{color:#0ff;margin-bottom:5px;text-shadow:0 0 5px rgba(0,255,255,.5)}@media(max-width:768px){.c{padding:20px}h1{font-size:32px}.bc{flex-direction:column}button{width:100%}}</style></head><body><div class="c"><h1>NEON BOT</h1><form id="f"><label class="f1">USERNAME</label><input class="i1" name="username" placeholder="Instagram username"><label class="f2">PASSWORD</label><input class="i2" type="password" name="password" placeholder="Password"><label class="f3">ADMINS</label><input class="i3" name="admin_ids" placeholder="admin1,admin2"><label class="f4">WELCOME</label><textarea class="i4" name="welcome" placeholder="Welcome to group!
Glad you joined!"></textarea><label class="f5">MENTION?</label><select class="i5" name="use_custom_name"><option value="yes">Yes</option><option value="no">No</option></select><label class="f6">COMMANDS?</label><select class="i6" name="enable_commands"><option value="yes">Yes</option></select><label class="f7">GROUPS</label><input class="i7" name="group_ids" placeholder="123456789,987654321"><label class="f8">DELAY</label><input class="i8" type="number" name="delay" value="3" min="1"><label class="f1">POLL</label><input class="i1" type="number" name="poll" value="5" min="3"><div class="bc"><button type="button" class="bs" onclick="start()">START</button><button type="button" class="bp" onclick="stop()">STOP</button></div></form><div class="ls"><div class="lt">LIVE LOGS</div><div class="lb" id="l">Waiting for bot...</div></div></div><script>async function start(){let r=await fetch('/start',{method:'POST',body:new FormData(document.getElementById('f'))});alert((await r.json()).message)}async function stop(){let r=await fetch('/stop',{method:'POST'});alert((await r.json()).message)}setInterval(async()=>{let r=await fetch('/logs');let d=await r.json();let b=document.getElementById('l');b.innerHTML=d.logs.map(l=>'<div class="le">'+l+'</div>').join('')||'Start bot...';b.scrollTop=b.scrollHeight},2000)</script></body></html>"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
