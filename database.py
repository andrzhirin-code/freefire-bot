# database.py
# Мини-база данных (в памяти, сбросится при перезапуске)

import time

class UserData:
    def __init__(self, user_id):
        self.user_id = user_id
        self.state = "MENU"
        self.phone = ""
        self.ram = ""
        self.style = ""
        self.weapon = ""
        self.fingers = ""
        self.problem = ""
        self.corrections_left = 2
        self.last_paid = None
        self.premium_active = False

# Хранилище пользователей
users = {}

def get_user(user_id):
    if user_id not in users:
        users[user_id] = UserData(user_id)
    return users[user_id]

def reset_user(user_id):
    users[user_id] = UserData(user_id)
    return users[user_id]