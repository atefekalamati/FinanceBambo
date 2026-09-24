from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from ..domain.estimate_basis import (effective_original_price,
                                    effective_original_quantity,
                                    estimate_line_effective_on_or_before,
                                    original_value_source)
from ..domain.price_resolution import resolved_price_columns, resolved_price_joins


class PsycopgLiveReportRepository:
    async def progress_reference_for_host(self,scope,host_snapshot_id):
        """The stored reference for one Core snapshot, if there is one. Read-only."""
        from .progress import REFERENCE_COLUMNS
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                "SELECT %s FROM progress_snapshot_refs WHERE organization_id=%%s "
                "AND project_id=%%s AND host_snapshot_id=%%s" % REFERENCE_COLUMNS,
                (scope.organization_id,scope.project_id,host_snapshot_id))
            return await cursor.fetchone()

    async def progress_reference_for_snapshot(self,scope,progress_snapshot_id):
        """The stored reference for one Finance source version, if any. Read-only."""
        from .progress import REFERENCE_COLUMNS
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(
                "SELECT %s FROM progress_snapshot_refs WHERE organization_id=%%s "
                "AND project_id=%%s AND progress_snapshot_id=%%s" % REFERENCE_COLUMNS,
                (scope.organization_id,scope.project_id,progress_snapshot_id))
            return await cursor.fetchone()

    async def ensure_progress_reference(self,scope,value):
        """The same idempotent write the progress repository uses, not a second copy."""
        from .progress import ensure_progress_reference
        return await ensure_progress_reference(self.db,scope,value)

    def __init__(self,db):self.db=db

    async def load(self,scope,as_of):
        """Everything one report needs, in one pass.

        `l.legacy_status IS NULL` is the MPP-derived population and it is the whole of
        0030's purpose here. A row with no MPP assignment and no MPP task is a row no
        schedule can account for; it used to be summed alongside the rest because this
        query had no predicate that could tell them apart. On the audited project that
        was 120 rows carrying 1,615,000,000 IRR against 3,605,823,967,776 IRR the file
        does account for.

        The rows are not deleted, not deactivated, and still reachable everywhere else --
        including from the two invoice lines that name them. They are excluded from THIS
        total, which is the one that claims to describe the schedule.

        Issued reports are untouched: an issued report froze its own payload and is never
        recomputed from this query.
        """
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT id,gross_built_area FROM finance_project_settings WHERE organization_id=%s AND project_id=%s AND effective_from<=%s ORDER BY revision DESC LIMIT 1",(scope.organization_id,scope.project_id,as_of));settings=await cursor.fetchone()
            cutoff="(SELECT as_of FROM report_cutoff)"
            eligibility=estimate_line_effective_on_or_before("l", cutoff)
            await cursor.execute("""WITH report_cutoff AS (SELECT %s::date AS as_of) SELECT l.id,l.resource_id,l.activity_external_id,NULL::text activity_title,NULL::text wbs_code,l.assignment_external_id,""" + effective_original_quantity("l", cutoff) + """ original_quantity,""" + effective_original_price("l", cutoff) + """ original_unit_price_irr,COALESCE((SELECT er.id FROM estimate_revisions er WHERE er.organization_id=l.organization_id AND er.project_id=l.project_id AND er.estimate_line_id=l.id AND (er.created_at AT TIME ZONE 'Asia/Tehran')::date<=%s ORDER BY er.revision DESC LIMIT 1),l.id) estimate_version_id,COALESCE((SELECT er.new_quantity FROM estimate_revisions er WHERE er.organization_id=l.organization_id AND er.project_id=l.project_id AND er.estimate_line_id=l.id AND (er.created_at AT TIME ZONE 'Asia/Tehran')::date<=%s ORDER BY er.revision DESC LIMIT 1),""" + effective_original_quantity("l", cutoff) + """) revised_quantity,r.resource_type resource_type,r.code resource_code,r.title resource_title,r.base_unit,r.dimension,""" + resolved_price_columns("r.base_unit") + """ FROM estimate_lines l JOIN finance_resources r ON r.organization_id=l.organization_id AND r.project_id=l.project_id AND r.id=l.resource_id""" + resolved_price_joins("l") + """ WHERE l.organization_id=%s AND l.project_id=%s AND l.deleted_at IS NULL AND r.deleted_at IS NULL AND l.legacy_status IS NULL AND """ + eligibility + """ ORDER BY l.created_at,l.id""",(as_of,as_of,as_of,as_of,as_of,scope.organization_id,scope.project_id));estimates=await cursor.fetchall()
            await cursor.execute("""SELECT EXISTS (
                SELECT 1 FROM estimate_lines l
                WHERE l.organization_id=%s AND l.project_id=%s AND l.deleted_at IS NULL
                  AND l.legacy_status IS NULL
                  AND NOT """ + estimate_line_effective_on_or_before("l", "%s") + """
            ) AS uncertain""",(scope.organization_id,scope.project_id,as_of,as_of))
            coverage=await cursor.fetchone()
            coverage_known=bool(estimates) and not coverage["uncertain"]
            await cursor.execute("""SELECT i.id invoice_id,il.estimate_line_id,il.resource_id,il.quantity,il.unit,il.final_line_amount_irr,i.financial_effect_sign,r.resource_type,r.code resource_code,r.base_unit,r.dimension FROM invoice_lines il JOIN invoices i ON i.organization_id=il.organization_id AND i.project_id=il.project_id AND i.id=il.invoice_id JOIN finance_resources r ON r.organization_id=il.organization_id AND r.project_id=il.project_id AND r.id=il.resource_id WHERE il.organization_id=%s AND il.project_id=%s AND i.status IN ('confirmed','voided','corrected') AND i.invoice_date<=%s""",(scope.organization_id,scope.project_id,as_of));invoices=await cursor.fetchall()
            await cursor.execute("""SELECT DISTINCT ON (source_unit,target_unit,dimension) id,source_unit,target_unit,dimension,factor FROM unit_conversions WHERE organization_id=%s AND project_id=%s AND effective_from<=%s ORDER BY source_unit,target_unit,dimension,(scope_kind='project') DESC,effective_from DESC,version DESC,created_at DESC,id DESC""",(scope.organization_id,scope.project_id,as_of));conversions=await cursor.fetchall()
            await cursor.execute("SELECT id progress_snapshot_ref_id,progress_snapshot_id,host_snapshot_id,reporting_date FROM progress_snapshot_refs WHERE organization_id=%s AND project_id=%s AND reporting_date<=%s AND snapshot_status='ready' ORDER BY reporting_date DESC,imported_at DESC LIMIT 1",(scope.organization_id,scope.project_id,as_of));snapshot=await cursor.fetchone()
        return {"settings_id":None if settings is None else settings["id"],"gross_area":None if settings is None else settings["gross_built_area"],"estimate_coverage_known":coverage_known,"estimates":estimates,"invoices":invoices,"conversions":conversions,"snapshot":snapshot}

    async def monthly_actuals(self,scope,date_from,date_to):
        """Day-level aggregates for the monthly series, summed by PostgreSQL.

        The status set and the signed line amount are the live report's definition of
        actual cost (see `load`), so the two cannot drift. Grouping stops at the day
        because Persian months do not align with Gregorian ones — the calendar cut is
        made in the domain, over at most one row per day per resource type.
        """
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("""SELECT i.invoice_date,r.resource_type,SUM(il.final_line_amount_irr*i.financial_effect_sign) amount_irr FROM invoice_lines il JOIN invoices i ON i.organization_id=il.organization_id AND i.project_id=il.project_id AND i.id=il.invoice_id JOIN finance_resources r ON r.organization_id=il.organization_id AND r.project_id=il.project_id AND r.id=il.resource_id WHERE il.organization_id=%s AND il.project_id=%s AND i.status IN ('confirmed','voided','corrected') AND i.invoice_date>=%s AND i.invoice_date<=%s GROUP BY i.invoice_date,r.resource_type ORDER BY i.invoice_date,r.resource_type""",(scope.organization_id,scope.project_id,date_from,date_to));amounts=await cursor.fetchall()
            await cursor.execute("""SELECT invoice_date,financial_effect_sign,COUNT(*) document_count FROM invoices WHERE organization_id=%s AND project_id=%s AND status IN ('confirmed','voided','corrected') AND invoice_date>=%s AND invoice_date<=%s GROUP BY invoice_date,financial_effect_sign ORDER BY invoice_date""",(scope.organization_id,scope.project_id,date_from,date_to));documents=await cursor.fetchall()
        return amounts,documents

    async def snapshot(self,scope,snapshot_id):
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT id progress_snapshot_ref_id,progress_snapshot_id,host_snapshot_id,reporting_date FROM progress_snapshot_refs WHERE organization_id=%s AND project_id=%s AND progress_snapshot_id=%s AND snapshot_status='ready'",(scope.organization_id,scope.project_id,snapshot_id));return await cursor.fetchone()

    async def issue(self,scope,value,payload,audit_id):
        async with self.db.transaction():
            async with self.db.cursor() as cursor:
                await cursor.execute("INSERT INTO report_snapshots(id,organization_id,project_id,reporting_date,progress_snapshot_ref_id,finance_settings_id,resource_version_ids,estimate_revision_ids,price_version_ids,unit_conversion_ids,invoice_ids,calculated_metrics,snapshot_payload,issued_by,issued_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",(value["report_snapshot_id"],scope.organization_id,scope.project_id,value["reporting_date"],value["progress_snapshot_ref_id"],value["finance_settings_id"],Jsonb(value["resource_version_ids"]),Jsonb(value["estimate_revision_ids"]),Jsonb(value["price_version_ids"]),Jsonb(value["unit_conversion_ids"]),Jsonb(value["invoice_ids"]),Jsonb(value["calculated_metrics"]),Jsonb(payload),scope.actor_user_id,value["issued_at"]))
                await cursor.execute("INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,before_values,after_values,occurred_at) VALUES(%s,%s,%s,%s,'report_snapshot.issued','report_snapshots',%s,NULL,%s,%s)",(audit_id,scope.organization_id,scope.project_id,scope.actor_user_id,value["report_snapshot_id"],Jsonb({"progressSnapshotId":str(value["progress_snapshot_id"]),"reportingDate":str(value["reporting_date"])}),value["issued_at"]))
        return value

    async def get(self,scope,report_id):
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT id report_snapshot_id,organization_id,project_id,reporting_date,progress_snapshot_ref_id,resource_version_ids,estimate_revision_ids,price_version_ids,unit_conversion_ids,invoice_ids,calculated_metrics,issued_by,issued_at,(SELECT progress_snapshot_id FROM progress_snapshot_refs p WHERE p.organization_id=r.organization_id AND p.project_id=r.project_id AND p.id=r.progress_snapshot_ref_id) progress_snapshot_id FROM report_snapshots r WHERE organization_id=%s AND project_id=%s AND id=%s",(scope.organization_id,scope.project_id,report_id))
            return await cursor.fetchone()

    @staticmethod
    def _snapshot_filters(scope,reporting_date_from,reporting_date_to):
        """Build the shared WHERE clause so the count and the page always agree."""
        clauses=["organization_id=%s","project_id=%s"];values=[scope.organization_id,scope.project_id]
        # reporting_date is a date, so both ends compare directly and both are inclusive.
        if reporting_date_from:clauses.append("reporting_date>=%s");values.append(reporting_date_from)
        if reporting_date_to:clauses.append("reporting_date<=%s");values.append(reporting_date_to)
        return " AND ".join(clauses),values

    async def list(self,scope,limit=50,offset=0,reporting_date_from=None,reporting_date_to=None):
        """Summaries only: the pinned id arrays and metrics belong to the detail endpoint."""
        where,values=self._snapshot_filters(scope,reporting_date_from,reporting_date_to)
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(f"SELECT COUNT(*) AS total FROM report_snapshots WHERE {where}",tuple(values))
            total=(await cursor.fetchone())["total"]
            await cursor.execute(
                "SELECT id report_snapshot_id,reporting_date,issued_at,issued_by,"
                "jsonb_array_length(invoice_ids) invoice_count,"
                "jsonb_array_length(price_version_ids) price_version_count,"
                "(SELECT progress_snapshot_id FROM progress_snapshot_refs p"
                " WHERE p.organization_id=r.organization_id AND p.project_id=r.project_id"
                " AND p.id=r.progress_snapshot_ref_id) progress_snapshot_id"
                f" FROM report_snapshots r WHERE {where}"
                " ORDER BY reporting_date DESC,issued_at DESC,id DESC LIMIT %s OFFSET %s",
                tuple(values+[limit,offset]))
            return await cursor.fetchall(),total

    async def export_payload(self,scope,report_id):
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT id report_snapshot_id,reporting_date,snapshot_payload FROM report_snapshots WHERE organization_id=%s AND project_id=%s AND id=%s",(scope.organization_id,scope.project_id,report_id))
            return await cursor.fetchone()

    async def latest_overrides(self,scope,progress_snapshot_ref_id):
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("""SELECT DISTINCT ON (o.estimate_line_id) o.estimate_line_id,o.computed_value,o.override_value,o.reason,o.created_by,o.created_at,l.activity_external_id,l.assignment_external_id FROM progress_overrides o JOIN estimate_lines l ON l.organization_id=o.organization_id AND l.project_id=o.project_id AND l.id=o.estimate_line_id WHERE o.organization_id=%s AND o.project_id=%s AND o.progress_snapshot_ref_id=%s ORDER BY o.estimate_line_id,o.created_at DESC,o.id DESC""",(scope.organization_id,scope.project_id,progress_snapshot_ref_id))
            return await cursor.fetchall()
