from decimal import Decimal
from dataclasses import replace

from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from uuid import uuid4

from ..domain.attachments import FinanceAttachment
from ..domain.extractions import ExtractionDraft, ExtractionField


class PsycopgExtractionRepository:
    def __init__(self, db): self.db = db

    @staticmethod
    def _map(row):
        attachment = FinanceAttachment(row["attachment_id"], row["organization_id"], row["project_id"],
            row["logical_type"], row["original_name_safe"], row["stored_name"], row["mime_type"],
            row["size_bytes"], row["sha256"], row["uploaded_by"], row["uploaded_at"],
            row["processing_status"], row["storage_key"], row["invoice_id"])
        fields = [ExtractionField(item["key"], item.get("extractedValue"), item.get("confirmedValue"),
            item["confidence"], item.get("editedByUser", False)) for item in row["extracted_fields"]]
        return ExtractionDraft(row["id"], row["organization_id"], row["project_id"], attachment,
            row["version"], row["review_status"], row["invoice_status"], row["provider_adapter"], fields,
            row["submitted_by"], row["created_at"], Decimal(row["financial_effect_irr"]),
            row["confirmed_by"], row["confirmed_at"])

    async def get(self, scope, draft_id):
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT d.*,a.id attachment_id,a.invoice_id,a.logical_type,a.original_name_safe,a.stored_name,a.mime_type,a.size_bytes,a.sha256,a.storage_key,a.processing_status,a.uploaded_by,a.uploaded_at,COALESCE(i.status,'draft') invoice_status FROM extraction_drafts d JOIN finance_attachments a ON a.organization_id=d.organization_id AND a.project_id=d.project_id AND a.id=d.attachment_id LEFT JOIN invoices i ON i.organization_id=a.organization_id AND i.project_id=a.project_id AND i.id=a.invoice_id WHERE d.organization_id=%s AND d.project_id=%s AND d.id=%s AND a.deleted_at IS NULL", (scope.organization_id, scope.project_id, draft_id))
            row = await cursor.fetchone()
        return None if row is None else self._map(row)

    async def latest_for_file(self, scope, file_id):
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT d.*,a.id attachment_id,a.invoice_id,a.logical_type,a.original_name_safe,a.stored_name,a.mime_type,a.size_bytes,a.sha256,a.storage_key,a.processing_status,a.uploaded_by,a.uploaded_at,COALESCE(i.status,'draft') invoice_status FROM extraction_drafts d JOIN finance_attachments a ON a.organization_id=d.organization_id AND a.project_id=d.project_id AND a.id=d.attachment_id LEFT JOIN invoices i ON i.organization_id=a.organization_id AND i.project_id=a.project_id AND i.id=a.invoice_id WHERE d.organization_id=%s AND d.project_id=%s AND d.attachment_id=%s AND a.deleted_at IS NULL ORDER BY d.version DESC LIMIT 1",(scope.organization_id,scope.project_id,file_id));row=await cursor.fetchone()
        return None if row is None else self._map(row)

    async def list(self, scope, page, page_size, review_status=None, source=None,
                   file_id=None, linked_invoice_id=None):
        clauses=["d.organization_id=%s","d.project_id=%s","a.deleted_at IS NULL"]
        args=[scope.organization_id,scope.project_id]
        if review_status is not None: clauses.append("d.review_status=%s");args.append(review_status)
        if source is not None: clauses.append("a.logical_type=%s");args.append("invoice_image" if source=="image" else "invoice_voice")
        if file_id is not None: clauses.append("d.attachment_id=%s");args.append(file_id)
        if linked_invoice_id is not None: clauses.append("a.invoice_id=%s");args.append(linked_invoice_id)
        where=" AND ".join(clauses)
        joined=" FROM extraction_drafts d JOIN finance_attachments a ON a.organization_id=d.organization_id AND a.project_id=d.project_id AND a.id=d.attachment_id LEFT JOIN invoices i ON i.organization_id=a.organization_id AND i.project_id=a.project_id AND i.id=a.invoice_id "
        columns="d.*,a.id attachment_id,a.invoice_id,a.logical_type,a.original_name_safe,a.stored_name,a.mime_type,a.size_bytes,a.sha256,a.storage_key,a.processing_status,a.uploaded_by,a.uploaded_at,COALESCE(i.status,'draft') invoice_status"
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT COUNT(*) total_count"+joined+"WHERE "+where,tuple(args));total=(await cursor.fetchone())["total_count"]
            await cursor.execute("SELECT "+columns+joined+"WHERE "+where+" ORDER BY d.created_at DESC,d.id DESC LIMIT %s OFFSET %s",(*args,page_size,(page-1)*page_size));rows=await cursor.fetchall()
        return [self._map(row) for row in rows],total

    async def reject(self, scope, draft, reason, audit_id, at):
        async with self.db.transaction():
            async with self.db.cursor(row_factory=dict_row) as cursor:
                await cursor.execute("SELECT id,version,review_status FROM extraction_drafts WHERE organization_id=%s AND project_id=%s AND attachment_id=%s ORDER BY version DESC LIMIT 1 FOR UPDATE",(scope.organization_id,scope.project_id,draft.file.file_id));latest=await cursor.fetchone()
                if latest is None or latest["id"]!=draft.draft_id or latest["version"]!=draft.version or latest["review_status"]!="awaitingReview":raise ValueError("stale extraction")
                await cursor.execute("UPDATE extraction_drafts SET review_status='rejected',version=version+1,updated_at=%s WHERE organization_id=%s AND project_id=%s AND id=%s AND version=%s AND review_status='awaitingReview'",(at,scope.organization_id,scope.project_id,draft.draft_id,draft.version))
                if cursor.rowcount!=1:raise ValueError("stale extraction")
                await cursor.execute("INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,reason,before_values,after_values,occurred_at) VALUES(%s,%s,%s,%s,'extraction.rejected','extraction_drafts',%s,%s,%s,%s,%s)",(audit_id,scope.organization_id,scope.project_id,scope.actor_user_id,draft.draft_id,reason,Jsonb({"reviewStatus":"awaitingReview","version":draft.version}),Jsonb({"reviewStatus":"rejected","version":draft.version+1}),at))
        return replace(draft,review_status="rejected",version=draft.version+1)

    async def create_next(self, scope, value):
        fields = [{"key": field.key, "extractedValue": field.extracted_value,
            "confirmedValue": field.confirmed_value, "confidence": field.confidence,
            "editedByUser": field.edited_by_user} for field in value.fields]
        async with self.db.transaction():
            async with self.db.cursor(row_factory=dict_row) as cursor:
                await cursor.execute("SELECT id FROM finance_attachments WHERE organization_id=%s AND project_id=%s AND id=%s FOR UPDATE", (scope.organization_id, scope.project_id, value.file.file_id))
                if await cursor.fetchone() is None: raise ValueError("file not found in scope")
                await cursor.execute("SELECT COALESCE(MAX(version),0)+1 next_version FROM extraction_drafts WHERE organization_id=%s AND project_id=%s AND attachment_id=%s", (scope.organization_id, scope.project_id, value.file.file_id))
                version = (await cursor.fetchone())["next_version"]
                await cursor.execute("INSERT INTO extraction_drafts(id,organization_id,project_id,attachment_id,version,review_status,provider_adapter,extracted_fields,confirmed_fields,financial_effect_irr,submitted_by,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,'awaitingReview',%s,%s,NULL,0,%s,%s,%s)", (value.draft_id, scope.organization_id, scope.project_id, value.file.file_id, version, value.provider_adapter, Jsonb(fields), value.submitted_by, value.created_at, value.created_at))
        return replace(value, version=version)

    async def confirm_with_invoice(self, scope, draft, confirmed_fields, invoice, duplicate_reason, extraction_audit_id, invoice_audit_id, at):
        fields = [{"key": field.key, "extractedValue": field.extracted_value,
            "confirmedValue": field.confirmed_value, "confidence": field.confidence,
            "editedByUser": field.edited_by_user} for field in confirmed_fields]
        try:
            async with self.db.transaction():
             async with self.db.cursor(row_factory=dict_row) as cursor:
                await cursor.execute("SELECT invoice_id FROM finance_attachments WHERE organization_id=%s AND project_id=%s AND id=%s FOR UPDATE", (scope.organization_id, scope.project_id, draft.file.file_id))
                attachment = await cursor.fetchone()
                if attachment is None or attachment["invoice_id"] is not None: raise ValueError("file is already linked")
                await cursor.execute("SELECT id,version,review_status FROM extraction_drafts WHERE organization_id=%s AND project_id=%s AND attachment_id=%s ORDER BY version DESC LIMIT 1 FOR UPDATE", (scope.organization_id, scope.project_id, draft.file.file_id))
                latest = await cursor.fetchone()
                if latest is None or latest["id"] != draft.draft_id or latest["version"] != draft.version or latest["review_status"] != "awaitingReview": raise ValueError("stale extraction")
                await cursor.execute("INSERT INTO invoices(id,organization_id,project_id,invoice_number,invoice_date,vendor_name,description,source,status,discount_irr,tax_irr,shipping_irr,other_costs_irr,final_amount_irr,financial_effect_sign,idempotency_key,version,submitted_by,confirmed_by,confirmed_at,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'confirmed',%s,%s,%s,%s,%s,1,%s,1,%s,%s,%s,%s,%s)", (invoice.id,scope.organization_id,scope.project_id,invoice.invoice_number,invoice.invoice_date,invoice.vendor_name,invoice.description,invoice.source,invoice.discount_irr,invoice.tax_irr,invoice.shipping_irr,invoice.other_costs_irr,invoice.final_amount_irr,invoice.idempotency_key,invoice.submitted_by,invoice.confirmed_by,invoice.confirmed_at,invoice.created_at,invoice.created_at))
                for line in invoice.lines:
                    await cursor.execute("INSERT INTO invoice_lines(id,organization_id,project_id,invoice_id,estimate_line_id,resource_id,quantity,unit,unit_price_snapshot_irr,raw_amount_irr,allocated_discount_irr,allocated_tax_irr,allocated_shipping_irr,allocated_other_costs_irr,final_line_amount_irr,description) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", (uuid4(),scope.organization_id,scope.project_id,invoice.id,line["estimate_line_id"],line["resource_id"],line["quantity"],line["unit"],line["unit_price_irr"],line["raw_amount_irr"],line["allocated_discount_irr"],line["allocated_tax_irr"],line["allocated_shipping_irr"],line["allocated_other_costs_irr"],line["final_line_amount_irr"],line["description"]))
                await cursor.execute("UPDATE extraction_drafts SET review_status='accepted',version=version+1,confirmed_fields=%s,confirmed_by=%s,confirmed_at=%s,updated_at=%s WHERE organization_id=%s AND project_id=%s AND id=%s AND version=%s AND review_status='awaitingReview'", (Jsonb(fields),scope.actor_user_id,at,at,scope.organization_id,scope.project_id,draft.draft_id,draft.version))
                if cursor.rowcount != 1: raise ValueError("stale extraction")
                await cursor.execute("UPDATE finance_attachments SET invoice_id=%s WHERE organization_id=%s AND project_id=%s AND id=%s AND invoice_id IS NULL", (invoice.id,scope.organization_id,scope.project_id,draft.file.file_id))
                if cursor.rowcount != 1: raise ValueError("file link conflict")
                await cursor.execute("INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,after_values,occurred_at) VALUES(%s,%s,%s,%s,'extraction.accepted','extraction_drafts',%s,%s,%s)", (extraction_audit_id,scope.organization_id,scope.project_id,scope.actor_user_id,draft.draft_id,Jsonb({"invoiceId":str(invoice.id),"reviewStatus":"accepted"}),at))
                await cursor.execute("INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,reason,after_values,occurred_at) VALUES(%s,%s,%s,%s,%s,'invoices',%s,%s,%s,%s)", (invoice_audit_id,scope.organization_id,scope.project_id,scope.actor_user_id,"invoice.duplicate_warning_overridden" if duplicate_reason else "invoice.confirmed",invoice.id,duplicate_reason,Jsonb({"source":invoice.source,"status":"confirmed","finalAmountIrr":str(invoice.final_amount_irr),"extractionDraftId":str(draft.draft_id)}),at))
        except errors.UniqueViolation as error: raise ValueError("competing extraction confirmation") from error
        return invoice

    async def get_linked_invoice_id(self, scope, attachment_id):
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT invoice_id FROM finance_attachments WHERE organization_id=%s AND project_id=%s AND id=%s", (scope.organization_id, scope.project_id, attachment_id))
            row = await cursor.fetchone()
        return None if row is None else row["invoice_id"]
