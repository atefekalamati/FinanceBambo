from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..domain.attachments import FinanceAttachment


class PsycopgAttachmentRepository:
    def __init__(self, db): self.db = db

    @staticmethod
    def _map(row):
        return FinanceAttachment(row["id"], row["organization_id"], row["project_id"], row["logical_type"],
            row["original_name_safe"], row["stored_name"], row["mime_type"], row["size_bytes"], row["sha256"],
            row["uploaded_by"], row["uploaded_at"], row["processing_status"], row["storage_key"], row["invoice_id"])

    async def get_by_hash(self, scope, digest):
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT * FROM finance_attachments WHERE organization_id=%s AND project_id=%s AND sha256=%s AND deleted_at IS NULL", (scope.organization_id, scope.project_id, digest))
            row = await cursor.fetchone()
        return None if row is None else self._map(row)

    async def get(self, scope, file_id):
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT * FROM finance_attachments WHERE organization_id=%s AND project_id=%s AND id=%s AND deleted_at IS NULL", (scope.organization_id, scope.project_id, file_id))
            row = await cursor.fetchone()
        return None if row is None else self._map(row)

    async def list(self, scope, page, page_size, logical_type=None,
                   file_category=None, processing_status=None, uploader_id=None):
        clauses = ["organization_id=%s", "project_id=%s", "deleted_at IS NULL"]
        args = [scope.organization_id, scope.project_id]
        if logical_type is not None:
            clauses.append("logical_type=%s"); args.append(logical_type)
        if file_category is not None:
            clauses.append("logical_type=%s"); args.append(
                "invoice_image" if file_category == "image" else "invoice_voice")
        if processing_status is not None:
            clauses.append("processing_status=%s"); args.append(processing_status)
        if uploader_id is not None:
            clauses.append("uploaded_by=%s"); args.append(uploader_id)
        where = " AND ".join(clauses)
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(f"SELECT COUNT(*) total_count FROM finance_attachments WHERE {where}", tuple(args))
            total_count = (await cursor.fetchone())["total_count"]
            await cursor.execute(
                f"SELECT * FROM finance_attachments WHERE {where} ORDER BY uploaded_at DESC,id DESC LIMIT %s OFFSET %s",
                (*args, page_size, (page - 1) * page_size),
            )
            rows = await cursor.fetchall()
        return [self._map(row) for row in rows], total_count

    async def create(self, scope, value):
        async with self.db.cursor() as cursor:
            await cursor.execute("INSERT INTO finance_attachments(id,organization_id,project_id,invoice_id,logical_type,original_name_safe,stored_name,mime_type,size_bytes,sha256,storage_key,processing_status,uploaded_by,uploaded_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'uploaded',%s,%s)", (value.file_id, scope.organization_id, scope.project_id, value.invoice_id, value.logical_type, value.original_name_safe, value.stored_name, value.mime_type, value.size_bytes, value.sha256, value.storage_key, value.uploaded_by, value.uploaded_at))
        return value

    async def transition(self, scope, value, target):
        async with self.db.cursor() as cursor:
            await cursor.execute("UPDATE finance_attachments SET processing_status=%s WHERE organization_id=%s AND project_id=%s AND id=%s AND processing_status=%s", (target, scope.organization_id, scope.project_id, value.file_id, value.processing_status))
            if cursor.rowcount != 1: raise ValueError("stale file processing status")
        return FinanceAttachment(value.file_id, value.organization_id, value.project_id, value.logical_type,
            value.original_name_safe, value.stored_name, value.mime_type, value.size_bytes, value.sha256,
            value.uploaded_by, value.uploaded_at, target, value.storage_key, value.invoice_id)

    async def record_access(self, scope, file_id, audit_id, occurred_at):
        async with self.db.cursor() as cursor:
            await cursor.execute("INSERT INTO finance_audit_events(id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,after_values,occurred_at) VALUES(%s,%s,%s,%s,'attachment.accessed','finance_attachments',%s,%s,%s)", (audit_id, scope.organization_id, scope.project_id, scope.actor_user_id, file_id, Jsonb({"fileId": str(file_id)}), occurred_at))
