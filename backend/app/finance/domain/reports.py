from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from .progress import (PROGRESS_FALLBACK, PROGRESS_MEASURED, ProgressPairing, assignment_keys,
                       line_keys, resolve_progress_quantity)

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
#: The live-value metrics any price problem touches -- absent, or in a unit this line
#: cannot be crossed into. One tuple, because the two gates exclude the same line from the
#: same figures and a second copy is how they drift apart.
PRICE_AFFECTED_METRICS = ("currentExecutedValueIrr", "remainingPhysicalCostIrr",
                          "moneyRequiredToContinueIrr", "forecastFinalCostIrr",
                          "forecastPerSquareMeterIrr")

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
    #: Estimate lines that state no baseline of their own. The counterpart of
    #: `missing_price_count`, and the reason `initialEstimateIrr` is a subtotal rather
    #: than a total whenever it is not zero.
    missing_estimate_line_count: int
    excluded_estimate_line_count: int
    excluded_estimate_line_ids: list[str]
    progress_quality: dict
    #: Lines the published figures actually rest on, and lines the project has. The
    #: metrics are sums over the first; the second is what says how much of the project
    #: that is. Equal counts mean the figures are whole.
    computed_line_count: int = 0
    total_line_count: int = 0
    #: Lines the FORECAST rests on -- `moneyRequiredToContinueIrr` and
    #: `forecastFinalCostIrr`. A different set from `computed_line_count`, and the reason
    #: both are published: a material with a price and no measurement is in one and not the
    #: other, and one number could not say so.
    required_line_count: int = 0


def _calculation_status(missing_price_count, missing_conversion_count, progress_quality):
    """"complete" only when nothing the figures depend on was missing.

    Prices and unit conversions were always counted. PROGRESS was not, and that was the
    bug: the report could call itself complete while `progressQuality.complete` was false
    in the same payload -- announcing that figures built on lines whose executed quantity
    nobody could measure were final. A reader had no reason to look at the second field.

    The vocabulary is unchanged (`complete` / `incomplete`), because every consumer of
    this field is typed to those two; only the honesty of the answer changes.
    """
    if missing_price_count or missing_conversion_count:
        return "incomplete"
    return "complete" if progress_quality.get("complete", True) else "incomplete"


def calculate_live_report(estimate_rows, invoice_rows, assignments, conversions, gross_area,
                          corroborate_identity=False):
    warnings = []
    # `corroborate_identity` is set for a feed whose rows belong to a Finance source
    # version. Estimate lines carry identifiers from whatever schedule created them and
    # record no provenance, so against a NEW source a lone integer match is a collision
    # as often as a mapping; requiring both identifiers is what makes "mapped" mean it.
    pairing = ProgressPairing(assignments, assignment_keys, corroborate_identity)
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
    # A line can be excluded twice over -- no price AND no measurement. It is one excluded
    # line either way, and counting it twice would make `excludedEstimateLineCount` exceed
    # the number of lines that exist.
    excluded_ids_seen=set()
    # How many lines the published figures actually rest on, against how many there are.
    # Without this pair a sum over 2 of 715 lines and a sum over 715 of 715 look identical.
    computed_line_count=0;total_line_count=0
    # A SECOND coverage figure, because the forecast rests on a different set of lines than
    # the executed-value figures do. A material line with a price and no measurement is
    # excluded from `computedLineCount` -- nobody measured it -- yet it still contributes
    # what it needs to `moneyRequiredToContinueIrr`, because what a material still needs is
    # what has not been BOUGHT. Reporting one count beside both pairs of metrics said the
    # forecast rested on 0 of 715 lines when it rested on rather more than that.
    required_line_count=0
    # missingCount counts lines that DID match an assignment but had no usable quantity on
    # it. Lines that matched nothing are unmappedLineCount instead: the two need different
    # work from different people, so one number for both told the reader nothing.
    # mappedLineCount + unmappedLineCount + generalCostLineCount is every estimate line
    # read for this date. General cost is counted separately because progress is
    # meaningless for it, so it belongs in neither of the other two.
    #: Lines that state no baseline of their own. Counted rather than absorbed: a total
    #: built from some of its lines is not the total, and a reader must be told which.
    missing_estimate_count = 0
    #: The same gap, per resource type, so a type made entirely of unstated lines does not
    #: publish a confident zero beside a type that really was estimated.
    missing_estimate_by_type = {kind: 0 for kind in actual_by_type}
    progress_quality={"complete":True,"manualOverrideCount":0,"taskFallbackCount":0,"missingCount":0,"assignmentActualCount":0,"assignmentPercentFallbackCount":0,"mappedLineCount":0,"unmappedLineCount":0,"generalCostLineCount":0,"workAsQuantityCount":0,"unmappedAssignmentCount":0,"unmappedActivityCount":0}
    for row in estimate_rows:
        total_line_count += 1
        kind = row["resource_type"]
        # Detected, not coerced. `or 0` read a line that states no price as a line
        # priced at nothing, and 715 of this project's 835 lines state neither a price nor
        # a quantity -- so the estimate was built from 120 of them and the other 715 were
        # silently counted as worth zero. The arithmetic below still runs on ZERO, exactly
        # as the missing-current-price guard does; what changes is that a total resting on
        # a line like this is no longer published as if it were complete.
        stated_price = row["original_unit_price_irr"]
        original_price = ZERO if stated_price is None else Decimal(stated_price)
        if kind == "general_cost":
            progress_quality["generalCostLineCount"] += 1
            # A general cost IS its amount: the price column holds it, and there is no
            # quantity to multiply. So its baseline is known exactly when that is stated.
            has_baseline = stated_price is not None
            if not has_baseline:
                missing_estimate_count += 1
                missing_estimate_by_type[kind] += 1
                warnings.append(_line_warning(row,"ESTIMATE_BASELINE_MISSING","The line states no original amount; estimate totals exclude it.",excluded=True,
                    affected=("initialEstimateIrr","revisedEstimateIrr")))
            original_amount = original_price
            revised_amount = money(row["revised_quantity"]) if row.get("revised_quantity") is not None else original_amount
            general_revised += revised_amount
            if has_baseline:
                initial_total += original_amount
                breakdown[kind]["initialEstimateIrr"] += original_amount
                breakdown[kind]["revisedEstimateIrr"] += revised_amount
            linked_actual = actual_by_line.get(row["id"], ZERO)
            pooled_actual = resource_actual_remaining.get(row["resource_id"], ZERO)
            pooled_allocated = min(max(revised_amount - linked_actual, ZERO), pooled_actual) if pooled_actual > ZERO else ZERO
            resource_actual_remaining[row["resource_id"]] = pooled_actual - pooled_allocated
            line_actual = linked_actual + pooled_allocated
            general_required += max(revised_amount - line_actual, ZERO)
            # Counted here because this branch `continue`s: a general cost contributes to
            # money_required through `general_required` below and never passes the
            # per-line test. Left out, the count would understate the forecast's coverage
            # by every general-cost line the project has.
            #
            # `computed_line_count` for the same reason. It is the coverage figure printed
            # beside «هزینه بروز باقیمانده», and that figure now includes general costs --
            # so a count that skipped them would say the metric rests on fewer lines than
            # it does, which is the one thing that count exists to prevent.
            if has_baseline: required_line_count += 1;computed_line_count += 1
            if line_actual > revised_amount:
                warnings.append(_line_warning(row,"GENERAL_COST_OVERRUN","General cost actual exceeds its revised estimate.",affected=("moneyRequiredToContinueIrr","forecastFinalCostIrr")))
            continue
        stated_quantity = row["original_quantity"]
        original_quantity = ZERO if stated_quantity is None else Decimal(stated_quantity)
        revised_quantity = Decimal(row["revised_quantity"] if row.get("revised_quantity") is not None else original_quantity)
        # An amount is a product, so it exists only where both its factors do. A quantity
        # of zero with a price is an amount of zero -- a fact -- and is counted; a quantity
        # nobody stated is not.
        has_baseline = stated_quantity is not None and stated_price is not None
        initial = money(original_quantity * original_price)
        revised_estimate = money(revised_quantity * original_price)
        if has_baseline:
            initial_total += initial;breakdown[kind]["initialEstimateIrr"] += initial;breakdown[kind]["revisedEstimateIrr"] += revised_estimate
        else:
            missing_estimate_count += 1
            missing_estimate_by_type[kind] += 1
            warnings.append(_line_warning(row,"ESTIMATE_BASELINE_MISSING","The line states no original quantity or no original price; estimate totals exclude it.",excluded=True,
                affected=("initialEstimateIrr","revisedEstimateIrr")))
        assignment = pairing.match(*line_keys(row))
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
                warnings.append(_line_warning(row,"PROGRESS_UNMAPPED","This estimate line is not linked to any assignment in the selected progress snapshot.",excluded=True,affected=PROGRESS_AFFECTED_METRICS,progressStatus=_status))
            else:
                progress_quality["missingCount"] += 1
                warnings.append(_line_warning(row,"PROGRESS_MISSING","The linked assignment carries no usable progress quantity for this estimate line.",excluded=True,affected=PROGRESS_AFFECTED_METRICS,progressStatus=_status))
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
        # Whether anybody actually MEASURED this line. `executed` is ZERO in both the
        # measured-nothing case and the measured-nothing-because-nobody-looked case, and
        # those are not the same fact: the second one makes `remaining` the line's whole
        # revised quantity, so an unmeasured line quietly reported its full value as work
        # still to pay for. The number was indistinguishable from a real one.
        progress_known = _source not in ("missing", "unmapped")
        remaining = max(revised_quantity - executed, ZERO)
        if executed > revised_quantity:
            deviation=executed-revised_quantity
            percent=None if revised_quantity==0 else (deviation*Decimal(100)/revised_quantity).quantize(Decimal("0.0001"),rounding=ROUND_HALF_UP)
            warnings.append(_line_warning(row,"QUANTITY_OVERRUN","Executed quantity exceeds revised quantity.",
                affected=("remainingPhysicalCostIrr","moneyRequiredToContinueIrr","forecastFinalCostIrr"),
                deviationQuantity=format(deviation,"f"),deviationPercent=None if percent is None else format(percent,"f")))
        # THE PRICE, IN THIS LINE'S OWN UNIT -- or no price at all.
        #
        # The two rungs are quoted per different units. A manual price is per the resource's
        # base unit, because that is the unit the person was shown when they typed it. A
        # SHEET price is per whatever the worksheet column said, and on this project those
        # frequently differ: «تجهیزکارگاه اولیه» is measured in «واحد» and its resolved
        # sheet price is quoted per «کیلو».
        #
        # This used to multiply the two regardless. «ریز برآورد» has refused that crossing
        # from the start -- "a cubic metre at the cost of a kilogram" is its own comment --
        # and the report simply could not see the unit, because its query never selected
        # it. So one surface declined to compute a line while the other computed it wrong,
        # from the same two numbers, and said nothing.
        #
        # Crossed through the conversions this function already holds, by the same rule and
        # the same table the purchased quantities above use -- converting the QUANTITY into
        # the price's unit rather than inverting the price, so no division rounds money.
        # Uncrossable is not a warning on a published figure: the line is excluded exactly
        # as an unpriced one is, because a price in the wrong unit is not this line's price.
        stated_current_price = row.get("current_unit_price_irr")
        price_unit = row.get("current_price_unit")
        price_quantity_factor = Decimal(1)
        uncrossable_price = False
        if stated_current_price is not None and price_unit is not None and price_unit != row.get("base_unit"):
            crossing = conversion_by_key.get((row.get("base_unit"), price_unit, row.get("dimension")))
            if crossing is None:
                uncrossable_price = True
            else:
                price_quantity_factor = crossing
        # A price in the wrong unit is not this line's price, so the line is excluded
        # exactly as an unpriced one is -- but it is NOT reported as unpriced. The price is
        # there and could not be brought into this unit: a different problem, fixed by a
        # different person, and the same distinction «ریز برآورد» draws when it replaces
        # «قیمت نیست» with «تبدیل واحد نیست». Counted with the other conversion gaps.
        current_price = None if uncrossable_price else stated_current_price
        has_price = current_price is not None
        if uncrossable_price:
            missing_conversion_count += 1
            missing_conversion_types.add(kind)
            excluded_estimate_line_ids.append(str(row["id"]));excluded_ids_seen.add(str(row["id"]))
            excluded_lines_by_type[kind] += 1
            warnings.append(_line_warning(row,"PRICE_UNIT_NOT_CONVERTIBLE",
                "The resolved price is quoted per a unit this line cannot be converted into; live-value metrics exclude this line.",
                excluded=True,affected=PRICE_AFFECTED_METRICS))
        elif current_price is None:
            missing_price_count += 1
            excluded_estimate_line_ids.append(str(row["id"]));excluded_ids_seen.add(str(row["id"]))
            excluded_lines_by_type[kind] += 1
            warnings.append(_line_warning(row,"CURRENT_PRICE_MISSING","Current price is missing; live-value metrics exclude this line.",excluded=True,
                affected=PRICE_AFFECTED_METRICS))
        # The price PER THIS LINE'S OWN UNIT. The crossing is applied here as a
        # multiplication -- price-per-price-unit times base-units-per-price-unit -- rather
        # than by dividing the price, so no division rounds money on its way to a total.
        current = ZERO if current_price is None else Decimal(current_price) * price_quantity_factor
        if not progress_known and str(row["id"]) not in excluded_ids_seen:
            excluded_estimate_line_ids.append(str(row["id"]));excluded_ids_seen.add(str(row["id"]))
            excluded_lines_by_type[kind] += 1
        executed_value = money(executed * current); remaining_cost = money(remaining * current)
        # Both sums rest on `executed`, so both need a price AND a measurement. Adding a
        # priced-but-unmeasured line here is what produced the old behaviour: zero executed
        # value and the full quantity outstanding, stated as confidently as a real line.
        if has_price and progress_known:
            current_executed += executed_value;remaining_physical_cost += remaining_cost
        line_bought = purchased_by_line.get(row["id"], ZERO)
        resource_remaining_purchase = resource_purchase_remaining.get(row["resource_id"], ZERO)
        resource_allocated_purchase = min(max(revised_quantity - line_bought, ZERO), resource_remaining_purchase) if resource_remaining_purchase > 0 else ZERO
        resource_purchase_remaining[row["resource_id"]] = resource_remaining_purchase - resource_allocated_purchase
        bought = line_bought + resource_allocated_purchase
        required_quantity = max(revised_quantity - bought, ZERO) if kind == "material" else remaining
        required = money(required_quantity * current)
        # What a material line still needs is what has not been BOUGHT, which the purchase
        # ledger states whether or not anyone measured site progress. So an unmeasured
        # material line still contributes here, and only here -- the purchased-quantity
        # rule is untouched. Every other kind derives its requirement from `remaining`, so
        # it needs the measurement like the two sums above do.
        required_is_known = has_price and (kind == "material" or progress_known)
        if required_is_known:
            money_required += required;required_line_count += 1
        if has_price and progress_known:
            breakdown[kind]["remainingPhysicalCostIrr"] += remaining_cost
        if required_is_known:
            breakdown[kind]["forecastFinalIrr"] += required
        # A line counts as computed when every figure the forecast asks of it is knowable.
        if has_price and progress_known: computed_line_count += 1
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

    # «هزینه بروز باقیمانده» IS every rial still to spend, and a general cost is one of
    # them. It was in the breakdown's own column and in no total, so the four rows of the
    # type table added up to 8.1 billion toman while the headline beside them said zero --
    # the same report, the same date, two answers. Nothing pinned the sum, which is why it
    # stood: the only test touching this asserts a case where `general_required` is zero.
    #
    # The one thing to know about the figure: for a priced line the remaining is
    # `quantity still to do × today's price`, and a general cost has no quantity, so its
    # remaining is `revised amount − what invoices have already paid against it`. Both are
    # "money still owed on this line", which is what the metric says it holds.
    #
    # No total is counted twice. `forecastFinalCostIrr` is built from `actual_total +
    # money_required` and never reads this metric, so adding the same figure to both is
    # two statements about one obligation, not two obligations.
    breakdown["general_cost"]["remainingPhysicalCostIrr"] = general_required
    remaining_physical_cost += general_required
    money_required += general_required
    for kind in breakdown:
        breakdown[kind]["forecastFinalIrr"] += actual_by_type[kind]
    breakdown["general_cost"]["forecastFinalIrr"] += general_required
    for kind in breakdown:
        breakdown[kind]["excludedEstimateLineCount"] = excluded_lines_by_type[kind]
        # How many of this type's lines state no baseline. The sum beside it is the sum of
        # the others -- a real subtotal of real lines, not the type's total -- and this is
        # the number that says so. Published even when zero, because "0 of them" is an
        # answer a reader needs as much as "88 of them".
        breakdown[kind]["missingEstimateLineCount"] = missing_estimate_by_type[kind]
        breakdown[kind]["calculationStatus"] = ("incomplete"
            if excluded_lines_by_type[kind] or missing_estimate_by_type[kind] or kind in missing_conversion_types
            else "complete")
    forecast = actual_total + money_required
    area = None if gross_area is None else Decimal(gross_area)
    # Lines whose executed quantity nobody could measure -- unmapped, or mapped to a row
    # that states no usable quantity. Their executed value is UNKNOWN, and a sum with an
    # unknown term is not a lower bound a reader can use, it is a number that looks final.
    # So the figures resting on it go unavailable, exactly as one missing price already
    # makes them: the per-line warnings above already declare these metrics affected, and
    # this is what makes that declaration true instead of decorative.
    progress_unknown=progress_quality["unmappedLineCount"]+progress_quality["missingCount"]
    incomplete_metric_keys=[]
    if missing_price_count or missing_conversion_count or progress_unknown:
        incomplete_metric_keys=["currentExecutedValueIrr","remainingPhysicalCostIrr","moneyRequiredToContinueIrr","forecastFinalCostIrr","forecastPerSquareMeterIrr"]
    # The baseline is its own kind of gap and names its own metrics. A project can have
    # every price and every measurement and still have lines nobody has estimated.
    if missing_estimate_count:
        incomplete_metric_keys=incomplete_metric_keys+["initialEstimateIrr","revisedEstimateIrr"]
    if area is None or area <= 0:
        actual_per_area = forecast_per_area = None
        warnings.append(_warning("GROSS_AREA_MISSING","Per-square-meter metrics are unavailable because gross built area is missing.",
            excluded=True,affected=("actualCostPerSquareMeterIrr","forecastPerSquareMeterIrr")))
    else:
        actual_per_area = money(actual_total / area);forecast_per_area = money(forecast / area)
    # The estimate is the sum of the lines that state one. When some state none it is a
    # PARTIAL sum, and `incompleteMetricKeys` and `missingEstimateLineCount` are what say
    # so -- withholding the figure entirely said it too, and said nothing else: a reader
    # looking at 342 billion toman of stated material estimate saw an em dash and had no
    # way to reach the number, while the lines it was missing were equipment the file
    # states no price for anywhere. A flagged subtotal is usable and honest; a blank is
    # only honest.
    # Published, not withheld. These are sums over the lines that could be computed, and
    # the lines that could not are gone from them rather than entered as zero -- which is
    # what makes publishing safe, and is why the exclusions above had to come first.
    # Removing this condition on its own would have replaced an em dash with a confident
    # 0 on a project where 715 of 715 lines resolve no price.
    #
    # `computedLineCount` against `totalLineCount` is what keeps the figure honest: a sum
    # over 2 of 715 lines and a sum over 715 of 715 are both numbers, and only the pair
    # tells them apart. `incompleteMetricKeys` still names every figure a gap touched.
    metrics = {"initialEstimateIrr":money(initial_total),"actualCostIrr":money(actual_total),
        "currentExecutedValueIrr":money(current_executed),
        "remainingPhysicalCostIrr":money(remaining_physical_cost),
        "moneyRequiredToContinueIrr":money(money_required),
        "forecastFinalCostIrr":money(forecast),
        "actualCostPerSquareMeterIrr":actual_per_area,
        "forecastPerSquareMeterIrr":forecast_per_area}
    price_variances.sort(key=lambda item:abs(item["varianceIrr"]),reverse=True)
    quantity_variances.sort(key=lambda item:abs(item["varianceQuantity"]),reverse=True)
    total_impact = sum(abs(item["varianceIrr"]) for item in price_variances) + sum(abs(item["remainingPhysicalCostIrr"] or ZERO) for item in quantity_variances)
    for item in price_variances:
        item["impactSharePercent"] = None if total_impact == 0 or not item["priceAvailable"] else (abs(item["varianceIrr"]) * Decimal(100) / total_impact).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    for item in quantity_variances:
        item["impactSharePercent"] = None if total_impact == 0 or not item["priceAvailable"] else (abs(item["remainingPhysicalCostIrr"] or ZERO) * Decimal(100) / total_impact).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return LiveReport(metrics,list(breakdown.values()),price_variances[:10],quantity_variances[:10],price_variances,quantity_variances,warnings,_calculation_status(missing_price_count,missing_conversion_count,progress_quality),incomplete_metric_keys,missing_price_count,missing_estimate_count,len(excluded_estimate_line_ids),excluded_estimate_line_ids,progress_quality,computed_line_count,total_line_count,required_line_count)
