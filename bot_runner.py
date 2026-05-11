import time, threading, sys, subprocess, os
from telegram_bot import start_bot
from app import app
from dotenv import load_dotenv

load_dotenv()

print(f"🔑 GROQ_API_KEY: {'✅ موجود' if os.getenv('GROQ_API_KEY') else '❌ غير موجود'}", flush=True)
print(f"🤖 BOT_TOKEN:    {'✅ موجود' if os.getenv('TELEGRAM_BOT_TOKEN') else '❌ غير موجود'}", flush=True)
print(f"📚 MOODLE_URL:   {os.getenv('MOODLE_URL', '❌ غير موجود')}", flush=True)

# Lock يُستخدم فقط في /ai handler — ليس هنا
monitor_lock = threading.Lock()


def run_monitor():
    first_run = True
    while True:
        try:
            print("🔄 تشغيل المراقبة...", flush=True)
            cmd = [sys.executable, "main.py"]
            if first_run:
                cmd.append("--silent")
                first_run = False
            # ── لا تحتجز الـ lock هنا
            subprocess.run(cmd, timeout=300, env=os.environ.copy())
            print("✅ انتهت المراقبة", flush=True)
        except subprocess.TimeoutExpired:
            print("⚠️ المراقبة تجاوزت 5 دقائق — تُلغى وتُعاد", flush=True)
        except Exception as e:
            print(f"⚠️ خطأ في المراقبة: {e}", flush=True)
        time.sleep(60 * 60 * 6)


def run_bot():
    while True:
        try:
            print("🤖 البوت يستمع للأوامر...", flush=True)
            start_bot()
        except Exception as e:
            print(f"⚠️ خطأ في البوت: {e} — إعادة المحاولة بعد 10 ثواني", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    # daemon=True → يموت مع العملية الرئيسية (Flask)
    threading.Thread(target=run_monitor, daemon=True).start()
    threading.Thread(target=run_bot, daemon=True).start()

    port = int(os.getenv("PORT", 10000))
    print(f"🚀 Flask يعمل على port {port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)