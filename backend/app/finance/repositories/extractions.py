from decimal import Decimal
from dataclasses import replace

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

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
            row["version"], row["review_status"], "draft", row["provider_adapter"], fields,
            row["submitted_by"], row["created_at"], Decimal(row["financial_effect_irr"]),
            row["confirmed_by"], row["confirmed_at"])

    async def get(self, scope, draft_id):
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT d.*,a.id attachment_id,a.invoice_id,a.logical_type,a.original_name_safe,a.stored_name,a.mime_type,a.size_bytes,a.sha256,a.storage_key,a.processing_status,a.uploaded_by,a.uploaded_at FROM extraction_drafts d JOIN finance_attachments a ON a.organization_id=d.organization_id AND a.project_id=d.project_id AND a.id=d.attachment_id WHERE d.organization_id=%s AND d.project_id=%s AND d.id=%s AND a.deleted_at IS NULL", (scope.organization_id, scope.project_id, draft_id))
            row = await cursor.fetchone()
        return None if row is None else self._map(row)

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
