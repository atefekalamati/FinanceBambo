import hashlib,io,inspect,sys,unittest
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
  rows,errors=parse_excel(data,"prices");self.assertEqual([],errors);self.assertEqual("1000",rows[0]["unitPriceIrr"])
 def test_row_currency_alone_drives_normalization(self):
  # Normalization reads each row's mandatory currency column, so the batch-level
  # currencyUnit cannot silently reinterpret a Toman file as Rial.
  toman=book([["resourceCode","unitPrice","currency","effectiveFrom","scope"],["M1",100,"TOMAN","2026-08-08","project"]])
  rial=book([["resourceCode","unitPrice","currency","effectiveFrom","scope"],["M1",100,"IRR","2026-08-08","project"]])
  self.assertEqual("1000",parse_excel(toman,"prices")[0][0]["unitPriceIrr"])
  self.assertEqual("100",parse_excel(rial,"prices")[0][0]["unitPriceIrr"])
 def test_row_without_a_valid_currency_is_rejected(self):
  data=book([["resourceCode","unitPrice","currency","effectiveFrom","scope"],["M1",100,None,"2026-08-08","project"]])
  _,errors=parse_excel(data,"prices")
  self.assertIn({"row":2,"field":"currency","reason":"invalid_choice"},errors)
 def test_preview_reports_columns_and_estimate_source(self):
  _,errors=parse_excel(book([["resourceCode"],["M1"]]),"estimate");self.assertTrue(errors)
  data=book([["resourceCode","activityExternalId","assignmentExternalId","originalQuantity","source"],["M1","A1","AS1","2.5","manual_entry"]])
  _,errors=parse_excel(data,"estimate");self.assertEqual("must_be_excel_import",errors[0]["reason"])
 def test_negative_malformed_values_and_missing_headers_are_row_specific(self):
  data=book([["resourceCode","activityExternalId","assignmentExternalId","originalQuantity","source"],["M1","A1","AS1","-1","excel_import"],["M1","A2","AS2","bad","excel_import"]])
  rows,errors=parse_excel(data,"estimate")
  self.assertEqual([2,3],[row["rowNumber"] for row in rows]);self.assertEqual({"negative_value","invalid_decimal"},{issue["reason"] for issue in errors})
  rows,errors=parse_excel(book([["resourceCode"],["M1"]]),"prices")
  self.assertEqual([],rows);self.assertIn("required_column",{issue["reason"] for issue in errors})
 def test_wrong_template_and_unknown_columns_are_rejected(self):
  rows,errors=parse_excel(book([["resourceCode","unitPrice","currency","effectiveFrom","scope","title"],["M1","1","IRR","2026-08-10","project","x"]]),"prices")
  self.assertEqual([],rows);self.assertIn({"row":1,"field":"title","reason":"unexpected_column"},errors)
  rows,errors=parse_excel(book([["resourceCode","unitPrice","currency","effectiveFrom","scope"],["M1","1","IRR","2026-08-10","project"]]),"estimate")
  self.assertEqual([],rows);self.assertIn("required_column",{issue["reason"] for issue in errors})

RESOURCE_ID=UUID("11111111-1111-4111-8111-111111111111")
SCOPE=SimpleNamespace(organization_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),project_id="project-a",actor_user_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"))

class PreviewRepo:
 def __init__(self,duplicate=None):self.saved=None;self.duplicate=duplicate;self.hash_lookup=None
 async def resolve_resources(self,scope,codes):
  self.resolve_scope=scope
  resources=[]
  if "M1" in codes:resources.append({"id":RESOURCE_ID,"code":"M1","title":"میلگرد","base_unit":"kg","resource_type":"material"})
  if "G1" in codes:resources.append({"id":UUID("44444444-4444-4444-8444-444444444444"),"code":"G1","title":"هزینه مجوز","base_unit":None,"resource_type":"general_cost"})
  return resources
 async def committed_with_hash(self,scope,kind,file_hash,exclude_id=None):
  self.hash_lookup=(scope,kind,file_hash)
  return self.duplicate
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
  result=await service.preview(SCOPE,"prices",data);payload=ImportPreviewResponse(**result).model_dump(mode="json",by_alias=True)
  self.assertEqual(("125","1250","2026-08-10","valid"),(payload["rows"][0]["unitPrice"],payload["rows"][0]["normalizedUnitPriceIrr"],payload["rows"][0]["effectiveFrom"],payload["rows"][0]["status"]))
  self.assertEqual({"invalid_decimal","invalid_date","resource_not_found"},{issue["reason"] for issue in payload["rows"][1]["errors"]})
 async def test_general_cost_preview_persists_integer_irr_in_money_field(self):
  repo=PreviewRepo();service=self.service(repo)
  data=book([["resourceCode","activityExternalId","assignmentExternalId","originalQuantity","source"],["G1","A1","AS1","2500000","excel_import"]])
  result=await service.preview(SCOPE,"estimate",data)
  self.assertTrue(result["canCommit"]);self.assertEqual("2500000",repo.saved[5][0]["originalUnitPriceIrr"])
  invalid=book([["resourceCode","activityExternalId","assignmentExternalId","originalQuantity","source"],["G1","A1","AS1","2.5","excel_import"]])
  result=await service.preview(SCOPE,"estimate",invalid);self.assertFalse(result["canCommit"]);self.assertEqual("fractional_irr",result["rows"][0]["errors"][-1]["reason"])
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


PREVIEW_ID = UUID("22222222-2222-4222-8222-222222222222")
NOW = datetime(2026, 8, 10, tzinfo=timezone.utc)
PRICE_SHEET = [["resourceCode","unitPrice","currency","effectiveFrom","scope"],
               ["M1","302000","TOMAN","2026-08-22","project"]]


class DuplicateImportFileTests(unittest.IsolatedAsyncioTestCase):
    """The same bytes must not be committed twice into one project."""

    def service(self, repo):
        return FinanceImportService(repo, id_factory=lambda: PREVIEW_ID, clock=lambda: NOW)

    async def test_a_first_upload_previews_and_stays_committable(self):
        repo = PreviewRepo()
        result = await self.service(repo).preview(SCOPE, "prices", book(PRICE_SHEET))
        self.assertEqual((False, None, True),
                         (result["duplicateFile"], result["duplicateOfImportId"], result["canCommit"]))

    async def test_the_same_bytes_after_a_commit_are_refused_at_preview(self):
        earlier = {"id": UUID(int=7), "committed_at": NOW}
        repo = PreviewRepo(duplicate=earlier)
        result = await self.service(repo).preview(SCOPE, "prices", book(PRICE_SHEET))
        self.assertTrue(result["duplicateFile"])
        self.assertEqual(UUID(int=7), result["duplicateOfImportId"])
        self.assertEqual(NOW, result["duplicateCommittedAt"])
        # canCommit is the decision the UI acts on; the rest only explains it.
        self.assertFalse(result["canCommit"])
        self.assertIn({"row": 0, "field": "file", "reason": "duplicate_import_file"}, result["errors"])

    async def test_identity_is_the_content_so_a_renamed_copy_is_the_same_import(self):
        # The service never sees a filename: it hashes the bytes it was handed.
        content = book(PRICE_SHEET)
        repo = PreviewRepo()
        await self.service(repo).preview(SCOPE, "prices", content)
        first = repo.hash_lookup[2]
        await self.service(PreviewRepo()).preview(SCOPE, "prices", content)
        self.assertEqual(64, len(first))
        self.assertEqual(first, hashlib.sha256(content).hexdigest())

    async def test_changing_one_price_makes_it_a_different_import(self):
        repo = PreviewRepo()
        await self.service(repo).preview(SCOPE, "prices", book(PRICE_SHEET))
        original = repo.hash_lookup[2]
        changed = PreviewRepo()
        await self.service(changed).preview(SCOPE, "prices", book(
            [PRICE_SHEET[0], ["M1", "303000", "TOMAN", "2026-08-22", "project"]]))
        self.assertNotEqual(original, changed.hash_lookup[2])

    async def test_the_lookup_is_scoped_to_the_tenant_and_the_import_kind(self):
        repo = PreviewRepo()
        await self.service(repo).preview(SCOPE, "prices", book(PRICE_SHEET))
        scope, kind, _digest = repo.hash_lookup
        # The same sheet may belong to another project, and an estimate sheet is not a
        # price sheet even byte for byte.
        self.assertIs(SCOPE, scope)
        self.assertEqual("prices", kind)

    async def test_the_hash_is_computed_from_the_bytes_not_taken_from_the_caller(self):
        source = inspect.getsource(FinanceImportService.preview)
        self.assertIn("hashlib.sha256(content).hexdigest()", source)
        # Nothing client-supplied may stand in for the digest.
        self.assertNotIn("file_sha256=", source)


class DuplicateImportCommitGuardTests(unittest.TestCase):
    """The preview check cannot be the only one: two previews can race to commit."""

    def test_commit_takes_a_lock_on_the_file_identity_and_looks_again(self):
        source = inspect.getsource(PsycopgFinanceImportRepository.commit)
        self.assertIn("pg_advisory_xact_lock", source)
        # The re-read has to happen after the lock, inside the same transaction.
        lock_at = source.index("pg_advisory_xact_lock")
        recheck_at = source.index("status='committed'")
        self.assertLess(lock_at, recheck_at)
        self.assertIn("DuplicateImportFile", source)
        self.assertIn("id<>%s", source)

    def test_the_duplicate_lookup_is_bound_and_scoped(self):
        source = inspect.getsource(PsycopgFinanceImportRepository.committed_with_hash)
        for fragment in ("organization_id=%s", "project_id=%s", "import_kind=%s",
                         "file_sha256=%s", "status='committed'"):
            self.assertIn(fragment, source)

    def test_the_refusal_is_a_conflict_with_its_own_code(self):
        from app.finance.domain.imports import DuplicateImportFile
        # Not STALE_VERSION: refreshing and retrying can never make this succeed.
        self.assertEqual((409, "DUPLICATE_IMPORT_FILE"),
                         (DuplicateImportFile.status, DuplicateImportFile.code))

