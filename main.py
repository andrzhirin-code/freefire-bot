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
user_pages = {}
longpoll_server = None
longpoll_key = None
longpoll_ts = None

POINTS_FILE = "/opt/render/project/src/points.json"
POINTS_BACKUP = "/opt/render/project/src/points_backup.json"

POINTS_LIKE = 4
POINTS_COMMENT = 8
POINTS_PREMIUM = 800
POINTS_REFERRER = 40
POINTS_REFERRAL = 20
POINTS_EXPIRE_DAYS = 30
MAX_LIKES_PER_DAY = 10
MAX_COMMENTS_PER_DAY = 5

PAGE_SIZE = 6

points_data = {}
points_lock = threading.Lock()
points_changed = False

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

def jsonbin_load():
    try:
        r = requests.get(
            f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}/latest",
            headers={"X-Master-Key": JSONBIN_KEY},
            timeout=10
        )
        if r.status_code == 200:
            data = r.json().get("record", {})
            if data and len(data) > 0:
                return data
    except:
        pass
    return None

def jsonbin_save(data):
    if not data or len(data) == 0:
        return
    try:
        requests.put(
            f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}",
            headers={"X-Master-Key": JSONBIN_KEY, "Content-Type": "application/json"},
            json=data, timeout=10
        )
    except:
        pass

def load_points():
    global points_data
    cloud = jsonbin_load()
    local = load_json(POINTS_FILE, {})
    backup = load_json(POINTS_BACKUP, {})

    if cloud and len(cloud) > 0:
        points_data = cloud
    elif local and len(local) > 0:
        points_data = local
    elif backup and len(backup) > 0:
        points_data = backup
    else:
        points_data = {}

    if local and len(local) > 0:
        merged = 0
        for uid, ldata in local.items():
            if uid in points_data:
                if ldata.get("points", 0) > points_data[uid].get("points", 0):
                    points_data[uid] = ldata
                    merged += 1
            else:
                points_data[uid] = ldata
                merged += 1
        if merged:
            log(f"📂 Объединено: {merged}")
    save_json(POINTS_FILE, points_data)
    save_json(POINTS_BACKUP, points_data)
    log(f"📂 Загружено: {len(points_data)} пользователей")

def save_points(data):
    global points_data, points_changed
    if not data or len(data) == 0:
        return
    with points_lock:
        points_data = data
        save_json(POINTS_FILE, data)
        save_json(POINTS_BACKUP, data)
        points_changed = True

def get_user_points(uid):
    key = str(uid)
    if key not in points_data:
        points_data[key] = {
            "points": 0,
            "corrections_left": MAX_CORRECTIONS,
            "last_active": datetime.now().isoformat(),
            "likes_today": 0,
            "comments_today": 0,
            "day": datetime.now().strftime("%Y-%m-%d"),
            "invited_by": None
        }
        save_points(points_data)
    else:
        today = datetime.now().strftime("%Y-%m-%d")
        if points_data[key].get("day") != today:
            points_data[key]["likes_today"] = 0
            points_data[key]["comments_today"] = 0
            points_data[key]["day"] = today
            save_points(points_data)
    return points_data, key

def add_points(uid, amount, action_type=None):
    data, key = get_user_points(uid)
    today = datetime.now().strftime("%Y-%m-%d")
    if data[key].get("day") != today:
        data[key]["likes_today"] = 0
        data[key]["comments_today"] = 0
        data[key]["day"] = today
    if action_type == "like" and data[key]["likes_today"] >= MAX_LIKES_PER_DAY:
        return False
    if action_type == "comment" and data[key]["comments_today"] >= MAX_COMMENTS_PER_DAY:
        return False
    data[key]["points"] = max(0, data[key]["points"] + amount)
    data[key]["last_active"] = datetime.now().isoformat()
    if action_type == "like":
        data[key]["likes_today"] += 1
    elif action_type == "comment":
        data[key]["comments_today"] += 1
    save_points(data)
    log(f"⭐ {'+' if amount > 0 else ''}{amount} баллов пользователю {uid} (всего: {data[key]['points']}) [{action_type}]")
    return True

def check_points_expiry(uid):
    data, key = get_user_points(uid)
    last = data[key].get("last_active")
    if last:
        if datetime.now() - datetime.fromisoformat(last) > timedelta(days=POINTS_EXPIRE_DAYS):
            data[key]["points"] = 0
            data[key]["corrections_left"] = MAX_CORRECTIONS
            data[key]["last_active"] = datetime.now().isoformat()
            save_points(data)
            return True
    return False

def sync_worker():
    global points_changed
    while True:
        time.sleep(300)
        if points_changed:
            with points_lock:
                if points_data and len(points_data) > 0:
                    data = points_data.copy()
                    jsonbin_save(data)
            points_changed = False

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

def back_to_question_kb():
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "↩ Вернуться к вопросу"}, "color": "secondary"}],
        ]
    }

def premium_inline_kb():
    return {
        "inline": True,
        "buttons": [
            [{"action": {"type": "callback", "label": "🔥 ПРЕМИУМ НАСТРОЙКА — 99₽", "payload": "{\"cmd\":\"premium\"}"}, "color": "positive"}]
        ]
    }

def premium_choice_kb():
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "💳 За 99₽"}, "color": "positive"},
             {"action": {"type": "text", "label": "⭐ За 800 баллов"}, "color": "positive"}],
            [{"action": {"type": "text", "label": "🏠 В меню"}, "color": "secondary"}],
        ]
    }

def call_deepseek(prompt):
    if not DEEPSEEK_API_KEY:
        return "❌ ИИ не настроен."
    try:
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        data = {"model": "deepseek-chat", "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 1500}
        resp = requests.post("https://api.proxyapi.ru/deepseek/chat/completions", headers=headers, json=data, timeout=30)
        result = resp.json()
        if "choices" in result:
            return result["choices"][0]["message"]["content"]
        else:
            return "❌ Ошибка ИИ."
    except:
        return "❌ Ошибка ИИ."

def handle_message(user_id, text, ref=None):
    log(f"💬 user={user_id} text={text}")
    user = get_user(user_id)
    state = user_states.get(user_id, "MENU")
    t = text.strip()

    # Проверка реферала (первое сообщение)
    if ref and str(ref).isdigit():
        ref_id = int(ref)
        data, key = get_user_points(user_id)
        if ref_id != user_id and not data[key].get("invited_by"):
            data[key]["invited_by"] = ref_id
            save_points(data)
            add_points(ref_id, POINTS_REFERRER, "referral")
            add_points(user_id, POINTS_REFERRAL, "referral_bonus")
            send_message(user_id, f"🎉 Ты пришёл по реферальной ссылке!\n+{POINTS_REFERRAL} баллов тебе, +{POINTS_REFERRER} баллов другу!")

    # Защита от выхода из премиум-опроса
    if state and state.startswith("AI_") and t.lower() in ["меню", "начать", "старт", "start", "отмена"]:
        if t.lower() == "отмена":
            data, key = get_user_points(user_id)
            data[key]["points"] += POINTS_PREMIUM
            data[key]["corrections_left"] = 0
            save_points(data)
            user_states[user_id] = "MENU"
            send_message(user_id, f"❌ Премиум-опрос отменён. {POINTS_PREMIUM} баллов возвращены.", keyboard=send_menu_keyboard())
            send_menu(user_id)
        else:
            send_message(user_id, "⚠️ Ты не завершил премиум-опрос! Пройди все 7 вопросов или напиши «отмена» чтобы выйти и вернуть баллы.", keyboard=back_to_question_kb())
        return

    if t.lower() in ["меню", "начать", "старт", "start"]:
        user_states[user_id] = "MENU"
        user_pages.pop(user_id, None)
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
                [{"action": {"type": "text", "label": "🔗 Моя реферальная ссылка"}, "color": "primary"}],
                [{"action": {"type": "text", "label": "← Назад в меню 🏠"}, "color": "secondary"}],
            ]
        }
        info = (
            f"🚀 Как заработать баллы:\n"
            f"❤ Лайкай записи — +{POINTS_LIKE} балла за лайк (до {MAX_LIKES_PER_DAY} лайков в день)\n"
            f"💬 Пиши комменты — +{POINTS_COMMENT} баллов за коммент (до {MAX_COMMENTS_PER_DAY} комментариев в день)\n"
            f"🔗 Приглашай друзей по ссылке — +{POINTS_REFERRER} баллов тебе за каждого друга и +{POINTS_REFERRAL} баллов каждому другу\n\n"
        )
        if expired:
            send_message(user_id, f"⌛ Баллы сгорели.\n\n⭐ Сейчас: 0 баллов\n\n{info}", keyboard=kb)
        else:
            send_message(user_id, f"⭐ ТВОИ БАЛЛЫ: {pts}\n🔥 Набери {POINTS_PREMIUM} и обменяй на 🔥 Премиум Настройку!\n📊 Не хватает: {need}\n\n{info}", keyboard=kb)
        return

    if t == "🔗 Моя реферальная ссылка":
        send_message(user_id,
            f"🔗 Твоя реферальная ссылка:\n\n"
            f"👉 https://vk.com/write-{GROUP_ID}?ref={user_id}\n\n"
            f"Отправь её другу! Когда он впервые напишет боту:\n"
            f"✅ Ты получишь +{POINTS_REFERRER} баллов\n"
            f"✅ Друг получит +{POINTS_REFERRAL} баллов\n\n"
            f"📌 Ссылка работает только для новых пользователей!",
            keyboard=None)
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
        send_message(user_id, "📱 Выбери марку телефона:", keyboard=kb)
        return

    if t in ["🔥 ПРЕМИУМ НАСТРОЙКА — 99₽", "🔥 Хочу премиум"]:
        send_message(user_id,
            "🔥 ПРЕМИУМ НАСТРОЙКА\n\n"
            "Что ты получишь:\n"
            "✅ Персональные настройки под твой телефон\n"
            "✅ Чувствительность под твой стиль игры\n"
            "✅ HUD под твои пальцы и размер экрана\n"
            "✅ Советы по тренировке под твоё оружие\n"
            "✅ Рекомендации по охлаждению телефона\n"
            "✅ 2 бесплатные корректировки\n\n"
            "🎯 Не шаблон — ИИ подбирает лично под тебя!\n\n"
            "👇 Выбери способ:",
            keyboard=premium_choice_kb())
        return

    if t == "💳 За 99₽":
        send_message(user_id, "💳 Оплата пока в разработке.\n\n⭐ Ты можешь получить премиум за 800 баллов — активничай в паблике!", keyboard=premium_choice_kb())
        return

    if t == "⭐ За 800 баллов":
        data, key = get_user_points(user_id)
        check_points_expiry(user_id)
        pts = data[key]["points"]
        if pts >= POINTS_PREMIUM:
            data[key]["points"] -= POINTS_PREMIUM
            data[key]["corrections_left"] = MAX_CORRECTIONS
            save_points(data)
            user_states[user_id] = "AI_ASK_PHONE"
            send_message(user_id, f"✅ Премиум активирован за {POINTS_PREMIUM} баллов!\nОсталось: {data[key]['points']}\n\n📱 Вопрос 1 из 7:\nНапиши модель телефона.", keyboard=back_to_question_kb())
        else:
            send_message(user_id, f"❌ Не хватает баллов.\nУ тебя: {pts}\nНужно: {POINTS_PREMIUM}", keyboard=premium_choice_kb())
        return

    if t == "🔥 Обменять баллы":
        data, key = get_user_points(user_id)
        check_points_expiry(user_id)
        pts = data[key]["points"]
        if pts >= POINTS_PREMIUM:
            data[key]["points"] -= POINTS_PREMIUM
            data[key]["corrections_left"] = MAX_CORRECTIONS
            save_points(data)
            user_states[user_id] = "AI_ASK_PHONE"
            send_message(user_id, f"✅ Премиум активирован за {POINTS_PREMIUM} баллов!\nОсталось: {data[key]['points']}\n\n📱 Вопрос 1 из 7:\nНапиши модель телефона.", keyboard=back_to_question_kb())
        else:
            need = POINTS_PREMIUM - pts
            send_message(user_id, f"❌ Не хватает баллов.\nУ тебя: {pts}\nНужно: {POINTS_PREMIUM}\nНе хватает: {need}")
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
        user_pages[user_id] = {"phones": phones, "page": 0}
        show_models_page(user_id)
        return

    if t == "Вперёд →":
        show_models_page(user_id, 1)
        return
    if t == "← Назад":
        data = user_pages.get(user_id)
        if data:
            show_models_page(user_id, -1)
        else:
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

    if t == "📱 Нет моей модели":
        send_message(user_id,
            "📱 Не нашёл свою модель?\n\n"
            "Напиши её в нашем обсуждении:\n"
            "👉 https://vk.com/topic-193012947_12345678\n\n"
            "Мы добавим её в бота! 🔧\n\n"
            "А пока можешь получить персональную настройку через 🔥 Премиум — ИИ подберёт под любой телефон!",
            keyboard=back_and_menu_kb())
        return

    if t in ["🏠 В меню"]:
        user_states[user_id] = "MENU"
        user_pages.pop(user_id, None)
        send_menu(user_id)
        return

    phone = find_phone(t)
    if phone:
        config = get_config(phone)
        if config:
            send_message(user_id, config, keyboard=premium_inline_kb())
            return

    if state == "AI_ASK_PHONE":
        user.phone = t; user_states[user_id] = "AI_ASK_RAM"
        send_message(user_id, "📱 Вопрос 2 из 7:\nСколько ОЗУ?", keyboard=back_to_question_kb())
        return
    if state == "AI_ASK_RAM":
        user.ram = t; user_states[user_id] = "AI_ASK_STYLE"
        send_message(user_id, "🎮 Вопрос 3 из 7:\nСтиль игры?", keyboard=back_to_question_kb())
        return
    if state == "AI_ASK_STYLE":
        user.style = t; user_states[user_id] = "AI_ASK_WEAPON"
        send_message(user_id, "🔫 Вопрос 4 из 7:\nОружие?", keyboard=back_to_question_kb())
        return
    if state == "AI_ASK_WEAPON":
        user.weapon = t; user_states[user_id] = "AI_ASK_FINGERS"
        send_message(user_id, "🤟 Вопрос 5 из 7:\nСколько пальцев?", keyboard=back_to_question_kb())
        return
    if state == "AI_ASK_FINGERS":
        user.fingers = t; user_states[user_id] = "AI_ASK_GYRO"
        send_message(user_id, "📳 Вопрос 6 из 7:\nГироскоп?", keyboard=back_to_question_kb())
        return
    if state == "AI_ASK_GYRO":
        user.gyro = t; user_states[user_id] = "AI_ASK_PROBLEM"
        send_message(user_id, "🔧 Вопрос 7 из 7:\nПроблема?", keyboard=back_to_question_kb())
        return
    if state == "AI_ASK_PROBLEM":
        user.problem = t if t.lower() != "нет" else ""
        user_states[user_id] = "AI_DONE"
        data, key = get_user_points(user_id)
        send_message(user_id, "🤖 ИИ подбирает настройки...")
        prompt = build_user_prompt(user)
        response = call_deepseek(prompt)
        send_message(user_id, response + f"\n\n🔄 Корректировок осталось: {data[key]['corrections_left']}")
        return

    if "корректировка" in t.lower():
        data, key = get_user_points(user_id)
        corr = data[key].get("corrections_left", 0)
        if state == "AI_DONE" and corr > 0:
            user_states[user_id] = "CORRECTION"
            send_message(user_id, f"🔄 Опиши проблему.\nОсталось: {corr}", keyboard=back_and_menu_kb())
            return
        elif state == "CORRECTION" and corr > 0:
            data[key]["corrections_left"] = corr - 1
            save_points(data)
            send_message(user_id, "🤖 ИИ пересчитывает...")
            prompt = build_correction_prompt(user, t)
            response = call_deepseek(prompt)
            user_states[user_id] = "AI_DONE"
            send_message(user_id, response + f"\n\n🔄 Осталось: {data[key]['corrections_left']}")
            return
        else:
            send_message(user_id, "❌ Лимит исчерпан.", keyboard=back_and_menu_kb())
            return

    if t in ["/stat", "/admin"] and user_id == ADMIN_ID:
        with points_lock:
            total = len(points_data)
            top = sorted(points_data.items(), key=lambda x: x[1]["points"], reverse=True)[:10]
        top_str = "\n".join([f"{i+1}. ID {k}: {v['points']} баллов" for i, (k, v) in enumerate(top)])
        send_message(user_id, f"📊 СТАТИСТИКА\n👥 Пользователей: {total}\n📱 Моделей: {len(PHONES)}\n\n🏆 Топ-10:\n{top_str}")
        return

    send_message(user_id, "❌ Я отвечаю только по настройкам Free Fire.\nНапиши «меню».")


def show_models_page(user_id, direction=0):
    data = user_pages.get(user_id)
    if not data:
        return
    phones = data["phones"]
    page = data["page"] + direction
    if page < 0:
        page = 0
    total_pages = (len(phones) - 1) // PAGE_SIZE
    if page > total_pages:
        page = total_pages
    data["page"] = page
    user_pages[user_id] = data

    start = page * PAGE_SIZE
    end = start + PAGE_SIZE
    page_phones = phones[start:end]

    kb = {"one_time": False, "buttons": []}
    row = []
    for phone in page_phones:
        row.append({"action": {"type": "text", "label": phone.title()}, "color": "primary"})
        if len(row) == 2:
            kb["buttons"].append(row)
            row = []
    if row:
        kb["buttons"].append(row)

    if page == total_pages:
        kb["buttons"].append([{"action": {"type": "text", "label": "📱 Нет моей модели"}, "color": "negative"}])

    nav_row = [{"action": {"type": "text", "label": "← Назад"}, "color": "secondary"},
               {"action": {"type": "text", "label": "🏠 В меню"}, "color": "secondary"}]
    if page < total_pages:
        nav_row.insert(1, {"action": {"type": "text", "label": "Вперёд →"}, "color": "primary"})
    kb["buttons"].append(nav_row)

    send_message(user_id, f"📱 Выбери модель (стр. {page+1}/{total_pages+1}):", keyboard=kb)


def get_longpoll_server():
    global longpoll_server, longpoll_key, longpoll_ts
    resp = vk_api("groups.getLongPollServer", {"group_id": GROUP_ID})
    if "response" in resp:
        longpoll_server = resp["response"]["server"]
        longpoll_key = resp["response"]["key"]
        longpoll_ts = resp["response"]["ts"]
        log(f"🔗 LongPoll подключён")

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
                    ref = msg.get("ref")
                    if uid and uid < 0: uid = abs(uid)
                    if uid and txt:
                        threading.Thread(target=handle_message, args=(uid, txt, ref)).start()
                elif update["type"] == "message_event":
                    obj = update["object"]
                    uid = obj.get("user_id")
                    payload = obj.get("payload", {})
                    if isinstance(payload, str): payload = json.loads(payload)
                    vk_api("messages.sendMessageEventAnswer", {"event_id": obj.get("event_id"), "user_id": uid, "peer_id": obj.get("peer_id")})
                    if payload.get("cmd") == "premium":
                        threading.Thread(target=handle_message, args=(uid, "🔥 Хочу премиум", None)).start()
                elif update["type"] == "like_add":
                    uid = update["object"].get("liker_id", 0)
                    if uid:
                        if uid < 0: uid = abs(uid)
                        add_points(uid, POINTS_LIKE, "like")
                elif update["type"] == "like_remove":
                    pass
                elif update["type"] == "wall_reply_new":
                    uid = update["object"].get("from_id", 0)
                    if uid:
                        if uid < 0: uid = abs(uid)
                        add_points(uid, POINTS_COMMENT, "comment")
                elif update["type"] == "wall_reply_delete":
                    pass
        except:
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

if __name__ == "__main__":
    log("🤖 Бот запускается...")
    load_points()
    get_longpoll_server()
    threading.Thread(target=longpoll_loop, daemon=True).start()
    threading.Thread(target=keep_alive, daemon=True).start()
    threading.Thread(target=sync_worker, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
