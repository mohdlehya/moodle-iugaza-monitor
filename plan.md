# Prompt for AI Coding Agent: Convert `moodle-iugaza-monitor` to a Multi-User Service

## Context (give this to the agent as-is)

You are working on an existing Python repository: **moodle-iugaza-monitor**
(https://github.com/mohdlehya/moodle-iugaza-monitor.git).

Current state:

- It logs into IUGaza's Moodle (SAML2 SSO) for **one hardcoded user** (`MOODLE_USERNAME` /
  `MOODLE_PASSWORD` in `.env`), scrapes course content (files, assignments, quizzes, folders)
  and the Moodle calendar API, diffs it against a locally saved JSON snapshot
  (`data.json`, `events.json`), and sends Telegram notifications to a **single hardcoded chat**
  (`TELEGRAM_CHAT_ID`).
- A Telegram bot (`telegram_bot.py`) answers slash-commands (`/courses`, `/deadlines`,
  `/files`, `/search`, `/ai`, ...) but only responds to that one chat ID.
- `groq_helper.py` calls the Groq API (`llama-3.1-8b-instant`) to produce Arabic summaries
  of assignments/quizzes/calendar events, and powers a `/ai` free-text Q&A command using the
  user's saved Moodle data as context.
- `bot_runner.py` + `app.py` run a Flask health-check server and two background threads
  (a 6-hour monitoring loop calling `main.py`, and the Telegram polling loop) — this is
  designed for a single free-tier deployment (e.g. Render).
- Storage is flat JSON files on local disk. No database. No encryption. No tests beyond
  manual scripts. No multi-tenant concept anywhere in the code.

**Goal:** Turn this into a multi-user service where any IUGaza student can register their own
Moodle account through the Telegram bot itself, get isolated monitoring + notifications +
AI summaries, and control their preferences (notification types, frequency, digest mode,
quiet hours, language, muted courses) directly from Telegram — without needing their own
deployment or touching any code/env vars.

## Non-negotiable constraints

1. **Per-user isolation** — one user's data, session, errors, or rate limits must never
   leak into or block another user's monitoring.
2. **Encrypt sensitive credentials at rest.** Never store or log plaintext Moodle passwords or user-provided Groq API keys.
3. **Respect Moodle server load.** With N students, requests must be staggered/jittered
   across the check window — never fire N simultaneous login+scrape sequences at the same
   university server, since that looks like an attack and risks the whole app getting
   IP-banned. Keep and extend the existing `sleep()` delay pattern.
4. **Graceful per-user failure handling.** A wrong password, locked account, or Moodle
   layout change for one user must degrade to "notify that user, mark them paused" — not
   crash the scheduler for everyone.
5. **Give users a way to leave and delete their data** (`/delete_account`), since you are
   storing university login credentials and custom API keys — this is sensitive data.
6. Keep the bot's user-facing language Arabic by default (matches current UX); code,
   comments, and internal docs can be English.
7. Work **phase by phase**. After each phase: summarize what changed, list new/changed
   files, list any new environment variables, and list how to test the phase, before moving
   to the next one. Do not silently skip encryption or isolation to "move faster" — those
   are core requirements, not polish.
8. Ask before deleting existing data, rewriting `.env`, or force-pushing.

## Target architecture (end state)

- **Database:** PostgreSQL in production (SQLite acceptable for local dev), accessed via
  SQLAlchemy + Alembic migrations. Replaces `data.json` / `events.json`.
- **Secrets:** Fernet symmetric encryption (`cryptography` package) for Moodle passwords and custom user Groq API keys,
  key supplied via a separate env var (`CREDENTIALS_ENCRYPTION_KEY`), never committed.
- **Scheduler:** APScheduler running per-user jobs with staggered start offsets within the
  check window (e.g. spread all users across 6 hours instead of firing together). Note a
  migration path to Celery + Redis if the user base grows large enough that in-process
  APScheduler becomes a bottleneck.
- **Telegram bot:** migrate off the raw `getUpdates` loop to the `python-telegram-bot`
  library, using its `ConversationHandler` for multi-step flows (registration, settings)
  and inline keyboards for settings menus instead of typed command syntax.
- **Web:** keep the Flask health endpoint; optionally add a lightweight `/admin/stats`
  endpoint (protected) for your own monitoring.

---

## Phase 0 — Discovery & project setup

- Read through the full existing codebase and confirm understanding of current data flow
  (login → scrape → diff → notify → calendar → AI summary).
- Create a new branch `multi-user-migration`.
- Add `.env.example` documenting every env var currently used (`MOODLE_URL`,
  `TELEGRAM_BOT_TOKEN`, `GROQ_API_KEY`, `PORT`, etc.) plus the new ones this plan will
  introduce.
- Pin dependency versions in `requirements.txt` (currently unpinned) and add:
  `sqlalchemy`, `alembic`, `cryptography`, `apscheduler`, `python-telegram-bot`, `pytest`.
- Write a short `ARCHITECTURE.md` describing the target design from this prompt, so future
  contributors don't need to re-derive it.

**Done when:** branch exists, `.env.example` and `ARCHITECTURE.md` are committed, deps
installed cleanly in a fresh venv.

---

## Phase 1 — Data model & persistence layer

Design and implement (SQLAlchemy models + Alembic migration):

- `users`: `id`, `telegram_chat_id` (unique), `telegram_username`, `moodle_username`,
  `moodle_password_encrypted`, `groq_api_key_encrypted` (nullable, encrypted custom Groq key),
  `moodle_url` (default IUGaza, but keep it a column — some future flexibility), `language` (default `ar`),
  `status` (`active` / `paused` / `error` / `unregistered`), `created_at`, `last_check_at`, `last_error`.
- `course_content`: per-user, per-course snapshot of files/assignments/quizzes/folders
  (JSON column is fine here — this data is inherently semi-structured and diffed as a
  whole, no need to over-normalize).
- `calendar_events`: per-user calendar snapshot (mirrors current `events.json` shape).
- `user_settings`: `user_id`, `notify_files`, `notify_assignments`, `notify_quizzes`,
  `notify_folders` (booleans), `digest_mode` (`instant` / `daily`), `digest_time`,
  `quiet_hours_start`, `quiet_hours_end`, `muted_courses` (JSON list), `ai_summaries_enabled`.
- Optional: `notification_log` for debugging/audit ("what did we send and when").

Write a one-off migration script that imports the _existing_ single-user `data.json` /
`events.json` (if present) as the first row in `users`, so the current deployment doesn't
lose history.

**Done when:** `alembic upgrade head` creates a working schema; a unit test inserts and
reads back a user + settings row.

---

## Phase 2 — Credential security

- Add `crypto.py` with `encrypt_credential(plain) -> bytes` / `decrypt_credential(bytes) -> str`
  using Fernet and `CREDENTIALS_ENCRYPTION_KEY` (handles both Moodle passwords and Groq API keys).
- Audit every place passwords and Groq API keys flow through (`scraper.create_session`, `groq_helper`,
  any logging/print statements) and make sure plaintext secrets never hit logs or disk outside of
  in-memory execution.
- Implement `/delete_account` in the bot: wipes the user's row, encrypted credentials (Moodle & Groq key),
  settings, snapshots, and confirms deletion back to them.

**Done when:** grepping the codebase and logs for a test password or test Groq key after a full run
shows zero plaintext occurrences outside of in-memory execution.

---

## Phase 3 — Multi-user Telegram bot & registration flow

- Migrate `telegram_bot.py` from manual polling to `python-telegram-bot`
  (`ApplicationBuilder`, handlers, `ConversationHandler`).
- Replace the hardcoded `cid == CHAT_ID` check with a DB lookup by `telegram_chat_id`.
- Build `/register` as a guided conversation:
  1. Ask for Moodle username.
  2. Ask for Moodle password **in a follow-up message**, then immediately delete that
     message from the chat via the Bot API (`delete_message`) after reading it, so the
     password doesn't sit visibly in chat history — tell the user you're doing this.
  3. Attempt a real login (reuse `scraper.create_session`) to validate credentials before
     saving; on failure, tell the user clearly and let them retry.
  4. On success, encrypt + store, create default `user_settings`, confirm registration,
     and kick off their first scrape (reuse today's "welcome summary" behavior).
- Scope every existing command (`/courses`, `/summary`, `/updates`, `/deadlines`, `/files`,
  `/assignments`, `/quizzes`, `/search`, `/ai`) to `user_id` resolved from the sender's
  `chat_id`, querying only their own data.
- Add `/setgroqkey` flow:
  1. Explain to the student in a 2-step Arabic message how to get a free Groq API key from console.groq.com (takes ~2 minutes).
  2. Ask student to reply with their API key (`gsk_...`).
  3. Immediately delete the message containing the key via Telegram Bot API `delete_message` after reading (same security pattern as Moodle password).
  4. Test key validity via a quick test ping call (`groq_helper.test_key(key)`).
  5. On success: encrypt and store in `groq_api_key_encrypted`, notify user. On failure: inform user clearly and allow retry.
- Add: `/logout` (stop monitoring, keep data), `/pause`, `/resume`, `/setgroqkey`, `/removegroqkey`,
  `/status` (shows check status, last error, and whether custom Groq key is set), `/delete_account`.

**Done when:** two different Telegram test accounts can independently `/register` with
different Moodle credentials and only ever see their own courses/data via any command.

---

## Phase 4 — Isolated per-user scraping & scheduling

- Refactor `main.py`'s `main()` into a `run_check_for_user(user_id)` function that pulls
  that user's decrypted credentials, creates its own `requests.Session`, scrapes, diffs
  against their stored snapshot, and sends notifications only to their `chat_id`.
- Set up an APScheduler `BackgroundScheduler` that, on startup, loads all `active` users
  and schedules a recurring job per user, with a randomized/staggered initial offset so
  users are spread across the check window instead of firing simultaneously — keep the
  existing `sleep()` delays between individual requests too.
- Wrap each user's job in error isolation: catch exceptions per-job, set
  `status='error'` + `last_error`, notify that user, and make sure one failure never stops
  the scheduler or affects other users' jobs.
- Add heuristics to detect Moodle rate-limiting/lockout responses (repeated redirects to a
  login/error page, HTTP 403, etc.) and back off + notify the affected user to re-check
  their credentials, instead of hammering Moodle repeatedly.
- Add a job that re-syncs the scheduler's user list periodically (so new registrations /
  pauses / deletions take effect without a full restart).

**Done when:** running with 3+ seeded test users produces staggered, isolated scrape runs
in logs, and killing/breaking one user's credentials doesn't affect the others.

---

## Phase 5 — Enhanced Telegram-based control (settings & preferences)

- `/settings` — inline-keyboard menu (using `python-telegram-bot`'s `InlineKeyboardMarkup`)
  to toggle, without typing exact syntax:
  - Notify on: files / assignments / quizzes / folders (independent toggles).
  - Digest mode: instant notifications vs. a single daily digest at a chosen time.
  - Quiet hours (no pushes between chosen start/end times; queue and send in the next
    allowed window, or fold into the next digest).
  - Bot language: Arabic / English (affects both bot UI strings and the Groq summary
    prompt language).
  - AI summaries: on/off (lets cost-conscious users disable Groq calls entirely).
- `/coursefilter` — list the user's courses with toggle buttons to mute/unmute
  notifications per course (keep receiving data on `/courses` etc., just skip push
  notifications for muted ones).
- `/status` should also show current settings at a glance (including custom Groq key status: `Set ✅` / `Not Set ❌`).

**Done when:** a user can fully configure notification behavior through button taps alone,
with no need to remember command syntax.

---

## Phase 6 — AI feature improvements & per-user Groq API keys

- Update `groq_helper.py` to instantiate client dynamically using each user's decrypted `groq_api_key_encrypted`:
  - **Custom Key (Primary):** If user has provided their own Groq key via `/setgroqkey`, decrypt and use it for all `/ai` queries and auto-summaries (zero cost impact on host, isolated rate limits).
  - **Shared Key Fallback (Optional):** If user has NOT set a custom key, fall back to the system `GROQ_API_KEY` (if configured in `.env`), enforced by a strict daily cap per user (e.g. 5 requests/day) to protect admin quota.
  - **No Key / Cap Reached:** If user has no key and system fallback is disabled or exhausted, prompt user with clear Arabic instructions to add their key via `/setgroqkey`.
- Add key validation & error handling: catch Groq API authorization/quota errors (401/429) per-user and notify user to update/check their key via `/setgroqkey`.
- Cache AI summaries per `(item_url, content_hash)` so the same assignment/quiz isn't re-summarized unnecessarily across runs.
- Respect the `ai_summaries_enabled` setting from Phase 5 before invoking Groq.

**Done when:** AI calls execute using the user's custom Groq key when provided, fall back safely when not, and invalid keys are caught gracefully without affecting other users.

---

## Phase 7 — Reliability, observability, admin tools

- Replace `print()` calls with Python's `logging` module: structured (include `user_id`
  where relevant), no secrets, configurable level via env var.
- Add an admin-only command set, restricted to a hardcoded "admin" `telegram_chat_id`
  (yours): `/admin_stats` (active/paused/error user counts, custom Groq key usage count, last global run time),
  `/admin_recheck <user_id>` (force an immediate check), `/admin_broadcast <message>`
  (send to all active users — e.g. for maintenance notices).
- Extend `app.py`'s Flask app with a lightweight `/admin/stats` JSON endpoint (basic-auth
  or a shared secret header) for external monitoring/alerting.
- Add `pytest` tests: HTML-parsing functions against saved fixture pages (so Moodle theme
  changes are caught by CI, not discovered in production), bot command handlers with
  mocked Telegram objects, and the encryption round-trip.

**Done when:** `pytest` runs a meaningful suite in CI, and you have visibility into system
health without SSHing into the server.

---

## Phase 8 — Deployment & scaling readiness

- Add a `Dockerfile` and `docker-compose.yml` (app + Postgres, + Redis only if/when Celery
  is adopted).
- Move off any free-tier ephemeral disk onto a managed Postgres instance (Render Postgres,
  Supabase, Railway, etc.) — this is required, since local JSON files/SQLite-on-ephemeral-
  disk will lose all user data on every redeploy.
- Wire `alembic upgrade head` into the deploy step.
- Update `README.md` and `.env.example` with the final full list of required env vars.
- Add graceful shutdown handling so the scheduler and bot threads stop cleanly on deploy
  restarts instead of leaving half-finished scrape jobs.

**Done when:** a fresh deploy from a clean database comes up, runs migrations, and existing
registered users keep working across a redeploy with zero data loss.

---

## Phase 9 — Documentation & handoff

- Full `README.md`: what the project does, architecture diagram/description, full env var
  list, how a new student self-registers via the bot (student-facing, in Arabic), how you
  operate it as admin.
- Short privacy note for users: what data is stored (Moodle username, encrypted password,
  encrypted Groq API key, course metadata, chat ID), why, and how to delete it (`/delete_account`).
- Student guide in Arabic explaining how to register at console.groq.com, generate a free API key, and configure it via `/setgroqkey`.

---

## How to hand this to the agent

Paste everything from "## Context" down to the end of Phase 9 as the agent's task. Tell it
to start at Phase 0, confirm the plan, then proceed phase-by-phase, pausing for your review
after each phase's "Done when" criteria are met before starting the next one.
