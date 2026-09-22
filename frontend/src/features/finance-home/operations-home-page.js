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
    tags: ["اقلام پروژه", "برآورد مقدار", "اصلاحات"],
    href: "#finance/financial-items",
  },
  {
    key: "prices",
    title: "قیمت روز و تبدیل واحد",
    description: "قیمت پایه سازمان، قیمت اختصاصی پروژه و تاریخچه تغییر قیمت",
    tags: ["قیمت روز", "تبدیل واحد", "تاریخچه قیمت"],
    href: "#finance/prices",
  },
  {
    key: "progress",
    title: "پیشرفت و مقادیر انجام‌شده",
    description: "نسخه‌های پیشرفت پروژه، کیفیت داده و اصلاح دستی مقدار",
    tags: ["نسخه پیشرفت", "مقدار انجام‌شده", "هشدارها و کنترل کیفیت"],
    href: "#finance/progress",
  },
  {
    key: "audit",
    title: "تاریخچه تغییرات مالی",
    description: "ردیابی اصلاحات، تأییدها و عملیات حساس مالی",
    tags: ["انجام‌دهنده", "زمان", "جزئیات تغییرات"],
    href: "#finance/audit",
  },
  {
    key: "settings",
    title: "تنظیمات مالی پروژه",
    description: "زیربنای کل، قواعد تبدیل واحد و تاریخچه بازنگری‌ها",
    tags: ["زیربنای مالی", "قواعد تبدیل واحد", "تاریخچه بازنگری"],
    href: "#finance/settings",
  },
]);

const AREA_ICON_PATHS = Object.freeze({
  "financial-items": ["M8 4.5h8l4 4v11H8z", "M16 4.5v4h4", "M11 12h6", "M11 15.5h6"],
  prices: ["M7 3.5h10a2 2 0 0 1 2 2v15H5v-15a2 2 0 0 1 2-2Z", "M8 7h8v3H8z", "M8.5 14h1", "M12 14h1", "M15.5 14h1", "M8.5 17h1", "M12 17h1", "M15.5 17h1"],
  progress: ["M5 19V9", "M10 19V13", "M15 19V7", "M20 19V4"],
  audit: ["M3 12a9 9 0 1 0 3-6.7L3 8", "M3 3v5h5", "M12 7v5l4 2"],
  settings: ["M12.2 2h-.4a2 2 0 0 0-2 2v.2a2 2 0 0 1-1 1.7l-.4.3a2 2 0 0 1-2 0l-.2-.1a2 2 0 0 0-2.7.7l-.2.4A2 2 0 0 0 4 9.9l.2.1a2 2 0 0 1 1 1.7v.6a2 2 0 0 1-1 1.7l-.2.1a2 2 0 0 0-.7 2.7l.2.4a2 2 0 0 0 2.7.7l.2-.1a2 2 0 0 1 2 0l.4.3a2 2 0 0 1 1 1.7v.2a2 2 0 0 0 2 2h.4a2 2 0 0 0 2-2v-.2a2 2 0 0 1 1-1.7l.4-.3a2 2 0 0 1 2 0l.2.1a2 2 0 0 0 2.7-.7l.2-.4a2 2 0 0 0-.7-2.7l-.2-.1a2 2 0 0 1-1-1.7v-.6a2 2 0 0 1 1-1.7l.2-.1a2 2 0 0 0 .7-2.7l-.2-.4a2 2 0 0 0-2.7-.7l-.2.1a2 2 0 0 1-2 0l-.4-.3a2 2 0 0 1-1-1.7V4a2 2 0 0 0-2-2Z", "M9 12a3 3 0 1 0 6 0 3 3 0 0 0-6 0Z"],
});

function createAreaIcon(key) {
  const namespace = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(namespace, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  (AREA_ICON_PATHS[key] || []).forEach((pathData) => {
    const path = document.createElementNS(namespace, "path");
    path.setAttribute("d", pathData);
    svg.append(path);
  });
  return svg;
}

function createWorkAreaCard(area) {
  const card = element("article", `work-area-card work-area-card--${area.key}`);
  const marker = element("span", "work-area-card__marker");
  marker.setAttribute("aria-hidden", "true");
  marker.append(createAreaIcon(area.key));
  const content = element("div", "work-area-card__content");
  content.append(element("h2", "", area.title), element("p", "", area.description));
  const tags = element("ul", "work-area-card__tags");
  area.tags.forEach((tag) => tags.append(element("li", "", tag)));
  const action = element("a", "button button--primary work-area-card__action");
  action.href = area.href;
  action.append(element("span", "", "ورود به فضای کاری"), element("span", "work-area-card__arrow", "‹"));
  card.append(marker, content, tags, action);
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
    const section = element("details", "operations-input-state");
    section.setAttribute("aria-label", "وضعیت ورودی‌های محاسبه");
    // "ورودی محاسبه" must name the version the figures are actually computed from, so it
    // asks the same question the report pages ask rather than assuming the newest row.
    const latest = defaultSnapshot(snapshots);

    const trigger = element("summary", "operations-input-state__trigger");
    trigger.setAttribute("title", "نمایش اطلاعات ورودی محاسبه");
    trigger.append(
      element("span", "operations-input-state__dots", "•••"),
      element("span", "sr-only", "نمایش اطلاعات ورودی محاسبه"),
    );
    section.append(trigger);

    const facts = element("dl", "operations-input-state__facts");
    const add = (label, value) => {
      const item = element("div");
      item.append(element("dt", "", label), element("dd", "", value));
      facts.append(item);
    };
    add("ورودی محاسبه", latest ? "نسخه فعال" : "بدون نسخه فعال");
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

    const header = element("header", "finance-page-header operations-home-page__header");
    const heading = element("div", "operations-home-page__heading");
    heading.append(
      element("h1", "finance-page-title", "امور مالی"),
      element("p", "", "مدیریت مالی پروژه، برآوردها، قیمت‌ها و تنظیمات مرتبط"),
    );
    header.append(heading);

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
