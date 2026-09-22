# -*- coding: utf-8 -*-
"""The published shape of "Items and Estimates".

Two levels, and the reader can always tell which one they are looking at. A resource's
`currentEstimateIrr` is the sum of its assignments' and must never be added beside them;
the project total is computed from the assignments once, and is returned at the top so
nobody has to add anything up to get it.

Every money and quantity field is nullable and null means "not established". None of them
is ever 0, "-" or "" standing in for a missing fact: a row nobody could price and a row
that costs nothing are different rows, and only one of them is a number.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from .base import ApiModel


class AssignmentResponse(ApiModel):
    """One use of one resource in one activity -- the grain the estimate is computed on."""

    #: The estimate line this assignment materialised as, or null when Finance has not
    #: made one. The assignment exists in the file either way.
    assignment_id: UUID | None = None
    source_assignment_uid: int
    source_task_uid: int | None = None
    task_name: str | None = None
    wbs_code: str | None = None

    #: The raw number the file put in "Units", carried through unread.
    assignment_value: Decimal | None = None
    #: What that number MEANS: physical_quantity | allocation_percentage | work | unknown.
    #: The whole point of the field. 1.0 against a WORK resource is 100% of one machine,
    #: not one of anything, and nothing may multiply it by a price per cubic metre.
    assignment_value_kind: str
    #: The registry code the unit resolved to, or null when the text was not a unit.
    assignment_unit: str | None = None
    #: The unit exactly as the file spelled it -- «مترمکعب», «ب».
    assignment_source_unit: str | None = None
    #: Present only for an allocation, and then as a percentage: 1.0 is published as 100.
    assignment_allocation_percent: Decimal | None = None
    #: Present ONLY when the value is a physical quantity. Null for an allocation, because
    #: there is no quantity to state.
    assignment_quantity: Decimal | None = None

    original_assignment_cost_irr: Decimal | None = None
    current_unit_price_irr: Decimal | None = None
    #: The price brought into this assignment's unit. Null when the crossing is not
    #: resolved -- the unconverted number is never passed through in its place.
    converted_unit_price_irr: Decimal | None = None
    price_unit: str | None = None
    #: Which rung of the shared ladder answered: a price a person set for this resource,
    #: the mapped market listing, or neither. The page shows the amount; this is what lets
    #: a reader tell an agreed rate from a market reading without opening another screen.
    price_source: Literal["manual_resource", "sheet", "none"] | None = None
    price_as_of: date | None = None

    #: quantity x converted unit price, or null. Never zero for a missing input.
    current_estimate_irr: Decimal | None = None
    #: calculated | not_calculable
    calculation_status: str
    #: Exactly what is missing: allocation_percentage_not_quantity, missing_quantity,
    #: missing_price, missing_conversion, unknown_assignment_semantics, ...
    issue_codes: list[str] = []
    excluded_from_total: bool = False


class ResourceAggregateResponse(ApiModel):
    """One MPP resource identity, and the sum of its assignments."""

    #: The Finance row for this resource, or null when the import has not made one.
    resource_id: UUID | None = None
    #: The identity. Never the name -- two resources may share a name and remain two.
    source_resource_uid: int | None = None
    #: The name the FILE gives. A price mapping never overwrites this.
    resource_name: str | None = None
    finance_resource_title: str | None = None
    #: What the file says it is (MATERIAL / WORK), beside what Finance classified it as.
    #: Both, because they can disagree and the disagreement is the thing worth seeing.
    file_resource_type: str | None = None
    resource_type: str | None = None
    source_unit: str | None = None
    normalized_unit: str | None = None

    assignment_count: int
    #: Only when every assignment is a physical quantity in the SAME unit. Null otherwise:
    #: four cubic metres plus four square metres is eight of nothing.
    total_assignment_quantity: Decimal | None = None
    original_mpp_cost_irr: Decimal | None = None

    #: The market listing this resource is priced against -- a separate field from
    #: `resourceName`, and the reason both survive.
    mapped_provider_item_id: UUID | None = None
    mapped_product_name: str | None = None
    #: approved | not_mapped
    mapping_status: str = "not_mapped"
    mapping_version: int | None = None
    conversion_status: str | None = None
    current_unit_price_irr: Decimal | None = None
    price_unit: str | None = None
    #: Same vocabulary as the assignment rows below it, so a reader comparing the two
    #: levels is comparing like with like.
    price_source: Literal["manual_resource", "sheet", "none"] | None = None

    #: The sum of this resource's assignment estimates. Never added beside them.
    current_estimate_irr: Decimal | None = None
    calculation_status: str
    counted_assignments: int
    excluded_assignments: int
    issue_codes: list[str] = []

    assignments: list[AssignmentResponse] = []


class LegacyLineResponse(ApiModel):
    """A row the schedule does not account for.

    Returned so it is visible and countable, never grafted into the tree: it has no
    assignment to be a child of, and inventing a resource to hang it under would be the
    fabricated identity the whole model exists to prevent. Excluded from every total here.
    """

    estimate_line_id: UUID
    #: legacy_unlinked | approved_exception
    legacy_status: str
    source: str
    resource_title: str | None = None
    resource_type: str | None = None
    original_quantity: Decimal | None = None
    original_unit_price_irr: Decimal | None = None
    #: True when an invoice line names it. Such a row is evidence of something a person
    #: did and is preserved whatever its provenance says.
    invoice_linked: bool = False
    created_at: datetime | None = None


class SourceVersionResponse(ApiModel):
    """Which file this listing is of. Part of the answer, not a fetch detail."""

    id: UUID
    source_file_name_safe: str | None = None
    source_sha256: str | None = None
    imported_at: datetime | None = None
    reporting_date: date | None = None
    row_count: int | None = None


class ItemsAndEstimatesResponse(ApiModel):
    """The section, from one source version."""

    #: Null when no schedule has been imported: an empty project, said plainly.
    source_version: SourceVersionResponse | None = None
    resources: list[ResourceAggregateResponse] = []
    #: The rows kept OUT of the total, listed so the exclusion is never silent.
    legacy_lines: list[LegacyLineResponse] = []

    #: Summed from the assignments exactly once. Adding the resource totals to this would
    #: count the same money twice, which is why the aggregates are not summed again here.
    project_current_estimate_irr: Decimal | None = None
    counted_assignments: int = 0
    #: How many assignments could not be priced. Never silently dropped.
    excluded_assignments: int = 0
    #: issue code -> how many assignments carry it.
    issue_counts: dict[str, int] = {}
