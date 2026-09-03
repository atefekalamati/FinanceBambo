# آزمون پذیرش هویت میزبان

**برای تیم Host/Core.** وقتی تابع `identity` را نوشتید، این تست‌ها می‌گویند تمام شده یا نه.

---

## آنچه میزبان می‌دهد — دقیقاً سه چیز

```python
async def identity(request) -> tuple[UUID, UUID, str]:
    ...                                    # ← این بخش مال شماست
    return user_id, organization_id, project_id
```

| مقدار | نوع | قید |
|---|---|---|
| `user_id` | `UUID` | کاربر احرازشده |
| `organization_id` | `UUID` | سازمانِ زمینه درخواست |
| `project_id` | `str` | `^[A-Za-z0-9_-]+$` — UUID نیست |

**در نبود Session معتبر، استثنا بدهید.** هیچ مقدار پیش‌فرضی برنگردانید.

سپس سه خط سیم‌کشی:

```python
application.state.auth_context_provider = CoreAuthContextAssembler(core_conn, identity)
application.state.scope_authorizer      = CoreScopeAuthorizer(core_conn)
application.state.permission_authorizer = CoreRbacPermissionAuthorizer(core_conn)
```

> نقطه‌چین را **پر نکنید مگر با Session واقعی خودتان**. این سند نمونه کوکی یا توکن نمی‌دهد،
> چون قرارداد رسمی BAMBO مکانیزم را عمداً به شما واگذار کرده.

---

## تقسیم مسئولیت

| میزبان تصمیم می‌گیرد | ماژول مالی تصمیم می‌گیرد |
|---|---|
| کوکی یا توکن | عضویت سازمان |
| ذخیره‌سازی Session | عضویت پروژه |
| Middleware یا Dependency | نقش سازمانی |
| چرخه حیات اعتبارنامه | مجوزهای مؤثر |
| ورود و خروج | اعمال چهار دروازه |

---

## اجرای آزمون

```bash
cd backend
python -m unittest tests.test_host_identity_contract -v
```

**۲۰ تست، بدون نیاز به دیتابیس.** فقط هویت جعل می‌شود — بقیه زنجیره، کد واقعی `coreint`
است که SQL واقعی می‌زند.

### شکل ورودی — ۱۰ تست

| تست | چه چیزی را تضمین می‌کند |
|---|---|
| `test_a_valid_identity_produces_a_finance_context` | مسیر موفق |
| `test_the_seam_takes_the_request_and_returns_three_values` | امضای تابع |
| `test_a_missing_identity_is_refused` | هیچ‌کدام از سه مقدار نمی‌تواند `None` باشد |
| `test_a_malformed_user_identifier_is_refused` | UUID نامعتبر رد می‌شود |
| `test_a_malformed_organization_identifier_is_refused` | همان برای سازمان |
| `test_a_project_identifier_outside_the_contract_is_refused` | فاصله، `;`، `'`، `../` رد می‌شوند |
| `test_an_identity_provider_that_raises_fails_closed` | استثنای شما = «Session معتبر نیست» |
| `test_nothing_on_the_request_can_replace_the_host_identity` | Header و Query و Body نمی‌توانند هویت بسازند |
| `test_no_mock_header_exists_in_deployable_code` | `X-Mock-User` در کد قابل‌استقرار نیست |
| `test_the_development_provider_is_not_reachable_from_deployable_code` | `app/` هرگز `devhost` را import نمی‌کند |

### زنجیره مجوزدهی — ۱۰ تست

| تست | چه چیزی را تضمین می‌کند |
|---|---|
| `test_a_member_passes_both_scope_gates` | عضو معتبر عبور می‌کند |
| `test_another_organization_is_refused` | ۴۰۳ |
| `test_another_project_in_the_same_organization_is_refused` | ۴۰۳ |
| `test_a_role_held_in_another_organization_grants_nothing_here` | نشتی بین‌سازمانی |
| `test_org_chief_resolves_from_the_rbac_role_code` | از `user_roles → roles.code` |
| `test_a_role_grant_reaches_the_permission_gate` | اعطای نقش کار می‌کند |
| `test_an_explicit_denial_beats_the_role_grant` | **سلب فردی غالب** |
| `test_issuing_a_report_stays_denied_because_core_has_no_such_permission` | fail-closed |
| `test_the_permission_gate_re_reads_core_rather_than_trusting_the_context` | دو دروازه مستقل |
| `test_the_assembler_has_no_default_identity` | بدون Fallback ناشناس |

---

## معیار پذیرش

```
□ ۲۰ تست بالا سبزند
□ تابع identity شما در نبود Session استثنا می‌دهد
□ هیچ Header یا پارامتری نمی‌تواند جای هویت را بگیرد
□ هیچ کاربر پیش‌فرض یا Admin ثابتی وجود ندارد
□ tests/test_route_authorization.py هنوز سبز است (هر ۵۷ مسیر محافظت‌شده)
```

**اگر هر ۲۰ تا سبز شدند، سمت مالی تمام است.** هیچ تغییری در ماژول مالی لازم نیست.

---

## دو چیزی که این تست‌ها عمداً نمی‌آزمایند

**۱. مکانیزم Session شما.** ماژول مالی نمی‌داند کوکی است یا توکن، و نباید بداند.

**۲. یک پیاده‌سازی ساختگی.** اگر اینجا یک احراز هویت نمونه می‌ساختیم، تست‌ها سبز می‌شدند و
هیچ‌چیز درباره پیاده‌سازی شما نمی‌گفتند.

> یک احراز هویت ساختگی که ۲۰۰ می‌دهد، تا روزی که کسی امتحانش کند، از یک احراز هویت واقعی
> قابل تشخیص نیست.
