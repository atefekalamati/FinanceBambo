# درخواست از تیم میزبان — هویت احرازشده

**مالک:** تیم Host/Core · **اولویت:** بحرانی — بدون این، هیچ مسیری در Production آزمودنی نیست

---

## آنچه لازم داریم — کوچک‌تر از آنچه به‌نظر می‌رسد

میزبان فقط **سه چیز** می‌دهد:

```
user_id           ← از Session احرازشده میزبان
organization_id   ← زمینه درخواست
project_id        ← از مسیر درخواست
```

**همین.** بقیه را ماژول مالی از جدول‌های هسته درمی‌آورد.

> **ماژول مالی احراز هویت نمی‌سازد و نباید بسازد.** ما قراردادی برای Session با میزبان
> نداریم، و ساختن یکی یعنی حدس‌زدن طراحی شخص دیگری.

---

## مرز اعتماد

> ### ورودی کلاینت، مجوز نیست
>
> `organization_id` و `project_id` از درخواست می‌آیند. ماژول مالی **هرگز** آن‌ها را
> به‌عنوان اجازه نمی‌پذیرد — فقط به‌عنوان «کاربر چه چیزی را درخواست کرده».
>
> عضویت و مجوز **مستقلاً** از هسته خوانده می‌شوند. اگر کاربر سازمانی را نام ببرد که عضوش
> نیست، ۴۰۳ می‌گیرد.

چهار دروازه، همیشه به این ترتیب:

```
احراز هویت → دامنه سازمان → دامنه پروژه → مجوز مالی
```

ترتیب مهم است: بررسی مجوز پیش از بررسی دامنه، «ممنوع» می‌گفت برای پروژه‌ای که کاربر حتی
نباید بداند وجود دارد.

---

## آنچه ماژول مالی خودش درمی‌آورد

| پرسش | منبع تأییدشده |
|---|---|
| عضو سازمان است؟ | `organization_memberships` |
| عضو پروژه است؟ | `project_memberships` + `JOIN projects` |
| نقش سازمانی چیست؟ | `user_roles` → `roles.code` |
| چه مجوزهایی دارد؟ | `user_roles` → `role_permissions` → `permissions` |
| سلب فردی؟ | `user_permission_overrides` |

> ### دو نکته که اشتباه‌شان گران است
>
> **۱. RBAC را از `organization_memberships.role` نگیرید.** آن یک واژگان درشت جداست
> (`org_admin`, `editor`, `viewer`, …). نقش RBAC — همانی که `org_chief` در آن است — در
> `user_roles → roles.code` است.
>
> **۲. `organization_members` و `project_members` را نخوانید.** شبیه‌اند ولی `user_id` در
> آن‌ها اختیاری است، یعنی می‌توانند کسی را توصیف کنند که حساب کاربری ندارد. آن‌ها دفترچه
> تماس‌اند، نه منبع مجوز.

**`JOIN projects` اختیاری نیست:** `project_memberships` سازمان خودش را ثبت نمی‌کند. بدون آن
JOIN، عضویت در پروژه P درخواستی را که سازمان B را نام می‌برد برآورده می‌کند.

---

## نمونه یکپارچه‌سازی

از رابط موجود استفاده کنید — چیزی ساخته نمی‌شود:

```python
from coreint.security import (CoreAuthContextAssembler, CoreScopeAuthorizer,
                              CoreRbacPermissionAuthorizer)

async def identity(request):
    """تنها چیزی که میزبان باید بنویسد.

    Session خودتان را بخوانید و سه مقدار برگردانید. اگر Session معتبر نیست،
    استثنا بدهید — ماژول مالی هویت نمی‌سازد.
    """
    session = <your_session_lookup>(request)
    return session.user_id, session.organization_id, request.path_params["projectId"]

application.state.auth_context_provider  = CoreAuthContextAssembler(core_conn, identity)
application.state.scope_authorizer       = CoreScopeAuthorizer(core_conn)
application.state.permission_authorizer  = CoreRbacPermissionAuthorizer(core_conn)
```

`core_conn` یک اتصال psycopg به دیتابیسی است که جدول‌های هسته در آن هستند.

سیم‌کشی کامل (۱۴ کلید) در `CORE_HOST_WIRING_FA.md`.

---

## `AuthContext` که ساخته می‌شود

ماژول مالی خودش می‌سازدش. برای اطلاع شما:

| فیلد | اعتبارسنجی |
|---|---|
| `userId` · `organizationId` | UUID الزامی |
| `projectId` | `^[A-Za-z0-9_-]+$` |
| `organizationRole` | غیرخالی — `org_chief` بدون ترجمه رد می‌شود |
| `projectRole` | غیرخالی |
| `permissionCodes` | `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`، یکتا |
| `timezone` | `Asia/Tehran` |

> **`org_chief` را ترجمه نکنید.** این کد در `roles` هسته وجود دارد و سیاست ویرایش تنظیمات
> دقیقاً روی همین رشته حساب می‌کند. لایه ترجمه یعنی دو واژگان که از هم فاصله می‌گیرند.

---

## معیار پذیرش

```
□ ۱. هویت کاربر احرازشده به ماژول مالی می‌رسد
□ ۲. organization_id و project_id به ماژول مالی می‌رسند
□ ۳. org_chief درست resolve می‌شود (از user_roles → roles.code)
□ ۴. دسترسی بین‌سازمانی ۴۰۳ می‌گیرد
□ ۵. دسترسی بین‌پروژه‌ای ۴۰۳ می‌گیرد
□ ۶. سلب فردی بر اعطای نقش غلبه می‌کند
□ ۷. هر ۵۷ مسیر محافظت‌شده می‌مانند
```

بند ۷ را ما تست می‌کنیم (`tests/test_route_authorization.py`) — شما فقط باید سه Adapter را
سیم‌کشی کنید.

---

## آنچه تیم میزبان باید فراهم کند

```
□ تابع identity(request) که سه مقدار برمی‌گرداند
□ اتصال psycopg به دیتابیس جدول‌های هسته
□ سه کلید امنیتی روی application.state
□ یازده سرویس دامنه (فهرست در CORE_HOST_WIRING_FA.md)
□ نقش دیتابیسِ اجرا که حق CREATE ندارد
```
