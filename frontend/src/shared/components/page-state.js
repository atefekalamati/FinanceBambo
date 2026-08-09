import { REQUEST_STATUS } from "../../core/state/request-state.js";

function messageCard({ title, message, actionLabel, onAction, variant = "neutral" }) {
  const section = document.createElement("section");
  section.className = `state-card state-card--${variant}`;
  const heading = document.createElement("h2");
  heading.textContent = title;
  const paragraph = document.createElement("p");
  paragraph.textContent = message;
  section.append(heading, paragraph);
  if (actionLabel && onAction) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "button button--primary";
    button.textContent = actionLabel;
    button.addEventListener("click", onAction);
    section.append(button);
  }
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
      return messageCard({
        title: "دریافت اطلاعات انجام نشد",
        message: `${state.error?.message || "دوباره تلاش کنید."}${state.error?.requestId ? ` · شناسه درخواست: ${state.error.requestId}` : ""}`,
        actionLabel: "تلاش دوباره",
        onAction: onRetry,
        variant: "danger",
      });
    case REQUEST_STATUS.SUCCESS:
      return renderContent(state.data);
    default:
      return document.createDocumentFragment();
  }
}
