from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .progress import consumed_quantity

IRR = Decimal("1")
ZERO = Decimal(0)


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
                warnings.append({"code":"UNIT_CONVERSION_MISSING","message":"Purchased quantity was excluded because its unit cannot be converted.","estimateLineId":str(row["estimate_line_id"]) if row.get("estimate_line_id") else None,"resourceId":str(row["resource_id"]),"resourceCode":row.get("resource_code"),"activityExternalId":None,"severity":"warning","excludedFromCalculation":True,"affectedMetricKeys":["moneyRequiredToContinueIrr","forecastFinalCostIrr"]})
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
    progress_quality={"complete":True,"manualOverrideCount":0,"taskFallbackCount":0,"missingCount":0,"assignmentActualCount":0,"assignmentPercentFallbackCount":0}
    for row in estimate_rows:
        kind = row["resource_type"]
        original_price = Decimal(row["original_unit_price_irr"] or 0)
        if kind == "general_cost":
            original_amount = original_price
            revised_amount = money(row["revised_quantity"]) if row.get("revised_quantity") is not None else original_amount
            initial_total += original_amount; general_revised += revised_amount
            breakdown[kind]["initialEstimateIrr"] += original_amount
            breakdown[kind]["revisedEstimateIrr"] += revised_amount
            continue
        original_quantity = Decimal(row["original_quantity"] or 0)
        revised_quantity = Decimal(row["revised_quantity"] if row.get("revised_quantity") is not None else original_quantity)
        initial = money(original_quantity * original_price)
        revised_estimate = money(revised_quantity * original_price)
        initial_total += initial;breakdown[kind]["initialEstimateIrr"] += initial;breakdown[kind]["revisedEstimateIrr"] += revised_estimate
        assignment = assignment_by_id.get(row.get("assignment_external_id")) or assignment_by_activity.get(row.get("activity_external_id"))
        try: executed, _source = consumed_quantity(assignment) if assignment else (ZERO,"missing")
        except ValueError: executed = ZERO;_source="missing"
        if _source == "missing":
            progress_quality["missingCount"] += 1;progress_quality["complete"] = False
            warnings.append({"code":"PROGRESS_MISSING","message":"No valid progress quantity is available for this estimate line.","estimateLineId":str(row["id"]),"resourceId":str(row["resource_id"]),"resourceCode":row["resource_code"],"activityExternalId":row.get("activity_external_id"),"severity":"warning","excludedFromCalculation":False,"affectedMetricKeys":["currentExecutedValueIrr","remainingPhysicalCostIrr","forecastFinalCostIrr"]})
        elif _source == "manual_override": progress_quality["manualOverrideCount"] += 1
        elif _source == "task_progress_fallback": progress_quality["taskFallbackCount"] += 1;progress_quality["complete"] = False
        elif _source == "assignment_work_percent": progress_quality["assignmentPercentFallbackCount"] += 1;progress_quality["complete"] = False
        elif _source == "assignment_actual": progress_quality["assignmentActualCount"] += 1
        remaining = max(revised_quantity - executed, ZERO)
        if executed > revised_quantity:
            deviation=executed-revised_quantity
            percent=None if revised_quantity==0 else (deviation*Decimal(100)/revised_quantity).quantize(Decimal("0.0001"),rounding=ROUND_HALF_UP)
            warnings.append({"code":"QUANTITY_OVERRUN","message":"Executed quantity exceeds revised quantity.","estimateLineId":str(row["id"]),"resourceId":str(row["resource_id"]),"resourceCode":row["resource_code"],"activityExternalId":row.get("activity_external_id"),"severity":"warning","excludedFromCalculation":False,"affectedMetricKeys":["remainingPhysicalCostIrr","moneyRequiredToContinueIrr","forecastFinalCostIrr"],"deviationQuantity":format(deviation,"f"),"deviationPercent":None if percent is None else format(percent,"f")})
        current_price = row.get("current_unit_price_irr")
        if current_price is None:
            missing_price_count += 1
            excluded_estimate_line_ids.append(str(row["id"]))
            warnings.append({"code":"CURRENT_PRICE_MISSING","message":"Current price is missing; live-value metrics exclude this line.","estimateLineId":str(row["id"]),"resourceId":str(row["resource_id"]),"resourceCode":row["resource_code"],"activityExternalId":row.get("activity_external_id"),"severity":"warning","excludedFromCalculation":True,"affectedMetricKeys":["currentExecutedValueIrr","remainingPhysicalCostIrr","moneyRequiredToContinueIrr","forecastFinalCostIrr","forecastPerSquareMeterIrr"]})
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
        breakdown[kind]["remainingPhysicalCostIrr"] += remaining_cost;breakdown[kind]["forecastFinalIrr"] += required
        price_variance = remaining_cost - money(remaining * original_price)
        quantity_variance = revised_quantity - original_quantity
        linked_actual_line = actual_by_line.get(row["id"], ZERO)
        resource_remaining_actual = resource_actual_remaining.get(row["resource_id"], ZERO)
        resource_allocated_actual = resource_remaining_actual
        resource_actual_remaining[row["resource_id"]] = ZERO
        actual_line = linked_actual_line + resource_allocated_actual
        forecast_line = actual_line + remaining_cost
        price_percent = None if original_price == 0 else ((current - original_price) * Decimal(100) / original_price).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        quantity_percent = None if original_quantity == 0 else (quantity_variance * Decimal(100) / original_quantity).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        price_variances.append({"estimateLineId":str(row["id"]),"resourceId":str(row["resource_id"]),"resourceCode":row["resource_code"],"resourceTitle":row["resource_title"],"resourceType":kind,
            "activityExternalId":row.get("activity_external_id"),"activityTitle":row.get("activity_title"),"wbsCode":row.get("wbs_code"),"baseUnit":row.get("base_unit"),
            "revisedQuantity":revised_quantity,"remainingQuantity":remaining,"estimateBaseUnitPriceIrr":original_price,"currentUnitPriceIrr":None if current_price is None else current,
            "varianceIrr":price_variance,"priceVariancePercent":price_percent,"actualCostIrr":actual_line,"remainingPhysicalCostIrr":remaining_cost,
            "forecastFinalIrr":forecast_line,"impactSharePercent":None,"currentPriceScope":row.get("current_price_scope"),"currentPriceEffectiveFrom":row.get("current_price_effective_from"),
            "currentPriceVersionId":row.get("price_version_id"),"estimatePriceVersionId":row.get("estimate_version_id")})
        quantity_variances.append({"estimateLineId":str(row["id"]),"resourceId":str(row["resource_id"]),"resourceCode":row["resource_code"],"resourceTitle":row["resource_title"],"resourceType":kind,
            "activityExternalId":row.get("activity_external_id"),"activityTitle":row.get("activity_title"),"wbsCode":row.get("wbs_code"),"baseUnit":row.get("base_unit"),
            "initialQuantity":original_quantity,"revisedQuantity":revised_quantity,"executedQuantity":executed,"remainingQuantity":remaining,
            "varianceQuantity":quantity_variance,"quantityVariancePercent":quantity_percent,"sourceMethod":_source,"progressSnapshotId":row.get("progress_snapshot_id"),
            "actualCostIrr":actual_line,"remainingPhysicalCostIrr":remaining_cost,"forecastFinalIrr":forecast_line,"impactSharePercent":None})

    general_required = max(general_revised - actual_by_type["general_cost"], ZERO)
    breakdown["general_cost"]["remainingPhysicalCostIrr"] = general_required
    if actual_by_type["general_cost"] > general_revised: warnings.append({"code":"GENERAL_COST_OVERRUN","message":"General cost actual exceeds its revised estimate.","estimateLineId":None,"resourceId":None,"resourceCode":None,"activityExternalId":None,"severity":"warning","excludedFromCalculation":False,"affectedMetricKeys":["moneyRequiredToContinueIrr","forecastFinalCostIrr"]})
    money_required += general_required
    for kind in breakdown:
        breakdown[kind]["forecastFinalIrr"] += actual_by_type[kind]
    breakdown["general_cost"]["forecastFinalIrr"] += general_required
    forecast = actual_total + money_required
    area = None if gross_area is None else Decimal(gross_area)
    incomplete_metric_keys=[]
    if missing_price_count or missing_conversion_count:
        incomplete_metric_keys=["currentExecutedValueIrr","remainingPhysicalCostIrr","moneyRequiredToContinueIrr","forecastFinalCostIrr","forecastPerSquareMeterIrr"]
    if area is None or area <= 0:
        actual_per_area = forecast_per_area = None
        warnings.append({"code":"GROSS_AREA_MISSING","message":"Per-square-meter metrics are unavailable because gross built area is missing.","estimateLineId":None,"resourceId":None,"resourceCode":None,"activityExternalId":None,"severity":"warning","excludedFromCalculation":True,"affectedMetricKeys":["actualCostPerSquareMeterIrr","forecastPerSquareMeterIrr"]})
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
    total_impact = sum(abs(item["varianceIrr"]) for item in price_variances) + sum(abs(item["remainingPhysicalCostIrr"]) for item in quantity_variances)
    for item in price_variances:
        item["impactSharePercent"] = None if total_impact == 0 else (abs(item["varianceIrr"]) * Decimal(100) / total_impact).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    for item in quantity_variances:
        item["impactSharePercent"] = None if total_impact == 0 else (abs(item["remainingPhysicalCostIrr"]) * Decimal(100) / total_impact).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return LiveReport(metrics,list(breakdown.values()),price_variances[:10],quantity_variances[:10],price_variances,quantity_variances,warnings,"incomplete" if missing_price_count or missing_conversion_count else "complete",incomplete_metric_keys,missing_price_count,len(excluded_estimate_line_ids),excluded_estimate_line_ids,progress_quality)
