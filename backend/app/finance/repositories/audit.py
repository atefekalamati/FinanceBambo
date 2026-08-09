from psycopg.rows import dict_row


class PsycopgFinanceAuditRepository:
    def __init__(self,db):self.db=db

    async def list(self,scope):
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute("SELECT id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,reason,before_values,after_values,occurred_at FROM finance_audit_events WHERE organization_id=%s AND project_id=%s ORDER BY occurred_at DESC,id DESC",(scope.organization_id,scope.project_id))
            return await cursor.fetchall()
