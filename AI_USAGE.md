# استفاده از هوش مصنوعی در ماژول مالی BAMBO

سند تحویل‌دادنی PRD §۱۶.۱. هر ادعای این سند از کد همین مخزن خوانده شده و مسیر فایلش نوشته شده.

---

## ۱. هوش مصنوعی کجا و فقط کجا

AI در این ماژول **یک کار** می‌کند: از تصویر یا صدای یک فاکتور، یک **پیش‌نویس** می‌سازد.

هیچ جای دیگری AI دخالت ندارد — نه در محاسبهٔ مالی، نه در نگاشت MPP، نه در قیمت‌گذاری،
نه در طبقه‌بندی منابع. آن‌ها قواعد قطعی‌اند و AI نمی‌بیندشان.

**اثر مالیِ پیش‌نویس، پیش از تأیید انسانی، دقیقاً صفر است.**
`extraction_drafts.financial_effect_irr = 0` تا لحظهٔ تأیید؛ و فقط فاکتور `confirmed`
وارد هزینهٔ واقعی می‌شود.

---

## ۲. انتزاع Provider

دو Protocol مستقل، در `backend/app/finance/adapters/ports.py`:

```
class InvoiceImageExtractor(Protocol):
    adapter_name: str
    async def extract(self, file, hints) -> object

class InvoiceVoiceExtractor(Protocol):
    adapter_name: str
    async def extract(self, file, hints) -> object
```

تصویر و صدا **دو Interface جدا** هستند، نه یکی با پرچم. هیچ نام Providerی در منطق مالی
نیست؛ سرویس فقط `adapter_name` را می‌بیند و همان را روی پیش‌نویس ثبت می‌کند
(`extraction_drafts.provider_adapter`).

### آنچه امروز پیاده شده

| آداپتر | `adapter_name` | فناوری | فایل |
|---|---|---|---|
| تصویر | `paddleocr-local` | PaddleOCR | `backend/extraction/providers/paddle_ocr.py` |
| صدا | `whisper-local` | OpenAI Whisper، مدل `small` | `backend/extraction/providers/whisper_voice.py` |

هر دو **خودمیزبان** هستند. هیچ فراخوانی شبکه‌ای به سرویس بیرونی انجام نمی‌دهند.

**پیش‌فرض، هیچ‌کدام نیست.** بدون `EXTRACTION_PROVIDER=self_hosted`، میزبان
`UnavailableExtractor` نصب می‌کند — یعنی استخراج «در دسترس نیست» می‌گوید نه اینکه
چیزی حدس بزند (`backend/devhost/environment.py`).

---

## ۳. قرارداد ورودی و خروجی

### ورودی

- فقط `invoice_image` یا `invoice_voice`، از راه multipart.
- تصویر: JPEG / PNG / WebP، حداکثر **۱۰ MiB**. GIF و SVG مجاز نیستند.
- صدا: MP3 / M4A / WAV / OGG، حداکثر **۲۵ MiB**. WebM جزو MVP نیست.
- پسوند، MIME اعلامی و **Magic Bytes** هر سه باید یکی باشند، وگرنه
  `UNSUPPORTED_MEDIA_TYPE` (`backend/app/finance/services/attachments.py::detect_file`).
- نام ذخیره تصادفی است؛ نام اصلی فقط به‌عنوان متادیتای نمایشی می‌ماند.

### خروجی

یک `ExtractionDraft` با:

- `extracted_fields` — آنچه Provider گفت
- هر فیلد: مقدار، **confidence**، مقدار تأییدشدهٔ کاربر، و علامت اینکه کاربر ویرایشش کرده
- `confirmed_fields` — تا پیش از تأیید `NULL`
- `review_status` ∈ `awaitingReview` · `accepted` · `rejected`
- `version` — برای تشخیص تأیید هم‌زمان
- `financial_effect_irr` = `0` تا تأیید

confidence خارج از بازه **کلمپ می‌شود، نه اینکه درخواست را بشکند**
(آزمون `test_a_confidence_outside_the_range_is_clamped_not_fatal`).

---

## ۴. Prompt

**هیچ prompt زبانی‌ای وجود ندارد.** هیچ LLM در مسیر نیست.

PaddleOCR یک مدل تشخیص متن است و Whisper یک مدل گفتار-به-متن؛ هیچ‌کدام دستور متنی
نمی‌گیرند. تبدیل متن خام به فیلدهای فاکتور با **قواعد قطعی و قابل‌خواندن** انجام می‌شود،
نه با مدل: `backend/extraction/invoice_parser.py` و `backend/extraction/parsing.py`.

این عمدی است. یک parser قاعده‌محور را می‌شود خواند، آزمود و توضیح داد؛ یک prompt را نه.

---

## ۵. حالت‌های خطا

| حالت | رفتار |
|---|---|
| Provider پیکربندی نشده | `UnavailableExtractor` — «در دسترس نیست»، نه حدس |
| Provider شکست خورد | فایل به `failed` می‌رود و **باقی می‌ماند**؛ ورود دستی همیشه ممکن است |
| محتوای نامعتبر | `AI_EXTRACTION_FAILED` (۴۲۲ / ۵۰۳) |
| کاربر غیرمجاز | `ExtractionForbidden` — «فقط ارسال‌کننده می‌تواند این فایل را پردازش کند» |
| تأیید هم‌زمان | بررسی نسخه؛ یکی موفق، دیگری Conflict |

**شکست Provider هرگز فایل را از بین نمی‌برد.** چرخهٔ فایل مستقل است و `failed` مبدأ
مجاز `Retry` است (`FILE_TRANSITIONS` در `backend/app/finance/domain/attachments.py`).

---

## ۶. Retry

`POST /finance/extractions/{draftId}/retry`

- فقط **ارسال‌کننده** می‌تواند retry کند.
- هر retry یک **نسخهٔ جدید** از پیش‌نویس می‌سازد؛ نسخهٔ قبلی بازنویسی نمی‌شود.
- شروع دوبارهٔ همان کار idempotent است؛ retry نسخهٔ بعدی می‌سازد
  (آزمون `test_repeated_start_is_idempotent_but_retry_creates_next_version`).
- وضعیت فایل مستقل می‌ماند
  (آزمون `test_retry_keeps_ready_file_lifecycle_independent_and_requires_uploader`).

---

## ۷. حریم داده

- هر دو آداپتر **خودمیزبان**‌اند: فایل فاکتور از این ماشین بیرون نمی‌رود.
- هیچ وابستگی به شبکهٔ بیرونی در مسیر استخراج نیست.
- فایل‌ها از مسیر عمومی سرو نمی‌شوند؛ فقط از endpoint مجوزدار
  (`GET /finance/files/{fileId}/content`، نیازمند `finance.manage_invoice`،
  و خارج از دامنه **۴۰۴** می‌دهد نه ۴۰۳ — اثبات‌شده).
- متادیتای هر فایل شامل سازمان، پروژه، بارگذارنده، اندازهٔ دقیق، MIME و **SHA-256** است.

اگر روزی Provider ابری انتخاب شود، این بند باید بازنویسی شود: سیاست استفاده از داده،
مدت نگه‌داری و آموزش‌ندادن مدل باید در قرارداد Provider بررسی شود (PRD §۱۳.۳).

---

## ۸. لاگ

- کد اپلیکیشن `print` ندارد (صفر مورد در `app/finance/`).
- پاکت خطا `requestId` دارد و پیام ۴۰۳ فارسی است، نه کد مجوز داخلی.
- رویدادهای ممیزی در `finance_audit_events`: ثبت، تأیید، ابطال، اصلاح، دسترسی به پیوست.
- متن فاکتور یا محتوای فایل در لاگ نوشته نمی‌شود.

---

## ۹. Secret

**هیچ کلید Providerی در این مخزن نیست و نمی‌تواند باشد.**

- دو آداپتر پیاده‌شده اصلاً کلید نمی‌خواهند (مدل محلی).
- پیکربندی Provider از محیط خوانده می‌شود، نه از مخزن
  (`EXTRACTION_PROVIDER`، `backend/devhost/environment.py`).
- `.env` در `.gitignore` است (`.gitignore:2`).
- جست‌وجوی الگوی کلید/توکن در `backend/extraction/`: **هیچ موردی**.

---

## ۱۰. آنچه هنوز تصمیم محصول است

انتخاب نهایی Provider واقعی OCR/Voice فارسی (PRD §۱ آن را تنها Gate باز نامیده) گرفته
نشده. آنچه امروز هست یک خانوادهٔ خودمیزبان پیاده‌شده و آزموده است، نه انتخاب تأییدشده.

مقایسهٔ دو گزینه — تحویل‌دادنی J4 — بدون تعیین گزینهٔ دوم قابل نوشتن نیست و در
`backend/docs/DECISION_PACKS_FA.md (بستهٔ D-4)` به‌صورت بستهٔ تصمیم آماده شده.

---

## ۱۱. بازتولید

```
cd backend
ai-extraction-env/Scripts/python -m pip install -r extraction/requirements-ai.txt
python extraction/scripts/test_ocr.py
```

نسخه‌هایی که واقعاً روی این ماشین اجرا شدند در `backend/extraction/samples/README.md` ثبت
است (Python 3.12.10، paddlepaddle 3.0.0 CPU، paddleocr 3.7.0، openai-whisper 20250625).
یک اجرای end-to-end واقعی در `backend/extraction/test_results/invoice_ocr_result.json` هست.

`ffmpeg` با pip نصب نمی‌شود و Whisper برای هر فرمتی به آن نیاز دارد.
