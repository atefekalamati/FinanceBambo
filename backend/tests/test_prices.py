import sys, unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID
BACKEND_ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(BACKEND_ROOT))
from types import SimpleNamespace
from app.finance.domain.prices import PricePeriodOverlap, PriceVersion
from app.finance.schemas.prices import PriceCreate
from app.finance.services.prices import FinancePriceService
from app.finance.security.guards import FinanceScope

ORG=UUID("11111111-1111-4111-8111-111111111111"); ACTOR=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1"); RES=UUID("22222222-2222-4222-8222-222222222222")

class Repo:
 def __init__(self): self.rows=[]
 async def append(self,scope,value,audit_id): self.rows.append(value); return value
 async def history(self,scope,resource_id=None): return [x for x in self.rows if resource_id is None or x.resource_id==resource_id]
 async def current(self,scope,resource_id,as_of):
  valid=[x for x in self.rows if x.resource_id==resource_id and x.effective_from<=as_of]
  if not valid:return None
  return max(valid,key=lambda x:(x.scope_kind=="project",x.effective_from,x.version,x.created_at,x.id.hex))

class PriceTests(unittest.IsolatedAsyncioTestCase):
 async def test_strict_append_and_project_override(self):
  ids=iter([UUID(int=i) for i in range(1,7)]); repo=Repo(); service=FinancePriceService(repo,lambda:next(ids),lambda:datetime(2026,8,8,tzinfo=timezone.utc)); scope=FinanceScope(ORG,"p1",ACTOR)
  first=await service.create(scope,RES,PriceCreate(scopeKind="organization",unitPriceIrr="100",effectiveFrom="2026-01-01",reason="base"))
  second=await service.create(scope,RES,PriceCreate(scopeKind="project",unitPriceIrr="120",effectiveFrom="2026-01-01",reason="override"))
  self.assertEqual(2,len(repo.rows)); self.assertEqual(Decimal("100"),repo.rows[0].unit_price_irr)
  self.assertEqual(second,await service.current(scope,RES,date(2026,2,1)))
  self.assertEqual((1,2),(first.version,second.version))
 def test_fractional_irr_and_blank_reason_rejected(self):
  with self.assertRaises(ValueError): PriceCreate(scopeKind="project",unitPriceIrr="100.5",effectiveFrom="2026-01-01",reason="x")
  with self.assertRaises(ValueError): PriceCreate(scopeKind="project",unitPriceIrr="100",effectiveFrom="2026-01-01",reason=" ")


class PricePeriodOverlapTests(unittest.IsolatedAsyncioTestCase):
    """PRD lists PRICE_PERIOD_OVERLAP as a 409; without it the older same-day price
    becomes unreachable data instead of a rejected write."""

    class Repo:
        def __init__(self,history):self.history_rows=history;self.appended=None
        async def history(self,scope,resource_id=None):return self.history_rows
        async def append(self,scope,value,audit_id):self.appended=value;return value

    def _existing(self,scope_kind,effective_from):
        return PriceVersion(UUID(int=1),UUID(int=2),"p1",UUID(int=3),scope_kind,1,
            Decimal("100"),effective_from,"r",UUID(int=4),datetime(2026,8,1,tzinfo=timezone.utc))

    def _command(self,scope_kind,effective_from):
        return PriceCreate(scopeKind=scope_kind,unitPriceIrr="200",effectiveFrom=effective_from.isoformat(),reason="r")

    def _scope(self):
        return SimpleNamespace(organization_id=UUID(int=2),project_id="p1",actor_user_id=UUID(int=4))

    async def test_same_scope_same_day_is_rejected(self):
        repo=self.Repo([self._existing("project",date(2026,8,10))])
        service=FinancePriceService(repo,id_factory=lambda:UUID(int=9))
        with self.assertRaises(PricePeriodOverlap):
            await service.create(self._scope(),UUID(int=3),self._command("project",date(2026,8,10)))
        self.assertIsNone(repo.appended)

    async def test_a_different_scope_or_a_different_day_still_appends(self):
        for scope_kind,day in (("organization",date(2026,8,10)),("project",date(2026,8,11))):
            with self.subTest(scope=scope_kind,day=day):
                repo=self.Repo([self._existing("project",date(2026,8,10))])
                service=FinancePriceService(repo,id_factory=lambda:UUID(int=9))
                await service.create(self._scope(),UUID(int=3),self._command(scope_kind,day))
                self.assertEqual(2,repo.appended.version)

