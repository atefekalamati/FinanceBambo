import { REQUEST_STATUS } from "../../core/state/request-state.js";
import { presentApiError } from "../errors/error-presentation.js";

function messageCard({ title, message, actionLabel, onAction, variant = "neutral", details = [], metadata = [] }) {
  const section = document.createElement("section");
  section.className = `state-card state-card--${variant}`;
  section.tabIndex = -1;
  section.setAttribute("role", variant === "danger" ? "alert" : "status");
  section.setAttribute("aria-live", variant === "danger" ? "assertive" : "polite");
  const heading = document.createElement("h2");
  heading.textContent = title;
  const paragraph = document.createElement("p");
  paragraph.textContent = message;
  section.append(heading, paragraph);
  if (details.length) {
    const list = document.createElement("ul");
    list.className = "state-card__details";
    details.forEach((detail) => {
      const item = document.createElement("li");
      item.textContent = detail;
      list.append(item);
    });
    section.append(list);
  }
  metadata.forEach(([label, value]) => {
    if (!value) return;
    const meta = document.createElement("small");
    meta.className = "state-card__meta numeric";
    meta.textContent = `${label}: ${value}`;
    section.append(meta);
  });
  if (actionLabel && onAction) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button button--primary";
    button.textContent = actionLabel;
    button.addEventListener("click", onAction);
    section.append(button);
  }
  if (variant === "danger") queueMicrotask(() => section.isConnected && section.focus());
  return section;
}

export function renderPageState(state, { renderContent, renderEmpty, onRetry } = {}) {
  switch (state.status) {
    case REQUEST_STATUS.LOADING:
      return messageCard({ title: "در حال بارگذاری", message: "اطلاعات مالی پروژه در حال دریافت است…" });
    case REQUEST_STATUS.EMPTY:
      return renderEmpty ? renderEmpty() : messageCard({ title: "داده‌ای ثبت نشده است", message: "برای این بخش هنوز اطلاعات مالی قابل نمایش وجود ندارد." });
    case REQUEST_STATUS.DENIED:
      return messageCard({ title: "دسترسی ندارید", message: "مجوز مالی یا دسترسی پروژه برای مشاهده این بخش کافی نیست.", variant: "danger" });
    case REQUEST_STATUS.ERROR:
      {
        const error = presentApiError(state.error);
        return messageCard({
          title: error.title,
          message: error.message,
          details: error.details,
          metadata: [["کد خطا", error.code], ["شناسه درخواست", error.requestId]],
          actionLabel: error.retryable && onRetry ? "تلاش دوباره" : null,
          onAction: error.retryable ? onRetry : null,
          variant: "danger",
        });
      }
    case REQUEST_STATUS.SUCCESS:
      return renderContent(state.data);
    default:
      return document.createDocumentFragment();
  }
}
