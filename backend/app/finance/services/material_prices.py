# -*- coding: utf-8 -*-
"""The read side of material prices: what the API answers with.

Everything here comes from the database. There is no fallback, no sample row and no
default price: an endpoint with nothing to return returns an empty list, and a listing
with no readable price returns a null price and a status saying which kind of nothing it
is.

Freshness is expressed in days against the date the caller asks about, and the caller
supplies both. This service does not read a clock -- a report for a date in the past must
not be told that everything in it is stale.
"""

from datetime import datetime, time, timezone
from decimal import Decimal

from ..domain.material_specs import SPEC_COLUMNS, WEIGHT_BASES_USABLE_FOR_CONVERSION
from ..domain.errors import FinanceDomainError
from ..domain.unit_conversion import can_convert
from .material_price_resolution import Resolution, canonical_unit, resolve

#: How old the newest workflow date may be before a price is labelled stale. Seven days is
#: the sheet's own rhythm -- its four dates span five days -- and it is a label, never a
#: reason to withhold: a stale price is still the best figure anybody has.
DEFAULT_STALE_AFTER_DAYS = 7


#: The virtual category that publishes equipment rates on the daily-prices page.
#:
#: It is not a worksheet and there are no `provider_items` behind it. The rows come from
#: `price_versions` -- the same rung the report resolves a manual price from -- and this
#: service only READS them. Nothing in this module writes a provider item or an
#: observation for a piece of equipment: a listing is something a supplier published, a
#: rate is something a person decided, and copying one into the other would put a row in
#: the importer's table that no sheet produced.
EQUIPMENT_CATEGORY = "equipment"


def _midnight(day):
    """A business DATE as the timestamp the response declares, or None.

    The sheet path carries a real observation time; a price version carries only the day
    it takes effect. Widening it here is honest exactly because `observedAtSource` says
    `workflow_date` beside it: the reader is told the timestamp came from a date.
    """
    return None if day is None else datetime.combine(day, time.min, tzinfo=timezone.utc)


#: A category at these levels is a statement about every project the tenant will ever
#: run, so it is gated harder than editing the project in front of you -- the same
#: distinction, and the same permission, the conversion rules draw for their own scopes.
TENANT_WIDE_CATEGORY_SCOPES = frozenset({"organization", "global"})
TENANT_WIDE_CATEGORY_PERMISSION = "finance.manage_settings"


class MaterialCategoryRefused(FinanceDomainError):
    """A category or a manual price the caller may not record as asked.

    409 rather than 422: the request is well formed and the conflict is with what already
    exists, which is the caller's to resolve by choosing another word or declaring the
    category first.
    """

    status = 409
    code = "FINANCE_MATERIAL_CATEGORY_REFUSED"


class MaterialPriceService:
    def __init__(self, repository, conversion_repository=None,
                 stale_after_days=DEFAULT_STALE_AFTER_DAYS):
        self.repository = repository
        self.conversions = conversion_repository
        self.stale_after_days = stale_after_days

    #: The supplier row every hand-entered price hangs from. One per project, named for
    #: what it is rather than for a company, because no company quoted through this path.
    MANUAL_PROVIDER_NAME = "ورود دستی"

    async def categories(self, scope, *, today=None):
        """Every category this project can show: counted from listings, plus declared ones.

        The union is deliberately seamless. A chip somebody declared and a chip the sheet
        produced look and behave the same on screen, and a client that wants to tell them
        apart reads `declared` and `scopeLevel` rather than inferring it from the shape of
        the answer.

        A declared category with no listings yet reports zero counts, which is the true
        answer: somebody named it and nothing has been recorded in it.
        """
        counted = await self.repository.categories(scope)
        by_name = {row["category"]: dict(row, declared=False, scope_level=None)
                   for row in counted}
        if hasattr(self.repository, "declared_categories"):
            for row in await self.repository.declared_categories(scope):
                existing = by_name.get(row["category"])
                if existing is None:
                    by_name[row["category"]] = {
                        "category": row["category"], "item_count": 0,
                        "active_count": 0, "inactive_count": 0,
                        "declared": True, "scope_level": row["scope_level"],
                        "declared_label": row.get("label")}
                else:
                    # It was declared AND something has been recorded in it. The counts
                    # stay -- they describe the listings -- and the level is added.
                    existing["declared"] = True
                    existing["scope_level"] = row["scope_level"]
                    existing["declared_label"] = row.get("label")
        # Equipment, when the project has any priced. Counted through the same statement
        # that lists them, so the chip's number and the table's rows cannot disagree.
        #
        # `today` rather than a clock read here: this service deliberately reads none, so a
        # caller asking about a past day is never told what is in force now. A caller that
        # names no day is not asking which rates are current and gets no equipment chip.
        if today is not None and hasattr(self.repository, "equipment_rate_count"):
            priced = await self.repository.equipment_rate_count(scope, as_of=today)
            if priced:
                by_name[EQUIPMENT_CATEGORY] = {
                    "category": EQUIPMENT_CATEGORY,
                    "item_count": priced,
                    # Every published equipment rate is active by construction: the rate
                    # IS the price version in force, and a resource with none is not
                    # published at all. There is no inactive half to report.
                    "active_count": priced, "inactive_count": 0,
                    "declared": False, "scope_level": None}
        return [by_name[name] for name in sorted(by_name)]

    async def declare_category(self, scope, payload, actor_id, *, permissions=()):
        """Record a category nobody had named yet.

        A category above project level is checked here rather than at the route, because
        `finance.manage_settings` is not one of the permissions a route may be gated on
        and the conversion rules already answer this question the same way: the route asks
        for `finance.edit`, and the wider scope is refused in the service.

        Refused when the word is already in this project's view -- declared here, declared
        for the organization, or simply in use by a listing the sheet brought. Two chips
        with the same name would be two chips for one thing, and the second would be
        unreachable from the first.
        """
        from uuid import uuid4

        if payload.scope_level in TENANT_WIDE_CATEGORY_SCOPES:
            if TENANT_WIDE_CATEGORY_PERMISSION not in set(permissions or ()):
                raise MaterialCategoryRefused(
                    "دسته‌ای که فراتر از این پروژه است تنها با دسترسی «%s» قابل ثبت است"
                    % TENANT_WIDE_CATEGORY_PERMISSION)
        category = payload.category.strip()
        if await self.repository.category_exists(scope, category):
            raise MaterialCategoryRefused(
                "دستهٔ «%s» از قبل وجود دارد." % category)
        row = await self.repository.declare_category(
            scope, category=category, label=(payload.label or "").strip() or None,
            scope_level=payload.scope_level, created_by=actor_id,
            category_id=uuid4())
        if row is None:
            # Somebody declared the same word between the check and the insert. The
            # table's own uniqueness caught it, which is why the check above is a
            # courtesy and this is the guarantee.
            raise MaterialCategoryRefused(
                "دستهٔ «%s» هم‌زمان توسط شخص دیگری ثبت شد." % category)
        return row

    async def record_manual_price(self, scope, payload, actor_id):
        """One price a person obtained, stored in the same world as the imported ones.

        It becomes a listing and an observation, exactly like a sheet row, so everything
        downstream -- the prices table, the history, the estimate -- reads it without
        knowing it was typed. What marks it is `origin`, and what protects it is that the
        importer's upsert never touches a manual listing.

        Recording a NEW price for the same product appends another observation rather than
        editing the last: the table is append-only by trigger, and a price that can be
        rewritten is not a record of what anything cost.
        """
        from hashlib import sha256
        from uuid import uuid4

        category = payload.category.strip()
        if not await self.repository.category_exists(scope, category):
            raise MaterialCategoryRefused(
                "دستهٔ «%s» تعریف نشده است. اول آن را بسازید." % category)
        unit = canonical_unit(payload.source_unit)
        if unit is None:
            raise MaterialCategoryRefused(
                "واحد «%s» در فهرست واحدهای سامانه نیست." % payload.source_unit)

        provider = await self.repository.ensure_manual_provider(
            scope, name=self.MANUAL_PROVIDER_NAME, provider_id=uuid4())
        name = payload.product_name.strip()
        item = await self.repository.find_manual_item(
            scope, provider_id=provider["id"], external_name=name, category=category)
        if item is None:
            item = await self.repository.create_manual_item(
                scope, provider_id=provider["id"], item_id=uuid4(),
                external_id="MANUAL-%s" % uuid4().hex[:12].upper(),
                external_name=name, category=category, source_unit=unit)

        # The same triple every imported row is fingerprinted on, so entering an
        # identical price for an identical day twice is recognised as one observation
        # rather than stored twice.
        fingerprint = sha256(
            "\x1f".join((str(item["id"]), payload.observed_at.isoformat(),
                          str(payload.price_irr))).encode("utf-8")).hexdigest()
        observation = await self.repository.record_manual_observation(
            scope, observation_id=uuid4(), provider_id=provider["id"],
            provider_item_id=item["id"], price_irr=payload.price_irr, source_unit=unit,
            observed_on=payload.observed_at, entered_by=actor_id,
            reason=payload.reason.strip(), fingerprint=fingerprint, product_name=name,
            provider_name=self.MANUAL_PROVIDER_NAME)
        return {"provider_item_id": item["id"], "category": category,
                "product_name": name, "source_unit": unit,
                "price_irr": payload.price_irr, "observed_at": payload.observed_at,
                "already_recorded": observation is None}

    async def runs(self, scope, page, page_size):
        return await self.repository.runs_page(scope, page=page, page_size=page_size)

    async def invalid_rows(self, scope, page, page_size):
        return await self.repository.invalid_observations_page(
            scope, page=page, page_size=page_size)

    async def history(self, scope, provider_item_id, page, page_size):
        return await self.repository.observation_history(
            scope, provider_item_id, page=page, page_size=page_size)

    async def unit_settings(self, scope, category=None):
        return await self.repository.unit_settings(scope, category=category)

    async def set_unit(self, scope, payload, actor_id):
        """Record a unit decision. Append-only: the previous decision stays readable."""
        return await self.repository.append_unit_setting(
            scope, category=payload.category, resource_id=payload.resource_id,
            display_unit=payload.display_unit, reason=payload.reason.strip(),
            created_by=actor_id)

    async def labels(self, scope, provider_item_id=None):
        return await self.repository.labels(scope, provider_item_id=provider_item_id)

    async def label_history(self, scope, provider_item_id):
        return await self.repository.label_history(scope, provider_item_id)

    async def save_label(self, scope, provider_item_id, payload, actor_id):
        """Record what a person says this listing is. Appended, never an update.

        An approval is stamped with the actor and the moment here rather than accepted from
        the request: a caller that could supply `mappingApprovedBy` could approve a mapping
        in somebody else's name.
        """
        values = {
            "label": _clean(payload.label),
            "display_name": _clean(payload.display_name),
            "category": _clean(payload.category),
            "product_type": _clean(payload.product_type),
            "source_unit": _clean(payload.source_unit),
            "source_basis": _clean(payload.source_basis),
            "target_unit": _clean(payload.target_unit),
            "finance_resource_id": payload.finance_resource_id,
            "mapping_approved": bool(payload.mapping_approved),
            "mapping_approved_by": actor_id if payload.mapping_approved else None,
            "mapping_approved_at": datetime.now(timezone.utc) if payload.mapping_approved else None,
            "active": payload.active,
            "notes": _clean(payload.notes),
            "reason": payload.reason.strip(),
        }
        return await self.repository.append_label(
            scope, provider_item_id=provider_item_id, values=values, created_by=actor_id)

    async def save_item_factor(self, scope, provider_item_id, payload, actor_id):
        """A measurement of one product, stored so a crossing becomes possible.

        `origin` is forced to 'manual': this endpoint is a person typing a number, and
        'sheet_attribute' is reserved for a factor the importer read off a column.
        """
        return await self.repository.append_item_factor(
            scope, provider_item_id=provider_item_id, from_unit=payload.from_unit,
            to_unit=payload.to_unit, factor=payload.factor,
            factor_type=payload.factor_type, origin="manual",
            reason=payload.reason.strip(), created_by=actor_id, approved_by=actor_id)

    async def unresolved(self, scope, page, page_size):
        return await self.repository.unresolved_items(scope, page=page, page_size=page_size)

    async def current(self, scope, *, category=None, as_of=None, page=1, page_size=50,
                      only_active=True, provider_item_id=None, today=None):
        """The newest observation per listing, resolved, paged.

        Paged in memory after resolution rather than in SQL, and deliberately: the status a
        row ends up with depends on the unit settings and the factors available to it, so a
        SQL page would be a page of rows whose statuses were not yet known. The population
        is one project's provider listings -- hundreds, not millions -- and correctness is
        worth more than the query here.
        """
        if category == EQUIPMENT_CATEGORY:
            return await self._equipment_current(scope, as_of=as_of, today=today,
                                                 page=page, page_size=page_size)
        options = {"category": category, "only_active": only_active}
        if provider_item_id is not None:
            options["provider_item_id"] = provider_item_id
        observations = await self.repository.latest_observations(scope, **options)
        settings = {row["category"]: row["display_unit"]
                    for row in await self.repository.unit_settings(scope)
                    if row.get("resource_id") is None and row.get("provider_item_id") is None}
        # What a person said about one listing. Fetched once for the whole page rather than
        # once per row: a project has hundreds of listings and one query answers all of them.
        labels = {}
        if hasattr(self.repository, "labels"):
            labels = {row["provider_item_id"]: row for row in await self.repository.labels(scope)}
        # The Finance unit of every approved-mapped resource, so a row can say whether the
        # unit it is priced in is the unit the schedule measures it in.
        finance_units = {}
        if hasattr(self.repository, "mapped_resource_units"):
            finance_units = await self.repository.mapped_resource_units(scope)

        resolved = []
        for row in observations:
            label = labels.get(row["provider_item_id"])
            # A label wins over the category-wide setting, and over the sheet. It is the
            # narrower statement and the only one made by somebody who looked at this row.
            # It never rewrites the observation: `row` is untouched and what the sheet said
            # still travels to the reader beside what the label made of it.
            display_unit = (label or {}).get("target_unit") or settings.get(row["category"])
            source = (canonical_unit((label or {}).get("source_unit"))
                      or canonical_unit(row.get("source_unit")))
            target = canonical_unit(display_unit)
            # Only fetched when the crossing actually needs one: a per-product factor is a
            # person's measurement, and asking for one where units already agree would
            # invite using it where it was never needed.
            factor = await self._product_factor(scope, row["provider_item_id"], source, target)
            # A label that names a Finance resource is a mapping claim, and a mapping claim
            # only counts once somebody has approved it. An unapproved one withholds the
            # price rather than quietly becoming the source of it.
            mapping_required = bool((label or {}).get("finance_resource_id"))
            outcome = resolve(
                dict(row, source_unit=source or row.get("source_unit")),
                display_unit=display_unit, product_factor=factor, as_of=as_of,
                stale_after_days=self.stale_after_days if as_of else None,
                mapping_required=mapping_required,
                mapping_approved=bool((label or {}).get("mapping_approved")),
                active=row.get("active", True) and (label or {}).get("active", True))
            resolved.append(self._shape(
                row, outcome, display_unit, label,
                finance_units.get(row["provider_item_id"]),
                # Judged here rather than in `_shape` because only this loop knows what was
                # ASKED for: `outcome.target_unit` is null when the crossing failed, and a
                # failed crossing and a crossing nobody requested are different answers.
                eligible=_conversion_eligible(row, source, target, factor)))

        total = len(resolved)
        start = (page - 1) * page_size
        return resolved[start:start + page_size], total

    async def _equipment_current(self, scope, *, as_of, today, page, page_size):
        """Equipment rates, in the shape the daily-prices table already renders.

        Asked for explicitly or not at all. `category=equipment` is the only way in: the
        "all" view and every material category go through the observation path above and
        never see these rows, because an equipment rate is not a sheet reading and would
        sit in a table of sheet readings claiming to be one.

        `includeInactive` has nothing to act on and is deliberately not consulted. The
        query publishes a resource only when a price version is in force for it, so there
        is no unpriced half a flag could reveal -- and letting `includeInactive` admit
        unpriced equipment would put rows with a null price into a price list.
        """
        cutoff = as_of or today
        if cutoff is None or not hasattr(self.repository, "equipment_rates"):
            return [], 0
        rows = await self.repository.equipment_rates(scope, as_of=cutoff)
        shaped = [self._equipment_row(row) for row in rows]
        start = (page - 1) * page_size
        return shaped[start:start + page_size], len(shaped)

    @staticmethod
    def _equipment_row(row):
        """One equipment rate as a price row. Every absent fact is null, never a placeholder.

        The nulls are the point. There is no supplier, so `providerName` is null rather
        than an invented name; there is no sheet, so there is no external id, no worksheet,
        no row number and no source url. A reader comparing an equipment row against a
        sheet row can see which of the two a number came from without being told.
        """
        unit = row.get("base_unit")
        effective = row.get("effective_from")
        return {
            "provider_item_id": row["provider_item_id"],
            # No supplier listing behind it. Null rather than "" or the resource code: an
            # empty string reads as "the sheet left this cell blank", which is a claim
            # about a sheet that does not exist.
            "external_id": None,
            "external_name": row["external_name"],
            "category": EQUIPMENT_CATEGORY,
            "provider_name": None,
            "active": True,
            "inactive_reason": None,
            "worksheet": None,
            # No worksheet object, so the router's `specs_of` finds no columns for this
            # category and publishes {} -- the honest table for a rate with no product
            # specification behind it.
            "metadata": None,
            "current_price_irr": row["unit_price_irr"],
            # `price_versions.unit_price_irr` is rials by definition, unlike the sheet,
            # whose cells are toman until the importer decides otherwise.
            "source_currency": "IRR",
            "raw_price": None,
            "secondary_price_irr": None,
            "secondary_price_basis": None,
            # All four are the resource's own unit. A rate is quoted per the unit the
            # resource is measured in; there is no second unit to cross into and nothing
            # was converted, so saying it four times is agreement, not repetition.
            "source_unit": unit,
            "source_unit_code": unit,
            "display_unit": unit,
            "target_unit": unit,
            "conversion_factor": None,
            "conversion_note": None,
            "factor_origin": None,
            # The sheet's other two spellings of the date do not exist here.
            "workflow_date_raw": None,
            "workflow_date_jalali": None,
            "workflow_date_gregorian": effective,
            # The business date IS the effective date, said out loud rather than implied:
            # `observedAt` below is that date widened to a timestamp, and a reader has to
            # be able to tell a widened date from a moment somebody recorded.
            "observed_at_source": "workflow_date",
            "observed_at": _midnight(effective),
            # When the rate was written down, which is a different fact from the day it
            # takes effect -- a price set in advance has the two days apart.
            "fetched_at": row.get("price_recorded_at") or _midnight(effective),
            # A price version is a decision, not a reading, so there is nothing to
            # validate and nothing that could be stale: it is in force or it is not.
            "validation_status": "valid",
            "validation_reasons": [],
            "resolution_status": "resolved",
            "resolution_reason": None,
            "source_row_number": None,
            "source_url": None,
            "origin": "manual",
            "entered_by": row.get("created_by"),
        }

    async def _product_factor(self, scope, provider_item_id, source, target):
        """`(factor, origin)` for one listing's own crossing, or `None`.

        Only a factor stored against THIS listing answers here. `unit_conversions` is not
        consulted: it holds dimension-level factors, and a dimension-level factor is
        exactly what `unit_conversion.py` already knows -- reaching for it at this point
        would mean a project could quietly define its own gram.
        """
        if source is None or target is None or source == target:
            return None
        if not hasattr(self.repository, "item_unit_factors"):
            return None
        for row in await self.repository.item_unit_factors(scope, provider_item_id):
            if (canonical_unit(row["from_unit"]), canonical_unit(row["to_unit"])) == (source, target):
                return Decimal(row["factor"]), row.get("origin")
        return None


    @staticmethod
    def _shape(row, outcome, display_unit, label=None, finance_resource=None, eligible=None):
        """One row of the API's answer. Every provenance field travels with the price."""
        shaped = {
            "provider_item_id": row["provider_item_id"],
            "external_id": row["external_id"],
            "external_name": row["external_name"],
            "category": row["category"],
            "provider_name": row["provider_name"],
            "active": row["active"],
            "inactive_reason": row["inactive_reason"],
            "worksheet": row.get("item_worksheet") or row.get("source_worksheet"),
            # The worksheet's own columns for this product, carried through untouched. The
            # router turns them into the category's published `specs`; nothing here reads
            # them, parses them, or prices from them.
            "metadata": row.get("metadata"),
            "current_price_irr": outcome.price,
            "raw_price": row["raw_price"],
            "source_currency": row["source_currency"],
            "secondary_price_irr": row["secondary_price_irr"],
            "secondary_price_basis": row["secondary_price_basis"],
            "source_unit": row["source_unit"],
            "source_unit_code": outcome.source_unit,
            "display_unit": display_unit,
            "target_unit": outcome.target_unit,
            "conversion_factor": outcome.conversion_factor,
            "conversion_note": outcome.conversion_note,
            "factor_origin": outcome.factor_origin,
            "workflow_date_raw": row["workflow_date_raw"],
            "workflow_date_jalali": row["workflow_date_jalali"],
            "workflow_date_gregorian": row["workflow_date_gregorian"],
            "observed_at_source": row["observed_at_source"],
            "observed_at": row["observed_at"],
            "fetched_at": row["fetched_at"],
            "validation_status": row["validation_status"],
            "validation_reasons": list(row["validation_reasons"] or []),
            "resolution_status": outcome.status,
            "resolution_reason": outcome.reason,
            "source_row_number": row["source_row_number"],
            "source_url": row["source_url"],
            # What a person wrote about this listing, travelling with the price so the
            # reader can see that a human decision is part of the answer.
            "label": (label or {}).get("label"),
            "label_display_name": (label or {}).get("display_name"),
            "label_product_type": (label or {}).get("product_type"),
            "label_source_basis": (label or {}).get("source_basis"),
            "finance_resource_id": (label or {}).get("finance_resource_id"),
            "mapping_approved": bool((label or {}).get("mapping_approved")),
            "labelled_by": (label or {}).get("created_by"),
            "labelled_at": (label or {}).get("created_at"),
            "label_version": (label or {}).get("version"),
            # The MSP/Finance side of the comparison. Reported whether or not it agrees,
            # because a reader deciding whether to trust a price needs to see both units,
            # not a verdict with the evidence hidden.
            "finance_resource_title": (finance_resource or {}).get("title"),
            "finance_resource_unit": (finance_resource or {}).get("base_unit"),
            "unit_alignment": _alignment(outcome, finance_resource),
            # Whether this listing's own attributes may be used to cross its price into
            # another unit. Derived on read and stored nowhere: it is a statement about
            # what the registry and the recorded facts allow today, not a fact about the
            # observation, and writing it down would freeze a judgement that changes the
            # moment somebody measures the product.
            "conversion_eligible": eligible,
            # A LATER row exists for this listing and could not be believed. The price
            # above is therefore older than the sheet's newest word on the product, and a
            # reader has to be told: without this they see a three-day-old number and no
            # reason it did not move.
            # Where this price came from. The prices table shows imported and
            # hand-entered rows side by side, and the two do not carry the same weight:
            # one is what a workbook published, the other is what a person obtained and
            # signed for. A column that cannot say which is a column that hides it.
            "origin": row.get("origin") or "sheet",
            "entered_by": row.get("entered_by"),
            "rejected_after_date": row.get("rejected_after_date"),
            "rejected_after_raw_price": row.get("rejected_after_raw_price"),
            "rejected_after_reasons": list(row.get("rejected_after_reasons") or []),
        }
        # The identity as the sheet stated it, on the day. These come off the OBSERVATION,
        # which is append-only, and they are what stops a later rename from rewriting the
        # evidence -- so they travel beside `externalName`/`providerName`, which are the
        # names the same listing carries NOW. They were declared in the response model and
        # dropped here, which made every one of them permanently null.
        shaped["product_id_snapshot"] = row.get("product_external_id")
        shaped["product_name_snapshot"] = row.get("product_name_snapshot")
        shaped["provider_name_snapshot"] = row.get("provider_name_snapshot")
        # The listing's typed specification columns, carried through exactly as stored. A
        # column the sheet said nothing about stays None: null means "not stated", and it
        # must never arrive as 0, "" or "-". Same reason as above -- 0027 added these, the
        # query selects them, the schema publishes them, and this dict left them behind.
        for column in SPEC_COLUMNS:
            shaped[column] = row.get(column)
        shaped["spec_source"] = row.get("spec_source")
        shaped["spec_conflicts"] = row.get("spec_conflicts")
        return shaped


def _clean(value):
    """A trimmed string, or None. An empty field is absent, not an empty string."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _conversion_eligible(row, source, target, factor):
    """Whether this listing's price may be crossed into the requested unit.

    Three ways to be eligible, and one way not to be:

        nothing to cross      no target was chosen, or it is the unit the price is
                              already in -- there is no crossing to be eligible FOR
        the registry bridges  kg -> ton is arithmetic over units. It is true of every
                              product and needs no property of this one
        somebody measured it  a factor recorded against THIS listing, by a person, with
                              a reason. That is evidence, and evidence is eligible

        NOT eligible          the crossing needs a property of the product, and the only
                              one stated is a WEIGHT WHOSE BASIS NOBODY GAVE

    The last case is the whole point. 415 listings state a weight and every one of them
    says 'unknown' for what it is per, because no worksheet read so far states it. 27 is
    then 27 per branch, per metre or per piece, and those differ by more than an order of
    magnitude -- the gram-versus-kilogram error, with a longer fuse. So an unknown basis
    is reported as ineligible rather than being quietly used, and `null` is returned when
    there is nothing to cross, because "no" and "not asked" are different answers.
    """
    if source is None or target is None or source == target:
        return None
    if can_convert(source, target):
        return True
    if factor is not None:
        return True
    # Only a product property can bridge it now, and a weight is the property these sheets
    # state. One with no basis is not a measurement anybody may convert with.
    if row.get("weight_kg") is not None:
        return row.get("weight_basis") in WEIGHT_BASES_USABLE_FOR_CONVERSION
    return False


def _alignment(outcome, finance_resource):
    """Whether the price is in the unit the Finance resource is measured in.

        not_mapped         no approved mapping, so there is nothing to align with
        missing_finance_unit   the resource itself states no unit
        aligned            the price is already in the resource's unit
        convertible        a different unit, but one the registry can bridge
        needs_factor       a different unit that only a measurement of this product bridges
        unresolved         the price never resolved, so there is nothing to align

    A verdict, never a correction. Nothing here converts anything or edits an MSP unit: the
    imported quantity and its unit are what the schedule said, and this only reports whether
    the market price can be expressed the same way.
    """
    if finance_resource is None:
        return "not_mapped"
    finance_unit = canonical_unit(finance_resource.get("base_unit"))
    if finance_unit is None:
        return "missing_finance_unit"
    if not outcome.usable:
        return "unresolved"
    priced_in = outcome.target_unit or outcome.source_unit
    if priced_in is None:
        return "unresolved"
    if priced_in == finance_unit:
        return "aligned"
    return "convertible" if can_convert(priced_in, finance_unit) else "needs_factor"
