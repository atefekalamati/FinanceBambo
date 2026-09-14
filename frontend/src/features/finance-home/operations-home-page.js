import { element } from "../../shared/dom/elements.js";
import { createRequestState, REQUEST_STATUS } from "../../core/state/request-state.js";
import { defaultSnapshot } from "../../shared/progress/project-snapshot.js";
import { renderPageState } from "../../shared/components/page-state.js";
import { formatBusinessDate, formatDisplayNumber } from "../../shared/formatters/display.js";

/**
 * امور مالی — the operations home.
 *
 * This side is where the numbers are authored: items and estimates, day prices,
 * progress, the documents people upload, and the settings that change results.
 * It deliberately shows no charts. The figures those charts draw belong to the
 * report surface, and duplicating them here would create a second place to read
 * a total from — which is how two screens start disagreeing.
 *
 * What it does show is the state of the inputs, because that is what an operator
 * is here to act on: which progress snapshot the calculation currently rests on,
 * and whether it is the latest one available.
 */

const WORK_AREAS = Object.freeze([
  {
    key: "financial-items",
    title: "اقلام و برآورد",
    description: "اقلام پروژه، ریز برآورد، مقدار اولیه و اصلاحات ثبت‌شده",
    meta: "اقلام · برآورد · اصلاحات",
    href: "#finance/financial-items",
  },
  {
    key: "prices",
    title: "قیمت روز و تبدیل واحد",
    description: "قیمت پایه سازمان، قیمت اختصاصی پروژه و تاریخچه تغییر قیمت",
    meta: "قیمت روز · تاریخچه · واحد",
    href: "#finance/prices",
  },
  {
    key: "progress",
    title: "پیشرفت و مقادیر انجام‌شده",
    description: "نسخه‌های پیشرفت پروژه، کیفیت داده و اصلاح دستی مقدار",
    meta: "نسخه پیشرفت · مقدار انجام‌شده · هشدار",
    href: "#finance/progress",
  },
  {
    key: "audit",
    title: "تاریخچه تغییرات مالی",
    description: "ردیابی اصلاحات، تأییدها و عملیات حساس مالی",
    meta: "انجام‌دهنده · زمان · دلیل",
    href: "#finance/audit",
  },
  {
    key: "settings",
    title: "تنظیمات مالی پروژه",
    description: "زیربنای کل، قواعد تبدیل واحد و تاریخچه بازنگری‌ها",
    meta: "زیربنا · تبدیل واحد · بازنگری",
    href: "#finance/settings",
  },
]);

function createWorkAreaCard(area) {
  const card = element("article", "work-area-card");
  const marker = element("span", "work-area-card__marker", area.title.slice(0, 1));
  marker.setAttribute("aria-hidden", "true");
  const content = element("div");
  content.append(
    element("h2", "", area.title),
    element("p", "", area.description),
    element("span", "work-area-card__meta", area.meta),
  );
  const action = element("a", "button button--primary", "ورود");
  action.href = area.href;
  card.append(marker, content, action);
  return card;
}

export function createOperationsHomePage({ progressAdapter }) {
  const root = element("div", "finance-home-page operations-home-page");
  let state = createRequestState(REQUEST_STATUS.LOADING);

  async function load() {
    state = createRequestState(REQUEST_STATUS.LOADING);
    paint();
    try {
      // A project with no ready snapshot is not an empty page here. That is
      // precisely the state an operator opens امور مالی to fix, and the work
      // areas that fix it must stay reachable — so it is said in a notice, not
      // rendered as an empty state that hides them.
      const snapshots = await progressAdapter.getSnapshots();
      state = createRequestState(REQUEST_STATUS.SUCCESS, { snapshots });
    } catch (error) {
      state = createRequestState(error.status === 403 ? REQUEST_STATUS.DENIED : REQUEST_STATUS.ERROR, null, error);
    }
    paint();
  }

  function renderInputState(snapshots) {
    const section = element("section", "operations-input-state");
    section.setAttribute("aria-label", "وضعیت ورودی‌های محاسبه");
    // "ورودی محاسبه" must name the version the figures are actually computed from, so it
    // asks the same question the report pages ask rather than assuming the newest row.
    const latest = defaultSnapshot(snapshots);

    section.append(element("span", "operations-input-state__lead", "ورودی محاسبه"));
    const facts = element("dl", "operations-input-state__facts");
    const add = (label, value) => {
      const item = element("div");
      item.append(element("dt", "", label), element("dd", "", value));
      facts.append(item);
    };
    add("نسخه پیشرفت مبنا", latest ? formatBusinessDate(latest.reportingDate) : "ثبت نشده");
    add("نسخه‌های ثبت‌شده", formatDisplayNumber(String(snapshots.length)));
    if (latest?.sourceFileNameSafe) add("فایل مبدأ", latest.sourceFileNameSafe);
    section.append(facts);

    if (!latest) {
      const notice = element("p", "inline-notice", "تا وقتی نسخه پیشرفتی ثبت نشده باشد، شاخص‌های مالی قابل محاسبه نیستند.");
      notice.setAttribute("role", "status");
      section.append(notice);
    }
    return section;
  }

  function renderContent(data) {
    const fragment = document.createDocumentFragment();

    const header = element("header", "finance-page-header");
    header.append(element("h1", "finance-page-title", "امور مالی"));

    const areas = element("section", "work-area-grid");
    areas.setAttribute("aria-label", "بخش‌های امور مالی");
    WORK_AREAS.forEach((area) => areas.append(createWorkAreaCard(area)));

    fragment.append(header, renderInputState(data.snapshots), areas);
    return fragment;
  }

  function paint() {
    root.replaceChildren(renderPageState(state, { renderContent, onRetry: load }));
  }

  load();
  return root;
}
