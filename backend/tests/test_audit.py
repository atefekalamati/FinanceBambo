import inspect
import sys
import unittest
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

BACKEND_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND_ROOT))

from app.finance.repositories.audit import PsycopgFinanceAuditRepository
from app.finance.schemas.audit import AuditEventResponse
from app.finance.services.audit import FinanceAuditService


class Repository:
    def __init__(self,row):self.row=row;self.scope=None;self.limit=None;self.offset=None
    async def list(self,scope,limit=50,offset=0):
        self.scope=scope;self.limit=limit;self.offset=offset;return [self.row]


class AuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_lists_only_repository_scoped_immutable_events(self):
        row={"id":UUID(int=1),"organization_id":UUID(int=2),"project_id":"p1","actor_user_id":UUID(int=3),
             "action":"report_snapshot.issued","entity_type":"report_snapshots","entity_id":UUID(int=4),
             "reason":None,"before_values":None,"after_values":{"immutable":True},"occurred_at":datetime(2026,8,9,tzinfo=timezone.utc)}
        repository=Repository(row);scope=SimpleNamespace(organization_id=UUID(int=2),project_id="p1")
        result=await FinanceAuditService(repository).list(scope,page=3,page_size=25)
        self.assertIs(scope,repository.scope)
        self.assertEqual((25,50),(repository.limit,repository.offset))
        self.assertEqual("report_snapshot.issued",AuditEventResponse(**result[0]).action)

    def test_postgres_query_is_dual_scoped_and_deterministic(self):
        source=inspect.getsource(PsycopgFinanceAuditRepository.list)
        self.assertIn("organization_id=%s AND project_id=%s",source)
        self.assertIn("ORDER BY occurred_at DESC,id DESC",source)
        self.assertIn("LIMIT %s OFFSET %s",source)


if __name__=="__main__":unittest.main()
