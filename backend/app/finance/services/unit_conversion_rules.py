# -*- coding: utf-8 -*-
"""Writing a conversion rule down, and closing the questions it answers.

WHAT THIS REFUSES, AND WHY THE REFUSALS ARE NOT SYMMETRIC

A rule is a claim about the world, and how broadly it may be believed depends on what kind
of claim it is. `1 ton = 1000 kg` is arithmetic and is safe everywhere. `1 branch = 22 kg`
is a weighing of one product and is wrong for the next size. So the same API call is
accepted at one scope and refused at another, and the refusal says which.

APPROVAL IS A SEPARATE ACT FROM WRITING

A rule arrives as a draft and changes nothing. Approving it is what lets it into a
calculation, and approving a rule that outlives one project needs a stronger permission
than editing that project -- otherwise a project editor could write a site-wide statement
every other project would then inherit.

CLOSING AN ISSUE IS PART OF APPROVING

Approving a rule and leaving the mismatch it answers open would be two facts disagreeing.
They happen together.
"""

import logging
from datetime import date, datetime, timezone

from ..domain.conversion_rules import (NARROW_SCOPES, ConversionRuleRefused,
                                       crosses_dimensions, resolve_rule,
                                       validate_scope)
from ..domain.errors import FinanceDomainError
from ..domain.unit_registry import UNIT_REGISTRY

#: An audit line that fails must not cost the rule it describes.
LOG = logging.getLogger("finance.conversion_rules")

#: Scopes that outlive one project. Writing one is a statement about every project this
#: tenant will ever run, so it is gated harder than editing the project in front of you.
TENANT_WIDE_SCOPES = frozenset({"global", "organization"})

APPROVE_TENANT_RULE_PERMISSION = "finance.manage_settings"


class UnitConversionRuleRefused(FinanceDomainError):
    status = 422
    code = "FINANCE_CONVERSION_RULE_REFUSED"


class UnitConversionRuleForbidden(FinanceDomainError):
    status = 403
    code = "FINANCE_CONVERSION_RULE_FORBIDDEN"


class UnitConversionRuleService:
    def __init__(self, repository, clock=date.today):
        self.repository = repository
        self.clock = clock

    # ------------------------------------------------------------------------- read

    async def list_rules(self, scope, **filters):
        return await self.repository.list_rules(scope, **filters)

    async def rule(self, scope, rule_id):
        return await self.repository.rule(scope, rule_id)

    async def history(self, scope, rule_id):
        return await self.repository.history_for(scope, rule_id)

    async def list_issues(self, scope, *, status="open", estimate_line_id=None):
        return await self.repository.list_issues(scope, status=status,
                                                 estimate_line_id=estimate_line_id)

    async def resolve_for(self, scope, *, from_unit, to_unit, provider_id=None,
                          provider_item_id=None, category=None, on_date=None):
        """The rule that applies to this crossing, or None.

        The only entry point the pricing path uses. Everything about precedence is in the
        domain; this fetches the candidates and hands them over.
        """
        if not from_unit or not to_unit or from_unit == to_unit:
            return None
        candidates = await self.repository.candidates_for(
            scope, from_unit=from_unit, to_unit=to_unit)
        return resolve_rule(candidates, from_unit=from_unit, to_unit=to_unit,
                            provider_id=provider_id, provider_item_id=provider_item_id,
                            category=category, on_date=on_date)

    async def candidates_by_pair(self, scope, pairs):
        """Approved rules for many crossings at once, for a caller pricing a whole table.

        Returns the raw candidates rather than resolved rules, because precedence depends
        on the ROW -- its listing, its supplier, its category -- and resolving here would
        mean one answer for every row that shares a unit pair. The caller keeps this and
        calls `resolve_rule` per row against it, which is arithmetic in memory rather than
        a query.
        """
        return await self.repository.candidates_for_pairs(scope, pairs)

    @staticmethod
    def rule_from(candidates, *, from_unit, to_unit, provider_id=None,
                  provider_item_id=None, category=None, on_date=None):
        """`resolve_for`'s decision, against candidates already in hand. No IO."""
        if not from_unit or not to_unit or from_unit == to_unit:
            return None
        return resolve_rule(candidates.get((from_unit, to_unit)) or [],
                            from_unit=from_unit, to_unit=to_unit,
                            provider_id=provider_id, provider_item_id=provider_item_id,
                            category=category, on_date=on_date)

    async def preview_rule(self, scope, rule_id, *, price_irr=None):
        """What a rule would do to a price, without letting it near a calculation.

        A draft can be previewed -- that is the point of a draft -- and the answer says
        plainly that it is not applied.
        """
        rule = await self.repository.rule(scope, rule_id)
        if rule is None:
            raise UnitConversionRuleRefused("این قانون تبدیل یافت نشد")
        from ..domain.daily_estimate import convert_daily_unit_price
        converted, multiplier, method, source = convert_daily_unit_price(
            price_irr, rule["from_unit"], rule["to_unit"], rule)
        return {
            "rule_id": str(rule["id"]),
            "version": rule["version"],
            "status": rule["status"],
            "applied_to_calculations": rule["status"] == "approved",
            "from_unit": rule["from_unit"],
            "to_unit": rule["to_unit"],
            "conversion_method": method or rule["conversion_method"],
            "conversion_multiplier": None if multiplier is None else str(multiplier),
            "source_price_irr": None if price_irr is None else str(price_irr),
            "converted_price_irr": None if converted is None else str(converted),
            "conversion_source": source,
        }

    # ------------------------------------------------------------------------ write

    async def create_rule(self, scope, *, payload, actor_id, permissions=()):
        """A new DRAFT rule. Nothing it says reaches a calculation until it is approved."""
        scope_type = (payload.scope_type or "").strip()
        from_unit = (payload.from_unit or "").strip()
        to_unit = (payload.to_unit or "").strip()
        reason = (payload.reason or "").strip()
        if not reason:
            raise UnitConversionRuleRefused("دلیل ثبت این قانون الزامی است")

        if scope_type in TENANT_WIDE_SCOPES:
            self._require_tenant_permission(permissions, "write")

        # An admission only has a subject when the crossing really does depend on the
        # product AND the scope is wider than one listing. Anywhere else it is stored as
        # false: a flag set on «تن» to «کیلوگرم» would later be read as "somebody had
        # doubts about this rule", and nobody did.
        acknowledged = bool(getattr(payload, "product_dependent_acknowledged", False)
                            and crosses_dimensions(from_unit, to_unit)
                            and scope_type not in NARROW_SCOPES)
        try:
            validate_scope(scope_type=scope_type, from_unit=from_unit, to_unit=to_unit,
                           project_id=payload.project_id or scope.project_id,
                           provider_id=payload.provider_id,
                           provider_item_id=payload.provider_item_id,
                           category=payload.category,
                           product_dependent_acknowledged=acknowledged)
        except ConversionRuleRefused as refused:
            raise UnitConversionRuleRefused(refused.message_fa or str(refused)) from refused

        method = (payload.conversion_method or "factor").strip()
        if method == "factor":
            if payload.factor_value is None or payload.factor_value <= 0:
                raise UnitConversionRuleRefused("ضریب تبدیل باید عددی مثبت باشد")
        elif method == "formula":
            if not payload.formula_definition:
                raise UnitConversionRuleRefused("تعریف فرمول الزامی است")
        else:
            raise UnitConversionRuleRefused("روش تبدیل باید «factor» یا «formula» باشد")

        # ---------------------------------------- one crossing, one rule, either spelling
        # Now that a rule is read from either side, `branch->kg` and `kg->branch` in the
        # SAME scope are two live answers to one question -- and nothing stops them
        # disagreeing, because 22 and 0.05 are not each other's inverse. The partial unique
        # index cannot see this: to the database the two rows have different unit pairs.
        #
        # Refused here rather than at the constraint so the message can name the rule that
        # is in the way, its number and its direction, in Persian. Replacing it is the
        # supported move and `supersedes_rule_id` is how -- which the message says, because
        # "already exists" without a way forward is where a person gets stuck.
        if method == "factor" and not payload.supersedes_rule_id:
            opposite = await self._opposite_direction_rule(
                scope, scope_type=scope_type, from_unit=from_unit, to_unit=to_unit,
                project_id=scope.project_id if scope_type == "project" else None,
                provider_item_id=payload.provider_item_id,
                provider_id=payload.provider_id, category=payload.category)
            if opposite is not None:
                raise UnitConversionRuleRefused(
                    "برای همین عبور، قانونی در جهت معکوس از قبل فعال است: «۱ %s = %s %s» "
                    "(نسخهٔ %s). همان قانون هر دو جهت را پاسخ می‌دهد، پس ثبت این یکی دو "
                    "پاسخ ناسازگار می‌سازد. برای تغییر، آن را با supersedes_rule_id "
                    "جایگزین کنید."
                    % (opposite["from_unit"], _plain(opposite.get("factor_value")),
                       opposite["to_unit"], opposite.get("version")))

        values = {
            # A project rule is scoped to THIS project, never to one named in the body: a
            # caller choosing its own project_id would be choosing its own tenant.
            "project_id": scope.project_id if scope_type == "project" else None,
            "provider_item_id": payload.provider_item_id,
            "provider_id": payload.provider_id,
            "category": payload.category,
            "scope_type": scope_type,
            "from_unit": from_unit,
            "to_unit": to_unit,
            "conversion_method": method,
            "factor_value": payload.factor_value,
            "formula_definition": payload.formula_definition,
            "formula_schema_version": payload.formula_schema_version,
            "direction_definition": payload.direction_definition,
            "effective_from": payload.effective_from or self.clock(),
            "supersedes_rule_id": payload.supersedes_rule_id,
            "evidence_source": payload.evidence_source,
            "reason": reason,
            # Stamped here rather than accepted from the request: a caller that could
            # supply the actor could make the admission in somebody else's name, which is
            # the one thing the three columns exist to prevent.
            "product_dependent_acknowledged": acknowledged,
            "product_dependent_acknowledged_by": actor_id if acknowledged else None,
            "product_dependent_acknowledged_at": (datetime.now(timezone.utc)
                                                  if acknowledged else None),
        }
        rule = await self.repository.create_rule(scope, values=values, created_by=actor_id)
        if acknowledged:
            # Its own audit line. The rule's creation is already recorded; this says a
            # person made a product-dependent claim at a scope that normally refuses one,
            # and it is findable without reading every rule's row.
            await self._record_acknowledgement(scope, rule, actor_id=actor_id,
                                               from_unit=from_unit, to_unit=to_unit,
                                               scope_type=scope_type)
        return rule

    async def _record_acknowledgement(self, scope, rule, *, actor_id, from_unit, to_unit,
                                      scope_type):
        """Audit the admission, and never fail the rule because auditing failed."""
        recorder = getattr(self.repository, "record_audit_event", None)
        if recorder is None:
            return
        try:
            await recorder(
                scope, action="finance.conversion_rule.product_dependent_acknowledged",
                entity_type="finance_unit_conversion_rules",
                entity_id=(rule or {}).get("id"), actor_id=actor_id,
                after_values={"fromUnit": from_unit, "toUnit": to_unit,
                              "scopeType": scope_type})
        except Exception:                                      # noqa: BLE001
            LOG.exception("conversion rule acknowledgement audit failed")

    async def approve_rule(self, scope, rule_id, *, actor_id, permissions=()):
        """Let a rule into calculations, and close the questions it answers."""
        rule = await self.repository.rule(scope, rule_id)
        if rule is None:
            raise UnitConversionRuleRefused("این قانون تبدیل یافت نشد")
        if rule["status"] != "draft":
            raise UnitConversionRuleRefused(
                "تنها قانونی که هنوز پیش‌نویس است می‌تواند تأیید شود")
        if rule["scope_type"] in TENANT_WIDE_SCOPES:
            self._require_tenant_permission(permissions, "approve")

        approved = await self.repository.approve_rule(scope, rule_id, approved_by=actor_id)
        if approved is None:
            raise UnitConversionRuleRefused("این قانون تبدیل تأیید نشد")

        resolved = await self.repository.resolve_issues_for(
            scope, from_unit=approved["from_unit"], to_unit=approved["to_unit"],
            rule_id=approved["id"], resolved_by=actor_id,
            provider_item_id=approved.get("provider_item_id"))
        return approved, resolved

    async def supersede_rule(self, scope, rule_id, *, effective_to=None, permissions=()):
        rule = await self.repository.rule(scope, rule_id)
        if rule is None:
            raise UnitConversionRuleRefused("این قانون تبدیل یافت نشد")
        if rule["scope_type"] in TENANT_WIDE_SCOPES:
            self._require_tenant_permission(permissions, "supersede")
        closed = await self.repository.supersede_rule(
            scope, rule_id, effective_to=effective_to or self.clock())
        if closed is None:
            raise UnitConversionRuleRefused("این قانون پیش‌تر بسته شده است")
        return closed

    async def record_mismatch(self, scope, *, estimate_line_id=None,
                              finance_resource_id=None, provider_item_id=None,
                              source_task_uid=None, source_assignment_uid=None,
                              source_resource_uid=None, resource_unit=None,
                              daily_price_unit=None, error_code):
        """Make an unresolved mismatch a record rather than a message.

        Called from the read path, which is unusual and deliberate: the moment a preview
        cannot produce a figure is the moment the question exists, and a question nobody
        wrote down is one nobody can be assigned.
        """
        return await self.repository.record_issue(scope, values={
            "estimate_line_id": estimate_line_id,
            "finance_resource_id": finance_resource_id,
            "provider_item_id": provider_item_id,
            "source_task_uid": source_task_uid,
            "source_assignment_uid": source_assignment_uid,
            "source_resource_uid": source_resource_uid,
            "resource_unit": resource_unit,
            "daily_price_unit": daily_price_unit,
            "error_code": error_code,
        })

    async def _opposite_direction_rule(self, scope, *, scope_type, from_unit, to_unit,
                                       project_id, provider_item_id, provider_id,
                                       category):
        """An active rule for the SAME scope stating the same crossing backwards, or None.

        Same scope is the whole test. A `kg->branch` rule at global level and a
        `branch->kg` rule on one listing are not in conflict -- the narrow one wins and
        that is the ladder working. Two at the same rank are the problem, because then
        only the direct/reverse tiebreak separates them and the number a row gets depends
        on which way somebody typed.
        """
        # `list_rules` rather than `candidates_for`, because that one returns only
        # APPROVED rules and a draft is exactly what this has to catch. Two drafts in
        # opposite directions are a conflict waiting for somebody to approve both, and the
        # moment to say so is while there is still one rule, not after there are two.
        candidates = await self.repository.list_rules(
            scope, from_unit=to_unit, to_unit=from_unit)
        for rule in candidates or ():
            if rule.get("from_unit") != to_unit or rule.get("to_unit") != from_unit:
                continue
            if rule.get("scope_type") != scope_type:
                continue
            if rule.get("project_id") != project_id:
                continue
            if rule.get("provider_item_id") != provider_item_id:
                continue
            if rule.get("provider_id") != provider_id:
                continue
            if rule.get("category") != category:
                continue
            if rule.get("superseded_at") is not None:
                continue
            # A rule somebody already withdrew is not in the way.
            if rule.get("status") in ("superseded", "rejected", "withdrawn"):
                continue
            return rule
        return None

    @staticmethod
    def _require_tenant_permission(permissions, action):
        if APPROVE_TENANT_RULE_PERMISSION not in set(permissions or ()):
            raise UnitConversionRuleForbidden(
                "قانونی که فراتر از این پروژه است تنها با دسترسی «%s» قابل %s است"
                % (APPROVE_TENANT_RULE_PERMISSION,
                   {"write": "ثبت", "approve": "تأیید", "supersede": "بستن"}[action]))


def _plain(value):
    """A factor as a person wrote it: no exponent, no trailing zeros, never a float."""
    if value is None:
        return "-"
    text = format(value, "f") if hasattr(value, "is_finite") else str(value)
    return text.rstrip("0").rstrip(".") if "." in text else text


def registry_units():
    """The units a rule may name, for the settings form's dropdowns."""
    return [{"code": code, "label": unit.label_fa, "dimension": unit.dimension,
             "dimension_label": unit.dimension_label_fa,
             # Whether a rule crossing INTO this unit may be written broadly. The form can
             # then say why a scope is unavailable instead of only refusing on save.
             "product_dependent_from": sorted(
                 other for other in UNIT_REGISTRY if other != code
                 and crosses_dimensions(other, code))}
            for code, unit in UNIT_REGISTRY.items() if unit.active]
