/**
 * Everything the report builder can put in a document, declared in one place.
 *
 * The catalogue is data, not behaviour: it says what a report is called, which
 * question it answers, which datasets it needs and whether the chosen period
 * changes it. How each one is drawn lives beside the page that draws it. That
 * separation is the point — a report that cannot be produced yet still belongs
 * in the catalogue, marked with the reason, so the reader learns what is coming
 * instead of finding a gap; and a report that arrives with a future feature is
 * one entry here plus one renderer, never a change to the builder itself.
 *
 * `needs` is the contract with the page: it names the datasets to fetch, and
 * nothing is fetched that no chosen report asked for.
 */

export const REPORT_CATEGORIES = Object.freeze([
  { key: "completion", title: "بودجه و تکمیل پروژه", description: "بودجه ادامه کار و شاخص‌های هزینه هر مترمربع" },
  { key: "controls", title: "پیگیری اقلام و اسناد", description: "قیمت‌های ناموجود، اسناد منتظر تأیید و اصلاحات مالی" },
  { key: "summary", title: "خلاصهٔ مدیریتی", description: "تصویر کلی وضعیت مالی پروژه در یک نگاه" },
  { key: "cost", title: "هزینه‌ها", description: "ترکیب و روند هزینه‌های ثبت‌شده" },
  { key: "deviation", title: "انحرافات", description: "اقلامی که از برآورد خود فاصله گرفته‌اند" },
  { key: "documents", title: "اسناد و رویدادها", description: "فاکتورها و تغییرات ثبت‌شده در بازه" },
  { key: "basis", title: "مبنای محاسبه", description: "قیمت‌ها، برآوردها و کیفیت داده‌ای که ارقام از آن ساخته شده‌اند" },
]);

/**
 * `period: true` means the chosen range changes what the report says. A report
 * without it is a picture taken at the reporting date, and the range does not
 * apply to it — the document says which is which rather than implying that
 * every page covers the same window.
 */
export const REPORTS = Object.freeze([
  {
    key: "overview",
    category: "summary",
    title: "خلاصه وضعیت مالی پروژه",
    summary: "برآورد اولیه، هزینه واقعی، ارزش کار انجام‌شده، پیش‌بینی نهایی و بودجه موردنیاز",
    needs: ["overview"],
    period: false,
    featured: true,
  },
  {
    key: "deviation",
    category: "summary",
    title: "انحراف پیش‌بینی از برآورد اولیه",
    summary: "فاصله پیش‌بینی هزینه نهایی از برآورد اولیه پروژه و جهت آن",
    needs: ["overview"],
    period: false,
    featured: false,
  },
  {
    key: "monthly",
    category: "cost",
    title: "روند ماهانه هزینه و برآورد",
    summary: "روند هزینه واقعی هر ماه و مقایسه آن با برآورد همان ماه",
    needs: ["monthly"],
    period: false,
    featured: true,
  },
  {
    key: "priceVariance",
    category: "deviation",
    title: "بیشترین انحراف قیمت",
    summary: "اقلامی که تغییر قیمتشان بیشترین اثر را بر برآورد پروژه گذاشته است",
    needs: ["overview"],
    period: false,
    featured: false,
  },
  {
    key: "quantityVariance",
    category: "deviation",
    title: "بیشترین انحراف مقدار",
    summary: "اقلامی که مقدار برآوردشان بیش از همه اصلاح شده است",
    needs: ["overview"],
    period: false,
    featured: false,
  },
  {
    key: "invoices",
    category: "documents",
    title: "فاکتورها و اسناد مالی",
    summary: "تمام اسناد بازه، وضعیت تأیید، اسناد برگشت و اصلاحی، فروشنده و مبلغ",
    needs: ["invoices"],
    period: true,
    featured: true,
  },
  {
    key: "auditEvents",
    category: "documents",
    title: "رویدادهای مالی بازه",
    summary: "اصلاحات، تأییدها و عملیات حساس ثبت‌شده در بازه",
    needs: ["audit"],
    period: true,
  },
  {
    key: "warnings",
    category: "basis",
    title: "کیفیت داده و محاسبات",
    summary: "کامل‌بودن محاسبات، کیفیت پیشرفت، قیمت‌های ناموجود و ردیف‌های کنارگذاشته‌شده",
    needs: ["overview"],
    period: false,
    featured: true,
  },
  {
    key: "prices",
    category: "basis",
    title: "جدول قیمت روز اقلام",
    summary: "قیمت پایه سازمان، قیمت اختصاصی پروژه و قیمت روز هر قلم",
    needs: ["prices"],
    period: false,
  },
  {
    key: "estimateLines",
    category: "basis",
    title: "ریز برآورد پروژه",
    summary: "مقدار اولیه و آخرین مقدار اصلاح‌شده هر ردیف برآورد",
    needs: ["financialItems"],
    period: false,
  },

  {
    key: "sCurve",
    category: "cost",
    title: "منحنی S مالی",
    summary: "روند تجمعی هزینه واقعی در بازه موجود؛ مقایسه با برنامه فقط در صورت وجود مبنای کامل",
    needs: ["monthly", "schedule"],
    period: false,
    featured: true,
  },
  {
    key: "levelOne",
    category: "summary",
    title: "گزارش مالی مراحل سطح ۱",
    summary: "برآورد اولیه و اصلاح‌شده، هزینه واقعی، باقیمانده، بودجه تکمیل و پیش‌بینی هر مرحله، با جزئیات تخصیص",
    needs: ["wbs"],
    period: false,
    featured: true,
  },
  {
    key: "completionBudget", category: "completion", title: "بودجه موردنیاز تا تکمیل",
    summary: "هزینه واقعی، هزینه کار باقی‌مانده، بودجه ادامه و پیش‌بینی نهایی؛ مطابق محاسبه سرویس",
    needs: ["overview"], period: false,
  },
  {
    key: "areaCosts", category: "completion", title: "هزینه واقعی و پیش‌بینی هر مترمربع",
    summary: "شاخص‌های هر مترمربع با مبالغ کل متناظر؛ بدون حدس‌زدن زیربنا یا جایگزینی مقدار ناموجود",
    needs: ["overview"], period: false,
  },
  {
    key: "unpricedItems", category: "controls", title: "اقلام بدون قیمت روز",
    summary: "فهرست اقلام فاقد قیمت جاری برای پیگیری تکمیل اطلاعات مالی",
    needs: ["prices"], period: false,
  },
  {
    key: "supplierDocuments", category: "documents", title: "اسناد به تفکیک فروشنده",
    summary: "تعداد و جمع مبلغ اسناد هر نام فروشنده، جداشده بر اساس وضعیت و منبع سند؛ نه مانده بدهی",
    needs: ["invoices"], period: true,
  },
  {
    key: "pendingDocuments", category: "controls", title: "اسناد در انتظار تأیید",
    summary: "پیش‌نویس‌ها و اسناد منتظر تأیید در بازه؛ بدون اثر مالی تا تأیید نهایی",
    needs: ["invoices"], period: true,
  },
  {
    key: "correctiveDocuments", category: "controls", title: "اسناد برگشت و اصلاحی",
    summary: "اسناد اصلاح و برگشت در بازه، با شماره و ارجاع به سند اصلی",
    needs: ["invoices"], period: true,
  },
  {
    key: "estimateChanges", category: "basis", title: "تغییرات برآورد اولیه تا مقدار جاری",
    summary: "مقایسه ردیف‌های تغییرکرده با مقدار اولیه؛ این مقایسه جایگزین تاریخچه تمام بازنگری‌ها نیست",
    needs: ["financialItems"], period: false,
  },
  // The two the period report drew and nothing here did. They are the only
  // entries that read the project at two dates rather than one, which is what
  // makes a range mean something for them and why both are period: true.
  {
    key: "periodMetrics", category: "summary", title: "شاخص‌های مالی در ابتدا و پایان بازه",
    summary: "هر شاخص اصلی در دو سر بازه و تغییر آن؛ با تفکیک شاخص انباشتی از وضعیتی",
    needs: ["periodOverview"], period: true,
  },
  {
    key: "periodBreakdown", category: "cost", title: "تفکیک هزینه در بازه بر اساس نوع قلم",
    summary: "سهم مصالح، نیروی انسانی، تجهیزات و هزینه عمومی از آنچه همین بازه افزوده است",
    needs: ["periodOverview"], period: true,
  },
]);

export function reportsByCategory(categoryKey) {
  return REPORTS.filter((report) => report.category === categoryKey);
}

export function findReport(key) {
  return REPORTS.find((report) => report.key === key) ?? null;
}

/** The featured shortcuts; the full catalogue remains available in the chooser. */
export function featuredReports() {
  return ["overview", "levelOne", "sCurve", "warnings", "invoices", "monthly"]
    .map(findReport).filter((report) => report.featured && !report.unavailable);
}

/** Only what exists, only once, and always in the order the catalogue declares. */
export function normalizeSelection(keys = []) {
  const wanted = new Set(keys);
  return REPORTS.filter((report) => wanted.has(report.key) && !report.unavailable).map((report) => report.key);
}

/** The datasets a selection needs, so nothing else is requested. */
export function datasetsFor(keys = []) {
  const needed = new Set();
  normalizeSelection(keys).forEach((key) => findReport(key)?.needs.forEach((dataset) => needed.add(dataset)));
  return [...needed];
}

/** Whether the chosen range applies to anything in the selection. */
export function selectionUsesPeriod(keys = []) {
  return normalizeSelection(keys).some((key) => findReport(key)?.period);
}
