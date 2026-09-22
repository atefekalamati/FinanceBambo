# -*- coding: utf-8 -*-
r"""Regenerate `docs/DATABASE_SCHEMA_FA.md` from a live database and this repository.

    python -m scripts.generate_schema_doc --dsn postgresql://...
    python -m scripts.generate_schema_doc            # uses FINANCE_DEV_DSN

WHY A GENERATOR AND NOT A HAND-WRITTEN DOCUMENT

A schema reference that is typed by hand is wrong the day after the next migration, and
wrong quietly: nothing fails, the column simply is not there any more and the document
keeps describing it. So everything a database can state about itself -- tables, columns,
types, nullability, defaults, foreign keys, CHECK vocabularies -- is READ, every time.

What a database cannot state is what a column MEANS. That part lives in `MEANING` below
and is the only part a person edits. When the two disagree the database wins: a column
dropped from the schema simply stops being printed, and its entry here becomes dead
weight rather than a false claim.

WHAT IT REFUSES TO DO

Guess. A column that neither the database nor `MEANING` describes is printed as
«توضیح ثبت‌نشده» and counted in the coverage table at the end of the document, so the gap
is visible instead of being filled with a plausible sentence. The same applies where the
meaning is genuinely unknown: `msp_tasks.number1` is populated on 16,224 rows and nothing
in this repository reads it, and the document says exactly that.

READ ONLY. It opens one connection, runs catalogue queries, and writes one file.
"""

import argparse
import ast
import collections
import io
import json
import re
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DOC_PATH = BACKEND_ROOT / "docs" / "DATABASE_SCHEMA_FA.md"
ROUTER = BACKEND_ROOT / "app" / "finance" / "router.py"
HOST = BACKEND_ROOT / "devhost" / "app.py"
FINANCE_PACKAGE = BACKEND_ROOT / "app" / "finance"
BASE_PATH = "/api/projects/{projectId}/finance"

# --------------------------------------------------------------------------- catalogue

#: One query for the whole schema. The foreign key picks the referenced column at the
#: SAME position in the key -- a composite `(organization_id, project_id)` reported by
#: its first column alone would point every member at `organization_id`, which reads as
#: a fact and is not one. Each CHECK carries the columns it actually governs, for the
#: same reason: a two-column rule mentioning a literal must not be printed as one
#: column's vocabulary.
SCHEMA_SQL = """
SELECT json_agg(t ORDER BY t->>'table')::text FROM (
  SELECT json_build_object(
    'table', c.relname,
    'rows', COALESCE(s.n_live_tup, 0),
    'comment', obj_description(c.oid),
    'columns', (SELECT json_agg(json_build_object(
        'name', a.attname,
        'type', format_type(a.atttypid, a.atttypmod),
        'notnull', a.attnotnull,
        'default', pg_get_expr(ad.adbin, ad.adrelid),
        'comment', col_description(c.oid, a.attnum),
        'fk', (SELECT cl2.relname || '.' || a2.attname
               FROM pg_constraint k
               CROSS JOIN LATERAL generate_subscripts(k.conkey, 1) AS p(i)
               JOIN pg_class cl2 ON cl2.oid = k.confrelid
               JOIN pg_attribute a2 ON a2.attrelid = k.confrelid
                                   AND a2.attnum = k.confkey[p.i]
               WHERE k.conrelid = c.oid AND k.contype = 'f'
                 AND k.conkey[p.i] = a.attnum
               LIMIT 1)
      ) ORDER BY a.attnum)
      FROM pg_attribute a
      LEFT JOIN pg_attrdef ad ON ad.adrelid = c.oid AND ad.adnum = a.attnum
      WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped),
    'checks', (SELECT json_agg(json_build_object(
        'def', pg_get_constraintdef(k.oid),
        'cols', (SELECT json_agg(a3.attname) FROM unnest(k.conkey) AS ck(n)
                 JOIN pg_attribute a3 ON a3.attrelid = c.oid AND a3.attnum = ck.n)))
      FROM pg_constraint k WHERE k.conrelid = c.oid AND k.contype = 'c')
  ) AS t
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
  LEFT JOIN pg_stat_user_tables s ON s.relid = c.oid
  WHERE c.relkind = 'r'
) q
"""


def read_schema(dsn):
    import psycopg
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute(SCHEMA_SQL)
            tables = json.loads(cursor.fetchone()[0])
            cursor.execute("SELECT version_num FROM finance_alembic_version")
            row = cursor.fetchone()
            cursor.execute("SELECT current_database()")
            database = cursor.fetchone()[0]
    return {t["table"]: t for t in tables}, (row[0] if row else "—"), database


# --------------------------------------------------------------------------- the API

def read_api():
    """Endpoints, and the tables the service behind each one can reach.

    The route comes from the router's decorators. The tables come from the repository
    that `devhost/app.py` injects into the service the endpoint calls -- which makes the
    mapping exact at SERVICE granularity and no finer. Matching on bare method names was
    tried first and is worse than useless: `settings`, `get` and `list` exist in several
    repositories, so every endpoint appeared to touch every table.
    """
    host_src = HOST.read_text(encoding="utf-8")
    host_tree = ast.parse(host_src)
    modules = {str(p.relative_to(BACKEND_ROOT)).replace("\\", "/"): p
               for p in FINANCE_PACKAGE.rglob("*.py")}

    class_module = {}
    for node in ast.walk(host_tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            candidate = "app/" + node.module.replace("app.", "").replace(".", "/") + ".py"
            if candidate in modules:
                for alias in node.names:
                    class_module[alias.name] = modules[candidate]

    def sql_tables(path, names):
        source = path.read_text(encoding="utf-8")
        alternation = "|".join(sorted(names, key=len, reverse=True))
        reads = set(re.findall(r"(?:FROM|JOIN)\s+(%s)\b" % alternation, source, re.I))
        writes = set(re.findall(r"(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(%s)\b"
                                % alternation, source, re.I))
        return reads, writes

    def build(names):
        alias_uses, attribute_uses = {}, collections.defaultdict(set)
        for node in ast.walk(host_tree):
            if not isinstance(node, ast.Assign):
                continue
            used = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
            for target in node.targets:
                if (isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Attribute)
                        and target.value.attr == "state"):
                    attribute_uses[target.attr] |= used
                elif isinstance(target, ast.Name):
                    alias_uses[target.id] = used

        per_attribute = {}
        for attribute, used in attribute_uses.items():
            used = set(used)
            for name in list(used):                       # `invoice_service = Service(...)`
                used |= alias_uses.get(name, set())
            reads, writes = set(), set()
            for name in used:
                module = class_module.get(name)
                if module is not None:
                    module_reads, module_writes = sql_tables(module, names)
                    reads |= module_reads
                    writes |= module_writes
            per_attribute[attribute] = (reads, writes)
        return per_attribute

    return build


def endpoints_of(per_attribute):
    source = ROUTER.read_text(encoding="utf-8")
    found = []
    for node in ast.parse(source).body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        routes = [d for d in node.decorator_list
                  if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                  and isinstance(d.func.value, ast.Name) and d.func.value.id == "router"
                  and d.args and isinstance(d.args[0], ast.Constant)]
        if not routes:
            continue
        attributes = {n.attr for n in ast.walk(node)
                      if isinstance(n, ast.Attribute)
                      and isinstance(n.value, ast.Attribute) and n.value.attr == "state"}
        reads, writes = set(), set()
        for attribute in attributes:
            attribute_reads, attribute_writes = per_attribute.get(attribute, (set(), set()))
            reads |= attribute_reads
            writes |= attribute_writes
        for route in routes:
            found.append({"verb": route.func.attr.upper(), "path": route.args[0].value,
                          "services": sorted(attributes),
                          "tables": sorted(reads | writes)})
    return found


# --------------------------------------------------------------------------- meaning
#
# Everything below this line is written by a person. A column the database describes with
# its own COMMENT wins over it; a column neither covers is printed as a gap.

#: Column names that mean the same thing wherever they appear.
GENERIC = {
    "id": "کلید اصلی سطر",
    "organization_id": "سازمان مالک سطر؛ مرز جداسازی داده بین سازمان‌ها",
    "project_id": "پروژه‌ای که سطر به آن تعلق دارد",
    "created_at": "زمان ساخت سطر",
    "updated_at": "زمان آخرین تغییر سطر",
    "created_by": "کاربری که سطر را ساخته",
    "updated_by": "کاربری که آخرین تغییر را زده",
    "deleted_at": "زمان حذف نرم؛ خالی یعنی سطر فعال است",
    "version": "شمارهٔ نسخه؛ با هر بازنویسی یک واحد بالا می‌رود",
    "superseded_at": "زمان جایگزین‌شدن با نسخهٔ جدیدتر؛ خالی یعنی نسخهٔ جاری",
    "superseded_by": "سطری که جای این را گرفت",
    "effective_from": "تاریخی که این مقدار از آن به بعد معتبر است",
    "effective_to": "تاریخی که اعتبار این مقدار تا آن است",
    "reason": "دلیل ثبت‌شده برای این تغییر",
    "notes": "یادداشت آزاد",
    "metadata": "دادهٔ جانبی ساخت‌نیافته (JSON)",
    "status": "وضعیت سطر",
    "label": "برچسب نمایشی",
    "name": "نام",
    "code": "کد",
    "title": "عنوان",
    "description": "شرح",
    "user_id": "کاربر",
    "sort_order": "ترتیب نمایش",
    "is_active": "فعال بودن سطر",
    "active": "فعال بودن سطر",
    "source_sha256": "اثر انگشت SHA-256 فایل مبدأ؛ همان فایل دوبار وارد نمی‌شود",
    "quantity": "مقدار",
    "unit": "واحد",
    "currency": "واحد پول",
    "category": "دسته‌بندی",
    "confidence": "میزان اطمینان (۰ تا ۱)",
    "warnings": "هشدارهای ثبت‌شده",
}

#: Name-suffix rules, applied longest-first so `_size_bytes` beats `_bytes` and
#: `_rel_path` beats `_path`. Without that ordering the shorter rule claims the column
#: and produces a description that is nearly right -- worse than one that is obviously
#: missing, because nobody goes back to check it.
SUFFIX = [
    ("_id", "شناسهٔ %s"), ("_at", "زمانِ %s"), ("_by", "کاربرِ %s"),
    ("_irr", "مبلغ %s به ریال"), ("_count", "تعداد %s"),
    ("_uid", "شناسهٔ %s در فایل مبدأ"), ("_percent", "درصد %s"),
    ("_json", "دادهٔ %s به صورت JSON"), ("_url", "نشانی %s"),
    ("_sha256", "اثرانگشت SHA-256 %s"),
    ("_hash", "درهم‌سازی %s (خود مقدار ذخیره نمی‌شود)"),
    ("_rel_path", "مسیر نسبی فایل %s"), ("_path", "مسیر فایل %s"),
    ("_jalali", "تاریخ %s، شمسی"), ("_gregorian", "تاریخ %s، میلادی"),
    ("_size_bytes", "حجم %s به بایت"), ("_bytes", "حجم %s به بایت"),
    ("_duration_ms", "مدت %s به میلی‌ثانیه"), ("_mime", "نوع MIME فایل %s"),
    ("_rial", "مبلغ %s به ریال"), ("_cost", "هزینهٔ %s"),
    ("_work", "کارِ %s (نفر-ساعت)"), ("_progress", "پیشرفت %s"),
    ("_percent_complete", "درصد تکمیل %s"), ("_quantity", "مقدار %s"),
    ("_unit", "واحدِ %s"), ("_value", "مقدار %s"), ("_reason", "دلیل %s"),
    ("_reason_code", "کد دلیل %s"), ("_label", "برچسب %s"),
    ("_name_safe", "نام %s، پاک‌سازی‌شده برای ذخیره روی دیسک"), ("_name", "نام %s"),
    ("_type", "نوع %s"), ("_kind", "نوع %s"), ("_source", "منبعِ %s"),
    ("_state", "وضعیت %s"), ("_status", "وضعیت %s"), ("_code", "کد %s"),
    ("_number", "شمارهٔ %s"), ("_limit", "سقف %s"), ("_ids", "فهرست شناسه‌های %s"),
    ("_values", "مقادیر %s"), ("_errors", "خطاهای %s"), ("_warnings", "هشدارهای %s"),
    ("_report", "گزارش %s"), ("_items", "تعداد یا فهرست %s"), ("_date", "تاریخ %s"),
    ("_token", "توکن %s"), ("_role", "نقشِ %s"), ("_stage", "مرحلهٔ %s"),
    ("_detail", "جزئیات %s"), ("_summary", "خلاصهٔ %s"), ("_verdict", "حکمِ %s"),
    ("_engine", "موتورِ %s"), ("_method", "روشِ %s"), ("_mode", "حالتِ %s"),
    ("_basis", "مبنای %s"), ("_definition", "تعریف %s"), ("_index", "نمایهٔ %s"),
    ("_phone", "شمارهٔ تلفن %s"), ("_email", "رایانامهٔ %s"), ("_address", "نشانی %s"),
    ("_sign", "علامت %s (مثبت یا منفی)"), ("_payload", "بارِ دادهٔ %s"),
    ("_metrics", "سنجه‌های %s"), ("_conflicts", "تعارض‌های %s"), ("_units", "واحدهای %s"),
    ("_stride", "گامِ %s"), ("_fps", "فریم بر ثانیهٔ %s"),
    ("_m2", "%s به متر مربع"), ("_m3", "%s به متر مکعب"), ("_sqm", "%s به متر مربع"),
]
SUFFIX.sort(key=lambda pair: -len(pair[0]))

#: What each table is FOR, in one line. A table missing from here is reported as a
#: gap rather than described from its name.
PURPOSE = {
    'audit_logs':
        'لاگ حسابرسی عمومی سامانه.',
    'capture_path_points':
        'نقاط مسیر یک جلسهٔ برداشت.',
    'capture_sessions':
        'جلسات برداشت میدانی (عکس و پانوراما).',
    'estimate_line_source_completions':
        'درصد تکمیل هر سطر برآورد، به تفکیک منبعِ مبدأ.',
    'estimate_lines':
        'سطرهای برآورد پروژه: چه کاری، چه مقدار، با چه واحدی.',
    'estimate_revisions':
        'بازنگری دستی یک سطر برآورد؛ مقدار دستی بر مقدار محاسبه\u200cشده اولویت دارد.',
    'extraction_drafts':
        'پیش\u200cنویس استخراج هوش مصنوعی از پیوست؛ تا تأیید نشود هیچ اثر مالی ندارد.',
    'field_note_activities':
        'رویدادهای یک یادداشت کارگاهی.',
    'field_note_attachments':
        'پیوست\u200cهای یادداشت کارگاهی.',
    'field_note_comments':
        'نظرات روی یادداشت کارگاهی.',
    'field_note_statuses':
        'وضعیت\u200cهای ممکن یادداشت کارگاهی.',
    'field_note_tag_links':
        'اتصال یادداشت به برچسب.',
    'field_note_tags':
        'برچسب\u200cهای یادداشت کارگاهی.',
    'field_notes':
        'یادداشت\u200cهای کارگاهی.',
    'finance_alembic_version':
        'شمارهٔ مهاجرت جاری دیتابیس مالی.',
    'finance_attachments':
        'فایل\u200cهای پیوست مالی (تصویر فاکتور، صوت، سند).',
    'finance_audit_events':
        'رویدادهای حسابرسی بخش مالی؛ فقط\u200cافزودنی.',
    'finance_import_batches':
        'دسته\u200cهای واردات داده به بخش مالی.',
    'finance_invoice_counters':
        'شمارندهٔ شمارهٔ فاکتور برای هر پروژه.',
    'finance_item_price_mapping_components':
        'اجزای قیمت یک سطر، وقتی از چند مصالح ساخته می\u200cشود.',
    'finance_item_price_mappings':
        'کدام آگهی بازار، کدام سطر برآورد را قیمت می\u200cدهد.',
    'finance_mpp_currency_decisions':
        'تصمیم «تومان یا ریال» برای هر فایل MPP، همراه با شواهدی که تصمیم بر آن استوار است.',
    'finance_mpp_rows':
        'خوانشِ مالیِ فایل MPP: هر سطر یک تخصیص با مقدار، واحد و هزینه. منبعی که «موارد و برآوردها» از آن تغذیه می\u200cشود.',
    'finance_mpp_source_versions':
        'نسخهٔ فایل MPP که سمت مالی به آن قفل شده؛ در هر لحظه فقط یکی «زنده» است.',
    'finance_price_categories':
        'دسته\u200cبندی\u200cهای قیمت که در سطح سازمان یا پروژه تعریف شده\u200cاند.',
    'finance_project_settings':
        'تنظیمات مالی پروژه، به\u200cصورت تاریخچهٔ فقط\u200cافزودنی.',
    'finance_resources':
        'منابع مالی پروژه (مصالح، نیرو، تجهیزات) با واحد پایه.',
    'finance_task_resource_map':
        'پل بین تسک MPP و منبع مالی.',
    'finance_unit_conversion_issues':
        'تبدیل\u200cهایی که قانون ندارند؛ ثبتِ پرسشِ بی\u200cپاسخ به\u200cجای حدس\u200cزدن.',
    'finance_unit_conversion_rules':
        'قانون تبدیل واحد با دامنه و اولویت؛ مثلاً «کیلوگرم به شاخه» برای یک پروژه.',
    'floors':
        'طبقات ساختمان.',
    'invoice_lines':
        'سطرهای هر فاکتور.',
    'invoices':
        'فاکتورها.',
    'material_unit_settings':
        'واحد نمایشی انتخاب\u200cشده برای هر دستهٔ مصالح.',
    'media_files':
        'فایل\u200cهای رسانه\u200cای.',
    'message_threads':
        'رشته\u200cهای گفت\u200cوگو.',
    'messages':
        'پیام\u200cها.',
    'msp_baseline_revisions':
        'بازنگری\u200cهای خط مبنا (baseline) برنامه.',
    'msp_edit_sessions':
        'جلسهٔ ویرایش برنامه؛ تغییرات پیش از اعمال اینجا جمع می\u200cشود.',
    'msp_file_versions':
        'فایل\u200cهای MPP بارگذاری\u200cشده و نسخه\u200cبندی آن\u200cها.',
    'msp_reporting_calendars':
        'تقویم گزارش\u200cدهی پروژه.',
    'msp_reporting_periods':
        'دوره\u200cهای گزارش\u200cدهی که پیشرفت در آن\u200cها ثبت می\u200cشود.',
    'msp_resource_assignments':
        'تخصیص منبع به تسک. مقدار و هزینه در سطح همین تخصیص معنا دارد، نه تسک.',
    'msp_resources':
        'منابع فایل MPP: نیروی انسانی، ماشین\u200cآلات و مصالح، با نرخ و واحد.',
    'msp_snapshots':
        'هر بار خواندن یک فایل MPP یک snapshot می\u200cسازد؛ مرجع نسخه\u200cای برنامه.',
    'msp_tasks':
        'فعالیت\u200cهای فایل MS Project؛ هر سطر یک تسک با تاریخ، مدت و جایگاه WBS.',
    'msp_voice_report_audio':
        'فایل صوتی خام هر گزارش صوتی.',
    'msp_voice_reports':
        'گزارش پیشرفت صوتی ثبت\u200cشده در کارگاه.',
    'note_activities':
        'رویدادهای یادداشت عمومی.',
    'note_tags':
        'برچسب\u200cهای یادداشت عمومی.',
    'notifications':
        'اعلان\u200cها.',
    'organization_members':
        'عضویت کاربر در سازمان (جدول قدیمی\u200cتر، ستون\u200cهای بیشتر).',
    'organization_memberships':
        'عضویت کاربر در سازمان.',
    'organizations':
        'سازمان\u200cها.',
    'otp_codes':
        'کدهای یک\u200cبارمصرف ورود.',
    'panoramas':
        'تصاویر پانوراما.',
    'permissions':
        'مجوزهای قابل\u200cاعطا.',
    'price_collection_runs':
        'هر بار اجرای ایمپورت قیمت، با آمار و وضعیت پایانی.',
    'price_collection_schedules':
        'زمان\u200cبندی اجرای خودکار ایمپورت قیمت.',
    'price_observations':
        'قیمت\u200cهای واردشده از گوگل\u200cشیت. هر ردیفِ شیت یک مشاهده؛ جدول اصلی قیمت بازار.',
    'price_providers':
        'تأمین\u200cکننده یا منبع قیمت.',
    'price_resolution_policies':
        'سیاست انتخاب قیمت وقتی چند مشاهده برای یک کالا وجود دارد.',
    'price_versions':
        'قیمت\u200cهای دستیِ نسخه\u200cدار برای منابع مالی — جدا از قیمت\u200cهای گوگل\u200cشیت.',
    'progress_overrides':
        'اصلاح دستی پیشرفت یک تخصیص.',
    'progress_snapshot_refs':
        'ارجاع به snapshot پیشرفتی که گزارش بر آن بنا شده.',
    'project_members':
        'عضویت کاربر در پروژه (جدول قدیمی\u200cتر).',
    'project_memberships':
        'عضویت کاربر در پروژه.',
    'project_sequences':
        'شمارنده برای تولید کدهای ترتیبی پروژه.',
    'projects':
        'پروژه\u200cها.',
    'provider_item_labels':
        'نام\u200cها و مشخصات جایگزین یک کالا، به\u200cصورت تاریخچه\u200cدار.',
    'provider_item_unit_factors':
        'ضریب تبدیل واحد مخصوص یک کالای مشخص؛ دقیق\u200cترین لایهٔ تبدیل.',
    'provider_items':
        'فهرست کالاهای هر تأمین\u200cکننده؛ هویتی که قیمت به آن می\u200cچسبد.',
    'provider_resource_mappings':
        'نگاشت کالای تأمین\u200cکننده به منبع مالی.',
    'report_snapshots':
        'گزارش\u200cهای ذخیره\u200cشده؛ عددِ لحظهٔ گرفتن گزارش را نگه می\u200cدارد.',
    'role_permissions':
        'کدام نقش کدام مجوز را دارد.',
    'roles':
        'نقش\u200cها.',
    'sessions':
        'نشست\u200cهای ورود.',
    'sheets':
        'شیت\u200cها و نقشه\u200cها.',
    'tags':
        'برچسب\u200cهای عمومی سامانه.',
    'unit_conversions':
        'تبدیل واحد عمومی پروژه.',
    'user_permission_overrides':
        'استثناء مجوز در سطح یک کاربر.',
    'user_roles':
        'کدام کاربر کدام نقش را دارد.',
    'users':
        'کاربران.',
    'zones':
        'زون\u200cهای هر طبقه.',
}

#: What a particular column of a particular table holds, where the name alone does
#: not say it or where saying it plainly is worth the line.
MEANING = {
    # ---- audit_logs
    ('audit_logs', 'action'):
        'کاری که ثبت شده',
    ('audit_logs', 'meta'):
        'دادهٔ جانبی رویداد',
    # ---- capture_path_points
    ('capture_path_points', 'x'):
        'مختصات X نقطه',
    ('capture_path_points', 'y'):
        'مختصات Y نقطه',
    ('capture_path_points', 'yaw'):
        'زاویهٔ چرخش افقی در این نقطه',
    # ---- estimate_line_source_completions
    ('estimate_line_source_completions', 'basis'):
        'مبنایی که درصد تکمیل بر آن حساب شده',
    # ---- estimate_lines
    ('estimate_lines', 'source'):
        'سطر از کجا آمده — در دادهٔ فعلی: progress_feed یا manual_entry',
    # ---- estimate_revisions
    ('estimate_revisions', 'revision'):
        'شمارهٔ بازنگری',
    # ---- extraction_drafts
    ('extraction_drafts', 'attachment_id'):
        'پیوستی که از آن استخراج شده',
    ('extraction_drafts', 'confirmed_fields'):
        'مقادیری که انسان تأیید کرده',
    ('extraction_drafts', 'extracted_fields'):
        'فیلدهای استخراج\u200cشده (JSONB: آرایه\u200cای از key / extractedValue / confidence / editedByUser / confirmedValue) — افزودن فیلد تازه مهاجرت نمی\u200cخواهد',
    ('extraction_drafts', 'financial_effect_irr'):
        'اثر مالی پیش\u200cنویس؛ CHECK آن را صفر نگه می\u200cدارد تا پیش\u200cنویس هرگز پول جابه\u200cجا نکند',
    ('extraction_drafts', 'provider_adapter'):
        'کدام مسیر استخراج این سطر را ساخته (تصویر یا صوت)',
    ('extraction_drafts', 'review_status'):
        'وضعیت بازبینی انسانی',
    # ---- field_note_activities
    ('field_note_activities', 'action'):
        'کاری که روی یادداشت انجام شده',
    ('field_note_activities', 'meta'):
        'دادهٔ جانبی رویداد',
    # ---- field_note_attachments
    ('field_note_attachments', 'mime'):
        'نوع MIME پیوست',
    # ---- field_note_comments
    ('field_note_comments', 'body'):
        'متن نظر',
    # ---- field_note_statuses
    ('field_note_statuses', 'color'):
        'رنگ نمایش وضعیت',
    ('field_note_statuses', 'is_closed_state'):
        'این وضعیت، وضعیتِ بسته\u200cشده است',
    ('field_note_statuses', 'label_fa'):
        'برچسب فارسی وضعیت',
    ('field_note_statuses', 'order'):
        'ترتیب نمایش',
    # ---- field_note_tags
    ('field_note_tags', 'label_fa'):
        'برچسب فارسی',
    ('field_note_tags', 'order'):
        'ترتیب نمایش',
    # ---- field_notes
    ('field_notes', 'context'):
        'زمینهٔ یادداشت',
    ('field_notes', 'is_closed'):
        'یادداشت بسته شده است',
    ('field_notes', 'x'):
        'مختصات X یادداشت روی پلان',
    ('field_notes', 'y'):
        'مختصات Y یادداشت روی پلان',
    # ---- finance_alembic_version
    ('finance_alembic_version', 'version_num'):
        'شمارهٔ مهاجرت جاری؛ تنها ستون و تنها سطر این جدول',
    # ---- finance_attachments
    ('finance_attachments', 'logical_type'):
        'نقش منطقی فایل (فاکتور، صوت، سند)',
    ('finance_attachments', 'mime_type'):
        'نوع MIME فایل',
    ('finance_attachments', 'original_name_safe'):
        'نام اصلی فایل، پاک\u200cسازی\u200cشده',
    ('finance_attachments', 'processing_status'):
        'وضعیت پردازش فایل',
    ('finance_attachments', 'sha256'):
        'اثرانگشت فایل؛ فایل تکراری دوبار ذخیره نمی\u200cشود',
    ('finance_attachments', 'storage_key'):
        'کلید فایل در فضای ذخیره\u200cسازی',
    ('finance_attachments', 'stored_name'):
        'نامی که فایل با آن ذخیره شده',
    # ---- finance_audit_events
    ('finance_audit_events', 'action'):
        'کاری که انجام شده',
    ('finance_audit_events', 'after_values'):
        'مقادیر پس از تغییر',
    ('finance_audit_events', 'before_values'):
        'مقادیر پیش از تغییر',
    ('finance_audit_events', 'entity_type'):
        'نوع موجودیتی که تغییر کرده',
    # ---- finance_import_batches
    ('finance_import_batches', 'currency_unit'):
        'واحد پول فایل واردشده',
    ('finance_import_batches', 'import_kind'):
        'نوع واردات',
    ('finance_import_batches', 'normalized_rows'):
        'ردیف\u200cهای استانداردشدهٔ فایل',
    ('finance_import_batches', 'validation_errors'):
        'خطاهای اعتبارسنجی فایل',
    # ---- finance_item_price_mapping_components
    ('finance_item_price_mapping_components', 'component_quantity_decimal'):
        'مقدار جزء پس از تبدیل واحد',
    ('finance_item_price_mapping_components', 'conversion_status'):
        'وضعیت تبدیل واحد این جزء',
    ('finance_item_price_mapping_components', 'product_type'):
        'نوع محصول این جزء',
    ('finance_item_price_mapping_components', 'selected_unit'):
        'واحد انتخاب\u200cشده برای این جزء',
    ('finance_item_price_mapping_components', 'source_price_basis'):
        'مبنای قیمت در منبع',
    ('finance_item_price_mapping_components', 'source_price_unit'):
        'واحد قیمت در منبع',
    ('finance_item_price_mapping_components', 'usage_mode'):
        'نحوهٔ مصرف این جزء در سطر برآورد',
    ('finance_item_price_mapping_components', 'usage_quantity_decimal'):
        'مقدار مصرف این جزء',
    ('finance_item_price_mapping_components', 'usage_unit'):
        'واحد مصرف این جزء',
    # ---- finance_item_price_mappings
    ('finance_item_price_mappings', 'conversion_status'):
        'وضعیت تبدیل واحد این نگاشت',
    ('finance_item_price_mappings', 'selected_unit'):
        'واحدی که برای قیمت\u200cگذاری انتخاب شده',
    ('finance_item_price_mappings', 'source_price_basis'):
        'مبنای قیمت در منبع',
    ('finance_item_price_mappings', 'source_price_unit'):
        'واحد قیمت در منبع',
    # ---- finance_mpp_currency_decisions
    ('finance_mpp_currency_decisions', 'amounts_are'):
        'تصمیم نهایی: اعداد فایل تومان\u200cاند یا ریال',
    ('finance_mpp_currency_decisions', 'compared_with_sha256'):
        'فایلی که برای این مقایسه مبنا بوده',
    ('finance_mpp_currency_decisions', 'evidence'):
        'شواهدی که تصمیم بر آن استوار است',
    ('finance_mpp_currency_decisions', 'file_currency_code'):
        'کد پولی که فایل اعلام می\u200cکند (مثلاً IRR) — می\u200cتواند با نماد نخواند',
    ('finance_mpp_currency_decisions', 'file_currency_symbol'):
        'نماد پولی که خود فایل نشان می\u200cدهد (مثلاً «تومان»)',
    # ---- finance_mpp_rows
    ('finance_mpp_rows', 'actual_progress'):
        'پیشرفت واقعی گزارش\u200cشده',
    ('finance_mpp_rows', 'physical_progress'):
        'پیشرفت فیزیکی',
    ('finance_mpp_rows', 'planned_progress'):
        'پیشرفت برنامه\u200cای در همان تاریخ',
    ('finance_mpp_rows', 'progress_variance'):
        'اختلاف پیشرفت واقعی با برنامه\u200cای',
    ('finance_mpp_rows', 'quantity_unit'):
        'واحد مقدار این سطر',
    ('finance_mpp_rows', 'resource_name'):
        'نام منبع',
    ('finance_mpp_rows', 'resource_type'):
        'نوع منبع (نیرو، مصالح، تجهیزات)',
    ('finance_mpp_rows', 'source_actual_cost'):
        'هزینهٔ واقعی طبق فایل',
    ('finance_mpp_rows', 'source_assignment_uid'):
        'شناسهٔ تخصیص در فایل MPP',
    ('finance_mpp_rows', 'source_assignment_units'):
        'واحدِ تخصیص؛ در فایل ضربدر ۱۰۰ ذخیره شده',
    ('finance_mpp_rows', 'source_cost'):
        'هزینه در سطح تسک است و روی همهٔ تخصیص\u200cهای آن تسک کپی می\u200cشود؛ جمع\u200cزدن ساده هزینه را چند برابر می\u200cشمارد',
    ('finance_mpp_rows', 'source_fixed_cost'):
        'هزینهٔ ثابت تسک؛ تنها جای پولی که مدت\u200cها خوانده نمی\u200cشد',
    ('finance_mpp_rows', 'source_resource_uid'):
        'شناسهٔ منبع در فایل MPP',
    ('finance_mpp_rows', 'source_task_uid'):
        'شناسهٔ تسک در فایل MPP',
    ('finance_mpp_rows', 'task_finish'):
        'تاریخ پایان تسک',
    ('finance_mpp_rows', 'task_name'):
        'نام تسک، کپی\u200cشده از فایل برای خواندن بدون join',
    ('finance_mpp_rows', 'task_wbs'):
        'کد WBS تسک',
    ('finance_mpp_rows', 'unit_source'):
        'اینکه واحد از کجا تعیین شده',
    ('finance_mpp_rows', 'weight_base'):
        'مبنایی که وزن بر آن حساب شده',
    ('finance_mpp_rows', 'weight_rial'):
        'وزن سطر بر مبنای ریال، برای تجمیع پیشرفت',
    ('finance_mpp_rows', 'weight_time'):
        'وزن سطر بر مبنای زمان',
    # ---- finance_price_categories
    ('finance_price_categories', 'scope_level'):
        'سطح تعریف دسته (سازمان یا پروژه)',
    # ---- finance_project_settings
    ('finance_project_settings', 'gross_built_area'):
        'زیربنای ناخالص پروژه، مبنای سنجه\u200cهای «به ازای متر مربع»',
    ('finance_project_settings', 'revision'):
        'شمارهٔ بازنگری تنظیمات؛ جدول فقط\u200cافزودنی است',
    # ---- finance_resources
    ('finance_resources', 'dimension'):
        'بُعد فیزیکی واحد منبع (جرم، طول، زمان، …)',
    # ---- finance_unit_conversion_rules
    ('finance_unit_conversion_rules', 'conversion_method'):
        'روش تبدیل: ضریب ثابت یا فرمول',
    ('finance_unit_conversion_rules', 'direction_definition'):
        'اینکه قانون یک\u200cطرفه است یا دوطرفه',
    ('finance_unit_conversion_rules', 'evidence_source'):
        'مستندی که ضریب بر آن استوار است',
    ('finance_unit_conversion_rules', 'factor_value'):
        'ضریب تبدیل — نام ستون factor_value است نه factor؛ خواندن با کلید اشتباه قانون را بی\u200cاثر می\u200cکند',
    ('finance_unit_conversion_rules', 'formula_definition'):
        'تعریف فرمول تبدیل، وقتی ضریب ثابت کافی نیست',
    ('finance_unit_conversion_rules', 'formula_schema_version'):
        'نسخهٔ ساختار فرمول',
    ('finance_unit_conversion_rules', 'from_unit'):
        'واحد مبدأ',
    ('finance_unit_conversion_rules', 'scope_level'):
        'دامنهٔ قانون؛ اولویت از جزئی به کلی: provider_item ← provider_category ← category ← provider ← project ← organization ← global',
    ('finance_unit_conversion_rules', 'to_unit'):
        'واحد مقصد',
    # ---- floors
    ('floors', 'exterior_boundary'):
        'مرز بیرونی طبقه (هندسه)',
    ('floors', 'order'):
        'ترتیب طبقه',
    ('floors', 'plan_interior_rect'):
        'مستطیل داخلی پلان (هندسه)',
    # ---- invoices
    ('invoices', 'confirmation_idempotency_key'):
        'همان کلید، برای مرحلهٔ تأیید',
    ('invoices', 'financial_effect_sign'):
        'جهت اثر مالی: فاکتور عادی مثبت، اصلاحیه منفی',
    ('invoices', 'idempotency_key'):
        'کلید یکتاسازی؛ ارسال دوبارهٔ یک درخواست، فاکتور دوم نمی\u200cسازد',
    ('invoices', 'invoice_date'):
        'تاریخ فاکتور',
    ('invoices', 'invoice_number'):
        'شمارهٔ فاکتور',
    ('invoices', 'source'):
        'فاکتور از کجا آمده (دستی، استخراج، واردات)',
    ('invoices', 'source_file_sha256'):
        'اثرانگشت فایل مبدأ فاکتور',
    ('invoices', 'vendor_name'):
        'نام فروشنده',
    # ---- material_unit_settings
    ('material_unit_settings', 'conversion_mode'):
        'روش رسیدن از واحد اصلی به واحد نمایشی',
    ('material_unit_settings', 'display_unit'):
        'واحدی که به کاربر نشان داده می\u200cشود',
    ('material_unit_settings', 'source_basis'):
        'مبنای واحد اصلی',
    ('material_unit_settings', 'source_unit'):
        'واحد اصلی داده',
    # ---- media_files
    ('media_files', 'bytes'):
        'حجم فایل به بایت',
    ('media_files', 'kind'):
        'نوع رسانه',
    ('media_files', 'mime'):
        'نوع MIME فایل',
    # ---- message_threads
    ('message_threads', 'scope'):
        'دامنهٔ گفت\u200cوگو',
    # ---- messages
    ('messages', 'body'):
        'متن پیام',
    # ---- msp_file_versions
    ('msp_file_versions', 'original_filename'):
        'نام اصلی فایل بارگذاری\u200cشده',
    ('msp_file_versions', 'plan_intent'):
        'قصدِ بارگذاری این نسخه',
    ('msp_file_versions', 'sha256'):
        'اثرانگشت فایل؛ همان فایل دوبار وارد نمی\u200cشود',
    # ---- msp_reporting_calendars
    ('msp_reporting_calendars', 'cadence_interval'):
        'طول هر دورهٔ گزارش\u200cدهی',
    # ---- msp_reporting_periods
    ('msp_reporting_periods', 'is_manual'):
        'اینکه دوره دستی ساخته شده یا از تقویم',
    # ---- msp_resource_assignments
    ('msp_resource_assignments', 'actual_work'):
        'کار انجام\u200cشدهٔ این تخصیص',
    ('msp_resource_assignments', 'planned_work'):
        'کار برنامه\u200cریزی\u200cشدهٔ این تخصیص',
    ('msp_resource_assignments', 'remaining_quantity'):
        'مقدار باقی\u200cماندهٔ این تخصیص',
    ('msp_resource_assignments', 'remaining_work'):
        'کار باقی\u200cماندهٔ این تخصیص',
    ('msp_resource_assignments', 'source_cost'):
        'هزینهٔ این تخصیص طبق فایل',
    ('msp_resource_assignments', 'source_remaining_cost'):
        'هزینهٔ باقی\u200cماندهٔ این تخصیص طبق فایل',
    ('msp_resource_assignments', 'units'):
        'ضریب تخصیص منبع به تسک؛ در فایل ×۱۰۰ ذخیره می\u200cشود',
    # ---- msp_resources
    ('msp_resources', 'actual_work'):
        'کار انجام\u200cشدهٔ منبع',
    ('msp_resources', 'cost_per_use'):
        'هزینهٔ ثابت هر بار استفاده',
    ('msp_resources', 'initials'):
        'حروف اختصاری منبع در MS Project',
    ('msp_resources', 'material_label'):
        'برچسب واحد مصالح در MS Project',
    ('msp_resources', 'max_units'):
        'حداکثر ظرفیت منبع',
    ('msp_resources', 'native_type'):
        'نوع منبع در خودِ MS Project (کار / مصالح / هزینه)',
    ('msp_resources', 'overtime_rate'):
        'نرخ اضافه\u200cکاری',
    ('msp_resources', 'quantity_unit_source'):
        'اینکه واحد مقدار از کجا آمده',
    ('msp_resources', 'remaining_work'):
        'کار باقی\u200cماندهٔ منبع',
    ('msp_resources', 'resource_group'):
        'گروه منبع',
    ('msp_resources', 'resource_guid'):
        'شناسهٔ سراسری منبع در فایل MPP',
    ('msp_resources', 'resource_name'):
        'نام منبع، همان\u200cطور که در فایل نوشته شده',
    ('msp_resources', 'source_actual_cost'):
        'هزینهٔ واقعی منبع طبق فایل',
    ('msp_resources', 'source_cost'):
        'هزینهٔ منبع طبق فایل',
    ('msp_resources', 'source_remaining_cost'):
        'هزینهٔ باقی\u200cماندهٔ منبع طبق فایل',
    ('msp_resources', 'work'):
        'کار برنامه\u200cریزی\u200cشدهٔ منبع',
    # ---- msp_snapshots
    ('msp_snapshots', 'source_filename'):
        'نام فایلی که snapshot از آن ساخته شده',
    # ---- msp_tasks
    ('msp_tasks', 'baseline_cost'):
        'هزینهٔ خط مبنا',
    ('msp_tasks', 'baseline_duration'):
        'مدت خط مبنا',
    ('msp_tasks', 'baseline_finish'):
        'پایان خط مبنا',
    ('msp_tasks', 'baseline_start'):
        'شروع خط مبنا',
    ('msp_tasks', 'duration'):
        'مدت تسک',
    ('msp_tasks', 'finish'):
        'تاریخ پایان برنامه\u200cریزی\u200cشده',
    ('msp_tasks', 'finish1'):
        'فیلد تاریخ سفارشی MS Project (Finish1)',
    ('msp_tasks', 'guid'):
        'شناسهٔ سراسری تسک در فایل MPP',
    ('msp_tasks', 'number1'):
        'فیلد عددی سفارشی MS Project (Number1). در دادهٔ فعلی پر است، ولی هیچ کدی در این مخزن آن را نمی\u200cخواند — **معنای آن احراز نشده**',
    ('msp_tasks', 'number13'):
        'فیلد عددی سفارشی MS Project (Number13). در دادهٔ فعلی پر است، ولی هیچ کدی در این مخزن آن را نمی\u200cخواند — **معنای آن احراز نشده**',
    ('msp_tasks', 'number14'):
        'فیلد عددی سفارشی MS Project (Number14). در دادهٔ فعلی پر است، ولی هیچ کدی در این مخزن آن را نمی\u200cخواند — **معنای آن احراز نشده**',
    ('msp_tasks', 'number18'):
        'فیلد عددی سفارشی MS Project (Number18). در دادهٔ فعلی پر است، ولی هیچ کدی در این مخزن آن را نمی\u200cخواند — **معنای آن احراز نشده**',
    ('msp_tasks', 'number3'):
        'فیلد عددی سفارشی MS Project (Number3). در دادهٔ فعلی پر است، ولی هیچ کدی در این مخزن آن را نمی\u200cخواند — **معنای آن احراز نشده**',
    ('msp_tasks', 'number4'):
        'فیلد عددی سفارشی MS Project (Number4). در دادهٔ فعلی پر است، ولی هیچ کدی در این مخزن آن را نمی\u200cخواند — **معنای آن احراز نشده**',
    ('msp_tasks', 'outline_level'):
        'عمق تسک در درخت برنامه؛ ۱ یعنی سطح اول',
    ('msp_tasks', 'outline_number'):
        'شمارهٔ سلسله\u200cمراتبی تسک در درخت برنامه',
    ('msp_tasks', 'percent_complete'):
        'درصد تکمیل تسک',
    ('msp_tasks', 'percent_work_complete'):
        'درصد تکمیل بر مبنای کار (نفر-ساعت)',
    ('msp_tasks', 'physical_percent_complete'):
        'درصد تکمیل فیزیکی، جدا از درصد کار',
    ('msp_tasks', 'start'):
        'تاریخ شروع برنامه\u200cریزی\u200cشده',
    ('msp_tasks', 'start1'):
        'فیلد تاریخ سفارشی MS Project (Start1)',
    ('msp_tasks', 'text1'):
        'فیلد متنی سفارشی MS Project (Text1)',
    ('msp_tasks', 'uid'):
        'شناسهٔ تسک در فایل MPP (UID)',
    ('msp_tasks', 'wbs'):
        'کد WBS تسک',
    # ---- msp_voice_report_audio
    ('msp_voice_report_audio', 'tag'):
        'برچسب فایل صوتی',
    # ---- msp_voice_reports
    ('msp_voice_reports', 'summary_text'):
        'متن خلاصهٔ گزارش صوتی',
    ('msp_voice_reports', 'text_generator'):
        'متن خلاصه را چه چیزی تولید کرده',
    # ---- note_activities
    ('note_activities', 'body'):
        'متن رویداد',
    ('note_activities', 'file_size'):
        'حجم فایل پیوست',
    ('note_activities', 'mime'):
        'نوع MIME فایل پیوست',
    ('note_activities', 'source'):
        'منبع رویداد',
    ('note_activities', 'status_from'):
        'وضعیت پیشین',
    ('note_activities', 'status_to'):
        'وضعیت جدید',
    # ---- notifications
    ('notifications', 'is_read'):
        'اعلان خوانده شده است',
    ('notifications', 'message'):
        'متن اعلان',
    ('notifications', 'type'):
        'نوع اعلان',
    # ---- organization_members
    ('organization_members', 'email'):
        'رایانامهٔ عضو',
    ('organization_members', 'is_org_president'):
        'عضو، رئیس سازمان است',
    ('organization_members', 'phone'):
        'شمارهٔ تلفن عضو',
    ('organization_members', 'role_title'):
        'عنوان سِمت عضو در سازمان',
    # ---- organization_memberships
    ('organization_memberships', 'role'):
        'نقش کاربر در سازمان',
    # ---- organizations
    ('organizations', 'city'):
        'شهر',
    ('organizations', 'contact_info'):
        'اطلاعات تماس',
    ('organizations', 'country'):
        'کشور',
    ('organizations', 'logo_path'):
        'مسیر لوگو',
    ('organizations', 'maps_embed'):
        'کد جاسازی نقشه',
    ('organizations', 'member_limit'):
        'سقف تعداد اعضا',
    ('organizations', 'org_type'):
        'نوع سازمان',
    ('organizations', 'province'):
        'استان',
    ('organizations', 'website'):
        'وب\u200cسایت سازمان',
    # ---- otp_codes
    ('otp_codes', 'consumed'):
        'کد مصرف شده است',
    ('otp_codes', 'phone'):
        'شماره\u200cای که کد برای آن فرستاده شده',
    # ---- panoramas
    ('panoramas', 'sheet_x'):
        'مختصات X روی شیت',
    ('panoramas', 'sheet_y'):
        'مختصات Y روی شیت',
    ('panoramas', 'yaw'):
        'زاویهٔ چرخش افقی دوربین',
    # ---- permissions
    ('permissions', 'action_key'):
        'کاری که مجوز اجازه می\u200cدهد',
    ('permissions', 'module_key'):
        'ماژولی که مجوز به آن تعلق دارد',
    # ---- price_collection_runs
    ('price_collection_runs', 'error_message'):
        'خطای پایانی اجرا، اگر شکست خورده',
    ('price_collection_runs', 'failed_items'):
        'تعداد ردیف\u200cهای ردشده',
    ('price_collection_runs', 'rejected_items'):
        'ردیف\u200cهای ردشده به همراه دلیل',
    ('price_collection_runs', 'successful_items'):
        'تعداد ردیف\u200cهای پذیرفته\u200cشده',
    ('price_collection_runs', 'total_items'):
        'تعداد کل ردیف\u200cهای خوانده\u200cشده در این اجرا',
    ('price_collection_runs', 'worksheet_report'):
        'گزارش تب\u200cبه\u200cتب همین اجرا',
    # ---- price_collection_schedules
    ('price_collection_schedules', 'enabled'):
        'فعال بودن زمان\u200cبندی',
    ('price_collection_schedules', 'interval_minutes'):
        'فاصلهٔ اجرا، به دقیقه',
    # ---- price_observations
    ('price_observations', 'availability'):
        'موجود بودن کالا',
    ('price_observations', 'collection_run_id'):
        'اجرای ایمپورتی که این ردیف را آورد',
    ('price_observations', 'confidence_score'):
        'میزان اطمینان به درستی این مشاهده',
    ('price_observations', 'fetched_at'):
        'زمان واکشی از گوگل',
    ('price_observations', 'normalized_price_irr'):
        'همان قیمت به ریال — برای محاسبه این را بخوانید، نه raw_price را',
    ('price_observations', 'observed_at'):
        'زمان اعتبار قیمت',
    ('price_observations', 'observed_at_source'):
        'زمانی که خود سند برای قیمت اعلام کرده',
    ('price_observations', 'origin'):
        'مشاهده از کجا آمده — در دادهٔ فعلی: sheet یا manual',
    ('price_observations', 'product_external_id'):
        'شناسهٔ کالا نزد تأمین\u200cکننده، در لحظهٔ ثبت',
    ('price_observations', 'product_name_snapshot'):
        'نام کالا در لحظهٔ ثبت؛ تغییر بعدی نام کالا این را عوض نمی\u200cکند',
    ('price_observations', 'provider_name_snapshot'):
        'نام تأمین\u200cکننده در لحظهٔ ثبت',
    ('price_observations', 'raw_data'):
        'کل ردیف خام شیت (JSON) برای ردیابی',
    ('price_observations', 'raw_price'):
        'عدد قیمت، دقیقاً همان\u200cطور که در سلول شیت نوشته شده (متن)',
    ('price_observations', 'row_fingerprint'):
        'اثرانگشت ردیف؛ پایهٔ ON CONFLICT DO NOTHING که ایمپورت مجدد را بی\u200cخطر می\u200cکند',
    ('price_observations', 'secondary_price_basis'):
        'مبنای قیمت دوم',
    ('price_observations', 'secondary_price_irr'):
        'قیمت دوم ردیف (مثلاً نقدی در برابر مدت\u200cدار) به ریال',
    ('price_observations', 'source_currency'):
        'واحد پول مبدأ؛ شیت به تومان است',
    ('price_observations', 'source_document_id'):
        'شناسهٔ سند گوگل\u200cشیت',
    ('price_observations', 'source_row_number'):
        'شمارهٔ ردیف در همان تب',
    ('price_observations', 'source_unit'):
        'واحد مبدأ، همان\u200cطور که در شیت آمده (مثلاً «کیلو»)',
    ('price_observations', 'source_worksheet'):
        'نام تب شیت',
    ('price_observations', 'validation_reasons'):
        'دلیل رد شدن ردیف',
    ('price_observations', 'validation_status'):
        'معتبر بودن ردیف',
    ('price_observations', 'workflow_date_gregorian'):
        'تاریخ ردیف، میلادی',
    ('price_observations', 'workflow_date_jalali'):
        'تاریخ ردیف، شمسی',
    ('price_observations', 'workflow_date_raw'):
        'تاریخ ردیف، خام',
    # ---- price_providers
    ('price_providers', 'crawl_method'):
        'روش گردآوری قیمت (شیت، خزش، دستی)',
    ('price_providers', 'default_interval_minutes'):
        'فاصلهٔ پیش\u200cفرض اجرای خودکار، به دقیقه',
    ('price_providers', 'domain'):
        'دامنهٔ اینترنتی تأمین\u200cکننده',
    ('price_providers', 'provider_type'):
        'نوع تأمین\u200cکننده',
    # ---- price_resolution_policies
    ('price_resolution_policies', 'max_age_minutes'):
        'حداکثر کهنگی قابل\u200cقبول قیمت، به دقیقه',
    ('price_resolution_policies', 'provider_weights'):
        'وزن هر تأمین\u200cکننده در انتخاب قیمت',
    ('price_resolution_policies', 'strategy'):
        'راهبرد انتخاب قیمت میان چند مشاهده',
    # ---- progress_snapshot_refs
    ('progress_snapshot_refs', 'reporting_date'):
        'تاریخ گزارشِ این snapshot',
    ('progress_snapshot_refs', 'snapshot_status'):
        'وضعیت snapshot',
    ('progress_snapshot_refs', 'source_file_name_safe'):
        'نام فایل مبدأ، پاک\u200cسازی\u200cشده',
    ('progress_snapshot_refs', 'source_type'):
        'نوع منبع snapshot',
    # ---- project_memberships
    ('project_memberships', 'role'):
        'نقش کاربر در پروژه',
    # ---- project_sequences
    ('project_sequences', 'last_seq'):
        'آخرین عدد مصرف\u200cشدهٔ دنباله',
    # ---- projects
    ('projects', 'actual_cost_to_date'):
        'هزینهٔ واقعی تا امروز',
    ('projects', 'address'):
        'نشانی پروژه',
    ('projects', 'built_area_sqm'):
        'زیربنا، متر مربع',
    ('projects', 'cost_source'):
        'منبع عدد هزینه',
    ('projects', 'cost_unit'):
        'واحد پول هزینه',
    ('projects', 'cover_image_path'):
        'مسیر تصویر شاخص پروژه',
    ('projects', 'estimated_cost'):
        'هزینهٔ برآوردی پروژه',
    ('projects', 'planned_end_date'):
        'تاریخ پایان برنامه\u200cریزی\u200cشده',
    ('projects', 'start_date'):
        'تاریخ شروع پروژه',
    # ---- provider_item_labels
    ('provider_item_labels', 'display_name'):
        'نامی که به کاربر نشان داده می\u200cشود',
    ('provider_item_labels', 'mapping_approved'):
        'اینکه این نگاشت تأیید انسانی گرفته یا نه',
    ('provider_item_labels', 'product_type'):
        'نوع محصول',
    ('provider_item_labels', 'source_basis'):
        'مبنای واحد مبدأ',
    ('provider_item_labels', 'source_unit'):
        'واحد مبدأ',
    ('provider_item_labels', 'target_unit'):
        'واحد مقصد',
    # ---- provider_item_unit_factors
    ('provider_item_unit_factors', 'factor'):
        'ضریب تبدیل — در این جدول نام ستون factor است، برخلاف finance_unit_conversion_rules',
    ('provider_item_unit_factors', 'factor_type'):
        'نوع ضریب',
    ('provider_item_unit_factors', 'from_unit'):
        'واحد مبدأ',
    ('provider_item_unit_factors', 'origin'):
        'ضریب از کجا آمده (اندازه\u200cگیری، اعلام فروشنده، …)',
    ('provider_item_unit_factors', 'to_unit'):
        'واحد مقصد',
    # ---- provider_items
    ('provider_items', 'base_unit'):
        'واحد پایهٔ کالا — در دادهٔ فعلی بخش بزرگی از مقادیر متن خام فایل است، نه کد واحد استاندارد',
    ('provider_items', 'category'):
        'دستهٔ مصالح (میلگرد، آجر، لوله، …)',
    ('provider_items', 'coverage_m2'):
        'سطح پوشش هر واحد، متر مربع',
    ('provider_items', 'diameter_value'):
        'قطر کالا',
    ('provider_items', 'external_id'):
        'شناسهٔ کالا نزد تأمین\u200cکننده',
    ('provider_items', 'external_name'):
        'نام کالا، همان\u200cطور که تأمین\u200cکننده نوشته',
    ('provider_items', 'grade'):
        'گرید یا رده (مثلاً A3 برای میلگرد)',
    ('provider_items', 'height_value'):
        'ارتفاع کالا',
    ('provider_items', 'inactive_reason'):
        'دلیل غیرفعال شدن کالا',
    ('provider_items', 'length_value'):
        'طول کالا',
    ('provider_items', 'manufacturer'):
        'سازنده',
    ('provider_items', 'pieces_per_package'):
        'تعداد در هر بسته',
    ('provider_items', 'product_code'):
        'کد کالا',
    ('provider_items', 'product_type'):
        'نوع محصول',
    ('provider_items', 'source_unit'):
        'واحد کالا، همان\u200cطور که در منبع نوشته شده',
    ('provider_items', 'source_worksheet'):
        'تبِ شیتی که کالا از آن آمده',
    ('provider_items', 'spec_conflicts'):
        'تعارض بین مشخصات استخراج\u200cشده از منابع مختلف',
    ('provider_items', 'spec_source'):
        'مشخصات فنی از کجا استخراج شده',
    ('provider_items', 'thickness_value'):
        'ضخامت کالا',
    ('provider_items', 'url'):
        'نشانی آگهی یا صفحهٔ کالا نزد تأمین\u200cکننده',
    ('provider_items', 'volume_m3'):
        'حجم هر واحد، متر مکعب',
    ('provider_items', 'width_value'):
        'عرض کالا',
    # ---- provider_resource_mappings
    ('provider_resource_mappings', 'approved'):
        'اینکه نگاشت تأیید انسانی گرفته یا نه',
    ('provider_resource_mappings', 'confidence_score'):
        'میزان اطمینان به درستی نگاشت',
    # ---- report_snapshots
    ('report_snapshots', 'calculated_metrics'):
        'سنجه\u200cهای محاسبه\u200cشدهٔ گزارش',
    ('report_snapshots', 'estimate_revision_ids'):
        'کدام بازنگری\u200cهای برآورد در این گزارش لحاظ شده\u200cاند',
    ('report_snapshots', 'invoice_ids'):
        'کدام فاکتورها لحاظ شده\u200cاند',
    ('report_snapshots', 'price_version_ids'):
        'کدام نسخه\u200cهای قیمت لحاظ شده\u200cاند',
    ('report_snapshots', 'reporting_date'):
        'تاریخی که گزارش برای آن گرفته شده',
    ('report_snapshots', 'resource_version_ids'):
        'کدام نسخه\u200cهای منابع لحاظ شده\u200cاند',
    ('report_snapshots', 'snapshot_payload'):
        'کل خروجی گزارش در لحظهٔ گرفتن',
    ('report_snapshots', 'unit_conversion_ids'):
        'کدام تبدیل\u200cهای واحد لحاظ شده\u200cاند',
    # ---- roles
    ('roles', 'is_system'):
        'نقش سیستمی است و قابل حذف نیست',
    # ---- sessions
    ('sessions', 'token'):
        'توکن نشست',
    # ---- sheets
    ('sheets', 'is_primary'):
        'شیت اصلی است',
    ('sheets', 'kind'):
        'نوع شیت یا نقشه',
    # ---- tags
    ('tags', 'is_default'):
        'برچسب پیش\u200cفرض است',
    # ---- unit_conversions
    ('unit_conversions', 'dimension'):
        'بُعد فیزیکی (جرم، طول، زمان، …)؛ عبور از بُعد بدون قانون مجاز نیست',
    ('unit_conversions', 'factor'):
        'ضریب تبدیل',
    ('unit_conversions', 'scope_kind'):
        'دامنهٔ اعتبار تبدیل',
    ('unit_conversions', 'source_unit'):
        'واحد مبدأ',
    ('unit_conversions', 'target_unit'):
        'واحد مقصد',
    # ---- user_permission_overrides
    ('user_permission_overrides', 'allowed'):
        'مجوز برای این کاربر صریحاً داده یا گرفته شده',
    # ---- users
    ('users', 'avatar_path'):
        'مسیر تصویر کاربر',
    ('users', 'display_name'):
        'نام نمایشی کاربر',
    ('users', 'email'):
        'رایانامهٔ کاربر',
    ('users', 'password_hash'):
        'درهم\u200cسازی گذرواژه؛ خودِ گذرواژه ذخیره نمی\u200cشود',
    ('users', 'phone'):
        'شمارهٔ تلفن کاربر',
    # ---- zones
    ('zones', 'rect'):
        'مستطیل زون روی پلان',
}


#: The order a reader meets the database in: what is planned, what it costs on the
#: market, what that makes the estimate, what was actually spent, and what is left over.
DOMAINS = [
    ("برنامهٔ زمان‌بندی و فایل MPP",
     "برنامهٔ MS Project و خوانشِ مالیِ آن. مرجعِ «چه کاری قرار است انجام شود».",
     ["msp_tasks", "msp_resources", "msp_resource_assignments", "msp_snapshots",
      "msp_file_versions", "msp_baseline_revisions", "msp_reporting_calendars",
      "msp_reporting_periods", "msp_edit_sessions", "msp_voice_reports",
      "msp_voice_report_audio", "finance_mpp_rows", "finance_mpp_source_versions",
      "finance_mpp_currency_decisions", "finance_task_resource_map"]),
    ("قیمت بازار و گوگل‌شیت",
     "قیمت‌هایی که از گوگل‌شیت وارد می‌شوند، و هویت کالایی که قیمت به آن می‌چسبد.",
     ["price_observations", "provider_items", "price_providers", "price_collection_runs",
      "price_collection_schedules", "provider_item_labels", "provider_item_unit_factors",
      "material_unit_settings", "finance_price_categories", "price_resolution_policies",
      "provider_resource_mappings"]),
    ("برآورد، منابع مالی و تبدیل واحد",
     "از برنامه تا عدد ریالی: سطر برآورد، منبع مالی، قیمت و ضریب تبدیل واحد.",
     ["estimate_lines", "estimate_revisions", "estimate_line_source_completions",
      "finance_resources", "price_versions", "unit_conversions",
      "finance_unit_conversion_rules", "finance_unit_conversion_issues",
      "finance_item_price_mappings", "finance_item_price_mapping_components"]),
    ("فاکتور و استخراج هوش مصنوعی",
     "سند واقعی خرج: پیوست، استخراج، پیش‌نویس و فاکتور تأییدشده.",
     ["invoices", "invoice_lines", "finance_invoice_counters", "finance_attachments",
      "extraction_drafts", "finance_import_batches"]),
    ("پیشرفت، گزارش و حسابرسی",
     "آنچه واقعاً اجرا شده، و ردِ هر تغییر.",
     ["progress_snapshot_refs", "progress_overrides", "report_snapshots",
      "finance_audit_events", "audit_logs", "finance_project_settings",
      "finance_alembic_version"]),
    ("سازمان، کاربر و دسترسی",
     "هویت و مجوز. بخش مالی این‌ها را می‌خواند و نمی‌نویسد.",
     ["organizations", "projects", "users", "roles", "permissions", "role_permissions",
      "user_roles", "user_permission_overrides", "organization_members",
      "organization_memberships", "project_members", "project_memberships",
      "project_sequences", "sessions", "otp_codes"]),
    ("ماژول‌های دیگر BAMBO",
     "در همین دیتابیس‌اند، ولی API مالی به آن‌ها دست نمی‌زند.",
     ["field_notes", "field_note_statuses", "field_note_tags", "field_note_tag_links",
      "field_note_comments", "field_note_attachments", "field_note_activities",
      "note_activities", "note_tags", "tags", "messages", "message_threads",
      "notifications", "media_files", "panoramas", "capture_sessions",
      "capture_path_points", "floors", "zones", "sheets"]),
]


# --------------------------------------------------------------------------- rendering

def constraint_note(table_meta, column):
    """What a CHECK says about ONE column, rendered from the constraint itself.

    Only a constraint that governs this column alone is reported. A two-column rule such
    as `(validation_status <> 'valid') OR (normalized_price_irr IS NOT NULL)` mentions
    both names and carries the literal 'valid', so matching on the name would print
    «مقادیر مجاز: valid» under a numeric money column -- a statement that is false.
    Postgres records which columns each constraint covers; that is what decides here.
    """
    for check in (table_meta.get("checks") or []):
        columns = check.get("cols") or []
        if len(columns) != 1 or columns[0] != column:
            continue
        definition = check["def"]
        vocabulary = list(dict.fromkeys(re.findall(r"'([^']*)'::text", definition)))
        if vocabulary and "ANY (ARRAY[" in definition and len(vocabulary) <= 12:
            return "مقادیر مجاز: " + " / ".join(vocabulary)
        # A non-blank rule, recognised BEFORE the numeric pattern -- which would
        # otherwise read its `> 0` and report a numeric limit on a text column.
        if re.search(r"length\(btrim", definition):
            return "نمی‌تواند خالی یا فقط فاصله باشد"
        fixed = re.match(r"^CHECK \(\(?%s = \(?(-?\d+)\)?" % re.escape(column), definition)
        if fixed:
            return "همیشه برابر %s" % fixed.group(1)
        bounds = list(dict.fromkeys(
            re.findall(r"[<>]=?\s*\(?(-?\d+(?:\.\d+)?)\)?", definition)))
        if len(bounds) > 1:
            return "محدودهٔ مجاز: %s تا %s" % (bounds[0], bounds[-1])
        if bounds:
            lower = re.search(r">=?\s*\(?%s" % re.escape(bounds[0]), definition)
            return "%s %s" % ("حداقل" if lower else "حداکثر", bounds[0])
    return None


class Describer:
    """Column meaning, and an honest count of where each description came from."""

    def __init__(self):
        self.sources = collections.Counter()
        self.missing = []

    def describe(self, table, column):
        if column.get("comment"):
            return self._seen(column["comment"], "db")
        key = (table, column["name"])
        if key in MEANING:
            return self._seen(MEANING[key], "hand")
        if column.get("fk"):
            return self._seen("ارجاع به `%s`" % column["fk"], "fk")
        if column["name"] in GENERIC:
            return self._seen(GENERIC[column["name"]], "generic")
        for suffix, template in SUFFIX:
            if column["name"].endswith(suffix) and len(column["name"]) > len(suffix):
                stem = column["name"][: -len(suffix)].replace("_", " ")
                return self._seen(template % stem, "suffix")
        self.missing.append("%s.%s" % (table, column["name"]))
        return self._seen("**توضیح ثبت‌نشده**", "none")

    def _seen(self, text, source):
        self.sources[source] += 1
        return text


def anchor(text):
    slug = text.strip().lower()
    slug = re.sub(r"[`«»,.()/]", "", slug)
    return slug.replace(" ", "-").replace("_", "-")


def render(schema, migration, database, endpoints):
    describer = Describer()
    by_table = collections.defaultdict(list)
    for endpoint in endpoints:
        for table in endpoint["tables"]:
            by_table[table].append("`%s %s`" % (endpoint["verb"], endpoint["path"]))
    for table in list(by_table):
        by_table[table] = sorted(dict.fromkeys(by_table[table]))

    domains = list(DOMAINS)
    placed = {t for _, _, tables in domains for t in tables}
    orphans = sorted(set(schema) - placed)
    if orphans:
        domains.append(("دسته‌بندی‌نشده", "در گروه‌بندی بالا جا نگرفته‌اند.", orphans))

    lines = []
    out = lines.append
    columns_total = sum(len(t["columns"]) for t in schema.values())

    out("# شمای دیتابیس BAMBO Finance")
    out("")
    out("مرجع ساختار دیتابیس: هر جدول برای چیست، هر ستون چه نگه می‌دارد، و کدام endpoint "
        "به آن می‌رسد.")
    out("")
    out("| | |")
    out("|---|---|")
    out("| دیتابیس | `%s` |" % database)
    out("| نسخهٔ مهاجرت | `%s` |" % migration)
    out("| تعداد جدول | %d |" % len(schema))
    out("| تعداد ستون | %d |" % columns_total)
    out("| تعداد endpoint | %d |" % len(endpoints))
    out("| جدول‌هایی که API مالی به آن‌ها می‌رسد | %d از %d |" % (len(by_table), len(schema)))
    out("| پیشوند مسیرها | `%s` |" % BASE_PATH)
    out("")
    out("این سند ساخته می‌شود، دستی نوشته نمی‌شود: `python -m scripts.generate_schema_doc`.")
    out("")
    out("ساختار، نوع، کلید خارجی، مقدار پیش‌فرض و واژگان CHECK مستقیماً از دیتابیس زنده "
        "خوانده شده‌اند. کاربردِ هر جدول و معنای هر ستون دستی نوشته شده است. ستونی که "
        "هیچ‌کدام پوشش نداده‌اند با **توضیح ثبت‌نشده** علامت خورده و در انتهای سند شمرده "
        "شده — حدس زده نشده.")
    out("")
    out("---")
    out("")

    out("## فهرست دامنه‌ها")
    out("")
    out("| دامنه | جدول | سطر | کاربرد |")
    out("|---|---:|---:|---|")
    for title, intro, tables in domains:
        tables = [t for t in tables if t in schema]
        rows = sum(schema[t]["rows"] for t in tables)
        out("| [%s](#%s) | %d | %s | %s |"
            % (title, anchor(title), len(tables), "{:,}".format(rows), intro))
    out("")
    out("---")
    out("")

    for title, intro, tables in domains:
        tables = [t for t in tables if t in schema]
        out("## %s" % title)
        out("")
        out(intro)
        out("")
        out("| جدول | سطر | ستون | کاربرد | API |")
        out("|---|---:|---:|---|---|")
        for table in sorted(tables, key=lambda name: -schema[name]["rows"]):
            reached = by_table.get(table, [])
            out("| [`%s`](#%s) | %s | %d | %s | %s |"
                % (table, anchor(table), "{:,}".format(schema[table]["rows"]),
                   len(schema[table]["columns"]),
                   PURPOSE.get(table, "**توضیح ثبت‌نشده**"),
                   ("%d endpoint" % len(reached)) if reached else "—"))
        out("")
        for table in sorted(tables, key=lambda name: -schema[name]["rows"]):
            meta = schema[table]
            out("### `%s`" % table)
            out("")
            out(PURPOSE.get(table, "**توضیح ثبت‌نشده**"))
            if meta.get("comment"):
                out("")
                out("> %s" % " ".join(meta["comment"].split()))
            out("")
            out("`%s` سطر · `%d` ستون" % ("{:,}".format(meta["rows"]), len(meta["columns"])))
            out("")
            out("| ستون | نوع | الزامی | کلید | معنا |")
            out("|---|---|:--:|:--:|---|")
            for column in meta["columns"]:
                text = describer.describe(table, column)
                note = constraint_note(meta, column["name"])
                if note:
                    text = "%s<br>*%s*" % (text, note)
                default = column.get("default") or ""
                if default and "nextval" not in default:
                    default = re.sub(r"::[a-zA-Z ]+", "", default).strip()
                    if len(default) < 40:
                        text = "%s<br>پیش‌فرض: `%s`" % (text, default)
                key = "FK" if column.get("fk") else ("PK" if column["name"] == "id" else "")
                out("| `%s` | `%s` | %s | %s | %s |"
                    % (column["name"], column["type"],
                       "بله" if column["notnull"] else "—", key, text))
            out("")
            if by_table.get(table):
                out("**API:** " + " · ".join(by_table[table]))
                out("")
        out("---")
        out("")

    out("## فهرست کامل API")
    out("")
    out("%d مسیر، همه زیر `%s`." % (len(endpoints), BASE_PATH))
    out("")
    out("ستون «جدول‌ها» از روی repositoryای ساخته شده که به هر service تزریق می‌شود، پس "
        "در سطح **service** دقیق است: جدول‌هایی که آن service می‌تواند بخواند یا بنویسد. "
        "تضمین نمی‌کند که این endpoint خاص به تک‌تک آن‌ها دست می‌زند — مثلاً یک `GET` "
        "جدولی را فقط می‌خواند، هرچند هم‌سرویسِ آن `POST` همان جدول را می‌نویسد.")
    out("")
    out("| متد | مسیر | service | جدول‌ها |")
    out("|---|---|---|---|")
    for endpoint in endpoints:
        out("| `%s` | `%s` | %s | %s |"
            % (endpoint["verb"], endpoint["path"],
               ", ".join(s.replace("_service", "") for s in endpoint["services"]) or "—",
               ", ".join("`%s`" % t for t in endpoint["tables"]) or "—"))
    out("")
    out("---")
    out("")

    out("## پوشش توضیحات")
    out("")
    out("| منبع توضیح | ستون |")
    out("|---|---:|")
    labels = {"db": "COMMENT خودِ دیتابیس", "hand": "نوشتهٔ دستی، مخصوص همان جدول",
              "fk": "از روی کلید خارجی", "generic": "قاعدهٔ عمومی نام ستون",
              "suffix": "از روی پسوند نام ستون", "none": "**ثبت‌نشده**"}
    for source, count in describer.sources.most_common():
        out("| %s | %d |" % (labels.get(source, source), count))
    out("| **جمع** | **%d** |" % sum(describer.sources.values()))
    out("")
    if describer.missing:
        out("### ستون‌های بدون توضیح (%d)" % len(describer.missing))
        out("")
        out("این‌ها حدس زده نشده‌اند. برای تکمیل، یا توضیح را به `MEANING` در "
            "`scripts/generate_schema_doc.py` اضافه کنید، یا `COMMENT ON COLUMN` را در "
            "یک مهاجرت ثبت کنید تا سند دفعهٔ بعد خودش آن را بردارد.")
        out("")
        for start in range(0, len(describer.missing), 6):
            out("- " + " · ".join("`%s`" % m for m in describer.missing[start:start + 6]))
        out("")
    return "\n".join(lines) + "\n", describer


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dsn", help="پیش‌فرض: FINANCE_DEV_DSN")
    parser.add_argument("--out", default=str(DOC_PATH))
    arguments = parser.parse_args()

    dsn = arguments.dsn
    if not dsn:
        from devhost.environment import database_url
        dsn = database_url()

    schema, migration, database = read_schema(dsn)
    endpoints = endpoints_of(read_api()(set(schema)))
    text, describer = render(schema, migration, database, endpoints)
    Path(arguments.out).write_text(text, encoding="utf-8")

    print("%s نوشته شد" % arguments.out)
    print("  %d جدول · %d ستون · %d endpoint"
          % (len(schema), sum(len(t["columns"]) for t in schema.values()), len(endpoints)))
    if describer.missing:
        print("  %d ستون بدون توضیح" % len(describer.missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
