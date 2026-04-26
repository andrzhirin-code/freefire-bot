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
        self.premium_active = False

users = {}

def get_user(user_id):
    if user_id not in users:
        users[user_id] = UserData(user_id)
    return users[user_id]
