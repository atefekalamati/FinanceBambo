import { compareWbsCodes } from "../../shared/reports/wbs-rollup.js";

/* Grouping the invoice line's targets by the project stage they belong to.
 *
 * WHY THIS EXISTS, AND WHAT IT DELIBERATELY DOES NOT DO
 * A stage is never STORED against an invoice line. The line points at an estimate line,
 * the estimate line names its activity, and the activity carries the WBS code -- that
 * chain already reaches «گزارش مالی سطح ۱» and it is the one the reports compute from.
 * Asking a person to tag a stage as well would put the same fact in two places, and the
 * day the schedule is re-imported and an activity moves, the two would disagree with no
 * rule for deciding which one the chart should believe.
 *
 * So the stage here is a FILTER, not a field. It narrows 835 estimate lines to the few
 * dozen of one stage, and then falls away. Nothing it produces is sent to the service.
 *
 * WHICH SEGMENTS ARE THE STAGE
 * Whatever the level-one report draws, because that is the whole claim this makes: pick
 * the stage you see on the chart. On the audited project the chart's stages are «۱.۵»,
 * «۱.۶», «۱.۷» -- TWO segments -- because the entire project hangs under a single «۱»,
 * and an activity's code is the full path beneath it («۱.۱۱.۱.۲», four deep).
 *
 * This read the FIRST segment, which on that shape is «۱» for every line in the project:
 * one group of 835, which is the flat list this module exists to break up, wearing a
 * stage's name. The depth is named once, here, and `STAGE_DEPTH` is the only thing to
 * change if a project's chart is ever drawn at another level.
 */

/** How many leading segments of an activity's code name the stage the chart draws. */
const STAGE_DEPTH = 2;

/** Targets with no estimate line at all. Real money, and no stage can be derived for it. */
export const GENERAL_COST_STAGE = "general_cost";

/** An estimate line whose activity states no WBS code. Neither the reader's fault nor fixable here. */
export const UNSTAGED = "unstaged";

/** The stage an activity's WBS code belongs to, or null when it states none. */
export function stageCodeOf(wbsCode) {
  const parts = String(wbsCode ?? "").trim().split(".").map((part) => part.trim()).filter(Boolean);
  if (!parts.length) return null;
  /* A code shallower than a stage IS its own stage rather than nothing: «۱.۳» has one
     estimate line on this project and «۱.۱» has one, and dropping them would lose a real
     row to a rule about depth. */
  return parts.slice(0, STAGE_DEPTH).join(".");
}

/** Which group a target sits in. Every target sits in exactly one. */
export function stageOf(target) {
  if (target?.targetType === "general_cost") return GENERAL_COST_STAGE;
  return stageCodeOf(target?.wbsCode ?? target?.stageCode) ?? UNSTAGED;
}

/**
 * The stages present in `targets`, in the order the structure reads.
 *
 * Only stages that HAVE targets appear: a stage with nothing to bill against is a choice
 * that leads to an empty list, and offering it is offering a dead end. The two groups
 * that are not stages come last, and in that order -- «بدون مرحله» is a data gap someone
 * can fix upstream, general cost is a deliberate choice the reader makes.
 *
 * @returns {{value: string, title: string|null, count: number, kind: string}[]}
 */
export function buildStageIndex(targets = []) {
  const groups = new Map();
  for (const target of targets) {
    const value = stageOf(target);
    const group = groups.get(value)
      ?? { value, title: null, count: 0, kind: value === GENERAL_COST_STAGE ? "general" : value === UNSTAGED ? "unstaged" : "stage" };
    group.count += 1;
    // The first non-empty title wins and later ones are ignored. Every line of one stage
    // reports the same stage title, so a disagreement would be a service fault; picking
    // one quietly is better here than rendering a select that changes its own labels.
    if (!group.title && target?.stageTitle) group.title = String(target.stageTitle);
    groups.set(value, group);
  }
  const stages = [...groups.values()];
  const ordered = stages.filter((group) => group.kind === "stage")
    .sort((left, right) => compareWbsCodes(left.value, right.value));
  return [
    ...ordered,
    ...stages.filter((group) => group.kind === "unstaged"),
    ...stages.filter((group) => group.kind === "general"),
  ];
}

/** The targets of one group, in the order they arrived. */
export function targetsInStage(targets = [], stageValue) {
  if (!stageValue) return [];
  return targets.filter((target) => stageOf(target) === stageValue);
}
