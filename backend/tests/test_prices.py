import sys, unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID
BACKEND_ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(BACKEND_ROOT))
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
