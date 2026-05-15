import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import io
import re
import openpyxl
from datetime import datetime, timedelta, timezone
import logging
import time

# ================= CONFIG =================
BOT_TOKEN = "8752771089:AAGSi7hA5BMVXp174voI0V8uWugGPTo8Sr0"
MAIN_ADMIN = 6058876211

bot = telebot.TeleBot(BOT_TOKEN)
bot.remove_webhook()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_PATH = "premium_bot.db"
BDT = timedelta(hours=6)

def bd_time():
    return (datetime.now(timezone.utc) + BDT).strftime("%Y-%m-%d %H:%M:%S")

EMOJI = {
    "star": "⭐", "fire": "🔥", "money": "💰", "rocket": "🚀", "crown": "👑",
    "tick": "✅", "cross": "❌", "clock": "⏳", "info": "ℹ️", "warning": "⚠️",
    "file": "📁", "user": "👤", "admin": "👨‍💻", "balance": "💎", "withdraw": "💸",
    "price": "💵", "language": "🌐", "back": "🔙", "add": "➕", "remove": "❌",
    "refresh": "🔄", "data": "📊", "broadcast": "📢", "dollar": "💱", "stats": "📈",
    "pending": "⏳", "approved": "✅", "rejected": "❌", "complete": "✔️",
}

def emo(name):
    return EMOJI.get(name, "✨")

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cur = conn.cursor()
    cur.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0,
            expected_balance REAL DEFAULT 0,
            joined TEXT,
            language TEXT DEFAULT 'bangla'
        );
        CREATE TABLE IF NOT EXISTS id_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price REAL,
            status TEXT DEFAULT 'active'
        );
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            file_id TEXT,
            file_name TEXT,
            id_type TEXT,
            id_count INTEGER DEFAULT 1,
            price_per_id REAL,
            total_amount REAL,
            status TEXT DEFAULT 'pending',
            submit_date TEXT,
            approve_date TEXT,
            approved_amount REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            method TEXT,
            account TEXT,
            amount_tk REAL,
            amount_usd REAL,
            status TEXT DEFAULT 'pending',
            request_date TEXT,
            complete_date TEXT
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS used_uids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE,
            user_id INTEGER,
            submission_id INTEGER,
            added_date TEXT
        );
        CREATE TABLE IF NOT EXISTS banned (user_id INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS muted (user_id INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS monitor_groups (group_id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS data_groups (group_id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY, username TEXT);
        CREATE TABLE IF NOT EXISTS balance_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            type TEXT,
            admin_id INTEGER,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS user_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            admin_id INTEGER,
            message_text TEXT,
            file_id TEXT,
            file_type TEXT,
            timestamp TEXT
        );
    ''')
    cur.execute("INSERT OR IGNORE INTO settings VALUES ('usd_rate','125')")
    cur.execute("INSERT OR IGNORE INTO settings VALUES ('min_withdraw','10')")
    cur.execute("INSERT OR IGNORE INTO settings VALUES ('submission_open','1')")
    cur.execute("INSERT OR IGNORE INTO admins VALUES (?,?)", (MAIN_ADMIN, "MainAdmin"))
    
    if cur.execute("SELECT COUNT(*) FROM id_types").fetchone()[0] == 0:
        default_types = [
            ("Cookies", 4.0), ("2FA", 5.0), ("Clone 13", 13.0),
            ("Number 00 Friend 2FA I'D", 4.5), ("Number 00 Cookies I'D", 3.5)
        ]
        for name, price in default_types:
            cur.execute("INSERT INTO id_types (name,price) VALUES (?,?)", (name, price))
    conn.commit()
    return conn, cur

conn, cursor = init_db()

def get_setting(key, default="0"):
    res = cursor.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return res[0] if res else default

def usd_rate(): return float(get_setting('usd_rate', '125'))
def min_withdraw(): return float(get_setting('min_withdraw', '10'))
def submission_open(): return get_setting('submission_open', '1') == '1'

def is_admin(user_id):
    return user_id == MAIN_ADMIN or cursor.execute("SELECT 1 FROM admins WHERE user_id=?", (user_id,)).fetchone() is not None

def is_banned(user_id): return cursor.execute("SELECT 1 FROM banned WHERE user_id=?", (user_id,)).fetchone() is not None
def is_muted(user_id): return cursor.execute("SELECT 1 FROM muted WHERE user_id=?", (user_id,)).fetchone() is not None

def get_all_admins():
    admins = [MAIN_ADMIN]
    admins.extend([row[0] for row in cursor.execute("SELECT user_id FROM admins WHERE user_id != ?", (MAIN_ADMIN,)).fetchall()])
    return admins

def notify_admins(text, file_id=None, reply_markup=None):
    for admin_id in get_all_admins():
        try:
            if file_id:
                bot.send_document(admin_id, file_id, caption=text, parse_mode="Markdown", reply_markup=reply_markup)
            else:
                bot.send_message(admin_id, text, parse_mode="Markdown", reply_markup=reply_markup)
        except:
            pass

def monitor_log(*args):
    if len(args) == 1:
        text = args[0]
    elif len(args) == 2:
        text = args[0]
    else:
        text = f"{emo('fire')} *Monitor Log*\n\n👤 User: `{args[0]}`\n📛 @{args[1]}\n⚡ Action: {args[2]}\n📝 {args[3]}\n🕐 {bd_time()}"
    groups = cursor.execute("SELECT group_id FROM monitor_groups").fetchall()
    for g in groups:
        try:
            bot.send_message(g[0], text, parse_mode="Markdown")
        except:
            pass

def data_log(text, file_id=None):
    groups = cursor.execute("SELECT group_id FROM data_groups").fetchall()
    for g in groups:
        try:
            bot.send_message(g[0], text, parse_mode="Markdown")
            if file_id:
                bot.send_document(g[0], file_id)
        except:
            pass

def send_target_message(target_user_id, text=None, file_id=None, file_type=None, caption=None):
    try:
        if file_id and file_type:
            if file_type == 'photo':
                bot.send_photo(target_user_id, file_id, caption=caption or text, parse_mode="Markdown")
            elif file_type == 'video':
                bot.send_video(target_user_id, file_id, caption=caption or text, parse_mode="Markdown")
            elif file_type == 'document':
                bot.send_document(target_user_id, file_id, caption=caption or text, parse_mode="Markdown")
            elif file_type == 'audio':
                bot.send_audio(target_user_id, file_id, caption=caption or text, parse_mode="Markdown")
            else:
                bot.send_message(target_user_id, text or caption or "Message", parse_mode="Markdown")
        else:
            bot.send_message(target_user_id, text or "Message", parse_mode="Markdown")
        return True
    except:
        return False

def main_menu(user_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row(KeyboardButton(f"{emo('rocket')} Submit ID"), KeyboardButton(f"{emo('star')} My Profile"))
    markup.row(KeyboardButton(f"{emo('money')} Balance"), KeyboardButton(f"{emo('withdraw')} Withdraw"))
    markup.row(KeyboardButton(f"{emo('price')} Price & Rules"), KeyboardButton(f"{emo('language')} Language"))
    if is_admin(user_id):
        markup.row(KeyboardButton(f"{emo('admin')} Admin Panel"))
    return markup

def admin_panel_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row("📊 All Submissions", "📋 Withdrawals")
    markup.row(f"{emo('pending')} Pending Files", "📊 User Balance Info")
    markup.row(f"{emo('add')} Add ID Type", f"{emo('remove')} Remove ID Type")
    markup.row(f"{emo('refresh')} Toggle Submission", "📡 Monitor Groups")
    markup.row("📤 Bot Data", "📅 Files by Date")
    markup.row("👑 Admin Management", f"{emo('broadcast')} Broadcast")
    markup.row(f"{emo('dollar')} USD Rate", f"{emo('stats')} Statistics")
    markup.row("👥 User Management", "✉️ Target User")
    markup.row(f"{emo('back')} Back")
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    uname = message.from_user.username or "Unknown"
    if not cursor.execute("SELECT 1 FROM users WHERE user_id=?", (uid,)).fetchone():
        cursor.execute("INSERT INTO users (user_id,username,joined) VALUES (?,?,?)", (uid, uname, bd_time()))
        conn.commit()
    monitor_log(f"🚀 New User Started\n👤 User: {uid}\n📛 @{uname}")
    data_log(f"🆕 New User\n👤 `{uid}` @{uname}\n📅 {bd_time()}")
    bot.send_message(uid, f"{emo('fire')} *WELCOME TO MACRO SOCIAL ID SELL BOT!*\n\n✨ EARN BY SELLING SOCIAl ID'S.\n💰 Instant payments.\n{emo('rocket')} Let's begin!", parse_mode="Markdown", reply_markup=main_menu(uid))

@bot.message_handler(func=lambda m: f"{emo('language')} Language" in m.text)
def language_menu(message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🇧🇩 বাংলা", callback_data="lang_bangla"), InlineKeyboardButton("🇬🇧 English", callback_data="lang_english"))
    bot.send_message(message.chat.id, "Select your language:", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('lang_'))
def set_language(call):
    bot.answer_callback_query(call.id, "✅ Language updated!", show_alert=False)
    lang = call.data.split('_')[1]
    cursor.execute("UPDATE users SET language=? WHERE user_id=?", (lang, call.from_user.id))
    conn.commit()
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, "✅ Language updated!", reply_markup=main_menu(call.from_user.id))

@bot.message_handler(func=lambda m: f"{emo('star')} My Profile" in m.text)
def profile(message):
    bot.send_chat_action(message.chat.id, 'typing')
    uid = message.from_user.id
    user = cursor.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    if not user: return
    stats = cursor.execute("SELECT COUNT(*), SUM(CASE WHEN status='approved' THEN 1 ELSE 0 END), SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END), SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) FROM submissions WHERE user_id=?", (uid,)).fetchone()
    wd_stats = cursor.execute("SELECT COUNT(*), COALESCE(SUM(amount_tk),0) FROM withdrawals WHERE user_id=? AND status='completed'", (uid,)).fetchone()
    text = f"""{emo('crown')} *PROFILE*\n\n🆔 `{user[0]}` | @{user[1]}\n📅 Joined: {user[4]}\n\n💰 Balance: *{user[2]:.2f}* Tk\n⏳ Expected: *{user[3]:.2f}* Tk\n\n📊 *Submissions*\n📁 Total: {stats[0] or 0}\n✅ Approved: {stats[1] or 0}\n❌ Rejected: {stats[2] or 0}\n⏳ Pending: {stats[3] or 0}\n\n💸 *Withdrawals*\n📤 Total: {wd_stats[0] or 0}\n💰 Total Amount: {wd_stats[1]:.2f} Tk"""
    bot.send_message(uid, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: f"{emo('money')} Balance" in m.text)
def check_balance(message):
    bot.send_chat_action(message.chat.id, 'typing')
    uid = message.from_user.id
    bal = cursor.execute("SELECT balance, expected_balance FROM users WHERE user_id=?", (uid,)).fetchone()
    if bal:
        bot.send_message(uid, f"{emo('money')} *YOUR BALANCE*\n\n🔵 Current: *{bal[0]:.2f}* Tk\n⏳ Expected: *{bal[1]:.2f}* Tk\n💲Min Withdraw: *{min_withdraw()}* Tk", parse_mode="Markdown")

@bot.message_handler(func=lambda m: f"{emo('price')} Price & Rules" in m.text)
def price_list(message):
    bot.send_chat_action(message.chat.id, 'typing')
    types = cursor.execute("SELECT name, price, status FROM id_types").fetchall()
    text = f"{emo('money')} *PRICE LIST*\n\n"
    for t in types:
        status_emoji = "✅" if t[2] == 'active' else "❌"
        text += f"📌 *{t[0]}*: {t[1]} Tk {status_emoji}\n\n"
    text += f"📌 Min Withdraw: *{min_withdraw()}* Tk\n💱 Exchange: *1$ = {usd_rate()}* Tk"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: f"{emo('rocket')} Submit ID" in m.text)
def submit_start(message):
    uid = message.from_user.id
    if is_banned(uid):
        bot.send_message(uid, "🚫 You are banned from submitting.")
        return
    if is_muted(uid):
        bot.send_message(uid, "🔇 You are muted.")
        return
    if not submission_open() and not is_admin(uid):
        bot.send_message(uid, "⚠️ Submissions are currently closed.")
        return
    types = cursor.execute("SELECT id, name, price FROM id_types WHERE status='active'").fetchall()
    if not types:
        bot.send_message(uid, "No active ID types available.")
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for t in types:
        markup.add(InlineKeyboardButton(f"📦 {t[1]} - {t[2]} Tk", callback_data=f"subtype_{t[0]}"))
    bot.send_message(uid, "📌 CHOOSE ID TYPE⬇️:", reply_markup=markup)

user_state = {}
admin_state = {}

@bot.callback_query_handler(func=lambda c: c.data.startswith('subtype_'))
def select_subtype(call):
    uid = call.from_user.id
    tid = int(call.data.split('_')[1])
    type_info = cursor.execute("SELECT name, price FROM id_types WHERE id=?", (tid,)).fetchone()
    if not type_info:
        bot.answer_callback_query(call.id, "Invalid type!")
        return
    user_state[uid] = {'type_id': tid, 'type_name': type_info[0], 'price': type_info[1]}
    bot.delete_message(call.message.chat.id, call.message.message_id)
    msg = bot.send_message(uid, f"📦 *{type_info[0]}*\n💰 {type_info[1]} Tk per ID\n\n📎 Send your `.xlsx` file containing UIDs (first column only):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_submission_file)

def process_submission_file(message):
    uid = message.from_user.id
    if uid not in user_state: return
    if not message.document or not message.document.file_name.endswith('.xlsx'):
        bot.send_message(uid, "❌ Invalid file. Please send an xlsx file✅")
        return
    state = user_state[uid]
    file_id = message.document.file_id
    file_name = message.document.file_name
    try:
        file_info = bot.get_file(file_id)
        excel_data = bot.download_file(file_info.file_path)
        wb = openpyxl.load_workbook(io.BytesIO(excel_data))
        sheet = wb.active
        uids = []
        duplicates = []
        for row in sheet.iter_rows(values_only=True):
            if row and row[0]:
                uid_str = re.sub(r'\D', '', str(row[0]))
                if uid_str.isdigit() and len(uid_str) >= 5:
                    if cursor.execute("SELECT 1 FROM used_uids WHERE uid=?", (uid_str,)).fetchone():
                        duplicates.append(uid_str)
                    else:
                        uids.append(uid_str)
    except Exception as e:
        logging.error(f"Excel parsing error for user {uid}: {e}")
        bot.send_message(uid, "❌ Failed to read Excel file. Make sure first column contains UIDs.")
        return
    if not uids and duplicates:
        bot.send_message(uid, f"⚠️ All {len(duplicates)} UIDs are already used. Submission rejected.")
        return
    if not uids:
        bot.send_message(uid, "⚠️ No valid UIDs found in file.")
        return
    total = state['price'] * len(uids)
    cursor.execute("INSERT INTO submissions (user_id, file_id, file_name, id_type, id_count, price_per_id, total_amount, submit_date) VALUES (?,?,?,?,?,?,?,?)", (uid, file_id, file_name, state['type_name'], len(uids), state['price'], total, bd_time()))
    sub_id = cursor.lastrowid
    for u in uids:
        cursor.execute("INSERT OR IGNORE INTO used_uids (uid, user_id, submission_id, added_date) VALUES (?,?,?,?)", (u, uid, sub_id, bd_time()))
    cursor.execute("UPDATE users SET expected_balance = expected_balance + ? WHERE user_id=?", (total, uid))
    conn.commit()
    bot.send_message(uid, f"✅ *Submission #{sub_id} successful!*\n\n📦 {state['type_name']}\n📊 {len(uids)} IDs\n💰 {total} Tk added to expected balance.\n🆔 #{sub_id}", parse_mode="Markdown")
    admin_text = f"📥 *NEW SUBMISSION #{sub_id}*\n\n👤 `{uid}` @{message.from_user.username}\n📦 {state['type_name']}\n📊 {len(uids)} IDs\n💰 {total} Tk\n📅 {bd_time()}"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"{emo('tick')} Approve", callback_data=f"approve_{sub_id}"), InlineKeyboardButton(f"{emo('cross')} Reject", callback_data=f"reject_{sub_id}"), InlineKeyboardButton("📎 View File", callback_data=f"viewfile_{sub_id}"))
    notify_admins(admin_text, file_id=file_id, reply_markup=markup)
    monitor_log(uid, message.from_user.username, f"📤 SUBMITTED #{sub_id}", f"{state['type_name']} - {len(uids)} IDs")
    data_log(f"📥 *New Submission #{sub_id}*\n👤 {uid} @{message.from_user.username}\n📦 {state['type_name']}\n📊 {len(uids)} IDs\n💰 {total} Tk\nStatus: ⏳ Pending\n📅 {bd_time()}", file_id=file_id)
    del user_state[uid]

@bot.callback_query_handler(func=lambda c: c.data.startswith('viewfile_'))
def view_file_callback(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Only admins can view files.")
        return
    sub_id = int(call.data.split('_')[1])
    file_data = cursor.execute("SELECT file_id, file_name FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if file_data and file_data[0]:
        bot.send_document(call.message.chat.id, file_data[0], caption=f"📎 File for submission #{sub_id}: {file_data[1]}")
        bot.answer_callback_query(call.id, "File sent.")
    else:
        bot.answer_callback_query(call.id, "No file found for this submission.")

# ================= FIXED SUBMISSION APPROVE WITH CUSTOM AMOUNT =================
@bot.callback_query_handler(func=lambda c: c.data.startswith('approve_') and not c.data.startswith('approve_wd_'))
def approve_with_amount_prompt(call):
    """First step: Ask admin for approval amount"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only.")
        return
    
    try:
        sub_id = int(call.data.split('_')[1])
    except:
        bot.answer_callback_query(call.id, "Invalid submission ID")
        return
    
    sub = cursor.execute("SELECT user_id, id_type, total_amount, id_count, status FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if not sub:
        bot.answer_callback_query(call.id, "Submission not found.")
        return
    
    if sub[4] != 'pending':
        bot.answer_callback_query(call.id, f"Already {sub[4]}.")
        return
    
    user_id, id_type, full_amount, id_count, status = sub
    
    # Store state for this admin
    admin_state[call.from_user.id] = {
        'action_type': 'approve_submission',
        'sub_id': sub_id,
        'user_id': user_id,
        'id_type': id_type,
        'full_amount': full_amount,
        'id_count': id_count
    }
    
    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    msg_text = f"💰 *Approve Submission #{sub_id}*\n\n" \
               f"📦 Type: {id_type}\n" \
               f"📊 IDs: {id_count}\n" \
               f"📌 Full Amount: {full_amount:.2f} Tk\n\n" \
               f"Enter the amount to approve (0 to cancel):"
    
    msg = bot.send_message(call.message.chat.id, msg_text, parse_mode="Markdown")
    bot.register_next_step_handler(msg, process_approve_amount)

def process_approve_amount(message):
    """Second step: Process the approval amount"""
    admin_id = message.from_user.id
    
    if admin_id not in admin_state or admin_state[admin_id].get('action_type') != 'approve_submission':
        bot.send_message(admin_id, "❌ Session expired.")
        return
    
    state = admin_state[admin_id]
    sub_id = state['sub_id']
    user_id = state['user_id']
    id_type = state['id_type']
    id_count = state['id_count']
    full_amount = state['full_amount']
    
    try:
        amount = float(message.text.strip())
    except:
        bot.send_message(admin_id, "❌ Invalid amount. Please enter a number.")
        del admin_state[admin_id]
        return
    
    if amount == 0:
        bot.send_message(admin_id, "❌ Approval cancelled.")
        del admin_state[admin_id]
        return
    
    if amount > full_amount:
        bot.send_message(admin_id, f"❌ Amount cannot exceed {full_amount:.2f} Tk")
        del admin_state[admin_id]
        return
    
    if amount < 0:
        bot.send_message(admin_id, "❌ Amount must be positive.")
        del admin_state[admin_id]
        return
    
    # Process approval
    cursor.execute("UPDATE submissions SET status='approved', approve_date=?, approved_amount=? WHERE id=?", 
                   (bd_time(), amount, sub_id))
    cursor.execute("UPDATE users SET balance = balance + ?, expected_balance = expected_balance - ? WHERE user_id=?", 
                   (amount, full_amount, user_id))
    
    # Add to balance log
    cursor.execute("INSERT INTO balance_log (user_id, amount, type, admin_id, timestamp) VALUES (?,?,?,?,?)",
                   (user_id, amount, 'submission_approve', admin_id, bd_time()))
    conn.commit()
    
    # Notify user
    try:
        user_msg = f"{emo('tick')} *Submission #{sub_id} Approved!*\n\n" \
                   f"📦 Type: {id_type}\n" \
                   f"📊 IDs: {id_count}\n" \
                   f"💰 Amount: +{amount:.2f} Tk\n\n" \
                   f"✅ Amount added to your balance."
        bot.send_message(user_id, user_msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Failed to notify user {user_id} about approval #{sub_id}: {e}")
    
    # Confirm to admin
    admin_msg = f"✅ *Submission #{sub_id} Approved*\n\n" \
                f"👤 User: `{user_id}`\n" \
                f"📦 Type: {id_type}\n" \
                f"💰 Amount: {amount:.2f} Tk (from {full_amount:.2f})\n" \
                f"📅 {bd_time()}"
    bot.send_message(admin_id, admin_msg, parse_mode="Markdown")
    
    # Log
    monitor_log(user_id, "user", f"✅ APPROVED #{sub_id}", f"+{amount:.2f} Tk | Admin: {admin_id}")
    data_log(f"✅ *Submission Approved #{sub_id}*\n👤 {user_id}\n📦 {id_type}\n💰 +{amount:.2f} Tk\nAdmin: {admin_id}\n📅 {bd_time()}")
    
    del admin_state[admin_id]

# Keep the rejection handler
@bot.callback_query_handler(func=lambda c: c.data.startswith('reject_'))
def reject_submission(call):
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "Admins only.")
        return
    
    try:
        sub_id = int(call.data.split('_')[1])
    except:
        bot.answer_callback_query(call.id, "Invalid submission ID")
        return
    
    sub = cursor.execute("SELECT user_id, id_type, total_amount, id_count, status FROM submissions WHERE id=?", (sub_id,)).fetchone()
    if not sub:
        bot.answer_callback_query(call.id, "Submission not found.")
        return
    
    if sub[4] != 'pending':
        bot.answer_callback_query(call.id, f"Already {sub[4]}.")
        return
    
    user_id, id_type, full_amount, id_count, status = sub
    
    cursor.execute("UPDATE submissions SET status='rejected' WHERE id=?", (sub_id,))
    cursor.execute("UPDATE users SET expected_balance = expected_balance - ? WHERE user_id=?", (full_amount, user_id))
    conn.commit()
    
    try:
        user_msg = f"{emo('cross')} *Submission #{sub_id} Rejected*\n\n" \
                   f"📦 Type: {id_type}\n" \
                   f"📊 IDs: {id_count}\n" \
                   f"💰 Amount: {full_amount} Tk\n\n" \
                   f"Reason: Not accepted by admin."
        bot.send_message(user_id, user_msg, parse_mode="Markdown")
    except:
        pass
    
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, f"❌ Rejected #{sub_id}", show_alert=True)
    
    monitor_log(user_id, "user", f"❌ REJECTED #{sub_id}", f"Admin: {call.from_user.id}")
    data_log(f"❌ *Submission Rejected #{sub_id}*\n👤 {user_id}\n📦 {id_type}\nAdmin: {call.from_user.id}\n📅 {bd_time()}")

@bot.message_handler(func=lambda m: f"{emo('withdraw')} Withdraw" in m.text)
def withdraw_start(message):
    uid = message.from_user.id
    if is_banned(uid):
        bot.send_message(uid, "🚫 Banned.")
        return
    if cursor.execute("SELECT 1 FROM withdrawals WHERE user_id=? AND status='pending'", (uid,)).fetchone():
        bot.send_message(uid, "⏳ You already have a pending withdrawal request.")
        return
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("💳 Bkash", callback_data="wd_bkash"), InlineKeyboardButton("💳 Nagad", callback_data="wd_nagad"), InlineKeyboardButton("₿ Binance", callback_data="wd_binance"))
    markup.add(InlineKeyboardButton(f"{emo('back')} Back", callback_data="wd_back"))
    bot.send_message(uid, f"{emo('withdraw')} SELECT WITHDRAWL METHOD⬇️:", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == 'wd_back')
def wd_back(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, f"{emo('tick')} Main menu", reply_markup=main_menu(call.from_user.id))

@bot.callback_query_handler(func=lambda c: c.data.startswith('wd_') and c.data not in ['wd_back','wd_confirm','wd_cancel'])
def wd_method(call):
    method = call.data.split('_')[1]
    uid = call.from_user.id
    bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
    if not bal or bal[0] < min_withdraw():
        bot.answer_callback_query(call.id, f"Min withdrawal: {min_withdraw()} Tk", show_alert=True)
        return
    user_state[uid] = {'wd_method': method}
    bot.delete_message(call.message.chat.id, call.message.message_id)
    msg = bot.send_message(uid, f"💳 *{method.upper()}*\n\nSend your {method.upper()} account number:", parse_mode="Markdown")
    bot.register_next_step_handler(msg, wd_account)

def wd_account(message):
    uid = message.from_user.id
    if uid not in user_state: return
    user_state[uid]['wd_account'] = message.text.strip()
    bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()[0]
    msg = bot.send_message(uid, f"💰 Enter amount (Min: {min_withdraw()} Tk | Balance: {bal:.2f} Tk):", parse_mode="Markdown")
    bot.register_next_step_handler(msg, wd_amount)

def wd_amount(message):
    uid = message.from_user.id
    if uid not in user_state: return
    try:
        amount = float(message.text.strip())
    except:
        bot.send_message(uid, "❌ Invalid amount.")
        del user_state[uid]
        return
    bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()[0]
    if amount < min_withdraw() or amount > bal:
        bot.send_message(uid, f"❌ Amount must be between {min_withdraw()} and {bal:.2f} Tk.")
        return
    state = user_state[uid]
    state['wd_amount'] = amount
    method = state['wd_method']
    account = state['wd_account']
    confirm_text = f"📋 *Confirm Withdrawal*\n\n💳 {method.upper()}\n📱 {account}\n💰 {amount:.2f} Tk"
    if method == 'binance':
        usdt = amount / usd_rate()
        confirm_text += f"\n💱 ${usdt:.2f} USDT"
    confirm_text += "\n\n⚠️ Balance will be deducted after admin approval."
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"{emo('tick')} Confirm", callback_data="wd_confirm"), InlineKeyboardButton(f"{emo('cross')} Cancel", callback_data="wd_cancel"))
    bot.send_message(uid, confirm_text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == 'wd_confirm')
def wd_confirm(call):
    bot.answer_callback_query(call.id, "⏳ Submitting request...", show_alert=False)
    uid = call.from_user.id
    if uid not in user_state:
        bot.answer_callback_query(call.id, "Session expired!", show_alert=True)
        return
    state = user_state[uid]
    method = state['wd_method']
    account = state['wd_account']
    amount = state['wd_amount']
    usdt = amount / usd_rate() if method == 'binance' else 0
    cursor.execute("INSERT INTO withdrawals (user_id, method, account, amount_tk, amount_usd, status, request_date) VALUES (?,?,?,?,?,?,?)", (uid, method, account, amount, usdt, 'pending', bd_time()))
    wid = cursor.lastrowid
    conn.commit()
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(uid, f"✅ Withdrawal request #{wid} submitted. Wait for admin approval.", reply_markup=main_menu(uid))
    admin_text = f"💸 *NEW WITHDRAWAL #{wid}*\n\n👤 `{uid}` @{call.from_user.username}\n💳 {method.upper()}\n📱 {account}\n💰 {amount} Tk"
    if method == 'binance':
        admin_text += f"\n💱 ${usdt:.2f} USDT"
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"{emo('tick')} Approve", callback_data=f"approve_wd_{wid}"), InlineKeyboardButton(f"{emo('cross')} Reject", callback_data=f"reject_wd_{wid}"))
    notify_admins(admin_text, reply_markup=markup)
    monitor_log(uid, call.from_user.username, f"💸 WITHDRAW REQUEST #{wid}", f"{amount} Tk via {method}")
    data_log(f"💸 *New Withdrawal #{wid}*\n👤 {uid} @{call.from_user.username}\n💳 {method.upper()}\n📱 {account}\n💰 {amount} Tk" + (f"\n💱 ${usdt:.2f} USDT" if method=='binance' else "") + f"\nStatus: ⏳ Pending\n📅 {bd_time()}")
    del user_state[uid]
    bot.answer_callback_query(call.id, f"✅ Request #{wid} submitted!", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data == 'wd_cancel')
def wd_cancel(call):
    if call.from_user.id in user_state:
        del user_state[call.from_user.id]
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, f"{emo('cross')} Cancelled.", reply_markup=main_menu(call.from_user.id))

# ================= FIXED WITHDRAWAL ADMIN ACTIONS =================
@bot.callback_query_handler(func=lambda c: c.data.startswith('approve_wd_'))
def approve_withdrawal(call):
    bot.answer_callback_query(call.id, "⏳ Processing approval...", show_alert=False)
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Admins only!", show_alert=True)
        return
    
    try:
        wid = int(call.data.split('_')[2])
    except:
        bot.answer_callback_query(call.id, "❌ Invalid withdrawal ID!", show_alert=True)
        return
    
    wd = cursor.execute("SELECT user_id, amount_tk, amount_usd, method, status FROM withdrawals WHERE id=?", (wid,)).fetchone()
    if not wd:
        bot.answer_callback_query(call.id, "❌ Withdrawal not found!", show_alert=True)
        return
    
    if wd[4] != 'pending':
        bot.answer_callback_query(call.id, f"⚠️ Already {wd[4]}!", show_alert=True)
        return
    
    user_id, amount_tk, amount_usd, method, status = wd
    
    # Step 1: Deduct balance
    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=? AND balance >= ?", 
                   (amount_tk, user_id, amount_tk))
    
    if cursor.rowcount == 0:
        bot.answer_callback_query(call.id, "❌ User has insufficient balance!", show_alert=True)
        return
    
    # Step 2: Mark as completed
    cursor.execute("UPDATE withdrawals SET status='completed', complete_date=? WHERE id=?", 
                   (bd_time(), wid))
    
    # Step 3: Add to balance log
    cursor.execute("INSERT INTO balance_log (user_id, amount, type, admin_id, timestamp) VALUES (?,?,?,?,?)",
                   (user_id, -amount_tk, 'withdrawal', call.from_user.id, bd_time()))
    conn.commit()
    
    # Step 4: Notify user
    try:
        msg = f"{emo('tick')} *Withdrawal #{wid} Approved!*\n\n" \
              f"💰 Amount: {amount_tk:.2f} Tk\n" \
              f"💳 Method: {method.upper()}\n" \
              f"✅ Status: Completed\n\n" \
              f"Amount has been deducted from your balance."
              
        if method == 'binance':
            msg += f"\n💱 Equivalent: ${amount_usd:.2f} USDT"
        bot.send_message(user_id, msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Failed to notify user {user_id} about withdrawal #{wid}: {e}")
    
    # Step 5: Update admin message
    try:
        new_text = f"✅ *WITHDRAWAL #{wid} APPROVED*\n\n" \
                   f"👤 User: `{user_id}`\n" \
                   f"💳 Method: {method.upper()}\n" \
                   f"💰 Amount: {amount_tk:.2f} Tk\n" \
                   f"✅ Status: Completed\n" \
                   f"🕐 {bd_time()}"
        bot.edit_message_text(new_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    except:
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(call.from_user.id, f"✅ Withdrawal #{wid} approved.\n💰 Amount: {amount_tk:.2f} Tk")
        except:
            pass
    
    bot.answer_callback_query(call.id, f"✅ Withdrawal #{wid} Approved!", show_alert=True)
    
    # Step 6: Log to monitor and data groups
    monitor_log(f"✅ Withdrawal #{wid} Approved | User: {user_id} | Amount: {amount_tk} Tk | Admin: {call.from_user.id}")
    data_log(f"✅ *Withdrawal Approved #{wid}*\n👤 {user_id}\n💰 {amount_tk} Tk\nAdmin: {call.from_user.id}\n📅 {bd_time()}")

@bot.callback_query_handler(func=lambda c: c.data.startswith('reject_wd_'))
def reject_withdrawal(call):
    bot.answer_callback_query(call.id, "⏳ Processing rejection...", show_alert=False)
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Admins only!", show_alert=True)
        return
    
    try:
        wid = int(call.data.split('_')[2])
    except:
        bot.answer_callback_query(call.id, "❌ Invalid withdrawal ID!", show_alert=True)
        return
    
    wd = cursor.execute("SELECT user_id, amount_tk, amount_usd, method, status FROM withdrawals WHERE id=?", (wid,)).fetchone()
    if not wd:
        bot.answer_callback_query(call.id, "❌ Withdrawal not found!", show_alert=True)
        return
    
    if wd[4] != 'pending':
        bot.answer_callback_query(call.id, f"⚠️ Already {wd[4]}!", show_alert=True)
        return
    
    user_id, amount_tk, amount_usd, method, status = wd
    
    # Mark as rejected
    cursor.execute("UPDATE withdrawals SET status='rejected' WHERE id=?", (wid,))
    conn.commit()
    
    # Notify user
    try:
        msg = f"{emo('cross')} *Withdrawal #{wid} Rejected*\n\n" \
              f"💰 Amount: {amount_tk:.2f} Tk\n" \
              f"💳 Method: {method.upper()}\n" \
              f"❌ Status: Rejected\n\n" \
              f"Your balance was not deducted. Contact support if needed."
        if method == 'binance':
            msg += f"\n💱 Requested: ${amount_usd:.2f} USDT"
        bot.send_message(user_id, msg, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Failed to notify user {user_id} about withdrawal rejection #{wid}: {e}")
    
    # Update admin message
    try:
        new_text = f"❌ *WITHDRAWAL #{wid} REJECTED*\n\n" \
                   f"👤 User: `{user_id}`\n" \
                   f"💳 Method: {method.upper()}\n" \
                   f"💰 Amount: {amount_tk:.2f} Tk\n" \
                   f"❌ Status: Rejected\n" \
                   f"🕐 {bd_time()}"
        bot.edit_message_text(new_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    except:
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
            bot.send_message(call.from_user.id, f"❌ Withdrawal #{wid} rejected!")
        except:
            pass
    
    bot.answer_callback_query(call.id, f"❌ Withdrawal #{wid} Rejected!", show_alert=True)
    
    # Log
    monitor_log(f"❌ Withdrawal #{wid} Rejected | User: {user_id} | Admin: {call.from_user.id}")
    data_log(f"❌ *Withdrawal Rejected #{wid}*\n👤 {user_id}\nAdmin: {call.from_user.id}\n📅 {bd_time()}")

# ================= ADMIN PANEL =================
@bot.message_handler(func=lambda m: f"{emo('admin')} Admin Panel" in m.text and is_admin(m.from_user.id))
def admin_panel(message):
    bot.send_chat_action(message.chat.id, 'typing')
    bot.send_message(message.chat.id, f"{emo('crown')} *Admin Panel*", parse_mode="Markdown", reply_markup=admin_panel_menu())

@bot.message_handler(func=lambda m: f"{emo('back')} Back" in m.text and is_admin(m.from_user.id))
def back_to_main(message):
    bot.send_chat_action(message.chat.id, 'typing')
    bot.send_message(message.chat.id, f"{emo('tick')} Back to main menu", reply_markup=main_menu(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == "📊 All Submissions" and is_admin(m.from_user.id))
def all_submissions(message):
    bot.send_chat_action(message.chat.id, 'typing')
    subs = cursor.execute("SELECT id, user_id, id_type, id_count, total_amount, status, submit_date FROM submissions ORDER BY id DESC LIMIT 30").fetchall()
    if not subs:
        bot.send_message(message.chat.id, "No submissions yet.")
        return
    text = "📊 *ALL SUBMISSIONS (last 30)*\n\n"
    for s in subs:
        emoji = "✅" if s[5]=='approved' else "❌" if s[5]=='rejected' else "⏳"
        text += f"#{s[0]} | {s[6][:10]} | 👤 {s[1]}\n└ {s[2]} | {s[3]}x | {s[4]} Tk | {emoji}\n\n"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📋 Withdrawals" and is_admin(m.from_user.id))
def all_withdrawals(message):
    bot.send_chat_action(message.chat.id, 'typing')
    wds = cursor.execute("SELECT w.id, w.user_id, u.username, w.method, w.amount_tk, w.amount_usd, w.status, w.request_date FROM withdrawals w LEFT JOIN users u ON w.user_id=u.user_id ORDER BY w.id DESC LIMIT 30").fetchall()
    if not wds:
        bot.send_message(message.chat.id, "No withdrawals yet.")
        return
    text = "📋 *WITHDRAWALS (last 30)*\n\n"
    markup = InlineKeyboardMarkup(row_width=2)
    for w in wds:
        emoji = "✅" if w[6]=='completed' else "❌" if w[6]=='rejected' else "⏳"
        text += f"#{w[0]} | @{w[2] or w[1]} | {w[3]} | {w[4]} Tk"
        if w[3] == 'binance':
            text += f" | ${w[5]:.2f}"
        text += f" | {emoji} | {w[7][:16]}\n"
        if w[6] == 'pending':
            markup.add(InlineKeyboardButton(f"✅ #{w[0]}", callback_data=f"approve_wd_{w[0]}"), InlineKeyboardButton(f"❌ #{w[0]}", callback_data=f"reject_wd_{w[0]}"))
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup if markup.keyboard else None)

@bot.message_handler(func=lambda m: m.text == f"{emo('pending')} Pending Files" and is_admin(m.from_user.id))
def pending_files(message):
    bot.send_chat_action(message.chat.id, 'typing')
    pendings = cursor.execute("SELECT id, user_id, id_type, id_count, total_amount, submit_date FROM submissions WHERE status='pending' ORDER BY id DESC LIMIT 30").fetchall()
    if not pendings:
        bot.send_message(message.chat.id, "✅ No pending files.")
        return
    text = f"{emo('pending')} *PENDING FILES*\n\n"
    for p in pendings:
        text += f"#{p[0]} | 👤 {p[1]} | 📦 {p[2]} | 📊 {p[3]}x | 💰 {p[4]} Tk | 📅 {p[5][:10]}\n"
    markup = InlineKeyboardMarkup(row_width=3)
    for p in pendings[:12]:
        markup.add(InlineKeyboardButton(f"✅ #{p[0]}", callback_data=f"approve_{p[0]}"), InlineKeyboardButton(f"❌ #{p[0]}", callback_data=f"reject_{p[0]}"), InlineKeyboardButton(f"📎 File", callback_data=f"viewfile_{p[0]}"))
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📊 User Balance Info" and is_admin(m.from_user.id))
def user_balance_info(message):
    bot.send_chat_action(message.chat.id, 'typing')
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton(f"{emo('add')} Add Balance", callback_data="ub_add"), InlineKeyboardButton(f"{emo('remove')} Remove Balance", callback_data="ub_remove"), InlineKeyboardButton("👥 All Users", callback_data="ub_all"), InlineKeyboardButton("📋 Balance Log", callback_data="ub_history"))
    bot.send_message(message.chat.id, "📊 *User Balance Management*", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data in ['ub_add', 'ub_remove'])
def ub_action(call):
    admin_state[call.from_user.id] = {'action': call.data[3:]}
    bot.delete_message(call.message.chat.id, call.message.message_id)
    msg = bot.send_message(call.message.chat.id, "Send user ID or @username:")
    bot.register_next_step_handler(msg, ub_get_user)

def ub_get_user(message):
    admin_id = message.from_user.id
    if admin_id not in admin_state: return
    identifier = message.text.strip().replace('@','')
    user = cursor.execute("SELECT user_id, username, balance FROM users WHERE user_id=? OR username=?", (identifier if identifier.isdigit() else 0, identifier)).fetchone()
    if not user:
        bot.send_message(admin_id, "❌ User not found.")
        del admin_state[admin_id]
        return
    admin_state[admin_id]['user_id'] = user[0]
    admin_state[admin_id]['username'] = user[1]
    admin_state[admin_id]['current_bal'] = user[2]
    bot.send_message(admin_id, f"👤 @{user[1]} | Current balance: {user[2]:.2f} Tk\n\nEnter amount to {admin_state[admin_id]['action']}:")
    bot.register_next_step_handler(message, ub_amount)

def ub_amount(message):
    admin_id = message.from_user.id
    if admin_id not in admin_state: return
    try:
        amt = float(message.text.strip())
    except:
        bot.send_message(admin_id, "❌ Invalid amount.")
        del admin_state[admin_id]
        return
    if amt <= 0:
        bot.send_message(admin_id, "Amount must be positive.")
        return
    state = admin_state[admin_id]
    if state['action'] == 'remove' and amt > state['current_bal']:
        bot.send_message(admin_id, f"❌ Cannot remove more than current balance ({state['current_bal']:.2f} Tk).")
        return
    state['amount'] = amt
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"{emo('tick')} Confirm", callback_data="ub_confirm"), InlineKeyboardButton(f"{emo('cross')} Cancel", callback_data="ub_cancel"))
    bot.send_message(admin_id, f"⚠️ {state['action'].upper()} {amt} Tk for @{state['username']}?", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == 'ub_confirm')
def ub_confirm(call):
    admin_id = call.from_user.id
    if admin_id not in admin_state: return
    state = admin_state[admin_id]
    uid = state['user_id']
    amt = state['amount']
    action = state['action']
    if action == 'add':
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
    else:
        cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amt, uid))
    cursor.execute("INSERT INTO balance_log (user_id, amount, type, admin_id, timestamp) VALUES (?,?,?,?,?)", (uid, amt, action, admin_id, bd_time()))
    conn.commit()
    new_bal = cursor.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()[0]
    try:
        bot.send_message(uid, f"💰 Admin {action}ed {amt:.2f} Tk. New balance: {new_bal:.2f} Tk")
    except:
        pass
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(admin_id, f"✅ Done. New balance: {new_bal:.2f} Tk")
    del admin_state[admin_id]

@bot.callback_query_handler(func=lambda c: c.data == 'ub_cancel')
def ub_cancel(call):
    if call.from_user.id in admin_state:
        del admin_state[call.from_user.id]
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, "Cancelled.")

@bot.callback_query_handler(func=lambda c: c.data == 'ub_all')
def ub_all_users(call):
    users = cursor.execute("SELECT user_id, username, balance FROM users ORDER BY balance DESC").fetchall()
    text = "👥 *ALL USERS*\n\n" + "\n".join([f"{i}. @{u[1] or u[0]} – {u[2]:.2f} Tk" for i, u in enumerate(users, 1)]) + f"\n📊 Total: {len(users)}"
    bot.send_message(call.message.chat.id, text, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == 'ub_history')
def ub_history(call):
    logs = cursor.execute("SELECT timestamp, (SELECT username FROM users WHERE user_id=bl.user_id), amount, type FROM balance_log bl ORDER BY id DESC LIMIT 50").fetchall()
    if not logs:
        bot.send_message(call.message.chat.id, "No balance logs yet.")
        return
    text = "📋 *BALANCE LOG (last 50)*\n\n"
    for l in logs:
        sign = "+" if l[3]=='add' else "-"
        text += f"`{l[0][:16]}` @{l[1] or l[0]} {sign}{l[2]:.2f} Tk\n"
    bot.send_message(call.message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == f"{emo('add')} Add ID Type" and is_admin(m.from_user.id))
def add_id_type(message):
    msg = bot.send_message(message.chat.id, "Format: `Name | Price`\nExample: `Premium ID | 7.5`", parse_mode="Markdown")
    bot.register_next_step_handler(msg, lambda m: add_id_exec(m))

def add_id_exec(message):
    try:
        name, price = [x.strip() for x in message.text.split('|', 1)]
        price = float(price)
        cursor.execute("INSERT INTO id_types (name, price) VALUES (?,?)", (name, price))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Added: {name} - {price} Tk")
    except:
        bot.send_message(message.chat.id, "❌ Invalid format. Use: Name | Price")

@bot.message_handler(func=lambda m: m.text == f"{emo('remove')} Remove ID Type" and is_admin(m.from_user.id))
def remove_id_type(message):
    types = cursor.execute("SELECT id, name FROM id_types").fetchall()
    if not types:
        bot.send_message(message.chat.id, "No ID types to remove.")
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for t in types:
        markup.add(InlineKeyboardButton(f"❌ {t[1]}", callback_data=f"del_id_{t[0]}"))
    bot.send_message(message.chat.id, "Select type to remove:", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('del_id_'))
def del_id_callback(call):
    tid = int(call.data.split('_')[2])
    cursor.execute("DELETE FROM id_types WHERE id=?", (tid,))
    conn.commit()
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Removed successfully.", show_alert=True)

@bot.message_handler(func=lambda m: m.text == f"{emo('refresh')} Toggle Submission" and is_admin(m.from_user.id))
def toggle_submission(message):
    current = submission_open()
    new = "0" if current else "1"
    cursor.execute("UPDATE settings SET value=? WHERE key='submission_open'", (new,))
    conn.commit()
    status = "OPEN" if new == "1" else "CLOSED"
    bot.send_message(message.chat.id, f"🔄 Submissions are now *{status}*", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == f"{emo('dollar')} USD Rate" and is_admin(m.from_user.id))
def set_usd(message):
    msg = bot.send_message(message.chat.id, f"Current rate: 1$ = {usd_rate()} Tk\nSend new rate:")
    bot.register_next_step_handler(msg, lambda m: set_usd_exec(m))

def set_usd_exec(message):
    try:
        rate = float(message.text.strip())
        cursor.execute("UPDATE settings SET value=? WHERE key='usd_rate'", (str(rate),))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ USD rate updated to {rate} Tk")
    except:
        bot.send_message(message.chat.id, "❌ Invalid number.")

@bot.message_handler(func=lambda m: m.text == f"{emo('stats')} Statistics" and is_admin(m.from_user.id))
def stats(message):
    bot.send_chat_action(message.chat.id, 'typing')
    total_users = cursor.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    approved_subs = cursor.execute("SELECT COUNT(*), SUM(total_amount) FROM submissions WHERE status='approved'").fetchone()
    completed_wds = cursor.execute("SELECT COUNT(*), SUM(amount_tk) FROM withdrawals WHERE status='completed'").fetchone()
    text = f"""📊 *STATISTICS*\n👥 Users: {total_users}\n✅ Approved submissions: {approved_subs[0] or 0} (Total: {approved_subs[1] or 0:.2f} Tk)\n💸 Completed withdrawals: {completed_wds[0] or 0} (Total: {completed_wds[1] or 0:.2f} Tk)\n💱 USD rate: 1$ = {usd_rate()} Tk"""
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "📡 Monitor Groups" and is_admin(m.from_user.id))
def monitor_groups(message):
    groups = cursor.execute("SELECT group_id FROM monitor_groups").fetchall()
    text = "📡 *Monitor Groups*\n" + ("\n".join([f"`{g[0]}`" for g in groups]) if groups else "None")
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(f"{emo('add')} Add", callback_data="mg_add"), InlineKeyboardButton(f"{emo('remove')} Remove", callback_data="mg_remove"))
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == 'mg_add')
def mg_add(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    msg = bot.send_message(call.message.chat.id, "Send group ID (e.g., -1001234567890):")
    bot.register_next_step_handler(msg, mg_add_exec)

def mg_add_exec(message):
    gid = message.text.strip()
    try:
        bot.send_message(gid, "✅ Monitor bot connected!")
        cursor.execute("INSERT OR IGNORE INTO monitor_groups VALUES (?)", (gid,))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Added {gid}")
    except:
        bot.send_message(message.chat.id, "❌ Failed. Make sure bot is admin in that group.")

@bot.callback_query_handler(func=lambda c: c.data == 'mg_remove')
def mg_remove(call):
    groups = cursor.execute("SELECT group_id FROM monitor_groups").fetchall()
    if not groups:
        bot.answer_callback_query(call.id, "No groups to remove.")
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for g in groups:
        markup.add(InlineKeyboardButton(f"❌ {g[0]}", callback_data=f"mg_del_{g[0]}"))
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, "Select group to remove:", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('mg_del_'))
def mg_del(call):
    gid = call.data[7:]
    cursor.execute("DELETE FROM monitor_groups WHERE group_id=?", (gid,))
    conn.commit()
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Removed")

@bot.message_handler(func=lambda m: m.text == "📤 Bot Data" and is_admin(m.from_user.id))
def bot_data(message):
    groups = cursor.execute("SELECT group_id FROM data_groups").fetchall()
    text = "📤 *Bot Data Groups*\nConnected: " + str(len(groups))
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton(f"{emo('add')} Add", callback_data="dg_add"), InlineKeyboardButton(f"{emo('remove')} Remove", callback_data="dg_remove"), InlineKeyboardButton("📋 List", callback_data="dg_list"), InlineKeyboardButton("📤 Export", callback_data="dg_export"))
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == 'dg_add')
def dg_add(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    msg = bot.send_message(call.message.chat.id, "Send group ID for data log:")
    bot.register_next_step_handler(msg, dg_add_exec)

def dg_add_exec(message):
    gid = message.text.strip()
    try:
        bot.send_message(gid, "✅ Data group connected. All submissions/withdrawals will be logged here with files.")
        cursor.execute("INSERT OR IGNORE INTO data_groups VALUES (?)", (gid,))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ Added {gid}")
    except:
        bot.send_message(message.chat.id, "❌ Failed.")

@bot.callback_query_handler(func=lambda c: c.data == 'dg_remove')
def dg_remove(call):
    groups = cursor.execute("SELECT group_id FROM data_groups").fetchall()
    if not groups:
        bot.answer_callback_query(call.id, "No groups.")
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for g in groups:
        markup.add(InlineKeyboardButton(f"❌ {g[0]}", callback_data=f"dg_del_{g[0]}"))
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, "Select group to remove:", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('dg_del_'))
def dg_del(call):
    gid = call.data[7:]
    cursor.execute("DELETE FROM data_groups WHERE group_id=?", (gid,))
    conn.commit()
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Removed")

@bot.callback_query_handler(func=lambda c: c.data == 'dg_list')
def dg_list(call):
    groups = cursor.execute("SELECT group_id FROM data_groups").fetchall()
    text = "📋 *Data Groups*\n" + ("\n".join([f"`{g[0]}`" for g in groups]) if groups else "None")
    bot.send_message(call.message.chat.id, text, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data == 'dg_export')
def dg_export(call):
    users = cursor.execute("SELECT user_id, username, balance, expected_balance FROM users").fetchall()
    text = "📊 *All Users*\n\n" + "\n".join([f"👤 `{u[0]}` @{u[1] or ''} | 💰 {u[2]:.2f} | ⏳ {u[3]:.2f}" for u in users])[:4000]
    for g in cursor.execute("SELECT group_id FROM data_groups").fetchall():
        try:
            bot.send_message(g[0], text, parse_mode="Markdown")
        except:
            pass
    bot.answer_callback_query(call.id, "Exported to data groups.")

@bot.message_handler(func=lambda m: m.text == "📅 Files by Date" and is_admin(m.from_user.id))
def files_by_date(message):
    msg = bot.send_message(message.chat.id, "📅 Enter date (DD-MM-YYYY or DD):")
    bot.register_next_step_handler(msg, send_files_for_date)

def send_files_for_date(message):
    date_input = message.text.strip()
    try:
        if '-' in date_input:
            target_date = datetime.strptime(date_input, "%d-%m-%Y").strftime("%Y-%m-%d")
        else:
            day = int(date_input)
            now = datetime.now()
            target_date = datetime(now.year, now.month, day).strftime("%Y-%m-%d")
    except:
        bot.send_message(message.chat.id, "❌ Invalid date format.")
        return
    submissions = cursor.execute("SELECT id, user_id, file_id, file_name, id_type, id_count, total_amount, status FROM submissions WHERE DATE(submit_date) = ?", (target_date,)).fetchall()
    if not submissions:
        bot.send_message(message.chat.id, f"📅 No submissions found for {target_date}.")
        return
    bot.send_message(message.chat.id, f"📅 *Files for {target_date}*\nFound {len(submissions)} submissions. Sending files...", parse_mode="Markdown")
    for sub in submissions:
        sub_id, uid, file_id, filename, id_type, count, amount, status = sub
        emoji = "✅" if status=='approved' else "❌" if status=='rejected' else "⏳"
        caption = f"📁 #{sub_id} | 👤 {uid} | {id_type} x{count} | {amount} Tk | {emoji}\n📎 {filename}"
        try:
            bot.send_document(message.chat.id, file_id, caption=caption)
        except:
            bot.send_message(message.chat.id, f"⚠️ Could not send file for #{sub_id}")
    bot.send_message(message.chat.id, "✅ All files sent.")

@bot.message_handler(func=lambda m: m.text == "✉️ Target User" and is_admin(m.from_user.id))
def target_user_menu(message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("📝 Text Message", callback_data="target_text"), InlineKeyboardButton("🖼️ Photo", callback_data="target_photo"), InlineKeyboardButton("🎥 Video", callback_data="target_video"), InlineKeyboardButton("📎 Document", callback_data="target_document"), InlineKeyboardButton("🎵 Audio", callback_data="target_audio"))
    bot.send_message(message.chat.id, "✉️ *Send Message to Specific User*\n\nChoose message type:", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('target_'))
def target_get_user(call):
    msg_type = call.data.split('_')[1]
    admin_state[call.from_user.id] = {'target_type': msg_type}
    bot.delete_message(call.message.chat.id, call.message.message_id)
    msg = bot.send_message(call.message.chat.id, "📝 Send the username (without @) or user ID of the target user:")
    bot.register_next_step_handler(msg, target_get_content)

def target_get_content(message):
    admin_id = message.from_user.id
    if admin_id not in admin_state: return
    identifier = message.text.strip().replace('@', '')
    user = cursor.execute("SELECT user_id, username FROM users WHERE user_id=? OR username=?", (identifier if identifier.isdigit() else 0, identifier)).fetchone()
    if not user:
        bot.send_message(admin_id, f"❌ User not found: {identifier}")
        del admin_state[admin_id]
        return
    admin_state[admin_id]['target_user_id'] = user[0]
    admin_state[admin_id]['target_username'] = user[1]
    msg_type = admin_state[admin_id]['target_type']
    if msg_type == 'text':
        msg = bot.send_message(admin_id, f"👤 Target: @{user[1] or user[0]}\n\n📝 Send your text message:")
        bot.register_next_step_handler(msg, target_send_text)
    else:
        msg = bot.send_message(admin_id, f"👤 Target: @{user[1] or user[0]}\n\nSend the media (with optional caption):")
        bot.register_next_step_handler(msg, target_send_media)

def target_send_text(message):
    admin_id = message.from_user.id
    if admin_id not in admin_state: return
    target_id = admin_state[admin_id]['target_user_id']
    target_name = admin_state[admin_id]['target_username']
    text = message.text
    success = send_target_message(target_id, text=text)
    if success:
        bot.send_message(admin_id, f"✅ Message sent successfully to @{target_name or target_id}!")
        cursor.execute("INSERT INTO user_messages (user_id, admin_id, message_text, timestamp) VALUES (?,?,?,?)", (target_id, admin_id, text, bd_time()))
        conn.commit()
    else:
        bot.send_message(admin_id, f"❌ Failed to send message to @{target_name or target_id}.")
    del admin_state[admin_id]

def target_send_media(message):
    admin_id = message.from_user.id
    if admin_id not in admin_state: return
    target_id = admin_state[admin_id]['target_user_id']
    target_name = admin_state[admin_id]['target_username']
    msg_type = admin_state[admin_id]['target_type']
    caption = message.caption if message.caption else None
    file_id = None
    file_type = None
    if msg_type == 'photo' and message.photo:
        file_id = message.photo[-1].file_id
        file_type = 'photo'
    elif msg_type == 'video' and message.video:
        file_id = message.video.file_id
        file_type = 'video'
    elif msg_type == 'document' and message.document:
        file_id = message.document.file_id
        file_type = 'document'
    elif msg_type == 'audio' and message.audio:
        file_id = message.audio.file_id
        file_type = 'audio'
    else:
        bot.send_message(admin_id, f"❌ Invalid media type.")
        del admin_state[admin_id]
        return
    success = send_target_message(target_id, text=caption, file_id=file_id, file_type=file_type)
    if success:
        bot.send_message(admin_id, f"✅ Media sent successfully to @{target_name or target_id}!")
        cursor.execute("INSERT INTO user_messages (user_id, admin_id, message_text, file_id, file_type, timestamp) VALUES (?,?,?,?,?,?)", (target_id, admin_id, caption, file_id, file_type, bd_time()))
        conn.commit()
    else:
        bot.send_message(admin_id, f"❌ Failed to send media to @{target_name or target_id}.")
    del admin_state[admin_id]

@bot.message_handler(func=lambda m: m.text == f"{emo('broadcast')} Broadcast" and is_admin(m.from_user.id))
def broadcast_menu(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📝 Text Message", callback_data="broadcast_text"), InlineKeyboardButton("📎 Media/File", callback_data="broadcast_media"))
    bot.send_message(message.chat.id, "📢 *Broadcast* – Choose type:", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('broadcast_'))
def broadcast_type(call):
    btype = call.data.split('_')[1]
    admin_state[call.from_user.id] = {'broadcast_type': btype}
    bot.delete_message(call.message.chat.id, call.message.message_id)
    if btype == 'text':
        msg = bot.send_message(call.message.chat.id, "Send the text message to broadcast:")
        bot.register_next_step_handler(msg, broadcast_send)
    else:
        msg = bot.send_message(call.message.chat.id, "Send the media (photo, video, document) to broadcast:")
        bot.register_next_step_handler(msg, broadcast_send)

def broadcast_send(message):
    admin_id = message.from_user.id
    if admin_id not in admin_state: return
    btype = admin_state[admin_id]['broadcast_type']
    users = cursor.execute("SELECT user_id FROM users").fetchall()
    success = 0
    fail = 0
    for (uid,) in users:
        try:
            if btype == 'text':
                bot.send_message(uid, message.text, parse_mode="Markdown")
            elif message.document:
                bot.send_document(uid, message.document.file_id, caption=message.caption)
            elif message.photo:
                bot.send_photo(uid, message.photo[-1].file_id, caption=message.caption)
            elif message.video:
                bot.send_video(uid, message.video.file_id, caption=message.caption)
            else:
                bot.send_message(uid, "Broadcast message", parse_mode="Markdown")
            success += 1
        except:
            fail += 1
    bot.send_message(admin_id, f"✅ Broadcast complete.\nSent: {success}\nFailed: {fail}")
    del admin_state[admin_id]

@bot.message_handler(func=lambda m: m.text == "👥 User Management" and is_admin(m.from_user.id))
def user_management(message):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("🚫 Ban User", callback_data="um_ban"), InlineKeyboardButton("🔇 Mute User", callback_data="um_mute"), InlineKeyboardButton("✅ Unban User", callback_data="um_unban"), InlineKeyboardButton("🔊 Unmute User", callback_data="um_unmute"))
    bot.send_message(message.chat.id, "👥 *User Management*", parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('um_'))
def um_action(call):
    action = call.data[3:]
    if action in ['ban', 'mute']:
        bot.delete_message(call.message.chat.id, call.message.message_id)
        msg = bot.send_message(call.message.chat.id, f"Send user ID to {action}:")
        bot.register_next_step_handler(msg, lambda m: um_set(m, action))
    elif action == 'unban':
        banned = cursor.execute("SELECT user_id FROM banned").fetchall()
        if not banned:
            bot.answer_callback_query(call.id, "No banned users.")
            return
        markup = InlineKeyboardMarkup(row_width=1)
        for (uid,) in banned:
            markup.add(InlineKeyboardButton(f"Unban {uid}", callback_data=f"unban_{uid}"))
        bot.edit_message_text("Select user to unban:", call.message.chat.id, call.message.message_id, reply_markup=markup)
    elif action == 'unmute':
        muted = cursor.execute("SELECT user_id FROM muted").fetchall()
        if not muted:
            bot.answer_callback_query(call.id, "No muted users.")
            return
        markup = InlineKeyboardMarkup(row_width=1)
        for (uid,) in muted:
            markup.add(InlineKeyboardButton(f"Unmute {uid}", callback_data=f"unmute_{uid}"))
        bot.edit_message_text("Select user to unmute:", call.message.chat.id, call.message.message_id, reply_markup=markup)

def um_set(message, action):
    try:
        uid = int(message.text.strip())
    except:
        bot.send_message(message.chat.id, "❌ Invalid user ID.")
        return
    if action == 'ban':
        cursor.execute("INSERT OR IGNORE INTO banned VALUES (?)", (uid,))
    else:
        cursor.execute("INSERT OR IGNORE INTO muted VALUES (?)", (uid,))
    conn.commit()
    bot.send_message(message.chat.id, f"✅ User {uid} has been {action}ed.")

@bot.callback_query_handler(func=lambda c: c.data.startswith('unban_'))
def unban_user(call):
    uid = int(call.data.split('_')[1])
    cursor.execute("DELETE FROM banned WHERE user_id=?", (uid,))
    conn.commit()
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, f"Unbanned {uid}", show_alert=True)

@bot.callback_query_handler(func=lambda c: c.data.startswith('unmute_'))
def unmute_user(call):
    uid = int(call.data.split('_')[1])
    cursor.execute("DELETE FROM muted WHERE user_id=?", (uid,))
    conn.commit()
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, f"Unmuted {uid}", show_alert=True)

@bot.message_handler(func=lambda m: m.text == "👑 Admin Management" and is_admin(m.from_user.id))
def admin_management(message):
    if message.from_user.id != MAIN_ADMIN:
        bot.send_message(message.chat.id, "Only the main admin can manage admins.")
        return
    admins = cursor.execute("SELECT user_id, username FROM admins").fetchall()
    text = "👑 *Admins*\n" + "\n".join([f"⭐ @{a[1] or a[0]} ({a[0]})" for a in admins])
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton(f"{emo('add')} Add Admin", callback_data="adm_add"), InlineKeyboardButton(f"{emo('remove')} Remove Admin", callback_data="adm_remove"))
    bot.send_message(message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == 'adm_add')
def adm_add(call):
    if call.from_user.id != MAIN_ADMIN:
        bot.answer_callback_query(call.id, "Only main admin.")
        return
    bot.delete_message(call.message.chat.id, call.message.message_id)
    msg = bot.send_message(call.message.chat.id, "Send username (without @) of the new admin:")
    bot.register_next_step_handler(msg, adm_add_exec)

def adm_add_exec(message):
    uname = message.text.strip()
    user = cursor.execute("SELECT user_id, username FROM users WHERE username=?", (uname,)).fetchone()
    if not user:
        bot.send_message(message.chat.id, "❌ User not found. Make sure they have started the bot.")
        return
    cursor.execute("INSERT OR IGNORE INTO admins VALUES (?,?)", (user[0], user[1]))
    conn.commit()
    bot.send_message(message.chat.id, f"✅ Added @{uname} as admin.")

@bot.callback_query_handler(func=lambda c: c.data == 'adm_remove')
def adm_remove(call):
    if call.from_user.id != MAIN_ADMIN:
        bot.answer_callback_query(call.id, "Only main admin.")
        return
    admins = cursor.execute("SELECT user_id, username FROM admins WHERE user_id != ?", (MAIN_ADMIN,)).fetchall()
    if not admins:
        bot.answer_callback_query(call.id, "No other admins to remove.")
        return
    markup = InlineKeyboardMarkup(row_width=1)
    for a in admins:
        markup.add(InlineKeyboardButton(f"❌ @{a[1] or a[0]}", callback_data=f"adm_del_{a[0]}"))
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, "Select admin to remove:", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith('adm_del_'))
def adm_del(call):
    uid = int(call.data.split('_')[2])
    cursor.execute("DELETE FROM admins WHERE user_id=?", (uid,))
    conn.commit()
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.answer_callback_query(call.id, "Admin removed.", show_alert=True)

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 BOT STARTED SUCCESSFULLY!")
    print("✅ Withdrawal Approve: Working with all checks!")
    print("✅ Submission Approve: Amount selection by admin!")
    print("=" * 50)
    bot.infinity_polling(timeout=60, interval=0)