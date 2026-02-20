import json
import sys
import asyncio
import random
import string
import sqlite3
from datetime import datetime, timedelta
import os
import logging

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

print("ТЕКУЩАЯ ПАПКА:", os.getcwd())

try:
    from captcha.image import ImageCaptcha
except ImportError:
    print("❌ ОШИБКА: Не установлена библиотека captcha. Выполните: pip install captcha")
    sys.exit()

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton, ChatMember
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from telegram.error import BadRequest, Forbidden

print("Python version:", sys.version)
print("=" * 50)

# --- КОНФИГУРАЦИЯ ---
DB_FILE = "bot_database.db"
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

# ========== РАБОТА С БАЗОЙ ДАННЫХ ==========
class Database:
    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_file)
    
    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                coins INTEGER DEFAULT 0,
                referrer_id INTEGER,
                last_free_account TIMESTAMP,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                banned INTEGER DEFAULT 0,
                captcha_passed INTEGER DEFAULT 1,
                pending_referral INTEGER,
                coins_pending_approval INTEGER DEFAULT 0
            )
            ''')
            
            # Таблица истории
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                account TEXT,
                type TEXT,
                game TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            ''')
            
            # Таблица аккаунтов TanksBlitz
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts_tanks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                login TEXT,
                password TEXT,
                account_type TEXT DEFAULT 'common',
                used_by INTEGER,
                used_at TIMESTAMP,
                FOREIGN KEY (used_by) REFERENCES users(user_id)
            )
            ''')
            
            # Таблица аккаунтов WoT Blitz
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS accounts_blitz (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                login TEXT,
                password TEXT,
                used_by INTEGER,
                used_at TIMESTAMP,
                FOREIGN KEY (used_by) REFERENCES users(user_id)
            )
            ''')
            
            # Таблица промокодов
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                reward INTEGER DEFAULT 1,
                max_uses INTEGER DEFAULT 1,
                used INTEGER DEFAULT 0,
                source TEXT DEFAULT 'common',
                game TEXT DEFAULT 'tanks',
                expires_at TIMESTAMP
            )
            ''')
            
            # Таблица использованных промокодов
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS used_promocodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                code TEXT,
                used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (code) REFERENCES promocodes(code)
            )
            ''')
            
            # Таблица отзывов
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                user_name TEXT,
                text TEXT,
                status TEXT DEFAULT 'pending',
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
            ''')
            
            # Таблица каналов
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT UNIQUE
            )
            ''')
            
            # Таблица админов
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                added_by INTEGER,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Таблица прав админов
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_permissions (
                user_id INTEGER,
                permission TEXT,
                value INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, permission),
                FOREIGN KEY (user_id) REFERENCES admins(user_id)
            )
            ''')
            
            # Таблица настроек
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            ''')
            
            # Таблица failed_deliveries
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS failed_deliveries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                failed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Проверяем и добавляем настройки по умолчанию
            default_settings = {
                'coin_reward': '1',
                'exchange_price': '10',
                'faq_text': """ℹ️ FAQ

🔹 Лимит: 1 бесплатный аккаунт в 24 часа.
🔹 Монеты: Даются ТОЛЬКО за приглашение друзей.
🔹 Условия: Друг должен перейти по вашей ссылке и пройти регистрацию И подписаться на каналы.
🔹 Награда: 1 монета за друга (начисляется после подписки на каналы).
🔹 Обмен: 10 монет = 1 аккаунт.
🔹 Промокоды: Дают аккаунты бесплатно (только из TanksBlitz).
🔹 Поддержка: @texpoddergka2026_bot"""
            }
            
            for key, value in default_settings.items():
                cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
            
            conn.commit()
    
    # ===== ПОЛЬЗОВАТЕЛИ =====
    def get_user(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            return cursor.fetchone()
    
    def create_user(self, user_id, username, full_name, referrer_id=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO users 
                (user_id, username, full_name, referrer_id, join_date)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, full_name, referrer_id, datetime.now().isoformat()))
            
            if referrer_id:
                cursor.execute('''
                    UPDATE users SET pending_referral = ? 
                    WHERE user_id = ?
                ''', (referrer_id, user_id))
            
            conn.commit()
    
    def update_user_coins(self, user_id, coins):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET coins = ? WHERE user_id = ?', (coins, user_id))
            conn.commit()
    
    def add_coins(self, user_id, amount):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET coins = coins + ? WHERE user_id = ?', (amount, user_id))
            conn.commit()
    
    def get_user_coins(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT coins FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result[0] if result else 0
    
    def set_last_free_account(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users SET last_free_account = ? 
                WHERE user_id = ?
            ''', (datetime.now().isoformat(), user_id))
            conn.commit()
    
    def get_last_free_account(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT last_free_account FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result[0] if result else None
    
    def set_captcha_passed(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET captcha_passed = 1 WHERE user_id = ?', (user_id,))
            conn.commit()
    
    def get_captcha_passed(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT captcha_passed FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result[0] if result else 1
    
    def set_pending_referral(self, user_id, referrer_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET pending_referral = ? WHERE user_id = ?', (referrer_id, user_id))
            conn.commit()
    
    def get_pending_referral(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT pending_referral FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result[0] if result else None
    
    def set_coins_pending(self, user_id, value):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET coins_pending_approval = ? WHERE user_id = ?', (1 if value else 0, user_id))
            conn.commit()
    
    def get_coins_pending(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT coins_pending_approval FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return bool(result[0]) if result else False
    
    def get_user_referrer(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT referrer_id FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return result[0] if result else None
    
    def clear_pending_referral(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET pending_referral = NULL WHERE user_id = ?', (user_id,))
            conn.commit()
    
    def is_banned(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT banned FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            return bool(result[0]) if result else False
    
    def ban_user(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET banned = 1 WHERE user_id = ?', (user_id,))
            conn.commit()
    
    def unban_user(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET banned = 0 WHERE user_id = ?', (user_id,))
            conn.commit()
    
    def get_all_users(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users')
            return [row[0] for row in cursor.fetchall()]
    
    def get_users_count(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            return cursor.fetchone()[0]
    
    def get_banned_count(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users WHERE banned = 1')
            return cursor.fetchone()[0]
    
    def get_total_coins(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT SUM(coins) FROM users')
            return cursor.fetchone()[0] or 0
    
    # ===== ИСТОРИЯ =====
    def add_to_history(self, user_id, account, type_, game):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO history (user_id, account, type, game, date)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, account, type_, game, datetime.now().isoformat()))
            conn.commit()
    
    def get_user_history(self, user_id, limit=10):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT account, type, game, date FROM history 
                WHERE user_id = ? ORDER BY date DESC LIMIT ?
            ''', (user_id, limit))
            return cursor.fetchall()
    
    def get_user_received_count(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM history WHERE user_id = ?', (user_id,))
            return cursor.fetchone()[0]
    
    def get_total_accounts_issued(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM history')
            return cursor.fetchone()[0]
    
    # ===== АККАУНТЫ TANKS =====
    def get_free_tanks_account(self, account_type='common'):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, login, password FROM accounts_tanks 
                WHERE account_type = ? AND used_by IS NULL 
                LIMIT 1
            ''', (account_type,))
            return cursor.fetchone()
    
    def use_tanks_account(self, account_id, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE accounts_tanks 
                SET used_by = ?, used_at = ? 
                WHERE id = ?
            ''', (user_id, datetime.now().isoformat(), account_id))
            conn.commit()
    
    def get_tanks_accounts_count(self, account_type='common'):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM accounts_tanks WHERE account_type = ? AND used_by IS NULL', (account_type,))
            return cursor.fetchone()[0]
    
    def add_tanks_accounts(self, accounts, account_type='common'):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for acc in accounts:
                if ':' in acc:
                    login, password = acc.split(':', 1)
                    cursor.execute('''
                        INSERT INTO accounts_tanks (login, password, account_type)
                        VALUES (?, ?, ?)
                    ''', (login.strip(), password.strip(), account_type))
            conn.commit()
    
    def delete_all_tanks_accounts(self, account_type='common'):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM accounts_tanks WHERE account_type = ?', (account_type,))
            conn.commit()
    
    # ===== АККАУНТЫ BLITZ =====
    def get_free_blitz_account(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, login, password FROM accounts_blitz WHERE used_by IS NULL LIMIT 1')
            return cursor.fetchone()
    
    def use_blitz_account(self, account_id, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE accounts_blitz 
                SET used_by = ?, used_at = ? 
                WHERE id = ?
            ''', (user_id, datetime.now().isoformat(), account_id))
            conn.commit()
    
    def get_blitz_accounts_count(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM accounts_blitz WHERE used_by IS NULL')
            return cursor.fetchone()[0]
    
    def add_blitz_accounts(self, accounts):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for acc in accounts:
                if ':' in acc:
                    login, password = acc.split(':', 1)
                    cursor.execute('''
                        INSERT INTO accounts_blitz (login, password)
                        VALUES (?, ?)
                    ''', (login.strip(), password.strip()))
            conn.commit()
    
    def delete_all_blitz_accounts(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM accounts_blitz')
            conn.commit()
    
    # ===== ПРОМОКОДЫ =====
    def get_promocode(self, code):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM promocodes 
                WHERE code = ? AND used < max_uses 
                AND (expires_at IS NULL OR expires_at > ?)
            ''', (code, datetime.now().isoformat()))
            return cursor.fetchone()
    
    def use_promocode(self, code, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE promocodes SET used = used + 1 WHERE code = ?', (code,))
            cursor.execute('INSERT INTO used_promocodes (user_id, code) VALUES (?, ?)', (user_id, code))
            conn.commit()
    
    def has_user_used_promocode(self, user_id, code):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM used_promocodes WHERE user_id = ? AND code = ?', (user_id, code))
            return cursor.fetchone()[0] > 0
    
    def create_promocode(self, code, reward, max_uses, source='common', game='tanks'):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO promocodes (code, reward, max_uses, source, game)
                VALUES (?, ?, ?, ?, ?)
            ''', (code, reward, max_uses, source, game))
            conn.commit()
    
    def get_all_promocodes(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT code, reward, max_uses, used, source, game FROM promocodes')
            return cursor.fetchall()
    
    def get_promocodes_count(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM promocodes')
            return cursor.fetchone()[0]
    
    # ===== ОТЗЫВЫ =====
    def add_review(self, user_id, user_name, text):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO reviews (user_id, user_name, text, status, date)
                VALUES (?, ?, ?, 'pending', ?)
            ''', (user_id, user_name, text, datetime.now().isoformat()))
            conn.commit()
            return cursor.lastrowid
    
    def approve_review(self, review_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE reviews SET status = "approved" WHERE id = ?', (review_id,))
            conn.commit()
    
    def reject_review(self, review_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM reviews WHERE id = ? AND status = "pending"', (review_id,))
            conn.commit()
    
    def get_pending_reviews(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, user_id, user_name, text, date FROM reviews WHERE status = "pending" ORDER BY date DESC')
            return cursor.fetchall()
    
    def get_approved_reviews(self, limit=10):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_name, text, date FROM reviews 
                WHERE status = "approved" ORDER BY date DESC LIMIT ?
            ''', (limit,))
            return cursor.fetchall()
    
    def get_reviews_count(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM reviews WHERE status = "approved"')
            return cursor.fetchone()[0]
    
    def get_pending_reviews_count(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM reviews WHERE status = "pending"')
            return cursor.fetchone()[0]
    
    def delete_review(self, review_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM reviews WHERE id = ?', (review_id,))
            conn.commit()
    
    def delete_all_reviews(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM reviews')
            conn.commit()
    
    # ===== КАНАЛЫ =====
    def get_channels(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT channel FROM channels')
            return [row[0] for row in cursor.fetchall()]
    
    def add_channel(self, channel):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT OR IGNORE INTO channels (channel) VALUES (?)', (channel,))
            conn.commit()
    
    def remove_channel(self, channel):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM channels WHERE channel = ?', (channel,))
            conn.commit()
    
    def get_channels_count(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM channels')
            return cursor.fetchone()[0]
    
    # ===== АДМИНЫ =====
    def is_admin(self, user_id):
        if user_id in SUPER_ADMIN_IDS:
            return True
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM admins WHERE user_id = ?', (user_id,))
            return cursor.fetchone()[0] > 0
    
    def check_perm(self, user_id, perm):
        if user_id in SUPER_ADMIN_IDS:
            return True
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM admin_permissions WHERE user_id = ? AND permission = ?', (user_id, perm))
            result = cursor.fetchone()
            return bool(result[0]) if result else False
    
    def add_admin(self, user_id, name, added_by):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT OR IGNORE INTO admins (user_id, name, added_by) VALUES (?, ?, ?)', 
                          (user_id, name, added_by))
            
            # Добавляем все права по умолчанию
            for perm in DEFAULT_PERMISSIONS:
                cursor.execute('''
                    INSERT OR IGNORE INTO admin_permissions (user_id, permission, value)
                    VALUES (?, ?, ?)
                ''', (user_id, perm, 1 if DEFAULT_PERMISSIONS[perm] else 0))
            conn.commit()
    
    def remove_admin(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM admin_permissions WHERE user_id = ?', (user_id,))
            cursor.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
            conn.commit()
    
    def toggle_perm(self, user_id, perm):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE admin_permissions SET value = NOT value 
                WHERE user_id = ? AND permission = ?
            ''', (user_id, perm))
            conn.commit()
    
    def get_admin_permissions(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT permission, value FROM admin_permissions WHERE user_id = ?', (user_id,))
            return {row[0]: bool(row[1]) for row in cursor.fetchall()}
    
    def get_all_admins(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id, name FROM admins')
            return cursor.fetchall()
    
    def get_admins_count(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM admins')
            return cursor.fetchone()[0]
    
    # ===== НАСТРОЙКИ =====
    def get_setting(self, key):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            result = cursor.fetchone()
            return result[0] if result else None
    
    def set_setting(self, key, value):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
            conn.commit()
    
    # ===== FAILED DELIVERIES =====
    def add_failed_delivery(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO failed_deliveries (user_id) VALUES (?)', (user_id,))
            conn.commit()
    
    def is_failed_delivery(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM failed_deliveries WHERE user_id = ?', (user_id,))
            return cursor.fetchone()[0] > 0
    
    def get_failed_deliveries_count(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(DISTINCT user_id) FROM failed_deliveries')
            return cursor.fetchone()[0]

# Инициализация БД
db = Database()

# ========== ФУНКЦИИ ДЛЯ БЕЗОПАСНОГО РЕДАКТИРОВАНИЯ ==========
async def safe_edit_message(query, new_text, new_markup=None):
    """Безопасно редактирует сообщение, избегая ошибки 'Message not modified'"""
    try:
        await query.edit_message_text(new_text, reply_markup=new_markup)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise e

async def safe_edit_markup(query, new_markup):
    """Безопасно обновляет клавиатуру, избегая ошибки 'Message not modified'"""
    try:
        await query.edit_message_reply_markup(reply_markup=new_markup)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise e

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def get_user_link(user):
    if hasattr(user, 'id'):
        return f'<a href="tg://user?id={user.id}">{user.full_name}</a> (ID: <code>{user.id}</code>)'
    return f'<a href="tg://user?id={user}">Пользователь</a> (ID: <code>{user}</code>)'

async def notify_super_admins(context: ContextTypes.DEFAULT_TYPE, text: str):
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
            print(f"❌ Ошибка отправки уведомления {owner_id}: {e}")
            # Игнорируем ошибку и продолжаем

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
    if db.is_admin(user_id):
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

def admin_kb_main(user_id, bot_stopped=False):
    status_icon = "▶️" if not bot_stopped else "⏸"
    
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
    if db.check_perm(user_id, PERM_ACCS):
        row2.append(InlineKeyboardButton("📦 Аккаунты", callback_data="admin_menu_accs"))
    if db.check_perm(user_id, PERM_PROMOS):
        row2.append(InlineKeyboardButton("🎟 Промокоды", callback_data="admin_menu_promo"))
    if row2: 
        kb.append(row2)

    row3 = []
    if db.check_perm(user_id, PERM_REVIEWS):
        row3.append(InlineKeyboardButton("⭐ Отзывы", callback_data="admin_menu_reviews"))
    if db.check_perm(user_id, PERM_BAN):
        row3.append(InlineKeyboardButton("👥 Пользователи", callback_data="admin_menu_users"))
    if row3: 
        kb.append(row3)

    row4 = []
    if db.check_perm(user_id, PERM_BROADCAST):
        row4.append(InlineKeyboardButton("📣 Рассылка", callback_data="admin_broadcast_start"))
    row4.append(InlineKeyboardButton("✉️ ЛС", callback_data="admin_pm"))
    if row4: 
        kb.append(row4)

    row5 = []
    if db.check_perm(user_id, PERM_CHANNELS):
        row5.append(InlineKeyboardButton("📢 Каналы", callback_data="admin_menu_channels"))
    if db.check_perm(user_id, PERM_ADD_ADMIN):
        row5.append(InlineKeyboardButton("🛡 Админы", callback_data="admin_menu_admins"))
    if row5: 
        kb.append(row5)

    if db.check_perm(user_id, PERM_SETTINGS):
        kb.append([InlineKeyboardButton("⚙️ Настройки", callback_data="admin_menu_settings")])

    kb.append([InlineKeyboardButton(f"{status_icon} Стоп/Старт Бот", callback_data="admin_toggle_bot")])
    kb.append([InlineKeyboardButton("❌ Закрыть", callback_data="admin_close")])
    
    return InlineKeyboardMarkup(kb)

def admin_kb_accounts():
    total_accounts = db.get_tanks_accounts_count('common') + db.get_tanks_accounts_count('promo') + db.get_blitz_accounts_count()
    
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
    admins = db.get_all_admins()
    for adm_id, name in admins:
        kb.append([InlineKeyboardButton(f"👤 {name}", callback_data=f"adm_edit:{adm_id}")])
    kb.append([InlineKeyboardButton("➕ Назначить админа", callback_data="admin_add_new")])
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_main")])
    return InlineKeyboardMarkup(kb)

def admin_kb_admin_rights(target_id):
    perms = db.get_admin_permissions(target_id)
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
    pending_count = db.get_pending_reviews_count()
    approved_count = db.get_reviews_count()
    
    kb = []
    
    if pending_count > 0:
        kb.append([InlineKeyboardButton(f"⏳ Ожидают ({pending_count})", callback_data="mod_view_pending")])
    
    kb.append([InlineKeyboardButton(f"✅ Опубликованные ({approved_count})", callback_data="mod_view_approved")])
    kb.append([InlineKeyboardButton("🔙 Назад", callback_data="admin_menu_reviews")])
    
    return InlineKeyboardMarkup(kb)

# ========== ФУНКЦИИ ДЛЯ РАССЫЛКИ ==========
async def handle_broadcast_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        context.user_data["broadcast_entities"] = msg.caption_entities if msg.caption else None
    
    await msg.reply_text("✅ Контент получен. Добавить кнопку с ссылкой?", reply_markup=broadcast_add_btn_kb())
    context.user_data["broadcast_step"] = "wait_decision"

async def show_broadcast_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    users = db.get_all_users()
    total_users = len(users)
    
    progress_msg = await query.message.reply_text(f"📊 Рассылка начата...\nОбработано: 0/{total_users}")
    
    for i, uid in enumerate(users, 1):
        if i % 50 == 0:
            try:
                await progress_msg.edit_text(f"📊 Рассылка в процессе...\nОбработано: {i}/{total_users}\nОтправлено: {count}")
            except:
                pass
        
        if db.is_failed_delivery(uid):
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
            db.add_failed_delivery(uid)
        except Exception as e:
            error_count += 1
            db.add_failed_delivery(uid)
    
    await notify_super_admins(
        context,
        f"📣 ВЫПОЛНЕНА РАССЫЛКА\nКем: {get_user_link(query.from_user)}\nОтправлено: {count} пользователям\nЗаблокировали бота: {block_count}\nОшибок: {error_count}\nПропущено: {skipped_count}\nВсего в базе: {total_users}"
    )
    
    try:
        await progress_msg.delete()
    except:
        pass
    
    await query.edit_message_text(
        f"✅ Рассылка завершена!\n\n📊 Статистика:\n• Отправлено: {count}\n• Заблокировали бота: {block_count}\n• Ошибок: {error_count}\n• Пропущено: {skipped_count}\n• Всего в базе: {total_users}"
    )
    
    for key in ["broadcast_step", "broadcast_msg_id", "broadcast_chat_id", 
                "broadcast_btn_text", "broadcast_btn_url", "broadcast_text",
                "broadcast_buttons", "broadcast_has_media", "broadcast_entities"]:
        if key in context.user_data:
            del context.user_data[key]

# ========== FAQ С ФОРМАТИРОВАНИЕМ ==========
async def about_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает FAQ с сохраненным форматированием"""
    faq_text = db.get_setting('faq_text')
    await update.message.reply_text(
        faq_text,
        reply_markup=menu(update.effective_user.id)
    )

async def save_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сохраняет FAQ с форматированием"""
    msg = update.message
    db.set_setting('faq_text', msg.text)
    await notify_super_admins(context, f"📝 ИЗМЕНЕН ТЕКСТ FAQ\nКем: {get_user_link(update.effective_user)}\nДлина текста: {len(msg.text)} символов")
    await msg.reply_text("✅ Текст FAQ обновлен! Предпросмотр:", reply_markup=back_btn("admin_menu_settings"))
    await msg.reply_text(msg.text)
    context.user_data["setting_faq"] = False

# ========== ОСНОВНЫЕ ФУНКЦИИ БОТА ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_stopped = context.application.bot_data.get("bot_stopped", False)
    if bot_stopped and not db.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Бот временно остановлен.")
        return

    user = update.effective_user
    user_id = user.id
    
    new_referrer = None
    if context.args and len(context.args) > 0:
        possible_id = context.args[0]
        if possible_id.isdigit() and int(possible_id) != user_id:
            if db.get_user(int(possible_id)):
                new_referrer = int(possible_id)

    # СОЗДАНИЕ ПОЛЬЗОВАТЕЛЯ (если новый)
    if not db.get_user(user_id):
        db.create_user(user_id, user.username, user.full_name, new_referrer)
        print(f"✅ Создан новый пользователь {user_id}")
        
        if new_referrer:
            await notify_super_admins(
                context,
                f"👤 НОВЫЙ ПОЛЬЗОВАТЕЛЬ ПО РЕФЕРАЛУ!\nИмя: {get_user_link(user)}\nПригласил: {new_referrer}"
            )
        else:
            await notify_super_admins(
                context,
                f"👤 НОВЫЙ ПОЛЬЗОВАТЕЛЬ!\nИмя: {get_user_link(user)}"
            )

    # Проверка капчи
    if not db.get_captcha_passed(user_id):
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
        
        ref_id = db.get_user_referrer(user_id)
        
        if ref_id:
            is_sub, not_sub_list = await check_subscription_logic(user.id, context)
            
            if is_sub:
                reward = int(db.get_setting('coin_reward'))
                db.add_coins(ref_id, reward)
                db.clear_pending_referral(user_id)
                
                try:
                    await context.bot.send_message(
                        chat_id=ref_id,
                        text=f"💰 Реферальный бонус начислен!\nПо вашей ссылке зарегистрировался новый пользователь: {user.full_name}\nВам начислено: {reward} монет."
                    )
                except: 
                    pass
                
                await notify_super_admins(
                    context,
                    f"🤝 РЕФЕРАЛЬНОЕ НАЧИСЛЕНИЕ\nРефовод: {ref_id}\nРеферал: {get_user_link(user)}\nНачислено: {reward} монет"
                )
            else:
                db.set_coins_pending(user_id, True)
                
                try:
                    await context.bot.send_message(
                        chat_id=ref_id,
                        text=f"⏳ Реферальный бонус ожидает подтверждения\nПо вашей ссылке зарегистрировался новый пользователь: {user.full_name}\nМонеты будут начислены после того, как пользователь подпишется на все каналы."
                    )
                except:
                    pass
                
                await notify_super_admins(
                    context,
                    f"⏳ ОЖИДАЕТСЯ ПОДТВЕРЖДЕНИЕ РЕФЕРАЛА\nРефовод: {ref_id}\nРеферал: {get_user_link(user)}\nСтатус: Ожидает подписки на каналы"
                )

    await send_main_menu(update, context)

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    coin_reward = db.get_setting('coin_reward')
    exchange_price = db.get_setting('exchange_price')

    pending_message = ""
    if db.get_coins_pending(user_id):
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

async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if db.is_admin(user.id):
        bot_stopped = context.application.bot_data.get("bot_stopped", False)
        await update.message.reply_text(
            "👑 Админ панель\nВыберите раздел:", 
            reply_markup=admin_kb_main(user.id, bot_stopped)
        )
    else:
        await update.message.reply_text("❌ У вас нет доступа.", reply_markup=menu(user.id))

async def user_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not db.is_admin(update.effective_user.id): 
        await update.message.reply_text("❌ У вас нет доступа к этой команде.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "ℹ️ Использование команды:\n/info ID_ПОЛЬЗОВАТЕЛЯ\n\n📌 Пример:\n/info 123456789"
        )
        return
    
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом.")
        return
    
    user_data = db.get_user(target_id)
    
    if not user_data:
        await update.message.reply_text(f"❌ Пользователь с ID {target_id} не найден.")
        return
    
    full_name = user_data[2] if len(user_data) > 2 else "Неизвестно"
    coins = user_data[3] if len(user_data) > 3 else 0
    join_date = user_data[6] if len(user_data) > 6 else "Неизвестно"
    banned = user_data[7] if len(user_data) > 7 else 0
    
    history = db.get_user_history(target_id, 5)
    received = db.get_user_received_count(target_id)
    
    tanks_count = 0
    blitz_count = 0
    for acc in history:
        if len(acc) > 2 and acc[2] == GAME_TANKS:
            tanks_count += 1
        elif len(acc) > 2 and acc[2] == GAME_BLITZ:
            blitz_count += 1
    
    info = f"""📊 СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ

👤 Основная информация:
🆔 ID: {target_id}
👤 Имя: {full_name}
📅 Дата регистрации: {join_date}

💰 Экономика:
💎 Монеты: {coins}
🎮 Всего получено аккаунтов: {received}

🎮 Статистика по играм:
• TanksBlitz: {tanks_count} аккаунтов
• WoT Blitz: {blitz_count} аккаунтов

📜 История (последние 5 аккаунтов):"""
    
    if history:
        for i, item in enumerate(history, 1):
            account = item[0] if len(item) > 0 else ""
            type_ = item[1] if len(item) > 1 else ""
            game = item[2] if len(item) > 2 else ""
            date = item[3] if len(item) > 3 else ""
            
            game_name = GAME_NAMES.get(game, "Unknown")
            type_icon = "🎁" if type_ == "daily_free" else ("💎" if type_ == "exchange" else "🎟")
            info += f"\n{i}. {date} {type_icon} ({game_name})\n   {account}"
    else:
        info += "\n📭 История пуста"
    
    info += f"\n\n🔨 Статус: {'⛔ ЗАБАНЕН' if banned else '✅ АКТИВЕН'}"
    
    await update.message.reply_text(info)

async def get_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_stopped = context.application.bot_data.get("bot_stopped", False)
    if bot_stopped and not db.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Бот временно остановлен.")
        return

    user = update.effective_user
    user_id = user.id

    if db.is_banned(user_id):
        await update.message.reply_text("❌ Вы заблокированы.")
        return

    is_sub, not_sub_list = await check_subscription_logic(user.id, context)
    if not is_sub:
        await update.message.reply_text(
            f"🛑 Доступ ограничен!\n\nДля получения аккаунтов необходимо подписаться на наших спонсоров:",
            reply_markup=get_sub_keyboard(not_sub_list)
        )
        return
    
    last_free = db.get_last_free_account(user_id)
    if last_free:
        last_time = datetime.fromisoformat(last_free)
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

async def process_game_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, game):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_id = user.id
    
    if game == GAME_TANKS:
        account = db.get_free_tanks_account('common')
        if not account:
            await query.edit_message_text(f"❌ В базе {GAME_NAMES[game]} пока нет аккаунтов. Попробуйте позже.")
            await context.bot.send_message(chat_id=user.id, text="Возвращаю меню...", reply_markup=menu(user.id))
            return
        
        account_id, login, password = account
        db.use_tanks_account(account_id, user_id)
        account_str = f"{login}:{password}"
    else:
        account = db.get_free_blitz_account()
        if not account:
            await query.edit_message_text(f"❌ В базе {GAME_NAMES[game]} пока нет аккаунтов. Попробуйте позже.")
            await context.bot.send_message(chat_id=user.id, text="Возвращаю меню...", reply_markup=menu(user.id))
            return
        
        account_id, login, password = account
        db.use_blitz_account(account_id, user_id)
        account_str = f"{login}:{password}"

    db.add_to_history(user_id, account_str, "daily_free", game)
    db.set_last_free_account(user_id)
    
    await notify_super_admins(
        context,
        f"🎁 ВЫДАН БЕСПЛАТНЫЙ АККАУНТ\nКому: {get_user_link(user)}\nИгра: {GAME_NAMES[game]}\nАккаунт: {account_str}"
    )

    await query.edit_message_text(
        f"✅ Аккаунт получен!\n\n🎮 Игра: {GAME_NAMES[game]}\n🔐 {account_str}\n\n⚠️ Следующий через 24 часа\n💡 Приглашай друзей, чтобы получать монеты!"
    )
    await context.bot.send_message(chat_id=user.id, text="Выберите действие:", reply_markup=menu(user.id))

async def exchange_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_stopped = context.application.bot_data.get("bot_stopped", False)
    if bot_stopped and not db.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Бот временно остановлен.")
        return

    user_id = update.effective_user.id
    coins = db.get_user_coins(user_id)
    price = int(db.get_setting('exchange_price'))

    if coins < price:
        await update.message.reply_text(
            f"❌ Недостаточно монет!\n\nВаш баланс: {coins} монет\nНужно для обмена: {price} монет\n\n💡 Приглашайте друзей по реферальной ссылке, чтобы получать монеты!",
            reply_markup=menu(user_id)
        )
        return

    await update.message.reply_text(
        "🎮 Выберите игру для обмена монет:\n\n👇 Нажмите на кнопку с нужной игрой:",
        reply_markup=game_selection_keyboard()
    )
    context.user_data["awaiting_game_selection"] = True
    context.user_data["awaiting_account_action"] = "exchange"

async def process_exchange_game_selection(update: Update, context: ContextTypes.DEFAULT_TYPE, game):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    price = int(db.get_setting('exchange_price'))
    
    if game == GAME_TANKS:
        account = db.get_free_tanks_account('common')
        if not account:
            await query.edit_message_text(f"❌ В базе {GAME_NAMES[game]} закончились аккаунты! Попробуйте позже.")
            await context.bot.send_message(chat_id=query.from_user.id, text="Возвращаю меню...", reply_markup=menu(user_id))
            return
        
        account_id, login, password = account
        db.use_tanks_account(account_id, user_id)
        account_str = f"{login}:{password}"
    else:
        account = db.get_free_blitz_account()
        if not account:
            await query.edit_message_text(f"❌ В базе {GAME_NAMES[game]} закончились аккаунты! Попробуйте позже.")
            await context.bot.send_message(chat_id=query.from_user.id, text="Возвращаю меню...", reply_markup=menu(user_id))
            return
        
        account_id, login, password = account
        db.use_blitz_account(account_id, user_id)
        account_str = f"{login}:{password}"
    
    db.update_user_coins(user_id, db.get_user_coins(user_id) - price)
    db.add_to_history(user_id, account_str, "exchange", game)
    
    await notify_super_admins(
        context,
        f"💎 ПОКУПКА ЗА МОНЕТЫ\nПокупатель: {get_user_link(query.from_user)}\nИгра: {GAME_NAMES[game]}\nСтоимость: {price} монет\nАккаунт: {account_str}"
    )
    
    await query.edit_message_text(
        f"✅ Успешный обмен!\n\n🎮 Игра: {GAME_NAMES[game]}\n💎 Списано: {price} монет\n🔐 Аккаунт:\n{account_str}\n\n💡 Продолжайте приглашать друзей за монеты!"
    )
    await context.bot.send_message(chat_id=query.from_user.id, text="Выберите действие:", reply_markup=menu(user_id))

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_stopped = context.application.bot_data.get("bot_stopped", False)
    if bot_stopped and not db.is_admin(update.effective_user.id):
        return

    user = update.effective_user
    user_id = user.id

    user_data = db.get_user(user_id)
    if user_data:
        coins = user_data[3]
        received = db.get_user_received_count(user_id)
        exchange_price = db.get_setting('exchange_price')
        coin_reward = db.get_setting('coin_reward')
        
        pending_coins_info = ""
        if db.get_coins_pending(user_id):
            pending_coins_info = "\n⚠️ У вас есть ожидающие начисления монеты!\nПодпишитесь на все каналы через '✅ Проверить подписку', чтобы получить их."

        last_free = db.get_last_free_account(user_id)
        time_text = ""
        if last_free:
            last = datetime.fromisoformat(last_free)
            next_time = last + timedelta(hours=24)
            if datetime.now() < next_time:
                wait = next_time - datetime.now()
                hours = wait.seconds // 3600
                minutes = (wait.seconds % 3600) // 60
                time_text = f"\n⏰ Следующий бесплатный аккаунт через: {hours}ч {minutes}м"
            else:
                time_text = "\n✅ Можно получить бесплатный аккаунт"

        text = f"""👤 ПРОФИЛЬ

🆔 ID: {user_id}
👤 Имя: {user_data[2]}
📅 Дата регистрации: {user_data[5]}

💰 БАЛАНС:
💎 Монеты: {coins}
🎮 Всего получено аккаунтов: {received}

🔗 ВАША РЕФЕРАЛЬНАЯ ССЫЛКА:
https://t.me/{context.bot.username}?start={user_id}

🎁 Награда за друга: {coin_reward} монет (после подписки на каналы)
💎 Обмен: {exchange_price} монет = 1 аккаунт{time_text}{pending_coins_info}"""

        await update.message.reply_text(text, reply_markup=menu(user.id))
    else:
        await update.message.reply_text("❌ Профиль не найден", reply_markup=menu(user.id))

async def account_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not db.get_user(user_id):
        await update.message.reply_text("❌ Запустите бота через /start", reply_markup=menu(user_id))
        return

    history = db.get_user_history(user_id, 10)

    if not history:
        await update.message.reply_text("📜 История пуста", reply_markup=menu(user_id))
        return

    text = "📜 ИСТОРИЯ (последние 10):\n\n"
    for i, item in enumerate(history, 1):
        account, type_, game, date = item
        date_obj = datetime.fromisoformat(date).strftime("%d.%m %H:%M")
        game_name = GAME_NAMES.get(game, "Unknown")
        type_icon = "🎁" if type_ == "daily_free" else ("💎" if type_ == "exchange" else "🎟")
        text += f"{i}. {date_obj} {type_icon} ({game_name})\n   {account}\n\n"

    await update.message.reply_text(text, reply_markup=menu(user_id))

async def check_subscription_logic(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    channels = db.get_channels()
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

async def check_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_sub, not_sub_list = await check_subscription_logic(user_id, context)
    
    if is_sub:
        if db.get_coins_pending(user_id):
            ref_id = db.get_pending_referral(user_id) or db.get_user_referrer(user_id)
            
            if ref_id and db.get_user(ref_id):
                reward = int(db.get_setting('coin_reward'))
                db.add_coins(ref_id, reward)
                db.set_coins_pending(user_id, False)
                db.clear_pending_referral(user_id)
                
                try:
                    await context.bot.send_message(
                        chat_id=ref_id,
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

# ========== ОБРАБОТКА ПРОМОКОДОВ ==========
async def process_promocode(update: Update, context: ContextTypes.DEFAULT_TYPE, promo_code: str):
    user = update.effective_user
    user_id = user.id
    
    if not db.get_user(user_id):
        await update.message.reply_text("❌ Сначала запустите бота через /start")
        return
    
    promo = db.get_promocode(promo_code)
    
    if not promo:
        await update.message.reply_text("❌ Неверный или истекший промокод.")
        return
    
    code, reward, max_uses, used, source, game = promo
    
    if db.has_user_used_promocode(user_id, code):
        await update.message.reply_text("❌ Вы уже использовали этот промокод.")
        return
    
    accounts_given = []
    
    for _ in range(reward):
        if game == GAME_TANKS:
            account = db.get_free_tanks_account(source)
            if account:
                account_id, login, password = account
                db.use_tanks_account(account_id, user_id)
                accounts_given.append(f"{login}:{password}")
            else:
                break
        else:
            account = db.get_free_blitz_account()
            if account:
                account_id, login, password = account
                db.use_blitz_account(account_id, user_id)
                accounts_given.append(f"{login}:{password}")
            else:
                break
    
    if not accounts_given:
        await update.message.reply_text(f"❌ Не удалось выдать аккаунты. Попробуйте позже.")
        return
    
    db.use_promocode(code, user_id)
    
    for acc in accounts_given:
        db.add_to_history(user_id, acc, "promocode", game)
    
    await notify_super_admins(
        context,
        f"🎟 АКТИВИРОВАН ПРОМОКОД\nКем: {get_user_link(user)}\nКод: {code}\nИгра: {GAME_NAMES.get(game, 'Unknown')}\nВыдано аккаунтов: {len(accounts_given)}"
    )
    
    accounts_text = "\n".join(accounts_given)
    await update.message.reply_text(
        f"✅ Промокод активирован!\n\n🎮 Игра: {GAME_NAMES.get(game, 'Unknown')}\n🔐 Аккаунт{'ы' if len(accounts_given) > 1 else ''}:\n{accounts_text}"
    )

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, что сообщение от пользователя
    if not update.effective_user:
        return
    
    bot_stopped = context.application.bot_data.get("bot_stopped", False)
    
    if bot_stopped and not db.is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Бот временно остановлен.")
        return

    user_id = update.effective_user.id
    message = update.message
    
    # Проверяем, что есть текст или подпись
    text = ""
    if message.text:
        text = message.text
    elif message.caption:
        text = message.caption
    
    if db.is_banned(user_id):
        return
    
    if context.user_data.get("awaiting_captcha"):
        correct = context.user_data.get("captcha_correct", "")
        if text.upper() == correct:
            context.user_data["awaiting_captcha"] = False
            context.user_data["just_passed_captcha"] = True
            db.set_captcha_passed(user_id)
            await message.reply_text("✅ Проверка пройдена!\n\nДобро пожаловать в бот!")
            await send_main_menu(update, context)
        else:
            await message.reply_text("❌ Неверный код. Попробуйте ещё раз:")
        return

    # СОХРАНЕНИЕ FAQ
    if context.user_data.get("setting_faq"):
        await save_faq(update, context)
        return

    # ОСТАВЛЕНИЕ ОТЗЫВА
    if context.user_data.get("leaving_review"):
        if len(text) > 500:
            await message.reply_text("❌ Отзыв слишком длинный (макс. 500 символов). Попробуйте снова:")
            return
        if len(text) < 5:
            await message.reply_text("❌ Отзыв слишком короткий (мин. 5 символов). Попробуйте снова:")
            return
        
        review_id = db.add_review(user_id, update.effective_user.full_name, text)
        
        await notify_super_admins(
            context,
            f"⭐ НОВЫЙ ОТЗЫВ НА МОДЕРАЦИЮ\nОт: {get_user_link(update.effective_user)}\nID отзыва: {review_id}\nТекст: {text[:200]}..."
        )
        
        await message.reply_text("✅ Спасибо за отзыв!\n\nВаш отзыв отправлен на модерацию и скоро будет опубликован.")
        context.user_data["leaving_review"] = False
        return

    # ЗАГРУЗКА ФАЙЛА С АККАУНТАМИ
    if context.user_data.get("awaiting_file") and message.document:
        if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_ACCS):
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

    # РАССЫЛКА - ОБРАБОТКА КНОПОК
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
        if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_BROADCAST):
            await message.reply_text("❌ У вас нет прав на рассылку.")
            context.user_data["broadcasting"] = False
            return
        await handle_broadcast_content(update, context)
        return

    # ИЗМЕНЕНИЕ ЦЕНЫ
    if context.user_data.get("setting_price"):
        if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_SETTINGS):
            await message.reply_text("❌ У вас нет прав на изменение настроек.")
            context.user_data["setting_price"] = False
            return
            
        try:
            price = int(text)
            if price < 1:
                await message.reply_text("❌ Цена должна быть положительным числом.")
                return
            
            db.set_setting('exchange_price', str(price))
            
            await notify_super_admins(
                context,
                f"💰 ИЗМЕНЕНА ЦЕНА АККАУНТА\nКем: {get_user_link(update.effective_user)}\nНовая цена: {price} монет"
            )
            
            await message.reply_text(f"✅ Цена аккаунта изменена на {price} монет.", reply_markup=back_btn("admin_menu_settings"))
        except ValueError:
            await message.reply_text("❌ Введите число.")
        context.user_data["setting_price"] = False
        return

    # ИЗМЕНЕНИЕ НАГРАДЫ
    if context.user_data.get("setting_reward"):
        if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_SETTINGS):
            await message.reply_text("❌ У вас нет прав на изменение настроек.")
            context.user_data["setting_reward"] = False
            return
            
        try:
            reward = int(text)
            if reward < 1:
                await message.reply_text("❌ Награда должна быть положительным числом.")
                return
            
            db.set_setting('coin_reward', str(reward))
            
            await notify_super_admins(
                context,
                f"🤝 ИЗМЕНЕНА НАГРАДА ЗА РЕФЕРАЛА\nКем: {get_user_link(update.effective_user)}\nНовая награда: {reward} монет"
            )
            
            await message.reply_text(f"✅ Награда за реферала изменена на {reward} монет.", reply_markup=back_btn("admin_menu_settings"))
        except ValueError:
            await message.reply_text("❌ Введите число.")
        context.user_data["setting_reward"] = False
        return

    # ДОБАВЛЕНИЕ КАНАЛА
    if context.user_data.get("adding_channel"):
        if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_CHANNELS):
            await message.reply_text("❌ У вас нет прав на управление каналами.")
            context.user_data["adding_channel"] = False
            return
            
        channel = text.strip()
        channels = db.get_channels()
        if channel not in channels:
            db.add_channel(channel)
            
            await notify_super_admins(
                context,
                f"📢 ДОБАВЛЕН КАНАЛ\nКем: {get_user_link(update.effective_user)}\nКанал: {channel}"
            )
            
            await message.reply_text(f"✅ Канал добавлен: {channel}", reply_markup=admin_kb_channels())
        else:
            await message.reply_text("❌ Канал уже есть в списке.")
        context.user_data["adding_channel"] = False
        return

    # УДАЛЕНИЕ КАНАЛА
    if context.user_data.get("deleting_channel"):
        if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_CHANNELS):
            await message.reply_text("❌ У вас нет прав на управление каналами.")
            context.user_data["deleting_channel"] = False
            return
            
        channel = text.strip()
        channels = db.get_channels()
        if channel in channels:
            db.remove_channel(channel)
            
            await notify_super_admins(
                context,
                f"📢 УДАЛЕН КАНАЛ\nКем: {get_user_link(update.effective_user)}\nКанал: {channel}"
            )
            
            await message.reply_text(f"✅ Канал удален: {channel}", reply_markup=admin_kb_channels())
        else:
            await message.reply_text("❌ Канал не найден в списке.")
        context.user_data["deleting_channel"] = False
        return

    # ДОБАВЛЕНИЕ АДМИНА
    # ДОБАВЛЕНИЕ АДМИНА
    if context.user_data.get("adding_admin"):
        if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_ADD_ADMIN):
            await message.reply_text("❌ У вас нет прав на добавление админов.")
            context.user_data["adding_admin"] = False
            return
            
        try:
            new_admin_id = int(text.strip())
            if new_admin_id == user_id:
                await message.reply_text("❌ Нельзя добавить самого себя.")
                return
                
            if db.is_admin(new_admin_id):
                await message.reply_text("❌ Этот пользователь уже админ.")
                return
                
            try:
                user_info = await context.bot.get_chat(new_admin_id)
                admin_name = user_info.full_name
            except Exception as e:
                print(f"❌ Ошибка получения информации о пользователе {new_admin_id}: {e}")
                admin_name = f"ID: {new_admin_id}"
                # Всё равно добавляем админа, даже если не можем получить имя
                pass
            
            db.add_admin(new_admin_id, admin_name, user_id)
            
            await notify_super_admins(
                context,
                f"🛡 НАЗНАЧЕН НОВЫЙ АДМИН\nКем: {get_user_link(update.effective_user)}\nАдмин: {admin_name} (ID: {new_admin_id})"
            )
            
            try:
                await context.bot.send_message(
                    chat_id=new_admin_id,
                    text="🎉 Поздравляем!\n\nВы были назначены администратором бота. Используйте команду /panel для доступа к админ-панели."
                )
            except Exception as e:
                print(f"❌ Не удалось отправить уведомление новому админу {new_admin_id}: {e}")
                
            await message.reply_text(f"✅ Пользователь {admin_name} назначен админом!", reply_markup=admin_kb_admins_list())
        except ValueError:
            await message.reply_text("❌ Введите числовой ID.")
        context.user_data["adding_admin"] = False
        return

    # СОЗДАНИЕ ПРОМОКОДА
    if context.user_data.get("creating_promo"):
        if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_PROMOS):
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
                
            if db.get_promocode(code):
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

    # БАН ПОЛЬЗОВАТЕЛЯ (БЕЗ УВЕДОМЛЕНИЯ ПОЛЬЗОВАТЕЛЮ)
    if context.user_data.get("banning_user"):
        if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_BAN):
            await message.reply_text("❌ У вас нет прав на бан пользователей.")
            context.user_data["banning_user"] = False
            return
            
        target_id = text.strip()
        
        if not target_id.isdigit():
            await message.reply_text("❌ ID должен состоять только из цифр.")
            return
            
        target_id = int(target_id)
        
        if db.is_banned(target_id):
            await message.reply_text("❌ Этот пользователь уже забанен.")
            return
            
        if target_id in SUPER_ADMIN_IDS:
            await message.reply_text("❌ Нельзя забанить супер-админа!")
            return
            
        if db.is_admin(target_id):
            await message.reply_text("❌ Нельзя забанить админа. Сначала удалите его из админов.")
            return
            
        if db.get_user(target_id):
            db.ban_user(target_id)
            
            await notify_super_admins(
                context,
                f"⛔ ЗАБАНЕН ПОЛЬЗОВАТЕЛЬ\nКем: {get_user_link(update.effective_user)}\nID пользователя: {target_id}"
            )
            
            await message.reply_text(f"✅ Пользователь {target_id} забанен.", reply_markup=admin_kb_users())
        else:
            await message.reply_text("❌ Пользователь не найден в базе.")
        context.user_data["banning_user"] = False
        return

    # РАЗБАН ПОЛЬЗОВАТЕЛЯ (БЕЗ УВЕДОМЛЕНИЯ ПОЛЬЗОВАТЕЛЮ)
    if context.user_data.get("unbanning_user"):
        if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_BAN):
            await message.reply_text("❌ У вас нет прав на разбан пользователей.")
            context.user_data["unbanning_user"] = False
            return
            
        target_id = text.strip()
        
        if not target_id.isdigit():
            await message.reply_text("❌ ID должен состоять только из цифр.")
            return
            
        target_id = int(target_id)
        
        if db.is_banned(target_id):
            db.unban_user(target_id)
            
            await notify_super_admins(
                context,
                f"✅ РАЗБАНЕН ПОЛЬЗОВАТЕЛЬ\nКем: {get_user_link(update.effective_user)}\nID пользователя: {target_id}"
            )
            
            await message.reply_text(f"✅ Пользователь {target_id} разбанен.", reply_markup=admin_kb_users())
        else:
            await message.reply_text("❌ Этот пользователь не забанен.")
        context.user_data["unbanning_user"] = False
        return

    # УДАЛЕНИЕ ОТЗЫВА
    if context.user_data.get("deleting_review"):
        if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_REVIEWS):
            await message.reply_text("❌ У вас нет прав на удаление отзывов.")
            context.user_data["deleting_review"] = False
            return
            
        review_id = text.strip()
        
        if not review_id.isdigit():
            await message.reply_text("❌ ID должен быть числом.")
            return
            
        db.delete_review(int(review_id))
        
        await notify_super_admins(
            context,
            f"🗑 УДАЛЕН ОТЗЫВ\nКем: {get_user_link(update.effective_user)}\nID отзыва: {review_id}"
        )
        
        await message.reply_text(f"✅ Отзыв с ID {review_id} удален.", reply_markup=admin_kb_reviews())
        context.user_data["deleting_review"] = False
        return

    # ОТПРАВКА ЛИЧНОГО СООБЩЕНИЯ
    if context.user_data.get("sending_pm"):
        parts = text.strip().split(' ', 1)
        if len(parts) < 2:
            await message.reply_text("❌ Неверный формат. Нужно: ID_ПОЛЬЗОВАТЕЛЯ СООБЩЕНИЕ\nПример: 123456789 Привет!")
            return
            
        target_id, pm_text = parts[0], parts[1]
        
        if not target_id.isdigit():
            await message.reply_text("❌ ID должен состоять только из цифр.")
            return
            
        target_id = int(target_id)
        
        try:
            await context.bot.send_message(
                chat_id=target_id,
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
        await message.reply_text("🎟 Введите промокод:\n")
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
        if db.is_admin(user_id):
            await panel_command(update, context)
        else:
            await send_main_menu(update, context)

# ========== ОБРАБОТЧИК CALLBACK ==========
async def main_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cb_data = query.data 
    user_id = query.from_user.id
    
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
        reviews = db.get_approved_reviews(10)
        if not reviews:
            await query.message.reply_text("📝 Пока нет отзывов. Будьте первым!", reply_markup=reviews_keyboard())
            return
        
        text = "⭐ Опубликованные отзывы:\n\n"
        for i, (user_name, review_text, date) in enumerate(reviews, 1):
            date_obj = datetime.fromisoformat(date).strftime("%d.%m.%Y")
            text += f"{i}. {review_text}\n   👤 {user_name} • {date_obj}\n\n"
        
        total = db.get_reviews_count()
        if total > 10:
            text += f"\n📊 Всего отзывов: {total}"
        
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
            if db.get_coins_pending(user_id):
                ref_id = db.get_pending_referral(user_id) or db.get_user_referrer(user_id)
                if ref_id and db.get_user(ref_id):
                    reward = int(db.get_setting('coin_reward'))
                    db.add_coins(ref_id, reward)
                    db.set_coins_pending(user_id, False)
                    db.clear_pending_referral(user_id)
                    
                    try:
                        await context.bot.send_message(
                            chat_id=ref_id,
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

    if not db.is_admin(user_id):
        return

    try:
        if cb_data == "admin_main":
            context.user_data.clear()
            bot_stopped = context.application.bot_data.get("bot_stopped", False)
            await query.edit_message_text("👑 Админ панель", reply_markup=admin_kb_main(user_id, bot_stopped))
        
        elif cb_data == "admin_stats":
            total_accounts_issued = db.get_total_accounts_issued()
            total_coins = db.get_total_coins()
            banned_count = db.get_banned_count()
            total_in_stock = db.get_tanks_accounts_count('common') + db.get_tanks_accounts_count('promo') + db.get_blitz_accounts_count()
            
            stats = f"""📊 Статистика бота

👥 Пользователей: {db.get_users_count()}
⛔️ Забанено: {banned_count}
📦 Аккаунтов в наличии: {total_in_stock}
🎮 Всего выдано аккаунтов: {total_accounts_issued}
💰 Всего монет у пользователей: {total_coins}
🎟 Промокодов: {db.get_promocodes_count()}
⭐️ Отзывов: {db.get_reviews_count()} (⏳ {db.get_pending_reviews_count()} на модерации)
📢 Каналов: {db.get_channels_count()}
🛡 Админов (доп): {db.get_admins_count()}

⏸️ Бот {'остановлен' if context.application.bot_data.get('bot_stopped', False) else 'работает'}"""
            await safe_edit_message(query, stats, back_btn())

        elif cb_data == "admin_menu_accs":
            if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_ACCS):
                await query.answer("❌ У вас нет прав на управление аккаунтами", show_alert=True)
                return
            
            await safe_edit_message(query, "📦 Управление аккаунтами", admin_kb_accounts())
            
        elif cb_data == "admin_select_game":
            await safe_edit_message(query, "🎮 Выберите игру для управления:", admin_kb_acc_game_selection())
            
        elif cb_data.startswith("admin_game_"):
            game = cb_data.split("_")[2]
            if game in [GAME_TANKS, GAME_BLITZ]:
                context.user_data["selected_admin_game"] = game
                game_name = GAME_NAMES[game]
                
                if game == GAME_TANKS:
                    common_count = db.get_tanks_accounts_count('common')
                    promo_count = db.get_tanks_accounts_count('promo')
                    text = f"""📦 Управление аккаунтами для {game_name}
                    
📊 Статистика:
• Общая база: {common_count} шт.
• Промо база: {promo_count} шт.
• Всего: {common_count + promo_count} шт."""
                else:
                    common_count = db.get_blitz_accounts_count()
                    text = f"""📦 Управление аккаунтами для {game_name}
                    
📊 Статистика:
• Общая база: {common_count} шт.
• Промо база: Нет (только общая база)"""
                
                await safe_edit_message(query, text, admin_kb_acc_actions_for_game(game))
            
        elif cb_data == "admin_menu_promo":
            if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_PROMOS):
                await query.answer("❌ У вас нет прав на управление промокодами", show_alert=True)
                return
            await safe_edit_message(query, "🎟 Управление промокодами (только для TanksBlitz)", admin_kb_promo())

        elif cb_data == "admin_menu_users":
            if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_BAN):
                await query.answer("❌ У вас нет прав на управление пользователями", show_alert=True)
                return
            await safe_edit_message(
                query,
                f"👥 Управление пользователями\nВсего юзеров: {db.get_users_count()}\nВ бане: {db.get_banned_count()}", 
                admin_kb_users()
            )

        elif cb_data == "admin_menu_reviews":
            if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_REVIEWS):
                await query.answer("❌ У вас нет прав на модерацию отзывов", show_alert=True)
                return
            await safe_edit_message(
                query,
                f"⭐ Управление отзывами\n\n⏳ Ожидают модерации: {db.get_pending_reviews_count()}\n✅ Опубликовано: {db.get_reviews_count()}", 
                admin_kb_reviews()
            )
            
        elif cb_data == "admin_menu_settings":
            if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_SETTINGS):
                await query.answer("❌ У вас нет прав на настройки", show_alert=True)
                return
            settings_text = f"""⚙️ НАСТРОЙКИ БОТА
            
💰 Цена аккаунта: {db.get_setting('exchange_price')} монет
🤝 Награда за реферала: {db.get_setting('coin_reward')} монет
📝 Текст FAQ: {len(db.get_setting('faq_text'))} символов"""
            await safe_edit_message(query, settings_text, admin_kb_settings())

        elif cb_data == "admin_close":
            await query.delete_message()
            
        elif cb_data == "admin_acc_load":
            if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_ACCS):
                await query.answer("❌ У вас нет прав на загрузку аккаунтов", show_alert=True)
                return
            await query.message.reply_text("🔄 Отправьте .txt файл с аккаунтами (почта:пароль).")
            context.user_data["awaiting_file"] = True

        elif cb_data.startswith("upload_to_common_") or cb_data.startswith("upload_to_promo_"):
            accounts = context.user_data.get("temp_accounts", [])
            if not accounts:
                await safe_edit_message(query, "❌ Ошибка: список аккаунтов пуст или утерян.")
                return
            
            parts = cb_data.split("_")
            target_type = parts[2]
            game = parts[3]
            
            if game == GAME_BLITZ and target_type == "promo":
                await safe_edit_message(query, "❌ Для WoT Blitz нет промо-базы. Можно загружать только в общую базу.")
                return
            
            if game == GAME_TANKS:
                db.add_tanks_accounts(accounts, target_type)
            else:
                db.add_blitz_accounts(accounts)
            
            name_map = {"common": "ОБЩУЮ", "promo": "ПРОМО"}
            game_map = {"tanks": "TanksBlitz", "blitz": "WoT Blitz"}
            
            await notify_super_admins(
                context,
                f"📦 ЗАГРУЖЕНЫ АККАУНТЫ\nКем: {get_user_link(query.from_user)}\nИгра: {game_map[game]}\nБаза: {name_map[target_type]}\nКоличество: {len(accounts)} аккаунтов"
            )
            
            await safe_edit_message(query, f"✅ Успешно добавлено {len(accounts)} аккаунтов в {name_map[target_type]} базу {game_map[game]}!", 
                                          admin_kb_acc_actions_for_game(game))
            context.user_data["temp_accounts"] = []

        elif cb_data.startswith("admin_acc_del_common_") or cb_data.startswith("admin_acc_del_promo_"):
            parts = cb_data.split("_")
            target_type = parts[3]
            game = parts[4]
            
            if game == GAME_BLITZ and target_type == "promo":
                await query.answer("Для WoT Blitz нет промо-базы", show_alert=True)
                return
            
            if game == GAME_TANKS:
                count = db.get_tanks_accounts_count(target_type)
                db.delete_all_tanks_accounts(target_type)
            else:
                count = db.get_blitz_accounts_count()
                db.delete_all_blitz_accounts()
            
            game_map = {"tanks": "TanksBlitz", "blitz": "WoT Blitz"}
            
            await notify_super_admins(
                context,
                f"🗑 УДАЛЕНЫ АККАУНТЫ\nКем: {get_user_link(query.from_user)}\nИгра: {game_map[game]}\nБаза: {target_type}\nКоличество: {count} аккаунтов"
            )
            
            await query.answer(f"Удалено {count} аккаунтов из {target_type} базы {game_map[game]}", show_alert=True)
            await safe_edit_message(query, "📦 Аккаунты обновлены", admin_kb_acc_actions_for_game(game))

        elif cb_data == "set_price":
            await query.message.reply_text(f"💰 Введите новую цену аккаунта (сейчас: {db.get_setting('exchange_price')}):")
            context.user_data["setting_price"] = True
            
        elif cb_data == "set_reward":
            await query.message.reply_text(f"🤝 Введите новую награду за рефа (сейчас: {db.get_setting('coin_reward')}):")
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
                await safe_edit_message(query, "❌ Ошибка: данные промокода не найдены.")
                return
            
            source = cb_data.split("_")[2]
            code = promo_data["code"]
            reward = promo_data["reward"]
            max_uses = promo_data["max_uses"]
            
            db.create_promocode(code, reward, max_uses, source, GAME_TANKS)
            
            src_name = "ОБЩЕЙ" if source == "common" else "ПРОМО"
            
            await notify_super_admins(
                context,
                f"🎟 СОЗДАН ПРОМОКОД\nКем: {get_user_link(query.from_user)}\nКод: {code}\nНаграда: {reward} аккаунтов\nЛимит: {max_uses} использований\nБаза: {src_name}"
            )
            
            await safe_edit_message(query, f"✅ Промокод {code} создан!\nИгра: TanksBlitz\nИсточник аккаунтов: с {src_name} базы.", back_btn("admin_menu_promo"))
            context.user_data["temp_promo_data"] = {}

        elif cb_data == "admin_channel_list":
            channels = db.get_channels()
            ch_list = "\n".join(channels) if channels else "Пусто"
            await safe_edit_message(query, f"📢 Каналы:\n{ch_list}", admin_kb_channels())
            
        elif cb_data == "admin_channel_add":
            if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_CHANNELS):
                await query.answer("❌ У вас нет прав на управление каналами", show_alert=True)
                return
            await query.message.reply_text("➕ Введите ссылку или @username канала (бот должен быть админом):")
            context.user_data["adding_channel"] = True

        elif cb_data == "admin_channel_del":
            if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_CHANNELS):
                await query.answer("❌ У вас нет прав на управление каналами", show_alert=True)
                return
            await query.message.reply_text("➖ Введите ссылку канала для удаления:")
            context.user_data["deleting_channel"] = True

        elif cb_data == "admin_menu_channels":
            if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_CHANNELS):
                await query.answer("❌ У вас нет прав на управление каналами", show_alert=True)
                return
            await safe_edit_message(query, "📢 Управление каналами", admin_kb_channels())
            
        elif cb_data == "admin_menu_admins":
            if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_ADD_ADMIN):
                await query.answer("❌ У вас нет прав на управление админами", show_alert=True)
                return
            await safe_edit_message(query, "🛡 Управление админами", admin_kb_admins_list())
            
        elif cb_data == "admin_add_new":
            await query.message.reply_text("👤 Введите ID нового админа:")
            context.user_data["adding_admin"] = True
            
        elif cb_data.startswith("adm_edit:"):
            target_id = int(cb_data.split(":")[1])
            try:
                user_info = await context.bot.get_chat(target_id)
                admin_name = user_info.full_name if user_info else f"ID: {target_id}"
            except Exception as e:
                print(f"❌ Ошибка получения информации о пользователе {target_id}: {e}")
                admin_name = f"ID: {target_id}"
            await safe_edit_message(query, f"⚙️ Права для {admin_name}", admin_kb_admin_rights(target_id))

        elif cb_data.startswith("adm_toggle:"):
            _, target_id, perm = cb_data.split(":")
            target_id = int(target_id)
            db.toggle_perm(target_id, perm)
            await safe_edit_markup(query, admin_kb_admin_rights(target_id))

        elif cb_data.startswith("adm_delete:"):
            target_id = int(cb_data.split(":")[1])
            try:
                user_info = await context.bot.get_chat(target_id)
                admin_name = user_info.full_name if user_info else f"ID: {target_id}"
            except Exception as e:
                print(f"❌ Ошибка получения информации о пользователе {target_id}: {e}")
                admin_name = f"ID: {target_id}"
            db.remove_admin(target_id)
            
            await notify_super_admins(
                context,
                f"🗑 УДАЛЕН АДМИН\nКем: {get_user_link(query.from_user)}\nАдмин: {admin_name} (ID: {target_id})"
            )
            
            await safe_edit_message(query, f"✅ Админ {admin_name} удален", admin_kb_admins_list())

        elif cb_data == "admin_promo_list":
            promos = db.get_all_promocodes()
            if not promos:
                await safe_edit_message(query, "🎟 Нет активных промокодов.")
                return
            
            text = "🎟 АКТИВНЫЕ ПРОМОКОДЫ:\n\n"
            for code, reward, max_uses, used, source, game in promos:
                uses = f"{used}/{max_uses}"
                source_name = "ОБЩАЯ" if source == "common" else "ПРОМО"
                game_name = GAME_NAMES.get(game, "Unknown")
                text += f"• {code} - {reward} акк. ({game_name})\n  Использовано: {uses} | Источник: {source_name}\n\n"
            
            await safe_edit_message(query, text, back_btn("admin_menu_promo"))

        elif cb_data == "admin_user_ban":
            await query.message.reply_text("⛔ Введите ID пользователя для бана:")
            context.user_data["banning_user"] = True

        elif cb_data == "admin_user_unban":
            await query.message.reply_text("✅ Введите ID пользователя для разбана:")
            context.user_data["unbanning_user"] = True

        elif cb_data == "admin_review_moderate":
            await safe_edit_message(query, "⭐ МОДЕРАЦИЯ ОТЗЫВОВ", admin_kb_review_moderation())

        elif cb_data == "mod_view_pending":
            pending = db.get_pending_reviews()
            if not pending:
                await safe_edit_message(query, "⏳ Нет отзывов на модерации.", admin_kb_review_moderation())
                return
            
            for review in pending[:5]:
                review_id, user_id, user_name, text, date = review
                date_obj = datetime.fromisoformat(date).strftime("%d.%m.%Y %H:%M")
                text_msg = f"⏳ ОТЗЫВ НА МОДЕРАЦИИ\n\nID: {review_id}\nДата: {date_obj}\n👤 Пользователь: {user_name} (ID: {user_id})\n\n📝 Текст:\n{text}"
                
                await query.message.reply_text(text_msg, reply_markup=moderation_review_kb(review_id))
            
            await safe_edit_message(query, f"⏳ Показано {min(5, len(pending))} из {len(pending)} отзывов", admin_kb_review_moderation())

        elif cb_data == "mod_view_approved":
            reviews = db.get_approved_reviews(10)
            if not reviews:
                await safe_edit_message(query, "✅ Нет опубликованных отзывов.", admin_kb_review_moderation())
                return
            
            text = "✅ ОПУБЛИКОВАННЫЕ ОТЗЫВЫ:\n\n"
            for i, (user_name, review_text, date) in enumerate(reviews, 1):
                date_obj = datetime.fromisoformat(date).strftime("%d.%m.%Y")
                text += f"{i}. {review_text}\n   👤 {user_name} • {date_obj}\n\n"
            
            total = db.get_reviews_count()
            if total > 10:
                text += f"\n📊 Всего отзывов: {total}"
            
            await safe_edit_message(query, text, admin_kb_review_moderation())

        elif cb_data.startswith("mod_approve:"):
            review_id = int(cb_data.split(":")[1])
            db.approve_review(review_id)
            
            await notify_super_admins(
                context,
                f"⭐ ОДОБРЕН ОТЗЫВ\nКем: {get_user_link(query.from_user)}\nID отзыва: {review_id}"
            )
            
            await safe_edit_message(query, "✅ Отзыв одобрен!", admin_kb_review_moderation())

        elif cb_data.startswith("mod_reject:"):
            review_id = int(cb_data.split(":")[1])
            db.reject_review(review_id)
            
            await notify_super_admins(
                context,
                f"⭐ ОТКЛОНЕН ОТЗЫВ\nКем: {get_user_link(query.from_user)}\nID отзыва: {review_id}"
            )
            
            await safe_edit_message(query, "❌ Отзыв отклонен.", admin_kb_review_moderation())

        elif cb_data == "admin_review_all":
            reviews = db.get_approved_reviews(100)
            if not reviews:
                await safe_edit_message(query, "📝 Нет отзывов.", admin_kb_reviews())
                return
            
            text = "⭐ ВСЕ ОТЗЫВЫ:\n\n"
            for i, (user_name, review_text, date) in enumerate(reviews, 1):
                date_obj = datetime.fromisoformat(date).strftime("%d.%m.%Y %H:%M")
                text += f"{i}. Дата: {date_obj}\n👤 Пользователь: {user_name}\n📝 Текст: {review_text}\n\n"
                if len(text) > 3500:
                    text += "...\n\n(Показаны первые отзывы)"
                    break
            
            await safe_edit_message(query, text[:4000], back_btn("admin_menu_reviews"))

        elif cb_data == "admin_review_clear_all":
            count = db.get_reviews_count() + db.get_pending_reviews_count()
            db.delete_all_reviews()
            
            await notify_super_admins(
                context,
                f"🗑 УДАЛЕНЫ ВСЕ ОТЗЫВЫ\nКем: {get_user_link(query.from_user)}\nКоличество: {count} отзывов"
            )
            
            await query.answer(f"Удалено {count} отзывов", show_alert=True)
            await safe_edit_message(query, f"🗑 Удалено {count} отзывов.", admin_kb_reviews())

        elif cb_data == "admin_review_del_one":
            await query.message.reply_text("❌ Введите ID отзыва для удаления:")
            context.user_data["deleting_review"] = True

        elif cb_data == "admin_broadcast_start":
            if user_id not in SUPER_ADMIN_IDS and not db.check_perm(user_id, PERM_BROADCAST):
                await query.answer("❌ У вас нет прав на рассылку", show_alert=True)
                return
            await query.message.reply_text(
                "📣 НАЧАЛО РАССЫЛКИ\n\nОтправьте сообщение для рассылки (текст, фото, видео, документ).\nКнопки добавляются отдельно после сообщения."
            )
            context.user_data["broadcasting"] = True
            context.user_data["broadcast_buttons"] = []

        elif cb_data == "bc_add_btn_yes":
            await query.message.reply_text(
                "➕ ДОБАВЛЕНИЕ КНОПКИ\n\nОтправьте текст кнопки (только текст):"
            )
            context.user_data["broadcast_step"] = "wait_btn_text"

        elif cb_data == "bc_add_btn_no":
            if not context.user_data.get("broadcast_msg_id") and not context.user_data.get("broadcast_text"):
                await safe_edit_message(query, "❌ Сначала отправьте сообщение для рассылки.")
                return

            await show_broadcast_preview(update, context)

        elif cb_data == "bc_edit_msg":
            await query.message.reply_text("✏️ Отправьте исправленное сообщение:")
            context.user_data["broadcasting"] = True

        elif cb_data == "bc_confirm_send":
            await start_broadcast(update, context)

        elif cb_data == "admin_pm":
            await query.message.reply_text(
                "✉️ ЛИЧНОЕ СООБЩЕНИЕ\n\nВведите: ID_ПОЛЬЗОВАТЕЛЯ СООБЩЕНИЕ\nПример: 123456789 Привет!"
            )
            context.user_data["sending_pm"] = True

        elif cb_data == "admin_toggle_bot":
            current = context.application.bot_data.get("bot_stopped", False)
            context.application.bot_data["bot_stopped"] = not current
            new_status = context.application.bot_data["bot_stopped"]
            
            status = "ОСТАНОВЛЕН" if new_status else "ЗАПУЩЕН"
            
            await notify_super_admins(
                context,
                f"⏸ БОТ {status}\nКем: {get_user_link(query.from_user)}"
            )
            
            await query.answer(f"Бот {status}", show_alert=True)
            bot_stopped = context.application.bot_data.get("bot_stopped", False)
            await safe_edit_message(
                query,
                f"👑 Админ панель\nБот: {'⏸ ОСТАНОВЛЕН' if bot_stopped else '▶️ ЗАПУЩЕН'}", 
                admin_kb_main(user_id, bot_stopped)
            )

    except Exception as e:
        print(f"❌ Ошибка в callback: {e}")
        try:
            await safe_edit_message(query, f"❌ Произошла ошибка: {str(e)[:100]}")
        except:
            pass

# ========== ЗАПУСК ==========
def main():
    print("=" * 50)
    print("🤖 ЗАПУСК БОТА")
    print("=" * 50)
    print(f"📊 Статистика при запуске:")
    print(f"  👥 Пользователей: {db.get_users_count()}")
    print(f"  📦 Аккаунтов TanksBlitz (общая): {db.get_tanks_accounts_count('common')}")
    print(f"  📦 Аккаунтов TanksBlitz (промо): {db.get_tanks_accounts_count('promo')}")
    print(f"  📦 Аккаунтов WoT Blitz: {db.get_blitz_accounts_count()}")
    print(f"  🎟 Промокодов: {db.get_promocodes_count()}")
    print(f"  ⭐ Отзывов: {db.get_reviews_count()} (ожидают: {db.get_pending_reviews_count()})")
    print(f"  ⛔ Забанено: {db.get_banned_count()}")
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Инициализируем состояние бота
    application.bot_data["bot_stopped"] = False
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("panel", panel_command))
    application.add_handler(CommandHandler("info", user_info_command))
    application.add_handler(CommandHandler("promo", message_handler))
    
    # Добавляем обработчик сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    application.add_handler(MessageHandler(filters.Document.ALL, message_handler))
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.AUDIO | filters.VOICE, message_handler))
    
    # Добавляем обработчик callback запросов
    application.add_handler(CallbackQueryHandler(main_callback_handler))
    
    print("✅ Бот запущен и готов к работе!")
    print("📱 Напишите /start в Telegram")
    print("⏸ Нажмите Ctrl+C для остановки")
    print("=" * 50)
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Бот остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()


