from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .progress import PROGRESS_FALLBACK, PROGRESS_MEASURED, resolve_progress_quantity

IRR = Decimal("1")
ZERO = Decimal(0)

#: What a line's executed quantity rests on. Five values in two groups.
#:
#: The line reached a source, and `domain/progress.py` says how far to trust what it said:
#:   measured -- the assignment stated the quantity, or a person did with an audit record
#:   fallback -- derived from a percentage, or taken from effort in an undeclared unit
#:
#: The line reached nothing, and each case needs a different person to fix it:
#:   unavailable         -- reached an assignment which reported nothing
#:   unmapped_assignment -- names an assignment that matched nothing: a broken reference
#:   unmapped_activity   -- reachable only through an activity that matched nothing, or
#:                          naming no identifier at all
#:
#: The group is the load-bearing part. Without it, executedQuantity 0 is ambiguous: it
#: could be a source that measured zero, or no source at all. With it, "measured" plus 0 is
#: a measured zero and any status in the second group plus 0 is an absence. The quantity is
#: the same either way -- what an absent measurement should do to the money is a product
#: decision, and this reports the situation rather than deciding it.
PROGRESS_UNMAPPED_ASSIGNMENT = "unmapped_assignment"
PROGRESS_UNMAPPED_ACTIVITY = "unmapped_activity"
PROGRESS_UNAVAILABLE = "unavailable"
PROGRESS_STATUSES = (PROGRESS_MEASURED, PROGRESS_FALLBACK, PROGRESS_UNAVAILABLE,
                     PROGRESS_UNMAPPED_ASSIGNMENT, PROGRESS_UNMAPPED_ACTIVITY)

#: The statuses that mean "no quantity was reported for this line". Named once so a caller
#: cannot ask the question with a different list.
PROGRESS_ABSENT = (PROGRESS_UNAVAILABLE, PROGRESS_UNMAPPED_ASSIGNMENT, PROGRESS_UNMAPPED_ACTIVITY)

#: Metrics that stop being trustworthy when a line's progress is unknown. All three
#: progress warnings claim the same list, so a reader cannot conclude that one kind of gap
#: threatens the forecast while another does not.
PROGRESS_AFFECTED_METRICS = ("currentExecutedValueIrr", "remainingPhysicalCostIrr",
                             "forecastFinalCostIrr")

#: The keys every warning carries. ReportWarning forbids extras, so a key invented at one
#: call site turns every report containing it into a 500 at response validation -- which is
#: what happened to deviationQuantity. Hence one constructor rather than eight hand-built
#: dicts, and EXTRA_WARNING_KEYS naming the only additions allowed.
WARNING_KEYS = ("code", "message", "estimateLineId", "resourceId", "resourceCode",
                "activityExternalId", "severity", "excludedFromCalculation", "affectedMetricKeys")

#: Per code, the keys that may appear beyond WARNING_KEYS. Anything else is a defect.
EXTRA_WARNING_KEYS = {"QUANTITY_OVERRUN": ("deviationQuantity", "deviationPercent"),
                      "PROGRESS_UNMAPPED": ("progressStatus",),
                      "PROGRESS_MISSING": ("progressStatus",),
                      "PROGRESS_WORK_NOT_QUANTITY": ("progressStatus",)}


def _warning(code, message, *, estimate_line_id=None, resource_id=None, resource_code=None,
             activity_external_id=None, excluded=False, affected=(), **extra):
    """One shape for every warning, so a new call site cannot invent a different one."""
    return {"code": code, "message": message, "estimateLineId": estimate_line_id,
            "resourceId": resource_id, "resourceCode": resource_code,
            "activityExternalId": activity_external_id, "severity": "warning",
            "excludedFromCalculation": excluded, "affectedMetricKeys": list(affected), **extra}


def _line_warning(row, code, message, *, excluded=False, affected=(), **extra):
    """A warning about one estimate line, identified the same way every time."""
    return _warning(code, message, estimate_line_id=str(row["id"]),
                    resource_id=str(row["resource_id"]), resource_code=row["resource_code"],
                    activity_external_id=row.get("activity_external_id"),
                    excluded=excluded, affected=affected, **extra)


def money(value):
    return Decimal(value).quantize(IRR, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class LiveReport:
    metrics: dict
    breakdown: list[dict]
    price_variances: list[dict]
    quantity_variances: list[dict]
    all_price_variances: list[dict]
    all_quantity_variances: list[dict]
    warnings: list[dict]
    calculation_status: str
    incomplete_metric_keys: list[str]
    missing_price_count: int
    excluded_estimate_line_count: int
    excluded_estimate_line_ids: list[str]
    progress_quality: dict


def calculate_live_report(estimate_rows, invoice_rows, assignments, conversions, gross_area):
    warnings = []
    assignment_by_id = {row.get("assignmentExternalId"): row for row in assignments if row.get("assignmentExternalId")}
    assignment_by_activity = {(row.get("task") or {}).get("activityCode"): row for row in assignments if (row.get("task") or {}).get("activityCode")}
    conversion_by_key = {(row["source_unit"], row["target_unit"], row["dimension"]): Decimal(row["factor"]) for row in conversions}
    purchased_by_line = {}
    purchased_by_resource = {}
    actual_by_type = {kind: ZERO for kind in ("material", "labor", "equipment", "general_cost")}
    actual_total = ZERO
    missing_conversion_count = 0
    missing_conversion_types = set()
    for row in invoice_rows:
        effect = Decimal(row["final_line_amount_irr"]) * Decimal(row["financial_effect_sign"])
        actual_total += effect
        actual_by_type[row["resource_type"]] += effect
        if row["resource_type"] == "general_cost" or row.get("quantity") is None: continue
        quantity = Decimal(row["quantity"]) * Decimal(row["financial_effect_sign"])
        source_unit, target_unit = row.get("unit"), row.get("base_unit")
        if source_unit != target_unit:
            factor = conversion_by_key.get((source_unit, target_unit, row.get("dimension")))
            if factor is None:
                missing_conversion_count += 1
                missing_conversion_types.add(row["resource_type"])
                warnings.append(_warning("UNIT_CONVERSION_MISSING","Purchased quantity was excluded because its unit cannot be converted.",
                    estimate_line_id=str(row["estimate_line_id"]) if row.get("estimate_line_id") else None,
                    resource_id=str(row["resource_id"]),resource_code=row.get("resource_code"),
                    excluded=True,affected=("moneyRequiredToContinueIrr","forecastFinalCostIrr")))
                continue
            quantity *= factor
        if row.get("estimate_line_id"):
            key = row["estimate_line_id"]
            purchased_by_line[key] = purchased_by_line.get(key, ZERO) + quantity
        else:
            key = row["resource_id"]
            purchased_by_resource[key] = purchased_by_resource.get(key, ZERO) + quantity

    actual_by_line = {};actual_by_resource = {}
    for row in invoice_rows:
        effect = Decimal(row["final_line_amount_irr"]) * Decimal(row["financial_effect_sign"])
        if row.get("estimate_line_id"):
            key = row["estimate_line_id"]
            actual_by_line[key] = actual_by_line.get(key, ZERO) + effect
        else:
            key = row["resource_id"]
            actual_by_resource[key] = actual_by_resource.get(key, ZERO) + effect
    breakdown = {kind:{"resourceType":kind,"initialEstimateIrr":ZERO,"revisedEstimateIrr":ZERO,"actualCostIrr":actual_by_type[kind],"remainingPhysicalCostIrr":ZERO,"forecastFinalIrr":ZERO} for kind in actual_by_type}
    current_executed = remaining_physical_cost = money_required = initial_total = ZERO
    price_variances, quantity_variances = [], []
    general_revised = ZERO;general_required = ZERO;missing_price_count=0
    excluded_estimate_line_ids=[];resource_purchase_remaining=dict(purchased_by_resource);resource_actual_remaining=dict(actual_by_resource)
    excluded_lines_by_type={kind:0 for kind in actual_by_type}
    # missingCount counts lines that DID match an assignment but had no usable quantity on
    # it. Lines that matched nothing are unmappedLineCount instead: the two need different
    # work from different people, so one number for both told the reader nothing.
    # mappedLineCount + unmappedLineCount + generalCostLineCount is every estimate line
    # read for this date. General cost is counted separately because progress is
    # meaningless for it, so it belongs in neither of the other two.
    progress_quality={"complete":True,"manualOverrideCount":0,"taskFallbackCount":0,"missingCount":0,"assignmentActualCount":0,"assignmentPercentFallbackCount":0,"mappedLineCount":0,"unmappedLineCount":0,"generalCostLineCount":0,"workAsQuantityCount":0,"unmappedAssignmentCount":0,"unmappedActivityCount":0}
    for row in estimate_rows:
        kind = row["resource_type"]
        original_price = Decimal(row["original_unit_price_irr"] or 0)
        if kind == "general_cost":
            progress_quality["generalCostLineCount"] += 1
            original_amount = original_price
            revised_amount = money(row["revised_quantity"]) if row.get("revised_quantity") is not None else original_amount
            initial_total += original_amount; general_revised += revised_amount
            breakdown[kind]["initialEstimateIrr"] += original_amount
            breakdown[kind]["revisedEstimateIrr"] += revised_amount
            linked_actual = actual_by_line.get(row["id"], ZERO)
            pooled_actual = resource_actual_remaining.get(row["resource_id"], ZERO)
            pooled_allocated = min(max(revised_amount - linked_actual, ZERO), pooled_actual) if pooled_actual > ZERO else ZERO
            resource_actual_remaining[row["resource_id"]] = pooled_actual - pooled_allocated
            line_actual = linked_actual + pooled_allocated
            general_required += max(revised_amount - line_actual, ZERO)
            if line_actual > revised_amount:
                warnings.append(_line_warning(row,"GENERAL_COST_OVERRUN","General cost actual exceeds its revised estimate.",affected=("moneyRequiredToContinueIrr","forecastFinalCostIrr")))
            continue
        original_quantity = Decimal(row["original_quantity"] or 0)
        revised_quantity = Decimal(row["revised_quantity"] if row.get("revised_quantity") is not None else original_quantity)
        initial = money(original_quantity * original_price)
        revised_estimate = money(revised_quantity * original_price)
        initial_total += initial;breakdown[kind]["initialEstimateIrr"] += initial;breakdown[kind]["revisedEstimateIrr"] += revised_estimate
        assignment = assignment_by_id.get(row.get("assignment_external_id")) or assignment_by_activity.get(row.get("activity_external_id"))
        # Three facts about the same line, deliberately separate. `_source` is the field the
        # number came from, `_measurement` is what kind of number it is, and `_status` is
        # whether there was a number at all -- so a reader can tell a measured zero from an
        # absent measurement, which `executed = ZERO` alone cannot say. The executed value
        # is the same in every branch below; only what the report says about it differs.
        _measurement = None
        if assignment is None:
            progress_quality["unmappedLineCount"] += 1
            executed = ZERO;_source = "unmapped"
            # Classified by the most specific identifier the line claims. A line naming an
            # assignment that matched nothing has a broken reference on the line itself; a
            # line without one was only ever findable through its activity, and a line
            # naming neither lands there too -- no activity could be found because none was
            # named. The two need different people to fix them, which is why one count for
            # both said nothing useful.
            _status = PROGRESS_UNMAPPED_ASSIGNMENT if row.get("assignment_external_id") else PROGRESS_UNMAPPED_ACTIVITY
            progress_quality["unmappedAssignmentCount" if _status == PROGRESS_UNMAPPED_ASSIGNMENT
                             else "unmappedActivityCount"] += 1
        else:
            progress_quality["mappedLineCount"] += 1
            try:
                resolved = resolve_progress_quantity(assignment)
                executed = resolved["effective_quantity"];_source = resolved["source_method"]
                _measurement = resolved["measurement_type"];_status = resolved["progress_status"]
            except ValueError: executed = ZERO;_source="missing";_status = PROGRESS_UNAVAILABLE
        if _source in ("missing","unmapped"):
            progress_quality["complete"] = False
            if _source == "unmapped":
                warnings.append(_line_warning(row,"PROGRESS_UNMAPPED","This estimate line is not linked to any assignment in the selected progress snapshot.",affected=PROGRESS_AFFECTED_METRICS,progressStatus=_status))
            else:
                progress_quality["missingCount"] += 1
                warnings.append(_line_warning(row,"PROGRESS_MISSING","The linked assignment carries no usable progress quantity for this estimate line.",affected=PROGRESS_AFFECTED_METRICS,progressStatus=_status))
        elif _source == "manual_override": progress_quality["manualOverrideCount"] += 1
        elif _source == "task_progress_fallback": progress_quality["taskFallbackCount"] += 1;progress_quality["complete"] = False
        elif _source == "assignment_work_percent": progress_quality["assignmentPercentFallbackCount"] += 1;progress_quality["complete"] = False
        elif _source == "assignment_actual": progress_quality["assignmentActualCount"] += 1
        if _measurement == "work_effort":
            # Effort reported as a quantity, about to be multiplied by a price per kg/m3/hour
            # a few lines below. The number is left exactly as it was -- see
            # domain/progress.py for why -- and the reader is told instead. This is counted
            # beside assignmentActualCount rather than instead of it: the value did come from
            # the assignment's actual, so that counter stays true and this one says which of
            # those actuals was effort.
            progress_quality["workAsQuantityCount"] += 1;progress_quality["complete"] = False
            warnings.append(_line_warning(row,"PROGRESS_WORK_NOT_QUANTITY","Executed quantity was taken from reported work effort, whose unit the progress source does not state.",affected=PROGRESS_AFFECTED_METRICS,progressStatus=_status))
        remaining = max(revised_quantity - executed, ZERO)
        if executed > revised_quantity:
            deviation=executed-revised_quantity
            percent=None if revised_quantity==0 else (deviation*Decimal(100)/revised_quantity).quantize(Decimal("0.0001"),rounding=ROUND_HALF_UP)
            warnings.append(_line_warning(row,"QUANTITY_OVERRUN","Executed quantity exceeds revised quantity.",
                affected=("remainingPhysicalCostIrr","moneyRequiredToContinueIrr","forecastFinalCostIrr"),
                deviationQuantity=format(deviation,"f"),deviationPercent=None if percent is None else format(percent,"f")))
        current_price = row.get("current_unit_price_irr")
        has_price = current_price is not None
        if current_price is None:
            missing_price_count += 1
            excluded_estimate_line_ids.append(str(row["id"]))
            excluded_lines_by_type[kind] += 1
            warnings.append(_line_warning(row,"CURRENT_PRICE_MISSING","Current price is missing; live-value metrics exclude this line.",excluded=True,
                affected=("currentExecutedValueIrr","remainingPhysicalCostIrr","moneyRequiredToContinueIrr","forecastFinalCostIrr","forecastPerSquareMeterIrr")))
            current = ZERO
        else: current = Decimal(current_price)
        executed_value = money(executed * current); remaining_cost = money(remaining * current)
        current_executed += executed_value;remaining_physical_cost += remaining_cost
        line_bought = purchased_by_line.get(row["id"], ZERO)
        resource_remaining_purchase = resource_purchase_remaining.get(row["resource_id"], ZERO)
        resource_allocated_purchase = min(max(revised_quantity - line_bought, ZERO), resource_remaining_purchase) if resource_remaining_purchase > 0 else ZERO
        resource_purchase_remaining[row["resource_id"]] = resource_remaining_purchase - resource_allocated_purchase
        bought = line_bought + resource_allocated_purchase
        required_quantity = max(revised_quantity - bought, ZERO) if kind == "material" else remaining
        required = money(required_quantity * current);money_required += required
        if has_price:
            breakdown[kind]["remainingPhysicalCostIrr"] += remaining_cost;breakdown[kind]["forecastFinalIrr"] += required
        price_variance = remaining_cost - money(remaining * original_price) if has_price else ZERO
        quantity_variance = revised_quantity - original_quantity
        linked_actual_line = actual_by_line.get(row["id"], ZERO)
        resource_remaining_actual = resource_actual_remaining.get(row["resource_id"], ZERO)
        resource_allocated_actual = resource_remaining_actual
        resource_actual_remaining[row["resource_id"]] = ZERO
        actual_line = linked_actual_line + resource_allocated_actual
        forecast_line = actual_line + remaining_cost
        price_percent = None if original_price == 0 else ((current - original_price) * Decimal(100) / original_price).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        quantity_percent = None if original_quantity == 0 else (quantity_variance * Decimal(100) / original_quantity).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        price_variances.append({"varianceKind":"price","estimateLineId":str(row["id"]),"resourceId":str(row["resource_id"]),"resourceCode":row["resource_code"],"resourceTitle":row["resource_title"],"resourceType":kind,
            "activityExternalId":row.get("activity_external_id"),"activityTitle":row.get("activity_title"),"wbsCode":row.get("wbs_code"),"baseUnit":row.get("base_unit"),
            "revisedQuantity":revised_quantity,"remainingQuantity":remaining,"estimateBaseUnitPriceIrr":original_price,"currentUnitPriceIrr":None if current_price is None else current,
            "varianceIrr":price_variance,"priceVariancePercent":price_percent,"actualCostIrr":actual_line,"remainingPhysicalCostIrr":remaining_cost if has_price else None,
            "forecastFinalIrr":forecast_line if has_price else None,"priceAvailable":has_price,"impactSharePercent":None,"currentPriceScope":row.get("current_price_scope"),"currentPriceEffectiveFrom":row.get("current_price_effective_from"),
            "currentPriceVersionId":row.get("price_version_id"),"estimatePriceVersionId":row.get("estimate_version_id")})
        quantity_variances.append({"varianceKind":"quantity","estimateLineId":str(row["id"]),"resourceId":str(row["resource_id"]),"resourceCode":row["resource_code"],"resourceTitle":row["resource_title"],"resourceType":kind,
            "activityExternalId":row.get("activity_external_id"),"activityTitle":row.get("activity_title"),"wbsCode":row.get("wbs_code"),"baseUnit":row.get("base_unit"),
            "initialQuantity":original_quantity,"revisedQuantity":revised_quantity,"executedQuantity":executed,"remainingQuantity":remaining,
            "varianceQuantity":quantity_variance,"quantityVariancePercent":quantity_percent,"sourceMethod":_source,"measurementType":_measurement,"progressStatus":_status,"progressSnapshotId":row.get("progress_snapshot_id"),
            "actualCostIrr":actual_line,"remainingPhysicalCostIrr":remaining_cost if has_price else None,"forecastFinalIrr":forecast_line if has_price else None,
            "priceAvailable":has_price,"impactSharePercent":None})

    breakdown["general_cost"]["remainingPhysicalCostIrr"] = general_required
    money_required += general_required
    for kind in breakdown:
        breakdown[kind]["forecastFinalIrr"] += actual_by_type[kind]
    breakdown["general_cost"]["forecastFinalIrr"] += general_required
    for kind in breakdown:
        breakdown[kind]["excludedEstimateLineCount"] = excluded_lines_by_type[kind]
        breakdown[kind]["calculationStatus"] = "incomplete" if excluded_lines_by_type[kind] or kind in missing_conversion_types else "complete"
    forecast = actual_total + money_required
    area = None if gross_area is None else Decimal(gross_area)
    incomplete_metric_keys=[]
    if missing_price_count or missing_conversion_count:
        incomplete_metric_keys=["currentExecutedValueIrr","remainingPhysicalCostIrr","moneyRequiredToContinueIrr","forecastFinalCostIrr","forecastPerSquareMeterIrr"]
    if area is None or area <= 0:
        actual_per_area = forecast_per_area = None
        warnings.append(_warning("GROSS_AREA_MISSING","Per-square-meter metrics are unavailable because gross built area is missing.",
            excluded=True,affected=("actualCostPerSquareMeterIrr","forecastPerSquareMeterIrr")))
    else:
        actual_per_area = money(actual_total / area);forecast_per_area = money(forecast / area)
    metrics = {"initialEstimateIrr":money(initial_total),"actualCostIrr":money(actual_total),
        "currentExecutedValueIrr":None if missing_price_count else money(current_executed),
        "remainingPhysicalCostIrr":None if missing_price_count else money(remaining_physical_cost),
        "moneyRequiredToContinueIrr":None if missing_price_count or missing_conversion_count else money(money_required),
        "forecastFinalCostIrr":None if missing_price_count or missing_conversion_count else money(forecast),
        "actualCostPerSquareMeterIrr":actual_per_area,
        "forecastPerSquareMeterIrr":None if missing_price_count or missing_conversion_count else forecast_per_area}
    price_variances.sort(key=lambda item:abs(item["varianceIrr"]),reverse=True)
    quantity_variances.sort(key=lambda item:abs(item["varianceQuantity"]),reverse=True)
    total_impact = sum(abs(item["varianceIrr"]) for item in price_variances) + sum(abs(item["remainingPhysicalCostIrr"] or ZERO) for item in quantity_variances)
    for item in price_variances:
        item["impactSharePercent"] = None if total_impact == 0 or not item["priceAvailable"] else (abs(item["varianceIrr"]) * Decimal(100) / total_impact).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    for item in quantity_variances:
        item["impactSharePercent"] = None if total_impact == 0 or not item["priceAvailable"] else (abs(item["remainingPhysicalCostIrr"] or ZERO) * Decimal(100) / total_impact).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return LiveReport(metrics,list(breakdown.values()),price_variances[:10],quantity_variances[:10],price_variances,quantity_variances,warnings,"incomplete" if missing_price_count or missing_conversion_count else "complete",incomplete_metric_keys,missing_price_count,len(excluded_estimate_line_ids),excluded_estimate_line_ids,progress_quality)
