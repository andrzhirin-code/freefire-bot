def btn(label, color="primary"):
    return {"action": {"type": "text", "label": label}, "color": color}

def main_menu():
    return {
        "one_time": False,
        "buttons": [
            [btn("📱 Бесплатные настройки", "primary")],
            [btn("🔥 Премиум (99₽)", "positive")],
            [btn("❓ Как это работает", "secondary")],
        ]
    }

def categories_menu():
    return {
        "one_time": False,
        "buttons": [
            [btn("📱 Xiaomi (Redmi/Poco)")],
            [btn("📱 Samsung")],
            [btn("📱 iPhone")],
            [btn("📱 Realme")],
            [btn("📱 Tecno/Infinix")],
            [btn("📱 Другие")],
            [btn("⬅ Назад в меню", "secondary")],
        ]
    }

def back_button():
    return {
        "one_time": False,
        "buttons": [
            [btn("⬅ Назад", "secondary")],
            [btn("🏠 В меню", "secondary")],
        ]
    }

def done_keyboard():
    return {
        "one_time": False,
        "buttons": [
            [btn("🔄 Корректировка")],
            [btn("🏠 В меню", "secondary")],
        ]
    }

def premium_keyboard():
    return {
        "one_time": False,
        "buttons": [
            [btn("✅ Оплатить 99₽", "positive")],
            [btn("⬅ Назад", "secondary")],
        ]
    }
