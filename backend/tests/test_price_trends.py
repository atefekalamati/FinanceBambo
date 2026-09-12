import inspect
import sys
import unittest
from datetime import date,datetime,timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from app.finance.domain.prices import PriceVersion,latest_price_trend
from app.finance.repositories.prices import PsycopgFinancePriceRepository
from app.finance.schemas.prices import CurrentPriceTrendResponse,PriceResponse
from app.finance.services.prices import FinancePriceService

ORG=UUID("11111111-1111-4111-8111-111111111111")
RESOURCE=UUID("22222222-2222-4222-8222-222222222222")
ACTOR=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
AT=datetime(2026,8,1,tzinfo=timezone.utc)


def version(number,price,day,scope="organization",resource=RESOURCE):
    return PriceVersion(UUID(int=number),ORG,"p1",resource,scope,number,Decimal(price),date.fromisoformat(day),"reason",ACTOR,AT)


class Repository:
    def __init__(self,rows):self.rows=rows;self.calls=[]
    async def trend_history(self,scope,as_of):self.calls.append((scope,as_of));return self.rows


class PriceTrendDomainTests(unittest.TestCase):
    def test_without_previous_version_returns_none(self):
        current,previous,percent,direction,points=latest_price_trend([version(1,"100","2026-01-01")])
        self.assertEqual((Decimal("100"),None,None,"none",1),(current.unit_price_irr,previous,percent,direction,len(points)))

    def test_up_down_and_flat_use_decimal_percent(self):
        cases=(("100","125","up",Decimal("25.000000")),("200","150","down",Decimal("-25.000000")),("100","100","flat",Decimal("0.000000")))
        for before,after,direction,percent in cases:
            with self.subTest(direction=direction):
                result=latest_price_trend([version(1,before,"2026-01-01"),version(2,after,"2026-02-01")])
                self.assertEqual(direction,result[3]);self.assertEqual(percent,result[2]);self.assertIsInstance(result[2],Decimal)

    def test_only_two_correct_latest_versions_are_compared_and_points_are_chronological(self):
        rows=[version(3,"130","2026-03-01"),version(1,"90","2026-01-01"),version(2,"100","2026-02-01")]
        current,previous,percent,direction,points=latest_price_trend(rows)
        self.assertEqual((Decimal("130"),Decimal("100"),Decimal("30.000000"),"up"),(current.unit_price_irr,previous.unit_price_irr,percent,direction))
        self.assertEqual([date(2026,1,1),date(2026,2,1),date(2026,3,1)],[point.effective_from for point in points])


class PriceTrendServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_project_override_wins_and_uses_only_project_scope_history(self):
        rows={RESOURCE:[version(1,"80","2026-01-01","organization"),version(2,"100","2026-02-01","organization"),version(3,"110","2026-01-15","project"),version(4,"121","2026-03-01","project")]}
        repository=Repository(rows);scope=SimpleNamespace(organization_id=ORG,project_id="p1")
        result=(await FinancePriceService(repository).trends(scope,date(2026,4,1)))[0]
        self.assertEqual((Decimal("121"),Decimal("110"),Decimal("10.000000"),"up","project"),(result["current_price_irr"],result["previous_price_irr"],result["latest_change_percent"],result["trend_direction"],result["scope_kind"]))
        self.assertEqual((Decimal("100"),Decimal("121"),date(2026,3,1)),(result["organization_price_irr"],result["project_price_irr"],result["current_effective_from"]))
        self.assertEqual([Decimal("110"),Decimal("121")],[point["unit_price_irr"] for point in result["trend_points"]])
        self.assertEqual([(scope,date(2026,4,1))],repository.calls)

    async def test_resource_without_price_is_returned_as_none(self):
        result=(await FinancePriceService(Repository({RESOURCE:[]})).trends(SimpleNamespace(),date(2026,4,1)))[0]
        self.assertEqual((None,None,None,"none",None,[]),(result["current_price_irr"],result["previous_price_irr"],result["latest_change_percent"],result["trend_direction"],result["scope_kind"],result["trend_points"]))

    async def test_organization_history_is_used_when_project_override_is_absent(self):
        rows={RESOURCE:[version(1,"100","2026-01-01","organization"),version(2,"90","2026-02-01","organization")]}
        result=(await FinancePriceService(Repository(rows)).trends(SimpleNamespace(),date(2026,3,1)))[0]
        self.assertEqual(("organization","down",Decimal("-10.000000")),(result["scope_kind"],result["trend_direction"],result["latest_change_percent"]))

    def test_json_is_camel_case_decimal_strings_and_old_price_response_is_unchanged(self):
        trend=CurrentPriceTrendResponse(resourceId=RESOURCE,organizationPriceIrr="100",organizationEffectiveFrom="2026-01-01",projectPriceIrr="121",projectEffectiveFrom="2026-03-01",currentPriceIrr="121",currentEffectiveFrom="2026-03-01",previousPriceIrr="110",latestChangePercent="10.000000",trendDirection="up",scopeKind="project",trendPoints=[{"effectiveFrom":"2026-01-01","unitPriceIrr":"110"}])
        payload=trend.model_dump(by_alias=True,mode="json")
        self.assertEqual("121",payload["currentPriceIrr"]);self.assertEqual("100",payload["organizationPriceIrr"]);self.assertEqual("10.000000",payload["latestChangePercent"])
        old=PriceResponse.from_domain(version(1,"100","2026-01-01")).model_dump(by_alias=True,mode="json")
        # `createdByName` is additive -- the id it accompanies is untouched, and it is None
        # until a host directory fills it at the API boundary.
        self.assertEqual({"scopeKind","unitPriceIrr","effectiveFrom","reason","id","resourceId","version","createdBy","createdByName","createdAt"},set(old))
        self.assertIsNone(old["createdByName"],"no host asked, so no name is claimed")

    def test_repository_uses_one_dual_scoped_query_without_mutating_history(self):
        source=inspect.getsource(PsycopgFinancePriceRepository.trend_history)
        self.assertEqual(1,source.count("execute("))
        self.assertIn("r.organization_id=%s AND r.project_id=%s",source)
        self.assertIn("pv.organization_id=r.organization_id AND pv.project_id=r.project_id",source)
        self.assertNotIn("UPDATE ",source.upper());self.assertNotIn("DELETE FROM",source.upper())


if __name__=="__main__":unittest.main()
