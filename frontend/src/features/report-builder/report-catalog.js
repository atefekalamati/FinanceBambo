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
    featured: true,
  },
  {
    key: "breakdown",
    category: "cost",
    title: "ترکیب هزینه به تفکیک نوع قلم",
    summary: "برآورد و هزینه واقعی مصالح، نیروی انسانی، تجهیزات و هزینه‌های عمومی",
    needs: ["overview"],
    period: false,
    featured: true,
  },
  {
    key: "monthly",
    category: "cost",
    title: "روند ماهانه هزینه",
    summary: "هزینه واقعی ثبت‌شده در هر ماه شمسی، به‌همراه تعداد اسناد و ابطال‌ها",
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
    featured: true,
  },
  {
    key: "quantityVariance",
    category: "deviation",
    title: "بیشترین انحراف مقدار",
    summary: "اقلامی که مقدار برآوردشان بیش از همه اصلاح شده است",
    needs: ["overview"],
    period: false,
    featured: true,
  },
  {
    key: "invoices",
    category: "documents",
    title: "فاکتورهای بازه",
    summary: "اسناد مالی با تاریخ داخل بازه، به‌همراه وضعیت، فروشنده و مبلغ",
    needs: ["invoices"],
    period: true,
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
    title: "هشدارهای کیفیت محاسبه",
    summary: "مواردی که سرویس مالی هنگام ساخت ارقام گزارش کرده است",
    needs: ["overview"],
    period: false,
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

  /* ── Declared, not yet producible ─────────────────────────────────────── */
  {
    key: "sCurve",
    category: "cost",
    title: "منحنی S مالی — برنامه در برابر عملکرد",
    summary: "هزینه برنامه‌ای و واقعی به‌صورت تجمعی روی دوره‌های پروژه",
    needs: ["monthly"],
    period: false,
    unavailable: "تا وقتی سرویس مالی دوره‌های زمانی و برآورد هر دوره را از فایل MSP استخراج نکند، مبنای برنامه‌ای برای این منحنی وجود ندارد.",
  },
  {
    key: "levelOne",
    category: "summary",
    title: "گزارش مالی مراحل سطح ۱",
    summary: "برآورد، ارزش کار انجام‌شده و هزینه واقعی هر مرحله از ساختار شکست کار",
    needs: ["overview"],
    period: false,
    unavailable: "این گزارش به جمع‌بندی مالی بر اساس مرحله سطح ۱ نیاز دارد که هنوز در سرویس مالی ساخته نشده است.",
  },
]);

export function reportsByCategory(categoryKey) {
  return REPORTS.filter((report) => report.category === categoryKey);
}

export function findReport(key) {
  return REPORTS.find((report) => report.key === key) ?? null;
}

/** The reports offered as chips on the overview, in catalogue order. */
export function featuredReports() {
  return REPORTS.filter((report) => report.featured && !report.unavailable);
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
