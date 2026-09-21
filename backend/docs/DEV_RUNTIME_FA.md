# محیط اجرای توسعه — BAMBO Finance Backend

## خلاصه

```
مفسر canonical      backend/ai-extraction-env/Scripts/python.exe   (Python 3.12.10)
اجرای devhost       backend/scripts/dev/run_devhost.cmd
```

همین. اگر فقط همین دو خط را بخوانید کافی است.

---

## چرا یک مفسرِ مشخص، و نه هر کدام که فعال باشد

روی یک ماشین توسعهٔ BAMBO چند محیط پایتون وجود دارد و پیش‌فرضِ `py` **اشتباه** است:

```
$ py -0p
  *               e:\bamboo\FINANCE\.venv\Scripts\python.exe     <-- پیش‌فرض
 -V:3.14          ...\Python314\python.exe
 -V:3.12          ...\Python312\python.exe
```

آنچه هر محیط واقعاً دارد:

| محیط | پایتون | backend | OCR / AI |
|---|---|---|---|
| `.venv` (ریشه) | 3.14.2 | ✅ | ❌ |
| `.venv312` | 3.12.10 | ✅ | ❌ |
| `ai-extraction-env` (ریشه) | 3.12.10 | ❌ | ناقص |
| **`backend/ai-extraction-env`** | **3.12.10** | ✅ | ✅ |

تنها محیطی که **هر دو** را دارد `backend/ai-extraction-env` است:
`uvicorn fastapi starlette pydantic alembic psycopg pytest sqlalchemy paddleocr paddle cv2 numpy PIL whisper torch jpype` — هیچ‌کدام غایب نیست.

---

## چرا `.venv` ریشه برای استخراج به کار نمی‌آید

سه دلیل، به ترتیب اهمیت:

**۱ — بسته‌های OCR آنجا نیستند و نصب هم نمی‌شوند.**
سرآمدِ خود `backend/extraction/requirements.txt` این را می‌گوید:

> «THESE PINS TARGET A LINUX SERVER AND ARE NOT VERIFIED. On Windows with CPython 3.12 they do not resolve at all — no wheels.»

`.venv` پایتون **۳.۱۴** است، یعنی wheelهای کمتری هم دارد. سند
`EXTRACTION_SELF_HOSTED_SETUP_FA.md` ثبت کرده که ساختن محیطی که واقعاً کار کند چه چیزهایی
لازم داشت — از جمله اینکه `paddlepaddle 3.3.1` روی Windows/CPU پیش از خواندن هر تصویری
داخل مسیر oneDNN خودش متوقف می‌شود.

**۲ — خرابی در لحظهٔ startup دیده نمی‌شود.**
`ImageExtractionAdapter` provider خود را **با تأخیر** import می‌کند — عمداً، تا میزبانی که
هرگز تصویری پردازش نمی‌کند بهای چند گیگابایت runtime یادگیری عمیق را نپردازد. نتیجه این
است که مفسر اشتباه کاملاً سالم به نظر می‌رسد: همهٔ endpointها سرو می‌شوند، log تمیز است،
و خطا خیلی بعد به‌صورت یک ۵۰۰ روی یک آپلود ظاهر می‌شود:

```
AI_EXTRACTION_FAILED
paddleocr-local (ProviderUnavailable)
ModuleNotFoundError: No module named 'paddleocr'
```

تا آن لحظه، آدم دارد فاکتور را debug می‌کند نه محیط را.

**۳ — MPP هم jpype می‌خواهد.**
`.venv312` حتی `jpype` ندارد، پس خواندن فایل‌های `.mpp` روی آن شکست می‌خورد.

---

## اجرا

```cmd
backend\scripts\dev\run_devhost.cmd
```

این اسکریپت:

- مفسر را **صریح** صدا می‌زند و به `PATH` کاری ندارد
- به `VIRTUAL_ENV` و محیط فعال‌شده کاری ندارد
- مسیر را از محل خودِ فایل حساب می‌کند، پس از هر دایرکتوری کار می‌کند
- آرگومان‌ها را عیناً رد می‌کند: `run_devhost.cmd --port 8010 --dsn ...`
- اگر مفسر canonical نبود، با پیام روشن و کد خروج ۱ متوقف می‌شود

برای محیط `terrace` (دیتابیس `bambo_canonical_test`) launcher اختصاصی جدا هست:

```cmd
backend\ai-extraction-env\Scripts\python.exe -m scripts.test_only.run_devhost_terrace
```

---

## هشدار startup

اگر devhost با مفسری بالا بیاید که `paddleocr` ندارد، پیش از هر چیز این را می‌نویسد:

```
  WARNING  this interpreter cannot run invoice extraction.
           `paddleocr` is not installed in it, so every call to
           POST /files/{fileId}/extractions will fail at request time.

           current interpreter   E:\bamboo\FINANCE\.venv\Scripts\python.exe
           expected              backend/ai-extraction-env/Scripts/python.exe
```

**جلوی بالا آمدن را نمی‌گیرد.** میزبانی بدون OCR چیز کاملاً عادی‌ای است — بیشتر کارهای
توسعه اصلاً به استخراج دست نمی‌زنند — پس این یادداشتی است دربارهٔ آنچه کار نخواهد کرد،
نه امتناع از اجرا.

بررسی با `importlib.util.find_spec` انجام می‌شود که فقط metadata را می‌خواند و ماژول را
**import نمی‌کند**؛ اندازه‌گیری‌شده ۰٫۰۰۰ ثانیه. یعنی خودِ هشدار نمی‌تواند همان بارگذاری
سنگینی را راه بیندازد که برای محافظت از آن نوشته شده.

---

## پیکربندی لازم برای استخراج

```
EXTRACTION_PROVIDER=self_hosted
```

بدون این، `extraction_providers()` عمداً `UnavailableExtractor("dev-image-extractor")`
برمی‌گرداند و استخراج با «provider پیکربندی نشده» رد می‌شود. این یک نام است نه یک boolean،
چون روزی بیش از یک گزینه خواهد بود.

هیچ API key ای لازم نیست — PaddleOCR و Whisper هر دو محلی‌اند. متغیرهای
`FINANCE_AI_*` فقط برای لایهٔ اختیاری LLM هستند که خلأهای پارسر قطعی را پر می‌کند.

---

## JRE برای اجرای کامل آزمون‌ها

مفسر canonical همهٔ بسته‌های پایتون را دارد، ولی MPXJ روی JVM اجرا می‌شود و JRE جزء
محیط پایتون نیست. بدون آن، یازده آزمونِ فایل واقعی MPP با `JavaRuntimeNotAvailable`
**خطا می‌دهند** — نه skip:

```cmd
set MPP_JAVA_HOME=E:\bamboo\jre\jdk-17.0.20.1+1-jre
```

این خطا عمدی است. `tests/test_mpp_reader_real_file.py` در سرآمد خودش نوشته که ماشینِ
بدون JRE باید **بلند** شکست بخورد نه بی‌صدا رد شود، چون آزمونی که خاموش از پارس‌کردنِ
فایل واقعی دست بکشد دقیقاً همان پوششی را از دست داده که برای آن نوشته شده.

JRE باید **کامل** باشد نه jlink‌شدهٔ کمینه: runtime بدون `jdk.charsets` داخل
charset initializer خود MPXJ و پیش از باز شدن هیچ فایلی می‌میرد.

بدون این متغیر:  `2105 passed, 11 errors`
با این متغیر:    `2116 passed, 0 failures`

---

## عیب‌یابی سریع

```cmd
rem  کدام مفسر؟
backend\ai-extraction-env\Scripts\python.exe --version
rem  انتظار: Python 3.12.10

rem  OCR هست؟
backend\ai-extraction-env\Scripts\python.exe -c "import paddleocr; print(paddleocr.__version__)"
rem  انتظار: 3.7.0

rem  devhost بالا می‌آید؟
backend\scripts\dev\run_devhost.cmd --help
```

اگر سومی `ModuleNotFoundError: No module named 'uvicorn'` داد، محیط اشتباهی را صدا
زده‌اید — احتمالاً `ai-extraction-env` ریشه به‌جای آنِ داخل `backend/`. این دو هم‌نام‌اند و
یکی‌شان ناقص است.

---

## آنچه **نباید** کرد

- ❌ نصب بسته‌های OCR در `.venv` — resolve نمی‌شوند
- ❌ ساختن محیط یکپارچهٔ جدید — محیط کامل از قبل هست
- ❌ ادغام محیط‌ها
- ❌ حذف هیچ‌کدام از محیط‌های موجود بدون تصمیم صریح

`.venv312` (۹۱M) و `ai-extraction-env` ریشه (۴۷۸M، ناقص) بازماندهٔ تلاش‌های قبلی‌اند.
دست‌نخورده مانده‌اند چون حذفشان تصمیمی است که کسی باید بگیرد، نه عارضهٔ جانبی یک اصلاح.
