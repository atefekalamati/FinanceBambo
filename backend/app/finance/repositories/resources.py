"""PostgreSQL persistence for scoped resources and append-only estimates."""
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..domain.resources import (DuplicateExternalResourceId, EstimateLine,
                                FinanceResource, UnitMismatch)


class PsycopgFinanceResourcesRepository:
    def __init__(self, connection): self._connection = connection

    @staticmethod
    def _resource(row):
        return FinanceResource(row["id"], row["organization_id"], row["project_id"],
            row["resource_type"], row["code"], row["title"], row["base_unit"], row["dimension"],
            row["external_resource_id"], row["created_by"], row["created_at"],
            row.get("source_resource_uid"))

    @staticmethod
    def _line(row, revisions=()):
        return EstimateLine(row["id"], row["organization_id"], row["project_id"], row["resource_id"],
            row["activity_external_id"], row["assignment_external_id"], row["original_quantity"],
            row["revised_quantity"], row["original_unit_price_irr"], row["source"], row["created_by"], row["created_at"],
            row.get("current_revision",0)+1,tuple(revisions),row.get("activity_title"),row.get("wbs_code"),
            row.get("source_assignment_uid"),row.get("source_task_uid"))

    async def list_resources(self, scope):
        async with self._connection.cursor(row_factory=dict_row) as c:
            await c.execute("SELECT * FROM finance_resources WHERE organization_id=%s AND project_id=%s AND deleted_at IS NULL ORDER BY created_at,id", (scope.organization_id, scope.project_id))
            return [self._resource(x) for x in await c.fetchall()]

    async def get_resource(self, scope, resource_id):
        async with self._connection.cursor(row_factory=dict_row) as c:
            await c.execute("SELECT * FROM finance_resources WHERE organization_id=%s AND project_id=%s AND id=%s AND deleted_at IS NULL", (scope.organization_id, scope.project_id, resource_id))
            row = await c.fetchone()
        return None if row is None else self._resource(row)

    async def create_resource(self, scope, value, audit_id):
        try:
            return await self._create_resource(scope, value, audit_id)
        except errors.UniqueViolation as error:
            if _is_external_identity_conflict(error):
                raise DuplicateExternalResourceId(
                    "another live resource in this project already uses external "
                    "resource id %r" % value.external_resource_id) from error
            raise

    async def _create_resource(self, scope, value, audit_id):
        async with self._connection.transaction():
            async with self._connection.cursor() as c:
                await c.execute("""INSERT INTO finance_resources (id,organization_id,project_id,resource_type,code,title,base_unit,dimension,external_resource_id,created_by,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (value.id,value.organization_id,value.project_id,value.type,value.code,value.title,value.base_unit,value.dimension,value.external_resource_id,value.created_by,value.created_at))
                await self._audit(c, audit_id, scope, value.created_by, "finance_resource.created", "finance_resources", value.id, None, value.__dict__, value.created_at)
        return value

    async def update_resource(self, scope, resource_id, changes, audit_id, occurred_at):
        current = await self.get_resource(scope, resource_id)
        if current is None: return None
        updated = current.with_changes(**changes)
        try:
            return await self._update_resource(scope, resource_id, current, updated,
                                               audit_id, occurred_at)
        except errors.UniqueViolation as error:
            if _is_external_identity_conflict(error):
                raise DuplicateExternalResourceId(
                    "another live resource in this project already uses external "
                    "resource id %r" % updated.external_resource_id) from error
            raise

    async def _update_resource(self, scope, resource_id, current, updated, audit_id,
                               occurred_at):
        async with self._connection.transaction():
            async with self._connection.cursor() as c:
                await c.execute("""UPDATE finance_resources SET resource_type=%s,code=%s,title=%s,base_unit=%s,dimension=%s,external_resource_id=%s WHERE organization_id=%s AND project_id=%s AND id=%s AND deleted_at IS NULL""", (updated.type,updated.code,updated.title,updated.base_unit,updated.dimension,updated.external_resource_id,scope.organization_id,scope.project_id,resource_id))
                await self._audit(c,audit_id,scope,scope.actor_user_id,"finance_resource.updated","finance_resources",resource_id,current.__dict__,updated.__dict__,occurred_at)
        return updated

    async def list_estimate_lines(self, scope):
        async with self._connection.cursor(row_factory=dict_row) as c:
            await c.execute("""SELECT l.*, COALESCE((SELECT r.new_quantity FROM estimate_revisions r WHERE r.organization_id=l.organization_id AND r.project_id=l.project_id AND r.estimate_line_id=l.id ORDER BY r.revision DESC LIMIT 1),CASE WHEN fr.resource_type='general_cost' THEN l.original_unit_price_irr ELSE l.original_quantity END) revised_quantity,COALESCE((SELECT max(r.revision) FROM estimate_revisions r WHERE r.organization_id=l.organization_id AND r.project_id=l.project_id AND r.estimate_line_id=l.id),0) current_revision FROM estimate_lines l JOIN finance_resources fr ON fr.organization_id=l.organization_id AND fr.project_id=l.project_id AND fr.id=l.resource_id WHERE l.organization_id=%s AND l.project_id=%s AND l.deleted_at IS NULL ORDER BY l.created_at,l.id""", (scope.organization_id,scope.project_id));lines=await c.fetchall()
            await c.execute("SELECT id,estimate_line_id,revision,previous_quantity,new_quantity,reason,created_by,created_at FROM estimate_revisions WHERE organization_id=%s AND project_id=%s ORDER BY estimate_line_id,revision",(scope.organization_id,scope.project_id));history=await c.fetchall()
        grouped={line["id"]:[] for line in lines}
        for revision in history:grouped.setdefault(revision["estimate_line_id"],[]).append({key:value for key,value in revision.items() if key!="estimate_line_id"})
        return [self._line(line,grouped[line["id"]]) for line in lines]

    async def list_task_resource_mappings(self, scope, page=1, page_size=100):
        """This project's optional MSP-task links, as the bridge states them. Read-only.

        Scoped through finance_resources -- the map carries no tenant keys by design
        (three columns), so the JOIN to a scope-filtered finance_resources IS the scoping.

        NO CORE TABLE IS READ HERE. Finance does not query `msp_tasks`, `msp_snapshots` or
        `msp_task_metrics`: the bridge is optional integration metadata, not the path
        Finance uses to obtain MPP values, and a Finance deployment must answer this
        endpoint whether or not Core's tables exist. `taskId` is returned as the opaque
        identifier the bridge stores; resolving it to a task is Core's business, and a
        caller that wants task detail asks Core for it.
        """
        offset = (max(page, 1) - 1) * page_size
        scoped = """
                  FROM finance_task_resource_map AS map
                  JOIN finance_resources AS resource ON resource.id = map.resource_id
                 WHERE resource.organization_id = %s AND resource.project_id = %s
                   AND resource.deleted_at IS NULL
        """
        async with self._connection.cursor(row_factory=dict_row) as c:
            await c.execute("""
                SELECT map.id, map.task_id, map.resource_id,
                       resource.code AS resource_code, resource.title AS resource_title,
                       resource.external_resource_id
            """ + scoped + """
                 ORDER BY map.task_id, resource.code
                 LIMIT %s OFFSET %s
            """, (scope.organization_id, scope.project_id, page_size, offset))
            rows = await c.fetchall()
            await c.execute("SELECT count(*) AS n " + scoped,
                            (scope.organization_id, scope.project_id))
            total = (await c.fetchone())["n"]
        return rows, total

    async def create_estimate_line(self, scope, value, audit_id):
        async with self._connection.transaction():
            async with self._connection.cursor() as c:
                await c.execute("""INSERT INTO estimate_lines (id,organization_id,project_id,resource_id,activity_external_id,assignment_external_id,original_quantity,original_unit_price_irr,source,created_by,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (value.id,value.organization_id,value.project_id,value.resource_id,value.activity_external_id,value.assignment_external_id,value.original_quantity,value.original_unit_price_irr,value.source,value.created_by,value.created_at))
                await self._audit(c,audit_id,scope,value.created_by,"estimate_line.created","estimate_lines",value.id,None,value.__dict__,value.created_at)
        return value

    async def append_estimate_revision(self, scope, line_id, revision_id, audit_id, new_quantity, reason, actor, occurred_at):
        async with self._connection.transaction():
            async with self._connection.cursor(row_factory=dict_row) as c:
                await c.execute("""SELECT l.*, fr.resource_type, COALESCE((SELECT r.new_quantity FROM estimate_revisions r WHERE r.organization_id=l.organization_id AND r.project_id=l.project_id AND r.estimate_line_id=l.id ORDER BY r.revision DESC LIMIT 1),CASE WHEN fr.resource_type='general_cost' THEN l.original_unit_price_irr ELSE l.original_quantity END) revised_quantity, COALESCE((SELECT max(r.revision) FROM estimate_revisions r WHERE r.organization_id=l.organization_id AND r.project_id=l.project_id AND r.estimate_line_id=l.id),0) current_revision FROM estimate_lines l JOIN finance_resources fr ON fr.organization_id=l.organization_id AND fr.project_id=l.project_id AND fr.id=l.resource_id WHERE l.organization_id=%s AND l.project_id=%s AND l.id=%s AND l.deleted_at IS NULL FOR UPDATE""", (scope.organization_id,scope.project_id,line_id))
                row = await c.fetchone()
                if row is None: return None
                if row["resource_type"] == "general_cost" and (new_quantity is None or new_quantity < 0 or new_quantity != new_quantity.to_integral_value()):
                    raise UnitMismatch("general cost revision requires an exact integer IRR amount")
                await c.execute("""INSERT INTO estimate_revisions (id,organization_id,project_id,estimate_line_id,revision,previous_quantity,new_quantity,reason,created_by,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (revision_id,scope.organization_id,scope.project_id,line_id,row["current_revision"]+1,row["revised_quantity"],new_quantity,reason,actor,occurred_at))
                await self._audit(c,audit_id,scope,actor,"estimate_line.revised","estimate_lines",line_id,{"quantity":row["revised_quantity"]},{"quantity":new_quantity},occurred_at,reason)
        return self._line({**row,"current_revision":row["current_revision"]+1}).with_revised_quantity(new_quantity)

    @staticmethod
    async def _audit(c,audit_id,scope,actor,action,entity_type,entity_id,before,after,at,reason=None):
        def clean(value):
            if value is None: return None
            return {k: str(v) if isinstance(v,(UUID,Decimal,datetime)) else v for k,v in value.items()}
        await c.execute("""INSERT INTO finance_audit_events (id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,reason,before_values,after_values,occurred_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (audit_id,scope.organization_id,scope.project_id,actor,action,entity_type,entity_id,reason,Jsonb(clean(before)),Jsonb(clean(after)),at))


def _is_external_identity_conflict(error):
    """Whether a UniqueViolation is 0009's external-identity index, by its NAME --
    a PK collision or any other unique constraint must keep its own meaning."""
    return getattr(error.diag, "constraint_name", None) ==         "ux_finance_resources_external_identity"
