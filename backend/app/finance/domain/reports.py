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
    warnings: list[dict]


def calculate_live_report(estimate_rows, invoice_rows, assignments, conversions, gross_area):
    warnings = []
    assignment_by_id = {row.get("assignmentExternalId"): row for row in assignments if row.get("assignmentExternalId")}
    assignment_by_activity = {(row.get("task") or {}).get("activityCode"): row for row in assignments if (row.get("task") or {}).get("activityCode")}
    conversion_by_key = {(row["source_unit"], row["target_unit"], row["dimension"]): Decimal(row["factor"]) for row in conversions}
    purchased = {}
    actual_by_type = {kind: ZERO for kind in ("material", "labor", "equipment", "general_cost")}
    actual_total = ZERO
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
                warnings.append({"code":"UNIT_CONVERSION_MISSING","message":"Purchased quantity was excluded because its unit cannot be converted.","estimateLineId":str(row["estimate_line_id"]) if row.get("estimate_line_id") else None})
                continue
            quantity *= factor
        key = row.get("estimate_line_id") or row["resource_id"]
        purchased[key] = purchased.get(key, ZERO) + quantity

    breakdown = {kind:{"resourceType":kind,"initialEstimateIrr":ZERO,"actualCostIrr":actual_by_type[kind],"forecastFinalIrr":ZERO} for kind in actual_by_type}
    current_executed = remaining_physical_cost = money_required = initial_total = ZERO
    price_variances, quantity_variances = [], []
    general_revised = ZERO
    for row in estimate_rows:
        kind = row["resource_type"]
        original_price = Decimal(row["original_unit_price_irr"] or 0)
        if kind == "general_cost":
            original_amount = original_price
            revised_amount = money(row["revised_quantity"]) if row.get("revised_quantity") is not None else original_amount
            initial_total += original_amount; general_revised += revised_amount
            breakdown[kind]["initialEstimateIrr"] += original_amount
            continue
        original_quantity = Decimal(row["original_quantity"] or 0)
        revised_quantity = Decimal(row["revised_quantity"] if row.get("revised_quantity") is not None else original_quantity)
        initial = money(original_quantity * original_price)
        initial_total += initial;breakdown[kind]["initialEstimateIrr"] += initial
        assignment = assignment_by_id.get(row.get("assignment_external_id")) or assignment_by_activity.get(row.get("activity_external_id"))
        try: executed, _source = consumed_quantity(assignment) if assignment else (ZERO,"missing")
        except ValueError: executed = ZERO;_source="missing"
        if _source == "missing": warnings.append({"code":"PROGRESS_MISSING","message":"No valid progress quantity is available for this estimate line.","estimateLineId":str(row["id"])})
        remaining = max(revised_quantity - executed, ZERO)
        if executed > revised_quantity:
            deviation=executed-revised_quantity
            percent=None if revised_quantity==0 else (deviation*Decimal(100)/revised_quantity).quantize(Decimal("0.0001"),rounding=ROUND_HALF_UP)
            warnings.append({"code":"QUANTITY_OVERRUN","message":"Executed quantity exceeds revised quantity.","estimateLineId":str(row["id"]),"deviationQuantity":format(deviation,"f"),"deviationPercent":None if percent is None else format(percent,"f")})
        current_price = row.get("current_unit_price_irr")
        if current_price is None:
            warnings.append({"code":"CURRENT_PRICE_MISSING","message":"Current price is missing; live-value metrics exclude this line.","estimateLineId":str(row["id"])})
            current = ZERO
        else: current = Decimal(current_price)
        executed_value = money(executed * current); remaining_cost = money(remaining * current)
        current_executed += executed_value;remaining_physical_cost += remaining_cost
        bought = purchased.get(row["id"], purchased.get(row["resource_id"], ZERO))
        required_quantity = max(revised_quantity - bought, ZERO) if kind == "material" else remaining
        required = money(required_quantity * current);money_required += required
        breakdown[kind]["forecastFinalIrr"] += required
        price_variance = remaining_cost - money(remaining * original_price)
        quantity_variance = revised_quantity - original_quantity
        price_variances.append({"estimateLineId":str(row["id"]),"resourceId":str(row["resource_id"]),"resourceCode":row["resource_code"],"resourceTitle":row["resource_title"],"resourceType":kind,"varianceIrr":price_variance})
        quantity_variances.append({"estimateLineId":str(row["id"]),"resourceId":str(row["resource_id"]),"resourceCode":row["resource_code"],"resourceTitle":row["resource_title"],"resourceType":kind,"varianceQuantity":quantity_variance})

    general_required = max(general_revised - actual_by_type["general_cost"], ZERO)
    if actual_by_type["general_cost"] > general_revised: warnings.append({"code":"GENERAL_COST_OVERRUN","message":"General cost actual exceeds its revised estimate.","estimateLineId":None})
    money_required += general_required
    for kind in breakdown:
        breakdown[kind]["forecastFinalIrr"] += actual_by_type[kind]
    breakdown["general_cost"]["forecastFinalIrr"] += general_required
    forecast = actual_total + money_required
    area = None if gross_area is None else Decimal(gross_area)
    if area is None or area <= 0:
        actual_per_area = forecast_per_area = None
        warnings.append({"code":"GROSS_AREA_MISSING","message":"Per-square-meter metrics are unavailable because gross built area is missing.","estimateLineId":None})
    else:
        actual_per_area = money(actual_total / area);forecast_per_area = money(forecast / area)
    metrics = {"initialEstimateIrr":money(initial_total),"actualCostIrr":money(actual_total),
        "currentExecutedValueIrr":money(current_executed),"remainingPhysicalCostIrr":money(remaining_physical_cost),
        "moneyRequiredToContinueIrr":money(money_required),"forecastFinalCostIrr":money(forecast),
        "actualCostPerSquareMeterIrr":actual_per_area,"forecastPerSquareMeterIrr":forecast_per_area}
    price_variances.sort(key=lambda item:abs(item["varianceIrr"]),reverse=True)
    quantity_variances.sort(key=lambda item:abs(item["varianceQuantity"]),reverse=True)
    return LiveReport(metrics,list(breakdown.values()),price_variances[:10],quantity_variances[:10],warnings)
