import asyncio
import time
import threading
import sys
import os
import signal
from telegram.error import Conflict
from telegram_bot import build_telegram_app
from scheduler import start_scheduler
from app import app
from database import init_db
from dotenv import load_dotenv

load_dotenv()

print(f"🔑 GROQ_API_KEY: {'✅ موجود' if os.getenv('GROQ_API_KEY') else '❌ غير موجود'}", flush=True)
print(f"🤖 BOT_TOKEN:    {'✅ موجود' if os.getenv('TELEGRAM_BOT_TOKEN') else '❌ غير موجود'}", flush=True)
print(f"📚 MOODLE_URL:   {os.getenv('MOODLE_URL', '❌ غير موجود')}", flush=True)

scheduler_instance = None


def shutdown_handler(signum, frame):
    """Gracefully shutdown scheduler and threads on SIGINT/SIGTERM."""
    print(f"\n🛑 Shutdown signal received ({signum}). Cleaning up...", flush=True)
    global scheduler_instance
    if scheduler_instance and scheduler_instance.running:
        scheduler_instance.shutdown(wait=False)
        print("⏰ BackgroundScheduler stopped.", flush=True)
    sys.exit(0)


def run_flask():
    port = int(os.getenv("PORT", 10000))
    print(f"🚀 Flask يعمل على port {port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def run_bot():
    while True:
        try:
            # Ensure a fresh event loop exists (previous run_polling closes it)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    asyncio.set_event_loop(asyncio.new_event_loop())
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())

            bot_app = build_telegram_app()
            if bot_app:
                print("🤖 البوت يعمل ومستعد لاستقبال الأوامر...", flush=True)
                bot_app.run_polling(drop_pending_updates=True)
            else:
                print("⚠️ تعذر تشغيل البوت — TELEGRAM_BOT_TOKEN غير موجود")
                break
        except Conflict:
            print("⚠️ Telegram Conflict: يرجى إيقاف أي كائن للبوت يعمل محلياً على جهازك. سيعاد الاتصال خلال 15 ثانية...", flush=True)
            time.sleep(15)
        except SystemExit:
            break
        except Exception as e:
            print(f"⚠️ خطأ في البوت: {e} — إعادة المحاولة بعد 10 ثواني", flush=True)
            time.sleep(10)


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, shutdown_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown_handler)

    # Initialize database tables if missing
    init_db()

    # Start APScheduler in background
    scheduler_instance = start_scheduler()

    # Start Flask Web Health Server in daemon thread
    threading.Thread(target=run_flask, daemon=True).start()

    # Start Telegram Bot in main thread
    run_bot()