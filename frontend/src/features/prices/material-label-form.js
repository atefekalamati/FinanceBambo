import { element } from "../../shared/dom/elements.js";
import { formatJalaliBusinessDate } from "../../shared/formatters/display.js";

/* The form where a person says what a listing is.
 *
 * The sheet states no unit for six of its seven categories, so «لوله پلی اتیلن ۱۱۰»
 * arrives with a price and no basis at all. No category-wide setting can supply one — the
 * row beside it might be sold by the branch. This is where somebody looks at that row and
 * says: it is a pipe, the price is per metre, show it per metre.
 *
 * WHAT THIS FORM IS NOT
 *
 * It is not a price editor and cannot become one. There is no field here that writes a
 * number into an observation, and there is no way to reach one: a label is configuration,
 * and the imported row it describes is never touched. The worst a wrong label can do is
 * withhold a price or show it in the wrong unit — both visible, both correctable by a
 * newer version, and both leaving the original row exactly as the sheet sent it.
 *
 * UNITS COME FROM THE BACKEND
 *
 * Every option in every unit dropdown is a row of the Finance unit registry, fetched from
 * `/unit-registry`. Nothing here has a list of its own. A unit the backend does not define
 * cannot be chosen, which is what stops a label introducing a vocabulary of its own.
 */

/** What a price can be quoted per, in words, when it is not a unit the registry knows. */
const BASIS_HINT = "برای مثال: قیمت بابت هر شاخهٔ ۱۲ متری";

/** Why a factor is needed, by the kind of crossing it bridges. */
export const FACTOR_TYPES = Object.freeze([
  { value: "weight_per_piece", label: "وزن هر عدد" },
  { value: "weight_per_branch", label: "وزن هر شاخه" },
  { value: "length_per_branch", label: "طول هر شاخه" },
  { value: "mass_per_bag", label: "وزن هر کیسه" },
  { value: "area_per_piece", label: "مساحت هر عدد" },
  { value: "volume_per_piece", label: "حجم هر عدد" },
  { value: "other", label: "دیگر" },
]);

/**
 * A select whose options are the registry's units.
 *
 * `units` is what `/unit-registry` returned. An empty list is not filled with a guess: the
 * select renders disabled with a notice, because a dropdown offering units nobody defined
 * would be the frontend inventing a vocabulary.
 */
export function unitSelect(name, units, { selected = null, allowNone = true,
                                          disabled = false, label = "" } = {}) {
  const wrapper = element("label", "app-field");
  if (label) wrapper.append(element("span", "app-field__label", label));

  const select = element("select", "app-input");
  select.name = name;
  select.disabled = disabled || !units.length;

  if (!units.length) {
    const empty = element("option", "", "واحدی از سرور دریافت نشد");
    empty.value = "";
    select.append(empty);
    wrapper.append(select);
    wrapper.append(element("span", "app-field__hint",
      "فهرست واحدها از سرور می‌آید؛ تا وقتی دریافت نشود، انتخابی ممکن نیست."));
    return wrapper;
  }

  if (allowNone) {
    const none = element("option", "", "انتخاب نشده");
    none.value = "";
    select.append(none);
  }
  units.forEach((unit) => {
    const option = element("option", "", `${unit.label ?? unit.code} (${unit.code})`);
    option.value = unit.code;
    if (unit.code === selected) option.selected = true;
    select.append(option);
  });
  wrapper.append(select);
  return wrapper;
}

function textField(name, labelText, { value = "", hint = "", disabled = false,
                                      required = false } = {}) {
  const wrapper = element("label", "app-field");
  wrapper.append(element("span", "app-field__label", labelText));
  const input = element("input", "app-input");
  input.type = "text";
  input.name = name;
  input.value = value ?? "";
  input.disabled = disabled;
  if (required) input.required = true;
  wrapper.append(input);
  if (hint) wrapper.append(element("span", "app-field__hint", hint));
  return wrapper;
}

/**
 * The label form for one listing.
 *
 * `canEdit` is the only thing that decides whether anything can be changed. A reader
 * without `finance.edit` sees exactly the same values, every control disabled and no save
 * button — the same information, none of the authority. The backend refuses the write
 * regardless; this is so nobody is invited to try.
 */
export function renderLabelForm(row, { units = [], resources = [], current = null,
                                       canEdit = false, onSave = null,
                                       onCancel = null } = {}) {
  const form = element("form", "material-label-form");
  form.append(element("h3", "", `برچسب: ${row.name}`));
  form.append(element("p", "app-field__hint",
    "این برچسب توضیح می‌دهد این قلم چیست و قیمتش بابت چیست. ردیف وارد‌شده از برگه "
    + "تغییر نمی‌کند و هیچ قیمتی اینجا ساخته نمی‌شود."));

  /* What the sheet said, shown as read-only fact beside what a person may decide. Seeing
     both is the point: a label that contradicts the source should look like a decision. */
  const source = element("dl", "material-label-form__source");
  [["نام در برگه", row.name],
   ["دستهٔ برگه", row.category],
   ["منبع", row.providerName],
   ["واحد اعلامی برگه", row.sourceUnit ?? "اعلام نشده"],
   ["تاریخ برگه", row.workflowDateJalali
     ? (formatJalaliBusinessDate(row.workflowDateJalali) === "—"
       ? row.workflowDateJalali : formatJalaliBusinessDate(row.workflowDateJalali))
     : row.workflowDateRaw ?? "بدون تاریخ"]]
    .forEach(([term, value]) => {
      source.append(element("dt", "", term), element("dd", "", String(value)));
    });
  form.append(source);

  form.append(textField("label", "برچسب", {
    value: current?.label ?? "", disabled: !canEdit,
    hint: "نامی که این قلم را با آن می‌شناسید",
  }));
  form.append(textField("displayName", "نام نمایشی", {
    value: current?.displayName ?? "", disabled: !canEdit,
  }));
  form.append(textField("productType", "نوع محصول", {
    value: current?.productType ?? "", disabled: !canEdit,
  }));

  form.append(unitSelect("sourceUnit", units, {
    selected: current?.sourceUnit ?? null, disabled: !canEdit,
    label: "قیمت منبع بابت هر…",
  }));
  form.append(textField("sourceBasis", "مبنای قیمت (توضیحی)", {
    value: current?.sourceBasis ?? "", disabled: !canEdit, hint: BASIS_HINT,
  }));
  form.append(unitSelect("targetUnit", units, {
    selected: current?.targetUnit ?? null, disabled: !canEdit,
    label: "نمایش بر حسب",
  }));

  /* The mapping. Unapproved by default and it stays that way unless somebody ticks the
     box: a suggestion must not become the source of a Finance price by being saved. */
  const mapping = element("label", "app-field");
  mapping.append(element("span", "app-field__label", "قلم هزینهٔ مالی"));
  const resourceSelect = element("select", "app-input");
  resourceSelect.name = "financeResourceId";
  resourceSelect.disabled = !canEdit;
  const noResource = element("option", "", "وصل نشده");
  noResource.value = "";
  resourceSelect.append(noResource);
  resources.forEach((resource) => {
    const option = element("option", "",
      `${resource.title}${resource.baseUnit ? ` — ${resource.baseUnit}` : ""}`);
    option.value = resource.resourceId;
    if (resource.resourceId === current?.financeResourceId) option.selected = true;
    resourceSelect.append(option);
  });
  mapping.append(resourceSelect);
  form.append(mapping);

  const approve = element("label", "app-field app-field--inline");
  const approveBox = element("input", "");
  approveBox.type = "checkbox";
  approveBox.name = "mappingApproved";
  approveBox.checked = Boolean(current?.mappingApproved);
  approveBox.disabled = !canEdit;
  approve.append(approveBox, element("span", "", "این اتصال را تأیید می‌کنم"));
  approve.append(element("span", "app-field__hint",
    "تا وقتی تأیید نشود، قیمت این قلم برای محاسبات مالی استفاده نمی‌شود."));
  form.append(approve);

  const active = element("label", "app-field app-field--inline");
  const activeBox = element("input", "");
  activeBox.type = "checkbox";
  activeBox.name = "active";
  activeBox.checked = current ? Boolean(current.active) : true;
  activeBox.disabled = !canEdit;
  active.append(activeBox, element("span", "", "فعال"));
  form.append(active);

  form.append(textField("reason", "دلیل", {
    value: "", disabled: !canEdit, required: true,
    hint: "چرا این تصمیم گرفته شد. ثبت می‌شود و بعداً قابل بازبینی است.",
  }));

  if (current) {
    form.append(element("p", "app-field__hint",
      `نسخهٔ فعلی: ${current.version} — ثبت‌شده توسط ${current.actorName ?? current.actorId}`));
  }

  if (!canEdit) {
    form.append(element("p", "inline-notice",
      "برای ویرایش برچسب، دسترسی ویرایش مالی لازم است."));
    return form;
  }

  const actions = element("div", "material-label-form__actions");
  const save = element("button", "button button--primary", "ثبت برچسب");
  save.type = "submit";
  actions.append(save);
  if (onCancel) {
    const cancel = element("button", "button button--ghost", "انصراف");
    cancel.type = "button";
    cancel.addEventListener("click", onCancel);
    actions.append(cancel);
  }
  form.append(actions);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!onSave) return;
    onSave(readLabelForm(form));
  });
  return form;
}

/** The form's values, shaped for the adapter. Empty strings become null, not "". */
export function readLabelForm(form) {
  const value = (name) => {
    const field = form.querySelector(`[name="${name}"]`);
    const text = (field?.value ?? "").trim();
    return text || null;
  };
  const checked = (name) => Boolean(form.querySelector(`[name="${name}"]`)?.checked);
  return {
    label: value("label"),
    displayName: value("displayName"),
    productType: value("productType"),
    sourceUnit: value("sourceUnit"),
    sourceBasis: value("sourceBasis"),
    targetUnit: value("targetUnit"),
    financeResourceId: value("financeResourceId"),
    mappingApproved: checked("mappingApproved"),
    active: checked("active"),
    reason: value("reason") ?? "",
  };
}
