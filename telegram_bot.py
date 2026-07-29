import os
import re
import asyncio
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Conflict
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from database import get_db_context
from models import User, UserSettings, CourseContent, CalendarEvent, NotificationLog
from crypto import encrypt_credential, decrypt_credential, mask_secret
from services.user_service import delete_user_by_telegram_id
from scraper import create_session
from groq_helper import chat_with_context, validate_groq_key
from calendar_api import parse_events, find_new_events, build_events_message

load_dotenv()

REG_USERNAME, REG_PASSWORD = range(2)
SET_GROQ_KEY_STATE = 1

bot_app: Application = None


def is_admin(chat_id: int) -> bool:
    admin_id = os.getenv("ADMIN_CHAT_ID")
    if not admin_id:
        return True  # If no ADMIN_CHAT_ID set, grant for dev/testing
    return str(chat_id) == str(admin_id)


async def safe_delete_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int):
    """Safely delete a message from chat history."""
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as e:
        print(f"⚠️ Could not delete message {message_id}: {e}")


def get_user_by_chat_id(chat_id: int) -> User | None:
    with get_db_context() as db:
        return db.query(User).filter(User.telegram_chat_id == chat_id).first()


def get_user_content(user_id: int) -> dict:
    with get_db_context() as db:
        rec = db.query(CourseContent).filter(CourseContent.user_id == user_id).first()
        return rec.content_json if rec and rec.content_json else {}


def get_user_events(user_id: int) -> list:
    with get_db_context() as db:
        rec = db.query(CalendarEvent).filter(CalendarEvent.user_id == user_id).first()
        return rec.events_json if rec and rec.events_json else []


def get_or_create_user_settings(user_id: int) -> UserSettings:
    with get_db_context() as db:
        st = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not st:
            st = UserSettings(user_id=user_id)
            db.add(st)
            db.flush()
        return st


# ══════════════════════════════════════════════════════════════
# Inline Keyboards
# ══════════════════════════════════════════════════════════════

def build_settings_keyboard(settings: UserSettings) -> InlineKeyboardMarkup:
    f_icon = "✅" if settings.notify_files else "❌"
    a_icon = "✅" if settings.notify_assignments else "❌"
    q_icon = "✅" if settings.notify_quizzes else "❌"
    d_icon = "✅" if settings.notify_folders else "❌"
    ai_icon = "✅" if settings.ai_summaries_enabled else "❌"
    mode_text = "فوري ⚡" if settings.digest_mode == "instant" else "ملخص يومي 📅"
    lang = getattr(settings, "language", "ar")
    lang_text = "العربية 🇵🇸" if lang == "ar" else "English 🇬🇧"

    keyboard = [
        [
            InlineKeyboardButton(f"📄 الملفات {f_icon}", callback_data="cfg_toggle:notify_files"),
            InlineKeyboardButton(f"📝 الواجبات {a_icon}", callback_data="cfg_toggle:notify_assignments"),
        ],
        [
            InlineKeyboardButton(f"❓ الكويزات {q_icon}", callback_data="cfg_toggle:notify_quizzes"),
            InlineKeyboardButton(f"📁 المجلدات {d_icon}", callback_data="cfg_toggle:notify_folders"),
        ],
        [
            InlineKeyboardButton(f"🤖 ملخصات AI {ai_icon}", callback_data="cfg_toggle:ai_summaries_enabled"),
        ],
        [
            InlineKeyboardButton(f"📩 الإشعارات: {mode_text}", callback_data="cfg_mode:digest_mode"),
            InlineKeyboardButton(f"🌐 اللغة: {lang_text}", callback_data="cfg_lang:language"),
        ],
        [
            InlineKeyboardButton("🔇 تصفية وكتم المساقات", callback_data="cfg_courses:menu"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_coursefilter_keyboard(courses: list, muted_courses: list) -> InlineKeyboardMarkup:
    keyboard = []
    for idx, course_name in enumerate(courses):
        is_muted = course_name in muted_courses
        icon = "🔇 مكتوم" if is_muted else "✅ مُفعل"
        short_name = course_name[:25] + "..." if len(course_name) > 28 else course_name
        keyboard.append([
            InlineKeyboardButton(f"{icon} | {short_name}", callback_data=f"mute_toggle:{idx}")
        ])
    keyboard.append([InlineKeyboardButton("🔙 العودة للإعدادات", callback_data="cfg_back:settings")])
    return InlineKeyboardMarkup(keyboard)


# ══════════════════════════════════════════════════════════════
# User Commands
# ══════════════════════════════════════════════════════════════

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user_by_chat_id(chat_id)

    if not user or user.status == "unregistered":
        msg = (
            "🤖 <b>مرحباً بك في بوت مراقبة Moodle (جامعة غزة الإسلامية)!</b>\n\n"
            "لم يتم تسجيل حسابك بعد.\n"
            "اضغط على /register للبدء وتسجيل حساب Moodle الخاص بك مجاناً 🚀"
        )
    else:
        msg = (
            f"👋 <b>أهلاً بك مجدداً ({user.moodle_username or 'طالب'})!</b>\n\n"
            "📚 <b>أوامر المحتوى والمساقات:</b>\n"
            "/courses — جميع مساقاتك مع الروابط\n"
            "/summary — ملخص عددي للمحتوى\n"
            "/files — ملفاتك المحفوظة\n"
            "/assignments — الواجبات المسجلة\n"
            "/quizzes — الكويزات المسجلة\n"
            "/search كلمة — بحث شامل في مساقاتك\n\n"
            "📅 <b>المواعيد والتقويم:</b>\n"
            "/updates — جميع المواعيد القادمة\n"
            "/deadlines — أقرب المواعيد\n\n"
            "⚙️ <b>الإعدادات والتحكم:</b>\n"
            "/settings — لوحة التفضيلات والإشعارات تفاعلية 🎛\n"
            "/coursefilter — كتم إشعارات مساق محدد 🔇\n"
            "/setgroqkey — إضافة مفتاح Groq الخاص بك 🔑\n"
            "/status — حالة المراقبة والخيارات\n"
            "/pause | /resume — إيقاف/استئناف المراقبة\n"
            "/logout | /delete_account — خروج / حذف الحساب"
        )
    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start_command(update, context)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user_by_chat_id(chat_id)

    if not user or user.status != "active":
        await update.message.reply_text("❌ يرجى تسجيل حسابك عبر /register أولاً.", parse_mode="HTML")
        return

    settings = get_or_create_user_settings(user.id)
    reply_markup = build_settings_keyboard(settings)

    await update.message.reply_text(
        "⚙️ <b>لوحة تفضيلات الإشعارات والذكاء الاصطناعي</b>\n\n"
        "انقر على الأزرار أدناه للتعديل المباشر:",
        parse_mode="HTML",
        reply_markup=reply_markup
    )


async def coursefilter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user_by_chat_id(chat_id)

    if not user or user.status != "active":
        await update.message.reply_text("❌ يرجى تسجيل حسابك عبر /register أولاً.", parse_mode="HTML")
        return

    settings = get_or_create_user_settings(user.id)
    content = get_user_content(user.id)
    courses = list(content.keys())

    if not courses:
        await update.message.reply_text("❌ لا توجد مساقات مسجلة بعد تصفيتها.", parse_mode="HTML")
        return

    muted = settings.muted_courses or []
    reply_markup = build_coursefilter_keyboard(courses, muted)

    await update.message.reply_text(
        "🔇 <b>تصفية وكتم إشعارات المساقات</b>\n\n"
        "انقر على اسم المساق لكتم إشعاراته الدورية (ستظل بياناته متاحة عبر /courses):",
        parse_mode="HTML",
        reply_markup=reply_markup
    )


async def settings_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = update.effective_chat.id
    user = get_user_by_chat_id(chat_id)

    if not user:
        return

    with get_db_context() as db:
        settings = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
        if not settings:
            settings = UserSettings(user_id=user.id)
            db.add(settings)
            db.flush()

        if data.startswith("cfg_toggle:"):
            attr = data.split(":")[1]
            if hasattr(settings, attr):
                current_val = getattr(settings, attr)
                setattr(settings, attr, not current_val)
                db.flush()
            reply_markup = build_settings_keyboard(settings)
            await query.edit_message_reply_markup(reply_markup=reply_markup)

        elif data.startswith("cfg_mode:"):
            settings.digest_mode = "daily" if settings.digest_mode == "instant" else "instant"
            db.flush()
            reply_markup = build_settings_keyboard(settings)
            await query.edit_message_reply_markup(reply_markup=reply_markup)

        elif data.startswith("cfg_lang:"):
            if hasattr(settings, "language"):
                settings.language = "en" if settings.language == "ar" else "ar"
                db.flush()
            reply_markup = build_settings_keyboard(settings)
            await query.edit_message_reply_markup(reply_markup=reply_markup)

        elif data == "cfg_courses:menu":
            user_content = get_user_content(user.id)
            courses = list(user_content.keys())
            if not courses:
                await query.edit_message_text("❌ لا توجد مساقات مسجلة بعد لتصفيتها.", parse_mode="HTML")
                return
            muted = settings.muted_courses or []
            reply_markup = build_coursefilter_keyboard(courses, muted)
            await query.edit_message_text(
                "🔇 <b>تصفية وكتم إشعارات المساقات</b>\n\nانقر لكتم أو تفعيل إشعارات المساق:",
                parse_mode="HTML",
                reply_markup=reply_markup
            )

        elif data.startswith("mute_toggle:"):
            idx = int(data.split(":")[1])
            user_content = get_user_content(user.id)
            courses = list(user_content.keys())
            if 0 <= idx < len(courses):
                c_name = courses[idx]
                muted = list(settings.muted_courses or [])
                if c_name in muted:
                    muted.remove(c_name)
                else:
                    muted.append(c_name)
                settings.muted_courses = muted
                db.flush()

                reply_markup = build_coursefilter_keyboard(courses, muted)
                await query.edit_message_reply_markup(reply_markup=reply_markup)

        elif data == "cfg_back:settings":
            reply_markup = build_settings_keyboard(settings)
            await query.edit_message_text(
                "⚙️ <b>لوحة تفضيلات الإشعارات والذكاء الاصطناعي</b>\n\nانقر على الأزرار أدناه للتعديل المباشر:",
                parse_mode="HTML",
                reply_markup=reply_markup
            )


# ══════════════════════════════════════════════════════════════
# Admin Commands
# ══════════════════════════════════════════════════════════════

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        await update.message.reply_text("❌ هذا الأمر مخصص لمدير النظام فقط.", parse_mode="HTML")
        return

    with get_db_context() as db:
        total_users = db.query(User).count()
        active_users = db.query(User).filter(User.status == "active").count()
        paused_users = db.query(User).filter(User.status == "paused").count()
        error_users = db.query(User).filter(User.status == "error").count()
        custom_key_users = db.query(User).filter(User.groq_api_key_encrypted.isnot(None)).count()

        since_24h = datetime.now() - timedelta(days=1)
        logs_24h = db.query(NotificationLog).filter(NotificationLog.sent_at >= since_24h).count()
        logs_total = db.query(NotificationLog).count()

    msg = (
        "👑 <b>لوحة تحكم مدير النظام (Admin Dashboard)</b>\n\n"
        f"📊 <b>إحصائيات المستخدمين:</b>\n"
        f"  • إجمالي المستخدمين: <b>{total_users}</b>\n"
        f"  • نَشِط (Active): <b>{active_users}</b> 🟢\n"
        f"  • متوقف (Paused): <b>{paused_users}</b> ⏸\n"
        f"  • خطأ (Error): <b>{error_users}</b> ⚠️\n"
        f"  • مفتاح Groq خاص: <b>{custom_key_users}</b> 🔑\n\n"
        f"📩 <b>إحصائيات الإشعارات:</b>\n"
        f"  • إشعارات آخر 24 ساعة: <b>{logs_24h}</b>\n"
        f"  • إجمالي الإشعارات المسجلة: <b>{logs_total}</b>\n\n"
        "🛠 <b>الأوامر المتاحة:</b>\n"
        "/admin_users — قائمة كاملة بالمستخدمين وحالاتهم\n"
        "/admin_broadcast نص الرسالة — إرسال إعلان لجميع الطلاب\n"
        "/admin_retry user_id — إعادة تفعيل حساب متعثر"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def admin_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        await update.message.reply_text("❌ هذا الأمر مخصص لمدير النظام فقط.", parse_mode="HTML")
        return

    with get_db_context() as db:
        users = db.query(User).all()

    if not users:
        await update.message.reply_text("ℹ️ لا يوجد مستخدمون في قاعدة البيانات.", parse_mode="HTML")
        return

    lines = ["👥 <b>قائمة جميع المستخدمين المسجلين:</b>\n"]
    for u in users:
        last_chk = u.last_check_at.strftime("%m-%d %H:%M") if u.last_check_at else "N/A"
        key_icon = "🔑" if u.groq_api_key_encrypted else "⚙️"
        lines.append(
            f"• <b>ID {u.id}</b> | @{u.telegram_username or 'N/A'} ({u.moodle_username})\n"
            f"   حالة: <code>{u.status}</code> | فحص: {last_chk} | {key_icon}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def admin_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        await update.message.reply_text("❌ هذا الأمر مخصص لمدير النظام فقط.", parse_mode="HTML")
        return

    text = update.message.text
    broadcast_msg = text[16:].strip() if len(text) > 16 else ""

    if not broadcast_msg:
        await update.message.reply_text("❌ استخدم: <code>/admin_broadcast نص الإعلان هنا</code>", parse_mode="HTML")
        return

    with get_db_context() as db:
        active_users = db.query(User).filter(User.status == "active").all()
        target_chat_ids = [u.telegram_chat_id for u in active_users if u.telegram_chat_id]

    status_msg = await update.message.reply_text(f"⏳ جاري إرسال الإعلان لـ {len(target_chat_ids)} مستخدم...", parse_mode="HTML")

    success_count = 0
    fail_count = 0
    formatted_msg = f"📢 <b>إعلان رسمي من إداري النظام:</b>\n\n{broadcast_msg}"

    for cid in target_chat_ids:
        try:
            send_message(formatted_msg, chat_id=cid)
            success_count += 1
            await asyncio.sleep(0.1)
        except Exception:
            fail_count += 1

    await status_msg.edit_text(
        f"✅ <b>اكتمل بث الإعلان!</b>\n\n"
        f"🟢 تم الإرسال بنجاح: <b>{success_count}</b>\n"
        f"🔴 فشل الإرسال: <b>{fail_count}</b>",
        parse_mode="HTML"
    )


async def admin_retry_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not is_admin(chat_id):
        await update.message.reply_text("❌ هذا الأمر مخصص لمدير النظام فقط.", parse_mode="HTML")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❌ استخدم: <code>/admin_retry user_id</code>", parse_mode="HTML")
        return

    try:
        target_user_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID غير صالح.", parse_mode="HTML")
        return

    with get_db_context() as db:
        u = db.query(User).filter(User.id == target_user_id).first()
        if not u:
            await update.message.reply_text("❌ لم يتم العثور على مستخدم بهذ الـ ID.", parse_mode="HTML")
            return

        u.status = "active"
        u.last_error = None

    await update.message.reply_text(f"✅ تم إعادة تفعيل الحساب لـ User ID {target_user_id} وتصفير الأخطاء.", parse_mode="HTML")


# ══════════════════════════════════════════════════════════════
# Registration Conversation Handler (/register)
# ══════════════════════════════════════════════════════════════

async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user_by_chat_id(chat_id)

    if user and user.status == "active":
        await update.message.reply_text(
            f"✅ حسابك مسجّل بالفعل لنفس الشات ({user.moodle_username}).\n"
            "استخدم /status لمعاينة بياناتك أو /logout لتسجيل الخروج.",
            parse_mode="HTML"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "📝 <b>خطوة 1 من 2: تسجيل حساب Moodle</b>\n\n"
        "من فضلك أرسل اسم المستخدم الخاص بك في Moodle (مثال: <code>20201234</code>):\n\n"
        "<i>يمكنك إرسال /cancel في أي وقت للإلغاء.</i>",
        parse_mode="HTML"
    )
    return REG_USERNAME


async def register_username_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()
    context.user_data["reg_username"] = username

    await update.message.reply_text(
        f"🔒 <b>خطوة 2 من 2: كلمة المرور لـ ({username})</b>\n\n"
        "أرسل الآن كلمة مرور Moodle الخاص بك.\n\n"
        "🛡 <b>ضمان الأمان:</b> سيتم حذف رسالتك المحتوية على كلمة المرور فوراً من الشات، وتُشفَّر كلمة المرور بتقنية Fernet قبل حفظها.",
        parse_mode="HTML"
    )
    return REG_PASSWORD


async def register_password_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg_id = update.message.message_id
    password = update.message.text.strip()
    username = context.user_data.get("reg_username")

    await safe_delete_message(context, chat_id, msg_id)

    status_msg = await update.message.reply_text(
        "⏳ <b>جاري التحقق من بيانات الدخول عبر Moodle...</b>\n<i>يرجى الانتظار بضع ثوانٍ.</i>",
        parse_mode="HTML"
    )

    try:
        session = await asyncio.to_thread(create_session, username, password)
        if not session:
            raise Exception("فشل الدخول")
    except Exception as e:
        await status_msg.edit_text(
            f"❌ <b>فشل تسجيل الدخول:</b> اسم المستخدم أو كلمة المرور غير صحيحة.\n\n"
            "أرسل /register للإعادة.",
            parse_mode="HTML"
        )
        return ConversationHandler.END

    enc_password = encrypt_credential(password)

    with get_db_context() as db:
        user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
        if not user:
            user = User(
                telegram_chat_id=chat_id,
                telegram_username=update.effective_user.username,
                moodle_username=username,
                moodle_password_encrypted=enc_password,
                status="active"
            )
            db.add(user)
            db.flush()
            settings = UserSettings(user_id=user.id)
            db.add(settings)
        else:
            user.moodle_username = username
            user.moodle_password_encrypted = enc_password
            user.status = "active"
            user.last_error = None

    await status_msg.edit_text(
        "🎉 <b>تم تسجيل حسابك بنجاح!</b>\n\n"
        "✅ تم التثبت من الحساب وتفعيل نظام المراقبة.\n"
        "💡 ننصحك بإضافة مفتاح Groq الخاص بك لتشغيل الذكاء الاصطناعي عبر الأمر /setgroqkey.\n\n"
        "أرسل /help لرؤية جميع الأوامر.",
        parse_mode="HTML"
    )
    return ConversationHandler.END


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ تم إلغاء العملية.", parse_mode="HTML")
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════════
# Set Groq Key Conversation Handler (/setgroqkey)
# ══════════════════════════════════════════════════════════════

async def setgroqkey_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user_by_chat_id(chat_id)

    if not user or user.status != "active":
        await update.message.reply_text("❌ يجب تسجيل حسابك أولاً عبر /register.", parse_mode="HTML")
        return ConversationHandler.END

    await update.message.reply_text(
        "🔑 <b>إعداد مفتاح Groq API الخاص بك (مجاني)</b>\n\n"
        "خطوات الحصول على المفتاح في دقيقتين:\n"
        "1️⃣ افتح الرابط: <a href='https://console.groq.com/keys'>console.groq.com/keys</a>\n"
        "2️⃣ سجّل دخولك واضغط <b>Create API Key</b> ثم انسخ المفتاح.\n\n"
        "أرسل المفتاح هنا الآن (يبدأ بـ <code>gsk_</code>):\n\n"
        "🛡 <i>سيتم حذف رسالتك فور استلامها وتشفير المفتاح at-rest.</i>\n"
        "<i>يمكنك إرسال /cancel للإلغاء.</i>",
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    return SET_GROQ_KEY_STATE


async def setgroqkey_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    msg_id = update.message.message_id
    raw_key = update.message.text.strip()

    await safe_delete_message(context, chat_id, msg_id)

    status_msg = await update.message.reply_text("⏳ <b>جاري فحص صلاحية مفتاح Groq...</b>", parse_mode="HTML")

    is_valid = await asyncio.to_thread(validate_groq_key, raw_key)
    if not is_valid:
        await status_msg.edit_text(
            "❌ <b>المفتاح غير صالح:</b> تعذر الاتصال بـ Groq API باستخدام هذا المفتاح.\n"
            "تأكد من نسخه بالكامل وأرسل /setgroqkey للتحاول مجدداً.",
            parse_mode="HTML"
        )
        return ConversationHandler.END

    enc_key = encrypt_credential(raw_key)
    with get_db_context() as db:
        user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
        if user:
            user.groq_api_key_encrypted = enc_key

    masked = mask_secret(raw_key)
    await status_msg.edit_text(
        f"✅ <b>تم تفعيل مفتاح Groq بنجاح!</b>\n\n"
        f"🔑 المفتاح المحفوظ: <code>{masked}</code>\n"
        "سيتم استخدام مفتاحك الخاص لجميع أسئلة /ai والملخصات التلقائية بدون حدود خادم مشتركة.",
        parse_mode="HTML"
    )
    return ConversationHandler.END


async def removegroqkey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    with get_db_context() as db:
        user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
        if user and user.groq_api_key_encrypted:
            user.groq_api_key_encrypted = None
            await update.message.reply_text("✅ تم إزالة مفتاح Groq الخاص بك والعودة إلى المفتاح المباشر.", parse_mode="HTML")
            return
    await update.message.reply_text("ℹ️ ليس لديك مفتاح Groq خاص محفوظ حالياً.", parse_mode="HTML")


# ══════════════════════════════════════════════════════════════
# Scoped Content Commands
# ══════════════════════════════════════════════════════════════

async def courses_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user_by_chat_id(chat_id)

    if not user or user.status != "active":
        await update.message.reply_text("❌ يرجى تسجيل حسابك عبر /register أولاً.", parse_mode="HTML")
        return

    data = get_user_content(user.id)
    if not data:
        await update.message.reply_text("❌ لا توجد بيانات مساق محفوظ حتى الآن — انتظر دورة المراقبة القادمة.", parse_mode="HTML")
        return

    lines = ["📚 <b>جميع المساقات المسجّلة:</b>\n"]
    total_all = 0
    for i, (course, c) in enumerate(data.items(), 1):
        files = c.get("files", [])
        assign = c.get("assignments", [])
        quizzes = c.get("quizzes", [])
        total = len(files) + len(assign) + len(quizzes)
        total_all += total
        course_url = ""
        for cat in [files, assign, quizzes]:
            if cat:
                match = re.search(r'\?id=(\d+)', cat[0]["url"])
                if match:
                    course_url = f"https://moodle.iugaza.edu.ps/course/view.php?id={match.group(1)}"
                break
        lines.append(
            f"{i}. <b>{course}</b>\n"
            f"   📄 {len(files)} ملف  |  📝 {len(assign)} واجب  |  ❓ {len(quizzes)} كويز\n"
            + (f"   🔗 <a href='{course_url}'>افتح المساق</a>\n" if course_url else "")
        )
    lines.append(f"\n📦 <b>الإجمالي: {total_all} عنصر</b>")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user_by_chat_id(chat_id)
    if not user or user.status != "active":
        await update.message.reply_text("❌ يرجى تسجيل حسابك عبر /register أولاً.", parse_mode="HTML")
        return

    data = get_user_content(user.id)
    if not data:
        await update.message.reply_text("❌ لا توجد بيانات مسجلة بعد.", parse_mode="HTML")
        return

    lines = [f"📊 <b>ملخص المحتوى الخاص بك</b> — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
    total_all = 0
    for course, c in data.items():
        t = sum(len(v) for v in c.values())
        total_all += t
        lines.append(
            f"📌 <b>{course}</b>\n"
            f"   📄 {len(c.get('files',[]))} ملف  |  "
            f"📝 {len(c.get('assignments',[]))} واجب  |  "
            f"❓ {len(c.get('quizzes',[]))} كويز\n"
        )
    lines.append(f"📦 الإجمالي: <b>{total_all}</b> عنصر")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def updates_or_deadlines_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cmd = update.message.text.split()[0]
    limit = 15 if "updates" in cmd else 10
    msg = get_deadlines_message(limit=limit)
    await update.message.reply_text(msg, parse_mode="HTML", disable_web_page_preview=True)


async def files_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user_by_chat_id(chat_id)
    if not user or user.status != "active":
        await update.message.reply_text("❌ يرجى تسجيل حسابك عبر /register أولاً.", parse_mode="HTML")
        return

    data = get_user_content(user.id)
    lines = ["📄 <b>ملفات مساقاتك المحفوظة:</b>\n"]
    for course, c in data.items():
        items = c.get("files", [])
        if items:
            lines.append(f"\n📚 <b>{course}</b>")
            for item in items:
                lines.append(f"• <a href='{item['url']}'>{item['name']}</a>")
    await update.message.reply_text("\n".join(lines) if len(lines) > 1 else "📂 لا توجد ملفات محددة.", parse_mode="HTML", disable_web_page_preview=True)


async def assignments_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user_by_chat_id(chat_id)
    if not user or user.status != "active":
        await update.message.reply_text("❌ يرجى تسجيل حسابك عبر /register أولاً.", parse_mode="HTML")
        return

    data = get_user_content(user.id)
    lines = ["📝 <b>جميع الواجبات المحفوظة:</b>\n"]
    for course, c in data.items():
        items = c.get("assignments", [])
        if items:
            lines.append(f"\n📚 <b>{course}</b>")
            for item in items:
                lines.append(f"• <a href='{item['url']}'>{item['name']}</a>")
    await update.message.reply_text("\n".join(lines) if len(lines) > 1 else "📝 لا توجد واجبات محفوظة.", parse_mode="HTML", disable_web_page_preview=True)


async def quizzes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user_by_chat_id(chat_id)
    if not user or user.status != "active":
        await update.message.reply_text("❌ يرجى تسجيل حسابك عبر /register أولاً.", parse_mode="HTML")
        return

    data = get_user_content(user.id)
    lines = ["❓ <b>جميع الكويزات المحفوظة:</b>\n"]
    for course, c in data.items():
        items = c.get("quizzes", [])
        if items:
            lines.append(f"\n📚 <b>{course}</b>")
            for item in items:
                lines.append(f"• <a href='{item['url']}'>{item['name']}</a>")
    await update.message.reply_text("\n".join(lines) if len(lines) > 1 else "❓ لا توجد كويزات محفوظة.", parse_mode="HTML", disable_web_page_preview=True)


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user_by_chat_id(chat_id)
    if not user or user.status != "active":
        await update.message.reply_text("❌ يرجى تسجيل حسابك عبر /register أولاً.", parse_mode="HTML")
        return

    text = update.message.text
    keyword = text[7:].strip().lower() if len(text) > 7 else ""
    if not keyword:
        await update.message.reply_text("❌ استخدم: /search كلمة_البحث", parse_mode="HTML")
        return

    data = get_user_content(user.id)
    results = []
    for course, c in data.items():
        for cat in ["files", "assignments", "quizzes"]:
            for item in c.get(cat, []):
                if keyword in item["name"].lower():
                    emoji = {"files": "📄", "assignments": "📝", "quizzes": "❓"}[cat]
                    results.append(f"{emoji} <a href='{item['url']}'>{item['name']}</a>\n   📚 {course}")

    if not results:
        await update.message.reply_text(f"🔍 لا توجد نتائج لـ: <b>{keyword}</b>", parse_mode="HTML")
    else:
        await update.message.reply_text(f"🔍 <b>نتائج \"{keyword}\":</b>\n\n" + "\n\n".join(results), parse_mode="HTML", disable_web_page_preview=True)


async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user_by_chat_id(chat_id)
    if not user or user.status != "active":
        await update.message.reply_text("❌ يرجى تسجيل حسابك عبر /register أولاً.", parse_mode="HTML")
        return

    text = update.message.text
    question = text[3:].strip() if len(text) > 3 else ""
    if not question:
        await update.message.reply_text(
            "🤖 <b>اسألني أي شيء عن مساقاتك!</b>\n\n"
            "أمثلة:\n"
            "/ai ما هي الكويزات القادمة؟\n"
            "/ai متى موعد تسليم الواجبات؟\n"
            "/ai رتّب أولوياتي للأسبوع القادم",
            parse_mode="HTML"
        )
        return

    data = get_user_content(user.id)
    events_list = get_user_events(user.id)
    events_dict = {str(i): e for i, e in enumerate(events_list)}

    status_msg = await update.message.reply_text("⏳ <b>جاري التفكير مع Groq AI...</b>", parse_mode="HTML")
    answer = await asyncio.to_thread(chat_with_context, question, data, events_dict)
    await status_msg.edit_text(f"🤖 <b>Groq AI:</b>\n\n{answer}", parse_mode="HTML")


# ══════════════════════════════════════════════════════════════
# Account Management Commands
# ══════════════════════════════════════════════════════════════

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user_by_chat_id(chat_id)

    if not user or user.status == "unregistered":
        await update.message.reply_text("❌ حسابك غير مسجل. أرسل /register للبدء.", parse_mode="HTML")
        return

    settings = get_or_create_user_settings(user.id)

    groq_status = "غير مُفاد ❌ (يمكنك إضافته عبر /setgroqkey)"
    if user.groq_api_key_encrypted:
        raw = decrypt_credential(user.groq_api_key_encrypted)
        groq_status = f"مُفعَّل ✅ (<code>{mask_secret(raw)}</code>)"

    last_chk = user.last_check_at.strftime("%Y-%m-%d %H:%M") if user.last_check_at else "لم يُفحص بعد"
    err = f"\n⚠️ <b>آخر خطأ:</b> {user.last_error}" if user.last_error else ""

    muted = settings.muted_courses or []
    muted_str = ", ".join(muted) if muted else "لا يوجد"

    msg = (
        f"📊 <b>حالة الحساب والمراقبة</b>\n\n"
        f"👤 <b>اسم المستخدم:</b> {user.moodle_username}\n"
        f"⚡ <b>حالة الحساب:</b> {user.status.upper()}\n"
        f"⏰ <b>آخر فحص:</b> {last_chk}\n"
        f"🔑 <b>مفتاح Groq:</b> {groq_status}\n\n"
        f"⚙️ <b>التفضيلات المفعلة:</b>\n"
        f"  • الملفات: {'✅' if settings.notify_files else '❌'}  |  الواجبات: {'✅' if settings.notify_assignments else '❌'}\n"
        f"  • الكويزات: {'✅' if settings.notify_quizzes else '❌'}  |  المجلدات: {'✅' if settings.notify_folders else '❌'}\n"
        f"  • ملخصات AI: {'✅' if settings.ai_summaries_enabled else '❌'}  |  الوضع: {settings.digest_mode.upper()}\n"
        f"  • المساقات المكتومة: <code>{muted_str}</code>"
        f"{err}"
    )
    await update.message.reply_text(msg, parse_mode="HTML")


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    with get_db_context() as db:
        user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
        if user and user.status == "active":
            user.status = "paused"
            await update.message.reply_text("⏸ <b>تم إيقاف المراقبة مؤقتاً.</b>\nأرسل /resume لإعادة تفعيلها.", parse_mode="HTML")
            return
    await update.message.reply_text("ℹ️ حسابك ليس نَشِطاً حالياً.", parse_mode="HTML")


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    with get_db_context() as db:
        user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
        if user and user.status in ["paused", "error"]:
            user.status = "active"
            user.last_error = None
            await update.message.reply_text("▶️ <b>تم استئناف المراقبة بنجاح!</b>", parse_mode="HTML")
            return
    await update.message.reply_text("ℹ️ حسابك نشط بالفعل.", parse_mode="HTML")


async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    with get_db_context() as db:
        user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
        if user:
            user.status = "unregistered"
            await update.message.reply_text("🚪 <b>تم تسجيل الخروج وتوقيف المراقبة.</b>\nأرسل /register للتسجيل مجدداً.", parse_mode="HTML")
            return
    await update.message.reply_text("ℹ️ ليس لديك حساب مسجل.", parse_mode="HTML")


async def delete_account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    deleted = delete_user_by_telegram_id(chat_id)
    if deleted:
        await update.message.reply_text("🗑 <b>تم حذف جميع بياناتك وحسابك نهائياً من قاعدة البيانات.</b>", parse_mode="HTML")
    else:
        await update.message.reply_text("ℹ️ لم يُعثر على حساب مسجل لحذفه.", parse_mode="HTML")


# ══════════════════════════════════════════════════════════════
# Application Build & Startup
# ══════════════════════════════════════════════════════════════

async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(context.error, Conflict):
        print("⚠️ Telegram Conflict: يرجى إيقاف أي كائن للبوت يعمل محلياً على جهازك.", flush=True)
    else:
        print(f"⚠️ Telegram Error: {context.error}", flush=True)


def build_telegram_app() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("⚠️ TELEGRAM_BOT_TOKEN غير موجود")
        return None

    app = ApplicationBuilder().token(token).build()

    # Registration conversation
    reg_handler = ConversationHandler(
        entry_points=[CommandHandler("register", register_start)],
        states={
            REG_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_username_received)],
            REG_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_password_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    # Groq Key conversation
    groq_handler = ConversationHandler(
        entry_points=[CommandHandler("setgroqkey", setgroqkey_start)],
        states={
            SET_GROQ_KEY_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, setgroqkey_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    app.add_handler(reg_handler)
    app.add_handler(groq_handler)

    # Callback Query Handler for Settings UI & Course Filters
    app.add_handler(CallbackQueryHandler(settings_callback_handler))

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("courses", courses_command))
    app.add_handler(CommandHandler("summary", summary_command))
    app.add_handler(CommandHandler("updates", updates_or_deadlines_command))
    app.add_handler(CommandHandler("deadlines", updates_or_deadlines_command))
    app.add_handler(CommandHandler("files", files_command))
    app.add_handler(CommandHandler("assignments", assignments_command))
    app.add_handler(CommandHandler("quizzes", quizzes_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("ai", ai_command))
    app.add_handler(CommandHandler("setgroqkey", setgroqkey_start))
    app.add_handler(CommandHandler("removegroqkey", removegroqkey_command))
    app.add_handler(CommandHandler("settings", settings_command))
    app.add_handler(CommandHandler("coursefilter", coursefilter_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("pause", pause_command))
    app.add_handler(CommandHandler("resume", resume_command))
    app.add_handler(CommandHandler("logout", logout_command))
    app.add_handler(CommandHandler("delete_account", delete_account_command))

    # Admin Handlers
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("admin_users", admin_users_command))
    app.add_handler(CommandHandler("admin_broadcast", admin_broadcast_command))
    app.add_handler(CommandHandler("admin_retry", admin_retry_command))

    app.add_error_handler(global_error_handler)

    return app


def send_message(text: str, chat_id: int | str = None):
    """Utility function for sending notification text via Telegram Bot API."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    cid = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not cid:
        print("⚠️ BOT_TOKEN or CHAT_ID not provided for notification")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            requests.post(url, json={
                "chat_id": cid,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }, timeout=15)
        except Exception as e:
            print(f"⚠️ Notification send error: {e}")


if __name__ == "__main__":
    app = build_telegram_app()
    if app:
        print("🤖 البوت يعمل ومستعد لاستقبال الأوامر...")
        app.run_polling()