import json
import threading
from datetime import datetime
import requests
import time
from config import *
from states import *
from database import get_user
from phones_db import *

user_states = {}
last_category = {}
longpoll_server = None
longpoll_key = None
longpoll_ts = None

def log(msg):
    with open("/tmp/bot.log", "a") as f:
        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")

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
            [{"action": {"type": "open_link", "label": "🛒 МАГАЗИН", "link": "https://vk.com/market-193012947"}}],
        ]
    }
    send_message(user_id, "🎮 Привет, боец!\n\nЯ бот по настройкам Free Fire.\n\n📱 Бесплатные настройки — готовые конфиги\n🔥 Премиум — ИИ подбирает лично под тебя за 99₽\n🛒 Магазин — перейти в магазин", keyboard=kb)

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

    if t in ["🔥 ПРЕМИУМ НАСТРОЙКА — 99₽", "🔥 Хочу премиум"]:
        user.premium_active = True
        user.corrections_left = MAX_CORRECTIONS
        user_states[user_id] = "AI_ASK_PHONE"
        send_message(user_id, "✅ Премиум активирован!\n\n📱 Вопрос 1 из 5:\nНапиши точную модель телефона.\nНапример: Redmi Note 10, iPhone 11", keyboard=back_and_menu_kb())
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
        send_message(user_id, "📱 Вопрос 2 из 5:\nСколько ОЗУ?", keyboard=back_and_menu_kb())
        return
    if state == "AI_ASK_RAM":
        user.ram = t
        user_states[user_id] = "AI_ASK_STYLE"
        send_message(user_id, "🎮 Вопрос 3 из 5:\nСтиль игры?", keyboard=back_and_menu_kb())
        return
    if state == "AI_ASK_STYLE":
        user.style = t
        user_states[user_id] = "AI_ASK_WEAPON"
        send_message(user_id, "🔫 Вопрос 4 из 5:\nОружие?", keyboard=back_and_menu_kb())
        return
    if state == "AI_ASK_WEAPON":
        user.weapon = t
        user_states[user_id] = "AI_ASK_FINGERS"
        send_message(user_id, "🤟 Вопрос 5 из 5:\nСколько пальцев?", keyboard=back_and_menu_kb())
        return
    if state == "AI_ASK_FINGERS":
        user.fingers = t
        user_states[user_id] = "AI_DONE"
        send_message(user_id, "🎯 Готово! ИИ подбирает настройки...")
        return

    if "корректировка" in t.lower():
        send_message(user_id, "🔄 Корректировка пока в разработке", keyboard=back_and_menu_kb())
        return

    if t in ["/stat", "/admin"] and user_id == ADMIN_ID:
        send_message(user_id, f"📊 СТАТИСТИКА\n👥 Пользователей: {len(user_states)}\n📱 Моделей: {len(PHONES)}")
        return

    send_message(user_id, "❌ Я отвечаю только по настройкам Free Fire.\nНапиши «меню».", keyboard=back_and_menu_kb())

def get_longpoll_server():
    global longpoll_server, longpoll_key, longpoll_ts
    resp = vk_api("groups.getLongPollServer", {"group_id": GROUP_ID})
    if "response" in resp:
        longpoll_server = resp["response"]["server"]
        longpoll_key = resp["response"]["key"]
        longpoll_ts = resp["response"]["ts"]
        log(f"🔗 LongPoll подключён: {longpoll_server}")

def longpoll_loop():
    global longpoll_ts
    while True:
        try:
            if not longpoll_server:
                get_longpoll_server()
            url = f"{longpoll_server}?act=a_check&key={longpoll_key}&ts={longpoll_ts}&wait=25"
            resp = requests.get(url, timeout=30).json()
            if "failed" in resp:
                log(f"🔄 LongPoll переподключение: {resp['failed']}")
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
                    payload = obj.get("payload", {})
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    cmd = payload.get("cmd", "")
                    log(f"🖲 message_event: user={user_id} cmd={cmd}")
                    if cmd == "premium":
                        threading.Thread(target=handle_message, args=(user_id, "🔥 ПРЕМИУМ НАСТРОЙКА — 99₽")).start()
        except Exception as e:
            log(f"⏳ Ошибка LongPoll: {e}")
            time.sleep(3)

if __name__ == "__main__":
    print("=" * 40)
    print("🎮 Free Fire Settings Bot")
    print("📡 LongPoll API mode")
    print("=" * 40)
    log("🤖 Бот запускается (LongPoll)...")
    get_longpoll_server()
    threading.Thread(target=longpoll_loop, daemon=True).start()
    # Держим главный поток
    while True:
        time.sleep(60)
