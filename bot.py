import json
import logging
import random



import os
import time
import threading

def keep_alive():
    """Функция для поддержания активности бота"""
    while True:
        time.sleep(300)  # Каждые 5 минут
        print("🔄 Бот активен...")

# Запускаем в отдельном потоке
keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
keep_alive_thread.start()




from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from config import BOT_TOKEN

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
            
        if 'pending_users' in pair_data:
            for uid, user_data in pair_data['users'].items():
                if user_data['username'] in pair_data['pending_users']:
                    return pair_data, pair_id
                
    return None, None

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
        await update.message.reply_text("❌ У тебя не установлен username в Telegram. Установи его в настройках!")
        return

    db = load_db()
    user_data, pair_id = get_user_data(user_id)
    
    if user_data:
        await update.message.reply_text("✅ Ты уже в игре! Напиши /game чтобы начать")
        return

    # Ищем существующую заявку
    pair_found = False
    for pair_id, pair_data in db.items():
        if username in pair_data['pending_users']:
            partner_id = list(pair_data['users'].keys())[0]
            partner_username = pair_data['users'][partner_id]['username']
            
            if partner_username == target_username:
                # Добавляем пользователя в пару
                pair_data['users'][str(user_id)] = {
                    'username': username,
                    'truth_count': 0,
                    'jokers': 1,
                    'pending_action': None
                }
                pair_data['pending_users'].remove(username)
                pair_data['current_turn'] = partner_id
                save_db(db)
                
                # Создаем клавиатуру выбора уровня
                level_keyboard = [['/level 1', '/level 2', '/level 3']]
                level_markup = ReplyKeyboardMarkup(level_keyboard, resize_keyboard=True)
                
                try:
                    await context.bot.send_message(
                        chat_id=partner_id,
                        text=f"🎉 Вы связаны с @{username}!\n\n"
                             f"Выбери уровень сложности:\n"
                             f"• /level 1 - Лёгкий ❄️\n"
                             f"• /level 2 - Средний 🌊\n"
                             f"• /level 3 - Сложный 🔥\n\n"
                             f"После выбора напиши /game",
                        reply_markup=level_markup
                    )
                    await update.message.reply_text(
                        f"🎉 Вы связаны с @{partner_username}!\n\n"
                        f"Выбери уровень сложности:\n"
                        f"• /level 1 - Лёгкий ❄️\n"
                        f"• /level 2 - Средний 🌊\n"
                        f"• /level 3 - Сложный 🔥\n\n"
                        f"После выбора напиши /game",
                        reply_markup=level_markup
                    )
                except Exception as e:
                    await update.message.reply_text("❌ Не могу написать партнеру. Попроси его написать боту!")
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
                    'pending_action': None
                }
            },
            'pending_users': [target_username],
            'level': 1,
            'current_turn': str(user_id)
        }
        save_db(db)
        
        await update.message.reply_text(
            f"✅ Запрос для @{target_username} создан!\n\n"
            f"Попроси партнера:\n"
            f"1. Написать мне\n"
            f"2. Отправить: /register_partner @{username}\n\n"
            f"Я свяжу вас автоматически! 🤝"
        )

async def set_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data, pair_id = get_user_data(user_id)

    if not user_data:
        await update.message.reply_text("❌ Сначала зарегистрируй партнера: /register_partner @username")
        return

    if not context.args:
        level_keyboard = [['/level 1', '/level 2', '/level 3']]
        reply_markup = ReplyKeyboardMarkup(level_keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            "🎚️ Выбери уровень сложности:\n\n"
            "• /level 1 - Лёд тронулся ❄️ (лёгкий)\n"
            "• /level 2 - Бездонное озеро 🌊 (средний)\n"
            "• /level 3 - Вулкан страсти 🔥 (18+)\n\n"
            "Уровень можно менять в любое время!",
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

    level_names = {
        1: "❄️ Лёд тронулся (лёгкий)",
        2: "🌊 Бездонное озеро (средний)", 
        3: "🔥 Вулкан страсти (18+)"
    }
    
    game_keyboard = [['/game']]
    reply_markup = ReplyKeyboardMarkup(game_keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        f"✅ Уровень изменен: {level_names[new_level]}\n\n"
        f"Напиши /game чтобы начать игру!",
        reply_markup=reply_markup
    )

async def game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data, pair_id = get_user_data(user_id)

    if not user_data:
        await update.message.reply_text("❌ Сначала зарегистрируй партнера: /register_partner @username")
        return

    partner_id = [uid for uid in user_data['users'].keys() if uid != str(user_id)][0]
    partner_username = user_data['users'][partner_id]['username']
    current_player_id = user_data['current_turn']

    if current_player_id == str(user_id):
        # Создаем клавиатуру для выбора действия
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

# База заданий (остается без изменений)
TASKS = {
    1: {
        'truth': [
            "Какая моя фотография в соцсетях нравится тебе больше всего?",
            "Какой у меня самый смешной недостаток?",
            "В какой момент нашего общения ты подумал(а) «ого, он(а) крутой(ая)»?",
            "Что тебе во мне нравится больше всего?",
            "Какой мой поступок тебя больше всего удивил?",
            "Какой фильм ты бы хотел(а) посмотреть со мной?",
            "Что тебя заставило обратить на меня внимание?",
            "Какой мой образ тебе нравится больше всего?",
            "Что бы ты хотел(а) изменить во мне?",
            "Какой подарок от меня ты бы хотел(а) получить?",
            "Где бы ты хотел(а) со мной поужинать?",
            "Что тебя смешит во мне?",
            "Какой момент нашего знакомства ты помнишь лучше всего?",
            "Что ты думал(а) обо мне при первой встрече?",
            "Какую песню ты ассоциируешь со мной?",
            "Что тебе нравится в моем характере?",
            "Какой комплимент от меня запомнился больше всего?",
            "Что бы ты хотел(а) делать вместе со мной?",
            "Какой мой талант тебя впечатляет?",
            "Что тебя раздражает во мне?",
            "Какую страну ты бы хотел(а) посетить со мной?",
            "Что ты считаешь моей самой милой привычкой?",
            "Какой жанр музыки ты бы хотел(а) мне посоветовать?",
            "Что тебе нравится в моей улыбке?",
            "Какой момент из нашего общения тебя смутил?",
            "Что ты думаешь о моем вкусе в одежде?",
            "Какую книгу ты бы рекомендовал(а) мне прочитать?",
            "Что тебе нравится в моем голосе?",
            "Какой сериал ты бы хотел(а) посмотреть вместе?",
            "Что ты считаешь моей самой привлекательной чертой?",
            "Какой вид спорта ты бы хотел(а) попробовать со мной?",
            "Что тебе нравится в моих глазах?",
            "Какой десерт ты бы хотел(а) разделить со мной?",
            "Что ты думаешь о моем чувстве юмора?",
            "Какой праздник ты бы хотел(а) отметить вместе?",
            "Что тебе нравится в моих руках?",
            "Какую суперспособность ты бы мне подарил(а)?",
            "Что ты считаешь моей самой милой чертой?",
            "Какой вид отдыха ты предпочитаешь со мной?",
            "Что тебе нравится в моей походке?",
            "Какую еду ты бы хотел(а) приготовить для меня?",
            "Что ты думаешь о моей улыбке?",
            "Какой подарок ты бы мне подарил(а)?",
            "Что тебе нравится в моем смехе?",
            "Какую игру ты бы хотел(а) со мной сыграть?",
            "Что ты считаешь моей самой сексуальной чертой?",
            "Какой напиток ассоциируется у тебя со мной?",
            "Что тебе нравится в моих волосах?",
            "Какую погоду ты любишь проводить со мной?",
            "Что ты думаешь о моей энергии?"
        ],
        'dare': [
            "Отправь голосовое, где скажешь «Привет, [имя]» самым соблазнительным голосом",
            "Сфоткай свою улыбку и пришли",
            "Нарисуй нас в виде двух забавных существ и пришли фото",
            "Спой куплет любимой песни и отправь голосовое",
            "Сфотографируй вид из своего окна и пришли",
            "Напиши стих про меня из 4 строк",
            "Сделай селфи с забавной рожицей",
            "Отправь фото своей текущей обуви",
            "Запиши танец под 15 секунд музыки",
            "Сфоткай что ты сейчас ешь/пьешь",
            "Нарисуй сердечко на руке и пришли фото",
            "Сделай комплимент мне голосовым сообщением",
            "Сфотографируй свою подушку",
            "Запиши как ты произносишь мое имя шепотом",
            "Сфоткай свои носки",
            "Напиши мое имя на бумаге и пришли фото",
            "Сделай селфи с домашним животным",
            "Отправь фото своего рабочего стола",
            "Запиши звук своего смеха",
            "Сфоткай свою зубную щетку",
            "Напиши сообщение левой рукой (если правша)",
            "Сделай селфи в шапке",
            "Отправь фото своей кружки",
            "Запиши как ты зеваешь",
            "Сфоткай свои брови крупным планом",
            "Напиши три комплимента мне подряд",
            "Сделай селфи с книгой",
            "Отправь фото своего завтрака",
            "Запиши как ты говоришь 'Я тебя хочу'",
            "Сфоткай свою тень",
            "Нарисуй смайлик на пальце и пришли",
            "Сделай селфи с цветком",
            "Отправь фото своего отражения в зеркале",
            "Запиши как ты шепчешь хорошую ночь",
            "Сфоткай свои ресницы",
            "Напиши мое имя на песке/муке/сахаре",
            "Сделай селфи с подмигиванием",
            "Отправь фото своего настроения сегодня",
            "Запиши как ты произносишь 'обожаю тебя'",
            "Сфоткай свои запястья",
            "Нарисуй солнышко и пришли",
            "Сделай селфи с поднятыми большими пальцами",
            "Отправь фото своего любимого места дома",
            "Запиши как ты говоришь 'ты прекрасен/а'",
            "Сфоткай свои колени",
            "Напиши сообщение с закрытыми глазами",
            "Сделай селфи с воздушным поцелуем",
            "Отправь фото своего телефона",
            "Запиши как ты свистишь",
            "Сфоткай свои ресницы сбоку"
        ]
    },
    2: {
        'truth': [
            "Чего ты боишься в наших отношениях?",
            "Какую мою слабость или уязвимость ты заметил(а)?",
            "О чём ты никогда не попросишь, но очень хочешь?",
            "Какая твоя самая большая тайна от меня?",
            "Что бы ты сделал(а), если бы мы расстались?",
            "Какое мое качество тебя пугает?",
            "О чем ты чаще всего лжешь мне?",
            "Что тебе не нравится в наших отношениях?",
            "Какую ошибку в отношениях ты боишься повторить?",
            "Что ты скрываешь от своих друзей про меня?",
            "Какое твое самое большое разочарование во мне?",
            "Что бы ты хотел(а) изменить в нашей интимной жизни?",
            "О чем ты жалеешь в наших отношениях?",
            "Что тебя бесит в моем характере?",
            "Какую ложь ты мне говорил(а)?",
            "Что ты думаешь о моей ревности?",
            "Какое твое самое постыдное воспоминание?",
            "Что бы ты сделал(а), если бы изменил(а) мне?",
            "О чем ты мечтаешь, но боишься сказать?",
            "Что тебя раздражает в моих привычках?",
            "Какую боль я тебе причинил(а)?",
            "Что ты скрываешь от своей семьи про меня?",
            "Какое твое самое большое сомнение во мне?",
            "Что бы ты хотел(а) забыть в наших отношениях?",
            "О чем ты врешь себе про меня?",
            "Что тебя пугает в моем прошлом?",
            "Какую слабость ты никогда не покажешь?",
            "Что ты думаешь о моих друзьях?",
            "Какое твое самое большое опасение о нашем будущем?",
            "Что бы ты сделал(а) ради меня, но боишься?",
            "О чем ты плачешь, когда один/одна?",
            "Что тебя разочаровало во мне?",
            "Какую правду ты боишься мне сказать?",
            "Что ты ненавидишь в моем характере?",
            "Какое твое самое большое сожаление о нас?",
            "Что бы ты хотел(а) получить от меня, но не просишь?",
            "О чем ты фантазируешь, но стесняешься сказать?",
            "Что тебя бесит в моем поведении с другими?",
            "Какую тайну ты унес(ла) бы с собой в могилу?",
            "Что ты думаешь о моей семье?",
            "Какое твое самое большое беспокойство о нас?",
            "Что бы ты простил(а), но никогда не забудешь?",
            "О чем ты молишься, когда мне плохо?",
            "Что тебя раздражает в моей внешности?",
            "Какую боль ты мне причинил(а)?",
            "Что ты скрываешь о своем здоровье?",
            "Какое твое самое темное желание?",
            "Что бы ты сделал(а) по-другому в наших отношениях?",
            "О чем ты врешь своим родителям про меня?",
            "Что тебя пугает в моих глазах?"
        ],
        'dare': [
            "Опиши, как бы прошел наш идеальный день вместе, от пробуждения до сна",
            "Запиши на диктофон свой искренний смех и пришли",
            "Пришли фото своего тайного места в доме, где любишь прятаться",
            "Напиши письмо себе из будущего о наших отношениях",
            "Запиши видео, где рассказываешь о своем страхе",
            "Сфоткай свою кровать и пришли",
            "Напиши список из 10 вещей, которые ты хочешь со мной сделать",
            "Запиши голосовое, где признаешься в чем-то стыдном",
            "Сфоткай свой дневник (можно закрыть текст)",
            "Опиши самый эротичный сон обо мне",
            "Запиши как ты говоришь 'прости' самым искренним голосом",
            "Сфоткай свою ванную комнату",
            "Напиши смс, которое ты бы отправил(а) при расставании",
            "Запиши видео, где танцуешь под медленную музыку",
            "Сфоткай свое отражение в воде",
            "Опиши мое тело в подробностях",
            "Запиши шепотом то, что боишься сказать вслух",
            "Сфоткай свою нижнее белье",
            "Напиши erotic рассказ про нас из 5 предложений",
            "Запиши как ты дышишь в микрофон 10 секунд",
            "Сфоткай свои губы крупным планом",
            "Опиши, как бы ты соблазнял(а) меня",
            "Запиши видео, где показываешь язык",
            "Сфоткай свою шею сзади",
            "Напиши сообщение, которое вызовет у меня мурашки",
            "Запиши как ты стонешь от удовольствия",
            "Сфоткай свои плечи",
            "Опиши мой запах",
            "Запиши видео, где проводишь рукой по своему телу",
            "Сфоткай свои бедра",
            "Напиши, где бы ты хотел(а) меня поцеловать",
            "Запиши звук поцелуя в microphone",
            "Сфоткай свою спину",
            "Опиши, как бы ты меня раздевал(а)",
            "Запиши видео, где закусываешь губу",
            "Сфоткай свои ноги",
            "Напиши, что бы ты сделал(а) со мной в лифте",
            "Запиши как ты произносишь 'возьми меня'",
            "Сфоткай свою грудь через одежду",
            "Опиши мой поцелуй",
            "Запиши видео, где закрываешь глаза и улыбаешься",
            "Сфоткай свой живот",
            "Напиши, где бы ты хотел(а) со мной заняться сексом",
            "Запиши звук своего сердцебиения",
            "Сфоткай свои руки с ракурса снизу",
            "Опиши, какой ты в постели",
            "Запиши видео, где проводишь пальцем по губам",
            "Сфоткай свою кожу крупным планом",
            "Напиши, что ты чувствуешь когда я касаюсь тебя",
            "Запиши как ты произносишь 'я твой/твоя'"
        ]
    },
    3: {
        'truth': [
            "Где самое эротичное место, где ты хочешь меня?",
            "Какая фантазия про нас кажется тебе самой запретной?",
            "Что в сексе ты стесняешься предложить, но очень хочешь?",
            "Какую сексуальную игру ты хочешь попробовать?",
            "Где бы ты кончил(а) на моем теле?",
            "Какая часть моего тела возбуждает тебя больше всего?",
            "Что ты представляешь когда мастурбируешь?",
            "Хочешь ли ты сделать наши интимные фото?",
            "Какой секс с нами был лучшим?",
            "Хочешь ли ты попробовать групповой секс?",
            "Какая поза тебе нравится больше всего?",
            "Что ты хочешь чтобы я сделал(а) с твоим телом?",
            "Где самое необычное место где ты занимался(ась) сексом?",
            "Хочешь ли ты чтобы я доминировал(а) над тобой?",
            "Какая твоя самая грязная фантазия?",
            "Что ты чувствуешь когда я внутри тебя?",
            "Хочешь ли ты сделать видео нашего секса?",
            "Какой оргазм был самым сильным?",
            "Что ты хочешь попробовать в оральном сексе?",
            "Хочешь ли ты секс в общественном месте?",
            "Какая игрушка для секса тебя интересует?",
            "Что тебя возбуждает в моих стонах?",
            "Хочешь ли ты чтобы я связал(а) тебя?",
            "Какой секс без презерватива ты хочешь?",
            "Что ты думаешь о моем вкусе в нижнем белье?",
            "Хочешь ли ты попробовать ролевые игры?",
            "Какая часть твоего тела самая чувствительная?",
            "Что тебя заводит в моем голосе?",
            "Хочешь ли ты чтобы я говорил(а) грязные слова?",
            "Какой секс утром тебе нравится?",
            "Что ты хочешь чтобы я сделал(а) языком?",
            "Хочешь ли ты секс перед зеркалом?",
            "Какая температура должна быть для идеального секса?",
            "Что тебя возбуждает в моих руках?",
            "Хочешь ли ты чтобы я был(а) агрессивнее?",
            "Какой запах моего тела тебя заводит?",
            "Что ты думаешь о моей технике в постели?",
            "Хочешь ли ты попробовать food play?",
            "Какая музыка должна играть во время секса?",
            "Что тебя возбуждает в моих глазах?",
            "Хочешь ли ты чтобы я носил(а) сексуальное белье?",
            "Какой тип ласк тебе нравится больше?",
            "Что ты чувствуешь когда я смотрю на тебя?",
            "Хочешь ли ты чтобы я делал(а) тебе массаж?",
            "Какая фантазия с другим человеком тебя возбуждает?",
            "Что ты думаешь о моей выносливости?",
            "Хочешь ли ты попробовать BDSM?",
            "Какой момент нашего секса ты вспоминаешь?",
            "Что тебя заводит в моей походке?",
            "Хочешь ли ты чтобы я был(а) твоим рабом?"
        ],
        'dare': [
            "Пришли фото своего запястья/шеи/бедра (на выбор) с текстом «Поцелуй сюда»",
            "Опиши словами, что будешь делать, когда мы останемся наедине",
            "Отправь голосовое с тяжёлым дыханием на 10 секунд",
            "Сфоткай свое нижнее белье и пришли",
            "Запиши видео, где проводишь рукой по внутренней стороне бедра",
            "Напиши подробно как ты себя ласкаешь",
            "Сфоткай свою кровать с ракурса как будто ты лежишь",
            "Запиши голосовое со стоном удовольствия",
            "Пришли фото своих губ с помадой/блеском",
            "Опиши какой секс ты хочешь прямо сейчас",
            "Сфоткай свое отражение в зеркале в нижнем белье",
            "Запиши как ты произносишь 'я кончаю'",
            "Пришли фото своей спины без одежды",
            "Напиши где бы ты хотел(а) мои поцелуи",
            "Сфоткай свои ноги с ракурса снизу",
            "Запиши видео, где закусываешь нижнюю губу",
            "Пришли фото своей груди через обтягивающую футболку",
            "Опиши что ты сделаешь с моим телом",
            "Сфоткай свои ягодицы в обтягивающих штанах",
            "Запиши звук поцелуев в свою руку",
            "Пришли фото своего живота с каплями воды",
            "Напиши какие ласки ты хочешь получить",
            "Сфоткай свои бедра в позе лежа",
            "Запиши видео, где медленно раздеваешься (можно до нижнего белья)",
            "Пришли фото своих плеч с поцелуями (нарисуй помадой)",
            "Опиши как ты будешь меня раздевать",
            "Сфоткай свою шею сзади с распущенными волосами",
            "Запиши как ты дышишь в ухо",
            "Пришли фото своих рук с ракурса как будто тянешься",
            "Напиши что ты шепчешь во время секса",
            "Сфоткай свои губы крупно с приоткрытым ртом",
            "Запиши видео, где проводишь языком по губам",
            "Пришли фото своей талии с ремнем/поясом",
            "Опиши какой ты хочешь foreplay",
            "Сфоткай свои колени с ракурса сверху",
            "Запиши как ты произносишь 'давай медленнее'",
            "Пришли фото своих волос рассыпанных по подушке",
            "Напиши где ты хочешь мои руки",
            "Сфоткай свою кожу с каплями пота",
            "Запиши видео, где касаешься своего декольте",
            "Пришли фото своих ногтей на руках с ракурса как ласкаешь",
            "Опиши какой оргазм ты хочешь",
            "Сфоткай свою поясницу/спину в джинсах",
            "Запиши как ты стонешь от прикосновений",
            "Пришли фото своих ресниц с ракурса снизу",
            "Напиши что ты кричишь в оргазме",
            "Сфоткай свою ключицу крупным планом",
            "Запиши видео, где медленно снимаешь носки",
            "Пришли фото своих запястий с часами/браслетом",
            "Опиши как ты кончаешь",
            "Сфоткай свою тень в сексуальной позе"
        ]
    }
}

# База наказаний (30 вариантов)
PUNISHMENTS = [
    "Спой песню о своей неудаче и пришли голосовое",
    "Сделай селфи с самым нелепым лицом",
    "Напиши признание в любви к неодушевлённому предмету",
    "Пришли фото, стоя на одной ноге",
    "Изобрази знаменитость и пришли фото",
    "Расскажи самый неловкий момент из своей жизни",
    "Станцуй танец маленьких утят и пришли видео",
    "Напиши стих про свою неудачу",
    "Сфоткай себя в самой нелепой позе",
    "Запиши голосовое с имитацией животного",
    "Сделай макияж с закрытыми глазами и пришли фото",
    "Спой гимн своей страны фальшиво",
    "Нарисуй свой портрет левой рукой",
    "Сфоткай свой холодильник и опиши что там",
    "Запиши видео как ты ешь лимон",
    "Сделай 20 приседаний и пришли запись дыхания",
    "Напиши объявление о продаже себя",
    "Сфоткай свою обувь с ракурса внутри",
    "Запиши как ты читаешь скороговорку",
    "Сделай прическу как у сумасшедшего ученого",
    "Напиши список своих недостатков",
    "Сфоткай свой беспорядок в комнате",
    "Запиши видео как ты пытаешься сесть на шпагат",
    "Сделай костюм из подручных средств",
    "Напиши критику самому себе",
    "Сфоткай свои старые фотографии",
    "Запиши как ты поешь в душе",
    "Сделай уборку и пришли фото до/после",
    "Напиши инструкцию как быть неудачником",
    "Сфоткай свои носки за неделю",
    "Запиши видео как мастурбируешь (можно через одежду)",
    "Пришли фото голой груди/торса в отражении зеркала",
    "Сними видео как принимаешь душ (можно в купальнике/трусах)",
    "Пришли фото в одних трусах/нижнем белье в соблазнительной позе",
    "Запиши аудио своего оргазма (можно симулировать)",
    "Сфоткай свои ягодицы без одежды при тусклом свете",
    "Пришли фото мокрого тела после душа в полотенце",
    "Запиши видео как наносишь крем/масло на тело",
    "Сфоткай свою промежность через узкое белье",
    "Пришли фото в позе на четвереньках (в одежде или без)",
    "Запиши стоны в подушку в течение 30 секунд",
    "Сфоткай свои губы в момент поцелуя воздуха",
    "Пришли фото спины в позе кошки (прогиб)",
    "Запиши видео как медленно снимаешь футболку",
    "Сфоткай свои ноги раздвинутыми на кровати"
]

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
    question = random.choice(TASKS[level]['truth'])

    partner_data['pending_action'] = f"Правда: {question}"
    db = load_db()
    db[pair_id]['users'][partner_id]['pending_action'] = partner_data['pending_action']
    db[pair_id]['current_turn'] = partner_id
    save_db(db)

    # Клавиатура для получателя задания
    action_keyboard = [['/joker', '/punishment'], ['/status']]
    reply_markup = ReplyKeyboardMarkup(action_keyboard, resize_keyboard=True)
    
    level_names = {1: "❄️", 2: "🌊", 3: "🔥"}
    
    await update.message.reply_text(f"🤔 Правда отправлена для @{partner_data['username']}! Жди ответа.")
    
    await context.bot.send_message(
        chat_id=partner_id,
        text=f"🤔 ДЛЯ ТЕБЯ ПРАВДА! {level_names[level]}\n\n"
             f"Вопрос: {question}\n\n"
             f"📝 Ответ пришли партнеру в общий чат!\n\n"
             f"Если не хочешь отвечать:\n"
             f"• /joker - Пропустить (осталось: {partner_data['jokers']} 🃏)\n"
             f"• /punishment - Получить наказание\n\n"
             f"После ответа жди своего хода!\n"
             f"• /truth - Правда \n\n"
             f"• /dare - Действие",
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
    task = random.choice(TASKS[level]['dare'])

    partner_data['pending_action'] = f"Действие: {task}"
    db = load_db()
    db[pair_id]['users'][partner_id]['pending_action'] = partner_data['pending_action']
    db[pair_id]['current_turn'] = partner_id
    save_db(db)

    # Клавиатура для получателя задания
    action_keyboard = [['/joker', '/punishment'], ['/status']]
    reply_markup = ReplyKeyboardMarkup(action_keyboard, resize_keyboard=True)
    
    level_names = {1: "❄️", 2: "🌊", 3: "🔥"}
    
    await update.message.reply_text(f"🎯 Действие отправлено для @{partner_data['username']}! Жди выполнения.")
    
    await context.bot.send_message(
        chat_id=partner_id,
        text=f"🎯 ДЛЯ ТЕБЯ ДЕЙСТВИЕ! {level_names[level]}\n\n"
             f"Задание: {task}\n\n"
             f"🎬 Выполни и пришли результат партнеру в общий чат!\n\n"
             f"Если не хочешь выполнять:\n"
             f"• /joker - Пропустить (осталось: {partner_data['jokers']} 🃏)\n"
             f"• /punishment - Получить наказание\n\n"
             f"После выполнения жди своего хода!\n"
             f"• /truth - Правда \n\n"
             f"• /dare - Действие",
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
    partner_data = user_data['users'][partner_id]

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

    # Клавиатура для нового хода
    action_keyboard = [['/truth', '/dare'], ['/status']]
    reply_markup = ReplyKeyboardMarkup(action_keyboard, resize_keyboard=True)
    
    await update.message.reply_text("🃏 Джокер использован! Задание пропущено.")
    await context.bot.send_message(
        chat_id=partner_id,
        text=f"🃏 Партнер использовал Джокер! Теперь твой ход.\n\n"
             f"Выбери:\n"
             f"• /truth - Правда\n"
             f"• /dare - Действие\n\n"
             f"Доступно Джокеров: {partner_data['jokers']} 🃏",
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

    # Клавиатура для нового хода
    action_keyboard = [['/truth', '/dare'], ['/status']]
    reply_markup = ReplyKeyboardMarkup(action_keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        f"⚡ ТВОЁ НАКАЗАНИЕ:\n{punishment_text}\n\n"
        f"Выполни и пришли результат партнеру!"
    )
    await context.bot.send_message(
        chat_id=partner_id,
        text=f"⚡ Партнер получил Наказание! Теперь твой ход.\n\n"
             f"Выбери:\n"
             f"• /truth - Правда\n"
             f"• /dare - Действие",
        reply_markup=reply_markup
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data, pair_id = get_user_data(user_id)

    if not user_data:
        await update.message.reply_text("❌ Ты не в игре! Напиши /register_partner @username")
        return

    partner_id = [uid for uid in user_data['users'].keys() if uid != str(user_id)][0]
    partner_data = user_data['users'][partner_id]
    partner_username = partner_data['username']

    level_names = {
        1: "❄️ Лёд тронулся (лёгкий)",
        2: "🌊 Бездонное озеро (средний)", 
        3: "🔥 Вулкан страсти (18+)"
    }
    current_level = level_names[user_data['level']]

    current_turn = "✅ Твой ход! 🎮" if user_data['current_turn'] == str(user_id) else f"⏳ Очередь @{partner_username}"
    
    jokers_you = user_data['users'][str(user_id)]['jokers']
    jokers_partner = partner_data['jokers']
    
    pending_action = user_data['users'][str(user_id)]['pending_action']
    action_status = f"📋 Задание: {pending_action}" if pending_action else "📋 Задания нет"

    status_text = (
        f"📊 СТАТУС ИГРЫ:\n\n"
        f"• Партнер: @{partner_username}\n"
        f"• Уровень: {current_level}\n"
        f"• {current_turn}\n"
        f"• Твои Джокеры: {jokers_you} 🃏\n"
        f"• Джокеры партнера: {jokers_partner} 🃏\n"
        f"• {action_status}\n\n"
        f"Команды:\n"
        f"• /game - ход\n"
        f"• /joker - пропустить\n"
        f"• /punishment - наказание\n"
        f"• /level - сменить уровень"
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