from psycopg.rows import dict_row


class PsycopgFinanceAuditRepository:
    def __init__(self,db):self.db=db

    @staticmethod
    def _filters(scope,action,entity_type,occurred_from,occurred_to,query):
        """Build the shared WHERE clause so the count and the page always agree."""
        clauses=["organization_id=%s","project_id=%s"];values=[scope.organization_id,scope.project_id]
        if action:clauses.append("action=%s");values.append(action)
        if entity_type:clauses.append("entity_type=%s");values.append(entity_type)
        if occurred_from:clauses.append("occurred_at>=%s");values.append(occurred_from)
        if occurred_to:clauses.append("occurred_at<%s");values.append(occurred_to)
        if query:
            clauses.append("(actor_user_id::text ILIKE %s OR entity_id::text ILIKE %s OR COALESCE(reason,'') ILIKE %s)")
            values.extend([f"%{query}%"]*3)
        return " AND ".join(clauses),values

    async def list(self,scope,limit=50,offset=0,action=None,entity_type=None,occurred_from=None,occurred_to=None,query=None):
        where,values=self._filters(scope,action,entity_type,occurred_from,occurred_to,query)
        async with self.db.cursor(row_factory=dict_row) as cursor:
            await cursor.execute(f"SELECT COUNT(*) AS total FROM finance_audit_events WHERE {where}",tuple(values))
            total=(await cursor.fetchone())["total"]
            await cursor.execute(
                "SELECT id,organization_id,project_id,actor_user_id,action,entity_type,entity_id,reason,"
                f"before_values,after_values,occurred_at FROM finance_audit_events WHERE {where} "
                "ORDER BY occurred_at DESC,id DESC LIMIT %s OFFSET %s",
                tuple(values+[limit,offset]))
            return await cursor.fetchall(),total
