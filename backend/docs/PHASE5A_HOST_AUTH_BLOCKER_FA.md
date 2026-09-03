# فاز ۵-الف — متوقف شد: قرارداد Session میزبان عمداً وجود ندارد

**نتیجه:** احراز هویت پیاده **نشد**. هیچ Adapter ساختگی ساخته نشد.
**دلیل:** قرارداد رسمی BAMBO صریحاً می‌گوید این بخش از عمد حذف شده است.

---

## آنچه جست‌وجو شد

| محل | نتیجه |
|---|---|
| `backend/app/` · `backend/coreint/` · `backend/devhost/` · `frontend/src/` | صفر پیاده‌سازی Session |
| کلیدواژه‌ها: `bearer` · `cookie` · `jwt` · `oauth` · `login` · `access_token` · `session_id` | **صفر مورد** |
| پیاده‌سازی‌های `AuthContextProvider.current` | فقط ۳ تا: `CoreAuthContextAssembler`، `StaticAuthContextProvider` (توسعه)، و بدل‌های تست |
| `Sources/BAMBO_FINANCE_INTEGRATION_KIT_v1.1/` | **قرارداد رسمی پیدا شد** — و صریحاً مکانیزم را حذف کرده |

> `E:\bamboo\platform` بررسی نشد و نباید بشود. پیاده‌سازی Pilot، قرارداد ماژول مالی نیست.

---

## آنچه قرارداد رسمی می‌گوید

از `01_PUBLIC_HOST_CONTRACT.md`:

> | Authentication boundary | **server-side opaque session; details are intentionally excluded**; host supplies validated context |

از `04_AUTH_AND_PERMISSION_CONTRACT.md`:

> The host resolves and validates the real opaque session before calling Finance.
> **Session storage, token format, cookie value, lookup logic, and credential flows are
> deliberately absent from this kit.**

> The mock uses `X-Mock-User` only to select synthetic contexts. **That mechanism is
> insecure outside local development and must not be copied into production.**

از `08_INTEGRATION_CHECKLIST.md`:

> - [ ] No dependency on `X-Mock-User` or any mock-only authentication

**این یک شکاف نیست — یک تصمیم است.** میزبان مالک احراز هویت است و مکانیزمش را عمداً از این
Kit بیرون گذاشته. ساختن یکی از سمت ما، حدس‌زدن طراحی امنیتی شخص دیگری است.

---

## آنچه ماژول مالی از قبل دارد

هر چهار قطعه‌ای که قرارداد نام می‌برد، **نوشته و تست‌شده‌اند**:

```text
AuthContextProvider.current(request) -> AuthContext         ✅ CoreAuthContextAssembler
ScopeAuthorizer.require_organization(context, org)          ✅ CoreScopeAuthorizer
ScopeAuthorizer.require_project(context, org, project)      ✅ CoreScopeAuthorizer
PermissionAuthorizer.require(context, permission_code)      ✅ CoreRbacPermissionAuthorizer
```

و چهار دروازه، به همان ترتیبی که قرارداد می‌خواهد:

```
احراز هویت → عضویت سازمان → عضویت پروژه → مجوز مالی
```

| بند قرارداد | وضعیت مالی |
|---|---|
| هر رکورد با هر دو کلید مستأجر فیلتر شود | ✅ تست‌شده روی همه Queryها |
| Body نتواند دامنه را تعیین کند | ✅ تست‌شده |
| مجموعه غیرمجاز ۴۰۳، شیء غیرمجاز ۴۰۴ | ✅ تست‌شده |
| `project_id` با `^[A-Za-z0-9_-]+$` | ✅ در `AuthContext` |
| `organization_id` به‌صورت UUID | ✅ |
| Python 3.12 | ✅ ۶۱۶ تست |
| PostgreSQL 16 و **همچنین** 18 | ✅ هر دو اعتبارسنجی‌شده |
| بدون وابستگی به `X-Mock-User` | ✅ چنین هدری وجود ندارد |

**ماژول مالی از نظر قرارداد کامل است.** تنها چیز غایب، سمت میزبان است.

---

## دقیقاً چه چیزی کم است

یک تابع. همین:

```python
async def identity(request) -> tuple[UUID, UUID, str]:
    """Session معتبرشده میزبان → (user_id, organization_id, project_id)

    اگر Session معتبر نیست، استثنا بدهید. هیچ مقدار پیش‌فرضی برنگردانید.
    """
```

سپس سه خط سیم‌کشی:

```python
application.state.auth_context_provider  = CoreAuthContextAssembler(core_conn, identity)
application.state.scope_authorizer       = CoreScopeAuthorizer(core_conn)
application.state.permission_authorizer  = CoreRbacPermissionAuthorizer(core_conn)
```

`core_conn` یک اتصال psycopg به دیتابیسی است که جدول‌های هسته در آن هستند.

### تیم میزبان باید این‌ها را روشن کند

```
□ Session کوکی‌محور است یا توکن‌محور؟
□ شناسه کاربر UUID است؟
□ organization_id از Session می‌آید یا از مسیر درخواست؟
□ هویت چطور به FastAPI می‌رسد — Middleware؟ Dependency؟ request.state؟
□ رفتار در نبود Session معتبر چیست — استثنا؟ کدام کد وضعیت؟
```

**ماژول مالی هیچ‌کدام را حدس نمی‌زند.**

---

## چرا اینجا متوقف شدیم

سه راهی که می‌شد «پیاده کرد» و هر سه رد شدند:

| میان‌بر | چرا رد شد |
|---|---|
| استفاده از `StaticAuthContextProvider` توسعه | یک هویت ثابت با همه مجوزها. Checklist رسمی صریحاً منعش می‌کند |
| کپی مکانیزم `X-Mock-User` | خودِ Kit می‌گوید «insecure outside local development» |
| نگاه‌کردن به پیاده‌سازی Pilot | خارج از محدوده، و قرارداد ماژول مالی نیست |

> هر سه یک Adapter تولید می‌کردند که **کار می‌کند** — و دقیقاً به همین دلیل خطرناک‌اند:
> یک احراز هویت ساختگی که پاسخ ۲۰۰ می‌دهد، تا روزی که کسی امتحانش کند از یک احراز هویت
> واقعی قابل تشخیص نیست.

---

## یافته جانبی — تأییدکننده موضع فعلی ما درباره `finance_report.issue`

Kit رسمی، `finance_report.issue` را در فهرست **PROPOSED** گذاشته، نه EXISTING:

> ## EXISTING permissions (verified)
> `finance.view` · `finance.edit` · `finance_report.view` · `finance_report.export`

و در ماتریس اقدامات:

> | Issue immutable report | **no existing decision** | `finance_report.issue` |

**«no existing decision»** یعنی هیچ Fallbackی تأیید نشده است. رفتار fail-closed فعلی ما
دقیقاً همان چیزی است که قرارداد می‌خواهد — و نگاشت به `export` یا `edit` صریحاً بی‌مجوز
است.

> Kit اضافه می‌کند: اگر روزی نگاشتی انجام شود، «the mapping must be explicit, reviewed, and
> tested» — نه بی‌صدا.

---

## قدم بعدی

**فاز ۵-الف تا رسیدن پاسخ میزبان متوقف است.**

`HANDOFF_HOST_AUTH_FA.md` را برای تیم Host/Core بفرستید. این سند همان درخواست است، با
معیار پذیرش.

وقتی تابع `identity` رسید، پیاده‌سازی **یک روز کار است، نه یک فاز** — چون بقیه‌اش از قبل
نوشته و تست شده.
