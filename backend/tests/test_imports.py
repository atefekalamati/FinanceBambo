import io,inspect,sys,unittest
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID
from openpyxl import Workbook
BACKEND_ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND_ROOT))
from app.finance.repositories.imports import PsycopgFinanceImportRepository
from app.finance.schemas.imports import ImportPreviewResponse
from app.finance.services.imports import FinanceImportService,parse_excel
def book(rows):
 w=Workbook();s=w.active
 for row in rows:s.append(row)
 out=io.BytesIO();w.save(out);return out.getvalue()
class ImportTests(unittest.TestCase):
 def test_price_excel_requires_explicit_currency_and_normalizes_toman(self):
  data=book([["resourceCode","unitPrice","currency","effectiveFrom","scope"],["M1",100,"TOMAN","2026-08-08","project"]])
  rows,errors=parse_excel(data,"prices","TOMAN");self.assertEqual([],errors);self.assertEqual("1000",rows[0]["unitPriceIrr"])
  _,errors=parse_excel(data,"prices","IRR");self.assertEqual("explicit_currency_mismatch",errors[0]["reason"])
 def test_preview_reports_columns_and_estimate_source(self):
  _,errors=parse_excel(book([["resourceCode"],["M1"]]),"estimate");self.assertTrue(errors)
  data=book([["resourceCode","activityExternalId","assignmentExternalId","originalQuantity","source"],["M1","A1","AS1","2.5","manual_entry"]])
  _,errors=parse_excel(data,"estimate");self.assertEqual("must_be_excel_import",errors[0]["reason"])
 def test_negative_malformed_values_and_missing_headers_are_row_specific(self):
  data=book([["resourceCode","activityExternalId","assignmentExternalId","originalQuantity","source"],["M1","A1","AS1","-1","excel_import"],["M1","A2","AS2","bad","excel_import"]])
  rows,errors=parse_excel(data,"estimate")
  self.assertEqual([2,3],[row["rowNumber"] for row in rows]);self.assertEqual({"negative_value","invalid_decimal"},{issue["reason"] for issue in errors})
  rows,errors=parse_excel(book([["resourceCode"],["M1"]]),"prices","IRR")
  self.assertEqual([],rows);self.assertIn("required_column",{issue["reason"] for issue in errors})

RESOURCE_ID=UUID("11111111-1111-4111-8111-111111111111")
SCOPE=SimpleNamespace(organization_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),project_id="project-a",actor_user_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"))

class PreviewRepo:
 def __init__(self):self.saved=None
 async def resolve_resources(self,scope,codes):
  self.resolve_scope=scope
  return [{"id":RESOURCE_ID,"code":"M1","title":"میلگرد","base_unit":"kg"}] if "M1" in codes else []
 async def save_preview(self,*args):self.saved=args
 async def commit(self,scope,preview_id,at):return 2

class ImportPreviewServiceTests(unittest.IsolatedAsyncioTestCase):
 def service(self,repo):
  return FinanceImportService(repo,id_factory=lambda:UUID("22222222-2222-4222-8222-222222222222"),clock=lambda:datetime(2026,8,10,tzinfo=timezone.utc))
 async def test_estimate_preview_returns_valid_and_invalid_rows_with_resolved_metadata(self):
  repo=PreviewRepo();service=self.service(repo)
  data=book([["resourceCode","activityExternalId","assignmentExternalId","originalQuantity","source"],["M1","A1","AS1","2.5000","excel_import"],["UNKNOWN","A2","AS2","-1","excel_import"]])
  result=await service.preview(SCOPE,"estimate",data)
  payload=ImportPreviewResponse(**result).model_dump(mode="json",by_alias=True)
  self.assertEqual((2,1,1,False),(payload["rowCount"],payload["validCount"],payload["invalidCount"],payload["canCommit"]))
  self.assertEqual((str(RESOURCE_ID),"میلگرد","kg","2.5000","valid"),(payload["rows"][0]["resourceId"],payload["rows"][0]["resourceTitle"],payload["rows"][0]["baseUnit"],payload["rows"][0]["originalQuantity"],payload["rows"][0]["status"]))
  self.assertIsNone(payload["rows"][0]["activityTitle"]);self.assertEqual("resource_not_found",payload["rows"][1]["errors"][-1]["reason"])
  self.assertIs(repo.resolve_scope,SCOPE);self.assertEqual(str(RESOURCE_ID),repo.saved[5][0]["resourceId"])
 async def test_price_preview_returns_irr_and_toman_normalization_and_invalid_details(self):
  repo=PreviewRepo();service=self.service(repo)
  data=book([["resourceCode","unitPrice","currency","effectiveFrom","scope"],["M1","125","TOMAN","2026-08-10","project"],["UNKNOWN","bad","TOMAN","bad-date","organization"]])
  result=await service.preview(SCOPE,"prices",data,"TOMAN");payload=ImportPreviewResponse(**result).model_dump(mode="json",by_alias=True)
  self.assertEqual(("125","1250","2026-08-10","valid"),(payload["rows"][0]["unitPrice"],payload["rows"][0]["normalizedUnitPriceIrr"],payload["rows"][0]["effectiveFrom"],payload["rows"][0]["status"]))
  self.assertEqual({"invalid_decimal","invalid_date","resource_not_found"},{issue["reason"] for issue in payload["rows"][1]["errors"]})
 async def test_commit_accepts_only_server_preview_identifier(self):
  repo=PreviewRepo();service=self.service(repo);preview_id=UUID("33333333-3333-4333-8333-333333333333")
  result=await service.commit(SCOPE,preview_id);self.assertEqual(2,result["committedCount"])

class ImportRepositoryContractTests(unittest.TestCase):
 def test_resource_resolution_and_commit_are_dual_scoped_atomic_and_server_controlled(self):
  source=inspect.getsource(PsycopgFinanceImportRepository)
  self.assertIn("organization_id=%s AND project_id=%s",source);self.assertIn("deleted_at IS NULL",source)
  self.assertIn("async with self.db.transaction()",source);self.assertIn('row["resourceId"]',source)
  self.assertNotIn('row["organizationId"]',source);self.assertNotIn('row["projectId"]',source)
 def test_commit_maps_estimate_and_price_fields_without_rewriting_price_history(self):
  source=inspect.getsource(PsycopgFinanceImportRepository.commit)
  for value in ("activity_external_id","assignment_external_id","original_quantity","'excel_import'","unit_price_irr","effective_from"):
   self.assertIn(value,source)
  self.assertIn("INSERT INTO price_versions",source);self.assertNotIn("UPDATE price_versions",source)
