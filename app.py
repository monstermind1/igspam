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
STATS = {"total_welcomed": 0, "today_welcomed": 0, "last_reset": datetime.now().date()}

def log(msg):
    ts = datetime.now().strftime('%H:%M:%S')
    lm = "[" + ts + "] " + msg
    LOGS.append(lm)
    print(lm)

def run_bot(un, pw, wm, gids, dly, pol, ucn, ecmd, admin_ids):
    cl = Client()
    try:
        if os.path.exists(SESSION_FILE):
            cl.load_settings(SESSION_FILE)
            cl.login(un, pw)
            log("Session loaded.")
        else:
            log("Logging in...")
            cl.login(un, pw)
            cl.dump_settings(SESSION_FILE)
            log("Session saved.")
    except Exception as e:
        log("Login failed: " + str(e))
        return
    log("Bot started - Monitoring...")
    log("Admin IDs: " + str(admin_ids))
    km = {}
    lm = {}
    for gid in gids:
        try:
            g = cl.direct_thread(gid)
            km[gid] = {u.pk for u in g.users}
            lm[gid] = g.messages[0].id if g.messages else None
            log("Tracking " + str(len(km[gid])) + " members in " + gid)
        except Exception as e:
            log("Error loading " + gid + ": " + str(e))
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
                    if ecmd:
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
                            sender_username = sender.username.lower()
                            is_admin = sender_username in [aid.lower() for aid in admin_ids]
                            if not is_admin and admin_ids:
                                continue
                            t = m.text.strip().lower() if m.text else ""
                            if t in ["/help", "!help"]:
                                cl.direct_send("ADMIN COMMANDS: /help /stats /count /welcome /ping /time /about", thread_ids=[gid])
                                log("Help sent to @" + sender.username)
                            elif t in ["/stats", "!stats"]:
                                cl.direct_send("STATS - Total: " + str(STATS['total_welcomed']) + " Today: " + str(STATS['today_welcomed']), thread_ids=[gid])
                                log("Stats sent to @" + sender.username)
                            elif t in ["/count", "!count"]:
                                mc = len(g.users)
                                cl.direct_send("MEMBERS - Total: " + str(mc), thread_ids=[gid])
                                log("Count sent to @" + sender.username)
                            elif t in ["/welcome", "!welcome"]:
                                cl.direct_send("@" + sender.username + " Test welcome!", thread_ids=[gid])
                                log("Test to @" + sender.username)
                            elif t in ["/ping", "!ping"]:
                                cl.direct_send("Pong! Bot is alive!", thread_ids=[gid])
                                log("Ping reply to @" + sender.username)
                            elif t in ["/time", "!time"]:
                                ct = datetime.now().strftime("%I:%M %p")
                                cl.direct_send("TIME: " + ct, thread_ids=[gid])
                                log("Time sent to @" + sender.username)
                            elif t in ["/about", "!about"]:
                                cl.direct_send("ABOUT - Insta Welcome Bot v2.0 - Auto-welcome + Admin Commands", thread_ids=[gid])
                                log("About sent to @" + sender.username)
                        if g.messages:
                            lm[gid] = g.messages[0].id
                    cm = {u.pk for u in g.users}
                    nwm = cm - km[gid]
                    if nwm:
                        for u in g.users:
                            if u.pk in nwm and u.username != un:
                                if STOP_EVENT.is_set():
                                    break
                                for ms in wm:
                                    if STOP_EVENT.is_set():
                                        break
                                    if ucn:
                                        fm = "@" + u.username + " " + ms
                                    else:
                                        fm = ms
                                    cl.direct_send(fm, thread_ids=[gid])
                                    STATS["total_welcomed"] += 1
                                    STATS["today_welcomed"] += 1
                                    log("Welcomed @" + u.username)
                                    for _ in range(dly):
                                        if STOP_EVENT.is_set():
                                            break
                                        time.sleep(1)
                                    if STOP_EVENT.is_set():
                                        break
                                km[gid].add(u.pk)
                    km[gid] = cm
                except Exception as e:
                    log("Error in " + gid + ": " + str(e))
            if STOP_EVENT.is_set():
                break
            for _ in range(pol):
                if STOP_EVENT.is_set():
                    break
                time.sleep(1)
        except Exception as e:
            log("Loop error: " + str(e))
    log("Bot stopped. Total: " + str(STATS['total_welcomed']))

@app.route("/")
def index():
    return render_template_string(PAGE_HTML)

@app.route("/start", methods=["POST"])
def start_bot():
    global BOT_THREAD, STOP_EVENT
    if BOT_THREAD and BOT_THREAD.is_alive():
        return jsonify({"message": "Already running."})
    un = request.form.get("username")
    pw = request.form.get("password")
    wl = request.form.get("welcome", "").splitlines()
    wl = [m.strip() for m in wl if m.strip()]
    gids = [g.strip() for g in request.form.get("group_ids", "").split(",") if g.strip()]
    admin_input = request.form.get("admin_ids", "").strip()
    admin_ids = [a.strip() for a in admin_input.split(",") if a.strip()] if admin_input else []
    dly = int(request.form.get("delay", 3))
    pol = int(request.form.get("poll", 10))
    ucn = request.form.get("use_custom_name") == "yes"
    ecmd = request.form.get("enable_commands") == "yes"
    if not un or not pw or not gids or not wl:
        return jsonify({"message": "Fill all fields."})
    STOP_EVENT.clear()
    BOT_THREAD = threading.Thread(target=run_bot, args=(un, pw, wl, gids, dly, pol, ucn, ecmd, admin_ids), daemon=True)
    BOT_THREAD.start()
    log("Bot started.")
    return jsonify({"message": "Bot started!"})

@app.route("/stop", methods=["POST"])
def stop_bot():
    global BOT_THREAD
    STOP_EVENT.set()
    log("Stopping...")
    if BOT_THREAD:
        BOT_THREAD.join(timeout=5)
    log("Stopped.")
    return jsonify({"message": "Bot stopped!"})

@app.route("/logs")
def get_logs():
    return jsonify({"logs": LOGS[-200:]})

@app.route("/stats")
def get_stats():
    return jsonify(STATS)

PAGE_HTML = """<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>INSTA BOT</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:Arial,sans-serif;background:#0f2027;color:#fff;padding:20px}.c{max-width:900px;margin:0 auto;background:rgba(255,255,255,.1);border-radius:15px;padding:30px}h1{text-align:center;margin-bottom:20px;color:#00eaff}.info{background:rgba(255,165,0,.15);border:2px solid rgba(255,165,0,.4);border-radius:10px;padding:15px;margin-bottom:20px;color:#ffa500;font-size:14px}label{display:block;margin:10px 0 5px;color:#00eaff;font-weight:600}.sub{font-size:12px;color:#43e97b;margin-top:3px}input,textarea,select{width:100%;padding:10px;border:2px solid rgba(0,234,255,.3);border-radius:8px;background:rgba(255,255,255,.1);color:#fff;font-size:14px}textarea{min-height:80px}button{padding:12px 25px;font-size:16px;font-weight:700;border:none;border-radius:8px;color:#fff;margin:8px 4px;cursor:pointer}.st{background:#00c6ff}.sp{background:#ff512f}.lb{background:rgba(0,0,0,.6);border-radius:12px;padding:15px;margin-top:25px;height:250px;overflow-y:auto;border:2px solid rgba(0,234,255,.3);font-family:monospace;font-size:13px}</style></head><body><div class="c"><h1>INSTA WELCOME BOT</h1><div class="info"><strong>ADMIN CONTROL FEATURE</strong><br>Sirf specified admin usernames hi commands use kar sakte hain!<br>Agar admin IDs khali chodi to sabhi members commands use kar sakte hain.</div><form id="f"><label>Bot Username<div class="sub">Instagram username jisse bot chalega</div></label><input name="username" placeholder="Instagram username"><label>Bot Password</label><input type="password" name="password" placeholder="Password"><label>Admin Usernames (Optional)<div class="sub">Comma separated - jaise: admin1,admin2,admin3 (khali chod sakte ho)</div></label><input name="admin_ids" placeholder="admin_username1,admin_username2"><label>Welcome Messages</label><textarea name="welcome" placeholder="Line 1 Line 2"></textarea><label>Mention Username?</label><select name="use_custom_name"><option value="yes">Yes</option><option value="no">No</option></select><label>Enable Commands?</label><select name="enable_commands"><option value="yes">Yes</option><option value="no">No</option></select><label>Group IDs</label><input name="group_ids" placeholder="123,456"><label>Delay</label><input type="number" name="delay" value="3"><label>Check Interval</label><input type="number" name="poll" value="10"><div style="text-align:center;margin-top:15px"><button type="button" class="st" onclick="start()">Start</button><button type="button" class="sp" onclick="stop()">Stop</button></div></form><h3 style="text-align:center;margin-top:30px;color:#00eaff">Logs</h3><div class="lb" id="l">Start bot...</div></div><script>async function start(){let d=new FormData(document.getElementById('f'));let r=await fetch('/start',{method:'POST',body:d});let j=await r.json();alert(j.message)}async function stop(){let r=await fetch('/stop',{method:'POST'});let j=await r.json();alert(j.message)}async function getLogs(){let r=await fetch('/logs');let j=await r.json();document.getElementById('l').innerHTML=j.logs.join('<br>')||'Start...'}setInterval(getLogs,2000)</script></body></html>"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
