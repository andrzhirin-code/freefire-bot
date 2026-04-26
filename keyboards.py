def main_menu():
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "📱 Бесплатные настройки", "payload": "free"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "🔥 Премиум (99₽)", "payload": "premium"}, "color": "positive"}],
            [{"action": {"type": "text", "label": "❓ Как это работает", "payload": "help"}, "color": "secondary"}],
        ]
    }

def categories_menu():
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "📱 Xiaomi (Redmi/Poco)", "payload": "cat_xiaomi"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "📱 Samsung", "payload": "cat_samsung"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "📱 iPhone", "payload": "cat_iphone"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "📱 Realme", "payload": "cat_realme"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "📱 Tecno/Infinix", "payload": "cat_tecno"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "📱 Другие", "payload": "cat_other"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "⬅ Назад в меню", "payload": "back"}, "color": "secondary"}],
        ]
    }

def back_button():
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "⬅ Назад", "payload": "back"}, "color": "secondary"}],
            [{"action": {"type": "text", "label": "🏠 В меню", "payload": "home"}, "color": "secondary"}],
        ]
    }

def done_keyboard():
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "🔄 Корректировка", "payload": "correct"}, "color": "primary"}],
            [{"action": {"type": "text", "label": "🏠 В меню", "payload": "home"}, "color": "secondary"}],
        ]
    }

def premium_keyboard():
    return {
        "one_time": False,
        "buttons": [
            [{"action": {"type": "text", "label": "✅ Оплатить 99₽", "payload": "pay"}, "color": "positive"}],
            [{"action": {"type": "text", "label": "⬅ Назад", "payload": "back"}, "color": "secondary"}],
        ]
    }
