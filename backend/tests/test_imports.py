import io,sys,unittest
from pathlib import Path
from openpyxl import Workbook
BACKEND_ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BACKEND_ROOT))
from app.finance.services.imports import parse_excel
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
