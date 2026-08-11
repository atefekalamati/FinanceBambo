import sys, unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID
BACKEND_ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND_ROOT))
from app.finance.schemas.conversions import ConversionCreate,ConversionPatch
from app.finance.services.conversions import UnitConversionService
from app.finance.domain.resources import UnitMismatch, UnitNotFound
from app.finance.security.guards import FinanceScope

ORG=UUID("11111111-1111-4111-8111-111111111111");ACTOR=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
class Repo:
 def __init__(self):self.rows=[]
 async def list(self,scope):return self.rows
 async def get(self,scope,cid):return next((x for x in self.rows if x.id==cid),None)
 async def append(self,scope,value,audit_id,before=None):self.rows.append(value);return value

class ConversionTests(unittest.IsolatedAsyncioTestCase):
 async def test_patch_appends_version_and_preserves_original(self):
  ids=iter(UUID(int=i) for i in range(1,9));repo=Repo();svc=UnitConversionService(repo,lambda:next(ids),lambda:datetime(2026,8,8,tzinfo=timezone.utc));scope=FinanceScope(ORG,"p1",ACTOR)
  first=await svc.create(scope,ConversionCreate(scopeKind="organization",sourceUnit="ton",targetUnit="kg",dimension="mass",factor="1000",effectiveFrom="2026-01-01",reason="base"))
  second=await svc.revise(scope,first.id,ConversionPatch(factor="1000.000001",effectiveFrom="2026-02-01",reason="correction"))
  self.assertEqual(2,len(repo.rows));self.assertEqual(Decimal("1000"),repo.rows[0].factor)
  self.assertEqual((1,2),(first.version,second.version));self.assertNotEqual(first.id,second.id)
 def test_factor_units_and_reason_are_validated(self):
  good=dict(scopeKind="project",sourceUnit="day",targetUnit="hour",dimension="equipment_time",effectiveFrom="2026-01-01",reason="x")
  for factor in ("0","-1","1.0000001"):
   with self.assertRaises(ValueError):ConversionCreate(**good,factor=factor)
  with self.assertRaises(ValueError):ConversionCreate(**{**good,"factor":"24","targetUnit":"day"})
  with self.assertRaises(ValueError):ConversionCreate(**{**good,"factor":"24","reason":" "})
 async def test_dimension_compatibility_is_validated_against_unit_registry(self):
  ids=iter(UUID(int=i) for i in range(1,9));repo=Repo();svc=UnitConversionService(repo,lambda:next(ids),lambda:datetime(2026,8,8,tzinfo=timezone.utc));scope=FinanceScope(ORG,"p1",ACTOR)
  await svc.create(scope,ConversionCreate(scopeKind="organization",sourceUnit="ton",targetUnit="kg",dimension="mass",factor="1000",effectiveFrom="2026-01-01",reason="base"))
  await svc.create(scope,ConversionCreate(scopeKind="project",sourceUnit="day",targetUnit="hour",dimension="equipment_time",factor="8",effectiveFrom="2026-01-01",reason="equipment day"))
  with self.assertRaises(UnitMismatch):
   await svc.create(scope,ConversionCreate(scopeKind="organization",sourceUnit="kg",targetUnit="m2",dimension="mass",factor="1",effectiveFrom="2026-01-01",reason="bad"))
  with self.assertRaises(UnitNotFound):
   await svc.create(scope,ConversionCreate(scopeKind="organization",sourceUnit="parsec",targetUnit="kg",dimension="mass",factor="1",effectiveFrom="2026-01-01",reason="bad"))
