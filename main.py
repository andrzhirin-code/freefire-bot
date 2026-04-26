import json
import asyncio
import aiohttp
from aiohttp import web
from config import *
from states import *
from database import get_user
from phones_db import *
from prompts import SYSTEM_PROMPT, build_user_prompt, build_correction_prompt
from keyboards import *

# Хранилище состояний
user_states = {}

# ==================== VK API ====================

async def vk_api(method, params):
    params["v"] = "5.131"
    params["access_token"] = VK_TOKEN
    async with aiohttp.ClientSession() as session:
        async with session.post(f"https://api.vk.com/method/{method}", params=params) as resp:
            return await resp.json()

async def send_message(user_id, text, keyboard=None):
    params = {
        "user_id": user_id,
        "message": text,
        "random_id": 0
    }
    if keyboard:
        params["keyboard"] = json.dumps(keyboard)
    return await vk_api("messages.send", params)

# ==================== МЕНЮ ====================

async def send_menu(user_id):
    await send_message(user_id,
        "🎮 Привет, боец!\n\n"
        "Я бот по настройкам Free Fire. Выбирай:\n\n"
        "📱 БЕСПЛАТНЫЕ НАСТРОЙКИ\n"
        "Готовые конфиги под популярные телефоны\n\n"
        "🔥 ПРЕМИУМ НАСТРОЙКА — 99₽\n"
        "ИИ подбирает лично под тебя!",
        keyboard=main_menu()
    )

# ==================== ОБРАБОТЧИК СООБЩЕНИЙ ====================

async def handle_message(user_id, text):
    user = get_user(user_id)
    state = user_states.get(user_id, MENU)
    text_lower = text.lower().strip()

    # Меню
    if text_lower in ["меню", "начать", "старт", "start"]:
        user_states[user_id] = MENU
        await send_menu(user_id)
        return

    # Помощь
    if text in ["❓ Как это работает", "помощь", "help"]:
        await send_message(user_id,
            "🤖 КАК ПОЛЬЗОВАТЬСЯ БОТОМ\n\n"
            "📱 БЕСПЛАТНО:\n"
            "1. Жми «Бесплатные настройки»\n"
            "2. Выбери марку и модель телефона\n"
            "3. Получи готовый конфиг\n\n"
            "🔥 ПРЕМИУМ (99₽):\n"
            "1. Жми «Премиум»\n"
            "2. Оплати через VK Pay\n"
            "3. Ответь на 5 вопросов\n"
            "4. ИИ выдаст ТВОИ личные настройки\n\n"
            "🔄 КОРРЕКТИРОВКА:\n"
            "• Напиши «корректировка» после получения\n"
            "• Доступно 2 бесплатные корректировки",
            keyboard=main_menu()
        )
        return

    # Бесплатные настройки
    if text == "📱 Бесплатные настройки":
        user_states[user_id] = FREE_PHONES
        await send_message(user_id, "📱 Выбери марку телефона:", keyboard=categories_menu())
        return

    # Премиум
    if text == "🔥 Премиум (99₽)":
        user_states[user_id] = AI_WAITING
        await send_message(user_id,
            f"🔥 ПРЕМИУМ НАСТРОЙКА — {PREMIUM_PRICE}₽\n\n"
            "✅ Под твой телефон\n"
            "✅ Под твой стиль игры\n"
            "✅ Под твоё оружие\n"
            "✅ 2 бесплатные корректировки\n\n"
            "👇 Жми кнопку для оплаты:",
            keyboard=premium_keyboard()
        )
        return

    # Оплата
    if text == "✅ Оплатить 99₽":
        user.premium_active = True
        user.corrections_left = MAX_CORRECTIONS
        user_states[user_id] = AI_ASK_PHONE
        await send_message(user_id,
            "✅ Оплата прошла!\n\n"
            "📱 Вопрос 1 из 5:\n"
            "Напиши точную модель телефона.\n"
            "Например: Redmi Note 10, iPhone 11",
            keyboard=back_button()
        )
        return

    # Категории телефонов
    categories = {
        "📱 Xiaomi (Redmi/Poco)": CATEGORIES["📱 Xiaomi (Redmi/Poco)"],
        "📱 Samsung": CATEGORIES["📱 Samsung"],
        "📱 iPhone": CATEGORIES["📱 iPhone"],
        "📱 Realme": CATEGORIES["📱 Realme"],
        "📱 Tecno/Infinix": CATEGORIES["📱 Tecno/Infinix"],
        "📱 Другие": CATEGORIES["📱 Другие"],
    }

    if text in categories:
        kb = {"one_time": False, "buttons": []}
        for phone in categories[text]:
            kb["buttons"].append([{"action": {"type": "text", "label": phone.title(), "payload": "phone"}, "color": "primary"}])
        kb["buttons"].append([{"action": {"type": "text", "label": "⬅ Назад", "payload": "back"}, "color": "secondary"}])
        await send_message(user_id, "📱 Выбери модель:", keyboard=kb)
        return

    # Назад
    if text in ["⬅ Назад", "⬅ Назад в меню", "🏠 В меню"]:
        user_states[user_id] = MENU
        await send_menu(user_id)
        return

    # Поиск телефона
    phone = find_phone(text)
    if phone:
        config = get_config(phone)
        if config:
            await send_message(user_id, config, keyboard=done_keyboard())
            return

    # ИИ опрос
    if state == AI_ASK_PHONE and user.premium_active:
        user.phone = text
        user_states[user_id] = AI_ASK_RAM
        await send_message(user_id, "📱 Вопрос 2 из 5:\nСколько ОЗУ?\n• 2-3 ГБ\n• 4-6 ГБ\n• 8+ ГБ\n• Не знаю", keyboard=back_button())
        return

    if state == AI_ASK_RAM:
        user.ram = text
        user_states[user_id] = AI_ASK_STYLE
        await send_message(user_id, "🎮 Вопрос 3 из 5:\nСтиль игры?\n• Агрессивный\n• Пассивный\n• Смешанный", keyboard=back_button())
        return

    if state == AI_ASK_STYLE:
        user.style = text
        user_states[user_id] = AI_ASK_WEAPON
        await send_message(user_id, "🔫 Вопрос 4 из 5:\nОружие?\nНапример: M4A1, AK47, SCAR", keyboard=back_button())
        return

    if state == AI_ASK_WEAPON:
        user.weapon = text
        user_states[user_id] = AI_ASK_FINGERS
        await send_message(user_id, "🤟 Вопрос 5 из 5:\nСколько пальцев?\n• 2\n• 4\n• 6", keyboard=back_button())
        return

    if state == AI_ASK_FINGERS:
        user.fingers = text
        user_states[user_id] = AI_DONE

        if DEEPSEEK_API_KEY:
            await send_message(user_id, "🤖 ИИ подбирает настройки... 5-10 секунд.")
            prompt = build_user_prompt(user)
            # Заглушка — здесь будет DeepSeek API
            await send_message(user_id,
                f"🎯 ТВОЯ ПЕРСОНАЛЬНАЯ ОТТЯЖКА\n\n"
                f"📱 {user.phone} | {user.ram}\n"
                f"🔫 {user.weapon} | 🎮 {user.style} | 🤟 {user.fingers}\n\n"
                f"⚙️ ИИ-подбор временно недоступен.\n"
                f"Вот базовая настройка под твой телефон:",
                keyboard=done_keyboard()
            )
        else:
            phone = find_phone(user.phone)
            if phone:
                config = get_config(phone)
                await send_message(user_id, config, keyboard=done_keyboard())
            else:
                await send_message(user_id, "❌ Модель не найдена.", keyboard=main_menu())
        return

    # Корректировка
    if "корректировка" in text_lower:
        if state in [AI_DONE, CORRECTION]:
            if user.corrections_left > 0:
                user_states[user_id] = CORRECTION
                await send_message(user_id, f"🔄 РЕЖИМ КОРРЕКТИРОВКИ\n\nНапиши что исправить.\nОсталось: {user.corrections_left}", keyboard=back_button())
            else:
                await send_message(user_id, "❌ Лимит корректировок исчерпан.", keyboard=main_menu())
        return

    if state == CORRECTION:
        user.corrections_left -= 1
        await send_message(user_id, f"✅ Корректировка принята! Осталось: {user.corrections_left}", keyboard=done_keyboard())
        user_states[user_id] = AI_DONE
        return

    # Админ-панель
    if text in ["/stat", "/admin"] and user_id == ADMIN_ID:
        await send_message(user_id,
            f"📊 СТАТИСТИКА\n\n"
            f"👥 Пользователей: {len(user_states)}\n"
            f"📱 Моделей в базе: {len(PHONES)}\n"
            f"🖥 Сервер: Online"
        )
        return

    # Дефолт
    await send_message(user_id, "❌ Я отвечаю только по настройкам Free Fire.\nНапиши «меню».", keyboard=main_menu())

# ==================== CALLBACK СЕРВЕР ====================

async def callback_handler(request):
    body = await request.json()
    if body.get("type") == "confirmation":
        return web.Response(text=CONFIRMATION_CODE)
    if body.get("secret") and body.get("secret") != SECRET_KEY:
        return web.Response(text="ok")
    
    obj = body.get("object", {})
    msg = obj.get("message", {})
    user_id = msg.get("from_id")
    text = msg.get("text", "")
    
    if user_id and text:
        asyncio.create_task(handle_message(user_id, text))
    
    return web.Response(text="ok")

async def main():
    app = web.Application()
    app.router.add_post("/callback", callback_handler)
    print("=" * 40)
    print("🎮 Free Fire Settings Bot")
    print("📡 Callback API mode")
    print(f"🔗 Порт: {PORT}")
    print("=" * 40)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    print("✅ Сервер запущен. Ожидание запросов...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
