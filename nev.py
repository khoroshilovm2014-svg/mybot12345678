import json
import sys
import asyncio
import random
import string
import io
from datetime import datetime, timedelta
import os
print("ТЕКУЩАЯ ПАПКА:", os.getcwd())
print("ФАЙЛЫ JSON В ПАПКЕ:")
for file in os.listdir('.'):
    if file.endswith('.json'):
        print(f"  - {file}")

try:
    from captcha.image import ImageCaptcha
except ImportError:
    print("❌ ОШИБКА: Не установлена библиотека captcha. Выполните: pip install captcha")
    sys.exit()

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, CallbackContext
from telegram.error import BadRequest, Forbidden

print("Python version:", sys.version)
print("=" * 50)

# --- КОНФИГУРАЦИЯ ---
DATA_FILE = "data.json"
SUPER_ADMIN_IDS = [7635015201] 
TOKEN = "8363126247:AAF7fbawYxeL7-LsI2Kk0BKFNLfdND32Lr0"

# ПРАВА ДОСТУПА
PERM_BAN = 'ban_users'
PERM_BROADCAST = 'broadcast'
PERM_ACCS = 'manage_accs'
PERM_PROMOS = 'manage_promos'
PERM_CHANNELS = 'manage_channels'
PERM_ADD_ADMIN = 'add_admin'
PERM_SETTINGS = 'manage_settings'
PERM_REVIEWS = 'moderate_reviews'

DEFAULT_PERMISSIONS = {
    PERM_BAN: True,
    PERM_BROADCAST: True,
    PERM_ACCS: True,
    PERM_PROMOS: True,
    PERM_CHANNELS: True,
    PERM_ADD_ADMIN: True,
    PERM_SETTINGS: True,
    PERM_REVIEWS: True
}

# ИГРЫ
GAME_TANKS = 'tanks'
GAME_BLITZ = 'blitz'
GAME_NAMES = {
    GAME_TANKS: "TanksBlitz",
    GAME_BLITZ: "WoT Blitz"
}

# Флаг остановки бота
BOT_STOPPED = False

# Структура данных по умолчанию
DEFAULT_DATA = {
    "accounts_common_tanks": [],
    "accounts_promo_tanks": [],
    "accounts_common_blitz": [],
    "users": {}, 
    "channels": [],
    "admins": {},
    "promocodes": {}, 
    "reviews": [],
    "pending_reviews": [],
    "banned_users": [],
    "failed_deliveries": {},
    "settings": {
        "coin_reward": 1,
        "exchange_price": 10,
        "faq_text": """ℹ️ FAQ

🔹 Лимит: 1 бесплатный аккаунт в 24 часа.
🔹 Монеты: Даются ТОЛЬКО за приглашение друзей.
🔹 Условия: Друг должен перейти по вашей ссылке и пройти регистрацию И подписаться на каналы.
🔹 Награда: 1 монета за друга (начисляется после подписки на каналы).
🔹 Обмен: 10 монет = 1 аккаунт.
🔹 Промокоды: Дают аккаунты бесплатно (только из TanksBlitz).
🔹 Поддержка: @texpoddergka2026_bot""",
        "faq_entities": None
    }
}

# Глобальная переменная данных
data = DEFAULT_DATA.copy()

def load_data():
    """Загружает данные из data.json"""
    global data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                # Рекурсивно обновляем данные, сохраняя структуру
                update_nested_dict(data, loaded_data)
            print(f"✅ Данные загружены из {DATA_FILE}")
            return True
        except Exception as e:
            print(f"❌ Ошибка загрузки данных: {e}")
            return False
    else:
        print(f"ℹ️ Файл {DATA_FILE} не найден, будет создан при сохранении")
        save_data()
        return True

def update_nested_dict(original, updates):
    """Рекурсивно обновляет вложенный словарь"""
    for key, value in updates.items():
        if key in original:
            if isinstance(original[key], dict) and isinstance(value, dict):
                update_nested_dict(original[key], value)
            else:
                original[key] = value
        else:
            original[key] = value

def save_data():
    """Сохраняет данные в data.json"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        print(f"❌ Ошибка сохранения данных: {e}")
        return False

def save():
    """Прокси-функция для сохранения (совместимость со старым кодом)"""
    return save_data()

def is_admin(user_id: int) -> bool:
    if user_id in SUPER_ADMIN_IDS:
        return True
    return str(user_id) in data.get("admins", {})

def check_perm(user_id: int, perm: str) -> bool:
    if user_id in SUPER_ADMIN_IDS:
        return True
    admin_data = data.get("admins", {}).get(str(user_id))
    if not admin_data: return False
    return admin_data.get("permissions", {}).get(perm, False)

def get_user_link(user):
    if hasattr(user, 'id'):
        return f'<a href="tg://user?id={user.id}">{user.full_name}</a> (ID: <code>{user.id}</code>)'
    return f'<a href="tg://user?id={user}">Пользователь</a> (ID: <code>{user}</code>)'

async def notify_super_admins(context: CallbackContext, text: str):
    if not SUPER_ADMIN_IDS:
        return
    
    for owner_id in SUPER_ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=owner_id,
                text=f"🔔 Уведомление\n\n{text}",
                parse_mode='HTML'
            )
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"Ошибка отправки уведомления {owner_id}: {e}")

def generate_captcha():
    image = ImageCaptcha(width=280, height=90)
    captcha_text = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
    data_img = image.generate(captcha_text)
    return captcha_text, data_img

def menu(user_id: int):
    kb = [
        ["🎮 Получить аккаунт", "📜 История"],
        ["💎 Обменять монеты", "🎟 Промокод"],
        ["ℹ️ О боте", "⭐ Отзывы"],
        ["✅ Проверить подписку", "👤 Мой профиль"]
    ]
    if is_admin(user_id):
        kb.append(["👑 Админ"])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def reviews_keyboard():
    keyboard = [
        [InlineKeyboardButton("📝 Посмотреть отзывы", callback_data="view_reviews")],
        [InlineKeyboardButton("⭐ Оставить отзыв", callback_data="leave_review")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_sub_keyboard(channels_list):
    kb = []
    for ch in channels_list:
        url = ch
        if ch.startswith("@"):
            url = f"https://t.me/{ch[1:]}"
        elif "t.me" not in ch:
            url = f"https://t.me/{ch}"
        kb.append([InlineKeyboardButton(f"Подписаться", url=url)])
    kb.append([InlineKeyboardButton("✅ Я подписался", callback_data="check_sub_confirm")])
    return InlineKeyboardMarkup(kb)

def exchange_keyboard():
    kb = [
        [InlineKeyboardButton("💎 Обменять монеты", callback_data="exchange_coins")],
        [InlineKeyboardButton("❌ Отмена", callback_data="delete_msg")]
    ]
    return InlineKeyboardMarkup(kb)

def game_selection_keyboard():
    kb = [
        [InlineKeyboardButton("• TanksBlitz", callback_data=f"select_game_{GAME_TANKS}")],
        [InlineKeyboardButton("• WoT Blitz", callback_data=f"select_game_{GAME_BLITZ}")]
    ]
    return InlineKeyboardMarkup(kb)

def admin_kb_main(user_id):
    status_icon = "▶️" if not BOT_STOPPED else "⏸"
    
    if user_id in SUPER_ADMIN_IDS:
        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")],
            [
                InlineKeyboardButton("📦 Аккаунты", callback_data="admin_menu_accs"),
                InlineKeyboardButton("🎟 Промокоды", callback_data="admin_menu_promo")
            ],
            [
                InlineKeyboardButton("⭐ Отзывы", callback_data="admin_menu_reviews"),
                InlineKeyboardButton("👥 Пользователи", callback_data="admin_menu_users")
            ],
            [
                InlineKeyboardButton("📣 Рассылка", callback_data="admin_broadcast_start"),
                InlineKeyboardButton("✉️ ЛС", callback_data="admin_pm")
            ],
            [
                InlineKeyboardButton("📢 Каналы", callback_data="admin_menu_channels"),
                InlineKeyboardButton("🛡 Админы", callback_data="admin_menu_admins")
            ],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="admin_menu_settings")],
            [InlineKeyboardButton(f"{status_icon} Стоп/Старт Бот", callback_data="admin_toggle_bot")],
            [InlineKeyboardButton("❌ Закрыть", callback_data="admin_close")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    kb = []
    kb.append([InlineKeyboardButton("📊 Полная Статистика", callback_data="admin_stats")])
    
    row2 = []
    if check_perm(user_id, PERM_ACCS):
        row2.append(InlineKeyboardButton("📦 Аккаунты", callback_data="admin_menu_accs"))
    if check_perm(user_id, PERM_PROMOS):
        row2.append(InlineKeyboardButton("🎟 Промокоды", callback_data="admin_menu_promo"))
    if row2: 
        kb.append(row2)

    row3 = []
    if check_perm(user_id, PERM_REVIEWS):
        row3.append(InlineKeyboardButton("⭐ Отзывы", callback_data="admin_menu_reviews"))
    if check_perm(user_id, PERM_BAN):
        row3.append(InlineKeyboardButton("👥 Пользователи", callback_data="admin_menu_users"))
    if row3: 
        kb.append(row3)

    row4 = []
    if check_perm(user_id, PERM_BROADCAST):
        row4.append(InlineKeyboardButton("📣 Рассылка", callback_data="admin_broadcast_start"))
    row4.append(InlineKeyboardButton("✉️ ЛС", callback_data="admin_pm"))
    if row4: 
        kb.append(row4)

    row5 = []
    if check_perm(user_id, PERM_CHANNELS):
        row5.append(InlineKeyboardButton("📢 Каналы", callback_data="admin_menu_channels"))
    if check_perm(user_id, PERM_ADD_ADMIN):
        row5.append(InlineKeyboardButton("🛡 Админы", callback_data="admin_menu_admins"))
    if row5: 
        kb.append(row5)

    if check_perm(user_id, PERM_SETTINGS):
        kb.append([InlineKeyboardButton("⚙️ Настройки", callback_data="admin_menu_settings")])

    kb.append([InlineKeyboardButton(f"{status_icon} Стоп/Старт Бот", callback_data="admin_toggle_bot")])
    kb.append([InlineKeyboardButton("❌ Закрыть", callback_data="admin_close")])
    
    return InlineKeyboardMarkup(kb)

def admin_kb_accounts():
    total_accounts = (len(data['accounts_common_tanks']) + len(data['accounts_promo_tanks']) +
                     len(data['accounts_common_blitz']))
    
    text = f"""📦 Управление аккаунтами

📊 Статистика аккаунтов:
• Всего аккаунтов в наличии: {total_accounts}
• TanksBlitz (Общая): {len(data['accounts_common_tanks'])} шт.
• TanksBlitz (Промо): {len(data['accounts_promo_tanks'])} шт.
• WoT Blitz (Общая): {len(data['accounts_common_blitz'])} шт.

Выберите действие:"""
    
    kb = [
        [InlineKeyboardButton("🔄 Загрузить (TXT)", callback_data="admin_acc_load")],
        [InlineKeyboardButton("🎯 Выбрать игру", callback_data="admin_select_game")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_main")]
    ]
    return InlineKeyboardMarkup(kb)

def admin_kb_acc_game_selection():
    kb = [
        [InlineKeyboardButton("• TanksBlitz", callback_data=f"admin_game_{GAME_TANKS}")],
        [InlineKeyboardButton("• WoT Blitz", callback_data=f"admin_game_{GAME_BLITZ}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_menu_accs")]
    ]
    return InlineKeyboardMarkup(kb)

def admin_kb_acc_actions_for_game(game):
    game_name = GAME_NAMES[game]
    
    if game == GAME_TANKS:
        kb = [
            [InlineKeyboardButton(f"📦 Загрузить в Общую ({game_name})", callback_data=f"upload_to_common_{game}")],
            [InlineKeyboardButton(f"🎟 Загрузить в Промо ({game_name})", callback_data=f"upload_to_promo_{game}")],
            [InlineKeyboardButton(f"❌ Удалить ВСЕ Общие ({game_name})", callback_data=f"admin_acc_del_common_{game}")],
            [InlineKeyboardButton(f"❌ Удалить ВСЕ Промо ({game_name})", callback_data=f"admin_acc_del_promo_{game}")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_menu_accs")]
        ]
    else:
        kb = [
            [InlineKeyboardButton(f"📦 Загрузить в Общую ({game_name})", callback_data=f"upload_to_common_{game}")],
            [InlineKeyboardButton(f"❌ Удалить ВСЕ Общие ({game_name})", callback_data=f"admin_acc_del_common_{game}")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_menu_accs")]
        ]
    return InlineKeyboardMarkup(kb)

def admin_kb_settings():
    kb = [
        [InlineKeyboardButton("💰 Изменить цену аккаунта", callback_data="set_price")],
        [InlineKeyboardButton("🤝 Изменить награду за реферала", callback_data="set_reward")],
        [InlineKeyboardButton("📝 Изменить текст FAQ", callback_data="set_faq")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_main")]
    ]
    return InlineKeyboardMarkup(kb)

def admin_kb_promo_source_choice():
    kb = [
        [InlineKeyboardButton("📦 С ОБЩЕЙ базы (TanksBlitz)", callback_data="promo_src_common")],
        [InlineKeyboardButton("🎟 С ПРОМО базы (TanksBlitz)", callback_data="promo_src_promo")],
        [InlineKeyboardButton("❌ Отмена", callback_data="admin_main")]
    ]
    return InlineKeyboardMarkup(kb)

def admin_kb_channels():
    kb = [
        [InlineKeyboardButton("➕ Добавить канал", callback_data="admin_channel_add")],
        [InlineKeyboardButton("➖ Удалить канал", callback_data="admin_channel_del")],
        [InlineKeyboardButton("📋 Список каналов", callback_data="admin_channel_list")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_main")]
    ]
    return InlineKeyboardMarkup(kb)

def admin_kb_admins_list():
    kb = []
    for adm_id, adm_data in data.get("admins", {}).items():
        name = adm_data.get("name", f"ID: {adm_id}")
        kb.append([InlineKeyboardButton(f"👤 {name}", callback_data=f"adm_edit:{adm_id}")])
    kb.append([InlineKeyboardButton("➕ Назначить админа", callback_data="admin_add_new")])
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_main")])
    return InlineKeyboardMarkup(kb)

def admin_kb_admin_rights(target_id):
    perms = data.get("admins", {}).get(str(target_id), {}).get("permissions", {})
    def p_btn(key, text):
        status = "✅" if perms.get(key, False) else "❌"
        return InlineKeyboardButton(f"{status} {text}", callback_data=f"adm_toggle:{target_id}:{key}")
    kb = [
        [p_btn(PERM_ACCS, "Аккаунты"), p_btn(PERM_PROMOS, "Промо")],
        [p_btn(PERM_BAN, "Бан"), p_btn(PERM_BROADCAST, "Рассылка")],
        [p_btn(PERM_CHANNELS, "Каналы"), p_btn(PERM_ADD_ADMIN, "Админы")],
        [p_btn(PERM_SETTINGS, "Настройки"), p_btn(PERM_REVIEWS, "Модерация")],
        [InlineKeyboardButton("🗑 УДАЛИТЬ АДМИНА", callback_data=f"adm_delete:{target_id}")],
        [InlineKeyboardButton("🔙 К списку", callback_data="admin_menu_admins")]
    ]
    return InlineKeyboardMarkup(kb)

def admin_kb_promo():
    kb = [
        [InlineKeyboardButton("🎟 Создать промокод", callback_data="admin_promo_create")],
        [InlineKeyboardButton("📋 Список активных", callback_data="admin_promo_list")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_main")]
    ]
    return InlineKeyboardMarkup(kb)

def admin_kb_reviews():
    kb = [
        [InlineKeyboardButton("📝 Модерация отзывов", callback_data="admin_review_moderate")],
        [InlineKeyboardButton("📋 Читать все", callback_data="admin_review_all")],
        [InlineKeyboardButton("🗑 Очистить ВСЕ", callback_data="admin_review_clear_all")],
        [InlineKeyboardButton("❌ Удалить по номеру", callback_data="admin_review_del_one")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_main")]
    ]
    return InlineKeyboardMarkup(kb)

def admin_kb_users():
    kb = [
        [InlineKeyboardButton("⛔ Забанить ID", callback_data="admin_user_ban")],
        [InlineKeyboardButton("✅ Разбанить ID", callback_data="admin_user_unban")],
        [InlineKeyboardButton("🔙 Назад", callback_data="admin_main")]
    ]
    return InlineKeyboardMarkup(kb)

def broadcast_add_btn_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить кнопку", callback_data="bc_add_btn_yes")],
        [InlineKeyboardButton("➡️ Нет, далее", callback_data="bc_add_btn_no")]
    ])

def broadcast_confirm_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 ЗАПУСТИТЬ", callback_data="bc_confirm_send")],
        [InlineKeyboardButton("✏️ Изм. сообщение", callback_data="bc_edit_msg")],
        [InlineKeyboardButton("✏️ Изм. кнопку", callback_data="bc_add_btn_yes")],
        [InlineKeyboardButton("❌ Отмена", callback_data="admin_main")]
    ])

def back_btn(callback_data="admin_main"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data=callback_data)]])

def moderation_review_kb(review_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"mod_approve:{review_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"mod_reject:{review_id}")
        ],
        [InlineKeyboardButton("📋 К списку", callback_data="admin_review_moderate")]
    ])

def admin_kb_review_moderation():
    pending_count = len(data["pending_reviews"])
    approved_count = len(data["reviews"])
    
    kb = []
    
    if pending_count > 0:
        kb.append([InlineKeyboardButton(f"⏳ Ожидают ({pending_count})", callback_data="mod_view_pending")])
    
    kb.append([InlineKeyboardButton(f"✅ Опубликованные ({approved_count})", callback_data="mod_view_approved")])
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_menu_reviews")])
    
    return InlineKeyboardMarkup(kb)

# ========== ФУНКЦИИ ДЛЯ РАССЫЛКИ (С ФОРМАТИРОВАНИЕМ) ==========
async def handle_broadcast_content(update: Update, context: CallbackContext):
    """Обработка контента для рассылки с сохранением форматирования"""
    msg = update.message
    
    context.user_data["broadcast_msg_id"] = msg.message_id
    context.user_data["broadcast_chat_id"] = msg.chat_id
    
    if msg.text:
        context.user_data["broadcast_text"] = msg.text
        context.user_data["broadcast_entities"] = msg.entities
        context.user_data["broadcast_has_media"] = False
    elif msg.caption:
        context.user_data["broadcast_text"] = msg.caption
        context.user_data["broadcast_entities"] = msg.caption_entities
        context.user_data["broadcast_has_media"] = True
    elif msg.photo or msg.video or msg.document or msg.audio or msg.voice:
        context.user_data["broadcast_has_media"] = True
        context.user_data["broadcast_entities"] = msg.caption_entities
    
    await msg.reply_text("✅ Контент получен. Добавить кнопку с ссылкой?", reply_markup=broadcast_add_btn_kb())
    context.user_data["broadcast_step"] = "wait_decision"

async def show_broadcast_preview(update: Update, context: CallbackContext):
    """Показать предпросмотр рассылки с форматированием"""
    chat_id = context.user_data.get("broadcast_chat_id")
    msg_id = context.user_data.get("broadcast_msg_id")
    
    kb = None
    if "broadcast_buttons" in context.user_data and context.user_data["broadcast_buttons"]:
        kb = InlineKeyboardMarkup(context.user_data["broadcast_buttons"])
        
    await update.effective_message.reply_text("📢 ПРЕДПРОСМОТР РАССЫЛКИ:")
    
    try:
        if "broadcast_text" in context.user_data:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=context.user_data["broadcast_text"],
                entities=context.user_data.get("broadcast_entities"),
                reply_markup=kb
            )
        elif chat_id and msg_id and context.user_data.get("broadcast_has_media"):
            await context.bot.copy_message(
                chat_id=update.effective_chat.id,
                from_chat_id=chat_id,
                message_id=msg_id,
                reply_markup=kb
            )
        else:
            await update.effective_message.reply_text("❌ Ошибка: данные рассылки не найдены")
            return
    except Exception as e:
        await update.effective_message.reply_text(f"Ошибка предпросмотра: {e}")
        
    await update.effective_message.reply_text("Запустить рассылку?", reply_markup=broadcast_confirm_kb())
    context.user_data["broadcast_step"] = "confirm"

async def start_broadcast(update: Update, context: CallbackContext):
    """Запуск рассылки с сохранением форматирования"""
    query = update.callback_query
    await query.edit_message_text("🚀 Рассылка запущена! Это может занять время...")
    
    chat_id = context.user_data.get("broadcast_chat_id")
    msg_id = context.user_data.get("broadcast_msg_id")
    
    kb = None
    if "broadcast_buttons" in context.user_data and context.user_data["broadcast_buttons"]:
        kb = InlineKeyboardMarkup(context.user_data["broadcast_buttons"])
        
    count = 0
    block_count = 0
    error_count = 0
    skipped_count = 0
    
    users = list(data["users"].keys())
    total_users = len(users)
    
    progress_msg = await query.message.reply_text(f"📊 Рассылка начата...\nОбработано: 0/{total_users}")
    
    for i, uid in enumerate(users, 1):
        if i % 50 == 0:
            try:
                await progress_msg.edit_text(f"📊 Рассылка в процессе...\nОбработано: {i}/{total_users}\nОтправлено: {count}")
            except:
                pass
        
        if uid in data.get("failed_deliveries", {}):
            skipped_count += 1
            continue
            
        try:
            if "broadcast_text" in context.user_data:
                await context.bot.send_message(
                    chat_id=int(uid),
                    text=context.user_data["broadcast_text"],
                    entities=context.user_data.get("broadcast_entities"),
                    reply_markup=kb
                )
            elif chat_id and msg_id and context.user_data.get("broadcast_has_media"):
                await context.bot.copy_message(
                    chat_id=int(uid),
                    from_chat_id=chat_id,
                    message_id=msg_id,
                    reply_markup=kb
                )
            else:
                error_count += 1
                continue
                
            count += 1
            await asyncio.sleep(0.05)
        except Forbidden:
            block_count += 1
            if "failed_deliveries" not in data:
                data["failed_deliveries"] = {}
            data["failed_deliveries"][uid] = datetime.now().isoformat()
        except Exception as e:
            error_count += 1
            if "failed_deliveries" not in data:
                data["failed_deliveries"] = {}
            data["failed_deliveries"][uid] = datetime.now().isoformat()
    
    save()
    
    try:
        await progress_msg.delete()
    except:
        pass
    
    await notify_super_admins(
        context,
        f"📣 ВЫПОЛНЕНА РАССЫЛКА\nКем: {get_user_link(query.from_user)}\nОтправлено: {count} пользователям\nЗаблокировали бота: {block_count}\nОшибок: {error_count}\nПропущено: {skipped_count}\nВсего в базе: {total_users}"
    )
    
    await query.edit_message_text(
        f"✅ Рассылка завершена!\n\n📊 Статистика:\n• Отправлено: {count}\n• Заблокировали бота: {block_count}\n• Ошибок: {error_count}\n• Пропущено: {skipped_count}\n• Всего в базе: {total_users}"
    )
    
    for key in ["broadcast_step", "broadcast_msg_id", "broadcast_chat_id", 
                "broadcast_btn_text", "broadcast_btn_url", "broadcast_text",
                "broadcast_buttons", "broadcast_has_media", "broadcast_entities"]:
        if key in context.user_data:
            del context.user_data[key]

# ========== FAQ С ФОРМАТИРОВАНИЕМ ==========
async def about_bot(update: Update, context: CallbackContext):
    """Показывает FAQ с сохраненным форматированием"""
    await update.message.reply_text(
        data["settings"]["faq_text"],
        entities=data["settings"].get("faq_entities"),
        reply_markup=menu(update.effective_user.id)
    )

async def save_faq(update: Update, context: CallbackContext):
    """Сохраняет FAQ с форматированием"""
    msg = update.message
    data["settings"]["faq_text"] = msg.text
    data["settings"]["faq_entities"] = msg.entities
    save()
    await notify_super_admins(context, f"📝 ИЗМЕНЕН ТЕКСТ FAQ\nКем: {get_user_link(update.effective_user)}\nДлина текста: {len(msg.text)} символов")
    await msg.reply_text("✅ Текст FAQ обновлен! Предпросмотр:", reply_markup=back_btn("admin_menu_settings"))
    await msg.reply_text(msg.text, entities=msg.entities)
    context.user_data["setting_faq"] = False

# ========== ОСТАЛЬНЫЕ ФУНКЦИИ БОТА ==========
async def start(update: Update, context: CallbackContext):
    global BOT_STOPPED
    if BOT_STOPPED and not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Бот временно остановлен.")
        return

    user = update.effective_user
    user_id = str(user.id)
    
    new_referrer = None
    if context.args and len(context.args) > 0:
        possible_id = context.args[0]
        if possible_id != user_id and possible_id in data["users"]:
            new_referrer = possible_id

    # СОЗДАНИЕ ПОЛЬЗОВАТЕЛЯ (если новый)
    if user_id not in data["users"]:
        data["users"][user_id] = {
            "name": user.full_name,
            "username": user.username,
            "coins": 0,
            "received": 0,
            "used_promocodes": [],
            "history": [],
            "join_date": datetime.now().isoformat(),
            "referrer_id": None,
            "captcha_passed": True,
            "pending_referral": None,
            "coins_pending_approval": False,
            "last_receive": None
        }
        save()
        print(f"✅ Создан новый пользователь {user_id}")
        
        if new_referrer:
            data["users"][user_id]["referrer_id"] = new_referrer
            data["users"][user_id]["pending_referral"] = new_referrer
            save()
            
            await notify_super_admins(
                context,
                f"👤 НОВЫЙ ПОЛЬЗОВАТЕЛЬ ПО РЕФЕРАЛУ!\nИмя: {get_user_link(user)}\nПригласил: {new_referrer}"
            )
        else:
            await notify_super_admins(
                context,
                f"👤 НОВЫЙ ПОЛЬЗОВАТЕЛЬ!\nИмя: {get_user_link(user)}"
            )

    user_data = data["users"][user_id]

    # Проверка капчи
    if not user_data.get("captcha_passed", False):
        captcha_text, captcha_image = generate_captcha()
        context.user_data["captcha_correct"] = captcha_text
        context.user_data["awaiting_captcha"] = True
        captcha_image.seek(0)
        await update.message.reply_photo(
            photo=captcha_image,
            caption="🔒 Проверка на бота\nВведите код с картинки, чтобы продолжить:"
        )
        return
    
    # Обработка реферала после капчи
    if context.user_data.get("just_passed_captcha"):
        del context.user_data["just_passed_captcha"]
        
        ref_id = user_data.get("referrer_id")
        
        if ref_id and ref_id in data["users"]:
            is_sub, not_sub_list = await check_subscription_logic(user.id, context)
            
            if is_sub:
                reward = data["settings"]["coin_reward"]
                data["users"][ref_id]["coins"] += reward
                
                if "pending_referral" in data["users"][user_id]:
                    del data["users"][user_id]["pending_referral"]
                
                try:
                    await context.bot.send_message(
                        chat_id=int(ref_id),
                        text=f"💰 Реферальный бонус начислен!\nПо вашей ссылке зарегистрировался новый пользователь: {user.full_name}\nВам начислено: {reward} монет."
                    )
                except: 
                    pass
                
                await notify_super_admins(
                    context,
                    f"🤝 РЕФЕРАЛЬНОЕ НАЧИСЛЕНИЕ\nРефовод: {ref_id}\nРеферал: {get_user_link(user)}\nНачислено: {reward} монет"
                )
            else:
                data["users"][user_id]["coins_pending_approval"] = True
                
                try:
                    await context.bot.send_message(
                        chat_id=int(ref_id),
                        text=f"⏳ Реферальный бонус ожидает подтверждения\nПо вашей ссылке зарегистрировался новый пользователь: {user.full_name}\nМонеты будут начислены после того, как пользователь подпишется на все каналы."
                    )
                except:
                    pass
                
                await notify_super_admins(
                    context,
                    f"⏳ ОЖИДАЕТСЯ ПОДТВЕРЖДЕНИЕ РЕФЕРАЛА\nРефовод: {ref_id}\nРеферал: {get_user_link(user)}\nСтатус: Ожидает подписки на каналы"
                )
            
            save()

    await send_main_menu(update, context)

async def send_main_menu(update: Update, context: CallbackContext):
    user = update.effective_user
    user_id = str(user.id)
    coin_reward = data["settings"]["coin_reward"]
    exchange_price = data["settings"]["exchange_price"]

    pending_message = ""
    user_data = data["users"][user_id]
    if user_data.get("coins_pending_approval", False):
        pending_message = "\n\n⚠️ У вас есть ожидающие начисления монеты!\nПодпишитесь на все каналы через '✅ Проверить подписку', чтобы получить реферальные монеты."

    text = f"""🎮 Добро пожаловать!

🤖 Я бот по бесплатной раздаче аккаунтов!

🔹 Лимит: 1 аккаунт в 24 часа.
🔹 Монеты: Зарабатываются ТОЛЬКО приглашением друзей!
🔹 Рефералка: {coin_reward} монета за друга (начисляется только после подписки на все каналы).
🔹 Обмен: {exchange_price} монет = 1 аккаунт.

🔗 Ваша реферальная ссылка:
https://t.me/{context.bot.username}?start={user_id}{pending_message}

Выберите действие из меню ниже:"""

    if update.message:
        await update.message.reply_text(text, reply_markup=menu(user.id))
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=menu(user.id))

async def panel_command(update: Update, context: CallbackContext):
    user = update.effective_user
    if is_admin(user.id):
        await update.message.reply_text("👑 Админ панель\nВыберите раздел:", reply_markup=admin_kb_main(user.id))
    else:
        await update.message.reply_text("❌ У вас нет доступа.", reply_markup=menu(user.id))

async def user_info_command(update: Update, context: CallbackContext):
    if not is_admin(update.effective_user.id): 
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
    
    if context.args:
        target_id = context.args[0]
        
        if target_id in data["users"]:
            user_data = data["users"][target_id]
            
            history = user_data.get('history', [])
            if history:
                last_activity = datetime.fromisoformat(history[-1]["date"]).strftime('%d.%m.%Y %H:%M')
            else:
                last_activity = "Никогда"
            
            tanks_count = sum(1 for item in history if item.get("game") == GAME_TANKS)
            blitz_count = sum(1 for item in history if item.get("game") == GAME_BLITZ)
            
            referrer_id = user_data.get("referrer_id", "Нет")
            pending_ref = user_data.get("pending_referral", "Нет")
            coins_pending = "✅" if user_data.get("coins_pending_approval") else "❌"
            
            info = f"""📊 СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ

👤 Основная информация:
🆔 ID: {target_id}
👤 Имя: {user_data['name']}
📅 Дата регистрации: {datetime.fromisoformat(user_data['join_date']).strftime('%d.%m.%Y %H:%M')}
🕐 Последняя активность: {last_activity}
👥 Реферер: {referrer_id}
⏳ Ожидающий реферер: {pending_ref}
💎 Монеты ожидают: {coins_pending}

💰 Экономика:
💎 Монеты: {user_data['coins']}
🎮 Всего получено аккаунтов: {user_data['received']}
🎟 Использовано промокодов: {len(user_data.get('used_promocodes', []))}

🎮 Статистика по играм:
• TanksBlitz: {tanks_count} аккаунтов
• WoT Blitz: {blitz_count} аккаунтов

📜 История (последние 5 аккаунтов):"""
            
            if history:
                for i, item in enumerate(history[-5:], 1):
                    date = datetime.fromisoformat(item["date"]).strftime('%d.%m.%Y %H:%M')
                    game = GAME_NAMES.get(item.get("game", GAME_TANKS), "Unknown")
                    acc_type = "🎁 Бесплатно" if item.get("type") == "daily_free" else ("💎 За монеты" if item.get("type") == "exchange" else "🎟 Промокод")
                    info += f"\n{i}. {date} | {game} | {acc_type}\n   {item['account']}"
            else:
                info += "\n📭 История пуста"
            
            if target_id in data.get("failed_deliveries", {}):
                last_fail = datetime.fromisoformat(data["failed_deliveries"][target_id]).strftime('%d.%m.%Y %H:%M')
                info += f"\n\n🚫 Ошибки доставки:\nПоследняя ошибка: {last_fail}"
            
            info += f"\n\n🔨 Статус: {'⛔ ЗАБАНЕН' if target_id in data.get('banned_users', []) else '✅ АКТИВЕН'}"
            
            await update.message.reply_text(info)
        else:
            await update.message.reply_text(f"❌ Пользователь с ID {target_id} не найден.")
    else:
        await update.message.reply_text(
            "ℹ️ Использование команды:\n/info ID_ПОЛЬЗОВАТЕЛЯ\n\n📌 Пример:\n/info 123456789"
        )

async def get_account(update: Update, context: CallbackContext):
    global BOT_STOPPED
    if BOT_STOPPED and not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Бот временно остановлен.")
        return

    user = update.effective_user
    user_id = str(user.id)

    if user_id in data.get("banned_users", []):
        await update.message.reply_text("❌ Вы заблокированы.")
        return

    is_sub, not_sub_list = await check_subscription_logic(user.id, context)
    if not is_sub:
        await update.message.reply_text(
            f"🛑 Доступ ограничен!\n\nДля получения аккаунтов необходимо подписаться на наших спонсоров:",
            reply_markup=get_sub_keyboard(not_sub_list)
        )
        return

    user_data = data["users"][user_id]
    
    if user_data.get("last_receive"):
        last_time = datetime.fromisoformat(user_data["last_receive"])
        if datetime.now() - last_time < timedelta(hours=24):
            next_time = last_time + timedelta(hours=24)
            wait = next_time - datetime.now()
            hours = wait.seconds // 3600
            minutes = (wait.seconds % 3600) // 60
            await update.message.reply_text(
                f"⏰ Лимит: 1 аккаунт в 24 часа\n\nСледующий аккаунт можно получить через:\n{hours} часов {minutes} минут",
                reply_markup=menu(user.id)
            )
            return

    await update.message.reply_text(
        "🎮 Выберите игру для получения аккаунта:\n\n👇 Нажмите на кнопку с нужной игрой:",
        reply_markup=game_selection_keyboard()
    )
    context.user_data["awaiting_game_selection"] = True
    context.user_data["awaiting_account_action"] = "get"

async def process_game_selection(update: Update, context: CallbackContext, game):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id = str(user.id)
    user_data = data["users"][user_id]
    
    game_accounts = data.get(f"accounts_common_{game}", [])
    
    if not game_accounts:
        await query.edit_message_text(f"❌ В базе {GAME_NAMES[game]} пока нет аккаунтов. Попробуйте позже.")
        await context.bot.send_message(chat_id=user.id, text="Возвращаю меню...", reply_markup=menu(user.id))
        return

    account = game_accounts.pop(0)
    data[f"accounts_common_{game}"] = game_accounts

    user_data["received"] += 1
    user_data["last_receive"] = datetime.now().isoformat()
    user_data["history"] = user_data.get("history", []) + [{
        "date": datetime.now().isoformat(),
        "account": account,
        "type": "daily_free",
        "game": game
    }]
    
    await notify_super_admins(
        context,
        f"🎁 ВЫДАН БЕСПЛАТНЫЙ АККАУНТ\nКому: {get_user_link(user)}\nИгра: {GAME_NAMES[game]}\nАккаунт: {account}"
    )

    save()

    await query.edit_message_text(
        f"✅ Аккаунт получен!\n\n🎮 Игра: {GAME_NAMES[game]}\n🔐 {account}\n\n⚠️ Следующий через 24 часа\n💡 Приглашай друзей, чтобы получать монеты!"
    )
    await context.bot.send_message(chat_id=user.id, text="Выберите действие:", reply_markup=menu(user.id))

async def exchange_coins(update: Update, context: CallbackContext):
    global BOT_STOPPED
    if BOT_STOPPED and not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Бот временно остановлен.")
        return

    user_id = str(update.effective_user.id)
    user_data = data["users"][user_id]
    coins = user_data["coins"]
    price = data["settings"]["exchange_price"]

    if coins < price:
        await update.message.reply_text(
            f"❌ Недостаточно монет!\n\nВаш баланс: {coins} монет\nНужно для обмена: {price} монет\n\n💡 Приглашайте друзей по реферальной ссылке, чтобы получать монеты!",
            reply_markup=menu(int(user_id))
        )
        return

    await update.message.reply_text(
        "🎮 Выберите игру для обмена монет:\n\n👇 Нажмите на кнопку с нужной игрой:",
        reply_markup=game_selection_keyboard()
    )
    context.user_data["awaiting_game_selection"] = True
    context.user_data["awaiting_account_action"] = "exchange"

async def process_exchange_game_selection(update: Update, context: CallbackContext, game):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    user_data = data["users"][user_id]
    price = data["settings"]["exchange_price"]
    
    game_accounts = data.get(f"accounts_common_{game}", [])
    if not game_accounts:
        await query.edit_message_text(f"❌ В базе {GAME_NAMES[game]} закончились аккаунты! Попробуйте позже.")
        await context.bot.send_message(chat_id=query.from_user.id, text="Возвращаю меню...", reply_markup=menu(int(user_id)))
        return

    account = game_accounts.pop(0)
    data[f"accounts_common_{game}"] = game_accounts
    
    user_data["coins"] -= price
    user_data["history"].append({
        "date": datetime.now().isoformat(),
        "account": account,
        "type": "exchange",
        "game": game
    })
    save()
    
    await notify_super_admins(
        context,
        f"💎 ПОКУПКА ЗА МОНЕТЫ\nПокупатель: {get_user_link(query.from_user)}\nИгра: {GAME_NAMES[game]}\nСтоимость: {price} монет\nАккаунт: {account}"
    )
    
    await query.edit_message_text(
        f"✅ Успешный обмен!\n\n🎮 Игра: {GAME_NAMES[game]}\n💎 Списано: {price} монет\n🔐 Аккаунт:\n{account}\n\n💡 Продолжайте приглашать друзей за монеты!"
    )
    await context.bot.send_message(chat_id=query.from_user.id, text="Выберите действие:", reply_markup=menu(int(user_id)))

async def profile(update: Update, context: CallbackContext):
    global BOT_STOPPED
    if BOT_STOPPED and not is_admin(update.effective_user.id):
        return

    user = update.effective_user
    user_id = str(user.id)

    if user_id in data["users"]:
        user_data = data["users"][user_id]
        used_promo = len(user_data.get("used_promocodes", []))
        exchange_price = data["settings"]["exchange_price"]
        coin_reward = data["settings"]["coin_reward"]
        
        pending_coins_info = ""
        if user_data.get("coins_pending_approval", False):
            pending_coins_info = "\n⚠️ У вас есть ожидающие начисления монеты!\nПодпишитесь на все каналы, чтобы получить их."

        time_text = ""
        if user_data.get("last_receive"):
            last = datetime.fromisoformat(user_data["last_receive"])
            next_time = last + timedelta(hours=24)
            if datetime.now() < next_time:
                wait = next_time - datetime.now()
                hours = wait.seconds // 3600
                minutes = (wait.seconds % 3600) // 60
                time_text = f"\n⏰ Следующий через: {hours}ч {minutes}м"
            else:
                time_text = "\n✅ Можете получить аккаунт"

        text = f"""👤 Профиль

🆔 ID: {user_id}
👤 Имя: {user_data['name']}
📅 Регистрация: {datetime.fromisoformat(user_data['join_date']).strftime('%d.%m.%Y')}
🎮 Получено аккаунтов: {user_data['received']}
💎 Монеты: {user_data['coins']}
🎟 Промокоды: {used_promo}{time_text}

🔗 Реферальная ссылка:
https://t.me/{context.bot.username}?start={user_id}
(Награда за друга: {coin_reward} монет ТОЛЬКО после подписки на каналы){pending_coins_info}

💎 Обмен монет:
1 аккаунт = {exchange_price} монет

Нажмите "💎 Обменять монеты" в меню, чтобы обменять монеты на аккаунт."""

        await update.message.reply_text(text, reply_markup=menu(user.id))
    else:
        await update.message.reply_text("❌ Профиль не найден", reply_markup=menu(user.id))

async def account_history(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    if user_id not in data["users"]:
        await update.message.reply_text("❌ Запустите бота /start", reply_markup=menu(int(user_id)))
        return

    user_data = data["users"][user_id]
    history = user_data.get("history", [])

    if not history:
        await update.message.reply_text("📜 История пуста", reply_markup=menu(int(user_id)))
        return

    text = "📜 История (последние 10):\n\n"
    for i, item in enumerate(history[-10:], 1):
        date = datetime.fromisoformat(item["date"]).strftime("%d.%m %H:%M")
        acc_type = item.get("type", "unknown")
        game = item.get("game", "tanks")
        game_name = GAME_NAMES.get(game, "Unknown")
        type_icon = "🎁" if acc_type == "daily_free" else ("💎" if "exchange" in acc_type else "🎟")
        text += f"{i}. {date} {type_icon} ({game_name})\n   {item['account']}\n\n"

    await update.message.reply_text(text, reply_markup=menu(int(user_id)))

async def check_subscription_logic(user_id: int, context: CallbackContext):
    channels = data.get("channels", [])
    if not channels:
        return True, []
    
    not_subscribed = []
    
    for channel in channels:
        try:
            chat_id = None
            if channel.startswith("@"):
                chat_id = channel
            elif "t.me/" in channel:
                username = channel.split("t.me/")[1].split("/")[0]
                if username:
                    chat_id = f"@{username}"
            else:
                chat_id = channel
            
            if chat_id:
                member = await context.bot.get_chat_member(chat_id, user_id)
                if member.status not in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
                    not_subscribed.append(channel)
        except:
            not_subscribed.append(channel)
    
    return len(not_subscribed) == 0, not_subscribed

async def check_subscription(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    is_sub, not_sub_list = await check_subscription_logic(user_id, context)
    
    if is_sub:
        str_user_id = str(user_id)
        user_data = data["users"][str_user_id]
        
        if user_data.get("coins_pending_approval", False):
            ref_id = user_data.get("pending_referral") or user_data.get("referrer_id")
            
            if ref_id and ref_id in data["users"]:
                reward = data["settings"]["coin_reward"]
                data["users"][ref_id]["coins"] += reward
                
                user_data["coins_pending_approval"] = False
                if "pending_referral" in user_data:
                    del user_data["pending_referral"]
                
                save()
                
                try:
                    await context.bot.send_message(
                        chat_id=int(ref_id),
                        text=f"💰 Реферальный бонус начислен!\nВаш реферал подписался на все каналы.\nВам начислено: {reward} монет."
                    )
                except:
                    pass
                
                await notify_super_admins(
                    context,
                    f"✅ ВЫПОЛНЕНА ПОДПИСКА РЕФЕРАЛА\nРеферал: {get_user_link(update.effective_user)}\nРефовод: {ref_id}\nНачислено: {reward} монет"
                )
        
        await update.message.reply_text("✅ Вы подписаны на все каналы!")
    else:
        await update.message.reply_text(
            f"❌ Вы не подписаны на все каналы!\n\nНеобходимо подписаться на:",
            reply_markup=get_sub_keyboard(not_sub_list)
        )

# ========== ФУНКЦИЯ ОБРАБОТКИ ПРОМОКОДОВ ==========
async def process_promocode(update: Update, context: CallbackContext, promo_code: str):
    user = update.effective_user
    user_id = str(user.id)
    
    if user_id not in data["users"]:
        await update.message.reply_text("❌ Сначала запустите бота через /start")
        return
    
    user_data = data["users"][user_id]
    
    if promo_code in data["promocodes"]:
        promo_data = data["promocodes"][promo_code]
        
        if promo_data["used"] >= promo_data["max_uses"]:
            await update.message.reply_text("❌ Промокод уже использован максимальное количество раз.")
            return
            
        if promo_code in user_data.get("used_promocodes", []):
            await update.message.reply_text("❌ Вы уже использовали этот промокод.")
            return
        
        source = promo_data.get("source", "common")
        game = promo_data.get("game", GAME_TANKS)
        
        if game == GAME_TANKS:
            if source == "common":
                accounts_list = data.get("accounts_common_tanks", [])
            else:
                accounts_list = data.get("accounts_promo_tanks", [])
        else:
            accounts_list = data.get(f"accounts_common_{game}", [])
        
        if not accounts_list:
            await update.message.reply_text(f"❌ Извините, аккаунты для {GAME_NAMES.get(game, 'этой игры')} временно закончились.")
            return
        
        reward_count = promo_data.get("reward", 1)
        accounts_given = []
        
        for _ in range(reward_count):
            if accounts_list:
                account = accounts_list.pop(0)
                accounts_given.append(account)
                
                user_data["history"] = user_data.get("history", []) + [{
                    "date": datetime.now().isoformat(),
                    "account": account,
                    "type": "promocode",
                    "game": game,
                    "promo_code": promo_code
                }]
            else:
                break
        
        if not accounts_given:
            await update.message.reply_text(f"❌ Не удалось выдать аккаунты. Попробуйте позже.")
            return
        
        if game == GAME_TANKS:
            if source == "common":
                data["accounts_common_tanks"] = accounts_list
            else:
                data["accounts_promo_tanks"] = accounts_list
        else:
            data[f"accounts_common_{game}"] = accounts_list
            
        promo_data["used"] += 1
        user_data["used_promocodes"] = user_data.get("used_promocodes", []) + [promo_code]
        user_data["received"] += len(accounts_given)
        
        save()
        
        accounts_text = "\n".join([f"{acc}" for acc in accounts_given])
        
        await notify_super_admins(
            context,
            f"🎟 АКТИВИРОВАН ПРОМОКОД\nКем: {get_user_link(user)}\nКод: {promo_code}\nИгра: {GAME_NAMES.get(game, 'Unknown')}\nВыдано аккаунтов: {len(accounts_given)}\nОсталось использований: {promo_data['max_uses'] - promo_data['used']}"
        )
        
        await update.message.reply_text(
            f"✅ Промокод активирован!\n\n🎮 Игра: {GAME_NAMES.get(game, 'Unknown')}\n🔐 Аккаунт{'ы' if len(accounts_given) > 1 else ''}:\n{accounts_text}\n\n🎟 Промокод использован: {promo_data['used']}/{promo_data['max_uses']}"
        )
    else:
        await update.message.reply_text("❌ Неверный промокод.")

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
async def message_handler(update: Update, context: CallbackContext):
    global BOT_STOPPED
    
    if BOT_STOPPED and not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Бот временно остановлен.")
        return

    user_id = update.effective_user.id
    str_user_id = str(user_id)
    message = update.message
    text = message.text or message.caption or ""
    
    if str_user_id in data.get("banned_users", []):
        return
    
    if context.user_data.get("awaiting_captcha"):
        correct = context.user_data.get("captcha_correct", "")
        if text.upper() == correct:
            context.user_data["awaiting_captcha"] = False
            context.user_data["just_passed_captcha"] = True
            data["users"][str_user_id]["captcha_passed"] = True
            save()
            await message.reply_text("✅ Проверка пройдена!\n\nДобро пожаловать в бот!")
            await send_main_menu(update, context)
        else:
            await message.reply_text("❌ Неверный код. Попробуйте ещё раз:")
        return

    # СОХРАНЕНИЕ FAQ
    if context.user_data.get("setting_faq"):
        await save_faq(update, context)
        return

    if context.user_data.get("leaving_review"):
        if len(text) > 500:
            await message.reply_text("❌ Отзыв слишком длинный (макс. 500 символов). Попробуйте снова:")
            return
        if len(text) < 5:
            await message.reply_text("❌ Отзыв слишком короткий (мин. 5 символов). Попробуйте снова:")
            return
        
        review_id = random.randint(100000, 999999)
        pending_review = {
            "id": review_id,
            "user_id": str_user_id,
            "user_name": update.effective_user.full_name,
            "text": text,
            "date": datetime.now().isoformat()
        }
        
        data["pending_reviews"].append(pending_review)
        save()
        
        await notify_super_admins(
            context,
            f"⭐ НОВЫЙ ОТЗЫВ НА МОДЕРАЦИЮ\nОт: {get_user_link(update.effective_user)}\nID отзыва: {review_id}\nТекст: {text[:200]}..."
        )
        
        await message.reply_text("✅ Спасибо за отзыв!\n\nВаш отзыв отправлен на модерацию и скоро будет опубликован.")
        context.user_data["leaving_review"] = False
        return

    if context.user_data.get("awaiting_file") and message.document:
        if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_ACCS):
            await message.reply_text("❌ У вас нет прав на загрузку аккаунтов.")
            context.user_data["awaiting_file"] = False
            return
            
        file = await message.document.get_file()
        content = await file.download_as_bytearray()
        
        try:
            text_content = content.decode('utf-8').strip()
        except:
            text_content = content.decode('latin-1').strip()
        
        accounts = []
        for line in text_content.split('\n'):
            line = line.strip()
            if line and ':' in line:
                accounts.append(line)
        
        if not accounts:
            await message.reply_text("❌ Не найдено валидных аккаунтов в формате почта:пароль.")
            context.user_data["awaiting_file"] = False
            return
        
        context.user_data["temp_accounts"] = accounts
        
        await message.reply_text(
            f"✅ Загружено {len(accounts)} аккаунтов.\n\nВыберите игру для загрузки:",
            reply_markup=admin_kb_acc_game_selection()
        )
        context.user_data["awaiting_file"] = False
        return

    # ========== РАССЫЛКА - ОБРАБОТКА КНОПОК ==========
    if context.user_data.get("broadcast_step") == "wait_btn_text":
        context.user_data["broadcast_btn_text"] = text
        await message.reply_text("🔗 Теперь отправьте ССЫЛКУ для кнопки (начинается с http/https или t.me):")
        context.user_data["broadcast_step"] = "wait_btn_url"
        return

    if context.user_data.get("broadcast_step") == "wait_btn_url":
        url = text.strip()
        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("t.me/")):
            await message.reply_text("❌ Ссылка должна начинаться с http://, https:// или t.me/. Попробуйте снова:")
            return
        
        if url.startswith("t.me/"):
            url = f"https://{url}"
            
        context.user_data["broadcast_btn_url"] = url
        
        if "broadcast_buttons" not in context.user_data:
            context.user_data["broadcast_buttons"] = []
        
        btn_text = context.user_data["broadcast_btn_text"]
        context.user_data["broadcast_buttons"].append([InlineKeyboardButton(btn_text, url=url)])
        
        del context.user_data["broadcast_btn_text"]
        del context.user_data["broadcast_btn_url"]
        
        await message.reply_text(f"✅ Кнопка добавлена! Добавить ещё кнопку?", reply_markup=broadcast_add_btn_kb())
        context.user_data["broadcast_step"] = "wait_decision"
        return

    if context.user_data.get("broadcasting"):
        if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_BROADCAST):
            await message.reply_text("❌ У вас нет прав на рассылку.")
            context.user_data["broadcasting"] = False
            return
        await handle_broadcast_content(update, context)
        return

    if context.user_data.get("setting_price"):
        if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_SETTINGS):
            await message.reply_text("❌ У вас нет прав на изменение настроек.")
            context.user_data["setting_price"] = False
            return
            
        try:
            price = int(text)
            if price < 1:
                await message.reply_text("❌ Цена должна быть положительным числом.")
                return
            
            data["settings"]["exchange_price"] = price
            save()
            
            await notify_super_admins(
                context,
                f"💰 ИЗМЕНЕНА ЦЕНА АККАУНТА\nКем: {get_user_link(update.effective_user)}\nНовая цена: {price} монет"
            )
            
            await message.reply_text(f"✅ Цена аккаунта изменена на {price} монет.", reply_markup=back_btn("admin_menu_settings"))
        except ValueError:
            await message.reply_text("❌ Введите число.")
        context.user_data["setting_price"] = False
        return

    if context.user_data.get("setting_reward"):
        if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_SETTINGS):
            await message.reply_text("❌ У вас нет прав на изменение настроек.")
            context.user_data["setting_reward"] = False
            return
            
        try:
            reward = int(text)
            if reward < 1:
                await message.reply_text("❌ Награда должна быть положительным числом.")
                return
            
            data["settings"]["coin_reward"] = reward
            save()
            
            await notify_super_admins(
                context,
                f"🤝 ИЗМЕНЕНА НАГРАДА ЗА РЕФЕРАЛА\nКем: {get_user_link(update.effective_user)}\nНовая награда: {reward} монет"
            )
            
            await message.reply_text(f"✅ Награда за реферала изменена на {reward} монет.", reply_markup=back_btn("admin_menu_settings"))
        except ValueError:
            await message.reply_text("❌ Введите число.")
        context.user_data["setting_reward"] = False
        return

    if context.user_data.get("adding_channel"):
        if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_CHANNELS):
            await message.reply_text("❌ У вас нет прав на управление каналами.")
            context.user_data["adding_channel"] = False
            return
            
        channel = text.strip()
        if channel not in data["channels"]:
            data["channels"].append(channel)
            save()
            
            await notify_super_admins(
                context,
                f"📢 ДОБАВЛЕН КАНАЛ\nКем: {get_user_link(update.effective_user)}\nКанал: {channel}"
            )
            
            await message.reply_text(f"✅ Канал добавлен: {channel}", reply_markup=admin_kb_channels())
        else:
            await message.reply_text("❌ Канал уже есть в списке.")
        context.user_data["adding_channel"] = False
        return

    if context.user_data.get("deleting_channel"):
        if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_CHANNELS):
            await message.reply_text("❌ У вас нет прав на управление каналами.")
            context.user_data["deleting_channel"] = False
            return
            
        channel = text.strip()
        if channel in data["channels"]:
            data["channels"].remove(channel)
            save()
            
            await notify_super_admins(
                context,
                f"📢 УДАЛЕН КАНАЛ\nКем: {get_user_link(update.effective_user)}\nКанал: {channel}"
            )
            
            await message.reply_text(f"✅ Канал удален: {channel}", reply_markup=admin_kb_channels())
        else:
            await message.reply_text("❌ Канал не найден в списке.")
        context.user_data["deleting_channel"] = False
        return

    if context.user_data.get("adding_admin"):
        if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_ADD_ADMIN):
            await message.reply_text("❌ У вас нет прав на добавление админов.")
            context.user_data["adding_admin"] = False
            return
            
        try:
            new_admin_id = int(text.strip())
            if str(new_admin_id) == str(user_id):
                await message.reply_text("❌ Нельзя добавить самого себя.")
                return
                
            if str(new_admin_id) in data["admins"]:
                await message.reply_text("❌ Этот пользователь уже админ.")
                return
                
            try:
                user_info = await context.bot.get_chat(new_admin_id)
                admin_name = user_info.full_name
            except:
                admin_name = f"ID: {new_admin_id}"
            
            data["admins"][str(new_admin_id)] = {
                "name": admin_name,
                "permissions": DEFAULT_PERMISSIONS.copy(),
                "added_by": str(user_id),
                "added_date": datetime.now().isoformat()
            }
            save()
            
            await notify_super_admins(
                context,
                f"🛡 НАЗНАЧЕН НОВЫЙ АДМИН\nКем: {get_user_link(update.effective_user)}\nАдмин: {admin_name} (ID: {new_admin_id})"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=new_admin_id,
                    text="🎉 Поздравляем!\n\nВы были назначены администратором бота. Используйте команду /panel для доступа к админ-панели."
                )
            except:
                pass
                
            await message.reply_text(f"✅ Пользователь {admin_name} назначен админом!", reply_markup=admin_kb_admins_list())
        except ValueError:
            await message.reply_text("❌ Введите числовой ID.")
        context.user_data["adding_admin"] = False
        return

    if context.user_data.get("creating_promo"):
        if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_PROMOS):
            await message.reply_text("❌ У вас нет прав на создание промокодов.")
            context.user_data["creating_promo"] = False
            return
            
        parts = text.strip().split()
        if len(parts) != 3:
            await message.reply_text("❌ Неверный формат. Нужно: КОД КОЛИЧЕСТВО_АККАУНТОВ ЛИМИТ_ИСПОЛЬЗОВАНИЙ\nПример: SUMMER 5 100")
            return
            
        code, reward_str, uses_str = parts
        
        try:
            reward = int(reward_str)
            max_uses = int(uses_str)
            
            if reward < 1 or max_uses < 1:
                await message.reply_text("❌ Количество аккаунтов и использований должны быть положительными числами.")
                return
                
            if code in data["promocodes"]:
                await message.reply_text("❌ Промокод с таким названием уже существует.")
                return
                
            context.user_data["temp_promo_data"] = {
                "code": code,
                "reward": reward,
                "max_uses": max_uses
            }
            
            await message.reply_text(
                f"✅ Данные промокода получены:\nКод: {code}\nНаграда: {reward} аккаунтов\nМакс. использований: {max_uses}\n\nВыберите источник аккаунтов:",
                reply_markup=admin_kb_promo_source_choice()
            )
        except ValueError:
            await message.reply_text("❌ Количество и использование должны быть числами.")
        context.user_data["creating_promo"] = False
        return

    if context.user_data.get("banning_user"):
        if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_BAN):
            await message.reply_text("❌ У вас нет прав на бан пользователей.")
            context.user_data["banning_user"] = False
            return
            
        target_id = text.strip()
        
        if target_id in data.get("banned_users", []):
            await message.reply_text("❌ Этот пользователь уже забанен.")
            return
            
        if not target_id.isdigit():
            await message.reply_text("❌ ID должен состоять только из цифр.")
            return
            
        if int(target_id) in SUPER_ADMIN_IDS:
            await message.reply_text("❌ Нельзя забанить супер-админа!")
            return
            
        if target_id in data.get("admins", {}):
            await message.reply_text("❌ Нельзя забанить админа. Сначала удалите его из админов.")
            return
            
        if target_id in data["users"]:
            data.setdefault("banned_users", []).append(target_id)
            save()
            
            await notify_super_admins(
                context,
                f"⛔ ЗАБАНЕН ПОЛЬЗОВАТЕЛЬ\nКем: {get_user_link(update.effective_user)}\nID пользователя: {target_id}"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=int(target_id),
                    text="⛔ Вы были заблокированы в боте!\n\nЕсли вы считаете, что это ошибка, обратитесь к администратору."
                )
            except:
                pass
                
            await message.reply_text(f"✅ Пользователь {target_id} забанен.", reply_markup=admin_kb_users())
        else:
            await message.reply_text("❌ Пользователь не найден в базе.")
        context.user_data["banning_user"] = False
        return

    if context.user_data.get("unbanning_user"):
        if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_BAN):
            await message.reply_text("❌ У вас нет прав на разбан пользователей.")
            context.user_data["unbanning_user"] = False
            return
            
        target_id = text.strip()
        
        if target_id in data.get("banned_users", []):
            data["banned_users"].remove(target_id)
            save()
            
            await notify_super_admins(
                context,
                f"✅ РАЗБАНЕН ПОЛЬЗОВАТЕЛЬ\nКем: {get_user_link(update.effective_user)}\nID пользователя: {target_id}"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=int(target_id),
                    text="✅ Ваша блокировка снята!\n\nВы снова можете пользоваться ботом."
                )
            except:
                pass
                
            await message.reply_text(f"✅ Пользователь {target_id} разбанен.", reply_markup=admin_kb_users())
        else:
            await message.reply_text("❌ Этот пользователь не забанен.")
        context.user_data["unbanning_user"] = False
        return

    if context.user_data.get("deleting_review"):
        if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_REVIEWS):
            await message.reply_text("❌ У вас нет прав на удаление отзывов.")
            context.user_data["deleting_review"] = False
            return
            
        review_id = text.strip()
        
        found = False
        for i, review in enumerate(data.get("reviews", [])):
            if str(review.get("id")) == review_id:
                data["reviews"].pop(i)
                found = True
                break
                
        if not found:
            for i, review in enumerate(data.get("pending_reviews", [])):
                if str(review.get("id")) == review_id:
                    data["pending_reviews"].pop(i)
                    found = True
                    break
        
        if found:
            save()
            
            await notify_super_admins(
                context,
                f"🗑 УДАЛЕН ОТЗЫВ\nКем: {get_user_link(update.effective_user)}\nID отзыва: {review_id}"
            )
            
            await message.reply_text(f"✅ Отзыв с ID {review_id} удален.", reply_markup=admin_kb_reviews())
        else:
            await message.reply_text("❌ Отзыв с таким ID не найден.")
        context.user_data["deleting_review"] = False
        return

    if context.user_data.get("sending_pm"):
        parts = text.strip().split(' ', 1)
        if len(parts) < 2:
            await message.reply_text("❌ Неверный формат. Нужно: ID_ПОЛЬЗОВАТЕЛЯ СООБЩЕНИЕ\nПример: 123456789 Привет!")
            return
            
        target_id, pm_text = parts[0], parts[1]
        
        if not target_id.isdigit():
            await message.reply_text("❌ ID должен состоять только из цифр.")
            return
            
        try:
            await context.bot.send_message(
                chat_id=int(target_id),
                text=pm_text
            )
            
            await notify_super_admins(
                context,
                f"✉️ ОТПРАВЛЕНО ЛИЧНОЕ СООБЩЕНИЕ\nКем: {get_user_link(update.effective_user)}\nКому: ID {target_id}\nТекст: {pm_text[:200]}..."
            )
            
            await message.reply_text(f"✅ Сообщение отправлено пользователю {target_id}")
        except Forbidden:
            await message.reply_text("❌ Пользователь заблокировал бота.")
        except Exception as e:
            await message.reply_text(f"❌ Ошибка отправки: {e}")
        context.user_data["sending_pm"] = False
        return

    # Обработка текстовых команд
    if text == "🎮 Получить аккаунт":
        await get_account(update, context)
    elif text == "👤 Мой профиль":
        await profile(update, context)
    elif text == "📜 История":
        await account_history(update, context)
    elif text == "💎 Обменять монеты":
        await exchange_coins(update, context)
    elif text == "🎟 Промокод":
        await message.reply_text("🎟 Введите промокод:\n\nОтправьте код промокода в сообщении.\nПример: SUMMER2024")
        context.user_data["awaiting_promocode"] = True
    elif text == "ℹ️ О боте":
        await about_bot(update, context)
    elif text == "✅ Проверить подписку":
        await check_subscription(update, context)
    elif text == "👑 Админ":
        await panel_command(update, context)
    elif text == "⭐ Отзывы":
        await message.reply_text("⭐ Отзывы о боте\n\nЗдесь вы можете прочитать отзывы других пользователей или оставить свой.", 
                               reply_markup=reviews_keyboard())
    elif context.user_data.get("awaiting_promocode"):
        promo_code = text.strip().upper()
        await process_promocode(update, context, promo_code)
        context.user_data["awaiting_promocode"] = False
    elif text.startswith('/promo'):
        parts = text.split(' ', 1)
        if len(parts) > 1:
            promo_code = parts[1].strip().upper()
            await process_promocode(update, context, promo_code)
        else:
            await message.reply_text("🎟 Использование команды:\n/promo КОД\n\nПример: /promo SUMMER2024")
    else:
        if update.effective_user.id in SUPER_ADMIN_IDS or str(update.effective_user.id) in data.get("admins", {}):
            await panel_command(update, context)
        else:
            await send_main_menu(update, context)

# ========== ОБРАБОТЧИК CALLBACK ==========
async def main_callback_handler(update: Update, context: CallbackContext):
    global BOT_STOPPED
    
    query = update.callback_query
    cb_data = query.data 
    user_id = query.from_user.id
    str_user_id = str(user_id)
    
    await query.answer()

    if cb_data.startswith("select_game_"):
        game = cb_data.split("_")[2]
        if game in [GAME_TANKS, GAME_BLITZ]:
            if context.user_data.get("awaiting_game_selection"):
                action = context.user_data.get("awaiting_account_action")
                if action == "get":
                    await process_game_selection(update, context, game)
                elif action == "exchange":
                    await process_exchange_game_selection(update, context, game)
                context.user_data["awaiting_game_selection"] = False
                context.user_data["awaiting_account_action"] = None
            else:
                await query.edit_message_text(
                    f"✅ Выбрана игра: {GAME_NAMES[game]}\n\nТеперь вы можете получать аккаунты для этой игры."
                )
        return

    if cb_data == "view_reviews":
        reviews = data.get("reviews", [])
        if not reviews:
            await query.message.reply_text("📝 Пока нет отзывов. Будьте первым!", reply_markup=reviews_keyboard())
            return
        
        text = "⭐ Опубликованные отзывы:\n\n"
        for i, review in enumerate(reviews[-10:], 1):
            date = datetime.fromisoformat(review["date"]).strftime("%d.%m.%Y")
            text += f"{i}. {review['text']}\n   👤 {review['user_name']} • {date}\n\n"
        if len(reviews) > 10:
            text += f"\n📊 Всего отзывов: {len(reviews)}"
        
        try:
            await query.edit_message_text(text, reply_markup=reviews_keyboard())
        except BadRequest:
            pass 
        return

    elif cb_data == "leave_review":
        await query.message.reply_text("⭐ Оставить отзыв\n\nНапишите ваш отзыв одним сообщением (максимум 500 символов):\n\n📝 Ваш отзыв будет отправлен на модерацию.")
        context.user_data["leaving_review"] = True
        return

    if cb_data == "delete_msg":
        try:
            await query.delete_message()
        except:
            pass
        return

    if cb_data == "check_sub_confirm":
        is_sub, not_sub_list = await check_subscription_logic(user_id, context)
        if is_sub:
            user_data = data["users"][str_user_id]
            if user_data.get("coins_pending_approval", False):
                ref_id = user_data.get("pending_referral") or user_data.get("referrer_id")
                if ref_id and ref_id in data["users"]:
                    reward = data["settings"]["coin_reward"]
                    data["users"][ref_id]["coins"] += reward
                    user_data["coins_pending_approval"] = False
                    if "pending_referral" in user_data:
                        del user_data["pending_referral"]
                    save()
                    
                    try:
                        await context.bot.send_message(
                            chat_id=int(ref_id),
                            text=f"💰 Реферальный бонус начислен!\nВаш реферал подписался на все каналы.\nВам начислено: {reward} монет."
                        )
                    except:
                        pass
                    
                    await notify_super_admins(
                        context,
                        f"✅ ВЫПОЛНЕНА ПОДПИСКА РЕФЕРАЛА\nРеферал: {get_user_link(query.from_user)}\nРефовод: {ref_id}\nНачислено: {reward} монет"
                    )
            
            await query.edit_message_text("✅ Отлично! Вы подписаны.\nТеперь можете пользоваться ботом.")
        else:
            await query.edit_message_text(f"❌ Вы все еще не подписаны!", reply_markup=get_sub_keyboard(not_sub_list))
        return

    if cb_data == "exchange_coins":
        if update.callback_query.message:
            await update.callback_query.message.reply_text("💎 Обмен монет:", reply_markup=exchange_keyboard())
        return

    if not is_admin(user_id):
        return

    try:
        if cb_data == "admin_main":
            context.user_data.clear()
            await query.edit_message_text("👑 Админ панель", reply_markup=admin_kb_main(user_id))
        
        elif cb_data == "admin_stats":
            total_accounts_issued = sum(user.get("received", 0) for user in data["users"].values())
            total_coins = sum(user.get("coins", 0) for user in data["users"].values())
            banned_count = len(data.get("banned_users", []))
            total_in_stock = (len(data['accounts_common_tanks']) + 
                              len(data['accounts_promo_tanks']) +
                              len(data['accounts_common_blitz']))
            
            stats = f"""📊 Статистика бота

👥 Пользователей: {len(data["users"])}
⛔️ Забанено: {banned_count}
📦 Аккаунтов в наличии: {total_in_stock}
🎮 Всего выдано аккаунтов: {total_accounts_issued}
💰 Всего монет у пользователей: {total_coins}
🎟 Промокодов: {len(data["promocodes"])}
⭐️ Отзывов: {len(data.get("reviews", []))} (⏳ {len(data["pending_reviews"])} на модерации)
📢 Каналов: {len(data.get("channels", []))}
🛡 Админов (доп): {len(data.get("admins", {}))}

⏸️ Бот {'остановлен' if BOT_STOPPED else 'работает'}"""
            await query.edit_message_text(stats, reply_markup=back_btn())

        elif cb_data == "admin_menu_accs":
            if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_ACCS):
                await query.answer("❌ У вас нет прав на управление аккаунтами", show_alert=True)
                return
                
            total_accounts = (len(data['accounts_common_tanks']) + len(data['accounts_promo_tanks']) +
                             len(data['accounts_common_blitz']))
            
            text = f"""📦 Управление аккаунтами

📊 Статистика аккаунтов:
• Всего аккаунтов в наличии: {total_accounts}
• TanksBlitz (Общая): {len(data['accounts_common_tanks'])} шт.
• TanksBlitz (Промо): {len(data['accounts_promo_tanks'])} шт.
• WoT Blitz (Общая): {len(data['accounts_common_blitz'])} шт.

Выберите действие:"""
            await query.edit_message_text(text, reply_markup=admin_kb_accounts())
            
        elif cb_data == "admin_select_game":
            await query.edit_message_text("🎮 Выберите игру для управления:", reply_markup=admin_kb_acc_game_selection())
            
        elif cb_data.startswith("admin_game_"):
            game = cb_data.split("_")[2]
            if game in [GAME_TANKS, GAME_BLITZ]:
                context.user_data["selected_admin_game"] = game
                game_name = GAME_NAMES[game]
                
                if game == GAME_TANKS:
                    common_count = len(data.get(f'accounts_common_{game}', []))
                    promo_count = len(data.get(f'accounts_promo_{game}', []))
                    text = f"""📦 Управление аккаунтами для {game_name}
                    
📊 Статистика:
• Общая база: {common_count} шт.
• Промо база: {promo_count} шт.
• Всего: {common_count + promo_count} шт."""
                else:
                    common_count = len(data.get(f'accounts_common_{game}', []))
                    text = f"""📦 Управление аккаунтами для {game_name}
                    
📊 Статистика:
• Общая база: {common_count} шт.
• Промо база: Нет (только общая база)"""
                
                await query.edit_message_text(text, reply_markup=admin_kb_acc_actions_for_game(game))
            
        elif cb_data == "admin_menu_promo":
            if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_PROMOS):
                await query.answer("❌ У вас нет прав на управление промокодами", show_alert=True)
                return
            await query.edit_message_text("🎟 Управление промокодами (только для TanksBlitz)", reply_markup=admin_kb_promo())

        elif cb_data == "admin_menu_users":
            if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_BAN):
                await query.answer("❌ У вас нет прав на управление пользователями", show_alert=True)
                return
            await query.edit_message_text(
                f"👥 Управление пользователями\nВсего юзеров: {len(data['users'])}\nВ бане: {len(data.get('banned_users', []))}", 
                reply_markup=admin_kb_users()
            )

        elif cb_data == "admin_menu_reviews":
            if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_REVIEWS):
                await query.answer("❌ У вас нет прав на модерацию отзывов", show_alert=True)
                return
            pending_count = len(data["pending_reviews"])
            approved_count = len(data["reviews"])
            await query.edit_message_text(
                f"⭐ Управление отзывами\n\n⏳ Ожидают модерации: {pending_count}\n✅ Опубликовано: {approved_count}", 
                reply_markup=admin_kb_reviews()
            )
            
        elif cb_data == "admin_menu_settings":
            if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_SETTINGS):
                await query.answer("❌ У вас нет прав на настройки", show_alert=True)
                return
            stats = f"""⚙️ Настройки бота
            
💰 Цена аккаунта: {data['settings']['exchange_price']} монет
🤝 Награда за реферала: {data['settings']['coin_reward']} монет
📝 Текст FAQ: {len(data['settings']['faq_text'])} символов"""
            await query.edit_message_text(stats, reply_markup=admin_kb_settings())

        elif cb_data == "admin_close":
            await query.delete_message()
            
        elif cb_data == "admin_acc_load":
            if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_ACCS):
                await query.answer("❌ У вас нет прав на загрузку аккаунтов", show_alert=True)
                return
            await query.message.reply_text("🔄 Отправьте .txt файл с аккаунтами (почта:пароль).")
            context.user_data["awaiting_file"] = True

        elif cb_data.startswith("upload_to_common_") or cb_data.startswith("upload_to_promo_"):
            accounts = context.user_data.get("temp_accounts", [])
            if not accounts:
                await query.edit_message_text("❌ Ошибка: список аккаунтов пуст или утерян.")
                return
            
            parts = cb_data.split("_")
            target_type = parts[2]
            game = parts[3]
            
            if game == GAME_BLITZ and target_type == "promo":
                await query.edit_message_text("❌ Для WoT Blitz нет промо-базы. Можно загружать только в общую базу.")
                return
            
            target_key = f"accounts_{target_type}_{game}"
            
            data[target_key].extend(accounts)
            save()
            
            name_map = {"common": "ОБЩУЮ", "promo": "ПРОМО"}
            game_map = {"tanks": "TanksBlitz", "blitz": "WoT Blitz"}
            
            await notify_super_admins(
                context,
                f"📦 ЗАГРУЖЕНЫ АККАУНТЫ\nКем: {get_user_link(query.from_user)}\nИгра: {game_map[game]}\nБаза: {name_map[target_type]}\nКоличество: {len(accounts)} аккаунтов"
            )
            
            await query.edit_message_text(f"✅ Успешно добавлено {len(accounts)} аккаунтов в {name_map[target_type]} базу {game_map[game]}!", 
                                          reply_markup=admin_kb_acc_actions_for_game(game))
            context.user_data["temp_accounts"] = []

        elif cb_data.startswith("admin_acc_del_common_") or cb_data.startswith("admin_acc_del_promo_"):
            parts = cb_data.split("_")
            target_type = parts[3]
            game = parts[4]
            
            if game == GAME_BLITZ and target_type == "promo":
                await query.answer("Для WoT Blitz нет промо-базы", show_alert=True)
                return
            
            target_key = f"accounts_{target_type}_{game}"
            count = len(data[target_key])
            data[target_key] = []
            save()
            
            game_map = {"tanks": "TanksBlitz", "blitz": "WoT Blitz"}
            
            await notify_super_admins(
                context,
                f"🗑 УДАЛЕНЫ АККАУНТЫ\nКем: {get_user_link(query.from_user)}\nИгра: {game_map[game]}\nБаза: {target_type}\nКоличество: {count} аккаунтов"
            )
            
            await query.answer(f"Удалено {count} аккаунтов из {target_type} базы {game_map[game]}", show_alert=True)
            await query.edit_message_text("📦 Аккаунты обновлены", reply_markup=admin_kb_acc_actions_for_game(game))

        elif cb_data == "set_price":
            await query.message.reply_text(f"💰 Введите новую цену аккаунта (сейчас: {data['settings']['exchange_price']}):")
            context.user_data["setting_price"] = True
            
        elif cb_data == "set_reward":
            await query.message.reply_text(f"🤝 Введите новую награду за рефа (сейчас: {data['settings']['coin_reward']}):")
            context.user_data["setting_reward"] = True
            
        elif cb_data == "set_faq":
            await query.message.reply_text("📝 Отправьте новый текст FAQ (можно с форматированием):")
            context.user_data["setting_faq"] = True

        elif cb_data == "admin_promo_create":
            await query.message.reply_text(
                "🎟 Создание промокода (только для TanksBlitz)\nВведите: КОД КОЛИЧЕСТВО_АККАУНТОВ ЛИМИТ_ИСПОЛЬЗОВАНИЙ\nПример: SUMMER 5 100"
            )
            context.user_data["creating_promo"] = True

        elif cb_data.startswith("promo_src_"):
            promo_data = context.user_data.get("temp_promo_data")
            if not promo_data:
                await query.edit_message_text("Ошибка создания промокода.")
                return
            
            source = cb_data.split("_")[2]
            code = promo_data["code"]
            
            data["promocodes"][code] = {
                "reward": promo_data["reward"],
                "max_uses": promo_data["max_uses"],
                "used": 0,
                "source": source,
                "game": GAME_TANKS
            }
            save()
            
            src_name = "ОБЩЕЙ" if source == "common" else "ПРОМО"
            
            await notify_super_admins(
                context,
                f"🎟 СОЗДАН ПРОМОКОД\nКем: {get_user_link(query.from_user)}\nКод: {code}\nНаграда: {promo_data['reward']} аккаунтов\nЛимит: {promo_data['max_uses']} использований\nБаза: {src_name}"
            )
            
            await query.edit_message_text(f"✅ Промокод {code} создан!\nИгра: TanksBlitz\nИсточник аккаунтов: с {src_name} базы.", reply_markup=back_btn("admin_menu_promo"))
            context.user_data["temp_promo_data"] = {}

        elif cb_data == "admin_channel_list":
            ch_list = "\n".join(data["channels"]) if data["channels"] else "Пусто"
            await query.edit_message_text(f"📢 Каналы:\n{ch_list}", reply_markup=admin_kb_channels())
            
        elif cb_data == "admin_channel_add":
            if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_CHANNELS):
                await query.answer("❌ У вас нет прав на управление каналами", show_alert=True)
                return
            await query.message.reply_text("➕ Введите ссылку или @username канала (бот должен быть админом):")
            context.user_data["adding_channel"] = True

        elif cb_data == "admin_channel_del":
            if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_CHANNELS):
                await query.answer("❌ У вас нет прав на управление каналами", show_alert=True)
                return
            await query.message.reply_text("➖ Введите ссылку канала для удаления:")
            context.user_data["deleting_channel"] = True

        elif cb_data == "admin_menu_channels":
            if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_CHANNELS):
                await query.answer("❌ У вас нет прав на управление каналами", show_alert=True)
                return
            await query.edit_message_text("📢 Управление каналами", reply_markup=admin_kb_channels())
            
        elif cb_data == "admin_menu_admins":
            if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_ADD_ADMIN):
                await query.answer("❌ У вас нет прав на управление админами", show_alert=True)
                return
            await query.edit_message_text("🛡 Управление админами", reply_markup=admin_kb_admins_list())
            
        elif cb_data == "admin_add_new":
            await query.message.reply_text("👤 Введите ID нового админа:")
            context.user_data["adding_admin"] = True
            
        elif cb_data.startswith("adm_edit:"):
            target_id = cb_data.split(":")[1]
            await query.edit_message_text(f"⚙️ Права для {target_id}", reply_markup=admin_kb_admin_rights(target_id))

        elif cb_data.startswith("adm_toggle:"):
            _, target_id, perm = cb_data.split(":")
            if str(target_id) in data["admins"]:
                curr = data["admins"][str(target_id)]["permissions"].get(perm, False)
                data["admins"][str(target_id)]["permissions"][perm] = not curr
                save()
                await query.edit_message_reply_markup(reply_markup=admin_kb_admin_rights(target_id))

        elif cb_data.startswith("adm_delete:"):
            target_id = cb_data.split(":")[1]
            if str(target_id) in data["admins"]:
                del data["admins"][str(target_id)]
                save()
                
                await notify_super_admins(
                    context,
                    f"🗑 УДАЛЕН АДМИН\nКем: {get_user_link(query.from_user)}\nID админа: {target_id}"
                )
                
                await query.edit_message_text("Админ удален", reply_markup=admin_kb_admins_list())

        elif cb_data == "admin_promo_list":
            promos = data.get("promocodes", {})
            if not promos:
                await query.edit_message_text("🎟 Нет активных промокодов.")
                return
            
            text = "🎟 Активные промокоды:\n\n"
            for code, details in promos.items():
                uses = f"{details.get('used', 0)}/{details.get('max_uses', 0)}"
                reward = details.get("reward", 1)
                source = details.get("source", "common")
                source_name = "ОБЩАЯ" if source == "common" else "ПРОМО"
                game = details.get("game", GAME_TANKS)
                game_name = GAME_NAMES.get(game, "Unknown")
                
                text += f"• {code} - {reward} акк. ({game_name})\n  Использовано: {uses} | Источник: {source_name}\n\n"
            
            await query.edit_message_text(text, reply_markup=back_btn("admin_menu_promo"))

        elif cb_data == "admin_user_ban":
            await query.message.reply_text("⛔ Введите ID пользователя для бана:")
            context.user_data["banning_user"] = True

        elif cb_data == "admin_user_unban":
            await query.message.reply_text("✅ Введите ID пользователя для разбана:")
            context.user_data["unbanning_user"] = True

        elif cb_data == "admin_review_moderate":
            await query.edit_message_text("⭐ Модерация отзывов", reply_markup=admin_kb_review_moderation())

        elif cb_data == "mod_view_pending":
            pending = data.get("pending_reviews", [])
            if not pending:
                await query.edit_message_text("⏳ Нет отзывов на модерации.", reply_markup=admin_kb_review_moderation())
                return
            
            for review in pending[:5]:
                date = datetime.fromisoformat(review["date"]).strftime("%d.%m.%Y %H:%M")
                text = f"⏳ Отзыв на модерации\n\nID: {review['id']}\nДата: {date}\n👤 Пользователь: {review['user_name']} (ID: {review['user_id']})\n\n📝 Текст:\n{review['text']}"
                
                await query.message.reply_text(text, reply_markup=moderation_review_kb(review['id']))
            
            await query.edit_message_text(f"⏳ Показано {min(5, len(pending))} из {len(pending)} отзывов", reply_markup=admin_kb_review_moderation())

        elif cb_data == "mod_view_approved":
            reviews = data.get("reviews", [])
            if not reviews:
                await query.edit_message_text("✅ Нет опубликованных отзывов.", reply_markup=admin_kb_review_moderation())
                return
            
            text = "✅ Опубликованные отзывы:\n\n"
            for i, review in enumerate(reviews[-10:], 1):
                date = datetime.fromisoformat(review["date"]).strftime("%d.%m.%Y")
                text += f"{i}. {review['text']}\n   👤 {review['user_name']} • {date}\n\n"
            
            if len(reviews) > 10:
                text += f"\n📊 Всего отзывов: {len(reviews)}"
            
            await query.edit_message_text(text, reply_markup=admin_kb_review_moderation())

        elif cb_data.startswith("mod_approve:"):
            review_id = cb_data.split(":")[1]
            pending = data.get("pending_reviews", [])
            
            for i, review in enumerate(pending):
                if str(review['id']) == review_id:
                    approved_review = pending.pop(i)
                    data["reviews"].append(approved_review)
                    save()
                    
                    try:
                        await context.bot.send_message(
                            chat_id=int(approved_review['user_id']),
                            text="✅ Ваш отзыв был одобрен и опубликован!\n\nСпасибо за обратную связь!"
                        )
                    except:
                        pass
                    
                    await notify_super_admins(
                        context,
                        f"⭐ ОДОБРЕН ОТЗЫВ\nКем: {get_user_link(query.from_user)}\nОт: {approved_review['user_name']} (ID: {approved_review['user_id']})\nID отзыва: {review_id}"
                    )
                    
                    await query.edit_message_text("✅ Отзыв одобрен и опубликован!", reply_markup=admin_kb_review_moderation())
                    return
            
            await query.answer("Отзыв не найден", show_alert=True)

        elif cb_data.startswith("mod_reject:"):
            review_id = cb_data.split(":")[1]
            pending = data.get("pending_reviews", [])
            
            for i, review in enumerate(pending):
                if str(review['id']) == review_id:
                    rejected_review = pending.pop(i)
                    save()
                    
                    try:
                        await context.bot.send_message(
                            chat_id=int(rejected_review['user_id']),
                            text="❌ Ваш отзыв был отклонен модератором.\n\nПожалуйста, убедитесь, что отзыв соответствует правилам сообщества."
                        )
                    except:
                        pass
                    
                    await notify_super_admins(
                        context,
                        f"⭐ ОТКЛОНЕН ОТЗЫВ\nКем: {get_user_link(query.from_user)}\nОт: {rejected_review['user_name']} (ID: {rejected_review['user_id']})\nID отзыва: {review_id}"
                    )
                    
                    await query.edit_message_text("❌ Отзыв отклонен.", reply_markup=admin_kb_review_moderation())
                    return
            
            await query.answer("Отзыв не найден", show_alert=True)

        elif cb_data == "admin_review_all":
            reviews = data.get("reviews", [])
            if not reviews:
                await query.edit_message_text("📝 Нет отзывов.", reply_markup=admin_kb_reviews())
                return
            
            text = "⭐ Все отзывы:\n\n"
            for i, review in enumerate(reviews, 1):
                date = datetime.fromisoformat(review["date"]).strftime("%d.%m.%Y %H:%M")
                text += f"{i}. ID: {review['id']} | Дата: {date}\n👤 Пользователь: {review['user_name']}\n📝 Текст: {review['text']}\n\n"
                if len(text) > 3500:
                    text += "...\n\n(Показаны первые отзывы)"
                    break
            
            await query.edit_message_text(text[:4000], reply_markup=back_btn("admin_menu_reviews"))

        elif cb_data == "admin_review_clear_all":
            count = len(data.get("reviews", []))
            data["reviews"] = []
            save()
            
            await notify_super_admins(
                context,
                f"🗑 УДАЛЕНЫ ВСЕ ОТЗЫВЫ\nКем: {get_user_link(query.from_user)}\nКоличество: {count} отзывов"
            )
            
            await query.answer(f"Удалено {count} отзывов", show_alert=True)
            await query.edit_message_text(f"🗑 Удалено {count} отзывов.", reply_markup=admin_kb_reviews())

        elif cb_data == "admin_review_del_one":
            await query.message.reply_text("❌ Введите ID отзыва для удаления:")
            context.user_data["deleting_review"] = True

        elif cb_data == "admin_broadcast_start":
            if user_id not in SUPER_ADMIN_IDS and not check_perm(user_id, PERM_BROADCAST):
                await query.answer("❌ У вас нет прав на рассылку", show_alert=True)
                return
            await query.message.reply_text(
                "📣 Начало рассылки\n\n"
                "Отправьте сообщение для рассылки (текст, фото, видео, документ).\n"
                "Кнопки добавляются отдельно после сообщения."
            )
            context.user_data["broadcasting"] = True
            context.user_data["broadcast_buttons"] = []

        elif cb_data == "bc_add_btn_yes":
            await query.message.reply_text(
                "➕ Добавление кнопки\n\n"
                "Отправьте текст кнопки (только текст):"
            )
            context.user_data["broadcast_step"] = "wait_btn_text"

        elif cb_data == "bc_add_btn_no":
            if not context.user_data.get("broadcast_msg_id") and not context.user_data.get("broadcast_text"):
                await query.edit_message_text("❌ Сначала отправьте сообщение для рассылки.")
                return

            await show_broadcast_preview(update, context)

        elif cb_data == "bc_edit_msg":
            await query.message.reply_text("✏️ Отправьте исправленное сообщение:")
            context.user_data["broadcasting"] = True

        elif cb_data == "bc_confirm_send":
            await start_broadcast(update, context)

        elif cb_data == "admin_pm":
            await query.message.reply_text(
                "✉️ Отправка личного сообщения\n\nВведите: ID_ПОЛЬЗОВАТЕЛЯ СООБЩЕНИЕ\nПример: 123456789 Привет! Как дела?"
            )
            context.user_data["sending_pm"] = True

        elif cb_data == "admin_toggle_bot":
            BOT_STOPPED = not BOT_STOPPED
            
            status = "остановлен" if BOT_STOPPED else "запущен"
            
            await notify_super_admins(
                context,
                f"⏸ БОТ {'ОСТАНОВЛЕН' if BOT_STOPPED else 'ЗАПУЩЕН'}\nКем: {get_user_link(query.from_user)}"
            )
            
            await query.answer(f"Бот {status}", show_alert=True)
            await query.edit_message_text(f"👑 Админ панель\nБот: {'⏸ ОСТАНОВЛЕН' if BOT_STOPPED else '▶️ ЗАПУЩЕН'}", reply_markup=admin_kb_main(user_id))

    except Exception as e:
        print(f"Callback error: {e}")
        try:
            await query.edit_message_text(f"❌ Ошибка: {e}")
        except:
            pass

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    global data, BOT_STOPPED
    
    print("🤖 Запуск бота...")
    
    # Загрузка данных из файла
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                # Обновляем данные, сохраняя структуру
                for key in DEFAULT_DATA:
                    if key in loaded_data:
                        data[key] = loaded_data[key]
                    else:
                        data[key] = DEFAULT_DATA[key]
            print(f"✅ Данные загружены из {DATA_FILE}")
        except Exception as e:
            print(f"❌ Ошибка загрузки данных: {e}")
            print("🔄 Использую структуру данных по умолчанию")
            data = DEFAULT_DATA.copy()
            save_data()
    else:
        print(f"ℹ️ Файл {DATA_FILE} не найден, создаю новый")
        data = DEFAULT_DATA.copy()
        save_data()
    
    # Проверка структуры данных
    required_keys = ["accounts_common_tanks", "accounts_promo_tanks", "accounts_common_blitz", 
                     "users", "channels", "admins", "promocodes", "reviews", 
                     "pending_reviews", "banned_users", "failed_deliveries", "settings"]
    
    for key in required_keys:
        if key not in data:
            print(f"⚠️ Добавлен отсутствующий ключ: {key}")
            data[key] = DEFAULT_DATA[key]
    
    # Проверка настроек
    if "settings" not in data:
        data["settings"] = DEFAULT_DATA["settings"]
    else:
        for setting_key in DEFAULT_DATA["settings"]:
            if setting_key not in data["settings"]:
                data["settings"][setting_key] = DEFAULT_DATA["settings"][setting_key]
    
    save_data()
    
    print(f"📊 Статистика при запуске:")
    print(f"  👥 Пользователей: {len(data['users'])}")
    print(f"  📦 Аккаунтов TanksBlitz (общая): {len(data['accounts_common_tanks'])}")
    print(f"  📦 Аккаунтов TanksBlitz (промо): {len(data['accounts_promo_tanks'])}")
    print(f"  📦 Аккаунтов WoT Blitz: {len(data['accounts_common_blitz'])}")
    print(f"  🎟 Промокодов: {len(data['promocodes'])}")
    print(f"  ⭐ Отзывов: {len(data['reviews'])} (ожидают: {len(data['pending_reviews'])})")
    print(f"  ⛔ Забанено: {len(data.get('banned_users', []))}")
    
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("panel", panel_command))
    app.add_handler(CommandHandler("info", user_info_command))
    app.add_handler(CommandHandler("promo", lambda u, c: message_handler(u, c)))  # Перенаправление на обработчик сообщений
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, message_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE, message_handler))
    
    app.add_handler(CallbackQueryHandler(main_callback_handler))
    
    print("✅ Бот запущен и готов к работе!")
    print("=" * 50)
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Сохраняем данные перед выходом
        save_data()
        print("💾 Данные сохранены")