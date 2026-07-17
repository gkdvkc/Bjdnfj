import telebot
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
    Message, CallbackQuery
)
import json
import time
import random
from datetime import datetime, timedelta
import threading
import os
import hashlib
import re
from collections import defaultdict, deque

# ========== تنظیمات ==========
BOT_TOKEN = "8793482183:AAEGUa7ZEURP26N34DzKvrudnndC3q7apBk"
ADMIN_IDS = [8680457924]  # ادمین‌های اصلی بات
bot = telebot.TeleBot(BOT_TOKEN)

# ========== دیتابیس پیشرفته ==========
class Database:
    def __init__(self):
        # تنظیمات گروه‌ها
        self.groups = {}
        # اطلاعات کاربران (گزارش تخلفات، اخطارها)
        self.users = defaultdict(lambda: {"warnings": {}, "muted_until": 0, "messages": deque(maxlen=10)})
        # داده‌های کپچا
        self.captcha_data = {}
        # آمار کلی
        self.stats = {
            "total_messages": 0,
            "total_bans": 0,
            "total_kicks": 0,
            "total_mutes": 0,
            "total_warns": 0,
            "total_captcha_passed": 0,
            "total_captcha_failed": 0,
        }
        # تنظیمات پیش‌فرض گروه
        self.default_settings = {
            "welcome": "👋 به گروه خوش آمدید {user_name}!",
            "captcha": True,
            "captcha_timeout": 60,
            "anti_spam": True,
            "spam_threshold": 5,       # تعداد پیام در ثانیه
            "spam_action": "mute",     # mute, kick, ban
            "spam_duration": 300,      # ثانیه
            "anti_raid": True,
            "raid_threshold": 5,       # تعداد عضو جدید در ۱۰ ثانیه
            "raid_action": "kick",
            "anti_mentions": True,
            "mention_limit": 3,
            "anti_caps": True,
            "caps_limit": 70,          # درصد حروف بزرگ
            "anti_emoji": True,
            "emoji_limit": 5,
            "anti_newlines": True,
            "newline_limit": 5,
            "auto_delete": False,
            "auto_delete_seconds": 60,
            "log_channel": None,
            "warn_limit": 3,
            "warn_action": "mute",     # mute, kick, ban
            "warn_duration": 3600,
        }
        # نمونه‌های اولیه (اختیاری)
        self._init_sample()

    def _init_sample(self):
        # برای نمایش در دمو
        pass

    def get_group(self, group_id):
        if group_id not in self.groups:
            self.groups[group_id] = self.default_settings.copy()
        return self.groups[group_id]

    def get_user(self, user_id):
        return self.users[user_id]

    def add_warning(self, group_id, user_id, reason):
        user = self.get_user(user_id)
        if group_id not in user["warnings"]:
            user["warnings"][group_id] = []
        user["warnings"][group_id].append({
            "time": datetime.now().isoformat(),
            "reason": reason
        })
        self.stats["total_warns"] += 1
        return len(user["warnings"][group_id])

    def clear_warnings(self, group_id, user_id):
        user = self.get_user(user_id)
        if group_id in user["warnings"]:
            user["warnings"][group_id] = []
            return True
        return False

    def set_mute(self, user_id, duration):
        self.users[user_id]["muted_until"] = int(time.time()) + duration

    def remove_mute(self, user_id):
        self.users[user_id]["muted_until"] = 0

    def is_muted(self, user_id):
        return self.users[user_id]["muted_until"] > int(time.time())

    def add_message(self, user_id):
        self.users[user_id]["messages"].append(time.time())
        self.stats["total_messages"] += 1

    def get_message_count(self, user_id, seconds):
        """تعداد پیام‌های کاربر در چند ثانیه اخیر"""
        now = time.time()
        msgs = self.users[user_id]["messages"]
        count = sum(1 for t in msgs if now - t <= seconds)
        return count

    def get_raid_count(self, group_id, seconds):
        """تعداد کاربران جدید در گروه در چند ثانیه اخیر"""
        # برای سادگی، در اینجا از یک لیست جداگانه استفاده نمی‌کنیم، اما می‌توانیم پیاده‌سازی کنیم
        # فعلاً از یک دیکشنری ساده برای ذخیره زمان ورود استفاده می‌کنیم
        if not hasattr(self, '_join_times'):
            self._join_times = {}
        key = f"{group_id}_{int(time.time() // seconds)}"
        return self._join_times.get(key, 0)

    def add_join(self, group_id):
        if not hasattr(self, '_join_times'):
            self._join_times = {}
        key = f"{group_id}_{int(time.time() // 10)}"  # بازه ۱۰ ثانیه
        self._join_times[key] = self._join_times.get(key, 0) + 1

db = Database()

# ========== ابزارهای کمکی ==========
def is_admin(user_id, chat_id):
    """بررسی اینکه کاربر ادمین گروه است یا خیر"""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ["administrator", "creator"]
    except:
        return False

def is_bot_admin(user_id):
    return user_id in ADMIN_IDS

def get_user_mention(user):
    return f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"

def format_duration(seconds):
    if seconds < 60:
        return f"{seconds} ثانیه"
    elif seconds < 3600:
        return f"{seconds // 60} دقیقه"
    elif seconds < 86400:
        return f"{seconds // 3600} ساعت"
    else:
        return f"{seconds // 86400} روز"

# ========== کیبوردهای زیبا ==========
def main_menu():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("⚙️ تنظیمات گروه", callback_data="settings"),
        InlineKeyboardButton("📊 آمار", callback_data="stats"),
        InlineKeyboardButton("📋 دستورات", callback_data="help"),
        InlineKeyboardButton("🔄 بروزرسانی", callback_data="refresh")
    )
    return keyboard

def settings_menu(group_id):
    settings = db.get_group(group_id)
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton(f"✅ خوش‌آمدگویی: {'فعال' if settings['welcome'] else 'غیرفعال'}", callback_data=f"toggle_welcome_{group_id}"),
        InlineKeyboardButton(f"🔐 کپچا: {'فعال' if settings['captcha'] else 'غیرفعال'}", callback_data=f"toggle_captcha_{group_id}"),
        InlineKeyboardButton(f"🛡️ ضد اسپم: {'فعال' if settings['anti_spam'] else 'غیرفعال'}", callback_data=f"toggle_antispam_{group_id}"),
        InlineKeyboardButton(f"🚫 ضد رید: {'فعال' if settings['anti_raid'] else 'غیرفعال'}", callback_data=f"toggle_antiraid_{group_id}"),
        InlineKeyboardButton(f"📢 ضد منشن: {'فعال' if settings['anti_mentions'] else 'غیرفعال'}", callback_data=f"toggle_antimentions_{group_id}"),
        InlineKeyboardButton(f"🔠 ضد کپس: {'فعال' if settings['anti_caps'] else 'غیرفعال'}", callback_data=f"toggle_anticaps_{group_id}"),
        InlineKeyboardButton(f"😊 ضد ایموجی: {'فعال' if settings['anti_emoji'] else 'غیرفعال'}", callback_data=f"toggle_antiemoji_{group_id}"),
        InlineKeyboardButton(f"📝 ضد خط جدید: {'فعال' if settings['anti_newlines'] else 'غیرفعال'}", callback_data=f"toggle_antinl_{group_id}"),
        InlineKeyboardButton(f"🗑️ حذف خودکار: {'فعال' if settings['auto_delete'] else 'غیرفعال'}", callback_data=f"toggle_autodelete_{group_id}"),
        InlineKeyboardButton("🔙 بازگشت", callback_data="back_main")
    )
    return keyboard

def back_button():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 بازگشت", callback_data="back_main"))
    return keyboard

# ========== دستورات ==========
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    name = message.from_user.first_name
    text = f"""
✨ **ربات محافظ گروه Luffy Ultra** ✨
━━━━━━━━━━━━━━━━━━━━━━
👤 **کاربر:** {name}
🆔 **آیدی:** `{user_id}`
👑 **نقش:** {'👑 ادمین' if is_bot_admin(user_id) else '👤 کاربر'}
━━━━━━━━━━━━━━━━━━━━━━

🛡️ **قابلیت‌ها:**
• ضد اسپم و رید
• کپچا برای ورود
• مدیریت اخطارها
• پاک‌سازی خودکار
• گزارش‌گیری کامل

📌 برای مدیریت گروه، بات را به گروه اضافه کنید و ادمین کنید.
"""
    bot.send_message(message.chat.id, text, reply_markup=main_menu(), parse_mode='HTML')

@bot.message_handler(commands=['settings'])
def settings_command(message):
    if not message.chat.type in ['group', 'supergroup']:
        bot.reply_to(message, "❌ این دستور فقط در گروه قابل استفاده است.")
        return
    group_id = message.chat.id
    if not is_admin(message.from_user.id, group_id) and not is_bot_admin(message.from_user.id):
        bot.reply_to(message, "⛔ شما ادمین گروه نیستید!")
        return
    bot.reply_to(message, "⚙️ **تنظیمات گروه:**", reply_markup=settings_menu(group_id), parse_mode='HTML')

@bot.message_handler(commands=['stats'])
def stats_command(message):
    if not message.chat.type in ['group', 'supergroup']:
        bot.reply_to(message, "❌ این دستور فقط در گروه قابل استفاده است.")
        return
    group_id = message.chat.id
    if not is_admin(message.from_user.id, group_id) and not is_bot_admin(message.from_user.id):
        bot.reply_to(message, "⛔ شما ادمین گروه نیستید!")
        return
    members = bot.get_chat_members_count(group_id)
    text = f"""
📊 **آمار گروه**
━━━━━━━━━━━━━━━━━━━━━━
👥 **تعداد اعضا:** {members}
📨 **پیام‌های کل:** {db.stats['total_messages']}
🚫 **اخراجی‌ها:** {db.stats['total_kicks']}
🔨 **بن‌ها:** {db.stats['total_bans']}
🔇 **میوت‌ها:** {db.stats['total_mutes']}
⚠️ **اخطارها:** {db.stats['total_warns']}
🔐 **کپچا موفق:** {db.stats['total_captcha_passed']}
❌ **کپچا ناموفق:** {db.stats['total_captcha_failed']}
━━━━━━━━━━━━━━━━━━━━━━
"""
    bot.reply_to(message, text, parse_mode='HTML')

@bot.message_handler(commands=['ban', 'unban', 'kick', 'mute', 'unmute', 'warn', 'warnings', 'resetwarnings', 'purge', 'pin', 'unpin'])
def admin_commands(message):
    if not message.chat.type in ['group', 'supergroup']:
        bot.reply_to(message, "❌ این دستور فقط در گروه قابل استفاده است.")
        return
    user_id = message.from_user.id
    group_id = message.chat.id
    if not is_admin(user_id, group_id) and not is_bot_admin(user_id):
        bot.reply_to(message, "⛔ شما ادمین گروه نیستید!")
        return

    command = message.text.split()[0].lower()
    args = message.text.split()[1:]

    if command == '/ban':
        if not args:
            bot.reply_to(message, "⚠️ `/ban [کاربر]` - کاربر را بن کنید.")
            return
        target = args[0]
        try:
            target_id = int(target) if target.isdigit() else None
            if not target_id:
                # تلاش برای یافتن با منشن یا ریپلای
                if message.reply_to_message:
                    target_id = message.reply_to_message.from_user.id
                else:
                    bot.reply_to(message, "❌ کاربر را مشخص کنید (آیدی یا ریپلای)")
                    return
            bot.ban_chat_member(group_id, target_id)
            db.stats['total_bans'] += 1
            bot.reply_to(message, f"✅ کاربر {target_id} بن شد.")
        except Exception as e:
            bot.reply_to(message, f"❌ خطا: {e}")

    elif command == '/unban':
        if not args:
            bot.reply_to(message, "⚠️ `/unban [کاربر]` - کاربر را آن‌بن کنید.")
            return
        target = args[0]
        try:
            target_id = int(target) if target.isdigit() else None
            if not target_id and message.reply_to_message:
                target_id = message.reply_to_message.from_user.id
            if not target_id:
                bot.reply_to(message, "❌ کاربر را مشخص کنید.")
                return
            bot.unban_chat_member(group_id, target_id)
            bot.reply_to(message, f"✅ کاربر {target_id} آن‌بن شد.")
        except Exception as e:
            bot.reply_to(message, f"❌ خطا: {e}")

    elif command == '/kick':
        if not args:
            bot.reply_to(message, "⚠️ `/kick [کاربر]` - کاربر را اخراج کنید.")
            return
        target = args[0]
        try:
            target_id = int(target) if target.isdigit() else None
            if not target_id and message.reply_to_message:
                target_id = message.reply_to_message.from_user.id
            if not target_id:
                bot.reply_to(message, "❌ کاربر را مشخص کنید.")
                return
            bot.ban_chat_member(group_id, target_id)
            bot.unban_chat_member(group_id, target_id)  # برای اخراج
            db.stats['total_kicks'] += 1
            bot.reply_to(message, f"✅ کاربر {target_id} اخراج شد.")
        except Exception as e:
            bot.reply_to(message, f"❌ خطا: {e}")

    elif command == '/mute':
        if not args:
            bot.reply_to(message, "⚠️ `/mute [کاربر] [مدت به ثانیه]` - کاربر را میوت کنید.")
            return
        target = args[0]
        duration = int(args[1]) if len(args) > 1 else 300
        try:
            target_id = int(target) if target.isdigit() else None
            if not target_id and message.reply_to_message:
                target_id = message.reply_to_message.from_user.id
            if not target_id:
                bot.reply_to(message, "❌ کاربر را مشخص کنید.")
                return
            db.set_mute(target_id, duration)
            db.stats['total_mutes'] += 1
            bot.reply_to(message, f"✅ کاربر {target_id} به مدت {format_duration(duration)} میوت شد.")
        except Exception as e:
            bot.reply_to(message, f"❌ خطا: {e}")

    elif command == '/unmute':
        if not args:
            bot.reply_to(message, "⚠️ `/unmute [کاربر]` - میوت کاربر را بردارید.")
            return
        target = args[0]
        try:
            target_id = int(target) if target.isdigit() else None
            if not target_id and message.reply_to_message:
                target_id = message.reply_to_message.from_user.id
            if not target_id:
                bot.reply_to(message, "❌ کاربر را مشخص کنید.")
                return
            db.remove_mute(target_id)
            bot.reply_to(message, f"✅ میوت کاربر {target_id} برداشته شد.")
        except Exception as e:
            bot.reply_to(message, f"❌ خطا: {e}")

    elif command == '/warn':
        if not args:
            bot.reply_to(message, "⚠️ `/warn [کاربر] [دلیل]` - به کاربر اخطار دهید.")
            return
        target = args[0]
        reason = " ".join(args[1:]) or "تخلف"
        try:
            target_id = int(target) if target.isdigit() else None
            if not target_id and message.reply_to_message:
                target_id = message.reply_to_message.from_user.id
            if not target_id:
                bot.reply_to(message, "❌ کاربر را مشخص کنید.")
                return
            count = db.add_warning(group_id, target_id, reason)
            settings = db.get_group(group_id)
            if count >= settings['warn_limit']:
                # اقدام بر اساس تنظیمات
                action = settings['warn_action']
                if action == "mute":
                    db.set_mute(target_id, settings['warn_duration'])
                    db.stats['total_mutes'] += 1
                    bot.reply_to(message, f"⚠️ کاربر {target_id} به دلیل {settings['warn_limit']} اخطار، میوت شد.")
                elif action == "kick":
                    bot.ban_chat_member(group_id, target_id)
                    bot.unban_chat_member(group_id, target_id)
                    db.stats['total_kicks'] += 1
                    bot.reply_to(message, f"⚠️ کاربر {target_id} به دلیل {settings['warn_limit']} اخطار، اخراج شد.")
                elif action == "ban":
                    bot.ban_chat_member(group_id, target_id)
                    db.stats['total_bans'] += 1
                    bot.reply_to(message, f"⚠️ کاربر {target_id} به دلیل {settings['warn_limit']} اخطار، بن شد.")
                db.clear_warnings(group_id, target_id)
            else:
                bot.reply_to(message, f"⚠️ کاربر {target_id} اخطار {count}/{settings['warn_limit']} دریافت کرد.")
        except Exception as e:
            bot.reply_to(message, f"❌ خطا: {e}")

    elif command == '/warnings':
        if not args:
            bot.reply_to(message, "⚠️ `/warnings [کاربر]` - نمایش اخطارهای کاربر.")
            return
        target = args[0]
        try:
            target_id = int(target) if target.isdigit() else None
            if not target_id and message.reply_to_message:
                target_id = message.reply_to_message.from_user.id
            if not target_id:
                bot.reply_to(message, "❌ کاربر را مشخص کنید.")
                return
            user = db.get_user(target_id)
            warns = user["warnings"].get(group_id, [])
            if warns:
                text = f"⚠️ **اخطارهای کاربر {target_id}:**\n"
                for i, w in enumerate(warns, 1):
                    text += f"{i}. {w['reason']} (زمان: {w['time']})\n"
                bot.reply_to(message, text, parse_mode='HTML')
            else:
                bot.reply_to(message, f"✅ کاربر {target_id} هیچ اخطاری ندارد.")
        except Exception as e:
            bot.reply_to(message, f"❌ خطا: {e}")

    elif command == '/resetwarnings':
        if not args:
            bot.reply_to(message, "⚠️ `/resetwarnings [کاربر]` - بازنشانی اخطارهای کاربر.")
            return
        target = args[0]
        try:
            target_id = int(target) if target.isdigit() else None
            if not target_id and message.reply_to_message:
                target_id = message.reply_to_message.from_user.id
            if not target_id:
                bot.reply_to(message, "❌ کاربر را مشخص کنید.")
                return
            if db.clear_warnings(group_id, target_id):
                bot.reply_to(message, f"✅ اخطارهای کاربر {target_id} بازنشانی شد.")
            else:
                bot.reply_to(message, f"❌ کاربر {target_id} اخطاری ندارد.")
        except Exception as e:
            bot.reply_to(message, f"❌ خطا: {e}")

    elif command == '/purge':
        # پاک‌سازی پیام‌ها (تا ۱۰۰ عدد)
        if not message.reply_to_message:
            bot.reply_to(message, "⚠️ برای پاک‌سازی، به یک پیام ریپلای کنید تا از آن به بعد حذف شود.")
            return
        try:
            msg_id = message.reply_to_message.message_id
            count = 0
            while msg_id < message.message_id and count < 100:
                bot.delete_message(group_id, msg_id)
                msg_id += 1
                count += 1
            bot.reply_to(message, f"✅ {count} پیام حذف شد.")
        except Exception as e:
            bot.reply_to(message, f"❌ خطا: {e}")

    elif command == '/pin':
        if not message.reply_to_message:
            bot.reply_to(message, "⚠️ به پیامی که می‌خواهید پین کنید ریپلای کنید.")
            return
        try:
            bot.pin_chat_message(group_id, message.reply_to_message.message_id)
            bot.reply_to(message, "📌 پیام پین شد.")
        except Exception as e:
            bot.reply_to(message, f"❌ خطا: {e}")

    elif command == '/unpin':
        try:
            bot.unpin_chat_message(group_id)
            bot.reply_to(message, "📌 پین برداشته شد.")
        except Exception as e:
            bot.reply_to(message, f"❌ خطا: {e}")

# ========== مدیریت اعضای جدید ==========
@bot.chat_member_handler()
def handle_new_member(chat_member_update):
    chat = chat_member_update.chat
    if chat.type not in ['group', 'supergroup']:
        return
    group_id = chat.id
    new_member = chat_member_update.new_chat_member
    if new_member.status == "member" and chat_member_update.old_chat_member.status in ["left", "kicked"]:
        # کاربر جدید وارد شده
        user = new_member.user
        user_id = user.id
        db.add_join(group_id)
        settings = db.get_group(group_id)

        # ضد رید
        if settings['anti_raid']:
            raid_count = db.get_raid_count(group_id, 10)
            if raid_count >= settings['raid_threshold']:
                action = settings['raid_action']
                try:
                    if action == "kick":
                        bot.ban_chat_member(group_id, user_id)
                        bot.unban_chat_member(group_id, user_id)
                        db.stats['total_kicks'] += 1
                    elif action == "ban":
                        bot.ban_chat_member(group_id, user_id)
                        db.stats['total_bans'] += 1
                    # لاگ
                except:
                    pass

        # کپچا
        if settings['captcha']:
            # تولید یک عدد تصادفی برای کپچا
            num1 = random.randint(1, 10)
            num2 = random.randint(1, 10)
            answer = num1 + num2
            db.captcha_data[user_id] = {"answer": answer, "time": time.time(), "group": group_id}
            bot.send_message(
                group_id,
                f"🔐 {get_user_mention(user)}، لطفاً برای اثبات اینکه ربات نیستی، پاسخ این معادله را بفرست:\n{num1} + {num2} = ?",
                parse_mode='HTML'
            )
            # بعد از timeout اگر پاسخ ندهد، اخراج
            def captcha_timeout():
                if user_id in db.captcha_data and db.captcha_data[user_id]["group"] == group_id:
                    try:
                        bot.ban_chat_member(group_id, user_id)
                        bot.unban_chat_member(group_id, user_id)
                        db.stats['total_captcha_failed'] += 1
                    except:
                        pass
                    del db.captcha_data[user_id]
            threading.Timer(settings['captcha_timeout'], captcha_timeout).start()

        # پیام خوش‌آمدگویی
        if settings['welcome']:
            welcome_text = settings['welcome'].replace("{user_name}", user.first_name)
            bot.send_message(group_id, welcome_text, parse_mode='HTML')

# ========== مدیریت پیام‌ها ==========
@bot.message_handler(func=lambda message: True, content_types=['text', 'photo', 'video', 'document', 'audio', 'voice', 'sticker'])
def handle_message(message):
    if not message.chat.type in ['group', 'supergroup']:
        return
    group_id = message.chat.id
    user = message.from_user
    user_id = user.id

    # نادیده گرفتن پیام‌های ادمین‌ها و خود بات
    if is_admin(user_id, group_id) or user.is_bot:
        return

    settings = db.get_group(group_id)

    # بررسی میوت
    if db.is_muted(user_id):
        bot.delete_message(group_id, message.message_id)
        bot.send_message(group_id, f"🔇 {get_user_mention(user)} شما میوت هستید!", parse_mode='HTML')
        return

    # ضد اسپم
    if settings['anti_spam']:
        db.add_message(user_id)
        count = db.get_message_count(user_id, 1)  # تعداد پیام در ۱ ثانیه
        if count >= settings['spam_threshold']:
            action = settings['spam_action']
            if action == "mute":
                db.set_mute(user_id, settings['spam_duration'])
                db.stats['total_mutes'] += 1
                bot.delete_message(group_id, message.message_id)
                bot.send_message(group_id, f"🔇 {get_user_mention(user)} به دلیل اسپم به مدت {format_duration(settings['spam_duration'])} میوت شد.", parse_mode='HTML')
            elif action == "kick":
                bot.ban_chat_member(group_id, user_id)
                bot.unban_chat_member(group_id, user_id)
                db.stats['total_kicks'] += 1
                bot.delete_message(group_id, message.message_id)
                bot.send_message(group_id, f"👢 {get_user_mention(user)} به دلیل اسپم اخراج شد.", parse_mode='HTML')
            elif action == "ban":
                bot.ban_chat_member(group_id, user_id)
                db.stats['total_bans'] += 1
                bot.delete_message(group_id, message.message_id)
                bot.send_message(group_id, f"🔨 {get_user_mention(user)} به دلیل اسپم بن شد.", parse_mode='HTML')
            return

    # ضد منشن
    if settings['anti_mentions'] and message.text:
        mentions = len(re.findall(r'@\w+', message.text)) + len(re.findall(r'<a href="tg://user', message.text))
        if mentions > settings['mention_limit']:
            bot.delete_message(group_id, message.message_id)
            db.add_warning(group_id, user_id, f"منشن بیش از حد ({mentions} بار)")
            bot.send_message(group_id, f"⚠️ {get_user_mention(user)} لطفاً منشن‌های زیاد نزنید!", parse_mode='HTML')

    # ضد کپس
    if settings['anti_caps'] and message.text:
        text = message.text
        letters = sum(c.isalpha() for c in text)
        if letters > 0:
            upper = sum(c.isupper() for c in text)
            ratio = (upper / letters) * 100
            if ratio > settings['caps_limit']:
                bot.delete_message(group_id, message.message_id)
                db.add_warning(group_id, user_id, f"کپس بیش از حد ({ratio:.0f}%)")
                bot.send_message(group_id, f"⚠️ {get_user_mention(user)} لطفاً با حروف بزرگ پیام ندهید!", parse_mode='HTML')

    # ضد ایموجی
    if settings['anti_emoji'] and message.text:
        emoji_count = len(re.findall(r'[^\w\s]', message.text))
        if emoji_count > settings['emoji_limit']:
            bot.delete_message(group_id, message.message_id)
            db.add_warning(group_id, user_id, f"ایموجی بیش از حد ({emoji_count} بار)")
            bot.send_message(group_id, f"⚠️ {get_user_mention(user)} لطفاً از ایموجی زیاد استفاده نکنید!", parse_mode='HTML')

    # ضد خط جدید
    if settings['anti_newlines'] and message.text:
        newlines = message.text.count('\n')
        if newlines > settings['newline_limit']:
            bot.delete_message(group_id, message.message_id)
            db.add_warning(group_id, user_id, f"خط جدید بیش از حد ({newlines} بار)")
            bot.send_message(group_id, f"⚠️ {get_user_mention(user)} لطفاً از خطوط جدید زیاد استفاده نکنید!", parse_mode='HTML')

    # حذف خودکار
    if settings['auto_delete']:
        def delete_later():
            try:
                bot.delete_message(group_id, message.message_id)
            except:
                pass
        threading.Timer(settings['auto_delete_seconds'], delete_later).start()

    # آمار
    db.stats['total_messages'] += 1

# ========== پاسخ به کپچا ==========
@bot.message_handler(func=lambda message: message.chat.type in ['group', 'supergroup'] and message.text and message.text.isdigit())
def captcha_answer(message):
    user_id = message.from_user.id
    if user_id in db.captcha_data:
        data = db.captcha_data[user_id]
        if int(message.text) == data["answer"]:
            del db.captcha_data[user_id]
            db.stats['total_captcha_passed'] += 1
            bot.reply_to(message, "✅ کپچا صحیح بود! خوش آمدید.")
        else:
            bot.reply_to(message, "❌ پاسخ نادرست! دوباره امتحان کنید.")
            # در صورت اشتباه، می‌توانیم اخراج کنیم یا دوباره سوال بپرسیم

# ========== مدیریت کال‌بک‌ها ==========
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    data = call.data

    if data == "back_main":
        bot.edit_message_text(
            "✨ **منوی اصلی**",
            chat_id,
            call.message.message_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)

    elif data == "settings":
        if not call.message.chat.type in ['group', 'supergroup']:
            bot.answer_callback_query(call.id, "❌ این بخش فقط در گروه قابل استفاده است.")
            return
        group_id = call.message.chat.id
        if not is_admin(user_id, group_id) and not is_bot_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ شما ادمین گروه نیستید!")
            return
        bot.edit_message_text(
            "⚙️ **تنظیمات گروه:**",
            chat_id,
            call.message.message_id,
            reply_markup=settings_menu(group_id),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)

    elif data == "stats":
        stats_command(call.message)
        bot.answer_callback_query(call.id)

    elif data == "help":
        text = """
📋 **دستورات ربات محافظ**
━━━━━━━━━━━━━━━━━━━━━━
**دستورات عمومی:**
/start - منوی اصلی
/help - این راهنما

**دستورات مدیریت گروه (فقط ادمین‌ها):**
/settings - تنظیمات گروه
/stats - آمار گروه
/ban [کاربر] - بن
/unban [کاربر] - آن‌بن
/kick [کاربر] - اخراج
/mute [کاربر] [مدت] - میوت
/unmute [کاربر] - رفع میوت
/warn [کاربر] [دلیل] - اخطار
/warnings [کاربر] - نمایش اخطارها
/resetwarnings [کاربر] - بازنشانی اخطارها
/purge (ریپلای به پیام) - پاک‌سازی
/pin (ریپلای) - پین
/unpin - برداشتن پین
━━━━━━━━━━━━━━━━━━━━━━
"""
        bot.edit_message_text(
            text,
            chat_id,
            call.message.message_id,
            reply_markup=back_button(),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)

    elif data == "refresh":
        bot.edit_message_text(
            "🔄 بروزرسانی شد.",
            chat_id,
            call.message.message_id,
            reply_markup=main_menu(),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id)

    elif data.startswith("toggle_"):
        parts = data.split("_")
        if len(parts) < 3:
            return
        toggle = parts[1]
        group_id = int(parts[2]) if parts[2].isdigit() else None
        if not group_id or group_id != chat_id:
            bot.answer_callback_query(call.id, "❌ گروه نادرست.")
            return
        if not is_admin(user_id, group_id) and not is_bot_admin(user_id):
            bot.answer_callback_query(call.id, "⛔ شما ادمین گروه نیستید!")
            return

        settings = db.get_group(group_id)
        if toggle == "welcome":
            settings['welcome'] = not settings['welcome']
        elif toggle == "captcha":
            settings['captcha'] = not settings['captcha']
        elif toggle == "antispam":
            settings['anti_spam'] = not settings['anti_spam']
        elif toggle == "antiraid":
            settings['anti_raid'] = not settings['anti_raid']
        elif toggle == "antimentions":
            settings['anti_mentions'] = not settings['anti_mentions']
        elif toggle == "anticaps":
            settings['anti_caps'] = not settings['anti_caps']
        elif toggle == "antiemoji":
            settings['anti_emoji'] = not settings['anti_emoji']
        elif toggle == "antinl":
            settings['anti_newlines'] = not settings['anti_newlines']
        elif toggle == "autodelete":
            settings['auto_delete'] = not settings['auto_delete']
        else:
            bot.answer_callback_query(call.id, "❌ تنظیم نامعتبر.")
            return

        bot.edit_message_text(
            "⚙️ **تنظیمات گروه:**",
            chat_id,
            call.message.message_id,
            reply_markup=settings_menu(group_id),
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id, "✅ تنظیمات ذخیره شد.")

# ========== مدیریت پیام‌های دیگر ==========
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    # پاسخ به پیام‌های متنی ساده برای راهنمایی
    if message.text and message.text.lower() in ["سلام", "درود", "hi", "hello"]:
        bot.reply_to(message, f"✨ سلام {message.from_user.first_name} جان! به ربات محافظ خوش آمدی! 🛡️")

# ========== اجرا ==========
if __name__ == "__main__":
    print("=" * 70)
    print("✨ ربات محافظ گروه Luffy Ultra نسخه 5.0.0 ✨")
    print("=" * 70)
    print(f"👥 ادمین‌ها: {ADMIN_IDS}")
    print("✅ برای شروع، بات را به گروه اضافه کنید و /start بزنید.")
    print("=" * 70)

    while True:
        try:
            bot.polling(none_stop=True, interval=0, timeout=60)
        except Exception as e:
            print(f"❌ خطا: {e}")
            print("🔄 راه‌اندازی مجدد در 5 ثانیه...")
            time.sleep(5)
            continue