import telebot
from telebot import types
import sqlite3
import os
import threading
import time
from datetime import datetime, timedelta
TOKEN = "8452726962:AAHgMeF7DBOd_hEmM2Lq39-nCjQ-7rqpULw"
MAIN_ADMIN_ID = 7176707054  
DB_NAME = 'moviequi.db'
bot = telebot.TeleBot(TOKEN)
def init_db():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        last_name TEXT,
        join_date TEXT,
        is_banned INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_id INTEGER UNIQUE,
        added_by INTEGER,
        added_date TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER UNIQUE,
        channel_username TEXT,
        added_by INTEGER,
        added_date TEXT,
        is_active INTEGER DEFAULT 1,
        is_private INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        title TEXT,
        type TEXT,
        description TEXT,
        file_id TEXT,
        year INTEGER,
        country TEXT,
        genre TEXT,
        added_by INTEGER,
        added_date TEXT,
        views INTEGER DEFAULT 0
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS statistics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        movie_code TEXT,
        watch_date TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS join_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        channel_id INTEGER,
        request_date TEXT,
        UNIQUE(user_id, channel_id)
    )''')
    c.execute('INSERT OR IGNORE INTO admins (admin_id, added_by, added_date) VALUES (?, ?, ?)', 
              (MAIN_ADMIN_ID, MAIN_ADMIN_ID, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    try:
        c.execute("PRAGMA table_info(channels)")
        cols = [r[1] for r in c.fetchall()]
        if 'is_private' not in cols:
            c.execute('ALTER TABLE channels ADD COLUMN is_private INTEGER DEFAULT 0')
            conn.commit()
    except Exception:
        pass
    conn.close()
def get_db():
    return sqlite3.connect(DB_NAME, check_same_thread=False)
if os.path.exists(DB_NAME):
    print(f"📂 Database topildi: {DB_NAME}")
else:
    print("🆕 Yangi database yaratilmoqda...")
init_db()
print("✅ Database tayyor!")
def is_admin(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM admins WHERE admin_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None
def is_banned(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result and result[0] == 1
def set_setting(key, value):
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, str(value)))
    conn.commit()
    conn.close()
def get_setting(key, default=None):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key = ?', (key,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else default
def get_all_admins():
    """Return list of all admin user IDs"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT admin_id FROM admins')
    admins = [row[0] for row in c.fetchall()]
    conn.close()
    return admins
def send_backup_to_admins():
    """Send the latest database backup to all admins"""
    admins = get_all_admins()
    if not admins:
        return
    try:
        conn = get_db()
        conn.execute('PRAGMA wal_checkpoint(RESTART)')
        conn.close()
        with open(DB_NAME, 'rb') as f:
            file_size = os.path.getsize(DB_NAME)
            file_time = datetime.fromtimestamp(os.path.getmtime(DB_NAME)).strftime('%Y-%m-%d %H:%M:%S')
            for admin_id in admins:
                try:
                    bot.send_document(admin_id, f)
                except Exception as e:
                    print(f"Adminni {admin_id} yuborish xatosi: {e}")
    except Exception as e:
        print(f"Backup yuborish xatosi: {e}")
def get_user_display_name(user_id):
    """Return the full name of a user by id (fallback to id string).
    Tries Telegram first, then database if available.
    """
    try:
        user = bot.get_chat(user_id)
        name = user.first_name or ""
        if getattr(user, 'last_name', None):
            name += f" {user.last_name}"
        return name.strip() or str(user_id)
    except Exception:
        try:
            conn = get_db()
            c = conn.cursor()
            c.execute('SELECT first_name, last_name FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            conn.close()
            if row:
                fname, lname = row
                return ((fname or "") + (" " + lname if lname else "")).strip() or str(user_id)
        except Exception:
            pass
    return str(user_id)

def get_user_username_or_name(user_id):
    try:
        user = bot.get_chat(user_id)
        if user.username:
            return f"@{user.username}"
        name = user.first_name or ""
        if getattr(user, 'last_name', None):
            name += f" {user.last_name}"
        return name.strip() or str(user_id)
    except Exception:
        try:
            conn = get_db()
            c = conn.cursor()
            c.execute('SELECT username, first_name, last_name FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            conn.close()
            if row:
                username, fname, lname = row
                if username:
                    return f"@{username}"
                return ((fname or "") + (" " + lname if lname else "")).strip() or str(user_id)
        except Exception:
            pass
    return str(user_id)
def step_handler_with_back(handler_func):
    """Orqaga tugmasini command sifatida qabul qilish uchun wrapper"""
    def wrapper(msg):
        if msg.text == "🔙 Orqaga":
            start(msg)
            return
        return handler_func(msg)
    return wrapper
def get_active_channels():
    """Faol kanallarni olish"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT channel_id, channel_username, is_private FROM channels WHERE is_active = 1 ORDER BY id')
    channels = c.fetchall()
    conn.close()
    return channels
def check_subscription(user_id):
    """Foydalanuvchi barcha faol kanallarga obuna bo'lganini tekshirish"""
    channels = get_active_channels()
    if not channels:
        return True, None
    for idx, channel in enumerate(channels, start=1):
        chan_id, chan_username, is_private = channel
        if is_private:
            conn = get_db()
            c = conn.cursor()
            c.execute('SELECT 1 FROM join_requests WHERE user_id = ? AND channel_id = ?',
                      (user_id, chan_id))
            req = c.fetchone()
            conn.close()
            if not req:
                return False, f"{idx}-kanal"
        else:
            try:
                status = bot.get_chat_member(chan_id, user_id).status
                if status in ['left', 'kicked']:
                    return False, f"{idx}-kanal"
            except Exception as e:
                print(f"Kanal tekshirishda xatolik: {e}")
                pass
    return True, None
def subscription_keyboard():
    """Obuna tugmalari - kanal havolalari va "Tekshirish" tugmasi"""
    channels = get_active_channels()
    markup = types.InlineKeyboardMarkup()
    for idx, channel in enumerate(channels, start=1):
        chan_id, chan_url, is_private = channel
        if chan_url.startswith('@'):
            link = f"https://t.me/{chan_url[1:]}"
        elif chan_url.startswith('http'):
            link = chan_url
        else:
            link = f"https://t.me/{chan_url}"
        channel_name = f"{idx}️⃣ {idx}- kanal"
        markup.add(types.InlineKeyboardButton(channel_name, url=link))
    markup.add(types.InlineKeyboardButton("✅ Tekshirish", callback_data="check_sub"))
    return markup
@bot.callback_query_handler(func=lambda call: call.data.startswith("open_"))
def open_channel_link(call):
    parts = call.data.split("_")
    try:
        idx = int(parts[1]) - 1
    except:
        return
    channels = get_active_channels()
    if idx < 0 or idx >= len(channels):
        return
    link = channels[idx][1]
    if link:
        if link.startswith('@'):
            link = f"https://t.me/{link[1:]}"
        elif link.startswith('http'):
            pass
        else:
            link = f"https://t.me/{link}"
    else:
        link = "(ma'lumot yo'q)"
    try:
        bot.send_message(call.from_user.id, link)
    except Exception:
        pass
@bot.message_handler(func=lambda m: m.text and m.text.endswith("-kanal"))
def show_channel(msg):
    text = msg.text.strip()
    try:
        idx = int(text.split("-")[0]) - 1
    except:
        return
    channels = get_active_channels()
    if idx < 0 or idx >= len(channels):
        bot.send_message(msg.chat.id, "❌ Kanal topilmadi")
        return
    chan_id, chan_url, is_private = channels[idx]
    if is_private:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📤 Zayafka yuborish", url=chan_url if chan_url.startswith('http') else f"https://t.me/{chan_url}"))
        bot.send_message(msg.chat.id, f"{idx+1}-kanal (yopiq):\n{chan_url}", reply_markup=markup)
    else:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔗 Kanalga o'tish", url=chan_url if chan_url.startswith('http') else f"https://t.me/{chan_url}"))
        bot.send_message(msg.chat.id, f"{idx+1}-kanal (ochiq):\n{chan_url}", reply_markup=markup)
def main_keyboard(user_id):
    """Asosiy menyu"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if is_admin(user_id):
        markup.row("👑 Admin Panel")
    return markup
def admin_keyboard():
    """Admin panel tugmalari"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("➕ Kino qo'shish")
    markup.row("✏️ Tahrirlash", "🗑 O'chirish")
    markup.row("👤 Adminlar", "📢 Kanallar")
    markup.row("🚫 Ban/Unban", "📊 Statistika")
    markup.row("💾 Zaxira")
    markup.row("📣 Reklama", "🔙 Orqaga")
    return markup
def check_sub_decorator(func):
    """Obuna tekshirish dekoratori"""
    def wrapper(msg):
        user_id = msg.from_user.id if hasattr(msg, 'from_user') else msg.message.chat.id
        try:
            if user_id == bot.get_me().id:
                return func(msg)
        except Exception:
            pass
        if is_admin(user_id):
            return func(msg)
        if is_banned(user_id):
            bot.send_message(user_id, "🚫 Siz bloklangansiz!")
            return
        subscribed, channel = check_subscription(user_id)
        if not subscribed:
            msg_text = (
                f"🚀 Botdan to'liq foydalanish uchun quyidagi kanallarga obuna bo'ling:"
            )
            bot.send_message(
                user_id,
                msg_text,
                reply_markup=subscription_keyboard()
            )
            return
        return func(msg)
    return wrapper
@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_sub_callback(call):
    user_id = call.from_user.id
    try:
        if user_id == bot.get_me().id:
            return
    except Exception:
        pass
    subscribed, channel = check_subscription(user_id)
    if subscribed:
        bot.answer_callback_query(call.id, "✅ Obuna tasdiqlandi!")
        bot.delete_message(call.message.chat.id, call.message.message_id)
        try:
            if user_id != bot.get_me().id:
                # Вместо start, просим код
                bot.send_message(user_id, "👋 Salom!\n\n🎬 Moviequi Bot ga xush kelibsiz!\n\n🔢 Iltimos, film kodini kiriting:")
                bot.register_next_step_handler(call.message, get_movie_from_start)
        except Exception:
            pass
    else:
        bot.answer_callback_query(call.id, f"❌ Siz barcha kanallarga obuna bo'lmadingiz. Iltimos, obuna bo'lib qayta tekshiring.", show_alert=True)
@bot.chat_join_request_handler(func=lambda q: True)
def handle_join_request(q):
    """Foydalanuvchi kanalga join request yuborganida yozib qo'yish"""
    user_id = q.from_user.id
    channel_id = q.chat.id
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id FROM channels WHERE channel_id = ? AND is_active = 1', (channel_id,))
    if c.fetchone():
        try:
            c.execute('INSERT OR IGNORE INTO join_requests (user_id, channel_id, request_date) VALUES (?, ?, ?)',
                      (user_id, channel_id, datetime.now().strftime("%Y-%m-%d %H:%M")))
            conn.commit()
        except Exception:
            pass
    conn.close()
    try:
        bot.send_message(user_id, "✅ Join request qabul qilindi! Botdan foydalanish uchun kuting yoki kanal adminlarini xabardor qiling.")
    except Exception:
        pass
@bot.message_handler(func=lambda m: m.text == "🔙 Orqaga_DISABLED")
@check_sub_decorator
def handle_back_button(msg):
    start(msg)
@bot.message_handler(commands=['start'])
@check_sub_decorator
def start(msg):
    user_id = msg.from_user.id
    username = msg.from_user.username or "Username yo'q"
    first_name = msg.from_user.first_name or ""
    last_name = msg.from_user.last_name or ""
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, ?, 0)''',
              (user_id, username, first_name, last_name, 
               datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()
    welcome = (
        f"👋 Salom, {first_name}!\n\n"
        f"🎬 Moviequi Bot ga xush kelibsiz!\n\n"
        f"📽 Minglab kinolar sizni kutmoqda!\n\n"
        f"🔢 Iltimos, film kodini kiriting:"
    )
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if is_admin(user_id):
        markup.row("👑 Admin Panel")
    bot.send_message(msg.chat.id, welcome, reply_markup=markup)
    bot.register_next_step_handler(msg, get_movie_from_start)
@bot.message_handler(func=lambda m: m.text == "👑 Admin Panel")
@check_sub_decorator
def admin_panel(msg):
    if not is_admin(msg.from_user.id):
        bot.send_message(msg.chat.id, "🚫 Sizda ruxsat yo'q!")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    users_count = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM movies')
    movies_count = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM admins')
    admins_count = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM channels WHERE is_active = 1')
    channels_count = c.fetchone()[0]
    conn.close()
    panel_text = (
        f"👑 *ADMIN PANEL*\n\n"
        f"📊 Statistika:\n"
        f"👥 Foydalanuvchilar: {users_count}\n"
        f"🎬 Kinolar: {movies_count}\n"
        f" Adminlar: {admins_count}\n"
        f"📢 Kanallar: {channels_count}\n\n"
        f"Kerakli bo'limni tanlang:"
    )
    bot.send_message(msg.chat.id, panel_text, parse_mode="Markdown", 
                     reply_markup=admin_keyboard())
@bot.message_handler(func=lambda m: m.text == "👤 Adminlar")
@check_sub_decorator
def admins_menu(msg):
    if not is_admin(msg.from_user.id):
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("➕ Admin qo'shish", "🗑 Admin o'chirish")
    markup.row("📋 Adminlar ro'yxati", "🔙 Orqaga")
    bot.send_message(msg.chat.id, "👤 Adminlar bo'limi:", reply_markup=markup)
@bot.message_handler(func=lambda m: m.text == "➕ Admin qo'shish")
@check_sub_decorator
def add_admin_start(msg):
    if msg.from_user.id != MAIN_ADMIN_ID:
        bot.send_message(msg.chat.id, "🚫 Faqat asosiy admin adminlar qo'sha oladi!")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, "🆔 Yangi admin ID yoki @username kiriting:", reply_markup=markup)
    bot.register_next_step_handler(msg, add_admin_id)
def add_admin_id(msg):
    if msg.text == "🔙 Orqaga":
        admins_menu(msg)
        return
    text = msg.text.strip()
    if text.startswith('@'):
        try:
            chat = bot.get_chat(text)
            new_admin_id = chat.id
        except Exception:
            bot.send_message(msg.chat.id, "❌ Username topilmadi!")
            return
    else:
        try:
            new_admin_id = int(text)
        except:
            bot.send_message(msg.chat.id, "❌ ID raqam yoki @username kiriting!")
            return
    if new_admin_id == MAIN_ADMIN_ID:
        bot.send_message(msg.chat.id, "⚠️ Bu asosiy admin!")
        return
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO admins (admin_id, added_by, added_date) VALUES (?, ?, ?)',
                  (new_admin_id, msg.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        name = get_user_display_name(new_admin_id)
        bot.send_message(msg.chat.id, f"✅ Admin qo'shildi: {name} ({new_admin_id})")
    except Exception:
        bot.send_message(msg.chat.id, "⚠️ Bu user allaqachon admin!")
    conn.close()
@bot.message_handler(func=lambda m: m.text == "🗑 Admin o'chirish")
@check_sub_decorator
def remove_admin_start(msg):
    if msg.from_user.id != MAIN_ADMIN_ID:
        bot.send_message(msg.chat.id, "🚫 Faqat asosiy admin!")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT admin_id FROM admins WHERE admin_id != ?', (MAIN_ADMIN_ID,))
    admins = c.fetchall()
    conn.close()
    if not admins:
        bot.send_message(msg.chat.id, "❌ O'chiriladigan adminlar yo'q!")
        return
    text = "📋 Adminlar:\n\n"
    for admin in admins:
        admin_id = admin[0]
        name = get_user_username_or_name(admin_id)
        text += f"• {name} ({admin_id})\n"
    text += "\n🆔 O'chirish uchun ID yoki @username kiriting:"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, text, parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(msg, remove_admin_id)
def remove_admin_id(msg):
    if msg.text == "🔙 Orqaga":
        admins_menu(msg)
        return
    text = msg.text.strip()
    if text.startswith('@'):
        try:
            admin_id = bot.get_chat(text).id
        except Exception:
            bot.send_message(msg.chat.id, "❌ Username topilmadi!")
            return
    else:
        try:
            admin_id = int(text)
        except:
            bot.send_message(msg.chat.id, "❌ ID raqam yoki @username kiriting!")
            return
    if admin_id == MAIN_ADMIN_ID:
        bot.send_message(msg.chat.id, "🚫 Asosiy adminni o'chirib bo'lmaydi!")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM admins WHERE admin_id = ?', (admin_id,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    if deleted > 0:
        name = get_user_display_name(admin_id)
        bot.send_message(msg.chat.id, f"✅ Admin o'chirildi: {name} ({admin_id})")
    else:
        bot.send_message(msg.chat.id, "❌ Admin topilmadi!")
@bot.message_handler(func=lambda m: m.text == "📋 Adminlar ro'yxati")
@check_sub_decorator
def list_admins(msg):
    if not is_admin(msg.from_user.id):
        return
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT admin_id, added_date FROM admins ORDER BY added_date')
    admins = c.fetchall()
    conn.close()
    text = "👮 *ADMINLAR RO'YXATI*\n\n"
    for i, admin in enumerate(admins, 1):
        admin_id, added = admin
        emoji = "👑" if admin_id == MAIN_ADMIN_ID else "👤"
        name = get_user_username_or_name(admin_id)
        text += f"{i}. {emoji} {name}\n   └ {added}\n"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")
@bot.message_handler(func=lambda m: m.text == "💾 Zaxira")
@check_sub_decorator
def backup_db(msg):
    if not is_admin(msg.from_user.id):
        return
    try:
        conn = get_db()
        conn.execute('PRAGMA wal_checkpoint(RESTART)')
        conn.close()
        with open(DB_NAME, 'rb') as f:
            bot.send_document(msg.chat.id, f)
        set_setting('last_manual_backup', datetime.now().isoformat())
        bot.send_message(msg.chat.id, "✅ Database zaxira yuborildi!")
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ Faylni jo'natishda xatolik: {e}")
@bot.message_handler(func=lambda m: m.text == "📢 Kanallar")
@check_sub_decorator
def channels_menu(msg):
    if not is_admin(msg.from_user.id):
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("➕ Kanal qo'shish", "🗑 Kanal o'chirish")
    markup.row("🔄 Kanal o'chirish/yoqish", "📋 Kanallar ro'yxati")
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, "📢 Kanallar bo'limi:", reply_markup=markup)
@bot.message_handler(func=lambda m: m.text == "➕ Kanal qo'shish")
@check_sub_decorator
def add_channel_start(msg):
    if not is_admin(msg.from_user.id):
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, "🔒 Kanal privatmi? (ha/yo'q)", reply_markup=markup)
    bot.register_next_step_handler(msg, ask_channel_privacy)
def ask_channel_privacy(msg):
    if msg.text == "🔙 Orqaga":
        channels_menu(msg)
        return
    ans = msg.text.strip().lower()
    is_private = 1 if ans.startswith('h') else 0
    if is_private:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("🔙 Orqaga")
        bot.send_message(msg.chat.id, "🔗 Iltimos, kanalga tashrif uchun invite linkni yuboring:", reply_markup=markup)
        bot.register_next_step_handler(msg, lambda m: add_channel_link(m, is_private))
    else:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("🔙 Orqaga")
        bot.send_message(msg.chat.id,
            "📢 Kanal username kiriting (masalan: @kanal)\n\n💡 Botni avval kanalga admin qiling!",
            reply_markup=markup)
        bot.register_next_step_handler(msg, lambda m: add_channel_username(m, is_private))
def add_channel_username(msg, is_private):
    if msg.text == "🔙 Orqaga":
        channels_menu(msg)
        return
    username = msg.text.strip()
    if not username.startswith('@'):
        username = '@' + username
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, "🆔 Kanal ID sini kiriting (masalan: -1001234567890):", reply_markup=markup)
    bot.register_next_step_handler(msg, lambda m: add_channel_id(m, username, is_private))
def add_channel_link(msg, is_private):
    """Private kanal uchun invite linkni qabul qiladi va keyin ID so'raydi"""
    if msg.text == "🔙 Orqaga":
        channels_menu(msg)
        return
    link = msg.text.strip()
    if not ("t.me" in link):
        bot.send_message(msg.chat.id, "❌ Iltimos, to'g'ri telegram link yuboring!")
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, "🆔 Kanal ID sini kiriting (masalan: -1001234567890):", reply_markup=markup)
    bot.register_next_step_handler(msg, lambda m: add_channel_id(m, link, is_private))
def add_channel_id(msg, username, is_private):
    if msg.text == "🔙 Orqaga":
        channels_menu(msg)
        return
    try:
        channel_id = int(msg.text.strip())
    except:
        bot.send_message(msg.chat.id, "❌ ID raqam kiriting!")
        return
    try:
        chat = bot.get_chat(channel_id)
        bot.send_message(msg.chat.id, f"✅ Kanal topildi: {chat.title}")
    except:
        bot.send_message(msg.chat.id, "⚠️ Kanal topilmadi yoki bot admin emas!")
        return
    if is_private:
        if "t.me" in username or username.startswith('http'):
            conn = get_db()
            c = conn.cursor()
            try:
                c.execute('INSERT INTO channels (channel_id, channel_username, added_by, added_date, is_private) VALUES (?, ?, ?, ?, ?)',
                          (channel_id, username, msg.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M"), is_private))
                conn.commit()
                bot.send_message(msg.chat.id, f"✅ Maxfiy kanal qo'shildi: {username}")
            except Exception:
                bot.send_message(msg.chat.id, "⚠️ Bu kanal allaqachon mavjud!")
            conn.close()
            return
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row("🔙 Orqaga")
        bot.send_message(msg.chat.id, "🔗 Iltimos, kanalga tashrif uchun invite linkni yuboring:", reply_markup=markup)
        bot.register_next_step_handler(msg, lambda m: add_channel_store(m, username, channel_id, is_private))
        return
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO channels (channel_id, channel_username, added_by, added_date, is_private) VALUES (?, ?, ?, ?, ?)',
                  (channel_id, username, msg.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M"), is_private))
        conn.commit()
        bot.send_message(msg.chat.id, f"✅ Kanal qo'shildi: {username} (ommaviy)")
    except Exception:
        bot.send_message(msg.chat.id, "⚠️ Bu kanal allaqachon mavjud!")
    conn.close()
def add_channel_store(msg, username, channel_id, is_private):
    """Maxfiy kanal uchun linkni qabul qilib saqlash"""
    if msg.text == "🔙 Orqaga":
        channels_menu(msg)
        return
    link = msg.text.strip()
    if not ("t.me" in link):
        bot.send_message(msg.chat.id, "❌ Iltimos, to'g'ri telegram link yuboring!")
        return
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('INSERT INTO channels (channel_id, channel_username, added_by, added_date, is_private) VALUES (?, ?, ?, ?, ?)',
                  (channel_id, link, msg.from_user.id, datetime.now().strftime("%Y-%m-%d %H:%M"), is_private))
        conn.commit()
        bot.send_message(msg.chat.id, f"✅ Maxfiy kanal qo'shildi: {link}")
    except Exception:
        bot.send_message(msg.chat.id, "⚠️ Bu kanal allaqachon mavjud!")
    conn.close()
@bot.message_handler(func=lambda m: m.text == "🗑 Kanal o'chirish")
@check_sub_decorator
def remove_channel_start(msg):
    if not is_admin(msg.from_user.id):
        return
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, channel_username, channel_id FROM channels')
    channels = c.fetchall()
    conn.close()
    if not channels:
        bot.send_message(msg.chat.id, "❌ Kanallar yo'q!")
        return
    text = "📋 Kanallar:\n\n"
    for ch in channels:
        text += f"{ch[0]}. Kanal (ID: `{ch[2]}`)\n"
    text += "\n🔢 O'chirish uchun kanal raqamini (1, 2, 3...) kiriting:"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, text, parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(msg, remove_channel_id)
def remove_channel_id(msg):
    if msg.text == "🔙 Orqaga":
        channels_menu(msg)
        return
    try:
        row_id = int(msg.text.strip())
    except:
        bot.send_message(msg.chat.id, "❌ Raqam kiriting!")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM channels WHERE id = ?', (row_id,))
    deleted = c.rowcount
    conn.commit()
    conn.close()
    if deleted > 0:
        bot.send_message(msg.chat.id, f"✅ Kanal o'chirildi!")
    else:
        bot.send_message(msg.chat.id, "❌ Kanal topilmadi!")
@bot.message_handler(func=lambda m: m.text == "🔄 Kanal o'chirish/yoqish")
@check_sub_decorator
def toggle_channel_start(msg):
    if not is_admin(msg.from_user.id):
        return
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, channel_username, is_active FROM channels')
    channels = c.fetchall()
    conn.close()
    if not channels:
        bot.send_message(msg.chat.id, "❌ Kanallar yo'q!")
        return
    text = "📋 Kanallar:\n\n"
    for ch in channels:
        status = "✅ Faol" if ch[2] == 1 else "❌ O'chiq"
        text += f"{ch[0]}. Kanal - {status}\n"
    text += "\n🔢 O'zgartirish uchun kanal raqamini kiriting:"
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, text, reply_markup=markup)
    bot.register_next_step_handler(msg, toggle_channel_id)
def toggle_channel_id(msg):
    if msg.text == "🔙 Orqaga":
        channels_menu(msg)
        return
    try:
        row_id = int(msg.text.strip())
    except:
        bot.send_message(msg.chat.id, "❌ Raqam kiriting!")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT is_active FROM channels WHERE id = ?', (row_id,))
    result = c.fetchone()
    if not result:
        conn.close()
        bot.send_message(msg.chat.id, "❌ Kanal topilmadi!")
        return
    new_status = 0 if result[0] == 1 else 1
    c.execute('UPDATE channels SET is_active = ? WHERE id = ?', (new_status, row_id))
    conn.commit()
    conn.close()
    status_text = "yoqildi" if new_status == 1 else "o'chirildi"
    bot.send_message(msg.chat.id, f"✅ Kanal {status_text}!")
@bot.message_handler(func=lambda m: m.text == "📋 Kanallar ro'yxati")
@check_sub_decorator
def list_channels(msg):
    if not is_admin(msg.from_user.id):
        return
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT channel_username, channel_id, is_active, added_date FROM channels ORDER BY added_date')
    channels = c.fetchall()
    conn.close()
    if not channels:
        bot.send_message(msg.chat.id, "❌ Kanallar yo'q!")
        return
    text = "📢 *KANALLAR RO'YXATI*\n\n"
    for i, ch in enumerate(channels, 1):
        status = "✅" if ch[2] == 1 else "❌"
        text += f"{i}. {status} Kanal\n   ID: `{ch[1]}`\n   └ {ch[3]}\n\n"
    bot.send_message(msg.chat.id, text, parse_mode="Markdown")
@bot.message_handler(func=lambda m: m.text == "➕ Kino qo'shish")
@check_sub_decorator
def add_movie_start(msg):
    if not is_admin(msg.from_user.id):
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, "🆔 Film kodini kiriting (masalan: K001):", reply_markup=markup)
    bot.register_next_step_handler(msg, add_movie_code)
def add_movie_code(msg):
    if msg.text == "🔙 Orqaga":
        admin_panel(msg)
        return
    code = msg.text.strip().upper()
    if len(code) < 1:
        bot.send_message(msg.chat.id, "❌ Kod juda qisqa. Qaytadan:")
        bot.register_next_step_handler(msg, add_movie_code)
        return
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM movies WHERE code = ?', (code,))
    if c.fetchone():
        conn.close()
        bot.send_message(msg.chat.id, f"⚠️ {code} kodi allaqachon mavjud!")
        return
    conn.close()
    bot.send_message(msg.chat.id, f"✅ Kod: `{code}`\n\n📝 Film nomini kiriting:", parse_mode="Markdown")
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, "Davom etish uchun nomni kiriting:", reply_markup=markup)
    bot.register_next_step_handler(msg, lambda m: add_movie_title(m, code))
def add_movie_title(msg, code):
    if msg.text == "🔙 Orqaga":
        admin_panel(msg)
        return
    title = msg.text.strip()
    template = (
        f"📋 *TEMPLATE - QUYIDAGINI COPY QILIB TO'LDIRING VA YUBORING:*\n\n"
        f"🎬 Yil: 2024\n"
        f"🎭 Janr: Drama\n"
        f"🌍 Mamlakat: O'zbekiston\n"
        f"📝 Tavsif: Film haqida qisqa tavsif yoziladi\n\n"
        f"⚠️ Yoki `/skip` deb yozib davom etishingiz mumkin"
    )
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("/skip", "🔙 Orqaga")
    bot.send_message(msg.chat.id, template, parse_mode="Markdown", reply_markup=markup)
    bot.register_next_step_handler(msg, lambda m: add_movie_description(m, code, title))
def add_movie_description(msg, code, title):
    if msg.text == "🔙 Orqaga":
        admin_panel(msg)
        return
    year = None
    genre = None
    country = None
    description = None
    if msg.text != "/skip":
        lines = msg.text.strip().split('\n')
        for line in lines:
            if ':' in line:
                key, val = line.split(':', 1)
                key = key.lower()
                val = val.strip()
                if 'yil' in key:
                    try: year = int(val)
                    except: year = 2024
                elif 'janr' in key: genre = val
                elif 'mamlakat' in key: country = val
                elif 'tavsif' in key: description = val
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, f"📹 Endi video faylni yuboring:", reply_markup=markup)   
    bot.register_next_step_handler(msg, lambda m: save_movie(m, code, title, description, year, genre, country))
def save_movie(msg, code, title, description, year=2024, genre="Noma'lum", country="Noma'lum"):
    if msg.text == "🔙 Orqaga":
        admin_panel(msg)
        return
    if not msg.video:
        bot.send_message(msg.chat.id, "❌ Video yuborilmadi! Qaytadan:")
        bot.register_next_step_handler(msg, lambda m: save_movie(m, code, title, description, year, genre, country))
        return
    file_id = msg.video.file_id
    user_id = msg.from_user.id
    bot.send_message(msg.chat.id, "⏳ Bazaga saqlanmoqda...")
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute('''INSERT INTO movies (code, title, type, description, file_id, year, country, genre, added_by, added_date) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (code, title, "movie", description, file_id, year, country, genre, user_id,
                   datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        success = (
            f"✅ *KINO MUVAFFAQIYATLI QO'SHILDI!*\n\n"
            f"🆔 Kod: `{code}`\n"
            f"🎬 Nomi: {title}\n"
            f"📝 Tavsif: {description}\n"
            f"📅 Yil: {year}\n"
            f"🌍 Mamlakat: {country}\n"
            f"🎭 Janr: {genre}\n"
            f"📦 File ID: `{file_id[:30]}...`\n"
            f"📅 Sana: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"👥 Foydalanuvchilar endi `{code}` kodi bilan bu filmni olishlari mumkin!"
        )
        bot.send_message(msg.chat.id, success, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ Bazaga saqlashda xatolik: {e}")
    conn.close()

def get_movie_from_start(msg):
    """Foydalanuvchi start keyin kodni kiritadi"""
    if msg.text == '/start':
        start(msg)
        return
    
    if msg.text.startswith('/'):
        return
    
    if msg.text == "👑 Admin Panel":
        admin_panel(msg)
        return
    
    if msg.text == "🔍 Qidiruv":
        search_menu(msg)
        return
    
    if msg.text == "ℹ️ Ma'lumot":
        info_menu(msg)
        return
    
    if msg.text == "🔙 Orqaga":
        start(msg)
        return
    
    code = msg.text.strip().upper()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM movies WHERE code = ?', (code,))
    movie = c.fetchone()
    if not movie:
        conn.close()
        bot.send_message(msg.chat.id, f"❌ `{code}` kodli film topilmadi!\n\n🔢 Qayta kod kiriting:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, get_movie_from_start)
        return
    
    user_id = msg.from_user.id
    c.execute('INSERT INTO statistics VALUES (NULL, ?, ?, ?)',
              (user_id, code, datetime.now().strftime("%Y-%m-%d %H:%M")))
    c.execute('UPDATE movies SET views = views + 1 WHERE code = ?', (code,))
    conn.commit()
    conn.close()
    
    caption = f"🎬 *{movie[2]}*\n"
    if movie[4] and movie[4].strip() not in ["None", "Tavsif yo'q", ""]:
        caption += f"\n📝 {movie[4]}\n"
    if movie[6] and str(movie[6]) != "0":
        caption += f"\n📅 Yil: {movie[6]}"
    if movie[7] and movie[7] not in ["Noma'lum", ""]:
        caption += f"\n🌍 Mamlakat: {movie[7]}"
    if movie[8] and movie[8] not in ["Noma'lum", ""]:
        caption += f"\n🎭 Janr: {movie[8]}"
    caption += f"\n🆔 Kod: `{movie[1]}`"
    
    try:
        bot.send_video(msg.chat.id, movie[5], caption=caption, parse_mode="Markdown")
        bot.send_message(msg.chat.id, "🔢 Boshqa kod kiriting:")
        bot.register_next_step_handler(msg, get_movie_from_start)
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ Xatolik: {e}")
        bot.register_next_step_handler(msg, get_movie_from_start)

@bot.message_handler(func=lambda m: m.text == "🎬 Kino_DISABLED")
@check_sub_decorator
def movies_menu(msg):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, "🔢 Film kodini kiriting:", reply_markup=markup)
    bot.register_next_step_handler(msg, get_movie_OLD)

def get_movie_OLD(msg):
    if msg.text == "🔙 Orqaga":
        start(msg)
        return
    code = msg.text.strip().upper()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM movies WHERE code = ?', (code,))
    movie = c.fetchone()
    if not movie:
        conn.close()
        bot.send_message(msg.chat.id, f"❌ `{code}` kodli film topilmadi!", parse_mode="Markdown")
        return
    user_id = msg.from_user.id
    c.execute('INSERT INTO statistics VALUES (NULL, ?, ?, ?)',
              (user_id, code, datetime.now().strftime("%Y-%m-%d %H:%M")))
    c.execute('UPDATE movies SET views = views + 1 WHERE code = ?', (code,))
    conn.commit()
    conn.close()
    caption = f"🎬 *{movie[2]}*\n"
    if movie[4] and movie[4].strip() not in ["None", "Tavsif yo'q", ""]:
        caption += f"\n📝 {movie[4]}\n"
    if movie[6] and str(movie[6]) != "0":
        caption += f"\n📅 Yil: {movie[6]}"
    if movie[7] and movie[7] not in ["Noma'lum", ""]:
        caption += f"\n🌍 Mamlakat: {movie[7]}"
    if movie[8] and movie[8] not in ["Noma'lum", ""]:
        caption += f"\n🎭 Janr: {movie[8]}"
    caption += f"\n\n👁 Ko'rishlar: {movie[11] + 1}"
    caption += f"\n🆔 Kod: `{movie[1]}`"
    try:
        bot.send_video(msg.chat.id, movie[5], caption=caption, parse_mode="Markdown")
    except Exception as e:
        bot.send_message(msg.chat.id, f"❌ Xatolik: {e}")
@bot.message_handler(func=lambda m: m.text == "🔍 Qidiruv")
@check_sub_decorator
def search_menu(msg):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, "🔍 Film nomini kiriting:", reply_markup=markup)
    bot.register_next_step_handler(msg, search_content)
def search_content(msg):
    if msg.text == "🔙 Orqaga":
        start(msg)
        return
    query = msg.text.strip().lower()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT code, title FROM movies WHERE LOWER(title) LIKE ?', (f'%{query}%',))
    movies = c.fetchall()
    conn.close()
    if not movies:
        bot.send_message(msg.chat.id, "❌ Hech narsa topilmadi!")
        return
    result = "🔍 *Qidiruv natijalari:*\n\n"
    if movies:
        result += "🎬 *Kinolar:*\n"
        for m in movies:
            result += f"• `{m[0]}` - {m[1]}\n"
    bot.send_message(msg.chat.id, result, parse_mode="Markdown")
@bot.message_handler(func=lambda m: m.text == "🚫 Ban/Unban")
@check_sub_decorator
def ban_menu(msg):
    if not is_admin(msg.from_user.id):
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, "🆔 Foydalanuvchi ID raqamini kiriting:", reply_markup=markup)
    bot.register_next_step_handler(msg, ban_user)
def ban_user(msg):
    if msg.text == "🔙 Orqaga":
        admin_panel(msg)
        return
    try:
        user_id = int(msg.text.strip())
    except:
        bot.send_message(msg.chat.id, "❌ ID raqam kiriting!")
        return
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT is_banned FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    if not result:
        conn.close()
        bot.send_message(msg.chat.id, "❌ Foydalanuvchi topilmadi!")
        return
    new_status = 0 if result[0] == 1 else 1
    c.execute('UPDATE users SET is_banned = ? WHERE user_id = ?', (new_status, user_id))
    conn.commit()
    conn.close()
    status_text = "bloklandi" if new_status == 1 else "blokdan chiqarildi"
    bot.send_message(msg.chat.id, f"✅ Foydalanuvchi {status_text}!")
@bot.message_handler(func=lambda m: m.text == "📊 Statistika")
@check_sub_decorator
def show_statistics(msg):
    if not is_admin(msg.from_user.id):
        return
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    total_users = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM users WHERE is_banned = 1')
    banned_users = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM movies')
    total_movies = c.fetchone()[0]
    c.execute('SELECT SUM(views) FROM movies')
    total_views = c.fetchone()[0] or 0
    c.execute('SELECT COUNT(*) FROM admins')
    total_admins = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM channels WHERE is_active = 1')
    active_channels = c.fetchone()[0]
    c.execute('SELECT code, title, views FROM movies ORDER BY views DESC LIMIT 5')
    top_movies = c.fetchall()
    conn.close()
    stats = (
        f"📊 *BOT STATISTIKASI*\n\n"
        f"👥 Foydalanuvchilar:\n"
        f"  • Jami: {total_users}\n"
        f"  • Bloklangan: {banned_users}\n"
        f"  • Faol: {total_users - banned_users}\n\n"
        f"🎬 Kontent:\n"
        f"  • Kinolar: {total_movies}\n\n"
        f"👁 Ko'rishlar: {total_views}\n"
        f"👮 Adminlar: {total_admins}\n"
        f"📢 Faol kanallar: {active_channels}\n\n"
        f"🏆 *TOP 5 Filmlar:*\n"
    )
    if top_movies:
        for i, movie in enumerate(top_movies, 1):
            stats += f"{i}. {movie[1]} - {movie[2]} ko'rish\n"
    else:
        stats += "_Hali ma'lumot yo'q_\n"
    bot.send_message(msg.chat.id, stats, parse_mode="Markdown")
@bot.message_handler(func=lambda m: m.text == "📣 Reklama")
@check_sub_decorator
def broadcast_menu(msg):
    if not is_admin(msg.from_user.id):
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, 
        "✍️ Barcha foydalanuvchilarga yuboriladigan xabarni yozing:\n\n"
        "💡 Rasm yoki video ham yuborishingiz mumkin.", reply_markup=markup)
    bot.register_next_step_handler(msg, broadcast_message)
def broadcast_message(msg):
    if msg.text == "🔙 Orqaga":
        admin_panel(msg)
        return
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT user_id FROM users WHERE is_banned = 0')
    users = c.fetchall()
    conn.close()
    total = len(users)
    success = 0
    failed = 0
    bot.send_message(msg.chat.id, f"📤 {total} ta foydalanuvchiga yuborilmoqda...")
    for user in users:
        try:
            bot.copy_message(
                chat_id=user[0],
                from_chat_id=msg.chat.id,
                message_id=msg.message_id
            )
            success += 1
        except Exception:
            failed += 1
    result = (
        f"✅ *Xabar yuborildi!*\n\n"
        f"📊 Natija:\n"
        f"✔️ Muvaffaqiyatli: {success}\n"
        f"❌ Xatolik: {failed}\n"
        f"📈 Jami: {total}"
    )
    bot.send_message(msg.chat.id, result, parse_mode="Markdown")
@bot.message_handler(func=lambda m: m.text == "✏️ Tahrirlash")
@check_sub_decorator
def edit_menu(msg):
    if not is_admin(msg.from_user.id):
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("✏️ Kino tahrirlash")
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, "Tanlang:", reply_markup=markup)
@bot.message_handler(func=lambda m: m.text == "✏️ Kino tahrirlash")
@check_sub_decorator
def edit_movie_start(msg):
    if not is_admin(msg.from_user.id):
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, "🔢 Film kodini kiriting:", reply_markup=markup)
    bot.register_next_step_handler(msg, edit_movie_show)
def edit_movie_show(msg):
    if msg.text == "🔙 Orqaga":
        admin_panel(msg)
        return
    code = msg.text.strip().upper()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM movies WHERE code = ?', (code,))
    movie = c.fetchone()
    conn.close()
    if not movie:
        bot.send_message(msg.chat.id, f"❌ {code} kodli film topilmadi!")
        return
    movie_info = (
        f"🎬 *Joriy ma'lumotlar:*\n\n"
        f"🆔 Kod: `{movie[1]}`\n"
        f"📝 Nomi: {movie[2]}\n"
        f"📄 Tavsif: {movie[4]}\n\n"
        f"Nimani o'zgartirmoqchisiz?"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("📝 Nomi", callback_data=f"edit_title_{code}"))
    markup.add(types.InlineKeyboardButton("📄 Tavsif", callback_data=f"edit_desc_{code}"))
    bot.send_message(msg.chat.id, movie_info, parse_mode="Markdown", reply_markup=markup)
@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_"))
def edit_movie_field(call):
    parts = call.data.split("_")
    field = parts[1]
    code = parts[2]
    field_names = {"title": "Nomi", "desc": "Tavsif"}
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(call.message.chat.id, f"✍️ Yangi {field_names[field]} kiriting:", reply_markup=markup)
    bot.register_next_step_handler(call.message, lambda m: update_movie_field(m, code, field))
    bot.answer_callback_query(call.id)
def update_movie_field(msg, code, field):
    if msg.text == "🔙 Orqaga":
        admin_panel(msg)
        return
    new_value = msg.text.strip()
    conn = get_db()
    c = conn.cursor()
    field_map = {"title": "title", "desc": "description"}
    db_field = field_map[field]
    c.execute(f'UPDATE movies SET {db_field} = ? WHERE code = ?', (new_value, code))
    conn.commit()
    conn.close()
    bot.send_message(msg.chat.id, f"✅ `{code}` kodi yangilandi!", parse_mode="Markdown")
@bot.message_handler(func=lambda m: m.text == "🗑 O'chirish")
@check_sub_decorator
def delete_menu(msg):
    if not is_admin(msg.from_user.id):
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🗑 Kino o'chirish")
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, "Tanlang:", reply_markup=markup)
@bot.message_handler(func=lambda m: m.text == "🗑 Kino o'chirish")
@check_sub_decorator
def delete_movie_start(msg):
    if not is_admin(msg.from_user.id):
        return
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("🔙 Orqaga")
    bot.send_message(msg.chat.id, "🔢 O'chiriladigan film kodini kiriting:", reply_markup=markup)
    bot.register_next_step_handler(msg, delete_movie)
def delete_movie(msg):
    if msg.text == "🔙 Orqaga":
        admin_panel(msg)
        return
    code = msg.text.strip().upper()
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT title FROM movies WHERE code = ?', (code,))
    movie = c.fetchone()
    if not movie:
        conn.close()
        bot.send_message(msg.chat.id, f"❌ {code} kodli film topilmadi!")
        return
    c.execute('DELETE FROM movies WHERE code = ?', (code,))
    c.execute('DELETE FROM statistics WHERE movie_code = ?', (code,))
    conn.commit()
    conn.close()
    bot.send_message(msg.chat.id, f"✅ '{movie[0]}' (`{code}`) o'chirildi!", parse_mode="Markdown")
@bot.message_handler(func=lambda m: m.text == "ℹ️ Ma'lumot")
@check_sub_decorator
def info_menu(msg):
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM movies')
    movies_count = c.fetchone()[0]
    conn.close()
    info = (
        f"ℹ️ *Moviequi Bot haqida*\n\n"
        f"🎬 Minglab kinoni bepul ko'ring!\n\n"
        f"📊 *Bizda:*\n"
        f"• {movies_count} ta kino\n\n"
        f"💡 *Foydalanish:*\n"
        f"1️⃣ Film kodini kiriting\n"
        f"2️⃣ Yoki qidiruv qiling\n"
        f"3️⃣ Tomosha qiling!\n\n"
        f"👨‍💻 Murojaat: @OlloberdiNabiyev"
    )
    bot.send_message(msg.chat.id, info, parse_mode="Markdown")
@bot.message_handler(func=lambda m: m.text == "🔙 Orqaga")
@check_sub_decorator
def back_handler(msg):
    if is_admin(msg.from_user.id):
        admin_panel(msg)
    else:
        # Вернуться к вводу кода
        bot.send_message(msg.chat.id, "🔢 Film kodini kiriting:")
        bot.register_next_step_handler(msg, get_movie_from_start)
@bot.message_handler(content_types=['document', 'audio', 'photo', 'sticker', 'voice'])
def handle_other_content(msg):
    bot.send_message(msg.chat.id, 
        "❌ Iltimos, tugmalardan foydalaning yoki film kodini kiriting.")
def auto_backup_scheduler():
    """Har 10 kunda avtomatik database backup yuborish (agar admin manual so'ramasa)"""
    while True:
        try:
            last = get_setting('last_auto_backup')
            last_manual = get_setting('last_manual_backup')
            now = datetime.now()
            should_backup = False
            if not last:
                should_backup = True
            else:
                try:
                    last_dt = datetime.fromisoformat(last)
                    if now - last_dt >= timedelta(days=10):
                        should_backup = True
                except Exception:
                    should_backup = True
            if should_backup:
                print(f"📤 Avtomatik backup yuborilmoqda ({now.strftime('%Y-%m-%d %H:%M')})")
                send_backup_to_admins()
                set_setting('last_auto_backup', now.isoformat())
                print("✅ Avtomatik backup yuborild!")
            time.sleep(3600)
        except Exception as e:
            print(f"❌ Scheduler xatosi: {e}")
            time.sleep(3600)
backup_thread = threading.Thread(target=auto_backup_scheduler, daemon=True)
backup_thread.start()
if __name__ == "__main__":
    print("="*60)
    print("🤖 Moviequi Bot ishga tushdi!")
    print(f"👑 Asosiy Admin ID: {MAIN_ADMIN_ID}")
    print(f"💾 Database: {DB_NAME}")
    print("="*60)
    print("\n✅ Bot ishlayapti...\n")
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:

        print(f"\n❌ Xatolik: {e}")
