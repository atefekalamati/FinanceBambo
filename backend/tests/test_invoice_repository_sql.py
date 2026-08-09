import inspect
import sys
import unittest
from pathlib import Path

BACKEND_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BACKEND_ROOT))

from app.finance.repositories.invoices import PsycopgInvoiceRepository


class InvoiceRepositorySqlTests(unittest.TestCase):
    def test_general_cost_queries_use_the_migration_column_name(self):
        for method in (PsycopgInvoiceRepository.are_general_costs,PsycopgInvoiceRepository.valid_line_links):
            source=inspect.getsource(method)
            self.assertIn("resource_type='general_cost'",source)
            self.assertNotIn(" type='general_cost'",source)


if __name__=="__main__":unittest.main()
