#local
# import time, threading
# from telegram_bot import start_bot, send_message

# if __name__ == "__main__":
#     print("🤖 البوت يعمل — أرسل /help في Telegram")
#     print("اضغط Ctrl+C لإيقافه")
#     try:
#         start_bot()  # يشتغل إلى الأبد
#     except KeyboardInterrupt:
#         print("\n⛔ تم إيقاف البوت")
import time, threading, sys, subprocess, os
from telegram_bot import start_bot
from app import app
from dotenv import load_dotenv

load_dotenv()

# ── تحقق من المتغيرات عند البدء
print(f"🔑 GROQ_API_KEY: {'✅ موجود' if os.getenv('GROQ_API_KEY') else '❌ غير موجود'}", flush=True)
print(f"🤖 BOT_TOKEN:    {'✅ موجود' if os.getenv('TELEGRAM_BOT_TOKEN') else '❌ غير موجود'}", flush=True)
print(f"📚 MOODLE_URL:   {os.getenv('MOODLE_URL', '❌ غير موجود')}", flush=True)

# ── Lock لمنع تشغيل monitor أثناء /ai
monitor_lock = threading.Lock()


def run_monitor():
    time.sleep(90)  # انتظر حتى يستقر كل شيء
    while True:
        try:
            with monitor_lock:
                print("🔄 تشغيل المراقبة...", flush=True)
                subprocess.run(
                    [sys.executable, "main.py"],
                    timeout=300,
                    env=os.environ.copy()  # ← مرر كل المتغيرات لـ main.py
                )
                print("✅ انتهت المراقبة", flush=True)
        except subprocess.TimeoutExpired:
            print("⚠️ انتهى الوقت المحدد للمراقبة", flush=True)
        except Exception as e:
            print(f"⚠️ خطأ في المراقبة: {e}", flush=True)
        time.sleep(6 * 60 * 60)


def run_bot():
    while True:
        try:
            print("🤖 البوت يستمع للأوامر...", flush=True)
            start_bot()
        except Exception as e:
            print(f"⚠️ خطأ في البوت: {e} — إعادة المحاولة", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    threading.Thread(target=run_monitor, daemon=True).start()
    threading.Thread(target=run_bot,     daemon=True).start()

    port = int(os.getenv("PORT", 10000))  # ← Render يستخدم 10000
    print(f"🚀 Flask يعمل على port {port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)