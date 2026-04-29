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

app = Flask(__name__)
user_states = {}
last_category = {}
longpoll_server = None
longpoll_key = None
longpoll_ts = None

POINTS_FILE = "/tmp/points.json"
POINTS_BACKUP = "/tmp/points_backup.json"

# Баллы за действия
POINTS_LIKE = 5
POINTS_COMMENT = 10
POINTS_PREMIUM = 400
POINTS_EXPIRE_DAYS = 30
POST_MAX_AGE_DAYS = 5

def log(msg):
    with open("/tmp/bot.log", "a") as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")

def load_points():
    if os.path.exists(POINTS_FILE):
        try:
            with open(POINTS_FILE, "r") as f:
                return json.load(f)
        except:
            if os.path.exists(POINTS_BACKUP):
                with open(POINTS_BACKUP, "r") as f:
                    return json.load(f)
    return {}

def save_points(data):
    with open(POINTS_FILE, "w") as f:
        json.dump(data, f)
    with open(POINTS_BACKUP, "w") as f:
        json.dump(data, f)

def get_user_points(uid):
    data = load_points()
    key = str(uid)
    if key not in data:
        data[key] = {"points": 0, "last_active": datetime.now().isoformat()}
        save_points(data)
    return data, key

def add_points(uid, amount):
    data, key = get_user_points(uid)
    data[key]["points"] += amount
    data[key]["last_active"] = datetime.now().isoformat()
    save_points(data)
    log(f"⭐ +{amount} баллов пользователю {uid} (всего: {data[key]['points']})")

def check_points_expiry(uid):
    data, key = get_user_points(uid)
    last = data[key].get("last_active")
    if last:
        last_date = datetime.fromisoformat(last)
        if datetime.now() - last_date > timedelta(days=POINTS_EXPIRE_DAYS):
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
    if keyboard:
        params["keyboard"] = json.dumps(keyboard)
    return vk_api("messages.send", params)

def send_menu(user_id):
    kb = {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "📱 Бесплатные настройки"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "🔥 ПРЕМИУМ НАСТРОЙКА — 99₽"}, "color": "positive"}],
            [{"action": {"type": "text", "label": "⭐ Мои баллы"}, "color": "primary"}],
            [{"action": {"type": "open_link", "label": "🛒 МАГАЗИН", "link": "https://vk.com/market-193012947"}}],
        ]
    }
    send_message(user_id, "🎮 Привет, боец!\n\nЯ бот по настройкам Free Fire.\n\n📱 Бесплатные настройки — готовые конфиги\n🔥 Премиум — ИИ подбирает лично под тебя\n⭐ Баллы — получай за активность и меняй на премиум\n🛒 Магазин — перейти в магазин", keyboard=kb)

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

def handle_message(user_id, text):
    log(f"💬 user={user_id} text={text}")
    user = get_user(user_id)
    state = user_states.get(user_id, "MENU")
    t = text.strip()

    if t.lower() in ["меню", "начать", "старт", "start"]:
        user_states[user_id] = "MENU"
        send_menu(user_id)
        return

    if t == "⭐ Мои баллы":
        expired = check_points_expiry(user_id)
        data, key = get_user_points(user_id)
        pts = data[key]["points"]
        if expired:
            send_message(user_id, f"⌛ Твои баллы сгорели из-за неактивности.\n\n⭐ Сейчас: 0 баллов\n🔥 {POINTS_PREMIUM} баллов = премиум\n\nАктивничай: лайки +{POINTS_LIKE}, комменты +{POINTS_COMMENT}", keyboard=back_and_menu_kb())
        else:
            send_message(user_id, f"⭐ Твои баллы: {pts}\n\n🔥 {POINTS_PREMIUM} баллов = премиум\n\nАктивничай: лайки +{POINTS_LIKE}, комменты +{POINTS_COMMENT}", keyboard=back_and_menu_kb())
        return

    if t == "📱 Бесплатные настройки":
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
        send_message(user_id, "📱 Выбери марку телефона:", keyboard=kb)
        return

    if t in ["🔥 ПРЕМИУМ НАСТРОЙКА — 99₽", "🔥 Хочу премиум", "🔥 Обменять баллы"]:
        data, key = get_user_points(user_id)
        check_points_expiry(user_id)
        pts = data[key]["points"]
        if pts >= POINTS_PREMIUM:
            data[key]["points"] -= POINTS_PREMIUM
            save_points(data)
            user.premium_active = True
            user.corrections_left = MAX_CORRECTIONS
            user_states[user_id] = "AI_ASK_PHONE"
            send_message(user_id, f"✅ Премиум активирован за {POINTS_PREMIUM} баллов!\nОсталось баллов: {data[key]['points']}\n\n📱 Вопрос 1 из 5:\nНапиши точную модель телефона.\nНапример: Redmi Note 10, iPhone 11", keyboard=back_and_menu_kb())
        else:
            send_message(user_id, f"❌ Не хватает баллов.\nУ тебя: {pts}\nНужно: {POINTS_PREMIUM}\n\nЗарабатывай: лайки +{POINTS_LIKE}, комменты +{POINTS_COMMENT}", keyboard=back_and_menu_kb())
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
        send_message(user_id, "📱 Вопрос 2 из 5:\nСколько ОЗУ?\n• 2-3 ГБ\n• 4-6 ГБ\n• 8+ ГБ\n• Не знаю", keyboard=back_and_menu_kb())
        return
    if state == "AI_ASK_RAM":
        user.ram = t
        user_states[user_id] = "AI_ASK_STYLE"
        send_message(user_id, "🎮 Вопрос 3 из 5:\nСтиль игры?\n• Агрессивный\n• Пассивный\n• Смешанный", keyboard=back_and_menu_kb())
        return
    if state == "AI_ASK_STYLE":
        user.style = t
        user_states[user_id] = "AI_ASK_WEAPON"
        send_message(user_id, "🔫 Вопрос 4 из 5:\nОсновное оружие?\nНапример: M4A1, AK47, SCAR", keyboard=back_and_menu_kb())
        return
    if state == "AI_ASK_WEAPON":
        user.weapon = t
        user_states[user_id] = "AI_ASK_FINGERS"
        send_message(user_id, "🤟 Вопрос 5 из 5:\nСколько пальцев?\n• 2\n• 4\n• 6", keyboard=back_and_menu_kb())
        return
    if state == "AI_ASK_FINGERS":
        user.fingers = t
        user_states[user_id] = "AI_DONE"
        send_message(user_id, "🎯 Готово! ИИ подбирает настройки...\n(ИИ пока в разработке)")
        return

    if "корректировка" in t.lower():
        send_message(user_id, "🔄 Корректировка пока в разработке", keyboard=back_and_menu_kb())
        return

    if t in ["/stat", "/admin"] and user_id == ADMIN_ID:
        data = load_points()
        total_users = len(data)
        top = sorted(data.items(), key=lambda x: x[1]["points"], reverse=True)[:10]
        top_str = "\n".join([f"{i+1}. ID {k}: {v['points']} баллов" for i, (k, v) in enumerate(top)])
        send_message(user_id, f"📊 СТАТИСТИКА\n👥 Пользователей с баллами: {total_users}\n📱 Моделей: {len(PHONES)}\n\n🏆 Топ-10:\n{top_str}")
        return

    send_message(user_id, "❌ Я отвечаю только по настройкам Free Fire.\nНапиши «меню».", keyboard=back_and_menu_kb())

def get_longpoll_server():
    global longpoll_server, longpoll_key, longpoll_ts
    resp = vk_api("groups.getLongPollServer", {"group_id": GROUP_ID})
    if "response" in resp:
        longpoll_server = resp["response"]["server"]
        longpoll_key = resp["response"]["key"]
        longpoll_ts = resp["response"]["ts"]
        log(f"🔗 LongPoll подключён")

def is_post_fresh(post_id):
    try:
        resp = vk_api("wall.getById", {"posts": f"-{GROUP_ID}_{post_id}"})
        if "response" in resp and resp["response"]:
            post_date = resp["response"][0].get("date", 0)
            age = time.time() - post_date
            return age < POST_MAX_AGE_DAYS * 86400
    except:
        pass
    return False

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
                    user_id = msg.get("from_id")
                    text = msg.get("text", "")
                    if user_id and user_id < 0:
                        user_id = abs(user_id)
                    if user_id and text:
                        threading.Thread(target=handle_message, args=(user_id, text)).start()
                elif update["type"] == "message_event":
                    obj = update["object"]
                    user_id = obj.get("user_id")
                    event_id = obj.get("event_id")
                    peer_id = obj.get("peer_id")
                    payload = obj.get("payload", {})
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    cmd = payload.get("cmd", "")
                    log(f"🖲 message_event: user={user_id} cmd={cmd}")
                    vk_api("messages.sendMessageEventAnswer", {
                        "event_id": event_id,
                        "user_id": user_id,
                        "peer_id": peer_id,
                    })
                    if cmd == "premium":
                        threading.Thread(target=handle_message, args=(user_id, "🔥 ПРЕМИУМ НАСТРОЙКА — 99₽")).start()
                elif update["type"] == "like_add":
                    uid = update["object"].get("liker_id", 0)
                    post_id = update["object"].get("post_id", 0)
                    if uid and post_id:
                        if uid < 0:
                            uid = abs(uid)
                        if is_post_fresh(post_id):
                            add_points(uid, POINTS_LIKE)
                elif update["type"] == "like_remove":
                    uid = update["object"].get("liker_id", 0)
                    post_id = update["object"].get("post_id", 0)
                    if uid and post_id:
                        if uid < 0:
                            uid = abs(uid)
                        if is_post_fresh(post_id):
                            add_points(uid, -POINTS_LIKE)
                elif update["type"] == "wall_reply_new":
                    uid = update["object"].get("from_id", 0)
                    post_id = update["object"].get("post_id", 0)
                    if uid and post_id:
                        if uid < 0:
                            uid = abs(uid)
                        if is_post_fresh(post_id):
                            add_points(uid, POINTS_COMMENT)
                elif update["type"] == "wall_reply_delete":
                    uid = update["object"].get("from_id", 0)
                    post_id = update["object"].get("post_id", 0)
                    if uid and post_id:
                        if uid < 0:
                            uid = abs(uid)
                        if is_post_fresh(post_id):
                            add_points(uid, -POINTS_COMMENT)
        except Exception as e:
            log(f"⏳ LongPoll: {e}")
            time.sleep(3)

@app.route("/")
def home():
    return "Bot is running"

@app.route("/log")
def show_log():
    try:
        with open("/tmp/bot.log", "r") as f:
            return "<pre>" + f.read() + "</pre>"
    except:
        return "empty"

if __name__ == "__main__":
    log("🤖 Бот запускается (LongPoll + Баллы)...")
    get_longpoll_server()
    threading.Thread(target=longpoll_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
