import os
from datetime import datetime
from flask import Flask, jsonify
from database import get_db_context
from models import User, NotificationLog
from scheduler import scheduler

app = Flask(__name__)
START_TIME = datetime.now()


@app.route("/")
def home():
    return "🤖 Moodle Bot is running!", 200


@app.route("/health")
@app.route("/healthz")
def health():
    db_status = "ok"
    try:
        with get_db_context() as db:
            db.query(User).first()
    except Exception as e:
        db_status = f"error: {e}"

    sched_status = "ok" if (scheduler and scheduler.running) else "stopped"
    overall_status = 200 if (db_status == "ok") else 500

    return jsonify({
        "status": "ok" if overall_status == 200 else "degraded",
        "database": db_status,
        "scheduler": sched_status,
        "timestamp": datetime.now().isoformat()
    }), overall_status


@app.route("/metrics")
def metrics():
    uptime_seconds = int((datetime.now() - START_TIME).total_seconds())
    try:
        with get_db_context() as db:
            total_users = db.query(User).count()
            active_users = db.query(User).filter(User.status == "active").count()
            error_users = db.query(User).filter(User.status == "error").count()
            total_logs = db.query(NotificationLog).count()
    except Exception:
        total_users = active_users = error_users = total_logs = -1

    job_count = len(scheduler.get_jobs()) if (scheduler and scheduler.running) else 0

    return jsonify({
        "uptime_seconds": uptime_seconds,
        "total_users": total_users,
        "active_users": active_users,
        "error_users": error_users,
        "total_notifications_sent": total_logs,
        "active_jobs_count": job_count
    }), 200


@app.route("/admin_export")
def admin_export():
    try:
        with get_db_context() as db:
            users = db.query(User).all()
            user_list = [
                {
                    "id": u.id,
                    "moodle_username": u.moodle_username,
                    "status": u.status,
                    "has_custom_groq_key": bool(u.groq_api_key_encrypted),
                    "last_check_at": u.last_check_at.isoformat() if u.last_check_at else None,
                    "last_error": u.last_error,
                }
                for u in users
            ]
            total_logs = db.query(NotificationLog).count()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({
        "exported_at": datetime.now().isoformat(),
        "total_users": len(user_list),
        "users": user_list,
        "total_notifications": total_logs,
    }), 200