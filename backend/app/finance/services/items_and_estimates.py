# -*- coding: utf-8 -*-
"""Resources, their assignments, and what each comes to.

THE SHAPE, AND WHY IT IS THIS SHAPE

    Resource (one MPP resource uid)
      └── Assignment (one MPP assignment uid, in one activity)

The estimate is calculated on the ASSIGNMENT and only there. A resource's number is the
sum of its assignments' numbers, and the project's number is the sum of the same
assignments -- not the sum of the resource totals, which would be the same money counted
at two levels. Both aggregates are computed from one list of assignment amounts here, so
they cannot disagree and cannot both be added.

WHAT MAKES A ROW COUNT

`domain/assignment_semantics.py` decides. This module does no arithmetic on a number whose
meaning it has not established, and a row it cannot price reports `not_calculable` with
the codes saying what is missing, rather than contributing a zero. Zero and "unknown" are
different, and a total that adds unknowns as zero is understated in a way nothing on the
screen reveals.

WHAT IT NEVER DOES

It creates nothing. There is no write path in this file, and no branch that invents a
resource, an assignment or an identity for a row that lacks one. A row the schedule does
not account for is returned in its own list -- never grafted into the tree under a
placeholder.
"""

from decimal import Decimal

from ..domain.assignment_semantics import (ALLOCATION_PERCENTAGE, CALCULATED,
                                           MISSING_CONVERSION, MISSING_PRICE,
                                           NOT_CALCULABLE, PHYSICAL_QUANTITY,
                                           allocation_percent, assignment_estimate,
                                           physical_quantity, roll_up, value_kind)

#: A mapping whose conversion the mapping workflow has not resolved cannot price anything.
#: The vocabulary is that workflow's, not this module's -- it is the CHECK constraint on
#: `finance_item_price_mappings.conversion_status`, which allows exactly
#: automatic | factor | incompatible | unknown. Reused rather than re-derived, so there is
#: one answer to "can this cross units" and not a second opinion here.
#:
#:     automatic     the registry crossed the two units on its own
#:     factor        a measured factor for this product crossed them
#:     incompatible  they cannot be crossed
#:     unknown       nobody has established whether they can
CONVERSION_READY = ("automatic", "factor")

#: A price the resolver took from `price_versions`. Named from the shared module rather
#: than spelled here, so the two cannot drift into disagreeing about what "manual" means.
from ..domain.price_resolution import SOURCE_MANUAL_RESOURCE  # noqa: E402
from ..domain.resource_types import canonical_resource_type  # noqa: E402


class ItemsAndEstimatesService:
    def __init__(self, repository):
        self.repository = repository

    async def listing(self, scope):
        """The whole section: one source version, its resources, and what is excluded."""
        version = await self.repository.live_version(scope)
        if version is None:
            # No schedule imported. An empty project, reported as empty -- never as a
            # project whose items happen not to have loaded.
            return {"source_version": None, "resources": [], "legacy_lines": [],
                    "project_current_estimate_irr": None, "counted_assignments": 0,
                    "excluded_assignments": 0, "issue_counts": {}}

        rows = await self.repository.assignments(scope, version["id"])
        legacy = await self.repository.legacy_lines(scope)

        by_resource = {}
        for row in rows:
            # The MPP resource uid is the identity. Not the name: two resources may share
            # one, and merging them would make one item out of two real ones.
            #
            # An assignment whose resource uid the file does not state gets a group of its
            # own, keyed by its assignment uid. 24 rows of the audited version are like
            # that, and collecting them under a single null-uid heading would assert they
            # are all the same item -- the same merge-by-coincidence the uid rule exists
            # to prevent, one step removed.
            key = (("resource", row["source_resource_uid"])
                   if row["source_resource_uid"] is not None
                   else ("unidentified", row["source_assignment_uid"]))
            by_resource.setdefault(key, []).append(row)

        resources, all_amounts, issue_counts = [], [], {}
        for (_kind, key), group in sorted(by_resource.items()):
            children = [self._assignment(row) for row in group]
            amounts = [child["current_estimate_irr"] for child in children]
            total, counted, excluded = roll_up(amounts)
            all_amounts.extend(amounts)
            for child in children:
                for code in child["issue_codes"]:
                    issue_counts[code] = issue_counts.get(code, 0) + 1
            resources.append(self._resource(group[0]["source_resource_uid"], group,
                                            children, total, counted, excluded))

        project_total, counted, excluded = roll_up(all_amounts)
        return {"source_version": version, "resources": resources,
                "legacy_lines": [self._legacy(row) for row in legacy],
                "project_current_estimate_irr": project_total,
                "counted_assignments": counted, "excluded_assignments": excluded,
                "issue_counts": issue_counts}

    # ------------------------------------------------------------------ assignment

    @staticmethod
    def _assignment(row):
        """One use of one resource in one activity, priced or explained."""
        kind = value_kind(row["file_resource_type"], row["normalized_unit"],
                          row["unit_source"])
        quantity = physical_quantity(kind, row["source_assignment_units"])
        percent = (allocation_percent(row["source_assignment_units"])
                   if kind == ALLOCATION_PERCENTAGE else None)

        # The converted price, and the reason there is none. The mapping workflow owns
        # whether a crossing is resolved; an unresolved one withholds the price rather
        # than passing the unconverted number through, which would price a cubic metre at
        # the cost of a kilogram.
        converted = None
        conversion_issue = None
        if row["current_unit_price_irr"] is not None:
            # `conversion_status` describes a MAPPING: it says whether the listing's unit
            # could be crossed into the line's. A manual resource price has no mapping and
            # needs no crossing -- it is already quoted per the resource's own base unit,
            # because that is the unit the person was shown when they typed it.
            #
            # Before this, the gate asked every price for a mapping's verdict. A machine
            # priced by hand answered None, fell to the `else`, and was reported as a
            # missing conversion: the price resolved, appeared in the row, and produced no
            # estimate. «قیمت هست، برآورد نیست» with nothing on screen explaining why.
            if row["current_price_source"] == SOURCE_MANUAL_RESOURCE:
                converted = Decimal(row["current_unit_price_irr"])
            elif row["conversion_status"] in CONVERSION_READY:
                converted = Decimal(row["current_unit_price_irr"])
            else:
                conversion_issue = MISSING_CONVERSION

        estimate, status, issues = assignment_estimate(kind, row["source_assignment_units"],
                                                       converted)
        issues = list(issues)
        # A crossing that failed is a better explanation than "no price": the price is
        # there and could not be brought into this unit.
        if conversion_issue and MISSING_PRICE in issues:
            issues[issues.index(MISSING_PRICE)] = conversion_issue
        elif conversion_issue and conversion_issue not in issues:
            issues.append(conversion_issue)

        return {
            "assignment_id": row["estimate_line_id"],
            "source_assignment_uid": row["source_assignment_uid"],
            "source_task_uid": row["source_task_uid"],
            "task_name": row["task_name"],
            "wbs_code": row["task_wbs"],
            "assignment_value": row["source_assignment_units"],
            "assignment_value_kind": kind,
            "assignment_unit": row["normalized_unit"],
            "assignment_source_unit": row["resource_unit"],
            "assignment_allocation_percent": percent,
            "assignment_quantity": quantity,
            "original_assignment_cost_irr": row["source_assignment_cost_irr"],
            "current_unit_price_irr": row["current_unit_price_irr"],
            "converted_unit_price_irr": converted,
            # The unit the PRICE is quoted per, from whichever rung answered: the
            # resource's base unit for a manual price, the worksheet's own unit for a
            # sheet price. `selected_unit` is the mapping's choice and only exists when a
            # mapping does, so it cannot speak for a manually priced machine.
            "price_unit": row["current_price_unit"] or row["selected_unit"],
            "price_source": row["current_price_source"],
            "price_as_of": row["current_price_effective_from"],
            "current_estimate_irr": estimate,
            "calculation_status": status,
            "issue_codes": issues,
            "excluded_from_total": status != CALCULATED,
        }

    # -------------------------------------------------------------------- resource

    @staticmethod
    def _resource(uid, group, children, total, counted, excluded):
        """The item identity, and the sum of its uses. Never a row of its own."""
        head = group[0]
        kinds = {child["assignment_value_kind"] for child in children}
        units = {child["assignment_unit"] for child in children}
        # Only added up when every assignment is measuring the same thing in the same
        # unit. Four cubic metres plus four square metres is eight of nothing.
        compatible = kinds == {PHYSICAL_QUANTITY} and len(units) == 1 and None not in units
        quantities = [child["assignment_quantity"] for child in children]
        return {
            "resource_id": head["resource_id"],
            "source_resource_uid": uid,
            # The MPP name, always. `mapped_product_name` is a different field on purpose:
            # a market listing is what this item was PRICED against, never what it is.
            "resource_name": head["resource_name"],
            "finance_resource_title": head["resource_title"],
            "file_resource_type": head["file_resource_type"],
            # A stored `labor`/`equipment` leaves as `work` (0038).
            "resource_type": canonical_resource_type(head["resource_type"]),
            "source_unit": head["resource_unit"],
            "normalized_unit": head["normalized_unit"],
            "assignment_count": len(children),
            "total_assignment_quantity": (sum(q for q in quantities if q is not None)
                                          if compatible and all(q is not None for q in quantities)
                                          else None),
            "original_mpp_cost_irr": sum(
                (Decimal(child["original_assignment_cost_irr"]) for child in children
                 if child["original_assignment_cost_irr"] is not None), Decimal(0)) or None,
            "mapped_provider_item_id": head["provider_item_id"],
            "mapped_product_name": head["mapped_product_name"],
            "mapping_status": ("approved" if head["mapping_id"] is not None
                               else "not_mapped"),
            "mapping_version": head["mapping_version"],
            "conversion_status": head["conversion_status"],
            "current_unit_price_irr": head["current_unit_price_irr"],
            "price_unit": head["current_price_unit"] or head["selected_unit"],
            "price_source": head["current_price_source"],
            "current_estimate_irr": total,
            "calculation_status": CALCULATED if counted else NOT_CALCULABLE,
            "counted_assignments": counted,
            "excluded_assignments": excluded,
            "issue_codes": sorted({code for child in children
                                   for code in child["issue_codes"]}),
            "assignments": children,
        }

    # ---------------------------------------------------------------------- legacy

    @staticmethod
    def _legacy(row):
        """A row the schedule does not account for. Reported, never hidden, never summed."""
        return {
            "estimate_line_id": row["id"],
            "legacy_status": row["legacy_status"],
            "source": row["source"],
            "resource_title": row["resource_title"],
            "resource_type": canonical_resource_type(row["resource_type"]),
            "original_quantity": row["original_quantity"],
            "original_unit_price_irr": row["original_unit_price_irr"],
            "invoice_linked": row["invoice_linked"],
            "created_at": row["created_at"],
        }
