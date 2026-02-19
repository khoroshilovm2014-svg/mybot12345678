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
DATA_FILE = "data.db"
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
                # Полностью заменяем данные
                data.clear()
                data.update(loaded_data)
            print(f"✅ Данные загружены из {DATA_FILE}")
            print(f"📊 В файле найдено:")
            print(f"   - Пользователей: {len(data.get('users', {}))}")
            print(f"   - Аккаунтов Tanks: {len(data.get('accounts_common_tanks', []))}")
            return True
        except Exception as e:
            print(f"❌ Ошибка загрузки данных: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        print(f"ℹ️ Файл {DATA_FILE} не найден, будет создан при сохранении")
        data.clear()
        data.update(DEFAULT_DATA)
        save_data()
        return True

def save_data():
    """Сохраняет данные в data.json"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"✅ Данные сохранены в {DATA_FILE}")
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
    
    if not update.effective_user:
        return
        
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
    """Отправляет главное меню пользователю"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    user_id = str(user.id)
    
    # Проверяем, есть ли пользователь в базе
    if user_id not in data["users"]:
        # Если нет, создаем через start
        await start(update, context)
        return
        
    coin_reward = data["settings"]["coin_reward"]
    exchange_price = data["settings"]["exchange_price"]
    user_data = data["users"][user_id]

    pending_message = ""
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
    """Команда /panel для админ-панели"""
    if not update.effective_user:
        return
        
    user = update.effective_user
    if is_admin(user.id):
        await update.message.reply_text("👑 Админ панель\nВыберите раздел:", reply_markup=admin_kb_main(user.id))
    else:
        await update.message.reply_text("❌ У вас нет доступа.", reply_markup=menu(user.id))

async def user_info_command(update: Update, context: CallbackContext):
    """Команда /info для просмотра информации о пользователе"""
    if not update.effective_user:
        return
        
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
    """Получение бесплатного аккаунта"""
    global BOT_STOPPED
    
    if not update.effective_user:
        return
        
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
    """Обработка выбора игры для получения аккаунта"""
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
    """Обмен монет на аккаунт"""
    global BOT_STOPPED
    
    if not update.effective_user:
        return
        
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
    """Обработка выбора игры для обмена монет"""
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
    """Показывает профиль пользователя"""
    global BOT_STOPPED
    
    if not update.effective_user:
        return
        
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
    """Показывает историю полученных аккаунтов"""
    if not update.effective_user:
        return
        
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
    """Проверяет подписку пользователя на каналы"""
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
        except Exception as e:
            print(f"Ошибка проверки подписки для канала {channel}: {e}")
            not_subscribed.append(channel)
    
    return len(not_subscribed) == 0, not_subscribed

async def check_subscription(update: Update, context: CallbackContext):
    """Команда для проверки подписки"""
    if not update.effective_user:
        return
        
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

async def process_promocode(update: Update, context: CallbackContext, promo_code: str):
    """Обработка промокода"""
    if not update.effective_user:
        return
        
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

# Добавим обработчик ошибок
async def error_handler(update: Update, context: CallbackContext):
    """Глобальный обработчик ошибок"""
    try:
        raise context.error
    except AttributeError as e:
        if "'NoneType' object has no attribute 'id'" in str(e):
            print(f"⚠️ Пропущен апдейт без пользователя: {update}")
            return
        print(f"❌ Ошибка: {e}")
    except Exception as e:
        print(f"❌ Необработанная ошибка: {e}")
        import traceback
        traceback.print_exc()

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    global data, BOT_STOPPED
    
    print("🤖 Запуск бота...")
    print("=" * 50)
    
    # Загружаем данные перед всем остальным
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
                # Очищаем и обновляем глобальные данные
                data.clear()
                data.update(loaded_data)
            print(f"✅ Данные загружены из {DATA_FILE}")
        except Exception as e:
            print(f"❌ Ошибка загрузки данных: {e}")
            print("🔄 Использую структуру данных по умолчанию")
            data.clear()
            data.update(DEFAULT_DATA)
            # Пробуем сохранить
            try:
                save_data()
            except:
                pass
    else:
        print(f"ℹ️ Файл {DATA_FILE} не найден, создаю новый")
        data.clear()
        data.update(DEFAULT_DATA)
        save_data()
    
    # Проверка структуры данных и добавление отсутствующих ключей
    required_keys = ["accounts_common_tanks", "accounts_promo_tanks", "accounts_common_blitz", 
                     "users", "channels", "admins", "promocodes", "reviews", 
                     "pending_reviews", "banned_users", "failed_deliveries", "settings"]
    
    data_updated = False
    for key in required_keys:
        if key not in data:
            print(f"⚠️ Добавлен отсутствующий ключ: {key}")
            data[key] = DEFAULT_DATA[key]
            data_updated = True
    
    # Проверка настроек
    if "settings" not in data:
        data["settings"] = DEFAULT_DATA["settings"]
        data_updated = True
    else:
        for setting_key in DEFAULT_DATA["settings"]:
            if setting_key not in data["settings"]:
                data["settings"][setting_key] = DEFAULT_DATA["settings"][setting_key]
                data_updated = True
    
    if data_updated:
        save_data()
        print("✅ Структура данных обновлена")
    
    # Статистика для проверки
    print(f"\n📊 СТАТИСТИКА ПРИ ЗАПУСКЕ:")
    print(f"  👥 Пользователей: {len(data['users'])}")
    print(f"  📦 Аккаунтов TanksBlitz (общая): {len(data['accounts_common_tanks'])}")
    print(f"  📦 Аккаунтов TanksBlitz (промо): {len(data['accounts_promo_tanks'])}")
    print(f"  📦 Аккаунтов WoT Blitz: {len(data['accounts_common_blitz'])}")
    print(f"  🎟 Промокодов: {len(data['promocodes'])}")
    print(f"  ⭐ Отзывов: {len(data['reviews'])} (ожидают: {len(data['pending_reviews'])})")
    print(f"  ⛔ Забанено: {len(data.get('banned_users', []))}")
    print(f"  📢 Каналов: {len(data.get('channels', []))}")
    print(f"  🛡 Админов: {len(data.get('admins', {}))}")
    print("=" * 50)
    
    app = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчик ошибок
    app.add_error_handler(error_handler)
    
    # Добавляем обработчики команд
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("panel", panel_command))
    app.add_handler(CommandHandler("info", user_info_command))
    
    # Добавляем обработчики сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, message_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE, message_handler))
    
    # Добавляем обработчик callback-запросов
    app.add_handler(CallbackQueryHandler(main_callback_handler))
    
    print("✅ Бот запущен и готов к работе!")
    print("=" * 50)
    print("📝 Для остановки бота нажмите Ctrl+C")
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


