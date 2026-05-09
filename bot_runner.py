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

print(f"🔑 GROQ_API_KEY: {'✅ موجود' if os.getenv('GROQ_API_KEY') else '❌ غير موجود'}", flush=True)
print(f"🤖 BOT_TOKEN:    {'✅ موجود' if os.getenv('TELEGRAM_BOT_TOKEN') else '❌ غير موجود'}", flush=True)

monitor_lock = threading.Lock()


def run_monitor():
    # ← شغّل فوراً عند البدء بدون انتظار
    while True:
        try:
            with monitor_lock:
                print("🔄 تشغيل المراقبة...", flush=True)
                subprocess.run(
                    [sys.executable, "main.py"],
                    timeout=300,
                    env=os.environ.copy()
                )
                print("✅ انتهت المراقبة", flush=True)
        except subprocess.TimeoutExpired:
            print("⚠️ انتهى الوقت", flush=True)
        except Exception as e:
            print(f"⚠️ خطأ: {e}", flush=True)
        time.sleep(6 * 60 * 60)


def run_bot():
    # ← انتظر 3 دقائق حتى تنتهي المراقبة الأولى وينشأ data.json
    print("⏳ انتظار 3 دقائق حتى ينشأ data.json...", flush=True)
    time.sleep(180)
    while True:
        try:
            print("🤖 البوت يستمع للأوامر...", flush=True)
            start_bot()
        except Exception as e:
            print(f"⚠️ خطأ في البوت: {e}", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    threading.Thread(target=run_monitor, daemon=True).start()
    threading.Thread(target=run_bot,     daemon=True).start()

    port = int(os.getenv("PORT", 10000))
    print(f"🚀 Flask يعمل على port {port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)