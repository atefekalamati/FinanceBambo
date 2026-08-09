# اسکلت Backend مالی BAMBO

این پوشه اسکلت مرحله دوم ماژول مالی است. Adapterهای واقعی Auth، Scope، File و Progress باید توسط تیم اصلی BAMBO تزریق شوند. هیچ Mock Header یا Endpoint احراز هویت در این برنامه وجود ندارد.

## اجرای تست اسکلت

از ریشه Repository:

```powershell
python -m unittest discover -s backend/tests -v
```

نسخه هدف Python برابر 3.12 است. وابستگی‌های مجاز این مرحله در `backend/requirements.txt` ثبت شده‌اند.

## Migration مالی

Migration پیشنهادی مستقل در `backend/migrations/0001_finance_core.up.sql` و Rollback آن در `backend/migrations/0001_finance_core.down.sql` قرار دارد. اجرای نهایی Migration فقط توسط تیم اصلی BAMBO و پس از تهیه Backup و Review مجاز است.

تست ساختاری Migration همراه کل Suite با همان Command بالا اجرا می‌شود. آزمون اجرایی باید جداگانه روی PostgreSQL 16 و 18، ابتدا روی دیتابیس خالی، سپس اجرای مجدد Up و در پایان Down انجام شود. اطلاعات اتصال باید از محیط اجرا تأمین شود و نباید در Repository ثبت گردد.
