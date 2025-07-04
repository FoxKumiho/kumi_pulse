import random

class Player:
    BASE_EXP = 100
    POWER = 2
    MAX_LEVEL = 5000
    TAX_PER_DAY = 3

    def __init__(self, hp, damage, mana, profession=None, exp=0):
        self.hp=hp
        self.damage = damage
        self.mana = mana
        self.profession = profession  # может быть None
        self.exp = exp

    level = 1

global p

p = Player(hp=100, damage=15, mana=50, exp=0)

class Enemy:
    def __init__(self, name, hp, damage, mana, exp=0):
        self.name = name
        self.hp = hp
        self.damage = damage
        self.mane = mana
        self.exp = exp

    def __str__(self):
        return str(self.name)



def random_experience(days= 365, exp_per_success=5, chance=0.5):
    total_exp = 0
    for _ in range(days):
        if random.random() < chance:
            total_exp += exp_per_success
    return total_exp

# функция для расчёта HP по уровню
def hp_for_level(level, base_hp=100, hp_per_level=20):
    return base_hp + (level - 1) * hp_per_level


def exp_for_level(level):
    """Общее накопленное количество опыта для достижения уровня."""
    return int(BASE_EXP * (level ** POWER))

def get_level(exp):
    level = int((exp / BASE_EXP) ** (1 / POWER))
    if level < 1:
        return 1
    elif level > 5000:
        return 5000
    else:
        return level

BASE_EXP = 10
POWER = 2



people = [
    {"name": "Михаил", "age": 26},
    {"name": "Анна", "age": 22},
    {"name": "Игорь", "age": 30},
    {"name": "Елена", "age": 25},
    {"name": "Сергей", "age": 28}
]

Slave = [
    {"role": " раб" },
    {"level": "0 - 5" }
]

professions = [
    {"name": "фермер", "gold": 4},
    {"name": "кузнец", "gold": 6},
    {"name": "торговец", "gold": 12},
    {"name": "солдат", "gold": 8},
    {"name": "ремесленник", "gold": 5},
    {"name": "рыбак", "gold": 4},
    {"name": "пекарь", "gold": 5}
]

debt = 100  # долг, который надо отдать

cataclysms = [
    {
        "name": "Война",
        "effects": {
            "фермер": {"gold": -2, "exp": -0.1},
            "кузнец": {"gold": +1, "exp": +0.1},
            "торговец": {"gold": -3, "exp": -0.2},
            "солдат": {"gold": +5, "exp": +0.3},
            "ремесленник": {"gold": -1, "exp": -0.1},
            "рыбак": {"gold": -2, "exp": -0.1},
            "пекарь": {"gold": -1, "exp": 0}
        }
    },
    {
        "name": "Болезнь",
        "effects": {
            "фермер": {"gold": -3, "exp": -0.2},
            "кузнец": {"gold": -1, "exp": -0.1},
            "торговец": {"gold": -2, "exp": -0.1},
            "солдат": {"gold": -2, "exp": -0.1},
            "ремесленник": {"gold": -2, "exp": -0.2},
            "рыбак": {"gold": -3, "exp": -0.2},
            "пекарь": {"gold": -1, "exp": -0.1}
        }
    },
    {
        "name": "Заморские штормы",
        "effects": {
            "фермер": {"gold": 0, "exp": 0},
            "кузнец": {"gold": 0, "exp": 0},
            "торговец": {"gold": -4, "exp": -0.3},
            "солдат": {"gold": 0, "exp": 0},
            "ремесленник": {"gold": -1, "exp": -0.1},
            "рыбак": {"gold": -5, "exp": -0.4},
            "пекарь": {"gold": 0, "exp": 0}
        }
    }
]

# Случайный выбор катаклизма на период
current_cataclysm = random.choice(cataclysms)
print(f"Текущий катаклизм: {current_cataclysm['name']}")

for person in people:
    profession = random.choice(professions)
    exp = random_experience()

    # создаём экземпляр Player
    player = Player(hp=100, damage=15, mana=50, profession=profession["name"], exp=exp)

    days_worked = (person["age"] - 16) * 365
    base_gold_per_day = profession["gold"] - 3

    effects = current_cataclysm["effects"].get(profession["name"], {"gold": 0, "exp": 0})

    gold_per_day = base_gold_per_day + effects["gold"]
    player.exp = int(player.exp * (1 + effects["exp"]))

    gold_earned = days_worked * gold_per_day
    status = "раб" if gold_earned < debt else "свободен"
    hp = hp_for_level(player.level)

    print(f"{person['name']} ({person['age']} лет) - Профессия: {player.profession}, "
          f"Опыт: {player.exp}, Уровень: {player.level}, HP: {hp}, Золото: {gold_earned}, Статус: {status}")

def quicksort(arr):
    if len(arr) <= 1:
        return arr
    pivot = arr[len(arr) // 2]
    left = [x for x in arr if x < pivot]
    middle = [x for x in arr if x == pivot]
    right = [x for  x in arr if x > pivot]
    return quicksort(left) + middle + quicksort(right)

print(quicksort([3,4,5,10,1,3,2,1]))

def __dir__():
    return 

print(f"привет")

input_line = input()
numbers_as_strings = input_line.split()
a = int(numbers_as_strings[0])
b = int(numbers_as_strings[1])
sum_result = a + b
print(sum_result)


print(('up', 3)