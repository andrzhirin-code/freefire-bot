import json
import threading
from datetime import datetime, timedelta
import requests
import time
import os
from flask import Flask
from config import *
from states import *
from database import get_user
from phones_db import *
from prompts import SYSTEM_PROMPT, build_user_prompt, build_correction_prompt

app = Flask(__name__)
user_states = {}
last_category = {}
longpoll_server = None
longpoll_key = None
longpoll_ts = None

POINTS_FILE = "/opt/render/project/src/points.json"
POINTS_BACKUP = "/opt/render/project/src/points_backup.json"

POINTS_LIKE = 5
POINTS_COMMENT = 10
POINTS_PREMIUM = 400
POINTS_EXPIRE_DAYS = 30
MAX_LIKES_PER_DAY = 10
MAX_COMMENTS_PER_DAY = 5

points_cache = {}
points_lock = threading.Lock()

def log(msg):
    with open("/tmp/bot.log", "a") as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except:
            pass
    return default

def save_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f)
    except:
        pass

def load_points():
    global points_cache
    with points_lock:
        data = load_json(POINTS_FILE, {})
        if not data:
            data = load_json(POINTS_BACKUP, {})
            if data:
                save_json(POINTS_FILE, data)
        points_cache = data

def save_points(data):
    global points_cache
    with points_lock:
        points_cache = data
        save_json(POINTS_FILE, data)
        save_json(POINTS_BACKUP, data)

def get_user_points(uid):
    key = str(uid)
    with points_lock:
        if key not in points_cache:
            points_cache[key] = {
                "points": 0,
                "last_active": datetime.now().isoformat(),
                "likes_today": 0,
                "comments_today": 0,
                "day": datetime.now().strftime("%Y-%m-%d")
            }
            save_points(points_cache)
        else:
            today = datetime.now().strftime("%Y-%m-%d")
            if points_cache[key].get("day") != today:
                points_cache[key]["likes_today"] = 0
                points_cache[key]["comments_today"] = 0
                points_cache[key]["day"] = today
                save_points(points_cache)
    return points_cache, key

def add_points(uid, amount, action_type=None):
    data, key = get_user_points(uid)
    with points_lock:
        today = datetime.now().strftime("%Y-%m-%d")
        if data[key].get("day") != today:
            data[key]["likes_today"] = 0
            data[key]["comments_today"] = 0
            data[key]["day"] = today
        if action_type == "like" and data[key].get("likes_today", 0) >= MAX_LIKES_PER_DAY:
            return False
        if action_type == "comment" and data[key].get("comments_today", 0) >= MAX_COMMENTS_PER_DAY:
            return False
        data[key]["points"] = max(0, data[key].get("points", 0) + amount)
        data[key]["last_active"] = datetime.now().isoformat()
        if action_type == "like":
            data[key]["likes_today"] += 1
        elif action_type == "comment":
            data[key]["comments_today"] += 1
        save_points(data)
    return True

def check_points_expiry(uid):
    data, key = get_user_points(uid)
    with points_lock:
        last = data[key].get("last_active")
        if last:
            if datetime.now() - datetime.fromisoformat(last) > timedelta(days=POINTS_EXPIRE_DAYS):
                data[key]["points"] = 0
                data[key]["last_active"] = datetime.now().isoformat()
                save_points(data)
                return True
    return False

def vk_api(method, params):
    params["v"] = "5.131"
    params["access_token"] = VK_TOKEN
    resp = requests.post(f"https://api.vk.com/method/{method}", params=params)
    result = resp.json()
    if "error" in result:
        log(f"❌ VK API {method}: {result['error']['error_msg']}")
    return result

def send_message(user_id, text, keyboard=None):
    params = {"user_id": user_id, "message": text, "random_id": 0}
    if keyboard is not None:
        params["keyboard"] = json.dumps(keyboard) if keyboard else ""
    else:
        params["keyboard"] = json.dumps({"one_time": False, "buttons": []})
    return vk_api("messages.send", params)

def send_menu(user_id):
    kb = {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "📱 БЕСПЛАТНЫЕ НАСТРОЙКИ"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "🔥 ПРЕМИУМ НАСТРОЙКА — 99₽"}, "color": "positive"}],
            [{"action": {"type": "text", "label": "⭐ МОИ БАЛЛЫ"}, "color": "primary"}],
            [{"action": {"type": "open_link", "label": "🛒 МАГАЗИН", "link": "https://vk.com/market-193012947"}}],
        ]
    }
    send_message(user_id, "🎮 Привет, боец!\n\n📱 БЕСПЛАТНЫЕ НАСТРОЙКИ — готовые конфиги\n🔥 ПРЕМИУМ — ИИ подбирает лично под тебя\n⭐ БАЛЛЫ — активничай и меняй на премиум\n🛒 МАГАЗИН — перейти в магазин", keyboard=kb)

def back_and_menu_kb():
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "← Назад"}, "color": "secondary"},
             {"action": {"type": "text", "label": "🏠 В меню"}, "color": "secondary"}],
        ]
    }

def premium_inline_kb():
    return {
        "inline": True,
        "buttons": [
            [{"action": {"type": "callback", "label": "🔥 ПРЕМИУМ НАСТРОЙКА — 99₽", "payload": "{\"cmd\":\"premium\"}"}, "color": "positive"}]
        ]
    }

def call_deepseek(prompt):
    if not DEEPSEEK_API_KEY:
        return "❌ ИИ не настроен."
    try:
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1500
        }
        resp = requests.post(
            "https://api.proxyapi.ru/deepseek/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        result = resp.json()
        if "choices" in result:
            return result["choices"][0]["message"]["content"]
        else:
            log(f"❌ DeepSeek: {result}")
            return "❌ Ошибка ИИ. Попробуй позже."
    except Exception as e:
        log(f"❌ DeepSeek: {e}")
        return "❌ Ошибка ИИ. Попробуй позже."

def handle_message(user_id, text):
    log(f"💬 user={user_id} text={text}")
    user = get_user(user_id)
    state = user_states.get(user_id, "MENU")
    t = text.strip()

    if t.lower() in ["меню", "начать", "старт", "start"]:
        user_states[user_id] = "MENU"
        send_menu(user_id)
        return

    if t == "⭐ МОИ БАЛЛЫ":
        expired = check_points_expiry(user_id)
        data, key = get_user_points(user_id)
        pts = data[key]["points"]
        need = max(0, POINTS_PREMIUM - pts)
        kb = {
            "one_time": False,
            "buttons": [
                [{"action": {"type": "text", "label": "🔥 Обменять баллы"}, "color": "positive"}],
                [{"action": {"type": "text", "label": "← Назад"}, "color": "secondary"},
                 {"action": {"type": "text", "label": "🏠 В меню"}, "color": "secondary"}],
            ]
        }
        if expired:
            send_message(user_id, f"⌛ Баллы сгорели.\n\n⭐ Сейчас: 0 баллов\n🔥 Нужно: {POINTS_PREMIUM}\n\n+{POINTS_LIKE} за лайк (макс {MAX_LIKES_PER_DAY}/день)\n+{POINTS_COMMENT} за комментарий (макс {MAX_COMMENTS_PER_DAY}/день)", keyboard=kb)
        else:
            send_message(user_id, f"⭐ Твои баллы: {pts}\n🔥 Нужно: {POINTS_PREMIUM}\n📊 Не хватает: {need}\n\n+{POINTS_LIKE} за лайк (макс {MAX_LIKES_PER_DAY}/день)\n+{POINTS_COMMENT} за комментарий (макс {MAX_COMMENTS_PER_DAY}/день)", keyboard=kb)
        return

    if t == "📱 БЕСПЛАТНЫЕ НАСТРОЙКИ":
        user_states[user_id] = "FREE_PHONES"
        brands = ["Xiaomi/Redmi/Poco", "Samsung", "iPhone", "Realme", "Tecno/Infinix", "Другие"]
        kb = {"one_time": False, "buttons": []}
        row = []
        for b in brands:
            row.append({"action": {"type": "text", "label": b}, "color": "primary"})
            if len(row) == 2:
                kb["buttons"].append(row)
                row = []
        if row:
            kb["buttons"].append(row)
        kb["buttons"].append([{"action": {"type": "text", "label": "← Назад"}, "color": "secondary"},
                              {"action": {"type": "text", "label": "🏠 В меню"}, "color": "secondary"}])
        send_message(user_id, "📱 Выбери марку:", keyboard=kb)
        return

    if t in ["🔥 ПРЕМИУМ НАСТРОЙКА — 99₽", "🔥 Хочу премиум"]:
        user.premium_active = True
        user.corrections_left = MAX_CORRECTIONS
        user_states[user_id] = "AI_ASK_PHONE"
        send_message(user_id, f"✅ Премиум активирован (тестовый режим)!\n\n📱 Вопрос 1 из 7:\nНапиши модель телефона.", keyboard=back_and_menu_kb())
        return

    if t == "🔥 Обменять баллы":
        data, key = get_user_points(user_id)
        check_points_expiry(user_id)
        pts = data[key]["points"]
        if pts >= POINTS_PREMIUM:
            data[key]["points"] -= POINTS_PREMIUM
            save_points(data)
            user.premium_active = True
            user.corrections_left = MAX_CORRECTIONS
            user_states[user_id] = "AI_ASK_PHONE"
            send_message(user_id, f"✅ Премиум активирован за {POINTS_PREMIUM} баллов!\nОсталось: {data[key]['points']}", keyboard=back_and_menu_kb())
        else:
            need = POINTS_PREMIUM - pts
            send_message(user_id, f"❌ Не хватает баллов.\nУ тебя: {pts}\nНужно: {POINTS_PREMIUM}\nНе хватает: {need}", keyboard=back_and_menu_kb())
        return

    cat_map = {
        "Xiaomi/Redmi/Poco": CATEGORIES["📱 Xiaomi (Redmi/Poco)"],
        "Samsung": CATEGORIES["📱 Samsung"],
        "iPhone": CATEGORIES["📱 iPhone"],
        "Realme": CATEGORIES["📱 Realme"],
        "Tecno/Infinix": CATEGORIES["📱 Tecno/Infinix"],
        "Другие": CATEGORIES["📱 Другие"],
    }

    if t in cat_map:
        phones = cat_map[t]
        last_category[user_id] = phones
        kb = {"one_time": False, "buttons": []}
        row = []
        for phone in phones:
            row.append({"action": {"type": "text", "label": phone.title()}, "color": "primary"})
            if len(row) == 2:
                kb["buttons"].append(row)
                row = []
        if row:
            kb["buttons"].append(row)
        kb["buttons"].append([{"action": {"type": "text", "label": "← Назад"}, "color": "secondary"},
                              {"action": {"type": "text", "label": "🏠 В меню"}, "color": "secondary"}])
        send_message(user_id, "📱 Выбери модель:", keyboard=kb)
        return

    if t in ["← Назад", "🏠 В меню"]:
        user_states[user_id] = "MENU"
        send_menu(user_id)
        return

    phone = find_phone(t)
    if phone:
        config = get_config(phone)
        if config:
            send_message(user_id, config, keyboard=premium_inline_kb())
            return

    if state == "AI_ASK_PHONE":
        user.phone = t
        user_states[user_id] = "AI_ASK_RAM"
        send_message(user_id, "📱 Вопрос 2 из 7:\nСколько ОЗУ?", keyboard=back_and_menu_kb())
        return
    if state == "AI_ASK_RAM":
        user.ram = t
        user_states[user_id] = "AI_ASK_STYLE"
        send_message(user_id, "🎮 Вопрос 3 из 7:\nСтиль игры?", keyboard=back_and_menu_kb())
        return
    if state == "AI_ASK_STYLE":
        user.style = t
        user_states[user_id] = "AI_ASK_WEAPON"
        send_message(user_id, "🔫 Вопрос 4 из 7:\nОружие?", keyboard=back_and_menu_kb())
        return
    if state == "AI_ASK_WEAPON":
        user.weapon = t
        user_states[user_id] = "AI_ASK_FINGERS"
        send_message(user_id, "🤟 Вопрос 5 из 7:\nСколько пальцев?", keyboard=back_and_menu_kb())
        return
    if state == "AI_ASK_FINGERS":
        user.fingers = t
        user_states[user_id] = "AI_ASK_GYRO"
        send_message(user_id, "📳 Вопрос 6 из 7:\nГироскоп?", keyboard=back_and_menu_kb())
        return
    if state == "AI_ASK_GYRO":
        user.gyro = t
        user_states[user_id] = "AI_ASK_PROBLEM"
        send_message(user_id, "🔧 Вопрос 7 из 7:\nПроблема?", keyboard=back_and_menu_kb())
        return
    if state == "AI_ASK_PROBLEM":
        user.problem = t if t.lower() != "нет" else ""
        user_states[user_id] = "AI_DONE"
        send_message(user_id, "🤖 ИИ подбирает настройки...")
        prompt = build_user_prompt(user)
        response = call_deepseek(prompt)
        send_message(user_id, response + f"\n\n🔄 Корректировок: {user.corrections_left}")
        return

    if "корректировка" in t.lower():
        if state == "AI_DONE" and user.corrections_left > 0:
            user_states[user_id] = "CORRECTION"
            send_message(user_id, f"🔄 Режим корректировки.\nОпиши проблему.", keyboard=back_and_menu_kb())
            return
        elif state == "CORRECTION" and user.corrections_left > 0:
            user.corrections_left -= 1
            prompt = build_correction_prompt(user, t)
            response = call_deepseek(prompt)
            user_states[user_id] = "AI_DONE"
            send_message(user_id, response + f"\n\n🔄 Осталось корректировок: {user.corrections_left}")
            return
        else:
            send_message(user_id, "❌ Лимит корректировок исчерпан.", keyboard=back_and_menu_kb())
            return

    if t in ["/stat", "/admin"] and user_id == ADMIN_ID:
        with points_lock:
            total = len(points_cache)
            top = sorted(points_cache.items(), key=lambda x: x[1]["points"], reverse=True)[:10]
        top_str = "\n".join([f"{i+1}. ID {k}: {v['points']} баллов" for i, (k, v) in enumerate(top)])
        send_message(user_id, f"📊 СТАТИСТИКА\n👥 Пользователей: {total}\n📱 Моделей: {len(PHONES)}\n\n🏆 Топ-10:\n{top_str}")
        return

    send_message(user_id, "❌ Я отвечаю только по настройкам Free Fire.\nНапиши «меню».", keyboard=back_and_menu_kb())

def get_longpoll_server():
    global longpoll_server, longpoll_key, longpoll_ts
    resp = vk_api("groups.getLongPollServer", {"group_id": GROUP_ID})
    if "response" in resp:
        longpoll_server = resp["response"]["server"]
        longpoll_key = resp["response"]["key"]
        longpoll_ts = resp["response"]["ts"]

def longpoll_loop():
    global longpoll_ts
    while True:
        try:
            if not longpoll_server:
                get_longpoll_server()
            url = f"{longpoll_server}?act=a_check&key={longpoll_key}&ts={longpoll_ts}&wait=25"
            resp = requests.get(url, timeout=30).json()
            if "failed" in resp:
                get_longpoll_server()
                continue
            longpoll_ts = resp.get("ts", longpoll_ts)
            for update in resp.get("updates", []):
                if update["type"] == "message_new":
                    msg = update["object"]["message"]
                    uid = msg.get("from_id")
                    txt = msg.get("text", "")
                    if uid and uid < 0: uid = abs(uid)
                    if uid and txt:
                        threading.Thread(target=handle_message, args=(uid, txt)).start()
                elif update["type"] == "message_event":
                    obj = update["object"]
                    uid = obj.get("user_id")
                    payload = obj.get("payload", {})
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    vk_api("messages.sendMessageEventAnswer", {
                        "event_id": obj.get("event_id"),
                        "user_id": uid,
                        "peer_id": obj.get("peer_id"),
                    })
                    if payload.get("cmd") == "premium":
                        threading.Thread(target=handle_message, args=(uid, "🔥 ПРЕМИУМ НАСТРОЙКА — 99₽")).start()
                elif update["type"] == "like_add":
                    uid = update["object"].get("liker_id", 0)
                    if uid:
                        if uid < 0: uid = abs(uid)
                        add_points(uid, POINTS_LIKE, "like")
                elif update["type"] == "like_remove":
                    uid = update["object"].get("liker_id", 0)
                    if uid:
                        if uid < 0: uid = abs(uid)
                        add_points(uid, -POINTS_LIKE, "like")
                elif update["type"] == "wall_reply_new":
                    uid = update["object"].get("from_id", 0)
                    if uid:
                        if uid < 0: uid = abs(uid)
                        add_points(uid, POINTS_COMMENT, "comment")
                elif update["type"] == "wall_reply_delete":
                    uid = update["object"].get("from_id", 0)
                    if uid:
                        if uid < 0: uid = abs(uid)
                        add_points(uid, -POINTS_COMMENT, "comment")
        except Exception as e:
            time.sleep(3)

def keep_alive():
    while True:
        time.sleep(540)
        try:
            requests.get("https://freefire-bot-xzgu.onrender.com/ping")
        except:
            pass

@app.route("/")
def home():
    return "Bot is running"

@app.route("/ping")
def ping():
    return "ok"

@app.route("/log")
def show_log():
    try:
        with open("/tmp/bot.log", "r") as f:
            return "<pre>" + f.read() + "</pre>"
    except:
        return "empty"

@app.route("/points")
def show_points():
    try:
        with open(POINTS_FILE, "r") as f:
            return "<pre>" + f.read() + "</pre>"
    except:
        return "no data"

if __name__ == "__main__":
    load_points()
    get_longpoll_server()
    threading.Thread(target=longpoll_loop, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
