# states.py
# Состояния пользователей (FSM - конечный автомат)

MENU = "MENU"                 # Главное меню
FREE_PHONES = "FREE_PHONES"   # Выбор бесплатной модели
AI_WAITING = "AI_WAITING"     # Ожидание оплаты
AI_ASK_PHONE = "AI_ASK_PHONE"      # Вопрос 1: телефон
AI_ASK_RAM = "AI_ASK_RAM"          # Вопрос 2: ОЗУ
AI_ASK_STYLE = "AI_ASK_STYLE"      # Вопрос 3: стиль игры
AI_ASK_WEAPON = "AI_ASK_WEAPON"    # Вопрос 4: оружие
AI_ASK_FINGERS = "AI_ASK_FINGERS"  # Вопрос 5: пальцы
AI_ASK_PROBLEM = "AI_ASK_PROBLEM"  # Вопрос 6: проблема
AI_DONE = "AI_DONE"           # Настройка выдана, ожидание корректировки
CORRECTION = "CORRECTION"     # Режим корректировки