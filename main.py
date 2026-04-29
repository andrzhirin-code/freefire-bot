import json
import threading
from flask import Flask, request
import requests
from config import *
from states import *
from database import get_user
from phones_db import *

app = Flask(__name__)
user_states = {}
last_category = {}

def log(msg):
    with open("/tmp/bot.log", "a") as f:
        f.write(f"[{__import__('datetime').datetime.now().strftime('%H:%M:%S')}] {msg}\n")

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
            [{"action": {"type": "open_link", "label": "🛒 МАГАЗИН", "link": "https://vk.com/market-193012947"}, "color": "positive"}],
        ]
    }
    send_message(user_id, "🎮 Привет, боец!\n\nЯ бот по настройкам Free Fire.\n\n📱 Бесплатные настройки — готовые конфиги\n🔥 Премиум — ИИ подбирает лично под тебя за 99₽\n🛒 Магазин — зайди посмотри", keyboard=kb)

@app.route("/callback", methods=["POST"])
def callback():
    body = request.get_json()
    log(f"📥 {body.get('type')}")

    if body.get("type") == "confirmation":
        return CONFIRMATION_CODE

    if body.get("type") == "message_new":
        obj = body.get("object", {})
        msg = obj.get("message", {})
        user_id = msg.get("from_id")
        text = msg.get("text", "")
        if user_id and user_id < 0:
            user_id = abs(user_id)
        if user_id and text:
            threading.Thread(target=handle_message, args=(user_id, text)).start()
    return "ok"

@app.route("/log")
def show_log():
    try:
        with open("/tmp/bot.log", "r") as f:
            return "<pre>" + f.read() + "</pre>"
    except:
        return "empty"

def back_and_menu_kb():
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "← Назад"}, "color": "secondary"},
             {"action": {"type": "text", "label": "🏠 В меню"}, "color": "secondary"}],
        ]
    }

def after_config_kb():
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "🔥 Хочу премиум"}, "color": "positive"}],
            [{"action": {"type": "text", "label": "← Назад"}, "color": "secondary"},
             {"action": {"type": "text", "label": "🏠 В меню"}, "color": "secondary"}],
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
        for i, phone in enumerate(phones, 1):
            row.append({"action": {"type": "text", "label": f"{i}. {phone.title()}"}, "color": "primary"})
            if len(row) == 2:
                kb["buttons"].append(row)
                row = []
        if row:
            kb["buttons"].append(row)
        kb["buttons"].append([{"action": {"type": "text", "label": "← Назад"}, "color": "secondary"},
                              {"action": {"type": "text", "label": "🏠 В меню"}, "color": "secondary"}])
        send_message(user_id, "📱 Выбери модель (напиши номер или название):", keyboard=kb)
        return

    if t in ["← Назад", "🏠 В меню"]:
        user_states[user_id] = "MENU"
        send_menu(user_id)
        return

    # Выбор по номеру
    if t.split(".")[0].isdigit():
        num = int(t.split(".")[0])
        cat = last_category.get(user_id, [])
        if 1 <= num <= len(cat):
            phone = cat[num - 1]
            config = get_config(phone)
            if config:
                send_message(user_id, config, keyboard=after_config_kb())
                return

    # Прямой поиск
    phone = find_phone(t)
    if phone:
        config = get_config(phone)
        if config:
            send_message(user_id, config, keyboard=after_config_kb())
            return

    # ИИ опрос
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
        send_message(user_id, "🎯 Готово! ИИ подбирает настройки...\n(ИИ пока в разработке)", keyboard=after_config_kb())
        return

    if "корректировка" in t.lower():
        send_message(user_id, "🔄 Корректировка пока в разработке", keyboard=back_and_menu_kb())
        return

    if t in ["/stat", "/admin"] and user_id == ADMIN_ID:
        send_message(user_id, f"📊 СТАТИСТИКА\n👥 Пользователей: {len(user_states)}\n📱 Моделей: {len(PHONES)}")
        return

    send_message(user_id, "❌ Я отвечаю только по настройкам Free Fire.\nНапиши «меню».", keyboard=back_and_menu_kb())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
