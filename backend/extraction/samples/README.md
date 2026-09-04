# نمونه‌های آزمون استخراج

**هیچ داده مالی واقعی اینجا نگذارید.** این پوشه برای آزمون محلی است و مسیرش در مخزن دیده
می‌شود؛ یک فاکتور واقعی با نام فروشنده و مبلغ، داده مالی است حتی اگر «فقط برای تست» باشد.
فایل‌های رسانه‌ای با `.gitignore` کنار همین فایل بیرون نگه داشته می‌شوند.

## فایل‌ها را خودتان بگذارید

```
extraction/samples/invoice.jpg     فاکتور فارسی، ساختگی
extraction/samples/voice.mp3       توصیف صوتی فارسی، ساختگی
```

### فاکتور نمونه چه چیزی داشته باشد

```
مقدار و واحد        ۲۰ مترمکعب
قیمت واحد          قیمت واحد 3,200,000 ریال
جمع کل             جمع کل 64,000,000 ریال
تاریخ شمسی          تاریخ 1405/06/12
```

اعداد را با ارقام فارسی **و** انگلیسی بنویسید — هر دو ارزش آزمودن دارند.

### صدای نمونه چه بگوید

> «خرید پانصد کیلوگرم میلگرد چهارده، قیمت واحد هشتصد و پنجاه هزار ریال»

سی ثانیه یا کمتر؛ بلندتر فقط آزمون را کند می‌کند.

## اجرا

```bash
cd backend

ai-extraction-env\Scripts\python extraction\scripts\test_ocr.py extraction\samples\invoice.jpg

ai-extraction-env\Scripts\python extraction\scripts\test_whisper.py extraction\samples\voice.mp3 --model small
```

کدهای خروج: `0` خوانده شد · `1` اجرا شد ولی چیزی نخواند · `2` فایل نامعتبر یا نبود ·
`3` provider اجرا نشد (بسته نصب نیست، ffmpeg نیست، مدل دانلود نشده).

## ffmpeg — نکته‌ای که بیشترین وقت را می‌گیرد

`winget install Gyan.FFmpeg` نصب می‌کند ولی **مسیرش را روی PATH نمی‌گذارد**. آن‌وقت
`shutil.which("ffmpeg")` مقدار `None` می‌دهد و Whisper — که برای **هر** قالبی، حتی WAV، به
ffmpeg شل می‌زند — با `[WinError 2]` از درون مدل شکست می‌خورد؛ خطایی که شبیه فایل صوتی خراب
به نظر می‌رسد. یا این مسیر را به PATH اضافه کنید یا با `--ffmpeg` بدهید:

```
%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg_*\ffmpeg-*-full_build\bin\ffmpeg.exe
```

## نسخه‌هایی که واقعاً روی این ماشین اجرا شدند

| بسته | نسخه |
|---|---|
| Python | 3.12.10 (`ai-extraction-env`) |
| paddlepaddle | 3.0.0 (CPU) |
| paddleocr | 3.7.0 |
| paddlex | 3.7.2 |
| openai-whisper | 20250625 |
| torch | 2.13.0 (CPU) |
| numpy | 2.3.5 |
| opencv-contrib-python | 4.10.0.84 |
| pillow | 12.3.0 |
| ffmpeg-python | 0.2.0 |
| ffmpeg | 9.0.1 (خارج از pip) |

**paddlepaddle 3.3.1 روی Windows/CPU کار نمی‌کند** — پیش از خواندن هر تصویری با
`ConvertPirAttribute2RuntimeAttribute not support` متوقف می‌شود و هیچ‌کدام از
`FLAGS_use_mkldnn=0`، `FLAGS_enable_pir_api=0`، `FLAGS_enable_pir_in_executor=0` دورش
نمی‌زنند. سقف `<3.1` در `requirements-ai.txt` به همین دلیل است.

## یک هشدار دربارهٔ اطمینان Whisper

روی یک تُن خالص بدون هیچ گفتاری، Whisper متن توهمی تولید کرد و اطمینان **۰.۹۱** گزارش داد.
`avg_logprob` روی ورودی غیرگفتاری با اطمینان بالا اشتباه می‌کند. اطمینان Whisper هرگز نباید
معیار پذیرش خودکار باشد.
