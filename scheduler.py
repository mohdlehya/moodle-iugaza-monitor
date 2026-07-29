import random
import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from database import get_db_context
from models import User
from main import run_check_for_user

scheduler = BackgroundScheduler()


def scheduled_user_job(user_id: int):
    """Wrapper function executing a single user check with total error isolation."""
    try:
        run_check_for_user(user_id)
    except Exception as e:
        print(f"⚠️ Scheduler error for user_id={user_id}: {e}")


def sync_user_jobs():
    """Sync active users from DB with APScheduler recurring jobs."""
    try:
        with get_db_context() as db:
            active_users = db.query(User).filter(User.status == "active").all()
            active_user_ids = {u.id for u in active_users}

        current_job_ids = {job.id for job in scheduler.get_jobs() if job.id.startswith("user_job_")}

        # Remove jobs for users no longer active/paused/deleted
        for job_id in current_job_ids:
            try:
                uid = int(job_id.replace("user_job_", ""))
                if uid not in active_user_ids:
                    scheduler.remove_job(job_id)
                    print(f"⏹ Descheduled job for User ID {uid}")
            except ValueError:
                pass

        # Add jobs for active users
        for uid in active_user_ids:
            job_id = f"user_job_{uid}"
            if not scheduler.get_job(job_id):
                jitter = random.randint(0, 120)
                scheduler.add_job(
                    scheduled_user_job,
                    "interval",
                    hours=6,
                    next_run_time=datetime.now(),
                    args=[uid],
                    id=job_id,
                    name=f"User Check {uid}",
                    replace_existing=True,
                    jitter=jitter,
                )
                print(f"🗓 Scheduled recurring 6-hour monitoring job for User ID {uid} (immediate first run)")

    except Exception as e:
        print(f"⚠️ Scheduler sync error: {e}")


def start_scheduler() -> BackgroundScheduler:
    """Start APScheduler and trigger recurring user list resync."""
    if not scheduler.running:
        scheduler.start()
        print("⏰ BackgroundScheduler started.")

    sync_user_jobs()

    if not scheduler.get_job("sync_user_jobs_meta"):
        scheduler.add_job(
            sync_user_jobs,
            "interval",
            minutes=5,
            id="sync_user_jobs_meta",
            name="Dynamic User List Resync",
        )

    return scheduler


if __name__ == "__main__":
    s = start_scheduler()
    print("Scheduler running. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        s.shutdown()
