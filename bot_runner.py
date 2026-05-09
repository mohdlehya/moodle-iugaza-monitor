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

def run_monitor():
    # انتظر دقيقة عند أول تشغيل
    time.sleep(60)
    while True:
        try:
            print("🔄 جاري تشغيل المراقبة...")
            subprocess.run([sys.executable, "main.py"], timeout=300)
            print("✅ انتهت — انتظار 6 ساعات")
        except Exception as e:
            print(f"⚠️ خطأ في المراقبة: {e}")
        time.sleep(6 * 60 * 60)

if __name__ == "__main__":
    threading.Thread(target=run_monitor, daemon=True).start()
    threading.Thread(target=start_bot, daemon=True).start()
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 Flask يعمل على port {port}")
    app.run(host="0.0.0.0", port=port)