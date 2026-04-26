# main.py
# Free Fire Settings Bot — Главный Файл
# Версия 1.0.0

import asyncio
import re
from vkbottle import Bot, Keyboard, Text
from vkbottle.bot import Message, rules
from config import *
from states import *
from database import get_user, reset_user
from phones_db import *
from prompts import SYSTEM_PROMPT, build_user_prompt, build_correction_prompt
from keyboards import *
import aiohttp

# Инициализация бота
bot = Bot(token=VK_TOKEN)

# ============================================================
# 🔧 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================

async def call_deepseek(prompt):
    """Запрос к DeepSeek API"""
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
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers=headers,
                json=data
            ) as response:
                result = await response.json()
                return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"❌ Ошибка ИИ. Попробуй позже.\n(Код ошибки: {str(e)[:100]})"

def is_paid(user_id):
    """Проверка оплаты (заглушка — в реальности проверка через VK Pay API)"""
    # TODO: Интеграция с VK Pay Callback API
    # Пока считаем что PREMIUM_ACTIVE проверяется через базу
    user = get_user(user_id)
    return user.premium_active

async def send_menu(message: Message):
    """Отправка главного меню"""
    await message.answer(
        "🎮 Привет, боец!\n\n"
        "Я бот по настройкам Free Fire. Выбирай:\n\n"
        "📱 БЕСПЛАТНЫЕ НАСТРОЙКИ\n"
        "Готовые конфиги под популярные телефоны\n\n"
        "🔥 ПРЕМИУМ НАСТРОЙКА — 99₽\n"
        "ИИ подбирает лично под тебя!\n"
        "• Под твой телефон\n"
        "• Под твой стиль игры\n"
        "• Под твои проблемы\n\n"
        "👇 Жми на кнопку внизу!",
        keyboard=main_menu()
    )

# ============================================================
# 📩 ОБРАБОТЧИКИ КОМАНД
# ============================================================

@bot.on.message(text=["меню", "Меню", "начать", "старт", "start"])
async def menu_command(message: Message):
    user = get_user(message.from_id)
    user.state = MENU
    await send_menu(message)

@bot.on.message(text=["❓ Как это работает", "помощь", "help"])
async def help_command(message: Message):
    await message.answer(
        "🤖 КАК ПОЛЬЗОВАТЬСЯ БОТОМ\n\n"
        "📱 БЕСПЛАТНО:\n"
        "1. Жми «Бесплатные настройки»\n"
        "2. Выбери марку телефона\n"
        "3. Выбери модель\n"
        "4. Получи готовый конфиг\n\n"
        "🔥 ПРЕМИУМ (99₽):\n"
        "1. Жми «Премиум»\n"
        "2. Оплати 99₽ через VK Pay\n"
        "3. Ответь на 5 вопросов\n"
        "4. ИИ выдаст ТВОИ личные настройки\n\n"
        "🔄 КОРРЕКТИРОВКА:\n"
        "• После получения настроек напиши «корректировка»\n"
        "• Доступно 2 бесплатные корректировки\n"
        "• Потом жди 14 дней\n\n"
        "Понял? Жми кнопку и погнали! 🚀",
        keyboard=main_menu()
    )

@bot.on.message(text=["📱 Бесплатные настройки"])
async def free_settings(message: Message):
    user = get_user(message.from_id)
    user.state = FREE_PHONES
    await message.answer(
        "📱 Выбери марку телефона:",
        keyboard=categories_menu()
    )

@bot.on.message(text=["🔥 Премиум (99₽)"])
async def premium_start(message: Message):
    user = get_user(message.from_id)
    user.state = AI_WAITING
    await message.answer(
        f"🔥 ПРЕМИУМ НАСТРОЙКА — {PREMIUM_PRICE}₽\n\n"
        "Что ты получишь:\n"
        "✅ Настройки под твой телефон\n"
        "✅ Под твой стиль игры\n"
        "✅ Под твоё оружие\n"
        "✅ Решение твоих проблем\n"
        "✅ 2 бесплатные корректировки\n\n"
        "Оплата через VK Pay — безопасно и мгновенно!\n\n"
        "👇 Жми кнопку для оплаты:",
        keyboard=premium_keyboard()
    )

@bot.on.message(text=["✅ Оплатить 99₽"])
async def pay_command(message: Message):
    user = get_user(message.from_id)
    # Заглушка — считаем что оплата прошла
    # В реальности: интеграция с VK Pay API
    user.premium_active = True
    user.state = AI_ASK_PHONE
    user.corrections_left = MAX_CORRECTIONS
    await message.answer(
        "✅ Оплата прошла!\n\n"
        "Сейчас ИИ подберёт настройки под тебя.\n\n"
        "📱 Вопрос 1 из 6:\n"
        "Напиши точную модель телефона.\n"
        "Например: Redmi Note 10, iPhone 11, Samsung A54\n\n"
        "⚠️ Пиши точную модель, от этого зависит результат!",
        keyboard=back_button()
    )

# ============================================================
# 📱 ОБРАБОТКА КАТЕГОРИЙ ТЕЛЕФОНОВ
# ============================================================

@bot.on.message(text=["📱 Xiaomi (Redmi/Poco)"])
async def cat_xiaomi(message: Message):
    await show_phones(message, CATEGORIES["📱 Xiaomi (Redmi/Poco)"])

@bot.on.message(text=["📱 Samsung"])
async def cat_samsung(message: Message):
    await show_phones(message, CATEGORIES["📱 Samsung"])

@bot.on.message(text=["📱 iPhone"])
async def cat_iphone(message: Message):
    await show_phones(message, CATEGORIES["📱 iPhone"])

@bot.on.message(text=["📱 Realme"])
async def cat_realme(message: Message):
    await show_phones(message, CATEGORIES["📱 Realme"])

@bot.on.message(text=["📱 Tecno/Infinix"])
async def cat_tecno(message: Message):
    await show_phones(message, CATEGORIES["📱 Tecno/Infinix"])

@bot.on.message(text=["📱 Другие"])
async def cat_other(message: Message):
    await show_phones(message, CATEGORIES["📱 Другие"])

async def show_phones(message: Message, phones):
    keyboard = Keyboard(one_time=False)
    for phone in phones:
        keyboard.add(Text(phone.title()))
    keyboard.row()
    keyboard.add(Text("⬅ Назад"))
    await message.answer(
        "📱 Выбери модель телефона:",
        keyboard=keyboard
    )

# ============================================================
# 🔍 ПОИСК ТЕЛЕФОНА ПО ТЕКСТУ
# ============================================================

@bot.on.message()
async def handle_message(message: Message):
    user_id = message.from_id
    user = get_user(user_id)
    text = message.text.strip()
    
    # Пропускаем команды, обработанные выше
    if message.text in ["меню", "Меню", "начать", "старт", "start",
                        "❓ Как это работает", "помощь", "help",
                        "📱 Бесплатные настройки", "🔥 Премиум (99₽)",
                        "✅ Оплатить 99₽", "📱 Xiaomi (Redmi/Poco)",
                        "📱 Samsung", "📱 iPhone", "📱 Realme",
                        "📱 Tecno/Infinix", "📱 Другие"]:
        return
    
    # Кнопка назад
    if text in ["⬅ Назад", "⬅ Назад в меню"]:
        await send_menu(message)
        user.state = MENU
        return
    
    if text == "🏠 В меню":
        await send_menu(message)
        user.state = MENU
        return
    
    # ==================== СОСТОЯНИЕ: БЕСПЛАТНЫЕ НАСТРОЙКИ ====================
    if user.state == FREE_PHONES or True:  # Всегда пробуем найти телефон
        phone = find_phone(text)
        if phone:
            config = get_config(phone)
            if config:
                await message.answer(
                    config,
                    keyboard=done_keyboard()
                )
                return
    
    # ==================== СОСТОЯНИЕ: ИИ ОПРОС ====================
    if user.state == AI_ASK_PHONE:
        user.phone = text
        user.state = AI_ASK_RAM
        await message.answer(
            "📱 Вопрос 2 из 6:\n"
            "Сколько у тебя ОЗУ (оперативной памяти)?\n\n"
            "• 2-3 ГБ\n"
            "• 4-6 ГБ\n"
            "• 8+ ГБ\n"
            "• Не знаю\n\n"
            "Напиши один из вариантов.",
            keyboard=back_button()
        )
        return
    
    if user.state == AI_ASK_RAM:
        user.ram = text
        user.state = AI_ASK_STYLE
        await message.answer(
            "🎮 Вопрос 3 из 6:\n"
            "Какой у тебя стиль игры?\n\n"
            "• Агрессивный (ближний бой, быстрые свайпы)\n"
            "• Пассивный (дальний бой, точность)\n"
            "• Смешанный\n\n"
            "Напиши свой стиль.",
            keyboard=back_button()
        )
        return
    
    if user.state == AI_ASK_STYLE:
        user.style = text
        user.state = AI_ASK_WEAPON
        await message.answer(
            "🔫 Вопрос 4 из 6:\n"
            "Какое основное оружие используешь?\n\n"
            "Например: M4A1, AK47, SCAR, Groza, MP40, MAG-7\n\n"
            "Напиши название оружия.",
            keyboard=back_button()
        )
        return
    
    if user.state == AI_ASK_WEAPON:
        user.weapon = text
        user.state = AI_ASK_FINGERS
        await message.answer(
            "🤟 Вопрос 5 из 6:\n"
            "Сколько пальцев используешь?\n\n"
            "• 2 пальца\n"
            "• 4 пальца (коготь)\n"
            "• 6 пальцев\n\n"
            "Напиши количество.",
            keyboard=back_button()
        )
        return
    
    if user.state == AI_ASK_FINGERS:
        user.fingers = text
        user.state = AI_ASK_PROBLEM
        await message.answer(
            "🔧 Вопрос 6 из 6 (последний):\n"
            "Есть конкретная проблема?\n\n"
            "Например:\n"
            "• Трудно контролить отдачу\n"
            "• Медленный поворот\n"
            "• Промахи в ближнем бою\n"
            "• Телефон греется и тормозит\n\n"
            "Если проблем нет — напиши «нет»",
            keyboard=back_button()
        )
        return
    
    if user.state == AI_ASK_PROBLEM:
        user.problem = text if text.lower() != "нет" else ""
        user.state = AI_DONE
        
        await message.answer("🤖 ИИ анализирует твои данные и подбирает настройки...\nЭто займёт 5-10 секунд.")
        
        prompt = build_user_prompt(user)
        response = await call_deepseek(prompt)
        
        await message.answer(
            response + f"\n\n🔄 Корректировок осталось: {user.corrections_left}\n"
            f"💬 Напиши «корректировка» если нужно что-то исправить.",
            keyboard=done_keyboard()
        )
        return
    
    # ==================== СОСТОЯНИЕ: КОРРЕКТИРОВКА ====================
    if user.state == AI_DONE or user.state == CORRECTION:
        if "корректировка" in text.lower():
            if user.corrections_left > 0:
                user.state = CORRECTION
                await message.answer(
                    "🔄 РЕЖИМ КОРРЕКТИРОВКИ\n\n"
                    "Напиши ЧТО именно нужно исправить.\n"
                    "Например:\n"
                    "• «трудно контролить отдачу»\n"
                    "• «медленный поворот»\n"
                    "• «неудобно нажимать кнопку огня»\n\n"
                    "Не пиши просто «плохо» — объясни что не так.\n"
                    f"У тебя осталось: {user.corrections_left} корректировка",
                    keyboard=back_button()
                )
                return
            else:
                await message.answer(
                    "❌ Лимит корректировок исчерпан.\n\n"
                    f"Новая персональная настройка будет доступна через {DAYS_BEFORE_NEW} дней.\n"
                    "А пока можешь использовать бесплатные шаблоны!",
                    keyboard=main_menu()
                )
                return
        
        if user.state == CORRECTION:
            user.corrections_left -= 1
            await message.answer("🤖 ИИ пересчитывает настройки с учётом проблемы...")
            
            prompt = build_correction_prompt(user, text)
            response = await call_deepseek(prompt)
            
            await message.answer(
                response + f"\n\n🔄 Корректировок осталось: {user.corrections_left}",
                keyboard=done_keyboard()
            )
            user.state = AI_DONE
            return
    
    # ==================== ЕСЛИ НИЧЕГО НЕ НАШЛОСЬ ====================
    await message.answer(
        "❌ Я не понял.\n\n"
        "Я отвечаю только на запросы по настройкам Free Fire.\n\n"
        "Напиши «меню» чтобы вернуться к выбору.\n"
        "Или «корректировка» если нужно исправить настройки.",
        keyboard=main_menu()
    )

# ============================================================
# 🔑 АДМИН-ПАНЕЛЬ
# ============================================================

@bot.on.message(text=["/stat", "/admin"])
async def admin_stats(message: Message):
    total_users = len(users)
    premium_users = sum(1 for u in users.values() if u.premium_active)
    await message.answer(
        f"📊 СТАТИСТИКА БОТА\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"💎 Премиум пользователей: {premium_users}\n"
        f"💰 Цена премиума: {PREMIUM_PRICE}₽\n"
        f"🔄 Корректировок на человека: {MAX_CORRECTIONS}\n"
        f"📅 Дней до новой настройки: {DAYS_BEFORE_NEW}\n"
        f"🖥 Сервер: Online"
    )

# ============================================================
# ЗАПУСК БОТА
# ============================================================

if __name__ == "__main__":
    print("=" * 40)
    print("🎮 Free Fire Settings Bot")
    print("=" * 40)
    print("🤖 Бот запускается...")
    print(f"💰 Премиум: {PREMIUM_PRICE}₽")
    print(f"🔄 Корректировок: {MAX_CORRECTIONS}")
    print(f"📅 Повтор через: {DAYS_BEFORE_NEW} дней")
    print(f"📱 Моделей в базе: {len(PHONES)}")
    print("=" * 40)
    bot.run_forever()
