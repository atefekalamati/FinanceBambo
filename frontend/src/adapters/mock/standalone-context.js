import { normalizeContext } from "../host/context-adapter.js";

const STANDALONE_CONTEXT = Object.freeze({
  userId: "00000000-0000-4000-8000-000000000001",
  organizationId: "00000000-0000-4000-8000-000000000002",
  organizationName: "سازمان نمایشی محلی",
  projectId: "finance_frontend_demo",
  projectName: "پروژه نمایشی Frontend",
  projectCode: "project-demo",
  grossBuiltArea: null,
  permissionCodes: ["finance.view", "finance.edit", "finance_report.view", "finance_report.export", "finance_report.issue"],
  locale: "fa-IR",
  timezone: "Asia/Tehran",
});

export function getStandaloneContext() {
  return normalizeContext(STANDALONE_CONTEXT);
}
