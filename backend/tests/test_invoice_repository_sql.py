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

    def test_link_checks_refuse_a_soft_deleted_resource_or_estimate_line(self):
        """A deleted record must not still be a valid target for a new invoice line.

        `finance_resources` and `estimate_lines` both soft-delete, and every read that
        shows them filters `deleted_at`. These two checks did not, so a line could be
        written against a record the rest of the module has stopped returning -- the
        invoice would list a resource the items page no longer has.
        """
        for method in (PsycopgInvoiceRepository.are_general_costs,
                       PsycopgInvoiceRepository.valid_line_links):
            source = inspect.getsource(method)
            statements = [line for line in source.splitlines() if "SELECT" in line]
            self.assertTrue(statements, "no statement found in %s" % method.__name__)
            for statement in statements:
                self.assertIn("deleted_at IS NULL", statement,
                              "%s reads a soft-deleted record: %s"
                              % (method.__name__, statement.strip()[:90]))

    def test_list_filters_and_paginates_in_sql_without_n_plus_one(self):
        source=inspect.getsource(PsycopgInvoiceRepository.list)
        for fragment in ("COUNT(*)","ILIKE %s","status=%s","source=%s","ORDER BY invoice_date DESC,created_at DESC,id DESC","LIMIT %s OFFSET %s","invoice_id=ANY(%s)"):
            self.assertIn(fragment,source)
        self.assertNotIn("await self._map",source)


if __name__=="__main__":unittest.main()
