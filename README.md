# 🤖 Moodle IUG Monitor & AI Assistant (جامعة غزة الإسلامية)

نظام مراقبة آلي وتفاعلي متعدد المستخدمين لبوابة **Moodle - الجامعة الإسلامية بغزة**، مدمج مع بوت Telegram ذكي مدعوم بمفاتيح **Groq AI (Llama-3)** مخصصة لكل طالب.

---

## 🌟 المميزات الرئيسية (Key Features)

- 🔒 **أمان عالي وخصوصية تامة**:
  - تشفير أوراق الاعتماد (كلمات مرور Moodle ومفاتيح Groq API) بتقنية **Fernet (AES-128-CBC)** at-rest.
  - حذف رسائل كلمات المرور والمفاتيح فور استلامها في شات التليجرام لحماية الخصوصية.
  - دعم حذف الحساب والبيانات نهائياً عبر أمر `/delete_account`.

- 🔑 **مفاتيح Groq API مخصصة لكل طالب (`/setgroqkey`)**:
  - يتطلب البوت من كل طالب إضافة مفتاحه المجاني الخاص من Groq لتجنب استهلاك الحصص المباشرة للمسؤول، وتفادي حدود الطلبات المشتركة per-minute.

- ⚙️ **لوحة إعدادات تفاعلية (`/settings` & `/coursefilter`)**:
  - أزرار تفاعلية (Inline Keyboard) للتحكم بكتم/تفعيل إشعارات (الملفات، الواجبات، الكويزات، المجلدات، ملخصات الذكاء الاصطناعي).
  - إمكانية كتم إشعارات مساق معين بضغطة زر مع بقاء بياناته متاحة للاستعلام.

- ⏰ **جدولة ذكية مع حماية Moodle (`APScheduler`)**:
  - جدولة آلية دورية بفوارق زمنية عشوائية (Jitter offsets) لمنع التحميل الفجائي على خوادم الجامعة.
  - عزل تام للأخطاء (Error Isolation): فشل دخول حساب طالب لا يؤثر على باقي الطلاب ويُسجل حالة أخطاء مخصصة له.

- 📊 **لوحة مراقبة وإدارة للمسؤول (`/admin`)**:
  - إحصائيات شاملة لحالات الحسابات (Nأشِط، متوقف، أخطاء) والإشعارات المُرْسَلَة.
  - إمكانية إرسال إعلانات عامة (`/admin_broadcast`) وإعادة تفعيل الحسابات المتعثرة (`/admin_retry`).
  - مسارات HTTP قياسية للمراقبة الحية: `/healthz` و `/metrics`.

---

## 🏗 بنية النظام (Architecture & Component Flow)

```mermaid
graph TD
    User([الطالب عبر Telegram]) <--> BotApp[Telegram Bot Application]
    Admin([مدير النظام]) <--> AdminCmds[/admin, /admin_broadcast, /admin_retry]

    BotApp <--> DB[(SQLAlchemy Database - SQLite/PostgreSQL)]
    
    subgraph Engine [محرك المراقبة والخدمات]
        Scheduler[APScheduler Background Workers] -->|Staggered Jitter Jobs| Scraper[Moodle Scraper & SAML2 Auth]
        Scraper -->|Scrape Courses & Events| Diff[Snapshot Diffing Engine]
        Diff -->|New Content Detected| Crypto[Fernet Decryption]
        Crypto -->|Decrypt Groq Key| Groq[Groq AI Client Llama-3]
        Groq -->|Generated Summaries| Notifier[Notification Dispatcher]
        Notifier -->|Push Notification| User
    end

    subgraph WebServer [Flask Observability]
        Health[/healthz & /metrics]
    end
```

---

## 🔑 متغيرات البيئة (Environment Variables)

| المتغير | الوصف | مثال / القيم |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | توكن البوت المستخرج من `@BotFather` | `123456789:ABCdef...` |
| `CREDENTIALS_ENCRYPTION_KEY` | مفتاح التشفير متناظر Fernet (32 bytes base64) | `s-I-0DmUMvgIJ1lLCX_...` |
| `DATABASE_URL` | رابط الاتصال بقاعدة البيانات (SQLite أو Postgres) | `postgresql://user:pass@host:5432/db` |
| `ADMIN_CHAT_ID` | Telegram Chat ID الخاص بمدير النظام | `123456789` |
| `GROQ_API_KEY` | مفتاح Groq احتياطي مشترك (Shared fallback key) | `gsk_...` |
| `MOODLE_URL` | رابط موقع Moodle للجامعة | `https://moodle.iugaza.edu.ps` |
| `PORT` | منفذ خادم Flask الهيلث شيك | `10000` |

---

## 📖 دليل الطالب لاستخدام البوت (Student User Guide)

### 1️⃣ التسجيل لأول مرة (`/register`)
1. افتح البوت وأرسل `/start` ثم اضغط على `/register`.
2. أدخل رقمك الجامعي (اسم المستخدم في Moodle).
3. أدخل كلمة المرور الخاصة بك. *(سيقوم البوت بحذف رسالة كلمة المرور فوراً من الشات وتشفيرها لحمايتك)*.

### 2️⃣ إضافة مفتاح Groq AI المجاني (`/setgroqkey`)
للحصول على ملخصات ذكية غير محدودة وإجابات سريعة عبر `/ai`:
1. افتح موقع Groq المجاني: [console.groq.com/keys](https://console.groq.com/keys).
2. قم بتسجيل الدخول واضغط على **Create API Key**.
3. انسخ المفتاح الذي يبدأ بـ `gsk_`.
4. أرسل الأمر `/setgroqkey` في البوت وأرسل المفتاح. *(سيحذف البوت المفتاح فور استلامه ويُشفره)*.

### 3️⃣ تخصيص الإشعارات وكتم المساقات (`/settings` & `/coursefilter`)
- أرسل `/settings` لإظهار الأزرار التفاعلية لتفعيل أو كتم (الملفات، الواجبات، الكويزات، ملخصات الذكاء الاصطناعي).
- أرسل `/coursefilter` لإظهار قائمة مساقاتك وكتم إشعارات أي مساق لا ترغب باتصالات دورية عنه.

### 4️⃣ الأوامر الاستعلامية اليومية
- `/courses`: عرض جميع المساقات والروابط المباشرة.
- `/summary`: ملخص عددي سريع لجميع محتوياتك.
- `/files`, `/assignments`, `/quizzes`: عرض الملفات والواجبات والكويزات.
- `/updates`, `/deadlines`: المواعيد القادمة من تقويم Moodle.
- `/ai سؤالك`: سؤال الذكاء الاصطناعي عن محتوى مساقاتك ومواعيدك.
- `/status`: عرض حالة حسابك ومراقبتك ومفتاحك.

---

## 👑 دليل مدير النظام (Admin Operations Guide)

عند تعيين `ADMIN_CHAT_ID` في بيئة العمل، تتوفر لك الأوامر التالية:

- `/admin`: يعرض لوحة تحكم تحتوي إحصائيات الحسابات والإشعارات المسجلة.
- `/admin_users`: يعرض جدول المستخدمين المسجلين، معرفاتهم وحالاتهم.
- `/admin_broadcast نص الإعلان`: إرسال إعلان رسمي لجميع الطلاب النشطين.
- `/admin_retry user_id`: إعادة تفعيل حساب متعثر (Error) وتصفير سجّلت أخطائه.

### منافذ المراقبة (HTTP Observability)
- `GET /healthz`: يعود بـ JSON يوضح حالة قاعدة البيانات وقناة الجدولة (`{"status": "ok", "database": "ok", "scheduler": "ok"}`).
- `GET /metrics`: يعود بمقاييس الأداء ووقت التشغيل وعدد المستخدمين والإشعارات.
- `GET /admin_export`: تصدير بيانات واستخدامات النظام بتنسيق JSON.

---

## 🛡 بيانية الخصوصية وحماية البيانات (Privacy & Security Statement)

- **البيانات المخزنة**:
  - `telegram_chat_id`: لإرسال الإشعارات إليك.
  - `moodle_username`: اسم المستخدم الخاص بك.
  - `moodle_password_encrypted`: كلمة المرور مشفرة شفرة Fernet at-rest ولا يمكن قراءتها كنص مجرد.
  - `groq_api_key_encrypted`: مفتاح Groq الخاص بك مشفر at-rest.
  - `content_json`: لقطة محتوى مساقاتك لغرض مقارنة التحديثات.
- **حذف البيانات**:
  - يمكنك في أي وقت حذف حسابك وجميع بياناتك نهائياً وبدون استرجاع عبر إرسال الأمر `/delete_account`.

---

## 🐳 التشغيل والتطوير المحلّي (Local Development & Docker Deployment)

### التشغيل عبر Docker Compose
```bash
# 1. نسخ ملف البيئة وتعبئة البيانات
cp .env.example .env

# 2. تشغيل الحاويات (App + PostgreSQL)
docker-compose up -d --build
```

### التشغيل المحلي للتطوير
```bash
# 1. التثبيت
pip install -r requirements.txt

# 2. توليد مفتاح تشفير جديد
python crypto.py --generate-key

# 3. تشغيل المهاجرات (Alembic)
alembic upgrade head

# 4. تشغيل البوت والجدولة
python bot_runner.py

# 5. تشغيل الاختبارات الآلية
pytest tests/ -v
```
