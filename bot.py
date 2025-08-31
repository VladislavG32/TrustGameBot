import json
import logging
import random
import os
import time
import threading
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
from config import BOT_TOKEN

# Функция для поддержания активности бота
def keep_alive():
    while True:
        time.sleep(300)
        print("🔄 Бот активен...")

keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DB_FILE = 'database.json'

def load_db():
    try:
        with open(DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_db(data):
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_user_data(user_id):
    db = load_db()
    user_id_str = str(user_id)
    
    for pair_id, pair_data in db.items():
        if user_id_str in pair_data['users']:
            return pair_data, pair_id
    return None, None

# Система для отслеживания использованных заданий
class TaskManager:
    def __init__(self):
        self.used_tasks = {}
    
    def mark_used(self, pair_id, task_text, task_type):
        if pair_id not in self.used_tasks:
            self.used_tasks[pair_id] = {'truth': set(), 'dare': set()}
        self.used_tasks[pair_id][task_type].add(task_text)
    
    def is_used(self, pair_id, task_text, task_type):
        if pair_id not in self.used_tasks:
            return False
        return task_text in self.used_tasks[pair_id][task_type]
    
    def get_available_task(self, pair_id, level, task_type):
        available_tasks = [task for task in TASKS[level][task_type] 
                          if not self.is_used(pair_id, task, task_type)]
        if not available_tasks:
            # Если все задания использованы, очищаем историю для этого типа
            if pair_id in self.used_tasks:
                self.used_tasks[pair_id][task_type] = set()
            available_tasks = TASKS[level][task_type]
        return random.choice(available_tasks)

task_manager = TaskManager()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [['/register_partner']]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        "🎮 Добро пожаловать в Игру Доверия! 🤝\n\n"
        "Чтобы начать:\n"
        "1. Добавь партнера в контакты\n"
        "2. Нажми /register_partner @username_партнера\n"
        "3. Выбери уровень сложности\n"
        "4. Начни игру!\n\n"
        "Доступные команды:\n"
        "• /level - выбрать уровень\n"
        "• /game - начать игру\n"
        "• /status - статус игры\n"
        "• /joker - пропустить задание\n"
        "• /punishment - получить наказание",
        reply_markup=reply_markup
    )

async def register_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    target_username = context.args[0] if context.args else None

    if not target_username:
        await update.message.reply_text("Укажи username партнера: /register_partner @username")
        return

    target_username = target_username.lstrip('@')
    
    if not username:
        await update.message.reply_text("❌ Установи username в настройках Telegram!")
        return

    db = load_db()
    user_data, pair_id = get_user_data(user_id)
    
    if user_data:
        await update.message.reply_text("✅ Ты уже в игре! Напиши /game")
        return

    pair_found = False
    for pair_id, pair_data in db.items():
        if username in pair_data['pending_users']:
            partner_id = list(pair_data['users'].keys())[0]
            partner_username = pair_data['users'][partner_id]['username']
            
            if partner_username == target_username:
                pair_data['users'][str(user_id)] = {
                    'username': username,
                    'truth_count': 0,
                    'jokers': 1,
                    'pending_action': None,
                    'used_tasks': []
                }
                pair_data['pending_users'].remove(username)
                pair_data['current_turn'] = partner_id
                save_db(db)
                
                level_keyboard = [['/level 1', '/level 2', '/level 3']]
                level_markup = ReplyKeyboardMarkup(level_keyboard, resize_keyboard=True)
                
                try:
                    await context.bot.send_message(
                        chat_id=partner_id,
                        text=f"🎉 Вы связаны с @{username}!\n\n"
                             f"Выбери уровень сложности и напиши /game",
                        reply_markup=level_markup
                    )
                    await update.message.reply_text(
                        f"🎉 Вы связаны с @{partner_username}!\n\n"
                        f"Выбери уровень сложности и напиши /game",
                        reply_markup=level_markup
                    )
                except Exception:
                    await update.message.reply_text("❌ Попроси партнера написать боту!")
                    db.pop(pair_id)
                    save_db(db)
                    return
                    
                pair_found = True
                break

    if not pair_found:
        new_pair_id = f"pair_{user_id}_{target_username}"
        db[new_pair_id] = {
            'users': {
                str(user_id): {
                    'username': username,
                    'truth_count': 0,
                    'jokers': 1,
                    'pending_action': None,
                    'used_tasks': []
                }
            },
            'pending_users': [target_username],
            'level': 1,
            'current_turn': str(user_id),
            'used_tasks': {'truth': [], 'dare': []}
        }
        save_db(db)
        
        await update.message.reply_text(
            f"✅ Запрос для @{target_username} создан!\n\n"
            f"Попроси партнера написать: /register_partner @{username}"
        )

async def set_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data, pair_id = get_user_data(user_id)

    if not user_data:
        await update.message.reply_text("❌ Сначала зарегистрируй партнера")
        return

    if not context.args:
        level_keyboard = [['/level 1', '/level 2', '/level 3']]
        reply_markup = ReplyKeyboardMarkup(level_keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "🎚️ Выбери уровень сложности:",
            reply_markup=reply_markup
        )
        return

    try:
        new_level = int(context.args[0])
        if new_level not in [1, 2, 3]:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Уровень должен быть: 1, 2 или 3")
        return

    db = load_db()
    db[pair_id]['level'] = new_level
    save_db(db)

    level_names = {1: "❄️ Лёд тронулся", 2: "🌊 Бездонное озеро", 3: "🔥 Вулкан страсти"}
    
    await update.message.reply_text(f"✅ Уровень изменен: {level_names[new_level]}")

async def game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data, pair_id = get_user_data(user_id)

    if not user_data:
        await update.message.reply_text("❌ Сначала зарегистрируй партнера")
        return

    partner_id = [uid for uid in user_data['users'].keys() if uid != str(user_id)][0]
    partner_username = user_data['users'][partner_id]['username']
    current_player_id = user_data['current_turn']

    if current_player_id == str(user_id):
        action_keyboard = [['/truth', '/dare'], ['/status', '/joker']]
        reply_markup = ReplyKeyboardMarkup(action_keyboard, resize_keyboard=True)
        
        level_names = {1: "❄️", 2: "🌊", 3: "🔥"}
        current_level = level_names[user_data['level']]
        
        await update.message.reply_text(
            f"🎮 Твой ход! {current_level}\n\n"
            f"Выбери для @{partner_username}:\n"
            f"• /truth - Правда 🤔\n"
            f"• /dare - Действие 🎯\n\n"
            f"Доступно Джокеров: {user_data['users'][str(user_id)]['jokers']} 🃏",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(f"⏳ Сейчас очередь @{partner_username}. Жди своего хода!")

# База заданий (сокращенная версия для примера)
TASKS = {
    1: {
        'truth': ["Какая моя фотография нравится тебе больше всего?", "Какой у меня смешной недостаток?"],
        'dare': ["Отправь голосовое с приветствием", "Сфоткай свою улыбку"]
    },
    2: {
        'truth': ["Чего ты боишься в наших отношениях?", "О чём ты никогда не попросишь?"],
        'dare': ["Опиши наш идеальный день", "Запиши свой смех"]
    },
    3: {
        'truth': ["Где самое эротичное место где ты хочешь меня?", "Какая фантазия про нас самая запретная?"],
        'dare': ["Пришли фото запястья с текстом «Поцелуй»", "Опиши что будешь делать наедине"]
    }
}

PUNISHMENTS = ["Спой песню о неудаче", "Сделай нелепое селфи", "Напиши признание предмету"]

async def truth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data, pair_id = get_user_data(user_id)

    if not user_data or user_data['current_turn'] != str(user_id):
        await update.message.reply_text("❌ Сейчас не твой ход!")
        return

    current_user = user_data['users'][str(user_id)]
    if current_user['truth_count'] >= 2:
        await update.message.reply_text("❌ Слишком много правды! Выбери Действие (/dare).")
        return

    current_user['truth_count'] += 1
    partner_id = [uid for uid in user_data['users'].keys() if uid != str(user_id)][0]
    partner_data = user_data['users'][partner_id]
    partner_data['truth_count'] = 0

    level = user_data['level']
    question = task_manager.get_available_task(pair_id, level, 'truth')
    task_manager.mark_used(pair_id, question, 'truth')

    partner_data['pending_action'] = f"Правда: {question}"
    db = load_db()
    db[pair_id]['users'][partner_id]['pending_action'] = partner_data['pending_action']
    db[pair_id]['current_turn'] = partner_id
    save_db(db)

    action_keyboard = [['/joker', '/punishment'], ['/status']]
    reply_markup = ReplyKeyboardMarkup(action_keyboard, resize_keyboard=True)
    
    level_names = {1: "❄️", 2: "🌊", 3: "🔥"}
    
    await update.message.reply_text(
        f"🤔 Ты выбрал(а) ПРАВДУ для @{partner_data['username']}\n"
        f"Вопрос: {question}\n\n"
        f"Жди ответа! 📝"
    )
    
    await context.bot.send_message(
        chat_id=partner_id,
        text=f"🤔 ДЛЯ ТЕБЯ ПРАВДА! {level_names[level]}\n\n"
             f"Вопрос: {question}\n\n"
             f"📝 Ответ пришли партнеру в общий чат!\n\n"
             f"Если не хочешь отвечать:\n"
             f"• /joker - Пропустить (осталось: {partner_data['jokers']} 🃏)\n"
             f"• /punishment - Получить наказание",
        reply_markup=reply_markup
    )

async def dare(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data, pair_id = get_user_data(user_id)

    if not user_data or user_data['current_turn'] != str(user_id):
        await update.message.reply_text("❌ Сейчас не твой ход!")
        return

    current_user = user_data['users'][str(user_id)]
    current_user['truth_count'] = 0

    partner_id = [uid for uid in user_data['users'].keys() if uid != str(user_id)][0]
    partner_data = user_data['users'][partner_id]
    partner_data['truth_count'] = 0

    level = user_data['level']
    task = task_manager.get_available_task(pair_id, level, 'dare')
    task_manager.mark_used(pair_id, task, 'dare')

    partner_data['pending_action'] = f"Действие: {task}"
    db = load_db()
    db[pair_id]['users'][partner_id]['pending_action'] = partner_data['pending_action']
    db[pair_id]['current_turn'] = partner_id
    save_db(db)

    action_keyboard = [['/joker', '/punishment'], ['/status']]
    reply_markup = ReplyKeyboardMarkup(action_keyboard, resize_keyboard=True)
    
    level_names = {1: "❄️", 2: "🌊", 3: "🔥"}
    
    await update.message.reply_text(
        f"🎯 Ты выбрал(а) ДЕЙСТВИЕ для @{partner_data['username']}\n"
        f"Задание: {task}\n\n"
        f"Жди выполнения! 🎬"
    )
    
    await context.bot.send_message(
        chat_id=partner_id,
        text=f"🎯 ДЛЯ ТЕБЯ ДЕЙСТВИЕ! {level_names[level]}\n\n"
             f"Задание: {task}\n\n"
             f"🎬 Выполни и пришли результат партнеру!\n\n"
             f"Если не хочешь выполнять:\n"
             f"• /joker - Пропустить (осталось: {partner_data['jokers']} 🃏)\n"
             f"• /punishment - Получить наказание",
        reply_markup=reply_markup
    )

async def joker(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data, pair_id = get_user_data(user_id)

    if not user_data:
        await update.message.reply_text("❌ Ты не в игре!")
        return

    current_user = user_data['users'][str(user_id)]
    partner_id = [uid for uid in user_data['users'].keys() if uid != str(user_id)][0]

    if current_user['jokers'] <= 0:
        await update.message.reply_text("❌ У тебя не осталось Джокеров!")
        return

    if not current_user['pending_action']:
        await update.message.reply_text("❌ Тебе нечего пропускать!")
        return

    current_user['jokers'] -= 1
    current_user['pending_action'] = None
    user_data['current_turn'] = partner_id

    db = load_db()
    db[pair_id]['users'][str(user_id)]['jokers'] = current_user['jokers']
    db[pair_id]['users'][str(user_id)]['pending_action'] = None
    db[pair_id]['current_turn'] = partner_id
    save_db(db)

    action_keyboard = [['/truth', '/dare'], ['/status']]
    reply_markup = ReplyKeyboardMarkup(action_keyboard, resize_keyboard=True)
    
    await update.message.reply_text("🃏 Джокер использован! Задание пропущено.")
    await context.bot.send_message(
        chat_id=partner_id,
        text=f"🃏 Партнер использовал Джокер! Теперь твой ход.\n\n"
             f"Выбери:\n• /truth - Правда\n• /dare - Действие",
        reply_markup=reply_markup
    )

async def punishment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data, pair_id = get_user_data(user_id)

    if not user_data:
        await update.message.reply_text("❌ Ты не в игре!")
        return

    current_user = user_data['users'][str(user_id)]
    partner_id = [uid for uid in user_data['users'].keys() if uid != str(user_id)][0]

    if not current_user['pending_action']:
        await update.message.reply_text("❌ У тебя нет задания для наказания!")
        return

    punishment_text = random.choice(PUNISHMENTS)
    current_user['pending_action'] = None
    user_data['current_turn'] = partner_id

    db = load_db()
    db[pair_id]['users'][str(user_id)]['pending_action'] = None
    db[pair_id]['current_turn'] = partner_id
    save_db(db)

    action_keyboard = [['/truth', '/dare'], ['/status']]
    reply_markup = ReplyKeyboardMarkup(action_keyboard, resize_keyboard=True)
    
    await update.message.reply_text(f"⚡ НАКАЗАНИЕ: {punishment_text}")
    await context.bot.send_message(
        chat_id=partner_id,
        text=f"⚡ Партнер получил Наказание! Теперь твой ход.\n\n"
             f"Выбери:\n• /truth - Правда\n• /dare - Действие",
        reply_markup=reply_markup
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data, pair_id = get_user_data(user_id)

    if not user_data:
        await update.message.reply_text("❌ Ты не в игре!")
        return

    partner_id = [uid for uid in user_data['users'].keys() if uid != str(user_id)][0]
    partner_data = user_data['users'][partner_id]

    level_names = {1: "❄️ Лёд тронулся", 2: "🌊 Бездонное озеро", 3: "🔥 Вулкан страсти"}
    current_level = level_names[user_data['level']]

    current_turn = "✅ Твой ход!" if user_data['current_turn'] == str(user_id) else f"⏳ Очередь партнера"
    
    jokers_you = user_data['users'][str(user_id)]['jokers']
    pending_action = user_data['users'][str(user_id)]['pending_action']
    action_status = f"📋 Задание: {pending_action}" if pending_action else "📋 Задания нет"

    status_text = (
        f"📊 СТАТУС ИГРЫ:\n\n"
        f"• Партнер: @{partner_data['username']}\n"
        f"• Уровень: {current_level}\n"
        f"• {current_turn}\n"
        f"• Твои Джокеры: {jokers_you} 🃏\n"
        f"• {action_status}"
    )

    await update.message.reply_text(status_text)

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("register_partner", register_partner))
    application.add_handler(CommandHandler("level", set_level))
    application.add_handler(CommandHandler("game", game))
    application.add_handler(CommandHandler("truth", truth))
    application.add_handler(CommandHandler("dare", dare))
    application.add_handler(CommandHandler("joker", joker))
    application.add_handler(CommandHandler("punishment", punishment))
    application.add_handler(CommandHandler("status", status))

    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
