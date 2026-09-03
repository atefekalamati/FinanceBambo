import inspect
import sys
import unittest
from datetime import date,datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

BACKEND_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND_ROOT))

from app.finance.repositories.audit import PsycopgFinanceAuditRepository
from app.finance.schemas.audit import AuditEventResponse
from app.finance.services.audit import FinanceAuditService


class Repository:
    def __init__(self,row):self.row=row;self.scope=None;self.limit=None;self.offset=None;self.filters=None
    async def list(self,scope,limit=50,offset=0,**filters):
        self.scope=scope;self.limit=limit;self.offset=offset;self.filters=filters;return [self.row],7


class AuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_lists_only_repository_scoped_immutable_events(self):
        row={"id":UUID(int=1),"organization_id":UUID(int=2),"project_id":"p1","actor_user_id":UUID(int=3),
             "action":"report_snapshot.issued","entity_type":"report_snapshots","entity_id":UUID(int=4),
             "reason":None,"before_values":None,"after_values":{"immutable":True},"occurred_at":datetime(2026,8,9,tzinfo=timezone.utc)}
        repository=Repository(row);scope=SimpleNamespace(organization_id=UUID(int=2),project_id="p1")
        result=await FinanceAuditService(repository).list(scope,page=3,page_size=25)
        self.assertIs(scope,repository.scope)
        self.assertEqual((25,50),(repository.limit,repository.offset))
        self.assertEqual("report_snapshot.issued",AuditEventResponse(**result["items"][0]).action)
        # The envelope reports the full match count, not just what this page holds.
        self.assertEqual((3,25,7,1),(result["page"],result["page_size"],result["total_items"],result["total_pages"]))

    async def test_filters_are_pushed_to_the_database_not_applied_to_one_page(self):
        repository=Repository({});scope=SimpleNamespace(organization_id=UUID(int=2),project_id="p1")
        await FinanceAuditService(repository).list(scope,page=1,page_size=50,action="invoice.confirmed",
            entity_type="invoices",occurred_from=date(2026,4,1),occurred_to=date(2026,5,1),query="اصلاح")
        self.assertEqual({"action":"invoice.confirmed","entity_type":"invoices",
            "occurred_from":date(2026,4,1),"occurred_to":date(2026,5,1),"query":"اصلاح"},repository.filters)

    async def test_total_pages_is_zero_when_nothing_matches(self):
        class Empty(Repository):
            async def list(self,scope,limit=50,offset=0,**filters):return [],0
        result=await FinanceAuditService(Empty({})).list(SimpleNamespace(organization_id=UUID(int=2),project_id="p1"))
        self.assertEqual(([],0,0),(result["items"],result["total_items"],result["total_pages"]))

    def test_postgres_query_is_dual_scoped_and_deterministic(self):
        source=inspect.getsource(PsycopgFinanceAuditRepository.list)+inspect.getsource(PsycopgFinanceAuditRepository._filters)
        self.assertIn('"organization_id=%s","project_id=%s"',source)
        self.assertIn("ORDER BY occurred_at DESC,id DESC",source)
        self.assertIn("LIMIT %s OFFSET %s",source)
        # Filter values are bound, never interpolated: only the clause skeleton is formatted in.
        self.assertNotIn('f"%s"',source)
        for fragment in ("action=%s","entity_type=%s"):
            self.assertIn(fragment,source)
        # Date bounds are asserted behaviourally in test_new_repository_sql.py, which pins
        # the whole-UTC-day semantics rather than a bare comparison.


if __name__=="__main__":unittest.main()
